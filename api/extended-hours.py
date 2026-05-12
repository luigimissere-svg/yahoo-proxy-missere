"""
Vercel Function: GET /api/extended-hours?symbols=NVDA,MSFT,...

Restituisce dati pre-market e after-hours per i ticker richiesti.
Fonte: Yahoo Finance v8/chart endpoint, che espone in `meta`:
  - marketState: PRE / REGULAR / POST / CLOSED / POSTPOST / PREPRE
  - preMarketPrice, preMarketChange, preMarketChangePercent, preMarketTime
  - postMarketPrice, postMarketChange, postMarketChangePercent, postMarketTime
  - regularMarketPrice, chartPreviousClose, exchangeTimezoneName

Cache 60 secondi (i dati extended-hours si muovono lentamente).
CORS aperto.
"""
from http.server import BaseHTTPRequestHandler
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import urlparse, parse_qs


_CACHE = {}  # symbol -> {"ts": float, "data": dict}
_CACHE_TTL = 60


def yahoo_fetch_meta(symbol: str, timeout: int = 8) -> dict:
    """Fetcha chart endpoint, deduce stato sessione e prezzi pre/post da serie 1m.

    Yahoo non popola più i campi preMarketPrice/postMarketPrice nel meta,
    quindi li ricostruiamo dalla serie 1m con includePrePost=true:
      - currentTradingPeriod.pre.start/end → finestra pre-market
      - currentTradingPeriod.regular.start/end → sessione regolare
      - currentTradingPeriod.post.start/end → finestra after-hours
    Confrontiamo ogni timestamp della serie con queste finestre per determinare
    l'ultimo prezzo pre/regular/post.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?range=2d&interval=1m&includePrePost=true"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PatrimonioMissere/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"ok": False, "error": f"yahoo_fetch: {str(e)[:120]}"}
    except Exception as e:
        return {"ok": False, "error": f"yahoo_fetch: {str(e)[:120]}"}

    try:
        result = j.get("chart", {}).get("result", [])
        if not result:
            return {"ok": False, "error": "yahoo: empty result"}
        r0 = result[0]
        meta = r0.get("meta", {})
        timestamps = r0.get("timestamp", []) or []
        closes = (
            (r0.get("indicators", {}).get("quote", [{}])[0].get("close", []))
            or []
        )

        ctp = meta.get("currentTradingPeriod", {}) or {}
        pre_win = ctp.get("pre", {}) or {}
        reg_win = ctp.get("regular", {}) or {}
        post_win = ctp.get("post", {}) or {}

        pre_start = pre_win.get("start")
        pre_end = pre_win.get("end")
        reg_start = reg_win.get("start")
        reg_end = reg_win.get("end")
        post_start = post_win.get("start")
        post_end = post_win.get("end")

        # Cerca ultimo prezzo per ciascuna sessione, scorrendo dalla fine.
        # Strategia: l'ULTIMO prezzo della serie è il più recente disponibile.
        # - Se rientra in finestra post di OGGI → post_price oggi
        # - Se siamo prima dell'apertura pre oggi ma la serie ha ancora punti
        #   recenti (es. post-market di ieri sera che si è protratto fino
        #   a notte fonda CEST) → trattalo come "ultimo prezzo extended"
        #   contro regular_price.
        pre_price = None
        pre_time = None
        post_price = None
        post_time = None
        last_extended_price = None
        last_extended_time = None

        for i in range(len(timestamps) - 1, -1, -1):
            ts = timestamps[i]
            cl = closes[i] if i < len(closes) else None
            if cl is None:
                continue
            in_post = post_start and post_end and post_start <= ts < post_end
            in_reg = reg_start and reg_end and reg_start <= ts < reg_end
            in_pre = pre_start and pre_end and pre_start <= ts < pre_end
            if in_post and post_price is None:
                post_price = cl
                post_time = ts
            elif in_pre and pre_price is None:
                pre_price = cl
                pre_time = ts
            # Se non in nessuna finestra "oggi" ma è il primissimo non-null
            # scorso dalla fine → è l'ultimo prezzo extended-hours disponibile
            # (tipicamente post-market di ieri sera USA)
            if last_extended_price is None and not in_reg and not in_pre and not in_post:
                last_extended_price = cl
                last_extended_time = ts
            if pre_price is not None and post_price is not None:
                break

        # Stato sessione corrente in base a now
        now = int(time.time())
        if reg_start and reg_end and reg_start <= now < reg_end:
            session = "REGULAR"
        elif pre_start and pre_end and pre_start <= now < pre_end:
            session = "PRE"
        elif post_start and post_end and post_start <= now < post_end:
            session = "POST"
        else:
            session = "CLOSED"

        regular_price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose")

        # Calcola variazioni %
        def pct(curr, base):
            if curr is None or base is None or base == 0:
                return None
            return round((curr / base - 1) * 100, 3)

        pre_change_pct = pct(pre_price, prev_close)
        post_change_pct = pct(post_price, regular_price)
        last_extended_change_pct = pct(last_extended_price, regular_price)

        out = {
            "ok": True,
            "symbol": symbol,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
            "exchange_tz": meta.get("exchangeTimezoneName"),
            "session": session,  # PRE/REGULAR/POST/CLOSED
            "regular_price": regular_price,
            "regular_time": meta.get("regularMarketTime"),
            "prev_close": prev_close,
            "pre_price": pre_price,
            "pre_change_pct": pre_change_pct,
            "pre_time": pre_time,
            "post_price": post_price,
            "post_change_pct": post_change_pct,
            "post_time": post_time,
            "last_extended_price": last_extended_price,
            "last_extended_change_pct": last_extended_change_pct,
            "last_extended_time": last_extended_time,
            "trading_period": {
                "pre_start": pre_start, "pre_end": pre_end,
                "reg_start": reg_start, "reg_end": reg_end,
                "post_start": post_start, "post_end": post_end,
            },
        }
        return out
    except Exception as e:
        return {"ok": False, "error": f"yahoo_parse: {str(e)[:120]}"}


def get_data(symbols: list) -> dict:
    """Recupera dati per lista simboli, usando cache 60s per ciascuno."""
    now = time.time()
    data = {}
    for sym in symbols:
        sym = sym.strip()
        if not sym:
            continue
        c = _CACHE.get(sym)
        if c and now - c["ts"] < _CACHE_TTL:
            data[sym] = c["data"]
            continue
        d = yahoo_fetch_meta(sym)
        _CACHE[sym] = {"ts": now, "data": d}
        data[sym] = d
    return data


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        symbols_raw = qs.get("symbols", [""])[0]
        symbols = [s for s in symbols_raw.split(",") if s.strip()]

        if not symbols:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "symbols param required"}).encode("utf-8"))
            return

        # max 30 simboli per chiamata
        symbols = symbols[:30]
        data = get_data(symbols)

        body = {
            "ok": True,
            "ts": int(time.time()),
            "count": len(data),
            "data": data,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
