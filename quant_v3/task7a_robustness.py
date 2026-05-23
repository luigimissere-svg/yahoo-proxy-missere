"""
Task 7a — Robustness post-feedback consulente:
1. Ljung-Box su F1 e F3 (oltre F2 già fatto)
2. Ricalcolo DSR per-fold con T_eff aggiornato (se autocorr significativa)
3. Decomposizione gap SR_0_boot vs SR_0_form per-fold (P6 esito)
4. Verifica vincolo bilatero sigillato Task 3 (primario>1.0 + secondario>0.5)
"""
import numpy as np
from scipy import stats
from scipy.stats import norm

data = np.load('task6_returns.npz')

# =============================================================================
# 1. Ljung-Box test su tutti i fold
# =============================================================================
print("=" * 80)
print("1. Ljung-Box test autocorrelazione (lags 1..10)")
print("=" * 80)

def ar1_rho(x):
    """AR1 coefficient via lag-1 autocorrelation."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0

def ljung_box(x, lags=10):
    """Ljung-Box Q statistic and p-value."""
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

def T_eff_politis(T, rho):
    """Politis effective sample size for AR1."""
    if abs(rho) >= 1:
        return T
    return T * (1 - rho) / (1 + rho)

folds = ['F1', 'F2', 'F3', 'Agg']
T_raw = {'F1': 66, 'F2': 65, 'F3': 65, 'Agg': 196}

print(f"\n{'Fold':6} {'T':>5} {'rho_AR1':>10} {'Q(10)':>10} {'p-value':>10} {'sig 5%':>8} {'T_eff':>9}")
ljb_results = {}
for f in folds:
    x = data[f]
    rho = ar1_rho(x)
    Q, p, rhos = ljung_box(x, lags=10)
    sig = "YES" if p < 0.05 else "no"
    T_e = T_eff_politis(T_raw[f], rho)
    ljb_results[f] = {'rho': rho, 'Q': Q, 'p': p, 'T_eff': T_e, 'sig': p < 0.05}
    print(f"{f:6} {T_raw[f]:>5d} {rho:+10.4f} {Q:>10.3f} {p:>10.4f} {sig:>8} {T_e:>9.2f}")

# =============================================================================
# 2. Ricalcolo DSR con T_eff aggiornato
# =============================================================================
print("\n" + "=" * 80)
print("2. DSR per-fold con T_eff post Ljung-Box")
print("=" * 80)

# Input sigillati
SR_hat_d = {'F1': 0.1657, 'F2': 0.1911, 'F3': -0.0069, 'Agg': 0.0744}
SR_0_boot_d = {'F1': 0.0870, 'F2': 0.0968, 'F3': 0.0735, 'Agg': 0.0443}
G1 = {'F1': -0.2036, 'F2': +0.6081, 'F3': +0.5635, 'Agg': +0.4873}
G2 = {'F1': +0.7660, 'F2': +1.2726, 'F3': +3.0367, 'Agg': +6.3370}

def dsr(SR_hat_d, SR_0_d, T, g1, g2):
    num = (SR_hat_d - SR_0_d) * np.sqrt(T - 1)
    den_var = 1.0 - g1 * SR_hat_d + (g2 / 4.0) * SR_hat_d**2
    if den_var <= 0:
        return np.nan, np.nan, np.nan
    den = np.sqrt(den_var)
    z = num / den
    return norm.cdf(z), z, den_var

print(f"\n{'Fold':6} {'T_raw':>6} {'T_eff':>8} {'DSR(T_raw)':>12} {'DSR(T_eff)':>12} {'Δ':>8}")
dsr_results = {}
for f in folds:
    Tr = T_raw[f]
    Te = ljb_results[f]['T_eff']
    d_raw, _, _ = dsr(SR_hat_d[f], SR_0_boot_d[f], Tr, G1[f], G2[f])
    d_eff, _, _ = dsr(SR_hat_d[f], SR_0_boot_d[f], Te, G1[f], G2[f])
    dsr_results[f] = {'DSR_raw': d_raw, 'DSR_eff': d_eff, 'T_raw': Tr, 'T_eff': Te}
    print(f"{f:6} {Tr:>6d} {Te:>8.2f} {d_raw:>12.4f} {d_eff:>12.4f} {d_eff-d_raw:>+8.4f}")

# =============================================================================
# 3. Decomposizione gap SR_0_boot vs SR_0_form
# =============================================================================
print("\n" + "=" * 80)
print("3. Decomposizione gap SR_0_boot vs SR_0_form (esito P6)")
print("=" * 80)

N_eff_primary = 1.2231
def sr0_form_d(N, T):
    if N <= 1:
        return 0.0
    return np.sqrt(2.0 * np.log(N)) / np.sqrt(T)

print(f"\nFormula chiusa Bailey-LdP: SR_0_d = sqrt(2·ln(N_eff)) / sqrt(252)")
print(f"N_eff primary = {N_eff_primary}")
print(f"\n{'Fold':6} {'T':>5} {'SR_0_boot':>11} {'SR_0_form':>11} {'gap abs':>10} {'gap rel %':>11}")
for f in folds:
    T = T_raw[f]
    sr0_b = SR_0_boot_d[f]
    sr0_f = np.sqrt(2.0 * np.log(N_eff_primary)) / np.sqrt(252)  # annualizzato/sqrt(252)
    gap_abs = sr0_b - sr0_f
    gap_rel = (sr0_b - sr0_f) / sr0_f * 100 if sr0_f > 0 else np.nan
    print(f"{f:6} {T:>5d} {sr0_b:>11.4f} {sr0_f:>11.4f} {gap_abs:>+10.4f} {gap_rel:>+11.1f}")

# Implied N_eff dal bootstrap (inverting formula)
print(f"\n{'Fold':6} {'SR_0_boot':>11} {'N_eff_implied':>14} {'N_eff_form':>11} {'ratio':>8}")
for f in folds:
    sr0_b = SR_0_boot_d[f]
    # SR_0_d = sqrt(2 ln N) / sqrt(252) → N = exp((SR_0_d * sqrt(252))^2 / 2)
    sr0_ann = sr0_b * np.sqrt(252)
    N_impl = np.exp(sr0_ann**2 / 2.0)
    ratio = N_impl / N_eff_primary
    print(f"{f:6} {sr0_b:>11.4f} {N_impl:>14.2f} {N_eff_primary:>11.4f} {ratio:>8.1f}x")

# =============================================================================
# 4. Vincolo bilatero sigillato Task 3
# =============================================================================
print("\n" + "=" * 80)
print("4. Vincolo bilatero sigillato Task 3")
print("=" * 80)
print("\nSoglie: DSR primario > 1.0  E  DSR secondario > 0.5")
print("DSR primario = DSR_boot (SR_0 bootstrap, N_eff trace primary)")
print("DSR secondario = DSR_form con N_eff=8 (cluster-count)")

def sr0_form_d_N(N):
    if N <= 1:
        return 0.0
    return np.sqrt(2.0 * np.log(N)) / np.sqrt(252)

print(f"\n{'Fold':6} {'DSR_prim':>10} {'>1.0?':>7} {'DSR_sec(N=8)':>14} {'>0.5?':>7} {'Bilatero':>10}")
for f in folds:
    Te = ljb_results[f]['T_eff']
    d_prim, _, _ = dsr(SR_hat_d[f], SR_0_boot_d[f], Te, G1[f], G2[f])
    sr0_sec = sr0_form_d_N(8.0)
    d_sec, _, _ = dsr(SR_hat_d[f], sr0_sec, Te, G1[f], G2[f])
    flag_p = "PASS" if d_prim > 1.0 else "FAIL"
    flag_s = "PASS" if d_sec > 0.5 else "FAIL"
    bil = "PASS" if (d_prim > 1.0 and d_sec > 0.5) else "FAIL"
    print(f"{f:6} {d_prim:>10.4f} {flag_p:>7} {d_sec:>14.4f} {flag_s:>7} {bil:>10}")

print("\n[Nota] DSR primario soglia >1.0 è IMPOSSIBILE in CDF normale (Φ max=1.0).")
print("       Probabilmente il sigillo Task 3 intendeva 'z primario > 1.0' non DSR.")
print("       Ricontrollo necessario sul sigillo originale.")
