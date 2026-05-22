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

# Importa relativi
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.custom_data import build_feed
from engine.strategy import PatrimonioStrategy
from engine.modules._fundamentals import set_data_root as set_fundamentals_root


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
    p.add_argument('--log-trades', type=str, default=None,
                   help="Path CSV per dump trade log")
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
    )

    # ── Analyzers ─────────────────────────────────────────────────────────
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0,
                        annualize=True, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='sharpe_a', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='dd')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn',
                        timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.Calmar, _name='calmar')
    # NOTE: AnnualReturn richiede stats.broker observer (non sempre attivo);
    # calcoliamo annual returns manualmente da timereturn (sotto).

    # ── Run ───────────────────────────────────────────────────────────────
    print(f"\nStart cash: {args.cash:,.2f}  commission: {args.commission*100:.2f}%")
    print(f"Period: {args.fromdate} → {args.todate or 'end'}\n")

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

    # Sharpe (annualizzato dal solo Sharpe analyzer with annualize=True)
    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
    sharpe_a = strat.analyzers.sharpe_a.get_analysis().get('sharperatio')
    if sharpe is not None:
        print(f"Sharpe (annual):  {sharpe:>15.3f}")
    if sharpe_a is not None and sharpe_a != sharpe:
        print(f"Sharpe_A:         {sharpe_a:>15.3f}")

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
