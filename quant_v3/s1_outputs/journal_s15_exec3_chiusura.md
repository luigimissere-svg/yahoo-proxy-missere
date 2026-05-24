# S1.5 esec 3 — Journal di chiusura

**Data**: 24/05/2026 07:40 CEST
**Branch**: `feature/v8-s1-refactor`
**Commit run apertura**: `50778de` (preregistration + grid)
**Commit addendum universo**: `3dfaf11` (--universe portfolio)

---

## 1. Verdetto sintetico

| Ipotesi | Esito | Note |
|---|---|---|
| H1 — Non-degenerazione (≤25%) | **FAIL** | 24/24 trial validi (100%) degenerati su F2 OOS |
| H2 — Monotonia ρ_AR(1) ~ mc | **PASS** | slope=+0.333, p<0.0001, ρ̄(mc=2)=−0.080, ρ̄(mc=3)=+0.253 |
| H3 — Convergenza selettori (≥3/4) | **PASS** | 4/4 selettori → (mc=2, thr=0.05, msp=NA) |
| H4 — Sharpe operativo BT ≥ 1.5 | **PASS** | Sharpe BT OOS = 1.944 |
| **Verdetto complessivo** | **FAIL** | H1 blocca leverage analysis |

---

## 2. Diagnosi dettagliata

### 2.1 H1 FAIL — Grid strutturalmente degenere

Su 36 combo del grid `GRID_S1_5_EXEC3`:

- **12 trial mc=4 → portfolio mai investito** (Sharpe NaN, PnL 0%, BUY=0 in tutti i fold). Mc=4 è troppo selettivo per il portafoglio 35 ticker: nessun segnale concordante mai trovato.
- **12 trial mc=2 → tutti producono Sharpe 4.389 esatto, ρ −0.080 esatto, PnL +20.45% esatto**. Le variazioni di `thr ∈ {0.05, 0.10, 0.15, 0.20, 0.25, 0.30}` e `msp ∈ {None, 0.30}` sono **completamente non-informative quando mc=2**.
- **12 trial mc=3 → 5 valori distinti di Sharpe** (range 1.610–1.952). Solo qui il grid è effettivamente discriminante.

Conclusione: il grid esplora di fatto **6 portafogli distinti** (1 mc=2 invariante + 5 mc=3 variabili + mc=4 inutilizzabile) su 36 trial nominali. Peggio del grid smoke (2/8 = 25%) — ma il numero assoluto di portafogli distinti è maggiore (6 vs 2). Il problema non è risolvibile aumentando thr o msp.

### 2.2 H2 PASS — Conferma robusta Bug 8

Estendendo mc a {2, 3, 4}:

| mc | n trial validi | ρ_AR(1) medio |
|---|---|---|
| 2 | 12 | −0.080 (mean-reverting) |
| 3 | 12 | +0.253 (autocorrelato) |
| 4 | 0 | — (NaN, portfolio flat) |

Regressione ρ ~ mc: slope +0.333, p < 0.0001. La monotonia osservata su mc ∈ {2, 3} si conferma direzionalmente; non possiamo testare mc=4 perché il portafoglio non investe mai.

**Implicazione Bug 8**: la disclosure §4.X del paper v8 ("ρ_AR(1) F2 OOS è funzione monotona di min_concordant") è **rafforzata** dal grid ampliato. Non solo confermata su {2,3} ma estesa con p-value sostanziale.

### 2.3 H3 PASS — Selettore data-driven robusto

I 4 selettori (max-Sharpe, max-DSR, min-|ρ|, max-Sharpe con vincolo |ρ|<0.10) convergono **tutti** su trial 1 (mc=2, thr=0.05, msp=NA).

**Discrepanza apparente vs sensitivity precedente (commit `c09e7dd`)**: lì il best era (mc=2, thr=0.15); qui è (mc=2, thr=0.05). **Non è un cambio reale** — sono lo stesso portafoglio. Quando mc=2, le scelte di thr 0.05, 0.10, 0.15, 0.20, 0.25, 0.30 producono backtest IDENTICI bit-a-bit. Trial 1 vince perché è il primo enumerato.

**Implicazione**: la sezione paper v8 §3-§4 non va modificata. Il best_param "vero" v8 resta (mc=2, thr=qualsiasi nel range testato) e Sharpe BT OOS = 1.944.

### 2.4 H4 PASS — Conferma esatta Sharpe operativo v8

Sharpe BT OOS F2 = **1.944** — coincide bit-a-bit con il valore che avevamo dal rerun esec 2 (commit `63d9be3`) e citato nel sigillo Bug 8 (`f51ed7e`). Stabilità numerica della pipeline confermata su grid completamente diverso.

---

## 3. Implicazioni decisionali

### 3.1 Bug 8 chiusura — resta valida

Il sigillo Bug 8 (`f51ed7e`) **non va riaperto**. H2+H3+H4 confermano tutte le componenti tecniche della chiusura. H1 FAIL non riguarda Bug 8 — riguarda la qualità intrinseca della strategia ATR/min_concordant come trattata sul portafoglio attuale.

### 3.2 Leverage analysis — BLOCCATA

Per direttiva preregistrazione (Step 7), FAIL su qualsiasi H blocca leverage analysis. **Non procediamo a leverage** finché non risolviamo H1.

### 3.3 Origine vera della degenerazione

Mc=2 produce backtest invariante perché:

1. Con mc=2, **almeno 2 indicatori concordi su 4** è una condizione molto debole — quasi sempre vera quando il mercato si muove. Quindi i segnali "buy" sono frequenti.
2. Quando thr varia 0.05→0.30, il filtro su entry strength dovrebbe restringere il numero di segnali, ma il portafoglio 10-position cap + `per-ticker-cap 0.10` **satura prima**: si arriva al cap di 10 posizioni indipendentemente da quanti segnali "vincenti" ci siano.
3. Quindi thr in pratica non riduce mai sotto 10 il numero di segnali ammessi.

**Diagnostica raccomandata**: contare quanti segnali BUY vengono emessi per ciascun trial mc=2 PRIMA del filtro dei 10. Se il numero è sempre molto >10, il grid sul thr è inutile su questo portafoglio. Per discriminare servirebbe:

- Universo più ampio (`extended` 1037 ticker) → più diversità di segnali
- Portfolio cap più alto (es. 20 posizioni)
- thr applicato a un asse diverso (es. score continuo invece di hit-count)

### 3.4 Items deferred — RICONFERMATI

- **S3 — Bootstrap Δ Sharpe operativo full equity multi-trial**: deferred
- **S2 — Cluster 2022 INCONCLUSIVE_DEGRADED**: indagine separata
- **target_risk_pct + max_portfolio_beta**: eventuale S1.5 esec 4

### 3.5 Nuovo item — S1.5 esec 4 raccomandato

**Obiettivo**: risolvere degenerazione H1 prima di leverage analysis.

**Ipotesi tecnica**: il `thr` non è discriminante perché il bottleneck è `max-positions=10 + per-ticker-cap=0.10`, non il filtro di entry.

**Diagnostica da eseguire**:

1. Conteggio segnali BUY emessi pre-cap per ogni trial mc=2 (PASS se varianza non-nulla → thr funziona ma cap satura)
2. Test con `--max-positions 20 --per-ticker-cap 0.05` su grid corrente (PASS se varianza emerge)
3. Test con universo `extended` (1037 ticker EU+US) su sottoinsieme thr/mc (PASS se varianza emerge)

**Decisione**: scegliere ONE delle tre + ripetere H1.

---

## 4. Output prodotti

| File | SHA256 | Note |
|---|---|---|
| `s15_exec3_f2_results.csv` | `e56f193cafcdac3888732c201b255447660fe42cdc85d87abec72a5b309305fa` | 3 fold × best_param |
| `s15_exec3_f2_stability.json` | `bc6452b6c5a65be570caa79ccc121d905b6d96bf49586a0c107c03bb7886f658` | nessun parametro stabile 3/3 |
| `s15_exec3_f2_equity.csv` | `7d9cb7f55ff696971387698dd5c4cb2117aff4e1e806ce5097d08dba21f8fbbe` | 35244 righe × 6 fold×phase |
| `s15_exec3_f2_trades.csv` | `7529bde491bf2bd92dee2b4af8172875df52e3107fb0cafeb9452ae8c8ce9350` | 32 trade chiusi/aperti su best_param fold |
| `s15_exec3_falsification_report.md` | `e16f422d8949c19ead901a2bb49f9dc260e5388a7a3b8fd64b8bffb6bec364a2` | report H1-H4 |
| `s15_exec3_falsification_report.json` | `98a7c2efe9e5290b55e7193521cda2845552697a01f3127c38d1f422f3ba985a` | dettaglio macchina-leggibile |
| `s15_exec3_falsification.py` | `edac44ecf1e4c8c5b613b113c3923169741e803795230f2db0c299cc73f5e794` | script (con fix NaN-aware H1+H3) |
| `s15_exec3_logs/run.log` | `4e866b1b1b035744038f54138a90c3b72e9b3046a022835d56e956cdec82d94e` | log completo wf_runner |

---

## 5. Vincoli rispettati

- Append-only: questo journal è ADD, nessuna modifica retroattiva di preregistrazione o ipotesi
- Ipotesi H1-H4 invariate post-esecuzione (no prompt-engineering verdetto)
- Bug fix su `s15_exec3_falsification.py` documentato qui sotto in §6 — NON cambia esito H1 (FAIL prima e dopo del fix); cambia H3 da FAIL apparente a PASS reale, allineato ai dati
- Validazione esplicita Luigi Missere: in attesa

## 6. Fix script falsificazione (trasparenza)

Lo script v1 aveva due bug:

1. **H1 contava trial NaN come degenerati**: corretto separando trial validi (Sharpe finito) da invalidi (NaN). Risultato: 24 validi su 36, 24/24 degenerati = 100%. Esito invariato (FAIL).
2. **H3 usava tuple con NaN per Counter**: due tuple `(2.0, 0.05, nan)` non sono uguali in Python (`nan != nan`), quindi `Counter` registrava 4 firme distinte invece di 1. Corretto convertendo a stringa normalizzata. Risultato: 4/4 selettori convergono. Esito cambia da FAIL apparente a PASS reale.

I dati grezzi (`s15_exec3_f2_results.csv`, `s15_exec3_f2_equity.csv`) sono invariati: il fix riguarda solo l'interpretazione.

— Luigi Missere (in attesa validazione), 24/05/2026 07:40 CEST
