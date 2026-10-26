"""F-417: every direct requirement and called service has an adoption row with its cost and
footprint; metered cost is measured from cost rows, unread things are UNMEASURED."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ad_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/a.db"

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.ops import adoptions as A  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()


def test_complete_and_a_new_requirement_fails():
    assert A.check() == []
    real = A.direct_requirements
    A.direct_requirements = lambda: real() + ["leftpad"]
    try:
        assert A.check() == ["requirement leftpad has no adoption row"]
    finally:
        A.direct_requirements = real


def test_metered_cost_is_measured_and_absence_is_named():
    with db.session() as s:
        s.add(CostEntry(agent="a", kind="model", amount_cad=1.25, purpose="p",
                        provider="anthropic"))
    rows = {r["adoption"]: r for r in A.report(db)["adoptions"]}
    assert rows["anthropic"]["recurring"]["cad_30d"] == 1.25
    assert "measured" in rows["anthropic"]["recurring"]["basis"]
    assert rows["bfl"]["recurring"]["basis"] == "measured: no cost rows in 30 days"
    assert rows["hosting"]["recurring"]["basis"] == "declared_not_observed"
    assert isinstance(rows["sqlalchemy"]["footprint"]["installed_mb"], float)
    assert A.installed_mb("no-such-package-xyz") == A.UNMEASURED


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
