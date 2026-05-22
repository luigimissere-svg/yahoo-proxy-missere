"""
Trend module — score basato su:
    1. Cross MA breve/lunga (golden/death cross): score base ±0.5
    2. ADX (forza trend): amplifica score se ADX > 25
    3. Slope SMA lungo periodo: bonus/malus se inclinata

Range output: [-1, +1]

Logica:
    - SMA_short > SMA_long      → +0.5  (uptrend)
    - SMA_short < SMA_long      → -0.5  (downtrend)
    - ADX > 25                  → ×1.5  (trend forte)
    - ADX < 15                  → ×0.5  (no trend, dampening)
    - Slope SMA_long positivo   → +0.2 (rinforzo)
    - Slope SMA_long negativo   → -0.2 (rinforzo opposto)
    Clip finale a [-1, +1].
"""

from __future__ import annotations

import backtrader as bt

from .base import AlphaModule


class TrendModule(AlphaModule):
    name = 'trend'

    DEFAULTS = {
        'sma_short': 50,
        'sma_long': 200,
        'adx_period': 14,
        'slope_lookback': 20,
        'adx_strong': 25.0,
        'adx_weak': 15.0,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)
        p = self.params
        self._indicators['sma_s'] = bt.ind.SMA(feed.close, period=p['sma_short'])
        self._indicators['sma_l'] = bt.ind.SMA(feed.close, period=p['sma_long'])
        self._indicators['adx'] = bt.ind.ADX(feed, period=p['adx_period'])

    def score(self) -> float:
        sma_s = self.safe(self._indicators['sma_s'][0])
        sma_l = self.safe(self._indicators['sma_l'][0])
        adx = self.safe(self._indicators['adx'][0])

        # Aspetta che gli indicatori siano "caldi"
        if sma_s == 0 or sma_l == 0:
            return 0.0

        # Base score: golden/death cross
        if sma_s > sma_l:
            base = 0.5
        elif sma_s < sma_l:
            base = -0.5
        else:
            base = 0.0

        # ADX modifier
        p = self.params
        if adx >= p['adx_strong']:
            base *= 1.5
        elif adx <= p['adx_weak']:
            base *= 0.5

        # Slope SMA_long su window slope_lookback
        try:
            slope_lb = p['slope_lookback']
            sma_l_back = self.safe(self._indicators['sma_l'][-slope_lb])
            if sma_l_back > 0:
                slope_pct = (sma_l - sma_l_back) / sma_l_back
                if slope_pct > 0.01:
                    base += 0.2
                elif slope_pct < -0.01:
                    base -= 0.2
        except IndexError:
            pass

        # Clip a [-1, +1]
        return max(-1.0, min(1.0, base))
