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

MARKETAUX_API_TOKEN = os.environ.get("MARKETAUX_API_TOKEN", "").strip()
MARKETAUX_BASE = "https://api.marketaux.com/v1"

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "").strip()
NEWSAPI_BASE = "https://newsapi.org/v2"

# Mappa ticker -> nome cercabile per NewsAPI (azienda + alias notori)
NEWSAPI_QUERY_MAP = {
    "NVDA": "Nvidia", "MSFT": "Microsoft", "MU": "Micron", "AMT": "American Tower",
    "META": "Meta Platforms",
    "ASML.AS": "ASML", "ADYEN.AS": "Adyen", "NESN.SW": "Nestle",
    "NOVO-B.CO": "Novo Nordisk", "RACE.MI": "Ferrari", "RHM.DE": "Rheinmetall",
    "STM.MI": "STMicroelectronics", "ENI.MI": "Eni", "ENEL.MI": "Enel",
    "ISP.MI": "Intesa Sanpaolo", "UCG.MI": "UniCredit", "CDP.MI": "Cassa Depositi",
    "TIT.MI": "Telecom Italia", "VOW3.DE": "Volkswagen", "SAP.DE": "SAP",
    "DTE.DE": "Deutsche Telekom",
    "ALNOV.PA": "Albioma", "ALBIO.PA": "Albioma", "EL.PA": "EssilorLuxottica",
}

# Domini italiani affidabili (filtrati a valle)
ITALIAN_FIN_DOMAINS = {
    "ilsole24ore.com", "repubblica.it", "ansa.it", "corriere.it",
    "milanofinanza.it", "borsaitaliana.it", "finanzaonline.com",
    "soldionline.it", "trend-online.com", "economyup.it",
    "firstonline.info", "ilmessaggero.it", "lastampa.it",
}

# Pattern di esclusione per filtrare rumore (sport, gossip, gaming)
NEWSAPI_NOISE_KEYWORDS = (
    "calcio", "football", "sampdoria", "reggiana", "forza horizon", "lego",
    "playstation", "xbox", "meloni", "renzi", "garlasco", "omicidio",
    "juventus", "milan", "inter", "napoli calcio", "premier league",
)


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


def fetch_marketaux_news(symbols: list, max_items: int = 20):
    """Scarica news da Marketaux per ticker (USA + EU). Restituisce lista normalizzata.

    Marketaux usa il formato simbolo nativo (es. NVDA, ENI.MI, RACE.MI, ASML.AS).
    Free tier: 100 richieste/giorno - usiamo una sola richiesta per tutti i ticker.
    Lingua: english + italian.
    """
    if not MARKETAUX_API_TOKEN or not symbols:
        return []
    try:
        params = urllib.parse.urlencode({
            "symbols": ",".join(symbols[:50]),  # max 50 per chiamata
            "filter_entities": "true",
            "language": "en,it",
            "limit": max_items,
            "api_token": MARKETAUX_API_TOKEN,
        })
        url = f"{MARKETAUX_BASE}/news/all?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", []) or []
        out = []
        for n in items:
            entities = n.get("entities") or []
            # Match ticker primario
            primary = None
            best_sentiment = None
            for e in entities:
                sym = e.get("symbol")
                if sym and sym in symbols and not primary:
                    primary = sym
                if best_sentiment is None and e.get("sentiment_score") is not None:
                    best_sentiment = e.get("sentiment_score")
            if not primary and entities:
                primary = entities[0].get("symbol") or ""
            # Parse timestamp -> epoch
            pub = n.get("published_at") or ""
            ts_epoch = 0
            try:
                from datetime import datetime
                ts_epoch = int(datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts_epoch = 0
            sentiment_label = None
            if best_sentiment is not None:
                if best_sentiment > 0.15:
                    sentiment_label = "positive"
                elif best_sentiment < -0.15:
                    sentiment_label = "negative"
                else:
                    sentiment_label = "neutral"
            out.append({
                "uuid": f"marketaux-{n.get('uuid')}",
                "title": n.get("title"),
                "publisher": n.get("source", "Marketaux"),
                "link": n.get("url"),
                "providerPublishTime": ts_epoch,
                "type": "STORY",
                "relatedTickers": [e.get("symbol") for e in entities if e.get("symbol")],
                "symbol": primary or "",
                "sentiment": sentiment_label,
                "sentiment_score": best_sentiment,
                "_source": "marketaux",
            })
        return out
    except Exception:
        return []


def fetch_newsapi_for_ticker(ticker: str, max_items: int = 5):
    """Cerca news NewsAPI per uno specifico ticker, usando il nome azienda + filtri qualità."""
    if not NEWSAPI_KEY:
        return []
    company_name = NEWSAPI_QUERY_MAP.get(ticker)
    if not company_name:
        return []
    try:
        # Cerco su finanza/economia: 'NomeAzienda AND (azione OR borsa OR earnings OR mercato OR investitori)'
        # Poi filtro a valle per dominio fidato.
        query = f'"{company_name}" AND (azione OR borsa OR earnings OR mercato OR investitori OR ricavi OR utile OR trimestre OR shares)'
        # Ultimi 3 giorni
        from datetime import datetime as _dt, timedelta as _td
        from_date = (_dt.utcnow() - _td(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        params = urllib.parse.urlencode({
            "q": query,
            "language": "it,en",
            "sortBy": "publishedAt",
            "pageSize": min(max_items * 3, 20),
            "from": from_date,
            "apiKey": NEWSAPI_KEY,
        })
        url = f"{NEWSAPI_BASE}/everything?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "ok":
            return []
        articles = data.get("articles", []) or []
        out = []
        for a in articles:
            title = (a.get("title") or "").strip()
            if not title or len(title) < 12:
                continue
            # Filtra rumore
            tl = title.lower()
            if any(k in tl for k in NEWSAPI_NOISE_KEYWORDS):
                continue
            url_a = a.get("url") or ""
            domain = url_a.split("//")[-1].split("/")[0].replace("www.", "") if url_a else ""
            # Parse timestamp
            pub = a.get("publishedAt") or ""
            ts_epoch = 0
            try:
                from datetime import datetime as _dt2
                ts_epoch = int(_dt2.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
            out.append({
                "uuid": f"newsapi-{abs(hash(url_a)) % (10**12)}",
                "title": title,
                "publisher": (a.get("source") or {}).get("name", "NewsAPI"),
                "link": url_a,
                "providerPublishTime": ts_epoch,
                "type": "STORY",
                "relatedTickers": [ticker],
                "symbol": ticker,
                "_source": "newsapi",
                "_domain": domain,
            })
            if len(out) >= max_items:
                break
        return out
    except Exception:
        return []


def fetch_newsapi_italian_business(max_items: int = 15):
    """Top business headlines dalle testate finanziarie italiane.
    Cerca termini market-wide e filtra per dominio."""
    if not NEWSAPI_KEY:
        return []
    try:
        domains = ",".join(sorted(ITALIAN_FIN_DOMAINS))
        params = urllib.parse.urlencode({
            "q": "borsa OR mercati OR azioni OR FTSE OR Piazza Affari OR Wall Street OR rendimento OR BTP OR Bce OR Fed",
            "domains": domains,
            "language": "it",
            "sortBy": "publishedAt",
            "pageSize": max_items,
            "apiKey": NEWSAPI_KEY,
        })
        url = f"{NEWSAPI_BASE}/everything?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PortfolioDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "ok":
            return []
        articles = data.get("articles", []) or []
        out = []
        for a in articles:
            title = (a.get("title") or "").strip()
            if not title or len(title) < 12:
                continue
            tl = title.lower()
            if any(k in tl for k in NEWSAPI_NOISE_KEYWORDS):
                continue
            url_a = a.get("url") or ""
            pub = a.get("publishedAt") or ""
            ts_epoch = 0
            try:
                from datetime import datetime as _dt3
                ts_epoch = int(_dt3.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
            out.append({
                "uuid": f"newsapi-it-{abs(hash(url_a)) % (10**12)}",
                "title": title,
                "publisher": (a.get("source") or {}).get("name", "NewsAPI"),
                "link": url_a,
                "providerPublishTime": ts_epoch,
                "type": "STORY",
                "relatedTickers": [],
                "symbol": "",
                "_source": "newsapi",
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
                "_source": "yahoo",
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
            #   - Marketaux per TUTTI i ticker (USA + EU + sentiment + stampa italiana)
            all_news = []
            with ThreadPoolExecutor(max_workers=12) as ex:
                yahoo_futs = [ex.submit(fetch_news_for_symbol, s) for s in symbols]
                finn_futs = [ex.submit(fetch_finnhub_company_news, s) for s in us_tickers]
                gen_fut = ex.submit(fetch_finnhub_general_news) if include_all else None
                marketaux_fut = ex.submit(fetch_marketaux_news, symbols, 25)
                # NewsAPI: 1 chiamata per ticker mappato (max 8 ticker per limitare uso quota)
                # + 1 chiamata market-wide italiano se include_all
                newsapi_tickers = [s for s in symbols if s in NEWSAPI_QUERY_MAP][:8]
                newsapi_tk_futs = [ex.submit(fetch_newsapi_for_ticker, s, 4) for s in newsapi_tickers]
                newsapi_it_fut = ex.submit(fetch_newsapi_italian_business, 12) if include_all else None
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
                try:
                    all_news.extend(marketaux_fut.result(timeout=12) or [])
                except Exception:
                    pass
                for f in newsapi_tk_futs:
                    try:
                        all_news.extend(f.result(timeout=10) or [])
                    except Exception:
                        pass
                if newsapi_it_fut is not None:
                    try:
                        all_news.extend(newsapi_it_fut.result(timeout=10) or [])
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
