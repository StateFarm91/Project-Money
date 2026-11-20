"""Eval fixtures for model-backed steps (Master Plan section 27).

A prompt version is only safe to change if there is a way to tell whether it got worse.
These are assertions about output *properties*, not exact strings, because a naming prompt
that returns different names is working and one that returns a size claim is broken.

The properties are chosen to catch the failure that actually matters here: a model quietly
adding a factual claim the pattern data does not support. Everything the compiler owns is
checked by the compiler; these check the narrow band where a model is allowed to operate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

_CLAIMY = re.compile(
    r"\b(\d+\s*(cm|inch|inches|in|m|metres|meters|yards?|yds?|sts?|stitches|rows?)\b|"
    r"beginner|intermediate|advanced|easy|quick|guaranteed|fits?\b)", re.I)


@dataclass
class EvalCase:
    name: str
    prompt_ref: str
    values: dict
    check: Callable[[dict], list[str]]


@dataclass
class EvalResult:
    case: str
    passed: bool
    problems: list[str] = field(default_factory=list)


def _naming_check(out: dict) -> list[str]:
    problems: list[str] = []
    names = out.get("names")
    if not isinstance(names, list) or len(names) != 3:
        return ["expected exactly three names"]
    for n in names:
        if not isinstance(n, str) or not n.strip():
            problems.append("a name is empty")
            continue
        if len(n) > 60:
            problems.append(f"name too long for a title slot: {n!r}")
        hit = _CLAIMY.search(n)
        if hit:
            # This is the whole point of the eval. A name is allowed to be evocative; it is
            # not allowed to assert a property that only the pattern data can establish.
            problems.append(f"name makes an unsupported claim ({hit.group(0)!r}): {n!r}")
    return problems


def _polish_check(original: str) -> Callable[[dict], list[str]]:
    facts = set(_CLAIMY.findall(original.lower()))

    def check(out: dict) -> list[str]:
        problems: list[str] = []
        text = out.get("description")
        if not isinstance(text, str) or len(text) < 50:
            return ["description came back missing or truncated"]
        after = set(_CLAIMY.findall(text.lower()))
        lost = facts - after
        added = after - facts
        if lost:
            problems.append(f"polish dropped factual claims: {sorted(lost)[:5]}")
        if added:
            problems.append(f"polish invented factual claims: {sorted(added)[:5]}")
        if out.get("changed_facts") is not False:
            problems.append("the model admits it changed facts")
        return problems

    return check


def _mining_check(out: dict) -> list[str]:
    themes = out.get("themes")
    if not isinstance(themes, list):
        return ["themes must be a list"]
    problems = []
    for t in themes:
        if not isinstance(t, dict) or "theme" not in t or "count" not in t:
            problems.append(f"malformed theme entry: {t!r}")
            continue
        if not isinstance(t["count"], int) or t["count"] < 1:
            problems.append(f"theme count must be a real positive count: {t!r}")
    return problems


SAMPLE_DESCRIPTION = (
    "Finished size: 90 x 122 cm, worked at the gauge below. Gauge: 16 sts x 18 rows = 10 cm "
    "in sc, 5 mm hook. Difficulty: confident beginner. Yarn: about 328-492 m of cream."
)

CASES: list[EvalCase] = [
    EvalCase("naming stays evocative and claimless", "concept.naming@1",
             {"category": "mosaic blanket", "motifs": "fir, star", "season": "Christmas"},
             _naming_check),
    EvalCase("polish preserves every factual claim", "listing.polish@1",
             {"description": SAMPLE_DESCRIPTION}, _polish_check(SAMPLE_DESCRIPTION)),
    EvalCase("review mining invents nothing", "review.mining@1",
             {"messages": "row 4 count seems off\nrow 4 count seems off\nlovely chart"},
             _mining_check),
]


def run_evals(gateway, agent: str = "market_radar",
              cases: list[EvalCase] | None = None) -> list[EvalResult]:
    """Run every case through the gateway. A failure here blocks a prompt version change."""
    results: list[EvalResult] = []
    for case in (cases or CASES):
        try:
            out = gateway.complete_json(case.prompt_ref, agent=agent, values=case.values)
        except Exception as e:  # noqa: BLE001
            results.append(EvalResult(case.name, False, [f"{type(e).__name__}: {e}"]))
            continue
        problems = case.check(out)
        results.append(EvalResult(case.name, not problems, problems))
    return results
