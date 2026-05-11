"""
Vercel Serverless Function — proxy a Yahoo Finance con CORS aperto + cache 60s.

Endpoint:
  GET /api/quotes?symbols=MSFT,UCG.MI,ASML.AS,...

Restituisce:
  {
    "ok": true,
    "ts": "2026-05-08T17:15:00+00:00",
    "cached": false,
    "fx_eur": {"USD": 0.85, "DKK": 0.134},
    "data": {
      "MSFT": {
        "price": 414.83,
        "prev_close": 420.77,
        "currency": "USD",
        "variazione_pct": -1.41,
        "name": "Microsoft Corporation",
        "exchange": "NMS"
      },
      ...
    },
    "errors": {"TICKER": "msg"} // solo se ci sono errori
  }

Note:
- Cache in-memory di 60s (warm function).
- User-Agent Mozilla per evitare 429.
- Conversione FX automatica (cache 5 min).
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

# Cache globale (persiste finché la function è "calda")
_QUOTE_CACHE: dict = {}      # symbol -> (timestamp, data)
_FX_CACHE: dict = {}         # ccy -> (timestamp, rate_to_eur)
QUOTE_TTL = 60               # 60 secondi
FX_TTL = 300                 # 5 minuti

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def yahoo_fetch(symbol: str, timeout: int = 6, range_param: str = "5d", interval: str = "1d") -> dict:
    """Scarica i dati di un singolo ticker da Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_param}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}


def parse_quote(j: dict, with_series: bool = False) -> dict:
    """Estrae price, prev_close (dal penultimo close della serie), currency.
    Se with_series=True, include anche "series": [{date, close}] per il range richiesto.
    """
    try:
        result = j["chart"]["result"][0]
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        currency = meta.get("currency", "")
        name = meta.get("longName") or meta.get("shortName") or meta.get("symbol", "")
        exchange = meta.get("exchangeName", "")

        # prev_close = penultimo close della serie storica (close di ieri)
        timestamps = result.get("timestamp") or []
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if len(pairs) >= 2:
            prev = float(pairs[-2][1])
        elif len(pairs) == 1:
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or pairs[0][1])
        else:
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)

        var_pct = (price - prev) / prev * 100 if prev else 0.0
        out = {
            "price": round(price, 4),
            "prev_close": round(prev, 4),
            "currency": currency,
            "variazione_pct": round(var_pct, 2),
            "name": name,
            "exchange": exchange,
        }
        if with_series:
            import datetime as _dt
            series = []
            for t, c in pairs:
                d = _dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
                series.append({"date": d, "close": round(float(c), 4)})
            out["series"] = series
        return out
    except Exception as e:
        return {"_error": f"parse: {e}"}


def get_quote_cached(symbol: str, range_param: str = "5d", with_series: bool = False) -> dict:
    """Restituisce il quote, usando cache se fresco. Cache key include il range."""
    now = time.time()
    cache_key = f"{symbol}|{range_param}|{int(with_series)}"
    cached = _QUOTE_CACHE.get(cache_key)
    ttl = QUOTE_TTL if range_param == "5d" else 3600  # cache 1h per range storici
    if cached and (now - cached[0]) < ttl:
        return {**cached[1], "_cached": True}
    j = yahoo_fetch(symbol, range_param=range_param)
    if "_error" in j:
        return {"_error": j["_error"]}
    parsed = parse_quote(j, with_series=with_series)
    if "_error" not in parsed:
        _QUOTE_CACHE[cache_key] = (now, parsed)
    return parsed


def get_fx_to_eur(ccy: str) -> float:
    """Tasso di cambio: 1 unità di ccy in EUR."""
    if not ccy or ccy == "EUR":
        return 1.0
    now = time.time()
    cached = _FX_CACHE.get(ccy)
    if cached and (now - cached[0]) < FX_TTL:
        return cached[1]
    j = yahoo_fetch(f"EUR{ccy}=X")
    try:
        rate_per_eur = float(j["chart"]["result"][0]["meta"]["regularMarketPrice"])
        rate = 1.0 / rate_per_eur
    except Exception:
        # Fallback approssimati
        rate = {"USD": 0.85, "DKK": 0.134, "GBP": 1.18, "CHF": 1.05}.get(ccy, 1.0)
    _FX_CACHE[ccy] = (now, rate)
    return rate


class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "public, max-age=30")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        # Parse query
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        symbols_raw = params.get("symbols", [""])[0]
        if not symbols_raw:
            self._respond(400, {"ok": False, "error": "Parametro 'symbols' richiesto. Esempio: ?symbols=MSFT,UCG.MI"})
            return

        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        if len(symbols) > 50:
            self._respond(400, {"ok": False, "error": "Max 50 simboli per richiesta"})
            return

        # Parametro range opzionale (default 5d). Valori validi Yahoo: 1mo,3mo,6mo,ytd,1y,2y,5y,max
        range_param = (params.get("range", ["5d"])[0] or "5d").strip().lower()
        # series=1 per includere array {date, close} (utile per calcoli storici lato client)
        with_series = params.get("series", ["0"])[0] == "1"

        # Fetch parallelo
        data = {}
        errors = {}
        any_cached = True
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(get_quote_cached, s, range_param, with_series): s for s in symbols}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    q = fut.result()
                    if "_error" in q:
                        errors[sym] = q["_error"]
                    else:
                        if not q.get("_cached"):
                            any_cached = False
                        # rimuovi flag interno
                        q.pop("_cached", None)
                        data[sym] = q
                except Exception as e:
                    errors[sym] = str(e)

        # FX (precarica le valute uniche)
        currencies = {q["currency"] for q in data.values() if q.get("currency")}
        fx_eur = {ccy: round(get_fx_to_eur(ccy), 6) for ccy in currencies if ccy != "EUR"}

        body = {
            "ok": True,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cached": any_cached,
            "count": len(data),
            "fx_eur": fx_eur,
            "data": data,
        }
        if errors:
            body["errors"] = errors
        self._respond(200, body)

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
