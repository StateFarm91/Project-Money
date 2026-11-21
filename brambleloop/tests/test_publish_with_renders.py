"""D-OWNER-PUBLISH-WITH-RENDERS: no buyer-visible "rendering" label on FLUX frames, provenance
kept internally, the sample-photo rule waived only with the directive, and no copy may claim
a photographed, tested or hand-made sample."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import release_gates as RG  # noqa: E402
from brambleloop.publish import sample_photo as SP  # noqa: E402
from brambleloop.gates.asset_truth import AssetClass  # noqa: E402

JOBS = (el.DESIRE, el.COLOUR_CONTEXT, el.LIFESTYLE, el.ANGLE, el.DETAIL, el.SCALE)


@contextmanager
def directive(on: bool):
    real = SP.publish_with_renders
    SP.publish_with_renders = lambda: on
    try:
        yield
    finally:
        SP.publish_with_renders = real


def test_the_directive_is_recorded_in_the_shipped_decision_index():
    assert SP.publish_with_renders() is True
    assert SP.WAIVER == "owner_directed_without_attestation: D-OWNER-PUBLISH-WITH-RENDERS"


def test_flux_alt_text_carries_no_rendering_label_with_the_directive():
    with directive(True):
        for job in JOBS:
            alt = RG._gallery_alt_text(job)
            low = alt.lower()
            assert "render" not in low and "ai-assisted" not in low and "concept" not in low, alt
            assert "photo" not in low, alt          # and never claims to be a photograph
    with directive(False):
        assert all(el.CONCEPT_LABEL in RG._gallery_alt_text(j) for j in JOBS)


def test_provenance_label_is_still_recorded_internally():
    # The certificate's honesty_label for a generated frame is computed, not dropped.
    for job in (el.DESIRE, el.LIFESTYLE):
        lab = el.honesty_label(AssetClass.AI_LIFESTYLE_CONCEPT, job)
        assert lab["label"] == el.CONCEPT_LABEL and lab["required"] is True, lab
    assert el.GENERATED_MEDIA == frozenset({AssetClass.AI_LIFESTYLE_CONCEPT})


def test_false_sample_claims_in_copy_are_refused():
    for claim in ("Photo of my sample, crocheted and tested by me.",
                  "Every photo shows my tested sample.", "I made this blanket last week.",
                  "Pattern tested by testers.", "Made by me with love."):
        assert SP.copy_problems(claim, photographed_sample=False), claim
    for honest in ("A cosy two-colour baby blanket pattern.",
                   "The finished blanket is approx. 79 x 96 cm (calculated)."):
        assert not SP.copy_problems(honest, photographed_sample=False), honest


def test_a_mutation_that_drops_the_false_claim_check_is_killed():
    src = Path(SP.__file__).read_text()
    marker = "        found = sorted({m.group(0).lower() for m in _FALSE_SAMPLE_CLAIM.finditer(text)})"
    assert src.count(marker) == 1
    ns: dict = {"__name__": SP.__name__, "__package__": SP.__package__, "__file__": SP.__file__}
    exec(compile(src.replace(marker, "        found = []"), SP.__file__, "exec"), ns)
    assert not ns["copy_problems"]("Photo of my sample.", photographed_sample=False)
    assert SP.copy_problems("Photo of my sample.", photographed_sample=False)


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
