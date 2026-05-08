"""
/api/targets - Yahoo Finance analyst price targets + recommendations
Cache: 30 minuti (i target cambiano poco)
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, time, urllib.request, http.cookiejar

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36'

# Cache in-memory (per warm container)
_cache = {}            # key: (ticker) -> (ts, data)
_crumb_cache = {'crumb': None, 'ts': 0, 'opener': None}
CACHE_TTL = 1800       # 30 min
CRUMB_TTL = 3600       # 1 h


def _get_opener_with_crumb():
    """Recupera (e cacha) un opener con cookie + crumb Yahoo."""
    now = time.time()
    if _crumb_cache['crumb'] and (now - _crumb_cache['ts']) < CRUMB_TTL:
        return _crumb_cache['opener'], _crumb_cache['crumb']

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', UA), ('Accept', 'application/json,text/plain,*/*')]

    # Visit Yahoo Finance home to set cookies
    try:
        opener.open('https://finance.yahoo.com', timeout=6)
    except Exception:
        pass

    # Get crumb
    try:
        r = opener.open('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=6)
        crumb = r.read().decode().strip()
    except Exception:
        crumb = None

    _crumb_cache.update({'crumb': crumb, 'ts': now, 'opener': opener})
    return opener, crumb


def _fetch_target(ticker):
    """Fetch financialData + price for a single ticker."""
    now = time.time()
    if ticker in _cache:
        ts, data = _cache[ticker]
        if (now - ts) < CACHE_TTL:
            return ticker, data

    opener, crumb = _get_opener_with_crumb()
    crumb_qs = f'&crumb={quote(crumb)}' if crumb else ''
    url = (f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}'
           f'?modules=financialData,price,summaryDetail{crumb_qs}')
    try:
        r = opener.open(url, timeout=8)
        d = json.loads(r.read())
        result = d['quoteSummary']['result'][0]
        fd = result.get('financialData', {}) or {}
        pr = result.get('price', {}) or {}
        sd = result.get('summaryDetail', {}) or {}

        def _raw(obj, key):
            v = obj.get(key, {})
            return v.get('raw') if isinstance(v, dict) else v

        cur_price = _raw(pr, 'regularMarketPrice')
        target_mean = _raw(fd, 'targetMeanPrice')
        target_high = _raw(fd, 'targetHighPrice')
        target_low = _raw(fd, 'targetLowPrice')
        target_median = _raw(fd, 'targetMedianPrice')
        n_analysts = _raw(fd, 'numberOfAnalystOpinions')
        rec_key = fd.get('recommendationKey', '') or ''
        rec_mean = _raw(fd, 'recommendationMean')
        ccy = pr.get('currency', '') or sd.get('currency', '')

        upside = None
        if target_mean and cur_price:
            try:
                upside = round((target_mean / cur_price - 1) * 100, 2)
            except Exception:
                upside = None

        data = {
            'price': cur_price,
            'target_mean': target_mean,
            'target_median': target_median,
            'target_high': target_high,
            'target_low': target_low,
            'n_analysts': n_analysts,
            'recommendation': rec_key,        # 'buy', 'hold', 'strong_buy', 'sell', 'underperform', 'none'
            'recommendation_mean': rec_mean,  # 1.0=Strong Buy, 5.0=Sell
            'currency': ccy,
            'upside_pct': upside,
            'name': pr.get('shortName') or pr.get('longName') or ticker,
        }
        _cache[ticker] = (now, data)
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
            if len(tickers) > 50:
                tickers = tickers[:50]

            data = {}
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(_fetch_target, t): t for t in tickers}
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
        self.send_header('Cache-Control', 'public, max-age=1800')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
