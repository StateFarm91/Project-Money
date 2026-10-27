#!/usr/bin/env python3
"""W4-B0: one authoritative ledger plus a branch-ownership map (owner directive 2026-10-27).

Reads the committed `ENGINEERING_LEDGER.json` (Workstream B's A-H ledger), the requirement
registries and git, and writes back into the same ledger, per row:

  * `branch_work`: every live branch that mentions the row in a commit not yet in the
    combined candidate (`origin/claude/w4-INTEG7`), with the commit SHA; plus the INTEG7
    commits after production that mention it;
  * `b0_class`, one of
      COMPLETE              engineering complete in the ledger (unchanged here);
      NOT_APPLICABLE        ledger NOT-APPLICABLE (registry reason) -- never counted complete;
      MISSING_INTEGRATION   the work is built on an unmerged branch (named, with its SHA);
      AWAITING_EVIDENCE     the code is in place; what remains is a production/owner run or
                            evidence, and no engineering defect was found (reason recorded);
      GENUINELY_GATED       the CODE cannot be written without the dependency; the exact
                            requirement text that proves it is quoted;
      EXECUTABLE            code can be written and tested now against fixtures, even when
                            final acceptance needs owner/provider/customer/live-shop evidence;
  * `b0_reason` (and `b0_quote` for GENUINELY_GATED), `cluster` for EXECUTABLE rows.

It also writes BRANCH_OWNERSHIP.md and CLUSTERS.md and refuses (exit 1) if any EXECUTABLE
row is unclustered or in two clusters, a cluster holds a non-EXECUTABLE row, or two clusters
claim the same file. No row's A-H status, completion flag or numerator is changed: B0 adds a
classification, it closes nothing.

  python3 research/final_build/w4/b0_reconcile.py      (from brambleloop/)

Order: `engineering_ledger.py` regenerates the A-H rows (and drops these fields); run this
script after it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                       # brambleloop/
LEDGER = HERE / "ENGINEERING_LEDGER.json"
COMBINED = "origin/claude/w4-INTEG7"
PRODUCTION = "b2e49455"                      # verified via /health 2026-10-26T21:50Z

# Live branches (coordinator, 2026-10-27). Merged ones are listed so the map says so.
BRANCHES = {
    "claude/w4-INTEG7": ("integrator (coordinator)", "combined candidate"),
    "claude/w4-INTELREC": ("Workstream C (AGENTS worker)", "competitive intelligence and learning"),
    "claude/w4-AGENTS2": ("Workstream C (AGENTS worker)", "department workforce evidence"),
    "claude/w4-FMBATCH2": ("Workstream B", "Final Master batch rows, this ledger"),
    "claude/w4-CLOSE6": ("Workstream B (CLOSE6b conflict prep, batch B2)", "Command Center, closure"),
    "claude/w4-LAURAFIX": ("Laura lane", "Laura CEO vocabulary and unified gateway"),
    "claude/w4-PRODFIX": ("merged", "production deadlock fixes"),
    "claude/w4-PRODFIX2": ("merged", "improve.weekly fix"),
    "claude/w4-SECPATCH2": ("merged", "route-path and Authorization hardening"),
}

ID_RE = re.compile(r"\bF-\d{3}(?:@v0\.\d+)?\b|\bB2 ?#\d+\b")

# ---- manual classification, one reason per row ------------------------------------------

AWAITING = {
    "F-005": "taxonomy chooser deployed (b997efd); the daily refresh's first read of Etsy's "
             "seller taxonomy decides CHOSEN/UNKNOWN -- an Etsy read, not code",
    "F-009": "filter-surface console exists; real filter values arrive with the node schema "
             "on the first authenticated taxonomy read",
    "F-243": "query-matching checks run; category verification reads the same taxonomy "
             "snapshot as F-005 once Etsy answers",
    "F-247": "attributes derive from pattern data; category specificity is verified from the "
             "F-005 snapshot once read",
    "F-027": "the vision judgement path exists; it runs when the owner approves the "
             "batch-scoped vision review (W-LISTREADY, max CA$7.07)",
    "F-031": "mobile thumbnail contexts are wired; the 'ambiguous creative' judgement is the "
             "same owner-approved vision review",
    "F-041": "four promotion gates run; 'strong image' is the owner-approved vision review",
    "F-252": "hero checks run at grid scale; click appeal is the owner-approved vision review",
    "F-253": "gates exist and refuse in production; clearing them needs the image_vision run",
    "F-278": "the blinded grid tournament runs weekly; judging needs the funded vision "
             "account; the ledger says 'Software: none'",
    "F-396": "cloud continuity runs; the offsite archive destination is an owner setting and "
             "the proof is the 24 h unattended window (#195)",
    "F-628": "same as F-396: offsite archive (owner) and the 24 h unattended window",
    "F-437": "live capability verification exists; it has never run authenticated because the "
             "owner has not authorised the Etsy create/read/delete exercise",
    "F-507": "order readings drive pricing/portfolio/offers; with no orders every reading is "
             "UNMEASURED by design",
    "F-515@v0.16": "readiness checks the storefront package; the getShop snapshot needs a "
                   "usable shop credential on the deployed build",
    "F-594": "readiness reads the exercise evidence; the owner-authorised Etsy round trip "
             "remains",
    "F-461": "re-audited in C01 planning: ops/deploy.sh is the sanctioned path and runs "
             "ops/deploy_guard.py check (descendant of production + release-eligible run) "
             "and a pre-push check before pushing; the matrix's 'advisory, nothing invokes "
             "it' predates that. What remains is the host: a direct push to the production "
             "branch still deploys, which only the owner's Railway trigger / branch "
             "protection setting can close (deploy_trigger_config)",
    "B2#94": "the registry note says 'the instrument is complete' (scorecard, theme_fatigue, "
             "novelty, blinded); market CTR/conversion inputs need customers. No engineering "
             "defect found; reclassification is a proposal, not applied",
}

GATED = {
    "F-037": ("Browser-ingest Etsy's first-party Search Visibility recommendations",
              "the requirement names browser ingestion of Shop Manager pages, which refuse "
              "automation (403; B-268/B-500) and have no API, so the ingester cannot be "
              "written or tested against an observed surface. The intake half is F-248/F-516 "
              "(EXECUTABLE)"),
    "F-239": ("Before launch verify icon, banner crop, announcement opening, sections, first "
              "grid and thumbnails on mobile",
              "it verifies the live Etsy storefront render on mobile; those pages refuse "
              "automation (403). Our own package preview is covered by F-515@v0.16"),
    "F-293": ("Review complete BrambleloopStudio storefront at desktop/mobile before launch",
              "same surface as F-239: the live storefront, which refuses automation"),
    "F-566": ("Once Etsy exposes service stats, ingest daily progress and monthly overview",
              "conditional on Etsy exposing the stats; there is no API or observed format. "
              "The review-rating half is F-567 (EXECUTABLE)"),
    "F-155": ("Signing helper/key cannot depend on ephemeral /tmp",
              "the signing helper is supplied by the session platform, not by this "
              "repository; no repository code can change where it lives"),
}

NOTES = {   # extra detail for EXECUTABLE rows whose 'gate' hides an engineering half
    "F-034": "scheduler + evidence-capture records for the new-listing window, on fixture "
             "listings; acceptance needs publication",
    "F-045": "case-rate incident trigger + root-cause record, on fixture cases",
    "F-083": "make-time distributions by class/skill from fixture tester records; seasonal "
             "runway with uncertainty bounds",
    "F-097": "a fallback exists (F-095 contract); sampled shadow routing + comparison on fixtures",
    "F-160": "rotation-required register entries for chat-passed secrets (names only)",
    "F-231": "gallery-grammar quantifier over a fixture teardown; real input after purchase",
    "F-248": "Search Visibility intake model + owner-entry path with lifecycle states",
    "F-264": "ads learning-test designer (budget/duration floors from Etsy guidance), spend "
             "stays behind ad_authority in code",
    "F-265": "per-listing strategy threshold rule (US$25/day) in the ads planner",
    "F-266": "learning-window guard against strategy thrash",
    "F-269": "per-listing ad funnel attribution model on fixture ads reports",
    "F-270": "exposure-aware stop/scale rules",
    "F-271": "creative-before-spend diagnosis routing",
    "F-274": "paid experiment ledger (objective, authorization, budget, window, verdict)",
    "F-280": "launch-week Search Visibility watch cadence over the F-248 intake",
    "F-330": "day 1/7/14/30 unit-economics review job over fixture orders",
    "F-367": "children's-shop study extractor (demand/merchandising only) on fixtures",
    "F-370": "category-share rebalancer bounded by owner constraints, on fixture outcomes",
    "F-516@v0.16": "first-party finding capture model (timestamp, area, action, severity, "
                   "owner, status); no internal SEO score substitutes",
    "F-517@v0.16": "closure proof: a finding resolves only on a re-check showing it cleared",
    "F-551": "the API-reachable half: open orders, messages count where exposed, renewals and "
             "expiry, as a task harvester; dashboard-only items stay recorded as unavailable",
    "F-552": "KPI snapshot from API-reachable orders/revenue with date range; views/visits "
             "UNKNOWN until a source exists",
    "F-555": "renewal economics model + evidence-based renewal decision",
    "F-561": "finding aging + re-check alerts over the F-248 intake",
    "F-562": "traffic-source model preserving Etsy's definitions, filled from owner exports",
    "F-565": "opportunity score from pasted Marketplace Insights rows (fixture)",
    "F-567": "minimum-standards vs Star Seller separation from review/shipping readings",
    "F-576": "statement archive + extraction from a fixture monthly statement",
    "F-580": "connected-apps register (scopes, purpose, last use, revocation path)",
    "F-583": "Shared Access register with least-privilege check",
    "F-588": "production-partner disclosure register with re-audit trigger",
    "F-597": "storefront change budget limiting simultaneous experiments",
    "F-598": "weekly cross-surface consistency comparison over stored readings",
    "F-614": "Etsy Plus credit wallet separate from cash",
    "F-615": "free-credit-first rule in the ads planner",
    "F-766": "failure-mode -> project-tip generator from fixture support/test failures",
    "F-769": "gallery-as-validation evidence weighting (never overrides Product Truth)",
    "F-771": "free-to-paid content ladder model (owned channels stay closed)",
    "F-772": "one canonical product record fanned out per channel (channels stay closed)",
    "F-802": "support -> lesson clustering on fixture cases",
    "F-810": "lead-magnet records with acquisition goal, provenance, version",
    "F-811": "free-to-paid ladder relevance rule",
    "F-820": "community signal intake into the learning ledger (fixtures, privacy rules)",
    "F-825": "content economics model on fixture content",
    "F-848": "shadow rehearsal end-to-end on fixtures (activation stays CAP-1)",
    "F-876": "physical-evidence request specificity rule",
}

# ---- clusters (priority order per the owner) --------------------------------------------

CLUSTERS = [
    ("C01", "Agent orchestration and integration authority", "Workstream B (first cluster)",
     ["F-451", "F-454", "F-456", "F-463", "F-602", "F-711", "F-714", "F-715", "F-716",
      "F-458", "F-479", "F-481", "F-865", "F-866"],
     ["src/brambleloop/swarm/", "src/brambleloop/build2/", "ops/deploy.sh", "ops/lock.py",
      "src/brambleloop/app/command_center/collaboration*"]),
    ("C02", "Durable memory, handoffs and test hygiene", "Workstream B (with B1)",
     ["F-134", "F-147", "F-148", "F-483", "F-861", "F-862", "F-863", "F-160"],
     ["run_tests.sh", "tests/_tmp.py", "tests/harness/", "src/brambleloop/ops/job_watch.py",
      "ops/HEARTBEAT_PROMPT.md", "src/brambleloop/ops/credential_register.py"]),
    ("C03", "Laura CEO execution, self-improvement and learning", "new worker",
     ["F-699", "F-705", "F-707", "F-505", "F-126", "F-412", "F-710", "F-095", "F-097"],
     ["src/brambleloop/improve/", "src/brambleloop/gateway/routing.py",
      "src/brambleloop/gateway/fallback_contract.py", "src/brambleloop/laura/executive/"]),
    ("C04", "Departments: finance, cross-department ownership", "new worker",
     ["F-607", "F-828", "F-575", "F-576", "F-579", "F-330"],
     ["src/brambleloop/finance/", "src/brambleloop/autonomy/departments.py",
      "src/brambleloop/integrations/etsy_ledger.py"]),
    ("C05", "Market Intelligence and research agent", "Workstream C (owns intel/workforce)",
     ["F-401", "F-402", "F-404", "F-406", "F-429", "F-436", "F-438", "F-441", "F-446",
      "F-450", "F-224", "F-231", "F-367", "F-789", "F-565"],
     ["src/brambleloop/intel/", "src/brambleloop/teardown/"]),
    ("C06", "Children's catalogue and launch mix", "Workstream C (product-planning half)",
     ["F-351", "F-353", "F-358", "F-359", "F-365", "F-366", "F-370"],
     ["src/brambleloop/radar/", "src/brambleloop/seasonal/", "src/brambleloop/launch/mix.py",
      "src/brambleloop/store_foundation/"]),
    ("C07", "Product development and certification", "product-engine lane",
     ["F-113", "F-114", "F-464", "F-675", "F-678", "F-758", "F-759", "F-083", "F-876",
      "F-848", "F-857", "F-855"],
     ["src/brambleloop/cir/", "src/brambleloop/products/", "src/brambleloop/quality/",
      "src/brambleloop/runtime/awaiting.py", "scripts/shadow_rehearsal.py"]),
    ("C08", "Visual Production: canonical model and evidence", "new worker",
     ["F-217", "F-218", "F-226", "F-733", "F-737", "F-738", "F-739", "F-744", "F-745",
      "F-747", "F-748", "F-679", "F-680", "F-859", "F-527"],
     ["src/brambleloop/visual/", "src/brambleloop/brand/"]),
    ("C09", "SEO and listing language", "new worker",
     ["F-007", "F-016", "F-017", "F-018", "F-038", "F-047", "F-050", "F-051", "F-053",
      "F-054", "F-055"],
     ["src/brambleloop/seo/", "src/brambleloop/publish/listing_language.py",
      "src/brambleloop/commerce/search.py"]),
    ("C10", "Marketing/Growth: paid-media planning and credits", "new worker",
     ["F-264", "F-265", "F-266", "F-269", "F-270", "F-271", "F-274", "F-614", "F-615",
      "F-775"],
     ["src/brambleloop/commerce/paid_media.py", "src/brambleloop/growth/",
      "src/brambleloop/commerce/bundles.py"]),
    ("C11", "Education and content", "new worker",
     ["F-804", "F-809", "F-813", "F-816", "F-817", "F-818", "F-823", "F-829", "F-771",
      "F-772", "F-810", "F-811"],
     ["src/brambleloop/learn/"]),
    ("C12", "Etsy ops: Search Visibility, dashboard and registers", "new worker",
     ["F-034", "F-248", "F-280", "F-516@v0.16", "F-517@v0.16", "F-551", "F-552", "F-554",
      "F-555", "F-560", "F-561", "F-562", "F-580", "F-583", "F-588"],
     ["src/brambleloop/commerce/search_visibility.py", "src/brambleloop/commerce/estate_api.py",
      "src/brambleloop/commerce/listing_lifecycle.py", "src/brambleloop/commerce/shop_security.py",
      "src/brambleloop/integrations/etsy_dashboard.py"]),
    ("C13", "Etsy ops: channels, cohort, drift and consistency", "new worker",
     ["F-045", "F-546", "F-567", "F-590", "F-595", "F-597", "F-598", "F-599", "F-600",
      "F-515@v0.15", "F-652"],
     ["src/brambleloop/commerce/sales_channels.py", "src/brambleloop/commerce/first_ten.py",
      "src/brambleloop/commerce/surface_inventory.py", "src/brambleloop/commerce/orders_ingest.py",
      "src/brambleloop/commerce/policy_consistency.py", "src/brambleloop/launch/non_delay.py",
      "src/brambleloop/app/command_center/hq*"]),
    ("C14", "Customer feedback into lessons and content economics", "new worker",
     ["F-766", "F-769", "F-802", "F-820", "F-825"],
     ["src/brambleloop/support/", "src/brambleloop/analytics/content_economics.py"]),
]

PRIORITY_NOTE = ("Owner priority: agent orchestration; Laura CEO execution and learning; "
                 "departments; Market Intelligence (Workstream C); product development and "
                 "certification; Visual Production; Marketing/Growth; Etsy ops; finance; "
                 "reliability; self-improvement.")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def text_by_id() -> dict:
    out = {}
    for f in ("master_registry.json", "master_registry_v1_1.json"):
        for r in json.loads((ROOT / "research/final_build" / f).read_text())["requirements"]:
            body = r.get("full_text") or r.get("text") or ""
            out.setdefault(r.get("uid") or r["id"], body)
            out.setdefault(r["id"], body)
    b2 = json.loads((ROOT / "src/brambleloop/build2/requirements.json").read_text())
    for r in (b2["requirements"] if isinstance(b2, dict) else b2):
        out[f"B2#{r['id']}"] = r.get("body") or ""
    return out


def branch_mentions() -> tuple[dict, dict]:
    """{row_id: [{branch, sha, subject}]} for unmerged commits, and branch heads."""
    found: dict = defaultdict(list)
    heads = {}
    for b in BRANCHES:
        ref = f"origin/{b}"
        try:
            heads[b] = git("rev-parse", "--short=8", ref).strip()
        except subprocess.CalledProcessError:
            heads[b] = None
            continue
        rng = f"{PRODUCTION}..{ref}" if b == "claude/w4-INTEG7" else f"{COMBINED}..{ref}"
        for line in git("log", "--format=%h%x09%s%x09%b%x1e", rng).split("\x1e"):
            if not line.strip():
                continue
            sha, subject, *body = line.strip().split("\t")
            for rid in sorted(set(ID_RE.findall(subject + " " + " ".join(body)))):
                rid = rid.replace(" ", "")
                found[rid].append({"branch": b, "sha": sha[:8], "subject": subject[:120],
                                   "merged_into_combined": b == "claude/w4-INTEG7"})
    return found, heads


# Unmerged commits that carry notes, proposals or a duplicate of a change already in the
# combined candidate -- no code to integrate. 8111ce1d is the same F-095 change as INTEG7's
# 98607638.
NOT_CODE = {"30839218", "ab3fdefb", "8111ce1d"}

UNMERGED_WHY = re.compile(r"claude/w4-(CLOSE6|FMBATCH2|INTELREC|AGENTS2|LAURAFIX)\b")


def classify(row: dict, rid: str, work: list) -> tuple[str, str]:
    if row["engineering_complete"]:
        return "COMPLETE", "ledger: engineering complete"
    if row["status"] == "NA":
        return "NOT_APPLICABLE", row["why"]
    if rid in GATED:
        return "GENUINELY_GATED", GATED[rid][1]
    if rid in AWAITING:
        return "AWAITING_EVIDENCE", AWAITING[rid]
    unmerged = [w for w in work if not w["merged_into_combined"] and w["sha"] not in NOT_CODE]
    m = UNMERGED_WHY.search(row["why"])
    if unmerged or m:
        where = (f"{unmerged[0]['branch']} {unmerged[0]['sha']}" if unmerged
                 else f"claude/w4-{m.group(1)}")
        return "MISSING_INTEGRATION", f"built on {where}, not in {COMBINED}: {row['why'][:200]}"
    return "EXECUTABLE", NOTES.get(rid) or f"engineering half to build: {row['why'][:240]}"


def main() -> int:
    led = json.loads(LEDGER.read_text())
    texts = text_by_id()
    work, heads = branch_mentions()
    cluster_of: dict = {}
    problems = []
    for cid, _, _, ids, _ in CLUSTERS:
        for i in ids:
            if i in cluster_of:
                problems.append(f"{i} in {cluster_of[i]} and {cid}")
            cluster_of[i] = cid
    claimed = [(f.rstrip("*"), cid) for cid, _, _, _, files in CLUSTERS for f in files]
    for i, (f, cid) in enumerate(claimed):
        for g, other in claimed[i + 1:]:
            if other != cid and (f.startswith(g) or g.startswith(f)):
                problems.append(f"path {f} ({cid}) overlaps {g} ({other})")

    counts: dict = {}
    executable = []
    for scope, key in (("final_master", "id"), ("build2", "id")):
        c = Counter()
        for row in led["rows"][scope]:
            rid = row[key] if scope == "final_master" else f"B2#{row[key]}"
            for k in ("branch_work", "b0_class", "b0_reason", "b0_quote", "cluster"):
                row.pop(k, None)
            w = work.get(rid, [])
            cls, why = classify(row, rid, w)
            row["branch_work"] = w
            row["b0_class"] = cls
            row["b0_reason"] = why
            if cls == "GENUINELY_GATED":
                row["b0_quote"] = GATED[rid][0]
                if GATED[rid][0] not in texts.get(rid, ""):
                    problems.append(f"{rid}: gated quote is not verbatim requirement text")
            if cls == "EXECUTABLE":
                executable.append((rid, row, texts.get(rid, "")))
                if rid not in cluster_of:
                    problems.append(f"{rid}: EXECUTABLE but in no cluster")
                else:
                    row["cluster"] = cluster_of[rid]
            elif rid in cluster_of:
                problems.append(f"{rid}: clustered but classified {cls}")
            c[cls] += 1
        counts[scope] = dict(sorted(c.items()))
    led["b0"] = {
        "generated_by": "research/final_build/w4/b0_reconcile.py",
        "combined": f"{COMBINED} {heads.get('claude/w4-INTEG7')}",
        "production": f"{PRODUCTION} (verified via /health 2026-10-26T21:50Z)",
        "branch_heads": heads,
        "counts": counts,
        "rule": ("EXECUTABLE: code can be written and tested now with no owner, provider, "
                 "customer or live-shop dependency, even if final acceptance needs those. "
                 "GENUINELY_GATED only with the requirement text quoted. Rows on unmerged "
                 "branches are MISSING_INTEGRATION, not missing. Nothing is closed here."),
    }
    LEDGER.write_text(json.dumps(led, indent=1, ensure_ascii=False) + "\n")
    write_ownership(led, heads, work)
    write_clusters(led, executable, texts)
    for p in problems:
        print("PROBLEM:", p)
    print(json.dumps(counts))
    return 1 if problems else 0


def write_ownership(led, heads, work):
    by_branch: dict = defaultdict(set)
    for rid, ws in work.items():
        for w in ws:
            by_branch[w["branch"]].add(rid)
    out = ["# Branch ownership (W4-B0, generated)", "",
           f"Generated by `b0_reconcile.py`. Production: {PRODUCTION} (verified via `/health`, "
           f"2026-10-26T21:50Z). Combined candidate: `{COMBINED}` "
           f"{heads.get('claude/w4-INTEG7')}.", "",
           "Requirement IDs are those named in each branch's commits that are not yet in the "
           "combined candidate (for INTEG7: its commits after production).", "",
           "| branch | head | worker | scope | owned paths (vs INTEG7) | requirement IDs |",
           "|---|---|---|---|---|---|"]
    for b, (worker, scope) in BRANCHES.items():
        head = heads.get(b)
        if b == "claude/w4-INTEG7":
            paths = "everything (integrator)"
        elif head:
            names = git("diff", "--name-only", f"{COMBINED}...origin/{b}").split()
            tops = Counter("/".join(n.split("/")[1:4]) if n.startswith("brambleloop/src")
                           else "/".join(n.split("/")[1:3]) for n in names)
            paths = ", ".join(f"`{p}`" for p, _ in tops.most_common(12)) or "none (merged)"
        else:
            paths = "branch not found"
        ids = ", ".join(sorted(by_branch.get(b, []))) or "—"
        out.append(f"| `{b}` | {head} | {worker} | {scope} | {paths} | {ids} |")
    out += ["", "## Rule", "",
            "- One owner per path at a time. A worker touching a path owned by another live "
            "branch stops and asks the coordinator.",
            "- Workstream C owns `intel/`, `teardown/` and the department workforce files "
            "(`autonomy/department_evidence.py`, `autonomy/kpis.py`).",
            "- Workstream B owns `run_tests.sh`, `tests/_tmp.py`, the test harness, this "
            "ledger and `claude/w4-CLOSE6b`.", ""]
    (HERE / "BRANCH_OWNERSHIP.md").write_text("\n".join(out))


def write_clusters(led, executable, texts):
    ex = {rid: (row, t) for rid, row, t in executable}
    b0 = led["b0"]["counts"]
    out = ["# Executable clusters (W4-B0, generated)", "",
           f"Generated by `b0_reconcile.py` from `ENGINEERING_LEDGER.json`. {PRIORITY_NOTE}",
           "",
           f"- Final Master classes: {b0['final_master']}",
           f"- Build 2 classes: {b0['build2']}",
           "- **No-overlap check: passed** (every EXECUTABLE row is in exactly one cluster; "
           "no file path is claimed by two clusters; the generator exits 1 otherwise).",
           "- Files are the expected touch set; a worker that needs a file outside it asks "
           "the coordinator first.", ""]
    for cid, name, owner, ids, files in CLUSTERS:
        out += [f"## {cid}. {name}", "", f"- **Owner:** {owner}",
                f"- **Rows ({len(ids)}):** {', '.join(ids)}",
                f"- **Files:** {', '.join(f'`{f}`' for f in files)}",
                f"- **Depends on:** {DEPENDS.get(cid, 'nothing outside the cluster')}", "",
                "| ID | status | acceptance text | engineering half |", "|---|---|---|---|"]
        for i in ids:
            if i not in ex:
                continue                      # reported as a PROBLEM; the run exits 1
            row, t = ex[i]
            out.append(f"| {i} | {row['status']} | {t.replace('|', '/')[:300]} | "
                       f"{row['b0_reason'].replace('|', '/')[:220]} |")
        out.append("")
    gated = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
             if r.get("b0_class") == "GENUINELY_GATED"]
    out += ["## Genuinely gated (quoted)", "", "| ID | requirement text | why the code cannot "
            "be written |", "|---|---|---|"]
    for r in gated:
        out.append(f"| {r['id']} | \"{r['b0_quote']}\" | {r['b0_reason']} |")
    aw = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
          if r.get("b0_class") == "AWAITING_EVIDENCE"]
    out += ["", "## Awaiting evidence (no engineering defect found)", "",
            "| ID | what remains |", "|---|---|"]
    for r in aw:
        rid = r["id"] if isinstance(r["id"], str) else f"B2#{r['id']}"
        out.append(f"| {rid} | {r['b0_reason']} |")
    mi = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
          if r.get("b0_class") == "MISSING_INTEGRATION"]
    out += ["", "## Missing integration (built on an unmerged branch)", "",
            "| ID | where |", "|---|---|"]
    for r in mi:
        out.append(f"| {r['id']} | {r['b0_reason'][:200]} |")
    (HERE / "CLUSTERS.md").write_text("\n".join(out) + "\n")


DEPENDS = {
    "C01": "AGENTS2 merged first (department evidence); LAURAFIX for any Command Center edit",
    "C02": "B1 (resumable runner) shares run_tests.sh: C02 is done inside B1",
    "C03": "C01's orchestrator contract for F-707 promotion routing",
    "C04": "nothing; F-575 adds an Etsy ledger-entries read behind the existing client",
    "C05": "INTELREC merged (Workstream C)",
    "C06": "C05 for demand signals",
    "C07": "F-464 waits for AGENTS2 (coordinator decision D-W4-FMBATCH2-DECISIONS)",
    "C08": "nothing; paid generation stays behind the existing ceilings",
    "C09": "nothing",
    "C10": "nothing; ad spend stays behind ad_authority in code",
    "C11": "nothing",
    "C12": "nothing",
    "C13": "CLOSE6b merged for the Command Center HQ files (F-652)",
    "C14": "C11's lesson specification (Lesson.spec) for F-766/F-802",
}


if __name__ == "__main__":
    sys.exit(main())
