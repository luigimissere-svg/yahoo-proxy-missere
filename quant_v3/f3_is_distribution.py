"""Distribuzione completa Sharpe IS F3 — grid vs metric saturation diagnostic."""
import pandas as pd
import numpy as np
import json
from pathlib import Path

ROOT = Path('/tmp/yahoo-proxy-missere/quant_v3')
eq = pd.read_csv(ROOT / 'wf_full_v74_equity.csv')

def parse_p(j):
    try: return json.loads(j)
    except: return {}

print("=" * 70)
print("Distribuzione IS Sharpe F3 — 72 trial completi")
print("=" * 70)

# F3 IS - prendi sharpe_a per ogni trial
f3_is = eq[(eq.fold_id==3) & (eq.phase=='IS')].copy()
trials_f3 = f3_is.groupby('trial_id').first()[['sharpe_a','params_json']].reset_index()
trials_f3['params'] = trials_f3.params_json.apply(parse_p)
trials_f3['mc'] = trials_f3.params.apply(lambda p: p.get('min_concordant'))
trials_f3['thr'] = trials_f3.params.apply(lambda p: p.get('threshold'))
trials_f3['tr'] = trials_f3.params.apply(lambda p: p.get('target_risk_pct'))
trials_f3['sc'] = trials_f3.params.apply(lambda p: p.get('max_sector_pct'))
trials_f3['mpb'] = trials_f3.params.apply(lambda p: p.get('max_portfolio_beta'))

print(f"\nN trial: {len(trials_f3)}")
print(f"Sharpe IS min: {trials_f3.sharpe_a.min():.4f}")
print(f"Sharpe IS max: {trials_f3.sharpe_a.max():.4f}")
print(f"Sharpe IS mean: {trials_f3.sharpe_a.mean():.4f}")
print(f"Sharpe IS std: {trials_f3.sharpe_a.std():.4f}")

# Distribuzione ordinata
sorted_sh = trials_f3.sort_values('sharpe_a', ascending=False).reset_index(drop=True)
print("\n=== Distribuzione completa Sharpe IS F3 (decrescente) ===")
print(f"{'rank':>4} {'sh':>8} {'mc':>3} {'thr':>5} {'tr':>6} {'sc':>5} {'mpb':>5}")
for i, r in sorted_sh.iterrows():
    print(f"{i+1:>4} {r.sharpe_a:>+8.4f} {r.mc:>3} {r.thr:>5} {r.tr:>6} {str(r.sc):>5} {str(r.mpb):>5}")

# Conta valori unici
print("\n=== Valori unici Sharpe IS F3 ===")
unique = sorted_sh.sharpe_a.round(6).value_counts().sort_index(ascending=False)
for v, c in unique.items():
    print(f"  Sharpe={v:+.4f}: {c} trial")

# Diagnosi grid vs metric
n_unique = sorted_sh.sharpe_a.round(4).nunique()
top5 = sorted_sh.head(5).sharpe_a.values
top_plateau = (top5.std() < 0.0001)

print("\n=== DIAGNOSI ===")
print(f"Valori unici a 4 decimali: {n_unique}/72")
print(f"Top 5 plateau (std<1e-4): {top_plateau}")
if n_unique <= 20:
    print(">>> METRICA: Sharpe IS satura — pochi valori distinti, strategy binaria")
    print("    Implicazione v8: nuovo selettore con penalty per varianza, NON solo grid finer")
else:
    print(">>> GRID: Sharpe IS variabile — molti valori distinti, top piattezza locale")
    print("    Implicazione v8: grid finer scioglierebbe il plateau")

# Confronto con F1, F2 per validare conclusione
print("\n=== Confronto F1 e F2 ===")
for f in [1, 2]:
    f_is = eq[(eq.fold_id==f) & (eq.phase=='IS')].copy()
    t_f = f_is.groupby('trial_id').first()['sharpe_a']
    n_u = t_f.round(4).nunique()
    print(f"Fold {f}: {len(t_f)} trial, {n_u} valori unici Sharpe IS (4 dec)")
    print(f"   Top 5 valori: {sorted(t_f.round(4).values, reverse=True)[:5]}")
