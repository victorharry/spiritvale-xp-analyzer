r"""XP Analyzer — sobreposicao de XP, lendo so a rede.

Mostra, numa janelinha arrastavel sobre o jogo, o level e o XP de classe e de
job, com ritmo e tempo estimado pro next_packet level.

    .venv\Scripts\python.exe xp_analyzer.py

Nao ha janela principal: a propria sobreposicao E o program.

**Nada e lido da memoria do jogo.** Os numeros vem dos packets que o servidor
ja manda pra sua maquina (ver capture.py), que trazem level e XP absoluto
prontos.

O que o servidor NAO manda e quanto XP o level pede — isso vem de xp_table.py,
extraida dos arquivos do proprio jogo. Entao nao ha nada a digitar, nada a
calibrar e nada a estimar: os 150 niveis sao exatos.

O aprendizado por level up continua no code, mas mudou de papel: em vez de
feed o config, ele VIGIA. Se um patch mexer na tabela, a medicao vai
divergir e o app avisa pra rodar extrair_tabela.py de novo.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from tkinter import messagebox, simpledialog

import customtkinter as ctk

import rawsocket
import capture
import settings
import pcap
import updates
import xp_table
import xp as motor_xp
from window import Overlay

# depois disso o XP absoluto sai do rodape, por ser informacao do momento.
# O NIVEL nao expira: reading velha nao fica errada, porque subir de level
# exige ganhar XP e ganhar XP gera reading nova
VALIDADE_REDE = 300.0


class XPAnalyzer(ctk.CTk):
    """Aplicativo de uma janela so: a sobreposicao."""

    def __init__(self):
        super().__init__()
        self.withdraw()                    # a raiz nunca aparece
        self.cfg = settings.load()
        settings.enable_dpi_awareness()

        self.fila: queue.Queue = queue.Queue()
        self.stop = threading.Event()

        # "ha capture" nao e o mesmo que "ha Npcap": rodando como administrador
        # o raw socket serve igual. Enquanto isso aqui perguntava so pelo Npcap,
        # desinstalar o driver impedia o monitor de sequer INICIAR — e ai nem
        # elevar adiantava, porque o segundo caminho nunca era tentado.
        self.rede_disponivel = pcap.available() or rawsocket.available()
        self.monitor = capture.Monitor(
            process_name=self.cfg.get("processo_jogo") or capture.PROCESS_NAME,
            ao_avisar=lambda text: self.fila.put(("fonte", f"network: {text}")))
        # inicia sempre: se nao houver caminho nenhum, quem diz isso e o proprio
        # monitor, e a janela mostra o motivo
        self.monitor.start()

        if not self._pedir_niveis():
            self.destroy()
            raise SystemExit(1)

        self.rastreador = motor_xp.Tracker(
            window_minutes=float(self.cfg.get("xp_janela_minutos", 15)))

        self.pausado = False
        self.TETO = {"base": 150, "job": 70}   # os maximos do jogo
        # medicoes antigas do usuario, de antes da tabela existir. Ficam como
        # reserva pra um level que a tabela nao cubra (ver _previsto)
        self.necessario: dict[str, int] = dict(self.cfg.get("xp_necessario") or {})
        # todas as estimativas ja registradas de cada level, pra mediana
        self._historico: dict[str, list[int]] = {
            k: list(v) for k, v in (self.cfg.get("xp_amostras") or {}).items()}
        self._nivel_anterior: dict[str, int] = {}
        self._pico: dict[str, int] = {}
        self.shift = 0.0     # seconds pausados, descontados do relogio
        self._pausa_em = 0.0
        self.janela = Overlay(self, ao_fechar=self.encerrar,
                               ao_zerar=self.zerar, ao_pausar=self.pausar,
                               ao_corrigir_nivel=self.corrigir_nivel,
                               ao_zoom=self.guardar_zoom,
                               escala=float(self.cfg.get('xp_escala', 1.0)))
        pos = self.cfg.get("xp_overlay_pos") or []
        self.janela.posicionar(*(int(p) for p in pos)) if len(pos) == 2 \
            else self.janela.posicionar(60, 60)

        threading.Thread(target=self._worker, daemon=True).start()
        self._checar_atualizacao()
        self._drenar()

    def _checar_atualizacao(self) -> None:
        """Pergunta ao GitHub se saiu versao nova, sem segurar a abertura.

        Vai pela fila como todo o resto: o resultado chega numa thread de rede
        e mexer em widget fora da thread da interface trava o Tk em casos que
        so aparecem na maquina dos outros.
        """
        if not self.cfg.get("update_check", True):
            return
        updates.check_in_background(
            lambda release: self.fila.put(("atualizacao", release)),
            skipped=str(self.cfg.get("update_skipped") or ""))

    def _ignorar_atualizacao(self, version: str) -> None:
        """Fechar o aviso significa 'nao me mostre ESTA versao de novo'."""
        self.cfg["update_skipped"] = version
        settings.save(self.cfg)

    def _pedir_niveis(self) -> bool:
        """Ultimo recurso: perguntar o level.

        So acontece quando a capture de rede nao esta available. Com ela, o
        servidor manda level e XP absolutos e nao ha nada pra perguntar — que
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
        settings.save(self.cfg)
        return True

    def guardar_zoom(self, escala: float):
        self.cfg["xp_escala"] = escala
        settings.save(self.cfg)

    def corrigir_nivel(self, qual: str):
        """Clicar no level mostra de onde vem o numero daquele bloco.

        Nao ha mais o que corrigir: o level vem do servidor e o size dele
        vem da tabela do jogo. Virou uma janelinha de procedencia — util quando
        o valor parecer errado, porque diz na hora se a fonte e a tabela ou uma
        medicao antiga sobrando no config.
        """
        packet = self.monitor.latest
        if packet is None:
            messagebox.showinfo("XP Analyzer", "No reading from the game yet.")
            return
        level = packet.level if qual == "base" else packet.job_level
        xp = packet.xp if qual == "base" else packet.job_xp
        oficial = xp_table.xp_for_level(level)
        medido = self.necessario.get(f"{qual}:{level}")
        fonte = ("game table" if oficial else
                 "your own measurement" if medido else "unknown")
        total = oficial or medido
        detalhe = (f"{xp:,} of {total:,} XP ({100.0 * xp / total:.2f}%)"
                   if total else "level size unknown")
        label = "CLASS" if qual == "base" else "JOB"
        messagebox.showinfo(
            "XP Analyzer",
            f"{label} level {level}\n\n{detalhe}\n\nsource: {fonte}")

    def pausar(self, pausado: bool):
        """Congela a tally sem stop de ler.

        O tempo em que voce ficou na cidade e DESCONTADO do relogio: sem isso,
        dez minutes vendendo derrubariam o ritmo medio e a estimativa ficaria
        sem sentido quando voce voltasse a farmar.
        """
        self.pausado = pausado
        if pausado:
            self._pausa_em = time.time()
        elif self._pausa_em:
            self.shift += time.time() - self._pausa_em
            self._pausa_em = 0.0

    def zerar(self):
        self.rastreador = motor_xp.Tracker(
            window_minutes=float(self.cfg.get("xp_janela_minutos", 15)))
        self.shift = 0.0
        self._pausa_em = 0.0

    def encerrar(self):
        self.stop.set()
        self.monitor.stop()
        try:
            self.cfg["xp_overlay_pos"] = [self.janela.winfo_x(),
                                          self.janela.winfo_y()]
            settings.save(self.cfg)
        except Exception:
            pass
        self.destroy()

    def _worker(self):
        """So rede. Nada mais e lido da memoria do jogo.

        O servidor entrega level e XP absoluto prontos. O que ele nao entrega e
        quanto XP o level pede — isso e aprendido quando voce sobe de level, e
        ate la nao ha porcentagem nem estimativa de tempo.

        Nao ter estimativa e melhor que inventar uma: a alternativa era adivinhar
        qual dos ~1.700 valores parecidos na memoria e a barra de XP, e uma
        escolha errada ali produz um numero convincente e falso.
        """
        sem_leitura = 0
        while not self.stop.is_set():
            packet = self.monitor.latest
            if packet is None:
                sem_leitura += 1
                if sem_leitura % 6 == 0:
                    self.fila.put(("espera", self._convite()))
                if sem_leitura in (10, 120):
                    self.fila.put(("erro", sem_leitura))
            else:
                sem_leitura = 0
                self._aprender_no_level_up(packet)
                self._niveis_da_rede(None)
                reading = self._leitura_da_rede(packet)
                if reading is None:
                    # sem o size do level nao ha porcentagem, mas o level e o
                    # XP existem e tem que aparecer: janela muda e pior que
                    # janela incompleta
                    reading = {"base_nivel": packet.level, "base_pct": None,
                               "job_nivel": packet.job_level, "job_pct": None}
                elif not self.pausado:
                    self.rastreador.record(
                        reading, time.time() - self.shift)
                self.fila.put(("xp", reading))

            end = time.time() + 0.5
            while time.time() < end and not self.stop.is_set():
                time.sleep(0.1)

    def _convite(self) -> tuple[str, str]:
        """(titulo, explicacao) da tela de espera, conforme o que falta.

        Sao tres situacoes bem diferentes e o usuario nao tem como distinguir
        sozinho — a mesma janela vazia servia pra todas. Nada aqui fala de
        packet, capture ou driver: cada text diz o que a PESSOA faz agora.
        """
        if self.monitor.state in ("sem capture", "falhou"):
            return ("Can't read the game",
                    "Close the XP Analyzer and open it again with "
                    "\"Run as administrator\".")
        if not self.monitor.packets:
            return ("Waiting for the game",
                    "Open SpiritVale and log into a character — "
                    "I'll pick it up from there.")
        return ("Go kill something",
                "I'll start tracking as soon as you gain XP.")

    def _resumo_rede(self) -> str:
        """Prefixo pro rodape: prova de vida enquanto a barra nao foi achada."""
        packet = self.monitor.latest
        if packet is None:
            return ""
        # curto de proposito: o rodape divide espaco com o notice de calibracao,
        # e text comprido demais era cortado pela esquerda
        return f"{packet.name} · {packet.xp:,} XP · "

    def _aprender_no_level_up(self, packet) -> None:
        """Subir de level entrega o size do level anterior — sem a barra.

        O maior XP visto antes da virada e, na pratica, o que aquele level
        pedia: as leituras chegam de poucos em poucos seconds, entao o erro
        fica bem abaixo de 1%.

        E a unica fonte que nao depende de ler a tela. A barra continua util
        so pra NAO ter que esperar um level up pra ter estimativa no level em
        que voce ja esta.
        """
        for qual, level, xp in (("base", packet.level, packet.xp),
                                ("job", packet.job_level, packet.job_xp)):
            anterior = self._nivel_anterior.get(qual)
            pico = self._pico.get(qual, 0)
            if anterior is not None and level > anterior and pico > 0:
                # A tabela do jogo ja da o valor, entao a medicao nao entra
                # mais como fonte: entra como VIGIA. O pico visto antes da
                # virada nunca passa do que o level pedia, e chega perto — se
                # ele passar da tabela, ou ficar muito abaixo, e sinal de que
                # um patch mexeu nos numeros e o extrator precisa rodar.
                esperado = xp_table.xp_for_level(anterior)
                if esperado and not esperado * 0.90 <= pico <= esperado * 1.01:
                    self.fila.put(("fonte", f"WARNING: level {anterior} measured "
                                            f"{pico:,} XP but the table says "
                                            f"{esperado:,} — run extrair_tabela.py"))
                if not esperado:
                    self.necessario[f"{qual}:{anterior}"] = pico
                    self.cfg["xp_necessario"] = self.necessario
                    settings.save(self.cfg)
            if level != anterior:
                self._pico[qual] = 0
            self._nivel_anterior[qual] = level
            self._pico[qual] = max(self._pico.get(qual, 0), xp)

    def _tabela_medida(self) -> dict[int, int]:
        """Todas as medicoes numa tabela so, sem separar classe de job.

        Elas SAO a mesma curva: medidos no mesmo level, classe e job batem em
        0,08% (level 21: 72.082 x 72.023) e 0,38% (level 22). Juntar as duas
        trilhas dobra a densidade da tabela de graca — medir o job do Corujo
        melhora a estimativa da classe do Galinho.
        """
        por_nivel: dict[int, list[int]] = {}
        for key, valor in self.necessario.items():
            _, _, level = key.partition(":")
            if level.isdigit() and valor:
                por_nivel.setdefault(int(level), []).append(int(valor))
        # mediana: uma reading com a porcentagem defasada nao arrasta o level
        return {n: sorted(v)[len(v) // 2] for n, v in por_nivel.items()}

    def vao_ate_medicao(self, level: int) -> int | None:
        """Quantos niveis separam as duas medicoes que cercam este.

        E a medida honesta de confianca da estimativa: o erro da interpolacao
        e funcao direta desse vao — 0,1% com 2 niveis de distancia, 2% com 40,
        33% com 79. Ver NOTAS-XP.md.
        """
        tabela = self._tabela_medida()
        if level in tabela:
            return 0
        abaixo = [n for n in tabela if n < level]
        acima = [n for n in tabela if n > level]
        if abaixo and acima:
            return min(acima) - max(abaixo)
        return None                      # so tem medicao de um lado: e extrapolacao

    def _previsto(self, qual: str, level: int) -> int | None:
        """O size do level: da tabela do jogo, ou interpolado se ela faltar.

        A tabela veio dos arquivos do proprio jogo e confere com as 18 medicoes
        independentes registradas — entao ela nao e estimativa, e o valor. Vem
        na frente de tudo. A interpolacao ficou como rede de seguranca para um
        patch que mude a tabela e a deixe fora de alcance.

        Nao ha formula global aqui, e isso e uma conclusao, nao preguica:
        polinomio, lei de potencia, potencia vezes exponencial e potencia por
        faixas foram todos testados contra as medicoes e nenhum chega perto da
        precisao delas (o melhor errava 1,6%, contra barras de 0,05%). O
        expoente local nem sequer e monotono — 3,25 entre os niveis 16 e 26,
        3,55 ate o 71, 5,42 entre o 114 e o 115. Parece tabela, nao formula.

        Interpolar em log-log entre os vizinhos medidos, por outro lado, erra
        0,1% quando eles estao a 2 niveis e 2% quando estao a 40. E melhora
        sozinho: cada medicao sua encurta algum vao. Ver NOTAS-XP.md.
        """
        if level < 1:
            return None
        oficial = xp_table.xp_for_level(level)
        if oficial:
            return oficial
        tabela = self._tabela_medida()
        if level in tabela:
            return tabela[level]
        abaixo = sorted(n for n in tabela if n < level)
        acima = sorted(n for n in tabela if n > level)
        if abaixo and acima:
            a, b = abaixo[-1], acima[0]
        elif len(abaixo) >= 2:
            a, b = abaixo[-2:]           # extrapolando pra cima
        elif len(acima) >= 2:
            a, b = acima[:2]             # extrapolando pra baixo
        else:
            return None

        try:
            passo = ((math.log(level) - math.log(a))
                     / (math.log(b) - math.log(a)))
            registro = (math.log(tabela[a])
                        + passo * (math.log(tabela[b]) - math.log(tabela[a])))
            return int(round(math.exp(registro)))
        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    def _leitura_da_rede(self, packet) -> dict | None:
        """A reading no formato da barra, mas com os numeros exatos do servidor.

        O size do level vem, nesta ordem: medido (level up ou porcentagem
        digitada) e, faltando isso, previsto pela formula. A ordem importa —
        medida sempre ganha de prevista.
        """
        estimado = False

        def porcento(qual: str, xp: int, level: int) -> float | None:
            nonlocal estimado
            if level >= self.TETO.get(qual, 10**9):
                return 100.0
            necessario = self.necessario.get(f"{qual}:{level}")
            if not necessario:
                necessario = self._previsto(qual, level)
                # so e "estimado" se nao veio da tabela do jogo
                estimado = estimado or not xp_table.xp_for_level(level)
            if not necessario:
                return None
            return max(0.0, min(100.0, 100.0 * xp / necessario))

        base = porcento("base", packet.xp, packet.level)
        job = porcento("job", packet.job_xp, packet.job_level)
        if base is None or job is None:
            return None
        return {"base_nivel": packet.level, "base_pct": base,
                "job_nivel": packet.job_level, "job_pct": job,
                "estimado": estimado}

    def _niveis_da_rede(self, reader) -> bool:
        """Aplica o level que veio dos packets. Diz se a rede esta mandando.

        O servidor entrega level e XP absolutos prontos; nao ha estimativa nem
        nada pro usuario digitar. Enquanto isso estiver chegando, o palpite da
        barra sobre level up nao vale.
        """
        packet = self.monitor.latest
        if packet is None:
            return False
        mudou = (packet.level != self.cfg.get("xp_nivel_base")
                 or packet.job_level != self.cfg.get("xp_nivel_job"))
        if mudou:
            self.cfg["xp_nivel_base"] = packet.level
            self.cfg["xp_nivel_job"] = packet.job_level
            settings.save(self.cfg)
            self.fila.put(("fonte", f"network: {packet.name} — class "
                                    f"{packet.level}, job {packet.job_level}"))
        if reader is not None and mudou:
            reader.definir_niveis(packet.level, packet.job_level)
        return True

    def _drenar(self):
        try:
            while True:
                kind, data = self.fila.get_nowait()
                if kind == "xp":
                    self._mostrar(data)
                elif kind == "erro":
                    self.janela.avisar(
                        "waiting for the game",
                        "open the game and gain a little XP — your progress "
                        "only arrives when it changes")
                elif kind == "espera":
                    self.janela.esperando(*data)
                elif kind == "deteccao":
                    self.janela.rodape(data)
                elif kind == "atualizacao":
                    self.janela.mostrar_atualizacao(
                        data.version, data.url,
                        ao_dispensar=self._ignorar_atualizacao)
                elif kind == "fonte":
                    print(data)          # so no console: o titulo fica limpo
        except queue.Empty:
            pass
        if not self.stop.is_set():
            self.after(100, self._drenar)

    def _mostrar(self, reading: dict):
        r = self.rastreador
        self.janela.atualizar_bloco("base", reading["base_nivel"],
                                    reading["base_pct"], r.eta("base"),
                                    r.rate("base"))
        self.janela.atualizar_bloco("job", reading["job_nivel"],
                                    reading["job_pct"], r.eta("job"),
                                    r.rate("job"))
        # chegou no end do jogo: o rodape para de falar de ritmo e comemora,
        # porque nao ha mais next_packet level pra medir
        if self.janela.tudo_no_maximo:
            self.janela.rodape("🏆  class 150 and job 70 — you've maxed "
                               "everything there is")
            return

        marca = "PAUSED · " if self.pausado else ""
        packet = self.monitor.latest
        if reading.get("estimado"):
            marca += "formula ~ · "
        if reading["base_pct"] is None:
            # ainda sem porcentagem: o rodape mostra o que existe de verdade,
            # que e o XP exato do servidor. Curto, senao a janela corta.
            name = packet.name if packet else "?"
            xp = f"{packet.xp:,}" if packet else "?"
            self.janela.rodape(f"{marca}{name} · {xp} XP")
            return
        exato = f" · {packet.xp:,} XP" if packet else ""
        self.janela.rodape(
            marca + f"class +{r.total_gain('base') or 0:.1f}%"
                 f" · job +{r.total_gain('job') or 0:.1f}%"
                 f" · {motor_xp.format_time(r.elapsed())}{exato}")
        self.janela.desenhar(r.history, r.elapsed())


def main() -> None:
    settings.prepare_console()
    # before anything else: it is what lets the installer notice this copy is
    # running and ask for it to be closed, instead of dying on a locked DLL
    settings.announce_running()
    ctk.set_appearance_mode("dark")
    try:
        app = XPAnalyzer()
    except SystemExit:
        return
    app.mainloop()


if __name__ == "__main__":
    main()
