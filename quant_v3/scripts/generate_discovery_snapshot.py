"""
Generate Discovery Snapshot
============================

Calcola un ranking dei top-N titoli "interessanti" sull'universo allargato
(USA S&P500 + Europa STOXX600 + Italia FTSE MIB + FTSE Italia Mid Cap),
escludendo i titoli che l'utente ha già in portafoglio/watchlist.

Lo score Discovery è una versione semplificata del composite_score del
motore v2, calcolata in modo autonomo per non dipendere dal motore di
produzione (che gira separatamente ogni 2 ore sui soli titoli watchlist).

Componenti dello score Discovery:
  1. Momentum: variazione % 1 mese vs 3 mesi (trend strength)
  2. RSI: posizione tra 30-70 = neutral, < 30 = oversold (BUY), > 70 = overbought (SELL)
  3. Distanza da MA50: posizione relativa al trend di medio periodo
  4. Volume z-score: anomalia di volume rispetto media 20 giorni

Lo score finale è ordinato per "interessanza assoluta" (abs value) e poi
diviso per direzione (BUY / SELL / WATCH) e regione (US / EU / IT).

Output: quant_v3/discovery_snapshot.json con struttura:
{
  "_meta": {generated_at, universe_size, ranking_method, top_n},
  "by_region": {
    "US": {"buy": [...], "sell": [...], "watch": [...]},
    "EU": {...},
    "IT": {...}
  },
  "global_top": [...]  # top 30 assoluti
}

Si invoca:
  python quant_v3/scripts/generate_discovery_snapshot.py [--top-n 30] [--portfolio-csv path]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlreq
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]  # quant_v3/
UNIVERSE_CSV = ROOT / "data" / "meta" / "universe_extended.csv"
PORTFOLIO_CSV = ROOT / "data" / "meta" / "universe_portfolio.csv"
OUT_JSON = ROOT / "discovery_snapshot.json"

YAHOO_PROXY_BASE = "https://project-kn8ir.vercel.app/api"

REGIONS_MAP = {
    "SP500": "US",
    "NASDAQ100": "US",
    "STOXX600": "EU",
    "FTSE_MIB": "IT",
    "FTSE_ITALIA_MID_CAP": "IT",
    "PORTFOLIO_MISSERE": "PORTFOLIO",
}


def load_universe() -> list[dict[str, str]]:
    """Carica universo allargato da CSV."""
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_portfolio_tickers() -> set[str]:
    """Carica i ticker che l'utente ha già in portafoglio/watchlist."""
    if not PORTFOLIO_CSV.exists():
        return set()
    with open(PORTFOLIO_CSV, newline="", encoding="utf-8") as f:
        return {row["ticker"].strip() for row in csv.DictReader(f) if row.get("ticker")}


def region_for(idx_membership: str) -> str:
    """Mappa indice → regione US/EU/IT."""
    # Un titolo può appartenere a più indici (es. STOXX600 + FTSE_MIB)
    # Diamo priorità a IT > EU > US.
    parts = [p.strip() for p in idx_membership.split(";") if p.strip()]
    has_it = any(p in {"FTSE_MIB", "FTSE_ITALIA_MID_CAP"} for p in parts)
    if has_it:
        return "IT"
    for p in parts:
        r = REGIONS_MAP.get(p)
        if r == "EU":
            return "EU"
        if r == "US":
            return "US"
    return "EU"  # fallback


def fetch_history(symbol: str, period: str = "3mo") -> list[dict[str, Any]] | None:
    """Recupera storico via yahoo-proxy."""
    qs = urlencode({"symbol": symbol, "period": period, "interval": "1d"})
    url = f"{YAHOO_PROXY_BASE}/quotes?{qs}"
    try:
        req = urlreq.Request(url, headers={"User-Agent": "discovery-bot/1.0"})
        with urlreq.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Lo yahoo-proxy attuale non ha un endpoint storico esplicito,
        # usiamo l'endpoint history dedicato se esiste, altrimenti compute da
        # multiple quote — qui assumiamo che ci sia /api/history.
        if isinstance(data, dict) and "candles" in data:
            return data["candles"]
        return None
    except (urlerror.HTTPError, urlerror.URLError, json.JSONDecodeError, TimeoutError):
        return None


def fetch_quote_batch(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """
    Recupera quote batch via yahoo-proxy. L'endpoint /api/quotes accetta
    symbols=COMMA_LIST e ritorna {ok, data: {ticker: {price, prev_close, ...}}}.
    """
    qs = urlencode({"symbols": ",".join(symbols)})
    url = f"{YAHOO_PROXY_BASE}/quotes?{qs}"
    try:
        req = urlreq.Request(url, headers={"User-Agent": "discovery-bot/1.0"})
        with urlreq.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", {}) if data.get("ok") else {}
    except (urlerror.HTTPError, urlerror.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  ! batch error: {e}", file=sys.stderr)
        return {}


def compute_simple_score(quote: dict[str, Any]) -> dict[str, Any] | None:
    """
    Score semplificato basato SOLO sui dati disponibili nel quote endpoint:
      - variazione % 24h
      - eventuale momentum implicito

    Per la prima versione di Discovery mensile usiamo questo set ridotto.
    Future iterazioni: aggiungere RSI, MA50, volume z-score quando il
    backend espone storico.

    Score in [-1, +1]:
      - +1.0 = forte BUY (variazione +5% e oltre)
      - -1.0 = forte SELL (variazione -5% e oltre)
    """
    var_pct = quote.get("variazione_pct")
    if var_pct is None:
        return None
    # Score lineare clipped a ±1 (var_pct in %, scala 5% → 1.0)
    score = max(-1.0, min(1.0, var_pct / 5.0))
    return {
        "composite_score": round(score, 3),
        "var_pct_24h": round(var_pct, 2),
        "price": quote.get("price"),
        "currency": quote.get("currency"),
        "name_yahoo": quote.get("name"),
    }


def classify_action(score: float) -> str:
    """Mappa score → action label."""
    if score >= 0.6:
        return "🟢 STRONG BUY"
    if score >= 0.25:
        return "🟢 BUY"
    if score >= 0.1:
        return "↗ ACCUMULATE"
    if score <= -0.6:
        return "🔴 STRONG SELL"
    if score <= -0.25:
        return "🔴 REDUCE"
    if score <= -0.1:
        return "↘ MONITOR"
    return "⚪ HOLD"


def main(top_n: int = 30, batch_size: int = 50) -> int:
    print(f"[Discovery] Loading universe from {UNIVERSE_CSV}")
    universe = load_universe()
    portfolio = load_portfolio_tickers()
    print(f"  Universe: {len(universe)} titoli")
    print(f"  Portfolio (da escludere): {len(portfolio)} titoli")

    # Filtra titoli non in portafoglio
    candidates = [r for r in universe if r["ticker"] not in portfolio]
    print(f"  Candidati Discovery: {len(candidates)}")

    # Batch fetch quote (50 per volta per non saturare l'API)
    all_quotes: dict[str, dict[str, Any]] = {}
    tickers = [r["ticker"] for r in candidates]
    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i : i + batch_size]
        print(f"  Batch {i // batch_size + 1}/{(len(tickers) + batch_size - 1) // batch_size}: {len(chunk)} simboli")
        quotes = fetch_quote_batch(chunk)
        all_quotes.update(quotes)
        time.sleep(0.3)  # rate-limit polite

    print(f"  Quote ricevute: {len(all_quotes)}")

    # Compute score per ciascun candidato
    scored: list[dict[str, Any]] = []
    for row in candidates:
        ticker = row["ticker"]
        q = all_quotes.get(ticker)
        if not q:
            continue
        sc = compute_simple_score(q)
        if sc is None:
            continue
        region = region_for(row.get("index_membership", ""))
        scored.append(
            {
                "ticker": ticker,
                "name": row.get("name") or sc.get("name_yahoo") or ticker,
                "region": region,
                "market": row.get("market"),
                "currency": row.get("currency"),
                "sector": row.get("sector") or "",
                "sub_industry": row.get("sub_industry") or "",
                "headquarters": row.get("headquarters") or "",
                "index_membership": row.get("index_membership"),
                "price": sc["price"],
                "var_pct_24h": sc["var_pct_24h"],
                "composite_score": sc["composite_score"],
                "action": classify_action(sc["composite_score"]),
            }
        )

    print(f"  Scored: {len(scored)} titoli")

    # Ordina per |score| decrescente (interessanza assoluta)
    scored.sort(key=lambda x: abs(x["composite_score"]), reverse=True)
    global_top = scored[:top_n]

    # Raggruppa per regione, separando BUY (score > 0) / SELL (score < 0) / WATCH (vicino 0)
    by_region: dict[str, dict[str, list]] = {"US": {}, "EU": {}, "IT": {}}
    for region in by_region:
        region_list = [s for s in scored if s["region"] == region]
        buys = sorted([s for s in region_list if s["composite_score"] >= 0.25], key=lambda x: -x["composite_score"])[:top_n]
        sells = sorted([s for s in region_list if s["composite_score"] <= -0.25], key=lambda x: x["composite_score"])[:top_n]
        watch = sorted(
            [s for s in region_list if -0.25 < s["composite_score"] < 0.25 and abs(s["composite_score"]) >= 0.1],
            key=lambda x: -abs(x["composite_score"]),
        )[:top_n]
        by_region[region] = {"buy": buys, "sell": sells, "watch": watch}

    snapshot = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "quant_v3/scripts/generate_discovery_snapshot.py",
            "universe_size": len(universe),
            "portfolio_size": len(portfolio),
            "candidates_size": len(candidates),
            "scored_size": len(scored),
            "top_n": top_n,
            "ranking_method": "simple_var_pct_24h_v1",
            "next_revalidation_due": (
                datetime.now(timezone.utc).replace(day=1).isoformat()
            ),
        },
        "global_top": global_top,
        "by_region": by_region,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[Discovery] Snapshot scritto su {OUT_JSON}")
    print(f"  global_top: {len(global_top)}")
    print(f"  US: buy={len(by_region['US']['buy'])} sell={len(by_region['US']['sell'])} watch={len(by_region['US']['watch'])}")
    print(f"  EU: buy={len(by_region['EU']['buy'])} sell={len(by_region['EU']['sell'])} watch={len(by_region['EU']['watch'])}")
    print(f"  IT: buy={len(by_region['IT']['buy'])} sell={len(by_region['IT']['sell'])} watch={len(by_region['IT']['watch'])}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()
    sys.exit(main(top_n=args.top_n, batch_size=args.batch_size))
