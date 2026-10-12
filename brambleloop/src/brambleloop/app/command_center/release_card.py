"""Release approval card (W4-CCREL): what the owner needs to authorise a deploy, on the phone.

The owner decision `production_window` ("authorise deploying the reviewed build") was a card
with no build on it. This reads the tracked release evidence the deploy guard and the runtime
boot guard already trust (`release/`, copied into the image) and states, for the newest
release record that has not been deployed:

* candidate SHA and when its record was made;
* the full-suite result from its tracked suite record (passing tests, failing suites), and the
  record's integrity re-checked by `ops.release_record.check_record` (pinned sha256s, same SHA,
  full run, zero failing suites);
* the security review, read from `release/SECURITY_REVIEW_<sha>.json` when one is recorded;
  otherwise UNKNOWN -- never assumed passed;
* the rollback target: the newest deployed commit (`release/DEPLOYED_HISTORY.json`) other than
  the candidate, the only kind of SHA the sanctioned rollback may target.

Read-only. The deploy itself is the integrator's step after the owner's authorisation; nothing
here deploys, approves or writes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ...ops import release_record as RR

SECURITY_REVIEW_GLOB = "SECURITY_REVIEW_{sha}.json"
DEPLOY_GATE = "production_window"


def _release_dir(root: Path | None = None) -> Path:
    return (root or RR.ROOT) / RR.RELEASE_DIR_NAME


def _records(rdir: Path) -> list[dict]:
    out = []
    for p in sorted(rdir.glob("RELEASE_*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if rec.get("kind") == "brambleloop.release_record" and rec.get("sha"):
            out.append({**rec, "_file": p.name})
    return sorted(out, key=lambda r: str(r.get("recorded_at") or ""))


def _deployed(rdir: Path) -> list[dict]:
    try:
        return list(json.loads((rdir / RR.HISTORY_FILE).read_text()).get("deployed") or [])
    except (OSError, ValueError):
        return []


def _is_deployed(rec: dict, deployed: list[dict]) -> bool:
    """Deployed when its SHA ran in production, or a deployed entry's evidence names its record
    (a record-only commit on top of the SHA has the same deployable tree)."""
    sha = rec["sha"]
    for d in deployed:
        if str(d.get("sha") or "") == sha or f"RELEASE_{sha}" in str(d.get("evidence") or ""):
            return True
    return False


def _suite(rec: dict, rdir: Path) -> dict:
    ref = rec.get("suite_record") or {}
    try:
        s = json.loads((rdir / str(ref.get("path") or "")).read_text())
    except (OSError, ValueError):
        return {"state": "UNKNOWN", "why": "tracked suite record unreadable"}
    passed = (s.get("status") == "passed" and s.get("scope") == "full"
              and not int(s.get("suites_failing") or 0))
    return {"state": "PASS" if passed else "FAIL", "status": s.get("status"),
            "scope": s.get("scope"), "tests_passing": s.get("tests_passing"),
            "suites_total": s.get("suites_total"), "suites_failing": s.get("suites_failing"),
            "tests_failing_reported": s.get("tests_failing_reported"),
            "run_id": s.get("run_id"), "finished_utc": s.get("finished_utc"),
            "source": f"release/{ref.get('path')}"}


def _security(sha: str, rdir: Path) -> dict:
    p = rdir / SECURITY_REVIEW_GLOB.format(sha=sha)
    if not p.is_file():
        return {"state": "UNKNOWN",
                "why": (f"no security review is recorded for this candidate "
                        f"(release/{p.name} absent); not assumed passed"),
                "source": f"release/{p.name}"}
    try:
        r = json.loads(p.read_text())
    except (OSError, ValueError):
        return {"state": "UNKNOWN", "why": "security review record unreadable",
                "source": f"release/{p.name}"}
    if r.get("sha") != sha:
        return {"state": "FAIL", "why": "security review names a different SHA",
                "source": f"release/{p.name}"}
    open_findings = int(r.get("open_high_findings") or 0)
    verdict = str(r.get("verdict") or "").upper()
    ok = verdict == "PASS" and open_findings == 0
    return {"state": "PASS" if ok else "FAIL", "verdict": verdict or "UNKNOWN",
            "open_high_findings": open_findings, "reviewed_at": r.get("reviewed_at"),
            "reviewer": r.get("reviewer"), "source": f"release/{p.name}",
            "why": None if ok else f"verdict {verdict or 'UNKNOWN'}, {open_findings} open "
                                   f"high finding(s)"}


def _rollback(sha: str, deployed: list[dict]) -> dict:
    for d in reversed(deployed):
        s = str(d.get("sha") or "")
        if s and s != sha:
            return {"state": "PASS", "sha": s, "observed": d.get("observed"),
                    "how": "ops/deploy_guard.py rollback-commit --to <sha> (ROLLBACK_RUNBOOK)",
                    "source": f"release/{RR.HISTORY_FILE}"}
    return {"state": "UNKNOWN", "sha": None,
            "why": "no previously deployed commit is recorded to roll back to",
            "source": f"release/{RR.HISTORY_FILE}"}


def candidate(root: Path | None = None) -> dict:
    """The newest undeployed release record with its evidence, or why there is none."""
    rdir = _release_dir(root)
    recs = _records(rdir)
    deployed = _deployed(rdir)
    latest_deployed = str((deployed[-1] if deployed else {}).get("sha") or "") or None
    pending = [r for r in recs if not _is_deployed(r, deployed)]
    if not pending:
        return {"pending": False, "latest_deployed": latest_deployed,
                "records": [r["_file"] for r in recs],
                "why": ("every tracked release record has been deployed; a new candidate "
                        "appears here when its release record is committed")
                if recs else "no release record is tracked in this build"}
    rec = pending[-1]
    sha = rec["sha"]
    integrity = RR.check_record(rec, rdir)
    return {"pending": True, "sha": sha, "sha12": sha[:12], "recorded_at": rec.get("recorded_at"),
            "record": f"release/{rec['_file']}", "version": rec.get("version"),
            "source_tree_sha256": rec.get("source_tree_sha256"),
            "integrity": {"state": "PASS" if not integrity else "FAIL",
                          "problems": integrity, "source": f"release/{rec['_file']}"},
            "suite": _suite(rec, rdir), "security_review": _security(sha, rdir),
            "rollback_target": _rollback(sha, deployed), "latest_deployed": latest_deployed}


def evidence(c: dict) -> list[dict]:
    """The candidate as F-885 evidence rows (label, state, why, source)."""
    if not c.get("pending"):
        return []
    s, sec, rb, it = c["suite"], c["security_review"], c["rollback_target"], c["integrity"]
    suite_why = (f"{s.get('status')} {s.get('scope')} run {s.get('run_id')}: "
                 f"{s.get('tests_passing')} tests passing, {s.get('suites_failing')} of "
                 f"{s.get('suites_total')} suites failing" if s.get("state") != "UNKNOWN"
                 else s.get("why"))
    return [
        {"label": f"Candidate SHA {c['sha12']}", "state": it["state"],
         "why": ("release record intact: pinned suite record and log match, same SHA"
                 if it["state"] == "PASS" else "; ".join(it["problems"])),
         "source": c["record"]},
        {"label": "Full release suite", "state": s["state"], "why": suite_why,
         "source": s.get("source") or c["record"]},
        {"label": "Security review", "state": sec["state"],
         "why": sec.get("why") or f"verdict {sec.get('verdict')} by {sec.get('reviewer')} "
                                  f"at {sec.get('reviewed_at')}", "source": sec["source"]},
        {"label": f"Rollback target {str(rb.get('sha') or 'UNKNOWN')[:12]}", "state": rb["state"],
         "why": rb.get("why") or f"deployed {rb.get('observed')}; {rb.get('how')}",
         "source": rb["source"]},
    ]


def ready(c: dict) -> bool:
    return bool(c.get("pending")) and all(e["state"] == "PASS" for e in evidence(c))


def card_fields(c: dict) -> dict:
    """Fields merged onto the `production_window` decision card (or a standalone card)."""
    if not c.get("pending"):
        return {}
    ok = ready(c)
    missing = [e["label"] for e in evidence(c) if e["state"] != "PASS"]
    return {
        "release_candidate": {k: c[k] for k in ("sha", "sha12", "recorded_at", "record",
                                                "suite", "security_review",
                                                "rollback_target", "latest_deployed")},
        "recommendation": (f"Authorise: candidate {c['sha12']} has a passing full suite, an "
                           f"intact record, a passed security review and a rollback target."
                           if ok else
                           f"Do not authorise yet: {', '.join(missing)} not PASS."),
        "uncertainty": (None if ok else
                        "UNKNOWN evidence is not a pass; it is shown as UNKNOWN until recorded"),
        "reversibility": (f"Roll back to {c['rollback_target']['sha'][:12]} with the "
                          f"sanctioned rollback (ROLLBACK_RUNBOOK)"
                          if c["rollback_target"].get("sha") else
                          "no recorded rollback target"),
    }


def standalone_card(c: dict) -> dict | None:
    """A read-only card when a candidate is pending but no deploy decision is open."""
    if not c.get("pending"):
        return None
    f = card_fields(c)
    return {"card_id": f"release:{c['sha12']}", "kind": "RELEASE",
            "title": f"Release candidate {c['sha12']}",
            "proposed_action": (f"Authorise deploying {c['sha12']} (owner decision "
                                f"{DEPLOY_GATE}); phase stays shadow."),
            "expected_benefit": "the reviewed build runs in production",
            "downside": "a defect the suite missed reaches production until rolled back",
            "max_spend_cad": 0.0, "deadline": None,
            "consequence_of_no_action": "production keeps running the deployed build",
            "evidence": evidence(c), "executable": False, "actions": [],
            "not_executable_reason": ("authorised outside this app: the integrator deploys "
                                      "after your recorded authorisation"),
            "sources": [c["record"], f"release/{RR.HISTORY_FILE}"], **f}


def envelope_for(c: dict) -> dict:
    from .providers import envelope

    if not c.get("pending"):
        return envelope("OK", [], ["release/"], provider="release_card",
                        reason=c.get("why"), latest_deployed=c.get("latest_deployed"),
                        pending=False)
    return envelope("OK" if ready(c) else "BLOCKED", evidence(c), ["release/"],
                    provider="release_card", pending=True, candidate_sha=c["sha"],
                    reason=None if ready(c) else card_fields(c)["recommendation"])


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
