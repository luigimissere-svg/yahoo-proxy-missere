# Pre-Registration S1 v8 — Addendum 13
# Chiusura S1.5 post esec 4 — §4.x paper v8 disclosure update

Data sigillo: 2026-05-24 11:15 CEST
Stato: SIGILLATO POST CHIUSURA S1.5 — append-only
Catena addenda: 02 → 02-wiki → 03 → 03-delist → 04 → 05 → 06 → 07 → 08 → 09 → 11 → 12 → **13**
(Add 10 in pulizia documentale parallela, recupero entro 29/05 23:59 CEST)

Firma agente: Consulente esecutivo S1 (agente)
Firma committente: Luigi Missere — validazione esplicita ricevuta 24/05/2026 11:10 CEST (messaggio "Verdetto esec 4 accettato + chiusura S1.5 opzione (d)")

Commit chiusura riferimento: `a91aea9` su branch `feature/v8-s1-refactor`
Catena commit S1.5: `e5d29eb` → `170e7b2` → `b2ed2ce` → `a91aea9`

---

## 1. Scopo addendum

Sigilla la chiusura S1.5 post esec 4 (FAIL su H1+H4) e aggiorna §4.x del paper v8 con la dichiarazione concordata col committente in data 24/05/2026 11:10 CEST. Non modifica sigilli precedenti (Bug 8 `f51ed7e`, disclosure §3 Sharpe operativo 1.94/1.91, disclosure §4.1 Sharpe segnale 4.389/1.610): tutti invariati.

---

## 2. Verdetto S1.5 esec 4 — sintesi sigillata

Run autoritativo `wf_runner --grid s1_5_exec3 --universe portfolio --max-positions 20 --per-ticker-cap 0.05`.

| Ipotesi | Esec 3 | Esec 4 | Soglia | Outcome esec 4 |
|---|---|---|---|---|
| H1 — non degenere | FAIL (76 coppie) | FAIL (28 coppie) | ≤25% | FAIL |
| H2 — ρ_AR(1) ~ mc monotono | PASS (slope +0.333) | PASS (slope +0.218, p=1.3e-13) | slope>0 ∧ p<0.10 | PASS |
| H3 — selettori convergenti | PASS 4/4 → thr=0.05 | PASS 3/4 → mc=2 thr=0.30 | ≥3/4 | PASS |
| H4 — Sharpe BT OOS best_param IS ≥ 1.5 | PASS (1.944) | FAIL (1.048) | ≥1.5 | FAIL |

Decision tree autorizzato 24/05 10:30 CEST: H1 FAIL + H4 FAIL → opzione (d) chiusura S1.5. Confermato dal committente 11:10 CEST.

Riferimento report falsificazione: `s15_exec4_falsification_report.json` SHA256 `8c4e00438dea52b119997b9d2800016f0bc5dbf5f9a177903c33c5b300cc0b8a`. Riferimento journal: `journal_s15_exec4_chiusura.md` SHA256 `c6b6bb349d236c37e72b1b18c1ed2f4416a083a7c0ee8475eb7ba5c4ae06ffcc`.

---

## 3. Dichiarazione §4.x paper v8 — verbatim sigillato

Testo concordato col committente in data 24/05/2026 11:10 CEST, da inserire in §4.x del paper v8 (sezione disclosure S1.5):

> "S1.5 esec 4 (max_positions=20, per_ticker_cap=0.05) ha eliminato la saturazione del cap diagnosticata in esec 3 ma non ha superato H1 (degenerazione residua su parametro max_sector_pct non binding) né H4 (Sharpe BT OOS best_param IS = 1.048 < 1.5). H1 limite noto del setup portfolio 35 ticker. Leverage analysis deferred a S3 con universo esteso."

Questo testo è il riferimento sigillato. Eventuali riformulazioni stilistiche nel paper v8 non potranno alterare il contenuto fattuale (numeri 20, 0.05, 1.048, 1.5, 35, e attribuzione causale a max_sector_pct non binding).

---

## 4. Nota a piè di pagina §4.X (Bug 8 / H2)

Coerente con annotazione condivisa col committente 24/05 11:10 CEST sulla discrepanza ρ_AR(1) mc=3 esec 4 (+0.2511) vs sealed v7.4 (+0.1883), Δ = +0.0628:

> "I valori numerici di ρ_AR(1) sono sensibili al setup operativo specifico (max_positions, per_ticker_cap, universo); l'invariante teoricamente predetto è il segno della relazione mc → ρ. La replicazione qualitativa della monotonia (slope +0.218 in esec 4 con p<1e-13) conferma il sigillo Bug 8 `f51ed7e` indipendentemente dai valori puntuali."

Inserita come nota a piè di pagina in §4.X, NON come correzione di valori sealed.

---

## 5. Stability 3/3 — annotazione paper v8

Nuova annotazione concordata col committente 11:10 CEST, da inserire in §4.x come evidenza positiva collaterale:

> "Il wf_runner sotto setup esec 4 produce convergenza stable IS 3/3 fold su `(mc=3, thr=0.30, msp=None)`, indicando che la procedura di selezione walk-forward è ben condizionata sotto il nuovo cap, sebbene la performance OOS associata sia insufficiente. Stable ≠ performante."

---

## 6. Sigilli precedenti — invariati

Confermato per chiusura S1.5:

- Sigillo Bug 8 `f51ed7e` SUPERATO da v8: INVARIATO. H2 PASS in esec 3 ed esec 4 lo ribadisce.
- Disclosure §3 (Sharpe operativo 1.94/1.91): INVARIATO.
- Disclosure §4.1 (Sharpe segnale 4.389/1.610): INVARIATO.
- §4.X rinforzato qualitativamente da H2 esec 4 replication.
- Add 11 §3 D3 default + Add 12 D3-bis ricostruzione F2: INVARIATI.

---

## 7. Roadmap post-chiusura S1.5

Confermata dal committente 11:10 CEST:

1. **S1.5 CHIUSO** opzione (d). Niente leverage analysis su S1.
2. **Paper v8 §4.x update** sigillato da questo addendum 13.
3. **S3 preregistrazione separata** (atto successivo a questo addendum):
   - Universo esteso 1037 ticker EU+US
   - Grid completa (mc × thr × msp)
   - Leverage analysis riaperta su setup S3
   - Bootstrap Δ Sharpe BT full equity multi-trial INCLUSO (recupero DEFERRED S3)
4. **S2 cluster 2022** INCONCLUSIVE_DEGRADED: invariato.
5. **DEFERRED S3 bootstrap Δ Sharpe BT full equity multi-trial**: assorbito in S3 preregistrazione.

---

## 8. Implicazione roadmap capitale 15/08 — annotazione paper v8

Annotazione concordata col committente 11:10 CEST per sezione roadmap operativa paper v8:

> "H4 FAIL su portfolio 35 ticker pesa sull'aspettativa originaria '4 DSR ≥ 0.95 al 15/08'. Lo sblocco dipende ora da S3 universo esteso. Probabilità soggettiva scenario A (passa tutto) scivola verso il basso del range 35-45%; scenario B (passa parziale, rimando) cresce. Nessuna decisione operativa su capitale fino a S3. Allocazione attuale (80-90k passive + 5-10k buffer + 0 attivo) resta sigillata."

Niente decisioni go/no-go capitale prima di S3 completata.

---

## 9. Append-only — vincoli di chiusura

Questo addendum 13 è sigillato append-only. Modifiche retroattive vietate. Vincoli irriducibili:

- SHA256 di questo file da computare post-write e sigillare in `.sha256` sibling.
- Nessuna firma a nome Luigi senza validazione esplicita (validazione 11:10 CEST già ricevuta — vedi §1).
- Nessuna modifica retroattiva di file pre-23/05 22:00.
- Nessun prompt-engineering del verdetto FAIL: i numeri 28, 1.048, 1.5 stanno nel report sealed e nel journal sealed; questo addendum li registra ma non li riformula.

---

## 10. Prossimo atto

S3 preregistrazione — file separato `preregistration_s3.md` in `quant_v3/s1_outputs/` (o `quant_v3/s3_outputs/` se nuovo branch directory), sigillato a sua volta con SHA256. Stato: in preparazione contestuale a questo addendum 13.

---

Fine Addendum 13.
