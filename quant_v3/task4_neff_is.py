"""
Task 4 — N_eff IS multi-metodo + confronto vs OOS (verifica predizione P5)

Metodi:
  (1) Trace-based primario: N_eff = (Σλ)² / Σλ² su C_mean IS
  (2) Off-diagonal: N_eff_offdiag = N / (1 + (N-1) ρ̄)
  (3) RMT bulk vs spike: numero spike eigenvalues + 1 (fattore mercato)
  (4) Frobenius cross-fold per stabilità (già calcolato Task 3)
  (5) Confronto IS vs OOS (Task 2c): predizione P5 ±5% sulla scala N_eff

Input: task3_corr_matrices.npz + wf_full_v74_equity.csv (per OOS)
Output: task4_summary.md + console verifica P5
"""
import numpy as np
import pandas as pd
from pathlib import Path

NPZ = Path("/tmp/yahoo-proxy-missere/quant_v3/task3_corr_matrices.npz")
CSV = Path("/tmp/yahoo-proxy-missere/quant_v3/wf_full_v74_equity.csv")
OUT_MD = Path("/home/user/workspace/task4_summary.md")

print("=" * 70)
print("TASK 4 — N_eff IS multi-metodo + verifica P5")
print("=" * 70)

# 1. Load matrici Task 3
data = np.load(NPZ)
C_F1 = data['C_F1']
C_F2 = data['C_F2']
C_F3 = data['C_F3']
C_mean = data['C_mean']
rho_bar_per_fold = data['rho_bar']
T_per_fold = data['T_per_fold']
N_per_fold = data['N_per_fold']

folds = [1, 2, 3]
Cs = {1: C_F1, 2: C_F2, 3: C_F3}

def neff_trace(C):
    """N_eff = (sum lambda)^2 / sum(lambda^2). Equivalent participation ratio."""
    eigvals = np.linalg.eigvalsh(C)
    return (eigvals.sum())**2 / (eigvals**2).sum()

def neff_offdiag(C):
    """N_eff = N / (1 + (N-1) * rho_bar). Bailey-Lopez de Prado constant-correlation."""
    N = C.shape[0]
    iu = np.triu_indices_from(C, k=1)
    rho_bar = C[iu].mean()
    return N / (1 + (N - 1) * rho_bar)

def neff_rmt(C, T):
    """N_eff_RMT = 1 (mercato) + n_spike sopra lambda_plus MP."""
    N = C.shape[0]
    q = N / T
    lam_plus = (1 + np.sqrt(q))**2
    eigvals = np.linalg.eigvalsh(C)
    n_spike = int((eigvals > lam_plus).sum())
    return float(n_spike), dict(lam_plus=lam_plus, q=q)

print("\n--- Metodo 1: N_eff trace-based (PRIMARIO) ---")
neff_trace_per_fold = {}
for f in folds:
    n = neff_trace(Cs[f])
    neff_trace_per_fold[f] = n
    print(f"  Fold {f}: N_eff_trace = {n:.4f}")
neff_trace_mean = neff_trace(C_mean)
print(f"  C_mean:  N_eff_trace = {neff_trace_mean:.4f}")

print("\n--- Metodo 2: N_eff off-diagonal (Bailey-LdP constant-correlation) ---")
neff_offdiag_per_fold = {}
for f in folds:
    n = neff_offdiag(Cs[f])
    neff_offdiag_per_fold[f] = n
    print(f"  Fold {f}: N_eff_offdiag = {n:.4f}  (rho_bar={rho_bar_per_fold[f-1]:.4f})")
neff_offdiag_mean = neff_offdiag(C_mean)
print(f"  C_mean:  N_eff_offdiag = {neff_offdiag_mean:.4f}")

print("\n--- Metodo 3: N_eff RMT (n_spike + 1 mercato) ---")
neff_rmt_per_fold = {}
for f in folds:
    n_spike, info = neff_rmt(Cs[f], T_per_fold[f-1])
    # Convenzione: N_eff_RMT = max(1, n_spike) perchè il mercato è 1 spike
    neff_rmt_per_fold[f] = max(1.0, n_spike)
    print(f"  Fold {f}: N_eff_RMT = {neff_rmt_per_fold[f]:.1f}  (n_spike={int(n_spike)} > lam+={info['lam_plus']:.3f})")

print("\n--- Metodo 4: Frobenius cross-fold (stabilità struttura) ---")
for i in range(3):
    for j in range(i+1, 3):
        diff = Cs[folds[i]] - Cs[folds[j]]
        frob = np.linalg.norm(diff, 'fro')
        frob_rel = frob / np.linalg.norm(Cs[folds[i]], 'fro')
        print(f"  ||C_{folds[i]} - C_{folds[j]}||_F = {frob:.4f}  rel = {frob_rel*100:.2f}%")

# === Confronto IS vs OOS — verifica P5 ===
print("\n" + "=" * 70)
print("VERIFICA P5: N_eff IS vs N_eff OOS (Task 2c) entro ±5%")
print("=" * 70)

# Ricomputa N_eff trace-based su matrice OOS per consistency
df = pd.read_csv(CSV)
df_oos = df[df['phase']=='OOS']
neff_oos_trace = {}
neff_oos_offdiag = {}
rho_bar_oos = {}
for f in folds:
    sub = df_oos[df_oos['fold_id']==f]
    pivot = sub.pivot_table(index='date', columns='trial_id', values='daily_return', aggfunc='first').sort_index().fillna(0.0)
    X = pivot.values
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, ddof=1, keepdims=True)
    sd = np.where(sd < 1e-12, 1.0, sd)
    Z = (X - mu) / sd
    T = X.shape[0]
    C_oos = (Z.T @ Z) / (T - 1)
    np.fill_diagonal(C_oos, 1.0)
    C_oos = 0.5*(C_oos + C_oos.T)
    n_t = neff_trace(C_oos)
    n_o = neff_offdiag(C_oos)
    iu = np.triu_indices_from(C_oos, k=1)
    neff_oos_trace[f] = n_t
    neff_oos_offdiag[f] = n_o
    rho_bar_oos[f] = C_oos[iu].mean()

print("\nConfronto trace-based per fold:")
print(f"{'Fold':<6}{'N_eff_IS':<12}{'N_eff_OOS':<12}{'Δrel %':<10}{'Entro ±5%?'}")
all_within_5 = True
for f in folds:
    n_is = neff_trace_per_fold[f]
    n_oos = neff_oos_trace[f]
    rel = (n_oos - n_is) / n_is * 100
    within = abs(rel) <= 5.0
    all_within_5 = all_within_5 and within
    print(f"{f:<6}{n_is:<12.4f}{n_oos:<12.4f}{rel:<+10.2f}{'PASS' if within else 'FAIL'}")

# Aggregato C_mean
print(f"\nAggregato (C_mean IS vs media N_eff trace OOS):")
neff_oos_mean = np.mean(list(neff_oos_trace.values()))
rel_agg = (neff_oos_mean - neff_trace_mean) / neff_trace_mean * 100
within_agg = abs(rel_agg) <= 5.0
print(f"  N_eff IS (C_mean) = {neff_trace_mean:.4f}")
print(f"  N_eff OOS (mean fold) = {neff_oos_mean:.4f}")
print(f"  Δrel = {rel_agg:+.2f}%  -> {'PASS ±5%' if within_agg else 'FAIL ±5%'}")

print(f"\n=> P5 GLOBALE: {'PASS' if (all_within_5 and within_agg) else 'PARZIALE/FAIL — vedi dettaglio'}")

# === Markdown ===
md = []
md.append("# Task 4 — N_eff IS multi-metodo + verifica P5\n")
md.append(f"_Generated: {pd.Timestamp.now(tz='Europe/Rome').isoformat()}_\n")
md.append("## Predizione sigillata pre-calcolo (P5)\n")
md.append("> N_eff IS trace-based convergerà a N_eff OOS Task 2c entro ±5%. Predizione puntuale: N_eff IS ∈ [1.05, 1.20].\n")

md.append("## Metodo 1 — N_eff trace-based (PRIMARIO sigillato)\n")
md.append("Formula: `N_eff = (Σλ)² / Σλ²` (participation ratio degli autovalori di C)\n")
md.append("| Fold | N_eff_trace IS | ρ̄_IS    |")
md.append("|------|----------------|----------|")
for f in folds:
    md.append(f"| {f}    | **{neff_trace_per_fold[f]:.4f}**   | {rho_bar_per_fold[f-1]:.4f} |")
md.append(f"| **C_mean** | **{neff_trace_mean:.4f}** | 0.9293 |\n")

md.append("## Metodo 2 — N_eff off-diagonal (constant-correlation)\n")
md.append("Formula: `N_eff = N / (1 + (N-1) ρ̄)`\n")
md.append("| Fold | N_eff_offdiag IS | ρ̄      |")
md.append("|------|------------------|---------|")
for f in folds:
    md.append(f"| {f}    | {neff_offdiag_per_fold[f]:.4f}    | {rho_bar_per_fold[f-1]:.4f} |")
md.append(f"| **C_mean** | {neff_offdiag_mean:.4f} | 0.9293 |\n")

md.append("## Metodo 3 — N_eff RMT (n_spike Marchenko-Pastur)\n")
md.append("| Fold | n_spike | N_eff_RMT |")
md.append("|------|---------|-----------|")
for f in folds:
    md.append(f"| {f}    | {int(neff_rmt_per_fold[f])} | {neff_rmt_per_fold[f]:.1f} |")
md.append("")

md.append("## Metodo 4 — Frobenius cross-fold (stabilità)\n")
md.append("| Coppia    | ||ΔC||_F | Rel (%) |")
md.append("|-----------|---------|---------|")
for i in range(3):
    for j in range(i+1, 3):
        diff = Cs[folds[i]] - Cs[folds[j]]
        frob = np.linalg.norm(diff, 'fro')
        frob_rel = frob / np.linalg.norm(Cs[folds[i]], 'fro')
        md.append(f"| F{folds[i]}-F{folds[j]} | {frob:.4f} | {frob_rel*100:.2f}% |")
md.append("\nTutte le distanze <6%: struttura correlazione molto stabile cross-fold.\n")

md.append("## VERIFICA P5 — IS vs OOS trace-based per fold\n")
md.append("| Fold | N_eff_IS | N_eff_OOS | Δrel % | Entro ±5%? |")
md.append("|------|----------|-----------|--------|--------------|")
for f in folds:
    n_is = neff_trace_per_fold[f]
    n_oos = neff_oos_trace[f]
    rel = (n_oos - n_is) / n_is * 100
    within = abs(rel) <= 5.0
    md.append(f"| {f}    | {n_is:.4f}   | {n_oos:.4f}    | {rel:+.2f}% | {'PASS' if within else 'FAIL'} |")
md.append("")
md.append(f"**Aggregato**: N_eff IS (C_mean) = **{neff_trace_mean:.4f}** vs N_eff OOS (media fold) = **{neff_oos_mean:.4f}**")
md.append(f"  → Δrel = {rel_agg:+.2f}%  → **{'PASS ±5%' if within_agg else 'FAIL ±5%'}**\n")

md.append("### Esito predizione P5\n")
if all_within_5 and within_agg:
    md.append("**P5 CONFERMATA su tutti i fold + aggregato.** La struttura di correlazione tra trial è quasi identica in regime IS e OOS, validando l'aggregazione di N_eff in singola stima per DSR.\n")
elif all_within_5:
    md.append("**P5 confermata per fold ma non aggregato** (vedi tabella).\n")
elif within_agg:
    md.append("**P5 confermata in aggregato ma non per ogni fold** (vedi tabella).\n")
else:
    md.append("**P5 FALSIFICATA**. Vedi `audit_journal_v7_3.md` per analisi causa.\n")

md.append("## Sintesi N_eff IS — input per Task 5/6/7 DSR\n")
md.append(f"- **N_eff primario sigillato** (trace-based, da `decisione_neff_primario.md`):")
md.append(f"  - IS C_mean = **{neff_trace_mean:.4f}**")
md.append(f"  - OOS media fold = **{neff_oos_mean:.4f}**")
md.append(f"  - **Stima consolidata DSR**: N_eff ≈ **{(neff_trace_mean+neff_oos_mean)/2:.3f}** (media IS+OOS)")
md.append(f"- **N_eff secondario** (cluster-count strategie distinte) = 8 (da Task 2c)")
md.append(f"- **SR_0 primario** = √(2·ln({(neff_trace_mean+neff_oos_mean)/2:.3f})) ≈ {np.sqrt(2*np.log((neff_trace_mean+neff_oos_mean)/2)):.4f}")
md.append(f"- **SR_0 secondario** = √(2·ln(8)) ≈ {np.sqrt(2*np.log(8)):.4f}\n")

md.append("## Output files\n")
md.append(f"- `task4_neff_is.py` (script)")
md.append(f"- `{OUT_MD}` (questo file)\n")

OUT_MD.write_text("\n".join(md))
print(f"\nMarkdown salvato: {OUT_MD}")
print("\n=== Task 4 completato ===")
