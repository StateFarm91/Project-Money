"""Which code is actually running (Execution Directive: never claim a deployment exists).

Every other honesty check in this system compares a claim against evidence. Deployment was
the exception: the only way to tell whether a fix had reached production was to look for its
*effects* and hope no other change explained them. That is how three idempotency layers
(B-070, B-071, B-072) each took a round of "the code is fixed and production disagrees" to
diagnose -- the question "is production running this commit?" had no answer, so "the deploy
landed" was an assumption dressed as a fact.

The commit is read from the build environment, which is the only place that knows it: the
container has no `.git`, so nothing inside the running image can derive it. When the platform
does not provide one the answer is `unknown`, reported as such. An invented or defaulted
value would be worse than no value, because a deploy check would then pass against a
placeholder.
"""
from __future__ import annotations

import os

UNKNOWN = "unknown"

# Railway sets the first of these at build time; the others are here so that a move to
# another platform does not silently lose the signal.
_COMMIT_VARS = (
    "RAILWAY_GIT_COMMIT_SHA",
    "BRAMBLELOOP_COMMIT",
    "GIT_COMMIT_SHA",
    "SOURCE_COMMIT",
)
_BRANCH_VARS = ("RAILWAY_GIT_BRANCH", "BRAMBLELOOP_BRANCH", "GIT_BRANCH")


def _first(names: tuple[str, ...], env: dict[str, str]) -> str:
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return UNKNOWN


def commit(env: dict[str, str] | None = None) -> str:
    """The full commit sha the running image was built from, or `unknown`."""
    return _first(_COMMIT_VARS, env if env is not None else dict(os.environ))


def identity(env: dict[str, str] | None = None) -> dict[str, object]:
    """Build identity for `/api/status`, with `known` stated rather than inferred.

    `known` exists so a caller does not have to compare against the string "unknown" to find
    out whether the commit means anything. A deploy check that treats `unknown` as a value
    would report success the moment the environment variable went missing.
    """
    e = env if env is not None else dict(os.environ)
    sha = commit(e)
    known = sha != UNKNOWN
    return {
        "commit": sha,
        "commit_short": sha[:12] if known else UNKNOWN,
        "branch": _first(_BRANCH_VARS, e),
        "known": known,
    }


def serves(sha: str, env: dict[str, str] | None = None) -> bool:
    """Is the running image built from `sha`? False when either side is unknown.

    Prefix comparison, because a caller usually has a short sha from `git rev-parse --short`
    and the platform reports the full one. Deliberately one-directional: an unknown build
    never matches anything, so "I cannot tell" is never reported as "yes".
    """
    running = commit(env)
    if running == UNKNOWN or not sha.strip():
        return False
    wanted = sha.strip().lower()
    running = running.lower()
    return running.startswith(wanted) or wanted.startswith(running)
