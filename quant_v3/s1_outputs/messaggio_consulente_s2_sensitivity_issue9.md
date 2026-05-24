# S2 — Sensitivity selettore + IC bootstrap Δ Sharpe + Issue #9 (Sharpe definition mismatch)

**Data**: 24/05/2026 06:40 CEST
**Mittente**: Luigi Missere
**Riferimento**: Bug 8 SUPERATO da v8 (commit 4326045); sensitivity selettore (commit c09e7dd)
**Branch**: `feature/v8-s1-refactor`

---

## 1. Esito robustness check (come da tua direttiva)

Ho eseguito i tre test che mi hai chiesto:

### 1.1 Sensitivity 4 selettori — F2 OOS v8 (T=65, grid smoke 8 trial)

| Selettore | Trial | mc | thr | Sharpe_a | ρ_AR(1) | DSR | PnL % |
|---|---|---|---|---|---|---|---|
| A · max-Sharpe | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 | +20.45 |
| B · max-DSR | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 | +20.45 |
| C · min-\|ρ\| | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 | +20.45 |
| D · max-Sharpe con vincolo \|ρ\|<0.10 | 1 | 2 | 0.15 | +4.389 | −0.080 | 0.975 | +20.45 |

**Convergenza completa**: i 4 selettori scelgono lo stesso trial. La selezione del best_param v8 (mc=2, thr=0.15) è quindi ROBUSTA rispetto al criterio di scelta — non è artefatto del fatto che abbiamo massimizzato Sharpe in particolare.

Nota tecnica: trial 1, 2, 5, 6 hanno tutti stat identiche (Sharpe 4.389, ρ −0.080, PnL +20.45%). Sul grid smoke (mc ∈ {2,3} × thr ∈ {0.15,0.25} × max_sector_pct ∈ {0.4,0.5}) il parametro `thr` e `max_sector_pct` sono **non-informativi** quando mc=2: la strategia diventa indipendente da quei due assi. Solo `min_concordant` muove il portafoglio. Lo segnalo perché potrebbe meritare un'analisi più ampia di grid (es. thr più discriminanti) in S1.5, ma non blocca la chiusura Bug 8.

### 1.2 IC bootstrap Δ Sharpe mc=2 (4.389) vs mc=3 trial-7 (1.610)

B=10000, seed=20260524, su daily_return F2 OOS (65 osservazioni).

| Metodo | IC 95% Δ Sharpe | p-value (H0: Δ=0) |
|---|---|---|
| i.i.d. resample | [−0.517, +5.953] | 0.0956 |
| Block bootstrap L=5 | [−0.636, +6.675] | 0.1196 |

**Entrambi gli intervalli contengono zero**. La preferenza per mc=2 sopra mc=3 NON è statisticamente significativa al 95% su questo campione. Con T=65 il potere è limitato — è il punto fragile della chiusura. La nostra giustificazione di v8 quindi non è "mc=2 batte mc=3", ma "il selettore data-driven sceglie mc=2 sul training, e questo è coerente con la procedura preregistrata".

### 1.3 Cluster 2022 INCONCLUSIVE_DEGRADED

Confermo che resta indagine S2 separata, non unificata con Bug 8. Decisione mia del 24/05 06:30. Procederò quando S1.5 esecuzione 3 sarà completata.

---

## 2. Issue #9 — Sharpe definition mismatch (richiede tua decisione)

Durante la verifica numeri ho riscontrato una discrepanza ~2x sulla stessa serie F2 OOS che ti devo segnalare prima di chiudere:

| Fonte | Definizione | Sharpe F2 OOS mc=2 | Sharpe F2 OOS mc=3 (trial 7) | Δ |
|---|---|---|---|---|
| **wf_runner Backtrader** | `bt.analyzers.SharpeRatio` su equity post-MtM | 1.94 | 1.91 | 0.03 |
| **Raw daily collector** | `mean(daily_return) / std(daily_return) × √252` | 4.389 | 1.610 | 2.78 |

I numeri che ti avevo passato in precedenza (1.94 vs 1.91) sono quelli di Backtrader. I numeri nuovi del sensitivity (4.389 etc.) sono quelli raw del collector dumpato via `--save-equity-csv`. **Sono la stessa serie sottostante**, ma:

- Backtrader calcola Sharpe sulla `equity` post mark-to-market, che include cash drag (capitale non investito remunerato a 0) e timing intra-bar. Sul rerun esec 2 il portafoglio resta ~50–60% in cash mediamente → equity meno volatile → Sharpe basso.
- Raw daily collector calcola Sharpe direttamente sui `daily_return` aggregati dalle posizioni effettivamente aperte → no cash drag → Sharpe alto.

**Le due grandezze divergono di un fattore ~2.3x su mc=2 e ~1.2x su mc=3**. La divergenza è asimmetrica perché mc=2 ha più periodi flat (peggio per Backtrader, neutro per raw).

### Domande operative

1. **Quale Sharpe vuoi come autoritativo nel paper v8?** Le opzioni che vedo:
   - **(a)** Backtrader post-MtM — riflette ciò che farebbe un broker, ma sottostima la qualità del segnale alpha
   - **(b)** Raw daily collector — riflette la qualità del segnale, ma ignora cash drag e va specificato
   - **(c)** Entrambi con disclosure esplicita
2. **L'IC bootstrap Δ Sharpe l'ho calcolato sulla definizione raw (b)** perché è quella che il sensitivity restituisce direttamente da `f2_metrics_per_trial`. Vuoi che lo rifaccia su Backtrader Sharpe (a) usando il rerun esec 2 daily? Lo posso fare ma serve girare di nuovo wf_runner mantenendo equity di tutti i trial, oggi salviamo solo quella del best_param.
3. **Bug 8 SUPERATO da v8 resta valido** indipendentemente da come decidi su Issue #9 — la chiusura non dipende dal numero esatto di Sharpe, dipende dalla traccia di derivazione (best_param flip mc=3 → mc=2, ρ_AR(1) funzione monotona di mc). Cerco solo conferma.

### Cosa propongo (se non hai preferenze)

Disclosure obbligatoria nel paper v8 §4 (metriche F2):

> Riportiamo Sharpe in due definizioni: (i) `bt.analyzers.SharpeRatio` su equity post-MtM con cash drag esplicito (definizione "broker"), (ii) Sharpe annualizzato `mean/std·√252` sui daily_return aggregati delle posizioni effettivamente aperte (definizione "alpha-pure"). Le due divergono di un fattore 1.2x–2.3x in funzione del cash drag. Adottiamo (i) come metrica primaria per coerenza con la prassi di backtest istituzionale; (ii) come metrica di diagnostica del segnale.

Aspetto tua decisione su (1), (2) e conferma su (3) prima di sigillare.

---

## 3. Stato esecutivo per chiusura

- Commit Bug 8 chiusura: `4326045` (pushato)
- Commit sensitivity: `c09e7dd` (pushato)
- Audit journal v7.3 sealed estratto: `quant_v3/s1_outputs/s2_indagine_bug8/audit_journal_v7_3_sealed.md` (SHA 04d08f88, da estratto e4dc7aa)
- `task6_returns.npz` recuperato: SHA 5327118365 (da estratto 2114311)
- Disclosure v8 redatta (bozza): "ρ_AR(1) F2 OOS è funzione monotona di min_concordant. Sul best_param v8 (mc=2) F2 è mean-reverting. La proprietà 'persistente' osservata in v7.4 era condizionata su mc=3, non universale."

Deadline residue: S1.5 entro 06/06 23:59 CEST, chiusura S1 completa 13/06.

In attesa di tue risposte su Issue #9.

— Luigi
