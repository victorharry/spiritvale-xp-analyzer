"""XP Analyzer — aplicativo independente, sem nada do mercado.

Le a barra de XP direto da memoria do jogo e mostra, numa janelinha
arrastavel sobre o jogo, quanto falta pro proximo nivel de classe e de job.

    .venv\\Scripts\\python.exe xp_analyzer.py

Nao ha janela principal: a propria sobreposicao E o programa. Fechar nela
fecha tudo.

Como funciona: a barra do jogo e translucida, entao o OCR sozinho nao serve
(o nome de um jogador passando atras dela e texto branco na mesma fonte). O
valor vem da MEMORIA — uma unica leitura de tela serve so pra desempatar qual
das barras de UI e a sua, e depois disso o OCR sai de cena.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import comum
import xp as motor_xp
from comum import capturar as capturar_regiao
from xp_janela import JanelaXP


class XPAnalyzer(ctk.CTk):
    """Aplicativo de uma janela so: a sobreposicao."""

    def __init__(self):
        super().__init__()
        self.withdraw()                    # a raiz nunca aparece
        self.cfg = comum.carregar_config()
        comum.ativar_dpi()
        try:
            comum.configurar_tesseract(self.cfg)
            self.erro_tesseract = None
        except SystemExit as erro:
            self.erro_tesseract = str(erro)

        if not self.cfg.get("xp_regiao") and not self._calibrar():
            self.destroy()
            raise SystemExit(1)

        self.fila: queue.Queue = queue.Queue()
        self.parar = threading.Event()
        self.rastreador = motor_xp.Rastreador(
            janela_minutos=float(self.cfg.get("xp_janela_minutos", 15)))

        self.pausado = False
        self.deslocamento = 0.0     # segundos pausados, descontados do relogio
        self._pausa_em = 0.0
        self.janela = JanelaXP(self, ao_fechar=self.encerrar,
                               ao_zerar=self.zerar, ao_pausar=self.pausar)
        pos = self.cfg.get("xp_overlay_pos") or []
        self.janela.posicionar(*(int(p) for p in pos)) if len(pos) == 2 \
            else self.janela.posicionar(60, 60)

        threading.Thread(target=self._worker, daemon=True).start()
        self._drenar()

    def _calibrar(self) -> bool:
        """Chama o assistente de calibracao da barra, na primeira vez.

        O programa e independente, entao ele mesmo resolve isso — nao da pra
        mandar o usuario abrir o Scanner so pra marcar um retangulo.
        """
        if not messagebox.askyesno(
                "Falta calibrar",
                "A barra de XP ainda nao foi marcada.\n\n"
                "E preciso uma vez so, pra confirmar qual das barras da tela e "
                "a sua; depois disso o valor vem da memoria.\n\n"
                "Abrir o assistente de calibracao agora?"):
            return False
        if getattr(sys, "frozen", False):
            # dentro do .exe nao ha script pra chamar: roda o assistente aqui
            import calibrar
            regioes = calibrar.Assistente(calibrar.PASSOS_XP, "xp").executar()
            if regioes:
                cfg = comum.carregar_config()
                cfg["tela"] = list(comum.tamanho_tela())
                cfg.update(regioes)
                comum.salvar_config(cfg)
        else:
            raiz = Path(__file__).resolve().parent
            subprocess.run([sys.executable, str(raiz / "calibrar.py"),
                            "--modo", "xp"], cwd=str(raiz))
        self.cfg = comum.carregar_config()
        if self.cfg.get("xp_regiao"):
            return True
        messagebox.showinfo("Nao calibrou",
                            "Nada foi marcado. Rode de novo quando quiser.")
        return False

    # -- ciclo ------------------------------------------------------------

    def pausar(self, pausado: bool):
        """Congela a contagem sem parar de ler.

        O tempo em que voce ficou na cidade e DESCONTADO do relogio: sem isso,
        dez minutos vendendo derrubariam o ritmo medio e a estimativa ficaria
        sem sentido quando voce voltasse a farmar.
        """
        self.pausado = pausado
        if pausado:
            self._pausa_em = time.time()
        elif self._pausa_em:
            self.deslocamento += time.time() - self._pausa_em
            self._pausa_em = 0.0

    def zerar(self):
        self.rastreador = motor_xp.Rastreador(
            janela_minutos=float(self.cfg.get("xp_janela_minutos", 15)))
        self.deslocamento = 0.0
        self._pausa_em = 0.0

    def encerrar(self):
        self.parar.set()
        try:
            self.cfg["xp_overlay_pos"] = [self.janela.winfo_x(),
                                          self.janela.winfo_y()]
            comum.salvar_config(self.cfg)
        except Exception:
            pass
        self.destroy()

    def _worker(self):
        """Mesma logica do Scanner: memoria quando da, OCR de reserva."""
        intervalo_ocr = max(2.0, float(self.cfg.get("xp_intervalo", 10)))
        intervalo_mem = max(0.1, float(self.cfg.get("xp_intervalo_memoria", 0.25)))
        leitor = self._ligar_memoria()
        ate_retentar = 0
        conhecido = None
        recusadas = falhas = 0

        while not self.parar.is_set():
            leitura = None
            if leitor is None:
                ate_retentar -= 1
                if ate_retentar <= 0:
                    leitor = self._ligar_memoria()
                    ate_retentar = int(self.cfg.get("xp_retentar_memoria", 30))
            if leitor is not None:
                leitura = leitor.ler()
                if leitura is None:
                    leitor.fechar()
                    leitor = None
                    ate_retentar = int(self.cfg.get("xp_retentar_memoria", 30))
                    self.fila.put(("fonte", "memory link lost — back to OCR"))
            if leitura is None and not self.erro_tesseract:
                try:
                    leitura = motor_xp.ler_barra(
                        capturar_regiao(self.cfg["xp_regiao"]), conhecido)
                except Exception:
                    leitura = None

            if leitura and self.pausado:
                pass          # segue lendo (o nivel continua conferido), mas
                              # nada entra na conta enquanto estiver pausado
            elif leitura:
                falhas = recusadas = 0
                conhecido = leitura["base_nivel"]
                self.rastreador.registrar(leitura, time.time() - self.deslocamento)
                self.fila.put(("xp", leitura))
            else:
                falhas += 1
                if conhecido is not None:
                    recusadas += 1
                    if recusadas >= 5:
                        conhecido = None
                        recusadas = 0
                if falhas in (3, 30):
                    self.fila.put(("erro", falhas))

            intervalo = intervalo_mem if leitor is not None else intervalo_ocr
            fim = time.time() + intervalo
            while time.time() < fim and not self.parar.is_set():
                time.sleep(min(0.1, intervalo))

    def _ligar_memoria(self):
        if (self.cfg.get("xp_fonte") or "auto").lower() == "ocr":
            return None
        if self.erro_tesseract:
            self.fila.put(("fonte", "OCR unavailable — can't confirm the bar"))
            return None
        try:
            referencia = motor_xp.ler_barra(capturar_regiao(self.cfg["xp_regiao"]))
            if not referencia:
                self.fila.put(("fonte", "no screen reading to confirm"))
                return None
            leitor = motor_xp.LeitorMemoria(
                (self.cfg.get("janela_jogo") or "SpiritVale"))
            self.fila.put(("fonte", "locating bars in memory..."))
            if leitor.localizar(referencia):
                self.fila.put(("fonte", "reading from MEMORY (exact)"))
                return leitor
            self.fila.put(("fonte", "not found in memory — using OCR"))
        except Exception as erro:
            self.fila.put(("fonte", f"memory unavailable ({erro})"))
        return None

    # -- interface --------------------------------------------------------

    def _drenar(self):
        try:
            while True:
                tipo, dados = self.fila.get_nowait()
                if tipo == "xp":
                    self._mostrar(dados)
                elif tipo == "erro":
                    self.janela.avisar(
                        "couldn't read the bar",
                        "check the calibration (calibrar.py --modo xp)"
                        " and that the game is visible")
                elif tipo == "fonte":
                    print(dados)          # so no console: o titulo fica limpo
        except queue.Empty:
            pass
        if not self.parar.is_set():
            self.after(100, self._drenar)

    def _mostrar(self, leitura: dict):
        r = self.rastreador
        self.janela.atualizar_bloco("base", leitura["base_nivel"],
                                    leitura["base_pct"], r.eta("base"),
                                    r.taxa("base"))
        self.janela.atualizar_bloco("job", leitura["job_nivel"],
                                    leitura["job_pct"], r.eta("job"),
                                    r.taxa("job"))
        self.janela.detalhe.configure(
            text=f"session  class +{r.ganho_total('base') or 0:.1f}%"
                 f"  ·  job +{r.ganho_total('job') or 0:.1f}%"
                 f"  ·  {motor_xp.formatar_tempo(r.duracao())}")
        self.janela.desenhar(r.historico, r.duracao())


def main() -> None:
    comum.preparar_console()
    ctk.set_appearance_mode("dark")
    try:
        app = XPAnalyzer()
    except SystemExit:
        return
    app.mainloop()


if __name__ == "__main__":
    main()
