# Pre-registration impatto B2 patch (Bug 7+5+2+4)

**Firma**: 23/05/2026 13:50 CEST
**Autore**: Luigi Missere (consulente)
**Scope**: stabilire ex-ante segni e magnitudini attese delle metriche post-patch B2, per distinguere correzione legittima da bug residuo.
**Stato pre-patch (Step 0, F3 testbed)**: documentato in `step0_sintesi.md`.

---

## Ipotesi quantitative

### F3 OOS — testbed step 0 (best_params, max_sector_pct=0.30)

Stato attuale (v7.2, post-Step-0):

- `sharpe_a` = 0.6584
- `pnl%` = 7.539
- `n_trades` = 12
- `n_bars` = 325 (contaminato da warmup)

Atteso post-patch:

- `n_bars` = 63 (warmup filtrato — verifica diretta di B2)
- **Se Bug 5 elimina MC.PA + BMPS.MI** (carry-in pre-fold, persi −25% e −13%):
  - `pnl%` atteso ≥ 7.539 (perdite eliminate)
  - `n_trades` atteso = 10-11 (2 chiusi pre-fold scompaiono)
  - `sharpe_a` atteso: difficile predire numericamente, **range 1.0-2.0** in base alla volatilità dei restanti
- **Se Bug 5 NON elimina MC.PA + BMPS.MI** (ipotesi nulla):
  - `sharpe_a` atteso ≈ 0.6584 × √(325/63) ≈ **1.495** (solo correzione Bug 2)

### F2 OOS — testbed roadmap (MU domina 51.5% PnL)

Stato v7.2: `sharpe_a_OOS` = 1.941

Atteso post-patch:

- **Se Bug 5 elimina MU pre-roll entry @ 199,96**:
  - `pnl%` F2 OOS scende drasticamente (MU contribuiva ~107% del PnL)
  - `HHI_pnl` scende sotto 0.310 (top-1 non più 51.5%)
  - `sharpe_a` F2 scende da 1.941 a valore **tra 0.5 e 1.0** (incertezza alta)
- **Se MU rimane** (apertura intra-fold a prezzo diverso):
  - `sharpe_a` F2 ≈ 1.941 × √(k_F2/n_OOS_F2)

### F1 OOS — campione neutro

Stato v7.2: `sharpe_a` = 0.688

Atteso post-patch:

- `n_bars` = 63
- Se distribuzione `open_at_end` è 5 pre-roll + 5 intra-fold (ipotesi simmetrica):
  - `sharpe_a` atteso ≈ 0.688 × √(k_F1/n_OOS_F1) modulato dai trade persi

---

## Falsifiabili — condizione di sospetto bug residuo

Se dopo patch:

- **`sharpe_a` F3 OOS < 0.66** → Bug 5 fix sta togliendo segnale buono, non rumore
- **`sharpe_a` F2 OOS > 2.5** → patch ha amplificato segnale invece di pulirlo
- **`sum(n_trades_post_patch) > sum(n_trades_pre_patch)`** → gate non sta funzionando

---

## Decisione di stop

- Se dopo patch **tutti i fold ricadono in range atteso** → procedere DSR pipeline (Task 1-11)
- Se anche **un solo fold viola un criterio falsificabile** → audit ulteriore PRIMA di Task 1

---

## Sigillo

Questo documento è LOCKED-IN al timestamp `23/05/2026 13:50 CEST`. Nessuna modifica retroattiva post-esecuzione. Eventuali revisioni vanno tracciate in append-only sotto, con nuovo timestamp.

---

## Revisioni

### Revisione R1 — 23/05/2026 14:00 CEST

Append-only, su critica metodologica dell'agent. Originali R0 restano validi e immutabili.

**Raffinamento falsifiabili F3 e F2** — le soglie originali R0 erano permissive perché non distinguevano l'effetto puro Bug 2 (warmup → 63 barre, scaling √(n_full/n_eff)) dall'effetto combinato Bug 5 (rimozione trade pre-roll).

#### Falsifiabile F3 OOS — STRINGENTE

Floor logico: anche solo Bug 2 da solo deve portare sharpe a circa 1.495 (= 0.6584 × √(325/63), ipotesi warmup-quasi-zero).

- **R1-F3-1**: se `sharpe_a` F3 OOS < **1.0** → bug residuo (Bug 2 non sta correggendo abbastanza, oppure Bug 5 sta rimuovendo segnale buono).
- Nota: il floor 1.0 assume `n_nonzero ≈ 63` post-patch. Se in step 0 post-patch emerge `n_nonzero` significativamente diverso da 63 (es. warmup conteneva trade attivi) → ricalcolare floor come `0.6584 × √(n_nonzero_pre / n_nonzero_post)` e aggiornare in R2.

#### Falsifiabile F2 OOS — STRINGENTE

Floor logico: Bug 2 puro porterebbe sharpe a circa `1.941 × √(315/63) ≈ 4.34`. Quindi la soglia originale "> 2.5" verrebbe violata da solo effetto Bug 2 senza che Bug 5 faccia nulla.

- **R1-F2-1**: se `sharpe_a` F2 OOS > **5.0** → patch ha amplificato segnale invece di pulirlo (Bug 5 non sta tagliando MU pre-roll, oppure altro bug residuo).
- **R1-F2-2**: se `sharpe_a` F2 OOS < **0.3** → Bug 5 ha tagliato troppo (rimosso anche segnale legittimo intra-fold).
- Nota: range atteso F2 OOS post-patch è [0.3, 5.0]. Stima centrale: se MU rimosso → ~0.5-1.0; se MU intra-fold → ~2-4.

#### Falsifiabili R0 che restano in vigore

- F3 OOS `sharpe_a` > 2.0 → segnale anomalo (R0 implicito dal range 1.0-2.0)
- `sum(n_trades_post) > sum(n_trades_pre)` → gate Bug 5 non funziona (R0 invariato)

#### Sigillo R1

LOCKED-IN 23/05/2026 14:00 CEST. Revisioni successive solo append-only.
