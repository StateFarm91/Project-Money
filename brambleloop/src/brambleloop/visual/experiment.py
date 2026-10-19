"""EXPERIMENT mode: an isolated, uncertified run of the real image orchestrator (W4-WRAPTEST).

The owner approved one experiment on 2026-10-19: the first end-to-end autonomous listing test,
on the Reading Nook Cable Wrap v0.1.0, which certification refuses (UNCALIBRATED_PRIMITIVE
cable2x2: a physical calibration gate, not a design defect). The orchestrator
(`visual.image_production`) correctly refuses an uncertified release, so this module is the
one, test-guarded door through which it runs anyway. Every property below has a test in
`tests/test_w4_wraptest.py`:

1. **Scratch database only.** An experiment is opened, recognised and run only on a
   `Database(..., scratch=True)`. Production never builds one (`core.db.resolve_url`), so the
   production database can never hold a live experiment.
2. **Bound to exact content, never certified.** `open_experiment` takes the refused
   certificate's own reading (`granted` False, its reasons and its `content_hash`), checks the
   content hash against the CIR, and records the uncertified US/UK PDF hashes rendered with a
   fixed `released_on`. It refuses a granted certificate (that release goes the normal way),
   and nothing here writes a certificate, a `PatternVersion` or a `certified` flag.
3. **Stamped everywhere.** `LABEL` is carried by the binding, every candidate's checks, the
   run's stage records, the approval card and the Command Center notification title.
4. **Never publication.** `refuse_if_experiment` is called first by `store.publish`,
   `publish.disclosed_listing.export_images`, `ops.publication_authority.approve`,
   `ops.activation_authority.approve` and `image_production.approve`. A candidate bound
   through an experiment is never `publishable`, whatever its judges say.

The experiment keeps every existing ceiling: the per-gallery spend plan, the gateway's
reservation and the monthly ceiling. Its own hard budget (`ExperimentBudget`) is in addition,
reserved before every paid call.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.resilience import PermanentError

LABEL = "EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION"
ACTION_OPENED = "experiment.opened"
ACTION_REFUSED = "experiment.publication_refused"
ACTOR = "experiment"
MAX_ATTEMPTS_PER_ROLE = 2            # owner rule for the experiment: at most 2 per FLUX role
OWNER_APPROVAL = ("owner-approved experiment 2026-10-19: Reading Nook Cable Wrap v0.1.0, "
                  "first end-to-end autonomous listing test, CA$5.00 total new paid usage, "
                  "no credit purchases, no publishing, SHADOW only")


class ExperimentRefused(PermanentError):
    """An experiment may not do this (wrong database, wrong content, or a publication path)."""


class ExperimentBudgetStop(ExperimentRefused):
    """The experiment's hard budget would be exceeded: nothing is sent."""


def is_scratch(db) -> bool:
    return bool(getattr(db, "scratch", False))


def require_scratch(db) -> None:
    if not is_scratch(db):
        raise ExperimentRefused(
            f"{LABEL}: an experiment runs only on a scratch database "
            f"(Database(..., scratch=True)); this one is not, so nothing is opened or run")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _artifact(slug: str, version: str) -> str:
    return f"{slug}@{version}"


# ---- opening ------------------------------------------------------------------------------

def open_experiment(db, *, cir, certification: dict, pdf_sha256: dict[str, str],
                    released_on: str, budget_cad: float, live: bool,
                    owner_approval: str = OWNER_APPROVAL, job_id: int | None = None) -> dict:
    """Record an experiment for this exact uncertified content. Idempotent per content."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..creative.pattern_refs import release_hash_of

    require_scratch(db)
    if certification.get("granted"):
        raise ExperimentRefused("the release is certified: it goes through the normal "
                                "orchestrator, never EXPERIMENT mode")
    reasons = list(certification.get("reasons") or [])
    if not reasons:
        raise ExperimentRefused("an experiment records why certification refused; no reason "
                                "was given, so the refusal is not on record")
    content = release_hash_of(cir)
    if certification.get("content_hash") != content:
        raise ExperimentRefused(
            f"the refused certificate examined content "
            f"{str(certification.get('content_hash'))[:12]}, not this CIR ({content[:12]})")
    if set(pdf_sha256) != {"US", "UK"} or not all(
            len(str(h)) == 64 for h in pdf_sha256.values()):
        raise ExperimentRefused("both uncertified PDFs (US and UK) must be rendered and hashed")
    if not released_on:
        raise ExperimentRefused("released_on must be fixed so the PDF bytes are reproducible")
    if not 0 < float(budget_cad) <= 5.00:
        raise ExperimentRefused(f"budget CA${budget_cad} is outside the owner-approved "
                                f"CA$0.01..5.00")
    art = _artifact(cir.slug, cir.version)
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION_OPENED,
                                                    AuditLog.artifact == art)):
            if (row.detail or {}).get("release") == content:
                return dict(row.detail)
        detail = {
            "label": LABEL, "experiment": True, "certified": False,
            "slug": cir.slug, "version": cir.version, "title": cir.title,
            "release": content, "cir_fingerprint": cir.fingerprint,
            "cir": cir.to_dict(),
            "certification": {"granted": False, "reasons": reasons[:10],
                              "content_hash": content,
                              "source": certification.get("source") or "gate.certify"},
            "pdf_sha256_by_terminology": dict(pdf_sha256), "released_on": str(released_on),
            "budget_cad": round(float(budget_cad), 2), "live": bool(live),
            "max_attempts_per_role": MAX_ATTEMPTS_PER_ROLE,
            "owner_approval": owner_approval, "opened_at": _now().isoformat(),
        }
        s.add(AuditLog(actor=ACTOR, action=ACTION_OPENED, artifact=art, job_id=job_id,
                       detail=detail))
    return detail


def _opened(db, slug: str, version: str) -> list[dict]:
    """Every experiment opened for slug@version on this database (any database)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    try:
        with db.session() as s:
            return [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
                AuditLog.action == ACTION_OPENED,
                AuditLog.artifact == _artifact(slug, version)))]
    except Exception:  # noqa: BLE001 - no audit table is no experiment
        return []


def registration(db, slug: str, version: str, release: str | None = None) -> dict | None:
    """The experiment for slug@version (and release, when given), on a scratch database only."""
    if not is_scratch(db):
        return None
    rows = _opened(db, slug, version)
    if release:
        rel = str(release).strip().lower()
        rows = [r for r in rows if len(rel) >= 12 and str(r.get("release", "")).startswith(rel)]
    return rows[-1] if rows else None


def is_experiment(db, slug: str, version: str) -> bool:
    return bool(_opened(db, slug, version))


def refuse_if_experiment(db, slug: str | None, version: str | None, *, action: str) -> None:
    """The publication paths call this first. An experiment never reaches them."""
    if not slug:
        return
    rows = _opened(db, slug, version or "") if version else []
    if not rows and not version:
        from sqlalchemy import select

        from ..core.models import AuditLog

        try:
            with db.session() as s:
                rows = [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
                    AuditLog.action == ACTION_OPENED,
                    AuditLog.artifact.like(f"{slug}@%")))]
        except Exception:  # noqa: BLE001
            rows = []
    if not rows:
        return
    why = (f"{LABEL}: {slug}@{version or '?'} is an uncertified experiment "
           f"(release {str(rows[-1].get('release'))[:12]}); {action} is refused")
    try:
        from ..core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor=ACTOR, action=ACTION_REFUSED,
                           artifact=_artifact(slug, version or "?"),
                           detail={"label": LABEL, "action": action, "why": why}))
    except Exception:  # noqa: BLE001 - the refusal stands even if it cannot be recorded
        pass
    raise ExperimentRefused(why)


def cir_of(reg: dict):
    from ..cir.model import CIR
    from ..creative.pattern_refs import release_hash_of

    cir = CIR.from_dict(reg["cir"])
    if release_hash_of(cir) != reg["release"]:
        raise ExperimentRefused("the stored experiment CIR no longer hashes to its release")
    return cir


def cir_loader(db):
    """For `Flux3Generator(cir_loader=...)`: the experiment's own CIR, never a certified one."""
    def load(slug: str, version: str):
        reg = registration(db, slug, version)
        if reg is None:
            raise ExperimentRefused(f"{slug}@{version}: no experiment is open on this scratch "
                                    f"database")
        return cir_of(reg)
    return load


# ---- binding, plan and the gate hooks the orchestrator calls --------------------------------

def binding(db, slug: str, version: str, release: str) -> dict | None:
    """The candidate-gate binding for an experiment run, or None when this is not one.

    PASS means the bytes are bound to this exact uncertified content and its uncertified PDF
    hashes: content identity, nothing more. `certified` is False and the label says so; the
    publication verdict always refuses (`publication_blockers`)."""
    reg = registration(db, slug, version, release)
    if reg is None:
        return None
    try:
        cir = cir_of(reg)
        pieces = int(sum(int(getattr(c, "make", 1) or 1) for c in cir.components))
    except Exception:  # noqa: BLE001
        pieces = None
    return {"status": "PASS",
            "why": (f"{LABEL}: bound to the UNCERTIFIED content {reg['release'][:12]} and its "
                    f"uncertified US/UK PDF hashes; certification REFUSED: "
                    f"{'; '.join(reg['certification']['reasons'])[:300]}"),
            "experiment": True, "certified": False, "label": LABEL,
            "release_hash": reg["release"],
            "pdf_sha256_by_terminology": dict(reg["pdf_sha256_by_terminology"]),
            "cir_fingerprint": reg.get("cir_fingerprint"), "pieces": pieces}


def publication_blockers(bind: dict) -> list[str]:
    if not (bind or {}).get("experiment"):
        return []
    return [f"{LABEL}: the product is uncertified (certification refused); an experiment "
            f"image is never publishable, exportable or approvable for a listing"]


# The seven roles, adapted to a wearable (owner brief). Roles 1 and 4 are FLUX lifestyle
# images; role 2 is the orchestrator's product-only anchor; 3, 5, 6, 7 are deterministic.
ROLE_HERO, ROLE_BACK = "lifestyle", "angle"
GALLERY = (
    (1, "hero", ROLE_HERO, "flux"),
    (2, "product_flat_lay", "product_anchor", "flux"),
    (3, "cable_texture_closeup", "detail", "deterministic:disclosed_render.detail"),
    (4, "laura_back_drape", ROLE_BACK, "flux"),
    (5, "size_fit", "size", "deterministic:disclosed_render.scale"),
    (6, "materials_construction", "materials", "deterministic:gallery_frames.MATERIALS"),
    (7, "digital_download_contents", "whats_included", "deterministic:contents_frame"),
)
HERO_BRIEF = ("hero: Laura standing in a warm reading nook, wearing the wrap draped over both "
              "shoulders with the long ends hanging evenly down the front, front view, "
              "three-quarter length, the cable columns and plain cream end bands visible")
BACK_BRIEF = ("second Laura image: Laura seen from behind, three-quarter back view, the wrap "
              "over her shoulders so its full width drapes down her back and the cable "
              "columns run vertically; a different pose from the hero")


def plan(reg: dict) -> dict:
    """The orchestrator plan for an experiment run (`image_production` campaign format)."""
    from ..publish import eligibility as el
    from . import shot_plans as SP

    def det(position, role, job, medium, purpose, why):
        return {"position": position, "role": role, "job": job, "why": why,
                "required_by": list(SP.REQUIRED_BY[job]),
                "sources": {SP.DISCLOSED: SP.SATISFIES, SP.GENERATED: SP.PURPOSE_REFUSED,
                            SP.PHOTO: SP.PURPOSE_REFUSED},
                "preferred_source": SP.DISCLOSED, "disclosed_medium": (medium, purpose),
                "conditional": False, "laura": False, "generate": False,
                "campaign_role": role, "fallback": SP.DISCLOSED, "brief": ""}

    def gen(position, role, job, brief, why):
        return {"position": position, "role": role, "job": job, "why": why,
                "required_by": list(SP.REQUIRED_BY[job]),
                "sources": {SP.DISCLOSED: SP.NOT_DRAWABLE, SP.GENERATED: SP.BLOCKED_F852,
                            SP.PHOTO: SP.SATISFIES},
                "preferred_source": SP.GENERATED, "disclosed_medium": (None, None),
                "conditional": False, "laura": True, "generate": True,
                "campaign_role": role, "fallback": None, "brief": brief}

    roles = [
        gen(1, ROLE_HERO, el.LIFESTYLE, HERO_BRIEF, "hero: Laura wearing the wrap (FLUX)"),
        det(3, "detail", el.DETAIL, "DIGITAL_TWIN_RENDER", el.ENGINEERING_EVIDENCE,
            "cable/texture close-up: deterministic, because a generated close-up of the "
            "cable cannot be verified stitch by stitch"),
        gen(4, ROLE_BACK, el.ANGLE, BACK_BRIEF, "second Laura image: back view, drape (FLUX)"),
        det(5, "size", el.SCALE, "DIGITAL_TWIN_RENDER", el.CUSTOMER_INFORMATION,
            "size/fit: deterministic only (computed dimensions; no measured sample)"),
        det(6, "materials", el.MATERIALS, "INFOGRAPHIC", el.CUSTOMER_INFORMATION,
            "materials/construction: deterministic"),
        det(7, "whats_included", el.CONTENTS, "PATTERN_PREVIEW", el.CUSTOMER_INFORMATION,
            "digital download contents: deterministic, from the uncertified PDFs"),
    ]
    return {"listing": reg["slug"], "category": "wrap", "experiment": True, "label": LABEL,
            "roles": roles, "image_count": 7, "one_outfit": True, "laura_in_campaign": True,
            "anchor_position": 2,
            "ruling_conflicts": [
                "the owner's experiment brief puts a generated Laura image at position 1; "
                "ASSET_CONCEPT_AS_HERO and F-852 keep a generated image out of a published "
                "hero, which is moot here because nothing in an experiment publishes"]}


@dataclass
class ExperimentBudget:
    """A hard cap, reserved before every paid call and settled after it. In memory."""

    cap_cad: float
    reserved_cad: float = 0.0
    spent_cad: float = 0.0
    entries: list[dict] = field(default_factory=list)

    def headroom(self) -> float:
        return round(self.cap_cad - self.spent_cad - self.reserved_cad, 6)

    def reserve(self, amount_cad: float, *, what: str) -> int:
        amount = round(float(amount_cad), 6)
        if amount <= 0:
            raise ExperimentBudgetStop(f"{what}: an unpriced call is an unbounded one")
        if amount > self.headroom():
            raise ExperimentBudgetStop(
                f"{what}: CA${amount:.4f} would exceed the experiment's hard cap "
                f"(CA${self.cap_cad:.2f}; spent {self.spent_cad:.4f}, reserved "
                f"{self.reserved_cad:.4f}); nothing is sent")
        self.reserved_cad = round(self.reserved_cad + amount, 6)
        self.entries.append({"what": what, "reserved_cad": amount, "at": _now().isoformat(),
                             "settled_cad": None})
        return len(self.entries) - 1

    def settle(self, rid: int, actual_cad: float | None) -> None:
        e = self.entries[rid]
        if e["settled_cad"] is not None:
            return
        # An unknown actual is billed at the reservation: never zero.
        actual = e["reserved_cad"] if actual_cad is None else round(float(actual_cad), 6)
        self.reserved_cad = round(self.reserved_cad - e["reserved_cad"], 6)
        self.spent_cad = round(self.spent_cad + actual, 6)
        e["settled_cad"] = actual
        e["settled_at"] = _now().isoformat()

    def to_dict(self) -> dict:
        return {"cap_cad": self.cap_cad, "spent_cad": round(self.spent_cad, 4),
                "reserved_cad": round(self.reserved_cad, 4),
                "headroom_cad": round(self.headroom(), 4), "entries": list(self.entries)}


@dataclass
class Context:
    """What `image_production.run_stage` needs for an experiment run."""

    reg: dict
    plan: dict
    judges_factory: object = None
    generator_factory: object = None
    budget: ExperimentBudget | None = None
    gallery_builder: object = None
    outfit_selector: object = None
    outfit_rejects: object = None          # (outfit view) -> bool: the brief excludes it
    max_attempts_per_role: int = MAX_ATTEMPTS_PER_ROLE

    @property
    def label(self) -> str:
        return LABEL

    def judges(self, db):
        if self.judges_factory is None:
            raise ExperimentRefused("an experiment names its judges (stub in a dry run, the "
                                    "live judges otherwise); none was registered")
        return self.judges_factory(db)

    def generator(self, db):
        if self.generator_factory is None:
            raise ExperimentRefused("an experiment names its generator (the stub provider in "
                                    "a dry run, FLUX 3 when live); none was registered")
        return self.generator_factory(db)

    def paid_authorised(self) -> bool:
        """The owner's experiment approval stands in for the image_generation gate, for this
        live experiment only and within its budget."""
        return bool(self.reg.get("live")) and self.budget is not None

    def guard_paid(self, cost_cad: float) -> None:
        if self.budget is None:
            raise ExperimentBudgetStop("no experiment budget: no paid call")
        if float(cost_cad) > self.budget.headroom():
            raise ExperimentBudgetStop(
                f"next call CA${float(cost_cad):.4f} exceeds the experiment headroom "
                f"CA${self.budget.headroom():.4f}")


_CONTEXTS: dict[str, Context] = {}


def install(db, reg: dict, **kw) -> Context:
    """Make an experiment runnable by the orchestrator in this process."""
    require_scratch(db)
    ctx = Context(reg=reg, plan=plan(reg), **kw)
    _CONTEXTS[_key(reg["slug"], reg["version"], reg["release"])] = ctx
    return ctx


def uninstall(reg: dict) -> None:
    _CONTEXTS.pop(_key(reg["slug"], reg["version"], reg["release"]), None)


def _key(slug, version, release) -> str:
    return f"{slug}@{version}@{release}"


def context_for(db, slug: str, version: str, release: str) -> Context:
    """The installed context for an experiment run, or a refusal (never a silent fallback)."""
    require_scratch(db)
    reg = registration(db, slug, version, release)
    if reg is None:
        raise ExperimentRefused(f"{slug}@{version}: no experiment is open for release "
                                f"{str(release)[:12]} on this scratch database")
    ctx = _CONTEXTS.get(_key(slug, version, reg["release"]))
    if ctx is None:
        raise ExperimentRefused("the experiment is open but not installed in this process "
                                "(judges and budget unknown); refused rather than defaulted")
    return ctx


def stamp_record(record: dict) -> dict:
    return {"experiment": True, "label": LABEL, **record}


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
