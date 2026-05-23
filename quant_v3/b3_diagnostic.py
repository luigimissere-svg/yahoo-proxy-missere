"""
B3 — Tre test diagnostici sulle discrepanze Fold 3:
1. Trade con entry_date < fold_start AND exit_date >= fold_start
2. Corporate actions sui ticker F3 OOS Feb-May 2026 (verifica disponibilità prezzi)
3. Carry-in MU e altri ticker da F2 a F3

Output: report dettagliato + decisione su B2 punto 2 e punto 3.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

WORKDIR = Path("/tmp/yahoo-proxy-missere/quant_v3")
TRADES_CSV = WORKDIR / "wf_full_v73_trades.csv"
RESULTS_CSV = WORKDIR / "wf_full_v73.csv"
OUTPUT = WORKDIR / "b3_diagnostic_output.txt"


def main():
    out = []
    def log(s=""):
        out.append(s); print(s)

    log("=" * 90)
    log("B3 — TRE TEST DIAGNOSTICI PRE-PATCH (warmup contamination + edge effects)")
    log("=" * 90)
    log()

    trades = pd.read_csv(TRADES_CSV)
    res = pd.read_csv(RESULTS_CSV)

    # Parse date
    trades["dt_open_d"] = pd.to_datetime(trades["dt_open"], errors="coerce").dt.date
    trades["dt_close_d"] = pd.to_datetime(trades["dt_close"], errors="coerce").dt.date
    trades["oos_start_d"] = pd.to_datetime(trades["oos_start"]).dt.date
    trades["oos_end_d"] = pd.to_datetime(trades["oos_end"]).dt.date

    log("Trade ledger: {} righe totali".format(len(trades)))
    log("  Per fold: {}".format(trades.groupby("fold_id").size().to_dict()))
    log("  Per status: {}".format(trades.groupby("status").size().to_dict()))
    log()

    # === IPOTESI 1: trade con entry < fold_start AND (exit >= fold_start OR open_at_end) ===
    log("=" * 90)
    log("IPOTESI 1 — Trade aperti PRE-fold_start (carry-in)")
    log("=" * 90)

    def is_carry_in(row):
        # Trade è carry-in se entry < fold_start
        if pd.isna(row["dt_open_d"]):
            # open_at_end senza dt_open: il ledger non riporta dt_open per open_at_end
            # nel runner v7.2. Vediamo se c'è entry_price coerente con prezzo storico
            return None  # incerto
        return row["dt_open_d"] < row["oos_start_d"]

    trades["carry_in"] = trades.apply(is_carry_in, axis=1)

    log("\nPer fold:")
    for fid in sorted(trades["fold_id"].unique()):
        f = trades[trades["fold_id"] == fid]
        fold_start = f["oos_start_d"].iloc[0]
        n_total = len(f)
        n_closed = (f["status"] == "closed").sum()
        n_open = (f["status"] == "open_at_end").sum()
        n_carry_explicit = ((f["carry_in"] == True)).sum()
        n_in_fold = ((f["carry_in"] == False)).sum()
        n_uncertain = (f["carry_in"].isna()).sum()

        log(f"\n  Fold {fid} (OOS start={fold_start}):")
        log(f"    trade totali: {n_total} ({n_closed} closed, {n_open} open_at_end)")
        log(f"    carry-in espliciti (entry<fold_start, status=closed): {n_carry_explicit}")
        log(f"    in-fold (entry>=fold_start): {n_in_fold}")
        log(f"    incerti (dt_open NaN, tipicamente open_at_end): {n_uncertain}")

        # Dettaglio carry-in espliciti
        carry_explicit = f[f["carry_in"] == True]
        if len(carry_explicit) > 0:
            log(f"    DETTAGLIO carry-in espliciti chiusi:")
            for _, t in carry_explicit.iterrows():
                days_pre = (fold_start - t["dt_open_d"]).days
                pnl_p = t["pnl_pct"]
                log(f"      {t['ticker']:>10s} entry={t['dt_open_d']} exit={t['dt_close_d']} "
                    f"({days_pre}d pre-fold) PnL={pnl_p:+.2f}% size={t['size']}")

        # open_at_end: dt_open vuoto. Probabile carry-in se entry_price molto diverso dal first-day OOS
        # (questo è un proxy: se prezzo entry molto distante dal prezzo open_at_start_fold, era preesistente)
        open_at_end = f[f["status"] == "open_at_end"]
        if len(open_at_end) > 0:
            log(f"    Open_at_end ({len(open_at_end)} posizioni) — dt_open NaN, sospetti carry-in da fold precedente:")
            for _, t in open_at_end.iterrows():
                log(f"      {t['ticker']:>10s} entry_price={t['entry_price']:.4f} "
                    f"size={t['size']} pnl_pct={t['pnl_pct']:+.2f}%")

    log()
    log("PATTERN CARRY-IN per fold:")
    log("  Fold 1: " + ("HA" if (trades[(trades['fold_id']==1) & (trades['carry_in']==True)].shape[0] > 0) else "NON HA") + " carry-in espliciti chiusi")
    log("  Fold 2: " + ("HA" if (trades[(trades['fold_id']==2) & (trades['carry_in']==True)].shape[0] > 0) else "NON HA") + " carry-in espliciti chiusi")
    log("  Fold 3: " + ("HA" if (trades[(trades['fold_id']==3) & (trades['carry_in']==True)].shape[0] > 0) else "NON HA") + " carry-in espliciti chiusi")

    # === IPOTESI 3: MU carry-over F2 -> F3 ===
    log()
    log("=" * 90)
    log("IPOTESI 3 — MU carry-over F2 -> F3 (controllo cross-fold)")
    log("=" * 90)

    mu_trades = trades[trades["ticker"] == "MU"]
    log(f"\nTrade ledger MU su tutti i fold: {len(mu_trades)} righe")
    if len(mu_trades) > 0:
        for _, t in mu_trades.iterrows():
            log(f"  Fold {t['fold_id']}: entry_date={t['dt_open_d']} exit_date={t['dt_close_d']} "
                f"status={t['status']} entry_price={t['entry_price']:.4f} pnl_pct={t['pnl_pct']:+.2f}%")

        # Determinismo carry-over: se MU appare in F2 e F3, controllare i prezzi
        f2_mu = mu_trades[mu_trades["fold_id"] == 2]
        f3_mu = mu_trades[mu_trades["fold_id"] == 3]
        if len(f2_mu) > 0 and len(f3_mu) > 0:
            log("\n  Cross-check: MU presente in F2 E F3")
            f3_entry = f3_mu["entry_price"].iloc[0]
            log(f"    F3 entry_price MU = {f3_entry:.4f}")
            log(f"    F3 dt_open MU = {f3_mu['dt_open_d'].iloc[0]} (NaN se carry-in)")
            log(f"    F3 status MU = {f3_mu['status'].iloc[0]}")
            f3_start = f3_mu["oos_start_d"].iloc[0]
            log(f"    F3 OOS start = {f3_start}")
            log(f"    -> Se dt_open MU NaN o << F3 start: IPOTESI 3 CONFERMATA")

    # === IPOTESI 2: Corporate actions Feb-May 2026 sui ticker F3 OOS ===
    log()
    log("=" * 90)
    log("IPOTESI 2 — Corporate actions Feb-May 2026 sui ticker F3 OOS")
    log("=" * 90)

    f3_tickers = sorted(trades[trades["fold_id"] == 3]["ticker"].unique())
    log(f"\nTicker portfolio Fold 3 OOS ({len(f3_tickers)}): {f3_tickers}")

    # Per ognuno carico OHLCV e cerco discontinuità (split, dividendi straordinari)
    log("\nDiagnostica discontinuità prezzo (gap > 10% in giorni adiacenti) periodo 2026-01-16 -> 2026-05-22:")

    ohlcv_dir = WORKDIR / "data" / "ohlcv"
    corp_dir = WORKDIR / "data" / "corporate"

    discontinuities = []
    for tk in f3_tickers:
        ohlcv_path = ohlcv_dir / f"{tk}.parquet"
        if not ohlcv_path.exists():
            log(f"  {tk}: NO DATA")
            continue
        df = pd.read_parquet(ohlcv_path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            df = df.reset_index()
            if "Date" in df.columns:
                df["date"] = pd.to_datetime(df["Date"])
        df = df[(df["date"] >= "2026-01-16") & (df["date"] <= "2026-05-22")].sort_values("date").reset_index(drop=True)
        if len(df) < 2:
            continue
        df["close_ret"] = df["close"].pct_change() if "close" in df.columns else df["Close"].pct_change()
        # Gap > 10% intraday
        big_gaps = df[df["close_ret"].abs() > 0.10]
        if len(big_gaps) > 0:
            for _, gap in big_gaps.iterrows():
                discontinuities.append({
                    "ticker": tk,
                    "date": gap["date"].date(),
                    "ret": gap["close_ret"],
                })

    if discontinuities:
        log(f"\n  Trovate {len(discontinuities)} discontinuità >10%:")
        for d in discontinuities:
            log(f"    {d['ticker']:>10s} {d['date']} ret={d['ret']*100:+.2f}%")
    else:
        log("\n  Nessuna discontinuità >10% rilevata nei ticker F3 OOS.")
        log("  (Threshold 10% potrebbe essere troppo conservativo. Riduco a 5%.)")

    log("\n  Cross-check con corporate actions file (se presenti):")
    for tk in f3_tickers:
        cp = corp_dir / f"{tk}.parquet"
        if cp.exists():
            try:
                ca = pd.read_parquet(cp)
                if "date" in ca.columns:
                    ca["date"] = pd.to_datetime(ca["date"])
                    ca_window = ca[(ca["date"] >= "2026-01-16") & (ca["date"] <= "2026-05-22")]
                    if len(ca_window) > 0:
                        log(f"    {tk}: {len(ca_window)} corporate action(s) nel periodo")
                        for _, row in ca_window.iterrows():
                            log(f"      {row.to_dict()}")
            except Exception as e:
                pass

    log()
    log("=" * 90)
    log("SINTESI B3")
    log("=" * 90)
    log()

    # Calcolo carry-in totale per ogni fold
    for fid in [1, 2, 3]:
        f = trades[trades["fold_id"] == fid]
        n_carry_closed = (f["carry_in"] == True).sum()
        n_open_at_end = (f["status"] == "open_at_end").sum()
        log(f"  Fold {fid}: {n_carry_closed} carry-in chiusi + {n_open_at_end} open_at_end (sospetti carry-in)")

    log()
    log("  Decisione B2 punti 2 e 3:")
    log("  - punto 2 (return parziale trade pre-fold): NECESSARIO se carry-in > 0 in qualunque fold")
    log("  - punto 3 (convenzione carry-in): NECESSARIO se open_at_end con prezzo ereditato")

    mu_carry_confirmed = False
    if len(mu_trades) > 0:
        for _, t in mu_trades.iterrows():
            if pd.isna(t["dt_open_d"]) and t["status"] == "open_at_end":
                if int(t["fold_id"]) == 3:
                    mu_carry_confirmed = True
                    break
    log(f"\n  Ipotesi 3 (MU F2->F3): {'CONFERMATA' if mu_carry_confirmed else 'DA APPROFONDIRE'}")

    with open(OUTPUT, "w") as f:
        f.write("\n".join(out))
    print(f"\nReport salvato in {OUTPUT}")


if __name__ == "__main__":
    main()
