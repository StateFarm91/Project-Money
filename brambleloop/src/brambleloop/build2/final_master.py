"""The Final Master closure as a live gate, read by the runtime (F-129, F-133, F-136, F-400,
F-831, F-832, F-838, F-844, F-867, F-879).

WHY THIS EXISTS. The Final Master registry (F-001..F-879) was adjudicated only offline: the
integrator ran `research/final_build/aggregate.py` and read the JSON. Nothing the runtime could
see said whether launch-critical work was finished, so "the build is complete" stayed a session
summary (F-136) and the launch gate was driven by its own items, not by the launch-critical set
(F-400, F-879).

WHAT IT READS. `final_master_closure.json`, beside this module: a compact projection of the
adjudicated matrix that `aggregate.py` regenerates on every run. It is inside `src/`, so it ships
in the image and is bound by the release tree digest (`ops.release_record`): the runtime never
reads research files that exist only on a development machine (F-397).

WHAT IT DOES NOT BELIEVE. The snapshot carries each row's verdict, and this module recomputes
it rather than trusting it (F-136, F-838): a launch-critical row counts as COMPLETE only when its
maturity reaches its target on the eight-rung ladder (F-844: IMPLEMENTED, TESTED, INTEGRATED,
DEPLOYED, EXERCISED, PRODUCTION-OBSERVED and COMMERCIALLY-EVIDENCED are distinct), coverage is
FULL, there is no recorded defect, and it names a producer and a consumer (F-831/F-832: a module
alone is not a capability). Only an explicit owner/data/external gate with a key takes
unfinished work out of OPEN (F-838) -- a default, a blank key or a "none" gate leaves it OPEN.
A partial that does not name its missing behaviour or its next action is an integrity violation
(F-133). A lowered completion target is honoured only on a row the adjudicator marked structural
(operator tooling) and never raises a verdict above what the rules give. Any disagreement between
the snapshot's verdict and the recomputation is an integrity violation, which blocks.

THE LAUNCH VERDICT (F-400, F-879). Ready iff zero launch-critical rows are OPEN and there are no
integrity violations. Post-launch and not-applicable rows are counted and reported but can never
block: the existence of another improvement is not a launch blocker. GATED rows do not block
the closure verdict; they are owner/data/external waits that the launch readiness gate already
presents as owner or data items, split by kind here (F-130).

Read-only and side-effect free. A missing or unreadable snapshot is UNKNOWN, never ready.
"""
from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().with_name("final_master_closure.json")
LEVELS = ("MISSING", "IMPLEMENTED", "TESTED", "INTEGRATED", "DEPLOYED", "EXERCISED",
          "PRODUCTION-OBSERVED", "COMMERCIALLY-EVIDENCED")
GATE_KINDS = ("owner", "data", "external")
_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    """The snapshot, or None when it is absent or unreadable. Cached by (path, mtime)."""
    p = Path(path) if path else SNAPSHOT
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return None
    if _CACHE.get("key") != key:
        try:
            _CACHE.update(key=key, data=json.loads(p.read_text()))
        except (OSError, ValueError):
            return None
    return _CACHE["data"]


def verdict(row: dict) -> tuple[str, list[str]]:
    """Recompute one launch-critical row's completion from its facts (never from its label)."""
    reasons: list[str] = []
    maturity = row.get("maturity")
    if maturity not in LEVELS:
        return "OPEN", [f"maturity {maturity!r} is not a rung of the ladder"]
    target = "INTEGRATED"
    if row.get("completion_target") == "TESTED" and row.get("structural") is True:
        target = "TESTED"
    if LEVELS.index(maturity) < LEVELS.index(target):
        reasons.append(f"maturity {maturity} below target {target}")
    if row.get("coverage") != "FULL":
        reasons.append("coverage PARTIAL")
    if row.get("defect"):
        reasons.append("defect recorded")
    if not reasons and not (row.get("has_producer") and row.get("has_consumer")):
        # F-831/F-832: a complete capability names what produces it and what consumes it. A
        # structural (operator-tooling) row has no runtime consumer by construction.
        if not (target == "TESTED" and row.get("has_producer")):
            reasons.append("no producer->consumer chain named")
    if not reasons:
        return "COMPLETE", []
    gate = row.get("gate") or {}
    if not row.get("defect") and gate.get("kind") in GATE_KINDS and gate.get("key"):
        return "GATED", [f"{gate['kind']} gate {gate['key']!r}"] + reasons
    return "OPEN", reasons


def integrity(snapshot: dict) -> list[dict]:
    """Every way the snapshot disagrees with the rules. Each one blocks the launch verdict."""
    out: list[dict] = []
    rows = snapshot.get("rows") or []
    if not rows:
        return [{"uid": None, "violation": "snapshot has no rows"}]
    seen: set[str] = set()
    for r in rows:
        uid = r.get("uid")
        if uid in seen:
            out.append({"uid": uid, "violation": "duplicate uid"})
        seen.add(uid)
        cls = r.get("launch_class")
        if cls not in ("LAUNCH-CRITICAL", "MATURE", "NA"):
            out.append({"uid": uid, "violation": f"launch_class {cls!r} is not a class"})
            continue
        if cls != "LAUNCH-CRITICAL":
            expect = "POST-LAUNCH" if cls == "MATURE" else "NOT-APPLICABLE"
            if r.get("completion") != expect:
                out.append({"uid": uid, "violation": f"{cls} row labelled {r.get('completion')}"})
            continue
        got, reasons = verdict(r)
        if got != r.get("completion"):
            out.append({"uid": uid, "violation": (
                f"labelled {r.get('completion')} but the rules give {got}"),
                "reasons": reasons})
        if got != "COMPLETE" and r.get("coverage") != "FULL" and not (
                r.get("has_missing_part") and str(r.get("next_action") or "").strip()):
            out.append({"uid": uid, "violation": "orphaned partial (F-133): no missing "
                                                 "behaviour or no next action named"})
        if r.get("completion_target") and r.get("structural") is not True:
            out.append({"uid": uid, "violation": "lowered completion target on a row that "
                                                 "is not structural"})
    return out


def summary(db=None, *, path: Path | None = None) -> dict:
    """Provider contract (status/as_of/basis/items/sources) plus the launch verdict."""
    snap = load(path)
    src = str(path or SNAPSHOT.name)
    if snap is None:
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [src], "launch_ready": False,
                "reason": "the Final Master closure snapshot is absent or unreadable"}
    rows = snap.get("rows") or []
    lc = [r for r in rows if r.get("launch_class") == "LAUNCH-CRITICAL"]
    verdicts = {r["uid"]: verdict(r) for r in lc}
    counts = {"COMPLETE": 0, "GATED": 0, "OPEN": 0}
    for v, _ in verdicts.values():
        counts[v] += 1
    gated_by_kind: dict[str, list[str]] = {k: [] for k in GATE_KINDS}
    gated_by_key: dict[str, list[str]] = {}
    for r in lc:
        if verdicts[r["uid"]][0] == "GATED":
            g = r["gate"]
            gated_by_kind[g["kind"]].append(r["uid"])
            gated_by_key.setdefault(g["key"], []).append(r["uid"])
    open_rows = [{"uid": r["uid"], "title": r.get("title"), "maturity": r.get("maturity"),
                  "reasons": verdicts[r["uid"]][1], "next_action": r.get("next_action")}
                 for r in lc if verdicts[r["uid"]][0] == "OPEN"]
    violations = integrity(snap)
    post_launch = sum(1 for r in rows if r.get("launch_class") == "MATURE")
    not_applicable = sum(1 for r in rows if r.get("launch_class") == "NA")
    ready = counts["OPEN"] == 0 and not violations and bool(lc)
    status = "BLOCKED" if violations else ("OK" if ready else "DEGRADED")
    basis = snap.get("basis") or {}
    return {
        "status": status, "as_of": None, "basis": "measured",
        "launch_ready": ready,
        "launch_critical": counts, "launch_critical_total": len(lc),
        "launch_critical_open": counts["OPEN"],
        "gated_by_kind": {k: len(v) for k, v in gated_by_kind.items()},
        "gated_by_key": {k: sorted(v) for k, v in sorted(gated_by_key.items())},
        "post_launch_excluded": post_launch, "not_applicable": not_applicable,
        "integrity_violations": violations,
        "items": open_rows,
        "sources": [src, "research/final_build/closure_matrix.json",
                    "research/final_build/aggregate.py"],
        "mapping_basis": basis.get("mapping"), "production_basis": basis.get("production"),
        "rule": ("ready iff zero launch-critical rows OPEN and no integrity violation; "
                 "post-launch rows never block (F-400/F-879); only an explicit owner/data/"
                 "external gate with a key removes work from OPEN (F-838)"),
        "note": ("as_of is null on purpose: the snapshot is a release artefact bound to the "
                 "tree digest, not a clock reading; the mapping SHAs say how old it is"),
    }
