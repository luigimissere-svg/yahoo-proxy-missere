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
):
    """
    Costruisce una callback `run_backtest(params, start, end) → RunMetrics`.

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
    """
    import datetime as _dt

    def run_backtest(params: Dict[str, Any], start: datetime, end: datetime) -> RunMetrics:
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

        try:
            results = cerebro.run()
            strat = results[0]
        except Exception as e:
            import traceback
            logger.warning(f"cerebro.run FAIL params={params}: {e}")
            logger.debug(traceback.format_exc())
            return RunMetrics.empty()

        # Cross-check Backtrader (mantenuto solo come sanity, non usato dal driver).
        sharpe_bt_raw = strat.analyzers.sharpe_bt.get_analysis().get('sharperatio')
        sharpe_bt = float(sharpe_bt_raw) if sharpe_bt_raw is not None else 0.0

        # Ground truth: Sharpe annualizzato calcolato a mano su daily return.
        # Guard clause: se la finestra ha < 20 barre, < 10 ritorni non-zero o
        # std troppo piccola, marca il fold come 'insufficient_window' e ritorna
        # NaN come Sharpe — il driver lo escluderà dalle aggregazioni.
        tr_ana = strat.analyzers.tr.get_analysis()
        rets = np.array(
            [r for _, r in sorted(tr_ana.items())],
            dtype=float,
        )
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

        return RunMetrics(
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
        )

    return run_backtest


# ─── Pretty print ────────────────────────────────────────────────────────────

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
    )

    results = run_walkforward(
        folds=folds,
        param_grid=grid,
        run_backtest=run_backtest,
        min_trades_per_fold=args.min_trades,
        tie_break_pct=args.tie_break_pct,
        verbose=args.verbose,
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


if __name__ == '__main__':
    main()
