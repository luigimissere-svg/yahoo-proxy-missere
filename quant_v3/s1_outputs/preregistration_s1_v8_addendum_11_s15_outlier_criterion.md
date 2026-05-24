# Pre-Registration S1 v8 — Addendum 11
# S1.5 Criterio outlier MU per isolamento Bug 8

Data sigillo: 2026-05-24 05:45 CEST
Stato: SIGILLATO PRIMA DELL'ESECUZIONE — append-only
Catena addenda: 02 → 02-wiki → 03 → 03-delist → 04 → 05 → 06 → 07 → 08 → 09 → **11**
(Add 10 in pulizia documentale parallela, recupero entro 29/05 23:59 CEST)

Firma agente: Consulente esecutivo S1 (agente)
Firma committente: validazione esplicita richiesta in atto separato con timestamp proprio

---

## 1. Riferimento mandato

Mandato committente del 24/05/2026 05:24 CEST "Autorizzazione S1.5 + gate 30/05 — risposta ai quesiti dashboard", sezione "Risposta Domanda 1 — Chiarimenti S1.5 outlier MU Bug 8".

## 2. Oggetto dell'isolamento — Bug 8

**Bug 8 sealed v7.3**: F2 OOS ρ_AR(1) lag-1 = **+0.1883** (Ljung-Box Q(10)=20.374, p=0.0259, sig 5%). Riferimento `audit_journal_v7_3.md` riga 802 (sealed Task 7a, 2026-05-23).

**Discrepanza paper v7.3**: PDF v7.3 riporta +0.176 (errato). Differenza +0.0123 documentata in critica 7 discrepanze, fonte autoritativa = journal sealed riga 802 (+0.1883).

**Serie sottostante**: 65 daily returns OOS portfolio fold F2 (oos_start 2025-11-01, oos_end 2026-02-01, 75 bar nominal, 65 nonzero effective).

**Best params F2 sealed**: threshold=0.25, min_concordant=2, target_risk_pct=0.008, max_sector_pct=None, max_portfolio_beta=None.

**Concentrazione PnL osservata** (`analisi_concentrazione_f2.md` 2026-05-23):
- 10 trade aperti, 0 chiusi entro finestra OOS (mid-term horizon)
- MU PnL net = +11.176 EUR (+107.48%), 51.5% del PnL totale fold
- Top-2 (MU+BBVA.MC) = 68.2%; HHI 0.310 → n-effettivi vincitori 3.22

## 3. Default conservativi documentati pre-esecuzione (committente ha skippato quesiti dashboard delle 05:25 CEST)

I seguenti default sono adottati senza conferma esplicita committente e documentati per trasparenza. Auto-falsificabili in qualsiasi momento se committente li revoca per iscritto.

### D1 — Relazione S1.3 ↔ S1.5

S1.5 ESTENDE S1.3 (non lo sostituisce). S1.3 sealed in `journal_s1_3_bug8_cap.md` (2026-05-23 18:50 CEST) resta valido come regola produzione v8 (cap notional 5% + winsor PnL_pct P95 + min_tickers=20). S1.5 è **analisi diagnostica attribuzionale separata** che misura la sensibilità del ρ_AR(1) F2 all'esclusione progressiva degli outlier, senza modificare la regola produzione.

Motivazione: vincolo append-only catena S1. S1.3 PASS sealed (commit `8519b01`) non si ritratta. S1.5 produce un secondo livello di evidenza sul fenomeno.

### D2 — Definizione operativa "outlier MU top-k"

Il mandato dice "isolamento outlier MU... esclusione progressiva top-1, top-3, top-5". Interpretazione: nel ledger F2 sealed c'è **1 solo trade MU** (single position open_at_end). Non esistono "top-3 trade MU" da escludere.

Default conservativo D2:
- **Perimetro outlier = 10 trade fold F2** (intero ledger sealed)
- **MU = top-1 atteso** (pnl_pct +107.48%, 8.3× mediana)
- **Top-3 e top-5** = ranking discendente per leverage/Cook's distance sui 10 trade, includono altri ticker (BBVA.MC, IBE.MC, PRY.MI, ENEL.MI, ETE.AT, EUROB.AT, FER.MC, EDP.LS, GMAB.CO oltre a MU)

Interpretazione alternativa esclusa (richiede dati non disponibili): "trade MU su tutti i fold v7.3" — ledger v7.3 completo PERSO (riferimento `journal_s1_3_bug8_cap.md` righe 17-20). Solo ledger F2 sopravvissuto.

Interpretazione alternativa esclusa (richiede ridefinizione semantica): "decomposizione daily intra-trade MU" — frammenta il singolo trade MU nei suoi 65 daily contribution; metodologicamente diverso da "esclusione trade", non risponde al mandato letterale.

### D3 — Ricostruzione serie 65 daily F2

`f2_oos_equity.csv` (citato in `analisi_concentrazione_f2.md` riga 77) NON presente in workspace. Default: ricostruisco la serie 65 daily portfolio returns F2 OOS da:
- 10 trade ledger (`f2_oos_trade_ledger.csv` sealed)
- Prezzi daily OHLCV per 10 ticker (`data/ohlcv/*.parquet` disponibili)
- Cash base 100.000 EUR, equal-weight implicito

Validazione di ricostruzione: ρ_AR(1) ricostruito DEVE essere entro ±0.02 dal sealed +0.1883. Se gap > 0.02, dichiaro **GAP_DI_RIPRODUZIONE** e flaggo S1.5 come INCONCLUSIVE_DEGRADED (analoga a 76-ibrido SEC EDGAR).

## 4. Criterio statistico outlier — sigillato PRIMA dell'esecuzione

### 4.1 Modello di riferimento

Modello AR(1) su serie 65 daily returns F2:

  r_t = α + ρ · r_{t-1} + ε_t,  t = 2, ..., 65

dove ρ è il parametro autocorrelazione di lag 1 stimato OLS sulla matrice di design

  X = [1, r_{t-1}],  y = r_t,  T_eff = 64 osservazioni AR(1)

### 4.2 Attribuzione trade-level

Ogni daily return portfolio r_t è la somma ponderata dei daily return dei 10 trade aperti:

  r_t = sum_i w_i · r_t^{(i)},  i ∈ {trade_1, ..., trade_10}

dove w_i = notional_open_i / sum_j notional_open_j (proxy equal-weight implicito v7.4) e r_t^{(i)} è il daily return del ticker del trade i tra dt-1 e dt.

### 4.3 Metrica primaria — leverage hat-matrix

Per ciascun trade i, calcolo il contributo leverage cumulativo sulla stima ρ tramite la formula leave-one-out:

  Δρ_i = ρ_full − ρ_{full \ {contributo trade i a tutti i r_t}}

dove "esclusione trade i" significa porre r_t^{(i)} = 0 per tutti i t (cioè rimuovere il trade dal portfolio, NON sostituirlo).

**Ranking outlier**: trade ordinati per |Δρ_i| discendente. Top-k = primi k trade del ranking.

### 4.4 Metrica secondaria — Cook's distance (sanity check)

Cook's distance classica su modello AR(1) OLS, calcolata per ciascuna osservazione t = 2, ..., 65:

  D_t = (r_t - r̂_t)² · h_tt / (p · MSE · (1 - h_tt)²)

dove h_tt è il leverage hat-matrix dell'osservazione t-esima, p=2 (intercept + lag1), MSE è il mean squared error del modello AR(1) full.

**Aggregazione trade-level**: D_i (trade i) = sum_t (w_i · |r_t^{(i)}| / r_t) · D_t · I(r_t ≠ 0).

Se ranking Cook's distance differisce dal ranking leverage Δρ per più di 2 posizioni in top-5, dichiaro **DISACCORDO_METRICHE** e adotto leverage Δρ come primario (sopra documentato).

### 4.5 Soglia binaria sealed

| Esito | Condizione | Verdetto |
|---|---|---|
| ISOLATO | ρ_AR(1) F2 dopo esclusione top-3 < **+0.10** | Bug 8 ISOLATO, trattabile via filtro outlier in produzione (S1.3 sufficiente) |
| STRUTTURALE | ρ_AR(1) F2 dopo esclusione top-5 ≥ **+0.10** | Bug 8 STRUTTURALE, redesign F2 obbligatorio (rinviato a fase S2 redesign) |
| INTERMEDIO | top-3 ≥ +0.10 AND top-5 < +0.10 | Bug 8 PARZIALMENTE ISOLATO, esclusione top-5 minima necessaria per produzione |

Soglia +0.10 motivata da:
- Politis T_eff = T·(1−ρ)/(1+ρ) → per ρ=+0.10 e T=65, T_eff=53.2 (perdita 18%, tollerabile)
- Per ρ=+0.20 (originale +0.1883), T_eff=44.4 (perdita 32%, eccessiva)

### 4.6 Output deliverable

1. `f2_oos_daily_returns_reconstructed.csv` — serie 65 daily F2 ricostruita con SHA256
2. `s15_leverage_ranking.csv` — ranking 10 trade per Δρ_i (e Cook's distance secondaria)
3. `s15_sensitivity_curve.json` — ρ_AR(1) F2 vs k (k=0,1,2,3,4,5,6,7,8,9,10)
4. `s15_sensitivity_curve.png` — chart sensibilità
5. `journal_s15_bug8_outlier_isolation.md` — verdetto binario sigillato + SHA256 di tutti i deliverable

## 5. Vincoli irriducibili eredità Add 09 §4.5 e mandato 21:03

1. Append-only: questo Add 11 è il **6° addendum sealed** (catena: 02 → 02-wiki → 03 → 03-delist → 04 → 05 → 06 → 07 → 08 → 09 → 11). Add 10 in pulizia parallela, non blocca.
2. SHA256 per ogni artefatto S1.5 (5 deliverable §4.6).
3. NO firma a nome Luigi Missere senza validazione preventiva esplicita (Add 09 §4.5).
4. NO modifica retroattiva file sealed pre-23/05 22:00.
5. NO prompt-engineering verdetto: se top-3 esclusione porta ρ a +0.099, dichiaro ISOLATO; se a +0.101, dichiaro INTERMEDIO. Soglia letterale.
6. NO selezione retroattiva outlier: criterio leverage Δρ_i sealed in §4.3 PRIMA dell'esecuzione.
7. Auto-falsificazione: se ρ ricostruito da serie 65 daily ricostruita differisce > 0.02 dal sealed +0.1883, S1.5 DEGRADED.

## 6. Deadline

- **24/05 06:00 CEST**: avvio onboarding WRDS (parallelo, gate 30/05)
- **25/05**: questo Add 11 sigillato (DONE 05:45 CEST, ante diem)
- **06/06 23:59 CEST**: S1.5 completato (deadline mandato)

## 7. Esclusioni esplicite

- NON si modifica `risk_caps.py` (S1.3 sealed, regola produzione invariata)
- NON si modifica `selector_v8.py` (S1.7 sealed)
- NON si modificano pesi default v8 (cap=5%, winsor P95, min_tickers=20)
- NON si re-esegue walkforward IS/OOS completo (S1.5 è diagnostica posthoc su F2 sealed)

## 8. Firma sigillo

Firmato dal Consulente esecutivo S1 (agente) il 2026-05-24 05:45 CEST.

Validazione committente richiesta in atto separato.

SHA256 di questo file = (calcolato post-write, allegato in `.sha256`)

---
FINE Addendum 11
