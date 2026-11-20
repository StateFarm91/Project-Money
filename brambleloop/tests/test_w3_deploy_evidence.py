"""Every boot records its own deploy evidence and names its rollback target (F-380, F-381).

Wave 3, lane TOOLS (cluster K14). The deploy guard is client-side (a git hook and
ops/deploy.sh) and can be skipped (F-461, owner-gated). The boot verdict audit row is written by
whatever code actually started, from inside the container, so the deploy record exists even when
the client-side door was bypassed.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import release_record as R  # noqa: E402


def _db():
    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp(prefix="w3-deployev-")
    db = Database(f"sqlite:///{tmp}/d.db")
    db.create_all()
    return db, tmp


def _verdicts(db) -> list[dict]:
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        return [dict(r.detail, _artifact=r.artifact) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == "release.boot_verdict")
            .order_by(AuditLog.id))]


def test_every_boot_appends_a_boot_verdict_row_proven_or_not():
    db, tmp = _db()
    try:
        bad = {"enforced": True, "ok": False, "reasons": ["no record"], "action": "forced_shadow",
               "tree_sha256": "d" * 64, "running_commit": "e" * 40}
        good = {"enforced": True, "ok": True, "action": "none", "tree_sha256": "d" * 64,
                "running_commit": "e" * 40,
                "record": {"file": "RELEASE_x.json", "sha": "e" * 40, "suite_run": "s"}}
        assert R.record_incident(db, bad) == "opened"
        assert R.record_incident(db, good) == "resolved"
        rows = _verdicts(db)
        assert len(rows) == 2
        assert rows[0]["ok"] is False and rows[0]["action"] == "forced_shadow"
        assert rows[0]["reasons"] == ["no record"] and rows[0]["_artifact"] is None
        assert rows[1]["ok"] is True and rows[1]["_artifact"] == "RELEASE_x.json"
        assert rows[1]["tree_sha256"] == "d" * 64
        assert "known_good_predecessor" in rows[1]
        assert R.record_incident(db, {}) == "not_run" and len(_verdicts(db)) == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_known_good_predecessor_comes_from_the_shipped_deployed_history():
    hist = json.loads((ROOT / "release" / R.HISTORY_FILE).read_text())["deployed"]
    assert hist, "the shipped deployed history is empty"
    last = hist[-1]["sha"]
    got = R.known_good_predecessor("f" * 40)
    assert got["sha"] == last and "rollback-commit" in got["how"]
    # The running commit is never its own rollback target.
    if len(hist) == 1:
        assert R.known_good_predecessor(last)["sha"] is None
    root = Path(tempfile.mkdtemp(prefix="w3-hist-"))
    try:
        (root / "release").mkdir()
        (root / "release" / R.HISTORY_FILE).write_text(json.dumps({"deployed": [
            {"sha": "a" * 40, "observed": "2026-10-01"}, {"sha": "b" * 40}]}))
        assert R.known_good_predecessor("b" * 40, root)["sha"] == "a" * 40
        assert R.known_good_predecessor("c" * 40, root)["sha"] == "b" * 40
        assert R.known_good_predecessor(None, root / "nope")["sha"] is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_history_ships_in_the_image():
    docker = (ROOT / "Dockerfile").read_text()
    assert "COPY release ./release" in docker


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
