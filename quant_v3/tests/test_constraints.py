"""Test PortfolioConstraints — Fase 3.3."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math

import pandas as pd
import pytest

from engine.constraints import (
    DEFAULT_BETA,
    DEFAULT_SECTOR,
    PortfolioConstraints,
    load_metadata,
    make_default_constraints,
)


# ─── Validation ──────────────────────────────────────────────────────────────

def test_default_construction():
    c = PortfolioConstraints()
    assert c.max_sector_pct == 0.30
    assert c.max_portfolio_beta == 1.3
    assert c.violation_policy == 'block_new'
    assert c.unknown_pool is True
    assert c.sector_map == {}
    assert c.beta_map == {}


def test_invalid_policy_raises():
    with pytest.raises(ValueError):
        PortfolioConstraints(violation_policy='foo')  # type: ignore[arg-type]


def test_invalid_sector_cap_raises():
    with pytest.raises(ValueError):
        PortfolioConstraints(max_sector_pct=-0.1)


def test_invalid_beta_cap_raises():
    with pytest.raises(ValueError):
        PortfolioConstraints(max_portfolio_beta=-0.5)


def test_caps_disabled_when_none():
    c = PortfolioConstraints(max_sector_pct=None, max_portfolio_beta=None)
    assert not c.sector_cap_enabled
    assert not c.beta_cap_enabled


def test_caps_disabled_when_zero():
    c = PortfolioConstraints(max_sector_pct=0, max_portfolio_beta=0)
    assert not c.sector_cap_enabled
    assert not c.beta_cap_enabled


# ─── Lookups ─────────────────────────────────────────────────────────────────

def test_sector_of_known():
    c = PortfolioConstraints(sector_map={'AAPL': 'Technology'})
    assert c.sector_of('AAPL') == 'Technology'


def test_sector_of_unknown_returns_default():
    c = PortfolioConstraints(sector_map={'AAPL': 'Technology'})
    assert c.sector_of('ZZZ') == DEFAULT_SECTOR
    assert c.sector_of('ZZZ') == 'Unknown'


def test_beta_of_known():
    c = PortfolioConstraints(beta_map={'AAPL': 1.25})
    assert c.beta_of('AAPL') == 1.25


def test_beta_of_unknown_returns_default():
    c = PortfolioConstraints(beta_map={'AAPL': 1.25})
    assert c.beta_of('ZZZ') == DEFAULT_BETA
    assert c.beta_of('ZZZ') == 1.0


def test_beta_of_nan_falls_back():
    c = PortfolioConstraints(beta_map={'AAPL': float('nan')})
    assert c.beta_of('AAPL') == DEFAULT_BETA


def test_beta_of_inf_falls_back():
    c = PortfolioConstraints(beta_map={'AAPL': float('inf')})
    assert c.beta_of('AAPL') == DEFAULT_BETA


# ─── load_metadata ───────────────────────────────────────────────────────────

def test_load_metadata_missing_file(tmp_path):
    sm, bm = load_metadata(tmp_path / 'does_not_exist.parquet')
    assert sm == {}
    assert bm == {}


def test_load_metadata_roundtrip(tmp_path):
    df = pd.DataFrame([
        {'ticker': 'AAPL', 'sector': 'Technology', 'beta': 1.25},
        {'ticker': 'XOM', 'sector': 'Energy', 'beta': 0.85},
    ])
    p = tmp_path / 'meta.parquet'
    df.to_parquet(p)
    sm, bm = load_metadata(p)
    assert sm == {'AAPL': 'Technology', 'XOM': 'Energy'}
    assert bm == {'AAPL': 1.25, 'XOM': 0.85}


def test_load_metadata_nan_beta_uses_default(tmp_path):
    df = pd.DataFrame([
        {'ticker': 'AAPL', 'sector': 'Technology', 'beta': float('nan')},
    ])
    p = tmp_path / 'meta.parquet'
    df.to_parquet(p)
    sm, bm = load_metadata(p)
    assert sm == {'AAPL': 'Technology'}
    assert bm == {'AAPL': DEFAULT_BETA}


def test_load_metadata_missing_sector_falls_back(tmp_path):
    df = pd.DataFrame([
        {'ticker': 'AAPL', 'sector': None, 'beta': 1.1},
    ])
    p = tmp_path / 'meta.parquet'
    df.to_parquet(p)
    sm, _ = load_metadata(p)
    assert sm['AAPL'] == DEFAULT_SECTOR


# ─── sector_exposure ─────────────────────────────────────────────────────────

def test_sector_exposure_basic():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'XOM': 'Energy'},
    )
    exp = c.sector_exposure({'AAPL': 1000.0, 'XOM': 500.0}, nav=10000.0)
    assert exp['Technology'] == pytest.approx(0.10)
    assert exp['Energy'] == pytest.approx(0.05)


def test_sector_exposure_multi_ticker_same_sector():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
    )
    exp = c.sector_exposure({'AAPL': 1000.0, 'MSFT': 2000.0}, nav=10000.0)
    assert exp['Technology'] == pytest.approx(0.30)


def test_sector_exposure_empty_positions():
    c = PortfolioConstraints()
    assert c.sector_exposure({}, nav=10000.0) == {}


def test_sector_exposure_nav_zero_returns_empty():
    c = PortfolioConstraints()
    assert c.sector_exposure({'AAPL': 1000.0}, nav=0.0) == {}


def test_sector_exposure_skips_zero_notional():
    c = PortfolioConstraints(sector_map={'AAPL': 'Technology'})
    exp = c.sector_exposure({'AAPL': 0.0}, nav=10000.0)
    assert exp == {}


def test_sector_exposure_unknown_pool_true():
    c = PortfolioConstraints(unknown_pool=True)  # no sector_map
    exp = c.sector_exposure({'AAPL': 1000.0, 'XOM': 500.0}, nav=10000.0)
    assert exp == {DEFAULT_SECTOR: pytest.approx(0.15)}


def test_sector_exposure_unknown_pool_false_skips():
    c = PortfolioConstraints(unknown_pool=False)  # no sector_map
    exp = c.sector_exposure({'AAPL': 1000.0, 'XOM': 500.0}, nav=10000.0)
    assert exp == {}


# ─── portfolio_beta ──────────────────────────────────────────────────────────

def test_portfolio_beta_basic():
    c = PortfolioConstraints(beta_map={'AAPL': 1.5, 'XOM': 0.5})
    # weight AAPL = 0.1, XOM = 0.05
    # beta = 0.1*1.5 + 0.05*0.5 = 0.15 + 0.025 = 0.175
    b = c.portfolio_beta({'AAPL': 1000.0, 'XOM': 500.0}, nav=10000.0)
    assert b == pytest.approx(0.175)


def test_portfolio_beta_empty():
    c = PortfolioConstraints()
    assert c.portfolio_beta({}, nav=10000.0) == 0.0


def test_portfolio_beta_nav_zero():
    c = PortfolioConstraints(beta_map={'AAPL': 1.5})
    assert c.portfolio_beta({'AAPL': 1000.0}, nav=0.0) == 0.0


def test_portfolio_beta_cash_component_is_zero():
    # 50% invested, beta_t=1.0 → portfolio_beta = 0.5 (resto è cash, beta=0)
    c = PortfolioConstraints(beta_map={'AAPL': 1.0})
    b = c.portfolio_beta({'AAPL': 5000.0}, nav=10000.0)
    assert b == pytest.approx(0.5)


def test_portfolio_beta_unknown_ticker_uses_default():
    c = PortfolioConstraints()  # empty maps
    # ticker non in map → beta=DEFAULT_BETA=1.0, weight=0.1
    b = c.portfolio_beta({'AAPL': 1000.0}, nav=10000.0)
    assert b == pytest.approx(0.1)


# ─── would_violate — sector cap ──────────────────────────────────────────────

def test_would_violate_sector_cap_not_binding():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # 5% nuova posizione in settore vuoto
    violated, reason = c.would_violate('AAPL', 500.0, {}, nav=10000.0)
    assert violated is False
    assert reason is None


def test_would_violate_sector_cap_binding():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # già 25% in Tech, candidato 10% → 35% > 30%
    violated, reason = c.would_violate(
        'MSFT', 1000.0, {'AAPL': 2500.0}, nav=10000.0,
    )
    assert violated is True
    assert reason is not None
    assert 'sector_cap' in reason
    assert 'Technology' in reason


def test_would_violate_sector_cap_just_below_limit_ok():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # 20% + 9% = 29% (sotto cap)
    violated, _ = c.would_violate(
        'MSFT', 900.0, {'AAPL': 2000.0}, nav=10000.0,
    )
    assert violated is False


# ─── would_violate — beta cap ────────────────────────────────────────────────

def test_would_violate_beta_cap_not_binding():
    c = PortfolioConstraints(
        beta_map={'AAPL': 1.0},
        max_sector_pct=None,
        max_portfolio_beta=1.3,
    )
    violated, reason = c.would_violate('AAPL', 1000.0, {}, nav=10000.0)
    assert violated is False
    assert reason is None


def test_would_violate_beta_cap_binding():
    c = PortfolioConstraints(
        beta_map={'AAPL': 1.0, 'NVDA': 2.5},
        max_sector_pct=None,
        max_portfolio_beta=1.3,
    )
    # già 50% AAPL beta=1.0 → portfolio_beta=0.5
    # candidato NVDA 50% beta=2.5 → +1.25 → totale 1.75 > 1.3
    violated, reason = c.would_violate(
        'NVDA', 5000.0, {'AAPL': 5000.0}, nav=10000.0,
    )
    assert violated is True
    assert reason is not None
    assert 'beta_cap' in reason


def test_would_violate_both_caps_disabled():
    c = PortfolioConstraints(
        max_sector_pct=None,
        max_portfolio_beta=None,
    )
    # Anche con posizione enorme, niente violazione
    violated, reason = c.would_violate(
        'AAPL', 100_000.0, {'AAPL': 100_000.0}, nav=10000.0,
    )
    assert violated is False
    assert reason is None


def test_would_violate_both_caps_active():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'NVDA': 'Technology'},
        beta_map={'AAPL': 1.0, 'NVDA': 2.5},
        max_sector_pct=0.30,
        max_portfolio_beta=1.3,
    )
    # già 25% AAPL Tech (beta=1.0 → 0.25)
    # NVDA 10% → tech 35% (sector viola PRIMA del beta check)
    violated, reason = c.would_violate(
        'NVDA', 1000.0, {'AAPL': 2500.0}, nav=10000.0,
    )
    assert violated is True
    assert 'sector_cap' in reason


def test_would_violate_zero_notional_returns_false():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology'},
        max_sector_pct=0.01,  # cap molto basso
    )
    violated, reason = c.would_violate('AAPL', 0.0, {}, nav=10000.0)
    assert violated is False
    assert reason is None


def test_would_violate_nav_zero_returns_false():
    c = PortfolioConstraints(sector_map={'AAPL': 'Technology'})
    violated, reason = c.would_violate('AAPL', 1000.0, {}, nav=0.0)
    assert violated is False
    assert reason is None


def test_would_violate_unknown_pool_false_skips_sector_check():
    c = PortfolioConstraints(
        unknown_pool=False,
        max_sector_pct=0.10,
        max_portfolio_beta=None,
    )
    # Ticker Unknown con notional > cap: viene SALTATO
    violated, _ = c.would_violate('ZZZ', 5000.0, {}, nav=10000.0)
    assert violated is False


def test_would_violate_unknown_pool_true_enforces_sector_check():
    c = PortfolioConstraints(
        unknown_pool=True,
        max_sector_pct=0.10,
        max_portfolio_beta=None,
    )
    # Ticker Unknown 50% → viola cap del pool Unknown
    violated, reason = c.would_violate('ZZZ', 5000.0, {}, nav=10000.0)
    assert violated is True
    assert 'Unknown' in reason


# ─── max_notional_allowed ────────────────────────────────────────────────────

def test_max_notional_allowed_no_caps_returns_inf():
    c = PortfolioConstraints(max_sector_pct=None, max_portfolio_beta=None)
    assert c.max_notional_allowed('AAPL', {}, nav=10000.0) == float('inf')


def test_max_notional_allowed_sector_cap_only():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # niente in Tech, cap 30% di 10000 → max 3000
    assert c.max_notional_allowed('AAPL', {}, nav=10000.0) == pytest.approx(3000.0)


def test_max_notional_allowed_sector_residual():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # già 25% Tech, residuo 5% di 10000 → 500
    allowed = c.max_notional_allowed('MSFT', {'AAPL': 2500.0}, nav=10000.0)
    assert allowed == pytest.approx(500.0)


def test_max_notional_allowed_sector_saturated():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
        max_sector_pct=0.30,
        max_portfolio_beta=None,
    )
    # già 30% Tech → niente spazio
    allowed = c.max_notional_allowed('MSFT', {'AAPL': 3000.0}, nav=10000.0)
    assert allowed == pytest.approx(0.0)


def test_max_notional_allowed_beta_cap_only():
    c = PortfolioConstraints(
        beta_map={'NVDA': 2.0},
        max_sector_pct=None,
        max_portfolio_beta=1.3,
    )
    # beta corrente 0, residuo 1.3, candidato beta=2.0
    # extra_notional = 1.3 * 10000 / 2.0 = 6500
    allowed = c.max_notional_allowed('NVDA', {}, nav=10000.0)
    assert allowed == pytest.approx(6500.0)


def test_max_notional_allowed_beta_residual():
    c = PortfolioConstraints(
        beta_map={'AAPL': 1.0, 'NVDA': 2.0},
        max_sector_pct=None,
        max_portfolio_beta=1.3,
    )
    # 50% AAPL beta=1 → portfolio_beta=0.5, residuo 0.8
    # extra_notional = 0.8 * 10000 / 2.0 = 4000
    allowed = c.max_notional_allowed('NVDA', {'AAPL': 5000.0}, nav=10000.0)
    assert allowed == pytest.approx(4000.0)


def test_max_notional_allowed_beta_negative_no_constraint():
    # candidate con beta<=0 abbassa il beta del portfolio → no constraint
    c = PortfolioConstraints(
        beta_map={'XOM': -0.1},
        max_sector_pct=None,
        max_portfolio_beta=1.3,
    )
    allowed = c.max_notional_allowed('XOM', {}, nav=10000.0)
    assert allowed == float('inf')


def test_max_notional_allowed_combined_min_wins():
    # sector residuo = 500, beta residuo = 6500 → 500
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology', 'MSFT': 'Technology'},
        beta_map={'AAPL': 1.0, 'MSFT': 1.0},
        max_sector_pct=0.30,
        max_portfolio_beta=1.3,
    )
    allowed = c.max_notional_allowed('MSFT', {'AAPL': 2500.0}, nav=10000.0)
    assert allowed == pytest.approx(500.0)


def test_max_notional_allowed_nav_zero():
    c = PortfolioConstraints(max_sector_pct=0.30)
    assert c.max_notional_allowed('AAPL', {}, nav=0.0) == 0.0


def test_max_notional_allowed_unknown_pool_false_ignores_sector():
    c = PortfolioConstraints(
        unknown_pool=False,
        max_sector_pct=0.10,
        max_portfolio_beta=None,
    )
    # Unknown ignorato → no sector cap → inf
    assert c.max_notional_allowed('ZZZ', {}, nav=10000.0) == float('inf')


# ─── diagnose ────────────────────────────────────────────────────────────────

def test_diagnose_returns_expected_keys():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology'},
        beta_map={'AAPL': 1.2},
    )
    d = c.diagnose({'AAPL': 1000.0}, nav=10000.0)
    expected_keys = {
        'nav', 'sector_exposure', 'portfolio_beta', 'max_sector_pct',
        'max_portfolio_beta', 'sector_cap_enabled', 'beta_cap_enabled',
        'n_positions',
    }
    assert expected_keys.issubset(set(d.keys()))


def test_diagnose_values():
    c = PortfolioConstraints(
        sector_map={'AAPL': 'Technology'},
        beta_map={'AAPL': 1.2},
        max_sector_pct=0.30,
        max_portfolio_beta=1.3,
    )
    d = c.diagnose({'AAPL': 1000.0}, nav=10000.0)
    assert d['nav'] == 10000.0
    assert d['n_positions'] == 1
    assert d['sector_cap_enabled'] is True
    assert d['beta_cap_enabled'] is True
    assert d['portfolio_beta'] == pytest.approx(0.12)
    assert d['sector_exposure']['Technology'] == pytest.approx(0.10)


def test_diagnose_no_positions():
    c = PortfolioConstraints()
    d = c.diagnose({}, nav=10000.0)
    assert d['n_positions'] == 0
    assert d['portfolio_beta'] == 0.0
    assert d['sector_exposure'] == {}


# ─── make_default_constraints factory ────────────────────────────────────────

def test_make_default_constraints_no_path():
    c = make_default_constraints(metadata_path=None)
    assert isinstance(c, PortfolioConstraints)
    assert c.sector_map == {}
    assert c.beta_map == {}
    assert c.max_sector_pct == 0.30
    assert c.max_portfolio_beta == 1.3


def test_make_default_constraints_with_path(tmp_path):
    df = pd.DataFrame([
        {'ticker': 'AAPL', 'sector': 'Technology', 'beta': 1.25},
    ])
    p = tmp_path / 'meta.parquet'
    df.to_parquet(p)
    c = make_default_constraints(metadata_path=p)
    assert c.sector_map == {'AAPL': 'Technology'}
    assert c.beta_map == {'AAPL': 1.25}


def test_make_default_constraints_custom_params():
    c = make_default_constraints(
        metadata_path=None,
        max_sector_pct=0.40,
        max_portfolio_beta=1.5,
        violation_policy='scale_down',
    )
    assert c.max_sector_pct == 0.40
    assert c.max_portfolio_beta == 1.5
    assert c.violation_policy == 'scale_down'


def test_make_default_constraints_missing_file_returns_empty(tmp_path):
    c = make_default_constraints(metadata_path=tmp_path / 'nope.parquet')
    assert c.sector_map == {}
    assert c.beta_map == {}
