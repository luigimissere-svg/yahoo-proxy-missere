"""
Fetch Fundamentals — Quant Framework v3.0 (Fase 2.3c)
======================================================

DA ESEGUIRE IN LOCALE (IP domestico, yfinance non funziona da Vercel/Actions).

Scarica snapshot fundamentals via yfinance.info per universe portfolio/extended:
    - P/E (trailing)
    - P/B
    - ROE
    - Debt/Equity
    - FCF yield (free cash flow / market cap)
    - Profit margin
    - Revenue growth (YoY)
    - Dividend yield

Output:
    quant_v3/data/fundamentals/{TICKER}.parquet  (1 row snapshot)
    quant_v3/data/fundamentals/_snapshot_log.json

USO:
    cd quant_v3
    python ingestion/fetch_fundamentals.py                      # tutto il portfolio
    python ingestion/fetch_fundamentals.py --portfolio-only     # 35 ticker (~3 min)
    python ingestion/fetch_fundamentals.py --extended           # 970 ticker (~30 min)
    python ingestion/fetch_fundamentals.py --resume             # skip già scaricati

NOTE:
    - yfinance.info è LENTO (~2 sec/ticker) e fragile (rate limit 429).
    - Il fetcher fa retry con backoff esponenziale.
    - I valori mancanti vengono salvati come NaN (non bloccano).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("ERRORE: yfinance non installato. pip install yfinance", file=sys.stderr)
    sys.exit(1)


# ─── Paths ──────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = ROOT / 'data'
META_DIR = DATA_DIR / 'meta'
OUT_DIR = DATA_DIR / 'fundamentals'
LOG_FILE = OUT_DIR / '_snapshot_log.json'


# ─── Fields da yfinance.info ────────────────────────────────────────────────

# Mappa nostro_nome → chiave yfinance.info
FIELDS = {
    'pe_trailing': 'trailingPE',
    'pe_forward': 'forwardPE',
    'pb': 'priceToBook',
    'ps': 'priceToSalesTrailing12Months',
    'roe': 'returnOnEquity',
    'roa': 'returnOnAssets',
    'debt_equity': 'debtToEquity',
    'profit_margin': 'profitMargins',
    'operating_margin': 'operatingMargins',
    'revenue_growth': 'revenueGrowth',
    'earnings_growth': 'earningsGrowth',
    'dividend_yield': 'dividendYield',
    'payout_ratio': 'payoutRatio',
    'beta': 'beta',
    'market_cap': 'marketCap',
    'enterprise_value': 'enterpriseValue',
    'fcf': 'freeCashflow',
    'sector': 'sector',
    'industry': 'industry',
    'currency': 'currency',
}


# ─── Helpers ────────────────────────────────────────────────────────────────


def _to_float(value):
    """Converte yfinance value in float, gestisce None/strings."""
    if value is None:
        return float('nan')
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return float('nan')
        return v
    except (TypeError, ValueError):
        return float('nan')


def fetch_one(ticker: str, max_retries: int = 3) -> dict | None:
    """Fetch fundamentals per un singolo ticker, con retry."""
    for attempt in range(max_retries):
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            if not info or len(info) < 5:
                # Empty/invalid response
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            row = {'ticker': ticker, 'snapshot_date': datetime.utcnow().date().isoformat()}
            for our_name, yf_key in FIELDS.items():
                raw = info.get(yf_key)
                if our_name in ('sector', 'industry', 'currency'):
                    row[our_name] = str(raw) if raw is not None else ''
                else:
                    row[our_name] = _to_float(raw)
            # Derived: FCF yield
            mcap = row.get('market_cap', float('nan'))
            fcf = row.get('fcf', float('nan'))
            if mcap and fcf and mcap > 0 and not math.isnan(mcap) and not math.isnan(fcf):
                row['fcf_yield'] = fcf / mcap
            else:
                row['fcf_yield'] = float('nan')
            return row
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  [{ticker}] retry {attempt+1}/{max_retries} after {wait}s: {e}",
                      file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  [{ticker}] FAILED after {max_retries}: {e}", file=sys.stderr)
                return None


def save_snapshot(ticker: str, row: dict) -> Path:
    """Salva singolo snapshot in parquet."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    out = OUT_DIR / f'{ticker}.parquet'
    df.to_parquet(out, compression='snappy', index=False)
    return out


def load_universe(portfolio_only: bool, extended: bool) -> list[str]:
    """Legge il CSV meta e ritorna lista ticker."""
    if extended:
        path = META_DIR / 'universe_extended.csv'
    elif portfolio_only:
        path = META_DIR / 'universe_portfolio.csv'
    else:
        path = META_DIR / 'universe_portfolio.csv'
    if not path.exists():
        print(f"ERRORE: {path} non esiste", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(path)
    return df['ticker'].dropna().unique().tolist()


# ─── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Fetch fundamentals snapshot via yfinance.info")
    parser.add_argument('--portfolio-only', action='store_true',
                        help='Solo 35 ticker portfolio (default)')
    parser.add_argument('--extended', action='store_true',
                        help='Universe completo ~970 ticker (~30 min)')
    parser.add_argument('--resume', action='store_true',
                        help='Skip ticker con file parquet già esistente')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limita N ticker (testing)')
    parser.add_argument('--sleep', type=float, default=0.3,
                        help='Sleep tra ticker per evitare rate limit (default 0.3s)')
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tickers = load_universe(args.portfolio_only or not args.extended, args.extended)
    if args.limit:
        tickers = tickers[: args.limit]

    if args.resume:
        existing = {f.stem for f in OUT_DIR.glob('*.parquet')}
        tickers_to_do = [t for t in tickers if t not in existing]
        print(f"Resume mode: {len(existing)} already done, {len(tickers_to_do)} to fetch")
        tickers = tickers_to_do

    print(f"Fetching fundamentals for {len(tickers)} tickers...")
    print(f"Output dir: {OUT_DIR}")

    results = {'ok': [], 'failed': [], 'started_at': datetime.utcnow().isoformat()}
    start = time.time()

    for i, tk in enumerate(tickers, 1):
        print(f"[{i:>4}/{len(tickers)}] {tk:<12}", end=' ', flush=True)
        row = fetch_one(tk)
        if row:
            save_snapshot(tk, row)
            pe = row.get('pe_trailing', float('nan'))
            roe = row.get('roe', float('nan'))
            print(f"OK  P/E={pe:>7.2f}  ROE={roe:>7.2%}" if not math.isnan(pe) and not math.isnan(roe)
                  else "OK  (some fields NaN)")
            results['ok'].append(tk)
        else:
            print("FAIL")
            results['failed'].append(tk)
        time.sleep(args.sleep)

    elapsed = time.time() - start
    results['ended_at'] = datetime.utcnow().isoformat()
    results['elapsed_sec'] = round(elapsed, 1)
    results['n_ok'] = len(results['ok'])
    results['n_failed'] = len(results['failed'])

    LOG_FILE.write_text(json.dumps(results, indent=2))

    print(f"\n{'='*60}")
    print(f"DONE in {elapsed:.0f}s — OK: {len(results['ok'])}  FAILED: {len(results['failed'])}")
    print(f"Log: {LOG_FILE}")
    if results['failed']:
        print(f"Failed tickers: {', '.join(results['failed'][:20])}"
              + (f" ... (+{len(results['failed'])-20} more)" if len(results['failed']) > 20 else ''))


if __name__ == '__main__':
    main()
