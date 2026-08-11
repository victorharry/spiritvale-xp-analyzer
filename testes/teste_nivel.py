"""Prova o aprendizado do tamanho do nivel — a unica coisa que o servidor
nao manda pronto.

Sem leitura de memoria: a fonte e o proprio level up. O maior XP visto antes da
virada e o que aquele nivel pedia.

Os numeros do cenario vem da captura real do personagem Corujo (niveis 1 a 12),
guardada em NOTAS-XP.md. O job vai no maximo (70) porque a leitura so fecha
quando as DUAS pontas sao conhecidas — meia estimativa nao vira tela.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import comum
import xp_analyzer
from personagem import Progresso

comum.salvar_config = lambda *_: None          # o teste nao toca no config real

falhas = []


def conferir(rotulo, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(rotulo)
    print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<48} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


class Fingido:
    """So o suficiente pros metodos rodarem, sem Tk e sem rede."""
    TETO = {"base": 150, "job": 70}
    CURVA = {"base": (1.6467, 3.512), "job": (2.9824, 3.318)}
    _previsto = xp_analyzer.XPAnalyzer._previsto
    _aprender_no_level_up = xp_analyzer.XPAnalyzer._aprender_no_level_up
    _leitura_da_rede = xp_analyzer.XPAnalyzer._leitura_da_rede
    informar_porcentagem = xp_analyzer.XPAnalyzer.informar_porcentagem

    def __init__(self):
        self.necessario, self.cfg = {}, {}
        self._nivel_anterior, self._pico = {}, {}
        self.fila = type("F", (), {"put": staticmethod(lambda *_: None)})()


def alimentar(app, leituras):
    for nivel, xp in leituras:
        app._aprender_no_level_up(Progresso("Corujo", nivel, xp, 70, 0))


app = Fingido()

print("sem nada medido, a formula entra — mas se declara estimativa:")
sem_medida = app._leitura_da_rede(Progresso("Corujo", 5, 900, 70, 0))
conferir("marcada como estimada", sem_medida["estimado"], True)
conferir("formula do nivel 5", app._previsto("base", 5), 469)
# 469 no nivel 5 contra 1.568 medido: a formula foi ajustada nos niveis
# 17-21 e NAO vale la embaixo. Ela existe pra ser conferida no nivel alto,
# e por isso medida sempre vence estimativa.

print("\nsubindo de nivel, o nivel anterior fica conhecido:")
alimentar(app, [(5, 700), (5, 1200), (5, 1568), (6, 107)])
conferir("nivel 5 aprendido pelo pico antes da virada",
         app.necessario.get("base:5"), 1568)
conferir("o nivel novo ainda e desconhecido",
         app.necessario.get("base:6"), None)

print("\ncom o tamanho conhecido, a rede calcula tudo sozinha:")
leitura = app._leitura_da_rede(Progresso("Corujo", 5, 784, 70, 0))
conferir("medida vence a formula", leitura["estimado"], False)
conferir("metade do nivel da 50%", round(leitura["base_pct"], 1), 50.0)
conferir("nivel vem do pacote", leitura["base_nivel"], 5)
cheio = app._leitura_da_rede(Progresso("Corujo", 5, 99_999, 70, 0))
conferir("XP acima do esperado nao passa de 100%", cheio["base_pct"], 100.0)

print("\no pico zera a cada nivel, senao um nivel contaminaria o seguinte:")
alimentar(app, [(6, 1787), (7, 148)])
conferir("nivel 6 aprendido com o pico dele, nao com o do 5",
         app.necessario.get("base:6"), 1787)

print("\nnivel maximo nao tem 'proximo', entao vale 100%:")
maximo = app._leitura_da_rede(Progresso("Galinho", 150, 0, 70, 0))
conferir("classe no teto", maximo["base_pct"], 100.0)
conferir("job no teto", maximo["job_pct"], 100.0)

print("\nXP parado nao inventa level up:")
antes = dict(app.necessario)
alimentar(app, [(7, 148), (7, 148), (7, 148)])
conferir("nada mudou", app.necessario, antes)

print("\ninformando a porcentagem a mao — o atalho que dispensa esperar o level up:")
mao = Fingido()
# numeros reais do teste com o Corujo (ver NOTAS-XP.md)
corujo = Progresso("Corujo", 18, 18_293, 13, 13_297)
mao.informar_porcentagem("base", 42.0, corujo)
conferir("42% de 18.293 XP -> o nivel pede ~43.555",
         mao.necessario.get("base:18"), 43_555)
conferir("a outra ponta cai na formula, entao fica estimada",
         mao._leitura_da_rede(corujo)["estimado"], True)
mao.informar_porcentagem("job", 84.8, corujo)
conferir("84,8% do job -> ~15.680", mao.necessario.get("job:13"), 15_680)
fechada = mao._leitura_da_rede(corujo)
conferir("com as duas medidas, nada mais e estimado", fechada["estimado"], False)
conferir("e a porcentagem bate com a informada",
         round(fechada["base_pct"], 1), 42.0)

print("\nrecusa os casos em que a conta nao existe:")
conferir("nivel maximo nao tem proximo",
         "max level" in (mao.informar_porcentagem(
             "base", 50.0, Progresso("Galinho", 150, 0, 70, 0)) or ""), True)
conferir("sem XP no nivel, nao ha o que dividir",
         "Gain a little" in (mao.informar_porcentagem(
             "base", 50.0, Progresso("Corujo", 19, 0, 14, 0)) or ""), True)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
