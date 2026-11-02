"""Versioned design knowledge, proposed from existing learning evidence.

The store accepts only registered rule identifiers and structured provenance. A
proposal is not an approval; evaluation and independent approval must be added
before any rule is made active or used by a design consumer.
"""
from __future__ import annotations

import hashlib
import math
import re

from sqlalchemy import func, select

from ..core.models import (AuditLog, BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct,
                           DesignRule, Incident, Lesson, SupportCase, TeardownFinding)


class DesignKnowledgeRefused(ValueError):
    """The proposal cannot be represented safely as design knowledge."""


# Rule meanings belong to our own implementation. Source text and arbitrary
# instructions cannot be embedded as a parameter.
RULES = {"include_finishing_checklist": frozenset()}
# Expand only alongside a consumer that understands the new scope.
SCOPE_VALUES = {"writer_section": frozenset({"finishing"})}
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SOURCES = {"lesson": Lesson, "finding": TeardownFinding, "incident": Incident,
            "analysis": BenchmarkAnalysis}


def _finding_source(session, finding_id: int):
    from ..teardown.enforce import MIN_BINDING_CONFIDENCE
    from ..teardown.review import independently_reviewed

    finding = session.scalar(select(TeardownFinding).where(
        TeardownFinding.id == finding_id).with_for_update())
    if finding is None or not independently_reviewed(finding):
        raise DesignKnowledgeRefused("reference finding lacks independent review")
    confidence = finding.confidence
    if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not math.isfinite(confidence) or confidence < MIN_BINDING_CONFIDENCE
            or confidence > 1):
        raise DesignKnowledgeRefused("reference finding confidence is insufficient")
    product = session.scalar(select(BenchmarkProduct).where(
        BenchmarkProduct.ref == finding.benchmark_ref).with_for_update())
    if product is None or not product.files:
        raise DesignKnowledgeRefused("reference purchase evidence is missing")
    lic = session.scalar(select(BenchmarkLicence).where(
        BenchmarkLicence.source_ref == product.ref).with_for_update())
    if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
            or "private_analysis" in (lic.prohibited_uses or []):
        raise DesignKnowledgeRefused("reference licence does not permit private analysis")
    return finding


def _lesson_roots(session, lesson) -> list[int]:
    """Trace known lesson producers; legacy or untraceable provenance fails closed."""
    from ..teardown import enforce
    from ..teardown.audits import STRONG, WEAK

    if lesson.withdrawn_at is not None or lesson.superseded_by is not None:
        raise DesignKnowledgeRefused("lesson is withdrawn or superseded")
    roots = lesson.source_findings
    if (not isinstance(roots, list) or any(type(i) is not int or i <= 0 for i in roots)
            or len(roots) != len(set(roots))):
        raise DesignKnowledgeRefused("lesson provenance is unavailable or invalid")
    ref = lesson.evidence_ref or ""
    if ref.startswith("teardown_requirement:"):
        if not roots:
            raise DesignKnowledgeRefused("teardown lesson has no finding provenance")
        try:
            prefix, kind, stamp = ref.rsplit(":", 2)
            key = prefix.removeprefix("teardown_requirement:")
        except ValueError as exc:
            raise DesignKnowledgeRefused("teardown lesson provenance is malformed") from exc
        expected = hashlib.sha256(",".join(str(i) for i in sorted(roots)).encode()).hexdigest()[:16]
        if stamp != f"roots-{expected}" or kind not in ("exceed", "prevent", "clarify"):
            raise DesignKnowledgeRefused("teardown lesson provenance does not match")
        findings = [_finding_source(session, ident) for ident in roots]
        if any(enforce._key(f)[0] != key for f in findings):
            raise DesignKnowledgeRefused("lesson references findings from a different requirement")
        scores = [enforce._score(f) for f in findings]
        correct = ((kind == "exceed" and max(scores) >= STRONG) or
                   (kind == "prevent" and min(scores) <= WEAK) or
                   (kind == "clarify" and len({f.benchmark_ref for f in findings}) >= 2
                    and max(scores) - min(scores) >= enforce.DISAGREEMENT))
        if not correct:
            raise DesignKnowledgeRefused("lesson no longer matches its reviewed findings")
        return sorted(roots)
    if roots:
        raise DesignKnowledgeRefused("lesson finding lineage cannot be verified")
    if ref.startswith("support_cases:") and lesson.origin_cell == "customer_experience":
        try:
            slug, ident = ref[len("support_cases:"):].rsplit(":", 1)
            case = session.get(SupportCase, int(ident))
        except (ValueError, TypeError):
            case = None
        if case is not None and case.product_slug == slug:
            return []
    if lesson.origin_cell == "quality" and lesson.subject == "defect":
        action = {"cir.compiled:compile_failed": "cir.compiled",
                  "cir.revise_unrepairable:unrepairable": "cir.revise_unrepairable"}.get(ref)
        if action:
            audits = session.scalars(select(AuditLog).where(AuditLog.action == action))
            if any(action != "cir.compiled" or (a.detail or {}).get("ok") is False for a in audits):
                return []
    raise DesignKnowledgeRefused("lesson source cannot be verified")


def propose(db, *, key: str, statement: dict, scope: dict, provenance: list,
            producer: str, supersedes: int | None = None) -> dict:
    """Persist a proposal; its evidence must already exist in the learning system."""
    if not isinstance(key, str) or not _TOKEN.fullmatch(key):
        raise DesignKnowledgeRefused("invalid rule key")
    if not isinstance(producer, str) or not producer.strip() or len(producer) > 120:
        raise DesignKnowledgeRefused("producer is required")
    from ..teardown.library import check_derived

    check_derived(producer)
    if not isinstance(statement, dict) or set(statement) != {"rule", "parameters"}:
        raise DesignKnowledgeRefused("statement needs a registered rule and parameters")
    rule, parameters = statement["rule"], statement["parameters"]
    if not isinstance(rule, str) or rule not in RULES or not isinstance(parameters, dict):
        raise DesignKnowledgeRefused("unknown rule or invalid parameters")
    if set(parameters) != RULES[rule]:
        raise DesignKnowledgeRefused("parameters do not match the rule vocabulary")
    if (not isinstance(scope, dict) or not scope or not set(scope) <= set(SCOPE_VALUES)
            or any(not isinstance(v, str) or v not in SCOPE_VALUES[k]
                   for k, v in scope.items())):
        raise DesignKnowledgeRefused("invalid structured scope")
    if not isinstance(provenance, list) or not provenance:
        raise DesignKnowledgeRefused("evidence is required")
    evidence = []
    provided = set()
    with db.session() as session:
        for item in provenance:
            if (not isinstance(item, dict) or set(item) != {"kind", "id"}
                    or not isinstance(item.get("kind"), str)
                    or item.get("kind") not in _SOURCES or type(item.get("id")) is not int
                    or item["id"] <= 0):
                raise DesignKnowledgeRefused("invalid evidence reference")
            source_type = _SOURCES[item["kind"]]
            source = session.scalar(select(source_type).where(source_type.id == item["id"])
                                    .with_for_update())
            if source is None:
                raise DesignKnowledgeRefused("evidence does not exist")
            if item["kind"] == "finding":
                _finding_source(session, item["id"])
            if item["kind"] == "analysis":
                from ..teardown.review import independently_reviewed

                if not independently_reviewed(source):
                    raise DesignKnowledgeRefused("reference evidence has not been independently reviewed")
            if item["kind"] == "analysis":
                product = session.scalar(select(BenchmarkProduct).where(
                    BenchmarkProduct.id == source.benchmark_id).with_for_update())
                if product is None or not any(f.get("sha256") == source.file_sha256
                                               for f in (product.files or [])):
                    raise DesignKnowledgeRefused("analysis source is no longer in the manifest")
                lic = session.scalar(select(BenchmarkLicence).where(
                    BenchmarkLicence.source_ref == product.ref).with_for_update())
                if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                        or "private_analysis" in (lic.prohibited_uses or []):
                    raise DesignKnowledgeRefused("analysis licence no longer permits private use")
            marker = (item["kind"], item["id"])
            if marker in provided:
                raise DesignKnowledgeRefused("duplicate evidence")
            provided.add(marker)
            if item not in evidence:
                evidence.append(dict(item))
            if item["kind"] == "lesson":
                for finding_id in _lesson_roots(session, source):
                    root = {"kind": "finding", "id": finding_id}
                    if root not in evidence:
                        evidence.append(root)
            if item["kind"] == "incident":
                detail = source.detail if isinstance(source.detail, dict) else {}
                roots = detail.get("source_findings")
                if (not isinstance(roots, list) or any(type(i) is not int or i <= 0 for i in roots)
                        or len(roots) != len(set(roots))):
                    raise DesignKnowledgeRefused("incident finding lineage is unavailable")
                for finding_id in roots:
                    _finding_source(session, finding_id)
                    root = {"kind": "finding", "id": finding_id}
                    if root not in evidence:
                        evidence.append(root)
        previous = session.get(DesignRule, supersedes) if supersedes is not None else None
        if supersedes is not None and (previous is None or previous.key != key):
            raise DesignKnowledgeRefused("superseded version must belong to this rule")
        version = (session.scalar(select(func.max(DesignRule.version))
                                  .where(DesignRule.key == key)) or 0) + 1
        row = DesignRule(key=key, version=version, statement=dict(statement), scope=dict(scope),
                         provenance=evidence, producer=producer.strip(), state="proposed",
                         supersedes=supersedes)
        session.add(row)
        session.flush()
        return {"id": row.id, "key": row.key, "version": row.version, "state": row.state}


def propose_from_analysis(db, analysis_id: int) -> dict:
    """Propose a bounded rule for a reviewed, fully read missing section.

    This records a hypothesis, not evidence of improved quality. The proposal is
    idempotent per source; approval must still require a held-out evaluation.
    """
    from sqlalchemy.exc import IntegrityError

    if type(analysis_id) is not int or analysis_id <= 0:
        raise DesignKnowledgeRefused("invalid analysis")
    key = f"finishing_from_analysis_{analysis_id}"
    try:
        with db.session() as s:
            source = s.scalar(select(BenchmarkAnalysis).where(BenchmarkAnalysis.id == analysis_id)
                              .with_for_update())
            from ..teardown.review import independently_reviewed

            if source is None or not independently_reviewed(source):
                return {"proposed": False, "reason": "not_reviewed"}
            data = source.observations or {}
            if data.get("fully_readable") is not True or \
                    (data.get("dimensions") or {}).get("finishing") != "absent":
                return {"proposed": False, "reason": "no_observed_gap"}
            existing = s.scalar(select(DesignRule).where(DesignRule.key == key))
            if existing is not None:
                return {"proposed": False, "reason": "already_proposed", "id": existing.id}
            product = s.scalar(select(BenchmarkProduct).where(
                BenchmarkProduct.id == source.benchmark_id).with_for_update())
            if product is None or not any(f.get("sha256") == source.file_sha256
                                           for f in (product.files or [])):
                raise DesignKnowledgeRefused("analysis source is no longer in the manifest")
            lic = s.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == product.ref).with_for_update())
            if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                    or "private_analysis" in (lic.prohibited_uses or []):
                raise DesignKnowledgeRefused("analysis licence no longer permits private use")
            row = DesignRule(key=key, version=1, statement={"rule": "include_finishing_checklist",
                "parameters": {}}, scope={"writer_section": "finishing"},
                provenance=[{"kind": "analysis", "id": analysis_id}],
                producer="teardown_analyst", state="proposed")
            s.add(row)
            s.flush()
            return {"proposed": True, "id": row.id, "key": key, "version": 1,
                    "state": "proposed"}
    except IntegrityError:
        with db.session() as s:
            existing = s.scalar(select(DesignRule).where(DesignRule.key == key))
            if existing is None:
                raise
            return {"proposed": False, "reason": "already_proposed", "id": existing.id}
