# S1.5 esec 3 — Report falsificazione H1-H4

**Timestamp**: 2026-05-24T07:39:46.069736+02:00
**Preregistration SHA**: `a2790d3c7ee73b355314e9699c9d7e2194312e3b50d3d7f0bb6ae3a091e00ecc`
**Addendum 01 universo SHA**: `0bbca3a90499b56f0c008c83d9e3bb2b0c4ad2a617e3d469f259726019edd0c3`
**Grid**: GRID_S1_5_EXEC3 (6×3×2=36 combo)
**Universo**: portfolio (35 ticker)

## H1 — Non-degenerazione (≤25% trial con stat identiche, su trial validi)
- Esito: **FAIL**
- N trial OOS F2 totali: 36
- N trial invalidi (Sharpe NaN, portfolio flat): 12
- N trial validi: 24
- N degenerati (sui validi): 24 (100.0%)
- Coppie degenere: 76

## H2 — Monotonia ρ_AR(1) ~ mc (slope>0, p<0.10)
- Esito: **PASS**
- Slope: 0.3331
- p-value: 0.0000
- ρ medio per mc: {2: -0.07980513446942562, 3: 0.2533023292695484}

## H3 — Convergenza selettori (≥3/4)
- Esito: **PASS**
- N convergenti su 4: 4
- Signature più comune: `mc=2.0|thr=0.05|msp=NA`
- Signature per selettore: `['mc=2.0|thr=0.05|msp=NA', 'mc=2.0|thr=0.05|msp=NA', 'mc=2.0|thr=0.05|msp=NA', 'mc=2.0|thr=0.05|msp=NA']`
- Dettaglio selettori: `{'A_max_sharpe': {'trial_id': 1, 'mc': np.float64(2.0), 'thr': np.float64(0.05), 'msp': np.float64(nan)}, 'B_max_dsr': {'trial_id': 1, 'mc': np.float64(2.0), 'thr': np.float64(0.05), 'msp': np.float64(nan)}, 'C_min_abs_rho': {'trial_id': 1, 'mc': np.float64(2.0), 'thr': np.float64(0.05), 'msp': np.float64(nan)}, 'D_max_sharpe_rho_lt_010': {'trial_id': 1, 'mc': np.float64(2.0), 'thr': np.float64(0.05), 'msp': np.float64(nan)}}`

## H4 — Sharpe operativo Backtrader best_param F2 OOS ≥ 1.5
- Esito: **PASS**
- Sharpe BT OOS: 1.9444541787871563
- Sharpe raw a OOS: 1.9414695965539397
- Best params: `{'mc': np.int64(2), 'thr': np.float64(0.25), 'msp': np.float64(nan)}`

## Verdetto complessivo: **FAIL**

Se PASS → procedere con leverage analysis.
Se FAIL su qualsiasi H → escalation S2 dedicata, NO unificazione con Bug 8.

— Generato automaticamente da `s15_exec3_falsification.py`, 2026-05-24T07:39:46.072339+02:00