"""F-715: competing build proposals are resolved by evidence of the requirement's kinds;
proposer and model never decide, a refuted proposal is rejected, and a tie stays UNRESOLVED."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import shutil
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import disagreement as D  # noqa: E402

T = "brambleloop/tests/test_w4_c01_disagreement.py"     # a test that exists in the repo


def _setup():
    d = Path(tempfile.mkdtemp(prefix="c01dg-"))
    D.DIR = d
    D.open_("dg1", question="Where does the integration rule live?", lane="W4-C01")
    D.propose("dg1", "hook", by="w-c01", model="opus", approach="in the pre-push hook")
    D.propose("dg1", "queue", by="w-c09", model="codex", approach="in ops/integrate.py only")
    return d


def test_only_evidence_kinds_count_and_tests_must_be_reproducible():
    d = _setup()
    try:
        for kw, word in ((dict(kind="opinion", ref="x", result="SUPPORTS"), "not evidence"),
                         (dict(kind="model_rank", ref="x", result="SUPPORTS"), "not evidence"),
                         (dict(kind="test", ref="no/such_test.py", result="SUPPORTS",
                               command="python3 x"), "not reproducible"),
                         (dict(kind="test", ref=T, result="SUPPORTS"), "command"),
                         (dict(kind="economics", ref="", result="SUPPORTS"), "cites"),
                         (dict(kind="economics", ref="ledger", result="MAYBE"), "result")):
            try:
                D.evidence("dg1", "hook", repo=OPS.parent, **kw)
                raise AssertionError(kw)
            except D.DisagreementRefused as exc:
                assert word in str(exc), (word, exc)
        assert D.resolve("dg1")["resolution"]["outcome"] == D.UNRESOLVED
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_refuted_loses_supported_wins_and_models_never_decide():
    d = _setup()
    try:
        D.evidence("dg1", "hook", kind="test", ref=T, result="SUPPORTS", repo=OPS.parent,
                   command="python3 " + T)
        D.evidence("dg1", "queue", kind="primary_evidence", ref="git push log", result="REFUTES",
                   detail="a worker pushed straight onto INTEG; the queue never saw it")
        r = D.resolve("dg1")["resolution"]
        assert r["outcome"] == D.ACCEPTED and r["accepted"] == "hook"
        assert r["status"] == {"hook": D.ACCEPTED, "queue": D.REJECTED}
        # Swap who proposed what, and with which model: the decision does not move.
        props = D.load("dg1")["proposals"]
        swapped = {"hook": {**props["hook"], "by": "w-c09", "model": "codex"},
                   "queue": {**props["queue"], "by": "w-c01", "model": "opus"}}
        assert D.decide(swapped, D.load("dg1")["evidence"])["accepted"] == "hook"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_two_supported_proposals_stay_unresolved():
    d = _setup()
    try:
        D.evidence("dg1", "hook", kind="economics", ref="cost", result="SUPPORTS")
        D.evidence("dg1", "queue", kind="product_truth", ref="cir", result="SUPPORTS")
        r = D.resolve("dg1")["resolution"]
        assert r["outcome"] == D.UNRESOLVED and r["accepted"] is None
        assert "separates hook, queue" in r["needs"]
        assert [x["id"] for x in D.for_lane("W4-C01")] == ["dg1"]
        try:
            D.open_("dg1", question="again", lane="W4-C01")
            raise AssertionError("reopened")
        except D.DisagreementRefused:
            pass
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
