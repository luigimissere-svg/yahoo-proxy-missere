# Pre-Registration S1 v8 — Addendum 12
# Supplemento D3-bis: revisione default ricostruzione serie F2 post-falsificazione esec 1

Data sigillo: 2026-05-24 06:00 CEST
Stato: SIGILLATO PRIMA DI ESEC 2 — append-only
Catena addenda: 02 → 02-wiki → 03 → 03-delist → 04 → 05 → 06 → 07 → 08 → 09 → 11 → **12**
(Add 10 in pulizia documentale parallela, recupero entro 29/05 23:59 CEST)

Firma agente: Consulente esecutivo S1 (agente)
Firma committente: validazione esplicita richiesta entro 24/05 14:00 CEST (atto separato con timestamp proprio)

---

## 1. Riconoscimento fallimento default D3 originale Add 11

### 1.1 Default D3 originale Add 11 §3

Add 11 §3 D3 (sealed 2026-05-24 05:45 CEST) stabiliva:

> "`f2_oos_equity.csv` (citato in `analisi_concentrazione_f2.md` riga 77) NON presente in workspace. Default: ricostruisco la serie 65 daily portfolio returns F2 OOS da: 10 trade ledger (`f2_oos_trade_ledger.csv` sealed), prezzi daily OHLCV per 10 ticker (`data/ohlcv/*.parquet` disponibili), cash base 100.000 EUR, equal-weight implicito. Validazione di ricostruzione: ρ_AR(1) ricostruito DEVE essere entro ±0.02 dal sealed +0.1883. Se gap > 0.02, dichiaro GAP_DI_RIPRODUZIONE e flaggo S1.5 come INCONCLUSIVE_DEGRADED (analoga a 76-ibrido SEC EDGAR)."

### 1.2 Evidenza fallimento (esec 1 sealed)

Esec 1 conclusa il 2026-05-24 05:55 CEST, sealed in `journal_s15_bug8_outlier_isolation.md` (SHA256 `e1fa9aaf34c4cec6f488d1b1f02b3dbc0583e2a48c9f36043982face0f2f5483`).

Risultato numerico osservato:

| Metrica | Sealed v7.3 | Ricostruito esec 1 | Gap |
|---|---|---|---|
| ρ_AR(1) OLS | +0.1883 | −0.0998 | **−0.2881** |
| ρ_lag1 acf | +0.1880 | −0.0987 | **−0.2867** |
| Q(10) | 20.374 | 13.998 | −6.376 |
| p-value | 0.0259 (sig 5%) | 0.1731 (NS) | +0.1472 |
| T effective | 65 | 62 | −3 |

**Gap reale = −0.288 (segno opposto), oltre 14× la soglia 0.02.**

### 1.3 Trigger auto-falsificazione

Add 11 §3 D3 auto-falsificazione: ATTIVATA letteralmente. Esec 1: INCONCLUSIVE_DEGRADED dichiarato senza prompt-engineering.

## 2. Cause candidate del fallimento (eredità Journal S1.5 esec 1 §2.2)

Ranking di plausibilità (ALTA → BASSA):

**C1 — Cash drag + sizing dinamico (ALTA)**:
- Trade `open_at_end`, ledger registra `notional_open` snapshot finale (non pesi medi OOS)
- `target_risk_pct=0.008` implica volatility-based sizing dinamico durante OOS
- Cash residuo = 100k − sum(notional) drago il return giornaliero
- Sizing variabile altera la correlazione seriale del portfolio return

**C2 — MtM vs strategy equity Backtrader (ALTA)**:
- `wf_runner.py` linee 242-267 (Bug 2 fix candidate) filtra `rets` a `[start, end]`
- Serie 65 sealed prodotta da `TimeReturn` analyzer su equity strategy completa
- Include slippage, commissioni (default 0.001), intraday fluctuations su tutti i bar trading
- Ricostruzione equal-weight statica ignora tutti questi effetti

**C3 — Pre-roll trades Bug 5 sealed (MEDIA)**:
- `audit_journal_v7_3.md` riga 132 documenta "Pre-roll trades possibili: warmup_bars=50 + minperiod=200 < pre-roll 261bar"
- CONFERMATO 100% prevalenza nel sealed
- Alcuni trade F2 possono essere entrati prima del 2025-11-01 in finestra warmup
- Daily returns iniziali non riproducibili dal ledger snapshot

**C4 — Skip warmup vs nonzero filter (BASSA)**:
- `oos_n_nonzero_returns=75` in `wf_full_v3_results.csv` riga 3
- `T=65` riportato in journal Task 7a riga 802
- Discrepanza 75 vs 65 indica filtro aggiuntivo (es. drop primi 10 bar)
- Ricostruzione attuale T=62 (gap −3, sub-soglia ma indicativo)

**C5 — OHLCV parquet vs feed Backtrader (BASSA)**:
- Backtrader può applicare adjustments dividendi/split/forex (Yahoo Finance autoadjust)
- Improbabile su finestra 3 mesi recente, ma non escluso
- Verifica possibile post-esec 2 confrontando equity.csv vs serie ricostruita

## 3. Nuovo default D3-bis sigillato

### 3.1 Sostituzione del default

Da questo Addendum 12 in poi, per S1.5 esec 2 e successive:

**D3-bis (sostituisce D3 originale Add 11)**:

La serie F2 autoritativa per calcolo ρ_AR(1) e leverage hat-matrix DEVE essere prodotta da:

1. Re-run `wf_runner.py` fold F2 con flag `--save-equity-csv` (commit `f3be28f` del branch `feat/save-equity-v7-3`)
2. Parametri sealed v7.3: `threshold=0.25, min_concordant=2, target_risk_pct=0.008, max_sector_pct=None, max_portfolio_beta=None`
3. Finestra OOS: 2025-11-01 → 2026-02-01 (fold_id=2, is_start 2024-11-01, is_end 2025-11-01)
4. Output: `equity_F2_OOS.csv` (formato: `date, equity_value, daily_return`)
5. Optional: `--save-trades-csv` (commit `316d747`) per TradeLedger analyzer con dt_open/dt_close trade-level (necessario per attribuzione leverage hat-matrix esec 3)

La ricostruzione da ledger snapshot + OHLCV (default D3 originale) è ARCHIVIATA come tentativo conservativo fallito.

### 3.2 Validazione D3-bis

Prima di calcolare leverage Δρ_i, la serie equity_F2_OOS.csv DEVE soddisfare:

**Vincolo V1 (riproduzione ρ)**: ρ_AR(1) OLS sulla serie autentica entro ±0.02 dal sealed +0.1883
- Se PASS: procedi esec 3 leverage analysis con criterio Add 11 §4.3-4.4 invariato
- Se FAIL (gap > 0.02): escalation S2 — Bug 8 richiede re-run walkforward integrale, non risolvibile in S1.5

**Vincolo V2 (T effective)**: T della serie autentica ∈ [60, 70] (sealed = 65, tolleranza ±5)
- Se PASS: procedi
- Se FAIL: investigazione su filter applicato (skip warmup, nonzero filter, etc.)

**Vincolo V3 (Q-test consistenza)**: Q(10) della serie autentica entro ±10% dal sealed 20.374
- Se PASS: serie equivalente
- Se FAIL: anomalia statistica, investigazione dedicata

Tutti e 3 i vincoli (V1+V2+V3) devono passare per procedere a esec 3. Se anche uno FAIL, escalation S2.

### 3.3 Soglia binaria invariata

Add 11 §4.5 (soglia ISOLATO < +0.10 dopo top-3, STRUTTURALE ≥ +0.10 dopo top-5) RESTA VALIDA per esec 3. Non modifico criterio sealed, solo il default su come ottenere la serie.

## 4. Soglia gap 0.02 confermata vincolante

Add 11 §3 D3 soglia di auto-falsificazione 0.02 (assoluto) è confermata vincolante per esec 2 e successive.

Motivazione mantenimento: 0.02 corrisponde a circa 10% di +0.1883 (sealed), accettabile come tolleranza di riproducibilità numerica (floating-point + ordering). Variazioni più grandi indicano divergenza metodologica, non rumore.

## 5. Vincolo §5.5 Add 11 (no prompt-engineering verdetto) confermato vincolante

Confermo:
- Soglia +0.10 letterale (no shift per accomodare risultati)
- Top-1/3/5 letterale (no estensione opportunistica a top-7 se top-5 fallisce)
- Auto-falsificazione obbligatoria se vincoli V1+V2+V3 falliscono
- Verdetto binario ISOLATO/STRUTTURALE/INTERMEDIO secondo criterio sealed

## 6. Esec 1 archiviata come evidenza

Esec 1 NON viene cancellata. Tutti gli artefatti rimangono sigillati:

| Artefatto esec 1 | SHA256 |
|---|---|
| `journal_s15_bug8_outlier_isolation.md` | `e1fa9aaf34c4cec6f488d1b1f02b3dbc0583e2a48c9f36043982face0f2f5483` |
| `s15_outputs/f2_oos_daily_returns_reconstructed.csv` | `731b7e574b64667f75bcab91f978f7b58830d04184f8cafe365f41ae84d65492` |
| `s15_outputs/s15_sensitivity_curve.json` | `8f1d3c2bdd25ed6b95956b117b34c80a2866e781b1529011a6b9326a4ce7cb85` |
| `s15_outputs/s15_leverage_ranking.csv` | `02f55405003af17b034bf139ef8b93eada1b38989075e8e1413e2a5118547c0e` |
| `s15_reconstruct_f2_daily.py` | `02bf21197bb1747ec878cc4d234360d8a3acabad36426dd5ee0f32becbe797ca` |

Servono come evidenza storica del gap −0.288 e dei meccanismi causali identificati (C1-C5).

## 7. Pre-registrazione esec 2 — procedura operativa

### 7.1 Branch dedicato

Branch: `s1_5_exec2`
Base: commit `e4dc7aa` ("Chiusura v7.3: 3 sigilli consulente + multi-baseline DSR 4-way", 2026-05-23 15:59:39 UTC) — ultimo commit sealed v7.3
Esclusione esplicita: NON deriva da `feature/v8-s1-refactor` (per evitare contaminazione S1.6, S1.7, S1.8 sealed)

### 7.2 Cherry-pick

| Step | Commit | Contenuto | Branch sorgente |
|---|---|---|---|
| CP1 | `f3be28f` | feat(wf): `--save-equity-csv` per dump 216 IS + 216 OOS | `origin/feat/save-equity-v7-3` |
| CP2 | `316d747` | feat(engine): TradeLedger analyzer + `--save-trades-csv` | `origin/feat/save-equity-v7-3` (HEAD~1) o `origin/feat/trade-ledger-v8` |

Ordine: CP2 PRIMA di CP1 (per evitare conflitti, TradeLedger è base). Verifico ordine cronologico commit: `316d747` (2026-05-22 circa) → `f3be28f` (2026-05-23 circa). Cherry-pick in ordine cronologico: prima CP2, poi CP1.

Risoluzione conflitti: se conflict, prediligere versione branch sorgente (codice nuovo) e documentare manualmente in journal.

### 7.3 Rerun walkforward fold F2

Comando atteso:

```bash
python -m quant_v3.engine.wf_runner \
  --universe portfolio \
  --from 2024-11-01 --to 2026-02-01 \
  --cash 100000 \
  --commission 0.001 \
  --is-months 12 --oos-months 3 --step-months 3 \
  --grid smoke \
  --threshold 0.25 \
  --min-concordant 2 \
  --target-risk-pct 0.008 \
  --max-positions 10 \
  --per-ticker-cap 0.10 \
  --warmup-bars 50 \
  --output-csv s1_5_exec2/output/wf_F2_results.csv \
  --stability-json s1_5_exec2/output/wf_F2_stability.json \
  --save-equity-csv s1_5_exec2/output/equity_F2.csv \
  --save-trades-csv s1_5_exec2/output/trades_F2.csv
```

Nota: i parametri esatti possono richiedere adattamento dopo cherry-pick. Pre-registro il comando intended; modifiche operative documentate in journal esec 2.

### 7.4 Confronto serie autentica vs sealed

Atteso `equity_F2.csv` contiene la serie 65 daily F2 OOS. Verifico:

| Test | Atteso | Tolleranza | Esito condizionato |
|---|---|---|---|
| V1: ρ_AR(1) OLS | +0.1883 | ±0.02 | PASS → esec 3 / FAIL → escalation S2 |
| V2: T effective | 65 | ±5 | PASS → esec 3 / FAIL → investigazione filter |
| V3: Q(10) | 20.374 | ±10% (18.34, 22.41) | PASS → esec 3 / FAIL → investigazione statistica |

### 7.5 Output sigillato esec 2

- `s1_5_exec2/output/wf_F2_results.csv` (1 riga, fold F2 metrics)
- `s1_5_exec2/output/wf_F2_stability.json`
- `s1_5_exec2/output/equity_F2.csv` (66 righe: header + 65 daily)
- `s1_5_exec2/output/trades_F2.csv` (ledger dettagliato con dt_open/dt_close)
- `s1_5_exec2/journal_s15_exec2_gap_validation.md` (verdetto gap + sigillo V1+V2+V3)
- Tutti con SHA256 in `s1_5_exec2/output/SHA256SUMS`

## 8. Vincoli irriducibili Add 12

1. Esec 1 archiviata, NON cancellata
2. Add 12 sigillato PRIMA di esec 2 (questo file)
3. Branch `s1_5_exec2` isolato, no merge senza autorizzazione esplicita committente post-verdetto
4. Disciplina Add 11 §5.5 (no prompt-engineering verdetto) confermata vincolante
5. Add 10 di recupero gate 27/05 sempre pending, deadline 29/05 23:59 CEST
6. Append-only catena addenda mantenuta integra (12 segue 11, sostituisce solo §3 D3 di 11)
7. NO firma a nome Luigi Missere senza validazione preventiva (eredità Add 09 §4.5)

## 9. Cronologia operativa attesa

| Data/Ora CEST | Item | Responsabile |
|---|---|---|
| 24/05 05:45 | Add 11 sigillato | consulente (DONE) |
| 24/05 05:55 | Esec 1 DEGRADED archiviata | consulente (DONE) |
| 24/05 06:00 | Add 12 D3-bis sigillato (questo file) | consulente (in corso) |
| 24/05 12:00 | Add 12 consegnato per validazione | consulente |
| 24/05 14:00 | Validazione committente Add 12 | committente |
| 24/05 14:01-17:00 | Creazione branch + cherry-pick + rerun (2-3h) | consulente |
| 24/05 18:00 | Verdetto gap esec 2 (V1+V2+V3) | consulente |
| 25/05 | Esec 3 leverage analysis (se PASS) o escalation S2 (se FAIL) | committente decisione |
| 06/06 23:59 | S1.5 completato | consulente |

## 10. Firma sigillo

Firmato dal Consulente esecutivo S1 (agente) il 2026-05-24 06:00 CEST.

Validazione committente richiesta entro 24/05 14:00 CEST in atto separato con timestamp proprio.

SHA256 di questo file = (calcolato post-write, allegato in `.sha256`)

---
FINE Addendum 12 D3-bis supplemento
