"""ENG-AUTOCODER: the deterministic rails every autocoder diff passes before anything is pushed.

The autocoder (`improve.autocoder`) lets a model edit this repository. Nothing here asks a
model anything: each rail is plain code, and a diff that any rail refuses is never pushed,
whatever the reviewer model says. "Deterministic validation wins even if every LLM disagrees."

The rails:

* **Refspec allowlist** (`assert_ref_allowed`). The job may push exactly one kind of ref:
  `refs/heads/auto/<name>`. The production branch, `main`, release branches, tags and any
  other ref are refused here and again inside each git host, so a bug in the job cannot reach
  them. Promotion is the certify-and-promote pipeline's, never this job's.
* **Path allowlist + denylist** (`path_refusal`). Edits are allowed only under
  `brambleloop/src/brambleloop/` and `brambleloop/tests/`, and never to the deploy guard, the
  boot guard, release records, spend ceilings and the paid-call path, child-safety and other
  gates, auth/security, authority and approvals code, the agent registry, the worker's
  lease/effect machinery, or the autocoder itself and its tests.
* **Test weakening** (`test_weakening`). A test file is never deleted; a test function is
  never removed; no test function loses assertions; no skip, xfail or `vacuity-ok` pragma is
  added; no constant-true assertion is added; no test gains an early `return`.
* **Secrets** (`secret_findings`). Added lines are scanned for provider keys, tokens and
  private keys.
* **Spend, network and execution paths** (`spend_path_findings`). An added line that opens a
  model call, a network request or a subprocess in source code is refused: a new way to spend
  or to reach the outside is a human-reviewed change, not an autonomous one.
* **Size** (`MAX_FILES`, `MAX_CHANGED_LINES`): small diffs only.

`check_changeset` runs all of them and returns the refusals (empty = the rails pass).
"""
from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field

# ---- refspec allowlist ---------------------------------------------------------------------

ALLOWED_REF_PREFIX = "refs/heads/auto/"
_REF_TAIL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}(/[A-Za-z0-9][A-Za-z0-9._-]{0,80}){0,2}$")


class RefRefused(PermissionError):
    """A push to a ref outside `refs/heads/auto/*`."""


def assert_ref_allowed(ref: str) -> str:
    """Return the ref if it is an `auto/*` branch; raise `RefRefused` otherwise.

    Accepts `auto/x` (shorthand) or `refs/heads/auto/x`. Refuses everything else, including
    `+` (force) refspecs, `src:dst` pairs, `..`, `@{`, trailing `.lock`, and empty tails."""
    if not isinstance(ref, str) or not ref:
        raise RefRefused("empty ref")
    if any(c in ref for c in (":", "+", "~", "^", "?", "*", "[", "\\", " ", "@{")) \
            or ".." in ref or ref.endswith((".lock", "/", ".")):
        raise RefRefused(f"ref {ref!r} is not a plain branch name")
    full = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
    if not full.startswith(ALLOWED_REF_PREFIX):
        raise RefRefused(f"ref {ref!r} is outside the autocoder allowlist ({ALLOWED_REF_PREFIX}*)"
                         f"; promotion belongs to the certify-and-promote pipeline")
    tail = full[len(ALLOWED_REF_PREFIX):]
    if not _REF_TAIL.match(tail):
        raise RefRefused(f"ref {ref!r} has an invalid auto/ branch name")
    return full


def branch_for(ecr_id: int) -> str:
    return assert_ref_allowed(f"auto/ecr-{int(ecr_id)}")


# ---- paths ---------------------------------------------------------------------------------

SRC = "brambleloop/src/brambleloop/"
TESTS = "brambleloop/tests/"
ALLOWED_ROOTS = (SRC, TESTS)
ALLOWED_SUFFIXES = (".py", ".json", ".md", ".txt")

# Never edited by the autocoder. Prefixes end in "/"; anything else is an exact file.
PROTECTED_PATHS: tuple[str, ...] = (
    # deploy guard, boot guard, release records, the release pipeline
    "ops/", ".github/", "brambleloop/release/", "brambleloop/spec/", "brambleloop/scripts/",
    "brambleloop/Dockerfile", "brambleloop/railway.json", "brambleloop/run_tests.sh",
    SRC + "ops/release_record.py", SRC + "ops/assurance.py",
    SRC + "app/main.py", SRC + "app/worker_entry.py", SRC + "app/scheduler_entry.py",
    SRC + "app/hq_worker.py", SRC + "app/runner.py",
    # spend ceilings, reservations and every paid provider path
    SRC + "gateway/", SRC + "finance/",
    SRC + "agents/registry.py", SRC + "core/phase.py", SRC + "core/db.py",
    SRC + "core/models.py", SRC + "core/resilience.py",
    # child safety and every other gate
    SRC + "gates/", SRC + "improve/invariants.py", SRC + "improve/tuning.py",
    # auth, security, secrets
    SRC + "app/security.py", SRC + "app/command_center/auth.py",
    SRC + "ops/log_secret_guard.py", SRC + "ops/secret_leak.py",
    SRC + "ops/credential_register.py", SRC + "laura/private/",
    # authority and approvals
    SRC + "authority/", SRC + "app/command_center/approvals.py",
    SRC + "app/activation_authority_api.py", SRC + "app/publication_authority_api.py",
    SRC + "app/storefront_authority_api.py", SRC + "ops/activation_authority.py",
    SRC + "ops/publication_authority.py", SRC + "ops/storefront_authority.py",
    SRC + "ops/standing_", SRC + "ops/owner_queue_guard.py", SRC + "ops/owner_execution.py",
    # the worker's lease, phase and external-effect machinery
    SRC + "runtime/worker.py", SRC + "queue/",
    # the autocoder itself, and the tests that pin the rails
    SRC + "improve/autocoder",
    TESTS + "test_eng_autocoder.py", TESTS + "test_vacuity.py",
    TESTS + "test_w4_resume_runner.py", TESTS + "_tmp.py", TESTS + "_minipytest.py",
    TESTS + "_spend_reach.py", TESTS + "test_deploy_guard.py",
    TESTS + "test_cert_spend_hosts.py", TESTS + "__init__.py",
)


def normalize(path: str) -> str:
    p = str(path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def path_refusal(path: str) -> str:
    """Why `path` may not be edited, or '' when it may."""
    p = normalize(path)
    if not p or p.startswith("/") or ".." in p.split("/") or "\x00" in p:
        return f"{path!r}: not a plain repository-relative path"
    if any(part.startswith(".") and part not in (".",) for part in p.split("/")):
        return f"{p}: hidden paths are not editable"
    for prot in PROTECTED_PATHS:
        # A prefix entry ends in "/" (a directory) or "_" (a family of files); the
        # autocoder's own modules are a prefix too. Anything else is one exact file.
        prefix = prot.endswith(("/", "_")) or prot == SRC + "improve/autocoder"
        if (p.startswith(prot) if prefix else p == prot):
            return f"{p}: protected path ({prot}) -- the autocoder never edits it"
    if not p.startswith(ALLOWED_ROOTS):
        return f"{p}: outside the editable roots {ALLOWED_ROOTS}"
    if not p.endswith(ALLOWED_SUFFIXES):
        return f"{p}: only {ALLOWED_SUFFIXES} files are editable"
    if "__pycache__" in p:
        return f"{p}: build output"
    return ""


def is_test_file(path: str) -> bool:
    p = normalize(path)
    return p.startswith(TESTS) and p.endswith(".py")


# ---- test weakening --------------------------------------------------------------------------

_SKIP_RE = re.compile(
    r"pytest\.skip|pytest\.mark\.skip|pytest\.mark\.xfail|pytest\.xfail|unittest\.skip|"
    r"\bskipIf\b|\bskipUnless\b|@skip\b|SkipTest|\bxfail\b|#\s*vacuity-ok|#\s*pragma:\s*no\s*cover")


def _is_assert_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return name == "check" or name.startswith("assert") or name in ("fail", "raises")


def _truthy_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value)


def _vacuous(test: ast.AST) -> bool:
    """A constant-true assertion: `assert True`, `assert 1`, `assert x or True`, `assert x == x`."""
    if _truthy_const(test):
        return True
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) \
            and any(_truthy_const(v) for v in test.values):
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1 \
            and isinstance(test.ops[0], (ast.Eq, ast.Is, ast.GtE, ast.LtE)) \
            and ast.dump(test.left) == ast.dump(test.comparators[0]):
        return True
    return False


@dataclass
class TestShape:
    parsed: bool = True
    functions: dict[str, int] = field(default_factory=dict)   # name -> assertion count
    early_return: set[str] = field(default_factory=set)
    total_asserts: int = 0
    vacuous: int = 0
    skips: int = 0


def test_shape(source: str) -> TestShape:
    shape = TestShape(skips=len(_SKIP_RE.findall(source or "")))
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        shape.parsed = False
        return shape
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            shape.total_asserts += 1
            if _vacuous(node.test):
                shape.vacuous += 1
        elif _is_assert_call(node):
            shape.total_asserts += 1
            args = getattr(node, "args", [])
            if args and _truthy_const(args[0]) and getattr(node.func, "attr", "") in (
                    "assertTrue", "check"):
                shape.vacuous += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            n = sum(1 for sub in ast.walk(node)
                    if isinstance(sub, ast.Assert) or _is_assert_call(sub))
            shape.functions[node.name] = n
            body = [b for b in node.body if not (isinstance(b, ast.Expr)
                                                 and isinstance(b.value, ast.Constant))]
            if body and isinstance(body[0], (ast.Return, ast.Pass)):
                shape.early_return.add(node.name)
    return shape


def test_weakening(path: str, old: str | None, new: str | None) -> list[str]:
    """Refusals for one test file's change (empty = not weakened)."""
    p = normalize(path)
    if new is None:
        return [f"{p}: deleting a test file is refused"]
    after = test_shape(new)
    if not after.parsed:
        return [f"{p}: does not parse after the change"]
    before = test_shape(old or "")
    out: list[str] = []
    for name, n in before.functions.items():
        if name not in after.functions:
            out.append(f"{p}: test {name} removed")
        elif after.functions[name] < n:
            out.append(f"{p}: test {name} lost assertions ({n} -> {after.functions[name]})")
    if after.total_asserts < before.total_asserts:
        out.append(f"{p}: assertions removed ({before.total_asserts} -> "
                   f"{after.total_asserts})")
    if after.skips > before.skips:
        out.append(f"{p}: skip/xfail/vacuity-ok/no-cover marker added")
    if after.vacuous > before.vacuous:
        out.append(f"{p}: constant-true (vacuous) assertion added")
    new_early = after.early_return - before.early_return
    if new_early:
        out.append(f"{p}: early return added to {sorted(new_early)}")
    return out


# ---- secrets ---------------------------------------------------------------------------------

SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("railway_token", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
                                 r"(?=.*(?:token|secret|key|password))", re.I)),
    ("assigned_secret", re.compile(
        r"(?i)\b[\w-]*(?:api[_-]?key|secret|token|password|passwd|bearer)[\w-]*\b\s*[:=]\s*"
        r"[\"'][A-Za-z0-9/+_.=-]{20,}[\"']")),
    ("bearer_header", re.compile(r"(?i)authorization[\"']?\s*[:=]\s*[\"'](?:bearer|token)\s+[A-Za-z0-9._-]{16,}")),
)


def added_lines(old: str | None, new: str | None) -> list[str]:
    a = (old or "").splitlines()
    b = (new or "").splitlines()
    return [ln[1:] for ln in difflib.unified_diff(a, b, lineterm="", n=0)
            if ln.startswith("+") and not ln.startswith("+++")]


def secret_findings(path: str, old: str | None, new: str | None) -> list[str]:
    out = []
    for ln in added_lines(old, new):
        for name, rx in SECRET_PATTERNS:
            if rx.search(ln):
                out.append(f"{normalize(path)}: possible secret ({name}) in an added line")
                break
    return out


# ---- spend / network / execution paths --------------------------------------------------------

SPEND_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("model_call", re.compile(r"\b(?:complete_json|complete_each|job_gateway|gateway_for|"
                              r"ModelGateway|AnthropicProvider|OpenAIProvider|for_task|"
                              r"provider_for|check_budget_cad|record_cost)\s*\(")),
    ("paid_call", re.compile(r"\bpaid_calls\.guarded|\bimages\.generate\b|laura_converse\.call")),
    ("network", re.compile(r"\burlopen\s*\(|\burllib\.request\b|\brequests\.(?:get|post|put|patch|"
                           r"delete|request|Session)\b|\bhttpx\.|\bhttp\.client\b|\bsocket\.|"
                           r"\baiohttp\b")),
    ("execution", re.compile(r"\bsubprocess\b|\bos\.system\s*\(|\bos\.popen\s*\(|\bos\.exec\w*\s*\(|"
                             r"\beval\s*\(|\bexec\s*\(|\b__import__\s*\(|\bctypes\b|\bpickle\.loads?\b")),
    ("environment", re.compile(r"\bos\.environ\s*\[[^\]]+\]\s*=|\bos\.environ\.(?:update|setdefault|pop)\s*\(|"
                               r"\bputenv\s*\(")),
    ("ceiling_literal", re.compile(r"(?i)\b\w*(?:ceiling|budget|cap)_?cad\w*\s*=\s*\d")),
)


# What test code may not do either: it runs inside the worker during the loop, before review.
# A test subprocess already gets a scrubbed environment (`autocoder._clean_env`), so a test that
# sets or reads `os.environ` sees nothing secret and is allowed; reading another process's
# environment or a secrets file is not. Source code is held to the stricter `env_read` rule:
# it will later run in the production worker, where the environment holds every credential.
EXECUTION_KINDS = ("network", "execution", "process_read")
SPEND_PATTERNS = SPEND_PATTERNS + (
    ("process_read", re.compile(r"/proc/|/run/secrets|\.netrc\b|\bgetpass\b|\.ssh/|"
                                r"\.git-credentials|\.docker/config")),
    ("env_read", re.compile(r"\bos\.environ\b|\bos\.getenv\s*\(")),
)


def test_execution_findings(path: str, old: str | None, new: str | None) -> list[str]:
    """For test files: no network, subprocess, environment write/read or /proc read added.

    Tests are exempt from the model-call rule (they drive stand-ins), but they execute in the
    worker during the loop, so what they may reach is narrower than what source may."""
    if not is_test_file(path):
        return []
    out = []
    for ln in added_lines(old, new):
        code = ln.split("#", 1)[0]
        for name, rx in SPEND_PATTERNS:
            if name in EXECUTION_KINDS and rx.search(code):
                out.append(f"{normalize(path)}: test adds a {name} path ({code.strip()[:80]!r})")
                break
    return out


def spend_path_findings(path: str, old: str | None, new: str | None) -> list[str]:
    if is_test_file(path):
        return []           # tests drive stand-ins; their spend never reaches a provider
    out = []
    for ln in added_lines(old, new):
        code = ln.split("#", 1)[0]
        for name, rx in SPEND_PATTERNS:
            if rx.search(code):
                out.append(f"{normalize(path)}: adds a {name} path ({code.strip()[:80]!r}); "
                           f"new spend, network or execution needs human review")
                break
    return out


# ---- the whole changeset ---------------------------------------------------------------------

MAX_FILES = 10
MAX_CHANGED_LINES = 600


def unified_diff(changes: dict[str, tuple[str | None, str | None]]) -> str:
    parts = []
    for path in sorted(changes):
        old, new = changes[path]
        parts.extend(difflib.unified_diff(
            (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
            fromfile=("/dev/null" if old is None else f"a/{path}"),
            tofile=("/dev/null" if new is None else f"b/{path}")))
    return "".join(p if p.endswith("\n") else p + "\n" for p in parts)


def changed_line_count(changes: dict[str, tuple[str | None, str | None]]) -> int:
    n = 0
    for old, new in changes.values():
        for ln in difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(),
                                       lineterm="", n=0):
            if ln[:1] in "+-" and not ln.startswith(("+++", "---")):
                n += 1
    return n


def check_changeset(changes: dict[str, tuple[str | None, str | None]]) -> list[str]:
    """Every rail over `{path: (old_text | None, new_text | None)}`. Empty list = pass."""
    refusals: list[str] = []
    real = {normalize(p): v for p, v in changes.items() if v[0] != v[1]}
    if not real:
        return ["empty diff: nothing to submit"]
    if len(real) > MAX_FILES:
        refusals.append(f"{len(real)} files changed; the limit is {MAX_FILES}")
    lines = changed_line_count(real)
    if lines > MAX_CHANGED_LINES:
        refusals.append(f"{lines} changed lines; the limit is {MAX_CHANGED_LINES}")
    for path, (old, new) in sorted(real.items()):
        why = path_refusal(path)
        if why:
            refusals.append(why)
            continue
        if new is None:
            refusals.append(f"{path}: deleting files is refused")
            continue
        if path.endswith(".py"):
            try:
                ast.parse(new)
            except SyntaxError as exc:
                refusals.append(f"{path}: does not parse ({exc.msg} line {exc.lineno})")
        if is_test_file(path):
            refusals.extend(test_weakening(path, old, new))
        else:
            # Skip markers and pragmas in source are as much a weakening as in tests.
            if len(_SKIP_RE.findall(new)) > len(_SKIP_RE.findall(old or "")):
                refusals.append(f"{path}: skip/xfail/vacuity-ok/no-cover marker added")
        refusals.extend(secret_findings(path, old, new))
        refusals.extend(spend_path_findings(path, old, new))
        refusals.extend(test_execution_findings(path, old, new))
    return refusals
