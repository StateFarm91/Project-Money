"""ENG-AUTOCODER: the in-production coding team (D-OWNER-AUTOCODER, 2026-11-20).

The self-improvement team files engineering change requests (`improve.ecr`) -- lessons only
code can act on. Until now a human-started builder session had to pick each one up. This
module is the `improve.code` worker job that does it on the company's own model budget:

1. **Pick** the highest-value open request (`pick`): FILED or REOPENED, priority first,
   engine-demand requests a level up, then occurrences. Requests already submitted, in
   flight, or recently refused are skipped.
2. **Workspace**: a depth-1 snapshot of the integration base (`BRAMBLELOOP_AUTOCODER_BASE`,
   default the production SHA Railway reports in `RAILWAY_GIT_COMMIT_SHA`) in a temp dir.
3. **Plan -> edit -> test loop** (`run_loop`) with Claude through the model gateway
   (`failover.job_gateway`, task `autocoder.step`): every call is reserved, ceiling-checked
   and billed to this job like every other model call. The model acts only through
   structured actions (list / read / grep / exact edit / create / run one test suite) that
   code applies; it never runs anything itself.
4. **Hard budgets** (`Limits`), checked before every call: per request CA$, tokens, wall time
   and iterations, and a monthly autocoder sub-ceiling inside the CA$100 model ceiling.
   Environment variables may only tighten them.
5. **Gate** (`gate`): the deterministic rails (`autocoder_safety.check_changeset`), then the
   targeted suites plus `test_vacuity` and `test_w4_resume_runner`, in the workspace. Any
   failure refuses the request with the reason; nothing is pushed.
6. **Independent review** (`review`): a second model call, different prompt and (by default)
   a different, stronger model, which must answer SHIP with every check true.
7. **Push** (`submit`) the branch `auto/ecr-<id>` -- and only an `auto/*` ref, enforced in
   `autocoder_safety.assert_ref_allowed` and again in each host -- and record the request as
   `code_submitted` with the commit SHA.

**Promotion is not this job's.** The certify-and-promote pipeline (GitHub Actions,
ENG-AUTOPROMOTE) takes a branch through the full suite, the release record and `deploy.sh`
with the guard. This job never pushes to the production branch or `main`.

**Off until switched on.** `BRAMBLELOOP_AUTOCODER_ENABLED` is the kill switch; unset means
OFF (see OWNER_ACTIONS_AUTOCODER.md for why). Enabled without `BRAMBLELOOP_GITHUB_TOKEN`, the
job reports UNKNOWN with that blocker named -- never a silent no-op, and never any spend.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import autocoder_safety as safety

JOB_TYPE = "improve.code"
AGENT = "autocoder"
ACTION = "improve.code"
STEP_TASK, REVIEW_TASK = "autocoder.step", "autocoder.review"
STEP_PROMPT, REVIEW_PROMPT = "autocoder.step@1", "autocoder.review@1"

ENABLED_VAR = "BRAMBLELOOP_AUTOCODER_ENABLED"
BASE_VAR = "BRAMBLELOOP_AUTOCODER_BASE"
PROD_SHA_VAR = "RAILWAY_GIT_COMMIT_SHA"
# The owner's choice, recorded in OWNER_ACTIONS_AUTOCODER.md: OFF until the owner sets "1".
DEFAULT_ENABLED = False

# Statuses this job writes into `evidence["autocoder"]["status"]` of a request.
CODING, SUBMITTED, CERTIFIED, REFUSED = "coding", "code_submitted", "certified", "refused"
# Run outcomes (the job's own result).
OFF, UNKNOWN, IDLE, PARKED = "OFF", "UNKNOWN", "IDLE", "PARKED"

MANDATORY_SUITES = ("tests/test_vacuity.py", "tests/test_w4_resume_runner.py")
REFUSE_COOLDOWN = timedelta(days=7)
MAX_ATTEMPTS = 3
IN_FLIGHT = timedelta(hours=2)


# ---- configuration and budgets -------------------------------------------------------------

def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def enabled(env=None) -> bool:
    env = os.environ if env is None else env
    raw = env.get(ENABLED_VAR)
    if raw is None or not str(raw).strip():
        return DEFAULT_ENABLED
    return _truthy(raw)


def base_ref(env=None) -> str:
    """The integration base the workspace branches from: config, else the production SHA."""
    env = os.environ if env is None else env
    return (env.get(BASE_VAR) or env.get(PROD_SHA_VAR) or "").strip()


@dataclass(frozen=True)
class Limits:
    ecr_cad: float = 3.50            # model spend per request, across all its attempts
    ecr_tokens: int = 400_000        # input + output tokens per request
    wall_s: int = 40 * 60            # one run, start to push (the lease renews to 60 min)
    iterations: int = 12             # plan/edit/test steps per run
    month_cad: float = 40.00         # autocoder sub-ceiling inside the CA$100 model ceiling
    test_timeout_s: int = 900        # per suite
    transcript_chars: int = 40_000   # what each step sees of the previous ones


HARD = Limits()
_ENV_LIMITS = {"ecr_cad": "BRAMBLELOOP_AUTOCODER_ECR_CAD",
               "ecr_tokens": "BRAMBLELOOP_AUTOCODER_ECR_TOKENS",
               "wall_s": "BRAMBLELOOP_AUTOCODER_WALL_S",
               "iterations": "BRAMBLELOOP_AUTOCODER_ITERATIONS",
               "month_cad": "BRAMBLELOOP_AUTOCODER_MONTHLY_CAD"}


def limits(env=None) -> Limits:
    """The limits in force. Environment may lower any of them; nothing may raise one. The
    monthly sub-ceiling is also never above the model ceiling in force."""
    env = os.environ if env is None else env
    vals = {}
    for name, var in _ENV_LIMITS.items():
        hard = getattr(HARD, name)
        raw = (env.get(var) or "").strip()
        try:
            v = float(raw) if raw else hard
        except ValueError:
            v = hard
        if not (v == v) or v < 0 or v in (float("inf"),):
            v = hard        # NaN, negative, infinite: not a lowering anyone meant
        vals[name] = type(hard)(min(v, hard))
    try:
        from ..gateway import anthropic as gw

        vals["month_cad"] = min(vals["month_cad"], float(gw.monthly_ceiling_cad()))
    except Exception:  # noqa: BLE001 - an unreadable ceiling binds at zero, never unbounded
        vals["month_cad"] = 0.0
    return Limits(**{**HARD.__dict__, **vals})


class BudgetStop(RuntimeError):
    """A hard budget would be exceeded by the next call. `which` names the budget."""

    def __init__(self, which: str, message: str):
        super().__init__(message)
        self.which = which


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_spent_cad(db, now: datetime | None = None) -> float:
    """What the autocoder agent has been billed this UTC month, from the ledger."""
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        v = s.scalar(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0)).where(
            CostEntry.agent == AGENT, CostEntry.at >= _month_start(now)))
    return round(float(v or 0.0), 6)


@dataclass
class Budget:
    limits: Limits
    month_before_cad: float           # billed to the agent this month before this run
    ecr_before_cad: float = 0.0       # spent on this request by earlier attempts
    ecr_before_tokens: int = 0
    started: float = field(default_factory=time.monotonic)
    clock: object = time.monotonic
    gateways: list = field(default_factory=list)

    def run_cad(self) -> float:
        return round(sum(c.cost_cad for g in self.gateways for c in g.calls), 6)

    def run_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for g in self.gateways for c in g.calls)

    def elapsed(self) -> float:
        return self.clock() - self.started

    def check(self, est_cad: float, est_tokens: int) -> None:
        L = self.limits
        if self.elapsed() >= L.wall_s:
            raise BudgetStop("wall_time", f"wall time {self.elapsed():.0f}s reached the "
                                          f"{L.wall_s}s limit")
        spent = self.ecr_before_cad + self.run_cad()
        if spent + est_cad > L.ecr_cad:
            raise BudgetStop("ecr_cad", f"request spend CA${spent:.4f} + next call "
                                        f"CA${est_cad:.4f} exceeds CA${L.ecr_cad:.2f}")
        tok = self.ecr_before_tokens + self.run_tokens()
        if tok + est_tokens > L.ecr_tokens:
            raise BudgetStop("ecr_tokens", f"request tokens {tok} + next {est_tokens} "
                                           f"exceed {L.ecr_tokens}")
        month = self.month_before_cad + self.run_cad()
        if month + est_cad > L.month_cad:
            raise BudgetStop("month_cad", f"autocoder month CA${month:.4f} + next call "
                                          f"CA${est_cad:.4f} exceeds the sub-ceiling "
                                          f"CA${L.month_cad:.2f}")


def _estimate(gateway, prompt_ref: str, values: dict) -> tuple[float, int]:
    """The padded estimate the gateway itself will reserve on (not restated here)."""
    from ..gateway import prompts

    prompt = prompts.get(prompt_ref)
    user = prompt.render(**values)
    provider = gateway.providers[0]
    tokens = (len(prompt.system) + len(user)) // 4 + int(prompt.max_output_tokens)
    return float(gateway._estimate_cad(prompt, provider, user)), tokens


def guarded_call(budget: Budget, gateway, prompt_ref: str, values: dict) -> dict:
    """One model call, refused before it is made if any hard budget would be exceeded."""
    if gateway not in budget.gateways:
        budget.gateways.append(gateway)
    est, tok = _estimate(gateway, prompt_ref, values)
    budget.check(est, tok)
    return gateway.complete_json(prompt_ref, agent=AGENT, values=values,
                                 max_attempts_per_provider=1)


# ---- picking a request -----------------------------------------------------------------------

_PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def is_engine_demand(r: dict) -> bool:
    ev = r.get("evidence") or {}
    if ev.get("engine_demand"):
        return True
    text = f"{r.get('module', '')} {r.get('title', '')}".lower()
    return r.get("defect_class") == "missing_capability" and "engine" in text


def _aware(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def eligible(r: dict, now: datetime) -> tuple[bool, str]:
    from . import ecr

    if r["state"] not in (ecr.FILED, ecr.REOPENED):
        return False, f"state {r['state']}"
    ac = (r.get("evidence") or {}).get("autocoder") or {}
    st = ac.get("status")
    if st in (SUBMITTED, CERTIFIED) and r["state"] != ecr.REOPENED:
        return False, st
    if st == CODING and (_aware(ac.get("at")) or now) > now - IN_FLIGHT:
        return False, "in flight"
    if int(ac.get("attempts") or 0) >= MAX_ATTEMPTS:
        return False, "attempts exhausted"
    if st == REFUSED and (_aware(ac.get("at")) or now) > now - REFUSE_COOLDOWN:
        return False, "refused recently"
    if float(ac.get("spent_cad") or 0.0) >= HARD.ecr_cad:
        return False, "request budget spent"
    return True, ""


def ranked(db, now: datetime | None = None) -> list[dict]:
    from . import ecr

    now = now or datetime.now(timezone.utc)
    rows = [r for r in ecr.listing(db, open_only=True) if eligible(r, now)[0]]

    def key(r):
        p = _PRIO.get(r["priority"], 3) - (1 if is_engine_demand(r) else 0)
        return (p, -int(r.get("occurrences") or 1), r["id"])
    return sorted(rows, key=key)


def pick(db, now: datetime | None = None) -> dict | None:
    rows = ranked(db, now)
    return rows[0] if rows else None


# ---- the workspace and its tools -------------------------------------------------------------

READ_LINES, READ_CHARS, OBS_CHARS = 400, 20_000, 6_000
GREP_HITS, GREP_FILES = 60, 4000
_TEXT = (".py", ".md", ".json", ".txt", ".sh", ".toml", ".cfg", ".yml", ".yaml")


def _clean_env(workspace: Path) -> dict:
    """The environment a test subprocess gets: nothing from the worker's own, so no
    credential, database URL or provider key is visible to code the model wrote."""
    home = workspace / ".autocoder_home"
    home.mkdir(exist_ok=True)
    tmp = workspace / ".autocoder_tmp"
    tmp.mkdir(exist_ok=True)
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(tmp),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "src:tests", "PYTHONHASHSEED": "0"}


def run_suite(workspace: Path, suite: str, timeout_s: int) -> dict:
    """Run one test file in the workspace (cwd brambleloop/), bounded by `timeout_s`."""
    started = time.monotonic()
    try:
        out = subprocess.run([sys.executable, suite], cwd=str(workspace / "brambleloop"),
                             env=_clean_env(workspace), capture_output=True, text=True,
                             timeout=timeout_s)
        rc, text = out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc = 124
        text = f"TIMEOUT after {timeout_s}s\n" + str(exc.stdout or "")[-2000:]
    return {"suite": suite, "rc": rc, "passed": rc == 0,
            "seconds": round(time.monotonic() - started, 1), "tail": text[-3000:]}


def _suite_ok(suite: str) -> bool:
    return bool(re.match(r"^tests/test_[A-Za-z0-9_]+\.py$", str(suite or "")))


class Workspace:
    """The model's only hands: structured actions applied by code, every write path-checked."""

    def __init__(self, root: Path, *, runner=run_suite, test_timeout_s: int = 900):
        self.root = Path(root)
        self.runner = runner
        self.test_timeout_s = test_timeout_s
        self.changes: dict[str, tuple[str | None, str]] = {}
        self.test_runs: list[dict] = []

    def _path(self, rel: str) -> Path:
        rel = safety.normalize(rel)
        if not rel or rel.startswith("/") or ".." in rel.split("/") \
                or rel.split("/")[0] in (".git", ".autocoder_home", ".autocoder_tmp"):
            raise ValueError(f"{rel!r} is outside the readable workspace")
        return self.root / rel

    def _write(self, rel: str, text: str) -> None:
        rel = safety.normalize(rel)
        why = safety.path_refusal(rel)
        if why:
            raise PermissionError(why)
        p = self._path(rel)
        old = p.read_text(encoding="utf-8") if p.exists() else None
        orig = self.changes[rel][0] if rel in self.changes else old
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self.changes[rel] = (orig, text)

    def apply(self, action: dict) -> str:
        """One action -> its observation (a bounded string). Never raises."""
        op = str((action or {}).get("op") or "")
        try:
            if op == "list":
                p = self._path(action.get("path") or ".")
                if not p.is_dir():
                    return f"list: {action.get('path')} is not a directory"
                names = sorted(f"{c.name}/" if c.is_dir() else c.name for c in p.iterdir()
                               if not c.name.startswith((".autocoder", ".git", "__pycache__")))
                return "\n".join(names[:200]) + ("\n..." if len(names) > 200 else "")
            if op == "read":
                p = self._path(action.get("path") or "")
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                a = max(1, int(action.get("start") or 1))
                b = min(len(lines), int(action.get("end") or a + READ_LINES - 1),
                        a + READ_LINES - 1)
                body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(a, b + 1))
                return f"{action.get('path')} lines {a}-{b} of {len(lines)}\n{body}"[:READ_CHARS]
            if op == "grep":
                rx = re.compile(str(action.get("pattern") or ""))
                p = self._path(action.get("path") or "brambleloop/src")
                files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()
                                                  and f.suffix in _TEXT
                                                  and "__pycache__" not in f.parts]
                hits = []
                for f in files[:GREP_FILES]:
                    for i, ln in enumerate(f.read_text(encoding="utf-8",
                                                       errors="replace").splitlines(), 1):
                        if rx.search(ln):
                            hits.append(f"{f.relative_to(self.root)}:{i}: {ln[:200]}")
                            if len(hits) >= GREP_HITS:
                                break
                    if len(hits) >= GREP_HITS:
                        break
                return "\n".join(hits) or "no match"
            if op == "edit":
                rel = action.get("path") or ""
                p = self._path(rel)
                text = p.read_text(encoding="utf-8")
                old, new = str(action.get("old") or ""), str(action.get("new") or "")
                n = text.count(old) if old else 0
                if n != 1:
                    return f"edit refused: 'old' occurs {n} times in {rel} (must be exactly once)"
                self._write(rel, text.replace(old, new, 1))
                return f"edited {rel}"
            if op == "create":
                rel = action.get("path") or ""
                if self._path(rel).exists():
                    return f"create refused: {rel} exists (use edit)"
                self._write(rel, str(action.get("content") or ""))
                return f"created {rel}"
            if op == "test":
                suite = str(action.get("suite") or "")
                if not _suite_ok(suite) or not (self.root / "brambleloop" / suite).exists():
                    return f"test refused: {suite!r} is not an existing tests/test_*.py file"
                # Code the model wrote runs here, so the rails that keep secrets, network,
                # subprocesses and spend out of a diff are checked before it runs at all.
                blocked = execution_rails(self.changes)
                if blocked:
                    return "test not run: " + "; ".join(blocked)[:1500]
                res = self.runner(self.root, suite, self.test_timeout_s)
                self.test_runs.append(res)
                return (f"{suite}: {'PASSED' if res['passed'] else 'FAILED'} rc={res['rc']} "
                        f"in {res['seconds']}s\n{res['tail'][-2500:]}")
            return f"unknown op {op!r}"
        except (OSError, ValueError, PermissionError, re.error, UnicodeDecodeError) as exc:
            return f"{op} refused: {type(exc).__name__}: {exc}"[:600]


def execution_rails(changes: dict) -> list[str]:
    """The rails that must hold before any model-written code is executed."""
    out = []
    for path, (old, new) in changes.items():
        why = safety.path_refusal(path)
        if why:
            out.append(why)
            continue
        out.extend(safety.secret_findings(path, old, new))
        out.extend(safety.spend_path_findings(path, old, new))
        out.extend(safety.test_execution_findings(path, old, new))
    return out


# ---- the loop --------------------------------------------------------------------------------

def ecr_brief(r: dict) -> str:
    keep = {k: r.get(k) for k in ("id", "title", "priority", "defect_class", "department",
                                  "module", "problem", "proposed_change",
                                  "acceptance_criteria", "occurrences")}
    ev = r.get("evidence") or {}
    keep["evidence"] = {k: v for k, v in ev.items() if k != "autocoder"}
    keep["engine_demand"] = is_engine_demand(r)
    return json.dumps(keep, default=str)[:6000]


ORIENTATION = (
    "Repository root holds brambleloop/ (the product). Source: brambleloop/src/brambleloop/ "
    "(packages: improve, cir, creative, commerce, intel, ops, runtime, app, ...). Tests: "
    "brambleloop/tests/test_*.py, each a plain script run as `python3 tests/test_x.py` from "
    "brambleloop/ with PYTHONPATH=src:tests; most import `_tmp` and build a temp sqlite "
    "Database. Job handlers register in runtime/release.py. ECR rows live in "
    "improve/ecr.py. Use `test` with a path relative to brambleloop/ (tests/test_x.py).")


@dataclass
class LoopResult:
    done: bool = False
    summary: str = ""
    targets: list = field(default_factory=list)
    iterations: int = 0
    stop: str = ""           # why the loop stopped without `done`
    transcript: list = field(default_factory=list)


def run_loop(r: dict, ws: Workspace, budget: Budget, gateway) -> LoopResult:
    from ..agents.registry import BudgetExceeded
    from ..core.resilience import MalformedModelOutput, TransientError

    out = LoopResult()
    L = budget.limits
    for it in range(1, L.iterations + 1):
        out.iterations = it
        transcript = "\n".join(out.transcript)[-L.transcript_chars:] or "(nothing yet)"
        left = (f"CA${max(0.0, L.ecr_cad - budget.ecr_before_cad - budget.run_cad()):.2f}, "
                f"{max(0, L.wall_s - int(budget.elapsed()))}s")
        values = {"ecr": ecr_brief(r), "roots": ", ".join(safety.ALLOWED_ROOTS),
                  "protected": ", ".join(safety.PROTECTED_PATHS[:40]) + ", ...",
                  "iteration": it, "max_iterations": L.iterations, "budget": left,
                  "orientation": ORIENTATION, "transcript": transcript}
        try:
            ans = guarded_call(budget, gateway, STEP_PROMPT, values)
        except BudgetStop as exc:
            out.stop = f"budget:{exc.which}"
            out.transcript.append(f"[stop] {exc}")
            return out
        except BudgetExceeded as exc:
            out.stop = "budget:gateway"
            out.transcript.append(f"[stop] gateway refused: {str(exc)[:200]}")
            return out
        except MalformedModelOutput as exc:
            out.transcript.append(f"[{it}] your reply was not the required JSON "
                                  f"({type(exc).__name__}); reply with JSON only")
            continue
        except TransientError as exc:
            out.stop = "model_unavailable"
            out.transcript.append(f"[stop] {type(exc).__name__}: {str(exc)[:200]}")
            return out
        except Exception as exc:  # noqa: BLE001 - no key, refused route: the environment's
            out.stop = "model_error"  # fault, not the request's; parked, never refused
            out.transcript.append(f"[stop] {type(exc).__name__}: {str(exc)[:200]}")
            return out
        actions = ans.get("actions") if isinstance(ans.get("actions"), list) else []
        out.transcript.append(f"[{it}] plan: {str(ans.get('plan') or '')[:500]}")
        for a in actions[:20]:
            obs = ws.apply(a if isinstance(a, dict) else {})
            desc = json.dumps({k: (v if k not in ("new", "content", "old") else
                                   f"<{len(str(v))} chars>") for k, v in
                               (a.items() if isinstance(a, dict) else [])})[:300]
            out.transcript.append(f"  > {desc}\n{obs[:OBS_CHARS]}")
        if isinstance(ans.get("targets"), list):
            out.targets = [t for t in ans["targets"] if _suite_ok(t)][:6]
        if ans.get("done") is True:
            out.done = True
            out.summary = str(ans.get("summary") or ans.get("plan") or "")[:2000]
            return out
    out.stop = "iterations"
    return out


# ---- the gate, the review, the push ------------------------------------------------------------

def text_changes(ws: Workspace) -> dict[str, tuple[str | None, str | None]]:
    return {p: (old, new) for p, (old, new) in ws.changes.items() if old != new}


def gate(ws: Workspace, loop: LoopResult, limits_: Limits) -> dict:
    """Deterministic: the rails, then the targeted suites + the two mandatory suites."""
    changes = text_changes(ws)
    rails = safety.check_changeset(changes)
    if rails:
        return {"passed": False, "stage": "rails", "reasons": rails[:20], "suites": []}
    changed_tests = [p[len("brambleloop/"):] for p in changes
                     if safety.is_test_file(p) and Path(p).name.startswith("test_")]
    targets = sorted({*loop.targets, *changed_tests})
    targets = [t for t in targets if _suite_ok(t) and (ws.root / "brambleloop" / t).exists()
               and t not in MANDATORY_SUITES]
    if not targets:
        return {"passed": False, "stage": "targets", "suites": [],
                "reasons": ["no targeted test suite: a change must be proven by a test it "
                            "names or changes"]}
    results = [ws.runner(ws.root, s, limits_.test_timeout_s)
               for s in [*targets, *MANDATORY_SUITES]]
    failed = [f"{x['suite']} rc={x['rc']}" for x in results if not x["passed"]]
    return {"passed": not failed, "stage": "tests" if failed else "passed",
            "reasons": failed, "suites": [{k: x[k] for k in ("suite", "rc", "passed",
                                                              "seconds")} for x in results],
            "targets": targets}


@dataclass(frozen=True)
class Review:
    ship: bool
    diff_sha256: str
    verdict: str
    reasons: tuple = ()
    checks: tuple = ()
    model: str = ""


REVIEW_CHECKS = ("no_weakened_gates", "no_deleted_or_skipped_tests", "no_vacuous_assertions",
                 "no_secrets", "no_spend_paths", "honest", "meets_ecr")


def diff_sha(diff: str) -> str:
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()


def review(r: dict, diff: str, summary: str, gate_result: dict, budget: Budget,
           gateway) -> Review:
    """The independent reviewer. SHIP only when it says SHIP and every check is true."""
    values = {"ecr": ecr_brief(r), "summary": summary or "(none given)",
              "rails": "passed (paths, test weakening, secrets, spend/network/exec, size)",
              "tests": json.dumps(gate_result.get("suites") or []),
              "diff": diff[:60_000]}
    ans = guarded_call(budget, gateway, REVIEW_PROMPT, values)
    checks = ans.get("checks") if isinstance(ans.get("checks"), dict) else {}
    verdict = str(ans.get("verdict") or "").strip().upper()
    all_true = all(checks.get(k) is True for k in REVIEW_CHECKS)
    reasons = tuple(str(x)[:300] for x in (ans.get("reasons") or [])[:10]) \
        if isinstance(ans.get("reasons"), list) else ()
    return Review(ship=(verdict == "SHIP" and all_true), diff_sha256=diff_sha(diff),
                  verdict=verdict or "NONE", reasons=reasons,
                  checks=tuple(sorted(k for k in REVIEW_CHECKS if checks.get(k) is True)),
                  model=str((ans.get("_meta") or {}).get("model") or ""))


class PushRefused(PermissionError):
    pass


def submit(host, *, ecr_id: int, base_sha: str, changes: dict, review_: Review,
           message: str) -> dict:
    """Push `auto/ecr-<id>`. Refused unless the reviewer SHIPped exactly this diff and every
    rail still passes on it; the ref is checked against the allowlist here and in the host."""
    if not isinstance(review_, Review) or review_.ship is not True:
        raise PushRefused("the independent reviewer did not SHIP this diff")
    diff = safety.unified_diff(changes)
    if review_.diff_sha256 != diff_sha(diff):
        raise PushRefused("the diff changed after review; it must be reviewed again")
    rails = safety.check_changeset(changes)
    if rails:
        raise PushRefused("rails refuse the diff: " + "; ".join(rails[:5]))
    ref = safety.branch_for(ecr_id)
    files = {p: new for p, (_old, new) in changes.items()}
    sha = host.push(ref, base_sha, files, message)
    return {"branch": ref[len("refs/heads/"):], "sha": sha}


# ---- recording -------------------------------------------------------------------------------

def _note(db, ecr_id: int, **fields) -> dict:
    from . import ecr

    return ecr.note_autocoder(db, ecr_id, **fields)


def _audit(db, detail: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=AGENT, action=ACTION, artifact=f"ecr:{detail.get('ecr')}",
                       detail=detail))


def _host_default():
    from .autocoder_git import GitHubHost

    return GitHubHost()


def _gateway_default(db, ctx_job_id, registry):
    from ..gateway import failover

    def make(task):
        return failover.job_gateway(db, task, registry=registry, agent=AGENT,
                                    job_id=ctx_job_id)
    return make


# ---- the job ---------------------------------------------------------------------------------

def run(db, *, registry=None, job_id: int | None = None, host=None, make_gateway=None,
        runner=run_suite, env=None, now: datetime | None = None, clock=time.monotonic,
        workdir: Path | None = None) -> dict:
    """One `improve.code` run: at most one request taken from pick to push (or refusal)."""
    from . import ecr

    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    if not enabled(env):
        return {"status": OFF, "work_done": 0,
                "reason": f"{ENABLED_VAR} is not set to 1 (kill switch OFF)"}
    blockers = []
    if host is None:
        from .autocoder_git import TOKEN_VAR

        if not (env.get(TOKEN_VAR) or "").strip():
            blockers.append(f"{TOKEN_VAR} is not set (OWNER_ACTIONS_AUTOCODER.md item 1)")
    base = base_ref(env)
    if not base:
        blockers.append(f"no integration base: set {BASE_VAR} or run where {PROD_SHA_VAR} "
                        f"is reported")
    if shutil.which("git") is None:
        blockers.append("git binary not in this image (test_w4_resume_runner needs it)")
    if blockers:
        out = {"status": UNKNOWN, "work_done": 0, "blockers": blockers,
               "reason": "blocked before any spend: " + "; ".join(blockers)}
        _audit(db, {"ecr": None, "outcome": UNKNOWN, "blockers": blockers})
        return out
    L = limits(env)
    month_before = month_spent_cad(db, now)
    if month_before >= L.month_cad:
        out = {"status": PARKED, "work_done": 0,
               "reason": f"autocoder month spend CA${month_before:.2f} reached the "
                         f"sub-ceiling CA${L.month_cad:.2f}"}
        _audit(db, {"ecr": None, "outcome": PARKED, "reason": out["reason"]})
        return out
    r = pick(db, now)
    if r is None:
        return {"status": IDLE, "work_done": 0, "reason": "no eligible open change request"}
    prev = (r.get("evidence") or {}).get("autocoder") or {}
    attempts = int(prev.get("attempts") or 0) + 1
    _note(db, r["id"], status=CODING, at=now.isoformat(), attempts=attempts, job=job_id,
          base=base)
    budget = Budget(L, month_before, ecr_before_cad=float(prev.get("spent_cad") or 0.0),
                    ecr_before_tokens=int(prev.get("tokens") or 0), clock=clock)
    budget.started = clock()
    host = host or _host_default()
    make_gateway = make_gateway or _gateway_default(db, job_id, registry)
    scratch = tempfile.TemporaryDirectory(prefix="autocoder-",
                                          dir=str(workdir) if workdir else None)
    tmp = Path(scratch.name)
    result: dict = {"ecr": r["id"], "attempt": attempts, "base": base}
    try:
        try:
            base_sha = host.materialize(base, tmp)
        except Exception as exc:  # noqa: BLE001 - a host failure is retryable, not a refusal
            return _park(db, r, result, budget, attempts,
                         f"workspace: {type(exc).__name__}: {str(exc)[:200]}")
        result["base_sha"] = base_sha
        ws = Workspace(tmp, runner=runner, test_timeout_s=L.test_timeout_s)
        try:
            step_gw = make_gateway(STEP_TASK)
        except Exception as exc:  # noqa: BLE001 - Parked, no provider, refused route
            return _park(db, r, result, budget, attempts,
                         f"model unavailable: {type(exc).__name__}: {str(exc)[:200]}")
        loop = run_loop(r, ws, budget, step_gw)
        result.update(iterations=loop.iterations, loop_stop=loop.stop or None)
        if loop.stop in ("model_unavailable", "model_error"):
            return _park(db, r, result, budget, attempts,
                         f"{loop.stop}: {(loop.transcript or [''])[-1][:200]}")
        if not loop.done:
            return _refuse(db, r, result, budget, "did_not_finish",
                           [f"stopped: {loop.stop or 'not done'}"])
        changes = text_changes(ws)
        g = gate(ws, loop, L)
        result["gate"] = {k: g[k] for k in ("passed", "stage", "suites")}
        if not g["passed"]:
            return _refuse(db, r, result, budget, f"gate_{g['stage']}", g["reasons"])
        diff = safety.unified_diff(changes)
        try:
            review_gw = make_gateway(REVIEW_TASK)
            rv = review(r, diff, loop.summary, g, budget, review_gw)
        except BudgetStop as exc:
            return _refuse(db, r, result, budget, f"budget_{exc.which}", [str(exc)])
        except Exception as exc:  # noqa: BLE001 - no review means no push; retried later
            return _park(db, r, result, budget, attempts,
                         f"review unavailable: {type(exc).__name__}: {str(exc)[:200]}")
        result["review"] = {"verdict": rv.verdict, "ship": rv.ship, "model": rv.model,
                            "checks_true": list(rv.checks), "reasons": list(rv.reasons)}
        if not rv.ship:
            return _refuse(db, r, result, budget, "review_block",
                           list(rv.reasons) or [f"verdict {rv.verdict}"])
        message = (f"ENG-AUTOCODER: ECR {r['id']} -- {str(r.get('title') or '')[:72]}\n\n"
                   f"{loop.summary[:1500]}\n\nBase: {base_sha}\nReview: SHIP "
                   f"({rv.model or 'reviewer'})\nSuites: "
                   + ", ".join(s["suite"] for s in g["suites"])
                   + f"\nRun by the improve.code job {job_id}; promotion is the "
                     f"certify-and-promote pipeline's.")
        try:
            pushed = submit(host, ecr_id=r["id"], base_sha=base_sha, changes=changes,
                            review_=rv, message=message)
        except PushRefused as exc:
            return _refuse(db, r, result, budget, "push_refused", [str(exc)])
        except Exception as exc:  # noqa: BLE001 - a push the host refused is retryable
            return _park(db, r, result, budget, attempts,
                         f"push: {type(exc).__name__}: {str(exc)[:200]}")
        result.update(status=SUBMITTED, branch=pushed["branch"], sha=pushed["sha"],
                      files=sorted(changes), diff_sha256=rv.diff_sha256)
        _note(db, r["id"], status=SUBMITTED, at=datetime.now(timezone.utc).isoformat(),
              attempts=attempts, branch=pushed["branch"], sha=pushed["sha"],
              base=base_sha, spent_cad=round(budget.ecr_before_cad + budget.run_cad(), 6),
              tokens=budget.ecr_before_tokens + budget.run_tokens(), reason=None)
        for to in (ecr.BUILDING, ecr.REVIEWED):
            try:
                ecr.advance(db, r["id"], to, by=AGENT, commit=pushed["sha"],
                            note=f"auto/ecr-{r['id']} at {pushed['sha'][:12]}")
            except ecr.ECRRefused:
                pass
        return _finish(db, result, budget)
    finally:
        scratch.cleanup()


def _park(db, r: dict, result: dict, budget: Budget, attempts: int, reason: str) -> dict:
    """Not the request's fault (host, model or reviewer unavailable): clear `coding` so it is
    picked again, do not count the attempt, but keep what was spent against its budget."""
    result.update(status=PARKED, reason=reason)
    _note(db, r["id"], status=None, attempts=attempts - 1, last=reason[:300],
          at=datetime.now(timezone.utc).isoformat(),
          spent_cad=round(budget.ecr_before_cad + budget.run_cad(), 6),
          tokens=budget.ecr_before_tokens + budget.run_tokens())
    return _finish(db, result, budget)


def _refuse(db, r: dict, result: dict, budget: Budget, reason: str, detail: list) -> dict:
    result.update(status=REFUSED, reason=reason, detail=[str(d)[:300] for d in detail[:20]])
    _note(db, r["id"], status=REFUSED, at=datetime.now(timezone.utc).isoformat(),
          attempts=result.get("attempt"), reason=reason,
          detail=" | ".join(result["detail"])[:1000],
          spent_cad=round(budget.ecr_before_cad + budget.run_cad(), 6),
          tokens=budget.ecr_before_tokens + budget.run_tokens())
    return _finish(db, result, budget)


def _finish(db, result: dict, budget: Budget) -> dict:
    result["spent_cad"] = budget.run_cad()
    result["tokens"] = budget.run_tokens()
    result["work_done"] = 1 if result.get("status") == SUBMITTED else 0
    _audit(db, {"ecr": result.get("ecr"), "outcome": result.get("status"),
                **{k: result.get(k) for k in ("reason", "branch", "sha", "spent_cad", "tokens",
                                              "iterations", "base_sha", "attempt")}})
    return result


def mark_certified(db, ecr_id: int, *, sha: str, by: str) -> dict:
    """For the integrator / pipeline readback: the submitted branch passed certification."""
    return _note(db, ecr_id, status=CERTIFIED, certified_sha=sha[:64], certified_by=by,
                 at=datetime.now(timezone.utc).isoformat())


# ---- Mission Control ------------------------------------------------------------------------

def classify(r: dict, now: datetime) -> str:
    from . import ecr

    ac = (r.get("evidence") or {}).get("autocoder") or {}
    st = ac.get("status")
    if r["state"] in (ecr.DEPLOYED, ecr.VERIFIED) and ac.get("sha"):
        return "deployed"
    if st == CERTIFIED:
        return "certified"
    if st == SUBMITTED:
        return "submitted"
    if st == CODING:
        return "coding"
    if st == REFUSED:
        return "refused"
    return "open" if r["state"] in (ecr.FILED, ecr.REOPENED) else "other"


def panel(db, *, now: datetime | None = None, env=None) -> dict:
    """ECRs by autocoder status, spend per request and for the month, switch and blockers."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import ecr
    from .autocoder_git import TOKEN_VAR

    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    L = limits(env)
    rows = ecr.listing(db, open_only=False, limit=500)
    counts = {k: 0 for k in ("open", "coding", "submitted", "certified", "deployed",
                             "refused")}
    items, refused = [], []
    for r in rows:
        c = classify(r, now)
        if c in counts:
            counts[c] += 1
        ac = (r.get("evidence") or {}).get("autocoder") or {}
        if ac or c == "open":
            items.append({"id": r["id"], "title": r["title"], "priority": r["priority"],
                          "state": r["state"], "autocoder": c,
                          "engine_demand": is_engine_demand(r),
                          "spent_cad": ac.get("spent_cad"), "tokens": ac.get("tokens"),
                          "attempts": ac.get("attempts"), "branch": ac.get("branch"),
                          "sha": ac.get("sha"), "reason": ac.get("reason")})
        if c == "refused":
            refused.append({"id": r["id"], "reason": ac.get("reason"),
                            "detail": str(ac.get("detail") or "")[:300]})
    blockers = []
    if not (env.get(TOKEN_VAR) or "").strip():
        blockers.append(f"{TOKEN_VAR} not set")
    if not base_ref(env):
        blockers.append("no integration base")
    if shutil.which("git") is None:
        blockers.append("git binary not in this image")
    with db.session() as s:
        last = s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                         .order_by(AuditLog.id.desc()).limit(1)).first()
        last_run = None if last is None else {
            "at": _aware(last.at).isoformat(), "outcome": (last.detail or {}).get("outcome"),
            "ecr": (last.detail or {}).get("ecr")}
    month = month_spent_cad(db, now)
    on = enabled(env)
    status = ("OFF" if not on else "BLOCKED" if blockers else "OK")
    return {"schema": "brambleloop.autocoder.panel.v1", "as_of": now.isoformat(),
            "status": status, "enabled": on, "kill_switch": ENABLED_VAR,
            "blockers": blockers, "counts": counts, "refused": refused[:50],
            "ecrs": items[:100], "month_spend_cad": month,
            "month_ceiling_cad": L.month_cad,
            "month_remaining_cad": round(max(0.0, L.month_cad - month), 6),
            "limits": {"ecr_cad": L.ecr_cad, "ecr_tokens": L.ecr_tokens, "wall_s": L.wall_s,
                       "iterations": L.iterations},
            "last_run": last_run, "branch_allowlist": safety.ALLOWED_REF_PREFIX + "*",
            "note": ("promotion is the certify-and-promote pipeline's; this job pushes only "
                     "auto/* branches")}


def readback(db, *, now: datetime | None = None) -> dict:
    """Counts and booleans only, for the read-only-token evidence readback."""
    p = panel(db, now=now)
    return {"readable": True, "status": p["status"], "enabled": p["enabled"],
            "blocked": bool(p["blockers"]), "blockers": len(p["blockers"]),
            "counts": p["counts"],
            "within_month_ceiling": p["month_spend_cad"] <= p["month_ceiling_cad"],
            "last_run_outcome": (p["last_run"] or {}).get("outcome")}
