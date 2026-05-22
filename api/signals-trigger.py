"""
Vercel Function: POST /api/signals-trigger

Scatena un run on-demand del workflow GitHub Actions 'signals-run.yml'
via API workflow_dispatch.

Richiede env var:
  - GITHUB_TOKEN (PAT con scope 'repo' o token GitHub App con workflows write)

Limiti integrati:
  - Throttle: max 1 trigger ogni 60s (per evitare abuse e race condition col cron)
  - GitHub Actions free tier: 2000min/mese, ogni run dura ~30-60s, quindi possiamo
    fare migliaia di trigger/mese senza problemi.

Risposta:
  - 200 {ok:true, run_id: null, started_at, message} se accettato
    (GitHub workflow_dispatch ritorna 204 no body, dobbiamo poi pollare)
  - 429 se throttled
  - 401 se GITHUB_TOKEN mancante
  - 502 se GitHub API errore
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

GH_OWNER = os.environ.get("GH_OWNER", "luigimissere-svg")
GH_REPO = os.environ.get("GH_REPO", "yahoo-proxy-missere")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
WORKFLOW_FILE = "signals-run.yml"

# Throttle: 1 trigger ogni N secondi
THROTTLE_SECONDS = 60
_LAST_TRIGGER = {"ts": 0}


def trigger_workflow(reason: str = "dashboard manual"):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"ok": False, "status": 401, "error": "GITHUB_TOKEN env missing"}

    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"

    payload = {
        "ref": GH_BRANCH,
        "inputs": {
            "reason": reason[:80],
        },
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PatrimonioMissere-signals-trigger/1.0",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # workflow_dispatch ritorna 204 No Content
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        return {"ok": False, "status": e.code, "error": f"github_api: {e.reason}", "body": body}
    except Exception as e:
        return {"ok": False, "status": 500, "error": f"trigger: {str(e)[:120]}"}


def _get_latest_run():
    """Recupera l'ultimo run del workflow per dare un riferimento all'utente."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "PatrimonioMissere-signals-trigger/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        runs = j.get("workflow_runs", [])
        if runs:
            r = runs[0]
            return {
                "id": r.get("id"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
                "html_url": r.get("html_url"),
            }
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body_dict):
        body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """GET ritorna solo lo stato dell'ultimo run (utile per polling dalla dashboard)."""
        latest = _get_latest_run()
        return self._send(200, {
            "ok": True,
            "throttle_seconds": THROTTLE_SECONDS,
            "seconds_until_next_trigger_allowed": max(0, THROTTLE_SECONDS - int(time.time() - _LAST_TRIGGER["ts"])),
            "latest_run": latest,
            "workflow_url": f"https://github.com/{GH_OWNER}/{GH_REPO}/actions/workflows/{WORKFLOW_FILE}",
        })

    def do_POST(self):
        try:
            # Throttle
            now = time.time()
            elapsed = now - _LAST_TRIGGER["ts"]
            if elapsed < THROTTLE_SECONDS:
                return self._send(429, {
                    "ok": False,
                    "error": "throttled",
                    "retry_after_seconds": int(THROTTLE_SECONDS - elapsed),
                })

            # Parse body opzionale per "reason"
            content_length = int(self.headers.get("Content-Length", "0"))
            reason = "dashboard manual"
            if content_length > 0:
                try:
                    body_raw = self.rfile.read(content_length).decode("utf-8")
                    body_json = json.loads(body_raw)
                    reason = body_json.get("reason", reason)
                except Exception:
                    pass

            result = trigger_workflow(reason=reason)
            if result.get("ok"):
                _LAST_TRIGGER["ts"] = now
                return self._send(200, {
                    "ok": True,
                    "triggered": True,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "estimated_completion_seconds": 60,
                    "workflow_url": f"https://github.com/{GH_OWNER}/{GH_REPO}/actions/workflows/{WORKFLOW_FILE}",
                    "message": "Run on-demand avviato. Polling /api/signals-cache tra ~60s per il risultato.",
                })
            else:
                return self._send(502, {
                    "ok": False,
                    "error": result.get("error"),
                    "github_status": result.get("status"),
                    "github_body": result.get("body", ""),
                })

        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)[:200]})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
