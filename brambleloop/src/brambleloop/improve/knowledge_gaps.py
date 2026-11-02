"""Track reference-derived knowledge gaps through the existing incident system."""
from __future__ import annotations

from sqlalchemy import select

from ..core.models import BenchmarkAnalysis, DesignRule
from ..ops import incident_lifecycle
from ..teardown.review import independent_decision, independently_reviewed
from . import design_knowledge


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
        rule = s.scalar(select(DesignRule).where(
            DesignRule.key == f"finishing_from_analysis_{analysis_id}").order_by(
                DesignRule.version.desc()))
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
        if state in ("analysis_unknown", "review_rejected", "review_required", "awaiting_approved_rule"):
            _, opened = incident_lifecycle.open_or_restate(
                s, signature=signature, severity="P2", halts_publication=False,
                summary="Reference observation needs reviewed design knowledge",
                detail={"source_analysis_id": analysis_id, "rule_id": rule_id, "state": state,
                        "source_findings": []})
            return {"state": state, "changed": opened}
        resolved = incident_lifecycle.resolve_signatures(s, [signature], resolution=(
            "The current independently approved rule passed verification" if state == "addressed"
            else "The current observation no longer supports this gap"))
        return {"state": state, "changed": bool(resolved)}
