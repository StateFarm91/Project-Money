"""W3 lane F: the canonical, provider-independent Laura Voice spec (D-FB-16 item 8) and the
qualification a replacement provider/voice must pass before it may speak as Laura.

* the spec covers every dimension the owner named and is pinned (v1 is never edited in place);
* a candidate passes only on MEASURED readings, sampled enough, inside every target, with the
  full pronunciation lexicon;
* estimates, provider descriptions, drift on any one dimension, a real-person clone without
  consent, or a claim to the GATED private register all FAIL;
* promotion is never automatic: it lists the owner decisions still needed.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_voice_spec.py
"""
from __future__ import annotations

import copy
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.laura.agency import voice_spec as V  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402

PINNED = "4c5ab12b2975a0269cde6d4ea13d985c3eab252a3cdf953c5a19edc420585b2b"   # v2, D-FB-18
PINNED_V1 = "08f98c00318bef946ca3a7d6727f23288c09800c0b6695ac3386908613a6ca53"


def _m(value, samples=30, method="praat f0 + forced alignment over 30 business sentences"):
    return {"value": value, "reading": "MEASURED", "method": method, "samples": samples}


def _panel(value):
    return _m(value, samples=7, method="blind listener panel, n=7")


def good_eval() -> dict:
    return {"median_f0_hz": _m(190), "f0_range_semitones": _m(6.5),
            "words_per_minute": _m(155), "pause_ms_between_sentences": _m(420),
            "warmth_panel": _panel(4.3), "energy_panel": _panel(3.2),
            "apparent_age_years": _panel(33), "accent": _panel("en-CA"),
            "timbre": _panel("warm"), "breathiness": _panel("low"),
            "pronunciation_accuracy": _m(1.0),
            "pronunciation_items": {w: True for w in V.SPEC["pronunciation"]["lexicon"]}}


CAND = {"provider": "provider-x", "voice_ref": "voice-17", "cloned_from_real_person": False,
        "registers": ["business"]}


def test_spec_covers_every_owner_dimension_and_is_pinned():
    s = V.SPEC
    for k in ("vocal_character", "accent_dialect", "apparent_age", "warmth", "pace", "energy",
              "rhythm", "pronunciation", "registers", "pitch"):
        assert k in s, k
    assert set(s["registers"]) == {"business", "private_owner"}
    assert s["registers"]["business"]["status"] == "ACTIVE"
    assert s["registers"]["private_owner"]["status"] == "GATED"
    assert s["identity_id"] == canonical.IDENTITY_ID          # the same Laura
    assert s["spec_id"] == "laura-voice-v2" and s["decision_id"] == "D-FB-18"
    assert s["owner_confirmation"].startswith("CONFIRMED")
    assert V.SPEC_SHA256 == V.spec_sha256() == PINNED, V.spec_sha256()
    assert V.SUPERSEDED["laura-voice-v1"][0] == PINNED_V1       # history kept, pinned


def test_v2_carries_the_owner_d_fb_18_direction():
    s = V.SPEC
    assert s["apparent_age"]["range_years"] == [30, 34] and s["apparent_age"]["target_years"] == 32
    assert s["accent_dialect"]["allowed"] == ["en-CA", "en-US-general"]
    assert s["accent_dialect"]["intensity"] == "subtle"
    vc = s["vocal_character"]
    for w in ("distinctly feminine", "warm", "intelligent", "confident", "charismatic",
              "attractive", "magnetic", "smooth", "expressive"):
        assert w in vc["positive"], w
    for w in ("forced seduction", "exaggerated breathiness", "pornographic performance",
              "cartoonish sensuality", "fake whispering", "childish or youthful delivery",
              "character acting"):
        assert w in vc["excluded_performance"], w
    for w in ("corporate narrator", "customer-service script", "radio announcer",
              "generic AI-assistant cadence", "robotic TTS rhythm", "over-polished delivery"):
        assert w in vc["excluded_cadence"], w
    for w in ("natural pauses", "thinking cadence", "humour", "amusement", "seriousness",
              "excitement", "reactions", "pacing changes"):
        assert w in s["prosody"]["natural_conversational"], w
    assert "ONE canonical voice" in s["one_voice"]
    assert set(s["registers"]) == {"business", "private_owner"}   # contexts, not voices
    priv = s["registers"]["private_owner"]
    assert priv["status"] == "GATED" and "prosody" in priv["delivery"]
    assert any("PRIV" in r for r in priv["requires"]) and any("provider" in r
                                                             for r in priv["requires"])
    assert "flirtation or intimacy" in s["registers"]["business"]["forbidden"]
    for k in V.REQUIRED_READINGS:                              # every reading has a target
        assert V._target(k)


def test_a_conforming_measured_voice_qualifies():
    q = V.qualify(CAND, good_eval())
    assert q["verdict"] == "PASS", q["failures"]
    assert q["spec_sha256"] == PINNED and len(q["checks"]) >= len(V.REQUIRED_READINGS)


def test_drift_on_any_single_dimension_fails():
    drifts = {"median_f0_hz": _m(240), "words_per_minute": _m(190),
              "energy_panel": _panel(4.6), "apparent_age_years": _panel(38),
              "accent": _panel("en-GB-rp"), "breathiness": _panel("high"),
              "pause_ms_between_sentences": _m(90), "pronunciation_accuracy": _m(0.9)}
    assert drifts
    for k, bad in drifts.items():
        ev = good_eval()
        ev[k] = bad
        q = V.qualify(CAND, ev)
        assert q["verdict"] == "FAIL" and any(f["check"] == k for f in q["failures"]), (k, q)
    ev = good_eval()
    ev["pronunciation_items"]["crochet"] = False
    assert V.qualify(CAND, ev)["verdict"] == "FAIL"


def test_estimates_descriptions_and_thin_samples_never_pass():
    for mutate in (lambda e: e.__setitem__("warmth_panel", {"value": 4.5, "reading": "ESTIMATED",
                                                            "method": "vendor page",
                                                            "samples": 50}),
                   lambda e: e.pop("median_f0_hz"),
                   lambda e: e.__setitem__("words_per_minute", _m(150, samples=3)),
                   lambda e: e.__setitem__("timbre", {"value": "warm", "reading": "MEASURED",
                                                      "samples": 9}),     # no method
                   lambda e: e.pop("pronunciation_items")):
        ev = good_eval()
        mutate(ev)
        assert V.qualify(CAND, ev)["verdict"] == "FAIL"


def test_real_person_clone_needs_consent_and_private_register_is_gated():
    clone = {**CAND, "cloned_from_real_person": True}
    q = V.qualify(clone, good_eval())
    assert q["verdict"] == "FAIL" and q["failures"][0]["check"] == "real_person_consent", q
    assert V.qualify({**clone, "consent_record": "consent:ref-1"}, good_eval())["verdict"] \
        == "PASS"
    unstated = {k: v for k, v in CAND.items() if k != "cloned_from_real_person"}
    assert V.qualify(unstated, good_eval())["verdict"] == "FAIL"
    priv = {**CAND, "registers": ["business", "private_owner"]}
    q = V.qualify(priv, good_eval())
    assert any(f["check"] == "private_register_gated" for f in q["failures"]), q
    assert V.qualify({**CAND, "registers": ["sultry"]}, good_eval())["verdict"] == "FAIL"


def test_promotion_is_never_automatic_and_public_view_hides_private_detail():
    q = V.qualify(CAND, good_eval())
    pr = V.promotion_requirements(q)
    assert pr["may_promote"] is False and pr["qualification"] == "PASS"
    assert any("owner listening decision" in r for r in pr["requires"])
    pv = V.public_view()
    assert set(pv["registers"]["private_owner"]) == {"status", "why_gated"}
    assert pv["spec_sha256"] == PINNED
    original = copy.deepcopy(V.SPEC)
    pv["pace"]["words_per_minute"] = [1, 999]                  # a copy, not the spec
    assert V.SPEC == original


if __name__ == "__main__":
    t0, fails = time.monotonic(), 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {e}"[:1500], flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
