"""
Vercel Function: GET /api/event_shock?symbols=NVDA,GMAB.CO,...&days=7&min_score=60

Event Shock Layer v1.1 - layer separato che NON modifica news.py production.
Spec autoritativa: /home/user/workspace/event_shock_classifier_spec_v1.md (sigillata 31/05/2026 12:40).

Architettura (Approccio B):
- Endpoint dedicato, prompt Gemini diverso da news.py
- 9 categorie totali:
  - 6 eligible automatica: FDA_APPROVAL, PHASE_III_SUCCESS, MEGA_CONTRACT_MATERIAL,
    GUIDANCE_RAISE_MATERIAL, MA_TRANSFORMATIVE, PATENT_BREAKTHROUGH
  - 3 manual review: PARTNERSHIP, AI_COLLABORATION, STRATEGIC_ALLIANCE
- EventCredibilityScore = 0.40*Officiality + 0.30*EconomicImpact + 0.20*VolumeShock + 0.10*AnalystReaction
- ShockCandidate gate: score>=80 AND volRatio>=3 AND GapMove>=max(4%, 1.5*dailyVol20d)
                      AND QualityShield!=Red AND NOT YieldTrap AND category eligible
- Cold Start Lock: 01/06 - 30/08/2026, Fast Probation max 1% NAV senza override
- Feature flag: EVENT_SHOCK_ENABLED (default false -> HTTP 503)
- Cache: chiave primaria (symbol,date), chiave secondaria hash(headline+source+date)

Variabili ambiente Vercel:
- EVENT_SHOCK_ENABLED ("true"/"false", default "false")
- GEMINI_API_KEY (riusata)
- FINNHUB_API_KEY (riusata)
- COLD_START_END_DATE (default "2026-08-30")
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import time
import math
import hashlib
import datetime as dt
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

# ---------------- Feature flag + credenziali ----------------
EVENT_SHOCK_ENABLED = os.environ.get("EVENT_SHOCK_ENABLED", "false").strip().lower() in ("1", "true", "yes")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
COLD_START_END_DATE = os.environ.get("COLD_START_END_DATE", "2026-08-30").strip()

FINNHUB_BASE = "https://finnhub.io/api/v1"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_URL_FALLBACK = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Budget Gemini per-request (doppio di news.py: chiamate piu' rare ma piu' lunghe)
_GEMINI_PER_REQUEST_LIMIT = int(os.environ.get("EVSHOCK_GEMINI_LIMIT", "30"))
_GEMINI_REQUEST_COUNTER = {"n": 0}

# Cache in-memory (no Redis)
_CACHE_TTL = 15 * 60  # 15 min (spec 2.3)
_CACHE_PRIMARY = {}     # key: f"evshock:{symbol}:{date.isoformat()}" -> (epoch, payload)
_CACHE_HEADLINE = {}    # key: sha1(headline+source+date) -> (epoch, classification)
_GEMINI_CACHE_MAX = 2000

# ---------------- Tassonomia ----------------
ELIGIBLE_AUTOMATIC = {
    "FDA_APPROVAL",
    "PHASE_III_SUCCESS",
    "MEGA_CONTRACT_MATERIAL",
    "GUIDANCE_RAISE_MATERIAL",
    "MA_TRANSFORMATIVE",
    "PATENT_BREAKTHROUGH",
}
MANUAL_REVIEW = {
    "PARTNERSHIP",
    "AI_COLLABORATION",
    "STRATEGIC_ALLIANCE",
}
ALL_CATEGORIES = ELIGIBLE_AUTOMATIC | MANUAL_REVIEW | {"NONE"}

# Severity logica (spec 3.1)
SEVERITY_BY_CATEGORY = {
    "FDA_APPROVAL": 5,
    "PHASE_III_SUCCESS": 5,
    "MEGA_CONTRACT_MATERIAL": 4,
    "GUIDANCE_RAISE_MATERIAL": 5,
    "MA_TRANSFORMATIVE": 5,
    "PATENT_BREAKTHROUGH": 4,
    "PARTNERSHIP": 3,
    "AI_COLLABORATION": 3,
    "STRATEGIC_ALLIANCE": 3,
    "NONE": 0,
}

# Whitelist controparti tier-1 (spec 3.2)
TIER1_COUNTERPARTIES = {
    "NVIDIA", "NVDA", "MICROSOFT", "MSFT", "GOOGLE", "ALPHABET", "GOOGL",
    "AMAZON", "AMZN", "APPLE", "AAPL", "META", "FACEBOOK",
    "OPENAI", "ANTHROPIC", "SNOWFLAKE", "PALANTIR", "PLTR",
    "TSMC", "ASML", "FERRARI", "LVMH", "SAUDI ARAMCO", "ARAMCO",
    "BLACKROCK", "BERKSHIRE",
}

# Fonti ufficiali / Tier source -> Officiality score (spec 4)
FONTI_OFFICIALI = {
    "fda.gov", "ema.europa.eu", "sec.gov", "defense.gov", "pentagon",
    "businesswire.com", "prnewswire.com", "globenewswire.com",
}
FONTI_TIER_REUTERS = {"reuters.com", "bloomberg.com", "apnews.com", "dowjones.com", "wsj.com"}
FONTI_TIER_MAINSTREAM = {"ft.com", "handelsblatt.com", "ilsole24ore.com", "lesechos.fr", "expansion.com"}

# ---------------- Trigger keyword (filtro pre-Gemini, spec 3.1) ----------------
TRIGGERS = {
    "FDA_APPROVAL": [
        "fda approves", "fda approval", "fda clearance", "fda cleared",
        "fda authorized", "fda grants approval", "approval label expansion",
        "approved label expansion", "ema approval", "ema approves",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "fda grants accelerated approval", "accelerated approval",
        "fda approva", "fda approvato", "approvazione fda",
        "ema approva", "approvato dall'ema",
        "fda-zulassung", "von der fda zugelassen", "ema-zulassung",
        "fda aprueba", "aprobado por la fda", "ema aprueba",
        "fda approuve", "approuve par la fda", "ema approuve",
    ],
    "PHASE_III_SUCCESS": [
        "met primary endpoint", "meets primary endpoint", "achieves primary endpoint",
        "positive top-line results", "positive top line results",
        "statistically significant", "phase 3 success", "phase iii success",
        "approval recommended by panel", "panel recommends approval",
        "ad-com positive vote", "advisory committee recommends",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "phase 3 positive results", "phase iii positive results",
        "phase 3 results", "phase iii results",
        "trial positive results", "trial succeeds",
        "reduces", "slows", "mean weight loss",  # ammessi solo se compaiono
        "raggiunto endpoint primario", "risultati positivi fase 3",
        "raccomandazione positiva", "comitato consultivo raccomanda",
        "primaeren endpunkt erreicht", "phase-3-erfolg",
        "alcanza endpoint primario", "resultados positivos fase 3",
        "atteint le critere principal", "resultats positifs phase 3",
        "chmp positive opinion",
    ],
    "MEGA_CONTRACT_MATERIAL": [
        "wins contract", "awarded contract", "signs contract worth",
        "announces contract", "multi-billion deal", "framework agreement signed",
        "major order", "landmark contract", "prime contractor selected",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "awards lockheed", "awards boeing", "awards airbus",
        "pentagon awards", "dod awards", "production contract",
        "wins record", "record order", "aircraft order",
        "signs purchase agreement", "order valued at",
        "order from", "valued at approximately", "value at list prices",
        "vince contratto", "si aggiudica contratto", "accordo quadro",
        "ordine principale", "contratto pluriennale",
        "vertrag gewonnen", "rahmenvereinbarung", "grossauftrag",
        "gana contrato", "se adjudica", "acuerdo marco", "gran pedido",
        "remporte contrat", "se voit attribuer", "accord-cadre",
    ],
    "GUIDANCE_RAISE_MATERIAL": [
        "raises full-year guidance", "raises fy guidance", "increases guidance",
        "boosts outlook", "upgrades outlook", "raises forecast",
        "raises eps guidance", "raises revenue outlook", "guidance hike",
        "raises q", "raises full year",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "raises full-year", "raises full year", "raises revenue guidance",
        "revenue guidance", "q4 revenue guidance", "q1 revenue guidance",
        "q2 revenue guidance", "q3 revenue guidance",
        "raises", "beats estimates by", "raises full-year 2024",
        "raises full-year 2025", "raises full-year 2026",
        "announces financial results", "earnings",
        "alza la guidance", "rivede al rialzo le stime", "alza outlook", "alza previsioni",
        "hebt prognose an", "erhoeht ausblick", "anhebung der prognose",
        "eleva las previsiones", "mejora outlook", "aumenta perspectivas",
        "releve ses previsions", "ameliore perspectives",
    ],
    "MA_TRANSFORMATIVE": [
        "transformative acquisition", "transformative merger",
        "agrees to acquire for billion", "strategic acquisition",
        "game-changing deal", "all-cash offer billion",
        "definitive agreement to acquire", "cross-industry merger",
        "to acquire for", "completes acquisition of",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "acquisition of", "announces acquisition", "agreed to acquire",
        "acquires for", "merger with", "buys for",
        "acquisizione strategica", "fusione trasformativa", "operazione storica",
        "accordo definitivo per acquisire",
        "transformatorische uebernahme", "strategische akquisition",
        "adquisicion estrategica", "fusion transformadora",
        "acquisition strategique", "fusion transformatrice",
    ],
    "PATENT_BREAKTHROUGH": [
        "patent granted for core technology", "patent granted flagship",
        "key patent issued", "landmark patent", "patent for",
        "fda grants exclusivity", "orphan drug exclusivity granted",
        # Estensioni post-golden-set validation (recall fix 31/05):
        "orphan drug exclusivity", "7-year orphan", "first crispr",
        "first-in-class", "first gene therapy",
        "brevetto concesso tecnologia core", "brevetto chiave",
        "patent fuer kerntechnologie erteilt",
        "patente concedida tecnologia clave",
        "brevet accorde technologie cle",
    ],
    "PARTNERSHIP": ["partnership", "collaboration", "joint venture"],
    "AI_COLLABORATION": [
        "ai partnership", "ai collaboration", "ai deal",
        "generative ai partnership",
        "partners with nvidia", "partners with openai", "partners with anthropic",
        "partners with deepmind",
    ],
    "STRATEGIC_ALLIANCE": [
        "strategic alliance", "long-term alliance",
        "framework alliance", "strategic agreement",
    ],
}

# Esclusioni che mappano ad OTHER (spec 3.1)
EXCLUDE_FDA = [
    "fda review", "fda filing", "fda accepts application",
    "fda accepted application", "fda grants fast track",
    "fda grants priority review", "submits nda", "bla filing", "pdufa date",
]
EXCLUDE_PHASE3 = [
    "phase iii initiated", "phase 3 enrolled", "phase iii enrollment",
    "phase iii data to be presented", "phase 3 filing", "phase iii review",
    "begins phase iii", "starts phase iii", "begins phase 3",
]


def reset_gemini_counter():
    _GEMINI_REQUEST_COUNTER["n"] = 0


# ---------------- Pre-filter keyword ----------------
def _matches_any_trigger(title: str, summary: str) -> str:
    """Ritorna il nome categoria che matcha (primo hit) o '' se nessun trigger.

    Applica anche le esclusioni per FDA/Phase III (spec 3.1).
    """
    if not title:
        return ""
    text = (title + " " + (summary or "")).lower()

    # Esclusioni prima del match positivo
    for ex in EXCLUDE_FDA:
        if ex in text:
            # Se nel testo c'e' "fda approves" insieme a "fda filing" la decisione
            # finale spetta a Gemini; lasciamo passare se trigger positivo presente.
            pass
    # Match positivo (ordine spec)
    for cat in ["FDA_APPROVAL", "PHASE_III_SUCCESS", "MEGA_CONTRACT_MATERIAL",
                "GUIDANCE_RAISE_MATERIAL", "MA_TRANSFORMATIVE", "PATENT_BREAKTHROUGH",
                "AI_COLLABORATION", "STRATEGIC_ALLIANCE", "PARTNERSHIP"]:
        for kw in TRIGGERS[cat]:
            if kw in text:
                # Verifica esclusione contestuale per FDA/Phase3
                if cat == "FDA_APPROVAL":
                    if any(ex in text for ex in EXCLUDE_FDA) and "approves" not in text:
                        return ""
                if cat == "PHASE_III_SUCCESS":
                    if any(ex in text for ex in EXCLUDE_PHASE3):
                        return ""
                return cat
    return ""


# ---------------- Gemini classification ----------------
PROMPT_TEMPLATE = """Sei un classificatore di eventi finanziari market-moving (shock events).
Analizza il seguente titolo e sommario di una news e restituisci JSON con:

- category: una di [FDA_APPROVAL, PHASE_III_SUCCESS, MEGA_CONTRACT_MATERIAL, GUIDANCE_RAISE_MATERIAL, MA_TRANSFORMATIVE, PATENT_BREAKTHROUGH, PARTNERSHIP, AI_COLLABORATION, STRATEGIC_ALLIANCE, NONE]
- is_eligible_automatic: true solo se category in {{FDA_APPROVAL, PHASE_III_SUCCESS, MEGA_CONTRACT_MATERIAL, GUIDANCE_RAISE_MATERIAL, MA_TRANSFORMATIVE, PATENT_BREAKTHROUGH}} E rispetta tutte le condizioni qualitative qui sotto.
- quantitative_value: numero se dichiarato nel testo, altrimenti null.
- quantitative_unit: "USD_BILLIONS" | "USD_MILLIONS" | "PERCENT_GUIDANCE_VS_PREV" | "PERCENT_GUIDANCE_VS_CONSENSUS" | "PERCENT_MARKET_CAP" | null.
- counterparty_tier1: true/false. True se la news menziona NVIDIA, MSFT, GOOGL, AMZN, AAPL, META, OpenAI, Anthropic, Snowflake, Palantir, TSMC, ASML, Ferrari, LVMH, Saudi Aramco, BlackRock, Berkshire.
- source_official: true se la news cita esplicitamente un press release ufficiale dell'emittente, regulatory filing, comunicato FDA/EMA/SEC/Pentagon.

Regole categoria stringenti:

FDA_APPROVAL: solo se "approves" / "clearance" / "approved label expansion". NON e' approval: "FDA review", "FDA filing", "submits NDA", "fast track granted".

PHASE_III_SUCCESS: solo "met primary endpoint", "positive top-line results", "statistically significant", "approval recommended by panel", "CHMP positive opinion". NON e': "phase III initiated", "phase 3 enrolled", "data to be presented".

MEGA_CONTRACT_MATERIAL: solo se quantitative_value >= 500 (USD_MILLIONS) OR >= 1.0 (PERCENT REVENUE). Senza valore numerico, is_eligible_automatic=false.

GUIDANCE_RAISE_MATERIAL: solo se quantitative_value >= 5 (PERCENT_GUIDANCE_VS_PREV) OR >= 10 (PERCENT_GUIDANCE_VS_CONSENSUS). Senza %, is_eligible_automatic=false.

MA_TRANSFORMATIVE: solo se quantitative_value >= 5 (USD_BILLIONS) OR >= 10 (PERCENT_MARKET_CAP), OPPURE testo dichiara "transformative"/"strategic"/"game-changing" + cross-sector.

PATENT_BREAKTHROUGH: solo se titolo/sommario menziona core technology, key drug, flagship product, orphan drug exclusivity granted.

PARTNERSHIP / AI_COLLABORATION / STRATEGIC_ALLIANCE: is_eligible_automatic sempre false. Vanno in manual_review_queue. Tier-1 conta solo per priorita' nella coda, non per auto-eligibility.

NONE: se la news non e' shock event (default conservativo).

Restituisci SOLO il JSON, senza testo aggiuntivo.

Titolo: {title}
Sommario: {summary}

JSON:"""


def classify_with_gemini(title: str, summary: str = "") -> dict:
    """Classifica una news come Event Shock via Gemini 2.5 Flash.

    Ritorna dict con campi normalizzati o None se chiave assente / errore / categoria NONE.
    """
    if not GEMINI_API_KEY or not title:
        return None
    if _GEMINI_REQUEST_COUNTER["n"] >= _GEMINI_PER_REQUEST_LIMIT:
        return None
    _GEMINI_REQUEST_COUNTER["n"] += 1

    prompt = PROMPT_TEMPLATE.format(title=title, summary=(summary or "")[:300])
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 300,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    def _call_endpoint(url, timeout=5.0):
        req = urllib.request.Request(
            f"{url}?key={GEMINI_API_KEY}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    try:
        try:
            raw = _call_endpoint(GEMINI_URL)
        except urllib.error.HTTPError as he:
            if he.code == 429:
                time.sleep(1.2)
                try:
                    raw = _call_endpoint(GEMINI_URL)
                except Exception:
                    raw = _call_endpoint(GEMINI_URL_FALLBACK)
            else:
                raw = _call_endpoint(GEMINI_URL_FALLBACK)
        except Exception:
            raw = _call_endpoint(GEMINI_URL_FALLBACK)

        data = json.loads(raw)
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            return None
        parsed = json.loads(text)
        cat = (parsed.get("category") or "").upper().strip()
        if cat == "NONE" or cat not in ALL_CATEGORIES - {"NONE"}:
            return None

        # Normalizzazione campi
        qv = parsed.get("quantitative_value")
        qu = parsed.get("quantitative_unit")
        try:
            qv = float(qv) if qv is not None else None
        except (TypeError, ValueError):
            qv = None
        if qu not in ("USD_BILLIONS", "USD_MILLIONS", "PERCENT_GUIDANCE_VS_PREV",
                      "PERCENT_GUIDANCE_VS_CONSENSUS", "PERCENT_MARKET_CAP", None):
            qu = None

        return {
            "category": cat,
            "is_eligible_automatic": bool(parsed.get("is_eligible_automatic", False)),
            "quantitative_value": qv,
            "quantitative_unit": qu,
            "counterparty_tier1": bool(parsed.get("counterparty_tier1", False)),
            "source_official": bool(parsed.get("source_official", False)),
            "source": "gemini",
        }
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            err_body = ""
        print(f"[evshock-gemini] HTTPError {e.code}: {err_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[evshock-gemini] error: {e}", file=sys.stderr)
        return None


# ---------------- News fetch (riusa pattern news.py) ----------------
def fetch_finnhub_company_news(symbol: str, days: int = 7, max_items: int = 12):
    """Scarica news Finnhub per ticker USA (riusa pattern news.py).

    Ritorna lista di dict normalizzati: {title, summary, source, url, published_ts}.
    """
    if not FINNHUB_API_KEY:
        return []
    to_date = time.strftime("%Y-%m-%d", time.gmtime())
    from_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    try:
        params = urllib.parse.urlencode({
            "symbol": symbol, "from": from_date, "to": to_date,
            "token": FINNHUB_API_KEY,
        })
        url = f"{FINNHUB_BASE}/company-news?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "EventShockLayer/1.1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        if not isinstance(items, list):
            return []
        items.sort(key=lambda x: x.get("datetime", 0), reverse=True)
        out = []
        for n in items[:max_items]:
            out.append({
                "title": n.get("headline") or "",
                "summary": n.get("summary") or "",
                "source": n.get("source") or "Finnhub",
                "url": n.get("url") or "",
                "published_ts": int(n.get("datetime") or 0),
                "symbol": symbol,
            })
        return out
    except Exception:
        return []


def fetch_yahoo_news_for_symbol(symbol: str, max_items: int = 8):
    """Fallback Yahoo search per ticker EU (cover EU)."""
    try:
        params = urllib.parse.urlencode({
            "q": symbol, "lang": "en-US", "region": "US",
            "quotesCount": 0, "newsCount": max_items,
            "enableFuzzyQuery": "false",
        })
        url = f"https://query2.finance.yahoo.com/v1/finance/search?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible) EventShockLayer/1.1"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("news", []) or []
        out = []
        for n in items:
            out.append({
                "title": n.get("title") or "",
                "summary": "",  # Yahoo non fornisce summary
                "source": n.get("publisher") or "Yahoo",
                "url": n.get("link") or "",
                "published_ts": int(n.get("providerPublishTime") or 0),
                "symbol": symbol,
            })
        return out
    except Exception:
        return []


def _is_us_ticker(sym: str) -> bool:
    return "." not in sym and "-" not in sym


def fetch_news_for_event_shock(symbol: str, days: int = 7) -> list:
    """Combina Finnhub (USA) + Yahoo (EU/global)."""
    out = []
    if _is_us_ticker(symbol):
        out.extend(fetch_finnhub_company_news(symbol, days=days, max_items=12))
    out.extend(fetch_yahoo_news_for_symbol(symbol, max_items=8))
    # Dedup per URL
    seen = set()
    dedup = []
    for n in out:
        k = (n.get("url") or n.get("title") or "")[:200]
        if k and k not in seen:
            seen.add(k)
            dedup.append(n)
    return dedup


# ---------------- Volume/Gap dal provider Yahoo chart ----------------
def fetch_yahoo_chart(symbol: str, range_days: int = 35) -> dict:
    """Scarica candele giornaliere Yahoo per calcolo volume_30d_avg + dailyVol20d.

    Ritorna dict con liste: timestamps, closes, volumes. Vuoto se errore.
    """
    try:
        params = urllib.parse.urlencode({
            "interval": "1d",
            "range": f"{max(range_days, 35)}d",
            "includePrePost": "false",
        })
        url = f"{YAHOO_CHART}/{urllib.parse.quote(symbol)}?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible) EventShockLayer/1.1"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        res = data.get("chart", {}).get("result", [{}])[0]
        ts = res.get("timestamp", []) or []
        ind = res.get("indicators", {}).get("quote", [{}])[0]
        closes = ind.get("close", []) or []
        volumes = ind.get("volume", []) or []
        opens = ind.get("open", []) or []
        return {"ts": ts, "closes": closes, "volumes": volumes, "opens": opens}
    except Exception:
        return {"ts": [], "closes": [], "volumes": [], "opens": []}


def compute_volume_and_gap(symbol: str, event_ts: int) -> dict:
    """Calcola event_volume_shock_ratio + gap_move_pct + daily_vol_20d.

    event_ts: timestamp UTC dell'evento. Usiamo la barra giornaliera dell'evento
    (o successiva se evento e' overnight) come "barra-evento".
    """
    chart = fetch_yahoo_chart(symbol, range_days=35)
    ts = chart["ts"]; closes = chart["closes"]; volumes = chart["volumes"]; opens = chart["opens"]
    if len(ts) < 22:
        return {
            "event_volume_shock_ratio": None,
            "gap_move_pct": None,
            "daily_vol_20d": None,
            "gap_move_threshold": None,
            "barra_evento_index": None,
        }
    # Trova indice della prima barra >= event_ts
    idx = None
    for i, t in enumerate(ts):
        if t >= event_ts:
            idx = i
            break
    if idx is None or idx == 0:
        idx = len(ts) - 1
    # Volume medio 30d pre-evento (max 30 barre, ma con 35d range possiamo averne 20-22)
    pre_start = max(0, idx - 30)
    pre_vols = [v for v in volumes[pre_start:idx] if v]
    if len(pre_vols) < 10:
        return {
            "event_volume_shock_ratio": None,
            "gap_move_pct": None,
            "daily_vol_20d": None,
            "gap_move_threshold": None,
            "barra_evento_index": idx,
        }
    avg_vol = sum(pre_vols) / len(pre_vols)
    event_vol = volumes[idx] or 0
    vol_ratio = (event_vol / avg_vol) if avg_vol > 0 else 0.0

    # Gap move: close evento vs close giorno precedente
    prev_idx = idx - 1
    prev_close = closes[prev_idx] if prev_idx >= 0 else None
    event_close = closes[idx]
    gap_pct = None
    if prev_close and event_close:
        gap_pct = (event_close - prev_close) / prev_close * 100.0

    # dailyVol20d: stddev rendimenti giornalieri ultimi 20 trading days pre-evento
    rets = []
    for i in range(max(1, idx - 20), idx):
        c0 = closes[i - 1] if i - 1 >= 0 else None
        c1 = closes[i]
        if c0 and c1 and c0 > 0:
            rets.append((c1 - c0) / c0 * 100.0)
    if len(rets) >= 5:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        daily_vol_20d = math.sqrt(var)
    else:
        daily_vol_20d = None

    threshold = None
    if daily_vol_20d is not None:
        threshold = max(4.0, 1.5 * daily_vol_20d)

    return {
        "event_volume_shock_ratio": round(vol_ratio, 3),
        "gap_move_pct": round(gap_pct, 3) if gap_pct is not None else None,
        "daily_vol_20d": round(daily_vol_20d, 3) if daily_vol_20d is not None else None,
        "gap_move_threshold": round(threshold, 3) if threshold is not None else None,
        "barra_evento_index": idx,
    }


# ---------------- Scoring (spec 4) ----------------
def score_officiality(source: str, source_official_flag: bool) -> int:
    """0-100 in base a fonte."""
    if source_official_flag:
        return 100
    s = (source or "").lower()
    for domain in FONTI_OFFICIALI:
        if domain in s:
            return 100
    for domain in FONTI_TIER_REUTERS:
        if domain in s:
            return 75
    for domain in FONTI_TIER_MAINSTREAM:
        if domain in s:
            return 50
    return 25


def score_economic_impact(category: str, quantitative_value, quantitative_unit) -> int:
    """AnalystDerivedImpactScore 0-100 dalla magnitudine quantitativa."""
    qv = quantitative_value
    qu = quantitative_unit
    if qv is None:
        # Senza dato quantitativo: punteggio basso per categorie quantitative,
        # punteggio medio per categorie qualitative (FDA/Phase3/Patent)
        if category in ("FDA_APPROVAL", "PHASE_III_SUCCESS", "PATENT_BREAKTHROUGH"):
            return 75
        return 40
    try:
        qv = float(qv)
    except (TypeError, ValueError):
        return 40

    if category == "MEGA_CONTRACT_MATERIAL":
        if qu == "USD_BILLIONS":
            qv_m = qv * 1000.0
        elif qu == "USD_MILLIONS":
            qv_m = qv
        else:
            qv_m = qv
        # 500M -> 60; 1B -> 75; 3B -> 90; 5B+ -> 100
        if qv_m >= 5000: return 100
        if qv_m >= 3000: return 90
        if qv_m >= 1000: return 75
        if qv_m >= 500: return 60
        return 30
    if category == "GUIDANCE_RAISE_MATERIAL":
        # vs prev: 5% -> 60, 10% -> 80, 20% -> 95, 50%+ -> 100
        # vs consensus: 10% -> 60, 30% -> 85, 50%+ -> 100
        if qu == "PERCENT_GUIDANCE_VS_CONSENSUS":
            if qv >= 50: return 100
            if qv >= 30: return 85
            if qv >= 15: return 70
            if qv >= 10: return 60
            return 30
        else:
            if qv >= 50: return 100
            if qv >= 20: return 95
            if qv >= 10: return 80
            if qv >= 5: return 60
            return 30
    if category == "MA_TRANSFORMATIVE":
        if qu == "USD_BILLIONS":
            if qv >= 50: return 100
            if qv >= 20: return 90
            if qv >= 10: return 80
            if qv >= 5: return 70
            return 40
        if qu == "PERCENT_MARKET_CAP":
            if qv >= 50: return 100
            if qv >= 25: return 90
            if qv >= 10: return 75
            return 40
        return 60
    # FDA / Phase3 / Patent: qualitative, ritorno 75 fisso
    if category in ("FDA_APPROVAL", "PHASE_III_SUCCESS", "PATENT_BREAKTHROUGH"):
        return 80
    return 40


def score_volume(ratio) -> int:
    """Piecewise lineare (spec 3.3): 1x->0, 2x->50, 3x->75, 5x->100."""
    if ratio is None:
        return 0
    r = float(ratio)
    if r <= 1.0:
        return 0
    if r <= 2.0:
        return int(round((r - 1.0) * 50))
    if r <= 3.0:
        return int(round(50 + (r - 2.0) * 25))
    if r <= 5.0:
        return int(round(75 + (r - 3.0) * 12.5))
    return 100


def score_analyst_reaction(upgrades: int, downgrades: int) -> int:
    """0-100 da numero upgrades/downgrades nelle 48h post-evento."""
    if upgrades >= 3:
        return 100
    if upgrades >= 2:
        return 75
    if upgrades >= 1 or (upgrades == 0 and downgrades == 0):
        return 50
    if downgrades >= 1 and upgrades == 0:
        return 0
    return 25


def compute_event_credibility(officiality: int, eco_impact: int,
                               volume_score: int, analyst_score: int,
                               manual_score=None) -> dict:
    """Combina con pesi 0.40 / 0.30 / 0.20 / 0.10.

    Se manual_score fornito, EconomicImpactScore = max(manual, analyst_derived).
    Calcola anche manual_score_divergence_flag (spec 3.1).
    """
    eco = eco_impact
    divergence_flag = False
    if manual_score is not None:
        if manual_score > eco_impact + 30:
            divergence_flag = True
        eco = max(int(manual_score), int(eco_impact))
    score = (0.40 * officiality + 0.30 * eco + 0.20 * volume_score + 0.10 * analyst_score)
    return {
        "event_credibility_score": round(score, 2),
        "economic_impact_score": eco,
        "analyst_derived_impact_score": eco_impact,
        "manual_impact_score": manual_score,
        "manual_score_divergence_flag": divergence_flag,
    }


# ---------------- Cold Start Lock (spec 7) ----------------
def cold_start_lock_active(today_iso: str = None) -> bool:
    today_iso = today_iso or dt.datetime.utcnow().strftime("%Y-%m-%d")
    return today_iso <= COLD_START_END_DATE


# ---------------- Audit (spec 10) ----------------
AUDIT_FILE = "/tmp/event_shock_history.jsonl"  # in Vercel: only /tmp writable
OVERRIDES_FILE = "/tmp/event_shock_overrides.log"


def audit_append(record: dict):
    """Append-only audit log. In Vercel scrive /tmp (effimero, ma sufficiente per debug)."""
    try:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------- Core pipeline per singolo ticker ----------------
def process_symbol(symbol: str, days: int = 7, min_score: float = 60.0) -> list:
    """Pipeline completa per un ticker. Ritorna lista di eventi (eligible o manual).

    Step:
    1. Cache lookup chiave primaria
    2. Fetch news (Finnhub+Yahoo)
    3. Per ogni news: pre-filter keyword, cache hash chiave secondaria, Gemini classify
    4. Per eventi classificati: calcola volume/gap, scores
    5. Filtra min_score, ordina, ritorna
    """
    today_iso = dt.datetime.utcnow().strftime("%Y-%m-%d")
    cache_key = f"evshock:{symbol}:{today_iso}"
    now = time.time()
    cached = _CACHE_PRIMARY.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    news_items = fetch_news_for_event_shock(symbol, days=days)
    events = []
    for n in news_items:
        title = n.get("title") or ""
        summary = n.get("summary") or ""
        if not title:
            continue

        # Pre-filter keyword
        kw_cat = _matches_any_trigger(title, summary)
        if not kw_cat:
            continue

        # Chiave secondaria per dedup multi-ticker (spec 2.3)
        date_key = time.strftime("%Y-%m-%d", time.gmtime(n.get("published_ts") or now))
        hash_in = (title + "|" + (n.get("source") or "") + "|" + date_key).encode("utf-8")
        h_key = hashlib.sha1(hash_in).hexdigest()
        h_cached = _CACHE_HEADLINE.get(h_key)
        if h_cached and (now - h_cached[0]) < _CACHE_TTL:
            classification = h_cached[1]
        else:
            classification = classify_with_gemini(title, summary)
            if classification:
                if len(_CACHE_HEADLINE) >= _GEMINI_CACHE_MAX:
                    for k in list(_CACHE_HEADLINE.keys())[:_GEMINI_CACHE_MAX // 2]:
                        _CACHE_HEADLINE.pop(k, None)
                _CACHE_HEADLINE[h_key] = (now, classification)

        if not classification:
            continue
        cat = classification["category"]
        if cat == "NONE" or cat not in ALL_CATEGORIES - {"NONE"}:
            continue

        # Compute metriche prezzo/volume
        event_ts = n.get("published_ts") or int(now)
        metrics = compute_volume_and_gap(symbol, event_ts)

        # Scores
        officiality = score_officiality(n.get("source", ""), classification.get("source_official", False))
        eco_impact = score_economic_impact(cat, classification.get("quantitative_value"), classification.get("quantitative_unit"))
        vol_score = score_volume(metrics.get("event_volume_shock_ratio"))
        # AnalystReaction: stub a 50 (neutro) — wire-up con finance_analyst_research e' opzionale Fase 2
        analyst_score = 50
        cred = compute_event_credibility(officiality, eco_impact, vol_score, analyst_score)

        # Gate ShockCandidate (spec 4)
        passes_credibility = cred["event_credibility_score"] >= 80
        vol_ratio = metrics.get("event_volume_shock_ratio") or 0
        passes_volume = vol_ratio >= 3.0
        gap_pct = metrics.get("gap_move_pct")
        gap_threshold = metrics.get("gap_move_threshold")
        passes_gap = (gap_pct is not None and gap_threshold is not None
                      and abs(gap_pct) >= gap_threshold and gap_pct > 0)  # upside only

        # QualityShield + YieldTrap: non disponibili in questa rotta -> placeholder neutro
        quality_shield = "Unknown"
        yield_trap = False

        is_eligible_auto = (cat in ELIGIBLE_AUTOMATIC
                            and classification.get("is_eligible_automatic", False))

        shock_candidate = (passes_credibility and passes_volume and passes_gap
                           and quality_shield != "Red" and not yield_trap
                           and is_eligible_auto)

        # Cold Start Lock
        cs_active = cold_start_lock_active()

        event = {
            "symbol": symbol,
            "event_date": time.strftime("%Y-%m-%d", time.gmtime(event_ts)),
            "category": cat,
            "is_eligible_automatic": is_eligible_auto,
            "headline": title[:300],
            "summary": summary[:300],
            "source_url": n.get("url"),
            "source": n.get("source"),
            "source_official": classification.get("source_official", False),
            "officiality_score": officiality,
            "economic_impact_score": cred["economic_impact_score"],
            "analyst_derived_impact_score": cred["analyst_derived_impact_score"],
            "manual_impact_score": cred["manual_impact_score"],
            "manual_score_divergence_flag": cred["manual_score_divergence_flag"],
            "event_volume_shock_ratio": metrics.get("event_volume_shock_ratio"),
            "volume_shock_score": vol_score,
            "gap_move_pct": gap_pct,
            "gap_move_threshold": gap_threshold,
            "daily_vol_20d": metrics.get("daily_vol_20d"),
            "analyst_reaction_score": analyst_score,
            "event_credibility_score": cred["event_credibility_score"],
            "passes_credibility_gate": passes_credibility,
            "passes_volume_gate": passes_volume,
            "passes_gap_gate": passes_gap,
            "quality_shield": quality_shield,
            "yield_trap": yield_trap,
            "shock_candidate_eligible": shock_candidate,
            "fast_probation_recommended": shock_candidate and cs_active,
            "fast_probation_size_pct_nav": 1.0 if (shock_candidate and cs_active) else None,
            "cold_start_lock_active": cs_active,
            "cold_start_override_required": cs_active and shock_candidate,
            "quantitative_value": classification.get("quantitative_value"),
            "quantitative_unit": classification.get("quantitative_unit"),
            "counterparty_tier1": classification.get("counterparty_tier1", False),
            "manual_review_status": "requires_manual_review" if (cat in MANUAL_REVIEW) else None,
            "manual_review_expiry": (
                (dt.datetime.utcnow() + dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
                if cat in MANUAL_REVIEW else None
            ),
        }
        if event["event_credibility_score"] >= min_score or event.get("manual_review_status"):
            events.append(event)
            # Audit append per ogni evento che supera la soglia
            audit_append({
                "timestamp_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "symbol": symbol,
                "event_date": event["event_date"],
                "category": cat,
                "event_credibility_score": event["event_credibility_score"],
                "decisione": "auto" if shock_candidate else ("manual" if cat in MANUAL_REVIEW else "rejected"),
                "headline_truncated": title[:200],
            })

    # Ordinamento per score discendente
    events.sort(key=lambda e: e.get("event_credibility_score", 0), reverse=True)
    _CACHE_PRIMARY[cache_key] = (now, events)
    return events


# ---------------- HTTP Handler ----------------
class handler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._set_cors(); self.end_headers()

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors()
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        # Feature flag (spec 2.4)
        if not EVENT_SHOCK_ENABLED:
            self._respond(503, {"error": "feature_disabled"})
            return
        reset_gemini_counter()
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            symbols_raw = (qs.get("symbols", [""])[0] or "").strip()
            if not symbols_raw:
                self._respond(400, {"ok": False, "error": "missing symbols param"})
                return
            try:
                days = int(qs.get("days", ["7"])[0])
            except ValueError:
                days = 7
            days = max(1, min(days, 30))
            try:
                min_score = float(qs.get("min_score", ["60"])[0])
            except ValueError:
                min_score = 60.0
            symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()][:30]

            all_events = []
            manual_queue = []
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(process_symbol, s, days, min_score): s for s in symbols}
                for f in futs:
                    try:
                        for ev in f.result(timeout=25) or []:
                            if ev.get("manual_review_status"):
                                manual_queue.append(ev)
                            else:
                                all_events.append(ev)
                    except Exception as e:
                        print(f"[evshock] symbol error: {e}", file=sys.stderr)

            all_events.sort(key=lambda e: e.get("event_credibility_score", 0), reverse=True)

            self._respond(200, {
                "as_of_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "universo_query_size": len(symbols),
                "events_found": len(all_events),
                "events_manual_review": len(manual_queue),
                "events": all_events,
                "manual_review_queue": manual_queue,
                "cold_start_lock_active": cold_start_lock_active(),
                "cold_start_end_date": COLD_START_END_DATE,
                "version": "1.1",
            })
        except Exception as e:
            print(f"[evshock] handler error: {e}", file=sys.stderr)
            self._respond(500, {"ok": False, "error": str(e)[:200]})
