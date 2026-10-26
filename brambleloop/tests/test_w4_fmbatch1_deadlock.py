"""F-485: mutually waiting lanes are detected as a deadlock (wait-for graph across
ops/registry.py lanes), dangling waits are named, and integration clears a lane's waits."""
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
    reg = R.Registry(Path(d) / "JOBS.json", git=lambda *a: (1, ""))
    for n in ("a", "b", "c", "d"):
        reg.enrol(B.Job(name=n, log=Path(d) / f"{n}.log"), lane=n)
    return reg


def test_a_cycle_is_a_deadlock_and_a_chain_is_not():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        assert reg.wait("a", ["b"], why="needs b's schema")["deadlocked"] is False
        assert reg.wait("b", ["c"], why="needs c's fixture")["deadlocked"] is False
        out = reg.wait("c", ["a"], why="needs a's API")
        assert out["deadlocked"] is True and out["cycles"] == [["a", "b", "c"]], out
        assert reg.survey()["deadlocks"]["cycles"] == [["a", "b", "c"]]
        cleared = reg.unwait("c")
        assert cleared["deadlocked"] is False and cleared["edges"] == {"a": ["b"], "b": ["c"]}


def test_two_lane_cycle_and_dangling_waits():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.wait("a", ["d"], why="x")
        out = reg.wait("d", ["a", "ghost"], why="y")
        assert out["cycles"] == [["a", "d"]]
        assert out["dangling"] == [{"lane": "d", "waits_on": "ghost", "why": "not enrolled"}]
        try:
            reg.wait("a", ["b"], why="  ")
            raise AssertionError("a wait with no reason was recorded")
        except ValueError:
            pass


def test_an_integrated_lane_leaves_the_graph_and_its_waiter_is_dangling():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.wait("a", ["b"], why="x")
        reg.wait("b", ["a"], why="y")
        data = reg.load()
        data["jobs"]["b"]["integrated"] = {"commit": "0" * 40}
        reg._save(data)
        out = R.wait_for_cycles(reg.load())
        assert out["deadlocked"] is False
        assert out["dangling"][0]["lane"] == "a" and "no longer live" in out["dangling"][0]["why"]


def test_cli_exit_code_reports_the_deadlock():
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.wait("a", ["b"], why="x")
        env = {**os.environ, "BRAMBLELOOP_JOB_REGISTRY": str(Path(d) / "JOBS.json")}
        r = subprocess.run([sys.executable, str(Path(OPS) / "registry.py"), "wait", "b", "a",
                            "needs", "a"], capture_output=True, text=True, env=env)
        assert r.returncode == 1 and json.loads(r.stdout)["cycles"] == [["a", "b"]], r.stdout


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
