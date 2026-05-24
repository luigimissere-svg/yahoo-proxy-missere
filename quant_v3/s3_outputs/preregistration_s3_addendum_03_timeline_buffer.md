# Pre-Registration S3 — Addendum 03: Timeline buffer + Allocazione SUCCESS 20-30k

Data sigillo: 2026-05-24 11:54 CEST
Stato: SIGILLATO PRE-ESECUZIONE — append-only
Riferimento parent: `preregistration_s3.md` SHA256 `733066f178d764dfa74c9f9958f16384d4742186f08c14ddc0f4b01c7c37f069`
Firma agente: Consulente esecutivo S3 (agente)
Firma committente: Luigi Missere — richiesta esplicita 24/05/2026 11:45 CEST nel messaggio "Validazione preregistrazione S3 Phase A — con 3 modifiche richieste" §4 e §5, integrata da decisione consulente 11:46 CEST ("vai avanti senza validazione")

---

## 1. Motivazione timeline buffer

Parent §9 schedulava verdetto 12/06 con deadline S1 originale 13/06 → 1 giorno di buffer. Il committente lo ha rilevato 24/05 11:45 CEST come insufficiente per imprevisti operativi (walltime scivolato, rerun falsificazione, errori sigillo da risolvere).

---

## 2. Timeline aggiornata (sostituisce parent §9)

- 24-27/05 CEST: validazione committente preregistrazione S3 (parent + Add 01-02-03) — atto separato.
- 28/05 - 02/06: implementazione script S3 Phase A (grid runner 324 trial + bootstrap + curva Sharpe(L) descrittiva).
- 03/06 - 08/06: esecuzione S3 Phase A (walltime stimato 2-4 ore dopo Add 01 riduzione grid; finestra estesa per slack operativo).
- 09/06 - 13/06: falsificazione H1-H6 (H6 = bootstrap), journal, sigillo SHA256, commit + push.
- 14/06: messaggio consulente con verdetto S3 Phase A.
- 13/06: deadline S1 originale invariata per attività non leverage-dependent (chiusure documentali, sigilli paper v8 §3 e §4.1, paper Add precedenti).
- 15/06: nuova deadline S1 leverage-dependent (estesa di +2gg vs parent per assorbire buffer richiesto dal committente).
- 16/06+: Phase B (H5-PhB leverage data-derived) solo se Phase A PASS pieno; altrimenti decisione operativa allocazione condizionale.

Buffer effettivo: 2 giorni (12/06 → 14/06 verdetto) + 2 giorni (13/06 → 15/06 leverage deadline). Slippage tollerato fino a +5gg ulteriori con disclosure giornaliera nel journal (vs +7gg parent — più stretto per non sforare luglio).

---

## 3. Soglie allocazione capitale (sostituisce parent §8)

Coerente con richiesta committente §5 messaggio 24/05 11:45 CEST e con annotazione paper v8 §roadmap operativa (Add 13 §8):

| Scenario S3 | Allocazione attiva massima | Leverage | Allocazione passive baseline |
|---|---|---|---|
| SUCCESS pieno (tutti H Phase A PASS + H5-PhB Phase B PASS) | **20-30k EUR** | L = L* derivato (H5-PhB) | 70-80k passive |
| PARZIALE (Phase A PASS, H5-PhB FAIL o Phase B non eseguita) | **10k EUR** | nessuna (L=1.0) | 70-80k passive |
| INCONCLUSIVO/FAIL (H1 ∨ H4 FAIL in Phase A) | **0 EUR attivo** | n/a | 80-90k passive + 5-10k buffer (allocazione attuale sigillata) |

Modifiche vs parent §8:
- Limite superiore SUCCESS alzato da 15-20k → 20-30k (richiesta committente §5).
- Riferimento esplicito a baseline passive 70-80k in scenari SUCCESS/PARZIALE (coerente con disponibilità capitale dichiarata committente 24/05).

### 3.1 Vincoli irriducibili allocazione

- Nessuna allocazione attiva prima del verdetto S3 (Phase A o Phase B a seconda dello scenario).
- Nessun frazionamento incrementale dell'allocazione "per testare" pre-verdetto.
- Decisione operativa allocazione richiede atto separato del committente post-verdetto con messaggio dedicato citante SHA del journal Phase A (e Phase B se applicabile).
- Allocazione attuale (80-90k passive + 5-10k buffer + 0 attivo) resta sigillata fino al verdetto.

---

## 4. Stop time-box (richiesta §6 committente, recepita)

Stop time-box duro confermato come da §6 messaggio 24/05 11:45 CEST:

> "Se a fine giugno non hai 2 DSR ≥ 0.95 preliminari, S3 chiusa."

Operativamente: alla data 30/06/2026 23:59 CEST, se il numero di trial con DSR preliminare ≥ 0.95 calcolato sul grid Phase A è < 2, S3 viene chiusa con verdetto INCONCLUSIVO indipendentemente dalle altre H. Nessuna estensione, nessun rerun di salvataggio.

Calcolo DSR preliminare: applicato su Sharpe OOS F2 best_param IS (e i 2 successivi per Sharpe IS) con penalty per N=108 trial indipendenti (vedi Add 01 §4).

---

## 5. Riepilogo modifiche Add 03 vs parent

| Sezione parent | Parent | Add 03 |
|---|---|---|
| §9 verdetto | 12/06 | **14/06** |
| §9 deadline S1 leverage | 13/06 | **15/06** (non-leverage attività resta 13/06) |
| §9 slippage tollerato | +7gg | **+5gg** (più stretto, no sforamento luglio) |
| §8 SUCCESS pieno | 15-20k | **20-30k** |
| §8 PARZIALE | 10k | 10k (invariato) |
| §8 INCONCLUSIVO | 0 | 0 (invariato) |
| Stop time-box | implicito | **30/06 23:59 CEST esplicito** |

---

## 6. SHA atteso

SHA256 di questo file computato post-write, sigillato nel `.sha256` sibling.

Fine Addendum 03.
