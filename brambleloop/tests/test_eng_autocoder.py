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
D. secrets and spend/network/execution paths are refused; and (B19 A1) the production job
   NEVER executes model-written code: no test op, no suite run, no subprocess or import from
   the modified tree -- tests run in the autocoder-ci workflow, whose result is read back;
E. budget ceilings bind: per request CA$ and tokens, wall time, the monthly sub-ceiling, and
   environment can only tighten; a run over budget makes no model call;
F. the reviewer must SHIP before any push (and SHIP binds to the exact diff);
G. end to end with the stub model on a toy ECR in a temp repository: an auto/ecr-<id> branch
   on top of the base, the request `code_submitted` with the SHA and the suites trailer, spend
   in the ledger; only a green CI status from github-actions[bot] makes it `code_certified`;
   the refusals (weakened test, review BLOCK, red CI) certify nothing;
H. kill switch OFF by default; enabled without the token -> UNKNOWN with a named blocker;
I. picking: priority, engine demand, cooldowns; the Mission Control panel and readback;
J. mutations of each rail are killed by the checks above;
K. (B19) the CI sandbox workflow: push to auto/** only, contents: read, no secrets, no
   credential on disk, status posted by a job that runs no repository code.

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
        if m == "GET" and "/statuses" in path:
            return resp(getattr(self, "statuses", []))
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
    "../etc/passwd", "/etc/passwd", SRC + ".env", SRC + "x.so", "brambleloop/README.md",
    # B19 A2: child safety, auth/session/OAuth, spend ceilings and authority outside the
    # packages listed before, plus shared test helpers by prefix
    SRC + "intel/childrens.py", SRC + "creative/children.py", SRC + "publish/pdf.py",
    SRC + "core/opsauth.py", SRC + "core/readbackauth.py", SRC + "core/oauth_store.py",
    SRC + "integrations/etsy_oauth.py", SRC + "integrations/etsy_authorise.py",
    SRC + "visual/spend_plan.py", SRC + "visual/product_authority.py",
    SRC + "app/command_center/private_context.py", SRC + "app/command_center/api.py",
    SRC + "ops/release_record.py", T + "_helpers.py", T + "_spend_reach.py",
    T + "test_autopromote.py", SRC + "app/session_totp.py", SRC + "new/kill_switch.py",
    SRC + "ops/deploy_guard.py", SRC + "app/boot_guard.py", SRC + "publish/release_gates.py")
EDITABLE_SAMPLES = (SRC + "improve/ecr.py", SRC + "cir/compiler_extra.py",
                    T + "test_toy.py", T + "test_new_thing.py", SRC + "creative/notes.md")


def path_failures() -> list[str]:
    out = [f"{p} was editable" for p in PROTECTED_SAMPLES if not S.path_refusal(p)]
    out += [f"{p} refused: {S.path_refusal(p)}" for p in EDITABLE_SAMPLES if S.path_refusal(p)]
    return out


def test_b_protected_paths_are_refused_and_ordinary_ones_are_not():
    assert path_failures() == []


SENSITIVE_RX = r"child|minor|auth|oauth|secret|spend|ceiling|budget|authority|guard|gate"


def sensitive_name_failures() -> list[str]:
    """B19 A2: every module in the real tree whose name says child, auth, secret, spend,
    ceiling, budget, authority, guard or gate is refused -- including ones added later."""
    import re

    rx = re.compile(SENSITIVE_RX, re.I)
    out = []
    for f in sorted((ROOT / "src/brambleloop").rglob("*.py")):
        rel = "brambleloop/" + str(f.relative_to(ROOT)).replace(os.sep, "/")
        if rx.search(rel[len("brambleloop/"):]) and not S.path_refusal(rel):
            out.append(f"{rel} is editable")
    for f in sorted((ROOT / "tests").glob("_*.py")):
        rel = "brambleloop/tests/" + f.name
        if not S.path_refusal(rel):
            out.append(f"{rel} is editable")
    return out


def test_b_every_sensitive_module_in_the_tree_is_protected_by_name_or_list():
    assert sensitive_name_failures() == [], sensitive_name_failures()[:20]
    # ...and the editable surface is not empty: ordinary product code stays editable.
    assert S.path_refusal(SRC + "improve/ecr.py") == ""
    assert S.path_refusal(SRC + "cir/compiler.py") == ""


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
    # B19 A4: a guarded early return, a rewritten (same-count) assertion, and a same-named
    # method in a second class all count.
    ("guarded early return", BASE_TEST.replace("def test_two():\n",
                                               "def test_two():\n    if True:\n        return\n")),
    ("assertion rewritten", BASE_TEST.replace("assert f(2) == 3", "assert f(2) is not None")),
)
CLASS_BASE = ("class A:\n    def test_x(self):\n        assert f(1) == 2\n\n\n"
              "class B:\n    def test_x(self):\n        assert g(1) == 2\n")
CLASS_WEAKENED = CLASS_BASE.replace("        assert g(1) == 2\n", "        g(1)\n")
STRENGTHENED = BASE_TEST + "\n\ndef test_three():\n    assert f(3) == 4\n"


def weakening_failures() -> list[str]:
    out = []
    for label, new in WEAKENED:
        if not S.test_weakening(T + "test_x.py", BASE_TEST, new):
            out.append(f"weakening not detected: {label}")
    if S.test_weakening(T + "test_x.py", BASE_TEST, STRENGTHENED):
        out.append("a strengthened test was refused")
    if not S.test_weakening(T + "test_x.py", CLASS_BASE, CLASS_WEAKENED):
        out.append("weakening not detected: B.test_x lost its assertion behind A.test_x")
    if S.test_weakening(T + "test_x.py", BASE_TEST,
                        BASE_TEST.replace("    assert f(2) == 3\n",
                                          "    assert f(2) == 3\n    assert f(4) == 5\n")):
        out.append("adding an assertion was refused")
    return out


SOURCE_WEAKENED = (
    ("raise deleted", "def f(x):\n    if x < 0:\n        raise ValueError(x)\n    return x\n",
     "def f(x):\n    return x\n"),
    ("refusal branch deleted", "def ok(r):\n    if r.bad:\n        return refuse(r)\n"
                               "    return True\n", "def ok(r):\n    return True\n"),
    ("threshold retuned", "MAX_ITEMS = 5\n", "MAX_ITEMS = 50\n"),
    ("assert deleted", "def g(x):\n    assert x\n    return x\n", "def g(x):\n    return x\n"),
)


def source_weakening_failures() -> list[str]:
    """B19 A3: a source change that deletes a check or retunes a constant is refused."""
    out = []
    for label, old, new in SOURCE_WEAKENED:
        if not S.check_changeset({SRC + "m.py": (old, new)}):
            out.append(f"source weakening not detected: {label}")
    fix = S.check_changeset({SRC + "toy.py": ("def add(a, b):\n    return a - b\n",
                                              "def add(a, b):\n    return a + b\n")})
    if fix:
        out.append(f"an ordinary fix was refused: {fix}")
    return out


def test_c_source_deletions_of_checks_are_refused():
    assert source_weakening_failures() == []


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
    # A test may steer its own (already scrubbed) environment; it may not read another
    # process's environment or a secrets file.
    assert S.test_execution_findings(T + "test_x.py", "", "os.environ.pop('X', None)\n") == []
    proc = S.test_execution_findings(T + "test_x.py", "",
                                     "open(f'/proc/{os.getppid()}/environ').read()\n")
    assert proc and "process_read" in proc[0], proc


def test_d_the_workspace_test_op_runs_nothing():
    """B19 A1: the `test` action is answered, never executed."""
    root = Path(tempfile.mkdtemp())
    (root / "brambleloop/tests").mkdir(parents=True)
    marker = root / "RAN"
    (root / "brambleloop/tests/test_x.py").write_text(
        f"open({str(marker)!r}, 'w').write('ran')\n")
    ws = AC.Workspace(root)
    obs = ws.apply({"op": "test", "suite": "tests/test_x.py"})
    assert obs.startswith("test not run") and "CI" in obs, obs
    assert not marker.exists()
    assert not hasattr(AC, "run_suite") and not hasattr(AC, "_clean_env")
    assert "runner" not in AC.Workspace.__init__.__code__.co_varnames
    assert "runner" not in AC.run.__code__.co_varnames


SPAWN_TOKENS = ("subprocess", "os.system", "os.popen", "os.exec", "os.spawn", "os.fork",
                "sys.executable", "runpy", "importlib", "__import__", "exec(", "eval(",
                "compile(", "multiprocessing", "pty.")


def spawn_failures() -> list[str]:
    """B19 A1, static half: the job's module has no way to start or import code at all."""
    src = (ROOT / "src/brambleloop/improve/autocoder.py").read_text()
    code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    import re

    return [f"autocoder.py mentions {t!r}" for t in SPAWN_TOKENS
            if re.search(r"(?<![\w.])" + re.escape(t), code)]


def test_d_the_job_never_spawns_or_imports_the_modified_code():
    """B19 A1: fails if the production job ever executes the tree it modified.

    Static: autocoder.py names no process, exec or import machinery. Dynamic: a full run on a
    toy ECR (rails -> SHIP -> push) with every process-spawning call trapped, a model that
    asks to run tests, and a modified test and source file that would leave a marker if
    executed or imported. Only the host's own git plumbing (LocalGitHost) may run, and never
    with the workspace as its cwd or an interpreter as argv[0]."""
    import builtins
    import importlib

    assert spawn_failures() == [], spawn_failures()
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    marker = Path(tempfile.mkdtemp()) / "EXECUTED"
    wd = str(Path(tempfile.mkdtemp(prefix="ws-")).resolve())    # the job's workspaces live here
    toy, test = SRC + "toy.py", T + "test_toy.py"
    boom = f"open({str(marker)!r}, 'w').write('x')\n"
    steps = [
        {"plan": "fix", "done": False, "actions": [
            {"op": "edit", "path": toy, "old": "return a - b", "new": "return a + b"},
            {"op": "edit", "path": test, "old": "from brambleloop import toy\n",
             "new": "from brambleloop import toy\n" + boom},
            {"op": "test", "suite": "tests/test_toy.py"}]},
        {"plan": "done", "actions": [{"op": "test", "suite": "tests/test_toy.py"}],
         "targets": ["tests/test_toy.py"], "done": True, "summary": "add() adds"}]

    def script(system, user, n):
        return steps[min(n, len(steps)) - 1]
    spawned, imported = [], []
    real_popen, real_import = subprocess.Popen, builtins.__import__
    real_system, real_execv = os.system, os.execv

    class TrapPopen(real_popen):
        def __init__(self, args, *a, **k):
            argv = list(args) if isinstance(args, (list, tuple)) else [str(args)]
            cwd = str(k.get("cwd") or "")
            spawned.append((argv[:3], cwd))
            if (argv and ("python" in Path(str(argv[0])).name or str(argv[0]) == sys.executable)) \
                    or str(Path(cwd or ".").resolve()).startswith(wd):
                raise AssertionError(f"the job spawned modified code: {argv[:3]} in {cwd}")
            super().__init__(args, *a, **k)

    def trap_import(name, globals=None, locals=None, fromlist=(), level=0):
        f = (globals or {}).get("__file__") or ""
        if str(f).startswith(wd) or name.endswith("test_toy"):
            imported.append(name)
            raise AssertionError(f"the job imported modified code: {name}")
        return real_import(name, globals, locals, fromlist, level)

    def refuse(*a, **k):
        raise AssertionError(f"the job spawned a process: {a[:2]}")
    subprocess.Popen, builtins.__import__ = TrapPopen, trap_import
    os.system, os.execv = refuse, refuse
    real_import_module = importlib.import_module
    importlib.import_module = lambda name, *a, **k: (
        imported.append(name), real_import_module(name, *a, **k))[1]
    try:
        out = AC.run(db, host=LocalGitHost(repo), env=_env(), workdir=Path(wd),
                     make_gateway=_gateways(db, script, _review(), {}))
    finally:
        subprocess.Popen, builtins.__import__ = real_popen, real_import
        os.system, os.execv = real_system, real_execv
        importlib.import_module = real_import_module
    assert out["status"] == AC.SUBMITTED, out
    assert not marker.exists(), "model-written code ran in the production job"
    assert imported == [] or all("test_toy" not in m and "toy" != m.split(".")[-1]
                                 for m in imported), imported
    assert all(a and a[0] == "git" for a, _cwd in spawned), spawned
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    assert row["evidence"]["autocoder"]["status"] == AC.SUBMITTED


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


def _ci(host, sha, state="success", creator=AC.CI_CREATOR):
    """What the autocoder-ci workflow's report job posts (the CI sandbox's verdict)."""
    host.statuses[sha] = {"state": state, "creator": creator, "context": AC.CI_CONTEXT,
                          "target_url": "https://github.com/x/actions/runs/1"}


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
    host = LocalGitHost(repo)
    out = AC.run(db, host=host, env=_env(),
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
    # The commit names the targeted suite and both mandatory suites for the CI sandbox.
    msg = subprocess.run(["git", "log", "-1", "--format=%B", sha], cwd=repo,
                         capture_output=True, text=True).stdout
    trailer = [ln for ln in msg.splitlines() if ln.startswith(AC.CI_TRAILER)]
    assert trailer and trailer[0].split()[1:] == ["tests/test_toy.py", *AC.MANDATORY_SUITES]
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    ac = row["evidence"]["autocoder"]
    # Pushed, not certified: the lifecycle waits for CI.
    assert row["state"] == ecr.FILED and ac["status"] == AC.SUBMITTED and ac["sha"] == sha
    assert ac["ci"]["state"] == "pending" and AC.classify(row, NOW) == "submitted"
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
    # No verdict yet: still waiting. A status from anyone but github-actions[bot] is ignored.
    assert AC.ci_readback(db, host)["waiting"] == [eid]
    _ci(host, sha, creator="brambleloop-autocoder")
    assert AC.ci_readback(db, host)["waiting"] == [eid]
    # Green CI from the sandbox: code_certified, and the ECR moves to REVIEWED.
    _ci(host, sha)
    got = AC.ci_readback(db, host)
    assert got["certified"] == [eid], got
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    ac = row["evidence"]["autocoder"]
    assert ac["status"] == AC.CERTIFIED == "code_certified" and ac["certified_sha"] == sha
    assert row["state"] == ecr.REVIEWED and AC.classify(row, NOW) == "certified"


def test_g_a_weakened_test_is_refused_and_nothing_is_pushed():
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    out = AC.run(db, host=LocalGitHost(repo), env=_env(),
                 make_gateway=_gateways(db, _toy_steps(weaken=True), _review(), {}))
    assert out["status"] == AC.REFUSED and out["reason"] == "gate_rails", out
    assert any("assertion" in d or "lost" in d for d in out["detail"]), out["detail"]
    assert _ref(repo, f"refs/heads/auto/ecr-{eid}") == ""
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    assert row["evidence"]["autocoder"]["status"] == AC.REFUSED
    assert row["state"] == ecr.FILED


def test_g_red_ci_refuses_the_request_and_nothing_is_certified():
    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()
    host = LocalGitHost(repo)
    out = AC.run(db, host=host, env=_env(),
                 make_gateway=_gateways(db, _toy_steps(), _review(), {}))
    assert out["status"] == AC.SUBMITTED, out
    _ci(host, out["sha"], state="failure")
    got = AC.ci_readback(db, host)
    assert got["failed"] == [eid] and got["certified"] == [], got
    row = next(r for r in ecr.listing(db, open_only=False) if r["id"] == eid)
    ac = row["evidence"]["autocoder"]
    assert ac["status"] == AC.REFUSED and ac["reason"] == "ci_failed"
    assert row["state"] == ecr.FILED
    # Certification without a green result for exactly this SHA is refused.
    for ci in ({"state": "failure", "creator": AC.CI_CREATOR},
               {"state": "success", "creator": "someone"},
               {"state": "success", "creator": AC.CI_CREATOR, "sha": "f" * 40}, None):
        try:
            AC.mark_certified(db, eid, sha=out["sha"], ci=ci, by="x")
            raise AssertionError(f"certified with {ci}")
        except AC.NotCertified:
            pass
    # A request with no CI result within the timeout is refused, not left forever.
    db2 = _db()
    e2 = _file_ecr(db2)
    host2 = LocalGitHost(_toy_repo()[0])
    out2 = AC.run(db2, host=host2, env=_env(),
                  make_gateway=_gateways(db2, _toy_steps(), _review(), {}))
    assert out2["status"] == AC.SUBMITTED
    late = datetime.now(timezone.utc) + AC.CI_TIMEOUT + timedelta(hours=1)
    assert AC.ci_readback(db2, host2, now=late)["failed"] == [e2]


def test_g_the_github_host_reads_the_ci_status_with_its_creator():
    sha = "c" * 40
    fake = _FakeGitHub("a" * 40)
    fake.statuses = [{"context": "other", "state": "success", "creator": {"login": "x"}},
                     {"context": AC.CI_CONTEXT, "state": "failure",
                      "creator": {"login": AC.CI_CREATOR}, "target_url": "u"}]
    os.environ["BRAMBLELOOP_GITHUB_TOKEN"] = "test-not-a-token"
    try:
        got = GitHubHost("owner/repo", opener=fake).ci_status(sha, AC.CI_CONTEXT)
    finally:
        os.environ.pop("BRAMBLELOOP_GITHUB_TOKEN", None)
    assert got == {"state": "failure", "sha": sha, "creator": AC.CI_CREATOR,
                   "target_url": "u"}, got
    assert fake.requests[-1][:2] == ("GET", f"/commits/{sha}/statuses?per_page=100")


def test_e_per_request_spend_comes_from_the_ledger_and_survives_a_crash():
    """B19 A5: a run that crashed after spending (no note written) still counts."""
    from brambleloop.core.models import Job

    db = _db()
    eid = _file_ecr(db)
    with db.session() as s:
        job = Job(job_type=AC.JOB_TYPE, agent=AC.AGENT, inputs={})
        s.add(job)
        s.flush()
        jid = job.id
    ecr.note_autocoder(db, eid, status=AC.CODING, at=(NOW - timedelta(hours=3)).isoformat(),
                       attempts=1, job=jid, jobs=[jid])
    with db.session() as s:      # what the crashed run had been billed
        s.add(CostEntry(agent=AC.AGENT, job_id=jid, amount_cad=AC.HARD.ecr_cad - 0.0001,
                        kind=routing.COST_KIND, purpose="autocoder.step@2",
                        tokens_in=10, tokens_out=5))
    assert AC.ecr_ledger_spend(db, [jid]) == (round(AC.HARD.ecr_cad - 0.0001, 6), 15)
    log: dict = {}
    repo, _base = _toy_repo()
    out = AC.run(db, host=LocalGitHost(repo), env=_env(), job_id=None,
                 make_gateway=_gateways(db, _toy_steps(), _review(), log))
    assert out["status"] == AC.REFUSED and out["loop_stop"] == "budget:ecr_cad", out
    assert log[AC.STEP_TASK][0].calls == []


# ---- F. the reviewer must SHIP ------------------------------------------------------------------

def test_f_review_block_or_a_false_check_pushes_nothing():
    for script in (_review("BLOCK"), _review("SHIP", no_spend_paths=False),
                   _review("ship it", honest=True)):
        db = _db()
        eid = _file_ecr(db)
        repo, _base = _toy_repo()
        out = AC.run(db, host=LocalGitHost(repo), env=_env(),
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
    out = AC.run(db, host=LocalGitHost(repo),
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


def test_e_an_environment_fault_parks_the_request_instead_of_refusing_it():
    from brambleloop.gateway.model_gateway import NoProviderAvailable

    db = _db()
    eid = _file_ecr(db)
    repo, _base = _toy_repo()

    def no_provider(task):
        raise NoProviderAvailable("no model provider is configured")
    out = AC.run(db, host=LocalGitHost(repo), env=_env(), make_gateway=no_provider)
    assert out["status"] == AC.PARKED and "NoProviderAvailable" in out["reason"], out
    row = next(r for r in ecr.listing(db) if r["id"] == eid)
    ac = row["evidence"]["autocoder"]
    assert "status" not in ac and ac["attempts"] == 0, ac
    assert AC.pick(db)["id"] == eid           # picked again on the next run


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
    # B19
    ("name rule removed", S, "SENSITIVE_NAME", __import__("re").compile(r"(?!x)x"),
     sensitive_name_failures),
    ("source-weakening rail returns nothing", S, "source_weakening_findings",
     lambda *a, **k: [], source_weakening_failures),
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
    assert sensitive_name_failures() == source_weakening_failures() == spawn_failures() == []


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


# ---- K. the CI sandbox workflow (B19 A1) ---------------------------------------------------------

WORKFLOW = ROOT.parent / ".github/workflows/autocoder-ci.yml"


def workflow_failures(text: str | None = None) -> list[str]:
    import re

    import yaml

    text = WORKFLOW.read_text() if text is None else text
    wf = yaml.safe_load(text)
    on = wf.get(True, wf.get("on"))       # YAML 1.1 reads the key `on` as True
    out = []
    if set(on) != {"push"} or on["push"] != {"branches": ["auto/**"]}:
        out.append(f"triggers must be exactly push to auto/**: {on}")
    if wf.get("permissions") != {"contents": "read"}:
        out.append(f"workflow permissions must be contents: read: {wf.get('permissions')}")
    if (wf.get("defaults") or {}).get("run", {}).get("shell") != "bash":
        out.append("defaults.run.shell must be bash (pipefail)")
    if "secrets." in text:
        out.append("the workflow references a secret")
    jobs = wf.get("jobs") or {}
    test, report = jobs.get("test") or {}, jobs.get("report") or {}
    if test.get("permissions") != {"contents": "read"}:
        out.append(f"test job permissions: {test.get('permissions')}")
    for st in test.get("steps") or []:
        if "checkout" in str(st.get("uses") or ""):
            if (st.get("with") or {}).get("persist-credentials") is not False:
                out.append("test job checkout must set persist-credentials: false")
        if re.search(r"\$\{\{", str(st.get("run") or "")):
            out.append(f"an expression is interpolated into a run script: {st.get('name')}")
        if "github.token" in str(st):
            out.append("the test job sees the token")
    run = "\n".join(str(st.get("run") or "") for st in test.get("steps") or [])
    for suite in AC.MANDATORY_SUITES:
        if suite not in run:
            out.append(f"mandatory suite {suite} not run")
    if AC.CI_TRAILER not in run:
        out.append("the targeted suites are not read from the commit trailer")
    if report.get("needs") != "test" or report.get("if") != "always()":
        out.append("the report job must follow the test job always")
    if report.get("permissions") != {"statuses": "write"}:
        out.append(f"report job permissions: {report.get('permissions')}")
    if any("uses" in st for st in report.get("steps") or []):
        out.append("the report job must not check out or run repository code")
    rrun = "\n".join(str(st.get("run") or "") for st in report.get("steps") or [])
    if AC.CI_CONTEXT not in rrun or "statuses/" not in rrun:
        out.append("the report job does not post the commit status")
    return out


def test_k_the_ci_sandbox_workflow_holds_no_secret_and_reports_by_status():
    assert workflow_failures() == [], workflow_failures()
    base = WORKFLOW.read_text()
    mutants = {
        "pull_request_target added": base.replace(
            '  push:\n    branches: ["auto/**"]',
            '  push:\n    branches: ["auto/**"]\n  pull_request_target:'),
        "secret given to the test job": base.replace(
            "          PYTHONPATH: src:tests",
            "          PYTHONPATH: src:tests\n          K: ${{ secrets.RAILWAY_TOKEN }}"),
        "credential persisted": base.replace("persist-credentials: false",
                                             "persist-credentials: true"),
        "write permission": base.replace("permissions:\n  contents: read",
                                         "permissions:\n  contents: write", 1),
        "report job checks out": base.replace(
            "      - name: Post the result as the commit status",
            "      - uses: actions/checkout@v4\n      - name: Post the result as the commit status"),
        "mandatory suite dropped": base.replace(" tests/test_vacuity.py", ""),
    }
    survived = [k for k, v in mutants.items() if v == base or not workflow_failures(v)]
    assert survived == [], survived


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
