"""
Value module — score basato su fundamentals (P/E, P/B, FCF yield).

Range output: [-1, +1]

Logica (CONTRARIAN: undervalued = score POSITIVO = BUY):
    - P/E trailing:
        * P/E < 10 (deep value)        →  +1.0
        * P/E in [10, 25] (fair)       →  +1 → -1 lineare
        * P/E > 30 (overvalued)        →  -1.0
        * P/E ≤ 0 o NaN                →   0.0 (neutro, no info)
    - P/B:
        * P/B < 1.0 (book discount)    →  +0.7
        * P/B in [1, 4]                →  scaling lineare
        * P/B > 4.0                    →  -0.7
    - FCF yield (FCF / market cap):
        * yield > 7%                   →  +1.0
        * yield in [0%, 7%]            →  lineare
        * yield < 0%                   →  -1.0
    - Blend pesato: 0.40 P/E + 0.30 P/B + 0.30 FCF yield

NOTA: se i fundamentals non sono disponibili (parquet mancante),
il modulo ritorna 0.0 (neutro) e il composite si appoggia sugli altri.
"""

from __future__ import annotations

from .base import AlphaModule
from ._fundamentals import get_fundamentals, safe_float


class ValueModule(AlphaModule):
    name = 'value'

    DEFAULTS = {
        'pe_low': 10.0,
        'pe_mid': 25.0,
        'pe_high': 30.0,
        'pb_low': 1.0,
        'pb_high': 4.0,
        'fcf_yield_target': 0.07,
        'w_pe': 0.40,
        'w_pb': 0.30,
        'w_fcf': 0.30,
    }

    def __init__(self, **params):
        super().__init__(**{**self.DEFAULTS, **params})
        self._fund: dict | None = None
        self._cached_score: float | None = None

    def prepare(self, feed):
        super().prepare(feed)
        ticker = getattr(feed, '_name', None) or str(feed)
        self._fund = get_fundamentals(ticker)
        # Score statico: pre-computato una volta sola
        self._cached_score = self._compute_score()

    def _compute_score(self) -> float:
        """Compute score from fundamentals snapshot. 0.0 if missing."""
        if not self._fund:
            return 0.0

        p = self.params
        pe = safe_float(self._fund.get('pe_trailing'))
        pb = safe_float(self._fund.get('pb'))
        fcfy = safe_float(self._fund.get('fcf_yield'))

        # 1) P/E score
        if pe != pe or pe <= 0:  # NaN check (NaN != NaN)
            pe_score = 0.0
        elif pe <= p['pe_low']:
            pe_score = 1.0
        elif pe >= p['pe_high']:
            pe_score = -1.0
        else:
            # Lineare tra pe_low e pe_high → +1 a -1
            pe_score = 1.0 - 2.0 * (pe - p['pe_low']) / (p['pe_high'] - p['pe_low'])
            pe_score = max(-1.0, min(1.0, pe_score))

        # 2) P/B score
        if pb != pb or pb <= 0:
            pb_score = 0.0
        elif pb <= p['pb_low']:
            pb_score = 0.7
        elif pb >= p['pb_high']:
            pb_score = -0.7
        else:
            pb_score = 0.7 - 1.4 * (pb - p['pb_low']) / (p['pb_high'] - p['pb_low'])
            pb_score = max(-0.7, min(0.7, pb_score))

        # 3) FCF yield score
        if fcfy != fcfy:
            fcf_score = 0.0
        elif fcfy < 0:
            fcf_score = -1.0
        elif fcfy >= p['fcf_yield_target']:
            fcf_score = 1.0
        else:
            fcf_score = fcfy / p['fcf_yield_target']
            fcf_score = max(0.0, min(1.0, fcf_score))

        total = (
            p['w_pe'] * pe_score
            + p['w_pb'] * pb_score
            + p['w_fcf'] * fcf_score
        )
        return max(-1.0, min(1.0, total))

    def score(self) -> float:
        if self._cached_score is None:
            return 0.0
        return self._cached_score
