"""
/api/markets - Indici borse mondiali, futures, indicatori macro LIVE
Sorgente primaria: Stooq (CSV gratuito, no rate limit, no auth)
Fallback: Yahoo Finance v8/chart per simboli non disponibili su Stooq
Cache: 60 secondi
"""
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, time, urllib.request, urllib.parse

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0'

_cache = {}
CACHE_TTL = 60

# Mappa simbolo "logico" -> (stooq_symbol | None, yahoo_symbol | None, label)
# stooq_symbol = None significa "salta Stooq, vai diretto su Yahoo"
SYMBOLS = {
    'europe': {
        'FTSEMIB':  ('^fmib',  '^FTSEMIB.MI', 'FTSE MIB'),
        'DAX':      ('^dax',   '^GDAXI',      'DAX (DE)'),
        'CAC40':    ('^cac',   '^FCHI',       'CAC 40 (FR)'),
        'STOXX50':  (None,     '^STOXX50E',   'EURO STOXX 50'),
        'IBEX':     ('^ibex',  '^IBEX',       'IBEX 35 (ES)'),
        'FTSE100':  ('^ftm',   '^FTSE',       'FTSE 100 (UK)'),
        'AEX':      ('^aex',   '^AEX',        'AEX (NL)'),
        'SMI':      ('^smi',   '^SSMI',       'SMI (CH)'),
    },
    'usa': {
        'SP500':    ('^spx',   '^GSPC',       'S&P 500'),
        'NASDAQ':   ('^ndq',   '^IXIC',       'Nasdaq Composite'),
        'DOW':      ('^dji',   '^DJI',        'Dow Jones'),
        'RUSSELL':  (None,     '^RUT',        'Russell 2000'),
    },
    'asia': {
        'NIKKEI':   ('^nkx',     '^N225',     'Nikkei 225 (JP)'),
        'HANGSENG': ('^hsi',     '^HSI',      'Hang Seng (HK)'),
        'SHANGHAI': ('^shc',     '000001.SS', 'Shanghai Composite'),
        'KOSPI':    ('^kospi',   '^KS11',     'KOSPI (KR)'),
        'ASX200':   (None,       '^AXJO',     'ASX 200 (AU)'),
    },
    'futures_us': {
        'ES_F': ('es.f',  'ES=F', 'S&P 500 Future'),
        'NQ_F': ('nq.f',  'NQ=F', 'Nasdaq 100 Future'),
        'YM_F': ('ym.f',  'YM=F', 'Dow Jones Future'),
        'RTY_F':(None,    'RTY=F','Russell 2000 Future'),
    },
    'currencies': {
        'EURUSD': ('eurusd', 'EURUSD=X', 'EUR/USD'),
        'EURGBP': ('eurgbp', 'EURGBP=X', 'EUR/GBP'),
        'EURCHF': ('eurchf', 'EURCHF=X', 'EUR/CHF'),
        'EURJPY': ('eurjpy', 'EURJPY=X', 'EUR/JPY'),
    },
    'commodities': {
        'GOLD':   ('gc.f', 'GC=F', 'Oro (USD/oz)'),
        'SILVER': ('si.f', 'SI=F', 'Argento (USD/oz)'),
        'WTI':    ('cl.f', 'CL=F', 'WTI Crude (USD/bbl)'),
        'BRENT':  (None,   'BZ=F', 'Brent Crude (USD/bbl)'),
        'NATGAS': ('ng.f', 'NG=F', 'Natural Gas (USD/MMBtu)'),
    },
    'rates': {
        'US10Y':  (None, '^TNX', 'US 10Y Treasury Yield'),
        'US30Y':  (None, '^TYX', 'US 30Y Treasury Yield'),
        'US5Y':   (None, '^FVX', 'US 5Y Treasury Yield'),
        'US3M':   (None, '^IRX', 'US 13W T-Bill Yield'),
    },
    'volatility': {
        'VIX':    (None, '^VIX', 'VIX (S&P 500 Vol)'),
        'VXN':    (None, '^VXN', 'VXN (Nasdaq Vol)'),
    },
}

# Tassi banche centrali (statici, aggiornare manualmente quando cambiano)
CENTRAL_BANKS = {
    'ECB': {'name': 'BCE (Eurozona)',     'rate': 2.25, 'next_meeting': '2026-06-04'},
    'FED': {'name': 'Federal Reserve',    'rate': 3.75, 'next_meeting': '2026-06-17'},
    'BOE': {'name': 'Bank of England',    'rate': 4.00, 'next_meeting': '2026-06-18'},
    'BOJ': {'name': 'Bank of Japan',      'rate': 0.50, 'next_meeting': '2026-06-19'},
}


def fetch_stooq(symbol):
    """Yahoo CSV-style endpoint: 1 simbolo per richiesta."""
    url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol)}&f=sd2t2ohlcpc&h&e=csv"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        text = r.read().decode('utf-8', errors='ignore').strip()
    lines = text.split('\n')
    if len(lines) < 2:
        return None
    parts = lines[1].split(',')
    # Symbol,Date,Time,Open,High,Low,Close,PrevClose
    if len(parts) < 8 or 'N/D' in parts[6]:
        return None
    try:
        close = float(parts[6])
        prev = float(parts[7]) if parts[7] and 'N/D' not in parts[7] else None
    except (ValueError, IndexError):
        return None
    return {
        'price': close,
        'prev_close': prev,
        'date': parts[1],
        'time': parts[2],
        'source': 'stooq',
    }


def fetch_yahoo(symbol):
    """Yahoo v8/chart - usato per simboli non coperti da Stooq."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode('utf-8'))
    result = data.get('chart', {}).get('result', [])
    if not result:
        return None
    r0 = result[0]
    meta = r0.get('meta', {})
    closes = r0.get('indicators', {}).get('quote', [{}])[0].get('close', []) or []
    closes = [c for c in closes if c is not None]
    if not closes:
        return None
    price = meta.get('regularMarketPrice') or closes[-1]
    prev = closes[-2] if len(closes) >= 2 else meta.get('chartPreviousClose')
    return {
        'price': price,
        'prev_close': prev,
        'source': 'yahoo',
    }


def fetch_one(logical_key, mapping, label):
    """Prova Stooq prima, poi Yahoo. Ritorna dict normalizzato."""
    stooq_sym, yahoo_sym, _ = mapping
    out = {'label': label}
    
    # Try Stooq
    if stooq_sym:
        try:
            r = fetch_stooq(stooq_sym)
            if r and r.get('price') is not None and r.get('prev_close') is not None:
                price, prev = r['price'], r['prev_close']
                pct = round((price - prev) / prev * 100, 2) if prev else None
                return {
                    **out,
                    'price': price,
                    'prev_close': prev,
                    'change_pct': pct,
                    'change_abs': round(price - prev, 2) if prev else None,
                    'source': 'stooq',
                }
        except Exception:
            pass
    
    # Fallback Yahoo
    if yahoo_sym:
        try:
            r = fetch_yahoo(yahoo_sym)
            if r and r.get('price') is not None:
                price, prev = r['price'], r['prev_close']
                pct = round((price - prev) / prev * 100, 2) if prev else None
                return {
                    **out,
                    'price': price,
                    'prev_close': prev,
                    'change_pct': pct,
                    'change_abs': round(price - prev, 2) if prev else None,
                    'source': 'yahoo',
                }
        except Exception as e:
            return {**out, 'error': str(e)[:80]}
    
    return {**out, 'error': 'no_data'}


def build_markets():
    """Esegue tutti i fetch in parallelo (max 8 thread)."""
    result = {}
    # Costruisci lista task: (group, key, mapping, label)
    tasks = []
    for group, symbols in SYMBOLS.items():
        result[group] = {}
        for k, mapping in symbols.items():
            label = mapping[2]
            tasks.append((group, k, mapping, label))
    
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_one, k, m, l): (g, k) for g, k, m, l in tasks}
        for fut in as_completed(futures):
            g, k = futures[fut]
            try:
                result[g][k] = fut.result()
            except Exception as e:
                result[g][k] = {'error': str(e)[:80]}
    
    result['central_banks'] = CENTRAL_BANKS
    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # CORS
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=60')
        self.end_headers()
        
        # Cache check
        now = time.time()
        cached = _cache.get('all')
        if cached and (now - cached['ts'] < CACHE_TTL):
            payload = {**cached['payload'], 'cached': True}
            self.wfile.write(json.dumps(payload).encode('utf-8'))
            return
        
        try:
            data = build_markets()
            payload = {
                'ok': True,
                'ts': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
                'cached': False,
                'data': data,
            }
            _cache['all'] = {'ts': now, 'payload': payload}
        except Exception as e:
            payload = {'ok': False, 'error': str(e)[:200]}
        
        self.wfile.write(json.dumps(payload).encode('utf-8'))
    
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
