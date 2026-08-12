"""Prova o porte do decodificador contra o payload sintetico do spirit-vale-tools.

Reproduz byte a byte o mesmo payload do teste deles (character/src/
synthetic-character.test-helper.ts) e confere que a nossa reading em Python
extrai os mesmos valores que o teste em TypeScript espera:

    level 42, xp 12345, level de job 18, xp de job 678

Se a ordem dos campos do jogo mudar num patch, este teste quebra — que e
exatamente o que se quer, porque ler fora de ordem nao da erro sozinho: entrega
numero errado com cara de certo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import character


def packed(out, valor):
    resto = (valor << 1) ^ (valor >> 63)
    while resto >= 0x80:
        out.append((resto & 0x7F) | 0x80)
        resto >>= 7
    out.append(resto)


def boolean(out, v):
    out.append(1 if v else 0)


def text(out, v):
    b = v.encode()
    packed(out, len(b))
    out.extend(b)


def list_of(out, valores, escreve):
    packed(out, len(valores))
    for v in valores:
        escreve(v)


def sintetico(com_update=True, name="Example Hero", uid="example-character-id"):
    """Mesma sequence de campos do helper deles.

    O `uid` e parametro porque o helper deles usa um id qualquer, mas no jogo
    de verdade esse campo e um GUID — e a cacada as cegas exige o formato.
    """
    o = []
    if com_update:
        packed(o, 4)
    boolean(o, False)
    text(o, uid)
    text(o, "example-account")
    packed(o, 7)
    text(o, "")
    text(o, "")
    text(o, name)
    boolean(o, False)
    for i in range(10):
        packed(o, i)
    boolean(o, False)
    list_of(o, [], lambda v: None)
    list_of(o, [], lambda v: None)
    text(o, "Trailblazer")
    text(o, "")
    text(o, "")
    list_of(o, [0, 12], lambda v: packed(o, v))
    packed(o, 42)
    packed(o, 12345)
    packed(o, 18)
    packed(o, 678)
    o.extend([0] * 64)          # o resto da estrutura, que nao lemos
    return bytes(o)


falhas = []


def conferir(label, obtido, esperado):
    if obtido != esperado:
        falhas.append(label)
    print(f"  {'ok ' if obtido == esperado else 'ERRO'} {label:<36} {obtido!r}"
          f"  (esperado {esperado!r})")


# o teste da rede importa os construtores daqui; sem esta guarda, rodar aquele
# rodaria este junto e a out sairia com dois "TUDO OK" embaralhados
if __name__ == "__main__":
    print("payload sintetico do spirit-vale-tools:")
    p = character.decode(sintetico(True), with_update_type=True)
    conferir("name", p.name if p else None, "Example Hero")
    conferir("level de classe", p.level if p else None, 42)
    conferir("XP absoluto", p.xp if p else None, 12345)
    conferir("level de job", p.job_level if p else None, 18)
    conferir("XP de job", p.job_xp if p else None, 678)

    print("\nrecusa o que nao entende, em vez de inventar:")
    conferir("truncado", character.decode(sintetico(True)[:12], True), None)
    conferir("lixo", character.decode(b"\x00" * 40, True), None)
    conferir("vazio", character.decode(b"", True), None)

    print("\nsanidade dos limites do jogo:")
    conferir("level acima de 150 e recusado",
             character.Progress("x", 151, 0, 1, 0).plausible(), False)
    conferir("job acima de 70 e recusado",
             character.Progress("x", 1, 0, 71, 0).plausible(), False)
    conferir("valores normais passam",
             character.Progress("x", 112, 999, 70, 5).plausible(), True)

    print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
    sys.exit(1 if falhas else 0)
