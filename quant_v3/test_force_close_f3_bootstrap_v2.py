"""
S1.4-v2 — Reopen Bug 7 force-close F3 con metodo robusto.

Pre-registrazione: preregistration_s1_v8.md §S1.4
                   addendum 04 (v1) + addendum 06 (v2 questo)
Sealed version: v8.s1.4-v2

Modifiche rispetto a v1:
  - n_seeds: 20 -> 100
  - sensitivity df: df ∈ {3, 4, 5, 6} invece di df=4 fisso
  - IC bootstrap p-value via percentili (p2.5, p97.5)
  - matrice risultati (df, seed) -> p-value, delta_obs

Validazione metodologica (committente Luigi Missere, 24/05/2026):
  - df=4 a priori difendibile (Cont 2001, Tsay 2010)
  - sensitivity df mostra robustezza cross-df invece di calibrazione
    fragile da 10 trade
  - 100 seed riducono IC del p_value median di sqrt(5) ≈ 2.24x

Output:
  - s1_4_force_close_f3_bootstrap_results_v2.json (matrice + IC)
  - s1_4_force_close_f3_bootstrap_report_v2.txt
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


SEALED_VERSION: str = "v8.s1.4-v2"
OUT_DIR = Path("/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs")

SR_MC2_OBS: float = -0.110
SR_MC3_OBS: float = +1.205
N_TRADES_PER_FOLD: int = 10
BAR_PER_TRADE: int = 63

DF_GRID = [3, 4, 5, 6]
N_SEEDS = 100
N_PERM = 5000


def _simulate_trade_returns(
    sharpe_a: float,
    n_trades: int,
    bar_per_trade: int,
    df_student: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sigma_d = 0.012
    sr_d = sharpe_a / math.sqrt(252)
    mean_d = sr_d * sigma_d
    mean_t = mean_d * bar_per_trade
    sigma_t = sigma_d * math.sqrt(bar_per_trade)
    # rescale t-Student to match sigma_t (variance = df/(df-2))
    var_ratio = df_student / (df_student - 2.0)
    scale_t = sigma_t / math.sqrt(var_ratio)
    raw = rng.standard_t(df_student, size=n_trades)
    return mean_t + scale_t * raw


def _sharpe_a_from_returns(r: np.ndarray, bar_per_trade: int) -> float:
    s = r.std(ddof=1)
    if s == 0:
        return float("nan")
    sr_per_trade = r.mean() / s
    return sr_per_trade * math.sqrt(252.0 / bar_per_trade)


def bootstrap_permutation(
    r_mc2: np.ndarray,
    r_mc3: np.ndarray,
    n_perm: int,
    bar_per_trade: int,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    n_mc2 = len(r_mc2)
    n_mc3 = len(r_mc3)
    pooled = np.concatenate([r_mc2, r_mc3])

    sr_mc2_obs = _sharpe_a_from_returns(r_mc2, bar_per_trade)
    sr_mc3_obs = _sharpe_a_from_returns(r_mc3, bar_per_trade)
    delta_obs = sr_mc3_obs - sr_mc2_obs

    deltas_perm = np.empty(n_perm, dtype=float)
    for i in range(n_perm):
        idx = rng.permutation(len(pooled))
        a = pooled[idx[:n_mc2]]
        b = pooled[idx[n_mc2 : n_mc2 + n_mc3]]
        sr_a = _sharpe_a_from_returns(a, bar_per_trade)
        sr_b = _sharpe_a_from_returns(b, bar_per_trade)
        deltas_perm[i] = sr_b - sr_a

    p_two = float(np.mean(np.abs(deltas_perm) >= abs(delta_obs)))
    p_one = float(np.mean(deltas_perm >= delta_obs))

    return {
        "sr_mc2_obs": sr_mc2_obs,
        "sr_mc3_obs": sr_mc3_obs,
        "delta_obs": delta_obs,
        "p_value_two_sided": p_two,
        "p_value_one_sided": p_one,
    }


def f3_falsification(p_value: float) -> tuple[str, str]:
    if p_value <= 0.05:
        return "REJECT_H0", f"p={p_value:.4f} <= 0.05: H0 RIFIUTATO"
    if p_value <= 0.20:
        return "INCONCLUSIVE", f"p={p_value:.4f} in (0.05, 0.20]: INCONCLUSIVO"
    return "FAIL_REJECT_H0", f"p={p_value:.4f} > 0.20: H0 NON rifiutato"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    matrix: dict[int, list[dict]] = {}
    for df in DF_GRID:
        runs = []
        for s in range(N_SEEDS):
            r_mc2 = _simulate_trade_returns(
                SR_MC2_OBS, N_TRADES_PER_FOLD, BAR_PER_TRADE, df, seed=s
            )
            r_mc3 = _simulate_trade_returns(
                SR_MC3_OBS, N_TRADES_PER_FOLD, BAR_PER_TRADE, df, seed=s + 10_000
            )
            boot = bootstrap_permutation(
                r_mc2, r_mc3, n_perm=N_PERM, bar_per_trade=BAR_PER_TRADE, seed=s + 99
            )
            boot["seed"] = s
            boot["df"] = df
            runs.append(boot)
        matrix[df] = runs

    # Aggregazione per df
    summary_by_df = {}
    for df, runs in matrix.items():
        p_two_arr = np.array([r["p_value_two_sided"] for r in runs])
        p_one_arr = np.array([r["p_value_one_sided"] for r in runs])
        delta_arr = np.array([r["delta_obs"] for r in runs])
        summary_by_df[df] = {
            "p_two_median": float(np.median(p_two_arr)),
            "p_two_mean": float(np.mean(p_two_arr)),
            "p_two_iqr": [
                float(np.quantile(p_two_arr, 0.25)),
                float(np.quantile(p_two_arr, 0.75)),
            ],
            "p_two_ci95": [
                float(np.quantile(p_two_arr, 0.025)),
                float(np.quantile(p_two_arr, 0.975)),
            ],
            "p_two_pct_below_005": float(np.mean(p_two_arr <= 0.05)),
            "p_two_pct_in_inconclusive": float(
                np.mean((p_two_arr > 0.05) & (p_two_arr <= 0.20))
            ),
            "p_two_pct_above_020": float(np.mean(p_two_arr > 0.20)),
            "p_one_median": float(np.median(p_one_arr)),
            "delta_obs_median": float(np.median(delta_arr)),
        }

    # Verdict per ciascun df
    verdicts = {df: f3_falsification(s["p_two_median"]) for df, s in summary_by_df.items()}

    # Aggregato cross-df: prendi median over all 4×100 = 400 runs
    all_p_two = np.array(
        [r["p_value_two_sided"] for runs in matrix.values() for r in runs]
    )
    all_delta = np.array([r["delta_obs"] for runs in matrix.values() for r in runs])
    cross_df_median_p = float(np.median(all_p_two))
    cross_df_ci95 = [
        float(np.quantile(all_p_two, 0.025)),
        float(np.quantile(all_p_two, 0.975)),
    ]
    cross_df_verdict, cross_df_motiv = f3_falsification(cross_df_median_p)

    # --- Report ---
    lines: list[str] = []
    lines.append("S1.4-v2 Reopen — Bootstrap permutation F3 (Bug 7)")
    lines.append(f"Sealed version: {SEALED_VERSION}")
    lines.append(f"n_seeds={N_SEEDS}, n_perm={N_PERM}, df grid={DF_GRID}")
    lines.append(f"SR target: mc=2 = {SR_MC2_OBS}, mc=3 = {SR_MC3_OBS}, Delta = {SR_MC3_OBS-SR_MC2_OBS:+.3f}")
    lines.append("")
    lines.append("Sensitivity per df:")
    lines.append(
        f"  {'df':<4} {'p_med':>8} {'p_mean':>8} {'IC95_low':>10} {'IC95_high':>10} {'%≤0.05':>8} {'%incon':>8} {'verdict':>14}"
    )
    for df in DF_GRID:
        s = summary_by_df[df]
        v, _ = verdicts[df]
        lines.append(
            f"  {df:<4} {s['p_two_median']:>8.4f} {s['p_two_mean']:>8.4f} "
            f"{s['p_two_ci95'][0]:>10.4f} {s['p_two_ci95'][1]:>10.4f} "
            f"{s['p_two_pct_below_005']*100:>7.1f}% {s['p_two_pct_in_inconclusive']*100:>7.1f}% "
            f"{v:>14}"
        )
    lines.append("")
    lines.append(f"Cross-df aggregate (400 runs):")
    lines.append(f"  p_value two-sided median: {cross_df_median_p:.4f}")
    lines.append(f"  IC95: [{cross_df_ci95[0]:.4f}, {cross_df_ci95[1]:.4f}]")
    lines.append(f"  verdict cross-df: {cross_df_verdict}")
    lines.append(f"  motivazione: {cross_df_motiv}")
    lines.append("")
    lines.append("Falsificazione F3 (pre-reg S1.4):")
    if cross_df_verdict == "REJECT_H0":
        lines.append(
            "  Verdetto cross-df: REJECT_H0. Mitigazione strutturale Bug 7 supportata "
            "statisticamente (proxy)."
        )
    else:
        lines.append(f"  Verdetto cross-df: {cross_df_verdict}. Vedi motivazione sopra.")
    lines.append("")
    lines.append("Caveat: test proxy. Validazione definitiva su ledger v8 reale rinviata a S2.")

    report = "\n".join(lines)
    print(report)

    out_txt = OUT_DIR / "s1_4_force_close_f3_bootstrap_report_v2.txt"
    out_txt.write_text(report + "\n")

    results_json = {
        "sealed_version": SEALED_VERSION,
        "config": {
            "n_seeds": N_SEEDS,
            "n_perm": N_PERM,
            "df_grid": DF_GRID,
            "n_trades_per_fold": N_TRADES_PER_FOLD,
            "bar_per_trade": BAR_PER_TRADE,
            "sigma_d_assumption": 0.012,
            "sr_mc2_target": SR_MC2_OBS,
            "sr_mc3_target": SR_MC3_OBS,
        },
        "summary_by_df": summary_by_df,
        "verdict_by_df": {df: v[0] for df, v in verdicts.items()},
        "cross_df": {
            "p_two_median": cross_df_median_p,
            "p_two_ci95": cross_df_ci95,
            "delta_obs_median": float(np.median(all_delta)),
            "verdict": cross_df_verdict,
            "motivation": cross_df_motiv,
        },
    }
    out_json = OUT_DIR / "s1_4_force_close_f3_bootstrap_results_v2.json"
    out_json.write_text(json.dumps(results_json, indent=2))

    h1 = hashlib.sha256(out_txt.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out_json.read_bytes()).hexdigest()
    (out_txt.parent / "s1_4_force_close_f3_bootstrap_report_v2.txt.sha256").write_text(h1 + "\n")
    (out_json.parent / "s1_4_force_close_f3_bootstrap_results_v2.json.sha256").write_text(h2 + "\n")

    print(f"\nSealed: report sha256={h1[:16]}..., results sha256={h2[:16]}...")


if __name__ == "__main__":
    main()
