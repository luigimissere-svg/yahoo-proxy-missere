"""
Vercel Function: GET /api/signals-tracker

Restituisce lo stato del tracker dei segnali del Daily Ideas Engine.
Legge data/signals_history.json (committato dal workspace tramite cron locale)
e ritorna:
  - meta: updated_at, count_total, count_open, count_closed
  - stats: hit_ratio_t5/t20/t60, avg_ret_*, best/worst t20, samples_*
  - recent: ultimi 20 segnali (più recenti prima) con followup
  - by_action: aggregati per action (BUY/WATCH/HOLD/REDUCE...)

Cache 120s. CORS aperto.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signals_history.json")
_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 120


def _aggregate_by_action(signals):
    buckets = {}
    for s in signals:
        act = s.get("action") or "UNKNOWN"
        b = buckets.setdefault(act, {"count": 0, "wins_t20": 0, "samples_t20": 0, "ret_sum_t20": 0.0})
        b["count"] += 1
        r = (s.get("followup", {}).get("t20") or {}).get("ret_pct")
        if r is not None:
            b["samples_t20"] += 1
            b["ret_sum_t20"] += r
            if r > 0:
                b["wins_t20"] += 1
    out = {}
    for act, b in buckets.items():
        out[act] = {
            "count": b["count"],
            "samples_t20": b["samples_t20"],
            "hit_ratio_t20": round(b["wins_t20"] / b["samples_t20"] * 100, 1) if b["samples_t20"] else None,
            "avg_ret_t20": round(b["ret_sum_t20"] / b["samples_t20"], 2) if b["samples_t20"] else None,
        }
    return out


def load_payload():
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"]
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except FileNotFoundError:
        return {"ok": False, "error": "signals_history.json not found in deploy", "signals": [], "stats": {}}
    except Exception as e:
        return {"ok": False, "error": f"failed to read history: {str(e)[:120]}", "signals": [], "stats": {}}

    signals = history.get("signals", []) or []
    stats = history.get("stats", {}) or {}

    # ordina per ts_signal desc
    sorted_sigs = sorted(signals, key=lambda s: s.get("ts_signal") or "", reverse=True)
    recent = sorted_sigs[:20]

    payload = {
        "ok": True,
        "updated_at": history.get("updated_at"),
        "version": history.get("version", 1),
        "meta": {
            "count_total": len(signals),
            "count_open": sum(1 for s in signals if s.get("status") == "open"),
            "count_closed": sum(1 for s in signals if s.get("status") == "closed"),
        },
        "stats": stats,
        "by_action": _aggregate_by_action(signals),
        "recent": recent,
    }
    _CACHE["data"] = payload
    _CACHE["ts"] = now
    return payload


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data = load_payload()
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=60, s-maxage=120")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = json.dumps({"ok": False, "error": str(e)[:200]}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(err)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
