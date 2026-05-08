"""
/api/markets - Indici borse mondiali, futures, indicatori macro LIVE
Cache: 60 secondi (dati real-time)
Usa lo stesso flusso di /api/quotes (Yahoo v8/finance/chart) che NON richiede crumb.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, time, urllib.request

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0'

# Cache
_cache = {}
CACHE_TTL = 60

# Definizione di TUTTI i simboli da fetchare, raggruppati
MARKETS = {
    'europe': {
        '^FTSEMIB.MI': 'FTSE MIB',
        '^GDAXI': 'DAX (DE)',
        '^FCHI': 'CAC 40 (FR)',
        '^STOXX50E': 'EURO STOXX 50',
        '^IBEX': 'IBEX 35 (ES)',
        '^FTSE': 'FTSE 100 (UK)',
        '^AEX': 'AEX (NL)',
        '^SSMI': 'SMI (CH)',
    },
    'usa': {
        '^GSPC': 'S&P 500',
        '^IXIC': 'Nasdaq Composite',
        '^DJI': 'Dow Jones',
        '^RUT': 'Russell 2000',
    },
    'asia': {
        '^N225': 'Nikkei 225 (JP)',
        '^HSI': 'Hang Seng (HK)',
        '000001.SS': 'Shanghai Composite',
        '^KS11': 'KOSPI (KR)',
        '^AXJO': 'ASX 200 (AU)',
    },
    'futures_us': {
        'ES=F': 'S&P 500 Future',
        'NQ=F': 'Nasdaq 100 Future',
        'YM=F': 'Dow Jones Future',
        'RTY=F': 'Russell 2000 Future',
    },
    'currencies': {
        'EURUSD=X': 'EUR/USD',
        'EURGBP=X': 'EUR/GBP',
        'EURCHF=X': 'EUR/CHF',
        'EURJPY=X': 'EUR/JPY',
    },
    'commodities': {
        'GC=F': 'Oro (USD/oz)',
        'SI=F': 'Argento (USD/oz)',
        'CL=F': 'WTI Crude (USD/bbl)',
        'BZ=F': 'Brent (USD/bbl)',
        'NG=F': 'Gas Naturale (USD/MMBtu)',
    },
    'rates': {
        '^TNX': 'US Treasury 10y',
        '^TYX': 'US Treasury 30y',
        '^FVX': 'US Treasury 5y',
        '^IRX': 'US Treasury 13w',
    },
    'volatility': {
        '^VIX': 'VIX',
        '^VXN': 'VXN (Nasdaq vol)',
    },
}

# Tassi banche centrali (statici - aggiornati manualmente, fonte ufficiale BCE/FED)
CENTRAL_BANK_RATES = {
    'BCE_DEPOSIT': {
        'label': 'BCE Deposit Facility',
        'value': 2.25,
        'unit': '%',
        'last_change': '2026-04-17',
        'last_change_bps': -25,
        'next_meeting': '2026-06-18',
        'source': 'European Central Bank',
    },
    'FED_FUNDS': {
        'label': 'Fed Funds Rate (upper)',
        'value': 3.75,
        'unit': '%',
        'last_change': '2026-03-19',
        'last_change_bps': -25,
        'next_meeting': '2026-06-12',
        'source': 'Federal Reserve',
    },
    'BOE_BANK': {
        'label': 'BoE Bank Rate',
        'value': 4.00,
        'unit': '%',
        'last_change': '2026-02-06',
        'last_change_bps': -25,
        'next_meeting': '2026-06-19',
        'source': 'Bank of England',
    },
    'BOJ': {
        'label': 'BoJ Policy Rate',
        'value': 0.50,
        'unit': '%',
        'last_change': '2026-01-24',
        'last_change_bps': 25,
        'next_meeting': '2026-06-13',
        'source': 'Bank of Japan',
    },
}


def _fetch_quote(symbol):
    """Fetch prezzo + storico 5 giorni per sparkline. Usa v8/chart (no crumb needed)."""
    cache_key = f'q:{symbol}'
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if (now - ts) < CACHE_TTL:
            return symbol, data

    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d&includePrePost=false'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        result = d['chart']['result'][0]
        meta = result.get('meta', {})
        indicators = result.get('indicators', {}).get('quote', [{}])[0]
        closes = indicators.get('close', []) or []
        # Filtra None e prendi gli ultimi 8 close per sparkline (estesa con storico più lungo se serve)
        sparkline = [c for c in closes if c is not None][-8:]

        price = meta.get('regularMarketPrice')
        prev_close = meta.get('chartPreviousClose')
        # Per indici e futures, prev_close di Yahoo è OK (chartPreviousClose di un range 5d = giorno-1)
        # Se invece vogliamo essere super precisi, usiamo il PENULTIMO close della serie
        valid_closes = [c for c in closes if c is not None]
        if len(valid_closes) >= 2:
            prev_close = valid_closes[-2]

        var_pct = None
        if price and prev_close:
            try:
                var_pct = round((price / prev_close - 1) * 100, 2)
            except Exception:
                pass

        data = {
            'symbol': symbol,
            'price': price,
            'prev_close': prev_close,
            'variazione_pct': var_pct,
            'currency': meta.get('currency', ''),
            'exchange': meta.get('exchangeName', ''),
            'sparkline': sparkline,
            'market_state': meta.get('marketState', ''),
            'timezone': meta.get('exchangeTimezoneShortName', ''),
        }
        _cache[cache_key] = (now, data)
        return symbol, data
    except Exception as e:
        return symbol, {'symbol': symbol, 'error': str(e)[:120]}


def _fetch_all_categories():
    """Fetch parallelo di tutti i simboli, ritorna dict per categoria."""
    out = {cat: {} for cat in MARKETS.keys()}
    all_pairs = []
    for cat, syms in MARKETS.items():
        for sym, label in syms.items():
            all_pairs.append((cat, sym, label))

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_fetch_quote, sym): (cat, sym, label) for (cat, sym, label) in all_pairs}
        for fut in as_completed(futures, timeout=25):
            cat, sym, label = futures[fut]
            try:
                _, data = fut.result()
            except Exception as e:
                data = {'symbol': sym, 'error': str(e)[:120]}
            data['label'] = label
            out[cat][sym] = data

    return out


def _build_derived(out):
    """Calcola valori derivati: spread BTP-Bund, ecc."""
    # Per BTP/Bund non abbiamo il futures preciso; usiamo TNX (US 10y) come proxy se serve
    # Aggiungo un placeholder per ora — l'utente può indicare le fonti preferite
    derived = {}
    return derived


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
            cat_filter = qs.get('category', [''])[0]

            if cat_filter and cat_filter in MARKETS:
                # Solo una categoria
                syms = MARKETS[cat_filter]
                cat_data = {}
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = {pool.submit(_fetch_quote, sym): (sym, label) for (sym, label) in syms.items()}
                    for fut in as_completed(futures, timeout=20):
                        sym, label = futures[fut]
                        try:
                            _, d = fut.result()
                        except Exception as e:
                            d = {'symbol': sym, 'error': str(e)[:120]}
                        d['label'] = label
                        cat_data[sym] = d
                payload = {
                    'ok': True,
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
                    'category': cat_filter,
                    'data': cat_data,
                }
            else:
                # Tutto
                all_data = _fetch_all_categories()
                payload = {
                    'ok': True,
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
                    'data': all_data,
                    'central_bank_rates': CENTRAL_BANK_RATES,
                }

            self._send_json(200, payload)
        except Exception as e:
            self._send_json(500, {'ok': False, 'error': str(e)[:200]})

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=60')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
