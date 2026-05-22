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
├── engine_v3/                     # [F2] Strategy Backtrader (prossima fase)
├── risk/                          # [F3] Risk management
├── optimization/                  # [F4] Walk-forward + optstrategy
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

## Roadmap fasi successive

- **F2** — Engine Backtrader: PatrimonioStrategy + 6 moduli + CustomData
- **F3** — Risk Management: position sizing, exit logic, portfolio constraints
- **F4** — Optimization + Walk-Forward: optstrategy + rolling window 12m/3m
- **F5** — Reporting + integrazione: PDF report + pesi ottimizzati → v2.0 production
