"""ws5 LOWs N1-N3 on the E6 draft resolver (review 6957411211).

N1: a draft renamed by hand during the halt is never released as "not created".
N2: a listing row without its own `state` makes the read undecided; it is never tagged.
N3: one list of listing states, read by the census, manual adoption and the resolver.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
from datetime import timedelta

from sqlalchemy import select  # noqa: E402

from brambleloop.publish import draft_intent as DI  # noqa: E402
from brambleloop.publish import draft_resolver as R  # noqa: E402
from test_ws5_e6_draft_resolver import (NOW, _actions, _audit, _cards, _db, _draft,  # noqa: E402
                                        _incident, _stuck)


def _released(db, key):
    with db.session() as s:
        return s.get(DI.DraftIntent, key) is None


def test_n1_a_draft_renamed_inside_the_create_window_is_never_released():
    db = _db()
    key = _stuck(db)                                         # intent at NOW - 20 min
    renamed = _draft("9401", title="Renamed By Hand", created=NOW - timedelta(minutes=19))
    for minutes in (0, 31, 90):
        out = R.resolve(db, [renamed], audit=_audit(db), now=NOW + timedelta(minutes=minutes))
        assert [i["outcome"] for i in out["intents"]] == ["escalated"], out
    assert not _released(db, key) and not _actions(db, R.RELEASED)
    assert _incident(db).resolved is False
    assert _cards(db) and "9401" in str(_incident(db).detail.get("candidates"))


def test_n1_window_bounds_and_adoption_are_unchanged():
    # Created well outside the window under another title: still released after two reads.
    db = _db()
    key = _stuck(db)
    old = _draft("9402", title="Unrelated", created=NOW - timedelta(hours=3))
    late = _draft("9403", title="Unrelated", created=NOW + timedelta(minutes=5))
    R.resolve(db, [old, late], audit=_audit(db), now=NOW)
    out = R.resolve(db, [old, late], audit=_audit(db), now=NOW + timedelta(minutes=31))
    assert out["intents"][0]["outcome"] == "released", out
    assert _released(db, key)
    # One exact candidate plus a renamed one in the window: the exact one is still adopted.
    db = _db()
    _stuck(db)
    out = R.resolve(db, [_draft("9404"),
                         _draft("9405", title="Renamed", created=NOW - timedelta(minutes=19))],
                    audit=_audit(db), now=NOW)
    assert [i["outcome"] for i in out["intents"]] == ["adopted"], out
    # The window is the intent's time plus or minus CREATE_SKEW, edges included.
    started = NOW - timedelta(minutes=20)
    for offset, outcome in ((R.CREATE_SKEW, "escalated"), (-R.CREATE_SKEW, "escalated"),
                            (R.CREATE_SKEW + timedelta(minutes=1), "awaiting_second_read")):
        db = _db()
        _stuck(db)
        edge = _draft("9406", title="Renamed", created=started + offset)
        out = R.resolve(db, [edge], audit=_audit(db), now=NOW)
        assert out["intents"][0]["outcome"] == outcome, (offset, out)


def test_n2_a_row_without_state_makes_the_read_undecided():
    db = _db()
    key = _stuck(db)

    class Shop:
        credentials = object()

        def get_shop_listings(self, *, state, limit, max_pages):
            if state == "active":
                row = _draft("9501")
                row.pop("state")
                return [row]
            return []

    out = R.run(db, audit=_audit(db), client=Shop(), now=NOW + timedelta(minutes=31))
    assert out["read"] is False and "no state of their own" in out["why"], out
    with db.session() as s:
        row = s.get(DI.DraftIntent, key)
        assert row is not None and not (row.detail or {}).get("empty_reads")
    assert not _actions(db, R.ADOPTED) and not _actions(db, R.RELEASED)


def test_n2_a_stateless_row_is_never_adopted_as_a_draft():
    db = _db()
    key = _stuck(db)
    row = _draft("9502")
    row.pop("state")
    out = R.resolve(db, [row], audit=_audit(db), now=NOW)
    assert [i["outcome"] for i in out["intents"]] == ["escalated"], out
    with db.session() as s:
        assert s.get(DI.DraftIntent, key).remote_id is None


def test_n3_one_list_of_listing_states():
    from brambleloop.integrations import etsy as E
    from brambleloop.publish import manual_adoption as MA
    from brambleloop.runtime import etsy_ops as EO

    assert E.LISTING_STATES == ("draft", "active", "inactive", "expired", "sold_out")
    assert R.LISTING_STATES is E.LISTING_STATES
    assert EO.CENSUS_STATES is E.LISTING_STATES
    assert MA._KNOWN_STATES is E.LISTING_STATES


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{fails} failed")
