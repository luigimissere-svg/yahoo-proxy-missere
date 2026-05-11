"""
/api/funds - NAV fondi UCITS via Yahoo Finance
Mapping: ISIN -> Yahoo internal symbol (Morningstar/exchange-specific code)

I fondi UCITS non sono indicizzati direttamente sotto l'ISIN su Yahoo.
Ogni ISIN ha pero' uno o piu' simboli interni (formato '0P000...' o codici
exchange come 'W0B0.MU') trovabili tramite l'endpoint v1/finance/search.

Usage: /api/funds?isins=IE000XRSHD49,IE00B8J38129,...
Cache: 5 minuti (NAV dei fondi UCITS si aggiornano max 1 volta al giorno).
"""
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
import json, time, urllib.request, urllib.parse

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0'

# Cache 5 min (NAV cambia max 1/giorno)
_cache = {}
CACHE_TTL = 300

# Mapping noto ISIN -> Yahoo symbol (popolato dal primo lookup, persistente in memoria warm function)
# Override manuali: i 4 fondi societa' Missere sono hardcoded per evitare il v1/finance/search
# (che genera 429 su Yahoo). Cosi' lookup_yahoo_symbol() ritorna immediato.
ISIN_OVERRIDE = {
    'IE000XRSHD49': '0P0001N260.F',  # Neuberger Berman Short Duration Euro Bond - 500 punti
    'IE00B8J38129': '0P000102IH.F',  # Algebris Financial Credit - 486 punti (W0B0.MU ha solo 1 punto, evitato)
    'IE0005FE8Z02': '0P0001QL5X.F',  # Man Global Investment Grade Opportunities - 485 punti
    'LU2915465798': '0P0001UKBS.F',  # Asteria 2028 IG Corporate Bond - 308 punti
}
_isin_to_yahoo = dict(ISIN_OVERRIDE)


def lookup_yahoo_symbol(isin):
    """ Trova il simbolo Yahoo dato un ISIN tramite v1/finance/search """
    if isin in _isin_to_yahoo:
        return _isin_to_yahoo[isin]
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(isin)}&quotesCount=5"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode('utf-8'))
        quotes = data.get('quotes', [])
        if not quotes:
            _isin_to_yahoo[isin] = None
            return None
        # Preferisci ETF/MUTUALFUND in EUR
        chosen = None
        for q in quotes:
            qt = q.get('quoteType', '').upper()
            if qt in ('ETF', 'MUTUALFUND'):
                chosen = q.get('symbol')
                break
        if not chosen:
            chosen = quotes[0].get('symbol')
        _isin_to_yahoo[isin] = chosen
        return chosen
    except Exception:
        return None


def fetch_chart(symbol, range_param='10d', interval='1d'):
    """ Yahoo v8/chart - range/interval configurabili. Retry semplice contro 429. """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_param}&interval={interval}"
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err


def fetch_history(isin, range_param='2y', interval='1d'):
    """ Storico completo NAV per un ISIN. Ritorna serie [{date, nav}] """
    sym = lookup_yahoo_symbol(isin)
    if not sym:
        return {'isin': isin, 'error': 'symbol_not_found'}
    try:
        data = fetch_chart(sym, range_param, interval)
        result = data.get('chart', {}).get('result', [])
        if not result:
            return {'isin': isin, 'error': 'no_result'}
        r0 = result[0]
        meta = r0.get('meta', {})
        ts_arr = r0.get('timestamp', []) or []
        closes = r0.get('indicators', {}).get('quote', [{}])[0].get('close', []) or []
        from datetime import datetime, timezone
        series = []
        for t, c in zip(ts_arr, closes):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).strftime('%Y-%m-%d')
            series.append({'date': d, 'nav': round(c, 4)})
        return {
            'isin': isin,
            'yahoo_symbol': sym,
            'name': meta.get('shortName') or meta.get('longName') or sym,
            'currency': meta.get('currency', 'EUR'),
            'count': len(series),
            'series': series,
        }
    except urllib.error.HTTPError as e:
        return {'isin': isin, 'error': f'http_{e.code}'}
    except Exception as e:
        return {'isin': isin, 'error': str(e)[:80]}


def fetch_ft(isin):
    """Recupera NAV/data/var dal Financial Times. Fonte primaria per fondi UCITS."""
    import re
    url = f"https://markets.ft.com/data/funds/tearsheet/summary?s={isin}:EUR"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        return None
    out = {}
    m = re.search(r'mod-ui-data-list__value[^>]*>([0-9]+\.[0-9]+)<', html)
    if not m:
        return None
    out['nav'] = float(m.group(1))
    md = re.search(r'as of ([A-Z][a-z]+ [0-9]{1,2} [0-9]{4})', html)
    if md:
        from datetime import datetime
        try:
            out['nav_date'] = datetime.strptime(md.group(1), '%b %d %Y').strftime('%Y-%m-%d')
        except ValueError:
            pass
    mc = re.search(
        r'mod-format--(pos|neg)"><i[^>]*arrow-(?:upwards|downwards)[^>]*></i>\s*([\-+]?[0-9]+\.[0-9]+)\s*/\s*([\-+]?[0-9]+\.[0-9]+)%',
        html,
    )
    if mc:
        sign = -1 if mc.group(1) == 'neg' else 1
        out['change_abs'] = round(sign * abs(float(mc.group(2))), 4)
        out['change_pct'] = round(sign * abs(float(mc.group(3))), 4)
        if 'nav' in out and out['change_abs'] is not None:
            out['prev_nav'] = round(out['nav'] - out['change_abs'], 4)
    # Nome del fondo
    mn = re.search(r'<title>([^<]+)</title>', html)
    if mn:
        title = mn.group(1).strip()
        title = re.sub(r'\s*[|\-]\s*Financial Times.*$', '', title)
        out['name'] = title[:120]
    out['currency'] = 'EUR'
    out['source'] = 'ft'
    return out


def fetch_nav(isin):
    """Restituisce dict normalizzato per un singolo ISIN. Strategia: FT primario, Yahoo fallback."""
    out = {'isin': isin}

    # 1) Prova prima Financial Times (più tempestivo, no rate-limit aggressivo)
    ft_data = fetch_ft(isin)
    if ft_data and ft_data.get('nav'):
        out.update(ft_data)
        return out

    # 2) Fallback Yahoo Finance
    sym = lookup_yahoo_symbol(isin)
    if not sym:
        out['error'] = 'symbol_not_found'
        return out
    out['yahoo_symbol'] = sym
    out['source'] = 'yahoo'
    try:
        data = fetch_chart(sym)
        result = data.get('chart', {}).get('result', [])
        if not result:
            out['error'] = 'no_chart_result'
            return out
        r0 = result[0]
        meta = r0.get('meta', {})
        ts_arr = r0.get('timestamp', []) or []
        closes = r0.get('indicators', {}).get('quote', [{}])[0].get('close', []) or []
        # Filtra null
        pairs = [(t, c) for t, c in zip(ts_arr, closes) if c is not None]
        if not pairs:
            out['error'] = 'no_close_data'
            return out
        last_ts, last = pairs[-1]
        prev_ts, prev = pairs[-2] if len(pairs) >= 2 else (None, None)
        chg_pct = ((last - prev) / prev * 100) if prev else None
        chg_abs = (last - prev) if prev else None
        # Data NAV: cerca all'indietro l'ULTIMO timestamp in cui il NAV è CAMBIATO
        # (Yahoo a volte ripete il NAV precedente con timestamp odierno per fondi T+1).
        from datetime import datetime, timezone
        nav_change_ts = last_ts
        for i in range(len(pairs) - 2, -1, -1):
            ti, ci = pairs[i]
            if abs(ci - last) > 1e-6:
                nav_change_ts = pairs[i + 1][0]
                break
        nav_date = datetime.fromtimestamp(nav_change_ts, tz=timezone.utc).strftime('%Y-%m-%d')
        out.update({
            'name': meta.get('shortName') or meta.get('longName') or sym,
            'currency': meta.get('currency', 'EUR'),
            'nav': round(last, 4),
            'nav_date': nav_date,
            'prev_nav': round(prev, 4) if prev else None,
            'change_abs': round(chg_abs, 4) if chg_abs is not None else None,
            'change_pct': round(chg_pct, 4) if chg_pct is not None else None,
        })
    except urllib.error.HTTPError as e:
        out['error'] = f'http_{e.code}'
    except Exception as e:
        out['error'] = str(e)[:80]
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=300')
        self.end_headers()

        # Parse query
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            isins_raw = (params.get('isins', [''])[0] or '').strip()
            if not isins_raw:
                self.wfile.write(json.dumps({'ok': False, 'error': 'missing isins param'}).encode())
                return
            isins = [s.strip().upper() for s in isins_raw.split(',') if s.strip()]
        except Exception as e:
            self.wfile.write(json.dumps({'ok': False, 'error': f'parse_error: {e}'}).encode())
            return

        # Modo history: range param per storico singolo o multi-ISIN
        history_mode = (params.get('history', ['0'])[0] or '0').lower() in ('1', 'true', 'yes')
        range_param = params.get('range', ['2y'])[0]
        interval = params.get('interval', ['1d'])[0]

        # Cache key (include modo)
        cache_key = f"{'h' if history_mode else 'q'}:{range_param}:{interval}:{','.join(sorted(isins))}"
        now = time.time()
        cached = _cache.get(cache_key)
        ttl = 3600 if history_mode else CACHE_TTL  # cache 1h per storici
        if cached and (now - cached['ts'] < ttl):
            payload = {**cached['payload'], 'cached': True}
            self.wfile.write(json.dumps(payload).encode('utf-8'))
            return

        # Parallel fetch
        funds = {}
        if history_mode:
            def task(i):
                return fetch_history(i, range_param, interval)
            with ThreadPoolExecutor(max_workers=4) as ex:
                for r in ex.map(task, isins):
                    funds[r['isin']] = r
        else:
            with ThreadPoolExecutor(max_workers=4) as ex:
                for r in ex.map(fetch_nav, isins):
                    funds[r['isin']] = r

        payload = {
            'ok': True,
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
            'cached': False,
            'mode': 'history' if history_mode else 'quote',
            'range': range_param if history_mode else None,
            'isins_requested': len(isins),
            'isins_found': sum(1 for f in funds.values() if 'error' not in f),
            'funds': funds,
        }
        _cache[cache_key] = {'ts': now, 'payload': payload}

        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
