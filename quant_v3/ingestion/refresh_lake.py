"""
Data Lake Incremental Refresh — Quant Framework v3.0
=====================================================

Aggiorna il data lake con le ultime barre mancanti.
Pensato per essere eseguito da GitHub Actions (cron settimanale).

Per ogni ticker già nel lake:
  1. Legge l'ultima data presente
  2. Scarica solo le barre nuove (start = last_date + 1)
  3. Append al parquet esistente

Ticker mancanti: NON scaricati (servirebbe initial_download.py).

USO:
  python ingestion/refresh_lake.py
  python ingestion/refresh_lake.py --benchmarks-only    # quick refresh
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("ERRORE: yfinance non installato")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
BENCH_DIR = DATA_DIR / "benchmarks"
LOG_PATH = DATA_DIR / "_refresh_log.json"

SLEEP_SEC = 0.4
TODAY = datetime.now().date()


def refresh_ticker(path: Path) -> dict:
    ticker = path.stem
    try:
        existing = pd.read_parquet(path)
        if existing.empty or "date" not in existing.columns:
            return {"ticker": ticker, "status": "EMPTY_EXISTING", "added": 0}
        
        last_date = pd.to_datetime(existing["date"]).max().date()
        start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        if pd.Timestamp(start).date() >= TODAY:
            return {"ticker": ticker, "status": "UP_TO_DATE", "added": 0}
        
        t = yf.Ticker(ticker)
        new = t.history(start=start, end=TODAY.strftime("%Y-%m-%d"), auto_adjust=False, actions=True)
        
        if new is None or new.empty:
            return {"ticker": ticker, "status": "NO_NEW_DATA", "added": 0}
        
        new = new.reset_index()
        new.columns = [c.lower().replace(" ", "_") for c in new.columns]
        if "date" not in new.columns and "datetime" in new.columns:
            new = new.rename(columns={"datetime": "date"})
        if pd.api.types.is_datetime64_any_dtype(new["date"]):
            try:
                new["date"] = pd.to_datetime(new["date"]).dt.tz_localize(None)
            except Exception:
                new["date"] = pd.to_datetime(new["date"])
        new["ticker"] = ticker
        
        combined = pd.concat([existing, new], ignore_index=True)
        combined = combined.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
        combined.to_parquet(path, compression="snappy", index=False)
        
        return {"ticker": ticker, "status": "OK", "added": len(new), "new_end": str(new["date"].max().date())}
    except Exception as e:
        return {"ticker": ticker, "status": "ERROR", "error": str(e)[:200], "added": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmarks-only", action="store_true")
    args = parser.parse_args()
    
    dirs = [BENCH_DIR] if args.benchmarks_only else [OHLCV_DIR, BENCH_DIR]
    
    all_files = []
    for d in dirs:
        if d.exists():
            all_files.extend(sorted(d.glob("*.parquet")))
    
    print(f"\n{'='*60}\n Incremental Refresh — {TODAY}\n Files: {len(all_files)}\n{'='*60}\n")
    
    t0 = time.time()
    results = []
    n_updated = 0
    n_uptodate = 0
    n_error = 0
    
    for i, f in enumerate(all_files, 1):
        r = refresh_ticker(f)
        results.append(r)
        
        if r["status"] == "OK":
            n_updated += 1
            print(f"[{i:>4d}/{len(all_files)}] {r['ticker']:<12s} ✓ +{r['added']} rows → {r.get('new_end','?')}")
        elif r["status"] in ("UP_TO_DATE", "NO_NEW_DATA"):
            n_uptodate += 1
        else:
            n_error += 1
            print(f"[{i:>4d}/{len(all_files)}] {r['ticker']:<12s} ✗ {r.get('error', r['status'])[:80]}")
        
        time.sleep(SLEEP_SEC)
    
    log = {
        "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_sec": round(time.time() - t0, 1),
        "n_files": len(all_files),
        "n_updated": n_updated,
        "n_up_to_date": n_uptodate,
        "n_error": n_error,
        "results": results,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2, default=str))
    
    print(f"\n{'='*60}")
    print(f"  ✓ Aggiornati: {n_updated}")
    print(f"  = Già al passo: {n_uptodate}")
    print(f"  ✗ Errori: {n_error}")
    print(f"  ⏱ Durata: {(time.time()-t0)/60:.1f} min")
    print(f"  📄 Log: {LOG_PATH}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
