"""
Fetch metadata (sector + beta) per universe via yfinance.

Output: data/meta/sector_beta.parquet con colonne:
    ticker, sector, industry, beta, market_cap, currency, updated_at

Uso:
    cd quant_v3
    python -m engine.fetch_metadata --universe portfolio
    python -m engine.fetch_metadata --universe extended --sleep 0.5

Note:
    - yfinance Ticker.info è soggetto a rate limiting → usare --sleep > 0 in extended.
    - Lancia da casa (no Vercel/Actions IP).
    - Default: NON sovrascrive ticker già presenti nel file (incremental). Usa --force per refresh.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger(__name__)


# ─── Fetch core ──────────────────────────────────────────────────────────────

def fetch_ticker_metadata(ticker: str) -> dict | None:
    """Ritorna dict con sector/industry/beta/market_cap/currency oppure None su errore."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance non installato → pip install yfinance")
        sys.exit(1)
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or not info.get('symbol'):
            return None
        return {
            'ticker': ticker,
            'sector': info.get('sector') or 'Unknown',
            'industry': info.get('industry') or 'Unknown',
            'beta': float(info['beta']) if info.get('beta') is not None else None,
            'market_cap': float(info['marketCap']) if info.get('marketCap') is not None else None,
            'currency': info.get('currency') or 'USD',
            'updated_at': datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.warning(f"{ticker}: fetch failed → {e}")
        return None


def main():
    p = argparse.ArgumentParser(description="Fetch metadata (sector + beta) via yfinance")
    p.add_argument('--universe', choices=['portfolio', 'extended'], default='portfolio')
    p.add_argument('--data-root', type=str, default='data')
    p.add_argument('--sleep', type=float, default=0.0,
                   help="Pausa fra ticker (s) per evitare rate limit (default 0)")
    p.add_argument('--force', action='store_true',
                   help="Refresh anche ticker già presenti (default: incremental)")
    p.add_argument('--output', type=str, default=None,
                   help="Output path (default: <data-root>/meta/sector_beta.parquet)")
    args = p.parse_args()

    loader = DataLakeLoader(data_root=args.data_root)
    tickers = loader.list_tickers(args.universe, apply_filters=False)
    logger.info(f"Universe '{args.universe}': {len(tickers)} ticker da processare")

    out_path = Path(args.output) if args.output else (Path(args.data_root) / 'meta' / 'sector_beta.parquet')
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Incremental: carica esistente
    existing = pd.DataFrame()
    if out_path.exists() and not args.force:
        existing = pd.read_parquet(out_path)
        logger.info(f"Existing metadata: {len(existing)} ticker già presenti — skip (usa --force per refresh)")
        already_done = set(existing['ticker'].tolist())
        tickers = [t for t in tickers if t not in already_done]
        logger.info(f"Da fetchare: {len(tickers)}")

    new_rows = []
    for i, tk in enumerate(tickers, 1):
        meta = fetch_ticker_metadata(tk)
        if meta:
            new_rows.append(meta)
            beta_str = f"beta={meta['beta']:.2f}" if meta['beta'] is not None else "beta=NA"
            logger.info(f"[{i}/{len(tickers)}] {tk}: sector={meta['sector']}  {beta_str}")
        else:
            new_rows.append({
                'ticker': tk, 'sector': 'Unknown', 'industry': 'Unknown',
                'beta': None, 'market_cap': None, 'currency': None,
                'updated_at': datetime.utcnow().isoformat(),
            })
            logger.warning(f"[{i}/{len(tickers)}] {tk}: no data, fallback Unknown")
        if args.sleep > 0:
            time.sleep(args.sleep)

    # Merge con esistente
    df_new = pd.DataFrame(new_rows)
    if not existing.empty:
        df = pd.concat([existing, df_new], ignore_index=True)
        # Dedup: keep last (più recente)
        df = df.drop_duplicates(subset='ticker', keep='last').reset_index(drop=True)
    else:
        df = df_new

    df.to_parquet(out_path, index=False)
    logger.info(f"Saved: {out_path}  ({len(df)} ticker totali, {len(df_new)} nuovi/aggiornati)")

    # Summary diagnostica
    by_sector = df.groupby('sector').size().sort_values(ascending=False)
    logger.info(f"\nDistribuzione settori:\n{by_sector.to_string()}")
    n_with_beta = df['beta'].notna().sum()
    logger.info(f"\nTicker con beta disponibile: {n_with_beta}/{len(df)}")
    if n_with_beta:
        logger.info(f"Beta range: {df['beta'].min():.2f} → {df['beta'].max():.2f}  mean={df['beta'].mean():.2f}")


if __name__ == '__main__':
    main()
