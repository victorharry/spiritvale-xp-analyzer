r"""Busca pela formula da curva de XP, usando todos os nucleos.

    .venv\Scripts\python.exe buscar_formula.py

A ideia, do Victor: quem escreve a formula de um jogo tende a usar numeros
redondos — 3, 3.5, 10, 15 — e nos estavamos sempre tentando encaixar um numero
quebrado. Entao vale varrer o espaco e ver se algo redondo bate.

O que torna isso rigoroso e barato ao mesmo tempo:

**Cada medicao e um INTERVALO, nao um ponto.** A barra do jogo mostra uma casa
decimal e arredonda — verificado: supondo truncamento, cinco niveis ficariam com
intervalos impossiveis; supondo arredondamento, nenhum. Ler 88,4% com 268.064
de XP significa que o level pede entre 303.101 e 303.121, e nada fora disso.
Varias leituras do mesmo level se cruzam e apertam mais ainda.

**Com o intervalo, o teste vira exato.** Para uma forma `f(n)` com um fator de
escala livre, `lo <= a*f(n) <= hi` em todo level quer dizer que `a` tem que
estar em `[max(lo/f), min(hi/f)]`. Ou essa intersecao existe, ou a forma esta
descartada — sem minimos quadrados, sem tolerancia escolhida a dedo.

Por isso o criterio aqui nao e "erro medio pequeno": e caber. Uma formula que
acerta quinze niveis e estoura dois nao e a formula do jogo.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def montar_faixas() -> dict[int, tuple[float, float]]:
    """Intervalo de cada level, cruzando todas as amostras registradas."""
    amostras = []
    for pasta in (ROOT, Path(os.environ.get("APPDATA", "")) / "XP Analyzer"):
        caminho = pasta / "amostras-xp.tsv"
        if not caminho.exists():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            parts = linha.split("\t")
            if len(parts) < 4:
                continue
            _, level, xp, pct = parts[:4]
            if float(pct) >= 5.0 and int(xp) > 0:
                amostras.append((int(level), int(xp), float(pct)))

    faixas: dict[int, tuple[float, float]] = {}
    for level, xp, pct in amostras:
        baixo, alto = xp / ((pct + 0.05) / 100), xp / ((pct - 0.05) / 100)
        if level in faixas:
            baixo = max(baixo, faixas[level][0])
            alto = min(alto, faixas[level][1])
        faixas[level] = (baixo, alto)

    # Onde as amostras se contradizem, o culpado nao e a medicao: e o intervalo
    # entre ler a porcentagem na tela e o packet que trouxe o XP. Ali eu afrouxo
    # pra uniao, em vez de pick uma amostra e fingir que as outras nao
    # existem — a incerteza e real e tem que aparecer na conta.
    for level, (baixo, alto) in list(faixas.items()):
        if baixo > alto:
            todas = [(xp / ((p + 0.05) / 100), xp / ((p - 0.05) / 100))
                     for n, xp, p in amostras if n == level]
            faixas[level] = (min(b for b, _ in todas), max(a for _, a in todas))
    return faixas


# Calculado na IMPORTACAO, nao em main(). No Windows o multiprocessing usa
# spawn: cada worker reimporta este modulo do zero. Enquanto isso ficava dentro
# de main(), os filhos herdavam a tabela VAZIA — e com zero niveis pra conferir,
# o laco de folga() nao rodava nenhuma vez e devolvia 0,0 pra qualquer coisa.
# O resultado foi uma busca inteira dizendo que ate a*n^2 cabia.
FAIXAS: dict[int, tuple[float, float]] = montar_faixas()
NIVEIS: list[int] = sorted(FAIXAS)


def folga(forma) -> float:
    """Quanto FALTA pra forma caber em todos os intervalos, em porcentagem.

    Zero significa que existe um fator de escala que satisfaz todos ao mesmo
    tempo. Acima de zero, o numero diz o size do problema — util pra
    ranquear as quase-solucoes em vez de so dizer "nao".
    """
    menor_teto = float("inf")
    maior_piso = 0.0
    for n in NIVEIS:
        f = forma(n)
        if f <= 0:
            return float("inf")
        baixo, alto = FAIXAS[n]
        piso, teto = baixo / f, alto / f
        if piso > maior_piso:
            maior_piso = piso
        if teto < menor_teto:
            menor_teto = teto
    if maior_piso <= menor_teto:
        return 0.0
    return (maior_piso - menor_teto) / menor_teto * 100.0


def escala(forma) -> tuple[float, float]:
    """A faixa de fatores de escala que fazem a forma caber."""
    pisos = [FAIXAS[n][0] / forma(n) for n in NIVEIS]
    tetos = [FAIXAS[n][1] / forma(n) for n in NIVEIS]
    return max(pisos), min(tetos)


# -- espaco de busca ------------------------------------------------------

def _avaliar(familia, v):
    if familia == "potencia":
        c, b = v
        return (lambda n: (n + c) ** b), f"a * (n{c:+g})^{b:g}"
    if familia == "pot_exp":
        c, b, d = v
        return (lambda n: (n + c) ** b * d ** n), f"a * (n{c:+g})^{b:g} * {d:g}^n"
    if familia == "exp_var":
        c, b, e = v
        return ((lambda n: (n + c) ** (b + e * n)),
                f"a * (n{c:+g})^({b:g}{e:+g}*n)")
    if familia == "degrau":
        c, b, passo, m = v
        return ((lambda n: (n + c) ** b * m ** (n // passo)),
                f"a * (n{c:+g})^{b:g} * {m:g}^floor(n/{passo})")
    raise ValueError(familia)


def _lote(tarefa):
    """Um pedaco do espaco, avaliado num nucleo."""
    familia, valores = tarefa
    found = []
    for v in valores:
        try:
            forma, name = _avaliar(familia, v)
            f = folga(forma)
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if f < 2.0:
            found.append((f, name, familia))
    found.sort()
    return found[:30]


def tarefas():
    """Os lotes. Grade fina nos parametros que exigem forca raw_value mesmo."""
    # potencia deslocada — a familia que ja apontou pra (n-1,5)^3
    cs = [x / 100 for x in range(-1000, 1001)]        # -10 a 10, de 0,01
    bs = [x / 1000 for x in range(2000, 6001)]        # 2 a 6, de 0,001
    for i in range(0, len(cs), 25):
        yield ("potencia", [(c, b) for c in cs[i:i + 25] for b in bs])

    cs2 = [x / 20 for x in range(-200, 201)]          # -10 a 10, de 0,05
    bs2 = [x / 100 for x in range(200, 601)]          # 2 a 6, de 0,01

    # potencia vezes exponencial
    ds = [1 + x / 10000 for x in range(0, 401)]       # 1 a 1,04
    for i in range(0, len(cs2), 5):
        yield ("pot_exp", [(c, b, d) for c in cs2[i:i + 5]
                           for b in bs2 for d in ds])

    # expoente que cresce com o level
    es = [x / 100000 for x in range(0, 1001)]
    for i in range(0, len(cs2), 5):
        yield ("exp_var", [(c, b, e) for c in cs2[i:i + 5]
                           for b in bs2 for e in es])

    # multiplicador a cada N niveis (tiers de MMO)
    ms = [1 + x / 1000 for x in range(0, 501)]
    for passo in range(5, 61, 5):
        yield ("degrau", [(c, b, passo, m) for c in cs2[::4]
                          for b in bs2[::4] for m in ms])


def main() -> None:
    if not NIVEIS:
        print("nenhuma amostra registrada ainda (amostras-xp.tsv)")
        return
    (ROOT / "faixas-xp.json").write_text(
        json.dumps({str(k): v for k, v in FAIXAS.items()}, indent=1),
        encoding="utf-8")

    nucleos = max(1, (os.cpu_count() or 4) - 1)
    lotes = list(tarefas())
    total = sum(len(v) for _, v in lotes)
    print("XP Analyzer — busca pela formula da curva de XP\n")
    print(f"  {len(NIVEIS)} niveis medidos, de {min(NIVEIS)} a {max(NIVEIS)}")
    print("  intervalos mais apertados:")
    apertados = sorted(NIVEIS,
                       key=lambda n: (FAIXAS[n][1] - FAIXAS[n][0]) / FAIXAS[n][0])
    for n in apertados[:3]:
        lo, hi = FAIXAS[n]
        print(f"      level {n:>3}: {lo:>12,.0f} a {hi:>12,.0f}"
              f"   ({(hi - lo) / lo * 100:.3f}%)")
    print(f"\n  {total:,} formas em {len(lotes)} lotes, em {nucleos} nucleos")
    print("  criterio: caber em TODOS os intervalos ao mesmo tempo\n")

    start = time.time()
    found = []
    with mp.Pool(nucleos) as pool:
        for i, resultado in enumerate(pool.imap_unordered(_lote, lotes), 1):
            found.extend(resultado)
            found.sort()
            found = found[:200]
            if i % 5 == 0 or i == len(lotes):
                melhor = found[0][0] if found else float("inf")
                print(f"  lote {i}/{len(lotes)}  ({time.time() - start:5.0f}s)"
                      f"   falta pra caber: {melhor:.4f}%", flush=True)

    print(f"\nterminou em {time.time() - start:.0f}s\n")
    cabem = [a for a in found if a[0] == 0.0]
    if cabem:
        print(f"CABE EM TODOS OS INTERVALOS — {len(cabem)} forma(s):")
        for _, name, familia in cabem[:25]:
            print(f"  {name}")
    else:
        print("Nenhuma forma cabe em todos os intervalos. As mais proximas:")
        for f, name, familia in found[:25]:
            print(f"  falta {f:7.4f}%  [{familia:>8}]  {name}")
        print("\nQuanto menor a folga, mais perto. Uma folga que nao chega a")
        print("zero com grade fina e evidencia de que a curva nao e uma formula")
        print("unica — provavelmente e tabela. Ver NOTAS-XP.md.")


if __name__ == "__main__":
    main()
