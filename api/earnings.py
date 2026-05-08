"""
/api/earnings - Calendario earnings dei prossimi 14 giorni per i ticker richiesti
Usa Yahoo Finance v10 quoteSummary modulo calendarEvents (rate limit gestito con cache 1h)
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, time, urllib.request, http.cookiejar, datetime as dt

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0'

_cache = {}
_crumb_state = {'crumb': None, 'ts': 0}
CACHE_TTL = 3600  # 1h
CRUMB_TTL = 1800


def _refresh_crumb():
    now = time.time()
    if _crumb_state['crumb'] and (now - _crumb_state['ts']) < CRUMB_TTL:
        return _crumb_state['crumb']
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', UA)]
    try:
        opener.open('https://finance.yahoo.com', timeout=5)
        r = opener.open('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=5)
        crumb = r.read().decode().strip()
        if crumb and len(crumb) < 30 and '<' not in crumb:
            _crumb_state.update({'crumb': crumb, 'ts': now, 'opener': opener})
            return crumb
    except Exception:
        pass
    return None


def _fetch_calendar(ticker):
    """Fetch calendarEvents per un ticker."""
    cache_key = f'cal:{ticker}'
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if (now - ts) < CACHE_TTL:
            return ticker, data

    crumb = _refresh_crumb()
    crumb_qs = f'&crumb={quote(crumb)}' if crumb else ''
    url = (f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}'
           f'?modules=calendarEvents,price{crumb_qs}')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        # Usa cookie jar dal crumb refresh se possibile
        opener = _crumb_state.get('opener') or urllib.request.build_opener()
        if not _crumb_state.get('opener'):
            opener.addheaders = [('User-Agent', UA)]
        r = opener.open(url, timeout=8)
        d = json.loads(r.read())
        result = d.get('quoteSummary', {}).get('result')
        if not result:
            data = {'error': 'no data'}
        else:
            ce = result[0].get('calendarEvents', {}) or {}
            pr = result[0].get('price', {}) or {}
            earnings = ce.get('earnings', {}) or {}

            # earningsDate è una lista di timestamp Unix; prendiamo il primo
            edates = earnings.get('earningsDate', []) or []
            earnings_date = None
            if edates:
                first = edates[0]
                if isinstance(first, dict):
                    earnings_date = first.get('raw')
                else:
                    earnings_date = first

            ex_div = ce.get('exDividendDate', {})
            ex_div_ts = ex_div.get('raw') if isinstance(ex_div, dict) else ex_div

            div_date = ce.get('dividendDate', {})
            div_date_ts = div_date.get('raw') if isinstance(div_date, dict) else div_date

            def _raw(o, k):
                v = o.get(k, {}) if o else {}
                return v.get('raw') if isinstance(v, dict) else v

            data = {
                'name': pr.get('shortName') or pr.get('longName') or ticker,
                'earnings_date': earnings_date,
                'earnings_eps_avg': _raw(earnings, 'earningsAverage'),
                'earnings_eps_low': _raw(earnings, 'earningsLow'),
                'earnings_eps_high': _raw(earnings, 'earningsHigh'),
                'revenue_avg': _raw(earnings, 'revenueAverage'),
                'is_estimate': earnings.get('isEarningsDateEstimate'),
                'ex_dividend_date': ex_div_ts,
                'dividend_date': div_date_ts,
                'currency': pr.get('currency', ''),
            }
        _cache[cache_key] = (now, data)
        return ticker, data
    except Exception as e:
        return ticker, {'error': str(e)[:120]}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            symbols = qs.get('symbols', [''])[0]
            tickers = [t.strip() for t in symbols.split(',') if t.strip()]
            if not tickers:
                self._send_json(400, {'ok': False, 'error': 'param symbols required'})
                return
            if len(tickers) > 30:
                tickers = tickers[:30]

            data = {}
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = {pool.submit(_fetch_calendar, t): t for t in tickers}
                for fut in as_completed(futures, timeout=30):
                    tk, res = fut.result()
                    data[tk] = res

            self._send_json(200, {
                'ok': True,
                'ts': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
                'count': len(data),
                'data': data,
            })
        except Exception as e:
            self._send_json(500, {'ok': False, 'error': str(e)[:200]})

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
