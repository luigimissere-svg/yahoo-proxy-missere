# Gate 30/05 — Verifica metodologica Opzione A fja05680/sp500 + diagnosi fallback B Norgate

Data: 2026-05-24 06:10 CEST
Riferimento mandato: decisione committente 24/05/2026 05:49 CEST ("Decisione terze fonti gate 30/05 — Opzione A con fallback B")
Vincoli applicati: mandato 21:03 §5 (NO Wikipedia) e §6 (non-circolarità cross-check)

---

## 1. Opzione A — fja05680/sp500 — VERDETTO: SQUALIFICATA

### 1.1 Evidenza primaria (README repository pubblico)

Fonte: `https://github.com/fja05680/sp500` (fetched 2026-05-24 06:05 CEST)

Citazioni testuali letterali del README:

| Citazione | Localizzazione |
|---|---|
| "Current List of S&P 500 companies retrieved from the **Wikipedia**: sp500.csv" | README §1 |
| "Every couple of months, **I use the S&P 500 Wikipedia page** and update `sp500_changes_since_2019.csv` with any changes that have occurred to the index." | README §3 metodologia |
| "The first thing I do when I update is to **compare my latest entry to current Wikipedia page** for S&P 500. I see what the differences are." | README §3 metodologia |
| "**Wikipedia shows 'Selected Changes'** not all changes" | README §3 |
| "**Google search** to get exact dates and the story of what happened" | README §3 |
| Notebook `sp500.ipynb`: "retrieves current S&P 500 composition **from Wikipedia** and outputs sp500.csv" | README struttura |

### 1.2 Periodo critico cluster 2022

Cluster 2022 cade nel periodo "since 2019" coperto da `sp500_changes_since_2019.csv`. Questo file è esplicitamente aggiornato da:
- Wikipedia (fonte primaria)
- Google search (fonte non istituzionale, non sistematica)

NON è coperto dal file originale Andreas Clenow 1996-2019 (che è il solo segmento potenzialmente indipendente).

### 1.3 Verdetto

Violazione mandato 21:03 §5 (NO Wikipedia) e §6 (non-circolarità cross-check):

- Il repository è derivato direttamente da Wikipedia per il periodo cluster 2022
- Non costituisce terza fonte indipendente
- Non risolve l'asimmetria di fonti documentata in Add 07-09

**Opzione A SQUALIFICATA per gate 30/05.**

### 1.4 Documentazione audit

Decisione documentata in audit journal v8 con timestamp 2026-05-24 06:10 CEST. Trigger fallback Opzione B.

## 2. Opzione B — Norgate Platinum trial — DIAGNOSI CRITICITÀ

### 2.1 Criticità 1: copertura trial limitata a 2 anni

Fonti citate:

| Fonte | Citazione | URL |
|---|---|---|
| Norgate FAQ ufficiale | "History is initially provided back to 1st January **10 years ago (or 20)**. Each year after that, on 1st January, the history extent is re-set to 10 years (or 20)." | norgatedata.com/data-package-faq.php |
| Concretum Group 2025-12-17 | "Norgate offers a **21-day free trial with access to two years of historical data**." | concretumgroup.com (Norgate Python tutorial) |
| Stator-AFM 2018-09-18 | "A free trial allows for an **abbreviated data history** to be updated for 3 weeks." | stator-afm.com |

**Diagnosi**: il trial gratuito 21 giorni ha **solo 2 anni di storia** (= 2024-05 → 2026-05 rispetto a oggi). Cluster 2022 cade FUORI dalla finestra trial.

Per accedere a dati 2022 serve subscription **Platinum o Diamond** (10 o 20 anni di storia), NON il trial.

### 2.2 Criticità 2: nessun dump tabellare disponibile

Da Norgate FAQ:

> "Information concerning historical index membership is **only available to subscribers (at Platinum level or above)** who are using a back-testing/analysis platform such as AmiBroker, RealTest, Wealth-Lab, Python or Zipline that can be linked to our database via a plugin. **There are no lists showing historical additions to, or removals from, an index. Nor are there are any lists showing constituents at year-end.** Instead, the plugins can deliver a true/false answer to the question of whether any stock (either currently-listed or delisted) was a member of an index on any day."

**Diagnosi**: per fare cross-check cluster 2022, servirebbe:
- Subscription Platinum (~$500-1000/mese stimato — verifica pricing in fase 2.3)
- Installazione Norgate Data Updater + plugin Python
- Query programmatica mese-per-mese su ticker S&P 500 candidati (∼500 ticker × 12 mesi = 6.000 query API)

NON è un dataset CSV scaricabile in un colpo. Richiede setup tecnico + sviluppo script.

### 2.3 Costi e tempi stimati

Pricing Platinum/Diamond non chiaramente esposto sulle pagine pubbliche raggiunte; price calculator richiede selezione di prodotto e periodo. Cifre tipicamente citate in community algotrading 2023-2025: $500-1000/mese USD per Platinum US Equities + Indices.

Tempi onboarding:
- Account creation + email verification: <1 ora
- Download + install Norgate Data Updater (Windows native, Wine su Linux): 1-2 ore
- Download iniziale 10 anni history: 2-6 ore (cluster 2022 incluso)
- Setup plugin Python + script query: 2-4 ore sviluppo
- Esecuzione 6.000 query mese×ticker cluster 2022: 1-2 ore

**Totale realistico: 1-2 giorni lavorativi + costo licenza pagato (non gratuito).**

### 2.4 Verdetto fallback B

Opzione B Norgate è **TECNICAMENTE PRATICABILE** (ha i dati cluster 2022 a livello Platinum), ma:

1. **Trial 21 giorni NON copre cluster 2022** (2 anni di storia, esclude 2022) → trial inutile per gate 30/05
2. **Subscription Platinum richiesta**, costo $500-1000/mese USD (decisione spesa committente)
3. **No dump tabellare**, serve sviluppo script Python query API
4. **Tempo onboarding 1-2 giorni lavorativi**, compatibile con deadline 29/05 12:00 CEST (ma stretto)

Mandato 24/05 05:24 CEST §4 (matrice valutazione) dava Norgate B "trial 21 giorni" come fallback gratuito. La verifica conferma che il **trial NON è sufficiente**. Per gate 30/05 con Opzione B serve subscription pagata.

## 3. Esito complessivo e proposta decisione committente

### 3.1 Stato fonti

| Opzione | Stato | Motivazione |
|---|---|---|
| A fja05680/sp500 | SQUALIFICATA | Wikipedia-dependent per periodo 2019+ |
| B Norgate Platinum trial | INSUFFICIENTE | Trial 21gg copre solo 2 anni, esclude 2022 |
| B' Norgate Platinum subscription | PRATICABILE PAGATA | $500-1000/mese, setup 1-2gg, cluster 2022 coperto |
| C WRDS istituzionale | ESCLUSA da committente | No affiliazione istituzionale |

### 3.2 Proposta operativa

Tre alternative al committente, in ordine di costo crescente:

**Alternativa 1 — Subscription Norgate Platinum a pagamento (~$500-1000)**:
- Onboarding 24/05 sera (entro deadline 29/05 12:00)
- Sviluppo script query API
- Cross-check cluster 2022 entro gate 30/05
- Costo: spesa cash committente

**Alternativa 2 — Estensione deadline gate 30/05 a 30/06 con ricerca alternativa**:
- Identificazione fonti terze gratuite indipendenti (es. SEC EDGAR direttamente con N-PORT 2022 IVV — tentativo già fallito 23/05 per IP-block 10min; CRSP free academic limitato; FactSet free tier; Bloomberg terminal accesso temporaneo)
- 30 giorni per identificare fonte alternativa
- Rischio: nessuna fonte gratuita garantita

**Alternativa 3 — Degradazione formale cluster 2022 a INCONCLUSIVE_DEGRADED**:
- Analoga a 76-ibrido sealed gate 27/05
- Verdetto sealed: cluster 2022 ratio 1.5126× con robustezza DEBOLE (IC95% [0.806×, 2.217×] include 1.5×, già documentato Add 09)
- Aggiungere riga formale: "terza fonte indipendente non identificata, cluster 2022 demandato a fase S2 con dati paid sources"
- Costo: zero, rinuncia al cross-check terza fonte per gate 30/05

### 3.3 Vincolo append-only

Qualunque decisione committente sarà documentata in addendum dedicato (Add 13 — esito gate 30/05) e sealed PRIMA dell'esecuzione. Add 12 D3-bis (S1.5) e Add 13 (gate 30/05) operano in parallelo, non interferiscono.

## 4. Artefatti collaterali

Nessun nuovo file dati creato in questa verifica. Output documentale only.

## 5. Firma

Firmato dal Consulente esecutivo S1 (agente) il 2026-05-24 06:10 CEST.

Decisione committente richiesta su Alternativa 1/2/3 entro 26/05 18:00 CEST (deadline implicita mandato).

---
FINE verifica Opzione A + fallback B
