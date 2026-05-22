"""
CustomData — feed Backtrader esteso con linee aggiuntive.

Linee standard backtrader: open, high, low, close, volume, openinterest
Linee custom aggiunte:
    - adj_close       : prezzo corretto per dividendi/split (per total return)
    - dividend        : importo dividendo del giorno (0 se nessun dividendo)
    - earnings_flag   : 1 se earnings nei prossimi/scorsi N giorni (default ±5gg), altrimenti 0
    - earnings_surprise : surprise % dell'ultimo earnings recente (NaN altrimenti)
    - days_to_earnings : giorni al prossimo earnings (NaN se >30gg o nessuno)

Uso:
    from engine.custom_data import PatrimonioFeed, build_feed
    feed = build_feed(bundle, fromdate='2024-06-01', todate='2026-05-21',
                      earnings_window=5)
    cerebro.adddata(feed, name=bundle.ticker)
"""

from __future__ import annotations

import logging
from typing import Optional

import backtrader as bt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─── Feed class ──────────────────────────────────────────────────────────────

class PatrimonioFeed(bt.feeds.PandasData):
    """
    Feed esteso con linee event-driven per PatrimonioStrategy.

    DataFrame atteso: index=DatetimeIndex, colonne:
        open, high, low, close, volume, adj_close,
        dividend, earnings_flag, earnings_surprise, days_to_earnings
    """

    lines = ('adj_close', 'dividend', 'earnings_flag', 'earnings_surprise', 'days_to_earnings')

    params = (
        ('datetime', None),       # uses index
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
        ('adj_close', 'adj_close'),
        ('dividend', 'dividend'),
        ('earnings_flag', 'earnings_flag'),
        ('earnings_surprise', 'earnings_surprise'),
        ('days_to_earnings', 'days_to_earnings'),
    )


# ─── Builder ─────────────────────────────────────────────────────────────────

def build_feed(
    bundle,
    fromdate: Optional[str | pd.Timestamp] = None,
    todate: Optional[str | pd.Timestamp] = None,
    earnings_window: int = 5,
) -> PatrimonioFeed:
    """
    Costruisce un PatrimonioFeed da un TickerBundle.

    Args:
        bundle: TickerBundle (vedi data_loader.py)
        fromdate / todate: filtra range date (incluso)
        earnings_window: giorni ±N per cui earnings_flag=1 (default 5)

    Returns:
        PatrimonioFeed pronto per cerebro.adddata()
    """
    df = bundle.ohlcv.copy()
    if df.empty:
        raise ValueError(f"{bundle.ticker}: OHLCV vuoto")

    # Rebuild index frequenza business days, forward-fill su gap brevi
    df = df.asfreq('B').ffill(limit=5).dropna(subset=['close'])

    # ── Dividend line ────────────────────────────────────────────────────
    df['dividend'] = 0.0
    if not bundle.dividends.empty:
        # bundle.dividends può avere colonne diverse a seconda della source
        div_col = _pick_first_existing(bundle.dividends, ['dividends', 'dividend', 'amount'])
        if div_col:
            div_series = bundle.dividends[div_col].copy()
            div_series.index = pd.to_datetime(div_series.index).normalize()
            # Reindex su df.index (business days)
            df['dividend'] = div_series.reindex(df.index, fill_value=0.0)

    # ── Earnings lines ───────────────────────────────────────────────────
    df['earnings_flag'] = 0
    df['earnings_surprise'] = np.nan
    df['days_to_earnings'] = np.nan

    if not bundle.earnings.empty:
        earn = bundle.earnings.copy()
        earn.index = pd.to_datetime(earn.index).normalize()
        # Drop tz-aware
        if earn.index.tz is not None:
            earn.index = earn.index.tz_localize(None)

        # Surprise column (può essere 'surprise(%)' o 'surprise_pct')
        surprise_col = _pick_first_existing(earn, ['surprise(%)', 'surprise_pct', 'surprise'])

        # Per ogni earnings_date, marca window
        for ed in earn.index.unique():
            if pd.isna(ed):
                continue
            window_start = ed - pd.Timedelta(days=earnings_window)
            window_end = ed + pd.Timedelta(days=earnings_window)
            mask = (df.index >= window_start) & (df.index <= window_end)
            df.loc[mask, 'earnings_flag'] = 1
            if surprise_col:
                surprise_val = earn.loc[ed, surprise_col]
                if isinstance(surprise_val, pd.Series):
                    surprise_val = surprise_val.iloc[0]
                if pd.notna(surprise_val):
                    df.loc[mask, 'earnings_surprise'] = surprise_val

        # Days to next earnings (per ogni giorno calcola giorni al prossimo earnings_date)
        future_dates = sorted([d for d in earn.index.unique() if pd.notna(d)])
        if future_dates:
            df['days_to_earnings'] = df.index.map(
                lambda d: _days_to_next(d, future_dates, max_days=30)
            )

    # ── Filtro date ──────────────────────────────────────────────────────
    if fromdate is not None:
        df = df.loc[pd.Timestamp(fromdate):]
    if todate is not None:
        df = df.loc[:pd.Timestamp(todate)]

    if df.empty:
        raise ValueError(f"{bundle.ticker}: dataframe vuoto dopo filtro date")

    # Backtrader vuole NaN come float
    df['earnings_surprise'] = df['earnings_surprise'].astype(float)
    df['days_to_earnings'] = df['days_to_earnings'].astype(float)
    df['earnings_flag'] = df['earnings_flag'].astype(int)
    df['dividend'] = df['dividend'].astype(float)

    feed = PatrimonioFeed(dataname=df)
    return feed


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _pick_first_existing(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _days_to_next(d: pd.Timestamp, future_dates: list, max_days: int = 30) -> float:
    """Giorni al prossimo earnings entro max_days. NaN se nessuno o oltre soglia."""
    upcoming = [fd for fd in future_dates if fd >= d]
    if not upcoming:
        return np.nan
    delta = (upcoming[0] - d).days
    if delta > max_days:
        return np.nan
    return float(delta)


# ─── Smoke test ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)

    from data_loader import DataLakeLoader

    loader = DataLakeLoader(data_root='data')
    aapl = loader.load_ticker('AAPL')
    if aapl is None:
        print("AAPL non disponibile")
    else:
        feed = build_feed(aapl, fromdate='2025-01-01', earnings_window=5)
        df = feed.p.dataname
        print(f"Feed AAPL: {len(df)} barre")
        print(f"  Earnings flagged: {df['earnings_flag'].sum()} giorni")
        print(f"  Total dividends: {df['dividend'].sum():.2f}")
        print(f"  Sample con earnings_flag=1:")
        sample = df[df['earnings_flag'] == 1].head(3)
        print(sample[['close', 'earnings_flag', 'earnings_surprise', 'days_to_earnings']])
