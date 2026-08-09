"""Cadeia de ponteiros estavel: acha as barras na hora, sem varrer nada.

O endereco muda a cada abertura do jogo (ASLR + heap gerenciado do Unity), mas
o CAMINHO ate ele nao muda: um deslocamento fixo dentro de GameAssembly.dll que
aponta pra um objeto, que aponta pra outro, ate a barra.

O metodo e o mesmo do Cheat Engine, e o passo que importa e o SEGUNDO:

    1. varrer()   -> milhares de caminhos candidatos que levam ao endereco
    2. filtrar()  -> reabre o jogo, acha o endereco de novo e mantem so os
                     caminhos que continuam resolvendo pra ele

Uma varredura sozinha nao vale nada: quase todo caminho e coincidencia de uma
sessao. Repetir o passo 2 duas ou tres vezes derruba milhares pra um punhado, e
o que sobra funciona pra sempre — ate o jogo receber um patch.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import memoria

ARQUIVO = "cadeia_xp.json"
NIVEIS = 6
FOLGA = 0x1000        # deslocamento maximo dentro de um objeto


def _regioes(proc) -> list[tuple[int, int]]:
    import ctypes

    info = memoria.MEMORY_BASIC_INFORMATION64()
    endereco, saida = 0, []
    while endereco < 0x7FFFFFFFFFFF:
        if not memoria.k32.VirtualQueryEx(proc.handle, ctypes.c_void_p(endereco),
                                          ctypes.byref(info), ctypes.sizeof(info)):
            break
        base, ext = info.BaseAddress, info.RegionSize
        if (info.State == memoria.MEM_COMMIT and info.Protect in (0x04, 0x02, 0x20)
                and 4096 <= ext <= 256 * 1024 * 1024):
            saida.append((base, ext))
        if base + ext <= endereco:
            break
        endereco = base + ext
    return saida


def _apontam_para(proc, regioes, alvos: np.ndarray, folga: int):
    """(endereco do ponteiro, alvo alcancado, deslocamento) — vetorizado."""
    alvos = np.sort(alvos.astype(np.uint64))
    achados = []
    for inicio, tam in regioes:
        dados = proc.ler(inicio, tam)
        if not dados:
            continue
        valores = np.frombuffer(dados, dtype="<u8", count=len(dados) // 8)
        idx = np.searchsorted(alvos, valores, side="right") - 1
        ok = np.flatnonzero(idx >= 0)
        if not len(ok):
            continue
        base = alvos[idx[ok]]
        delta = valores[ok].astype(np.int64) - base.astype(np.int64)
        bons = ok[(delta >= 0) & (delta <= folga)]
        for k in bons:
            v = int(valores[k])
            a = int(alvos[np.searchsorted(alvos, v, side="right") - 1])
            achados.append((inicio + int(k) * 8, a, v - a))
    return achados


def varrer(proc, alvo: int, niveis: int = NIVEIS, folga: int = FOLGA,
           teto: int = 300_000, aviso=print) -> list[dict]:
    """Todos os caminhos ancorados num modulo que levam ate `alvo`."""
    mods = memoria.modulos(proc.pid)
    faixas = {n: (b, b + t) for n, (b, t) in mods.items() if t > 0}
    regioes = _regioes(proc)
    for nome, (base, tam) in mods.items():
        if tam > 4096:
            regioes.append((base, min(tam, 128 * 1024 * 1024)))

    # de quem cada endereco veio, pra reconstruir o caminho no fim
    pai: dict[int, tuple[int, int]] = {}
    atual = np.array([alvo], dtype=np.uint64)
    caminhos: list[dict] = []

    for nivel in range(1, niveis + 1):
        achados = _apontam_para(proc, regioes, atual, folga)
        aviso(f"  nivel {nivel}: {len(achados):,} ponteiro(s)")
        if not achados:
            break
        novos = []
        for endereco, destino, desloc in achados[:teto]:
            pai[endereco] = (destino, desloc)
            for nome, (ini, fim) in faixas.items():
                if ini <= endereco < fim:
                    passos = [desloc]
                    ponto = destino
                    while ponto in pai:
                        prox, d = pai[ponto]
                        passos.append(d)
                        ponto = prox
                    caminhos.append({"modulo": nome, "base": endereco - ini,
                                     "offsets": passos})
                    break
            else:
                novos.append(endereco)
        if caminhos:
            aviso(f"  {len(caminhos):,} caminho(s) ancorado(s) num modulo")
            break
        if not novos:
            break
        atual = np.array(sorted(set(novos)), dtype=np.uint64)
    return caminhos


def resolver(proc, caminho: dict) -> int | None:
    """Segue o caminho e devolve o endereco final nesta sessao."""
    mods = memoria.modulos(proc.pid)
    if caminho["modulo"] not in mods:
        return None
    endereco = mods[caminho["modulo"]][0] + caminho["base"]
    passos = caminho["offsets"]
    for i, passo in enumerate(passos):
        ponteiro = proc.ler_ponteiro(endereco)
        if not ponteiro:
            return None
        endereco = ponteiro + passo
    return endereco


def filtrar(proc, caminhos: list[dict], alvo: int) -> list[dict]:
    """Mantem so os caminhos que ainda chegam no alvo — a peneira que vale."""
    return [c for c in caminhos if resolver(proc, c) == alvo]


def caminho_arquivo(pasta: Path) -> Path:
    return pasta / ARQUIVO


def carregar(pasta: Path) -> dict:
    arq = caminho_arquivo(pasta)
    if not arq.exists():
        return {}
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar(pasta: Path, dados: dict) -> None:
    caminho_arquivo(pasta).write_text(
        json.dumps(dados, indent=2), encoding="utf-8")
