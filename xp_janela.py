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


class JanelaXP(ctk.CTkToplevel):
    """Sobreposicao sem borda, sempre no topo, que voce arrasta pra onde quiser.

    Mostra o ritmo de XP e quanto falta pro proximo nivel. Fica pequena de
    proposito: ela e capturada junto com a tela, entao se cobrir a lista de
    ofertas ou a propria barra de XP, atrapalha o OCR do resto do programa.
    """

    def __init__(self, pai, ao_fechar=None, ao_zerar=None, ao_pausar=None,
                 ao_corrigir_nivel=None):
        super().__init__(pai, fg_color=CARTAO)
        self.ao_fechar = ao_fechar
        self.ao_zerar = ao_zerar
        self.ao_pausar = ao_pausar
        self.ao_corrigir_nivel = ao_corrigir_nivel
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.92)
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
        self.botao_pausa = ctk.CTkButton(
            topo, text="⏸", width=26, height=26, fg_color="transparent",
            hover_color=BORDA, text_color=TEXTO_SUB, font=(FONTE, 14),
            command=self._alternar_pausa)
        self.botao_pausa.pack(side="right", padx=(0, 2))
        self.pausado = False

        # um bloco por barra: cada uma tem o proprio tempo pro nivel seguinte,
        # que era o que faltava — antes o job cabia numa linha solta no rodape
        self.blocos = {}
        for qual, rotulo, cor in (("base", "CLASS XP", VERDE),
                                  ("job", "JOB XP", ACENTO)):
            self.blocos[qual] = self._bloco(corpo, rotulo, cor, qual)

        # grafico com as duas curvas, nas mesmas cores dos blocos
        self.grafico = tk.Canvas(corpo, width=340, height=155, bg=CARTAO2,
                                 highlightthickness=0, bd=0)
        self.grafico.pack(padx=16, pady=(4, 6))

        self.detalhe = ctk.CTkLabel(corpo, text="", font=(FONTE, 12),
                                    text_color=TEXTO_SUB, justify="left")
        self.detalhe.pack(padx=16, pady=(0, 14), anchor="w")

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

    def atualizar_bloco(self, qual: str, nivel: int, pct: float,
                        eta: float | None, taxa: float | None) -> None:
        bloco = self.blocos[qual]
        bloco["nivel"].configure(text=f"level {nivel}")

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
        self.detalhe.configure(text="session restarted")

    def avisar(self, mensagem: str, detalhe: str = "") -> None:
        """Mostra um problema no lugar dos tempos, sem apagar os blocos."""
        for bloco in self.blocos.values():
            bloco["eta"].configure(text="?", text_color=LARANJA)
            bloco["rodape"].configure(text=mensagem)
        self.detalhe.configure(text=detalhe)

