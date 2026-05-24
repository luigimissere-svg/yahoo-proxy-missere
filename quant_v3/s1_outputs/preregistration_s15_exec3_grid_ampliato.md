# Preregistrazione S1.5 esecuzione 3 — Grid ampliato post-sigillo Bug 8

**Data preregistrazione**: 24/05/2026 06:46 CEST
**Riferimento**: Sigillo Bug 8 (commit `f51ed7e`), raccomandazione consulente §3.2
**Deadline esecuzione**: 06/06/2026 23:59 CEST
**Branch**: `feature/v8-s1-refactor`

---

## 1. Motivazione

Post-sigillo Bug 8 (24/05 06:44), il consulente ha raccomandato ampliamento del grid prima di leverage analysis. Osservazione critica del sensitivity (commit `c09e7dd`):

> Trial 1, 2, 5, 6 del `GRID_SMOKE` producono stat IDENTICHE (Sharpe 4.389, ρ −0.080, PnL +20.45%). Quando `min_concordant = 2`, i parametri `threshold` e `max_sector_pct` sono NON-informativi: la strategia diventa indipendente da quegli assi.

Conseguenza: il grid smoke esplora solo **2 portafogli effettivamente distinti su 8 trial nominali**. Il selettore opera su uno spazio degenere. Bug 8 SUPERATO da v8 resta valido, ma S1.5 esec 3 deve girare su grid più discriminante per validare la robustezza del best_param.

---

## 2. Grid ampliato (preregistrato)

`GRID_S1_5_EXEC3` introdotto in `quant_v3/engine/wf_runner.py`:

```python
GRID_S1_5_EXEC3: Dict[str, List[Any]] = {
    'threshold':       [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    'min_concordant':  [2, 3, 4],
    'max_sector_pct':  [None, 0.30],
}  # 6×3×2 = 36 combo
```

### Razionale assi

- **threshold** step 0.05 da 0.05 a 0.30: 6 livelli discriminanti per testare se thr smette di essere degenere fuori dal range smoke (0.15, 0.25). Confine inferiore 0.05 cattura strategie quasi-sempre-attive; 0.30 cattura strategie selettive.
- **min_concordant** ∈ {2, 3, 4}: estensione richiesta da consulente. Smoke aveva solo {2,3}; aggiungiamo 4 per verificare se la monotonia osservata su mc (mc=2 mean-reverting → mc=3 autocorrelato) prosegue oltre mc=3.
- **max_sector_pct** ∈ {None, 0.30}: invariato vs smoke. Non si amplia perché vincolo settoriale ortogonale al fenomeno Bug 8.

Esclusi: `target_risk_pct` e `max_portfolio_beta` (presenti in GRID_FULL). Motivo: contenere costo. Verranno reintrodotti in eventuale S1.5 esec 4 se servisse.

### Costo atteso

- 36 combo × N_fold × 2 fasi (IS + OOS) ≈ 36 × (12 fold est.) × 2 ≈ 864 backtest
- Singolo backtest ~5-10 s su universo S&P500/STOXX600 → ETA 1.2-2.4 h
- Più overhead OOS-grid scan dedicato (v7.3 DSR) ≈ 36 × N_fold ≈ 432 backtest aggiuntivi
- ETA totale: **~2-3 h walltime**

---

## 3. Ipotesi pre-registrate (H1-H4)

### H1 — Non-degenerazione

Sul grid ampliato, **non più del 25% dei trial** produrrà stat identiche a un altro trial (tolleranza |ΔSharpe| < 0.05, |Δρ| < 0.01, |ΔPnL| < 0.5%).

Falsificazione: se ≥ 50% dei trial sono identici a un altro, il grid resta degenere e va ulteriormente ampliato.

### H2 — Monotonia ρ_AR(1) su mc

Estendendo a mc=4, la relazione monotona ρ_AR(1) ~ mc osservata su mc ∈ {2,3} si conferma:

- mc=2: ρ < 0 (mean-reverting)
- mc=3: 0 < ρ < +0.30
- mc=4: ρ > 0 (più persistente di mc=3, oppure plateau)

Falsificazione: se mc=4 produce ρ < ρ(mc=3) o ρ < 0, la monotonia è artefatto e Bug 8 va riaperto.

### H3 — Best_param stabile (sensitivity post-grid ampliato)

Applicando i 4 selettori (max-Sharpe, max-DSR, min-|ρ|, max-Sharpe con vincolo |ρ|<0.10) sul grid 36-combo, **almeno 3 su 4 selettori** convergono sullo stesso `(thr, mc)`.

Falsificazione: se ≤ 2 selettori convergono, la robustezza del best_param v8 è compromessa e va rivista la sezione paper v8 §3-§4.

### H4 — Sharpe operativo Backtrader del best_param ≥ 1.5

Sul best_param selezionato dal grid ampliato, **Sharpe Backtrader OOS ≥ 1.5** (corrisponde al floor operativo discusso con consulente).

Falsificazione: se Sharpe operativo < 1.5, la chiusura S1 si ferma e si rivede strategia.

---

## 4. Procedura (preregistrata, non modificabile post-esecuzione)

### Step 1 — Smoke check pre-rerun

```bash
cd quant_v3 && python -m engine.wf_runner \
    --grid s1_5_exec3 \
    --universe SP500 \
    --output-csv s1_outputs/s15_exec3_dry.csv \
    --stability-json s1_outputs/s15_exec3_dry_stability.json \
    --is-months 12 --oos-months 3 --step-months 3 \
    --max-positions 10 --per-ticker-cap 0.10
```

Solo per verificare che il flag `--grid s1_5_exec3` funzioni e che 36 combo siano generate. Output: `s15_exec3_dry.csv` da scartare (verrà sovrascritto da run autoritativo).

### Step 2 — Run autoritativo F2 (S&P500)

Stesso comando ma con `--save-equity-csv` e `--save-trades-csv`:

```bash
python -m engine.wf_runner \
    --grid s1_5_exec3 \
    --universe SP500 \
    --output-csv s1_outputs/s15_exec3_f2_results.csv \
    --stability-json s1_outputs/s15_exec3_f2_stability.json \
    --save-equity-csv s1_outputs/s15_exec3_f2_equity.csv \
    --save-trades-csv s1_outputs/s15_exec3_f2_trades.csv \
    --is-months 12 --oos-months 3 --step-months 3 \
    --max-positions 10 --per-ticker-cap 0.10 \
    --stable-threshold 3
```

### Step 3 — Falsificazione H1 (non-degenerazione)

Script `s15_exec3_degeneracy_check.py` da scrivere: legge `s15_exec3_f2_results.csv`, calcola coppie di trial con stat identiche, restituisce % degenere. PASS se ≤ 25%.

### Step 4 — Falsificazione H2 (monotonia mc)

Per ogni fold OOS, regressione ρ_AR(1) ~ mc. PASS se coefficient positivo significativo (p < 0.10).

### Step 5 — Falsificazione H3 (sensitivity post-grid)

Riesecuzione `sensitivity_selector.py` sul nuovo CSV. PASS se ≥ 3/4 selettori concordano.

### Step 6 — Falsificazione H4 (Sharpe operativo ≥ 1.5)

Lettura Sharpe Backtrader OOS del best_param H3. PASS se ≥ 1.5.

### Step 7 — Sigillo S1.5 esec 3

Se PASS H1+H2+H3+H4 → procedere con leverage analysis. Se FAIL su qualsiasi H → escalation S2 dedicata, NO unificazione con Bug 8.

---

## 5. Vincoli operativi

- Append-only su `s1_outputs/`: nessun file pre-24/05 va modificato
- SHA256 di ogni file output va registrato nel commit finale S1.5 esec 3
- NO modifica retroattiva delle ipotesi H1-H4 post-esecuzione
- NO prompt-engineering verdetti

---

## 6. Items NON in scope esec 3

- Bootstrap Δ Sharpe operativo (Backtrader full equity dump multi-trial) → **DEFERRED S3**
- Cluster 2022 INCONCLUSIVE_DEGRADED → **INDAGINE SEPARATA S2**
- target_risk_pct, max_portfolio_beta → **EVENTUALE S1.5 esec 4**
- Leverage analysis → BLOCCATA fino a PASS H1-H4

---

## 7. Validazione

Preregistrazione validata da Luigi Missere, 24/05/2026 06:46 CEST.
Validazione consulente: implicita via direttiva §3.2 sigillo Bug 8 (24/05 06:44).
