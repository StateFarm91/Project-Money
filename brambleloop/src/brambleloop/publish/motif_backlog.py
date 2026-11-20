"""OWNER P0 (ENG-MOTIF-BACKLOG): recover paid renders whose motif check was refused, not failed.

`motif_fidelity.check` called `provider.see` with no company-budget reservation. The paid-provider
gate refused every such call (`no_budget_reservation`, `gateway.paid_provider_gate.authorize`)
and `check` folded the refusal into `unmeasurable`, so `motif_verified` was False on every owned
(`owned_photography.make`) and model (`model_photography.make`) render. Those renders were paid for.
A refusal is not a verdict about the fabric: the picture was never looked at.

The owner's instruction (verbatim): "Recover the backlog of existing paid images before
generating replacements. Do not throw away assets merely because verification was temporarily
refused."

**What this does, and what it never does.** The re-ask itself is ENG-MOTIF's
(`eng/motif-reservation`, merged): `motif_fidelity.rejudge` re-runs `check` on the kept bytes
through its own reservation (`quality_director` / `asset_inspection`, billed at cost), and
`owned_photography.rejudge_motif` / `model_photography.rejudge_frame` turn the answer into the
superseding record every reader already understands. This module is the backlog around it:

* `scan` finds every filed render (an `assets.owned_photography` row, or a frame inside an
  `assets.model_photography` sequence) whose motif is `unmeasurable` because the call was
  refused for budget or reservation (`refusal_code`): the legacy refusal text, or the coded
  `budget_refused`. A genuine `unmeasurable` or a `mismatch` is never picked up. One
  `motif_recovery` row per distinct image, so a frame a later sequence reused is one render.
* `recheck_one` re-asks only the motif question -- nothing is rendered -- and only when a
  match would make the render usable (`motif_fidelity.worth_rejudging`); otherwise the row is
  PARKED at no cost and re-evaluated every sweep. A match is PASSED and filed; a mismatch or a
  genuine unmeasurable is FAILED, the only state queued for regeneration (the existing
  photography job for its path); a budget/activation refusal is QUEUED_BUDGET and retried next
  sweep -- never lost, never regenerated; plumbing is retried MAX_RECHECKS times.
* **Spend bounds (ENG-MOTIF-BACKLOG-FIX).** One bound on paid re-asks per sweep, `limit`
  (SWEEP_LIMIT), across every row state -- a PARKED row that becomes worth asking draws on
  it too -- and a durable daily cap (DAILY_CAP, lowered only by DAILY_CAP_ENV), counted from
  the `assets.motif_backlog.claimed` rows. Each paid re-ask is claimed BEFORE the call, in one
  transaction that advances `rechecks` by compare-and-set and writes the claim row, so a crash
  mid-call still counts toward MAX_RECHECKS and the cap. Before paying, an answer already on
  file for the same image (the photography job's own re-ask, or this sweep's before a crash)
  is reused. A render ineligible on its merits (`eligible`: the photography jobs' own rule) is
  INELIGIBLE and never asked; PASSED means a real MATCH that left the render usable.
* `sweep` (the `assets.motif_backlog` job) also hands a completed gallery to the release
  chain (`gallery_handoff`), and stamps galleries and listing packages that completed.
* `report` is the owner's read-only count, from the `motif_recovery` rows.

**No gate is weakened.** A filed re-ask changes only what the motif measurement feeds.
Every usability reader still requires `visual.product_authority.structural_floor` == PASS,
which a generated frame does not reach (F-852, D-FB-7); the listing-set certificate, the
F-852 policy classification, the A3 photo authority and `SAMPLE_PHOTO_REQUIRED` are
untouched. A recovered frame completes a gallery only where the existing readers accept it,
and the report says how many did.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

JOB_TYPE = "assets.motif_backlog"
AGENT = "publishing"                 # the agent that runs the photography jobs it recovers
AUDIT_SWEPT = "assets.motif_backlog.swept"
AUDIT_RECHECKED = "assets.motif_backlog.rechecked"
# One row per claimed paid re-ask, written in the same transaction that claims the recovery
# row (`_claim`), so the daily cap is a durable count that survives a crash mid-call.
AUDIT_CLAIMED = "assets.motif_backlog.claimed"
REGEN_KEY = "motif-backlog-regen:"
SWEEP_LIMIT = 50                     # paid re-asks per sweep, across every row state
DAILY_CAP = 40                       # paid re-asks per UTC day, across every sweep
DAILY_CAP_ENV = "BRAMBLELOOP_MOTIF_BACKLOG_DAILY_CAP"   # may lower DAILY_CAP, never raise it
SCAN_LIMIT = 2000                    # filed rows read per action per scan

OWNED = "assets.owned_photography"
MODEL = "assets.model_photography"
SOURCES = (OWNED, MODEL)

# States. BLOCKED: found, never re-checked. QUEUED_BUDGET: a re-check was refused for budget
# and waits for the next sweep. PASSED / FAILED: a measurement was made. BYTES_MISSING: the
# paid bytes cannot be read back, so nothing can be measured (reported, never regenerated
# here). SUPERSEDED: the product's certified release moved on, so its current chart is not the
# chart this render was made against (reported; the release's own cadence covers it).
# QUEUED_RETRY: the re-check produced no verdict for a reason that is neither budget nor the
# picture (no provider, an unreadable answer, a chart that would not draw); retried up to
# MAX_RECHECKS, then UNRESOLVED (reported, never regenerated -- nobody judged the fabric).
BLOCKED, QUEUED_BUDGET, PASSED, FAILED = "BLOCKED", "QUEUED_BUDGET", "PASSED", "FAILED"
BYTES_MISSING, SUPERSEDED = "BYTES_MISSING", "SUPERSEDED"
QUEUED_RETRY, UNRESOLVED, PARKED = "QUEUED_RETRY", "UNRESOLVED", "PARKED"
# INELIGIBLE: the render fails on its merits whatever the motif says -- an owned render whose
# asset-truth verdict is not `clear` (`owned_photography.motif_eligible`), a model frame with
# another floor open or failed (`model_photography.motif_eligible_frame`) -- or a match was
# filed and the existing readers still do not accept it as usable. Never re-asked, never
# counted as passed, never regenerated here (its own job's cadence owns it).
INELIGIBLE = "INELIGIBLE"
STATES = (BLOCKED, QUEUED_BUDGET, QUEUED_RETRY, PARKED, PASSED, FAILED, BYTES_MISSING,
          SUPERSEDED, UNRESOLVED, INELIGIBLE)
# PARKED: a match would not make the render usable (no structural PASS for a generated frame,
# F-852), so no vision call is bought. Re-evaluated on every sweep at no cost.
OPEN_STATES = (BLOCKED, QUEUED_BUDGET, QUEUED_RETRY, PARKED)
MAX_RECHECKS = 3

# The gate's refusal codes that mean "the accounting said no", not "the picture was judged".
# Read from `paid_provider_gate.authorize` and `anthropic.check_budget*`. `not_activated_by_owner`
# and friends are NOT here: a provider the owner never activated is an owner decision, and a
# re-check would only be refused again.
BUDGET_CODES = frozenset({
    "no_budget_reservation", "reservation_underfunded", "reservation_already_used",
    "company_monthly_budget", "provider_daily_ceiling", "provider_monthly_ceiling",
    "per_gallery_limit", "run_call_ceiling",
})
# `motif_fidelity.check` writes "the comparison call failed: <exc>"; the gate's exception text
# is "[<code>] <message>" (`PaidCallRefused`), carried through `VisionGateRefused`.
_FAILED_CALL = "the comparison call failed:"
_CODE = re.compile(r"\[([a-z_]+)\]")
_BUDGET_EXC = ("BudgetExceeded", "AgentCeilingExceeded")


class MotifRecovery(Base):
    __tablename__ = "motif_recovery"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    render_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    source_action: Mapped[str] = mapped_column(String(80), index=True)
    audit_id: Mapped[int] = mapped_column(Integer, index=True)
    shot: Mapped[str] = mapped_column(String(40), default="")
    slug: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    refusal_code: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(16), index=True, default=BLOCKED)
    rechecks: Mapped[int] = mapped_column(Integer, default=0)
    budget_deferrals: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(16), default="")
    motif: Mapped[dict] = mapped_column(JSON, default=dict)
    why: Mapped[str] = mapped_column(String(400), default="")
    recovered_audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regen_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gallery_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                   nullable=True)
    package_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_motif_recovery"


def ensure_tables(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[MotifRecovery.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


# ---- what counts as a refusal ---------------------------------------------------------------

def refusal_code(motif: dict | None) -> str | None:
    """The budget/reservation refusal behind an `unmeasurable` motif verdict, or None.

    None for every verdict that was actually made: `match`, `mismatch`, and the genuine
    `unmeasurable` (fabric unreadable, the judge could not tell, an unreadable answer, a chart
    that would not draw). Only a refused *call* is recoverable without a new render."""
    from . import motif_fidelity as MF

    if not isinstance(motif, dict) or motif.get("verdict") != MF.UNMEASURABLE:
        return None
    if "unmeasured" in motif:
        # A reading filed since ENG-MOTIF codes its reason: only a budget refusal is this
        # backlog's (the owner's "missing reservation or budget refusal").
        return (str(motif.get("unmeasured")) if motif.get("unmeasured") == MF.UNMEASURED_BUDGET
                else None)
    why = str(motif.get("why") or "")
    if not why.startswith(_FAILED_CALL):
        return None
    for code in _CODE.findall(why):
        if code in BUDGET_CODES:
            return code
    for name in _BUDGET_EXC:
        if name in why:
            return name
    return None


def _sha(frame: dict) -> str:
    image = frame.get("image") or {}
    sha = image.get("sha256") if isinstance(image, dict) else None
    return sha if isinstance(sha, str) and len(sha) == 64 else ""


def render_key(source: str, slug: str, version: str, sha: str) -> str:
    return f"{source}:{slug}@{version}:{sha}"[:200]


def _frames_of(source: str, detail: dict):
    """(shot, frame, slug, version) for every render a filed row carries."""
    if not detail.get("made"):
        return
    slug, version = str(detail.get("slug") or ""), str(detail.get("version") or "")
    if source == MODEL and detail.get("frames"):
        for frame in detail.get("frames") or ():
            if isinstance(frame, dict) and frame.get("made"):
                yield (str(frame.get("shot") or ""), frame,
                       str(frame.get("slug") or slug), str(frame.get("version") or version))
        return
    yield str(detail.get("shot") or detail.get("role") or ""), detail, slug, version


# ---- scan -----------------------------------------------------------------------------------

def scan(db, *, now: datetime | None = None) -> dict:
    """Find every refused motif check on file. Idempotent: one row per distinct image."""
    from sqlalchemy import desc

    from ..core.models import AuditLog

    ensure_tables(db)
    now = _now(now)
    found, new, rows_read = 0, 0, 0
    with db.session() as s:
        known = set(s.scalars(select(MotifRecovery.render_key)))
        for source in SOURCES:
            for row in s.scalars(select(AuditLog).where(AuditLog.action == source)
                                 .order_by(desc(AuditLog.id)).limit(SCAN_LIMIT)):
                rows_read += 1
                for shot, frame, slug, version in _frames_of(source, row.detail or {}):
                    code = refusal_code(frame.get("motif"))
                    sha = _sha(frame)
                    if code is None or not slug or not sha:
                        continue
                    found += 1
                    key = render_key(source, slug, version, sha)
                    if key in known:
                        continue
                    known.add(key)
                    new += 1
                    s.add(MotifRecovery(render_key=key, source_action=source, audit_id=row.id,
                                        shot=shot[:40], slug=slug[:120], version=version[:40],
                                        image_sha256=sha, refusal_code=code[:40],
                                        state=BLOCKED, found_at=now))
    return {"rows_read": rows_read, "refused_frames_seen": found, "new": new}


# ---- re-check (through ENG-MOTIF's reserved re-ask; nothing is rendered) --------------------
#
# The re-ask itself is ENG-MOTIF's (`eng/motif-reservation`, merged here): `motif_fidelity.rejudge`
# reads the kept bytes back by digest and runs `check`, whose `_call_judge` reserves through
# `check_budget` as `quality_director` / `asset_inspection` and bills at cost; the answer is filed
# as a new row for the same image by `owned_photography.rejudge_motif` /
# `model_photography.rejudge_frame`, which every reader already takes as superseding the refused
# one. This module adds the backlog around it: finding every refused render, the per-render
# state, the budget queue, routing a genuine failure to regeneration, the gallery handoff and
# the report. It does not reserve or call a provider of its own.

def _release_of(db, slug: str, version: str):
    """The certified CIR and twin for exactly slug@version, or (None, None, why).

    Read from the certified `PatternVersion` row, not rebuilt from the catalogue: the chart
    the render is compared against must be the one that release certified."""
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.twin import build_twin
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        cir_json = dict(pv.cir_json) if pv is not None and pv.certified and pv.cir_json else None
    if cir_json is None:
        return None, None, f"no certified release of {slug}@{version} to compare against"
    cir = CIR.from_dict(cir_json)
    result = compile_cir(cir)
    if not result.ok:
        return None, None, f"{slug}@{version} does not compile"
    return cir, build_twin(cir, result), ""


def _filed(db, rec) -> tuple[dict | None, dict | None]:
    """(the filed row's detail, the frame inside it this recovery row is about)."""
    from ..core.models import AuditLog

    with db.session() as s:
        row = s.get(AuditLog, rec["audit_id"])
        detail = dict(row.detail or {}) if row is not None else None
    if detail is None:
        return None, None
    for _shot, frame, _slug, _version in _frames_of(rec["source_action"], detail):
        if _sha(frame) == rec["image_sha256"]:
            return detail, frame
    return detail, None


# `motif_fidelity` unmeasured codes -> this backlog's state. Budget and activation are spend
# decisions (queued, never lost); plumbing is retried a bounded number of times; a render whose
# bytes are gone cannot be asked about.
_CODE_STATE = {
    "budget_refused": QUEUED_BUDGET, "no_accounting_store": QUEUED_BUDGET,
    "gate_refused": QUEUED_BUDGET, "call_failed_transient": QUEUED_RETRY,
    "call_failed": QUEUED_RETRY, "answer_unreadable": QUEUED_RETRY,
    "chart_unrenderable": QUEUED_RETRY, "image_missing": BYTES_MISSING,
}


def _file_answer(db, rec, detail: dict, answered: dict) -> int:
    """File the re-ask's answer the way the photography jobs file it; returns the row id."""
    from ..core.models import AuditLog
    from . import model_photography as MP

    if rec["source_action"] == OWNED:
        record = answered["record"]
    else:
        # Every frame of the sequence carries the newest answer on file for its image: this
        # one's, and any sibling frame of the same sequence answered by an earlier sweep.
        known = _answered_frames(db, rec["slug"], rec["version"])
        frames = []
        for frame in detail.get("frames") or [detail]:
            sha = _sha(frame) if isinstance(frame, dict) else ""
            if sha == rec["image_sha256"]:
                frames.append(dict(answered["frame"], reused=False, rejudged=True))
            elif sha in known:
                frames.append(dict(known[sha], reused=False, rejudged=True))
            else:
                frames.append(dict(frame, reused=True, rejudged=False))
        floors = MP._combine_floors(frames)
        usable = all(v == "pass" for v in floors.values())
        record = dict(detail, frames=frames, floors=floors, usable_as_listing_asset=usable,
                      spent_cad=0.0, reused_frames=[f.get("shot") for f in frames
                                                    if f.get("reused")],
                      rejudged_frames=[f.get("shot") for f in frames if f.get("rejudged")],
                      motif_rejudge_only=True,
                      why=("every floor cleared across the sequence" if usable else
                           "; ".join(f"{k}: {v}" for k, v in sorted(floors.items())
                                     if v != "pass")))
    record = dict(record, motif_recovered_by=JOB_TYPE)
    with db.session() as s:
        row = AuditLog(actor=AGENT, action=rec["source_action"],
                       artifact=f"{rec['slug']}@{rec['version']}"[:200], detail=record)
        s.add(row)
        s.flush()
        return row.id


def _answered_frames(db, slug: str, version: str) -> dict:
    """{image sha256: the newest re-asked frame on file} for this release's model frames."""
    from . import model_photography as MP

    out: dict = {}
    for record in MP.sequences(db, slug=slug):
        if record.get("version") != version:
            continue
        for frame in record.get("frames") or ():
            sha = _sha(frame) if isinstance(frame, dict) else ""
            if sha and sha not in out and frame.get("motif_rejudge"):
                out[sha] = frame
    return out


def daily_cap() -> int:
    """DAILY_CAP, or a lower value from the environment. Never higher: an unreadable, negative
    or larger value leaves DAILY_CAP in force."""
    raw = os.environ.get(DAILY_CAP_ENV, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DAILY_CAP
    return value if 0 <= value < DAILY_CAP else DAILY_CAP


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def claimed_today(db, *, now: datetime | None = None) -> int:
    """Paid re-asks claimed since 00:00 UTC, from the durable claim rows."""
    from ..core.models import AuditLog

    now = _now(now)
    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == AUDIT_CLAIMED, AuditLog.at >= _day_start(now))) or 0)


def _claim(db, rec_id: int, rec: dict, now: datetime) -> str:
    """Claim one paid re-ask BEFORE it is made: in one transaction, the daily cap is read from
    the durable claim rows, `rechecks` is advanced by compare-and-set on the value this call
    read (so two sweeps cannot both claim the same attempt, and a replay after a crash claims
    a new attempt rather than re-using a spent one), and the claim row the cap counts is
    written. A crash during the call therefore still counts, toward MAX_RECHECKS and the cap.
    Returns "claimed", "daily_cap" or "lost"."""
    from ..core.models import AuditLog

    cap = daily_cap()
    with db.session() as s:
        used = int(s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == AUDIT_CLAIMED, AuditLog.at >= _day_start(now))) or 0)
        if used >= cap:
            return "daily_cap"
        moved = s.execute(update(MotifRecovery).where(
            MotifRecovery.id == rec_id, MotifRecovery.rechecks == rec["rechecks"],
            MotifRecovery.state.in_(OPEN_STATES)).values(
            rechecks=rec["rechecks"] + 1, checked_at=now)).rowcount
        if moved != 1:
            return "lost"
        s.add(AuditLog(actor=AGENT, action=AUDIT_CLAIMED, artifact=str(rec_id)[:200], at=now,
                       detail={"render_key": rec.get("render_key"),
                               "image_sha256": rec["image_sha256"],
                               "attempt": rec["rechecks"] + 1, "daily_cap": cap}))
    return "claimed"


def eligible(source: str, frame: dict) -> bool:
    """The render on its merits, by the photography jobs' own rule (structural floor aside):
    `owned_photography.motif_eligible` (asset truth `clear`) for an owned render,
    `model_photography.motif_eligible_frame` (every other floor) for a model frame."""
    from . import model_photography as MP
    from . import owned_photography as OP

    if source == OWNED:
        return OP.motif_eligible(frame, structural=False)
    return MP.motif_eligible_frame(frame, structural=False)


def _usable(answer: dict) -> bool:
    """Whether a filed answer made the render usable, by the existing readers' test."""
    from ..visual.product_authority import structural_floor

    try:
        return bool(answer.get("usable_as_listing_asset")) and \
            structural_floor(answer)["status"] == "PASS"
    except Exception:  # noqa: BLE001 - unreadable evidence is not usable
        return False


def _newer_answer(db, rec) -> tuple[int, dict, dict] | None:
    """The newest answered motif on file for this image, filed after the refused row:
    (row id, row detail, the frame carrying the answer), or None. Whoever filed it -- the
    photography job's own re-ask, or this sweep before a crash -- the image was looked at,
    so it is not paid for again."""
    from sqlalchemy import desc

    from ..core.models import AuditLog
    from . import motif_fidelity as MF

    with db.session() as s:
        rows = [(r.id, r.action, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action.in_(SOURCES),
                                   AuditLog.id > rec["audit_id"])
            .order_by(desc(AuditLog.id)).limit(SCAN_LIMIT))]
    for row_id, action, detail in rows:
        for _shot, frame, slug, version in _frames_of(action, detail):
            if (_sha(frame) != rec["image_sha256"] or slug != rec["slug"]
                    or version != rec["version"]):
                continue
            motif = frame.get("motif")
            if (isinstance(motif, dict) and motif.get("verdict")
                    and refusal_code(motif) is None and not MF.rejudgeable(motif)):
                return row_id, detail, frame
    return None


_NO_VERDICT = ("call_failed", "answer_unreadable", "chart_unrenderable")


def recheck_one(db, rec_id: int, *, provider=None, judger=None,
                now: datetime | None = None, regenerate=None,
                allowance: dict | None = None) -> dict:
    """Re-ask only the motif question about one recovery row's render. Never renders.

    At most one paid call, and only after it is claimed (`_claim`). `allowance` is the
    sweep's shared {"left": n}: with none left, nothing is paid and the row waits."""
    from ..core import workspace
    from . import model_photography as MP
    from . import motif_fidelity as MF
    from . import owned_photography as OP

    now = _now(now)
    with db.session() as s:
        row = s.get(MotifRecovery, rec_id)
        if row is None or row.state not in OPEN_STATES:
            return {"id": rec_id, "state": getattr(row, "state", None), "skipped": True}
        rec = {k: getattr(row, k) for k in ("source_action", "audit_id", "slug", "version",
                                             "image_sha256", "rechecks", "budget_deferrals",
                                             "render_key", "state")}

    def settle(state: str, **fields) -> dict:
        with db.session() as s:
            row = s.get(MotifRecovery, rec_id)
            row.state = state
            for k, v in fields.items():
                setattr(row, k, v)
            row.checked_at = now
        return {"id": rec_id, "state": state,
                **{k: v for k, v in fields.items() if k in ("verdict", "why")}}

    def settle_answer(answer: dict, filed_id: int, *, ours: bool) -> dict:
        """The state an answer on file puts this render in. PASSED only on a real MATCH that
        the existing readers accept as usable."""
        motif = dict(answer.get("motif") or {})
        motif.pop("chart", None)
        code = str(motif.get("unmeasured") or "")
        verdict = str(motif.get("verdict") or "")
        why = str(motif.get("why") or "")[:400]
        if code == "image_missing":
            return settle(BYTES_MISSING, motif=motif, why=why, recovered_audit_id=filed_id)
        if code in _NO_VERDICT:
            return settle(UNRESOLVED, motif=motif, why=why, recovered_audit_id=filed_id)
        if verdict == MF.MATCH:
            if _usable(answer):
                return settle(PASSED, verdict=verdict, motif=motif, why=why,
                              recovered_audit_id=filed_id)
            return settle(INELIGIBLE, verdict=verdict, motif=motif, recovered_audit_id=filed_id,
                          why=("the motif matched, but the existing readers do not accept "
                               "the render as usable: " + why)[:400])
        # A mismatch, or a genuine unmeasurable (the judge could not see the fabric): the
        # picture was looked at and it does not show the pattern. The only kind regenerated
        # -- here only when this sweep asked; an answer the photography job filed is its own
        # cadence's to act on, and queueing it again would buy a second render.
        out = settle(FAILED, verdict=verdict, motif=motif, why=why, recovered_audit_id=filed_id)
        if ours and regenerate is not None:
            job_id = regenerate(rec["source_action"], rec["slug"], rec_id)
            if job_id is not None:
                with db.session() as s:
                    s.get(MotifRecovery, rec_id).regen_job_id = int(job_id)
            out["regen_job_id"] = job_id
        return out

    detail, frame = _filed(db, rec)
    if frame is None:
        return settle(SUPERSEDED, why="the filed render this row names is no longer on file")
    if not eligible(rec["source_action"], frame):
        # The photography jobs' own rule (`OP.awaiting_motif`, `MP._awaiting_motif_frame`):
        # a render the asset-truth gate did not clear, or a frame with another floor open or
        # failed, is not made usable by any motif answer, so nothing is bought to ask.
        return settle(INELIGIBLE, why=("ineligible on its merits: "
                                       + ("the asset-truth verdict is not clear"
                                          if rec["source_action"] == OWNED else
                                          "another floor of the frame is open or failed")))
    if not MF.worth_rejudging(frame):
        # ENG-MOTIF's rule, kept: a re-ask is bought only when a match would make the render
        # usable. A generated frame has no structural PASS (F-852), so asking would spend a
        # vision call on an answer that changes nothing. Parked, not lost: re-evaluated free
        # on every sweep, and asked the day a qualified producer gives it a structural floor.
        return settle(PARKED, why=("a match would not make this render usable: the "
                                   "structural floor gives a generated frame no PASS (F-852, "
                                   "D-FB-7), so no vision call is bought to re-ask"))
    newer = _newer_answer(db, rec)
    if newer is not None:
        # Already answered for this image -- by the photography job's own re-ask, or by this
        # sweep before a crash between filing and settling. Reused; nothing is paid.
        filed_id, newer_detail, newer_frame = newer
        out = settle_answer(newer_frame, filed_id,
                            ours=newer_detail.get("motif_recovered_by") == JOB_TYPE)
        return dict(out, reused_answer=filed_id)
    paid_attempts = int(rec["rechecks"] or 0) - int(rec["budget_deferrals"] or 0)
    if paid_attempts >= MAX_RECHECKS:
        # Every attempt that could have paid is spent -- including one claimed and then lost
        # to a crash mid-call. Reported, never regenerated: nobody judged the fabric.
        return settle(UNRESOLVED, why=f"{paid_attempts} re-asks claimed with no verdict "
                                      f"(MAX_RECHECKS {MAX_RECHECKS})")
    if allowance is not None and allowance.get("left", 0) <= 0:
        return {"id": rec_id, "state": rec["state"], "skipped": True,
                "deferred": "sweep_bound"}
    cir, twin, why = _release_of(db, rec["slug"], rec["version"])
    if cir is None:
        return settle(SUPERSEDED, why=why[:400])
    claim = _claim(db, rec_id, rec, now)
    if claim != "claimed":
        return {"id": rec_id, "state": rec["state"], "skipped": True, "deferred": claim}
    if allowance is not None:
        allowance["left"] = allowance.get("left", 0) - 1
    asked = int(rec["rechecks"] or 0) + 1

    with workspace.work_dir(None, prefix="motif-backlog-") as work:
        if rec["source_action"] == OWNED:
            answered = OP.rejudge_motif(db, frame, cir, twin, work_dir=work, provider=provider,
                                        judger=judger, now=now)
        else:
            answered = MP.rejudge_frame(db, frame, cir, twin, work_dir=work, provider=provider,
                                        judger=judger, now=now)
    motif = dict(answered.get("motif") or (answered.get("record") or answered.get("frame")
                                           or {}).get("motif") or {})
    motif.pop("chart", None)
    code = str(motif.get("unmeasured") or "")
    if not answered.get("filed"):
        state = _CODE_STATE.get(code, QUEUED_RETRY)
        if state == QUEUED_RETRY and asked >= MAX_RECHECKS:
            state = UNRESOLVED
        if state == QUEUED_BUDGET:
            with db.session() as s:
                row = s.get(MotifRecovery, rec_id)
                row.budget_deferrals = int(row.budget_deferrals or 0) + 1
        return dict(settle(state, refusal_code=(code or "unknown")[:40],
                           why=str(motif.get("why") or answered.get("why") or "")[:400]),
                    paid=True)
    if code in _NO_VERDICT and asked < MAX_RECHECKS:
        # No verdict about the fabric: retried, and nothing filed -- an unanswered question is
        # not charged as an attempt while it can still be asked. On the last try it is filed,
        # so the render stops waiting everywhere (ENG-MOTIF's own reading of these codes).
        return dict(settle(QUEUED_RETRY, refusal_code=code, why=str(motif.get("why"))[:400]),
                    paid=True)
    filed_id = _file_answer(db, rec, detail, answered)
    answer = answered["record"] if rec["source_action"] == OWNED else answered["frame"]
    return dict(settle_answer(answer, filed_id, ours=True), paid=True)


# ---- advancement: a completed gallery hands off to the release chain ------------------------
#
# The handoff that was missing (W6 ENG-MOTIF-BACKLOG trace): `assets.owned_photography`,
# `assets.model_photography` and this recovery all filed a usable gallery and enqueued nothing,
# so `pricing.position` -> `listing.seo` -> `launch.plan` -> `listing.package` saw it only if
# some later sweep happened to re-read the release. The successor is `assets.build` for the
# certified release -- the stage that reads `listing_asset.last` and itself enqueues
# `pricing.position`, which the existing chain carries through `listing.seo` and `launch.plan`
# to `listing.package`. One key per gallery identity, so the same gallery advances once.

GALLERY_TOKEN = "gallery:"


def _enqueue_once(enqueue, agent, job_type, inputs, **kw):
    """A duplicate idempotency key is the same work already queued: a success, not an error
    (`JobContext.enqueue` already says so; a bare `JobQueue.enqueue` raises)."""
    from ..queue.durable import DuplicateJob

    try:
        return enqueue(agent, job_type, inputs, **kw)
    except DuplicateJob:
        return None


def certified_release(db, slug: str, version: str) -> str | None:
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        if pv is None or not pv.certified:
            return None
        return pv.release_hash or ""


def gallery_complete(db, slug: str, version: str) -> tuple[bool, str, frozenset]:
    """Whether the listing gallery for slug@version is complete, by the EXISTING reader
    (`listing_asset.last` + `listing_asset.usable`: every floor, structural PASS included).
    Returns (complete, identity, image sha256s of the frames that completed it)."""
    import hashlib

    from . import listing_asset

    record = listing_asset.last(db, slug=slug)
    if not record or str(record.get("version") or "") != str(version):
        return False, "", frozenset()
    if not listing_asset.usable(record):
        return False, "", frozenset()
    frames = [f for f in (record.get("frames") or [record]) if isinstance(f, dict)]
    shas = frozenset(s for s in (_sha(f) for f in frames) if s)
    ident = "|".join(sorted(_sha(f) or str((f.get("image") or {}).get("url") or "")
                            for f in frames))
    return True, hashlib.sha256(ident.encode()).hexdigest()[:12], shas


def gallery_handoff(enqueue, db, slug: str, version: str, *,
                    requires_image: str = "") -> dict:
    """Enqueue `assets.build` for a release whose gallery is now complete. Writes nothing
    else; a gallery that is not complete by the existing reader advances nothing. With
    `requires_image`, only a gallery that this image is part of counts: a product whose
    gallery was already complete from other frames was not completed by this render."""
    from ..runtime.release import chain_key

    done, ident, shas = gallery_complete(db, slug, version)
    if not done:
        return {"advanced": False, "why": "gallery not complete by listing_asset.usable"}
    if requires_image and requires_image not in shas:
        return {"advanced": False, "why": "the completed gallery does not use this render"}
    release = certified_release(db, slug, version)
    if release is None:
        return {"advanced": False, "why": "no certified release for this version"}
    token = GALLERY_TOKEN + ident
    job = _enqueue_once(enqueue, "publishing", "assets.build",
                        {"slug": slug, "version": version, "release": release, "rebuild": token},
                        idempotency_key=chain_key("assets", slug, version, release, token))
    return {"advanced": True, "job_id": getattr(job, "id", None), "token": token,
            "queued": job is not None}


# ---- the sweep (the job) --------------------------------------------------------------------

def regenerate_with(enqueue):
    """The regeneration path for a GENUINELY failed render: the existing photography job for
    its path, keyed per render so a re-sweep never queues it twice."""
    def regen(source: str, slug: str, rec_id: int):
        with_key = f"{REGEN_KEY}{source}:{rec_id}"[:200]
        job = _enqueue_once(enqueue, AGENT, source,
                            {"slug": slug, "reason": "motif_backlog_failed"},
                            idempotency_key=with_key)
        return getattr(job, "id", None)
    return regen


def _package_ready_since(db, slug: str, version: str, since: datetime) -> datetime | None:
    """The listing package for slug@version, READY and assembled at/after `since`."""
    from ..core.models import OperatingReading
    from . import listing_package as LP

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == LP.KIND,
            OperatingReading.period_key == f"{slug}@{version}"))
        payload = dict(row.payload or {}) if row is not None else {}
    if payload.get("state") != LP.READY:
        return None
    try:
        at = datetime.fromisoformat(str(payload.get("assembled_at")))
    except (TypeError, ValueError):
        return None
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return at if at >= since else None


def sweep(db, enqueue, *, provider=None, judger=None, limit: int = SWEEP_LIMIT,
          now: datetime | None = None, audit=None) -> dict:
    """Scan, re-check the open rows, regenerate only genuine failures, hand completed
    galleries to the chain, and stamp galleries/packages that completed. Idempotent."""
    now = _now(now)
    found = scan(db, now=now)
    with db.session() as s:
        ids = list(s.scalars(select(MotifRecovery.id).where(
            MotifRecovery.state.in_((BLOCKED, QUEUED_BUDGET, QUEUED_RETRY)))
            .order_by(MotifRecovery.id).limit(SCAN_LIMIT)))
        # Parked rows cost nothing to re-evaluate (no call unless a match could be used), but
        # one that becomes worth asking draws on the same allowance as every other row.
        ids += list(s.scalars(select(MotifRecovery.id).where(MotifRecovery.state == PARKED)
                              .order_by(MotifRecovery.id).limit(SCAN_LIMIT)))
    # ONE bound on paid re-asks for the whole sweep, across every row state, and never more
    # than the day has left under the durable daily cap (`_claim` re-checks it per call).
    allowance = {"left": max(0, min(int(limit), daily_cap() - claimed_today(db, now=now)))}
    regen = regenerate_with(enqueue)
    results = []
    for rec_id in ids:
        out = recheck_one(db, rec_id, provider=provider, judger=judger, now=now,
                          regenerate=regen, allowance=allowance)
        results.append(out)
        if audit is not None and not out.get("skipped"):
            audit(AUDIT_RECHECKED, artifact=str(rec_id),
                  detail={k: out.get(k) for k in ("state", "verdict", "regen_job_id")})
    # Passed renders: hand completed galleries on, once per gallery; stamp what completed.
    advanced = []
    with db.session() as s:
        passed = [(r.id, r.slug, r.version, r.image_sha256, r.gallery_completed_at,
                   r.package_ready_at)
                  for r in s.scalars(select(MotifRecovery).where(MotifRecovery.state == PASSED))]
    for rec_id, slug, version, sha, gallery_at, package_at in passed:
        if gallery_at is None:
            hand = gallery_handoff(enqueue, db, slug, version, requires_image=sha)
            if hand["advanced"]:
                advanced.append({"slug": slug, "version": version, **hand})
                with db.session() as s:
                    s.get(MotifRecovery, rec_id).gallery_completed_at = now
                gallery_at = now
        if gallery_at is not None and package_at is None:
            ready = _package_ready_since(db, slug, version, _now(gallery_at))
            if ready is not None:
                with db.session() as s:
                    s.get(MotifRecovery, rec_id).package_ready_at = ready
    summary = {"scan": found,
               "rechecked": len([r for r in results if not r.get("skipped")
                                 and r.get("state") != PARKED]),
               "paid_reasks": sum(1 for r in results if r.get("paid")),
               "deferred": sum(1 for r in results if r.get("deferred")),
               "states": {st: sum(1 for r in results if r.get("state") == st) for st in STATES},
               "advanced": advanced[:30]}
    if audit is not None:
        audit(AUDIT_SWEPT, detail={"scan": found, "rechecked": summary["rechecked"],
                                   "paid_reasks": summary["paid_reasks"],
                                   "states": summary["states"],
                                   "advanced": len(advanced)})
    summary["work_done"] = bool(found["new"] or summary["rechecked"] or advanced)
    return summary


# ---- the report (read-only) -----------------------------------------------------------------

UNKNOWN = "UNKNOWN"


def report(db) -> dict:
    """Owner-visible recovery counts, from persisted rows only. Never writes.

    A count nobody has measured is UNKNOWN, never 0: before the first sweep there is no
    `assets.motif_backlog.swept` row, so the backlog has not been looked at, and an
    unreadable table is UNKNOWN with the reason."""
    from sqlalchemy import desc, func, inspect as sa_inspect

    from ..core.models import AuditLog

    try:
        with db.session() as s:
            swept = s.scalar(select(AuditLog).where(AuditLog.action == AUDIT_SWEPT)
                             .order_by(desc(AuditLog.id)).limit(1))
            last_sweep = swept.at if swept is not None else None
        if last_sweep is None or not sa_inspect(db.engine).has_table(
                MotifRecovery.__tablename__):
            counts = {k: UNKNOWN for k in COUNT_NAMES}
            return {"readable": True, "swept": False, "last_sweep_at": None,
                    "counts": counts, "why": "the recovery sweep has never run, so the backlog "
                                             "has not been measured; UNKNOWN, not 0"}
        with db.session() as s:
            by_state = dict(s.execute(select(MotifRecovery.state, func.count())
                                      .group_by(MotifRecovery.state)).all())
            rechecked = s.scalar(select(func.count()).where(MotifRecovery.rechecks > 0)
                                 .select_from(MotifRecovery))
            galleries = s.scalar(select(func.count(func.distinct(
                MotifRecovery.slug + "@" + MotifRecovery.version))).where(
                MotifRecovery.gallery_completed_at.is_not(None)))
            packages = s.scalar(select(func.count(func.distinct(
                MotifRecovery.slug + "@" + MotifRecovery.version))).where(
                MotifRecovery.package_ready_at.is_not(None)))
            regenerated = s.scalar(select(func.count()).where(
                MotifRecovery.regen_job_id.is_not(None)).select_from(MotifRecovery))
            products = s.scalar(select(func.count(func.distinct(
                MotifRecovery.slug + "@" + MotifRecovery.version))))
        counts = {
            "renders_found_blocked": sum(by_state.values()),
            "renders_rechecked": int(rechecked or 0),
            "renders_passed": int(by_state.get(PASSED, 0)),
            "renders_failed": int(by_state.get(FAILED, 0)),
            "renders_still_queued_budget": int(by_state.get(QUEUED_BUDGET, 0)),
            "renders_queued_retry": int(by_state.get(QUEUED_RETRY, 0)),
            "renders_parked_unusable_if_matched": int(by_state.get(PARKED, 0)),
            "renders_unresolved": int(by_state.get(UNRESOLVED, 0)),
            "renders_awaiting_first_recheck": int(by_state.get(BLOCKED, 0)),
            "renders_bytes_missing": int(by_state.get(BYTES_MISSING, 0)),
            "renders_superseded": int(by_state.get(SUPERSEDED, 0)),
            "renders_ineligible_on_merits": int(by_state.get(INELIGIBLE, 0)),
            "regenerations_queued": int(regenerated or 0),
            "products_blocked": int(products or 0),
            "products_gallery_completed": int(galleries or 0),
            "listing_packages_became_ready": int(packages or 0),
        }
        return {"readable": True, "swept": True,
                "last_sweep_at": (last_sweep if last_sweep.tzinfo else
                                  last_sweep.replace(tzinfo=timezone.utc)).isoformat(),
                "counts": counts,
                "spend": ("each re-ask is reserved and billed by motif_fidelity._call_judge "
                          "as quality_director / asset_inspection on the spend ledger"),
                "gates_unchanged": ("a recovered motif verdict completes a gallery only where "
                                    "listing_asset.usable already accepts it: structural PASS, "
                                    "F-852, the A3 photo authority and SAMPLE_PHOTO_REQUIRED "
                                    "are unchanged")}
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never 0
        return {"readable": False, "swept": None, "last_sweep_at": None,
                "counts": {k: UNKNOWN for k in COUNT_NAMES},
                "why": f"unreadable: {type(exc).__name__}"}


COUNT_NAMES = ("renders_found_blocked", "renders_rechecked", "renders_passed",
               "renders_failed", "renders_still_queued_budget", "renders_queued_retry",
               "renders_parked_unusable_if_matched", "renders_unresolved",
               "renders_awaiting_first_recheck", "renders_bytes_missing",
               "renders_superseded", "renders_ineligible_on_merits", "regenerations_queued", "products_blocked",
               "products_gallery_completed", "listing_packages_became_ready")
