"""Versioned design knowledge, proposed from existing learning evidence.

The store accepts only registered rule identifiers and structured provenance. A
proposal is not an approval; evaluation and independent approval must be added
before any rule is made active or used by a design consumer.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re

from sqlalchemy import func, select, update

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
_log = logging.getLogger(__name__)


def rule_digest(row) -> str:
    """Digest the versioned rule and its lineage, excluding mutable review state."""
    data = {"id": row.id, "key": row.key, "version": row.version,
            "statement": row.statement, "scope": row.scope,
            "provenance": row.provenance, "producer": row.producer,
            "supersedes": row.supersedes}
    try:
        content = json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise DesignKnowledgeRefused("rule cannot be fingerprinted") from exc
    return hashlib.sha256(content).hexdigest()


def verify_pins(db, pins: list[dict]) -> list[dict]:
    """Verify all frozen knowledge pins or refuse the entire set."""
    from ..teardown.review import principal
    if not isinstance(pins, list):
        raise DesignKnowledgeRefused("knowledge pins must be a list")
    if not pins:
        return []
    expected = {"rule_id", "rule_version", "rule_digest", "evaluation_digest"}
    seen = set()
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) != expected:
            raise DesignKnowledgeRefused("invalid knowledge pin")
        if (type(pin["rule_id"]) is not int or pin["rule_id"] <= 0
                or type(pin["rule_version"]) is not int or pin["rule_version"] <= 0
                or any(not isinstance(pin[key], str) or not re.fullmatch(r"[0-9a-f]{64}", pin[key])
                       for key in ("rule_digest", "evaluation_digest"))):
            raise DesignKnowledgeRefused("invalid knowledge pin")
        if pin["rule_id"] in seen:
            raise DesignKnowledgeRefused("duplicate knowledge pin")
        seen.add(pin["rule_id"])
    verified = []
    with db.session() as s:
        for pin in pins:
            rule = s.get(DesignRule, pin["rule_id"])
            if (rule is None or rule.state != "approved" or rule.version != pin["rule_version"]
                    or rule.active_slot != 1 or not rule.approved_at
                    or not isinstance(rule.approved_by, str) or not rule.approved_by.strip()
                    or not isinstance(rule.producer, str) or not rule.producer.strip()
                    or principal(rule.approved_by) == principal(rule.producer)
                    or rule_digest(rule) != pin["rule_digest"]):
                raise DesignKnowledgeRefused("knowledge pin is not an approved rule version")
            if (rule.statement != {"rule": "include_finishing_checklist", "parameters": {}}
                    or rule.scope != {"writer_section": "finishing"}):
                raise DesignKnowledgeRefused("rule implementation or scope is unsupported")
            approval = s.scalar(select(AuditLog).where(
                AuditLog.action == "design_knowledge.rule_approved",
                AuditLog.artifact == f"design-rule:{rule.id}",
                AuditLog.actor == rule.approved_by).order_by(AuditLog.id.desc()))
            detail = approval.detail if approval is not None and isinstance(approval.detail, dict) else {}
            if detail.get("rule_digest") != pin["rule_digest"] \
                    or detail.get("evaluation_digest") != pin["evaluation_digest"]:
                raise DesignKnowledgeRefused("independent approval evidence is unavailable")
            _revalidate_provenance(s, rule)
            try:
                got = _assert_evaluation(db, s, rule, detail.get("evaluation_id"))
            except ValueError as exc:
                raise DesignKnowledgeRefused("evaluation evidence is unavailable") from exc
            if got != pin["evaluation_digest"]:
                raise DesignKnowledgeRefused("evaluation digest does not match")
            verified.append({"pin": dict(pin), "statement": dict(rule.statement),
                             "scope": dict(rule.scope)})
    return verified


def applicable(db, scope: dict) -> list[dict]:
    """Read approved, evaluated rules for a scope; unavailable evidence means none apply."""
    if (not isinstance(scope, dict) or not scope or not set(scope) <= set(SCOPE_VALUES)
            or any(not isinstance(v, str) or v not in SCOPE_VALUES[k]
                   for k, v in scope.items())):
        raise DesignKnowledgeRefused("invalid structured scope")
    try:
        with db.session() as s:
            rows = list(s.scalars(select(DesignRule).where(DesignRule.state == "approved")))
            candidates = []
            for row in rows:
                if row.scope == scope:
                    audit = s.scalar(select(AuditLog).where(
                        AuditLog.action == "design_knowledge.rule_approved",
                        AuditLog.artifact == f"design-rule:{row.id}",
                        AuditLog.actor == row.approved_by).order_by(AuditLog.id.desc()))
                    if audit is not None and isinstance(audit.detail, dict):
                        candidates.append({"rule_id": row.id, "rule_version": row.version,
                                           "rule_digest": rule_digest(row),
                                           "evaluation_digest": audit.detail.get("evaluation_digest")})
        result = []
        for pin in candidates:
            try:
                result.extend(verify_pins(db, [pin]))
            except (DesignKnowledgeRefused, ValueError):
                _log.warning("design rule %s withheld: evidence invalid or stale", pin["rule_id"])
        return result
    except Exception:
        _log.exception("design knowledge unavailable; no rule applied")
        return []


def verify_cir_pins(db, cir) -> list[dict]:
    """Verify the frozen CIR directives, including their rule-to-pin mapping."""
    from ..cir import knowledge

    try:
        entries = knowledge.markers(cir)
    except ValueError as exc:
        raise DesignKnowledgeRefused(str(exc)) from exc
    verified = verify_pins(db, [entry["pin"] for entry in entries])
    if len(entries) != len(verified) or any(entry["rule"] != record["statement"]["rule"]
           for entry, record in zip(entries, verified)):
        raise DesignKnowledgeRefused("frozen directive does not match its approved rule")
    return verified


def freeze_pins(db, cir, pins: list[dict]):
    """Return a new CIR carrying only the verified closed-vocabulary directives."""
    import copy
    from ..cir import knowledge

    records = verify_pins(db, pins)
    try:
        prior = knowledge.markers(cir)
    except ValueError as exc:
        raise DesignKnowledgeRefused(str(exc)) from exc
    wanted = [knowledge.marker(record["statement"]["rule"], record["pin"]) for record in records]
    existing = [knowledge.marker(entry["rule"], entry["pin"]) for entry in prior]
    if existing and existing != wanted:
        raise DesignKnowledgeRefused("a frozen knowledge record cannot be replaced")
    out = copy.deepcopy(cir)
    if wanted and getattr(out, "provenance", None) is None:
        raise DesignKnowledgeRefused("CIR provenance is required for frozen knowledge")
    if wanted and not existing:
        out.provenance.primitives_used = (*out.provenance.primitives_used, *wanted)
    return out


def write_with_verified_knowledge(db, cir, result, terminology: str = "US", **layout) -> str:
    """Render verified knowledge or the exact no-knowledge baseline on read failure.

    Certification and PDF callers must separately refuse invalid pins: this
    fallback is for non-release consumers, never authority to publish.
    """
    import copy
    from ..cir import knowledge, writer

    try:
        verify_cir_pins(db, cir)
        return writer.write_pattern(cir, result, terminology, **layout)
    except Exception:
        _log.exception("design knowledge unavailable; using baseline")
        plain = copy.deepcopy(cir)
        if getattr(plain, "provenance", None) is not None:
            plain.provenance.primitives_used = tuple(
                item for item in plain.provenance.primitives_used
                if not (isinstance(item, str) and item.startswith(knowledge.PREFIX)))
        return writer.write_pattern(plain, result, terminology, **layout)


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
        if ref == "cir.compiled:compile_failed":
            audits = session.scalars(select(AuditLog).where(AuditLog.action == "cir.compiled"))
            if any((a.detail or {}).get("ok") is False for a in audits):
                return []
        elif ref == "cir.revise_unrepairable:unrepairable":
            audit = session.scalar(select(AuditLog.id).where(
                AuditLog.action == "cir.revise_unrepairable").limit(1))
            if audit is not None:
                return []
    raise DesignKnowledgeRefused("lesson source cannot be verified")


def _revalidate_provenance(session, rule) -> None:
    """Recheck all reviewed sources and current licences at use time."""
    from ..teardown.review import independently_reviewed

    if not isinstance(rule.provenance, list) or not rule.provenance:
        raise DesignKnowledgeRefused("rule evidence is unavailable")
    for item in rule.provenance:
        if (not isinstance(item, dict) or set(item) != {"kind", "id"}
                or not isinstance(item["kind"], str) or item["kind"] not in _SOURCES
                or type(item["id"]) is not int
                or item["id"] <= 0):
            raise DesignKnowledgeRefused("invalid rule provenance")
    supplied = {(item["kind"], item["id"]) for item in rule.provenance}
    if len(supplied) != len(rule.provenance):
        raise DesignKnowledgeRefused("invalid rule provenance")
    supported_finishing_gap = False
    for item in rule.provenance:
        source = session.get(_SOURCES[item["kind"]], item["id"])
        if source is None:
            raise DesignKnowledgeRefused("rule evidence is missing")
        if item["kind"] == "finding":
            _finding_source(session, item["id"])
        elif item["kind"] == "lesson":
            roots = _lesson_roots(session, source)
            if any(("finding", ident) not in supplied for ident in roots):
                raise DesignKnowledgeRefused("lesson root is missing")
        elif item["kind"] == "incident":
            detail = source.detail if isinstance(source.detail, dict) else {}
            roots = detail.get("source_findings")
            if not isinstance(roots, list) or any(type(i) is not int or i <= 0 for i in roots) \
                    or len(roots) != len(set(roots)):
                raise DesignKnowledgeRefused("incident lineage is invalid")
            for ident in roots:
                if ("finding", ident) not in supplied:
                    raise DesignKnowledgeRefused("incident root is missing")
                _finding_source(session, ident)
        else:
            if not independently_reviewed(source):
                raise DesignKnowledgeRefused("analysis review is invalid")
            observations = source.observations if isinstance(source.observations, dict) else {}
            dimensions = observations.get("dimensions")
            supported_finishing_gap |= (observations.get("fully_readable") is True
                and isinstance(dimensions, dict) and dimensions.get("finishing") == "absent")
            product = session.get(BenchmarkProduct, source.benchmark_id)
            if product is None or not any(f.get("sha256") == source.file_sha256
                                           for f in (product.files or [])):
                raise DesignKnowledgeRefused("analysis source is no longer in the manifest")
            lic = session.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == product.ref))
            if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                    or "private_analysis" in (lic.prohibited_uses or []):
                raise DesignKnowledgeRefused("analysis licence no longer permits private use")
    if (rule.statement == {"rule": "include_finishing_checklist", "parameters": {}}
            and not supported_finishing_gap):
        raise DesignKnowledgeRefused("reviewed evidence does not support a finishing gap")


def lineage_digest(session, rule) -> str:
    """Bind an evaluation to the reviewed evidence behind every source id."""
    _revalidate_provenance(session, rule)
    sources = []
    for item in rule.provenance:
        row = session.get(_SOURCES[item["kind"]], item["id"])
        value = {"kind": item["kind"], "id": item["id"]}
        if item["kind"] in ("finding", "analysis"):
            value.update({"reviewed_sha256": row.reviewed_sha256,
                          "reviewed_by": row.reviewed_by})
        elif item["kind"] == "lesson":
            value.update({"evidence_ref": row.evidence_ref, "roots": row.source_findings,
                          "withdrawn": str(row.withdrawn_at), "superseded_by": row.superseded_by})
        else:
            value["detail"] = row.detail
        sources.append(value)
    try:
        encoded = json.dumps(sources, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise DesignKnowledgeRefused("source evidence cannot be fingerprinted") from exc
    return hashlib.sha256(encoded).hexdigest()


def _assert_evaluation(db, session, rule, evaluation_id: int) -> str:
    from ..quality import design_eval
    from ..core.models import DesignEvaluationRun

    if type(evaluation_id) is not int or evaluation_id <= 0:
        raise DesignKnowledgeRefused("completed evaluation is required")
    audit = session.get(AuditLog, evaluation_id)
    if audit is None or audit.action != "design_eval.completed" \
            or audit.actor != "design_evaluator" or audit.artifact != f"design-rule:{rule.id}":
        raise DesignKnowledgeRefused("completed evaluation is required")
    report = audit.detail
    run = session.scalar(select(DesignEvaluationRun).where(
        DesignEvaluationRun.audit_id == audit.id, DesignEvaluationRun.rule_id == rule.id))
    try:
        valid = (isinstance(report, dict) and report.get("state") == "passed"
            and run is not None and report.get("run_key") == run.run_key
            and report.get("approval_evidence_complete") is True
            and report.get("rule_id") == rule.id and report.get("rule_key") == rule.key
            and report.get("rule_version") == rule.version
            and report.get("rule_sha256") == rule_digest(rule)
            and report.get("lineage_sha256") == lineage_digest(session, rule)
            and report.get("implementation_sha256") == design_eval.implementation_digest(db)
            and report.get("corpus_sha256") == design_eval.corpus_digest(db)
            and report.get("case_set_sha256") == design_eval.load_cases(db=db)["sha256"]
            and design_eval.classify_evaluation(report) == "passed")
    except design_eval.DesignEvaluationRefused as exc:
        raise DesignKnowledgeRefused("evaluation evidence is unavailable") from exc
    if not valid:
        raise DesignKnowledgeRefused("evaluation is incomplete, stale or regressed")
    return design_eval._digest(report)


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


def review_rule(db, rule_id: int, *, reviewer: str, decision: str, reason: str,
                evaluation_id: int | None = None) -> dict:
    """Independently review a proposal against its current held-out evidence."""
    from ..core.models import utcnow
    from ..teardown.library import check_derived
    from ..teardown.review import principal
    from sqlalchemy.exc import IntegrityError

    if type(rule_id) is not int or rule_id <= 0:
        raise DesignKnowledgeRefused("invalid rule id")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 120:
        raise DesignKnowledgeRefused("reviewer identity required")
    if decision not in ("approve", "reject", "retire"):
        raise DesignKnowledgeRefused("decision must be approve, reject or retire")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise DesignKnowledgeRefused("review reason required")
    check_derived(reviewer)
    check_derived(reason)
    reviewer = reviewer.strip()
    with db.session() as s:
        rule = s.scalar(select(DesignRule).where(DesignRule.id == rule_id).with_for_update())
        if rule is None:
            raise DesignKnowledgeRefused("rule not found")
        if not rule.producer or principal(rule.producer) == principal(reviewer):
            raise DesignKnowledgeRefused("independent reviewer required")
        if decision == "retire":
            if rule.state != "approved" or rule.active_slot != 1:
                raise DesignKnowledgeRefused("an active rule is required")
            changed = s.execute(update(DesignRule).where(
                DesignRule.id == rule_id, DesignRule.state == "approved",
                DesignRule.active_slot == 1).values(state="retired", active_slot=None))
            if changed.rowcount != 1:
                raise DesignKnowledgeRefused("rule changed during retirement")
            s.add(AuditLog(actor=reviewer, action="design_knowledge.rule_retired",
                           artifact=f"design-rule:{rule_id}",
                           detail={"rule_id": rule_id, "version": rule.version,
                                   "reason": reason.strip()}))
            return {"rule_id": rule_id, "state": "retired", "decision": "retired"}
        if rule.state != "proposed":
            raise DesignKnowledgeRefused("a proposed rule is required")
        if decision == "approve":
            _revalidate_provenance(s, rule)
            evaluation_digest = _assert_evaluation(db, s, rule, evaluation_id)
            if s.scalar(select(DesignRule.id).where(DesignRule.active_slot == 1)) is not None:
                raise DesignKnowledgeRefused("another knowledge version is active")
            stamp = utcnow()
            digest = rule_digest(rule)
            try:
                changed = s.execute(update(DesignRule).where(
                    DesignRule.id == rule_id, DesignRule.state == "proposed",
                    DesignRule.producer == rule.producer).values(
                        state="approved", approved_by=reviewer, approved_at=stamp, active_slot=1))
            except IntegrityError as exc:
                raise DesignKnowledgeRefused("another knowledge version is active") from exc
            if changed.rowcount != 1:
                raise DesignKnowledgeRefused("rule changed during review")
            s.add(AuditLog(actor=reviewer, action="design_knowledge.rule_approved",
                           artifact=f"design-rule:{rule_id}", detail={
                               "rule_digest": digest, "evaluation_id": evaluation_id,
                               "evaluation_digest": evaluation_digest, "reason": reason.strip()}))
            return {"rule_id": rule_id, "state": "approved", "decision": "approved",
                    "pin": {"rule_id": rule_id, "rule_version": rule.version,
                            "rule_digest": digest, "evaluation_digest": evaluation_digest}}
        changed = s.execute(update(DesignRule).where(
            DesignRule.id == rule_id, DesignRule.state == "proposed",
            DesignRule.producer == rule.producer).values(state="retired"))
        if changed.rowcount != 1:
            raise DesignKnowledgeRefused("rule changed during review")
        s.add(AuditLog(actor=reviewer, action="design_knowledge.rule_reviewed",
                       artifact=f"design-rule:{rule_id}",
                       detail={"rule_id": rule_id, "version": rule.version,
                               "decision": "rejected", "reason": reason.strip(),
                               "reviewed_at": utcnow().isoformat()}))
        return {"rule_id": rule_id, "state": "retired", "decision": "rejected"}
