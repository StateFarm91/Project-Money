"""Additive schema migration (Master Plan section 13).

`Base.metadata.create_all` creates tables that do not exist. It does not touch tables that do,
so a column added in code never reaches a database that was created before it. On a laptop you
notice immediately; on a deployed service you get an `UndefinedColumn` at 3am, or worse, code
that quietly routes around the missing field.

This is the third instance of one underlying problem in this system, and naming it is the
point: **code changed, the deployed database did not.** The first was an agent permission that
lived in `DEFAULT_AGENTS` and never reached an existing row. The second was a pipeline upgrade
that could not reach products already certified. This is the schema version.

Deliberately additive only. It adds missing columns and nothing else — it will not drop a
column, narrow a type, rename anything, or alter data. Those are real migrations and they need
a human looking at them. What this covers is the common, safe, boring case that otherwise
breaks a deploy.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .db import Base

log = logging.getLogger("brambleloop.migrate")


class UnsafeMigration(RuntimeError):
    """A schema change this module will not make on its own."""


def plan(engine: Engine) -> list[tuple[str, str, str]]:
    """Columns the models declare that the database does not have.

    Returns (table, column, DDL type). Only nullable columns or columns with a default are
    included: adding a NOT NULL column with no default to a table that has rows cannot
    succeed, and pretending otherwise would turn a clear error into a confusing one.
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    out: list[tuple[str, str, str]] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue   # create_all handles this case
        have = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                raise UnsafeMigration(
                    f"{table.name}.{column.name} is NOT NULL with no default. Adding it to a "
                    f"table that already has rows cannot succeed, and this module will not "
                    f"guess a backfill value. Add a default, or write a real migration.")
            ddl = column.type.compile(dialect=engine.dialect)
            out.append((table.name, column.name, ddl))
    return out


def apply(engine: Engine) -> list[str]:
    """Add every missing column, then every missing index. Returns what changed.

    Indexes matter here as much as the columns. A column added without its index is a column
    that works in testing and degrades quietly under a table that has grown, which is the
    hardest kind of problem to attribute later.
    """
    changes: list[str] = []
    for table, column, ddl in plan(engine):
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
        changes.append(f"{table}.{column} {ddl}")
        log.info("added column %s.%s (%s)", table, column, ddl)

    if changes:
        insp = inspect(engine)
        existing_tables = set(insp.get_table_names())
        for table_obj in Base.metadata.sorted_tables:
            if table_obj.name not in existing_tables:
                continue
            have = {i["name"] for i in insp.get_indexes(table_obj.name)}
            for index in table_obj.indexes:
                if index.name in have:
                    continue
                index.create(bind=engine, checkfirst=True)
                changes.append(f"index {index.name}")
                log.info("created index %s", index.name)
    return changes
