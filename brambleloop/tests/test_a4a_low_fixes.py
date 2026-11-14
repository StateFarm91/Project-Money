"""The A4a LOW list from Main's A4a verdict (6590805732).

* Originality reads title variants: plural, hyphenation, fullwidth letters and case all
  name the same title. It uses the shared title fold plus stemming.
* A listing dated after today is not an observation.
* The evidence floor holds for the object chosen, not only for the whole pod.
* The surviving mutants are pinned: the originality threshold, the date filter, the window,
  the per-gap task guard and the stall length.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_a4a_low_fixes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.radar import ideation as I  # noqa: E402
import test_w5_a4a_research_to_concept as T  # noqa: E402

TODAY = date.today()
POD = "kitchen_bath"


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.audits = []

    def audit(self, action, **kw):
        self.audits.append(action)

    def enqueue(self, *a, **k):
        return None


def test_originality_refuses_plural_hyphen_fullwidth_and_case_variants():
    ours = "Linen Ridge Dishcloth"
    for variant in ("LINEN RIDGE DISHCLOTHS", "Linen-Ridge Dishcloth",
                    "Linen‑Ridge Dish-cloth",
                    "Ｌｉｎｅｎ Ｒｉｄｇｅ Dishcloths"):
        why = I.originality_reasons(ours, "Zz", [("r1", variant)])
        assert why and "equals" in why[0], (variant, why)
    assert I.originality_reasons(ours, "Zz", [("r2", "Farmhouse Washcloth")]) == []
    assert I.title_words("Doilies Boxes Patterns") == ["doily", "box", "pattern"]
    assert I.title_words("This Glass") == ["this", "glass"]


def test_the_originality_threshold_is_pinned_at_half():
    assert I.ORIGINALITY_OVERLAP == 0.5
    ours = "Linen Ridge Dishcloth"                      # specific: linen ridge dishcloth
    half = I.originality_reasons(ours, "Zz", [("r1", "Linen Dishcloth Mesh")])     # 2/4
    below = I.originality_reasons(ours, "Zz", [("r2", "Linen Dishcloth Mesh Grid")])  # 2/5
    assert half and "overlaps" in half[0], half
    assert below == [], below


def test_future_dated_listings_and_the_window_edges_are_pinned():
    assert I.OBSERVATION_WINDOW_DAYS == 90
    rows = [(f"shop-{i}", f"Cotton Dishcloth {i}", 6.0) for i in range(3)]
    db = T._db()
    T._listings(db, POD, rows, days_ago=-3)             # dated three days from now
    assert I.observe(db, POD, today=TODAY)["listings"] == 0
    db = T._db()
    T._listings(db, POD, rows, days_ago=89)             # inside the window
    assert I.observe(db, POD, today=TODAY)["listings"] == 3
    db = T._db()
    T._listings(db, POD, rows, days_ago=92)             # outside it
    assert I.observe(db, POD, today=TODAY)["listings"] == 0


def test_the_floor_holds_for_the_chosen_object():
    db = T._db()
    T._listings(db, POD, [("shop-a", "Cotton Dishcloth", 6.0),
                          ("shop-a", "Scrubby Dishcloth", 6.5),
                          ("shop-b", "Granny Potholder", 7.0),
                          ("shop-c", "Bath Mat", 9.0),
                          ("shop-c", "Soap Saver", 4.0)])
    obs = I.observe(db, POD, today=TODAY)
    assert obs["listings"] == 5 and obs["shops"] == 3, obs  # the pod clears the floor
    assert obs["ok"] is False, obs
    assert any("dishcloth listing(s), below" in r for r in obs["reasons"]), obs["reasons"]
    assert any("shop(s) sell a dishcloth, below" in r for r in obs["reasons"]), obs["reasons"]
    # The fixture the main suite uses clears it: four dishcloths across three shops.
    db = T._db()
    T._listings(db, POD, T.KITCHEN)
    assert I.observe(db, POD, today=TODAY)["ok"] is True


def test_a_gap_with_a_task_is_never_given_a_second_brief():
    db = T._db()
    gid = T._gap(db, POD)
    T._listings(db, POD, T.KITCHEN)
    gap = {"gap": gid, "pod": POD, "arena": f"watchlist:{POD}"}
    first = I.open_briefs(_Ctx(db), [gap], today=TODAY)
    assert first["opened"] and not first["already"], first
    second = I.open_briefs(_Ctx(db), [gap], today=TODAY)
    # Research dedupes identical questions, so a missing guard would be masked by the task
    # count; the guard's own outcome is what is pinned.
    assert second["already"] == [gid] and not second["opened"], second
    assert len(T._tasks(db)) == 1


def test_the_stall_length_is_pinned_at_fourteen_days():
    assert I.STALL_DAYS == 14
    db = T._db()
    opened = datetime(2026, 11, 1, tzinfo=timezone.utc)
    rec = {"task": 1, "opened_at": opened.isoformat()}
    assert I.status(db, rec, now=opened + timedelta(days=13))[0] == "in_flight"
    assert I.status(db, rec, now=opened + timedelta(days=15)) == ("done", "stalled")


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
