"""W4-FMGATE: the stale-artefact sentinel's rebuild keys fit `jobs.idempotency_key`.

Production 0417f35 (2026-10-11): `ops.sentinel` dead-lettered every run with
`StringDataRightTruncation ... character varying(200)` because `rebuild_graph.enqueue` keyed
`chain.rebuild` on every moved ref and its fingerprint. The deploy moved many code
fingerprints at once, the key outgrew VARCHAR(200), and the 24-hour off-device proof can never
pass while a cadence dead-letters hourly. SQLite does not enforce VARCHAR lengths, so these
tests assert the length directly instead of relying on the database to refuse.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402
from brambleloop.ops import artefacts as A, rebuild_graph as G  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from sqlalchemy import select  # noqa: E402

DESIGN = A.fingerprint({"rows": 12})


def _many_changed(tag: str) -> dict[str, str]:
    """A deploy-sized change: forty code refs plus the design, each with a new fingerprint."""
    out = {f"code:brambleloop/module_number_{i:02d}.py": A.fingerprint({"v": tag, "i": i})
           for i in range(40)}
    out["cir:hex"] = A.fingerprint({"rows": tag})
    return out


def _db():
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        A.record(s, artefact_class="pdf", artefact_key="hex.pdf", product_slug="hex",
                 inputs={"cir:hex": DESIGN})
    return db


def _keys(db):
    with db.session() as s:
        return [k for k in s.scalars(select(Job.idempotency_key)) if k]


def test_the_limit_is_the_column_length():
    assert Job.__table__.c.idempotency_key.type.length == G.IDEMPOTENCY_KEY_MAX


def test_a_deploy_sized_change_enqueues_keys_that_fit_the_column():
    for per in ("product", "artefact"):
        db = _db()
        with db.session() as s:
            out = G.enqueue(s, JobQueue(db), changed=_many_changed("a"),
                            reason="deploy moved forty refs", per=per)
        keys = _keys(db)
        assert out["enqueued"], per
        assert keys and all(len(k) <= G.IDEMPOTENCY_KEY_MAX for k in keys), (per, keys)


def test_a_long_change_is_still_idempotent_and_a_different_change_enqueues_again():
    db = _db()
    q = JobQueue(db)
    with db.session() as s:
        first = G.enqueue(s, q, changed=_many_changed("a"), reason="r", per="product")
        again = G.enqueue(s, q, changed=_many_changed("a"), reason="r", per="product")
        other = G.enqueue(s, q, changed=_many_changed("b"), reason="r", per="product")
    assert first["enqueued"] and again["enqueued"] == [] and again["already_queued"]
    assert other["enqueued"]
    assert len(set(_keys(db))) == 2


def test_a_short_key_is_unchanged():
    assert G.job_key("rebuild:product:hex", "cir:hex=abcd1234") == \
        "rebuild:product:hex:cir:hex=abcd1234"
    long = G.job_key("rebuild:product:hex", "x" * 400)
    assert long.startswith("rebuild:product:hex:sha256=") and len(long) <= 200
    huge = G.job_key("rebuild:" + "p" * 300, "x" * 400)
    assert huge.startswith("rebuild:sha256=") and len(huge) <= 200


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
