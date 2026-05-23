"""
Task 7 — DSR finale: doppio output Opt(A) per-fold + Opt(B) aggregato concatenato.

Formula canonica Bailey-LdP 2014 eq. 11 (scala daily coerente):
  DSR = Φ((SR̂_d − SR_0_d) · √(T−1) / sqrt(1 − γ₁·SR̂_d + (γ₂/4)·SR̂²_d))

Input:
- SR̂_d = SR̂_annual / √252  (mediana 3 best OOS, opt(i))
- SR_0_d (primario): bootstrap empirico (Task 5) per T<100, formula chiusa altrimenti
- SR_0_d (sensitivity): formula chiusa Bailey-LdP √(2 ln N_eff) / √252
- γ₁, γ₂_excess: point Joanes-Gill (Task 6)
- T: F1=66, F2=65, F3=65, Agg=196
- N_eff: primario 1.2231 (OOS aggregato), sensitivity 1.1521 (IS), secondario 8.0 (cluster)

Sensitivity per Task 7:
- Banda DSR su CI 90% γ₂ (low/high)
- N_eff IS vs OOS
- SR_0 boot vs formula chiusa
"""
import numpy as np
from scipy.stats import norm

# =============================================================================
# Input sigillati
# =============================================================================

# SR̂_annual per fold + Agg (mediana 3 best OOS)
SR_hat_a = {'F1': 2.631, 'F2': 3.033, 'F3': -0.110, 'Agg_daily_to_annual': None}

# T_eff per fold
T_eff = {'F1': 66, 'F2': 44.4, 'F3': 65, 'Agg': 196}  # F2 post-AR1
T_raw = {'F1': 66, 'F2': 65, 'F3': 65, 'Agg': 196}    # senza correzione AR1

# SR̂_daily da equity csv (calcolato in Task 5)
SR_hat_d = {'F1': 0.1657, 'F2': 0.1911, 'F3': -0.0069, 'Agg': 0.0744}

# SR_0 bootstrap daily (Task 5, b=5)
SR_0_boot_d = {'F1': 0.0870, 'F2': 0.0968, 'F3': 0.0735, 'Agg': 0.0443}

# γ point Joanes-Gill (Task 6)
G1 = {'F1': -0.2036, 'F2': +0.6081, 'F3': +0.5635, 'Agg': +0.4873}
G2 = {'F1': +0.7660, 'F2': +1.2726, 'F3': +3.0367, 'Agg': +6.3370}

# γ₂ CI 90% (Task 6)
G2_ci = {'F1': (-0.4184, +1.5826),
         'F2': (-0.1876, +2.7002),
         'F3': (+0.5256, +5.0370),
         'Agg': (+1.6903, +9.2062)}
G1_ci = {'F1': (-0.6190, +0.3978),
         'F2': (-0.1657, +1.1579),
         'F3': (-0.3810, +1.6100),
         'Agg': (-0.7129, +1.7583)}

# N_eff (decisione_neff_primario.md)
N_eff_primary  = 1.2231  # OOS aggregato trace-based
N_eff_sens     = 1.1521  # IS C_mean
N_eff_secondary= 8.0     # cluster-count

# =============================================================================
# Formula
# =============================================================================
def dsr(SR_hat_d, SR_0_d, T, g1, g2):
    """Bailey-Lopez de Prado 2014 eq.11, scala daily."""
    num = (SR_hat_d - SR_0_d) * np.sqrt(T - 1)
    den_var = 1.0 - g1 * SR_hat_d + (g2 / 4.0) * SR_hat_d**2
    if den_var <= 0:
        return np.nan
    den = np.sqrt(den_var)
    z = num / den
    return norm.cdf(z), z, den_var

def sr0_formula_d(N_eff, ann=False):
    """SR_0 formula chiusa Bailey-LdP √(2 ln N_eff). Returns daily se ann=False."""
    if N_eff <= 1:
        return 0.0
    sr_a = np.sqrt(2.0 * np.log(N_eff))
    return sr_a if ann else sr_a / np.sqrt(252)

# =============================================================================
# Output Opt(A) per-fold
# =============================================================================
print("=" * 100)
print("Task 7 — DSR finale (Opt A per-fold + Opt B aggregato)")
print("=" * 100)

print("\n--- Opt (A) per-fold ---")
print(f"{'Fold':4} {'T':>6} {'SR̂_d':>9} {'SR_0_d_boot':>12} {'SR_0_d_form':>12} {'γ₁':>8} {'γ₂':>8} {'DSR_boot':>10} {'DSR_form':>10}")

results_A = {}
for f in ['F1', 'F2', 'F3']:
    T = T_eff[f]
    sr_h = SR_hat_d[f]
    sr0_b = SR_0_boot_d[f]
    sr0_f = sr0_formula_d(N_eff_primary)
    g1, g2 = G1[f], G2[f]

    dsr_boot, z_b, dv_b = dsr(sr_h, sr0_b, T, g1, g2)
    dsr_form, z_f, dv_f = dsr(sr_h, sr0_f, T, g1, g2)

    results_A[f] = {
        'T': T, 'SR_hat_d': sr_h, 'SR_0_d_boot': sr0_b, 'SR_0_d_form': sr0_f,
        'G1': g1, 'G2': g2,
        'DSR_boot': dsr_boot, 'DSR_form': dsr_form,
        'z_boot': z_b, 'z_form': z_f, 'denom_var': dv_b
    }
    print(f"{f:4} {T:6.1f} {sr_h:+9.4f} {sr0_b:12.4f} {sr0_f:12.4f} {g1:+8.4f} {g2:+8.4f} {dsr_boot:10.4f} {dsr_form:10.4f}")

# --- Opt (B) aggregato ---
print("\n--- Opt (B) aggregato concatenato T=196 ---")
print(f"{'Stat':30} {'value':>12}")

T_agg = T_eff['Agg']
sr_h_agg = SR_hat_d['Agg']
sr0_b_agg = SR_0_boot_d['Agg']
sr0_f_agg_prim = sr0_formula_d(N_eff_primary)
sr0_f_agg_sens = sr0_formula_d(N_eff_sens)
sr0_f_agg_sec  = sr0_formula_d(N_eff_secondary)
g1_agg = G1['Agg']
g2_agg = G2['Agg']

dsr_agg_boot, z_agg_b, dv_agg = dsr(sr_h_agg, sr0_b_agg, T_agg, g1_agg, g2_agg)
dsr_agg_form_prim, z_p, _ = dsr(sr_h_agg, sr0_f_agg_prim, T_agg, g1_agg, g2_agg)
dsr_agg_form_sens, z_s, _ = dsr(sr_h_agg, sr0_f_agg_sens, T_agg, g1_agg, g2_agg)
dsr_agg_form_sec , z_c, _ = dsr(sr_h_agg, sr0_f_agg_sec , T_agg, g1_agg, g2_agg)

print(f"{'T_agg':30} {T_agg:>12.0f}")
print(f"{'SR̂_d_agg':30} {sr_h_agg:>12.4f}")
print(f"{'SR_0_d_boot':30} {sr0_b_agg:>12.4f}")
print(f"{'SR_0_d_form (N_eff=1.2231)':30} {sr0_f_agg_prim:>12.4f}")
print(f"{'SR_0_d_form (N_eff=1.1521)':30} {sr0_f_agg_sens:>12.4f}")
print(f"{'SR_0_d_form (N_eff=8.0 sec)':30} {sr0_f_agg_sec:>12.4f}")
print(f"{'γ₁ point':30} {g1_agg:>12.4f}")
print(f"{'γ₂ point':30} {g2_agg:>12.4f}")
print(f"{'denominator var':30} {dv_agg:>12.4f}")
print(f"{'DSR_boot (primary)':30} {dsr_agg_boot:>12.4f}")
print(f"{'DSR_form N=1.2231 (primary)':30} {dsr_agg_form_prim:>12.4f}")
print(f"{'DSR_form N=1.1521 (sens)':30} {dsr_agg_form_sens:>12.4f}")
print(f"{'DSR_form N=8.0 (cluster)':30} {dsr_agg_form_sec:>12.4f}")

# =============================================================================
# Sensitivity DSR su γ₂ CI 90%
# =============================================================================
print("\n--- Sensitivity DSR su γ₂ CI 90% (Opt A + Opt B) ---")
print(f"{'Fold':4} {'γ₂ low':>9} {'γ₂ point':>9} {'γ₂ high':>9} {'DSR(γ₂ low)':>13} {'DSR(γ₂ point)':>14} {'DSR(γ₂ high)':>14}")

sens_g2 = {}
for f in ['F1', 'F2', 'F3', 'Agg']:
    T = T_eff[f]
    sr_h = SR_hat_d[f]
    sr0 = SR_0_boot_d[f]
    g1 = G1[f]
    g2_lo, g2_hi = G2_ci[f]
    dsr_lo, _, _ = dsr(sr_h, sr0, T, g1, g2_lo)
    dsr_pt, _, _ = dsr(sr_h, sr0, T, g1, G2[f])
    dsr_hi, _, _ = dsr(sr_h, sr0, T, g1, g2_hi)
    sens_g2[f] = (dsr_lo, dsr_pt, dsr_hi)
    print(f"{f:4} {g2_lo:+9.4f} {G2[f]:+9.4f} {g2_hi:+9.4f} {dsr_lo:13.4f} {dsr_pt:14.4f} {dsr_hi:14.4f}")

# Sensitivity su γ₁ CI 90%
print("\n--- Sensitivity DSR su γ₁ CI 90% ---")
print(f"{'Fold':4} {'γ₁ low':>9} {'γ₁ point':>9} {'γ₁ high':>9} {'DSR(γ₁ low)':>13} {'DSR(γ₁ point)':>14} {'DSR(γ₁ high)':>14}")
sens_g1 = {}
for f in ['F1', 'F2', 'F3', 'Agg']:
    T = T_eff[f]
    sr_h = SR_hat_d[f]
    sr0 = SR_0_boot_d[f]
    g2 = G2[f]
    g1_lo, g1_hi = G1_ci[f]
    dsr_lo, _, _ = dsr(sr_h, sr0, T, g1_lo, g2)
    dsr_pt, _, _ = dsr(sr_h, sr0, T, G1[f], g2)
    dsr_hi, _, _ = dsr(sr_h, sr0, T, g1_hi, g2)
    sens_g1[f] = (dsr_lo, dsr_pt, dsr_hi)
    print(f"{f:4} {g1_lo:+9.4f} {G1[f]:+9.4f} {g1_hi:+9.4f} {dsr_lo:13.4f} {dsr_pt:14.4f} {dsr_hi:14.4f}")

# =============================================================================
# Sensitivity N_eff (formula chiusa)
# =============================================================================
print("\n--- Sensitivity N_eff su DSR formula chiusa (SR_0 chiuso) ---")
print(f"{'Fold':4} {'N_eff=1.1521':>15} {'N_eff=1.2231':>15} {'N_eff=8.0':>15}")
for f in ['F1', 'F2', 'F3', 'Agg']:
    T = T_eff[f]
    sr_h = SR_hat_d[f]
    g1, g2 = G1[f], G2[f]
    res = []
    for Ne in [1.1521, 1.2231, 8.0]:
        sr0 = sr0_formula_d(Ne)
        d, _, _ = dsr(sr_h, sr0, T, g1, g2)
        res.append(d)
    print(f"{f:4} {res[0]:15.4f} {res[1]:15.4f} {res[2]:15.4f}")

# =============================================================================
# Sanity vincolo bilatero (DSR > 0.5)
# =============================================================================
print("\n--- Vincolo bilatero DSR > 0.5 ---")
for f in ['F1', 'F2', 'F3']:
    db = results_A[f]['DSR_boot']
    df = results_A[f]['DSR_form']
    flag_b = "PASS" if db > 0.5 else "FAIL"
    flag_f = "PASS" if df > 0.5 else "FAIL"
    print(f"  {f}: DSR_boot={db:.4f} [{flag_b}]  DSR_form={df:.4f} [{flag_f}]")
flag_b = "PASS" if dsr_agg_boot > 0.5 else "FAIL"
flag_f = "PASS" if dsr_agg_form_prim > 0.5 else "FAIL"
print(f"  Agg: DSR_boot={dsr_agg_boot:.4f} [{flag_b}]  DSR_form_prim={dsr_agg_form_prim:.4f} [{flag_f}]")

# =============================================================================
# Save
# =============================================================================
out = {}
for f in ['F1', 'F2', 'F3']:
    for k, v in results_A[f].items():
        out[f'{f}_{k}'] = v
out['Agg_T'] = T_agg
out['Agg_SR_hat_d'] = sr_h_agg
out['Agg_SR_0_d_boot'] = sr0_b_agg
out['Agg_SR_0_d_form_primary'] = sr0_f_agg_prim
out['Agg_SR_0_d_form_sens'] = sr0_f_agg_sens
out['Agg_DSR_boot'] = dsr_agg_boot
out['Agg_DSR_form_primary'] = dsr_agg_form_prim
out['Agg_DSR_form_sens'] = dsr_agg_form_sens

np.savez('task7_dsr_final.npz', **out)
print("\nSaved task7_dsr_final.npz")
