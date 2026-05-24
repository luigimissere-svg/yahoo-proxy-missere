"""
S2 indagine Bug 8 - Diagnostica strutturale.

Perché ρ_AR(1) sealed = +0.1883 ma ρ_AR(1) rerun = -0.0807?
Le due serie hanno Pearson +0.7361 ma flip di segno su lag-1.

Test:
1. Shift di 1 bar tra sealed e rerun
2. ρ_AR(1) rerun dopo aver applicato il fit lineare sealed = a + b*rerun
3. Identificazione delle posizioni dove sealed e rerun differiscono molto
4. Cumulato sealed vs rerun (equity curve implicita)
5. Posizione del primo bar zero in sealed
"""
import numpy as np
import pandas as pd

NPZ = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/task6_returns.npz"
RERUN_F2 = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/f2_oos_daily_returns_rerun.csv"


def ar1_rho(x):
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0


def main():
    data = np.load(NPZ)
    sealed = data["F2"]
    rerun = pd.read_csv(RERUN_F2)["daily_return"].values.astype(float)
    rerun_dates = pd.read_csv(RERUN_F2)["date"].values

    print(f"Sealed T={len(sealed)}, Rerun T={len(rerun)}")
    print(f"Sealed[0:10]: {sealed[:10]}")
    print(f"Rerun [0:10]: {rerun[:10]}")
    print(f"Sealed[-5:]:  {sealed[-5:]}")
    print(f"Rerun [-5:]:  {rerun[-5:]}")

    # ---- Shift tests ----
    print("\n" + "=" * 70)
    print("TEST 1 — Pearson corr a vari shift sealed-vs-rerun")
    print("=" * 70)
    for s in range(-3, 4):
        if s == 0:
            a, b = sealed, rerun
        elif s > 0:
            a, b = sealed[s:], rerun[:-s]
        else:
            a, b = sealed[:s], rerun[-s:]
        if len(a) < 5:
            continue
        c = np.corrcoef(a, b)[0, 1]
        print(f"  shift sealed by {s:+d}: corr={c:+.4f}, T_eff={len(a)}")

    # ---- ρ_AR(1) sealed con primo elemento rimosso ----
    print("\n" + "=" * 70)
    print("TEST 2 — ρ_AR(1) sealed escludendo il primo elemento (=0.0)")
    print("=" * 70)
    rho_full = ar1_rho(sealed)
    rho_skip0 = ar1_rho(sealed[1:])
    print(f"  ρ_AR(1) sealed full (T={len(sealed)}):           {rho_full:+.4f}")
    print(f"  ρ_AR(1) sealed senza primo (T={len(sealed)-1}):  {rho_skip0:+.4f}")
    print(f"  → il primo elemento 0.0 contribuisce per: {rho_full - rho_skip0:+.4f}")

    # ---- ρ_AR(1) sealed e rerun side-by-side ----
    print("\n" + "=" * 70)
    print("TEST 3 — ρ_AR(1) di varie trasformazioni della rerun")
    print("=" * 70)
    rho_rerun = ar1_rho(rerun)
    rho_rerun_demean = ar1_rho(rerun - rerun.mean())
    # forza primo elemento a 0
    rerun_force0 = rerun.copy(); rerun_force0[0] = 0.0
    rho_rerun_force0 = ar1_rho(rerun_force0)
    # rerun * 0.5318 (scaling del fit)
    rho_rerun_scaled = ar1_rho(rerun * 0.5318)
    # rerun shifted di 1
    rerun_shift1 = np.concatenate([[0.0], rerun[:-1]])
    rho_rerun_shift1 = ar1_rho(rerun_shift1)
    print(f"  ρ rerun                            : {rho_rerun:+.4f}")
    print(f"  ρ rerun demeaned                   : {rho_rerun_demean:+.4f}  (uguale, demean non cambia)")
    print(f"  ρ rerun con primo elem forzato 0   : {rho_rerun_force0:+.4f}")
    print(f"  ρ rerun * 0.5318 (scaling)         : {rho_rerun_scaled:+.4f}  (uguale, scale-invariant)")
    print(f"  ρ rerun shifted di 1 (lag intera)  : {rho_rerun_shift1:+.4f}")

    # ---- Cumulato equity-curve ----
    print("\n" + "=" * 70)
    print("TEST 4 — Cumulato (equity curve implicita)")
    print("=" * 70)
    cum_sealed = (1 + sealed).cumprod()
    cum_rerun = (1 + rerun).cumprod()
    print(f"  Final equity sealed: {cum_sealed[-1]:.6f}  (return totale {(cum_sealed[-1]-1)*100:+.2f}%)")
    print(f"  Final equity rerun:  {cum_rerun[-1]:.6f}  (return totale {(cum_rerun[-1]-1)*100:+.2f}%)")
    print(f"  Ratio (sealed/rerun): {cum_sealed[-1]/cum_rerun[-1]:.4f}")
    print(f"  Diff finale assoluta: {(cum_sealed[-1]-cum_rerun[-1])*100:+.2f}%")

    # ---- Top deviations ----
    print("\n" + "=" * 70)
    print("TEST 5 — Top 10 posizioni con max diff |sealed - rerun|")
    print("=" * 70)
    diff = sealed - rerun
    idx_sorted = np.argsort(-np.abs(diff))
    print(f"  {'idx':>4} {'date':>12} {'sealed':>10} {'rerun':>10} {'diff':>10}")
    for i in idx_sorted[:10]:
        print(f"  {i:>4d} {str(rerun_dates[i])[:10]:>12} {sealed[i]:+10.6f} {rerun[i]:+10.6f} {diff[i]:+10.6f}")

    # ---- Date allineate? ----
    print("\n" + "=" * 70)
    print("TEST 6 — Date rerun primo/ultimo vs serie sealed shape")
    print("=" * 70)
    print(f"  Rerun: {rerun_dates[0]} → {rerun_dates[-1]} (T={len(rerun)})")
    print(f"  Sealed primo elem = 0.0 (Bar OOS-start = warmup/inception equity invariata)")
    print(f"  Rerun primo elem = {rerun[0]:+.6f}")

    # Test: la sealed POTREBBE essere un ricampionamento di equity_curve raw OOS:
    # daily_return_sealed[i] = (equity_oos[i] - equity_oos[i-1]) / equity_oos[i-1]
    # con equity_oos[0] = capitale iniziale fold (no return) → primo = 0
    # Mentre la rerun usa daily_return collector che è già returns post-MtM Backtrader

    # Test cruciale: scalando rerun e shiftando di 1, otteniamo ρ +0.19?
    print("\n" + "=" * 70)
    print("TEST 7 — Ricostruzione: rerun con primo bar=0 e altri vari trattamenti")
    print("=" * 70)
    # 7a: prependi 0 e rimuovi ultimo
    v7a = np.concatenate([[0.0], rerun[:-1]])
    print(f"  7a prepend 0, drop last: ρ={ar1_rho(v7a):+.4f}, T={len(v7a)}")
    # 7b: sostituisci primo con 0
    v7b = rerun.copy(); v7b[0] = 0.0
    print(f"  7b primo→0, resto invariato: ρ={ar1_rho(v7b):+.4f}, T={len(v7b)}")
    # 7c: smoothing 2-day MA
    v7c = np.convolve(rerun, np.array([0.5, 0.5]), mode='same')
    print(f"  7c MA(2) su rerun: ρ={ar1_rho(v7c):+.4f}")
    # 7d: differenze prime di equity_curve cumulata
    eq = np.concatenate([[1.0], (1+rerun).cumprod()])
    v7d = np.diff(eq) / eq[:-1]
    print(f"  7d diff% equity curve (= rerun): ρ={ar1_rho(v7d):+.4f}")
    # 7e: medie portfolio-style: ogni ritorno spalmato su 5 giorni
    v7e = np.zeros_like(rerun)
    for i in range(len(rerun)):
        end = min(i+5, len(rerun))
        v7e[i:end] += rerun[i] / 5
    print(f"  7e spread over 5d: ρ={ar1_rho(v7e):+.4f}")

    print("\n" + "=" * 70)
    print("CONCLUSIONE")
    print("=" * 70)
    print("Le due serie hanno Pearson +0.736 (stessa direzione complessiva del portfolio)")
    print("ma differiscono strutturalmente nel TIMING dei ritorni: la sealed sembra")
    print("aver subito un'operazione di smoothing/spreading che introduce autocorrelazione")
    print("positiva ARTIFICIALE (averaging crea persistence).")
    print()
    print("Se 7c o 7e producono ρ ≈ +0.19 → BUG 8 = ARTEFATTO DI CALCOLO (smoothing).")
    print("Se nessuno match → divergenza strutturale altra causa.")


if __name__ == "__main__":
    main()
