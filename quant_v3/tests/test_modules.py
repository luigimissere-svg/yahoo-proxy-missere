"""Test moduli alpha (momentum, mean_reversion, trend, event_driven)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest
import backtrader as bt

from engine.modules.trend import TrendModule
from engine.modules.momentum import MomentumModule
from engine.modules.mean_reversion import MeanReversionModule
from engine.modules.event_driven import EventDrivenModule
from engine.modules.value import ValueModule
from engine.modules.quality import QualityModule
from engine.modules import _fundamentals as fund_mod


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_feed(prices: np.ndarray, dates=None):
    """Crea PandasData feed da array prezzi (close)."""
    n = len(prices)
    if dates is None:
        dates = pd.date_range('2024-01-01', periods=n, freq='B')
    df = pd.DataFrame({
        'open': prices,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.full(n, 1_000_000),
    }, index=dates)
    return bt.feeds.PandasData(dataname=df)


class _CapturingStrategy(bt.Strategy):
    """Strategy che salva lo score finale di un modulo."""
    params = (('module', None),)

    def __init__(self):
        self.module = self.p.module
        self.module.prepare(self.datas[0])
        self.scores = []

    def next(self):
        self.scores.append(self.module.score())


def _run_module(module, prices):
    """Esegue una strategia che colleziona score per ogni barra."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(_make_feed(prices))
    cerebro.addstrategy(_CapturingStrategy, module=module)
    res = cerebro.run()
    return res[0].scores


# ─── Trend ──────────────────────────────────────────────────────────────────


def test_trend_uptrend_positive():
    """Serie crescente monotona → score finale positivo."""
    prices = np.linspace(100, 200, 300)
    scores = _run_module(TrendModule(), prices)
    # Ultimi 10 score in uptrend conclamato
    last = [s for s in scores[-10:] if s != 0.0]
    assert len(last) > 0
    assert np.mean(last) > 0.3, f"Expected positive trend score, got {np.mean(last):.3f}"


def test_trend_downtrend_negative():
    prices = np.linspace(200, 100, 300)
    scores = _run_module(TrendModule(), prices)
    last = [s for s in scores[-10:] if s != 0.0]
    assert len(last) > 0
    assert np.mean(last) < -0.3, f"Expected negative trend, got {np.mean(last):.3f}"


def test_trend_score_bounded():
    """Score sempre in [-1, +1]."""
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(300))
    scores = _run_module(TrendModule(), prices)
    for s in scores:
        assert -1.0 <= s <= 1.0


# ─── Momentum ───────────────────────────────────────────────────────────────


def test_momentum_strong_uptrend_positive():
    """Forte uptrend (con micro-noise per ATR>0) → momentum score positivo."""
    np.random.seed(11)
    trend = np.linspace(100, 250, 300)
    noise = np.random.randn(300) * 0.3
    prices = trend + noise
    scores = _run_module(MomentumModule(), prices)
    last = [s for s in scores[-20:] if s != 0.0]
    assert len(last) > 0
    assert np.mean(last) > 0.3, f"Got {np.mean(last):.3f}"


def test_momentum_strong_downtrend_negative():
    np.random.seed(12)
    trend = np.linspace(250, 100, 300)
    noise = np.random.randn(300) * 0.3
    prices = trend + noise
    scores = _run_module(MomentumModule(), prices)
    last = [s for s in scores[-20:] if s != 0.0]
    assert len(last) > 0
    assert np.mean(last) < -0.3, f"Got {np.mean(last):.3f}"


def test_momentum_sideways_near_zero():
    """Serie laterale → momentum vicino a 0."""
    np.random.seed(7)
    prices = 100 + np.random.randn(300) * 0.5
    scores = _run_module(MomentumModule(), prices)
    last = [s for s in scores[-20:] if s != 0.0]
    if last:
        assert abs(np.mean(last)) < 0.3, f"Expected near-zero, got {np.mean(last):.3f}"


def test_momentum_bounded():
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(300))
    scores = _run_module(MomentumModule(), prices)
    for s in scores:
        assert -1.0 <= s <= 1.0


# ─── Mean Reversion ─────────────────────────────────────────────────────────


def test_mean_reversion_oversold_positive():
    """Crash improvviso dopo lateralità → MR score positivo (BUY contrarian)."""
    np.random.seed(1)
    base = 100 + np.random.randn(280) * 0.3  # 280 giorni laterali
    crash = np.linspace(100, 80, 20)  # crash finale
    prices = np.concatenate([base, crash])
    scores = _run_module(MeanReversionModule(), prices)
    last = scores[-1]
    assert last > 0.2, f"Expected oversold positive, got {last:.3f}"


def test_mean_reversion_overbought_negative():
    """Spike improvviso dopo lateralità → MR score negativo."""
    np.random.seed(2)
    base = 100 + np.random.randn(280) * 0.3
    spike = np.linspace(100, 120, 20)
    prices = np.concatenate([base, spike])
    scores = _run_module(MeanReversionModule(), prices)
    last = scores[-1]
    assert last < -0.2, f"Expected overbought negative, got {last:.3f}"


def test_mean_reversion_bounded():
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(300))
    scores = _run_module(MeanReversionModule(), prices)
    for s in scores:
        assert -1.0 <= s <= 1.0


# ─── Event Driven ───────────────────────────────────────────────────────────


def test_event_driven_default_zero():
    """Senza earnings/dividend lines, event_driven ritorna 0."""
    prices = np.linspace(100, 110, 100)
    scores = _run_module(EventDrivenModule(), prices)
    # PandasData base non ha lines earnings/dividend custom; should default to 0
    assert all(s == 0.0 for s in scores)


# ─── Value / Quality (require fundamentals) ───────────────────────────


def test_value_no_fundamentals_returns_zero(tmp_path):
    """Senza parquet fundamentals, ValueModule ritorna 0.0."""
    fund_mod.set_data_root(tmp_path)  # tmp_path vuoto, niente fundamentals
    prices = np.linspace(100, 110, 100)
    feed = _make_feed(prices)
    feed._name = 'TESTNOFUND'
    m = ValueModule()
    m.prepare(feed)
    assert m.score() == 0.0


def test_value_undervalued_positive(tmp_path):
    """Stock undervalued (low P/E, low P/B, alto FCF yield) → score positivo."""
    # Crea parquet finto
    fund_dir = tmp_path / 'fundamentals'
    fund_dir.mkdir()
    df = pd.DataFrame([{
        'ticker': 'CHEAP',
        'pe_trailing': 8.0,    # < pe_low (10)
        'pb': 0.8,             # < pb_low (1)
        'fcf_yield': 0.10,     # > target (7%)
        'roe': 0.15,
        'profit_margin': 0.10,
        'debt_equity': 30.0,
    }])
    df.to_parquet(fund_dir / 'CHEAP.parquet', index=False)

    fund_mod.set_data_root(tmp_path)
    feed = _make_feed(np.linspace(100, 110, 100))
    feed._name = 'CHEAP'
    m = ValueModule()
    m.prepare(feed)
    score = m.score()
    assert score > 0.5, f"Expected high positive value score, got {score:.3f}"


def test_value_overvalued_negative(tmp_path):
    fund_dir = tmp_path / 'fundamentals'
    fund_dir.mkdir()
    df = pd.DataFrame([{
        'ticker': 'EXPENSIVE',
        'pe_trailing': 60.0,   # >> pe_high (30)
        'pb': 8.0,             # >> pb_high (4)
        'fcf_yield': -0.02,    # negative
    }])
    df.to_parquet(fund_dir / 'EXPENSIVE.parquet', index=False)

    fund_mod.set_data_root(tmp_path)
    feed = _make_feed(np.linspace(100, 110, 100))
    feed._name = 'EXPENSIVE'
    m = ValueModule()
    m.prepare(feed)
    score = m.score()
    assert score < -0.5, f"Expected negative value score, got {score:.3f}"


def test_quality_excellent_positive(tmp_path):
    """Stock con ROE 25%, margin 20%, D/E 30 → score alto."""
    fund_dir = tmp_path / 'fundamentals'
    fund_dir.mkdir()
    df = pd.DataFrame([{
        'ticker': 'TOP',
        'roe': 0.25,
        'profit_margin': 0.20,
        'debt_equity': 30.0,
    }])
    df.to_parquet(fund_dir / 'TOP.parquet', index=False)

    fund_mod.set_data_root(tmp_path)
    feed = _make_feed(np.linspace(100, 110, 100))
    feed._name = 'TOP'
    m = QualityModule()
    m.prepare(feed)
    score = m.score()
    assert score > 0.7, f"Expected high quality score, got {score:.3f}"


def test_quality_poor_negative(tmp_path):
    fund_dir = tmp_path / 'fundamentals'
    fund_dir.mkdir()
    df = pd.DataFrame([{
        'ticker': 'BAD',
        'roe': -0.05,            # ROE negativo
        'profit_margin': -0.03,  # loss-making
        'debt_equity': 350.0,    # high leverage
    }])
    df.to_parquet(fund_dir / 'BAD.parquet', index=False)

    fund_mod.set_data_root(tmp_path)
    feed = _make_feed(np.linspace(100, 110, 100))
    feed._name = 'BAD'
    m = QualityModule()
    m.prepare(feed)
    score = m.score()
    assert score < -0.5, f"Expected negative quality, got {score:.3f}"
