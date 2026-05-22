"""
Vercel Function: GET /api/signals-cache

Legge lo snapshot Segnali v2.0 generato e committato da GitHub Actions.

Strategia:
  1. Legge data/signals_v2_snapshot.json dal repo via GitHub raw CDN (cache 60s function-level)
  2. Calcola età dello snapshot (in minuti)
  3. Ritorna il payload con metadata: from_committed_snapshot, snapshot_age_min, next_cron_at

Il bottone "Aggiorna segnali" della dashboard può chiamare /api/signals-trigger
per forzare un nuovo run on-demand via GitHub Actions workflow_dispatch.

Cache 60s lato server.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

GH_OWNER = os.environ.get("GH_OWNER", "luigimissere-svg")
GH_REPO = os.environ.get("GH_REPO", "yahoo-proxy-missere")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
SNAPSHOT_PATH = "data/signals_v2_snapshot.json"

RAW_URL = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/{SNAPSHOT_PATH}"

_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 60


def fetch_snapshot_from_github():
    """Legge l'ultimo snapshot dal raw GitHub CDN."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"], True  # from function cache

    req = urllib.request.Request(
        RAW_URL,
        headers={"User-Agent": "PatrimonioMissere-signals-cache/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _CACHE["data"] = data
        _CACHE["ts"] = now
        return data, False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "error": "snapshot not yet generated (run GitHub Action first)"}, False
        return {"ok": False, "error": f"github_raw_http_{e.code}"}, False
    except Exception as e:
        return {"ok": False, "error": f"github_raw: {str(e)[:120]}"}, False


def age_minutes(snapshot):
    try:
        gen = snapshot.get("generated_at")
        if not gen:
            return None
        dt = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return None


def next_cron_at():
    """Ritorna timestamp ISO del prossimo cron schedulato (più vicino)."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=lun, 6=dom
    # Cron UTC: 08:00, 12:00, 15:35, 20:05 nei giorni 0-4 (lun-ven)
    targets_utc = [(8, 0), (12, 0), (15, 35), (20, 5)]
    candidates = []
    for days_ahead in range(0, 7):
        d = now.replace(hour=0, minute=0, second=0, microsecond=0)
        d = d.replace(day=d.day) if days_ahead == 0 else d
        try:
            d_target = d.replace(hour=0, minute=0)
            from datetime import timedelta
            d_target = d_target + timedelta(days=days_ahead)
        except Exception:
            continue
        if d_target.weekday() > 4:
            continue
        for h, m in targets_utc:
            t = d_target.replace(hour=h, minute=m)
            if t > now:
                candidates.append(t)
    if not candidates:
        return None
    candidates.sort()
    return candidates[0].isoformat()


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
            snap, from_func_cache = fetch_snapshot_from_github()

            if not snap.get("ok") if isinstance(snap.get("ok"), bool) else (snap.get("error") is not None):
                # Errore o snapshot mancante
                return self._send(200, {
                    "ok": False,
                    "error": snap.get("error", "unknown"),
                    "next_cron_at": next_cron_at(),
                })

            age = age_minutes(snap)
            payload = dict(snap)
            payload["ok"] = True
            payload["from_committed_snapshot"] = True
            payload["from_function_cache"] = from_func_cache
            payload["snapshot_age_min"] = round(age, 1) if age is not None else None
            payload["next_cron_at"] = next_cron_at()
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
