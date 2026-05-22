"""
Smoke test data_loader + custom_data.

Run:
    cd quant_v3
    python -m pytest tests/ -v
    # oppure:
    python tests/test_data_loader.py
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Make engine/ importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from engine.data_loader import DataLakeLoader, TickerBundle
from engine.custom_data import build_feed, PatrimonioFeed


DATA_ROOT = Path(__file__).resolve().parents[1] / 'data'


@pytest.fixture(scope='module')
def loader():
    return DataLakeLoader(data_root=DATA_ROOT)


# ─── Loader basics ───────────────────────────────────────────────────────────

def test_data_lake_exists(loader):
    s = loader.summary()
    assert s['ohlcv_files'] >= 900, f"OHLCV troppo pochi: {s['ohlcv_files']}"
    assert s['benchmark_files'] >= 14, f"Benchmark troppo pochi: {s['benchmark_files']}"
    assert s['corporate_files'] >= 1000, f"Corporate troppo pochi: {s['corporate_files']}"


def test_portfolio_universe(loader):
    tickers = loader.list_tickers('portfolio', apply_filters=False)
    assert len(tickers) >= 30, f"Portfolio universe troppo piccolo: {len(tickers)}"
    # Filtered should not exceed unfiltered
    filtered = loader.list_tickers('portfolio', apply_filters=True)
    assert len(filtered) <= len(tickers)


def test_extended_universe(loader):
    tickers = loader.list_tickers('extended', apply_filters=False)
    assert len(tickers) >= 900
    filtered = loader.list_tickers('extended', apply_filters=True)
    # Filtri applicati: deve eliminare almeno qualche ticker (low coverage)
    assert len(filtered) < len(tickers)
    assert len(filtered) >= 700, f"Extended filtered troppo restrittivo: {len(filtered)}"


# ─── Single ticker bundle ────────────────────────────────────────────────────

def test_load_aapl(loader):
    b = loader.load_ticker('AAPL')
    assert b is not None
    assert isinstance(b, TickerBundle)
    assert b.ticker == 'AAPL'
    assert b.n_rows > 252
    assert 'close' in b.ohlcv.columns
    assert b.ohlcv['close'].notna().all()


def test_load_eu_ticker(loader):
    """STOXX600: BMW.DE should load with .DE suffix."""
    b = loader.load_ticker('BMW.DE')
    assert b is not None
    assert b.n_rows > 200


def test_load_portfolio_ticker(loader):
    """Portfolio Greek ticker."""
    b = loader.load_ticker('PPC.AT')
    assert b is not None
    assert b.n_rows > 200


def test_unknown_ticker_returns_none(loader):
    b = loader.load_ticker('XXXFAKE')
    assert b is None


# ─── Custom data feed ────────────────────────────────────────────────────────

def test_build_feed_aapl(loader):
    b = loader.load_ticker('AAPL')
    feed = build_feed(b, fromdate='2025-01-01', earnings_window=5)
    assert isinstance(feed, PatrimonioFeed)
    df = feed.p.dataname
    # Linee custom presenti
    for col in ['open', 'high', 'low', 'close', 'volume', 'adj_close',
                'dividend', 'earnings_flag', 'earnings_surprise', 'days_to_earnings']:
        assert col in df.columns, f"Colonna mancante: {col}"
    # Earnings dovrebbe essere flaggato in qualche giorno
    assert df['earnings_flag'].sum() > 0, "Nessun earnings flagged in AAPL ultimi 18 mesi?"


def test_build_feed_with_dividend(loader):
    """AAPL paga dividendi → almeno qualche giorno con dividend > 0."""
    b = loader.load_ticker('AAPL')
    feed = build_feed(b)
    df = feed.p.dataname
    assert df['dividend'].sum() > 0, "AAPL dovrebbe avere dividendi"


def test_build_feed_date_filter(loader):
    b = loader.load_ticker('AAPL')
    feed = build_feed(b, fromdate='2026-01-01', todate='2026-03-31')
    df = feed.p.dataname
    assert df.index.min() >= pd.Timestamp('2026-01-01')
    assert df.index.max() <= pd.Timestamp('2026-03-31')


# ─── Benchmarks ──────────────────────────────────────────────────────────────

def test_benchmarks_loadable(loader):
    benchmarks = loader.list_benchmarks()
    assert '^GSPC' in benchmarks
    assert '^VIX' in benchmarks
    assert '^STOXX' in benchmarks
    df = loader.load_benchmark('^GSPC')
    assert len(df) > 250


# ─── Manual run ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Running smoke tests inline (no pytest)...")
    loader = DataLakeLoader(data_root=DATA_ROOT)
    print("\n=== Summary ===")
    for k, v in loader.summary().items():
        print(f"  {k}: {v}")

    print("\n=== AAPL bundle ===")
    aapl = loader.load_ticker('AAPL')
    print(f"  rows={aapl.n_rows}  range={aapl.first_date.date()}→{aapl.last_date.date()}")

    print("\n=== AAPL feed ===")
    feed = build_feed(aapl, fromdate='2025-01-01', earnings_window=5)
    df = feed.p.dataname
    print(f"  feed bars={len(df)}")
    print(f"  earnings_flag sum={df['earnings_flag'].sum()}")
    print(f"  dividend sum={df['dividend'].sum():.2f}")
    print("\n  Sample with earnings_flag=1:")
    print(df[df['earnings_flag'] == 1].head(3)[
        ['close', 'earnings_flag', 'earnings_surprise', 'days_to_earnings']
    ])
    print("\nAll smoke tests OK")
