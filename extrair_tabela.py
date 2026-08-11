r"""Regenera `tabela_xp.py` a partir dos arquivos do jogo.

    .venv\Scripts\python.exe extrair_tabela.py

Rode isto quando um patch mudar a tabela de XP. O app avisa sozinho quando
desconfia: ele continua medindo os niveis nos level ups e reclama se a medicao
divergir da tabela embutida.

Nao procuro por um endereco fixo — endereco muda a cada build. Procuro pela
FORMA da tabela: uma sequencia longa de inteiros de 32 bits que so cresce,
comeca pequena (o nivel 1 custa dezenas de XP) e chega na casa dos bilhoes.
Entre gigabytes de textura e malha, praticamente nada mais tem esse feitio.

A confirmacao vem depois, e e ela que importa: os valores tem que casar com o
que foi medido lendo a barra do jogo e cruzando com o XP dos pacotes — duas
fontes que nao se falam.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

PASTA_PADRAO = Path(r"C:\Program Files (x86)\Steam\steamapps\common\SpiritVale")

# como a tabela tem que ser pra ser aceita
MINIMO_DE_NIVEIS = 120
PRIMEIRO_MAXIMO = 200          # o nivel 1 custa pouco; nada de comecar em milhoes
ULTIMO_MINIMO = 10_000_000     # e tem que chegar longe

# medicoes independentes, pra conferir o que for achado (ver NOTAS-XP.md).
# Nao sao aproximacoes: cada faixa saiu de cruzar a porcentagem da barra com o
# XP absoluto dos pacotes, e varias leituras do mesmo nivel se cruzando.
CONFERENCIA = {
    16: (29669, 29699), 21: (72055, 72079), 25: (126648, 126662),
    33: (303101, 303121), 71: (4525421, 4526623),
    114: (39227811, 39324526), 116: (42952473, 43198619),
}


def _candidatas(dados: np.ndarray):
    """Sequencias crescentes de uint32 com cara de tabela de XP."""
    for desloc in range(4):
        corte = dados[desloc:]
        corte = corte[:len(corte) // 4 * 4]
        if len(corte) < MINIMO_DE_NIVEIS * 4:
            continue
        v = corte.view(np.uint32)
        # Acha as corridas crescentes de uma vez, sem laco Python: caminhar
        # elemento a elemento por gigabytes de asset levava horas.
        cresce = (np.diff(v.astype(np.int64)) > 0).astype(np.int8)
        bordas = np.flatnonzero(np.diff(np.concatenate(([0], cresce, [0]))))
        inicios, fins = bordas[0::2], bordas[1::2]
        longas = np.flatnonzero(fins - inicios >= MINIMO_DE_NIVEIS - 1)
        for k in longas:
            i, fim = int(inicios[k]), int(fins[k])       # fim inclusivo
            if v[i] <= PRIMEIRO_MAXIMO and v[fim] >= ULTIMO_MINIMO:
                yield desloc + i * 4, [int(x) for x in v[i:fim + 1]]


SATURACAO = 2 ** 31        # o jogo trava o valor aqui depois do ultimo nivel


def _aparar(tabela: list[int]) -> list[int]:
    """Corta a cauda saturada.

    A partir do nivel 162 o jogo repete 2^31 — e o teto do int32 assinado, nao
    um custo de verdade. Deixar isso na tabela faria o app dizer que o nivel
    162 pede dois bilhoes de XP, quando na verdade ele nao existe.
    """
    while tabela and tabela[-1] >= SATURACAO:
        tabela = tabela[:-1]
    return tabela


def _confere(tabela: list[int]) -> tuple[int, int]:
    """Quantos niveis conferidos caem dentro da faixa medida."""
    dentro = 0
    for nivel, (baixo, alto) in CONFERENCIA.items():
        if nivel <= len(tabela) and baixo <= tabela[nivel - 1] <= alto:
            dentro += 1
    return dentro, len(CONFERENCIA)


def procurar(pasta: Path):
    """Varre os arquivos do jogo e devolve (arquivo, posicao, tabela)."""
    arquivos = []
    for raiz, _, nomes in os.walk(pasta):
        for nome in nomes:
            # .resS e textura e audio cru; a tabela nao mora la
            if nome.endswith(".resS"):
                continue
            caminho = Path(raiz) / nome
            try:
                if caminho.stat().st_size <= 600 * 1024 * 1024:
                    arquivos.append(caminho)
            except OSError:
                pass
    arquivos.sort(key=lambda p: p.stat().st_size)

    for caminho in arquivos:
        try:
            dados = np.fromfile(caminho, dtype=np.uint8)
        except (OSError, MemoryError):
            continue
        for posicao, tabela in _candidatas(dados):
            tabela = _aparar(tabela)
            acertos, total = _confere(tabela)
            if acertos == total:
                return caminho, posicao, tabela
        print(f"  ...{caminho.name}", end="\r", flush=True)
    return None, None, None


def escrever(tabela: list[int], origem: str, posicao: int) -> None:
    linhas = []
    for i in range(0, len(tabela), 5):
        grupo = tabela[i:i + 5]
        valores = " ".join(f"{format(x, '_'):>13}," for x in grupo)
        linhas.append(f"    {valores}   # {i + 1}-{i + len(grupo)}")

    Path("tabela_xp.py").write_text(f'''"""Quanto XP cada nivel pede — a tabela do jogo, nao uma estimativa.

GERADO por extrair_tabela.py. Nao edite a mao; rode o extrator de novo.

Origem: {origem}, offset {posicao}.

A tabela esta no cliente porque tem que estar: o servidor manda XP absoluto, e
quem desenha a barra em porcentagem e o cliente — entao ele precisa do
denominador.

Nao ha formula por tras destes numeros. Isso foi testado a serio: 294 milhoes
de formas contra as medicoes, e nem restringindo a faixa lisa (niveis 15-130)
com os valores exatos algo desce de 1,2% de erro. Sao {len(tabela)} numeros
escritos a mao, como em Ragnarok, onde o EXP por nivel tambem e arquivo de
dados.

Uma tabela so serve classe e job — o que explica os dois baterem em 0,08%
quando medidos no mesmo nivel.
"""

from __future__ import annotations

# indice 0 = nivel 1
NECESSARIO = (
{chr(10).join(linhas)}
)

MAXIMO_NA_TABELA = len(NECESSARIO)


def xp_do_nivel(nivel: int) -> int | None:
    """XP que o nivel pede, ou None se estiver fora da tabela."""
    if 1 <= nivel <= MAXIMO_NA_TABELA:
        return NECESSARIO[nivel - 1]
    return None
''', encoding="utf-8")


def main() -> int:
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA_PADRAO
    if not pasta.is_dir():
        print(f"pasta do jogo nao encontrada: {pasta}")
        print(r"uso: python extrair_tabela.py [caminho\do\SpiritVale]")
        return 1

    print(f"procurando a tabela de XP em {pasta}\n")
    caminho, posicao, tabela = procurar(pasta)
    if tabela is None:
        print("\nnao achei nenhuma tabela que case com as medicoes.")
        print("Se o jogo mudou de formato, o filtro em _candidatas() precisa")
        print("de ajuste — ou a tabela deixou de ser um array de uint32.")
        return 1

    origem = os.path.relpath(caminho, pasta)
    acertos, total = _confere(tabela)
    print(f"\nachada em {origem}, offset {posicao}")
    print(f"  {len(tabela)} niveis  |  nivel 1 = {tabela[0]:,}  |  "
          f"nivel {len(tabela)} = {tabela[-1]:,}")
    print(f"  confere com {acertos}/{total} medicoes independentes")
    escrever(tabela, origem, posicao)
    print("\ntabela_xp.py regerado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
