"""Debug endpoint: testa direttamente Yahoo chart da Vercel."""
from http.server import BaseHTTPRequestHandler
import json
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        results = {}
        for ticker in ["MSFT", "TRN.MI", "FTSEMIB.MI", "^GSPC"]:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    code = resp.status
                    j = json.loads(resp.read().decode("utf-8"))
                    err = j.get("chart", {}).get("error")
                    meta = j.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    results[ticker] = {
                        "http": code,
                        "yahoo_err": err,
                        "price": meta.get("regularMarketPrice"),
                        "prev": meta.get("chartPreviousClose"),
                    }
            except Exception as e:
                results[ticker] = {"exception": str(e)[:200]}

        body = json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
