# Quant Framework v3.0 — Patrimonio Missere

Framework quantitativo per backtesting, ottimizzazione e validazione walk-forward dell'algoritmo Segnali.

## Obiettivo

Trasformare il motore Segnali v2.0 (descrittivo) in un **framework quantitativo validabile statisticamente**:
- eliminare l'arbitrarietà dei pesi del composite score
- validare quali moduli generano realmente alpha
- ridurre overfitting e falsi segnali
- introdurre risk management reale
- preparare per future estensioni ML

## Struttura

```
quant_v3/
├── data/                          # Data lake versionato
│   ├── meta/                      # Universe definitions
│   │   ├── universe_extended.csv     # ~969 ticker (S&P500 + STOXX600)
│   │   ├── universe_portfolio.csv    # 35 ticker portfolio Missere
│   │   └── benchmarks.csv            # 16 indici e factor
│   ├── ohlcv/                     # 1 parquet/ticker (24m daily)
│   ├── benchmarks/                # OHLCV per ^GSPC, ^STOXX, ^VIX, etc.
│   ├── corporate/                 # Dividendi, splits, earnings
│   ├── _download_log.json         # Log download iniziale
│   ├── _refresh_log.json          # Log ultimo refresh incrementale
│   └── _validation_report.csv     # Report qualità dati
├── ingestion/
│   ├── build_universe.py          # Costruisce CSV universe da Wikipedia
│   ├── initial_download.py        # DA ESEGUIRE IN LOCALE: download iniziale 24m
│   ├── refresh_lake.py            # Refresh incrementale (per cron Actions)
│   ├── validation.py              # Quality checks sul lake
│   └── requirements.txt
├── engine/                        # [F2 ✓] Strategy Backtrader
│   ├── data_loader.py             # Parquet → PandasData feeds
│   ├── custom_data.py             # PatrimonioFeed (earnings/dividend lines)
│   ├── signals.py                 # CompositeSignal Hybrid A+C
│   ├── strategy.py                # PatrimonioStrategy (long-only, ranking-based)
│   ├── runner.py                  # CLI backtest + analyzers QuantStats
│   ├── sizing.py                  # ✓ F3.1 PositionSizer vol-target/Kelly
│   ├── regime.py                  # ✓ F3.2 RegimeDetector VIX
│   ├── constraints.py             # ✓ F3.3 PortfolioConstraints (sector + beta cap)
│   ├── fetch_metadata.py          # ✓ F3.3 yfinance fetch sector+beta
│   └── modules/                   # 6 alpha modules
│       ├── trend.py               # SMA cross + ADX + slope
│       ├── momentum.py            # RSI + MACD/ATR + ROC
│       ├── mean_reversion.py      # Z-score + Bollinger + ADX filter
│       ├── value.py               # P/E + P/B + FCF yield
│       ├── quality.py             # ROE + margin + D/E
│       └── event_driven.py        # PEAD post-earnings drift
├── tests/                          # pytest suite (163 test, < 5s)
│   ├── test_sizing.py             # ✅ Fase 3.1 (vol_target + edge cases)
│   ├── test_regime.py             # ✅ Fase 3.2 (regime VIX + deleveraging + trailing)
│   └── test_constraints.py        # ✅ Fase 3.3 (sector cap + beta cap)
├── data/meta/sector_beta.parquet  # ✓ Fase 3.3 — ticker→(sector, beta) cache
├── optimization/                  # [F4] Walk-forward + optstrategy (TODO)
└── reports/                       # Report PDF di backtest
```

## Setup iniziale (UNA TANTUM)

### Fase 1 — Costruzione data lake (questa fase)

```bash
# 1. Clone branch v3
git clone -b v3-quant-framework https://github.com/luigimissere-svg/yahoo-proxy-missere.git
cd yahoo-proxy-missere/quant_v3

# 2. Setup ambiente Python
pip install -r ingestion/requirements.txt

# 3. (Già fatto) Universe definitivo
python ingestion/build_universe.py
# → data/meta/universe_extended.csv, universe_portfolio.csv, benchmarks.csv

# 4. Download iniziale (DA LANCIARE SUL TUO PC con IP domestico)
python ingestion/initial_download.py
# → ~30-45 min, ~50 MB di parquet

# 5. Validazione qualità
python ingestion/validation.py
# → data/_validation_report.csv

# 6. Commit + push
git add data/
git commit -m "data: initial lake snapshot 2026-05-22"
git push origin v3-quant-framework
```

### Modalità rapide (per test)

```bash
# Solo il tuo portfolio (35 ticker, ~2 min)
python ingestion/initial_download.py --portfolio-only

# Solo benchmarks (16 ticker, ~1 min)
python ingestion/initial_download.py --benchmarks-only

# Limit 50 ticker per test
python ingestion/initial_download.py --limit 50

# Resume da interruzione
python ingestion/initial_download.py --resume
```

## Manutenzione automatica

Workflow `.github/workflows/data-lake-refresh.yml`:
- Cron domenica 23:00 UTC → refresh ai dati più recenti
- Trigger manuale: `gh workflow run data-lake-refresh.yml`

## Governance dati

| Aspetto | Decisione |
|---|---|
| **Snapshot date** | 2026-05-22 (fissato per riproducibilità) |
| **Range storico** | 24 mesi (2024-05 → 2026-05) |
| **Frequenza** | Daily OHLCV |
| **Aggiustamenti** | Raw + colonna `adj_close` (auto_adjust=False) |
| **Survivorship** | Universe estratto al snapshot date — **bias presente**, accettato per ora |
| **Formato** | Parquet snappy, 1 file per ticker |
| **Versioning** | Git commit + tag `v3-datalake-YYYY-MM-DD` |
| **Source primario** | Yahoo Finance via yfinance |
| **Source secondario** | Stooq (fallback automatico per ticker bloccati) |

## Universe stats

| Set | N. ticker | Mercato |
|---|---|---|
| `universe_extended` | 969 | S&P500 (503) + STOXX600 (~534, dedup con SP500) |
| `universe_portfolio` | 35 | Holdings + watchlist + discovery Missere |
| `benchmarks` | 16 | Equity indices + VIX/VSTOXX + rates + commodities + FX |
| **TOTALE univoci** | **~1008** | Mix US/EU |

## Fase 2 — Engine Backtrader (✓ completata)

### Architettura

```
        feeds (parquet)              
             ↓                       
     DataLakeLoader → PandasData     
             ↓                       
     PatrimonioStrategy              
        ├─ 6 alpha modules → score ∈ [-1, +1]
        ├─ CompositeSignal Hybrid A+C  
        │    ├─ weighted average            (A)
        │    └─ gating: |composite| > thr  
        │        + ≥ N moduli concordi    (C)
        ├─ Ranking BUY (top-N candidati per score)
        ├─ Risk: stop_loss / take_profit / trailing
        └─ Logging: trade log CSV
             ↓                       
     Analyzers Backtrader            
        ├─ Sharpe/Sortino/Calmar/SQN  
        ├─ Profit factor + expectancy 
        ├─ Annual returns breakdown   
        └─ Equity curve + QuantStats HTML
```

### Composite Signal — Hybrid A+C

Trade emesso solo se:
- `|composite| ≥ threshold` (default 0.20)
- `≥ min_concordant` moduli hanno stesso segno del composite (default 3)

**Pesi default — Strategia B (pre-screening)** (`engine/signals.py::DEFAULT_WEIGHTS`):

| Modulo | Peso | Cosa misura |
|---|---|---|
| trend | 0.30 | SMA50/200 cross + ADX + slope |
| momentum | 0.30 | RSI(14) + MACD/ATR + ROC(21) |
| mean_reversion | 0.20 | Z-score(20) + Bollinger + ADX filter |
| value | **0.00** | P/E + P/B + FCF yield — *pre-screening only* |
| quality | **0.00** | ROE + profit margin + D/E — *pre-screening only* |
| event_driven | 0.20 | PEAD post-earnings drift |

### Strategia B: fundamentals come pre-screening

Value e Quality NON contribuiscono al composite (weight=0). Vengono invece usati
come filtro pre-screening sui candidati BUY: il ticker è **scartato solo se ENTRAMBI**
`value_score < value_floor` E `quality_score < quality_floor` (default `-0.5`).

**Logica permissiva**: score 0 o NaN (fundamentals mancanti) = benefit of doubt, NON scarta.

**Motivazione** (validata su backtest 2024-08 → 2026-05, portfolio Missere):

| Configurazione | P&L | Sharpe annual | Max DD |
|---|---|---|---|
| value/quality nel composite | -1.32% | -0.054 | 8.32% |
| value/quality esclusi (no filter) | +12.29% | +1.170 | 4.06% |
| **Strategia B: pre-screening** | **+14.83%** | **+1.355** | **4.52%** |

Lo snapshot statico dei fundamentals creava un bias value-tilt EU (banche/utilities)
che escludeva mega-cap tech US ad alta crescita. Il pre-screening preserva la funzione
risk-management ("no junk") senza penalizzare growth stock di qualità.

### Fase 3.1 — Position Sizing Vol-Targeted

Il sizing equal-weight (`per_ticker_cap` fisso) carica lo stesso notional su titoli
tranquilli e volatili. Il vol-targeting alloca più capitale su asset stabili e meno
su asset volatili, mantenendo un rischio target uniforme per posizione.

**Formula** (`engine/sizing.py::PositionSizer`):

```
target_risk_eur  = target_risk_pct  × NAV       (es. 1% × 100k = 1000)
vol_proxy_eur    = ATR(14) o std(returns_21d) × close
vol_shares       = target_risk_eur / vol_proxy_eur
final_shares     = min(vol_shares, cap_shares, cash_shares)
skip if          notional < min_position_pct × NAV
```

**Caps di sicurezza**:
- `per_ticker_cap` (default 10% NAV) — hard upper cap, evita concentrazione
- `min_position_pct` (default 0.5% NAV) — sotto, salta trade (no micro-positions)
- `vol_floor_pct` (default 0.5% prezzo) — vol minima, evita leverage esplosivo

**Esempi BUY su portfolio (vol_target attivo)**:

| Ticker | Prezzo | ATR(14) EUR | Shares | Notional |
|---|---|---|---|---|
| NVDA | 184.89 | 6.22 | 55 | 10.169 |
| LLY | 868.27 | 27.76 | 12 | 10.419 |
| BMPS.MI | 8.78 | 0.26 | 1138 | 9.995 |
| EDP.LS | 4.28 | 0.11 | 2312 | 9.888 |
| MU | 426.13 | 24.98 | 23 | 9.801 |

Il cap del 10% NAV è binding nella maggior parte dei casi col target_risk=1% di default,
rendendo vol_target equivalente a equal in portfolio piccoli. **In Fase 4 (walk-forward)**
ottimizzeremo `target_risk × cap` insieme. Per testare il vol-target puro:
```bash
python -m engine.runner --target-risk 0.005 --per-ticker-cap 0.20
```

### Fase 3.2 — Exit Dinamica Regime-Aware

Usa il livello del **VIX** come proxy del regime di mercato per (a) ridurre la size
dei nuovi BUY in regimi alti (deleveraging) e (b) stringere il trailing stop ATR
in volatilità elevata (full mode).

**Regimi VIX** (default, `engine/regime.py`):

| Regime | VIX | Size factor | Trailing ATR mult |
|---|---|---|---|
| LOW | < 15 | 1.0 | 2.5× |
| NORMAL | 15–20 | 1.0 | 2.5× |
| ELEVATED | 20–25 | 0.7 | 2.0× |
| HIGH | 25–35 | 0.4 | 1.5× |
| EXTREME | ≥ 35 | 0.0 (no BUY) | 1.0× |

**Modalità CLI** (`--regime-mode`):
- `off` (default, retrocompatibile): nessun deleveraging, nessun trailing ATR.
- `deleveraging`: applica solo la riduzione di size sui NEW BUY. **Non tocca** le
  posizioni esistenti.
- `full`: deleveraging + trailing stop ATR-based, con `mult` regime-aware. È più
  conservativo ma sensibile alla calibrazione del mult per regime (Fase 4).

**Backtest 2024-08 → 2026-05 (portfolio Missere, 35 ticker)**:

| Mode | P&L | Sharpe | Max DD | Trades | Note |
|---|---|---|---|---|---|
| off (baseline) | +14.83% | 1.355 | 4.52% | 10 | composite exit |
| deleveraging | +12.48% | 1.283 | **3.56%** | 10 | -16% P&L, **DD -21%** |
| full | +1.55% | 0.329 | 3.79% | 14 | trailing ATR 1.5× troppo stretto, 9 stop-outs |

**Lettura**: il `deleveraging` realizza il classico trade-off return-per-risk
(meno return, meno drawdown). Il `full` mode richiede calibrazione dei mult ATR
per evitare "noise stops": il tuning verrà fatto out-of-sample in Fase 4.

**Override pythonico** (per walk-forward o custom backtest):
```python
from engine.strategy import PatrimonioStrategy
cerebro.addstrategy(
    PatrimonioStrategy,
    regime_mode='deleveraging',
    vix_feed_name='^VIX',
    regime_thresholds={'LOW': 12.0, 'NORMAL': 18.0, 'ELEVATED': 23.0, 'HIGH': 30.0, 'EXTREME': float('inf')},
    deleveraging_factors={'LOW': 1.0, 'NORMAL': 1.0, 'ELEVATED': 0.5, 'HIGH': 0.25, 'EXTREME': 0.0},
)
```

Il `RegimeDetector` è **stateless** (una sola `detect(vix)` per bar) e iniettabile
via parametri, quindi pronto per ottimizzazione walk-forward di soglie e fattori.

### Fase 3.3 — Portfolio Constraints (sector cap + beta cap)

Vincoli pre-trade applicati ai candidati BUY per evitare concentrazioni eccessive
di settore o esposizioni di mercato (beta) elevate. Step finale di Fase 3 (Risk
Management), pronto per la validazione walk-forward in Fase 4.

**Vincoli**:
- `sector cap`: max X% NAV per settore GICS (default **30%**).
- `beta cap`: max Σ(weight_i × beta_i) sull'intero portfolio (default **1.3**).

**Distribuzione settori portfolio (35 ticker)** — cached in `data/meta/sector_beta.parquet`:

| Settore | Ticker | Esempi notevoli |
|---|---|---|
| Consumer Cyclical | 7 | AMZN, BKNG, MELI, ITX.MC, MC.PA, RACE.MI, SE |
| Healthcare | 5 | LLY (β=0.48), BSX, GMAB.CO, NOVO-B.CO (β=0.35), ZTS |
| Utilities | 5 | EDP.LS, ENEL.MI, IBE.MC, PPC.AT, TRN.MI |
| Financial Services | 5 | BBVA.MC, BMPS.MI, BNP.PA, ETE.AT, EUROB.AT |
| Technology | 4 | ADBE, MSFT, MU (β=1.92), NVDA (β=2.24) |
| Industrials | 4 | AENA.MC, FER.MC, LHA.DE, PRY.MI |
| Consumer Defensive | 2 | JMT.LS, WMT |
| Communication Services | 1 | META (β=1.24) |
| Energy | 1 | REP.MC (β=−0.13) |
| Real Estate | 1 | AMT |

Beta range: **−0.13 → 2.24**, mean ≈ 0.91. Coverage: 35/35.

**Policy di violazione** (`--violation-policy`):
- `block_new` (default): se il candidato porterebbe a violare un cap, **skippa**
  il BUY e prova il candidato successivo nel ranking.
- `scale_down`: riduce le shares in modo da rispettare i cap residui (rispetta
  `min_position_pct` floor; se il floor non sta nei cap → skip).

**Unknown handling**: ticker non in `sector_map` finiscono in pool `'Unknown'`
(default `unknown_pool=True`, applica il sector cap anche al pool). Ticker senza
beta → β=1.0 (neutro).

**Backtest 2024-08 → 2026-05 (portfolio Missere, 35 ticker)**:

| Config | P&L | Sharpe | Max DD | Trades | Note |
|---|---|---|---|---|---|
| baseline (no constraints) | +14.83% | 1.355 | 4.52% | 10 | Fase 3.2 ref |
| sector≤30% | +14.83% | 1.355 | 4.52% | 10 | non binding |
| sector≤30% + β≤1.3 | +14.83% | 1.355 | 4.52% | 10 | non binding |
| sector≤15% scale_down | +10.72% | 1.274 | **3.23%** | 9 | DD −29%, P&L −28% |
| sector≤5% (stress) | 0.00% | — | 0.00% | 0 | 47 BUY bloccati, sanity check |

**Lettura**: sui 10 trade del portfolio Missere il sector cap a 30% non è
binding (la strategy con `per_ticker_cap=10%` + `max_positions=10` non concentra
naturalmente più del 20-25% per settore). Il valore del framework si vede al
restringersi del cap o nello stress test: i log diagnostici `SKIP <ticker>
constraint=...` documentano ogni violazione, e il counter finale
`blocked_by_sector / blocked_by_beta / scaled` quantifica l'intervento. È
esattamente lo strumento che serve per la walk-forward Fase 4: previene scenari
estremi (es. NVDA+MU+MSFT insieme con beta totale 1.8+) quando l'ottimizzatore
tenterà combinazioni aggressive di parametri.

**Fetch metadata** (yfinance una tantum):
```bash
python -m engine.fetch_metadata --universe portfolio        # 35 ticker, ~1 min
python -m engine.fetch_metadata --universe extended         # 970 ticker, ~25 min
python -m engine.fetch_metadata --resume                    # skip già fatti
```
Output: `data/meta/sector_beta.parquet` (colonne: ticker, sector, beta, industry).

**Esempi CLI**:
```bash
# sector cap 30%, beta cap 1.3 (default)
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --max-sector-pct 0.30 --max-beta 1.3 \
    --metadata-path data/meta/sector_beta.parquet

# solo sector cap, policy scale_down
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --max-sector-pct 0.25 --violation-policy scale_down \
    --metadata-path data/meta/sector_beta.parquet --verbose
```

**Override pythonico**:
```python
from engine.constraints import make_default_constraints
from engine.strategy import PatrimonioStrategy

constraints = make_default_constraints(
    metadata_path='data/meta/sector_beta.parquet',
    max_sector_pct=0.30,
    max_portfolio_beta=1.3,
    violation_policy='block_new',
)
cerebro.addstrategy(PatrimonioStrategy, portfolio_constraints=constraints)
```

`PortfolioConstraints` è **stateless** (no side effects su `would_violate`) e
iniettabile, quindi compatibile con ottimizzazione walk-forward.

### Setup engine

```bash
cd quant_v3
pip install -r engine/requirements.txt
```

### Fundamentals snapshot (per moduli value/quality)

```bash
# Da lanciare in locale (yfinance bloccato da IP cloud)
python ingestion/fetch_fundamentals.py --portfolio-only        # 35 ticker, ~3 min
python ingestion/fetch_fundamentals.py --extended              # 970 ticker, ~30 min
python ingestion/fetch_fundamentals.py --resume                # skip gìà fatti
```

Output: `data/fundamentals/{TICKER}.parquet`

Senza fundamentals, value/quality ritornano 0.0 (neutri) e il pre-screening fa
benefit of doubt: nessun candidato viene scartato. Con i fundamentals, il filtro
elimina junk stock con value E quality estremi (negativi).

### Esempi run

**Backtest base (default config)**:
```bash
python -m engine.runner --universe portfolio --from 2024-08-01
```

**Backtest completo con report HTML**:
```bash
python -m engine.runner \
    --universe portfolio --from 2024-08-01 --to 2026-05-21 \
    --cash 100000 --commission 0.001 \
    --threshold 0.20 --min-concordant 3 \
    --max-positions 10 --per-ticker-cap 0.10 \
    --stop-loss 0.07 --take-profit 0.20 --trailing 0.08 \
    --log-trades trades.csv \
    --equity-csv equity.csv \
    --quantstats-html report.html \
    --verbose
```

**Smoke test (loose gating, debug)**:
```bash
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --threshold 0.05 --min-concordant 1 --verbose
```

**Backtest con regime VIX deleveraging (Fase 3.2)**:
```bash
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --regime-mode deleveraging --verbose
```

**Backtest full regime-aware (deleveraging + trailing ATR adattivo)**:
```bash
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --regime-mode full --verbose
```

**Backtest con portfolio constraints (Fase 3.3)**:
```bash
python -m engine.runner --universe portfolio --from 2024-08-01 \
    --max-sector-pct 0.30 --max-beta 1.3 \
    --metadata-path data/meta/sector_beta.parquet --verbose
```

### Parametri runner CLI

| Flag | Default | Descrizione |
|---|---|---|
| `--universe` | `portfolio` | `portfolio` (35) o `extended` (970) |
| `--max-tickers` | None | Limita N ticker (testing) |
| `--from` | `2024-08-01` | Inizio backtest YYYY-MM-DD |
| `--to` | None | Fine backtest (default: ultimo bar) |
| `--cash` | `100000` | Capitale iniziale |
| `--commission` | `0.001` | Commissione (10 bps) |
| `--threshold` | `0.20` | Soglia composite per gating |
| `--min-concordant` | `3` | Moduli minimi concordi |
| `--max-positions` | `10` | Posizioni massime simultanee |
| `--per-ticker-cap` | `0.10` | Max % cash per ticker |
| `--stop-loss` | None | Stop loss % dall'entry |
| `--take-profit` | None | Take profit % dall'entry |
| `--trailing` | None | Trailing stop % dal massimo |
| `--warmup-bars` | `200` | Bar di warmup pre-segnali |
| `--log-trades` | None | CSV trade log |
| `--equity-csv` | None | CSV equity curve giornaliera |
| `--quantstats-html` | None | Report HTML completo |
| `--verbose` | False | Log BUY/EXIT bar-by-bar |
| `--no-quality-filter` | (enabled) | Disabilita pre-screening fundamentals |
| `--value-floor` | `-0.5` | Soglia minima value_score |
| `--quality-floor` | `-0.5` | Soglia minima quality_score |
| `--sizing` | `vol_target` | Metodo sizing: `equal` (legacy) o `vol_target` |
| `--target-risk` | `0.01` | Rischio target per trade (% NAV) |
| `--min-position` | `0.005` | Notional minimo (% NAV); sotto, skip trade |
| `--vol-floor` | `0.005` | Vol floor (% prezzo) per evitare sizing esplosivo |
| `--vol-proxy` | `atr` | `atr` o `realized` (std returns) |
| `--vol-lookback` | `14` | Periodo ATR/realized vol |
| `--regime-mode` | `off` | `off`/`deleveraging`/`full` (VIX-based exit) |
| `--vix-ticker` | `^VIX` | Simbolo VIX nel data lake (vuoto = nessuno) |

### Output runner

```
BACKTEST RESULT
Final value:        114,827.03
P&L:                +14,827.03  (+14.83%)
Sharpe (annual):    1.355
Max drawdown:       4.52%  (length=15 bars)
Calmar ratio:       2.12
SQN:                2.34   (>1.6 decente, >2 buono, >3 ottimo)
Trades:             10 (won=4 lost=2 win rate=66.7%)
Profit factor:      2.15  (>1 profittevole, >2 robusto)
Expectancy/trade:   +152.30 EUR
Avg holding bars:   won=42.3  lost=18.5

Annual returns:
  2024:   +0.00%
  2025:   +0.00%
  2026:  +12.29%
```

### Tests

```bash
cd quant_v3
python -m pytest tests/ -v
```

163 test, < 5s. Coverage:
- `test_data_loader.py` (11) — lake structure + feed building
- `test_signals.py` (17) — composite blending + gating + Strategia B (pesi 0, pre-screening)
- `test_modules.py` (16) — 6 moduli alpha + bounds + monotonia
- `test_strategy_smoke.py` (3) — e2e cerebro run + quality_filter unit
- `test_sizing.py` (21) — PositionSizer equal vs vol_target, caps, edge cases
- `test_regime.py` (39) — RegimeDetector VIX (classify, deleveraging, trailing, mode bypass)
- `test_constraints.py` (56) — PortfolioConstraints (sector cap, beta cap, would_violate, scale_down, edge cases)

### Troubleshooting

| Problema | Soluzione |
|---|---|
| `ValueError: badly formed help string` | Python 3.14 — git pull, controlla che runner.py non abbia `%` non escapati nelle help argparse |
| `invalid path 'CON.DE.parquet'` su `git clone` Windows | Reserved name; risolto in commit `89b4b0c` (rimosso) |
| `git checkout -f` con file non-tracked | `git reset --hard origin/v3-quant-framework` |
| Tutte BUY al primo bar e zero EXIT | Fundamentals statici dominano: usa Strategia B (default) oppure `--no-quality-filter` |
| Quality filter scarta troppi tickers | Abbassa `--value-floor` e `--quality-floor` (es. -0.7) o disabilita con `--no-quality-filter` |
| `unsupported format character '('` | Help argparse contiene `%` non valido — fixed |
| yfinance 429 / blocked | Lancia da casa (no Vercel/Actions IP); `--sleep 1.0` aumenta delay |

## Fase 4 — Walk-Forward + parameter stability (✓ completata)

Framework di validazione out-of-sample con rolling window. **Non cerca il
parametro 'migliore in assoluto'**: misura se il sistema è stabile OOS e se i
parametri ottimali ricorrono coerentemente nei fold.

### Schema rolling window

Dataset disponibile: 2024-08-01 → 2026-05-22 (~22 mesi reali).

- **IS = 12 mesi** (training/optimization)
- **OOS = 3 mesi** (validazione)
- **Step = 3 mesi** (rolling forward)
- **Fold reali generati = 3** (l'ultimo richiederebbe OOS oltre 2026-05)

| Fold | IS                          | OOS                         |
| ---- | --------------------------- | --------------------------- |
| F1   | 2024-08-01 → 2025-08-01     | 2025-08-01 → 2025-11-01     |
| F2   | 2024-11-01 → 2025-11-01     | 2025-11-01 → 2026-02-01     |
| F3   | 2025-02-01 → 2026-02-01     | 2026-02-01 → 2026-05-01     |

### Griglia parametri (72 combinazioni)

| Parametro             | Valori                |
| --------------------- | --------------------- |
| `threshold`           | 0.10, 0.15, 0.25      |
| `min_concordant`      | 2, 3                  |
| `target_risk_pct`     | 0.005, 0.008, 0.012   |
| `max_sector_pct`      | None, 0.3             |
| `max_portfolio_beta`  | None, 1.3             |

Totale = 3 × 2 × 3 × 2 × 2 = 72 combo × 3 fold = 216 backtest IS + 3 OOS.

### Selezione & stabilità

- **Metrica obiettivo IS**: Sharpe annualizzato semplice.
- **Tie-break**: a parità di Sharpe (entro 5%), preferisco la `threshold` più
  alta (parametro più conservativo).
- **Min trades per fold**: 5 (sotto, lo skippo per evitare risultati spuri).
- **Overfitting flag**: OOS_Sharpe < 0.3 × IS_Sharpe (solo se IS > 0).
- **Parametro 'stabile'**: stesso valore vincente in ≥3/3 fold.

### Risultati Full Run (72 combo)

| Fold | IS Sharpe | OOS Sharpe | Degradation | OOS Trades | OOS DD | Flag    |
| ---- | --------- | ---------- | ----------- | ---------- | ------ | ------- |
| F1   | 2.576     | 0.000      | 0.00        | 4          | 0.86%  | ⚠ OVF  |
| F2   | 1.000     | 1.599      | 1.60        | 2          | 1.00%  | ok      |
| F3   | 1.304     | 1.000      | 0.77        | 10         | 1.76%  | ok      |

**Aggregate stability**:
- IS Sharpe medio: **1.627**
- OOS Sharpe medio: **0.866**
- Degradation ratio medio: **0.79** (> 0.7 = molto stabile)
- Overfitting count: **1/3 fold**

**Parametri stabili** (3/3 fold):
- `threshold = 0.25`
- `target_risk_pct = 0.008`
- `max_sector_pct = None`
- `max_portfolio_beta = None`
- `min_concordant`: 3 in 2/3 fold (quasi stabile)

### Esempi CLI

```bash
# Smoke run (8 combo, ~2 min)
python -m engine.wf_runner --universe portfolio \
    --from 2024-08-01 --to 2026-05-22 \
    --grid smoke \
    --output-csv wf_smoke_results.csv \
    --stability-json wf_smoke_stability.json

# Full run (72 combo, ~20 min)
python -m engine.wf_runner --universe portfolio \
    --from 2024-08-01 --to 2026-05-22 \
    --grid full \
    --output-csv wf_full_results.csv \
    --stability-json wf_full_stability.json

# Custom schema (es. 18m IS / 6m OOS / 6m step)
python -m engine.wf_runner --universe portfolio \
    --is-months 18 --oos-months 6 --step-months 6 \
    --grid full
```

### Note implementative

- **TrendModuleWF**: per i fold OOS di 3 mesi (~63 bar), il `TrendModule`
  default con `sma_long=200` causa `IndexError` (basicops). Il WF runner usa
  un override `TrendModuleWF` con `sma_short=20, sma_long=60` (subclass
  inline in `wf_runner.main`).
- **Warmup**: `warmup_calendar_days=120` arretra il feed `fromdate` per
  alimentare gli indicatori PRIMA della finestra di valutazione.
  `warmup_bars=60` ridotto rispetto al default 200 della strategy.
- **TradeAnalyzer**: usiamo `total.total` (open + closed) e NON `total.closed`,
  perché le posizioni IS spesso restano aperte fino al fold end.
- **Loop esplicito** sui parametri (no `cerebro.optstrategy`): permette
  scoring custom, gestione exception per combo, e logging dettagliato.

### File generati

- `engine/walkforward.py` (478 righe): `Fold`, `FoldResult`, `RunMetrics`,
  `generate_folds`, `expand_grid`, `select_best_params`, `aggregate_stability`,
  `run_walkforward`.
- `engine/wf_runner.py` (480 righe): CLI runner + `make_backtest_runner` factory
  + `TrendModuleWF`.
- `tests/test_walkforward.py` (37 test): tutti i moduli del framework.
- Test suite totale: **200 test verdi** in 4.3s.

## Roadmap fasi successive

- **F2** — ✓ Engine Backtrader: PatrimonioStrategy + 6 moduli + CustomData
- **F3** — ✓ Risk Management: ✓ 3.1 vol-target sizing, ✓ 3.2 regime VIX exit
  dinamica, ✓ 3.3 portfolio constraints (sector cap + beta cap)
- **F4** — ✓ Walk-Forward + parameter stability: rolling window 12m/3m,
  griglia 72 combo, OOS validation, stability analysis
- **F5** — Reporting + integrazione: PDF report + pesi ottimizzati → v2.0 production
