"""
Vercel Function: GET /api/debug_env
Verifica presenza env var (non rivela il valore).
"""
from http.server import BaseHTTPRequestHandler
import json
import os


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        finnhub = os.environ.get("FINNHUB_API_KEY", "")
        body = {
            "finnhub_present": bool(finnhub),
            "finnhub_length": len(finnhub),
            "finnhub_prefix": finnhub[:4] if finnhub else None,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
