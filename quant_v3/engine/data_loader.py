"""
Data Loader — carica parquet OHLCV/benchmark/corporate dal data lake e li trasforma
in feeds backtrader (CustomData con earnings/dividend lines).

Schema parquet OHLCV (da initial_download.py):
    columns = [date, open, high, low, close, adj_close, volume, dividends, stock_splits, ticker]
    date è una colonna (pd.Timestamp), non l'indice → set_index('date') al load.

Filtri qualità applicati di default:
    - coverage >= MIN_COVERAGE (0.80) — esclude IPO recenti / reintegrazioni indice tardive
    - rows >= MIN_ROWS (252) — almeno 1 anno di dati per warmup indicatori
    - exclude tickers in EXCLUDE_LIST (manuali, es. dati corrotti)

Uso tipico:
    from engine.data_loader import DataLakeLoader
    loader = DataLakeLoader(data_root='data')
    feeds = loader.load_universe('portfolio')   # 35 tickers
    feeds = loader.load_universe('extended')    # ~960 tickers (filtered)
    bench = loader.load_benchmark('^GSPC')
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ─── Config defaults ─────────────────────────────────────────────────────────
MIN_COVERAGE = 0.80   # Backtest universe quality threshold
MIN_ROWS = 252        # Almeno 1 anno (252 trading days)
EXCLUDE_LIST: set = set()  # Aggiungi qui ticker da escludere manualmente

# Mapping universe key → file in data/meta/
UNIVERSE_FILES = {
    'portfolio': 'universe_portfolio.csv',
    'extended':  'universe_extended.csv',
}


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class TickerBundle:
    """Container con OHLCV + corporate events allineati."""
    ticker: str
    ohlcv: pd.DataFrame          # index=date, cols=open/high/low/close/adj_close/volume
    dividends: pd.DataFrame      # index=ex_date, col=dividend
    earnings: pd.DataFrame       # index=earnings_date, cols=eps_estimate/reported_eps/surprise_pct
    splits: pd.DataFrame         # index=date, col=split_ratio
    meta: dict                   # universe metadata (sector, industry, country, mktcap)

    @property
    def n_rows(self) -> int:
        return len(self.ohlcv)

    @property
    def first_date(self) -> pd.Timestamp:
        return self.ohlcv.index.min()

    @property
    def last_date(self) -> pd.Timestamp:
        return self.ohlcv.index.max()


# ─── Loader principale ───────────────────────────────────────────────────────

class DataLakeLoader:
    """
    Loader del data lake quant_v3/data/.

    Args:
        data_root: path root del data lake (default 'data' relativo a CWD).
        min_coverage: coverage minimo (% giorni con dati vs benchmark) per includere il ticker.
        min_rows: numero minimo di righe OHLCV.
        validate: se True, applica filtri qualità (default True).
    """

    def __init__(
        self,
        data_root: str | Path = 'data',
        min_coverage: float = MIN_COVERAGE,
        min_rows: int = MIN_ROWS,
        validate: bool = True,
    ):
        self.data_root = Path(data_root)
        self.min_coverage = min_coverage
        self.min_rows = min_rows
        self.validate = validate

        if not self.data_root.exists():
            raise FileNotFoundError(f"Data lake non trovato: {self.data_root.resolve()}")

        self.ohlcv_dir = self.data_root / 'ohlcv'
        self.bench_dir = self.data_root / 'benchmarks'
        self.corp_dir = self.data_root / 'corporate'
        self.meta_dir = self.data_root / 'meta'

        self._validation_df: Optional[pd.DataFrame] = None
        self._universe_meta: Dict[str, pd.DataFrame] = {}

    # ── Validation report ─────────────────────────────────────────────────

    @property
    def validation(self) -> pd.DataFrame:
        """Carica e cachea data/_validation_report.csv"""
        if self._validation_df is None:
            path = self.data_root / '_validation_report.csv'
            if not path.exists():
                logger.warning(f"Validation report non trovato: {path}")
                self._validation_df = pd.DataFrame()
            else:
                self._validation_df = pd.read_csv(path)
        return self._validation_df

    def get_quality(self, ticker: str) -> Optional[dict]:
        """Coverage, status, issues per un ticker. None se non in report."""
        if self.validation.empty:
            return None
        # Il ticker nel report potrebbe essere senza suffisso (es. "PPC" invece di "PPC.AT")
        # Match esatto + match base (prima del primo punto)
        base = ticker.split('.')[0]
        rows = self.validation[
            (self.validation['ticker'] == ticker) | (self.validation['ticker'] == base)
        ]
        if rows.empty:
            return None
        return rows.iloc[0].to_dict()

    # ── Universe loading ──────────────────────────────────────────────────

    def load_universe_meta(self, universe: str = 'extended') -> pd.DataFrame:
        """Carica universe_*.csv (sector/industry/country/mktcap)."""
        if universe in self._universe_meta:
            return self._universe_meta[universe]

        if universe not in UNIVERSE_FILES:
            raise ValueError(f"Universe sconosciuto: {universe}. Disponibili: {list(UNIVERSE_FILES)}")

        path = self.meta_dir / UNIVERSE_FILES[universe]
        if not path.exists():
            raise FileNotFoundError(f"Universe file non trovato: {path}")

        df = pd.read_csv(path)
        if 'ticker' not in df.columns:
            raise ValueError(f"Colonna 'ticker' mancante in {path}")

        self._universe_meta[universe] = df
        return df

    def list_tickers(self, universe: str = 'extended', apply_filters: bool = True) -> List[str]:
        """
        Ritorna lista ticker dell'universe, opzionalmente filtrata per qualità.

        Args:
            universe: 'portfolio' o 'extended'
            apply_filters: se True applica MIN_COVERAGE / MIN_ROWS / EXCLUDE_LIST
        """
        meta = self.load_universe_meta(universe)
        tickers = meta['ticker'].dropna().unique().tolist()

        if not apply_filters:
            return tickers

        # Filter 1: existence in ohlcv/
        tickers = [t for t in tickers if (self.ohlcv_dir / f'{t}.parquet').exists()]

        # Filter 2: validation quality
        if self.validate and not self.validation.empty:
            kept = []
            for t in tickers:
                q = self.get_quality(t)
                if q is None:
                    # Ticker non in report → skip prudenzialmente
                    continue
                if q.get('coverage', 0) >= self.min_coverage and q.get('rows', 0) >= self.min_rows:
                    kept.append(t)
            tickers = kept

        # Filter 3: exclusion list
        tickers = [t for t in tickers if t not in EXCLUDE_LIST]

        return sorted(tickers)

    # ── Single ticker bundle ──────────────────────────────────────────────

    def load_ticker(self, ticker: str, universe: str = 'extended') -> Optional[TickerBundle]:
        """
        Carica TickerBundle completo (OHLCV + dividends + earnings + splits + meta).

        Returns None se OHLCV mancante o sotto soglie.
        """
        # OHLCV
        ohlcv_path = self.ohlcv_dir / f'{ticker}.parquet'
        if not ohlcv_path.exists():
            logger.debug(f"{ticker}: OHLCV file mancante")
            return None

        df = pd.read_parquet(ohlcv_path)
        if df.empty or 'date' not in df.columns:
            logger.warning(f"{ticker}: parquet vuoto o senza colonna 'date'")
            return None

        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        # Forward fill su gap brevi (max 5 giorni — festività)
        df = df.asfreq('B').ffill(limit=5)

        if self.validate and len(df) < self.min_rows:
            logger.debug(f"{ticker}: solo {len(df)} righe (<{self.min_rows})")
            return None

        ohlcv = df[['open', 'high', 'low', 'close', 'adj_close', 'volume']].dropna(how='all')

        # Dividends (corporate/<ticker>_dividends.parquet)
        div = self._load_corporate(ticker, 'dividends')
        # Earnings (corporate/<ticker>_earnings.parquet)
        earn = self._load_corporate(ticker, 'earnings')
        # Splits (corporate/<ticker>_splits.parquet — raro)
        splits = self._load_corporate(ticker, 'splits')

        # Meta
        meta = self._load_ticker_meta(ticker, universe)

        return TickerBundle(
            ticker=ticker,
            ohlcv=ohlcv,
            dividends=div,
            earnings=earn,
            splits=splits,
            meta=meta,
        )

    def _load_corporate(self, ticker: str, kind: str) -> pd.DataFrame:
        """kind: 'dividends' | 'earnings' | 'splits'"""
        path = self.corp_dir / f'{ticker}_{kind}.parquet'
        if not path.exists():
            return pd.DataFrame()

        df = pd.read_parquet(path)
        if df.empty:
            return df

        # Standardize date column (alcuni hanno 'date', earnings ha 'earnings_date')
        if 'earnings_date' in df.columns:
            df['date'] = pd.to_datetime(df['earnings_date'], utc=True).dt.tz_localize(None)
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], utc=True, errors='coerce').dt.tz_localize(None)
        elif df.index.name == 'date' or isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df['date'] = pd.to_datetime(df['date'])
        else:
            return pd.DataFrame()

        df = df.set_index('date').sort_index()
        return df

    def _load_ticker_meta(self, ticker: str, universe: str) -> dict:
        """Estrae meta (sector, industry, country, mktcap) dall'universe csv."""
        try:
            u = self.load_universe_meta(universe)
            row = u[u['ticker'] == ticker]
            if row.empty:
                return {}
            return row.iloc[0].to_dict()
        except Exception:
            return {}

    # ── Batch loading ─────────────────────────────────────────────────────

    def load_universe(
        self,
        universe: str = 'extended',
        max_tickers: Optional[int] = None,
        progress: bool = True,
    ) -> Dict[str, TickerBundle]:
        """
        Carica tutti i ticker dell'universe come dict[ticker] → TickerBundle.

        Args:
            universe: 'portfolio' o 'extended'
            max_tickers: limita a primi N (utile per smoke test)
            progress: stampa progresso ogni 50 ticker
        """
        tickers = self.list_tickers(universe, apply_filters=self.validate)
        if max_tickers:
            tickers = tickers[:max_tickers]

        bundles: Dict[str, TickerBundle] = {}
        for i, t in enumerate(tickers, 1):
            b = self.load_ticker(t, universe)
            if b is not None:
                bundles[t] = b
            if progress and i % 50 == 0:
                print(f"  [{i}/{len(tickers)}] loaded {len(bundles)}")

        logger.info(f"Universe '{universe}': caricati {len(bundles)}/{len(tickers)} ticker")
        return bundles

    # ── Benchmark ─────────────────────────────────────────────────────────

    def load_benchmark(self, symbol: str) -> pd.DataFrame:
        """Carica benchmark (^GSPC, ^STOXX, ^VIX, EURUSD=X, ...)."""
        path = self.bench_dir / f'{symbol}.parquet'
        if not path.exists():
            raise FileNotFoundError(f"Benchmark non trovato: {path}")

        df = pd.read_parquet(path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        return df

    def list_benchmarks(self) -> List[str]:
        """Ritorna lista simboli benchmark disponibili."""
        if not self.bench_dir.exists():
            return []
        return sorted(p.stem for p in self.bench_dir.glob('*.parquet'))

    # ── Diagnostics ───────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Statistiche data lake."""
        n_ohlcv = len(list(self.ohlcv_dir.glob('*.parquet')))
        n_bench = len(list(self.bench_dir.glob('*.parquet')))
        n_corp = len(list(self.corp_dir.glob('*.parquet')))
        try:
            n_portfolio = len(self.list_tickers('portfolio', apply_filters=False))
            n_portfolio_filt = len(self.list_tickers('portfolio', apply_filters=True))
            n_ext = len(self.list_tickers('extended', apply_filters=False))
            n_ext_filt = len(self.list_tickers('extended', apply_filters=True))
        except Exception:
            n_portfolio = n_portfolio_filt = n_ext = n_ext_filt = 0

        return {
            'data_root': str(self.data_root.resolve()),
            'ohlcv_files': n_ohlcv,
            'benchmark_files': n_bench,
            'corporate_files': n_corp,
            'portfolio_total': n_portfolio,
            'portfolio_filtered': n_portfolio_filt,
            'extended_total': n_ext,
            'extended_filtered': n_ext_filt,
            'min_coverage': self.min_coverage,
            'min_rows': self.min_rows,
        }


# ─── CLI smoke test ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    loader = DataLakeLoader(data_root='data')
    print("=== DATA LAKE SUMMARY ===")
    for k, v in loader.summary().items():
        print(f"  {k}: {v}")

    print("\n=== SAMPLE: AAPL ===")
    aapl = loader.load_ticker('AAPL')
    if aapl:
        print(f"  Rows: {aapl.n_rows}  ({aapl.first_date.date()} → {aapl.last_date.date()})")
        print(f"  Dividends: {len(aapl.dividends)} events")
        print(f"  Earnings: {len(aapl.earnings)} events")
        print(f"  Last close: {aapl.ohlcv['close'].iloc[-1]:.2f}")
