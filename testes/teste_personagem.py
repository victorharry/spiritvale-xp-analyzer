"""Prova o porte do decodificador contra o payload sintetico do spirit-vale-tools.

Reproduz byte a byte o mesmo payload do teste deles (character/src/
synthetic-character.test-helper.ts) e confere que a nossa leitura em Python
extrai os mesmos valores que o teste em TypeScript espera:

    nivel 42, xp 12345, nivel de job 18, xp de job 678

Se a ordem dos campos do jogo mudar num patch, este teste quebra — que e
exatamente o que se quer, porque ler fora de ordem nao da erro sozinho: entrega
numero errado com cara de certo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import personagem


def packed(saida, valor):
    resto = (valor << 1) ^ (valor >> 63)
    while resto >= 0x80:
        saida.append((resto & 0x7F) | 0x80)
        resto >>= 7
    saida.append(resto)


def booleano(saida, v):
    saida.append(1 if v else 0)


def texto(saida, v):
    b = v.encode()
    packed(saida, len(b))
    saida.extend(b)


def lista(saida, valores, escreve):
    packed(saida, len(valores))
    for v in valores:
        escreve(v)


def sintetico(com_update=True, nome="Example Hero"):
    """Mesma sequencia de campos do helper deles."""
    o = []
    if com_update:
        packed(o, 4)
    booleano(o, False)
    texto(o, "example-character-id")
    texto(o, "example-account")
    packed(o, 7)
    texto(o, "")
    texto(o, "")
    texto(o, nome)
    booleano(o, False)
    for i in range(10):
        packed(o, i)
    booleano(o, False)
    lista(o, [], lambda v: None)
    lista(o, [], lambda v: None)
    texto(o, "Trailblazer")
    texto(o, "")
    texto(o, "")
    lista(o, [0, 12], lambda v: packed(o, v))
    packed(o, 42)
    packed(o, 12345)
    packed(o, 18)
    packed(o, 678)
    o.extend([0] * 64)          # o resto da estrutura, que nao lemos
    return bytes(o)


falhas = []


def conferir(rotulo, obtido, esperado):
    if obtido != esperado:
        falhas.append(rotulo)
    print(f"  {'ok ' if obtido == esperado else 'ERRO'} {rotulo:<36} {obtido!r}"
          f"  (esperado {esperado!r})")


print("payload sintetico do spirit-vale-tools:")
p = personagem.decodificar(sintetico(True), com_tipo_de_update=True)
conferir("nome", p.nome if p else None, "Example Hero")
conferir("nivel de classe", p.nivel if p else None, 42)
conferir("XP absoluto", p.xp if p else None, 12345)
conferir("nivel de job", p.nivel_job if p else None, 18)
conferir("XP de job", p.xp_job if p else None, 678)

print("\nrecusa o que nao entende, em vez de inventar:")
conferir("truncado", personagem.decodificar(sintetico(True)[:12], True), None)
conferir("lixo", personagem.decodificar(b"\x00" * 40, True), None)
conferir("vazio", personagem.decodificar(b"", True), None)

print("\nsanidade dos limites do jogo:")
conferir("nivel acima de 150 e recusado",
         personagem.Progresso("x", 151, 0, 1, 0).plausivel(), False)
conferir("job acima de 70 e recusado",
         personagem.Progresso("x", 1, 0, 71, 0).plausivel(), False)
conferir("valores normais passam",
         personagem.Progresso("x", 112, 999, 70, 5).plausivel(), True)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
