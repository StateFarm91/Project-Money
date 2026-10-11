"""Re-audit L-3 (INDEPENDENT_REAUDIT_7421ef6): missing indexes are created on every pass.

`migrate.apply` ran its index pass only when `changes` was non-empty, and only backfilled
columns were recorded. A release adding only nullable, no-default, indexed columns therefore
added the columns to an existing database without their indexes, and a database missing an
index for any other reason never got it back.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from brambleloop.core import migrate  # noqa: E402
from brambleloop.core.db import Base, Database  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4-auditfix-migrate-")


def _fresh():
    url = f"sqlite:///{_TMP}/{os.urandom(4).hex()}.sqlite"
    db = Database(url)
    assert db.create_all() == [], "a fresh database needed a migration"
    return url, db


def _nullable_no_default_indexed_column():
    """(table, column, index name) for a single-column index on a nullable, default-less column."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            cols = list(index.columns)
            if len(cols) != 1 or index.unique:
                continue
            c = cols[0]
            if c.nullable and c.default is None and c.server_default is None \
                    and not c.primary_key and not c.foreign_keys:
                return table.name, c.name, index.name
    raise AssertionError("no nullable, default-less indexed column in the models")


def test_a_no_default_column_comes_back_with_its_index():
    url, db = _fresh()  # registers every model module's tables first
    table, column, index = _nullable_no_default_indexed_column()
    assert migrate._scalar_default(table, column) is None
    with db.engine.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{index}"'))
        conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{column}"'))
    again = Database(url)
    changes = again.create_all()
    insp = inspect(again.engine)
    assert column in {c["name"] for c in insp.get_columns(table)}, changes
    assert index in {i["name"] for i in insp.get_indexes(table)}, \
        f"{table}.{column} came back without its index {index}: {changes}"
    assert any(f"index {index}" == c for c in changes), changes
    assert Database(url).create_all() == [], "the migration is not idempotent"


def test_a_missing_index_alone_is_recreated():
    url, db = _fresh()
    table, _column, index = _nullable_no_default_indexed_column()
    with db.engine.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{index}"'))
    changes = migrate.apply(Database(url).engine)
    assert changes == [f"index {index}"], changes
    assert index in {i["name"] for i in inspect(db.engine).get_indexes(table)}


if __name__ == "__main__":
    fails = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("OK  ", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    import traceback
                    traceback.print_exc()
                    print("FAIL", name, repr(e))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"{fails} failing")
    sys.exit(1 if fails else 0)
