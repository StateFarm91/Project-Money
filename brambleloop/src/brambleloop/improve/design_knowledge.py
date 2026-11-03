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
from ..teardown.analysis_store import manifested_pdf


class DesignKnowledgeRefused(ValueError):
    """The proposal cannot be represented safely as design knowledge."""


# Rule meanings belong to our own implementation. Source text and arbitrary
# instructions cannot be embedded as a parameter.
RULES = {"include_finishing_checklist": frozenset(),
         "include_checklist_and_end_check": frozenset()}
# Expand only alongside a consumer that understands the new scope.
SCOPE_VALUES = {"writer_section": frozenset({"finishing"}),
                "construction_family": frozenset({"flat_rows", "joined_rounds", "spiral_rounds"})}
_SCOPE_SLOTS = {None: 1, "flat_rows": 2, "joined_rounds": 3, "spiral_rounds": 4}
_SCOPE_GUARD_KEY = "system_design_scope_guard"
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SOURCES = {"lesson": Lesson, "finding": TeardownFinding, "incident": Incident,
            "analysis": BenchmarkAnalysis}
_log = logging.getLogger(__name__)


def scope_slot(scope: dict) -> int:
    """A closed, stable scope maps to its database conflict slot."""
    if (not isinstance(scope, dict) or set(scope) not in
            ({"writer_section"}, {"writer_section", "construction_family"})
            or scope.get("writer_section") != "finishing"
            or ("construction_family" in scope and
                (not isinstance(scope["construction_family"], str) or
                 scope["construction_family"] not in SCOPE_VALUES["construction_family"]))):
        raise DesignKnowledgeRefused("invalid structured scope")
    return _SCOPE_SLOTS[scope.get("construction_family")]


def scope_matches(scope: dict, cir) -> bool:
    scope_slot(scope)
    family = scope.get("construction_family")
    return family is None or family == getattr(cir, "construction", None)


def scope_overlaps(left: dict, right: dict) -> bool:
    scope_slot(left)
    scope_slot(right)
    return (left.get("construction_family") is None or right.get("construction_family") is None
            or left["construction_family"] == right["construction_family"])


def _ensure_scope_integrity(session) -> None:
    """Reject inconsistent state rather than choosing one of overlapping rules."""
    active = list(session.scalars(select(DesignRule).where(DesignRule.state == "approved")))
    for index, rule in enumerate(active):
        if rule.active_slot != scope_slot(rule.scope):
            raise DesignKnowledgeRefused("active knowledge scope is inconsistent")
        if any(scope_overlaps(rule.scope, previous.scope) for previous in active[:index]):
            raise DesignKnowledgeRefused("overlapping active knowledge scopes conflict")
    if any(scope_slot(rule.scope) != 1 for rule in active):
        guard = session.scalar(select(DesignRule).where(DesignRule.active_slot == 1))
        if guard is None or guard.state != "retired" or guard.key != _SCOPE_GUARD_KEY:
            raise DesignKnowledgeRefused("legacy rollback scope guard is unavailable")


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
        _ensure_scope_integrity(s)
        for pin in pins:
            rule = s.get(DesignRule, pin["rule_id"])
            if rule is None:
                raise DesignKnowledgeRefused("knowledge pin is not an approved rule version")
            expected_slot = scope_slot(rule.scope)
            if (rule is None or rule.state != "approved" or rule.version != pin["rule_version"]
                    or rule.active_slot != expected_slot or not rule.approved_at
                    or not isinstance(rule.approved_by, str) or not rule.approved_by.strip()
                    or not isinstance(rule.producer, str) or not rule.producer.strip()
                    or principal(rule.approved_by) == principal(rule.producer)
                    or rule_digest(rule) != pin["rule_digest"]):
                raise DesignKnowledgeRefused("knowledge pin is not an approved rule version")
            if (not isinstance(rule.statement, dict) or set(rule.statement) != {"rule", "parameters"}
                    or not isinstance(rule.statement.get("rule"), str)
                    or rule.statement.get("rule") not in RULES or rule.statement.get("parameters") != {}):
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
    for i, record in enumerate(verified):
        if any(scope_overlaps(record["scope"], other["scope"]) for other in verified[:i]):
            raise DesignKnowledgeRefused("overlapping knowledge scopes conflict")
    return verified


def applicable(db, scope: dict) -> list[dict]:
    """Read approved, evaluated rules for a scope; unavailable evidence means none apply."""
    scope_slot(scope)
    try:
        with db.session() as s:
            rows = list(s.scalars(select(DesignRule).where(DesignRule.state == "approved")))
            candidates = []
            for row in rows:
                if row.scope == scope or (row.scope == {"writer_section": "finishing"}
                                          and "construction_family" in scope):
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
        if len(result) > 1:
            raise DesignKnowledgeRefused("overlapping knowledge scopes conflict")
        return result
    except Exception:
        _log.exception("design knowledge unavailable; no rule applied")
        return []


def applicable_to_cir(db, cir) -> list[dict]:
    """Read the finishing rule for this CIR's actual construction family."""
    return applicable(db, {"writer_section": "finishing",
                           "construction_family": getattr(cir, "construction", None)})


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
    if any(not scope_matches(record["scope"], cir) for record in verified):
        raise DesignKnowledgeRefused("frozen directive is outside its approved scope")
    return verified


def freeze_pins(db, cir, pins: list[dict]):
    """Return a new CIR carrying only the verified closed-vocabulary directives."""
    import copy
    from ..cir import knowledge

    records = verify_pins(db, pins)
    if any(not scope_matches(record["scope"], cir) for record in records):
        raise DesignKnowledgeRefused("knowledge is outside its approved scope")
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


def repin_revalidated_cir(db, cir, pins: list[dict], *, new_version: str):
    """Copy a CIR to a newly approved evaluation of the same unchanged rules.

    This never changes an existing release, and is not authority to publish the
    copy. Its caller must recertify it through the ordinary production gates.
    """
    import copy
    from ..cir import knowledge
    from ..teardown.review import principal

    if (not isinstance(new_version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,19}",
                                                              new_version)
            or new_version == getattr(cir, "version", None)):
        raise DesignKnowledgeRefused("repinning requires a distinct release version")
    try:
        old = knowledge.markers(cir)
    except ValueError as exc:
        raise DesignKnowledgeRefused(str(exc)) from exc
    new = verify_pins(db, pins)
    if any(not scope_matches(record["scope"], cir) for record in new):
        raise DesignKnowledgeRefused("knowledge is outside its approved scope")
    if not old or len(old) != len(new):
        raise DesignKnowledgeRefused("old and new knowledge must match")
    with db.session() as s:
        from ..core.models import PatternVersion, Product
        existing = s.scalar(select(PatternVersion.id).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == new_version))
        if existing is not None:
            raise DesignKnowledgeRefused("repinning cannot replace an existing release version")
        for prior, current in zip(old, new):
            old_pin, new_pin = prior["pin"], current["pin"]
            if (prior["rule"] != current["statement"]["rule"]
                    or any(old_pin[k] != new_pin[k] for k in
                           ("rule_id", "rule_version", "rule_digest"))):
                raise DesignKnowledgeRefused("repinning cannot change a rule")
            rule = s.get(DesignRule, old_pin["rule_id"])
            if rule is None:
                raise DesignKnowledgeRefused("historical rule is unavailable")
            approvals = list(s.scalars(select(AuditLog).where(
                AuditLog.action == "design_knowledge.rule_approved",
                AuditLog.artifact == f"design-rule:{rule.id}").order_by(AuditLog.id.desc())))
            matching = [a for a in approvals if isinstance(a.detail, dict)
                and a.detail.get("rule_digest") == old_pin["rule_digest"]
                and a.detail.get("evaluation_digest") == old_pin["evaluation_digest"]]
            if not matching or not matching[0].actor \
                    or principal(matching[0].actor) == principal(rule.producer):
                raise DesignKnowledgeRefused("historical pin approval is unavailable")
            historical = _assert_evaluation(db, s, rule, matching[0].detail.get("evaluation_id"),
                check_current_corpus=False, check_current_implementation=False)
            if historical != old_pin["evaluation_digest"]:
                raise DesignKnowledgeRefused("historical pin evidence does not match")
    out = copy.deepcopy(cir)
    out.version = new_version
    untouched = tuple(item for item in out.provenance.primitives_used
                      if not (isinstance(item, str) and item.startswith(knowledge.PREFIX)))
    out.provenance.primitives_used = (*untouched, *(knowledge.marker(
        record["statement"]["rule"], record["pin"]) for record in new))
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
    supporting_products = set()
    supporting_hashes = set()
    supporting_sellers = set()
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
            supports_gap = (observations.get("fully_readable") is True
                and isinstance(dimensions, dict) and dimensions.get("finishing") == "absent")
            product = session.get(BenchmarkProduct, source.benchmark_id)
            if not manifested_pdf(product, source.file_sha256):
                raise DesignKnowledgeRefused("analysis source is no longer in the manifest")
            lic = session.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == product.ref))
            if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                    or "private_analysis" in (lic.prohibited_uses or []):
                raise DesignKnowledgeRefused("analysis licence no longer permits private use")
            if supports_gap:
                supporting_products.add(product.id)
                supporting_hashes.add(source.file_sha256)
                if isinstance(product.seller, str) and product.seller.strip():
                    supporting_sellers.add(product.seller.strip().casefold())
    if (isinstance(rule.statement, dict) and isinstance(rule.statement.get("rule"), str)
            and rule.statement.get("rule") in RULES
            and not supporting_products):
        raise DesignKnowledgeRefused("reviewed evidence does not support a finishing gap")
    if (isinstance(rule.statement, dict)
            and rule.statement.get("rule") == "include_checklist_and_end_check"
            and (len(supporting_products) < 2 or len(supporting_hashes) < 2
                 or len(supporting_sellers) < 2)):
        raise DesignKnowledgeRefused("end-check rule needs two distinct reviewed sellers and files")


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


def _assert_evaluation(db, session, rule, evaluation_id: int, *, seen=None,
                       check_current_corpus: bool = True,
                       check_current_implementation: bool = True) -> str:
    from ..quality import design_eval
    from ..core.models import DesignEvaluationRun
    from ..teardown.review import principal

    if type(evaluation_id) is not int or evaluation_id <= 0:
        raise DesignKnowledgeRefused("completed evaluation is required")
    seen = set() if seen is None else set(seen)
    identity = (rule.id, evaluation_id)
    if identity in seen:
        raise DesignKnowledgeRefused("cyclic knowledge history")
    seen.add(identity)
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
            and report.get("rule_name") == rule.statement.get("rule")
            and report.get("scope", {"writer_section": "finishing"}) == rule.scope
            and report.get("rule_sha256") == rule_digest(rule)
            and report.get("lineage_sha256") == lineage_digest(session, rule)
            and isinstance(report.get("implementation_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", report["implementation_sha256"]) is not None
            and isinstance(report.get("corpus_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", report["corpus_sha256"]) is not None
            and (not check_current_implementation or report.get("implementation_sha256")
                 == design_eval.implementation_digest(db))
            and (not check_current_corpus or report.get("corpus_sha256") == design_eval.corpus_digest(db))
            and report.get("case_set_sha256") == design_eval.load_cases(db=db)["sha256"]
            and design_eval.classify_evaluation(report) == "passed")
    except design_eval.DesignEvaluationRefused as exc:
        raise DesignKnowledgeRefused("evaluation evidence is unavailable") from exc
    if not valid:
        raise DesignKnowledgeRefused("evaluation is incomplete, stale or regressed")
    if report.get("mode") == "revalidation":
        from ..quality import design_revalidation

        previous = session.get(AuditLog, report.get("previous_approval_id"))
        latest = session.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule.id}", AuditLog.id < audit.id)
            .order_by(AuditLog.id.desc()))
        detail = previous.detail if previous is not None and isinstance(previous.detail, dict) else {}
        if (previous is None or latest is None or previous.id != latest.id
                or not previous.actor or principal(previous.actor) == principal(rule.producer)
                or detail.get("rule_digest") != rule_digest(rule)):
            raise DesignKnowledgeRefused("historical approval is unavailable")
        prior_digest = _assert_evaluation(db, session, rule, detail.get("evaluation_id"),
            seen=seen, check_current_corpus=False, check_current_implementation=False)
        historical = session.get(AuditLog, detail.get("evaluation_id"))
        if (detail.get("evaluation_digest") != prior_digest
                or report.get("previous_evaluation_digest") != prior_digest
                or not design_revalidation.no_historical_regression(historical.detail, report)):
            raise DesignKnowledgeRefused("revalidation regressed or history changed")
    prior_pins = report.get("incumbent_pins")
    if not isinstance(prior_pins, list) or len(prior_pins) > 1:
        raise DesignKnowledgeRefused("evaluation incumbent is invalid")
    if prior_pins:
        pin = prior_pins[0]
        if not isinstance(pin, dict) or set(pin) != {
                "rule_id", "rule_version", "rule_digest", "evaluation_digest"} \
                or pin.get("rule_id") != rule.supersedes:
            raise DesignKnowledgeRefused("evaluation incumbent does not match the successor")
        prior = session.get(DesignRule, pin["rule_id"])
        if (prior is None or prior.state not in ("approved", "retired") or prior.scope != rule.scope
                or prior.version != pin["rule_version"] or rule_digest(prior) != pin["rule_digest"]
                or not isinstance(prior.approved_by, str) or not prior.approved_by.strip()
                or not isinstance(prior.producer, str) or not prior.producer.strip()
                or not prior.approved_at
                or principal(prior.approved_by) == principal(prior.producer)):
            raise DesignKnowledgeRefused("incumbent history is invalid")
        approval = session.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{prior.id}", AuditLog.actor == prior.approved_by)
            .order_by(AuditLog.id.desc()))
        detail = approval.detail if approval is not None and isinstance(approval.detail, dict) else {}
        if detail.get("rule_digest") != pin["rule_digest"] \
                or detail.get("evaluation_digest") != pin["evaluation_digest"]:
            raise DesignKnowledgeRefused("incumbent approval is unavailable")
        _revalidate_provenance(session, prior)
        if _assert_evaluation(db, session, prior, detail.get("evaluation_id"), seen=seen,
                              check_current_corpus=False,
                              check_current_implementation=(check_current_implementation
                                  and report.get("mode") != "revalidation")) \
                != pin["evaluation_digest"]:
            raise DesignKnowledgeRefused("incumbent evaluation does not match")
    return design_eval._digest(report)


def incumbent_for_evaluation(db, scope: dict | None = None) -> list[dict]:
    """Authenticate a historical incumbent for a fresh private comparison only.

    A new reference changes the corpus and immediately blocks production use of
    the old pin. The evaluator may still compare its prior approved behavior
    against that new corpus; this function does not authorize production use.
    """
    from ..teardown.review import principal

    scope = scope or {"writer_section": "finishing"}
    slot = scope_slot(scope)
    with db.session() as s:
        _ensure_scope_integrity(s)
        rules = [r for r in s.scalars(select(DesignRule).where(DesignRule.state == "approved"))
                 if r.scope == scope]
        if not rules:
            return []
        if len(rules) != 1:
            raise DesignKnowledgeRefused("incumbent knowledge set is unsupported")
        rule = rules[0]
        if (rule.active_slot != slot or not isinstance(rule.approved_by, str)
                or not rule.approved_by.strip() or not isinstance(rule.producer, str)
                or not rule.producer.strip() or not rule.approved_at
                or principal(rule.approved_by) == principal(rule.producer)):
            raise DesignKnowledgeRefused("incumbent approval is invalid")
        approval = s.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule.id}", AuditLog.actor == rule.approved_by)
            .order_by(AuditLog.id.desc()))
        detail = approval.detail if approval is not None and isinstance(approval.detail, dict) else {}
        digest = rule_digest(rule)
        if detail.get("rule_digest") != digest:
            raise DesignKnowledgeRefused("incumbent approval is unavailable")
        _revalidate_provenance(s, rule)
        evaluated = _assert_evaluation(db, s, rule, detail.get("evaluation_id"),
                                       check_current_corpus=False)
        if detail.get("evaluation_digest") != evaluated:
            raise DesignKnowledgeRefused("incumbent evaluation is invalid")
        return [{"pin": {"rule_id": rule.id, "rule_version": rule.version,
                         "rule_digest": digest, "evaluation_digest": evaluated},
                 "statement": dict(rule.statement), "scope": dict(rule.scope)}]


def propose(db, *, key: str, statement: dict, scope: dict, provenance: list,
            producer: str, supersedes: int | None = None) -> dict:
    """Persist a proposal; its evidence must already exist in the learning system."""
    if not isinstance(key, str) or not _TOKEN.fullmatch(key) or key == _SCOPE_GUARD_KEY:
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
    scope_slot(scope)
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
                if not manifested_pdf(product, source.file_sha256):
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
        if supersedes is not None and (previous is None or previous.key != key
                                       or previous.scope != scope):
            raise DesignKnowledgeRefused("superseded version must belong to this rule")
        version = (session.scalar(select(func.max(DesignRule.version))
                                  .where(DesignRule.key == key)) or 0) + 1
        row = DesignRule(key=key, version=version, statement=dict(statement), scope=dict(scope),
                         provenance=evidence, producer=producer.strip(), state="proposed",
                         supersedes=supersedes)
        session.add(row)
        session.flush()
        return {"id": row.id, "key": row.key, "version": row.version, "state": row.state}


def propose_from_analysis(db, analysis_id: int, *, construction_family: str | None = None) -> dict:
    """Propose a bounded rule for a reviewed, fully read missing section.

    This records a hypothesis, not evidence of improved quality. The proposal is
    idempotent per source; approval must still require a held-out evaluation.
    """
    from sqlalchemy.exc import IntegrityError

    if type(analysis_id) is not int or analysis_id <= 0:
        raise DesignKnowledgeRefused("invalid analysis")
    scope = {"writer_section": "finishing"}
    if construction_family is not None:
        scope["construction_family"] = construction_family
    slot = scope_slot(scope)
    key = f"finishing_from_analysis_{analysis_id}"
    if construction_family is not None:
        key += f"_{construction_family}"
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
            existing = s.scalar(select(DesignRule).where(DesignRule.key == key)
                                .order_by(DesignRule.version.desc()))
            if existing is not None:
                return {"proposed": False, "reason": "already_proposed", "id": existing.id}
            product = s.scalar(select(BenchmarkProduct).where(
                BenchmarkProduct.id == source.benchmark_id).with_for_update())
            if not manifested_pdf(product, source.file_sha256):
                raise DesignKnowledgeRefused("analysis source is no longer in the manifest")
            lic = s.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == product.ref).with_for_update())
            if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                    or "private_analysis" in (lic.prohibited_uses or []):
                raise DesignKnowledgeRefused("analysis licence no longer permits private use")
            current = list(s.scalars(select(DesignRule).where(
                DesignRule.state == "approved").with_for_update()))
            if any(item.scope != scope and scope_overlaps(item.scope, scope) for item in current):
                return {"proposed": False, "reason": "scope_conflict"}
            active = next((item for item in current if item.active_slot == slot), None)
            if active is not None:
                if active.statement != {"rule": "include_finishing_checklist", "parameters": {}}:
                    return {"proposed": False, "reason": "no_new_rule"}
                _revalidate_provenance(s, active)
                roots = [item for item in active.provenance if item.get("kind") == "analysis"]
                sources = [s.get(BenchmarkAnalysis, item["id"]) for item in roots]
                source_products = {item.benchmark_id for item in sources}
                source_hashes = {item.file_sha256 for item in sources}
                prior_products = [s.get(BenchmarkProduct, ident) for ident in source_products]
                source_sellers = {item.seller.strip().casefold() for item in prior_products
                                  if item is not None and isinstance(item.seller, str)
                                  and item.seller.strip()}
                if (product.id in source_products or source.file_sha256 in source_hashes
                        or not isinstance(product.seller, str) or not product.seller.strip()
                        or product.seller.strip().casefold() in source_sellers):
                    return {"proposed": False, "reason": "source_not_independent"}
                key = active.key
                existing = s.scalar(select(DesignRule).where(DesignRule.supersedes == active.id,
                    DesignRule.state == "proposed").order_by(DesignRule.version.desc()))
                if existing is not None:
                    return {"proposed": False, "reason": "already_proposed", "id": existing.id}
                version = (s.scalar(select(func.max(DesignRule.version)).where(
                    DesignRule.key == key)) or 0) + 1
                row = DesignRule(key=key, version=version, statement={
                    "rule": "include_checklist_and_end_check", "parameters": {}},
                    scope=scope,
                    provenance=[*active.provenance, {"kind": "analysis", "id": analysis_id}],
                    producer="teardown_analyst", state="proposed", supersedes=active.id)
            else:
                row = DesignRule(key=key, version=1, statement={"rule": "include_finishing_checklist",
                                 "parameters": {}}, scope=scope,
                    provenance=[{"kind": "analysis", "id": analysis_id}],
                    producer="teardown_analyst", state="proposed")
            s.add(row)
            s.flush()
            return {"proposed": True, "id": row.id, "key": key, "version": row.version,
                    "state": "proposed"}
    except IntegrityError:
        with db.session() as s:
            existing = s.scalar(select(DesignRule).where(DesignRule.key == key)
                                .order_by(DesignRule.version.desc()))
            if existing is None:
                raise
            return {"proposed": False, "reason": "already_proposed", "id": existing.id}


def _lock_scope_for_approval(session, scope: dict) -> int:
    """Serialize scope changes and reserve legacy slot 1 while scoped rules exist.

    The non-approved guard makes an older single-slot binary fail closed instead
    of approving a global rule over scoped rules during a rolling rollback.
    """
    from sqlalchemy.exc import IntegrityError

    slot = scope_slot(scope)
    first = session.scalar(select(DesignRule).where(DesignRule.active_slot == 1).with_for_update())
    if slot == 1 and first is not None and first.state == "retired":
        if first.key != _SCOPE_GUARD_KEY:
            raise DesignKnowledgeRefused("scope guard is invalid")
        session.execute(update(DesignRule).where(DesignRule.id == first.id)
                        .values(version=DesignRule.version))
        if session.scalar(select(DesignRule.id).where(
                DesignRule.state == "approved", DesignRule.active_slot.in_((2, 3, 4))).limit(1)):
            raise DesignKnowledgeRefused("global scope conflicts with active scoped knowledge")
        session.delete(first)
        session.flush()
    elif slot != 1:
        if first is not None and (first.state != "retired" or first.key != _SCOPE_GUARD_KEY):
            raise DesignKnowledgeRefused("scoped knowledge conflicts with global scope")
        if first is None:
            first = DesignRule(key=_SCOPE_GUARD_KEY, version=1, statement={}, scope={},
                               provenance=[], producer="scope_guard", state="retired", active_slot=1)
            session.add(first)
            try:
                session.flush()
            except IntegrityError as exc:
                raise DesignKnowledgeRefused("knowledge scopes changed concurrently") from exc
        session.execute(update(DesignRule).where(DesignRule.id == first.id)
                        .values(version=DesignRule.version))
    elif first is not None:
        session.execute(update(DesignRule).where(DesignRule.id == first.id)
                        .values(version=DesignRule.version))
    return slot


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
    if decision not in ("approve", "reject", "retire", "reapprove"):
        raise DesignKnowledgeRefused("decision must be approve, reject, retire or reapprove")
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
        slot = scope_slot(rule.scope)
        if decision == "reapprove":
            if rule.state != "approved" or rule.active_slot != slot:
                raise DesignKnowledgeRefused("an active rule is required")
            _ensure_scope_integrity(s)
            digest = _assert_evaluation(db, s, rule, evaluation_id)
            evidence = s.get(AuditLog, evaluation_id)
            latest = s.scalar(select(AuditLog).where(
                AuditLog.action == "design_knowledge.rule_approved",
                AuditLog.artifact == f"design-rule:{rule.id}").order_by(AuditLog.id.desc()))
            if (evidence.detail.get("mode") != "revalidation" or latest is None
                    or evidence.detail.get("previous_approval_id") != latest.id):
                raise DesignKnowledgeRefused("current revalidation evidence is required")
            updated = s.execute(update(DesignRule).where(DesignRule.id == rule_id,
                DesignRule.state == "approved", DesignRule.active_slot == slot,
                DesignRule.approved_by == rule.approved_by,
                DesignRule.approved_at == rule.approved_at).values(
                    approved_by=reviewer, approved_at=utcnow()))
            if updated.rowcount != 1:
                raise DesignKnowledgeRefused("rule changed during reapproval")
            rule_sha = rule_digest(rule)
            s.add(AuditLog(actor=reviewer, action="design_knowledge.rule_approved",
                artifact=f"design-rule:{rule_id}", detail={"rule_digest": rule_sha,
                    "evaluation_id": evaluation_id, "evaluation_digest": digest,
                    "reason": reason.strip(), "revalidation_of": latest.id}))
            return {"rule_id": rule_id, "state": "approved", "decision": "reapproved",
                    "pin": {"rule_id": rule_id, "rule_version": rule.version,
                            "rule_digest": rule_sha, "evaluation_digest": digest}}
        if decision == "retire":
            if rule.state != "approved" or rule.active_slot != slot:
                raise DesignKnowledgeRefused("an active rule is required")
            changed = s.execute(update(DesignRule).where(
                DesignRule.id == rule_id, DesignRule.state == "approved",
                DesignRule.active_slot == slot).values(state="retired", active_slot=None))
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
            evaluation = s.get(AuditLog, evaluation_id)
            incumbent_pins = evaluation.detail["incumbent_pins"]
            _ensure_scope_integrity(s)
            _lock_scope_for_approval(s, rule.scope)
            _ensure_scope_integrity(s)
            active = s.scalar(select(DesignRule).where(
                DesignRule.active_slot == slot, DesignRule.state == "approved").with_for_update())
            if active is None:
                if incumbent_pins:
                    raise DesignKnowledgeRefused("evaluated incumbent is no longer active")
            else:
                if (len(incumbent_pins) != 1 or incumbent_pins[0].get("rule_id") != active.id
                        or rule.supersedes != active.id or rule.key != active.key):
                    raise DesignKnowledgeRefused("candidate does not replace the evaluated incumbent")
                historical = incumbent_for_evaluation(db, rule.scope)
                if [record["pin"] for record in historical] != incumbent_pins:
                    raise DesignKnowledgeRefused("incumbent changed since evaluation")
                retired = s.execute(update(DesignRule).where(
                    DesignRule.id == active.id, DesignRule.state == "approved",
                    DesignRule.active_slot == slot).values(state="retired", active_slot=None))
                if retired.rowcount != 1:
                    raise DesignKnowledgeRefused("incumbent changed during approval")
                s.add(AuditLog(actor=reviewer, action="design_knowledge.rule_superseded",
                               artifact=f"design-rule:{active.id}", detail={
                                   "successor_id": rule.id, "reason": reason.strip()}))
            stamp = utcnow()
            digest = rule_digest(rule)
            try:
                changed = s.execute(update(DesignRule).where(
                    DesignRule.id == rule_id, DesignRule.state == "proposed",
                    DesignRule.producer == rule.producer).values(
                        state="approved", approved_by=reviewer, approved_at=stamp, active_slot=slot))
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
