"""
S1.7 — Selettore robusto median-fold-OOS v8.

Pre-registrazione: preregistration_s1_v8.md §S1.7
Versione sigillata: v8.s1.7

Problema risolto:
  Il selettore v7.4 (`select_best_params`) sceglie best params su IS
  Sharpe del SINGOLO fold. Quando la grid produce plateau IS (Sharpe
  identico tra trial), il tie-break su threshold è arbitrario e
  porta a overfitting selettore (journal_f3_selector_overfitting.md).
  In v7.4 questo selettore ha sbagliato in 3/3 fold (mc=2 OOS sarebbe
  stato meglio in F1+F2; mc=3 OOS sarebbe stato meglio in F3).

Soluzione v8:
  Per ogni combinazione di parametri, raccoglie lo Sharpe OOS in
  TUTTI i fold (richiede walk-forward completo). Seleziona la combo
  con il MASSIMO della MEDIANA cross-fold dello Sharpe OOS.
  Tie-break secondario: massimo del MIN cross-fold (worst-case).
  Tie-break terziario: minimo della VAR cross-fold (stabilità).

Vincoli aggiuntivi v8:
  - min_tickers (default 20): se cap notional 5% (S1.3),
    serve almeno 20 ticker distinti per fold OOS per non avere
    cap notional cosmetico. Combo con < min_tickers in qualsiasi
    fold sono ESCLUSE.
  - min_trades (default 10): legacy filter da v7.4.
  - sharpe_flag == 'ok' su tutti i fold OOS.

Implementazione no look-ahead:
  Il selettore opera su risultati OOS aggregati DOPO che tutti i fold
  sono stati eseguiti. La scelta finale di parametri è UNICA per
  l'intero walk-forward (no rolling re-selection per fold). Questo
  rispetta no look-ahead perché il selettore non vede il futuro
  durante il training del singolo fold; la selezione è una decisione
  di MODELLO globale post-WF, non un parametro adattivo.

NOTA CRITICA:
  In modalità "deployment" (paper/live trading) si usano i parametri
  selezionati dal WF storico, applicati uniformemente. Il selettore
  median-fold-OOS NON è un mechanism di trading — è un mechanism di
  validazione/selezione del modello finale.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, variance
from typing import Any, Dict, List, Optional, Sequence, Tuple


SEALED_VERSION: str = "v8.s1.7"
DEFAULT_MIN_TICKERS: int = 20
DEFAULT_MIN_TRADES: int = 10


@dataclass(frozen=True)
class FoldOOSPerf:
    """Performance OOS di un fold per una specifica combinazione di parametri."""

    fold_id: int
    params_key: str  # stringa canonical dei parametri (per merge)
    sharpe_oos: float
    pnl_pct_oos: float
    n_trades: int
    n_tickers: int
    sharpe_flag: str  # 'ok', 'warmup', etc.


@dataclass(frozen=True)
class ComboAggregate:
    """Aggregato cross-fold per una combinazione."""

    params_key: str
    n_folds: int
    sharpe_median: float
    sharpe_min: float
    sharpe_max: float
    sharpe_var: float
    pnl_median: float
    excluded: bool
    exclusion_reason: str = ""


def _canonical_key(params: Dict[str, Any]) -> str:
    """Chiave canonical dei parametri ordinata."""
    return "|".join(f"{k}={params[k]}" for k in sorted(params.keys()))


def aggregate_cross_fold(
    perfs: Sequence[FoldOOSPerf],
    min_tickers: int = DEFAULT_MIN_TICKERS,
    min_trades: int = DEFAULT_MIN_TRADES,
    expected_n_folds: Optional[int] = None,
) -> List[ComboAggregate]:
    """Raggruppa per params_key e calcola statistiche cross-fold OOS.
    Esclude combo che non soddisfano min_tickers/min_trades/sharpe_flag
    in QUALSIASI fold (filtro AND).
    """
    by_key: Dict[str, List[FoldOOSPerf]] = {}
    for p in perfs:
        by_key.setdefault(p.params_key, []).append(p)

    out: List[ComboAggregate] = []
    for key, fold_perfs in by_key.items():
        n = len(fold_perfs)
        if expected_n_folds is not None and n != expected_n_folds:
            out.append(
                ComboAggregate(
                    params_key=key,
                    n_folds=n,
                    sharpe_median=float("nan"),
                    sharpe_min=float("nan"),
                    sharpe_max=float("nan"),
                    sharpe_var=float("nan"),
                    pnl_median=float("nan"),
                    excluded=True,
                    exclusion_reason=f"fold incompleti: {n}/{expected_n_folds}",
                )
            )
            continue

        # Filtri qualitativi su ogni fold
        bad_tickers = [fp for fp in fold_perfs if fp.n_tickers < min_tickers]
        bad_trades = [fp for fp in fold_perfs if fp.n_trades < min_trades]
        bad_flag = [fp for fp in fold_perfs if fp.sharpe_flag != "ok"]

        if bad_tickers or bad_trades or bad_flag:
            reasons = []
            if bad_tickers:
                reasons.append(
                    f"min_tickers<{min_tickers} in fold "
                    f"{[fp.fold_id for fp in bad_tickers]}"
                )
            if bad_trades:
                reasons.append(
                    f"min_trades<{min_trades} in fold "
                    f"{[fp.fold_id for fp in bad_trades]}"
                )
            if bad_flag:
                reasons.append(
                    f"sharpe_flag!=ok in fold "
                    f"{[(fp.fold_id, fp.sharpe_flag) for fp in bad_flag]}"
                )
            out.append(
                ComboAggregate(
                    params_key=key,
                    n_folds=n,
                    sharpe_median=float("nan"),
                    sharpe_min=float("nan"),
                    sharpe_max=float("nan"),
                    sharpe_var=float("nan"),
                    pnl_median=float("nan"),
                    excluded=True,
                    exclusion_reason="; ".join(reasons),
                )
            )
            continue

        sharpes = [fp.sharpe_oos for fp in fold_perfs]
        pnls = [fp.pnl_pct_oos for fp in fold_perfs]
        out.append(
            ComboAggregate(
                params_key=key,
                n_folds=n,
                sharpe_median=median(sharpes),
                sharpe_min=min(sharpes),
                sharpe_max=max(sharpes),
                sharpe_var=variance(sharpes) if len(sharpes) > 1 else 0.0,
                pnl_median=median(pnls),
                excluded=False,
            )
        )
    return out


def select_median_fold_oos(
    aggregates: Sequence[ComboAggregate],
) -> Optional[ComboAggregate]:
    """Seleziona la combo con MAX(median Sharpe OOS).
    Tie-break: MAX(min Sharpe OOS) → MIN(variance Sharpe OOS).
    Esclude combo con `excluded=True`.
    """
    valid = [a for a in aggregates if not a.excluded]
    if not valid:
        return None

    valid.sort(
        key=lambda a: (
            -a.sharpe_median,
            -a.sharpe_min,
            a.sharpe_var,
        )
    )
    return valid[0]


def select_robust(
    aggregates: Sequence[ComboAggregate],
    worst_case_guard: bool = True,
    guard_fallback_topk: int = 3,
) -> Tuple[Optional[ComboAggregate], str]:
    """Selettore robusto v8 (PRIMARIO).

    Strategia:
      1) Ordina valid combo per MAX(median OOS).
      2) Se top.sharpe_min >= 0 → ritorna top.
      3) Altrimenti (worst-case guard attivo): tra le top-K per median,
         scegli la combo con MAX(min OOS). Questo evita di selezionare
         strategie con median alto trainate da uno o due fold ottimi e
         un fold disastroso.

    Ritorna (combo, motivazione).
    """
    valid = [a for a in aggregates if not a.excluded]
    if not valid:
        return None, "no_valid_combo"

    sorted_by_med = sorted(valid, key=lambda a: -a.sharpe_median)
    top = sorted_by_med[0]

    if (not worst_case_guard) or top.sharpe_min >= 0:
        return top, "median_primary" + (
            "" if not worst_case_guard else "_no_neg_fold"
        )

    candidates = sorted_by_med[: min(guard_fallback_topk, len(sorted_by_med))]
    candidates.sort(key=lambda a: (-a.sharpe_min, -a.sharpe_median))
    chosen = candidates[0]
    return chosen, (
        f"worst_case_guard_triggered(top_min={top.sharpe_min:.3f}<0, "
        f"chosen_min={chosen.sharpe_min:.3f})"
    )


def selector_report(aggregates: Sequence[ComboAggregate]) -> str:
    """Report tabulare delle combo aggregate."""
    lines = [f"Selector report ({SEALED_VERSION})"]
    lines.append("-" * 100)
    header = (
        f"{'params_key':<60} {'med':>7} {'min':>7} {'max':>7} {'var':>7} {'pnl_m':>7} {'excl'}"
    )
    lines.append(header)
    lines.append("-" * 100)
    sorted_a = sorted(aggregates, key=lambda a: (a.excluded, -a.sharpe_median))
    for a in sorted_a:
        if a.excluded:
            lines.append(
                f"{a.params_key:<60} {'-':>7} {'-':>7} {'-':>7} {'-':>7} {'-':>7} EXCLUDED: {a.exclusion_reason}"
            )
        else:
            lines.append(
                f"{a.params_key:<60} {a.sharpe_median:>7.3f} {a.sharpe_min:>7.3f} "
                f"{a.sharpe_max:>7.3f} {a.sharpe_var:>7.3f} {a.pnl_median:>7.2f}"
            )
    return "\n".join(lines)


__all__ = [
    "SEALED_VERSION",
    "DEFAULT_MIN_TICKERS",
    "DEFAULT_MIN_TRADES",
    "FoldOOSPerf",
    "ComboAggregate",
    "aggregate_cross_fold",
    "select_median_fold_oos",
    "select_robust",
    "selector_report",
]
