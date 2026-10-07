"""Build MJS_FINDINGS from production's public read-only command-center endpoints (W4-MJS).

Read-only: HTTP GET against the deployed brambleloop-os service's public JSON endpoints, which
serve what the production `mjs.scan` / `mjs.reviews` cadences stored. Nothing is written to
production, nothing is fetched from Etsy here, and no competitor text is kept: the endpoints
expose counts, prices, palettes and medians, and the findings are written from those.

Usage: PYTHONPATH=src python research/final_build/w4/mjs/snapshot_findings.py [--offline]
--offline re-synthesises from the saved raw snapshot (raw_snapshot.json) without network.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BASE = "https://brambleloop-os-production.up.railway.app"
PODS = ("amigurumi", "bags", "blankets", "collections", "garments", "hats", "home_decor",
        "kitchen_bath", "ornaments", "seasonal_gift", "stockings", "education")


def get(path: str, timeout: int = 180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


def fetch() -> dict:
    health = get("/health")
    teardown = get("/api/teardown")
    audit = lambda a, n=5: get(f"/api/audit?limit={n}&action={a}")["audit"]  # noqa: E731
    reviews = audit("mjs.reviews", 1)
    scans = audit("mjs.scanned", 200)
    blocked = []
    for action in ("intel.gallery_analysis_blocked", "serp.capture_blocked",
                   "intel.panel_discovery_blocked", "mjs.scan_blocked"):
        rows = audit(action, 1)
        if rows:
            blocked.append({"source": action, "latest": rows[0]["at"],
                            "reason": str(rows[0]["detail"].get("reason", ""))[:240]})
    cadence_runs = {a: [r["at"] for r in audit(a, 200)] for a in (
        "mjs.scanned", "mjs.reviews", "intel.gallery_analysis", "learning.ingested",
        "mjs.mission_events", "intel.serp_capture", "intel.panel_discovered",
        "intel.benchmark_refresh", "mjs.pod_capability", "mjs.seasonal_sentinel")}
    mjs = get("/api/mjs")
    gaps_actions = []
    for obs in mjs.get("recent_observations") or []:
        for act in obs.get("actions") or []:
            if act.startswith("coverage gap: ") and act[14:] not in gaps_actions:
                gaps_actions.append(act[14:])
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "deployed_commit": (health.get("build") or {}).get("commit"),
        "benchmark_key": "mjs_off_the_hook_designs",
        "market_map": teardown["mjs_market_map"],
        "departments": get("/api/arbitrage/departments"),
        "arbitrage": {p: get(f"/api/arbitrage?pod={p}") for p in PODS},
        "gallery": get("/api/gallery-intelligence"),
        "reviews": {"themes": reviews[0]["detail"]["themes"], "at": reviews[0]["at"]}
        if reviews else {},
        "gaps": [{"arena": a, "pod": "", "state": "uncovered", "score": None}
                 for a in gaps_actions],
        "blocked": blocked,
        "cadence_runs": {k: {"count_in_page": len(v), "latest": v[0] if v else None,
                             "oldest_in_page": v[-1] if v else None}
                         for k, v in cadence_runs.items()},
        "latest_scan": scans[0]["detail"]["catalogue_coverage"] if scans else None,
        "mjs_registry": mjs.get("registry"),
    }


def main() -> None:
    sys.path.insert(0, str(HERE.parents[3] / "src"))
    from brambleloop.intel import findings

    raw_path = HERE / "raw_snapshot.json"
    if "--offline" in sys.argv:
        snap = json.loads(raw_path.read_text())
    else:
        snap = fetch()
        # The raw snapshot keeps only aggregates the findings were computed from: the map
        # rows (pod, price, image count, palette stats), department medians and weakness
        # counts. Listing image URLs and free-text vision reads are dropped.
        for row in snap["market_map"]["rows"]:
            row.pop("absent", None)
        for pod in snap["gallery"].get("by_pod", {}).values():
            pod["reads"] = [r for r in pod.get("reads") or []
                            if r.replace("_", "").isalpha() and "_" in r]
        raw_path.write_text(json.dumps(snap, indent=1, sort_keys=True))
    ev = findings.evidence_from_public_snapshot(snap)
    today = date.fromisoformat(snap["fetched_at"][:10])
    result = findings.synthesize(ev, today=today)
    result["evidence_source"] = {
        "kind": "production public read-only endpoints (GET only)",
        "base": BASE, "fetched_at": snap["fetched_at"],
        "deployed_commit": snap["deployed_commit"],
        "endpoints": ["/health", "/api/teardown (mjs_market_map)", "/api/arbitrage/departments",
                      "/api/arbitrage?pod=*", "/api/gallery-intelligence", "/api/mjs",
                      "/api/audit?action=*"],
        "cadence_runs": snap["cadence_runs"], "latest_scan": snap["latest_scan"]}
    (OUT / "MJS_FINDINGS.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({"findings": [f["key"] for f in result["findings"]],
                      "unmeasured": [u["key"] for u in result["unmeasured"]]}))


if __name__ == "__main__":
    main()
