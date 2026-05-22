"""
Vercel Function: GET /api/signals-cache

Smart cache per l'algoritmo Segnali v2.0:
  - Se l'ultimo snapshot committato in data/signals_v2_snapshot.json ha età <30 min
    → restituisce direttamente quel JSON (istantaneo, zero chiamate Yahoo)
  - Altrimenti → chiama /api/signals-run per ricalcolare live (e ottenere fresh data)

Questo è l'endpoint che il bottone "Aggiorna segnali" della dashboard deve chiamare.

Cache 30 min lato server.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signals_v2_snapshot.json")
FRESH_TTL_MIN = 30  # se snapshot più recente di questo → usa cache, altrimenti ricalcola

# Self URL: il proxy chiama sé stesso. In dev usa localhost, in prod il dominio Vercel.
SELF_BASE = os.environ.get("VERCEL_URL")
SELF_URL = f"https://{SELF_BASE}" if SELF_BASE else "https://yahoo-proxy-missere.vercel.app"


def load_local_snapshot():
    """Legge data/signals_v2_snapshot.json (committato dal cron)."""
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def age_minutes(snapshot):
    """Quanti minuti sono passati dal generated_at."""
    try:
        gen = snapshot.get("generated_at")
        if not gen:
            return None
        dt = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return None


def call_signals_run(commit=False):
    """Chiama /api/signals-run per ricalcolare."""
    url = SELF_URL + "/api/signals-run"
    if commit:
        url += "?commit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "signals-cache-proxy"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"signals_run_call: {str(e)[:120]}"}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body_dict):
        body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=30, s-maxage=60")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            force = params.get("force", ["0"])[0] == "1"

            snap = load_local_snapshot()
            if snap and not force:
                age = age_minutes(snap)
                if age is not None and age < FRESH_TTL_MIN:
                    snap["from_committed_snapshot"] = True
                    snap["snapshot_age_min"] = round(age, 1)
                    return self._send(200, snap)

            # Snapshot vecchio o mancante → ricalcola
            fresh = call_signals_run(commit=False)
            fresh["from_committed_snapshot"] = False
            if snap:
                fresh["previous_snapshot_age_min"] = round(age_minutes(snap) or 0, 1)
            return self._send(200, fresh)

        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)[:200]})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
