"""
S1.3 — Backward test della regola exposure cap su ledger F2 OOS v7.4.

Input: /home/user/workspace/f2_oos_trade_ledger.csv (10 trade, fold 1, F2 OOS).
Output:
  - tabella before/after cap notional
  - delta P&L del fold
  - applicazione falsificazione F2 della pre-reg
  - hash dell'output sealing per audit

Esecuzione:
  python -m quant_v3.test_risk_caps_backward
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from quant_v3.risk_caps import (
    NOTIONAL_CAP_PCT,
    SEALED_VERSION,
    Trade,
    apply_notional_cap,
    f2_falsification,
)


LEDGER_PATH = Path("/home/user/workspace/f2_oos_trade_ledger.csv")
OUT_DIR = Path("/home/user/workspace/yahoo-proxy-missere/quant_v3/s1_outputs")


def load_ledger(path: Path) -> list[Trade]:
    with path.open() as f:
        return [
            Trade(
                ticker=row["ticker"],
                notional_open=float(row["notional_open"]),
                pnl_gross=float(row["pnl_gross"]),
            )
            for row in csv.DictReader(f)
        ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    trades = load_ledger(LEDGER_PATH)
    fold_capital = sum(t.notional_open for t in trades)
    cap_results = apply_notional_cap(trades, fold_capital, NOTIONAL_CAP_PCT)

    tot_orig = sum(r.pnl_orig for r in cap_results)
    tot_capped = sum(r.pnl_capped for r in cap_results)
    delta_abs = tot_capped - tot_orig
    delta_pct = delta_abs / tot_orig * 100.0 if tot_orig else 0.0

    # MU contributo % al PnL prima/dopo
    mu_res = next(r for r in cap_results if r.ticker == "MU")
    mu_pct_orig = mu_res.pnl_orig / tot_orig * 100.0
    mu_pct_capped = mu_res.pnl_capped / tot_capped * 100.0 if tot_capped else 0.0

    is_marginal, motiv = f2_falsification(delta_pct, threshold_pct=5.0)

    # --- Output tabellare ---
    lines: list[str] = []
    lines.append(f"S1.3 Backward Test — Bug 8 Exposure Cap")
    lines.append(f"Sealed version: {SEALED_VERSION}")
    lines.append(f"Cap %: {NOTIONAL_CAP_PCT*100:.1f}%")
    lines.append(f"Fold capital (sum notional_open): {fold_capital:,.2f} EUR")
    lines.append(f"Cap notional per ticker: {fold_capital*NOTIONAL_CAP_PCT:,.2f} EUR\n")

    header = f"{'Ticker':<10} {'Not_orig':>11} {'Not_cap':>11} {'scale':>6} {'PnL_orig':>11} {'PnL_cap':>11}"
    lines.append(header)
    lines.append("-" * len(header))
    for r in sorted(cap_results, key=lambda x: -x.pnl_orig):
        lines.append(
            f"{r.ticker:<10} {r.notional_orig:>11.2f} {r.notional_capped:>11.2f} "
            f"{r.scale_notional:>6.3f} {r.pnl_orig:>11.2f} {r.pnl_capped:>11.2f}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'TOT':<10} {'':>11} {'':>11} {'':>6} {tot_orig:>11.2f} {tot_capped:>11.2f}"
    )
    lines.append("")
    lines.append(f"Delta P&L (cap vs orig): {delta_abs:+,.2f} EUR ({delta_pct:+.2f}%)")
    lines.append(f"MU contributo PRE-cap: {mu_pct_orig:.2f}% del PnL fold")
    lines.append(f"MU contributo POST-cap: {mu_pct_capped:.2f}% del PnL fold")
    lines.append("")
    lines.append(f"Falsificazione F2 pre-reg S1.3:")
    lines.append(f"  marginal = {is_marginal}")
    lines.append(f"  {motiv}")

    report = "\n".join(lines)
    print(report)

    # --- Sealing ---
    out_txt = OUT_DIR / "s1_3_backward_test_report.txt"
    out_json = OUT_DIR / "s1_3_backward_test_results.json"
    out_txt.write_text(report + "\n")

    results = {
        "sealed_version": SEALED_VERSION,
        "cap_pct": NOTIONAL_CAP_PCT,
        "fold_capital": fold_capital,
        "tot_pnl_orig": tot_orig,
        "tot_pnl_capped": tot_capped,
        "delta_pnl_abs": delta_abs,
        "delta_pnl_pct": delta_pct,
        "mu_pct_orig": mu_pct_orig,
        "mu_pct_capped": mu_pct_capped,
        "f2_marginal": is_marginal,
        "f2_motivation": motiv,
        "trades_capped": [
            {
                "ticker": r.ticker,
                "notional_orig": r.notional_orig,
                "notional_capped": r.notional_capped,
                "scale": r.scale_notional,
                "pnl_orig": r.pnl_orig,
                "pnl_capped": r.pnl_capped,
            }
            for r in cap_results
        ],
    }
    out_json.write_text(json.dumps(results, indent=2))

    # SHA256 sealing
    h = hashlib.sha256(out_txt.read_bytes()).hexdigest()
    (out_txt.parent / "s1_3_backward_test_report.txt.sha256").write_text(h + "\n")
    h2 = hashlib.sha256(out_json.read_bytes()).hexdigest()
    (out_json.parent / "s1_3_backward_test_results.json.sha256").write_text(h2 + "\n")

    print(f"\nSealed:")
    print(f"  {out_txt.name} sha256={h[:16]}...")
    print(f"  {out_json.name} sha256={h2[:16]}...")


if __name__ == "__main__":
    main()
