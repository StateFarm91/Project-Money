"""Fixed evidence set for deterministic design-knowledge evaluation.

The case identities and hashes are frozen independently of any challenger.
Only hashes and closed-vocabulary identifiers leave this module; benchmark
instructions or source text are never copied into an evaluation record.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from pathlib import Path

from ..cir import benchmarks
from ..products import launch0
from . import stitch_benchmarks

_LAUNCH_CASES = (
    ("hexagonal-bread-basket", "basket_small"),
    ("cloudline-baby-blanket", "cloudline_blanket"),
    ("hexagon-coaster-set", "hexagon_coasters"),
    ("nordic-star-ornaments", "snowflake_ornaments"),
    ("winter-village-graphghan", "snowfall_throw"),
    ("nordic-forest-mosaic-throw-baby", "nordic_forest_baby"),
    ("mosaic-placemat-pair", "placemat_pair"),
    ("housewarming-key-basket", "key_basket"),
)
_MANIFEST = Path(__file__).with_name("design_eval_cases.json")
_BENCH2 = Path(__file__).resolve().parents[3] / "research" / "bench2" / "out" / "product_truth.json"


class DesignEvaluationRefused(ValueError):
    """The fixed held-out set is unavailable, altered, or challenger-supplied."""


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def materialize_cases() -> list[dict]:
    """Build the fixed case identities from current source, without returning source text."""
    cases = []
    for slug, build_key in _LAUNCH_CASES:
        candidate = launch0.candidate(slug)
        cir = launch0.cir_for(build_key)
        cases.append({"kind": "launch0", "id": slug, "build": build_key,
                      "cir_sha256": _digest(cir.to_dict()),
                      "brief_sha256": _digest(dataclasses.asdict(candidate))})
    cases.append({"kind": "benchmark_truth", "id": "bench1_xs",
                  "cir_sha256": _digest(benchmarks.cardigan("XS").to_dict()),
                  "truth_sha256": _digest(benchmarks.reconcile("XS"))})
    if not _BENCH2.is_file():
        raise DesignEvaluationRefused("bench2 Product Truth is unavailable")
    cases.append({"kind": "benchmark_truth", "id": "bench2",
                  "truth_sha256": hashlib.sha256(_BENCH2.read_bytes()).hexdigest()})
    for name, fn in sorted(stitch_benchmarks.FAMILIES.items()):
        cases.append({"kind": "stitch_family", "id": name,
                      "validator_sha256": hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()})
    return cases


def load_cases(*, challenger_cases=None) -> dict:
    """Return only the pinned shared set; a challenger cannot supply its own cases."""
    if challenger_cases is not None:
        raise DesignEvaluationRefused("a challenger may not supply evaluation cases")
    if not _MANIFEST.is_file():
        raise DesignEvaluationRefused("held-out case manifest is unavailable")
    try:
        frozen = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        live = materialize_cases()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DesignEvaluationRefused("held-out cases cannot be read") from exc
    if not isinstance(frozen, dict):
        raise DesignEvaluationRefused("held-out case manifest is invalid")
    if frozen.get("cases") != live or frozen.get("sha256") != _digest(live):
        raise DesignEvaluationRefused("held-out cases differ from the frozen manifest")
    return {"cases": live, "sha256": frozen["sha256"]}


def measure_written_case(cir, text: str, *, db=None) -> dict:
    """Measure actual output without storing the output or reference instructions.

    This is a diagnostic, not a release certificate or an approval decision. In
    particular it cannot establish similarity against an unavailable library.
    """
    from ..cir.compiler import compile_cir
    from ..cir.reverse import compare
    from ..cir.twin import build_twin
    from ..cir.writer import FINISHING_HEADING, finishing_lines
    from ..gates.asset_truth import check_technique_claims
    from ..gates.originality import similarity_review
    from ..gates.policy import check_text

    compiled = compile_cir(cir)
    expected = finishing_lines(cir, result=compiled)[1:]
    lines = text.splitlines()
    try:
        section = lines[lines.index(FINISHING_HEADING) + 1:]
    except ValueError:
        section = []
    # Count independently generated complete actions, not merely a heading.
    normalized = {line.removeprefix('- ').strip() for line in section}
    twin_failures = 0
    truth_findings = 0
    for component in cir.components:
        try:
            twin = build_twin(cir, compiled, component=component.name)
            truth_findings += len(check_technique_claims(text, cir, twin, "pattern"))
        except (ValueError, KeyError):
            twin_failures += 1
    similarity = similarity_review(cir, pattern_text=text, db=db) if db is not None else None
    return {"compile_errors": len(compiled.errors), "twin_failures": twin_failures,
            "reverse_findings": len(compare(cir, text)),
            "policy_findings": len(check_text(text, "pattern")),
            "truth_findings": truth_findings if not twin_failures else None,
            "originality_escalations": len(similarity["escalated"]) if similarity else None,
            "originality_unmeasured": len(similarity["unmeasured"]) if similarity else None,
            "finishing_actions_expected": len(expected),
            "finishing_actions_present": sum(line in normalized for line in expected),
            "finishing_actions_listed": sum(('- ' + line) in section for line in expected)}


def compare_written_case(cir, baseline: str, candidate: str, *, db=None) -> dict:
    """Compare two actual renderings, exposing regressions without persisting text."""
    from ..gates.originality import shingles

    before = measure_written_case(cir, baseline, db=db)
    after = measure_written_case(cir, candidate, db=db)
    regressions = [key for key in ("compile_errors", "twin_failures", "reverse_findings",
                                  "policy_findings", "truth_findings", "originality_escalations")
                   if before[key] is not None and after[key] is not None
                   and after[key] > before[key]]
    if before["truth_findings"] is not None and after["truth_findings"] is None:
        regressions.append("truth_unmeasured")
    if before["originality_unmeasured"] is not None and after["originality_unmeasured"] is not None \
            and after["originality_unmeasured"] > before["originality_unmeasured"]:
        regressions.append("originality_unmeasured")
    if after["finishing_actions_present"] < before["finishing_actions_present"]:
        regressions.append("finishing_actions_present")
    # The shingles are not a substitute for a comparison with purchased sources.
    # They do detect changed word sequences for this formatting-only experiment.
    same_shingles = shingles(baseline) == shingles(candidate)
    if not same_shingles:
        regressions.append("word_shingles_changed")
    return {"before": before, "after": after, "regressions": regressions,
            "same_word_shingles": same_shingles,
            "approval_evidence_complete": False,
            "incomplete_reason": "full benchmark and Product Truth evaluation is incomplete"}


def preview_registered_rule(db, rule_id: int) -> dict:
    """Measure a registered proposal against the frozen launch cases.

    This preview deliberately cannot approve a rule: the production writer and
    the complete benchmark/originality stages must first be bound to the same
    evaluated implementation. No customer or reference instructions are saved.
    """
    from sqlalchemy import select

    from ..cir.compiler import compile_cir
    from ..cir.writer import FINISHING_HEADING, write_pattern
    from ..core.models import AuditLog, DesignRule
    from ..improve.design_knowledge import _TOKEN

    if type(rule_id) is not int or rule_id <= 0:
        raise DesignEvaluationRefused("invalid rule id")
    frozen = load_cases()
    with db.session() as s:
        rule = s.get(DesignRule, rule_id)
        if rule is None or rule.state != "proposed":
            raise DesignEvaluationRefused("a proposed rule is required")
        if not isinstance(rule.key, str) or not _TOKEN.fullmatch(rule.key):
            raise DesignEvaluationRefused("invalid rule key")
        if rule.statement != {"rule": "include_finishing_checklist", "parameters": {}} \
                or rule.scope != {"writer_section": "finishing"}:
            raise DesignEvaluationRefused("unsupported rule or scope")
        if s.scalar(select(DesignRule.id).where(DesignRule.state == "approved")) is not None:
            raise DesignEvaluationRefused("incumbent knowledge is not yet supported")
        identity = {"id": rule.id, "key": rule.key, "version": rule.version,
                    "statement": rule.statement, "scope": rule.scope,
                    "provenance": rule.provenance, "producer": rule.producer}
    case_results = []
    for case in frozen["cases"]:
        if case["kind"] != "launch0":
            continue
        cir = launch0.cir_for(case["build"])
        baseline = write_pattern(cir, compile_cir(cir))
        head, separator, finishing = baseline.partition(FINISHING_HEADING)
        if not separator:
            raise DesignEvaluationRefused("writer did not produce a finishing section")
        candidate = head + separator + "\n" + "\n".join(
            "- " + line if line else line for line in finishing.strip().splitlines()) + "\n"
        case_results.append({"case": case["id"], **compare_written_case(cir, baseline, candidate,
                                                                          db=db)})
    if len(case_results) != len(_LAUNCH_CASES):
        raise DesignEvaluationRefused("not all frozen launch cases were measured")
    report = {"rule_id": rule_id, "rule_key": identity["key"],
              "rule_version": identity["version"], "rule_sha256": _digest(identity),
              "case_set_sha256": frozen["sha256"], "cases": case_results,
              "state": "insufficient_evidence", "approval_evidence_complete": False,
              "why": "preview renderer is not the production writer; benchmark and full "
                     "Product Truth evidence is incomplete"}
    with db.session() as s:
        current = s.scalar(select(DesignRule).where(DesignRule.id == rule_id).with_for_update())
        if current is None or current.state != "proposed" or _digest({
                "id": current.id, "key": current.key, "version": current.version,
                "statement": current.statement, "scope": current.scope,
                "provenance": current.provenance, "producer": current.producer}) != report["rule_sha256"]:
            raise DesignEvaluationRefused("proposal changed during evaluation")
        row = AuditLog(actor="design_evaluator", action="design_eval.preview",
                       artifact=f"design-rule:{rule_id}", detail=report)
        s.add(row)
        s.flush()
        report = {**report, "audit_id": row.id}
    return report
