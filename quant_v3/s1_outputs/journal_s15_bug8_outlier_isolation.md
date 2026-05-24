# Journal S1.5 — Bug 8 isolamento outlier (ESECUZIONE 1, DEGRADED)

Data: 2026-05-24 — 05:55 CEST
Branch: feature/v8-s1-refactor
Pre-registrazione: Addendum 11 sealed (`preregistration_s1_v8_addendum_11_s15_outlier_criterion.md`)
SHA256 Add 11: `81778f37904187584aad7ce96d2d51d4117fc208e991a1eeae8c2dd31bef84ba`

Sealed version: v8.s1.5 (esecuzione 1, da rifare con dati sealed reali)

---

## 1. Esecuzione 1 — ricostruzione serie F2 OOS da ledger + OHLCV

### 1.1 Metodologia adottata

Default D3 di Add 11: ricostruzione serie 65 daily F2 OOS via:
- Ledger sealed `f2_oos_trade_ledger.csv` (10 trade open_at_end, fold_id=2)
- Prezzi daily OHLCV da `quant_v3/data/ohlcv/*.parquet` per i 10 ticker
- Pesi notional = `notional_open_i / sum_j notional_open_j` (equal-weight implicito)
- Portfolio daily return = `sum_i w_i × r_t^{(i)}`

Script: `s15_reconstruct_f2_daily.py` (337 righe)
Output: `s15_outputs/f2_oos_daily_returns_reconstructed.csv`
SHA256: `731b7e574b64667f75bcab91f978f7b58830d04184f8cafe365f41ae84d65492`

### 1.2 Risultati numerici ricostruzione

| Metrica | Sealed v7.3 (riga 802) | Ricostruito | Gap | Stato |
|---|---|---|---|---|
| ρ_AR(1) OLS | +0.1883 | **−0.0998** | **−0.2881** | GAP > 0.02 |
| ρ_lag1 (acf) | +0.1880 (Task 5) | **−0.0987** | **−0.2870** | GAP > 0.02 |
| Q(10) Ljung-Box | 20.374 | 13.998 | −6.376 | |
| p-value | 0.0259 (sig 5%) | 0.1731 (NS) | +0.1472 | |
| T effective | 65 | 62 | −3 | |
| Mean daily return | n/d | +0.002740 | | |
| Std daily return | n/d | +0.010342 | | |
| Cum return OOS | +21.26% (cfr `analisi_concentrazione_f2.md`) | +18.10% | −3.16pp | |

### 1.3 Verdetto auto-falsificazione (Add 11 §3 D3 e §5.7)

Criterio sealed pre-esecuzione:
> "Se ρ ricostruito da serie 65 daily ricostruita differisce > 0.02 dal sealed +0.1883, S1.5 DEGRADED."

**Gap osservato**: −0.2881 (acf: −0.2870). Entrambi violano la soglia 0.02.

**S1.5 esecuzione 1: DICHIARATO INCONCLUSIVE_DEGRADED.**

NON si può procedere al verdetto binario (ISOLATO / STRUTTURALE / INTERMEDIO) perché il dato di base è non-equivalente al sealed v7.3.

## 2. Diagnosi della discrepanza

### 2.1 Segno opposto ρ

Sealed v7.3 F2: ρ = +0.1883 (autocorrelazione positiva, momentum daily)
Ricostruito: ρ = −0.0998 (autocorrelazione negativa, mean-reverting daily)

Differenza qualitativa: il portfolio sealed F2 ha **persistenza** (Bug 8); il portfolio ricostruito (basket equal-weight statico) ha **reversione**.

### 2.2 Cause candidate (in ordine di plausibilità)

**C1 — Cash drag e sizing dinamico (ALTA plausibilità)**: i 10 trade del ledger sono `open_at_end`, ma il `target_risk_pct=0.008` implica un sizing volatility-based dinamico durante OOS. I `notional_open` registrati nel ledger sono lo snapshot finale, non i pesi medi over OOS. Il portfolio sealed include anche cash residuo (cash = 100k − sum(notional)) che drago il return giornaliero, alterando la correlazione seriale.

**C2 — Mark-to-market vs strategy equity (ALTA)**: `wf_runner.py` linea 242-267 (Bug 2 fix candidate) filtra `rets` a `[start, end]` per escludere warmup. La serie 65 sealed è prodotta da Backtrader `TimeReturn` analyzer applicato all'equity strategy completa (include slippage, commissioni, intraday fluctuations su tutti i bar trading, non solo i 10 ticker selezionati). La ricostruzione equal-weight ignora questi effetti.

**C3 — Pre-roll trades (MEDIA)**: Bug 5 sealed v7.3 (`audit_journal_v7_3.md` riga 132) documenta "Pre-roll trades possibili: warmup_bars=50 + minperiod=200 < pre-roll 261bar" con CONFERMATO 100% prevalenza. Alcuni trade del fold F2 possono essere entrati prima del 2025-11-01 (in finestra warmup), influenzando i daily returns iniziali in modo non riproducibile dal ledger snapshot.

**C4 — Skip warmup vs nonzero filter (BASSA)**: `oos_n_nonzero_returns=75` nel `wf_full_v3_results.csv`, `T=65` riportato in journal Task 7a. La discrepanza 75 vs 65 può indicare un filtro aggiuntivo (es. drop primi 10 bar per warmup contamination). Ricostruzione attuale ha T=62 effective.

**C5 — Differenza OHLCV parquet vs feed Backtrader (BASSA)**: Backtrader può applicare adjustments dividendi/split/forex (Yahoo Finance autoadjust) diversi da quelli salvati nei parquet locali. Improbabile su finestra 3 mesi recente.

### 2.3 Cause non plausibili escluse

- **Errore di firma codice S1.5**: codice ricontrollato, OLS standard `np.linalg.lstsq`, acf manuale Politis-style. Match interno acf vs OLS al 4° decimale (−0.0987 vs −0.0998). Algoritmo corretto.
- **Errore ledger**: `f2_oos_trade_ledger.csv` immutato da 23/05 08:38 CEST (sealed pre-gate). 10 trade riconciliati con `analisi_concentrazione_f2.md` (MU +11.176, totale +21.361). Consistenza ledger PASS.
- **Errore prezzi**: tutti 10 ticker hanno range OHLCV completo 2025-11-03 → 2026-01-30. Mancano solo 2025-11-01 (sabato) e 2025-11-02 (domenica). Coerente con calendario.

## 3. Rimedio proposto — esecuzione 2 (richiede merge branch feat/save-equity-v7-3)

### 3.1 Piano operativo

1. Cherry-pick commit `f3be28f` (feat: --save-equity-csv) dal branch `origin/feat/save-equity-v7-3` su `feature/v8-s1-refactor`
2. Re-run `wf_runner.py` con `--save-equity-csv` per il solo fold F2 (params F2 sealed: threshold=0.25, min_concordant=2, target_risk_pct=0.008)
3. Estrarre serie 65 daily F2 OOS direttamente da `wf_runner` output (questa è la serie sealed)
4. Verificare ρ_AR(1) reale = +0.1883 (entro ±0.001)
5. Rieseguire leverage hat-matrix Δρ_i per ciascun trade con sostituzione `r_t^{(i)} → 0` operata sulla serie sealed
6. Per applicare D2 (esclusione trade): serve mapping daily contribution per ticker. Backtrader analyzer custom `PositionsValue` o equivalente. Alternativa: usare `--save-trades-csv` (commit `316d747`) per ledger dettagliato con dt_open/dt_close per ciascun trade, poi ricostruire daily contribution su quei trade specifici.

### 3.2 Tempi stimati

- Cherry-pick + risoluzione conflitti: 30 min
- Re-run wf_runner singolo fold F2: 5-15 min CPU
- Re-analisi leverage + verdetto: 1h
- Totale: ~2-3h, ben entro deadline S1.5 06/06 23:59 CEST

### 3.3 Vincoli da rispettare in esecuzione 2

- Add 11 §5.6: nessuna selezione retroattiva outlier. Criterio leverage Δρ_i sealed §4.3 invariato.
- Add 11 §5.5: nessun prompt-engineering verdetto. Soglia +0.10 invariata.
- Append-only: questo journal documenta esecuzione 1 DEGRADED in modo definitivo; esecuzione 2 produce nuovo journal `journal_s15_bug8_outlier_isolation_exec2.md`.

## 4. Artefatti sigillati esecuzione 1

| File | SHA256 |
|---|---|
| `preregistration_s1_v8_addendum_11_s15_outlier_criterion.md` | `81778f37904187584aad7ce96d2d51d4117fc208e991a1eeae8c2dd31bef84ba` |
| `s15_outputs/f2_oos_daily_returns_reconstructed.csv` | `731b7e574b64667f75bcab91f978f7b58830d04184f8cafe365f41ae84d65492` |
| `s15_outputs/s15_sensitivity_curve.json` | `8f1d3c2bdd25ed6b95956b117b34c80a2866e781b1529011a6b9326a4ce7cb85` |
| `s15_outputs/s15_leverage_ranking.csv` | `02f55405003af17b034bf139ef8b93eada1b38989075e8e1413e2a5118547c0e` |
| `s15_reconstruct_f2_daily.py` | (calcolato in §5) |
| `journal_s15_bug8_outlier_isolation.md` | (questo file, calcolato post-write) |

## 5. Status S1.5 esecuzione 1

INCONCLUSIVE_DEGRADED.

Bug 8 verdetto: **NON ATTRIBUIBILE in esecuzione 1**. Procedere con esecuzione 2 post merge branch feat/save-equity-v7-3.

## 6. Lezione metodologica (entra nel registro disclosure)

La ricostruzione di una serie sealed da artefatti derivati (ledger snapshot + OHLCV indipendenti) NON è equivalente alla serie generata dal walk-forward backtester. Per riproduzione di precisione su test statistici (ρ_AR(1), Q-test, DSR), il dato sealed deve essere prodotto dallo stesso codice che ha generato il test originale, NON ricostruito da artefatti adiacenti.

Implicazione operativa: il flag `--save-equity-csv` (branch `feat/save-equity-v7-3`) doveva essere mergeato in `feature/v8-s1-refactor` PRIMA di chiudere v7.3 sealed. Ritardo nel merge è la causa root del DEGRADED odierno.

## 7. Firma esecuzione 1

Firmato dal Consulente esecutivo S1 (agente) il 2026-05-24 05:55 CEST.

Validazione committente richiesta su:
- Conferma diagnosi C1+C2 (cash drag + MtM)
- Autorizzazione cherry-pick `f3be28f` + `316d747` su feature/v8-s1-refactor
- Eventuale revisione default D3 Add 11

---
FINE Journal S1.5 esecuzione 1
