"""
Event-driven module — earnings ±N giorni + dividend ex-date.

Usa le linee custom del PatrimonioFeed:
    - earnings_flag (1 se ±earnings_window giorni da earnings)
    - earnings_surprise (% surprise dell'ultimo earnings recente)
    - days_to_earnings (giorni al prossimo, ≤30)
    - dividend (importo dividendo del giorno)

Logica base:
    - Avvicinamento earnings (3-7gg prima): score POSITIVO se surprise storico positivo,
      NEGATIVO se negativo (momentum post-earnings).
    - Post-earnings (1-3gg dopo): se surprise corrente > +5% → +0.6 (PEAD), se < -5% → -0.6
    - Dividend ex-date: leggero negativo il giorno (price drop tecnico), ignora il modulo

Range output: [-1, +1]
"""

from __future__ import annotations

import backtrader as bt

from .base import AlphaModule


class EventDrivenModule(AlphaModule):
    name = 'event_driven'

    DEFAULTS = {
        'pead_pos_threshold': 5.0,    # surprise > 5% → PEAD positivo
        'pead_neg_threshold': -5.0,
        'pre_earnings_min_days': 3,
        'pre_earnings_max_days': 7,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})

    def prepare(self, feed):
        super().prepare(feed)
        # Le linee custom sono già nel feed (PatrimonioFeed)
        # Niente bt.ind necessari

    def score(self) -> float:
        f = self._feed
        if f is None:
            return 0.0

        try:
            flag = self.safe(f.earnings_flag[0], 0.0)
            surprise = self.safe(f.earnings_surprise[0], 0.0)
            days_to = self.safe(f.days_to_earnings[0], 99.0)
        except (AttributeError, IndexError):
            return 0.0

        if flag != 1 or surprise == 0.0:
            return 0.0

        p = self.params
        # Pre-earnings: usa surprise STORICO (proxy: stessa surprise propagata indietro)
        if p['pre_earnings_min_days'] <= days_to <= p['pre_earnings_max_days']:
            if surprise > p['pead_pos_threshold']:
                return 0.4
            elif surprise < p['pead_neg_threshold']:
                return -0.4

        # Post-earnings (PEAD)
        if days_to <= 0 or days_to > p['pre_earnings_max_days']:
            if surprise > p['pead_pos_threshold']:
                return 0.6
            elif surprise < p['pead_neg_threshold']:
                return -0.6

        return 0.0
