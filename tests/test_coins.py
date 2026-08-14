"""Prova o decodificador de ouro e a regra de "so o que sobe conta".

Os numeros aqui sao reais: saem da captura de 3 minutos que serviu pra achar o
ExpCoinsChanged_T, com o Galinho em classe 119 e job 70. Inclusive o caso mais
importante, que e o do offset deslocado.

Comecar um byte depois do inicio de um inteiro de varios bytes le o RESTO
daquele mesmo inteiro como um numero menor e termina no mesmo lugar. Ou seja,
os quatro campos seguintes saem identicos e o candidato passa em todos os
filtros: mesmo level, mesmo job, mesmas moedas. So o XP fica errado. Por isso o
decodificador tem que devolver o PRIMEIRO offset que fecha, nunca qualquer um.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coins
import xp as motor_xp

falhas = []


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<48} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


def packed(valor):
    """Codifica como o jogo codifica: zigzag + 7 bits por byte."""
    bruto = (valor << 1) ^ (-1 if valor < 0 else 0)
    if valor < 0:
        bruto = ((-valor) << 1) - 1
    saida = bytearray()
    while True:
        byte = bruto & 0x7F
        bruto >>= 7
        if bruto:
            saida.append(byte | 0x80)
        else:
            saida.append(byte)
            return bytes(saida)


def pacote(exp, level, job_exp, job_level, moedas, cabecalho=b""):
    return cabecalho + b"".join(packed(v) for v in
                                (exp, level, job_exp, job_level, moedas))


print("lendo o pacote (valores medidos na captura do Galinho):")
bruto = pacote(6785430, 119, 0, 70, 1157957, cabecalho=bytes.fromhex("67290600a0bc1a"))
lido = coins.decode(bruto, 119, 70)
conferir("xp", lido and lido.xp, 6785430)
conferir("moedas", lido and lido.coins, 1157957)
conferir("level", lido and lido.level, 119)
conferir("job no maximo reporta 0 de xp", lido and lido.job_xp, 0)

print("\no que NAO pode ser aceito:")
conferir("level diferente do conhecido",
         coins.decode(bruto, 118, 70), None)
conferir("job diferente do conhecido",
         coins.decode(bruto, 119, 69), None)
# sem exigir que os campos terminem no ultimo byte, os cinco numeros aparecem
# no meio de qualquer trafego e viram leitura falsa
conferir("campos no meio, com sobra depois",
         coins.decode(bruto + b"\x00\x00", 119, 70), None)
conferir("payload curto demais", coins.decode(b"\x01\x02", 119, 70), None)

print("\no offset deslocado (o erro que produz numero convincente):")
# 6785430 ocupa varios bytes; comecar depois do primeiro le o resto dele
so_campos = pacote(6785430, 119, 0, 70, 1157957)
deslocado = so_campos[1:]
torto = coins.decode(deslocado, 119, 70)
conferir("o deslocado tambem 'fecha'", torto is not None, True)
conferir("e mente no xp", torto and torto.xp != 6785430, True)
conferir("mas acerta as moedas", torto and torto.coins, 1157957)
conferir("no pacote inteiro, vale o primeiro offset",
         coins.decode(so_campos, 119, 70).xp, 6785430)

print("\ncontando o ouro da sessao:")
g = motor_xp.GoldTracker()
t = time.time()
for i, moedas in enumerate([1157957, 1158584, 1160000, 1174612]):
    g.record(moedas, t + i * 60)
conferir("total e a ultima leitura", g.total, 1174612)
conferir("ganho e a soma das subidas", g.gained, 1174612 - 1157957)

print("\ngastar nao pode apagar o que foi farmado:")
g = motor_xp.GoldTracker()
t = time.time()
g.record(1_000_000, t)
g.record(1_050_000, t + 60)      # farmou 50k
g.record(200_000, t + 120)       # comprou algo caro
g.record(210_000, t + 180)       # farmou mais 10k
conferir("ganho ignora a queda", g.gained, 60_000)
conferir("total acompanha a carteira de verdade", g.total, 210_000)
conferir("ritmo nunca fica negativo", g.rate() >= 0, True)

print("\nformatando numero grande em janela pequena:")
conferir("milhoes", motor_xp.format_gold(1174612), "1.17M")
conferir("milhares", motor_xp.format_gold(16655), "16.7k")
conferir("pouco", motor_xp.format_gold(842), "842")
conferir("nada ainda", motor_xp.format_gold(None), "—")

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
