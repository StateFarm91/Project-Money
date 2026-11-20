"""F-714 / F-866: high-risk build work integrates only after an independent review of exactly
that head by a different agent; the review never certifies, and a reviewer cannot be the
implementer. Low-risk lanes are untouched."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import integrate as I  # noqa: E402
import review as RV  # noqa: E402

CONTRACT = "brambleloop/tests/test_w4_fmbatch1_contracts.py"
PKG = "brambleloop/src/brambleloop/"


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def _ok(**kw):
    base = dict(lane="L", head="abc1234", implementer="w-c01", implementer_model="opus",
                reviewer="w-review", reviewer_model="codex", verdict="NO_BLOCKERS",
                findings="re-ran the guard tests; tried a force push; refused")
    base.update(kw)
    return base


def test_the_high_risk_table_names_every_class_in_the_requirement():
    assert set(RV.HIGH_RISK) == {"customer_facing", "financial", "marketplace", "security",
                                 "infrastructure", "product_truth"}
    hit = RV.classify(["ops/deploy_guard.py", PKG + "finance/books.py",
                       "./" + PKG + "cir/schema.py", "README.md", PKG + "radar/x.py"])
    assert hit == {"security": ["ops/deploy_guard.py"],
                   "financial": [PKG + "finance/books.py"],
                   "product_truth": [PKG + "cir/schema.py"]}
    assert RV.classify(["a.txt", "brambleloop/tests/test_x.py"]) == {}


def test_record_refuses_self_review_and_any_certification():
    d = Path(tempfile.mkdtemp(prefix="c01rv-"))
    try:
        RV.LOG = d / "REVIEWS.jsonl"
        for bad, word in ((_ok(reviewer="W-C01"), "own work"),
                          (_ok(verdict="LGTM"), "verdict"),
                          (_ok(findings=" "), "states what"),
                          (_ok(head="main"), "head"),
                          (_ok(certifies=True), "never certifies")):
            try:
                RV.record(**bad)
                raise AssertionError(bad)
            except RV.ReviewRefused as exc:
                assert word in str(exc), (word, exc)
        r = RV.record(**_ok())
        assert r["certifies"] is False and r["second_model"] is True
        same = RV.record(**_ok(reviewer_model="OPUS", head="def5678"))
        assert same["second_model"] is False        # a different agent, same model: recorded
        assert len(RV._read()) == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_integration_requires_a_review_of_exactly_the_head():
    base = Path(tempfile.mkdtemp(prefix="c01rvi-"))
    try:
        RV.LOG = base / "REVIEWS.jsonl"
        I.QUEUE = base / "MERGE_QUEUE.json"
        repo = base / "r"
        subprocess.run(["git", "init", "-q", "-b", "integration", str(repo)], check=True)
        (repo / "brambleloop" / "tests").mkdir(parents=True)
        (repo / CONTRACT).write_text("import sys; sys.exit(0)\n")
        (repo / "ops").mkdir()
        (repo / "ops" / "deploy_guard.py").write_text("v1\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "checkout", "-q", "-b", "risky")
        (repo / "ops" / "deploy_guard.py").write_text("v2\n")
        _git(repo, "commit", "-qam", "touch the guard")
        old_head = _git(repo, "rev-parse", "HEAD")
        (repo / "ops" / "deploy_guard.py").write_text("v3\n")
        _git(repo, "commit", "-qam", "again")
        head = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-q", "integration")
        before = _git(repo, "rev-parse", "integration")
        I.enqueue("risky", "risky")
        out = I.next_lane(target="integration", repo=repo)
        assert out["merged"] is False and "independent review" in out["why"], out
        assert _git(repo, "rev-parse", "integration") == before
        RV.record(**_ok(lane="risky", head=old_head))             # an older head: no carry
        assert I.next_lane(target="integration", repo=repo)["merged"] is False
        RV.record(**_ok(lane="risky", head=head, verdict="BLOCKERS",
                        findings="the guard lets a deletion through"))
        out = I.next_lane(target="integration", repo=repo)
        assert out["merged"] is False
        assert [c for c in out["checks"] if c["check"].startswith("independent")][0]["why"] \
            == "BLOCKERS recorded on this head"
        RV.LOG.write_text("")                                     # a fresh review history
        RV.record(**_ok(lane="risky", head=head))
        out = I.next_lane(target="integration", repo=repo)
        assert out["merged"] is True, out
        rv = [c for c in out["checks"] if c["check"].startswith("independent")][0]
        assert rv["classes"] == ["security"] and rv["certifies"] is False
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
