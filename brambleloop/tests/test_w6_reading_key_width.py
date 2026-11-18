"""W6 P0-VIS: a release-keyed operating reading fits its column on PostgreSQL.

`publish.listing_package` keys its reading `f"{slug}@{version}"`: an 80-character
`Product.slug`, '@', and a 20-character `PatternVersion.version`, so up to 101 characters.
`OperatingReading.period_key` was VARCHAR(20). SQLite never enforces a VARCHAR length, so
every SQLite suite passed while PostgreSQL refused the insert for any slug@version longer
than 20 characters (StringDataRightTruncation), failing the six-hourly `listing.package`
sweep. Ported from Codex commit 61418af0 (independent A9 review 2026-11-17 recommended it
on its own); `core.migrate.widen` applies the wider VARCHAR to an existing PostgreSQL
column at startup.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import String  # noqa: E402

from brambleloop.core import migrate  # noqa: E402
from brambleloop.core.models import OperatingReading, PatternVersion, Product  # noqa: E402


def _len(col) -> int:
    assert isinstance(col.type, String), col
    return int(col.type.length)


def test_period_key_holds_the_longest_release_key():
    longest = (_len(Product.__table__.c.slug) + 1
               + _len(PatternVersion.__table__.c.version))
    assert _len(OperatingReading.__table__.c.period_key) >= longest, longest


def test_widen_plans_the_old_postgres_column():
    """The real planner, against the prior PostgreSQL shape, widens period_key."""
    import types

    class OldVarchar(String):
        pass

    class FakeInspector:
        def get_table_names(self):
            return [OperatingReading.__table__.name]

        def get_columns(self, table):
            cols = []
            for c in OperatingReading.__table__.columns:
                t = OldVarchar(20) if c.name == "period_key" else c.type
                cols.append({"name": c.name, "type": t})
            return cols

    engine = types.SimpleNamespace(dialect=types.SimpleNamespace(name="postgresql"))
    real = migrate.inspect
    migrate.inspect = lambda _e: FakeInspector()
    try:
        plan = migrate.widen_plan(engine)
    finally:
        migrate.inspect = real
    want = _len(OperatingReading.__table__.c.period_key)
    assert (OperatingReading.__table__.name, "period_key", 20, want) in plan, plan


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
