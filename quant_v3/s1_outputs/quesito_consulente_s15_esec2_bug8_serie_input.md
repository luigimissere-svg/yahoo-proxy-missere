# Quesito consulente — S1.5 esec 2, Bug 8 UNRESOLVED, gap ρ confermato in segno opposto

**Data:** 2026-05-24 06:18 CEST
**Branch:** `feature/v8-s1-refactor`
**HEAD:** `63d9be3`
**Mittente:** Luigi Missere
**Oggetto:** richiesta indagine S2 sulla serie input del test AR(1) sealed v7.3 task 7a

---

## Contesto

Esec 1 (ricostruzione equal-weight da ledger F2 + OHLCV) aveva prodotto ρ_AR(1) = **−0.0998** contro sealed v7.3 = **+0.1883**, gap −0.288. Per autofalsificazione Add 11 §3 D3 l'esito è stato archiviato DEGRADED e in Add 12 D3-bis ho cambiato default: rerun diretto del `wf_runner` con dump equity OOS via nuovo flag `--save-equity-csv` (cherry-pick `65efd0c` + `81219ab` da serie F2 portati sul branch S1.5).

## Esec 2 — rerun wf_runner

Identica griglia smoke (8 combo), portfolio 35 ticker, IS=12m / OOS=3m / step=3m, warmup-bars=50.

Best params F2 nel rerun: `threshold=0.25, min_concordant=2, max_sector_pct=None` — **identici al sealed v7.3** (replicabilità best_params OK). Sharpe annualizzato F2 OOS rerun = 1.94, PnL = 21.3%.

## Verifica vincoli Add 12 D3-bis (T=65 daily portfolio returns OOS F2)

| Vincolo | Target sealed | Rerun | Gap | Esito |
|---|---|---|---|---|
| V1 ρ_AR(1) ±0.02 | +0.1883 | **−0.0807** | −0.2690 | FAIL |
| V2 T ∈ [60,70] | 65 | 65 | — | PASS |
| V3 Q(10) ±10% | 20.374 | **13.710** | −6.664 | FAIL |

Verdetto: 2 FAIL su 3 → escalation S2. Esec 3 leverage analysis NON eseguita (gate non superato).

## Domanda chiave

La replicabilità dei best_params F2 è perfetta, ma la **serie 65 daily portfolio returns** prodotta dal collector ufficiale `--save-equity-csv` produce ρ_AR(1) **negativo** (sia su 65 daily inclusi zeri, sia su 63 non-zero: ρ = −0.105). Sia rerun che ricostruzione esec 1 convergono su segno opposto rispetto al sealed v7.3 +0.1883.

Conclusione: la serie input del test AR(1) sealed task 7a v7.3 **non è** la `daily_return` corrente del collector.

### Cause candidate per S2

- **C1** — cash drag / MtM equity Backtrader (la equity_curve include cash idle, mentre v7.3 potrebbe aver lavorato su returns post-trade pesati)
- **C2** — serie sealed = equity_curve raw (level) e ρ calcolato sui returns derivati con metodo diverso (es. log-returns vs simple returns, o weighting per gross exposure)
- **C3** — Bug 5 pre-roll/warmup differente nella build sealed (i 326 `oos_n_bars` del collector includono warmup post-IS che la build v7.3 potrebbe escludere)

## Cosa serve

1. Conferma quale serie esatta è stata data in input al test AR(1) lag-1 nel task 7a v7.3 (`audit_journal_v7_3.md` riga 802, sealed 2026-05-23). Definizione operativa: file / colonna / finestra / filtri.
2. Se la serie è derivata (es. log-returns su equity_curve raw, weighting custom), specifica la formula.
3. Indica se ritieni Bug 8 ancora ARMATO con priorità ALTA per S2, o se la sua definizione stessa va rivista alla luce della non-replicabilità.

## Stato cluster 2022

In parallelo, Gate 30/05 ha squalificato sia Opzione A (`fja05680/sp500` = Wikipedia-dependent) sia fallback B (Norgate trial 2y, cluster 2022 escluso). Decisione committente: cluster 2022 → **INCONCLUSIVE_DEGRADED Alt 3** (simmetrico 76-ibrido, deferred S2 alta priorità). IC95% sealed t-Student [0.470×, 2.557×], bootstrap [0.806×, 2.217×]; ratio osservato 1.5126× resta MARGINALE robustezza DEBOLE.

## Cambio regime (24/05 05:58 CEST)

Committente ha snellito le regole: meno formalismo, focus sviluppo software. Add 13 (degradazione formale cluster 2022) e Add 10 (recupero pulizia documentale) **skippati** — sostanza preservata nei commit, niente addendum dedicati. Append-only su file già sealed e SHA256 restano vincoli irriducibili.

## Artefatti rerun (SHA256)

| File | SHA256 |
|---|---|
| `equity_full.csv` (7832 righe, 24 backtest) | `c182dd2d3b59c4c589d9342f0827a692475971ce7bba398b6b29d79f5451a1fb` |
| `trades_full.csv` | `6b62550c9e8cdc52f1a4d06faf97765e32124bb9a05a8cbf6f75a8b5c3e2c6d9` |
| `wf_rerun_results.csv` | `baccf1676bc8d77d056ee627b394871272463a943a779dc16010e7c94ad04c2d` |
| `wf_rerun_stability.json` | `66a3760f1989ac3e445d52962b6fdab6060a16f27e5265ecd5d05f4384758c20` |
| `f2_oos_daily_returns_rerun.csv` | `8d1616a7520792ed37343bc9ee51da76f90e64184dc9653f07786140a3b62e93` |
| `f2_rerun_verifica_gap.json` | `29850620ec94eb4a1de4a48aa5a43ad32e6ac393df0ecd8e4d912f4382672153` |
| `extract_f2_and_verify.py` | `2fb55774bde0e2f6d84c9d88cfa15dfcb36f01c8571d850b193d928a14a81fce` |

## Catena commit sessione

`a49a5a5` (Add 12 D3-bis) → `e612b2b` (verifica Gate 30/05) → `65efd0c` (cherry-pick TradeLedger) → `81219ab` (cherry-pick --save-equity-csv) → **`63d9be3`** (rerun F2 + verifica gap)

## Next

Attendo riscontro sulla fonte serie sealed prima di muovere S2. Bug 8 resta UNRESOLVED, deferred S2 alta priorità (insieme a cluster 2022 INCONCLUSIVE_DEGRADED).

— Luigi
