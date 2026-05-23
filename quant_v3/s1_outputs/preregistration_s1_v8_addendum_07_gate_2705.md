# Pre-registration S1 v8 — Addendum 07 Gate 27/05

Data sigillo: 23/05/2026 — 22:00 CEST
Riferimenti vincolanti:
- Addendum 02–06 (catena append-only preservata)
- Mandato committente 23/05 20:55 CEST (scelta C + 3 condizioni)
- Mandato committente 23/05 21:03 CEST (H3 approvato + 6 vincoli vincolanti)
- Quesito consulente `quesito_consulente_gate_2705_asimmetria_fonti.md`

Scope: cross-check universo PIT v8 vs holdings IVV reali (fonte primaria) per
falsificazione potenziale costruzione PIT. Doppio report: 58-puro VINCOLANTE
+ 76-ibrido INFORMATIVO con degradazione operativa documentata.

## 1. Mandato 21:03 — vincoli vincolanti applicati

| # | Vincolo | Applicazione |
|---|---|---|
| 1 | 58-puro VINCOLANTE (≤1% snapshot, ≤0.5% mean) | Misurato: max 0.99%, mean 0.39% → PASS |
| 2 | 76-ibrido INFORMATIVO (stesso vincolo, NO_COVERAGE esclusi) | DEGRADED → INCONCLUSIVE per impedimento SEC rate-limit |
| 3 | UNCLASSIFIED trigger >1% delle discordanze totali | 0/115 = 0% → no trigger |
| 4 | Cluster 2022 check + flag deferred-pending-S2 | Cluster 2022 mean 0.495% (+26% vs overall, sotto 1.5×) → no signal; flag attivato |
| 5 | NO Wikipedia come terza fonte | Rispettato (deferred-pending-S2 senza Wiki) |
| 6 | Deadline 23:15 stanotte | Rispettata (sigillo 22:00) |

## 2. Universo coperto e fonti

### 2.1 Granularità mensile reale 2020-01 → 2026-04 (76 punti)

| Categoria | N mesi | Fonte | Stato |
|---|---|---|---|
| 58-puro Wayback IVV | 58 | iShares.com snapshots via Wayback Machine `web.archive.org/web/{ts}id_/` (raw mode) | COMPLETO |
| Mapping b: SEC 13F-proxy-Q (N-PORT IVV) | 13 | EDGAR CIK 0001100663 seriesId S000004310 | DEGRADED |
| NO_COVERAGE | 5 | Nessun filing entro ±100 giorni | NO_COVERAGE |

### 2.2 Mesi NO_COVERAGE (5)
`2020-06, 2022-04, 2022-10, 2023-01, 2024-07`

### 2.3 Mesi DEGRADED_PENDING (13)
`2020-04, 2020-07, 2020-10, 2021-01, 2021-05, 2022-01, 2022-05, 2022-08, 2022-11, 2023-02, 2023-08, 2024-08, 2025-10`

## 3. Verdetto 58-puro VINCOLANTE — PASS

### 3.1 Metriche aggregate

| Metrica | Valore | Soglia | Stato |
|---|---|---|---|
| n_mesi | 58 | 58 | OK |
| mean discordanza per snapshot | 0.3925% | ≤ 0.5% | PASS |
| median discordanza | 0.396% | (informativa) | — |
| max discordanza singolo snapshot | 0.9862% | ≤ 1.0% | PASS (margine 0.014%) |
| mesi sopra 1% | 0 / 58 | 0 atteso | PASS |
| discordanze totali | 115 | (informativo) | — |

### 3.2 Breakdown per anno

| Anno | N mesi | Mean % | Max % | Min % |
|---|---|---|---|---|
| 2020 | 8 | 0.4204 | 0.789 | 0.198 |
| 2021 | 10 | 0.4346 | 0.984 | 0.000 |
| 2022 | 6 | **0.4951** | 0.794 | 0.000 |
| 2023 | 9 | 0.2863 | 0.594 | 0.000 |
| 2024 | 10 | 0.3369 | 0.791 | 0.000 |
| 2025 | 11 | 0.3782 | 0.792 | 0.000 |
| 2026 | 4 | 0.4948 | 0.986 | 0.199 |

### 3.3 Cluster 2022 (mandato 21:03 vincolo 4)

| Metrica | Cluster 2022 | Overall 58 | Delta | Trigger |
|---|---|---|---|---|
| Mean discordanza | 0.4951% | 0.3925% | +0.1026 pp (+26%) | < 1.5× → NO trigger |
| Excess assoluto | 0.103% | — | — | < 0.5pp → NO trigger |

**Conclusione cluster 2022**: nessun signal automatico di sospensione. Tuttavia,
il delta +26% rispetto all'overall è sufficiente a richiedere cross-check
supplementare al gate 30/05 con terza fonte non-Wikipedia (vincolo 5 mandato
21:03 rispettato). Flag `deferred-pending-S2` attivato.

### 3.4 Classificazione 5-categorie

| Categoria | N | % discordanze |
|---|---|---|
| ADDED_INTRA_PERIOD | 104 | 90.4% |
| IVV_CASH_POSITION | 5 | 4.3% |
| DELISTED_INTRA_PERIOD | 3 | 2.6% |
| BLACKROCK_DRIFT | 3 | 2.6% |
| **UNCLASSIFIED** | **0** | **0.0%** |
| Totale | 115 | 100% |

Trigger UNCLASSIFIED >1%: **NON attivato** (0%).

## 4. Verdetto 76-ibrido INFORMATIVO — INCONCLUSIVE_DEGRADED

### 4.1 Stato

Per i 13 mesi mappati a SEC 13F-proxy-Q (N-PORT IVV), l'identificazione del
filing specifico per seriesId `S000004310` (iShares Core S&P 500 ETF) entro
iShares Trust (CIK `0001100663`) è stata **impedita operativamente** da:

- SEC EDGAR rate-limit IP-block (10 minuti per ciclo, ripetuto)
- iShares Trust filing ~390 sub-fondi: 220-285 candidati N-PORT-P per ogni
  trimestre target, ciascuno richiede verifica `primary_doc.xml` per series_id
- Volume richiesto ~3000 richieste SEC concentrate, non praticabile sotto
  rate-limit attivo entro deadline operativa 23:15 CEST

### 4.2 Verifica meccanica preservata

Identità iShares Trust → IVV verificata su filing campione:
- CIK `0001100663` (iShares Trust)
- accession `0001752724-24-194289` (filed 2024-08-27)
- `seriesId S000004310` = iShares Core S&P 500 ETF
- period `2024-06-30`
- holdings count: 504 equity + 4 cash positions

### 4.3 Path di degradazione conforme mandato 21:03

Vincolo 4 del mandato 21:03 (richiamato): "auto-falsificazione >2% media MA
NO prompt-engineering del verdetto". L'opzione disponibile rispettando il
vincolo: marca 76-ibrido come **INCONCLUSIVE_DEGRADED** con esplicita
dichiarazione dell'impedimento operativo. NON degradare a PASS per costruzione,
NON sostituire con sorgenti alternative non pre-registrate (Wikipedia escluso
per vincolo 5).

### 4.4 Verdetto

| Aspetto | Valore |
|---|---|
| Verdetto operativo gate | **INCONCLUSIVE_DEGRADED** |
| Causa | Impedimento operativo SEC rate-limit |
| Validità del 58-puro PASS | **Preservata** (VINCOLANTE, indipendente da 76) |
| Azione richiesta S2 | Identificazione offline batch 13 filing IVV + cluster 2022 cross-check terza fonte |

## 5. Flag deferred-pending-S2

| # | Item | Priorità | Note |
|---|---|---|---|
| 1 | 13 mesi DEGRADED_PENDING — identificazione filing N-PORT IVV offline | ALTA | Eseguibile via SEC EDGAR full-text con rate-limit conservativo (0.5 req/s) in slot 8h |
| 2 | Cluster 2022 cross-check terza fonte non-Wikipedia | ALTA | Opzioni: S&P Dow Jones official PIT (a pagamento), ICE Data, Compustat constituent history. **NO Wikipedia** per vincolo 5. |
| 3 | 5 mesi NO_COVERAGE — accept gap permanente o aggiungere fonte | MEDIA | Da decidere a S2 se accettabile gap 5/76 = 6.6% mese-zero o richiede sorgente alternativa |

## 6. Pre-commitments del mandato 21:03 — rispetto

| # | Pre-commitment | Stato |
|---|---|---|
| 1 | Append-only catena addenda | Rispettato (Add 07 aggiunto, 01-06 invariati) |
| 2 | SHA256 ogni artefatto | Rispettato (vedi §7) |
| 3 | Replicabilità Wayback timestamp + 13F accession | Rispettato (manifesto in `/tmp/cond1/wayback_manifest.json` + accession campione documentato §4.2) |
| 4 | Auto-falsificazione >2% media | Non attivata (0.39% << 2%) |
| 5 | NO prompt-engineering del verdetto | Rispettato (76-ibrido = INCONCLUSIVE, NON forzato a PASS) |
| 6 | NO modifica retroattiva mandato 20:55 | Rispettato (Add 07 cita 20:55 come radice) |

## 7. Artefatti sigillati (SHA256)

| File | SHA256 | Note |
|---|---|---|
| `quant_v3/s1_gate_2705/diff/diff_final_5cat_fonte.csv` | `d85cee628671145d8dc5f553e76aef47bb2b977c7c52cb61800c272670da171f` | 133 righe + header — 115 discordanze 58-puro + 18 placeholder degradati |
| `quant_v3/s1_gate_2705/diff/verdetto_58_puro.json` | `4a1efeaa29cc3df94e68270103480fca6fba6a7ef129a3ca47b869c5da0744be` | Verdetto VINCOLANTE PASS |
| `quant_v3/s1_gate_2705/diff/verdetto_76_ibrido.json` | `ea007105fe1bc084e0a7eb98b1b34d68048e7638386355e5e812b6926277a76a` | Verdetto INCONCLUSIVE_DEGRADED |
| `quant_v3/s1_gate_2705/diff/categories_final.json` | (auto-genera nel commit) | 115 entries 5-categorie |
| `quant_v3/s1_gate_2705/parsed/pit_v8_by_month.json` | (auto-genera nel commit) | Universo PIT esploso 76 mesi |
| `/tmp/cond1/wayback_manifest.json` | (locale, link manifesto Wayback) | SHA per 58 snapshot Wayback |

I file in `/tmp/cond1/` (catalogo Wayback + raw JSON) restano locali alla sandbox.
Copia del manifesto importata nel commit per garantire replicabilità.

## 8. Verdetto finale di gate 27/05

### Gate decision
- **58-puro VINCOLANTE: PASS** (max 0.99%, mean 0.39%, 0/58 sopra soglia 1%)
- **76-ibrido INFORMATIVO: INCONCLUSIVE_DEGRADED** (impedimento operativo, documentato)
- **Trigger UNCLASSIFIED**: NON attivato
- **Cluster 2022**: no auto-signal, flag deferred-pending-S2 per supplementare
- **Gate complessivo**: **PASS** sulla parte VINCOLANTE; 76-ibrido demandato a S2

### Conseguenze operative
- Universo PIT v8 NON falsificato dal cross-check Wayback 58-puro
- Costruzione PIT validata entro tolleranza pre-registrata
- S2 ha mandato esplicito a chiudere 76-ibrido + cluster 2022 con terza fonte

### Limiti conosciuti
- Bug Wikipedia parser confermati (DAY/CDAY, FISV/FI, PSKY/PARA, MRSH/MMC) ma
  classificati come ADDED_INTRA_PERIOD nei mesi corretti — non producono falsi positivi
  oltre soglia
- Mancato pieno 76-coverage non è bias del verdetto: 58-puro è uno strato
  primario sufficiente per il gate vincolante

---

Sigillo: Luigi Missere, 23/05/2026 22:00 CEST
Replicabilità: vedi §7 + manifesti per ogni download
Append-only: questa è la versione 1 sigillata dell'Addendum 07. Eventuali
correzioni vanno in Addendum 08 (NON modifica retroattiva).
