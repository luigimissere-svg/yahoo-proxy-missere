"""
Data Lake Validation — Quant Framework v3.0
============================================

Controlli qualità sul data lake scaricato. Output report JSON + CSV.

Esegui DOPO initial_download.py, PRIMA di committare.

Controlli:
  1. Copertura: ogni ticker ha >= MIN_COVERAGE_PCT delle barre attese
  2. Gap detection: nessun gap > MAX_GAP_DAYS feriali
  3. Outlier prices: nessun jump intraday > MAX_DAILY_MOVE_PCT senza split
  4. Volume sanity: % barre con volume=0 < MAX_ZERO_VOL_PCT
  5. Benchmark presence: tutti i benchmark essenziali presenti
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
BENCH_DIR = DATA_DIR / "benchmarks"
META_DIR = DATA_DIR / "meta"
REPORT_PATH = DATA_DIR / "_validation_report.json"
CSV_REPORT_PATH = DATA_DIR / "_validation_report.csv"

# === Thresholds ===
EXPECTED_TRADING_DAYS = 504  # ~24 mesi
MIN_COVERAGE_PCT = 0.80
MAX_GAP_DAYS = 5
MAX_DAILY_MOVE_PCT = 50.0
MAX_ZERO_VOL_PCT = 0.05
ESSENTIAL_BENCHMARKS = ["^GSPC", "^STOXX", "FTSEMIB.MI", "^VIX"]


def validate_file(path: Path) -> dict:
    try:
        df = pd.read_parquet(path)
    except Exception as e:
        return {"ticker": path.stem, "status": "READ_ERROR", "error": str(e)[:200]}
    
    if df.empty:
        return {"ticker": path.stem, "status": "EMPTY"}
    
    if "date" not in df.columns:
        return {"ticker": path.stem, "status": "NO_DATE_COL"}
    
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)
    coverage = n / EXPECTED_TRADING_DAYS
    
    # Gap detection
    df["date"] = pd.to_datetime(df["date"])
    df["delta_days"] = df["date"].diff().dt.days.fillna(0)
    max_gap = int(df["delta_days"].max())
    n_big_gaps = int((df["delta_days"] > MAX_GAP_DAYS).sum())
    
    # Outliers (jump > X% without split)
    if "close" in df.columns:
        df["pct_change"] = df["close"].pct_change().abs() * 100
        n_outliers = int((df["pct_change"] > MAX_DAILY_MOVE_PCT).sum())
        max_move = float(df["pct_change"].max() or 0)
    else:
        n_outliers = -1
        max_move = -1
    
    # Volume sanity
    if "volume" in df.columns:
        zero_vol_pct = float((df["volume"] == 0).sum() / max(n, 1))
    else:
        zero_vol_pct = -1
    
    # Verdict
    issues = []
    if coverage < MIN_COVERAGE_PCT: issues.append(f"low_coverage({coverage:.0%})")
    if n_big_gaps > 0: issues.append(f"gaps({n_big_gaps})")
    if n_outliers > 0: issues.append(f"outliers({n_outliers})")
    if zero_vol_pct > MAX_ZERO_VOL_PCT: issues.append(f"zero_vol({zero_vol_pct:.0%})")
    
    return {
        "ticker": path.stem,
        "status": "OK" if not issues else "WARN",
        "rows": n,
        "coverage": round(coverage, 3),
        "date_start": str(df["date"].min().date()),
        "date_end": str(df["date"].max().date()),
        "max_gap_days": max_gap,
        "n_gaps_big": n_big_gaps,
        "n_outliers": n_outliers,
        "max_move_pct": round(max_move, 2),
        "zero_vol_pct": round(zero_vol_pct, 4),
        "issues": ";".join(issues) if issues else "",
    }


def main():
    print(f"\n{'='*60}\n Data Lake Validation\n{'='*60}\n")
    
    rows = []
    for d in (OHLCV_DIR, BENCH_DIR):
        files = sorted(d.glob("*.parquet"))
        print(f"📁 {d.name}: {len(files)} file")
        for f in files:
            rows.append({"folder": d.name, **validate_file(f)})
    
    df = pd.DataFrame(rows)
    
    # Summary
    n_ok = (df["status"] == "OK").sum()
    n_warn = (df["status"] == "WARN").sum()
    n_err = (~df["status"].isin(["OK", "WARN"])).sum()
    
    print(f"\n✓ OK:     {n_ok}")
    print(f"⚠ WARN:   {n_warn}")
    print(f"✗ ERROR:  {n_err}")
    
    # Check essential benchmarks
    missing_bench = [b for b in ESSENTIAL_BENCHMARKS if not (BENCH_DIR / f"{b}.parquet").exists()]
    if missing_bench:
        print(f"\n🚨 BENCHMARK MANCANTI: {missing_bench}")
    else:
        print(f"\n✓ Tutti i benchmark essenziali presenti")
    
    # Write reports
    df.to_csv(CSV_REPORT_PATH, index=False)
    REPORT_PATH.write_text(json.dumps({
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "n_total": len(df),
        "n_ok": int(n_ok),
        "n_warn": int(n_warn),
        "n_error": int(n_err),
        "missing_benchmarks": missing_bench,
        "thresholds": {
            "min_coverage_pct": MIN_COVERAGE_PCT,
            "max_gap_days": MAX_GAP_DAYS,
            "max_daily_move_pct": MAX_DAILY_MOVE_PCT,
        },
    }, indent=2))
    
    print(f"\n📄 Report: {CSV_REPORT_PATH}")
    print(f"📄 Summary: {REPORT_PATH}\n")
    
    # Print worst cases
    if n_warn > 0:
        worst = df[df["status"] == "WARN"].sort_values("coverage").head(20)
        print(f"Top 20 ticker con issue:")
        print(worst[["ticker", "status", "coverage", "rows", "issues"]].to_string(index=False))


if __name__ == "__main__":
    main()
