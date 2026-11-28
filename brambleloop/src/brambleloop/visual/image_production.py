"""Autonomous listing-image production: an event-driven, resumable workflow (W-OWNERIMG).

The owner redirected on 2026-10-19: autonomous production is the primary architecture, and
an owner upload is only an optional fallback. Both paths share one set of gates
(`visual.candidate_gates.evaluate`), and no criterion differs by method.

**Engine.** There is no new engine. Each stage is one execution of the job type
`visual.image_production` on the durable `JobQueue`, run by the `publishing` agent. That
gives the stage the agent's permission, its CA$2.00/day ceiling and the queue's lease,
retry, dead-letter and checkpoint semantics. The workflow works like this:

* A stage stores its inputs, outputs, evidence and cost on the run row
  (`image_records.ImageProductionRun`).
* It then enqueues the next stage with the idempotency key
  `imgprod:<slug>@<version>@<release>:<stage>[:<round>]`. A duplicate event therefore
  becomes a deduplicated job, never a second gallery.
* **Trigger:** the `assets.build` handler calls `trigger` once its certified release has
  produced a usable disclosed render set.

**Stages** (see `STAGES`):

1. retrieve the certified release and its PDF hash;
2. prepare references (generator interface);
3. generate the product-only candidate;
4. gate on fidelity;
5. load Laura's references;
6. reserve an outfit;
7. generate the lifestyle candidate;
8. generate the remaining shot-plan roles;
9. run the independent checks;
10. bounded repair;
11. assemble the gallery;
12. make the owner approval card.

**Generators.** W-FLUXAPI owns the provider adapter, multi-reference transmission, the
deterministic pattern-reference generator and the stage generation functions, with their
receipts and costs. This module calls them only through the `Generator` interface. Until
that branch registers one, `resolve_generator` returns None and a run stops at
`blocked(no image generator is wired)`. That is a status, not a notification. Tests inject a
stub.

**Budget.** The bounds are:

* `MAX_ATTEMPTS_PER_ROLE`, `MAX_GENERATION_CALLS` and `MAX_REPAIR_ROUNDS`;
* a per-gallery `visual.spend_plan` whose `guard` runs before every call;
* the `image_generation` gate, which must be open before any paid generator is called.

The adapter's own `gateway.images.reserve_render` (W-FLUXAPI) still applies on top.
Nothing loops: every repeat is a new, counted, idempotency-keyed job.

**Notifications.** There are two triggers, and nothing else notifies:

* `ready_for_owner_review`;
* `blocked` after the permitted attempts.

`notification_candidates` feeds the existing deduplicated owner-notification refresh
(`app.command_center.notifications.candidates`).

**Learning.** Every candidate row records its outcome, its failure categories, cost and
latency. `learning_summary` reports cost per accepted image, which is undefined (None) when
nothing has been accepted. Brief changes are adopted only as promoted `improve.league`
prompt versions (`PROMPT_KEY`). Nothing here relaxes a gate.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Protocol

from . import candidate_gates as CG
from . import outfits
from . import shot_plans as SP

JOB_TYPE = "visual.image_production"
AGENT = "publishing"
PROMPT_KEY = "image_production:briefs"

# (stage, Command Center state while it runs)
STAGES: tuple[tuple[str, str], ...] = (
    ("retrieve_release", "reference_preparation"),
    ("prepare_references", "reference_preparation"),
    ("product_generation", "product_generation"),
    ("fidelity_gate", "product_generation"),
    ("load_laura_references", "lifestyle_generation"),
    ("reserve_outfit", "lifestyle_generation"),
    # W-VISNEXT2, stage A of the owner's manual method: Laura alone in the listing's outfit,
    # judged, then reused as identity context for every Laura frame of the listing.
    ("identity_anchor", "lifestyle_generation"),
    ("lifestyle_generation", "lifestyle_generation"),
    ("remaining_roles", "lifestyle_generation"),
    ("verification", "automated_verification"),
    ("repair", "automated_verification"),
    ("gallery_assembly", "gallery_assembly"),
    ("owner_card", "ready_for_owner_review"),
)
STAGE_STATE = dict(STAGES)
# D-OWNER-SPEND-ORDER (ENG-SALE-PIPELINE): `awaiting_pre_image_readiness` is the non-spending
# wait of a run whose release is not (yet) admitted for sale by `publish.sale_pipeline`.
AWAITING_PRE_IMAGE = "awaiting_pre_image_readiness"
STATES = ("awaiting_certified_pattern", AWAITING_PRE_IMAGE, "reference_preparation",
          "product_generation", "lifestyle_generation", "gallery_assembly",
          "automated_verification", "ready_for_owner_review", "blocked",
          "approved_for_publication", "waiting_for_sale_admission")
# The stages that can call a generator (and so spend); none runs for an unadmitted release.
SPENDING_STAGES = ("prepare_references", "product_generation", "identity_anchor",
                   "lifestyle_generation", "remaining_roles", "repair")
NOTIFY_STATES = ("ready_for_owner_review", "blocked")

MAX_ATTEMPTS_PER_ROLE = 3          # one generation + two repairs
MAX_REPAIR_ROUNDS = 2
# D-OWNER-PHOTO-BUDGET (owner, 2026-11-28: "up the photo budget i dont care. Get it right."):
# the per-gallery plan is three times the D-OWNER-FLUX-GALLERY one -- CA$2.00 -> CA$6.00, calls
# 12 -> 36 (20 -> 60 on the ~gallery route). The FLUX activation's daily ceiling (CA$10), its
# monthly ceiling (CA$40) and the company's CA$100/month cap still bind on top.
PHOTO_BUDGET_FACTOR = 3
PLAN_VERSION_TAG = "gallery-plan/2"   # /1: CA$2.00, 12/20 calls (D-OWNER-FLUX-GALLERY)
MAX_GENERATION_CALLS = 12 * PHOTO_BUDGET_FACTOR   # per gallery, every role and repair included
MAX_SPEND_CAD_PER_GALLERY = 6.00   # the code maximum; the owner may lower it (gallery_budget)
ANCHOR_ROLE = "product_anchor"     # the product-only candidate: a fidelity anchor, not a frame
# IMAGE-AD (V2): a vessel's anchor is a pair. This is its side view, standing, rendered by
# `image_stages.product_only(view="side")` as its own paid call before the top-down anchor;
# its bytes ride on the anchor (`side_data`) and its id in the anchor's checks
# (`_anchor_side`), so recovery and re-verification read the same pair. Never a frame.
ANCHOR_SIDE_ROLE = "product_anchor_side"
IDENTITY_ANCHOR_ROLE = "laura_identity_anchor"   # stage A: an intermediate reference, not a frame
MAX_IDENTITY_ANCHOR_ATTEMPTS = 2   # one generation + one bounded proportion-correction pass
MAX_RESTARTS = 3                   # per run and generation-method version (D-RESTART-PER-
#                                    METHOD); a restart never resets attempts, calls or spend
RESTART_CAP_CODE = "max_restarts"  # `restartable`'s refusal code when MAX_RESTARTS binds
# ENG-IMAGES-LAURA: the owner's two-step method. Step 1 makes and accepts the product frame
# (the fidelity-gated anchor); step 2 conditions every Laura frame on that accepted frame plus
# Laura's canonical identity images, and nothing else. Used when the generator declares it.
OWNER_METHOD = "owner_two_step/1"
PRODUCT_FRAME_LABEL = "accepted_product_frame"
# ENG-MANUAL-METHOD (`creative.manual_method.MANUAL_METHOD`, kept equal by a test): part of the
# generation-method version, and the labels of the prior candidates it hands the generator.
MANUAL_METHOD_VERSION = "manual_method/1"
CORRECTION_LABEL = "correction_base"
PRODUCT_SIDE_LABEL = "accepted_product_side"
CAMPAIGN_LABEL = "campaign_reference"
RESTART_KEY = "_restart"           # the run's restart record inside `stages`
# ENG-IMAGE-METHOD-REDRIVE: every generated candidate carries the generation method it was made
# under (`generation_method`), by stable identifiers. A candidate with no stamp was made
# before stamps existed and reads as PRE_METHOD: stored provenance does not carry the
# pattern-reference version, so the current method cannot be proven for it.
METHOD_KEY = "_generation_method"
PRE_METHOD = "pre-method"
METHOD_REDRIVE_BY = "method_redrive"
METHOD_REDRIVE_KEY = "_method_redrive"          # the run's last method-redrive readback
# The fixed vocabulary of the method redrive (codes and sweep evidence). Never free text.
METHOD_REDRIVE_NO_HEADROOM = "method_redrive:no_headroom"
METHOD_REDRIVE_ALREADY = "method_redrive:already_redriven"
METHOD_REDRIVE_CURRENT = "method_redrive:failed_under_current_method"
# 19i29: the generation provider's own daily ceiling cannot cover one attempt today (FLUX
# CA$5.00/day): the sweep waits for the UTC day rather than spend the new method's first
# restart on a call the ceiling refuses. Day-scoped; the ceiling itself is never raised.
METHOD_REDRIVE_WAIT_DAILY = "method_redrive:generation_daily_ceiling"
# 19i29: another run of the same release is being re-judged (a free re-read of stored frames);
# the method redrive (a paid regeneration) waits for it to finish.
METHOD_REDRIVE_SIBLING = "method_redrive:sibling_rejudging"
METHOD_REDRIVE_EVIDENCE = ("eligible", "done", "no_headroom")


class Generator(Protocol):
    """What W-FLUXAPI's stage functions provide. `paid` providers need the gate open."""

    name: str
    paid: bool

    def prepare_references(self, *, slug: str, version: str, release: str,
                           cir_fingerprint: str | None) -> list[dict]:
        """[{"kind": one of candidate_gates.REFERENCE_KINDS, "data": bytes}]"""

    def generate(self, *, stage: str, role: str, brief: str, references: list[dict],
                 outfit: dict | None, attempt: int, repair: dict | None = None) -> dict:
        """{"data": bytes, "provider", "model", "prompt", "cost_cad", "latency_s",
        "identity_evidence" (optional; the conditioning receipt / judge readings)}"""


_GENERATORS: dict[str, object] = {}


def register_generator(name: str, factory) -> None:
    """W-FLUXAPI registers its stage functions here; nothing is registered in this branch."""
    _GENERATORS[name] = factory


def resolve_generator(db):
    """The registered generator. The FLUX 3 stages (W-FLUXAPI) register themselves on
    first use. A paid generator is still refused while the image_generation gate is closed."""
    if not _GENERATORS:
        try:
            from ..creative import flux3_generator

            flux3_generator.register(register_generator)
        except ImportError:
            return None
    names = sorted(_GENERATORS)
    if len(names) > 1:
        # F-739 (W4-C08): with a choice, on-model work goes to the best demonstrated
        # configuration (`provider_routing.route`), not to whichever name sorts first.
        from . import provider_routing

        gens = {n: _GENERATORS[n](db) for n in names}
        prov = {n: str(getattr(g, "provider", None) or n) for n, g in gens.items()}
        by_provider = {p: n for n, p in reversed(list(prov.items()))}
        pick = provider_routing.route(db, available=sorted(by_provider),
                                      default=prov[names[0]])
        return gens[by_provider.get(pick["provider"], names[0])]
    for _name, factory in sorted(_GENERATORS.items()):
        return factory(db)
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


ROUTE_SUFFIX = "~gallery"   # D-OWNER-FLUX-GALLERY: the generated-gallery run of a release


def run_key(slug: str, version: str, release: str, ns: str = "", route: str = "") -> str:
    """The run's identity. `ns` (W-VISNEXT2) separates a controlled-experiment run of a
    certified release from the release's ordinary production run, which it never touches.
    `route` (D-OWNER-FLUX-GALLERY) gives the seven-frame FLUX campaign its own run, beside the
    release's campaign run, with its own attempts, calls and spend."""
    return (f"imgprod:{slug}@{version}@{release}" + (ROUTE_SUFFIX if route else "")
            + (f"#{ns}" if ns else ""))


def route_of_key(key: str) -> str:
    return SP.FLUX_ROUTE if ROUTE_SUFFIX in str(key or "").split("#")[0] else ""


def stage_key(slug: str, version: str, release: str, stage: str, round_: int = 0,
              epoch: int = 0, ns: str = "", route: str = "") -> str:
    """A stage job's idempotency key. `epoch` > 0 only after a restart (W-VISNEXT), so a
    restarted run's jobs never collide with the ones its first pass already ran."""
    return (run_key(slug, version, release, ns, route) + f":{stage}"
            + (f":{round_}" if round_ else "") + (f":e{epoch}" if epoch else ""))


def prompt_version(db) -> str:
    try:
        from ..improve.league import incumbent_payload

        inc = incumbent_payload(db, kind="prompt", key=PROMPT_KEY)
        if inc:
            return f"league:{inc['config_id']}:{inc['version']}"
    except Exception:  # noqa: BLE001 - an unreadable registry falls back to the code default
        pass
    blob = json.dumps(SP.LIFESTYLE_BRIEF, sort_keys=True).encode()
    return f"code-default:{hashlib.sha256(blob).hexdigest()[:12]}"


# ---- trigger -----------------------------------------------------------------------------

def trigger(enqueue, *, slug: str, version: str, release: str, ns: str = "",
            controlled_run_id: int | None = None, route: str = "") -> dict:
    """Enqueue the workflow once per slug@version@release. `enqueue(inputs, key)` returns
    None on a duplicate key (JobContext.enqueue semantics). `ns` and `controlled_run_id`
    (W-VISNEXT2) start an owner-authorised controlled-experiment run of a certified release:
    its own run row, the authorization's caps in place of the image_generation gate, and an
    EXPERIMENT label on everything it makes."""
    if not (slug and version and release):
        return {"enqueued": False, "why": "slug, version and release are all required"}
    if bool(ns) != bool(controlled_run_id):
        return {"enqueued": False, "why": "a namespaced run is a controlled run, and back"}
    inputs = {"slug": slug, "version": version, "release": release,
              "stage": STAGES[0][0], "round": 0}
    if ns:
        inputs.update(ns=ns, controlled_run_id=int(controlled_run_id))
    if route:
        # D-OWNER-FLUX-GALLERY: the seven-frame FLUX campaign (shot_plans.flux_campaign_plan)
        if route != SP.FLUX_ROUTE:
            return {"enqueued": False, "why": f"unknown gallery route {route!r}"}
        inputs["route"] = route
    job = enqueue(inputs, stage_key(slug, version, release, STAGES[0][0], ns=ns, route=route))
    return {"enqueued": job is not None, "run_key": run_key(slug, version, release, ns, route)}


# ---- for-sale admission (b17-c A3, D-OWNER-SPEND-ORDER) ----------------------------------
#
# The FLUX gallery is paid. It was enqueued at build time, before pricing, listing copy or any
# non-image listing gate had run, so once `image_generation` opened every certified release
# would have bought seven images -- including releases later rejected or parked. Now:
#   * nothing at build time enqueues the FLUX route (runtime/release.py);
#   * the for-sale admission point is the `listing.package` job, which runs after the whole
#     listing chain and calls `admit_for_sale` -- the route is enqueued only when every
#     NON-image listing gate is PASS (the recorded package's only blockers are image ones);
#   * every stage of a FLUX run re-checks admission before it does anything; a product that
#     is not (or no longer) eligible parks in the non-spending `SALE_WAITING` state, and its
#     unused outfit reservation is released.
SALE_WAITING = "waiting_for_sale_admission"
STOPPED_STAGES = ("REJECTED", "RETIRED", "ROLLED_BACK")
_SALE_WAITS = "_sale_waits"


def sale_admission(db, slug: str, version: str, release: str) -> dict:
    """Whether `slug@version@release` is selected for sale: the product is not rejected or
    withdrawn, and the recorded listing package for exactly this release has no blocker other
    than its images and the allow-listed publish-time gates (D-MAIN-IMAGE-ADMISSION), which
    still block publishing. Anything unreadable is not admitted (unknown never admits)."""
    def no(why: str, **kw) -> dict:
        return {"admitted": False, "why": why, **kw}

    if not (slug and version and release):
        return no("slug, version and release are all required")
    try:
        from ..products import lifecycle

        stage = str((lifecycle.derive(db, slug) or {}).get("stage") or "")
    except Exception as exc:  # noqa: BLE001 - an unreadable lifecycle is not for sale
        return no(f"product lifecycle unreadable ({type(exc).__name__})")
    if stage in STOPPED_STAGES:
        return no(f"product is {stage}", rejected=True, lifecycle=stage)
    try:
        from ..publish import listing_package

        pkg = listing_package.latest(db, slug, version)
    except Exception as exc:  # noqa: BLE001
        return no(f"listing package unreadable ({type(exc).__name__})")
    if not pkg:
        return no("no listing package is recorded: pricing, listing copy and the listing "
                  "gates have not all run")
    if pkg.get("release_hash") != release:
        return no(f"the recorded listing package is for release "
                  f"{str(pkg.get('release_hash') or '')[:12]}, not {release[:12]}")
    blockers = pkg.get("blockers")
    if not isinstance(blockers, list):
        return no("listing package blockers unreadable")
    other = [b for b in blockers if not _admissible_blocker(b)]
    if other:
        return no(f"{len(other)} non-image listing gate(s) not PASS: "
                  + "; ".join(str((b or {}).get("why") if isinstance(b, dict) else b)[:120]
                              for b in other[:3]),
                  non_image_blockers=other[:10])
    publish_time = sorted({b["publish_time"] for b in blockers if not b.get("image") is True})
    return {"admitted": True,
            "why": ("every non-image listing gate is PASS" if not publish_time else
                    "every non-image listing gate is PASS except the publish-time gate(s) "
                    f"{', '.join(publish_time)}, which still block publishing"),
            "image_blockers": sum(1 for b in blockers if b.get("image") is True),
            "publish_time_blockers": publish_time, "lifecycle": stage}


def _admissible_blocker(b) -> bool:
    """A listing-package blocker that does not stop admission for images: one the images
    cause (`image: True`), or one from an allow-listed publish-time / store-wide gate
    (D-MAIN-IMAGE-ADMISSION; `release_gates.PUBLISH_TIME_AREAS`). Both still block
    publishing. Anything else -- including a blocker that cannot be attributed -- is a
    non-image blocker and never admits."""
    if not isinstance(b, dict):
        return False
    if b.get("image") is True:
        return True
    from ..publish.release_gates import PUBLISH_TIME_AREAS

    area = b.get("publish_time")
    return (b.get("source") == "release_gates.for_publish" and isinstance(area, str)
            and area in PUBLISH_TIME_AREAS)


def _park_for_sale(db, key: str, stage: str, adm: dict) -> dict:
    """Park a FLUX run that is not admitted: no spend, its unused outfit reservation freed."""
    from sqlalchemy.orm.attributes import flag_modified

    run = get_run(db, key) or {}
    freed = None
    listing = run.get("listing") or ""
    if listing:
        held = outfits.reserved_for(db, listing)
        if held:
            freed = outfits.release(db, held["outfit_id"], listing,
                                    why=f"image run parked: {adm['why']}"[:300])
    with db.session() as s:
        r = _run_locked(s, key)
        st = dict(r.stages or {})
        waits = dict(st.get(_SALE_WAITS) or {})
        # IMAGE-AD: a run re-entered by `_readmit` that parks again is a NEW wait, even though
        # its status never left SALE_WAITING (readmission does not change it). Before this the
        # count stayed put, the next readmission reused the taken "#admitted<n>" key, and an
        # admitted release waited forever (found on the bread basket, whose listing is
        # re-drafted once after its first package).
        # Only the FLUX gallery route (D-OWNER-SPEND-ORDER's one gallery per for-sale
        # product): re-entering the campaign route as well would buy a second gallery.
        if r.status != SALE_WAITING or (
                route_of_key(key) == SP.FLUX_ROUTE
                and waits.get("readmitted") is not None
                and int(waits.get("readmitted") or 0) == int(waits.get("count") or 0)):
            waits["count"] = int(waits.get("count") or 0) + 1
        waits.update(at=_now().isoformat(), why=str(adm.get("why"))[:500], stage=stage)
        st[_SALE_WAITS] = waits
        r.stages = st
        flag_modified(r, "stages")
        r.status, r.blocked_reason, r.updated_at = SALE_WAITING, "", _now()
    return {"run_key": key, "waiting": True, "admission": adm, "outfit_released": freed}


def admit_for_sale(db, enqueue, *, slug: str, version: str, release: str) -> dict:
    """The for-sale admission point (called by `listing.package`): enqueue the FLUX gallery
    route for this release only when `sale_admission` admits it. A run already parked in
    SALE_WAITING is re-entered once per wait; a running or finished run is left alone. A
    product that is not admitted has any existing FLUX run parked (and its reservation freed)."""
    adm = sale_admission(db, slug, version, release)
    key = run_key(slug, version, release, route=SP.FLUX_ROUTE)
    run = get_run(db, key)
    if not adm["admitted"]:
        if run is not None and run["state"] not in (
                SALE_WAITING, "blocked", "ready_for_owner_review", "approved_for_publication"):
            _park_for_sale(db, key, run["stage"] or STAGES[0][0], adm)
        return {"enqueued": False, "admission": adm, "run_key": key}
    # A campaign-route run parked for the same reason (paid generator) resumes too.
    readmitted = [_readmit(db, enqueue, run_key(slug, version, release), slug, version,
                           release, "")]
    if run is None:
        return {**trigger(enqueue, slug=slug, version=version, release=release,
                          route=SP.FLUX_ROUTE), "admission": adm}
    if run["state"] != SALE_WAITING:
        return {"enqueued": False, "admission": adm, "run_key": key,
                "why": f"run is already {run['status']}"}
    readmitted.append(_readmit(db, enqueue, key, slug, version, release, SP.FLUX_ROUTE))
    return {"enqueued": bool(readmitted[-1]), "admission": adm, "run_key": key,
            "readmitted": True}


def _readmit(db, enqueue, key: str, slug: str, version: str, release: str,
             route: str) -> bool:
    """Re-enter a run parked in SALE_WAITING at its first stage, once per wait."""
    run = get_run(db, key)
    if run is None or run["state"] != SALE_WAITING:
        return False
    waits = int((_stage_data(db, key).get(_SALE_WAITS) or {}).get("count") or 0)
    inputs = {"slug": slug, "version": version, "release": release,
              "stage": STAGES[0][0], "round": 0}
    if route:
        inputs["route"] = route
    if run.get("restarts"):
        inputs["epoch"] = run["restarts"]
    job = enqueue(inputs, stage_key(slug, version, release, STAGES[0][0], 0,
                                    run.get("restarts") or 0, "", route)
                  + f"#admitted{waits}")
    if job is not None:
        from sqlalchemy.orm.attributes import flag_modified

        with db.session() as s:
            r = _run_locked(s, key)
            st = dict(r.stages or {})
            w = dict(st.get(_SALE_WAITS) or {})
            w["readmitted"] = waits
            st[_SALE_WAITS] = w
            r.stages = st
            flag_modified(r, "stages")
    return job is not None


# ---- run row -----------------------------------------------------------------------------

def _run(s, key: str):
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    return s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))


def _run_locked(s, key: str):
    """Serialize cooperating mutations of the run row on PostgreSQL."""
    from sqlalchemy import select
    from .image_records import ImageProductionRun

    return s.scalar(select(ImageProductionRun).where(
        ImageProductionRun.run_key == key).with_for_update())


def _ensure_run(db, slug, version, release, ns: str = "", route: str = ""):
    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    key = run_key(slug, version, release, ns, route)
    with db.session() as s:
        existing = _run(s, key)
        if existing is None:
            s.add(ImageProductionRun(run_key=key, slug=slug, version=version, release=release,
                                     listing=outfits.listing_of(slug), stages={}))
        elif (existing.slug, existing.version, existing.release) != (slug, version, release):
            raise ValueError("visual run key collides with another product or release")
    return key


def _update(db, key: str, *, stage: str, status: str | None = None, record: dict | None = None,
            blocked: str = "", exhausted: bool = False, **fields) -> dict:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        r = _run_locked(s, key)
        r.stage = stage
        if record is not None:
            st = dict(r.stages or {})
            st[stage] = {**record, "at": _now().isoformat()}
            r.stages = st
            flag_modified(r, "stages")
        if blocked:
            r.status, r.blocked_reason, r.attempts_exhausted = "blocked", blocked[:2000], exhausted
        elif status:
            r.status, r.blocked_reason = status, ""
        for k, v in fields.items():
            setattr(r, k, v)
            if isinstance(v, (dict, list)):
                flag_modified(r, k)
        r.updated_at = _now()
        return _run_view(r)


def _run_view(r) -> dict:
    status = r.status if r.status != "blocked" else f"blocked({r.blocked_reason})"
    return {"run_key": r.run_key, "slug": r.slug, "version": r.version, "release": r.release,
            "listing": r.listing, "stage": r.stage, "state": r.status, "status": status,
            "blocked_reason": r.blocked_reason or None,
            "attempts_exhausted": bool(r.attempts_exhausted),
            "generation_calls": r.generation_calls, "spent_cad": round(r.spent_cad or 0.0, 4),
            "outfit_id": r.outfit_id or None, "card": dict(r.card or {}),
            "owner_decision": dict(r.owner_decision or {}),
            "restarts": int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0),
            "method_redrive": dict((r.stages or {}).get(METHOD_REDRIVE_KEY) or {}),
            "stages": sorted((k for k in (r.stages or {}) if not k.startswith("_")),
                             key=lambda k: [s for s, _ in STAGES].index(k)
                             if k in STAGE_STATE else 99),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def get_run(db, key: str) -> dict | None:
    from .image_records import ensure_tables

    ensure_tables(db)
    with db.session() as s:
        r = _run(s, key)
        return _run_view(r) if r else None


def _stage_data(db, key: str) -> dict:
    with db.session() as s:
        return dict(_run(s, key).stages or {})


# ---- candidates and learning ------------------------------------------------------------

def store_bytes(db, data: bytes, *, key: str, why: str) -> str:
    from ..core.artifacts import ArtifactStore

    return ArtifactStore().put(key, data, "image/png", db=db, keep=why).sha256


def record_candidate(db, cand: dict, verdict: dict, *, method: str, run: str = "",
                     stage: str = "", attempt: int = 1, owner_visual_approval=None,
                     submitted_by: str = "", outcome: str | None = None) -> dict:
    """One learning/provenance row per candidate, whatever made it."""
    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    q = verdict["checks"].get("quality") or {}
    tech = verdict["technical_status"]
    outcome = outcome or {"PASS": "accepted", "FAIL": "rejected"}.get(tech, "unverified")
    prompt = str(cand.get("prompt") or "")
    with db.session() as s:
        row = ImageCandidate(
            sha256=verdict["sha256"], run_key=run, method=method,
            provenance_kind=cand.get("provenance_kind") or f"ai_generated_{method}",
            slug=cand.get("slug", ""), version=cand.get("version", ""),
            release=cand.get("release", ""), listing=verdict.get("listing", ""),
            role=cand.get("role", ""), stage=stage, attempt=attempt,
            provider=str(cand.get("provider") or "")[:80],
            model=str(cand.get("model") or "")[:120], prompt=prompt[:8000],
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            prompt_version=str(cand.get("prompt_version") or "")[:80],
            references=[_ref_provenance(r) for r in cand.get("references") or []],
            laura_present=bool(cand.get("laura_present")),
            outfit_id=str(cand.get("outfit_id") or "")[:80],
            cost_cad=cand.get("cost_cad"), cost_basis=str(cand.get("cost_basis") or "")[:200],
            latency_s=cand.get("latency_s"), width=q.get("width"), height=q.get("height"),
            binding={k: v for k, v in verdict["checks"]["binding"].items()},
            checks={**verdict["checks"], "_publication": verdict.get("publication") or {},
                    # D-OWNER-FLUX-GALLERY: the route the candidate was generated and judged
                    # under, so a re-verification and the listing set judge it the same way
                    **({"_route": {"route": str(cand["route"]),
                                   # ENG-OWNER-GALLERY: who made the frame (internal only)
                                   **({"supplied_by": str(cand["supplied_by"])[:20]}
                                      if cand.get("supplied_by") else {})}}
                       if cand.get("route") else {}),
                    **({"_paid_call": {"token": cand["_paid_call_token"]}}
                       if cand.get("_paid_call_token") else {}),
                    **({"_anchor_side": dict(cand["_anchor_side"])}
                       if cand.get("_anchor_side") else {}),
                    # ENG-IMAGES-LAURA: the reference inputs by hash, in the order sent
                    **({"_reference_provenance": dict(cand["_reference_provenance"])}
                       if cand.get("_reference_provenance") else {}),
                    # ENG-IMAGE-METHOD-REDRIVE: the generation method this candidate was made
                    # under, by stable identifiers (absent = "pre-method")
                    **({METHOD_KEY: dict(cand[METHOD_KEY])}
                       if isinstance(cand.get(METHOD_KEY), dict) else {}),
                    **({"_generation_operation": {"key": cand["_generation_operation"],
                                                   "mode": cand.get("_generation_mode")}}
                       if cand.get("_generation_operation") else {}),
                    # the generator's conditioning receipt (references sent, proven), kept
                    # so a re-verification reads the same evidence (W-VISNEXT)
                    "_identity_evidence": _receipt_summary(cand.get("identity_evidence")),
                    # ENG-LEARN: the scene the producer chose (room, camera, lighting), read
                    # back by learning.image_lessons.harvest; never read by a gate.
                    **({"_scene": {k: str(v)[:200] for k, v in cand["scene"].items()}}
                       if isinstance(cand.get("scene"), dict) else {})},
            technical_status=tech,
            publishable=bool(verdict["publishable"]), outcome=outcome,
            failure_categories=list(verdict.get("failure_categories") or []),
            owner_visual_approval=owner_visual_approval, submitted_by=submitted_by[:120])
        s.add(row)
        s.flush()
        return {"candidate_id": row.id, "sha256": row.sha256, "outcome": outcome}


def _ref_provenance(r: dict) -> dict:
    """{sha256, kind}, plus source and label for a certified-PDF page reference."""
    from ..creative.pdf_page_refs import SOURCE, is_page_ref

    out = {"sha256": r.get("sha256"), "kind": r.get("kind")}
    if is_page_ref(r):
        out["source"] = SOURCE
        out["label"] = str(r.get("label") or "").split("|", 1)[0][:60]
    return out


def _receipt_summary(ev) -> dict:
    ev = ev if isinstance(ev, dict) else {}
    out = {k: ev[k] for k in ("conditioning", "references", "request", "non_identity_references")
           if k in ev}
    if isinstance(out.get("request"), dict):
        out["request"] = {k: out["request"].get(k) for k in ("conditioning_proven",
                                                              "request_sha256")}
    return out


def learning_summary(db, *, slug: str | None = None) -> dict:
    from sqlalchemy import select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        q = select(ImageCandidate)
        if slug:
            q = q.where(ImageCandidate.slug == slug)
        rows = list(s.scalars(q))
    cats: dict[str, int] = {}
    for r in rows:
        for c in r.failure_categories or []:
            cats[c] = cats.get(c, 0) + 1
    spent = sum(r.cost_cad for r in rows if r.cost_cad is not None)
    unknown_cost = sum(1 for r in rows if r.cost_cad is None)
    accepted = sum(1 for r in rows if r.outcome == "accepted")
    lat = [r.latency_s for r in rows if r.latency_s is not None]
    return {"candidates": len(rows), "accepted": accepted,
            "outcomes": {o: sum(1 for r in rows if r.outcome == o)
                         for o in ("accepted", "rejected", "unverified", "provider_error")},
            "failure_categories": cats, "spent_cad": round(spent, 4),
            "candidates_with_unknown_cost": unknown_cost,
            "cost_per_accepted_cad": (round(spent / accepted, 4) if accepted and not
                                      unknown_cost else None),
            "latency_s": ({"min": min(lat), "max": max(lat),
                           "mean": round(sum(lat) / len(lat), 2)} if lat else None),
            "note": ("cost per accepted image is undefined when nothing was accepted or any "
                     "cost is unknown; never reported as zero")}


def _best(db, *, listing: str, role: str, run: str | None = None,
          slug: str | None = None, version: str | None = None,
          release: str | None = None, method: str | None = None,
          unscoped_only: bool = False, exclude_ids: tuple[int, ...] = (),
          production_only: bool = False) -> dict | None:
    from sqlalchemy import and_, case, func, or_, select

    from .image_records import ImageCandidate

    with db.session() as s:
        q = select(ImageCandidate).where(ImageCandidate.listing == listing,
                                         ImageCandidate.role == role)
        if run:
            q = q.where(ImageCandidate.run_key == run)
        if unscoped_only:
            q = q.where(ImageCandidate.run_key == "")
        if production_only:
            q = q.where(or_(and_(ImageCandidate.run_key == "", ImageCandidate.method == "owner_submitted"),
                            and_(ImageCandidate.run_key != "", ~ImageCandidate.run_key.like("%#%"))))
        if slug is not None:
            q = q.where(ImageCandidate.slug == slug)
        if version is not None:
            q = q.where(ImageCandidate.version == version)
        if release is not None:
            q = q.where(func.lower(ImageCandidate.release) == release.lower())
        if method is not None:
            q = q.where(ImageCandidate.method == method)
        if exclude_ids:
            q = q.where(ImageCandidate.id.not_in(exclude_ids))
        rank = case((ImageCandidate.technical_status == "PASS", 0),
                    (ImageCandidate.technical_status == "UNKNOWN", 1),
                    (ImageCandidate.technical_status == "FAIL", 2), else_=3)
        publishable_rank = case((ImageCandidate.publishable.is_(True), 0), else_=1)
        r = s.scalar(q.order_by(publishable_rank, rank, ImageCandidate.id.desc()).limit(1))
    if r is None:
        return None
    return {"candidate_id": r.id, "sha256": r.sha256, "method": r.method,
            "technical_status": r.technical_status, "publishable": r.publishable,
            "attempt": r.attempt, "outcome": r.outcome,
            "failure_categories": list(r.failure_categories or []),
            "owner_visual_approval": r.owner_visual_approval,
            "unknown": sorted(k for k, c in (r.checks or {}).items()
                              if k != "_paid_call_token" and c.get("status") == "UNKNOWN"),
            "failed": {k: c.get("why") for k, c in (r.checks or {}).items()
                       if k != "_paid_call_token" and c.get("status") == "FAIL"},
            "blockers": ((r.checks or {}).get("_publication") or {}).get("blockers"),
            "listing": r.listing, "slug": r.slug, "version": r.version, "release": r.release,
            "cir_fingerprint": (r.binding or {}).get("cir_fingerprint"),
            "laura_present": r.laura_present, "outfit_id": r.outfit_id or None,
            "fidelity": _fidelity_summary(r.checks),
            "structural": structural_failure(r.checks) if r.technical_status == "FAIL"
            else None,
            "item_reading": _item_reading(r.checks)}


def structural_failure(checks: dict | None) -> str | None:
    """The named reason a FAILed candidate cannot be fixed by regenerating it, or None.

    W5-V1 (audit P0-a): a LIFESTYLE candidate's `lifestyle_evidence` FAILs because its
    references are pattern-derived (classed informational: a chart), and a regeneration uses
    the same references, so it cannot pass. `candidate_gates.lifestyle_reading` names that as
    `structural`; this reads it back from the stored checks."""
    le = ((checks or {}).get("product_truth") or {}).get("lifestyle_evidence") or {}
    if le.get("status") == "FAIL" and le.get("structural"):
        return str(le["structural"])
    return None


def _item_reading(checks: dict | None) -> dict | None:
    """V2 / P1-d: the vision judge's blind description of this frame's item (the candidate
    side of its anchor-consistency reading), or None when it was never judged."""
    fid = ((checks or {}).get("product_truth") or {}).get("fidelity") or {}
    for c in fid.get("checks") or []:
        if c.get("check") == "anchor_consistency":
            got = ((c.get("reading") or {}).get("image_2"))
            return dict(got) if isinstance(got, dict) else None
    return None


def _fidelity_summary(checks: dict | None) -> dict:
    """What the fidelity verifier left unknown or failed on a stored candidate."""
    fid = ((checks or {}).get("product_truth") or {}).get("fidelity") or {}
    needs = sorted({f"{c['check']} needs a {c['needs']}" for c in fid.get("checks") or []
                    if c.get("needs") and c.get("status") == "UNKNOWN"})
    return {"status": fid.get("status"), "kind": fid.get("kind"), "checker": fid.get("checker"),
            "image_sha256": fid.get("image_sha256"), "cir_fingerprint": fid.get("cir_fingerprint"),
            "slug": fid.get("slug"), "version": fid.get("version"),
            "checks": fid.get("checks") or [],
            "unknown": fid.get("unknown") or [],
            "failed": fid.get("failed") or [], "codes": fid.get("codes") or [],
            "needs": needs}


def _attempts(db, run: str, role: str) -> int:
    """Attempts spent on `role` in `run`. After a method redrive (ENG-IMAGE-METHOD-REDRIVE)
    only candidates made under the method the run was re-driven for count: the older method's
    attempts were spent on a method that no longer runs. Calls and spend are never scoped."""
    from sqlalchemy import func, select

    from .image_records import ImageCandidate

    scoped = _redriven_method(db, run)
    with db.session() as s:
        rows = s.execute(select(ImageCandidate.checks, ImageCandidate.outcome,
                                ImageCandidate.sha256).where(
            ImageCandidate.run_key == run, ImageCandidate.role == role)).all()
    # REDRIVE-REFUSAL: a call the provider never accepted is not an attempt.
    return sum(1 for checks, outcome, sha in rows
               if not candidate_unaccepted(outcome, sha, checks)
               and (scoped is None or candidate_method_version(checks) == scoped))


# ---- REDRIVE-REFUSAL: a call the provider never accepted is not spent ----------------------
# Production 19i19 (2026-11-23): the BFL key was rejected (403) before any task id, and the
# paid gate refused daily-ceiling calls before sending. Nothing was billed, but each such call
# still counted toward `MAX_GENERATION_CALLS`, the per-role attempt cap and the restart cap, so
# runs re-driven after the key fix and the daily reset had no budget left to run. A call that
# was never accepted -- a 4xx on the submit (`gateway.images._post` marks it), or the paid gate
# refusing before any I/O -- is now excluded from those counts. `generation_calls` itself
# still records every call (audit); billed and uncertain calls count in full; spend, and every
# money cap, are untouched.
UNACCEPTED_KEY = "_unaccepted"          # candidate.checks marker: {"accepted": False, ...}
GATE_REFUSED_TEXT = "paid provider gate refused before sending"
# Rows written before the marker: the submit's own words, "<provider> 401: " / "<provider> 403: "
# (an auth refusal before a task id). A poll error reads "<provider> poll <code>" and never
# matches, so an accepted-then-failed render is never taken for an unbilled one.
_LEGACY_UNACCEPTED = re.compile(r"(?:^|[\s:])[\w.\-]+ 40[13]: ")
# IMAGE-STALE-REFS: the generator's binding check refusing stale references
# (`flux3_generator.StaleReferences`, before it existed a plain GeneratorRefused with the same
# words). `_bind` raises it before any reservation, preflight or render: nothing was sent.
_STALE_REFUSAL = re.compile(
    r"(?:GeneratorRefused|StaleReferences): the (?:product|certified-PDF page) references "
    r"handed in are not (?:the bytes this release renders|the pages of this release's "
    r"certified PDF); refused")


def never_accepted_status(exc: BaseException | None) -> int | None:
    """The provider's 4xx status when `exc`'s chain says the submit was refused before a task
    id (`never_accepted_status` on the gateway's error); None otherwise."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        st = getattr(exc, "never_accepted_status", None)
        if isinstance(st, int) and not isinstance(st, bool) and 400 <= st < 500:
            return st
        exc = exc.__cause__ or exc.__context__
    return None


def candidate_unaccepted(outcome, sha256, checks) -> bool:
    """A provider-error candidate whose call the provider never accepted (no bytes, no bill)."""
    if outcome != "provider_error" or sha256:
        return False
    checks = checks if isinstance(checks, dict) else {}
    mark = checks.get(UNACCEPTED_KEY)
    if isinstance(mark, dict):
        return mark.get("accepted") is False
    why = str((checks.get("provider") or {}).get("why") or "")
    return bool(_LEGACY_UNACCEPTED.search(why)) or bool(_STALE_REFUSAL.search(why))


def _sent_nothing(exc: BaseException | None) -> bool:
    """True when `exc`'s chain is a generator refusal raised before anything was sent
    (`sent_nothing`, e.g. `flux3_generator.StaleReferences`)."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if getattr(type(exc), "sent_nothing", False) is True:
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _utc(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _unaccepted_rows(session, key: str) -> list:
    """created_at of each never-accepted candidate of run `key`."""
    from sqlalchemy import select

    from .image_records import ImageCandidate as IC

    return [_utc(at) for at, outcome, sha, checks in session.execute(
        select(IC.created_at, IC.outcome, IC.sha256, IC.checks).where(
            IC.run_key == key, IC.outcome == "provider_error"))
        if candidate_unaccepted(outcome, sha, checks)]


def _gate_refused(reason) -> bool:
    return GATE_REFUSED_TEXT in str(reason or "")


def unbilled_calls(session, row) -> int:
    """Calls of run `row` (an ImageProductionRun) that the provider never accepted: every
    never-accepted candidate, plus one per block the paid gate caused by refusing before
    sending (that call was counted, then released unbilled)."""
    stages = dict(row.stages or {})
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    n = len(_unaccepted_rows(session, row.run_key))
    n += sum(1 for h in history if isinstance(h, dict) and _gate_refused(h.get("blocked_reason")))
    if row.status == "blocked" and _gate_refused(row.blocked_reason):
        n += 1
    return n


def counted_calls(session, row) -> int:
    """`generation_calls` less the calls the provider never accepted: what the call cap reads.
    A corrupt persisted counter (not a nonnegative integer) is returned as it is, so the spend
    plan's guard refuses it rather than this hiding it."""
    calls = row.generation_calls
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
        return calls
    return max(0, calls - unbilled_calls(session, row))


# D-RESTART-PER-METHOD (19i29): MAX_RESTARTS binds per generation-method version. A run whose
# method version moved (`generation_method`: prompt builder, pattern references, PDF page
# references, owner method) is a new product attempt and its restart budget starts fresh; the
# restarts spent under older versions stay in the history and in the evidence
# (`restart_counts`), and do not count against the current version's cap. Within one version
# the cap binds exactly as before (the thrash bound). Spend caps are unchanged.
#
# Every history entry written from 19i29 carries `generation_method` (the version the restart
# was made under). An entry written before carries none; a method redrive's entry names its
# `method_version`. Otherwise the version is the one production ran at the entry's time:
# 19i27 (cc3058b25, deployed 2026-11-25T11:42Z) introduced pattern-refs/3.1.6; 19i26
# (74bd8d57a, 08:45Z) prompt builder 2.4.0 with pattern-refs/3.1.5. Anything earlier ran an
# older method. An unstamped entry whose time cannot be read counts under the current version
# (it cannot be shown to be older).
HISTORY_METHOD_KEY = "generation_method"
_LEGACY_METHOD_TIMELINE = (
    ("2026-11-25T11:42:00+00:00",
     "flux3-prompt-builder/2.4.0|pattern-refs/3.1.6|pdf-page-refs/1.0.0|owner_two_step/1"),
    ("2026-11-25T08:45:00+00:00",
     "flux3-prompt-builder/2.4.0|pattern-refs/3.1.5|pdf-page-refs/1.0.0|owner_two_step/1"),
)
LEGACY_METHOD_BEFORE_19I26 = "unstamped:before-2026-11-25T08:45Z"


def entry_method_version(h: dict, current: str | None = None) -> str:
    """The generation-method version restart-history entry `h` was made under."""
    v = h.get(HISTORY_METHOD_KEY) or h.get("method_version")
    if v:
        return str(v)
    at = _utc(h.get("at"))
    if at is None:
        return current or current_method_version()
    for since, version in _LEGACY_METHOD_TIMELINE:
        if at >= datetime.fromisoformat(since):
            return version
    return LEGACY_METHOD_BEFORE_19I26


def restart_counts(session, row, *, current: str | None = None) -> dict:
    """{"current": restarts counting toward MAX_RESTARTS (the current method version's),
    "total": every counted restart of the run, "method_version": the current version,
    "by_method": {version: counted restarts}}.

    An epoch counts unless every call it made was never accepted (it made at least one call
    and none reached the provider's bill). An epoch with no call at all still counts: the cap
    is also a thrash bound. D-RESTART-DUPLICATE-CREDIT: a zero-generation fidelity
    re-judgement under a (judge version, check version) an earlier re-judgement of the run
    already used (`_duplicate_rejudgement`) is our own duplicate and does not count.
    D-RESTART-PER-METHOD: only the epochs made under the current generation-method version
    count toward the cap; the rest stay in `total` and `by_method`."""
    current = current or current_method_version()
    stages = dict(row.stages or {})
    rec = stages.get(RESTART_KEY) or {}
    epoch = int(rec.get("epoch") or 0)
    history = [h for h in (rec.get("history") or []) if isinstance(h, dict)]
    by: dict[str, int] = {}
    if not history:
        # no history to attribute: every epoch counts under the current version
        if epoch:
            by[current] = epoch
        return {"current": epoch, "total": epoch, "method_version": current, "by_method": by}
    unaccepted = _unaccepted_rows(session, row.run_key)
    for i, h in enumerate(history):
        if not _epoch_counts(history, i, row, unaccepted):
            continue
        v = entry_method_version(h, current)
        by[v] = by.get(v, 0) + 1
    # epochs the history does not describe (never expected) count under the current version
    missing = max(0, epoch - len(history))
    if missing:
        by[current] = by.get(current, 0) + missing
    total = sum(by.values())
    return {"current": by.get(current, 0), "total": total, "method_version": current,
            "by_method": by}


def _epoch_counts(history: list[dict], i: int, row, unaccepted) -> bool:
    """Whether history entry `i`'s epoch counts as a spent restart (see `restart_counts`)."""
    h = history[i]
    start, start_calls = _utc(h.get("at")), h.get("generation_calls")
    if i + 1 < len(history):
        nxt = history[i + 1]
        end, end_calls, end_reason = _utc(nxt.get("at")), nxt.get("generation_calls"), \
            nxt.get("blocked_reason")
    elif row.status == "blocked":
        end, end_calls, end_reason = None, row.generation_calls, row.blocked_reason
    else:
        return True          # the current epoch is still running: it counts
    if start is None or not isinstance(start_calls, int) or not isinstance(end_calls, int):
        return True
    made = end_calls - start_calls
    if made == 0 and _duplicate_rejudgement(history, i):
        # D-RESTART-DUPLICATE-CREDIT: a zero-generation re-judgement under (judge version,
        # check version) an earlier re-judgement of this run had already used. It added no
        # generation and no new version: our own duplicate, not an attempt.
        return False
    if made <= 0:
        return True
    lost = sum(1 for at in unaccepted
               if at is not None and at >= start and (end is None or at < end))
    lost += 1 if _gate_refused(end_reason) else 0
    return lost < made


def restarts_spent(session, row, *, current: str | None = None) -> int:
    """Restarts that count toward `MAX_RESTARTS`: the counted epochs made under the current
    generation-method version (D-RESTART-PER-METHOD; `restart_counts`)."""
    return restart_counts(session, row, current=current)["current"]


def _duplicate_rejudgement(history: list[dict], i: int) -> bool:
    """History entry `i` is a fidelity re-judgement (reverify / rejudge) whose (judge version,
    check version) an EARLIER re-judgement entry of the same run already carried. Only such an
    epoch with zero generation calls is credited back (`restarts_spent`); every other epoch,
    including the first re-judgement under any version pair, counts as before."""
    h = history[i]
    if h.get("by") not in _REJUDGEMENT_BY or not h.get("judge_version"):
        return False
    pair = (h.get("judge_version"), _entry_check_version(h))
    return any(e.get("by") in _REJUDGEMENT_BY
               and (e.get("judge_version"), _entry_check_version(e)) == pair
               for e in history[:i])


def _run_counts(db, key: str) -> dict:
    """{"counted_calls", "restarts_spent" (under the current generation-method version: what
    MAX_RESTARTS reads), "restarts_total" (every method version), "unbilled_calls"} for run
    `key`."""
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None:
            return {"counted_calls": 0, "restarts_spent": 0, "restarts_total": 0,
                    "unbilled_calls": 0}
        rc = restart_counts(s, r)
        return {"counted_calls": counted_calls(s, r), "restarts_spent": rc["current"],
                "restarts_total": rc["total"], "unbilled_calls": unbilled_calls(s, r)}


# ---- one generation, through the budget --------------------------------------------------

class BudgetStop(RuntimeError):
    pass


class ConditioningRefused(RuntimeError):
    pass


class CapabilityBlocked(RuntimeError):
    """A missing capability (a closed gate), not a failed attempt: shown, not notified."""


# D-OWNER-FLUX-GALLERY: a seven-frame FLUX gallery is two anchors and six frames, plus at most
# MAX_REPAIR_ROUNDS repair rounds of six (20), times D-OWNER-PHOTO-BUDGET's factor (60).
FLUX_MAX_GENERATION_CALLS = (2 + 6 * (1 + MAX_REPAIR_ROUNDS)) * PHOTO_BUDGET_FACTOR


def _spend_plan(key: str = "", db=None) -> dict:
    from . import gallery_budget, spend_plan

    calls = FLUX_MAX_GENERATION_CALLS if route_of_key(key) else MAX_GENERATION_CALLS
    return spend_plan.build(
        hypothesis="one truthful gallery per certified release",
        provider_model="registered generator", call_count=calls,
        # the lower of the code maximum and the owner's per-gallery cap
        max_spend_cad=gallery_budget.effective_cap(db) if db is not None
        else MAX_SPEND_CAD_PER_GALLERY,
        pass_criteria=["every generated role technical PASS under candidate_gates"],
        fail_criteria=["attempt cap reached", "any spend past the plan"])


def _begin_generation(db, key, *, stage, paid, next_cost):
    """Record a paid call before dispatch; unresolved calls hold further generation."""
    from uuid import uuid4
    from sqlalchemy import select
    from .image_records import ImageProductionRun
    from . import spend_plan

    token = uuid4().hex if paid else None
    with db.session() as session:
        row = session.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        stages = dict(row.stages or {})
        if "_pending_paid_call" in stages or "_unresolved_free_cost" in stages:
            raise BudgetStop("prior paid image call has an unresolved cost; review required")
        try:
            spend_plan.guard(_spend_plan(key, db), spent_cad=row.spent_cad,
                             calls_made=counted_calls(session, row), next_cost_cad=next_cost)
        except spend_plan.PlanRefused as exc:
            raise BudgetStop(str(exc)) from None
        row.generation_calls += 1
        row.stage, row.updated_at = stage, _now()
        if paid:
            stages["_pending_paid_call"] = {"token": token, "stage": stage,
                                             "maximum_cad": next_cost,
                                             "at": _now().isoformat()}
            row.stages = stages
    return token


def _refused_before_send(exc: BaseException):
    """The `PaidCallRefused` in `exc`'s chain, if any: the gateway's enforcement point refuses
    before any network I/O, so a call refused there was never billed."""
    from ..gateway.paid_provider_gate import PaidCallRefused

    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, PaidCallRefused):
            return exc
        exc = exc.__cause__ or exc.__context__
    return None


def _release_refused_generation(db, key, token):
    """Clear this call's pending-paid hold (it was refused before sending; nothing billed)."""
    from sqlalchemy import select
    from .image_records import ImageProductionRun

    with db.session() as session:
        row = session.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        stages = dict(row.stages or {})
        pending = stages.get("_pending_paid_call")
        if isinstance(pending, dict) and pending.get("token") == token \
                and pending.get("state") is None:
            del stages["_pending_paid_call"]
            row.stages, row.updated_at = stages, _now()


def _settle_paid_generation(db, key, token, cost):
    """Record the actual charge while retaining the marker until candidate persistence."""
    from sqlalchemy import select
    from .image_records import ImageProductionRun
    from . import spend_plan

    if not spend_plan._amount(cost):
        raise BudgetStop("paid image call has an invalid or missing cost; review required")
    with db.session() as session:
        row = session.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        stages = dict(row.stages or {})
        pending = stages.get("_pending_paid_call")
        if not isinstance(pending, dict) or pending.get("token") != token:
            raise BudgetStop("paid image call reservation changed; review required")
        if pending.get("state") is not None:
            raise BudgetStop("paid image call receipt was already processed; review required")
        if not spend_plan._amount(row.spent_cad):
            raise BudgetStop("recorded visual spend is invalid; review required")
        maximum = pending["maximum_cad"]
        row.spent_cad += cost
        if cost > maximum:
            stages["_pending_paid_call"] = {**pending, "actual_cad": cost,
                                             "state": "cost_exceeded_maximum"}
        else:
            stages["_pending_paid_call"] = {**pending, "actual_cad": cost,
                                             "state": "receipt_recorded"}
        row.stages = stages
        row.updated_at = _now()
    if cost > maximum:
        raise BudgetStop("paid image call exceeded its declared maximum; review required")


def _complete_paid_generation(db, key, token, candidate_id):
    """Release the hold only after this run's candidate and receipt are durable."""
    from sqlalchemy import select
    from .image_records import ImageCandidate, ImageProductionRun

    with db.session() as session:
        row = session.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        stages = dict(row.stages or {})
        pending = stages.get("_pending_paid_call")
        cand = session.get(ImageCandidate, candidate_id)
        if (not isinstance(pending, dict) or pending.get("token") != token
                or pending.get("state") != "receipt_recorded" or cand is None
                or cand.run_key != key or cand.stage != pending.get("stage")
                or not cand.sha256 or cand.cost_cad != pending.get("actual_cad")
                or ((cand.checks or {}).get("_paid_call") or {}).get("token") != token):
            raise BudgetStop("paid image candidate or receipt is missing; review required")
        del stages["_pending_paid_call"]
        row.stages, row.updated_at = stages, _now()


def _settle_free_generation(db, key, cost):
    """Record unexpected free-adapter charges without overwriting concurrent spend."""
    from sqlalchemy import select
    from .image_records import ImageProductionRun
    from . import spend_plan

    valid = spend_plan._amount(cost)
    with db.session() as session:
        row = session.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        if not spend_plan._amount(row.spent_cad):
            raise BudgetStop("recorded visual spend is invalid; review required")
        if valid and cost > 0:
            row.spent_cad += cost
        if not valid or cost > 0:
            stages = dict(row.stages or {})
            # A separate marker cannot be cleared by a concurrent paid settlement.
            stages["_unresolved_free_cost"] = {"state": "unexpected_free_cost",
                                                "actual_cad": cost if valid else None}
            row.stages = stages
        row.updated_at = _now()
    if not valid or cost > 0:
        raise BudgetStop("free image generator returned an invalid or nonzero cost; review required")


def _recover_generation(db, key, *, operation, stage, role, slug, version, release,
                        experiment: bool = False):
    """Reuse only the candidate recorded by this exact stage invocation."""
    if not operation:
        return None
    from sqlalchemy import select
    from ..core.artifacts import ArtifactStore
    from .image_records import ImageCandidate

    with db.session() as session:
        rows = session.scalars(select(ImageCandidate).where(
            ImageCandidate.run_key == key, ImageCandidate.stage == stage,
            ImageCandidate.role == role)).all()
        matches = [r for r in rows if isinstance((r.checks or {}).get("_generation_operation"), dict)
                   and r.checks["_generation_operation"].get("key") == operation]
        if len(matches) > 1:
            raise BudgetStop("multiple candidates for one generation operation; review required")
        if not matches:
            return None
        row = matches[0]
        binding = row.binding if isinstance(row.binding, dict) else {}
        mode = row.checks["_generation_operation"].get("mode")
        if (mode != ("experiment" if experiment else "normal")
                or binding.get("experiment", False) is not experiment):
            raise BudgetStop("generation operation mode is ambiguous or changed; review required")
        if (row.slug != slug or row.version != version or row.release != release
                or not row.sha256):
            raise BudgetStop("generation operation candidate identity changed; review required")
        try:
            data = ArtifactStore().get(row.sha256, db=db)
        except Exception as exc:
            raise BudgetStop("generation operation artifact unavailable; review required") from exc
        if not data or hashlib.sha256(data).hexdigest() != row.sha256:
            raise BudgetStop("generation operation artifact changed; review required")
        out = {"candidate_id": row.id, "sha256": row.sha256, "outcome": row.outcome,
               "technical_status": row.technical_status, "publishable": row.publishable,
               "cost_cad": row.cost_cad, "attempt": row.attempt}
        token = ((row.checks or {}).get("_paid_call") or {}).get("token")
    current = _stage_data(db, key)
    if "_unresolved_free_cost" in current:
        raise BudgetStop("prior image call has an unresolved cost; review required")
    if "_pending_paid_call" in current:
        pending = current["_pending_paid_call"]
        if not token or not isinstance(pending, dict) or pending.get("token") != token:
            raise BudgetStop("another paid image call has an unresolved cost; review required")
        _complete_paid_generation(db, key, token, out["candidate_id"])
    return out


def _generate(db, key: str, gen, *, slug, version, release, role, stage, brief, refs, outfit,
              laura: bool, judges, plan_attempt: int, evaluate: bool = True,
              repair: dict | None = None, exp=None, operation: str = "",
              route: str = "", side: dict | None = None,
              reference_provenance: dict | None = None) -> dict:
    from . import spend_plan
    from .gallery import gates_now

    recovered = _recover_generation(db, key, operation=operation, stage=stage, role=role,
                                    slug=slug, version=version, release=release,
                                    experiment=exp is not None)
    if recovered is not None:
        return recovered
    with db.session() as s:
        r = _run(s, key)
        calls, spent = counted_calls(s, r), r.spent_cad
    paid = getattr(gen, "paid", True) is not False
    next_cost = getattr(gen, "max_cost_cad_per_call", 0.0)
    try:
        spend_plan.guard(_spend_plan(key, db), spent_cad=spent, calls_made=calls,
                         next_cost_cad=next_cost)
    except spend_plan.PlanRefused as exc:
        raise BudgetStop(str(exc)) from None
    if exp is not None:
        # W4-WRAPTEST: an experiment's paid call needs the owner's recorded experiment approval
        # and headroom in its own hard budget; every ceiling below still applies on top.
        from .experiment import ExperimentBudgetStop

        if paid and not exp.paid_authorised():
            raise CapabilityBlocked("experiment is not live: a paid generator may not be "
                                    "called (dry run uses the stub provider)")
        if paid:
            try:
                exp.guard_paid(next_cost)
            except ExperimentBudgetStop as exc:
                raise BudgetStop(str(exc)) from None
    elif _controlled_of(db, key) and paid:
        # W-VISNEXT2: an owner-authorised controlled run of a certified release. The owner's
        # step-up authorization, inside its (shared) cap, stands in for the image_generation
        # gate for this run only; every ceiling below still applies on top.
        from ..experiments import controlled as CX

        CX.guard_generation(db, _controlled_of(db, key), next_cost)
    elif paid and not gates_now(db, keys=("image_generation",)).get(
            "image_generation"):
        from ..gateway.paid_provider_gate import generation_gate_reason
        raise CapabilityBlocked("image_generation gate closed: a paid generator may not be "
                                f"called ({generation_gate_reason(db)})")
    if paid and next_cost == 0:
        raise BudgetStop("paid generator requires a positive maximum cost per call")
    # V1's _begin_generation runs V0's spend_plan.guard and counts the call, atomically.
    call_token = _begin_generation(db, key, stage=stage, paid=paid, next_cost=next_cost)
    base = {"slug": slug, "version": version, "release": release, "run_key": key, "role": role,
            "laura_present": laura, "outfit_id": (outfit or {}).get("outfit_id"),
            "listing": outfits.listing_of(slug), "prompt_version": prompt_version(db),
            METHOD_KEY: generation_method(gen)}
    if route:
        base["route"] = route
    if exp is not None:
        base["experiment"] = True
    if hasattr(type(gen), "current_run_key"):
        gen.current_run_key = key         # the generator reads this run's own anchor
    try:
        kw = {"repair": repair} if repair else {}
        out = gen.generate(stage=stage, role=role, brief=brief, references=refs,
                           outfit=outfit, attempt=plan_attempt, **kw)
    except Exception as exc:  # noqa: BLE001 - a provider error is a recorded outcome
        from .image_records import ImageCandidate

        refused = _refused_before_send(exc)
        if paid and refused is not None:
            # IMAGE-E2E: the paid-provider gate refused this render before any network I/O
            # (a per-gallery, daily or monthly ceiling, or no activation), so nothing was
            # billed. Release this call's hold and stop the run naming the ceiling. Before
            # this the hold stayed and the run blocked as "prior paid image call has an
            # unresolved cost; review required" -- a cap reported as a billing mystery.
            _release_refused_generation(db, key, call_token)
            raise BudgetStop(f"paid provider gate refused before sending "
                             f"({refused.code}): {str(refused)[:300]}") from None
        unaccepted = never_accepted_status(exc)
        nothing_sent = _sent_nothing(exc)
        if paid and nothing_sent:
            # IMAGE-STALE-REFS: the generator refused its inputs before any send (stale
            # references): nothing was billed. Release the hold; the row below is marked, so
            # it counts toward no call, attempt or restart cap.
            _release_refused_generation(db, key, call_token)
        if paid and unaccepted is not None:
            # REDRIVE-REFUSAL: the provider refused the submit before a task id (e.g. a 403
            # on a rejected key): nothing was billed, so this call's hold is released and the
            # candidate below is marked; it counts toward no call, attempt or restart cap.
            _release_refused_generation(db, key, call_token)
        with db.session() as s:
            s.add(ImageCandidate(sha256="", run_key=key, method="autonomous",
                                 provenance_kind="ai_generated_autonomous", slug=slug,
                                 version=version, release=release, listing=base["listing"],
                                 role=role, stage=stage, attempt=plan_attempt,
                                 provider=getattr(gen, "name", "?")[:80],
                                 technical_status="UNKNOWN", outcome="provider_error",
                                 failure_categories=["provider_error"],
                                 checks={"provider": {"status": "FAIL",
                                                      "why": f"{type(exc).__name__}: "
                                                             f"{str(exc)[:300]}"},
                                         METHOD_KEY: dict(base[METHOD_KEY]),
                                         **({UNACCEPTED_KEY: {
                                             "accepted": False, "http_status": unaccepted}}
                                            if unaccepted is not None else
                                            {UNACCEPTED_KEY: {
                                                "accepted": False, "http_status": None,
                                                "refused": "sent_nothing"}}
                                            if nothing_sent else {})}))
        return {"provider_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    cost = out.get("cost_cad")
    if paid:
        _settle_paid_generation(db, key, call_token, cost)
    else:
        _settle_free_generation(db, key, cost)
    data = out["data"]
    ctl = _controlled_of(db, key)
    sha = store_bytes(db, data, key=f"{key}/{role}/{plan_attempt}",
                      why="generated listing-image candidate (AI; never a photograph)" + (
                          f"; {exp.label}" if exp is not None else "") + (
                          "; EXPERIMENT (controlled run)" if ctl else ""))
    if ctl:
        # marked as an experiment image before anything evaluates it
        from ..experiments import controlled as CX

        CX.record_generation(db, ctl, reserved_cad=next_cost if paid
                             else 0.0, actual_cad=cost, sha256=sha)
    cand = {**base, "data": data, "sha256": sha, "provider": out.get("provider"),
            "model": out.get("model"), "prompt": out.get("prompt") or brief,
            # ENG-IMAGES-PDFREF: a certified-PDF page carries its source and label (kind,
            # page) so each candidate records the reference page hashes as provenance
            "references": [_ref_provenance(r) for r in refs],
            "identity_evidence": out.get("identity_evidence"), "cost_cad": cost,
            "cost_basis": out.get("cost_basis") or "generator receipt",
            "latency_s": out.get("latency_s"), "provenance_kind": "ai_generated_autonomous",
            "repair": repair}
    if paid:
        cand["_paid_call_token"] = call_token
    if side is not None and role == ANCHOR_ROLE:
        # IMAGE-AD: the vessel's side view, judged with the top-down anchor as one pair
        cand["side_data"] = side["data"]
        cand["_anchor_side"] = {"candidate_id": side["candidate_id"],
                                "sha256": side["sha256"]}
    if operation:
        cand["_generation_operation"] = operation
        cand["_generation_mode"] = "experiment" if exp is not None else "normal"
    if reference_provenance:
        cand["_reference_provenance"] = reference_provenance
    if role == ANCHOR_ROLE:
        bind = _binding(db, exp, slug, version, release)
        pt = judges.product_truth({**cand, "role": ANCHOR_ROLE}, bind)
        q = CG.quality(data)
        verdict = {"sha256": sha, "listing": base["listing"], "publishable": False,
                   "checks": {"binding": bind, "product_truth": pt, "quality": q},
                   "technical_status": CG.worst(bind["status"], pt["status"], q["status"]),
                   "failure_categories": sorted(
                       {CG.FAILURE_CATEGORY[k] for k, c in (("binding", bind),
                        ("product_truth", pt), ("quality", q)) if c["status"] == CG.FAIL})
                   # the fidelity verifier's codes (W-FIDELITY), so learning and the
                   # repair router read the same words as for every other role
                   + [str(c) for c in pt.get("codes") or []]}
    elif role == IDENTITY_ANCHOR_ROLE:
        verdict = identity_anchor_verdict(db, cand, judges,
                                          _binding(db, exp, slug, version, release))
    elif role == ANCHOR_SIDE_ROLE:
        verdict = side_view_verdict(cand, _binding(db, exp, slug, version, release))
    else:
        verdict = CG.evaluate(db, cand, judges=judges)
    rec = record_candidate(db, cand, verdict, method="autonomous", run=key, stage=stage,
                           attempt=plan_attempt)
    if paid:
        _complete_paid_generation(db, key, call_token, rec["candidate_id"])
    return {**rec, "technical_status": verdict["technical_status"],
            "publishable": verdict["publishable"], "cost_cad": cost, "attempt": plan_attempt}


def side_view_verdict(cand: dict, bind: dict) -> dict:
    """IMAGE-AD: a vessel's side view on its own is only bound and decodable; whether it
    shows the CIR's wall is decided with the top-down view, as one pair, by the anchor's
    fidelity verifier (`fidelity.verify_anchor(side=...)`). Never publishable."""
    q = CG.quality(cand["data"])
    tech = CG.worst(bind["status"], q["status"])
    return {"sha256": cand["sha256"], "listing": cand.get("listing", ""),
            "checks": {"binding": bind, "quality": q}, "technical_status": tech,
            "publishable": False,
            "publication": {"publishable": False, "blockers": [
                "a vessel's side view is half of its fidelity anchor, never a gallery frame"]},
            "failure_categories": sorted({CG.FAILURE_CATEGORY[k] for k, c in (
                ("binding", bind), ("quality", q)) if c["status"] == CG.FAIL})}


def is_vessel_release(db, slug: str, version: str) -> bool:
    """Whether the certified CIR is a vessel (its anchor needs a side view). Unreadable is
    False: the anchor verifier then reads the CIR itself and refuses by name."""
    try:
        from ..publish.release_gates import _release
        from . import vessel

        cir, _rh = _release(db, slug, version)
        return bool(cir is not None and vessel.is_vessel(cir))
    except Exception:  # noqa: BLE001
        return False


def _anchor_side_bytes(db, side: dict | None) -> dict | None:
    """The recorded side view's bytes, checked against its sha256, or None."""
    if not side or not side.get("sha256"):
        return None
    from ..core.artifacts import ArtifactStore

    try:
        data = ArtifactStore().get(side["sha256"], db=db)
    except Exception:  # noqa: BLE001 - bytes gone: the pair cannot be judged
        return None
    if not data or hashlib.sha256(data).hexdigest() != side["sha256"]:
        return None
    return {"candidate_id": side.get("candidate_id"), "sha256": side["sha256"], "data": data}


def identity_anchor_verdict(db, cand: dict, judges, bind: dict) -> dict:
    """The stage-A anchor's verdict: identity, body proportions, outfit (registry and
    consistency), anatomy and realism, plus the release binding. It is an intermediate
    reference, never a gallery frame, so the listing image-quality floor (2000 px) and the
    gallery role check do not apply to it, and it is never publishable."""
    reserved = outfits.get(db, cand["outfit_id"]) if cand.get("outfit_id") else None
    checks = {"binding": bind,
              "identity": CG._judge(judges, "identity", cand),
              "body_proportions": CG._judge(judges, "body_proportions", cand),
              "outfit_distinctness": outfits.distinctness(db, cand.get("outfit_id"),
                                                          cand.get("listing", "")),
              "outfit_consistency": (CG._judge(judges, "outfit_consistency", cand, reserved)
                                     if reserved else CG._c(CG.UNKNOWN, "no reserved outfit")),
              "anatomy": CG._judge(judges, "anatomy", cand),
              "realism": CG._judge(judges, "realism", cand)}
    # Review VISUAL D1 A-1 (owner V3 condition): through gate_status, so a fixture-labelled
    # identity PASS never makes Laura's identity anchor "accepted" without the owner's review.
    tech = CG.technical_of(checks)
    cats = sorted({CG.FAILURE_CATEGORY[k] for k, c in checks.items()
                   if c["status"] == CG.FAIL and k in CG.FAILURE_CATEGORY})
    for c in checks.values():
        if c.get("status") in (CG.FAIL, CG.UNKNOWN):
            cats += [str(x) for x in c.get("codes") or [] if str(x) not in cats]
    return {"sha256": cand["sha256"], "listing": cand.get("listing", ""), "checks": checks,
            "technical_status": tech, "publishable": False,
            "publication": {"publishable": False, "blockers": [
                "the identity anchor is an intermediate reference, never a gallery frame"]},
            "failure_categories": cats,
            "unknown": CG.unknown_of(checks)}


def _controlled_of(db, key: str) -> int | None:
    """The controlled run a namespaced orchestrator run belongs to (W-VISNEXT2)."""
    if "#" not in key:
        return None
    rec = _stage_data(db, key).get("_controlled") or {}
    return int(rec.get("run_id") or 0) or None


def _binding(db, exp, slug, version, release) -> dict:
    """The release binding: the certified one, or (EXPERIMENT mode only) the experiment's
    content-identity binding, which is never a certification."""
    if exp is not None:
        from . import experiment as XP

        got = XP.binding(db, slug, version, release)
        if got is not None:
            return got
    return CG.binding(db, slug, version, release)


# ---- the stages --------------------------------------------------------------------------

def _next(stage: str) -> str | None:
    names = [s for s, _ in STAGES]
    i = names.index(stage)
    return names[i + 1] if i + 1 < len(names) else None


# ---- IMAGE-STALE-REFS: the prepared references are always this release's current render -----
#
# Production 19i23: `prepare_references` ran once per run and every later stage read the stored
# references back. Batch 19i16 (pattern-refs 3.1.3 -> 3.1.4) changed what a vessel's layout and
# rules references render; runs prepared under 3.1.3 and later restarted at product_generation
# (method and provider redrives resume there) handed the 3.1.3 bytes to a generator whose
# binding check renders 3.1.4, and were refused: "the product references handed in are not the
# bytes this release renders". The check is right. The stored references now carry the
# renderer version and epoch they were made under, and a stage that would hand them on
# re-prepares them (a deterministic, free render) when either differs.

def references_version() -> str:
    """The reference renderers' version: pattern references 4-7 and the certified-PDF pages
    (without the environment's pdfium build). Only code changes move it."""
    from ..creative import pattern_refs

    return f"{pattern_refs.VERSION}|{_stable_pdf_page_refs_version()}"


def _prepare_and_store(db, key: str, gen, *, slug, version, release, bind) -> list | str:
    """The generator's references for this release, stored; a block reason on a bad kind."""
    refs = []
    for r in gen.prepare_references(slug=slug, version=version, release=release,
                                    cir_fingerprint=bind.get("cir_fingerprint")):
        if r.get("kind") not in CG.REFERENCE_KINDS:
            return f"generator returned an unknown reference kind {r.get('kind')!r}"
        sha = store_bytes(db, r["data"], key=f"{key}/ref", why="image reference")
        refs.append({"kind": r["kind"], "sha256": sha, "label": r.get("label", "")})
    return refs


MAX_SUPERSEDED_REFERENCE_SETS = 8


def _current_references(db, key: str, gen, *, slug, version, release, bind,
                        epoch: int) -> list | str:
    """The run's stored references, re-prepared first when they were made by another
    reference-renderer version or in another restart epoch (or carry no stamp: written
    before stamps existed). The superseded hashes are kept in the record as provenance. The
    run's stage, status, calls and spend are untouched; nothing is sent or spent."""
    from sqlalchemy.orm.attributes import flag_modified

    want = references_version()
    rec = dict(_stage_data(db, key).get("prepare_references") or {})
    outs = dict(rec.get("outputs") or {})
    refs = list(outs.get("references") or [])
    if outs.get("references_version") == want and int(outs.get("epoch") or 0) == epoch:
        return refs
    fresh = _prepare_and_store(db, key, gen, slug=slug, version=version, release=release,
                               bind=bind)
    if isinstance(fresh, str):
        return fresh
    old = [r.get("sha256") for r in refs]
    new_outs = {**outs, "references": fresh, "references_version": want, "epoch": epoch,
                "refreshed_at": _now().isoformat()}
    if old != [r["sha256"] for r in fresh]:
        sup = list(outs.get("superseded") or [])
        made = outs.get("references_version") or "an unstamped renderer"
        sup.append({"sha256s": old, "references_version": outs.get("references_version"),
                    "epoch": outs.get("epoch"), "at": _now().isoformat(),
                    "why": f"prepared under {made} (epoch {outs.get('epoch')}); this "
                           f"release renders {want} (epoch {epoch})"})
        new_outs["superseded"] = sup[-MAX_SUPERSEDED_REFERENCE_SETS:]
    with db.session() as s:
        r = _run_locked(s, key)
        st = dict(r.stages or {})
        st["prepare_references"] = {**rec, "outputs": new_outs}
        r.stages = st
        flag_modified(r, "stages")
    return fresh


def run_stage(db, inputs: dict, *, follow, generator=None, judges=None) -> dict:
    """Run one stage and enqueue the next (see `_run_stage`). A controlled run (W-VISNEXT2)
    mirrors its end state onto its controlled-experiment record."""
    out = _run_stage(db, inputs, follow=follow, generator=generator, judges=judges)
    if inputs.get("controlled_run_id") and out.get("run_key"):
        from ..experiments import controlled as CX

        CX.sync_pipeline(db, int(inputs["controlled_run_id"]), out["run_key"])
    return out


_ADMISSION_WHY = ("D-OWNER-SPEND-ORDER: paid image generation starts only for a release the "
                  "sale pipeline admitted (certified, selected for sale, every non-image gate "
                  "PASS, within the per-listing cap and the month ceiling)")


def _spend_admitted(db, gen, exp, controlled, slug, version, release) -> bool:
    """Whether this run may call its generator. A known-free generator (a test double or a
    deterministic renderer) spends nothing; an experiment or an owner-authorised controlled
    run carries its own authorization and caps. Otherwise -- a paid generator, or none wired
    yet -- only a release `publish.sale_pipeline` admitted may proceed. Unreadable is no."""
    if exp is not None or controlled:
        return True
    if gen is not None and getattr(gen, "paid", True) is False:
        return True
    try:
        from ..publish import sale_pipeline

        return sale_pipeline.spend_admitted(db, slug, version, release)
    except Exception:  # noqa: BLE001 - unreadable admission never spends
        return False


def _sale_owned(db, slug: str, version: str, release: str) -> bool:
    """Whether `publish.sale_pipeline` holds a run for exactly this release. Unreadable is
    treated as owned, so its (stricter) spend gate is read first."""
    try:
        from ..publish import sale_pipeline

        return sale_pipeline.get(db, slug, version, release) is not None
    except Exception:  # noqa: BLE001
        return True


def _run_stage(db, inputs: dict, *, follow, generator=None, judges=None) -> dict:
    """Run one stage and enqueue the next. `follow(inputs, idempotency_key)` enqueues."""
    slug, version, release = inputs["slug"], inputs["version"], str(inputs.get("release") or "")
    stage, round_ = inputs.get("stage") or STAGES[0][0], int(inputs.get("round") or 0)
    if stage not in STAGE_STATE:
        raise ValueError(f"unknown stage {stage!r}")
    exp = None
    if inputs.get("experiment"):
        # W4-WRAPTEST: EXPERIMENT mode. Scratch database, an opened experiment for this exact
        # content and an installed context, or a refusal; never a silent fallback.
        from . import experiment as XP

        exp = XP.context_for(db, slug, version, release)
    ns = str(inputs.get("ns") or "")
    controlled = int(inputs.get("controlled_run_id") or 0) or None
    if ns or controlled:
        from ..experiments import controlled as CX

        CX.require_pipeline_run(db, controlled, ns=ns, slug=slug, version=version,
                                release=release)
    route = str(inputs.get("route") or "")
    if route and route != SP.FLUX_ROUTE:
        raise ValueError(f"unknown gallery route {route!r}")
    key = _ensure_run(db, slug, version, release, ns, route)
    if controlled:
        from sqlalchemy.orm.attributes import flag_modified

        with db.session() as s:
            r_ = _run_locked(s, key)
            st_ = dict(r_.stages or {})
            if not st_.get("_controlled"):
                st_["_controlled"] = {"run_id": controlled, "ns": ns}
                r_.stages = st_
                flag_modified(r_, "stages")
    run = get_run(db, key)
    epoch = int(inputs.get("epoch") or 0)
    if epoch != run.get("restarts", 0):
        # a job from before (or beyond) the run's current restart epoch: superseded
        return {"run_key": key, "skipped": True,
                "why": f"job epoch {epoch} is not the run's epoch {run.get('restarts', 0)}"}
    if run["state"] in ("blocked", "ready_for_owner_review", "approved_for_publication"):
        return {"run_key": key, "skipped": True, "why": f"run is {run['status']}"}
    if run["state"] == AWAITING_PRE_IMAGE and stage != "retrieve_release":
        # D-OWNER-SPEND-ORDER: an admitted re-entry starts again at retrieve_release.
        return {"run_key": key, "skipped": True, "why": f"run is {run['status']}"}
    if generator is not None:
        gen = generator
    elif exp is not None:
        gen = exp.generator(db)
    else:
        gen = resolve_generator(db)
    if exp is None and not controlled and (route == SP.FLUX_ROUTE
                                           or bool(getattr(gen, "paid", False))):
        # b17-c A3 (D-OWNER-SPEND-ORDER): every stage of a paid gallery -- the FLUX route
        # always, the campaign route whenever its generator is paid -- re-checks for-sale
        # admission before it does anything. Not admitted parks it without spend.
        # Batch 19: both spend admissions must hold (vis-gallery `sale_admission` and the
        # sale pipeline's `spend_admitted`). Where the sale pipeline owns the release, or the
        # stage itself spends, its gate is read first and the run waits in its state.
        if (stage in SPENDING_STAGES or _sale_owned(db, slug, version, release)) and \
                not _spend_admitted(db, gen, exp, controlled, slug, version, release):
            return {"run_key": key, **_update(db, key, stage=stage, status=AWAITING_PRE_IMAGE,
                                               record={"outputs": {"waiting": _ADMISSION_WHY}})}
        adm = sale_admission(db, slug, version, release)
        if not adm["admitted"]:
            return _park_for_sale(db, key, stage, adm)
    judges = judges or (exp.judges(db) if exp is not None else CG.RealJudges(db))
    if exp is not None:
        plan = exp.plan
    elif route == SP.FLUX_ROUTE:
        plan = SP.flux_campaign_plan(run["listing"]) if _is_launch(run["listing"]) else None
    else:
        plan = SP.campaign_plan(run["listing"]) if _is_launch(run["listing"]) else None
    max_att = exp.max_attempts_per_role if exp is not None else MAX_ATTEMPTS_PER_ROLE

    def operation_for(role: str, segment: str = "") -> str:
        identity = [key, stage, round_, epoch, role, segment]
        if exp is not None:
            # Legacy scratch experiments can use the same run key as a normal
            # run. Their candidates must not satisfy each other's replay key.
            identity.append("experiment")
        material = json.dumps(identity, separators=(",", ":"))
        return hashlib.sha256(material.encode()).hexdigest()

    def go(next_stage: str | None, *, rnd: int = 0):
        if next_stage is None:
            return None
        nxt = {"slug": slug, "version": version, "release": release, "stage": next_stage,
               "round": rnd}
        if exp is not None:
            nxt["experiment"] = True
        if route:
            nxt["route"] = route
        if epoch:
            nxt["epoch"] = epoch
        if ns:
            nxt.update(ns=ns, controlled_run_id=controlled)
        follow(nxt, stage_key(slug, version, release, next_stage, rnd, epoch, ns, route))
        return next_stage

    def block(why: str, *, exhausted: bool = False, record: dict | None = None):
        return {"run_key": key, **_update(db, key, stage=stage, blocked=why, exhausted=exhausted,
                                          record=record or {"outputs": {"blocked": why}})}

    st = STAGE_STATE[stage]
    if stage == "retrieve_release":
        try:  # the first learning example (owner manual wrap experiment); idempotent
            from .repair_routes import seed_experiments

            seed_experiments(db)
        except Exception:  # noqa: BLE001 - learning seed never blocks production
            pass
        bind = _binding(db, exp, slug, version, release)
        if bind["status"] == CG.FAIL and "no certified release" in bind["why"]:
            return {"run_key": key, **_update(db, key, stage=stage,
                                               status="awaiting_certified_pattern",
                                               record={"evidence": bind})}
        if bind["status"] != CG.PASS:
            return block(f"release binding {bind['status']}: {bind['why']}",
                         record={"evidence": bind})
        if plan is None:
            return block(f"{run['listing']} has no shot plan (not a Launch-0 listing)")
        if not _spend_admitted(db, gen, exp, controlled, slug, version, release):
            return {"run_key": key, **_update(db, key, stage=stage, status=AWAITING_PRE_IMAGE,
                                               record={"evidence": bind, "outputs": {
                                                   "waiting": _ADMISSION_WHY}})}
        rec = {"inputs": dict(inputs), "evidence": bind,
               "outputs": {"plan_roles": [r["role"] for r in plan["roles"]],
                           "route": route or "campaign", "family": plan.get("family")}}
        if exp is not None:
            rec = {**rec, "experiment": True, "label": exp.label,
                   "certification": exp.reg["certification"]}
        _update(db, key, stage=stage, status=st, record=rec)
        return {"run_key": key, "next": go(_next(stage))}

    data = _stage_data(db, key)
    bind = (data.get("retrieve_release") or {}).get("evidence") or {}

    if stage in SPENDING_STAGES and not _spend_admitted(db, gen, exp, controlled, slug,
                                                        version, release):
        # a continuation queued before admission was withdrawn (or before this rule) waits,
        # never spends
        return {"run_key": key, **_update(db, key, stage=stage, status=AWAITING_PRE_IMAGE,
                                           record={"outputs": {"waiting": _ADMISSION_WHY}})}
    if gen is None and stage in ("prepare_references", "product_generation",
                                 "lifestyle_generation", "remaining_roles", "repair"):
        return block("no image generator is wired: W-FLUXAPI's stage functions have not "
                     "landed (gateway/images.py and the reference generator)")

    try:
        if stage == "prepare_references":
            refs = _prepare_and_store(db, key, gen, slug=slug, version=version,
                                      release=release, bind=bind)
            if isinstance(refs, str):
                return block(refs)
            _update(db, key, stage=stage, status=st,
                    record={"outputs": {"references": refs,
                                        "references_version": references_version(),
                                        "epoch": epoch}, "cost_cad": 0.0})
            return {"run_key": key, "next": go(_next(stage))}

        refs = (data.get("prepare_references") or {}).get("outputs", {}).get("references", [])
        if refs and stage in SPENDING_STAGES:
            # IMAGE-STALE-REFS: never hand the generator references another renderer made.
            refs = _current_references(db, key, gen, slug=slug, version=version,
                                       release=release, bind=bind, epoch=epoch)
            if isinstance(refs, str):
                return block(refs)
        ref_bytes = None

        def _refs_with_bytes():
            from ..core.artifacts import ArtifactStore

            nonlocal ref_bytes
            if ref_bytes is None:
                ref_bytes = [{**r, "data": ArtifactStore().get(r["sha256"], db=db)}
                             for r in refs]
            return ref_bytes

        if stage == "product_generation":
            attempt = _attempts(db, key, ANCHOR_ROLE) + 1
            operation = operation_for(ANCHOR_ROLE)
            # A retried job may recover its already-recorded candidate even when it
            # used the last attempt. A different invocation must respect the cap.
            recovered = _recover_generation(db, key, operation=operation, stage=stage,
                                            role=ANCHOR_ROLE, slug=slug, version=version,
                                            release=release, experiment=exp is not None)
            if recovered is None and attempt > max_att:
                return block(f"product generation attempt cap {max_att} reached",
                             exhausted=True)
            # A regeneration after a fidelity FAIL carries the targeted repair for its codes
            # when every code has a route; otherwise it is a plain retry within the cap.
            prior = (_best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
                     if attempt > 1 else None)
            repair = (_repair_for(prior) if prior and prior.get("technical_status") == "FAIL"
                      else None)
            # ENG-MANUAL-METHOD: a correction edits the failed candidate (and, for a vessel, the
            # side view judged with it), naming the gate's codes -- not a blind regeneration.
            fix = (_correction_refs(db, prior) if repair and getattr(
                gen, "accepts_manual_method", False) else {})
            side = None
            if recovered is None and is_vessel_release(db, slug, version):
                # IMAGE-AD (V2): a vessel is verified from a top-down and a side view of it
                # standing. The side view is its own paid render, through the same budget,
                # run cap and paid-provider gate (per-gallery, daily), with its own replay
                # key, so a redrive recovers it instead of buying it again.
                side_op = operation_for(ANCHOR_SIDE_ROLE)
                got_side = _recover_generation(
                    db, key, operation=side_op, stage=stage, role=ANCHOR_SIDE_ROLE,
                    slug=slug, version=version, release=release,
                    experiment=exp is not None) or _generate(
                    db, key, gen, slug=slug, version=version, release=release,
                    role=ANCHOR_SIDE_ROLE, stage=stage, laura=False, judges=judges,
                    brief="the finished piece alone, standing, seen from the side at eye "
                          "level, plain background, the whole wall and rim visible",
                    refs=_refs_with_bytes() + fix.get("side", []), outfit=None,
                    plan_attempt=attempt, repair=repair if fix.get("side") else None,
                    exp=exp, operation=side_op)
                if got_side.get("provider_error"):
                    return block(f"vessel side view could not be rendered: "
                                 f"{got_side['provider_error']}")
                side = _anchor_side_bytes(db, got_side)
                if side is None:
                    return block("vessel side view bytes unavailable; review required")
            got = recovered or _generate(db, key, gen, slug=slug, version=version, release=release,
                            role=ANCHOR_ROLE, stage=stage, laura=False, judges=judges,
                            brief="the finished piece alone, flat, plain background, every "
                                  "piece visible", refs=_refs_with_bytes() + fix.get(
                                      "anchor", []), outfit=None,
                            plan_attempt=attempt, repair=repair, exp=exp,
                            operation=operation, side=side)
            _update(db, key, stage=stage, status=st,
                    record={"outputs": got, "cost_cad": got.get("cost_cad")})
            return {"run_key": key, "next": go(_next(stage), rnd=got.get("attempt", attempt) - 1)}

        if stage == "fidelity_gate":
            if inputs.get("rejudge"):
                # IMAGE-FIDELITY-2: every stored anchor frame FAILed by the older verifier
                # (bounded) is judged again; nothing is generated, no attempt is added.
                for cid in rejudge_candidate_ids(db, key)[:MAX_REJUDGE_CANDIDATES]:
                    reverify(db, cid, judges=judges, exp=exp)
            elif inputs.get("reverify"):
                # W-VISNEXT restart: the stored anchor bytes are judged again with today's
                # judges; nothing is regenerated and no attempt is added.
                b = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
                if b:
                    reverify(db, b["candidate_id"], judges=judges, exp=exp)
            best = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
            status = (best or {}).get("technical_status", "UNKNOWN")
            record = {"evidence": best}
            if status == "PASS":
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go(_next(stage))}
            if status == "FAIL" and exp is not None and not (_repair_for(best) or {}).get(
                    "directives"):
                return block(f"{exp.label}: the flat lay failed a hard Product Truth check "
                             f"and no bounded correction is routable "
                             f"({(best or {}).get('failure_categories')}); stopped early, "
                             f"nothing more is spent", exhausted=True, record=record)
            if status == "FAIL" and _attempts(db, key, ANCHOR_ROLE) < max_att:
                n = _attempts(db, key, ANCHOR_ROLE)
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go("product_generation", rnd=n)}
            if status == "FAIL":
                return block(f"product fidelity FAIL after {max_att} attempts: "
                             f"{(best or {}).get('failed')}", exhausted=True, record=record)
            fid = (best or {}).get("fidelity") or {}
            return block("product fidelity cannot be verified: the fidelity verifier "
                         f"(visual.fidelity) reads UNKNOWN on {fid.get('unknown') or '?'}"
                         + (f" ({'; '.join(fid['needs'])})" if fid.get("needs") else "")
                         + f". Unknown: {(best or {}).get('unknown')}", record=record)

        laura_roles = [r for r in SP.generated_roles(plan) if r["laura"]]
        if stage == "load_laura_references":
            from . import canonical_registry

            if not laura_roles:
                _update(db, key, stage=stage, status=st,
                        record={"outputs": {"laura": "not in this listing's shot plan"}})
                return {"run_key": key, "next": go(_next(stage))}
            # F-733 (WIRE1): Laura is resolved from the canonical asset registry -- manifest
            # bytes, approved views, conditioning packages and the approval record -- never
            # from a constant the stage remembers.
            reg = canonical_registry.resolve(db)
            if not reg.get("ok"):
                views = [p for p in reg.get("problems") or [] if p.startswith("view ")]
                if views:
                    # a canonical view that cannot be sent is reduced identity conditioning,
                    # refused here before any Laura frame is generated
                    return block(f"reduced identity conditioning: {reg.get('problems')}")
                return block(f"Laura's canonical references failed verification: "
                             f"{reg.get('problems')}")
            _update(db, key, stage=stage, status=st, record={"outputs": {
                "identity_id": reg["identity_id"], "registry": reg["registry"],
                "references": {f: v["sha256"] for f, v in reg["approved_views"].items()}}})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "reserve_outfit":
            if not laura_roles:
                _update(db, key, stage=stage, status=st, record={"outputs": {"outfit": None}})
                return {"run_key": key, "next": go(_next(stage))}
            pick = outfits.reserved_for(db, run["listing"])
            styled = None
            retire = None
            if (exp is not None and pick is not None and exp.outfit_rejects is not None
                    and exp.outfit_rejects(pick)):
                # Experiment: the outfit already held for this listing (e.g. the owner's manual
                # test outfit, seeded as wardrobe history) is one the brief excludes; a new one
                # is chosen and the old one retired, never reused.
                retire, pick = pick["outfit_id"], None
            if pick is None:
                # D-W4-LAURA-FLUX3 §5: Creative chooses the outfit and concept; the owner
                # does not. Deterministic, and it avoids outfits/settings other listings use.
                from . import styling

                styled = (exp.outfit_selector(db, run["listing"])
                          if exp is not None and exp.outfit_selector is not None
                          else styling.select_for_listing(db, run["listing"]))
                if not styled.get("outfit"):
                    return block(f"automatic styling found no unused complete outfit: "
                                 f"{styled.get('why')}")
                o = styled["outfit"]
                try:
                    outfits.register(db, outfit_id=o["outfit_id"], garments=o["garments"],
                                     colours=o["colours"], concept=styled["concept"])
                    pick = outfits.approve(db, o["outfit_id"],
                                           approved_by=f"creative_director:{styling.STYLING_VERSION}")
                except outfits.OutfitRefused as exc:
                    return block(f"automatic styling refused by the wardrobe registry: {exc}")
            if retire:
                rep = outfits.replace(db, retire, pick["outfit_id"], run["listing"])
                got = (outfits.reserve(db, pick["outfit_id"], run["listing"])
                       if rep.get("replaced") else rep)
                got = {**got, "retired": retire}
            else:
                got = outfits.reserve(db, pick["outfit_id"], run["listing"])
            if got.get("status") != "PASS":
                return block(f"outfit reservation {got.get('status')}: {got.get('why')}")
            _update(db, key, stage=stage, status=st, outfit_id=pick["outfit_id"],
                    record={"outputs": {**got, "styling": styled,
                                        "concept": (outfits.get(db, pick["outfit_id"]) or {})
                                        .get("concept")}})
            return {"run_key": key, "next": go(_next(stage))}

        def laura_refs():
            from . import canonical
            out = []
            if canonical.verify().get("ok"):
                from pathlib import Path
                for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items():
                    path = canonical.reference_file(frame)
                    if path:  # '' = not the recorded bytes: never a substitute
                        data_ = Path(path).read_bytes()
                        if hashlib.sha256(data_).hexdigest() == sha:
                            out.append({"kind": "laura_canonical", "sha256": sha,
                                        "frame": frame, "data": data_})
            if len(out) != len(canonical.CURRENT_REFERENCE_HASHES):
                # D-W4-LAURA-FLUX3 §1: never continue with reduced identity conditioning.
                raise ConditioningRefused(
                    f"{len(out)} of {len(canonical.CURRENT_REFERENCE_HASHES)} canonical Laura "
                    f"references validated; generation with reduced identity conditioning is "
                    f"refused")
            return out

        owner_method = bool(getattr(gen, "accepts_owner_method", False)) and exp is None
        owner_cache = {}

        def owner_inputs():
            """(accepted product frame ref, canonical Laura refs): both by their bytes."""
            if "v" not in owner_cache:
                pf = _accepted_product_frame(db, key, run["listing"])
                if pf is None:
                    raise ConditioningRefused("no product frame has been accepted through the "
                                              "fidelity gate; Laura frames come after it")
                owner_cache["v"] = (pf, laura_refs())
            return owner_cache["v"]

        def owner_provenance(pf, lr, outfit_):
            from . import canonical

            return reference_provenance(pf, lr, outfit_id=(outfit_ or {}).get("outfit_id"),
                                        identity_id=canonical.IDENTITY_ID)

        manual_cache = {}

        def manual_extras(r):
            """ENG-MANUAL-METHOD: a vessel's accepted side view, and for every frame after the
            listing's lifestyle frame, that accepted frame as the campaign reference (room and
            campaign continuity). Empty for a generator that does not declare the method."""
            if not getattr(gen, "accepts_manual_method", False):
                return []
            if "side" not in manual_cache:
                manual_cache["side"] = _accepted_product_side(db, key, run["listing"])
            out_ = [manual_cache["side"]] if manual_cache["side"] else []
            if r["job"] != "LIFESTYLE":
                if "campaign" not in manual_cache:
                    c_ = _accepted_lifestyle(db, key, run["listing"], plan, slug=run["slug"],
                                             version=run["version"], release=run["release"])
                    manual_cache["campaign"] = ({**c_, "label": CAMPAIGN_LABEL}
                                                if c_ else None)
                if manual_cache["campaign"]:
                    out_.append(manual_cache["campaign"])
            return out_

        def gen_roles(roles, rnd_stage, repairs=None):
            outs = []
            outfit = outfits.get(db, run["outfit_id"]) if run["outfit_id"] else None
            for r in roles:
                if r.get("route") and not repairs:
                    from . import gallery_recovery

                    prior_ = gallery_recovery.already(db, key, r["role"])
                    if prior_ is not None:
                        outs.append(prior_)
                        continue
                attempt = _attempts(db, key, r["role"]) + 1
                if attempt > max_att and not (r["laura"] and owner_method):
                    recovered = _recover_generation(
                        db, key, operation=operation_for(r["role"]), stage=rnd_stage,
                        role=r["role"], slug=slug, version=version, release=release,
                        experiment=exp is not None)
                    if recovered is not None:
                        outs.append(recovered)
                    continue
                if r["laura"] and owner_method:
                    # ENG-IMAGES-LAURA: the accepted product frame + the canonical three. The
                    # pattern references ride along only so the generator can bind the release;
                    # it does not transmit them. Idempotent per input hashes: the operation is
                    # keyed by what is sent (not by the restart epoch), so a redrive recovers
                    # the frame already bought instead of buying it again.
                    if not outfit:
                        raise ConditioningRefused("a Laura frame needs the outfit already "
                                                  "assigned to this listing")
                    pf, lr = owner_inputs()
                    prov = owner_provenance(pf, lr, outfit)
                    extras = manual_extras(r)
                    seg = prov["input_digest"]
                    if extras:
                        # the extra inputs key the replay too: different inputs, a new frame
                        seg += ":manual:" + ",".join(e["sha256"] for e in extras)
                        prov = {**prov, "manual_method": MANUAL_METHOD_VERSION,
                                "extra_images": [{"label": e["label"], "sha256": e["sha256"]}
                                                 for e in extras]}
                    if repairs:
                        seg += ":repair:" + str(round_) + ":" + hashlib.sha256(json.dumps(
                            (repairs or {}).get(r["role"]), sort_keys=True,
                            default=str).encode()).hexdigest()
                    op = _owner_operation(key, rnd_stage, r["role"], seg, exp is not None)
                    if attempt > max_att:
                        recovered = _recover_generation(
                            db, key, operation=op, stage=rnd_stage, role=r["role"],
                            slug=slug, version=version, release=release,
                            experiment=exp is not None)
                        if recovered is not None:
                            outs.append(recovered)
                        continue
                    outs.append(_generate(db, key, gen, slug=slug, version=version,
                                          release=release, role=r["role"], stage=rnd_stage,
                                          route=str(r.get("route") or ""), laura=True,
                                          judges=judges, brief=r["brief"] or
                                          f"{r['job']}: the finished piece",
                                          refs=_refs_with_bytes() + lr + [pf] + extras,
                                          outfit=outfit,
                                          plan_attempt=attempt,
                                          repair=(repairs or {}).get(r["role"]), exp=exp,
                                          operation=op, reference_provenance=prov))
                    continue
                refs_ = _refs_with_bytes() + (laura_refs() if r["laura"] else [])
                if not r["laura"]:
                    refs_ = refs_ + manual_extras(r)
                if (r["laura"] and outfit and outfit.get("approved_reference")
                        and getattr(gen, "accepts_outfit_reference", False)):
                    # OWNERIMG E6: the outfit's approved reference image, as a clothing
                    # reference only (kind prior_candidate; never an identity reference).
                    # Sent only to a generator that declares it can carry one.
                    from ..core.artifacts import ArtifactStore

                    ref = ArtifactStore().get(outfit["approved_reference"], db=db)
                    if ref:
                        refs_ = refs_ + [{"kind": "prior_candidate", "label": "outfit_reference",
                                          "sha256": outfit["approved_reference"], "data": ref}]
                if r["laura"] and getattr(gen, "accepts_staged_method", False):
                    # W-VISNEXT2 stage A: the listing's accepted identity anchor, as identity
                    # context after the canonical three (never instead of them).
                    ia = _accepted_identity_anchor(db, key)
                    if ia:
                        refs_ = refs_ + [ia]
                    # Stage D: a non-LIFESTYLE Laura role edits the accepted lifestyle frame,
                    # so the outfit stays identical across the listing.
                    if r["job"] != "LIFESTYLE":
                        base_ = _accepted_lifestyle(db, key, run["listing"], plan,
                                                    slug=run["slug"], version=run["version"],
                                                    release=run["release"])
                        if base_:
                            refs_ = refs_ + [base_]
                if r.get("route") and attempt == 1 and not repairs:
                    # D-OWNER-FLUX-GALLERY: recovery first -- an image already made for this
                    # release and role is re-judged under the route before one is bought.
                    from . import gallery_recovery

                    got_ = gallery_recovery.recover(
                        db, key, slug=slug, version=version, release=release,
                        listing=run["listing"], role=r["role"], laura=bool(r["laura"]),
                        outfit_id=(outfit or {}).get("outfit_id") if r["laura"] else None,
                        judges=judges, route=str(r["route"]), stage=rnd_stage)
                    if got_ is not None:
                        outs.append(got_)
                        continue
                outs.append(_generate(db, key, gen, slug=slug, version=version,
                                      release=release, role=r["role"], stage=rnd_stage,
                                      route=str(r.get("route") or ""),
                                      laura=r["laura"], judges=judges, brief=r["brief"] or
                                      f"{r['job']}: the finished piece", refs=refs_,
                                      outfit=outfit if r["laura"] else None,
                                      plan_attempt=attempt,
                                      repair=(repairs or {}).get(r["role"]), exp=exp,
                                      operation=operation_for(r["role"])))
            return outs

        if stage == "identity_anchor":
            return _stage_identity_anchor(db, key, run, inputs, gen=gen, judges=judges, exp=exp,
                                          laura_roles=laura_roles, st=st, go=go, block=block,
                                          refs=_refs_with_bytes, laura_refs=laura_refs,
                                          slug=slug, version=version, release=release,
                                          operation_for=operation_for)

        if stage in ("lifestyle_generation", "remaining_roles") and (
                _accepted_product_frame(db, key, run["listing"]) is None):
            # ENG-IMAGES-LAURA: nothing after step 1 runs (or spends) before a product frame
            # of this gallery is accepted, however the job got here.
            return block("no product frame accepted: lifestyle and every later role start "
                         "only after the product frame passes the fidelity gate")

        if stage == "lifestyle_generation":
            roles = [r for r in SP.generated_roles(plan) if r["job"] == "LIFESTYLE"]
            outs = gen_roles(roles, stage)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs, "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "remaining_roles":
            roles = [r for r in SP.generated_roles(plan) if r["job"] != "LIFESTYLE"]
            outs = gen_roles(roles, stage)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs or {"note": "every other role is covered by the disclosed set "
                                            "or needs a photograph"},
                "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "verification":
            roles = SP.generated_roles(plan)
            if inputs.get("reverify"):
                for r in roles:
                    b = _best(db, listing=run["listing"], role=r["role"], run=key)
                    if b:
                        reverify(db, b["candidate_id"], judges=judges, exp=exp)
            per = {r["role"]: _best(db, listing=run["listing"], role=r["role"], run=key)
                   for r in roles}
            structural = {r["role"]: per[r["role"]]["structural"] for r in roles
                          if (per[r["role"]] or {}).get("technical_status") == "FAIL"
                          and (per[r["role"]] or {}).get("structural")
                          and _repair_for(per[r["role"]]) is None}
            if structural and exp is None:
                # W5-V1 (audit P0-a): a failure no regeneration can change blocks the run
                # here, named, instead of buying repairs that cannot pass. Experiments keep
                # going to their owner card: they never repair it either (see below).
                why = "; ".join(f"{role}: {reason}" for role, reason in sorted(
                    structural.items()))
                return block(f"{why} (structural: the references are pattern-derived, so a "
                             f"regeneration cannot change this; a qualified photographic "
                             f"reference or an owner policy decision is needed)",
                             exhausted=True, record={"evidence": per,
                                                     "structural": structural})
            failing = [r for r in roles if (per[r["role"]] or {}).get("technical_status")
                       == "FAIL" and _attempts(db, key, r["role"]) < max_att
                       and _repair_for(per[r["role"]]) is not None
                       # Experiment: only a routable correction is bought, never a re-roll
                       # of a failure regeneration cannot change.
                       and (exp is None or (_repair_for(per[r["role"]]) or {}).get(
                           "directives"))]
            _update(db, key, stage=stage, status=st, record={"evidence": per})
            if failing and round_ < MAX_REPAIR_ROUNDS:
                return {"run_key": key, "next": go("repair", rnd=round_ + 1)}
            return {"run_key": key, "next": go("gallery_assembly")}

        if stage == "repair":
            roles = SP.generated_roles(plan)
            repairs = {}
            for r in roles:
                b = _best(db, listing=run["listing"], role=r["role"], run=key) or {}
                if b.get("technical_status") == "FAIL" and _repair_for(b) is not None and (
                        exp is None or (_repair_for(b) or {}).get("directives")):
                    repairs[r["role"]] = _repair_for(b)
            failing = [r for r in roles if r["role"] in repairs]
            repick = any(d.get("kind") == "repick_outfit" for rp in repairs.values()
                         for d in rp.get("directives") or [])
            if repick and run["outfit_id"]:
                got = _repick_outfit(db, run["listing"], run["outfit_id"])
                if not got.get("replaced"):
                    return block(f"wardrobe repetition and no distinct outfit could be "
                                 f"re-picked: {got.get('why')}", exhausted=True)
                run["outfit_id"] = got["new"]
                _update(db, key, stage=stage, outfit_id=got["new"])
            outs = gen_roles(failing, stage, repairs)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs, "round": round_, "repairs": repairs,
                "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go("verification", rnd=round_)}
    except BudgetStop as exc:
        return block(f"budget stop: {exc}", exhausted=True)
    except ConditioningRefused as exc:
        return block(f"conditioning refused: {exc}")
    except CapabilityBlocked as exc:
        return block(str(exc))
    except Exception as exc:  # noqa: BLE001 - a generator refusal is a recorded block
        if type(exc).__name__ in ("GeneratorRefused", "StageRefused"):
            return block(f"generator refused: {type(exc).__name__}: {str(exc)[:400]}")
        raise

    if stage == "gallery_assembly":
        view = readiness(db, run["listing"], run_key_=key,
                         plan=plan if (exp is not None or route) else None)
        if exp is not None:
            view = {**view, "experiment": True, "label": exp.label}
            if exp.gallery_builder is not None:
                view["experiment_gallery"] = exp.gallery_builder(db, key)
        _update(db, key, stage=stage, status=st, record={"outputs": view})
        return {"run_key": key, "next": go(_next(stage))}

    if stage == "owner_card":
        view = (data.get("gallery_assembly") or {}).get("outputs") or readiness(
            db, run["listing"], run_key_=key, plan=plan if (exp is not None or route) else None)
        gen_roles_ = [r for r in view["roles"] if r["source"] == "generated"]
        not_ready = [r for r in gen_roles_ if (r.get("candidate") or {}).get(
            "technical_status") != "PASS"]
        card = {"listing": run["listing"], "slug": slug, "version": version,
                "release": release, "roles": view["roles"], "route": route or "campaign",
                "set_check": view["set_check"],
                "publication_blockers": view["publication_blockers"],
                "spent_cad": get_run(db, key)["spent_cad"],
                "recommended_fix": _recommend(not_ready, view),
                "owner_approval_is_not_technical_verification": True}
        card["campaign_consistency"] = view.get("campaign_consistency")
        card["campaign_standard"] = view.get("campaign_standard")
        if exp is None and _controlled_of(db, key):
            from ..experiments import controlled as CX
            from . import experiment as XP

            lbl = CX.label_of_run(db, _controlled_of(db, key))
            card.update(experiment=True, label=lbl, controlled_run_id=_controlled_of(
                db, key), certification={"granted": True, "reasons": [
                    "certified release; this gallery is a controlled experiment's output"]},
                publication_blockers=sorted(set(card["publication_blockers"]) | {
                    f"{lbl}: controlled experiment output, never published"}),
                approvals_are_separate={
                    "visual_approval": "the owner's look at these images only",
                    "technical_certification": "the stored verdicts",
                    "publication_authorization": "NOT AVAILABLE: experiments never publish"})
        if exp is not None:
            from . import experiment as XP

            card.update(experiment=True, label=exp.label,
                        certification=exp.reg["certification"],
                        content_hash=exp.reg["release"],
                        pdf_sha256_by_terminology=exp.reg["pdf_sha256_by_terminology"],
                        gallery=view.get("experiment_gallery"),
                        publication_blockers=sorted(set(card["publication_blockers"]) | set(
                            XP.publication_blockers({"experiment": True}))),
                        approvals_are_separate={
                            "visual_approval": "the owner's look at these images only",
                            "technical_certification": "REFUSED: " + "; ".join(
                                exp.reg["certification"]["reasons"])[:300],
                            "publication_authorization": "NOT AVAILABLE: experiments never "
                                                         "publish"})
        if (view.get("campaign_consistency") or {}).get("status") == CG.FAIL:
            not_ready = not_ready or [{"role": "gallery", "candidate": {
                "technical_status": "FAIL",
                "failed": {"campaign_consistency": view["campaign_consistency"]["why"]}}}]
        if exp is not None and not view["set_check"]["ok"]:
            # An experiment asks the owner for a look, not for a listing: the set check is a
            # publication check, reported as a blocker rather than stopping the card.
            card["publication_blockers"] = sorted(set(card["publication_blockers"]) | {
                f"gallery set check: {p.get('kind')}: {p.get('why')}"
                for p in view["set_check"]["problems"]})
        if not_ready or (not view["set_check"]["ok"] and exp is None):
            why = "; ".join(f"{r['role']}: {(r.get('candidate') or {}).get('technical_status', 'no candidate')}"
                            f" (failed {sorted(((r.get('candidate') or {}).get('failed') or {}))},"
                            f" unknown {(r.get('candidate') or {}).get('unknown')})"
                            for r in not_ready) or str(view["set_check"]["problems"])[:500]
            out_ = {"run_key": key, **_update(db, key, stage=stage, blocked=why[:1500],
                                               exhausted=True, card=card,
                                               record={"outputs": card})}
            return _certify_route(db, key, route, out_)
        out_ = {"run_key": key, **_update(db, key, stage=stage,
                                           status="ready_for_owner_review", card=card,
                                           record={"outputs": card})}
        return _certify_route(db, key, route, out_)
    raise ValueError(f"stage {stage!r} fell through")


def _certify_route(db, key: str, route: str, out: dict) -> dict:
    """D-OWNER-FLUX-GALLERY: a generated-gallery run is judged for its certificate the moment
    its card is assembled -- certified when every frame and set check passes, otherwise its
    blockers (gate, reason, owner, next action) are recorded. The owner's look is not asked."""
    if route != SP.FLUX_ROUTE:
        return out
    try:
        from . import gallery_persist

        got = gallery_persist.certify_gallery(db, key)
        res = {**out, "gallery_certified": bool(got.get("certified")),
               "gallery_blockers": len(got.get("blockers") or [])}
        if not got.get("certified") and got.get("status"):
            # IMAGE-BF (finding B): a gallery verified in every respect but Laura's
            # publication raises ONE owner card (passphrase + TOTP decision); never inferred.
            from . import laura_approval

            card = laura_approval.raise_card(db, key, st=got["status"])
            res["laura_card"] = {k: card.get(k) for k in ("raised", "requirement_key",
                                                           "card_id", "why")}
        return res
    except Exception as exc:  # noqa: BLE001 - a certification error is recorded, never a pass
        return {**out, "gallery_certified": False,
                "gallery_error": f"{type(exc).__name__}: {str(exc)[:200]}"}


# ---- re-verification and restart (W-VISNEXT; OWNERIMG E4) -----------------------------------

def reverify(db, candidate_id: int, *, judges, exp=None) -> dict:
    """Judge one stored candidate's bytes again with `judges`, in place.

    The same image, a new reading: nothing is generated, no attempt is added (attempts are
    counted from candidate rows), and the previous verdict is kept in
    `checks["_reverified"]`. Used when a restart follows a capability change (for example the
    vision judge being funded). UNKNOWN stays UNKNOWN unless the new reading resolves it."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.artifacts import ArtifactStore
    from .image_records import ImageCandidate

    with db.session() as s:
        row = s.get(ImageCandidate, candidate_id)
        if row is None or not row.sha256:
            return {"reverified": False, "why": "no stored candidate"}
        cand = {"slug": row.slug, "version": row.version, "release": row.release,
                "run_key": row.run_key,
                "role": row.role, "provider": row.provider, "model": row.model,
                "prompt": row.prompt, "references": list(row.references or []),
                "laura_present": row.laura_present, "outfit_id": row.outfit_id or None,
                "listing": row.listing, "provenance_kind": row.provenance_kind,
                "identity_evidence": (row.checks or {}).get("_identity_evidence") or {},
                "prompt_version": row.prompt_version,
                "route": ((row.checks or {}).get("_route") or {}).get("route") or ""}
        kept = {k: v for k, v in (row.checks or {}).items()
                if k in ("_route", "_paid_call", "_generation_operation", "_anchor_side",
                         METHOD_KEY)}
        prev = {"technical_status": row.technical_status,
                "failure_categories": list(row.failure_categories or []),
                "unknown": sorted(k for k, c in (row.checks or {}).items()
                                  if isinstance(c, dict) and c.get("status") == "UNKNOWN"),
                "history": list(((row.checks or {}).get("_reverified") or {}).get(
                    "history") or [])}
        sha = row.sha256
    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception as exc:  # noqa: BLE001 - bytes gone: nothing can be re-read
        return {"reverified": False, "why": f"bytes unavailable ({type(exc).__name__})"}
    cand = {**cand, "data": data, "sha256": sha}
    if exp is not None:
        cand["experiment"] = True
    if cand["role"] == ANCHOR_ROLE:
        # IMAGE-AD: a vessel anchor is re-judged as the same pair it was generated as
        side = _anchor_side_bytes(db, kept.get("_anchor_side"))
        if side is not None:
            cand["side_data"] = side["data"]
        bind = _binding(db, exp, cand["slug"], cand["version"], cand["release"])
        pt = judges.product_truth({**cand}, bind)
        q = CG.quality(data)
        verdict = {"checks": {"binding": bind, "product_truth": pt, "quality": q},
                   "technical_status": CG.worst(bind["status"], pt["status"], q["status"]),
                   "publishable": False, "publication": {},
                   "failure_categories": sorted(
                       {CG.FAILURE_CATEGORY[k] for k, c in (("binding", bind),
                        ("product_truth", pt), ("quality", q)) if c["status"] == CG.FAIL})
                   + [str(c) for c in pt.get("codes") or []]}
    elif cand["role"] == IDENTITY_ANCHOR_ROLE:
        verdict = identity_anchor_verdict(db, cand, judges, _binding(
            db, exp, cand["slug"], cand["version"], cand["release"]))
    else:
        verdict = CG.evaluate(db, cand, judges=judges, record_outfit_use=False)
    tech = verdict["technical_status"]
    with db.session() as s:
        row = s.get(ImageCandidate, candidate_id)
        row.checks = {**verdict["checks"], "_publication": verdict.get("publication") or {},
                      **kept, "_identity_evidence": cand["identity_evidence"],
                      "_reverified": {"history": prev["history"] + [{
                          "at": _now().isoformat(), "previous_status": prev["technical_status"],
                          "previous_failure_categories": prev["failure_categories"],
                          "previous_unknown": prev["unknown"]}]}}
        row.technical_status = tech
        row.publishable = bool(verdict["publishable"])
        row.outcome = {"PASS": "accepted", "FAIL": "rejected"}.get(tech, "unverified")
        row.failure_categories = list(verdict.get("failure_categories") or [])
        flag_modified(row, "checks")
        flag_modified(row, "failure_categories")
    return {"reverified": True, "candidate_id": candidate_id, "previous": prev["technical_status"],
            "technical_status": tech}


def _run_candidates_failed(db, key: str, listing: str) -> list[str]:
    """Roles whose best candidate in this run is a technical FAIL."""
    from sqlalchemy import select

    from .image_records import ImageCandidate

    with db.session() as s:
        roles = sorted({r for (r,) in s.execute(select(ImageCandidate.role).where(
            ImageCandidate.run_key == key))})
    return [r for r in roles if (_best(db, listing=listing, role=r, run=key) or {}).get(
        "technical_status") == "FAIL"]


# ---- ENG-IMAGE-METHOD-REDRIVE: one restart per new generation-method version -----------------

def _stable_pdf_page_refs_version() -> str:
    """The page-reference renderer's version without the environment's pdfium build, which
    is not a method change."""
    from ..creative import pdf_page_refs

    return str(pdf_page_refs.RENDER_VERSION).split(";", 1)[0]


def generation_method(gen=None) -> dict:
    """The generation method by stable identifiers: the FLUX prompt builder, the pattern
    reference renderer (references 4-7 and the certified-PDF pages) and the owner's two-step
    method identifier this pipeline implements (`OWNER_METHOD`). Only code changes move the
    version. With `gen`, what that generator declares is recorded beside it
    (`generator_owner_method`) as provenance; it is not part of the version."""
    from ..creative import flux_prompt, pattern_refs

    parts = {"prompt_builder": str(flux_prompt.BUILDER_VERSION),
             "pattern_refs": str(pattern_refs.VERSION),
             "pdf_page_refs": _stable_pdf_page_refs_version(),
             "owner_method": OWNER_METHOD,
             # ENG-MANUAL-METHOD: the owner's October 28 hand method, generalised. A new part,
             # so every run FAILed under the earlier method is method-redrive eligible once.
             "image_method": MANUAL_METHOD_VERSION}
    out = {**parts, "version": "|".join(parts[k] for k in (
        "prompt_builder", "pattern_refs", "pdf_page_refs", "owner_method", "image_method"))}
    if gen is not None:
        out["generator_owner_method"] = bool(getattr(gen, "accepts_owner_method", False))
    return out


def current_method_version() -> str:
    return generation_method()["version"]


def candidate_method_version(checks) -> str:
    """The method version a stored candidate was made under; PRE_METHOD when unstamped."""
    rec = (checks or {}).get(METHOD_KEY) if isinstance(checks, dict) else None
    v = rec.get("version") if isinstance(rec, dict) else None
    return str(v) if v else PRE_METHOD


def _redriven_method(db, key: str) -> str | None:
    """The method version this run was last re-driven for, or None (never re-driven)."""
    from .image_records import ImageProductionRun
    from sqlalchemy import select

    with db.session() as s:
        stages = s.scalar(select(ImageProductionRun.stages).where(
            ImageProductionRun.run_key == key))
    v = (((stages or {}).get(RESTART_KEY) or {}).get("method_redrive") or {}).get("version")
    return str(v) if v else None


def _run_fail_versions(db, key: str, roles: list[str]) -> list[str]:
    """The method versions of every FAILed candidate of `roles` in this run."""
    from sqlalchemy import select

    from .image_records import ImageCandidate

    with db.session() as s:
        rows = s.execute(select(ImageCandidate.checks).where(
            ImageCandidate.run_key == key, ImageCandidate.role.in_(roles),
            ImageCandidate.technical_status == "FAIL")).all()
    return [candidate_method_version(c) for (c,) in rows]


def _redrive_call_cost_cad() -> float:
    """The most one FLUX 3 product-frame call may cost, CAD (the generator's own figure)."""
    from ..creative import image_stages
    from ..gateway import images

    try:
        usd = images.BFL3_TIER_USD[images.bfl3_tier(image_stages.PRODUCT_SIZE)]
    except Exception:  # noqa: BLE001 - unknown tier: assume the dearest, never the cheapest
        usd = max(images.BFL3_TIER_USD.values())
    return round(usd * images.USD_TO_CAD, 6)


def method_headroom(db, key: str, run: dict) -> dict:
    """Whether the run's existing call and spend caps leave room for one product-frame
    attempt (two calls for a vessel: side view + top-down). Reads the same spend plan the
    generation guard enforces; nothing here resets or raises a cap."""
    plan = _spend_plan(key, db)
    calls = 2 if is_vessel_release(db, run["slug"], run["version"]) else 1
    cost = _redrive_call_cost_cad()
    calls_left = int(plan["call_count"]) - int(_run_counts(db, key)["counted_calls"])
    spend_left = round(float(plan["max_spend_cad"]) - float(run.get("spent_cad") or 0.0), 4)
    ok = calls_left >= calls and spend_left + 1e-9 >= calls * cost
    return {"ok": ok, "calls_needed": calls, "calls_left": calls_left,
            "call_cap": int(plan["call_count"]), "spend_left_cad": spend_left,
            "spend_cap_cad": float(plan["max_spend_cad"]),
            "needed_cad": round(calls * cost, 4)}


def method_redrive_check(db, key: str, run: dict, failed: list[str]) -> dict:
    """Whether a run blocked on a fidelity FAIL may be restarted once under the current
    generation method. Eligible only when it blocked at `fidelity_gate`, every FAILed
    candidate of the failed roles was made under another method version, and no restart of
    this run has yet been spent on the current version. `ok` additionally needs headroom
    under the existing call and spend caps; without it the code is `method_redrive:no_headroom`."""
    current = current_method_version()
    base = {"version": current}
    if run.get("stage") != "fidelity_gate" or not failed:
        return {**base, "eligible": False, "ok": False, "code": None}
    history = (((_stage_data(db, key).get(RESTART_KEY)) or {}).get("history")) or []
    if any(h.get("method_version") == current for h in history):
        return {**base, "eligible": False, "ok": False, "code": METHOD_REDRIVE_ALREADY,
                "why": f"{METHOD_REDRIVE_ALREADY}: already restarted once under {current}"}
    versions = _run_fail_versions(db, key, failed)
    if not versions or current in versions:
        return {**base, "eligible": False, "ok": False, "code": METHOD_REDRIVE_CURRENT,
                "why": f"{METHOD_REDRIVE_CURRENT}: FAIL on {failed} under {current}"}
    room = method_headroom(db, key, run)
    out = {**base, "eligible": True, "ok": room["ok"], "headroom": room,
           "failed_versions": sorted(set(versions))}
    if not room["ok"]:
        out.update(code=METHOD_REDRIVE_NO_HEADROOM, why=(
            f"{METHOD_REDRIVE_NO_HEADROOM}: {room['calls_left']} of {room['call_cap']} calls "
            f"and CA${room['spend_left_cad']:.2f} of CA${room['spend_cap_cad']:.2f} left; one "
            f"attempt needs {room['calls_needed']} call(s) and CA${room['needed_cad']:.2f}"))
    else:
        out["code"] = None
    return out


def _record_method_readback(db, key: str, chk: dict, status: str, *,
                            day: str | None = None) -> None:
    """Write the run's method-redrive readback (`stages._method_redrive`). The run's status,
    blocked reason, calls and spend are untouched."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageProductionRun

    assert status in METHOD_REDRIVE_EVIDENCE, status
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None:
            return
        st = dict(r.stages or {})
        st[METHOD_REDRIVE_KEY] = {"status": status, "code": chk.get("code"),
                                  "version": chk.get("version"),
                                  "why": str(chk.get("why") or "")[:500],
                                  "headroom": chk.get("headroom") or {},
                                  **({"day": day} if day else {}),
                                  "at": _now().isoformat()}
        r.stages = st
        flag_modified(r, "stages")


def restartable(db, key: str, *, rejudge: bool = False, reverify_only: bool = False) -> dict:
    """Whether a blocked run may be restarted, and from which stage.

    Allowed: a run blocked by a missing capability (gate closed, no generator, a check the
    verifier or the vision judge could not read), including an owner-card block whose only
    reason is UNKNOWN. Refused: experiments; budget stops; a run whose best candidate for some
    role FAILed (its attempts are spent; a new release or a repair decides that); more than
    `MAX_RESTARTS`. A restart never resets attempts, generation calls or spend."""
    run = get_run(db, key)
    if run is None:
        return {"restartable": False, "why": "no such run"}
    from . import experiment as XP

    if (run.get("card") or {}).get("experiment") or XP.is_experiment(db, run["slug"],
                                                                       run["version"]):
        return {"restartable": False, "why": f"{XP.LABEL}: an experiment run is one-shot"}
    if "#" in key:
        return {"restartable": False, "why": "a controlled experiment run is one-shot; "
                                             "submit a new run from the Command Center"}
    if run["state"] != "blocked":
        return {"restartable": False, "why": f"run is {run['status']}, not blocked"}
    counts = _run_counts(db, key)
    spent = counts["restarts_spent"]
    if spent >= MAX_RESTARTS:
        # D-RESTART-PER-METHOD: the cap binds per generation-method version.
        return {"restartable": False, "code": RESTART_CAP_CODE,
                "why": f"already restarted {spent} times under generation method "
                       f"{current_method_version()} (cap {MAX_RESTARTS}; "
                       f"{counts['restarts_total']} in all)"}
    reason = str(run.get("blocked_reason") or "")
    daily = reason.startswith("budget stop") and daily_ceiling_reset(run)
    # D-OWNER-PHOTO-BUDGET: a stop on the per-gallery PLAN (its call count or money cap) is
    # final only while that plan is still exhausted. Once the plan has been raised and leaves
    # room for one more attempt, the run resumes where it stopped, like a daily-ceiling stop;
    # every cap still binds when it does.
    planned = plan_budget_block(reason) and plan_headroom(db, key, run)["ok"]
    daily = daily or planned
    if reason.startswith("budget stop") and not daily:
        return {"restartable": False, "why": "a budget stop is final for this run: " + reason}
    # REDRIVE-REFUSAL: a daily-ceiling stop interrupted generation (often mid-repair, with an
    # earlier FAILed candidate the repair was answering): it was stopped by the window, not
    # by spent attempts. It resumes where it stopped; the per-role attempt cap, the call cap
    # and the spend plan still bind when it does.
    # IMAGE-STALE-REFS: a stale-reference refusal is not a verdict on any candidate: nothing
    # was sent. It resumes where it stopped (the stage re-prepares the references); the stage's
    # own per-role attempt cap, the call cap and the spend plan still bind.
    stale = stale_references_block(reason)
    failed = [] if (daily or stale) else _run_candidates_failed(db, key, run["listing"])
    if failed and rejudge and failed == [ANCHOR_ROLE] and run["stage"] == "fidelity_gate" \
            and rejudge_candidate_ids(db, key):
        # IMAGE-FIDELITY-2: the anchor's FAILs were judged by a verifier that has since been
        # corrected (`fidelity.FIDELITY_JUDGE_VERSION`). Its stored frames are judged again;
        # nothing is generated, no attempt is added. A FAIL then stays a FAIL.
        return {"restartable": True, "resume_at": "fidelity_gate", "reverify": True,
                "rejudge": True, "blocked_at": run["stage"], "blocked_reason": reason,
                "epoch": run.get("restarts", 0) + 1}
    if failed and reverify_only and run["stage"] == "verification" \
            and structural_verification_block(reason):
        # VERIFY-REFS (19i31): the run stopped on a structural reading the current Product
        # Truth policy no longer gives any of its stored frames. The stored frames are
        # verified again; nothing is generated, no attempt is added.
        with db.session() as s_:
            had, still = _structural_roles_in(s_, key)
        if had and not still:
            return {"restartable": True, "resume_at": "verification", "reverify": True,
                    "reverify_only": True, "blocked_at": run["stage"],
                    "blocked_reason": reason, "epoch": run.get("restarts", 0) + 1}
        return {"restartable": False, "code": "structural_reference",
                "why": f"structural: {still or had} still FAIL on their references under "
                       f"today's policy; re-verifying the stored frames cannot change it"}
    if failed:
        chk = method_redrive_check(db, key, run, failed)
        if chk["eligible"] and not chk["ok"]:
            return {"restartable": False, "code": chk["code"], "why": chk["why"],
                    "method_redrive": chk}
        if not chk["ok"]:
            return {"restartable": False, "why": f"FAIL on {failed}: attempts were spent on a "
                                                 f"failure, not a missing capability",
                    **({"code": chk["code"]} if chk.get("code") else {})}
        # ENG-IMAGE-METHOD-REDRIVE: the failures were made under an older method. Regenerate
        # the product frame under the current one; attempts then count that method only.
        return {"restartable": True, "resume_at": "product_generation", "reverify": False,
                "blocked_at": run["stage"], "blocked_reason": reason,
                "epoch": run.get("restarts", 0) + 1, "method_redrive": chk}
    names = [st for st, _ in STAGES]
    blocked_at = run["stage"] if run["stage"] in names else names[0]
    has_anchor = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key) is not None
    if stale:
        resume, reverify_ = blocked_at, False
    elif names.index(blocked_at) >= names.index("verification"):
        resume, reverify_ = "verification", True
    elif blocked_at in ("product_generation", "fidelity_gate") and has_anchor:
        resume, reverify_ = "fidelity_gate", True
    elif blocked_at == "identity_anchor" and _best(
            db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key) is not None:
        resume, reverify_ = "identity_anchor", True
    else:
        resume, reverify_ = blocked_at, False
    return {"restartable": True, "resume_at": resume, "reverify": reverify_,
            "blocked_at": blocked_at, "blocked_reason": reason,
            "epoch": run.get("restarts", 0) + 1}


def restart(db, key: str, *, follow, by: str, reason: str = "",
            record: dict | None = None, rejudge: bool = False,
            reverify_only: bool = False) -> dict:
    """Restart a blocked run under a new epoch (W-VISNEXT; OWNERIMG E4).

    The next job carries `epoch` and its idempotency key ends `:e<epoch>`, so it never collides
    with the first pass; jobs from an older epoch are skipped. Attempts, generation calls and
    spend carry over (the per-role cap and the gallery spend plan still bind), and stored
    candidates are re-verified rather than regenerated where they exist. `follow` must enqueue
    the job using the supplied SQLAlchemy `session` and propagate failures so the restart
    state and job commit or roll back together."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    from .image_records import ImageProductionRun

    if not str(by or "").strip():
        raise ValueError("a restart names who asked for it")
    can = restartable(db, key, rejudge=rejudge, reverify_only=reverify_only)
    if not can["restartable"]:
        return {"restarted": False, **can}
    if reverify_only and not can.get("reverify_only"):
        # a re-verification request never becomes a regeneration (a method redrive)
        return {"restarted": False, "reverify_only": False,
                "why": "not a structural verification block this policy reads differently"}
    if rejudge and not can.get("rejudge"):
        # a rejudge request never becomes another kind of restart (a method redrive)
        return {"restarted": False, "rejudge": False,
                "why": "no FAILed anchor frame is this verifier version's to re-read"}
    run = get_run(db, key)
    epoch = can["epoch"]
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        # The preflight performs multiple reads. Refuse a concurrently changed run;
        # do not spend a new epoch on a stale preflight decision.
        current_epoch = int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0) if r else -1
        if (r is None or r.status != "blocked" or current_epoch != epoch - 1
                or r.stage != run["stage"] or r.stage != can["blocked_at"]
                or (r.blocked_reason or "") != (run["blocked_reason"] or "")
                or (r.blocked_reason or "") != can["blocked_reason"]):
            return {"restarted": False, "why": "run changed during restart; retry preflight"}
        st = dict(r.stages or {})
        rec = dict(st.get(RESTART_KEY) or {})
        rec["epoch"] = epoch
        rec["history"] = list(rec.get("history") or []) + [{
            "epoch": epoch, "at": _now().isoformat(), "by": str(by)[:120],
            "reason": str(reason)[:500], "blocked_at": can["blocked_at"],
            "blocked_reason": can["blocked_reason"][:1000], "resume_at": can["resume_at"],
            "reverify": can["reverify"], "generation_calls": r.generation_calls,
            "spent_cad": round(r.spent_cad or 0.0, 4),
            # D-RESTART-PER-METHOD: the method version this restart is spent under
            HISTORY_METHOD_KEY: current_method_version(),
            **({"method_version": can["method_redrive"]["version"]}
               if can.get("method_redrive") else {}), **dict(record or {})}]
        if can.get("method_redrive"):
            rec["method_redrive"] = {"version": can["method_redrive"]["version"],
                                     "epoch": epoch, "at": _now().isoformat(),
                                     "failed_versions": can["method_redrive"].get(
                                         "failed_versions") or []}
        st[RESTART_KEY] = rec
        r.stages = st
        flag_modified(r, "stages")
        r.status, r.blocked_reason, r.attempts_exhausted = (STAGE_STATE[can["resume_at"]], "",
                                                            False)
        r.stage = can["resume_at"]
        r.updated_at = _now()
        inputs = {"slug": run["slug"], "version": run["version"], "release": run["release"],
                  "stage": can["resume_at"], "round": 0, "epoch": epoch}
        route = route_of_key(key)
        if route:
            inputs["route"] = route
        if can["reverify"]:
            inputs["reverify"] = True
        if can.get("rejudge"):
            inputs["rejudge"] = True
        job = follow(inputs, stage_key(run["slug"], run["version"], run["release"],
                                       can["resume_at"], 0, epoch, route=route), session=s)
        if job is None:
            raise RuntimeError("restart job was not durably enqueued")
    return {"restarted": True, "epoch": epoch, "resume_at": can["resume_at"],
            "reverify": can["reverify"], "enqueued": job is not None, "run_key": key,
            **({"method_version": can["method_redrive"]["version"]}
               if can.get("method_redrive") else {})}


# ---- V2 / P2-a: a capability-only block is re-driven once when its gate opens -------------

# A blocked reason that names a closed gate, and the gate whose opening clears it. Only these
# are re-driven automatically: every other block (a FAIL, a budget stop, an owner card) waits
# for the person or the repair that decides it.
CAPABILITY_GATES = (("image_generation gate closed", "image_generation"),)
REDRIVE_BY = "capability_redrive"

# ENG-FLUX-PROVIDER (2026-11-23): a run blocked on a TRANSIENT provider answer (BFL 503, an
# unreachable host, a timeout) used to stay blocked for good -- nothing re-drove it, so one busy
# spell at BFL parked the gallery (production: 4 runs at product_generation:provider, no FLUX
# call for hours). Such a run is restarted by the hourly sweep, at most once per UTC hour and
# not before PROVIDER_REDRIVE_AFTER has passed since it blocked. Every cap still binds:
# MAX_RESTARTS, the per-role attempt cap, the call cap, the per-gallery and daily ceilings.
PROVIDER_REDRIVE_BY = "provider_transient_redrive"
PROVIDER_REDRIVE_AFTER = timedelta(minutes=15)
_PROVIDER_CONTEXT = ("provider error", "could not be rendered", "generator refused")
_PROVIDER_TRANSIENT = re.compile(
    r"TransientError|\b(?:500|502|503|504)\b|unreachable|timed out|did not finish within",
    re.IGNORECASE)


def provider_transient_block(reason) -> bool:
    """A block whose recorded cause is a transient provider answer (never a budget stop)."""
    text = str(reason or "")
    if text.startswith("budget stop"):
        return False
    low = text.lower()
    return any(c in low for c in _PROVIDER_CONTEXT) and bool(_PROVIDER_TRANSIENT.search(text))


# IMAGE-STALE-REFS (19i24): a run blocked because the generator refused references another
# renderer made (production 19i23: four basket galleries at product_generation). The stage now
# re-prepares stale references itself; a run already blocked on it is restarted by the hourly
# sweep once per reference-renderer version (`references_version`). The refused call sent
# nothing, so its stranded hold is released first and it counts toward no cap. Every other
# cap still binds: MAX_RESTARTS, the per-role attempt cap, the call cap, the spend plan.
STALE_REFS_REDRIVE_BY = "stale_references_redrive"
STALE_REFS_KEY = "_stale_refs_redrive"   # stages: {"references_version", "why", "at"} if refused


def stale_references_block(reason) -> bool:
    """A block whose recorded cause is the generator refusing stale references."""
    text = str(reason or "")
    return not text.startswith("budget stop") and bool(_STALE_REFUSAL.search(text))


def _stale_redriven(stages: dict, version: str) -> bool:
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    if any(isinstance(h, dict) and h.get("by") == STALE_REFS_REDRIVE_BY
           and h.get("references_version") == version for h in history):
        return True
    return (stages.get(STALE_REFS_KEY) or {}).get("references_version") == version


def _release_stale_refusal_hold(db, key: str) -> bool:
    """Release the paid hold a stale-reference refusal left behind (before the refusal
    released its own hold). Only when the hold is unsettled (no receipt), the run is blocked
    on that refusal, and the run's latest candidate is that refusal's provider-error row (no
    bytes) at the hold's stage, made after the hold. Anything else is left for review."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageCandidate, ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(
            ImageProductionRun.run_key == key).with_for_update())
        if r is None or r.status != "blocked" or not stale_references_block(r.blocked_reason):
            return False
        st = dict(r.stages or {})
        pending = st.get("_pending_paid_call")
        if not isinstance(pending, dict) or pending.get("state") is not None:
            return False
        last = s.scalar(select(ImageCandidate).where(ImageCandidate.run_key == key)
                        .order_by(ImageCandidate.id.desc()).limit(1))
        why = str(((last.checks or {}).get("provider") or {}).get("why") or "") if last else ""
        at, made = _utc(pending.get("at")), _utc(last.created_at) if last else None
        if (last is None or last.outcome != "provider_error" or last.sha256
                or last.stage != pending.get("stage") or not _STALE_REFUSAL.search(why)
                or at is None or made is None or made < at):
            return False
        del st["_pending_paid_call"]
        r.stages = st
        flag_modified(r, "stages")
        return True


def _record_stale_refusal(db, key: str, version: str, why: str) -> None:
    """Record that the stale-reference redrive of `key` was refused under `version`."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None or r.status != "blocked":
            return
        st = dict(r.stages or {})
        st[STALE_REFS_KEY] = {"references_version": version, "why": why[:500],
                              "at": _now().isoformat()}
        r.stages = st
        flag_modified(r, "stages")


def _sweep_stale_references(db, key: str, stages: dict, *, follow, restarted: list,
                            refused: list) -> None:
    version = references_version()
    if _stale_redriven(stages, version):
        refused.append({"run_key": key, "why": f"already re-driven for stale references "
                                               f"under {version}"})
        return
    _release_stale_refusal_hold(db, key)
    try:
        out = restart(db, key, follow=follow, by=STALE_REFS_REDRIVE_BY,
                      reason=f"references re-prepared under {version}",
                      record={"references_version": version})
    except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    if not out.get("restarted") and out.get("restartable") is False:
        _record_stale_refusal(db, key, version, str(out.get("why") or ""))
    (restarted if out.get("restarted") else refused).append(
        {"run_key": key, **{k: out[k] for k in ("epoch", "resume_at", "why") if k in out}})


def _provider_redrive_due(stages: dict, updated_at, now: datetime) -> str | None:
    """The UTC hour key a provider-transient redrive may use now, else None."""
    at = _utc(updated_at)
    if at is not None and now - at < PROVIDER_REDRIVE_AFTER:
        return None
    hour = now.strftime("%Y-%m-%dT%HZ")
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    if any(h.get("by") == PROVIDER_REDRIVE_BY and hour in str(h.get("reason", ""))
           for h in history):
        return None
    return hour


# IMAGE-FIDELITY-ROUTE (19i25): a run blocked at `fidelity_gate` because its product frame's
# fidelity verdict read UNKNOWN ("product fidelity cannot be verified") had no retry path at
# all: it is not a FAIL (no method redrive), not a capability gate, not a provider answer.
# Production 19i24: hexagon-coaster-set@1.2.1, two runs, parked since 19i18 because the
# verifier's vision judge asked only the Anthropic-gated `image_vision` route while the owner
# had activated openai-vision. Such a run is restarted by the hourly sweep ONCE per fidelity
# judge version (`fidelity.FIDELITY_JUDGE_VERSION`), only when a vision route is usable now,
# and it resumes at `fidelity_gate` with `reverify`: the stored frame's bytes are judged again;
# nothing is generated and no attempt is added. A FAIL then takes the existing bounded repair
# loop (per-role attempt cap); an UNKNOWN blocks again and is not re-driven again under the
# same version. Every cap binds: MAX_RESTARTS, the attempt cap, the call cap, the spend plan.
# IMAGE-FIDELITY-3 (19i27): "version" is the pair (judge version, deterministic check version,
# `fidelity.FIDELITY_CHECK_VERSION`): a corrected deterministic check re-drives an UNKNOWN-
# parked run once too (the coaster palette read the table through the fabric as yarn).
FIDELITY_UNKNOWN_PREFIX = "product fidelity cannot be verified"
FIDELITY_REDRIVE_BY = "fidelity_unknown_redrive"
FIDELITY_REDRIVE_KEY = "_fidelity_unknown_redrive"  # stages: {"judge_version", "check_version",
#                                                     "day", "why", "at"}


def fidelity_unknown_block(reason) -> bool:
    """A block whose recorded cause is an UNKNOWN product-frame fidelity verdict."""
    return str(reason or "").startswith(FIDELITY_UNKNOWN_PREFIX)


def fidelity_judge_version() -> str:
    from .fidelity import FIDELITY_JUDGE_VERSION

    return FIDELITY_JUDGE_VERSION


def fidelity_check_version() -> str:
    """IMAGE-FIDELITY-3: the deterministic checks' version (`fidelity.FIDELITY_CHECK_VERSION`).
    An UNKNOWN-parked run is re-driven once per (judge version, check version)."""
    from .fidelity import FIDELITY_CHECK_VERSION

    return FIDELITY_CHECK_VERSION


# REDRIVE-ELIGIBILITY (19i28): a restart history entry written before IMAGE-FIDELITY-3 names no
# check version; its frames were judged by the first deterministic checks.
LEGACY_CHECK_VERSION = "fidelity-checks/1"
# The fidelity re-judgements: each re-reads stored frames under (judge version, check version)
# and generates nothing.
_REJUDGEMENT_BY = (FIDELITY_REDRIVE_BY, "fidelity_rejudge_redrive")


def _entry_check_version(h: dict) -> str:
    return str(h.get("check_version") or LEGACY_CHECK_VERSION)


def _fidelity_redriven(stages: dict, version: str) -> bool:
    """Already re-judged under (`version`, the current check version) by either fidelity
    redrive. REDRIVE-ELIGIBILITY (19i28): production 19i26 re-drove both hexagon-coaster runs
    a second time under fidelity-judge/2 an hour after the rejudge redrive had re-read the same
    frames under fidelity-judge/2 (this test looked at `fidelity_unknown_redrive` entries only).
    That restart could not read anything differently, and it was the third: both runs reached
    MAX_RESTARTS, so the IMAGE-FIDELITY-3 re-judgement (fidelity-checks/2) was refused."""
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    checks = fidelity_check_version()
    return any(isinstance(h, dict) and h.get("by") in _REJUDGEMENT_BY
               and h.get("judge_version") == version and _entry_check_version(h) == checks
               for h in history)


def _frame_judged_now(checks, version: str, check_version: str) -> bool:
    """A stored anchor verdict already made under (`version`, `check_version`)."""
    fid = ((checks or {}).get("product_truth") or {}).get("fidelity") \
        if isinstance(checks, dict) and isinstance(checks.get("product_truth"), dict) else None
    return (isinstance(fid, dict) and fid.get("judge_version") == version
            and str(fid.get("check_version") or LEGACY_CHECK_VERSION) == check_version)


def _anchor_frames_judged_now(session, key: str, version: str) -> bool:
    """Every stored anchor frame of run `key` was already judged under (`version`, the current
    check version): a re-judgement would read nothing differently. False with no frame."""
    from sqlalchemy import select

    from .image_records import ImageCandidate

    checks = fidelity_check_version()
    rows = [c for (c,) in session.execute(select(ImageCandidate.checks).where(
        ImageCandidate.run_key == key, ImageCandidate.role == ANCHOR_ROLE,
        ImageCandidate.sha256 != ""))]
    return bool(rows) and all(_frame_judged_now(c, version, checks) for c in rows)


# ---- REDRIVE-ELIGIBILITY: the vision judge's own daily ceiling ----------------------------
# A re-judgement generates nothing, so no generation ceiling (the FLUX daily ceiling, the call
# cap, the gallery spend plan) holds it back. It does ask the vision judge, and that route has
# its own owner ceilings (openai-vision: CA$2.00 a day). When today's headroom on the route the
# verifier would ask cannot cover the questions, re-judging now would read UNKNOWN and spend the
# run's once-per-version re-judgement and a restart on nothing: the sweep waits for the UTC day.
VISION_CALLS_PER_FRAME = 2      # the craft reading, plus a vessel's second view (conservative)


def _vision_route_read(db) -> tuple[str | None, str]:
    """(vendor, model) the fidelity verifier's vision route would use, read-only.

    The same rule as `visual.vision_route.choose` (keep the two in step): the Anthropic route
    when `image_vision` is usable, else OpenAI vision when `openai-vision:vision` is usable,
    else none. Duplicated on purpose (19i30): `choose` constructs the paid provider
    (`provider_for`), and this pre-check runs inside the free `chain.successors` sweep, which
    only restarts runs; the vision call itself is made later by the image-production job,
    which is classified as spending. This reads evidence and model names, nothing more."""
    from ..gateway import paid_provider_gate as G
    from ..gateway import routing
    from ..gateway.providers import last_vision_probe  # F-091: the boundary, a probe reading
    from . import vision_route

    try:
        # `anthropic.vision_usable`'s condition, inlined: the static spend graph resolves its
        # local name `state` to `anthropic.state` (a provider constructor), a false edge.
        probe_row = last_vision_probe(db)
        if G.probe_activation_open(db, probe_row, G.ANTHROPIC_VISION, G.VISION):
            return vision_route.ANTHROPIC, str(routing.route(vision_route.TASK)[1].model)
    except Exception:  # noqa: BLE001 - unreadable evidence is a closed Anthropic route
        pass
    try:
        from ..creative import concept_judge

        if concept_judge.openai_vision_usable(db):
            return vision_route.OPENAI, str(routing.openai_model_for(vision_route.TASK))
    except Exception:  # noqa: BLE001 - an unpriced or unroutable model judges nothing
        pass
    return None, ""


def _vision_route_usable_read(db) -> bool:
    """`fidelity.vision_route_usable`, read-only (`_vision_route_read`; same rule)."""
    return _vision_route_read(db)[0] is not None


def _vision_headroom(db, frames: int) -> tuple[bool, str]:
    """(ok, why): whether today's ceiling on the vision route the fidelity verifier would ask
    covers `frames` re-judged frames. Unreadable is not ok (fail closed: wait). Read-only:
    `_vision_route_read` and `paid_provider_gate`'s activation and headroom reads."""
    try:
        from ..gateway import paid_provider_gate as G
        from . import vision_route

        vendor, model = _vision_route_read(db)
        if vendor is None:
            return False, "no vision route is usable for the fidelity verifier"
        gate = G.OPENAI_VISION if vendor == vision_route.OPENAI else G.ANTHROPIC_VISION
        st = G.activation_state(db, gate, G.VISION)
        if not st["active"]:
            # the Anthropic route is opened by its own gate (vision_usable); nothing to read
            return (vendor != vision_route.OPENAI,
                    f"{gate} is not active ({st.get('reason')})")
        left = G.daily_headroom_cad(db, gate, G.VISION)
        need = round(max(1, int(frames)) * VISION_CALLS_PER_FRAME
                     * _vision_call_estimate_cad(vendor, model), 6)
    except Exception as exc:  # noqa: BLE001 - unreadable headroom never spends
        return False, f"vision headroom unreadable ({type(exc).__name__})"
    if left is None or left + 1e-9 < need:
        return False, (f"{gate} daily ceiling: CA${(left or 0.0):.4f} left today, a "
                       f"re-judgement needs up to CA${need:.4f}; waits for the next UTC day")
    return True, ""


def _vision_call_estimate_cad(vendor: str, model: str) -> float:
    """One fidelity vision question's reservation on `model` (its vendor's own estimate rule)."""
    from ..gateway import providers as gw
    from . import vision_route
    from .fidelity import CRAFT_SYSTEM, craft_prompt

    model = str(model or "")
    tokens = gw.input_tokens(model, system=CRAFT_SYSTEM, user=craft_prompt(), images=1)
    if vendor == vision_route.OPENAI:
        from ..gateway import openai_chat

        return float(openai_chat.estimate_cad(model, input_tokens=tokens, output_tokens=300))
    return float(gw.estimate_cad(model, input_tokens=tokens, output_tokens=300))  # F-091


# 19i29 (production 16:37Z): hexagon-coaster-set@1.2.1's UNKNOWN reverify read `refusal_held`
# at 2 of 3 restarts. The hold was recorded by 19i27's 12:00Z sweep, whose restart was refused
# "already restarted 3 times (cap 3)" under (fidelity-judge/2, fidelity-checks/2), as a hold
# for good. 19i28's duplicate credit then counted that history as 2, and per-method counting
# (D-RESTART-PER-METHOD) counts it as 0 under the current method, but the hold outlived the
# count it was made from. A refusal recorded because MAX_RESTARTS bound now holds only while
# the cap still binds; every other hold is unchanged. The OpenAI vision headroom was not the
# cause: CA$0.7635 of CA$2.00 spent (unchanged since 12:59Z), one re-judgement needs CA$0.022.
#
# A recorded refusal's cause, in a fixed vocabulary (`hold` in the readback).
HOLD_CODES = (RESTART_CAP_CODE, "role_failed", "judged_now", "no_vision_route",
              "vision_headroom", "restart_refused", "generation_headroom", "other")


def hold_code(rec) -> str | None:
    """The fixed-vocabulary cause of a recorded refusal (records before 19i29 carry no code:
    read from their own words)."""
    if not isinstance(rec, dict) or not rec:
        return None
    code = rec.get("code")
    if code in HOLD_CODES:
        return code
    why = str(rec.get("why") or "")
    for prefix, c in (("already restarted ", RESTART_CAP_CODE), ("a role FAILed", "role_failed"),
                      ("every stored anchor frame is already judged", "judged_now"),
                      ("no vision route is usable", "no_vision_route"),
                      ("vision headroom unreadable", "vision_headroom")):
        if why.startswith(prefix):
            return c
    if " daily ceiling: " in why and "re-judgement needs" in why:
        return "vision_headroom"
    return "other"


def _cap_hold_lifted(rec, spent: int | None) -> bool:
    """A refusal recorded because MAX_RESTARTS bound, while the cap no longer binds (the
    count under the current generation-method version is below it)."""
    return (spent is not None and spent < MAX_RESTARTS
            and hold_code(rec) == RESTART_CAP_CODE)


def _fidelity_refusal_holds(stages: dict, version: str, day: str, *,
                            spent: int | None) -> bool:
    """The sweep judged this run under `version` and was refused: for good when the restart
    itself was refused, for the UTC day when no vision route (or no vision headroom) was
    usable. A refusal by MAX_RESTARTS holds only while the cap binds (`spent`: restarts
    under the current generation-method version)."""
    rec = stages.get(FIDELITY_REDRIVE_KEY) or {}
    if not isinstance(rec, dict) or rec.get("judge_version") != version \
            or rec.get("check_version") != fidelity_check_version():
        return False
    if _cap_hold_lifted(rec, spent):
        return False
    return rec.get("day") in (None, day)


def _record_fidelity_refusal(db, key: str, version: str, why: str, *,
                             day: str | None, code: str = "other") -> None:
    """Record that the fidelity redrive of `key` was refused under `version` (`day` set: only
    for that UTC day, because no vision route was usable)."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None or r.status != "blocked":
            return
        st = dict(r.stages or {})
        st[FIDELITY_REDRIVE_KEY] = {"judge_version": version,
                                    "check_version": fidelity_check_version(), "day": day,
                                    "code": code if code in HOLD_CODES else "other",
                                    "why": why[:500], "at": _now().isoformat()}
        r.stages = st
        flag_modified(r, "stages")


def _fidelity_redrive_candidate(db, key: str, reason: str) -> bool:
    """A run the fidelity redrive owns: blocked at `fidelity_gate` on an UNKNOWN product-frame
    verdict, not an experiment."""
    if "#" in key or not fidelity_unknown_block(reason):
        return False
    return (get_run(db, key) or {}).get("stage") == "fidelity_gate"


def _sweep_fidelity_unknown(db, key: str, stages: dict, *, follow, restarted: list,
                            waiting: list, refused: list) -> bool:
    """The fidelity redrive's sweep step. False when the run is not this redrive's to judge
    (a FAILed role: the method redrive then looks at it); True otherwise."""

    version = fidelity_judge_version()
    day = str(_now().date())
    run = get_run(db, key) or {}
    if _run_candidates_failed(db, key, run.get("listing", "")):
        # A FAILed role is decided by the repair loop and the method redrive, never by a
        # re-judgement; recorded so `redrive_due` stops reporting it under this version.
        why = "a role FAILed: the repair loop and the method redrive own this run"
        _record_fidelity_refusal(db, key, version, why, day=None, code="role_failed")
        return False
    if _fidelity_redriven(stages, version):
        refused.append({"run_key": key, "why": f"already re-driven for an UNKNOWN fidelity "
                                               f"verdict under {version} "
                                               f"({fidelity_check_version()})"})
        return True
    if _fidelity_refusal_holds(stages, version, day,
                               spent=_run_counts(db, key)["restarts_spent"]):
        prior = str((stages.get(FIDELITY_REDRIVE_KEY) or {}).get("why") or "")
        refused.append({"run_key": key, "why": f"already judged under {version}: "
                                               f"{prior}"[:500]})
        return True
    with db.session() as s:
        judged_now = _anchor_frames_judged_now(s, key, version)
    if judged_now:
        # REDRIVE-ELIGIBILITY: every stored frame already carries a verdict under these
        # versions (e.g. the rejudge redrive just re-read them): a restart would only spend
        # one of the run's MAX_RESTARTS on the same reading.
        why = (f"every stored anchor frame is already judged under {version} "
               f"({fidelity_check_version()}); a re-judgement would read nothing differently")
        _record_fidelity_refusal(db, key, version, why, day=None, code="judged_now")
        refused.append({"run_key": key, "why": why})
        return True
    if not _vision_route_usable_read(db):
        why = "no vision route is usable for the fidelity verifier; re-judging would read UNKNOWN"
        _record_fidelity_refusal(db, key, version, why, day=day, code="no_vision_route")
        waiting.append({"run_key": key, "why": why})
        return True
    ok, why = _vision_headroom(db, 1)
    if not ok:
        _record_fidelity_refusal(db, key, version, why, day=day, code="vision_headroom")
        waiting.append({"run_key": key, "why": why})
        return True
    try:
        out = restart(db, key, follow=follow, by=FIDELITY_REDRIVE_BY,
                      reason=f"product frame re-judged under {version} "
                             f"({fidelity_check_version()})",
                      record={"judge_version": version,
                              "check_version": fidelity_check_version()})
    except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    if not out.get("restarted") and out.get("restartable") is False:
        _record_fidelity_refusal(db, key, version, str(out.get("why") or ""), day=None,
                                 code=out.get("code") if out.get("code") == RESTART_CAP_CODE
                                 else "restart_refused")
    (restarted if out.get("restarted") else refused).append(
        {"run_key": key, **{k: out[k] for k in ("epoch", "resume_at", "reverify", "why")
                            if k in out}})
    return True


# IMAGE-FIDELITY-2 (19i26): five gallery runs ended `fidelity_gate:product_truth:exhausted`
# (production 19i25, evidence 07:24Z) on FAILs the verifier itself got wrong: the coaster's
# declared wine round read as an edging by the craft judge (INVENTED_EDGING x10), and the
# basket's side view read through its opening (the far wall's inner stripes counted as wall
# bands; band shares by round count on a dc/slip-stitch wall). Both readings are corrected
# under `fidelity.FIDELITY_JUDGE_VERSION`. Such a run is restarted by the hourly sweep ONCE
# per judge version, only while a vision route is usable, at `fidelity_gate` with `rejudge`:
# its stored anchor frames that FAILed on a check this version reads differently
# (`fidelity.REJUDGED_CHECKS`), judged under an older version, are judged again (at most
# MAX_REJUDGE_CANDIDATES). Nothing is generated and no attempt is added. A frame that still
# FAILs stays FAILed: the run blocks again, and the method redrive (a new generation method)
# then decides. Every cap binds: MAX_RESTARTS, the attempt cap, the call cap, the spend plan.
FIDELITY_REJUDGE_BY = "fidelity_rejudge_redrive"
FIDELITY_REJUDGE_KEY = "_fidelity_rejudge"   # stages: {"judge_version", "day", "why", "at"}
FIDELITY_FAIL_PREFIX = "product fidelity FAIL after"
MAX_REJUDGE_CANDIDATES = 6
assert FIDELITY_REJUDGE_BY in _REJUDGEMENT_BY


def fidelity_fail_block(reason) -> bool:
    """A block whose recorded cause is the anchor's fidelity FAIL with its attempts spent."""
    return str(reason or "").startswith(FIDELITY_FAIL_PREFIX)


def _rejudge_wanted(checks, version: str) -> bool:
    """A stored anchor verdict that the current verifier would read differently: FAILed on a
    `fidelity.REJUDGED_CHECKS` check, judged under another (or no recorded) judge version."""
    from .fidelity import REJUDGED_CHECKS

    fid = ((checks or {}).get("product_truth") or {}).get("fidelity") \
        if isinstance(checks, dict) else None
    if not isinstance(fid, dict) or fid.get("judge_version") == version:
        return False
    failed = [str(c) for c in fid.get("failed") or []]
    return any(c == k or (k.startswith(":") and c.endswith(k))
               for c in failed for k in REJUDGED_CHECKS)


def _rejudge_ids_in(session, key: str, version: str) -> list[int]:
    from sqlalchemy import select

    from .image_records import ImageCandidate

    rows = session.execute(select(ImageCandidate.id, ImageCandidate.checks,
                                  ImageCandidate.sha256).where(
        ImageCandidate.run_key == key, ImageCandidate.role == ANCHOR_ROLE,
        ImageCandidate.technical_status == "FAIL").order_by(ImageCandidate.id.desc())).all()
    return [cid for cid, checks, sha in rows if sha and _rejudge_wanted(checks, version)]


def rejudge_candidate_ids(db, key: str) -> list[int]:
    """This run's FAILed anchor frames the current fidelity judge version would re-read,
    newest first."""
    with db.session() as s:
        return _rejudge_ids_in(s, key, fidelity_judge_version())


def _rejudged(stages: dict, version: str, day: str, *, spent: int | None) -> bool:
    """Already re-judged under `version`, or judged and refused (for good, or for the UTC
    day when no vision route was usable). A refusal by MAX_RESTARTS holds only while the cap
    binds (`spent`: restarts under the current generation-method version)."""
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    if any(isinstance(h, dict) and h.get("by") == FIDELITY_REJUDGE_BY
           and h.get("judge_version") == version for h in history):
        return True
    rec = stages.get(FIDELITY_REJUDGE_KEY) or {}
    if _cap_hold_lifted(rec, spent):
        return False
    return (isinstance(rec, dict) and rec.get("judge_version") == version
            and rec.get("day") in (None, day))


def _record_rejudge_refusal(db, key: str, version: str, why: str, *, day: str | None,
                            code: str = "other") -> None:
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None or r.status != "blocked":
            return
        st = dict(r.stages or {})
        st[FIDELITY_REJUDGE_KEY] = {"judge_version": version, "day": day, "why": why[:500],
                                    "code": code if code in HOLD_CODES else "other",
                                    "at": _now().isoformat()}
        r.stages = st
        flag_modified(r, "stages")


def _rejudge_redrive_candidate(db, key: str, reason: str, stages: dict) -> bool:
    """A run the rejudge redrive owns now: blocked at `fidelity_gate` on a spent-attempts
    FAIL, not an experiment, not yet judged under this version, with a frame to re-read."""
    if "#" in key or not fidelity_fail_block(reason):
        return False
    if (get_run(db, key) or {}).get("stage") != "fidelity_gate":
        return False
    if _rejudged(stages, fidelity_judge_version(), str(_now().date()),
                 spent=_run_counts(db, key)["restarts_spent"]):
        return False
    return bool(rejudge_candidate_ids(db, key))


def _sweep_fidelity_rejudge(db, key: str, *, follow, restarted: list, waiting: list,
                            refused: list) -> None:

    version = fidelity_judge_version()
    if not _vision_route_usable_read(db):
        why = "no vision route is usable for the fidelity verifier; re-judging would read UNKNOWN"
        _record_rejudge_refusal(db, key, version, why, day=str(_now().date()),
                                code="no_vision_route")
        waiting.append({"run_key": key, "why": why})
        return
    n = len(rejudge_candidate_ids(db, key))
    ok, why = _vision_headroom(db, min(n, MAX_REJUDGE_CANDIDATES))
    if not ok:
        # REDRIVE-ELIGIBILITY: the vision route's own daily ceiling (never a generation
        # ceiling: a re-judgement generates nothing) cannot cover the re-reads today.
        _record_rejudge_refusal(db, key, version, why, day=str(_now().date()),
                                code="vision_headroom")
        waiting.append({"run_key": key, "why": why})
        return
    try:
        out = restart(db, key, follow=follow, by=FIDELITY_REJUDGE_BY, rejudge=True,
                      reason=f"anchor frames re-judged under {version} "
                             f"({min(n, MAX_REJUDGE_CANDIDATES)} frame(s))",
                      record={"judge_version": version,
                              "check_version": fidelity_check_version()})
    except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    if not out.get("restarted") and (out.get("restartable") is False
                                     or out.get("rejudge") is False):
        # Judged under this version: `redrive_due` stops asking; the method redrive decides.
        _record_rejudge_refusal(db, key, version, str(out.get("why") or ""), day=None,
                                code=out.get("code") if out.get("code") == RESTART_CAP_CODE
                                else "restart_refused")
    (restarted if out.get("restarted") else refused).append(
        {"run_key": key, "kind": "fidelity_rejudge",
         **{k: out[k] for k in ("epoch", "resume_at", "reverify", "why") if k in out}})


# VERIFY-REFS (19i31): production 19i30 (01:31Z) shows both hexagon-coaster-set@1.2.1 runs
# `verification:references:exhausted`, `final_block`. Both product frames passed fidelity and
# lifestyle generation ran; verification then stopped on the LIFESTYLE frame's structural
# Product Truth reading (W5-V1): `compose.lifestyle_evidence` FAILs a frame made from
# pattern-derived references ("chart", informational), whatever the image shows, so no
# regeneration is bought. That is policy (test_v6_gallery_e2e REMAINING_GATES
# "LIFESTYLE-EVIDENCE": a photographic reference of a made sample, or an owner decision), not a
# misread, and it is unchanged here. Separately, every generated non-anchor frame read
# region_palette UNKNOWN because its product region was asked of the `image_vision`-only judge
# (fixed: `fidelity.LIFESTYLE_REGION_ROUTE`).
#
# The redrive: a run blocked at `verification` on a structural reading is restarted ONCE per
# `verify_redrive_version()` to re-verify its stored frames (reverify at `verification`; nothing
# is generated, no attempt is added), and only when today's policy no longer reads any of its
# stored FAILed frames as structural (`candidate_gates.lifestyle_structural`, recomputed free
# from the stored references). While the policy still applies, re-verifying would spend vision
# calls on the same block: the run reads `structural_reference` instead of `final_block`.
# MAX_RESTARTS, the vision route's own daily ceiling, the call cap and the spend plan bind.
STRUCTURAL_MARKER = "(structural: the references are pattern-derived"
VERIFY_REDRIVE_BY = "verification_reverify_redrive"


def structural_verification_block(reason) -> bool:
    """A block whose recorded cause is a structural Product Truth reading at verification."""
    return STRUCTURAL_MARKER in str(reason or "")


def verify_redrive_version() -> str:
    """The verification redrive's once-per key: the fidelity judge, its deterministic checks,
    the lifestyle product-region route and the lifestyle Product Truth policy (19i32,
    D-OWNER-LIFESTYLE-GENERATED: `candidate_gates.LIFESTYLE_POLICY_VERSION`)."""
    from .fidelity import FIDELITY_CHECK_VERSION, FIDELITY_JUDGE_VERSION, LIFESTYLE_REGION_ROUTE

    return (f"{FIDELITY_JUDGE_VERSION}|{FIDELITY_CHECK_VERSION}|{LIFESTYLE_REGION_ROUTE}|"
            f"{CG.LIFESTYLE_POLICY_VERSION}")


def _structural_roles_in(session, key: str) -> tuple[list[str], list[str]]:
    """(roles of run `key` with a stored FAIL recorded as structural, those of them today's
    policy still reads structural). Reads rows; asks no judge."""
    from sqlalchemy import select

    from .image_records import ImageCandidate as IC

    had, still = set(), set()
    for role, slug, version, refs, binding, checks in session.execute(select(
            IC.role, IC.slug, IC.version, IC.references, IC.binding, IC.checks).where(
            IC.run_key == key, IC.technical_status == "FAIL")):
        if structural_failure(checks) is None:
            continue
        had.add(role)
        if CG.lifestyle_structural({"role": role, "slug": slug, "version": version,
                                    "references": list(refs or [])}, dict(binding or {})):
            still.add(role)
    return sorted(had), sorted(still)


def _verify_redriven(stages: dict, version: str) -> bool:
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    return any(isinstance(h, dict) and h.get("by") == VERIFY_REDRIVE_BY
               and h.get("verify_version") == version for h in history)


def _verify_redrive_candidate(db, key: str, reason: str) -> bool:
    """A run the verification redrive owns: blocked at `verification` on a structural
    reading, not an experiment."""
    if "#" in key or not structural_verification_block(reason):
        return False
    return (get_run(db, key) or {}).get("stage") == "verification"


def _sweep_verify_reverify(db, key: str, stages: dict, *, follow, restarted: list,
                           waiting: list, refused: list) -> None:
    version = verify_redrive_version()
    if _verify_redriven(stages, version):
        refused.append({"run_key": key, "kind": "verification_reverify",
                        "why": f"already re-verified under {version}"})
        return
    with db.session() as s:
        had, still = _structural_roles_in(s, key)
    if still or not had:
        refused.append({"run_key": key, "kind": "verification_reverify",
                        "why": f"structural: {still or had} still FAIL on their references "
                               f"under today's policy (an owner decision or a photographic "
                               f"reference of a made sample decides it)"})
        return
    if not _vision_route_usable_read(db):
        waiting.append({"run_key": key, "why": "no vision route is usable for the fidelity "
                                               "verifier; re-verifying would read UNKNOWN"})
        return
    # every frame of the campaign is re-read (conservative: the whole standard gallery)
    ok, why = _vision_headroom(db, SP.CAMPAIGN_MIN_FRAMES)
    if not ok:
        waiting.append({"run_key": key, "why": why})
        return
    try:
        out = restart(db, key, follow=follow, by=VERIFY_REDRIVE_BY, reverify_only=True,
                      reason=f"stored frames re-verified under {version}",
                      record={"verify_version": version})
    except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    (restarted if out.get("restarted") else refused).append(
        {"run_key": key, "kind": "verification_reverify",
         **{k: out[k] for k in ("epoch", "resume_at", "reverify", "why") if k in out}})


# A budget stop whose only cause is the provider's DAILY ceiling is a window, not a verdict:
# nothing was billed (the gate refused before sending) and the ceiling resets at the next UTC
# day. Every other budget stop (the per-gallery cap, a monthly ceiling, a reservation) stays
# final. The run's spend, calls and attempts are never reset; the ceiling still applies on the
# new day, so a restarted run that meets it again simply blocks again.
DAILY_CEILING_CODE = "(provider_daily_ceiling)"
DAILY_REDRIVE_BY = "daily_ceiling_redrive"


def _utc_day(iso: str | None):
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).date()
    except ValueError:
        return None


# D-OWNER-PHOTO-BUDGET (19i32): a run stopped by the per-gallery spend plan under the old plan
# (CA$2.00, 12/20 calls) is re-driven once per plan version (`PLAN_VERSION_TAG`) when the
# current plan leaves room for one more attempt. MAX_RESTARTS per method, the generation
# provider's daily ceiling and the plan itself still bind.
PLAN_REDRIVE_BY = "spend_plan_redrive"
_PLAN_STOP = ("exceeds the plan's call_count", "exceeds the plan's max_spend_cad")


def plan_budget_block(reason) -> bool:
    text = str(reason or "")
    return text.startswith("budget stop") and any(n in text for n in _PLAN_STOP)


def plan_headroom(db, key: str, run: dict) -> dict:
    """`method_headroom` (one product-frame attempt) under the current plan; unreadable: no."""
    try:
        return method_headroom(db, key, run)
    except Exception as exc:  # noqa: BLE001 - unreadable headroom never restarts a run
        return {"ok": False, "why": type(exc).__name__}


def _plan_redriven(stages: dict) -> bool:
    history = (stages.get(RESTART_KEY) or {}).get("history") or []
    return any(isinstance(h, dict) and h.get("by") == PLAN_REDRIVE_BY
               and h.get("plan_version") == PLAN_VERSION_TAG for h in history)


def _sweep_plan_budget(db, key: str, stages: dict, *, follow, restarted: list,
                       waiting: list, refused: list) -> None:
    if _plan_redriven(stages):
        refused.append({"run_key": key, "kind": "spend_plan_raised", "code": "already_redriven",
                        "why": f"already re-driven under {PLAN_VERSION_TAG}"})
        return
    room = plan_headroom(db, key, get_run(db, key) or {})
    if not room.get("ok"):
        refused.append({"run_key": key, "kind": "spend_plan_raised", "code": "final_block",
                        "why": f"the current plan leaves no room for one attempt: {room}"[:500]})
        return
    ok, why = generation_daily_headroom(db, room.get("needed_cad") or _redrive_call_cost_cad())
    if not ok:
        waiting.append({"run_key": key, "kind": "spend_plan_raised",
                        "code": METHOD_REDRIVE_WAIT_DAILY, "why": why})
        return
    try:
        out = restart(db, key, follow=follow, by=PLAN_REDRIVE_BY,
                      reason=f"per-gallery spend plan raised ({PLAN_VERSION_TAG}, "
                             f"D-OWNER-PHOTO-BUDGET)",
                      record={"plan_version": PLAN_VERSION_TAG})
    except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    (restarted if out.get("restarted") else refused).append(
        {"run_key": key, "kind": "spend_plan_raised",
         **{k: out[k] for k in ("epoch", "resume_at", "why", "code") if k in out}})


DAILY_REDRIVE_KEY = "_daily_redrive"   # stages: {"day", "why", "at"} of a refused daily redrive


def _record_daily_refusal(db, key: str, day: str, why: str) -> None:
    """Record that today's daily redrive of `key` was refused (status, reason and
    `updated_at` untouched: the blocked day is read from `updated_at`)."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None or r.status != "blocked":
            return
        st = dict(r.stages or {})
        st[DAILY_REDRIVE_KEY] = {"day": day, "why": why[:500], "at": _now().isoformat()}
        r.stages = st
        flag_modified(r, "stages")


def daily_ceiling_reset(run: dict, now=None) -> bool:
    """True when `run` is a budget stop caused only by the provider's daily ceiling and the
    UTC day has changed since it blocked."""
    reason = str(run.get("blocked_reason") or "")
    if not (reason.startswith("budget stop") and DAILY_CEILING_CODE in reason):
        return False
    blocked_day = _utc_day(run.get("updated_at"))
    today = (now or _now()).astimezone(timezone.utc).date()
    return blocked_day is not None and today > blocked_day


def _gate_of(reason: str) -> str | None:
    for needle, gate in CAPABILITY_GATES:
        if needle in (reason or ""):
            return gate
    return None


# 19i30 GATE-EPISODE: "once" is per gate-closure episode, not forever. The episode is the
# closure that blocked the run: for image_generation, the image.probe row the gate read when
# the run blocked (`images.closure_episode`). The restart's history reason carries it
# (`[episode probe:<id>]`). A history entry written before 19i30 carries none; it belongs to
# the episode in force when it was made, i.e. it counts against the current episode only if
# it was made after that episode's probe. MAX_RESTARTS per method still applies on top.
EPISODE_TAG = "episode "
_EPISODE_RE = re.compile(r"\[episode ([^\]]+)\]")


def _closure_episode(session, gate: str, blocked_at) -> str:
    if gate != "image_generation":
        return f"{gate}:unkeyed"
    from ..gateway import images

    return images.closure_episode(session, blocked_at)


def _episode_probe_at(session, episode: str):
    from ..core.models import AuditLog

    try:
        row = session.get(AuditLog, int(episode.split(":", 1)[1]))
    except (ValueError, IndexError, TypeError):
        return None
    at = row.at if row is not None else None
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def _redriven_in_episode(session, history, gate: str, episode: str) -> bool:
    """Whether `history` already holds a capability redrive for `gate` in `episode`."""
    legacy = []
    for h in history or []:
        reason = str(h.get("reason", ""))
        if h.get("by") != REDRIVE_BY or gate not in reason:
            continue
        m = _EPISODE_RE.search(reason)
        if m:
            if m.group(1) == episode:
                return True
        else:
            legacy.append(h)
    if not legacy:
        return False
    # A pre-19i30 redrive counts against this episode only if it was made after this
    # episode's probe row was written; unknown either way counts (fail closed: no loop).
    at = _episode_probe_at(session, episode) if episode.startswith("probe:") else None
    if at is None:
        return True
    for h in legacy:
        hat = _utc(h.get("at"))
        if hat is None or hat >= at:
            return True
    return False


def redrive_capability_blocked(db, *, follow) -> dict:
    """Restart each run blocked only on a capability gate that is now open, once per closure.

    "Once": a run this has already restarted for the same gate in the same closure episode is
    never restarted for it again (the restart history records `by=capability_redrive` and the
    episode); a later, unrelated closure of the gate may be re-driven once (19i30).
    Everything `restartable` refuses stays refused: a run whose candidate FAILed, a budget
    stop, an experiment, the restart cap. Nothing here generates; the restarted job does, and
    only because the gate it was waiting on is open."""
    from sqlalchemy import select

    from .gallery import gates_now
    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        rows = [(r.run_key, r.blocked_reason or "", dict(r.stages or {}))
                for r in s.scalars(select(ImageProductionRun).where(
                    ImageProductionRun.status == "blocked"))]
        updated = {r.run_key: r.updated_at for r in s.scalars(select(ImageProductionRun).where(
            ImageProductionRun.status == "blocked"))}
    # 19i29: fidelity re-judgements (free re-reads) are judged before any method redrive (a
    # paid regeneration), so a method redrive of a sibling run of the same release sees the
    # re-judgement in flight and waits for it (`_sibling_rejudging`).
    rows.sort(key=lambda t: 0 if (fidelity_unknown_block(t[1]) or fidelity_fail_block(t[1]))
              else 1)
    gates = {g for _n, g in CAPABILITY_GATES}
    open_now = gates_now(db, keys=tuple(sorted(gates)))
    restarted, waiting, refused = [], [], []
    method = {k: [] for k in METHOD_REDRIVE_EVIDENCE}
    for key, reason, stages in rows:
        gate = _gate_of(reason)
        if gate is None and _fidelity_redrive_candidate(db, key, reason) and \
                _sweep_fidelity_unknown(db, key, stages, follow=follow, restarted=restarted,
                                        waiting=waiting, refused=refused):
            continue
        if gate is None and _rejudge_redrive_candidate(db, key, reason, stages):
            _sweep_fidelity_rejudge(db, key, follow=follow, restarted=restarted,
                                    waiting=waiting, refused=refused)
            continue
        if gate is None and _verify_redrive_candidate(db, key, reason):
            _sweep_verify_reverify(db, key, stages, follow=follow, restarted=restarted,
                                   waiting=waiting, refused=refused)
            continue
        if gate is None and _method_redrive_candidate(db, key, reason, stages):
            _sweep_method_redrive(db, key, follow=follow, method=method,
                                  restarted=restarted, refused=refused, waiting=waiting)
            continue
        if gate is None and stale_references_block(reason) and "#" not in key:
            _sweep_stale_references(db, key, stages, follow=follow, restarted=restarted,
                                    refused=refused)
            continue
        if gate is None and provider_transient_block(reason) and "#" not in key:
            hour = _provider_redrive_due(stages, updated.get(key), _now())
            if hour is None:
                waiting.append({"run_key": key, "why": "transient provider block; re-driven "
                                                       "at most once per UTC hour"})
                continue
            try:
                out = restart(db, key, follow=follow, by=PROVIDER_REDRIVE_BY,
                              reason=f"transient provider answer; retried at {hour}")
            except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
                out = {"restarted": False,
                       "why": f"restart not enqueued ({type(exc).__name__})"}
            (restarted if out.get("restarted") else refused).append(
                {"run_key": key, **{k: out[k] for k in ("epoch", "resume_at", "why")
                                    if k in out}})
            continue
        if gate is None and plan_budget_block(reason) and "#" not in key:
            _sweep_plan_budget(db, key, stages, follow=follow, restarted=restarted,
                               waiting=waiting, refused=refused)
            continue
        if gate is None:
            if DAILY_CEILING_CODE in reason and reason.startswith("budget stop"):
                run = get_run(db, key) or {}
                if not daily_ceiling_reset(run):
                    waiting.append({"run_key": key, "why": "provider daily ceiling; resets "
                                                           "at the next UTC day"})
                    continue
                day = str(_now().date())
                history = (stages.get(RESTART_KEY) or {}).get("history") or []
                if any(h.get("by") == DAILY_REDRIVE_BY and day in str(h.get("reason", ""))
                       for h in history):
                    refused.append({"run_key": key, "why": f"already re-driven on {day}"})
                    continue
                judged = stages.get(DAILY_REDRIVE_KEY) or {}
                if isinstance(judged, dict) and judged.get("day") == day:
                    refused.append({"run_key": key, "why": f"already judged on {day}: "
                                                           f"{judged.get('why', '')}"[:500]})
                    continue
                try:
                    out = restart(db, key, follow=follow, by=DAILY_REDRIVE_BY,
                                  reason=f"provider daily ceiling reset on {day}")
                except Exception as exc:  # noqa: BLE001 - restart rolled back; stays blocked
                    out = {"restarted": False,
                           "why": f"restart not enqueued ({type(exc).__name__})"}
                if not out.get("restarted") and out.get("restartable") is False:
                    # REDRIVE-REFUSAL: a preflight refusal is judged once per UTC day, so
                    # `redrive_due` stops reporting the run as due (it lifted the backoff
                    # every hour for a restart that could not happen). A transient failure
                    # (enqueue error, concurrent change) is retried by the next sweep.
                    _record_daily_refusal(db, key, day, str(out.get("why") or ""))
                (restarted if out.get("restarted") else refused).append(
                    {"run_key": key, **{k: out[k] for k in ("epoch", "resume_at", "why")
                                        if k in out}})
            continue
        history = (stages.get(RESTART_KEY) or {}).get("history") or []
        with db.session() as s:
            episode = _closure_episode(s, gate, updated.get(key))
            again = _redriven_in_episode(s, history, gate, episode)
        if again:
            refused.append({"run_key": key, "code": "already_redriven",
                            "why": f"already re-driven once for {gate} in {episode}"})
            continue
        if not open_now.get(gate):
            waiting.append({"run_key": key, "code": "gate_closed",
                            "why": f"{gate} is still closed"})
            continue
        ok, why = generation_daily_headroom(db, _redrive_call_cost_cad())
        if not ok:
            # 19i30: the restart is not spent on a call the daily ceiling would refuse; the
            # next sweep after the UTC day changes restarts it.
            waiting.append({"run_key": key, "code": METHOD_REDRIVE_WAIT_DAILY, "why": why})
            continue
        try:
            out = restart(db, key, follow=follow, by=REDRIVE_BY,
                          reason=f"{gate} opened after the run blocked on it "
                                 f"[{EPISODE_TAG}{episode}]")
        except Exception as exc:  # noqa: BLE001 - the restart rolled back; the run stays blocked
            out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
        (restarted if out.get("restarted") else refused).append(
            {"run_key": key, **{k: out[k] for k in ("epoch", "resume_at", "why")
                                if k in out}})
    return {"restarted": restarted, "waiting": waiting, "refused": refused,
            "method_redrives": method}


def _method_redrive_candidate(db, key: str, reason: str, stages: dict) -> bool:
    """A blocked run the sweep should consider for a method redrive: blocked at the fidelity
    gate (`method_redrive_check` then requires a FAILed role), and not a budget stop."""
    if reason.startswith("budget stop") or "#" in key:
        return False
    run = get_run(db, key) or {}
    return run.get("stage") == "fidelity_gate"


def generation_daily_headroom(db, needed_cad: float) -> tuple[bool, str]:
    """(ok, why): whether some activated paid image generator's own daily ceiling still covers
    `needed_cad` today. Reads only (`paid_provider_gate.daily_headroom_cad`); the ceiling is
    enforced at call time as before. With no active paid generator, or an unreadable store,
    this does not hold the redrive (the generation gate decides, as before)."""
    try:
        from ..gateway import paid_provider_gate as G

        now = _now()
        active = [p for p in G.image_providers()
                  if G.activation_state(db, p, G.GENERATION, now=now)["active"]]
        if not active:
            return True, ""
        lefts = {p: G.daily_headroom_cad(db, p, G.GENERATION, now=now) for p in active}
    except Exception:  # noqa: BLE001 - unreadable: the generation gate decides at call time
        return True, ""
    if any(v is None or v + 1e-9 >= needed_cad for v in lefts.values()):
        return True, ""
    best = max(lefts.values())
    return False, (f"{METHOD_REDRIVE_WAIT_DAILY}: CA${best:.4f} left today under the "
                   f"generation provider's daily ceiling ({', '.join(sorted(lefts))}); one "
                   f"attempt needs CA${needed_cad:.4f}; waits for the next UTC day")


def _sibling_rejudging(session, row) -> str | None:
    """The key of another run of `row`'s release that is being re-judged now (not blocked, not
    finished, its latest restart a fidelity re-judgement), or None."""
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    done = ("blocked", "ready_for_owner_review", "approved_for_publication")
    for other in session.scalars(select(ImageProductionRun).where(
            ImageProductionRun.slug == row.slug, ImageProductionRun.version == row.version,
            ImageProductionRun.release == row.release,
            ImageProductionRun.run_key != row.run_key)):
        if "#" in other.run_key or other.status in done:
            continue
        hist = ((other.stages or {}).get(RESTART_KEY) or {}).get("history") or []
        last = hist[-1] if hist and isinstance(hist[-1], dict) else {}
        if last.get("by") in _REJUDGEMENT_BY:
            return other.run_key
    return None


def _sweep_method_redrive(db, key: str, *, follow, method: dict, restarted: list,
                          refused: list, waiting: list | None = None) -> None:
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    waiting = waiting if waiting is not None else []
    run = get_run(db, key) or {}
    failed = _run_candidates_failed(db, key, run.get("listing", ""))
    chk = method_redrive_check(db, key, run, failed)
    if not chk["eligible"]:
        if chk.get("code"):
            refused.append({"run_key": key, "code": chk["code"], "why": chk.get("why", "")})
        return
    method["eligible"].append(key)
    if not chk["ok"]:
        method["no_headroom"].append(key)
        _record_method_readback(db, key, chk, "no_headroom")
        refused.append({"run_key": key, "code": chk["code"], "why": chk["why"]})
        return
    with db.session() as s:
        row = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        sibling = _sibling_rejudging(s, row) if row is not None else None
    if sibling:
        # 19i29: never race a sibling's re-judgement of the same release; nothing recorded,
        # the next sweep looks again once it has finished.
        waiting.append({"run_key": key, "code": METHOD_REDRIVE_SIBLING,
                        "why": f"{METHOD_REDRIVE_SIBLING}: {sibling} is being re-judged"})
        return
    ok, why = generation_daily_headroom(db, float(
        (chk.get("headroom") or {}).get("needed_cad") or _redrive_call_cost_cad()))
    if not ok:
        # 19i29: day-scoped; the restart is not spent on a call the daily ceiling refuses.
        method["no_headroom"].append(key)
        _record_method_readback(db, key, {**chk, "code": METHOD_REDRIVE_WAIT_DAILY,
                                          "why": why}, "no_headroom", day=str(_now().date()))
        waiting.append({"run_key": key, "code": METHOD_REDRIVE_WAIT_DAILY, "why": why})
        return
    try:
        out = restart(db, key, follow=follow, by=METHOD_REDRIVE_BY,
                      reason=f"generation method changed to {chk['version']}; failures were "
                             f"made under {chk.get('failed_versions')}")
    except Exception as exc:  # noqa: BLE001 - the restart rolled back; the run stays blocked
        out = {"restarted": False, "why": f"restart not enqueued ({type(exc).__name__})"}
    if out.get("restarted"):
        method["done"].append(key)
        _record_method_readback(db, key, chk, "done")
        restarted.append({"run_key": key, **{k: out[k] for k in (
            "epoch", "resume_at", "method_version") if k in out}})
    else:
        if out.get("code") == METHOD_REDRIVE_NO_HEADROOM:
            method["no_headroom"].append(key)
            _record_method_readback(db, key, out.get("method_redrive") or chk, "no_headroom")
        refused.append({"run_key": key, **{k: out[k] for k in ("code", "why") if k in out}})
        # REDRIVE-FIRE: an eligible run whose restart was refused (the restart cap, a
        # concurrent change) is judged under this version: `redrive_due` stops asking.
        _record_method_readback(db, key, {**chk, "code": out.get("code") or chk.get("code"),
                                          "why": out.get("why") or chk.get("why")},
                                "eligible")


# ---- REDRIVE-FIRE: the sweep's own input, for the scheduler's backoff -----------------------
#
# Production 19i18 (2026-11-23T01:50Z): neither redrive fired. Both live inside the hourly
# `chain.successors` sweep, and that cadence sits in the thrash breaker's free-poll backoff at
# 32x (32 hours; BUILD_STATE). The backoff reads "three identical outputs" as an idle poll. A
# run waiting for the UTC day to change does produce identical outputs, because only the
# clock moves. The breaker re-arms a parked free loop once per new release. That probe ran
# under 19i18 before 00:00Z, saw "waiting" again and parked the sweep for another 32 hours.
# The new day came and nothing was left to look at it. The method redrive had the same
# dependency: it fired only if that single per-release probe happened to see the run at the
# right moment.
#
# `redrive_due` is the sweep's input, read from the rows themselves: a restart the sweep
# would make NOW that it could not have made when the backoff was recorded. The breaker
# (`swarm.orchestrate.INPUT_PROBES`) lifts the backoff while one is due. The probe never
# restarts anything: the sweep does that, and its once-per-day and once-per-method rules,
# the restart cap and every spend cap stay where they are. A due restart leaves the "due"
# set once the sweep acts: the run is unblocked, the day's redrive is in its history, or the
# method readback names the current version. So this cannot hold the sweep at hourly
# forever.

def _midnight_after(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)


# REDRIVE-ELIGIBILITY (19i28): the verdict for every blocked run, so the evidence readback can
# show WHY a run is not due. Production 19i27 (12:59Z): `redrive_due` read None and nothing
# said that both hexagon-coaster runs sat at MAX_RESTARTS (that branch was a silent
# `continue`). `refused` is a fixed vocabulary, never free text.
REDRIVE_KINDS = ("stale_references", "provider_transient", "daily_ceiling_reset",
                 "fidelity_unknown", "fidelity_rejudge", "method_redrive", "capability_gate",
                 "verification_reverify", "spend_plan_raised", "none")
REDRIVE_REFUSALS = ("max_restarts", "experiment_one_shot", "already_redriven",
                    "refusal_held", "already_judged_now", "hourly_backoff",
                    "waiting_daily_reset", "seen_by_sweep", "no_frame_to_reread",
                    "failed_under_current_method", "no_failure", "gate_closed_or_redriven",
                    "final_block", "sibling_rejudging", "structural_reference")


def _redrive_kind(reason: str, stage: str) -> str:
    """Which redrive owns a blocked run of this reason and stage (none: a final block)."""
    if _gate_of(reason) is not None:
        return "capability_gate"
    if stale_references_block(reason):
        return "stale_references"
    if provider_transient_block(reason):
        return "provider_transient"
    if reason.startswith("budget stop") and DAILY_CEILING_CODE in reason:
        return "daily_ceiling_reset"
    if plan_budget_block(reason):
        return "spend_plan_raised"
    if stage == "fidelity_gate" and fidelity_unknown_block(reason):
        return "fidelity_unknown"
    if stage == "fidelity_gate" and fidelity_fail_block(reason):
        return "fidelity_rejudge"
    if stage == "fidelity_gate" and not reason.startswith("budget stop"):
        return "method_redrive"
    if stage == "verification" and structural_verification_block(reason):
        return "verification_reverify"
    return "none"


def _redrive_verdict(session, r, since, now: datetime, memo: dict) -> dict:
    """{"kind", "due", "refused", "at", "restarts_spent", "restarts_total", "hold"} for one
    blocked run row `r`: whether the hourly sweep would restart it now and could not have at
    `since` (`due`), else the first refusal that holds (`refused`, from REDRIVE_REFUSALS).
    `restarts_spent` is the count under the current generation-method version (what
    MAX_RESTARTS reads, D-RESTART-PER-METHOD), `restarts_total` every version's; `hold` the
    recorded cause (HOLD_CODES) when `refused` is `refusal_held`. Reads rows only."""
    from sqlalchemy import select

    from .image_records import ImageCandidate

    key, reason, stages = r.run_key, r.blocked_reason or "", dict(r.stages or {})
    today = now.date()
    kind = _redrive_kind(reason, r.stage)
    rec = stages.get(RESTART_KEY) or {}
    if "current" not in memo:
        memo["current"] = current_method_version()
    counts = restart_counts(session, r, current=memo["current"]) if rec else {}
    spent = int(counts.get("current") or 0)
    out = {"kind": kind, "due": False, "refused": None, "at": None, "restarts_spent": spent,
           "restarts_total": int(counts.get("total") or 0), "hold": None}
    holds: list = []

    def no(code: str) -> dict:
        hold = None
        if code == "refusal_held":
            hold = next((h for h in holds if h), "other")
        return {**out, "refused": code, "hold": hold}

    def yes(kind_: str, at: str) -> dict:
        return {**out, "kind": kind_, "due": True, "at": at}

    if "#" in key:
        return no("experiment_one_shot")
    if spent >= MAX_RESTARTS:
        # Every restart path refuses this run (`restartable`). Not due: the probe must not lift
        # the sweep's backoff for it. Visible in the readback, never silently skipped.
        return no("max_restarts")
    history = rec.get("history") or []
    if kind == "capability_gate" and r.stage != "fidelity_gate":
        # 19i30: once per closure episode. The sweep restarts it once its gate opens
        # (`gates_now`, not a row read; the readback shows the gate beside this verdict).
        gate = _gate_of(reason) or ""
        if _redriven_in_episode(session, history, gate,
                                _closure_episode(session, gate, r.updated_at)):
            return no("already_redriven")
        return no("gate_closed_or_redriven")
    if kind == "stale_references":
        if not _stale_redriven(stages, references_version()):
            return yes(kind, now.isoformat())
        return no("already_redriven")
    if kind == "provider_transient":
        if _provider_redrive_due(stages, r.updated_at, now) is not None:
            return yes(kind, now.isoformat())
        return no("hourly_backoff")
    if kind == "daily_ceiling_reset":
        blocked_day = _utc_day(r.updated_at.isoformat() if r.updated_at else None)
        if blocked_day is None or today <= blocked_day:
            return no("waiting_daily_reset")
        reset_at = _midnight_after(blocked_day)
        if since is not None and reset_at <= since:
            return no("seen_by_sweep")    # the backoff was recorded after the reset
        day = str(today)
        if any(h.get("by") == DAILY_REDRIVE_BY and day in str(h.get("reason", ""))
               for h in history if isinstance(h, dict)):
            return no("already_redriven")
        judged = stages.get(DAILY_REDRIVE_KEY) or {}
        if judged.get("day") == day and not _cap_hold_lifted(judged, spent):
            holds.append(hold_code(judged))
            return no("refusal_held")     # the sweep already judged it today and was refused
        return yes(kind, reset_at.isoformat())
    if kind == "spend_plan_raised":
        # D-OWNER-PHOTO-BUDGET: once per plan version, while the raised plan leaves room for
        # one attempt (the sweep then checks the provider's daily headroom).
        if _plan_redriven(stages):
            return no("already_redriven")
        plan = _spend_plan(key, None)        # rows only: the code plan (the sweep reads the
        calls_left = int(plan["call_count"]) - int(counted_calls(session, r))  # owner's too)
        spend_left = float(plan["max_spend_cad"]) - float(r.spent_cad or 0.0)
        if calls_left < 1 or spend_left + 1e-9 < _redrive_call_cost_cad():
            return no("final_block")
        return yes(kind, now.isoformat())
    if kind == "verification_reverify":
        # VERIFY-REFS: once per verify version, and only when today's policy no longer reads
        # a stored frame as structural (free; the sweep then checks the vision route).
        if _verify_redriven(stages, verify_redrive_version()):
            return no("already_redriven")
        had, still = _structural_roles_in(session, key)
        if still or not had:
            return no("structural_reference")
        return yes(kind, now.isoformat())
    first = None
    if r.stage == "fidelity_gate" and fidelity_unknown_block(reason):
        # IMAGE-FIDELITY-ROUTE: due once per (judge version, check version); a refusal holds
        # for the UTC day (no vision route, no vision headroom) or for the versions (restart
        # refused, or a FAILed role, which the method redrive below then judges).
        version = fidelity_judge_version()
        if _fidelity_redriven(stages, version):
            first = "already_redriven"
        elif _fidelity_refusal_holds(stages, version, str(today), spent=spent):
            first = "refusal_held"
            holds.append(hold_code(stages.get(FIDELITY_REDRIVE_KEY)))
        elif _anchor_frames_judged_now(session, key, version):
            first = "already_judged_now"
        else:
            return yes("fidelity_unknown", now.isoformat())
    if r.stage == "fidelity_gate" and fidelity_fail_block(reason):
        # IMAGE-FIDELITY-2: due once per fidelity judge version while a FAILed anchor
        # frame would be read differently; a refusal holds for the day or the version.
        version = fidelity_judge_version()
        if _rejudged(stages, version, str(today), spent=spent):
            first = first or "already_redriven"
        elif not _rejudge_ids_in(session, key, version):
            first = first or "no_frame_to_reread"
        else:
            return yes("fidelity_rejudge", now.isoformat())
    if r.stage == "fidelity_gate" and not reason.startswith("budget stop"):
        current = memo["current"]
        if any(isinstance(h, dict) and h.get("method_version") == current for h in history):
            return no(first or "already_redriven")
        mr = stages.get(METHOD_REDRIVE_KEY) or {}
        if mr.get("version") == current and not _cap_hold_lifted(mr, spent) \
                and mr.get("day") in (None, str(today)):
            # judged under this method (no headroom, a refused restart); a wait for the
            # generation provider's daily ceiling holds for its UTC day only
            if not first:
                holds.append(hold_code(mr) if mr.get("code") != METHOD_REDRIVE_WAIT_DAILY
                             else "generation_headroom")
            return no(first or "refusal_held")
        fails = [candidate_method_version(c) for (c,) in session.execute(
            select(ImageCandidate.checks).where(ImageCandidate.run_key == key,
                                                ImageCandidate.technical_status == "FAIL"))]
        if not fails:
            return no(first or "no_failure")
        if current in fails:
            return no(first or "failed_under_current_method")
        if _sibling_rejudging(session, r):
            return no(first or "sibling_rejudging")
        return yes("method_redrive", now.isoformat())
    return no(first or "final_block")


def _blocked_rows(session):
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    return session.scalars(select(ImageProductionRun).where(
        ImageProductionRun.status == "blocked").order_by(ImageProductionRun.id))


def redrive_due(session, since, *, now: datetime | None = None) -> dict | None:
    """The first blocked run the hourly sweep would restart now but could not have restarted
    at `since`, as {"at", "run_key", "kind"}; None when there is none. Reads rows only."""
    now = (now or _now()).astimezone(timezone.utc)
    since = since if since is None or since.tzinfo else since.replace(tzinfo=timezone.utc)
    memo: dict = {}
    for r in _blocked_rows(session):
        v = _redrive_verdict(session, r, since, now, memo)
        if v["due"]:
            return {"at": v["at"], "run_key": r.run_key, "kind": v["kind"]}
    return None


MAX_READBACK_RUNS = 40


def redrive_readback(session, *, now: datetime | None = None) -> dict:
    """REDRIVE-ELIGIBILITY: per blocked run key, whether the hourly sweep would restart it now
    and, if not, why -- {"runs": {run_key: {"kind", "eligible", "refused", "restarts_spent",
    "restarts_total", "max_restarts", "hold"}}, "counts": {...}}. `restarts_spent` is the count
    under the current generation-method version (D-RESTART-PER-METHOD), `restarts_total` every
    version's. Fixed vocabulary and counts only; no reason text, no record. Reads rows
    only (the sweep's own day-only checks -- a usable vision route, its headroom -- are
    recorded by the sweep as a refusal and read back here as `refusal_held`)."""
    now = (now or _now()).astimezone(timezone.utc)
    memo: dict = {}
    runs: dict = {}
    counts = {"blocked": 0, "eligible": 0, "at_max_restarts": 0,
              "by_refusal": {k: 0 for k in REDRIVE_REFUSALS}}
    for r in _blocked_rows(session):
        v = _redrive_verdict(session, r, None, now, memo)
        counts["blocked"] += 1
        if v["due"]:
            counts["eligible"] += 1
        else:
            counts["by_refusal"][v["refused"]] += 1
            if v["refused"] == "max_restarts":
                counts["at_max_restarts"] += 1
        if len(runs) < MAX_READBACK_RUNS:
            runs[str(r.run_key)[:200]] = {"kind": v["kind"], "eligible": bool(v["due"]),
                                          "refused": v["refused"],
                                          "restarts_spent": int(v["restarts_spent"]),
                                          "restarts_total": int(v["restarts_total"]),
                                          "max_restarts": MAX_RESTARTS,
                                          "hold": v.get("hold")}
    counts["by_refusal"] = {k: n for k, n in counts["by_refusal"].items() if n}
    return {"runs": runs, "counts": counts}


def redrive_input_probe(session, since) -> dict | None:
    """`swarm.orchestrate.INPUT_PROBES` entry for `chain.successors`."""
    hit = redrive_due(session, since)
    return {"at": hit["at"], "input": hit["kind"]} if hit else None


# ---- the owner's two-step method (ENG-IMAGES-LAURA) ---------------------------------------------

def _accepted_product_frame(db, key: str, listing: str) -> dict | None:
    """Step 1's output: this gallery's product frame that PASSed the fidelity gate, as a
    reference whose bytes are re-read from the artifact store and must hash to the stored
    sha256. None when no product frame of this run is accepted."""
    b = _best(db, listing=listing, role=ANCHOR_ROLE, run=key)
    if not b or b.get("technical_status") != "PASS" or not b.get("sha256"):
        return None
    if _anchor_has_negative_decision(db, b.get("candidate_id")):
        return None
    ref = _prior_ref(db, b["sha256"], PRODUCT_FRAME_LABEL)
    if ref is None:
        return None
    return {**ref, "candidate_id": b["candidate_id"]}


def _correction_refs(db, prior: dict | None) -> dict:
    """ENG-MANUAL-METHOD: the failed product candidate (and the side view judged with it) as
    `correction_base` prior references, by their stored bytes. {} when unreadable."""
    if not prior or not prior.get("sha256") or prior.get("technical_status") != "FAIL":
        return {}
    out = {}
    base = _prior_ref(db, prior["sha256"], CORRECTION_LABEL)
    if base:
        out["anchor"] = [base]
    side_sha = _anchor_side_sha(db, prior.get("candidate_id"))
    side = _prior_ref(db, side_sha, CORRECTION_LABEL) if side_sha else None
    if side:
        out["side"] = [side]
    return out


def _anchor_side_sha(db, candidate_id) -> str | None:
    if not candidate_id:
        return None
    from .image_records import ImageCandidate

    with db.session() as s:
        row = s.get(ImageCandidate, candidate_id)
        side = ((row.checks or {}).get("_anchor_side") or {}) if row is not None else {}
    sha = side.get("sha256") if isinstance(side, dict) else None
    return str(sha) if sha else None


def _accepted_product_side(db, key: str, listing: str) -> dict | None:
    """A vessel's side view that was judged, as one pair, with the accepted product frame:
    the same accepted product from the side. None for a flat product."""
    b = _best(db, listing=listing, role=ANCHOR_ROLE, run=key)
    if not b or b.get("technical_status") != "PASS":
        return None
    sha = _anchor_side_sha(db, b.get("candidate_id"))
    return _prior_ref(db, sha, PRODUCT_SIDE_LABEL) if sha else None


def reference_provenance(product_frame: dict, laura: list[dict], *, outfit_id: str | None,
                         identity_id: str) -> dict:
    """What a Laura frame is conditioned on, by hash, in the order FLUX 3 receives it
    (`image_stages.OWNER_METHOD_ROLES`: canonical face, torso, full length, then the accepted
    product frame), and the digest that keys its idempotency."""
    from . import conditioning

    by_frame = {r.get("frame"): r["sha256"] for r in laura}
    lsha = [by_frame.get(f) for f in conditioning.FRAME_ORDER]
    images = [{"position": i + 1, "role": role, "sha256": sha} for i, (role, sha) in enumerate(
        zip(("laura_face", "laura_torso", "laura_body", "product_candidate"),
            lsha + [product_frame["sha256"]]))]
    material = json.dumps({"method": OWNER_METHOD, "images": [i["sha256"] for i in images],
                           "outfit_id": outfit_id}, separators=(",", ":"), sort_keys=True)
    return {"method": OWNER_METHOD, "identity_id": identity_id, "images": images,
            "accepted_product_frame": {"candidate_id": product_frame.get("candidate_id"),
                                       "sha256": product_frame["sha256"]},
            "laura_references": dict(zip(conditioning.FRAME_ORDER, lsha)),
            "outfit_id": outfit_id,
            "input_digest": hashlib.sha256(material.encode()).hexdigest()}


def _owner_operation(key: str, stage: str, role: str, segment: str, experiment: bool) -> str:
    """The replay key of an owner-method generation: the run, stage, role and input hashes --
    deliberately not the restart epoch, so a redrive of the same inputs is never bought twice."""
    material = json.dumps([key, stage, role, OWNER_METHOD, segment]
                          + (["experiment"] if experiment else []), separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


# ---- stage A and stage D (W-VISNEXT2) --------------------------------------------------------

def _prior_ref(db, sha: str, label: str) -> dict | None:
    from ..core.artifacts import ArtifactStore

    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception:  # noqa: BLE001 - bytes gone: not handed in
        return None
    return {"kind": "prior_candidate", "label": label, "sha256": sha, "data": data} \
        if data and hashlib.sha256(data).hexdigest() == sha else None


def _anchor_has_negative_decision(db, candidate_id) -> bool:
    """A negative decision on THIS product-frame candidate (owner disapproval or a rejected
    outcome). Scoped to the candidate, not its bytes: a later frame that happens to share
    bytes and is rejected for its own reason (e.g. wardrobe repetition) never voids step 1."""
    from sqlalchemy import or_, select
    from .image_records import ImageCandidate

    if candidate_id is None:
        return True
    with db.session() as session:
        return session.scalar(select(ImageCandidate.id).where(
            ImageCandidate.id == candidate_id,
            or_(ImageCandidate.owner_visual_approval.is_(False),
                ImageCandidate.outcome == "rejected"),
        ).limit(1)) is not None


def _image_has_negative_decision(db, *, slug: str, version: str, sha: str) -> bool:
    """Hold duplicate image bytes when a record has a negative decision.

    This read does not authenticate the decision or fence concurrent writers.
    """
    from sqlalchemy import or_, select
    from .image_records import ImageCandidate

    with db.session() as session:
        return session.scalar(select(ImageCandidate.id).where(
            ImageCandidate.slug == slug, ImageCandidate.version == version,
            ImageCandidate.sha256 == sha,
            or_(ImageCandidate.owner_visual_approval.is_(False),
                ImageCandidate.outcome == "rejected"),
        ).limit(1)) is not None


def _accepted_identity_anchor(db, key: str) -> dict | None:
    """The identity anchor this run accepted at stage A (PASS, or owner-confirmed review)."""
    rec = (_stage_data(db, key).get("identity_anchor") or {}).get("outputs") or {}
    sha = rec.get("accepted_sha256")
    return _prior_ref(db, sha, "identity_anchor") if sha else None


def _accepted_lifestyle(db, key: str, listing: str, plan: dict, *, slug: str,
                        version: str, release: str) -> dict | None:
    """The edit base for stage D: the run's best LIFESTYLE frame that no check FAILed and the
    owner did not reject. It is a generation input, not a verdict: the variant made from it is
    judged on its own."""
    from .fidelity import same_release

    canonical = run_key(slug, version, release)
    if not same_release(release, release) or not (
            key in (canonical, canonical + ROUTE_SUFFIX) or key.startswith(canonical + "#")):
        return None
    roles = [r["role"] for r in SP.generated_roles(plan) if r["job"] == "LIFESTYLE"]
    for role in roles:
        try:
            b = _best(db, listing=listing, role=role, run=key,
                      slug=slug, version=version, release=release)
            if not b or not b.get("sha256") or b.get("technical_status") not in ("PASS", "UNKNOWN"):
                continue
            if b.get("failed") or b.get("outcome") == "rejected" or \
                    b.get("owner_visual_approval") is False:
                continue
            fidelity = b.get("fidelity") or {}
            checks = fidelity.get("checks") or []
            if fidelity.get("status") == "FAIL" or any(
                    not isinstance(c, dict) or c.get("status") == "FAIL"
                    or c.get("blocks_variant_input") is True
                    or (c.get("check") == "anchor_consistency" and c.get("status") == "UNKNOWN")
                    or (c.get("check") == "craft_texture" and c.get("status") == "UNKNOWN"
                        and isinstance(c.get("reading"), dict)
                        and (str(c["reading"].get("fabric_visible_clearly") or "").strip().lower()
                             not in ("true", "yes")
                             or str(c["reading"].get("craft") or "").strip().lower()
                             not in ("crochet", "knitting", "woven", "printed"))) for c in checks):
                continue
            if _image_has_negative_decision(db, slug=b["slug"], version=b["version"],
                                            sha=b["sha256"]):
                continue
            ref = _prior_ref(db, b["sha256"], "edit_base")
            if ref:
                return ref
        except Exception:  # noqa: BLE001 - unreadable evidence must not be used as input
            continue
    return None


def _drifted_dimensions(best: dict | None, db) -> list[str]:
    from .image_records import ImageCandidate

    if not best:
        return []
    with db.session() as s:
        row = s.get(ImageCandidate, best["candidate_id"])
        body = ((row.checks or {}).get("body_proportions") or {}) if row else {}
    if body.get("status") != "FAIL":
        return []
    return list(body.get("drifted") or ["bust and body proportions"])


def _stage_identity_anchor(db, key, run, inputs, *, gen, judges, exp, laura_roles, st, go,
                           block, refs, laura_refs, slug, version, release, operation_for) -> dict:
    """Stage A. PASS: accepted and reused. A judged body-proportion drift gets exactly one
    correction pass. FAIL after that: blocked (attempts spent). UNKNOWN: an identity review is
    opened for the owner and the run stops at this gate with every image kept; it resumes only
    after the owner's review (then `restart`), and the review never turns the verdict into a
    PASS: the anchor becomes a reference, nothing more."""
    from . import identity_gate

    stage = "identity_anchor"
    owner = exp is None and bool(getattr(gen, "accepts_owner_method", False))
    if (not laura_roles or exp is not None or owner
            or not getattr(gen, "accepts_staged_method", False)):
        why = ("no Laura in this listing's shot plan" if not laura_roles else
               "EXPERIMENT: the owner-approved plan has no stage A" if exp is not None else
               f"{OWNER_METHOD}: every Laura frame is conditioned on the accepted product "
               f"frame and the canonical identity images only; no identity anchor is bought"
               if owner else "the generator does not carry the staged method")
        _update(db, key, stage=stage, status=st, record={"outputs": {"skipped": why}})
        return {"run_key": key, "next": go(_next(stage))}
    outfit = outfits.get(db, run["outfit_id"]) if run["outfit_id"] else None
    if not outfit:
        return block("stage A needs the listing's reserved outfit")
    best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    if best and inputs.get("reverify"):
        reverify(db, best["candidate_id"], judges=judges, exp=exp)
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)

    def generate(repair=None):
        n = _attempts(db, key, IDENTITY_ANCHOR_ROLE) + 1
        return _generate(db, key, gen, slug=slug, version=version, release=release,
                         role=IDENTITY_ANCHOR_ROLE, stage=stage, laura=True, judges=judges,
                         brief="Laura alone in the listing's outfit", outfit=outfit,
                         refs=refs() + laura_refs(), plan_attempt=n, repair=repair, exp=exp,
                         operation=operation_for(IDENTITY_ANCHOR_ROLE,
                                                 "correction" if repair else "initial"))

    if best is None:
        got = generate()
        if got.get("provider_error"):
            return block(f"identity anchor: provider error {got['provider_error']}")
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    drift = _drifted_dimensions(best, db)
    if drift and _attempts(db, key, IDENTITY_ANCHOR_ROLE) < MAX_IDENTITY_ANCHOR_ATTEMPTS:
        generate(repair={"correction": drift, "codes": ["body_proportion_drift"],
                         "directives": []})
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    status = (best or {}).get("technical_status", "UNKNOWN")
    record = {"evidence": best}
    if status == "PASS":
        _update(db, key, stage=stage, status=st, record={
            **record, "outputs": {"accepted_sha256": best["sha256"], "basis": "PASS"}})
        return {"run_key": key, "next": go(_next(stage))}
    if status == "FAIL":
        return block(f"identity anchor FAIL after {_attempts(db, key, IDENTITY_ANCHOR_ROLE)} "
                     f"attempt(s) (one proportion correction at most): {best.get('failed')}",
                     exhausted=True, record=record)
    # UNKNOWN: the owner reviews the anchor (identity review band), never auto-passed.
    review = _anchor_review(db, best["sha256"])
    if review and review.get("decision") == "confirmed_same_person":
        _update(db, key, stage=stage, status=st, record={
            **record, "outputs": {"accepted_sha256": best["sha256"],
                                  "basis": "owner review confirmed_same_person; the anchor is "
                                           "identity context only, its verdict stays UNKNOWN",
                                  "review_id": review["id"]}})
        return {"run_key": key, "next": go(_next(stage))}
    if review and review.get("decision") in ("not_laura",):
        return block("identity anchor: the owner's review says not Laura", exhausted=True,
                     record=record)
    gate = {"review_required": True, "band": identity_gate.BAND_REVIEW,
            "why": f"identity anchor UNKNOWN on {best.get('unknown')}",
            "validity": None, "biometric": None, "judges": []}
    rid = identity_gate.open_review(db, product_class="laura_identity_anchor",
                                    subject=f"{key}:identity_anchor", gate=gate,
                                    image_sha256=best["sha256"])
    return block(f"identity anchor UNKNOWN ({best.get('unknown')}): held for owner review "
                 f"(identity review {rid}); every image so far is kept", record={
                     **record, "outputs": {"review_id": rid}})


def _anchor_review(db, sha: str) -> dict | None:
    """The latest identity review of this anchor's bytes, open or resolved."""
    from sqlalchemy import desc, select

    from .rnd import models as M

    if not M.tables_exist(db):
        return None
    with M.session(db) as s:
        r = s.scalar(select(M.VisualIdentityReview).where(
            M.VisualIdentityReview.image_sha256 == sha[:64])
            .order_by(desc(M.VisualIdentityReview.id)))
        return ({"id": r.id, "state": r.state, "decision": r.decision or None}
                if r is not None else None)


def resolve_identity_anchor_review(db, key: str, *, decision: str, by: str, note: str = "",
                                   follow=None) -> dict:
    """The owner's review of a held identity anchor, then (if confirmed) a restart.

    `confirmed_same_person` lets the anchor be used as identity context; it does not make
    any verdict PASS. `not_laura` ends the run's stage A. `inconclusive` keeps it held."""
    from . import identity_gate

    run = get_run(db, key)
    if run is None:
        return {"resolved": False, "why": "no such run"}
    best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    review = _anchor_review(db, best["sha256"]) if best else None
    if not review or review["state"] != "open":
        return {"resolved": False, "why": "no open identity review for this run's anchor"}
    out = identity_gate.resolve(db, review["id"], decision=decision, reviewer=by, note=note)
    restarted = None
    if decision in ("confirmed_same_person", "not_laura") and follow is not None:
        restarted = restart(db, key, follow=follow, by=by,
                            reason=f"identity anchor review: {decision}")
    return {"resolved": True, **out, "restart": restarted}


def _repick_outfit(db, listing: str, current: str) -> dict:
    """WARDROBE_REPETITION repair: a new distinct complete outfit, the current one excluded,
    replacing it for this listing. The old one stays bound to the listing (retired)."""
    from . import styling

    styled = styling.select_for_listing(db, listing, exclude=[current])
    o = styled.get("outfit")
    if not o:
        return {"replaced": False, "why": styled.get("why")}
    try:
        outfits.register(db, outfit_id=o["outfit_id"], garments=o["garments"],
                         colours=o["colours"], concept=styled["concept"])
        outfits.approve(db, o["outfit_id"],
                        approved_by=f"creative_director:{styling.STYLING_VERSION}")
    except outfits.OutfitRefused as exc:
        return {"replaced": False, "why": str(exc)}
    return outfits.replace(db, current, o["outfit_id"], listing)


def _repair_for(best: dict | None) -> dict | None:
    """Targeted repair for a failed candidate, or None when it cannot be repaired by
    regeneration (an unrouted code, or a structural failure such as a LIFESTYLE
    `lifestyle_evidence` FAIL on a chart reference: see
    `structural_failure`). Codes from the shared Product Truth set route to prompt
    negatives or a reference change. Other failures (identity, outfit, body proportions,
    quality) are regenerated with the same canonical references, and nothing is waived."""
    from . import repair_routes

    # A prompt-only repair cannot resolve a structural reference failure, even
    # when it could address another defect on the same candidate.
    if (best or {}).get("structural"):
        return None
    cats = list((best or {}).get("failure_categories") or [])
    shared = set(repair_routes.shared_codes()["codes"]) | set(repair_routes.ROUTES)
    codes = [c for c in cats if c in shared or c.isupper()]
    routed = repair_routes.route(codes)
    if routed["unrouted"]:
        return None
    # ENG-COASTER-SIDES: a failing check may name its own fix ("coaster has 8 sides; must be
    # 6 (a hexagon)"); it leads that code's negatives, so the repair says what to change.
    fixes: dict[str, list[str]] = {}
    for c in ((best or {}).get("fidelity") or {}).get("checks") or []:
        if isinstance(c, dict) and c.get("status") == "FAIL" and c.get("code") and \
                isinstance(c.get("fix"), str) and c["fix"]:
            fixes.setdefault(c["code"], []).append(f"to fix: {c['fix']}")
    routed["directives"] = [
        {**d, "negatives": list(dict.fromkeys(fixes[d["code"]] + list(d.get("negatives") or [])))}
        if d.get("code") in fixes else d for d in routed["directives"]]
    return {"codes": codes, "directives": routed["directives"],
            "stays_unknown": routed["stays_unknown"],
            "regenerate_for": sorted(set(cats) - set(codes))}


def _recommend(not_ready: list, view: dict) -> list[str]:
    out = []
    for r in not_ready:
        c = r.get("candidate") or {}
        if "identity" in (c.get("failed") or {}):
            out.append(f"{r['role']}: identity drift; regenerate with the canonical references")
        if "product_truth" in (c.get("failed") or {}):
            out.append(f"{r['role']}: product fidelity failed; a qualified sample photo "
                       f"reference (physical_upgrade.intake) is the truthful fix")
        for u in c.get("unknown") or []:
            out.append(f"{r['role']}: {u} UNKNOWN; fund/qualify the verifier, never waive it")
    if any("F-852" in b for b in view["publication_blockers"]):
        out.append("publication: F-852 refuses generated product imagery; an owner policy "
                   "decision is required (VISREF E4), or a photo of a made sample")
    return sorted(set(out))


def _is_launch(listing: str) -> bool:
    from ..products import launch0

    return listing in launch0.LAUNCH0_SLUGS


# ---- gallery assembly / readiness (both methods) ----------------------------------------

def _dashboard_identity(db, listing: str) -> tuple[dict | None, bool]:
    """Resolve a single production identity for an unscoped dashboard, or hold ambiguity."""
    from sqlalchemy import and_, or_, select
    from .fidelity import same_release
    from .image_records import ImageCandidate

    with db.session() as session:
        rows = list(session.execute(select(
            ImageCandidate.slug, ImageCandidate.version, ImageCandidate.release,
            ImageCandidate.run_key, ImageCandidate.method,
        ).where(ImageCandidate.listing == listing).where(or_(
            and_(ImageCandidate.run_key == "", ImageCandidate.method == "owner_submitted"),
            and_(ImageCandidate.run_key != "", ~ImageCandidate.run_key.like("%#%")),
        )).distinct().limit(256)))
    if not rows:
        return None, False
    if len(rows) == 256:
        return None, True
    identities = set()
    for slug, version, release, key, method in rows:
        if (not isinstance(slug, str) or not slug or not isinstance(version, str) or not version
                or not same_release(release, release)
                or (key and key not in (run_key(slug, version, release),
                                        run_key(slug, version, release, route=SP.FLUX_ROUTE)))
                or (not key and method != "owner_submitted")):
            return None, True
        identities.add((slug, version, release.lower()))
    if len(identities) != 1:
        return None, True
    slug, version, release = identities.pop()
    return {"slug": slug, "version": version, "release": release}, False


def readiness(db, listing: str, *, run_key_: str | None = None, plan: dict | None = None) -> dict:
    """The shot plan with what fills each role, the set check and publication blockers."""
    from ..gates.asset_truth import AssetClass
    from ..publish import eligibility as el
    from .fidelity import same_release

    plan = plan or SP.campaign_plan(listing)
    run = get_run(db, run_key_) if run_key_ else None
    identity = None
    ambiguous = False
    if run and run.get("listing") == listing:
        release = run.get("release") or ""
        canonical = run_key(run.get("slug", ""), run.get("version", ""), release)
        if (isinstance(run_key_, str) and same_release(release, release) and
                (run_key_ in (canonical, canonical + ROUTE_SUFFIX)
                 or run_key_.startswith(canonical + "#"))):
            identity = {"slug": run["slug"], "version": run["version"], "release": release}
    if not run_key_:
        identity, ambiguous = _dashboard_identity(db, listing)
    elif identity is None:
        ambiguous = True
    roles, set_cands, blockers, chosen = [], [], set(), []
    if ambiguous:
        blockers.add("generated candidates have ambiguous or unavailable production identity; select a valid run")
    for r in plan["roles"]:
        entry = {"position": r["position"], "role": r["role"], "job": r["job"],
                 "campaign_role": r.get("campaign_role"), "laura": r.get("laura"),
                 "required_by": r["required_by"], "conditional": r["conditional"],
                 "preferred_source": r["preferred_source"]}
        best = None
        if r.get("generate"):
            if run_key_ and identity:
                best = _best(db, listing=listing, role=r["role"], run=run_key_, **identity)
                if best is None and run_key_ == canonical:
                    best = _best(db, listing=listing, role=r["role"], unscoped_only=True,
                                 method="owner_submitted", **identity)
            elif not run_key_ and identity:
                best = _best(db, listing=listing, role=r["role"], production_only=True, **identity)
            if best is not None:
                chosen.append(best)
                for b in best.get("blockers") or []:
                    blockers.add(b)
        # ENG-COASTER-SIDES: only a PASS frame counts toward a valid gallery. A frame whose
        # verdict is UNKNOWN (or FAIL) is never "publishable" here, whatever its stored flag.
        if best is not None and best["publishable"] and best.get("technical_status") == "PASS":
            entry.update(source="generated", candidate=best, status="publishable")
            set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}", medium=CG.MEDIUM,
                                          purpose=el.CONVERSION_CREATIVE, job=r["job"],
                                          position=r["position"]))
        elif r["sources"][SP.DISCLOSED] == SP.SATISFIES:
            entry.update(source="generated" if r.get("generate") else "disclosed_render",
                         candidate=best,
                         status=("disclosed set (certified by the existing listing-set "
                                 "certificate path)" + (
                                     f"; generated candidate {best['technical_status']}, "
                                     f"not publishable" if best else
                                     "; generated candidate missing" if r.get("generate")
                                     else "")),
                         fallback="disclosed_render")
            medium, purpose = r["disclosed_medium"]
            set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}",
                                          medium=AssetClass(medium), purpose=purpose,
                                          job=r["job"], position=r["position"]))
        else:
            entry.update(source="generated" if r.get("generate") else r["preferred_source"],
                         candidate=best,
                         status=("missing" if best is None else
                                 f"candidate {best['technical_status']}, not publishable"))
        if r.get("gap"):
            entry["gap"] = r["gap"]
        roles.append(entry)
    set_check = el.check_set(set_cands) if set_cands else {"ok": False, "problems": [
        {"kind": "no_valid_frames"}]}
    # ENG-VISUAL: the seven-frame campaign standard (shot_plans.CAMPAIGN_MIN_FRAMES). A plan
    # below it is never gallery-ready, and its shortfall is a set-check problem.
    standard = SP.campaign_standard(plan)
    if not standard["ok"]:
        set_check = {"ok": False, "problems": list(set_check["problems"])
                     + list(standard["problems"])}
    # D-OWNER-LAURA-MANDATORY (owner, 2026-11-23: "Laura and model photography is
    # mandatory"): a gallery is never ready without an accepted (publishable, generated)
    # Laura lifestyle frame. A disclosed render or a missing frame does not satisfy it.
    # The plan marks every Laura frame (`laura`), whatever its job: at least one must hold a
    # generated Laura frame that no check FAILed. PASS or UNKNOWN both qualify -- the Laura
    # identity verifier is not production-qualified yet (UNKNOWN is the honest reading and the
    # owner card says so); publishability is the separate publication gate, judged elsewhere.
    # ENG-COASTER-SIDES: the UNKNOWN allowance is the identity verifier's alone. A Laura frame
    # whose Product Truth is UNKNOWN (its product unverified) does not count.
    laura_ok = any(e.get("laura") and e.get("source") == "generated"
                   and (e.get("candidate") or {}).get("technical_status") in ("PASS", "UNKNOWN")
                   and "product_truth" not in ((e.get("candidate") or {}).get("unknown") or [])
                   for e in roles)
    if not laura_ok:
        set_check = {"ok": False, "problems": list(set_check["problems"]) + [
            {"kind": "laura_lifestyle_missing",
             "why": "D-OWNER-LAURA-MANDATORY: an accepted Laura lifestyle frame is required"}]}
    consistency = CG.campaign_consistency(chosen) if chosen else CG._c(
        CG.NA, "no generated images yet")
    # F-226 (W4-C08): two Laura frames that are one photograph are copy-paste sameness, not a
    # real person photographed on different days. The owner still sees the card; the gallery
    # cannot be approved for publication while the blocker stands.
    from . import naturalism

    sameness = naturalism.sameness_only(chosen) if chosen else {"status": "PASS",
                                                                "findings": []}
    blockers |= set(naturalism.publication_blockers(sameness))
    if consistency.get("blocker"):
        blockers.add(consistency["blocker"])      # I-V2-UNJUDGED-PAIRS
    return {"listing": listing, "category": plan["category"], "roles": roles,
            "image_count": plan["image_count"],
            "campaign_standard": standard,
            "set_check": {"ok": set_check["ok"], "problems": set_check["problems"]},
            "campaign_consistency": consistency,
            "naturalism": sameness,
            "ruling_conflicts": plan.get("ruling_conflicts") or [],
            "publication_blockers": sorted(blockers),
            "gallery_ready": all(e["status"].startswith(("disclosed", "publishable"))
                                 for e in roles) and bool(set_check["ok"])
                             and consistency["status"] in (CG.PASS, CG.NA) and not ambiguous
                             and standard["ok"] and laura_ok,
            "laura_lifestyle_ok": laura_ok,
            "basis": "visual.shot_plans.campaign_plan + campaign_standard + candidate_gates + "
                     "eligibility.check_set"}


# ---- Command Center ---------------------------------------------------------------------

MAX_FRAMES_PER_LISTING = 300


def _frame_view(c) -> dict:
    """One candidate frame for the owner's Images page: thumbnail route, verdict, codes."""
    from ..creative import failure_codes as FC

    checks = c.checks if isinstance(c.checks, dict) else {}
    pt = checks.get("product_truth") if isinstance(checks.get("product_truth"), dict) else {}
    fid = pt.get("fidelity") if isinstance(pt.get("fidelity"), dict) else {}
    codes = {x for x in (fid.get("codes") or []) if isinstance(x, str)}
    codes |= {x for x in (c.failure_categories or []) if isinstance(x, str)}
    failed = sorted({k.get("check") for k in (fid.get("checks") or [])
                     if isinstance(k, dict) and k.get("status") == "FAIL"
                     and isinstance(k.get("check"), str)})
    return {"candidate_id": c.id, "run_key": c.run_key, "role": c.role, "stage": c.stage,
            "attempt": c.attempt, "method": c.method,
            "technical_status": c.technical_status, "outcome": c.outcome,
            "codes": sorted(k if k in FC.ALL_CODES else k for k in codes),
            "failed_checks": failed, "width": c.width, "height": c.height,
            "image_url": f"/api/cc/images/candidates/{c.id}/image",
            "created_at": c.created_at.isoformat() if c.created_at else None}


def status_board(db) -> dict:
    """The owner's Images page: every Launch-0 listing AND every listing that has image runs
    or candidates (IMAGES-DIALIN: production runs for products outside LAUNCH0_SLUGS were
    invisible), each with its latest run, all of its runs and every candidate frame."""
    from sqlalchemy import select

    from ..products import launch0
    from .image_records import ImageCandidate, ImageProductionRun, ensure_tables

    ensure_tables(db)
    out = []
    with db.session() as s:
        runs = list(s.scalars(select(ImageProductionRun)
                              .order_by(ImageProductionRun.updated_at.desc(),
                                        ImageProductionRun.id.desc())))
        cands = list(s.scalars(select(ImageCandidate).order_by(ImageCandidate.id.desc())))
        by_listing: dict[str, list] = {}
        for r in runs:
            by_listing.setdefault(r.listing or r.slug, []).append(r)
        frames_by_run: dict[str, list] = {}
        cand_listing: dict[str, str] = {}
        for c in cands:
            frames_by_run.setdefault(c.run_key or "", []).append(c)
            cand_listing.setdefault(c.run_key or "", c.listing or c.slug)
        listings = list(launch0.LAUNCH0_SLUGS)
        for name in list(by_listing) + list(cand_listing.values()):
            if name and name not in listings:
                listings.append(name)
        known = {r.run_key for r in runs}
        for listing in listings:
            rs = by_listing.get(listing, [])
            run_views = []
            shown = 0
            for r in rs:
                v = _run_view(r)
                fr = frames_by_run.get(r.run_key, [])[:max(0, MAX_FRAMES_PER_LISTING - shown)]
                shown += len(fr)
                v["frames"] = [_frame_view(c) for c in fr]
                run_views.append(v)
            # candidates whose run key has no run row (owner-submitted `<run>#owner` sets, or
            # a run row since removed): shown, never hidden
            for key, l in cand_listing.items():
                if l != listing or key in known:
                    continue
                fr = frames_by_run.get(key, [])[:max(0, MAX_FRAMES_PER_LISTING - shown)]
                shown += len(fr)
                run_views.append({"run_key": key or None, "listing": listing,
                                  "state": "owner_submitted" if key.endswith("#owner")
                                  else "no_run_record",
                                  "status": "owner_submitted" if key.endswith("#owner")
                                  else "no_run_record", "frames": [_frame_view(c) for c in fr]})
            if rs:
                head = _run_view(rs[0])
            else:
                head = {"listing": listing, "state": "awaiting_certified_pattern",
                        "status": "awaiting_certified_pattern",
                        "why": "no certified release has triggered image production yet"}
            head["runs"] = run_views
            head["frame_count"] = sum(len(v["frames"]) for v in run_views)
            head["slug"] = head.get("slug") or (rs[0].slug if rs else listing)
            out.append(head)
    return {"products": out, "states": list(STATES),
            "learning": learning_summary(db)}


def notification_candidates(db) -> list[dict]:
    """Owner notifications, only for ready_for_owner_review or blocked after attempts."""
    from sqlalchemy import select

    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    out = []
    with db.session() as s:
        rows = list(s.scalars(select(ImageProductionRun).where(
            ImageProductionRun.status.in_(NOTIFY_STATES))))
    for r in rows:
        if r.status == "blocked" and not r.attempts_exhausted:
            if "held for owner review" in (r.blocked_reason or ""):
                # W-VISNEXT2: stage A needs the owner's identity review; that is a decision
                # only the owner can make, so it is notified (once per epoch).
                ep = int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0)
                out.append({
                    "dedupe_key": f"image_identity_review:{r.run_key}:e{ep}",
                    "severity": "normal", "category": "decision",
                    "title": f"Laura identity anchor needs your review: {r.listing}"[:300],
                    "body": (f"{r.blocked_reason}. Confirming lets the anchor be used as "
                             f"identity context; it never makes any check PASS.")[:1000],
                    "consequence": "Laura frames for this listing wait until you review",
                    "evidence": [f"image_production_runs:{r.id}"],
                    "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
            continue
        ready = r.status == "ready_for_owner_review"
        card = dict(r.card or {})
        if not card.get("experiment"):
            from . import experiment as XP

            if XP.is_experiment(db, r.slug, r.version):
                # stopped before the card stage (e.g. at the fidelity gate): still stamped
                reg = (XP._opened(db, r.slug, r.version) or [{}])[-1]
                card = {**card, "experiment": True, "label": XP.LABEL,
                        "certification": reg.get("certification") or {}}
        if card.get("experiment"):
            # W4-WRAPTEST: the experiment's card, stamped; it asks for a look, never for
            # publication.
            out.append({
                "dedupe_key": f"image_gallery:{r.run_key}:{r.status}:experiment",
                "severity": "normal", "category": "decision",
                "title": (f"{card.get('label')}: gallery "
                          f"{'ready for your look' if ready else 'stopped'}: {r.listing}")[:300],
                "body": (f"{card.get('label')}. Visual approval only. Pattern certification: "
                         + ("granted (certified release)" if (card.get("certification") or {})
                            .get("granted") else
                            f"REFUSED ({'; '.join((card.get('certification') or {}).get('reasons') or [])[:300]})")
                         + ". "
                         f"Publication authorization: not available for an experiment. "
                         + ("" if ready else f"Stopped: {r.blocked_reason}"))[:1000],
                "consequence": ("nothing publishes: an experiment can never reach "
                                "store.publish, export or listing approval")[:1000],
                "evidence": [f"image_production_runs:{r.id}"],
                "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
            continue
        ep = int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0)
        out.append({
            # a restarted run that reaches the same state again is news again
            "dedupe_key": f"image_gallery:{r.run_key}:{r.status}" + (f":e{ep}" if ep else ""),
            "severity": "normal" if ready else "high",
            "category": "decision" if ready else "anomaly",
            "title": (f"Gallery ready for your review: {r.listing}" if ready else
                      f"Gallery blocked after permitted attempts: {r.listing}")[:300],
            "body": ("every generated role passed automated verification; publication "
                     "blockers: " + "; ".join(card.get("publication_blockers") or [])[:600]
                     if ready else f"cause: {r.blocked_reason}"[:1000]),
            "consequence": ("nothing publishes until you approve and every publication gate "
                            "passes" if ready else
                            "LIFESTYLE stays unfilled for this listing; recommended fix: " +
                            "; ".join(card.get("recommended_fix") or [])[:500]),
            "evidence": [f"image_production_runs:{r.id}"],
            "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
    return out


def approve(db, key: str, *, decided_by: str) -> dict:
    """The owner's approval. It never bypasses a gate: every candidate is re-checked now."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageCandidate

    run = get_run(db, key)
    if run is None:
        return {"approved": False, "why": "no such run"}
    from . import experiment as XP

    if (run.get("card") or {}).get("experiment"):
        XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing approval")
        raise XP.ExperimentRefused(f"{XP.LABEL}: an experiment run is never approved for "
                                   f"publication")
    XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing approval")
    XP.refuse_if_experiment_image(db, [((r.get("candidate") or {}).get("sha256"))
                                       for r in (run.get("card") or {}).get("roles") or []],
                                  action="listing approval")
    if run["state"] != "ready_for_owner_review":
        return {"approved": False, "why": f"run is {run['status']}, not ready_for_owner_review"}
    blockers = list(run["card"].get("publication_blockers") or [])
    with db.session() as s:
        for r in run["card"].get("roles") or []:
            c = r.get("candidate")
            if r.get("source") == "generated" and c:
                row = s.get(ImageCandidate, c["candidate_id"])
                if row is None or not row.publishable:
                    blockers.append(f"{r['role']}: candidate not publishable")
    decision = {"by": decided_by, "at": _now().isoformat(), "blockers": sorted(set(blockers))}
    with db.session() as s:
        r = _run(s, key)
        r.owner_decision = {**dict(r.owner_decision or {}), **decision, "approved_look": True,
                            "publication_requested": True}
        flag_modified(r, "owner_decision")
        if not blockers:
            r.status = "approved_for_publication"
    if blockers:
        return {"approved": False, "owner_look_recorded": True,
                "why": "publication gates still block; approval is recorded but cannot "
                       "override them", "blockers": decision["blockers"]}
    # W-VISNEXT (OWNERIMG E5): the approved frames go to ListingAsset only after a fresh
    # re-verification, and the set is re-certified by release_gates.listing_set.
    from .gallery_persist import persist_approved

    return {"approved": True, "state": "approved_for_publication",
            "listing_assets": persist_approved(db, key)}


def record_visual_approval(db, key: str, *, decided_by: str, approved: bool,
                           note: str = "") -> dict:
    """The owner's look at the images, recorded on its own (W-VISNEXT gallery card).

    It is not technical certification and not publication authorization: no gate reads it,
    the run's state does not change, and `approve` (the publication decision, step-up) still
    re-checks every gate."""
    from sqlalchemy.orm.attributes import flag_modified

    if not str(decided_by or "").strip():
        raise ValueError("a visual approval names who decided")
    run = get_run(db, key)
    if run is None:
        return {"recorded": False, "why": "no such run"}
    if run["state"] not in ("ready_for_owner_review", "blocked", "approved_for_publication"):
        return {"recorded": False, "why": f"run is {run['status']}: no gallery to look at yet"}
    entry = {"approved_look": bool(approved), "by": str(decided_by)[:120],
             "at": _now().isoformat(), "note": str(note or "")[:1000],
             "is_technical_certification": False, "is_publication_authorization": False}
    with db.session() as s:
        r = _run(s, key)
        od = dict(r.owner_decision or {})
        od["visual"] = entry
        od["visual_history"] = list(od.get("visual_history") or []) + [entry]
        r.owner_decision = od
        flag_modified(r, "owner_decision")
    return {"recorded": True, "visual_approval": entry, "state": run["state"]}


def _anchor_card(db, key: str, run: dict) -> dict | None:
    """Stage A's anchor as the card shows it: the image, its verdict and any owner review."""
    b = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    if not b:
        return None
    review = _anchor_review(db, b["sha256"]) if b.get("sha256") else None
    return {"image_url": f"/api/cc/images/candidates/{b['candidate_id']}/image",
            "sha256": b["sha256"], "technical_status": b["technical_status"],
            "unknown": b.get("unknown") or [], "failed": b.get("failed") or {},
            "review": review, "attempts": _attempts(db, key, IDENTITY_ANCHOR_ROLE),
            "label": "Laura identity anchor (intermediate reference, never a gallery frame)",
            "review_needed": bool(review and review.get("state") == "open")}


def gallery_card(db, key: str) -> dict | None:
    """The Command Center gallery approval card: every frame with its image, and three
    decisions kept apart (W-VISNEXT).

    * visual approval: the owner's look (`record_visual_approval`); never a gate input;
    * technical certification: every generated frame's technical verdict, the set check and
      campaign consistency, from the stored candidates;
    * publication authorization: available only when no publication blocker remains, and
      then only through `approve` (step-up), which re-checks every gate."""
    run = get_run(db, key)
    if run is None:
        return None
    card = dict(run.get("card") or {})
    roles = card.get("roles")
    if roles is None:   # no card yet (blocked earlier): show what candidates exist
        try:
            roles = readiness(db, run["listing"], run_key_=key)["roles"]
        except Exception:  # noqa: BLE001 - no plan: no roles to show
            roles = []
    frames, tech = [], []
    for r in roles or []:
        c = r.get("candidate") or {}
        img = (f"/api/cc/images/candidates/{c['candidate_id']}/image"
               if c.get("candidate_id") and c.get("sha256") else None)
        frames.append({"position": r.get("position"), "role": r.get("role"),
                       "job": r.get("job"), "source": r.get("source"),
                       "status": r.get("status"), "laura": r.get("laura"),
                       "image_url": img, "sha256": c.get("sha256"),
                       "technical_status": c.get("technical_status"),
                       "failed": c.get("failed") or {}, "unknown": c.get("unknown") or [],
                       "fidelity": c.get("fidelity") or {},
                       "label": "AI-generated concept image, never a photograph"
                       if img else None})
        if r.get("source") == "generated" and c:
            tech.append(c.get("technical_status") or "UNKNOWN")
    blockers = sorted(set(card.get("publication_blockers") or []))
    tech_status = CG.worst(*tech) if tech else CG.UNKNOWN
    set_ok = (card.get("set_check") or {}).get("ok")
    od = dict(run.get("owner_decision") or {})
    visual = od.get("visual")
    experiment = bool(card.get("experiment"))
    pub_available = (run["state"] == "ready_for_owner_review" and not blockers and not
                     experiment and tech_status == CG.PASS and bool(set_ok))
    return {
        "run_key": key, "listing": run["listing"], "slug": run["slug"],
        "version": run["version"], "release": run["release"], "state": run["state"],
        "status": run["status"], "experiment": experiment, "label": card.get("label"),
        "frames": frames, "spent_cad": run["spent_cad"],
        "generation_calls": run["generation_calls"], "restarts": run.get("restarts", 0),
        "restartable": restartable(db, key) if run["state"] == "blocked" else
        {"restartable": False, "why": f"run is {run['status']}"},
        "outfit_id": run.get("outfit_id"),
        "identity_anchor": _anchor_card(db, key, run),
        "decisions": {
            "visual_approval": {
                "state": ("approved" if visual and visual.get("approved_look") else
                          "rejected" if visual else "not_recorded"),
                "record": visual, "affects_gates": False,
                "what": "your look at these images only"},
            "technical_certification": {
                "state": tech_status, "set_check": card.get("set_check"),
                "campaign_consistency": card.get("campaign_consistency"),
                "certification": card.get("certification"),
                "what": "automated verification of every generated frame; UNKNOWN is never "
                        "PASS and your approval cannot change it"},
            "publication_authorization": {
                "state": ("approved" if run["state"] == "approved_for_publication" else
                          "available" if pub_available else "not_available"),
                "blockers": blockers,
                "requires": "step-up; every gate is re-checked at the moment you approve",
                "what": "whether these frames may go to the listing"}},
        "recommended_fix": card.get("recommended_fix") or []}

