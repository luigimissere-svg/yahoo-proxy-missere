"""Build point-in-time S&P 500 universe.

Strategy:
  1. Start from snapshot at 2026-05-23 (503 current components)
  2. Reverse-replay change events: per ogni evento, undo additions and undo removals
  3. Output: universe_v8_sp500_pit.csv with one row per (ticker, period)

Output schema:
  ticker, security, gics_sector, in_universe_from, in_universe_to, reason_added, reason_removed
  - in_universe_from: data di ingresso nell'S&P 500 (NaN se prima del 2020-01-01)
  - in_universe_to: data di uscita (NaN se ancora presente al 2026-05-23)

Membership query:
  universe(date) = { ticker | (in_universe_from <= date OR isnan) AND (in_universe_to > date OR isnan) }
"""
import csv
import json
from datetime import datetime, date
from pathlib import Path

SNAPSHOT_DATE = "2026-05-23"
HISTORY_START = "2020-01-01"  # esteso indietro fino a qui

# Load snapshot
snapshot = {}
with open("/home/user/workspace/sp500_snapshot_2026_05_23.csv") as f:
    rdr = csv.DictReader(f)
    for r in rdr:
        t = r["ticker"].strip()
        if not t:
            continue
        snapshot[t] = {
            "security": r["security"],
            "gics_sector": r["gics_sector"],
            "gics_sub_industry": r["gics_sub_industry"],
            "date_added": r["date_added"],
        }
print(f"Snapshot 2026-05-23: {len(snapshot)} ticker")

# Load changes (sorted by date asc)
changes = []
with open("/home/user/workspace/sp500_changes_2020_2026.csv") as f:
    rdr = csv.DictReader(f)
    for r in rdr:
        changes.append({
            "date": r["date_iso"],
            "added_t": r["added_ticker"].strip(),
            "added_s": r["added_security"].strip(),
            "removed_t": r["removed_ticker"].strip(),
            "removed_s": r["removed_security"].strip(),
            "reason": r["reason"].strip(),
        })
changes.sort(key=lambda x: x["date"])
print(f"Changes 2020-2026: {len(changes)} events")

# Build membership map: ticker -> list of (from, to, reason)
# Approach: walk events asc. Maintain current_set. Record entry/exit per ticker.
current = set(snapshot.keys())

# But snapshot represents END state. To build history, we reverse-walk from snapshot:
# Going backwards: undo each event.
#   If event added X and removed Y at date D:
#     Before D: X NOT in set, Y in set
#   So when reverse-walking:
#     current.discard(added_t)  # X was added at D, so before D it was absent
#     current.add(removed_t)    # Y was removed at D, so before D it was present
#
# We record (ticker, in_from, in_to, ...) by tracking when each ticker enters/exits.

membership = {}  # ticker -> {security, gics_sector, in_from, in_to, reason_added, reason_removed}

# Initialize: all snapshot tickers are currently "in" with in_to = None (still present)
for t, meta in snapshot.items():
    membership[t] = {
        "security": meta["security"],
        "gics_sector": meta["gics_sector"],
        "in_from": None,  # da determinare in walk
        "in_to": None,    # ancora presente al 23/05/2026
        "reason_added": "",
        "reason_removed": "",
    }

# Reverse-walk: events in descending order
for ev in reversed(changes):
    d = ev["date"]
    at = ev["added_t"]
    rt = ev["removed_t"]
    # Added ticker at date d: prima di d non era presente -> registriamo in_from = d
    if at:
        if at not in membership:
            membership[at] = {
                "security": ev["added_s"],
                "gics_sector": "",  # GICS non disponibile per added/removed
                "in_from": d,
                "in_to": None,
                "reason_added": ev["reason"],
                "reason_removed": "",
            }
        else:
            membership[at]["in_from"] = d
            if not membership[at]["reason_added"]:
                membership[at]["reason_added"] = ev["reason"]
        current.discard(at)
    # Removed ticker at date d: prima di d era presente -> aggiungiamo al set storico
    if rt:
        if rt not in membership:
            membership[rt] = {
                "security": ev["removed_s"],
                "gics_sector": "",
                "in_from": None,  # presente all'inizio della finestra
                "in_to": d,
                "reason_added": "",
                "reason_removed": ev["reason"],
            }
        else:
            # ticker già in membership (es. aggiunto in past poi rimosso poi riaggiunto)
            # Tracciamo come primo evento utile
            if not membership[rt]["in_to"]:
                membership[rt]["in_to"] = d
                membership[rt]["reason_removed"] = ev["reason"]
        current.add(rt)

print(f"\nTotal tickers in PIT universe (2020-01-01 to 2026-05-23): {len(membership)}")
print(f"  Of which currently in S&P 500 (in_to is null): {sum(1 for v in membership.values() if v['in_to'] is None)}")
print(f"  Of which removed during window: {sum(1 for v in membership.values() if v['in_to'])}")

# Write CSV
out = Path("/home/user/workspace/universe_v8_sp500_pit.csv")
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ticker", "security", "gics_sector", "in_universe_from",
                "in_universe_to", "reason_added", "reason_removed"])
    for t in sorted(membership.keys()):
        m = membership[t]
        w.writerow([t, m["security"], m["gics_sector"],
                    m["in_from"] or "", m["in_to"] or "",
                    m["reason_added"], m["reason_removed"]])
print(f"\nSaved: {out} ({out.stat().st_size} bytes)")

# Test query: membership at 2024-01-01
def universe_at(target_date_str, membership):
    td = target_date_str
    result = set()
    for t, m in membership.items():
        from_ok = (m["in_from"] is None) or (m["in_from"] <= td)
        to_ok = (m["in_to"] is None) or (m["in_to"] > td)
        if from_ok and to_ok:
            result.add(t)
    return result

u_2026 = universe_at("2026-05-23", membership)
u_2024 = universe_at("2024-01-01", membership)
u_2022 = universe_at("2022-01-01", membership)
u_2020 = universe_at("2020-01-01", membership)

print(f"\nUniverse size by date (point-in-time):")
print(f"  2020-01-01: {len(u_2020)} ticker")
print(f"  2022-01-01: {len(u_2022)} ticker")
print(f"  2024-01-01: {len(u_2024)} ticker")
print(f"  2026-05-23: {len(u_2026)} ticker")

print(f"\nDelta 2024-01-01 vs 2026-05-23:")
print(f"  In 2024 ma non in 2026 (rimossi nel periodo): {len(u_2024 - u_2026)}")
sample = sorted(u_2024 - u_2026)[:15]
print(f"  Sample: {sample}")
print(f"  In 2026 ma non in 2024 (aggiunti nel periodo): {len(u_2026 - u_2024)}")
sample = sorted(u_2026 - u_2024)[:15]
print(f"  Sample: {sample}")

# Save universe_at samples as JSON snapshots
snapshots_out = Path("/home/user/workspace/universe_v8_snapshots.json")
snapshots_out.write_text(json.dumps({
    "2020-01-01": sorted(u_2020),
    "2022-01-01": sorted(u_2022),
    "2024-01-01": sorted(u_2024),
    "2026-05-23": sorted(u_2026),
}, indent=2))
print(f"\nSnapshot JSON saved: {snapshots_out}")
