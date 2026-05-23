#!/usr/bin/env python3
"""
Genera lo snapshot Walk-Forward per la dashboard.

Combina:
- wf_full_v3_results.csv (best params + metriche per ogni fold)
- wf_full_v3_stability.json (param_counts, stable_params, aggregati)
- config/active_params.json (active params + meta)

Output: walkforward_snapshot.json — file unico consumato sia da:
- /api/walkforward.py (yahoo-proxy-missere)
- public/walkforward_snapshot.json (patrimonio-missere, statico nel build)

Usage:
    python -m scripts.generate_wf_snapshot
    python -m scripts.generate_wf_snapshot --results wf_full_v3_results.csv
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _safe_float(v) -> float | None:
    """Convert to float or None if NaN/missing."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_str(v) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return str(v)


def build_snapshot(results_csv: Path, stability_json: Path, active_params_json: Path) -> dict:
    """Costruisce lo snapshot completo come dict."""
    df = pd.read_csv(results_csv)
    with stability_json.open() as f:
        stability = json.load(f)
    with active_params_json.open() as f:
        active = json.load(f)

    # Folds detail: 1 record per fold con best params + metriche
    folds = []
    for _, row in df.sort_values('fold_id').iterrows():
        # Helper per leggere colonne opzionali (post-patch bug Sharpe OOS):
        # sui CSV generati prima della patch i campi diagnostici non esistono.
        def _opt_float(col, r=row):
            return _safe_float(r[col]) if col in r.index else None

        def _opt_int(col, r=row):
            return int(r[col]) if col in r.index and not pd.isna(r[col]) else None

        def _opt_str(col, default=None, r=row):
            return _safe_str(r[col]) if col in r.index else default

        folds.append({
            'fold_id': int(row['fold_id']),
            'is_start': _safe_str(row['is_start']),
            'is_end': _safe_str(row['is_end']),
            'oos_start': _safe_str(row['oos_start']),
            'oos_end': _safe_str(row['oos_end']),
            'is_sharpe': _safe_float(row['is_sharpe_a']),
            'oos_sharpe': _safe_float(row['oos_sharpe_a']),
            # POST-PATCH bug Sharpe OOS = 1,0000: campi diagnostici nuovi.
            'is_sharpe_bt': _opt_float('is_sharpe_bt'),
            'oos_sharpe_bt': _opt_float('oos_sharpe_bt'),
            'is_sharpe_flag': _opt_str('is_sharpe_flag', 'ok'),
            'oos_sharpe_flag': _opt_str('oos_sharpe_flag', 'ok'),
            'is_n_bars': _opt_int('is_n_bars'),
            'oos_n_bars': _opt_int('oos_n_bars'),
            'is_n_nonzero_returns': _opt_int('is_n_nonzero_returns'),
            'oos_n_nonzero_returns': _opt_int('oos_n_nonzero_returns'),
            'degradation_ratio': _safe_float(row['degradation_ratio']),
            'overfitting_flag': bool(row['overfitting_flag']),
            'is_pnl_pct': _safe_float(row['is_pnl_pct']),
            'oos_pnl_pct': _safe_float(row['oos_pnl_pct']),
            'is_max_dd_pct': _safe_float(row['is_max_dd']),
            'oos_max_dd_pct': _safe_float(row['oos_max_dd']),
            'is_trades': int(row['is_trades']) if not pd.isna(row['is_trades']) else 0,
            'oos_trades': int(row['oos_trades']) if not pd.isna(row['oos_trades']) else 0,
            'n_combos_evaluated': int(row['n_combos_evaluated']),
            'best_params': {
                'threshold': _safe_float(row['param_threshold']),
                'min_concordant': int(row['param_min_concordant']) if not pd.isna(row['param_min_concordant']) else None,
                'target_risk_pct': _safe_float(row['param_target_risk_pct']),
                'max_sector_pct': _safe_float(row['param_max_sector_pct']),
                'max_portfolio_beta': _safe_float(row['param_max_portfolio_beta']),
            },
        })

    # Param stability: come si distribuiscono i parametri ottimali tra fold
    param_stability = {}
    for pname, counts in stability['param_counts'].items():
        # Trova il valore stabile (max count)
        max_count = max(counts.values())
        winner = max(counts.items(), key=lambda kv: kv[1])
        param_stability[pname] = {
            'distribution': counts,
            'winner_value': winner[0],
            'winner_count': winner[1],
            'total_folds': stability['n_folds'],
            'is_stable': max_count >= stability['stable_threshold'],
            'stability_pct': round(100 * max_count / stability['n_folds'], 1),
        }

    snapshot = {
        '_meta': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'generator': 'quant_v3/scripts/generate_wf_snapshot.py',
            'source_results_csv': results_csv.name,
            'source_stability_json': stability_json.name,
            'validation_commit': active['_meta'].get('validation_commit'),
            'validation_date': active['_meta'].get('validation_date'),
            'data_lake_range': active['_meta'].get('data_lake_range'),
            'next_revalidation_due': active['_meta'].get('next_revalidation_due'),
        },
        'aggregate': {
            'n_folds': stability['n_folds'],
            # POST-PATCH bug Sharpe OOS = 1,0000: campi diagnostici aggregati.
            'n_folds_valid': stability.get('n_folds_valid', stability['n_folds']),
            'n_folds_insufficient_is': stability.get('n_folds_insufficient_is', 0),
            'n_folds_insufficient_oos': stability.get('n_folds_insufficient_oos', 0),
            'is_sharpe_mean': _safe_float(stability['is_sharpe_mean']),
            'oos_sharpe_mean': _safe_float(stability['oos_sharpe_mean']),
            'degradation_mean': _safe_float(stability['degradation_mean']),
            'overfitting_count': stability['overfitting_count'],
            'overfitting_pct': round(100 * stability['overfitting_count'] / stability['n_folds'], 1),
            'stability_level': active['stability_summary'].get('stability_level', 'unknown'),
        },
        'active_params': {
            pname: {
                'value': pdata['value'],
                'confidence': pdata['confidence'],
                'stable_in_folds': pdata.get('stable_in_folds'),
                'total_folds': pdata.get('total_folds'),
                'note': pdata.get('note', ''),
            }
            for pname, pdata in active['params'].items()
        },
        'param_stability': param_stability,
        'folds': folds,
    }
    return snapshot


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--results', type=Path, default=Path('wf_full_v3_results.csv'))
    p.add_argument('--stability', type=Path, default=Path('wf_full_v3_stability.json'))
    p.add_argument('--active-params', type=Path, default=Path('config/active_params.json'))
    p.add_argument('--output', type=Path, default=Path('walkforward_snapshot.json'))
    args = p.parse_args()

    # Risolvi relative paths dal dir dello script
    base = Path(__file__).parent.parent  # quant_v3/
    results = base / args.results if not args.results.is_absolute() else args.results
    stability = base / args.stability if not args.stability.is_absolute() else args.stability
    active = base / args.active_params if not args.active_params.is_absolute() else args.active_params
    output = base / args.output if not args.output.is_absolute() else args.output

    print(f"[generate_wf_snapshot] Reading {results.name}")
    print(f"[generate_wf_snapshot] Reading {stability.name}")
    print(f"[generate_wf_snapshot] Reading {active.name}")

    snap = build_snapshot(results, stability, active)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w') as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)

    print(f"[generate_wf_snapshot] ✓ Written {output} ({output.stat().st_size} bytes)")
    agg = snap['aggregate']
    print(f"  Folds: {agg['n_folds']}  (valid={agg.get('n_folds_valid')}, "
          f"insufficient OOS={agg.get('n_folds_insufficient_oos')})")

    def _fmt(v):
        return f"{v:.3f}" if isinstance(v, (int, float)) and v == v else 'n/a'

    print(f"  IS Sharpe mean:  {_fmt(agg['is_sharpe_mean'])}")
    print(f"  OOS Sharpe mean: {_fmt(agg['oos_sharpe_mean'])}")
    print(f"  Degradation:    {_fmt(agg['degradation_mean'])}")
    print(f"  Overfitting: {agg['overfitting_count']}/{agg['n_folds']}")


if __name__ == '__main__':
    main()
