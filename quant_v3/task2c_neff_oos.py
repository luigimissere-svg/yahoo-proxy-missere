"""Task 2c — Check qualitativo N_eff OOS.

Tre stime di N_eff per la DSR:
  N1 — nominale: 216 (72 trial × 3 fold)
  N2 — cluster OOS sharpe: # di valori OOS sharpe distinti
  N3 — trace-based (preview Task 4): N / (1 + (N-1) * rho_mean)

Per ora: focus su N2 e correlazione media delle equity OOS tra trial come preview.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

ROOT = Path('/tmp/yahoo-proxy-missere/quant_v3')
eq = pd.read_csv(ROOT / 'wf_full_v74_equity.csv')

oos = eq[eq.phase=='OOS'].copy()
oos.date = pd.to_datetime(oos.date)
print(f"OOS rows: {len(oos)}")
print(f"Trial OOS: {oos.trial_id.nunique()}")

# ── N2: cluster OOS sharpe distinti ──────────────────────
print("\n=== N_eff cluster (OOS sharpe distinti per fold) ===")
oos_sh = oos.groupby(['trial_id','fold_id']).first()['sharpe_a'].reset_index()
for f in [1,2,3]:
    s = oos_sh[oos_sh.fold_id==f].sharpe_a.round(4)
    n_u = s.nunique()
    print(f"  Fold {f}: {n_u} cluster unici / 72 trial")

# Cluster cross-fold (tuple di 3 sharpe)
pivot_oos = oos.groupby(['trial_id','fold_id']).first()['sharpe_a'].unstack()
pivot_oos.columns = [f'F{c}' for c in pivot_oos.columns]
pivot_oos_r = pivot_oos.round(4)
n_unique_tuples = pivot_oos_r.apply(tuple, axis=1).nunique()
print(f"\nCluster cross-fold OOS distinti: {n_unique_tuples} / 72 trial")

# ── Matrice correlazione equity OOS tra trial (preview Task 4) ──
# Per ciascun fold separatamente, costruisco la matrice 72x72 dei daily_return
# e calcolo correlazione media off-diagonale.
print("\n=== Correlazione equity OOS tra trial (preview Task 4) ===")
rhos = {}
for f in [1,2,3]:
    sub = oos[oos.fold_id==f].copy()
    # pivot: index=date, columns=trial_id, values=daily_return
    pv = sub.pivot_table(index='date', columns='trial_id', values='daily_return', aggfunc='first')
    pv = pv.fillna(0.0)
    # demean per trial
    pv_d = pv - pv.mean(axis=0)
    # correlazione
    C = pv_d.corr().values  # 72x72
    # off-diagonal
    mask = ~np.eye(C.shape[0], dtype=bool)
    off = C[mask]
    rho_mean = float(np.nanmean(off))
    rho_median = float(np.nanmedian(off))
    rho_std = float(np.nanstd(off))
    print(f"  Fold {f}: rho_mean={rho_mean:.4f}, median={rho_median:.4f}, std={rho_std:.4f}, "
          f"n_pairs={mask.sum()}")
    # N_eff trace-based: N / (1 + (N-1)*rho_mean)
    N = 72
    n_eff = N / (1 + (N-1) * max(rho_mean, 0.0))
    print(f"          N_eff_trace = {N} / (1 + 71 * {rho_mean:.4f}) = {n_eff:.2f}")
    rhos[f] = (rho_mean, n_eff)

# Aggregato cross-fold: concateno daily_return per fold e calcolo correlazione media
print("\n=== Cross-fold aggregato (216 trial-fold) ===")
# Costruisco vettore 216 di SR_hat OOS
sr_vec = pivot_oos.stack().reset_index()
sr_vec.columns = ['trial_id','fold_id','oos_sharpe']
print(f"SR vector: shape {sr_vec.shape}")
print(f"SR mean = {sr_vec.oos_sharpe.mean():.4f}, std = {sr_vec.oos_sharpe.std():.4f}, "
      f"median = {sr_vec.oos_sharpe.median():.4f}")
print(f"SR min = {sr_vec.oos_sharpe.min():.4f}, max = {sr_vec.oos_sharpe.max():.4f}")
print(f"SR positivi: {(sr_vec.oos_sharpe > 0).sum()} / 216 = {100*(sr_vec.oos_sharpe>0).sum()/216:.1f}%")
print(f"SR >= 1.0: {(sr_vec.oos_sharpe >= 1.0).sum()} / 216 = {100*(sr_vec.oos_sharpe>=1.0).sum()/216:.1f}%")
print(f"SR >= 2.0: {(sr_vec.oos_sharpe >= 2.0).sum()} / 216 = {100*(sr_vec.oos_sharpe>=2.0).sum()/216:.1f}%")
print(f"SR negativi: {(sr_vec.oos_sharpe < 0).sum()} / 216 = {100*(sr_vec.oos_sharpe<0).sum()/216:.1f}%")

print("\n=== Per fold OOS sharpe distribuzione ===")
for f in [1,2,3]:
    s = pivot_oos[f'F{f}']
    print(f"  F{f}: mean={s.mean():+.3f}, std={s.std():.3f}, min={s.min():+.3f}, max={s.max():+.3f}, "
          f"median={s.median():+.3f}, n_neg={(s<0).sum()}")

# Stima preliminare N_eff aggregato
rho_mean_avg = np.mean([rhos[f][0] for f in [1,2,3]])
N_agg = 216
n_eff_agg = N_agg / (1 + (N_agg-1) * max(rho_mean_avg, 0.0))
print(f"\nN_eff aggregato (preview): {N_agg} / (1 + 215 * {rho_mean_avg:.4f}) = {n_eff_agg:.2f}")
print(f"(Stima rough — Task 4 farà calcolo formale con Frobenius)")

# Salva tabella
sr_vec.to_csv(ROOT / 'task2c_sr_vec_oos.csv', index=False)
print(f"\nSR vector OOS salvato: {ROOT}/task2c_sr_vec_oos.csv")
