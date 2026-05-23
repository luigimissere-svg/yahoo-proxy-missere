"""
Verifiche pre-patch warmup contamination (richieste dal consulente).

Dubbio 1: warmup ha return ≈ 0?
   Per ogni (trial, fold, phase) confronta le statistiche dei returns
   pre-fold vs in-fold. MA: il dump v7.3 ha già filtrato a [start, end],
   quindi i returns pre-fold NON SONO nel CSV. Devo confrontare indirettamente:
   - n_bars_saved (totale, incluso warmup) vs n_rows_dumped (filtrato fold)
   - n_nonzero_returns_saved (totale) vs n_nonzero_dumped
   Se n_nonzero_saved ≈ n_nonzero_dumped, il warmup è effettivamente "muto"
   (return = 0 per tutte le ~261 barre pre-fold).

Dubbio 2: trade a cavallo del confine?
   Confronta sum(returns_in_fold) vs oos_pnl_pct del results CSV
   per i best trial. Se coincidono entro tol, no edge effect.
   NB: il PnL è prodotto cumulato (1+r1)(1+r2)...-1, non somma.
   Quindi devo usare cum_return = prod(1+r) - 1.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

WORKDIR = Path("/tmp/yahoo-proxy-missere/quant_v3")
EQUITY_CSV = WORKDIR / "wf_full_v73_equity.csv"
RESULTS_CSV = WORKDIR / "wf_full_v73.csv"
OUTPUT = WORKDIR / "task2_pre_patch_verify_output.txt"


def main():
    out = []

    def log(s=""):
        out.append(s)
        print(s)

    log("=" * 90)
    log("VERIFICHE PRE-PATCH WARMUP CONTAMINATION (richieste dal consulente)")
    log("=" * 90)
    log()

    eq = pd.read_csv(EQUITY_CSV)
    res = pd.read_csv(RESULTS_CSV)

    # === DUBBIO 1: warmup ha return ≈ 0? ===
    # Indirettamente: confronto n_nonzero_returns (totale) vs nonzero nel dump
    log("=" * 90)
    log("DUBBIO 1 — Warmup ha return ≈ 0?")
    log("=" * 90)
    log()
    log("Strategia: confronto n_nonzero_returns SALVATO (totale, include warmup) vs")
    log("n_nonzero RICONTATO sulle righe dumpate (filtrate [start,end]).")
    log("Se warmup è 'muto' (return=0 sempre), allora nonzero_saved ≈ nonzero_dumped.")
    log("Se warmup ha trade, allora nonzero_saved > nonzero_dumped.")
    log()

    agg = (
        eq.groupby(["trial_id", "fold_id", "phase"])
        .agg(
            n_bars_saved=("n_bars", "first"),
            n_nonzero_saved=("n_nonzero_returns", "first"),
            n_rows_dumped=("daily_return", "size"),
            n_nonzero_dumped=("daily_return", lambda s: int((s.astype(float) != 0).sum())),
        )
        .reset_index()
    )
    agg["nonzero_extra_warmup"] = agg["n_nonzero_saved"] - agg["n_nonzero_dumped"]
    agg["warmup_n_bars"] = agg["n_bars_saved"] - agg["n_rows_dumped"]
    agg["pct_warmup_zero"] = 1 - (agg["nonzero_extra_warmup"] / agg["warmup_n_bars"])

    log(f"Trials totali: {len(agg)}")
    log()
    log("Statistiche per phase:")
    for phase in ["IS", "OOS"]:
        a = agg[agg["phase"] == phase]
        log(f"  {phase}:")
        log(f"    n trial:              {len(a)}")
        log(f"    n_bars_saved:         mean={a['n_bars_saved'].mean():.1f}  range=[{a['n_bars_saved'].min()},{a['n_bars_saved'].max()}]")
        log(f"    n_rows_dumped:        mean={a['n_rows_dumped'].mean():.1f}  range=[{a['n_rows_dumped'].min()},{a['n_rows_dumped'].max()}]")
        log(f"    warmup_n_bars:        mean={a['warmup_n_bars'].mean():.1f}  range=[{a['warmup_n_bars'].min()},{a['warmup_n_bars'].max()}]")
        log(f"    n_nonzero_saved:      mean={a['n_nonzero_saved'].mean():.1f}  range=[{a['n_nonzero_saved'].min()},{a['n_nonzero_saved'].max()}]")
        log(f"    n_nonzero_dumped:     mean={a['n_nonzero_dumped'].mean():.1f}  range=[{a['n_nonzero_dumped'].min()},{a['n_nonzero_dumped'].max()}]")
        log(f"    nonzero_extra_warmup: mean={a['nonzero_extra_warmup'].mean():.1f}  range=[{a['nonzero_extra_warmup'].min()},{a['nonzero_extra_warmup'].max()}]")
        log(f"    pct warmup ZERO:      mean={a['pct_warmup_zero'].mean()*100:.2f}%  median={a['pct_warmup_zero'].median()*100:.2f}%")
        log()

    log("VERDETTO Dubbio 1:")
    is_zero_pct = agg[agg["phase"] == "IS"]["pct_warmup_zero"].mean()
    oos_zero_pct = agg[agg["phase"] == "OOS"]["pct_warmup_zero"].mean()
    if is_zero_pct >= 0.95 and oos_zero_pct >= 0.95:
        log(f"  PASS — warmup è 95%+ zero in entrambe le fasi (IS={is_zero_pct*100:.1f}%, OOS={oos_zero_pct*100:.1f}%)")
        log(f"  Scenario A confermato: deflazione 1/√k è la diagnosi corretta.")
    else:
        log(f"  ATTENZIONE — warmup NON è 95%+ zero (IS={is_zero_pct*100:.1f}%, OOS={oos_zero_pct*100:.1f}%)")
        log(f"  Scenario B/C: il warmup contiene segnale residuo, la patch va pensata meglio.")
    log()

    # Distribuzione nonzero_extra_warmup per capire se ci sono trial anomali
    log("Distribuzione nonzero_extra_warmup (per fase):")
    for phase in ["IS", "OOS"]:
        a = agg[agg["phase"] == phase]
        log(f"  {phase}: pct trial con extra warmup=0:  "
            f"{(a['nonzero_extra_warmup']==0).mean()*100:.1f}%")
        log(f"  {phase}: pct trial con extra warmup<=2: "
            f"{(a['nonzero_extra_warmup']<=2).mean()*100:.1f}%")
        log(f"  {phase}: pct trial con extra warmup<=5: "
            f"{(a['nonzero_extra_warmup']<=5).mean()*100:.1f}%")
    log()

    # === DUBBIO 2: trade a cavallo del confine? ===
    log("=" * 90)
    log("DUBBIO 2 — Trade a cavallo del confine fold?")
    log("=" * 90)
    log()
    log("Strategia: confronto cum_return = prod(1+r)-1 sulle serie dumpate (filtrate")
    log("[start,end]) vs PnL pct del results CSV per i best trial per fold.")
    log("Se coincidono entro tol stretta, no edge effect.")
    log("Se PnL_saved > cum_return_dumped, ci sono trade a cavallo che il dump perde.")
    log()

    for _, fold_row in res.iterrows():
        fid = fold_row["fold_id"]
        log(f"--- Fold {fid} ---")

        # Match best params nel dump OOS
        params_target = {
            "threshold": fold_row["param_threshold"],
            "min_concordant": int(fold_row["param_min_concordant"]),
            "target_risk_pct": fold_row["param_target_risk_pct"],
            "max_sector_pct": None if pd.isna(fold_row["param_max_sector_pct"]) else fold_row["param_max_sector_pct"],
            "max_portfolio_beta": None if pd.isna(fold_row["param_max_portfolio_beta"]) else fold_row["param_max_portfolio_beta"],
        }

        for phase, pnl_col, fold_pnl in [
            ("IS", "is_pnl_pct", fold_row["is_pnl_pct"]),
            ("OOS", "oos_pnl_pct", fold_row["oos_pnl_pct"]),
        ]:
            eq_sub = eq[(eq["fold_id"] == fid) & (eq["phase"] == phase)]

            best_trial_id = None
            for trial_id, grp in eq_sub.groupby("trial_id"):
                pj = json.loads(grp["params_json"].iloc[0])
                if (abs(float(pj.get("threshold", -999)) - params_target["threshold"]) < 1e-9
                    and int(pj.get("min_concordant", -999)) == params_target["min_concordant"]
                    and abs(float(pj.get("target_risk_pct", -999)) - params_target["target_risk_pct"]) < 1e-9
                    and (pj.get("max_sector_pct") == params_target["max_sector_pct"]
                         or (pj.get("max_sector_pct") is not None and params_target["max_sector_pct"] is not None
                             and abs(float(pj["max_sector_pct"]) - params_target["max_sector_pct"]) < 1e-9))
                    and (pj.get("max_portfolio_beta") == params_target["max_portfolio_beta"]
                         or (pj.get("max_portfolio_beta") is not None and params_target["max_portfolio_beta"] is not None
                             and abs(float(pj["max_portfolio_beta"]) - params_target["max_portfolio_beta"]) < 1e-9))
                    ):
                    best_trial_id = trial_id
                    break

            if best_trial_id is None:
                log(f"  {phase}: nessun match params")
                continue

            grp = eq_sub[eq_sub["trial_id"] == best_trial_id]
            r = grp["daily_return"].astype(float).values
            cum_ret = ((1 + r).prod() - 1) * 100  # pct
            sum_ret = r.sum() * 100  # additive approx

            delta = cum_ret - fold_pnl
            log(f"  {phase} best trial #{best_trial_id} (n_bars dumpate={len(r)}):")
            log(f"    cum_return (prod-1) =  {cum_ret:.6f}%")
            log(f"    sum_return (additive)=  {sum_ret:.6f}%")
            log(f"    pnl_pct results CSV =  {fold_pnl:.6f}%")
            log(f"    delta (cum - pnl)   = {delta:+.6f}%")
            if abs(delta) < 0.5:
                log(f"    -> PASS (delta < 0.5pp, nessun edge effect significativo)")
            elif abs(delta) < 2.0:
                log(f"    -> MEDIO (delta 0.5-2.0pp, possibili trade a cavallo)")
            else:
                log(f"    -> ATTENZIONE (delta > 2pp, edge effect significativo)")
        log()

    log("=" * 90)
    log("CONCLUSIONI")
    log("=" * 90)
    log()

    # Decisione finale automatica
    cond1 = is_zero_pct >= 0.95 and oos_zero_pct >= 0.95
    log(f"Condizione 1 (Dubbio 1, warmup ≈ 0): {'PASS' if cond1 else 'FAIL'}")
    log("Condizione 2 (Dubbio 2, no edge): verifica visiva delta < 0.5pp per ogni fold/phase.")
    log()
    if cond1:
        log("Se anche Condizione 2 PASS:")
        log("  -> Scenario A pulito confermato")
        log("  -> Procedere con opzione A4 (patch runner + procedere su serie già dumpate)")
        log("  -> Sharpe corretti = quelli ricalcolati sulle serie dumpate")
    else:
        log("Se Condizione 1 FAIL:")
        log("  -> Scenario B/C: serve ragionamento più sofisticato")
        log("  -> Aprire ulteriore quesito al consulente prima di patchare")

    with open(OUTPUT, "w") as f:
        f.write("\n".join(out))
    print(f"\nReport salvato in {OUTPUT}")

    # CSV diagnostico
    agg.to_csv(WORKDIR / "task2_warmup_diag.csv", index=False)


if __name__ == "__main__":
    main()
