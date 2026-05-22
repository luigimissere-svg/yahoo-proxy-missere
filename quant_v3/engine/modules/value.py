"""
Value module — P/E + P/B filter (skeleton).

NOTA: il data lake attuale non ha fundamentals (P/E, P/B).
Per Fase 2.3 si aggiungerà uno snapshot fundamentals (corporate/<ticker>_fundamentals.parquet).
Per ora ritorna 0.0 (neutro).
"""

from __future__ import annotations

from .base import AlphaModule


class ValueModule(AlphaModule):
    name = 'value'

    DEFAULTS = {
        'pe_low': 10.0,
        'pe_high': 30.0,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)

    def score(self) -> float:
        return 0.0
