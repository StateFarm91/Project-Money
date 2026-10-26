"""F-455: a lane's context pack carries its own rows' requirement, gap, files and tests, and
nothing else; unknown rows are named; a lane's enrolled rows drive the pack."""
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import board as B  # noqa: E402
import context_pack as CP  # noqa: E402
import registry as R  # noqa: E402


def test_pack_holds_only_the_named_rows():
    p = CP.build(["F-485", "F-467", "#8", "F-999999"])
    ids = [r["row"] for r in p["rows"]]
    assert ids == ["F-485", "F-467", "#8"]
    f485 = p["rows"][0]
    assert f485["requirement"] and "deadlock" in (f485["requirement"] + f485["title"]).lower()
    assert f485["gap"] and f485["next_action"]
    assert p["unknown_rows"] == ["F-999999"]
    assert all(r["row"] in ("F-485", "F-467", "#8") for r in p["rows"])
    assert p["files_to_read_first"] and all(f.endswith(".py") for f in p["files_to_read_first"])
    assert set(p["files_to_read_first"]) == {f for r in p["rows"] for f in r.get("files") or []}
    md = CP.to_markdown(p)
    assert "## F-485" in md and "F-451" not in md


def test_lane_enrolled_rows_drive_the_pack():
    with TemporaryDirectory() as d:
        env = {**os.environ, "BRAMBLELOOP_JOB_REGISTRY": str(Path(d) / "JOBS.json")}
        subprocess.run([sys.executable, str(OPS / "registry.py"), "enrol", "lane-x",
                        str(Path(d) / "x.log"), "--rows", "F-462,F-464"], check=True,
                       capture_output=True, env=env)
        reg_path = Path(d) / "JOBS.json"
        lane = json.loads(reg_path.read_text())["jobs"]["lane-x"]
        p = CP.build(lane["rows"], lane=lane)
        assert [r["row"] for r in p["rows"]] == ["F-462", "F-464"]
        assert p["lane"]["rows"] == ["F-462", "F-464"]


def test_cli_refuses_without_rows():
    r = subprocess.run([sys.executable, str(OPS / "context_pack.py")], capture_output=True,
                       text=True)
    assert r.returncode == 2 and "no rows" in r.stdout


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
