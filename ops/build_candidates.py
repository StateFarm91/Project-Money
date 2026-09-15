#!/usr/bin/env python3
"""Merge raw lens-research JSON into research/candidates/candidates.json and CANDIDATES.md.
Inputs: research/candidates/raw/*.json — either a single-lens file {lens, market_notes, candidates[]}
        or a multi-lens group file {group, market_notes, candidates[] (each with .lens)}.
Usage: python3 ops/build_candidates.py
Ids are assigned in file order (C01...). Re-running keeps ids stable as long as the raw files do not change order."""
import json, glob, pathlib, datetime
root = pathlib.Path(__file__).resolve().parent.parent
raw_dir = root / "research" / "candidates" / "raw"
cands, notes = [], []
for f in sorted(raw_dir.glob("*.json")):
    d = json.load(open(f))
    src = d.get("lens") or d.get("group")
    notes.append((src, d.get("market_notes", ""), d.get("searches_run"), d.get("pages_read")))
    for c in d["candidates"]:
        c = dict(c); c.setdefault("lens", src); c["source_file"] = f.name
        cands.append(c)
for i, c in enumerate(cands, 1):
    c["id"] = f"C{i:02d}"
out = root / "research" / "candidates"
json.dump(cands, open(out / "candidates.json", "w"), indent=1)
L = []
L.append("# CANDIDATES — opportunity sweep\n")
L.append(f"_Built {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%MZ} by `ops/build_candidates.py` from {len(list(raw_dir.glob('*.json')))} raw research files. {len(cands)} candidates. Every evidence item carries a URL and an evidence/assumption label as returned by the researcher; numbers are researcher estimates, not measurements._\n")
L.append("## Summary table\n")
L.append("| id | name | model | target customer | first-10 channel | days to 1st rev | capital CAD | Day-90 base CAD | owner | competition | conf |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|")
for c in cands:
    L.append(f"| {c['id']} | {c['name']} | {c['model_type'][:60]} | {c['target_customer'][:70]} | {c['first_10_customers'][:90]} | {c['est_days_to_first_revenue']} | {c['est_capital_cad']} | {c['est_day90_revenue_base_cad']} | {c['owner_involvement']} | {c['competition_intensity']} | {c['confidence']} |")
L.append("\n## Candidates\n")
for c in cands:
    L.append(f"### {c['id']} — {c['name']}\n")
    L.append(f"_Lens: {c['lens']}_\n")
    for k, lab in [("one_liner","One-liner"),("model_type","Model"),("target_customer","Target customer"),("problem","Problem"),("offer_and_pricing","Offer and pricing"),("first_10_customers","First 10 customers"),("first_100_customers","First 100 customers"),("why_over_alternatives","Why over alternatives"),("why_now_2026","Why now (2026)"),("gross_margin_est","Gross margin (est.)"),("owner_involvement_notes","Owner involvement"),("biggest_failure_reason","Biggest failure reason")]:
        L.append(f"- **{lab}:** {c.get(k,'')}")
    L.append(f"- **Estimates:** capital {c['est_capital_cad']} CAD; days to first revenue {c['est_days_to_first_revenue']}; Day-90 base revenue {c['est_day90_revenue_base_cad']} CAD; owner {c['owner_involvement']}; automation {c['automation_potential']}; competition {c['competition_intensity']}; Day-180 asset {c['day180_asset_potential']}; confidence {c['confidence']}")
    L.append("- **Key risks:** " + "; ".join(c.get("key_risks", [])))
    L.append("- **Evidence:**")
    for e in c["evidence"]:
        L.append(f"  - [{e['kind']}] {e['claim']} — <{e['source_url']}> ({e['recency']})")
    L.append("")
L.append("## Market notes by research source\n")
for src, n, s, p in notes:
    L.append(f"### {src}\n_searches: {s}, pages read: {p}_\n\n{n}\n")
(out / "CANDIDATES.md").write_text("\n".join(L))
print(f"{len(cands)} candidates -> research/candidates/candidates.json, CANDIDATES.md")
