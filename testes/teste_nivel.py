"""Prova a conta que junta as duas fontes: XP exato + tamanho do nivel.

O servidor manda XP absoluto mas nao manda quanto o nivel pede. A barra manda a
porcentagem mas nao manda numero nenhum. Juntas fecham a conta — e depois disso
a barra nao e mais necessaria.

Testa sem abrir janela: so os dois metodos de calculo, num objeto de mentira.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import comum
import xp as motor_xp
import xp_analyzer
from personagem import Progresso

comum.salvar_config = lambda *_: None          # o teste nao toca no config real

falhas = []


def conferir(rotulo, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(rotulo)
    print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<46} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


class Fingido:
    """So o suficiente pros dois metodos rodarem, sem Tk e sem rede."""
    TETO = motor_xp.LeitorMemoria.TETO
    _aprender_necessario = xp_analyzer.XPAnalyzer._aprender_necessario
    _leitura_da_rede = xp_analyzer.XPAnalyzer._leitura_da_rede

    def __init__(self):
        self.necessario, self._amostras, self.cfg = {}, {}, {}
        self.fila = type("F", (), {"put": staticmethod(lambda *_: None)})()


app = Fingido()
galinho = Progresso("Galinho", 114, 6_000_000, 70, 0)

print("antes de aprender, a rede sozinha nao sabe a porcentagem:")
conferir("sem tamanho de nivel, nao inventa", app._leitura_da_rede(galinho), None)

print("\naprendendo com a barra (6M de XP marcando 40%):")
for _ in range(4):
    app._aprender_necessario(galinho, {"base_pct": 40.0, "job_pct": 100.0})
conferir("4 amostras ainda e pouco", app.necessario.get("base:114"), None)
app._aprender_necessario(galinho, {"base_pct": 40.0, "job_pct": 100.0})
conferir("na quinta, aprende", app.necessario.get("base:114"), 15_000_000)

print("\numa leitura ruim da barra nao estraga o aprendido:")
for _ in range(3):
    app._aprender_necessario(galinho, {"base_pct": 4.0, "job_pct": 100.0})
conferir("mediana ignora o disparate", app.necessario.get("base:114"), 15_000_000)

print("\nagora a rede calcula tudo sozinha:")
leitura = app._leitura_da_rede(galinho)
conferir("porcentagem", leitura["base_pct"], 40.0)
conferir("nivel", leitura["base_nivel"], 114)
conferir("job no maximo vale 100%", leitura["job_pct"], 100.0)
dobro = app._leitura_da_rede(Progresso("Galinho", 114, 12_000_000, 70, 0))
conferir("o dobro de XP vira o dobro da barra", dobro["base_pct"], 80.0)
cheio = app._leitura_da_rede(Progresso("Galinho", 114, 99_000_000, 70, 0))
conferir("XP acima do esperado nao passa de 100%", cheio["base_pct"], 100.0)

print("\nnivel novo comeca sem saber de novo (cada nivel pede o seu):")
conferir("115 ainda desconhecido",
         app._leitura_da_rede(Progresso("Galinho", 115, 10, 70, 0)), None)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
