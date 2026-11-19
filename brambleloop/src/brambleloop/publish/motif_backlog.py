"""OWNER P0 (ENG-MOTIF-BACKLOG): recover paid renders whose motif check was refused, not failed.

`motif_fidelity.check` called `provider.see` with no company-budget reservation. The paid-provider
gate refused every such call (`no_budget_reservation`, `gateway.paid_provider_gate.authorize`)
and `check` folded the refusal into `unmeasurable`, so `motif_verified` was False on every owned
(`owned_photography.make`) and model (`model_photography.make`) render. Those renders were paid for.
A refusal is not a verdict about the fabric: the picture was never looked at.

The owner's instruction (verbatim): "Recover the backlog of existing paid images before
generating replacements. Do not throw away assets merely because verification was temporarily
refused."

**What this does, and what it never does.**

* `scan` finds every filed render (an `assets.owned_photography` row, or a frame inside an
  `assets.model_photography` sequence row) whose motif verdict is `unmeasurable` *because the
  gate refused the call for budget or reservation reasons* (`BUDGET_CODES`). A genuine
  `unmeasurable` (the fabric could not be seen) or a `mismatch` is not a refusal and is never
  picked up. One `motif_recovery` row per distinct image (slug@version + image sha256), so a
  frame a later sequence reused is one render, not two.
* `recheck` re-runs ONLY the motif comparison, on the exact bytes that were paid for (fetched
  from the artifact store by their sha256), through a reservation taken by
  `gateway.providers.check_budget` under the existing agent (`visual.inspect.AGENT`) and purpose
  (`motif_fidelity.TASK`) -- so the per-agent daily ceiling, the purpose's authorisation, the
  company month and the owner's paid-provider activation all bind exactly as they do for every
  other vision call. Nothing is rendered. No image generator is imported here.
* A render that now reads `match` is PASSED: its corrected record is overlaid onto the filed
  row by every reader that decides usability (`overlay`), so its gallery slot is judged on a
  measurement instead of on a refusal. A render that reads `mismatch` (or a genuine
  `unmeasurable`) is FAILED and is the only kind queued for regeneration, through the
  existing photography job for its path. A refusal for budget again leaves the row
  QUEUED_BUDGET for the next sweep: never lost, never regenerated.

**No gate is weakened.** The overlay replaces a refusal with a real, paid, reserved
measurement and recomputes only what that measurement feeds (`motif_verified`, the model
path's `product_truth` floor, and the record's own `usable_as_listing_asset` conjunction).
Every reader still requires `visual.product_authority.structural_floor` == PASS, which a
generated frame does not reach (F-852, D-FB-7); the listing-set certificate, the A3 photo
authority and `SAMPLE_PHOTO_REQUIRED` are untouched. So a recovered frame completes a gallery
slot only where the existing readers already accept it -- and the report says how many did,
from persisted rows, rather than assuming.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

JOB_TYPE = "assets.motif_backlog"
AGENT = "publishing"                 # the agent that runs the photography jobs it recovers
AUDIT_SWEPT = "assets.motif_backlog.swept"
AUDIT_RECHECKED = "assets.motif_backlog.rechecked"
REGEN_KEY = "motif-backlog-regen:"
SWEEP_LIMIT = 50                     # re-checks per sweep; the rest wait for the next sweep
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
QUEUED_RETRY, UNRESOLVED = "QUEUED_RETRY", "UNRESOLVED"
STATES = (BLOCKED, QUEUED_BUDGET, QUEUED_RETRY, PASSED, FAILED, BYTES_MISSING, SUPERSEDED,
          UNRESOLVED)
OPEN_STATES = (BLOCKED, QUEUED_BUDGET, QUEUED_RETRY)
MAX_RECHECKS = 3
# `motif_fidelity.check` reasons that are not a verdict about the fabric: nothing was judged.
_NOT_A_VERDICT = ("the comparison call failed:", "the answer could not be read:",
                  "the chart could not be rendered", "nothing was observed")

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
    spent_cad: Mapped[float] = mapped_column(default=0.0)
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


# ---- re-check -------------------------------------------------------------------------------

class _Metered:
    """The provider, with the one response it returns kept so the call is billed at cost."""

    def __init__(self, provider):
        self._p = provider
        self.response = None
        self.model = provider.model
        self.name = getattr(provider, "name", "anthropic")
        self.cost_per_1k_input_cad = getattr(provider, "cost_per_1k_input_cad", 0.0)
        self.cost_per_1k_output_cad = getattr(provider, "cost_per_1k_output_cad", 0.0)

    def see(self, system, prompt, image_urls, **kw):
        self.response = self._p.see(system, prompt, image_urls, **kw)
        return self.response


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


def recheck_one(db, rec_id: int, *, provider=None, now: datetime | None = None,
                regenerate=None) -> dict:
    """Re-run only the motif comparison for one recovery row. Never renders."""
    import os

    from ..core import workspace
    from ..core.artifacts import ArtifactStore
    from ..gateway import providers as gw
    from ..visual import inspect as I
    from . import motif_fidelity as MF

    now = _now(now)
    with db.session() as s:
        rec = s.get(MotifRecovery, rec_id)
        if rec is None or rec.state not in OPEN_STATES:
            return {"id": rec_id, "state": getattr(rec, "state", None), "skipped": True}
        slug, version, sha, source = rec.slug, rec.version, rec.image_sha256, rec.source_action

    def settle(state: str, **fields) -> dict:
        with db.session() as s:
            rec = s.get(MotifRecovery, rec_id)
            rec.state = state
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.checked_at = now
        return {"id": rec_id, "state": state, **{k: v for k, v in fields.items()
                                                  if k in ("verdict", "why")}}

    cir, twin, why = _release_of(db, slug, version)
    if cir is None:
        return settle(SUPERSEDED, why=why[:400])
    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception as exc:  # noqa: BLE001 - unreadable bytes are not a verdict
        return settle(BYTES_MISSING, why=f"paid bytes unavailable: {type(exc).__name__}"[:400])

    provider = _Metered(provider or gw.provider_for(MF.TASK))
    held, estimate = None, 0.0
    with workspace.work_dir(None, prefix="motif-backlog-") as root:
        path = os.path.join(root, f"{sha[:16]}.png")
        with open(path, "wb") as fh:
            fh.write(data)
        try:
            budget = gw.check_budget(
                db, model=provider.model,
                input_tokens=gw.input_tokens(provider.model, system=MF.SYSTEM,
                                             user=MF.prompt(), images=2),
                max_tokens=MF.MAX_TOKENS, agent=I.AGENT, purpose=MF.TASK,
                product_slug=slug)
            held, estimate = budget.get("reservation_id"), float(budget.get("estimate_cad") or 0)
        except Exception as exc:  # noqa: BLE001 - a ceiling refusal waits; it is not a verdict
            with db.session() as s:
                rec = s.get(MotifRecovery, rec_id)
                rec.budget_deferrals = int(rec.budget_deferrals or 0) + 1
            return settle(QUEUED_BUDGET,
                          why=f"re-check refused before the call: {type(exc).__name__}: "
                              f"{str(exc)[:200]}"[:400])
        try:
            motif = MF.check(db, path, cir, twin, provider=provider)
        finally:
            resp = provider.response
            cost = 0.0
            if resp is not None:
                cost = round(resp.input_tokens * provider.cost_per_1k_input_cad / 1000
                             + resp.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
            gw.release_reservation(db, held, actual_cad=cost if resp is not None else None)
            if resp is not None:
                I._bill(db, provider, {"reserved": estimate, "actual": cost,
                                       "tokens_in": resp.input_tokens,
                                       "tokens_out": resp.output_tokens},
                        f"motif-backlog:{sha[:16]}", purpose=MF.TASK)
    motif = {**motif, "chart": "", "rechecked_by": JOB_TYPE, "rechecked_at": now.isoformat()}

    with db.session() as s:
        rec = s.get(MotifRecovery, rec_id)
        rec.rechecks = int(rec.rechecks or 0) + 1
        rec.spent_cad = round(float(rec.spent_cad or 0.0) + cost, 8)
    code = refusal_code(motif)
    if code is not None:
        with db.session() as s:
            rec = s.get(MotifRecovery, rec_id)
            rec.budget_deferrals = int(rec.budget_deferrals or 0) + 1
        return settle(QUEUED_BUDGET, refusal_code=code, why=str(motif.get("why"))[:400])
    verdict = str(motif.get("verdict") or "")
    if verdict == MF.UNMEASURABLE and str(motif.get("why") or "").startswith(_NOT_A_VERDICT):
        with db.session() as s:
            spent_checks = int(s.get(MotifRecovery, rec_id).rechecks or 0)
        return settle(QUEUED_RETRY if spent_checks < MAX_RECHECKS else UNRESOLVED,
                      why=str(motif.get("why"))[:400])
    if verdict == MF.MATCH:
        return settle(PASSED, verdict=verdict, motif=motif, why=str(motif.get("why"))[:400])
    out = settle(FAILED, verdict=verdict, motif=motif, why=str(motif.get("why"))[:400])
    if regenerate is not None:
        job_id = regenerate(source, slug, rec_id)
        if job_id is not None:
            with db.session() as s:
                s.get(MotifRecovery, rec_id).regen_job_id = int(job_id)
        out["regen_job_id"] = job_id
    return out


# ---- overlay: the readers' view of a recovered render ---------------------------------------

def recovered(db) -> dict:
    """{(slug, version, sha256): motif} for every render a re-check measured. {} if none or
    the table is unreadable -- an unreadable recovery table leaves every record as filed."""
    try:
        ensure_tables(db)
        with db.session() as s:
            return {(r.slug, r.version, r.image_sha256): dict(r.motif or {})
                    for r in s.scalars(select(MotifRecovery).where(
                        MotifRecovery.state.in_((PASSED, FAILED))))}
    except Exception:  # noqa: BLE001 - fail closed: the filed (refused) verdict stands
        return {}


def _apply_owned(detail: dict, motif: dict) -> dict:
    from . import motif_fidelity as MF

    out = dict(detail, motif=motif, motif_verified=motif.get("verdict") == MF.MATCH,
               motif_why=motif.get("why"), motif_recovered=True)
    clear = (detail.get("verdict") == "clear")
    out["usable_as_listing_asset"] = clear and motif.get("verdict") == MF.MATCH
    out["usable_why"] = (
        "every asset-truth check passed and the fabric works the chart's pattern"
        if out["usable_as_listing_asset"]
        else f"motif: {motif.get('why')}" if clear else detail.get("why"))
    return out


def _apply_frame(frame: dict, motif: dict) -> dict:
    from . import motif_fidelity as MF

    floors = dict(frame.get("floors") or {})
    v = motif.get("verdict")
    floors["product_truth"] = ("pass" if v == MF.MATCH else "fail" if v == MF.MISMATCH
                               else "unverifiable")
    usable = bool(floors) and all(x == "pass" for x in floors.values())
    return dict(frame, motif=motif, motif_verified=v == MF.MATCH, floors=floors,
                usable_as_listing_asset=usable, motif_recovered=True,
                why=("every floor cleared" if usable else
                     "; ".join(f"{k}: {x}" for k, x in sorted(floors.items()) if x != "pass")))


def overlay(db, source: str, details: list[dict], *, table: dict | None = None) -> list[dict]:
    """The filed records with every recovered measurement applied. Same rows, same order,
    same count -- attempt budgets and failure histories count renders, and a re-check is not
    a render."""
    table = recovered(db) if table is None else table
    if not table:
        return details
    out = []
    for detail in details:
        out.append(_overlay_one(source, detail, table))
    return out


def _overlay_one(source: str, detail: dict, table: dict) -> dict:
    if not isinstance(detail, dict) or not detail.get("made"):
        return detail
    slug, version = str(detail.get("slug") or ""), str(detail.get("version") or "")
    if source == MODEL and detail.get("frames"):
        from . import model_photography as MP

        changed, frames = False, []
        for frame in detail.get("frames") or ():
            motif = (table.get((str(frame.get("slug") or slug),
                                str(frame.get("version") or version), _sha(frame)))
                     if isinstance(frame, dict) else None)
            if motif is not None and refusal_code(frame.get("motif")) is not None:
                frame, changed = _apply_frame(frame, motif), True
            frames.append(frame)
        if not changed:
            return detail
        floors = MP._combine_floors(frames)
        usable = all(v == "pass" for v in floors.values())
        return dict(detail, frames=frames, floors=floors, usable_as_listing_asset=usable,
                    motif_recovered=True,
                    why=("every floor cleared across the sequence" if usable else
                         "; ".join(f"{k}: {v}" for k, v in sorted(floors.items())
                                   if v != "pass")))
    motif = table.get((slug, version, _sha(detail)))
    if motif is None or refusal_code(detail.get("motif")) is None:
        return detail
    if source == MODEL:
        return _apply_frame(detail, motif)
    return _apply_owned(detail, motif)


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
    job = enqueue("publishing", "assets.build",
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
        job = enqueue(AGENT, source, {"slug": slug, "reason": "motif_backlog_failed"},
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


def sweep(db, enqueue, *, provider=None, limit: int = SWEEP_LIMIT,
          now: datetime | None = None, audit=None) -> dict:
    """Scan, re-check the open rows, regenerate only genuine failures, hand completed
    galleries to the chain, and stamp galleries/packages that completed. Idempotent."""
    now = _now(now)
    found = scan(db, now=now)
    with db.session() as s:
        ids = list(s.scalars(select(MotifRecovery.id).where(
            MotifRecovery.state.in_(OPEN_STATES)).order_by(MotifRecovery.id).limit(limit)))
    regen = regenerate_with(enqueue)
    results = []
    for rec_id in ids:
        out = recheck_one(db, rec_id, provider=provider, now=now, regenerate=regen)
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
    summary = {"scan": found, "rechecked": len([r for r in results if not r.get("skipped")]),
               "states": {st: sum(1 for r in results if r.get("state") == st) for st in STATES},
               "advanced": advanced[:30]}
    if audit is not None:
        audit(AUDIT_SWEPT, detail={"scan": found, "rechecked": summary["rechecked"],
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
            spent = s.scalar(select(func.coalesce(func.sum(MotifRecovery.spent_cad), 0.0)))
        counts = {
            "renders_found_blocked": sum(by_state.values()),
            "renders_rechecked": int(rechecked or 0),
            "renders_passed": int(by_state.get(PASSED, 0)),
            "renders_failed": int(by_state.get(FAILED, 0)),
            "renders_still_queued_budget": int(by_state.get(QUEUED_BUDGET, 0)),
            "renders_queued_retry": int(by_state.get(QUEUED_RETRY, 0)),
            "renders_unresolved": int(by_state.get(UNRESOLVED, 0)),
            "renders_awaiting_first_recheck": int(by_state.get(BLOCKED, 0)),
            "renders_bytes_missing": int(by_state.get(BYTES_MISSING, 0)),
            "renders_superseded": int(by_state.get(SUPERSEDED, 0)),
            "regenerations_queued": int(regenerated or 0),
            "products_blocked": int(products or 0),
            "products_gallery_completed": int(galleries or 0),
            "listing_packages_became_ready": int(packages or 0),
        }
        return {"readable": True, "swept": True,
                "last_sweep_at": (last_sweep if last_sweep.tzinfo else
                                  last_sweep.replace(tzinfo=timezone.utc)).isoformat(),
                "counts": counts, "recheck_spend_cad": round(float(spent or 0.0), 6),
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
               "renders_unresolved",
               "renders_awaiting_first_recheck", "renders_bytes_missing",
               "renders_superseded", "regenerations_queued", "products_blocked",
               "products_gallery_completed", "listing_packages_became_ready")
