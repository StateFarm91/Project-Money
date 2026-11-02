"""Independent review of a reference finding, with an atomic audit record."""
from __future__ import annotations

from sqlalchemy import select, update

from ..core.models import (AuditLog, BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct,
                           TeardownFinding, utcnow)
from .library import ContentRefused, check_derived


class ReviewRefused(ValueError):
    pass


def independent_decision(row, decision: str) -> bool:
    """A state label alone is not evidence that a different actor reviewed it."""
    recorder = getattr(row, "recorded_by", None)
    reviewer = getattr(row, "reviewed_by", None)
    return (decision in ("reviewed", "rejected")
            and getattr(row, "review_state", None) == decision
            and isinstance(recorder, str) and bool(recorder.strip())
            and isinstance(reviewer, str) and bool(reviewer.strip())
            and recorder.strip().casefold() != reviewer.strip().casefold()
            and getattr(row, "reviewed_at", None) is not None)


def independently_reviewed(row) -> bool:
    return independent_decision(row, "reviewed")


def review_finding(db, finding_id: int, *, reviewer: str, decision: str, reason: str) -> dict:
    if type(finding_id) is not int or finding_id <= 0:
        raise ReviewRefused("invalid finding")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 64:
        raise ReviewRefused("reviewer identity required")
    if decision not in ("reviewed", "rejected"):
        raise ReviewRefused("decision must be reviewed or rejected")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ReviewRefused("reason required")
    reviewer = reviewer.strip()
    try:
        check_derived(reason)
        check_derived(reviewer)
    except ContentRefused as exc:
        raise ReviewRefused(str(exc)) from exc
    with db.session() as s:
        row = s.scalar(select(TeardownFinding).where(TeardownFinding.id == finding_id)
                       .with_for_update())
        if row is None:
            raise ReviewRefused("finding not found")
        if not row.recorded_by:
            raise ReviewRefused("recorder is unknown; independent review cannot be established")
        if row.recorded_by.casefold() == reviewer.casefold():
            raise ReviewRefused("recorder cannot review their own finding")
        if row.review_state != "proposed":
            raise ReviewRefused("finding has already been reviewed")
        changed = s.execute(update(TeardownFinding).where(
            TeardownFinding.id == finding_id, TeardownFinding.review_state == "proposed",
            TeardownFinding.recorded_by == row.recorded_by).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow()))
        if changed.rowcount != 1:
            raise ReviewRefused("finding changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.finding_reviewed",
                       artifact=f"teardown-finding:{finding_id}",
                       detail={"finding": finding_id, "decision": decision,
                               "reason": reason.strip()}))
        return {"finding": finding_id, "review_state": decision}


def review_analysis(db, analysis_id: int, *, reviewer: str, decision: str, reason: str) -> dict:
    """Review structured observations without treating them as a quality score."""
    if type(analysis_id) is not int or analysis_id <= 0:
        raise ReviewRefused("invalid analysis")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 64:
        raise ReviewRefused("reviewer identity required")
    if decision not in ("reviewed", "rejected"):
        raise ReviewRefused("decision must be reviewed or rejected")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ReviewRefused("reason required")
    reviewer = reviewer.strip()
    try:
        check_derived(reason)
        check_derived(reviewer)
    except ContentRefused as exc:
        raise ReviewRefused(str(exc)) from exc
    with db.session() as s:
        row = s.scalar(select(BenchmarkAnalysis).where(BenchmarkAnalysis.id == analysis_id)
                       .with_for_update())
        if row is None:
            raise ReviewRefused("analysis not found")
        if not row.recorded_by or row.recorded_by.casefold() == reviewer.casefold():
            raise ReviewRefused("independent reviewer required")
        if row.review_state != "proposed":
            raise ReviewRefused("analysis has already been reviewed")
        product = s.get(BenchmarkProduct, row.benchmark_id)
        if product is None or not any(f.get("sha256") == row.file_sha256
                                      for f in (product.files or [])):
            raise ReviewRefused("analysis source is no longer in the purchase manifest")
        lic = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == product.ref))
        if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                or "private_analysis" in (lic.prohibited_uses or []):
            raise ReviewRefused("purchase licence does not allow private analysis")
        changed = s.execute(update(BenchmarkAnalysis).where(
            BenchmarkAnalysis.id == analysis_id, BenchmarkAnalysis.review_state == "proposed",
            BenchmarkAnalysis.recorded_by == row.recorded_by).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow()))
        if changed.rowcount != 1:
            raise ReviewRefused("analysis changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.analysis_reviewed",
                       artifact=f"benchmark-analysis:{analysis_id}",
                       detail={"analysis": analysis_id, "decision": decision,
                               "reason": reason.strip()}))
        return {"analysis": analysis_id, "review_state": decision}
