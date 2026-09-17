"""Backup and restore with a verification drill (Master Plan section 28, Gate A).

"A backup that has never been restored is unproven." So `drill()` does not merely write a
file -- it restores into a scratch database and compares row counts, which is the only way to
learn that a backup is unusable *before* needing it.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from .db import Base, Database, is_postgres


@dataclass
class BackupResult:
    path: Path
    table_counts: dict[str, int]
    bytes_written: int
    created_at: datetime


@dataclass
class DrillResult:
    ok: bool
    backup: BackupResult
    restored_counts: dict[str, int]
    mismatches: dict[str, tuple[int, int]]

    def __str__(self) -> str:
        if self.ok:
            total = sum(self.restored_counts.values())
            return f"restore drill passed: {total} rows across {len(self.restored_counts)} tables"
        return f"restore drill FAILED: {self.mismatches}"


def _table_counts(db: Database) -> dict[str, int]:
    out: dict[str, int] = {}
    with db.session() as s:
        for table in Base.metadata.sorted_tables:
            out[table.name] = s.scalar(select(func.count()).select_from(table)) or 0
    return out


def backup(db: Database, dest_dir: str | Path) -> BackupResult:
    """Write a restorable snapshot plus a manifest of expected row counts."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counts = _table_counts(db)

    url = str(db.engine.url)
    if is_postgres(db.engine):
        path = dest / f"brambleloop-{stamp}.sql"
        subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", "-f", str(path), url],
            check=True, capture_output=True,
        )
    else:
        path = dest / f"brambleloop-{stamp}.sqlite"
        # sqlite3's online backup API is consistent even while the source is in use, unlike a
        # naive file copy.
        src = sqlite3.connect(db.engine.raw_connection().driver_connection.execute(
            "PRAGMA database_list").fetchone()[2] or ":memory:")
        try:
            out = sqlite3.connect(str(path))
            with out:
                src.backup(out)
            out.close()
        finally:
            src.close()

    manifest = path.with_suffix(path.suffix + ".manifest.json")
    manifest.write_text(json.dumps({"created_at": stamp, "counts": counts}, indent=2))

    return BackupResult(
        path=path,
        table_counts=counts,
        bytes_written=path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )


def drill(db: Database, work_dir: str | Path) -> DrillResult:
    """Back up, restore into a scratch database, and prove the row counts survived."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    result = backup(db, work)

    restored_path = work / "restore-check.sqlite"
    if restored_path.exists():
        restored_path.unlink()

    if is_postgres(db.engine):
        # Restoring a Postgres dump needs a live scratch database; that is an integration
        # concern, so the drill is explicit about not having verified it.
        return DrillResult(
            ok=False,
            backup=result,
            restored_counts={},
            mismatches={"_postgres": (0, 0)},
        )

    shutil.copy(result.path, restored_path)
    restored = Database(f"sqlite:///{restored_path}")
    restored_counts = _table_counts(restored)

    mismatches = {
        t: (result.table_counts.get(t, 0), restored_counts.get(t, 0))
        for t in set(result.table_counts) | set(restored_counts)
        if result.table_counts.get(t, 0) != restored_counts.get(t, 0)
    }
    return DrillResult(
        ok=not mismatches,
        backup=result,
        restored_counts=restored_counts,
        mismatches=mismatches,
    )
