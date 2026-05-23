# Quick check skew/kurtosis sui 3 best OOS (pre-Task 6)

**Timestamp**: 23/05/2026 17:05 CEST
**Obiettivo**: stimare γ1, γ2 per validare/smorzare predizione DSR

## Skew e kurtosis per fold (best param OOS)

| Fold | trial | mean (daily) | std (daily) | SR annual | γ1 (skew) | γ2 (excess kurt) | n bar |
|---|---|---|---|---|---|---|---|
| F1 | 61 (mc=3, thr=0.25) | +0.00110 | 0.00661 | **+2.65** | **−0.199** | +0.620 | 66 |
| F2 | 61 (mc=3, thr=0.25) | +0.00146 | 0.00758 | **+3.06** | **+0.594** | +1.086 | 65 |
| F3 | 49 (mc=2, thr=0.25) | −0.00011 | 0.01611 | **−0.11** | **+0.550** | +2.717 | 65 |

Sorpresa rispetto al letterario "momentum factor ha skew negativa":
- F1: skew leggermente negativa (−0.20), coerente
- F2 e F3: skew POSITIVA (+0.55 / +0.59) — la strategia vol-targeting limita i drawdown (cappa il rischio sui losing trade) mentre i winning trade corrono → distribution right-tailed

**Excess kurtosis bassa-moderata** (0.6 / 1.1 / 2.7) — fat tail presente ma non estrema.

## Aggregato concatenato (196 bar)

- mean = +0.00082, std = 0.01097
- γ1 aggregato = +0.484 (right-skew dominante per F2+F3)
- γ2 aggregato = +6.146 (effetto somma di tail F3 + F2)
- SR aggregato = +1.185 (sotto la media singoli perché F3 negativo dilui)

## Adjustment factor Bailey-LdP (preview Task 6)

Formula numeratore: `1 − γ1 · SR_per_period + γ2/4 · SR_per_period²`

Su scala daily aggregata: `1 − 0.484 · 0.0746 + 6.146/4 · 0.0746² ≈ 0.973`

**Correzione γ1/γ2 ≈ −2.7%** sull'SR_hat. **Predizione DSR resta nel range [1.0, 1.8]**.

## Decisione metodologica per Task 6

- Calcolo γ1 e γ2 **per fold**, non aggregato concatenato (l'aggregazione dilui F2/F3 positivi col F3 negativo)
- Block bootstrap con block_size {1, 5, 10} (Task 5) per CI 90% di γ3 = γ1 e γ4 = γ2
- Applicazione DSR per-fold + DSR aggregato come due output complementari

## Conclusione

Skew/kurtosis NON sono estremi. La predizione DSR [1.0, 1.8] non va smorzata.
Solo F3 ha kurt moderata (2.7) ma con n_bar = 65 piccolo la stima è rumorosa — CI bootstrap sarà ampio.
