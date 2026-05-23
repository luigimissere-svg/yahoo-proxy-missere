# Journal full run B2 patchato — esito

**Timestamp**: 23/05/2026 16:09 CEST
**Commit**: 6e80001 (branch patch/b2-bugs-2-4-5-7)
**Comando**: `python -m engine.wf_runner --grid full --output-csv wf_full_v74.csv --stability-json wf_full_v74_stability.json --save-equity-csv wf_full_v74_equity.csv --save-trades-csv wf_full_v74_trades.csv`
**Runtime**: ~2h (12:15 → 14:09)
**Esito**: PASS — stop condition rispettata, patch confermata matematicamente

## Stop condition (verifica >10%)
- OOS trial totali: 216 (72 × 3 fold)
- n_nonzero_returns == 0: **0/216 (0.0%)** — pass
- |pnl_pct| < 1e-9:        **0/216 (0.0%)** — pass

## Main pipeline (3 best param OOS)

| Fold | IS sh | OOS sh | OOS pnl% | trades | degr | overfit | best param |
|---|---|---|---|---|---|---|---|
| F1 (ago-nov 2025) | +2.084 | **+2.631** | +7.40 | 10 | 1.26 | False | thr=0.25, mc=3, sc=None |
| F2 (nov 2025-feb 2026) | +1.475 | **+3.033** | +9.74 | 10 | 2.06 | False | thr=0.25, mc=3, sc=None |
| F3 (feb-mag 2026) | +1.625 | **−0.110** | −1.56 | 10 | −0.07 | **True** | thr=0.25, mc=2, sc=None |

OOS Sharpe medio: **+1.851** (stable_threshold=3)
stable_params: threshold=0.25, target_risk_pct=0.008, max_sector_pct=None, max_portfolio_beta=None
min_concordant: 3 stabile su 2/3 fold (F1+F2); F3 sceglie mc=2 (overfit flag)

## Distribuzione OOS (72 trial per fold)

| Fold | mean | std | min | max | n_trades=0 |
|---|---|---|---|---|---|
| F1 | +3.173 | 0.583 | +2.576 | +3.752 | 0 |
| F2 | +3.056 | 0.162 | +2.678 | +3.289 | 0 |
| F3 | +0.591 | 0.711 | −0.110 | +1.452 | 0 |

F3 bimodalità confermata: mc=2 → cluster ~−0.11, mc=3 → cluster ~+1.21.

## HHI_pnl_post (best param OOS, 10 trade open_at_end)

| Fold | HHI | N_eff | pnl tot abs (€) | top trade | top pnl |
|---|---|---|---|---|---|
| F1 | 0.1698 | 5.89 | 12 205 | MU +37.5% | 3 722 € |
| F2 | 0.2363 | 4.23 | 15 852 | MU +61.7% | **6 967 €** |
| F3 | 0.1267 | 7.89 | 12 980 | PRY +24.6% | 2 500 € |

F2 il più concentrato (1 trade = 44% del pnl assoluto), F3 il più diversificato.

## Conferma matematica patch Bug 2 (warmup contamination)

Per ogni fold, ricalcolo: `sharpe_a_post ≈ sharpe_bt × √((n_bars_oos + warmup) / n_bars_oos)`
con warmup = 250 bar (SMA200 minperiod + 50 explicit), n_bars_oos = 65-66.
Boost factor atteso: √(316/66) ≈ 2.19.

| Fold | sharpe_bt (con warmup) | × boost (2.19-2.20) | atteso | sharpe_a osservato | Δ |
|---|---|---|---|---|---|
| F1 | +1.178 | 2.188 | +2.577 | +2.631 | +0.054 |
| F2 | +1.345 | 2.201 | +2.961 | +3.033 | +0.072 |
| F3 | −0.050 | 2.201 | −0.109 | −0.110 | −0.001 |

Coerenza eccellente su F3 (Δ=0.001) e buona su F1/F2 (residuo da n_nonzero_returns ≠ n_bars).
**Patch matematicamente verificata in tutti i 3 fold.**

## n_carryover_pre (pre-patch wf_full_v73_trades.csv)

| Fold | trades | NaT dt_open (Bug 4) | dt_open < oos_start (carry-over reale) |
|---|---|---|---|
| F1 | 10 | 10 | 0 |
| F2 | 10 | 10 | 0 |
| F3 | 12 | 10 | **2** ← MU/REP.MC pre-roll |

Conferma audit A.0-A.3: solo F3 aveva carry-over autentici (2 trade pre-roll su MU + REP.MC che hanno catturato +37%/+46% pre-fold). Bug 5 (gate `current_date < fold_start_dt`) li ha azzerati nel post-patch.

## Confronto pre/post patch (best param per fold)

| Fold | metric | PRE (v73) | POST (v74) | Δ |
|---|---|---|---|---|
| F1 | OOS sharpe | n/a | +2.631 | — |
| F1 | OOS pnl% | n/a | +7.40 | — |
| F2 | OOS sharpe | +1.941 | **+3.033** | +1.09 |
| F2 | OOS pnl% | n/a | +9.74 | — |
| F3 | OOS sharpe | +0.658 | **−0.110** | −0.77 |
| F3 | OOS pnl% | +7.54 | **−1.56** | **−9.10** |

F2 +1.09 sharpe = effetto warmup contamination puro (no carry-over).
F3 −9.10 pnl% = effetto carry-over MU/REP.MC/PRY rimosso (allineato a stima audit: 3 trade × ~+45% × notional ~10k = ~+13k = ~+13% sul cash 100k → contributo reale rimosso ~7-9% sul pnl OOS dopo netting).

## Decisione
- Patch B2 validata su tutti i 3 fold (matematica + falsificabili pre-reg)
- Narrazione paper v7.3 aggiornata: F3 OOS pulito **−1.56% (sharpe −0.11)**, F2 OOS pulito **+9.74% (sharpe +3.03)**
- min_concordant=2 sceglie F3 ma con overfit flag → da considerare nella DSR
- Procedere con Task 2b (M_eff = trial ok su tutti 3 fold IS)
