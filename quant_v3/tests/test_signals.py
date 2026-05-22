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


def test_invalid_weights_raise():
    with pytest.raises(ValueError):
        CompositeSignal(weights={'trend': 0.5, 'momentum': 0.3})  # < 1


def test_unknown_module_raises():
    with pytest.raises(ValueError):
        bad = {**DEFAULT_WEIGHTS, 'foo': 0.0}
        bad['trend'] = 0.25  # restore total = 1
        CompositeSignal(weights=bad)


# ─── Combine logic ───────────────────────────────────────────────────────────

def test_strong_buy_passes_gating():
    sig = CompositeSignal(threshold=0.20, min_concordant=3)
    scores = {
        'trend': 0.8, 'momentum': 0.7, 'mean_reversion': 0.4,
        'value': 0.3, 'quality': 0.5, 'event_driven': 0.2,
    }
    out = sig.combine(scores)
    assert out > 0.4, f"Strong buy expected, got {out}"


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
    """3 positivi e 3 negativi → composite vicino a 0."""
    sig = CompositeSignal(threshold=0.05, min_concordant=3)
    scores = {
        'trend': 0.5, 'momentum': 0.5, 'mean_reversion': 0.5,
        'value': -0.5, 'quality': -0.5, 'event_driven': -0.5,
    }
    out = sig.combine(scores)
    # Pesi: trend(0.25)+momentum(0.25)+mr(0.15) - value(0.15)-quality(0.10)-event(0.10)
    # = 0.5 × (0.65 - 0.35) = 0.15
    # 0.15 > 0.05, ma concordance: solo 3 positivi (>eps=0.10) — esattamente min_concordant=3 → passa
    assert out != 0.0


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
    sig = CompositeSignal()
    scores = {k: 0.5 for k in DEFAULT_WEIGHTS}
    diag = sig.diagnose(scores)
    assert 'composite' in diag
    assert 'contributions' in diag
    assert len(diag['contributions']) == 6
    assert diag['n_concordant'] == 6
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
