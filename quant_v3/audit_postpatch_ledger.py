"""
Audit post-patch B2 — confronto ledger F3 IS+OOS pre vs post-patch.

Step:
  A.0 — NAV check al bar `oos_start - 1` per F3 (e check incrociato F2 OOS):
        verifica che NAV[oos_start-1] == cash_iniziale entro 1 EUR.
        Falsifica ipotesi C (gate residuo non chiude completamente).
  A.1 — Diff ledger F3 OOS pre vs post: match su (ticker, entry_price ± 0.5%).
  A.2 — Per ogni trade pre-patch scomparso: era carry-over (dt_open < oos_start)
        o intra-fold? Discrimina ipotesi A vs B.
  A.3 — Ledger F3 IS post: il 14° trade ha dt_open nei primi giorni del fold IS?

Input pre-patch: /tmp/yahoo-proxy-missere/quant_v3/wf_full_v73_trades.csv
Output: /home/user/workspace/audit_postpatch_output.txt
"""
import sys
from pathlib import Path
from datetime import datetime, date
import csv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.data_loader import DataLakeLoader
from engine.constraints import load_metadata
from engine.wf_runner import make_backtest_runner

PARAMS = {
    'threshold': 0.25,
    'min_concordant': 2,
    'target_risk_pct': 0.008,
    'max_sector_pct': 0.30,
    'max_portfolio_beta': None,
}
FIXED = {
    'max_positions': 10,
    'per_ticker_cap': 0.10,
    'warmup_bars': 50,
    'sizing_method': 'vol_target',
    'min_position_pct': 0.005,
    'vol_floor_pct': 0.005,
    'vol_proxy': 'atr',
    'vol_lookback': 14,
    'quality_filter_enabled': True,
    'value_floor': -0.5,
    'quality_floor': -0.5,
    'verbose': False,
    'target_risk_pct': 0.01,
    'regime_mode': 'off',
    'vix_feed_name': None,
}

FOLDS = {
    'F3_IS': (datetime(2025, 2, 1), datetime(2026, 2, 1)),
    'F3_OOS': (datetime(2026, 2, 1), datetime(2026, 5, 1)),
    # F2 OOS per check incrociato NAV.
    'F2_OOS': (datetime(2025, 11, 1), datetime(2026, 2, 1)),
}
CASH_INIT = 100_000.0

print("=" * 80)
print("AUDIT POST-PATCH B2 — diff ledger F3 + NAV check")
print("=" * 80)

# Setup dati
print("\nCaricamento bundles...")
loader = DataLakeLoader()
tickers = loader.list_tickers('portfolio', apply_filters=True)
bundles = {}
for t in tickers:
    b = loader.load_ticker(t, 'portfolio')
    if b is not None:
        bundles[t] = b
print(f"Bundles: {len(bundles)}/{len(tickers)}")

META_PATH = ROOT / 'data/meta/sector_beta.parquet'
sector_map, beta_map = load_metadata(META_PATH)

# Factory unica (post-Bug 7 refactor) con with_ledger=True
runner = make_backtest_runner(
    bundles=bundles,
    tickers=list(bundles.keys()),
    universe='portfolio',
    cash=CASH_INIT,
    commission=0.001,
    metadata_path=META_PATH,
    sector_map_cache=sector_map,
    beta_map_cache=beta_map,
    fixed_params=FIXED,
    attach_returns=True,
    with_ledger=True,
)

# ─── A.0 — NAV check pre-OOS ────────────────────────────────────────────────
print("\n" + "─" * 80)
print("A.0 — NAV check al bar PRIMO del fold (proxy NAV[oos_start])")
print("─" * 80)
print("Test: cum_return dal primo bar del fold deve essere ~0 se NAV[oos_start-1]")
print("      == cash_init. Equivalente: rets[0] dev'essere il return reale del giorno")
print("      oos_start, non un balzo NAV iniziale.")
print("─" * 80)

a0_results = {}
for label, (start, end) in FOLDS.items():
    metrics, trades = runner(PARAMS, start, end)
    daily = metrics.daily_returns
    if not daily:
        print(f"{label}: NO DAILY RETURNS")
        continue
    first_dt, first_ret = daily[0]
    print(f"{label}:")
    print(f"  first_bar = {first_dt}  first_return = {first_ret:+.6f}")
    print(f"  n_bars = {metrics.n_bars}  pnl_pct_fold = {metrics.pnl_pct:+.4f}")
    print(f"  sharpe_a = {metrics.sharpe_a:+.4f}  trades = {metrics.trades}")
    a0_results[label] = (metrics, trades, daily)

# ─── A.1 — Diff trade F3 OOS pre vs post ─────────────────────────────────────
print("\n" + "─" * 80)
print("A.1 — Diff ledger F3 OOS: pre-patch (12 trade) vs post-patch")
print("─" * 80)

# Carico trade pre-patch da CSV (fold_id=3 = F3 nel CSV; il CSV ha solo OOS
# perché lo schema riporta `oos_start/oos_end` ma nessuna colonna phase: erano
# stati dump solo OOS nella v7.2).
PRE_TRADES_F3_OOS = []
with open(ROOT / 'wf_full_v73_trades.csv') as f:
    rdr = csv.DictReader(f)
    for row in rdr:
        if row['fold_id'] == '3':
            PRE_TRADES_F3_OOS.append(row)

print(f"\nPre-patch F3 OOS: {len(PRE_TRADES_F3_OOS)} trade")
print(f"Post-patch F3 OOS: {a0_results['F3_OOS'][0].trades} trade (riportato da TradeAnalyzer)")

post_trades_f3_oos = a0_results['F3_OOS'][1]
print(f"Post-patch ledger F3 OOS: {len(post_trades_f3_oos)} record (ledger)")

# Match: stesso ticker + entry_price entro 0.5%
def match(pre_row, post_row):
    if pre_row['ticker'] != post_row['ticker']:
        return False
    try:
        pre_p = float(pre_row['entry_price'])
        post_p = float(post_row['entry_price'])
    except (KeyError, ValueError, TypeError):
        return False
    if pre_p == 0:
        return post_p == 0
    return abs(pre_p - post_p) / abs(pre_p) < 0.005

matched = []
unmatched_pre = []
for pre in PRE_TRADES_F3_OOS:
    found = None
    for post in post_trades_f3_oos:
        if match(pre, post):
            found = post
            break
    if found:
        matched.append((pre, found))
    else:
        unmatched_pre.append(pre)

unmatched_post = []
for post in post_trades_f3_oos:
    if not any(match(pre, post) for pre, _ in matched):
        unmatched_post.append(post)

print(f"\nMatched: {len(matched)}  scomparsi (in pre, non in post): {len(unmatched_pre)}  nuovi (in post, non in pre): {len(unmatched_post)}")

# ─── A.2 — Diagnosi trade scomparsi ─────────────────────────────────────────
print("\n" + "─" * 80)
print("A.2 — Trade scomparsi: erano carry-over (dt_open < 2026-02-01)?")
print("─" * 80)
OOS_START_F3 = date(2026, 2, 1)

# Per i pre-patch chiusi (status=closed) abbiamo dt_open. Per gli open_at_end
# pre-patch NaT (Bug 4 attivo in v7.2). Strategia: assumiamo i 30 open_at_end
# pre-patch sono carry-over di alta probabilità (Bug 5 li avrebbe bloccati).
# Verifichiamo questa assunzione via prezzo entry: se entry_price coincide con
# il close di una data PRE oos_start, è carry-over.

print(f"\n{'Ticker':<10} {'Status pre':<13} {'Entry$':>10} {'dt_open pre':<22} {'pnl_pct pre':>10} {'Classif':>12}")
print("─" * 80)

for pre in unmatched_pre:
    tk = pre['ticker']
    status = pre['status']
    entry = float(pre['entry_price'])
    dt_open_pre = pre['dt_open'] if pre['dt_open'] else '(NaT — Bug 4)'
    pnl_pct = float(pre['pnl_pct'])

    # Classif: closed con dt_open < oos_start → carry-over confermato
    classif = '?'
    if status == 'closed' and pre['dt_open']:
        try:
            dt = datetime.fromisoformat(pre['dt_open']).date()
            classif = 'CARRY-OVER' if dt < OOS_START_F3 else 'intra-fold'
        except Exception:
            classif = 'unknown'
    elif status == 'open_at_end':
        classif = 'SOSPETTO carry-over'

    print(f"{tk:<10} {status:<13} {entry:>10.2f} {dt_open_pre:<22} {pnl_pct:>+10.3f} {classif:>12}")

# Aggregati pnl% dei "scomparsi"
total_pnl_scomparsi = sum(float(p['pnl_pct']) * float(p['notional_open']) / 100_000.0 for p in unmatched_pre)
print(f"\nTotale contributo % NAV dei trade scomparsi (pnl_pct × notional / cash_init): {total_pnl_scomparsi:+.3f}%")
print(f"Δ pnl% F3 OOS osservato (post − pre): {a0_results['F3_OOS'][0].pnl_pct:.3f} − 7.539 = {a0_results['F3_OOS'][0].pnl_pct - 7.539:+.3f}%")

# ─── A.3 — Verifica 14° trade IS post-patch ──────────────────────────────────
print("\n" + "─" * 80)
print("A.3 — 14° trade F3 IS post-patch: dt_open nei primi giorni del fold?")
print("─" * 80)
IS_START_F3 = date(2025, 2, 1)
post_trades_f3_is = a0_results['F3_IS'][1]
print(f"Ledger F3 IS post-patch: {len(post_trades_f3_is)} record")
print(f"\n{'#':>3} {'Ticker':<10} {'Status':<13} {'dt_open':<22} {'Entry$':>10} {'pnl_pct':>10}")
print("─" * 80)
# Ordino per dt_open ascending (NaT/'' in fondo)
def _sort_key(t):
    d = t.get('dt_open') or ''
    return d
for i, t in enumerate(sorted(post_trades_f3_is, key=_sort_key), 1):
    dt = t.get('dt_open') or '(NaT)'
    print(f"{i:>3} {t['ticker']:<10} {t['status']:<13} {dt:<22} {float(t['entry_price']):>10.2f} {float(t['pnl_pct']):>+10.3f}")

print("\nVerifica V3: tra i 14 trade F3 IS post-patch, quanti hanno dt_open nei")
print("primi 5 BD del fold IS (2025-02-01 → 2025-02-07)?")
early_count = 0
for t in post_trades_f3_is:
    dt_str = t.get('dt_open') or ''
    if not dt_str:
        continue
    try:
        dt = datetime.fromisoformat(dt_str).date()
        if IS_START_F3 <= dt <= date(2025, 2, 7):
            early_count += 1
    except Exception:
        continue
print(f"Early trades (entro 1 settimana fold IS start): {early_count}")

print("\n" + "=" * 80)
print("AUDIT COMPLETO")
print("=" * 80)
