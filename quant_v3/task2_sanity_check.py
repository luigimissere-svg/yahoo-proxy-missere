"""
Task 2 — Sanity check v7.3 DSR
1) SR ricalcolato dalle serie daily_return vs colonna sharpe_a salvata
2) Confronto risultati per-fold IS/OOS vs results CSV (best params)
3) Coerenza tra cum returns e PnL pct (per best params)

Tolleranza: 1e-4 sulla differenza assoluta Sharpe.
"""
import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path

WORKDIR = Path("/tmp/yahoo-proxy-missere/quant_v3")
EQUITY_CSV = WORKDIR / "wf_full_v73_equity.csv"
RESULTS_CSV = WORKDIR / "wf_full_v73.csv"
OUTPUT = WORKDIR / "task2_sanity_output.txt"

TOL = 1e-4
ANNUALIZE = np.sqrt(252)


def main():
    out = []

    def log(s=""):
        out.append(s)
        print(s)

    log("=" * 90)
    log("TASK 2 — SANITY CHECK v7.3 DSR Bailey-LdP")
    log("=" * 90)
    log()

    # Carica
    log("Caricamento equity CSV...")
    eq = pd.read_csv(EQUITY_CSV)
    log(f"  Righe totali: {len(eq):,}")
    log(f"  Colonne: {list(eq.columns)}")
    log(f"  Phase counts: {eq['phase'].value_counts().to_dict()}")
    log()

    log("Caricamento results CSV (best params per fold)...")
    res = pd.read_csv(RESULTS_CSV)
    log(f"  Folds: {res['fold_id'].tolist()}")
    log()

    # Separa righe valide (con date e daily_return) da sentinelle
    eq_valid = eq.dropna(subset=["date", "daily_return"]).copy()
    eq_sentinel = eq[eq["date"].isna() | eq["daily_return"].isna()].copy()
    log(f"  Righe valide (con returns): {len(eq_valid):,}")
    log(f"  Righe sentinella (insufficient_window): {len(eq_sentinel)}")
    if len(eq_sentinel) > 0:
        log(f"  Sentinelle distinct (trial,fold,phase): {eq_sentinel[['trial_id','fold_id','phase']].drop_duplicates().shape[0]}")
    log()

    # === BLOCCO 1: SR ricalcolato vs salvato per ogni (trial, fold, phase) ===
    log("=" * 90)
    log("BLOCCO 1 — Sharpe ricalcolato vs salvato (tol abs = 1e-4)")
    log("=" * 90)

    def recompute_sr(group):
        r = group["daily_return"].astype(float).values
        if len(r) < 2:
            return pd.Series({
                "n_bars_eq": len(r),
                "n_nonzero_eq": int((r != 0).sum()),
                "sr_recomp": np.nan,
                "sharpe_a_saved": group["sharpe_a"].iloc[0],
                "sharpe_flag": group["sharpe_flag"].iloc[0],
            })
        mu = r.mean()
        sd = r.std(ddof=1)
        if sd == 0 or np.isnan(sd):
            sr = np.nan
        else:
            sr = (mu / sd) * ANNUALIZE
        return pd.Series({
            "n_bars_eq": len(r),
            "n_nonzero_eq": int((r != 0).sum()),
            "sr_recomp": sr,
            "sharpe_a_saved": group["sharpe_a"].iloc[0],
            "sharpe_flag": group["sharpe_flag"].iloc[0],
        })

    sr_check = (
        eq_valid.groupby(["trial_id", "fold_id", "phase"], group_keys=False)
        .apply(recompute_sr)
        .reset_index()
    )
    log(f"  Trials checked: {len(sr_check)}")

    # Calcola delta
    sr_check["delta"] = (sr_check["sr_recomp"] - sr_check["sharpe_a_saved"]).abs()
    sr_check["delta"] = sr_check["delta"].fillna(np.nan)

    # Conta entro tol
    ok_mask = sr_check["delta"] <= TOL
    nan_mask = sr_check["delta"].isna()
    ko_mask = (~ok_mask) & (~nan_mask)

    log(f"  PASS (delta <= {TOL}): {ok_mask.sum()}/{len(sr_check)}")
    log(f"  NaN (sr saved o ricalcolato = NaN): {nan_mask.sum()}")
    log(f"  FAIL (delta > {TOL}): {ko_mask.sum()}")
    log()

    if ko_mask.sum() > 0:
        log("  DETTAGLIO FAIL:")
        for _, row in sr_check[ko_mask].head(20).iterrows():
            log(f"    trial={row['trial_id']:>3} fold={row['fold_id']} phase={row['phase']:>3} "
                f"saved={row['sharpe_a_saved']:.6f} recomp={row['sr_recomp']:.6f} "
                f"delta={row['delta']:.6e} flag={row['sharpe_flag']}")
        log()

    if nan_mask.sum() > 0:
        log(f"  DETTAGLIO NaN ({min(20, nan_mask.sum())} esempi):")
        for _, row in sr_check[nan_mask].head(20).iterrows():
            log(f"    trial={row['trial_id']:>3} fold={row['fold_id']} phase={row['phase']:>3} "
                f"saved={row['sharpe_a_saved']} recomp={row['sr_recomp']} "
                f"n_bars={int(row['n_bars_eq'])} n_nz={int(row['n_nonzero_eq'])} flag={row['sharpe_flag']}")
        log()

    # Distribuzione delta per phase (escluso NaN)
    log("  Delta abs per phase (escluso NaN):")
    for phase in ["IS", "OOS"]:
        d = sr_check[(sr_check["phase"] == phase) & (~sr_check["delta"].isna())]["delta"]
        if len(d) > 0:
            log(f"    {phase}: n={len(d)} max={d.max():.3e} p99={d.quantile(0.99):.3e} mean={d.mean():.3e}")
    log()

    # === BLOCCO 2: SR per-fold best params vs results CSV ===
    log("=" * 90)
    log("BLOCCO 2 — Sharpe per-fold (best params) vs results CSV")
    log("=" * 90)

    # Per ciascun fold, trova nei trial IS/OOS quello con sharpe_a vicino a quello del results
    # Il best IS è quello con max sharpe_a, OOS è valutato con i params del best IS
    # Ma il results CSV ha:
    # - is_sharpe_a = max sharpe IS sul fold
    # - oos_sharpe_a = sharpe OOS con i params best IS
    # Confronto: prendo per ogni fold il max IS sharpe ricalcolato e best params
    # NB: equity dump della fase IS contiene tutti i 72 trial, fase OOS-grid-scan contiene tutti i 72 trial OOS

    for _, fold_row in res.iterrows():
        fid = fold_row["fold_id"]
        log(f"\n  --- Fold {fid} ---")

        # IS: max sharpe ricalcolato tra i 72 trial IS
        is_trials = sr_check[(sr_check["fold_id"] == fid) & (sr_check["phase"] == "IS")]
        is_valid = is_trials.dropna(subset=["sr_recomp"])
        if len(is_valid) > 0:
            is_max = is_valid["sr_recomp"].max()
            best_is_trial = is_valid.loc[is_valid["sr_recomp"].idxmax(), "trial_id"]
            log(f"    IS  max SR ricalc = {is_max:.6f}  (trial #{best_is_trial})")
            log(f"    IS  results CSV   = {fold_row['is_sharpe_a']:.6f}")
            log(f"    IS  delta         = {abs(is_max - fold_row['is_sharpe_a']):.3e}  "
                f"{'PASS' if abs(is_max - fold_row['is_sharpe_a']) <= TOL else 'FAIL'}")

        # OOS: trial con stessi params del best IS
        oos_trials = sr_check[(sr_check["fold_id"] == fid) & (sr_check["phase"] == "OOS")]
        if len(oos_trials) > 0:
            # Per matching params, riprendo equity con params_json
            eq_fold_oos = eq_valid[(eq_valid["fold_id"] == fid) & (eq_valid["phase"] == "OOS")]
            params_target = {
                "threshold": fold_row["param_threshold"],
                "min_concordant": int(fold_row["param_min_concordant"]),
                "target_risk_pct": fold_row["param_target_risk_pct"],
                "max_sector_pct": None if pd.isna(fold_row["param_max_sector_pct"]) else fold_row["param_max_sector_pct"],
                "max_portfolio_beta": None if pd.isna(fold_row["param_max_portfolio_beta"]) else fold_row["param_max_portfolio_beta"],
            }
            log(f"    Target params best: {params_target}")
            # cerco params_json matching
            matches = []
            for trial_id, grp in eq_fold_oos.groupby("trial_id"):
                pj = json.loads(grp["params_json"].iloc[0])
                # confronto tollerante
                eq_match = (
                    abs(float(pj.get("threshold", -999)) - params_target["threshold"]) < 1e-9
                    and int(pj.get("min_concordant", -999)) == params_target["min_concordant"]
                    and abs(float(pj.get("target_risk_pct", -999)) - params_target["target_risk_pct"]) < 1e-9
                    and (pj.get("max_sector_pct") == params_target["max_sector_pct"]
                         or (pj.get("max_sector_pct") is not None and params_target["max_sector_pct"] is not None
                             and abs(float(pj["max_sector_pct"]) - params_target["max_sector_pct"]) < 1e-9))
                    and (pj.get("max_portfolio_beta") == params_target["max_portfolio_beta"]
                         or (pj.get("max_portfolio_beta") is not None and params_target["max_portfolio_beta"] is not None
                             and abs(float(pj["max_portfolio_beta"]) - params_target["max_portfolio_beta"]) < 1e-9))
                )
                if eq_match:
                    matches.append(trial_id)

            if matches:
                # prendo il primo match e ricalcolo
                trial_id = matches[0]
                grp = eq_fold_oos[eq_fold_oos["trial_id"] == trial_id]
                r = grp["daily_return"].astype(float).values
                mu, sd = r.mean(), r.std(ddof=1)
                sr_recomp = (mu / sd) * ANNUALIZE if sd > 0 else np.nan
                cum_return = (1 + r).prod() - 1  # rendimento cumulato moltiplicativo
                sum_returns = r.sum()  # somma semplice (per check additivo, equity log-like)
                log(f"    OOS trial match: #{trial_id} (matches={len(matches)})")
                log(f"    OOS SR ricalc     = {sr_recomp:.6f}")
                log(f"    OOS results CSV   = {fold_row['oos_sharpe_a']:.6f}")
                log(f"    OOS delta         = {abs(sr_recomp - fold_row['oos_sharpe_a']):.3e}  "
                    f"{'PASS' if abs(sr_recomp - fold_row['oos_sharpe_a']) <= TOL else 'FAIL'}")
                log(f"    OOS cum returns (prod) = {cum_return*100:.6f}%")
                log(f"    OOS sum returns        = {sum_returns*100:.6f}%")
                log(f"    OOS results PnL pct    = {fold_row['oos_pnl_pct']:.6f}%")
                log(f"    OOS delta PnL (prod-pnl) = {abs(cum_return*100 - fold_row['oos_pnl_pct']):.3e}")
            else:
                log(f"    OOS no match params trovato")

    log()
    log("=" * 90)
    log("SUMMARY TASK 2")
    log("=" * 90)
    log(f"  Sharpe ricalcolato OK: {ok_mask.sum()}/{len(sr_check)}")
    log(f"  Sharpe NaN: {nan_mask.sum()}")
    log(f"  Sharpe FAIL: {ko_mask.sum()}")
    if ok_mask.sum() == len(sr_check) - nan_mask.sum():
        log("  ESITO: SANITY CHECK PASSATO — tutte le serie ricostruiscono il Sharpe entro tol 1e-4")
    else:
        log("  ESITO: ATTENZIONE — alcuni mismatch sopra tol")

    # Salva il report
    with open(OUTPUT, "w") as f:
        f.write("\n".join(out))
    print(f"\nReport salvato in {OUTPUT}")

    # Salva anche un CSV diagnostico
    diag_csv = WORKDIR / "task2_sr_check.csv"
    sr_check.to_csv(diag_csv, index=False)
    print(f"CSV diagnostico salvato in {diag_csv}")


if __name__ == "__main__":
    main()
