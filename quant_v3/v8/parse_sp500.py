"""Parse Wikipedia S&P 500 markdown content into CSV.

Two tables expected:
1. Current components (Symbol|Security|GICS Sector|...)
2. Recent changes (Date|Added|Removed|Reason)
"""
import csv
import re
import sys
from pathlib import Path

src = Path("/tmp/sp500_wiki.md").read_text()

# ------------------------------------------------------------------
# Table 1: current components
# ------------------------------------------------------------------
# Match the header line and capture all subsequent rows until blank
lines = src.splitlines()
current_rows = []
changes_rows = []

mode = None  # 'current' | 'changes' | None
header_current = None
header_changes = None

for i, line in enumerate(lines):
    s = line.strip()
    if s.startswith("|Symbol|Security|GICS Sector|"):
        mode = "current"
        header_current = [c.strip() for c in s.strip("|").split("|")]
        continue
    if s.startswith("|Date|") and "Added" in s and "Removed" in s:
        mode = "changes"
        header_changes = [c.strip() for c in s.strip("|").split("|")]
        continue
    if mode == "current":
        if s.startswith("|--"):
            continue
        if not s.startswith("|") or "|" not in s[1:]:
            mode = None
            continue
        parts = [c.strip() for c in s.strip("|").split("|")]
        if len(parts) >= 3 and parts[0] and parts[0] != "Symbol":
            current_rows.append(parts)
    elif mode == "changes":
        if s.startswith("|--"):
            continue
        if not s.startswith("|") or "|" not in s[1:]:
            mode = None
            continue
        parts = [c.strip() for c in s.strip("|").split("|")]
        if len(parts) >= 4 and parts[0]:
            changes_rows.append(parts)

print(f"Current components: {len(current_rows)}")
print(f"Changes rows: {len(changes_rows)}")
print(f"Header current: {header_current}")
print(f"Header changes: {header_changes}")

# ------------------------------------------------------------------
# Save current snapshot CSV
# ------------------------------------------------------------------
out_current = Path("/home/user/workspace/sp500_snapshot_2026_05_23.csv")
with out_current.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ticker", "security", "gics_sector", "gics_sub_industry",
                "hq_location", "date_added", "cik", "founded"])
    for r in current_rows:
        # Pad/truncate to 8 columns
        r = (r + [""] * 8)[:8]
        w.writerow(r)

print(f"Saved {out_current} ({out_current.stat().st_size} bytes)")

# ------------------------------------------------------------------
# Save changes table (parsed automatically)
# ------------------------------------------------------------------
out_changes = Path("/home/user/workspace/sp500_changes_raw.csv")
if changes_rows:
    with out_changes.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header_changes)
        for r in changes_rows:
            r = (r + [""] * len(header_changes))[:len(header_changes)]
            w.writerow(r)
    print(f"Saved {out_changes} ({out_changes.stat().st_size} bytes)")

# Show first 3 rows of each
print("\n--- First 3 current ---")
for r in current_rows[:3]:
    print(r[:4])
print("\n--- First 5 changes ---")
for r in changes_rows[:5]:
    print(r)
