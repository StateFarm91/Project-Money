"""F-712: a task contract is validated field by field (a missing field is refused); F-713:
integration fails a lane that changed files outside its contract's owned paths."""
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import integrate as I  # noqa: E402
import task_contract as T  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_w4_fmbatch1_integrate import _git, _repo  # noqa: E402

GOOD = {"base_sha": "abc1234", "objective": "Build the thing to its acceptance text",
        "owned_paths": ["src/feature/*"], "authority": "BUILD_ONLY",
        "budget": {"max_hours": 2, "max_spend_cad": 0}, "dependencies": [],
        "outputs": ["the thing"], "tests": ["tests/test_thing.py"], "sentinel": "lane DONE"}


def _refused(c):
    try:
        T.validate(c)
    except T.ContractRefused as exc:
        return str(exc)
    raise AssertionError(f"accepted {c}")


def test_validation():
    assert T.validate(dict(GOOD)) == GOOD
    for f in T.FIELDS:
        c = dict(GOOD)
        del c[f]
        assert f in _refused(c)
    assert "authority" in _refused({**GOOD, "authority": "DEPLOY"})
    assert "budget" in _refused({**GOOD, "budget": {"max_hours": 0, "max_spend_cad": 0}})
    assert "owned_paths" in _refused({**GOOD, "owned_paths": []})
    assert "unknown" in _refused({**GOOD, "push_to": "main"})


def _lane_files(repo, name, files):
    _git(repo, "checkout", "-q", "-b", name, "integration")
    for f in files:
        p = repo / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", name)
    _git(repo, "checkout", "-q", "integration")


def test_integration_refuses_an_out_of_boundary_change():
    base, repo = _repo()
    head = _git(repo, "rev-parse", "integration")
    _lane_files(repo, "inside", ["src/feature/a.py"])
    _lane_files(repo, "outside", ["src/feature/b.py", "src/other/c.py"])
    contract = {**GOOD, "base_sha": head}
    assert T.boundary(repo, head, "inside", contract["owned_paths"]) == []
    assert T.boundary(repo, head, "outside", contract["owned_paths"]) == ["src/other/c.py"]
    try:
        I.enqueue("bad", "outside", contract={**contract, "authority": "DEPLOY"})
    except I.Refused as exc:
        assert "task contract refused" in str(exc)
    else:
        raise AssertionError("an invalid contract was queued")
    I.enqueue("outside", "outside", contract=contract)
    out = I.next_lane(target="integration", repo=repo)
    assert out["merged"] is False and "owned_paths boundary" in out["why"], out
    assert _git(repo, "rev-parse", "integration") == head
    I._save({"queue": [], "done": []})
    I.enqueue("inside", "inside", contract=contract)
    assert I.next_lane(target="integration", repo=repo)["merged"] is True


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
