"""F-861 / F-862 / F-863: a lane's handoff lives in the repository with every field the
requirement names, is DURABLE only when its head is pushed and nothing tracked is uncommitted,
persists conclusions as they are reached, and is re-verified against git on resume."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import handoff as H  # noqa: E402

FIELDS = dict(decisions=["keep the guard local"], defects=[], tests=["tests/t.py"],
              unfinished=["wire the CLI"], next_actions=["run tests/t.py then push"])


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                           "-c", "user.email=t@e.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _setup():
    base = Path(tempfile.mkdtemp(prefix="c01ho-"))
    origin, repo = base / "o.git", base / "r"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "lane", str(repo)], check=True)
    (repo / "f").write_text("1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    _git(repo, "remote", "add", "origin", str(origin))
    H.HANDOFF_DIR = base / "handoffs"
    return base, repo


def test_every_field_is_required_and_read_from_git():
    base, repo = _setup()
    try:
        for drop in ("decisions", "tests", "unfinished", "next_actions", "defects"):
            kw = {k: v for k, v in FIELDS.items() if k != drop}
            try:
                H.write(lane="L", objective="close the handoff rows", repo=repo, **kw)
                raise AssertionError(f"accepted a handoff without {drop}")
            except H.HandoffRefused as exc:
                assert drop in str(exc)
        try:
            H.write(lane="L", objective="wip", repo=repo, **FIELDS)
            raise AssertionError("a one-word objective was accepted")
        except H.HandoffRefused:
            pass
        rec = H.write(lane="L", objective="close the handoff rows", repo=repo, **FIELDS)
        assert rec["head"] == _git(repo, "rev-parse", "HEAD") and rec["branch"] == "lane"
        assert rec["defects"] == [] and rec["next_actions"] == FIELDS["next_actions"]
        on_disk = json.loads((H.HANDOFF_DIR / "L.json").read_text())
        assert on_disk["objective"] == "close the handoff rows"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_durable_only_when_pushed_and_committed():
    base, repo = _setup()
    try:
        rec = H.write(lane="L", objective="close the handoff rows", repo=repo, **FIELDS)
        assert rec["durability"]["state"] == H.NOT_DURABLE
        assert "on no remote ref" in rec["durability"]["reasons"][0]
        _git(repo, "push", "-q", "origin", "lane")
        _git(repo, "fetch", "-q", "origin")
        assert H.write(lane="L", objective="close the handoff rows", repo=repo,
                       **FIELDS)["durability"]["state"] == H.DURABLE
        (repo / "f").write_text("2\n")
        d = H.write(lane="L", objective="close the handoff rows", repo=repo,
                    **FIELDS)["durability"]
        assert d["state"] == H.NOT_DURABLE and d["uncommitted"] == ["f"]
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_conclusions_persist_immediately_and_resume_reverifies():
    base, repo = _setup()
    try:
        assert H.resume(lane="L", repo=repo)["found"] is False
        H.conclude(lane="L", text="F-711 needs the hook, not integrate.py")
        _git(repo, "push", "-q", "origin", "lane")
        _git(repo, "fetch", "-q", "origin")
        H.write(lane="L", objective="close the handoff rows", repo=repo, **FIELDS)
        r = H.resume(lane="L", repo=repo)
        assert r["verify"]["remote"] == "AT_HEAD" and not r["incomplete_fields"]
        assert r["handoff"]["conclusions"][0]["text"].startswith("F-711")
        (repo / "f").write_text("3\n")
        _git(repo, "commit", "-qam", "two")
        _git(repo, "push", "-q", "origin", "lane")
        _git(repo, "fetch", "-q", "origin")
        r = H.resume(lane="L", repo=repo)
        assert r["verify"]["remote"] == "MOVED_AHEAD", r["verify"]
        try:
            H.conclude(lane="L", text="   ")
            raise AssertionError("empty conclusion accepted")
        except H.HandoffRefused:
            pass
        try:
            H.write(lane="../x", objective="close the handoff rows", repo=repo, **FIELDS)
            raise AssertionError("path-like lane accepted")
        except H.HandoffRefused:
            pass
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
