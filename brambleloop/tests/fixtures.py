"""Shared CIR fixtures for the acceptance suite (Gate B).

`good_sphere` and `good_mosaic_panel` are known-good. The `broken_*` builders return CIRs
with exactly one deliberate defect each, so a test can assert the compiler catches that
specific defect rather than failing for an unrelated reason.
"""
from __future__ import annotations

from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Provenance, Repeat, Row


def _own(key: str) -> Provenance:
    """The design provenance a known-good Brambleloop fixture carries.

    F-783/F-798: certification refuses a Brambleloop-authored release without a complete
    provenance record, so a fixture that is meant to certify has to have one -- exactly as
    every catalogue product now does.
    """
    return Provenance(concept_key=key, brief_digest=f"fixture-{key}",
                      primitives_used=("tests.fixtures",), benchmarks_consulted=(),
                      generated_by="brambleloop")


def good_sphere() -> CIR:
    """Classic amigurumi hemisphere: 6 sc in a magic ring, then standard increase rounds."""
    rows = [
        Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream",
            note="6 sc in magic ring"),
        Row(index=2, ops=[Repeat([Op("inc")], times=6)], declared_count=12, color="cream"),
        Row(index=3, ops=[Repeat([Op("sc"), Op("inc")], times=6)], declared_count=18, color="cream"),
        Row(index=4, ops=[Repeat([Op("sc", 2), Op("inc")], times=6)], declared_count=24, color="cream"),
        Row(index=5, ops=[Repeat([Op("sc", 3), Op("inc")], times=6)], declared_count=30, color="cream"),
        Row(index=6, ops=[Op("sc", 30)], declared_count=30, color="cream"),
        Row(index=7, ops=[Repeat([Op("sc", 3), Op("dec")], times=6)], declared_count=24, color="cream"),
    ]
    return CIR(
        slug="test-sphere",
        title="Test Sphere",
        version="1.0.0",
        construction="spiral_rounds",
        risk_class="B",
        colors={"cream": "#FAF6EB"},
        gauge=Gauge(stitches_per_10cm=20, rows_per_10cm=22, stitch_type="sc", hook_mm=3.5),
        # Sport weight, because 20 sc/10cm is a sport-weight fabric (band 16-20): worsted's
        # band is 11-14 and a worsted declaration here is refused at certification (F-112).
        materials=[Material(name="sport cotton", yarn_weight="sport", color_id="cream")],
        components=[
            Component(name="body", construction="spiral_rounds", rows=rows,
                      foundation=0, foundation_kind="magic_ring")
        ],
        provenance=_own("test-sphere"),
    )


def good_mosaic_panel() -> CIR:
    """Flat two-colour panel worked on a 40-stitch foundation with a to-end repeat."""
    rows = [
        Row(index=1, ops=[Op("sc", 40)], declared_count=40, color="forest",
            turning_chain=1, into=None),
        Row(index=2, ops=[Repeat([Op("sc", 3), Op("dc")], times=None)], declared_count=40,
            color="wine", turning_chain=1),
        Row(index=3, ops=[Op("sc", 40)], declared_count=40, color="forest", turning_chain=1),
        Row(index=4, ops=[Repeat([Op("dc"), Op("sc", 3)], times=None)], declared_count=40,
            color="wine", turning_chain=1),
    ]
    return CIR(
        slug="test-mosaic",
        title="Test Mosaic Panel",
        version="1.0.0",
        construction="flat_rows",
        risk_class="A",
        colors={"forest": "#244A3A", "wine": "#6E1F2A"},
        # The yarn the gauge is evidenced by (F-116): 16 sc/10cm is inside the DK band.
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=14, stitch_type="sc", hook_mm=5.0,
                    yarn_weight="dk"),
        components=[
            Component(name="panel", construction="flat_rows", rows=rows, foundation=40)
        ],
        provenance=_own("test-mosaic"),
    )


def broken_stitch_count() -> CIR:
    """Round 4 claims 23 stitches but the maths produces 24."""
    cir = good_sphere()
    cir.components[0].rows[3].declared_count = 23
    return cir


def broken_repeat() -> CIR:
    """A to-end repeat of 4 stitches over a 30-stitch round: 30 is not divisible by 4."""
    cir = good_sphere()
    cir.components[0].rows[5] = Row(
        index=6,
        ops=[Repeat([Op("sc", 3), Op("inc")], times=None)],
        declared_count=30,
        color="cream",
    )
    return cir


def broken_overrun() -> CIR:
    """Round 6 works 34 stitches into a round that only has 30."""
    cir = good_sphere()
    cir.components[0].rows[5] = Row(index=6, ops=[Op("sc", 34)], declared_count=34, color="cream")
    return cir


def broken_underrun() -> CIR:
    """Round 6 works only 28 of the 30 available stitches without declaring a remainder."""
    cir = good_sphere()
    cir.components[0].rows[5] = Row(index=6, ops=[Op("sc", 28)], declared_count=28, color="cream")
    return cir


def broken_unknown_color() -> CIR:
    cir = good_mosaic_panel()
    cir.components[0].rows[1].color = "chartreuse"
    return cir


# ---- F-112 / F-116 / F-074: the product-truth refusals -------------------------------------
#
# The Build-1 catalogue and the Launch-0 vessels declare yarn weights whose published bands
# cannot hold their typed gauges (worsted at 16-18 sc/10cm against a band of 11-14), and the
# texture designs use primitives no sample has calibrated. Certification refuses those now;
# the fix belongs in the product modules (declare the weight that holds the gauge, or derive
# the gauge from the yarn), not in the gate. Tests whose subject is some *other* stage of the
# chain assert that stage through this helper: every error on the certificate must be one of
# these, so a regression anywhere else in the chain still fails the test, and the day a
# product is re-authored the same assertion holds with the certificate granted.
PRODUCT_TRUTH_CODES: frozenset[str] = frozenset({
    "GAUGE_OUTSIDE_DECLARED_YARN_BAND", "GAUGE_WITHOUT_YARN_EVIDENCE", "UNCALIBRATED_PRIMITIVE",
})


def clean_but_for_product_truth(cert) -> bool:
    """Granted, or refused only by the product-truth gates above (never by anything else)."""
    return cert.granted or {f.code for f in cert.errors} <= PRODUCT_TRUTH_CODES
