"""Track reference-derived knowledge gaps through the existing incident system."""
from __future__ import annotations

from sqlalchemy import select

from ..core.models import BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct, DesignRule
from ..ops import incident_lifecycle
from ..teardown.review import independent_decision, independently_reviewed
from . import design_knowledge


def _architecture_complete(session, source, reviewed: bool) -> bool:
    """Only current, independently reviewed evidence can close this knowledge gap."""
    from ..teardown.audits import PDF_ARCHITECTURE

    data = source.observations if isinstance(source.observations, dict) else {}
    answers = data.get("architecture")
    product = session.scalar(select(BenchmarkProduct).where(
        BenchmarkProduct.id == source.benchmark_id).with_for_update())
    if (not reviewed or product is None or not any(
            isinstance(f, dict) and f.get("sha256") == source.file_sha256
            for f in (product.files or []))):
        return False
    terms = session.scalar(select(BenchmarkLicence).where(
        BenchmarkLicence.source_ref == product.ref).with_for_update())
    if (terms is None or "private_analysis" not in (terms.allowed_uses or [])
            or "private_analysis" in (terms.prohibited_uses or [])):
        return False
    if (data.get("architecture_complete") is not True or data.get("architecture_withheld") != []
            or not isinstance(answers, dict) or set(answers) != set(PDF_ARCHITECTURE.element_keys)):
        return False
    return all(isinstance(value, dict) and set(value) == {"present", "pages"}
               and type(value["present"]) is bool and isinstance(value["pages"], list)
               and all(type(page) is int and page > 0 for page in value["pages"])
               for value in answers.values())


def observe_analysis(db, analysis_id: int) -> dict:
    """Record the gap until a current, verified approved rule addresses it."""
    signature = f"learning.knowledge_gap:analysis:{analysis_id}"
    with db.session() as s:
        source = s.get(BenchmarkAnalysis, analysis_id)
        if source is None:
            return {"state": "missing", "changed": False}
        observations = source.observations if isinstance(source.observations, dict) else {}
        dimensions = observations.get("dimensions")
        verdict = dimensions.get("finishing") if isinstance(dimensions, dict) else None
        readable = observations.get("fully_readable") is True
        reviewed = independently_reviewed(source)
        rejected = independent_decision(source, "rejected")
        rules = list(s.scalars(select(DesignRule).order_by(DesignRule.version.desc(),
                                                          DesignRule.id.desc())))
        matching = [item for item in rules if {"kind": "analysis", "id": analysis_id}
                    in (item.provenance or [])]
        rule = (next((item for item in matching if item.state == "approved"), None)
                or next((item for item in matching if item.state == "proposed"), None)
                or (matching[0] if matching else None))
        rule_id = rule.id if rule else None
        rule_state = rule.state if rule else None
    if rejected:
        state = "review_rejected"
    elif not readable or verdict not in ("observed", "absent"):
        state = "analysis_unknown"
    elif not reviewed:
        state = "review_required"
    elif verdict == "absent":
        state = "awaiting_approved_rule"
        if rule_state == "approved":
            try:
                records = design_knowledge.applicable(db, {"writer_section": "finishing"})
                if any(record["pin"]["rule_id"] == rule_id for record in records):
                    state = "addressed"
            except Exception:
                # Missing evidence never closes the gap.
                state = "awaiting_approved_rule"
    else:
        state = "not_observed"
    with db.session() as s:
        current = s.scalar(select(BenchmarkAnalysis).where(
            BenchmarkAnalysis.id == analysis_id).with_for_update())
        architecture_complete = bool(current is not None and _architecture_complete(
            s, current, independently_reviewed(current)))
        architecture_signature = f"learning.knowledge_gap:architecture:{analysis_id}"
        if architecture_complete:
            architecture_changed = bool(incident_lifecycle.resolve_signatures(
                s, [architecture_signature], resolution="Current licensed architecture observations "
                "are complete and independently reviewed"))
        else:
            _, architecture_changed = incident_lifecycle.open_or_restate(
                s, signature=architecture_signature, severity="P2", halts_publication=False,
                summary="Reference architecture has unknown or unreviewed elements",
                detail={"source_analysis_id": analysis_id, "state": "evidence_incomplete",
                        "source_findings": []})
        if state in ("analysis_unknown", "review_rejected", "review_required", "awaiting_approved_rule"):
            _, opened = incident_lifecycle.open_or_restate(
                s, signature=signature, severity="P2", halts_publication=False,
                summary="Reference observation needs reviewed design knowledge",
                detail={"source_analysis_id": analysis_id, "rule_id": rule_id, "state": state,
                        "source_findings": []})
            return {"state": state, "changed": opened or architecture_changed}
        resolved = incident_lifecycle.resolve_signatures(s, [signature], resolution=(
            "The current independently approved rule passed verification" if state == "addressed"
            else "The current observation no longer supports this gap"))
        return {"state": state, "changed": bool(resolved) or architecture_changed}
