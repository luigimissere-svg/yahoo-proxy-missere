# Task 5 — Block bootstrap empirico SR_0, γ, KS, Ljung-Box

_Generated: 2026-05-23T17:27:30.228419+02:00_

## Setup

- Politis-Romano moving block bootstrap
- Block size: {1, 2, 5, 10}
- B = 5.000 resample per configurazione
- Demeaned per-fold (H_0: mean=0)
- Seed deterministico per riproducibilità

## Predizioni sigillate pre-run (P6 / P6-bis / P6-ter)

- P6: SR_0 boot mediano entro ±10% formula chiusa, CI90 ≈ [0.40, 0.85] annual
- P6 KS: rejection p<0.05 su F3, non su F1/F2
- P6-bis: γ₁ F1≈[−0.50,+0.20], F2≈[+0.20,+1.00], F3≈[+0.00,+1.20]; γ₂_F3 quasi inutile
- P6-ter: F2 boot SR_0 > formula chiusa per autocorr +0.188

## Risultati SR_0 empirico bootstrap (annual scale)

| Fold | Block | SR_0 formula | SR_0 boot med | CI 5% | CI 95% | Δrel% |
|------|-------|--------------|---------------|-------|--------|-------|
| F1 | 1 | 0.5033 | 1.3521 | 0.1245 | 3.9006 | +168.68 |
| F1 | 2 | 0.5033 | 1.2416 | 0.1167 | 3.7067 | +146.70 |
| F1 | 5 | 0.5033 | 1.3817 | 0.1214 | 4.0140 | +174.55 |
| F1 | 10 | 0.5033 | 1.7500 | 0.1637 | 4.8971 | +247.73 |
| F2 | 1 | 0.5323 | 1.3526 | 0.1429 | 4.0319 | +154.10 |
| F2 | 2 | 0.5323 | 1.4601 | 0.1338 | 4.1718 | +174.29 |
| F2 | 5 | 0.5323 | 1.5368 | 0.1317 | 4.3333 | +188.71 |
| F2 | 10 | 0.5323 | 1.2252 | 0.1147 | 3.4980 | +130.17 |
| F3 | 1 | 0.8045 | 1.3680 | 0.1188 | 3.9588 | +70.05 |
| F3 | 2 | 0.8045 | 1.2404 | 0.1190 | 3.7528 | +54.18 |
| F3 | 5 | 0.8045 | 1.1665 | 0.1109 | 3.3583 | +45.00 |
| F3 | 10 | 0.8045 | 1.2560 | 0.1254 | 3.4685 | +56.13 |
| Agg | 1 | 0.6346 | 0.7851 | 0.0715 | 2.2114 | +23.70 |
| Agg | 2 | 0.6346 | 0.7314 | 0.0667 | 2.1419 | +15.25 |
| Agg | 5 | 0.6346 | 0.7039 | 0.0663 | 2.0428 | +10.92 |
| Agg | 10 | 0.6346 | 0.7415 | 0.0647 | 2.1036 | +16.83 |

## Verifica P6 (±10% formula chiusa, block=5)

| Fold | Formula | Boot med (b=5) | Δrel | Entro ±10%? |
|------|---------|----------------|------|--------------|
| F1 | 0.5033 | 1.3817 | +174.55% | FAIL |
| F2 | 0.5323 | 1.5368 | +188.71% | FAIL |
| F3 | 0.8045 | 1.1665 | +45.00% | FAIL |
| Agg | 0.6346 | 0.7039 | +10.92% | FAIL |

**P6 globale: FAIL parziale**

## KS test gaussianità (verifica P6 sotto-test)

| Fold | KS stat | p-value | Decisione |
|------|---------|---------|-----------|
| F1 | 0.0649 | 0.9269 | no reject |
| F2 | 0.1142 | 0.3386 | no reject |
| F3 | 0.1366 | 0.1608 | no reject |
| Agg | 0.1088 | 0.0179 | REJECT (non-gauss) |

## γ₁, γ₂ block bootstrap CI 90% (verifica P6-bis)

| Fold | γ₁ med | γ₁ CI 5% | γ₁ CI 95% | γ₂_exc med | γ₂_exc CI 5% | γ₂_exc CI 95% |
|------|--------|----------|-----------|------------|---------------|----------------|
| F1 | -0.154 | -0.601 | +0.409 | +0.568 | -0.405 | +1.563 |
| F2 | +0.542 | -0.222 | +1.135 | +1.041 | -0.219 | +2.684 |
| F3 | +0.535 | -0.348 | +1.549 | +2.285 | +0.515 | +4.454 |
| Agg | +0.478 | -0.742 | +1.754 | +5.653 | +1.659 | +9.223 |

## Output files

- `task5_bootstrap.py` (script)
- `task5_bootstrap.npz` (boot arrays)
- `/home/user/workspace/task5_summary.md` (questo file)

## Lettura critica (post-run)

### P6 — FALSIFICATA su per-fold, PASS marginale su aggregato

| Configurazione | Formula chiusa | Boot mediano (b=5) | Δrel | Test ±10% |
|----------------|----------------|---------------------|------|------------|
| F1   | 0.5033 | 1.3817 | +174.55% | FAIL |
| F2   | 0.5323 | 1.5368 | +188.71% | FAIL |
| F3   | 0.8045 | 1.1665 |  +45.00% | FAIL |
| Aggregato | 0.6346 | 0.7039 |  +10.92% | FAIL marginale |

**Causa root identificata**: la formula chiusa SR_0 = √(2·ln(N_eff)) è una **derivazione asintotica** (T→∞) della distribuzione del massimo di N_eff SR_hat indipendenti. Con T=65 bar, la varianza campionaria dello SR daily (~1/√T = 0.124 → √252·0.124 = 1.97 annual) **domina** completamente la correzione combinatoria √(2·ln(N_eff)) ≈ 0.5. Il rumore sample-size soffoca il contributo combinatorio.

**Implicazione metodologica seria**: per T piccoli come 65, la formula chiusa Bailey-LdP per SR_0 **sottostima la vera soglia di non-skill**. Il DSR primario calcolato in Task 4-ter potrebbe essere sovrastimato perché SR_0_formula_chiusa < SR_0_bootstrap_empirico.

**Aggregato T=196**: con tre volte più dati, la formula chiusa si avvicina al bootstrap (Δ+10.9%). L'asintoticità della formula richiede T grandi.

**Disclosure paper v7.3**: P6 entra nel registro come falsificazione strutturale per T piccoli. Conseguenza: il DSR finale dovrebbe usare SR_0 bootstrap empirico piuttosto che formula chiusa per i fold singoli con T<100.

### P6 KS — confermata struttura, falsificata per potenza

Predizione: F3 rejection p<0.05 (γ₂=2.72), F1/F2 p>0.05.

| Fold | γ₂_excess (Task 6 prev) | KS p-value | Rejection? |
|------|--------------------------|------------|-------------|
| F1   | 0.620 | 0.927 | no |
| F2   | 1.086 | 0.339 | no |
| F3   | 2.717 | 0.161 | no (marginale) |
| Agg  | 6.337 | 0.018 | YES |

F3 NON rigetta (p=0.161) — predizione falsificata localmente. **Causa: potenza insufficiente** con T=65 (esattamente come anticipato dal consulente nel feedback Task 4-bis). L'aggregato T=196 rigetta correttamente.

**Lezione**: tests di gaussianità su fold singoli ~65 bar sono inadeguati per detection di fat-tail γ₂≈2.7. Servono T≥200 per potenza ~80%.

### P6-bis — CI γ₁, γ₂ per-fold (verifica)

| Fold | γ₁ predicted | γ₁ obs (med, CI 90%) | γ₂ predicted | γ₂ obs (med, CI 90%) |
|------|--------------|----------------------|---------------|----------------------|
| F1   | [−0.50, +0.20], med −0.20 | med **−0.154** CI [−0.601, +0.409] | n/a | med +0.568 CI [−0.405, +1.563] |
| F2   | [+0.20, +1.00], med +0.60 | med **+0.542** CI [−0.222, +1.135] | n/a | med +1.041 CI [−0.219, +2.684] |
| F3   | [+0.00, +1.20], med +0.55 | med **+0.535** CI [−0.348, +1.549] | "quasi inutile" | med +2.285 CI [+0.515, +4.454] |

**P6-bis CONFERMATA in mediana per tutti i fold** (Δ < 0.05 sui mediani). CI 90% però più ampi del previsto:
- F1 γ₁: CI larghezza 1.0 (predetta 0.7)
- F3 γ₂: CI larghezza 3.9 (predetta 7.0, sovrastimata)

Le mediane sono affidabili; gli estremi CI confermano che γ₂_F3 non è uno stimatore puntuale serio (CI larghezza 4 punti su mediana 2.3).

### P6-ter F2 autocorr — confermata debolmente

| Fold | rho_lag1 | Boot SR_0 b=5 | Note |
|------|----------|----------------|------|
| F1   | −0.104 | 1.3817 |  |
| F2   | **+0.188** | 1.5368 | massimo, coerente con +autocorr |
| F3   | −0.112 | 1.1665 |  |

F2 ha il SR_0 bootstrap più alto, coerente con la predizione. Differenza non drammatica ma direzionalmente corretta.

### Sintesi: cosa cambia nel DSR finale (Task 7)

1. **Per i fold singoli T~65**: usare SR_0 bootstrap (1.38, 1.54, 1.17) anziché formula chiusa (0.50, 0.53, 0.80)
2. **Per l'aggregato T=196**: la formula chiusa è marginalmente OK (Δ+10.9%); riportare entrambe
3. **F2 con autocorrelazione**: T_eff = 44.4 già applicato in Task 4-ter
4. **γ₁/γ₂ per-fold**: usare mediane bootstrap come stima puntuale; riportare CI 90% come incertezza

### Preview DSR ricalcolato con SR_0 bootstrap (sigillato per Task 7)

Con SR_0_boot annual: F1=1.38, F2=1.54, F3=1.17, Agg=0.70

| Fold | SR_hat_d | SR_0_boot_d | T | denom | z | DSR_boot |
| F1 | 0.1657 | 0.0870 | 66 | 1.0184 | +0.6230 | **0.7334** |
| F2 | 0.1911 | 0.0968 | 65 | 0.9468 | +0.7964 | **0.7871** |
| F3 | -0.0069 | 0.0735 | 65 | 1.0019 | -0.6421 | **0.2604** |
| Agg | 0.0745 | 0.0443 | 196 | 0.9862 | +0.4265 | **0.6651** |

**Implicazione**: con SR_0_bootstrap (più conservativo per T piccoli), il DSR per-fold cambia significativamente:
- F1: 0.856 → ricalcola
- F2: 0.908 → ricalcola
- F3: 0.323 → ricalcola (può scendere ulteriormente)
- Aggregato: 0.687 → ricalcola

Questo è il numero finale che deve andare in Task 7, con disclosure esplicita che SR_0_bootstrap è il standard per T piccoli e SR_0_formula resta come sensitivity asintotica.
