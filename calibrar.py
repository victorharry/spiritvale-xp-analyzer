"""Marca na tela onde fica a barra de XP.

Uma janelinha diz o que deixar na tela; voce arruma o jogo e so entao manda
congelar. Ela some do print antes da captura, entao nunca entra no recorte.
"""

from __future__ import annotations

import argparse
import time
import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image, ImageTk

import comum

# (chave, o que deixar na tela, o que marcar)
PASSOS_XP = [
    ("xp_regiao",
     "Deixe o HUD do jogo a mostra, com a barra de XP visivel (aquela com "
     "'Base Level ... % ... % ... Job Level').",
     "a BARRA DE XP INTEIRA - do numero do nivel base, na esquerda, ate o "
     "numero do nivel de job, na direita; pegue os dois hexagonos junto"),
]

MODOS = {"xp": PASSOS_XP}

# Regioes cuja aparencia vira "assinatura" da tela (deteccao por semelhanca).
ASSINATURAS: dict[str, str] = {}   # a barra de XP nao usa assinatura


def capturar_tela() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        bruto = sct.grab(monitor)
    return Image.frombytes("RGB", bruto.size, bruto.bgra, "raw", "BGRX")


class _Selecao:
    """Sobrepoe a tela congelada e devolve um retangulo."""

    def __init__(self, pai: tk.Tk, imagem: Image.Image, instrucao: str):
        self.retorno: list[int] | None = None
        self.inicio: tuple[int, int] | None = None

        self.janela = tk.Toplevel(pai)
        self.janela.attributes("-fullscreen", True)
        self.janela.attributes("-topmost", True)
        self.janela.configure(cursor="crosshair")

        self.tk_img = ImageTk.PhotoImage(imagem)
        self.canvas = tk.Canvas(self.janela, width=imagem.width, height=imagem.height,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor="nw")
        self.canvas.create_rectangle(0, 0, imagem.width, 78, fill="#000000", outline="")
        self.canvas.create_text(imagem.width // 2, 28, fill="#ffffff",
                                font=("Segoe UI", 17, "bold"),
                                text=f"Arraste em cima de: {instrucao}")
        self.canvas.create_text(imagem.width // 2, 58, fill="#9fb4d0",
                                font=("Segoe UI", 11),
                                text="ESC volta pro passo sem marcar nada")
        self.retangulo = None

        self.canvas.bind("<ButtonPress-1>", self._pressionar)
        self.canvas.bind("<B1-Motion>", self._arrastar)
        self.canvas.bind("<ButtonRelease-1>", self._soltar)
        self.janela.bind("<Escape>", lambda _e: self.janela.destroy())
        self.janela.focus_force()
        pai.wait_window(self.janela)

    def _pressionar(self, evento) -> None:
        self.inicio = (evento.x, evento.y)
        if self.retangulo:
            self.canvas.delete(self.retangulo)
        self.retangulo = self.canvas.create_rectangle(
            evento.x, evento.y, evento.x, evento.y, outline="#31d0ff", width=3)

    def _arrastar(self, evento) -> None:
        if self.inicio and self.retangulo:
            self.canvas.coords(self.retangulo, *self.inicio, evento.x, evento.y)

    def _soltar(self, evento) -> None:
        if not self.inicio:
            return
        x0, y0 = self.inicio
        largura, altura = abs(evento.x - x0), abs(evento.y - y0)
        if largura < 10 or altura < 8:
            self.inicio = None  # arrasto acidental
            return
        self.retorno = [min(x0, evento.x), min(y0, evento.y), largura, altura]
        self.janela.destroy()


class Assistente:
    """Conduz a calibracao passo a passo, sem congelar tudo de uma vez."""

    def __init__(self, passos: list[tuple[str, str, str]], modo: str):
        self.passos = passos
        self.modo = modo
        self.resultados: dict[str, list[int]] = {}
        self.recortes: dict[str, Image.Image] = {}
        self.indice = 0
        self.cancelado = False

        self.root = tk.Tk()
        self.root.title(f"Calibracao — {modo}")
        self.root.attributes("-topmost", True)
        self.root.geometry("+60+60")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancelar)

        dpi = self.root.winfo_fpixels("1i")
        if dpi / 96 > 1.05:
            self.root.tk.call("tk", "scaling", dpi / 72)

        quadro = ttk.Frame(self.root, padding=14)
        quadro.pack(fill="both", expand=True)

        self.rot_passo = ttk.Label(quadro, font=("Segoe UI", 11, "bold"))
        self.rot_passo.pack(anchor="w")
        self.rot_preparo = ttk.Label(quadro, wraplength=int(420 * max(1, dpi / 96)),
                                     justify="left", foreground="#1c4f8b")
        self.rot_preparo.pack(anchor="w", pady=(8, 2))
        self.rot_marcar = ttk.Label(quadro, wraplength=int(420 * max(1, dpi / 96)),
                                    justify="left")
        self.rot_marcar.pack(anchor="w", pady=(0, 10))

        linha = ttk.Frame(quadro)
        linha.pack(fill="x")
        self.botao = ttk.Button(linha, text="Congelar a tela", command=self._congelar)
        self.botao.pack(side="left")
        ttk.Label(linha, text="depois de").pack(side="left", padx=(8, 4))
        self.atraso = tk.IntVar(value=4)
        ttk.Spinbox(linha, from_=0, to=20, width=3,
                    textvariable=self.atraso).pack(side="left")
        ttk.Label(linha, text="s").pack(side="left", padx=(2, 0))
        ttk.Button(linha, text="Pular", command=self._pular).pack(side="right")
        ttk.Button(linha, text="Cancelar", command=self._cancelar).pack(side="right", padx=6)

        self.rot_status = ttk.Label(quadro, foreground="#4a5568")
        self.rot_status.pack(anchor="w", pady=(10, 0))

        self._mostrar()

    # ------------------------------------------------------------------

    def _mostrar(self) -> None:
        if self.indice >= len(self.passos):
            self.root.destroy()
            return
        chave, preparo, marcar = self.passos[self.indice]
        self.rot_passo.configure(text=f"Passo {self.indice + 1} de {len(self.passos)}")
        self.rot_preparo.configure(text="1. " + preparo)
        self.rot_marcar.configure(text=f"2. Depois de congelar, arraste em cima de: {marcar}.")
        feitos = len(self.resultados)
        self.rot_status.configure(
            text=f"{feitos} de {len(self.passos)} marcados"
            + ("   ·   volte pro jogo depois de clicar em Congelar" if not feitos else ""))

    def _congelar(self) -> None:
        segundos = max(0, self.atraso.get())
        self.botao.configure(state="disabled")
        self._contar(segundos)

    def _contar(self, restante: int) -> None:
        if restante > 0:
            self.rot_status.configure(text=f"Congelando em {restante}...  "
                                           "deixe o jogo na frente")
            self.root.after(1000, lambda: self._contar(restante - 1))
            return

        # esconde a janelinha pra ela nao aparecer no recorte
        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)
        imagem = capturar_tela()
        self.root.deiconify()
        self.root.attributes("-topmost", True)

        chave, _preparo, marcar = self.passos[self.indice]
        selecao = _Selecao(self.root, imagem, marcar).retorno
        self.botao.configure(state="normal")
        if selecao is None:
            self.rot_status.configure(text="Nada marcado. Tente de novo.")
            return
        self.resultados[chave] = selecao
        x, y, largura, altura = selecao
        self.recortes[chave] = imagem.crop((x, y, x + largura, y + altura))
        self.indice += 1
        self._mostrar()

    def _pular(self) -> None:
        self.indice += 1
        self._mostrar()

    def _cancelar(self) -> None:
        self.cancelado = True
        self.root.destroy()

    def executar(self) -> dict[str, list[int]] | None:
        self.root.mainloop()
        return None if self.cancelado else self.resultados


def main() -> None:
    comum.preparar_console()
    comum.ativar_dpi()

    parser = argparse.ArgumentParser(description="Calibra a barra de XP.")
    parser.add_argument("--modo", choices=sorted(MODOS), default="xp",
                        help="so existe o modo xp")
    args = parser.parse_args()

    assistente = Assistente(MODOS[args.modo], args.modo)
    regioes = assistente.executar()
    if not regioes:
        print("Calibracao cancelada. Nada foi salvo.")
        raise SystemExit(1)

    cfg = comum.carregar_config()
    cfg["tela"] = list(comum.tamanho_tela())
    cfg.update(regioes)

    # Grava a "impressao digital" das regioes de deteccao (mercado aberto, tela
    # de login, tela de personagem): e o que depois permite reconhecer a tela
    # sem depender de limiar chutado.
    for regiao, chave_assinatura in ASSINATURAS.items():
        if regiao in assistente.recortes:
            cfg[chave_assinatura] = comum.assinatura(assistente.recortes[regiao])
            print(f"  assinatura gravada: {chave_assinatura}")

    comum.salvar_config(cfg)
    print(f"Calibracao de {args.modo} salva em config.json:")
    for chave in regioes:
        print(f"  {chave:<20}: {cfg[chave]}")


if __name__ == "__main__":
    main()
