"""Janela do XP Analyzer — usada pelo app independente e pelo Scanner.

Fica fora do app do mercado de proposito: o medidor de XP nao tem nada a ver
com compra e venda, e assim os dois podem evoluir sem se atrapalhar.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

import xp as motor_xp

# mesma paleta do Scanner, pra os dois programas parecerem a mesma familia
CARTAO = "#171b24"
CARTAO2 = "#1d2230"
BORDA = "#262c3a"
ACENTO = "#3b82f6"
VERDE = "#22c55e"
LARANJA = "#f59e0b"
TEXTO = "#e6eaf2"
TEXTO_SUB = "#8b93a7"
FONTE = "Segoe UI"


def _mistura(fundo: str, frente: str, quanto: float) -> str:
    """Cor entre duas, em hex. `quanto`=0 devolve o fundo, 1 devolve a frente."""
    a = tuple(int(fundo[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(frente[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * quanto) for x, y in zip(a, b))


class JanelaXP(ctk.CTkToplevel):
    """Sobreposicao sem borda, sempre no topo, que voce arrasta pra onde quiser.

    Mostra o ritmo de XP e quanto falta pro proximo nivel. Fica pequena de
    proposito: ela e capturada junto com a tela, entao se cobrir a lista de
    ofertas ou a propria barra de XP, atrapalha o OCR do resto do programa.
    """

    def __init__(self, pai, ao_fechar=None, ao_zerar=None, ao_pausar=None,
                 ao_corrigir_nivel=None, ao_zoom=None, escala=1.0):
        super().__init__(pai, fg_color=CARTAO)
        self.ao_fechar = ao_fechar
        self.ao_zerar = ao_zerar
        self.ao_pausar = ao_pausar
        self.ao_corrigir_nivel = ao_corrigir_nivel
        self.ao_zoom = ao_zoom
        self.escala_ui = float(escala)
        ctk.set_widget_scaling(self.escala_ui)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", self.ALPHA)
        self.resizable(False, False)

        corpo = ctk.CTkFrame(self, fg_color=CARTAO, corner_radius=12)
        corpo.pack(fill="both", expand=True, padx=1, pady=1)

        topo = ctk.CTkFrame(corpo, fg_color="transparent")
        topo.pack(fill="x", padx=16, pady=(10, 0))
        self.titulo = ctk.CTkLabel(topo, text="XP Analyzer", font=(FONTE, 14, "bold"),
                                   text_color=TEXTO_SUB)
        self.titulo.pack(side="left")
        ctk.CTkButton(topo, text="✕", width=26, height=26, fg_color="transparent",
                      hover_color=BORDA, text_color=TEXTO_SUB,
                      font=(FONTE, 15), command=self._fechar).pack(side="right")
        ctk.CTkButton(topo, text="⟳", width=26, height=26, fg_color="transparent",
                      hover_color=BORDA, text_color=TEXTO_SUB, font=(FONTE, 15),
                      command=self._zerar).pack(side="right", padx=(0, 2))
        self.botao_compacto = ctk.CTkButton(
            topo, text="▭", width=26, height=26, fg_color="transparent",
            hover_color=BORDA, text_color=TEXTO_SUB, font=(FONTE, 14),
            command=self._alternar_compacto)
        self.botao_compacto.pack(side="right", padx=(0, 2))
        self.botao_pausa = ctk.CTkButton(
            topo, text="⏸", width=26, height=26, fg_color="transparent",
            hover_color=BORDA, text_color=TEXTO_SUB, font=(FONTE, 14),
            command=self._alternar_pausa)
        self.botao_pausa.pack(side="right", padx=(0, 2))
        # Zoom: a janela foi dimensionada num monitor 4K e ocupa espaco demais
        # em telas menores. Aqui voce encolhe/aumenta tudo junto.
        for texto, passo in (("+", 0.1), ("−", -0.1)):
            ctk.CTkButton(topo, text=texto, width=22, height=26,
                          fg_color="transparent", hover_color=BORDA,
                          text_color=TEXTO_SUB, font=(FONTE, 14),
                          command=lambda d=passo: self._zoom(d)
                          ).pack(side="right", padx=(0, 1))
        self.pausado = False
        self.compacto = False
        self._tem_dados = False
        self._teto = {"base": False, "job": False}
        self._painel = None
        self._pulso = 0.0
        self._animacao = None

        # A janela tem tres caras, e mostrar a errada e o que fazia ela parecer
        # quebrada: antes da primeira leitura ela exibia dois blocos vazios com
        # "?" e um grafico em branco, como se algo tivesse falhado. Agora cada
        # momento tem a sua tela.
        self.painel_espera = self._montar_espera(corpo)
        self.painel_dados = ctk.CTkFrame(corpo, fg_color="transparent")
        self.painel_compacto = self._montar_compacto(corpo)

        # um bloco por barra: cada uma tem o proprio tempo pro nivel seguinte,
        # que era o que faltava — antes o job cabia numa linha solta no rodape
        self.blocos = {}
        for qual, rotulo, cor in (("base", "CLASS XP", VERDE),
                                  ("job", "JOB XP", ACENTO)):
            self.blocos[qual] = self._bloco(self.painel_dados, rotulo, cor, qual)

        # grafico com as duas curvas, nas mesmas cores dos blocos
        self.grafico = tk.Canvas(self.painel_dados,
                                 width=int(340 * self.escala_ui),
                                 height=int(155 * self.escala_ui), bg=CARTAO2,
                                 highlightthickness=0, bd=0)
        self.grafico.pack(padx=16, pady=(4, 6))

        # Tres coisas precisam estar certas pro texto longo aparecer inteiro,
        # e faltando qualquer uma ele e cortado:
        #   wraplength  quebra a linha (sem isso, some pelas bordas)
        #   - 2*PADDING porque o rotulo tem 16px de cada lado; usar a largura
        #               cheia faz cada linha nascer maior que a janela
        #   anchor="w"  o padrao do CTkLabel e centralizar, e ai o excesso
        #               vaza dos DOIS lados de uma vez
        self.detalhe = ctk.CTkLabel(self.painel_dados, text="", font=(FONTE, 12),
                                    text_color=TEXTO_SUB, justify="left",
                                    anchor="w",
                                    wraplength=self._largura_texto())
        self.detalhe.pack(padx=16, pady=(0, 14), anchor="w", fill="x")

        # arrastar por qualquer parte que nao seja o botao de fechar
        for alvo in (self, corpo, topo, self.titulo, self.detalhe, self.grafico):
            alvo.bind("<Button-1>", self._pegar)
            alvo.bind("<B1-Motion>", self._arrastar)

        # Janela sem borda nao se ajusta sozinha ao conteudo: sem isto ela fica
        # nos 200x200 do padrao e corta tudo. E o tamanho tem que ser dividido
        # pela escala: o CTk ja devolve winfo_req* em pixels FISICOS e torna a
        # multiplicar pela escala dentro de geometry() — sem isso sobra um vazio
        # embaixo, proporcional ao zoom do Windows.
        self.update_idletasks()
        try:
            escala = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            escala = 1.0
        self._largura = int(self.winfo_reqwidth() / escala)
        self._altura = int(self.winfo_reqheight() / escala)
        self.geometry(f"{self._largura}x{self._altura}")
        # so aqui: _trocar_painel chama _ajustar(), que precisa do tamanho ja medido
        self._trocar_painel("espera", animar=False)

    LARGURA_BASE = 340        # a coluna do conteudo, que o grafico define
    PADDING = 16

    # -- as tres telas ----------------------------------------------------

    def _montar_espera(self, pai):
        """Antes da primeira leitura: convida, em vez de parecer quebrada."""
        quadro = ctk.CTkFrame(pai, fg_color="transparent")
        interno = ctk.CTkFrame(quadro, fg_color=CARTAO2, corner_radius=10)
        interno.pack(fill="x", padx=16, pady=(4, 12))

        # o ponto que respira: um sinal silencioso de que o programa esta vivo
        # e esperando, nao travado
        self.pulso = tk.Canvas(interno, width=int(10 * self.escala_ui),
                               height=int(10 * self.escala_ui), bg=CARTAO2,
                               highlightthickness=0, bd=0)
        self.pulso.pack(pady=(20, 0))
        self.pulso.create_oval(1, 1, int(9 * self.escala_ui),
                               int(9 * self.escala_ui), fill=VERDE,
                               outline="", tags="ponto")

        self.espera_titulo = ctk.CTkLabel(
            interno, text="Go kill something", font=(FONTE, 17, "bold"),
            text_color=TEXTO)
        self.espera_titulo.pack(padx=20, pady=(12, 2))
        self.espera_texto = ctk.CTkLabel(
            interno, text="I'll start tracking as soon as you gain XP",
            font=(FONTE, 12), text_color=TEXTO_SUB, justify="center",
            wraplength=self._largura_texto())
        self.espera_texto.pack(padx=20, pady=(0, 22))

        for alvo in (quadro, interno, self.espera_titulo, self.espera_texto,
                     self.pulso):
            alvo.bind("<Button-1>", self._pegar)
            alvo.bind("<B1-Motion>", self._arrastar)
        return quadro

    def _montar_compacto(self, pai):
        """Modo pequeno: so os tempos, lado a lado, pra ficar fora do caminho."""
        quadro = ctk.CTkFrame(pai, fg_color="transparent")
        linha = ctk.CTkFrame(quadro, fg_color=CARTAO2, corner_radius=10)
        linha.pack(fill="x", padx=16, pady=(2, 14))

        self.compacto_itens = {}
        for qual, rotulo, cor in (("base", "CLASS", VERDE), ("job", "JOB", ACENTO)):
            caixa = ctk.CTkFrame(linha, fg_color="transparent")
            caixa.pack(side="left", padx=16, pady=12)
            titulo = ctk.CTkLabel(caixa, text=rotulo, font=(FONTE, 10, "bold"),
                                  text_color=cor)
            titulo.pack(anchor="w")
            tempo = ctk.CTkLabel(caixa, text="—", font=(FONTE, 20, "bold"),
                                 text_color=cor)
            tempo.pack(anchor="w")
            self.compacto_itens[qual] = {"caixa": caixa, "tempo": tempo}
            for alvo in (caixa, titulo, tempo):
                alvo.bind("<Button-1>", self._pegar)
                alvo.bind("<B1-Motion>", self._arrastar)

        # aparece so quando os dois chegam no teto: ai nao ha tempo pra mostrar,
        # e o espaco vira comemoracao em vez de um "—" sem sentido
        self.compacto_maximo = ctk.CTkLabel(
            linha, text="", font=(FONTE, 13, "bold"), text_color=LARANJA,
            justify="center", wraplength=self._largura_texto())

        for alvo in (quadro, linha):
            alvo.bind("<Button-1>", self._pegar)
            alvo.bind("<B1-Motion>", self._arrastar)
        return quadro

    def _trocar_painel(self, nome: str, animar: bool = True) -> None:
        """Mostra uma das telas. Trocar reencolhe a janela de proposito.

        `_ajustar` so cresce, o que e certo durante a operacao normal (evita
        tremer a cada atualizacao) e errado aqui: sem zerar, a janela ficaria
        do tamanho da tela completa depois de ir pro modo compacto.
        """
        if nome == self._painel:
            return
        for painel in (self.painel_espera, self.painel_dados,
                       self.painel_compacto):
            painel.pack_forget()
        alvo = {"espera": self.painel_espera, "dados": self.painel_dados,
                "compacto": self.painel_compacto}[nome]
        alvo.pack(fill="both", expand=True)
        self._painel = nome
        self._largura = self._altura = 1
        self._ajustar()
        if nome == "espera":
            self._respirar()
        if animar:
            self._surgir()

    # -- movimento --------------------------------------------------------

    ALPHA = 0.92

    def _surgir(self) -> None:
        """Transicao curta entre telas: some e volta, em vez de piscar seco."""
        passos = [0.55, 0.66, 0.77, 0.86, self.ALPHA]

        def passo(i: int = 0) -> None:
            if i >= len(passos) or not self.winfo_exists():
                return
            self.attributes("-alpha", passos[i])
            self.after(28, lambda: passo(i + 1))

        self.attributes("-alpha", 0.45)
        passo()

    def _respirar(self) -> None:
        """O ponto da tela de espera pulsando devagar.

        So roda enquanto essa tela esta visivel — animacao em painel escondido
        e trabalho jogado fora, e em overlay sobre jogo isso custa quadro.
        """
        if self._animacao is not None:
            self.after_cancel(self._animacao)
            self._animacao = None
        if self._painel != "espera" or not self.winfo_exists():
            return
        import math
        self._pulso = (self._pulso + 0.09) % (2 * math.pi)
        brilho = (math.sin(self._pulso) + 1) / 2          # 0..1
        self.pulso.itemconfigure("ponto", fill=_mistura(CARTAO2, VERDE,
                                                        0.25 + 0.75 * brilho))
        self._animacao = self.after(45, self._respirar)

    def _largura_texto(self) -> int:
        """Onde a linha do rodape deve quebrar, ja descontado o padding."""
        return int((self.LARGURA_BASE - 2 * self.PADDING) * self.escala_ui)

    def rodape(self, texto: str) -> None:
        """Escreve no rodape e ajusta a janela.

        Passa por aqui todo mundo que escreve ali. Antes cada chamador fazia
        `detalhe.configure(text=...)` direto, e so o caminho que desenhava o
        grafico chamava _ajustar() depois — ou seja, a janela crescia pra caber
        o texto CURTO da operacao normal, e nao crescia pro texto LONGO de
        configuracao, que e justamente o que precisa ser lido.
        """
        self.detalhe.configure(text=texto)
        self._ajustar()

    def _bloco(self, pai, rotulo: str, cor: str, qual: str) -> dict:
        quadro = ctk.CTkFrame(pai, fg_color=CARTAO2, corner_radius=10)
        quadro.pack(fill="x", padx=16, pady=(0, 8))

        linha = ctk.CTkFrame(quadro, fg_color="transparent")
        linha.pack(fill="x", padx=14, pady=(9, 0))
        ctk.CTkLabel(linha, text=rotulo, font=(FONTE, 12, "bold"),
                     text_color=cor).pack(side="left")
        nivel = ctk.CTkLabel(linha, text="", font=(FONTE, 12),
                             text_color=TEXTO_SUB)
        nivel.pack(side="right")
        # O numero do nivel nao esta na barra (ela guarda so o preenchimento),
        # entao vem do que voce informou. Clicar nele permite corrigir sem ter
        # que abrir o config na mao.
        nivel.configure(cursor="hand2")
        nivel.bind("<Button-1>", lambda _e, q=qual: self._corrigir(q))

        eta = ctk.CTkLabel(quadro, text="—", font=(FONTE, 30, "bold"),
                           text_color=cor)
        eta.pack(padx=14, anchor="w")
        rodape = ctk.CTkLabel(quadro, text="measuring...", font=(FONTE, 12),
                              text_color=TEXTO_SUB)
        rodape.pack(padx=14, pady=(0, 11), anchor="w")
        for alvo in (quadro, linha, eta, rodape):
            alvo.bind("<Button-1>", self._pegar)
            alvo.bind("<B1-Motion>", self._arrastar)
        return {"nivel": nivel, "eta": eta, "rodape": rodape, "cor": cor}

    # nivel maximo de cada barra: chegando ali, nao ha proximo nivel pra estimar
    TETO = {"base": 150, "job": 70}

    def atualizar_bloco(self, qual: str, nivel: int, pct: float | None,
                        eta: float | None, taxa: float | None) -> None:
        # chegou leitura: a tela de convite ja cumpriu o papel dela
        self._tem_dados = True
        self._teto[qual] = (nivel >= self.TETO.get(qual, 10**9)
                            and pct is not None and pct >= 99.9)
        self._atualizar_compacto(qual, nivel, eta, self._teto[qual])
        self._decidir_painel()

        bloco = self.blocos[qual]
        bloco["nivel"].configure(text=f"level {nivel}")

        # pct None = o servidor deu o nivel e o XP, mas ninguem sabe ainda
        # quanto este nivel PEDE. Sem isso nao existe porcentagem — e dizer
        # "0.0% done" seria inventar. Aqui a janela pede o que falta.
        if pct is None:
            bloco["eta"].configure(text="—", text_color=TEXTO_SUB)
            bloco["rodape"].configure(text="click the level ↑ and type the %")
            return

        # Barra no maximo ficava dizendo "measuring..." pra sempre: sem ganho a
        # taxa e 0, o ETA vira None e a interface parecia travada. Agora ela diz
        # o que e — nao ha o que medir.
        if nivel >= self.TETO.get(qual, 10**9) and pct >= 99.9:
            bloco["eta"].configure(text="MAX", text_color=bloco["cor"])
            bloco["rodape"].configure(text="max level reached")
            return
        if eta is None:
            bloco["eta"].configure(text="—", text_color=TEXTO_SUB)
            bloco["rodape"].configure(text=f"{pct:.1f}% done · measuring…")
            return
        if taxa:
            ritmo = (f"{taxa:.1f}%/h" if taxa < 100
                     else f"{taxa / 100:.2f} levels/h")
        else:
            ritmo = "—"
        bloco["eta"].configure(text=motor_xp.formatar_tempo(eta),
                               text_color=bloco["cor"])
        bloco["rodape"].configure(
            text=f"{pct:.1f}% done  ·  to {nivel + 1}  ·  {ritmo}")


    def _alternar_compacto(self) -> None:
        self.compacto = not self.compacto
        self.botao_compacto.configure(text="▬" if self.compacto else "▭")
        self._decidir_painel()

    def _decidir_painel(self) -> None:
        """Escolhe a tela pelo que existe pra mostrar, nao pelo que o usuario
        clicou por ultimo: sem leitura nenhuma, o modo compacto mostraria dois
        travessoes e nada mais."""
        if not self._tem_dados:
            self._trocar_painel("espera")
        else:
            self._trocar_painel("compacto" if self.compacto else "dados")

    def esperando(self, titulo: str = "", texto: str = "") -> None:
        """Volta pra tela de convite, opcionalmente com outra mensagem."""
        self._tem_dados = False
        if titulo:
            self.espera_titulo.configure(text=titulo)
        if texto:
            self.espera_texto.configure(text=texto)
        self._decidir_painel()

    def _atualizar_compacto(self, qual: str, nivel: int, eta: float | None,
                            no_teto: bool) -> None:
        item = self.compacto_itens[qual]
        if no_teto:
            # no maximo nao ha tempo pra mostrar; a caixa sai da linha em vez
            # de ocupar espaco com um "—" que nao quer dizer nada
            item["caixa"].pack_forget()
        else:
            if not item["caixa"].winfo_ismapped():
                item["caixa"].pack(side="left", padx=16, pady=12)
            item["tempo"].configure(
                text=motor_xp.formatar_tempo(eta) if eta else "—")

        no_maximo = all(self._teto.get(q) for q in ("base", "job"))
        if no_maximo:
            self.compacto_maximo.configure(text="🏆  all maxed out")
            if not self.compacto_maximo.winfo_ismapped():
                self.compacto_maximo.pack(padx=18, pady=14)
        elif self.compacto_maximo.winfo_ismapped():
            self.compacto_maximo.pack_forget()

    @property
    def tudo_no_maximo(self) -> bool:
        """Classe e job os dois no teto — nao ha mais nada a estimar."""
        return all(self._teto.values())

    def _ajustar(self) -> None:
        """Cresce a janela se o conteudo passou a nao caber.

        A largura era fixada na abertura, com os rotulos ainda vazios. Quando o
        texto cresce ("63.7% done · to 113 · 1.13 levels/h") ele estourava e era
        cortado dos DOIS lados. So cresce, nunca encolhe: encolher faria a
        janela tremer a cada atualizacao.
        """
        self.update_idletasks()
        try:
            escala = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            escala = 1.0
        larg = int(self.winfo_reqwidth() / escala)
        alt = int(self.winfo_reqheight() / escala)
        if larg > self._largura or alt > self._altura:
            self._largura = max(larg, self._largura)
            self._altura = max(alt, self._altura)
            self.geometry(f"{self._largura}x{self._altura}"
                          f"+{self.winfo_x()}+{self.winfo_y()}")

    def posicionar(self, x: int, y: int) -> None:
        """Move sem perder o tamanho (geometry so com '+x+y' zera o resto)."""
        self.geometry(f"{self._largura}x{self._altura}+{x}+{y}")

    JANELA_RITMO = 90.0   # segundos de historico que formam cada ponto da curva

    @staticmethod
    def _curva_ritmo(historico: list, coluna: int,
                     janela: float = JANELA_RITMO) -> list[tuple[float, float]]:
        """Ritmo (%/h) ao longo do tempo, em janela movel.

        O acumulado so cresce — parar de matar deixa a linha reta, nunca a
        derruba. Aqui cada ponto e quanto XP entrou nos ultimos `janela`
        segundos, entao a curva SOBE quando voce acelera e CAI quando esfria.
        """
        saida = []
        inicio = 0
        for atual in range(len(historico)):
            t_atual = historico[atual][0]
            while (inicio < atual
                   and historico[inicio][0] < t_atual - janela):
                inicio += 1
            intervalo = t_atual - historico[inicio][0]
            if intervalo < 5:     # amostra curta demais pra dizer qualquer coisa
                continue
            ganho = historico[atual][coluna] - historico[inicio][coluna]
            saida.append((t_atual, ganho / intervalo * 3600))
        return saida

    def desenhar(self, historico: list, duracao: float) -> None:
        """Curva do RITMO de XP ao longo da sessao.

        Nao e o acumulado: aquilo so subia, e ficar parado apenas achatava a
        linha. Aqui o eixo Y e %/h medido numa janela movel, entao da pra ver
        na hora se o spot esfriou.
        """
        g = self.grafico
        g.delete("all")
        larg = int(g.cget("width"))
        alt = int(g.cget("height"))

        ritmo_base = self._curva_ritmo(historico, 1)
        ritmo_job = self._curva_ritmo(historico, 2)
        if len(ritmo_base) < 2:
            g.create_text(larg // 2, alt // 2, text="collecting...",
                          fill=TEXTO_SUB, font=(FONTE, 11))
            return

        # Lendo da memoria chegam ~4 amostras por segundo: desenhar todas seria
        # redesenhar milhares de pontos varias vezes por segundo, sem ganho
        # nenhum de resolucao (o canvas tem ~300 pixels de largura).
        def reduzir(serie):
            if len(serie) > larg:
                passo = len(serie) // larg + 1
                return serie[::passo] + [serie[-1]]
            return serie

        ritmo_base, ritmo_job = reduzir(ritmo_base), reduzir(ritmo_job)
        t0 = ritmo_base[0][0]
        pontos = [(t - t0, v) for t, v in ritmo_base]
        pontos_job = [(t - t0, v) for t, v in ritmo_job]
        span_x = max(1e-6, pontos[-1][0])
        span_y = max(1e-6, max(y for _x, y in pontos),
                     max(y for _x, y in pontos_job))

        # Espaco reservado FORA da area do desenho: o nome do eixo fica do lado
        # de fora da seta e os numeros ficam dentro, senao um escreve por cima
        # do outro (era o "+11.5%" em cima do "XP" e a duracao em cima de "time").
        #
        # As margens saem do tamanho REAL do texto, medido agora: o canvas mede
        # em pixels logicos mas a fonte sai escalada pelo zoom do monitor, entao
        # margem fixa corta o rotulo em tela 4K e sobra espaco em tela comum.
        def medir(texto):
            item = g.create_text(-999, -999, text=texto, font=(FONTE, 10, "bold"))
            caixa = g.bbox(item)
            g.delete(item)
            return (caixa[2] - caixa[0], caixa[3] - caixa[1]) if caixa else (30, 14)

        larg_rotulo, alt_rotulo = medir("time")
        larg_eixo_y, _ = medir("XP/h")
        esq = 6
        dir_ = larg_rotulo + 14
        topo = alt_rotulo
        baixo = alt_rotulo
        x0, y0 = esq, alt - baixo          # origem
        x1, y1 = larg - dir_, topo         # canto oposto

        for fracao in (0.33, 0.66):        # grade discreta
            y = y0 - (y0 - y1) * fracao
            g.create_line(x0, y, x1, y, fill=BORDA)

        def tela(x, y):
            return (x0 + (x1 - x0) * (x / span_x),
                    y0 - (y0 - y1) * (y / span_y))

        coords = []
        for x, y in pontos:
            coords.extend(tela(x, y))
        area = list(coords)
        area.extend([x1, y0, x0, y0])
        g.create_polygon(area, fill="#14331f", outline="")

        coords_job = []
        for x, y in pontos_job:
            coords_job.extend(tela(x, y))
        g.create_line(coords_job, fill=ACENTO, width=2)
        g.create_line(coords, fill=VERDE, width=2)

        # eixos com seta: XP sobe, tempo anda pra direita
        g.create_line(x0, y0, x0, y1 - 6, fill=TEXTO_SUB, width=1,
                      arrow="last", arrowshape=(6, 7, 3))
        g.create_line(x0, y0, x1 + 6, y0, fill=TEXTO_SUB, width=1,
                      arrow="last", arrowshape=(6, 7, 3))
        # nomes dos eixos: acima da seta de cima, e depois da seta da direita
        g.create_text(x0 + 6, y1 - 9, anchor="w", text="XP/h",
                      fill=TEXTO_SUB, font=(FONTE, 10, "bold"))
        g.create_text(x1 + 10, y0, anchor="w", text="time",
                      fill=TEXTO_SUB, font=(FONTE, 10, "bold"))

        # ao lado do nome do eixo vai o ritmo de AGORA, nao o pico: e o numero
        # que responde "estou rendendo mais ou menos que ha pouco?"
        atual = pontos[-1][1]
        g.create_text(x0 + 6 + larg_eixo_y + 10, y1 - 9, anchor="w",
                      text=f"{atual:.0f}%/h", fill=VERDE, font=(FONTE, 10, "bold"))
        g.create_text(x0 + 3, y0 - 2, anchor="sw", text="0", fill=TEXTO_SUB,
                      font=(FONTE, 9))
        g.create_text(x1 - 3, y0 - 2, anchor="se",
                      text=motor_xp.formatar_tempo(duracao), fill=TEXTO_SUB,
                      font=(FONTE, 9))
        self._ajustar()

    def _pegar(self, evento):
        self._dx = evento.x_root - self.winfo_x()
        self._dy = evento.y_root - self.winfo_y()

    def _arrastar(self, evento):
        self.posicionar(evento.x_root - self._dx, evento.y_root - self._dy)

    def _fechar(self):
        if self.ao_fechar:
            self.ao_fechar()
        else:
            self.destroy()

    def _zoom(self, passo: float):
        """Encolhe ou aumenta a janela inteira, e guarda a escolha."""
        nova = round(min(1.4, max(0.5, self.escala_ui + passo)), 2)
        if nova == self.escala_ui:
            return
        self.escala_ui = nova
        ctk.set_widget_scaling(nova)
        self.grafico.configure(width=int(340 * nova), height=int(155 * nova))
        # a quebra de linha acompanha o zoom, senao o texto volta a estourar
        self.detalhe.configure(wraplength=self._largura_texto())
        # deixa a janela reencolher: so crescer travaria no tamanho antigo
        self._largura = self._altura = 1
        self._ajustar()
        if self.ao_zoom:
            self.ao_zoom(nova)

    def _corrigir(self, qual: str):
        if self.ao_corrigir_nivel:
            self.ao_corrigir_nivel(qual)

    def _alternar_pausa(self):
        """Pausa a contagem — util quando voce vai pra cidade.

        O tempo parado NAO entra na conta: sem isso, dez minutos vendendo
        derrubariam o ritmo medio e a estimativa ficaria sem sentido.
        """
        self.pausado = not self.pausado
        self.botao_pausa.configure(text="►" if self.pausado else "⏸",
                                   text_color=VERDE if self.pausado else TEXTO_SUB)
        # O TEXTO do titulo nao muda de tamanho de proposito: a janela tem
        # largura fixa, e um titulo maior empurrava os botoes pra fora do
        # layout — o proprio botao de pause sumia depois de pausar. O estado
        # aparece pela cor do titulo e pelo simbolo do botao.
        self.titulo.configure(text_color=LARANJA if self.pausado else TEXTO_SUB)
        if self.ao_pausar:
            self.ao_pausar(self.pausado)

    def _zerar(self):
        """Recomeca a contagem sem fechar a janela nem reprocurar as barras."""
        if self.ao_zerar:
            self.ao_zerar()
        self.grafico.delete("all")
        for bloco in self.blocos.values():
            bloco["eta"].configure(text="—", text_color=TEXTO_SUB)
            bloco["rodape"].configure(text="measuring...")
        self.rodape("session restarted")

    def avisar(self, mensagem: str, detalhe: str = "") -> None:
        """Mostra um problema no lugar dos tempos, sem apagar os blocos."""
        for bloco in self.blocos.values():
            bloco["eta"].configure(text="?", text_color=LARANJA)
            bloco["rodape"].configure(text=mensagem)
        self.rodape(detalhe)

