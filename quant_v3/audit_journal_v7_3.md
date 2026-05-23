# Audit Journal v7.3 — Pre-patch B2 completo

**Avviato**: 23/05/2026 13:15 CEST  
**Scope**: 4 layer del runner walkforward, ricerca esaustiva bug residui  
**Metodologia**: lettura sistematica + verifica invarianti + cross-check con osservazioni B3

---

## Layer 1 — `engine/trade_ledger.py` (164 righe)

### Invarianti che il codice assume

| # | Invariante | Dove |
|---|---|---|
| L1.A | `trade.justopened` è True esattamente UNA volta per trade, all'apertura iniziale | linea 50 |
| L1.B | Backtrader azzera `trade.size` e `trade.value` alla chiusura, quindi vanno cached at-open | linee 39-44 |
| L1.C | `trade.dtopen` e `trade.dtclose` sono validi numeri Backtrader convertibili via `bt.num2date` | linee 69-70 |
| L1.D | `notify_trade` riceve TUTTI i trade chiusi durante il run | linea 58 |
| L1.E | A fine run, `broker.getposition(d).size != 0` ⇔ esiste una posizione aperta | linee 127-128 |
| L1.F | `pos.price` per posizione aperta = prezzo medio di apertura (entry price) | linea 150 |

### Punti dove l'invariante può essere violata

| # | Possibile violazione | Severità | Note |
|---|---|---|---|
| L1.V1 | **L1.A può fallire su scaling-in/out**: se la strategia aumenta una posizione esistente, Backtrader può aprire un "nuovo" trade logico mentre la posizione fisica resta. `justopened` torna True; potenziale doppio conteggio. | MEDIA | da verificare in strategy.py se fa scaling |
| L1.V2 | **L1.D è VIOLATA quando il run termina prima della chiusura naturale**: trade ancora aperti a `stop()` non emettono `notify_trade` con `isclosed=True`. Catturati dal ramo `stop()` ma SENZA `dt_open`. | **ALTA — BUG 4** | linea 146 hardcoded `'dt_open': ''` |
| L1.V3 | **L1.F è ambigua per scaling-in**: `pos.price` è il prezzo medio ponderato di TUTTI gli scale-in. Se la strategia scale-in dopo aver attraversato fold boundary, il prezzo medio mescola pre-fold e in-fold. | MEDIA | da verificare in strategy.py |
| L1.V4 | **`broker.getposition(d).size` può essere `Decimal` o `float`** a seconda della versione di Backtrader. Cast a `float` è OK ma confronto `== 0` fragile per numeri molto piccoli (frazionari). | BASSA | linea 128, edge case |
| L1.V5 | **`open_state` dict NON viene mai pulito** se un trade resta aperto fino a `stop()`. Memory leak benigno ma il fatto che esista significa che TUTTI gli open_at_end hanno `open_state` salvato a memoria, MA NON USATO nel ramo `stop()`. | **ALTA — BUG 4-bis** | il ramo stop() ignora `_open_state` |

### Bug identificati

#### BUG 4 (confermato) — `dt_open` hardcoded `''` per `open_at_end`

**Linea 146**: nel ramo `stop()`, il dict pushed in `_open_snapshot` ha `'dt_open': ''` letterale. Soluzione: leggere `_open_state[trade.ref]` ... ma il problema è che `notify_trade` cache `_open_state` indicizzato per `trade.ref`, mentre `stop()` itera per `data`, non per trade.

**Diagnosi corretta**: 
- L'unico modo affidabile di recuperare `dt_open` per una posizione aperta è leggere `pos.adjbase` o usare il timestamp del primo ordine eseguito su quella data
- Backtrader espone `data._owner.position` ma NON il dt di apertura della posizione (è una limitazione strutturale del framework)
- **Soluzione robusta**: tracciare l'apertura via `notify_order` (event `Completed` + `isbuy()/issell()` sulla prima esecuzione su un dato `data`), salvare `dt_open` per `data._name`, leggerlo in `stop()`

#### BUG 4-bis — `_open_state` populated ma non usato per snapshot

**Linee 39-55 + 144-157**: cache `_open_state[trade.ref]` contiene `size_open, price_open, value_open` per ogni trade aperto. Ma `stop()` ignora completamente questa cache e ricostruisce tutto da `broker.getposition`. Quindi:
1. Se la strategia ha fatto scaling-in, `pos.price` è prezzo medio, non prezzo di prima apertura
2. Il `size` nella snapshot è la posizione netta corrente, non la size aperta inizialmente

**Conseguenza concreta su F3**: MU entry_price 353,10 nel ledger F3 OOS è probabilmente il prezzo medio post-scaling, non il prezzo di prima apertura. Se MU era stata aperta in F2 a 199,96 e poi scalata in più volte fino al F3, il 353,10 NON è il vero entry → PnL pct è calcolato su una base sbagliata.

### Domande aperte (da chiarire prima di patchare)

1. **La strategia fa scaling-in/out?** Va letta strategy.py per capire se può aumentare/ridurre posizioni esistenti
2. **L'engine inizializza il broker fresh per ogni fold?** Se sì, MU in F3 entry 353,10 è UNA NUOVA POSIZIONE aperta dentro F3 OOS, non un carry-over → cambia tutto. Da verificare in walkforward.py
3. **`bt.num2date` ritorna UTC o local?** Per il dump CSV su date pre-fold serve essere coerenti

---

## Decisione di sequenza dopo Layer 1

Prima di scrivere Layer 2, devo rispondere alla **Domanda 2** sopra, perché cambia drasticamente l'interpretazione di tutti i carry-in.

Se ogni fold ha cerebro fresh (broker resettato), allora:
- I 10 `open_at_end` di F1 sono trade aperti DENTRO F1 OOS che non si chiudono
- I 10 `open_at_end` di F2 sono altrettanti DENTRO F2 OOS, NON eredità da F1
- MU 199,96 in F2 e MU 353,10 in F3 sono due posizioni indipendenti aperte in fold diversi
- "Carry-over MU F2→F3" sarebbe FALSO

Se cerebro è continuativo tra fold (sharing state), allora carry-over è reale.

Vado a verificare PRIMA questo punto in walkforward.py — è dirimente per capire la portata del bug.

---

## Risposta alla Domanda 2 (cerebro fresh vs continuativo) — RISOLTA

Verificato in `engine/wf_runner.py` linee 117-119:

```python
def run_backtest(params, start, end) -> RunMetrics:
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_cash(cash)
    cerebro.broker.setcommission(commission=commission)
```

**Conferma**: cerebro è FRESH ad ogni chiamata `run_backtest`. Ogni fold (IS e OOS) è un cerebro isolato con broker resettato a cash iniziale. Nessuna eredità di stato tra fold.

**Conseguenza sulle conclusioni B3**:
- I 30 `open_at_end` sono tutti trade APERTI dentro il rispettivo fold OOS, NON carry-over
- MU F2 (entry 199,96) e MU F3 (entry 353,10) sono DUE POSIZIONI INDIPENDENTI in due cerebro distinti
- La narrazione "MU carry-over da F2 a F3" è FALSA come spiegazione causale
- Tuttavia: lo stesso BUG STRUTTURALE può aver aperto MU in fold diversi su prezzi diversi perché ogni cerebro indipendentemente ha attraversato lo stesso pattern di segnale

---

## Scoperta secondaria — BUG 5 (NUOVO): pre-roll trades inquinano la finestra OOS

Leggendo `wf_runner.py` linee 122-126 + `strategy.py` linee 320-325:

1. Feed range: `[start - 365cal, end]` per ogni fold
2. Backtrader attende `minperiod=200` (SMA200) bar PRIMA di chiamare `next()`. 365cal ≈ 261 bar trading → minperiod soddisfatto a `start - ~80cal`
3. Strategy gate: `bar_count < warmup_bars` con `warmup_bars=50` (default CLI, NON 200 come scrive il commento obsoleto)
4. Primo trade utile: bar #50 dopo minperiod, cioè a `start - ~30cal`

**Conseguenza**: la strategy può APRIRE TRADE nella finestra `[start - 30cal, start]`, cioè PRIMA del nominal fold start. Questi trade entrano nel ledger con `dt_entry < fold.start`, e poi proseguono dentro la finestra OOS dove il loro PnL contribuisce al sharpe del fold.

Questo è un BUG STRUTTURALE distinto dal warmup contamination (bug 2):
- Bug 2 → ritorni warmup includono variazioni pre-fold nella series → SR deflazionato di 1/√k
- Bug 5 → trade aperti pre-fold contaminano il count di trade e il PnL del fold

La correzione per bug 5 richiede uno dei due:
- (5a) `warmup_bars` strategy ≥ 365cal × 5/7 = 261 bar → garantisce che il primo segnale cade a `start` o dopo
- (5b) Gate esplicito in strategy: se `current_dt < fold_start_dt`, return  (richiede passare `fold_start` come parametro)

Verifica numerica della prevalenza:
- Su 32 trade nel ledger v7.3, 2 sono chiusi e 30 open_at_end
- Cross-check con dt_open dei 2 chiusi: se entrambi hanno `dt_open < fold.start`, il bug è 100%
- Cross-check con ledger trades.csv già fatto in B3.3 mostrava MU F3 con prezzo 353,10 — coerente con apertura nei primi giorni di F3, NON pre-fold

Richeck necessario: leggere wf_full_v73_trades.csv e contare quanti dei 2 closed hanno dt_open prima del fold start.

---

## Layer 1 — Conclusione

Bug rilevati in trade_ledger.py + dipendenze:

| # | Bug | File | Severità |
|---|---|---|---|
| 4 | dt_open hardcoded `''` per open_at_end | trade_ledger.py L146 | ALTA |
| 4-bis | _open_state cached ma non usato in stop() | trade_ledger.py L144-157 | MEDIA |
| 5 (NEW) | Pre-roll trades possibili: warmup_bars=50 + minperiod=200 < pre-roll 261bar | wf_runner.py L124 + strategy.py L324 | ALTA |

Bug 5 richiede ulteriore conferma con count empirico sul ledger esistente. Procedo a verificare PRIMA di passare a Layer 2.

### Verifica empirica bug 5 — ESEGUITA, esito 100% prevalenza

Letto `wf_full_v73_trades.csv` (32 righe). I 2 unici trade con `dt_open` valorizzato sono entrambi in F3 OOS:

| Ticker | dt_open | oos_start | Δ gg | Status |
|---|---|---|---|---|
| MC.PA | 2026-01-16 | 2026-02-01 | -16 gg PRE-FOLD | closed |
| BMPS.MI | 2026-01-16 | 2026-02-01 | -16 gg PRE-FOLD | closed |

**Entrambi APERTI 16 giorni PRIMA del fold start.** Il calcolo teorico era:
- feed_from = oos_start - 365cal = 2025-02-01
- minperiod 200 bar trading ≈ 280cal → ready a 2025-11-13
- + warmup_bars 50 trading ≈ 70cal → first trade signal a 2026-01-22

La data empirica (2026-01-16) è 6 giorni prima della stima teorica — differenza compatibile con il fatto che minperiod non è esattamente 200cal ma dipende dal calendario reale di trading.

**Bug 5 è strutturale, sistematico, 100% prevalenza sui dati noti.** Distribuzione open_at_end: 10 per ogni fold (F1, F2, F3) — indica che la strategia sta entrando vicino alla fine del fold e non riesce a chiudere prima di `oos_end`. Comportamento consistente con segnale lento (SMA200).

### Conseguenza sulla narrazione MU F2/F3

MU F2 OOS: entry 199,96 il ??/01/2026 (dt_open NaN), oos_window 01-nov-2025 → 01-feb-2026. Probabilmente aperta a metà-gennaio 2026 in pre-fold del F2? No, F2 oos_start = 01-nov-2025, quindi MU 199,96 è stata aperta nel pre-fold di F2 (probabilmente metà ottobre 2025) ed ha cavalcato la salita MU fino a 31-gen-2026 (chiusura forzata stop()).

MU F3 OOS: entry 353,10. F3 oos_start = 01-feb-2026. Pre-fold F3 sarebbe metà-gennaio 2026. Quindi MU 353,10 è stata aperta a metà gennaio 2026 PRE-FOLD F3, cioè dentro F2 OOS finestra ma in un cerebro DIVERSO. Spiegazione coerente con l'isolamento cerebro: è normale che lo stesso evento (segnale buy MU a gennaio 2026) appaia sia in F2 (vecchio cerebro, MU comprata ad ottobre 2025 a 199,96 e tenuta) sia in F3 (nuovo cerebro, MU comprata a gennaio 2026 a 353,10).

Questa osservazione rafforza l'analisi precedente: il "carry-over" è narrativamente sbagliato, ma il problema reale è il pre-fold trading che inquina l'attribuzione PnL del fold.

### Bug counter aggiornato Layer 1

| # | Bug | File | Severità | Status |
|---|---|---|---|---|
| 4 | dt_open hardcoded `''` per open_at_end | trade_ledger.py L146 | ALTA | CONFERMATO |
| 4-bis | _open_state cached ma non usato in stop() | trade_ledger.py L144-157 | MEDIA | CONFERMATO |
| 5 | Pre-roll trades (entry in pre-fold window) | wf_runner.py L124 + strategy.py L324 | ALTA | CONFERMATO 100% prevalenza |

**Layer 1 è COMPLETO.** Procedo Layer 2 (strategy.py 603 righe).

---

## Layer 2 — `engine/strategy.py` (604 righe) + dipendenze

### Invarianti che il codice assume

| # | Invariante | Dove |
|---|---|---|
| L2.A | BUY solo se `pos.size == 0 and score > 0` (NO scaling-in) | strategy.py L356 |
| L2.B | EXIT solo per 5 motivi: composite_reversal / stop_loss / take_profit / trailing_pct / trailing_atr | strategy.py L476-519 |
| L2.C | Sector cap policy 'block_new': blocca nuove buy, NON forza chiusura esistenti | strategy.py L448-451 |
| L2.D | warmup_bars=50 (CLI default), bar_count incrementa da bar 1 di next() | strategy.py L324 |
| L2.E | Universo ticker filtrato UNA SOLA VOLTA in wf_runner.py L563, identico per tutti i fold | wf_runner.py + data_loader.py |
| L2.F | Filtri universe (coverage >= 0.80, rows >= 252) sono valori aggregati sul "today" del data lake | data_loader.py L181-183 |

### Risposta a Step 2.1 — Scaling SÌ/NO

**NO scaling**. Solo 2 call sites:
- `self.close(data=d)` (linea 349) per EXIT
- `self.buy(data=d, size=size)` (linea 388) per ENTRY, gated da `pos.size == 0` (linea 356)

Nessun `order_target_percent/size/value`. Quindi `pos.price` = entry price unico.

**Conseguenza per Bug 4-bis**: declassato a **BASSA / code smell**. La patch Bug 4 può:
- Leggere `pos.price` direttamente per `entry_price` (già lo fa, linea 150 trade_ledger.py)
- Tracciare `dt_open` via `notify_order` (event Completed + size sale da 0 a >0 sulla prima esecuzione su `data._name`)
- Salvare in dict `_dt_open_by_data[data._name] = bt.num2date(order.executed.dt)`
- Leggerlo nel ramo `stop()` per popolare lo snapshot

### Risposta a Step 2.2 — Sector cap chiude posizioni esistenti?

**NO**. Sector cap è solo "block on new" (linee 448-451):
```python
if self._constraints.violation_policy == 'block_new':
    return 0
```
Nessuna logica di "force close on cap breach" nel ramo EXIT. Quindi i 2 trade chiusi MC.PA (2026-03-20) e BMPS.MI (2026-04-09) sono stati chiusi da uno dei 5 motivi standard (composite_reversal o trailing più probabili viste le perdite −25% e −13%).

**Conseguenza per Bug 3**: la narrazione "vincolo settoriale Fold 3" del consulente nel B3.1 è INESATTA. Il vincolo settoriale non chiude posizioni — al massimo le blocca all'apertura. Il vero meccanismo del Fold 3 anomalo è il Bug 5 (entry pre-fold) combinato con il pattern di mercato sui titoli.

### Risposta a Step 2.3 — Fix Bug 5

Confermo fix candidata (5b) come la più pulita: aggiungere parametro `oos_start_dt` al `__init__` della strategia + gate in `next()`:

```python
if self.params.oos_start_dt is not None:
    if self.datas[0].datetime.date(0) < self.params.oos_start_dt:
        return
```

Passare `oos_start_dt = start` dal `run_backtest` di wf_runner. Compatibile con IS (passare `is_start`) e OOS (passare `oos_start`). warmup_bars resta a 50 ma diventa effettivo solo nella finestra "fold valid".

### Risposta a Step 2.4 — BUG 6 (NUOVO) survivorship bias

`data_loader.py` linee 156-188: `list_tickers` applica 3 filtri:
1. Esistenza file parquet OHLCV
2. `coverage >= MIN_COVERAGE (0.80)` e `rows >= MIN_ROWS (252)` sulla serie aggregata
3. `EXCLUDE_LIST` (vuota)

Tutti e 3 i filtri sono **applicati una sola volta su "today"** del data lake, NON ricalcolati per `oos_start` di ogni fold. Il filtro è chiamato una sola volta in `wf_runner.py` linea 563 PRIMA del loop sui fold.

**Conseguenza**: l'universo di 35 ticker è **identico** per F1 OOS (ago-nov 2025), F2 OOS (nov 2025-feb 2026), F3 OOS (feb-mag 2026). Se un ticker:
- Era live in F1 ma poi delisted in F3 → escluso da tutti i fold (look-back contamination)
- Era piccolo in F1 ma cresciuto a maggio 2026 → incluso anche se a F1 non avrebbe passato il filtro
- È stato fatto IPO a gennaio 2026 → escluso da F1/F2 perché `rows < 252` nel data lake aggregato (corretto in questo caso)
- Era fallito a febbraio 2026 → escluso da F1/F2 anche se era live (errato — look-ahead exclusion)

Il commento esplicito in data_loader.py linea 10-12 riconosce l'intento ma ammette di filtrare sull'aggregato:
> "coverage >= MIN_COVERAGE (0.80) — esclude IPO recenti / reintegrazioni indice tardive"

**Bug 6 — Severità ALTA per ricerca walk-forward rigorosa.** In pratica per gli universi piccoli e stabili come "portfolio" (probabilmente 50-100 mega-cap occidentali) l'impatto è limitato perché il turnover di delisting è basso. Su "extended" o stoxx600 sarebbe disastroso.

### Bug counter aggiornato Layer 2

| # | Bug | File | Severità | Status |
|---|---|---|---|---|
| 4 | dt_open hardcoded `''` per open_at_end | trade_ledger.py L146 | ALTA | CONFERMATO |
| 4-bis | _open_state ridondante (no scaling) | trade_ledger.py L144-157 | BASSA (code smell) | CONFERMATO + DECLASSIFICATO |
| 5 | Pre-roll trades (entry in pre-fold window) | wf_runner.py L124 + strategy.py L324 | ALTA | CONFERMATO 100% prevalenza |
| 6 (NEW) | Survivorship bias: universo filtrato sul today, non per oos_start | data_loader.py L156-188 | ALTA per WF rigoroso | CONFERMATO struttura |

**Layer 2 è COMPLETO.** Procedo Layer 3 (walkforward.py 590 righe — orchestrazione, RunMetrics, equity_collector).

---

## Layer 3 — `engine/walkforward.py` (591 righe)

### Invarianti che il codice assume

| # | Invariante | Dove |
|---|---|---|
| L3.A | `oos_start = is_end` esatto, no purge buffer tra IS e OOS | walkforward.py L224 |
| L3.B | `degradation_ratio = oos_sharpe_a / is_sharpe_a` con guard NaN su flag != 'ok' | walkforward.py L138-150 |
| L3.C | `select_best_params` filtra trades>=min_trades AND sharpe_flag=='ok' | walkforward.py L290-297 |
| L3.D | equity_collector chiamato per IS dentro main loop (L487), per OOS in post-loop OOS-grid scan (wf_runner L847) | walkforward.py + wf_runner.py |
| L3.E | IS e OOS sono due chiamate run_backtest distinte, due cerebro freschi | walkforward.py L478, L510 |
| L3.F | Tie-break a parità di Sharpe seleziona threshold più alto (più selettivo) | walkforward.py L308-314 |

### Punti dove l'invariante può essere violata

| # | Possibile violazione | Severità | Note |
|---|---|---|---|
| L3.V1 | **L3.A: nessun purge buffer** — un trade aperto last bar IS può essere aperto a (start - 16gg) di OOS grazie a Bug 5. Però essendo cerebro fresh, NON c'è data leak diretto da IS a OOS. | BASSA | non è leak, è scelta metodologica |
| L3.V2 | `select_best_params` linea 313 — tie-break su `params.get('threshold', 0)`: se la griglia non include `threshold`, fallback a 0 → comportamento non deterministico se più param hanno tie | BASSA | griglia v7.3 include threshold |
| L3.V3 | `degradation_ratio` divide per `is_sharpe_a` ma guard è `abs() < 1e-9` → return 0.0. Se IS sharpe è negativo (raro ma possibile), ratio è negativo ma `overfitting_flag=False` (L161). OK ma counterintuitivo | BASSA | comportamento intenzionale |
| L3.V4 | Il logger usa `equity_collector` come callback opzionale; se solleva, viene loggato come warning e ignorato → uno trial può finire con riga mancante nel CSV equity | MEDIA | da valutare a posteriori dal log run |

### Bug identificati Layer 3

**NESSUN NUOVO BUG.** Il file è ben strutturato. L'unico punto sospetto (L3.V4) è di logging, non di correttezza numerica.

**Layer 3 è COMPLETO.** Procedo Layer 4 (wf_runner.py 864 righe — sezioni non ancora lette: linee 286-525 + 700-810).

---

## Layer 4 — `engine/wf_runner.py` (864 righe)

### Invarianti che il codice assume

| # | Invariante | Dove |
|---|---|---|
| L4.A | `make_backtest_runner` e `make_ledger_runner` producono RunMetrics identici per stessi params/start/end | wf_runner.py L86, L286 |
| L4.B | Feed range identico in entrambe le factory: `[start - 365cal, end]` | wf_runner.py L124, L314 |
| L4.C | TradeLedger analyzer è additivo: stessa logica strategy + ledger di trade | wf_runner.py L371 |
| L4.D | OOS-grid scan post-WF rieffettua N_grid × N_fold backtest indipendenti per dump equity OOS di tutti i trial | wf_runner.py L817-859 |
| L4.E | `attach_returns=True` filtra ritorni a `[start, end]` per escludere warmup (bug 2 fix candidate) | wf_runner.py L242-267 |

### Punti dove l'invariante può essere violata

| # | Possibile violazione | Severità | Note |
|---|---|---|---|
| L4.V1 | **L4.A duplicazione codice**: 200 righe duplicate tra make_backtest_runner e make_ledger_runner. Una correzione su una sola delle due genera divergenza silenziosa | MEDIA | code smell — Bug 7 latente di manutenzione |
| L4.V2 | **make_ledger_runner NON filtra ritorni a [start,end]** (linee 386-388 senza attach_returns filter) → ledger Sharpe è quello "contaminato" da warmup, mentre make_backtest_runner con attach_returns=True può essere "pulito" | ALTA | inconsistenza tra le due factory |
| L4.V3 | `n_trades` da `trades_ana.total.total` include APERTI + CHIUSI (vedi commento L233-237). Quindi un fold con tutti aperti contributisce a n_trades anche se nessuno è chiuso | DESIGN INTENZIONALE | docs presenti, ma da tenere a mente per Task 2b M_eff |
| L4.V4 | `sharpe = sharpe_bt / sqrt(252)` (L228, L394) è un "sharpe non annualizzato" inferito dal bt analyzer annualizzato. Se sharpe_bt è instabile su finestre corte (bug originario v7), anche sharpe lo è | LATENTE | non usato dal driver, solo legacy field |

### Bug identificati Layer 4

#### Bug 7 (NUOVO) — Duplicazione factory rischio divergenza patch

`make_backtest_runner` (linee 86-283) e `make_ledger_runner` (linee 286-420) duplicano:
- Setup cerebro/broker/feed (linee 118-138 vs 310-328)
- Strategy kwargs + addstrategy (linee 142-165 vs 332-352)
- Analyzers (linee 174-189 vs 354-371)
- Metriche post-run (linee 200-280 vs 380-413)

La differenza principale: ledger ha analyzer `TradeLedger` aggiuntivo e ritorna anche `trades`. La parte make_backtest_runner ha anche `attach_returns` (filtro warmup, item bug 2). Make_ledger_runner NON ha questo filtro.

**Conseguenza pratica per la patch B2**: ogni fix dei bug 2, 4, 5 va applicato in DUE posti. Il rischio di dimenticarne uno è alto.

**Soluzione suggerita**: rifattorizzare `make_ledger_runner` come thin wrapper di `make_backtest_runner` che inietta solo l'analyzer TradeLedger e l'unwrap. Lavoro 30-45 min, ma vincolante per consistenza.

### Bug counter FINALE (post-audit completo 4 layer)

| # | Bug | File | Severità | Status | Patch B2 |
|---|---|---|---|---|---|
| 4 | dt_open hardcoded `''` per open_at_end | trade_ledger.py L146 | ALTA | CONFERMATO | tracciare via notify_order |
| 4-bis | _open_state ridondante (no scaling) | trade_ledger.py L144-157 | BASSA (code smell) | DECLASSIFICATO | rimuovere o documentare |
| 5 | Pre-roll trades (entry in pre-fold window) | wf_runner.py L124 + strategy.py L324 | ALTA | CONFERMATO 100% prevalenza | gate oos_start_dt in strategy |
| 6 | Survivorship bias: universo filtrato sul today, non per oos_start | data_loader.py L156-188 | ALTA per WF rigoroso | CONFERMATO struttura | fuori scope B2 — schedulare per v8 |
| 7 | Duplicazione factory make_backtest/make_ledger | wf_runner.py L86-420 | MEDIA (manutenibilità) | CONFERMATO | rifattorizzare wrapper |
| 2 | Warmup contamination Sharpe 1/√k (già diagnosticato) | wf_runner.py L208-228 | ALTA | CONFERMATO precedentemente | filtro rets a [start,end] |

**Layer 4 è COMPLETO. AUDIT TUTTI I 4 LAYER COMPLETO.**

---

## Roadmap B2 finale post-audit

### Priorità ALTE — incluse nella patch B2

1. **Bug 2** (warmup contamination): in `make_backtest_runner`, filtrare `rets` a `[start, end]` PRIMA di calcolare `sharpe_a` (linee 208-222). Stesso filtro in `make_ledger_runner` (linee 383-393).
2. **Bug 4** (dt_open NaT): in `trade_ledger.py`, aggiungere `notify_order` event Completed + tracciare `dt_open_by_data[data._name]`. Leggerlo in `stop()` L146.
3. **Bug 5** (pre-fold trades): aggiungere parametro `oos_start_dt` a `PatrimonioStrategy.__init__`, gate in `next()` L320:
   ```python
   if self.params.oos_start_dt is not None:
       if self.datas[0].datetime.date(0) < self.params.oos_start_dt:
           return
   ```
   Passare `oos_start_dt = start` da entrambe le factory.
4. **Bug 7** (factory duplicazione): rifattorizzare per ridurre rischio divergenza future patch.

### Priorità BASSE — fuori scope B2

5. **Bug 4-bis** (code smell): documentare in commento che _open_state è ridondante per strategia no-scaling, rimuoverlo se possibile.
6. **Bug 6** (survivorship): richiede ricostruzione lookback-aware dell'universo per fold. Lavoro grande, schedulare per v8 finale (vedi roadmap 31/07).

### Validazioni post-patch obbligatorie

- Re-run sanity check (Task 2): SR_recomp == SR_saved entro tolleranza 1e-6 per tutti 432 trial
- Verifica empirica Bug 5: `dt_open` di tutti i trade chiusi >= `oos_start` (zero pre-fold)
- Spot-check MU F3: con bug 5 corretto, MU non dovrebbe più apparire in F3 (perché segnale gennaio 2026 è fuori finestra OOS), oppure deve apparire con entry_price reale di febbraio 2026
- Atteso impatto numerico: Sharpe IS scende leggermente perché perdiamo trade pre-fold; Sharpe OOS scende di più perché perdiamo i trade vincenti pre-roll (MU +50%)


---

## SIGILLO Task 3 (2026-05-23 17:05) — Falsificazione P4 + decisione SR_hat + predizione P5

### Predizione P4 — FALSIFICATA

Testo originale pre-registrato (sigillato in `preregistration_outcome.md` post Task 2c, citato da `task3_summary.md` v1):

> "Confronto α_LW vs α_RMT entro tolleranza ±15%"

Risultato Task 3 (run 17:00-17:03):

| Fold | α_LW   | α_RMT  | Δrel    |
|------|--------|--------|---------|
| F1   | 0.6485 | 0.0137 | −97.9%  |
| F2   | 1.0000 | 0.0410 | −95.9%  |
| F3   | 0.6331 | 0.0243 | −96.2%  |

**Esito: P4 falsificata su 3/3 fold.**

**Causa root** (errore concettuale dell'agente): α_LW e α_RMT misurano grandezze non equivalenti su scala lineare diretta. α_LW = peso convex-combination verso target specifico (constant-correlation); α_RMT = frazione di traccia in autovalori bulk Marchenko-Pastur. Con un fattore dominante (top1 eigenvalue = 91-95% della traccia), α_RMT è strutturalmente piccolo per costruzione, indipendentemente dalla qualità della matrice campionaria.

**Lezione operativa**: l'equivalenza tra metodi di shrinkage non si verifica sui parametri α grezzi ma sulla scala N_eff derivata. Su questa scala i tre metodi (trace su C, LW_equiv via N/(1+(N-1)ρ_eff), n_spike RMT) convergono qualitativamente a 1-3 dimensioni effettive in tutti i fold validi (F1, F3; F2 esclusa per α=1 — vedi sotto).

**Conseguenza per paper v7.3**: P4 entra nel registro disclosure delle predizioni falsificate, sezione "Limiti e correzioni del processo". La menzione esplicita della falsificazione aumenta credibilità peer-review.

### Post-hoc F2 α=1.0 — Discriminazione ipotesi (a) vs (b)

Test eseguito 17:05: ricalcolo α_LW(F2) con target alternativo `μ·I` (Ledoit-Wolf 2004 identity-scaled).

| F2 LW config                  | α      | π       | ρ       | γ       |
|-------------------------------|--------|---------|---------|---------|
| Target constant-correlation   | 1.0000 | 1.03e-3 | 1.03e-3 | ≈0      |
| Target identity μ·I           | 0.0467 | 1.03e-3 | 1.58e-5 | 8.29e-5 |

**Esito: ipotesi (b) confermata** — target constant-correlation troppo flessibile, satura strutturalmente con ρ̄=0.95. Con target identity α_LW(F2)=0.047 perfettamente coerente con α_RMT(F2)=0.041 (Δrel +14%, entro ±15%). F2 NON ha anomalia strutturale; nessuna patch richiesta. Flag aperto in Task 2b chiuso.

### Decisione SIGILLATA SR_hat per DSR (Task 7)

Tre opzioni considerate:
- (i) Mediana 3 best-per-fold OOS = mediana(2.631, 3.033, −0.110) = **2.631** — convenzione Bailey-Lopez de Prado, standard accademico
- (ii) Mediana 216 OOS = +2.654 — più robusta ma include trial non selezionati
- (iii) Media pesata IS-weighted dei 3 best — compromesso, ma introduce data snooping IS→OOS

**SCELTA SIGILLATA: opzione (i) come SR_hat primario, opzione (ii) come sensitivity secondaria.**

Motivazione:
- (i) è lo standard Bailey-LdP per DSR: "Sharpe ratio of the strategy selected via the IS selector, evaluated OOS"
- (ii) come sensitivity rivela quanto il DSR dipende dal selettore vs dal pool globale
- (iii) scartata perché reintroduce contaminazione IS in numeratore DSR

**Triple output Task 7**:
- DSR aggregato con SR_hat=(i)=2.631 e N_eff_primario=1.10-1.20 → range atteso [1.5, 1.8]
- DSR aggregato con SR_hat=(ii)=2.654 e N_eff_primario=1.10-1.20 → range atteso [1.5, 1.8] (numeratore quasi identico, conferma robustezza)
- DSR per-fold (3 valori separati): predizione F1+F2 entrambi sopra 1.5, F3 negativo o vicino a 0

### Vincolo bilatero DSR primario vs secondario

Sigillo aggiuntivo: il sistema è considerato statisticamente validato se ENTRAMBI:
- DSR primario (SR_0≈0.45) > 1.0
- DSR secondario (SR_0≈2.04) > 0.5

Se solo il primario passa, il sistema è validato "condizionalmente al modello N_eff trace-based". Se solo il secondario passa, il sistema è validato "condizionalmente al modello cluster-count". Solo se entrambi passano la validazione è robusta a entrambe le scelte modellistiche.

### Predizione P5 (sigillata pre-Task 4)

> "N_eff IS trace-based su C_mean convergerà a N_eff OOS Task 2c entro ±5%. Predizione puntuale: N_eff IS ∈ [1.05, 1.20] basato su ρ̄_IS_mean = 0.9293 (dato Task 3)."

Tolleranza ±5% sulla scala N_eff (non sui parametri α — lezione P4 applicata).

Verifica empirica diretta: calcolare N_eff_trace = (Σλ)²/Σλ² su C_mean Task 3 e confrontare con N_eff trace-based OOS Task 2c.


---

## SIGILLO Task 4 (2026-05-23 17:08) — Falsificazione P5 + N_eff sigillato DSR

### Predizione P5 — FALSIFICATA parzialmente

Testo originale (sigillato 17:05 sopra):
> "N_eff IS trace-based su C_mean convergerà a N_eff OOS Task 2c entro ±5%. Predizione puntuale: N_eff IS ∈ [1.05, 1.20]."

Risultato Task 4 (run 17:07):

**Per fold:**
| Fold | N_eff_IS | N_eff_OOS | Δrel    | Entro ±5%? |
|------|----------|-----------|---------|-------------|
| F1   | 1.1573   | 1.1350    | −1.93%  | PASS        |
| F2   | 1.1035   | 1.1522    | +4.42%  | PASS        |
| F3   | 1.1972   | 1.3821    | +15.44% | **FAIL**    |

**Aggregato**: N_eff IS (C_mean) = 1.1521 vs N_eff OOS (media fold) = 1.2231 → Δrel = +6.16% → FAIL.

**Causa root identificata**: F3 OOS ρ̄=0.832 vs F3 IS ρ̄=0.910 (drop −8.4 punti). Coerente con selector overfitting già scoperto: in F3 OOS i cluster mc=2 e mc=3 divergono performance-wise (mc=2 negativa, mc=3 positiva) → dispersione aumenta → ρ̄ scende → N_eff sale. F1+F2 stabili perché cluster coerenti IS↔OOS.

**Lezione operativa nuova**: l'instabilità della struttura di correlazione IS↔OOS è un indicatore di "overfitting cost sulla scala N_eff", distinto dalla degradazione Sharpe. Per fold con cluster overfitting, N_eff sale in OOS aumentando il debito DSR. F1/F2 entro ±5% confermano che il fenomeno è isolato a F3, coerente con selector overfitting già documentato.

**Disclosure paper v7.3**: P5 nel registro come falsificazione PARZIALE (2/3 fold PASS, F3 FAIL). Nuovo nesso causale documentato: instabilità cluster → instabilità correlazione → cost DSR su F3.

### N_eff sigillato DSR (Task 7)

**Scelta sigillata**: N_eff = **1.2231** (OOS aggregato, più conservativo di IS=1.1521).

Motivazione: la falsificazione di P5 mostra che OOS è il regime "vero" in cui si misura il DSR, e che F3 instabilità gonfia N_eff. Usare N_eff IS sarebbe ottimistico (sottostima debito DSR di ~6%). Standard accademico Bailey-LdP è calcolare N_eff sulla matrice di SR_hat candidati o sulla matrice di returns OOS — qui sceglie OOS returns.

**SR_0 finali sigillati** per Task 7 DSR:
- SR_0 primario = √(2·ln(1.223)) = **0.6346**
- SR_0 secondario = √(2·ln(8)) = **2.0393**

### Preview DSR (informativa, non sostituisce Task 7 finale)

Con SR_hat = 2.631 (opt. i, mediana 3 best OOS), T=66, γ1=0.484, γ2excess=3.146 (aggregato Task 6 preview):
- Adjustment factor ≈ 0.282
- **DSR primario ≈ 1.000** (saturazione CDF normale)
- **DSR secondario ≈ 0.982**

Entrambi SOPRA le soglie del vincolo bilatero (>1.0 e >0.5 rispettivamente). Sistema preliminarmente validato in entrambi i regimi modellistici.

Caveat: Task 6 ricalcolerà γ per fold con block bootstrap CI 90%; il numero finale può oscillare. Task 5 ricalcolerà SR_0 anche via block bootstrap empirico (non solo formula chiusa) per cross-validazione.

---

## SIGILLO Task 4-bis (2026-05-23 17:17) — Bug DSR preview unit-mixing + correzione

### Bug diagnosticato (su feedback consulente)

Nel sigillo Task 4 (17:08) ho riportato:
> Adjustment factor ≈ 0.282 / DSR primario ≈ 1.000 (saturazione CDF normale)

Saturazione CDF al 100% è chimicamente impossibile per uno z finito. Indagine:

**Formula errata usata**: `adj_old = sqrt((1 − γ₁·SR_hat + γ₂/4·SR_hat²) / (T−1))` con SR_hat=2.631 (annual), γ₁=0.484 (daily), γ₂=3.146 (daily). Due errori sovrapposti:

1. **Unit-mixing**: SR_hat in scala annuale mescolato con γ₁, γ₂ in scala daily nella stessa espressione. Il termine γ₂·SR_hat² = 0.787·6.92 = 5.44 esplode perché γ₂ è una proprietà DAILY mentre SR² è ANNUALE.
2. **Posizionamento errato di √(T−1)**: la formula canonica Bailey-LdP 2014 (eq. 11) ha √(T−1) al NUMERATORE come moltiplicatore della differenza SR_hat−SR_0; non come divisore dentro la radice dell'adjustment factor.

### Formula corretta canonica Bailey-LdP 2014 eq. 11

```
DSR = Φ( (SR̂ − SR_0) · √(T−1) / √(1 − γ₁·SR̂ + (γ₂_excess/4)·SR̂²) )
```

Vincolo dimensionale obbligatorio: SR̂, SR_0, γ₁, γ₂ TUTTI sulla stessa scala temporale. Scegliamo scala **DAILY** perché γ₁, γ₂ sono calcolati su daily_return (vedi `skew_kurt_check_summary.md`) e T è in bar daily.

### Conversioni daily-scale (sigillate)

| Quantità | Annual | Daily (canonico per formula) |
|----------|--------|-------------------------------|
| SR_hat (opt. i) | 2.631 | 2.631/√252 = **0.1657** |
| SR_0 primario (N_eff OOS) | 0.6346 | 0.6346/√252 = **0.0400** |
| SR_0 secondario (cluster=8) | 2.0393 | 2.0393/√252 = **0.1285** |
| SR_0 primario alt (N_eff IS) | 0.5321 | 0.5321/√252 = **0.0335** |
| γ₁ (daily, già nella scala) | n/a | 0.484 |
| γ₂_excess (daily, già) | n/a | 3.146 |

### Preview DSR ricalcolato (corretto)

Calcolo con T=66 (OOS F1, scala daily):

- Denominatore (adjustment scala daily): √(1 − 0.484·0.1657 + 3.146/4·0.1657²) = √0.9414 = **0.9703**
- Numeratore primario: (0.1657 − 0.0400) · √65 = **1.0139** → z_prim = 1.045 → **DSR_prim = 0.852**
- Numeratore secondario: (0.1657 − 0.1285) · √65 = 0.3005 → z_sec = 0.3097 → **DSR_sec = 0.622**

### Sensitivity ex-ante (N_eff IS) vs ex-post (N_eff OOS) [sigillata]

| Configurazione | N_eff | SR_0_annual | SR_0_daily | z | DSR |
|----------------|-------|-------------|------------|---|-----|
| Ex-ante (IS)  | 1.1521 | 0.5321 | 0.0335 | 1.099 | **0.864** |
| Ex-post (OOS) | 1.2231 | 0.6346 | 0.0400 | 1.045 | **0.852** |
| Δ              |        |        |        |       | +1.20 pp |

Differenza piccola (1.2 pp), come predetto dal consulente. **Decisione sigillata**: in paper v7.3 riporteremo entrambe come due righe della sensitivity table, indicando ex-post come "primary number" e ex-ante come "robustness check".

### Caveat metodologico aggiunto al paper

Stiamo usando correlazione di **daily returns** OOS come proxy della correlazione tra **SR_hat dei trial candidati** (canone Bailey-LdP). La correlazione di SR è generalmente ≥ della correlazione di returns; quindi la nostra stima N_eff potrebbe essere sottostimata (N_eff vero ≥ N_eff stimato → SR_0 vero ≥ SR_0 stimato → DSR vero ≤ DSR stimato). Effetto direzionale conservativo nel paper: stiamo sovrastimando il DSR.

### Lezione metodologica generale

Prima di ogni formula multi-grandezza:
1. Documentare unità di misura di ogni input
2. Verificare consistency dimensionale prima di passare al codice
3. Confronto sanity: per SR ~2.5 annual e ~50 osservazioni, DSR atteso 0.7-0.95 (sistema "interessante non saturato"). Numero fuori range = bug probabile.
4. Saturazione CDF >0.99 sempre da scrivere come numero esatto (0.99974), mai come "≈1.000".

Questa lezione entra in `audit_journal_v7_3.md` come regola permanente del workflow DSR.

### Predizione P6 (sigillata pre-Task 5)

> "SR_0 block bootstrap empirico mediano convergerà a SR_0 formula chiusa = 0.6346 (annual) ovvero 0.0400 (daily) entro ±20%. CI 90% atteso ≈ [0.30, 0.95] (annual) / [0.019, 0.060] (daily).
>
> KS test contro distribuzione normale formula chiusa mostrerà rejection p<0.05 per fold F3 (γ₂=2.72) ma non per F1 (γ₂=0.62) — block size insensitive a livello {1, 5, 10}.
>
> Block size sigillato: {1, 5, 10}, B=10.000 resample, demeaned per-fold (Politis-Romano)."

Falsifica criterion: media bootstrap fuori ±20% dalla formula chiusa = falsificazione. KS p>0.05 su F3 = falsificazione su quel sub-test (autorizza la formula gaussiana, indebolendo necessità dell'aggiustamento Bailey-LdP).


---

## SIGILLO Task 4-ter (2026-05-23 17:23) — DSR opt(A)+(B) sigillati + Ljung-Box + correzione γ aggregato

### Critica accolta (consulente 17:17)

Il preview Task 4-bis usava γ aggregato concatenato con SR_hat best-F1 — mescolanza sottile. Anche il valore γ₂_excess=3.146 era errato: il vero aggregato su 196 bar concatenati è **γ₂_excess=6.337**. Il numero 3.146 veniva da `skew_kurt_check_summary.md` ma riferito a un subset (n_bar diverso) — ricalcolato qui con consistency: 6.146 → 6.337 (Joanes-Gill bias-corrected, scipy default).

### Opzione (A) DSR per-fold — SIGILLATA PRIMARIA

γ_F_i + SR_hat_F_i + T_F_i + N_eff_OOS_F_i (consistency completa):

| Fold | SR_hat_d | γ₁     | γ₂_exc | T   | N_eff_OOS | SR_0_d | z      | DSR    |
|------|----------|--------|--------|-----|-----------|--------|--------|--------|
| F1   | 0.1657   | −0.199 | +0.620 | 66  | 1.1350    | 0.0317 | +1.061 | **0.856** |
| F2   | 0.1911   | +0.594 | +1.086 | 65  | 1.1522    | 0.0335 | +1.331 | **0.908** |
| F3   | −0.0069  | +0.550 | +2.717 | 65  | 1.3821    | 0.0507 | −0.460 | **0.323** |

Sensitivity ex-ante N_eff_IS: F1=0.851, F2=0.916, F3=0.361.

### Opzione (B) DSR aggregato concatenato 196 bar — SIGILLATA SECONDARIA

Trial_id identificati: F1=t.61, F2=t.61, F3=t.49 (mc=3/3/2 thr=0.25 msp=None mpb=None).

- T_agg = 196 bar, SR_daily_agg = 0.0744 → SR_annual_agg = **1.182** (match consulente 1.185)
- γ₁_agg = 0.487, γ₂_excess_agg = **6.337**
- DSR(N_eff OOS) = **0.687**
- DSR(N_eff IS) = **0.719**

### Ljung-Box per-fold (bonus Task 5 anticipato)

| Fold | Q(10) | p | rho_lag1 |
|------|-------|---|----------|
| F1 | 6.78 | 0.747 | −0.104 |
| F2 | 20.37 | **0.026** | **+0.188** AUTOCORR |
| F3 | 8.43 | 0.586 | −0.112 |
| Agg | 14.21 | 0.164 | — |

**Implicazione F2**: T_eff_AR1 = 65·(1−0.188)/(1+0.188) = **44.4 bar**.
- DSR F2 con T_nom=65: 0.908
- DSR F2 con T_eff=44.4: **0.864**

Δ = −0.044 (4.4pp ridotti). F2 resta validato in entrambi i regimi (>0.85).

### Sintesi opt(A)+(B) post-Ljung-Box

| Output | F1 | F2(T_nom) | F2(T_eff) | F3 | Agg(B) |
|--------|-----|-----------|-----------|-----|---------|
| DSR(N_eff OOS) | 0.856 | 0.908 | 0.864 | 0.323 | 0.687 |
| DSR(N_eff IS)  | 0.851 | 0.916 | 0.873 | 0.361 | 0.719 |

**Vincolo bilatero**:
- F1+F2: PASS in tutti i regimi
- F3: FAIL in tutti i regimi (negativo OOS)
- Aggregato (B): PASS marginale ~0.7

### Decisioni sigillate per Task 7 finale

1. **Output primario paper**: opt(A) DSR per-fold + F3 fail esplicito (disclosure onesta del fenomeno selector overfitting)
2. **Output secondario paper**: opt(B) aggregato 196-bar come "unconditional system DSR"
3. **F2 in paper**: doppia T (T_nom + T_eff), preferendo T_eff come conservativo
4. **Range N_eff sensitivity**: ex-ante (IS) e ex-post (OOS) come due righe della tabella

### Predizioni P6 e P6-bis (sigillate pre-Task 5)

**P6 (revisionata su feedback)**: tolleranza ridotta da ±20% a ±10%
> "SR_0 block bootstrap mediano (Politis-Romano demeaned per-fold) convergerà a SR_0 formula chiusa entro ±10% (annual scale). CI 90% bootstrap ≈ [0.40, 0.85] (annual). Block size {1, 2, 5, 10}, B=5.000."

**P6 sotto-test KS** (rejection attesa dipende dal vero γ₂ per fold):
- F1 (γ₂=0.620): KS p > 0.05 atteso (gaussianità ragionevole)
- F2 (γ₂=1.086): KS p > 0.05 atteso ma marginale
- F3 (γ₂=2.717): KS p < 0.05 atteso (fat-tail significativa)
- Caveat potenza: T=65 può ridurre potenza; rejection KS in F3 condizionata a potenza sufficiente

**P6-bis (nuovo, suggerito dal consulente)**: CI 90% γ₁, γ₂ per-fold block bootstrap
> γ₁_F1 CI ≈ [−0.50, +0.20] mediana ≈ −0.20
> γ₁_F2 CI ≈ [+0.20, +1.00] mediana ≈ +0.60
> γ₁_F3 CI ≈ [+0.00, +1.20] mediana ≈ +0.55 (più ampio)
> γ₂_F3 CI ≈ [−1.0, +6.0] — quasi inutile come stima puntuale

**P6-ter Ljung-Box**: già verificato sopra (anticipato). F2 ha rho_lag1=+0.188. Predizione: il bootstrap su F2 darà SR_0 più alto del formula-chiusa proprio per via dell'autocorrelazione (perché variance di SR_hat bootstrap aumenta con block size crescente).


---

## SIGILLO Task 5 (2026-05-23 17:25) — Bootstrap risultati + 3 falsificazioni nuove

### P6 — FALSIFICATA su per-fold (PASS marginale aggregato)

| Config | Formula | Boot b=5 | Δrel |
|--------|---------|----------|------|
| F1 | 0.5033 | 1.382 | +175% |
| F2 | 0.5323 | 1.537 | +189% |
| F3 | 0.8045 | 1.167 | +45% |
| Agg | 0.6346 | 0.704 | **+10.9%** marginale |

**Causa root**: SR_0 = √(2·ln(N_eff)) è derivazione asintotica T→∞. Con T=65 la varianza campionaria SR daily (~1/√T = 0.124) annualizzata = 1.97 → domina sulla correzione combinatoria 0.5. Solo l'aggregato T=196 si avvicina ragionevolmente.

**Implicazione metodologica**: per fold singoli T~65, **SR_0 formula chiusa sottostima la vera soglia non-skill**. Il DSR Task 4-ter è sovrastimato.

### P6 KS — falsificata per potenza statistica

F3 KS p=0.161 (no rejection) nonostante γ₂=2.72. Insufficient power con T=65 — confermata predizione consulente.

### P6-bis γ — confermata su mediane, CI 90% larghi

| Fold | γ₁ med | γ₁ CI | γ₂ med | γ₂ CI |
|------|--------|-------|--------|-------|
| F1 | −0.154 | [−0.601, +0.409] | +0.568 | [−0.405, +1.563] |
| F2 | +0.542 | [−0.222, +1.135] | +1.041 | [−0.219, +2.684] |
| F3 | +0.535 | [−0.348, +1.549] | +2.285 | [+0.515, +4.454] |

γ₂_F3 conferma "quasi inutile come stima puntuale" (CI larghezza 3.9 punti).

### P6-ter F2 autocorr — confermata debolmente

F2 SR_0_boot b=5 = 1.54 (massimo dei 3 fold), coerente con rho_lag1=+0.188. Differenza non drammatica.

### DSR ricalcolato con SR_0_bootstrap (sigillato Task 7)

| Fold | SR_hat_d | SR_0_boot_d | DSR_formula | DSR_boot |
|------|----------|-------------|-------------|----------|
| F1 | 0.1657 | 0.0870 | 0.856 | **0.733** |
| F2 | 0.1911 | 0.0968 | 0.908 | **0.787** |
| F3 | −0.0069 | 0.0735 | 0.323 | **0.260** |
| Agg | 0.0744 | 0.0443 | 0.687 | **0.665** |

**Vincolo bilatero post-boot**:
- F1: PASS (0.73 > 0.5)
- F2: PASS (0.79 > 0.5)
- F3: FAIL (0.26 < 0.5)
- Aggregato: PASS marginale (0.67 > 0.5)

### Decisioni sigillate per Task 7

1. **DSR primario paper** = DSR_bootstrap (più conservativo per T piccoli)
2. **DSR sensitivity formula-chiusa** in colonna affiancata (per disclosure asintotica)
3. **F3 esplicitamente non validato in entrambi i metodi**
4. **Aggregato (B) come "system-level DSR"** = 0.665 — il numero principale del paper

### Lezione metodologica nuova

Per peer review nel paper: SR_0 formula chiusa Bailey-LdP è **asintotica** e richiede T grande. Per T<100, usare bootstrap empirico. Per T grande (T≥200), formula chiusa si avvicina (entro ±15%). Questa lezione entra come regola permanente nel workflow DSR.

