"""
Pre-flight check B2 — 8 trial x 3 fold = 24 backtest (10 min target).

Verifica 3 invarianti su tutti i 24 run:
  I1) first_return del fold == 0.0 (gate Bug 5 robusto su tutti params)
  I2) ledger trade chiusi: dt_open >= fold_start_dt (gate strict)
  I3) ledger open_at_end: dt_open != '' (Bug 4 robusto)

Output: /home/user/workspace/preflight_output.txt + tabella per-trial
Stop: se anche solo 1 trial viola una invariante → STOP, scrivi journal.
"""
import sys
import itertools
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.constraints import load_metadata
from engine.wf_runner import make_backtest_runner

# 8 trial campione: 2 threshold x 2 min_concordant x 2 max_sector_pct
GRID = {
    'threshold': [0.15, 0.25],
    'min_concordant': [2, 3],
    'max_sector_pct': [None, 0.30],
}

FIXED = {
    'max_positions': 10,
    'per_ticker_cap': 0.10,
    'warmup_bars': 50,
    'sizing_method': 'vol_target',
    'min_position_pct': 0.005,
    'vol_floor_pct': 0.005,
    'vol_proxy': 'atr',
    'vol_lookback': 14,
    'quality_filter_enabled': True,
    'value_floor': -0.5,
    'quality_floor': -0.5,
    'verbose': False,
    'target_risk_pct': 0.01,
    'regime_mode': 'off',
    'vix_feed_name': None,
}

FOLDS = {
    'F1_OOS': (datetime(2025, 5, 1), datetime(2025, 8, 1)),
    'F2_OOS': (datetime(2025, 11, 1), datetime(2026, 2, 1)),
    'F3_OOS': (datetime(2026, 2, 1), datetime(2026, 5, 1)),
}

print("=" * 80)
print("PRE-FLIGHT CHECK B2 — 8 trial x 3 fold OOS = 24 backtest")
print("=" * 80)

print("\nCaricamento bundles...")
loader = DataLakeLoader()
tickers = loader.list_tickers('portfolio', apply_filters=True)
bundles = {}
for t in tickers:
    b = loader.load_ticker(t, 'portfolio')
    if b is not None:
        bundles[t] = b
print(f"Bundles: {len(bundles)}/{len(tickers)}")

META_PATH = ROOT / 'data/meta/sector_beta.parquet'
sector_map, beta_map = load_metadata(META_PATH)

runner = make_backtest_runner(
    bundles=bundles,
    tickers=list(bundles.keys()),
    universe='portfolio',
    cash=100_000.0,
    commission=0.001,
    metadata_path=META_PATH,
    sector_map_cache=sector_map,
    beta_map_cache=beta_map,
    fixed_params=FIXED,
    attach_returns=True,
    with_ledger=True,
)

# Genera gli 8 trial
keys = list(GRID.keys())
trial_combos = list(itertools.product(*[GRID[k] for k in keys]))
trials = [dict(zip(keys, combo)) for combo in trial_combos]
print(f"\nTrial generati: {len(trials)}")

violations = []

print("\n" + "─" * 80)
print(f"{'Trial':<22}{'Fold':<8}{'sharpe':>8}{'pnl%':>8}{'tr':>4}{'bars':>5}{'I1':>4}{'I2':>4}{'I3':>4}")
print("─" * 80)

for t_idx, params in enumerate(trials, 1):
    p_short = f"t{params['threshold']}_mc{params['min_concordant']}_sc{params['max_sector_pct']}"
    for fold_label, (start, end) in FOLDS.items():
        metrics, trades = runner(params, start, end)

        # I1: first_return == 0
        i1_pass = True
        i1_val = None
        if metrics.daily_returns:
            i1_val = metrics.daily_returns[0][1]
            i1_pass = (i1_val == 0.0)

        # I2: trade chiusi → dt_open >= fold_start_dt
        fold_start_d = start.date()
        i2_pass = True
        i2_violators = []
        for tr in trades:
            if tr.get('status') != 'closed':
                continue
            dt_str = tr.get('dt_open') or ''
            if not dt_str:
                i2_pass = False
                i2_violators.append((tr['ticker'], 'NaT'))
                continue
            try:
                dt = datetime.fromisoformat(dt_str).date()
                if dt < fold_start_d:
                    i2_pass = False
                    i2_violators.append((tr['ticker'], dt.isoformat()))
            except Exception:
                i2_pass = False
                i2_violators.append((tr['ticker'], 'parse-err'))

        # I3: open_at_end → dt_open != ''
        i3_pass = True
        i3_violators = []
        for tr in trades:
            if tr.get('status') != 'open_at_end':
                continue
            dt_str = tr.get('dt_open') or ''
            if not dt_str:
                i3_pass = False
                i3_violators.append(tr['ticker'])

        tag_i1 = 'OK' if i1_pass else 'FAIL'
        tag_i2 = 'OK' if i2_pass else 'FAIL'
        tag_i3 = 'OK' if i3_pass else 'FAIL'

        sh = metrics.sharpe_a
        pn = metrics.pnl_pct
        tr_count = metrics.trades
        nb = metrics.n_bars
        sh_str = f"{sh:>+7.3f}" if sh == sh else "    NaN"  # NaN check

        print(f"{p_short:<22}{fold_label:<8}{sh_str}{pn:>+8.2f}{tr_count:>4}{nb:>5}{tag_i1:>4}{tag_i2:>4}{tag_i3:>4}")

        if not (i1_pass and i2_pass and i3_pass):
            violations.append({
                'trial': p_short,
                'fold': fold_label,
                'i1': i1_pass,
                'i1_val': i1_val,
                'i2': i2_pass,
                'i2_violators': i2_violators,
                'i3': i3_pass,
                'i3_violators': i3_violators,
            })

print("─" * 80)
n_runs = len(trials) * len(FOLDS)
print(f"\nTotale run: {n_runs}  Violazioni: {len(violations)}")

if violations:
    print("\n" + "!" * 80)
    print("INVARIANTI VIOLATE — STOP")
    print("!" * 80)
    for v in violations:
        print(f"\nTrial {v['trial']} / Fold {v['fold']}:")
        if not v['i1']:
            print(f"  I1 FAIL: first_return = {v['i1_val']} (atteso 0.0)")
        if not v['i2']:
            print(f"  I2 FAIL: closed trades con dt_open < fold_start:")
            for vt in v['i2_violators']:
                print(f"      {vt[0]}: {vt[1]}")
        if not v['i3']:
            print(f"  I3 FAIL: open_at_end senza dt_open:")
            for vt in v['i3_violators']:
                print(f"      {vt}")
else:
    print("\n" + "=" * 80)
    print("✓ TUTTI 24 RUN PASS — invarianti I1+I2+I3 verificate")
    print("  Procedere con full run 864 backtest")
    print("=" * 80)
