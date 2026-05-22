"""
Momentum module — RSI + MACD + ROC (skeleton).

TODO Fase 2.3: implementare logica completa.
"""

from __future__ import annotations

import backtrader as bt

from .base import AlphaModule


class MomentumModule(AlphaModule):
    name = 'momentum'

    DEFAULTS = {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'roc_period': 21,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)
        p = self.params
        self._indicators['rsi'] = bt.ind.RSI(feed.close, period=p['rsi_period'])
        self._indicators['macd'] = bt.ind.MACD(
            feed.close,
            period_me1=p['macd_fast'],
            period_me2=p['macd_slow'],
            period_signal=p['macd_signal'],
        )
        self._indicators['roc'] = bt.ind.ROC(feed.close, period=p['roc_period'])

    def score(self) -> float:
        # TODO 2.3: implementare blending RSI/MACD/ROC
        return 0.0
