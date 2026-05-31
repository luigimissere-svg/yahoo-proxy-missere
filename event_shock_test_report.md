# Event Shock Layer v1.1 - Report Test Locale Step 4-5

Data: 31/05/2026 ore 20:50 CEST
Autore: Computer (per Luigi Missere)
Stato: TEST OFFLINE COMPLETATI - PRONTO PER PREVIEW DEPLOY

## Fonti

- Spec autoritativa: `/home/user/workspace/event_shock_classifier_spec_v1.md` v1.1 (sigillata 31/05 ore 12:40)
- Implementazione: `/home/user/workspace/api/event_shock.py` (926 righe)
- Golden set: `/home/user/workspace/event_shock_golden_set.jsonl` (25 eventi UPSIDE verificati 2023-2025)
- Script test: `/home/user/workspace/test_event_shock_golden.py`

## Risultati Step 4 - Recall pre-filter keyword

Il pre-filter keyword serve a evitare chiamate Gemini su news irrilevanti. Il recall pre-filter "generico" (qualsiasi trigger matcha) e' la metrica critica: solo le news che superano il pre-filter raggiungono il classifier Gemini.

| Metrica | Risultato | Target spec | Esito |
|---|---|---|---|
| Recall pre-filter generico (qualsiasi match) | 25/25 = 100% | >= 60% | OK |
| Recall pre-filter categoria corretta | 22/25 = 88% | n/d | informativo |

Eventi con match keyword in categoria diversa da quella attesa (3 casi):
- UP-016 LLY Kisunla: trigger FDA_APPROVAL ma category attesa PHASE_III_SUCCESS. Caso noto, segnalato dal subagent stesso.
- UP-024 SNPS-Ansys: trigger MA_TRANSFORMATIVE ma category attesa MEGA_CONTRACT_MATERIAL. Ambiguo.
- UP-025 VRTX Casgevy: trigger FDA_APPROVAL ma category attesa PATENT_BREAKTHROUGH. Ambiguo.

In tutti e 3 i casi Gemini riceve la news (pre-filter passa) e ha possibilita' di riclassificarla in categoria corretta o NONE. Il pre-filter non costituisce un fallimento.

Recall per categoria:

| Categoria | Match corretto / totale | % |
|---|---|---|
| FDA_APPROVAL | 5/6 | 83% |
| GUIDANCE_RAISE_MATERIAL | 5/5 | 100% |
| MA_TRANSFORMATIVE | 4/4 | 100% |
| MEGA_CONTRACT_MATERIAL | 3/4 | 75% |
| PATENT_BREAKTHROUGH | 0/1 | 0% (caso unico Casgevy) |
| PHASE_III_SUCCESS | 4/5 | 80% |

## Risultati Step 4 - Event Credibility Score

Calcolato con `volume_shock_score = 75` (stub corrispondente a ratio 3x, allineato al gate spec) e `analyst_reaction_score = 50` (neutro). Officiality dedotta da `source_official` del golden set (tutti True salvo UP-001 stimato).

| Metrica | Risultato | Target |
|---|---|---|
| Media event_credibility_score | 85.2 | >= 80 |
| Eventi con score >= 80 (gate spec) | 23/25 = 92% | >= 60% |

Solo 2 eventi sotto soglia 80:
- UP-003 LLY guidance raise (eco_impact 60 perche' qv=3 con unit USD_BILLIONS dichiarato come delta assoluto, non %)
- UP-005 ASML guidance raise (eco_impact 60, qv=14 PERCENT_GUIDANCE_VS_CONSENSUS, soglia interpolata)

Entrambi rimangono candidate validi (score 78), sotto il default min_score=60 dell'endpoint vengono comunque restituiti.

## Step 5 - Verifica criteri accettazione

| Criterio | Target spec | Misurato | Esito |
|---|---|---|---|
| recall su golden set | >= 0.6 | 1.0 generico, 0.88 categoria-corretta | OK |
| precision >= 0.7 sulle 6 categorie eligible | richiede deploy reale + 1 settimana | non misurabile offline | DEFERITO a post-deploy |
| costo Gemini < 200 crediti/settimana | con cache TTL 15min + budget 30/req | stimato 50-100 chiamate/sett su universo 65 ticker | OK previsionale |
| latenza p95 < 8s | con timeout 5s Gemini + 8s Yahoo/Finnhub + ThreadPool 8 workers | non misurabile offline | DEFERITO a preview deploy |

## Cose verificate offline

1. Sintassi Python: PASS (ast.parse OK)
2. Pre-filter keyword: 100% recall generico su golden set
3. Scoring functions: tutte e 4 (officiality, economic_impact, volume, analyst) producono output 0-100
4. Gate ShockCandidate: testabile solo con dati prezzo/volume reali (richiede preview deploy)
5. Cold Start Lock: data attuale 2026-05-31 <= 2026-08-30 -> cold_start_lock_active = True
6. Feature flag EVENT_SHOCK_ENABLED: default false, HTTP 503 (verificato a codice)
7. Manual review queue + expiry 7 giorni: implementato (verificato a codice)

## Cose NON verificate offline (richiedono preview deploy)

1. Latenza p95 endpoint
2. Behavior real Gemini su prompt v1.1
3. Volume/gap su ticker reali (Yahoo chart API)
4. Audit append in /tmp Vercel
5. Cache hit ratio chiave secondaria headline (multi-ticker)

## Prossimi step

1. Commit branch feature/event-shock-layer su GitHub luigimissere-svg/yahoo-proxy-missere
2. Deploy preview Vercel (NO --prod)
3. Smoke test endpoint con symbols=NVDA,LLY,MSFT (USA) e symbols=ASML.AS,AIR.PA (EU)
4. Misura latenza e costo Gemini su 65 ticker seed
5. Solo dopo verifica metriche: merge in main + deploy --prod con EVENT_SHOCK_ENABLED=true

## Vincoli rispettati

- news.py production NON modificato
- v8 paper sigillato INTOCCATO
- Quality-Shield NON tocato
- v3.1d sigillata INTOCCATA
- Approccio B (layer separato)
- Cold Start Lock attivo
- Lingua italiana, no emoji, no markdown italic
