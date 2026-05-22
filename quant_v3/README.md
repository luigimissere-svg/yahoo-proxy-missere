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
│   └── modules/                   # 6 alpha modules
│       ├── trend.py               # SMA cross + ADX + slope
│       ├── momentum.py            # RSI + MACD/ATR + ROC
│       ├── mean_reversion.py      # Z-score + Bollinger + ADX filter
│       ├── value.py               # P/E + P/B + FCF yield
│       ├── quality.py             # ROE + margin + D/E
│       └── event_driven.py        # PEAD post-earnings drift
├── tests/                          # pytest suite (47 test, < 5s)
├── risk/                          # [F3] Risk management (TODO)
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

47 test, < 5s. Coverage:
- `test_data_loader.py` (11) — lake structure + feed building
- `test_signals.py` (15) — composite blending + gating + Strategia B (pesi 0, pre-screening)
- `test_modules.py` (16) — 6 moduli alpha + bounds + monotonia
- `test_strategy_smoke.py` (3) — e2e cerebro run + quality_filter unit

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

## Roadmap fasi successive

- **F2** — ✓ Engine Backtrader: PatrimonioStrategy + 6 moduli + CustomData
- **F3** — Risk Management: position sizing avanzato (vol-targeting, Kelly capped),
  exit logic dinamica (regime-aware), portfolio constraints (sector cap, beta cap)
- **F4** — Optimization + Walk-Forward: optstrategy su rolling window 12m/3m,
  out-of-sample validation, parameter stability analysis
- **F5** — Reporting + integrazione: PDF report + pesi ottimizzati → v2.0 production
