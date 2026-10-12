"""W4-PRELAUNCH: pre-launch verifiability of every row the finish-line board has not verified.

Owner decision 2026-10-12: the entire agreed Build 2 and Final Master is built and verified BEFORE
the Etsy store opens; "post_launch" scope is not a deferral. Acceptance criteria are unchanged.

For every Build 2 and Final Master row whose board class is not `verified_complete` (and not
`not_applicable`), this classifies the row's EXISTING acceptance criterion (the registry text,
quoted verbatim) as:

  A  buildable and verifiable pre-launch: code + tests / rehearsal / staging evidence can meet it;
  B  buildable pre-launch, but the criterion itself requires production deployment or soak
     (verifiable after an approved deploy, before the store opens);
  C  impossible to verify without live customers, real transactions or post-launch operating
     history -- only when the criterion's own words demand it; the words are quoted.

Strict by construction: C needs a match of one of `C_PATTERNS` in the criterion text itself (a
board gate such as `customers` is NOT enough -- the gate is how the row is blocked today, not what
its criterion says), and the matched sentence is quoted exactly. B needs a production/soak phrase
in the criterion (`B_PATTERNS`), or the board's own release/soak root cause for that row.
Everything else is A. Pattern matching can only ever under-call C (an unmatched live-only
criterion stays A and gets worked): the safe direction under the owner's decision.

  cd brambleloop && python3 research/final_build/w4/prelaunch_scope.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
BL = FB.parents[1]

C_PATTERNS = [
    r"\b(?:real|actual|live|paying)\s+(?:etsy\s+)?(?:customers?|buyers?|orders?|sales|"
    r"transactions?|purchases?|traffic|shoppers?|revenue)\b",
    r"\bafter (?:launch|the first sale|first sales?|go-live|the shop opens)\b",
    r"\bpost-launch\b",
    r"\bfirst (?:\d+|ten|hundred|few) (?:sales|orders|customers|buyers|purchases)\b",
    r"\bfirst (?:sale|order|purchase|customer|buyer)\b",
    r"\b(?:conversion rates?|click-through|CTR|impressions|repeat purchases?|refund rates?|"
    r"return rates?|sell-through)\b",
    r"\bonce (?:the )?(?:shop|store|listings?) (?:is |are )?(?:live|open)\b",
    r"\b(?:over|across) (?:\d+|several|multiple|many) (?:weeks|months|seasons|quarters|years)\b",
    r"\bhistorical (?:sales|orders|performance)\b",
    r"\b(?:sales|order|revenue|traffic) (?:data|history|evidence)\b",
    r"\bbuyer (?:reviews?|ratings?|behaviou?r)\b",
]
B_PATTERNS = [
    # production as the place the criterion is verified -- not "production" as in making
    # things ("production feasibility", "production partners", "a Pinterest production system")
    r"\b(?:in|on|into) production\b", r"\bproduction (?:workers?|queues?|scheduler|"
    r"deploy\w*|readback|smoke|runtime|environment|window|operations?)\b",
    r"\bafter (?:the )?(?:final )?deploy\w*\b", r"\bdeployed readback\b",
    r"\bverify remotely\b", r"\b24/7\b", r"\bunattended\b", r"\boff-device\b",
    r"\bovernight\b", r"\bsoak\b", r"\bhosted\b", r"\bcloud-resident\b", r"\balways-on\b",
    r"\bremain live\b", r"\bwithout the owner'?s PC\b",
]
B_ROOTS = {"release_not_deployed"}
# Rows where a C pattern matched but the criterion's own subject does not demand live
# operations: a definition, a display, or a decision rule that is verifiable pre-launch with
# fixtures / honest UNMEASURED states. Reviewed one by one; each keeps its reason. They are
# worked pre-launch (A), never deferred.
NOT_LIVE = {
    ("build2", 25): "a weekly review rule naming the constraint; it also covers product coverage "
                    "and margin, which exist pre-launch",
    ("build2", 28): "a diagnostic rule (high traffic + weak CTR -> thumbnail/title), testable "
                    "with fixtures",
    ("build2", 258): "'real customer/tester finished projects': tester projects exist pre-launch",
    ("final_master", "F-261"): "a remediation decision table, testable with fixtures",
    ("final_master", "F-271"): "an escalation decision rule, testable with fixtures",
    ("final_master", "F-287"): "a dashboard that shows these fields; UNMEASURED is shown "
                               "honestly before data exists",
    ("final_master", "F-523"): "a diagnosis rule, testable with fixtures",
    ("final_master", "F-606"): "the constraint list also covers quality, uptime, capacity and "
                               "policy, which exist pre-launch",
    ("final_master", "F-618"): "one canonical KPI definition is code, verifiable pre-launch",
    ("final_master", "F-622"): "a Command Center panel; UNMEASURED is shown honestly before "
                               "data exists",
}

DOMAINS = [  # (worker domain, module prefixes, title/section keywords)
    ("command_center_ui", ("app/command_center/",), (r"command center", r"\bowner (?:app|ui)\b")),
    ("image_visual", ("visual/", "assets/", "gateway/images", "gateway/image"),
     (r"\bvisual\b", r"\bimage", r"photo", r"render", r"canonical model", r"\bgallery\b",
      r"thumbnail", r"\bhero\b")),
    ("build2_creative", ("creative/", "brand/"), (r"creative", r"\bbrand", r"style", r"taste")),
    ("store_product", ("commerce/", "products/", "publish/", "listing", "seo/", "search/",
                       "integrations/", "store/", "cir/", "pattern"),
     (r"\betsy\b", r"listing", r"\bstore\b", r"\bshop\b", r"product", r"pattern", r"seo",
      r"search", r"pric", r"\bpdf\b", r"customer", r"order", r"support")),
    ("autonomy_learning", ("improve/", "learn/", "swarm/", "intel/", "autonomy/", "laura/",
                           "radar/"),
     (r"learn", r"autonom", r"improv", r"swarm", r"intel", r"market", r"laura", r"research")),
    ("ops_runtime_governance", ("ops/", "runtime/", "queue/", "gateway/", "finance/", "scale/",
                                "core/", "build2/", "app/", "launch/", "security", "agents/"),
     (r"deploy", r"runtime", r"queue", r"spend", r"financ", r"budget", r"release", r"audit",
      r"rollback", r"credential", r"govern", r"continuity", r"cloud", r"slo\b", r"cost")),
]


def _domain(row: dict, text: str) -> str:
    for name, prefixes, _kw in DOMAINS:
        if any(m.startswith(prefixes) for m in row.get("modules") or []):
            return name
    low = text.lower()
    for name, _p, kws in DOMAINS:
        if any(re.search(k, low) for k in kws):
            return name
    return "ops_runtime_governance"


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return text[left + 1 if left >= 0 else 0:right].strip()


def _criteria() -> dict[tuple[str, object], str]:
    out = {}
    for r in json.loads((BL / "src/brambleloop/build2/requirements.json").read_text()):
        out[("build2", r["id"])] = str(r.get("body") or r.get("title") or "")
    reg = json.loads((FB / "master_registry.json").read_text())["requirements"]
    for r in reg:
        out[("final_master", r["uid"])] = str(r.get("full_text") or r.get("text") or "")
    v11 = FB / "master_registry_v1_1.json"
    if v11.exists():
        for r in json.loads(v11.read_text())["requirements"]:
            out[("final_master", r.get("uid") or r["id"])] = (
                f"{r.get('title', '')} - {r.get('text', '')}")
    return out


def classify(row: dict, criterion: str, key=None) -> dict:
    for pat in C_PATTERNS:
        m = re.search(pat, criterion, re.I)
        if m and key in NOT_LIVE:
            return {"class": "A", "quote": _sentence(criterion, m.start(), m.end()),
                    "matched": m.group(0),
                    "basis": "C pattern matched but reviewed as not live-only: "
                             + NOT_LIVE[key]}
        if m:
            return {"class": "C", "quote": _sentence(criterion, m.start(), m.end()),
                    "matched": m.group(0), "basis": "criterion text demands live operations"}
    for pat in B_PATTERNS:
        m = re.search(pat, criterion, re.I)
        if m:
            return {"class": "B", "quote": _sentence(criterion, m.start(), m.end()),
                    "matched": m.group(0),
                    "basis": "criterion text requires production deployment / soak"}
    if row.get("root") in B_ROOTS:
        return {"class": "B", "quote": None, "matched": None,
                "basis": f"board root cause {row['root']}: the row's evidence is a production "
                         "readback of a release not yet deployed"}
    return {"class": "A", "quote": None, "matched": None,
            "basis": "no production or live-operations requirement in the criterion text"}


def main() -> int:
    board = json.loads((HERE / "COMPLETION_BOARD_FINAL.json").read_text())
    crit = _criteria()
    rows_out = []
    for source in ("build2", "final_master"):
        for r in board["rows"][source]:
            if r["cls"] in ("verified_complete", "not_applicable"):
                continue
            text = crit.get((source, r["id"]), "")
            v = classify(r, text, (source, r["id"]))
            rows_out.append({
                "source": source, "id": r["id"], "scope": r["scope"], "title": r["title"],
                "board_class": r["cls"], "blocked_by": r.get("blocked_by"),
                "root": r.get("root"), "domain": _domain(r, f"{r['title']} {text}"),
                "verifiability": v["class"], "criterion_quote": v["quote"],
                "matched": v["matched"], "basis": v["basis"],
                "criterion": text[:600] if text else None})
    order = {"A": 0, "B": 1, "C": 2}
    scope_order = {"launch_critical": 0, "build2": 1, "post_launch": 2}
    queues: dict[str, list] = defaultdict(list)
    for x in sorted(rows_out, key=lambda x: (order[x["verifiability"]],
                                             scope_order.get(x["scope"], 3),
                                             str(x["id"]))):
        queues[x["domain"]].append(
            f"{x['verifiability']} {'B2#' if x['source'] == 'build2' else ''}{x['id']} "
            f"[{x['board_class']}] {x['title'][:60]}")
    counts = {
        "total_not_verified": len(rows_out),
        "by_class": dict(Counter(x["verifiability"] for x in rows_out)),
        "by_source": {s: dict(Counter(x["verifiability"] for x in rows_out if x["source"] == s))
                      for s in ("build2", "final_master")},
        "by_domain": {d: dict(Counter(x["verifiability"] for x in rows_out if x["domain"] == d))
                      for d in sorted({x["domain"] for x in rows_out})},
        "by_scope": {s: dict(Counter(x["verifiability"] for x in rows_out if x["scope"] == s))
                     for s in ("build2", "launch_critical", "post_launch")},
    }
    out = {"kind": "brambleloop.prelaunch_scope", "schema": 1,
           "decision": ("owner 2026-10-12: the entire agreed Build 2 and Final Master is built "
                        "and verified BEFORE the Etsy store opens; post_launch is not a "
                        "deferral; acceptance criteria unchanged"),
           "generated_by": "research/final_build/w4/prelaunch_scope.py (do not edit by hand)",
           "board": {"file": "research/final_build/w4/COMPLETION_BOARD_FINAL.json",
                     "generated_at": board.get("generated_at"),
                     "branch_head": board.get("branch_head")},
           "rule": __doc__.split("\n\n")[2].strip(),
           "c_patterns": C_PATTERNS, "b_patterns": B_PATTERNS,
           "counts": counts, "queues": dict(queues), "rows": rows_out}
    (HERE / "PRELAUNCH_SCOPE.json").write_text(json.dumps(out, indent=1) + "\n")
    _md(out)
    print(json.dumps(counts, indent=1))
    return 0


def _md(o):
    c = o["counts"]
    L = ["# Pre-launch scope: what can be verified before the Etsy store opens", "",
         f"Generated by `{o['generated_by'].split(' ')[0]}` from the finish-line board "
         f"({o['board']['generated_at']}, head {o['board']['branch_head']}). {o['decision']}.",
         "",
         "- **A**: buildable and verifiable pre-launch (code + tests / rehearsal / staging).",
         "- **B**: buildable pre-launch; its criterion requires production deployment or soak "
         "(verify after an approved deploy, before the store opens).",
         "- **C**: impossible without live customers, real transactions or post-launch history "
         "-- only where the criterion's own words demand it, quoted below.", "",
         f"Rows not yet verified: **{c['total_not_verified']}**. By class: {c['by_class']}.", "",
         "| domain | A | B | C |", "|---|---|---|---|"]
    for d, k in c["by_domain"].items():
        L.append(f"| {d} | {k.get('A', 0)} | {k.get('B', 0)} | {k.get('C', 0)} |")
    L += ["", "| scope | A | B | C |", "|---|---|---|---|"]
    for s, k in c["by_scope"].items():
        L.append(f"| {s} | {k.get('A', 0)} | {k.get('B', 0)} | {k.get('C', 0)} |")
    L += ["", "## C rows (criterion words quoted exactly)", "",
          "| row | domain | quoted criterion | matched |", "|---|---|---|---|"]
    for x in o["rows"]:
        if x["verifiability"] == "C":
            rid = f"B2#{x['id']}" if x["source"] == "build2" else x["id"]
            q = (x["criterion_quote"] or "").replace("|", "/")[:260]
            L.append(f"| {rid} | {x['domain']} | \"{q}\" | {x['matched']} |")
    L += ["", "## Worker queues (A first, then B, then C; launch-critical first within a "
          "class)", ""]
    for d, items in o["queues"].items():
        L += [f"### {d} ({len(items)})", ""] + [f"- {i}" for i in items] + [""]
    (HERE / "PRELAUNCH_SCOPE.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
