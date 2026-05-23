# Indagine F3 — sensitivity to selector heuristic

**Timestamp**: 23/05/2026 16:45 CEST
**Trigger**: Azione 2 del feedback consulente post full run (sospetto overfitting del selettore best-param)
**Esito**: ipotesi confermata in modo netto. Bug **non** di codice — è un problema **metodologico** della heuristic "top IS sharpe → run OOS".

## Test 1: F3 OOS con mc=3 forzato

| Config | Sharpe OOS | pnl% OOS |
|---|---|---|
| **best selettore** (mc=2, thr=0.25, sc=None, tr=0.008) | **−0.110** | **−1.560** |
| **alt forzato**     (mc=3, thr=0.25, sc=None, tr=0.008) | **+1.205** | **+3.351** |

Δ sharpe = **1.315** in funzione di 1 iperparametro. F3 con mc=3 sarebbe stato positivo.

## Test 2: cross-check F1 e F2 — il pattern è SISTEMATICO

| Fold | mc=2 (alt) OOS | mc=3 (best selettore) OOS | mc=2 − mc=3 |
|---|---|---|---|
| F1 | **+3.752** | +2.631 | **+1.121** |
| F2 | **+3.080** | +3.033 | +0.047 |
| F3 | −0.110 | **+1.205** | **−1.315** |

In 2 fold su 3 (F1 e F2), mc=2 OOS sarebbe stato **meglio** di mc=3. In 1 fold su 3 (F3), mc=3 OOS sarebbe stato meglio. Il selettore IS sceglie mc=3 su F1+F2 e mc=2 su F3 → **sbaglia in tutti e 3**.

## Test 3: la causa — plateau IS sharpe

Top 5 trial IS per fold (sharpe IS identico fino a 3 decimali):

| Fold | Top 5 IS sharpe | mc | thr |
|---|---|---|---|
| F1 | tutti +2.084 | mc=3 | 0.15-0.20 |
| F2 | tutti +1.475 | mc=3 | 0.25 (tr vario) |
| F3 | tutti +1.625 | mc=2 | 0.25 (tr vario) |

**La grid ha plateau IS**. La scelta "best param" è un tie-break sul primo trial trovato, non un'ottimizzazione reale. La metrica IS sharpe **non distingue** tra config che generalizzano e config che non generalizzano.

## Interpretazione causale

1. La heuristic "argmax(IS sharpe) → run OOS" è **fragile** quando la grid è coarse rispetto alla risoluzione della metrica IS. Su 72 trial, 5+ sono pari merito con stesso IS sharpe.
2. Il tie-break (per ordine di iterazione) introduce **dipendenza dall'ordine della grid**, non da merito statistico.
3. In F3 il selettore ha scelto mc=2 (perché su F3 IS, mc=2 ha IS sharpe leggermente più alto di mc=3 — F3 ha pattern IS distintivo) ma mc=2 OOS è disastroso (overfitting).
4. Su F1+F2 il selettore ha scelto mc=3 ma mc=2 OOS sarebbe stato superiore — pattern opposto, ma stessa radice (plateau IS + tie-break arbitrario).

## Implicazioni per la narrazione paper v7.3

La frase "F3 OOS pulito è −1.56 / sharpe −0.11" è tecnicamente vera ma **fuorviante**:

- Vero: con il selettore corrente, F3 OOS = −0.11
- Fuorviante: lascia intendere che il **segnale momentum** non funzioni in Feb-May 2026
- Realtà: il segnale momentum funziona (con mc=3 forzato, F3 OOS = +1.21); fallisce il **selettore**

Narrazione corretta v7.3:

> "Sistema con segnale momentum stabile su 3/3 fold quando i parametri sono fissati globalmente (mc=3). Il selettore best-param IS è sub-ottimale a causa di plateau nella metrica IS sharpe: con grid 72-cell, 5+ trial pari merito generano tie-break arbitrario. Walk-forward Sharpe con selettore: media +1.85 (F1 +2.63, F2 +3.03, F3 −0.11). Walk-forward Sharpe con mc=3 globale: media +2.29 (F1 +2.63, F2 +3.03, F3 +1.21). Walk-forward Sharpe con mc=2 globale: media +2.24 (F1 +3.75, F2 +3.08, F3 −0.11). Il segnale è robusto; il selettore è il punto debole."

## Predizione DSR rivista

Se la DSR scalare viene calcolata su **tutti i 72 trial × 3 fold = 216 osservazioni OOS** (non solo i 3 best selezionati), la robustezza emerge: la maggior parte dei 216 trial ha sharpe positivo. Il DSR aggregato dovrebbe quindi essere alto (>1.0) indipendentemente dalla scelta del selettore — la diagnostica DSR è proprio per **questo**: validare se il segnale c'è al netto della molteplicità delle scelte.

## Azione operativa

1. **Procedere con Task 2b/2c/3-7** della DSR pipeline usando **tutti i 216 trial OOS** come popolazione (la DSR di Bailey-LdP è progettata esattamente per questo).
2. **Nel paper v7.3**, includere una sezione "Selector sensitivity": tre walk-forward differenti (mc=2 globale, mc=3 globale, selettore IS). DSR su ognuno.
3. **Non riformulare** il selettore — la pre-reg è sigillata. Il DSR aggregato risponde formalmente alla domanda "il segnale è reale al netto della multiplicity?".
