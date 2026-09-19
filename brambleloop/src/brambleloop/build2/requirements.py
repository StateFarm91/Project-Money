"""The Build-2 requirement registry: all 320 upgrades of v1.4.3, and where each one stands.

`spec/08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf` is canonical. This module is the
audit of that document against the Build-1 system, held as data rather than prose so that
"what is left" is a query rather than somebody's recollection.

The status vocabulary is deliberately five values, not two, because "done / not done" is what
makes a large build dishonest. A requirement that needs an Etsy shop is not the same kind of
unfinished as one nobody has written yet, and conflating them either hides real work or
manufactures blockers that excuse it:

    covered      Build 1 implements it. `note` names the module that does.
    partial      Something real exists and is not sufficient. `note` states the gap.
    missing      No implementation. Executable Build-2 work, owned by this build.
    owner_gated  Needs an owner action, credential, service or spend approval first. The
                 surrounding machinery is usually still buildable and is tracked separately.
    data_gated   Needs real market, customer or sales data that cannot exist before launch.

`owner_gated` and `data_gated` are not hiding places. Each carries the specific dependency,
and `executable()` deliberately excludes them so the remaining work is never overstated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Inside the package on purpose. It used to live at the repository root, which worked
# everywhere except the container -- the Dockerfile copies `src`, so the registry was never
# shipped and every endpoint that reads it returned 500 in production while passing every
# test locally. A data file beside its module travels with it by construction rather than by
# somebody remembering a COPY line.
REGISTRY_PATH = Path(__file__).resolve().parent / "requirements.json"

COVERED = "covered"
PARTIAL = "partial"
MISSING = "missing"
OWNER_GATED = "owner_gated"
DATA_GATED = "data_gated"

STATUSES = (COVERED, PARTIAL, MISSING, OWNER_GATED, DATA_GATED)

# What this build is responsible for finishing. Not a judgement about importance: an
# owner-gated requirement can be the most important thing in the document (the MJs mission
# is), it simply cannot be completed by writing code today.
EXECUTABLE = (PARTIAL, MISSING)

TOTAL = 320


@dataclass(frozen=True)
class Requirement:
    id: int
    title: str
    body: str
    version: str
    section: str
    status: str
    note: str

    @property
    def executable(self) -> bool:
        return self.status in EXECUTABLE

    @property
    def done(self) -> bool:
        return self.status == COVERED

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "version": self.version,
                "section": self.section, "status": self.status, "note": self.note}


@lru_cache(maxsize=1)
def load() -> tuple[Requirement, ...]:
    """Every requirement, by id. Cached: the registry is a build-time artifact."""
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    reqs = tuple(Requirement(**r) for r in raw)
    _validate(reqs)
    return reqs


def _validate(reqs: tuple[Requirement, ...]) -> None:
    """Refuse a registry that has quietly lost or duplicated a requirement.

    The spec is numbered 1..320 with no gaps. A registry that silently drops one is worse
    than no registry, because the coverage percentage would still look plausible.
    """
    ids = [r.id for r in reqs]
    if len(ids) != TOTAL:
        raise ValueError(f"registry holds {len(ids)} requirements; v1.4.3 defines {TOTAL}")
    if sorted(ids) != list(range(1, TOTAL + 1)):
        gaps = sorted(set(range(1, TOTAL + 1)) - set(ids))
        raise ValueError(f"registry is not a complete 1..{TOTAL} spine; missing {gaps[:10]}")
    bad = [r.id for r in reqs if r.status not in STATUSES]
    if bad:
        raise ValueError(f"requirements with an unknown status: {bad}")
    unexplained = [r.id for r in reqs if not r.note.strip()]
    if unexplained:
        raise ValueError(f"requirements with no note: {unexplained}")


def get(requirement_id: int) -> Requirement:
    for r in load():
        if r.id == requirement_id:
            return r
    raise KeyError(f"no requirement {requirement_id}")


def by_status(status: str) -> tuple[Requirement, ...]:
    return tuple(r for r in load() if r.status == status)


def executable() -> tuple[Requirement, ...]:
    """What Build 2 still owes, excluding anything waiting on the owner or on real data."""
    return tuple(r for r in load() if r.executable)


def counts() -> dict[str, int]:
    return {s: len(by_status(s)) for s in STATUSES}


def coverage() -> dict:
    """The honest summary. `remaining` counts only what this build can actually finish."""
    c = counts()
    return {
        "total": TOTAL,
        "by_status": c,
        "executable_remaining": c[PARTIAL] + c[MISSING],
        "blocked_on_owner": c[OWNER_GATED],
        "blocked_on_data": c[DATA_GATED],
        "complete": c[COVERED],
        "percent_complete": round(100.0 * c[COVERED] / TOTAL, 1),
    }


def sections() -> list[dict]:
    """Per-version rollup, so progress is visible where the work actually clusters."""
    out: dict[str, dict] = {}
    for r in load():
        entry = out.setdefault(r.version, {"version": r.version, "section": r.section,
                                           "total": 0, **{s: 0 for s in STATUSES}})
        entry["total"] += 1
        entry[r.status] += 1
    return sorted(out.values(), key=lambda e: e["version"])
