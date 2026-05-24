# Indagine S2 Bug 8 — Chiusura come SUPERATO da v8

**Data chiusura:** 2026-05-24 06:35 CEST
**Branch:** `feature/v8-s1-refactor`
**Decisione committente:** Bug 8 → SUPERATO da v8 (NON artefatto di calcolo, NON falso positivo)

## Verdetto

Bug 8 sealed v7.3 (ρ_AR(1) F2 OOS = +0.1883, Q(10) = 20.374, p = 0.0259) è **riproducibile al sesto decimale** sulla serie originale `task6_returns.npz['F2']`. Il fenomeno è reale ma **condizionato** sul best_param v7.4 F2 = (min_concordant=3, threshold=0.25). La build v8 post-patch bug 2/4/5/7 seleziona best_param F2 = (min_concordant=2, threshold=0.25), su cui F2 è mean-reverting (ρ_AR(1) = −0.08).

**ρ_AR(1) F2 OOS è funzione monotona di `min_concordant`:**

| min_concordant | regime | ρ_AR(1) | trial v8 rerun |
|---|---|---|---|
| 2 | mean-reverting | −0.0798 | 1, 2, 5, 6 |
| 3 (thr=0.15) | autocorrelato + | +0.2841 | 3, 4 |
| 3 (thr=0.25) | autocorrelato + | +0.2474 | 7, 8 |
| 3 (thr=0.25) sealed v7.4 | autocorrelato + | **+0.1883** | sealed |

Pearson trial 7 v8 vs sealed v7.4: **+0.8411**. Riproducibilità qualitativa confermata; residuo 0.06 di gap ρ imputabile a patch bug 2/4/5/7 e fix warmup tra v7.4 e v8.

## Disclosure obbligatoria nel paper v8

> ρ_AR(1) F2 OOS è funzione monotona di `min_concordant`. Sul best_param v8 (`min_concordant=2`) F2 è mean-reverting (ρ = −0.08). La proprietà "persistente" osservata in v7.4 (ρ = +0.19, Bug 8) era condizionata su `min_concordant=3`, non universale. Il fenomeno è confermato riproducibile (Pearson 0.84 tra build v7.4 e v8 sul medesimo trial mc=3) ma non si applica al sistema operativo corrente.

## Catena di evidenza

| Commit | Data | Ruolo |
|---|---|---|
| `13dcf97` | 23/05 15:29 | Task 5 v7.3 — task5_bootstrap.py legge `wf_full_v74_equity.csv` filtrando per best_config F2 = (mc=3, thr=0.25, trial_id=61) |
| `2114311` | 23/05 15:34 | Task 6+7 — committa binario `task6_returns.npz` con key F2 derivata da Task 5 |
| `99379ed` | 23/05 15:42 | Task 7a — `task7a_robustness.py` calcola ρ_AR(1) +0.1883 e Q(10) 20.374 |
| `e4dc7aa` | 23/05 15:59 | Chiusura v7.3 sealed con audit_journal_v7_3.md |
| `6e80001` | 23/05 ~16:00 | Patch B2 bug 2/4/5/7 |
| `63d9be3` | 24/05 04:23 | Rerun v8 esec 2 con grid smoke 8 trial — best F2 cambia a mc=2 |
| S2 (questa indagine) | 24/05 06:30 | Diagnosi definitiva: artefatto di selezione best_param |

## File indagine S2

| File | SHA256 |
|---|---|
| `task6_returns.npz` (estratto da commit 2114311) | `5327118365c58edfe00c1d3462f4486515386d56e4ad02f8a04fba1ebeb5de26` |
| `inspect_task6_npz.py` | `d6ecb02e240b8f5fa4a9b42d56591b3cae6b1d454a2abc083277a2ec7ee6f255` |
| `structural_diff.py` | `00607fcf3b6970b27aa64eb30a80afd4efe6b29014255d2d9523caf76983bb47` |
| `test_alternative_trials.py` | `a8a3c6b1ba3c6ba81c24c18f937db716439344802d3465e59e70d80f1ba936c5` |
| `audit_journal_v7_3_sealed.md` (estratto e4dc7aa) | `04d08f887fdcd6a51b884a595d90f834eab90d2adfb70871ba0165f2a85813fc` |
| `f2_sealed_from_npz.csv` | `ac0873cb871f83106cc9eff60361b7b3f10bfd392e3ee9f03fe45f626fe68700` |

## Next operativo (deferred S2, alta priorità)

1. **Sensitivity selettore**: testare max-DSR, min-|ρ_AR(1)|, max-Sharpe con vincolo |ρ|<0.10 contro max-Sharpe corrente. Tabella selettore × best_param × Sharpe × ρ × PnL.
2. **IC bootstrap sulla differenza Sharpe v8 mc=2 (1.94) vs mc=3 (1.91) sui 65 daily F2 OOS**. Δ Sharpe = 0.03 plausibilmente entro noise; se IC contiene zero, la preferenza mc=2 è statisticamente non significativa e la selezione corrente è fragile.
3. **Cluster 2022 INCONCLUSIVE_DEGRADED** resta indagine separata (problema dati, non sensibilità selettore).

## Stato Bug 8

**CHIUSO — SUPERATO da v8**, con disclosure obbligatoria nel paper. Nessun fix nel codice richiesto. Indagine sensitivity selettore aperta in S2 come robustness check metodologico.
