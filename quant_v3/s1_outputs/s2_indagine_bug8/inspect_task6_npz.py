"""
S2 indagine Bug 8 - Step 2/3/4.

Ispeziona task6_returns.npz (input al test AR(1) sealed task 7a) per recuperare:
- Quali fold/array sono dentro
- Loro shape e contenuto F2 sealed
- Riproduzione esatta del calcolo +0.1883
- Confronto con f2_oos_daily_returns_rerun.csv (collector ufficiale)
"""
import numpy as np
import pandas as pd
import hashlib

NPZ = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/task6_returns.npz"
RERUN_F2 = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s15_outputs/f2_oos_daily_returns_rerun.csv"


def ar1_rho_sealed(x):
    """Formula ESATTA del codice sealed task7a_robustness.py."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0


def ljung_box_sealed(x, lags=10):
    """Formula ESATTA del codice sealed."""
    from scipy import stats
    n = len(x)
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    den = np.sum(x ** 2)
    rhos = []
    for k in range(1, lags + 1):
        num = np.sum(x[:-k] * x[k:])
        rhos.append(num / den if den > 0 else 0.0)
    rhos = np.array(rhos)
    Q = n * (n + 2) * np.sum(rhos ** 2 / (n - np.arange(1, lags + 1)))
    p = 1 - stats.chi2.cdf(Q, df=lags)
    return Q, p, rhos


def main():
    print("=" * 80)
    print("STEP 2 — Apertura task6_returns.npz (input sealed task 7a)")
    print("=" * 80)
    data = np.load(NPZ, allow_pickle=False)
    print(f"\nKeys: {list(data.keys())}")
    for k in data.keys():
        a = data[k]
        print(f"  {k:8} → shape={a.shape}, dtype={a.dtype}, "
              f"min={a.min():.6f}, max={a.max():.6f}, mean={a.mean():.6f}, std={a.std(ddof=1):.6f}")

    print("\n" + "=" * 80)
    print("STEP 3 — Riproduzione esatta del calcolo +0.1883 su F2")
    print("=" * 80)
    if "F2" not in data.keys():
        print("[ERRORE] Chiave F2 non presente.")
        return
    f2_sealed = np.asarray(data["F2"], dtype=float)
    print(f"\nSerie F2 sealed: T = {len(f2_sealed)}")
    print(f"Prime 5: {f2_sealed[:5]}")
    print(f"Ultime 5: {f2_sealed[-5:]}")

    rho_sealed = ar1_rho_sealed(f2_sealed)
    Q_sealed, p_sealed, _ = ljung_box_sealed(f2_sealed, lags=10)
    print(f"\nρ_AR(1) sealed-formula su F2 sealed: {rho_sealed:+.4f}  (target +0.1883)")
    print(f"Q(10) sealed-formula su F2 sealed:   {Q_sealed:.3f}    (target 20.374)")
    print(f"p-value: {p_sealed:.4f}")
    repro = abs(rho_sealed - 0.1883) < 0.001
    print(f"RIPRODUCIBILITÀ +0.1883: {'CONFERMATA' if repro else 'FALLITA'}")

    print("\n" + "=" * 80)
    print("STEP 4 — Confronto con serie f2_oos_daily_returns_rerun.csv")
    print("=" * 80)
    rerun = pd.read_csv(RERUN_F2)
    print(f"\nRerun: {len(rerun)} righe, date {rerun['date'].min()} → {rerun['date'].max()}")
    rerun_arr = rerun["daily_return"].values.astype(float)
    print(f"Rerun stats: T={len(rerun_arr)}, mean={rerun_arr.mean():.6f}, "
          f"std={rerun_arr.std(ddof=1):.6f}, min={rerun_arr.min():.6f}, max={rerun_arr.max():.6f}")

    print(f"\nDIFF DESCRITTIVA SEALED F2 vs RERUN F2:")
    print(f"  T:    {len(f2_sealed)} vs {len(rerun_arr)}")
    print(f"  mean: {f2_sealed.mean():+.6f} vs {rerun_arr.mean():+.6f}  (delta {f2_sealed.mean()-rerun_arr.mean():+.6f})")
    print(f"  std:  {f2_sealed.std(ddof=1):.6f} vs {rerun_arr.std(ddof=1):.6f}  (ratio {f2_sealed.std(ddof=1)/rerun_arr.std(ddof=1):.4f})")
    print(f"  min:  {f2_sealed.min():+.6f} vs {rerun_arr.min():+.6f}")
    print(f"  max:  {f2_sealed.max():+.6f} vs {rerun_arr.max():+.6f}")

    # Allineamento per check 1:1 se T uguale
    if len(f2_sealed) == len(rerun_arr):
        diff = f2_sealed - rerun_arr
        corr = np.corrcoef(f2_sealed, rerun_arr)[0, 1]
        print(f"\nCONFRONTO 1:1 (stessa T={len(f2_sealed)}):")
        print(f"  Pearson corr sealed-vs-rerun: {corr:+.4f}")
        print(f"  max |diff|: {np.abs(diff).max():.6f}")
        print(f"  mean diff:  {diff.mean():+.6f}")
        print(f"  RMSE diff:  {np.sqrt((diff**2).mean()):.6f}")
        # Test: la serie sealed è una semplice trasformazione lineare della rerun?
        if rerun_arr.std() > 0:
            slope, intercept = np.polyfit(rerun_arr, f2_sealed, 1)
            print(f"  Fit lineare sealed ~ a + b*rerun: a={intercept:+.6f}, b={slope:+.6f}")

        # Test: sealed = -rerun?
        rho_neg = np.corrcoef(f2_sealed, -rerun_arr)[0, 1]
        print(f"  Pearson sealed vs (-rerun): {rho_neg:+.4f}")
    else:
        print("\n[Note] T diverse, niente confronto 1:1 puntuale.")
        # Stesso ρ_AR(1) sulla rerun con la formula sealed?
        rho_rerun_sealed_formula = ar1_rho_sealed(rerun_arr)
        Q_rerun_sealed_formula, _, _ = ljung_box_sealed(rerun_arr, lags=10)
        print(f"  ρ_AR(1) sealed-formula su rerun: {rho_rerun_sealed_formula:+.4f}")
        print(f"  Q(10)  sealed-formula su rerun:  {Q_rerun_sealed_formula:.3f}")

    print("\n" + "=" * 80)
    print("RISULTATO")
    print("=" * 80)
    print(f"Serie F2 sealed: 'task6_returns.npz' key='F2', T={len(f2_sealed)}, hash:")
    h = hashlib.sha256(f2_sealed.tobytes()).hexdigest()
    print(f"  SHA256 array F2 sealed: {h}")
    rerun_h = hashlib.sha256(rerun_arr.tobytes()).hexdigest()
    print(f"  SHA256 array F2 rerun:  {rerun_h}")

    # Salva anche CSV della serie sealed per ispezione manuale
    out = pd.DataFrame({"index": np.arange(len(f2_sealed)), "f2_sealed": f2_sealed})
    out_path = "/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs/s2_indagine_bug8/f2_sealed_from_npz.csv"
    out.to_csv(out_path, index=False)
    print(f"\nCSV serie sealed F2: {out_path}")


if __name__ == "__main__":
    main()
