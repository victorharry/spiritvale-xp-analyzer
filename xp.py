"""XP rate meter: how much came in, how fast, how much is left.

Os numeros ja chegam prontos da rede (ver capture.py) — este modulo so calcula
the rate and the estimate on top of them.

The estimate uses a recent WINDOW, not the whole session: if you stopped
for ten minutes to sell, the session average would lie low and the
convergiria.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def format_time(seconds: float | None) -> str:
    if seconds is None or seconds <= 0 or seconds != seconds:  # NaN
        return "—"
    if seconds > 99 * 3600:
        return "> 99h"
    hours, resto = divmod(int(seconds), 3600)
    minutes, segs = divmod(resto, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {segs:02d}s"
    return f"{segs}s"


@dataclass
class Tracker:
    """Guarda as leituras e responde ritmo e tempo restante.

    `progress` lineariza level + porcentagem (level 111 a 6,8% vira 11106,8),
    so levelling up does not read as a 100%-to-0% drop.
    """

    window_minutes: float = 15.0
    amostras: list[tuple[float, float, float]] = field(default_factory=list)
    # history da session inteira, pro grafico — as amostras acima sao podadas
    # in the recent window, so they cannot draw the whole curve
    history: list[tuple[float, float, float]] = field(default_factory=list)
    limite_historico: int = 3000
    start: float | None = None
    primeira: dict | None = None
    ultima: dict | None = None

    @staticmethod
    def progress(level: int, pct: float) -> float:
        return level * 100.0 + pct

    # a jump bigger than this (in % of a level) is not progress: it is a
    IMPOSSIBLE_JUMP = 150.0

    def record(self, reading: dict, agora: float | None = None) -> None:
        agora = time.time() if agora is None else agora

        # O level vem de UMA reading de tela, e o OCR erra (ja leu "17" no lugar
        # de "71"). Quando ele se corrige, o progress linearizado da um salto de
        # dezenas de niveis e o ritmo vai pra casa dos milhares de %/h. Salto
        # assim nao e XP ganho: e a reading consertada. Recomeca a tally.
        if self.ultima:
            for chave_n, chave_p in (("base_nivel", "base_pct"),
                                     ("job_nivel", "job_pct")):
                antes = self.progress(self.ultima[chave_n], self.ultima[chave_p])
                agora_prog = self.progress(reading[chave_n], reading[chave_p])
                if abs(agora_prog - antes) > self.IMPOSSIBLE_JUMP:
                    self.amostras.clear()
                    self.history.clear()
                    self.start = None
                    self.primeira = None
                    break

        if self.start is None:
            self.start = agora
            self.primeira = dict(reading)
        self.ultima = dict(reading)
        ponto = (
            agora,
            self.progress(reading["base_nivel"], reading["base_pct"]),
            self.progress(reading["job_nivel"], reading["job_pct"]),
        )
        self.amostras.append(ponto)
        self.history.append(ponto)
        if len(self.history) > self.limite_historico:
            # descarta um sim, um nao: mantem a forma da curva inteira
            self.history = self.history[::2]
        self._prune(agora)

    def _prune(self, agora: float) -> None:
        limit = agora - self.window_minutes * 60
        # mantem sempre pelo menos duas amostras pra rate nao sumir
        while len(self.amostras) > 2 and self.amostras[0][0] < limit:
            self.amostras.pop(0)

    def rate(self, qual: str = "base") -> float | None:
        """Percent per hour over the recent window. None if it is too early."""
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
        """Seconds to the next level. None while the rate cannot carry it."""
        rate = self.rate(qual)
        falta = self.falta(qual)
        if not rate or falta is None:
            return None
        return falta / rate * 3600

    def total_gain(self, qual: str = "base") -> float | None:
        """How far it moved since the meter opened, in percent of a level."""
        if not (self.primeira and self.ultima):
            return None
        chave_n = "base_nivel" if qual == "base" else "job_nivel"
        chave_p = "base_pct" if qual == "base" else "job_pct"
        return (self.progress(self.ultima[chave_n], self.ultima[chave_p])
                - self.progress(self.primeira[chave_n], self.primeira[chave_p]))

    def elapsed(self) -> float:
        if self.start is None or not self.amostras:
            return 0.0
        return self.amostras[-1][0] - self.start


@dataclass
class GoldTracker:
    """How much gold came in this session, and how fast.

    Only RISES count. Gold is the one number here that can go down, and it goes
    down for reasons that have nothing to do with farming: repairing, buying
    potions, one visit to a vendor. Counting the drops would let a single
    shopping trip erase an hour of earnings, or worse, report a negative rate
    while the player is standing on a pile of loot.

    So `gained` is the sum of the positive steps, and `total` is simply the
    latest reading. They answer different questions and both are worth showing:
    one is what this session produced, the other is what is in the pocket.
    """

    window_minutes: float = 15.0
    gained: int = 0
    total: int | None = None
    _previous: int | None = None
    amostras: list[tuple[float, int]] = field(default_factory=list)
    start: float | None = None

    def record(self, coins: int, agora: float | None = None) -> None:
        agora = time.time() if agora is None else agora
        if self._previous is not None and coins > self._previous:
            self.gained += coins - self._previous
        self._previous = coins
        self.total = coins
        if self.start is None:
            self.start = agora
        self.amostras.append((agora, self.gained))
        limit = agora - self.window_minutes * 60
        while len(self.amostras) > 2 and self.amostras[0][0] < limit:
            self.amostras.pop(0)

    def rate(self) -> float | None:
        """Gold per hour over the recent window. None while it is too early."""
        if len(self.amostras) < 2:
            return None
        span = self.amostras[-1][0] - self.amostras[0][0]
        if span < 30:                     # under 30s says nothing
            return None
        entrou = self.amostras[-1][1] - self.amostras[0][1]
        return max(0.0, entrou / span * 3600)


def format_gold(value: float | int | None) -> str:
    """Gold is a big number in a small window: 1,174,612 becomes 1.17M."""
    if value is None:
        return "—"
    value = float(value)
    sinal = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sinal}{value / 1_000_000:.2f}M"
    if value >= 10_000:
        return f"{sinal}{value / 1000:.1f}k"
    return f"{sinal}{int(value):,}"
