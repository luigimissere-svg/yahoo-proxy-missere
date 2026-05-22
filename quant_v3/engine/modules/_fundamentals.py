"""
Fundamentals loader — helper condiviso da value.py e quality.py.

Carica snapshot parquet da data/fundamentals/{TICKER}.parquet.
Cache in-memory per evitare reload multipli.

Se il file non esiste, ritorna None (i moduli scoreranno 0.0 = neutro).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import pandas as pd


# ─── Cache globale ─────────────────────────────────────────────────────────

_FUNDAMENTALS_CACHE: dict[str, Optional[dict]] = {}
_DATA_ROOT: Optional[Path] = None


def set_data_root(path: str | Path) -> None:
    """Setta data root globale. Chiamato da DataLakeLoader o runner."""
    global _DATA_ROOT, _FUNDAMENTALS_CACHE
    _DATA_ROOT = Path(path)
    _FUNDAMENTALS_CACHE.clear()


def _resolve_data_root() -> Path:
    """Ritorna data root, default 'data' rispetto cwd."""
    if _DATA_ROOT is not None:
        return _DATA_ROOT
    return Path('data')


def get_fundamentals(ticker: str) -> Optional[dict]:
    """
    Ritorna dict fundamentals per ticker, o None se non disponibile.

    Cache: una sola lettura parquet per ticker per process.
    """
    if ticker in _FUNDAMENTALS_CACHE:
        return _FUNDAMENTALS_CACHE[ticker]

    root = _resolve_data_root()
    path = root / 'fundamentals' / f'{ticker}.parquet'
    if not path.exists():
        _FUNDAMENTALS_CACHE[ticker] = None
        return None

    try:
        df = pd.read_parquet(path)
        if df.empty:
            _FUNDAMENTALS_CACHE[ticker] = None
            return None
        row = df.iloc[0].to_dict()
        _FUNDAMENTALS_CACHE[ticker] = row
        return row
    except Exception:
        _FUNDAMENTALS_CACHE[ticker] = None
        return None


def safe_float(value, default: float = float('nan')) -> float:
    """Helper: converte in float, gestisce NaN/None."""
    if value is None:
        return default
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default
