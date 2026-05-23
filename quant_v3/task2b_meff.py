"""Task 2b — M_eff: numero di trial validi su tutti 3 fold IS.

Definizione M_eff (Bailey-LdP convention adattata):
  M_eff = # trial che hanno IS sharpe > 0 (o sopra una soglia) su TUTTI i 3 fold IS.
  Variante più stringente: # trial con IS sharpe consistente cross-fold (std intra-trial bassa).

Output:
  - Tabella 72 × 3 di IS sharpe (trial × fold)
  - Flag valid_all_folds (IS > 0 su 3/3 fold)
  - Flag valid_robust (IS > soglia_robusta su 3/3 fold)
  - M_eff scalare con due definizioni
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

ROOT = Path('/tmp/yahoo-proxy-missere/quant_v3')
eq = pd.read_csv(ROOT / 'wf_full_v74_equity.csv')

def parse_p(j):
    try: return json.loads(j)
    except: return {}

# Estraggo IS sharpe per ogni (trial, fold)
is_data = eq[eq.phase=='IS'].groupby(['trial_id','fold_id']).first().reset_index()
print(f"IS data rows: {len(is_data)} (atteso 72*3=216)")

# Pivot
pivot = is_data.pivot(index='trial_id', columns='fold_id', values='sharpe_a')
pivot.columns = [f'F{c}_IS_sharpe' for c in pivot.columns]
print(f"\nPivot shape: {pivot.shape}")

# Aggiungo params per leggibilità
params_per_trial = is_data.groupby('trial_id').first()['params_json'].apply(parse_p)
pivot['mc'] = params_per_trial.apply(lambda p: p.get('min_concordant'))
pivot['thr'] = params_per_trial.apply(lambda p: p.get('threshold'))
pivot['tr'] = params_per_trial.apply(lambda p: p.get('target_risk_pct'))
pivot['sc'] = params_per_trial.apply(lambda p: p.get('max_sector_pct'))
pivot['mpb'] = params_per_trial.apply(lambda p: p.get('max_portfolio_beta'))

# Statistiche cross-fold per trial
sh_cols = ['F1_IS_sharpe','F2_IS_sharpe','F3_IS_sharpe']
pivot['IS_min'] = pivot[sh_cols].min(axis=1)
pivot['IS_max'] = pivot[sh_cols].max(axis=1)
pivot['IS_mean'] = pivot[sh_cols].mean(axis=1)
pivot['IS_std'] = pivot[sh_cols].std(axis=1)

# Flag valid: IS sharpe > 0 su 3/3 fold
pivot['valid_all_folds'] = (pivot[sh_cols] > 0).all(axis=1)

# Flag robust: IS sharpe >= 0.5 su 3/3 fold (soglia min_trades equivalent)
pivot['valid_robust_05'] = (pivot[sh_cols] >= 0.5).all(axis=1)

# Flag stringente: IS sharpe >= 1.0 su 3/3 fold
pivot['valid_robust_10'] = (pivot[sh_cols] >= 1.0).all(axis=1)

# Min_trades equivalente: tutti i 72 trial hanno trades>=min_trades?
# (min_trades = 8 da config v74). Verifico
is_trades = eq[eq.phase=='IS'].groupby(['trial_id','fold_id']).first().reset_index()
# tradiamo n_nonzero come proxy del trade count? No, è giorni con return non-zero
# n_bars vs n_nonzero non distingue trade. Usiamo solo sharpe.

print("\n=== Tabella M_eff: 72 trial × 3 fold IS ===")
print(pivot[sh_cols + ['IS_min','IS_max','IS_mean','IS_std','valid_all_folds','valid_robust_05','valid_robust_10']].to_string())

print("\n=== M_eff scalare ===")
print(f"M_eff (IS>0 su 3/3 fold):       {pivot.valid_all_folds.sum()} / 72 = {100*pivot.valid_all_folds.sum()/72:.1f}%")
print(f"M_eff (IS>=0.5 su 3/3 fold):    {pivot.valid_robust_05.sum()} / 72 = {100*pivot.valid_robust_05.sum()/72:.1f}%")
print(f"M_eff (IS>=1.0 su 3/3 fold):    {pivot.valid_robust_10.sum()} / 72 = {100*pivot.valid_robust_10.sum()/72:.1f}%")

print("\n=== Top 10 trial per IS_mean (cross-fold) ===")
top = pivot.sort_values('IS_mean', ascending=False).head(10)
print(top[sh_cols + ['IS_mean','IS_std','mc','thr','tr','sc','mpb','valid_all_folds']].to_string())

print("\n=== Distribuzione per mc (split principale) ===")
for mc_val in sorted(pivot.mc.unique()):
    sub = pivot[pivot.mc == mc_val]
    print(f"\nmc={mc_val}: N={len(sub)}")
    print(f"  F1 IS sharpe mean: {sub.F1_IS_sharpe.mean():.4f} (std {sub.F1_IS_sharpe.std():.4f})")
    print(f"  F2 IS sharpe mean: {sub.F2_IS_sharpe.mean():.4f} (std {sub.F2_IS_sharpe.std():.4f})")
    print(f"  F3 IS sharpe mean: {sub.F3_IS_sharpe.mean():.4f} (std {sub.F3_IS_sharpe.std():.4f})")
    print(f"  N validi all_folds: {sub.valid_all_folds.sum()}/{len(sub)}")
    print(f"  N validi >=1.0: {sub.valid_robust_10.sum()}/{len(sub)}")

# Salva CSV
out = ROOT / 'task2b_meff_table.csv'
pivot.reset_index().to_csv(out, index=False)
print(f"\nTabella salvata: {out}")
