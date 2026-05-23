# Task 2c — N_eff OOS (qualitativo, preview Task 4)

**Timestamp**: 23/05/2026 17:15 CEST
**Input**: `wf_full_v74_equity.csv` (216 OOS trial-fold, 65-67 bar ciascuno)
**Output**: `task2c_sr_vec_oos.csv` (vettore 216 di SR_hat OOS)

## Cluster OOS sharpe distinti (saturazione metrica out-of-sample)

| Fold | Cluster OOS unici / 72 |
|---|---|
| F1 | **3** |
| F2 | **8** |
| F3 | **4** |
| Cross-fold (tuple) | **8** / 72 trial |

Conferma e amplifica il pattern IS (8-11 cluster): in OOS i cluster sono ancora più pochi. La grid 72-cell esplora **8 strategie davvero distinte** quando proiettata cross-fold.

## Correlazione equity OOS tra trial (preview Task 4)

| Fold | ρ_mean off-diag | ρ_median | std ρ | N_eff trace-based (rough) |
|---|---|---|---|---|
| F1 | **0.936** | 0.874 | 0.063 | **1.07** |
| F2 | **0.928** | 0.872 | 0.065 | 1.08 |
| F3 | **0.833** | 0.678 | 0.161 | 1.20 |

Le equity OOS dei 72 trial sono **quasi identiche** come serie temporali (83-94% di correlazione). Non si stanno esplorando 72 strategie diverse — si sta esplorando **una strategia con 1-2 varianti**.

N_eff trace-based formula rough: N / (1 + (N-1) · ρ̄). Con ρ̄ ≈ 0.90, N_eff ≈ 1.1 (su 72). **Task 4 darà il calcolo formale via traccia della matrice di correlazione e Frobenius**, atteso N_eff intorno a 2-5 cross-fold dopo le correzioni.

## Distribuzione SR_hat OOS (216 trial-fold)

| Statistica | Valore |
|---|---|
| Mean | +2.273 |
| Median | +2.654 |
| Std | 1.308 |
| Min | −0.110 (F3 mc=2) |
| Max | +3.752 (F1 mc=2) |
| Positivi | **180 / 216 = 83.3%** |
| ≥ 1.0 | 180 / 216 = 83.3% (identico) |
| ≥ 2.0 | 144 / 216 = 66.7% |
| Negativi | 36 / 216 = 16.7% (tutti F3 mc=2) |

**Tutti i 36 negativi sono F3 mc=2.** È un **cluster strutturale** di failure, non rumore.

## Per fold OOS distribuzione

| Fold | Mean | Std | Min | Max | Median | n_neg |
|---|---|---|---|---|---|---|
| F1 | +3.173 | 0.583 | +2.576 | +3.752 | +3.191 | 0 |
| F2 | +3.056 | 0.162 | +2.678 | +3.289 | +3.070 | 0 |
| F3 | +0.591 | 0.711 | −0.110 | +1.452 | +0.547 | **36** |

F2 è eccezionalmente stable (std 0.16). F3 ha varianza maggiore e tutti i 36 negativi.

## Implicazione DSR

Con ρ̄ cross-fold ≈ 0.90, **N_eff trace-based ≈ 1.1**.

Questo NON è negativo per la DSR: significa che la **molteplicità delle scelte è molto bassa**. La penalizzazione Bailey-LdP per multiplicity sarà piccola. Il valore DSR sarà determinato prevalentemente da:

1. SR_hat aggregato: alto (+2.27 mean / +2.65 median)
2. T effettivo per fold (~65 bar): basso → SR_0 alto → penalizzazione
3. Curtosi/skew dei return (Task 6 con γ3/γ4)
4. Block bootstrap SR_0 (Task 5)

## Predizione DSR raffinata (post Task 2c)

Range probabile **[1.0, 1.8]** — più alto della predizione precedente [0.5, 1.5] perché:
- ρ̄ alto → multiplicity penalty bassa
- SR_hat mean alto (2.27)

Ma:
- T = 65 bar → SR_0 ~ 0.5-0.7 con bootstrap empirico
- F3 negativi tirano giù il median del bootstrap aggregato

Modale atteso: **DSR ~ 1.2-1.5**.

## Decisione

Procedo Task 3 — matrici C IS fold-locali + media + LW2017. Useremo:
- 72 × 65 daily_return per fold OOS come input
- Lo stesso schema (72 × ~260) per IS in fold locali
- Ledoit-Wolf 2017 shrinkage per stabilizzare con N=72 trial e T=65-260 bar
