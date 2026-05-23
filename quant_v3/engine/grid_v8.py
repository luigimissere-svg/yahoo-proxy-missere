"""
S1.6 — Grid iperparametri ridotta v8 (sigillata).

Pre-registrazione: preregistration_s1_v8.md §S1.6
Conformità: 24 × 3 fold = 24 esperimenti totali (sotto vincolo "≤36×3").

Riduzione dimensionale rispetto a GRID_FULL v7.4 (72 combo):
  threshold: {0.15, 0.20, 0.25} → {0.20, 0.25}
    motivazione: in v7.4 tutti e 3 i fold hanno selezionato 0.25
    (F1: 0.15-0.20 plateau, F2/F3: 0.25). Tenuto 0.20 come
    backstop per coprire la fascia bassa-media.
  min_concordant: {2, 3}  (invariato — chiave Bug 7)
    motivazione: variabile centrale del selector overfitting
    (journal_f3_selector_overfitting.md). NON ridurre.
  target_risk_pct: {0.008, 0.010, 0.012} → {0.008, 0.010}
    motivazione: in v7.4 tutti e 3 i fold hanno selezionato 0.008.
    0.012 scartato (non ha mai vinto in IS o OOS).
  max_sector_pct: {None, 0.30} → {0.30}  (SIGILLATO)
    motivazione: doctrine v8 — vincolo di diversificazione settoriale
    obbligatorio per stabilità out-of-sample. None disabilita il
    constraint, incompatibile con discipline S1.3 (min_tickers ≥ 20)
    senza diversificazione settoriale.
  max_portfolio_beta: {None, 1.3} → {1.3}  (SIGILLATO)
    motivazione: doctrine v8 — beta cap operativo per controllo
    esposizione direzionale al mercato. None scartato.

Risultato: 2 × 2 × 2 × 1 × 1 = 8 combo per fold × 3 fold = 24 trial.

Sealed version: v8.s1.6
"""

from __future__ import annotations

from typing import Any, Dict, List


SEALED_VERSION: str = "v8.s1.6"


# Grid v8 sigillata — modifiche richiedono addendum pre-reg
GRID_V8: Dict[str, List[Any]] = {
    "threshold": [0.20, 0.25],
    "min_concordant": [2, 3],
    "target_risk_pct": [0.008, 0.010],
    "max_sector_pct": [0.30],
    "max_portfolio_beta": [1.3],
}


def n_combos(grid: Dict[str, List[Any]] = GRID_V8) -> int:
    """Numero di combinazioni nella grid."""
    n = 1
    for v in grid.values():
        n *= len(v)
    return n


def grid_summary(grid: Dict[str, List[Any]] = GRID_V8) -> str:
    """Stringa riassuntiva della grid."""
    lines = [f"Grid {SEALED_VERSION}: {n_combos(grid)} combo per fold"]
    for k, vs in grid.items():
        lines.append(f"  {k}: {vs}")
    return "\n".join(lines)


# Frozen params (NON modificabili senza addendum)
FROZEN_PARAMS: Dict[str, Any] = {
    "max_sector_pct": 0.30,
    "max_portfolio_beta": 1.3,
}


__all__ = ["SEALED_VERSION", "GRID_V8", "FROZEN_PARAMS", "n_combos", "grid_summary"]


if __name__ == "__main__":
    print(grid_summary())
    print(f"\nTotal trials (3 fold): {n_combos() * 3}")
    print(f"Conformity check (<=36 per fold): {n_combos() <= 36}")
    print(f"Frozen params: {FROZEN_PARAMS}")
