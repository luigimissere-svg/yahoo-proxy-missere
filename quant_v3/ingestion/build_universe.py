"""
Universe builder per Quant Framework v3.0
==========================================

Costruisce 3 file CSV immutabili (committati nel repo):
- universe_extended.csv: ~1100 ticker (S&P500 + STOXX600 constituents al snapshot date)
- universe_portfolio.csv: 35 ticker del portafoglio Luigi Missere (portfolio + watchlist + discovery)
- benchmarks.csv: indici e factor proxy per relative strength e regime detection

Fonti:
- S&P500: Wikipedia (constituents tabella ufficiale)
- STOXX600: Wikipedia (constituents tabella ufficiale)
- Portfolio: snapshot v2.0 signals_v2_snapshot.json

Eseguire UNA VOLTA per fissare l'universe. Output committato e versionato.
"""
from __future__ import annotations
import json
import sys
import time
import io
from pathlib import Path
import pandas as pd
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")

ROOT = Path(__file__).resolve().parents[1]
META_DIR = ROOT / "data" / "meta"
META_DIR.mkdir(parents=True, exist_ok=True)

# === Snapshot date — fissato per riproducibilità ===
SNAPSHOT_DATE = "2026-05-22"


def fetch_sp500() -> pd.DataFrame:
    """Constituents S&P500 da Wikipedia (tabella stabile)."""
    print("[1/3] S&P 500 constituents…", flush=True)
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = _fetch_html(url)
    tables = pd.read_html(io.StringIO(html))
    df = tables[0]
    df = df.rename(columns={
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "GICS Sub-Industry": "sub_industry",
        "Headquarters Location": "headquarters",
    })
    df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B -> BRK-B (Yahoo)
    df["market"] = "US"
    df["currency"] = "USD"
    df["index_membership"] = "SP500"
    print(f"      → {len(df)} ticker raccolti", flush=True)
    return df[["ticker", "name", "market", "currency", "sector", "sub_industry", "headquarters", "index_membership"]]


def fetch_stoxx600() -> pd.DataFrame:
    """Constituents STOXX 600 da Wikipedia (con ticker Yahoo-compatible)."""
    print("[2/3] STOXX 600 constituents…", flush=True)
    url = "https://en.wikipedia.org/wiki/STOXX_Europe_600"
    html = _fetch_html(url)
    tables = pd.read_html(io.StringIO(html))
    # Wikipedia STOXX 600 table is usually the largest one with Ticker column
    df = None
    for t in tables:
        cols_lower = [str(c).lower() for c in t.columns]
        if any("ticker" in c for c in cols_lower) and len(t) > 100:
            df = t.copy()
            break
    if df is None:
        print("      ⚠ STOXX600 table not found, returning empty", flush=True)
        return pd.DataFrame(columns=["ticker", "name", "market", "currency", "sector", "sub_industry", "headquarters", "index_membership"])
    
    # Normalize columns
    df.columns = [str(c).strip() for c in df.columns]
    rename_map = {}
    for c in df.columns:
        cl = c.lower()
        if "ticker" in cl: rename_map[c] = "ticker"
        elif cl == "name" or "company" in cl: rename_map[c] = "name"
        elif "sector" in cl or "supersector" in cl or "ICB" in c: rename_map[c] = "sector"
        elif "country" in cl: rename_map[c] = "country"
    df = df.rename(columns=rename_map)
    
    # Ensure ticker column exists
    if "ticker" not in df.columns:
        print("      ⚠ No ticker column found in STOXX600", flush=True)
        return pd.DataFrame()
    
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["name"] = df.get("name", "").astype(str)
    df["sector"] = df.get("sector", "").astype(str)
    df["sub_industry"] = ""
    df["headquarters"] = df.get("country", "").astype(str)
    df["market"] = "EU"
    df["index_membership"] = "STOXX600"
    
    # Currency inference from ticker suffix
    def infer_currency(t: str) -> str:
        if t.endswith(".L"): return "GBP"
        if t.endswith(".MI"): return "EUR"
        if t.endswith(".DE") or t.endswith(".F"): return "EUR"
        if t.endswith(".PA"): return "EUR"
        if t.endswith(".AS"): return "EUR"
        if t.endswith(".MC"): return "EUR"
        if t.endswith(".BR"): return "EUR"
        if t.endswith(".LS"): return "EUR"
        if t.endswith(".HE"): return "EUR"
        if t.endswith(".VI"): return "EUR"
        if t.endswith(".CO"): return "DKK"
        if t.endswith(".ST"): return "SEK"
        if t.endswith(".OL"): return "NOK"
        if t.endswith(".SW") or t.endswith(".VX"): return "CHF"
        return "EUR"
    df["currency"] = df["ticker"].apply(infer_currency)
    
    print(f"      → {len(df)} ticker raccolti", flush=True)
    return df[["ticker", "name", "market", "currency", "sector", "sub_industry", "headquarters", "index_membership"]]


def build_portfolio_universe() -> pd.DataFrame:
    """I 35 ticker del portafoglio Missere — letti dallo snapshot v2.0 corrente."""
    print("[3/3] Portfolio Missere (35 ticker da snapshot v2)…", flush=True)
    snap_path = ROOT.parent / "data" / "signals_v2_snapshot.json"
    
    if not snap_path.exists():
        print(f"      ⚠ snapshot non trovato, uso fallback hardcoded", flush=True)
        # Hardcoded fallback dai ticker noti del portfolio
        tickers = [
            # Portfolio
            "NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN", "BRK-B", "JPM", "V", "MA",
            "WMT", "JNJ", "PG", "KO", "PEP", "MCD", "DIS", "ZTS", "UNH", "LLY",
            # Watchlist EU
            "PPC.AT", "EUROB.AT", "NOVO-B.CO", "ASML.AS", "MC.PA",
            # Discovery
            "TSM", "ASML", "TSLA", "AMD", "SHOP",
        ]
    else:
        with open(snap_path) as f:
            snap = json.load(f)
        tickers = sorted(set(s["ticker"] for s in snap.get("signals", []) if "ticker" in s))
    
    def market_from_ticker(t: str) -> str:
        if "." in t: return "EU"
        return "US"
    
    def currency_from_ticker(t: str) -> str:
        if not "." in t: return "USD"
        suf = "." + t.rsplit(".", 1)[-1]
        return {".L":"GBP",".MI":"EUR",".DE":"EUR",".PA":"EUR",".AS":"EUR",".MC":"EUR",
                ".BR":"EUR",".LS":"EUR",".HE":"EUR",".VI":"EUR",".CO":"DKK",".ST":"SEK",
                ".OL":"NOK",".SW":"CHF",".VX":"CHF",".AT":"EUR",".F":"EUR"}.get(suf, "EUR")
    
    df = pd.DataFrame({
        "ticker": tickers,
        "name": "",
        "market": [market_from_ticker(t) for t in tickers],
        "currency": [currency_from_ticker(t) for t in tickers],
        "sector": "",
        "sub_industry": "",
        "headquarters": "",
        "index_membership": "PORTFOLIO_MISSERE",
    })
    print(f"      → {len(df)} ticker raccolti", flush=True)
    return df


def build_benchmarks() -> pd.DataFrame:
    """Benchmarks per relative strength + regime detection."""
    return pd.DataFrame([
        # Equity benchmarks
        {"ticker": "^GSPC",     "name": "S&P 500",                  "role": "benchmark_us",       "currency": "USD"},
        {"ticker": "^NDX",      "name": "Nasdaq 100",               "role": "benchmark_us_tech",  "currency": "USD"},
        {"ticker": "^DJI",      "name": "Dow Jones Industrial",     "role": "benchmark_us_value", "currency": "USD"},
        {"ticker": "^STOXX",    "name": "STOXX Europe 600",         "role": "benchmark_eu",       "currency": "EUR"},
        {"ticker": "^STOXX50E", "name": "Euro Stoxx 50",            "role": "benchmark_eu_lcap",  "currency": "EUR"},
        {"ticker": "FTSEMIB.MI","name": "FTSE MIB",                 "role": "benchmark_it",       "currency": "EUR"},
        {"ticker": "^GDAXI",    "name": "DAX",                      "role": "benchmark_de",       "currency": "EUR"},
        {"ticker": "^FCHI",     "name": "CAC 40",                   "role": "benchmark_fr",       "currency": "EUR"},
        # Volatility / regime
        {"ticker": "^VIX",      "name": "CBOE Volatility Index",    "role": "regime_vix",         "currency": "USD"},
        {"ticker": "^V2TX",     "name": "VSTOXX (EU Vol)",          "role": "regime_vstoxx",      "currency": "EUR"},
        # Rates
        {"ticker": "^TNX",      "name": "10Y Treasury Yield",       "role": "rates_us_10y",       "currency": "USD"},
        {"ticker": "^FVX",      "name": "5Y Treasury Yield",        "role": "rates_us_5y",        "currency": "USD"},
        # Commodities (regime risk-on/off)
        {"ticker": "GC=F",      "name": "Gold Futures",             "role": "commodity_gold",     "currency": "USD"},
        {"ticker": "CL=F",      "name": "Crude Oil WTI",            "role": "commodity_oil",      "currency": "USD"},
        # FX
        {"ticker": "EURUSD=X",  "name": "EUR/USD",                  "role": "fx_eur_usd",         "currency": "USD"},
        {"ticker": "DX-Y.NYB",  "name": "US Dollar Index",          "role": "fx_dxy",             "currency": "USD"},
    ])


def main():
    print(f"\n{'='*60}\n Universe builder — Quant Framework v3.0\n Snapshot date: {SNAPSHOT_DATE}\n{'='*60}\n")
    
    # 1. Extended universe (S&P500 + STOXX600)
    try:
        sp500 = fetch_sp500()
    except Exception as e:
        print(f"      ✗ Errore S&P500: {e}", flush=True)
        sp500 = pd.DataFrame()
    time.sleep(1)
    
    try:
        stoxx = fetch_stoxx600()
    except Exception as e:
        print(f"      ✗ Errore STOXX600: {e}", flush=True)
        stoxx = pd.DataFrame()
    
    extended = pd.concat([sp500, stoxx], ignore_index=True).drop_duplicates(subset="ticker", keep="first")
    extended = extended.sort_values("ticker").reset_index(drop=True)
    extended["snapshot_date"] = SNAPSHOT_DATE
    
    ext_path = META_DIR / "universe_extended.csv"
    extended.to_csv(ext_path, index=False)
    print(f"\n✓ universe_extended.csv: {len(extended)} ticker → {ext_path}", flush=True)
    
    # 2. Portfolio universe
    portfolio = build_portfolio_universe()
    portfolio["snapshot_date"] = SNAPSHOT_DATE
    pf_path = META_DIR / "universe_portfolio.csv"
    portfolio.to_csv(pf_path, index=False)
    print(f"✓ universe_portfolio.csv: {len(portfolio)} ticker → {pf_path}", flush=True)
    
    # 3. Benchmarks
    bench = build_benchmarks()
    bench["snapshot_date"] = SNAPSHOT_DATE
    b_path = META_DIR / "benchmarks.csv"
    bench.to_csv(b_path, index=False)
    print(f"✓ benchmarks.csv: {len(bench)} ticker → {b_path}", flush=True)
    
    # 4. Summary
    print(f"\n{'='*60}\n Universe definitivo:\n  • Extended: {len(extended)} (S&P500 + STOXX600)\n  • Portfolio: {len(portfolio)} (snapshot Missere)\n  • Benchmarks: {len(bench)}\n  • TOTALE ticker da scaricare: {len(set(extended['ticker']).union(portfolio['ticker']).union(bench['ticker']))}\n{'='*60}\n")


if __name__ == "__main__":
    main()
