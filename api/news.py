"""
Vercel Function: GET /api/news?symbols=MSFT,UCG.MI,...&limit=20[&all=1]
Recupera le news combinando Yahoo Finance (cover EU) + Finnhub (cover USA pro-grade).

- Holdings USA (no suffisso .XX) -> Finnhub (10x più news, fonti Reuters/Bloomberg/Benzinga)
- Holdings EU (con suffisso .MI/.PA/.DE/...) -> Yahoo (Finnhub gratuito non copre EU)
- General market news -> Finnhub (fonti professionali)
- Cache in-memory 5 minuti per ridurre carico provider
- CORS aperto, dedup per uuid, ordinato per data discendente
- Tronca a 'limit' (default 20, max 50)
- ?all=1 -> include news generiche e market-wide news

FINNHUB_API_KEY: env var Vercel. Se mancante, fallback a sole news Yahoo.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _is_us_ticker(t: str) -> bool:
    """True se il ticker non ha suffisso di mercato (.MI, .PA, .DE, .AS, .MC, .CO, .VI, .AT, .L, .SS)."""
    if not t:
        return False
    suffix = t.split(".")[-1] if "." in t else ""
    # Lista stock exchanges non-USA
    return suffix.upper() not in {"MI", "PA", "DE", "AS", "MC", "CO", "VI", "AT", "L", "SS", "HK", "T", "TO", "ST", "OL", "BR", "LS", "WA", "PR", "BUD", "AX", "NZ"}


def fetch_finnhub_company_news(symbol: str, days: int = 7, max_items: int = 8):
    """Scarica news da Finnhub per ticker USA. Restituisce lista normalizzata."""
    if not FINNHUB_API_KEY:
        return []
    today = time.gmtime()
    to_date = time.strftime("%Y-%m-%d", today)
    from_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    try:
        params = urllib.parse.urlencode({
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": FINNHUB_API_KEY,
        })
        url = f"{FINNHUB_BASE}/company-news?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        if not isinstance(items, list):
            return []
        # Ordina desc per datetime e tronca
        items.sort(key=lambda x: x.get("datetime", 0), reverse=True)
        out = []
        for n in items[:max_items]:
            out.append({
                "uuid": f"finnhub-{n.get('id')}",
                "title": n.get("headline"),
                "publisher": n.get("source", "Finnhub"),
                "link": n.get("url"),
                "providerPublishTime": n.get("datetime"),
                "type": "STORY",
                "relatedTickers": [n.get("related") or symbol],
                "symbol": symbol,
                "_source": "finnhub",
            })
        return out
    except Exception:
        return []


def fetch_finnhub_general_news(category: str = "general", max_items: int = 30):
    """Scarica market news generali (Reuters/Bloomberg/etc) da Finnhub."""
    if not FINNHUB_API_KEY:
        return []
    try:
        params = urllib.parse.urlencode({
            "category": category,
            "token": FINNHUB_API_KEY,
        })
        url = f"{FINNHUB_BASE}/news?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        if not isinstance(items, list):
            return []
        out = []
        for n in items[:max_items]:
            out.append({
                "uuid": f"finnhub-gen-{n.get('id')}",
                "title": n.get("headline"),
                "publisher": n.get("source", "Finnhub"),
                "link": n.get("url"),
                "providerPublishTime": n.get("datetime"),
                "type": "STORY",
                "relatedTickers": [],
                "symbol": "",
                "_source": "finnhub-general",
            })
        return out
    except Exception:
        return []

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

            # all=1 -> restituisce TUTTE le news raccolte (senza filtro per relatedTickers)
            # utile per la card "Tutte le news" che vuole anche le notizie macro/generiche.
            include_all = (qs.get("all", ["0"])[0] or "0").lower() in ("1", "true", "yes")

            # Split ticker USA vs EU
            us_tickers = [s for s in symbols if _is_us_ticker(s)]
            eu_tickers = [s for s in symbols if not _is_us_ticker(s)]

            # Fetch in parallelo:
            #   - Yahoo per TUTTI i ticker (già funziona, copre EU)
            #   - Finnhub per ticker USA (qualità superiore)
            #   - Finnhub general news se include_all
            all_news = []
            with ThreadPoolExecutor(max_workers=10) as ex:
                # Tasks futures
                yahoo_futs = [ex.submit(fetch_news_for_symbol, s) for s in symbols]
                finn_futs = [ex.submit(fetch_finnhub_company_news, s) for s in us_tickers]
                gen_fut = ex.submit(fetch_finnhub_general_news) if include_all else None
                # Raccogli
                for f in yahoo_futs:
                    try:
                        all_news.extend(f.result(timeout=10) or [])
                    except Exception:
                        pass
                for f in finn_futs:
                    try:
                        all_news.extend(f.result(timeout=10) or [])
                    except Exception:
                        pass
                if gen_fut is not None:
                    try:
                        all_news.extend(gen_fut.result(timeout=10) or [])
                    except Exception:
                        pass

            # Costruisci set ticker "base" richiesti per il matching (rimuove suffisso .MI/.PA/.DE/.AS/.MC/.CO/.VI/.AT)
            def _base(t):
                return t.split(".")[0].upper() if t else ""
            requested_base = {_base(s) for s in symbols if s}
            requested_full = {s.upper() for s in symbols if s}

            # Deduplica per uuid + similarity title-time (Yahoo e Finnhub spesso hanno la stessa news)
            seen_uid = set()
            seen_titles = []  # lista di (title_norm, time) per dedup soft

            def _title_norm(t):
                return "".join(c.lower() for c in (t or "") if c.isalnum())[:60]

            deduped = []
            for n in all_news:
                uid = n.get("uuid")
                if not uid or uid in seen_uid:
                    continue
                # Dedup soft: titolo normalizzato simile + entro 6 ore
                tn = _title_norm(n.get("title"))
                ts_n = n.get("providerPublishTime") or 0
                duplicate = False
                if tn:
                    for tn2, ts2 in seen_titles:
                        if tn == tn2 and abs(ts_n - ts2) < 21600:
                            duplicate = True
                            break
                if duplicate:
                    continue

                rel = [t for t in (n.get("relatedTickers") or []) if t]
                # Trova il primo relatedTicker che matcha un ticker richiesto
                primary = None
                for rt in rel:
                    if rt.upper() in requested_full:
                        primary = rt
                        break
                if not primary:
                    for rt in rel:
                        if _base(rt) in requested_base:
                            primary = rt
                            break
                # Per news Finnhub company, il symbol è già affidabile
                if not primary and n.get("_source") == "finnhub" and n.get("symbol") in requested_full:
                    primary = n["symbol"]
                if primary:
                    n["symbol"] = primary
                    n["matches_portfolio"] = True
                else:
                    if not include_all:
                        continue  # news generica, scarta in modalità "miei titoli"
                    n["matches_portfolio"] = False
                    n["symbol"] = ""
                seen_uid.add(uid)
                if tn:
                    seen_titles.append((tn, ts_n))
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
