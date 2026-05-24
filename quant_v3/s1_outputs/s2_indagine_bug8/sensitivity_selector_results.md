# Sensitivity selettore Bug 8 — Robustness check S2

**Data:** 2026-05-24 06:35 CEST
**Seed bootstrap:** 20260524
**B bootstrap:** 10000
**Serie analizzata:** F2 OOS, T=65, 8 trial grid smoke v8 rerun (commit 63d9be3)

## Tabella stats per trial

| Trial | mc | thr | msp | Sharpe_a | ρ_AR(1) | \|ρ\| | DSR | PnL % |
|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 0.15 | nan | +4.3887 | -0.0798 | 0.0798 | 0.9751 | +20.45 |
| 2 | 2 | 0.15 | 0.3 | +4.3887 | -0.0798 | 0.0798 | 0.9751 | +20.45 |
| 3 | 3 | 0.15 | nan | +1.8451 | +0.2841 | 0.2841 | 0.7275 | +4.92 |
| 4 | 3 | 0.15 | 0.3 | +1.8451 | +0.2841 | 0.2841 | 0.7275 | +4.92 |
| 5 | 2 | 0.25 | nan | +4.3887 | -0.0798 | 0.0798 | 0.9751 | +20.45 |
| 6 | 2 | 0.25 | 0.3 | +4.3887 | -0.0798 | 0.0798 | 0.9751 | +20.45 |
| 7 | 3 | 0.25 | nan | +1.6103 | +0.2474 | 0.2474 | 0.6864 | +4.14 |
| 8 | 3 | 0.25 | 0.3 | +1.6103 | +0.2474 | 0.2474 | 0.6864 | +4.14 |

## Esito 4 selettori

| Selettore | Trial | mc | thr | Sharpe_a | ρ_AR(1) | DSR | PnL % |
|---|---|---|---|---|---|---|---|
| A_max_sharpe | 1 | 2 | 0.15 | +4.3887 | -0.0798 | 0.9751 | +20.45 |
| B_max_DSR | 1 | 2 | 0.15 | +4.3887 | -0.0798 | 0.9751 | +20.45 |
| C_min_abs_rho | 1 | 2 | 0.15 | +4.3887 | -0.0798 | 0.9751 | +20.45 |
| D_max_sharpe_constr_rho | 1 | 2 | 0.15 | +4.3887 | -0.0798 | 0.9751 | +20.45 |

**Best_param distinti emersi:** [(2, np.float64(0.15))]
→ **SELEZIONE ROBUSTA**: tutti i selettori convergono.

## IC bootstrap Δ Sharpe trial 5 (mc=2) − trial 7 (mc=3)

- Sharpe_a trial 5 (mc=2): **+4.3887**
- Sharpe_a trial 7 (mc=3): **+1.6103**
- Δ osservato: **+2.7784**

### Bootstrap i.i.d.

- IC 95%: **[-0.5166, +5.9532]**
- Contiene zero: **True**
- p-value bilatero: **0.0956**

### Block bootstrap L=5 (Politis-Romano)

- IC 95%: **[-0.6363, +6.6746]**
- Contiene zero: **True**
- p-value bilatero: **0.1196**

## Verdetto

L'IC 95% Δ Sharpe (mc=2 − mc=3) **contiene zero** in entrambi i bootstrap.
La preferenza mc=2 vs mc=3 **NON è statisticamente significativa** al 95%.
Conferma la fragilità della selezione max-Sharpe (Δ = 0.03 entro noise).
