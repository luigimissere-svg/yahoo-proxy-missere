"""
Base class per tutti i moduli alpha.

Ogni modulo è un'oggetto con due metodi:
    - prepare(feed): istanzia indicatori backtrader sul feed
    - score(idx=0): ritorna float in [-1, +1] per la barra corrente

Convenzione:
    - score positivo  → segnale BUY (long)
    - score negativo  → segnale SELL (short / exit)
    - score 0 / NaN   → neutro (no signal)

I moduli NON prendono decisioni (no buy/sell), solo segnali.
La decisione finale è di PatrimonioStrategy via CompositeSignal.
"""

from __future__ import annotations

import math
from typing import Optional

import backtrader as bt


class AlphaModule:
    """Classe base. Ogni modulo concreto la estende."""

    name: str = 'base'

    def __init__(self, **params):
        self.params = params
        self._indicators = {}
        self._feed = None

    def prepare(self, feed: bt.feeds.PandasData) -> None:
        """Chiamato una volta per feed. Istanzia indicatori (bt.ind.*)."""
        self._feed = feed

    def score(self) -> float:
        """
        Score per la barra CORRENTE del feed.
        Default: 0.0 (neutro). Sottoclassi override.
        """
        return 0.0

    def safe(self, value, default: float = 0.0) -> float:
        """Helper: gestisce NaN/None/inf."""
        if value is None:
            return default
        try:
            v = float(value)
            if math.isnan(v) or math.isinf(v):
                return default
            return v
        except (TypeError, ValueError):
            return default
