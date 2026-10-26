"""F-476: a second live lane on the same requirement rows or the same question is refused
before dispatch; integrated lanes and observers do not count."""
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = str(Path(__file__).resolve().parents[2] / "ops")
sys.path.insert(0, OPS)
import board as B  # noqa: E402
import registry as R  # noqa: E402


def _reg(d):
    return R.Registry(Path(d) / "JOBS.json", git=lambda *a: (1, ""))


def _job(d, n):
    return B.Job(name=n, log=Path(d) / f"{n}.log")


def test_same_rows_or_same_question_is_refused():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.enrol(_job(d, "a"), rows=["F-485", "f-467"], question="Detect lane deadlocks?")
        for kw in ({"rows": ["F-467"]}, {"question": "detect   LANE deadlocks"}):
            try:
                reg.enrol(_job(d, "b"), **kw)
                raise AssertionError(f"duplicate accepted: {kw}")
            except R.DuplicateWork as exc:
                assert exc.duplicates[0]["lane"] == "a"
        assert reg.enrol(_job(d, "c"), rows=["F-451"], question="a different question")


def test_integrated_lanes_and_re_enrolment_do_not_block():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.enrol(_job(d, "a"), rows=["F-485"])
        assert reg.enrol(_job(d, "a"), rows=["F-485"])          # the same lane, again
        data = reg.load()
        data["jobs"]["a"]["integrated"] = {"commit": "0" * 40}
        reg._save(data)
        assert reg.enrol(_job(d, "b"), rows=["F-485"])


def test_cli_refuses_a_duplicate():
    with TemporaryDirectory() as d:
        env = {**os.environ, "BRAMBLELOOP_JOB_REGISTRY": str(Path(d) / "JOBS.json")}
        cmd = [sys.executable, str(Path(OPS) / "registry.py"), "enrol"]
        ok = subprocess.run(cmd + ["a", str(Path(d) / "a.log"), "--rows", "F-001"],
                            capture_output=True, text=True, env=env)
        assert ok.returncode == 0, ok.stdout + ok.stderr
        dup = subprocess.run(cmd + ["b", str(Path(d) / "b.log"), "--rows", "F-001"],
                             capture_output=True, text=True, env=env)
        assert dup.returncode == 2 and "duplicate work" in dup.stdout, dup.stdout
        assert json.loads(ok.stdout)["rows"] == ["F-001"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
