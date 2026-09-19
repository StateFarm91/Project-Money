"""Business continuity: a portable export of the state that cannot be rebuilt from code.

Requirements 50, 51 and 184, and the gap Build 1 found in its own baseline: the production
database was not backed up from the application environment, and the existing restore drill
is honest that it has never verified a *Postgres* restore -- it needs a live scratch database,
so `drill()` returns ok=False rather than pretending.

This closes that without needing one. Two ideas do the work:

**Portable, not native.** `pg_dump` output restores into Postgres and nowhere else, which is
exactly the dependency #51 says to remove: "the company must be reconstructable if a SaaS
provider disappears." So the export is plain JSON Lines per table -- readable by anything,
restorable into SQLite, Postgres or a spreadsheet. The native dump remains available and
complementary; this is the one that survives losing the vendor.

**Provable.** Because the format is engine-independent, a Postgres export can be restored
into a scratch SQLite database and compared row by row, which means the restore is
*demonstrated* rather than assumed. A backup nobody has restored is a hope.

What is worth preserving, from the Build-1 baseline's own analysis: products, listings and
assets are re-derivable by `chain.rebuild`, so losing them costs compute. The audit log, job
history, owner-action queue, incidents, physical tests, cost entries and ledger are records of
what happened and cannot be rebuilt from code. Both are exported -- the whole database is
small and selective backups are how people discover, at restore time, that they drew the line
in the wrong place -- but the manifest marks which is which, so a partial recovery knows what
it is actually missing.

Secrets never appear here. The export carries table rows; the connection string is not a row,
it is not logged, and `redact()` exists so a manifest can name a database without quoting it.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func, insert, select

from .db import Base, Database

# Bumped when the export's shape changes in a way a reader must know about. A restore refuses
# a format it does not understand rather than silently importing half of it.
EXPORT_FORMAT = 1

# Tables whose contents are a record of something that happened. Code can rebuild a listing;
# it cannot rebuild the fact that a job ran at 04:31 or that the owner was asked to approve a
# fee. Named explicitly so the distinction survives someone adding a table later.
NON_REDERIVABLE = (
    "audit_log",
    "jobs",
    "owner_actions",
    "incidents",
    "physical_tests",
    "benchmark_listings",
    "benchmark_observations",
    "coverage_gaps",
    "benchmark_products",
    "teardown_findings",
    "improvements",
    "lessons",
    "capability_history",
    "growth_loops",
    # #144 exactly: the point of a culture radar is what it remembers. A restore that
    # rebuilt everything except which territories recur annually would have lost the
    # asset and kept the machinery.
    "culture_signals",
    "culture_observations",
    # A policy reading cannot be re-derived: it is what the platform said on a day.
    "policy_snapshots",
    # Neither can a price point or a cohort arm: both are a window of real behaviour, and a
    # restore that lost them would lose the only evidence price or ads ever produced.
    "price_observations",
    "cohorts",
    # The build loop's own state. Re-derivable from the registry only in part: the claims,
    # the completion evidence and the decision history are not in any file, and losing them
    # would mean a restored company that does not know what it was doing.
    "build_tasks",
    "build_events",
    # What the pods learned and what changed their minds. Re-derivable from nothing: the
    # outcomes that moved these are gone once the rows are.
    "pod_lessons",
    # Why each running configuration is the one running, and what it beat. Re-derivable
    # from nothing: the runs that justified the switches are gone with the rows.
    "config_versions",
    "cost_entries",
    "ledger_entries",
    "spend_limits",
    "support_cases",
    "agents",
)

# An export does not contain the previous exports. Retained archives are copies of this
# file, so including them would make each night's export carry the compressed bytes of the
# last three, and the backup would grow faster than the company it describes. They are also
# the one table a restore does not need: whoever is restoring is holding the archive.
EXCLUDED_TABLES = ("continuity_archives",)


_URL_CREDENTIALS = re.compile(r"://[^/@\s]*@")


def redact(url: str) -> str:
    """A connection string with its credentials removed, safe to write into a manifest.

    Used so continuity evidence can say *which* database it came from without ever putting
    `DATABASE_URL` into a file, a log line or an API response.
    """
    return _URL_CREDENTIALS.sub("://***@", str(url))


def _jsonable(value: Any) -> Any:
    """Convert a database value into something JSON can hold, losslessly where it matters."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        # Kept as a string: a Decimal through float loses cents at scale, and this is the
        # ledger.
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return {"__datetime__": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes_hex__": bytes(value).hex()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return {"__repr__": repr(value)}


def _from_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        if "__datetime__" in value:
            return datetime.fromisoformat(value["__datetime__"])
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if "__decimal__" in value:
            return Decimal(value["__decimal__"])
        if "__bytes_hex__" in value:
            return bytes.fromhex(value["__bytes_hex__"])
        if "__repr__" in value:
            return value["__repr__"]
        return {k: _from_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_jsonable(v) for v in value]
    return value


@dataclass
class TableExport:
    name: str
    rows: int
    sha256: str
    non_rederivable: bool


@dataclass
class ExportResult:
    path: Path
    format: int
    created_at: datetime
    source: str
    tables: list[TableExport] = field(default_factory=list)
    bytes_written: int = 0

    @property
    def total_rows(self) -> int:
        return sum(t.rows for t in self.tables)

    @property
    def digest(self) -> str:
        """One hash over every table's hash: the whole export in a single comparable value."""
        joined = "|".join(f"{t.name}:{t.sha256}" for t in sorted(self.tables,
                                                                 key=lambda t: t.name))
        return hashlib.sha256(joined.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "bytes": self.bytes_written,
            "total_rows": self.total_rows,
            "digest": self.digest,
            "tables": [
                {"name": t.name, "rows": t.rows, "sha256": t.sha256,
                 "non_rederivable": t.non_rederivable}
                for t in sorted(self.tables, key=lambda t: t.name)
            ],
            "non_rederivable_rows": sum(t.rows for t in self.tables if t.non_rederivable),
        }


def _ordered_tables():
    """Dependency order, so a restore inserts parents before children."""
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


def _rows_of(db: Database, table) -> Iterator[dict]:
    columns = [c.name for c in table.columns]
    with db.session() as s:
        # Ordered by primary key where there is one, so two exports of unchanged data are
        # byte-identical and their hashes can be compared meaningfully.
        stmt = select(table)
        pk = list(table.primary_key.columns)
        if pk:
            stmt = stmt.order_by(*pk)
        for row in s.execute(stmt):
            yield {col: _jsonable(val) for col, val in zip(columns, row)}


def export(db: Database, dest: str | Path) -> ExportResult:
    """Write every table as JSON Lines into one portable file, hashing as it goes.

    JSON Lines rather than one JSON document so a large table streams instead of being held
    in memory, and so a truncated file is detectably truncated rather than silently
    unparseable at the very end.
    """
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc)
    source = redact(str(db.engine.url))

    tables: list[TableExport] = []
    with path.open("w", encoding="utf-8") as fh:
        ordered = list(_ordered_tables())
        # The header declares which tables this file will contain, and the trailer declares
        # that it finished. Without both, a file cut exactly on a table boundary reads as a
        # complete export of fewer tables -- every table it does contain is internally
        # consistent, so the per-table row counts all agree and the operator is told the
        # restore succeeded. That is the failure mode this whole module exists to prevent,
        # and it was found by a test cutting an export in half at the wrong place.
        header = {"__brambleloop_export__": EXPORT_FORMAT,
                  "created_at": created.isoformat(),
                  "source": source,
                  "tables": [t.name for t in ordered],
                  "excluded_tables": list(EXCLUDED_TABLES)}
        fh.write(json.dumps(header, sort_keys=True) + "\n")

        for table in ordered:
            digest = hashlib.sha256()
            count = 0
            fh.write(json.dumps({"__table__": table.name}, sort_keys=True) + "\n")
            for row in _rows_of(db, table):
                line = json.dumps(row, sort_keys=True)
                digest.update(line.encode())
                fh.write(line + "\n")
                count += 1
            fh.write(json.dumps({"__end_table__": table.name, "rows": count},
                                sort_keys=True) + "\n")
            tables.append(TableExport(
                name=table.name, rows=count, sha256=digest.hexdigest(),
                non_rederivable=table.name in NON_REDERIVABLE,
            ))

        fh.write(json.dumps({"__end_export__": EXPORT_FORMAT,
                             "tables": len(ordered),
                             "total_rows": sum(t.rows for t in tables)},
                            sort_keys=True) + "\n")

    result = ExportResult(path=path, format=EXPORT_FORMAT, created_at=created,
                          source=source, tables=tables,
                          bytes_written=path.stat().st_size)
    path.with_suffix(path.suffix + ".manifest.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def read_manifest(export_path: str | Path) -> dict:
    return json.loads(Path(str(export_path) + ".manifest.json").read_text(encoding="utf-8"))


def restore(export_path: str | Path, target: Database) -> dict[str, int]:
    """Load a portable export into any empty database this code can talk to.

    Refuses a format it does not understand, and refuses a truncated file, because a restore
    that quietly stops halfway is worse than one that fails: the operator believes they have
    their data back.
    """
    path = Path(export_path)
    target.create_all()

    counts: dict[str, int] = {}
    current = None
    buffer: list[dict] = []
    tables = {t.name: t for t in _ordered_tables()}
    closed: set[str] = set()

    def flush() -> None:
        if current is None or not buffer:
            return
        table = tables.get(current)
        if table is None:
            raise ValueError(f"export contains unknown table {current!r}")
        rows = [{k: _from_jsonable(v) for k, v in row.items()} for row in buffer]
        with target.session() as s:
            s.execute(insert(table), rows)
        buffer.clear()

    finished: dict | None = None
    with path.open("r", encoding="utf-8") as fh:
        first = fh.readline()
        if not first:
            raise ValueError("export is empty")
        header = json.loads(first)
        fmt = header.get("__brambleloop_export__")
        if fmt != EXPORT_FORMAT:
            raise ValueError(
                f"export format {fmt!r} cannot be read by this code (expects "
                f"{EXPORT_FORMAT}); refusing rather than importing part of it")

        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "__table__" in record:
                flush()
                current = record["__table__"]
                counts[current] = 0
                continue
            if "__end_export__" in record:
                finished = record
                continue
            if "__end_table__" in record:
                flush()
                name = record["__end_table__"]
                if counts.get(name, 0) != record["rows"]:
                    raise ValueError(
                        f"table {name} declared {record['rows']} rows but {counts.get(name, 0)} "
                        f"were read; the export is truncated or corrupt")
                closed.add(name)
                current = None
                continue
            buffer.append(record)
            counts[current] = counts.get(current, 0) + 1
            if len(buffer) >= 500:
                flush()
    flush()

    declared_tables = header.get("tables")
    if isinstance(declared_tables, list):
        never_arrived = [t for t in declared_tables if t not in closed]
        if never_arrived:
            raise ValueError(
                f"the export declares {len(declared_tables)} tables and "
                f"{len(never_arrived)} never arrived ({never_arrived[:3]}...); the file is "
                f"truncated. Each table it does contain is internally consistent, which is "
                f"exactly why this has to be checked against the header rather than against "
                f"the rows")
    if finished is None:
        raise ValueError(
            "the export has no end marker, so it is truncated or was never finished. A "
            "restore that stops halfway and reports success is worse than one that fails")
    if finished.get("tables") != len(closed):
        raise ValueError(
            f"the export says it holds {finished.get('tables')} tables and {len(closed)} "
            f"were read; the file is truncated or corrupt")

    unterminated = set(counts) - closed
    if unterminated:
        raise ValueError(
            f"export ends inside table(s) {sorted(unterminated)}; it is truncated")
    return counts


@dataclass
class RestoreProof:
    """Evidence that the export can actually be turned back into the database."""

    ok: bool
    export: ExportResult
    restored_counts: dict[str, int]
    mismatches: dict[str, tuple[int, int]]
    round_trip_digest: str
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "source_digest": self.export.digest,
            "round_trip_digest": self.round_trip_digest,
            "total_rows": self.export.total_rows,
            "tables": len(self.export.tables),
            "mismatches": {k: list(v) for k, v in self.mismatches.items()},
            "problems": self.problems,
            "non_rederivable_rows": sum(t.rows for t in self.export.tables
                                        if t.non_rederivable),
        }

    def __str__(self) -> str:
        if self.ok:
            return (f"restore proved: {self.export.total_rows} rows across "
                    f"{len(self.export.tables)} tables, digest {self.round_trip_digest[:12]}")
        return f"restore FAILED: {self.problems or self.mismatches}"


def prove_restore(db: Database, work_dir: str | Path) -> RestoreProof:
    """Export, restore into a scratch database, re-export, and compare the hashes.

    Comparing row *counts* alone is the weak version of this check: a restore that dropped
    every timestamp, mangled a JSON column or silently coerced a Decimal would pass it. So
    the proof re-exports the restored database and compares per-table content hashes, which
    only match if the values survived the round trip intact.

    This works against Postgres precisely because the format is engine-independent -- which
    is what the original drill could not do, and why it was honest enough to report ok=False.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    source_path = work / "continuity-export.jsonl"
    original = export(db, source_path)

    scratch_path = work / "continuity-restore-check.sqlite"
    if scratch_path.exists():
        scratch_path.unlink()
    # `scratch=True` is required in production: BRAMBLELOOP_REQUIRE_POSTGRES refuses ephemeral
    # SQLite, and rightly, but this file is a deliberate throwaway target for the restore --
    # not the company's memory. Production dead-lettered this job three times before the
    # exemption existed, which is the guard working and the call site being wrong.
    scratch = Database(f"sqlite:///{scratch_path}", scratch=True)

    problems: list[str] = []
    try:
        restored_counts = restore(source_path, scratch)
    except Exception as e:  # noqa: BLE001 - a failed restore is the finding, not a crash
        return RestoreProof(ok=False, export=original, restored_counts={},
                            mismatches={}, round_trip_digest="",
                            problems=[f"restore raised {type(e).__name__}: {e}"])

    expected = {t.name: t.rows for t in original.tables}
    mismatches = {
        name: (expected.get(name, 0), restored_counts.get(name, 0))
        for name in set(expected) | set(restored_counts)
        if expected.get(name, 0) != restored_counts.get(name, 0)
    }

    # The part that makes this a proof rather than a headcount.
    round_trip = export(scratch, work / "continuity-roundtrip.jsonl")
    if round_trip.digest != original.digest:
        differing = [
            t.name for t in original.tables
            if t.sha256 != next((r.sha256 for r in round_trip.tables if r.name == t.name), "")
        ]
        problems.append(
            "restored data does not hash identically to the source; tables differing: "
            + ", ".join(sorted(differing)[:10]))

    return RestoreProof(
        ok=not mismatches and not problems,
        export=original,
        restored_counts=restored_counts,
        mismatches=mismatches,
        round_trip_digest=round_trip.digest,
        problems=problems,
    )


def counts_by_table(db: Database) -> dict[str, int]:
    out: dict[str, int] = {}
    with db.session() as s:
        for table in _ordered_tables():
            out[table.name] = s.scalar(select(func.count()).select_from(table)) or 0
    return out


# ---------------------------------------------------------------------------
# Retention (#51). Proving a restore of a file that no longer exists an hour later is a
# drill, not a backup.

# How many archives are kept. More than one because the newest export of a database that was
# corrupted this morning is an export of the corruption; three gives a reader somewhere to
# step back to. Few enough that the archives never become the largest thing in the database.
RETAINED_ARCHIVES = 3


def _compress(path: Path) -> tuple[bytes, int]:
    import gzip

    raw = path.read_bytes()
    return gzip.compress(raw, 6), len(raw)


def retain(db: Database, export_path: str | Path, result: ExportResult) -> dict:
    """Store a finished export where it outlives the container that produced it.

    This is deliberately not called durable storage. The bytes sit in the same database they
    describe, so they survive a container replacement, a redeploy and a crash -- the failures
    that actually happen -- and not the provider disappearing, which is the failure #51 names
    and the reason an off-provider copy is an owner item rather than something claimed here.
    """
    from .models import ContinuityArchive

    path = Path(export_path)
    payload, raw_bytes = _compress(path)
    with db.session() as s:
        row = ContinuityArchive(
            format=result.format, digest=result.digest,
            payload_sha256=hashlib.sha256(payload).hexdigest(), payload=payload,
            raw_bytes=raw_bytes, stored_bytes=len(payload),
            total_rows=result.total_rows, source=result.source,
            manifest=result.to_dict())
        s.add(row)
        s.flush()
        archive_id = row.id

        keep = [r.id for r in s.scalars(
            select(ContinuityArchive).order_by(ContinuityArchive.at.desc(),
                                               ContinuityArchive.id.desc()))][:RETAINED_ARCHIVES]
        pruned = [r for r in s.scalars(select(ContinuityArchive)) if r.id not in keep]
        for old in pruned:
            s.delete(old)
        pruned_ids = [r.id for r in pruned]

    return {
        "archive_id": archive_id,
        "digest": result.digest,
        "raw_bytes": raw_bytes,
        "stored_bytes": len(payload),
        "retained": len(keep),
        "pruned": pruned_ids,
        "survives": {"container_replacement": True, "redeploy": True,
                     "provider_loss": False},
        "note": ("held in the database it describes: this survives losing the container, "
                 "not losing the provider. The off-provider copy #51 asks for is an owner "
                 "item and is not claimed here"),
    }


def retained(db: Database) -> list[dict]:
    """What archives exist, newest first, without reading the payloads back."""
    from .models import ContinuityArchive

    with db.session() as s:
        rows = list(s.scalars(select(ContinuityArchive).order_by(
            ContinuityArchive.at.desc(), ContinuityArchive.id.desc())))
        return [{"archive_id": r.id, "at": r.at.isoformat(), "digest": r.digest,
                 "total_rows": r.total_rows, "stored_bytes": r.stored_bytes,
                 "raw_bytes": r.raw_bytes, "tables": len(r.manifest.get("tables", []))}
                for r in rows]


def write_retained(db: Database, archive_id: int, dest: str | Path) -> Path:
    """Write a retained archive back out as the same JSON Lines file it was made from.

    The stored bytes are hashed before they are trusted. A corrupt archive that restores
    three quarters of a company is worse than one that refuses, because the first is
    discovered months later and the second is discovered now.
    """
    from .models import ContinuityArchive

    import gzip

    with db.session() as s:
        row = s.get(ContinuityArchive, archive_id)
        if row is None:
            raise ValueError(f"no retained archive {archive_id}")
        payload, expected = row.payload, row.payload_sha256
        manifest = dict(row.manifest or {})

    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(
            f"archive {archive_id} does not hash to what was stored "
            f"({actual[:12]} != {expected[:12]}); it is corrupt and will not be restored")

    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.decompress(payload))
    # The manifest travels with the file, so a recovered archive is as readable on its own as
    # the export that made it. An archive that restores but cannot say what it contains
    # leaves the operator counting rows by hand at the worst possible moment.
    Path(str(path) + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def restore_retained(db: Database, archive_id: int, target: Database,
                     work_dir: str | Path) -> dict[str, int]:
    """Rebuild a database from a retained archive, the way a real recovery would."""
    path = write_retained(db, archive_id, Path(work_dir) / f"archive-{archive_id}.jsonl")
    return restore(path, target)
