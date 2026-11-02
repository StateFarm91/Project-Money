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


def measure_written_case(cir, text: str) -> dict:
    """Measure actual output without storing the output or reference instructions.

    This is a diagnostic, not a release certificate or an approval decision. In
    particular it cannot establish similarity against an unavailable library.
    """
    from ..cir.compiler import compile_cir
    from ..cir.reverse import compare
    from ..cir.writer import FINISHING_HEADING, finishing_lines
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
    return {"compile_errors": len(compiled.errors),
            "reverse_findings": len(compare(cir, text)),
            "policy_findings": len(check_text(text, "pattern")),
            "finishing_actions_expected": len(expected),
            "finishing_actions_present": sum(line in normalized for line in expected),
            "finishing_actions_listed": sum(('- ' + line) in section for line in expected)}


def compare_written_case(cir, baseline: str, candidate: str) -> dict:
    """Compare two actual renderings, exposing regressions without persisting text."""
    from ..gates.originality import shingles

    before = measure_written_case(cir, baseline)
    after = measure_written_case(cir, candidate)
    regressions = [key for key in ("compile_errors", "reverse_findings", "policy_findings")
                   if after[key] > before[key]]
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
            "incomplete_reason": "benchmark originality and Product Truth evaluation not measured"}
