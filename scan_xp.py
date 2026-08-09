"""Acha na memoria do jogo onde fica o XP — por eliminacao, em varias passadas.

    1) .venv\\Scripts\\python.exe scan_xp.py iniciar --base 111 --job 70
    2) ganhe XP          ->  .venv\\Scripts\\python.exe scan_xp.py subiu
    3) fique PARADO 30s  ->  .venv\\Scripts\\python.exe scan_xp.py parado
    4) repita 2 e 3 ate sobrar pouca coisa
    5) .venv\\Scripts\\python.exe scan_xp.py mostrar

Uma passada so nao resolve: metade da memoria do jogo muda a cada quadro
(animacao, posicao, temporizador). A passada PARADO e a que limpa — ela exige
que o valor tenha ficado igual enquanto voce nao ganhava XP, e isso derruba
tudo que varia sozinho. Alternar "subiu" e "parado" corta o campo por duas
peneiras opostas.

A primeira busca usa uma ancora: nivel base e nivel de job vivem no mesmo
objeto, coladinhos. Procurar "111 com 70 por perto" ja elimina milhoes de
coincidencias antes de comecar.
"""

from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path

import numpy as np

import memoria

ESTADO = Path(__file__).resolve().parent / "debug" / "scan_xp.pkl"
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04


def regioes_de_dados(proc: memoria.Processo) -> list[tuple[int, int]]:
    """So memoria privada e gravavel: e onde vive o estado do jogo."""
    import ctypes

    info = memoria.MEMORY_BASIC_INFORMATION64()
    endereco, saida = 0, []
    while endereco < 0x7FFFFFFFFFFF:
        if not memoria.k32.VirtualQueryEx(proc.handle, ctypes.c_void_p(endereco),
                                          ctypes.byref(info), ctypes.sizeof(info)):
            break
        base, extensao = info.BaseAddress, info.RegionSize
        if (info.State == memoria.MEM_COMMIT and info.Type == MEM_PRIVATE
                and info.Protect == PAGE_READWRITE
                and 4096 <= extensao <= 256 * 1024 * 1024):
            saida.append((base, extensao))
        if base + extensao <= endereco:
            break
        endereco = base + extensao
    return saida


def achar_ancora(proc, regioes, base_nivel, job_nivel, alcance=256) -> list[int]:
    """Enderecos do nivel base que tem o nivel de job por perto."""
    achados = []
    passo = alcance // 4
    for inicio, tamanho in regioes:
        dados = proc.ler(inicio, tamanho)
        if not dados:
            continue
        valores = np.frombuffer(dados, dtype="<i4", count=len(dados) // 4)
        (bases,) = np.where(valores == base_nivel)
        if not len(bases):
            continue
        (jobs,) = np.where(valores == job_nivel)
        if not len(jobs):
            continue
        for indice in bases:
            if np.any((jobs > indice - passo) & (jobs < indice + passo)):
                achados.append(inicio + int(indice) * 4)
    return achados


class Bloco:
    """Uma vizinhanca sob observacao, com a mascara do que ainda esta vivo."""

    __slots__ = ("inicio", "tamanho", "valores", "vivos")

    def __init__(self, inicio: int, tamanho: int, valores: np.ndarray):
        self.inicio = inicio
        self.tamanho = tamanho
        self.valores = valores
        self.vivos = np.ones(len(valores), dtype=bool)

    def enderecos(self) -> np.ndarray:
        return self.inicio + np.flatnonzero(self.vivos) * 4


def ler_bloco(proc, inicio: int, tamanho: int) -> np.ndarray | None:
    dados = proc.ler(inicio, tamanho)
    if not dados:
        return None
    return np.frombuffer(dados, dtype="<i4", count=len(dados) // 4).copy()


def peneirar(proc, blocos: list[Bloco], modo: str) -> int:
    """Mantem so quem se comportou como o esperado nesta passada.

    subiu  = cresceu um pouco (XP nao anda pra tras, nem salta bilhoes)
    parado = ficou exatamente igual (derruba animacao, relogio, posicao)
    """
    restantes = 0
    for bloco in blocos:
        agora = ler_bloco(proc, bloco.inicio, bloco.tamanho)
        if agora is None or len(agora) != len(bloco.valores):
            bloco.vivos[:] = False
            continue
        if modo == "subiu":
            delta = agora.astype(np.int64) - bloco.valores.astype(np.int64)
            # crescimento plausivel: positivo e nao absurdo. Delta gigante e
            # ponteiro ou float lido como inteiro, nao contador de XP.
            ok = (delta > 0) & (delta < 100_000_000) & (agora > 0)
        else:
            ok = agora == bloco.valores
        bloco.vivos &= ok
        bloco.valores = agora
        restantes += int(bloco.vivos.sum())
    return restantes


def carregar() -> tuple[list[Bloco], dict]:
    if not ESTADO.exists():
        raise SystemExit("Nenhuma busca em andamento. Rode primeiro:\n"
                         "  .venv\\Scripts\\python.exe scan_xp.py iniciar "
                         "--base <nivel> --job <job>")
    with ESTADO.open("rb") as arquivo:
        return pickle.load(arquivo)


def salvar(blocos: list[Bloco], meta: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    with ESTADO.open("wb") as arquivo:
        pickle.dump((blocos, meta), arquivo)


def abrir_jogo(nome: str) -> memoria.Processo:
    pid = memoria.achar_processo(nome)
    if not pid:
        raise SystemExit(f"{nome} nao esta aberto.")
    return memoria.Processo(pid)


def cmd_iniciar(args) -> None:
    with abrir_jogo(args.processo) as proc:
        regioes = regioes_de_dados(proc)
        total = sum(t for _, t in regioes) / 1024 / 1024
        print(f"varrendo {len(regioes)} regioes privadas ({total:.0f} MB)...")
        inicio = time.time()
        ancoras = achar_ancora(proc, regioes, args.base, args.job, args.alcance)
        print(f"  {len(ancoras)} ancora(s) em {time.time() - inicio:.1f}s")
        if not ancoras:
            print("Nada. Confira os niveis, ou aumente --alcance.")
            return

        blocos, vistos = [], set()
        for endereco in ancoras:
            comeco = endereco - args.antes
            if comeco in vistos:
                continue
            vistos.add(comeco)
            valores = ler_bloco(proc, comeco, args.antes + args.depois)
            if valores is not None:
                blocos.append(Bloco(comeco, args.antes + args.depois, valores))
        vivos = sum(int(b.vivos.sum()) for b in blocos)
        salvar(blocos, {"base": args.base, "job": args.job, "passadas": []})
        print(f"  {len(blocos)} vizinhancas, {vivos:,} valores sob observacao\n")
        print("Agora GANHE XP e rode:  scan_xp.py subiu")


def cmd_passada(args, modo: str) -> None:
    blocos, meta = carregar()
    antes = sum(int(b.vivos.sum()) for b in blocos)
    with abrir_jogo(args.processo) as proc:
        restantes = peneirar(proc, blocos, modo)
    meta["passadas"].append(modo)
    salvar(blocos, meta)
    print(f"passada '{modo}': {antes:,} -> {restantes:,} candidatos")
    if restantes == 0:
        print("\nZerou. Comece de novo — provavelmente a passada foi feita com")
        print("o jogo em estado diferente do esperado.")
    elif restantes <= 30:
        print("\nJa da pra olhar:  scan_xp.py mostrar")
    else:
        seguinte = "parado" if modo == "subiu" else "subiu"
        acao = ("fique PARADO uns 30s" if seguinte == "parado" else "GANHE XP")
        print(f"\nAgora {acao} e rode:  scan_xp.py {seguinte}")


def cmd_mostrar(args) -> None:
    blocos, meta = carregar()
    with abrir_jogo(args.processo) as proc:
        linhas = []
        for bloco in blocos:
            agora = ler_bloco(proc, bloco.inicio, bloco.tamanho)
            if agora is None:
                continue
            for indice in np.flatnonzero(bloco.vivos):
                endereco = bloco.inicio + int(indice) * 4
                valor = int(agora[indice])
                # o par de 8 bytes, caso o XP seja int64
                largo = proc.ler_int(endereco, 8, sinal=True)
                linhas.append((endereco, valor, largo))
    print(f"passadas: {' -> '.join(meta['passadas']) or '(nenhuma)'}")
    print(f"{len(linhas)} candidato(s) vivos\n")
    for endereco, valor, largo in linhas[:60]:
        extra = f"   int64: {largo:,}" if largo and abs(largo) < 10**15 else ""
        print(f"  0x{endereco:X}   int32: {valor:>13,}{extra}")
    if len(linhas) > 60:
        print(f"  ... e mais {len(linhas) - 60}")
    if linhas:
        print("\nO XP e o valor que bate com a barra. Sabendo a porcentagem")
        print("(ex.: 25,4%), o campo de XP dividido pelo de XP-do-nivel da isso.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("acao", choices=["iniciar", "subiu", "parado", "mostrar"])
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--base", type=int, help="seu nivel base (so no 'iniciar')")
    p.add_argument("--job", type=int, help="seu nivel de job (so no 'iniciar')")
    p.add_argument("--alcance", type=int, default=256)
    p.add_argument("--antes", type=int, default=256)
    p.add_argument("--depois", type=int, default=512)
    args = p.parse_args()

    if args.acao == "iniciar":
        if args.base is None or args.job is None:
            raise SystemExit("Informe --base e --job (os niveis que a barra mostra).")
        cmd_iniciar(args)
    elif args.acao in ("subiu", "parado"):
        cmd_passada(args, args.acao)
    else:
        cmd_mostrar(args)


if __name__ == "__main__":
    main()
