"""
Vercel Serverless Function — proxy quotazioni con CORS aperto + cache 60s.

Endpoint:
  GET /api/quotes?symbols=MSFT,UCG.MI,ASML.AS,...

Logica:
  1. Google Finance (primario) — scraping HTML, prezzi live SSR per UA "curl/wget-like"
  2. Yahoo Finance (fallback) — quando Google non ha il simbolo (es. watchlist .L/.PA)
  3. FX live da Google Finance (EUR/USD, EUR/GBP, EUR/DKK)

Il simbolo richiesto dal frontend è in formato Yahoo (es. PRY.MI, KTN.DE, NOV.DE).
Lo mappiamo internamente al formato Google (PRY:BIT, KTN:ETR, NOV:ETR).
"""
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

# Cache globale (persiste finché la function è "calda")
_QUOTE_CACHE: dict = {}
_FX_CACHE: dict = {}
QUOTE_TTL = 60
FX_TTL = 300

# User-Agent semplice: Google serve HTML SSR con data-last-price SOLO per agenti non-browser
UA_GOOGLE = "curl/7.81.0"
UA_YAHOO = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# Cookie SOCS bypassa GDPR di Google
GOOGLE_COOKIE = "SOCS=CAISHAgCEhJnd3NfMjAyNjA0MjAtMF9SQzEaAmVuIAEaBgiAqruyBg"

# Mappa Yahoo symbol → Google Finance symbol (per i ticker che vogliamo da Google)
YAHOO_TO_GOOGLE = {
    # USA - holding portafoglio
    "MSFT": "MSFT:NASDAQ", "GOOGL": "GOOGL:NASDAQ", "AMZN": "AMZN:NASDAQ",
    "META": "META:NASDAQ", "NVDA": "NVDA:NASDAQ", "MU": "MU:NASDAQ",
    "BKNG": "BKNG:NASDAQ", "WMT": "WMT:NASDAQ", "AMT": "AMT:NYSE",
    "AMD": "AMD:NASDAQ", "IBM": "IBM:NYSE", "MRVL": "MRVL:NASDAQ",
    "AVGO": "AVGO:NASDAQ", "ABT": "ABT:NYSE", "ADBE": "ADBE:NASDAQ",
    "ADSK": "ADSK:NASDAQ", "BSX": "BSX:NYSE", "GFS": "GFS:NASDAQ",
    "MELI": "MELI:NASDAQ", "MSI": "MSI:NYSE", "PANW": "PANW:NASDAQ",
    "SE": "SE:NYSE",
    # Norvegia
    "YAR.OL": "YAR:OSL",
    # Italia
    "UCG.MI": "UCG:BIT", "PRY.MI": "PRY:BIT", "ENEL.MI": "ENEL:BIT", "RACE.MI": "RACE:BIT",
    # Germania / Xetra
    "NEM.DE": "NEM:ETR", "MBG.DE": "MBG:ETR", "KTN.DE": "KTN:ETR",
    "NOV.DE": "NOV:ETR", "PCZ.DE": "PCZ:ETR",
    # Olanda / Spagna
    "ASML.AS": "ASML:AMS", "ADYEN.AS": "ADYEN:AMS",
    "IBE.MC": "IBE:BME",
    # Watchlist Francia (Euronext Paris)
    "ALNOV.PA": "ALNOV:EPA", "ALBIO.PA": "ALBIO:EPA",
    "EL.PA": "EL:EPA", "BNP.PA": "BNP:EPA", "TTE.PA": "TTE:EPA",
    # Watchlist UK / Danimarca
    "DGE.L": "DGE:LON", "PRU.L": "PRU:LON", "MRO.L": "MRO:LON",
    "GMAB.CO": "GMAB:CPH",
    # Vecchi alias (Vienna/Copenhagen → Xetra)
    "KTN.VI": "KTN:ETR",
    "NOVO-B.CO": "NOV:ETR",
}

GOOGLE_CURRENCY = {
    "BIT": "EUR", "ETR": "EUR", "EPA": "EUR", "BME": "EUR", "AMS": "EUR",
    "FRA": "EUR", "MIL": "EUR", "VIE": "EUR",
    "CPH": "DKK", "LON": "GBX", "STO": "SEK", "OSL": "NOK",
    "NASDAQ": "USD", "NYSE": "USD", "NYSEARCA": "USD",
}


# =============================================================================
# GOOGLE FINANCE
# =============================================================================

def google_fetch(google_symbol: str, timeout: int = 6) -> dict:
    """Fetch prezzo + prev_close + valuta da Google Finance via scraping HTML."""
    url = f"https://www.google.com/finance/quote/{google_symbol}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_GOOGLE,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": GOOGLE_COOKIE,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"_error": f"google_fetch: {e}"}

    m = re.search(r'data-last-price="([0-9.]+)"', html)
    if not m:
        return {"_error": "google: no data-last-price"}
    price = float(m.group(1))

    cm = re.search(r'data-currency-code="([A-Z]+)"', html)
    if cm:
        ccy = cm.group(1)
    else:
        exch = google_symbol.split(":")[1] if ":" in google_symbol else ""
        ccy = GOOGLE_CURRENCY.get(exch, "USD")

    # Prev close: classe P6K39c subito dopo "Previous close"
    prev = None
    pc_idx = html.find("Previous close")
    if pc_idx > 0:
        tail = html[pc_idx:pc_idx + 800]
        pm = re.search(r'class="P6K39c"[^>]*>([^<]+)<', tail)
        if pm:
            raw = pm.group(1).strip()
            num = re.sub(r'[^\d.,-]', '', raw).replace(',', '')
            try:
                prev = float(num)
            except ValueError:
                pass

    # Name: cerca <h1> con classe specifica
    name = google_symbol.split(":")[0]
    nm = re.search(r'class="zzDege"[^>]*>([^<]+)<', html)
    if nm:
        name = nm.group(1).strip()

    if prev is None:
        prev = price
    var_pct = (price - prev) / prev * 100 if prev else 0.0

    return {
        "price": round(price, 4),
        "prev_close": round(prev, 4),
        "currency": ccy,
        "variazione_pct": round(var_pct, 2),
        "name": name,
        "exchange": google_symbol.split(":")[1] if ":" in google_symbol else "",
        "source": "google",
    }


def google_fx_to_eur(ccy: str) -> float:
    """Cambio 1 CCY → EUR via Google Finance."""
    if not ccy or ccy == "EUR":
        return 1.0
    url = f"https://www.google.com/finance/quote/EUR-{ccy}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_GOOGLE,
        "Cookie": GOOGLE_COOKIE,
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'data-last-price="([0-9.]+)"', html)
        if m:
            rate = float(m.group(1))  # quanti CCY per 1 EUR
            return 1.0 / rate if rate else 0.0
    except Exception:
        pass
    return {"USD": 0.85, "DKK": 0.134, "GBP": 1.18, "CHF": 1.05, "SEK": 0.09}.get(ccy, 1.0)


# =============================================================================
# YAHOO FINANCE (fallback)
# =============================================================================

def yahoo_fetch(symbol: str, timeout: int = 6, range_param: str = "10d", interval: str = "1d") -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_param}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": UA_YAHOO})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}


def yahoo_parse(j: dict, with_series: bool = False) -> dict:
    try:
        result = j["chart"]["result"][0]
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        currency = meta.get("currency", "")
        name = meta.get("longName") or meta.get("shortName") or meta.get("symbol", "")
        exchange = meta.get("exchangeName", "")

        timestamps = result.get("timestamp") or []
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]

        # ===== FIX gap-day bug (16/06/2026) =====
        # La serie storica di Yahoo /v8/chart con range=10d&interval=1d puo' NON
        # includere la chiusura del giorno corrente quando il mercato e' chiuso
        # o e' pre-market. In quel caso pairs[-1] e' gia' l'ultima chiusura
        # ufficiale (=prev_close corretto rispetto a regularMarketPrice).
        # Prendere pairs[-2] saltava di due sedute e produceva variazioni errate
        # (es. AMD 16/06 mostrava +12,04% vs +6,98% reale).
        # Strategia:
        #   - Se l'ultimo elemento della serie ha data == data di regularMarketPrice => usa pairs[-2]
        #   - Altrimenti (serie ferma a ieri) => usa pairs[-1] = ultima chiusura ufficiale
        import datetime as _dt2
        prev = None
        if len(pairs) >= 1:
            last_ts = int(pairs[-1][0])
            last_date = _dt2.datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
            reg_ts = int(meta.get("regularMarketTime") or 0)
            reg_date = _dt2.datetime.utcfromtimestamp(reg_ts).strftime("%Y-%m-%d") if reg_ts else ""
            if reg_date and last_date == reg_date:
                # serie include la barra di oggi => prev = penultimo
                if len(pairs) >= 2:
                    prev = float(pairs[-2][1])
            else:
                # serie si ferma a ieri => prev = ultima chiusura ufficiale
                prev = float(pairs[-1][1])
        if prev is None or prev <= 0:
            # fallback robusto: chartPreviousClose, previousClose, infine price
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        # ===== fine fix =====

        var_pct = (price - prev) / prev * 100 if prev else 0.0
        out = {
            "price": round(price, 4),
            "prev_close": round(prev, 4),
            "currency": currency,
            "variazione_pct": round(var_pct, 2),
            "name": name,
            "exchange": exchange,
            "source": "yahoo",
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


# =============================================================================
# ORCHESTRAZIONE
# =============================================================================

def get_quote(symbol: str, range_param: str = "5d", with_series: bool = False) -> dict:
    """Google primario, Yahoo fallback. Cache 60s.

    Per range != "5d" o with_series=True → forza Yahoo (Google non espone serie storica via scraping).
    """
    now = time.time()
    cache_key = f"{symbol}|{range_param}|{int(with_series)}"
    cached = _QUOTE_CACHE.get(cache_key)
    ttl = QUOTE_TTL if range_param == "5d" else 3600
    if cached and (now - cached[0]) < ttl:
        return {**cached[1], "_cached": True}

    # Per serie storiche → Yahoo (Google scraping non le ha)
    if range_param != "5d" or with_series:
        j = yahoo_fetch(symbol, range_param=range_param)
        if "_error" in j:
            return {"_error": j["_error"]}
        parsed = yahoo_parse(j, with_series=with_series)
        if "_error" not in parsed:
            _QUOTE_CACHE[cache_key] = (now, parsed)
        return parsed

    # Google Finance primario
    g_sym = YAHOO_TO_GOOGLE.get(symbol)
    if g_sym:
        parsed = google_fetch(g_sym)
        if "_error" not in parsed:
            _QUOTE_CACHE[cache_key] = (now, parsed)
            return parsed
        # Fall through a Yahoo

    # Yahoo fallback
    j = yahoo_fetch(symbol)
    if "_error" in j:
        return {"_error": j["_error"]}
    parsed = yahoo_parse(j)
    if "_error" not in parsed:
        _QUOTE_CACHE[cache_key] = (now, parsed)
    return parsed


def get_fx_to_eur(ccy: str) -> float:
    if not ccy or ccy == "EUR":
        return 1.0
    now = time.time()
    cached = _FX_CACHE.get(ccy)
    if cached and (now - cached[0]) < FX_TTL:
        return cached[1]
    rate = google_fx_to_eur(ccy)
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

        range_param = (params.get("range", ["5d"])[0] or "5d").strip().lower()
        with_series = params.get("series", ["0"])[0] == "1"

        data = {}
        errors = {}
        any_cached = True
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(get_quote, s, range_param, with_series): s for s in symbols}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    q = fut.result()
                    if "_error" in q:
                        errors[sym] = q["_error"]
                    else:
                        if not q.get("_cached"):
                            any_cached = False
                        q.pop("_cached", None)
                        data[sym] = q
                except Exception as e:
                    errors[sym] = str(e)

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
