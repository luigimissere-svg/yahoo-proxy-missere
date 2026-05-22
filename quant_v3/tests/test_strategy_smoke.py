"""
Strategy smoke test — esegue cerebro su 5 ticker portfolio per ~1 anno.

Verifica:
    - Strategy si carica senza errori
    - Modules istanziati correttamente
    - cerebro.run() completa
    - bar_count > warmup
    - trade_log popolato (anche se 0 trade è OK)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backtrader as bt
import pytest

from engine.data_loader import DataLakeLoader
from engine.custom_data import build_feed
from engine.strategy import PatrimonioStrategy

DATA_ROOT = Path(__file__).resolve().parents[1] / 'data'


@pytest.fixture(scope='module')
def loader():
    return DataLakeLoader(data_root=DATA_ROOT)


def test_strategy_runs_on_5_tickers(loader):
    tickers = loader.list_tickers('portfolio', apply_filters=True)[:5]
    assert len(tickers) >= 3

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_cash(100_000)
    cerebro.broker.setcommission(commission=0.001)

    n_added = 0
    for t in tickers:
        b = loader.load_ticker(t)
        if b is None:
            continue
        feed = build_feed(b, fromdate='2024-08-01', earnings_window=5)
        cerebro.adddata(feed, name=t)
        n_added += 1

    assert n_added >= 3, f"Servono ≥3 feed, caricati {n_added}"

    cerebro.addstrategy(
        PatrimonioStrategy,
        threshold=0.20,
        min_concordant=3,
        max_positions=5,
        per_ticker_cap=0.20,
        warmup_bars=200,
        verbose=False,
    )

    res = cerebro.run()
    strat = res[0]

    # Verifiche
    assert strat.bar_count >= 200, f"Bars troppo poche: {strat.bar_count}"
    assert isinstance(strat.trade_log, list)
    assert cerebro.broker.get_value() > 0


def test_strategy_buy_when_strong_signal_unit(loader):
    """Test unit della logica composite (senza eseguire cerebro)."""
    from engine.signals import CompositeSignal

    sig = CompositeSignal(threshold=0.20, min_concordant=3)
    # Strong buy: 4+ moduli concordi positivi
    scores = {
        'trend': 0.8, 'momentum': 0.7, 'mean_reversion': 0.0,
        'value': 0.3, 'quality': 0.4, 'event_driven': 0.0,
    }
    composite = sig.combine(scores)
    assert composite > 0.30, f"Strong buy should compose > 0.30, got {composite}"

    # Weak signal: solo 2 concordi
    scores = {
        'trend': 0.6, 'momentum': 0.4, 'mean_reversion': 0.0,
        'value': 0.0, 'quality': 0.0, 'event_driven': 0.0,
    }
    composite = sig.combine(scores)
    assert composite == 0.0, f"Weak signal should be filtered, got {composite}"
