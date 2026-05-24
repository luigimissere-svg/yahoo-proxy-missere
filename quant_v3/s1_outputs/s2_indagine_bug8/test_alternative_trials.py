"""
S2 indagine Bug 8 - Test alternative trials.

DISCOVERY chiave: v7.3 task 5 usa best_config F2 = (mc=3, thr=0.25, trial_id=61)
mentre il nostro rerun v8 ha best F2 = (mc=2, thr=0.25, trial_id=5).

Test: estraiamo dalla rerun corrente la serie F2 OOS con mc=3 (trial_id=7 nel
grid smoke v8, che è {mc=3, thr=0.25, max_sector_pct=None}) e ricalcoliamo
ρ_AR(1) con la formula sealed.

Mapping trial v8 smoke grid (8 combo):
  trial 1: thr=0.15, mc=2, msp=None
  trial 2: thr=0.15, mc=2, msp=0.3
  trial 3: thr=0.15, mc=3, msp=None
  trial 4: thr=0.15, mc=3, msp=0.3
  trial 5: thr=0.25, mc=2, msp=None  ← best v8 F2
  trial 6: thr=0.25, mc=2, msp=0.3
  trial 7: thr=0.25, mc=3, msp=None  ← MATCH params v7.3 F2 (mc=3, thr=0.25)
  trial 8: thr=0.25, mc=3, msp=0.3
"""
import numpy as np
import pandas as pd

EQUITY = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/equity_full.csv"
NPZ = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/task6_returns.npz"


def ar1_rho(x):
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0


def main():
    df = pd.read_csv(EQUITY)
    sealed = np.load(NPZ)["F2"]

    print("=" * 80)
    print("Confronto ρ_AR(1) F2 OOS per OGNI trial rerun vs sealed v7.3")
    print("=" * 80)
    f2 = df[(df["fold_id"] == 2) & (df["phase"] == "OOS")].copy()
    print(f"\n{'trial':>5} {'params':<55} {'T':>4} {'mean':>10} {'std':>10} {'ρ_AR(1)':>10}")
    print("-" * 110)
    rho_sealed = ar1_rho(sealed)
    print(f"{'SEALED':>5} {'(da task6_returns.npz F2)':<55} {len(sealed):>4d} "
          f"{sealed.mean():+10.6f} {sealed.std(ddof=1):>10.6f} {rho_sealed:+10.4f}")
    print("-" * 110)
    for tid in sorted(f2["trial_id"].unique()):
        sub = f2[f2["trial_id"] == tid].sort_values("date")
        params = sub["params_json"].iloc[0]
        r = sub["daily_return"].values.astype(float)
        rho = ar1_rho(r)
        print(f"{tid:>5d} {params:<55} {len(r):>4d} {r.mean():+10.6f} {r.std(ddof=1):>10.6f} {rho:+10.4f}")

    # In particolare trial 7 (mc=3, thr=0.25, msp=None)
    print("\n" + "=" * 80)
    print("Confronto puntuale: trial 7 (mc=3, thr=0.25, msp=None) vs sealed F2")
    print("=" * 80)
    sub7 = f2[f2["trial_id"] == 7].sort_values("date")
    r7 = sub7["daily_return"].values.astype(float)
    print(f"Rerun trial 7 F2 OOS: T={len(r7)}, mean={r7.mean():+.6f}, std={r7.std(ddof=1):.6f}, ρ={ar1_rho(r7):+.4f}")
    print(f"Sealed F2: T={len(sealed)}, mean={sealed.mean():+.6f}, std={sealed.std(ddof=1):.6f}, ρ={rho_sealed:+.4f}")
    if len(r7) == len(sealed):
        corr = np.corrcoef(r7, sealed)[0, 1]
        ratio = sealed.std(ddof=1) / r7.std(ddof=1) if r7.std(ddof=1) > 0 else float("nan")
        print(f"Pearson trial-7-vs-sealed: {corr:+.4f}")
        print(f"std ratio sealed/rerun-7: {ratio:.4f}")

    # Anche analisi cross-trial: trovare il trial con ρ più vicino a sealed +0.1883
    print("\n" + "=" * 80)
    print("RANKING trial per |ρ - 0.1883|")
    print("=" * 80)
    rhos = []
    for tid in sorted(f2["trial_id"].unique()):
        r = f2[f2["trial_id"] == tid].sort_values("date")["daily_return"].values.astype(float)
        rhos.append((tid, ar1_rho(r), abs(ar1_rho(r) - 0.1883)))
    rhos.sort(key=lambda x: x[2])
    for tid, rho, gap in rhos:
        print(f"  trial {tid}: ρ={rho:+.4f}, |gap_to_sealed|={gap:.4f}")


if __name__ == "__main__":
    main()
