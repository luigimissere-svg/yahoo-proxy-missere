"""
Mean Reversion module — Bollinger Bands + Z-score (skeleton).

TODO Fase 2.3: implementare logica completa.
"""

from __future__ import annotations

import backtrader as bt

from .base import AlphaModule


class MeanReversionModule(AlphaModule):
    name = 'mean_reversion'

    DEFAULTS = {
        'bb_period': 20,
        'bb_devfactor': 2.0,
        'zscore_period': 20,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)
        p = self.params
        self._indicators['bb'] = bt.ind.BollingerBands(
            feed.close, period=p['bb_period'], devfactor=p['bb_devfactor']
        )
        self._indicators['sma'] = bt.ind.SMA(feed.close, period=p['zscore_period'])
        self._indicators['stddev'] = bt.ind.StdDev(feed.close, period=p['zscore_period'])

    def score(self) -> float:
        return 0.0
