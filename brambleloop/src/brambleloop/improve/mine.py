"""Failure mining: the rows where something went wrong, turned into routed lessons.

Requirements 97, 101, 193. The nightly sweep's MINE stage counted unresolved incidents and
called that mining. Counting is not mining: a count tells the next night how many things are
wrong and tells nobody which department should change what. Production ran that count every
night and published zero lessons, because `bus.publish` had no caller anywhere.

This reads the three places a failure lands -- an unresolved Incident, a gate or asset
refusal in the audit log, a job that exhausted its retries -- groups each by its signature or
error code so ten reports of one defect are one lesson, and publishes each group through the
lesson bus so the routing table decides who hears it. Publication is idempotent on the
evidence reference: the same unresolved incident re-read tomorrow returns the same lesson
rather than a second one, so a defect open for a month is one lesson a month old.

When an incident carries the CIR it was raised against, the defective pattern is frozen as a
regression fixture (acceptance Gate B) so a future change that loosens the check fails in the
suite rather than at a customer's row 94. A pattern that compiles clean records that it is not
a compiler-visible defect; the fixture is never fabricated.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import bus

ACTION = "improve.mine"

# Audit actions that are a gate saying no. `gate.*` come from the certificate chain;
# `assets.<step>_blocked` from the listing-asset builders.
GATE_ACTIONS: tuple[str, ...] = ("gate.blocked", "gate.halted")
_ASSET_BLOCKED = re.compile(r"^assets\.[a-z_]+_blocked$")

# W4-LEARN: the release-chain publish gates are computed on every publish attempt, shadow
# included, and a product they would hold back is a pre-sale failure the company can act on
# (the search certificate refused every Launch-0 product on a clean shadow run). Only audits
# that block release are read.
RELEASE_GATES = "store.release_gates"

# Where each kind of failure enters the bus, and the subject that routes it. Subjects are the
# existing routing table's, not new ones: a lesson whose audience is undefined stays where it
# was found, which is the failure the bus exists to remove.
INCIDENT_SUBJECT = "defect"
INCIDENT_ORIGIN = "quality"
GATE_SUBJECT = "defect"
GATE_ORIGIN = "quality"
ASSET_SUBJECT = "thumbnail"
ASSET_ORIGIN = "creative_assets"
DEAD_SUBJECT = "defect"
DEAD_ORIGIN = "runtime"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def error_code(text: str) -> str:
    """The stable part of an error: the exception type, or the text before its first colon."""
    head = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    head = head.split(":", 1)[0].strip().lower()
    head = re.sub(r"[^a-z0-9_. -]+", "", head)
    head = re.sub(r"\s+", " ", head)
    return head[:60] or "unknown"


# W4-LEARN (2026-10-11): production's open incidents are 347, of which 300 are
# `stale-artefact:<kind>:<slug>@<version>#<n>` -- one row per artefact rebuild. Grouped by the
# raw signature, the miner read 367 rows into 364 groups and published 316 "lessons" in one
# pass (`improve.mine` job 12071), every one a restatement of a single pattern, so the bus held
# 369 defect lessons nobody could act on. A lesson is the pattern behind the reports, so an
# incident is grouped by its *family*: the signature's leading tokens up to the first one that
# names an instance (a product slug, a version, a sequence number, a content hash).
_INSTANCE_TOKEN = re.compile(r"(@|#|^[0-9a-f]{8,}$|^\d+$)")


def incident_family(signature: str, *, slugs: frozenset[str] = frozenset()) -> str:
    """The family a signature belongs to: its tokens up to the first instance token.

    `row-94-count` stays `row-94-count`; `stale-artefact:visual_truth:hexie@1.0.0#91` is
    `stale-artefact:visual_truth`; `seasonal.at_risk:<slug>:Halloween` is `seasonal.at_risk`.
    A signature whose first token is already an instance keeps its first token.
    """
    tokens = (signature or "").split(":")
    kept: list[str] = []
    for tok in tokens:
        if kept and (tok in slugs or _INSTANCE_TOKEN.search(tok)):
            break
        kept.append(tok)
    return ":".join(kept) or (signature or "")


def last_watermark(db) -> dict:
    """Where the previous mine stopped reading, so this one reads only what is new."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return {"audit_id": 0, "job_id": 0, "at": None}
        detail = row.detail or {}
        return {"audit_id": int(detail.get("audit_id") or 0),
                "job_id": int(detail.get("job_id") or 0),
                "at": _aware(row.at).isoformat()}


def _read(db, since: dict) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident, Job, JobStatus, Product

    with db.session() as s:
        slugs = frozenset(s.scalars(select(Product.slug)))
        incidents = [{"id": i.id, "signature": i.signature, "summary": i.summary or "",
                      "severity": i.severity, "product_slug": i.product_slug,
                      "reports": int(i.report_count or 1), "detail": dict(i.detail or {}),
                      "family": incident_family(
                          i.signature, slugs=slugs | ({i.product_slug} if i.product_slug
                                                      else frozenset()))}
                     for i in s.scalars(select(Incident).where(Incident.resolved.is_(False))
                                        .order_by(Incident.id))]
        audits = [{"id": a.id, "action": a.action, "artifact": a.artifact or "",
                   "detail": dict(a.detail or {})}
                  for a in s.scalars(select(AuditLog).where(AuditLog.id > since["audit_id"])
                                     .order_by(AuditLog.id))
                  if a.action in GATE_ACTIONS or _ASSET_BLOCKED.match(a.action or "")
                  or (a.action == RELEASE_GATES and (a.detail or {}).get("blocks_release"))]
        # W4-LEARN: only DEFECT dead letters are failures. A shadow-mode refusal or a build
        # stand-aside is a gate working (`queue.durable.classify_dead_letter`, the single
        # classifier every dead-letter reader uses); mined, it became a false `defect` lesson
        # ("dead:store.publish:capability not enabled") routed to three departments.
        from ..queue.durable import DEFECT, classify_dead_letter

        dead_rows = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD,
                                                     Job.id > since["job_id"])
                                   .order_by(Job.id)))
        dead = [{"id": j.id, "job_type": j.job_type, "agent": j.agent,
                 "error": j.last_error or ""}
                for j in dead_rows
                if classify_dead_letter(j.job_type, j.last_error or "") == DEFECT]
        not_defects = len(dead_rows) - len(dead)
        newest_audit = s.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)) or 0
        newest_job = s.scalar(select(Job.id).order_by(Job.id.desc()).limit(1)) or 0
    return {"incidents": incidents, "blocked": audits, "dead": dead,
            "dead_not_defects": not_defects,
            "newest_audit": int(newest_audit), "newest_job": int(newest_job)}


def _gate_code(detail: dict) -> str:
    # `gate.blocked` carries `reasons`; the asset builders carry `blocking`; `gate.halted`
    # carries one `reason`. The first entry names the group, because a refusal lists its
    # findings in the order the check found them and the first is the one that fired.
    for key in ("reasons", "blocking"):
        found = detail.get(key)
        if isinstance(found, list) and found:
            return error_code(str(found[0]))
    return error_code(str(detail.get("reason") or detail.get("why") or ""))


def group(read: dict) -> list[dict]:
    """Every failure, grouped by the signature or error code that makes it one thing."""
    groups: dict[tuple, dict] = {}

    for inc in read["incidents"]:
        family = inc.get("family") or inc["signature"]
        key = ("incident", family)
        g = groups.setdefault(key, {
            "kind": "incident", "code": family, "origin": INCIDENT_ORIGIN,
            "subject": INCIDENT_SUBJECT, "evidence_ref": f"incident:{family}",
            "members": [], "reports": 0, "summary": inc["summary"][:200],
            "severity": inc["severity"], "products": set(), "signatures": set()})
        g["members"].append(inc["id"])
        g["signatures"].add(inc["signature"])
        g["reports"] += inc["reports"]
        if inc["product_slug"]:
            g["products"].add(inc["product_slug"])
        if inc["severity"] < g["severity"]:      # P0 < P1 < P2: the worst one names it
            g["severity"] = inc["severity"]

    for row in read["blocked"]:
        code = _gate_code(row["detail"])
        is_asset = bool(_ASSET_BLOCKED.match(row["action"]))
        key = (row["action"], code)
        g = groups.setdefault(key, {
            "kind": ("asset_block" if is_asset else "release_block"
                     if row["action"] == RELEASE_GATES else "gate_block"), "code": code,
            "origin": ASSET_ORIGIN if is_asset else GATE_ORIGIN,
            "subject": ASSET_SUBJECT if is_asset else GATE_SUBJECT,
            "evidence_ref": f"{row['action']}:{code}", "members": [], "reports": 0,
            "summary": row["action"], "severity": "P3", "products": set()})
        g["members"].append(row["id"])
        g["reports"] += 1
        if row["artifact"]:
            g["products"].add(row["artifact"].split("@", 1)[0])

    for job in read["dead"]:
        code = error_code(job["error"])
        key = ("dead", job["job_type"], code)
        g = groups.setdefault(key, {
            "kind": "dead_letter", "code": f"{job['job_type']}:{code}", "origin": DEAD_ORIGIN,
            "subject": DEAD_SUBJECT, "evidence_ref": f"dead:{job['job_type']}:{code}",
            "members": [], "reports": 0, "summary": job["error"].splitlines()[0][:200]
            if job["error"] else "", "severity": "P3", "products": set()})
        g["members"].append(job["id"])
        g["reports"] += 1

    out = []
    for g in groups.values():
        g["products"] = sorted(g["products"])
        if "signatures" in g:
            g["signatures"] = sorted(g["signatures"])
        out.append(g)
    out.sort(key=lambda g: (g["severity"], -g["reports"], g["evidence_ref"]))
    return out


def _statement(g: dict) -> str:
    n = len(g["members"])
    times = f"{g['reports']} report(s) across {n} row(s)"
    products = f" on {', '.join(g['products'][:3])}" if g["products"] else ""
    if g["kind"] == "incident" and len(g.get("signatures") or ()) > 1:
        more = f" and {len(g['products']) - 3} more" if len(g["products"]) > 3 else ""
        return (f"Unresolved {g['severity']} incident family {g['code']!r}{products}{more}: "
                f"{len(g['signatures'])} distinct signature(s) open, e.g. "
                f"{g['summary'] or 'no summary'}. {times}; the pattern behind the reports, "
                f"not the individual report, is what has to change")
    if g["kind"] == "incident":
        return (f"Unresolved {g['severity']} incident {g['code']!r}{products}: "
                f"{g['summary'] or 'no summary'}. {times}; the pattern behind the reports, "
                f"not the individual report, is what has to change")
    if g["kind"] == "gate_block":
        return (f"The certificate chain refused {n} time(s){products} for {g['code']!r}. "
                f"A refusal repeated at the same code is a defect upstream of the gate, and "
                f"the remedy is in what is submitted rather than in the gate")
    if g["kind"] == "release_block":
        return (f"The release gates would hold back {len(g['products']) or n} product(s)"
                f"{products} for {g['code']!r}. A product blocked at release is finished work "
                f"that cannot ship, and the remedy is the evidence the gate asks for, never a "
                f"looser gate")
    if g["kind"] == "asset_block":
        return (f"Listing assets were blocked {n} time(s){products} for {g['code']!r}. "
                f"An asset refused at the same check repeatedly is a brief or render "
                f"problem, and fixing it at the check would be weakening the check")
    return (f"Jobs of type {g['code'].split(':', 1)[0]!r} exhausted their retries {n} "
            f"time(s) with {g['code'].split(':', 1)[-1]!r}. A dead letter repeated at one "
            f"error code is a code path failing the same way, not bad luck")


def _capture_regressions(db, read: dict, *, fixture_dir: Path | None) -> list[dict]:
    """Freeze the defective pattern behind any incident that carries one (Gate B)."""
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product
    from ..gates import regression

    out = []
    for inc in read["incidents"]:
        detail = inc["detail"]
        if "regression_fixture" in detail:
            continue                                   # captured, or recorded as not reproducible
        cir_dict = detail.get("cir") if isinstance(detail.get("cir"), dict) else None
        if cir_dict is None and inc["product_slug"] and detail.get("pattern_version"):
            with db.session() as s:
                product = s.scalar(select(Product).where(
                    Product.slug == inc["product_slug"]))
                if product is not None:
                    version = s.scalar(select(PatternVersion).where(
                        PatternVersion.product_id == product.id,
                        PatternVersion.version == str(detail["pattern_version"])))
                    if version is not None:
                        cir_dict = dict(version.cir_json or {})
        if not cir_dict:
            continue
        try:
            cir = CIR.from_dict(cir_dict)
        except Exception as exc:  # noqa: BLE001 - a malformed CIR is a finding, not a crash
            out.append({"incident": inc["id"], "captured": False,
                        "why": f"the incident's CIR does not parse: {exc}"[:200]})
            continue
        fixture = regression.capture_from_incident(db, inc["id"], cir, directory=fixture_dir)
        out.append({"incident": inc["id"], "captured": fixture is not None,
                    "slug": getattr(fixture, "slug", None),
                    "expected_codes": list(getattr(fixture, "expected_codes", []) or [])})
    return out


def _supersede_instances(db, g: dict, family_lesson: int) -> list[int]:
    """Point every live per-signature lesson of this family at the family's lesson.

    The bus held one lesson per raw signature before families existed; those rows are not
    deleted (a superseded lesson is history) but they leave the live inbox, so the backlog a
    department sees is one lesson per pattern.
    """
    from sqlalchemy import select

    from ..core.models import Lesson

    refs = [f"incident:{sig}" for sig in g.get("signatures") or ()
            if f"incident:{sig}" != g["evidence_ref"]]
    if not refs:
        return []
    out = []
    with db.session() as s:
        for row in s.scalars(select(Lesson).where(
                Lesson.evidence_ref.in_(refs), Lesson.subject == g["subject"],
                Lesson.superseded_by.is_(None), Lesson.id != family_lesson)):
            row.superseded_by = family_lesson
            out.append(row.id)
    return out


def mine(db, *, now: datetime | None = None, fixture_dir: Path | None = None) -> dict:
    """Read every failure since the last mine, group it, and publish each group as a lesson.

    Returns the counts the nightly MINE stage reports: `read` is every failure row looked at
    and `found` is the lessons that did not exist before tonight. An unresolved incident
    re-read on its thirtieth night reads as one row and finds nothing new, which is the
    correct output rather than thirty lessons.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, Lesson

    now = now or datetime.now(timezone.utc)
    since = last_watermark(db)
    read = _read(db, since)
    groups = group(read)

    with db.session() as s:
        before = {row.id for row in s.scalars(select(Lesson))}

    published, reused, superseded = [], [], []
    for g in groups:
        lesson_id = bus.publish(
            db, origin_cell=g["origin"], subject=g["subject"], statement=_statement(g),
            evidence_ref=g["evidence_ref"],
            confidence="measured" if g["reports"] > 1 else "observed")
        entry = {"lesson": lesson_id, "kind": g["kind"], "code": g["code"],
                 "evidence_ref": g["evidence_ref"], "members": len(g["members"]),
                 "reports": g["reports"], "routed_to": list(bus.route_for(g["subject"])),
                 "origin": g["origin"]}
        (published if lesson_id not in before else reused).append(entry)
        if g["kind"] == "incident":
            superseded += _supersede_instances(db, g, lesson_id)

    fixtures = _capture_regressions(db, read, fixture_dir=fixture_dir)

    # The creative jury is a failure source too: every concept it killed died of something,
    # and the Creativity Director keeps each recorded run's causes as a lesson (#85).
    from ..creative.audit import creativity_director

    director = creativity_director(db, since_audit_id=since["audit_id"])
    for out in director["kept"]:
        entry = {"lesson": out["lesson"], "kind": "jury_autopsy",
                 "code": out.get("dominant_cause"), "evidence_ref": out["evidence_ref"],
                 "members": 1, "reports": 1, "routed_to": out["routed_to"],
                 "origin": "product_creativity"}
        (published if out["lesson"] not in before else reused).append(entry)

    total_read = (len(read["incidents"]) + len(read["blocked"]) + len(read["dead"])
                  + director["runs_read"] + director["autopsies_read"])
    detail = {
        "at": now.isoformat(),
        "audit_id": read["newest_audit"], "job_id": read["newest_job"],
        "since": since,
        "read": total_read,
        "incidents": len(read["incidents"]), "blocked": len(read["blocked"]),
        "dead": len(read["dead"]),
        "dead_not_defects": int(read.get("dead_not_defects") or 0),
        "jury_runs": director["runs_read"], "jury_refused": director["refused"],
        "groups": len(groups),
        "found": len(published),
        "published": published, "reused": reused,
        "superseded": superseded,
        "regression_fixtures": fixtures,
        "note": (f"read {total_read} failure row(s) in {len(groups)} group(s); "
                 f"{len(published)} new lesson(s), {len(reused)} already on the bus"),
    }
    with db.session() as s:
        s.add(AuditLog(actor="improvement", action=ACTION, detail=detail))
    return detail


def state() -> dict:
    return {
        "action": ACTION,
        "reads": ["unresolved Incident rows", f"AuditLog rows in {list(GATE_ACTIONS)} and "
                  f"assets.*_blocked", "Job rows in the dead state"],
        "groups_by": "incident signature, gate reason code, job type and error code",
        "publishes_through": "improve.bus.publish, idempotent on evidence_ref",
        "routes_by": "improve.bus.SUBJECT_ROUTING",
        "regression": "gates.regression.capture_from_incident when an incident carries a CIR",
        "jury": "creative.audit.creativity_director keeps each recorded jury run as a lesson",
    }
