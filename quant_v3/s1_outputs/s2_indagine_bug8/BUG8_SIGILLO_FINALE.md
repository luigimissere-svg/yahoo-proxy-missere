# Bug 8 — Sigillo finale: SUPERATO da v8

**Data sigillo**: 24/05/2026 06:44 CEST
**Branch**: `feature/v8-s1-refactor`
**Commit chiusura indagine**: `4326045`
**Commit sensitivity**: `c09e7dd`
**Validazione consulente**: 24/05 06:44 CEST (risposta su Issue #9 + sensitivity)
**Validazione committente**: Luigi Missere, 24/05 06:44 CEST

---

## 1. Verdetto

**Bug 8 SUPERATO da v8** — artefatto di selezione del best_param, non di calcolo, non falso positivo. La proprietà "ρ_AR(1) F2 OOS persistente" osservata in v7.4 era condizionata su `min_concordant = 3`. In v8 il selettore data-driven sceglie `min_concordant = 2` e la stessa serie F2 diventa mean-reverting. Non c'è bug nel codice — c'è una sensibilità strutturale di ρ_AR(1) a `min_concordant` che non era stata documentata.

### Traccia di derivazione (riproducibile)

- `task6_returns.npz` (SHA estratto 2114311) → ρ_AR(1) = +0.1883 ESATTO
- `task7a_robustness.py` (commit 99379ed) → formula AR(1) standard `(r_t − μ)·(r_{t−1} − μ) / Σ(r − μ)²`
- `task5_bootstrap.py` (commit 13dcf97) → `best_config F2 v7.4 = (mc=3, thr=0.25, trial_id=61)`
- v8 best_config F2 (rerun esec 2): `(mc=2, thr=0.15, trial_id=1)`
- Trial 7 v8 (mc=3, thr=0.25) replica v7.4: ρ = +0.2474, Pearson(serie v8 trial-7, sealed v7.4) = +0.8411
- Residuo gap +0.06 (0.2474 vs 0.1883) imputabile a patch B2 (bug 2/4/5/7), commit 6e80001

### Sensitivity selettore (commit c09e7dd)

| Selettore | Trial | mc | thr | Sharpe_a (raw) | ρ_AR(1) | DSR |
|---|---|---|---|---|---|---|
| A · max-Sharpe | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 |
| B · max-DSR | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 |
| C · min-\|ρ\| | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 |
| D · max-Sharpe con \|ρ\|<0.10 | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 |

I 4 selettori convergono sullo stesso trial → selezione del best_param ROBUSTA al criterio di scelta.

### IC bootstrap Δ Sharpe raw (B=10000, seed=20260524)

- i.i.d.: IC95% [−0.517, +5.953], p=0.0956
- Block L=5: IC95% [−0.636, +6.675], p=0.1196

Entrambi contengono zero → preferenza mc=2 sopra mc=3 NON statisticamente significativa al 95% sul campione T=65. Non-significatività confermata; bootstrap su Sharpe operativo (Backtrader) deferred S3 (vedi §3.1).

---

## 2. Disclosure obbligatoria paper v8 (versione finale validata dal consulente)

### §3 Metriche operative

Sharpe primario operativo: `bt.analyzers.SharpeRatio` su equity post-MtM (definizione "broker", include cash drag).

| F2 OOS v8 | Sharpe operativo |
|---|---|
| mc=2 (best_param) | 1.94 |
| mc=3 (trial 7) | 1.91 |

Questa è la metrica autoritativa del paper: riflette ciò che otterremmo deployando 100 k€ tramite broker.

### §4.1 Analisi segnale alpha (NON Sharpe di portafoglio investibile)

Sharpe del segnale puro su daily return aggregati, escluso cash drag — NON è il Sharpe di portafoglio investibile.

| F2 OOS v8 | Sharpe segnale (alpha-pure) |
|---|---|
| mc=2 (best_param) | 4.389 |
| mc=3 (trial 7) | 1.610 |

Etichetta esplicita richiesta nel paper. Da NON confondere con Sharpe operativo §3.

### §4.1 Cash drag disclosure (testo obbligatorio)

> L'efficienza di capitale di F2 v8 è ~50-60% in cash. Il gap tra Sharpe segnale (§4.1) e Sharpe operativo (§3) riflette questo. Lavoro futuro: cash overlay (T-bills) potrebbe ridurre il gap senza alterare il segnale alpha.

### §4.X ρ_AR(1) — disclosure Bug 8

> ρ_AR(1) F2 OOS è funzione monotona di `min_concordant`. Sul best_param v8 (mc=2) F2 è mean-reverting (ρ = −0.080). La proprietà "persistente" osservata in v7.4 era condizionata su mc=3, non universale. La selezione del best_param mc=2 in v8 è data-driven e robusta a 4 criteri (max-Sharpe, max-DSR, min-|ρ|, max-Sharpe con vincolo |ρ|<0.10).

---

## 3. Items deferred

### 3.1 Deferred S3 — Bootstrap Δ Sharpe operativo (Backtrader)

Bootstrap Δ Sharpe operativo (Backtrader) mc=2 vs mc=3 con full equity dump multi-trial.

**Motivo deferral**: Costo (rerun wf_runner mantenendo equity di TUTTI i trial, oggi salviamo solo equity del best_param) > beneficio in S1. L'IC raw [−0.517, +5.953] include zero ampiamente; è molto improbabile che l'IC operativo (più stretto perché cash drag schiaccia entrambe le code) escluda zero. Inferenza qualitativa: non-significatività confermata, dettaglio quantitativo deferred.

**Pre-requisito S3**: estendere wf_runner con `--save-equity-multi-trial` flag (analogo a `--save-equity-csv` ma su tutti i trial).

### 3.2 S1.5 esec 3 — Grid degenere (raccomandazione consulente)

**Osservazione**: trial 1, 2, 5, 6 producono stat identiche (Sharpe 4.389, ρ −0.080, PnL +20.45%). Sul grid smoke attuale (mc ∈ {2,3} × thr ∈ {0.15,0.25} × max_sector_pct ∈ {0.4,0.5}), quando mc=2 i parametri `thr` e `max_sector_pct` sono NON-informativi: la strategia diventa indipendente da quegli assi.

**Conseguenza**: il grid smoke esplora solo **2 portafogli effettivamente distinti su 8 trial nominali**. Il selettore opera su uno spazio degenere.

**Raccomandazione**: ampliamento grid prima di leverage analysis in S1.5 esec 3:
- thr più discriminanti (es. {0.05, 0.10, 0.15, 0.20, 0.25, 0.30})
- mc esteso a {2, 3, 4}
- verifica che ogni cella produca portafoglio distinto

**Non blocca chiusura Bug 8** ma deve essere annotato come fragilità del grid corrente.

### 3.3 S2 separato — Cluster 2022 INCONCLUSIVE_DEGRADED

Resta indagine S2 separata, NON unificata con Bug 8. Decisione committente 24/05 06:30.

---

## 4. Vincoli rispettati

- Append-only file sealed: rispettato (questo file è ADD, niente modifiche retroattive)
- SHA256: ogni file di indagine ha hash registrato in `README_S2_bug8_chiusura.md`
- NO firma a nome Luigi senza validazione esplicita: questo sigillo riporta validazione esplicita 24/05 06:44 CEST
- NO modifica retroattiva pre-23/05 22:00: rispettato (estrazione `audit_journal_v7_3_sealed.md` è copia, non modifica)
- NO prompt-engineering verdetto: il verdetto SUPERATO da v8 emerge dalla traccia di derivazione, non da formulazione

---

## 5. Status post-sigillo

| Item | Status |
|---|---|
| Bug 8 | CHIUSO — SUPERATO da v8 |
| Disclosure paper v8 | Versione finale §3 + §4.1 + §4.X validata |
| Sensitivity selettore | ROBUSTA (4 selettori convergono) |
| IC bootstrap raw | Δ Sharpe NON significativa (p=0.096 i.i.d., p=0.120 block L=5) |
| Bootstrap Backtrader | DEFERRED S3 |
| Grid degenere | DEFERRED S1.5 esec 3 |
| Cluster 2022 | INDAGINE SEPARATA S2 |
| S1.5 esec 3 | Da pianificare (deadline 06/06 23:59 CEST) |
| Chiusura S1 completa | Deadline 13/06 |

— Luigi Missere, 24/05/2026 06:44 CEST
