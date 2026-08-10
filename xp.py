"""Medidor de XP: le a barra do jogo e estima quanto falta pro proximo nivel.

A barra mostra tudo numa linha so:

    [111] Base Level        6,8%   100%        Job Level [70]

Entao a leitura e posicional: os quatro numeros, da esquerda pra direita, sao
nivel base, % base, % de job e nivel de job. Nao dependemos de achar as
palavras "Base"/"Job" — elas ficam sobre fundo colorido e o OCR erra mais nelas
do que nos numeros.

A estimativa usa uma JANELA recente (nao a sessao inteira): se voce parou dez
minutos pra vender, a media da sessao mentiria pra baixo e o "falta" nunca
convergiria.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import comum

# A barra e TRANSLUCIDA: o cenario aparece atras (pedra marrom, folhagem
# verde com flores brancas, ceu). Por isso a leitura nao pode depender de
# brilho — flor branca fica igual a letra branca em escala de cinza.
#
# Cada estrategia e um jeito de separar a letra do fundo; a primeira que
# devolver os quatro numeros esperados vence.
#   v_minimo: quao claro tem que ser pra contar como branco
#   s_maximo: quao "sem cor" — derruba verde, marrom, azul e amarelo
#   mancha:   remove branco mais GROSSO que isso (flor, nuvem), guarda o traco
# A ordem importa: a primeira que fecha os quatro numeros vence. A mais
# EXIGENTE vem primeiro de proposito — as frouxas tambem devolvem quatro
# numeros em folhagem, so que errados ("111" vira "11", "70" vira "10"), e
# leitura errada com cara de certa e pior que leitura que falha.
ESTRATEGIAS = (
    {"v_minimo": 215, "s_maximo": 30, "mancha": 13},
    {"v_minimo": 205, "s_maximo": 45, "mancha": 9},
    {"v_minimo": 190, "s_maximo": 60, "mancha": 9},
    {"v_minimo": 175, "s_maximo": 80, "mancha": 7},
    {"v_minimo": 205, "s_maximo": 45, "mancha": 0},   # sem tirar manchas
)
# ultimo recurso: o filtro antigo, por brilho puro (funciona em fundo escuro)
LIMIARES = (200, 170, 225, 140)
NUMERO = re.compile(r"^\d{1,3}(?:[.,]\d{1,2})?%?$")


def _valor(texto: str) -> float | None:
    limpo = texto.replace("%", "").replace(",", ".").strip()
    try:
        return float(limpo)
    except ValueError:
        return None


def _numeros(palavras) -> list[float]:
    achados = []
    for palavra in sorted(palavras, key=lambda p: p["x"]):
        texto = palavra["texto"].strip()
        if not NUMERO.match(texto):
            continue
        valor = _valor(texto)
        if valor is not None:
            achados.append(valor)
    return achados


def tentativas(imagem):
    """(rotulo, numeros lidos) de cada estrategia, na ordem de preferencia."""
    for opcoes in ESTRATEGIAS:
        palavras = comum.palavras_ocr(imagem, psm=7, escala=3, conf_minima=0,
                                      texto_branco=opcoes)
        rotulo = (f"branco v>={opcoes['v_minimo']} s<={opcoes['s_maximo']} "
                  f"mancha={opcoes['mancha']}")
        yield rotulo, _numeros(palavras)
    for limiar in LIMIARES:
        palavras = comum.palavras_ocr(imagem, psm=7, escala=3, conf_minima=0,
                                      texto_claro=limiar)
        yield f"brilho {limiar}", _numeros(palavras)


def numeros_da_barra(imagem) -> list[float]:
    """Os numeros da barra, da esquerda pra direita.

    Passa por cada estrategia e fica com a PRIMEIRA que devolve os quatro
    numeros esperados; se nenhuma fechar, entrega a melhor que conseguiu (o
    chamador decide se serve).
    """
    melhor: list[float] = []
    for _rotulo, achados in tentativas(imagem):
        if len(achados) == 4:
            return achados
        if len(achados) > len(melhor):
            melhor = achados
    return melhor


def _montar(valores: list[float]) -> dict | None:
    """Vira dicionario, ou None se os numeros nao forem plausiveis."""
    if len(valores) != 4:
        return None
    base_nivel, base_pct, job_pct, job_nivel = valores
    # sanidade: nivel e inteiro, porcentagem nunca passa de 100
    if base_pct > 100 or job_pct > 100:
        return None
    if base_nivel != int(base_nivel) or job_nivel != int(job_nivel):
        return None
    if base_nivel < 1 or job_nivel < 1:
        return None
    return {"base_nivel": int(base_nivel), "base_pct": base_pct,
            "job_nivel": int(job_nivel), "job_pct": job_pct}


def ler_barra(imagem, base_conhecido: int | None = None) -> dict | None:
    """(nivel base, % base, % job, nivel job) — None se a leitura nao fechar.

    Passando `base_conhecido`, so aceita a estrategia cujo nivel bate com o que
    ja sabemos (o nivel muda de 1 em 1, nunca salta). Isso derruba a leitura
    plausivel-porem-errada: sobre folhagem, um filtro frouxo le "11" no lugar
    de "111" e devolveria quatro numeros como se estivesse tudo bem.
    """
    primeira = None
    for _rotulo, valores in tentativas(imagem):
        leitura = _montar(valores)
        if leitura is None:
            continue
        if base_conhecido is None:
            return leitura
        if abs(leitura["base_nivel"] - base_conhecido) <= 1:
            return leitura
        if primeira is None:
            primeira = leitura
    # havia leituras, mas nenhuma condiz com o nivel conhecido: melhor devolver
    # nada do que envenenar a media com um nivel inventado
    return None


def formatar_tempo(segundos: float | None) -> str:
    if segundos is None or segundos <= 0 or segundos != segundos:  # NaN
        return "—"
    if segundos > 99 * 3600:
        return "> 99h"
    horas, resto = divmod(int(segundos), 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}m"
    if minutos:
        return f"{minutos}m {segs:02d}s"
    return f"{segs}s"


@dataclass
class Rastreador:
    """Guarda as leituras e responde ritmo e tempo restante.

    `progresso` lineariza nivel + porcentagem (nivel 111 a 6,8% vira 11106,8),
    entao subir de nivel nao vira uma queda de 100% pra 0%.
    """

    janela_minutos: float = 15.0
    amostras: list[tuple[float, float, float]] = field(default_factory=list)
    # historico da sessao inteira, pro grafico — as amostras acima sao podadas
    # na janela recente, entao nao servem pra desenhar a curva toda
    historico: list[tuple[float, float, float]] = field(default_factory=list)
    limite_historico: int = 3000
    inicio: float | None = None
    primeira: dict | None = None
    ultima: dict | None = None

    @staticmethod
    def progresso(nivel: int, pct: float) -> float:
        return nivel * 100.0 + pct

    # salto maior que isso (em % de nivel) nao e progresso: e leitura corrigida
    SALTO_ABSURDO = 150.0

    def registrar(self, leitura: dict, agora: float | None = None) -> None:
        agora = time.time() if agora is None else agora

        # O nivel vem de UMA leitura de tela, e o OCR erra (ja leu "17" no lugar
        # de "71"). Quando ele se corrige, o progresso linearizado da um salto de
        # dezenas de niveis e o ritmo vai pra casa dos milhares de %/h. Salto
        # assim nao e XP ganho: e a leitura consertada. Recomeca a contagem.
        if self.ultima:
            for chave_n, chave_p in (("base_nivel", "base_pct"),
                                     ("job_nivel", "job_pct")):
                antes = self.progresso(self.ultima[chave_n], self.ultima[chave_p])
                agora_prog = self.progresso(leitura[chave_n], leitura[chave_p])
                if abs(agora_prog - antes) > self.SALTO_ABSURDO:
                    self.amostras.clear()
                    self.historico.clear()
                    self.inicio = None
                    self.primeira = None
                    break

        if self.inicio is None:
            self.inicio = agora
            self.primeira = dict(leitura)
        self.ultima = dict(leitura)
        ponto = (
            agora,
            self.progresso(leitura["base_nivel"], leitura["base_pct"]),
            self.progresso(leitura["job_nivel"], leitura["job_pct"]),
        )
        self.amostras.append(ponto)
        self.historico.append(ponto)
        if len(self.historico) > self.limite_historico:
            # descarta um sim, um nao: mantem a forma da curva inteira
            self.historico = self.historico[::2]
        self._podar(agora)

    def _podar(self, agora: float) -> None:
        limite = agora - self.janela_minutos * 60
        # mantem sempre pelo menos duas amostras pra taxa nao sumir
        while len(self.amostras) > 2 and self.amostras[0][0] < limite:
            self.amostras.pop(0)

    def taxa(self, qual: str = "base") -> float | None:
        """Avanco em % por hora na janela recente. None se ainda nao da pra dizer."""
        if len(self.amostras) < 2:
            return None
        coluna = 1 if qual == "base" else 2
        t0, *_ = self.amostras[0]
        t1 = self.amostras[-1][0]
        span = t1 - t0
        if span < 30:            # menos de 30s nao diz nada
            return None
        avanco = self.amostras[-1][coluna] - self.amostras[0][coluna]
        if avanco <= 0:
            return 0.0
        return avanco / span * 3600

    def falta(self, qual: str = "base") -> float | None:
        if not self.ultima:
            return None
        pct = self.ultima["base_pct" if qual == "base" else "job_pct"]
        return max(0.0, 100.0 - pct)

    def eta(self, qual: str = "base") -> float | None:
        """Segundos ate o proximo nivel. None se o ritmo ainda nao da conta."""
        taxa = self.taxa(qual)
        falta = self.falta(qual)
        if not taxa or falta is None:
            return None
        return falta / taxa * 3600

    def ganho_total(self, qual: str = "base") -> float | None:
        """Quanto avancou desde que o medidor abriu, em % de nivel."""
        if not (self.primeira and self.ultima):
            return None
        chave_n = "base_nivel" if qual == "base" else "job_nivel"
        chave_p = "base_pct" if qual == "base" else "job_pct"
        return (self.progresso(self.ultima[chave_n], self.ultima[chave_p])
                - self.progresso(self.primeira[chave_n], self.primeira[chave_p]))

    def duracao(self) -> float:
        if self.inicio is None or not self.amostras:
            return 0.0
        return self.amostras[-1][0] - self.inicio


class LeitorMemoria:
    """Le as barras direto da memoria do jogo, sem OCR.

    Localiza o `fillAmount` das duas barras por assinatura e confirma com UMA
    leitura de tela — dai em diante o valor vem da memoria, exato. Os niveis
    nao estao ali (a barra so guarda o preenchimento), entao vem da mesma
    leitura inicial; subir de nivel e detectado pela QUEDA BRUSCA da barra,
    que dispensa ler o numero de novo.
    """

    # Subir de nivel e a barra indo de QUASE CHEIA a QUASE VAZIA. Aceitar
    # "caiu 40 pontos" era frouxo demais: num par errado, qualquer oscilacao
    # virava level up e o nivel subia sem parar (chegou a 160, acima do teto).
    CHEIA = 85.0
    VAZIA = 20.0
    TETO = {"base": 150, "job": 70}

    def __init__(self, processo: str = "SpiritVale"):
        import achar_barras
        import memoria

        self._achar = achar_barras
        self._memoria = memoria
        self.processo = processo
        self.proc = None
        self.base = self.job = None
        self.base_nivel = self.job_nivel = None
        self._ultimo = None

    def niveis_plausiveis(self) -> bool:
        """Nivel acima do teto do jogo significa que algo esta errado."""
        return (1 <= (self.base_nivel or 0) <= self.TETO["base"]
                and 1 <= (self.job_nivel or 0) <= self.TETO["job"])

    def definir_niveis(self, base: int, job: int) -> None:
        """Os niveis nao estao na barra (ela so guarda o preenchimento).

        Voce informa uma vez; dai em diante subir de nivel e detectado pela
        queda brusca e o numero anda sozinho.
        """
        self.base_nivel = max(1, min(int(base), self.TETO["base"]))
        self.job_nivel = max(1, min(int(job), self.TETO["job"]))

    def localizar(self, referencia: dict, tolerancia: float = 3.0) -> bool:
        """`referencia` e uma leitura de OCR, so pra desempatar os candidatos."""
        pid = self._memoria.achar_processo(self.processo)
        if not pid:
            return False
        self.proc = self._memoria.Processo(pid)
        candidatos = self._achar.achar_barras(self.proc)
        bons = [c for c in candidatos
                if abs(c["base_pct"] - referencia["base_pct"]) <= tolerancia
                and abs(c["job_pct"] - referencia["job_pct"]) <= tolerancia]
        if len(bons) != 1:
            self.fechar()
            return False
        self.base = bons[0]["base"]
        self.job = bons[0]["job"]
        self.base_nivel = referencia["base_nivel"]
        self.job_nivel = referencia["job_nivel"]
        return True

    def localizar_por_comportamento(self, segundos: float = 40.0,
                                    passo: float = 0.5, aviso=None) -> bool:
        """Acha as barras sem OCR nenhum, olhando como elas se COMPORTAM.

        A assinatura sozinha devolve ~1.600 barras de UI parecidas. O que separa
        a de XP de todas as outras e o jeito de mexer: XP so sobe, nunca desce,
        e as duas (classe e job) sobem JUNTAS quando voce mata algo. HP e MP
        oscilam pra cima e pra baixo; barra de cast zera; cooldown volta ao
        cheio. Nada disso sobrevive ao filtro.

        Precisa que voce ganhe XP durante a medicao — e o unico sinal que
        identifica a barra sem depender de ler a tela.
        """
        pid = self._memoria.achar_processo(self.processo)
        if not pid:
            return False
        self.proc = self._memoria.Processo(pid)
        vivos = self._achar.achar_barras(self.proc)
        if not vivos:
            self.fechar()
            return False

        estado = [{"c": c, "base": c["base_pct"], "job": c["job_pct"],
                   "subiu": 0} for c in vivos]
        fim = time.time() + segundos
        while time.time() < fim and len(estado) > 1:
            time.sleep(passo)
            sobrou = []
            for e in estado:
                b = self.proc.ler_float(e["c"]["base"])
                j = self.proc.ler_float(e["c"]["job"])
                if b is None or j is None:
                    continue
                b, j = b * 100, j * 100
                # queda so vale se for virada de nivel (cheio -> quase vazio)
                # folga de 0,05 ponto: o Unity ANIMA o preenchimento, entao a
                # barra passa do valor e volta. Sem isso, a propria barra certa
                # era descartada por uma oscilacao de arredondamento.
                caiu_b = b < e["base"] - 0.05 and not (e["base"] > 60 and b < 40)
                caiu_j = j < e["job"] - 0.05 and not (e["job"] > 60 and j < 40)
                if caiu_b or caiu_j:
                    continue                      # XP nao anda pra tras
                if b > e["base"] + 0.001 or j > e["job"] + 0.001:
                    e["subiu"] += 1
                e["base"], e["job"] = max(b, e["base"]), max(j, e["job"])
                sobrou.append(e)
            estado = sobrou
            if aviso:
                aviso(len(estado))

        # Entre os que nunca cairam, fica quem realmente ANDOU. Sobrar mais de
        # um e NORMAL, nao erro: o mesmo valor aparece espelhado em varios
        # enderecos (buffers de UI e de replicacao). Exigir exatamente um fazia
        # a deteccao falhar justamente quando dava certo. Fica o que mais se
        # mexeu — o espelho mais "vivo", que e o que a barra desenha.
        andaram = [e for e in estado if e["subiu"] > 0]
        if not andaram:
            self.fechar()
            return False
        andaram.sort(key=lambda e: -e["subiu"])
        escolhido = andaram[0]["c"]
        self.base, self.job = escolhido["base"], escolhido["job"]
        return True

    def ler(self) -> dict | None:
        if not self.proc:
            return None
        base = self.proc.ler_float(self.base)
        job = self.proc.ler_float(self.job)
        if base is None or job is None:
            return None
        if not (0.0 <= base <= 1.0 and 0.0 <= job <= 1.0):
            return None   # o objeto foi liberado: melhor admitir do que chutar
        base_pct, job_pct = base * 100, job * 100
        if self._ultimo:
            if (self._ultimo["base_pct"] >= self.CHEIA and base_pct <= self.VAZIA
                    and self.base_nivel < self.TETO["base"]):
                self.base_nivel += 1
            if (self._ultimo["job_pct"] >= self.CHEIA and job_pct <= self.VAZIA
                    and self.job_nivel < self.TETO["job"]):
                self.job_nivel += 1
        leitura = {"base_nivel": self.base_nivel, "base_pct": base_pct,
                   "job_nivel": self.job_nivel, "job_pct": job_pct}
        self._ultimo = leitura
        return leitura

    def fechar(self) -> None:
        if self.proc:
            self.proc.fechar()
            self.proc = None


def diagnostico() -> None:
    """Captura a barra agora e mostra o que cada estrategia enxerga.

    Uso:  .venv\\Scripts\\python.exe xp.py

    Rode com o jogo visivel, em lugares diferentes do mapa (pedra, folhagem,
    interior). Salva cada imagem processada em debug/xp/ pra dar pra VER onde
    a letra se perde, em vez de adivinhar.
    """
    from pathlib import Path

    from comum import capturar

    comum.preparar_console()
    comum.ativar_dpi()
    cfg = comum.carregar_config()
    comum.configurar_tesseract(cfg)
    if not cfg.get("xp_regiao"):
        raise SystemExit("Barra de XP nao calibrada. Rode:\n"
                         "  .venv\\Scripts\\python.exe calibrar.py --modo xp")

    pasta = Path(__file__).resolve().parent / "debug" / "xp"
    pasta.mkdir(parents=True, exist_ok=True)
    imagem = capturar(cfg["xp_regiao"])
    imagem.save(pasta / "0-original.png")
    print(f"regiao {cfg['xp_regiao']}  ->  debug/xp/0-original.png\n")

    for indice, (rotulo, numeros) in enumerate(tentativas(imagem), 1):
        if rotulo.startswith("branco"):
            partes = rotulo.split()
            opcoes = {"v_minimo": int(partes[1][3:]), "s_maximo": int(partes[2][3:]),
                      "mancha": int(partes[3].split("=")[1])}
            processada = comum.isolar_texto_branco(imagem, escala=3, **opcoes)
        else:
            processada = comum.isolar_texto_claro(
                imagem, escala=3, limiar=int(rotulo.split()[1]))
        nome = f"{indice}-{rotulo.replace(' ', '_').replace('>=','').replace('<=','')}.png"
        processada.save(pasta / nome)
        marca = "  <-- FECHOU" if len(numeros) == 4 else ""
        print(f"  {rotulo:<42} {numeros}{marca}")

    leitura = ler_barra(imagem)
    print(f"\nresultado final: {leitura if leitura else 'NAO CONSEGUI LER'}")
    print(f"imagens em: {pasta}")


if __name__ == "__main__":
    diagnostico()
