"""Estrai tabella S&P 500 changes da Wikipedia markdown.

Cattura tutte le righe del periodo 2020-2026 e produce CSV con:
  date, added_ticker, added_security, removed_ticker, removed_security, reason
"""
import csv
import re
from datetime import datetime
from pathlib import Path

src = Path("/tmp/sp500_wiki.md").read_text().splitlines()

# Trova il primo bordo della tabella changes
start = None
for i, line in enumerate(src):
    if line.strip().startswith("|Effective Date|Added|Added|Removed|Removed|Reason|"):
        start = i + 3  # salto header (2 righe) + separatore
        break

if start is None:
    raise SystemExit("Tabella changes non trovata")

rows = []
for line in src[start:]:
    s = line.strip()
    if not s.startswith("|"):
        break
    parts = [c.strip() for c in s.strip("|").split("|")]
    if len(parts) < 6:
        continue
    rows.append(parts[:6])

print(f"Raw rows parsed: {len(rows)}")

# Filtra periodo 01/01/2020 -> 23/05/2026 e produci CSV
month_map = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}

def parse_date(s):
    # Esempi: "May 7, 2026", "December 23, 2024"
    m = re.match(r"(\w+) (\d+), (\d{4})", s)
    if not m:
        return None
    mon, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    if mon not in month_map:
        return None
    try:
        return datetime(year, month_map[mon], day)
    except ValueError:
        return None

cutoff_start = datetime(2020, 1, 1)
cutoff_end   = datetime(2026, 5, 23)

filtered = []
for r in rows:
    dt = parse_date(r[0])
    if dt is None:
        continue
    if cutoff_start <= dt <= cutoff_end:
        filtered.append((dt.strftime("%Y-%m-%d"), *r[1:]))

print(f"Filtered (2020-01-01 to 2026-05-23): {len(filtered)}")

# Salva
out = Path("/home/user/workspace/sp500_changes_2020_2026.csv")
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date_iso", "date_text", "added_ticker", "added_security",
                "removed_ticker", "removed_security", "reason"])
    for r in filtered:
        # r = (iso, original_date, added_t, added_s, removed_t, removed_s, reason)
        w.writerow(r)
print(f"Saved: {out} ({out.stat().st_size} bytes)")

# Statistiche delisting (solo righe con removed_ticker non vuoto)
removed = [r for r in filtered if r[4].strip()]
print(f"\nDelisting/removal records: {len(removed)}")

# Categorizza per motivazione
mna = sum(1 for r in removed if "acquired" in r[6].lower() or "spun off" in r[6].lower())
mcap = sum(1 for r in removed if "market cap" in r[6].lower())
other = len(removed) - mna - mcap
print(f"  M&A / spin-off: {mna}")
print(f"  Market cap change: {mcap}")
print(f"  Altri: {other}")
