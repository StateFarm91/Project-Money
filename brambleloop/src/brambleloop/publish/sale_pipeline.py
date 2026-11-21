"""The automatic sale pipeline (D-OWNER-SALE-PIPELINE, HARD RULE; ENG-SALE-PIPELINE).

"If a product passes its tests and the agents think it should be for sale, then it should
obviously have images for the PDF, the PDF with the pattern and images, and images for the
listing. Then it's ready to be for sale. Hard rule."

**Ready for sale** = a certified pattern + a complete certified campaign gallery (seven
frames, D-OWNER-GALLERY-COMPLETE) + both premium illustrated PDFs (US and UK) certified for
exactly this release against `research/benchmarks/PDF_STRUCTURE_STANDARD.md`
(D-OWNER-PDF-STANDARD, `publish.pdf_standard`) + every listing gate PASS (the listing
package, which runs `release_gates.for_publish`). Nothing less counts (`ready_for_sale`).

**The chain.** One `sale_pipeline_runs` row per slug@version@release. Each stage is one
`sale.pipeline` job on the durable queue (agent `listing`), keyed
`sale:<slug>@<version>@<release>:<stage>[:d<n>]`, so a duplicate event is a deduplicated job,
never a second gallery or a second PDF. Each stage enqueues its own successor:

1. `admission` -- the pre-image readiness reading (every non-image gate: certified pattern,
   selected for sale, copy and SEO, pricing, the children's/family decision, both PDF
   editions certified for the release, and their text, schematics and diagrams already
   passing the standard with image slots pending). Not eligible: the row waits in
   `awaiting_pre_image_readiness` and nothing is spent. Eligible: the admission queue
   (D-OWNER-SPEND-ORDER) decides, in expected-value order with the core families first,
   bounded by `PER_LISTING_IMAGE_CAP_CAD` and the CA$100/month ceiling. Admitted: a
   reservation is held and `visual.image_production` is started (or released from its own
   non-spending wait). Not yet admissible: `awaiting_admission` with the named reason.
2. `gallery` -- enqueued by image production itself when its run reaches an end state.
   The certified seven-frame gallery is read from the valid listing-set certificate
   (`etsy_ops.certified_frames`); where ENG-VIS-GALLERY's generated-gallery route is
   installed (`gallery_persist.certify_gallery`), an assembled run is certified through it.
   Complete: the reservation is consumed and `pdf_build` follows.
3. `pdf_build` -- both premium editions are rendered with the certified images in the
   standard's slots (`publish.pdf_photos`, the `campaign_photos` hook in `publish.pdf`) plus
   the CIR schematics and diagrams, and stored. One gallery spend serves both.
4. `pdf_certify` -- `publish.pdf_standard.check` on the stored bytes of each edition writes a
   durable `pdf_certificates` row per edition, bound to the release hash, the PDF hash, the
   gallery certificate and the standard's hash.
5. `attach` -- the listing package is re-assembled; it attaches the gallery, carries both
   premium PDFs, and BLOCKS unless both certificates PASS for exactly this release.
6. `ready` -- `ready_for_sale` is re-checked and the row is marked READY. A gate that
   blocks only publication (the sample photograph, `release_gates.ACTIVATION_ONLY_CODES`,
   D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE) does not stop READY or the private draft; it is
   recorded as `publication_waits_on`, and activation still refuses on it.

**No silent stalls.** `sweep` (the hourly `sale.pipeline_sweep`, run by Railway's
scheduler) admits newly eligible releases, re-drives a stage that has not advanced within
`STALL_AFTER` (bounded, `MAX_REDRIVES`), and opens one P2 incident per stalled release with
the named blocker (provider key missing, identity not qualified, budget ceiling, ...).
`board` gives Mission Control and readback the counts: eligible, gallery done, PDFs
certified, READY, blocked by reason. A rejected or parked product's reservation is released.

Nothing here publishes, calls Etsy, a model or the network. The only spend it can start is
image production, and only for an admitted release.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

JOB_TYPE = "sale.pipeline"
SWEEP_JOB_TYPE = "sale.pipeline_sweep"
AGENT = "listing"
AUDIT = "sale.pipeline"
INCIDENT_PREFIX = "sale-stall:"

STAGES = ("admission", "gallery", "pdf_build", "pdf_certify", "attach", "ready")
# Run states. `awaiting_pre_image_readiness` and `awaiting_admission` never spend.
AWAITING_PRE_IMAGE = "awaiting_pre_image_readiness"
AWAITING_ADMISSION = "awaiting_admission"
GALLERY = "gallery_in_production"
GALLERY_DONE = "gallery_certified"
PDFS_BUILT = "pdfs_built"
PDFS_CERTIFIED = "pdfs_certified"
ATTACHED = "images_attached"
READY = "READY"
PARKED, REJECTED = "parked", "rejected"
STATES = (AWAITING_PRE_IMAGE, AWAITING_ADMISSION, GALLERY, GALLERY_DONE, PDFS_BUILT,
          PDFS_CERTIFIED, ATTACHED, READY, PARKED, REJECTED)
# Which stage runs next from each state.
NEXT_STAGE = {AWAITING_PRE_IMAGE: "admission", AWAITING_ADMISSION: "admission",
              GALLERY: "gallery", GALLERY_DONE: "pdf_build", PDFS_BUILT: "pdf_certify",
              PDFS_CERTIFIED: "attach", ATTACHED: "ready"}
ELIGIBLE_STATES = (AWAITING_ADMISSION, GALLERY, GALLERY_DONE, PDFS_BUILT, PDFS_CERTIFIED,
                   ATTACHED, READY)

# D-OWNER-SPEND-ORDER: the bounds, in code.
def _per_listing_cap() -> float:
    from ..visual.image_production import MAX_SPEND_CAD_PER_GALLERY

    return float(MAX_SPEND_CAD_PER_GALLERY)


PER_LISTING_IMAGE_CAP_CAD = 2.00      # = image_production.MAX_SPEND_CAD_PER_GALLERY
CORE_FAMILY_WORDS = {
    "amigurumi": ("amigurumi", "stuffed", "plush", "toy", "softie"),
    "baby": ("baby", "infant", "newborn", "nursery"),
    "pillow": ("pillow", "cushion"),
}
# Bounded time to advance before an eligible release is an incident, by state.
STALL_AFTER = {AWAITING_ADMISSION: timedelta(hours=24), GALLERY: timedelta(hours=12),
               GALLERY_DONE: timedelta(hours=2), PDFS_BUILT: timedelta(hours=2),
               PDFS_CERTIFIED: timedelta(hours=2), ATTACHED: timedelta(hours=2)}
MAX_REDRIVES = 3
SWEEP_LIMIT = 200

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


# ---- records ------------------------------------------------------------------------------

class SalePipelineRun(Base):
    __tablename__ = "sale_pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(40))
    release: Mapped[str] = mapped_column(String(80))
    family: Mapped[str] = mapped_column(String(40), default="other")
    core: Mapped[bool] = mapped_column(Boolean, default=False)
    ev_score: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(40), default=AWAITING_PRE_IMAGE, index=True)
    stage: Mapped[str] = mapped_column(String(40), default="admission")
    blocker: Mapped[str] = mapped_column(String(80), default="")
    blocker_detail: Mapped[str] = mapped_column(Text, default="")
    reserved_cad: Mapped[float] = mapped_column(Float, default=0.0)
    reservation: Mapped[str] = mapped_column(String(20), default="none")
    redrives: Mapped[int] = mapped_column(Integer, default=0)
    readiness: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    progressed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PdfCertificate(Base):
    """One edition's verdict against the PDF standard, for exactly one release and file."""
    __tablename__ = "pdf_certificates"
    __table_args__ = (UniqueConstraint("release", "terminology", "pdf_sha256",
                                       name="uq_pdf_certificate"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(40))
    release: Mapped[str] = mapped_column(String(80), index=True)
    terminology: Mapped[str] = mapped_column(String(4))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(24))
    checks: Mapped[list] = mapped_column(JSON, default=list)
    expected: Mapped[dict] = mapped_column(JSON, default=dict)
    gallery_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_pdf_sha256: Mapped[str] = mapped_column(String(64), default="")
    standard_sha256: Mapped[str] = mapped_column(String(64), default="")
    checker: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_TABLES = (SalePipelineRun.__table__, PdfCertificate.__table__)
_ensured: set = set()
_lock = threading.Lock()


def ensure_tables(db) -> None:
    key = id(db.engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            for t in _TABLES:
                t.create(db.engine, checkfirst=True)
            _ensured.add(key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(t: datetime | None) -> datetime | None:
    if t is None:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def run_key(slug: str, version: str, release: str) -> str:
    return f"sale:{slug}@{version}@{release}"


def stage_key(slug: str, version: str, release: str, stage: str, drive: int = 0) -> str:
    return run_key(slug, version, release) + f":{stage}" + (f":d{drive}" if drive else "")


def _row(s, key: str, *, lock: bool = False):
    from sqlalchemy import select

    q = select(SalePipelineRun).where(SalePipelineRun.run_key == key)
    return s.scalar(q.with_for_update() if lock else q)


def _view(r) -> dict:
    return {"run_key": r.run_key, "slug": r.slug, "version": r.version, "release": r.release,
            "family": r.family, "core": bool(r.core), "ev_score": r.ev_score,
            "state": r.state, "stage": r.stage, "blocker": r.blocker or None,
            "blocker_detail": r.blocker_detail or None, "reserved_cad": r.reserved_cad,
            "reservation": r.reservation, "redrives": r.redrives,
            "readiness": dict(r.readiness or {}), "evidence": dict(r.evidence or {}),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "progressed_at": r.progressed_at.isoformat() if r.progressed_at else None}


def get(db, slug: str, version: str, release: str) -> dict | None:
    ensure_tables(db)
    with db.session() as s:
        r = _row(s, run_key(slug, version, release))
        return _view(r) if r else None


def ensure_run(db, slug: str, version: str, release: str) -> dict:
    ensure_tables(db)
    key = run_key(slug, version, release)
    fam, core = classify(db, slug)
    with db.session() as s:
        r = _row(s, key)
        if r is None:
            r = SalePipelineRun(run_key=key, slug=slug, version=version, release=release,
                                family=fam, core=core, evidence={})
            s.add(r)
            s.flush()
        return _view(r)


_ORDER = {st: i for i, st in enumerate(STATES)}
HIGH_WATER = "progress_high_water"   # evidence key: the furthest state this run has reached


def _forward(high: str | None, now: str) -> bool:
    """True when `now` is further along STATES than the furthest state the run has reached.
    Returning to a state held earlier (a flapping gate) is not progress, so it never resets
    the stall clock. PARKED and REJECTED are terminal decisions and count as progress."""
    if now in (PARKED, REJECTED):
        return True
    return _ORDER.get(now, -1) > _ORDER.get(high, -1)


def _update(db, key: str, *, state: str | None = None, stage: str | None = None,
            blocker: str | None = None, detail: str = "", progressed: bool = False,
            evidence: dict | None = None, **fields) -> dict:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        r = _row(s, key, lock=True)
        if state is not None and state != r.state:
            # Progress is a forward move past the furthest state reached: a flap back and
            # forth (a transient UNKNOWN gate) never resets the stall clock (review b19-a #5).
            ev0 = dict(r.evidence or {})
            high = ev0.get(HIGH_WATER) or r.state
            if _forward(high, state):
                progressed = True
                ev0[HIGH_WATER] = state
            else:
                ev0[HIGH_WATER] = high
            r.evidence = ev0
            flag_modified(r, "evidence")
            r.state = state
        if stage is not None:
            r.stage = stage
        if blocker is not None:
            r.blocker, r.blocker_detail = blocker[:80], str(detail or "")[:2000]
        if evidence:
            ev = dict(r.evidence or {})
            ev.update(evidence)
            r.evidence = ev
            flag_modified(r, "evidence")
        for k, v in fields.items():
            setattr(r, k, v)
            if isinstance(v, (dict, list)):
                flag_modified(r, k)
        r.updated_at = _now()
        if progressed:
            r.progressed_at = r.updated_at
            r.redrives = 0
        return _view(r)


# ---- family and expected value -------------------------------------------------------------

def classify(db, slug: str) -> tuple[str, bool]:
    """(family, core). Core families first (D-OWNER-CORE-FAMILIES): amigurumi, baby, pillow."""
    words = [slug.lower()]
    try:
        from sqlalchemy import select

        from ..core.models import Listing, PatternVersion, Product

        with db.session() as s:
            p = s.scalar(select(Product).where(Product.slug == slug))
            if p is not None:
                words.append(str(getattr(p, "name", "") or getattr(p, "title", "")).lower())
                pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == p.id)
                              .order_by(PatternVersion.id.desc()).limit(1))
                cir = dict(pv.cir_json or {}) if pv is not None else {}
                words += [str(cir.get("title") or "").lower(),
                          str(cir.get("category") or "").lower()]
            li = s.scalar(select(Listing).where(Listing.product_slug == slug)
                          .order_by(Listing.id.desc()).limit(1))
            if li is not None:
                words.append(str(li.title or "").lower())
    except Exception:  # noqa: BLE001 - unreadable facts classify as other, never core
        pass
    text = " ".join(words)
    for fam, needles in CORE_FAMILY_WORDS.items():
        if any(n in text for n in needles):
            return fam, True
    return "other", False


def expected_value(db, slug: str, version: str, *, core: bool) -> float:
    """The admission order's score: the listing's price (what one sale earns) weighted 2x for
    a core family, plus the demand reading where one is recorded. Unknown price scores 0, so
    an unpriced product is never admitted ahead of a priced one."""
    from sqlalchemy import select

    from ..core.models import Listing

    price = 0.0
    try:
        with db.session() as s:
            li = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                Listing.version == version))
            price = float(li.price_cad or 0.0) if li is not None else 0.0
    except Exception:  # noqa: BLE001
        price = 0.0
    demand = 1.0
    try:
        from ..radar import market  # MadelineMaeCo-like demand, where measured

        reading = getattr(market, "demand_weight", None)
        if callable(reading):
            demand = float(reading(db, slug) or 1.0)
    except Exception:  # noqa: BLE001 - no demand reading is neutral, never a boost
        demand = 1.0
    return round(price * (2.0 if core else 1.0) * max(0.0, demand), 4)


# ---- pre-image readiness ---------------------------------------------------------------------

def _gate(status: str, why: str = "", **kw) -> dict:
    return {"status": status, "why": why, **kw}


def _latest_job(db, job_type: str, slug: str, version: str, release: str):
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    with db.session() as s:
        for job in s.scalars(select(Job).where(Job.job_type == job_type,
                                               Job.status == JobStatus.DONE)
                             .order_by(desc(Job.id)).limit(500)):
            i = dict(job.inputs or {})
            if (i.get("slug"), i.get("version")) == (slug, version) and \
                    str(i.get("release") or "") == release:
                return {"id": job.id, "inputs": i, "outputs": dict(job.outputs or {})}
    return None


def base_pdf_hashes(db, slug: str, version: str, release: str) -> dict | None:
    """The text-only PDFs `assets.build` certified for exactly this release."""
    from ..runtime import pipeline

    return pipeline._certified_pdf_hashes(db, slug, version, release)


def _base_pdf_bytes(db, slug, version, release, terminology, sha) -> bytes:
    from ..commerce import deliverables

    got = deliverables.resolve_pdf(db, slug, version, terminology, release=release)
    data = got.get("bytes") if isinstance(got, dict) else None
    if not isinstance(data, (bytes, bytearray)) or hashlib.sha256(data).hexdigest() != sha:
        raise ValueError(f"{terminology} PDF bytes do not match the certified hash")
    return bytes(data)


def _cir(db, slug: str, version: str):
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == p.id,
                                                   PatternVersion.version == version)) \
            if p is not None else None
        if pv is None:
            return None, None
        return CIR.from_dict(pv.cir_json), {"certified": bool(pv.certified),
                                            "release_hash": pv.release_hash or "",
                                            "created": pv.created_at}


def pre_image_readiness(db, slug: str, version: str, release: str, *,
                        cached: dict | None = None) -> dict:
    """Every non-image listing gate for this release. Eligible only when all PASS; UNKNOWN is
    never PASS. `cached` is a previous reading: the PDF-structure reading is reused while the
    base PDF hashes are unchanged (it costs two PDF parses)."""
    from sqlalchemy import select

    from ..core.models import Listing

    gates: dict[str, dict] = {}
    cir, pv = None, None
    try:
        cir, pv = _cir(db, slug, version)
    except Exception as exc:  # noqa: BLE001
        gates["certified_pattern"] = _gate(UNKNOWN, f"{type(exc).__name__}")
    if "certified_pattern" not in gates:
        ok = bool(pv and pv["certified"] and release and pv["release_hash"] == release)
        gates["certified_pattern"] = _gate(PASS if ok else FAIL, "" if ok else
                                           "no certified pattern for exactly this release")
    # selected for sale: the agents' launch decision for this release, not withheld.
    launch = _latest_job(db, "launch.plan", slug, version, release)
    if launch is None:
        gates["selected_for_sale"] = _gate(FAIL, "no launch decision for this release yet")
    elif launch["outputs"].get("withheld") or launch["outputs"].get("refused"):
        gates["selected_for_sale"] = _gate(FAIL, "the launch decision withheld this release",
                                           decision="withheld")
    else:
        gates["selected_for_sale"] = _gate(PASS, held=bool(launch["outputs"].get("held")))
    copy = None
    try:
        with db.session() as s:
            li = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                Listing.version == version))
            if li is not None:
                copy = {"title": li.title, "description": li.description,
                        "tags": list(li.tags or []), "price_cad": li.price_cad,
                        "release": li.release_hash or ""}
    except Exception as exc:  # noqa: BLE001
        gates["copy_seo"] = _gate(UNKNOWN, type(exc).__name__)
    if "copy_seo" not in gates:
        seo = _latest_job(db, "listing.seo", slug, version, release)
        ok = bool(copy and copy["title"] and copy["tags"] and copy["release"] == release
                  and seo is not None and seo["outputs"].get("ok") is True)
        gates["copy_seo"] = _gate(PASS if ok else FAIL, "" if ok else
                                  "no listing copy and SEO drafted for exactly this release")
        price = (copy or {}).get("price_cad") or 0
        gates["pricing"] = _gate(PASS if price and price > 0 else FAIL,
                                 "" if price and price > 0 else "no price positioned")
    else:
        gates["pricing"] = _gate(UNKNOWN, "listing unreadable")
    try:
        from ..products import launch0

        decision = (launch0.childrens_decision_for(cir, listing=copy) if cir is not None
                    else None)
        words = launch0.child_words_in_listing(copy) if copy else False
        dec = decision[0] if isinstance(decision, tuple) else None
        if cir is None:
            gates["child_family"] = _gate(UNKNOWN, "no pattern to judge")
        elif dec == getattr(launch0, "UNDECIDED", "undecided"):
            gates["child_family"] = _gate(FAIL, "the children's audience decision is undecided")
        elif words and dec != launch0.ASSIGNED:
            gates["child_family"] = _gate(FAIL, "listing copy names a child audience without "
                                                "an explicit assignment")
        else:
            gates["child_family"] = _gate(PASS, decision=dec)
    except Exception as exc:  # noqa: BLE001 - an unreadable decision is never a pass
        gates["child_family"] = _gate(UNKNOWN, type(exc).__name__)
    hashes = None
    try:
        hashes = base_pdf_hashes(db, slug, version, release)
    except Exception as exc:  # noqa: BLE001
        gates["pdf_text"] = _gate(UNKNOWN, type(exc).__name__)
    if "pdf_text" not in gates:
        ok = bool(hashes and hashes.get("US") and hashes.get("UK"))
        gates["pdf_text"] = _gate(PASS if ok else FAIL, "" if ok else
                                  "both PDF editions are not certified for this release",
                                  hashes=dict(hashes or {}))
    # Text, schematics and diagrams against the standard, image slots pending.
    if gates["pdf_text"]["status"] == PASS and cir is not None:
        prev = (cached or {}).get("pdf_structure") or {}
        if prev.get("hashes") == hashes and prev.get("status") in (PASS, FAIL):
            gates["pdf_structure"] = prev
        else:
            gates["pdf_structure"] = _structure(db, slug, version, release, cir, hashes)
    else:
        gates["pdf_structure"] = _gate(FAIL if gates["pdf_text"]["status"] == FAIL else UNKNOWN,
                                       "no certified PDFs to read")
    failing = {k: v for k, v in gates.items() if v["status"] != PASS}
    first = next(iter(failing), None)
    return {"eligible": not failing, "gates": gates,
            "blocker": (f"pre_image:{first}" if first else ""),
            "why": (failing[first].get("why") if first else "")}


def _structure(db, slug, version, release, cir, hashes) -> dict:
    from . import pdf_standard as PS

    readings = {}
    for t in PS.TERMINOLOGIES:
        try:
            data = _base_pdf_bytes(db, slug, version, release, t, hashes[t])
            r = PS.check(data, cir=cir, terminology=t, expected=None, images="pending")
            readings[t] = {"verdict": r["verdict"], "failed": r["failed"],
                           "unknown": r["unknown"]}
        except Exception as exc:  # noqa: BLE001 - an unreadable PDF is UNKNOWN
            readings[t] = {"verdict": UNKNOWN, "error": type(exc).__name__}
    ok = all(v.get("verdict") == "PASS_PENDING_IMAGES" for v in readings.values())
    bad = any(v.get("verdict") == FAIL for v in readings.values())
    why = "" if ok else "; ".join(f"{t}: {v.get('verdict')} {v.get('failed') or v.get('error')}"
                                  for t, v in readings.items() if v.get("verdict") !=
                                  "PASS_PENDING_IMAGES")
    return {"status": PASS if ok else (FAIL if bad else UNKNOWN), "why": why,
            "hashes": dict(hashes), "editions": readings}


def spend_admitted(db, slug: str, version: str, release: str) -> bool:
    """D-OWNER-SPEND-ORDER, read by `visual.image_production` before any paid generation:
    True only while this release holds (or has consumed) an admission reservation. Unreadable
    is False."""
    try:
        ensure_tables(db)
        with db.session() as s:
            r = _row(s, run_key(slug, version, release))
            return bool(r is not None and r.reservation in ("held", "consumed")
                        and r.state not in (PARKED, REJECTED, AWAITING_PRE_IMAGE))
    except Exception:  # noqa: BLE001 - unreadable admission never spends
        return False


# ---- admission (spend order) -------------------------------------------------------------

def _month_budget(db) -> tuple[float | None, float, str]:
    """(spent this month or None if unreadable, ceiling, why)."""
    from ..gateway import routing

    try:
        b = routing.budget(db)
        return float(b.spent_cad), float(b.ceiling_cad), ""
    except Exception as exc:  # noqa: BLE001 - an unreadable ledger admits nothing
        return None, float(routing.MONTHLY_CEILING_CAD), f"{type(exc).__name__}: {exc}"[:200]


def _held_reservations(s) -> float:
    from sqlalchemy import func, select

    return float(s.scalar(select(func.coalesce(func.sum(SalePipelineRun.reserved_cad), 0.0))
                          .where(SalePipelineRun.reservation == "held")) or 0.0)


def admission_queue(db) -> list[dict]:
    """Eligible releases waiting for admission, in admission order: core families first,
    then expected value, then age."""
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(SalePipelineRun).where(
            SalePipelineRun.state == AWAITING_ADMISSION)))
        rows.sort(key=lambda r: (not r.core, -(r.ev_score or 0.0), r.id))
        return [_view(r) for r in rows]


def try_admit(db, key: str) -> dict:
    """Admit one eligible release if it is first in line and the caps allow it. Holds a
    reservation of the per-listing cap under the row lock; never over the month ceiling."""
    cap = _per_listing_cap()
    spent, ceiling, why = _month_budget(db)
    queue = admission_queue(db)
    with db.session() as s:
        r = _row(s, key, lock=True)
        if r.reservation in ("held", "consumed"):
            return {"admitted": True, "already": True}
        ahead = [q for q in queue if q["run_key"] != key and
                 (not q["core"], -(q["ev_score"] or 0.0)) < (not r.core, -(r.ev_score or 0.0))]
        if spent is None:
            return {"admitted": False, "blocker": "budget_ledger_unreadable", "why": why}
        held = _held_reservations(s)
        if spent + held + cap > ceiling + 1e-9:
            return {"admitted": False, "blocker": "budget_ceiling",
                    "why": (f"CA${spent:.2f} spent + CA${held:.2f} reserved + CA${cap:.2f} "
                            f"would cross the CA${ceiling:.2f} month ceiling")}
        free_slots = int((ceiling - spent - held + 1e-9) // cap)
        if len(ahead) >= free_slots:
            return {"admitted": False, "blocker": "admission_queue",
                    "why": f"{len(ahead)} higher-value release(s) ahead within the caps"}
        r.reservation, r.reserved_cad = "held", cap
        r.state, r.stage, r.blocker, r.blocker_detail = GALLERY, "gallery", "", ""
        r.evidence = {**dict(r.evidence or {}), HIGH_WATER: GALLERY}
        r.updated_at = r.progressed_at = _now()
        r.redrives = 0
        return {"admitted": True, "reserved_cad": cap}


def release_reservation(db, key: str, *, to_state: str, why: str) -> dict:
    """A rejected or parked product gives its reservation back (D-OWNER-SPEND-ORDER)."""
    if to_state not in (PARKED, REJECTED, AWAITING_PRE_IMAGE):
        raise ValueError(f"not a releasing state: {to_state}")
    with db.session() as s:
        r = _row(s, key, lock=True)
        if r is None:
            return {"released": False, "why": "no such run"}
        was = r.reservation
        if r.reservation == "held":
            r.reservation, r.reserved_cad = "released", 0.0
        r.state, r.blocker, r.blocker_detail = to_state, (
            "" if to_state == AWAITING_PRE_IMAGE else to_state), why[:2000]
        # A reservation given back restarts the run: the next admission is real progress.
        r.evidence = {**dict(r.evidence or {}), HIGH_WATER: to_state}
        r.updated_at = r.progressed_at = _now()
        return {"released": was == "held", "state": to_state}


def park(db, slug: str, version: str, release: str, *, why: str,
         rejected: bool = False) -> dict:
    ensure_tables(db)
    return release_reservation(db, run_key(slug, version, release),
                               to_state=REJECTED if rejected else PARKED, why=why)


# ---- stages ---------------------------------------------------------------------------------

def _next(follow, slug, version, release, stage, drive: int = 0):
    follow({"slug": slug, "version": version, "release": release, "stage": stage,
            **({"drive": drive} if drive else {})},
           stage_key(slug, version, release, stage, drive))
    return stage


def start(follow, *, slug: str, version: str, release: str) -> dict:
    """The chain's entry: enqueue `admission` once per release (idempotent key)."""
    if not (slug and version and release):
        return {"enqueued": False, "why": "slug, version and release are all required"}
    job = follow({"slug": slug, "version": version, "release": release, "stage": "admission"},
                 stage_key(slug, version, release, "admission"))
    return {"enqueued": job is not None, "run_key": run_key(slug, version, release)}


def run_stage(db, inputs: dict, *, follow, start_images=None, store_root=None) -> dict:
    """Run one stage and enqueue its successor. `start_images(slug, version, release)` starts
    (or admits) the release's image production; it defaults to the queue trigger."""
    slug, version = str(inputs["slug"]), str(inputs["version"])
    release, stage = str(inputs.get("release") or ""), str(inputs.get("stage") or "admission")
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    if not release:
        return {"skipped": True, "why": "no release named"}
    run = ensure_run(db, slug, version, release)
    key = run["run_key"]
    if run["state"] in (PARKED, REJECTED):
        return {"run_key": key, "skipped": True, "why": f"run is {run['state']}"}
    fn = {"admission": _admission, "gallery": _gallery, "pdf_build": _pdf_build,
          "pdf_certify": _pdf_certify, "attach": _attach, "ready": _ready}[stage]
    out = fn(db, key, run, follow=follow, start_images=start_images, store_root=store_root)
    return {"run_key": key, "stage": stage, **out}


def _admission(db, key, run, *, follow, start_images, store_root):
    slug, version, release = run["slug"], run["version"], run["release"]
    reading = pre_image_readiness(db, slug, version, release, cached=run["readiness"]
                                  .get("gates"))
    if not reading["eligible"]:
        sel = reading["gates"].get("selected_for_sale", {})
        if run["reservation"] == "held":
            # no longer eligible (withdrawn, re-certified): the reservation goes back
            release_reservation(db, key, to_state=AWAITING_PRE_IMAGE, why=reading["why"])
        if sel.get("decision") == "withheld":
            view = park(db, slug, version, release, why="launch decision withheld")
            _update(db, key, readiness=reading)
            return {"state": PARKED, "next": None, **view}
        view = _update(db, key, state=AWAITING_PRE_IMAGE, stage="admission",
                       blocker=reading["blocker"], detail=reading["why"], readiness=reading)
        return {"state": AWAITING_PRE_IMAGE, "next": None, "blocker": view["blocker"],
                "why": reading["why"]}
    fam, core = classify(db, slug)
    ev = expected_value(db, slug, version, core=core)
    if run["state"] in (GALLERY, GALLERY_DONE, PDFS_BUILT, PDFS_CERTIFIED, ATTACHED, READY):
        _update(db, key, readiness=reading, family=fam, core=core, ev_score=ev)
        return {"state": run["state"], "next": None, "why": "already admitted"}
    _update(db, key, state=AWAITING_ADMISSION, stage="admission", readiness=reading,
            family=fam, core=core, ev_score=ev, blocker="", detail="")
    got = try_admit(db, key)
    if not got.get("admitted"):
        _update(db, key, blocker=got["blocker"], detail=got.get("why", ""))
        return {"state": AWAITING_ADMISSION, "next": None, "blocker": got["blocker"],
                "why": got.get("why")}
    started = (start_images or _start_images_default(follow))(slug, version, release)
    _update(db, key, evidence={"image_production": started})
    return {"state": GALLERY, "admitted": True, "image_production": started,
            "next": None, "note": "image production enqueues the gallery stage at its end"}


def _start_images_default(follow):
    def start_images(slug, version, release):
        return {"via": "follow", "note": "no image starter wired"}
    return start_images


def _gallery_route_certify(db, slug, version, release):
    """ENG-VIS-GALLERY's generated-gallery certification, where installed."""
    from ..visual import image_production as IP

    try:
        from ..visual import gallery_persist as GP
    except ImportError:
        return None
    certify = getattr(GP, "certify_gallery", None)
    if certify is None:
        return None
    for key in _image_run_keys(slug, version, release):
        run = IP.get_run(db, key)
        if run and run["state"] == "ready_for_owner_review":
            return certify(db, key)
    return None


def _image_run_keys(slug, version, release) -> list[str]:
    from ..visual import image_production as IP

    keys = [IP.run_key(slug, version, release)]
    route = getattr(IP, "ROUTE_SUFFIX", None)
    if route:
        keys.insert(0, IP.run_key(slug, version, release) + route)
    return keys


def image_run(db, slug, version, release) -> dict | None:
    from ..visual import image_production as IP

    for key in _image_run_keys(slug, version, release):
        run = IP.get_run(db, key)
        if run is not None:
            return run
    return None


def gallery_reading(db, slug: str, version: str, release: str) -> dict:
    """The certified campaign gallery for exactly this release: complete (>= the campaign
    standard's seven frames) with no certificate problem, or the reason it is not."""
    from ..runtime import etsy_ops
    from ..visual.shot_plans import CAMPAIGN_MIN_FRAMES

    try:
        got = etsy_ops.certified_frames(db, slug, version, release=release)
    except Exception as exc:  # noqa: BLE001
        return {"complete": False, "why": f"{type(exc).__name__}", "frames": []}
    frames = list(got.get("frames") or [])
    problems = list(got.get("problems") or [])
    complete = not problems and len(frames) >= CAMPAIGN_MIN_FRAMES
    return {"complete": complete, "record_id": got.get("record_id"), "frames": frames,
            "why": "; ".join(str(p) for p in problems)[:600] if problems else (
                "" if complete else f"{len(frames)} of {CAMPAIGN_MIN_FRAMES} frames")}


# Named blockers for an image run that has stopped (incident vocabulary).
BLOCKERS = (
    ("provider_key_missing", ("key", "credential", "not configured", "no image generator",
                              "image_generation gate", "gate is closed", "closed")),
    ("identity_not_qualified", ("identity", "laura", "biometric", "qualif")),
    ("budget_ceiling", ("budget", "ceiling", "spend plan", "plan refused")),
    ("product_truth", ("fidelity", "motif", "product_truth", "structural")),
    ("owner_review", ("owner", "ready_for_owner_review", "approval")),
)


def name_blocker(text: str) -> str:
    t = str(text or "").lower()
    for name, needles in BLOCKERS:
        if any(n in t for n in needles):
            return name
    return "image_run_blocked" if t else "unrecorded"


def _gallery(db, key, run, *, follow, start_images, store_root):
    slug, version, release = run["slug"], run["version"], run["release"]
    if run["state"] not in (GALLERY, GALLERY_DONE):
        return {"state": run["state"], "next": None, "why": "not at the gallery stage"}
    reading = gallery_reading(db, slug, version, release)
    certify = None
    if not reading["complete"]:
        try:
            certify = _gallery_route_certify(db, slug, version, release)
        except Exception as exc:  # noqa: BLE001 - recorded as the blocker below
            certify = {"certified": False, "why": f"{type(exc).__name__}: {exc}"[:300]}
        if certify and certify.get("certified"):
            reading = gallery_reading(db, slug, version, release)
    if not reading["complete"]:
        img = image_run(db, slug, version, release)
        if img is None:
            blocker, why = "image_run_missing", "no image production run for this release"
        elif img["state"] == "blocked":
            blocker, why = name_blocker(img.get("blocked_reason")), img.get("blocked_reason")
        elif img["state"] == "ready_for_owner_review" and certify is None:
            blocker, why = ("gallery_certification_route", "the gallery is assembled; no "
                            "generated-gallery certification route is installed "
                            "(ENG-VIS-GALLERY gallery_persist.certify_gallery)")
        elif certify is not None:
            blocker, why = "gallery_certification_refused", str(certify.get("why"))[:600]
        else:
            blocker, why = "gallery_in_production", f"image run is {img['status']}"
        view = _update(db, key, blocker=blocker, detail=why or reading["why"],
                       evidence={"gallery": {k: reading[k] for k in ("complete", "why",
                                                                     "record_id")}})
        return {"state": run["state"], "next": None, "blocker": view["blocker"], "why": why}
    img = image_run(db, slug, version, release) or {}
    _update(db, key, state=GALLERY_DONE, stage="pdf_build", blocker="", detail="",
            reservation="consumed" if run["reservation"] == "held" else run["reservation"],
            evidence={"gallery": {"complete": True, "record_id": reading["record_id"],
                                  "frames": [{k: f.get(k) for k in ("position", "role",
                                                                    "sha256")}
                                             for f in reading["frames"]],
                                  "spent_cad": img.get("spent_cad")}})
    return {"state": GALLERY_DONE, "next": _next(follow, slug, version, release, "pdf_build")}


def premium_key(slug: str, version: str, terminology: str) -> str:
    from .pdf import pattern_filename

    return f"{slug}/{version}/premium/{pattern_filename(terminology)}"


def gallery_slots(db, slug, version, release, *, store_root=None) -> dict:
    """The certified gallery's bytes assigned to the PDF slots (`pdf_photos.plan`)."""
    from ..runtime import etsy_ops
    from . import pdf_photos as PP

    reading = gallery_reading(db, slug, version, release)
    if not reading["complete"]:
        return {"slots": None, "problems": [reading["why"] or "gallery incomplete"],
                "record_id": reading.get("record_id")}
    imgs = etsy_ops.certified_images(db, slug, version, release=release, store_root=store_root)
    if imgs.get("problems"):
        return {"slots": None, "problems": list(imgs["problems"]),
                "record_id": reading["record_id"]}
    by_sha = {hashlib.sha256(d).hexdigest(): d for _n, d in imgs.get("images") or []}
    frames = [{"sha256": f.get("sha256"), "role": f.get("role") or f.get("kind"),
               "position": f.get("position"), "data": by_sha.get(f.get("sha256")),
               "kind": f.get("kind") or "generated"}
              for f in reading["frames"]]
    got = PP.plan(frames)
    return {**got, "frames": frames, "record_id": reading["record_id"]}


def render_premium(db, slug: str, version: str, release: str, *, store_root=None) -> dict:
    """Both premium editions, byte-deterministic, in the owner's master template
    (D-OWNER-PDF-TEMPLATE, `publish.pdf_template.build_template_pdf`): the certified pattern
    (release date pinned, calibration) with the release's seven certified gallery frames in
    the template's slots -- the same bytes the listing uploads (one spend)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..quality.physical import calibration_from_db
    from . import pdf_photos as PP
    from .pdf import TERMINOLOGIES
    from .pdf_template import build_template_pdf

    plan = gallery_slots(db, slug, version, release, store_root=store_root)
    if plan["slots"] is None:
        raise ValueError(f"gallery not usable for the PDF: {plan['problems'][:3]}")
    bad = [p for p in plan["problems"] if "do not match" in p]
    if bad:
        raise ValueError(f"gallery not usable for the PDF: {bad[:3]}")
    cir, pv = _cir(db, slug, version)
    if cir is None or not pv["certified"] or pv["release_hash"] != release:
        raise ValueError("no certified pattern for exactly this release")
    released_on = pv["created"].date() if pv["created"] else None
    if released_on is None:
        raise ValueError("the release has no date to pin")
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(db, cir))
    docs = {t: build_template_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                  gallery=plan["frames"])
            for t in TERMINOLOGIES}
    return {"docs": docs, "expected": PP.expected(plan["slots"], plan.get("photos")),
            "gallery_record_id": plan["record_id"], "cir": cir, "layout": "template"}


def _pdf_build(db, key, run, *, follow, start_images, store_root):
    from ..core.artifacts import ArtifactStore

    slug, version, release = run["slug"], run["version"], run["release"]
    if run["state"] not in (GALLERY_DONE, PDFS_BUILT):
        return {"state": run["state"], "next": None, "why": "gallery not certified"}
    try:
        built = render_premium(db, slug, version, release, store_root=store_root)
    except Exception as exc:  # noqa: BLE001 - named, never silent
        why = f"{type(exc).__name__}: {str(exc)[:400]}"
        _update(db, key, blocker="pdf_build_failed", detail=why)
        return {"state": run["state"], "next": None, "blocker": "pdf_build_failed", "why": why}
    store = ArtifactStore(store_root) if store_root else ArtifactStore()
    files = {}
    for t, d in built["docs"].items():
        stored = store.put(premium_key(slug, version, t), d.pdf_bytes, "application/pdf",
                           db=db, keep="premium pattern PDF (sale pipeline)")
        files[t] = {"sha256": stored.sha256, "pages": d.pages}
    _update(db, key, state=PDFS_BUILT, stage="pdf_certify", blocker="", detail="",
            evidence={"premium_pdfs": files, "expected": built["expected"],
                      "gallery_record_id": built["gallery_record_id"],
                      "base_pdfs": base_pdf_hashes(db, slug, version, release) or {}})
    return {"state": PDFS_BUILT, "files": files,
            "next": _next(follow, slug, version, release, "pdf_certify")}


def certify_pdfs(db, slug: str, version: str, release: str, *, files: dict, expected: dict,
                 gallery_record_id, base: dict, store_root=None) -> dict:
    """Check each stored edition's bytes against the standard and record its certificate."""
    from ..core.artifacts import ArtifactStore
    from . import pdf_standard as PS

    cir, _pv = _cir(db, slug, version)
    store = ArtifactStore(store_root) if store_root else ArtifactStore()
    std = PS.standard_sha256() or ""
    out = {}
    for t in PS.TERMINOLOGIES:
        sha = (files.get(t) or {}).get("sha256")
        try:
            data = store.get(sha, db=db)
            r = PS.check(data, cir=cir, terminology=t, expected=expected,
                         require_template=True)
        except Exception as exc:  # noqa: BLE001
            r = {"verdict": UNKNOWN, "checks": [{"check": "readable", "status": UNKNOWN,
                                                 "why": type(exc).__name__}],
                 "failed": [], "unknown": ["readable"]}
        _record_certificate(db, slug=slug, version=version, release=release, terminology=t,
                            pdf_sha256=sha or "", verdict=r["verdict"], checks=r["checks"],
                            expected=expected, gallery_record_id=gallery_record_id,
                            base_pdf_sha256=str((base or {}).get(t) or ""), standard_sha256=std)
        out[t] = {"verdict": r["verdict"], "failed": r.get("failed"),
                  "unknown": r.get("unknown"), "pdf_sha256": sha}
    return out


def _record_certificate(db, **kw) -> None:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        row = s.scalar(select(PdfCertificate).where(
            PdfCertificate.release == kw["release"],
            PdfCertificate.terminology == kw["terminology"],
            PdfCertificate.pdf_sha256 == kw["pdf_sha256"]))
        if row is None:
            s.add(PdfCertificate(checker=_checker(), **kw))
        else:
            for k, v in kw.items():
                setattr(row, k, v)
            row.checker, row.created_at = _checker(), _now()


def _checker() -> str:
    from . import pdf_standard as PS

    return PS.CHECKER_VERSION


def _pdf_certify(db, key, run, *, follow, start_images, store_root):
    slug, version, release = run["slug"], run["version"], run["release"]
    if run["state"] not in (PDFS_BUILT, PDFS_CERTIFIED):
        return {"state": run["state"], "next": None, "why": "premium PDFs not built"}
    ev = run["evidence"]
    got = certify_pdfs(db, slug, version, release, files=ev.get("premium_pdfs") or {},
                       expected=ev.get("expected") or {},
                       gallery_record_id=ev.get("gallery_record_id"),
                       base=ev.get("base_pdfs") or {}, store_root=store_root)
    certs = pdf_certificates(db, slug, version, release)
    if not certs["both_pass"]:
        why = "; ".join(f"{t}: {v['verdict']} {v.get('failed') or v.get('unknown') or ''}"
                        for t, v in got.items() if v["verdict"] != PASS)
        _update(db, key, blocker="pdf_standard_fail", detail=why,
                evidence={"pdf_certificates": got})
        return {"state": PDFS_BUILT, "next": None, "blocker": "pdf_standard_fail", "why": why}
    _update(db, key, state=PDFS_CERTIFIED, stage="attach", blocker="", detail="",
            evidence={"pdf_certificates": got})
    return {"state": PDFS_CERTIFIED, "certificates": got,
            "next": _next(follow, slug, version, release, "attach")}


def pdf_certificates(db, slug: str, version: str, release: str) -> dict:
    """The current premium-PDF certificates for exactly this release: one per edition, for
    the premium file the pipeline built, PASS for both or not."""
    from sqlalchemy import desc, select

    from . import pdf_standard as PS

    ensure_tables(db)
    out = {"release": release, "editions": {}, "both_pass": False}
    if not release:
        return out
    run = get(db, slug, version, release) or {}
    files = (run.get("evidence") or {}).get("premium_pdfs") or {}
    base_now = None
    try:
        base_now = base_pdf_hashes(db, slug, version, release) or {}
    except Exception:  # noqa: BLE001 - unreadable base binding never passes
        base_now = None
    # The certificate is bound to the checker that issued it (a PASS from an older, weaker
    # checker is not current) and to the gallery certified now (a re-certified gallery
    # supersedes PDFs holding the old photos). A mismatch is UNKNOWN, never PASS, so the
    # sweep re-certifies (review b19-a #3, #4).
    checker_now = PS.CHECKER_VERSION
    try:
        standard_now = PS.standard_sha256() or ""
    except Exception:  # noqa: BLE001 - an unreadable standard binds nothing
        standard_now = None
    try:
        g = gallery_reading(db, slug, version, release)
        gallery_now = g.get("record_id") if g.get("complete") else None
    except Exception:  # noqa: BLE001 - an unreadable gallery binds nothing
        gallery_now = None
    with db.session() as s:
        for t in PS.TERMINOLOGIES:
            sha = (files.get(t) or {}).get("sha256")
            row = s.scalar(select(PdfCertificate).where(
                PdfCertificate.slug == slug, PdfCertificate.version == version,
                PdfCertificate.release == release, PdfCertificate.terminology == t,
                PdfCertificate.pdf_sha256 == (sha or "")).order_by(desc(PdfCertificate.id))
                .limit(1)) if sha else None
            bound = bool(row is not None and base_now is not None
                         and row.base_pdf_sha256 == str(base_now.get(t) or "")
                         and row.base_pdf_sha256)
            current = bool(row is not None and row.checker == checker_now
                           and standard_now is not None
                           and (row.standard_sha256 or "") == standard_now)
            on_gallery = bool(row is not None and gallery_now is not None
                              and row.gallery_record_id == gallery_now)
            verdict = UNKNOWN
            if row is not None:
                verdict = row.verdict if (current and on_gallery) else UNKNOWN
            out["editions"][t] = {"verdict": verdict,
                                  "recorded_verdict": row.verdict if row else None,
                                  "pdf_sha256": sha, "certificate_id": row.id if row else None,
                                  "current_checker": current,
                                  "bound_to_gallery": on_gallery,
                                  "bound_to_release_pdfs": bound}
    out["both_pass"] = all(e["verdict"] == PASS and e["bound_to_release_pdfs"]
                           for e in out["editions"].values()) and len(out["editions"]) == 2
    return out


def certified_premium_pdfs(db, slug: str, version: str, release: str, *,
                           store_root=None) -> dict | None:
    """{terminology: bytes} of both certified premium editions, re-hashed on read; None
    unless both certificates PASS for exactly this release."""
    from ..core.artifacts import ArtifactStore

    certs = pdf_certificates(db, slug, version, release)
    if not certs["both_pass"]:
        return None
    store = ArtifactStore(store_root) if store_root else ArtifactStore()
    out = {}
    for t, e in certs["editions"].items():
        data = store.get(e["pdf_sha256"], db=db)
        if hashlib.sha256(data).hexdigest() != e["pdf_sha256"]:
            return None
        out[t] = data
    return out


def _attach(db, key, run, *, follow, start_images, store_root):
    from . import listing_package as LP

    slug, version, release = run["slug"], run["version"], run["release"]
    if run["state"] not in (PDFS_CERTIFIED, ATTACHED):
        return {"state": run["state"], "next": None, "why": "PDFs not certified"}
    try:
        out = LP.for_release(db, slug, version, expected_release=release)
    except Exception as exc:  # noqa: BLE001
        why = f"{type(exc).__name__}: {str(exc)[:300]}"
        _update(db, key, blocker="listing_package_failed", detail=why)
        return {"state": run["state"], "next": None, "blocker": "listing_package_failed"}
    pkg = LP.latest(db, slug, version) or {}
    gallery = [g.get("sha256") for g in pkg.get("gallery") or []]
    if not package_ready_for_sale(pkg, release):
        why = "; ".join(f"{b.get('source')}: {b.get('why')}"
                        for b in draft_blockers(pkg) or pkg.get("blockers") or [])
        _update(db, key, blocker="listing_gates", detail=why[:2000] or "package not ready",
                evidence={"package": {"state": pkg.get("state"), "gallery": gallery,
                                      "results": out.get("ready")}})
        return {"state": run["state"], "next": None, "blocker": "listing_gates", "why": why}
    _update(db, key, state=ATTACHED, stage="ready", blocker="", detail="",
            evidence={"package": {"state": pkg.get("state"), "gallery": gallery,
                                  "fingerprint": pkg.get("fingerprint"),
                                  "publication_waits_on": publication_blockers(pkg)}})
    return {"state": ATTACHED, "next": _next(follow, slug, version, release, "ready")}


def publication_blockers(pkg: dict | None) -> list[str]:
    """The package's blockers that block only PUBLICATION (activation of a private draft),
    as their codes (D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE). Only a blocker from
    `release_gates.for_publish` whose `activation_only` tag is on
    `release_gates.ACTIVATION_ONLY_CODES`, re-checked here, counts; anything else is a
    blocker of the draft too, and unknown never counts as publication-only."""
    from . import release_gates as RG

    out = []
    for b in (pkg or {}).get("blockers") or []:
        tag = b.get("activation_only") if isinstance(b, dict) else None
        if (isinstance(tag, str) and tag in RG.ACTIVATION_ONLY_CODES
                and b.get("source") == "release_gates.for_publish"
                and str(b.get("why") or "").startswith(f"{tag}:")):
            out.append(tag)
    return sorted(set(out))


def draft_blockers(pkg: dict | None) -> list[dict]:
    """The package's blockers that also block the sale pipeline's READY state and a private
    draft: every blocker except the publication-only ones (`publication_blockers`)."""
    out = []
    for b in (pkg or {}).get("blockers") or []:
        if publication_blockers({"blockers": [b]}):
            continue
        out.append(b)
    return out


def package_ready_for_sale(pkg: dict | None, release: str) -> bool:
    """The listing package admits the release to READY: it is for exactly this release and
    every blocker on it is publication-only. A package READY for owner review has none; a
    BLOCKED one qualifies only when its sole blockers wait on the sample photograph."""
    from . import listing_package as LP

    pkg = pkg or {}
    if not release or pkg.get("release_hash") != release:
        return False
    if pkg.get("state") == LP.READY:
        return not pkg.get("blockers")
    return (pkg.get("state") == LP.BLOCKED and bool(pkg.get("blockers"))
            and not draft_blockers(pkg))


def ready_for_sale(db, slug: str, version: str, release: str | None = None) -> dict:
    """D-OWNER-SALE-PIPELINE: certified pattern + complete certified gallery + both premium
    PDF certificates PASS for this release + every listing gate PASS. Unreadable is not
    ready. `release` defaults to the certified release on file.

    D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE: a gate that blocks only publication (the sample
    photograph, `release_gates.ACTIVATION_ONLY_CODES`) does not stop READY or the private
    draft; it is returned in `publication_blockers`, and `publishable` is False while any
    remains. Activation still refuses on it (`for_publish(stage=activation)`)."""
    from . import listing_package as LP

    reasons = []
    try:
        cir, pv = _cir(db, slug, version)
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "reasons": [f"pattern unreadable: {type(exc).__name__}"]}
    if pv is None or not pv["certified"]:
        return {"ready": False, "reasons": ["no certified pattern"]}
    release = release if release is not None else pv["release_hash"]
    if not release or pv["release_hash"] != release:
        return {"ready": False, "reasons": ["the release is not the certified one"]}
    try:
        g = gallery_reading(db, slug, version, release)
        if not g["complete"]:
            reasons.append(f"gallery incomplete: {g['why']}")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"gallery unreadable: {type(exc).__name__}")
    try:
        certs = pdf_certificates(db, slug, version, release)
        if not certs["both_pass"]:
            reasons.append("premium PDFs not certified for this release: " + ", ".join(
                f"{t} {e['verdict']}" for t, e in certs["editions"].items()))
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"PDF certificates unreadable: {type(exc).__name__}")
    waits: list[str] = ["listing package unread"]
    try:
        pkg = LP.latest(db, slug, version) or {}
        if not package_ready_for_sale(pkg, release):
            reasons.append("listing gates do not all PASS (listing package not ready)")
        waits = publication_blockers(pkg)
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"listing package unreadable: {type(exc).__name__}")
    return {"ready": not reasons, "reasons": reasons, "release": release,
            "publication_blockers": waits, "publishable": not reasons and not waits}


def _ready(db, key, run, *, follow, start_images, store_root):
    slug, version, release = run["slug"], run["version"], run["release"]
    got = ready_for_sale(db, slug, version, release)
    if not got["ready"]:
        _update(db, key, blocker="not_ready", detail="; ".join(got["reasons"])[:2000])
        return {"state": run["state"], "next": None, "blocker": "not_ready",
                "reasons": got["reasons"]}
    # D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE: READY may still wait on a publication-only gate
    # (the sample photograph); it is recorded, so the board never reads it as publishable.
    _update(db, key, state=READY, stage="ready", blocker="", detail="",
            evidence={"ready_at": _now().isoformat(),
                      "publication_waits_on": got.get("publication_blockers") or []})
    return {"state": READY, "next": None,
            "publication_blockers": got.get("publication_blockers") or []}


# ---- image production hook -------------------------------------------------------------------

IMAGE_END_STATES = ("ready_for_owner_review", "blocked", "approved_for_publication")


def image_run_ended(follow, *, slug: str, version: str, release: str, state: str,
                    epoch: int = 0) -> dict:
    """Called by the `visual.image_production` handler when a run reaches an end state: the
    gallery stage is the image stage's successor. Keyed by end state and restart epoch, so a
    restarted run that ends again is a new event."""
    if state not in IMAGE_END_STATES:
        return {"enqueued": False}
    job = follow({"slug": slug, "version": version, "release": release, "stage": "gallery",
                  "image_state": state},
                 stage_key(slug, version, release, "gallery") + f":{state}:e{epoch}")
    return {"enqueued": job is not None}


# ---- sweep: admission, re-drive, stall incidents ----------------------------------------------

def candidates(db) -> list[tuple[str, str, str]]:
    """Certified releases with a listing (slug, version, release)."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    with db.session() as s:
        rows = s.execute(select(Product.slug, PatternVersion.version, PatternVersion.release_hash)
                         .join(PatternVersion, PatternVersion.product_id == Product.id)
                         .join(Listing, (Listing.product_slug == Product.slug)
                               & (Listing.version == PatternVersion.version))
                         .where(PatternVersion.certified == True)  # noqa: E712
                         .order_by(PatternVersion.id.desc()).limit(SWEEP_LIMIT)).all()
    seen, out = set(), []
    for slug, version, release in rows:
        if release and (slug, version) not in seen:
            seen.add((slug, version))
            out.append((slug, version, release))
    return out


def sweep(db, *, follow, now: datetime | None = None, incident=None) -> dict:
    """The hourly safety net. Enqueues admission for every certified release with a
    listing (deduplicated per release and hour), re-drives a stalled stage (bounded), and
    opens or restates a named incident for every eligible release that has not advanced
    within its bound. `incident(signature, summary, detail)` records one."""
    now = now or _now()
    ensure_tables(db)
    hour = now.strftime("%Y%m%d%H")
    admitted, redriven, incidents = 0, 0, []
    for slug, version, release in candidates(db):
        run = ensure_run(db, slug, version, release)
        if run["state"] in (AWAITING_PRE_IMAGE, AWAITING_ADMISSION):
            # admission is cheap to re-ask: once per hour per release
            follow({"slug": slug, "version": version, "release": release,
                    "stage": "admission", "sweep": hour},
                   stage_key(slug, version, release, "admission") + f":h{hour}")
            admitted += 1
    from sqlalchemy import select

    with db.session() as s:
        rows = [_view(r) for r in s.scalars(select(SalePipelineRun).where(
            SalePipelineRun.state.in_(tuple(STALL_AFTER))))]
    for run in rows:
        bound = STALL_AFTER[run["state"]]
        since = _aware(datetime.fromisoformat(run["progressed_at"])) if run["progressed_at"] \
            else None
        if since is None or now - since < bound:
            continue
        blocker = run["blocker"] or "no_progress"
        sig = f"{INCIDENT_PREFIX}{run['slug']}@{run['version']}"
        detail = {"run_key": run["run_key"], "state": run["state"], "blocker": blocker,
                  "why": (run["blocker_detail"] or "")[:500],
                  "stalled_hours": round((now - since).total_seconds() / 3600, 1)}
        if incident is not None:
            incident(sig, f"eligible for sale but stalled at {run['state']}: {blocker}", detail)
        incidents.append(detail)
        stage = NEXT_STAGE.get(run["state"])
        if stage and run["redrives"] < MAX_REDRIVES:
            with db.session() as s:
                r = _row(s, run["run_key"], lock=True)
                r.redrives += 1
                drive = r.redrives
            _next(follow, run["slug"], run["version"], run["release"], stage, drive)
            redriven += 1
    return {"admission_asked": admitted, "redriven": redriven, "stalled": len(incidents),
            "incidents": incidents[:30], "work_done": bool(admitted or redriven or incidents)}


def resolved_signatures(db) -> list[str]:
    """Stall incidents whose release has since reached READY (or was parked/rejected)."""
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        return [f"{INCIDENT_PREFIX}{r.slug}@{r.version}" for r in s.scalars(
            select(SalePipelineRun).where(SalePipelineRun.state.in_((READY, PARKED, REJECTED))))]


# ---- the board (Mission Control readiness row, readback) -----------------------------------

def board(db, *, now: datetime | None = None) -> dict:
    """Counts the owner sees: eligible, gallery done, PDFs certified, READY, blocked by
    reason, waiting before images. Unreadable is UNKNOWN, never 0."""
    from sqlalchemy import select

    now = now or _now()
    try:
        ensure_tables(db)
        with db.session() as s:
            rows = [_view(r) for r in s.scalars(select(SalePipelineRun))]
    except Exception as exc:  # noqa: BLE001
        return {"readable": False, "error_class": type(exc).__name__,
                "eligible": "UNKNOWN", "gallery_done": "UNKNOWN", "pdfs_certified": "UNKNOWN",
                "ready": "UNKNOWN", "blocked_by_reason": {}}
    by_state = {st: sum(1 for r in rows if r["state"] == st) for st in STATES}
    eligible = [r for r in rows if r["state"] in ELIGIBLE_STATES]
    gallery_done = [r for r in rows if r["state"] in (GALLERY_DONE, PDFS_BUILT, PDFS_CERTIFIED,
                                                      ATTACHED, READY)]
    pdfs = [r for r in rows if r["state"] in (PDFS_CERTIFIED, ATTACHED, READY)]
    blocked: dict[str, int] = {}
    stalled = 0
    for r in eligible:
        if r["state"] == READY:
            continue
        if r["blocker"]:
            blocked[r["blocker"]] = blocked.get(r["blocker"], 0) + 1
        since = _aware(datetime.fromisoformat(r["progressed_at"])) if r["progressed_at"] \
            else None
        bound = STALL_AFTER.get(r["state"])
        if bound and since and now - since >= bound:
            stalled += 1
    pre: dict[str, int] = {}
    for r in rows:
        if r["state"] == AWAITING_PRE_IMAGE:
            pre[r["blocker"] or "unrecorded"] = pre.get(r["blocker"] or "unrecorded", 0) + 1
    reserved = round(sum(r["reserved_cad"] for r in rows if r["reservation"] == "held"), 2)
    # D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE: READY for a private draft, publication still
    # waiting on a publication-only gate (the sample photograph), counted by that gate.
    waiting: dict[str, int] = {}
    for r in rows:
        if r["state"] == READY:
            for code in (r["evidence"].get("publication_waits_on") or []):
                waiting[str(code)] = waiting.get(str(code), 0) + 1
    return {"readable": True, "releases": len(rows), "eligible": len(eligible),
            "gallery_done": len(gallery_done), "pdfs_certified": len(pdfs),
            "ready": by_state[READY],
            "ready_publication_waits_on": dict(sorted(waiting.items())),
            "blocked_by_reason": dict(sorted(blocked.items())),
            "stalled": stalled, "awaiting_pre_image_readiness": by_state[AWAITING_PRE_IMAGE],
            "awaiting_pre_image_by_reason": dict(sorted(pre.items())),
            "awaiting_admission": by_state[AWAITING_ADMISSION],
            "parked": by_state[PARKED], "rejected": by_state[REJECTED],
            "reserved_cad": reserved, "per_listing_cap_cad": _per_listing_cap(),
            "by_state": by_state}
