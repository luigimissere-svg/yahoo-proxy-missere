"""
Vercel Function: GET /api/insider-buys

Fetcha OpenInsider.com con filtro Cluster Buys (clp=1), parsea la tabella HTML
e restituisce JSON con i top cluster buys SEC Form 4 (≥ 2 insider distinti per
ticker nelle ultime 4 settimane).

Cache 30 min. CORS aperto.

Query params:
  - limit: numero max ticker da restituire (default 30)
  - min_insiders: minimo insider distinti per ticker (default 2)
"""
from http.server import BaseHTTPRequestHandler
import json
import re
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
from html import unescape
from collections import defaultdict


# Filtro: Cluster Buys, ultimi 30 giorni, transazioni ≥ $100k
OPENINSIDER_URL = (
    "http://openinsider.com/screener?"
    "clp=1"            # cluster buys filter
    "&fdlyl=&fdlyh="
    "&fdr=&td=0&tdr="
    "&fdtl=&fdth="
    "&xp=1&xs=1"       # purchases only
    "&vl=100&vh="      # min $100k
    "&ocl=&och="
    "&sic1=-1&sicl=100&sich=9999"
    "&grp=0"
    "&sortcol=0&cnt=100&page=1"
)

_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 1800  # 30 min


def strip_html(s: str) -> str:
    """Rimuove tag HTML e normalizza whitespace. Pulisce anche residui di tooltip JS."""
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    # OpenInsider lascia residui tipo: '\', DELAY, 1)" onmouseout="UnTip()">TICKER'
    if "onmouseout" in s.lower() or "UnTip" in s or "DELAY" in s:
        # Tieni solo la parte dopo l'ultimo '>'
        last_gt = s.rfind(">")
        if last_gt >= 0:
            s = s[last_gt + 1:].strip()
    return s


def parse_money(s: str) -> float:
    """Parsa stringhe come '$1,234,567' o '+$45,000' in float."""
    s = s.replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_int(s: str) -> int:
    s = s.replace(",", "").replace("+", "").strip()
    try:
        return int(s)
    except ValueError:
        return 0


def parse_pct(s: str) -> float:
    s = s.replace("%", "").replace("+", "").replace(",", "").strip()
    if s in ("", "New", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_openinsider():
    """Fetcha pagina OpenInsider, estrae tabella tinytable, ritorna lista righe."""
    req = urllib.request.Request(
        OPENINSIDER_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PatrimonioMissere/1.0)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Trova la tabella class="tinytable" — pattern testato: è la Table[9]
    table_match = re.search(
        r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not table_match:
        return []

    table_html = table_match.group(1)

    # Estrai righe tbody
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)

    results = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 13:
            continue

        # Schema OpenInsider tinytable (17 colonne):
        # 0=X, 1=Filing Date, 2=Trade Date, 3=Ticker, 4=Company Name,
        # 5=Insider Name, 6=Title, 7=Trade Type, 8=Price, 9=Qty,
        # 10=Owned, 11=ΔOwn, 12=Value, 13=1d, 14=1w, 15=1m, 16=6m
        filing_date = strip_html(cells[1])
        trade_date = strip_html(cells[2])
        ticker = strip_html(cells[3]).upper()
        company = strip_html(cells[4])
        insider_name = strip_html(cells[5])
        title = strip_html(cells[6])
        trade_type = strip_html(cells[7])
        price = parse_money(strip_html(cells[8]))
        qty = parse_int(strip_html(cells[9]))
        owned = parse_int(strip_html(cells[10]))
        delta_own_pct = parse_pct(strip_html(cells[11]))
        value = parse_money(strip_html(cells[12]))

        if not ticker or not insider_name:
            continue
        # Solo buy / purchase: trade_type comincia con "P" (es. "P - Purchase")
        tt_upper = trade_type.upper().strip()
        if not (tt_upper.startswith("P") or "PURCHASE" in tt_upper):
            continue
        # Value deve essere positivo per buy
        if value <= 0 or qty <= 0:
            continue

        results.append({
            "filing_date": filing_date,
            "trade_date": trade_date,
            "ticker": ticker,
            "company": company,
            "insider": insider_name,
            "title": title,
            "trade_type": trade_type,
            "price": price,
            "qty": qty,
            "owned_after": owned,
            "delta_own_pct": delta_own_pct,
            "value_usd": value,
        })

    return results


def aggregate_clusters(rows, min_insiders=2, limit=30):
    """
    Aggrega per ticker:
      - n_insiders distinti
      - total_value_usd
      - avg_price
      - most_recent trade_date
      - lista insiders (nome + titolo)
    Filtra ticker con >= min_insiders.
    """
    by_ticker = defaultdict(lambda: {
        "trades": [],
        "insiders": set(),
        "total_value": 0.0,
        "total_qty": 0,
        "max_filing": "",
    })

    for r in rows:
        t = r["ticker"]
        by_ticker[t]["trades"].append(r)
        by_ticker[t]["insiders"].add(r["insider"])
        by_ticker[t]["total_value"] += r["value_usd"]
        by_ticker[t]["total_qty"] += r["qty"]
        if r["filing_date"] > by_ticker[t]["max_filing"]:
            by_ticker[t]["max_filing"] = r["filing_date"]

    clusters = []
    for ticker, agg in by_ticker.items():
        n = len(agg["insiders"])
        if n < min_insiders:
            continue
        # Avg price ponderato per qty
        total_qty = sum(t["qty"] for t in agg["trades"]) or 1
        avg_price = sum(t["price"] * t["qty"] for t in agg["trades"]) / total_qty

        # Lista insider più recenti
        sorted_trades = sorted(agg["trades"], key=lambda x: x["filing_date"], reverse=True)
        insiders_list = []
        seen = set()
        for tr in sorted_trades:
            if tr["insider"] not in seen:
                seen.add(tr["insider"])
                insiders_list.append({
                    "name": tr["insider"],
                    "title": tr["title"],
                    "trade_date": tr["trade_date"],
                    "value_usd": tr["value_usd"],
                })

        # Company name dal primo trade
        company_name = agg["trades"][0].get("company", "")

        clusters.append({
            "ticker": ticker,
            "company": company_name,
            "n_insiders": n,
            "n_trades": len(agg["trades"]),
            "total_value_usd": round(agg["total_value"], 0),
            "total_qty": agg["total_qty"],
            "avg_price": round(avg_price, 2),
            "most_recent_filing": agg["max_filing"],
            "insiders": insiders_list[:5],
            "openinsider_url": f"http://openinsider.com/{ticker}",
        })

    # Ordina per total_value_usd desc
    clusters.sort(key=lambda x: x["total_value_usd"], reverse=True)
    return clusters[:limit]


def get_data(limit=30, min_insiders=2):
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"], True
    try:
        rows = fetch_openinsider()
        clusters = aggregate_clusters(rows, min_insiders=min_insiders, limit=limit)
        data = {
            "ok": True,
            "source": "openinsider.com",
            "filter": "cluster_buys",
            "filing_window_days": 30,
            "min_value_usd": 100000,
            "min_insiders": min_insiders,
            "n_clusters": len(clusters),
            "n_raw_trades": len(rows),
            "clusters": clusters,
            "fetched_at": int(now),
        }
        _CACHE["data"] = data
        _CACHE["ts"] = now
        return data, False
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        if _CACHE["data"] is not None:
            return _CACHE["data"], True
        return {"ok": False, "error": f"openinsider_unavailable: {str(e)[:120]}", "clusters": []}, False
    except Exception as e:
        if _CACHE["data"] is not None:
            return _CACHE["data"], True
        return {"ok": False, "error": f"parse_error: {str(e)[:120]}", "clusters": []}, False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse query params
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            limit = int(qs.get("limit", ["30"])[0])
            limit = max(1, min(100, limit))
        except ValueError:
            limit = 30
        try:
            min_insiders = int(qs.get("min_insiders", ["2"])[0])
            min_insiders = max(2, min(10, min_insiders))
        except ValueError:
            min_insiders = 2

        data, cached = get_data(limit=limit, min_insiders=min_insiders)
        body = dict(data)
        body["proxy_cached"] = cached

        self.send_response(200 if data.get("ok") else 502)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=1800")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
