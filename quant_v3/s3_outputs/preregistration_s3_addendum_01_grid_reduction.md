# Pre-Registration S3 — Addendum 01: Grid Reduction (DSR-tractable)

Data sigillo: 2026-05-24 11:50 CEST
Stato: SIGILLATO PRE-ESECUZIONE — append-only
Riferimento parent: `preregistration_s3.md` SHA256 `733066f178d764dfa74c9f9958f16384d4742186f08c14ddc0f4b01c7c37f069`
Firma agente: Consulente esecutivo S3 (agente)
Firma committente: Luigi Missere — richiesta esplicita 24/05/2026 11:45 CEST nel messaggio "Validazione preregistrazione S3 Phase A — con 3 modifiche richieste" §2

---

## 1. Motivazione

DSR (Deflated Sharpe Ratio) penalizza in funzione del numero di trial indipendenti testati. Con 1296 cerebro run (parent §3.1) la deflazione sarebbe severa al punto da rendere irraggiungibile DSR ≥ 0.95 anche con Sharpe nominali 1.8-2.0. Il committente lo ha rilevato 24/05 11:45 CEST.

Riduzione della grid fatta **ex ante**, motivata, e preregistrata in questo addendum prima di qualsiasi esecuzione. Non è ricerca esplorativa: è dimensionamento del search space tenendo conto del costo statistico (DSR penalty).

---

## 2. Grid sigillata (sostituisce parent §3.1)

| Parametro | Parent §3.1 | Add 01 (vincolante) | Livelli |
|---|---|---|---|
| momentum_classes (mc) | {2, 3, 4} | {2, 3, 4} | 3 |
| threshold (thr) | {0.05, 0.10, 0.20, 0.30} | {0.05, 0.15, 0.30} | 3 |
| max_sector_pct (msp) | {None, 0.20, 0.30, 0.40} | {None, 0.30} | 2 |
| max_positions | {20, 30, 50} | {20, 30, 50} | 3 |
| per_ticker_cap | {0.02, 0.03, 0.05} | {0.03, 0.05} | 2 |

Cardinalità nuova: 3 × 3 × 2 × 3 × 2 = **108 trial/fold × 3 fold = 324 cerebro run**.

Riduzione: -75% vs parent (da 1296 a 324). Walltime stimato 2-4 ore (vs 8-15 ore parent §9). Penalità DSR proporzionalmente ridotta.

---

## 3. Giustificazione per parametro

### 3.1 mc {2, 3, 4} — invariato
mc=4 resta testabile per la prima volta su universo 1037. Eliminare mc=4 ridurrebbe la cardinalità ma annullerebbe uno dei motivi specifici di S3 vs S1 (vedi parent §3.4).

### 3.2 thr {0.05, 0.15, 0.30} — ridotto
Eliminato 0.10 e 0.20: livelli intermedi ridondanti per H3 (convergenza selettori). 0.05 (low), 0.15 (mid), 0.30 (high) coprono il range con risoluzione sufficiente per discriminare regime.

### 3.3 msp {None, 0.30} — ridotto
Eliminato 0.20 e 0.40. {None, 0.30} è il minimo per disambiguare H1 (degenerazione su msp non binding diagnosticata in S1.5 esec 4 §2 Add 13). Se None e 0.30 producono Sharpe identici a 6 decimali su tutti 3 fold → degenerazione H1 confermata strutturalmente; se diversi → H1 ok per quel sotto-universo.

### 3.4 max_positions {20, 30, 50} — invariato
Tre livelli necessari per evitare ricaduta saturazione cap vista in S1.5 esec 3 (diagnostica `170e7b2`). Ridurre a 2 livelli rischierebbe di lasciare scoperta una regione del cap-space.

### 3.5 per_ticker_cap {0.03, 0.05} — ridotto
Eliminato 0.02. Coerente con max_positions ∈ {20, 30, 50}: 50 × 0.02 = 1.00 nav saturated by definition. 0.03 e 0.05 coprono il range operativamente rilevante.

---

## 4. Impatto su ipotesi parent §4

Le definizioni di H1-H6 restano invariate. Cambia solo il denominatore di H1 (coppie totali) e la dimensione del trial space su cui calcolare DSR (Add 13 §4 / parent §4.4).

Numero coppie totali H1: C(108, 2) = 5778. Soglia H1 PASS resta ≤ 25% → ≤ 1444 coppie degeneri.

---

## 5. Vincoli irriducibili

- Append-only, no edit retroattivo.
- SHA256 di questo file sigillato in `.sha256` sibling.
- Modifica della grid post-sigillo vietata. Eventuali ulteriori riduzioni richiedono addendum 04+ con nuova validazione.
- Nessun rerun della grid con parametri diversi presentato come "esecuzione 2" non preregistrata.

---

## 6. SHA atteso

SHA256 di questo file computato post-write, sigillato nel `.sha256` sibling. Verificabile via `sha256sum`.

Fine Addendum 01.
