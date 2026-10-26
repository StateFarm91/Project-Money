"""F-492: lane records carry checkable stop/escalation criteria; survey names live lanes past
them; malformed criteria are refused; integrated lanes are not reported."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = str(Path(__file__).resolve().parents[2] / "ops")
sys.path.insert(0, OPS)
import board as B  # noqa: E402
import registry as R  # noqa: E402

STOP = {"escalate_after_hours": 4, "stop_after_hours": 8, "escalate_to": "coordinator",
        "stop_when": "push what is green and hand back"}


def _reg(d):
    return R.Registry(Path(d) / "JOBS.json", git=lambda *a: (1, ""))


def test_criteria_are_validated():
    for bad in ({"escalate_to": "x", "stop_when": "y"},
                {"stop_after_hours": 2, "escalate_after_hours": 5, "escalate_to": "x",
                 "stop_when": "y"},
                {"stop_after_hours": 2},
                {"stop_after_hours": 2, "escalate_to": "x", "stop_when": "y", "extra": 1}):
        try:
            R.validate_stop(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)


def test_survey_reports_escalate_then_stop():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.enrol(B.Job(name="a", log=Path(d) / "a.log"), stop=STOP)
        reg.enrol(B.Job(name="b", log=Path(d) / "b.log"))
        start = datetime.fromisoformat(reg.load()["jobs"]["a"]["enrolled_utc"])
        at = lambda h: (start + timedelta(hours=h)).timestamp()  # noqa: E731
        assert R.stop_states(reg.load(), now=at(1)) == []
        esc = R.stop_states(reg.load(), now=at(5))
        assert [(x["lane"], x["state"]) for x in esc] == [("a", "escalate")]
        assert esc[0]["escalate_to"] == "coordinator"
        assert R.stop_states(reg.load(), now=at(9))[0]["state"] == "stop"
        assert "stop_criteria" in reg.survey(now=at(9))
        reg.integrate("a", "abc123")
        assert R.stop_states(reg.load(), now=at(9)) == []


def test_cli_accepts_stop_json_and_refuses_bad_json():
    with TemporaryDirectory() as d:
        env = {"BRAMBLELOOP_JOB_REGISTRY": str(Path(d) / "JOBS.json"), "PATH": "/usr/bin:/bin"}
        ok = subprocess.run([sys.executable, f"{OPS}/registry.py", "enrol", "x",
                             str(Path(d) / "x.log"), "--stop", json.dumps(STOP)],
                            capture_output=True, text=True, env=env)
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert json.loads(ok.stdout)["stop"]["stop_after_hours"] == 8.0
        bad = subprocess.run([sys.executable, f"{OPS}/registry.py", "enrol", "y",
                              str(Path(d) / "y.log"), "--stop", "{not json"],
                             capture_output=True, text=True, env=env)
        assert bad.returncode == 2 and "refused" in bad.stdout


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
