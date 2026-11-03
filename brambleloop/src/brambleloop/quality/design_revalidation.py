"""Re-evaluate an existing approval without authorizing its production use.

The historical audit is authenticated but is never treated as current. The
same rule is measured again against its original held-out baseline, under the
current implementation and originality corpus; every historical quality
metric must also be preserved. Only a separate owner action can approve it.
"""
from __future__ import annotations

from collections import Counter
import copy

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.models import AuditLog, DesignEvaluationRun, DesignRule
from ..improve import design_knowledge as knowledge
from . import design_eval as ev


_INCREASE_IS_BAD = ("compile_errors", "twin_failures", "reverse_findings", "policy_findings",
                    "truth_findings", "originality_escalations", "originality_unmeasured")
_DECREASE_IS_BAD = ("finishing_actions_expected", "finishing_actions_present",
                    "finishing_actions_listed", "end_check_present")
_CODES = ("reverse_codes", "policy_codes", "truth_codes", "originality_escalation_keys")


def no_historical_regression(previous: dict, current: dict) -> bool:
    """Compare actual held-out outcomes, never treating missing data as success."""
    try:
        if (ev.classify_evaluation(previous) != "passed" or ev.classify_evaluation(current) != "passed"
                or previous.get("scope", {"writer_section": "finishing"}) !=
                   current.get("scope", {"writer_section": "finishing"})
                or any(previous[k] != current[k] for k in
                       ("rule_id", "rule_key", "rule_version", "rule_sha256", "rule_name",
                        "case_set_sha256", "incumbent_pins"))):
            return False
        before = {c["case"]: c["after"] for c in previous["cases"]}
        after = {c["case"]: c["after"] for c in current["cases"]}
        if len(before) != len(previous["cases"]) or set(before) != set(after):
            return False
        for case, old in before.items():
            new = after[case]
            for metric in _INCREASE_IS_BAD + _DECREASE_IS_BAD:
                if type(old[metric]) is not int or type(new[metric]) is not int:
                    return False
                if metric in _INCREASE_IS_BAD and new[metric] > old[metric]:
                    return False
                if metric in _DECREASE_IS_BAD and new[metric] < old[metric]:
                    return False
            for metric in _CODES:
                if not isinstance(old[metric], list) or not isinstance(new[metric], list):
                    return False
                if Counter(new[metric]) - Counter(old[metric]):
                    return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _history(db, rule_id: int) -> dict:
    """Authenticate prior approval solely as historical evidence, not as a live pin."""
    from ..teardown.review import principal

    if type(rule_id) is not int or rule_id <= 0:
        raise ev.DesignEvaluationRefused("invalid rule id")
    with db.session() as s:
        knowledge._ensure_scope_integrity(s)
        rule = s.get(DesignRule, rule_id)
        if (rule is None or rule.state != "approved" or rule.active_slot != knowledge.scope_slot(rule.scope)
                or not rule.approved_at or not rule.approved_by or not rule.producer
                or principal(rule.approved_by) == principal(rule.producer)):
            raise ev.DesignEvaluationRefused("an independently approved active rule is required")
        approval = s.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule.id}", AuditLog.actor == rule.approved_by)
            .order_by(AuditLog.id.desc()))
        detail = approval.detail if approval is not None and isinstance(approval.detail, dict) else {}
        if detail.get("rule_digest") != knowledge.rule_digest(rule):
            raise ev.DesignEvaluationRefused("historical approval is unavailable")
        try:
            digest = knowledge._assert_evaluation(db, s, rule, detail.get("evaluation_id"),
                check_current_corpus=False, check_current_implementation=False)
        except knowledge.DesignKnowledgeRefused as exc:
            raise ev.DesignEvaluationRefused("historical evidence is unavailable") from exc
        if detail.get("evaluation_digest") != digest:
            raise ev.DesignEvaluationRefused("historical evaluation digest differs")
        previous = s.get(AuditLog, detail["evaluation_id"])
        prior_pins = copy.deepcopy(previous.detail["incumbent_pins"])
        baseline = None
        if prior_pins:
            prior = s.get(DesignRule, prior_pins[0]["rule_id"])
            if prior is None:
                raise ev.DesignEvaluationRefused("historical baseline is unavailable")
            baseline = prior.statement["rule"]
        return {"approval_id": approval.id, "evaluation_digest": digest,
                "previous": copy.deepcopy(previous.detail), "baseline_pins": prior_pins,
                "baseline_rule": baseline, "rule_digest": knowledge.rule_digest(rule),
                "rule_name": rule.statement["rule"], "key": rule.key, "version": rule.version,
                "scope": copy.deepcopy(rule.scope)}


def evaluation_key(db, rule_id: int) -> str:
    history = _history(db, rule_id)
    with db.session() as s:
        lineage = knowledge.lineage_digest(s, s.get(DesignRule, rule_id))
    identity = {"rule": history["rule_digest"], "approval": history["approval_id"],
                "previous": history["evaluation_digest"], "lineage": lineage,
                "cases": ev.load_cases(db=db)["sha256"], "implementation": ev.implementation_digest(db),
                "corpus": ev.corpus_digest(db)}
    return f"design-reval:{rule_id}:{ev._digest(identity)}"


def evaluate(db, rule_id: int, *, expected_key: str | None = None) -> dict:
    """Record current evidence; this function never changes the approval."""
    from ..cir import knowledge as cir_knowledge
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..products import launch0

    key = evaluation_key(db, rule_id)
    if expected_key is not None and expected_key != key:
        raise ev.StaleEvaluation("revalidation inputs changed before execution")
    with db.session() as s:
        prior_run = s.scalar(select(DesignEvaluationRun).where(DesignEvaluationRun.run_key == key))
        if prior_run is not None:
            audit = s.get(AuditLog, prior_run.audit_id)
            if (audit is None or audit.action != "design_eval.completed"
                    or audit.actor != "design_evaluator"
                    or audit.artifact != f"design-rule:{rule_id}"
                    or not isinstance(audit.detail, dict)
                    or audit.detail.get("mode") != "revalidation"
                    or audit.detail.get("run_key") != key or prior_run.rule_id != rule_id):
                raise ev.DesignEvaluationRefused("revalidation audit is missing")
            return {**audit.detail, "audit_id": audit.id, "created": False}
    history = _history(db, rule_id)
    frozen = ev.load_cases(db=db)
    implementation, corpus = ev.implementation_digest(db), ev.corpus_digest(db)
    with db.session() as s:
        lineage = knowledge.lineage_digest(s, s.get(DesignRule, rule_id))
    cases = []
    for case in frozen["cases"]:
        if case["kind"] != "launch0":
            continue
        cir = launch0.cir_for(case["build"])
        matches_scope = knowledge.scope_matches(history["scope"], cir)
        if cir.provenance is None:
            raise ev.DesignEvaluationRefused("held-out CIR has no provenance")
        baseline_cir = copy.deepcopy(cir)
        if history["baseline_pins"] and matches_scope:
            baseline_cir.provenance.primitives_used += (cir_knowledge.marker(
                history["baseline_rule"], history["baseline_pins"][0]),)
        baseline = write_pattern(baseline_cir, compile_cir(baseline_cir))
        candidate_cir = copy.deepcopy(cir)
        pin = {"rule_id": rule_id, "rule_version": history["version"],
               "rule_digest": history["rule_digest"], "evaluation_digest": history["evaluation_digest"]}
        if matches_scope:
            candidate_cir.provenance.primitives_used += (cir_knowledge.marker(history["rule_name"], pin),)
        candidate = write_pattern(candidate_cir, compile_cir(candidate_cir))
        expected = ev._preview_checklist(baseline, rule_name=history["rule_name"]) if matches_scope else baseline
        if candidate != expected:
            raise ev.DesignEvaluationRefused("candidate writer differs from the registered rule")
        cases.append({"case": case["id"], **ev.compare_written_case(cir, baseline, candidate, db=db)})
    report = {"mode": "revalidation", "rule_id": rule_id, "rule_key": history["key"],
              "rule_version": history["version"], "rule_sha256": history["rule_digest"],
              "rule_name": history["rule_name"], "case_set_sha256": frozen["sha256"],
              "scope": history["scope"],
              "out_of_scope_controls": "unmodified_no_knowledge",
              "incumbent_pins": history["baseline_pins"], "cases": cases,
              "benchmark_checks": ev._benchmark_checks(db), "implementation_sha256": implementation,
              "corpus_sha256": corpus, "lineage_sha256": lineage, "run_key": key,
              "previous_approval_id": history["approval_id"],
              "previous_evaluation_digest": history["evaluation_digest"]}
    report["state"] = ev.classify_evaluation(report)
    if report["state"] == "passed" and not no_historical_regression(history["previous"], report):
        report["state"] = "regression"
    report["approval_evidence_complete"] = report["state"] == "passed"
    if evaluation_key(db, rule_id) != key:
        raise ev.StaleEvaluation("revalidation inputs changed during measurement")
    try:
        with db.session() as s:
            active = s.scalar(select(DesignRule).where(DesignRule.id == rule_id).with_for_update())
            approval = s.scalar(select(AuditLog).where(AuditLog.action == "design_knowledge.rule_approved",
                AuditLog.artifact == f"design-rule:{rule_id}").order_by(AuditLog.id.desc()))
            if (active is None or active.state != "approved"
                    or active.active_slot != knowledge.scope_slot(active.scope)
                    or knowledge.rule_digest(active) != history["rule_digest"]
                    or approval is None or approval.id != history["approval_id"]):
                raise ev.StaleEvaluation("approval changed during revalidation")
            audit = AuditLog(actor="design_evaluator", action="design_eval.completed",
                             artifact=f"design-rule:{rule_id}", detail=report)
            s.add(audit)
            s.flush()
            s.add(DesignEvaluationRun(run_key=key, rule_id=rule_id, audit_id=audit.id))
            s.flush()
            return {**report, "audit_id": audit.id, "created": True}
    except IntegrityError:
        with db.session() as s:
            prior = s.scalar(select(DesignEvaluationRun).where(DesignEvaluationRun.run_key == key))
            if prior is None:
                raise
            audit = s.get(AuditLog, prior.audit_id)
            if (audit is None or audit.action != "design_eval.completed"
                    or audit.actor != "design_evaluator"
                    or audit.artifact != f"design-rule:{rule_id}"
                    or not isinstance(audit.detail, dict)
                    or audit.detail.get("mode") != "revalidation"
                    or audit.detail.get("run_key") != key or prior.rule_id != rule_id):
                raise ev.DesignEvaluationRefused("revalidation audit is missing")
            return {**audit.detail, "audit_id": audit.id, "created": False}
