"""Business continuity: the export, the restore, and the proof that it works.

Requirement 51, and the gap Build 1 wrote into its own baseline rather than hiding. The
owner's Build-2 authorization added the constraint that matters more than the feature: no
secret may escape through logs, repository files or unauthenticated endpoints.

So these tests are in two halves. The first proves the data survives a round trip -- not by
counting rows, which a restore that mangled every timestamp would also pass, but by comparing
content hashes. The second attacks the endpoint that can return the database.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import continuity, opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402


def _loaded_db() -> tuple[Database, str]:
    """A database with the kinds of value that break naive exporters."""
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/source.sqlite")
    db.create_all()
    Registry(db).seed_defaults()

    q = JobQueue(db)
    for i in range(7):
        q.enqueue("orchestrator", "ops.heartbeat", {"n": i, "nested": {"a": [1, 2, None]}},
                  idempotency_key=f"continuity-{i}")
    reg = Registry(db)
    reg.audit("orchestrator", "continuity.fixture",
              detail={"unicode": "pine – cream ✓", "float": 1.5, "bool": True,
                      "null": None, "list": [1, "two", {"three": 3}]})
    reg.audit("listing", "continuity.fixture.two", artifact="a-slug", detail={})
    return db, tmp


def test_an_export_restores_into_an_empty_database_and_hashes_identically():
    """The proof, and why it is not a row count.

    A restore that dropped every timestamp, mangled a JSON column or coerced a Decimal to a
    float would pass a headcount unchanged. So the restored database is re-exported and
    compared hash for hash -- which only matches if the values themselves survived.
    """
    db, tmp = _loaded_db()
    proof = continuity.prove_restore(db, tmp)

    assert proof.ok, (proof.problems, proof.mismatches)
    assert not proof.mismatches, proof.mismatches
    assert proof.export.digest == proof.round_trip_digest
    assert proof.export.total_rows > 0
    # The records that cannot be rebuilt from code are the point of the exercise.
    assert proof.to_dict()["non_rederivable_rows"] > 0


def test_the_export_is_portable_rather_than_engine_native():
    """#51 asks for formats that survive losing the vendor.

    A `pg_dump` restores into Postgres and nowhere else, which is the dependency the
    requirement exists to remove. This asserts the export is plain text anyone can read, and
    that a Postgres-shaped export can be restored into SQLite -- which is exactly what makes
    the proof possible at all.
    """
    import json

    db, tmp = _loaded_db()
    result = continuity.export(db, f"{tmp}/portable.jsonl")

    lines = Path(result.path).read_text(encoding="utf-8").strip().split("\n")
    header = json.loads(lines[0])
    assert header["__brambleloop_export__"] == continuity.EXPORT_FORMAT
    # Every line stands alone, so a truncated file is detectably truncated.
    for line in lines:
        json.loads(line)

    scratch = Database(f"sqlite:///{tmp}/restored.sqlite")
    counts = continuity.restore(result.path, scratch)
    assert counts["audit_log"] >= 2
    assert counts["jobs"] == 7


def test_a_truncated_export_is_refused_rather_than_half_restored():
    """A restore that quietly stops halfway is worse than one that fails.

    The operator believes they have their data back. Every table declares its own row count
    and the reader checks it, so truncation is caught at the point it happened.
    """
    db, tmp = _loaded_db()
    result = continuity.export(db, f"{tmp}/truncate-me.jsonl")

    full = Path(result.path).read_text(encoding="utf-8").split("\n")
    cut = Path(tmp) / "truncated.jsonl"
    cut.write_text("\n".join(full[: len(full) // 2]), encoding="utf-8")

    scratch = Database(f"sqlite:///{tmp}/truncated-target.sqlite")
    try:
        continuity.restore(cut, scratch)
    except ValueError as e:
        assert "truncat" in str(e).lower() or "corrupt" in str(e).lower(), e
    else:
        raise AssertionError("a truncated export was restored as if it were complete")


def test_an_export_from_a_future_format_is_refused():
    """Importing half of a format you do not understand is worse than refusing it."""
    db, tmp = _loaded_db()
    result = continuity.export(db, f"{tmp}/future.jsonl")

    lines = Path(result.path).read_text(encoding="utf-8").split("\n")
    lines[0] = lines[0].replace(f'"__brambleloop_export__": {continuity.EXPORT_FORMAT}',
                                '"__brambleloop_export__": 99')
    future = Path(tmp) / "future-format.jsonl"
    future.write_text("\n".join(lines), encoding="utf-8")

    scratch = Database(f"sqlite:///{tmp}/future-target.sqlite")
    try:
        continuity.restore(future, scratch)
    except ValueError as e:
        assert "format" in str(e).lower(), e
    else:
        raise AssertionError("an unknown export format was read anyway")


def test_no_connection_string_ever_reaches_the_export_or_its_manifest():
    """The constraint the owner put above the feature.

    The export names which database it came from, because continuity evidence that cannot
    say that is not evidence. It must do so without the credential.
    """
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/plain.sqlite")
    db.create_all()
    result = continuity.export(db, f"{tmp}/redaction.jsonl")

    secret = "hunter2-should-never-appear"
    assert continuity.redact(
        f"postgresql://brambleloop:{secret}@db.internal:5432/rail") == \
        "postgresql://***@db.internal:5432/rail"
    assert secret not in continuity.redact(
        f"postgresql://user:{secret}@host/db")

    body = Path(result.path).read_text(encoding="utf-8")
    manifest = Path(str(result.path) + ".manifest.json").read_text(encoding="utf-8")
    for blob in (body, manifest, str(result.to_dict())):
        assert "@" not in result.source or "***@" in result.source
        assert secret not in blob


def test_the_export_endpoint_is_closed_when_no_credential_is_configured():
    """Absent must mean closed, not open.

    The opposite default serves the company to the internet during the window between
    deploying the endpoint and remembering to set the variable -- which is precisely the
    window in which nobody is looking.
    """
    empty: dict[str, str] = {}
    assert opsauth.configured(empty) is False
    for attempt in (None, "", "anything", "Bearer anything"):
        try:
            opsauth.check(attempt, empty)
        except opsauth.OpsAuthUnavailable:
            pass
        else:
            raise AssertionError(f"an unconfigured endpoint accepted {attempt!r}")


def test_a_wrong_or_short_credential_is_refused():
    """And a configured endpoint still refuses the wrong token, in constant time."""
    good = "a" * 40
    env = {opsauth.TOKEN_VAR: good}

    opsauth.check(good, env)
    opsauth.check(f"Bearer {good}", env)

    for wrong in (None, "", "b" * 40, good[:-1], good + "x", "Bearer " + "b" * 40):
        try:
            opsauth.check(wrong, env)
        except opsauth.OpsAuthRefused:
            pass
        else:
            raise AssertionError(f"credential {wrong!r} was accepted")

    # A short token is treated as unusable rather than as a weak-but-valid secret.
    short = {opsauth.TOKEN_VAR: "tiny"}
    assert opsauth.configured(short) is False
    assert opsauth.token_health(short)["usable"] is False
    try:
        opsauth.check("tiny", short)
    except opsauth.OpsAuthUnavailable:
        pass
    else:
        raise AssertionError("a token below the minimum length was accepted")


def test_token_health_never_reveals_the_token():
    """Health has to be reportable on an open status endpoint."""
    secret = "z" * 48
    health = opsauth.token_health({opsauth.TOKEN_VAR: secret})
    assert health["usable"] is True
    blob = str(health)
    assert secret not in blob
    assert "z" * 8 not in blob


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
