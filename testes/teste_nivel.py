"""Prova de onde sai o tamanho de cada nivel, e em que ordem.

Hoje a fonte e a tabela do proprio jogo (`tabela_xp.py`), extraida dos arquivos
do cliente. Antes dela existiam dois metodos de medicao, e os dois continuam
aqui: o aprendizado no level up e a porcentagem digitada. Nao sao redundancia
inutil — foram eles que produziram as 18 medicoes que CONFEREM a tabela, e sao
eles que sobram se um patch mudar o arquivo e a extracao parar de valer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import comum
import tabela_xp
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
    _previsto = xp_analyzer.XPAnalyzer._previsto
    _tabela_medida = xp_analyzer.XPAnalyzer._tabela_medida
    vao_ate_medicao = xp_analyzer.XPAnalyzer.vao_ate_medicao
    _aprender_no_level_up = xp_analyzer.XPAnalyzer._aprender_no_level_up
    _leitura_da_rede = xp_analyzer.XPAnalyzer._leitura_da_rede

    def __init__(self):
        self.necessario, self.cfg = {}, {}
        self._nivel_anterior, self._pico, self._historico = {}, {}, {}
        self.fila = type("F", (), {"put": staticmethod(lambda *_: None)})()


def alimentar(app, leituras):
    for nivel, xp in leituras:
        app._aprender_no_level_up(Progresso("Corujo", nivel, xp, 70, 0))


app = Fingido()

print("a tabela do jogo responde sozinha, sem nenhuma medicao do usuario:")
conferir("nivel 5", app._previsto("base", 5), 1620)
conferir("nivel 114", app._previsto("base", 114), 39_284_872)
leitura = app._leitura_da_rede(Progresso("Galinho", 114, 19_642_436, 70, 0))
conferir("metade do nivel 114 da 50%", round(leitura["base_pct"], 2), 50.0)
conferir("e nao vem marcado como estimativa", leitura["estimado"], False)

print("\njob no maximo vale 100%, sem consultar tabela nenhuma:")
conferir("job 70", leitura["job_pct"], 100.0)
maximo = app._leitura_da_rede(Progresso("Galinho", 150, 0, 70, 0))
conferir("classe 150", maximo["base_pct"], 100.0)

print("\nacima da tabela (nivel 162+, onde o jogo satura em 2^31):")
conferir("sem medicao, nao inventa", app._previsto("base", 200), None)

print("\nsubir de nivel agora VIGIA a tabela em vez de alimentar o config:")
quieto = Fingido()
recados = []
quieto.fila = type("F", (), {"put": staticmethod(lambda x: recados.append(x[1]))})()
# 1.600 antes de virar, contra 1.620 da tabela: uma morte de mob de diferenca
alimentar(quieto, [(5, 700), (5, 1200), (5, 1600), (6, 107)])
conferir("medicao que concorda nao gera aviso",
         any("WARNING" in str(r) for r in recados), False)
conferir("e nao grava nada (a tabela ja sabe)",
         quieto.necessario.get("base:5"), None)

print("\nmedicao que DIVERGE da tabela vira aviso, nao vira valor:")
vigia = Fingido()
avisos = []
vigia.fila = type("F", (), {"put": staticmethod(lambda x: avisos.append(x[1]))})()
# nivel 5 pede 1.620; fingir que so juntou 900 antes de virar e sinal de patch
alimentar(vigia, [(5, 900), (6, 10)])
conferir("avisou", any("WARNING" in str(a) for a in avisos), True)
conferir("e nao gravou o valor errado", vigia.necessario.get("base:5"), None)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
