"""F-198: the owned_surfaces gate names its acceptable surfaces and the requirement each
serves, and its owner card is held (not asked) until a listing is live."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.build2 import executor, gate_clearance as GC  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def test_gate_lists_acceptable_surfaces_and_why_each_requirement_needs_one():
    d = executor.GATE_BY_KEY["owned_surfaces"].to_dict()
    assert d["acceptable_surfaces"] == ["site", "pinterest", "email", "video"]
    assert "etsy_shop" not in d["acceptable_surfaces"]
    parked = {rid for rid, k in executor.gated_requirements().items() if k == "owned_surfaces"}
    assert parked and set(d["why_required"]) == parked == set(d["requirement_ids"])
    for rid, w in d["why_required"].items():
        assert w["needs"] and set(w["needs"]) <= set(d["acceptable_surfaces"]), rid
        assert w["etsy_satisfies"], rid


def test_card_is_held_until_a_listing_is_live_then_carries_why_required():
    db = _db()
    pre = GC.prerequisite(db, "owned_surfaces", env={})
    assert pre and "no listing is live" in pre and "#246" in pre
    inbox = executor.approval_inbox(db, env={})
    assert "owned_surfaces" not in [c.get("gate") for c in inbox["cards"]]
    held = [x for x in inbox.get("not_yet_askable") or [] if x["gate"] == "owned_surfaces"]
    assert held and held[0]["precondition"] == pre

    real = executor.GATE_BY_KEY["live_listings"].check
    executor.GATE_BY_KEY["live_listings"].check = lambda db, env=None: True
    try:
        assert GC.prerequisite(db, "owned_surfaces", env={}) is None
        f = GC.card_fields(db, "owned_surfaces", env={})
    finally:
        executor.GATE_BY_KEY["live_listings"].check = real
    assert f["requirement_ids"] == sorted(GC.OWNED_SURFACE_NEEDS)
    assert set(f["why_required"]) == set(GC.OWNED_SURFACE_NEEDS)
    assert f["acceptable_surfaces"] == list(GC.ACCEPTABLE_SURFACES)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
