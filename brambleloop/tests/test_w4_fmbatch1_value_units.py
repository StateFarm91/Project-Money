"""F-107: spend by requirement and benchmark, as first-class report dimensions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402
from brambleloop.finance import spend_report as R  # noqa: E402
from brambleloop.finance import value_units as V  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def test_scope_stamps_requirement_and_benchmark_on_the_bill():
    db = _db()
    with V.scope(requirement_id="F-107", benchmark_key="hat-gallery-v2"):
        R.record(db, agent="market_radar", amount_cad=0.5, purpose="gallery_observation")
    out = R.what_it_bought(db)
    assert out["by_requirement"] == {"F-107": {"cad": 0.5, "calls": 1}}
    assert out["by_benchmark"] == {"hat-gallery-v2": {"cad": 0.5, "calls": 1}}


def test_job_inputs_attribute_when_the_writer_did_not_stamp():
    db = _db()
    with db.session() as s:
        j = Job(agent="x", job_type="bench.run",
                inputs={"requirement": "F-096", "benchmark": "compat-pack"})
        s.add(j)
        s.flush()
        jid = j.id
    R.record(db, agent="x", amount_cad=0.25, purpose="bench", job_id=jid)
    out = R.what_it_bought(db)
    assert out["by_requirement"]["F-096"]["cad"] == 0.25
    assert out["by_benchmark"]["compat-pack"]["calls"] == 1


def test_unattributed_spend_keeps_its_dollars_and_scope_does_not_leak():
    db = _db()
    with V.scope(requirement_id="F-1"):
        pass
    R.record(db, agent="x", amount_cad=1.0, purpose="p")
    R.record(db, agent="x", amount_cad=2.0, purpose="p",
             detail={"requirement_id": "explicit"})
    with V.scope(requirement_id="scoped"):
        R.record(db, agent="x", amount_cad=4.0, purpose="p",
                 detail={"requirement_id": "explicit"})
    out = R.what_it_bought(db)
    req = out["by_requirement"]
    assert req[R.UNATTRIBUTED]["cad"] == 1.0
    assert req["explicit"] == {"cad": 6.0, "calls": 2}       # explicit beats the scope
    assert "scoped" not in req and "F-1" not in req
    assert sum(b["cad"] for b in req.values()) == out["spent_cad"]
    assert out["by_benchmark"] == {R.UNATTRIBUTED: {"cad": 7.0, "calls": 3}}


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
