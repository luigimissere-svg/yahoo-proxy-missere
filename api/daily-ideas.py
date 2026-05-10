"""
Vercel Function: GET /api/daily-ideas
Proxy verso il backend "patrimonio-missere.vercel.app/api/daily-ideas".
Lo script Daily Ideas Engine (cron 5d3d7678) scrive direttamente sul backend
patrimonio-missere; questo proxy permette al frontend di leggere i dati da un
unico endpoint canonico.
Cache 60s. CORS aperto.
"""
from http.server import BaseHTTPRequestHandler
import json
import time
import urllib.request
import urllib.error


UPSTREAM = "https://patrimonio-missere.vercel.app/api/daily-ideas"
_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 60  # 60 secondi


def fetch_upstream():
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"], True
    try:
        req = urllib.request.Request(
            UPSTREAM,
            headers={"User-Agent": "PatrimonioMissere/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            _CACHE["data"] = data
            _CACHE["ts"] = now
            return data, False
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        # In caso di errore, restituisco la cache se presente, altrimenti errore
        if _CACHE["data"] is not None:
            return _CACHE["data"], True
        return {"ok": False, "error": f"upstream_unavailable: {str(e)[:100]}"}, False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data, cached = fetch_upstream()
        body = dict(data)
        body["proxy_cached"] = cached
        self.send_response(200 if data.get("ok") else 502)
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
