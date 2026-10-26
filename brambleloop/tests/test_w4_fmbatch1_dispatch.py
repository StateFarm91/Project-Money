"""F-494: READY build work becomes advisory dispatch cards (enrol command, context pack,
brief); held, claimed or non-READY work is skipped; nothing is started, pushed or deployed."""
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import dispatch as D  # noqa: E402

READY = [{"requirement_id": 8, "title": "Proof Stack", "state": "READY", "priority": 1},
         {"requirement_id": 20, "title": "Owned audience", "state": "READY", "priority": 2,
          "claimed_by": "session-x"},
         {"requirement_id": 21, "title": "Creators", "state": "PARKED", "priority": 3},
         {"requirement_id": "F-485", "title": "Deadlock", "state": "READY", "priority": 4},
         {"requirement_id": 23, "title": "Kill table", "state": "READY", "priority": 5}]


def test_cards_for_ready_unheld_work_only():
    reg = {"jobs": {"lane-23": {"rows": ["#23"], "integrated": None, "role": "work"}}}
    c = D.cards(READY, registry_data=reg, limit=5)
    assert [k["task"] for k in c["cards"]] == ["#8", "F-485"]
    why = {s["task"]: s["why"] for s in c["skipped"]}
    assert "claimed" in why["#20"] and "PARKED" in why[21] and "held" in why["#23"]
    k = c["cards"][0]
    assert "--rows #8" in k["enrol"] and "context_pack.py --rows #8" in k["context_pack"]
    assert "ops/deploy.sh" in k["brief"] and "per-SHA approval" in k["brief"]
    assert (c["advisory"], c["starts_sessions"], c["pushes"], c["deploys"]) == \
        (True, False, False, False)


def test_cli_reads_a_saved_ready_list_and_writes_cards_only():
    with TemporaryDirectory() as d:
        src = Path(d) / "build.json"
        src.write_text(json.dumps({"queue": {"ready": READY}}))
        out = Path(d) / "DISPATCH.md"
        env = {**os.environ, "BRAMBLELOOP_JOB_REGISTRY": str(Path(d) / "JOBS.json")}
        r = subprocess.run([sys.executable, str(OPS / "dispatch.py"), "--ready-json", str(src),
                            "--out", str(out), "--limit", "1"], capture_output=True,
                           text=True, env=env, cwd=d)
        assert r.returncode == 0, r.stdout + r.stderr
        text = out.read_text()
        assert "advisory; nothing was started" in text and "## #8" in text
        assert "F-485" not in text                                       # --limit 1
        assert sorted(p.name for p in Path(d).iterdir()) == ["DISPATCH.md", "build.json"]


def test_refuses_without_a_ready_source():
    r = subprocess.run([sys.executable, str(OPS / "dispatch.py")], capture_output=True,
                       text=True)
    assert r.returncode == 2 and "refused" in r.stdout


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
