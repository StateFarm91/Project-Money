"""F-096: provider compatibility pack -- deterministic golden tasks, stubs only."""
import json
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


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
