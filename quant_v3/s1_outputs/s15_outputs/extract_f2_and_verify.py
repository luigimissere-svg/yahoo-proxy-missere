"""
S1.5 esec 2 - Estrazione serie F2 OOS dal rerun e verifica vincoli gap V1+V2+V3.

Target sealed v7.3 fold F2 OOS:
- ρ_AR(1) OLS = +0.1883
- T = 65 daily returns
- Q(10) Ljung-Box = 20.374

Params sealed F2: threshold=0.25, min_concordant=2, max_sector_pct=None
(target_risk_pct=0.008, max_portfolio_beta=None nel grid_smoke sono default fissi)

Vincoli (Add 12 D3-bis):
- V1: |ρ_AR(1)_rerun - 0.1883| ≤ 0.02
- V2: T ∈ [60, 70]
- V3: |Q(10)_rerun - 20.374| ≤ 10% (i.e. [18.337, 22.411])
"""
import json
import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox

EQUITY = "/home/user/workspace/yahoo-proxy-missere/quant_v3/quant_v3/s1_outputs/s15_outputs/equity_full.csv"

# Target sealed
RHO_SEALED = 0.1883
T_SEALED = 65
Q10_SEALED = 20.374

# Tolleranze
RHO_TOL = 0.02
T_RANGE = (60, 70)
Q10_TOL_PCT = 0.10

# Params sealed F2
TARGET_PARAMS = {
    "threshold": 0.25,
    "min_concordant": 2,
    "max_sector_pct": None,
}


def main():
    df = pd.read_csv(EQUITY)
    print(f"Totale righe equity: {len(df)}")
    print(f"Fold disponibili: {sorted(df['fold_id'].unique())}")
    print(f"Phase: {sorted(df['phase'].unique())}")
    print(f"Trial: {sorted(df['trial_id'].unique())}")

    # Filtra F2 OOS
    f2 = df[(df["fold_id"] == 2) & (df["phase"] == "OOS")].copy()
    print(f"\nF2 OOS rows: {len(f2)}")
    print(f"F2 OOS trial: {sorted(f2['trial_id'].unique())}")

    # Mostra params per trial
    trial_params = (
        f2.groupby("trial_id")["params_json"].first().to_dict()
    )
    print("\nParams per trial:")
    for tid, p in trial_params.items():
        print(f"  trial {tid}: {p}")

    # Trova trial con params sealed
    target_trial = None
    for tid, p_str in trial_params.items():
        p = json.loads(p_str)
        match = (
            p.get("threshold") == TARGET_PARAMS["threshold"]
            and p.get("min_concordant") == TARGET_PARAMS["min_concordant"]
            and p.get("max_sector_pct") == TARGET_PARAMS["max_sector_pct"]
        )
        if match:
            target_trial = tid
            print(f"\n>>> MATCH trial {tid} params sealed F2")
            break

    if target_trial is None:
        print("\n[ERRORE] Nessun trial corrisponde ai params sealed F2.")
        return

    series = f2[f2["trial_id"] == target_trial].copy()
    series = series.sort_values("date").reset_index(drop=True)
    print(f"\nSerie F2 OOS trial {target_trial}: {len(series)} righe")
    print(f"Date range: {series['date'].min()} → {series['date'].max()}")

    # Verifica n_nonzero
    n_nonzero = int(series["n_nonzero_returns"].iloc[0])
    n_bars = int(series["n_bars"].iloc[0])
    print(f"n_bars (metadata): {n_bars}, n_nonzero_returns (metadata): {n_nonzero}")

    returns = series["daily_return"].dropna().values.astype(float)
    print(f"Returns array len: {len(returns)}")
    nonzero = returns[returns != 0.0]
    print(f"Returns non-zero: {len(nonzero)}")

    # Per il test, usiamo TUTTI i daily returns OOS (inclusi zeri) - è la serie 65 daily portfolio
    # Ma se Bug 8 sealed usava solo i giorni di trading (non-zero), filtriamo
    # Decisione: prima provo con tutti i daily, poi anche con non-zero, e mostro entrambi.

    def ar1_ols(x):
        x = np.asarray(x, dtype=float)
        if len(x) < 3:
            return float("nan"), float("nan")
        y = x[1:]
        X = x[:-1]
        # OLS: y = a + b*X
        n = len(X)
        Xm = X.mean()
        ym = y.mean()
        cov = ((X - Xm) * (y - ym)).sum() / n
        var = ((X - Xm) ** 2).sum() / n
        b = cov / var if var > 0 else float("nan")
        # corr coefficient (Pearson) — più vicino a "ρ_AR(1)"
        rho = np.corrcoef(X, y)[0, 1]
        return rho, b

    def q10(x):
        x = np.asarray(x, dtype=float)
        if len(x) < 11:
            return float("nan"), float("nan")
        res = acorr_ljungbox(x, lags=[10], return_df=True)
        return float(res["lb_stat"].iloc[0]), float(res["lb_pvalue"].iloc[0])

    print("\n" + "=" * 70)
    print("VERIFICA SU TUTTI I DAILY RETURNS (inclusi zeri):")
    print("=" * 70)
    rho_all, b_all = ar1_ols(returns)
    q_all, p_all = q10(returns)
    print(f"T = {len(returns)}")
    print(f"ρ_AR(1) Pearson = {rho_all:+.4f} (target {RHO_SEALED:+.4f}, gap {rho_all - RHO_SEALED:+.4f})")
    print(f"β_AR(1) OLS slope = {b_all:+.4f}")
    print(f"Q(10) = {q_all:.3f} (target {Q10_SEALED:.3f}, gap {q_all - Q10_SEALED:+.3f}, p={p_all:.4f})")

    print("\n" + "=" * 70)
    print("VERIFICA SU SOLO RETURNS NON-ZERO:")
    print("=" * 70)
    rho_nz, b_nz = ar1_ols(nonzero)
    q_nz, p_nz = q10(nonzero) if len(nonzero) >= 11 else (float("nan"), float("nan"))
    print(f"T = {len(nonzero)}")
    print(f"ρ_AR(1) Pearson = {rho_nz:+.4f} (target {RHO_SEALED:+.4f}, gap {rho_nz - RHO_SEALED:+.4f})")
    print(f"β_AR(1) OLS slope = {b_nz:+.4f}")
    print(f"Q(10) = {q_nz:.3f} (target {Q10_SEALED:.3f}, gap {q_nz - Q10_SEALED:+.3f}, p={p_nz:.4f})")

    # Verdetto vincoli (uso serie "all daily")
    print("\n" + "=" * 70)
    print("VERIFICA VINCOLI ADD 12 D3-BIS (su serie all-daily):")
    print("=" * 70)
    v1_pass = abs(rho_all - RHO_SEALED) <= RHO_TOL
    v2_pass = T_RANGE[0] <= len(returns) <= T_RANGE[1]
    v3_pass = abs(q_all - Q10_SEALED) <= Q10_SEALED * Q10_TOL_PCT
    print(f"V1 (|ρ-{RHO_SEALED}| ≤ {RHO_TOL}): {rho_all:+.4f} vs {RHO_SEALED:+.4f}, |gap|={abs(rho_all-RHO_SEALED):.4f} → {'PASS' if v1_pass else 'FAIL'}")
    print(f"V2 (T ∈ [{T_RANGE[0]}, {T_RANGE[1]}]): T={len(returns)} → {'PASS' if v2_pass else 'FAIL'}")
    print(f"V3 (|Q(10)-{Q10_SEALED}| ≤ {Q10_SEALED*Q10_TOL_PCT:.3f}): Q={q_all:.3f}, |gap|={abs(q_all-Q10_SEALED):.3f} → {'PASS' if v3_pass else 'FAIL'}")
    print(f"\nVERDETTO V1+V2+V3: {'TUTTI PASS → procedi leverage analysis' if (v1_pass and v2_pass and v3_pass) else 'UNO O PIÙ FAIL → escalation S2'}")

    # Salva serie F2 OOS sealed reproduction
    out_csv = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/f2_oos_daily_returns_rerun.csv"
    series[["date", "daily_return"]].to_csv(out_csv, index=False)
    print(f"\nSerie salvata: {out_csv}")

    # Salva report JSON
    report = {
        "target_sealed": {
            "rho_AR1": RHO_SEALED,
            "T": T_SEALED,
            "Q10": Q10_SEALED,
        },
        "params_used": TARGET_PARAMS,
        "trial_id_match": int(target_trial),
        "serie_all_daily": {
            "T": int(len(returns)),
            "rho_AR1_pearson": float(rho_all),
            "beta_AR1_ols": float(b_all),
            "Q10": float(q_all),
            "Q10_pvalue": float(p_all),
            "gap_rho": float(rho_all - RHO_SEALED),
            "gap_Q10": float(q_all - Q10_SEALED),
        },
        "serie_nonzero": {
            "T": int(len(nonzero)),
            "rho_AR1_pearson": float(rho_nz),
            "beta_AR1_ols": float(b_nz),
            "Q10": float(q_nz) if not np.isnan(q_nz) else None,
            "Q10_pvalue": float(p_nz) if not np.isnan(p_nz) else None,
            "gap_rho": float(rho_nz - RHO_SEALED),
            "gap_Q10": float(q_nz - Q10_SEALED) if not np.isnan(q_nz) else None,
        },
        "vincoli_V1_V2_V3": {
            "V1_rho_tol_002": bool(v1_pass),
            "V2_T_range_60_70": bool(v2_pass),
            "V3_Q10_tol_10pct": bool(v3_pass),
            "tutti_pass": bool(v1_pass and v2_pass and v3_pass),
        },
    }
    out_json = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/f2_rerun_verifica_gap.json"
    with open(out_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report salvato: {out_json}")


if __name__ == "__main__":
    main()
