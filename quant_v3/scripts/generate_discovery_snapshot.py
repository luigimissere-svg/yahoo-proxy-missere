"""
Generate Discovery Snapshot v2 — Motore Quant completo
=======================================================

Versione 2.0 del generatore Discovery. Applica lo STESSO motore composito dei
"Segnali del giorno" v2 ai 1.036 titoli dell'universo allargato (escluso il
portafoglio), producendo uno snapshot con indicatori completi per ogni
candidato:

  - var_pct_24h: variazione % 24h (da last close / prev close)
  - atr_pct:    Average True Range % (volatilità storica 14gg)
  - rsi:        RSI 14 Wilder
  - ma50_dist:  distanza % dal prezzo dalla MA50
  - vol_z:      volume z-score (oggi vs media 20gg)
  - rs_delta:   relative strength vs benchmark di regione
  - composite_score: score finale in range [-10, +10]
  - action:     etichetta STRONG BUY / BUY / ACCUMULATE / HOLD / MONITOR / REDUCE / STRONG SELL

Differenze chiave vs v1:
  - v1 usava solo variazione_pct dal endpoint quotes (score in ±1)
  - v2 fetcha storico 3mo via Yahoo Chart API direttamente (no proxy) per
    ognuno dei ~1010 candidati e calcola tutti gli indicatori v2
  - Score range esteso a ±10 per coerenza con Segnali del giorno
  - Filtri qualitativi: ATR<8% (no volatilità eccessiva), volume
    mediano 20gg > 100K azioni (no illiquidità), prezzo > 1$ (no penny stock)

Performance attesa:
  - ~1010 fetch_hist sequenziali con sleep 0.2s = 10-15 minuti totali
  - Pensato per cron mensile, non per uso interattivo

Output:
  quant_v3/discovery_snapshot.json (formato compatibile con DiscoveryBox v1)

Esecuzione:
  python quant_v3/scripts/generate_discovery_snapshot.py [--top-n 30] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev, median
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]  # quant_v3/
UNIVERSE_CSV = ROOT / "data" / "meta" / "universe_extended.csv"
PORTFOLIO_CSV = ROOT / "data" / "meta" / "universe_portfolio.csv"
OUT_JSON = ROOT / "discovery_snapshot.json"

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"

REGIONS_MAP = {
    "SP500": "US",
    "NASDAQ100": "US",
    "STOXX600": "EU",
    "FTSE_MIB": "IT",
    "FTSE_ITALIA_MID_CAP": "IT",
    "PORTFOLIO_MISSERE": "PORTFOLIO",
}

# Benchmark per regione
BENCH_US = "^GSPC"     # S&P 500
BENCH_EU = "^STOXX"    # STOXX Europe 600
BENCH_IT = "FTSEMIB.MI"  # FTSE MIB

# Filtri qualitativi
MAX_ATR_PCT = 8.0       # esclude titoli con ATR > 8% (volatilità eccessiva)
MIN_VOL_MEDIAN = 100000  # esclude titoli con volume mediano 20gg < 100K
MIN_PRICE_USD = 1.0     # esclude penny stock (in valuta locale, soglia conservativa)

# Rate-limit verso Yahoo Chart API
SLEEP_BETWEEN_FETCHES = 0.2


# ============================================================================
# Universe + portfolio loading
# ============================================================================

def load_universe() -> list[dict[str, str]]:
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_portfolio_tickers() -> set[str]:
    if not PORTFOLIO_CSV.exists():
        return set()
    with open(PORTFOLIO_CSV, newline="", encoding="utf-8") as f:
        return {row["ticker"].strip() for row in csv.DictReader(f) if row.get("ticker")}


def region_for(idx_membership: str) -> str:
    parts = [p.strip() for p in idx_membership.split(";") if p.strip()]
    has_it = any(p in {"FTSE_MIB", "FTSE_ITALIA_MID_CAP"} for p in parts)
    if has_it:
        return "IT"
    for p in parts:
        r = REGIONS_MAP.get(p)
        if r == "EU":
            return "EU"
        if r == "US":
            return "US"
    return "EU"


def benchmark_for_region(region: str) -> str:
    if region == "US":
        return BENCH_US
    if region == "IT":
        return BENCH_IT
    return BENCH_EU


# ============================================================================
# Yahoo Chart API — fetch storico OHLCV
# ============================================================================

def fetch_hist(symbol: str, range_str: str = "3mo", interval: str = "1d"):
    """Recupera serie storica OHLCV dal Yahoo Chart API."""
    url = f"{YAHOO_CHART}{symbol}?range={range_str}&interval={interval}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "discovery-v2/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        chart = data.get("chart", {}).get("result", [None])[0]
        if not chart:
            return None
        meta = chart.get("meta", {})
        timestamps = chart.get("timestamp", [])
        quote = chart.get("indicators", {}).get("quote", [{}])[0]
        return {
            "ts": timestamps,
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
            "currency": meta.get("currency"),
            "regular_price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose") or meta.get("previousClose"),
        }
    except Exception:
        return None


# ============================================================================
# Indicatori (clonati da scripts/signals_v2_engine.py)
# ============================================================================

def compute_var_pct(hist: dict) -> float | None:
    """Variazione % 24h: last close vs penultimo close della serie.

    NB: Yahoo `chartPreviousClose` è il close del giorno PRIMA dell'inizio del
    range (3mo fa), quindi non utile. Usiamo sempre closes[-2] → closes[-1].
    """
    if not hist:
        return None
    closes = [c for c in hist["close"] if c is not None]
    if len(closes) < 2:
        return None
    last = closes[-1]
    prev = closes[-2]
    if not prev:
        return None
    return round(((last - prev) / prev) * 100, 2)


def compute_atr_pct(hist: dict, period: int = 14) -> float | None:
    if not hist or not hist["close"]:
        return None
    closes = [c for c in hist["close"] if c is not None]
    highs = [h for h in hist["high"] if h is not None]
    lows = [l for l in hist["low"] if l is not None]
    if len(closes) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return None
    # Allinea le lunghezze (Yahoo a volte ha gap)
    n = min(len(closes), len(highs), len(lows))
    closes, highs, lows = closes[-n:], highs[-n:], lows[-n:]
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = mean(trs[-period:])
    last_close = closes[-1]
    return round((atr / last_close) * 100, 2) if last_close else None


def adaptive_thresholds(atr_pct: float | None) -> dict:
    if atr_pct is None or atr_pct < 0.3:
        return {
            "opportunity": -5.0, "caution": -2.0, "rally": 2.0, "momentum": 5.0,
            "atr_pct": None, "method": "static",
        }
    return {
        "opportunity": round(-2.5 * atr_pct, 2),
        "caution": round(-1.0 * atr_pct, 2),
        "rally": round(1.0 * atr_pct, 2),
        "momentum": round(2.5 * atr_pct, 2),
        "atr_pct": round(atr_pct, 2),
        "method": "adaptive",
    }


def compute_volume_zscore(hist: dict, window: int = 20) -> float | None:
    if not hist or not hist["volume"]:
        return None
    vols = [v for v in hist["volume"] if v is not None and v > 0]
    if len(vols) < window + 1:
        return None
    today = vols[-1]
    historical = vols[-window-1:-1]
    mu = mean(historical)
    sigma = stdev(historical) if len(historical) > 1 else 1
    if sigma == 0:
        return None
    return round((today - mu) / sigma, 2)


def median_volume(hist: dict, window: int = 20) -> float | None:
    if not hist or not hist["volume"]:
        return None
    vols = [v for v in hist["volume"] if v is not None and v > 0]
    if len(vols) < 5:
        return None
    return median(vols[-window:])


def compute_rsi(hist: dict, period: int = 14) -> float | None:
    if not hist or not hist["close"]:
        return None
    closes = [c for c in hist["close"] if c is not None]
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = mean(gains[-period:])
    avg_loss = mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100/(1+rs), 1)


def compute_ma_distance(hist: dict, period: int = 50) -> float | None:
    if not hist or not hist["close"]:
        return None
    closes = [c for c in hist["close"] if c is not None]
    if len(closes) < period:
        return None
    ma = mean(closes[-period:])
    last = closes[-1]
    if ma == 0:
        return None
    return round(((last - ma) / ma) * 100, 2)


def mean_reversion_score(rsi: float | None, ma_dist: float | None) -> int | None:
    if rsi is None or ma_dist is None:
        return None
    score = 0
    if rsi < 30:
        score += 2
    elif rsi < 40:
        score += 1
    elif rsi > 70:
        score -= 2
    elif rsi > 60:
        score -= 1

    if ma_dist < -10:
        score += 2
    elif ma_dist < -5:
        score += 1
    elif ma_dist > 15:
        score -= 2
    elif ma_dist > 10:
        score -= 1
    return score


def compute_relative_strength(ticker_var: float | None, bench_var: float | None) -> float | None:
    if ticker_var is None or bench_var is None:
        return None
    return round(ticker_var - bench_var, 2)


def classify_signal(var_pct: float | None, thresholds: dict) -> tuple[str, int]:
    if var_pct is None:
        return "NEUTRAL", 0
    if var_pct <= thresholds["opportunity"]:
        return "OPPORTUNITY", -4
    if var_pct <= thresholds["caution"]:
        return "CAUTION", -2
    if var_pct >= thresholds["momentum"]:
        return "MOMENTUM", 4
    if var_pct >= thresholds["rally"]:
        return "RALLY", 2
    return "NEUTRAL", 0


def composite_score(
    base_score: int,
    rs_delta: float | None,
    mr_score: int | None,
    vol_z: float | None,
) -> float:
    """
    Score finale composito (range -10 a +10).
    Versione Discovery: stesso scoring del v2 engine, ma SENZA persistence
    (non abbiamo storico segnali per i 1010 candidati extra-watchlist).
    """
    score = float(base_score)
    if rs_delta is not None:
        score += rs_delta * 0.3
    if mr_score is not None:
        score += mr_score * 0.5
    if vol_z is not None:
        score += vol_z * 0.3
    return round(max(-10, min(10, score)), 2)


def action_label(composite: float) -> str:
    if composite >= 5:
        return "🟢 STRONG BUY"
    if composite >= 2:
        return "🟢 BUY"
    if composite >= 0.5:
        return "↗ ACCUMULATE"
    if composite <= -5:
        return "🔴 STRONG SELL"
    if composite <= -2:
        return "🔴 REDUCE"
    if composite <= -0.5:
        return "↘ MONITOR"
    return "⚪ HOLD"


# ============================================================================
# Filtri qualitativi
# ============================================================================

def passes_quality_filters(
    price: float | None,
    atr_pct: float | None,
    vol_median: float | None,
    currency: str | None,
) -> tuple[bool, str]:
    """
    Ritorna (passed, reason_if_failed).
    """
    if price is None:
        return False, "no_price"
    # Penny stock: in valute molto deboli (es. yen/lira) la soglia 1.0 è troppo bassa,
    # ma per US/EUR/GBP è sensata. Per ora applichiamo solo in USD/EUR/GBP/CHF.
    if currency in ("USD", "EUR", "GBP", "CHF") and price < MIN_PRICE_USD:
        return False, f"penny_stock_{price}"
    if atr_pct is not None and atr_pct > MAX_ATR_PCT:
        return False, f"high_volatility_atr_{atr_pct}"
    if vol_median is not None and vol_median < MIN_VOL_MEDIAN:
        return False, f"low_liquidity_vol_{int(vol_median)}"
    return True, ""


# ============================================================================
# Benchmark cache
# ============================================================================

def fetch_benchmarks() -> dict[str, float | None]:
    """Fetch variazione % 24h per i 3 benchmark."""
    out = {}
    for region, symbol in [("US", BENCH_US), ("EU", BENCH_EU), ("IT", BENCH_IT)]:
        print(f"  [bench] Fetch {region} → {symbol}")
        hist = fetch_hist(symbol, "5d", "1d")
        var = compute_var_pct(hist) if hist else None
        out[region] = var
        print(f"    var: {var}%")
        time.sleep(SLEEP_BETWEEN_FETCHES)
    return out


# ============================================================================
# Main
# ============================================================================

def main(top_n: int = 30, limit: int | None = None) -> int:
    print(f"[Discovery v2] Loading universe from {UNIVERSE_CSV}")
    universe = load_universe()
    portfolio = load_portfolio_tickers()
    print(f"  Universe: {len(universe)} titoli")
    print(f"  Portfolio (da escludere): {len(portfolio)} titoli")

    candidates = [r for r in universe if r["ticker"] not in portfolio]
    if limit:
        candidates = candidates[:limit]
        print(f"  LIMIT attivo: prime {limit} candidati")
    print(f"  Candidati Discovery: {len(candidates)}")

    # Fetch benchmark variazioni
    print(f"\n[1/3] Fetching benchmark variations...")
    bench_var = fetch_benchmarks()
    print(f"  Benchmarks: US={bench_var['US']}% EU={bench_var['EU']}% IT={bench_var['IT']}%")

    # Fetch storico per ognuno + calcolo indicatori
    print(f"\n[2/3] Fetching history + computing indicators for {len(candidates)} candidates...")
    print(f"  (stimato ~{len(candidates) * (SLEEP_BETWEEN_FETCHES + 0.5) / 60:.1f} min)")

    scored: list[dict[str, Any]] = []
    rejected: dict[str, int] = {"no_hist": 0, "no_price": 0, "penny_stock": 0,
                                "high_volatility": 0, "low_liquidity": 0, "no_var": 0}
    t0 = time.time()

    for i, row in enumerate(candidates):
        ticker = row["ticker"]
        region = region_for(row.get("index_membership", ""))

        # Log progressivo ogni 50
        if i % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / max(elapsed, 0.1)
            eta = (len(candidates) - i) / max(rate, 0.01)
            print(f"  [{i+1}/{len(candidates)}] {ticker:14s} reg={region} | scored={len(scored)} | ETA {eta/60:.1f}min")

        hist = fetch_hist(ticker, "3mo", "1d")
        time.sleep(SLEEP_BETWEEN_FETCHES)

        if not hist:
            rejected["no_hist"] += 1
            continue

        price = hist.get("regular_price")
        if not price:
            closes = [c for c in hist["close"] if c is not None]
            price = closes[-1] if closes else None

        currency = hist.get("currency") or row.get("currency")

        var_pct = compute_var_pct(hist)
        if var_pct is None:
            rejected["no_var"] += 1
            continue

        atr_pct = compute_atr_pct(hist)
        vol_median_val = median_volume(hist)

        # Filtri qualitativi
        passed, reason = passes_quality_filters(price, atr_pct, vol_median_val, currency)
        if not passed:
            if reason.startswith("no_price"):
                rejected["no_price"] += 1
            elif reason.startswith("penny_stock"):
                rejected["penny_stock"] += 1
            elif reason.startswith("high_volatility"):
                rejected["high_volatility"] += 1
            elif reason.startswith("low_liquidity"):
                rejected["low_liquidity"] += 1
            continue

        # Indicatori v2 completi
        thresh = adaptive_thresholds(atr_pct)
        tag, base_score = classify_signal(var_pct, thresh)
        vol_z = compute_volume_zscore(hist)
        rsi = compute_rsi(hist)
        ma_dist = compute_ma_distance(hist)
        mr_score = mean_reversion_score(rsi, ma_dist)
        rs_delta = compute_relative_strength(var_pct, bench_var.get(region))
        composite = composite_score(base_score, rs_delta, mr_score, vol_z)
        action = action_label(composite)

        scored.append({
            "ticker": ticker,
            "name": row.get("name") or ticker,
            "region": region,
            "market": row.get("market"),
            "currency": currency,
            "sector": row.get("sector") or "",
            "sub_industry": row.get("sub_industry") or "",
            "headquarters": row.get("headquarters") or "",
            "index_membership": row.get("index_membership"),
            "price": round(price, 4) if price else None,
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

    elapsed_total = time.time() - t0
    print(f"\n  Completato in {elapsed_total/60:.1f} min")
    print(f"  Scored: {len(scored)}")
    print(f"  Rejected: {rejected}")

    # Ordinamento + segmentazione
    print(f"\n[3/3] Ranking + segmentation...")
    scored.sort(key=lambda x: abs(x["composite_score"]), reverse=True)
    global_top = scored[:top_n]

    # by_region: BUY (>=2), SELL (<=-2), WATCH (in mezzo ma con abs>=0.5)
    by_region: dict[str, dict[str, list]] = {}
    for region in ("US", "EU", "IT"):
        region_list = [s for s in scored if s["region"] == region]
        buys = sorted([s for s in region_list if s["composite_score"] >= 2.0],
                      key=lambda x: -x["composite_score"])[:top_n]
        sells = sorted([s for s in region_list if s["composite_score"] <= -2.0],
                       key=lambda x: x["composite_score"])[:top_n]
        watch = sorted(
            [s for s in region_list
             if -2.0 < s["composite_score"] < 2.0 and abs(s["composite_score"]) >= 0.5],
            key=lambda x: -abs(x["composite_score"]),
        )[:top_n]
        by_region[region] = {"buy": buys, "sell": sells, "watch": watch}

    snapshot = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "quant_v3/scripts/generate_discovery_snapshot.py",
            "engine_version": "2.0",
            "universe_size": len(universe),
            "portfolio_size": len(portfolio),
            "candidates_size": len(candidates),
            "scored_size": len(scored),
            "rejected": rejected,
            "elapsed_seconds": round(elapsed_total, 1),
            "benchmark_variations": bench_var,
            "top_n": top_n,
            "ranking_method": "composite_score_v2_full",
            "filters": {
                "max_atr_pct": MAX_ATR_PCT,
                "min_vol_median": MIN_VOL_MEDIAN,
                "min_price_strong_currencies": MIN_PRICE_USD,
            },
            "next_revalidation_due": (
                datetime.now(timezone.utc).replace(day=1).isoformat()
            ),
        },
        "global_top": global_top,
        "by_region": by_region,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"\n[Discovery v2] Snapshot scritto su {OUT_JSON}")
    print(f"  global_top: {len(global_top)}")
    for region in ("US", "EU", "IT"):
        b = by_region[region]
        print(f"  {region}: buy={len(b['buy'])} sell={len(b['sell'])} watch={len(b['watch'])}")

    # Top 10 preview
    print(f"\n{'=' * 72}")
    print("TOP 10 DISCOVERY (per |composite_score|)")
    print(f"{'=' * 72}")
    print(f"{'Ticker':<14s} {'Reg':<4s} {'Var%':>7s} {'RSI':>5s} {'ATR%':>6s} {'Score':>7s} {'Action':<20s}")
    print("-" * 72)
    for r in scored[:10]:
        ticker = r["ticker"]
        reg = r["region"]
        var = r["var_pct_24h"]
        rsi = r["rsi"] if r["rsi"] is not None else 0
        atr = r["atr_pct"] or 0
        score = r["composite_score"]
        action = r["action"][:18]
        print(f"{ticker:<14s} {reg:<4s} {var:>+7.2f} {rsi:>5.1f} {atr:>6.2f} {score:>+7.2f} {action:<20s}")

    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=30, help="Numero top candidati per segmento")
    ap.add_argument("--limit", type=int, default=None, help="Limite candidati (per test)")
    args = ap.parse_args()
    sys.exit(main(top_n=args.top_n, limit=args.limit))
