"""S1.5 — Ricostruzione serie 65 daily returns OOS portfolio F2 + leverage hat-matrix per isolamento Bug 8.

Pre-reg: Add 11 sealed 2026-05-24 05:45 CEST.
Vincoli: append-only, no modifica retroattiva, no prompt-engineering verdetto.
"""

import json
import hashlib
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/home/user/workspace/yahoo-proxy-missere/quant_v3")
LEDGER = Path("/home/user/workspace/f2_oos_trade_ledger.csv")
OUT_DIR = ROOT / "s1_outputs" / "s15_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_ledger() -> pd.DataFrame:
    df = pd.read_csv(LEDGER)
    print(f"[OK] Ledger F2 OOS caricato: {len(df)} trade")
    return df


def load_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Carica OHLCV daily per un ticker, finestra inclusive."""
    fpath = ROOT / "data" / "ohlcv" / f"{ticker}.parquet"
    if not fpath.exists():
        raise FileNotFoundError(f"OHLCV mancante per {ticker}: {fpath}")
    df = pd.read_parquet(fpath)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    else:
        df.index = pd.to_datetime(df.index)
    df = df[(df.index >= start) & (df.index <= end)].copy()
    return df


def reconstruct_f2_daily_returns(ledger: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Ricostruisce daily portfolio return F2 OOS dal ledger + OHLCV.

    Convenzione: tutti i trade aperti il 2025-11-01 al prezzo close 31/10 o open 2025-11-01,
    mark-to-market daily, equal-weight implicito su notional (notional_open / sum_notional).
    """
    oos_start = "2025-11-01"
    oos_end = "2026-02-01"

    # Carica prezzi per ciascun ticker
    tickers = ledger["ticker"].tolist()
    price_panel = {}
    for tk in tickers:
        df = load_ohlcv(tk, oos_start, oos_end)
        if "Close" in df.columns:
            price_panel[tk] = df["Close"]
        elif "close" in df.columns:
            price_panel[tk] = df["close"]
        else:
            raise ValueError(f"Colonna Close/close mancante per {tk}: cols={df.columns.tolist()}")
        print(f"[OK] {tk}: {len(df)} bar OOS (range {df.index.min().date()} → {df.index.max().date()})")

    # Union dei date index (alcuni ticker possono avere date diverse — IT vs US holidays)
    all_dates = sorted(set().union(*[set(s.index) for s in price_panel.values()]))
    date_index = pd.DatetimeIndex(all_dates)
    print(f"[OK] Date index unione: {len(date_index)} giorni unici da {date_index[0].date()} a {date_index[-1].date()}")

    # Reindex tutti i ticker su union, ffill per holiday cross-market
    aligned = pd.DataFrame({tk: s.reindex(date_index).ffill() for tk, s in price_panel.items()})

    # Daily returns per ticker
    rets = aligned.pct_change().fillna(0.0)

    # Pesi notional (equal-weight implicito su 10 trade, dal ledger)
    notionals = {row["ticker"]: row["notional_open"] for _, row in ledger.iterrows()}
    total_notional = sum(notionals.values())
    weights = {tk: notionals[tk] / total_notional for tk in tickers}
    print(f"[OK] Pesi notional (somma={sum(weights.values()):.6f}):")
    for tk, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"     {tk:12s} w={w:.4f}  notional={notionals[tk]:.2f}")

    # Portfolio daily return = sum_i w_i × r_i,t
    port_ret = pd.Series(0.0, index=rets.index)
    contrib = pd.DataFrame(0.0, index=rets.index, columns=tickers)
    for tk in tickers:
        contrib[tk] = weights[tk] * rets[tk]
        port_ret += contrib[tk]

    # Filtro: serie OOS 2025-11-01 → 2026-02-01, escludo il primo giorno (NaN/0 da pct_change initial)
    mask = (port_ret.index >= oos_start) & (port_ret.index <= oos_end)
    port_ret = port_ret[mask]
    contrib = contrib[mask]

    # Filtro nonzero returns (skip giorni con tutti i prezzi ffilled / weekend)
    nonzero_mask = port_ret.abs() > 1e-10
    port_ret_nz = port_ret[nonzero_mask]
    contrib_nz = contrib[nonzero_mask]

    print(f"\n[OK] Serie ricostruita F2 OOS:")
    print(f"     Totale bar OOS: {len(port_ret)}")
    print(f"     Nonzero bar:    {len(port_ret_nz)}")
    print(f"     Mean daily:     {port_ret_nz.mean():.6f}")
    print(f"     Std daily:      {port_ret_nz.std():.6f}")
    print(f"     Cum return:     {(1 + port_ret_nz).prod() - 1:.4f}")

    # Output dataframe completo (date, ret_port, contrib per ticker)
    out_df = pd.DataFrame({"date": port_ret_nz.index, "ret_port": port_ret_nz.values})
    for tk in tickers:
        out_df[f"contrib_{tk}"] = contrib_nz[tk].values

    return out_df, port_ret_nz.values


def estimate_ar1(r: np.ndarray) -> dict:
    """Stima ρ_AR(1), Q(10) Ljung-Box, p-value."""
    from scipy import stats
    # OLS: r_t = α + ρ · r_{t-1} + ε_t
    y = r[1:]
    x = r[:-1]
    X = np.column_stack([np.ones_like(x), x])
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    alpha, rho = beta
    resid = y - X @ beta
    n = len(y)
    p = 2
    mse = (resid ** 2).sum() / (n - p)
    # h_tt diagonal
    H = X @ np.linalg.inv(X.T @ X) @ X.T
    h_tt = np.diag(H)

    # Ljung-Box Q(10) on full series r
    def ljung_box(x, lags=10):
        n_full = len(x)
        x_dem = x - x.mean()
        # autocorrelations
        acf = np.zeros(lags + 1)
        c0 = (x_dem ** 2).sum() / n_full
        for k in range(lags + 1):
            ck = (x_dem[k:] * x_dem[:n_full - k]).sum() / n_full
            acf[k] = ck / c0
        Q = n_full * (n_full + 2) * sum(acf[k] ** 2 / (n_full - k) for k in range(1, lags + 1))
        pval = 1 - stats.chi2.cdf(Q, df=lags)
        return Q, pval, acf

    Q, pval, acf = ljung_box(r, lags=10)
    return {
        "rho": float(rho),
        "alpha": float(alpha),
        "Q10": float(Q),
        "pval": float(pval),
        "acf_lag1": float(acf[1]),
        "n_obs": int(n),
        "mse": float(mse),
        "h_tt": h_tt.tolist(),
        "resid": resid.tolist(),
    }


def leverage_delta_rho(r_full: np.ndarray, contrib_df: pd.DataFrame, tickers: list) -> dict:
    """Calcola Δρ_i = ρ_full − ρ_{esclusione contributo trade i} per ciascun trade.

    Esclusione = sottrazione del contributo trade i da r_t per tutti t.
    Riprodotto su serie ricostruita.
    """
    full_stat = estimate_ar1(r_full)
    rho_full = full_stat["rho"]

    delta = {}
    for tk in tickers:
        r_excl = r_full - contrib_df[f"contrib_{tk}"].values
        stat = estimate_ar1(r_excl)
        delta[tk] = {
            "rho_excl": stat["rho"],
            "delta_rho": rho_full - stat["rho"],
            "Q10_excl": stat["Q10"],
            "pval_excl": stat["pval"],
        }
    return rho_full, delta


def cooks_distance(r: np.ndarray) -> np.ndarray:
    """Cook's distance per ogni osservazione AR(1)."""
    y = r[1:]
    x = r[:-1]
    X = np.column_stack([np.ones_like(x), x])
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n = len(y)
    p = 2
    mse = (resid ** 2).sum() / (n - p)
    H = X @ np.linalg.inv(X.T @ X) @ X.T
    h_tt = np.diag(H)
    D = (resid ** 2) * h_tt / (p * mse * (1 - h_tt) ** 2)
    return D


def main():
    ledger = load_ledger()
    out_df, r_full = reconstruct_f2_daily_returns(ledger)

    # Salva serie ricostruita
    daily_csv = OUT_DIR / "f2_oos_daily_returns_reconstructed.csv"
    out_df.to_csv(daily_csv, index=False)
    print(f"\n[OK] Serie salvata: {daily_csv}")
    print(f"     SHA256: {sha256_file(daily_csv)}")

    # Stima AR(1) full
    full_stat = estimate_ar1(r_full)
    print(f"\n[OK] AR(1) full ricostruito:")
    print(f"     ρ_lag1 (acf): {full_stat['acf_lag1']:.6f}")
    print(f"     ρ_OLS:        {full_stat['rho']:.6f}")
    print(f"     Q(10):        {full_stat['Q10']:.4f}")
    print(f"     p-value:      {full_stat['pval']:.4f}")
    print(f"     n_obs AR(1):  {full_stat['n_obs']}")
    print(f"     T full:       {len(r_full)}")

    # Confronto con sealed +0.1883
    sealed_rho = 0.1883
    gap = full_stat['rho'] - sealed_rho
    gap_acf = full_stat['acf_lag1'] - sealed_rho
    print(f"\n[CHECK] Gap di riproduzione:")
    print(f"     ρ_OLS - sealed: {gap:+.6f}  ({'PASS' if abs(gap) < 0.02 else 'GAP_DI_RIPRODUZIONE'})")
    print(f"     ρ_acf - sealed: {gap_acf:+.6f}  ({'PASS' if abs(gap_acf) < 0.02 else 'GAP_DI_RIPRODUZIONE'})")

    # Leverage Δρ per ciascun trade
    tickers = ledger["ticker"].tolist()
    contrib_cols = [f"contrib_{tk}" for tk in tickers]
    contrib_df = out_df[contrib_cols].copy()
    contrib_df.columns = contrib_cols  # keep
    rho_full, delta = leverage_delta_rho(r_full, out_df, tickers)

    print(f"\n[OK] Leverage Δρ per trade (ranking discendente |Δρ|):")
    ranked = sorted(delta.items(), key=lambda x: -abs(x[1]["delta_rho"]))
    for i, (tk, d) in enumerate(ranked, 1):
        print(f"  {i:2d}. {tk:12s} ρ_excl={d['rho_excl']:+.6f}  Δρ={d['delta_rho']:+.6f}  Q10_excl={d['Q10_excl']:7.3f}  p={d['pval_excl']:.4f}")

    # Sensitivity curve: esclusione top-k per k=0..10
    print(f"\n[OK] Sensitivity curve ρ_AR(1) F2 vs k outlier esclusi:")
    sensitivity = []
    for k in range(0, len(tickers) + 1):
        top_k_tickers = [tk for tk, _ in ranked[:k]]
        r_excl = r_full.copy()
        for tk in top_k_tickers:
            r_excl = r_excl - out_df[f"contrib_{tk}"].values
        if k == 0:
            r_excl = r_full
        stat = estimate_ar1(r_excl)
        sensitivity.append({
            "k": k,
            "tickers_excluded": top_k_tickers,
            "rho": stat["rho"],
            "acf_lag1": stat["acf_lag1"],
            "Q10": stat["Q10"],
            "pval": stat["pval"],
        })
        print(f"  k={k:2d}  excl={top_k_tickers!s:60s}  ρ_OLS={stat['rho']:+.6f}  ρ_acf={stat['acf_lag1']:+.6f}  p={stat['pval']:.4f}")

    # Cook's distance per osservazione (sanity check)
    cd = cooks_distance(r_full)
    cd_top = np.argsort(cd)[::-1][:10]
    print(f"\n[OK] Cook's distance top-10 osservazioni:")
    for idx in cd_top:
        d = out_df.iloc[idx + 1]  # +1 perché AR(1) parte da t=1
        print(f"  obs {idx:3d}  date={d['date']}  D={cd[idx]:.6f}  ret={d['ret_port']:+.6f}")

    # Verdetto binario sealed (criterio Add 11 §4.5)
    rho_full_val = sensitivity[0]["rho"]
    rho_top3 = sensitivity[3]["rho"]
    rho_top5 = sensitivity[5]["rho"]
    print(f"\n[VERDETTO BINARIO Add 11 §4.5]")
    print(f"  ρ full:    {rho_full_val:+.6f}")
    print(f"  ρ top-3:   {rho_top3:+.6f}  (soglia ISOLATO: < +0.10)")
    print(f"  ρ top-5:   {rho_top5:+.6f}  (soglia STRUTTURALE: ≥ +0.10)")
    if rho_top3 < 0.10:
        verdict = "ISOLATO"
        verdict_msg = "Bug 8 ISOLATO via top-3 esclusione, trattabile con filtro outlier in produzione (S1.3 sufficiente)"
    elif rho_top5 >= 0.10:
        verdict = "STRUTTURALE"
        verdict_msg = "Bug 8 STRUTTURALE, redesign F2 obbligatorio (rinviato a fase S2)"
    else:
        verdict = "INTERMEDIO"
        verdict_msg = "Bug 8 PARZIALMENTE ISOLATO, esclusione top-5 minima necessaria"
    print(f"\n  VERDETTO: {verdict}")
    print(f"  {verdict_msg}")

    # Output JSON sensitivity + ranking
    sensitivity_path = OUT_DIR / "s15_sensitivity_curve.json"
    sensitivity_data = {
        "addendum_11_sealed_sha256": "81778f37904187584aad7ce96d2d51d4117fc208e991a1eeae8c2dd31bef84ba",
        "data_execution_cest": "2026-05-24 05:50 CEST",
        "rho_sealed_v73": sealed_rho,
        "rho_reconstructed_full": rho_full_val,
        "rho_reconstructed_acf": full_stat['acf_lag1'],
        "gap_OLS_vs_sealed": gap,
        "gap_acf_vs_sealed": gap_acf,
        "reproduction_status": "PASS" if abs(gap_acf) < 0.02 else "GAP_DI_RIPRODUZIONE",
        "n_obs_OOS_reconstructed": len(r_full),
        "n_obs_OOS_sealed": 65,
        "ranking_delta_rho": [
            {"rank": i, "ticker": tk, "delta_rho": d["delta_rho"], "rho_excl": d["rho_excl"], "Q10_excl": d["Q10_excl"], "pval_excl": d["pval_excl"]}
            for i, (tk, d) in enumerate(ranked, 1)
        ],
        "sensitivity_curve": sensitivity,
        "cooks_distance_top10": [
            {"obs_idx": int(idx), "date": str(out_df.iloc[idx + 1]["date"]), "D": float(cd[idx]), "ret_port": float(out_df.iloc[idx + 1]["ret_port"])}
            for idx in cd_top
        ],
        "verdict": verdict,
        "verdict_msg": verdict_msg,
    }
    with open(sensitivity_path, "w") as f:
        json.dump(sensitivity_data, f, indent=2, default=str)
    print(f"\n[OK] Sensitivity JSON: {sensitivity_path}")
    print(f"     SHA256: {sha256_file(sensitivity_path)}")

    # Ranking CSV
    ranking_csv = OUT_DIR / "s15_leverage_ranking.csv"
    ranking_df = pd.DataFrame([
        {"rank": i, "ticker": tk, "delta_rho": d["delta_rho"], "rho_excl": d["rho_excl"], "Q10_excl": d["Q10_excl"], "pval_excl": d["pval_excl"], "abs_delta_rho": abs(d["delta_rho"])}
        for i, (tk, d) in enumerate(ranked, 1)
    ])
    ranking_df.to_csv(ranking_csv, index=False)
    print(f"[OK] Ranking CSV: {ranking_csv}")
    print(f"     SHA256: {sha256_file(ranking_csv)}")

    return sensitivity_data


if __name__ == "__main__":
    main()
