# Pre-registration S1 v8 — Addendum 02

Data sigillo: 23/05/2026 — 19:00 CEST
Riferimento: preregistration_s1_v8.md (root), addendum_01.md
Scope: S1.6 — Grid iperparametri ridotta sigillata

## Sigillo grid v8

File implementativo: `quant_v3/engine/grid_v8.py`
Sealed version: `v8.s1.6`

### Grid sigillata

```python
GRID_V8 = {
    "threshold":          [0.20, 0.25],
    "min_concordant":     [2, 3],
    "target_risk_pct":    [0.008, 0.010],
    "max_sector_pct":     [0.30],          # FROZEN
    "max_portfolio_beta": [1.3],            # FROZEN
}
```

- Combo per fold: 2 × 2 × 2 × 1 × 1 = **8**
- Combo totali (3 fold): **24**
- Conformità pre-reg ("≤36 per fold, ≤108 totali"): ✓

### Riduzione dimensionale vs v7.4 (GRID_FULL = 72 combo)

| Parametro | v7.4 | v8 | Motivazione |
|---|---|---|---|
| threshold | {0.15, 0.20, 0.25} | {0.20, 0.25} | 0.25 vincente in F1/F2/F3; 0.15 ridondante con 0.20 nel plateau IS F1 |
| min_concordant | {2, 3} | {2, 3} | Invariato — variabile chiave Bug 7 |
| target_risk_pct | {0.008, 0.010, 0.012} | {0.008, 0.010} | 0.008 vincente in tutti i fold v7.4; 0.012 mai selezionato |
| max_sector_pct | {None, 0.30} | {0.30} | FROZEN — doctrine v8 diversificazione settoriale obbligatoria |
| max_portfolio_beta | {None, 1.3} | {1.3} | FROZEN — doctrine v8 beta cap operativo |

### Frozen params (immutabili senza nuovo addendum)

```python
FROZEN_PARAMS = {
    "max_sector_pct":     0.30,
    "max_portfolio_beta": 1.3,
}
```

Questi parametri NON sono soggetti a ottimizzazione in S2. Modifica
richiede addendum pre-reg sigillato e giustificazione esplicita
(non riduzione di Sharpe — necessità metodologica).

### Plateau IS — implicazione per il selettore S1.7

Il journal F3 (`journal_f3_selector_overfitting.md`) ha mostrato che
in v7.4 la grid produce plateau IS (tutti i trial in F1 hanno Sharpe IS
+2.084 identico; F2 +1.475 identico; F3 +1.625 identico). Il selettore
`best param` su tie-break ha generalizzazione casuale.

Conseguenza S1.6: con grid ridotta a 8 combo per fold, il plateau IS
sarà ancora più probabile (meno punti di distinzione). Il selettore
S1.7 deve usare un criterio robusto **median-fold-OOS** che non
dipende dal tie-break su IS.

### Tracciabilità

- File: `quant_v3/engine/grid_v8.py` (81 righe)
- Test self-check eseguito: 24 trial totali, conformity True
- Commit (post-addendum): TBD
- Tag: rimane `s1-prereg-v8` (cumulativo, addendum non spostano il tag)

## Append-only

Questo addendum non modifica la pre-reg root né l'addendum 01.
Si aggiunge in coda alla catena. Eventuali modifiche future
richiedono addendum 03 firmato.

SHA256 di questo file: (calcolato post-write)
