"""Test CompositeSignal blending."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import numpy as np

from engine.signals import CompositeSignal, DEFAULT_WEIGHTS, normalize_score, zscore_to_score


# ─── Validation ──────────────────────────────────────────────────────────────

def test_default_weights_sum_to_one():
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-6


def test_default_weights_strategy_B():
    """Strategia B: value e quality hanno weight=0 (pre-screening only)."""
    assert DEFAULT_WEIGHTS['value'] == 0.0
    assert DEFAULT_WEIGHTS['quality'] == 0.0
    # I 4 moduli attivi sommano a 1
    active = {k: v for k, v in DEFAULT_WEIGHTS.items() if v > 0}
    assert len(active) == 4
    assert abs(sum(active.values()) - 1.0) < 1e-6


def test_invalid_weights_raise():
    with pytest.raises(ValueError):
        CompositeSignal(weights={'trend': 0.5, 'momentum': 0.3})  # < 1


def test_negative_weights_raise():
    with pytest.raises(ValueError):
        CompositeSignal(weights={
            'trend': 0.5, 'momentum': 0.6, 'mean_reversion': 0.0,
            'value': -0.1, 'quality': 0.0, 'event_driven': 0.0,
        })


def test_min_concordant_exceeds_active_modules_raises():
    """Se min_concordant > num moduli con peso>0, deve sollevare."""
    weights = {
        'trend': 0.5, 'momentum': 0.5, 'mean_reversion': 0.0,
        'value': 0.0, 'quality': 0.0, 'event_driven': 0.0,
    }
    # Solo 2 moduli attivi, min_concordant=3 → deve raise
    with pytest.raises(ValueError):
        CompositeSignal(weights=weights, min_concordant=3)
    # min_concordant=2 → OK
    CompositeSignal(weights=weights, min_concordant=2)


def test_unknown_module_raises():
    with pytest.raises(ValueError):
        bad = {**DEFAULT_WEIGHTS, 'foo': 0.0}
        bad['trend'] = 0.25  # restore total = 1
        CompositeSignal(weights=bad)


# ─── Combine logic ───────────────────────────────────────────────────────────

def test_strong_buy_passes_gating():
    # Test con pesi tutti uniformi 1/6 per non dipendere dai default
    weights = {k: 1/6 for k in DEFAULT_WEIGHTS}
    sig = CompositeSignal(weights=weights, threshold=0.20, min_concordant=3)
    scores = {
        'trend': 0.8, 'momentum': 0.7, 'mean_reversion': 0.4,
        'value': 0.3, 'quality': 0.5, 'event_driven': 0.2,
    }
    out = sig.combine(scores)
    assert out > 0.4, f"Strong buy expected, got {out}"


def test_zero_weight_modules_ignored_in_concordance():
    """Moduli con weight=0 non devono contare nel concordance count."""
    weights = {
        'trend': 0.5, 'momentum': 0.5, 'mean_reversion': 0.0,
        'value': 0.0, 'quality': 0.0, 'event_driven': 0.0,
    }
    sig = CompositeSignal(weights=weights, threshold=0.10, min_concordant=2)
    # Solo 2 moduli attivi entrambi positivi → weighted_sum=0.6, 2 concordi → passa
    scores = {
        'trend': 0.6, 'momentum': 0.6,
        'mean_reversion': 1.0, 'value': 1.0, 'quality': 1.0, 'event_driven': 1.0,
    }
    out = sig.combine(scores)
    assert out > 0.5
    # Gli altri moduli con score=1.0 NON contribuiscono perché weight=0
    diag = sig.diagnose(scores)
    assert diag['n_active_modules'] == 2
    assert diag['n_concordant'] == 2  # solo trend e momentum


def test_default_weights_pre_screening_composition():
    """Con DEFAULT_WEIGHTS (B), 4 moduli attivi e value/quality non in composite."""
    sig = CompositeSignal(threshold=0.20, min_concordant=3)
    # Composite forte dai 4 moduli tecnici, value/quality molto negativi
    scores = {
        'trend': 0.7, 'momentum': 0.6, 'mean_reversion': 0.4, 'event_driven': 0.5,
        'value': -0.9, 'quality': -0.9,
    }
    out = sig.combine(scores)
    # value/quality (weight=0) non devono frenare il composite
    assert out > 0.4, f"Pre-screening: value/quality non in composite, got {out}"
    diag = sig.diagnose(scores)
    assert diag['n_active_modules'] == 4
    assert diag['n_concordant'] == 4


def test_below_threshold_returns_zero():
    sig = CompositeSignal(threshold=0.30, min_concordant=3)
    scores = {k: 0.1 for k in DEFAULT_WEIGHTS}  # weighted avg = 0.1 < 0.30
    out = sig.combine(scores)
    assert out == 0.0


def test_insufficient_concordance_returns_zero():
    """Solo 1 modulo positivo, gli altri ~0 → composite passa threshold ma non concordance."""
    sig = CompositeSignal(threshold=0.10, min_concordant=3)
    scores = {
        'trend': 1.0,         # forte, peso 0.25 → contribuisce 0.25
        'momentum': 0.0, 'mean_reversion': 0.0,
        'value': 0.0, 'quality': 0.0, 'event_driven': 0.0,
    }
    out = sig.combine(scores)
    # composite = 0.25 > 0.10 ma solo 1 modulo concorde → 0.0
    assert out == 0.0, f"Insufficient concordance should return 0, got {out}"


def test_strong_sell():
    sig = CompositeSignal(threshold=0.20, min_concordant=3)
    scores = {k: -0.7 for k in DEFAULT_WEIGHTS}
    out = sig.combine(scores)
    assert out < -0.5


def test_mixed_signals_neutral():
    """3 positivi e 3 negativi con pesi uniformi 1/6 → composite=0."""
    weights = {k: 1/6 for k in DEFAULT_WEIGHTS}
    sig = CompositeSignal(weights=weights, threshold=0.05, min_concordant=3)
    scores = {
        'trend': 0.5, 'momentum': 0.5, 'mean_reversion': 0.5,
        'value': -0.5, 'quality': -0.5, 'event_driven': -0.5,
    }
    out = sig.combine(scores)
    # weighted_sum = (3*0.5 - 3*0.5) / 6 = 0 → threshold filter → 0
    assert out == 0.0


def test_nan_handled():
    sig = CompositeSignal(threshold=0.10, min_concordant=2)
    scores = {
        'trend': float('nan'), 'momentum': 0.5, 'mean_reversion': 0.4,
        'value': 0.3, 'quality': float('nan'), 'event_driven': 0.0,
    }
    # Non deve crashare
    out = sig.combine(scores)
    assert not np.isnan(out)


def test_diagnose_returns_full_breakdown():
    sig = CompositeSignal()  # DEFAULT_WEIGHTS (Strategia B: 4 attivi)
    scores = {k: 0.5 for k in DEFAULT_WEIGHTS}
    diag = sig.diagnose(scores)
    assert 'composite' in diag
    assert 'contributions' in diag
    assert len(diag['contributions']) == 6  # tutti i moduli, anche weight=0
    # Solo 4 moduli attivi concordano (value/quality weight=0 esclusi)
    assert diag['n_active_modules'] == 4
    assert diag['n_concordant'] == 4
    assert diag['emitted'] is True


# ─── Helpers ─────────────────────────────────────────────────────────────────

def test_normalize_score_basic():
    # RSI: 30→+1 (oversold), 70→-1 (overbought)
    assert normalize_score(30, 30, 70, invert=True) == pytest.approx(1.0)
    assert normalize_score(70, 30, 70, invert=True) == pytest.approx(-1.0)
    assert normalize_score(50, 30, 70, invert=True) == pytest.approx(0.0)


def test_zscore_to_score():
    assert zscore_to_score(0.0) == 0.0
    assert zscore_to_score(3.0) == pytest.approx(1.0)
    assert zscore_to_score(-3.0) == pytest.approx(-1.0)
    assert zscore_to_score(1.5) == pytest.approx(0.5)
