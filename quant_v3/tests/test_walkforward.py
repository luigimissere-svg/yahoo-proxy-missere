"""Test walk-forward framework — Fase 4."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine.walkforward import (
    Fold,
    FoldResult,
    RunMetrics,
    _add_months,
    aggregate_stability,
    expand_grid,
    generate_folds,
    results_to_csv_rows,
    run_walkforward,
    select_best_params,
)


# ─── _add_months ─────────────────────────────────────────────────────────────

def test_add_months_simple():
    assert _add_months(datetime(2024, 8, 1), 3) == datetime(2024, 11, 1)


def test_add_months_year_rollover():
    assert _add_months(datetime(2024, 11, 1), 3) == datetime(2025, 2, 1)


def test_add_months_clamp_to_month_end():
    # 31 gennaio + 1 mese → 28/29 febbraio
    assert _add_months(datetime(2025, 1, 31), 1) == datetime(2025, 2, 28)
    # anno bisestile
    assert _add_months(datetime(2024, 1, 31), 1) == datetime(2024, 2, 29)


def test_add_months_zero():
    assert _add_months(datetime(2024, 8, 1), 0) == datetime(2024, 8, 1)


# ─── generate_folds ──────────────────────────────────────────────────────────

def test_generate_folds_basic():
    folds = generate_folds(
        start=datetime(2024, 8, 1),
        end=datetime(2026, 5, 1),
        is_months=12,
        oos_months=3,
        step_months=3,
    )
    # 22 mesi - 12 IS - 3 OOS = 7 mesi residui → 7/3 = 2 step in più → 3 fold
    # Verifichiamo che ci siano almeno 3 fold
    assert len(folds) >= 3
    # F1: IS 2024-08→2025-08 OOS 2025-08→2025-11
    f1 = folds[0]
    assert f1.fold_id == 1
    assert f1.is_start == datetime(2024, 8, 1)
    assert f1.is_end == datetime(2025, 8, 1)
    assert f1.oos_start == datetime(2025, 8, 1)
    assert f1.oos_end == datetime(2025, 11, 1)


def test_generate_folds_count_full_period():
    """24 mesi (2024-08 → 2026-08) con 12IS/3OOS/3step → 4 fold."""
    folds = generate_folds(
        start=datetime(2024, 8, 1),
        end=datetime(2026, 8, 1),
        is_months=12,
        oos_months=3,
        step_months=3,
    )
    assert len(folds) == 4
    # F4 deve avere oos_end <= end
    for f in folds:
        assert f.oos_end <= datetime(2026, 8, 1)


def test_generate_folds_rolling_window():
    folds = generate_folds(
        start=datetime(2024, 8, 1),
        end=datetime(2026, 8, 1),
        is_months=12,
        oos_months=3,
        step_months=3,
    )
    # Check step coerente
    for i in range(1, len(folds)):
        delta = (folds[i].is_start - folds[i-1].is_start).days
        # ~3 mesi = 89-92 giorni
        assert 89 <= delta <= 92


def test_generate_folds_too_short_raises():
    with pytest.raises(ValueError, match="troppo corto"):
        generate_folds(
            start=datetime(2024, 8, 1),
            end=datetime(2024, 12, 1),
            is_months=12,
            oos_months=3,
        )


def test_generate_folds_invalid_args():
    with pytest.raises(ValueError):
        generate_folds(datetime(2024, 8, 1), datetime(2026, 5, 1), is_months=0)
    with pytest.raises(ValueError):
        generate_folds(datetime(2026, 5, 1), datetime(2024, 8, 1))  # start > end


def test_generate_folds_ids_sequential():
    folds = generate_folds(
        datetime(2024, 8, 1), datetime(2026, 8, 1),
        is_months=12, oos_months=3, step_months=3,
    )
    assert [f.fold_id for f in folds] == list(range(1, len(folds) + 1))


def test_fold_str():
    f = Fold(1, datetime(2024, 8, 1), datetime(2025, 8, 1),
             datetime(2025, 8, 1), datetime(2025, 11, 1))
    s = str(f)
    assert "F1" in s
    assert "2024-08-01" in s


# ─── expand_grid ─────────────────────────────────────────────────────────────

def test_expand_grid_basic():
    grid = {'a': [1, 2], 'b': [10, 20]}
    combos = expand_grid(grid)
    assert len(combos) == 4
    assert {'a': 1, 'b': 10} in combos
    assert {'a': 2, 'b': 20} in combos


def test_expand_grid_single_param():
    combos = expand_grid({'threshold': [0.15, 0.20, 0.25]})
    assert len(combos) == 3


def test_expand_grid_empty_returns_one_empty_combo():
    assert expand_grid({}) == [{}]


def test_expand_grid_with_none_values():
    combos = expand_grid({'max_sector_pct': [None, 0.30]})
    assert {'max_sector_pct': None} in combos
    assert {'max_sector_pct': 0.30} in combos


def test_expand_grid_full_size():
    """Verifica griglia full 72 combo."""
    grid = {
        'threshold': [0.15, 0.20, 0.25],
        'min_concordant': [2, 3],
        'target_risk_pct': [0.008, 0.010, 0.012],
        'max_sector_pct': [None, 0.30],
        'max_portfolio_beta': [None, 1.3],
    }
    assert len(expand_grid(grid)) == 72


# ─── select_best_params ──────────────────────────────────────────────────────

def test_select_best_params_simple():
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, 1.0, 10.0, 5.0, 10, 110000)),
        ({'threshold': 0.20}, RunMetrics(0, 2.0, 20.0, 4.0, 10, 120000)),
        ({'threshold': 0.25}, RunMetrics(0, 1.5, 15.0, 4.5, 10, 115000)),
    ]
    best_params, best_metrics, n_skipped = select_best_params(is_results, min_trades=5)
    assert best_params == {'threshold': 0.20}
    assert best_metrics.sharpe_a == 2.0
    assert n_skipped == 0


def test_select_best_params_min_trades_filter():
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, 5.0, 50.0, 2.0, 2, 150000)),  # 2 trade → skip
        ({'threshold': 0.20}, RunMetrics(0, 1.0, 10.0, 5.0, 10, 110000)),  # 10 trade ok
    ]
    best_params, best_metrics, n_skipped = select_best_params(is_results, min_trades=5)
    assert best_params == {'threshold': 0.20}
    assert best_metrics.sharpe_a == 1.0
    assert n_skipped == 1


def test_select_best_params_all_skipped_returns_none():
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, 5.0, 50.0, 2.0, 2, 150000)),
        ({'threshold': 0.20}, RunMetrics(0, 4.0, 40.0, 3.0, 3, 140000)),
    ]
    best_params, best_metrics, n_skipped = select_best_params(is_results, min_trades=5)
    assert best_params is None
    assert best_metrics is None
    assert n_skipped == 2


def test_select_best_params_tie_break_threshold():
    """A parità di sharpe entro 5%, vince threshold più alto."""
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, 2.00, 10.0, 5.0, 10, 110000)),
        ({'threshold': 0.20}, RunMetrics(0, 1.98, 10.0, 5.0, 10, 110000)),  # ~ -1% → tie
        ({'threshold': 0.25}, RunMetrics(0, 1.95, 10.0, 5.0, 10, 110000)),  # ~ -2.5% → tie
    ]
    best_params, _, _ = select_best_params(is_results, min_trades=5, tie_break_pct=0.05)
    # tutti entro 5% → vince threshold più alto = 0.25
    assert best_params == {'threshold': 0.25}


def test_select_best_params_no_tie_when_gap_large():
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, 2.00, 10.0, 5.0, 10, 110000)),
        ({'threshold': 0.20}, RunMetrics(0, 1.50, 10.0, 5.0, 10, 110000)),  # -25% gap
        ({'threshold': 0.25}, RunMetrics(0, 1.00, 10.0, 5.0, 10, 110000)),
    ]
    best_params, _, _ = select_best_params(is_results, min_trades=5, tie_break_pct=0.05)
    assert best_params == {'threshold': 0.15}  # no tie, vince sharpe max


def test_select_best_params_negative_sharpe_no_tie_break():
    """Con sharpe negativo, salta il tie-break (non significativo)."""
    is_results = [
        ({'threshold': 0.15}, RunMetrics(0, -1.0, -10.0, 5.0, 10, 90000)),
        ({'threshold': 0.20}, RunMetrics(0, -0.5, -5.0, 5.0, 10, 95000)),
        ({'threshold': 0.25}, RunMetrics(0, -2.0, -20.0, 5.0, 10, 80000)),
    ]
    best_params, _, _ = select_best_params(is_results, min_trades=5)
    assert best_params == {'threshold': 0.20}  # max sharpe (meno negativo)


# ─── FoldResult ──────────────────────────────────────────────────────────────

def _make_fold_result(fold_id: int, is_sharpe: float, oos_sharpe: float,
                     best_params: dict = None) -> FoldResult:
    return FoldResult(
        fold_id=fold_id,
        is_start='2024-08-01',
        is_end='2025-08-01',
        oos_start='2025-08-01',
        oos_end='2025-11-01',
        best_params=best_params or {'threshold': 0.20},
        is_metrics=RunMetrics(0, is_sharpe, 10.0, 5.0, 10, 110000),
        oos_metrics=RunMetrics(0, oos_sharpe, 8.0, 6.0, 5, 108000),
        n_combos_evaluated=8,
        n_combos_skipped_min_trades=0,
    )


def test_fold_result_degradation_ratio():
    r = _make_fold_result(1, is_sharpe=2.0, oos_sharpe=1.0)
    assert r.degradation_ratio == 0.5


def test_fold_result_degradation_zero_is_sharpe():
    r = _make_fold_result(1, is_sharpe=0.0, oos_sharpe=1.0)
    assert r.degradation_ratio == 0.0


def test_fold_result_overfitting_flag_true():
    r = _make_fold_result(1, is_sharpe=2.0, oos_sharpe=0.5)  # 0.25 < 0.3
    assert r.overfitting_flag is True


def test_fold_result_overfitting_flag_false():
    r = _make_fold_result(1, is_sharpe=2.0, oos_sharpe=1.5)  # 0.75 >= 0.3
    assert r.overfitting_flag is False


def test_fold_result_overfitting_skip_when_is_negative():
    """Se IS è già negativo, no overfitting (sistema fallito a monte)."""
    r = _make_fold_result(1, is_sharpe=-1.0, oos_sharpe=-2.0)
    assert r.overfitting_flag is False


# ─── aggregate_stability ─────────────────────────────────────────────────────

def test_aggregate_stability_empty():
    s = aggregate_stability([], stable_threshold=3)
    assert s['n_folds'] == 0
    assert s['stable_params'] == {}


def test_aggregate_stability_basic():
    results = [
        _make_fold_result(1, 2.0, 1.5, {'threshold': 0.20, 'min_concordant': 3}),
        _make_fold_result(2, 1.8, 1.6, {'threshold': 0.20, 'min_concordant': 3}),
        _make_fold_result(3, 2.2, 1.7, {'threshold': 0.20, 'min_concordant': 3}),
        _make_fold_result(4, 1.5, 1.0, {'threshold': 0.25, 'min_concordant': 2}),
    ]
    s = aggregate_stability(results, stable_threshold=3)
    assert s['n_folds'] == 4
    # threshold=0.20 vincente in 3/4 → stabile
    # min_concordant=3 vincente in 3/4 → stabile
    assert s['stable_params'].get('threshold') == 0.20
    assert s['stable_params'].get('min_concordant') == 3


def test_aggregate_stability_no_stable_param():
    """Nessun valore ricorrente 3+ volte → stable_params vuoto."""
    results = [
        _make_fold_result(1, 2.0, 1.0, {'threshold': 0.15}),
        _make_fold_result(2, 2.0, 1.0, {'threshold': 0.20}),
        _make_fold_result(3, 2.0, 1.0, {'threshold': 0.25}),
        _make_fold_result(4, 2.0, 1.0, {'threshold': 0.15}),
    ]
    s = aggregate_stability(results, stable_threshold=3)
    # Massimo conteggio è 2 (threshold=0.15) → nessuno stabile
    assert s['stable_params'] == {}


def test_aggregate_stability_metrics_means():
    results = [
        _make_fold_result(1, 2.0, 1.0),
        _make_fold_result(2, 4.0, 3.0),
    ]
    s = aggregate_stability(results)
    assert s['is_sharpe_mean'] == 3.0
    assert s['oos_sharpe_mean'] == 2.0


def test_aggregate_stability_overfitting_count():
    results = [
        _make_fold_result(1, 2.0, 0.5),   # ratio 0.25 < 0.3 → overfit
        _make_fold_result(2, 2.0, 1.5),   # ratio 0.75 ok
        _make_fold_result(3, 2.0, 0.4),   # ratio 0.20 < 0.3 → overfit
    ]
    s = aggregate_stability(results)
    assert s['overfitting_count'] == 2


def test_aggregate_stability_none_values_serializable():
    """Param value None deve essere gestito senza errori."""
    results = [
        _make_fold_result(1, 2.0, 1.5, {'max_sector_pct': None}),
        _make_fold_result(2, 2.0, 1.5, {'max_sector_pct': 0.30}),
        _make_fold_result(3, 2.0, 1.5, {'max_sector_pct': None}),
    ]
    s = aggregate_stability(results, stable_threshold=2)
    counts = s['param_counts']['max_sector_pct']
    assert counts[None] == 2
    assert counts[0.30] == 1
    assert s['stable_params'].get('max_sector_pct') is None


# ─── run_walkforward end-to-end (con run_backtest mock) ──────────────────────

def test_run_walkforward_end_to_end():
    """Test integrazione con mock callback deterministico."""
    folds = [
        Fold(1, datetime(2024, 8, 1), datetime(2025, 8, 1),
             datetime(2025, 8, 1), datetime(2025, 11, 1)),
        Fold(2, datetime(2024, 11, 1), datetime(2025, 11, 1),
             datetime(2025, 11, 1), datetime(2026, 2, 1)),
    ]
    grid = {'threshold': [0.15, 0.25], 'min_concordant': [2, 3]}

    def mock_run(params, start, end):
        # threshold 0.25 + min_concordant 3 vince sempre con sharpe alto
        is_oos = (end - start).days < 200  # IS è ~365gg, OOS ~90gg
        base = 2.0 if (params['threshold'] == 0.25 and params['min_concordant'] == 3) else 1.0
        # OOS un po' peggio di IS
        sharpe = base * 0.8 if is_oos else base
        return RunMetrics(0, sharpe, 10.0, 5.0, 10, 110000)

    results = run_walkforward(folds, grid, mock_run, min_trades_per_fold=5, verbose=False)
    assert len(results) == 2
    for r in results:
        assert r.best_params == {'threshold': 0.25, 'min_concordant': 3}
        # IS sharpe = 2.0, OOS = 1.6 → degradation 0.8 → no overfit
        assert r.is_metrics.sharpe_a == 2.0
        assert r.oos_metrics.sharpe_a == pytest.approx(1.6)
        assert r.overfitting_flag is False


def test_run_walkforward_skipped_fold_when_no_valid_combo():
    """Tutti combo < min_trades → fold scartato."""
    folds = [
        Fold(1, datetime(2024, 8, 1), datetime(2025, 8, 1),
             datetime(2025, 8, 1), datetime(2025, 11, 1)),
    ]
    grid = {'threshold': [0.15, 0.25]}

    def mock_run(params, start, end):
        return RunMetrics(0, 2.0, 10.0, 5.0, 2, 110000)  # solo 2 trade

    results = run_walkforward(folds, grid, mock_run, min_trades_per_fold=5, verbose=False)
    assert results == []


def test_run_walkforward_handles_exception():
    """Se callback solleva eccezione, run è considerato fallito (Sharpe=0)."""
    folds = [
        Fold(1, datetime(2024, 8, 1), datetime(2025, 8, 1),
             datetime(2025, 8, 1), datetime(2025, 11, 1)),
    ]
    grid = {'threshold': [0.15, 0.25]}
    call_count = [0]

    def mock_run(params, start, end):
        call_count[0] += 1
        if params['threshold'] == 0.15:
            raise RuntimeError("synthetic failure")
        return RunMetrics(0, 1.0, 10.0, 5.0, 10, 110000)

    results = run_walkforward(folds, grid, mock_run, min_trades_per_fold=5, verbose=False)
    assert len(results) == 1
    # vince comunque 0.25 perché 0.15 ha sollevato (RunMetrics.empty → sharpe 0 + 0 trade → skipped)
    assert results[0].best_params == {'threshold': 0.25}


# ─── CSV serialization ───────────────────────────────────────────────────────

def test_results_to_csv_rows():
    results = [
        _make_fold_result(1, 2.0, 1.5, {'threshold': 0.20, 'max_sector_pct': 0.30}),
        _make_fold_result(2, 1.8, 1.0, {'threshold': 0.25, 'max_sector_pct': None}),
    ]
    rows = results_to_csv_rows(results)
    assert len(rows) == 2
    assert rows[0]['fold_id'] == 1
    assert rows[0]['param_threshold'] == 0.20
    assert rows[0]['param_max_sector_pct'] == 0.30
    assert rows[1]['param_max_sector_pct'] is None
    assert rows[0]['degradation_ratio'] == 0.75
    assert rows[0]['overfitting_flag'] is False
