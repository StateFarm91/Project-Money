"""F-672 (rest): the pipeline records its own lifecycle moves -- a completed pipeline job writes
the stage its rows now show, with history; an illegal move is an anomaly, never silent."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, PatternVersion, Phase, Product  # noqa: E402
from brambleloop.products import lifecycle as L  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb2lc-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_a_completed_pipeline_job_records_the_move_it_caused():
    db = _db()
    reg = HandlerRegistry()

    # The certified version is written beforehand: a real certify job writes it with its
    # certificate's provenance row, and the worker's provenance backstop (rightly) kills a
    # stand-in handler that writes a certificate without one. The hook reads rows at job end.
    with db.session() as s:
        p = Product(slug="hex", title="Hex")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True))

    @reg.register("gate.certify")
    def certify(ctx):
        return {"certified": True}

    @reg.register("listing.draft")
    def draft(ctx):
        with ctx.db.session() as s:
            s.add(Listing(product_slug="hex", version="1", title="t", description="d",
                          state="drafted"))
        return {"drafted": True}

    q = JobQueue(db)
    w = Worker(db, "fmb2", phase=Phase.SHADOW, registry=reg)
    q.enqueue("quality_director", "gate.certify", {"slug": "hex"}, idempotency_key="c")
    while w.run_once():                             # the queue does not promise FIFO order
        pass
    q.enqueue("listing", "listing.draft", {"slug": "hex"}, idempotency_key="d")
    while w.run_once():
        pass
    body = memory.get(db, L.KEY + "hex")["body"]
    assert body["stage"] == "VISUAL" and body["observed"] is True
    assert [(h["from"], h["to"], h["by"]) for h in body["history"]] == [
        (None, "QA", "gate.certify"), ("QA", "VISUAL", "listing.draft")]
    assert all(h["legal"] for h in body["history"])


def test_an_illegal_observed_move_is_an_anomaly_and_non_pipeline_jobs_record_nothing():
    db = _db()
    with db.session() as s:
        p = Product(slug="x", title="x")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True))
        s.add(Listing(product_slug="x", version="1", title="t", description="d",
                      state="published"))
    assert L.after_job(db, "seo.cycle", {"slug": "x"}, {}) == []
    first = L.after_job(db, "store.publish", {"slug": "x"}, {})
    assert first == [{"slug": "x", "from": None, "to": "LIVE", "legal": True}]
    with db.session() as s:                          # rows now say a draft again: backwards
        s.query(Listing).update({"state": "drafted"})
    moved = L.after_job(db, "listing.draft", {"slug": "x"}, {})
    assert moved[0]["legal"] is False and moved[0]["to"] == "VISUAL"
    with db.session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == L.ANOMALY_ACTION).count() == 1
    assert L.after_job(db, "listing.draft", {"slug": "x"}, {}) == []    # unchanged: no row


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
