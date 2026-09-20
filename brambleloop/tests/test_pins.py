"""#246: a pin set that is genuinely several pins.

The requirement says "avoid spammy duplicate pins" and the mechanism is not about images.
Five pins that differ in crop, overlay and filter are one pin posted five times, and they
are indistinguishable from five pins to any check that looks at the file. What makes two
pins different is what they are about.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.growth import pins as P  # noqa: E402
from brambleloop.seasonal.calendar import MILESTONES  # noqa: E402


def _pin(angle, **over):
    base = dict(product_slug="winter-throw", angle=angle,
                destination="https://example.invalid/listing/1",
                keywords=("crochet throw", "chunky blanket"), board="Throws")
    base.update(over)
    return P.Pin(**base)


# --- what makes two pins different --------------------------------------------------------

def test_a_crop_is_not_an_angle():
    for not_a_pin in ("different_crop", "text_overlay", "filtered", "vertical"):
        try:
            _pin(not_a_pin)
        except P.PinRefused as exc:
            assert "what they are about" in str(exc), not_a_pin
        else:  # pragma: no cover
            raise AssertionError(f"{not_a_pin} was accepted as an angle")


def test_one_pin_posted_three_times_is_not_a_set():
    out = P.check_set([_pin("finished_object") for _ in range(3)])
    assert out["ok"] is False
    assert any("posted five times" in r for r in out["reasons"])
    assert any("offered twice" in r for r in out["reasons"])


def test_three_different_reasons_to_save_it_are_a_set():
    out = P.check_set([_pin("finished_object"), _pin("fabric_detail"), _pin("in_a_room")])
    assert out["ok"] is True
    assert out["angles"] == ["fabric_detail", "finished_object", "in_a_room"]
    assert "gift_framing" in out["unused_angles"]


def test_more_pins_than_reasons_to_save_one_is_repetition():
    pins = [_pin(a) for a in P.ANGLES]
    pins.append(_pin("finished_object"))
    out = P.check_set(pins)
    assert any("repeating whatever they are called" in r for r in out["reasons"])


def test_a_pin_with_nowhere_to_land_is_a_leaflet():
    out = P.check_set([_pin("finished_object", destination=" "), _pin("fabric_detail"),
                       _pin("in_a_room")])
    assert any("a leaflet" in r for r in out["reasons"])


def test_a_pin_nothing_files_is_a_pin_nobody_finds():
    out = P.check_set([_pin("finished_object", keywords=()), _pin("fabric_detail"),
                       _pin("in_a_room")])
    assert any("nobody searching finds them" in r for r in out["reasons"])


def test_every_angle_says_what_it_is_for():
    assert len(P.ANGLES) == 7
    for angle, why in P.ANGLES.items():
        assert len(why.split()) >= 5, angle


# --- the schedule is about the shopping window -------------------------------------------------

def test_pins_go_up_when_the_listing_is_indexed_not_when_the_occasion_arrives():
    out = P.schedule(event_date=date(2026, 12, 25), today=date(2026, 9, 20))
    assert out["publish_on"] == "2026-09-26"       # 90 days before
    assert out["ramp_on"] == "2026-10-26"          # 60 days before
    assert out["late"] is False
    assert "after the decision" in out["why"]


def test_the_dates_are_the_calendars_own():
    """A second set of seasonal dates is a second answer to when the work is late."""
    calendar = {name: days for name, days, _ in MILESTONES}
    assert P.MILESTONE_DAYS[P.PUBLISH_AT_MILESTONE] == calendar["listing_indexing_date"]
    assert P.MILESTONE_DAYS[P.RAMP_AT_MILESTONE] == calendar["promotional_ramp"]


def test_a_schedule_past_its_publication_date_says_it_is_late():
    out = P.schedule(event_date=date(2026, 10, 31), today=date(2026, 9, 20))
    assert out["late"] is True
    assert "already late" in out["why"]


# --- amplifying a winner -------------------------------------------------------------------------

def test_amplifying_a_winner_means_another_angle():
    existing = [_pin("finished_object"), _pin("fabric_detail")]
    out = P.amplify(existing[0], existing)
    assert "finished_object" not in out["next_angles"]
    assert "in_a_room" in out["next_angles"]
    assert "door marked success" in out["note"]


def test_when_every_angle_is_used_the_next_thing_is_not_a_pin():
    pins = [_pin(a) for a in P.ANGLES]
    out = P.amplify(pins[0], pins)
    assert out["next_angles"] == []
    assert "supporting content rather than another pin" in out["note"]


def test_state_says_what_cannot_be_done_yet():
    out = P.state()
    assert set(out["cannot_do_yet"]) == {"images", "destinations", "attribution"}
    assert "nobody has granted" in out["cannot_do_yet"]["images"]
    assert len(out["not_a_different_pin"]) == 4


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
