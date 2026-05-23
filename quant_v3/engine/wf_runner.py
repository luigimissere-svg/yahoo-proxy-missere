"""
Walk-Forward runner CLI — Fase 4.

Lancia walk-forward optimization sul portfolio Missere:
    cd quant_v3
    python -m engine.wf_runner --universe portfolio \\
        --from 2024-08-01 --to 2026-05-22 \\
        --is-months 12 --oos-months 3 --step-months 3 \\
        --grid full \\
        --output-csv wf_results.csv \\
        --stability-json wf_stability.json

Output:
    - wf_results.csv: una riga per fold con best_params + IS/OOS metrics
    - wf_stability.json: aggregate stability analysis
    - Stdout: tabella sintetica leggibile

Grid presets:
    - smoke (8 combo, ~3 min/fold): per validare pipeline
    - full (72 combo, ~25 min/fold): griglia completa Fase 4

Note tecniche:
    - I feed sono caricati una volta sola; ogni run cerebro li registra con
      clamp fromdate/todate del fold. Riusiamo `bundle` cached.
    - cerebro.run() è single-threaded; il parallel sarebbe Pool ma poco utile
      data l'overhead di pickle dei feed.
    - PortfolioConstraints viene istanziato per ogni combinazione (costo
      trascurabile: solo lookup in dict).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import backtrader as bt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.custom_data import build_feed
from engine.strategy import PatrimonioStrategy
from engine.modules._fundamentals import set_data_root as set_fundamentals_root
from engine.constraints import make_default_constraints
from engine.trade_ledger import TradeLedger
from engine.walkforward import (
    Fold,
    FoldResult,
    RunMetrics,
    aggregate_stability,
    generate_folds,
    results_to_csv_rows,
    run_walkforward,
)

logger = logging.getLogger(__name__)


# ─── Grid presets ────────────────────────────────────────────────────────────

GRID_SMOKE: Dict[str, List[Any]] = {
    'threshold': [0.15, 0.25],
    'min_concordant': [2, 3],
    'max_sector_pct': [None, 0.30],
}  # 2×2×2 = 8 combo

GRID_FULL: Dict[str, List[Any]] = {
    'threshold': [0.15, 0.20, 0.25],
    'min_concordant': [2, 3],
    'target_risk_pct': [0.008, 0.010, 0.012],
    'max_sector_pct': [None, 0.30],
    'max_portfolio_beta': [None, 1.3],
}  # 3×2×3×2×2 = 72 combo


# ─── Backtest factory ────────────────────────────────────────────────────────

def make_backtest_runner(
    bundles: Dict[str, Any],
    tickers: List[str],
    universe: str,
    cash: float,
    commission: float,
    metadata_path: Path,
    sector_map_cache: Dict[str, str],
    beta_map_cache: Dict[str, float],
    fixed_params: Dict[str, Any],
    warmup_calendar_days: int = 365,
    attach_returns: bool = False,
    with_ledger: bool = False,
):
    """
    Costruisce una callback `run_backtest(params, start, end) → RunMetrics`
    (oppure `(RunMetrics, list[dict trade])` se with_ledger=True).

    `bundles` è il dict ticker → DataBundle pre-caricato dal data lake.
    `warmup_calendar_days` arretra il feed `fromdate` per dare a backtrader
    bar storici sufficienti a far 'scaldare' gli indicatori PRIMA del fold start.
    Con SMA(200) il minperiod è 200 bar trading ≈ 280 calendar days; usiamo
    365 (1 anno) per margine.

    Importante (Fase 4 estesa): warmup totale = minperiod (200 bar SMA200)
    + warmup_bars esplicito (default 50) = 250 bar. Backtrader attende il
    minperiod automaticamente (prenext), poi la strategia aggiunge i
    warmup_bars espliciti per stabilizzare segnali compositi prima del
    primo trade. Pre-roll richiesto: ≥ 250 business days dal feed start
    al fold IS start.

    Bug 7 fix (B2 patch 23/05/2026): with_ledger=True aggiunge il TradeLedger
    analyzer e cambia signature di ritorno a (RunMetrics, list[dict]).
    `make_ledger_runner` è ora un thin wrapper di questa funzione.

    Bug 2 fix (B2 patch 23/05/2026): il calcolo `sharpe_a` ora usa
    `rets_filtered` con dates in [start_d, end_d], non l'intero vettore
    del feed che includeva ~262 BD di warmup. Convenzione Opzione A
    (strict): include il return del primo giorno del fold.

    Bug 5 fix (B2 patch 23/05/2026): `fold_start_dt = start.date()` viene
    propagato alla strategia per bloccare segnali pre-roll.
    """
    import datetime as _dt

    def run_backtest(params: Dict[str, Any], start: datetime, end: datetime):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.broker.set_cash(cash)
        cerebro.broker.setcommission(commission=commission)

        # Feed range: arretra fromdate per warmup; la strategia userà il primo
        # bar utile dopo warmup_bars per emettere segnali.
        feed_from = start - _dt.timedelta(days=warmup_calendar_days)
        from_str = feed_from.strftime('%Y-%m-%d')
        to_str = end.strftime('%Y-%m-%d')

        n_added = 0
        for t in tickers:
            bundle = bundles.get(t)
            if bundle is None:
                continue
            try:
                feed = build_feed(bundle, fromdate=from_str, todate=to_str, earnings_window=5)
                cerebro.adddata(feed, name=t)
                n_added += 1
            except Exception:
                continue
        if n_added == 0:
            return RunMetrics.empty()

        # Costruisci PortfolioConstraints se richiesto dai params
        max_sector_pct = params.get('max_sector_pct', None)
        max_portfolio_beta = params.get('max_portfolio_beta', None)
        portfolio_constraints = None
        if (max_sector_pct is not None and max_sector_pct > 0) or \
           (max_portfolio_beta is not None and max_portfolio_beta > 0):
            from engine.constraints import PortfolioConstraints
            portfolio_constraints = PortfolioConstraints(
                sector_map=sector_map_cache,
                beta_map=beta_map_cache,
                max_sector_pct=max_sector_pct,
                max_portfolio_beta=max_portfolio_beta,
                violation_policy='block_new',
            )

        # Build strategy kwargs: parametri dalla griglia + defaults da fixed_params
        strat_kwargs = dict(fixed_params)
        # Mappa parametri della griglia ai param della strategy
        for key in ('threshold', 'min_concordant', 'target_risk_pct'):
            if key in params:
                strat_kwargs[key] = params[key]
        strat_kwargs['portfolio_constraints'] = portfolio_constraints
        # Bug 5 fix: propaga fold_start_dt come date (Backtrader fornisce date).
        strat_kwargs['fold_start_dt'] = start.date() if isinstance(start, _dt.datetime) else start

        cerebro.addstrategy(PatrimonioStrategy, **strat_kwargs)

        # Analyzers minimi (Sharpe + DD + trades + TimeReturn per ground truth NumPy).
        #
        # POST-PATCH bug Sharpe OOS = 1,0000 (maggio 2026, branch v3-quant-framework):
        # rimosso bt.analyzers.SharpeRatio_A perché numericamente instabile su
        # finestre OOS corte (~63 barre). Sostituito con calcolo a mano via NumPy
        # sul TimeReturn analyzer (ground truth). bt.analyzers.SharpeRatio standard
        # è mantenuto come cross-check con annualizzazione esplicita.
        cerebro.addanalyzer(
            bt.analyzers.SharpeRatio,
            _name='sharpe_bt',
            riskfreerate=0.0,
            annualize=True,
            timeframe=bt.TimeFrame.Days,
            convertrate=True,
            factor=252,
        )
        cerebro.addanalyzer(
            bt.analyzers.TimeReturn,
            _name='tr',
            timeframe=bt.TimeFrame.Days,
        )
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='dd')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        # Bug 7 fix: ledger opzionale sulla stessa codepath.
        if with_ledger:
            cerebro.addanalyzer(TradeLedger, _name='ledger')

        try:
            results = cerebro.run()
            strat = results[0]
        except Exception as e:
            import traceback
            logger.warning(f"cerebro.run FAIL params={params}: {e}")
            logger.debug(traceback.format_exc())
            return (RunMetrics.empty(), []) if with_ledger else RunMetrics.empty()

        # Cross-check Backtrader (mantenuto solo come sanity, non usato dal driver).
        sharpe_bt_raw = strat.analyzers.sharpe_bt.get_analysis().get('sharperatio')
        sharpe_bt = float(sharpe_bt_raw) if sharpe_bt_raw is not None else 0.0

        # Bug 2 fix (B2 patch 23/05/2026): filtro [start_d, end_d] applicato
        # PRIMA del calcolo Sharpe. Pre-patch il vettore `rets` conteneva ~262
        # BD di warmup_calendar_days che diluivano la deviazione standard di un
        # fattore ~√(n_full/n_eff) sottostimando il Sharpe v7.2.
        # Convenzione Opzione A: include il return del primo giorno del fold.
        # Ground truth: Sharpe annualizzato calcolato a mano su daily return.
        # Guard clause: se la finestra ha < 20 barre, < 10 ritorni non-zero o
        # std troppo piccola, marca il fold come 'insufficient_window' e ritorna
        # NaN come Sharpe — il driver lo escluderà dalle aggregazioni.
        tr_ana = strat.analyzers.tr.get_analysis()

        def _to_date(x):
            if isinstance(x, _dt.datetime):
                return x.date()
            if isinstance(x, _dt.date):
                return x
            return None

        start_d_filter = _to_date(start)
        end_d_filter = _to_date(end)
        rets_pairs = []
        for d, r in sorted(tr_ana.items()):
            d_norm = _to_date(d)
            if d_norm is None or start_d_filter is None or end_d_filter is None:
                continue
            if start_d_filter <= d_norm <= end_d_filter:
                rets_pairs.append((d_norm, float(r)))
        rets = np.array([r for _, r in rets_pairs], dtype=float)
        n_bars = int(rets.size)
        n_nonzero = int(np.count_nonzero(rets))
        # Std richiede almeno 2 osservazioni; calcola in sicurezza.
        std_rets = float(rets.std(ddof=1)) if n_bars >= 2 else 0.0
        if n_bars < 20 or n_nonzero < 10 or std_rets < 1e-8:
            sharpe_a = float('nan')
            sharpe_flag = 'insufficient_window'
        else:
            sharpe_a = float(rets.mean() / std_rets * np.sqrt(252))
            sharpe_flag = 'ok'

        # Sharpe standard non-annualizzato (lasciato per compatibilità retroattiva
        # con il campo `sharpe` di RunMetrics; non usato dal driver). Ricavato dallo
        # stesso analyzer Backtrader, senza annualizzazione — valore puramente
        # informativo.
        sharpe = sharpe_bt / float(np.sqrt(252)) if sharpe_flag == 'ok' else 0.0

        dd = strat.analyzers.dd.get_analysis().get('max', {}).get('drawdown', 0.0) or 0.0
        trades_ana = strat.analyzers.trades.get_analysis()
        # FIX Fase 4: TradeAnalyzer.closed conta solo i trade chiusi.
        # In una finestra IS di 12 mesi le posizioni possono restare aperte fino alla fine,
        # quindi usiamo `total.total` (open + closed) — questo è il numero di trade APERTI
        # nel fold, che è la metrica corretta per giudicare se la strategia è attiva.
        total_block = trades_ana.get('total', {}) or {}
        n_trades = total_block.get('total', 0) or total_block.get('closed', 0) or 0
        final_value = cerebro.broker.getvalue()
        pnl_pct = (final_value / cash - 1.0) * 100.0

        # v7.3 DSR: serie giornaliera attaccata su richiesta esplicita.
        # Riutilizziamo `rets_pairs` già filtrato a [start_d, end_d] sopra
        # (Bug 2 fix): la finestra usata per equity CSV è identica a quella
        # del calcolo Sharpe, garantendo consistenza.
        daily_returns: List[Any] = []
        if attach_returns:
            daily_returns = [(d.isoformat(), r) for d, r in rets_pairs]

        metrics = RunMetrics(
            sharpe=float(sharpe),
            sharpe_a=float(sharpe_a),
            pnl_pct=float(pnl_pct),
            max_dd=float(dd),
            trades=int(n_trades),
            final_value=float(final_value),
            sharpe_bt=float(sharpe_bt),
            sharpe_flag=sharpe_flag,
            n_bars=n_bars,
            n_nonzero_returns=n_nonzero,
            daily_returns=daily_returns,
        )
        if with_ledger:
            ledger_data = strat.analyzers.ledger.get_analysis()
            return metrics, ledger_data.get('trades', [])
        return metrics

    return run_backtest


def make_ledger_runner(
    bundles: Dict[str, Any],
    tickers: List[str],
    cash: float,
    commission: float,
    sector_map_cache: Dict[str, str],
    beta_map_cache: Dict[str, float],
    fixed_params: Dict[str, Any],
    warmup_calendar_days: int = 365,
    universe: str = 'portfolio',
    metadata_path: Path = Path('.'),
):
    """
    Bug 7 fix (B2 patch 23/05/2026): thin wrapper di `make_backtest_runner`
    con `with_ledger=True`. Tutta la logica (Sharpe, Bug 2 filtro rets, Bug 5
    gate fold-start) è nell'unica codepath di make_backtest_runner. Questa
    funzione esiste solo per retro-compatibilità con i call sites che
    usavano la vecchia signature.

    Returns:
        run_with_ledger(params, start, end) → (RunMetrics, list[dict trade])

    Nota: `metadata_path` non era usato neanche nell'implementazione originale
    pre-refactor (era un parametro ridondante in make_backtest_runner).
    Mantenuto opzionale per compatibilità; default Path('.') è sicuro perché
    sector_map e beta_map sono passati già risolti come dict.
    """
    return make_backtest_runner(
        bundles=bundles,
        tickers=tickers,
        universe=universe,
        cash=cash,
        commission=commission,
        metadata_path=metadata_path,
        sector_map_cache=sector_map_cache,
        beta_map_cache=beta_map_cache,
        fixed_params=fixed_params,
        warmup_calendar_days=warmup_calendar_days,
        attach_returns=True,
        with_ledger=True,
    )


# ─── Pretty print ────────────────────────────────────────────────

def print_results_table(results: List[FoldResult]) -> None:
    print("\n" + "═" * 110)
    print("WALK-FORWARD RESULTS — IS vs OOS per fold")
    print("═" * 110)
    header = f"{'Fold':<5} {'IS period':<23} {'OOS period':<23} {'IS Shp':>7} {'OOS Shp':>8} {'Degr':>6} {'IS tr':>6} {'OOS tr':>7} {'OOS DD':>7} {'Flag':>6}"
    print(header)
    print("─" * 110)
    for r in results:
        is_p = f"{r.is_start}→{r.is_end}"
        oos_p = f"{r.oos_start}→{r.oos_end}"
        flag = '⚠OVF' if r.overfitting_flag else 'ok'
        print(
            f"F{r.fold_id:<4} {is_p:<23} {oos_p:<23} "
            f"{r.is_metrics.sharpe_a:>7.3f} {r.oos_metrics.sharpe_a:>8.3f} "
            f"{r.degradation_ratio:>6.2f} {r.is_metrics.trades:>6d} "
            f"{r.oos_metrics.trades:>7d} {r.oos_metrics.max_dd:>6.2f}% {flag:>6}"
        )
    print("─" * 110)


def print_best_params_table(results: List[FoldResult]) -> None:
    print("\n" + "═" * 110)
    print("BEST PARAMS per fold")
    print("═" * 110)
    if not results:
        return
    # Estrai tutti i param keys
    keys = sorted({k for r in results for k in r.best_params.keys()})
    header = f"{'Fold':<5} " + " ".join(f"{k:<18}" for k in keys)
    print(header)
    print("─" * 110)
    for r in results:
        row = f"F{r.fold_id:<4} " + " ".join(
            f"{str(r.best_params.get(k, '-')):<18}" for k in keys
        )
        print(row)
    print("─" * 110)


def print_stability_summary(stability: Dict[str, Any]) -> None:
    print("\n" + "═" * 110)
    print("PARAMETER STABILITY ANALYSIS")
    print("═" * 110)
    n_folds = stability['n_folds']
    threshold = stability['stable_threshold']
    print(f"Fold totali analizzati: {n_folds}")
    print(f"Soglia 'stabile': ≥{threshold}/{n_folds} fold con stesso valore vincente\n")

    print("Distribuzione valori vincenti per parametro:")
    for param, counter in stability['param_counts'].items():
        sorted_counter = sorted(counter.items(), key=lambda x: -x[1])
        line = f"  {param}: " + " | ".join(
            f"{v}={c}" for v, c in sorted_counter
        )
        print(line)

    stable = stability['stable_params']
    if stable:
        print(f"\n✓ Parametri STABILI (almeno {threshold}/{n_folds} fold):")
        for k, v in stable.items():
            print(f"    {k} = {v}")
    else:
        print(f"\n⚠ Nessun parametro stabile su {threshold}/{n_folds} fold "
              f"→ sistema sensibile al periodo, considerare composite metric o griglia diversa")

    print(f"\nIS Sharpe medio:  {stability['is_sharpe_mean']:>7.3f}")
    print(f"OOS Sharpe medio: {stability['oos_sharpe_mean']:>7.3f}")
    print(f"Degradation medio: {stability['degradation_mean']:>7.2f}  "
          f"(< 0.3 = overfitting; > 0.7 = molto stabile)")
    print(f"Overfitting flag count: {stability['overfitting_count']}/{n_folds}")
    print("═" * 110)


# ─── Main CLI ────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Patrimonio v3 walk-forward optimization")
    p.add_argument('--universe', choices=['portfolio', 'extended'], default='portfolio')
    p.add_argument('--from', dest='fromdate', type=str, default='2024-08-01')
    p.add_argument('--to', dest='todate', type=str, default='2026-05-22')
    p.add_argument('--cash', type=float, default=100_000.0)
    p.add_argument('--commission', type=float, default=0.001)
    # WF window
    p.add_argument('--is-months', type=int, default=12)
    p.add_argument('--oos-months', type=int, default=3)
    p.add_argument('--step-months', type=int, default=3)
    # Grid
    p.add_argument('--grid', choices=['smoke', 'full'], default='smoke',
                   help="Preset griglia: 'smoke' (8 combo) o 'full' (72 combo)")
    # Fixed params (defaults Fase 3)
    p.add_argument('--max-positions', type=int, default=10)
    p.add_argument('--per-ticker-cap', type=float, default=0.10)
    p.add_argument('--warmup-bars', type=int, default=50,
                   help="Warmup bars strategy explicit (default 50). "
                        "Backtrader aggiunge automaticamente i 200 bar di "
                        "minperiod SMA200 → warmup totale = 250 bar.")
    p.add_argument('--metadata-path', type=str,
                   default='data/meta/sector_beta.parquet')
    # Anti-overfitting
    p.add_argument('--min-trades', type=int, default=5,
                   help="Trade minimi IS per validare un parameter set")
    p.add_argument('--tie-break-pct', type=float, default=0.05)
    p.add_argument('--stable-threshold', type=int, default=3,
                   help="N fold richiesti per dichiarare un parametro 'stabile'")
    # Output
    p.add_argument('--output-csv', type=str, default='wf_results.csv')
    p.add_argument('--stability-json', type=str, default='wf_stability.json')
    p.add_argument('--save-trades-csv', dest='save_trades_csv', type=str, default=None,
                   help="Path CSV per dump trade-level ledger su tutti i fold OOS "
                        "con best_params selezionati. Genera un re-run OOS dedicato "
                        "per fold con TradeLedger attivo (overhead ~ N_fold * 1 backtest). "
                        "Output: 1 riga per trade chiuso (+ snapshot trade aperti a fine "
                        "finestra OOS) con colonna fold_id. Necessario per analisi di "
                        "concentrazione e falsificazione ipotesi few-winners.")
    p.add_argument('--save-equity-csv', dest='save_equity_csv', type=str, default=None,
                   help="Path CSV per dump daily returns equity-curve di TUTTI i trial "
                        "della grid × tutti i fold, sia in fase IS sia in fase OOS. "
                        "Output formato lungo: trial_id, fold_id, phase (IS|OOS), "
                        "params_json, sharpe_a, date, daily_return. Per IS: usa le "
                        "serie già calcolate nel walk-forward (zero overhead). Per OOS: "
                        "esegue un OOS-grid scan dedicato (N_grid × N_fold backtest "
                        "aggiuntivi, ~2-3h per griglia full). Necessario per DSR formale "
                        "Bailey-LdP con matrice di correlazione (item consulente v7.3).")
    p.add_argument('--data-root', type=str, default=str(ROOT / 'data'))
    p.add_argument('--verbose', action='store_true')
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s | %(message)s",
    )

    # ── Pre-load bundles (una volta sola) ────────────────────────────────
    loader = DataLakeLoader(data_root=args.data_root)
    set_fundamentals_root(args.data_root)
    tickers = loader.list_tickers(args.universe, apply_filters=True)
    print(f"Loading {len(tickers)} ticker bundles from universe '{args.universe}'...")
    bundles = {}
    for t in tickers:
        b = loader.load_ticker(t, args.universe)
        if b is not None:
            bundles[t] = b
    print(f"Bundles loaded: {len(bundles)}/{len(tickers)}")

    # ── Sector/beta metadata ─────────────────────────────────────────────
    from engine.constraints import load_metadata
    meta_path = Path(args.metadata_path)
    if not meta_path.is_absolute():
        meta_path = ROOT / meta_path
    if not meta_path.exists():
        print(f"WARN: metadata file '{meta_path}' non trovato → constraints disabilitati")
        sector_map_cache, beta_map_cache = {}, {}
    else:
        sector_map_cache, beta_map_cache = load_metadata(meta_path)
        print(f"Metadata loaded: {len(sector_map_cache)} ticker mapped")

    # ── Folds ────────────────────────────────────────────────────────────
    start_dt = datetime.strptime(args.fromdate, '%Y-%m-%d')
    end_dt = datetime.strptime(args.todate, '%Y-%m-%d')
    folds = generate_folds(
        start_dt, end_dt,
        is_months=args.is_months,
        oos_months=args.oos_months,
        step_months=args.step_months,
    )
    print(f"\nGenerated {len(folds)} fold(s):")
    for f in folds:
        print(f"  {f}")

    # ── Grid ─────────────────────────────────────────────────────────────
    grid = GRID_FULL if args.grid == 'full' else GRID_SMOKE
    n_combos = 1
    for v in grid.values():
        n_combos *= len(v)
    print(f"\nGrid preset '{args.grid}': {n_combos} combo")
    for k, vs in grid.items():
        print(f"  {k}: {vs}")

    # ── Fixed params (defaults Fase 3) ───────────────────────────────────
    # Fase 4 estesa: data lake da 2023-01 → abbiamo abbastanza storia per
    # ripristinare warmup_bars=200 (default strategy) e usare DEFAULT_MODULES
    # (TrendModule con SMA(200)). Niente più TrendModuleWF.
    fixed_params = {
        'max_positions': args.max_positions,
        'per_ticker_cap': args.per_ticker_cap,
        'warmup_bars': args.warmup_bars,
        'sizing_method': 'vol_target',
        'min_position_pct': 0.005,
        'vol_floor_pct': 0.005,
        'vol_proxy': 'atr',
        'vol_lookback': 14,
        'quality_filter_enabled': True,
        'value_floor': -0.5,
        'quality_floor': -0.5,
        'verbose': False,
        # target_risk_pct: default Fase 3.1 = 0.01, sovrascrivibile dalla griglia
        'target_risk_pct': 0.01,
        'regime_mode': 'off',
        'vix_feed_name': None,
    }

    # ── Run WF ───────────────────────────────────────────────────────────
    # v7.3 DSR: se --save-equity-csv è attivo, abilitiamo attach_returns nella
    # factory e predisponiamo il CSV append-mode + il collector che intercetta
    # le serie IS di tutti i trial della grid mentre il walk-forward gira
    # (zero overhead, riusa le tr_ana già calcolate).
    attach_returns_flag = bool(args.save_equity_csv)

    run_backtest = make_backtest_runner(
        bundles=bundles,
        tickers=list(bundles.keys()),
        universe=args.universe,
        cash=args.cash,
        commission=args.commission,
        metadata_path=meta_path,
        sector_map_cache=sector_map_cache,
        beta_map_cache=beta_map_cache,
        fixed_params=fixed_params,
        attach_returns=attach_returns_flag,
    )

    # Equity CSV setup + collector closure.
    equity_csv_writer = None
    equity_csv_file = None
    equity_collector_fn = None
    if args.save_equity_csv:
        equity_path = Path(args.save_equity_csv)
        if not equity_path.is_absolute():
            equity_path = ROOT / equity_path
        equity_path.parent.mkdir(parents=True, exist_ok=True)
        equity_csv_file = equity_path.open('w', newline='', encoding='utf-8')
        equity_csv_writer = csv.writer(equity_csv_file)
        equity_csv_writer.writerow([
            'trial_id', 'fold_id', 'phase', 'params_json',
            'sharpe_a', 'sharpe_flag', 'n_bars', 'n_nonzero_returns',
            'date', 'daily_return',
        ])
        print(f"\n[v7.3 DSR] Equity CSV opened: {equity_path}")

        def _equity_collector(trial_idx, fold_id, phase, params, metrics):
            params_repr = json.dumps(params, default=str, sort_keys=True)
            if not metrics.daily_returns:
                # Riga sentinella per fold/trial senza serie (insufficient_window)
                equity_csv_writer.writerow([
                    trial_idx, fold_id, phase, params_repr,
                    metrics.sharpe_a, metrics.sharpe_flag,
                    metrics.n_bars, metrics.n_nonzero_returns,
                    '', '',
                ])
                return
            for d_iso, ret in metrics.daily_returns:
                equity_csv_writer.writerow([
                    trial_idx, fold_id, phase, params_repr,
                    metrics.sharpe_a, metrics.sharpe_flag,
                    metrics.n_bars, metrics.n_nonzero_returns,
                    d_iso, f"{ret:.10f}",
                ])

        equity_collector_fn = _equity_collector

    results = run_walkforward(
        folds=folds,
        param_grid=grid,
        run_backtest=run_backtest,
        min_trades_per_fold=args.min_trades,
        tie_break_pct=args.tie_break_pct,
        verbose=args.verbose,
        equity_collector=equity_collector_fn,
    )

    # ── Output ───────────────────────────────────────────────────────────
    if not results:
        print("\n⚠ Nessun fold ha prodotto un parameter set valido (verifica min-trades).")
        return

    print_results_table(results)
    print_best_params_table(results)
    stability = aggregate_stability(results, stable_threshold=args.stable_threshold)
    print_stability_summary(stability)

    # CSV
    csv_path = Path(args.output_csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    rows = results_to_csv_rows(results)
    if rows:
        all_keys = sorted({k for r in rows for k in r.keys()})
        # Riordina: id/period prima, metriche dopo, param_* in fondo
        priority = [
            'fold_id', 'is_start', 'is_end', 'oos_start', 'oos_end',
            'is_sharpe_a', 'oos_sharpe_a', 'degradation_ratio', 'overfitting_flag',
            'is_pnl_pct', 'oos_pnl_pct', 'is_max_dd', 'oos_max_dd',
            'is_trades', 'oos_trades',
            'n_combos_evaluated', 'n_combos_skipped_min_trades',
        ]
        ordered_keys = [k for k in priority if k in all_keys] + \
                       [k for k in all_keys if k not in priority]
        with csv_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=ordered_keys)
            w.writeheader()
            w.writerows(rows)
        print(f"\nResults CSV saved: {csv_path}")

    # JSON
    json_path = Path(args.stability_json)
    if not json_path.is_absolute():
        json_path = ROOT / json_path
    # Serializzazione: param_counts ha valori non sempre JSON-friendly (None ok, float ok)
    def _safe(o):
        if isinstance(o, dict):
            return {str(k): _safe(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_safe(x) for x in o]
        return o

    with json_path.open('w') as f:
        json.dump(_safe(stability), f, indent=2, default=str)
    print(f"Stability JSON saved: {json_path}")

    # ── Trade ledger dump (item consulente v7→v8) ────────────────────────
    # Re-run OOS per ogni fold con best_params selezionati e TradeLedger attivo.
    # Costo: N_fold backtest aggiuntivi (~3 per WF standard) — trascurabile.
    # Risultato: 1 CSV con tutti i trade chiusi OOS + snapshot trade aperti a
    # fine OOS, con colonna fold_id, utile per analisi di concentrazione e
    # falsificazione dell'ipotesi few-winners.
    if args.save_trades_csv:
        print("\n" + "═" * 110)
        print("TRADE LEDGER — re-run OOS per-fold con best_params")
        print("═" * 110)

        ledger_run = make_ledger_runner(
            bundles=bundles,
            tickers=list(bundles.keys()),
            cash=args.cash,
            commission=args.commission,
            sector_map_cache=sector_map_cache,
            beta_map_cache=beta_map_cache,
            fixed_params=fixed_params,
        )

        all_trades: List[Dict[str, Any]] = []
        for r in results:
            oos_start_dt = datetime.strptime(r.oos_start, '%Y-%m-%d') \
                if isinstance(r.oos_start, str) else r.oos_start
            oos_end_dt = datetime.strptime(r.oos_end, '%Y-%m-%d') \
                if isinstance(r.oos_end, str) else r.oos_end
            print(f"  Fold {r.fold_id}: re-run OOS {r.oos_start} → {r.oos_end} "
                  f"con params={r.best_params}")
            try:
                _metrics, trades = ledger_run(r.best_params, oos_start_dt, oos_end_dt)
            except Exception as exc:
                print(f"    ⚠ ledger re-run errore: {exc}")
                continue
            for tr in trades:
                row = dict(tr)
                row['fold_id'] = r.fold_id
                row['oos_start'] = r.oos_start
                row['oos_end'] = r.oos_end
                all_trades.append(row)
            n_closed = sum(1 for t in trades if t.get('status') == 'closed')
            n_open = sum(1 for t in trades if t.get('status') == 'open_at_end')
            print(f"    → closed={n_closed}, open_at_end={n_open}")

        # Dump CSV.
        trades_csv_path = Path(args.save_trades_csv)
        if not trades_csv_path.is_absolute():
            trades_csv_path = ROOT / trades_csv_path
        fieldnames = [
            'fold_id', 'oos_start', 'oos_end',
            'ticker', 'dt_open', 'dt_close', 'bars_held',
            'size', 'entry_price', 'notional_open',
            'pnl_gross', 'pnl_net', 'pnl_pct',
            'commission', 'status',
        ]
        with trades_csv_path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in all_trades:
                w.writerow({k: row.get(k, '') for k in fieldnames})
        print(f"\nTrade ledger CSV saved: {trades_csv_path}  "
              f"(rows={len(all_trades)})")

    # ── v7.3 DSR: OOS grid scan + chiusura equity CSV ─────────────────────────
    # Quando --save-equity-csv è attivo, il collector ha già dumpato le serie
    # IS di tutti i trial durante il walk-forward. Ora dobbiamo dumpare anche
    # le serie OOS di TUTTI i trial (non solo del vincitore di fold) eseguendo
    # un OOS-grid scan dedicato. Costo: N_grid × N_fold backtest aggiuntivi
    # (~2-3h per griglia full su 3 fold). Necessario per il block bootstrap
    # empirico di SR_0 sotto framework DSR Bailey-LdP (item consulente v7.3).
    if equity_csv_writer is not None:
        try:
            from engine.walkforward import expand_grid
            print("\n" + "═" * 110)
            print("OOS-GRID SCAN — dump serie equity di TUTTI i trial × fold OOS (v7.3 DSR)")
            print("═" * 110)
            combos_all = expand_grid(grid)
            total_oos_runs = len(combos_all) * len(results)
            print(
                f"Esecuzione di {len(combos_all)} trial × {len(results)} fold = "
                f"{total_oos_runs} backtest OOS aggiuntivi."
            )
            for r in results:
                oos_start_dt = datetime.strptime(r.oos_start, '%Y-%m-%d') \
                    if isinstance(r.oos_start, str) else r.oos_start
                oos_end_dt = datetime.strptime(r.oos_end, '%Y-%m-%d') \
                    if isinstance(r.oos_end, str) else r.oos_end
                print(f"  Fold {r.fold_id} OOS [{r.oos_start} → {r.oos_end}]: "
                      f"avvio scan di {len(combos_all)} trial...")
                for trial_idx, params in enumerate(combos_all, 1):
                    try:
                        m_oos = run_backtest(params, oos_start_dt, oos_end_dt)
                    except Exception as exc:
                        logger.warning(
                            f"  OOS-grid trial {trial_idx} fold {r.fold_id} FAIL: {exc}"
                        )
                        m_oos = None
                    if m_oos is None:
                        continue
                    try:
                        equity_collector_fn(trial_idx, r.fold_id, 'OOS', params, m_oos)
                    except Exception as exc:
                        logger.warning(
                            f"  equity_collector OOS trial {trial_idx} fold {r.fold_id} FAIL: {exc}"
                        )
                    if args.verbose and trial_idx % 10 == 0:
                        print(f"    OOS scan fold {r.fold_id}: {trial_idx}/{len(combos_all)}")
                print(f"  Fold {r.fold_id} OOS scan completato.")
        finally:
            if equity_csv_file is not None:
                equity_csv_file.flush()
                equity_csv_file.close()
                print(f"\n[v7.3 DSR] Equity CSV closed: {args.save_equity_csv}")


if __name__ == '__main__':
    main()
