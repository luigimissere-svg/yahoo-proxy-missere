# Event Shock Classifier — Specifica tecnica v1.1 (offline, pre-implementazione)

Data: 31/05/2026 12:40 CEST (v1.1 post-riscontro critico ChatGPT)
Autore: Computer (per Luigi Missere)
Stato: SPEC OFFLINE. Nessun codice deployato. Implementazione vietata fino a lettura reminder 90ee1b63 lunedi 01/06/2026.
Approccio scelto: B - Layer separato, news.py production IMMUTATO.

### Changelog v1.0 -> v1.1 (31/05/2026 ore 12:40)
Applicate 6 correzioni del riscontro critico ChatGPT:
- 3.1 EconomicImpactScore: aggiunto `manual_score_divergence_flag` (anti FOMO/hindsight).
- 3.2 FDA_APPROVAL: rimosso "CHMP positive opinion" (non e' market authorization), riclassificato come PHASE_III_SUCCESS.
- 3.3 VolumeShock: sostituita formula lineare con piecewise (ratio 3x -> score 75, allinea gate e score).
- 3.4 GapMove: soglia fissa 8% sostituita con `max(4%, 1.5 * dailyVol20d)` per adattabilita' cross-sector.
- 3.5 Cache: aggiunta key secondaria `evshock:news:hash(headline+source+date)` per evitare riclassificazione multi-ticker.
- 3.6 manual_review_queue: aggiunto expiry 7 giorni (evita accumulo rumore).
- 3.7 Test plan: aggiunto criterio recall >= 0.6 su golden set 20-30 eventi storici noti (evita classifier muto).

---

## 1. Scope

Specifica dell'endpoint dedicato `/api/event_shock` che alimentera' l'Event Shock Layer v1.0 senza modificare il classifier news.py sigillato il 28/05/2026.

Non in scope:
- modifica `_VALID_CATEGORIES_NEG` / `_VALID_CATEGORIES_POS` di news.py;
- modifica prompt Gemini di news.py;
- alterazione severity esistenti;
- ingresso delle nuove categorie nell'Alert pulsante ordinario della dashboard.

---

## 2. Architettura

### 2.1 Posizione nel backend

Nuovo file: `api/event_shock.py` nel repo yahoo-proxy (branch `feature/event-shock-layer`).

Endpoint: `GET /api/event_shock?symbols=AAPL,MSFT,...&days=7`

Parametri:
- `symbols` (obbligatorio, max 30 per chiamata)
- `days` (default 7, max 30) — finestra news da analizzare
- `min_score` (default 60) — soglia EventCredibilityScore minima per restituire l'evento

### 2.2 Flusso

```
GET /api/event_shock?symbols=NVDA,GMAB.CO&days=7
        |
        v
1. Lettura news raw (riusa fetch_finnhub_company_news + fetch_news_for_symbol di news.py)
2. Filtro pre-Gemini: titolo contiene almeno una keyword trigger di una delle 9 categorie
3. Classificazione Gemini dedicata (prompt diverso da news.py)
4. Per ogni evento valido:
   - calcolo EventCredibilityScore (4 componenti)
   - lookup volume/price provider (yfinance gia' importato)
   - composizione output JSON
5. Filtro min_score
6. Ordinamento per score discendente, return JSON
```

### 2.3 Cache

- TTL 15 minuti per coppia (symbol, day) — eventi shock sono per definizione rari, no costo refresh frequente.
- Cache key primaria: `f"evshock:{symbol}:{date.isoformat()}"`.
- Cache key secondaria (correzione ChatGPT 31/05 - 3.5): `f"evshock:news:{sha1(headline + source + date)}"`.
  Stessa news che compare su piu' ticker (es. M&A con acquirente + target, o partnership che cita 2 societa') NON viene riclassificata Gemini due volte:
  prima chiamata calcola classification + cache hash; chiamate successive riusano la classification e calcolano solo metriche per-ticker (volume, gap, AnalystReaction).
  Riduzione attesa costo Gemini: 20-30% in scenari di news multi-symbol (M&A, regulatory shock di settore, eventi geopolitici).
- Cache in-memory (no Redis) coerente con pattern news.py.

### 2.4 Feature flag

Variabile d'ambiente Vercel: `EVENT_SHOCK_ENABLED` (default "false").
Se "false" l'endpoint restituisce HTTP 503 con body `{"error":"feature_disabled"}`.
Permette accensione/spegnimento senza redeploy.

---

## 3. Le 9 categorie - regole definitive

### 3.1 Whitelist eligible automatica (6 categorie)

Queste 6 categorie attivano `ShockCandidate` automaticamente se `EventCredibilityScore >= 80` e tutti gli altri gate del piano sono soddisfatti.

#### FDA_APPROVAL (severity logica 5, peso eventCredibility max)

Trigger keyword (titolo o sommario):
- EN: "FDA approves", "FDA approval", "FDA clearance", "FDA cleared", "FDA authorized", "FDA grants approval", "approval label expansion", "approved label expansion", "EMA approval", "EMA approves"

NOTA correzione ChatGPT 31/05 (3.2): CHMP positive opinion RIMOSSO da FDA_APPROVAL. Non e' market authorization definitiva, e' parere consultivo CHMP che precede decisione Commissione UE. Trattato come PHASE_III_SUCCESS (segnale positivo forte ma non approval). Se il titolo riporta esclusivamente "CHMP positive opinion" senza approval EMA gia' notificata, classificare in PHASE_III_SUCCESS e NON in FDA_APPROVAL.
- IT: "FDA approva", "FDA approvato", "approvazione FDA", "EMA approva", "approvato dall'EMA"
- DE: "FDA-Zulassung", "von der FDA zugelassen", "EMA-Zulassung"
- ES: "FDA aprueba", "aprobado por la FDA", "EMA aprueba"
- FR: "FDA approuve", "approuve par la FDA", "EMA approuve"

Escludere (causa OTHER):
- "FDA review", "FDA filing", "FDA accepts application", "FDA accepted application", "FDA grants fast track", "FDA grants priority review", "submits NDA", "BLA filing", "PDUFA date".

#### PHASE_III_SUCCESS (severity logica 5)

Trigger keyword:
- EN: "met primary endpoint", "meets primary endpoint", "achieves primary endpoint", "positive top-line results", "positive top line results", "statistically significant", "phase 3 success", "phase III success", "approval recommended by panel", "panel recommends approval", "ad-com positive vote", "advisory committee recommends"
- IT: "raggiunto endpoint primario", "risultati positivi fase 3", "raccomandazione positiva", "comitato consultivo raccomanda"
- DE: "primaeren endpunkt erreicht", "phase-3-erfolg", "ausschuss empfiehlt zulassung"
- ES: "alcanza endpoint primario", "resultados positivos fase 3", "comite recomienda aprobacion"
- FR: "atteint le critere principal", "resultats positifs phase 3", "comite recommande l'approbation"

Escludere:
- "phase III initiated", "phase 3 enrolled", "phase III enrollment", "phase III data to be presented", "phase 3 filing", "phase III review", "begins phase III", "starts phase III".

#### MEGA_CONTRACT_MATERIAL (severity logica 4)

Soglia quantitativa OBBLIGATORIA (Gemini deve estrarre il valore dal titolo/sommario):
- contratto >= 500 mln USD in valore assoluto, OPPURE
- contratto >= 1% revenue annua del gruppo (Gemini deve calcolare se rivela revenue/% nel titolo).

Trigger keyword:
- EN: "wins contract", "awarded contract", "signs contract worth", "announces contract", "multi-billion deal", "framework agreement signed", "major order", "landmark contract", "prime contractor selected"
- IT: "vince contratto", "si aggiudica contratto", "accordo quadro", "ordine principale", "contratto pluriennale"
- DE: "vertrag gewonnen", "rahmenvereinbarung", "grossauftrag"
- ES: "gana contrato", "se adjudica", "acuerdo marco", "gran pedido"
- FR: "remporte contrat", "se voit attribuer", "accord-cadre"

Regola di safety: se il valore non e' dichiarato nel titolo o sommario, NON classificare automaticamente. Spostare in `manual_review_queue` con ManualImpactScore richiesto.

#### GUIDANCE_RAISE_MATERIAL (severity logica 5)

Soglia OBBLIGATORIA:
- guidance EPS o revenue alzata >= 5% rispetto alla guidance precedente, OPPURE
- guidance alzata >= 10% rispetto al consensus dichiarato.

Trigger keyword:
- EN: "raises full-year guidance", "raises FY guidance", "increases guidance", "boosts outlook", "upgrades outlook", "raises forecast", "raises EPS guidance", "raises revenue outlook", "guidance hike"
- IT: "alza la guidance", "rivede al rialzo le stime", "alza outlook", "alza previsioni"
- DE: "hebt prognose an", "erhoeht ausblick", "anhebung der prognose"
- ES: "eleva las previsiones", "mejora outlook", "aumenta perspectivas"
- FR: "releve ses previsions", "ameliore perspectives"

Discriminante critico: il prompt Gemini deve cercare nel sommario una percentuale numerica. Se il +% non e' presente o e' < 5%, classificare come `GUIDANCE_RAISE` ordinaria (gia' coperta da news.py) e NON propagare come shock.

#### MA_TRANSFORMATIVE (severity logica 5)

Soglia OBBLIGATORIA:
- deal value >= 10% market cap dell'acquirente, OPPURE
- deal value >= 5 mld USD in assoluto, OPPURE
- acquisizione cross-sector dichiarata "strategic" / "transformative" / "game-changing".

Trigger keyword:
- EN: "transformative acquisition", "transformative merger", "agrees to acquire for billion", "strategic acquisition", "game-changing deal", "all-cash offer billion", "definitive agreement to acquire", "cross-industry merger"
- IT: "acquisizione strategica", "fusione trasformativa", "operazione storica", "accordo definitivo per acquisire"
- DE: "transformatorische uebernahme", "strategische akquisition"
- ES: "adquisicion estrategica", "fusion transformadora"
- FR: "acquisition strategique", "fusion transformatrice"

Regola di safety: se il valore non e' dichiarato o e' inferiore a 5 mld USD e non sono dichiarate transformative-keywords, fallback a `MA_POSITIVE` di news.py (gia' coperto).

#### PATENT_BREAKTHROUGH (severity logica 4)

Trigger keyword:
- EN: "patent granted for core technology", "patent granted flagship", "key patent issued", "landmark patent", "patent for [drug name]", "FDA grants exclusivity", "orphan drug exclusivity granted"
- IT: "brevetto concesso tecnologia core", "brevetto chiave"
- DE: "patent fuer kerntechnologie erteilt"
- ES: "patente concedida tecnologia clave"
- FR: "brevet accorde technologie cle"

Regola di safety: SOLO se il sommario o il titolo riferisce esplicitamente a core technology, key drug, flagship product. "Patent granted" generico NON e' shock. Default: manual_review_queue.

### 3.2 Whitelist manual review (3 categorie)

Queste 3 categorie NON attivano ShockCandidate automaticamente. Vengono salvate in `manual_review_queue` e richiedono override loggato in `/home/user/workspace/data/event_shock_overrides.log` (con ManualImpactScore esplicito).

#### PARTNERSHIP
Trigger: presenza di "partnership", "collaboration", "joint venture" nel titolo.
Filtro automatico safety:
- controparte tier-1 esplicita nel titolo (whitelist controparti: NVIDIA, MSFT, GOOGL, AMZN, AAPL, META, OpenAI, Anthropic, Snowflake, Palantir, TSMC, ASML, Ferrari, LVMH, Saudi Aramco, BlackRock, Berkshire), OPPURE
- valore deal dichiarato >= 100 mln USD, OPPURE
- impatto revenue / EBITDA dichiarato nel titolo.

Se nessuno dei tre filtri matcha, spostare in `manual_review_queue` con `status=requires_manual_review`.

#### AI_COLLABORATION
Trigger: presenza di "AI partnership", "AI collaboration", "AI deal", "generative AI partnership", "partners with NVIDIA / OpenAI / Anthropic / DeepMind" nel titolo.
Filtri identici a PARTNERSHIP.
Note tassonomiche: e' sottoinsieme di PARTNERSHIP. Manteniamo categoria separata per metrica dedicata "AI exposure" nel theme score (10% del PromotionScore).

#### STRATEGIC_ALLIANCE
Trigger: "strategic alliance", "long-term alliance", "framework alliance", "strategic agreement".
Filtri identici. Spesso sinonimo di PARTNERSHIP. Mantenere SEPARATA per tag dashboard, ma trattare come manual review.

---

## 4. EventCredibilityScore - formula

Conferma del piano Event Shock Layer v1.0 consolidato:

```
EventCredibilityScore = 0.40 * Officiality
                      + 0.30 * EconomicImpactScore
                      + 0.20 * VolumeShock
                      + 0.10 * AnalystReaction

dove:
- Officiality (0-100): 100 se fonte e' press release ufficiale dell'emittente
                      / regulatory filing / agenzia pubblica (FDA/EMA/SEC/Pentagon);
                      75 se Reuters/Bloomberg/AP/Dow Jones;
                      50 se testata finanziaria mainstream (FT/WSJ/Handelsblatt/Sole24Ore);
                      25 altrimenti.

- EconomicImpactScore = max(ManualImpactScore, AnalystDerivedImpactScore)
  - ManualImpactScore (0-100): se override loggato fornisce un valore, usarlo.
  - AnalystDerivedImpactScore (0-100): derivato dalla magnitudine
    quantitativa dichiarata (% guidance raise, $ deal value, ecc).
  - manual_score_divergence_flag (correzione ChatGPT 31/05 - 3.1):
    SE ManualImpactScore > AnalystDerivedImpactScore + 30 ALLORA flag = true.
    Il flag impone override_reason RAFFORZATO (minimo 120 caratteri vs 50 standard)
    OPPURE inoltro automatico a manual_review_queue prima di classificare ShockCandidate.
    Protezione anti FOMO / hindsight bias / escalation discrezionale.

- VolumeShock (correzione ChatGPT 31/05 - 3.3): mappa piecewise lineare
  per allineare gate logico (ratio>=3) e score numerico:
    ratio 1x -> 0
    ratio 2x -> 50
    ratio 3x -> 75   (questa e' anche la soglia gate -> score significativo)
    ratio 5x -> 100
  Interpolazione lineare fra i punti. Cap a 100 per ratio >= 5.
  eventVolumeShockRatio = avgVol1d_evento / avgVol30d_pre_evento.

- AnalystReaction (0-100): da finance_analyst_research nelle 48h post-evento.
  100 se >=3 upgrade nei 2 giorni dopo l'evento;
  75 se >=2 upgrade;
  50 se >=1 upgrade O nessun downgrade;
  25 se mix neutrale;
  0 se downgrade prevalente.
```

Gate combinato per ShockCandidate (post-correzione ChatGPT 31/05 - 3.4):
```
ShockCandidate = (EventCredibilityScore >= 80)
              AND (eventVolumeShockRatio >= 3)
              AND (GapMove >= GapMoveThreshold)   # vedi sotto
              AND (QualityShield != Red)
              AND (NOT YieldTrap)
              AND (category IN whitelist_eligible_automatica)

GapMoveThreshold = max(4%, 1.5 * dailyVol20d)
```

Motivazione GapMove dinamico:
- 8% fisso era tarato su biotech / small cap / eventi clinici;
- per Airbus, Schneider, Siemens, mega cap mature un +5% / +6% e' gia' un
  vero information shock (3-4 deviazioni standard);
- dailyVol20d = deviazione standard rendimenti giornalieri close-to-close
  ultimi 20 trading day; moltiplicatore 1.5 = circa 1.5 sigma giornaliero.
- floor a 4% per evitare shock spuri su titoli ultra-stabili (es. utility regolate).

---

## 5. Output JSON dell'endpoint

```json
{
  "as_of_utc": "2026-06-01T05:00:00Z",
  "universo_query_size": 2,
  "events_found": 1,
  "events_manual_review": 0,
  "events": [
    {
      "symbol": "GMAB.CO",
      "event_date": "2026-05-30",
      "category": "PHASE_III_SUCCESS",
      "is_eligible_automatic": true,
      "headline": "Genmab announces positive top-line results for...",
      "source_url": "https://...",
      "source_official": true,
      "officiality_score": 100,
      "economic_impact_score": 85,
      "analyst_derived_impact_score": 85,
      "manual_impact_score": null,
      "event_volume_shock_ratio": 4.2,
      "volume_shock_score": 84,
      "gap_move_pct": 11.3,
      "analyst_reaction_score": 75,
      "event_credibility_score": 86.7,
      "passes_credibility_gate": true,
      "passes_volume_gate": true,
      "passes_gap_gate": true,
      "quality_shield": "Green",
      "yield_trap": false,
      "shock_candidate_eligible": true,
      "fast_probation_recommended": true,
      "fast_probation_size_pct_nav": 1.0,
      "cold_start_lock_active": true,
      "cold_start_override_required": true
    }
  ],
  "manual_review_queue": []
}
```

---

## 6. Prompt Gemini dedicato

```
Sei un classificatore di eventi finanziari market-moving (shock events).
Analizza il seguente titolo e sommario di una news e restituisci JSON con:

- category: una di [FDA_APPROVAL, PHASE_III_SUCCESS, MEGA_CONTRACT_MATERIAL,
  GUIDANCE_RAISE_MATERIAL, MA_TRANSFORMATIVE, PATENT_BREAKTHROUGH,
  PARTNERSHIP, AI_COLLABORATION, STRATEGIC_ALLIANCE, NONE]

- is_eligible_automatic: true solo se category in {FDA_APPROVAL, PHASE_III_SUCCESS,
  MEGA_CONTRACT_MATERIAL, GUIDANCE_RAISE_MATERIAL, MA_TRANSFORMATIVE,
  PATENT_BREAKTHROUGH} E rispetta tutte le condizioni qualitative qui sotto.

- quantitative_value: numero se dichiarato nel testo (es. deal value in USD,
  % guidance raise, % market cap impattata), altrimenti null.

- quantitative_unit: "USD_BILLIONS" | "USD_MILLIONS" | "PERCENT_GUIDANCE_VS_PREV"
  | "PERCENT_GUIDANCE_VS_CONSENSUS" | "PERCENT_MARKET_CAP" | null.

- counterparty_tier1: true/false. True se la news menziona controparte tra
  NVIDIA, MSFT, GOOGL, AMZN, AAPL, META, OpenAI, Anthropic, Snowflake, Palantir,
  TSMC, ASML, Ferrari, LVMH, Saudi Aramco, BlackRock, Berkshire.

- source_official: true se la news cita esplicitamente un press release ufficiale
  dell'emittente, regulatory filing, comunicato FDA/EMA/SEC/Pentagon.

Regole categoria stringenti:

FDA_APPROVAL: solo se "approves" / "clearance" / "approved label expansion".
NON e' approval: "FDA review", "FDA filing", "submits NDA", "fast track granted".

PHASE_III_SUCCESS: solo "met primary endpoint", "positive top-line results",
"statistically significant", "approval recommended by panel".
NON e': "phase III initiated", "phase 3 enrolled", "data to be presented".

MEGA_CONTRACT_MATERIAL: solo se quantitative_value >= 500 (USD_MILLIONS) OR
>= 1.0 (PERCENT REVENUE). Senza valore numerico, is_eligible_automatic=false.

GUIDANCE_RAISE_MATERIAL: solo se quantitative_value >= 5
(PERCENT_GUIDANCE_VS_PREV) OR >= 10 (PERCENT_GUIDANCE_VS_CONSENSUS). Senza %,
is_eligible_automatic=false (degrada a GUIDANCE_RAISE ordinario gestito altrove).

MA_TRANSFORMATIVE: solo se quantitative_value >= 5 (USD_BILLIONS) OR >= 10
(PERCENT_MARKET_CAP), OPPURE testo dichiara "transformative"/"strategic"/
"game-changing" + cross-sector.

PATENT_BREAKTHROUGH: solo se titolo/sommario menziona core technology, key drug,
flagship product, orphan drug exclusivity granted.

PARTNERSHIP / AI_COLLABORATION / STRATEGIC_ALLIANCE: is_eligible_automatic
sempre false. Vanno in manual_review_queue. Tier-1 conta solo per priorita'
nella coda, non per auto-eligibility.

NONE: se la news non e' shock event (default conservativo).

Restituisci SOLO il JSON, senza testo aggiuntivo.

Titolo: {title}
Sommario: {summary[:300]}

JSON:
```

Parametri Gemini:
- temperature: 0.0
- maxOutputTokens: 300
- responseMimeType: application/json
- thinkingConfig: thinkingBudget=0
- timeout: 5s (un secondo in piu' di news.py perche' il prompt e' piu' lungo)
- budget per-request: 30 chiamate (raddoppio rispetto a news.py: ammettiamo Event Shock essere ON-DEMAND e meno frequente)

---

## 7. Cold Start Lock

Conferma del Cold Start Lock dal piano Event Shock consolidato (Opzione B):

- Dal 01/06/2026 al 30/08/2026 (primi 90 giorni): qualsiasi ShockCandidate eligible automaticamente puo' arrivare al massimo a Fast Probation (1% NAV) e MAI a Probation standard senza override loggato.
- Override loggato obbligatorio in `/home/user/workspace/data/event_shock_overrides.log` con campi: timestamp ISO, user email, category, symbol, event_date, reason (minimo 50 caratteri), event_credibility_score snapshot, sha256 hash del record.

L'endpoint `/api/event_shock` espone sempre il campo `cold_start_lock_active` e `cold_start_override_required` per disambiguazione frontend.

---

## 8. Universo applicazione

Coerente con decisione 11 del riscontro:

- Fase iniziale (01/06 - validazione classifier): SOLO universo seed 65 ticker (holdings + watchlist).
- Fase 2 (dopo validazione): estensione a candidate set Promotion Pipeline (probabile espansione 65 -> 80-100 ticker).
- Fase 3 (post Cold Start, 30/08+): nessuna estensione automatica a 686. Valutazione dedicata.

---

## 9. Test plan (Step 3 del riscontro)

Metriche da raccogliere durante la prima settimana post-deploy (01/06 - 08/06):

1. Eventi classificati per categoria (target 0-3 eventi/settimana su 65 ticker).
2. Falsi positivi (annotati manualmente confrontando con outcome 5-day post-evento).
3. Overlap con news.py: percentuale di eventi che news.py classifica gia' come MA_POSITIVE / GUIDANCE_RAISE / etc.
4. Distribuzione EventCredibilityScore (media, p25, p75, p90).
5. Costo Gemini: chiamate/giorno e crediti consumati (atteso < 50 chiamate/giorno data la cache 15 min).
6. Latenza p95 endpoint (target < 8s).
7. Manual review queue size: numero eventi PARTNERSHIP / AI / STRATEGIC_ALLIANCE accumulati.
8. Tasso di accettazione override (override approvati / eventi proposti).

Criteri di accettazione per estensione Fase 2:
- precision >= 0.7 sulle 6 categorie eligible automatiche (validazione manuale di tutti gli eventi proposti);
- nessun falso positivo critico (cioe' nessun "FDA_APPROVAL" che era in realta' FDA review);
- costo Gemini totale < 200 crediti/settimana;
- latenza p95 < 8s;
- recall su dataset storico noto >= 0.6 (correzione ChatGPT 31/05 - 3.7).

### 9.1 Misurazione recall su eventi storici noti (correzione ChatGPT 31/05 - 3.7)

Rischio identificato: un classifier puo' avere precision alta semplicemente perche' classifica pochissimi eventi. Senza misura recall, non si distingue "classifier preciso" da "classifier muto".

Protocollo:
1. Costruire dataset offline di 20-30 eventi storici verificati (2023-2025) su universo S&P 500 + STOXX 600. Esempi target:
   - 5-7 FDA / EMA approvals (Gilead, Moderna, Novo Nordisk, Lilly, GMAB);
   - 5-7 mega M&A annunciate (Microsoft-Activision close, Vodafone-Three UK, Amgen-Horizon, Pfizer-Seagen);
   - 5 guidance raises significativi (NVDA Q1 2024, Eli Lilly 2023, Meta Q4 2023);
   - 5 phase III successes (Lilly Tirzepatide, Novo Wegovy outcomes);
   - 3-5 supply shock / event di filiera (Maersk red sea, supply chain Apple).
2. Salvare dataset in `/home/user/workspace/data/event_shock_golden_set.jsonl` con campi: date, symbol, headline, category_attesa, source_url.
3. Eseguire l'endpoint `/api/event_shock` simulando la data come `event_date` di ogni record.
4. Calcolare recall = eventi classificati correttamente / eventi noti.
5. Target minimo: recall >= 0.6 (cattura almeno il 60% degli shock storici grandi).
6. Se recall < 0.6 -> ricalibrare keyword trigger / threshold prima del deploy production.

Il golden set viene preparato OFFLINE prima del 01/06 (Step F della checklist) e congelato come baseline. Espansioni successive del set richiedono override loggato per evitare cherry-picking.

---

## 10. Auditabilita'

Conferma del piano Event Shock consolidato sezione 17:

Ogni record dell'endpoint che porta a una promozione di stato (anche solo Fast Probation) viene serializzato in `/home/user/workspace/data/event_shock_history.jsonl` (append-only) con:
- timestamp_utc, symbol, event_date, category, event_credibility_score
- raw_response_gemini_truncated (primi 500 char)
- decisione finale (auto / manual / rejected)
- user_email (luigimissere@gmail.com) e session_id

Override manuali aggiuntivi in `/home/user/workspace/data/event_shock_overrides.log` (vincolo del piano).

### 10.1 Manual review queue expiry (correzione ChatGPT 31/05 - 3.6)

Gli eventi inseriti in `manual_review_queue` (PARTNERSHIP, AI_INTEGRATION, STRATEGIC_ALLIANCE, IP_KEY_PRODUCT, e categorie con manual_score_divergence_flag=true) hanno expiry automatica:

- `manual_review_queue_expiry = 7 giorni` dalla data di inserimento.
- Dopo 7 giorni senza revisione: `status = expired`, evento NON puo' piu' diventare ShockCandidate.
- Razionale: gli shock sono per definizione time-sensitive. Una partnership o annuncio AI non revisionato dopo 7 giorni quasi certamente NON era un vero shock di mercato.
- Job di pulizia: cron quotidiano alle 06:00 UTC che esegue scan della queue e marca expired (no eliminazione fisica, mantiene auditabilita').
- Eventi expired vengono comunque conservati in `event_shock_history.jsonl` con `decisione = expired_no_review`.

---

## 11. Cose NON da fare (recap vincoli)

1. NON modificare news.py production (sigillato 28/05).
2. NON modificare `_VALID_CATEGORIES_NEG` / `_VALID_CATEGORIES_POS`.
3. NON estendere il prompt Gemini di news.py.
4. NON alterare severity esistenti.
5. NON fare comparire le 9 categorie nell'Alert pulsante dashboard ordinario.
6. NON applicare il classifier Event Shock a tutti i 686 ticker prima della validazione Fase 1.
7. NON deployare prima di lunedi 01/06 dopo lettura reminder 90ee1b63.
8. NON saltare il branch `feature/event-shock-layer` con commit + push GitHub prima del deploy.
9. NON includere Event Shock nel walk-forward 686 ticker (walk-forward = solo PromotionScore).
10. NON automatizzare promozioni oltre Fast Probation durante Cold Start senza override loggato.

---

## 12. Checklist pre-deploy 01/06 (lunedi mattina)

Ordine operativo:

[ ] Step A - Lettura reminder 90ee1b63: verificare Hit%/Edge% EU post-patch vs baseline 28/05. Se Edge% < 40% (rumore eccessivo), STOP, ricalibrare classifier prima.
[ ] Step B - Lettura /home/user/workspace/diagnostica_pipeline_classifier_2805_chiusura.md e output cron fd2cc132.
[ ] Step C - Verifica conteggi src/sev sui ticker EU sensibili (NTGY.MC, JMT.LS, PCZ.DE, ALBIO.PA, ALNOV.PA, YAR.OL, NOV.DE, MC.PA).
[ ] Step D - Importazione news.py reale workspace -> GitHub luigimissere-svg/yahoo-proxy-missere con commit "baseline: sigillo classifier 28/05/2026 (post-patch Gemini + 3 categorie + keyword 6 cat. multilingua)".
[ ] Step E - Tag git `classifier-baseline-28may`.
[ ] Step F - Creazione branch `feature/event-shock-layer`.
[ ] Step G - Preparazione golden set 20-30 eventi storici verificati (`event_shock_golden_set.jsonl`) per test recall.
[ ] Step H - Implementazione `api/event_shock.py` secondo questa spec (v1.1).
[ ] Step I - Test locale su 65 ticker seed (no deploy ancora) + run golden set per recall.
[ ] Step J - Verifica criteri accettazione: precision >= 0.7, recall >= 0.6, costo < 200 crediti/settimana, latenza p95 < 8s.
[ ] Step K - Test E2E su staging Vercel (preview deploy, NO --prod).
[ ] Step L - Solo dopo conferma metriche: merge in main + deploy --prod.

---

## 13. Decisioni recepite dal riscontro ChatGPT

| Domanda | Decisione |
|---|---|
| Deploy ora? | No, aspettare 01/06 |
| Approccio | B, layer separato /api/event_shock |
| GitHub fonte verita'? | Si |
| News classifier production | NON toccare ora |
| Alert pulsante | No Event Shock dentro alert ordinario |
| Universo Event Shock iniziale | Seed 65 ticker |
| Walk-forward 686 | Solo PromotionScore |
| Event Shock backtest | Separato |
| Partnership / AI / Strategic Alliance | Manual review, non automatiche |
| Severity esistente | Non modificare |
| Cold Start Lock | Attivo, Fast Probation max senza override loggato |
| Feature flag | EVENT_SHOCK_ENABLED in Vercel env |
| Auditabilita' | Ogni evento in event_shock_history.jsonl + overrides.log |
| Fonte di verita' codice | GitHub branch feature/event-shock-layer |

Specifica congelata. Pronta per implementazione lunedi 01/06 dopo lettura reminder 90ee1b63.

---

## 14. Riscontro critico ChatGPT 31/05/2026 12:40 (verdetto)

Verdetto ChatGPT: "SPEC APPROVATA CON CORREZIONI MINORI CONSIGLIATE".

Valutazioni per area:
- Architettura separata: ECCELLENTE
- Feature flag: ECCELLENTE
- Protezione classifier legacy: MOLTO FORTE
- Auditabilita': ECCELLENTE
- Test plan: MOLTO BUONO (ora completato con recall)
- Robustezza anti-hype: BUONA -> RAFFORZATA (manual_score_divergence_flag)
- Rischio leakage discrezionale: PRESENTE ma MITIGATO (divergence flag + expiry + override reason rafforzato)
- Implementabilita': ALTA

Le 6 correzioni sono state recepite integralmente nella v1.1. La spec non e' hype-driven ne' overfit, e' disciplinata e coerente con la filosofia v7.3.
