"""Test PositionSizer — Fase 3.1."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math
import numpy as np
import pytest

from engine.sizing import PositionSizer, realized_vol_to_eur


# ─── Validation ──────────────────────────────────────────────────────────────

def test_default_construction():
    s = PositionSizer()
    assert s.method == 'vol_target'
    assert s.target_risk_pct == 0.01
    assert s.per_ticker_cap == 0.10
    assert s.vol_proxy == 'atr'


def test_invalid_method_raises():
    with pytest.raises(ValueError):
        PositionSizer(method='foo')


def test_invalid_vol_proxy_raises():
    with pytest.raises(ValueError):
        PositionSizer(vol_proxy='garbage')


def test_negative_pct_raises():
    with pytest.raises(ValueError):
        PositionSizer(target_risk_pct=-0.01)


def test_min_position_greater_than_cap_raises():
    with pytest.raises(ValueError):
        PositionSizer(min_position_pct=0.20, per_ticker_cap=0.10)


# ─── Equal method (legacy) ───────────────────────────────────────────────────

def test_equal_sizing_basic():
    s = PositionSizer(method='equal', per_ticker_cap=0.10, min_position_pct=0.005)
    # NAV=100k, price=100 → cap_notional=10k → 100 shares
    shares = s.size(nav=100_000, cash=100_000, price=100.0)
    assert shares == 100


def test_equal_sizing_cash_limited():
    s = PositionSizer(method='equal', per_ticker_cap=0.10)
    # cap consente 100 shares, ma cash=3000 → solo 30
    shares = s.size(nav=100_000, cash=3_000, price=100.0)
    assert shares == 30


def test_equal_sizing_zero_on_degenerate():
    s = PositionSizer(method='equal')
    assert s.size(nav=0, cash=10_000, price=100.0) == 0
    assert s.size(nav=10_000, cash=0, price=100.0) == 0
    assert s.size(nav=10_000, cash=10_000, price=0) == 0
    assert s.size(nav=-1, cash=10_000, price=100.0) == 0


# ─── Vol-target method ───────────────────────────────────────────────────────

def test_vol_target_basic():
    """target_risk=1% NAV=100k → 1000 EUR risk; ATR=2 EUR → 500 shares."""
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.50,  # cap alto per non interferire
        min_position_pct=0.001,
        vol_floor_pct=0.0,    # floor off
    )
    shares = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=2.0)
    # 1000 / 2 = 500
    assert shares == 500


def test_vol_target_high_vol_reduces_size():
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.50, min_position_pct=0.001, vol_floor_pct=0.0,
    )
    # ATR=10 (vol alta) → 100 shares
    high_vol = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=10.0)
    # ATR=2 (vol bassa) → 500 shares
    low_vol = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=2.0)
    assert high_vol < low_vol
    assert high_vol == 100


def test_vol_target_cap_caps_size():
    """Cap deve bloccare sizing esplosivo su vol bassissima."""
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.10, min_position_pct=0.001, vol_floor_pct=0.0,
    )
    # Vol=0.01 EUR → 100_000 shares teoriche, ma cap=10% di 100k=10k → 100 shares
    shares = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=0.01)
    assert shares == 100  # cap_shares = 10_000 / 100


def test_vol_target_vol_floor_protects_from_zero():
    """Vol floor evita sizing esplosivo su vol_eur quasi 0."""
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.10, min_position_pct=0.001,
        vol_floor_pct=0.01,   # floor = 1% prezzo
    )
    # Senza floor: vol_eur=0.001 → vol_shares=1_000_000 → capped a cap_shares
    # Con floor: vol_eur effective=1.0 → vol_shares=1000 → capped a 100 (cap)
    diag = s.diagnose(nav=100_000, cash=100_000, price=100.0, vol_eur=0.001)
    assert diag['vol_floored'] is True
    assert diag['vol_eur_effective'] == pytest.approx(1.0)
    assert diag['vol_shares'] == 1000   # 1000 EUR target / 1 EUR floor
    assert diag['shares'] == 100        # cap=10% × 100k / 100 = 100


def test_vol_target_fallback_to_equal_if_no_vol():
    """Se vol_eur è None o <=0, comportamento legacy (per_ticker_cap)."""
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.10, min_position_pct=0.001, vol_floor_pct=0.0,
    )
    shares_none = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=None)
    shares_zero = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=0)
    shares_nan = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=float('nan'))
    # Tutti devono coincidere col cap
    assert shares_none == shares_zero == shares_nan == 100


def test_min_position_filter_skip_tiny_trades():
    """Se notional < min_position_pct, ritorna 0."""
    s = PositionSizer(
        method='vol_target', target_risk_pct=0.01,
        per_ticker_cap=0.50,
        min_position_pct=0.05,   # 5% NAV = 5000 EUR minimo
        vol_floor_pct=0.0,
    )
    # Vol alta forza raw_shares basso → 100 shares × 100 = 10k OK
    # Ma se vol=50 → 1000/50=20 shares × 100 = 2000 EUR < 5000 → SKIP
    shares = s.size(nav=100_000, cash=100_000, price=100.0, vol_eur=50.0)
    assert shares == 0


def test_diagnose_breakdown():
    s = PositionSizer(method='vol_target', vol_floor_pct=0.0)
    diag = s.diagnose(nav=100_000, cash=100_000, price=100.0, vol_eur=2.0)
    assert diag['method'] == 'vol_target'
    assert diag['cap_shares'] == 100  # 10% di 100k / 100
    assert diag['vol_shares'] == 500
    assert diag['raw_shares'] == 100   # min(500, 100, 1000) = 100 (cap)
    assert diag['shares'] == 100
    assert diag['reason'] == 'ok'


def test_diagnose_fallback_when_no_vol():
    s = PositionSizer(method='vol_target')
    diag = s.diagnose(nav=100_000, cash=100_000, price=100.0, vol_eur=None)
    assert diag['effective_method'] == 'equal_fallback'


def test_diagnose_below_min_position():
    # cap > min per soddisfare validazione
    s = PositionSizer(
        method='vol_target', per_ticker_cap=0.50, min_position_pct=0.20, vol_floor_pct=0.0,
    )
    # cap_shares=500, vol_eur=10 → vol_shares=100 → notional=10k < 20k=min → 0
    diag = s.diagnose(nav=100_000, cash=100_000, price=100.0, vol_eur=10.0)
    assert diag['shares'] == 0
    assert diag['reason'] == 'below_min_position'


# ─── realized_vol_to_eur helper ──────────────────────────────────────────────

def test_realized_vol_basic():
    rets = np.array([0.01, -0.02, 0.015, -0.005, 0.008, -0.012, 0.003])
    vol = realized_vol_to_eur(price=100.0, daily_returns=rets)
    assert vol > 0
    expected = float(np.std(rets, ddof=1)) * 100
    assert vol == pytest.approx(expected, rel=1e-6)


def test_realized_vol_too_few_obs():
    rets = np.array([0.01, -0.01])
    assert math.isnan(realized_vol_to_eur(100.0, rets))


def test_realized_vol_handles_nan():
    rets = np.array([0.01, float('nan'), 0.02, float('nan'), -0.01, 0.015, -0.005])
    vol = realized_vol_to_eur(100.0, rets)
    # Filtra NaN, 5 obs rimaste → calcolo OK
    assert vol > 0 and math.isfinite(vol)


# ─── Integration: monotonia (più vol → meno shares) ──────────────────────────

def test_monotonia_vol_vs_shares():
    s = PositionSizer(
        method='vol_target', per_ticker_cap=0.99,
        min_position_pct=0.0, vol_floor_pct=0.0,
    )
    vols = [1.0, 2.0, 5.0, 10.0, 20.0]
    sizes = [s.size(nav=1_000_000, cash=1_000_000, price=100.0, vol_eur=v)
             for v in vols]
    # Monotonicamente decrescente
    for i in range(len(sizes) - 1):
        assert sizes[i] >= sizes[i + 1], f"Non monotono: {sizes}"
