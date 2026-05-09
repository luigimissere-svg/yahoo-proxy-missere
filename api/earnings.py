"""
Vercel Function: GET /api/earnings?symbols=MSFT,NVDA,...&days=30
Restituisce earnings calendar Finnhub filtrato sui ticker richiesti.

Output:
{
  "ok": true,
  "ts": 1778312669,
  "from": "2026-05-09",
  "to": "2026-06-09",
  "earnings": [
    {"symbol":"NVDA","date":"2026-05-20","hour":"amc","epsEstimate":1.79,"epsActual":null,"revenueEstimate":80068303638,"revenueActual":null,"year":2026,"quarter":1}
  ]
}

FINNHUB_API_KEY env var richiesta. CORS aperto. Cache 30 min.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.parse
import urllib.request

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
FINNHUB_BASE = "https://finnhub.io/api/v1"

_CACHE = {}  # (from,to) -> (timestamp, full_calendar)
_CACHE_TTL = 1800  # 30 min


def fetch_calendar(from_date: str, to_date: str):
    if not FINNHUB_API_KEY:
        return None, "FINNHUB_API_KEY missing"
    cache_key = f"{from_date}:{to_date}"
    cached = _CACHE.get(cache_key)
    now = time.time()
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1], None
    try:
        params = urllib.parse.urlencode({
            "from": from_date,
            "to": to_date,
            "token": FINNHUB_API_KEY,
        })
        url = f"{FINNHUB_BASE}/calendar/earnings?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("earningsCalendar", []) or []
        _CACHE[cache_key] = (now, items)
        return items, None
    except Exception as e:
        if cached:
            return cached[1], None
        return None, str(e)


class handler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            symbols_raw = (qs.get("symbols", [""])[0] or "").strip()
            try:
                days = int(qs.get("days", ["30"])[0])
            except ValueError:
                days = 30
            days = max(1, min(days, 90))

            symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()][:60]
            symbols_base = {s.split(".")[0] for s in symbols}

            today = time.gmtime()
            from_date = time.strftime("%Y-%m-%d", today)
            to_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() + days * 86400))

            items, err = fetch_calendar(from_date, to_date)
            if items is None:
                self._respond(503, {"ok": False, "error": err or "fetch failed"})
                return

            # Filtra sui ticker richiesti (matching base senza suffisso)
            filtered = []
            if symbols:
                for e in items:
                    sym = (e.get("symbol") or "").upper()
                    base = sym.split(".")[0]
                    if base in symbols_base or sym in symbols:
                        filtered.append({
                            "symbol": sym,
                            "date": e.get("date"),
                            "hour": e.get("hour", ""),  # bmo, amc, dmh
                            "epsEstimate": e.get("epsEstimate"),
                            "epsActual": e.get("epsActual"),
                            "revenueEstimate": e.get("revenueEstimate"),
                            "revenueActual": e.get("revenueActual"),
                            "year": e.get("year"),
                            "quarter": e.get("quarter"),
                        })
            else:
                # Senza filtro: top 50 per data
                for e in items[:50]:
                    filtered.append({
                        "symbol": e.get("symbol"),
                        "date": e.get("date"),
                        "hour": e.get("hour", ""),
                        "epsEstimate": e.get("epsEstimate"),
                        "epsActual": e.get("epsActual"),
                        "revenueEstimate": e.get("revenueEstimate"),
                        "revenueActual": e.get("revenueActual"),
                        "year": e.get("year"),
                        "quarter": e.get("quarter"),
                    })

            # Ordina per data
            filtered.sort(key=lambda x: x.get("date") or "")

            self._respond(200, {
                "ok": True,
                "ts": int(time.time()),
                "from": from_date,
                "to": to_date,
                "count": len(filtered),
                "symbols_requested": symbols,
                "earnings": filtered,
            })
        except Exception as e:
            self._respond(500, {"ok": False, "error": str(e)})

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=1800")
        self._set_cors()
        self.end_headers()
        self.wfile.write(payload)
