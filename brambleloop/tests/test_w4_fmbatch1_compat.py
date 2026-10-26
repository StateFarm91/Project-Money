"""F-096: provider compatibility pack -- deterministic golden tasks, stubs only."""
import json
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import compat_pack as C  # noqa: E402
from brambleloop.gateway.model_gateway import EchoProvider, ModelResponse  # noqa: E402

GOOD = {
    "extract": {"stitches_per_10cm": 18, "rows_per_10cm": 20, "hook_mm": 4.5,
                "total_metres": 255},
    "Rank": {"ranking": ["A", "C", "B"], "violations": ["B"]},
    "Shop X": {"winners": {"conversion": "X", "return_rate": "Y", "cost_per_sale": "X"}},
    "Conversion was": {"direction": "worse", "relative_change": -0.25, "significant": True},
}


def _script(answers):
    def f(_system, user):
        for k, v in answers.items():
            if k in user:
                return json.dumps(v)
        return "{}"
    return f


class _Vision(EchoProvider):
    def see(self, system, prompt, image_urls, *, max_tokens):
        assert image_urls == ["fixture://compat/gallery_4_listings.png"]
        return ModelResponse(text='{"listing_count": 4}', provider=self.name,
                             model=self.model, input_tokens=1, output_tokens=1, latency_ms=0)


def test_every_family_has_a_golden_task():
    assert set(C.FAMILIES) == {"extraction", "vision_gallery", "creative_jury",
                               "benchmark_comparison", "improvement_analysis"}


def test_a_correct_vision_provider_is_compatible():
    rep = C.run(_Vision(scripted=_script({"From this text": GOOD["extract"], **GOOD})))
    assert rep["compatible"] is True, rep
    assert rep["counts"]["PASS"] == len(C.TASKS)


def test_text_only_provider_is_unsupported_never_pass():
    rep = C.run(EchoProvider(scripted=_script({"From this text": GOOD["extract"], **GOOD})))
    vis = [r for r in rep["results"] if r["family"] == "vision_gallery"][0]
    assert vis["status"] == "UNSUPPORTED" and rep["compatible"] is False


def test_wrong_answers_fail_with_reasons():
    bad = {"From this text": {**GOOD["extract"], "hook_mm": 5.0},
           "Rank": {"ranking": ["B", "A", "C"], "violations": []},
           "Shop X": {"winners": {"conversion": "Y", "return_rate": "Y", "cost_per_sale": "X"}},
           "Conversion was": {"direction": "better", "relative_change": 0.25,
                              "significant": True}}
    rep = C.run(_Vision(scripted=_script(bad)))
    st = {r["task"]: r for r in rep["results"]}
    assert st["extract.gauge_yardage"]["status"] == "FAIL"
    assert any("hook_mm" in p for p in st["extract.gauge_yardage"]["problems"])
    assert any("ranked first" in p for p in st["jury.hard_rule"]["problems"])
    assert st["bench.per_metric"]["status"] == "FAIL"
    assert st["improve.direction"]["status"] == "FAIL"
    assert st["vision.gallery_count"]["status"] == "PASS"
    assert rep["compatible"] is False


def test_errors_and_prose_are_errors_not_passes():
    rep = C.run(EchoProvider(scripted=lambda s, u: "I think the answer is 18."))
    assert {r["status"] for r in rep["results"]} == {"ERROR", "UNSUPPORTED"}
    down = C.run(_Vision(fail_times=99))
    assert all(r["status"] == "ERROR" for r in down["results"]
               if r["family"] != "vision_gallery")


def test_compare_flags_a_swap_that_loses_a_task_and_records():
    cur = C.run(_Vision(scripted=_script({"From this text": GOOD["extract"], **GOOD})))
    cand = C.run(EchoProvider(name="other", scripted=_script(
        {"From this text": GOOD["extract"], **GOOD})))
    cmp_ = C.compare(cur, cand)
    assert cmp_["swap_safe"] is False and cmp_["lost"] == ["vision.gallery_count"]
    assert C.compare(cur, cur)["swap_safe"] is True
    db = Database("sqlite://")
    db.create_all()
    assert C.latest(db) is None
    C.record(db, cand)
    assert C.latest(db)["compatible"] is False


# ---- independent review F-4 / F-5: a live drill is billed and reserved like any paid call --

def _paid_db():
    import tempfile

    from brambleloop.agents.registry import Registry

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1cp-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


@dataclass
class _Paid(EchoProvider):
    name: str = "anthropic"
    model: str = "claude-haiku-4-5"
    cost_per_1k_input_cad: float = 0.001
    cost_per_1k_output_cad: float = 0.005


def _ledger(db):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return [(r.purpose, r.amount_cad, r.tokens_in) for r in s.query(CostEntry).all()]


def test_review_f4_every_billed_response_is_a_spend_row_and_nothing_stays_reserved():
    from brambleloop.finance import reservations

    db = _paid_db()
    p = _Paid(scripted=_script({"From this text": GOOD["extract"], **GOOD}))
    rep = C.run(p, db=db)
    rows = _ledger(db)
    billed = [r for r in rows if r[0] == "compat_pack"]
    # Four text tasks answered; the vision task is UNSUPPORTED and makes no call.
    assert len(billed) == 4 and all(a > 0 for _p, a, _t in billed), rows
    assert rep["counts"]["UNSUPPORTED"] == 1
    assert reservations.outstanding(db)["count"] == 0


def test_review_f4_unreadable_usage_is_billed_at_the_estimate_not_released_as_free():
    from brambleloop.finance import reservations

    class _NoUsage(_Paid):
        def complete(self, system, user, *, max_tokens):
            class R:
                text = "{}"
            return R()

    db = _paid_db()
    C.run(_NoUsage(), db=db, tasks=(C.TASKS[0],))
    billed = [r for r in _ledger(db) if r[0] == "compat_pack"]
    assert len(billed) == 1 and billed[0][1] > 0, billed
    assert reservations.outstanding(db)["count"] == 0


def test_review_f5_vision_reserves_its_image_tokens_and_text_only_reserves_nothing():
    from brambleloop.gateway import providers as gw

    seen = []
    real = gw.check_budget

    def spy(db, **kw):
        seen.append(kw)
        return real(db, **kw)

    gw.check_budget = spy
    try:
        db = _paid_db()

        class _PaidVision(_Paid):
            def see(self, system, prompt, image_urls, *, max_tokens):
                return ModelResponse(text='{"listing_count": 4}', provider=self.name,
                                     model=self.model, input_tokens=10, output_tokens=5,
                                     latency_ms=0)

        vt = next(t for t in C.TASKS if t.vision)
        C.run(_PaidVision(), db=db, tasks=(vt,))
        assert seen and seen[0]["input_tokens"] >= gw.IMAGE_TOKENS_ESTIMATE
        seen.clear()
        C.run(_Paid(), db=db, tasks=(vt,))                    # text-only: no reservation
        assert seen == []
    finally:
        gw.check_budget = real


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
