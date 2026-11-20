"""Live self-tuning inside guardrails: champion/challenger over an allowlist of tunable keys.

**What may be tuned is a closed, hard-coded allowlist (`TUNABLES`).** Each entry names its
department, its kind (a number within bounds, or one of a fixed set of choices: prompt
templates, price-test arms), its default and the code that reads it. Anything not on the list
is refused. Every key -- and every proposed value -- also goes through `improve.invariants`,
so a certified gate, a safety rule, a spend ceiling, an evidence floor or an owner exception
can never be tuned even if somebody adds its name here: `_assert_allowlist_safe` runs at
import and the module refuses to load. A list the loop could edit is a list the loop would
eventually edit, so there is no write path to it.

**A change runs as a challenger, capped twice.** A challenger receives at most `share` of the
units of work (<= `MAX_SHARE`), assigned by a stable hash of (trial, unit) so a unit always
lands in the same arm, and it stops receiving work the moment its arm's recorded cost reaches
its spend cap (<= `MAX_SPEND_CAP_CAD`). The tuner itself spends nothing; costs are what the
reader recorded for the work it did anyway.

**Promotion needs a statistically meaningful KPI gain** (`stats.compare`, judged only at the
fixed looks of `stats.LOOKS` so repeated runs do not inflate false promotions: both arms >=
`MIN_ARM_N`, z >= `stats.PROMOTE_Z` one-sided per look and an absolute gain >= 3 points). A challenger that is
significantly worse stops at once (REJECTED); one that never separates is retired at
`MAX_TRIAL_N` (EXPIRED). Noise is not promoted.

**Automatic rollback.** A promoted value is WATCHED against a holdback of the value it
replaced (`HOLDBACK_SHARE` of units). If the promoted value is significantly worse than the
holdback it is rolled back on the spot -- the previous value is restored as champion -- and
the rollback is audited with its evidence. A watch that completes without regression SETTLES.

Every state change is appended to the trial's `history` and written to `audit_log` with the
comparison it was decided on.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Integer

from . import invariants, stats

ACTION = "improve.self_tune"

RUNNING, WATCHING, SETTLED = "RUNNING", "WATCHING", "SETTLED"
REJECTED, EXPIRED, ROLLED_BACK, CAPPED = "REJECTED", "EXPIRED", "ROLLED_BACK", "CAPPED"
ACTIVE_STATES = (RUNNING, WATCHING)

MAX_SHARE = 0.2              # a challenger never gets more than a fifth of the work
MAX_SPEND_CAP_CAD = 5.0      # nor more than this much recorded cost on its arm
HOLDBACK_SHARE = 0.2         # units kept on the replaced value while a promotion is watched
MAX_TRIAL_N = 2000           # per arm: a challenger that never separates is retired
WATCH_N = 200                # per arm: the watch that settles a promotion


@dataclass(frozen=True)
class Tunable:
    key: str
    department: str
    kind: str                      # "number" | "choice"
    default: object
    lo: float | None = None
    hi: float | None = None
    integer: bool = False
    choices: tuple = ()
    kpi: str = "yield"
    reader: str = ""               # module:function that reads it via tuning.value()
    what: str = ""

    def declaration(self) -> dict:
        return {"param": self.key, "lo": self.lo, "hi": self.hi, "integer": self.integer}


# The allowlist. Names avoid the protected vocabulary on purpose -- and if one did not, the
# import-time check below would refuse to load the module rather than let it be tuned.
TUNABLES: tuple[Tunable, ...] = (
    Tunable("research.focus_weight.amigurumi", "research", "number", 1.0, 0.5, 2.0,
            what="relative research focus on amigurumi demand (D-OWNER research weighting)"),
    Tunable("research.focus_weight.home_decor", "research", "number", 1.0, 0.5, 2.0,
            what="relative research focus on pillows/cushions"),
    Tunable("research.watchlist_period_factor", "research", "number", 1.0, 0.5, 2.0,
            what="schedule: multiplier on the watchlist scan cadence"),
    Tunable("concept.lesson_nudge_step", "concept_creative", "number", 0.02, 0.01, 0.03,
            what="weight of one matched lesson in concept ranking (consume.STEP); the "
                 "caps on total lesson influence are not tunable"),
    Tunable("engineering.lesson_match_words", "engineering", "number", 2, 1, 4, integer=True,
            what="shared content words for an engineering lesson to match a draft"),
    Tunable("qa.recheck_period_factor", "qa", "number", 1.0, 0.5, 2.0,
            what="schedule: multiplier on re-verification of certified releases"),
    Tunable("visual.prompt_template", "visual", "choice", "scene_v1",
            choices=("scene_v1", "scene_v2_light", "scene_v3_context"),
            what="lifestyle prompt template; identity lock and disclosures are unaffected"),
    Tunable("listing.title_template", "seo_listing", "choice", "object_first",
            choices=("object_first", "use_first", "style_first"),
            what="title word order; required disclosures are appended regardless"),
    Tunable("pricing.test_arm", "pricing", "choice", "ends_00",
            choices=("ends_00", "ends_50", "ends_99"),
            what="price-ending arm inside the certified price band; never outside it"),
    Tunable("marketing.content_lesson_words", "marketing", "number", 1, 1, 3, integer=True,
            what="shared words for a lesson to shape a content piece"),
    Tunable("finance.cost_flag_rank_weight", "finance", "number", 1.0, 0.5, 2.0,
            what="ranking weight of cost-review flags in the work queue (flags only)"),
    Tunable("ops.queue_check_period_factor", "ops", "number", 1.0, 0.5, 2.0,
            what="schedule: multiplier on the queue-health check cadence"),
    Tunable("support.lesson_rank_weight", "support", "number", 1.0, 0.5, 2.0,
            what="ranking weight of matched lessons attached to a support case"),
)
BY_KEY: dict[str, Tunable] = {t.key: t for t in TUNABLES}


class NotTunable(ValueError):
    """A key or value the allowlist and the invariants refuse."""


def check(key: str, value) -> invariants.Verdict:
    """May `key` be set to `value`? Allowlist first, then the protected invariants."""
    t = BY_KEY.get(key)
    hit = invariants.protected_invariant(key)
    if hit is not None:
        return invariants.Verdict(False, key, hit.key,
                                  f"{key!r} lands on the protected invariant {hit.key!r}: "
                                  f"never tunable ({hit.protects})")
    if t is None:
        return invariants.Verdict(False, key, "undeclared_surface",
                                  f"{key!r} is not on the tunable allowlist; an undeclared "
                                  f"key is protected, never free")
    if t.kind == "choice":
        if isinstance(value, str) and value in t.choices:
            return invariants.Verdict(True, key)
        return invariants.Verdict(False, key, "malformed_value",
                                  f"{value!r} is not one of {list(t.choices)}")
    return invariants.check(key, value, tunable=t.declaration())


def assert_tunable(key: str, value) -> None:
    v = check(key, value)
    if not v.ok:
        raise NotTunable(v.reason)


def _assert_allowlist_safe() -> None:
    problems = []
    for t in TUNABLES:
        if not check(t.key, t.default).ok:
            problems.append(f"{t.key}: {check(t.key, t.default).reason}")
        if t.kind == "number" and (t.lo is None or t.hi is None or not t.lo <= t.default <= t.hi):
            problems.append(f"{t.key}: default outside its bounds")
        if t.kind == "choice" and t.default not in t.choices:
            problems.append(f"{t.key}: default not among its choices")
    if len(BY_KEY) != len(TUNABLES):
        problems.append("duplicate tunable keys")
    if problems:  # pragma: no cover - a defect in the allowlist is a build defect
        raise RuntimeError("tunable allowlist unsafe: " + "; ".join(problems))


_assert_allowlist_safe()


# ---- reading the live value -------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def _bucket(trial_id: int, unit: str) -> float:
    h = hashlib.sha256(f"{trial_id}:{unit}".encode()).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


def champion(db, key: str):
    """The champion value of a key: the stored one if it still passes the guard, else default."""
    from .self_models import PolicyValue

    t = BY_KEY.get(key)
    if t is None:
        raise NotTunable(f"{key!r} is not on the tunable allowlist")
    with db.session() as s:
        row = s.get(PolicyValue, key)
        stored = (row.value or {}).get("v") if row is not None else None
    if row is not None and check(key, stored).ok:
        return stored
    return t.default


def _arm_cost(s, trial_id: int, arm: str) -> float:
    from sqlalchemy import func, select

    from .self_models import Observation

    return float(s.scalar(select(func.coalesce(func.sum(Observation.cost_cad), 0.0)).where(
        Observation.challenger_id == trial_id, Observation.arm == arm,
        Observation.phase == "trial")) or 0.0)


def _capped(spent: float, cap: float) -> bool:
    """A cap of 0 means the challenger may incur no recorded cost at all."""
    return spent > 0 if cap <= 0 else spent >= cap


def assign(db, key: str, unit: str) -> dict:
    """The value a reader uses for one unit of work, and the arm it belongs to.

    {"value", "arm", "trial", "phase"}; trial None means no trial is running for the key.
    """
    from sqlalchemy import select

    from .self_models import Challenger

    champ = champion(db, key)
    with db.session() as s:
        row = s.scalar(select(Challenger).where(Challenger.key == key,
                                                Challenger.state.in_(ACTIVE_STATES))
                       .order_by(Challenger.id.desc()).limit(1))
        if row is None:
            return {"value": champ, "arm": "champion", "trial": None, "phase": None}
        b = _bucket(row.id, unit)
        if row.state == RUNNING:
            capped = _capped(_arm_cost(s, row.id, "challenger"), row.spend_cap_cad)
            if b < row.share and not capped:
                return {"value": row.challenger_value.get("v"), "arm": "challenger",
                        "trial": row.id, "phase": "trial"}
            return {"value": row.champion_value.get("v"), "arm": "champion",
                    "trial": row.id, "phase": "trial"}
        # WATCHING: the promoted value is champion; a holdback keeps the replaced one.
        if b < HOLDBACK_SHARE:
            return {"value": row.champion_value.get("v"), "arm": "champion",
                    "trial": row.id, "phase": "watch"}
        return {"value": row.challenger_value.get("v"), "arm": "challenger",
                "trial": row.id, "phase": "watch"}


def value(db, key: str, unit: str | None = None):
    """The value to use. Without a unit, the champion (no unit can be assigned an arm)."""
    if unit is None:
        return champion(db, key)
    return assign(db, key, unit)["value"]


# ---- the trial --------------------------------------------------------------------------

def _audit(db, detail: dict, artifact: str) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="improve.self_tune", action=ACTION, artifact=artifact[:200],
                       detail=detail))


def _log(row, event: str, **evidence) -> dict:
    entry = {"at": _now().isoformat(), "event": event, **evidence}
    row.history = list(row.history or []) + [entry]
    return entry


def start(db, key: str, challenger_value, *, share: float = 0.1, spend_cap_cad: float = 0.0,
          proposed_by: str, lesson_ref: str = "") -> int:
    """Open a challenger for `key`. Refused (NotTunable / ValueError) unless every guard holds."""
    from sqlalchemy import select

    from .self_models import Challenger

    assert_tunable(key, challenger_value)
    if not (isinstance(share, (int, float)) and math.isfinite(share) and 0 < share <= MAX_SHARE):
        raise ValueError(f"share {share!r} must be in (0, {MAX_SHARE}]")
    if not (isinstance(spend_cap_cad, (int, float)) and math.isfinite(spend_cap_cad)
            and 0 <= spend_cap_cad <= MAX_SPEND_CAP_CAD):
        raise ValueError(f"spend cap {spend_cap_cad!r} must be in [0, {MAX_SPEND_CAP_CAD}]")
    champ = champion(db, key)
    if challenger_value == champ:
        raise ValueError("a challenger equal to the champion is a no-op, not a trial")
    t = BY_KEY[key]
    with db.session() as s:
        if s.scalar(select(Challenger.id).where(Challenger.key == key,
                                                Challenger.state.in_(ACTIVE_STATES))):
            raise ValueError(f"{key} already has an active trial")
        row = Challenger(department=t.department, key=key, champion_value={"v": champ},
                         challenger_value={"v": challenger_value}, share=float(share),
                         spend_cap_cad=float(spend_cap_cad), state=RUNNING,
                         proposed_by=proposed_by, lesson_ref=lesson_ref, history=[])
        s.add(row)
        s.flush()
        entry = _log(row, "started", champion=champ, challenger=challenger_value,
                     share=share, spend_cap_cad=spend_cap_cad, lesson_ref=lesson_ref)
        tid = row.id
    _audit(db, {"trial": tid, "key": key, **entry}, f"si_challenger:{tid}")
    return tid


def record(db, trial_id: int, arm: str, unit: str, success: bool, *, phase: str = "trial",
           cost_cad: float = 0.0, ref: str = "") -> bool:
    """Record one judged unit. False when the unit was already recorded (never counted twice)."""
    from sqlalchemy import select

    from .self_models import Observation

    if arm not in ("champion", "challenger") or phase not in ("trial", "watch"):
        raise ValueError("arm/phase")
    with db.session() as s:
        if s.scalar(select(Observation.id).where(Observation.challenger_id == trial_id,
                                                 Observation.phase == phase,
                                                 Observation.unit == unit)):
            return False
        s.add(Observation(challenger_id=trial_id, phase=phase, arm=arm, unit=str(unit)[:120],
                          success=bool(success), cost_cad=max(0.0, float(cost_cad or 0.0)),
                          ref=ref[:200]))
    return True


def counts(db, trial_id: int, phase: str, *, first: int | None = None) -> dict:
    """(successes, trials) per arm; with `first`, over each arm's first `first` units only."""
    from sqlalchemy import func, select

    from .self_models import Observation

    out = {"champion": (0, 0), "challenger": (0, 0)}
    with db.session() as s:
        if first is None:
            for arm, n, x in s.execute(
                    select(Observation.arm, func.count(Observation.id),
                           func.sum(func.cast(Observation.success, Integer)))
                    .where(Observation.challenger_id == trial_id, Observation.phase == phase)
                    .group_by(Observation.arm)):
                out[arm] = (int(x or 0), int(n or 0))
            return out
        for arm in out:
            flags = list(s.scalars(select(Observation.success).where(
                Observation.challenger_id == trial_id, Observation.phase == phase,
                Observation.arm == arm).order_by(Observation.id).limit(first)))
            out[arm] = (sum(1 for f in flags if f), len(flags))
    return out


def _trial_comparison(db, trial_id: int) -> dict:
    """Promotion is judged at the newest fixed look; harm on everything recorded."""
    full = counts(db, trial_id, "trial")
    look = stats.checkpoint(min(full["challenger"][1], full["champion"][1]))
    if look is None:
        return {**stats.compare(full["challenger"], full["champion"]), "look": None}
    at_look = counts(db, trial_id, "trial", first=look)
    cmp = stats.compare(at_look["challenger"], at_look["champion"])
    if cmp["verdict"] != "BETTER":
        whole = stats.compare(full["challenger"], full["champion"])
        if whole["verdict"] == "WORSE":
            cmp = whole
    return {**cmp, "look": look, "recorded": {k: list(v) for k, v in full.items()}}


def _set_champion(s, key: str, new, *, source: str) -> None:
    from .self_models import PolicyValue

    row = s.get(PolicyValue, key)
    if row is None:
        s.add(PolicyValue(key=key, value={"v": new}, previous={"v": BY_KEY[key].default},
                          version=1, set_at=_now(), source=source))
    else:
        row.previous = dict(row.value or {})
        row.value = {"v": new}
        row.version = (row.version or 1) + 1
        row.set_at = _now()
        row.source = source


def judge(db, trial_id: int) -> dict:
    """Decide one trial on its recorded units. Idempotent: an undecidable trial stays as is."""
    from .self_models import Challenger

    with db.session() as s:
        row = s.get(Challenger, trial_id)
        if row is None or row.state not in ACTIVE_STATES:
            return {"trial": trial_id, "decision": "none",
                    "state": None if row is None else row.state}
        key, state = row.key, row.state
    if state == RUNNING:
        c = counts(db, trial_id, "trial")
        cmp = _trial_comparison(db, trial_id)
        with db.session() as s:
            row = s.get(Challenger, trial_id)
            spent = _arm_cost(s, trial_id, "challenger")
            decision, entry = "wait", None
            if cmp["verdict"] == "BETTER":
                assert_tunable(key, row.challenger_value.get("v"))  # re-checked at execution
                _set_champion(s, key, row.challenger_value.get("v"),
                              source=f"si_challenger:{trial_id}")
                row.state, row.promoted_at, row.decided_at = WATCHING, _now(), _now()
                decision = "promoted"
            elif cmp["verdict"] == "WORSE":
                row.state, row.decided_at, decision = REJECTED, _now(), "rejected"
            elif min(c["challenger"][1], c["champion"][1]) >= MAX_TRIAL_N:
                row.state, row.decided_at, decision = EXPIRED, _now(), "expired"
            elif _capped(spent, row.spend_cap_cad):
                row.state, row.decided_at, decision = CAPPED, _now(), "spend_capped"
            if decision != "wait":
                entry = _log(row, decision, comparison=cmp, spent_cad=round(spent, 4))
        if entry:
            _audit(db, {"trial": trial_id, "key": key, **entry}, f"si_challenger:{trial_id}")
        return {"trial": trial_id, "key": key, "decision": decision, "comparison": cmp}
    # WATCHING: promoted value (arm "challenger") against the holdback (arm "champion").
    c = counts(db, trial_id, "watch")
    cmp = stats.compare(c["challenger"], c["champion"])
    regressed = (cmp["verdict"] != "UNKNOWN" and cmp.get("z") is not None
                 and cmp["z"] <= -stats.REGRESSION_Z)
    with db.session() as s:
        row = s.get(Challenger, trial_id)
        decision, entry = "wait", None
        if regressed:
            _set_champion(s, key, row.champion_value.get("v"),
                          source=f"rollback:si_challenger:{trial_id}")
            row.state, row.rolled_back_at = ROLLED_BACK, _now()
            decision = "rolled_back"
        elif min(c["challenger"][1], c["champion"][1]) >= WATCH_N:
            row.state, decision = SETTLED, "settled"
        if decision != "wait":
            entry = _log(row, decision, comparison=cmp)
    if entry:
        _audit(db, {"trial": trial_id, "key": key, **entry}, f"si_challenger:{trial_id}")
    return {"trial": trial_id, "key": key, "decision": decision, "comparison": cmp}


def judge_all(db) -> list[dict]:
    from sqlalchemy import select

    from .self_models import Challenger

    with db.session() as s:
        ids = list(s.scalars(select(Challenger.id).where(Challenger.state.in_(ACTIVE_STATES))
                             .order_by(Challenger.id)))
    return [judge(db, i) for i in ids]


def trials(db, *, department: str | None = None) -> list[dict]:
    from sqlalchemy import select

    from .self_models import Challenger

    with db.session() as s:
        q = select(Challenger).order_by(Challenger.id.desc()).limit(200)
        if department:
            q = q.where(Challenger.department == department)
        rows = list(s.scalars(q))
        return [{"id": r.id, "department": r.department, "key": r.key, "state": r.state,
                 "champion": (r.champion_value or {}).get("v"),
                 "challenger": (r.challenger_value or {}).get("v"), "share": r.share,
                 "spend_cap_cad": r.spend_cap_cad, "proposed_by": r.proposed_by,
                 "lesson_ref": r.lesson_ref,
                 "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
                 "rolled_back_at": r.rolled_back_at.isoformat() if r.rolled_back_at else None,
                 "last_event": (r.history or [{}])[-1].get("event")} for r in rows]


def describe() -> list[dict]:
    return [{"key": t.key, "department": t.department, "kind": t.kind, "default": t.default,
             "bounds": [t.lo, t.hi] if t.kind == "number" else None,
             "choices": list(t.choices) or None, "reader": t.reader or None,
             "reader_wired": bool(t.reader), "what": t.what} for t in TUNABLES]


__all__ = ["TUNABLES", "BY_KEY", "check", "assert_tunable", "assign", "value", "start",
           "record", "judge", "judge_all", "trials", "describe", "NotTunable"]
