"""
S1.5 esecuzione 3 — Test di falsificazione H1-H4

Script eseguito al termine del run autoritativo wf_runner --grid s1_5_exec3.

Ipotesi pre-registrate (preregistration_s15_exec3_grid_ampliato.md SHA a2790d3c):

  H1 — Non-degenerazione: ≤25% trial con stat identiche (|ΔSharpe|<0.05,
       |Δρ|<0.01, |ΔPnL|<0.5%) a un altro trial nello stesso fold OOS.

  H2 — Monotonia ρ_AR(1) su mc: regressione ρ ~ mc su F2 OOS con
       coefficient positivo significativo (p<0.10).

  H3 — Best_param stabile: 4 selettori (max-Sharpe, max-DSR, min-|ρ|,
       max-Sharpe con vincolo |ρ|<0.10) → ≥3/4 convergono.

  H4 — Sharpe operativo Backtrader del best_param OOS ≥ 1.5 (F2 OOS).

Output: s15_exec3_falsification_report.md + JSON dettagliato.

USO:
    python s1_outputs/s15_exec3_falsification.py
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
RESULTS_CSV = BASE / "s15_exec3_f2_results.csv"
EQUITY_CSV = BASE / "s15_exec3_f2_equity.csv"
TRADES_CSV = BASE / "s15_exec3_f2_trades.csv"
STABILITY_JSON = BASE / "s15_exec3_f2_stability.json"
OUT_MD = BASE / "s15_exec3_falsification_report.md"
OUT_JSON = BASE / "s15_exec3_falsification_report.json"

CEST = timezone(timedelta(hours=2))


def _ar1(returns: np.ndarray) -> float:
    """Correlazione AR(1) di una serie di rendimenti."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 3:
        return np.nan
    mu = r.mean()
    num = ((r[1:] - mu) * (r[:-1] - mu)).sum()
    den = ((r - mu) ** 2).sum()
    if den <= 0:
        return np.nan
    return float(num / den)


def _dsr(sharpe: float, n: int, skew: float = 0.0, kurt_excess: float = 0.0) -> float:
    """Deflated Sharpe Ratio approssimato (forma chiusa Bailey 2014)."""
    if n < 2 or not np.isfinite(sharpe):
        return np.nan
    se = np.sqrt(max((1.0 - skew * sharpe + 0.25 * (kurt_excess) * sharpe ** 2) / (n - 1), 1e-12))
    return float(sharpe / se)


def load_per_trial_oos_metrics(equity_df: pd.DataFrame, fold_id: int = 2) -> pd.DataFrame:
    """Per ogni trial nel fold OOS specificato calcola Sharpe raw, ρ, n_obs."""
    sub = equity_df[(equity_df["fold_id"] == fold_id) & (equity_df["phase"] == "OOS")].copy()
    if sub.empty:
        return pd.DataFrame()

    rows = []
    for trial_id, grp in sub.groupby("trial_id"):
        rets = grp["daily_return"].astype(float).values
        rets = rets[~np.isnan(rets)]
        if len(rets) < 5:
            continue
        mu = rets.mean()
        sd = rets.std(ddof=1)
        sharpe_a = (mu / sd) * np.sqrt(252) if sd > 0 else np.nan
        rho = _ar1(rets)
        params = json.loads(grp["params_json"].iloc[0]) if "params_json" in grp.columns else {}
        rows.append({
            "trial_id": int(trial_id),
            "mc": params.get("min_concordant"),
            "thr": params.get("threshold"),
            "msp": params.get("max_sector_pct"),
            "n_obs": len(rets),
            "sharpe_a_raw": sharpe_a,
            "rho_ar1": rho,
            "pnl_pct": float((np.prod(1 + rets) - 1) * 100),
            "dsr": _dsr(sharpe_a, len(rets)),
        })
    return pd.DataFrame(rows).sort_values("trial_id").reset_index(drop=True)


# ─── H1: non-degenerazione ────────────────────────────────────────────────────
def test_h1(metrics: pd.DataFrame) -> dict:
    if metrics.empty or len(metrics) < 2:
        return {"pass": None, "reason": "metrics vuoto"}

    # Trial "invalidi" (Sharpe NaN — portfolio mai investito): conteggiati a parte.
    valid_mask = metrics["sharpe_a_raw"].notna() & metrics["rho_ar1"].notna()
    valid = metrics[valid_mask].reset_index(drop=True)
    n_invalid = int((~valid_mask).sum())
    n = len(valid)
    if n < 2:
        return {"pass": None, "reason": "trial validi <2", "n_invalid": n_invalid}

    degenerate_pairs = 0
    degenerate_set = set()
    for i in range(n):
        for j in range(i + 1, n):
            a, b = valid.iloc[i], valid.iloc[j]
            if (abs(a.sharpe_a_raw - b.sharpe_a_raw) < 0.05 and
                    abs(a.rho_ar1 - b.rho_ar1) < 0.01 and
                    abs(a.pnl_pct - b.pnl_pct) < 0.5):
                degenerate_pairs += 1
                degenerate_set.add(int(a.trial_id))
                degenerate_set.add(int(b.trial_id))

    pct = (len(degenerate_set) / n) * 100
    return {
        "pass": pct <= 25.0,
        "n_trials_total": int(len(metrics)),
        "n_trials_valid": n,
        "n_trials_invalid_nan": n_invalid,
        "n_degenerate": len(degenerate_set),
        "pct_degenerate": round(pct, 2),
        "degenerate_pairs": degenerate_pairs,
        "threshold": "≤25% (su trial validi non-NaN)",
    }


# ─── H2: monotonia ρ ~ mc ─────────────────────────────────────────────────────
def test_h2(metrics: pd.DataFrame) -> dict:
    if metrics.empty:
        return {"pass": None, "reason": "metrics vuoto"}
    df = metrics.dropna(subset=["mc", "rho_ar1"]).copy()
    if len(df) < 3 or df["mc"].nunique() < 2:
        return {"pass": None, "reason": "campione insufficiente"}

    slope, intercept, r, p, stderr = sp_stats.linregress(df["mc"].astype(float), df["rho_ar1"].astype(float))
    rho_per_mc = df.groupby("mc")["rho_ar1"].mean().to_dict()
    return {
        "pass": (slope > 0) and (p < 0.10),
        "slope": float(slope),
        "intercept": float(intercept),
        "r": float(r),
        "p_value": float(p),
        "rho_mean_per_mc": {int(k): float(v) for k, v in rho_per_mc.items()},
        "threshold": "slope>0 AND p<0.10",
    }


# ─── H3: convergenza selettori ────────────────────────────────────────────────
def test_h3(metrics: pd.DataFrame) -> dict:
    if metrics.empty:
        return {"pass": None, "reason": "metrics vuoto"}
    m = metrics.copy()
    selectors = {}
    selectors["A_max_sharpe"] = int(m.loc[m.sharpe_a_raw.idxmax(), "trial_id"])
    selectors["B_max_dsr"] = int(m.loc[m.dsr.idxmax(), "trial_id"])
    selectors["C_min_abs_rho"] = int(m.loc[m.rho_ar1.abs().idxmin(), "trial_id"])
    constrained = m[m.rho_ar1.abs() < 0.10]
    selectors["D_max_sharpe_rho_lt_010"] = int(constrained.loc[constrained.sharpe_a_raw.idxmax(), "trial_id"]) if not constrained.empty else None

    chosen_params = {}
    for k, tid in selectors.items():
        if tid is None:
            continue
        row = m[m.trial_id == tid].iloc[0]
        chosen_params[k] = {"trial_id": int(tid), "mc": row.mc, "thr": row.thr, "msp": row.msp}

    # convergenza su (mc, thr, msp) — usa stringhe per gestire NaN (nan!=nan in tuple)
    def _sig(c):
        def _norm(v):
            try:
                return "NA" if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v)
            except Exception:
                return str(v)
        return f"mc={_norm(c['mc'])}|thr={_norm(c['thr'])}|msp={_norm(c['msp'])}"
    sigs = [_sig(c) for c in chosen_params.values()]
    from collections import Counter
    top, top_count = Counter(sigs).most_common(1)[0]
    pct_converge = top_count / len(sigs)

    return {
        "pass": top_count >= 3,
        "selectors": chosen_params,
        "most_common_signature": top,
        "n_converging": top_count,
        "n_selectors": len(sigs),
        "all_signatures": sigs,
        "threshold": "≥3/4 selettori convergenti",
    }


# ─── H4: Sharpe operativo Backtrader best_param F2 OOS ≥ 1.5 ──────────────────
def test_h4(results_df: pd.DataFrame, fold_id: int = 2) -> dict:
    if results_df.empty:
        return {"pass": None, "reason": "results vuoto"}
    f2 = results_df[results_df["fold_id"] == fold_id]
    if f2.empty:
        return {"pass": None, "reason": f"fold {fold_id} assente"}
    # wf_runner espone best_param OOS Sharpe Backtrader come oos_sharpe_bt
    row = f2.iloc[0]
    sharpe_bt = float(row.get("oos_sharpe_bt", np.nan))
    return {
        "pass": np.isfinite(sharpe_bt) and sharpe_bt >= 1.5,
        "fold_id": fold_id,
        "best_params": {
            "mc": row.get("param_min_concordant"),
            "thr": row.get("param_threshold"),
            "msp": row.get("param_max_sector_pct"),
        },
        "sharpe_bt_oos": sharpe_bt,
        "sharpe_a_oos": float(row.get("oos_sharpe_a", np.nan)),
        "threshold": "Sharpe BT ≥ 1.5",
    }


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"S1.5 esec 3 — Falsificazione H1-H4 — {datetime.now(CEST).isoformat()}")

    if not RESULTS_CSV.exists():
        raise SystemExit(f"FAIL: {RESULTS_CSV} non esiste — il run non è completato")
    if not EQUITY_CSV.exists():
        raise SystemExit(f"FAIL: {EQUITY_CSV} non esiste")

    results = pd.read_csv(RESULTS_CSV)
    equity = pd.read_csv(EQUITY_CSV)
    print(f"  results.csv: {len(results)} righe, fold {sorted(results['fold_id'].unique())}")
    print(f"  equity.csv: {len(equity)} righe")

    # F2 OOS metrics per trial (per H1, H2, H3)
    metrics_f2 = load_per_trial_oos_metrics(equity, fold_id=2)
    print(f"  F2 OOS trial: {len(metrics_f2)}")

    h1 = test_h1(metrics_f2)
    h2 = test_h2(metrics_f2)
    h3 = test_h3(metrics_f2)
    h4 = test_h4(results, fold_id=2)

    overall_pass = all([h1.get("pass"), h2.get("pass"), h3.get("pass"), h4.get("pass")])

    report = {
        "timestamp_cest": datetime.now(CEST).isoformat(),
        "preregistration_sha": "a2790d3c7ee73b355314e9699c9d7e2194312e3b50d3d7f0bb6ae3a091e00ecc",
        "addendum_universo_sha": "0bbca3a90499b56f0c008c83d9e3bb2b0c4ad2a617e3d469f259726019edd0c3",
        "grid": "GRID_S1_5_EXEC3 (6×3×2=36 combo)",
        "universe": "portfolio (35 ticker)",
        "fold_target": "F2",
        "metrics_f2_oos": metrics_f2.to_dict(orient="records"),
        "H1": h1,
        "H2": h2,
        "H3": h3,
        "H4": h4,
        "overall_pass": overall_pass,
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))

    # Markdown report
    lines = [
        "# S1.5 esec 3 — Report falsificazione H1-H4",
        "",
        f"**Timestamp**: {report['timestamp_cest']}",
        f"**Preregistration SHA**: `{report['preregistration_sha']}`",
        f"**Addendum 01 universo SHA**: `{report['addendum_universo_sha']}`",
        f"**Grid**: {report['grid']}",
        f"**Universo**: {report['universe']}",
        "",
        "## H1 — Non-degenerazione (≤25% trial con stat identiche, su trial validi)",
        f"- Esito: **{'PASS' if h1.get('pass') else 'FAIL'}**",
        f"- N trial OOS F2 totali: {h1.get('n_trials_total')}",
        f"- N trial invalidi (Sharpe NaN, portfolio flat): {h1.get('n_trials_invalid_nan')}",
        f"- N trial validi: {h1.get('n_trials_valid')}",
        f"- N degenerati (sui validi): {h1.get('n_degenerate')} ({h1.get('pct_degenerate')}%)",
        f"- Coppie degenere: {h1.get('degenerate_pairs')}",
        "",
        "## H2 — Monotonia ρ_AR(1) ~ mc (slope>0, p<0.10)",
        f"- Esito: **{'PASS' if h2.get('pass') else 'FAIL'}**",
        f"- Slope: {h2.get('slope'):.4f}" if isinstance(h2.get('slope'), (int, float)) else f"- Slope: {h2.get('slope')}",
        f"- p-value: {h2.get('p_value'):.4f}" if isinstance(h2.get('p_value'), (int, float)) else f"- p-value: {h2.get('p_value')}",
        f"- ρ medio per mc: {h2.get('rho_mean_per_mc')}",
        "",
        "## H3 — Convergenza selettori (≥3/4)",
        f"- Esito: **{'PASS' if h3.get('pass') else 'FAIL'}**",
        f"- N convergenti su {h3.get('n_selectors')}: {h3.get('n_converging')}",
        f"- Signature più comune: `{h3.get('most_common_signature')}`",
        f"- Signature per selettore: `{h3.get('all_signatures')}`",
        f"- Dettaglio selettori: `{h3.get('selectors')}`",
        "",
        "## H4 — Sharpe operativo Backtrader best_param F2 OOS ≥ 1.5",
        f"- Esito: **{'PASS' if h4.get('pass') else 'FAIL'}**",
        f"- Sharpe BT OOS: {h4.get('sharpe_bt_oos')}",
        f"- Sharpe raw a OOS: {h4.get('sharpe_a_oos')}",
        f"- Best params: `{h4.get('best_params')}`",
        "",
        f"## Verdetto complessivo: **{'PASS' if overall_pass else 'FAIL'}**",
        "",
        "Se PASS → procedere con leverage analysis.",
        "Se FAIL su qualsiasi H → escalation S2 dedicata, NO unificazione con Bug 8.",
        "",
        f"— Generato automaticamente da `s15_exec3_falsification.py`, {datetime.now(CEST).isoformat()}",
    ]
    OUT_MD.write_text("\n".join(lines))

    print(f"\n  H1: {'PASS' if h1.get('pass') else 'FAIL'}  H2: {'PASS' if h2.get('pass') else 'FAIL'}  "
          f"H3: {'PASS' if h3.get('pass') else 'FAIL'}  H4: {'PASS' if h4.get('pass') else 'FAIL'}")
    print(f"  Verdetto: {'PASS' if overall_pass else 'FAIL'}")
    print(f"  Output: {OUT_MD}")
    print(f"  Output: {OUT_JSON}")


if __name__ == "__main__":
    main()
