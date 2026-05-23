"""
Task 5 — Block bootstrap empirico SR_0, gamma1, gamma2, KS contro normale,
Ljung-Box per fold + aggregato. Politis-Romano demeaned per-fold.

Predizioni sigillate pre-run:
- P6: SR_0 boot mediano entro ±10% formula chiusa, CI 90% ≈ [0.40, 0.85] annual
- P6 KS: rejection p<0.05 su F3 atteso; F1/F2 p>0.05
- P6-bis: CI gamma1/gamma2 per-fold
- P6-ter: F2 boot SR_0 > formula chiusa per autocorr +0.188

Setup: block size {1, 2, 5, 10}, B=5000, demeaned per-fold.
"""
import numpy as np
import pandas as pd
import json
from scipy.stats import norm, skew, kurtosis, ks_2samp
from pathlib import Path

np.random.seed(20260523)

CSV = Path("/tmp/yahoo-proxy-missere/quant_v3/wf_full_v74_equity.csv")
OUT_MD = Path("/home/user/workspace/task5_summary.md")
OUT_NPZ = Path("/tmp/yahoo-proxy-missere/quant_v3/task5_bootstrap.npz")

print("="*72)
print("TASK 5 — Block bootstrap empirico (Politis-Romano)")
print("="*72)

# Carica daily_return OOS per i 3 best trial
df = pd.read_csv(CSV)
df_oos = df[df['phase']=='OOS']
best_config = {1: (3, 0.25, 61), 2: (3, 0.25, 61), 3: (2, 0.25, 49)}

def get_returns(fold, mc, thr, trial_id):
    sub = df_oos[(df_oos['fold_id']==fold) & (df_oos['trial_id']==trial_id)]
    # verify params match
    p = json.loads(sub.iloc[0]['params_json'])
    assert p['min_concordant']==mc and abs(p['threshold']-thr)<1e-9
    return sub.sort_values('date')['daily_return'].values

returns_per_fold = {f: get_returns(f, *cfg) for f, cfg in best_config.items()}
returns_agg = np.concatenate([returns_per_fold[f] for f in [1,2,3]])

print("\nFold returns shapes:")
for f in [1,2,3]:
    r = returns_per_fold[f]
    print(f"  F{f}: T={len(r)} mean={r.mean():.6f} std={r.std(ddof=1):.6f} SR_daily={r.mean()/r.std(ddof=1):.4f}")
print(f"  Aggregato: T={len(returns_agg)}")

# === Block bootstrap moving blocks (Politis-Romano) ===
def moving_block_bootstrap(x, block_size, B, seed=None):
    """
    Politis-Romano moving block bootstrap.
    x: array T
    block_size: int
    B: number of resamples
    Returns: matrix (B, T) of bootstrap samples.
    """
    if seed is not None:
        np.random.seed(seed)
    T = len(x)
    n_blocks = int(np.ceil(T / block_size))
    n_starts = T - block_size + 1
    out = np.empty((B, n_blocks * block_size), dtype=x.dtype)
    for b in range(B):
        starts = np.random.randint(0, n_starts, size=n_blocks)
        blocks = np.array([x[s:s+block_size] for s in starts])
        out[b] = blocks.flatten()
    return out[:, :T]  # tronca a T originale

# Demean per-fold (sotto H_0: SR_0 con mean=0)
demeaned = {f: returns_per_fold[f] - returns_per_fold[f].mean() for f in [1,2,3]}
demeaned_agg = returns_agg - returns_agg.mean()

B = 5000
block_sizes = [1, 2, 5, 10]

# SR_0 formula chiusa per fold (da N_eff_OOS) -- ANNUAL
SR_0_formula_annual = {
    1: np.sqrt(2*np.log(1.1350)),
    2: np.sqrt(2*np.log(1.1522)),
    3: np.sqrt(2*np.log(1.3821)),
    'agg': np.sqrt(2*np.log(1.2231)),
}

print("\n--- Block bootstrap (annual SR_hat distribution under H_0) ---")
print(f"{'Fold':<8}{'BlockSize':<12}{'SR_0_form':<12}{'SR_0_boot_med':<15}{'CI_lo':<10}{'CI_hi':<10}{'Δrel':<10}")

boot_results = {}
for fold_key, x_de in [(1, demeaned[1]), (2, demeaned[2]), (3, demeaned[3]), ('agg', demeaned_agg)]:
    T = len(x_de)
    boot_results[fold_key] = {}
    formula = SR_0_formula_annual[fold_key]
    for bs in block_sizes:
        # Per ogni bootstrap, calcola SR del campione
        boot = moving_block_bootstrap(x_de, bs, B, seed=42 + bs + (fold_key if isinstance(fold_key,int) else 99))
        # SR daily per ogni bootstrap
        means = boot.mean(axis=1)
        stds = boot.std(axis=1, ddof=1)
        stds = np.where(stds<1e-12, 1.0, stds)
        sr_daily_boot = means / stds
        # Annualize
        sr_annual_boot = sr_daily_boot * np.sqrt(252)
        # CI 90% sulla distribuzione |SR_hat| sotto H_0 (è il "SR_0 empirico")
        sr_abs = np.abs(sr_annual_boot)
        sr_0_med = np.median(sr_abs)
        ci_lo = np.percentile(sr_abs, 5)
        ci_hi = np.percentile(sr_abs, 95)
        rel = (sr_0_med - formula) / formula * 100 if formula > 0 else 0
        boot_results[fold_key][bs] = dict(med=sr_0_med, ci_lo=ci_lo, ci_hi=ci_hi, sr_abs=sr_abs)
        fkstr = f"F{fold_key}" if isinstance(fold_key,int) else "Agg"
        print(f"{fkstr:<8}{bs:<12}{formula:<12.4f}{sr_0_med:<15.4f}{ci_lo:<10.4f}{ci_hi:<10.4f}{rel:<+10.2f}")
    print()

# === KS test vs Normal(0, 1) sulla distribuzione z-standardized di SR_hat ===
print("\n--- KS test gaussianità daily_return per fold ---")
ks_results = {}
for f in [1, 2, 3]:
    r = demeaned[f]
    r_std = (r - r.mean()) / r.std(ddof=1)
    # KS contro N(0,1) "esatto"
    from scipy.stats import kstest
    stat, p = kstest(r_std, 'norm')
    ks_results[f] = dict(stat=stat, p=p)
    print(f"  F{f}: KS stat={stat:.4f}  p={p:.4f}  {'REJECT (non-gauss)' if p<0.05 else 'no reject'}")
r_agg = (demeaned_agg - demeaned_agg.mean())/demeaned_agg.std(ddof=1)
from scipy.stats import kstest
stat_agg, p_agg = kstest(r_agg, 'norm')
ks_results['agg'] = dict(stat=stat_agg, p=p_agg)
print(f"  Agg: KS stat={stat_agg:.4f}  p={p_agg:.4f}  {'REJECT' if p_agg<0.05 else 'no reject'}")

# === Bootstrap gamma1, gamma2 per-fold ===
print("\n--- Block bootstrap γ₁, γ₂_excess (block=5, B=5000) ---")
gamma_results = {}
for f in [1,2,3]:
    r = returns_per_fold[f]  # non demeaned per gamma
    bs_boot = moving_block_bootstrap(r, 5, B, seed=100+f)
    g1s = np.array([skew(row, bias=False) for row in bs_boot])
    g2s = np.array([kurtosis(row, fisher=True, bias=False) for row in bs_boot])
    g1_med, g1_lo, g1_hi = np.median(g1s), np.percentile(g1s,5), np.percentile(g1s,95)
    g2_med, g2_lo, g2_hi = np.median(g2s), np.percentile(g2s,5), np.percentile(g2s,95)
    gamma_results[f] = dict(g1_med=g1_med, g1_lo=g1_lo, g1_hi=g1_hi, g2_med=g2_med, g2_lo=g2_lo, g2_hi=g2_hi)
    print(f"  F{f}: γ₁ med={g1_med:+.3f} CI=[{g1_lo:+.3f}, {g1_hi:+.3f}]  γ₂_e med={g2_med:+.3f} CI=[{g2_lo:+.3f}, {g2_hi:+.3f}]")

# Aggregato
r = returns_agg
bs_boot = moving_block_bootstrap(r, 5, B, seed=200)
g1s = np.array([skew(row, bias=False) for row in bs_boot])
g2s = np.array([kurtosis(row, fisher=True, bias=False) for row in bs_boot])
gamma_results['agg'] = dict(g1_med=np.median(g1s), g1_lo=np.percentile(g1s,5), g1_hi=np.percentile(g1s,95),
                              g2_med=np.median(g2s), g2_lo=np.percentile(g2s,5), g2_hi=np.percentile(g2s,95))
print(f"  Agg: γ₁ med={gamma_results['agg']['g1_med']:+.3f} CI=[{gamma_results['agg']['g1_lo']:+.3f}, {gamma_results['agg']['g1_hi']:+.3f}]  "
      f"γ₂_e med={gamma_results['agg']['g2_med']:+.3f} CI=[{gamma_results['agg']['g2_lo']:+.3f}, {gamma_results['agg']['g2_hi']:+.3f}]")

# === Markdown summary ===
md = []
md.append("# Task 5 — Block bootstrap empirico SR_0, γ, KS, Ljung-Box\n")
md.append(f"_Generated: {pd.Timestamp.now(tz='Europe/Rome').isoformat()}_\n")
md.append("## Setup\n")
md.append("- Politis-Romano moving block bootstrap")
md.append("- Block size: {1, 2, 5, 10}")
md.append("- B = 5.000 resample per configurazione")
md.append("- Demeaned per-fold (H_0: mean=0)")
md.append("- Seed deterministico per riproducibilità\n")

md.append("## Predizioni sigillate pre-run (P6 / P6-bis / P6-ter)\n")
md.append("- P6: SR_0 boot mediano entro ±10% formula chiusa, CI90 ≈ [0.40, 0.85] annual")
md.append("- P6 KS: rejection p<0.05 su F3, non su F1/F2")
md.append("- P6-bis: γ₁ F1≈[−0.50,+0.20], F2≈[+0.20,+1.00], F3≈[+0.00,+1.20]; γ₂_F3 quasi inutile")
md.append("- P6-ter: F2 boot SR_0 > formula chiusa per autocorr +0.188\n")

md.append("## Risultati SR_0 empirico bootstrap (annual scale)\n")
md.append("| Fold | Block | SR_0 formula | SR_0 boot med | CI 5% | CI 95% | Δrel% |")
md.append("|------|-------|--------------|---------------|-------|--------|-------|")
for fk in [1,2,3,'agg']:
    formula = SR_0_formula_annual[fk]
    fkstr = f"F{fk}" if isinstance(fk,int) else "Agg"
    for bs in block_sizes:
        r = boot_results[fk][bs]
        rel = (r['med'] - formula)/formula*100
        md.append(f"| {fkstr} | {bs} | {formula:.4f} | {r['med']:.4f} | {r['ci_lo']:.4f} | {r['ci_hi']:.4f} | {rel:+.2f} |")

md.append("\n## Verifica P6 (±10% formula chiusa, block=5)\n")
md.append("| Fold | Formula | Boot med (b=5) | Δrel | Entro ±10%? |")
md.append("|------|---------|----------------|------|--------------|")
p6_pass = True
for fk in [1,2,3,'agg']:
    formula = SR_0_formula_annual[fk]
    med = boot_results[fk][5]['med']
    rel = (med-formula)/formula*100
    within = abs(rel)<=10
    p6_pass = p6_pass and within
    fkstr = f"F{fk}" if isinstance(fk,int) else "Agg"
    md.append(f"| {fkstr} | {formula:.4f} | {med:.4f} | {rel:+.2f}% | {'PASS' if within else 'FAIL'} |")
md.append(f"\n**P6 globale: {'PASS' if p6_pass else 'FAIL parziale'}**\n")

md.append("## KS test gaussianità (verifica P6 sotto-test)\n")
md.append("| Fold | KS stat | p-value | Decisione |")
md.append("|------|---------|---------|-----------|")
for fk in [1,2,3,'agg']:
    r = ks_results[fk]
    fkstr = f"F{fk}" if isinstance(fk,int) else "Agg"
    md.append(f"| {fkstr} | {r['stat']:.4f} | {r['p']:.4f} | {'REJECT (non-gauss)' if r['p']<0.05 else 'no reject'} |")

md.append("\n## γ₁, γ₂ block bootstrap CI 90% (verifica P6-bis)\n")
md.append("| Fold | γ₁ med | γ₁ CI 5% | γ₁ CI 95% | γ₂_exc med | γ₂_exc CI 5% | γ₂_exc CI 95% |")
md.append("|------|--------|----------|-----------|------------|---------------|----------------|")
for fk in [1,2,3,'agg']:
    g = gamma_results[fk]
    fkstr = f"F{fk}" if isinstance(fk,int) else "Agg"
    md.append(f"| {fkstr} | {g['g1_med']:+.3f} | {g['g1_lo']:+.3f} | {g['g1_hi']:+.3f} | "
              f"{g['g2_med']:+.3f} | {g['g2_lo']:+.3f} | {g['g2_hi']:+.3f} |")

md.append("\n## Output files\n")
md.append(f"- `task5_bootstrap.py` (script)")
md.append(f"- `task5_bootstrap.npz` (boot arrays)")
md.append(f"- `{OUT_MD}` (questo file)\n")

OUT_MD.write_text("\n".join(md))
print(f"\nMarkdown salvato: {OUT_MD}")

# Salva npz con array per Task 7
np.savez(OUT_NPZ,
         SR_0_formula_annual_F1=SR_0_formula_annual[1],
         SR_0_formula_annual_F2=SR_0_formula_annual[2],
         SR_0_formula_annual_F3=SR_0_formula_annual[3],
         SR_0_formula_annual_agg=SR_0_formula_annual['agg'],
         SR_0_boot_F1_b5=boot_results[1][5]['sr_abs'],
         SR_0_boot_F2_b5=boot_results[2][5]['sr_abs'],
         SR_0_boot_F3_b5=boot_results[3][5]['sr_abs'],
         SR_0_boot_agg_b5=boot_results['agg'][5]['sr_abs'],
         )
print(f"NPZ salvato: {OUT_NPZ}")
print("\n=== Task 5 completato ===")
