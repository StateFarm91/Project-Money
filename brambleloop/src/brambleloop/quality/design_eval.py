"""Fixed evidence set for deterministic design-knowledge evaluation.

The case identities and hashes are frozen independently of any challenger.
Only hashes and closed-vocabulary identifiers leave this module; benchmark
instructions or source text are never copied into an evaluation record.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
import ast
import hashlib
import inspect
import json
import re
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
_INTEG1_MANIFEST = Path(__file__).with_name("design_eval_cases_integ1.json")
_TRUSTED_CASE_HASHES = {
    "design_eval_cases.json": "d6ccb9c7953ae0b0228a2c76f64e2c3f989ba8a809aa42ecfefd657379f57464",
    "design_eval_cases_integ1.json": "10d923dfedccfb58d59802a06ac79021a34697f6aad1bd29edf3c398ed7ef469",
}
_BENCH2 = Path(__file__).resolve().parents[3] / "research" / "bench2" / "out" / "product_truth.json"
_BENCH2_REF = "benchmark-2-mini-star-stitch-cardigan"
_BENCH2_TRUTH_SHA = "5167e32bf702af7e56d8a8e78a8425b62febc6e69083ec57aaa3bfd0ab3e2aa1"
_BENCH2_BUILDER_SHA = "dec34b0b5cea211ef31399835952d2bc34679cdaa5bfe32a3b4a7330260f6a83"
_BENCH2_MANIFEST_SHA = "bf5f8c6807413dba16ff9b4a2b620a6774e67a20531aa87a3fde6008bdf101ed"


class DesignEvaluationRefused(ValueError):
    """The fixed held-out set is unavailable, altered, or challenger-supplied."""


class StaleEvaluation(DesignEvaluationRefused):
    """The queued inputs were superseded; the sweep will enqueue the new version."""


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bench2_files(db=None) -> tuple[bytes, bytes, bytes]:
    """Read the pinned benchmark evidence privately, including on worker-only hosts."""
    from ..teardown import library, licence

    try:
        licence.refuse_unless_permitted(db, _BENCH2_REF, "private_analysis")
        if _BENCH2.is_file():
            truth = _BENCH2.read_bytes()
            manifest = (_BENCH2.parent / "bench2_manifest.json").read_bytes()
            builder = (_BENCH2.parent.parent / "product_truth.py").read_bytes()
        else:
            if db is None:
                raise DesignEvaluationRefused("bench2 private evidence requires a database")
            prefix = f"{_BENCH2_REF}/evaluation"
            truth = library.retrieve(f"{prefix}/product_truth.json", "teardown_analyst", db=db)
            manifest = library.retrieve(f"{prefix}/bench2_manifest.json", "teardown_analyst", db=db)
            builder = library.retrieve(f"{prefix}/product_truth.py", "teardown_analyst", db=db)
    except (OSError, library.LibraryRefused, licence.LicenceRefused) as exc:
        raise DesignEvaluationRefused("bench2 private evidence is unavailable or unlicensed") from exc
    if (hashlib.sha256(truth).hexdigest() != _BENCH2_TRUTH_SHA
            or hashlib.sha256(builder).hexdigest() != _BENCH2_BUILDER_SHA
            or hashlib.sha256(manifest).hexdigest() != _BENCH2_MANIFEST_SHA):
        raise DesignEvaluationRefused("bench2 implementation evidence differs from its freeze")
    return truth, manifest, builder


def implementation_digest(db=None) -> str:
    """Bind evidence to the writer and deterministic checks that produced it."""
    import sys
    import numpy
    from ..cir import assembly, compiler, knowledge, reverse, specification, topology, twin
    from ..cir import writer
    from ..gates import asset_truth, certificate, originality, policy, risk_matrix
    from ..improve import design_knowledge
    from ..teardown import analysis_store, licence, reader, review, size_family
    from . import benchmark_e2e, design_revalidation

    modules = (sys.modules[__name__], writer, knowledge, compiler, reverse, twin, assembly, specification,
               topology, asset_truth, certificate, originality, policy, risk_matrix, benchmarks,
               benchmark_e2e, stitch_benchmarks, design_knowledge, analysis_store,
               licence, reader, review, size_family, design_revalidation)
    _, manifest, builder = _bench2_files(db)
    parts = [inspect.getsource(module) for module in modules]
    parts.extend(hashlib.sha256(data).hexdigest() for data in (manifest, builder))
    parts.append(numpy.__version__)
    try:
        import scipy
        parts.append(scipy.__version__)
    except ImportError:
        parts.append("scipy:unavailable")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def corpus_digest(db) -> str:
    """Bind evaluation to the current hashed originality corpus, not its source text."""
    from sqlalchemy import select
    from ..core.models import BenchmarkFingerprintRecord, BenchmarkLicence, BenchmarkProduct

    with db.session() as s:
        records = list(s.scalars(select(BenchmarkFingerprintRecord).order_by(
            BenchmarkFingerprintRecord.benchmark_ref)))
        products = list(s.scalars(select(BenchmarkProduct).order_by(BenchmarkProduct.ref)))
        licences = list(s.scalars(select(BenchmarkLicence).order_by(BenchmarkLicence.source_ref)))
        return _digest({"fingerprints": [
            {"ref": row.benchmark_ref, "features": row.features, "construction": row.construction,
             "size_sequences": row.size_sequences, "piece_numbers": row.piece_numbers,
             "wording": row.wording_shingles} for row in records],
            "products": [{"ref": row.ref, "files": row.files} for row in products],
            "licences": [{"ref": row.source_ref, "kind": row.source_kind,
                           "allowed": row.allowed_uses, "prohibited": row.prohibited_uses}
                          for row in licences]})


def materialize_cases(db=None) -> list[dict]:
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
    truth, _, _ = _bench2_files(db)
    cases.append({"kind": "benchmark_truth", "id": "bench2",
                  "truth_sha256": hashlib.sha256(truth).hexdigest()})
    for name, fn in sorted(stitch_benchmarks.FAMILIES.items()):
        cases.append({"kind": "stitch_family", "id": name,
                      "validator_sha256": hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()})
    return cases


def load_cases(*, challenger_cases=None, db=None) -> dict:
    """Return only the pinned shared set; a challenger cannot supply its own cases."""
    if challenger_cases is not None:
        raise DesignEvaluationRefused("a challenger may not supply evaluation cases")
    try:
        live = materialize_cases(db)
        available = [path for path in (_MANIFEST, _INTEG1_MANIFEST) if path.is_file()]
        if not available:
            raise DesignEvaluationRefused("held-out case manifest is unavailable")
        for path in available:
            frozen = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(frozen, dict) or frozen.get("sha256") != _TRUSTED_CASE_HASHES[path.name]:
                raise DesignEvaluationRefused("held-out case manifest is invalid")
            if frozen.get("cases") == live and frozen["sha256"] == _digest(live):
                return {"cases": live, "sha256": frozen["sha256"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DesignEvaluationRefused("held-out cases cannot be read") from exc
    raise DesignEvaluationRefused("held-out cases differ from the frozen manifest")


def measure_written_case(cir, text: str, *, db=None) -> dict:
    """Measure actual output without storing the output or reference instructions.

    This is a diagnostic, not a release certificate or an approval decision. In
    particular it cannot establish similarity against an unavailable library.
    """
    from ..cir.compiler import compile_cir
    from ..cir.compiler import ERROR
    from ..cir import assembly
    from ..cir.reverse import compare
    from ..cir.topology import topology_problems
    from ..cir.twin import build_twin
    from ..cir.writer import FINISHING_HEADING, finishing_lines
    from ..gates.asset_truth import check_shape_claims, check_technique_claims
    from ..gates import certificate, risk_matrix
    from ..gates.originality import release_findings, similarity_review
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
    end_check = int(any(re.search(r"\b(?:tug|check|test)\b", line, re.I)
                        and re.search(r"\bends?\b", line, re.I)
                        and re.search(r"\b(?:loose|secure)\b", line, re.I)
                        for line in section))
    twin_failures = 0
    truth_codes = []
    twins = {}
    for index, component in enumerate(cir.components):
        try:
            twin = build_twin(cir, compiled, component=component.name)
            twins[component.name] = twin
            if index == 0:
                # Match the certificate's title and notes checks. Applying the
                # whole multi-piece pattern to each individual component would
                # falsely require every piece to contain every named technique.
                truth_codes.extend(f.code for f in check_technique_claims(
                    cir.title, cir, twin, "cir.title"))
                truth_codes.extend(f.code for f in check_technique_claims(
                    cir.designer_notes or "", cir, twin, "cir.designer_notes"))
                truth_codes.extend(f.code for f in check_shape_claims(
                    cir.title, cir, twin, "cir.title"))
        except (ValueError, KeyError):
            twin_failures += 1
    if not twin_failures:
        findings = (certificate.specification_findings(cir)
                    + certificate.component_gauge_findings(cir)
                    + certificate.configuration_findings(cir)
                    + certificate.grading_findings(cir)
                    + risk_matrix.plausibility_findings(cir, twins)
                    + certificate.assembly_findings(cir, assembly.assemble(cir, twins))
                    + certificate.colour_carry_findings(cir)
                    + certificate.stitch_semantics_findings(cir))
        truth_codes.extend(f.code for f in findings if f.severity == ERROR)
        for twin in twins.values():
            if twin.geometry is not None:
                truth_codes.extend(f.code for f in twin.geometry.findings if f.severity == ERROR)
        truth_codes.extend("TOPOLOGY_INCONSISTENT" for _ in topology_problems(cir))
    similarity = None
    unknown_ip = 0
    if db is not None:
        from sqlalchemy import select
        from ..core.models import BenchmarkFingerprintRecord
        from ..gates.originality import code_benchmarks
        from ..teardown import licence

        with db.session() as s:
            refs = set(s.scalars(select(BenchmarkFingerprintRecord.benchmark_ref)))
        refs.update(b.ref for b in code_benchmarks())
        unknown_ip = sum(not licence.licence_for(db, ref).permits("similarity_review")[0]
                         for ref in refs)
        if not unknown_ip:
            similarity = similarity_review(cir, pattern_text=text, db=db)
            release_ip = release_findings(cir, pattern_text=text, db=db)
            unknown_ip += sum(f.code in ("ORIGINALITY_EVIDENCE_UNKNOWN", "ORIGINALITY_LICENCE_REFUSED",
                                        "ORIGINALITY_DURABLE_EVIDENCE_UNCHECKED") for f in release_ip)
    reverse_codes = sorted(f.code for f in compare(cir, text))
    policy_codes = sorted(f.code for f in check_text(text, "pattern"))
    return {"compile_errors": len(compiled.errors), "twin_failures": twin_failures,
            "reverse_findings": len(reverse_codes), "reverse_codes": reverse_codes,
            "policy_findings": len(policy_codes), "policy_codes": policy_codes,
            "truth_findings": len(truth_codes) if not twin_failures else None,
            "truth_codes": sorted(truth_codes) if not twin_failures else None,
            "originality_escalations": len(similarity["escalated"]) if similarity else None,
            "originality_escalation_keys": sorted(_digest(item) for item in similarity["escalated"])
            if similarity else None,
            "originality_unmeasured": (len(similarity["unmeasured"]) + unknown_ip if similarity
                                       else unknown_ip if db is not None else None),
            "finishing_actions_expected": len(expected),
            "finishing_actions_present": sum(line in normalized for line in expected),
            "finishing_actions_listed": sum(('- ' + line) in section for line in expected),
            "end_check_present": end_check}


def compare_written_case(cir, baseline: str, candidate: str, *, db=None) -> dict:
    """Compare two actual renderings, exposing regressions without persisting text."""
    from ..gates.originality import shingles

    before = measure_written_case(cir, baseline, db=db)
    after = measure_written_case(cir, candidate, db=db)
    regressions = [key for key in ("compile_errors", "twin_failures", "reverse_findings",
                                  "policy_findings", "truth_findings", "originality_escalations")
                   if before[key] is not None and after[key] is not None
                   and after[key] > before[key]]
    # Equal counts can still hide a new defect replacing an old one.
    for key in ("reverse_codes", "policy_codes", "truth_codes", "originality_escalation_keys"):
        if before[key] is not None and after[key] is not None \
                and Counter(after[key]) - Counter(before[key]):
            regressions.append(key)
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
    return {"before": before, "after": after, "regressions": regressions,
            "same_word_shingles": same_shingles,
            "approval_evidence_complete": False,
            "incomplete_reason": "full benchmark and Product Truth evaluation is incomplete"}


def _preview_checklist(text: str, *, rule_name: str = "include_finishing_checklist") -> str:
    from ..cir.writer import finishing_checklist

    try:
        return finishing_checklist(text, check_ends=rule_name == "include_checklist_and_end_check")
    except ValueError as exc:
        raise DesignEvaluationRefused(str(exc)) from exc


def _bench2_stages(db) -> dict:
    """Replay only frozen private Product Truth; never render the benchmark pattern."""
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR, Component, Gauge, Material, Op, Row, Seam

    truth_bytes, manifest_bytes, builder_bytes = _bench2_files(db)
    try:
        truth = json.loads(truth_bytes)
        manifest = json.loads(manifest_bytes)
        checks = truth["derived"]["checks"]
        pattern_ok = (len(checks) == 25 and all(c["status"] == "PASS"
                      and len(c["per_size"]) == 10
                      and all(value is True for value in c["per_size"]) for c in checks))
        tree = ast.parse(builder_bytes, filename="<pinned-private-benchmark>")
        builders = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "build_cir"]
        if len(builders) != 1:
            raise ValueError("invalid pinned builder")
        safe_globals = {"__builtins__": {"int": int, "range": range, "round": round},
                        "CIR": CIR, "Component": Component, "Gauge": Gauge,
                        "Material": Material, "Op": Op, "Row": Row, "Seam": Seam,
                        "SIZES": ("0-3m", "3-6m", "6-12m", "12-18m", "2-3T",
                                  "4", "6", "8", "10", "12")}
        module = ast.fix_missing_locations(ast.Module(body=builders, type_ignores=[]))
        exec(compile(module, "<pinned-private-benchmark>", "exec"), safe_globals)
        facts = dict(truth["facts"])
        facts["_derived_after"] = [row["sleeve_rows_after_neck_derived"]
                                   for row in truth["derived"]["per_size"]]
        cir = safe_globals["build_cir"](facts, "2-3T")
        cir_ok = compile_cir(cir).ok and cir.fingerprint == manifest.get("cir_fingerprint")
    except (KeyError, TypeError, ValueError, SyntaxError) as exc:
        raise DesignEvaluationRefused("bench2 Product Truth cannot be validated") from exc
    return {"pattern": "PASS" if pattern_ok else "FAIL", "cir": "PASS" if cir_ok else "FAIL",
            "reference": "UNKNOWN", "ad_image": "UNKNOWN", "comparison": "UNKNOWN"}


def _benchmark_checks(db) -> dict:
    """Run existing offline benchmark gates; retain statuses only, never source text."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    cir = benchmarks.cardigan("XS")
    compiled = compile_cir(cir)
    twins_ok = compiled.ok
    if twins_ok:
        for component in cir.components:
            try:
                build_twin(cir, compiled, component=component.name)
            except (ValueError, KeyError):
                twins_ok = False
    stages = _bench2_stages(db)
    return {"bench1_seam_compatible": benchmarks.reconcile("XS")["seam_compatible"],
            "bench1_compiles": compiled.ok, "bench1_twins": twins_ok,
            "bench2_stages": stages,
            "stitch_families": {name: stitch_benchmarks.promotion_gate(name)["state"]
                                for name in sorted(stitch_benchmarks.FAMILIES)}}


def classify_evaluation(report: dict) -> str:
    """Require measured, non-regressing cases and a measurable writer improvement."""
    try:
        from ..improve import design_knowledge
        cases = report["cases"]
        checks = report["benchmark_checks"]
        scope = report.get("scope", {"writer_section": "finishing"})
        design_knowledge.scope_slot(scope)
        if ("construction_family" in scope and report.get("out_of_scope_controls") !=
                "unmodified_no_knowledge"):
            return "insufficient_evidence"
        matches = {slug: design_knowledge.scope_matches(scope, launch0.cir_for(build))
                   for slug, build in _LAUNCH_CASES}
        if not any(matches.values()):
            return "insufficient_evidence"
        if report["rule_name"] not in ("include_finishing_checklist", "include_checklist_and_end_check"):
            return "insufficient_evidence"
        if ({c["case"] for c in cases} != {slug for slug, _ in _LAUNCH_CASES}
                or len(cases) != len(_LAUNCH_CASES)):
            return "insufficient_evidence"
        if (checks["bench1_seam_compatible"] is not True
                or checks["bench1_compiles"] is not True or checks["bench1_twins"] is not True
                or checks["bench2_stages"].get("pattern") != "PASS"
                or checks["bench2_stages"].get("cir") != "PASS"
                or set(checks["stitch_families"]) != set(stitch_benchmarks.FAMILIES)
                or any(v != "PROMOTABLE" for v in checks["stitch_families"].values())):
            return "insufficient_evidence"
        improvement = False
        for case in cases:
            before, after = case["before"], case["after"]
            if not matches[case["case"]] and before != after:
                return "regression"
            for metric in ("compile_errors", "twin_failures", "reverse_findings",
                           "policy_findings", "truth_findings", "finishing_actions_present",
                           "finishing_actions_listed", "end_check_present"):
                if type(before[metric]) is not int or type(after[metric]) is not int:
                    return "insufficient_evidence"
                if before[metric] < 0 or after[metric] < 0:
                    return "insufficient_evidence"
            if before["end_check_present"] not in (0, 1) or after["end_check_present"] not in (0, 1):
                return "insufficient_evidence"
            if case["regressions"] or after["truth_findings"] != 0:
                return "regression"
            if report["rule_name"] == "include_finishing_checklist" \
                    and case["same_word_shingles"] is not True:
                return "regression"
            for metric in ("reverse_codes", "policy_codes", "truth_codes"):
                if not isinstance(before[metric], list) or not isinstance(after[metric], list):
                    return "insufficient_evidence"
                count_key = {"reverse_codes": "reverse_findings", "policy_codes": "policy_findings",
                             "truth_codes": "truth_findings"}[metric]
                if len(before[metric]) != before[count_key] or len(after[metric]) != after[count_key]:
                    return "insufficient_evidence"
                if Counter(after[metric]) - Counter(before[metric]):
                    return "regression"
            if any(after[k] > before[k] for k in ("compile_errors", "twin_failures",
                                                   "reverse_findings", "policy_findings")):
                return "regression"
            if after["finishing_actions_present"] < before["finishing_actions_present"]:
                return "regression"
            if after["end_check_present"] < before["end_check_present"]:
                return "regression"
            if matches[case["case"]]:
                improvement |= after["finishing_actions_listed"] > before["finishing_actions_listed"]
                improvement |= after["end_check_present"] > before["end_check_present"]
        for case in cases:
            for phase in ("before", "after"):
                if case[phase]["originality_unmeasured"] != 0:
                    return "insufficient_evidence"
                if type(case[phase]["originality_escalations"]) is not int:
                    return "insufficient_evidence"
                if not isinstance(case[phase]["originality_escalation_keys"], list):
                    return "insufficient_evidence"
                if len(case[phase]["originality_escalation_keys"]) != \
                        case[phase]["originality_escalations"]:
                    return "insufficient_evidence"
            if Counter(case["after"]["originality_escalation_keys"]) - Counter(
                    case["before"]["originality_escalation_keys"]):
                return "regression"
        return "passed" if improvement else "no_improvement"
    except (KeyError, TypeError, ValueError):
        return "insufficient_evidence"


def _incumbent_pins(db, scope: dict | None = None) -> list[dict]:
    """Authenticate the old decision for a fresh comparison against the current corpus."""
    from ..improve import design_knowledge

    try:
        return [record["pin"] for record in design_knowledge.incumbent_for_evaluation(db, scope)]
    except (design_knowledge.DesignKnowledgeRefused, ValueError) as exc:
        raise DesignEvaluationRefused("incumbent knowledge cannot be verified") from exc


def evaluation_key(db, rule_id: int) -> str:
    from ..core.models import DesignRule
    from ..improve.design_knowledge import lineage_digest, rule_digest

    with db.session() as s:
        row = s.get(DesignRule, rule_id)
        if row is None or row.state != "proposed":
            raise DesignEvaluationRefused("a proposed rule is required")
        rule_sha = rule_digest(row)
        lineage_sha = lineage_digest(s, row)
        supersedes = row.supersedes
        scope = dict(row.scope)
    incumbent = _incumbent_pins(db, scope)
    if incumbent and supersedes != incumbent[0]["rule_id"]:
        raise DesignEvaluationRefused("candidate must supersede the current incumbent")
    identity = {"rule": rule_sha, "cases": load_cases(db=db)["sha256"],
                "lineage": lineage_sha, "implementation": implementation_digest(db),
                "corpus": corpus_digest(db), "incumbent": incumbent}
    return f"design-eval:{rule_id}:{_digest(identity)}"


def evaluate(db, rule_id: int, *, expected_key: str | None = None) -> dict:
    """Run and persist the fixed evaluation; UNKNOWN and no improvement block approval."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from ..core.models import AuditLog, DesignEvaluationRun, DesignRule
    from ..improve.design_knowledge import lineage_digest, rule_digest

    run_key = evaluation_key(db, rule_id)
    if expected_key is not None and expected_key != run_key:
        raise StaleEvaluation("evaluation inputs changed before execution")
    with db.session() as s:
        existing = s.scalar(select(DesignEvaluationRun).where(DesignEvaluationRun.run_key == run_key))
        if existing is not None:
            audit = s.get(AuditLog, existing.audit_id)
            if audit is None or audit.action != "design_eval.completed":
                raise DesignEvaluationRefused("completed evaluation evidence is missing")
            return {**audit.detail, "audit_id": audit.id,
                    "evaluation_digest": _digest(audit.detail), "created": False}
    implementation = implementation_digest(db)
    corpus = corpus_digest(db)
    with db.session() as s:
        lineage = lineage_digest(s, s.get(DesignRule, rule_id))
    result = dict(preview_registered_rule(db, rule_id))
    preview_id = result.pop("audit_id")
    if implementation != implementation_digest(db) or corpus != corpus_digest(db):
        raise DesignEvaluationRefused("evaluation environment changed during measurement")
    result.update({"implementation_sha256": implementation, "corpus_sha256": corpus,
                   "lineage_sha256": lineage,
                   "preview_id": preview_id, "run_key": run_key})
    result["state"] = classify_evaluation(result)
    result["approval_evidence_complete"] = result["state"] == "passed"
    result.pop("why", None)
    if evaluation_key(db, rule_id) != run_key:
        raise DesignEvaluationRefused("evaluation inputs changed during measurement")
    try:
        with db.session() as s:
            row = s.scalar(select(DesignRule).where(DesignRule.id == rule_id).with_for_update())
            if row is None or row.state != "proposed" or rule_digest(row) != result["rule_sha256"]:
                raise DesignEvaluationRefused("proposal changed during evaluation")
            current = [r.id for r in s.scalars(select(DesignRule).where(
                DesignRule.state == "approved").with_for_update()) if r.scope == row.scope]
            if current != [pin["rule_id"] for pin in result["incumbent_pins"]]:
                raise DesignEvaluationRefused("incumbent knowledge changed during evaluation")
            audit = AuditLog(actor="design_evaluator", action="design_eval.completed",
                             artifact=f"design-rule:{rule_id}", detail=result)
            s.add(audit)
            s.flush()
            s.add(DesignEvaluationRun(run_key=run_key, rule_id=rule_id, audit_id=audit.id))
            s.flush()
            return {**result, "audit_id": audit.id, "evaluation_digest": _digest(result),
                    "created": True}
    except IntegrityError:
        with db.session() as s:
            existing = s.scalar(select(DesignEvaluationRun).where(
                DesignEvaluationRun.run_key == run_key))
            if existing is None:
                raise
            audit = s.get(AuditLog, existing.audit_id)
            if audit is None:
                raise DesignEvaluationRefused("completed evaluation evidence is missing")
            return {**audit.detail, "audit_id": audit.id,
                    "evaluation_digest": _digest(audit.detail), "created": False}


def preview_registered_rule(db, rule_id: int) -> dict:
    """Measure a registered proposal against the frozen launch cases.

    This preview deliberately cannot approve a rule: the production writer and
    the complete benchmark/originality stages must first be bound to the same
    evaluated implementation. No customer or reference instructions are saved.
    """
    from sqlalchemy import select

    from ..cir.compiler import compile_cir
    import copy
    from ..cir import knowledge
    from ..cir.writer import write_pattern
    from ..core.models import AuditLog, DesignRule
    from ..improve.design_knowledge import _TOKEN, scope_matches, scope_slot

    if type(rule_id) is not int or rule_id <= 0:
        raise DesignEvaluationRefused("invalid rule id")
    frozen = load_cases(db=db)
    with db.session() as s:
        rule = s.get(DesignRule, rule_id)
        if rule is None or rule.state != "proposed":
            raise DesignEvaluationRefused("a proposed rule is required")
        if not isinstance(rule.key, str) or not _TOKEN.fullmatch(rule.key):
            raise DesignEvaluationRefused("invalid rule key")
        if (not isinstance(rule.statement, dict) or set(rule.statement) != {"rule", "parameters"}
                or rule.statement.get("rule") not in ("include_finishing_checklist",
                                                       "include_checklist_and_end_check")
                or rule.statement.get("parameters") != {}):
            raise DesignEvaluationRefused("unsupported rule or scope")
        try:
            scope_slot(rule.scope)
        except ValueError as exc:
            raise DesignEvaluationRefused("unsupported rule or scope") from exc
        incumbent = _incumbent_pins(db, rule.scope)
        if incumbent and rule.supersedes != incumbent[0]["rule_id"]:
            raise DesignEvaluationRefused("candidate must supersede the current incumbent")
        identity = {"id": rule.id, "key": rule.key, "version": rule.version,
                    "statement": rule.statement, "scope": rule.scope,
                    "provenance": rule.provenance, "producer": rule.producer,
                    "supersedes": rule.supersedes}
    case_results = []
    for case in frozen["cases"]:
        if case["kind"] != "launch0":
            continue
        cir = launch0.cir_for(case["build"])
        matches_scope = scope_matches(identity["scope"], cir)
        compiled = compile_cir(cir)
        plain = write_pattern(cir, compiled)
        if incumbent and matches_scope:
            from ..improve.design_knowledge import incumbent_for_evaluation

            records = incumbent_for_evaluation(db, identity["scope"])
            if [record["pin"] for record in records] != incumbent or cir.provenance is None:
                raise DesignEvaluationRefused("incumbent changed during evaluation")
            incumbent_cir = copy.deepcopy(cir)
            incumbent_rule = records[0]["statement"]["rule"]
            incumbent_cir.provenance.primitives_used += (
                knowledge.marker(incumbent_rule, incumbent[0]),)
            baseline = write_pattern(incumbent_cir, compile_cir(incumbent_cir))
        else:
            baseline = plain
        if incumbent and matches_scope and baseline != _preview_checklist(plain, rule_name=incumbent_rule):
            raise DesignEvaluationRefused("incumbent writer output could not be verified")
        # A hypothetical marker is confined to this held-out run; it has no
        # approval authority. Exercise the actual writer rather than approving
        # a preview whose output might differ from production.
        if cir.provenance is None:
            raise DesignEvaluationRefused("candidate CIR has no provenance")
        candidate_cir = copy.deepcopy(cir)
        hypothetical_pin = {"rule_id": identity["id"], "rule_version": identity["version"],
                            "rule_digest": _digest(identity), "evaluation_digest": "0" * 64}
        if matches_scope:
            candidate_cir.provenance.primitives_used += (
                knowledge.marker(identity["statement"]["rule"], hypothetical_pin),)
        candidate = write_pattern(candidate_cir, compile_cir(candidate_cir))
        expected = (_preview_checklist(baseline, rule_name=identity["statement"]["rule"])
                    if matches_scope else baseline)
        if candidate != expected:
            raise DesignEvaluationRefused("candidate writer output differs from evaluated preview")
        case_results.append({"case": case["id"], **compare_written_case(cir, baseline, candidate,
                                                                          db=db)})
    if len(case_results) != len(_LAUNCH_CASES):
        raise DesignEvaluationRefused("not all frozen launch cases were measured")
    report = {"rule_id": rule_id, "rule_key": identity["key"],
              "rule_version": identity["version"], "rule_sha256": _digest(identity),
              "rule_name": identity["statement"]["rule"],
              "scope": identity["scope"],
              "out_of_scope_controls": "unmodified_no_knowledge",
              "case_set_sha256": frozen["sha256"], "incumbent_pins": incumbent,
              "cases": case_results,
              "benchmark_checks": _benchmark_checks(db),
              "state": "insufficient_evidence", "approval_evidence_complete": False,
              "why": "preview renderer is not the production writer; benchmark and full "
                     "Product Truth evidence is incomplete"}
    with db.session() as s:
        current = s.scalar(select(DesignRule).where(DesignRule.id == rule_id).with_for_update())
        if current is None or current.state != "proposed" or _digest({
                "id": current.id, "key": current.key, "version": current.version,
                "statement": current.statement, "scope": current.scope,
                "provenance": current.provenance, "producer": current.producer,
                "supersedes": current.supersedes}) != report["rule_sha256"]:
            raise DesignEvaluationRefused("proposal changed during evaluation")
        row = AuditLog(actor="design_evaluator", action="design_eval.preview",
                       artifact=f"design-rule:{rule_id}", detail=report)
        s.add(row)
        s.flush()
        report = {**report, "audit_id": row.id}
    return report
