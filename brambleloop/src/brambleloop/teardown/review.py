"""Independent review of a reference finding, with an atomic audit record."""
from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select, update

from ..core.models import (AuditLog, BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct,
                           BenchmarkTechniqueObservation, TeardownFinding, utcnow)
from .library import ContentRefused, check_derived


class ReviewRefused(ValueError):
    pass


def principal(value: str) -> str:
    """All owner sessions represent the same owner, not independent people."""
    name = (value or "").strip().casefold()
    return "owner" if name == "owner" or name.startswith("owner:") else name


def evidence_digest(row) -> str:
    """Bind a review to the exact immutable evidence used by its consumers."""
    if isinstance(row, BenchmarkAnalysis):
        data = {"id": row.id, "benchmark_id": row.benchmark_id,
                "file_sha256": row.file_sha256, "observations": row.observations,
                "recorded_by": row.recorded_by}
    elif isinstance(row, BenchmarkTechniqueObservation):
        data = {"id": row.id, "analysis_id": row.analysis_id,
                "extractor_version": row.extractor_version, "extractor_sha256": row.extractor_sha256,
                "source_digest": row.source_digest,
                "file_sha256": row.file_sha256, "observation": row.observation,
                "recorded_by": row.recorded_by}
    elif isinstance(row, TeardownFinding):
        detail = row.detail if isinstance(row.detail, dict) else {}
        data = {"id": row.id, "benchmark_ref": row.benchmark_ref, "dimension": row.dimension,
                "score": row.score, "mechanism": row.mechanism, "improvement": row.improvement,
                "confidence": row.confidence, "raw_notes": row.raw_notes,
                "detail": {key: detail.get(key) for key in ("audit", "element", "element_score")},
                "recorded_by": row.recorded_by, "recorder_verified": row.recorder_verified}
    else:
        raise ReviewRefused("unsupported review evidence")
    try:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewRefused("review evidence is not serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def independent_decision(row, decision: str) -> bool:
    """A state label alone is not evidence that a different actor reviewed it."""
    recorder = getattr(row, "recorded_by", None)
    reviewer = getattr(row, "reviewed_by", None)
    independent = (decision in ("reviewed", "rejected")
            and getattr(row, "review_state", None) == decision
            and isinstance(recorder, str) and bool(recorder.strip())
            and isinstance(reviewer, str) and bool(reviewer.strip())
            and principal(recorder) != principal(reviewer)
            and getattr(row, "reviewed_at", None) is not None)
    if isinstance(row, TeardownFinding) and row.recorder_verified is not True:
        return False
    if not independent:
        return False
    try:
        return bool(row.reviewed_sha256) and row.reviewed_sha256 == evidence_digest(row)
    except ReviewRefused:
        return False


def independently_reviewed(row) -> bool:
    return independent_decision(row, "reviewed")


_SUPPORTED_TECHNIQUE_EXTRACTORS = frozenset({"round_joining_v1"})


def _technique_source_valid(session, row, *, lock=True) -> bool:
    from .analysis_store import manifested_pdf

    observation = row.observation
    if (row.extractor_version not in _SUPPORTED_TECHNIQUE_EXTRACTORS
            or not isinstance(row.extractor_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", row.extractor_sha256)
            or not isinstance(observation, dict)
            or set(observation) != {"kind", "pages"}
            or observation.get("kind") not in ("unknown", "mixed_cues", "joined_rounds_cue", "spiral_rounds_cue")
            or not isinstance(observation.get("pages"), list)
            or any(type(p) is not int or p <= 0 for p in observation["pages"])
            or observation["pages"] != sorted(set(observation["pages"]))
            or (observation["kind"] == "unknown") != (not observation["pages"])):
        return False
    source_query = select(BenchmarkAnalysis).where(BenchmarkAnalysis.id == row.analysis_id)
    source = session.scalar(source_query.with_for_update() if lock else source_query)
    if source is None or source.file_sha256 != row.file_sha256 or evidence_digest(source) != row.source_digest:
        return False
    product_query = select(BenchmarkProduct).where(BenchmarkProduct.id == source.benchmark_id)
    product = session.scalar(product_query.with_for_update() if lock else product_query)
    if not manifested_pdf(product, row.file_sha256):
        return False
    licence_query = select(BenchmarkLicence).where(BenchmarkLicence.source_ref == product.ref)
    licence = session.scalar(licence_query.with_for_update() if lock else licence_query)
    return bool(licence is not None and "private_analysis" in (licence.allowed_uses or [])
                and "private_analysis" not in (licence.prohibited_uses or []))


def pending_technique_observations(db) -> list[dict]:
    """Expose only validated, closed-vocabulary evidence in the owner inbox."""
    with db.session() as s:
        rows = s.scalars(select(BenchmarkTechniqueObservation).where(
            BenchmarkTechniqueObservation.review_state == "proposed").order_by(
            BenchmarkTechniqueObservation.id).limit(100))
        result = []
        for row in rows:
            try:
                valid = _technique_source_valid(s, row, lock=False)
            except (ReviewRefused, TypeError, ValueError):
                valid = False
            if valid:
                result.append({"id": row.id, "analysis_id": row.analysis_id,
                               "kind": row.observation["kind"],
                               "pages": list(row.observation["pages"])})
        return result


def independently_reviewed_technique(db, observation_id: int) -> bool:
    """A review is usable only while its exact source and licence remain current."""
    if type(observation_id) is not int or observation_id <= 0:
        return False
    with db.session() as s:
        row = s.get(BenchmarkTechniqueObservation, observation_id)
        try:
            return bool(row is not None and independently_reviewed(row) and _technique_source_valid(s, row))
        except ReviewRefused:
            return False


def review_technique_observation(db, observation_id: int, *, reviewer: str,
                                 decision: str, reason: str) -> dict:
    if type(observation_id) is not int or observation_id <= 0:
        raise ReviewRefused("invalid technique observation")
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
        row = s.scalar(select(BenchmarkTechniqueObservation).where(
            BenchmarkTechniqueObservation.id == observation_id).with_for_update())
        if row is None or not row.recorded_by or principal(row.recorded_by) == principal(reviewer):
            raise ReviewRefused("independent reviewer required")
        if not _reviewable(row):
            raise ReviewRefused("technique observation has already been reviewed")
        if not _technique_source_valid(s, row):
            raise ReviewRefused("technique source or licence is no longer valid")
        digest = evidence_digest(row)
        changed = s.execute(update(BenchmarkTechniqueObservation).where(
            BenchmarkTechniqueObservation.id == observation_id,
            BenchmarkTechniqueObservation.review_state == row.review_state,
            BenchmarkTechniqueObservation.recorded_by == row.recorded_by,
            BenchmarkTechniqueObservation.reviewed_sha256 == row.reviewed_sha256).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow(), reviewed_sha256=digest))
        if changed.rowcount != 1:
            raise ReviewRefused("technique observation changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.technique_reviewed",
                       artifact=f"benchmark-technique:{observation_id}", detail={
                           "observation": observation_id, "decision": decision,
                           "reason": reason.strip(), "evidence_sha256": digest}))
        return {"observation": observation_id, "review_state": decision}


def _reviewable(row) -> bool:
    """A changed or legacy review needs a fresh independent decision."""
    state = getattr(row, "review_state", None)
    return state == "proposed" or (state in ("reviewed", "rejected")
                                   and not independent_decision(row, state))


def attest_finding_recorder(db, finding_id: int, *, recorder: str, actor: str,
                            reason: str) -> dict:
    """Record an owner's explicit attestation for an unattributed legacy finding."""
    if type(finding_id) is not int or finding_id <= 0 or principal(actor) != "owner":
        raise ReviewRefused("owner attestation and valid finding required")
    if not isinstance(recorder, str) or len(recorder) > 120:
        raise ReviewRefused("recorder identity required")
    recorder = recorder.strip()
    if not (recorder == "owner" or recorder.startswith("external:")
            or recorder.startswith("agent:")) or recorder.endswith(":"):
        raise ReviewRefused("recorder must identify the owner, an external person, or an agent")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ReviewRefused("attestation reason required")
    check_derived(recorder)
    check_derived(reason)
    with db.session() as s:
        row = s.scalar(select(TeardownFinding).where(TeardownFinding.id == finding_id).with_for_update())
        if row is None or row.recorder_verified is True:
            raise ReviewRefused("finding is missing or its recorder is already established")
        prior = row.recorded_by
        changed = s.execute(update(TeardownFinding).where(
            TeardownFinding.id == finding_id, TeardownFinding.recorder_verified == row.recorder_verified,
            TeardownFinding.recorded_by == prior).values(
                recorded_by=recorder, recorder_verified=True, review_state="proposed",
                reviewed_by=None, reviewed_at=None, reviewed_sha256=None))
        if changed.rowcount != 1:
            raise ReviewRefused("finding changed during attestation")
        s.add(AuditLog(actor="owner", action="teardown.recorder_attested",
                       artifact=f"teardown-finding:{finding_id}", detail={
                           "finding": finding_id, "recorder": recorder,
                           "reason": reason.strip(), "prior_recorder_known": bool(prior)}))
        return {"finding": finding_id, "recorder": recorder, "review_state": "proposed"}


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
        if not row.recorded_by or row.recorder_verified is not True:
            raise ReviewRefused("recorder is unknown; independent review cannot be established")
        if principal(row.recorded_by) == principal(reviewer):
            raise ReviewRefused("recorder cannot review their own finding")
        if not _reviewable(row):
            raise ReviewRefused("finding has already been reviewed")
        digest = evidence_digest(row)
        changed = s.execute(update(TeardownFinding).where(
            TeardownFinding.id == finding_id, TeardownFinding.review_state == row.review_state,
            TeardownFinding.recorded_by == row.recorded_by,
            TeardownFinding.reviewed_sha256 == row.reviewed_sha256).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow(),
                reviewed_sha256=digest))
        if changed.rowcount != 1:
            raise ReviewRefused("finding changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.finding_reviewed",
                       artifact=f"teardown-finding:{finding_id}",
                       detail={"finding": finding_id, "decision": decision,
                               "reason": reason.strip(), "evidence_sha256": digest}))
        return {"finding": finding_id, "review_state": decision}


def review_analysis(db, analysis_id: int, *, reviewer: str, decision: str, reason: str) -> dict:
    """Review structured observations without treating them as a quality score."""
    from .analysis_store import manifested_pdf
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
        if not row.recorded_by or principal(row.recorded_by) == principal(reviewer):
            raise ReviewRefused("independent reviewer required")
        if not _reviewable(row):
            raise ReviewRefused("analysis has already been reviewed")
        product = s.scalar(select(BenchmarkProduct).where(
            BenchmarkProduct.id == row.benchmark_id).with_for_update())
        if not manifested_pdf(product, row.file_sha256):
            raise ReviewRefused("analysis source is no longer in the purchase manifest")
        lic = s.scalar(select(BenchmarkLicence).where(
            BenchmarkLicence.source_ref == product.ref).with_for_update())
        if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                or "private_analysis" in (lic.prohibited_uses or []):
            raise ReviewRefused("purchase licence does not allow private analysis")
        digest = evidence_digest(row)
        changed = s.execute(update(BenchmarkAnalysis).where(
            BenchmarkAnalysis.id == analysis_id, BenchmarkAnalysis.review_state == row.review_state,
            BenchmarkAnalysis.recorded_by == row.recorded_by,
            BenchmarkAnalysis.reviewed_sha256 == row.reviewed_sha256).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow(),
                reviewed_sha256=digest))
        if changed.rowcount != 1:
            raise ReviewRefused("analysis changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.analysis_reviewed",
                       artifact=f"benchmark-analysis:{analysis_id}",
                       detail={"analysis": analysis_id, "decision": decision,
                               "reason": reason.strip(), "evidence_sha256": digest}))
        return {"analysis": analysis_id, "review_state": decision}
