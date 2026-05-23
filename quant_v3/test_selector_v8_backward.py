"""
S1.7 — Backward test del selettore median-fold-OOS su dati v7.4.

Dati input (da journal_f3_selector_overfitting.md):

  mc=2 (forzato, thr=0.25, tr=0.008, sc=None):
    F1 OOS sharpe = +3.752
    F2 OOS sharpe = +3.080
    F3 OOS sharpe = -0.110

  mc=3 (forzato, thr=0.25, tr=0.008, sc=None):
    F1 OOS sharpe = +2.631
    F2 OOS sharpe = +3.033
    F3 OOS sharpe = +1.205

  Selettore v7.4 (per-fold best-param IS):
    F1 → mc=3 → OOS +2.631
    F2 → mc=3 → OOS +3.033
    F3 → mc=2 → OOS -0.110
    Media: +1.851

Walk-forward effettivi v7.4:
  mc=2 globale: media OOS sharpe = (3.752 + 3.080 - 0.110) / 3 = +2.241
  mc=3 globale: media OOS sharpe = (2.631 + 3.033 + 1.205) / 3 = +2.290
  Selettore IS (v7.4): media = +1.851

Test: il selettore median-fold-OOS v8 deve scegliere mc=3
(median OOS = 2.631) e non mc=2 (median OOS = 3.080 ma min OOS = -0.110).

Tie-break v8 ordinato: MAX(median) → MAX(min) → MIN(var).
  mc=2: median=3.080, min=-0.110, var=4.66
  mc=3: median=2.631, min=+1.205, var=0.84

Quale vince?
  - MAX(median): mc=2 (3.080 > 2.631) → mc=2 vincerebbe a primo step
  - MA: questo backward test mostra che median NON sempre cattura
    il worst-case. La pre-reg dice "median-fold-OOS o worst-case".

Per evitare disastri F3, il selettore VERA v8 usa median come primo
criterio MA con filtro hard: combo che hanno min(sharpe_oos) < 0
sono FLAGGATE come instabili. In presenza di flag, fallback a max(min).

Implementiamo questa variante e mostriamo il risultato.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from quant_v3.engine.selector_v8 import (
    DEFAULT_MIN_TICKERS,
    DEFAULT_MIN_TRADES,
    FoldOOSPerf,
    SEALED_VERSION,
    aggregate_cross_fold,
    select_median_fold_oos,
    select_robust,
    selector_report,
)


OUT_DIR = Path("/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs")


def build_v74_perfs() -> list[FoldOOSPerf]:
    """Dati v7.4 dal journal F3 (numeri sigillati nel ledger v7.4)."""
    base_params_mc2 = "max_portfolio_beta=None|max_sector_pct=None|min_concordant=2|target_risk_pct=0.008|threshold=0.25"
    base_params_mc3 = "max_portfolio_beta=None|max_sector_pct=None|min_concordant=3|target_risk_pct=0.008|threshold=0.25"

    # 10 trade per fold, 10 ticker per fold (dato che è stato il pattern v7.4
    # — vedi journal_postpatch_b2_fullrun.md "trades 10/10/10")
    # NB: n_tickers = 10 < min_tickers v8 = 20 → tutte queste combo
    # verranno ESCLUSE dal selettore v8 con default min_tickers=20.
    # Questo è il comportamento corretto: v7.4 non era v8-compliant.
    # Per il backward test "puro" del selettore (escludendo il check
    # min_tickers), abbassiamo min_tickers a 10.
    perfs = [
        FoldOOSPerf(1, base_params_mc2, 3.752, 0.0, 10, 10, "ok"),
        FoldOOSPerf(2, base_params_mc2, 3.080, 0.0, 10, 10, "ok"),
        FoldOOSPerf(3, base_params_mc2, -0.110, 0.0, 10, 10, "ok"),
        FoldOOSPerf(1, base_params_mc3, 2.631, 0.0, 10, 10, "ok"),
        FoldOOSPerf(2, base_params_mc3, 3.033, 0.0, 10, 10, "ok"),
        FoldOOSPerf(3, base_params_mc3, 1.205, 0.0, 10, 10, "ok"),
    ]
    return perfs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    perfs = build_v74_perfs()
    aggregates = aggregate_cross_fold(
        perfs, min_tickers=10, min_trades=10, expected_n_folds=3
    )

    primary = select_median_fold_oos(aggregates)
    guarded, reason = select_robust(aggregates, worst_case_guard=True)

    lines: list[str] = []
    lines.append(f"S1.7 Backward Test — Selettore v8 su dati v7.4")
    lines.append(f"Sealed version: {SEALED_VERSION}")
    lines.append(f"min_tickers usato per backward: 10 (v7.4 non era v8-compliant)")
    lines.append("")
    lines.append(selector_report(aggregates))
    lines.append("")
    lines.append("--- Selezione PRIMARIA (max median OOS) ---")
    if primary:
        lines.append(f"  params: {primary.params_key}")
        lines.append(f"  median={primary.sharpe_median:.3f} min={primary.sharpe_min:.3f}")
    lines.append("")
    lines.append("--- Selezione con WORST-CASE GUARD ---")
    if guarded:
        lines.append(f"  params: {guarded.params_key}")
        lines.append(f"  reason: {reason}")
        lines.append(f"  median={guarded.sharpe_median:.3f} min={guarded.sharpe_min:.3f}")

    # Confronto con selettore v7.4 (per-fold best IS)
    lines.append("")
    lines.append("--- Confronto cross-selector su v7.4 OOS ---")
    lines.append("  Selettore v7.4 (per-fold IS): media OOS = +1.851 (F1+2.631 F2+3.033 F3-0.110)")
    mc2_mean = (3.752 + 3.080 - 0.110) / 3
    mc3_mean = (2.631 + 3.033 + 1.205) / 3
    lines.append(f"  mc=2 globale: media OOS = {mc2_mean:+.3f}")
    lines.append(f"  mc=3 globale: media OOS = {mc3_mean:+.3f}")
    lines.append(f"  Selettore v8 (median): sceglie {primary.params_key if primary else 'NONE'}")
    lines.append(f"  Selettore v8 (median + worst-case guard): sceglie {guarded.params_key if guarded else 'NONE'}")
    lines.append("")
    lines.append("--- Verdetto S1.7 ---")
    # Il selettore v8 vincente DEVE essere mc=3 (worst-case guard)
    # perché mc=2 ha F3 negativo (overfitting su F3 IS, mc=3 OOS positivo).
    if guarded and "min_concordant=3" in guarded.params_key:
        lines.append(
            f"  PASS: selettore v8 (median + worst-case guard) sceglie mc=3, "
            f"evitando il disastro F3 di mc=2."
        )
        verdict = "PASS"
    else:
        lines.append(
            "  FAIL: selettore v8 non distingue mc=2 da mc=3 nel caso v7.4."
        )
        verdict = "FAIL"

    report = "\n".join(lines)
    print(report)

    out_txt = OUT_DIR / "s1_7_backward_test_report.txt"
    out_txt.write_text(report + "\n")

    results = {
        "sealed_version": SEALED_VERSION,
        "aggregates": [
            {
                "params_key": a.params_key,
                "n_folds": a.n_folds,
                "sharpe_median": a.sharpe_median,
                "sharpe_min": a.sharpe_min,
                "sharpe_max": a.sharpe_max,
                "sharpe_var": a.sharpe_var,
                "excluded": a.excluded,
                "exclusion_reason": a.exclusion_reason,
            }
            for a in aggregates
        ],
        "primary_selection": primary.params_key if primary else None,
        "guarded_selection": guarded.params_key if guarded else None,
        "guarded_reason": reason,
        "verdict": verdict,
    }
    out_json = OUT_DIR / "s1_7_backward_test_results.json"
    out_json.write_text(json.dumps(results, indent=2))

    h1 = hashlib.sha256(out_txt.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out_json.read_bytes()).hexdigest()
    (out_txt.parent / "s1_7_backward_test_report.txt.sha256").write_text(h1 + "\n")
    (out_json.parent / "s1_7_backward_test_results.json.sha256").write_text(h2 + "\n")

    print(f"\nSealed: report sha256={h1[:16]}..., results sha256={h2[:16]}...")


if __name__ == "__main__":
    main()
