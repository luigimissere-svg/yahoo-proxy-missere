"""
S1.4 — Bug 7 force-close F3: test bootstrap label permutation.

Pre-registrazione: preregistration_s1_v8.md §S1.4
Sealed version: v8.s1.4

H0 (null): la differenza di Sharpe OOS tra mc=3 (stabile) e mc=2 (overfit)
           in F3 è zero in popolazione; il Delta osservato (+1.315) è
           dovuto al caso e a una specifica realizzazione di mercato.
H1 (alt): mc=2 in F3 selettore IS è overfit; mc=3 forzato globalmente
           ha return distribution sistematicamente diversa.

Test: bootstrap permutation con label shuffle.

Dati input (da journal_f3_selector_overfitting.md Test 2):
  mc=2 F3 OOS sharpe = -0.110
  mc=3 F3 OOS sharpe = +1.205
  Delta osservato = +1.315
  N trade per fold = 10 (v7.4 sealed; 10 ticker, holding ~3 mesi)

Force-close F3: l'ultimo trade del fold viene chiuso al bar finale
del window OOS (open_at_end=True nel ledger v7.4). Questo introduce
una possibile sensibilità del Sharpe al singolo punto di chiusura.

Metodologia:
  1) Simula trade-level returns per mc=2 e mc=3 in F3 OOS, ricostruiti
     da Sharpe annualizzato osservato e da assumption ragionevoli:
       - SR_d (daily) = SR_a / sqrt(252)
       - 10 trade indipendenti per fold (worst-case: indipendenza)
       - distribution shape: t-Student df=4 (heavy tail osservato in v7.4)
  2) Statistica osservata: Delta_obs = SR_mc3 - SR_mc2
  3) Bootstrap permutation N=10000:
       - concatena returns mc=2 e mc=3
       - permuta label, ricalcola SR_a per gruppo, Delta_perm
       - p_value = P(|Delta_perm| >= |Delta_obs|)
  4) Falsificazione F3 (pre-reg S1.4): p-value in [0.05, 0.20] -> inconclusivo

Caveat: senza accesso al ledger di trade originali, la simulazione usa
returns generati da Sharpe target + assunzioni distribuzionali. Il test
è quindi un PROXY del bootstrap reale. Per S2 deliverable, ri-eseguire
con ledger v7.4 ricostruito a partire dal walk-forward v8 (i fold v8
saranno diversi ma il TEST sarà metodologicamente uguale).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


SEALED_VERSION: str = "v8.s1.4"
OUT_DIR = Path("/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs")

# Dati v7.4 sealed
SR_MC2_OBS: float = -0.110
SR_MC3_OBS: float = +1.205
N_TRADES_PER_FOLD: int = 10
BAR_PER_TRADE: int = 63  # ~3 mesi trading bar (252/4)


def _simulate_trade_returns(
    sharpe_a: float,
    n_trades: int,
    bar_per_trade: int,
    df_student: float = 4.0,
    seed: int = 0,
) -> np.ndarray:
    """Simula n_trades return di trade con holding bar_per_trade bar e
    Sharpe annualizzato target sharpe_a.

    SR_a = SR_d * sqrt(252)
    SR_d = mean_d / sigma_d
    Per trade di durata bar_per_trade bar, return cumulato approx:
       r_trade ~ Normal/t( mean_d * bar_per_trade, sigma_d * sqrt(bar_per_trade) )

    Calibriamo:
      sigma_d = 0.012 (vol giornaliera tipica equity single-name)
      mean_d = SR_d * sigma_d = (SR_a / sqrt(252)) * 0.012
    """
    rng = np.random.default_rng(seed)
    sigma_d = 0.012
    sr_d = sharpe_a / math.sqrt(252)
    mean_d = sr_d * sigma_d
    mean_t = mean_d * bar_per_trade
    sigma_t = sigma_d * math.sqrt(bar_per_trade)
    # t-Student con df=4 → varianza = df/(df-2)*sigma^2 = 2*sigma^2
    # ridimensioniamo per ottenere la varianza target sigma_t^2
    scale_t = sigma_t / math.sqrt(df_student / (df_student - 2))
    raw = rng.standard_t(df_student, size=n_trades)
    return mean_t + scale_t * raw


def _sharpe_a_from_returns(r: np.ndarray, bar_per_trade: int) -> float:
    """Sharpe annualizzato da returns per-trade.
    Annualizza assumendo n_trade trade indipendenti × bar_per_trade giorni cad.
    """
    if r.std(ddof=1) == 0:
        return float("nan")
    sr_per_trade = r.mean() / r.std(ddof=1)
    # Sharpe per-trade → daily: SR_d = SR_trade / sqrt(bar_per_trade)
    # SR_a = SR_d * sqrt(252) = SR_trade * sqrt(252 / bar_per_trade)
    return sr_per_trade * math.sqrt(252.0 / bar_per_trade)


def bootstrap_permutation(
    r_mc2: np.ndarray,
    r_mc3: np.ndarray,
    n_perm: int = 10000,
    bar_per_trade: int = 63,
    seed: int = 42,
) -> dict:
    """Test bootstrap permutation della differenza di Sharpe annualizzato."""
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

    # p-value two-sided
    p_two = float(np.mean(np.abs(deltas_perm) >= abs(delta_obs)))
    p_one = float(np.mean(deltas_perm >= delta_obs))

    return {
        "sr_mc2_obs": sr_mc2_obs,
        "sr_mc3_obs": sr_mc3_obs,
        "delta_obs": delta_obs,
        "n_perm": n_perm,
        "p_value_two_sided": p_two,
        "p_value_one_sided": p_one,
        "delta_perm_quantiles": {
            "p05": float(np.quantile(deltas_perm, 0.05)),
            "p50": float(np.quantile(deltas_perm, 0.50)),
            "p95": float(np.quantile(deltas_perm, 0.95)),
            "p99": float(np.quantile(deltas_perm, 0.99)),
        },
    }


def f3_falsification(p_value: float) -> tuple[str, str]:
    """Pre-reg S1.4 F3:
      p <= 0.05 → H0 RIFIUTATO → mc=3 sistematicamente migliore in F3.
      p in [0.05, 0.20] → INCONCLUSIVO, F3 input prioritario S2.
      p > 0.20 → H0 NON rifiutato → Delta osservato compatibile con caso.
    """
    if p_value <= 0.05:
        return "REJECT_H0", (
            f"p={p_value:.4f} <= 0.05: H0 (no diff) RIFIUTATO. "
            "mc=3 OOS sistematicamente >  mc=2 in F3."
        )
    if p_value <= 0.20:
        return "INCONCLUSIVE", (
            f"p={p_value:.4f} in (0.05, 0.20]: INCONCLUSIVO. "
            "F3 ingresso prioritario in S2 (n trade insufficienti)."
        )
    return "FAIL_REJECT_H0", (
        f"p={p_value:.4f} > 0.20: H0 NON rifiutato. "
        "Delta osservato compatibile con il caso."
    )


def run_multi_seed(n_seeds: int = 20, n_perm: int = 5000) -> list[dict]:
    """Ripete il bootstrap con n_seeds simulazioni indipendenti per
    misurare la sensibilità del p-value alla simulazione."""
    results = []
    for s in range(n_seeds):
        r_mc2 = _simulate_trade_returns(
            SR_MC2_OBS, N_TRADES_PER_FOLD, BAR_PER_TRADE, seed=s
        )
        r_mc3 = _simulate_trade_returns(
            SR_MC3_OBS, N_TRADES_PER_FOLD, BAR_PER_TRADE, seed=s + 1000
        )
        # ricalibra realized sharpe alla simulazione
        boot = bootstrap_permutation(r_mc2, r_mc3, n_perm=n_perm, seed=s + 99)
        results.append({"seed": s, **boot})
    return results


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("S1.4 Backward Test — Bootstrap permutation F3 (Bug 7)")
    lines.append(f"Sealed version: {SEALED_VERSION}")
    lines.append(f"H0: SR(mc=3, F3 OOS) = SR(mc=2, F3 OOS)")
    lines.append(f"Target SR_obs: mc=2 = {SR_MC2_OBS:+.3f}, mc=3 = {SR_MC3_OBS:+.3f}, Delta = {SR_MC3_OBS-SR_MC2_OBS:+.3f}")
    lines.append(f"N trade per fold (sealed v7.4): {N_TRADES_PER_FOLD}")
    lines.append("")

    # Multi-seed sensitivity
    multi = run_multi_seed(n_seeds=20, n_perm=5000)
    p_two_vals = [m["p_value_two_sided"] for m in multi]
    p_one_vals = [m["p_value_one_sided"] for m in multi]
    delta_vals = [m["delta_obs"] for m in multi]

    p_two_med = float(np.median(p_two_vals))
    p_two_p25 = float(np.quantile(p_two_vals, 0.25))
    p_two_p75 = float(np.quantile(p_two_vals, 0.75))
    delta_med = float(np.median(delta_vals))

    lines.append(f"Multi-seed analysis (n_seeds=20, n_perm=5000 cad):")
    lines.append(f"  Delta_obs (simulated) median: {delta_med:+.3f}")
    lines.append(f"  p_value_two_sided: median={p_two_med:.4f}, IQR=[{p_two_p25:.4f}, {p_two_p75:.4f}]")
    lines.append(f"  p_value_one_sided: median={float(np.median(p_one_vals)):.4f}")
    lines.append("")

    verdict, motiv = f3_falsification(p_two_med)
    lines.append(f"Falsificazione F3 pre-reg S1.4:")
    lines.append(f"  verdetto = {verdict}")
    lines.append(f"  {motiv}")
    lines.append("")
    lines.append("Caveat: simulazione proxy del bootstrap reale (no ledger v7.4 individuale).")
    lines.append("Validazione completa rinviata a S2 con dati v8 reali.")

    report = "\n".join(lines)
    print(report)

    out_txt = OUT_DIR / "s1_4_force_close_f3_bootstrap_report.txt"
    out_txt.write_text(report + "\n")

    results_json = {
        "sealed_version": SEALED_VERSION,
        "sr_mc2_target": SR_MC2_OBS,
        "sr_mc3_target": SR_MC3_OBS,
        "delta_target": SR_MC3_OBS - SR_MC2_OBS,
        "n_trades_per_fold": N_TRADES_PER_FOLD,
        "bar_per_trade": BAR_PER_TRADE,
        "n_seeds": 20,
        "n_perm_per_seed": 5000,
        "p_value_two_sided_median": p_two_med,
        "p_value_two_sided_iqr": [p_two_p25, p_two_p75],
        "p_value_one_sided_median": float(np.median(p_one_vals)),
        "delta_obs_median": delta_med,
        "verdict": verdict,
        "motivation": motiv,
        "per_seed": multi,
    }
    out_json = OUT_DIR / "s1_4_force_close_f3_bootstrap_results.json"
    out_json.write_text(json.dumps(results_json, indent=2))

    h1 = hashlib.sha256(out_txt.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out_json.read_bytes()).hexdigest()
    (out_txt.parent / "s1_4_force_close_f3_bootstrap_report.txt.sha256").write_text(h1 + "\n")
    (out_json.parent / "s1_4_force_close_f3_bootstrap_results.json.sha256").write_text(h2 + "\n")

    print(f"\nSealed: report sha256={h1[:16]}..., results sha256={h2[:16]}...")


if __name__ == "__main__":
    main()
