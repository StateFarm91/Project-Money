"""ENG-AUTOCODER: the in-production coding team (D-OWNER-AUTOCODER, 2026-11-20).

OFFLINE TEST -- NOT PRODUCTION EVIDENCE. No network, no real model, no real spend. The model is
a scripted test double behind the REAL gateway (`failover.job_gateway` -> `ModelGateway`), so
reservations, the ceiling check and billing to the ledger are the production code paths; the
git host is a local repository in a temp directory.

Covers:
A. the refspec allowlist: only refs/heads/auto/* is pushable, in the rail and in each host;
B. the path denylist: deploy/boot guard, release records, spend, gates, auth, authority,
   approvals and the autocoder itself are refused -- in the rail, the workspace and the push;
C. test-weakening detection: deleted tests, removed tests/assertions, skips, vacuity pragmas,
   constant-true assertions and early returns are refused; a strengthened test passes;
D. secrets and spend/network/execution paths are refused (and checked before a test runs);
E. budget ceilings bind: per request CA$ and tokens, wall time, the monthly sub-ceiling, and
   environment can only tighten; a run over budget makes no model call;
F. the reviewer must SHIP before any push (and SHIP binds to the exact diff);
G. end to end with the stub model on a toy ECR in a temp repository: an auto/ecr-<id> branch
   on top of the base, the request `code_submitted` with the SHA, spend in the ledger; and the
   refusals (weakened test, review BLOCK, failing mandatory suite) push nothing;
H. kill switch OFF by default; enabled without the token -> UNKNOWN with a named blocker;
I. picking: priority, engine demand, cooldowns; the Mission Control panel and readback;
J. mutations of each rail are killed by the checks above.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_eng_autocoder.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("ANTHROPIC_API_KEY", "BRAMBLELOOP_GITHUB_TOKEN", "BRAMBLELOOP_AUTOCODER_ENABLED",
           "BRAMBLELOOP_AUTOCODER_BASE", "RAILWAY_GIT_COMMIT_SHA",
           "BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", "BRAMBLELOOP_MODEL_ROUTES"):
    os.environ.pop(_k, None)

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.authority import classes  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry  # noqa: E402
from brambleloop.gateway import failover, routing  # noqa: E402
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402
from brambleloop.improve import autocoder as AC  # noqa: E402
from brambleloop.improve import autocoder_safety as S  # noqa: E402
from brambleloop.improve import ecr  # noqa: E402
from brambleloop.improve.autocoder_git import GitHubHost, LocalGitHost  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, handlers  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SRC = "brambleloop/src/brambleloop/"
T = "brambleloop/tests/"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='autocoder-')}/a.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _file_ecr(db, *, priority="P1", title="add() subtracts", module="brambleloop.toy",
              defect_class="recurring_defect", evidence=None, occurrences=1):
    got = None
    for _ in range(occurrences):
        got = ecr.file(db, defect_class=defect_class, department="engineering", module=module,
                       title=title, problem="toy.add(2, 3) returns -1",
                       evidence=evidence or {"examples": ["add(2,3)=-1"]},
                       proposed_change="make add() add, with a test",
                       acceptance_criteria=["add(2, 3) == 5"], priority=priority)
    return got["id"]


# ---- A. refspec allowlist -------------------------------------------------------------------

ALLOWED_REFS = ("auto/ecr-1", "refs/heads/auto/ecr-42", "auto/ecr-7/retry-2")
REFUSED_REFS = ("claude/repository-setup-nc9x6o", "main", "refs/heads/main",
                "refs/heads/claude/repository-setup-nc9x6o", "refs/tags/v1", "+auto/ecr-1",
                "auto/ecr-1:refs/heads/main", "HEAD:refs/heads/main", "auto/../main", "auto/",
                "refs/heads/autox/ecr-1", "refs/heads/auto", "auto/x.lock", "auto/a b",
                "claude/w6-release-1", "refs/remotes/origin/auto/x", "", "auto/@{1}")


def refspec_failures() -> list[str]:
    out = []
    for ref in ALLOWED_REFS:
        try:
            S.assert_ref_allowed(ref)
        except S.RefRefused as exc:
            out.append(f"allowed ref {ref!r} refused: {exc}")
    for ref in REFUSED_REFS:
        try:
            S.assert_ref_allowed(ref)
            out.append(f"ref {ref!r} was allowed")
        except S.RefRefused:
            pass
    return out


def test_a_only_auto_refs_pass_the_allowlist():
    assert refspec_failures() == []
    assert S.branch_for(12) == "refs/heads/auto/ecr-12"


def _toy_repo() -> tuple[Path, str]:
    """A local repository with the brambleloop layout, a buggy toy module and its test."""
    repo = Path(tempfile.mkdtemp(prefix="toy-origin-"))
    (repo / "brambleloop/src/brambleloop").mkdir(parents=True)
    (repo / "brambleloop/tests").mkdir(parents=True)
    (repo / "ops").mkdir()
    (repo / "brambleloop/src/brambleloop/__init__.py").write_text("")
    (repo / "brambleloop/src/brambleloop/toy.py").write_text(
        "def add(a, b):\n    return a - b\n")
    (repo / "brambleloop/tests/test_toy.py").write_text(TOY_TEST)
    (repo / "ops/deploy_guard.py").write_text("GUARD = True\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@invalid"}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"],
                 ["branch", "claude/repository-setup-nc9x6o"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                         text=True, check=True).stdout.strip()
    return repo, sha


TOY_TEST = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop import toy


def test_add_zero():
    assert toy.add(2, 0) == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("toy ok")
'''


def _ref(repo: Path, ref: str) -> str:
    out = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=repo,
                         capture_output=True, text=True)
    return out.stdout.strip()


def test_a_hosts_refuse_non_auto_refs_before_writing_anything():
    repo, base = _toy_repo()
    host = LocalGitHost(repo)
    files = {SRC + "toy.py": "def add(a, b):\n    return a + b\n"}
    for ref in REFUSED_REFS:
        try:
            host.push(ref, base, files, "x")
            raise AssertionError(f"local host pushed {ref!r}")
        except S.RefRefused:
            pass
    assert _ref(repo, "refs/heads/main") == base
    assert _ref(repo, "refs/heads/claude/repository-setup-nc9x6o") == base
    calls = []

    def opener(req, timeout=0):  # records; must never be reached for a refused ref
        calls.append(req.full_url)
        raise AssertionError("network reached")

    os.environ["BRAMBLELOOP_GITHUB_TOKEN"] = "test-not-a-token"
    try:
        gh = GitHubHost("owner/repo", opener=opener)
        for ref in ("main", "claude/repository-setup-nc9x6o", "refs/heads/main"):
            try:
                gh.push(ref, base, files, "x")
                raise AssertionError(f"github host pushed {ref!r}")
            except S.RefRefused:
                pass
    finally:
        os.environ.pop("BRAMBLELOOP_GITHUB_TOKEN", None)
    assert calls == []


class _FakeGitHub:
    """GitHub's REST API, as far as the autocoder uses it. Records every request."""

    def __init__(self, base: str, *, ref_exists: bool = False, tarball: bytes = b""):
        self.base, self.ref_exists, self.tarball = base, ref_exists, tarball
        self.requests: list[tuple[str, str, dict | None]] = []

    def __call__(self, req, timeout=0):
        import io
        import urllib.error

        body = json.loads(req.data) if req.data else None
        path = req.full_url.split("/repos/owner/repo", 1)[1]
        self.requests.append((req.get_method(), path, body))
        assert req.get_header("Authorization") == "Bearer test-not-a-token"

        def resp(obj, raw=None):
            payload = raw if raw is not None else json.dumps(obj).encode()

            class R(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False
            return R(payload)
        m = req.get_method()
        if m == "GET" and path.startswith("/commits/"):
            return resp({"sha": self.base})
        if m == "GET" and path.startswith("/tarball/"):
            return resp(None, raw=self.tarball)
        if m == "GET" and path.startswith("/git/commits/"):
            return resp({"tree": {"sha": "t" * 40}})
        if m == "POST" and path == "/git/blobs":
            return resp({"sha": "b" * 40})
        if m == "POST" and path == "/git/trees":
            return resp({"sha": "e" * 40})
        if m == "POST" and path == "/git/commits":
            return resp({"sha": "c" * 40})
        if m == "POST" and path == "/git/refs" and self.ref_exists:
            raise urllib.error.HTTPError(req.full_url, 422, "exists", {},
                                         io.BytesIO(b'{"message": "Reference already exists"}'))
        if path.startswith("/git/refs"):
            return resp({"ref": body.get("ref")})
        raise AssertionError(f"unexpected request {m} {path}")


def test_a_the_github_host_pushes_only_the_auto_ref_through_the_git_data_api():
    import io
    import tarfile

    base = "a" * 40
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"def add(a, b):\n    return a - b\n"
        info = tarfile.TarInfo(f"owner-repo-{base[:7]}/{SRC}toy.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        evil = tarfile.TarInfo(f"owner-repo-{base[:7]}/link")
        evil.type, evil.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(evil)
    os.environ["BRAMBLELOOP_GITHUB_TOKEN"] = "test-not-a-token"
    try:
        fake = _FakeGitHub(base, tarball=buf.getvalue())
        gh = GitHubHost("owner/repo", opener=fake)
        dest = Path(tempfile.mkdtemp()) / "ws"
        dest.mkdir()
        assert gh.materialize("claude/w6-INTEG7", dest) == base
        assert (dest / SRC / "toy.py").read_text().endswith("a - b\n")
        assert not (dest / "link").exists()          # symlinks are never extracted
        files = {SRC + "toy.py": "def add(a, b):\n    return a + b\n"}
        assert gh.push("auto/ecr-5", base, files, "m") == "c" * 40
        refs = [r for r in fake.requests if r[1].startswith("/git/refs")]
        assert refs == [("POST", "/git/refs", {"ref": "refs/heads/auto/ecr-5", "sha": "c" * 40})]
        commit = next(r for r in fake.requests if r[1] == "/git/commits")
        assert commit[2]["parents"] == [base]
        fake2 = _FakeGitHub(base, ref_exists=True)
        GitHubHost("owner/repo", opener=fake2).push("auto/ecr-5", base, files, "m")
        assert fake2.requests[-1][:2] == ("PATCH", "/git/refs/heads/auto/ecr-5")
        writes = [r for r in fake.requests + fake2.requests if r[0] != "GET"]
        assert writes and all("repository-setup" not in r[1] and "/main" not in r[1]
                              for r in writes)
    finally:
        os.environ.pop("BRAMBLELOOP_GITHUB_TOKEN", None)


# ---- B. path denylist -------------------------------------------------------------------------

PROTECTED_SAMPLES = (
    "ops/deploy_guard.py", "ops/deploy.sh", "ops/hooks/pre-push", ".github/workflows/x.yml",
    "brambleloop/release/RELEASE_x.json", "brambleloop/Dockerfile", "brambleloop/run_tests.sh",
    SRC + "ops/release_record.py", SRC + "app/main.py", SRC + "app/worker_entry.py",
    SRC + "gateway/anthropic.py", SRC + "gateway/model_gateway.py", SRC + "gateway/routing.py",
    SRC + "finance/spend_policy.py", SRC + "finance/reservations.py",
    SRC + "gates/child_safety.py", SRC + "gates/small_parts.py",
    SRC + "app/security.py", SRC + "app/command_center/auth.py",
    SRC + "authority/policy.py", SRC + "app/command_center/approvals.py",
    SRC + "ops/standing_grants.py", SRC + "agents/registry.py", SRC + "runtime/worker.py",
    SRC + "improve/autocoder.py", SRC + "improve/autocoder_safety.py",
    SRC + "improve/autocoder_git.py", T + "test_eng_autocoder.py", T + "test_vacuity.py",
    T + "test_w4_resume_runner.py", "CLAUDE.md", "brambleloop/DECISION_LOG.md",
    "../etc/passwd", "/etc/passwd", SRC + ".env", SRC + "x.so", "brambleloop/README.md")
EDITABLE_SAMPLES = (SRC + "improve/ecr.py", SRC + "cir/compiler_extra.py",
                    T + "test_toy.py", T + "test_new_thing.py", SRC + "creative/notes.md")


def path_failures() -> list[str]:
    out = [f"{p} was editable" for p in PROTECTED_SAMPLES if not S.path_refusal(p)]
    out += [f"{p} refused: {S.path_refusal(p)}" for p in EDITABLE_SAMPLES if S.path_refusal(p)]
    return out


def test_b_protected_paths_are_refused_and_ordinary_ones_are_not():
    assert path_failures() == []


def test_b_a_changeset_touching_a_protected_path_is_refused_whole():
    changes = {SRC + "toy.py": ("a = 1\n", "a = 2\n"),
               SRC + "gates/child_safety.py": ("MIN_AGE = 3\n", "MIN_AGE = 0\n")}
    got = S.check_changeset(changes)
    assert any("gates/child_safety.py" in r and "protected" in r for r in got), got


def test_b_the_workspace_refuses_a_protected_write_and_leaves_the_file():
    root = Path(tempfile.mkdtemp())
    (root / "ops").mkdir()
    (root / "ops/deploy_guard.py").write_text("GUARD = True\n")
    ws = AC.Workspace(root)
    obs = ws.apply({"op": "edit", "path": "ops/deploy_guard.py", "old": "True", "new": "False"})
    assert "refused" in obs and "protected" in obs, obs
    assert (root / "ops/deploy_guard.py").read_text() == "GUARD = True\n"
    assert ws.changes == {}
    obs = ws.apply({"op": "create", "path": "../escape.py", "content": "x"})
    assert "refused" in obs and not (root.parent / "escape.py").exists()


def test_b_the_push_refuses_a_protected_path_even_with_a_forged_review():
    repo, base = _toy_repo()
    files = {"ops/deploy_guard.py": "GUARD = False\n"}
    try:
        LocalGitHost(repo).push("auto/ecr-1", base, files, "x")
        raise AssertionError("pushed a protected path")
    except PermissionError:
        pass
    assert _ref(repo, "refs/heads/auto/ecr-1") == ""


# ---- C. test weakening --------------------------------------------------------------------------

BASE_TEST = '''def test_one():
    assert f(1) == 2
    assert f(2) == 3


def test_two():
    assert g() is None
'''
WEAKENED = (
    ("assertion removed", BASE_TEST.replace("    assert f(2) == 3\n", "")),
    ("test removed", BASE_TEST.split("\n\n\ndef test_two")[0] + "\n"),
    ("skip added", "import pytest\n" + BASE_TEST.replace(
        "def test_two():", "@pytest.mark.skip\ndef test_two():")),
    ("vacuity pragma", BASE_TEST + "\n\ndef test_three():\n    for x in xs:  # vacuity-ok: n\n"
                                   "        assert x\n"),
    ("assert True", BASE_TEST.replace("assert g() is None", "assert g() is None\n    assert True")),
    ("assert or True", BASE_TEST.replace("assert g() is None", "assert g() is None or True")),
    ("tautology", BASE_TEST.replace("assert g() is None", "assert g() is None\n    assert g() == g()")),
    ("early return", BASE_TEST.replace("def test_two():\n", "def test_two():\n    return\n")),
    ("deleted", None),
    ("unparseable", BASE_TEST + "\ndef broken(:\n"),
)
STRENGTHENED = BASE_TEST + "\n\ndef test_three():\n    assert f(3) == 4\n"


def weakening_failures() -> list[str]:
    out = []
    for label, new in WEAKENED:
        if not S.test_weakening(T + "test_x.py", BASE_TEST, new):
            out.append(f"weakening not detected: {label}")
    if S.test_weakening(T + "test_x.py", BASE_TEST, STRENGTHENED):
        out.append("a strengthened test was refused")
    return out


def test_c_every_weakening_is_refused_and_strengthening_is_not():
    assert weakening_failures() == []
    refusals = S.check_changeset({T + "test_x.py": (BASE_TEST, WEAKENED[0][1])})
    assert any("assertion" in r for r in refusals), refusals


# ---- D. secrets and spend paths ------------------------------------------------------------------

SECRET_LINES = (
    'KEY = "sk-ant-api03-' + "A" * 40 + '"', 'tok = "ghp_' + "b" * 36 + '"',
    "-----BEGIN RSA PRIVATE KEY-----", 'api_key = "' + "Z" * 32 + '"',
    'OPENAI = "sk-proj-' + "c" * 30 + '"', "aws = 'AKIA" + "Q" * 16 + "'")
SPEND_LINES = (
    "    gateway.complete_json('x@1', agent='a', values={})",
    "    urllib.request.urlopen('https://example.com')",
    "    import subprocess", "    requests.post(url, json=body)",
    "    os.environ['X'] = 'y'", "    eval(text)", "    open('/proc/1/environ').read()",
    "    failover.job_gateway(db, 'autocoder.step', registry=r, agent='a')",
    "    MONTHLY_CEILING_CAD = 500")


def rail_failures() -> list[str]:
    out = []
    for line in SECRET_LINES:
        if not S.secret_findings(SRC + "m.py", "x = 1\n", f"x = 1\n{line}\n"):
            out.append(f"secret not found: {line[:30]}")
    for line in SPEND_LINES:
        if not S.spend_path_findings(SRC + "m.py", "def f():\n    pass\n",
                                     f"def f():\n{line}\n"):
            out.append(f"spend/network path not found: {line.strip()[:40]}")
    if S.secret_findings(SRC + "m.py", "", "x = 1\nname = 'token_count'\n"):
        out.append("an ordinary line read as a secret")
    return out


def test_d_secrets_and_spend_network_exec_paths_are_refused():
    assert rail_failures() == []
    test_exec = S.test_execution_findings(T + "test_x.py", "", "import subprocess\n")
    assert test_exec and "execution" in test_exec[0], test_exec


def test_d_model_written_code_is_not_executed_past_the_rails():
    root = Path(tempfile.mkdtemp())
    (root / "brambleloop/tests").mkdir(parents=True)
    (root / "brambleloop/tests/test_x.py").write_text("def test_a():\n    assert 1 == 1\n")
    ran = []
    ws = AC.Workspace(root, runner=lambda w, s, t: ran.append(s) or {
        "suite": s, "rc": 0, "passed": True, "seconds": 0, "tail": ""})
    ws.apply({"op": "edit", "path": T + "test_x.py", "old": "assert 1 == 1",
              "new": "assert 1 == 1\n    import subprocess; subprocess.run(['true'])"})
    obs = ws.apply({"op": "test", "suite": "tests/test_x.py"})
    assert obs.startswith("test not run") and ran == [], obs


def test_d_tests_run_with_a_scrubbed_environment():
    os.environ["BRAMBLELOOP_SECRET_PROBE"] = "must-not-leak"
    try:
        env = AC._clean_env(Path(tempfile.mkdtemp()))
    finally:
        os.environ.pop("BRAMBLELOOP_SECRET_PROBE", None)
    assert "BRAMBLELOOP_SECRET_PROBE" not in env and "DATABASE_URL" not in env
    assert set(env) == {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE",
                        "PYTHONPATH", "PYTHONHASHSEED"}


# ---- the stub model (test double) behind the real gateway ------------------------------------------

@dataclass
class StubModel:
    """A transport stand-in, priced, scripted per call. Not a model of judgement."""

    model: str
    script: object
    name: str = "anthropic"
    cost_per_1k_input_cad: float = 0.004
    cost_per_1k_output_cad: float = 0.02
    calls: list = field(default_factory=list)

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse:
        self.calls.append(user)
        text = json.dumps(self.script(system, user, len(self.calls)))
        return ModelResponse(text=text, provider=self.name, model=self.model,
                             input_tokens=max(1, len(user) // 4),
                             output_tokens=max(1, len(text) // 4), latency_ms=1.0,
                             stop_reason="end_turn")


def _gateways(db, step_script, review_script, log: dict):
    def make(task):
        script = step_script if task == AC.STEP_TASK else review_script
        stub_holder = {}

        def factory(model):
            stub = StubModel(model=model, script=script)
            stub_holder["stub"] = stub
            log.setdefault(task, []).append(stub)
            return stub
        return failover.job_gateway(db, task, registry=Registry(db), agent=AC.AGENT,
                                    job_id=None, provider_factory=factory)
    return make


def _toy_steps(weaken: bool = False):
    toy, test = SRC + "toy.py", T + "test_toy.py"
    fix = [{"op": "edit", "path": toy, "old": "return a - b", "new": "return a + b"}]
    if weaken:
        fix.append({"op": "edit", "path": test, "old": "    assert toy.add(2, 0) == 2\n",
                    "new": "    toy.add(2, 0)\n"})
    else:
        fix.append({"op": "edit", "path": test, "old": "    assert toy.add(2, 0) == 2\n",
                    "new": "    assert toy.add(2, 0) == 2\n\n\ndef test_add_positive():\n"
                           "    assert toy.add(2, 3) == 5\n"})
    fix.append({"op": "test", "suite": "tests/test_toy.py"})

    def script(system, user, n):
        if n == 1:
            return {"plan": "read the module", "done": False,
                    "actions": [{"op": "read", "path": toy}]}
        if n == 2:
            return {"plan": "fix add and prove it", "done": False, "actions": fix}
        return {"plan": "finished", "actions": [], "targets": ["tests/test_toy.py"],
                "done": True, "summary": "add() subtracted; it now adds, proven by a test."}
    return script


def _review(verdict="SHIP", **overrides):
    checks = {k: True for k in AC.REVIEW_CHECKS} | overrides

    def script(system, user, n):
        return {"verdict": verdict, "checks": checks, "reasons": ["checked the diff"]}
    return script


def _runner(mandatory_ok=True, ran=None):
    ran = [] if ran is None else ran

    def runner(ws, suite, timeout):
        ran.append(suite)
        if suite in AC.MANDATORY_SUITES:
            # The two mandatory suites need the whole repository; in the toy repository the
            # gate's use of their result is what is under test. Production runs them for real.
            return {"suite": suite, "rc": 0 if mandatory_ok else 1, "passed": mandatory_ok,
                    "seconds": 0.0, "tail": "stand-in"}
        return AC.run_suite(ws, suite, timeout)
    return runner, ran


def _env(**extra):
    return {"BRAMBLELOOP_AUTOCODER_ENABLED": "1", "BRAMBLELOOP_AUTOCODER_BASE": "main", **extra}


def _ledger(db) -> tuple[int, float]:
    with db.session() as s:
        n = s.scalar(select(func.count(CostEntry.id)).where(CostEntry.agent == AC.AGENT))
        v = s.scalar(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0)).where(
            CostEntry.agent == AC.AGENT))
    return int(n or 0), float(v or 0.0)


# ---- G. end to end ------------------------------------------------------------------------------

def test_g_end_to_end_toy_ecr_becomes_a_reviewed_auto_branch():
    db = _db()
    eid = _file_ecr(db)
    repo, base = _toy_repo()
    log: dict = {}
    runner, ran = _runner()
    out = AC.run(db, host=LocalGitHost(repo), runner=runner, env=_env(),
                 make_gateway=_gateways(db, _toy_steps(), _review(), log))
    assert out["status"] == AC.SUBMITTED, out
    assert out["branch"] == f"auto/ecr-{eid}" and out["work_done"] == 1
    sha = _ref(repo, f"refs/heads/auto/ecr-{eid}")
    assert sha == out["sha"] and len(sha) == 40
    parent = subprocess.run(["git", "rev-parse", f"{sha}^"], cwd=repo, capture_output=True,
                            text=True).stdout.strip()
    assert parent == base
    changed = subprocess.run(["git", "diff", "--name-only", base, sha], cwd=repo,
                             capture_output=True, text=True).stdout.split()
    assert sorted(changed) == sorted([T + "test_toy.py", SRC + "toy.py"]), changed
    shown = subprocess.run(["git", "show", f"{sha}:{SRC}toy.py"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert "return a + b" in shown
    # The production branch and main never move.
    assert _ref(repo, "refs/heads/main") == base
    assert _ref(repo, "refs/heads/claude/repository-setup-nc9x6o") == base
    # The targeted suite and both mandatory suites gated the push.
    assert "tests/test_toy.py" in ran and set(AC.MANDATORY_SUITES) <= set(ran)
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    ac = row["evidence"]["autocoder"]
    assert row["state"] == ecr.REVIEWED and ac["status"] == AC.SUBMITTED and ac["sha"] == sha
    assert ac["spent_cad"] > 0 and ac["tokens"] > 0
    # Every call went through the gateway and was billed to the autocoder agent.
    n, cad = _ledger(db)
    assert n == len(log[AC.STEP_TASK][0].calls) + len(log[AC.REVIEW_TASK][0].calls) == 4
    assert abs(cad - out["spent_cad"]) < 1e-6
    p = AC.panel(db, env=_env(BRAMBLELOOP_GITHUB_TOKEN="x"))
    assert p["counts"]["submitted"] == 1 and p["month_spend_cad"] > 0
    assert p["ecrs"][0]["branch"] == f"auto/ecr-{eid}"
    # A submitted request is not picked again.
    assert AC.pick(db) is None


def test_g_a_weakened_test_is_refused_and_nothing_is_pushed():
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    runner, _ran = _runner()
    out = AC.run(db, host=LocalGitHost(repo), runner=runner, env=_env(),
                 make_gateway=_gateways(db, _toy_steps(weaken=True), _review(), {}))
    assert out["status"] == AC.REFUSED and out["reason"] == "gate_rails", out
    assert any("assertion" in d or "lost" in d for d in out["detail"]), out["detail"]
    assert _ref(repo, f"refs/heads/auto/ecr-{eid}") == ""
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    assert row["evidence"]["autocoder"]["status"] == AC.REFUSED
    assert row["state"] == ecr.FILED


def test_g_a_failing_mandatory_suite_refuses_the_push():
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    runner, _ran = _runner(mandatory_ok=False)
    out = AC.run(db, host=LocalGitHost(repo), runner=runner, env=_env(),
                 make_gateway=_gateways(db, _toy_steps(), _review(), {}))
    assert out["status"] == AC.REFUSED and out["reason"] == "gate_tests", out
    assert _ref(repo, f"refs/heads/auto/ecr-{eid}") == ""


# ---- F. the reviewer must SHIP ------------------------------------------------------------------

def test_f_review_block_or_a_false_check_pushes_nothing():
    for script in (_review("BLOCK"), _review("SHIP", no_spend_paths=False),
                   _review("ship it", honest=True)):
        db = _db()
        eid = _file_ecr(db)
        repo, _base = _toy_repo()
        runner, _ran = _runner()
        out = AC.run(db, host=LocalGitHost(repo), runner=runner, env=_env(),
                     make_gateway=_gateways(db, _toy_steps(), script, {}))
        assert out["status"] == AC.REFUSED and out["reason"] == "review_block", out
        assert _ref(repo, f"refs/heads/auto/ecr-{eid}") == ""


def review_gate_failures() -> list[str]:
    """`submit` pushes only a SHIP review of exactly this diff."""
    out = []
    repo, base = _toy_repo()
    host = LocalGitHost(repo)
    changes = {SRC + "toy.py": ("def add(a, b):\n    return a - b\n",
                                "def add(a, b):\n    return a + b\n")}
    diff = S.unified_diff(changes)
    cases = (("no review", None),
             ("BLOCK", AC.Review(ship=False, diff_sha256=AC.diff_sha(diff), verdict="BLOCK")),
             ("other diff", AC.Review(ship=True, diff_sha256=AC.diff_sha(diff + "x"),
                                      verdict="SHIP")))
    for label, rv in cases:
        try:
            AC.submit(host, ecr_id=1, base_sha=base, changes=changes, review_=rv, message="m")
            out.append(f"pushed with {label}")
        except AC.PushRefused:
            pass
    if _ref(repo, "refs/heads/auto/ecr-1"):
        out.append("a branch exists after refused pushes")
    ok = AC.Review(ship=True, diff_sha256=AC.diff_sha(diff), verdict="SHIP")
    got = AC.submit(host, ecr_id=1, base_sha=base, changes=changes, review_=ok, message="m")
    if _ref(repo, "refs/heads/auto/ecr-1") != got["sha"]:
        out.append("a SHIP review of this diff did not push")
    return out


def test_f_submit_requires_a_ship_review_of_exactly_this_diff():
    assert review_gate_failures() == []


def review_ship_failures() -> list[str]:
    """`review` turns SHIP into ship=True only when every check is true."""
    db = _db()
    r = next(iter(ecr.listing(db))) if ecr.listing(db) else None
    if r is None:
        _file_ecr(db)
        r = ecr.listing(db)[0]
    out = []
    budget = AC.Budget(AC.limits({}), 0.0)
    for label, script, want in (("SHIP all true", _review(), True),
                                ("SHIP one false", _review(no_secrets=False), False),
                                ("BLOCK", _review("BLOCK"), False)):
        gw = _gateways(db, None, script, {})(AC.REVIEW_TASK)
        got = AC.review(r, "diff", "summary", {"suites": []}, budget, gw)
        if got.ship is not want:
            out.append(f"{label}: ship={got.ship}")
    return out


def test_f_review_ships_only_when_every_check_holds():
    assert review_ship_failures() == []


# ---- E. budgets bind ------------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@dataclass
class _Call:
    cost_cad: float
    input_tokens: int
    output_tokens: int


class _G:
    def __init__(self, calls):
        self.calls = calls


def budget_failures() -> list[str]:
    out = []
    L = AC.Limits(ecr_cad=1.0, ecr_tokens=1000, wall_s=60, iterations=3, month_cad=5.0)
    clock = _Clock()
    cases = (
        ("ecr_cad", AC.Budget(L, 0.0, ecr_before_cad=0.95, clock=clock), 0.10, 10),
        ("ecr_tokens", AC.Budget(L, 0.0, ecr_before_tokens=995, clock=clock), 0.01, 10),
        ("month_cad", AC.Budget(L, 4.95, clock=clock), 0.10, 10),
        ("ecr_cad", AC.Budget(L, 0.0, clock=clock, gateways=[_G([_Call(0.95, 1, 1)])]), 0.1, 1),
    )
    for which, b, est, tok in cases:
        b.started = clock()
        try:
            b.check(est, tok)
            out.append(f"{which} did not bind")
        except AC.BudgetStop as exc:
            if exc.which != which:
                out.append(f"{which} bound as {exc.which}")
    b = AC.Budget(L, 0.0, clock=clock)
    b.started = clock()
    clock.t = 61.0
    try:
        b.check(0.0, 0)
        out.append("wall_time did not bind")
    except AC.BudgetStop as exc:
        if exc.which != "wall_time":
            out.append(f"wall bound as {exc.which}")
    clock.t = 0.0
    b = AC.Budget(L, 0.0, clock=clock)
    b.started = clock()
    try:
        b.check(0.5, 100)
    except AC.BudgetStop as exc:
        out.append(f"a call inside every budget was refused: {exc}")
    return out


def test_e_every_hard_budget_binds():
    assert budget_failures() == []


def limits_failures() -> list[str]:
    out = []
    raised = AC.limits({"BRAMBLELOOP_AUTOCODER_ECR_CAD": "500",
                        "BRAMBLELOOP_AUTOCODER_MONTHLY_CAD": "1000",
                        "BRAMBLELOOP_AUTOCODER_ITERATIONS": "999"})
    if raised.ecr_cad > AC.HARD.ecr_cad or raised.month_cad > AC.HARD.month_cad \
            or raised.iterations > AC.HARD.iterations:
        out.append(f"environment raised a limit: {raised}")
    lowered = AC.limits({"BRAMBLELOOP_AUTOCODER_ECR_CAD": "0.5",
                         "BRAMBLELOOP_AUTOCODER_MONTHLY_CAD": "7"})
    if lowered.ecr_cad != 0.5 or lowered.month_cad != 7.0:
        out.append(f"environment could not lower: {lowered}")
    nan = AC.limits({"BRAMBLELOOP_AUTOCODER_ECR_CAD": "nan",
                     "BRAMBLELOOP_AUTOCODER_MONTHLY_CAD": "-3"})
    if nan.ecr_cad != AC.HARD.ecr_cad or nan.month_cad != AC.HARD.month_cad:
        out.append(f"nan/negative changed a limit: {nan}")
    os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = "10"
    try:
        if AC.limits({}).month_cad != 10.0:
            out.append("the sub-ceiling exceeds the model ceiling in force")
    finally:
        os.environ.pop("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", None)
    if AC.HARD.month_cad > 100.0:
        out.append("the autocoder sub-ceiling is above the CA$100 model ceiling")
    return out


def test_e_environment_only_tightens_and_the_sub_ceiling_sits_inside_the_model_ceiling():
    assert limits_failures() == []


def test_e_a_run_over_its_request_budget_makes_no_model_call():
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    log: dict = {}
    runner, _ran = _runner()
    out = AC.run(db, host=LocalGitHost(repo), runner=runner,
                 env=_env(BRAMBLELOOP_AUTOCODER_ECR_CAD="0.0001"),
                 make_gateway=_gateways(db, _toy_steps(), _review(), log))
    assert out["status"] == AC.REFUSED and out["loop_stop"] == "budget:ecr_cad", out
    assert log[AC.STEP_TASK][0].calls == [] and _ledger(db) == (0, 0.0)
    assert _ref(repo, f"refs/heads/auto/ecr-{eid}") == ""


def test_e_the_monthly_sub_ceiling_parks_the_run_before_any_call():
    db = _db()
    _file_ecr(db)
    with db.session() as s:
        s.add(CostEntry(agent=AC.AGENT, amount_cad=AC.HARD.month_cad, kind=routing.COST_KIND,
                        purpose="autocoder.step@1"))
    called = []
    out = AC.run(db, host=LocalGitHost(_toy_repo()[0]), env=_env(),
                 make_gateway=lambda task: called.append(task))
    assert out["status"] == AC.PARKED and "sub-ceiling" in out["reason"], out
    assert called == []


# ---- H. kill switch and the token blocker --------------------------------------------------------

def test_h_off_by_default_and_unknown_with_a_named_blocker_without_the_token():
    assert AC.DEFAULT_ENABLED is False and AC.enabled({}) is False
    db = _db()
    eid = _file_ecr(db)
    off = AC.run(db, env={})
    assert off["status"] == AC.OFF and AC.ENABLED_VAR in off["reason"]
    out = AC.run(db, env=_env(), make_gateway=lambda task: (_ for _ in ()).throw(
        AssertionError("no model call without the token")))
    assert out["status"] == AC.UNKNOWN and out["work_done"] == 0, out
    assert any("BRAMBLELOOP_GITHUB_TOKEN" in b for b in out["blockers"]), out
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == AC.ACTION)))
    assert rows and rows[-1].detail["outcome"] == AC.UNKNOWN
    row = next(r for r in ecr.listing(db) if r["id"] == eid)
    assert "autocoder" not in row["evidence"] and _ledger(db) == (0, 0.0)
    p = AC.panel(db, env=_env())
    assert p["status"] == "BLOCKED" and any("TOKEN" in b for b in p["blockers"])
    nobase = AC.run(db, env={"BRAMBLELOOP_AUTOCODER_ENABLED": "1",
                             "BRAMBLELOOP_GITHUB_TOKEN": "x"})
    assert nobase["status"] == AC.UNKNOWN and any("base" in b for b in nobase["blockers"])


def test_h_the_integration_base_defaults_to_the_production_sha():
    assert AC.base_ref({"RAILWAY_GIT_COMMIT_SHA": "a" * 40}) == "a" * 40
    assert AC.base_ref({"RAILWAY_GIT_COMMIT_SHA": "a" * 40,
                        "BRAMBLELOOP_AUTOCODER_BASE": "claude/w6-INTEG7"}) == "claude/w6-INTEG7"


# ---- I. picking, wiring, panel, readback --------------------------------------------------------

def test_i_pick_orders_by_priority_with_engine_demand_a_level_up():
    db = _db()
    plain_p2 = _file_ecr(db, priority="P2", module="m.plain", occurrences=3)
    engine_p2 = _file_ecr(db, priority="P2", module="m.engine", title="x",
                          evidence={"engine_demand": True, "examples": ["need engine"]})
    order = [r["id"] for r in AC.ranked(db)]
    assert order == [engine_p2, plain_p2], order
    p0 = _file_ecr(db, priority="P0", module="m.urgent")
    assert AC.pick(db)["id"] == p0
    ecr.note_autocoder(db, p0, status=AC.REFUSED, at=NOW.isoformat(), attempts=1)
    assert AC.pick(db)["id"] == engine_p2
    old = (NOW - AC.REFUSE_COOLDOWN - timedelta(hours=1)).isoformat()
    ecr.note_autocoder(db, p0, at=old)
    assert AC.pick(db)["id"] == p0
    ecr.note_autocoder(db, p0, attempts=AC.MAX_ATTEMPTS)
    assert AC.pick(db)["id"] == engine_p2


def test_i_the_job_is_registered_scheduled_and_classified():
    assert handlers.get(AC.JOB_TYPE) is not None
    assert ("autocoder", AC.AGENT, AC.JOB_TYPE, 6 * 60 * 60) in CADENCES
    agent = next(a for a in DEFAULT_AGENTS if a["name"] == AC.AGENT)
    assert agent["allowed_job_types"] == [AC.JOB_TYPE]
    assert classes.JOB_CLASS[AC.JOB_TYPE] == classes.ActionClass.BUILD
    assert AC.JOB_TYPE in classes.BUILD_PLANE_JOB_TYPES
    assert classes.plane_violations(DEFAULT_AGENTS) == []
    assert routing.TASKS[AC.STEP_TASK].stronger_fallback is False
    assert routing.route(AC.STEP_TASK)[1].model != routing.route(AC.REVIEW_TASK)[1].model


def test_i_the_handler_runs_through_the_worker_context_and_reports_off():
    db = _db()

    class Ctx:
        def __init__(self):
            self.db, self.registry, self.audits = db, Registry(db), []
            self.job = type("J", (), {"id": None})()

        def audit(self, action, detail=None):
            self.audits.append((action, detail))
    ctx = Ctx()
    out = handlers.get(AC.JOB_TYPE)(ctx)
    assert out["status"] == AC.OFF and ctx.audits[0][0] == "improve.code.run"


def test_i_the_readback_section_is_counts_and_booleans():
    db = _db()
    _file_ecr(db)
    rb = AC.readback(db)
    assert rb["readable"] is True and rb["counts"]["open"] == 1
    assert rb["enabled"] is False and rb["status"] == "OFF"
    from brambleloop.ops import production_evidence as PE

    sec = PE.SECTIONS["autocoder"](db, now=NOW)
    assert sec["readable"] is True and "month_spend_cad" not in sec
    sys.path.insert(0, str(ROOT.parent / "ops"))
    import readback as RB  # noqa: E402

    assert RB._judge_section("autocoder", sec, None)[0] == RB.WARN
    assert RB._judge_section("autocoder", None, None)[0] == RB.UNKNOWN
    assert RB._judge_section("autocoder", {**sec, "enabled": True, "blocked": False,
                                           "status": "OK"}, None)[0] == RB.PASS


# ---- J. mutations of every rail are killed -------------------------------------------------------

MUTANTS = (
    ("refspec allowlist accepts anything", S, "assert_ref_allowed", lambda ref: ref,
     refspec_failures),
    ("denylist emptied", S, "PROTECTED_PATHS", (), path_failures),
    ("weakening detector returns nothing", S, "test_weakening", lambda *a, **k: [],
     weakening_failures),
    ("secret scanner returns nothing", S, "secret_findings", lambda *a, **k: [],
     rail_failures),
    ("spend scanner returns nothing", S, "spend_path_findings", lambda *a, **k: [],
     rail_failures),
    ("budget check is a no-op", AC.Budget, "check", lambda self, e, t: None, budget_failures),
    ("review checks ignored", AC, "REVIEW_CHECKS", (), review_ship_failures),
    ("limits no longer clamp", AC, "limits", lambda env=None: AC.Limits(ecr_cad=500.0,
                                                                           month_cad=1000.0),
     limits_failures),
)


def test_j_each_rail_mutation_is_killed():
    survived = []
    for label, owner, attr, mutant, check in MUTANTS:
        original = getattr(owner, attr)
        setattr(owner, attr, mutant)
        try:
            if not check():
                survived.append(label)
        except Exception:  # noqa: BLE001 - a mutant that crashes its check is killed
            pass
        finally:
            setattr(owner, attr, original)
    assert survived == [], f"mutants survived: {survived}"
    # And with every rail restored, every check is clean again.
    assert refspec_failures() == path_failures() == weakening_failures() == []
    assert rail_failures() == budget_failures() == limits_failures() == []


def test_j_the_submit_ship_gate_mutation_is_killed():
    original = AC.submit

    def mutant(host, *, ecr_id, base_sha, changes, review_, message):
        ref = S.branch_for(ecr_id)
        sha = host.push(ref, base_sha, {p: n for p, (_o, n) in changes.items()}, message)
        return {"branch": ref[len("refs/heads/"):], "sha": sha}
    AC.submit = mutant
    try:
        assert review_gate_failures() != []
    finally:
        AC.submit = original
    assert review_gate_failures() == []


if __name__ == "__main__":
    if shutil.which("git") is None:
        print("FAIL git binary required")
        sys.exit(1)
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e)[:300])
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
