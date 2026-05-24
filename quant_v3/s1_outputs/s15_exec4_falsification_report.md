# S1.5 esec 4 — Report falsificazione H1-H4

**Timestamp**: 2026-05-24T11:01:28.961294+02:00
**Preregistration SHA**: `fa3b149a86bf10ed6b7011e9fca11026934d0c68c3c147f2df385a99302bec61`
**Diagnostica BUY pre-cap SHA**: `a82c8c1e2f633118db8a86214c0a3aa8c50160ddcbd3ec36b54c29ff0fe7d588`
**Grid**: GRID_S1_5_EXEC3 (6×3×2=36 combo)
**Universo**: portfolio (35 ticker)

## H1 — Non-degenerazione (≤25% trial con stat identiche, su trial validi)
- Esito: **FAIL**
- N trial OOS F2 totali: 36
- N trial invalidi (Sharpe NaN, portfolio flat): 12
- N trial validi: 24
- N degenerati (sui validi): 24 (100.0%)
- Coppie degenere: 28

## H2 — Monotonia ρ_AR(1) ~ mc (slope>0, p<0.10)
- Esito: **PASS**
- Slope: 0.2183
- p-value: 0.0000
- ρ medio per mc: {2: -0.013479784242874224, 3: 0.20478237174815395}

## H3 — Convergenza selettori (≥3/4)
- Esito: **PASS**
- N convergenti su 4: 3
- Signature più comune: `mc=2.0|thr=0.3|msp=NA`
- Signature per selettore: `['mc=2.0|thr=0.3|msp=NA', 'mc=2.0|thr=0.3|msp=NA', 'mc=2.0|thr=0.25|msp=NA', 'mc=2.0|thr=0.3|msp=NA']`
- Dettaglio selettori: `{'A_max_sharpe': {'trial_id': 31, 'mc': np.float64(2.0), 'thr': np.float64(0.3), 'msp': np.float64(nan)}, 'B_max_dsr': {'trial_id': 31, 'mc': np.float64(2.0), 'thr': np.float64(0.3), 'msp': np.float64(nan)}, 'C_min_abs_rho': {'trial_id': 25, 'mc': np.float64(2.0), 'thr': np.float64(0.25), 'msp': np.float64(nan)}, 'D_max_sharpe_rho_lt_010': {'trial_id': 31, 'mc': np.float64(2.0), 'thr': np.float64(0.3), 'msp': np.float64(nan)}}`

## H4 — Sharpe operativo Backtrader best_param F2 OOS ≥ 1.5
- Esito: **FAIL**
- Sharpe BT OOS: 1.0484706058316844
- Sharpe raw a OOS: 1.0468612869923135
- Best params: `{'mc': np.int64(3), 'thr': np.float64(0.3), 'msp': np.float64(nan)}`

## Verdetto complessivo: **FAIL**

Se PASS → procedere con leverage analysis.
Se FAIL su qualsiasi H → escalation S2 dedicata, NO unificazione con Bug 8.

— Generato automaticamente da `s15_exec4_falsification.py`, 2026-05-24T11:01:28.963059+02:00