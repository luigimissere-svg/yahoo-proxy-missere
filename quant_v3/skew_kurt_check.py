"""Quick check skew/kurtosis sui 3 best OOS — input per Task 6 e calibrazione DSR."""
import pandas as pd
import numpy as np
from scipy import stats
import json
from pathlib import Path

ROOT = Path('/tmp/yahoo-proxy-missere/quant_v3')
eq = pd.read_csv(ROOT / 'wf_full_v74_equity.csv')

def parse_p(j):
    try: return json.loads(j)
    except: return {}

# Da wf_full_v74.csv: best params per fold
res = pd.read_csv(ROOT / 'wf_full_v74.csv')
best_params_per_fold = {}
for _, row in res.iterrows():
    f = int(row['fold_id'])
    best_params_per_fold[f] = dict(
        threshold=row.param_threshold,
        min_concordant=row.param_min_concordant,
        target_risk_pct=row.param_target_risk_pct,
        max_sector_pct=row.param_max_sector_pct if pd.notna(row.param_max_sector_pct) else None,
        max_portfolio_beta=row.param_max_portfolio_beta if pd.notna(row.param_max_portfolio_beta) else None,
    )

print("Best params per fold:")
for f, p in best_params_per_fold.items():
    print(f"  F{f}: {p}")

# Per ciascun fold, trova il trial OOS che matcha i best params
oos = eq[eq.phase=='OOS'].copy()

def match_trial(fold, params_target):
    sub = oos[oos.fold_id==fold]
    for tid, g in sub.groupby('trial_id'):
        p = parse_p(g.params_json.iloc[0])
        # Match minimo: threshold + min_concordant + sc + mpb
        match = (
            p.get('threshold') == params_target['threshold']
            and p.get('min_concordant') == params_target['min_concordant']
            and p.get('target_risk_pct') == params_target['target_risk_pct']
        )
        # Gestione None vs nan
        ts = params_target.get('max_sector_pct')
        ps = p.get('max_sector_pct')
        match = match and ((ts is None and ps is None) or ts == ps)
        tm = params_target.get('max_portfolio_beta')
        pm = p.get('max_portfolio_beta')
        match = match and ((tm is None and pm is None) or tm == pm)
        if match:
            return tid, g
    return None, None

print("\n=== Skew/Kurtosis daily returns OOS (3 best trial) ===")
print(f"{'Fold':<6}{'trial':<8}{'mean':>10}{'std':>10}{'sharpe':>10}{'skew γ1':>10}{'kurt γ2':>10}{'n':>5}")
print("─" * 70)

dr_per_fold = {}
for f in [1,2,3]:
    tid, g = match_trial(f, best_params_per_fold[f])
    if g is None:
        print(f"F{f}: NO MATCH")
        continue
    dr = g.daily_return.astype(float).values
    dr_nz = dr[dr != 0.0]  # non-zero returns
    mean = dr.mean()
    std = dr.std()
    sh = mean/std * np.sqrt(252) if std > 0 else 0
    skew = stats.skew(dr)
    kurt = stats.kurtosis(dr, fisher=True)  # excess kurtosis (γ2 - 3)
    print(f"F{f:<5}{tid:<8}{mean:>+10.5f}{std:>10.5f}{sh:>+10.3f}{skew:>+10.3f}{kurt:>+10.3f}{len(dr):>5}")
    dr_per_fold[f] = dr

# Test aggregato: concateno i 3 fold come distribuzione aggregata daily return
print("\n=== Aggregato 3 best concatenati ===")
dr_agg = np.concatenate([dr_per_fold[f] for f in [1,2,3]])
print(f"N agg = {len(dr_agg)}")
print(f"mean = {dr_agg.mean():+.5f}, std = {dr_agg.std():.5f}")
print(f"skew γ1 = {stats.skew(dr_agg):+.3f}")
print(f"kurt γ2 (excess) = {stats.kurtosis(dr_agg, fisher=True):+.3f}")

# Implicazione Bailey-LdP
sr_hat = dr_agg.mean()/dr_agg.std() * np.sqrt(252)
print(f"\nSR_hat aggregato = {sr_hat:+.3f}")

# Bailey-LdP probabilistic Sharpe ratio adjustment factor
# numeratore correzione: 1 - γ1 * SR/√T + (γ2/4) * SR²/T
g1 = stats.skew(dr_agg)
g2 = stats.kurtosis(dr_agg, fisher=True)
T = len(dr_agg)
SR_annual = sr_hat
SR_per_period = SR_annual / np.sqrt(252)  # SR su scala daily
# Adjustment factor (approssimazione di numeratore DSR)
num = 1 - g1 * SR_per_period + (g2 / 4.0) * SR_per_period**2
print(f"γ1 (skew) = {g1:+.3f}")
print(f"γ2 (excess kurt) = {g2:+.3f}")
print(f"T (n bar agg) = {T}")
print(f"SR daily = {SR_per_period:+.5f}")
print(f"Adjustment numerator (1 − γ1·SR + γ2/4·SR²) = {num:.4f}")
print(f"  → impatto su SR_hat per DSR: × {num:.4f}")
print(f"  → SR_hat corretto ≈ {sr_hat * num:+.3f}")

# Test rumore numerico
if abs(num - 1) < 0.05:
    print("  Correzione minima (<5%): predizione DSR resta nel range proposto")
elif num < 0.7:
    print("  CORREZIONE SIGNIFICATIVA (<70%): smorzare la predizione DSR")
elif num > 1.3:
    print("  CORREZIONE POSITIVA: la predizione DSR può salire")
else:
    print(f"  Correzione moderata ({(num-1)*100:+.1f}%): predizione DSR leggermente modificata")
