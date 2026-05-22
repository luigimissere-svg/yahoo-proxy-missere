"""
Vercel Function: GET /api/discovery

Espone il Discovery snapshot — top-N titoli interessanti sull'universo
allargato (USA S&P500 + Europa STOXX600 + Italia FTSE MIB + FTSE Italia
Mid Cap), esclusi quelli già nel portafoglio dell'utente.

Strategia identica a /api/walkforward:
  1. Legge quant_v3/discovery_snapshot.json dal repo via GitHub raw CDN
  2. Cache function-level 10 min (Discovery cambia mensilmente)
  3. Ritorna il payload con metadata di freshness

Generato da quant_v3/scripts/generate_discovery_snapshot.py e committato
sul branch v3-quant-framework. Si aggiorna mensilmente via GitHub Action.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

GH_OWNER = os.environ.get("GH_OWNER", "luigimissere-svg")
GH_REPO = os.environ.get("GH_REPO", "yahoo-proxy-missere")
GH_BRANCH = os.environ.get("DISCOVERY_GH_BRANCH", "v3-quant-framework")
SNAPSHOT_PATH = "quant_v3/discovery_snapshot.json"

RAW_URL = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/{SNAPSHOT_PATH}"

_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 600  # 10 minuti


def fetch_snapshot_from_github():
    """Legge l'ultimo Discovery snapshot dal raw GitHub CDN."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"], True

    req = urllib.request.Request(
        RAW_URL,
        headers={"User-Agent": "PatrimonioMissere-discovery/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _CACHE["data"] = data
        _CACHE["ts"] = now
        return data, False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "error": (
                    f"discovery snapshot not found on branch {GH_BRANCH} "
                    f"(path: {SNAPSHOT_PATH}). Run "
                    "scripts/generate_discovery_snapshot.py and commit."
                ),
            }, False
        return {"error": f"github_raw_http_{e.code}"}, False
    except Exception as e:
        return {"error": f"github_raw: {str(e)[:120]}"}, False


def age_minutes(snapshot):
    """Età dello snapshot in minuti, dal campo _meta.generated_at."""
    try:
        gen = snapshot.get("_meta", {}).get("generated_at")
        if not gen:
            return None
        dt = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body_dict):
        body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # Cache aggressiva: Discovery cambia mensilmente
        self.send_header("Cache-Control", "public, max-age=600, s-maxage=1800")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            snap, from_func_cache = fetch_snapshot_from_github()

            if snap.get("error"):
                return self._send(200, {
                    "ok": False,
                    "error": snap["error"],
                    "raw_url": RAW_URL,
                })

            age = age_minutes(snap)
            payload = dict(snap)
            payload["ok"] = True
            payload["from_committed_snapshot"] = True
            payload["from_function_cache"] = from_func_cache
            payload["snapshot_age_min"] = round(age, 1) if age is not None else None
            payload["raw_url"] = RAW_URL

            return self._send(200, payload)

        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)[:200]})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
