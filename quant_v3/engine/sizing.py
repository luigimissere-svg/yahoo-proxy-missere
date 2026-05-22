"""
Position sizing — Fase 3.1.

Trasforma un segnale (composite > 0) + una stima di volatilità in un numero
di azioni da comprare, in modo che ogni posizione contribuisca con un
rischio target comparabile (vol-targeted risk parity per single ticker).

Formula vol-target (Kelly-like, semplificata):

    target_risk_eur   = target_risk_pct × NAV
    risk_per_share    = vol_proxy_eur   (es. ATR(14) in valuta)
    raw_shares        = target_risk_eur / risk_per_share
    capped_shares     = min(raw_shares, per_ticker_cap × NAV / price)
    final_shares      = capped_shares  (se notional ≥ min_position_pct × NAV)

dove vol_proxy è una di:
    - 'atr':       ATR(14) in valuta della price (giornaliero)
    - 'realized':  realized vol 21d × price (annualizzata × √(1/252))

Caps:
    - per_ticker_cap (% NAV)        → hard upper cap
    - min_position_pct (% NAV)      → notional floor, sotto skip
    - vol_floor_pct (% prezzo)      → vol minima per evitare leverage esplosivo
                                       su asset ultra-piatti

Backward compatibility:
    'equal' → comportamento legacy (per_ticker_cap × NAV / price)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


SizingMethod = Literal['equal', 'vol_target']
VolProxy = Literal['atr', 'realized']


@dataclass
class PositionSizer:
    """
    Sizing engine — usato da PatrimonioStrategy._size_for().

    Attributes:
        method: 'equal' (legacy) o 'vol_target'.
        target_risk_pct: rischio target per trade (es. 0.01 = 1% NAV).
        per_ticker_cap: cap superiore notional come % NAV (es. 0.10 = 10%).
        min_position_pct: notional minimo per emettere trade (es. 0.005 = 0.5% NAV).
        vol_floor_pct: vol_proxy minima come % prezzo (es. 0.005 = 0.5%) per evitare
                       sizing esplosivo su asset ultra-piatti.
        vol_proxy: 'atr' o 'realized' (solo se method='vol_target').
    """
    method: SizingMethod = 'vol_target'
    target_risk_pct: float = 0.01
    per_ticker_cap: float = 0.10
    min_position_pct: float = 0.005
    vol_floor_pct: float = 0.005
    vol_proxy: VolProxy = 'atr'

    def __post_init__(self):
        if self.method not in ('equal', 'vol_target'):
            raise ValueError(f"method must be 'equal' or 'vol_target', got {self.method}")
        if self.vol_proxy not in ('atr', 'realized'):
            raise ValueError(f"vol_proxy must be 'atr' or 'realized', got {self.vol_proxy}")
        for name, v in (
            ('target_risk_pct', self.target_risk_pct),
            ('per_ticker_cap', self.per_ticker_cap),
            ('min_position_pct', self.min_position_pct),
            ('vol_floor_pct', self.vol_floor_pct),
        ):
            if v < 0 or v > 1:
                raise ValueError(f"{name} must be in [0,1], got {v}")
        if self.min_position_pct > self.per_ticker_cap:
            raise ValueError(
                f"min_position_pct ({self.min_position_pct}) > per_ticker_cap "
                f"({self.per_ticker_cap}) — impossibile soddisfare entrambi"
            )

    # ── Public API ───────────────────────────────────────────────────────

    def size(
        self,
        nav: float,
        cash: float,
        price: float,
        vol_eur: float | None = None,
    ) -> int:
        """
        Ritorna numero intero di azioni da comprare.

        Args:
            nav: total portfolio value (cash + holdings).
            cash: available cash.
            price: prezzo corrente del ticker.
            vol_eur: stima di rischio per share in valuta (es. ATR in EUR).
                     Required se method='vol_target', ignorato se 'equal'.

        Returns:
            n_shares (int). 0 se nessun trade fattibile (cash insufficiente,
            sotto floor, o input degeneri).
        """
        # Guard rails
        if nav <= 0 or cash <= 0 or price <= 0:
            return 0

        # Hard cap notional
        cap_notional = self.per_ticker_cap * nav
        cap_shares = int(cap_notional / price)
        if cap_shares <= 0:
            return 0

        # Cash limit
        cash_shares = int(cash / price)
        if cash_shares <= 0:
            return 0

        if self.method == 'equal':
            raw_shares = min(cap_shares, cash_shares)
        else:
            # vol_target
            if vol_eur is None or not np.isfinite(vol_eur) or vol_eur <= 0:
                # Fallback: usa cap (no info su vol → comportamento legacy)
                raw_shares = min(cap_shares, cash_shares)
            else:
                # Applica vol floor (in valuta) — vol_floor_pct è % del prezzo
                vol_floor_eur = self.vol_floor_pct * price
                vol_eur_eff = max(vol_eur, vol_floor_eur)

                target_risk_eur = self.target_risk_pct * nav
                vol_shares = int(target_risk_eur / vol_eur_eff)
                raw_shares = min(vol_shares, cap_shares, cash_shares)

        # Notional floor — se sotto soglia minima, salta trade
        notional = raw_shares * price
        if notional < self.min_position_pct * nav:
            return 0

        return max(0, raw_shares)

    def diagnose(
        self,
        nav: float,
        cash: float,
        price: float,
        vol_eur: float | None = None,
    ) -> dict:
        """Ritorna breakdown del calcolo per debug/logging."""
        out = {
            'method': self.method, 'nav': nav, 'cash': cash, 'price': price,
            'vol_eur': vol_eur, 'vol_proxy': self.vol_proxy,
        }
        if nav <= 0 or cash <= 0 or price <= 0:
            out.update(shares=0, reason='degenerate_inputs')
            return out

        cap_shares = int(self.per_ticker_cap * nav / price)
        cash_shares = int(cash / price)
        out['cap_shares'] = cap_shares
        out['cash_shares'] = cash_shares

        if self.method == 'equal' or vol_eur is None or vol_eur <= 0:
            raw = min(cap_shares, cash_shares)
            out['vol_shares'] = None
            out['effective_method'] = 'equal_fallback' if (
                self.method == 'vol_target' and (vol_eur is None or vol_eur <= 0)
            ) else self.method
        else:
            vol_floor_eur = self.vol_floor_pct * price
            vol_eur_eff = max(vol_eur, vol_floor_eur)
            out['vol_eur_effective'] = vol_eur_eff
            out['vol_floored'] = vol_eur < vol_floor_eur
            target_risk_eur = self.target_risk_pct * nav
            vol_shares = int(target_risk_eur / vol_eur_eff)
            raw = min(vol_shares, cap_shares, cash_shares)
            out['vol_shares'] = vol_shares
            out['effective_method'] = 'vol_target'

        notional = raw * price
        floor_eur = self.min_position_pct * nav
        out['raw_shares'] = raw
        out['notional'] = notional
        out['notional_floor'] = floor_eur
        if notional < floor_eur:
            out['shares'] = 0
            out['reason'] = 'below_min_position'
        else:
            out['shares'] = max(0, raw)
            out['reason'] = 'ok'
        return out


# ─── Helpers per stima volatilità realized (alternativa ad ATR) ─────────────

def realized_vol_to_eur(price: float, daily_returns: np.ndarray) -> float:
    """
    Stima daily vol in valuta da array di rendimenti giornalieri.

        sigma_daily_pct = std(rets)
        sigma_eur       = sigma_daily_pct × price

    Usato come alternativa ad ATR quando vol_proxy='realized'.
    Richiede >= 5 osservazioni, altrimenti ritorna NaN.
    """
    if daily_returns is None or len(daily_returns) < 5:
        return float('nan')
    arr = np.asarray(daily_returns, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 5:
        return float('nan')
    sigma_pct = float(np.std(arr, ddof=1))
    return sigma_pct * price
