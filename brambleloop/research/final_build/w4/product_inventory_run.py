"""W4-PIPE: write PRODUCT_INVENTORY.json/.md from the repository, a shadow chain DB and a
read-only production snapshot.

    PYTHONPATH=src python research/final_build/w4/product_inventory_run.py \
        --chain-db /path/run.sqlite [--out research/final_build/w4]

The production snapshot is the set of files in evidence_PIPE/ captured from production's public
read-only aggregate endpoints (/api/catalogue, /api/asset-coverage, /api/launch). Production runs
an older build (fcb982d); its rows are labelled as observations of that build.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE / "evidence_PIPE"


def production_snapshot() -> tuple[dict, dict]:
    cat = json.loads((EV / "prod_catalogue_20261006.json").read_text())
    cov = json.loads((EV / "prod_asset_coverage_20261006.json").read_text())["owned"]
    launch = json.loads((EV / "prod_launch_20261006.json").read_text())
    out: dict[str, dict] = {}
    for l in cat["listings"]:
        if l["version"] == "collection":
            out.setdefault(l["slug"], {})["collection_listing"] = {
                "title": l["title"], "price_cad": l["price_cad"], "state": l["state"]}
            continue
        photo = ("no_asset" if l["slug"] in cov["with_no_asset_at_all"] else
                 "unusable" if l["slug"] in cov["with_only_unusable_assets"] else
                 "usable" if l["slug"] in cov.get("with_usable_asset", []) else "not_counted")
        out.setdefault(l["slug"], {}).update({
            "observed": "production fcb982d public /api/catalogue, 2026-10-06",
            "version": l["version"], "chain_version": l["chain_version"], "state": l["state"],
            "title": l["title"], "tags": l["tags"], "price_cad": l["price_cad"],
            "images": l["images"], "release": l["release"], "photography": photo})
    reqs = {r["key"]: {"ready": r["ready"], "blocked_by": r.get("blocked_by")}
            for r in launch["requirements"]}
    return out, {"listings": len(cat["listings"]), "requirements": reqs,
                 "verify": json.loads((EV / "prod_verify_20261006.json").read_text())["checks"][1]}


def md(inv: dict, prod_summary: dict, sha: str) -> str:
    L = [f"# Product inventory (W4-PIPE)", "",
         f"Generated {inv['generated_at']} at `{sha}` by `research/final_build/w4/product_inventory_run.py`. "
         "Static = computed now from the CIR; chain = a fresh shadow DB that ran plan.cycle → "
         "store.publish (refused in shadow); production = read-only public snapshot of the deployed "
         "fcb982d build.", "",
         "## Production as the owner sees it", "",
         f"- {prod_summary['listings']} drafted listing rows (15 product slugs + 1 collection), 0 on Etsy; "
         f"`/api/verify` nothing_published: {json.dumps(prod_summary['verify']['evidence'])} — the "
         "dashboard's ~166 'deliveries' are these shadow publish refusals, not deliveries to customers.",
         "- Production listings are all version 1.0.0 / chain 7; this code releases 1.2.0 / chain 8 "
         "(DEPLOY gate for every product).", "",
         "## Counts", "", "| status | n |", "|---|---|"]
    for k, v in sorted(inv["counts"].items()):
        L.append(f"| {k} | {v} |")
    L += ["", "## Per product", "",
          "| product | status | v (repo/prod) | truth | imagery (chain/prod) | search cert (chain) | blockers (clearer) |",
          "|---|---|---|---|---|---|---|"]
    for p in inv["products"]:
        st, ch, pr = p["static"], p["chain"] or {}, p["production"] or {}
        img = ch.get("imagery") or {}
        L.append("| {} | {} | {}/{} | {} | {}/{} | {} | {} |".format(
            p["slug"], p["status"], st.get("version", "-"), pr.get("version", "-"),
            "PASS" if st.get("product_truth_ok") else ("—" if not st.get("exists") else "FAIL"),
            ("usable" if img.get("usable") else (img.get("kind") or "none")) if ch else "-",
            pr.get("photography", "-"),
            (ch.get("publish_verdict") or {}).get("search") or "-",
            "; ".join(f"{b['gate']} ({b['clearer']})" for b in p["blockers"]) or "shop-wide only"))
    L += ["", "## Shop-wide gates (block every product)", ""]
    for g in inv["shop_wide_gates"]:
        L.append(f"- **{g['gate']}** ({g['clearer']}): {g['evidence']}")
    L += ["", "## Shortest path per product", ""]
    for p in inv["products"]:
        L.append(f"- **{p['slug']}** — " + " → ".join(p["shortest_path"][:-1] or ["shop-wide owner gates only"]))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-db")
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--name", default="PRODUCT_INVENTORY")
    a = ap.parse_args()
    from brambleloop.products import inventory as inv_mod

    db = None
    if a.chain_db:
        from brambleloop.core.db import Database
        db = Database(f"sqlite:///{a.chain_db}")
    prod, prod_summary = production_snapshot()
    from datetime import date
    inv = inv_mod.inventory(db=db, production=prod, today=date(2026, 10, 7))
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    inv.update({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "head": sha, "production_summary": prod_summary,
                "chain_db": "fresh shadow SQLite, plan.cycle as_of 2026-10-06" if db else None})
    out = Path(a.out)
    (out / f"{a.name}.json").write_text(json.dumps(inv, indent=1, default=str) + "\n")
    (out / f"{a.name}.md").write_text(md(inv, prod_summary, sha))
    print(json.dumps(inv["counts"]))


if __name__ == "__main__":
    main()
