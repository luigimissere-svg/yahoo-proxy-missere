"""
S2 sensitivity selettore — Bug 8 robustness check.

Direttiva committente 24/05 06:30:
  Quattro selettori alternativi su trial F2 OOS rerun v8 (grid smoke 8 combo):
    A) max-Sharpe       (selettore corrente v8)
    B) max-DSR          (più conservativo, penalizza tail risk)
    C) min-|ρ_AR(1)|    (selezione esplicita per i.i.d.)
    D) max-Sharpe con vincolo |ρ_AR(1)| < 0.10 (Sharpe-feasible su iid set)

  Output: tabella selettore × best_param × Sharpe × ρ × PnL.
  Vincolo critico aggiuntivo: IC bootstrap (B=10000) sulla differenza Sharpe
  tra mc=2 (trial 5) e mc=3 (trial 7) sui 65 daily F2 OOS.
  Se IC contiene zero → preferenza mc=2 statisticamente non significativa.

Output:
  /home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/sensitivity_selector_results.md
  /home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/sensitivity_selector_results.json
"""
import json
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

EQUITY = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/equity_full.csv"
OUT_MD = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/sensitivity_selector_results.md"
OUT_JSON = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/sensitivity_selector_results.json"

SEED = 20260524
B_BOOT = 10000


def ar1_rho(x):
    """Formula sealed task7a v7.3."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0


def sharpe_annual(r, ppy=252):
    r = np.asarray(r, dtype=float)
    m = r.mean()
    s = r.std(ddof=1)
    if s <= 0:
        return 0.0
    return (m / s) * np.sqrt(ppy)


def sharpe_daily(r):
    r = np.asarray(r, dtype=float)
    m = r.mean()
    s = r.std(ddof=1)
    return m / s if s > 0 else 0.0


def dsr_bailey(r, N_eff=1.2231, T_override=None):
    """
    Deflated Sharpe Ratio Bailey-LdP (formula chiusa).
    Usa skew/kurt (Joanes-Gill) campionari, SR_0 da formula sqrt(2 ln N_eff)/sqrt(252).
    """
    r = np.asarray(r, dtype=float)
    T = len(r) if T_override is None else T_override
    if T < 4:
        return float("nan")
    SR_hat_d = sharpe_daily(r)
    # Joanes-Gill G1, G2
    n = len(r)
    mu = r.mean()
    d = r - mu
    m2 = (d**2).mean()
    if m2 <= 0:
        return float("nan")
    m3 = (d**3).mean()
    m4 = (d**4).mean()
    g1 = m3 / m2**1.5
    g2 = m4 / m2**2 - 3.0
    G1 = (np.sqrt(n*(n-1)) / (n-2)) * g1
    G2 = ((n-1) / ((n-2)*(n-3))) * ((n+1)*g2 + 6)
    # SR_0 daily
    SR_0_d = np.sqrt(2.0 * np.log(N_eff)) / np.sqrt(252)
    num = (SR_hat_d - SR_0_d) * np.sqrt(T - 1)
    den_var = 1.0 - G1 * SR_hat_d + (G2 / 4.0) * SR_hat_d**2
    if den_var <= 0:
        return float("nan")
    z = num / np.sqrt(den_var)
    return float(norm.cdf(z))


def pnl_pct_from_returns(r):
    """Cumulato compounded -1."""
    r = np.asarray(r, dtype=float)
    return float((1 + r).prod() - 1.0) * 100


def main():
    print("=" * 80)
    print("S2 — Sensitivity selettore Bug 8 robustness check")
    print(f"Seed bootstrap = {SEED}, B = {B_BOOT}")
    print("=" * 80)

    df = pd.read_csv(EQUITY)
    f2 = df[(df["fold_id"] == 2) & (df["phase"] == "OOS")].copy()

    # Raccogli stats per trial
    rows = []
    series_map = {}
    for tid in sorted(f2["trial_id"].unique()):
        sub = f2[f2["trial_id"] == tid].sort_values("date")
        r = sub["daily_return"].values.astype(float)
        params = json.loads(sub["params_json"].iloc[0])
        rho = ar1_rho(r)
        sh_a = sharpe_annual(r)
        ds = dsr_bailey(r, N_eff=1.2231)
        pnl = pnl_pct_from_returns(r)
        rows.append({
            "trial_id": int(tid),
            "threshold": params["threshold"],
            "min_concordant": params["min_concordant"],
            "max_sector_pct": params["max_sector_pct"],
            "T": int(len(r)),
            "mean_d": float(r.mean()),
            "std_d": float(r.std(ddof=1)),
            "sharpe_a": float(sh_a),
            "rho_AR1": float(rho),
            "abs_rho": float(abs(rho)),
            "DSR": float(ds),
            "PnL_pct": float(pnl),
        })
        series_map[int(tid)] = r

    stats_df = pd.DataFrame(rows)
    print("\nTABELLA STATS PER TRIAL F2 OOS:")
    print(stats_df.to_string(index=False))

    # --- Quattro selettori ---
    print("\n" + "=" * 80)
    print("SELETTORI ALTERNATIVI")
    print("=" * 80)

    selectors = {}

    # A) max-Sharpe
    best_A = stats_df.loc[stats_df["sharpe_a"].idxmax()].copy()
    selectors["A_max_sharpe"] = best_A

    # B) max-DSR
    best_B = stats_df.loc[stats_df["DSR"].idxmax()].copy()
    selectors["B_max_DSR"] = best_B

    # C) min-|ρ_AR(1)|
    best_C = stats_df.loc[stats_df["abs_rho"].idxmin()].copy()
    selectors["C_min_abs_rho"] = best_C

    # D) max-Sharpe con vincolo |ρ| < 0.10
    feasible = stats_df[stats_df["abs_rho"] < 0.10]
    if len(feasible) > 0:
        best_D = feasible.loc[feasible["sharpe_a"].idxmax()].copy()
    else:
        best_D = None
    selectors["D_max_sharpe_constr_rho"] = best_D

    for name, row in selectors.items():
        if row is None:
            print(f"\n{name}: NESSUN TRIAL FEASIBLE (vincolo |ρ| < 0.10 violato da tutti)")
        else:
            print(f"\n{name}:")
            print(f"  trial {int(row['trial_id'])}: mc={int(row['min_concordant'])}, thr={row['threshold']}, msp={row['max_sector_pct']}")
            print(f"  Sharpe_a={row['sharpe_a']:+.4f}, ρ={row['rho_AR1']:+.4f}, DSR={row['DSR']:.4f}, PnL={row['PnL_pct']:+.2f}%")

    # --- Bootstrap IC Δ Sharpe trial 5 (mc=2) vs trial 7 (mc=3) ---
    print("\n" + "=" * 80)
    print(f"IC BOOTSTRAP Δ Sharpe trial 5 (mc=2) vs trial 7 (mc=3), B={B_BOOT}")
    print("=" * 80)
    r5 = series_map[5]
    r7 = series_map[7]
    sh5 = sharpe_annual(r5)
    sh7 = sharpe_annual(r7)
    diff_obs = sh5 - sh7
    print(f"\nSharpe_a trial 5 (mc=2) = {sh5:+.4f}")
    print(f"Sharpe_a trial 7 (mc=3) = {sh7:+.4f}")
    print(f"Δ osservato (5 - 7)     = {diff_obs:+.4f}")

    # Bootstrap appaiato (paired): stessa permutazione di indici T=65 estratti con
    # replacement, calcola Sharpe su entrambe le serie. Conserva dipendenza temporale
    # solo parzialmente (i.i.d. bootstrap classico). Successivo: block bootstrap L=5.
    rng = np.random.default_rng(SEED)
    T = len(r5)
    assert len(r7) == T
    diffs_iid = np.empty(B_BOOT)
    for b in range(B_BOOT):
        idx = rng.integers(0, T, size=T)
        diffs_iid[b] = sharpe_annual(r5[idx]) - sharpe_annual(r7[idx])
    ci_iid = (float(np.percentile(diffs_iid, 2.5)), float(np.percentile(diffs_iid, 97.5)))
    contains_zero_iid = ci_iid[0] <= 0.0 <= ci_iid[1]
    pval_iid_two = 2 * min(np.mean(diffs_iid >= 0), np.mean(diffs_iid <= 0))

    # Block bootstrap L=5 (Politis-Romano moving block circolare)
    L = 5
    n_blocks = int(np.ceil(T / L))
    r5_ext = np.concatenate([r5, r5[:L]])
    r7_ext = np.concatenate([r7, r7[:L]])
    diffs_blk = np.empty(B_BOOT)
    rng2 = np.random.default_rng(SEED + 1)
    for b in range(B_BOOT):
        starts = rng2.integers(0, T, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + L) for s in starts])[:T] % T
        diffs_blk[b] = sharpe_annual(r5_ext[idx]) - sharpe_annual(r7_ext[idx])
    ci_blk = (float(np.percentile(diffs_blk, 2.5)), float(np.percentile(diffs_blk, 97.5)))
    contains_zero_blk = ci_blk[0] <= 0.0 <= ci_blk[1]
    pval_blk_two = 2 * min(np.mean(diffs_blk >= 0), np.mean(diffs_blk <= 0))

    print(f"\nBootstrap i.i.d. B={B_BOOT}:")
    print(f"  Δ media boot         = {diffs_iid.mean():+.4f}")
    print(f"  Δ std boot           = {diffs_iid.std(ddof=1):+.4f}")
    print(f"  IC 95% [Δ_2.5, Δ_97.5] = [{ci_iid[0]:+.4f}, {ci_iid[1]:+.4f}]")
    print(f"  Contiene zero        = {contains_zero_iid}")
    print(f"  p-value bilatero     = {pval_iid_two:.4f}")

    print(f"\nBlock bootstrap L=5 B={B_BOOT}:")
    print(f"  Δ media boot         = {diffs_blk.mean():+.4f}")
    print(f"  Δ std boot           = {diffs_blk.std(ddof=1):+.4f}")
    print(f"  IC 95% [Δ_2.5, Δ_97.5] = [{ci_blk[0]:+.4f}, {ci_blk[1]:+.4f}]")
    print(f"  Contiene zero        = {contains_zero_blk}")
    print(f"  p-value bilatero     = {pval_blk_two:.4f}")

    # Verdetto
    print("\n" + "=" * 80)
    print("VERDETTO ROBUSTEZZA SELETTORE")
    print("=" * 80)
    winners = set()
    for name, row in selectors.items():
        if row is not None:
            winners.add((int(row["min_concordant"]), row["threshold"]))
    print(f"Best_param distinti emersi dai 4 selettori: {sorted(winners)}")
    if len(winners) == 1:
        print("→ SELEZIONE ROBUSTA: tutti i selettori convergono sullo stesso best_param")
    else:
        print("→ SELEZIONE FRAGILE: selettori divergono — best_param dipende dal criterio")

    if contains_zero_iid and contains_zero_blk:
        print("\nIC 95% Δ Sharpe (mc=2 - mc=3) contiene zero in entrambi i bootstrap:")
        print("→ La preferenza mc=2 vs mc=3 NON è statisticamente significativa (95%).")
        print("→ Conferma fragilità della selezione max-Sharpe: 0.03 di Δ entro noise.")
    else:
        print("\nIC 95% Δ Sharpe NON contiene zero:")
        print("→ La preferenza mc=2 vs mc=3 è statisticamente significativa (95%).")

    # Salva risultati
    out = {
        "seed": SEED,
        "B_bootstrap": B_BOOT,
        "trial_stats": stats_df.to_dict(orient="records"),
        "selectors": {
            name: (row.to_dict() if row is not None else None) for name, row in selectors.items()
        },
        "delta_sharpe_test": {
            "trial_5_mc2_sharpe_a": float(sh5),
            "trial_7_mc3_sharpe_a": float(sh7),
            "diff_observed": float(diff_obs),
            "iid_bootstrap": {
                "ci_95": list(ci_iid),
                "contains_zero": bool(contains_zero_iid),
                "pvalue_two_sided": float(pval_iid_two),
                "boot_mean": float(diffs_iid.mean()),
                "boot_std": float(diffs_iid.std(ddof=1)),
            },
            "block_bootstrap_L5": {
                "ci_95": list(ci_blk),
                "contains_zero": bool(contains_zero_blk),
                "pvalue_two_sided": float(pval_blk_two),
                "boot_mean": float(diffs_blk.mean()),
                "boot_std": float(diffs_blk.std(ddof=1)),
            },
        },
        "winners_distinct": len(winners),
        "winners_set": [list(w) for w in sorted(winners)],
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nJSON salvato: {OUT_JSON}")

    # Salva markdown report
    md = []
    md.append("# Sensitivity selettore Bug 8 — Robustness check S2\n")
    md.append(f"**Data:** 2026-05-24 06:35 CEST")
    md.append(f"**Seed bootstrap:** {SEED}")
    md.append(f"**B bootstrap:** {B_BOOT}")
    md.append(f"**Serie analizzata:** F2 OOS, T=65, 8 trial grid smoke v8 rerun (commit 63d9be3)\n")
    md.append("## Tabella stats per trial\n")
    md.append("| Trial | mc | thr | msp | Sharpe_a | ρ_AR(1) | \\|ρ\\| | DSR | PnL % |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in stats_df.itertuples():
        md.append(f"| {r.trial_id} | {r.min_concordant} | {r.threshold} | {r.max_sector_pct} | "
                  f"{r.sharpe_a:+.4f} | {r.rho_AR1:+.4f} | {r.abs_rho:.4f} | {r.DSR:.4f} | {r.PnL_pct:+.2f} |")
    md.append("\n## Esito 4 selettori\n")
    md.append("| Selettore | Trial | mc | thr | Sharpe_a | ρ_AR(1) | DSR | PnL % |")
    md.append("|---|---|---|---|---|---|---|---|")
    for name, row in selectors.items():
        if row is None:
            md.append(f"| {name} | — | — | — | — | — | — | NESSUN FEASIBLE |")
        else:
            md.append(f"| {name} | {int(row['trial_id'])} | {int(row['min_concordant'])} | "
                      f"{row['threshold']} | {row['sharpe_a']:+.4f} | {row['rho_AR1']:+.4f} | "
                      f"{row['DSR']:.4f} | {row['PnL_pct']:+.2f} |")
    md.append(f"\n**Best_param distinti emersi:** {sorted(winners)}")
    if len(winners) == 1:
        md.append("→ **SELEZIONE ROBUSTA**: tutti i selettori convergono.")
    else:
        md.append("→ **SELEZIONE FRAGILE**: selettori divergono.")
    md.append("\n## IC bootstrap Δ Sharpe trial 5 (mc=2) − trial 7 (mc=3)\n")
    md.append(f"- Sharpe_a trial 5 (mc=2): **{sh5:+.4f}**")
    md.append(f"- Sharpe_a trial 7 (mc=3): **{sh7:+.4f}**")
    md.append(f"- Δ osservato: **{diff_obs:+.4f}**\n")
    md.append("### Bootstrap i.i.d.\n")
    md.append(f"- IC 95%: **[{ci_iid[0]:+.4f}, {ci_iid[1]:+.4f}]**")
    md.append(f"- Contiene zero: **{contains_zero_iid}**")
    md.append(f"- p-value bilatero: **{pval_iid_two:.4f}**\n")
    md.append("### Block bootstrap L=5 (Politis-Romano)\n")
    md.append(f"- IC 95%: **[{ci_blk[0]:+.4f}, {ci_blk[1]:+.4f}]**")
    md.append(f"- Contiene zero: **{contains_zero_blk}**")
    md.append(f"- p-value bilatero: **{pval_blk_two:.4f}**\n")
    md.append("## Verdetto\n")
    if contains_zero_iid and contains_zero_blk:
        md.append("L'IC 95% Δ Sharpe (mc=2 − mc=3) **contiene zero** in entrambi i bootstrap.")
        md.append("La preferenza mc=2 vs mc=3 **NON è statisticamente significativa** al 95%.")
        md.append("Conferma la fragilità della selezione max-Sharpe (Δ = 0.03 entro noise).\n")
    else:
        md.append("L'IC 95% Δ Sharpe **NON contiene zero**.")
        md.append("La preferenza mc=2 vs mc=3 **è statisticamente significativa** al 95%.\n")
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))
    print(f"MD salvato: {OUT_MD}")


if __name__ == "__main__":
    main()
