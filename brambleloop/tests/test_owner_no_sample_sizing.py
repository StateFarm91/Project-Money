"""D-OWNER-NO-SAMPLE-SIZING (owner, 2026-11-22: "Yes, sizes from math").

No sample will ever be made (D-OWNER-NO-SAMPLE). So:
- a primitive with a documented, conservative published stitch-dimension default (post
  stitches, cables, bobbles, the star family) is sized from standard gauge with that default,
  recorded as source `standard_gauge_default`, never as calibrated, and no longer raises
  UNCALIBRATED_PRIMITIVE;
- a Class C design whose every size is arithmetic from a stated, yarn-evidenced gauge no
  longer raises PHYSICAL_TEST_REQUIRED (a warning records it); one with no yarn evidence still
  does;
- the PDF and the listing copy say that sizes are calculated from standard gauge, and claim
  no test or make;
- deterministic validation still runs and still refuses what it refused.
Each test fails on the code before the ruling.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from brambleloop.cir import stitches as st  # noqa: E402
from brambleloop.cir.model import Op, Row  # noqa: E402
from brambleloop.gates import estimate_claims as ec  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402


def test_documented_primitives_carry_a_standard_gauge_default_never_calibration():
    table = st.calibration_table()
    for code in ("fpdc", "bpdc", "cable2x2", "cable1x1", "bob", "star_st", "hdc_inc"):
        assert table[code] == st.STANDARD_GAUGE, code
        d = st.standard_gauge_default(code)
        assert d["source"] == "standard_gauge_default" and "calibrat" not in d["source"]
        low, high = d["band_sc"]
        assert low <= d["row_height_sc"] <= high, (code, d)
        assert d["convention"], code
    assert st.CALIBRATED not in table.values()
    # Failing closed stays: a primitive with no documented default is uncalibrated.
    assert st.calibration_status("a-stitch-added-tomorrow") == st.UNCALIBRATED
    assert set(st.STANDARD_GAUGE_DEFAULTS) <= set(st.known_codes())


def _panel_with(row_ops):
    cir = fixtures.good_mosaic_panel()
    cir.components[0].rows.append(Row(index=len(cir.components[0].rows) + 1, ops=row_ops,
                                      declared_count=40, color="forest", turning_chain=1))
    return cir


def test_a_bobble_pattern_is_no_longer_blocked_as_an_uncalibrated_primitive():
    cert = certify(_panel_with([Op("sc", 19), Op("bob"), Op("sc", 20)]))
    codes = {f.code for f in cert.findings}
    assert "UNCALIBRATED_PRIMITIVE" not in codes, cert.blocking_reasons
    assert "PRIMITIVE_STANDARD_GAUGE_DEFAULT" in codes
    assert cert.primitives["uncalibrated"] == []
    assert cert.primitives["status"]["bob"] == st.STANDARD_GAUGE
    assert cert.primitives["standard_gauge_default"]["bob"]["source"] == "standard_gauge_default"
    assert cert.granted, cert.blocking_reasons
    # Deterministic validation still decides: a miscounted row is refused as before.
    bad = certify(_panel_with([Op("sc", 19), Op("bob"), Op("sc", 21)]))
    assert not bad.granted


def _class_c(material_weight: str | None):
    from brambleloop.cir.model import Gauge, Material
    from brambleloop.products import garments as G
    from brambleloop.cir import graded as GR

    fitted = GR.GradedDesign(
        key="fitted", title="Fitted", table=GR.WOMAN, gauge=Gauge(16, 18),
        fit=GR.FitIntent({"bust": 4, "back_length": 10, "armhole_depth": 3, "upper_arm": 4}),
        requires=G.DROP_SHOULDER_REQUIRES,
        template=lambda g: G.drop_shoulder_flat(
            g, key="fitted", title="Fitted Pullover", family=G.StitchFamily(),
            material=Material("wool", yarn_weight=material_weight)))
    return fitted.build("M")


def test_class_c_sizes_from_standard_gauge_instead_of_a_physical_test():
    from brambleloop.publish.substitution import WEIGHT_BY_KEY, holds_gauge

    weight = next(k for k, w in WEIGHT_BY_KEY.items() if holds_gauge(w, 16))
    cir = _class_c(weight)
    assert cir.risk_class == "C"
    cert = certify(cir)
    codes = {f.code for f in cert.findings}
    assert "PHYSICAL_TEST_REQUIRED" not in codes, cert.blocking_reasons
    assert "SIZES_FROM_STANDARD_GAUGE" in codes
    w = next(f for f in cert.findings if f.code == "SIZES_FROM_STANDARD_GAUGE")
    assert "nothing was tested or physically made" in w.message
    # With no yarn evidence behind the gauge, there is no standard gauge to size from.
    unevidenced = certify(_class_c(None))
    assert "PHYSICAL_TEST_REQUIRED" in {f.code for f in unevidenced.errors}


def test_the_listing_copy_and_pdf_state_sizes_are_calculated_from_standard_gauge():
    from test_estimate_claims import _coasters, _description

    cir, _result, twin, _docs, texts = _coasters()
    assert "calculated from standard gauge" in ec.STANDARD_GAUGE_NOTE
    assert set(texts) == {"US", "UK"}
    for terminology, text in texts.items():
        assert ec.STANDARD_GAUGE_NOTE in re.sub(r"\s+", " ", text), terminology
    copy = _description(cir, twin)
    assert ec.STANDARD_GAUGE_NOTE in copy
    # It claims arithmetic, never a test or a make.
    assert ec.physical_implications(ec.STANDARD_GAUGE_NOTE) == []
    assert not re.search(r"\b(tested|tester[- ]made|was made|measured)\b",
                         ec.STANDARD_GAUGE_NOTE, re.I)
    # A measured caller prints no estimate wording at all.
    assert ec.STANDARD_GAUGE_NOTE not in _description(cir, twin, size_is_estimate=False)


if __name__ == "__main__":
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and inspect.isfunction(f)]
    for n, f in tests:
        f()
        print(f"OK   {n}")
    print(f"{len(tests)} passed")
