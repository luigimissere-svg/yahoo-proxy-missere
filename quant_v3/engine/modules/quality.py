"""
Quality module — ROE + Debt/Equity (skeleton).

Vedi note in value.py: serviranno fundamentals.
"""

from __future__ import annotations

from .base import AlphaModule


class QualityModule(AlphaModule):
    name = 'quality'

    DEFAULTS = {
        'roe_min': 0.10,
        'de_max': 1.5,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)

    def score(self) -> float:
        return 0.0
