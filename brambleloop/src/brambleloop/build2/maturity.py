"""How far a requirement actually got: implemented -> tested -> deployed -> exercised ->
evidenced -> production-observed.

The registry answers "is it covered". That question was never wrong, but it was answering a
smaller question than the word suggests, and the owner named the gap exactly: *a requirement
is not complete merely because code exists.* `covered` means somebody read the spec line,
read the module and judged that the module satisfies it. That is a real judgement and it is
rung one and a half. It is not deployment, it has never been exercised by it, and it says
nothing about whether the code has ever run against production data.

Two hundred and twenty-two of those, reported as "69.4% complete", is the most flattering
number this build produces, and flattering numbers are the ones that need a floor under them.

So this module computes the ladder from evidence, and it is built to be able to say no:

    implemented          the module the audit note names exists in the package
    tested               a file under tests/ names that module
    deployed             the module imports in *this* process and this process is a
                         deployed image -- unknowable from a laptop, so unmeasurable there
    exercised            a job whose handler reaches that module has actually run
    evidenced            that job finished and left an append-only audit row behind it
    production_observed  the evidence above is in a Postgres database and recent

Three rules keep it from becoming another flattering number.

**The registry's own status is never evidence.** Nothing in here reads `covered`. The status
is the claim under test; a ladder that consulted it would be measuring the claim against
itself.

**Unmeasurable is not a pass and not a failure.** Most requirements are libraries that no job
type reaches, and a library called from a request path leaves no job row. Reporting those as
"not exercised" would manufacture 200 failures out of the measurement's own blind spot, which
is the mirror image of the defect and just as dishonest. They are unmeasurable, counted in
their own column, and never added to either of the other two.

**The ladder does not skip.** A rung above an unmeasurable rung is unmeasurable, and a rung
above a failed rung is a failure. Otherwise a module nobody can find would still be able to
report that it was exercised, because some job somewhere ran.

The job-type map is derived rather than declared: `runtime/release.py` is parsed, and each
`@handlers.register("x.y")` function is read for the Brambleloop modules it actually reaches.
A hand-written table would drift the way the gate table drifted from the registry notes
(B-...), and always in the flattering direction.
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from . import requirements as reg

YES = "yes"
NO = "no"
UNMEASURABLE = "unmeasurable"

IMPLEMENTED = "implemented"
TESTED = "tested"
DEPLOYED = "deployed"
EXERCISED = "exercised"
EVIDENCED = "evidenced"
PRODUCTION_OBSERVED = "production_observed"

RUNGS: tuple[str, ...] = (IMPLEMENTED, TESTED, DEPLOYED, EXERCISED, EVIDENCED,
                          PRODUCTION_OBSERVED)

# What "recent" means for the top rung. Long enough that a weekly cadence still counts,
# short enough that a thing which ran once in July is not called production-observed today.
OBSERVED_WITHIN_DAYS = 14

_PACKAGE = Path(__file__).resolve().parent.parent          # src/brambleloop
_TESTS = _PACKAGE.parent.parent / "tests"
_RELEASE = _PACKAGE / "runtime" / "release.py"

# The audit notes name modules the way a person writes them: `commerce/lanes.py operates both
# queues`, or `runrate.decompose() shows the target`. Both forms are matched, and anything
# that does not resolve to a real file is dropped rather than guessed at -- a note that says
# "the compiler" names something true and unusable, and inventing a module for it would put a
# rung under a requirement that has no evidence.
_PATH_FORM = re.compile(r"\b([a-z0-9_]+(?:/[a-z0-9_]+)*\.py)\b")
# `growth/portfolio.classify`, `swarm/orchestrate.ThrashDetector` -- a path, then the thing
# in it. The slash makes this unambiguous, so no resolution guess is involved.
_SLASH_ATTR_FORM = re.compile(r"\b([a-z0-9_]+(?:/[a-z0-9_]+)+)\.[A-Za-z_][A-Za-z0-9_]*")
# `runrate.decompose()`, `runrate.SCALE_RULES`, `identity.DRIFT_DIMENSIONS`. The trailing
# call parenthesis was required at first and it cost ten requirements: a note naming a
# module's table rather than its function is naming the same module.
_DOTTED_FORM = re.compile(
    r"\b([a-z0-9_]+(?:\.[a-z0-9_]+)*)\.(?:[a-z0-9_]+\(|[A-Z][A-Za-z0-9_]*)")


def _module_of(token: str) -> str | None:
    """Resolve a note's token to a package-relative module path, or None."""
    token = token.strip().strip("`")
    if token.endswith(".py"):
        candidate = _PACKAGE / token
        if candidate.is_file():
            return token
        # A bare `lanes.py` with no package: accept it only if exactly one file matches,
        # because two candidates mean the note did not say which.
        hits = [p for p in _PACKAGE.rglob(token) if p.is_file()]
        if len(hits) == 1:
            return str(hits[0].relative_to(_PACKAGE))
        return None
    parts = token.split(".")
    candidate = _PACKAGE / Path(*parts[:-1]) / f"{parts[-1]}.py"
    if candidate.is_file():
        return str(candidate.relative_to(_PACKAGE))
    candidate = _PACKAGE / Path(*parts).with_suffix(".py")
    if candidate.is_file():
        return str(candidate.relative_to(_PACKAGE))
    hits = [p for p in _PACKAGE.rglob(f"{parts[0]}.py") if p.is_file()]
    if len(hits) == 1:
        return str(hits[0].relative_to(_PACKAGE))
    return None


def modules_named(note: str) -> list[str]:
    """Every module the audit note names and that actually exists, in order."""
    found: list[str] = []
    for pattern in (_PATH_FORM, _SLASH_ATTR_FORM, _DOTTED_FORM):
        for match in pattern.finditer(note):
            resolved = _module_of(match.group(1))
            if resolved and resolved not in found:
                found.append(resolved)
    return found


# ---------------------------------------------------------------------------
# Which job types reach which modules, derived from the handler source


def _names_in(node: ast.AST) -> set[str]:
    """Every dotted name and imported module referenced inside a function body."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.ImportFrom) and child.module:
            out.add(child.module)
            for alias in child.names:
                out.add(f"{child.module}.{alias.name}")
                out.add(alias.name)
        elif isinstance(child, ast.Import):
            for alias in child.names:
                out.add(alias.name)
        elif isinstance(child, ast.Attribute):
            parts: list[str] = []
            cursor: ast.AST = child
            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
            if isinstance(cursor, ast.Name):
                parts.append(cursor.id)
                out.add(".".join(reversed(parts)))
                out.add(cursor.id)
    return out


@lru_cache(maxsize=1)
def handler_modules() -> dict[str, tuple[str, ...]]:
    """`{job_type: (module, ...)}` parsed out of `runtime/release.py`.

    Derived rather than declared. The alternative is a table somebody maintains, and the
    only thing this build has learnt more than once is that two places holding the same
    fact disagree, always in whichever direction flatters the report.
    """
    tree = ast.parse(_RELEASE.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        job_types = [
            d.args[0].value
            for d in node.decorator_list
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and d.func.attr == "register" and d.args
            and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)]
        if not job_types:
            continue
        modules = {m for name in _names_in(node) if (m := _module_of(name))}
        for job_type in job_types:
            out[job_type] = tuple(sorted(modules))
    return out


@lru_cache(maxsize=1)
def _module_to_jobs() -> dict[str, tuple[str, ...]]:
    out: dict[str, set[str]] = {}
    for job_type, modules in handler_modules().items():
        for module in modules:
            out.setdefault(module, set()).add(job_type)
    return {k: tuple(sorted(v)) for k, v in out.items()}


def jobs_reaching(module: str) -> tuple[str, ...]:
    return _module_to_jobs().get(module, ())


# ---------------------------------------------------------------------------
# The rungs


@lru_cache(maxsize=1)
def _tested_modules() -> frozenset[str]:
    """Every Brambleloop module the suite imports, parsed rather than grepped.

    The first version searched the test sources for the dotted module path and reported
    nine covered requirements as untested. All nine had tests; they were imported as
    `from brambleloop.culture import translate`, in which the string `culture.translate`
    never appears. A matcher that cannot see the ordinary import form is not measuring
    test coverage, it is measuring how people happen to write imports -- and it fails in
    the direction that invents work.
    """
    if not _TESTS.is_dir():
        return frozenset()
    found: set[str] = set()
    for path in sorted(_TESTS.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                                     # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
                for alias in node.names:
                    found.add(f"{node.module}.{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name)
    return frozenset(
        n[len("brambleloop."):] for n in found if n.startswith("brambleloop."))


def _tested(module: str) -> bool:
    return module[:-3].replace("/", ".") in _tested_modules()


def _importable(module: str) -> bool:
    import importlib.util

    name = "brambleloop." + module[:-3].replace("/", ".")
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _is_deployed_image(env: dict[str, str] | None) -> bool:
    from ..core import build

    return build.commit(env) != build.UNKNOWN


# The rungs that imply one another. A job that ran, ran in the deployed image, and the image
# contains the module -- so evidence high on this chain settles everything below it, and a
# failure low on it settles everything above. `tested` is deliberately not on the chain:
# untested code deploys and runs perfectly well, and a suite proves nothing about production.
# It is a rung of the ladder because the owner's sequence puts it there, and it gates
# `reached`, but it neither implies nor is implied by the rest.
_IMPLICATION_CHAIN: tuple[str, ...] = (IMPLEMENTED, DEPLOYED, EXERCISED, EVIDENCED,
                                       PRODUCTION_OBSERVED)


def _settle(raw: dict[str, str]) -> dict[str, str]:
    """Resolve the chain in both directions.

    Downward, because evidence is transitive: a job observed in production last week is
    proof the module shipped, and reporting `deployed: unmeasurable` beside
    `exercised: yes` would be the report arguing with itself. Upward, because a missing
    module cannot have been run: without this, each rung is independently true and the
    ladder means nothing -- a module nobody can find still reports being exercised on the
    strength of some job somewhere having run.
    """
    out = dict(raw)
    # Upward first, and the order is the whole argument. A module that is not on disk is a
    # fact read off the filesystem; "a job of that type ran" is a fact about a job type that
    # several modules share. When those two contradict each other the filesystem wins, and
    # running the passes the other way round would let a shared job type resurrect a module
    # nobody can find.
    for i, rung in enumerate(_IMPLICATION_CHAIN):
        if out[rung] == NO:
            for higher in _IMPLICATION_CHAIN[i + 1:]:
                out[higher] = NO
            break
    for i in range(len(_IMPLICATION_CHAIN) - 1, 0, -1):
        if out[_IMPLICATION_CHAIN[i]] == YES:
            for lower in _IMPLICATION_CHAIN[:i]:
                out[lower] = YES
    return out


def ladder(db, requirement, *, signals: dict | None = None,
           env: dict[str, str] | None = None) -> dict:
    """The six rungs for one requirement, each with what decided it.

    `signals` is the production evidence, gathered once for the whole registry by
    `_signals` rather than queried per requirement -- 320 requirements against a live
    Postgres is a report that nobody runs twice.
    """
    modules = modules_named(requirement.note)
    if not modules:
        return {
            "requirement_id": requirement.id,
            "modules": [],
            "rungs": {r: {"verdict": UNMEASURABLE,
                          "why": "the audit note names no module this can look for"}
                      for r in RUNGS},
            "reached": None,
        }

    signals = signals if signals is not None else _signals(db)
    raw: dict[str, str] = {}
    why: dict[str, str] = {}
    extra: dict[str, dict] = {}

    present = [m for m in modules if (_PACKAGE / m).is_file()]
    raw[IMPLEMENTED] = YES if len(present) == len(modules) else NO
    why[IMPLEMENTED] = (", ".join(modules) if len(present) == len(modules)
                        else f"{len(present)} of {len(modules)} named modules exist")

    named_in_tests = [m for m in modules if _tested(m)]
    raw[TESTED] = YES if named_in_tests else NO
    why[TESTED] = (f"named by the suite: {', '.join(named_in_tests)}" if named_in_tests
                   else "no test file imports any of these modules")

    if not _is_deployed_image(env):
        raw[DEPLOYED] = UNMEASURABLE
        why[DEPLOYED] = ("this process is not a deployed image -- there is no commit to "
                         "check against, and an import that succeeds on a laptop is rung "
                         "one wearing rung three's name")
    elif all(_importable(m) for m in modules):
        raw[DEPLOYED], why[DEPLOYED] = YES, "present in the running image"
    else:
        raw[DEPLOYED], why[DEPLOYED] = NO, "the running image cannot import it"

    job_types = sorted({j for m in modules for j in jobs_reaching(m)})
    if not job_types:
        raw[EXERCISED] = UNMEASURABLE
        why[EXERCISED] = ("no registered job type reaches this module. A library called "
                          "from a request path leaves no job row, so this is unreadable "
                          "rather than unexercised")
        raw[EVIDENCED], why[EVIDENCED] = UNMEASURABLE, "nothing to have left an audit row"
        raw[PRODUCTION_OBSERVED] = UNMEASURABLE
        why[PRODUCTION_OBSERVED] = "nothing to have been observed"
    else:
        extra[EXERCISED] = {"job_types": job_types}
        ran = sorted(j for j in job_types if j in signals["jobs_seen"])
        raw[EXERCISED] = YES if ran else NO
        why[EXERCISED] = (f"jobs that ran: {', '.join(ran)}" if ran
                          else f"registered but never run: {', '.join(job_types)}")

        audited = sorted(j for j in job_types if j in signals["jobs_audited"])
        raw[EVIDENCED] = YES if audited else NO
        why[EVIDENCED] = (
            f"finished and left an append-only audit row: {', '.join(audited)}" if audited
            else "ran, but left no audit row behind it -- a job row is retention, an "
                 "audit row is the record")

        if not signals["is_production"]:
            raw[PRODUCTION_OBSERVED] = UNMEASURABLE
            why[PRODUCTION_OBSERVED] = (
                f"this database is {signals['engine']}, not production. A suite that "
                "could satisfy this rung would be a suite that proves a deploy")
        else:
            recent = sorted(j for j in job_types if j in signals["jobs_recent"])
            raw[PRODUCTION_OBSERVED] = YES if recent else NO
            why[PRODUCTION_OBSERVED] = (
                f"seen in production within {OBSERVED_WITHIN_DAYS} days: "
                f"{', '.join(recent)}" if recent
                else f"nothing in the last {OBSERVED_WITHIN_DAYS} days")

    settled = _settle(raw)
    rungs = {}
    for rung in RUNGS:
        entry = {"verdict": settled[rung], "why": why[rung], **extra.get(rung, {})}
        if settled[rung] != raw[rung]:
            entry["settled_from"] = raw[rung]
            entry["why"] = (
                f"{why[rung]} -- settled to {settled[rung]} by the rungs around it, "
                "because evidence of running is evidence of shipping and a module that "
                "is not there cannot have run")
        rungs[rung] = entry

    reached = None
    for rung in RUNGS:
        if rungs[rung]["verdict"] != YES:
            break
        reached = rung
    return {"requirement_id": requirement.id, "modules": modules, "rungs": rungs,
            "reached": reached}


def _signals(db) -> dict:
    """Every production fact the ladder needs, in three queries rather than nine hundred."""
    from sqlalchemy import select

    from ..core.models import AuditLog, Job, JobStatus

    if db is None:
        return {"jobs_seen": set(), "jobs_audited": set(), "jobs_recent": set(),
                "is_production": False, "engine": "none"}

    engine = db.engine.dialect.name if hasattr(db, "engine") else "unknown"
    cutoff = datetime.now(timezone.utc) - timedelta(days=OBSERVED_WITHIN_DAYS)
    with db.session() as s:
        rows = [(j.id, j.job_type, j.status, j.finished_at)
                for j in s.scalars(select(Job))]
        audited_job_ids = {a.job_id for a in s.scalars(select(AuditLog))
                           if a.job_id is not None}

    seen = {t for _, t, _, _ in rows}
    done = {jid: t for jid, t, status, _ in rows if status == JobStatus.DONE}
    recent = {t for _, t, status, finished in rows
              if status == JobStatus.DONE and finished is not None
              and (finished if finished.tzinfo else
                   finished.replace(tzinfo=timezone.utc)) >= cutoff}
    return {
        "jobs_seen": seen,
        "jobs_audited": {t for jid, t in done.items() if jid in audited_job_ids},
        "jobs_recent": recent,
        "is_production": engine == "postgresql",
        "engine": engine,
    }


def report(db, *, env: dict[str, str] | None = None) -> dict:
    """The ladder across every requirement the registry calls covered.

    Only `covered` ones, because the others have never claimed to be finished and adding
    them would pad the unmeasurable column with requirements nobody asserted anything about.
    """
    signals = _signals(db)
    covered = reg.by_status(reg.COVERED)
    ladders = [ladder(db, r, signals=signals, env=env) for r in covered]

    tally = {rung: {YES: 0, NO: 0, UNMEASURABLE: 0} for rung in RUNGS}
    for entry in ladders:
        for rung in RUNGS:
            tally[rung][entry["rungs"][rung]["verdict"]] += 1

    unreadable = sorted(e["requirement_id"] for e in ladders if not e["modules"])
    return {
        "covered_by_the_registry": len(covered),
        "rungs": tally,
        "highest_rung_reached": {
            rung: sum(1 for e in ladders if e["reached"] == rung) for rung in RUNGS},
        "no_rung_reached": sum(1 for e in ladders if e["reached"] is None),
        "notes_naming_no_module": {
            "count": len(unreadable), "requirements": unreadable[:40],
            "why": ("these were audited in prose that names no module, so the ladder has "
                    "nothing to look for. They are not counted as reaching any rung, and "
                    "they are not counted as failing one either")},
        "is_production": signals["is_production"],
        "engine": signals["engine"],
        "what_covered_means": (
            "somebody read the spec line, read the module and judged that the module "
            "satisfies it. That is a real judgement and it is not deployment, it is not "
            "exercise, and it is not production. This ladder is the difference, and the "
            "registry's own status is never consulted as evidence for any rung of it"),
    }
