"""#29: which single thing failing would end this company, and whether that is a risk yet.

The requirement has two halves that pull against each other, and a module implementing only
the first is worse than none: it tells a pre-revenue company with one department to open a
second marketplace, and its one real advantage becomes five half-built ones. These tests are
mostly about the second half holding.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.scale import dependency as D  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/dep.sqlite")
    db.create_all()
    return db


def test_concentration_alone_is_not_a_finding():
    """A single marketplace nobody has sold on is a plan, not an existential dependency.

    Calling it existential would be alarming and wrong, and a risk report nobody believes is
    a risk report nobody reads.
    """
    plan = D.assess("marketplace", {"etsy": 4}, load_bearing=False)
    assert plan["verdict"] == D.PLAN, plan
    assert plan["share"] == 1.0
    assert "diversify *after*" in plan["why"]

    real = D.assess("marketplace", {"etsy": 4}, load_bearing=True)
    assert real["verdict"] == D.EXISTENTIAL, real
    assert "carries real weight" in real["why"]


def test_the_axis_that_is_genuinely_existential_today_says_so():
    """One model provider, and nothing in this system that needs judgement runs without it.

    This is the axis where the uncomfortable answer is the correct one, and a module that
    softened it would be useless in the one place it matters.
    """
    verdict = D.assess("ai_provider", {"anthropic": 1}, load_bearing=True)
    assert verdict["verdict"] == D.EXISTENTIAL
    assert verdict["largest"] == "anthropic"
    assert "stops every agent at once" in verdict["why"]


def test_a_spread_axis_is_sound_rather_than_praised():
    spread = D.assess("occasion", {"christmas": 4, "easter": 3, "everyday": 4}, 
                      load_bearing=True)
    assert spread["verdict"] == D.SOUND, spread
    assert spread["share"] < D.CONCENTRATED_ABOVE


def test_two_holders_is_still_concentrated_however_even_the_split():
    """A 50/50 split across two holders reads as spread and is one failure from total.

    The share test alone would pass it, which is why the holder count is checked as well.
    """
    pair = D.assess("ai_provider", {"a": 1, "b": 1}, load_bearing=True)
    assert pair["share"] == 0.5
    assert pair["verdict"] == D.SOUND, pair
    lone = D.assess("ai_provider", {"a": 1}, load_bearing=True)
    assert lone["verdict"] == D.EXISTENTIAL


def test_an_empty_axis_is_unmeasurable_rather_than_diversified():
    """"No traffic source is dominant" is true of a company with no traffic.

    It is also the single most misleading sentence such a company could publish about itself.
    """
    empty = D.assess("traffic_source", {}, load_bearing=False)
    assert empty["verdict"] == D.UNMEASURABLE
    assert "not the same as spread" in empty["why"]
    assert empty["share"] is None


def test_no_provider_configured_is_a_worse_state_than_concentration_and_says_which():
    """Zero providers is not "unknown concentration". Nothing runs at all."""
    report = D.report(_db())
    provider = next(a for a in report["axes"] if a["axis"] == "ai_provider")
    if provider["holders"] == 0:
        assert "nothing in this system that needs judgement can run" in provider["why"]
    else:
        assert provider["verdict"] == D.EXISTENTIAL


def test_holders_per_product_is_undefined_rather_than_fine_with_no_products():
    """The most spread-too-thin a company can be would otherwise report as fine.

    `False` here reads as "the spread is within what the catalogue supports" for a company
    carrying seven holders and nothing to put on them, which inverts the finding.
    """
    focus = D.report(_db())["focus"]
    assert focus["validated_products"] == 0
    assert focus["spread_too_thin"] is None, focus
    assert "has not been tested" in focus["why"]


def test_every_axis_names_what_would_make_it_load_bearing():
    """A risk that cannot say what would make it real is a mood."""
    for axis in D.AXES:
        assert axis.load_bearing_when.strip(), axis.key
        assert axis.why_it_ends_the_company.strip(), axis.key
    report = D.report(_db())
    assert {a["axis"] for a in report["axes"]} == {a.key for a in D.AXES}
    for row in report["axes"]:
        assert row["would_count_when"].strip(), row


def test_an_unknown_axis_is_refused_rather_than_scored():
    raised = None
    try:
        D.assess("vibes", {"good": 1}, load_bearing=True)
    except KeyError as e:
        raised = e
    assert raised is not None
    assert "not a dependency axis" in str(raised)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
