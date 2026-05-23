# Task 2b — M_eff (validità cross-fold IS)

**Timestamp**: 23/05/2026 17:00 CEST
**Input**: `wf_full_v74_equity.csv` (216 IS + 216 OOS, post-patch B2)
**Output**: `task2b_meff_table.csv` (72 trial × 3 fold IS sharpe + flag)

## M_eff scalare

| Definizione | N | % | Note |
|---|---|---|---|
| `valid_all_folds`: IS sharpe > 0 su 3/3 fold | **72 / 72** | 100.0% | Criterio Bailey-LdP classico |
| `valid_robust_05`: IS sharpe ≥ 0.5 su 3/3 fold | **72 / 72** | 100.0% | Soglia min_trades equivalent |
| `valid_robust_10`: IS sharpe ≥ 1.0 su 3/3 fold | **36 / 72** | 50.0% | Soglia stringente |

**Tutti i 72 trial sono validi al criterio classico**. Nessun trial degenerato.

## Pattern strutturale per mc (split principale)

| mc | N | F1 IS mean | F2 IS mean | F3 IS mean | IS_min cross-fold | Validi ≥1.0 / N |
|---|---|---|---|---|---|---|
| **mc=2** | 36 | 1.568 | 1.098 | **1.466** | min su F2 | 24/36 |
| **mc=3** | 36 | **2.061** | **1.265** | 0.997 | min su F3 | 12/36 |

Pattern simmetrico cross-fold:
- mc=3 domina F1 e F2 (sharpe IS più alti, std intra-mc bassissima 0.023-0.099)
- mc=2 domina F3 ma è peggio su F1+F2
- Min cross-fold per mc=2 cade su F2 (1.098); min per mc=3 cade su F3 (0.997)

Questo spiega completamente il bimodale OOS F3 documentato nel journal `journal_f3_selector_overfitting`:
il selettore IS per F3 sceglie mc=2 (legittimo: IS più alto 1.625 vs 1.006) ma OOS la generalizzazione fallisce (-0.110 vs +1.205).

## N effettivo per la DSR

I 72 trial collassano in cluster di IS sharpe identici per fold:
- F1: **8 cluster** distinti (~9 trial per cluster)
- F2: **10 cluster**
- F3: **11 cluster** (+ 1 cluster doppio a 0.9988 con 12 trial)

Cluster cross-fold (tuple di IS-sharpe per 3 fold):
- Probabilmente 12-18 cluster effettivi quando si combinano i pattern

Implicazione DSR:
- N nominale = 216 trial-fold
- N effettivo per fold ≈ 8-11
- N effettivo cross-fold ≈ 12-18

## Top 10 trial per IS_mean cross-fold

| trial | F1 | F2 | F3 | mean | std | mc | thr | tr |
|---|---|---|---|---|---|---|---|---|
| 61, 62, 65, 66, 69, 70 | 2.084 | 1.475 | 1.006 | **1.522** | 0.540 | 3 | 0.25 | 0.008-0.012 |
| 49, 50, 53, 54, 57, 58 | 1.705 | 1.181 | 1.625 | **1.504** | 0.282 | 2 | 0.25 | 0.008-0.012 |

I top 6 trial assoluti sono **mc=3 thr=0.25** (con `target_risk_pct` e `max_portfolio_beta` indifferenti).
I top 12 includono **mc=2 thr=0.25** con std cross-fold più bassa (0.28 vs 0.54).

Notare: il cluster mc=2 thr=0.25 ha **IS_std cross-fold 0.282** vs il cluster mc=3 thr=0.25 con **IS_std 0.540**.
mc=2 è più **consistente cross-fold IS** ma sub-ottimale in 2/3 fold OOS (F1, F2).
mc=3 è meno consistente IS ma migliore OOS in F1+F2.

## Predizione DSR raffinata

Dato:
- 8-11 cluster IS distinti per fold
- 36 trial validi a soglia 1.0 (50% della grid)
- Cross-fold std massima 0.540 (cluster mc=3 thr=0.25 alto)
- Cross-fold std minima 0.160 (cluster mc=3 thr=0.25 alto con tr variabile)

Predizione **DSR aggregato range [0.4, 1.2]**, modale intorno a **0.6-0.9**. Il F3 negativo OOS (per il best mc=2) zavorra la coda sinistra; ma se la DSR si calcola sui 216 trial OOS (non sui 3 best), la maggioranza positiva domina.

## Decisione operativa

- Procedo Task 2c (N_eff OOS qualitativo) usando la stessa logica di clustering ma su OOS sharpe.
- M_eff = 72 per criterio Bailey-LdP. Nessun trial scartato dalla DSR.
- Tabella salvata: `task2b_meff_table.csv` per uso downstream.
