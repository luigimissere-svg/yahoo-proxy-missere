"""
S1.3 — Bug 8 isolamento outlier MU
Single-ticker exposure cap 5% per fold + winsorization PnL extremes.

Pre-registrazione: preregistration_s1_v8.md §S1.3
Falsificazione F2: se cap 5% cambia P&L del fold < 5% in valore assoluto,
                  Bug 8 marginale (cap mantenuto come precauzione).

Doppio meccanismo:
  (a) exposure_cap_notional: limita notional per ticker a NOTIONAL_CAP_PCT
      del capitale di fold (default 5%). Implica MIN 20 ticker per fold
      se distribuito uniformemente.
  (b) pnl_winsor_per_trade: limita PnL_pct di un singolo trade al
      percentile WINSOR_PCTILE della distribuzione storica di PnL_pct
      sui trade chiusi del fold di training (no look-ahead).

Sealed parameters:
  NOTIONAL_CAP_PCT = 0.05  (5%)
  WINSOR_PCTILE = 95       (P95 della distribuzione train)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


# --- Parametri sigillati S1.3 -------------------------------------------------

NOTIONAL_CAP_PCT: float = 0.05
WINSOR_PCTILE: float = 95.0
SEALED_VERSION: str = "v8.s1.3"


# --- Strutture dati -----------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    """Singolo trade post-execution."""

    ticker: str
    notional_open: float
    pnl_gross: float

    @property
    def pnl_pct(self) -> float:
        if self.notional_open == 0:
            return 0.0
        return self.pnl_gross / self.notional_open * 100.0


@dataclass(frozen=True)
class CapResult:
    """Risultato applicazione cap su un trade."""

    ticker: str
    notional_orig: float
    notional_capped: float
    pnl_orig: float
    pnl_capped: float
    scale_notional: float
    winsor_applied: bool
    pnl_pct_orig: float
    pnl_pct_capped: float


# --- Regola operativa ---------------------------------------------------------


def apply_notional_cap(
    trades: Sequence[Trade],
    fold_capital: float,
    cap_pct: float = NOTIONAL_CAP_PCT,
) -> list[CapResult]:
    """Cap notional per ticker: nessun trade può avere notional > cap_pct * fold_capital.
    PnL viene scalato linearmente (stesso entry, size ridotta).
    """
    cap_notional = fold_capital * cap_pct
    out: list[CapResult] = []
    for t in trades:
        if t.notional_open > cap_notional:
            scale = cap_notional / t.notional_open
            new_notional = cap_notional
            new_pnl = t.pnl_gross * scale
        else:
            scale = 1.0
            new_notional = t.notional_open
            new_pnl = t.pnl_gross
        out.append(
            CapResult(
                ticker=t.ticker,
                notional_orig=t.notional_open,
                notional_capped=new_notional,
                pnl_orig=t.pnl_gross,
                pnl_capped=new_pnl,
                scale_notional=scale,
                winsor_applied=False,
                pnl_pct_orig=t.pnl_pct,
                pnl_pct_capped=(new_pnl / new_notional * 100.0) if new_notional else 0.0,
            )
        )
    return out


def apply_winsor_pnl_pct(
    capped: Sequence[CapResult],
    train_pnl_pct: Sequence[float],
    pctile: float = WINSOR_PCTILE,
) -> list[CapResult]:
    """Winsorizza PnL_pct per trade al P{pctile} della distribuzione train (no look-ahead).
    Richiede che la distribuzione train sia stata calcolata SOLO su trade
    pre-OOS-window (responsabilità del chiamante).
    """
    if len(train_pnl_pct) < 5:
        # distribuzione troppo piccola → no winsor
        return list(capped)

    upper = float(np.percentile(train_pnl_pct, pctile))
    lower = float(np.percentile(train_pnl_pct, 100.0 - pctile))

    out: list[CapResult] = []
    for r in capped:
        if r.pnl_pct_capped > upper:
            new_pct = upper
            new_pnl = r.notional_capped * new_pct / 100.0
            winsor = True
        elif r.pnl_pct_capped < lower:
            new_pct = lower
            new_pnl = r.notional_capped * new_pct / 100.0
            winsor = True
        else:
            new_pct = r.pnl_pct_capped
            new_pnl = r.pnl_capped
            winsor = False
        out.append(
            CapResult(
                ticker=r.ticker,
                notional_orig=r.notional_orig,
                notional_capped=r.notional_capped,
                pnl_orig=r.pnl_orig,
                pnl_capped=new_pnl,
                scale_notional=r.scale_notional,
                winsor_applied=winsor,
                pnl_pct_orig=r.pnl_pct_orig,
                pnl_pct_capped=new_pct,
            )
        )
    return out


def isolate_outliers(
    trades: Sequence[Trade],
    fold_capital: float,
    train_pnl_pct: Sequence[float] | None = None,
    cap_pct: float = NOTIONAL_CAP_PCT,
    winsor_pctile: float = WINSOR_PCTILE,
) -> list[CapResult]:
    """Pipeline completa: (a) exposure cap + (b) winsor PnL%.
    Se train_pnl_pct è None o vuoto, applica solo (a).
    """
    capped = apply_notional_cap(trades, fold_capital, cap_pct)
    if train_pnl_pct:
        capped = apply_winsor_pnl_pct(capped, train_pnl_pct, winsor_pctile)
    return capped


# --- Falsificazione F2 -------------------------------------------------------


def f2_falsification(
    delta_pnl_pct: float, threshold_pct: float = 5.0
) -> tuple[bool, str]:
    """Pre-reg S1.3 falsification F2:
    Se |delta P&L fold con cap vs senza| < threshold_pct → Bug 8 marginale.
    Ritorna (is_marginal, motivazione).
    """
    abs_delta = abs(delta_pnl_pct)
    if abs_delta < threshold_pct:
        return True, (
            f"Bug 8 marginale: |Delta P&L| = {abs_delta:.2f}% < {threshold_pct:.1f}%. "
            "Cap mantenuto come precauzione metodologica."
        )
    return False, (
        f"Bug 8 NON marginale: |Delta P&L| = {abs_delta:.2f}% >= {threshold_pct:.1f}%. "
        "Cap necessario per stabilità del fold."
    )


__all__ = [
    "Trade",
    "CapResult",
    "NOTIONAL_CAP_PCT",
    "WINSOR_PCTILE",
    "SEALED_VERSION",
    "apply_notional_cap",
    "apply_winsor_pnl_pct",
    "isolate_outliers",
    "f2_falsification",
]
