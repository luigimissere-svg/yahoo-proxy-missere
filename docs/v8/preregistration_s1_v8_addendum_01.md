# Addendum 01 a Pre-registration S1 v8

**Data**: 23/05/2026 18:49 CEST
**Stato**: sigillato append-only
**Riferimento**: `preregistration_s1_v8.md` (SHA256 10f8c4cecf37e7f365b971e62ac2ca3e7f4ee260bbed7f64cedddf1bd042214f)

---

## Scope dell'addendum

Disciplina append-only: la pre-registration originale prevedeva 3 obiettivi tecnici + 3 discipline metodologiche senza specificare l'**indice di base** né la **fonte dati universo**. Questo addendum sigilla le due decisioni operative emerse al kick-off, prima di toccare codice.

---

## Decisione 1 — Indice di base v8

**Sigillato**: S&P 500 (USA)

Motivazione:
- Liquidità superiore (slippage modellabile più accuratamente)
- Dati storici di qualità migliore (Yahoo Finance copre S&P 500 con minor numero di gap)
- Riconoscibile pubblicamente — l'audit indipendente S4 sarà più facile da difendere

Trade-off accettato:
- Il momentum mega-cap USA è proprio dove l'overfitting strutturale di v7.4 si è manifestato (DSR Combinatorial 0.0004). Sigillo qui che il cambio universo da 35 ticker mega-cap a S&P 500 (~500 ticker) ha effetto atteso di **ridurre** il rapporto N_trial / universo, e quindi DSR Combinatorial dovrebbe migliorare per ragioni strutturali (non per skill aggiunto). Questo va distinto chiaramente nei risultati S3.

---

## Decisione 2 — Fonte dati composizione storica

**Sigillato**: snapshot S&P 500 attuale (23/05/2026) + delisting manuale per il periodo 2020-2026

Procedura operativa:
1. Acquisizione composizione S&P 500 al 23/05/2026 (Yahoo Finance o Wikipedia snapshot)
2. Ricerca manuale dei principali delisting / index removal nel periodo 01/01/2020 → 23/05/2026
3. Lista target: minimo 15 ticker delistati/usciti, con date di rimozione
4. File output: `universe_v8_sp500_pit.csv` con colonne `ticker, added_date, removed_date, reason`

Casi noti da includere (lista non esaustiva, da espandere in S1.1):
- Silicon Valley Bank (SIVB) — fallimento marzo 2023
- Signature Bank (SBNY) — fallimento marzo 2023
- First Republic Bank (FRC) — fallimento maggio 2023
- Bed Bath & Beyond (BBBY) — fallimento aprile 2023
- Twitter (TWTR) — delisting ottobre 2022 (acquisita da Elon Musk)
- Activision Blizzard (ATVI) — acquisita da Microsoft ottobre 2023
- Splunk (SPLK) — acquisita da Cisco marzo 2024
- VMware (VMW) — acquisita da Broadcom novembre 2023
- Seagen (SGEN) — acquisita da Pfizer dicembre 2023
- ... (espandere a 15+ in S1.1)

---

## Trade-off accettato esplicitamente

Questa procedura è **approssimazione**, non gold standard. Documentato come tale.

Cosa NON cattura:
- Microcap aggiunti/rimossi senza tracciamento
- Variazioni intra-mese della composizione
- Decisioni discrezionali del comitato S&P (riclassificazioni settoriali)

Cosa cattura sufficientemente bene:
- I principali default/M&A degli ultimi 6 anni
- Selection bias da "i 35 ticker mega-cap di v7.4 erano tutti vivi al 23/05/2026"

Pre-impegno: se l'audit indipendente S4 contesta la procedura come insufficiente, accetto rework S2 (non re-run S3) con fonte gold standard (Refinitiv/Bloomberg) come scope aggiuntivo, non come falsificazione di S1.

---

## Impatto su criteri di successo S1

Criterio S1.2 originale: "Almeno 3 ticker presenti in 2024 e non in 2026 (delisting, M&A, fallimenti)"

Aggiornato in: **Almeno 15 ticker delistati/usciti dall'S&P 500 nel periodo 2020-2026 documentati con data e ragione**.

Tutti gli altri criteri (S1.1, S1.3-S1.8) restano invariati.

---

## Out-of-scope confermato

Non in S1, anche con questo addendum:
- Microcap / Russell 2000 (mai considerato)
- Reconstitution storiche pre-2020
- Dati su splits, dividendi, corporate actions diverse da M&A/delisting

---

**Firmato**: Luigi Missere + Perplexity Computer
**Timestamp sigillo**: 23/05/2026 18:49 CEST
**Hash da committare al merge**: SHA256 di questo file
