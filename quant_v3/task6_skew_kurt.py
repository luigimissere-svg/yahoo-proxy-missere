"""
Task 6 — γ₁ (skewness) e γ₂_excess (excess kurtosis) Joanes-Gill bias-corrected
+ CI 90% via block bootstrap moving-block (L=5, B=10000)

Joanes-Gill (1998) bias-corrected sample skewness/excess-kurtosis:
  G1 = (sqrt(n(n-1))/(n-2)) * g1
  G2 = ((n-1)/((n-2)(n-3))) * ((n+1)*g2 + 6)
dove
  g1 = m3 / m2^(3/2),  g2 = m4/m2^2 - 3  (sample moments)

Procedura:
1. Calcolo Joanes-Gill su sample completo per F1, F2, F3, Agg
2. Block bootstrap moving-block circolare L=5, B=10000 → distribuzione γ₁, γ₂
3. CI 90% (percentile method) [5%, 95%]
4. Cross-check con Task 5 bootstrap (mediane già calcolate, verifica coerenza)
"""
import numpy as np

rng = np.random.default_rng(2026_05_23_06)

def sample_moments(x):
    """Joanes-Gill bias-corrected skewness e excess kurtosis."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 4:
        return np.nan, np.nan
    mu = x.mean()
    d = x - mu
    m2 = (d**2).mean()
    if m2 <= 0:
        return np.nan, np.nan
    m3 = (d**3).mean()
    m4 = (d**4).mean()
    g1 = m3 / m2**1.5
    g2 = m4 / m2**2 - 3.0
    G1 = (np.sqrt(n*(n-1)) / (n-2)) * g1
    G2 = ((n-1) / ((n-2)*(n-3))) * ((n+1)*g2 + 6)
    return G1, G2

def moving_block_bootstrap(x, L, B, rng):
    """Moving-block bootstrap circolare. Restituisce array B×n di resamples."""
    x = np.asarray(x)
    n = len(x)
    n_blocks = int(np.ceil(n / L))
    # Estendi ciclico per circular
    x_ext = np.concatenate([x, x[:L]])
    out_G1 = np.empty(B)
    out_G2 = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, n, size=n_blocks)
        # Costruisci sample
        idx = np.concatenate([np.arange(s, s+L) for s in starts])[:n]
        idx = idx % n  # wrap
        sample = x_ext[idx]
        G1, G2 = sample_moments(sample)
        out_G1[b] = G1
        out_G2[b] = G2
    return out_G1, out_G2

data = np.load('task6_returns.npz')
folds = ['F1', 'F2', 'F3', 'Agg']

L = 5
B = 10000

results = {}
boot_dists = {}

print("=" * 80)
print("Task 6 — γ₁, γ₂_excess Joanes-Gill + block bootstrap CI 90%")
print(f"L = {L}, B = {B}, seed=2026_05_23_06")
print("=" * 80)

for f in folds:
    x = data[f]
    n = len(x)
    G1_hat, G2_hat = sample_moments(x)
    G1_boot, G2_boot = moving_block_bootstrap(x, L, B, rng)
    G1_boot = G1_boot[np.isfinite(G1_boot)]
    G2_boot = G2_boot[np.isfinite(G2_boot)]
    ci_G1 = (np.percentile(G1_boot, 5), np.percentile(G1_boot, 95))
    ci_G2 = (np.percentile(G2_boot, 5), np.percentile(G2_boot, 95))
    med_G1 = np.median(G1_boot)
    med_G2 = np.median(G2_boot)

    results[f] = {
        'n': n,
        'G1_hat': G1_hat, 'G2_hat': G2_hat,
        'G1_med': med_G1, 'G2_med': med_G2,
        'G1_ci': ci_G1, 'G2_ci': ci_G2,
        'B_valid_G1': len(G1_boot), 'B_valid_G2': len(G2_boot)
    }
    boot_dists[f'{f}_G1'] = G1_boot
    boot_dists[f'{f}_G2'] = G2_boot

    print(f"\n{f} (n={n}):")
    print(f"  γ₁ Joanes-Gill (point) = {G1_hat:+.4f}")
    print(f"  γ₁ bootstrap median   = {med_G1:+.4f}  CI90% = [{ci_G1[0]:+.4f}, {ci_G1[1]:+.4f}]")
    print(f"  γ₂_excess JG (point)  = {G2_hat:+.4f}")
    print(f"  γ₂ bootstrap median   = {med_G2:+.4f}  CI90% = [{ci_G2[0]:+.4f}, {ci_G2[1]:+.4f}]")
    print(f"  B valid: G1={len(G1_boot)} / G2={len(G2_boot)}")

# Salva
np.savez('task6_gamma_bootstrap.npz',
         **{f'{f}_G1_boot': boot_dists[f'{f}_G1'] for f in folds},
         **{f'{f}_G2_boot': boot_dists[f'{f}_G2'] for f in folds})

print("\n" + "=" * 80)
print("Saved task6_gamma_bootstrap.npz")
print("=" * 80)

# Cross-check con Task 5 mediani (sigillati in context)
# Task 5 boot mediani: F1 (−0.154, +0.568), F2 (+0.542, +1.041), F3 (+0.535, +2.285), Agg (+0.478, +5.653)
expected_t5 = {
    'F1': (-0.154, 0.568),
    'F2': (0.542, 1.041),
    'F3': (0.535, 2.285),
    'Agg': (0.478, 5.653),
}
print("\nCross-check vs Task 5 sigillati (mediane attese):")
print(f"{'Fold':6} {'γ₁ T5':>10} {'γ₁ T6':>10} {'Δ':>8}   {'γ₂ T5':>10} {'γ₂ T6':>10} {'Δ':>8}")
for f in folds:
    e1, e2 = expected_t5[f]
    m1, m2 = results[f]['G1_med'], results[f]['G2_med']
    print(f"{f:6} {e1:+10.4f} {m1:+10.4f} {m1-e1:+8.4f}   {e2:+10.4f} {m2:+10.4f} {m2-e2:+8.4f}")

# Tabella DSR-ready summary
print("\n" + "=" * 80)
print("Tabella DSR-ready (γ aggregato per Task 7):")
print("=" * 80)
print(f"{'Fold':6} {'γ₁ point':>10} {'γ₁ med':>10} {'γ₁ CI90% lo':>14} {'γ₁ CI90% hi':>14}  {'γ₂ point':>10} {'γ₂ med':>10} {'γ₂ CI90% lo':>14} {'γ₂ CI90% hi':>14}")
for f in folds:
    r = results[f]
    print(f"{f:6} {r['G1_hat']:+10.4f} {r['G1_med']:+10.4f} {r['G1_ci'][0]:+14.4f} {r['G1_ci'][1]:+14.4f}  {r['G2_hat']:+10.4f} {r['G2_med']:+10.4f} {r['G2_ci'][0]:+14.4f} {r['G2_ci'][1]:+14.4f}")
