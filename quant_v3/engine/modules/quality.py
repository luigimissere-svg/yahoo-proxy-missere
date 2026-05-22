"""
Quality module — score basato su fundamentals (ROE, profit margin, D/E).

Range output: [-1, +1]

Logica:
    - ROE (Return on Equity):
        * ROE > 20%                    →  +1.0
        * ROE in [10%, 20%]            →  scaling lineare
        * ROE in [0%, 10%]             →  scaling lineare → 0
        * ROE < 0%                     →  -1.0
    - Profit margin (net):
        * margin > 15%                 →  +1.0
        * margin in [5%, 15%]          →  lineare
        * margin in [0%, 5%]           →  lineare → 0
        * margin < 0% (loss-making)    →  -1.0
    - Debt/Equity:
        * D/E < 50 (low leverage)      →  +0.7
        * D/E in [50, 200]             →  lineare
        * D/E > 200 (high leverage)    →  -0.7
    - Blend: 0.40 ROE + 0.40 margin + 0.20 D/E

NOTA: D/E in yfinance è in % (es. 150 = 1.5x equity).

Se i fundamentals non sono disponibili → 0.0 (neutro).
"""

from __future__ import annotations

from .base import AlphaModule
from ._fundamentals import get_fundamentals, safe_float


class QualityModule(AlphaModule):
    name = 'quality'

    DEFAULTS = {
        'roe_excellent': 0.20,
        'roe_good': 0.10,
        'margin_excellent': 0.15,
        'margin_good': 0.05,
        'de_low': 50.0,
        'de_high': 200.0,
        'w_roe': 0.40,
        'w_margin': 0.40,
        'w_de': 0.20,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})
        self._fund: dict | None = None
        self._cached_score: float | None = None

    def prepare(self, feed):
        super().prepare(feed)
        ticker = getattr(feed, '_name', None) or str(feed)
        self._fund = get_fundamentals(ticker)
        self._cached_score = self._compute_score()

    def _compute_score(self) -> float:
        if not self._fund:
            return 0.0

        p = self.params
        roe = safe_float(self._fund.get('roe'))
        margin = safe_float(self._fund.get('profit_margin'))
        de = safe_float(self._fund.get('debt_equity'))

        # 1) ROE
        if roe != roe:
            roe_score = 0.0
        elif roe < 0:
            roe_score = -1.0
        elif roe >= p['roe_excellent']:
            roe_score = 1.0
        elif roe >= p['roe_good']:
            roe_score = (roe - p['roe_good']) / (p['roe_excellent'] - p['roe_good'])
        else:
            roe_score = roe / p['roe_good']  # 0..1 scaling
            roe_score = max(0.0, min(1.0, roe_score))

        # 2) Profit margin
        if margin != margin:
            margin_score = 0.0
        elif margin < 0:
            margin_score = -1.0
        elif margin >= p['margin_excellent']:
            margin_score = 1.0
        elif margin >= p['margin_good']:
            margin_score = (margin - p['margin_good']) / (p['margin_excellent'] - p['margin_good'])
        else:
            margin_score = margin / p['margin_good']
            margin_score = max(0.0, min(1.0, margin_score))

        # 3) Debt/Equity (basso = buono)
        if de != de or de < 0:
            de_score = 0.0
        elif de <= p['de_low']:
            de_score = 0.7
        elif de >= p['de_high']:
            de_score = -0.7
        else:
            # Lineare da 0.7 a -0.7
            de_score = 0.7 - 1.4 * (de - p['de_low']) / (p['de_high'] - p['de_low'])
            de_score = max(-0.7, min(0.7, de_score))

        total = (
            p['w_roe'] * roe_score
            + p['w_margin'] * margin_score
            + p['w_de'] * de_score
        )
        return max(-1.0, min(1.0, total))

    def score(self) -> float:
        if self._cached_score is None:
            return 0.0
        return self._cached_score
