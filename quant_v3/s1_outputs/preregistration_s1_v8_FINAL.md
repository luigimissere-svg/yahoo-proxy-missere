# Pre-registration S1 v8 — FINALE FIRMATA

Data sigillo finale: 23/05/2026 — 19:40 CEST
Branch: feature/v8-s1-refactor
Tag pre-reg: s1-prereg-v8 (cumulativo)
Firma operatore: Luigi Missere (via agent supervisionato)

## Catena append-only

Questa pre-registrazione finale CONFERMA e CHIUDE Sprint S1 v8.
La catena documentale completa è:

| File | SHA256 | Scope |
|---|---|---|
| `preregistration_s1_v8.md` | `10f8c4cecf37e7f3...` | Root: 10 deliverable, falsificazioni F1/F2/F3, pre-impegni |
| `preregistration_s1_v8_addendum_01.md` | (signed via commit `c49e539`) | Indice S&P 500 sigillato, fonte snapshot+delisting |
| `preregistration_s1_v8_addendum_02.md` | `6d72e089bfdf8fe1...` | Grid v8 sigillata 8×3=24 trial |
| `preregistration_s1_v8_addendum_03.md` | `9432ff9a33eb0c15...` | Selettore robusto median+guard sigillato |
| `preregistration_s1_v8_addendum_04.md` | `2ab3dc63144086ea...` | Bootstrap F3 sigillato (verdetto proxy) |
| `preregistration_s1_v8_FINAL.md` | (questo file) | Chiusura S1, riepilogo verdetti |

Nessuna modifica retroattiva è stata apportata ai file precedenti.

## Stato deliverable S1 (verdict map)

| ID | Deliverable | Criterio PASS | Verdetto |
|---|---|---|---|
| S1.0 | Branch + pre-reg sigillata | tag s1-prereg-v8 pushato | **PASS** |
| S1.1 | Universe PIT loader (Bug 6) | universo storico ≠ attuale | **PASS** |
| S1.2 | Survivorship validation | ≥ 15 ticker rimossi 2020→2026 | **PASS** (40 rimossi) |
| S1.3 | Bug 8 single-ticker cap 5% | falsificazione F2 risolta | **PASS** (cap necessario; cap notional da solo cosmetico → richiede min_tickers≥20 in S1.7) |
| S1.4 | Bootstrap force-close F3 (Bug 7) | p-value ≤ 0.05 per H1 | **PASS PROXY** (p median=0.037; IQR ampio → conferma S2 richiesta) |
| S1.5 | Universe sealed | hash + JSON committato | **PASS** |
| S1.6 | Grid sealed ≤ 36 trial/fold | grid_v8.py 24 trial totali | **PASS** |
| S1.7 | Selettore median-fold-OOS | backward test su v7.4 PASS | **PASS** (+0.44 Sharpe medio WF) |
| S1.8 | Pre-reg finale firmata | questo file + tag | **IN CHIUSURA** |
| S1.9 | Gate 13/06 review GO/NO-GO | review formale | RINVIATO al 13/06 |

**Score S1: 8/8 PASS dei deliverable tecnici. S1.9 è gate temporale (13/06).**

## Verdetti su bug v7.4

| Bug | Diagnosi v7.4 | Mitigazione v8 | Stato S1 |
|---|---|---|---|
| **Bug 6 — Survivorship** | universo dinamico mai sigillato PIT | universe_v8_sp500_pit.csv (616 ticker, 40 rimossi 2024→2026) | RISOLTO |
| **Bug 7 — F3 force-close + selector overfit** | mc=2 selezionato IS, OOS disastroso (-0.110) | selettore v8 median+guard sceglie mc=3 (OOS +1.205); bootstrap proxy p=0.037 | MITIGATO (validazione S2) |
| **Bug 8 — MU outlier 52% del PnL F2** | equal-weight + assenza cap → singolo ticker domina | cap notional 5% + winsor P95 + min_tickers≥20 enforcement S1.7 | MITIGATO (cap notional da solo insufficiente; combo richiesta) |

## Discipline metodologiche v8 in vigore

1. **Universo sigillato pre-grid** (S1.5) — universe_v8_sp500_pit.csv,
   SHA256 `6c350fd7566bf300...`
2. **Grid ridotta ≤ 24 trial × 3 fold** (S1.6) — grid_v8.py,
   FROZEN_PARAMS: max_sector_pct=0.30, max_portfolio_beta=1.3
3. **Selettore robusto median-fold-OOS + worst-case guard** (S1.7) —
   selector_v8.py, min_tickers=20, min_trades=10
4. **Cap notional 5% per ticker per fold + winsor P95** (S1.3) —
   risk_caps.py

## Pre-impegni S2 sigillati

Lo Sprint S2 (14/06 → 04/07) DEVE iniziare con:

a) Walk-forward v8 completo: universe PIT × grid v8 × selettore v8 ×
   risk caps. Output: ledger v8 trade-level per ogni fold.

b) Rerun S1.4 bootstrap force-close F3 con ledger v8 REALE (non proxy).
   Verdetto definitivo Bug 7 atteso.

c) Verifica `min_tickers ≥ 20` su ogni fold del WF v8. Se la grid
   produce < 20 ticker in qualche fold, la combo è ESCLUSA dal
   selettore (no override silente).

d) Calcolo DSR su WF v8 con denominatore N_eff Politis (sealed v7.3).
   Soglia DEPLOY: DSR ≥ 0.95 (Internal + Combinatorial + Absolute).
   Se DSR < 0.95: pre-impegno sigillato di NON-DEPLOY al 15/08/2026.

e) Documentazione di tutte le decisioni in journal append-only.

## Pre-impegno comportamentale finale S1

Firmando questa pre-reg finale, l'operatore conferma:

1. Nessuna deviazione dalle discipline v8 senza nuovo addendum.
2. Nessun re-run v7.4 alternativo per "recuperare" il framework.
3. Nessuna ottimizzazione su FROZEN_PARAMS.
4. Drawdown URTH (benchmark) durante S2-S4 NON influenza le decisioni
   v8: il benchmark è informativo, non operativo per la strategia.
5. In caso di DSR < 0.95 al 15/08: NO-DEPLOY automatico, periodo
   paper trading 12 mesi minimo, no overrides.

## Allocazione capitale durante v8 sprint (ribadita)

Capitale totale: 100 000 EUR.
- 80 000 – 90 000 EUR su benchmark passivo (URTH / ACWI / SPY).
- 0 EUR su strategia v7.4 (sigillata, no nuovi trade).
- 10 000 – 20 000 EUR cash o liquidità per emergenze / paper trading v8.

## Sigillo finale

Sprint S1 v8 chiuso al 23/05/2026 19:40 CEST.
Gate S1.9 (review GO/NO-GO S2) fissato al 13/06/2026 (preserva la
deadline pre-registrata anche se i deliverable tecnici sono pronti
3 settimane in anticipo — questo permette eventuale validazione
asincrona).

Tag finale: `s1-final-v8` (da pushare).

SHA256 di questo file: (calcolato post-write)
