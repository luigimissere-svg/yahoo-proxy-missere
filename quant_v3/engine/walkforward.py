"""
Walk-Forward optimization framework — Fase 4.

Obiettivo:
    Validare statisticamente se i parametri ottimizzati su finestre IS (In-Sample)
    si comportano coerentemente OOS (Out-Of-Sample). Non cerchiamo "il parametro
    migliore in assoluto", ma rispondiamo a:
        1. Quali parametri ricorrono come vincenti nei vari fold?
        2. Il sistema regge OOS o degrada (overfitting)?

Schema default (modificabile via CLI):
    IS: 12 mesi  |  OOS: 3 mesi  |  Step: 3 mesi  → 4 fold su 22 mesi totali.

Pipeline:
    1. generate_folds(start, end) → lista di Fold (is_start, is_end, oos_start, oos_end)
    2. Per ogni fold:
        a. Per ogni combinazione del param_grid:
            - run cerebro su IS (clamped al periodo del fold)
            - calcola Sharpe IS + #trade
            - skip se trades < min_trades_per_fold (anti-noise)
        b. Tie-break: a parità di Sharpe entro 5%, vince threshold più alto
        c. Best params → run cerebro su OOS → calcola Sharpe OOS, P&L, DD
    3. aggregate_stability(results) → tabella parametro→counter (quante volte vincente)

Output:
    - results: list[FoldResult] con (fold_id, best_params, is_sharpe, is_trades,
      oos_sharpe, oos_pnl, oos_dd, degradation_ratio, overfitting_flag)
    - stability: dict param_name → dict value → count

Design:
    - NON usa cerebro.optstrategy: alcuni parametri richiedono istanze (es. 
      PortfolioConstraints), non scalari. Loop esplicito è più chiaro e
      controllabile.
    - Il `runner_factory` callback è iniettabile: prepara un cerebro fresh per
      ogni run (no side effects tra combinazioni).
    - Sharpe annualizzato (SharpeRatio_A di Backtrader).
"""
from __future__ import annotations

import itertools
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class Fold:
    """Singolo fold walk-forward."""
    fold_id: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime

    def __str__(self) -> str:
        return (f"F{self.fold_id} IS {self.is_start:%Y-%m-%d}→{self.is_end:%Y-%m-%d} "
                f"OOS {self.oos_start:%Y-%m-%d}→{self.oos_end:%Y-%m-%d}")


@dataclass
class RunMetrics:
    """Output di un singolo backtest (IS o OOS).

    Post-patch bug Sharpe OOS = 1,0000 (maggio 2026):
    - `sharpe_a` ora contiene lo Sharpe annualizzato calcolato a mano via NumPy
      su TimeReturn (ground truth), NON più l'output dell'analyzer
      bt.analyzers.SharpeRatio_A che si era dimostrato numericamente instabile
      su finestre OOS corte (~63 barre) — collassava a 1,0000 esatto.
    - `sharpe_bt` è mantenuto come cross-check (output dell'analyzer
      bt.analyzers.SharpeRatio standard, annualizzato esplicitamente con
      factor=252). Non usato dal driver, solo per diagnostica.
    - `sharpe_flag` ('ok' | 'insufficient_window') segnala se la finestra ha
      dati a sufficienza per calcolare uno Sharpe affidabile.
    - I quattro campi diagnostici `n_*` consentono di verificare a posteriori
      condizioni di patologia (finestre troppo corte, troppi zeri).

    DSR Bailey-LdP v7.3 (maggio 2026):
    - `daily_returns` opzionale: lista di tuple (date_iso_str, return_float)
      ordinata cronologicamente. Popolata solo quando la factory è chiamata
      con `attach_returns=True`. Necessaria per costruire la matrice di
      correlazione fra trial e per il block bootstrap empirico di SR_0
      sotto il framework DSR formale (item consulente v7.3).
    """
    sharpe: float
    sharpe_a: float
    pnl_pct: float
    max_dd: float
    trades: int
    final_value: float
    # Campi aggiunti post-patch (default safe per back-compat con i test).
    sharpe_bt: float = 0.0
    sharpe_flag: str = 'ok'
    n_bars: int = 0
    n_nonzero_returns: int = 0
    # Campi aggiunti v7.3 DSR (attach_returns=True dalla factory).
    daily_returns: List[Any] = field(default_factory=list)

    @staticmethod
    def empty() -> 'RunMetrics':
        return RunMetrics(
            sharpe=0.0,
            sharpe_a=0.0,
            pnl_pct=0.0,
            max_dd=0.0,
            trades=0,
            final_value=0.0,
            sharpe_bt=0.0,
            sharpe_flag='insufficient_window',
            n_bars=0,
            n_nonzero_returns=0,
            daily_returns=[],
        )


@dataclass
class FoldResult:
    """Output completo per un fold dopo IS optimization + OOS evaluation."""
    fold_id: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    best_params: Dict[str, Any]
    is_metrics: RunMetrics
    oos_metrics: RunMetrics
    n_combos_evaluated: int
    n_combos_skipped_min_trades: int

    @property
    def degradation_ratio(self) -> float:
        """OOS_sharpe / IS_sharpe. < 0.3 = overfitting; > 0.7 = molto stabile.

        Ritorna NaN se uno dei due lati è stato marcato 'insufficient_window'
        (finestra troppo corta o serie degenere), perché il rapporto sarebbe
        privo di significato statistico.
        """
        if (self.is_metrics.sharpe_flag != 'ok'
                or self.oos_metrics.sharpe_flag != 'ok'):
            return float('nan')
        if abs(self.is_metrics.sharpe_a) < 1e-9:
            return 0.0
        return self.oos_metrics.sharpe_a / self.is_metrics.sharpe_a

    @property
    def overfitting_flag(self) -> bool:
        """True se OOS sharpe < 0.3 × IS sharpe (con IS positivo).

        Ritorna False se la diagnosi non è calcolabile (fold non valutabile).
        """
        if (self.is_metrics.sharpe_flag != 'ok'
                or self.oos_metrics.sharpe_flag != 'ok'):
            return False
        if self.is_metrics.sharpe_a <= 0:
            return False  # IS già negativo, non si parla di overfitting
        return self.degradation_ratio < 0.3

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['degradation_ratio'] = self.degradation_ratio
        d['overfitting_flag'] = self.overfitting_flag
        return d


# ─── Window generation ───────────────────────────────────────────────────────

def _add_months(dt: datetime, months: int) -> datetime:
    """Aggiunge N mesi rispettando i giorni del mese (clamp a fine mese)."""
    y, m = dt.year, dt.month + months
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    # Clamp day a fine mese se necessario
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    d = min(dt.day, last_day)
    return dt.replace(year=y, month=m, day=d)


def generate_folds(
    start: datetime,
    end: datetime,
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
) -> List[Fold]:
    """
    Genera fold rolling walk-forward.

    Args:
        start: data inizio dataset (es. 2024-08-01)
        end: data fine dataset (es. 2026-05-22)
        is_months: lunghezza finestra IS in mesi
        oos_months: lunghezza finestra OOS in mesi
        step_months: incremento tra fold consecutivi

    Returns:
        Lista di Fold ordinati per fold_id (1, 2, 3, ...).

    Un fold è valido solo se l'OOS termina entro `end`. L'ultimo fold può avere
    OOS parziale (se end < oos_end teorico) → escluso per default per onestà
    statistica (sotto-campionato).
    """
    if is_months <= 0 or oos_months <= 0 or step_months <= 0:
        raise ValueError("is_months, oos_months, step_months devono essere > 0")
    if start >= end:
        raise ValueError(f"start ({start}) deve essere < end ({end})")

    folds: List[Fold] = []
    fold_id = 1
    is_start = start
    while True:
        is_end = _add_months(is_start, is_months)
        oos_start = is_end
        oos_end = _add_months(oos_start, oos_months)
        if oos_end > end:
            # Fold parziale: scartato per non avere OOS sotto-campionato.
            # Eccezione: se è il PRIMO fold ed è parziale → solleva, dataset troppo corto.
            if fold_id == 1:
                raise ValueError(
                    f"Dataset troppo corto: IS={is_months}m + OOS={oos_months}m "
                    f"= {is_months + oos_months}m richiesti, disponibili "
                    f"{(end - start).days / 30:.1f}m"
                )
            break
        folds.append(Fold(
            fold_id=fold_id,
            is_start=is_start,
            is_end=is_end,
            oos_start=oos_start,
            oos_end=oos_end,
        ))
        fold_id += 1
        is_start = _add_months(is_start, step_months)
    return folds


# ─── Param grid ──────────────────────────────────────────────────────────────

def expand_grid(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Espande grid dict in lista di combinazioni.

    Esempio:
        grid = {'threshold': [0.15, 0.20], 'min_concordant': [2, 3]}
        → [{'threshold': 0.15, 'min_concordant': 2},
           {'threshold': 0.15, 'min_concordant': 3},
           {'threshold': 0.20, 'min_concordant': 2},
           {'threshold': 0.20, 'min_concordant': 3}]
    """
    if not grid:
        return [{}]
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    combos = []
    for combination in itertools.product(*values):
        combos.append(dict(zip(keys, combination)))
    return combos


# ─── Best-params selection (con tie-break) ───────────────────────────────────

def select_best_params(
    is_results: List[Tuple[Dict[str, Any], RunMetrics]],
    min_trades: int = 5,
    tie_break_pct: float = 0.05,
) -> Tuple[Optional[Dict[str, Any]], Optional[RunMetrics], int]:
    """
    Seleziona miglior parameter set su IS.

    Args:
        is_results: lista di (params, metrics) per ciascuna combinazione.
        min_trades: trade minimi richiesti per ritenere il run statisticamente valido.
        tie_break_pct: a parità di Sharpe entro questa frazione, vince threshold più alto.

    Returns:
        (best_params, best_metrics, n_skipped_min_trades). Tutti None se nessun
        run supera il floor di min_trades.
    """
    # Filtra per min_trades E per sharpe_flag = 'ok' (post-patch bug Sharpe OOS):
    # un combo IS con sharpe_a non affidabile non può alimentare il sort della
    # grid search. Senza questo filtro si rischia di riprodurre lo stesso
    # difetto che ha invalidato lo snapshot pre-patch.
    valid = [
        (p, m) for p, m in is_results
        if m.trades >= min_trades and m.sharpe_flag == 'ok'
    ]
    n_skipped = len(is_results) - len(valid)
    if not valid:
        return None, None, n_skipped

    # Ordina per Sharpe annualizzato decrescente
    valid.sort(key=lambda x: x[1].sharpe_a, reverse=True)

    # Tie-break: tra i top entro tie_break_pct, scegli threshold massimo
    top_sharpe = valid[0][1].sharpe_a
    if top_sharpe > 0:
        # tolleranza relativa
        tolerance = top_sharpe * tie_break_pct
        ties = [(p, m) for p, m in valid if abs(m.sharpe_a - top_sharpe) <= tolerance]
        if len(ties) > 1:
            # tra i tie, ordina per threshold desc (più selettivo = meno overfit)
            ties.sort(key=lambda x: x[0].get('threshold', 0), reverse=True)
            return ties[0][0], ties[0][1], n_skipped

    return valid[0][0], valid[0][1], n_skipped


# ─── Stability analysis ──────────────────────────────────────────────────────

def aggregate_stability(
    results: List[FoldResult],
    stable_threshold: int = 3,
) -> Dict[str, Any]:
    """
    Calcola statistiche di stabilità dei parametri sui fold.

    Per ciascun parametro, conta quante volte ciascun valore è stato vincente.
    Un parametro è "stabile" se lo stesso valore vince in >= stable_threshold fold.

    Returns:
        {
            'n_folds': N,
            'stable_threshold': K,
            'param_counts': {
                'threshold': {0.15: 1, 0.20: 3},
                'min_concordant': {2: 0, 3: 4},
                ...
            },
            'stable_params': {
                # parametri con un valore ricorrente in >= K fold
                'min_concordant': 3,
                ...
            },
            'is_sharpe_mean': float,
            'oos_sharpe_mean': float,
            'degradation_mean': float,
            'overfitting_count': int,
        }
    """
    if not results:
        return {
            'n_folds': 0, 'stable_threshold': stable_threshold,
            'param_counts': {}, 'stable_params': {},
            'is_sharpe_mean': 0.0, 'oos_sharpe_mean': 0.0,
            'degradation_mean': 0.0, 'overfitting_count': 0,
        }

    # Conta valori per ciascun parametro
    param_counts: Dict[str, Dict[Any, int]] = {}
    for r in results:
        for k, v in r.best_params.items():
            # serialize value: None resta None, float arrotondato
            if isinstance(v, float):
                v_key = round(v, 6)
            else:
                v_key = v
            param_counts.setdefault(k, {})
            param_counts[k][v_key] = param_counts[k].get(v_key, 0) + 1

    # Stable params: valore ricorrente >= stable_threshold
    stable_params: Dict[str, Any] = {}
    for param, counter in param_counts.items():
        winner = max(counter.items(), key=lambda x: x[1])
        if winner[1] >= stable_threshold:
            stable_params[param] = winner[0]

    # Aggregate metrics (post-patch bug Sharpe OOS):
    # le medie ora sono calcolate SOLO sui fold con sharpe_flag = 'ok' su
    # entrambi i lati. I fold con finestra OOS insufficiente vengono contati
    # separatamente in n_folds_insufficient_oos.
    valid_results = [
        r for r in results
        if r.is_metrics.sharpe_flag == 'ok'
        and r.oos_metrics.sharpe_flag == 'ok'
    ]
    n_insufficient_oos = sum(
        1 for r in results if r.oos_metrics.sharpe_flag != 'ok'
    )
    n_insufficient_is = sum(
        1 for r in results if r.is_metrics.sharpe_flag != 'ok'
    )

    if valid_results:
        is_sharpes = [r.is_metrics.sharpe_a for r in valid_results]
        oos_sharpes = [r.oos_metrics.sharpe_a for r in valid_results]
        degradations = [r.degradation_ratio for r in valid_results]
        overfitting_count = sum(1 for r in valid_results if r.overfitting_flag)
        is_sharpe_mean = sum(is_sharpes) / len(is_sharpes)
        oos_sharpe_mean = sum(oos_sharpes) / len(oos_sharpes)
        degradation_mean = sum(degradations) / len(degradations)
    else:
        is_sharpe_mean = float('nan')
        oos_sharpe_mean = float('nan')
        degradation_mean = float('nan')
        overfitting_count = 0

    return {
        'n_folds': len(results),
        'n_folds_valid': len(valid_results),
        'n_folds_insufficient_is': n_insufficient_is,
        'n_folds_insufficient_oos': n_insufficient_oos,
        'stable_threshold': stable_threshold,
        'param_counts': param_counts,
        'stable_params': stable_params,
        'is_sharpe_mean': is_sharpe_mean,
        'oos_sharpe_mean': oos_sharpe_mean,
        'degradation_mean': degradation_mean,
        'overfitting_count': overfitting_count,
    }


# ─── Main walk-forward runner ────────────────────────────────────────────────

# Type alias: callback che esegue un singolo backtest e ritorna RunMetrics
# Signature: run_backtest(params: dict, start: datetime, end: datetime) → RunMetrics
RunCallback = Callable[[Dict[str, Any], datetime, datetime], RunMetrics]

# Type alias v7.3 DSR: callback per raccogliere serie equity per trial × fold.
# Signature: equity_collector(trial_idx, fold_id, phase, params, metrics) → None
# phase ∈ {'IS', 'OOS'}; metrics.daily_returns conterrà la serie.
EquityCollector = Callable[[int, int, str, Dict[str, Any], RunMetrics], None]


def run_walkforward(
    folds: List[Fold],
    param_grid: Dict[str, List[Any]],
    run_backtest: RunCallback,
    min_trades_per_fold: int = 5,
    tie_break_pct: float = 0.05,
    verbose: bool = True,
    equity_collector: Optional[EquityCollector] = None,
) -> List[FoldResult]:
    """
    Esegue walk-forward completo.

    Args:
        folds: lista di Fold da generate_folds()
        param_grid: dict param → lista valori
        run_backtest: callback (params, start, end) → RunMetrics
        min_trades_per_fold: floor di trade IS per validare un parameter set
        tie_break_pct: tolleranza Sharpe per tie-break su threshold
        verbose: log progresso

    Returns:
        Lista di FoldResult.
    """
    combos = expand_grid(param_grid)
    if verbose:
        logger.info(
            f"Walk-forward: {len(folds)} fold × {len(combos)} combo = "
            f"{len(folds) * (len(combos) + 1)} run cerebro totali "
            f"({len(folds) * len(combos)} IS + {len(folds)} OOS)"
        )

    results: List[FoldResult] = []
    t_start = time.time()

    for fold in folds:
        fold_t0 = time.time()
        if verbose:
            logger.info(f"━━━ {fold} ━━━")

        # IS optimization: run tutti i combo
        is_results: List[Tuple[Dict[str, Any], RunMetrics]] = []
        for i, params in enumerate(combos, 1):
            try:
                m = run_backtest(params, fold.is_start, fold.is_end)
            except Exception as e:
                logger.warning(f"  IS combo {i}/{len(combos)} {params} FAIL: {e}")
                m = RunMetrics.empty()
            is_results.append((params, m))
            # v7.3 DSR: raccogli la serie IS per matrice di correlazione fra trial.
            # trial_idx è 1-based (1..N_combo) per coerenza con il display utente.
            if equity_collector is not None:
                try:
                    equity_collector(i, fold.fold_id, 'IS', params, m)
                except Exception as exc:
                    logger.warning(
                        f"  equity_collector IS failed trial={i} fold={fold.fold_id}: {exc}"
                    )
            if verbose and i % 10 == 0:
                logger.info(
                    f"  IS progress {i}/{len(combos)} elapsed={time.time()-fold_t0:.0f}s"
                )

        # Select best
        best_params, best_metrics, n_skipped = select_best_params(
            is_results, min_trades=min_trades_per_fold, tie_break_pct=tie_break_pct,
        )

        if best_params is None:
            logger.warning(
                f"  {fold}: nessun parameter set con trades >= {min_trades_per_fold}. Skipped."
            )
            continue

        # OOS evaluation
        try:
            oos_metrics = run_backtest(best_params, fold.oos_start, fold.oos_end)
        except Exception as e:
            logger.warning(f"  OOS run FAIL: {e}")
            oos_metrics = RunMetrics.empty()

        fold_result = FoldResult(
            fold_id=fold.fold_id,
            is_start=fold.is_start.strftime('%Y-%m-%d'),
            is_end=fold.is_end.strftime('%Y-%m-%d'),
            oos_start=fold.oos_start.strftime('%Y-%m-%d'),
            oos_end=fold.oos_end.strftime('%Y-%m-%d'),
            best_params=best_params,
            is_metrics=best_metrics,
            oos_metrics=oos_metrics,
            n_combos_evaluated=len(is_results),
            n_combos_skipped_min_trades=n_skipped,
        )
        results.append(fold_result)

        if verbose:
            flag_tag = ''
            if oos_metrics.sharpe_flag != 'ok':
                flag_tag = f' ⚠ OOS_{oos_metrics.sharpe_flag.upper()}'
            elif fold_result.overfitting_flag:
                flag_tag = ' ⚠ OVERFIT'
            logger.info(
                f"  {fold} best={best_params} "
                f"IS_sharpe={best_metrics.sharpe_a:.3f} ({best_metrics.trades}t) "
                f"OOS_sharpe={oos_metrics.sharpe_a:.3f} ({oos_metrics.trades}t) "
                f"degradation={fold_result.degradation_ratio:.2f}"
                f"{flag_tag} "
                f"elapsed={time.time()-fold_t0:.0f}s"
            )

    if verbose:
        logger.info(
            f"Walk-forward completato: {len(results)}/{len(folds)} fold validi, "
            f"total elapsed={time.time()-t_start:.0f}s"
        )

    return results


# ─── Serialization ───────────────────────────────────────────────────────────

def results_to_csv_rows(results: List[FoldResult]) -> List[Dict[str, Any]]:
    """Flatten FoldResult per CSV (best_params espansi in colonne)."""
    rows = []
    for r in results:
        row = {
            'fold_id': r.fold_id,
            'is_start': r.is_start,
            'is_end': r.is_end,
            'oos_start': r.oos_start,
            'oos_end': r.oos_end,
            'is_sharpe_a': r.is_metrics.sharpe_a,
            'is_sharpe_bt': r.is_metrics.sharpe_bt,
            'is_sharpe_flag': r.is_metrics.sharpe_flag,
            'is_n_bars': r.is_metrics.n_bars,
            'is_n_nonzero_returns': r.is_metrics.n_nonzero_returns,
            'is_pnl_pct': r.is_metrics.pnl_pct,
            'is_max_dd': r.is_metrics.max_dd,
            'is_trades': r.is_metrics.trades,
            'oos_sharpe_a': r.oos_metrics.sharpe_a,
            'oos_sharpe_bt': r.oos_metrics.sharpe_bt,
            'oos_sharpe_flag': r.oos_metrics.sharpe_flag,
            'oos_n_bars': r.oos_metrics.n_bars,
            'oos_n_nonzero_returns': r.oos_metrics.n_nonzero_returns,
            'oos_pnl_pct': r.oos_metrics.pnl_pct,
            'oos_max_dd': r.oos_metrics.max_dd,
            'oos_trades': r.oos_metrics.trades,
            'degradation_ratio': r.degradation_ratio,
            'overfitting_flag': r.overfitting_flag,
            'n_combos_evaluated': r.n_combos_evaluated,
            'n_combos_skipped_min_trades': r.n_combos_skipped_min_trades,
        }
        # Espandi best_params come param_<name>
        for k, v in r.best_params.items():
            row[f'param_{k}'] = v
        rows.append(row)
    return rows
