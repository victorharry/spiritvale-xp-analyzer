"""Medidor de ritmo de XP: quanto entrou, a que velocidade, quanto falta.

Os numeros ja chegam prontos da rede (ver captura.py) — este modulo so calcula
o ritmo e a estimativa em cima deles.

A estimativa usa uma JANELA recente, nao a sessao inteira: se voce parou dez
minutos pra vender, a media da sessao mentiria pra baixo e o "falta" nunca
convergiria.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


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
