"""F-462: a scoped lease (ops/lock.py --scope) does not wait behind the global heartbeat
lease or another lane's; the same scope still excludes; unscoped behaviour is unchanged."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

LOCK_PY = Path(__file__).resolve().parents[2] / "ops" / "lock.py"


def _run(d, *args):
    r = subprocess.run([sys.executable, str(Path(d) / "lock.py"), *args],
                       capture_output=True, text=True, cwd=d)
    return r.returncode, r.stdout


def test_scopes_are_independent_and_each_still_excludes():
    with TemporaryDirectory() as d:
        shutil.copy(LOCK_PY, Path(d) / "lock.py")
        assert _run(d, "acquire", "heartbeat-1")[0] == 0                 # global lease
        assert _run(d, "acquire", "heartbeat-2")[0] == 3                 # global still excludes
        assert _run(d, "acquire", "research-1", "--scope", "research")[0] == 0
        assert _run(d, "acquire", "drafting-1", "--scope", "drafting")[0] == 0
        assert _run(d, "acquire", "research-2", "--scope", "research")[0] == 3
        rc, out = _run(d, "leases")
        held = json.loads(out)
        assert held["global"]["session"] == "heartbeat-1"
        assert held["research"]["session"] == "research-1"
        assert held["drafting"]["session"] == "drafting-1"
        assert _run(d, "release", "research-1", "--scope", "research")[0] == 0
        assert _run(d, "acquire", "research-2", "--scope", "research")[0] == 0
        assert _run(d, "status")[1].strip().startswith("{")              # unscoped unchanged


def test_a_bad_scope_is_refused():
    with TemporaryDirectory() as d:
        shutil.copy(LOCK_PY, Path(d) / "lock.py")
        assert _run(d, "acquire", "x", "--scope", "../LOCK")[0] == 2
        assert not (Path(d) / "LOCK").exists()


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
