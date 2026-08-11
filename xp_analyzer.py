"""XP Analyzer — aplicativo independente, sem nada do mercado.

Le a barra de XP direto da memoria do jogo e mostra, numa janelinha
arrastavel sobre o jogo, quanto falta pro proximo nivel de classe e de job.

    .venv\\Scripts\\python.exe xp_analyzer.py

Nao ha janela principal: a propria sobreposicao E o programa. Fechar nela
fecha tudo.

Sem OCR e sem dependencia externa: as barras sao identificadas pelo COMPORTA-
MENTO. Entre as ~1.600 barras de UI do jogo, a de XP e a unica que so sobe e
nunca desce, e classe e job sobem juntas quando voce mata algo. HP e MP
oscilam, cast zera, cooldown volta ao cheio — nada disso passa no filtro.

Os numeros dos niveis voce informa uma vez (a barra guarda so o preenchimento);
dai em diante eles sobem sozinhos, detectados pela queda brusca da barra.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

import customtkinter as ctk

import cadeia
import captura
import comum
import memoria
import pcap
import xp as motor_xp
from xp_janela import JanelaXP

# depois disso o XP absoluto sai do rodape, por ser informacao do momento.
# O NIVEL nao expira: leitura velha nao fica errada, porque subir de nivel
# exige ganhar XP e ganhar XP gera leitura nova
VALIDADE_REDE = 300.0


class XPAnalyzer(ctk.CTk):
    """Aplicativo de uma janela so: a sobreposicao."""

    def __init__(self):
        super().__init__()
        self.withdraw()                    # a raiz nunca aparece
        self.cfg = comum.carregar_config()
        comum.ativar_dpi()

        self.fila: queue.Queue = queue.Queue()
        self.parar = threading.Event()

        # o nivel vem dos pacotes do jogo quando da; a memoria so tem o
        # preenchimento da barra, que nao carrega numero nenhum
        self.rede_disponivel = pcap.disponivel()
        self.monitor = captura.Monitor(
            nome_processo=self.cfg.get("processo_jogo") or captura.NOME_PROCESSO,
            ao_avisar=lambda texto: self.fila.put(("fonte", f"network: {texto}")))
        if self.rede_disponivel:
            self.monitor.iniciar()

        if not self._pedir_niveis():
            self.destroy()
            raise SystemExit(1)

        self.rastreador = motor_xp.Rastreador(
            janela_minutos=float(self.cfg.get("xp_janela_minutos", 15)))

        self.pausado = False
        self.leitor = None
        self.deslocamento = 0.0     # segundos pausados, descontados do relogio
        self._pausa_em = 0.0
        self.janela = JanelaXP(self, ao_fechar=self.encerrar,
                               ao_zerar=self.zerar, ao_pausar=self.pausar,
                               ao_corrigir_nivel=self.corrigir_nivel,
                               ao_zoom=self.guardar_zoom,
                               escala=float(self.cfg.get('xp_escala', 1.0)))
        pos = self.cfg.get("xp_overlay_pos") or []
        self.janela.posicionar(*(int(p) for p in pos)) if len(pos) == 2 \
            else self.janela.posicionar(60, 60)

        threading.Thread(target=self._worker, daemon=True).start()
        self._drenar()

    def _pedir_niveis(self) -> bool:
        """Ultimo recurso: perguntar o nivel.

        So acontece quando a captura de rede nao esta disponivel. Com ela, o
        servidor manda nivel e XP absolutos e nao ha nada pra perguntar — que
        era o incomodo: a barra guarda so o preenchimento, nunca o numero.
        """
        if self.rede_disponivel:
            return True
        if self.cfg.get("xp_nivel_base") and self.cfg.get("xp_nivel_job"):
            return True
        base = simpledialog.askinteger(
            "XP Analyzer", "What's your CLASS level right now?",
            minvalue=1, maxvalue=999)
        if not base:
            return False
        job = simpledialog.askinteger(
            "XP Analyzer", "And your JOB level?", minvalue=1, maxvalue=999)
        if not job:
            return False
        self.cfg["xp_nivel_base"], self.cfg["xp_nivel_job"] = base, job
        comum.salvar_config(self.cfg)
        return True

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

    def guardar_zoom(self, escala: float):
        self.cfg["xp_escala"] = escala
        comum.salvar_config(self.cfg)

    def corrigir_nivel(self, qual: str):
        """Clicou no numero do nivel: deixa acertar sem editar o config."""
        chave = "xp_nivel_base" if qual == "base" else "xp_nivel_job"
        rotulo = "CLASS" if qual == "base" else "JOB"
        novo = simpledialog.askinteger(
            "XP Analyzer", f"{rotulo} level:", minvalue=1, maxvalue=999,
            initialvalue=self.cfg.get(chave) or 1)
        if not novo:
            return
        self.cfg[chave] = novo
        comum.salvar_config(self.cfg)
        if self.leitor is not None:
            self.leitor.definir_niveis(self.cfg.get("xp_nivel_base") or 1,
                                       self.cfg.get("xp_nivel_job") or 1)

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
        self.monitor.parar()
        try:
            self.cfg["xp_overlay_pos"] = [self.janela.winfo_x(),
                                          self.janela.winfo_y()]
            comum.salvar_config(self.cfg)
        except Exception:
            pass
        self.destroy()

    def _worker(self):
        """Mesma logica do Scanner: memoria quando da, OCR de reserva."""
        intervalo_mem = max(0.1, float(self.cfg.get("xp_intervalo_memoria", 0.25)))
        leitor = self._ligar_memoria()
        ate_retentar = 0
        conhecido = None
        recusadas = falhas = 0

        while not self.parar.is_set():
            leitura = None
            rede_manda = self._niveis_da_rede(leitor)
            if leitor is None:
                ate_retentar -= 1
                if ate_retentar <= 0:
                    leitor = self._ligar_memoria()
                    ate_retentar = int(self.cfg.get("xp_retentar_memoria", 30))
            self.leitor = leitor
            if leitor is not None:
                leitura = leitor.ler()
                # par errado costuma ficar cravado em 0% e nunca andar: depois
                # de um tempo assim, e melhor procurar de novo do que insistir
                if leitura and leitura["base_pct"] == 0.0 and leitura["job_pct"] == 0.0:
                    zerados = getattr(self, "_zerados", 0) + 1
                    self._zerados = zerados
                    if zerados > 120:      # ~30s a 4 leituras por segundo
                        self._zerados = 0
                        leitura = None
                else:
                    self._zerados = 0
                if leitura is None:
                    leitor.fechar()
                    leitor = None
                    ate_retentar = int(self.cfg.get("xp_retentar_memoria", 30))
                    self.fila.put(("fonte", "memory link lost — back to OCR"))

            if leitura and self.pausado:
                pass          # segue lendo (o nivel continua conferido), mas
                              # nada entra na conta enquanto estiver pausado
            elif leitura:
                falhas = recusadas = 0
                conhecido = leitura["base_nivel"]
                self.rastreador.registrar(leitura, time.time() - self.deslocamento)
                # com a rede viva, o nivel dela e o certo: a barra so DEDUZ o
                # level up por uma queda brusca, e deduzir erra
                if rede_manda:
                    pass
                elif (leitura["base_nivel"] != self.cfg.get("xp_nivel_base")
                        or leitura["job_nivel"] != self.cfg.get("xp_nivel_job")):
                    self.cfg["xp_nivel_base"] = leitura["base_nivel"]
                    self.cfg["xp_nivel_job"] = leitura["job_nivel"]
                    comum.salvar_config(self.cfg)   # sobreviveu ao level up
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

            intervalo = intervalo_mem if leitor is not None else 5.0
            fim = time.time() + intervalo
            while time.time() < fim and not self.parar.is_set():
                time.sleep(min(0.1, intervalo))

    def _niveis_da_rede(self, leitor) -> bool:
        """Aplica o nivel que veio dos pacotes. Diz se a rede esta mandando.

        O servidor entrega nivel e XP absolutos prontos; nao ha estimativa nem
        nada pro usuario digitar. Enquanto isso estiver chegando, o palpite da
        barra sobre level up nao vale.
        """
        pacote = self.monitor.ultimo
        if pacote is None:
            return False
        mudou = (pacote.nivel != self.cfg.get("xp_nivel_base")
                 or pacote.nivel_job != self.cfg.get("xp_nivel_job"))
        if mudou:
            self.cfg["xp_nivel_base"] = pacote.nivel
            self.cfg["xp_nivel_job"] = pacote.nivel_job
            comum.salvar_config(self.cfg)
            self.fila.put(("fonte", f"network: {pacote.nome} — class "
                                    f"{pacote.nivel}, job {pacote.nivel_job}"))
        if leitor is not None and mudou:
            leitor.definir_niveis(pacote.nivel, pacote.nivel_job)
        return True

    def _tentar_cadeia(self):
        """Caminho gravado: resolve na hora, sem varrer e sem esperar XP."""
        dados = cadeia.carregar(comum.RAIZ)
        caminhos = dados.get("caminhos") or []
        if not caminhos:
            return None
        try:
            pid = memoria.achar_processo(self.cfg.get("janela_jogo") or "SpiritVale")
            if not pid:
                return None
            proc = memoria.Processo(pid)
            for c in caminhos:
                base = cadeia.resolver(proc, c)
                job = cadeia.resolver(proc, c["par"]) if c.get("par") else None
                if base is None or job is None:
                    continue
                b, j = proc.ler_float(base), proc.ler_float(job)
                if b is None or j is None or not (0 <= b <= 1 and 0 <= j <= 1):
                    continue
                leitor = motor_xp.LeitorMemoria(
                    self.cfg.get("janela_jogo") or "SpiritVale")
                leitor.proc, leitor.base, leitor.job = proc, base, job
                leitor.definir_niveis(self.cfg.get("xp_nivel_base") or 1,
                                      self.cfg.get("xp_nivel_job") or 1)
                self.fila.put(("fonte", "found via saved pointer chain (instant)"))
                return leitor
            proc.fechar()
        except Exception:
            pass
        return None

    def _aprender_cadeia(self, leitor):
        """Grava/refina o caminho ate as barras.

        A primeira varredura devolve milhares de caminhos, quase todos
        coincidencia desta sessao. Nas aberturas seguintes eles sao FILTRADOS
        contra o endereco novo — e o que sobrevive a dois ou tres reinicios e
        estavel de verdade.
        """
        try:
            dados = cadeia.carregar(comum.RAIZ)
            antigos = dados.get("caminhos") or []
            if antigos:
                bons = []
                for c in antigos:
                    if (cadeia.resolver(leitor.proc, c) == leitor.base
                            and c.get("par")
                            and cadeia.resolver(leitor.proc, c["par"]) == leitor.job):
                        bons.append(c)
                dados["caminhos"] = bons[:200]
                dados["confirmacoes"] = int(dados.get("confirmacoes", 0)) + 1
                cadeia.salvar(comum.RAIZ, dados)
                self.fila.put(("fonte", f"pointer chain: {len(bons)} path(s) "
                                        f"survived {dados['confirmacoes']} restart(s)"))
                if bons:
                    return
            self.fila.put(("fonte", "mapping pointer chain (once)..."))
            base = cadeia.varrer(leitor.proc, leitor.base, aviso=lambda t: None)
            job = cadeia.varrer(leitor.proc, leitor.job, aviso=lambda t: None)
            juntos = []
            for a, b in zip(base[:200], job[:200]):
                a = dict(a); a["par"] = b
                juntos.append(a)
            cadeia.salvar(comum.RAIZ, {"caminhos": juntos, "confirmacoes": 0})
            self.fila.put(("fonte", f"pointer chain: {len(juntos)} candidate(s) "
                                    "— reopen the game to refine"))
        except Exception as erro:
            self.fila.put(("fonte", f"pointer chain failed ({erro})"))

    def _ligar_memoria(self):
        atalho = self._tentar_cadeia()
        if atalho is not None:
            return atalho
        """Acha as barras SEM OCR, so pelo comportamento delas.

        Nao ha mais dependencia de Tesseract: XP e a unica barra que so sobe,
        e as duas sobem juntas. Basta voce estar farmando enquanto ele mede.
        """
        try:
            leitor = motor_xp.LeitorMemoria(
                (self.cfg.get("janela_jogo") or "SpiritVale"))
            self.fila.put(("fonte", "detecting XP bars — keep farming..."))
            achou = leitor.localizar_por_comportamento(
                segundos=float(self.cfg.get("xp_deteccao_segundos", 40)),
                aviso=lambda n: self.fila.put(
                    ("deteccao", f"detecting… {n} candidates left")))
            if achou:
                self._aprender_cadeia(leitor)
                leitor.definir_niveis(self.cfg.get("xp_nivel_base") or 1,
                                      self.cfg.get("xp_nivel_job") or 1)
                self.fila.put(("fonte", "reading from MEMORY (exact)"))
                return leitor
            self.fila.put(("fonte", "couldn't identify the bars — retrying"))
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
                        "looking for the XP bars",
                        "keep playing and gaining XP for a few "
                        "seconds so they can be identified")
                elif tipo == "deteccao":
                    self.janela.detalhe.configure(text=dados)
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
        marca = "PAUSED  ·  " if self.pausado else ""
        # quando a rede esta viva, o XP absoluto e informacao que a barra nunca
        # teve — vale mostrar
        pacote = self.monitor.ultimo
        exato = ""
        if pacote is not None and self.monitor.idade <= VALIDADE_REDE:
            exato = f"  ·  {pacote.xp:,} XP"
        self.janela.detalhe.configure(
            text=marca + f"session  class +{r.ganho_total('base') or 0:.1f}%"
                 f"  ·  job +{r.ganho_total('job') or 0:.1f}%"
                 f"  ·  {motor_xp.formatar_tempo(r.duracao())}{exato}")
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
