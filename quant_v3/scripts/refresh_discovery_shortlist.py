"""
Refresh Discovery Shortlist (mar-ven, run veloce)
==================================================

Aggiorna SOLO i titoli già emersi nello snapshot Discovery del lunedì,
senza rifare lo scan completo sui 1.010 candidati. Cosa fa:

  1. Legge lo snapshot esistente (discovery_snapshot.json)
  2. Estrae la "shortlist" = tutti i ticker che compaiono in
     global_top + by_region[*].buy/sell/watch (~150-250 ticker totali)
  3. Per ognuno: fetch storico 3mo + ricalcolo completo degli indicatori v2
  4. Aggiorna in-place i campi: price, var_pct_24h, rsi, ma50_dist, vol_z,
     atr_pct, rs_delta, composite_score, action, base_tag
  5. NON rifa il ranking globale (la composizione delle liste resta del lunedì,
     così la "shortlist della settimana" è stabile e confrontabile)
  6. Aggiorna _meta.last_refresh con il timestamp del refresh quotidiano

Performance: ~150-250 fetch × 0.2s sleep ≈ 1-1.5 minuti.

Esecuzione manuale:
  python quant_v3/scripts/refresh_discovery_shortlist.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import helper dallo script principale per condividere la logica
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_discovery_snapshot import (  # noqa: E402
    OUT_JSON,
    BENCH_US, BENCH_EU, BENCH_IT,
    SLEEP_BETWEEN_FETCHES,
    fetch_hist,
    compute_var_pct,
    compute_atr_pct,
    adaptive_thresholds,
    compute_volume_zscore,
    compute_rsi,
    compute_ma_distance,
    mean_reversion_score,
    compute_relative_strength,
    classify_signal,
    composite_score,
    action_label,
    median_volume,
    passes_quality_filters,
)


def fetch_benchmark_variations() -> dict[str, float | None]:
    """Fetch variazione % 24h per i 3 benchmark."""
    out: dict[str, float | None] = {}
    for region, symbol in [("US", BENCH_US), ("EU", BENCH_EU), ("IT", BENCH_IT)]:
        hist = fetch_hist(symbol, "5d", "1d")
        var = compute_var_pct(hist) if hist else None
        out[region] = var
        time.sleep(SLEEP_BETWEEN_FETCHES)
    return out


def collect_shortlist(snapshot: dict) -> list[dict[str, Any]]:
    """
    Estrae la shortlist di ticker da rinfrescare. Restituisce una lista di
    candidati (ognuno è un dict completo dello snapshot precedente) deduplicata
    per ticker. La PRIMA occorrenza viene mantenuta (così se un ticker è in più
    liste, prendiamo il dict più recente come base).
    """
    seen: set[str] = set()
    shortlist: list[dict[str, Any]] = []

    # Sorgenti: global_top + by_region * (buy/sell/watch)
    sources: list[list[dict[str, Any]]] = []
    sources.append(snapshot.get("global_top", []))
    by_region = snapshot.get("by_region", {})
    for region in ("US", "EU", "IT"):
        block = by_region.get(region, {})
        sources.append(block.get("buy", []))
        sources.append(block.get("sell", []))
        sources.append(block.get("watch", []))

    for src in sources:
        for c in src:
            tkr = c.get("ticker")
            if tkr and tkr not in seen:
                seen.add(tkr)
                shortlist.append(c)
    return shortlist


def refresh_candidate(c: dict[str, Any], bench_var: dict[str, float | None]) -> dict[str, Any] | None:
    """Ricalcola tutti gli indicatori v2 per un singolo candidato.
    Ritorna il dict aggiornato, o None se il fetch fallisce.
    """
    ticker = c["ticker"]
    region = c.get("region", "EU")

    hist = fetch_hist(ticker, "3mo", "1d")
    if not hist:
        return None

    price = hist.get("regular_price")
    if not price:
        closes = [x for x in hist["close"] if x is not None]
        price = closes[-1] if closes else None

    currency = hist.get("currency") or c.get("currency")

    var_pct = compute_var_pct(hist)
    if var_pct is None:
        return None

    atr_pct = compute_atr_pct(hist)
    vol_median_val = median_volume(hist)

    # Filtri qualitativi: se il titolo non passa più, lo segniamo ma manteniamo i vecchi dati
    passed, reason = passes_quality_filters(price, atr_pct, vol_median_val, currency)
    if not passed:
        c = dict(c)
        c["_filter_warning"] = reason
        # Aggiorniamo comunque i campi calcolati
        c["price"] = round(price, 4) if price else c.get("price")
        c["var_pct_24h"] = var_pct
        c["atr_pct"] = atr_pct
        return c

    thresh = adaptive_thresholds(atr_pct)
    tag, base_score = classify_signal(var_pct, thresh)
    vol_z = compute_volume_zscore(hist)
    rsi = compute_rsi(hist)
    ma_dist = compute_ma_distance(hist)
    mr_score = mean_reversion_score(rsi, ma_dist)
    rs_delta = compute_relative_strength(var_pct, bench_var.get(region))
    composite = composite_score(base_score, rs_delta, mr_score, vol_z)
    action = action_label(composite)

    updated = dict(c)
    updated.update({
        "price": round(price, 4) if price else c.get("price"),
        "currency": currency,
        "var_pct_24h": var_pct,
        "atr_pct": atr_pct,
        "rsi": rsi,
        "ma50_dist": ma_dist,
        "vol_z": vol_z,
        "rs_delta": rs_delta,
        "base_tag": tag,
        "composite_score": composite,
        "action": action,
    })
    # Pulisci eventuale warning precedente
    updated.pop("_filter_warning", None)
    return updated


def apply_refresh_to_snapshot(snapshot: dict, refreshed_by_ticker: dict[str, dict[str, Any]]) -> dict:
    """
    Applica gli update in-place a tutte le sezioni dello snapshot.
    Mantiene l'ordine originale delle liste.
    """
    def update_list(lst: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for c in lst:
            t = c.get("ticker")
            if t and t in refreshed_by_ticker:
                out.append(refreshed_by_ticker[t])
            else:
                out.append(c)
        return out

    snapshot["global_top"] = update_list(snapshot.get("global_top", []))
    by_region = snapshot.get("by_region", {})
    for region in ("US", "EU", "IT"):
        block = by_region.get(region, {})
        for key in ("buy", "sell", "watch"):
            block[key] = update_list(block.get(key, []))
        by_region[region] = block
    snapshot["by_region"] = by_region
    return snapshot


def main() -> int:
    print(f"[Refresh] Loading snapshot from {OUT_JSON}")
    if not OUT_JSON.exists():
        print(f"  ! snapshot non trovato. Esegui prima generate_discovery_snapshot.py.")
        return 1

    with open(OUT_JSON, encoding="utf-8") as f:
        snapshot = json.load(f)

    shortlist = collect_shortlist(snapshot)
    print(f"  Shortlist: {len(shortlist)} titoli unici da rinfrescare")

    print(f"\n[1/3] Fetching benchmark variations...")
    bench_var = fetch_benchmark_variations()
    print(f"  US={bench_var['US']}% EU={bench_var['EU']}% IT={bench_var['IT']}%")

    print(f"\n[2/3] Refreshing {len(shortlist)} candidates...")
    t0 = time.time()
    refreshed: dict[str, dict[str, Any]] = {}
    fail = 0
    for i, c in enumerate(shortlist):
        if i % 25 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / max(elapsed, 0.1)
            eta = (len(shortlist) - i) / max(rate, 0.01)
            print(f"  [{i+1}/{len(shortlist)}] {c.get('ticker','?'):14s} | refreshed={len(refreshed)} fail={fail} | ETA {eta:.0f}s")
        updated = refresh_candidate(c, bench_var)
        time.sleep(SLEEP_BETWEEN_FETCHES)
        if updated:
            refreshed[updated["ticker"]] = updated
        else:
            fail += 1

    elapsed_total = time.time() - t0
    print(f"\n  Refreshed: {len(refreshed)} | Failed: {fail} | Tempo: {elapsed_total:.1f}s")

    print(f"\n[3/3] Applying updates to snapshot...")
    snapshot = apply_refresh_to_snapshot(snapshot, refreshed)

    # Aggiorna meta
    meta = snapshot.get("_meta", {})
    meta["last_refresh_at"] = datetime.now(timezone.utc).isoformat()
    meta["last_refresh_count"] = len(refreshed)
    meta["last_refresh_failures"] = fail
    meta["last_refresh_benchmark"] = bench_var
    meta["last_refresh_elapsed_seconds"] = round(elapsed_total, 1)
    snapshot["_meta"] = meta

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"  Snapshot scritto su {OUT_JSON}")

    # Preview top 10 by abs(composite)
    all_candidates: list[dict[str, Any]] = list(refreshed.values())
    all_candidates.sort(key=lambda x: abs(x.get("composite_score") or 0), reverse=True)
    print(f"\n{'=' * 72}")
    print("TOP 10 DOPO REFRESH (per |composite_score|)")
    print(f"{'=' * 72}")
    print(f"{'Ticker':<14s} {'Reg':<4s} {'Var%':>7s} {'RSI':>5s} {'Score':>7s} {'Action':<20s}")
    print("-" * 72)
    for r in all_candidates[:10]:
        ticker = r["ticker"]
        reg = r.get("region", "?")
        var = r.get("var_pct_24h") or 0
        rsi = r.get("rsi") or 0
        score = r.get("composite_score") or 0
        action = (r.get("action") or "")[:18]
        print(f"{ticker:<14s} {reg:<4s} {var:>+7.2f} {rsi:>5.1f} {score:>+7.2f} {action:<20s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
