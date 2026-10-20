"""W-VISNEXT: the owner's six-reference single-shot baseline in the WRAPTEST harness.

Offline: the stub provider, no key, no spend. Proves the exact owner references (and the
auto-generated equivalents) go out in the owner's order behind the canonical three; that each
candidate is saved with its ordered fingerprints, prompt, receipt and cost, labelled
EXPERIMENT and never publishable; that verification classifies with the shared codes and
retries a routed FAIL at most twice in total, carrying the repair negatives; that UNKNOWN and
unrouted FAIL are never retried; and that --live refuses without keys.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_baseline_six.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="baseline6-art-")
HARNESS = ROOT / "research" / "final_build" / "w4" / "experiment_wrap" / "run.py"
OWNER_SHAS = [
    "a42aeac72ba5733e42f55f9eb527218242c50610531ec9263ffb6f3e82519bc9",
    "afe6191fb4c68d0a9c61229fe822a1032ee7c54150597210888db25b0f9ef0db",
    "f32bac686cba46c75e3ac193e72f2bcea4ba7ebc80355a102a4bed4bca3931e0",
    "3f737a0835691df44da268af41356005015c7e95ce9991d1ab821cfdbb9d5747",
    "10d013b8a53de2f1f15e76287425f8b86e04dfb0cc88e2b233d8fa8c7c97fd36",
    "3638b3a57a71c074695ec7a9c70bfd07cad9bf22c944e55996cca4351960f14b"]


def _harness():
    spec = importlib.util.spec_from_file_location("wraptest_run_b6", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _harness()
import baseline_six as B  # noqa: E402  (on sys.path through the harness)


def _setup(tmp: Path):
    from brambleloop.creative import image_stages as S
    from brambleloop.creative import pattern_refs as P
    from brambleloop.products import moment_candidates as mc
    from brambleloop.visual import experiment as XP

    cir = mc.reading_nook_cable_wrap(H.VERSION)
    rel_hash = P.release_hash_of(cir)
    rel = S.release_from_cir(cir, release_hash=rel_hash, version=cir.version,
                             out_dir=tmp / "refs")
    budget = XP.ExperimentBudget(cap_cad=5.0)
    log: list = []
    renderer = H.BudgetedRenderer(H.stub_renderer_class()(), budget, live=False,
                                  per_role=1 + B.MAX_RETRIES, log=log)
    reg = {"slug": cir.slug, "version": cir.version, "release": rel_hash}
    outfit = {"outfit_id": "exp-test", "description": "a dusty-rose cardigan; dark jeans",
              "garments": {"top_or_dress": "dusty-rose knit cardigan", "lower": "dark jeans",
                           "shoes": "brown leather ankle boots", "outerwear": "none",
                           "accessories": "small gold hoops"}}
    return dict(cir=cir, rel=rel, budget=budget, renderer=renderer, reg=reg, outfit=outfit,
                log=log)


def _run(tmp, verifier, sources=("owner", "auto")):
    from brambleloop.visual import experiment as XP

    e = _setup(tmp)
    rep = B.run_baseline(db=None, cir=e["cir"], reg=e["reg"], rel=e["rel"],
                         renderer=e["renderer"], budget=e["budget"], outfit=e["outfit"],
                         out=tmp / "baseline", sources=sources, verifier=verifier,
                         label=XP.LABEL, flux_log=e["log"])
    return rep, e


def test_the_harness_dry_run_sends_the_owners_exact_six_then_the_auto_equivalents():
    out = Path(tempfile.mkdtemp(prefix="b6-dry-")) / "out"
    s = H.run(live=False, out=out, baseline=("owner", "auto"))
    assert s["mode"] == "dry-run baseline-six-ref" and s["spent_cad"] == 0.0
    assert [i["source"] for i in s["images"]] == ["owner", "auto"]
    assert s["images"][0]["transmitted_references"] == OWNER_SHAS
    auto = s["images"][1]["transmitted_references"]
    assert auto[:3] == OWNER_SHAS[:3] and len(auto) == 6 and auto[3:] != OWNER_SHAS[3:]
    assert all(i["verification"] == "UNKNOWN" for i in s["images"])   # no judge: never PASS
    assert s["retries_used"] == 0 and s["flux_calls"] == 2
    rep = json.loads((out / "baseline" / "baseline_report.json").read_text())
    assert rep["publishable"] is False and "EXPERIMENT" in rep["label"]
    first = rep["images"][0]
    assert first["certification"] == "UNCERTIFIED" and first["publishable"] is False
    for k in ("image", "prompt_file", "prompt_sha256", "provider_receipt", "cost_cad",
              "transmitted_references", "verification", "result"):
        assert k in first, k
    prompt = (out / "baseline" / first["prompt_file"]).read_text()
    assert hashlib.sha256(prompt.encode()).hexdigest() == first["prompt_sha256"]
    assert (out / "baseline" / first["image"]).is_file()
    assert "Transmitted references, in order" in (out / "baseline" /
                                                  "baseline_report.html").read_text()
    assert "certification" in s and s["certification"]                 # refused, recorded


def test_a_routed_fail_is_retried_at_most_twice_with_the_repair_negatives():
    tmp = Path(tempfile.mkdtemp(prefix="b6-retry-"))

    def failing(data, cand, outfit):
        return {"craft_texture": {"status": "FAIL", "codes": ["INVENTED_EDGING"],
                                  "why": "border seen"},
                "identity": {"status": "UNKNOWN", "why": "no judge"}}

    rep, e = _run(tmp, failing)
    attempts = [(i["source"], i["attempt"]) for i in rep["images"]]
    assert attempts == [("owner", 1), ("owner", 2), ("owner", 3), ("auto", 1)], attempts
    assert rep["retries_used"] == B.MAX_RETRIES == 2
    assert len(e["log"]) == 4                                          # 1 + 2 retries + 1
    assert rep["images"][1]["extra_negatives"] and "no edging" in rep["images"][1][
        "extra_negatives"]
    p2 = (tmp / "baseline" / rep["images"][1]["prompt_file"]).read_text()
    assert "no edging" in p2
    assert all(i["result"]["status"] == "FAIL" for i in rep["images"])
    assert rep["images"][0]["result"]["failed_codes"] == ["INVENTED_EDGING"]


def test_unknown_and_unrouted_failures_are_never_retried():
    tmp = Path(tempfile.mkdtemp(prefix="b6-unknown-"))

    rep, e = _run(tmp, lambda d, c, o: {"identity": {"status": "UNKNOWN", "why": "x"}},
                  sources=("owner",))
    assert len(rep["images"]) == 1 and rep["retries_used"] == 0
    tmp2 = Path(tempfile.mkdtemp(prefix="b6-unrouted-"))
    rep2, _ = _run(tmp2, lambda d, c, o: {"anatomy": {"status": "FAIL", "why": "six fingers"}},
                   sources=("owner",))
    assert len(rep2["images"]) == 1 and rep2["images"][0]["result"]["retryable"] is False
    tmp3 = Path(tempfile.mkdtemp(prefix="b6-count-"))
    rep3, _ = _run(tmp3, lambda d, c, o: {"fidelity": {"status": "FAIL",
                                                       "codes": ["UNVERIFIABLE_COUNT"]}},
                   sources=("owner",))
    assert len(rep3["images"]) == 1                     # verify-unfolded is not a retry


def test_the_owner_files_are_verified_by_bytes_and_order_is_fixed():
    assert [Path(p).name for p in B.owner_references()] == [n for _, n in B.OWNER_FILES]
    saved = B.OWNER_DIR
    tmp = Path(tempfile.mkdtemp(prefix="b6-tamper-"))
    shutil.copytree(saved, tmp / "d")
    p = tmp / "d" / "ref5_cable_stitch_structure.png"
    p.write_bytes(p.read_bytes() + b"x")
    try:
        B.OWNER_DIR = tmp / "d"
        try:
            B.owner_references()
            raise AssertionError("a tampered owner reference was accepted")
        except B.BaselineRefused:
            pass
    finally:
        B.OWNER_DIR = saved
    from brambleloop.creative import image_stages as S

    e = _setup(Path(tempfile.mkdtemp(prefix="b6-two-")))
    try:
        S.six_reference_lifestyle(e["rel"], B.owner_references()[:2], None,
                                  {"id": "o", "description": "d"},
                                  renderer=S.StubRenderer(), work_dir=str(tempfile.mkdtemp()))
        raise AssertionError("five references were accepted")
    except S.StageRefused:
        pass


def test_live_baseline_refuses_without_keys_before_anything_opens():
    saved = {k: os.environ.pop(k, None) for k in H.KEY_VARS}
    out = Path(tempfile.mkdtemp(prefix="b6-live-")) / "out"
    try:
        try:
            H.run(live=True, out=out, baseline=("owner", "auto"))
            raise AssertionError("live ran without keys")
        except H.Refused:
            pass
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert not out.exists()


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except BaseException as e:  # noqa: BLE001 - Refused is a SystemExit
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
