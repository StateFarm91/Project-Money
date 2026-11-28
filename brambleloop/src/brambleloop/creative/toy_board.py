"""AMIGURUMI-JUDGING: the concept board a stuffed-toy concept is judged on.

The radar judge (`creative.intake.judge_radar_waiting`) asks a vision model whether a concept
reads at mobile-grid size and how its craft reads. It needs a picture. For flat and round
pieces `creative.board.make_board` draws one from the prototype's digital twin. A toy has no
prototype geometry (`'toy' has no finished size on file`), and `disclosed_render` draws flat and
round pieces only. So every amigurumi concept waited on `board_image` forever, though the animal
engine (`creative.animals`, ENG-AMIGURUMI-BREADTH) can draft it. The engine-demand list leads
with amigurumi.

This module makes that board, in this order, and stops at the first step that fails:

1. **The engine's own draft, first, for CA$0.** The concept is drafted exactly as `cir.draft`
   will draft it: the same job inputs `radar.score` offers (`draft_inputs`), the same route
   (`fallback_constructions.plan`), the same builder (`animals.build`). The draft must compile.
   A concept the animal engine will not draft gets no render, so no money is spent on a toy
   nobody can engineer.
2. **The child-safety preconditions, before any spend.** Nothing about the toy gate changes:
   certification still withholds every stuffed toy for its physical sample and the child-safety
   physical evidence. Here, before paying for a picture, the draft must also show:
   - every crocheted-in piece clears the small-parts cylinder (`small_parts.blocking`);
   - the face is embroidered with yarn only (the body note says so);
   - nothing in the materials is a safety eye, button, bead or other hard part;
   - the premise names nothing the engine refuses (`animals.premise_refusal`);
   - the age-suitability and embroidered-features statements the pattern will print exist
     (`child_safety.STATEMENTS`).
3. **One FLUX render, prompted from the draft.** The prompt is built from the compiled CIR
   only: the animal, the pieces and how many of each, the two colours, the yarn weight and the
   embroidered face. It forbids safety eyes, buttons, accessories, text and any other maker's
   design. It goes through `gateway.images.generate`, so the owner's `flux-3-image:generation`
   activation (D-OWNER-APPROVE-ALL), the provider's daily and monthly ceilings, the per-gallery
   limit and the code's image caps all apply, inside the budget lock, before any network I/O.
   The gallery is `concept-board:<slug>`. This module also has its own lower limits:
   `MAX_RENDERS_PER_RUN` and `MAX_RENDERS_PER_DAY`, so concept boards never take the day's
   image budget from listing galleries.
4. **Paid once.** Before the provider is asked, a `creative.toy_render` row records that a
   render was requested (written under the budget lock). After that:
   - a later run finds the filed board and judges it;
   - a refusal *before* anything was sent (no activation, a ceiling, no key) is recorded as
     `declined`, and a later run may ask again;
   - a 4xx on the submit, before the provider issued a task id (a rejected key, a refused
     request: `images._post` marks it `never_accepted_status`), was never accepted and never
     billed. It is recorded as `provider_refused`: it still counts toward the day's cap, the
     owner gate still counts it, and the concept may be asked again on a later UTC day only
     (TOY-BOARD). Before that it was written `paid_unfiled` and the toy was held forever;
   - anything after the provider may have taken the work (a failure after acceptance, a
     timeout, a crash between request and record) is never bought again by the system. The
     concept is held with that reason.
5. **Disclosed, and never a listing image.** The board is filed as a `creative.concept_board`
   row of kind `ai_concept_render`. Its disclosure says it is an AI concept render prompted
   from the drafted CIR: not a photograph, not the made toy, and not for any listing. It is
   never written to `listing_asset` frames. The judgement is bound to its bytes (CB2-D01), as
   for every other board.

The pattern itself is never derived from the picture. The CIR exists before the render and
the render is prompted from it, never the other way round.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time, timezone

ACTION = "creative.toy_render"
REQUESTED, FILED, DECLINED, PAID_UNFILED = "requested", "filed", "declined", "paid_unfiled"
# TOY-BOARD: the provider refused the submit with a 4xx before it issued a task id (a rejected
# key, a malformed or refused request): never accepted, never billed. Not "may have been paid
# for". It still counts toward MAX_RENDERS_PER_DAY, and the concept may be asked again on a
# later UTC day only, so a standing refusal costs at most one request per concept per day.
PROVIDER_REFUSED = "provider_refused"
KIND = "ai_concept_render"
SOURCE = "toy_render"
PROVIDER = "flux-3-image"
SIZE = "1024x1024"           # the 1k tier: the cheapest render, and plenty for a grid tile
AGENT = "creative"
PURPOSE = "creative.toy_concept_board"
PROMPT_VERSION = "toy-board/1"
# Below every gate ceiling, so concept boards never crowd out listing galleries. A gallery of
# 7 listing frames is ~16 images; four toy boards a day is a quarter of one gallery.
MAX_RENDERS_PER_RUN = 2
MAX_RENDERS_PER_DAY = 4

# Hard parts a child's toy built by this engine never has. A material naming one stops the
# render (and the engine never adds one; this is the check that it did not).
_HARD_PARTS = ("safety eye", "safety-eye", "button", "bead", "bell", "wire", "pellet",
               "plastic eye", "glass eye", "pipe cleaner")


# TOY-BOARD: why `render_board` filed no board, as one fixed code (no free text), so the
# readback can count the re-judge's `board_render_failed` holds by cause.
WHY_CODES = ("not_approved", "route_not_animal", "engine_refused", "not_compiling",
             "child_safety", "flux_not_ready", "already_filed", "already_requested",
             "daily_cap", "refused_before_sending", "provider_refused",
             "provider_refused_today", "failed_after_paid", "other")


class ToyBoardRefused(ValueError):
    """No board for this concept, and why. Nothing was spent. `code` is one of WHY_CODES."""

    def __init__(self, message: str, code: str = "other"):
        super().__init__(message)
        self.code = code if code in WHY_CODES else "other"


def gallery_for(slug: str) -> str:
    return f"concept-board:{slug}"[:160]


# ---- 1. the engine's own draft ------------------------------------------------------------


def draft_inputs(db, slug: str, *, today: date | None = None) -> dict | None:
    """The `cir.draft` inputs `radar.score` would offer for an approved concept, or None.

    The same three parts, in the same order, as `runtime.pipeline.handle_radar_score`: the
    scored seed, the intake row's stored concept and brief (`radar.intake.gate_inputs`), and
    the seed's geometry and palette (`concept_geometry`)."""
    from ..radar import intake as radar_intake
    from ..radar.opportunity import score_concept
    from ..runtime.pipeline import concept_geometry

    got = radar_intake.approved_concept(db, slug)
    if got is None:
        return None
    seed = got["seed"]
    payload = score_concept(seed, today or date.today()).to_dict()
    payload.update(radar_intake.gate_inputs(db, slug, {}))
    payload.update(concept_geometry(seed))
    payload["_seed"] = seed
    return payload


def engine_draft(db, slug: str, *, today: date | None = None):
    """(cir, route) as `cir.draft` will make them on the animal engine, or ToyBoardRefused."""
    from ..cir.compiler import compile_cir
    from ..runtime.pipeline import Concept
    from . import animals
    from . import fallback_constructions as FC

    i = draft_inputs(db, slug, today=today)
    if i is None:
        raise ToyBoardRefused("not an approved research concept", "not_approved")
    seed = i.pop("_seed")
    concept = Concept(slug=i["slug"], title=i["title"], category=i["category"],
                      stitch_repeat=[(s, n) for s, n in i["stitch_repeat"]],
                      width_stitches=i["width_stitches"], rows=i["rows"], colors=i["colors"],
                      season=i.get("season"), risk_class=i.get("risk_class", "A"))
    route = FC.plan(category=concept.category, title=concept.title,
                    is_bundle=bool(seed.is_bundle), slug=concept.slug,
                    rationale=seed.rationale or "")
    if route["family"] != FC.AMIGURUMI_ANIMAL:
        raise ToyBoardRefused(f"the draft route is {route['family']!r}, not the animal engine: "
                              f"{route.get('why') or ''}"[:240], "route_not_animal")
    try:
        cir = animals.build(concept)
    except ValueError as exc:
        raise ToyBoardRefused(f"the animal engine will not draft it: {exc}"[:240],
                              "engine_refused") from None
    result = compile_cir(cir)
    if not result.ok:
        codes = sorted({f.code for f in result.findings if f.is_error})
        raise ToyBoardRefused(f"the engine's draft does not compile: {codes}"[:240],
                              "not_compiling")
    return cir, route, i


def toy_concept(db, slug: str) -> bool:
    """Whether this approved concept is a stuffed toy whose draft route is the animal engine.
    CA$0 and no draft: the route only. `render_board` then drafts and checks it."""
    from . import fallback_constructions as FC

    from ..radar import intake as radar_intake

    got = radar_intake.approved_concept(db, slug)
    if got is None:
        return False
    seed = got["seed"]
    try:
        route = FC.plan(category=seed.category, title=seed.title,
                        is_bundle=bool(seed.is_bundle), slug=slug,
                        rationale=seed.rationale or "")
    except Exception:  # noqa: BLE001 - an unroutable title is not a toy this engine makes
        return False
    return route["family"] == FC.AMIGURUMI_ANIMAL


# ---- 2. the child-safety preconditions ------------------------------------------------------


def safety_preconditions(cir, *, premise: str = "") -> list[str]:
    """What stops a render of this toy before any spend: [] when every precondition holds."""
    from ..gates import child_safety as CS
    from ..gates import small_parts
    from . import animals

    problems = [f"small parts: {b}" for b in small_parts.blocking(cir)]
    body = next((c for c in cir.components if c.name == "body"), None)
    if body is None or "Embroider the face with yarn only" not in (body.note or ""):
        problems.append("the face is not stated as embroidered with yarn only")
    for m in cir.materials:
        name = str(m.name or "").lower()
        hit = next((h for h in _HARD_PARTS if h in name), None)
        if hit:
            problems.append(f"the materials name a hard part ({hit!r})")
    word = animals.premise_refusal(premise)
    if word:
        problems.append(f"the premise names {word!r}, which the engine does not build")
    for key in ("age_suitability", "features"):
        if key not in CS.STATEMENTS:
            problems.append(f"the child-safety statement {key!r} is missing")
    return problems


# ---- 3. the prompt, from the CIR ------------------------------------------------------------


def _colour_word(hex_value: str) -> str:
    """A plain colour name for a hex value (hue, lightness): a prompt word, not a claim."""
    import colorsys

    h = str(hex_value or "").lstrip("#")
    try:
        r, g, b = (int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))
    except (ValueError, IndexError):
        return "natural"
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.15:
        return ("cream" if light > 0.85 else "light grey" if light > 0.6 else
                "grey" if light > 0.3 else "charcoal")
    names = ((0.04, "red"), (0.09, "rust"), (0.14, "mustard"), (0.20, "olive"),
             (0.45, "green"), (0.55, "teal"), (0.70, "blue"), (0.80, "purple"),
             (0.95, "rose"), (1.01, "red"))
    name = next(n for limit, n in names if hue < limit)
    shade = "pale " if light > 0.75 else "deep " if light < 0.3 else "soft "
    return shade + name


def prompt_for(cir) -> str:
    """The render prompt, from the compiled CIR only. Deterministic for one CIR."""
    from . import animals

    kind = animals.route(cir.title)["kind"]
    parts = [c for c in cir.components if c.name != "body"]
    pieces = ", ".join(f"{c.make} {c.name}{'s' if c.make > 1 else ''}" for c in parts)
    colours = list(dict.fromkeys(cir.colors.values()))
    words = [_colour_word(v) for v in colours]
    palette = words[0] if len(words) == 1 else f"{words[0]} with {words[1]} accents"
    body = cir.components[0]
    sleepy = "sleepy" in (body.note or "")
    eyes = ("closed sleepy eyes embroidered as curved lines of yarn" if sleepy
            else "small eyes embroidered with a few straight stitches of dark yarn")
    weight = cir.gauge.yarn_weight
    return (
        f"Concept render of one handmade crocheted {kind} amigurumi toy, worked in "
        f"{weight}-weight yarn in tight single crochet. Head and body are one rounded piece; "
        f"its {pieces} are crocheted onto the body. Colours: {palette}. The face has {eyes}, "
        f"and an embroidered nose. No plastic safety eyes, no buttons, no beads, no "
        f"accessories, no clothing, no text or logo. Plain light background, soft daylight, "
        f"the whole toy in view, a square product thumbnail.")


def fingerprint(cir, prompt: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}|{cir.fingerprint}|{prompt}".encode()).hexdigest()


# ---- 4. paid once ---------------------------------------------------------------------------


def _rows(session, slug: str):
    from sqlalchemy import select

    from ..core.models import AuditLog

    return list(session.scalars(select(AuditLog).where(
        AuditLog.action == ACTION, AuditLog.artifact == slug).order_by(AuditLog.id)))


def state(db, slug: str) -> dict:
    """The newest render record for `slug`: {} when no render was ever asked for."""
    with db.session() as s:
        rows = _rows(s, slug)
        return dict(rows[-1].detail or {}) if rows else {}


def _requested_today(session, now: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import AuditLog

    day0 = datetime.combine(now.date(), time(0), tzinfo=timezone.utc)
    rows = list(session.scalars(select(AuditLog).where(AuditLog.action == ACTION,
                                                       AuditLog.at >= day0)))
    # A request refused before anything was sent cost nothing and does not use the day's cap.
    requested = sum(1 for r in rows if (r.detail or {}).get("state") == REQUESTED)
    declined = sum(1 for r in rows if (r.detail or {}).get("state") == DECLINED)
    return max(0, requested - declined)


def never_accepted_status(exc: BaseException | None) -> int | None:
    """The provider's 4xx when `exc`'s chain says the submit was refused before a task id
    (`gateway.images._post` sets `never_accepted_status`); None otherwise. The same rule as
    `visual.image_production.never_accepted_status` (REDRIVE-REFUSAL), kept here so the board
    path does not import the gallery runner."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        st = getattr(exc, "never_accepted_status", None)
        if isinstance(st, int) and not isinstance(st, bool) and 400 <= st < 500:
            return st
        exc = exc.__cause__ or exc.__context__
    return None


# A PAID_UNFILED row written before TOY-BOARD for a submit the provider refused: the message
# `gateway.images._post` raises for a 4xx on the submit ("<provider> <status>: ..."). A poll
# failure or a terminal status after acceptance reads differently ("... poll 4xx",
# "... returned <status>"), so it never matches.
_LEGACY_SUBMIT_REFUSAL = re.compile(
    rf"^(?:ImagesRefused|QuotaUnavailable): {re.escape(PROVIDER)} (4\d\d): ")


def _billed(session, slug: str) -> bool:
    """Whether the ledger holds an image cost row for this concept's board (any billing)."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    for d in session.scalars(select(CostEntry.detail).where(CostEntry.agent == AGENT,
                                                            CostEntry.kind == "image")):
        d = d or {}
        if d.get("slug") == slug and d.get("what") == "toy concept board":
            return True
    return False


def _effective(session, slug: str, last: dict) -> dict:
    """The newest record, with a legacy PAID_UNFILED that was a refused submit (its message
    says so AND the ledger has no cost row for this board) read as PROVIDER_REFUSED. Anything
    else that may have been accepted stays never-bought-again."""
    if last.get("state") != PAID_UNFILED:
        return last
    hit = _LEGACY_SUBMIT_REFUSAL.match(str(last.get("why") or ""))
    if hit is None or _billed(session, slug):
        return last
    return {**last, "state": PROVIDER_REFUSED, "provider_status": int(hit.group(1)),
            "legacy": True}


def _claim(db, slug: str, fp: str, job_id, now: datetime) -> tuple[bool, str, str]:
    """Write the REQUESTED row under the budget lock, or say why not. Check and write are one
    decision, so two workers cannot both buy the same board."""
    from ..core.models import AuditLog
    from ..gateway import providers as gw

    with gw.budget_lock(db) as s:
        rows = _rows(s, slug)
        last = _effective(s, slug, dict(rows[-1].detail or {}) if rows else {})
        st = last.get("state")
        if st == PROVIDER_REFUSED and rows and not last.get("legacy"):
            try:
                at = datetime.fromisoformat(str(last.get("at")))
            except ValueError:
                at = rows[-1].at
            at = at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at
            if at is None or at.date() >= now.date():
                return False, (f"the provider refused this board's request today (HTTP "
                               f"{last.get('provider_status')}, nothing billed); asked again "
                               f"on a later UTC day"), "provider_refused_today"
        if st == FILED:
            return False, "a board was already rendered and filed for this concept", \
                "already_filed"
        if st in (REQUESTED, PAID_UNFILED):
            return False, (f"a render was already requested for this concept (job "
                           f"{last.get('job_id')}) and may have been paid for; it is never "
                           f"bought again by the system"), "already_requested"
        if _requested_today(s, now) >= MAX_RENDERS_PER_DAY:
            return False, (f"{MAX_RENDERS_PER_DAY} toy concept renders already requested today "
                           f"(MAX_RENDERS_PER_DAY)"), "daily_cap"
        s.add(AuditLog(actor=AGENT, action=ACTION, artifact=slug,
                       detail={"state": REQUESTED, "fingerprint": fp, "job_id": job_id,
                               "provider": PROVIDER, "gallery": gallery_for(slug),
                               "at": now.isoformat()}))
    return True, "", ""


def _record(db, slug: str, detail: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=AGENT, action=ACTION, artifact=slug, detail=detail))


def _sha(value) -> str:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(c in "0123456789abcdef" for c in text) else ""


def render_board(db, slug: str, *, job_id=None, today: date | None = None,
                 now: datetime | None = None, premise: str = "") -> dict:
    """Make and file the toy's concept board, or say why not.

    {"board": image_ref, "why": "", "paid": bool} on success; {"board": "", "why": ...,
    "paid": False|True, "retry": bool} otherwise. `retry` says a later run may ask again."""
    from pathlib import Path

    from ..core.artifacts import ArtifactStore
    from ..core.models import AuditLog
    from ..core.workspace import work_dir
    from ..gateway import flux_provider
    from ..gateway import images
    from ..gateway import paid_provider_gate as gate
    from ..gateway.providers import BudgetExceeded
    from ..products.moment_candidates import BOARD_ACTION

    now = now or datetime.now(timezone.utc)
    try:
        cir, route, inputs = engine_draft(db, slug, today=today)
    except ToyBoardRefused as exc:
        return {"board": "", "why": f"no toy board: {exc}"[:240], "why_code": exc.code,
                "paid": False, "retry": False}
    problems = safety_preconditions(cir, premise=premise or str(inputs.get("premise") or ""))
    if problems:
        return {"board": "", "why": ("child-safety precondition: " + "; ".join(problems))[:240],
                "why_code": "child_safety", "paid": False, "retry": False}
    ready = flux_provider.readiness(db)
    if ready["state"] != flux_provider.READY:
        return {"board": "", "why": f"FLUX not ready ({ready['code']}); nothing was spent",
                "why_code": "flux_not_ready", "paid": False, "retry": True}
    prompt = prompt_for(cir)
    fp = fingerprint(cir, prompt)
    claimed, why, code = _claim(db, slug, fp, job_id, now)
    if not claimed:
        return {"board": "", "why": why, "why_code": code, "paid": False, "retry": False}
    out = {"asked": True}
    base = {"fingerprint": fp, "job_id": job_id, "provider": PROVIDER,
            "gallery": gallery_for(slug)}
    try:
        with work_dir(None, prefix="generated-") as wd, gate.gallery_scope(gallery_for(slug)):
            got = images.generate(prompt, provider_key=PROVIDER, size=SIZE, work_dir=str(wd),
                                  db=db, agent=AGENT, purpose=PURPOSE, job_id=job_id,
                                  prompt_version=PROMPT_VERSION, product=slug,
                                  spend_detail={"what": "toy concept board", "slug": slug})
            raw = Path(str(got.get("path") or "")).read_bytes()
    except (images.ImagesGateRefused, images.ImagesNotConfigured, BudgetExceeded) as exc:
        # Refused before any request left: nothing was billed, so a later run may ask again.
        _record(db, slug, {**base, "state": DECLINED, "why": str(exc)[:240]})
        out["asked"] = False      # nothing was sent: the per-run render cap is not used
        return {**out, "board": "", "why": f"render refused before sending: {exc}"[:240],
                "why_code": "refused_before_sending", "paid": False, "retry": True}
    except Exception as exc:  # noqa: BLE001 - possibly billed: never bought again
        status = never_accepted_status(exc)
        if status is not None:
            # TOY-BOARD: a 4xx on the submit, before a task id: the provider never accepted
            # the work and billed nothing (images.generate released the claim unbilled; the
            # owner gate still counts it). Recorded as such, not as "may have been paid for",
            # so a rejected key or a refused request does not hold the concept forever.
            _record(db, slug, {**base, "state": PROVIDER_REFUSED, "provider_status": status,
                               "at": now.isoformat(),
                               "why": f"{type(exc).__name__}: {str(exc)[:200]}"})
            return {**out, "board": "", "why": (f"the provider refused the render request "
                                                f"before accepting it (HTTP {status}); "
                                                f"nothing was billed")[:240],
                    "why_code": "provider_refused", "paid": False, "retry": True}
        _record(db, slug, {**base, "state": PAID_UNFILED,
                           "why": f"{type(exc).__name__}: {str(exc)[:200]}"})
        return {**out, "board": "", "why": (f"the render failed after it may have been paid for "
                                     f"({type(exc).__name__}); it is not bought again"),
                "why_code": "failed_after_paid", "paid": True, "retry": False}
    stored = ArtifactStore().put(f"board/{slug}-toy.png", raw, "image/png", db=db,
                                 keep="toy concept board for the radar vision judge")
    sha = _sha(stored.sha256)
    disclosure = ("an AI concept render (FLUX), prompted from the drafted CIR's animal, "
                  "pieces, colours and embroidered face; not a photograph, not the made toy, "
                  "and never used in a listing")
    record = {"slug": slug, "kind": KIND, "image": {"sha256": sha},
              "image_ref": f"sha256:{sha}", "disclosure": disclosure,
              "source": "radar.board", "board_source": SOURCE,
              "cir_fingerprint": cir.fingerprint, "route": route["family"],
              "prompt_version": PROMPT_VERSION, "prompt_sha256":
                  hashlib.sha256(prompt.encode()).hexdigest(),
              "cost_entry_id": got.get("cost_entry_id"), "replayed": bool(got.get("replayed"))}
    with db.session() as s:
        s.add(AuditLog(actor=AGENT, action=BOARD_ACTION, artifact=slug, detail=record))
        s.add(AuditLog(actor=AGENT, action=ACTION, artifact=slug,
                       detail={**base, "state": FILED, "board_sha256": sha,
                               "cost_entry_id": got.get("cost_entry_id")}))
    return {**out, "board": record["image_ref"], "why": "", "paid": not got.get("replayed"),
            "retry": False}
