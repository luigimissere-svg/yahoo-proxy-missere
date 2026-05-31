"""Test offline: applica i pre-filter keyword e scoring sull'event_shock_golden_set.jsonl.

Non chiama Gemini ne' Yahoo/Finnhub (test offline puro):
- pre-filter trigger keyword (matches_any_trigger)
- score_officiality dato source_official
- score_economic_impact dato quantitative_value/unit + category
- compute_event_credibility con volume=stub e analyst=stub

Obiettivo: misurare recall del solo pre-filter keyword.
Target spec: recall >= 0.6 sulle 6 categorie eligible automatica.
"""
import json
import sys
import os

sys.path.insert(0, "/home/user/workspace/api")
from event_shock import (
    _matches_any_trigger, score_officiality, score_economic_impact,
    score_volume, score_analyst_reaction, compute_event_credibility,
    ELIGIBLE_AUTOMATIC, MANUAL_REVIEW, SEVERITY_BY_CATEGORY,
)

GOLDEN_PATH = "/home/user/workspace/event_shock_golden_set.jsonl"

with open(GOLDEN_PATH) as f:
    rows = [json.loads(l) for l in f if l.strip()]

print(f"Caricati {len(rows)} eventi da golden set")
print("=" * 80)

# Step 1: recall pre-filter
true_positive_kw = 0   # trigger keyword corretto e categoria corretta
matched_some_kw = 0    # trigger keyword qualsiasi
miss = []

for r in rows:
    title = r["titolo_notizia"]
    cat_attesa = r["category"]
    kw_match = _matches_any_trigger(title, "")
    if kw_match:
        matched_some_kw += 1
        if kw_match == cat_attesa:
            true_positive_kw += 1
        else:
            miss.append({
                "id": r["id"], "ticker": r["ticker"],
                "atteso": cat_attesa, "match_kw": kw_match,
                "title": title[:120],
            })
    else:
        miss.append({
            "id": r["id"], "ticker": r["ticker"],
            "atteso": cat_attesa, "match_kw": "NESSUNO",
            "title": title[:120],
        })

print(f"Pre-filter keyword (no Gemini):")
print(f"  Match generico: {matched_some_kw}/{len(rows)} ({matched_some_kw/len(rows)*100:.1f}%)")
print(f"  Match categoria corretta: {true_positive_kw}/{len(rows)} ({true_positive_kw/len(rows)*100:.1f}%)")
print()

if miss:
    print(f"Eventi NON matchati o classe errata (pre-filter only, {len(miss)}):")
    for m in miss[:20]:
        print(f"  {m['id']} {m['ticker']} atteso={m['atteso']:<25} kw_match={m['match_kw']:<25} | {m['title']}")
    print()

# Step 2: scoring credibility (solo officiality + economic_impact)
print("=" * 80)
print("Scoring credibility (officiality + economic_impact, no volume/analyst reali):")
print()
print(f"{'ID':<8} {'TICKER':<10} {'CATEGORIA':<25} {'OFF':>4} {'ECO':>4} {'CRED':>6}")
print("-" * 80)
sum_cred = 0
above_80 = 0
for r in rows:
    cat = r["category"]
    off_flag = r.get("source_official", False)
    off = score_officiality(r.get("fonte_url", ""), off_flag)
    eco = score_economic_impact(cat, r.get("quantitative_value"), r.get("quantitative_unit"))
    # volume_score stub: 75 (3x ratio - soglia spec)
    cred = compute_event_credibility(off, eco, 75, 50)
    score = cred["event_credibility_score"]
    sum_cred += score
    if score >= 80:
        above_80 += 1
    print(f"{r['id']:<8} {r['ticker']:<10} {cat:<25} {off:>4} {eco:>4} {score:>6.1f}")

print("-" * 80)
print(f"Media event_credibility_score (stub vol=75 analyst=50): {sum_cred/len(rows):.1f}")
print(f"Eventi con score >= 80 (gate spec): {above_80}/{len(rows)} ({above_80/len(rows)*100:.1f}%)")
print()

# Step 3: distribuzione per categoria (pre-filter recall)
print("=" * 80)
print("Recall pre-filter per categoria:")
from collections import Counter
per_cat_total = Counter(r["category"] for r in rows)
per_cat_match = Counter()
for r in rows:
    if _matches_any_trigger(r["titolo_notizia"], "") == r["category"]:
        per_cat_match[r["category"]] += 1
for cat in sorted(per_cat_total.keys()):
    tot = per_cat_total[cat]
    ok = per_cat_match[cat]
    print(f"  {cat:<28} {ok}/{tot}  ({ok/tot*100 if tot else 0:.0f}%)")
