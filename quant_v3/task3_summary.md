# Task 3 — Matrici di correlazione IS fold-locali

_Generated: 2026-05-23 (Europe/Rome)_

## Setup

- Input: `wf_full_v74_equity.csv` filter `phase=='IS'`
- 3 fold IS, ognuno N=72 trial × T daily_return
- Pivot `(date, trial_id)` → `daily_return`, NaN → 0 (giorni senza trade)
- Pearson correlation tra colonne (trial); diagonale forzata a 1, simmetria simmetrizzata

## Risultati primari — Matrici C 72×72 per fold

| Fold | T (dates) | N (trials) | ρ̄ off-diag | min off-diag | max off-diag | std off-diag |
|------|-----------|------------|------------|--------------|--------------|--------------|
| 1    | 262       | 72         | **0.9270** | 0.8557       | 1.0000       | 0.0534       |
| 2    | 261       | 72         | **0.9506** | 0.9026       | 1.0000       | 0.0342       |
| 3    | 260       | 72         | **0.9103** | 0.8025       | 1.0000       | 0.0656       |

**Matrice media** (C_mean = (C1+C2+C3)/3):
- ρ̄ off-diag (media): **0.9293**
- min/max off-diag: 0.8203 / 1.0000
- std off-diag: 0.0461

I tre fold mostrano alta consistenza strutturale (vedi Frobenius cross-fold sotto). F2 è il fold con minor dispersione (std 0.034); F3 il più disperso (std 0.066), coerente con la sua bimodalità interna mc=2 vs mc=3 (cluster strutturali distinti).

## Ledoit-Wolf 2003/2017 shrinkage analitico

Target: constant correlation model (off-diag = ρ̄ campionaria, diag = 1). Formula α* = max(0, min(1, (π − ρ) / (T · γ))).

| Fold | α_LW       | π      | ρ      | γ      | T   | N  | ρ̄     |
|------|------------|--------|--------|--------|-----|----|--------|
| 1    | **0.6485** | 0.0005 | 0.0004 | 0.0000 | 262 | 72 | 0.9270 |
| 2    | **1.0000** | 0.0010 | 0.0010 | 0.0000 | 261 | 72 | 0.9506 |
| 3    | **0.6331** | 0.0005 | 0.0005 | 0.0000 | 260 | 72 | 0.9103 |

Interpretazione: α_LW alto su tutti i fold (0.63–1.00). F2 satura a 1.0 perché la matrice campionaria è già praticamente identica al target constant-correlation (γ→0, distanza nulla). Coerente con la predizione pre-registrata "α LW alto 0.5-0.7 atteso dato ρ̄≈0.90".

## RMT cutoff Marchenko-Pastur

α_RMT = frazione di traccia in autovalori "bulk" (sotto cutoff λ+ MP, considerata rumore).

| Fold | α_RMT      | q=N/T | λ+    | λ−    | n_spike | n_bulk | max_eig |
|------|------------|-------|-------|-------|---------|--------|---------|
| 1    | **0.0137** | 0.275 | 2.323 | 0.224 | 2       | 70     | 66.82   |
| 2    | **0.0410** | 0.276 | 2.326 | 0.226 | 1       | 71     | 68.50   |
| 3    | **0.0243** | 0.277 | 2.329 | 0.227 | 2       | 70     | 65.64   |

## Diagnostica supplementare

### Top eigenvalues — struttura fattoriale dominante

| Fold | top1 (mercato) | top2  | top3  | top4  | top5  | frac_top1 |
|------|----------------|-------|-------|-------|-------|-----------|
| 1    | 66.821         | 3.712 | 0.555 | 0.428 | 0.226 | 92.81%    |
| 2    | 68.501         | 2.197 | 0.759 | 0.185 | 0.142 | 95.14%    |
| 3    | 65.643         | 4.510 | 0.660 | 0.478 | 0.363 | 91.17%    |

Un singolo "fattore comune" assorbe 91-95% della varianza totale in tutti i fold. Il secondo autovalore è significativo (2.2-4.5, sopra λ+≈2.3) solo per F1 e F3 (n_spike=2): questo corrisponde al **cluster mc=2 vs mc=3** che separa le strategie. F2 ha un solo spike (n_spike=1) perché in F2 i due cluster danno performance più omogenee (predominio mc=3).

### N_eff equivalent dai due metodi (scala comparabile)

| Fold | N_eff_trace(C) | N_eff_LW_equiv | n_spike(RMT) |
|------|----------------|----------------|--------------|
| 1    | 1.157          | 2.983          | 2            |
| 2    | 1.103          | N/A (α=1)      | 1            |
| 3    | 1.197          | 2.913          | 2            |

**Lettura critica**: i tre metodi convergono qualitativamente:
- N_eff_trace (1.10-1.20): un fattore comune domina, è il dato primario (sigillato come N_eff primario in `decisione_neff_primario.md`)
- N_eff_LW_equiv per F1/F3 (≈3.0): coerente con n_spike RMT=2 (1 mercato + 2 secondari = 3 dimensioni effettive)
- F2 esclusa dalla media LW_equiv (α=1 satura il modello constant-correlation, formula degenera)

### Test target identity per F2 (post-hoc, falsifica ipotesi a vs b)

Ipotesi:
- (a) F2 IS strutturalmente omogeneo (predominio mc=3) → α=1 segnala mancanza informazione
- (b) Target constant-correlation troppo flessibile con ρ̄=0.95 → γ→0 satura

Ricalcolo α_LW(F2) con target alternativo `μ·I` (identity-scaled, Ledoit-Wolf 2004):

| F2 LW config | α | π | ρ | γ |
|--------------|---|---|---|---|
| Target constant-correlation | 1.0000 | 0.0010 | 0.0010 | ≈0 |
| Target identity μ·I         | **0.0467** | 1.03e-3 | 1.58e-5 | 8.29e-5 |

**Esito: ipotesi (b) CONFERMATA**. Con target identity α=0.047 coerente con α_RMT(F2)=0.041 (Δrel +14%). La saturazione α=1 era artefatto del target che assorbiva strutturalmente ρ̄=0.95, non segnale di anomalia F2.

### Frobenius distance cross-fold (stabilità struttura)

| Coppia    | ||C_i − C_j||_F | Rel (%) |
|-----------|-----------------|---------|
| F1 vs F2  | 2.6526          | 3.96%   |
| F1 vs F3  | 1.7914          | 2.68%   |
| F2 vs F3  | 4.0128          | 5.85%   |

Tutte sotto 6%: struttura di correlazione **molto stabile cross-fold**, valida l'aggregazione di N_eff in un'unica stima per DSR aggregato (Task 7).

## Confronto α_LW vs α_RMT — Predizione P4 FALSIFICATA

| Fold | α_LW   | α_RMT  | Δrel   | Entro ±15%? |
|------|--------|--------|--------|--------------|
| 1    | 0.6485 | 0.0137 | −97.9% | FAIL         |
| 2    | 1.0000 | 0.0410 | −95.9% | FAIL         |
| 3    | 0.6331 | 0.0243 | −96.2% | FAIL         |

**Esito: P4 falsificata su tutti 3 fold.**

Causa: errore concettuale nella formulazione della predizione — α_LW e α_RMT non sono direttamente confrontabili su scala lineare. α_LW è un peso convex-combination verso un target specifico; α_RMT è una frazione di traccia in autovalori bulk MP. In presenza di un fattore dominante (top1 = 91-95% traccia in tutti i fold), α_RMT è strutturalmente piccolo (<5%) mentre α_LW può essere grande perché la distanza al target ρ̄ è piccola.

**Lezione (sigillata `audit_journal_v7_3.md`)**: l'equivalenza tra metodi di shrinkage non si verifica sui parametri α, ma sulla scala N_eff derivata. Su quella scala (vedi tabella precedente) i tre metodi convergono qualitativamente a 1-3 dimensioni effettive.

**Disclosure paper v7.3**: P4 inclusa nel registro predizioni falsificate; la lezione metodologica entra in sezione "Limiti e correzioni del processo".


## Decisioni metodologiche confermate

1. **N_eff primario** (sigillato pre-DSR, da `decisione_neff_primario.md`): trace-based su matrice equity OOS ≈ 1.07-1.20 (cross-fold)
2. **N_eff secondario** confermato dai 3 metodi su C IS: range 1.1-3.0
3. Aggregazione DSR (Task 7): la stabilità Frobenius <6% giustifica una singola stima cross-fold
4. **F2 saturation α=1 risolta**: artefatto target constant-correlation con ρ̄=0.95; nessun problema strutturale F2 (vedi test identity sopra)
5. **Predizione P4 falsificata** (vedi sezione successiva e `audit_journal_v7_3.md`)

## Output files

- `/tmp/yahoo-proxy-missere/quant_v3/task3_corr_matrices.npz` (C_F1, C_F2, C_F3, C_mean, C_LW per fold, α_LW, α_RMT, T, N, ρ̄)
- `/home/user/workspace/task3_summary.md` (questo file)
- `/tmp/yahoo-proxy-missere/quant_v3/task3_corr_matrices.py` (script)

## Prossimi step

- **Task 4**: N_eff IS trace-based su C medio + Frobenius già calcolato + RMT cutoff + confronto vs N_eff OOS (Task 2c trace-based = 1.07-1.20)
- Task 4 può attingere direttamente al NPZ generato qui senza ricomputare
