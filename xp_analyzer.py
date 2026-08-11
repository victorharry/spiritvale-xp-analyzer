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

import math
import queue
import threading
import time
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
        # Nao ha curva embutida. A estimativa vem de INTERPOLAR entre as
        # medicoes do proprio usuario (ver _previsto): polinomio, lei de
        # potencia, potencia vezes exponencial e potencia por faixas foram
        # todos testados e nenhum chega na precisao das medicoes.
        # quanto XP cada nivel pede — aprendido, nao chutado (ver _aprender_no_level_up)
        self.necessario: dict[str, int] = dict(self.cfg.get("xp_necessario") or {})
        # todas as estimativas ja registradas de cada nivel, pra mediana
        self._historico: dict[str, list[int]] = {
            k: list(v) for k, v in (self.cfg.get("xp_amostras") or {}).items()}
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
            estimativa = int(round(xp / (pct / 100.0)))
            previsto = self._previsto(qual, nivel)
            erro = 100.0 * (previsto - estimativa) / estimativa if previsto else 0.0
            linhas.append(f"{qual}\t{nivel}\t{xp}\t{pct}\t{estimativa}\t"
                          f"{previsto}\t{erro:+.1f}")

            # Guarda TODAS as estimativas do nivel e fica com a mediana, em vez
            # de o ultimo registro virar a verdade. Duas fontes de erro pedem
            # isso: a barra arredonda na primeira decimal, e entre voce ler a
            # porcentagem e clicar o XP ja subiu um pouco (pior ainda em grupo).
            # Uma amostra do nivel 115 saiu 9% acima das outras dez — sozinha,
            # ela substituiria as boas.
            chave = f"{qual}:{nivel}"
            historico = self._historico.setdefault(chave, [])
            historico.append(estimativa)
            del historico[:-25]
            necessario = sorted(historico)[len(historico) // 2]
            self.necessario[chave] = necessario
            self.cfg["xp_amostras"] = self._historico
            resumo.append(f"{qual} {nivel}: {necessario:,} "
                          f"({len(historico)} amostra(s), {erro:+.1f}% vs previsto)")

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
        """O tamanho do nivel, interpolado entre as medicoes que o cercam.

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
