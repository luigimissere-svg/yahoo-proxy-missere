"""
Step 0 audit — verifica empirica L4.V2.

Confronta `make_backtest_runner` vs `make_ledger_runner` sui best_params di F3
(che ha max_sector_pct=0.3, copre tutte le features). Esegue IS + OOS.

Atteso (se L4.V2 è bug attivo):
- runner.sharpe_a != ledger.sharpe_a (perché runner filtra warmup, ledger no)
  → conferma bug 7 era già attivo nelle pubblicazioni v7.2

Atteso (se L4.V2 è dormiente):
- runner.sharpe_a == ledger.sharpe_a (entrambi senza filtro warmup nel codice attuale)
  → bug 7 è solo manutenibilità, non ha contaminato v7.2

Confronto: tolleranza 1e-6 su sharpe_a, pnl_pct, trades.
"""
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.constraints import load_metadata
from engine.wf_runner import make_backtest_runner, make_ledger_runner

# best_params F3 v7.3
PARAMS = {
    'threshold': 0.25,
    'min_concordant': 2,
    'target_risk_pct': 0.008,
    'max_sector_pct': 0.30,
    'max_portfolio_beta': None,
}

# Fixed params identici a wf_runner.main() linea 610-627
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
    'F3_IS': (datetime(2025, 2, 1), datetime(2026, 2, 1)),
    'F3_OOS': (datetime(2026, 2, 1), datetime(2026, 5, 1)),
}

print("=" * 80)
print("STEP 0 — runner vs ledger Sharpe consistency check")
print("=" * 80)

# Setup dati
print("\nCaricamento bundles...")
loader = DataLakeLoader()
tickers = loader.list_tickers('portfolio', apply_filters=True)
bundles = {}
for t in tickers:
    b = loader.load_ticker(t, 'portfolio')
    if b is not None:
        bundles[t] = b
print(f"Bundles caricati: {len(bundles)}/{len(tickers)}")

META_PATH = ROOT / 'data/meta/sector_beta.parquet'
sector_map, beta_map = load_metadata(META_PATH)
print(f"Metadata: sector_map={len(sector_map)} beta_map={len(beta_map)}")

# Factory
print("\nIstanzio le due factory...")
runner_fn = make_backtest_runner(
    bundles=bundles,
    tickers=list(bundles.keys()),
    universe='portfolio',
    cash=100_000.0,
    commission=0.001,
    metadata_path=META_PATH,
    sector_map_cache=sector_map,
    beta_map_cache=beta_map,
    fixed_params=FIXED,
    attach_returns=True,  # come è attivo nel full run
)
ledger_fn = make_ledger_runner(
    bundles=bundles,
    tickers=list(bundles.keys()),
    cash=100_000.0,
    commission=0.001,
    sector_map_cache=sector_map,
    beta_map_cache=beta_map,
    fixed_params=FIXED,
)

# Run + confronto
print("\n" + "─" * 80)
print(f"{'Fold':<10} {'sharpe_a':<22} {'pnl_pct':<22} {'trades':<14} {'n_bars':<10} {'match':<6}")
print(f"{'':<10} {'runner | ledger | Δ':<22} {'runner | ledger | Δ':<22} {'r | l | Δ':<14} {'r | l':<10}")
print("─" * 80)

results = []
for label, (start, end) in FOLDS.items():
    r_metrics = runner_fn(PARAMS, start, end)
    l_metrics, l_trades = ledger_fn(PARAMS, start, end)

    d_sharpe = r_metrics.sharpe_a - l_metrics.sharpe_a
    d_pnl = r_metrics.pnl_pct - l_metrics.pnl_pct
    d_trades = r_metrics.trades - l_metrics.trades
    match = abs(d_sharpe) < 1e-6 and abs(d_pnl) < 1e-4 and d_trades == 0

    print(
        f"{label:<10} "
        f"{r_metrics.sharpe_a:>7.4f}|{l_metrics.sharpe_a:>6.4f}|{d_sharpe:>+.1e} "
        f"{r_metrics.pnl_pct:>7.3f}|{l_metrics.pnl_pct:>6.3f}|{d_pnl:>+.1e} "
        f"{r_metrics.trades:>3d}|{l_metrics.trades:>3d}|{d_trades:>+3d}     "
        f"{r_metrics.n_bars:>3d}|{l_metrics.n_bars:>3d}  "
        f"{'OK' if match else 'FAIL'}"
    )
    results.append((label, match, d_sharpe, d_pnl, d_trades, r_metrics, l_metrics))

print("─" * 80)
n_match = sum(1 for r in results if r[1])
print(f"\nMatch: {n_match}/{len(results)} fold")

if n_match == len(results):
    print("\n✓ Bug 7 è DORMIENTE: runner e ledger producono metriche identiche.")
    print("  Significato: la duplicazione factory è solo code smell, non ha contaminato v7.2.")
    print("  Patch bug 7 (refactor wrapper) resta utile per evitare divergenze future.")
else:
    print("\n✗ Bug 7 è ATTIVO: runner e ledger divergono.")
    print("  Significato: alcune pubblicazioni v7.2 sono su factory diverse → metriche inconsistenti.")
    print("  Va segnalato nel paper v7.3 come scoperta accidentale dell'audit.")
    print("\n  Dettaglio divergenze:")
    for label, match, d_sharpe, d_pnl, d_trades, rm, lm in results:
        if not match:
            print(f"    {label}: Δsharpe={d_sharpe:+.6f} Δpnl={d_pnl:+.4f} Δtrades={d_trades:+d}")
            print(f"      runner: n_bars={rm.n_bars} n_nonzero={rm.n_nonzero_returns}")
            print(f"      ledger: n_bars={lm.n_bars} n_nonzero={lm.n_nonzero_returns}")
