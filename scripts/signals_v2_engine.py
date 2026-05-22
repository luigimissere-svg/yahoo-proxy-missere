#!/usr/bin/env python3
"""
Signals v2.0 Engine — Patrimonio Missere
=========================================

Evoluzione dell'algoritmo "Segnali del giorno" con 6 nuovi moduli:

  1. Soglie adattive ATR-based (volatilità storica per ogni titolo)
  2. Delta vs benchmark (FTSE-MIB per EU, S&P 500 per US)
  3. Volume Z-score (filtra segnali reali da rumore)
  4. Calendar overlay (earnings, ex-dividend, FOMC)
  5. Mean reversion score (RSI 14 + distanza da MA50)
  6. Storico segnali ricorrenti (persistence count)

Output: snapshot JSON arricchito + ranking composito
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from statistics import mean, stdev
from pathlib import Path

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
PROXY_QUOTES = "https://project-kn8ir.vercel.app/api/quotes"

# Universo tracciato
HOLDINGS = [
    "NVDA", "MSFT", "MC.PA", "PRY.MI", "ZTS", "SE", "BSX",
    "ADBE", "LLY", "NOVO-B.CO", "META", "BKNG", "AMZN",
    "IBE.MC", "ENEL.MI", "MU", "MELI", "RACE.MI", "AMT",
    "WMT", "BNP.PA", "BMPS.MI", "LHA.DE", "GMAB.CO",
]
WATCHLIST = [
    "EUROB.AT", "AENA.MC", "ITX.MC", "BBVA.MC", "PPC.AT",
    "JMT.LS", "FER.MC", "EDP.LS", "ETE.AT", "REP.MC",
    "TRN.MI",
]
ALL_TICKERS = HOLDINGS + WATCHLIST

# Benchmark
BENCH_EU = "FTSEMIB.MI"   # FTSE-MIB
BENCH_US = "^GSPC"         # S&P 500

# Identificazione mercato per benchmark
US_SUFFIXES = ()  # US: nessun suffisso
EU_SUFFIXES = (".MI", ".PA", ".MC", ".DE", ".AS", ".CO", ".LS", ".AT", ".L", ".SW")


def is_eu(ticker: str) -> bool:
    return any(ticker.endswith(s) for s in EU_SUFFIXES)


# ============================================================================
# MODULO 1 — Yahoo data fetch (historical + intraday)
# ============================================================================

def fetch_hist(symbol: str, range_str: str = "3mo", interval: str = "1d"):
    """Recupera serie storica OHLCV per il simbolo."""
    url = f"{YAHOO_CHART}{symbol}?range={range_str}&interval={interval}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SignalsV2/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        chart = data.get("chart", {}).get("result", [None])[0]
        if not chart:
            return None
        timestamps = chart.get("timestamp", [])
        quote = chart.get("indicators", {}).get("quote", [{}])[0]
        return {
            "ts": timestamps,
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }
    except Exception as e:
        return None


# ============================================================================
# MODULO 2 — Soglie adattive ATR-based
# ============================================================================

def compute_atr_pct(hist: dict, period: int = 14) -> float:
    """Average True Range come percentuale del prezzo (volatilità storica)."""
    if not hist or not hist["close"]:
        return None
    closes = [c for c in hist["close"] if c is not None]
    highs = [h for h in hist["high"] if h is not None]
    lows = [l for l in hist["low"] if l is not None]
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        )
        trs.append(tr)
    atr = mean(trs[-period:])
    last_close = closes[-1]
    return (atr / last_close) * 100 if last_close else None


def adaptive_thresholds(atr_pct: float) -> dict:
    """
    Ritorna soglie classificazione PERSONALIZZATE sulla volatilità del titolo.
    - 1 sigma ATR → CAUTION/RALLY
    - 2.5 sigma ATR → OPPORTUNITY/MOMENTUM
    """
    if atr_pct is None or atr_pct < 0.3:
        # fallback soglie statiche
        return {
            "opportunity": -5.0, "caution": -2.0, "rally": 2.0, "momentum": 5.0,
            "atr_pct": None, "method": "static"
        }
    return {
        "opportunity": round(-2.5 * atr_pct, 2),
        "caution": round(-1.0 * atr_pct, 2),
        "rally": round(1.0 * atr_pct, 2),
        "momentum": round(2.5 * atr_pct, 2),
        "atr_pct": round(atr_pct, 2),
        "method": "adaptive",
    }


# ============================================================================
# MODULO 3 — Volume Z-score
# ============================================================================

def compute_volume_zscore(hist: dict, window: int = 20) -> float:
    """Z-score del volume di oggi vs media degli ultimi 20 giorni."""
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


def volume_quality(z: float) -> str:
    """Tagging qualitativo del volume."""
    if z is None:
        return "n/a"
    if z >= 2.0:
        return "🔊 alto (segnale forte)"
    if z >= 1.0:
        return "📈 sopra media"
    if z <= -1.0:
        return "🔇 basso (rumore)"
    return "✓ normale"


# ============================================================================
# MODULO 4 — Mean Reversion Score (RSI + distanza da MA50)
# ============================================================================

def compute_rsi(hist: dict, period: int = 14) -> float:
    """RSI classico Wilder."""
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


def compute_ma_distance(hist: dict, period: int = 50) -> float:
    """Distanza % del prezzo corrente dalla media mobile 50gg."""
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


def mean_reversion_score(rsi: float, ma_dist: float) -> tuple:
    """
    Score composito mean reversion:
    - RSI <30 + prezzo <MA50 → ipervenduto (BUY signal)
    - RSI >70 + prezzo >MA50+10% → ipercomprato (SELL signal)
    """
    if rsi is None or ma_dist is None:
        return None, "n/a"
    score = 0
    notes = []
    if rsi < 30:
        score += 2
        notes.append(f"RSI {rsi} ipervenduto")
    elif rsi < 40:
        score += 1
        notes.append(f"RSI {rsi} debole")
    elif rsi > 70:
        score -= 2
        notes.append(f"RSI {rsi} ipercomprato")
    elif rsi > 60:
        score -= 1
        notes.append(f"RSI {rsi} forte")

    if ma_dist < -10:
        score += 2
        notes.append(f"prezzo {ma_dist:.1f}% sotto MA50")
    elif ma_dist < -5:
        score += 1
    elif ma_dist > 15:
        score -= 2
        notes.append(f"prezzo +{ma_dist:.1f}% sopra MA50")
    elif ma_dist > 10:
        score -= 1

    label = "n/a"
    if score >= 3:
        label = "🟢 mean reversion BUY"
    elif score >= 1:
        label = "📉 oversold mild"
    elif score <= -3:
        label = "🔴 mean reversion SELL"
    elif score <= -1:
        label = "📈 overbought mild"
    else:
        label = "neutrale"

    return score, label + (" | " + "; ".join(notes) if notes else "")


# ============================================================================
# MODULO 5 — Delta vs Benchmark
# ============================================================================

def compute_relative_strength(ticker_var: float, bench_var: float) -> dict:
    """Relative strength del titolo vs benchmark."""
    if ticker_var is None or bench_var is None:
        return {"delta": None, "label": "n/a"}
    delta = round(ticker_var - bench_var, 2)
    label = "in linea"
    if delta >= 2:
        label = f"🚀 sovraperforma +{delta}%"
    elif delta >= 0.5:
        label = f"↗ meglio del mercato +{delta}%"
    elif delta <= -2:
        label = f"⚠ sottoperforma {delta}%"
    elif delta <= -0.5:
        label = f"↘ peggio del mercato {delta}%"
    return {"delta": delta, "label": label}


# ============================================================================
# MODULO 6 — Calendar overlay (stub — andrebbe integrato con API earnings)
# ============================================================================

def calendar_overlay(ticker: str) -> dict:
    """
    Stub: ritorna eventi noti per ticker.
    In produzione, andrebbe integrato con earnings calendar API (Yahoo, FMP, EodHd).
    Per ora caricamento manuale dei principali eventi noti.
    """
    today = datetime.now(timezone.utc).date()
    # Eventi noti maggio-giugno 2026 (curato manualmente)
    KNOWN_EVENTS = {
        "NVDA": ("2026-05-28", "earnings Q1FY27"),
        "WMT": ("2026-05-15", "earnings Q1FY27 (passato — sell-off odierno)"),
        "MSFT": ("2026-07-23", "earnings Q4FY26"),
        "ZTS": ("2026-08-05", "earnings Q2"),
        "ADBE": ("2026-06-12", "earnings Q2"),
        "META": ("2026-07-31", "earnings Q2"),
        "AMZN": ("2026-08-01", "earnings Q2"),
        "LLY": ("2026-08-08", "earnings Q2"),
        "NOVO-B.CO": ("2026-08-07", "earnings Q2"),
        "EUROB.AT": ("2026-08-01", "earnings 1H"),
        "TRN.MI": ("2026-07-29", "earnings 1H"),
        "ENEL.MI": ("2026-07-31", "earnings 1H + ex-div 22/07"),
        "IBE.MC": ("2026-07-23", "earnings 1H"),
        "AENA.MC": ("2026-10-30", "earnings 3Q"),
    }
    if ticker in KNOWN_EVENTS:
        date_str, label = KNOWN_EVENTS[ticker]
        evt_date = datetime.fromisoformat(date_str).date()
        delta = (evt_date - today).days
        if -7 <= delta <= 30:
            return {"event": label, "in_days": delta, "date": date_str}
    return {"event": None, "in_days": None, "date": None}


# ============================================================================
# MODULO 7 — Persistence (storico segnali)
# ============================================================================

HISTORY_FILE = Path("/home/user/workspace/auto_watchlist/signals_history.json")


def load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return {}


def persistence_count(ticker: str, current_tag: str, history: dict) -> int:
    """
    Quanti giorni consecutivi il titolo ha avuto questo tag (es. CAUTION)?
    Utile per spotter trend persistenti.
    """
    if not history:
        return 1
    entries = history.get("entries", [])
    count = 1
    for entry in reversed(entries[-30:]):
        if entry.get("ticker") == ticker:
            prev_tag = entry.get("tag") or entry.get("action", "")
            if current_tag.lower() in prev_tag.lower():
                count += 1
            else:
                break
    return count


# ============================================================================
# CLASSIFICATORE COMPOSITO
# ============================================================================

def classify_signal(var_pct: float, thresholds: dict) -> tuple:
    """Classifica il segnale base sulle soglie adattive."""
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


def composite_score(base_score: int, rs_delta: float, mr_score: int, vol_z: float, persistence: int) -> float:
    """
    Score finale composito (range -10 a +10):
    - base_score (-4 a +4) ha peso 1.0
    - relative strength vs benchmark ha peso 0.3
    - mean reversion score ha peso 0.5
    - volume z-score ha peso 0.3 (amplifica)
    - persistence (giorni consecutivi) ha peso 0.2
    """
    score = float(base_score)
    if rs_delta is not None:
        score += rs_delta * 0.3
    if mr_score is not None:
        score += mr_score * 0.5
    if vol_z is not None:
        score += vol_z * 0.3
    if persistence > 1:
        # penalizza tag ricorrenti (titolo bloccato in trend)
        score -= (persistence - 1) * 0.2 * (1 if base_score < 0 else -1)
    return round(max(-10, min(10, score)), 2)


def action_label(composite: float) -> str:
    if composite >= 5:
        return "🟢 STRONG BUY"
    if composite >= 2:
        return "🟢 BUY"
    if composite >= 0.5:
        return "↗ ACCUMULATE"
    if composite <= -5:
        return "🔴 STRONG SELL / TAKE PROFIT"
    if composite <= -2:
        return "🔴 REDUCE"
    if composite <= -0.5:
        return "↘ MONITOR"
    return "⚪ HOLD"


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print(f"SIGNALS v2.0 ENGINE — Patrimonio Missere")
    print(f"Run: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Step 1: fetch live quotes via proxy
    print("\n[1/6] Fetching live quotes...")
    symbols_csv = ",".join(ALL_TICKERS + [BENCH_EU, BENCH_US])
    url = f"{PROXY_QUOTES}?symbols={symbols_csv}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            quotes_raw = json.loads(resp.read().decode("utf-8"))
        quotes = quotes_raw.get("data", {})
        print(f"  ✓ {len(quotes)} ticker recuperati")
    except Exception as e:
        print(f"  ✗ Errore fetch quotes: {e}")
        return

    bench_eu_var = quotes.get(BENCH_EU, {}).get("variazione_pct")
    bench_us_var = quotes.get(BENCH_US, {}).get("variazione_pct")
    print(f"  📊 FTSE-MIB var: {bench_eu_var}% | S&P 500 var: {bench_us_var}%")

    # Step 2: fetch historical for ATR, RSI, MA, volume
    print(f"\n[2/6] Fetching historical (3mo) per {len(ALL_TICKERS)} titoli...")
    hist_data = {}
    for i, ticker in enumerate(ALL_TICKERS):
        hist = fetch_hist(ticker, "3mo", "1d")
        hist_data[ticker] = hist
        print(f"  [{i+1}/{len(ALL_TICKERS)}] {ticker:12s} {'✓' if hist else '✗'}")

    # Step 3: storico segnali
    print("\n[3/6] Loading signal history...")
    history = load_history()
    print(f"  ✓ {len(history.get('entries', []))} entries storiche caricate")

    # Step 4: analyze each ticker
    print(f"\n[4/6] Analyzing {len(ALL_TICKERS)} ticker...")
    results = []
    for ticker in ALL_TICKERS:
        q = quotes.get(ticker, {})
        var_pct = q.get("variazione_pct")
        price = q.get("price")
        if var_pct is None:
            continue

        hist = hist_data.get(ticker)

        # Modulo 1 — ATR adaptive thresholds
        atr_pct = compute_atr_pct(hist) if hist else None
        thresh = adaptive_thresholds(atr_pct)

        # Classifier base
        tag, base_score = classify_signal(var_pct, thresh)

        # Modulo 2 — Volume Z-score
        vol_z = compute_volume_zscore(hist) if hist else None
        vol_label = volume_quality(vol_z)

        # Modulo 3 — Mean reversion score
        rsi = compute_rsi(hist) if hist else None
        ma_dist = compute_ma_distance(hist) if hist else None
        mr_score, mr_label = mean_reversion_score(rsi, ma_dist)

        # Modulo 4 — Relative strength
        bench_var = bench_eu_var if is_eu(ticker) else bench_us_var
        rs = compute_relative_strength(var_pct, bench_var)

        # Modulo 5 — Calendar
        cal = calendar_overlay(ticker)

        # Modulo 6 — Persistence
        persist = persistence_count(ticker, tag, history)

        # Composite score
        composite = composite_score(base_score, rs["delta"], mr_score, vol_z, persist)
        action = action_label(composite)

        results.append({
            "ticker": ticker,
            "side": "HOLDING" if ticker in HOLDINGS else "WATCHLIST",
            "price": price,
            "currency": q.get("currency"),
            "var_pct": var_pct,
            "atr_pct": atr_pct,
            "thresholds": thresh,
            "tag": tag,
            "base_score": base_score,
            "volume_z": vol_z,
            "volume_label": vol_label,
            "rsi": rsi,
            "ma50_distance_pct": ma_dist,
            "mean_reversion_score": mr_score,
            "mean_reversion_label": mr_label,
            "relative_strength": rs,
            "calendar": cal,
            "persistence_days": persist,
            "composite_score": composite,
            "action": action,
        })

    # Step 5: ranking
    print(f"\n[5/6] Ranking per composite score...")
    results.sort(key=lambda r: abs(r["composite_score"]), reverse=True)

    # Step 6: output
    print(f"\n[6/6] Generating snapshot v2...")
    snapshot = {
        "engine_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "ftse_mib_var": bench_eu_var,
            "sp500_var": bench_us_var,
        },
        "modules_active": [
            "adaptive_atr_thresholds",
            "volume_zscore",
            "mean_reversion_rsi_ma50",
            "relative_strength_benchmark",
            "calendar_overlay",
            "persistence_history",
        ],
        "total_signals": len(results),
        "signals": results,
    }

    import os
    out_path = Path(os.environ.get("SNAPSHOT_OUT", "/home/user/workspace/signals_v2_snapshot.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"  ✓ Snapshot salvato in {out_path}")

    # Print top 10
    print(f"\n{'=' * 70}")
    print("TOP 10 SEGNALI PER FORZA COMPOSITA")
    print(f"{'=' * 70}")
    print(f"{'Ticker':<14s} {'Var%':>7s} {'ATR%':>6s} {'Score':>7s} {'Action':<24s} {'RS vs Bench':<18s}")
    print("-" * 100)
    for r in results[:15]:
        ticker = r["ticker"]
        var = r["var_pct"]
        atr = r["atr_pct"] or 0
        score = r["composite_score"]
        action = r["action"][:22]
        rs = r["relative_strength"]["label"][:18]
        print(f"{ticker:<14s} {var:>+7.2f} {atr:>6.2f} {score:>+7.2f} {action:<24s} {rs:<18s}")

    return snapshot


if __name__ == "__main__":
    main()
