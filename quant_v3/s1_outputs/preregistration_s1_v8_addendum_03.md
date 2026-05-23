# Pre-registration S1 v8 — Addendum 03

Data sigillo: 23/05/2026 — 19:15 CEST
Riferimento: preregistration_s1_v8.md (root), addendum_01.md, addendum_02.md
Scope: S1.7 — Selettore robusto median-fold-OOS con worst-case guard

## Sigillo selettore v8

File implementativo: `quant_v3/engine/selector_v8.py`
Sealed version: `v8.s1.7`

### Regola operativa sigillata

```python
def select_robust(aggregates, worst_case_guard=True, guard_fallback_topk=3):
    """
    1) Ordina valid combo per MAX(median Sharpe OOS).
    2) Se top.sharpe_min >= 0 → ritorna top.
    3) Altrimenti, tra le top-K per median, scegli combo con MAX(min OOS).
    """
```

Filtri pre-selezione (in `aggregate_cross_fold`):
- `min_tickers = 20` (default) — coerente con cap notional 5% S1.3
- `min_trades = 10` (legacy v7.4)
- `sharpe_flag == 'ok'` per OGNI fold (AND)

### Backward test su dati v7.4 (sealed)

Input: dati da journal_f3_selector_overfitting.md (Test 2).

| Combo | F1 OOS | F2 OOS | F3 OOS | median | min |
|---|---|---|---|---|---|
| mc=2, thr=0.25, tr=0.008 | +3.752 | +3.080 | −0.110 | 3.080 | −0.110 |
| mc=3, thr=0.25, tr=0.008 | +2.631 | +3.033 | +1.205 | 2.631 | +1.205 |

Risultati selettore:
| Selettore | Scelta | Media OOS WF |
|---|---|---|
| v7.4 (per-fold best IS) | mc=3/3/2 mix | +1.851 |
| v8 median puro | mc=2 (median 3.080) | +2.241 (ma F3 = −0.11 disastroso) |
| **v8 median + worst-case guard** | **mc=3** | **+2.290** |

Verdetto: PASS. Il selettore v8 con worst-case guard supera v7.4 di
**+0.44 Sharpe medio WF** (1.851 → 2.290, miglioramento +23.8%) e
soprattutto **evita il fold F3 negativo** che ha contribuito al
mancato passaggio del DSR threshold 0.95 in v7.4.

Output sigillato:
- `quant_v3/s1_outputs/s1_7_backward_test_report.txt`
- `quant_v3/s1_outputs/s1_7_backward_test_results.json`

### Interpretazione del worst-case guard

Il guard si attiva SOLO quando la top combo per median ha min < 0 in
qualche fold. In condizioni normali (tutte le combo top hanno min ≥ 0)
il selettore degenera al puro median-fold-OOS, come da pre-reg root.

Il guard NON è una black-box: il fallback a max(min) tra le top-K
per median (K=3 default) è giustificato perché:
- median premia performance centrale ma è insensibile a tail negative
- worst-case (min) è il criterio adversarial dello stesso campione
- combinare i due (median primario, min secondario condizionato)
  evita sia ottimismo (median-only) sia eccessivo conservativismo
  (worst-only nell'intero universo)

### Vincoli ereditati da S1.3

Il filtro `min_tickers >= 20` è la concretizzazione dell'enforcement
spostato da S1.3. Una combo che, in qualche fold, seleziona < 20
ticker distinti viene ESCLUSA (rende cosmetico il cap notional).
Questo crea un legame esplicito tra S1.3 (cap notional 5%) e S1.7
(selettore con min_tickers 20).

### Nota importante: dati v7.4 non v8-compliant

Il backward test usa `min_tickers=10` (non 20 default) perché v7.4 ha
10 trade per fold su 10 ticker distinti. Sotto regime v8 (min_tickers
20), TUTTE le combo v7.4 sarebbero ESCLUSE. Questo è coerente: v7.4
non era v8-compliant. Il backward test isola il selettore puro
dall'enforcement v8 per misurare il guadagno netto del selettore.

In v8 produzione, il vincolo min_tickers=20 si applica.

### Tracciabilità

- File: `quant_v3/engine/selector_v8.py` (~270 righe)
- File: `quant_v3/test_selector_v8_backward.py` (~200 righe)
- Commit (post-addendum): TBD
- Tag: rimane `s1-prereg-v8` (cumulativo)

## Append-only

SHA256 di questo file: (calcolato post-write)
