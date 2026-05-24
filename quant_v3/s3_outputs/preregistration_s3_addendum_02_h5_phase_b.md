# Pre-Registration S3 — Addendum 02: H5 spostata a Phase B + curva Sharpe(L) descrittiva Phase A

Data sigillo: 2026-05-24 11:52 CEST
Stato: SIGILLATO PRE-ESECUZIONE — append-only
Riferimento parent: `preregistration_s3.md` SHA256 `733066f178d764dfa74c9f9958f16384d4742186f08c14ddc0f4b01c7c37f069`
Firma agente: Consulente esecutivo S3 (agente)
Firma committente: Luigi Missere — richiesta esplicita 24/05/2026 11:45 CEST nel messaggio "Validazione preregistrazione S3 Phase A — con 3 modifiche richieste" §3, integrata da decisione consulente 11:46 CEST ("vai avanti senza validazione")

---

## 1. Motivazione

Parent §4 H5 era preregistrata con `L*=1.25` come pin fisso non derivato. Il committente lo ha rilevato 24/05 11:45 CEST:

- Testare concavità su curva Sharpe(L) sotto soglia H4 è metodologicamente vuoto (la curva di una strategia non funzionante non porta informazione operativa).
- `L*=1.25` non è derivato dai dati: è un pin arbitrario che equivarrebbe a falsificare un valore stabilito ex cathedra.

Rimozione di H5 da Phase A e ristrutturazione: Phase B conterrà H5 con L* derivato empiricamente dalla curva Phase A.

---

## 2. Modifica vincolante a parent §4

### 2.1 Ipotesi Phase A (vincolanti, falsificanti)

| H | Definizione | Soglia PASS | Stato in S3 Phase A |
|---|---|---|---|
| H1 | non degenere | coppie degeneri ≤ 25% | FALSIFICANTE |
| H2 | ρ_AR(1) ~ mc monotono | slope > 0 ∧ p < 0.10 | FALSIFICANTE |
| H3 | convergenza 4 selettori IS | ≥ 3/4 stessa (mc, thr) F2 | FALSIFICANTE |
| H4 | Sharpe BT OOS F2 best_param IS | ≥ 1.5 | FALSIFICANTE |
| H6 | bootstrap Δ Sharpe BT | IC 95% non include 0 ∧ lower bound ≥ 0.5 | FALSIFICANTE |
| ~~H5~~ | ~~leverage rationality, L*=1.25~~ | ~~concavità Sharpe(L)~~ | **SPOSTATA A PHASE B** |

H5 è rimossa da Phase A. Non concorre al verdetto Phase A.

### 2.2 Output descrittivo non-falsificante (Phase A)

Phase A produce la curva Sharpe(L) per L ∈ {1.0, 1.25, 1.5, 2.0} sul best_param IS, salvata in `s3_phaseA_leverage_descriptive.csv`. Vincoli:

- Etichetta esplicita "DESCRIPTIVE_NOT_FALSIFYING" in header CSV e nel journal.
- Nessuna soglia PASS/FAIL applicata.
- Nessuna decisione operativa derivata da questi numeri in Phase A.
- Serve come input per Phase B per derivare L* empirico.

Motivazione di tenere la curva descrittiva in Phase A invece che ri-eseguire in Phase B: i backtest leveraged richiedono lo stesso engine cerebro già caricato in Phase A; ri-eseguirli a freddo in Phase B costerebbe 4 cerebro run aggiuntivi senza informazione nuova.

### 2.3 Ipotesi Phase B (condizionale)

H5 Phase B (preregistrata qui ma falsificata solo in Phase B):

**H5-PhB**: leverage rationality data-derived.
- Pre-condizione: H4 Phase A PASS. Se H4 FAIL → H5 non viene testata, leverage chiusa NON GIUSTIFICATA.
- Definizione: dato curve Sharpe(L) descrittiva Phase A, L* = argmax_L Sharpe_OOS(L).
- Soglia PASS H5-PhB: la curva Sharpe(L) presenta massimo interno (L* ∉ {min(L_grid), max(L_grid)}) ∧ Sharpe(L*) > Sharpe(1.0) × 1.05 (incremento marginale ≥ 5%).
- Soglia FAIL: L* coincide con un estremo della grid (1.0 o 2.0) → curva monotona, leverage non discriminante.

---

## 3. Decision tree S3 aggiornato

Sostituisce parent §6:

- (H1 + H2 + H3 + H4 + H6) all-PASS in Phase A → procedi a Phase B per H5-PhB.
- H1 FAIL ∨ H4 FAIL → diagnosi causale, niente Phase B, niente rescue post-hoc.
- H2 FAIL → riapertura Bug 8 (atto grave separato).
- H3 FAIL ∧ resto PASS → annotazione paper, procedere con cautela a Phase B.
- H6 FAIL → DEFERRED o INCONCLUSIVO Phase A.

Phase B (solo se Phase A PASS pieno):
- H5-PhB PASS → leverage giustificata con L* derivato, allocazione attiva con L=L* autorizzata in §8 condizioni allocazione (vedi Add 03 §3).
- H5-PhB FAIL → leverage chiusa NON GIUSTIFICATA, allocazione attiva no leverage.

---

## 4. Cost of leverage — invariato

Parent §5.3 invariato: per L > 1.0 cost = (L − 1) × (€STR + 0.005) annualizzato, sottratto da equity giornaliera. Vale sia per la curva descrittiva Phase A sia per H5-PhB Phase B.

---

## 5. Vincoli irriducibili

- Curve Sharpe(L) descrittiva Phase A ha etichetta "DESCRIPTIVE_NOT_FALSIFYING" tracciata in journal e header CSV.
- Phase A NON dichiara verdetto su leverage. Comunicazione esterna che dichiari leverage validata sulla base della curva descrittiva è violazione di sigillo.
- L* derivato in Phase B deve essere quello empirico, non aggiustato post-hoc.
- Append-only, no edit retroattivo, SHA256 sigillato.

---

## 6. SHA atteso

SHA256 di questo file computato post-write, sigillato nel `.sha256` sibling.

Fine Addendum 02.
