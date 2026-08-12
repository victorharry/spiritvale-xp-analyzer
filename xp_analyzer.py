r"""XP Analyzer — sobreposicao de XP, lendo so a rede.

Mostra, numa janelinha arrastavel sobre o jogo, o nivel e o XP de classe e de
job, com ritmo e tempo estimado pro proximo nivel.

    .venv\Scripts\python.exe xp_analyzer.py

Nao ha janela principal: a propria sobreposicao E o programa.

**Nada e lido da memoria do jogo.** Os numeros vem dos pacotes que o servidor
ja manda pra sua maquina (ver captura.py), que trazem nivel e XP absoluto
prontos.

O que o servidor NAO manda e quanto XP o nivel pede — isso vem de tabela_xp.py,
extraida dos arquivos do proprio jogo. Entao nao ha nada a digitar, nada a
calibrar e nada a estimar: os 150 niveis sao exatos.

O aprendizado por level up continua no codigo, mas mudou de papel: em vez de
alimentar o config, ele VIGIA. Se um patch mexer na tabela, a medicao vai
divergir e o app avisa pra rodar extrair_tabela.py de novo.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from tkinter import messagebox, simpledialog

import customtkinter as ctk

import bruto
import captura
import comum
import pcap
import tabela_xp
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

        # "ha captura" nao e o mesmo que "ha Npcap": rodando como administrador
        # o raw socket serve igual. Enquanto isso aqui perguntava so pelo Npcap,
        # desinstalar o driver impedia o monitor de sequer INICIAR — e ai nem
        # elevar adiantava, porque o segundo caminho nunca era tentado.
        self.rede_disponivel = pcap.disponivel() or bruto.disponivel()
        self.monitor = captura.Monitor(
            nome_processo=self.cfg.get("processo_jogo") or captura.NOME_PROCESSO,
            ao_avisar=lambda texto: self.fila.put(("fonte", f"network: {texto}")))
        # inicia sempre: se nao houver caminho nenhum, quem diz isso e o proprio
        # monitor, e a janela mostra o motivo
        self.monitor.iniciar()

        if not self._pedir_niveis():
            self.destroy()
            raise SystemExit(1)

        self.rastreador = motor_xp.Rastreador(
            janela_minutos=float(self.cfg.get("xp_janela_minutos", 15)))

        self.pausado = False
        self.TETO = {"base": 150, "job": 70}   # os maximos do jogo
        # medicoes antigas do usuario, de antes da tabela existir. Ficam como
        # reserva pra um nivel que a tabela nao cubra (ver _previsto)
        self.necessario: dict[str, int] = dict(self.cfg.get("xp_necessario") or {})
        # todas as estimativas ja registradas de cada nivel, pra mediana
        self._historico: dict[str, list[int]] = {
            k: list(v) for k, v in (self.cfg.get("xp_amostras") or {}).items()}
        self._nivel_anterior: dict[str, int] = {}
        self._pico: dict[str, int] = {}
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

    def guardar_zoom(self, escala: float):
        self.cfg["xp_escala"] = escala
        comum.salvar_config(self.cfg)

    def corrigir_nivel(self, qual: str):
        """Clicar no nivel mostra de onde vem o numero daquele bloco.

        Nao ha mais o que corrigir: o nivel vem do servidor e o tamanho dele
        vem da tabela do jogo. Virou uma janelinha de procedencia — util quando
        o valor parecer errado, porque diz na hora se a fonte e a tabela ou uma
        medicao antiga sobrando no config.
        """
        pacote = self.monitor.ultimo
        if pacote is None:
            messagebox.showinfo("XP Analyzer", "No reading from the game yet.")
            return
        nivel = pacote.nivel if qual == "base" else pacote.nivel_job
        xp = pacote.xp if qual == "base" else pacote.xp_job
        oficial = tabela_xp.xp_do_nivel(nivel)
        medido = self.necessario.get(f"{qual}:{nivel}")
        fonte = ("game table" if oficial else
                 "your own measurement" if medido else "unknown")
        total = oficial or medido
        detalhe = (f"{xp:,} of {total:,} XP ({100.0 * xp / total:.2f}%)"
                   if total else "level size unknown")
        rotulo = "CLASS" if qual == "base" else "JOB"
        messagebox.showinfo(
            "XP Analyzer",
            f"{rotulo} level {nivel}\n\n{detalhe}\n\nsource: {fonte}")

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
                if sem_leitura % 6 == 0:
                    # Sem leitura, o unico jeito de o usuario entender o que
                    # esta havendo e ver o estado da captura. Isso so ia pro
                    # print(), e o .exe nao tem console — a janela dizia
                    # "waiting for the game" tanto pra jogo fechado quanto pra
                    # captura que nunca abriu.
                    # a contagem de pacotes e o que separa os dois modos de
                    # falhar: zero = a captura nao esta vendo a rede; muitos =
                    # esta vendo, mas nao achou o personagem nos pacotes
                    self.fila.put(("deteccao",
                                   f"{self.monitor.aviso or self.monitor.estado}"
                                   f"  ·  {self.monitor.pacotes} pkt"))
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
                # A tabela do jogo ja da o valor, entao a medicao nao entra
                # mais como fonte: entra como VIGIA. O pico visto antes da
                # virada nunca passa do que o nivel pedia, e chega perto — se
                # ele passar da tabela, ou ficar muito abaixo, e sinal de que
                # um patch mexeu nos numeros e o extrator precisa rodar.
                esperado = tabela_xp.xp_do_nivel(anterior)
                if esperado and not esperado * 0.90 <= pico <= esperado * 1.01:
                    self.fila.put(("fonte", f"WARNING: level {anterior} measured "
                                            f"{pico:,} XP but the table says "
                                            f"{esperado:,} — run extrair_tabela.py"))
                if not esperado:
                    self.necessario[f"{qual}:{anterior}"] = pico
                    self.cfg["xp_necessario"] = self.necessario
                    comum.salvar_config(self.cfg)
            if nivel != anterior:
                self._pico[qual] = 0
            self._nivel_anterior[qual] = nivel
            self._pico[qual] = max(self._pico.get(qual, 0), xp)

    def _tabela_medida(self) -> dict[int, int]:
        """Todas as medicoes numa tabela so, sem separar classe de job.

        Elas SAO a mesma curva: medidos no mesmo nivel, classe e job batem em
        0,08% (nivel 21: 72.082 x 72.023) e 0,38% (nivel 22). Juntar as duas
        trilhas dobra a densidade da tabela de graca — medir o job do Corujo
        melhora a estimativa da classe do Galinho.
        """
        por_nivel: dict[int, list[int]] = {}
        for chave, valor in self.necessario.items():
            _, _, nivel = chave.partition(":")
            if nivel.isdigit() and valor:
                por_nivel.setdefault(int(nivel), []).append(int(valor))
        # mediana: uma leitura com a porcentagem defasada nao arrasta o nivel
        return {n: sorted(v)[len(v) // 2] for n, v in por_nivel.items()}

    def vao_ate_medicao(self, nivel: int) -> int | None:
        """Quantos niveis separam as duas medicoes que cercam este.

        E a medida honesta de confianca da estimativa: o erro da interpolacao
        e funcao direta desse vao — 0,1% com 2 niveis de distancia, 2% com 40,
        33% com 79. Ver NOTAS-XP.md.
        """
        tabela = self._tabela_medida()
        if nivel in tabela:
            return 0
        abaixo = [n for n in tabela if n < nivel]
        acima = [n for n in tabela if n > nivel]
        if abaixo and acima:
            return min(acima) - max(abaixo)
        return None                      # so tem medicao de um lado: e extrapolacao

    def _previsto(self, qual: str, nivel: int) -> int | None:
        """O tamanho do nivel: da tabela do jogo, ou interpolado se ela faltar.

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
        if nivel < 1:
            return None
        oficial = tabela_xp.xp_do_nivel(nivel)
        if oficial:
            return oficial
        tabela = self._tabela_medida()
        if nivel in tabela:
            return tabela[nivel]
        abaixo = sorted(n for n in tabela if n < nivel)
        acima = sorted(n for n in tabela if n > nivel)
        if abaixo and acima:
            a, b = abaixo[-1], acima[0]
        elif len(abaixo) >= 2:
            a, b = abaixo[-2:]           # extrapolando pra cima
        elif len(acima) >= 2:
            a, b = acima[:2]             # extrapolando pra baixo
        else:
            return None

        try:
            passo = ((math.log(nivel) - math.log(a))
                     / (math.log(b) - math.log(a)))
            registro = (math.log(tabela[a])
                        + passo * (math.log(tabela[b]) - math.log(tabela[a])))
            return int(round(math.exp(registro)))
        except (ValueError, ZeroDivisionError, OverflowError):
            return None

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
                # so e "estimado" se nao veio da tabela do jogo
                estimado = estimado or not tabela_xp.xp_do_nivel(nivel)
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
