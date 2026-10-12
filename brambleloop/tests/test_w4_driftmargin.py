"""W4-DRIFTMARGIN: F-218, graded drift margins and a near-threshold trend for the canonical model.

The identity verdicts stay ternary (match / drift / unmeasurable). The judge now also grades
each answer `clear` or `borderline`. Grades are recorded per frame, and `drift_series`
trends the share of passes graded borderline with the same rule it uses for drift, so a
run of near-threshold passes is visible before any pass becomes drift. A missing or
off-vocabulary grade is `unknown` and never counts as clear. Identity gates are unchanged:
Laura (laura-r2-a42aeac7) is judged exactly as before. Stub judge only: no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_driftmargin.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.publish import model_photography as MP  # noqa: E402
from brambleloop.visual import drift_series, identity, model_registry  # noqa: E402


class _Judge:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad, cost_per_1k_output_cad = 0.003, 0.015

    def __init__(self, answer):
        self.answer = answer

    def see(self, system, prompt, images, max_tokens=0):
        payload = json.dumps(self.answer)

        class R:
            text = payload
            input_tokens, output_tokens = 2400, 200
        return R()


def test_the_prompt_asks_for_a_grade_without_changing_the_question():
    p = model_registry.compare_prompt()
    assert '"margins"' in p and "never changes it" in p
    for d in identity.DRIFT_DIMENSIONS:
        assert d in p


def test_compare_identity_records_grades_and_keeps_verdicts_unchanged():
    dims = list(identity.DRIFT_DIMENSIONS)
    assert dims
    answer = {d: "match" for d in dims}
    answer[dims[0]] = "drift"
    answer[dims[1]] = "unmeasurable"
    answer["margins"] = {dims[0]: "borderline", dims[2]: "clear", dims[3]: "maybe"}
    out = model_registry.compare_identity(None, "ref.png", "cand.png", provider=_Judge(answer))
    assert out[dims[0]] == "drift" and out[dims[1]] == "unmeasurable" and out[dims[2]] == "match"
    m = out["margins"]
    assert m[dims[0]] == "borderline" and m[dims[2]] == "clear"
    assert m[dims[3]] == "unknown", "an off-vocabulary grade is unknown, never clear"
    assert dims[1] not in m, "an unmeasurable dimension has no grade"


def test_margins_merge_from_the_comparison_that_could_see_each_dimension():
    face = identity.FACE_DIMENSIONS[0]
    body = identity.MORPHOLOGY_DIMENSIONS[0]
    got = MP._merge_margins({"margins": {face: "borderline", body: "clear"}},
                            {"margins": {face: "clear", body: "borderline"}}, has_body=True)
    assert got == {face: "borderline", body: "borderline"}
    assert MP._merge_margins({"margins": {face: "clear"}}, {"margins": {body: "clear"}},
                             has_body=False) == {face: "clear"}


def _file_batches(db, near_shares, dim):
    now = datetime.now(timezone.utc)
    assert near_shares
    with db.session() as s:
        for b, near in enumerate(near_shares):
            for i in range(4):
                margins = {dim: "borderline" if i < near else "clear"}
                s.add(AuditLog(actor="publishing", action=MP.ACTION,
                               at=now - timedelta(days=len(near_shares) - b),
                               detail={"identity": {
                                   "dimensions": {d: "match" for d in identity.DRIFT_DIMENSIONS},
                                   "margins": margins}}))


def test_a_rising_run_of_borderline_passes_is_reported_before_any_drift():
    db = Database("sqlite://")
    db.create_all()
    dim = identity.FACE_DIMENSIONS[0]
    _file_batches(db, [0, 1, 2, 3], dim)
    out = drift_series.series(db)
    assert out["gradual_drift"] == [], "no pass became drift"
    trend = {t["dimension"]: t for t in out["near_threshold_trend"]}
    assert dim in trend and trend[dim]["rising"] is True, out["near_pass_per_dimension"][dim]
    assert trend[dim]["near_pass_shares"] == [0.0, 0.25, 0.5, 0.75]


def test_steady_or_ungraded_passes_are_not_a_trend():
    db = Database("sqlite://")
    db.create_all()
    dim = identity.FACE_DIMENSIONS[0]
    _file_batches(db, [1, 1, 1, 1], dim)
    assert drift_series.series(db)["near_threshold_trend"] == []
    db2 = Database("sqlite://")
    db2.create_all()
    now = datetime.now(timezone.utc)
    with db2.session() as s:
        for b in range(4):
            for _ in range(3):
                s.add(AuditLog(actor="publishing", action=MP.ACTION,
                               at=now - timedelta(days=4 - b),
                               detail={"identity": {"dimensions": {
                                   d: "match" for d in identity.DRIFT_DIMENSIONS}}}))
    out = drift_series.series(db2)
    assert out["near_threshold_trend"] == []
    assert all(x is None for x in out["near_pass_per_dimension"][dim]), "ungraded is no reading"


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
