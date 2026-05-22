"""
Vercel Function: GET/POST /api/signals-run

Esegue on-demand l'algoritmo Segnali v2.0 sul universo (holdings + watchlist).
Calcola per ogni ticker:
  - var % giornaliera (vs prev_close)
  - ATR% adattivo 14gg
  - RSI 14
  - MA50 distance %
  - Volume Z-score 20gg
  - Relative Strength vs benchmark (FTSE-MIB EU / ^GSPC US)
  - Composite score [-10, +10]
  - Action label

Sorgenti dati:
  - Prezzi live: /api/quotes (stesso dominio, già in cache)
  - OHLCV storico: Yahoo /v8/finance/chart (3 mesi, daily)

Output: JSON con top_signals, full_snapshot, generated_at.
Se param ?commit=1, scrive anche su GitHub data/signals_v2_snapshot.json (richiede GITHUB_TOKEN env).

Cache 60s lato server (function warm) + ETag.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import math
import base64
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# =============================================================================
# CONFIG
# =============================================================================

# Universo: holdings + watchlist
HOLDINGS = [
    "MSFT", "GOOGL", "AMZN", "META", "NVDA", "MU", "BKNG", "WMT", "AMT",
    "ASML.AS", "ADYEN.AS", "UCG.MI", "PRY.MI", "ENEL.MI", "RACE.MI",
    "IBE.MC", "NOVO-B.CO", "ZTS", "ADBE", "MELI", "SE",
]

WATCHLIST = [
    # Maggiori EU
    "TRN.MI", "SRG.MI", "ACE.MI", "G.MI",
    # Periferici / opportunità
    "EUROB.AT", "AENA.MC", "ITX.MC", "BBVA.MC", "PPC.AT", "JMT.LS",
    "FER.MC", "EDP.LS", "ETE.AT", "REP.MC", "REN.LS",
    # USA growth
    "TSLA", "CRWD",
]

BENCH_EU = "FTSEMIB.MI"
BENCH_US = "^GSPC"

# Costanti algoritmo
ATR_WIN = 14
RSI_WIN = 14
MA_WIN = 50
VOL_WIN = 20

# Pesi composite
W_BASE = 1.0
W_RS = 0.3
W_MR = 0.5
W_VOL = 0.3
W_PERSIST = 0.2

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# Cache function-level (warm)
_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 60


# =============================================================================
# YAHOO FETCH
# =============================================================================

def yahoo_chart(ticker: str, range_str: str = "3mo", interval: str = "1d", timeout: int = 8) -> dict:
    """Ritorna {ok, close[], high[], low[], volume[], ts[]}."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
    url += f"?range={range_str}&interval={interval}&includePrePost=false"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"yahoo_chart: {str(e)[:80]}"}

    try:
        result = j["chart"]["result"][0]
        ts = result["timestamp"]
        ind = result["indicators"]["quote"][0]
        close = [c for c in ind["close"] if c is not None]
        high = [c for c in ind["high"] if c is not None]
        low = [c for c in ind["low"] if c is not None]
        vol = [c for c in (ind.get("volume") or []) if c is not None]
        return {"ok": True, "close": close, "high": high, "low": low, "volume": vol, "ts": ts}
    except (KeyError, IndexError, TypeError) as e:
        return {"ok": False, "error": f"yahoo_chart parse: {str(e)[:80]}"}


def yahoo_quote(ticker: str, timeout: int = 6) -> dict:
    """Ritorna {ok, price, prev_close, var_pct}."""
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(ticker)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        r = j["quoteResponse"]["result"][0]
        price = r.get("regularMarketPrice")
        prev = r.get("regularMarketPreviousClose")
        if price is None or prev is None or prev == 0:
            return {"ok": False, "error": "no_price"}
        var_pct = (price - prev) / prev * 100
        return {"ok": True, "price": price, "prev_close": prev, "var_pct": var_pct,
                "currency": r.get("currency"), "ts": r.get("regularMarketTime")}
    except Exception as e:
        return {"ok": False, "error": f"yahoo_quote: {str(e)[:80]}"}


# =============================================================================
# INDICATORI
# =============================================================================

def atr_pct(high, low, close, n=14):
    """ATR Wilder come % del prezzo corrente."""
    if len(close) < n + 1:
        return None
    trs = []
    for i in range(1, len(close)):
        tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        trs.append(tr)
    if len(trs) < n:
        return None
    atr = sum(trs[-n:]) / n
    return atr / close[-1] * 100


def rsi_wilder(close, n=14):
    if len(close) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, n + 1):
        diff = close[i] - close[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains) / n
    avg_l = sum(losses) / n
    for i in range(n + 1, len(close)):
        diff = close[i] - close[i-1]
        g = max(diff, 0)
        l = max(-diff, 0)
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def ma50_distance(close, n=50):
    if len(close) < n:
        return None
    ma = sum(close[-n:]) / n
    return (close[-1] - ma) / ma * 100


def volume_z(vol, n=20):
    if len(vol) < n + 1:
        return None
    arr = vol[-(n+1):-1]  # ultimi 20 escludendo oggi
    mu = sum(arr) / len(arr)
    var = sum((v - mu) ** 2 for v in arr) / len(arr)
    sd = math.sqrt(var) if var > 0 else 0
    if sd == 0:
        return None
    return (vol[-1] - mu) / sd


def mean_reversion_score(rsi_val, ma_dist):
    s = 0
    if rsi_val is not None:
        if rsi_val < 30: s += 2
        elif rsi_val < 40: s += 1
        elif rsi_val > 70: s -= 2
        elif rsi_val > 60: s -= 1
    if ma_dist is not None:
        if ma_dist < -10: s += 2
        elif ma_dist < -5: s += 1
        elif ma_dist > 15: s -= 2
        elif ma_dist > 10: s -= 1
    return max(-4, min(4, s))


def base_score_from_tag(var_pct, atr_pct_v):
    """Tag base in funzione di soglie ATR-adaptive."""
    if atr_pct_v is None or atr_pct_v == 0:
        # fallback statico
        if var_pct <= -5: return -2, "OPPORTUNITY"
        if var_pct <= -2: return -1, "CAUTION"
        if var_pct >= 5: return 2, "MOMENTUM"
        if var_pct >= 2: return 1, "RALLY"
        return 0, "NEUTRAL"
    opp = -2.5 * atr_pct_v
    caut = -1.0 * atr_pct_v
    rally = 1.0 * atr_pct_v
    mom = 2.5 * atr_pct_v
    if var_pct <= opp: return -2, "OPPORTUNITY"
    if var_pct <= caut: return -1, "CAUTION"
    if var_pct >= mom: return 2, "MOMENTUM"
    if var_pct >= rally: return 1, "RALLY"
    return 0, "NEUTRAL"


def action_from_score(score):
    if score >= 5: return "🟢 STRONG BUY"
    if score >= 2: return "🟢 BUY"
    if score >= 0.5: return "↗ ACCUMULATE"
    if score >= -0.5: return "⚪ HOLD"
    if score >= -2: return "↘ MONITOR"
    if score >= -5: return "🔴 REDUCE"
    return "🔴 STRONG SELL"


# =============================================================================
# PIPELINE
# =============================================================================

def benchmark_for(ticker: str) -> str:
    """Identifica benchmark naturale dal suffisso ticker."""
    eu_suffixes = (".MI", ".DE", ".AS", ".MC", ".PA", ".AT", ".LS", ".CO", ".L", ".VI")
    return BENCH_EU if any(ticker.endswith(s) for s in eu_suffixes) else BENCH_US


def compute_signal(ticker: str, side: str, bench_returns: dict) -> dict:
    """Calcola signal completo per un ticker."""
    quote = yahoo_quote(ticker)
    if not quote.get("ok"):
        return {"ticker": ticker, "ok": False, "error": quote.get("error")}

    hist = yahoo_chart(ticker, range_str="3mo")
    if not hist.get("ok"):
        return {"ticker": ticker, "ok": False, "error": hist.get("error")}

    close = hist["close"]
    high = hist["high"]
    low = hist["low"]
    vol = hist["volume"]
    var_pct = quote["var_pct"]

    atr_v = atr_pct(high, low, close, ATR_WIN)
    rsi_v = rsi_wilder(close, RSI_WIN)
    ma_dist = ma50_distance(close, MA_WIN)
    vol_z = volume_z(vol, VOL_WIN) if vol else None

    base, tag = base_score_from_tag(var_pct, atr_v)
    mr_score = mean_reversion_score(rsi_v, ma_dist)

    bench = benchmark_for(ticker)
    rs_delta = var_pct - bench_returns.get(bench, 0)

    # Composite
    composite = base * W_BASE + rs_delta * W_RS + mr_score * W_MR
    if vol_z is not None:
        composite += vol_z * W_VOL
    composite = max(-10, min(10, composite))

    return {
        "ticker": ticker,
        "side": side,
        "ok": True,
        "price": quote["price"],
        "prev_close": quote["prev_close"],
        "currency": quote.get("currency"),
        "var_pct": round(var_pct, 2),
        "atr_pct": round(atr_v, 2) if atr_v else None,
        "rsi": round(rsi_v, 1) if rsi_v else None,
        "ma50_distance_pct": round(ma_dist, 2) if ma_dist else None,
        "volume_z": round(vol_z, 2) if vol_z is not None else None,
        "relative_strength": {
            "benchmark": bench,
            "delta": round(rs_delta, 2),
        },
        "tag": tag,
        "base_score": base,
        "mean_reversion_score": mr_score,
        "composite_score": round(composite, 2),
        "action": action_from_score(composite),
    }


def run_pipeline() -> dict:
    """Esegue l'algoritmo completo. Ritorna snapshot."""
    # 1. Benchmark returns (paralleli)
    bench_returns = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(yahoo_quote, b): b for b in [BENCH_EU, BENCH_US]}
        for f in as_completed(futs):
            b = futs[f]
            q = f.result()
            bench_returns[b] = q.get("var_pct", 0) if q.get("ok") else 0

    # 2. Universo
    universe = [(t, "HOLDING") for t in HOLDINGS] + [(t, "WATCHLIST") for t in WATCHLIST]
    signals = []

    # 3. Compute parallelo (max 10 worker per non saturare Yahoo)
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(compute_signal, t, s, bench_returns): (t, s) for t, s in universe}
        for f in as_completed(futs):
            try:
                sig = f.result(timeout=12)
                if sig.get("ok"):
                    signals.append(sig)
            except Exception:
                pass

    # 4. Ordina per |composite_score| desc (più informativi in cima)
    signals.sort(key=lambda s: abs(s.get("composite_score", 0)), reverse=True)

    return {
        "ok": True,
        "version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmarks": {
            BENCH_EU: round(bench_returns.get(BENCH_EU, 0), 2),
            BENCH_US: round(bench_returns.get(BENCH_US, 0), 2),
        },
        "universe_size": len(universe),
        "signals_count": len(signals),
        "top15": signals[:15],
        "all": signals,
    }


# =============================================================================
# GITHUB COMMIT (opzionale, se ?commit=1)
# =============================================================================

def github_commit_snapshot(snapshot: dict) -> dict:
    """Committa snapshot su GitHub data/signals_v2_snapshot.json."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN missing"}

    repo = os.environ.get("GITHUB_REPO", "luigimissere-svg/yahoo-proxy-missere")
    path = "data/signals_v2_snapshot.json"
    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # Get current SHA (se file esiste)
    sha = None
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "PatrimonioMissere-Cron/1.0",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            sha = json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return {"ok": False, "error": f"sha_fetch: {e.code}"}

    # Encode content
    content_str = json.dumps(snapshot, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

    payload = {
        "message": f"cron: signals v2 snapshot {snapshot.get('generated_at', '')[:19]}",
        "content": content_b64,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "PatrimonioMissere-Cron/1.0",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"commit: {e.code} {e.reason}"}


# =============================================================================
# HANDLER
# =============================================================================

class handler(BaseHTTPRequestHandler):
    def _send(self, status, body_dict):
        body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=60, s-maxage=60")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            commit_flag = params.get("commit", ["0"])[0] == "1"

            # Cache warm
            now = time.time()
            if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL and not commit_flag:
                payload = dict(_CACHE["data"])
                payload["from_cache"] = True
                return self._send(200, payload)

            snap = run_pipeline()
            _CACHE["data"] = snap
            _CACHE["ts"] = now

            if commit_flag:
                commit_res = github_commit_snapshot(snap)
                snap["github_commit"] = commit_res

            return self._send(200, snap)
        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)[:200]})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
