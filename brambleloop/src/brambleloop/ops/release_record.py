"""The runtime boot guard: a hosted build must carry a committed, release-eligible record (A3-05).

The deploy guard (`ops/deploy_guard.py`, repo root) is a git hook and a script, so anything
that does not pass through them -- a push with `--no-verify`, a push from a fresh clone that
never installed the hook, a redeploy triggered from the hosting platform -- reaches production
unchecked. This module is the control those paths cannot skip: it runs inside the container,
at import of the app, on whatever code was actually built.

WHAT IT CHECKS. The build's deployable tree (`src/**` without bytecode, plus
`requirements.lock`) is hashed with `tree_digest`. A tracked release record
(`release/RELEASE_<sha>.json`, committed in the repository and copied into the image) must
name that exact digest, bind it to a commit SHA, and point at a tracked copy of a
release-eligible full-suite run record (and its log) whose sha256 it pins. The suite copy
must name the same SHA, be `release_eligible`, `passed`, `full` and have zero failing suites;
the log copy must name the run and the SHA and end with `suites failing: 0`. Nothing gitignored
and nothing from the environment is believed: the evidence is in the image, from git.

The record cannot live inside the commit it names (a commit cannot contain its own hash), so
it is committed on top (`ops/deploy_guard.py record` writes it; a record-only commit adds it).
Binding to the tree digest rather than to the running commit is what makes that sound: the
record-only commit has the same deployable tree as the commit the suite ran on.

WHAT IT DOES. Off the hosting platform it only reports. On it (any `RAILWAY_*` marker, or
`BRAMBLELOOP_BOOT_GUARD=enforce|refuse`), an unproven build is forced to SHADOW (the
`BRAMBLELOOP_PHASE` the process sees is overwritten before anything reads it) and a P1
incident that halts publication is opened at startup -- or, with `BRAMBLELOOP_BOOT_GUARD=refuse`,
the process exits non-zero. There is no environment switch that turns enforcement off on the
platform. Production at fcb982d predates this module and is unaffected until a new deploy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # /app in the image; brambleloop/ in git
RELEASE_DIR_NAME = "release"
DEPLOYABLE_DIRS = ("src/",)
DEPLOYABLE_FILES = ("requirements.lock",)
PLATFORM_MARKERS = ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID",
                    "RAILWAY_SERVICE_ID", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_DEPLOYMENT_ID")
MODE_ENV = "BRAMBLELOOP_BOOT_GUARD"
INCIDENT_SIGNATURE = "release.unproven_build"
_TOTAL = re.compile(r"^TOTAL PASSING: (\d+) ; suites failing: (\d+)\s*$", re.M)


def deployable(rel: str) -> bool:
    """Whether a path (relative to the brambleloop root, '/'-separated) is in the digest."""
    if rel in DEPLOYABLE_FILES:
        return True
    if not rel.startswith(DEPLOYABLE_DIRS):
        return False
    parts = rel.split("/")
    return "__pycache__" not in parts and not rel.endswith((".pyc", ".pyo"))


def tree_digest(entries) -> str:
    """sha256 over sorted `relpath NUL sha256(bytes)` lines. Same function in deploy_guard."""
    h = hashlib.sha256()
    for rel, data in sorted(entries, key=lambda e: e[0]):
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).hexdigest().encode() + b"\n")
    return h.hexdigest()


def filesystem_digest(root: Path = ROOT) -> str:
    entries = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(root).as_posix()
        if deployable(rel):
            entries.append((rel, p.read_bytes()))
    return tree_digest(entries)


def platform(env) -> list[str]:
    return sorted(m for m in PLATFORM_MARKERS if (env or {}).get(m))


def enforced(env) -> bool:
    return bool(platform(env)) or (env or {}).get(MODE_ENV, "") in ("enforce", "refuse")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_record(rec: dict, release_dir: Path) -> list[str]:
    """Why this record does not prove a release-eligible build; empty when it does."""
    reasons: list[str] = []
    sha = str(rec.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        reasons.append("record does not name a full commit SHA")
    if rec.get("release_eligible") is not True:
        reasons.append("record is not marked release_eligible")
    suite_ref = rec.get("suite_record") or {}
    log_ref = rec.get("suite_log") or {}
    suite = None
    for label, ref in (("suite record", suite_ref), ("suite log", log_ref)):
        rel = str(ref.get("path") or "")
        p = (release_dir / rel).resolve()
        if not rel or release_dir.resolve() not in p.parents:
            reasons.append(f"{label} path missing or outside the release directory")
            continue
        if not p.is_file():
            reasons.append(f"tracked {label} copy {rel!r} is absent")
            continue
        if _sha256(p) != ref.get("sha256"):
            reasons.append(f"tracked {label} copy {rel!r} does not match its pinned sha256")
            continue
        if label == "suite record":
            try:
                suite = json.loads(p.read_text())
            except ValueError:
                reasons.append("tracked suite record is not JSON")
        else:
            text = p.read_text(errors="replace")
            if suite is not None and (f"RUN ID: {suite.get('run_id')}" not in text
                                      or f"GIT SHA: {sha}" not in text):
                reasons.append("tracked log does not name this run and SHA")
            totals = _TOTAL.findall(text)
            if not totals or int(totals[-1][1]) != 0:
                reasons.append("tracked log has no TOTAL line with suites failing: 0")
    if suite is not None:
        if suite.get("git_sha") != sha:
            reasons.append("suite record ran on a different SHA than the record names")
        if suite.get("release_eligible") is not True or suite.get("status") != "passed":
            reasons.append("suite record is not a passed, release-eligible run")
        if suite.get("scope") != "full" or suite.get("failing_suites") or int(
                suite.get("suites_failing") or 0):
            reasons.append("suite record is not a full run with zero failing suites")
    return reasons


def verify_build(root: Path = ROOT, env=None) -> dict:
    """Read-only: does this build carry a committed release record for its exact tree?"""
    env = os.environ if env is None else env
    release_dir = root / RELEASE_DIR_NAME
    out = {"enforced": enforced(env), "platform_markers": platform(env),
           "running_commit": (env.get("RAILWAY_GIT_COMMIT_SHA") or None),
           "release_dir": str(release_dir), "ok": False, "record": None, "reasons": []}
    try:
        digest = filesystem_digest(root)
    except OSError as exc:
        out["reasons"].append(f"deployable tree unreadable: {type(exc).__name__}")
        return out
    out["tree_sha256"] = digest
    matching = []
    for p in sorted(release_dir.glob("RELEASE_*.json")) if release_dir.is_dir() else []:
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if rec.get("source_tree_sha256") == digest:
            matching.append((p, rec))
    if not matching:
        out["reasons"].append("no committed release record names this build's tree digest")
        return out
    best = []
    for p, rec in matching:
        why = check_record(rec, release_dir)
        if not why:
            out.update(ok=True, record={"file": p.name, "sha": rec.get("sha"),
                                        "suite_run": (rec.get("suite_record") or {}).get("path")},
                       reasons=[])
            return out
        best = why
    out["reasons"] = best
    return out


BOOT: dict = {}


def apply_at_import(env=None, root: Path = ROOT) -> dict:
    """Run once at app import. Forces SHADOW (or exits) on an unproven hosted build."""
    env = os.environ if env is None else env
    result = verify_build(root, env)
    result["action"] = "none"
    if result["enforced"] and not result["ok"]:
        if env.get(MODE_ENV) == "refuse":
            raise SystemExit("boot guard: unproven build refused to start: "
                             + "; ".join(result["reasons"]))
        env["BRAMBLELOOP_PHASE"] = "shadow"
        result["action"] = "forced_shadow"
    BOOT.clear()
    BOOT.update(result)
    return result


HISTORY_FILE = "DEPLOYED_HISTORY.json"


def known_good_predecessor(running_commit: str | None, root: Path = ROOT) -> dict:
    """F-381: the newest commit in the shipped deployed history that is not this build.

    `release/DEPLOYED_HISTORY.json` is tracked and copied into the image; the sanctioned
    rollback (`ops/deploy_guard.py rollback-commit`, ops/ROLLBACK_RUNBOOK.md) may only target a
    SHA listed there. Recording it at every boot means the rollback target is named in the
    runtime's own audit trail before it is needed, not reconstructed during an incident.
    """
    try:
        dep = json.loads((root / RELEASE_DIR_NAME / HISTORY_FILE).read_text()).get(
            "deployed") or []
    except (OSError, ValueError):
        return {"sha": None, "why": f"{HISTORY_FILE} absent or unreadable in this build"}
    for entry in reversed(dep):
        sha = str(entry.get("sha") or "")
        if sha and sha != (running_commit or ""):
            return {"sha": sha, "observed": entry.get("observed"),
                    "how": "ops/deploy_guard.py rollback-commit --to <sha> (ROLLBACK_RUNBOOK)"}
    return {"sha": None, "why": "no previously deployed commit other than this build"}


def record_incident(db, result: dict | None = None) -> str:
    """At startup: open (or resolve) the P1 incident for an unproven hosted build.

    F-380: every boot also appends one `release.boot_verdict` audit row -- the deploy evidence
    as the runtime itself observed it (proven or not, which record, which tree digest, whether
    enforcement applied, the action taken) plus the known-good predecessor (F-381). The deploy
    guard is client-side and skippable; this row is written by whatever code actually booted.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident

    result = BOOT if result is None else result
    if not result:
        return "not_run"
    with db.session() as s:
        s.add(AuditLog(actor="release_guard", action="release.boot_verdict",
                       artifact=(result.get("record") or {}).get("file"),
                       detail={"ok": bool(result.get("ok")),
                               "enforced": bool(result.get("enforced")),
                               "action": result.get("action"),
                               "record": result.get("record"),
                               "tree_sha256": result.get("tree_sha256"),
                               "running_commit": result.get("running_commit"),
                               "reasons": (result.get("reasons") or [])[:5],
                               "known_good_predecessor": known_good_predecessor(
                                   result.get("running_commit"))}))
        open_row = s.scalar(select(Incident).where(Incident.signature == INCIDENT_SIGNATURE,
                                                   Incident.resolved == False))  # noqa: E712
        if result.get("enforced") and not result.get("ok"):
            detail = {k: result.get(k) for k in ("reasons", "tree_sha256", "running_commit",
                                                 "platform_markers", "action")}
            if open_row is None:
                s.add(Incident(severity="P1", signature=INCIDENT_SIGNATURE,
                               halts_publication=True, detail=detail,
                               summary=("This build carries no committed release-eligible "
                                        "record for its exact tree; running as SHADOW.")))
                return "opened"
            open_row.report_count = (open_row.report_count or 1) + 1
            open_row.detail = detail
            return "restated"
        if open_row is not None and result.get("ok"):
            open_row.resolved = True
            return "resolved"
    return "none"
