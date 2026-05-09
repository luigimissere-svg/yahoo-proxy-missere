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
# Override manuali per ISIN dove l'auto-lookup sceglie un simbolo con poco storico
ISIN_OVERRIDE = {
    # Algebris Financial Credit Fund R EUR - W0B0.MU ha solo 1 punto, 0P000102IH.F ha 486 punti
    'IE00B8J38129': '0P000102IH.F',
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
    """ Yahoo v8/chart - range/interval configurabili """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_param}&interval={interval}"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


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


def fetch_nav(isin):
    """ Restituisce dict normalizzato per un singolo ISIN """
    out = {'isin': isin}
    sym = lookup_yahoo_symbol(isin)
    if not sym:
        out['error'] = 'symbol_not_found'
        return out
    out['yahoo_symbol'] = sym
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
        # Data NAV in formato YYYY-MM-DD da timestamp
        from datetime import datetime, timezone
        nav_date = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime('%Y-%m-%d')
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
