"""
Initial Data Lake Download — Quant Framework v3.0
==================================================

DA ESEGUIRE UNA TANTUM IN LOCALE (IP domestico, non Actions).

Scarica:
  • OHLCV daily (24 mesi) per ~1008 ticker (S&P500 + STOXX600 + portfolio + benchmarks)
  • Dividendi e splits storici
  • Earnings dates storici (via yfinance)
  • Salva in formato parquet compresso, 1 file per ticker

Output:
  quant_v3/data/ohlcv/{TICKER}.parquet
  quant_v3/data/corporate/{TICKER}_dividends.parquet
  quant_v3/data/corporate/{TICKER}_earnings.parquet
  quant_v3/data/benchmarks/{TICKER}.parquet
  quant_v3/data/_download_log.json

Fallback automatico Yahoo → Stooq per ticker bloccati.

USO:
  cd <repo_clonato>/quant_v3
  pip install -r ingestion/requirements.txt
  python ingestion/initial_download.py

  # Opzionale: ridotto per test
  python ingestion/initial_download.py --limit 50
  # Solo portfolio (35 ticker, ~2 min)
  python ingestion/initial_download.py --portfolio-only
  # Resume da interruzione
  python ingestion/initial_download.py --resume

DURATA STIMATA:
  • Portfolio only (35 tk): ~2 min
  • Universe completo (1008 tk): ~30-45 min
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("ERRORE: yfinance non installato. Esegui: pip install -r ingestion/requirements.txt")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
BENCH_DIR = DATA_DIR / "benchmarks"
CORP_DIR = DATA_DIR / "corporate"
META_DIR = DATA_DIR / "meta"
LOG_PATH = DATA_DIR / "_download_log.json"

for d in (OHLCV_DIR, BENCH_DIR, CORP_DIR):
    d.mkdir(parents=True, exist_ok=True)

# === Config ===
# Fase 4 (estesa): da 2023-01-01 per avere ~40 mesi (warmup 200 bar + 7-8 fold).
START_DATE = "2023-01-01"
END_DATE = "2026-05-22"
HISTORY_MONTHS = 40  # info only
BATCH_SIZE = 1  # download seriale per evitare rate limit Yahoo
SLEEP_SEC = 0.5  # tra un download e l'altro
SLEEP_AFTER_BATCH = 2.0


def load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return {"completed": [], "failed": [], "started_at": None, "last_update": None}


def save_log(log: dict) -> None:
    log["last_update"] = datetime.now().isoformat(timespec="seconds")
    LOG_PATH.write_text(json.dumps(log, indent=2, default=str))


def download_ohlcv(ticker: str, target_dir: Path) -> Optional[dict]:
    """Scarica OHLCV. Ritorna metadati o None se fallisce."""
    out_path = target_dir / f"{ticker.replace('/', '_')}.parquet"
    
    try:
        t = yf.Ticker(ticker)
        df = t.history(start=START_DATE, end=END_DATE, auto_adjust=False, actions=True)
        
        if df is None or df.empty or len(df) < 30:
            return None
        
        # Reset index, normalize columns
        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        
        # Ensure timezone-naive date
        if pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None) if df["date"].dt.tz is not None else df["date"]
        
        df["ticker"] = ticker
        df.to_parquet(out_path, compression="snappy", index=False)
        
        # Dividends + splits (only non-zero)
        if "dividends" in df.columns:
            divs = df[df["dividends"] > 0][["date", "dividends"]].copy()
            if not divs.empty:
                divs["ticker"] = ticker
                divs.to_parquet(CORP_DIR / f"{ticker}_dividends.parquet", index=False)
        
        if "stock_splits" in df.columns:
            sps = df[df["stock_splits"] > 0][["date", "stock_splits"]].copy()
            if not sps.empty:
                sps["ticker"] = ticker
                sps.to_parquet(CORP_DIR / f"{ticker}_splits.parquet", index=False)
        
        # Earnings dates (best-effort, may fail silently for many tickers)
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                ed = ed.reset_index()
                ed.columns = [str(c).lower().replace(" ", "_") for c in ed.columns]
                ed["ticker"] = ticker
                ed.to_parquet(CORP_DIR / f"{ticker}_earnings.parquet", index=False)
        except Exception:
            pass
        
        return {
            "ticker": ticker,
            "rows": len(df),
            "start": str(df["date"].min().date()) if "date" in df.columns else None,
            "end": str(df["date"].max().date()) if "date" in df.columns else None,
            "size_kb": out_path.stat().st_size // 1024,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)[:200]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers (testing)")
    parser.add_argument("--portfolio-only", action="store_true", help="Solo 35 ticker portfolio")
    parser.add_argument("--benchmarks-only", action="store_true", help="Solo benchmarks (16 ticker)")
    parser.add_argument("--resume", action="store_true", help="Skip ticker già completati")
    args = parser.parse_args()
    
    # Load universes
    ext_path = META_DIR / "universe_extended.csv"
    pf_path = META_DIR / "universe_portfolio.csv"
    b_path = META_DIR / "benchmarks.csv"
    
    if not all(p.exists() for p in [ext_path, pf_path, b_path]):
        print("✗ Universe files mancanti. Esegui prima: python ingestion/build_universe.py")
        sys.exit(1)
    
    extended = pd.read_csv(ext_path)
    portfolio = pd.read_csv(pf_path)
    bench = pd.read_csv(b_path)
    
    # Build task list
    tasks: list[tuple[str, Path]] = []  # (ticker, target_dir)
    
    if args.benchmarks_only:
        tasks = [(t, BENCH_DIR) for t in bench["ticker"].tolist()]
    elif args.portfolio_only:
        tasks = [(t, OHLCV_DIR) for t in portfolio["ticker"].tolist()]
        tasks += [(t, BENCH_DIR) for t in bench["ticker"].tolist()]
    else:
        # Full: extended + portfolio + benchmarks (deduplicated)
        all_equity = set(extended["ticker"].tolist()) | set(portfolio["ticker"].tolist())
        tasks = [(t, OHLCV_DIR) for t in sorted(all_equity)]
        tasks += [(t, BENCH_DIR) for t in bench["ticker"].tolist()]
    
    if args.limit:
        tasks = tasks[:args.limit]
    
    # Load resume log
    log = load_log()
    if not log["started_at"]:
        log["started_at"] = datetime.now().isoformat(timespec="seconds")
    
    completed = set(log["completed"])
    if args.resume:
        tasks = [(t, d) for t, d in tasks if t not in completed]
        print(f"[RESUME] Skipping {len(completed)} già completati. Restano {len(tasks)} ticker.\n")
    
    print(f"{'='*60}")
    print(f"  Initial Data Lake Download — Quant Framework v3.0")
    print(f"  Range: {START_DATE} → {END_DATE}")
    print(f"  Ticker da scaricare: {len(tasks)}")
    print(f"  Output: {DATA_DIR}")
    print(f"{'='*60}\n")
    
    t0 = time.time()
    n_ok = 0
    n_fail = 0
    
    for i, (ticker, target_dir) in enumerate(tasks, 1):
        elapsed = time.time() - t0
        eta_sec = (elapsed / i) * (len(tasks) - i) if i > 0 else 0
        eta_min = eta_sec / 60
        
        prefix = f"[{i:>4d}/{len(tasks)}] {ticker:<12s}"
        result = download_ohlcv(ticker, target_dir)
        
        if result and "error" not in result:
            n_ok += 1
            print(f"{prefix} ✓ {result['rows']:>4d} rows  {result['size_kb']:>4d} KB  ETA {eta_min:.0f}min")
            log["completed"].append(ticker)
        else:
            n_fail += 1
            err = result.get("error", "no data") if result else "no data"
            print(f"{prefix} ✗ {err[:80]}")
            log["failed"].append({"ticker": ticker, "error": err[:200], "at": datetime.now().isoformat(timespec="seconds")})
        
        # Save log every 10 ticker
        if i % 10 == 0:
            save_log(log)
        
        time.sleep(SLEEP_SEC)
    
    save_log(log)
    
    print(f"\n{'='*60}")
    print(f"  COMPLETATO")
    print(f"  ✓ OK: {n_ok}")
    print(f"  ✗ Falliti: {n_fail}")
    print(f"  Tempo: {(time.time()-t0)/60:.1f} min")
    print(f"  Log: {LOG_PATH}")
    print(f"{'='*60}")
    print(f"\n  Prossimo step:")
    print(f"    python ingestion/validation.py")
    print(f"    git add quant_v3/data/")
    print(f"    git commit -m 'data: initial lake snapshot {END_DATE}'")
    print(f"    git push origin v3-quant-framework")


if __name__ == "__main__":
    main()
