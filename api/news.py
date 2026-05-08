"""
Vercel Function: GET /api/news?symbols=MSFT,UCG.MI,...&limit=20
Recupera le news da Yahoo Finance per i ticker passati.
- Cache in-memory 5 minuti per ridurre carico Yahoo
- CORS aperto
- Deduplica per uuid
- Ordina per data discendente
- Tronca a 'limit' news (default 20, max 50)
"""
from http.server import BaseHTTPRequestHandler
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Cache in-memory (warm container)
_CACHE = {}  # symbol -> (timestamp, news_list)
_CACHE_TTL = 300  # 5 minuti

YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PortfolioBot/1.0)",
    "Accept": "application/json",
}


def fetch_news_for_symbol(symbol: str, max_per_symbol: int = 6):
    """Fetch news per un singolo simbolo Yahoo. Usa la cache se valida."""
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        params = urllib.parse.urlencode({
            "q": symbol,
            "lang": "it-IT",
            "region": "IT",
            "quotesCount": 0,
            "newsCount": max_per_symbol,
            "enableFuzzyQuery": "false",
        })
        url = f"{YAHOO_SEARCH}?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("news", []) or []
        news_list = []
        for n in items:
            news_list.append({
                "uuid": n.get("uuid"),
                "title": n.get("title"),
                "publisher": n.get("publisher"),
                "link": n.get("link"),
                "providerPublishTime": n.get("providerPublishTime"),  # epoch
                "type": n.get("type"),
                "relatedTickers": n.get("relatedTickers", []),
                "symbol": symbol,  # ticker richiesto (per filtraggio in UI)
            })
        _CACHE[symbol] = (now, news_list)
        return news_list
    except Exception as e:
        # Se cache stantia esiste, restituisci quella in caso di errore
        if cached:
            return cached[1]
        return []


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
            if not symbols_raw:
                self._respond(400, {"ok": False, "error": "missing symbols param"})
                return
            try:
                limit = int(qs.get("limit", ["20"])[0])
            except ValueError:
                limit = 20
            limit = max(1, min(limit, 50))

            symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()][:30]

            # Fetch in parallelo
            all_news = []
            with ThreadPoolExecutor(max_workers=8) as ex:
                results = list(ex.map(fetch_news_for_symbol, symbols))
            for lst in results:
                all_news.extend(lst)

            # Deduplica per uuid (mantenendo prima occorrenza)
            seen = set()
            deduped = []
            for n in all_news:
                uid = n.get("uuid")
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                deduped.append(n)

            # Ordina per data discendente
            deduped.sort(key=lambda x: x.get("providerPublishTime") or 0, reverse=True)

            # Tronca
            deduped = deduped[:limit]

            self._respond(200, {
                "ok": True,
                "ts": int(time.time()),
                "count": len(deduped),
                "symbols_requested": symbols,
                "news": deduped,
            })
        except Exception as e:
            self._respond(500, {"ok": False, "error": str(e)})

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=60")  # CDN cache
        self._set_cors()
        self.end_headers()
        self.wfile.write(payload)
