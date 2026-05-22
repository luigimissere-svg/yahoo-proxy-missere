"""Test RegimeDetector — Fase 3.2."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math
import pytest

from engine.regime import (
    RegimeDetector,
    RegimeState,
    DEFAULT_VIX_THRESHOLDS,
    DEFAULT_DELEVERAGING,
    DEFAULT_TRAILING_ATR_MULT,
    make_default_detector,
)


# ─── Validation ──────────────────────────────────────────────────────────────

def test_default_construction():
    d = RegimeDetector()
    assert d.mode == 'off'
    assert d.fallback_regime == 'NORMAL'
    # Defaults coerenti
    assert d.thresholds['LOW'] == 15.0
    assert d.deleveraging['EXTREME'] == 0.0
    assert d.trailing_atr_mult['LOW'] == 2.5


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        RegimeDetector(mode='foo')


def test_invalid_fallback_raises():
    with pytest.raises(ValueError):
        RegimeDetector(fallback_regime='WEIRD')


def test_missing_regime_in_thresholds_raises():
    bad = {'LOW': 15.0}  # mancano altri regimi
    with pytest.raises(ValueError):
        RegimeDetector(mode='deleveraging', thresholds=bad)


def test_non_monotone_thresholds_raises():
    bad = dict(DEFAULT_VIX_THRESHOLDS)
    bad['NORMAL'] = 10.0  # < LOW=15 → non monotone
    with pytest.raises(ValueError):
        RegimeDetector(mode='deleveraging', thresholds=bad)


def test_negative_deleveraging_raises():
    bad = dict(DEFAULT_DELEVERAGING)
    bad['HIGH'] = -0.1
    with pytest.raises(ValueError):
        RegimeDetector(mode='deleveraging', deleveraging=bad)


# ─── Classification ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("vix, expected", [
    (10.0, 'LOW'),
    (14.99, 'LOW'),
    (15.0, 'NORMAL'),
    (17.5, 'NORMAL'),
    (19.99, 'NORMAL'),
    (20.0, 'ELEVATED'),
    (22.5, 'ELEVATED'),
    (24.99, 'ELEVATED'),
    (25.0, 'HIGH'),
    (30.0, 'HIGH'),
    (34.99, 'HIGH'),
    (35.0, 'EXTREME'),
    (50.0, 'EXTREME'),
    (100.0, 'EXTREME'),
])
def test_classify_thresholds(vix, expected):
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(vix)
    assert state.name == expected


# ─── Mode='off' bypass ───────────────────────────────────────────────────────

def test_mode_off_always_normal():
    d = RegimeDetector(mode='off')
    for vix in (5.0, 18.0, 30.0, 60.0, None, float('nan')):
        state = d.detect(vix)
        assert state.name == 'NORMAL'
        assert state.deleveraging_factor == 1.0
        assert state.block_new_buys is False


# ─── VIX None / NaN fallback ─────────────────────────────────────────────────

def test_none_vix_falls_back_to_normal():
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(None)
    assert state.name == 'NORMAL'
    assert state.vix is None
    assert state.deleveraging_factor == 1.0
    assert not state.block_new_buys


def test_nan_vix_falls_back():
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(float('nan'))
    assert state.name == 'NORMAL'
    assert state.vix is None


def test_custom_fallback_regime():
    d = RegimeDetector(mode='full', fallback_regime='ELEVATED')
    state = d.detect(None)
    assert state.name == 'ELEVATED'
    assert state.deleveraging_factor == DEFAULT_DELEVERAGING['ELEVATED']


# ─── Deleveraging factors ────────────────────────────────────────────────────

def test_deleveraging_factor_low_is_one():
    d = RegimeDetector(mode='deleveraging')
    assert d.detect(10.0).deleveraging_factor == 1.0


def test_deleveraging_factor_elevated():
    d = RegimeDetector(mode='deleveraging')
    assert d.detect(22.0).deleveraging_factor == 0.7


def test_deleveraging_factor_high():
    d = RegimeDetector(mode='deleveraging')
    assert d.detect(28.0).deleveraging_factor == 0.4


def test_extreme_blocks_new_buys():
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(40.0)
    assert state.name == 'EXTREME'
    assert state.deleveraging_factor == 0.0
    assert state.block_new_buys is True


def test_block_new_buys_only_when_factor_zero():
    """block_new_buys deve essere True SOLO se delev == 0."""
    d = RegimeDetector(mode='deleveraging')
    for vix in (10.0, 17.0, 22.0, 28.0):
        assert not d.detect(vix).block_new_buys
    assert d.detect(50.0).block_new_buys


# ─── Trailing ATR mult ───────────────────────────────────────────────────────

def test_trailing_atr_mult_full_mode():
    d = RegimeDetector(mode='full')
    assert d.detect(10.0).trailing_atr_mult == 2.5     # LOW
    assert d.detect(17.0).trailing_atr_mult == 2.5     # NORMAL
    assert d.detect(22.0).trailing_atr_mult == 2.0     # ELEVATED
    assert d.detect(28.0).trailing_atr_mult == 1.5     # HIGH
    assert d.detect(40.0).trailing_atr_mult == 1.0     # EXTREME


def test_trailing_atr_mult_deleveraging_uses_default():
    """In mode='deleveraging' il trailing NON è regime-aware → sempre NORMAL default."""
    d = RegimeDetector(mode='deleveraging')
    for vix in (10.0, 22.0, 28.0, 40.0):
        # In deleveraging, trailing usa sempre default NORMAL
        assert d.detect(vix).trailing_atr_mult == DEFAULT_TRAILING_ATR_MULT['NORMAL']


# ─── Monotonia: VIX↑ → delev↓ ────────────────────────────────────────────────

def test_deleveraging_monotone_decreasing():
    """A VIX crescente, deleveraging_factor non aumenta mai."""
    d = RegimeDetector(mode='deleveraging')
    vix_levels = [5, 12, 17, 22, 28, 40, 60]
    factors = [d.detect(v).deleveraging_factor for v in vix_levels]
    for i in range(1, len(factors)):
        assert factors[i] <= factors[i-1], (
            f"non-monotone at vix={vix_levels[i]}: {factors[i]} > {factors[i-1]}"
        )


def test_trailing_atr_mult_monotone_decreasing():
    """A VIX crescente, trailing_atr_mult non aumenta mai (in full mode)."""
    d = RegimeDetector(mode='full')
    vix_levels = [5, 12, 17, 22, 28, 40, 60]
    mults = [d.detect(v).trailing_atr_mult for v in vix_levels]
    for i in range(1, len(mults)):
        assert mults[i] <= mults[i-1]


# ─── Override custom ─────────────────────────────────────────────────────────

def test_custom_thresholds():
    """Soglie più aggressive: ELEVATED già da VIX=18."""
    thr = {'LOW': 12.0, 'NORMAL': 18.0, 'ELEVATED': 23.0, 'HIGH': 30.0, 'EXTREME': math.inf}
    d = RegimeDetector(mode='deleveraging', thresholds=thr)
    assert d.detect(10.0).name == 'LOW'
    assert d.detect(15.0).name == 'NORMAL'
    assert d.detect(20.0).name == 'ELEVATED'
    assert d.detect(25.0).name == 'HIGH'


def test_custom_deleveraging():
    """Custom factors più conservativi (size si dimezza già in ELEVATED)."""
    delev = {'LOW': 1.0, 'NORMAL': 1.0, 'ELEVATED': 0.5, 'HIGH': 0.25, 'EXTREME': 0.0}
    d = RegimeDetector(mode='deleveraging', deleveraging=delev)
    assert d.detect(22.0).deleveraging_factor == 0.5
    assert d.detect(30.0).deleveraging_factor == 0.25


# ─── Factory ─────────────────────────────────────────────────────────────────

def test_factory_default():
    d = make_default_detector()
    assert d.mode == 'off'


def test_factory_with_mode():
    d = make_default_detector(mode='full')
    assert d.mode == 'full'
    # Sanity: detect funziona
    state = d.detect(30.0)
    assert state.name == 'HIGH'
    assert state.trailing_atr_mult == 1.5


# ─── State immutability semantics ────────────────────────────────────────────

def test_state_carries_vix_value():
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(22.5)
    assert state.vix == 22.5
    # Caso None deve restare None
    state2 = d.detect(None)
    assert state2.vix is None


# ─── Edge case: VIX=0 e negativi ─────────────────────────────────────────────

def test_zero_vix_classified_as_low():
    """VIX=0 (impossibile in pratica) cade in LOW."""
    d = RegimeDetector(mode='deleveraging')
    state = d.detect(0.0)
    assert state.name == 'LOW'
