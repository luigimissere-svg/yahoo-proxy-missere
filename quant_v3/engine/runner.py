"""
Runner CLI per backtest PatrimonioStrategy.

Uso:
    cd quant_v3
    python -m engine.runner --universe portfolio --from 2024-08-01 --cash 100000

    python -m engine.runner --universe portfolio \\
        --from 2024-08-01 --to 2026-05-21 \\
        --cash 100000 --commission 0.001 \\
        --threshold 0.20 --min-concordant 3 \\
        --max-positions 10 --per-ticker-cap 0.10 \\
        --stop-loss 0.07 --take-profit 0.20 --trailing 0.08 \\
        --log-trades trades.csv \\
        --verbose

Output:
    - Stampe a stdout: equity finale, return %, drawdown, sharpe, sortino, n trade
    - CSV trade log se --log-trades specificato
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import backtrader as bt
import numpy as np

# Importa relativi
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.custom_data import build_feed
from engine.strategy import PatrimonioStrategy
from engine.modules._fundamentals import set_data_root as set_fundamentals_root
from engine.constraints import make_default_constraints


def parse_args():
    p = argparse.ArgumentParser(description="Patrimonio v3 backtest runner")
    p.add_argument('--universe', choices=['portfolio', 'extended'], default='portfolio')
    p.add_argument('--max-tickers', type=int, default=None,
                   help="Limita N ticker (smoke test)")
    p.add_argument('--from', dest='fromdate', type=str, default='2024-08-01',
                   help="Inizio backtest (YYYY-MM-DD)")
    p.add_argument('--to', dest='todate', type=str, default=None,
                   help="Fine backtest (YYYY-MM-DD)")
    p.add_argument('--cash', type=float, default=100_000.0)
    p.add_argument('--commission', type=float, default=0.001,
                   help="Commission rate (es. 0.001 = 10bps)")
    p.add_argument('--threshold', type=float, default=0.20)
    p.add_argument('--min-concordant', type=int, default=3)
    p.add_argument('--max-positions', type=int, default=10)
    p.add_argument('--per-ticker-cap', type=float, default=0.10)
    p.add_argument('--stop-loss', type=float, default=None)
    p.add_argument('--take-profit', type=float, default=None)
    p.add_argument('--trailing', type=float, default=None)
    p.add_argument('--warmup-bars', type=int, default=200)
    # ── Position sizing (Fase 3.1) ──
    p.add_argument('--sizing', choices=['equal', 'vol_target'], default='vol_target',
                   help="Metodo sizing: 'equal' (legacy) o 'vol_target' (default)")
    p.add_argument('--target-risk', type=float, default=0.01,
                   help="Rischio target per trade come %% NAV (default 0.01 = 1%%)")
    p.add_argument('--min-position', type=float, default=0.005,
                   help="Notional minimo per emettere trade come %% NAV (default 0.005)")
    p.add_argument('--vol-floor', type=float, default=0.005,
                   help="Vol floor come %% prezzo per evitare sizing esplosivo (default 0.005)")
    p.add_argument('--vol-proxy', choices=['atr', 'realized'], default='atr',
                   help="Stima vol: 'atr' (default) o 'realized' (std dei returns)")
    p.add_argument('--vol-lookback', type=int, default=14,
                   help="Periodo ATR o lookback realized vol (default 14)")
    # ── Regime-aware exit (Fase 3.2) ──
    p.add_argument('--regime-mode', choices=['off', 'deleveraging', 'full'], default='off',
                   help="Regime VIX: 'off' (legacy), 'deleveraging' (riduce size), "
                        "'full' (size + trailing ATR adattivo). Default 'off'")
    p.add_argument('--vix-ticker', type=str, default='^VIX',
                   help="Simbolo VIX nel data lake (default ^VIX). Vuoto = nessun VIX")
    # ── Portfolio constraints (Fase 3.3) ──
    p.add_argument('--max-sector-pct', type=float, default=None,
                   help="Cap %% NAV per settore (es. 0.30). Default None = disabled")
    p.add_argument('--max-beta', type=float, default=None,
                   help="Cap portfolio beta (es. 1.3). Default None = disabled")
    p.add_argument('--metadata-path', type=str, default='data/meta/sector_beta.parquet',
                   help="Parquet con ticker→sector,beta (default data/meta/sector_beta.parquet)")
    p.add_argument('--violation-policy', choices=['block_new', 'scale_down'], default='block_new',
                   help="Su violazione cap: 'block_new' (skip) o 'scale_down' (riduce size)")
    # ── Pre-screening fundamentals (Strategia B) ──
    p.add_argument('--no-quality-filter', dest='quality_filter_enabled',
                   action='store_false', default=True,
                   help="Disabilita il pre-screening value/quality (default: attivo)")
    p.add_argument('--value-floor', type=float, default=-0.5,
                   help="Soglia minima value_score per passare il filtro (default -0.5)")
    p.add_argument('--quality-floor', type=float, default=-0.5,
                   help="Soglia minima quality_score per passare il filtro (default -0.5)")
    p.add_argument('--log-trades', type=str, default=None,
                   help="Path CSV per dump trade log")
    p.add_argument('--save-trades-csv', dest='save_trades_csv', type=str, default=None,
                   help="Path CSV per dump ledger trade-level dall'analyzer TradeLedger "
                        "(ticker, dt_open, dt_close, bars_held, pnl_net, pnl_pct, status). "
                        "Include sia trade chiusi che snapshot di quelli aperti a fine run. "
                        "Necessario per analisi di concentrazione e falsificazione ipotesi "
                        "few-winners (item consulente maggio 2026).")
    p.add_argument('--equity-csv', type=str, default=None,
                   help="Path CSV per dump equity curve giornaliera")
    p.add_argument('--quantstats-html', type=str, default=None,
                   help="Path HTML per report QuantStats completo")
    p.add_argument('--data-root', type=str, default='data')
    p.add_argument('--verbose', action='store_true')
    return p.parse_args()


def run_backtest(args):
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s | %(message)s',
    )

    # ── Load universe ─────────────────────────────────────────────────────
    loader = DataLakeLoader(data_root=args.data_root)
    # Inizializza root fundamentals per moduli value/quality
    set_fundamentals_root(args.data_root)
    print(f"Data lake summary: {loader.summary()}")

    tickers = loader.list_tickers(args.universe, apply_filters=True)
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
    print(f"\nLoading {len(tickers)} tickers from universe '{args.universe}'...")

    # ── Cerebro setup ─────────────────────────────────────────────────────
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_cash(args.cash)
    cerebro.broker.setcommission(commission=args.commission)

    # Add feeds
    n_added = 0
    for t in tickers:
        bundle = loader.load_ticker(t, args.universe)
        if bundle is None:
            continue
        try:
            feed = build_feed(bundle, fromdate=args.fromdate, todate=args.todate, earnings_window=5)
            cerebro.adddata(feed, name=t)
            n_added += 1
        except Exception as e:
            print(f"  skip {t}: {e}")
    print(f"Feeds added: {n_added}")

    # ── Portfolio constraints (Fase 3.3) ───────────────────────────────
    portfolio_constraints = None
    sector_cap_active = args.max_sector_pct is not None and args.max_sector_pct > 0
    beta_cap_active = args.max_beta is not None and args.max_beta > 0
    if sector_cap_active or beta_cap_active:
        meta_path = Path(args.metadata_path)
        if not meta_path.exists():
            print(f"WARN: metadata file '{meta_path}' non trovato → constraints disabilitati")
            print("      Esegui: python -m engine.fetch_metadata --universe portfolio")
        else:
            portfolio_constraints = make_default_constraints(
                metadata_path=meta_path,
                max_sector_pct=args.max_sector_pct if sector_cap_active else None,
                max_portfolio_beta=args.max_beta if beta_cap_active else None,
                violation_policy=args.violation_policy,
            )
            n_sect = len(portfolio_constraints.sector_map)
            n_beta = sum(1 for b in portfolio_constraints.beta_map.values() if b != 1.0)
            print(f"Constraints loaded: {n_sect} ticker mapped, {n_beta} con beta custom")

    # ── Feed VIX (non-tradable) per regime detection ─────────────────────
    vix_feed_name = args.vix_ticker if (args.vix_ticker and args.regime_mode != 'off') else None
    if vix_feed_name:
        try:
            vix_df = loader.load_benchmark(vix_feed_name)
            # Filtra range coerente con i feed di trading
            if args.fromdate:
                vix_df = vix_df.loc[args.fromdate:]
            if args.todate:
                vix_df = vix_df.loc[:args.todate]
            # Crea feed pandas standard (no eventi/dividendi necessari)
            import pandas as _pd
            vix_bt = bt.feeds.PandasData(
                dataname=vix_df[['open', 'high', 'low', 'close', 'volume']].asfreq('B').ffill(limit=5).dropna(subset=['close'])
            )
            cerebro.adddata(vix_bt, name=vix_feed_name)
            print(f"VIX feed loaded: {vix_feed_name}  range={vix_df.index.min().date()} → {vix_df.index.max().date()}")
        except FileNotFoundError:
            print(f"WARN: VIX feed '{vix_feed_name}' non trovato nel data lake → regime-mode forzato a 'off'")
            args.regime_mode = 'off'
            vix_feed_name = None
        except Exception as e:
            print(f"WARN: errore caricamento VIX feed: {e} → regime-mode forzato a 'off'")
            args.regime_mode = 'off'
            vix_feed_name = None

    if n_added == 0:
        print("ERROR: nessun feed caricato")
        return

    # ── Strategy ──────────────────────────────────────────────────────────
    cerebro.addstrategy(
        PatrimonioStrategy,
        threshold=args.threshold,
        min_concordant=args.min_concordant,
        max_positions=args.max_positions,
        per_ticker_cap=args.per_ticker_cap,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
        trailing_pct=args.trailing,
        warmup_bars=args.warmup_bars,
        verbose=args.verbose,
        quality_filter_enabled=args.quality_filter_enabled,
        value_floor=args.value_floor,
        quality_floor=args.quality_floor,
        sizing_method=args.sizing,
        target_risk_pct=args.target_risk,
        min_position_pct=args.min_position,
        vol_floor_pct=args.vol_floor,
        vol_proxy=args.vol_proxy,
        vol_lookback=args.vol_lookback,
        regime_mode=args.regime_mode,
        vix_feed_name=vix_feed_name,
        portfolio_constraints=portfolio_constraints,
    )

    # ── Analyzers ─────────────────────────────────────────────────────────
    # POST-PATCH bug Sharpe OOS = 1,0000 (maggio 2026, branch v3-quant-framework):
    # rimosso bt.analyzers.SharpeRatio_A per coerenza con wf_runner.py (stesso
    # difetto su finestre corte). Lo Sharpe annualizzato finale viene calcolato
    # a mano via NumPy sul TimeReturn analyzer (ground truth); SharpeRatio
    # standard è mantenuto solo come cross-check.
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name='sharpe_bt',
        riskfreerate=0.0,
        annualize=True,
        timeframe=bt.TimeFrame.Days,
        convertrate=True,
        factor=252,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='dd')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn',
                        timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.Calmar, _name='calmar')
    # Ledger trade-level: necessario per analisi di concentrazione su singoli
    # ticker e falsificazione dell'ipotesi few-winners (item consulente v7 → v8).
    from engine.trade_ledger import TradeLedger
    cerebro.addanalyzer(TradeLedger, _name='ledger')
    # NOTE: AnnualReturn richiede stats.broker observer (non sempre attivo);
    # calcoliamo annual returns manualmente da timereturn (sotto).

    # ── Run ───────────────────────────────────────────────────────────────
    print(f"\nStart cash: {args.cash:,.2f}  commission: {args.commission*100:.2f}%")
    print(f"Period: {args.fromdate} → {args.todate or 'end'}")
    qf_status = 'ON' if args.quality_filter_enabled else 'OFF'
    print(f"Quality filter: {qf_status}  (value_floor={args.value_floor} quality_floor={args.quality_floor})")
    if args.sizing == 'vol_target':
        print(f"Sizing: vol_target  (target_risk={args.target_risk:.2%} "
              f"vol_proxy={args.vol_proxy}({args.vol_lookback}) "
              f"min_position={args.min_position:.2%} vol_floor={args.vol_floor:.2%})")
    else:
        print(f"Sizing: equal_weight (cap={args.per_ticker_cap:.2%} per ticker)")
    if args.regime_mode != 'off':
        print(f"Regime: mode={args.regime_mode}  VIX feed={vix_feed_name}")
    else:
        print("Regime: off (legacy)")
    if portfolio_constraints is not None and (
        portfolio_constraints.sector_cap_enabled or portfolio_constraints.beta_cap_enabled
    ):
        s_cap = f"sector≤{args.max_sector_pct:.0%}" if portfolio_constraints.sector_cap_enabled else "sector=off"
        b_cap = f"beta≤{args.max_beta:.2f}" if portfolio_constraints.beta_cap_enabled else "beta=off"
        print(f"Constraints: {s_cap}  {b_cap}  policy={args.violation_policy}")
    else:
        print("Constraints: off")
    print()

    res = cerebro.run()
    strat = res[0]

    final_value = cerebro.broker.get_value()
    pnl = final_value - args.cash
    ret_pct = pnl / args.cash * 100

    print("\n" + "=" * 60)
    print("BACKTEST RESULT")
    print("=" * 60)
    print(f"Final value:      {final_value:>15,.2f}")
    print(f"P&L:              {pnl:>+15,.2f}  ({ret_pct:+.2f}%)")

    # Sharpe annualizzato — ground truth via NumPy su TimeReturn (post-patch).
    tr_ana = strat.analyzers.timereturn.get_analysis()
    rets = np.array([r for _, r in sorted(tr_ana.items())], dtype=float)
    n_bars = int(rets.size)
    n_nonzero = int(np.count_nonzero(rets))
    std_rets = float(rets.std(ddof=1)) if n_bars >= 2 else 0.0
    if n_bars < 20 or n_nonzero < 10 or std_rets < 1e-8:
        sharpe_a = float('nan')
        sharpe_flag = 'insufficient_window'
    else:
        sharpe_a = float(rets.mean() / std_rets * np.sqrt(252))
        sharpe_flag = 'ok'

    # Cross-check Backtrader (sanity, non usato come metrica primaria).
    sharpe_bt = strat.analyzers.sharpe_bt.get_analysis().get('sharperatio')

    if sharpe_flag == 'ok':
        print(f"Sharpe (annual):  {sharpe_a:>15.3f}  [NumPy ground truth]")
    else:
        print(f"Sharpe (annual):  {'n/a':>15}  [{sharpe_flag}]")
    print(f"  bars OOS:       {n_bars:>15d}")
    print(f"  nonzero rets:   {n_nonzero:>15d}")
    if sharpe_bt is not None:
        print(f"  Sharpe BT (xcheck): {sharpe_bt:>11.3f}")

    # Drawdown
    dd = strat.analyzers.dd.get_analysis()
    print(f"Max drawdown:     {dd.max.drawdown:>15.2f}%  (length={dd.max.len} bars)")

    # Calmar (return / |max DD|)
    calmar = strat.analyzers.calmar.get_analysis()
    calmar_val = None
    if calmar:
        # Calmar è OrderedDict di valori per periodo; prendiamo l'ultimo
        try:
            calmar_val = list(calmar.values())[-1]
        except Exception:
            pass
    if calmar_val is not None and calmar_val == calmar_val:  # not NaN
        print(f"Calmar ratio:     {calmar_val:>15.3f}")

    # SQN
    sqn = strat.analyzers.sqn.get_analysis().get('sqn')
    if sqn is not None:
        print(f"SQN:              {sqn:>15.3f}  (>1.6 = decente, >2 = buono, >3 = ottimo)")

    # Trade analyzer dettagliato
    trades = strat.analyzers.trades.get_analysis()
    n_total = trades.get('total', {}).get('total', 0)
    won = trades.get('won', {}).get('total', 0) or 0
    lost = trades.get('lost', {}).get('total', 0) or 0
    # Pre-screening counter
    n_filt = getattr(strat, 'n_filtered_by_quality', 0)
    if n_filt:
        print(f"Filtered by quality filter: {n_filt} candidati scartati")

    if n_total:
        wr = won / n_total * 100
        print(f"Trades:           {n_total} (won={won}  lost={lost}  win rate={wr:.1f}%)")
        # Profit factor & expectancy
        pnl_won = trades.get('won', {}).get('pnl', {}).get('total', 0) or 0
        pnl_lost = abs(trades.get('lost', {}).get('pnl', {}).get('total', 0) or 0)
        if pnl_lost > 0:
            pf = pnl_won / pnl_lost
            print(f"Profit factor:    {pf:>15.3f}  (>1 profittevole, >2 robusto)")
        avg_won = trades.get('won', {}).get('pnl', {}).get('average', 0) or 0
        avg_lost = trades.get('lost', {}).get('pnl', {}).get('average', 0) or 0
        if won and lost:
            expectancy = (won/n_total) * avg_won + (lost/n_total) * avg_lost
            print(f"Expectancy/trade: {expectancy:>+15,.2f} EUR")
        avg_len_won = trades.get('len', {}).get('won', {}).get('average', 0) or 0
        avg_len_lost = trades.get('len', {}).get('lost', {}).get('average', 0) or 0
        if avg_len_won or avg_len_lost:
            print(f"Avg holding bars: won={avg_len_won:.1f}  lost={avg_len_lost:.1f}")
    else:
        print("Trades:           0 (nessun trade chiuso)")

    # Annual returns calcolati manualmente da TimeReturn daily
    tr_daily = strat.analyzers.timereturn.get_analysis()
    if tr_daily:
        from collections import OrderedDict
        annual = OrderedDict()
        for dt, r in sorted(tr_daily.items()):
            year = dt.year if hasattr(dt, 'year') else int(str(dt)[:4])
            if year not in annual:
                annual[year] = 1.0
            annual[year] *= (1.0 + r)
        if annual:
            print("\nAnnual returns:")
            for year, mult in annual.items():
                print(f"  {year}: {(mult - 1.0) * 100:>+7.2f}%")

    # Equity curve dump
    if args.equity_csv:
        import csv as _csv
        tr = strat.analyzers.timereturn.get_analysis()
        equity = args.cash
        with open(args.equity_csv, 'w', newline='', encoding='utf-8') as f:
            w = _csv.writer(f)
            w.writerow(['date', 'daily_return', 'equity'])
            for dt, r in sorted(tr.items()):
                equity *= (1.0 + r)
                w.writerow([dt.isoformat() if hasattr(dt, 'isoformat') else str(dt),
                            f"{r:.6f}", f"{equity:.2f}"])
        print(f"\nEquity curve → {args.equity_csv}")

    if args.log_trades:
        strat.dump_log(args.log_trades)
        print(f"\nTrade log → {args.log_trades}")

    # Trade-level ledger dump (item consulente v7→v8).
    if args.save_trades_csv:
        import csv as _csv
        ledger_data = strat.analyzers.ledger.get_analysis()
        trades_list = ledger_data.get('trades', [])
        if not trades_list:
            print(f"\nTrade ledger: nessun trade da salvare (n_closed=0)")
        else:
            fieldnames = [
                'ticker', 'dt_open', 'dt_close', 'bars_held',
                'size', 'entry_price', 'notional_open',
                'pnl_gross', 'pnl_net', 'pnl_pct',
                'commission', 'status',
            ]
            with open(args.save_trades_csv, 'w', newline='', encoding='utf-8') as _f:
                _w = _csv.DictWriter(_f, fieldnames=fieldnames)
                _w.writeheader()
                for tr in trades_list:
                    _w.writerow({k: tr.get(k, '') for k in fieldnames})
            print(f"\nTrade ledger CSV → {args.save_trades_csv}  "
                  f"(closed={ledger_data.get('n_closed', 0)}, "
                  f"open_at_end={ledger_data.get('n_open_at_end', 0)})")

    # QuantStats HTML report opzionale
    if args.quantstats_html:
        try:
            import quantstats as qs
            import pandas as pd
            tr = strat.analyzers.timereturn.get_analysis()
            if tr:
                series = pd.Series(
                    {pd.Timestamp(dt): float(r) for dt, r in tr.items()}
                ).sort_index()
                qs.reports.html(series, output=args.quantstats_html, title='Patrimonio v3 backtest')
                print(f"QuantStats HTML  → {args.quantstats_html}")
            else:
                print("QuantStats: timereturn vuoto, skip HTML")
        except ImportError:
            print("QuantStats non installato (pip install quantstats)")
        except Exception as e:
            print(f"QuantStats HTML error: {e}")

    print("=" * 60)


if __name__ == '__main__':
    args = parse_args()
    run_backtest(args)
