# Pre-Registration S3 — Universo Esteso + Leverage Analysis
# Sigillo iniziale append-only

Data sigillo: 2026-05-24 11:20 CEST
Stato: SIGILLATO PRE-ESECUZIONE — append-only
Firma agente: Consulente esecutivo S1/S3 (agente)
Firma committente: Luigi Missere — validazione esplicita richiesta entro 27/05/2026 23:59 CEST con messaggio dedicato citante SHA256 di questo file

Riferimenti antecedenti sigillati:
- Add 11 §3 D3 default (sealed 24/05 05:45 CEST)
- Add 12 D3-bis supplemento (sealed 24/05 06:00 CEST)
- Add 13 chiusura S1.5 (sealed 24/05 11:15 CEST, SHA256 `8fb05ff7c59585d9b8dde248ecd4499df9c860671ee66b72586f37bf927f8688`)
- Sigillo Bug 8 SUPERATO `f51ed7e`
- Catena commit S1.5: `e5d29eb → 170e7b2 → b2ed2ce → a91aea9 → 35357ee`

---

## 0. Posizionamento

S3 è preregistrazione separata da S1 e S2. Apre per la prima volta:
1. Universo esteso 1037 ticker EU+US (vs portfolio 35 di S1).
2. Leverage analysis (bloccata in S1 per H4 FAIL).
3. Bootstrap Δ Sharpe Backtrader full equity multi-trial (DEFERRED S3 assorbito).

S3 NON tocca S2 (cluster 2022 `INCONCLUSIVE_DEGRADED` invariato). S3 NON tocca disclosure paper v8 §3/§4.1/§4.X (sigilli invariati).

---

## 1. Universo

### 1.1 Definizione
- File: `quant_v3/data/meta/universe_extended.csv`
- Conteggio righe attuale: 1037 (header + 1036 ticker)
- Composizione: EU (STOXX600) + US (S&P500/large-cap), valute EUR/USD/GBP, settori MSCI/GICS-like.
- Snapshot date di riferimento: `2026-05-22`.

### 1.2 Vincolo sigillato
La lista ticker effettiva utilizzata in S3 viene congelata pre-esecuzione con SHA256 del file `universe_extended.csv` calcolato e annotato in §10 (sigillo SHA pre-run). Modifiche post-sigillo sono vietate. Se serve sostituire il file (es. `universe_extended_fixed.csv` con 970 ticker), va dichiarato prima dell'esecuzione e ri-sigillato.

### 1.3 Filtri ammessi
- Esclusione ticker con dato OHLCV mancante > 5% nel range training window (criterio uniforme su tutto l'universo, non per-strategy).
- Esclusione ticker delisted in `data/meta/delist_list.csv` (Add 03-delist invariato).
- Nessun altro filtro discrezionale. Filtri liquidity/market-cap-based vietati post-hoc.

---

## 2. Periodi e finestre walk-forward

### 2.1 Fold S3
Tre fold walk-forward identici per natura a S1 (no innovazione metodologica qui per non confondere effetti universo con effetti procedura):
- F1: train 2018-01-01 → 2020-12-31, OOS 2021-01-01 → 2021-12-31
- F2: train 2019-01-01 → 2021-12-31, OOS 2022-01-01 → 2022-12-31
- F3: train 2020-01-01 → 2022-12-31, OOS 2023-01-01 → 2023-12-31

(Identici a S1.5 esec 3/4 fold setup per consentire confronto diretto degli effetti dell'universo esteso.)

### 2.2 Annotazione 2024-2025
2024 e 2025 NON inclusi in S3 versione iniziale (Phase A). Fold F4 (OOS 2024) e F5 (OOS 2025) deferred a S3 Phase B, soggetta a esito Phase A. Motivazione: limitare degrees of freedom e mantenere comparabilità con S1.

---

## 3. Grid parametri

### 3.1 Grid principale (Phase A)
- `momentum_classes` (mc): {2, 3, 4}
- `threshold` (thr): {0.05, 0.10, 0.20, 0.30}
- `max_sector_pct` (msp): {None, 0.20, 0.30, 0.40}
- `max_positions`: {20, 30, 50}
- `per_ticker_cap`: {0.02, 0.03, 0.05}

Cardinalità: 3 × 4 × 4 × 3 × 3 = 432 trial per fold × 3 fold = 1296 cerebro run.

### 3.2 Leverage grid
- `leverage_factor`: {1.0, 1.25, 1.5, 2.0}
- Applicato solo dopo selezione best_param IS-based identica a S1; leverage misurata come effetto puramente moltiplicativo su equity, costo finanziamento applicato secondo §5.

### 3.3 Justification grid expansion
L'espansione `max_positions × per_ticker_cap` (vs S1 fissato {20, 0.05}) è motivata dalla diagnostica sigillata `s15_diag_buy_pre_cap` (commit `170e7b2`) che ha mostrato saturazione cap mc-dipendente. Su universo 1037 l'effetto saturazione potrebbe spostarsi: serve coprire più scenari.

### 3.4 Justification mc=4 inclusion
mc=4 non testato in S1 perché dichiarato non testabile su 35 ticker (cardinalità classi degenere). Su 1037 ticker la cardinalità per classe è sufficiente: mc=4 testabile per la prima volta.

---

## 4. Ipotesi e soglie (preregistrate)

### H1 — Non degenerazione grid
Definizione coppia degenere: due trial con parametri diversi che producono Sharpe IS identico a 6 decimali in tutti i 3 fold.

Soglia PASS: ≤ 25% delle coppie totali sono degeneri. Soglia FAIL: > 25%.

### H2 — Bug 8 monotonia ρ_AR(1) vs mc (replication)
OLS slope ρ_AR(1) ~ mc su tutti i trial. PASS se slope > 0 ∧ p < 0.10. FAIL altrimenti.

### H3 — Convergenza selettori
4 selettori indipendenti (max Sharpe IS, max Calmar IS, min MDD IS, max Sortino IS). PASS se ≥ 3/4 convergono sulla stessa (mc, thr) per F2. FAIL altrimenti.

### H4 — Sharpe BT OOS best_param IS
Soglia PASS: best_param IS-based ha Sharpe BT OOS F2 ≥ 1.5. FAIL altrimenti.

### H5 — Leverage rationality (NUOVA, esclusiva S3)
Per leverage_factor L ∈ {1.0, 1.25, 1.5, 2.0}: Sharpe OOS BT(L) deve essere monotonicamente non-crescente con L oltre L_optimal preregistrato come L*=1.25.
PASS se: Sharpe(1.25) ≥ Sharpe(1.0) ∧ Sharpe(2.0) < Sharpe(1.5) (concavità rispettata).
FAIL se: leverage rende Sharpe monotonicamente crescente (segnale di artefatto numerico) o monotonicamente decrescente da 1.0 in poi (segnale che leverage non è giustificata).

### H6 — Bootstrap Δ Sharpe BT full equity multi-trial (DEFERRED S3 assorbito)
Per ogni (mc, thr) bootstrap N=1000 di Sharpe OOS BT con block bootstrap (block_size = √n_OOS). PASS se intervallo confidenza 95% di Sharpe OOS best_param non include 0 e ha lower bound ≥ 0.5. FAIL altrimenti.

---

## 5. Costi e attriti (sigillato)

### 5.1 Slippage
0.05% per trade su BT (invariato vs S1).

### 5.2 Commissioni
0.10% per trade su BT (invariato vs S1).

### 5.3 Cost of leverage
Per L > 1.0: costo finanziamento giornaliero = (L - 1) × (€STR + 0.005) sul nominale extra. Annualizzato e sottratto da equity giornaliera prima del calcolo Sharpe OOS leveraged.

### 5.4 Tassazione
Esclusa da BT (coerente con S1).

---

## 6. Decision tree S3 (preregistrato)

Esecuzione 1 S3 Phase A:

- H1 PASS ∧ H2 PASS ∧ H3 PASS ∧ H4 PASS ∧ H5 PASS ∧ H6 PASS → S3 SUCCESS. Procedere con allocazione capitale entro range definito in §8.
- H1 FAIL ∨ H4 FAIL → diagnosi causale (saturazione vs degenerazione strutturale) prima di rerun. Niente rescue post-hoc.
- H2 FAIL → riapertura Bug 8 (atto separato grave, richiede consulente).
- H3 FAIL ∧ tutto il resto PASS → annotazione paper "convergenza selettori sub-soglia su universo esteso", procedere con cautela.
- H5 FAIL → leverage analysis chiusa con verdetto NON GIUSTIFICATA. Niente leverage operativa.
- H6 FAIL → bootstrap mostra fragilità statistica → DEFERRED ulteriormente o chiusura S3 con verdetto INCONCLUSIVO.

Nessun "esec 2/3/4" preautorizzato. Ogni rerun richiede preregistrazione addendum specifico e validazione committente.

---

## 7. Riproducibilità

### 7.1 Seed
Backtrader seed: 42 (invariato vs S1).
Bootstrap seed (H6): 12345.
NumPy default_rng: chiamato esplicitamente con seed dichiarato in script run.

### 7.2 Versioni
- Backtrader: pinnato a versione da `requirements.txt` commit `35357ee` (HEAD post-S1.5).
- Python: 3.11.x (sandbox standard).
- NumPy/Pandas/SciPy: pinnati in requirements.

### 7.3 Output sigillati
Ogni esecuzione produce:
- `s3_phaseA_results.csv` (full grid + Sharpe IS/OOS per fold per trial)
- `s3_phaseA_stability.json` (selettori convergenza)
- `s3_phaseA_equity.csv` (equity daily per best_param IS)
- `s3_phaseA_trades.csv` (trade ledger best_param IS)
- `s3_phaseA_leverage.csv` (Sharpe OOS leveraged per L ∈ grid)
- `s3_phaseA_bootstrap.json` (H6 IC 95% per best_param)
- `s3_phaseA_falsification_report.json` (H1-H6 PASS/FAIL)
- `s3_phaseA_falsification_report.md` (human-readable)
- `s3_phaseA_logs/run.log`
- `journal_s3_phaseA.md`

Tutti sigillati con SHA256 in `journal_s3_phaseA.md`.

---

## 8. Allocazione capitale post-S3 (preregistrata, condizionale)

Coerente con annotazione paper v8 §roadmap operativa (Add 13 §8):
- Se S3 SUCCESS (tutto PASS): proporre allocazione attiva fino a 15-20k EUR su strategia best_param IS, leverage L=1.25 se H5 PASS, soggetta a validazione committente con messaggio dedicato.
- Se S3 PARZIALE (H4 PASS ∧ H5 FAIL): allocazione attiva fino a 10k EUR no leverage.
- Se S3 INCONCLUSIVO/FAIL: zero allocazione attiva. Allocazione attuale (80-90k passive + 5-10k buffer + 0 attivo) resta sigillata.

Decisione operativa post-S3 richiede atto separato del committente. Questa preregistrazione NON autorizza alcuna allocazione.

---

## 9. Timeline preregistrata

- 24/05 - 27/05 CEST: validazione committente preregistrazione S3 (atto separato).
- 28/05 - 02/06: implementazione script S3 Phase A (grid runner + leverage analyzer + bootstrap).
- 03/06 - 07/06: esecuzione S3 Phase A (walltime stimato 8-15 ore su sandbox standard).
- 08/06 - 11/06: falsificazione H1-H6, journal, sigillo SHA256, commit + push.
- 12/06: messaggio consulente con verdetto S3 Phase A.
- 13/06: deadline S1 originale (invariata per attività non leverage-dependent).
- 14/06+: roadmap S3 Phase B (F4/F5) o decisione operativa allocazione condizionale.

Deadline non vincolanti: slippage tollerato fino a +7gg con disclosure giornaliera nel journal.

---

## 10. Sigillo SHA256

SHA256 di questo file (computato post-write, prima del commit): da inserire in `.sha256` sibling. Modifiche retroattive vietate.

Vincoli irriducibili (invariati da S1):
- Append-only.
- No firma a nome Luigi senza validazione esplicita.
- No modifica retroattiva pre-23/05 22:00.
- No prompt-engineering del verdetto: H1-H6 vanno valutate esattamente come dichiarate qui.
- Validazione committente entro 27/05 23:59 CEST necessaria per procedere all'implementazione (§9).

---

## 11. Aperture esplicite

- Discussione committente ammessa su §3 (grid cardinalità: 432 trial × 3 fold = 1296 cerebro run è oneroso, valutare riduzione).
- Discussione committente ammessa su §4 H5 e H6 soglie precise (1.25 L*, IC 95% lower bound 0.5).
- Discussione committente ammessa su §8 soglie allocazione 15-20k / 10k.
- Discussione committente NON ammessa su universo (1037 fissato), fold setup (identici S1), o vincoli irriducibili §10.

Eventuali modifiche §3/§4/§8 in seguito a feedback committente saranno tracciate come `preregistration_s3_addendum_01_*.md` con SHA proprio, NON come edit di questo file.

---

Fine Pre-Registration S3 (versione iniziale).
