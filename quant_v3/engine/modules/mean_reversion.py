"""
Mean Reversion module — score basato su:
    1. Z-score(close, 20): distanza in stddev dalla media mobile
    2. Bollinger Bands position: dove sta il close rispetto alle bande
    3. Filtro regime via ADX: in trend forte mean-reversion è UNRELIABLE

Range output: [-1, +1]

Logica (CONTRARIAN: prezzo basso = score POSITIVO = BUY):
    - Z-score < -2.0 (estremamente sotto media)  → +1.0 (BUY mean-rev)
    - Z-score > +2.0 (estremamente sopra media)  → -1.0 (SELL mean-rev)
    - Posizione vs BB: se close < BB_lower → +0.3 boost
                       se close > BB_upper → -0.3 boost
    - Regime filter: se ADX > 30 (trend forte), score *= 0.3 (dampening)
      perché in trend forte mean-reversion non funziona

NOTE: questo modulo va in OPPOSIZIONE a trend/momentum quando il prezzo
è agli estremi. CompositeSignal gestirà la concordanza.
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
        'adx_period': 14,
        # Soglie Z-score per saturazione
        'z_strong': 2.0,
        # Soglia ADX per dampening (trend forte = MR poco affidabile)
        'adx_trend_strong': 30.0,
        'adx_dampening': 0.3,
        # Pesi blend
        'w_zscore': 0.70,
        'w_bb': 0.30,
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
        self._indicators['stddev'] = bt.ind.StdDev(
            feed.close, period=p['zscore_period']
        )
        self._indicators['adx'] = bt.ind.ADX(feed, period=p['adx_period'])

    def score(self) -> float:
        close = self.safe(self._feed.close[0])
        sma = self.safe(self._indicators['sma'][0])
        std = self.safe(self._indicators['stddev'][0])
        bb_top = self.safe(self._indicators['bb'].top[0])
        bb_bot = self.safe(self._indicators['bb'].bot[0])
        adx = self.safe(self._indicators['adx'][0])

        if close == 0 or sma == 0 or std == 0:
            return 0.0

        p = self.params

        # 1) Z-score CONTRARIAN: -z = score positivo (prezzo basso → BUY)
        z = (close - sma) / std
        # Mappa z in [-z_strong, +z_strong] → [+1, -1] (sign flipped)
        z_score = -z / p['z_strong']
        z_score = max(-1.0, min(1.0, z_score))

        # 2) Bollinger position
        bb_score = 0.0
        if bb_top > bb_bot:
            if close < bb_bot:
                bb_score = 1.0  # extremely oversold → BUY
            elif close > bb_top:
                bb_score = -1.0  # extremely overbought → SELL
            else:
                # Continua scaling: dove sta close tra bot e top → [-1, +1]
                # close == sma → 0; close == top → -1; close == bot → +1
                mid = (bb_top + bb_bot) / 2.0
                half_width = (bb_top - bb_bot) / 2.0
                if half_width > 0:
                    bb_score = -(close - mid) / half_width
                    bb_score = max(-1.0, min(1.0, bb_score))

        # Blend pesato
        total = p['w_zscore'] * z_score + p['w_bb'] * bb_score

        # 3) Regime filter: ADX alto = trend, dampening
        if adx >= p['adx_trend_strong']:
            total *= p['adx_dampening']

        return max(-1.0, min(1.0, total))
