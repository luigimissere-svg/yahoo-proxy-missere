# Pre-registration S1 v8 — sigillata

**Sprint**: S1 (refactor universo + isolamento MU + force-close F3)
**Periodo nominale**: 23/05/2026 18:44 CEST → 13/06/2026
**Branch git**: `feature/v8-s1-refactor` (da `v3-quant-framework` che funge da main in questo repo, NON da `patch/b2-bugs-2-4-5-7` che resta sigillato v7.3)
**Stato**: sigillato append-only al timestamp 23/05/2026 18:44 CEST
**Disciplina**: nessuna modifica retroattiva a obiettivi, metriche di successo, criteri di falsificazione

---

## 1. Obiettivi sigillati

Esattamente tre obiettivi tecnici, esattamente tre discipline metodologiche. Nessun obiettivo aggiuntivo può essere inserito durante S1 senza nuovo file `preregistration_s1_v8_addendum.md` firmato.

### 1A — Obiettivi tecnici (Bug 6, 8, 7)

1. **Bug 6 — universo point-in-time**: il loader universo deve restituire la composizione storica alla data di rebalancing, non la composizione attuale del 23/05/2026. Survivorship bias eliminato.
2. **Bug 8 — isolamento outlier MU**: regola esplicita single-ticker exposure cap. Nessun ticker può contribuire più del 5% del P&L atteso per fold.
3. **Bug 7 — force-close F3**: test formale di H0 "mc=3 stabile su tutti i fold" contro H1 "mc=2 overfit su F3" tramite bootstrap label permutation.

### 1B — Discipline metodologiche (anti-p-hacking)

4. **Universo v8 sigillato**: `universe_v8_sealed.json` con hash SHA256 committato prima di toccare la grid.
5. **Grid iperparametri ridotta**: da 72×3 a 36×3 o 24×3, pre-registrata in `grid_v8_sealed.json`.
6. **Selettore robusto**: "best fold OOS" sostituito da "median fold OOS" o "worst-case fold OOS". Backward test su ledger v7.4 per verificare che la sostituzione cambi la selezione.

---

## 2. Criteri di successo S1 (PASS/FAIL binari)

| # | Deliverable | Criterio PASS |
|---|---|---|
| S1.1 | Universe loader point-in-time | `universe_loader.get(date)` restituisce composizione storica. Test: universo 01/01/2024 ≠ universo 23/05/2026 |
| S1.2 | Survivorship validazione | Almeno 3 ticker presenti in 2024 e non in 2026 (delisting, M&A, fallimenti) |
| S1.3 | Single-ticker exposure cap | Test backward su v7.4 F2: trade MU avrebbe pesato ≤ 5% del P&L fold |
| S1.4 | Test force-close F3 | Bootstrap label permutation N=1000, p-value ≤ 0.05 per H1 = overfit |
| S1.5 | Universe sealed | File `universe_v8_sealed.json` committed + SHA256 in journal |
| S1.6 | Grid sealed | File `grid_v8_sealed.json` con ≤ 36 trial per fold, committed |
| S1.7 | Selettore robusto | `median_fold_oos_selector` implementato + test su v7.4 ledger: selezione cambia rispetto a best-fold |
| S1.8 | Pre-reg firmata | Commit firmato + tag git `s1-prereg-v8` |

Gate 13/06/2026: tutti gli 8 deliverable PASS → S2. Se ≥1 FAIL → S1 esteso (massimo +1 settimana al 20/06) o redesign.

---

## 3. Criteri di falsificazione

Pre-impegno: registro qui i tre scenari che, se realizzati, mi costringono a riconoscere che S1 non ha prodotto valore atteso. Falsificazione registrata = obbligo di nuova entry nel journal, non riformulazione retroattiva.

### F1 — Universo storico identico

Se al termine di S1.1+S1.2 risulta che l'universo storico point-in-time è identico (entro 1 ticker) all'universo attuale, allora Bug 6 non era materiale. Esito: registrare nel journal e procedere a S2 senza modifica della pipeline.

### F2 — Cap exposure inutile

Se al termine di S1.3 risulta che applicando il cap 5% su v7.4 ledger il P&L aggregato cambia di meno del 5%, allora Bug 8 era marginale (non strutturale). Esito: registrare e mantenere il cap come precauzione, ma non come fix decisivo.

### F3 — Force-close test inconclusivo

Se il bootstrap label permutation su S1.4 restituisce p-value ∈ [0.05, 0.20], il test è inconclusivo e non posso sigillare F3 come overfit né scartare l'ipotesi. Esito: F3 resta classificato "non risolto" e diventa input prioritario per S2.

---

## 4. Materiali sigillati al kick-off

- Audit journal v7.3: `audit_journal_v7_3.md` (563 righe, commit e4dc7aa)
- PDF paper v7.3-r1: `Relazione_Quant_v3_v7_3.pdf` (21 pagine, da rigenerare r2 il 24/05)
- Codice base: branch `main` post-merge di `patch/b2-bugs-2-4-5-7`
- Validazione consulente: `validazione_consulente_chiusura_v7_3.md`

---

## 5. Out-of-scope esplicito S1

Questi elementi NON sono S1 e non possono essere anticipati. Tentazioni naturali da resistere:

- Re-run walk-forward completo (è S3, dopo che universo + grid + selettore sono sigillati)
- Stress test crisi 2008/2020/2022 (è S2)
- Calcolo nuovo DSR (è S3)
- Apertura ramo v9-A in parallelo (avviato in background, ma max 20% tempo settimanale, non in S1)

---

## 6. Pre-impegno comportamentale

Sottoscritto al kick-off:

- Nessuna deviazione da questa pre-reg senza nuovo file addendum sigillato
- Nessun re-run di v7.4 con parametri "alternativi" per cercare il valore che spinga DSR sopra 0.95
- Drawdown URTH > 10% nel periodo S1-S4 non è informazione su v8 e non giustifica deviazioni
- Bug 6 ha priorità su Bug 8 e 7 (è il più strutturale)

---

**Firmato**: Luigi Missere (committente) + Perplexity Computer (agente esecutore)
**Timestamp sigillo**: 23/05/2026 18:44 CEST
**Hash da committare**: SHA256 di questo file al momento del commit git
