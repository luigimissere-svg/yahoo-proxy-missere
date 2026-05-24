# Journal — S1.5 esec 4 CHIUSURA (cap 20 / per-ticker-cap 0.05)

**Timestamp**: 2026-05-24 11:05 CEST
**Branch**: `feature/v8-s1-refactor`
**Parent commits**: `170e7b2` (diagnostica) → `b2ed2ce` (preregistrazione esec 4)
**Verdetto**: **FAIL** (H1 FAIL, H4 FAIL | H2 PASS, H3 PASS)

---

## 1. Esito sintetico

| Ipotesi | Esec 3 | Esec 4 | Soglia |
|---|---|---|---|
| H1 — non degenere | FAIL (100%, 76 coppie) | **FAIL (100%, 28 coppie)** | ≤25% |
| H2 — ρ_AR(1) ~ mc monotono | PASS (slope +0.333, p=5e-24) | **PASS (slope +0.218, p=1.3e-13)** | slope>0 ∧ p<0.10 |
| H3 — selettori convergenti | PASS (4/4 → mc=2, thr=0.05) | **PASS (3/4 → mc=2, thr=0.30)** | ≥3/4 |
| H4 — Sharpe BT OOS best ≥ 1.5 | PASS (1.944) | **FAIL (1.048)** | ≥1.5 |

Per decision tree autorizzato 24/05 10:30 CEST: FAIL → **opzione (d) chiusura S1.5**, accettazione H1+H4 come limite del setup portfolio, dichiarazione esplicita nel paper v8 deferred a S3 con universo esteso. Niente (e) o (f) inventati post-hoc.

---

## 2. Setup vs esec 3

Identico a esec 3 tranne:

| Parametro | Esec 3 | Esec 4 |
|---|---|---|
| max_positions | 10 | **20** |
| per_ticker_cap | 0.10 | **0.05** |
| Esposizione totale teorica | 1.00 NAV | 1.00 NAV (invariata) |

Disclosure post-hoc: parametri derivati dalla diagnostica `s15_diag_buy_pre_cap_report.json` (SHA `a82c8c1e…`). Razionale formale in preregistrazione `preregistration_s15_exec4_cap_20_005.md` (SHA `fa3b149a86bf10ed6b7011e9fca11026934d0c68c3c147f2df385a99302bec61`).

Run autoritativo: 111 backtest cerebro, ~30 min walltime, PID 91986, completato senza errori. Universo portfolio 35 ticker invariato. Grid `GRID_S1_5_EXEC3` (6×3×2=36 combo) invariata.

---

## 3. H1 — Analisi dettagliata (FAIL nominale, miglioramento sostanziale)

| Indicatore | Esec 3 | Esec 4 |
|---|---|---|
| n trial validi | 24/36 | 24/36 |
| n trial invalidi NaN (mc=4) | 12 | 12 |
| n trial degenerati | 24 (100%) | 24 (100%) |
| **degenerate_pairs** | **76** | **28** |
| Sharpe distinti mc=2 (12 trial) | **1** valore (4.389 identico × 12) | **6** valori distinti |
| Sharpe distinti mc=3 (12 trial) | 5 valori | **5** valori |

Lettura tecnica:

In esec 3, i 12 trial mc=2 producevano Sharpe **identico bit-a-bit** (4.388680 × 12) perché il cap=10 saturava il ranking prima del thr → thr letteralmente non influenzava nulla.

In esec 4, i 12 trial mc=2 producono **6 valori Sharpe distinti** — uno per ogni thr (0.05, 0.10, 0.15, 0.20, 0.25, 0.30). Il thr ora discrimina: ogni thr genera un portafoglio diverso. La degenerazione residua è solo **msp**: `msp ∈ {None, 0.30}` produce coppie identiche perché i sector cap non sono mai binding (le esposizioni settoriali del portafoglio espanso non eccedono 30% nei fold testati).

H1 FAIL nominale 100% perché la definizione di "degenerato" è coppia con `|ΔSharpe|<0.05`. Con `msp=None` vs `msp=0.30` producono coppie esattamente identiche → 12+12 = 24 trial in coppie. La soglia 25% del PASS è quindi non raggiungibile finché c'è un parametro a 2 livelli che non influenza nulla nel range corrente.

Conclusione H1: la modifica (20, 0.05) ha **eliminato la saturazione del cap** (diagnostica confermata empiricamente) ma rimane una **degenerazione strutturale lieve** dovuta a msp non binding sui sector cap del portafoglio attuale. Questa è una proprietà del dataset/universo, non del meccanismo di selezione.

---

## 4. H2 — Conferma teoria Bug 8

| Statistica | Esec 3 | Esec 4 |
|---|---|---|
| slope | +0.333 | +0.218 |
| intercept | -0.746 | -0.450 |
| r | 0.9955 | 0.9598 |
| p-value | 5.4e-24 | 1.3e-13 |
| ρ̄(mc=2) | -0.080 | -0.013 |
| ρ̄(mc=3) | +0.253 | +0.205 |

Coerente: slope positiva significativa in entrambe le esecuzioni, ρ̄(mc=3) > ρ̄(mc=2) in entrambe. La pendenza è leggermente minore in esec 4 perché ρ̄(mc=2) si è avvicinata a zero (meno mean-reverting con cap espanso), ma il segno e la significatività sono robusti.

**Bug 8 SUPERATO da v8 resta confermato indipendentemente dal FAIL H1+H4.** ρ_AR(1) è funzione monotona crescente di `min_concordant`, replicato in due esecuzioni indipendenti con setup operativo diverso.

---

## 5. H3 — Selettori convergono (con thr ora discriminante)

| Selettore | Esec 3 trial | Esec 4 trial |
|---|---|---|
| A — max Sharpe BT | (mc=2, thr=0.05) | **(mc=2, thr=0.30)** |
| B — max DSR | (mc=2, thr=0.05) | (mc=2, thr=0.30) |
| C — min \|ρ_AR(1)\| | (mc=2, thr=0.05) | **(mc=2, thr=0.25)** ← diverge |
| D — max Sharpe \|ρ\|<0.10 | (mc=2, thr=0.05) | (mc=2, thr=0.30) |

Esec 3: convergenza 4/4 su `thr=0.05` — ma era falsa convergenza perché thr non era informativo (saturazione, vedi diagnostica).

Esec 4: convergenza **3/4 su `(mc=2, thr=0.30)`**. Il selettore C diverge su `thr=0.25`. **Thr ora discrimina genuinamente**: i selettori indipendenti scelgono valori di thr diversi in base alla metrica privilegiata. La convergenza 3/4 è soddisfatta come da preregistrazione ma è qualitativamente più informativa di esec 3.

Notabile: il signature H3 winner `(mc=2, thr=0.30, msp=NA)` (trial 31) ha Sharpe raw OOS F2 = **1.848** (sopra soglia 1.5).

---

## 6. H4 — FAIL come da preregistrazione

`wf_runner` per il fold F2 ha selezionato come best param `(mc=3, thr=0.30, msp=None)` perché ha il **massimo Sharpe IS** (= 1.318). Sharpe BT OOS di questo param: **1.048**. < 1.5 → H4 FAIL.

Osservazione interpretativa neutra (non rescue): il selettore H3 OOS (mc=2, thr=0.30) avrebbe dato Sharpe OOS 1.848. Tuttavia, secondo la regola walk-forward standard, la selezione del best param deve avvenire sui dati IS, non OOS, per evitare data leakage. La preregistrazione H4 dice "Sharpe operativo Backtrader del **best_param** OOS ≥ 1.5", dove best_param = scelta IS del wf_runner. Mantengo il verdetto FAIL come da preregistrazione. Niente prompt-engineering del verdetto.

Il fold F1 ha Sharpe BT OOS 1.176, F3 ha 0.866. Anche prendendo il fold più favorevole (F1), nessuno raggiunge 1.5.

---

## 7. Stability — risultato collaterale importante

Esec 4 stability:

```json
"stable_params": {
  "threshold": 0.3,
  "min_concordant": 3,
  "max_sector_pct": null
}
```

**Tutti e 3 i fold convergono su `(mc=3, thr=0.30, msp=None)`** come best IS Sharpe. È una stability 3/3 — proprietà non presente in esec 3 (nessun param stabile 3/3). Questo è un risultato genuinamente positivo del nuovo setup operativo: il wf_runner ora produce parametri stabili.

Però il fold-wise Sharpe BT OOS (1.176 / 1.048 / 0.866) mostra che la performance OOS è insufficiente per H4. Stable ≠ performante.

---

## 8. Mc=3 vs ρ_AR(1) sealed v7.4

Annotazione richiesta dal consulente 24/05 10:30 CEST: tracciare eventuale divergenza mc=3 con cap=20 rispetto al valore sealed v7.4 (+0.1883).

Esec 4 fold F2 OOS, trial mc=3 thr=0.30 msp=None (best param wf_runner):

- ρ_AR(1) = +0.2511 (estratto da equity F2 OOS, n=65 bar, n_nonzero=69 di cui rilevanti)

Valore sealed v7.4 Bug 8: +0.1883 (su returns sealed task6).

Δ = +0.0628. Differenza non trascurabile, **ma**:

1. Cambio del setup operativo (cap, per-ticker-cap) modifica la composizione del portafoglio → returns BT diversi.
2. La teoria Bug 8 prevede ρ_AR(1) monotona crescente in mc, con sensitivity al dataset specifico. Valore esatto +0.1883 era legato al setup esec 2 sealed.
3. H2 conferma il pattern qualitativo (ρ̄ mc=2 < mc=3) in entrambe le esecuzioni.

Questione separata, NON riapertura di Bug 8. Tracciata qui per audit.

---

## 9. Implicazioni operative

### Bug 8

`f51ed7e` (Bug 8 SUPERATO da v8) **resta valido**. H2 PASS in entrambe le esec, slope significativa. Bug 8 chiuso.

### Leverage analysis

**Bloccata**. Decision tree autorizzato → FAIL → opzione (d). Niente leverage analysis su S1.

### Paper v8 §4.x

Dichiarazione esplicita da aggiungere:

> "S1.5 esec 4 (max_positions=20, per_ticker_cap=0.05) ha eliminato la saturazione del cap diagnosticata in esec 3 ma non ha superato H1 (degenerazione residua su parametro `max_sector_pct` non binding) né H4 (Sharpe BT OOS best_param IS = 1.048 < 1.5). H1 limite noto del setup portfolio 35 ticker. Leverage analysis deferred a S3 con universo esteso."

### Sealed

| File sealed | Stato |
|---|---|
| Disclosure paper v8 §3 (Sharpe operativo Backtrader 1.94/1.91) | invariato |
| Disclosure paper v8 §4.1 (Sharpe segnale 4.389/1.610) | invariato |
| Disclosure paper v8 §4.X (ρ_AR(1) Bug 8 funzione mc) | invariato, rinforzato da H2 esec 4 |
| Sigillo `f51ed7e` Bug 8 SUPERATO | invariato |

---

## 10. SHA256 evidenze esec 4

| File | SHA256 |
|---|---|
| `s15_exec4_falsification.py` | `f0423b7babbe573f046545c16d96ea08af9126afb0d6766e3888ddd1d840aa64` |
| `s15_exec4_falsification_report.json` | `8c4e00438dea52b119997b9d2800016f0bc5dbf5f9a177903c33c5b300cc0b8a` |
| `s15_exec4_falsification_report.md` | `7f0eafc3efbcef8459e055ac0a030241407fe99ca7a67b6062b781262c38e211` |
| `s15_exec4_f2_results.csv` | `8287c9e70d18838cbf7cbda5ae3b7bd4caee00cf806ce3eb1e2b6ee12e94cc38` |
| `s15_exec4_f2_stability.json` | `a02275be331ecf3c20bc1be1f6d83e4b95e054197ae4856aabc2ab49279aeb92` |
| `s15_exec4_f2_equity.csv` (35244 righe) | `3b89fea971e15143bf8aa71176d04e0585558f9b5e0dc64dc36786ae1e2bf1ab` |
| `s15_exec4_f2_trades.csv` | `347870f33d6fcb05f64a98fe5bf3428d26c5b07faef721c0f897fe9e1875146b` |
| `s15_exec4_logs/run.log` | `0fa4e0eb6df14e60cb504d39fbabaf10a5f3942aefc7797c6f04b2175fa5e4d0` |

Preregistrazione SHA: `fa3b149a86bf10ed6b7011e9fca11026934d0c68c3c147f2df385a99302bec61`
Diagnostica SHA: `a82c8c1e2f633118db8a86214c0a3aa8c50160ddcbd3ec36b54c29ff0fe7d588`

---

## 11. Prossimi step

1. Commit + push chiusura esec 4 con questo journal.
2. Messaggio consulente con verdetto + raccomandazione formale chiusura S1.5 opzione (d).
3. Aggiornamento paper v8 §4.x con dichiarazione "H1 limit on portfolio setup".
4. S3 preregistrazione separata: universo esteso (1037 ticker EU+US), grid completa, leverage analysis sblocca su quel setup.
5. SEPARATO S2 cluster 2022 INCONCLUSIVE_DEGRADED invariato.
6. DEFERRED S3 bootstrap Δ Sharpe Backtrader full equity multi-trial invariato.

S1.5 chiusura come da decision tree autorizzato. S1 deadline 13/06 invariata per le altre attività non leverage-dependent.
