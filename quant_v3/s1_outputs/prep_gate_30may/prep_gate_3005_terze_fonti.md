# Prep Gate 30/05 — Terze fonti candidate per cross-check cluster 2022

Data: 24/05/2026 — 01:00 CEST
Firma esecutiva: Consulente esecutivo S1 (agente)
Status: DRAFT preparatorio, non sigillato pre-reg

Scope: identificazione e shortlist delle terze fonti non-Wikipedia
candidate per cross-check del cluster 2022 (Add 09 §3) e — opportunamente
— per promozione retroattiva categoria BLACKROCK_DRIFT (Add 09 §2).
Vincolo applicato: NO Wikipedia (mandato 21:03 §5, ribadito Add 07).

## 1. Requisiti funzionali della terza fonte

Per qualificarsi come terza fonte valida al gate 30/05, deve fornire:

| # | Requisito | Obbligatorio | Note |
|---|---|---|---|
| 1 | Lista constituenti S&P 500 con effective_date addition/removal | SÌ | Granularità giornaliera, copertura 2020-2026 |
| 2 | Indipendente da Wikipedia (no scraping Wiki upstream) | SÌ | Vincolo committente |
| 3 | Indipendente da iShares IVV holdings (no derivazione da nostro dataset 58-puro) | SÌ | Per essere terza fonte, non seconda |
| 4 | Replicabile (manifesto SHA256 o accesso programmatico verificabile) | SÌ | Mandato §2 pre-commitments |
| 5 | Copertura cluster 2022 completa (12/12 mesi) | SÌ | Per chiudere il cluster |
| 6 | Costo accessibile o accesso istituzionale | NO | Trade-off costo/valore documentato |

## 2. Shortlist candidate

### 2.1 S&P Dow Jones Indices API ([spglobal.com/spdji](https://www.spglobal.com/spdji/en/landing/topic/api-data-solutions/))

| Attributo | Valore |
|---|---|
| Tipo | Provider ufficiale (source-of-truth) |
| Copertura | Tutti gli indici S&P branded, EOD data, storico completo |
| Requisito 1 | SÌ — constituenti con metadati ufficiali |
| Requisito 2 | SÌ — è la fonte upstream di tutti gli altri |
| Requisito 3 | SÌ — produttore originale dell'indice |
| Requisito 4 | SÌ — RESTful API documentata |
| Requisito 5 | SÌ |
| Costo | ALTO — sottoscrizione enterprise, prezzo su richiesta (tipico $5-50k/anno) |
| Tempo onboarding | 2-4 settimane (custom product, client relationship manager) |
| Qualità | MASSIMA — source-of-truth ufficiale |

**Valutazione**: gold standard se accessibile, ma costo + tempo onboarding
non compatibili con deadline gate 30/05 (~6 giorni). Da escludere per
questo gate, considerare per S2 se budget consente.

### 2.2 Norgate Data ([norgatedata.com](https://norgatedata.com))

| Attributo | Valore |
|---|---|
| Tipo | Provider commerciale di terza parte |
| Copertura | S&P 500 Current & Past constituents con effective_date, 30+ anni |
| Requisito 1 | SÌ — `NorgateIndexConstituentTimeSeries` per ogni simbolo |
| Requisito 2 | SÌ — fonte indipendente, non derivata da Wikipedia |
| Requisito 3 | SÌ — universo indipendente da iShares |
| Requisito 4 | SÌ — Python API + Norgate Data Updater (manifest verificabile) |
| Requisito 5 | SÌ — copertura giornaliera completa |
| Costo | MEDIO — trial gratuito 21 giorni, poi Platinum/Diamond per historical constituents (~USD 500-1500/anno) |
| Tempo onboarding | 1-2 giorni (account + installazione Updater + download) |
| Qualità | ALTA — reputazione consolidata in community quant |

**Valutazione**: candidato preferito per gate 30/05. Trial 21 giorni copre
ampiamente il fabbisogno gate (anche se trial limitato a 2 anni di storico —
verificare se copre 2022). Se trial non basta, sottoscrizione Platinum
(~$500-1000) accettabile vs valore audit.

**ATTENZIONE**: documentazione Norgate dichiara "trial 21 giorni con
accesso a 2 anni di storico". Per il cluster 2022 servono ~4 anni di
storico (2022 retrospettivo). Verifica obbligatoria prima del download:
trial copre 2022 o serve sottoscrizione attiva.

### 2.3 WRDS Compustat ([wrds-www.wharton.upenn.edu](https://wrds-www.wharton.upenn.edu/classroom/sp500-introduction/over-time/))

| Attributo | Valore |
|---|---|
| Tipo | Database accademico/professionale aggregato |
| Copertura | S&P 500 Constituents Over Time, storico completo |
| Requisito 1 | SÌ — table `crsp.msp500list` o `comp.idxcst_his` |
| Requisito 2 | SÌ — fonte primaria S&P + CRSP, non Wikipedia |
| Requisito 3 | SÌ |
| Requisito 4 | SÌ — query SQL replicabili, snapshot scaricabili |
| Requisito 5 | SÌ |
| Costo | VARIABILE — accesso istituzionale gratuito se affiliato, altrimenti $25-50k/anno enterprise |
| Tempo onboarding | 1-7 giorni se affiliazione esiste, 30+ giorni altrimenti |
| Qualità | MASSIMA — usato accademicamente per backtest survivorship-bias-free |

**Valutazione**: gold standard accademico. Accessibile solo se il
committente ha affiliazione istituzionale (università, ricerca, etc.).
Da verificare con committente — possibile fonte gratuita di altissima
qualità se affiliazione esiste.

### 2.4 GitHub `fja05680/sp500` ([github.com/fja05680/sp500](https://github.com/fja05680/sp500))

| Attributo | Valore |
|---|---|
| Tipo | Dataset open source mantenuto da privato |
| Copertura | S&P 500 Historical Components & Changes 1996-presente, formato CSV |
| Requisito 1 | SÌ — effective_date di ogni cambio constituents |
| Requisito 2 | SÌ — autore dichiara metodologia indipendente da Wikipedia (verifica obbligatoria) |
| Requisito 3 | SÌ |
| Requisito 4 | SÌ — repository pubblico con commit history, SHA verificabile |
| Requisito 5 | SÌ — granularità giornaliera |
| Costo | ZERO |
| Tempo onboarding | <1 ora — download CSV |
| Qualità | MEDIA — dataset community, no SLA, da validare cross-check |

**Valutazione**: opzione gratuita immediatamente disponibile. **RISCHIO
CRITICO**: alcuni dataset GitHub di S&P 500 storici sono in realtà
derivati da Wikipedia (vedi articolo RobotWealth/InteractiveBrokers che
documenta scraping Wikipedia come base). Verifica obbligatoria della
metodologia di costruzione del repository prima dell'uso — se deriva da
Wikipedia, fonte SQUALIFICATA per vincolo 5.

### 2.5 LSEG / Refinitiv Compustat Fundamentals

| Attributo | Valore |
|---|---|
| Tipo | Provider commerciale enterprise |
| Costo | ALTO — sottoscrizione enterprise |
| Tempo onboarding | 2-6 settimane |

**Valutazione**: stesso ordine di S&P DJI ufficiale, esclusa per gate 30/05
per stessi motivi.

## 3. Decisione raccomandata (sub iudice committente)

### 3.1 Path operativo proposto

**Step 1 (entro 26/05)**: verifica metodologia `fja05680/sp500` GitHub
- Leggere README e source files del repository
- Verificare se i dati derivano da Wikipedia (squalifica) o da S&P
  ufficiale + cross-check (idoneo)
- Se idoneo, scaricare CSV e calcolare SHA256
- Costo zero, tempo <2h

**Step 2 (entro 27/05)**: se `fja05680/sp500` squalificato, account
Norgate trial 21 giorni
- Verifica esplicita che il trial copre 2022 (4 anni di storico)
- Se sì: download cluster 2022 via API Python
- Se no: valutare sottoscrizione Platinum ~$500-1000 per 1 mese
- Costo: zero (trial) o ~$500-1000 (sottoscrizione mensile)
- Tempo onboarding: 1-2 giorni

**Step 3 (parallelo, entro 28/05)**: verifica con committente disponibilità
affiliazione WRDS
- Se committente ha accesso istituzionale → opzione gold standard gratuita
- Se no → procedere con Step 1+2

**Step 4 (gate 30/05)**: cross-check operativo
- Estrazione lista constituenti S&P 500 per ciascun mese 2022 (12 mesi)
- Diff vs PIT v8 esploso per 2022 (già calcolato)
- Diff vs Wayback IVV per i 6 mesi 2022 Wayback (già calcolato)
- Calcolo nuovo ratio cluster 2022 con denominatore "vera lista S&P 500"
- Promozione retroattiva BLACKROCK_DRIFT: le 107 ADDED_INTRA_PERIOD
  ri-valutate

### 3.2 Decisione richiesta al committente

Tre opzioni per il committente:

**Opzione A — Zero costo, alto rischio**: usare `fja05680/sp500` GitHub
dopo verifica metodologica. Se la verifica conferma indipendenza da
Wikipedia, fonte gratuita e immediata. Se rivela dipendenza Wiki,
squalifica e fallback Opzione B.

**Opzione B — Costo medio, basso rischio**: sottoscrizione Norgate
Platinum 1 mese (~$500-1000). Garanzia di qualità, replicabilità, e
copertura completa cluster 2022. Tempo onboarding 1-2 giorni.

**Opzione C — Affiliazione WRDS gratuita** (se committente ha accesso):
gold standard accademico, costo zero, copertura completa.

### 3.3 Default operativo (se nessuna decisione committente entro 26/05 18:00)

In assenza di decisione esplicita, eseguo **Opzione A** (verifica
`fja05680/sp500`) entro 26/05 e comunico esito + raccomandazione binaria
A-mantenuta o B-fallback al committente per decisione finale.

## 4. Calendario operativo proposto

| Data | Attività | Responsabile |
|---|---|---|
| 24/05 (oggi) | Sigillo audit journal v8 + commit prep terze fonti | Esecutivo |
| 24/05 (oggi) | Decisione opzione A/B/C dal committente | Committente |
| 26/05 entro 18:00 | Verifica fja05680/sp500 metodologia (opzione A) o setup Norgate (opzione B) | Esecutivo |
| 28/05 entro 18:00 | Download dati e SHA256 manifest | Esecutivo |
| 30/05 mattina | Cross-check operativo + diff cluster 2022 | Esecutivo |
| 30/05 pomeriggio | Verdetto cluster 2022 + promozione BLACKROCK_DRIFT | Esecutivo + Committente |

## 5. Append-only

Questo documento è prep preparatorio, non sigillato pre-reg. Diventa
input al gate 30/05 quando il committente sceglie opzione A/B/C e
fornisce eventuale affiliazione WRDS. Decisioni finali saranno
documentate in Addendum 10 del gate 30/05.
