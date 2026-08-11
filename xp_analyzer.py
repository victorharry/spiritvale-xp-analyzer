r"""XP Analyzer — sobreposicao de XP, lendo so a rede.

Mostra, numa janelinha arrastavel sobre o jogo, o nivel e o XP de classe e de
job, com ritmo e tempo estimado pro proximo nivel.

    .venv\Scripts\python.exe xp_analyzer.py

Nao ha janela principal: a propria sobreposicao E o programa.

**Nada e lido da memoria do jogo.** Os numeros vem dos pacotes que o servidor
ja manda pra sua maquina (ver captura.py), que trazem nivel e XP absoluto
prontos. Nao ha o que digitar e nao ha o que adivinhar.

O que o servidor NAO manda e quanto XP o nivel pede. Isso e aprendido quando
voce sobe de nivel: o maior XP visto antes da virada e o que aquele nivel
pedia, com erro de uma morte de mob (0,25% no nivel 114 — ver NOTAS-XP.md).
Ate o primeiro level up nao ha porcentagem nem estimativa de tempo, so nivel,
XP e ritmo. Ficar sem estimativa e melhor que exibir uma inventada.
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

import captura
import comum
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
        self.TETO = {"base": 150, "job": 70}   # os maximos do jogo
        # req(n) = k * n^expoente. UMA curva so: classe e job medidos no mesmo
        # nivel batem em 0,08% (ver NOTAS-XP.md), entao sao a mesma funcao.
        # Ajustada sobre os niveis 16-28, onde erra no maximo 0,65%.
        #
        # FORA dessa faixa e chute. No nivel 114 tres formas que cabem nos dados
        # medidos com <0,7% divergem por 2x entre si — ajuste local nao licencia
        # extrapolacao. Por isso a previsao vem sempre marcada como estimativa
        # e qualquer medicao a substitui.
        self.CURVA = {"base": (3.6993, 3.2434), "job": (3.6993, 3.2434)}
        self.FAIXA_AJUSTADA = (16, 28)
        # quanto XP cada nivel pede — aprendido, nao chutado (ver _aprender_no_level_up)
        self.necessario: dict[str, int] = dict(self.cfg.get("xp_necessario") or {})
        self._nivel_anterior: dict[str, int] = {}
        self._pico: dict[str, int] = {}
        self.deslocamento = 0.0     # segundos pausados, descontados do relogio
        self._pausa_em = 0.0
        self.janela = JanelaXP(self, ao_registrar=self.registrar_amostra,
                               ao_fechar=self.encerrar,
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

    def guardar_zoom(self, escala: float):
        self.cfg["xp_escala"] = escala
        comum.salvar_config(self.cfg)

    def informar_porcentagem(self, qual: str, pct: float, pacote) -> str | None:
        """A conta: XP exato do servidor + porcentagem lida por voce.

        Devolve o texto do aviso, ou None se nao deu pra calcular.

        O `pacote` vem de fora de proposito. A porcentagem que voce le na tela
        vale para o XP daquele instante; se eu buscasse o XP depois da digitacao
        estaria dividindo XP novo por porcentagem velha, e superestimando o
        tamanho do nivel — foi exatamente assim que a medicao do job saiu 10%
        alta no teste (ver NOTAS-XP.md).
        """
        nivel = pacote.nivel if qual == "base" else pacote.nivel_job
        xp = pacote.xp if qual == "base" else pacote.xp_job
        if nivel >= self.TETO.get(qual, 10**9):
            return "That's already the max level — nothing to estimate."
        if xp <= 0:
            return "No XP in this level yet. Gain a little first."
        if not 0 < pct <= 100:
            return None
        chave = f"{qual}:{nivel}"
        self.necessario[chave] = int(round(xp / (pct / 100.0)))
        self.cfg["xp_necessario"] = self.necessario
        comum.salvar_config(self.cfg)
        return (f"Level {nivel} needs about {self.necessario[chave]:,} XP.\n"
                f"({xp:,} XP was {pct}% of it)")

    def registrar_amostra(self, valores: dict) -> str:
        """Painel temporario de calibracao: guarda (nivel, XP, %) e recalcula.

        Grava a amostra CRUA num arquivo, nao so o `necessario` derivado. O
        derivado ja e uma conclusao; se depois a gente quiser reajustar a curva
        com outro criterio, precisa dos ingredientes, nao do bolo pronto.

        O XP e lido AGORA, no clique — a porcentagem que voce acabou de digitar
        vale pro XP deste instante.
        """
        pacote = self.monitor.ultimo
        if pacote is None:
            return "no reading from the game yet"

        linhas, resumo = [], []
        for qual, pct in valores.items():
            nivel = pacote.nivel if qual == "base" else pacote.nivel_job
            xp = pacote.xp if qual == "base" else pacote.xp_job
            if nivel >= self.TETO.get(qual, 10**9) or xp <= 0 or not 0 < pct <= 100:
                continue
            necessario = int(round(xp / (pct / 100.0)))
            previsto = self._previsto(qual, nivel)
            erro = 100.0 * (previsto - necessario) / necessario if previsto else 0.0
            linhas.append(f"{qual}\t{nivel}\t{xp}\t{pct}\t{necessario}\t"
                          f"{previsto}\t{erro:+.1f}")
            self.necessario[f"{qual}:{nivel}"] = necessario
            resumo.append(f"{qual} {nivel}: {necessario:,} ({erro:+.1f}% vs formula)")

        if not linhas:
            return "nothing to record (max level, or no XP yet)"
        with open(comum.RAIZ / "amostras-xp.tsv", "a", encoding="utf-8") as arq:
            for linha in linhas:
                arq.write(linha + "\n")
        self.cfg["xp_necessario"] = self.necessario
        comum.salvar_config(self.cfg)
        return " · ".join(resumo)

    def corrigir_nivel(self, qual: str):
        """Clicou no numero do nivel: pergunta a PORCENTAGEM, nao o nivel.

        O nivel nao se pergunta mais — vem do servidor. O que falta e o tamanho
        do nivel, e ate subir de nivel a unica fonte disso e voce olhando a
        barra do jogo. Ler da sua tela e digitar nao e ler memoria: e voce
        contando o que ve.
        """
        pacote = self.monitor.ultimo
        if pacote is None:
            messagebox.showinfo(
                "XP Analyzer",
                "No reading from the game yet.\n\n"
                "The server only sends your progress when it changes — "
                "gain a little XP and try again.")
            return
        rotulo = "CLASS" if qual == "base" else "JOB"
        nivel = pacote.nivel if qual == "base" else pacote.nivel_job
        pct = simpledialog.askfloat(
            "XP Analyzer",
            f"{rotulo} level {nivel}: what % does the game show?\n\n"
            f"Read it now — the number is matched against the XP as it is "
            f"at this moment.",
            minvalue=0.1, maxvalue=100.0)
        if not pct:
            return
        aviso = self.informar_porcentagem(qual, pct, pacote)
        if aviso:
            messagebox.showinfo("XP Analyzer", aviso)

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
        """So rede. Nada mais e lido da memoria do jogo.

        O servidor entrega nivel e XP absoluto prontos. O que ele nao entrega e
        quanto XP o nivel pede — isso e aprendido quando voce sobe de nivel, e
        ate la nao ha porcentagem nem estimativa de tempo.

        Nao ter estimativa e melhor que inventar uma: a alternativa era adivinhar
        qual dos ~1.700 valores parecidos na memoria e a barra de XP, e uma
        escolha errada ali produz um numero convincente e falso.
        """
        sem_leitura = 0
        while not self.parar.is_set():
            pacote = self.monitor.ultimo
            if pacote is None:
                sem_leitura += 1
                if sem_leitura in (10, 120):
                    self.fila.put(("erro", sem_leitura))
            else:
                sem_leitura = 0
                self._aprender_no_level_up(pacote)
                self._niveis_da_rede(None)
                leitura = self._leitura_da_rede(pacote)
                if leitura is None:
                    # sem o tamanho do nivel nao ha porcentagem, mas o nivel e o
                    # XP existem e tem que aparecer: janela muda e pior que
                    # janela incompleta
                    leitura = {"base_nivel": pacote.nivel, "base_pct": None,
                               "job_nivel": pacote.nivel_job, "job_pct": None}
                elif not self.pausado:
                    self.rastreador.registrar(
                        leitura, time.time() - self.deslocamento)
                self.fila.put(("xp", leitura))

            fim = time.time() + 0.5
            while time.time() < fim and not self.parar.is_set():
                time.sleep(0.1)

    def _resumo_rede(self) -> str:
        """Prefixo pro rodape: prova de vida enquanto a barra nao foi achada."""
        pacote = self.monitor.ultimo
        if pacote is None:
            return ""
        # curto de proposito: o rodape divide espaco com o aviso de calibracao,
        # e texto comprido demais era cortado pela esquerda
        return f"{pacote.nome} · {pacote.xp:,} XP · "

    def _aprender_no_level_up(self, pacote) -> None:
        """Subir de nivel entrega o tamanho do nivel anterior — sem a barra.

        O maior XP visto antes da virada e, na pratica, o que aquele nivel
        pedia: as leituras chegam de poucos em poucos segundos, entao o erro
        fica bem abaixo de 1%.

        E a unica fonte que nao depende de ler a tela. A barra continua util
        so pra NAO ter que esperar um level up pra ter estimativa no nivel em
        que voce ja esta.
        """
        for qual, nivel, xp in (("base", pacote.nivel, pacote.xp),
                                ("job", pacote.nivel_job, pacote.xp_job)):
            anterior = self._nivel_anterior.get(qual)
            pico = self._pico.get(qual, 0)
            if anterior is not None and nivel > anterior and pico > 0:
                chave = f"{qual}:{anterior}"
                self.necessario[chave] = pico
                self.cfg["xp_necessario"] = self.necessario
                comum.salvar_config(self.cfg)
                self.fila.put(("fonte", f"level size from level up: "
                                        f"{chave} = {pico:,} XP"))
            if nivel != anterior:
                self._pico[qual] = 0
            self._nivel_anterior[qual] = nivel
            self._pico[qual] = max(self._pico.get(qual, 0), xp)

    def _previsto(self, qual: str, nivel: int) -> int | None:
        """O tamanho do nivel pela formula, quando ele ainda nao foi medido.

        Ajuste sobre os pontos que o proprio app coletou nos level ups do
        Corujo (classe 17-21, job 12-16), com residuo maximo de 0,7%. Ver
        NOTAS-XP.md.

        ATENCAO: no nivel 114 isso e extrapolacao de 93 niveis a partir de uma
        faixa de 5. Esta aqui pra ser CONFERIDO contra a barra do jogo, nao pra
        ser confiado. Medida sempre ganha de prevista — por isso a formula so
        entra quando nao ha valor aprendido.
        """
        k, expoente = self.CURVA.get(qual, (None, None))
        if k is None or nivel < 1:
            return None
        return int(round(k * nivel ** expoente))

    def _leitura_da_rede(self, pacote) -> dict | None:
        """A leitura no formato da barra, mas com os numeros exatos do servidor.

        O tamanho do nivel vem, nesta ordem: medido (level up ou porcentagem
        digitada) e, faltando isso, previsto pela formula. A ordem importa —
        medida sempre ganha de prevista.
        """
        estimado = False

        def porcento(qual: str, xp: int, nivel: int) -> float | None:
            nonlocal estimado
            if nivel >= self.TETO.get(qual, 10**9):
                return 100.0
            necessario = self.necessario.get(f"{qual}:{nivel}")
            if not necessario:
                necessario = self._previsto(qual, nivel)
                estimado = True
            if not necessario:
                return None
            return max(0.0, min(100.0, 100.0 * xp / necessario))

        base = porcento("base", pacote.xp, pacote.nivel)
        job = porcento("job", pacote.xp_job, pacote.nivel_job)
        if base is None or job is None:
            return None
        return {"base_nivel": pacote.nivel, "base_pct": base,
                "job_nivel": pacote.nivel_job, "job_pct": job,
                "estimado": estimado}

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

    def _drenar(self):
        try:
            while True:
                tipo, dados = self.fila.get_nowait()
                if tipo == "xp":
                    self._mostrar(dados)
                elif tipo == "erro":
                    self.janela.avisar(
                        "waiting for the game",
                        "the server only reports your progress when it "
                        "changes — gain a little XP")
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
        marca = "PAUSED · " if self.pausado else ""
        pacote = self.monitor.ultimo
        if leitura.get("estimado"):
            marca += "formula ~ · "
        if leitura["base_pct"] is None:
            # ainda sem porcentagem: o rodape mostra o que existe de verdade,
            # que e o XP exato do servidor. Curto, senao a janela corta.
            nome = pacote.nome if pacote else "?"
            xp = f"{pacote.xp:,}" if pacote else "?"
            self.janela.detalhe.configure(text=f"{marca}{nome} · {xp} XP")
            return
        exato = f" · {pacote.xp:,} XP" if pacote else ""
        self.janela.detalhe.configure(
            text=marca + f"class +{r.ganho_total('base') or 0:.1f}%"
                 f" · job +{r.ganho_total('job') or 0:.1f}%"
                 f" · {motor_xp.formatar_tempo(r.duracao())}{exato}")
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
