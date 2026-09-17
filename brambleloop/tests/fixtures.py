"""Shared CIR fixtures for the acceptance suite (Gate B).

`good_sphere` and `good_mosaic_panel` are known-good. The `broken_*` builders return CIRs
with exactly one deliberate defect each, so a test can assert the compiler catches that
specific defect rather than failing for an unrelated reason.
"""
from __future__ import annotations

from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row


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
        materials=[Material(name="worsted cotton", yarn_weight="worsted", color_id="cream")],
        components=[
            Component(name="body", construction="spiral_rounds", rows=rows,
                      foundation=0, foundation_kind="magic_ring")
        ],
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
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=14, stitch_type="sc", hook_mm=5.0),
        components=[
            Component(name="panel", construction="flat_rows", rows=rows, foundation=40)
        ],
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
