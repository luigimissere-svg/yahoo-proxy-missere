"""
Momentum module — score basato su:
    1. RSI(14): score base da deviazione vs 50
    2. MACD histogram: conferma direzionale
    3. ROC(21): forza di tendenza percentuale

Range output: [-1, +1]

Logica:
    - RSI score: mappato linearmente (RSI - 50) / 30, clip [-1, +1]
        * RSI < 30 (oversold)  → score < -0.66 (segnale BUY mean-rev,
          MA QUI: momentum tradizionale dice "trend al ribasso, attenzione")
        * RSI > 70 (overbought) → score > +0.66 (momentum forte)
        * Per momentum classico: alto = bullish, basso = bearish
    - MACD histogram: sign(hist) * min(|hist|/atr_proxy, 1) → bonus direzionale
    - ROC(21): se > +5% → +0.3 boost, se < -5% → -0.3
    - Blend pesato: 0.50 * rsi_score + 0.30 * macd_score + 0.20 * roc_score
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
        # Soglie ROC per boost
        'roc_strong_pos': 5.0,
        'roc_strong_neg': -5.0,
        # Pesi blend
        'w_rsi': 0.50,
        'w_macd': 0.30,
        'w_roc': 0.20,
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
        # ATR per normalizzazione MACD histogram (scala invariante)
        self._indicators['atr'] = bt.ind.ATR(feed, period=14)

    def score(self) -> float:
        rsi = self.safe(self._indicators['rsi'][0])
        macd_line = self.safe(self._indicators['macd'].macd[0])
        macd_signal = self.safe(self._indicators['macd'].signal[0])
        roc = self.safe(self._indicators['roc'][0])
        atr = self.safe(self._indicators['atr'][0])
        close = self.safe(self._feed.close[0])

        # Aspetta indicatori caldi
        if rsi == 0 or close == 0:
            return 0.0

        p = self.params

        # 1) RSI score: mappa (RSI - 50) / 30 → range tipico [-1.67, +1.67] poi clip
        rsi_score = (rsi - 50.0) / 30.0
        rsi_score = max(-1.0, min(1.0, rsi_score))

        # 2) MACD histogram score: (macd - signal) normalizzato per ATR
        # Se ATR non pronto, salto contributo MACD
        macd_hist = macd_line - macd_signal
        if atr > 0:
            # hist normalizzato come % di ATR; tipicamente |hist|/atr ∈ [0, 0.5]
            macd_norm = macd_hist / atr
            macd_score = max(-1.0, min(1.0, macd_norm * 2.0))
        else:
            macd_score = 0.0

        # 3) ROC score: rapporto vs soglia
        if roc >= p['roc_strong_pos']:
            roc_score = 1.0
        elif roc <= p['roc_strong_neg']:
            roc_score = -1.0
        else:
            # Linear scaling tra -5% e +5%
            roc_score = roc / p['roc_strong_pos']
            roc_score = max(-1.0, min(1.0, roc_score))

        # Blend pesato
        total = (
            p['w_rsi'] * rsi_score
            + p['w_macd'] * macd_score
            + p['w_roc'] * roc_score
        )

        return max(-1.0, min(1.0, total))
