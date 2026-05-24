"""
S1.5 diagnostica leggera — BUY candidati pre-cap su F2 OOS per mc=2 e mc=3.

Obiettivo: verificare ipotesi saturazione max_positions=10 sul fold F2 OOS
(2025-11-01 → 2026-02-01) testando due trial con thr=0.05 (massima permissività):
    - mc=2 (sospetto: candidati >> 10 → thr non informativo perché si satura prima)
    - mc=3 (sospetto: candidati ≲ 10 → vincolo opera, ma campione piccolo)

Metrica: a ogni bar, dopo PASS 1 della strategia (raccolta candidati BUY, con
quality filter già applicato, regime check già applicato), prima del PASS 2
(ranking + max_positions + portfolio constraints), conta len(candidates).

Output per ciascun mc: mean / median / p90 / max / min / p25 / p75
del numero giornaliero di candidati pre-cap, e count slot disponibili
(max_positions - n_open) per cross-check sull'effettivo bottleneck.

Approccio: subclass diagnostica di PatrimonioStrategy che intercetta candidates
prima del troncamento. Niente patch al sorgente principale, niente commit del
runtime — solo file output diagnostico.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import backtrader as bt
import numpy as np

# Import quant_v3 modules
HERE = Path(__file__).resolve().parent  # quant_v3/s1_outputs
QUANT_ROOT = HERE.parent                 # quant_v3
sys.path.insert(0, str(QUANT_ROOT))

from engine.data_loader import DataLakeLoader
from engine.custom_data import build_feed
from engine.strategy import PatrimonioStrategy
from engine.modules._fundamentals import set_data_root as set_fundamentals_root


class DiagStrategy(PatrimonioStrategy):
    """Subclass diagnostica: cattura candidates pre-cap per bar."""

    def __init__(self):
        super().__init__()
        self.daily_candidates_pre_cap = []      # list[ (date, n_candidates) ]
        self.daily_open_positions = []          # list[ (date, n_open) ]
        self.daily_slots_available = []         # list[ (date, slots) ]
        self.daily_max_positions = self.p.max_positions

    def next(self):
        # Replicate PASS 1 ourselves to capture pre-cap count, then delegate to super().
        # Approach safer: call super().next() but instrument by snapshot BEFORE super.
        #
        # Problem: super().next() actually builds `candidates` internally as a local
        # variable, we can't intercept easily. Solution: replicate PASS 1 logic here
        # to count, then call super().next() to run the actual trading.
        #
        # Concretamente conto i candidati ESATTAMENTE come fa PASS 1, prima del troncamento.

        # Warmup check identico a super
        if self.bar_count + 1 < self.p.warmup_bars:
            super().next()
            return

        # Conta candidati replicando PASS 1 (senza side effects sui counter principali)
        # NB: regime + quality filter sono identici a super; usiamo gli stessi helper
        # Recupera data corrente (prima dei datas)
        d0 = None
        for d in self.datas:
            if d is not self._vix_feed:
                d0 = d
                break
        if d0 is None:
            super().next()
            return
        try:
            curr_date = d0.datetime.date(0)
        except Exception:
            super().next()
            return

        n_candidates_pre_cap = 0
        n_open = 0
        for d in self.datas:
            if d is self._vix_feed:
                continue
            pos = self.getposition(d)
            if pos.size > 0:
                n_open += 1
                continue  # posizione aperta non è candidato BUY
            # Composite score
            score, diag = self._composite_score(d)
            if score <= 0:
                continue
            # Regime block (off mode → _regime_state può essere None)
            rs = getattr(self, '_regime_state', None)
            if rs is not None and getattr(rs, 'block_new_buys', False):
                continue
            # Quality filter
            if not self._passes_quality_filter(diag):
                continue
            n_candidates_pre_cap += 1

        self.daily_candidates_pre_cap.append((curr_date, n_candidates_pre_cap))
        self.daily_open_positions.append((curr_date, n_open))
        self.daily_slots_available.append(
            (curr_date, max(0, self.p.max_positions - n_open))
        )

        # Ora delega al super per il trading vero (PASS 1 ricostruisce candidates,
        # PASS 2 applica cap)
        super().next()


def run_diagnostic(args):
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s | %(message)s')

    loader = DataLakeLoader(data_root=args.data_root)
    set_fundamentals_root(args.data_root)
    tickers = loader.list_tickers(args.universe, apply_filters=True)
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_cash(args.cash)
    cerebro.broker.setcommission(commission=args.commission)

    n_added = 0
    for t in tickers:
        bundle = loader.load_ticker(t, args.universe)
        if bundle is None:
            continue
        try:
            feed = build_feed(bundle, fromdate=args.fromdate, todate=args.todate,
                              earnings_window=5)
            cerebro.adddata(feed, name=t)
            n_added += 1
        except Exception as e:
            print(f"  skip {t}: {e}")
    print(f"Feeds added: {n_added}  universe={args.universe}  "
          f"window={args.fromdate} → {args.todate}")

    cerebro.addstrategy(
        DiagStrategy,
        threshold=args.threshold,
        min_concordant=args.min_concordant,
        max_positions=args.max_positions,
        per_ticker_cap=args.per_ticker_cap,
        warmup_bars=args.warmup_bars,
        verbose=False,
        regime_mode='off',  # come grid esec 3 default
    )

    results = cerebro.run()
    strat = results[0]
    return strat


def summarize(strat, mc, thr, oos_start, oos_end, max_positions):
    """Estrae statistiche descrittive sui giorni OOS."""
    rows = strat.daily_candidates_pre_cap
    slots = strat.daily_slots_available

    # Filtra solo bar in finestra OOS
    oos_s = datetime.strptime(oos_start, "%Y-%m-%d").date()
    oos_e = datetime.strptime(oos_end, "%Y-%m-%d").date()
    oos_rows = [(d, n) for (d, n) in rows if oos_s <= d < oos_e]
    oos_slots = [(d, n) for (d, n) in slots if oos_s <= d < oos_e]

    counts = np.array([n for (_, n) in oos_rows], dtype=float)
    slots_arr = np.array([n for (_, n) in oos_slots], dtype=float)

    if len(counts) == 0:
        return {
            'mc': mc, 'thr': thr,
            'n_bars_oos': 0,
            'error': 'no_oos_bars',
        }

    summary = {
        'mc': mc,
        'thr': thr,
        'max_positions_cap': max_positions,
        'n_bars_oos': int(len(counts)),
        'candidates_pre_cap': {
            'mean': float(np.mean(counts)),
            'median': float(np.median(counts)),
            'p25': float(np.percentile(counts, 25)),
            'p75': float(np.percentile(counts, 75)),
            'p90': float(np.percentile(counts, 90)),
            'min': float(np.min(counts)),
            'max': float(np.max(counts)),
            'std': float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0,
        },
        'slots_available': {
            'mean': float(np.mean(slots_arr)),
            'median': float(np.median(slots_arr)),
            'min': float(np.min(slots_arr)),
            'max': float(np.max(slots_arr)),
        },
        'n_bars_with_excess': int(np.sum(counts > max_positions)),
        'pct_bars_with_excess': float(np.mean(counts > max_positions) * 100),
        'n_bars_zero_candidates': int(np.sum(counts == 0)),
        'pct_bars_zero_candidates': float(np.mean(counts == 0) * 100),
    }
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', default='data')
    p.add_argument('--universe', default='portfolio')
    p.add_argument('--max-tickers', type=int, default=None)
    # Coerente con wf_runner: feed parte 365 gg prima del fold IS_start per minperiod
    # SMA200 + warmup_bars=50. F2: IS 2024-11-01 → OOS 2025-11-01 → OOS_end 2026-02-01.
    p.add_argument('--fromdate', default='2023-11-01')   # IS_start F2 - 365gg
    p.add_argument('--todate', default='2026-02-01')     # OOS_end F2
    p.add_argument('--oos-start', default='2025-11-01')
    p.add_argument('--oos-end', default='2026-02-01')
    p.add_argument('--cash', type=float, default=100_000.0)
    p.add_argument('--commission', type=float, default=0.001)
    p.add_argument('--thr', type=float, default=0.05)
    p.add_argument('--max-positions', type=int, default=10)
    p.add_argument('--per-ticker-cap', type=float, default=0.10)
    p.add_argument('--warmup-bars', type=int, default=50)
    p.add_argument('--mc-list', default='2,3')
    p.add_argument('--output-json',
                   default='s1_outputs/s15_diag_buy_pre_cap_report.json')
    p.add_argument('--output-csv',
                   default='s1_outputs/s15_diag_buy_pre_cap_daily.csv')
    args = p.parse_args()

    mc_list = [int(x.strip()) for x in args.mc_list.split(',')]
    all_summaries = []
    all_daily_rows = []   # per CSV dettagliato

    for mc in mc_list:
        print(f"\n=== Diagnostica mc={mc} thr={args.thr} ===")
        # Costruisce un namespace argomenti per run_diagnostic
        diag_args = argparse.Namespace(
            data_root=args.data_root,
            universe=args.universe,
            max_tickers=args.max_tickers,
            fromdate=args.fromdate,
            todate=args.todate,
            cash=args.cash,
            commission=args.commission,
            threshold=args.thr,
            min_concordant=mc,
            max_positions=args.max_positions,
            per_ticker_cap=args.per_ticker_cap,
            warmup_bars=args.warmup_bars,
        )
        strat = run_diagnostic(diag_args)
        summary = summarize(
            strat, mc=mc, thr=args.thr,
            oos_start=args.oos_start, oos_end=args.oos_end,
            max_positions=args.max_positions,
        )
        all_summaries.append(summary)
        print(json.dumps(summary, indent=2))

        # Daily rows per CSV
        oos_s = datetime.strptime(args.oos_start, "%Y-%m-%d").date()
        oos_e = datetime.strptime(args.oos_end, "%Y-%m-%d").date()
        for (d, n_cand), (_, n_slots) in zip(strat.daily_candidates_pre_cap,
                                              strat.daily_slots_available):
            if oos_s <= d < oos_e:
                all_daily_rows.append({
                    'date': d.isoformat(),
                    'mc': mc,
                    'thr': args.thr,
                    'candidates_pre_cap': n_cand,
                    'slots_available': n_slots,
                    'max_positions_cap': args.max_positions,
                })

    # Output JSON aggregato
    out = {
        'timestamp_cest': datetime.now().astimezone().isoformat(),
        'window_oos': {'start': args.oos_start, 'end': args.oos_end},
        'universe': args.universe,
        'max_positions_cap': args.max_positions,
        'per_ticker_cap': args.per_ticker_cap,
        'thr': args.thr,
        'summaries': all_summaries,
    }
    out_path = QUANT_ROOT / args.output_json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nJSON output → {out_path}")

    # Output CSV daily
    import csv
    csv_path = QUANT_ROOT / args.output_csv
    if all_daily_rows:
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(all_daily_rows[0].keys()))
            w.writeheader()
            w.writerows(all_daily_rows)
        print(f"CSV daily → {csv_path}")


if __name__ == '__main__':
    main()
