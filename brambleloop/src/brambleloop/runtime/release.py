"""The second half of the release chain: assets, pricing, listing, launch, support.

`pipeline.py` carries a concept as far as a Quality Release Certificate. This carries the
certified pattern the rest of the way to something that could actually be sold: the PDF and
charts a customer downloads, a price that survives Etsy's fees, a listing whose every claim
is checkable, a launch plan anchored on the buying window, and a support surface that can
answer from the released version without being able to change it.

The ordering is not cosmetic. Assets are rendered from the certified CIR, the listing's
claims are taken from the rendered assets, and the policy check runs on what was actually
written. Nothing downstream is allowed to assert something nothing upstream computed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import build_twin
from ..cir.writer import collapses_rows
from ..quality.physical import calibration_from_db
from ..commerce import launch as launch_mod
from ..commerce import pricing as pricing_mod
from ..commerce import pricing_intel as pricing_mod_intel
from ..commerce import search as search_mod
from ..commerce import seo as seo_mod
from ..commerce import thumbnail as thumb_mod
from ..core.artifacts import ArtifactStore
from ..core.models import PatternVersion, Product
from ..gates.policy import ListingDraft, check_listing
from ..core.models import ListingAsset
from ..gates.asset_truth import check_assets
from ..publish.charts import render_legend
from ..publish.listing_assets import build_frames, check_frame_plan
from ..products import launch0 as products_launch0
from ..publish.pdf import (
    TERMINOLOGIES, build_pattern_pdf, chart_image, childrens_statements, pattern_filename,
)
from ..radar.market import shopping_window
from ..radar.opportunity import POOL, _event
from .worker import JobContext, handlers

# The release chain's own version, stamped into every downstream idempotency key.
#
# Without it a pipeline upgrade cannot reach products that already shipped. Production proved
# this: fifteen products were certified before listing imagery, search coverage and the
# content ecosystem existed, and the next cycle silently collapsed every downstream job
# against keys like "assets:slug:1.0.0" that were already taken. The cycle reported success
# and produced nothing.
#
# "Build assets for slug@1.0.0 with chain v2" is genuinely different work from doing it with
# v1, so it gets a different key. Bump this whenever a stage after certification changes what
# it produces.
CHAIN_VERSION = "8"  # 8: hero kept out of the title-safe band (C-58), size-card labels (#60)

# How much of an owner action's opening clause identifies it, for adopting rows queued
# before `OwnerAction.requirement_key` existed. Long enough to be unambiguous, short enough
# that no action's derived figure reaches it. A test asserts the prefixes are distinct.
ADOPT_PREFIX = 40


def chain_key(stage: str, slug: str, version: str, release: str = "",
              token: str = "") -> str:
    """The idempotency key for one post-certification stage.

    Three things identify the work, and leaving any of them out has cost a delivery:

    - `slug` and `version` say which product. Alone they meant a code change could never
      reach a product that had already shipped, which is what CHAIN_VERSION fixed.
    - `release` says *what was certified*. Without it a re-engineered design re-certifies
      and then finds every downstream key taken, so production issued new certificates and
      kept serving the old listings.
    - `token` says which rebuild asked. A rebuild exists precisely for the case where the
      work already ran and its result is no longer right, so the trigger has to be part of
      the key or the rebuild cannot re-drive a single stage of the chain. It rides the whole
      chain in the job inputs, so every stage re-runs once for that rebuild and not once per
      cadence.
    """
    parts = [stage, slug, version]
    if release:
        parts.append(release[:12])
    if token:
        parts.append(token[:12])
    parts.append(f"c{CHAIN_VERSION}")
    return ":".join(parts)


CATEGORY_BANDS_CAD: dict[str, tuple[float, float]] = {
    "mosaic_blanket": (8.50, 14.00),
    "blanket": (8.50, 14.00),
    "graphghan": (7.50, 12.00),
    "baby": (6.00, 10.00),
    "seasonal_decor": (4.00, 9.00),
    "ornament": (4.00, 7.50),
    "basket": (4.50, 8.00),
    "runner": (5.00, 9.00),
    "flower": (4.00, 8.00),
    "pet": (4.00, 7.50),
}
DEFAULT_BAND = (4.50, 9.50)


def _load_cir(ctx: JobContext, slug: str, version: str) -> CIR:
    from sqlalchemy import select

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            raise ValueError(f"no product {slug!r}: assets cannot precede certification")
        pv = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        if pv is None or not pv.certified:
            raise ValueError(
                f"{slug}@{version} has no certified release; refusing to render customer "
                f"assets for a pattern that did not pass the gates")
        return CIR.from_dict(pv.cir_json)


def _content_hash_of(cir: CIR) -> str:
    """The content hash `gates.certificate.certify` names for this CIR (US text, F-078)."""
    from ..cir.writer import write_pattern
    from ..gates.certificate import _release_hash

    return _release_hash(cir, write_pattern(cir, compile_cir(cir), "US"))


def _load_examined_cir(ctx: JobContext, slug: str, version: str, *,
                       content_hash: str | None = None) -> tuple[CIR, str, bool]:
    """The CIR the chain examined for slug@version, certified or not, and its content hash.

    Candidates are the stored release (any certification state) and every CIR `gate.certify`
    was handed for slug@version. The content is the one the caller names (`content_hash`,
    what the tester was handed) or, absent that, the content the chain most recently
    examined for this release -- read from the append-only `gate.certified`/`gate.blocked`
    audit, falling back to the stored release's hash. A slug/version the chain never
    examined, or a named hash none of its content has, is refused: a sample of unknown text
    binds to nothing and is not recorded as if it did.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Job
    from .pipeline import CERTIFY_ACTIONS

    candidates: list[CIR] = []
    certified, stored_hash = False, ""
    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        if pv is not None and pv.cir_json:
            candidates.append(CIR.from_dict(pv.cir_json))
            certified, stored_hash = bool(pv.certified), pv.release_hash or ""
        for job in s.scalars(select(Job).where(Job.job_type == "gate.certify")
                             .order_by(desc(Job.id))):
            raw = (job.inputs or {}).get("cir")
            if (isinstance(raw, dict) and raw.get("slug") == slug
                    and raw.get("version") == version):
                try:
                    candidates.append(CIR.from_dict(raw))
                except Exception:  # noqa: BLE001 - an unparseable input is no candidate
                    continue
        examined = None
        if not content_hash:
            for row in s.scalars(select(AuditLog).where(
                    AuditLog.artifact == f"{slug}@{version}",
                    AuditLog.action.in_(CERTIFY_ACTIONS)).order_by(desc(AuditLog.id))):
                examined = (row.detail or {}).get("content_hash")
                if examined:
                    break
    if not candidates:
        raise ValueError(f"no release {slug}@{version} has been examined by the chain; a "
                         f"sample cannot be recorded against a pattern that does not exist")
    target = content_hash or examined or stored_hash
    if not target:
        raise ValueError(f"{slug}@{version} has no examined content hash; which text the "
                         f"tester worked is unknown, so the sample is not recorded")
    seen: set[str] = set()
    for cir in candidates:
        key = json.dumps(cir.to_dict(), sort_keys=True, default=str)
        if key in seen:      # the same CIR handed to gate.certify again hashes the same
            continue
        seen.add(key)
        h = _content_hash_of(cir)
        if h == target:
            return cir, h, certified and h == stored_hash
    raise ValueError(f"{slug}@{version}: content {target[:12]} is not content the chain "
                     f"examined for this release; the sample is refused rather than bound "
                     f"to a text nobody can produce")


def _released_on(ctx: JobContext, slug: str, version: str):
    """The date this release was created, so the PDF does not read the wall clock.

    `build_pattern_pdf` prints a release date, and left to itself it prints `date.today()`.
    That makes the rendered bytes a function of when somebody happened to render them -- and
    artifact bytes are not durable, so a purchased file is re-rendered on demand and the
    store's publish handler renders it again at upload time. A hash recorded here and a file
    downloaded next month would then differ for no reason connected to the pattern, which is
    exactly the property `assets.build` claims its hash proves.

    The release row already knows when it was made, so the document is pinned to that.
    """
    from sqlalchemy import select

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id,
            PatternVersion.version == version)) if product else None
        created = getattr(pv, "created_at", None)
        return created.date() if created else None


def _seed_for(slug: str):
    return next((s for s in POOL if slug.startswith(s.slug) or s.slug == slug), None)


UNKNOWN_PRODUCT = "UNKNOWN_PRODUCT"


def _product_record(slug: str, inputs: dict | None = None) -> dict | None:
    """What this product IS, read from its own record -- never a default (PT-01).

    A Launch-0 product answers from `products.launch0.listing_identity`: its kind, its Etsy
    category intent and its listing vocabulary, keyed exactly on the CIR slug. Anything else
    answers from its radar seed, or from a category the job was explicitly handed. None means
    nobody has said what this product is, and the caller refuses: this used to fall back to
    `mosaic_blanket`, which is how a basket was titled, tagged, priced and filed as a blanket.
    """
    identity = products_launch0.listing_identity(slug)
    if identity is not None:
        cand = products_launch0.candidate_for_cir(slug)
        return {"category": identity.etsy_category, "kind": identity.kind,
                "nouns": list(identity.nouns), "motifs": list(identity.qualifiers),
                "techniques": list(identity.techniques), "season": None,
                "launch0": slug in products_launch0.launch_scope_slugs(),
                "source": f"products.launch0:{cand.slug if cand else slug}"}
    seed = _seed_for(slug)
    if seed is not None:
        return {"category": seed.category, "kind": seed.category, "nouns": [],
                "motifs": _motifs_for(slug), "techniques": None, "season": seed.season,
                "launch0": False, "source": f"radar.pool:{seed.slug}"}
    category = (inputs or {}).get("category")
    if category:
        return {"category": str(category), "kind": str(category), "nouns": [],
                "motifs": _motifs_for(slug), "techniques": None, "season": None,
                "launch0": False, "source": "job inputs"}
    return None


@handlers.register("assets.build")
def handle_assets_build(ctx: JobContext) -> dict:
    """Render the customer PDF and charts from the certified CIR, and record their hashes.

    The hash is the point. A PDF is the only artefact the customer ever sees, so the system
    has to be able to prove that the file it is about to ship is the one that was certified
    and not a re-render that drifted.
    """
    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs["version"]
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))

    # Both terminologies, because both are sold.
    #
    # This rendered `pattern-us.pdf` alone while the listing title said "US and UK Terms", the
    # description said "US and UK terminology", the content FAQ said "the UK equivalent for
    # every stitch in the key" and a Pinterest pin said "US and UK terms". One file shipped.
    # That is a live customer-facing falsehood, and the honest end of it is to ship what is
    # claimed rather than to quietly narrow the claim -- a UK maker translating a US pattern
    # in their head is exactly the buyer this catalogue is for.
    #
    # It could only be done once UK localisation was correct, which it now is:
    # `cir.stitches.UK_TERMS` is the single terminology table, `cir.writer` delegates to it,
    # and `build_pattern_pdf` refuses a terminology whose stitches it cannot name truthfully.
    # The refusal is load-bearing here: a gap in the table stops this handler rather than
    # shipping a UK document that instructs the wrong stitch.
    released_on = _released_on(ctx, slug, version)
    from ..learn.service import pdf_help_links
    lesson_links = pdf_help_links(ctx.db, cir.to_dict())
    docs = {t: build_pattern_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                 lesson_links=lesson_links)
            for t in TERMINOLOGIES}
    doc = docs["US"]
    # Every file this handler stores is a derived artefact the provenance sentinel watches,
    # so the store is told which class each one is and refuses the write without lineage
    # (#171). The upstream fingerprints come from the stored release, not the CIR in hand.
    from ..ops import artefacts as provenance

    with ctx.db.session() as s:
        design = provenance.design_inputs(s, slug, version)
    lineage = _lineage(ctx)
    certificate_ref = f"certificate:{provenance.release_key(slug, version)}"
    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))
    pdfs = {t: store.put(f"{slug}/{version}/{pattern_filename(t)}", d.pdf_bytes,
                         "application/pdf", artefact_class="pdf", lineage=lineage)
            for t, d in docs.items()}
    pdf = pdfs["US"]

    # What is wrong with the document the customer receives, measured on the document. These
    # are recorded whether or not they block, because a finding nobody records is a finding
    # nobody acts on -- the same failure as a severity comparison that is always false.
    #
    # Per terminology, because the two documents are not the same document: the UK render had
    # its own defects -- a gauge line still in US terms, a special-stitch method telling a UK
    # maker to finish a post stitch as a double crochet -- and a US-only audit could not have
    # seen either.
    for terminology, rendered in sorted(docs.items()):
        if rendered.problems:
            ctx.audit("assets.deliverable_problems", artifact=f"{slug}@{version}",
                      detail={"terminology": terminology, "problems": rendered.problems})

    import io

    chart_png = io.BytesIO()
    # The chart the customer's document prints, not a second one.
    #
    # This stored `render_any_chart` at the default spec: the whole piece, which for a
    # seventy-round nesting basket is 1.21 mm per ring and 2.1 pt round numbers. So one
    # release produced two charts of the same product -- the legible one inside the PDF and
    # an illegible one with a URL on it. `publish.pdf.chart_image` chooses on the size a ring
    # or cell actually lands at on the page, and it is the one the buyer sees.
    chart_image(cir, twin).save(chart_png, format="PNG")
    chart = store.put(f"{slug}/{version}/chart.png", chart_png.getvalue(), "image/png",
                      artefact_class="chart", lineage=lineage)

    legend_png = io.BytesIO()
    render_legend(cir, twin).save(legend_png, format="PNG")
    legend = store.put(f"{slug}/{version}/legend.png", legend_png.getvalue(), "image/png",
                       artefact_class="chart", lineage=lineage)

    with ctx.db.session() as s:
        for terminology, stored in sorted(pdfs.items()):
            provenance.record_lineage(
                s, artefact_class="pdf",
                artefact_key=provenance.pdf_key(slug, version, terminology),
                product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
                lineage=lineage.for_file(stored.sha256).under(certificate_ref).validated(
                    "problems" if docs[terminology].problems else "passed"))
        for which, stored in (("chart", chart), ("legend", legend)):
            provenance.record_lineage(
                s, artefact_class="chart",
                artefact_key=provenance.chart_key(slug, version, which),
                product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
                lineage=lineage.for_file(stored.sha256).under(certificate_ref).validated(
                    "passed"))

    ctx.audit("assets.built", artifact=f"{slug}@{version}", detail={
        "pdf": pdf.to_dict(), "chart": chart.to_dict(), "legend": legend.to_dict(),
        # One hash per file the customer receives. `pdf` above is the US document and is kept
        # under its old key so nothing downstream has to change its mind about what that means;
        # `pdfs` is the complete set, and a reader that finds only one entry in it is looking
        # at a release that shipped one terminology.
        "pdfs": {t: stored.to_dict() for t, stored in sorted(pdfs.items())},
        "pages": doc.pages, "size_label": doc.size_label(),
        "storage_durable": pdf.durable,
    })
    if not pdf.durable:
        ctx.audit("assets.storage_not_durable", artifact=f"{slug}@{version}", detail={
            "reason": "no object storage is provisioned; artifact bytes do not survive a "
                      "container restart. Hashes are durable and assets re-render from the "
                      "certified CIR."})

    # Listing imagery is part of the release, not an afterthought bolted on before publish.
    # It is rendered from the same twin as the PDF, so no frame can assert something the
    # pattern does not produce, and then checked by Asset Truth like any other asset.
    from ..cir.writer import write_pattern

    siblings = _collection_siblings(slug)
    # #63: the creative brief is derived from the engineering evidence *before* the
    # conversion creative exists, so it constrains the frames rather than captioning them.
    from ..publish import brief as brief_mod

    creative_brief = brief_mod.brief_for_release(
        cir, twin, evidence_ref=f"chart:{chart.sha256}",
        deliverables=tuple(f"pdf:{t}" for t in sorted(pdfs)) + ("chart", "legend"))
    frames = build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                          difficulty=_difficulty(twin, cir), pages=doc.pages,
                          siblings=siblings)
    structural = check_frame_plan(frames)
    truth = check_assets([f.to_asset(slug) for f in frames], cir, twin)
    # A hero is judged at the size a shopper actually sees it, not in the editor.
    aspect = ((twin.width_cm / twin.height_cm)
              if twin.width_cm and twin.height_cm else None)
    hero = thumb_mod.evaluate_thumbnail(frames[0].image, text_pt_on_canvas=0.056 * 2000,
                                        canvas_px=2000, subject_aspect=aspect)
    # #201: a model-bearing frame whose identity cannot be verified does not ship. Today no
    # frame carries the model, so this is `not_applicable` and changes nothing -- which is
    # the point of wiring it now rather than on the day the first model frame is built, when
    # the temptation to let it through is at its highest.
    from ..visual import model_registry

    identity_gate = model_registry.gate_frames(ctx.db, [
        {"role": f.role, "has_model": bool(getattr(f, "has_model", False)),
         "image_ref": ""} for f in frames])

    blocking = (structural + [str(f) for f in truth if f.is_error] + hero.problems
                + list(identity_gate["blocking"]))

    # #63: CIR -> twin -> evidence -> brief -> creative -> independent asset truth -> gates,
    # walked in order. Creative that shows a motif, size or texture the truth does not
    # contain is refused here, and the product goes back to the brief.
    flow = brief_mod.walk(creative_brief, brief_mod.produced_by_frames(frames),
                          produced_by="publishing:listing_assets",
                          compared_by="gates.asset_truth", gates_ok=not blocking)
    if not flow["creative"]["ok"]:
        blocking.append("CREATIVE_INVENTED: the listing frames depict what the truth does "
                        f"not contain: {flow['creative']['invented']}"[:400])
    ctx.audit(brief_mod.FLOW_ACTION, artifact=f"{slug}@{version}",
              detail={k: flow[k] for k in ("steps", "reached", "blocked_at", "restart",
                                           "export_ready", "creative", "independence")}
              | {"brief": flow["brief"]})

    stored_frames = []
    frame_paths: dict[int, str] = {}
    for frame in frames:
        art = store.put(f"{slug}/{version}/frame-{frame.position}.png", frame.png(),
                        "image/png", artefact_class="visual_truth", lineage=lineage)
        stored_frames.append({"position": frame.position, "role": frame.role,
                              "asset_class": frame.asset_class.value,
                              "sha256": art.sha256})
        frame_paths[frame.position] = str(art.path)

    # #61 (C-69): independent visual review of every listing frame -- the finished-result
    # frame, the size card, the chart preview and the rest -- not only the hero. A model that
    # never sees the caption describes each frame and deterministic code compares that with
    # what the frame's role claims. It runs when the vision gate is open; otherwise every
    # frame is recorded UNREVIEWED, which the publish path reads as not passed. A frame the
    # review blocks stops the chain here.
    review = _review_frames(ctx, slug, version, frames, frame_paths,
                            shas={f["position"]: f["sha256"] for f in stored_frames})
    blocking.extend(review["blocking"])

    # #36: every listing image is stored with its provenance -- kind, physical or
    # simulated, AI-assisted or not, the pattern version it depicts and its colourway.
    from ..commerce import buyer_trust

    try:
        provenance_row = buyer_trust.record_gallery(
            ctx.db, slug=slug, version=version, job_id=ctx.job.id,
            records=buyer_trust.records_for_frames(
                stored_frames, slug=slug, version=version,
                colourway=", ".join(sorted(c for c in twin.colors_used if c))))
    except buyer_trust.TrustRefused as exc:
        provenance_row = None
        blocking.append(f"IMAGE_PROVENANCE_REFUSED: {exc}"[:400])

    # #68: every visual defect found here becomes a regression fixture (or, in a class that
    # already has one, a recorded fixture bug), and this product's fixtures are replayed.
    from ..publish import defects as defects_mod

    replayed = defects_mod.replay(ctx.db, blocking, slug=slug)
    captured = None
    if blocking:
        captured = defects_mod.capture(
            ctx.db, blocking, slug=slug, version=version, job_id=ctx.job.id,
            reproduces_with=(f"assets.build {slug}@{version} release "
                             f"{ctx.job.inputs.get('release', '') or '-'} chain "
                             f"{CHAIN_VERSION}; hero sha256 "
                             f"{stored_frames[0]['sha256'] if stored_frames else '-'}"))
    _persist_frames(ctx, slug, version, frames, stored_frames, blocking)
    # D-FB-7: the product's customer imagery when no qualified photograph exists -- the
    # disclosed deterministic render set, drawn from this certified CIR, verified from its
    # pixels and filed where the parity and eligibility readers find it.
    disclosed = _disclosed_render_set(ctx, cir, slug, version, store, lineage)

    ctx.audit("assets.listing_images_built" if not blocking else "assets.listing_images_blocked",
              artifact=f"{slug}@{version}",
              detail={"frames": len(frames), "blocking": blocking[:5],
                      "identity_gate": {k: identity_gate[k]
                                        for k in ("checked", "verdict") if k in identity_gate},
                      "hero_thumbnail": hero.to_dict(),
                      "evidence_flow": {"blocked_at": flow["blocked_at"],
                                        "export_ready": flow["export_ready"]},
                      "image_provenance": (provenance_row or {}).get("audit_id"),
                      "defect_fixtures": ({"first": captured["first"],
                                           "recurrences": captured["recurrences"]}
                                          if captured else None),
                      "fixture_replay": {"fixtures": replayed["fixtures"],
                                         "failed": replayed["failed"][:5]},
                      "disclosed_render": disclosed})
    if blocking:
        # A listing whose imagery misrepresents the pattern does not proceed to pricing. The
        # chain stops here rather than producing a price for something that cannot ship.
        return {"slug": slug, "version": version, "ok": False,
                "blocking_image_problems": blocking}

    release = ctx.job.inputs.get("release", "")
    token = ctx.job.inputs.get("rebuild", "")
    payload = {"slug": slug, "version": version, "release": release, "rebuild": token,
               "pages": doc.pages,
               "size_label": doc.size_label(),
               "finished_size_cm": list(doc.finished_size_cm) if doc.finished_size_cm else None,
               "yardage": doc.yardage_by_color, "tolerance": doc.yardage_tolerance,
               "calibrated": doc.calibrated,
               "pdf_sha256": pdf.sha256, "chart_sha256": chart.sha256,
               "legend_sha256": legend.sha256,
               # Both documents' hashes, so a later step can prove the file it is handling is
               # one of the two this release certified rather than only the US one.
               "pdf_sha256_by_terminology": {t: stored.sha256
                                             for t, stored in sorted(pdfs.items())},
               "frames": stored_frames}
    ctx.enqueue("pricing", "pricing.position", payload,
                idempotency_key=chain_key("price", slug, version, release, token))
    return payload


def _disclosed_render_set(ctx: JobContext, cir, slug: str, version: str, store,
                          lineage) -> dict | None:
    """Render, verify, QA and file the disclosed listing set for a Launch-0 release.

    Skipped when a photograph that clears every floor is on file, and reused when this exact
    design already has a set. Returns a summary for the build's audit row; the full record
    (frames, manifests, verification, QA) is its own audit row, which `listing_asset.last`
    reads for the parity and eligibility gates.
    """
    from ..publish import disclosed_listing, listing_asset

    if not listing_asset._in_launch_scope(slug):
        return None
    current = listing_asset.last(ctx.db, slug=slug)
    if current and current.get("kind") != "disclosed_render" and listing_asset.usable(current):
        return {"skipped": "a qualified photograph is on file"}
    if (current and current.get("kind") == "disclosed_render"
            and current.get("version") == version
            and current.get("cir_fingerprint") == cir.fingerprint):
        return {"reused": True, "usable": current.get("usable_as_listing_asset"),
                "frames": [f["image"]["sha256"] for f in current.get("frames") or []]}
    try:
        rec = disclosed_listing.build(cir, store=store, db=ctx.db, lineage=lineage)
    except Exception as exc:  # noqa: BLE001 - imagery that could not be made is recorded,
        # never allowed to take the PDF and chart build down with it.
        ctx.audit("assets.disclosed_render_failed", artifact=f"{slug}@{version}",
                  detail={"why": f"{type(exc).__name__}: {str(exc)[:300]}"})
        return {"made": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if rec.get("made"):
        disclosed_listing.record(ctx.db, rec)
    return {"made": rec.get("made"), "usable": rec.get("usable_as_listing_asset"),
            "launch_blocked": rec.get("launch_blocked", [])[:5],
            "frames": [{"view": f["view"], "sha256": f["image"]["sha256"],
                        "structural_truth": f["structural_truth"]["status"]}
                       for f in rec.get("frames") or []]}


def _pricing_net_inputs(db, slug: str) -> dict:
    """What `decide_price` needs to decide on net contribution, read from rows (#269)."""
    from sqlalchemy import select

    from ..core.models import Order, PriceObservation
    from ..finance import currency

    from ..commerce import orders_ingest as _oi

    with db.session() as s:
        orders = _oi.countable_orders(s)  # rc1-ORD2: the one countable predicate
        points = [{"price_cad": float(p.price_cad or 0.0), "visits": int(p.visits or 0),
                   "contribution_cad": float(p.contribution_cad or 0.0)}
                  for p in s.scalars(select(PriceObservation).where(
                      PriceObservation.product_slug == slug, PriceObservation.on_sale.is_(False)))]
    foreign = None
    rate = None
    if orders:
        foreign = sum(1 for o in orders if (o.currency or "CAD") != "CAD") / len(orders)
        measured = [o for o in orders if o.fx_measured and o.fx_usd_per_cad]
        if measured:
            last = max(measured, key=lambda o: o.fx_taken_on or "")
            from datetime import date as _d

            rate = currency.Rate(float(last.fx_usd_per_cad),
                                 _d.fromisoformat(last.fx_taken_on) if last.fx_taken_on
                                 else _d.today(), measured=True, source="settlement")
    return {"foreign_share": foreign, "rate": rate, "price_points": points}


@handlers.register("pricing.position")
def handle_pricing_position(ctx: JobContext) -> dict:
    i = dict(ctx.job.inputs)
    slug = i["slug"]
    record = _product_record(slug, i)
    if record is None:
        # PT-01: no default product type, so no default price band either.
        ctx.audit("pricing.refused", artifact=slug, detail={
            "code": UNKNOWN_PRODUCT, "stopped": "listing.seo not enqueued",
            "why": "no product record names what this product is (no Launch-0 identity, no "
                   "radar seed, no category in the job): it is not priced from another "
                   "product's band"})
        return {"slug": slug, "refused": True, "code": UNKNOWN_PRODUCT, "stopped": True}
    launch = products_launch0.launch_price(slug) if record["launch0"] else None
    if record["launch0"]:
        return _price_launch0(ctx, i, slug, record, launch)
    seed = _seed_for(slug)
    category = record["category"]
    band = CATEGORY_BANDS_CAD.get(category, DEFAULT_BAND)
    sizes = len(ctx.job.inputs.get("sizes") or []) or 1
    is_bundle = bool(seed and seed.is_bundle)
    # #7: the customer outcome is priced -- the finished object, the hours it asks for and the
    # support that comes with it -- anchored on what the department is observed to charge.
    # A bundle keeps its own arithmetic below, which is measured against its members.
    outcome = None if is_bundle else _outcome_price(ctx, i, seed, category, band)
    proposed = (outcome["price_cad"] if outcome else
                (seed.price_cad if seed else band[1]))
    # #24: contribution per visitor, not conversion, decides. When a higher-priced sibling in
    # this category earns more per visitor than this listing, a lower price is not proposed.
    per_visitor = _contribution_per_visitor_guard(ctx, slug, category, proposed)
    proposed = per_visitor["proposed_cad"]

    members = ctx.job.inputs.get("bundle_members_cad")
    if is_bundle and not members:
        # A bundle's saving has to be measured against the prices we actually charge for its
        # members, so they are read from the pool rather than guessed or passed in by a
        # caller who might pass anything.
        members = [m.price_cad for m in POOL
                   if m.family == seed.family and not m.is_bundle]
    # #269 (C-64): the decision reads net contribution from what the orders show -- the share
    # paid in another currency and the rate recorded with them -- and this product's measured
    # price points, rather than deciding on the sticker.
    net_inputs = _pricing_net_inputs(ctx.db, slug)
    decision = pricing_mod.decide_price(
        slug, category_band_cad=band, proposed_cad=proposed,
        has_video=False, sizes_offered=sizes,
        is_bundle=is_bundle, bundle_members_cad=members, **net_inputs)
    # #269 (CB2-O08): a net floor no price in the band can clear stops the chain here. The
    # product is not passed to listing at a price that cannot pay for itself; the refusal is
    # audited and the job returns it, and nothing downstream is queued.
    if decision.refused:
        ctx.audit("pricing.refused", artifact=slug,
                  detail={**decision.to_dict(), "stopped": "listing.seo not enqueued"})
        return {**decision.to_dict(), "stopped": True}

    # #233 / #235 (CB2-O08): the daily order readings' discount guard and promotion verdicts.
    # A product the guard refused, or whose promotion lost contribution, is full price only:
    # any sale the job was asked to run (`inputs.promotion`, a promo price and window) is
    # dropped before it reaches the listing, and the listing is told no sale is allowed.
    from ..commerce.order_readings import directives

    guard = directives(ctx.db)
    sale_allowed = True
    if slug in guard["discount_refused"] or slug in guard["promotion_do_not_repeat"]:
        sale_allowed = False
        decision.reasons.append(
            "full price only: the value-ladder discount guard or a measured promotion "
            "verdict refuses a sale price for this product (#233, #235)")
        if i.get("promotion"):
            ctx.audit("pricing.promotion_refused", artifact=slug,
                      detail={"promotion": i["promotion"],
                              "discount_refused": slug in guard["discount_refused"],
                              "promotion_do_not_repeat":
                                  slug in guard["promotion_do_not_repeat"]})
            i.pop("promotion", None)
    i["sale_allowed"] = sale_allowed

    # The category's standing "50% off" is not available to us; assert that explicitly rather
    # than relying on nobody adding it later.
    pricing_mod.check_no_fake_discount(decision.price_cad, None, ever_charged=False)

    # #46: every price this handler sets opens a point in the elasticity memory, with its
    # season, traffic source and sale state as columns. An unchanged price is not re-recorded,
    # so a rebuild cannot manufacture a flat history.
    from ..commerce import elasticity

    price_point = elasticity.record_price_set(
        ctx.db, product_slug=slug, category=category, price_cad=decision.price_cad,
        season=(seed.season or "evergreen") if seed else "unassigned")

    ctx.audit("pricing.positioned", artifact=slug,
              detail={**decision.to_dict(), "price_point": price_point,
                      "outcome_price": outcome, "per_visitor": per_visitor})
    i.update({"price_cad": decision.price_cad, "net_cad": decision.net_cad,
              "pricing_reasons": decision.reasons, "pricing_warnings": decision.warnings,
              "category": category})
    ctx.enqueue("listing", "listing.seo", i,
                idempotency_key=chain_key("seo", slug, i["version"], i.get("release", ""),
                                          i.get("rebuild", "")))
    return decision.to_dict()


def _price_launch0(ctx: JobContext, i: dict, slug: str, record: dict,
                   launch: dict | None) -> dict:
    """PT-04: a Launch-0 product is priced from its own plan, with the basis recorded.

    `products.launch0.price_plan` runs the candidate's researched band and proposal through
    `commerce.pricing.decide_price` (floor, ceiling, fee arithmetic). The radar category band,
    the outcome anchor and the per-visitor guard are not consulted: they priced a CA$4 coaster
    set at CA$14. A plan price outside the candidate's band, or one the pricing module
    refused, stops the chain here rather than reaching a listing.
    """
    if launch is None or launch.get("price_cad") is None:
        ctx.audit("pricing.refused", artifact=slug, detail={
            "code": UNKNOWN_PRODUCT, "stopped": "listing.seo not enqueued",
            "why": f"Launch-0 product {slug} has no price plan on its candidate"})
        return {"slug": slug, "refused": True, "code": UNKNOWN_PRODUCT, "stopped": True}
    if not launch["within_plan_band"]:
        ctx.audit("pricing.refused", artifact=slug, detail={
            **{k: launch[k] for k in ("price_cad", "band_cad", "proposed_cad", "basis")},
            "code": "OUTSIDE_PLAN_BAND", "stopped": "listing.seo not enqueued"})
        return {"slug": slug, "refused": True, "code": "OUTSIDE_PLAN_BAND", "stopped": True,
                "price_cad": launch["price_cad"], "band_cad": launch["band_cad"]}

    from ..commerce import elasticity
    from ..commerce.order_readings import directives

    guard = directives(ctx.db)
    sale_allowed = not (slug in guard["discount_refused"]
                        or slug in guard["promotion_do_not_repeat"])
    if not sale_allowed:
        i.pop("promotion", None)
    i["sale_allowed"] = sale_allowed
    price = float(launch["price_cad"])
    pricing_mod.check_no_fake_discount(price, None, ever_charged=False)
    price_point = elasticity.record_price_set(
        ctx.db, product_slug=slug, category=record["category"], price_cad=price,
        season="evergreen")
    detail = {"price_cad": price, "net_cad": launch["net_cad_after_fees"],
              "band_cad": list(launch["band_cad"]), "band_basis": launch["band_basis"],
              "proposed_cad": launch["proposed_cad"], "basis": launch["basis"],
              "candidate": launch["candidate"], "reasons": list(launch["reasons"]),
              "warnings": list(launch["warnings"]), "price_point": price_point,
              "product_record": record["source"]}
    ctx.audit("pricing.positioned", artifact=slug, detail=detail)
    i.update({"price_cad": price, "net_cad": launch["net_cad_after_fees"],
              "pricing_reasons": list(launch["reasons"]),
              "pricing_warnings": list(launch["warnings"]),
              "pricing_basis": launch["basis"], "category": record["category"]})
    ctx.enqueue("listing", "listing.seo", i,
                idempotency_key=chain_key("seo", slug, i["version"], i.get("release", ""),
                                          i.get("rebuild", "")))
    return detail


OUTCOME_ANCHOR_MIN_LISTINGS = 5


def _outcome_price(ctx: JobContext, inputs: dict, seed, category: str,
                   band: tuple[float, float]) -> dict | None:
    """#7: `value_stack.outcome_price` on this release's finished size, make time and colours.

    The anchor is the department's observed median price from the benchmark catalogue when
    at least five listings were observed there, and otherwise the midpoint of the category's
    researched band -- labelled, so a reader can see which one priced it.
    """
    from statistics import median
    from types import SimpleNamespace

    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..publish.value_stack import ValueStackRefused, outcome_price
    from ..seasonal.daily import DEPARTMENT_OF
    from ..seasonal.leadtime import classify

    size = inputs.get("finished_size_cm") or [None, None]
    if not seed or not size or size[0] is None:
        return None
    pod = DEPARTMENT_OF.get(category)
    with ctx.db.session() as s:
        prices = [float(r.price_cad) for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.pod == pod)) if r.price_cad and r.price_cad > 0] if pod else []
    if len(prices) >= OUTCOME_ANCHOR_MIN_LISTINGS:
        anchor, basis = median(prices), f"observed median of {len(prices)} {pod} listings"
    else:
        anchor = (band[0] + band[1]) / 2
        basis = (f"midpoint of the researched {category} band: {len(prices)} observed {pod} "
                 f"listing(s), below the {OUTCOME_ANCHOR_MIN_LISTINGS} a median needs")
    hours = sum(seed.maker_hours) / 2.0
    try:
        got = outcome_price(SimpleNamespace(width_cm=float(size[0]),
                                            height_cm=float(size[1] or size[0])),
                            make_hours=hours, make_lane=classify(hours),
                            colours=len(inputs.get("yardage") or {}) or 1,
                            market_median_cad=anchor)
    except (ValueStackRefused, TypeError, ValueError):
        return None
    got["anchor_basis"] = basis
    return got


def _contribution_per_visitor_guard(ctx: JobContext, slug: str, category: str,
                                    proposed: float) -> dict:
    """#24 in the pricing agent: read the per-visitor ranking and refuse a conversion-led cut."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ..scale.runrate import per_visitor_from_db

    ranking = per_visitor_from_db(ctx.db)
    rows = {r["slug"]: r for r in ranking.get("ranked") or []}
    mine = rows.get(slug)
    if mine is None:
        return {"proposed_cad": proposed, "status": UNMEASURED_PRICE,
                "why": "this listing has no recorded visits and measured orders yet"}
    peers = [r for k, r in rows.items() if k != slug
             and (_seed_for(k).category if _seed_for(k) else "") == category]
    richer = [r for r in peers if r["price_cad"] > mine["price_cad"]
              and r["contribution_per_visitor"] > mine["contribution_per_visitor"]]
    with ctx.db.session() as s:
        current = max((float(l.price_cad or 0.0) for l in s.scalars(
            select(Listing).where(Listing.product_slug == slug))), default=0.0)
    floor = current if richer else 0.0
    return {"proposed_cad": max(proposed, floor), "status": "measured",
            "contribution_per_visitor": mine["contribution_per_visitor"],
            "higher_priced_peers_earning_more": [r["slug"] for r in richer],
            "why": ("a higher-priced sibling earns more per visitor, so the price is not cut "
                    "to chase conversion" if richer else
                    "no higher-priced sibling earns more per visitor")}


UNMEASURED_PRICE = "UNMEASURED"


@handlers.register("listing.seo")
def handle_listing_seo(ctx: JobContext) -> dict:
    """Assemble the listing from computed facts, then let the Policy Gate try to break it."""
    i = dict(ctx.job.inputs)
    slug, version = i["slug"], i["version"]
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))
    # PT-01: the title, tags and category come from the product's own record. A product
    # nobody has described is refused here -- there is no default product type.
    record = _product_record(slug, i)
    if record is None:
        why = (f"{UNKNOWN_PRODUCT}: no product record names what {slug} is (no Launch-0 "
               f"identity, no radar seed, no category in the job); no listing is drafted "
               f"under another product's type")
        ctx.audit("listing.seo_blocked", artifact=f"{slug}@{version}",
                  detail={"blocking": [why], "code": UNKNOWN_PRODUCT})
        return {"slug": slug, "version": version, "ok": False, "blocking": [why]}
    category = (record["category"] if record["launch0"]
                else (i.get("category") or record["category"]))
    season = record["season"]
    # #297: a pivot to evergreen removes the seasonal premise from the copy -- no season in
    # the title and none in the query set -- rather than relabelling a Christmas listing.
    evergreen = i.get("positioning") == "evergreen"
    if evergreen:
        season = None
    motifs = list(record["motifs"])

    tolerance_pct = int(twin.yardage_tolerance * 100)
    yardage_lines = [
        f"{name}: about {m * (1 - twin.yardage_tolerance):.0f}-"
        f"{m * (1 + twin.yardage_tolerance):.0f} m"
        for name, m in sorted(twin.yarn_metres_by_color.items())
    ]
    gauge_line = (f"{cir.gauge.stitches_per_10cm} sts x {cir.gauge.rows_per_10cm} rows = 10 cm "
                  f"in {cir.gauge.stitch_type}, {cir.gauge.hook_mm:g} mm hook"
                  if cir.gauge else None)
    from ..cir.twin import size_statement   # PT-10: round pieces name their convention

    size_label = ((size_statement(twin) if twin.shape is not None else
                   f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm")
                  if twin.width_cm and twin.height_cm else None)

    # F-005..F-009: the deepest truthful Etsy category, from the stored taxonomy snapshot,
    # and every property of that node decided from the pattern's own facts. No snapshot is
    # UNKNOWN -- the draft proceeds, and search certification refuses below.
    from ..commerce import category as category_mod

    difficulty = _difficulty(twin, cir)
    colors = sorted(c for c in twin.colors_used if c)
    facts = category_mod.Facts(
        category=category, difficulty=difficulty,
        colors=[(c, (cir.colors or {}).get(c)) for c in colors], season=season,
        width_cm=twin.width_cm or None, height_cm=twin.height_cm or None)
    cat_reading = category_mod.for_product(ctx.db, category=category, facts=facts)
    choice, props = cat_reading["choice"], cat_reading["properties"]
    # F-006 / F-014: the phrases the structured fields already supply.
    structured = (category_mod.path_phrases(choice)
                  + category_mod.attribute_values(props["decisions"]))

    # Tags come from the query model rather than a fixed template: thirteen slots are
    # scarce, and spending them on head terms a shop with no history cannot place for is the
    # most common way a new listing is invisible.
    techniques = (list(record["techniques"]) if record["techniques"] is not None else
                  (["mosaic"] if "mosaic" in (category + " " + cir.slug) else ["texture"]))
    queries = search_mod.build_query_set(category, motifs, season, techniques,
                                         difficulty=difficulty)
    # #293: the phrases buyers were observed using for this product's facets join the query
    # set, and the ones that fit a tag are spent first -- the search strategy starts from
    # what buyers already type, and stays accurate because the facets are the product's own.
    from ..commerce import intent as intent_mod

    buyer = intent_mod.listing_language(ctx.db, slug=slug, category=category, season=season,
                                        difficulty=_difficulty(twin, cir),
                                        techniques=techniques)
    # F-020: the observed phrases carry their provenance and the date they were read; every
    # template phrase stays `assumed`.
    import dataclasses

    read_at = date.today().isoformat()
    queries = queries + [dataclasses.replace(q, provenance="observed:benchmark_titles+serp",
                                             read_at=read_at, family="buyer_language")
                         for q in buyer["queries"]
                         # F-008: observed is not the same as true of this product.
                         if not search_mod.tag_truth(q.phrase, difficulty=difficulty)]
    title = seo_mod.build_title(cir.title, category, motifs, season,
                                sizes=len(i.get("sizes") or []) or 1)
    # #97: Listings read their lesson inbox. A search-language or construction lesson whose
    # words match one of this product's candidate queries puts that query in a tag slot --
    # the listing surfaces what the company learned buyers look for -- and the lesson is
    # recorded as acted on.
    from ..improve import consume

    listing_text = " ".join([cir.title, category, " ".join(motifs)]
                            + [q.phrase for q in queries])
    seo_lessons = [l for l in consume.matching(ctx.db, "seo_search", listing_text,
                                               subject=slug)
                   if l["direction"] >= 0]
    # #293's observed buyer language takes its slots first; a lesson-matched query may take
    # up to two more.
    must = list(buyer["tags"])
    for lesson in seo_lessons:
        for q in queries:
            if (len(q.phrase) <= 20 and q.phrase not in must
                    and set(lesson["shared"]) & set(q.phrase.split())):
                must.append(q.phrase)
                break
    must = must[:len(buyer["tags"]) + 2]
    # F-008: an observed or lesson phrase is still a claim; one this pattern cannot support
    # ("easy" on an intermediate pattern, finished-item phrasing) never takes a slot.
    untrue_must = [m for m in must if search_mod.tag_truth(m, difficulty=difficulty)]
    must = [m for m in must if m not in untrue_must]
    tags = search_mod.choose_tags(queries, must_include=must, exclude=structured)
    lesson_slots = [m for m in must if m not in buyer["tags"]]
    if lesson_slots:
        consume.act(ctx.db, "seo_search", seo_lessons,
                    how=f"listing.seo for {slug} gave a tag slot to {lesson_slots}")
    # #240: a slot spent on a phrase another listing of ours already spends one on is our
    # own listings ranked against each other. Re-chosen from the remaining queries, never
    # fewer slots, and the swap is recorded with the catalogue reading below.
    tags, portfolio_reading = _diversify_tags(ctx.db, slug, queries, tags)
    # #237 / #24: the owner's Etsy Stats export, joined to orders, is read by the SEO agent.
    # A term shown thousands of times that never sold is a vanity term; a slot spent on it is
    # re-spent on a phrase that has not been proven to earn nothing.
    tags, portfolio_reading["search_terms"] = _drop_vanity_tags(ctx.db, queries, tags)

    # A children's product's listing carries the statements a buyer needs before they pay.
    #
    # `seo.build_description` takes them and `seo.childrens_listing_audit` checks the finished
    # text for them, and this caller passed neither -- so the live chain would have assembled a
    # children's listing with no safety section, and the auditor built to catch exactly that
    # would have failed it at the end of a release rather than the start. The assignment comes
    # from the catalogue, which is where "is this merchandised to a child" is decided; None
    # means it is not, and a non-children's listing acquires nothing.
    assignment = products_launch0.childrens_assignment(cir.slug)
    childrens = (childrens_statements(cir, twin, assignment)
                 if assignment is not None else None)

    from ..learn import service as _learn_service

    copy = seo_mod.ListingCopy(
        title=title,
        tags=tags,
        description=seo_mod.build_description(
            cir.title, size_label=size_label, yardage_lines=yardage_lines,
            tolerance_pct=tolerance_pct, difficulty=difficulty,
            colors=colors, terminology="US",
            gauge_line=gauge_line, stitches=sorted(twin.stitch_types_used),
            season=season, pages=i.get("pages"),
            collapsed_repeats=collapses_rows(cir), childrens=childrens,
            key_phrases=_opening_phrases(tags, queries),
            # F-808: approved lessons only, and only once an owned HTTPS Learn origin is set.
            lesson_links=_learn_service.listing_help_links(ctx.db, cir.to_dict())),
        materials=[m.name for m in cir.materials],
        price_cad=float(i.get("price_cad", 0.0)),
        supported_claims=[c for c in (size_label, gauge_line) if c],
    )

    attributes = search_mod.listing_attributes(
        category=category, difficulty=difficulty, colors=colors, season=season)

    # #35: classify this release under the Creativity Standards before its listing exists,
    # generate the disclosures it owes into the copy, and let the Policy Gate check the copy
    # against that classification. A generated image in a role that claims something about
    # the finished object is refused; labelling it does not convert it.
    from ..gates import platform_policy
    from ..publish import listing_asset

    release_frames = list(i.get("frames") or _stored_frames(ctx.db, slug, version))
    on_file = listing_asset.frames_for(ctx.db, slug=slug)
    generated = [f for f in on_file if f.get("made") and f.get("generated", True)]
    # Fail closed (F-852): a generated product picture filed for THIS release in a role that
    # claims something about the object is classified even when another record won the
    # listing slot. Which record `listing_asset.last` happens to prefer must not decide whether
    # a picture of an object that does not exist is noticed.
    from ..publish import model_photography as _mp, owned_photography as _op

    for _rec in (_op.last_asset(ctx.db, slug=slug), _mp.last_asset(ctx.db, slug=slug)):
        for _f in ((_rec or {}).get("frames") or ([_rec] if _rec else [])):
            if (_f.get("made", (_rec or {}).get("made")) and _f.get("generated")
                    and (_rec or {}).get("version") in (None, version)
                    and not any(_f is g for g in generated)):
                generated.append(_f)
    # D-FB-7: disclosed renders are classified as what they are, and their disclosure is
    # written into the copy the export check later reads back.
    disclosed = [f for f in on_file if f.get("kind") == "disclosed_render"]
    try:
        classification = platform_policy.classify_release(release_frames, generated,
                                                          disclosed=disclosed)
        class_problems = [f"POLICY_CLASSIFICATION: {p}" for p in classification.problems]
    except platform_policy.PolicyRefused as exc:
        classification = None
        class_problems = [f"POLICY_CLASSIFICATION: {exc}"]
    if classification is not None and classification.disclosures:
        copy.description = (copy.description.rstrip() + "\n\n"
                            + platform_policy.disclosure_block(classification))
    try:
        new_class = platform_policy.check_new_class(
            ctx.db, product_class=classification.product_class if classification
            else platform_policy.AI_ASSISTED_DESIGN,
            asset_roles=tuple(sorted({a.role for a in platform_policy.release_assets(
                release_frames, generated)})) if classification else ())
        new_class = {"enabled": True, "policy": new_class.get("policy")}
    except platform_policy.PolicyRefused as exc:
        # Recorded, not raised: drafting a listing is not enabling a class for sale. The
        # stamp rides with the listing so publication can see the reading was not current.
        new_class = {"enabled": False, "why": str(exc)[:400]}
    ctx.audit(platform_policy.CLASSIFIED_ACTION, artifact=f"{slug}@{version}", detail={
        "classification": classification.to_dict() if classification else None,
        "problems": class_problems, "assets": len(release_frames) + len(generated),
        "generated_assets": len(generated), "class_enablement": new_class})

    coverage = search_mod.score_coverage(
        queries, title=copy.title, tags=copy.tags, description=copy.description,
        category_path=choice.path_names,
        attribute_values=category_mod.attribute_values(props["decisions"]))

    # #139: famous dialogue, lyrics, slogans and catchphrases the culture radar declared
    # are screened out of customer-facing copy unless a recorded basis puts them in the
    # direct lane.
    rights_problems, rights_reading = _quote_screen(
        ctx.db, " \n".join([copy.title, copy.description, " ".join(copy.tags)]))

    structural = (seo_mod.check_listing_limits(copy)
                  + search_mod.check_attributes(attributes))
    policy = check_listing(ListingDraft(title=copy.title, description=copy.description,
                                        tags=copy.tags, price_cad=copy.price_cad),
                           classification=classification)
    # The search-copy gate and the truth gates are blocking (F-011, F-021, F-245, F-298,
    # F-026, F-008, F-251): a stuffed title, unused tag slots with no recorded limitation, a
    # keyword-dump description, an untrue tag or attribute stop the draft. They were audited
    # after the listing was written; an audit nobody acts on is not a gate.
    copy_gate = seo_mod.check_search_copy(
        copy, phrases=[q.phrase for q in queries],
        tag_limitation=i.get("tag_slot_limitation"),
        translation_record=i.get("translation_record"))
    tag_problems = search_mod.tags_truth(copy.tags, difficulty=difficulty)
    attribute_problems = search_mod.attribute_truth(attributes, difficulty=difficulty,
                                                    colors=colors, season=season)
    # PT-01: the title and tags name the product the CIR makes, and no fabric it cannot make.
    # Blocking for Launch-0 (the first customer's listings); recorded for the rest of the
    # catalogue, whose CIR titles predate the vocabulary.
    from ..gates import first_customer as _fc

    identity_problems = (_fc.product_type_findings(cir, title=copy.title, tags=copy.tags)
                         + _fc.colourwork_findings(cir, twin, title=copy.title, tags=copy.tags))
    if record["launch0"] and record["kind"] not in _fc.product_type_words_in_cir(cir):
        identity_problems.append(
            f"LISTING_PRODUCT_TYPE_UNSUPPORTED: {record['source']} declares a "
            f"{record['kind']!r} and the CIR ({cir.slug}) names "
            f"{sorted(_fc.product_type_words_in_cir(cir))}")
    blocking = (structural + [str(f) for f in policy if f.is_error] + class_problems
                + rights_problems + copy_gate["blocking"] + tag_problems + attribute_problems
                + (identity_problems if record["launch0"] else []))

    # F-004: the holistic search certificate. Category, properties, copy, tags and the
    # description must all pass; the hero is completed at publish by release_gates.
    duplicates = search_mod.structured_duplicates(copy.tags, structured)
    description_problems = [p for p in copy_gate["blocking"] if p.startswith("DESCRIPTION_")]
    certificate = search_mod.search_certificate(
        category=choice.to_dict(), properties=props, attribute_problems=attribute_problems,
        copy_gate={**copy_gate, "blocking": [p for p in copy_gate["blocking"]
                                             if not p.startswith("DESCRIPTION_")],
                   "ok": not [p for p in copy_gate["blocking"]
                              if not p.startswith("DESCRIPTION_")]},
        tag_problems=tag_problems + [f"TAG_REPEATS_STRUCTURED_FIELD: {t!r}"
                                     for t in duplicates],
        description_problems=description_problems)
    tag_sources = search_mod.tag_provenance(copy.tags, queries, observed_tags=buyer["tags"])
    _persist_search_profile(ctx, slug, version, copy=copy, choice=choice, props=props,
                            attributes=attributes, coverage=coverage, tag_sources=tag_sources,
                            certificate=certificate,
                            tag_limitation=i.get("tag_slot_limitation") or "",
                            snapshot=cat_reading["snapshot"])

    ctx.audit("listing.seo_drafted" if not blocking else "listing.seo_blocked",
              artifact=f"{slug}@{version}",
              detail={"title_len": len(copy.title), "tags": len(copy.tags),
                      "search_share": coverage.share, "gaps": coverage.gaps[:5],
                      "search_share_basis": "assumed+observed (planning proxy)",
                      "evidence_share": coverage.to_dict()["evidence_share"],
                      "blocking": blocking[:5],
                      "search_copy_soft": copy_gate["soft"],
                      "stuffing": copy_gate["stuffing"],
                      "untrue_phrases_withheld": untrue_must,
                      "category": {k: choice.to_dict()[k] for k in
                                   ("status", "taxonomy_id", "path_names", "why")},
                      "properties": {"complete": props.get("complete"),
                                     "gaps": list(props.get("gaps") or [])[:6]},
                      "filters": props.get("filters"),
                      "search_certificate": {k: certificate[k] for k in
                                             ("verdict", "failed", "pending")},
                      "tag_provenance": tag_sources,
                      "coverage_matrix": coverage.matrix,
                      "buyer_language": {k: v for k, v in buyer.items() if k != "queries"},
                      "disclosures_owed": (classification.disclosures
                                           if classification else None),
                      "rights_screen": rights_reading,
                      "product_record": {k: record[k] for k in ("source", "kind", "category",
                                                                "launch0")},
                      "product_identity_findings": identity_problems[:5]})
    if blocking:
        return {"slug": slug, "version": version, "ok": False, "blocking": blocking}

    i.update({"listing": copy.to_dict(), "attributes": attributes,
              "search_coverage": coverage.to_dict(),
              # For the publish path (cluster B): the node and the property payload to send.
              "search_category": {k: choice.to_dict()[k] for k in
                                  ("status", "taxonomy_id", "path_names")},
              "etsy_properties": list(props.get("payload") or []),
              "search_certificate": {k: certificate[k] for k in
                                     ("verdict", "failed", "pending")},
              "classification": classification.to_dict() if classification else None})
    _persist_listing(ctx, slug, version, copy, coverage.share, i.get("release", ""))
    # F-004: the hero is the one search dimension the draft cannot judge. Now that the copy
    # the listing-set certificate checks (the disclosure, the dimensions) is on file, the
    # certified image set is judged and the completed certificate written back with its
    # evidence -- the stored verdict reaches PASS on the merits or stays PENDING/REFUSED.
    hero_reading = _judge_search_hero(ctx, slug, version)

    # #41 / C-47: the disclosure check reads the stored Listing row, so it runs here, after
    # the row exists -- run before it (as listing.draft did) it could only ever say
    # UNMEASURED. A missing owed disclosure is a finding on the draft and publication
    # re-checks it.
    from ..commerce.buyer_trust import listing_disclosure_finding

    disclosure = listing_disclosure_finding(ctx.db, slug=slug, version=version)
    ctx.audit("listing.disclosure_finding" if disclosure.get("finding")
              else "listing.disclosure_checked", artifact=f"{slug}@{version}",
              detail=disclosure)
    # C-69 / #40 / #54: the product's support knowledge (its FAQ, rendered from the one terms
    # decision plus this release's own facts) is produced here, where the PDF and the listing
    # both exist, and the three surfaces are checked against each other on the produced
    # artefacts. A divergence stops the chain before launch and halts publication.
    knowledge = _support_knowledge(ctx, slug, version, i, cir=cir, twin=twin,
                                   listing_text=copy.description)
    if knowledge.get("divergent"):
        return {"slug": slug, "version": version, "ok": False,
                "blocking": ["terms diverge across PDF, listing and FAQ"],
                "terms": knowledge["consistency"]}
    # #240: the catalogue reading, with this listing in it.
    from ..commerce import portfolio as portfolio_mod

    catalogue = portfolio_mod.diversification(ctx.db)
    ctx.audit("listing.query_portfolio", artifact=f"{slug}@{version}", detail={
        **portfolio_reading,
        "stuffing": portfolio_mod.stuffing(copy.title, copy.tags),
        "catalogue": {k: catalogue.get(k) for k in ("measurable", "listings",
                                                    "concentrated_on", "competing_pairs",
                                                    "stuffing", "required_facets_missing")}})
    ctx.enqueue("growth", "launch.plan", i,
                idempotency_key=chain_key("launch", slug, version, i.get("release", ""),
                                          i.get("rebuild", "")
                                          + (":evergreen" if evergreen else "")))
    return {"slug": slug, "version": version, "ok": True, "listing": copy.to_dict(),
            "attributes": attributes, "search_coverage": coverage.to_dict(),
            "disclosures": disclosure, "query_portfolio": portfolio_reading,
            "search_hero": hero_reading}


def _judge_search_hero(ctx: JobContext, slug: str, version: str) -> dict:
    """Judge frame 1 on the certified listing set and complete the search certificate.

    The listing set is certified (or its valid certificate re-checked) under the same
    issuance conditions `release_gates.for_publish` uses -- not while the release is stale
    and not outside its launch window -- and `search.judge_hero` writes the completed
    certificate back: PASS only when every dimension passed on the merits. A failure to judge
    is recorded and leaves the stored verdict short of PASS; it never passes.
    """
    from ..commerce import search as search_mod
    from ..publish import release_gates as rg

    try:
        stale = rg.staleness(ctx.db, slug=slug)
        window = rg.window_decision(ctx.db, slug=slug, version=version)
        set_verdict = rg.listing_set(ctx.db, slug=slug, version=version,
                                     issue=not stale["blocks"]
                                     and window["may_launch_seasonally"])
        reading = search_mod.judge_hero(ctx.db, slug=slug, version=version,
                                        set_verdict=set_verdict)
    except Exception as exc:  # noqa: BLE001 - unjudged stays short of PASS
        reading = {"judged": False, "verdict": None,
                   "why": f"hero not judged: {type(exc).__name__}: {str(exc)[:200]}"}
    ctx.audit(search_mod.HERO_JUDGED_ACTION, artifact=f"{slug}@{version}",
              detail=json.loads(json.dumps(reading, default=str)))
    return {k: reading.get(k) for k in ("judged", "verdict", "why", "reasons")
            if k in reading}


# Query families whose phrases name the product rather than the file format, which is what
# a description's first sentence should carry (F-025).
_OPENING_FAMILIES = ("buyer_language", "motif", "object", "core", "seasonal", "family")


def _opening_phrases(tags: list[str], queries) -> list[str]:
    """Up to three of the chosen tags that name the product, in slot order (F-025)."""
    family = {q.phrase: q.family for q in queries}
    return [t for t in tags if family.get(t) in _OPENING_FAMILIES][:3]


def _persist_search_profile(ctx: JobContext, slug: str, version: str, *, copy, choice, props,
                            attributes: dict, coverage, tag_sources: list, certificate: dict,
                            tag_limitation: str, snapshot: dict | None) -> None:
    """The listing's search-truth reading, bound to the copy it was computed on (F-002, F-004).

    Written whether or not the draft was blocked: the query -> field matrix and the refusal
    reasons of a blocked draft are exactly what somebody needs to read. The fingerprint is
    of the copy passed here, which is the copy `_persist_listing` stores when the draft is
    not blocked, so `release_gates.search_gate` can tell an edited listing from this one.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import ListingSearchProfile
    from ..publish.release_gates import search_fingerprint

    payload = list(props.get("payload") or [])
    fingerprint = search_fingerprint(title=copy.title, description=copy.description,
                                     tags=copy.tags, taxonomy_id=choice.taxonomy_id,
                                     properties=payload)
    with ctx.db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug,
            ListingSearchProfile.version == version))
        if row is None:
            row = ListingSearchProfile(product_slug=slug, version=version)
            s.add(row)
        row.snapshot_id = (snapshot or {}).get("id")
        row.category_status = choice.status
        row.taxonomy_id = choice.taxonomy_id
        row.taxonomy_path = list(choice.path_names)
        row.attributes = json.loads(json.dumps(attributes, default=str))
        row.properties = json.loads(json.dumps(payload, default=str))
        row.filters = json.loads(json.dumps({**(props.get("filters") or {}),
                                             "decisions": props.get("decisions") or []},
                                            default=str))
        row.coverage_matrix = json.loads(json.dumps(coverage.matrix, default=str))
        row.tag_provenance = list(tag_sources)
        row.tag_limitation = tag_limitation or ""
        row.verdict = certificate["verdict"]
        row.certificate = json.loads(json.dumps(certificate, default=str))
        row.fingerprint = fingerprint
        row.updated_at = datetime.now(timezone.utc)


@handlers.register("listing.taxonomy_refresh")
def handle_taxonomy_refresh(ctx: JobContext) -> dict:
    """F-005: read Etsy's seller taxonomy into a snapshot, behind the etsy_api gate.

    A closed gate is an honest no-op: no client is built, no request is made, and the run
    says UNMEASURED with the reason. Every category then stays UNKNOWN and search
    certification refuses -- which is the truth about a company that has not read the tree.
    """
    from ..integrations import etsy_taxonomy

    got = etsy_taxonomy.refresh(ctx.db)
    summary = {k: got.get(k) for k in ("ran", "reading", "network_calls", "snapshot_id",
                                       "new_snapshot", "nodes", "pattern_subtree",
                                       "properties_read", "truncated", "why")}
    summary["gate_missing"] = (got.get("gate") or {}).get("missing", [])
    ctx.audit(etsy_taxonomy.REFRESHED_ACTION if got.get("ran")
              else "etsy.taxonomy_unmeasured", detail=summary)
    return summary


SUPPORT_KNOWLEDGE_ACTION = "support.knowledge_built"
TERMS_DIVERGENCE_SIGNATURE = "terms-divergence"


def support_faq(cir, twin, *, version: str) -> str:
    """This release's FAQ: the shop FAQ (terms rendered from one decision) plus its own facts."""
    from ..commerce import shop_package

    stitches = ", ".join(sorted(twin.stitch_types_used)) or "see the stitch key"
    yardage = "; ".join(f"{name} about {m * (1 - twin.yardage_tolerance):.0f}-"
                        f"{m * (1 + twin.yardage_tolerance):.0f} m"
                        for name, m in sorted(twin.yarn_metres_by_color.items()))
    product = [
        ("Which version of this pattern do I have?",
         f"This is version {version} of {cir.title}. Every question is answered against the "
         f"exact version you bought."),
        ("Which stitches do I need?", f"{stitches}. Every stitch is in the key."),
        ("How much yarn does it take?", yardage or "See the materials page of the pattern."),
        ("How hard is it?", f"{_difficulty(twin, cir)}."),
    ]
    return shop_package.faq_text() + "\n\n" + "\n\n".join(f"{q}\n{a}" for q, a in product)


def _support_knowledge(ctx: JobContext, slug: str, version: str, i: dict, *, cir, twin,
                       listing_text: str) -> dict:
    """Build and record the release's support knowledge; check #40 on the produced surfaces."""
    from ..commerce import terms as customer_terms
    from ..core.artifacts import ArtifactMissing
    from ..core.models import Incident
    from ..ops import artefacts as provenance
    from ..publish.pdf import extracted_text

    faq = support_faq(cir, twin, version=version)
    store = ArtifactStore(i.get("artifact_dir"))
    lineage = _lineage(ctx, validation_status="passed")
    stored = store.put(f"{slug}/{version}/support-faq.txt", faq.encode("utf-8"),
                       "text/plain", artefact_class="support_knowledge", lineage=lineage)
    key = provenance.release_key(slug, version)
    pdf_sha = (i.get("pdf_sha256_by_terminology") or {}).get("US") or i.get("pdf_sha256")
    pdf_text, pdf_status = None, "UNMEASURED: no PDF hash on this job"
    if pdf_sha:
        try:
            pdf_text = extracted_text(store.get(pdf_sha, db=ctx.db))
            pdf_status = "measured"
        except ArtifactMissing as exc:
            pdf_status = f"UNMEASURED: {exc}"[:200]
    consistency = (customer_terms.consistency(pdf_text, listing_text, faq)
                   if pdf_text is not None else None)
    divergent = bool(consistency and not consistency["consistent"])
    with ctx.db.session() as s:
        design = provenance.design_inputs(s, slug, version)
        parents = [f"listing_copy:{key}"]
        if pdf_sha:
            parents.append(f"pdf:{provenance.pdf_key(slug, version, 'US')}")
        provenance.record_lineage(
            s, artefact_class="support_knowledge", artefact_key=f"{key}#support",
            product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
            lineage=lineage.for_file(stored.sha256).under(*parents).validated(
                "blocked" if divergent else ("passed" if consistency else "unmeasured")))
        if divergent:
            sig = f"{TERMS_DIVERGENCE_SIGNATURE}:{slug}"
            if s.scalar(select_incident(Incident, sig)) is None:
                s.add(Incident(severity="P1", signature=sig, halts_publication=True,
                               summary=(f"customer-use terms diverge across the produced PDF, "
                                        f"listing and FAQ of {slug}@{version} (#40)"),
                               detail={"divergences": consistency["divergences"][:12]}))
    ctx.audit("terms.divergent" if divergent else SUPPORT_KNOWLEDGE_ACTION,
              artifact=f"{slug}@{version}",
              detail={"faq_sha256": stored.sha256, "faq_chars": len(faq),
                      "pdf": pdf_status,
                      "consistent": None if consistency is None else consistency["consistent"],
                      "divergences": (consistency or {}).get("divergences", [])[:12]})
    return {"faq_sha256": stored.sha256, "consistency": consistency, "divergent": divergent,
            "pdf": pdf_status}


def select_incident(Incident, signature: str):
    from sqlalchemy import select

    return select(Incident).where(Incident.signature == signature,
                                  Incident.resolved.is_(False))


FRAME_REVIEW_ACTION = "assets.frame_review"
# What each frame's role claims, in the closed vocabulary `visual.inspect.compare` checks.
# Every role `listing_assets.build_frames` emits has an entry (C-80 defect 6): a frame with
# no claim would be compared against nothing and pass by having nothing to fail, so a role
# missing here is recorded UNCLAIMED and blocks, never reviewed vacuously.
ROLE_CLAIMS: dict[str, dict] = {
    "hero": {"shows_finished_object": True},
    "whats_included": {"shows_text": True},
    "size": {"shows_size_reference": True},
    "materials": {"shows_text": True},
    "pattern_preview": {"shows_text": True},
    "chart": {"shows_chart_preview": True},
    "collection": {"shows_text": True},
}


def _review_frames(ctx: JobContext, slug: str, version: str, frames, paths: dict,
                   shas: dict[int, str] | None = None) -> dict:
    from ..visual import inspect as inspection_mod
    from ..visual.gallery import gates_now

    vision_open = gates_now(ctx.db, keys=("image_vision",)).get("image_vision", False)
    verdicts: dict[int, dict] = {}
    blocking: list[str] = []
    for frame in frames:
        claim = ROLE_CLAIMS.get(frame.role)
        if claim is None:
            verdicts[frame.position] = {"role": frame.role, "verdict": "unclaimed",
                                        "why": f"no claim is registered for role "
                                               f"{frame.role!r}; a frame compared against "
                                               f"nothing is not reviewed (#61)"}
            blocking.append(f"FRAME_REVIEW_UNCLAIMED: frame {frame.position} ({frame.role}) "
                            f"has no registered claim to be reviewed against")
            continue
        if not vision_open:
            verdicts[frame.position] = {"role": frame.role, "verdict": "unreviewed",
                                        "why": "image_vision gate closed: no model has "
                                               "been proven to look at a picture"}
            continue
        try:
            got = inspection_mod.inspect_image(paths[frame.position], db=ctx.db, claim=claim)
            verdict = inspection_mod.gate(got)
        except Exception as exc:  # noqa: BLE001 - a review that failed is unmade, not passed
            verdicts[frame.position] = {"role": frame.role, "verdict": "unreviewed",
                                        "why": f"{type(exc).__name__}: {exc}"[:200]}
            continue
        # C-80 defect 6 (Codex P06): an unjudged verdict stays unjudged. Unmade checks are
        # not passed checks, whatever kind of frame they were not made on; the publish path
        # reads anything other than `clear` as not independently reviewed.
        verdicts[frame.position] = {"role": frame.role, "verdict": verdict["verdict"],
                                    "why": verdict.get("why"),
                                    "unmade": verdict.get("unmade"),
                                    "semantic": (got.get("semantic") or {}).get("problems")}
        if verdict["verdict"] == "blocked":
            blocking.append(f"FRAME_REVIEW_BLOCKED: frame {frame.position} ({frame.role}) "
                            f"does not communicate what it claims: "
                            f"{(got.get('semantic') or {}).get('problems')}"[:400])
    ctx.audit(FRAME_REVIEW_ACTION, artifact=f"{slug}@{version}",
              detail={"vision_open": vision_open,
                      "frames": {str(k): v for k, v in verdicts.items()},
                      # the bytes this review was of (C-80 defect 7): the publish path
                      # accepts the review only for these exact stored frames
                      "frame_shas": {str(k): v for k, v in (shas or {}).items()},
                      "unreviewed": sorted(k for k, v in verdicts.items()
                                           if v["verdict"] == "unreviewed")})
    return {"verdicts": verdicts, "blocking": blocking, "vision_open": vision_open}


def frame_review_state(db, slug: str, version: str) -> dict:
    """The latest independent review of this release's frames, for the publish path.

    Reviewed only when the review judged a non-empty set of frames, every one is `clear`,
    and the review was of exactly the frame bytes now stored for the release (the sha set
    recorded with the review equals the stored frames' sha set). A review of an empty map,
    of different bytes, or with any frame unreviewed / unjudged / blocked is not a review
    of this release (C-80 defect 7, Codex P06).
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == FRAME_REVIEW_ACTION,
                                              AuditLog.artifact == f"{slug}@{version}")
                       .order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail or {}) if row is not None else None
    if detail is None:
        return {"reviewed": False, "why": "no independent frame review is on record (#61)"}
    frames = detail.get("frames") or {}
    bad = {k: v.get("verdict") for k, v in frames.items() if v.get("verdict") != "clear"}
    if not frames:
        return {"reviewed": False, "not_clear": {}, "bound_to_stored_frames": False,
                "why": "the frame review on record judged no frames (#61): an empty review "
                       "is not a review"}
    reviewed_shas = {str(k): v for k, v in (detail.get("frame_shas") or {}).items()}
    stored = {str(f["position"]): f["sha256"] for f in _stored_frames(db, slug, version)}
    bound = bool(reviewed_shas) and bool(stored) and reviewed_shas == stored
    if not bound:
        why = ("the frame review on record is not bound to the frames now stored for this "
               "release (#61): " + ("it recorded no frame hashes" if not reviewed_shas else
                                    "no frames are stored" if not stored else
                                    "the stored frame bytes differ from the ones reviewed"))
        return {"reviewed": False, "not_clear": bad, "bound_to_stored_frames": False,
                "why": why}
    return {"reviewed": not bad, "not_clear": bad, "bound_to_stored_frames": True,
            "why": ("every stored frame was independently reviewed and communicates its claim"
                    if not bad else f"frames not independently cleared (#61): {bad}")}


def _stored_frames(db, slug: str, version: str) -> list[dict]:
    """The listing frames `assets.build` filed for this release, when the job carries none."""
    from sqlalchemy import select

    with db.session() as s:
        return [{"position": r.position, "role": r.role, "asset_class": r.asset_class,
                 "sha256": r.sha256}
                for r in s.scalars(select(ListingAsset).where(
                    ListingAsset.product_slug == slug, ListingAsset.version == version)
                    .order_by(ListingAsset.position))]


def _diversify_tags(db, slug: str, queries, tags: list[str]) -> tuple[list[str], dict]:
    """#240 applied: spend fewer slots on phrases other listings of ours already spend on.

    Re-chooses from the queries no other listing's tags already use, then tops up from the
    original choice so the listing never loses a slot. Kept only when it shares fewer
    phrases than the original; otherwise the original stands and the reading says so.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        others = {t.lower() for r in s.scalars(select(Listing).where(
            Listing.product_slug != slug)) for t in (r.tags or [])}
    shared_before = sorted(t for t in tags if t.lower() in others)
    reading = {"other_listing_tags": len(others), "shared_before": shared_before}
    if not others or not shared_before:
        return tags, {**reading, "shared_after": shared_before, "changed": False,
                      "why": ("no other listing's tags to diverge from" if not others
                              else "no tag is shared with another listing")}
    fresh = [q for q in queries if q.phrase.lower() not in others]
    diversified = search_mod.choose_tags(fresh)
    diversified = [t for t in diversified if t.lower() not in others]
    for t in tags:
        if len(diversified) >= len(tags):
            break
        if t not in diversified:
            diversified.append(t)
    shared_after = sorted(t for t in diversified if t.lower() in others)
    if len(shared_after) < len(shared_before) and len(diversified) >= len(tags):
        return diversified, {**reading, "shared_after": shared_after, "changed": True,
                             "why": (f"{len(shared_before) - len(shared_after)} slot(s) moved "
                                     f"off phrases another listing already competes for")}
    return tags, {**reading, "shared_after": shared_before, "changed": False,
                  "why": "no reachable alternative phrase; the original tags stand"}


ATTRIBUTION_KIND = "attribution.stats"


def _drop_vanity_tags(db, queries, tags: list[str]) -> tuple[list[str], dict]:
    """Swap tags the latest ingested Stats export shows as vanity terms (#237)."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == ATTRIBUTION_KIND)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        stats = dict(row.payload or {}) if row is not None else None
    if not stats:
        return tags, {"status": "UNMEASURED",
                      "why": "no Etsy Stats export has been ingested (/api/attribution/stats)"}
    vanity = {t.lower() for t in (stats.get("joined") or {}).get("vanity_terms") or []}
    earning = [t["term"] for t in (stats.get("joined") or {}).get("terms") or []
               if (t.get("contribution_per_visit_cad") or t.get("revenue_per_visit_cad"))]
    dropped = [t for t in tags if t.lower() in vanity]
    if not dropped:
        return tags, {"status": "measured", "vanity_dropped": [], "earning_terms": earning[:10],
                      "export": stats.get("period_key")}
    kept = [t for t in tags if t.lower() not in vanity]
    # #24: a freed slot goes first to a term the export shows earning per visit, and only then
    # to a phrase nothing has measured yet -- contribution economics, not impressions.
    refilled_from_earning = []
    for phrase in list(earning) + [q.phrase for q in queries]:
        if len(kept) >= len(tags):
            break
        if (phrase.lower() not in vanity and phrase.lower() not in {k.lower() for k in kept}
                and len(phrase) <= 20):
            kept.append(phrase)
            if phrase in earning:
                refilled_from_earning.append(phrase)
    return kept, {"status": "measured", "vanity_dropped": dropped, "earning_terms": earning[:10],
                  "refilled_from_earning": refilled_from_earning,
                  "export": stats.get("period_key"),
                  "why": (f"{len(dropped)} tag(s) were shown and never sold in the owner's "
                          f"Stats export; their slots went to terms that earned per visit "
                          f"first, then to unproven phrases")}


def _quote_screen(db, text: str) -> tuple[list[str], dict]:
    """#139: screen customer-facing copy against every protected token the radar declared.

    Routed by `culture.rights.route` with the basis recorded on the signal, and checked by
    `rights.check_direct_use` -- a protected phrase reaching copy through the original lane
    is refused. With no declared tokens the screen ran and found nothing to look for, which
    is reported as such rather than as clearance.
    """
    from sqlalchemy import select

    from ..core.models import CultureSignal
    from ..culture import rights

    with db.session() as s:
        signals = [(r.key, list(r.protected_tokens or []), r.basis)
                   for r in s.scalars(select(CultureSignal))]
    problems: list[str] = []
    screened, quote_classes = 0, {rights.DIALOGUE, rights.LYRIC, rights.SLOGAN}
    quotes = 0
    for key, raw_tokens, raw_basis in signals:
        tokens = []
        for t in raw_tokens:
            try:
                tokens.append(rights.ProtectedToken(text=str(t.get("text") or ""),
                                                    asset_class=str(t.get("asset_class") or ""),
                                                    source=str(t.get("source") or "")))
            except rights.RightsRefused as exc:
                problems.append(f"RIGHTS_UNREADABLE_TOKEN: signal {key}: {exc}"[:300])
        if not tokens:
            continue
        screened += len(tokens)
        quotes += sum(1 for t in tokens if t.asset_class in quote_classes)
        basis = None
        if raw_basis:
            try:
                basis = rights.Basis(**{k: raw_basis[k] for k in (
                    "kind", "evidence", "recorded_by", "recorded_on", "scope")
                    if k in raw_basis})
            except TypeError:
                basis = None
        routing = rights.route(tokens, basis=basis)
        try:
            rights.check_direct_use(routing, product_or_copy=text)
        except rights.RightsRefused as exc:
            problems.append(f"RIGHTS_DIRECT_USE: signal {key}: {exc}"[:400])
    return problems, {"signals": len(signals), "tokens_screened": screened,
                      "quote_catchphrase_tokens": quotes, "refused": len(problems),
                      "note": ("no protected token has been declared by the radar, so the "
                               "screen had nothing to look for" if not screened else "")}


# ---- swarm stewardship and experiment registration -------------------------------------
#
# Thin handlers over `swarm.orchestrate` and `growth.experiments`, placed beside the listing
# stage because the experiment pack is what a drafted listing launches with. All GREEN: they
# read the database, write recommendations and records, reassign only pending work to agents
# that already hold the permission, and enqueue only non-spending GREEN work.


@handlers.register("swarm.review")
def handle_swarm_review(ctx: JobContext) -> dict:
    """#174: every agent's quality metric, read from job outcomes, against its retirement
    condition. Recommends; never disables."""
    from ..swarm.orchestrate import agent_quality

    out = agent_quality(ctx.db)
    ctx.audit("swarm.agent_review", detail={
        "retire": out["retire"], "merge": out["merge"], "watch": out["watch"],
        "unmeasured": len(out["unmeasured"]), "agents": len(out["agents"])})
    return out


@handlers.register("swarm.allocate")
def handle_swarm_allocate(ctx: JobContext) -> dict:
    """#175: fan-out per lane, bounded by `work_that_fits`, recorded and then acted on by
    the idle backlog. Raises no ceiling and spends nothing."""
    from ..swarm.orchestrate import allocate

    out = allocate(ctx.db)
    ctx.audit("swarm.allocation", detail={k: v for k, v in out.items() if k != "lanes"})
    return {k: v for k, v in out.items() if k != "lanes"}


@handlers.register("swarm.orphans")
def handle_swarm_orphans(ctx: JobContext) -> dict:
    """#176: work items from jobs, incidents and improvements; unowned work is reassigned
    or raised as an incident with its evidence."""
    from ..swarm.orchestrate import resolve_orphans

    out = resolve_orphans(ctx.db)
    for moved in out["reassigned"]:
        ctx.audit("swarm.reassigned", artifact=f"job:{moved['ref']}", detail=moved)
    ctx.audit("swarm.orphans", detail={
        "work_items": out["work_items"], "orphans": len(out["orphans"]),
        "reassigned": len(out["reassigned"]),
        "incident_owners_assigned": len(out["incident_owners_assigned"]),
        "surfaced": len(out["surfaced_as_incident"])})
    return out


@handlers.register("swarm.backlog")
def handle_swarm_backlog(ctx: JobContext) -> dict:
    """#186: when the queue is idle, enqueue the highest-value standing items the latest
    allocation allows. Idempotent per window, bounded, GREEN-only, non-spending."""
    from ..swarm.orchestrate import feed_idle

    out = feed_idle(ctx.db, ctx.queue)
    ctx.audit("swarm.backlog", detail={"idle": out["idle"],
                                       "enqueued": [e["job_type"] for e in out["enqueued"]],
                                       "skipped": len(out.get("skipped", []))})
    return out


@handlers.register("growth.experiments")
def handle_growth_experiments(ctx: JobContext) -> dict:
    """#241, #265: every drafted listing launches with a persisted, pre-registered pack.

    With `slug` and `price_cad` in the inputs it registers that product; without, it
    registers every drafted listing that has none. Registration is write-once, so re-running
    is free and cannot move a threshold after the fact.
    """
    from sqlalchemy import select

    from ..core.models import Listing
    from ..growth.experiments import register_launch

    i = dict(ctx.job.inputs or {})
    if i.get("slug"):
        targets = [(i["slug"], float(i.get("price_cad") or 0.0))]
    else:
        with ctx.db.session() as s:
            targets = sorted({(r.product_slug, float(r.price_cad or 0.0))
                              for r in s.scalars(select(Listing))})
    results = [register_launch(ctx.db, product=slug, price_cad=price)
               for slug, price in targets]
    created = sum(r["created"] for r in results)
    ctx.audit("growth.experiments_registered", detail={
        "products": len(results), "created": created,
        "killed": [k for r in results for k in r["killed"]],
        "gated": sum(len(r["gated"]) for r in results)})
    return {"products": len(results), "created": created, "results": results}

def _lineage(ctx: JobContext, **overrides):
    """Who is making this artefact, from the job that is making it (#171).

    The agent, the job, the running commit and the phase are all known at the moment of the
    write, and nowhere else afterwards: the production estate had 275 artefacts whose maker
    could not be named because nothing wrote it down at the time.
    """
    from ..ops import artefacts as provenance

    fields = dict(created_by=ctx.job.agent, job_id=ctx.job.id,
                  publication_authority=ctx.phase.value if ctx.phase else "shadow")
    fields.update(overrides)
    return provenance.Lineage(**fields)


def _content_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


def _persist_listing(ctx: JobContext, slug: str, version: str, copy, share: float,
                     release: str = "") -> None:
    """Drafted, never published. Shadow mode holds the whole shop ready rather than open."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ..ops import artefacts as provenance

    with ctx.db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is None:
            row = Listing(product_slug=slug, version=version)
            s.add(row)
        row.title = copy.title
        row.description = copy.description
        row.tags = list(copy.tags)
        row.price_cad = copy.price_cad
        row.seo_score = share
        row.state = "draft"
        row.chain_version = CHAIN_VERSION
        row.release_hash = release or ""
        s.flush()

        # Three derived artefacts live on this one row -- the words, the tags and the price
        # -- and each is recorded against the stored release so a redesign under the same
        # slug turns all three stale rather than leaving a current-looking listing (#171).
        key = provenance.release_key(slug, version)
        design = provenance.design_inputs(s, slug, version)
        lineage = _lineage(ctx, validation_status="passed")
        certificate_ref = f"certificate:{key}"
        provenance.record_lineage(
            s, artefact_class="listing_copy", artefact_key=key, product_slug=slug,
            inputs=design, chain_version=CHAIN_VERSION,
            lineage=lineage.for_file(_content_hash(copy.title, copy.description))
                           .under(certificate_ref))
        provenance.record_lineage(
            s, artefact_class="seo", artefact_key=key, product_slug=slug,
            inputs=design, chain_version=CHAIN_VERSION,
            lineage=lineage.for_file(_content_hash(copy.title, *sorted(copy.tags)))
                           .under(f"listing_copy:{key}"))
        if (copy.price_cad or 0) > 0:
            provenance.record_lineage(
                s, artefact_class="pricing", artefact_key=key, product_slug=slug,
                inputs=design, chain_version=CHAIN_VERSION,
                lineage=lineage.under(certificate_ref))


@handlers.register("launch.plan")
def handle_launch_plan(ctx: JobContext) -> dict:
    i = dict(ctx.job.inputs)
    slug = i["slug"]
    seed = _seed_for(slug)
    today = (date.fromisoformat(i["as_of"]) if i.get("as_of") else date.today())

    window = None
    if seed and seed.season:
        base = _event(seed.season)
        if base is not None:
            from ..radar.market import SeasonalEvent

            scoped = SeasonalEvent(base.name, base.event_date, seed.maker_hours,
                                   base.gift_lead_days)
            window = shopping_window(scoped)

    plan = launch_mod.plan_launch(slug, today=today, window=window,
                                  build_lead_days=seed.build_lead_days if seed else 7)
    ctx.audit("launch.planned", artifact=slug, detail={
        "launch_on": plan.launch_on.isoformat(), "compressed": plan.compressed,
        "warnings": plan.warnings[:3]})

    i["launch"] = plan.to_dict()

    # #297: finished engineering is not a reason to launch under a seasonal premise the
    # customer can no longer meet. The same decision the seasonal sentinel audits, enforced
    # here: a missed window neither schedules seasonal marketing nor queues publication, and
    # the decision (pivot / simplify / hold) is recorded with its reason.
    from ..publish.release_gates import window_decision

    decision = window_decision(ctx.db, slug=slug, version=i["version"], today=today,
                               positioning=i.get("positioning"))
    i["window_decision"] = decision
    if not decision["may_launch_seasonally"]:
        ctx.audit("launch.held", artifact=f"{slug}@{i['version']}", detail=decision)
        # #297: when the decision is a pivot, carry it out -- the copy is rewritten as
        # evergreen, which comes back here with the pivot applied -- rather than leaving the
        # product held with the recommendation written down and nobody acting on it.
        from ..seasonal import leadtime as _lt

        if decision.get("action") == _lt.PIVOT_EVERGREEN and not decision.get("pivot_applied"):
            ctx.enqueue("listing", "listing.seo", {**i, "positioning": "evergreen"},
                        idempotency_key=chain_key("seo", slug, i["version"],
                                                  i.get("release", ""),
                                                  i.get("rebuild", "") + ":evergreen"))
            ctx.audit("launch.pivot_queued", artifact=f"{slug}@{i['version']}",
                      detail={"why": decision.get("why"), "occasion": decision.get("occasion")})
        out = plan.to_dict()
        out.update({"held": True, "window_decision": decision})
        return out

    # #66: the listing set as a shopper meets it, rendered in its four contexts and the
    # renders stored, here -- the QA stage -- so store.publish can verify them without
    # writing storage ahead of its Shadow Mode refusal.
    from ..publish.release_gates import listing_set as _listing_set_qa

    try:
        qa = _listing_set_qa(ctx.db, slug=slug, version=i["version"], issue=False,
                             store_root=i.get("artifact_dir"), store_renders=True)
        ctx.audit("listing.mobile_qa", artifact=f"{slug}@{i['version']}",
                  detail={"mobile": qa.get("mobile"), "blocks_release": qa["blocks_release"],
                          "reasons": qa["reasons"][:5]})
    except Exception as e:  # noqa: BLE001 - QA that crashed is unrendered, and publish says so
        ctx.audit("listing.mobile_qa", artifact=f"{slug}@{i['version']}",
                  detail={"error": f"{type(e).__name__}: {str(e)[:300]}"})

    # F-003: ranking readiness, read after the QA above so the click dimension sees this
    # release's listing-set reading. Five independent dimensions, each MEASURED or UNMEASURED,
    # recorded with the plan and never blended into one score.
    from ..commerce import ranking_readiness

    try:
        ranking = ranking_readiness.profile(ctx.db, slug, i["version"])
        ranking_summary = ranking_readiness.summary(ranking)
        ctx.audit("launch.ranking_readiness", artifact=f"{slug}@{i['version']}",
                  detail={"dimensions": ranking_summary,
                          "unmeasured": ranking["unmeasured"], "failing": ranking["failing"],
                          "search_certificate": ranking["search_certificate"]["verdict"]})
    except Exception as e:  # noqa: BLE001 - an unread profile is unmeasured, and says so
        ranking_summary = {d: "UNMEASURED" for d in ranking_readiness.DIMENSIONS}
        ctx.audit("launch.ranking_readiness", artifact=f"{slug}@{i['version']}",
                  detail={"error": f"{type(e).__name__}: {str(e)[:300]}"})

    # #241: every launch ships with its pre-registered experiment pack (hero variants, title
    # and tag strategy, confounder log), registered here at launch, write-once. The
    # growth.experiments cadence remains the backstop for anything launched before this.
    from ..growth.experiments import register_at_launch

    try:
        registered = register_at_launch(ctx.db, product=slug)
        ctx.audit("growth.experiments_registered", artifact=f"{slug}@{i['version']}",
                  detail={"created": registered.get("created"),
                          "experiments": [e.get("key") for e in
                                          registered.get("experiments", [])][:12]})
    except Exception as e:  # noqa: BLE001 - a pack that failed to register is audited, not silent
        ctx.audit("growth.experiments_unregistered", artifact=f"{slug}@{i['version']}",
                  detail={"error": f"{type(e).__name__}: {str(e)[:300]}"})

    # C-69 (#171): the release bundle -- everything this release ships together -- recorded
    # as its own derived artefact, over the rows of its members, so a CIR change invalidates
    # the bundle as a whole and not only its parts.
    _record_release_bundle(ctx, slug, i["version"])

    # #163 / #169 (C-69): the teardown QA again, now that the product's artefacts exist -- the
    # advantages its support knowledge evidences are compared with the purchased benchmarks
    # and its delight mechanisms are measured from its files. A parity-only product is
    # withheld here exactly as at certification: no content, no publication.
    from ..teardown import lab as teardown_lab
    from .pipeline import _mark_withheld

    seed_ = _seed_for(slug)
    qa_ = teardown_lab.product_qa(ctx.db, slug,
                                  product_class=(seed_.category if seed_ else ""))
    if qa_.get("blocks_release"):
        reason = "teardown QA (#163): " + str(qa_["unique_value"].get("reason", ""))[:300]
        _mark_withheld(ctx, _load_cir(ctx, slug, i["version"]), reason)
        ctx.audit("gate.release_withheld", artifact=f"{slug}@{i['version']}",
                  detail={"reason": reason, "stage": "launch.plan"})
        out = plan.to_dict()
        out.update({"withheld": reason, "window_decision": decision})
        return out

    publish_inputs = {"slug": slug, "version": i["version"]}
    for carried in ("as_of", "positioning"):
        if i.get(carried):
            publish_inputs[carried] = i[carried]
    ctx.enqueue("growth", "marketing.schedule", i,
                idempotency_key=chain_key("content", slug, i["version"],
                                          i.get("release", ""), i.get("rebuild", "")))
    ctx.enqueue("store_operator", "store.publish", publish_inputs,
                idempotency_key=chain_key("publish", slug, i["version"],
                                          i.get("release", ""), i.get("rebuild", "")))
    out = plan.to_dict()
    out["window_decision"] = decision
    out["ranking_readiness"] = ranking_summary
    return out


BUNDLE_MEMBER_CLASSES = ("certificate", "pdf", "chart", "visual_truth", "listing_copy", "seo",
                         "pricing", "support_knowledge")


def _record_release_bundle(ctx: JobContext, slug: str, version: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance
    from ..ops import artefacts as provenance

    key = provenance.release_key(slug, version)
    with ctx.db.session() as s:
        members = sorted(
            (r.artefact_class, r.artefact_key, r.sha256 or provenance.fingerprint(r.inputs))
            for r in s.scalars(select(ArtefactProvenance).where(
                ArtefactProvenance.product_slug == slug,
                ArtefactProvenance.artefact_class.in_(BUNDLE_MEMBER_CLASSES)))
            if r.artefact_key == key or r.artefact_key.startswith(key + "#"))
        if not members:
            return None
        design = provenance.design_inputs(s, slug, version)
        manifest = provenance.fingerprint([list(m) for m in members])
        provenance.record_lineage(
            s, artefact_class="release_bundle", artefact_key=f"{key}#bundle",
            product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
            lineage=_lineage(ctx, validation_status="passed",
                             evidence={"manifest": manifest, "members": len(members)})
            .under(*[f"{c}:{k}" for c, k, _ in members]))
    return {"manifest": manifest, "members": len(members)}


@handlers.register("marketing.schedule")
def handle_marketing_schedule(ctx: JobContext) -> dict:
    """Draft the product's content ecosystem and hold it (section 11).

    Nothing is scheduled to publish itself. There is no Pinterest, email, video or social
    integration in this system, and shadow mode means the plan is built and reviewable before
    any account exists rather than after.
    """
    from ..core.models import ContentPiece
    from ..growth import content as content_mod

    i = dict(ctx.job.inputs)
    slug, version = i["slug"], i["version"]
    seed = _seed_for(slug)
    listing = i.get("listing") or {}
    launch_on = date.fromisoformat(i["launch"]["launch_on"])

    # #173 and #297 before anything is scheduled: a product with an open publication-halting
    # incident (the stale-artefact sentinel raises one), a descendant still built from a
    # moved input, or a missed seasonal window gets no content drafted under that premise.
    # An audited, reasoned block; nothing is written.
    from ..publish.release_gates import for_marketing

    gate = for_marketing(ctx.db, slug=slug, version=version,
                         today=date.fromisoformat(i["as_of"]) if i.get("as_of") else None,
                         positioning=i.get("positioning"))
    outstanding = list(gate["staleness"]["rebuild"]["outstanding"] or [])
    if gate["blocks"] and i.get("rebuild") and gate.get("only_own_marketing_stale"):
        # C-69: the only thing outstanding is the content this rebuild exists to remake.
        # Blocking it on its own staleness would make a stale marketing asset unrebuildable.
        # C-80 defect 11: read from the gate's structured flag, not from reason wording.
        gate = {**gate, "blocks": False, "reasons": [],
                "rebuilding": outstanding}
    if gate["blocks"]:
        ctx.audit("marketing.blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": gate["reasons"][:5], "published": False,
                          "window": gate["window"],
                          "halted": gate["staleness"]["halted"],
                          "rebuild_outstanding": gate["staleness"]["rebuild"]["outstanding"][:10]})
        return {"slug": slug, "version": version, "pieces": 0, "blocked": True,
                "problems": gate["reasons"], "published": False}

    cir = _load_cir(ctx, slug, version)
    twin = build_twin(cir, compile_cir(cir),
                      calibration=calibration_from_db(ctx.db, cir))
    tol = twin.yardage_tolerance
    yardage_line = "; ".join(
        f"{name} about {m * (1 - tol):.0f}-{m * (1 + tol):.0f} m"
        for name, m in sorted(twin.yarn_metres_by_color.items())) or "see the pattern"

    record = _product_record(slug, i)
    if record is None:
        why = f"{UNKNOWN_PRODUCT}: no product record names what {slug} is"
        ctx.audit("marketing.blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": [why], "published": False})
        return {"slug": slug, "version": version, "pieces": 0, "blocked": True,
                "problems": [why], "published": False}
    facts = content_mod.ProductFacts(
        slug=slug, title=cir.title,
        category=(record["category"] if record["launch0"]
                  else (i.get("category") or record["category"])),
        size_label=i.get("size_label"),
        difficulty=_difficulty(twin, cir),
        stitches=sorted(twin.stitch_types_used),
        colors=sorted(c for c in twin.colors_used if c),
        yardage_line=yardage_line,
        maker_hours=seed.maker_hours if seed else (4.0, 12.0),
        season=seed.season if seed else None,
        price_cad=float(listing.get("price_cad") or i.get("price_cad") or 0.0),
        siblings=_collection_siblings(slug))

    pieces = content_mod.build_ecosystem(facts, launch_on=launch_on)
    problems = content_mod.check_ecosystem(pieces, facts)

    with ctx.db.session() as s:
        from sqlalchemy import select

        from ..ops import artefacts as provenance

        design = provenance.design_inputs(s, slug, version)
        lineage = _lineage(ctx, validation_status="blocked" if problems else "passed")
        listing_ref = f"listing_copy:{provenance.release_key(slug, version)}"
        for piece in pieces:
            existing = s.scalar(select(ContentPiece).where(
                ContentPiece.product_slug == slug,
                ContentPiece.channel == piece.channel,
                ContentPiece.title == piece.title))
            if existing is not None and not i.get("rebuild"):
                # Written by an earlier run under inputs this run cannot vouch for. Its
                # lineage is the backfill's to derive from that run's evidence, or it
                # stays unproven; recording it here would be a lineage nobody had.
                continue
            if existing is not None:
                # C-69 (#172): a rebuild remakes the piece from the current release -- this
                # run wrote these words, so it records their lineage.
                existing.body = piece.body
                existing.detail = piece.detail
                existing.scheduled_for = piece.scheduled_for
                provenance.record_lineage(
                    s, artefact_class="marketing_asset",
                    artefact_key=provenance.marketing_key(slug, piece.channel, piece.title),
                    product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
                    lineage=lineage.for_file(_content_hash(piece.title, piece.body))
                                   .under(listing_ref))
                continue
            s.add(ContentPiece(product_slug=slug, channel=piece.channel, title=piece.title,
                               body=piece.body, scheduled_for=piece.scheduled_for,
                               state="drafted", detail=piece.detail))
            provenance.record_lineage(
                s, artefact_class="marketing_asset",
                artefact_key=provenance.marketing_key(slug, piece.channel, piece.title),
                product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
                lineage=lineage.for_file(_content_hash(piece.title, piece.body))
                               .under(listing_ref))

    ctx.audit("marketing.scheduled" if not problems else "marketing.blocked",
              artifact=f"{slug}@{version}",
              detail={"pieces": len(pieces), "channels": sorted({p.channel for p in pieces}),
                      "problems": problems[:5], "published": False})
    return {"slug": slug, "version": version, "pieces": len(pieces),
            "problems": problems, "published": False}


@handlers.register("support.reply")
def handle_support_reply(ctx: JobContext) -> dict:
    """Triage a customer message and draft a reply from the exact released version.

    The version is an input, not a lookup of "the current one". A customer who bought 1.0.0
    must be answered from 1.0.0; answering from 1.1.0 because it happens to be newer is how a
    support system tells someone their correct work is wrong.

    Nothing is sent. There is no messaging integration, and the case is recorded as unsent
    rather than relying on that absence.
    """
    from ..support.department import CustomerExperience

    # A reply enqueued by the triage cadence names the stored case it drafts for, and the
    # draft is written onto that case rather than beside it (#41).
    case_id = ctx.job.inputs.get("case_id")
    slug = ctx.job.inputs.get("slug")
    version = ctx.job.inputs.get("version")
    question = ctx.job.inputs.get("question")
    customer = ctx.job.inputs.get("customer_ref", "unknown")
    if case_id is not None:
        from ..core.models import SupportCase

        with ctx.db.session() as s:
            case = s.get(SupportCase, int(case_id))
            if case is None:
                raise ValueError(f"support.reply names case {case_id}, which does not exist")
            question = question or case.question
            slug = slug or case.product_slug
            version = version or case.version
            customer = case.customer_ref or customer
    if not question:
        raise ValueError("support.reply needs a question or a stored case to draft for")

    cir = _load_cir(ctx, slug, version) if slug and version else None
    reply = CustomerExperience(ctx.db).handle(
        customer_ref=customer, message=question, cir=cir,
        product_slug=slug, version=version,
        case_id=int(case_id) if case_id is not None else None)

    # #257: the anti-gating guard reads every draft before it can go anywhere, and #18: the
    # case records how long the answer took. Both act on the case itself.
    checked = _check_and_time_reply(ctx, case_id=case_id, customer=customer,
                                    question=question, reply=reply)
    ctx.audit("support.replied", artifact=f"{slug}@{version}" if slug else None,
              detail={"specialist": reply.specialist, "escalated": reply.escalated,
                      "sent": reply.sent, "case_id": checked["case_id"],
                      "copy_ok": checked["copy"]["ok"],
                      "response_minutes": checked["timing"].get("minutes")})
    out = {**reply.to_dict(), "case_id": checked["case_id"],
           "copy_check": checked["copy"], "timing": checked["timing"]}
    if not checked["copy"]["ok"]:
        out["body"] = ""
        out["escalated"] = True
    return out


def _check_and_time_reply(ctx: JobContext, *, case_id, customer: str, question: str,
                          reply) -> dict:
    """Refuse a draft that gates a review (#257) and time the case (#18).

    A draft carrying one of `reviews.GATING_PHRASES` is not held for sending: its body is
    removed from the case and the case is escalated to a person with the phrase named, since
    a support answer the buyer was owed may never carry a request for a rating. The response
    time is recorded on the case -- as `draft_ready` while shadow mode holds every reply,
    because a held draft is not a response anybody received.
    """
    from datetime import datetime, timezone

    from sqlalchemy import desc, select

    from ..commerce.reviews import check_support_copy
    from ..core.models import SupportCase
    from ..support import service

    copy = check_support_copy(reply.body or "")
    with ctx.db.session() as s:
        if case_id is not None:
            case = s.get(SupportCase, int(case_id))
        else:
            case = s.scalar(select(SupportCase).where(
                SupportCase.customer_ref == customer, SupportCase.question == question)
                .order_by(desc(SupportCase.id)).limit(1))
        if case is None:
            return {"case_id": case_id, "copy": copy,
                    "timing": {"recorded": False, "why": "no stored case to time"}}
        cid = int(case.id)
        at = case.at if case.at.tzinfo else case.at.replace(tzinfo=timezone.utc)
        # A draft timing does not block the later sent timing (Codex CB2-G08); a sent one,
        # or a second draft, is already recorded.
        prior = dict(case.detail or {})
        already = "response_minutes" in prior and (
            prior.get("response_measured_as", "sent") == "sent" or not reply.sent)
        if not copy["ok"]:
            case.answer = ""
            case.escalated = True
            case.resolved = False
            case.detail = {**dict(case.detail or {}), "draft_refused": copy["found"],
                           "escalation_reason": ("the draft asked for a rating attached to "
                                                 "support the buyer was owed")}
    minutes = max(0.0, (datetime.now(timezone.utc) - at).total_seconds() / 60.0)
    if already:
        timing = {"recorded": False, "why": "this case's response time is already recorded"}
    else:
        timing = {"recorded": True, **service.record_response(
            ctx.db, cid, minutes=round(minutes, 2), from_canonical=not reply.escalated,
            measured_as="sent" if reply.sent else "draft_ready")}
    if not copy["ok"]:
        ctx.audit("support.draft_refused", artifact=f"case:{cid}",
                  detail={"found": copy["found"], "why": copy["why"]})
    return {"case_id": cid, "copy": copy, "timing": timing}


@handlers.register("support.triage")
def handle_support_triage(ctx: JobContext) -> dict:
    """Triage stored cases, enqueue a draft for each that needs one, and mine for defects.

    The cadence #41 lacked (C-42): `support.reply` was registered and nothing ever enqueued
    it. Triage classifies every stored case once -- including whether the buyer was confused
    about buying a digital pattern -- and enqueues one `support.reply` per case with nothing
    drafted, keyed on the case. Replies stay drafts in shadow mode; nothing is sent to anyone.
    Confusion is then counted from those triage runs, UNMEASURED as a rate until there are
    orders, and each open case's deadline stays UNKNOWN unless a policy reading states the
    case window in days.
    """
    from ..support.department import CustomerExperience

    dept = CustomerExperience(ctx.db)
    triaged = dept.triage_cases(ctx.queue)
    out = dept.mine_cases(ctx.job.inputs.get("slug"))
    out["triage"] = {k: triaged[k] for k in ("triaged", "reply_jobs", "awaiting_draft",
                                            "needing_reply", "sent")}
    out["confusion"] = triaged["confusion"]
    out["case_window"] = triaged["case_window"]
    # F-043: the first-response clock. Every recorded buyer message with no reply recorded
    # as sent raises an owner action + incident at 24h and escalates at 36h, before Etsy's
    # 48h standard; a recorded reply closes both. Audited either way.
    from ..support import response_watch

    out["response_watch"] = response_watch.watch(ctx.db)
    ctx.audit("support.response_watch", detail={
        k: out["response_watch"][k] for k in ("watching", "raised", "escalated", "breached",
                                               "closed", "thresholds_hours")})
    # #155 / #158: Pattern Help consumes the teardown traps -- an open case about one is
    # routed to the pattern_help specialist with the obligation on it.
    from ..teardown import enforce as teardown_enforce

    out["pattern_help"] = teardown_enforce.apply_pattern_help(ctx.db)
    # #97: Support reads its lesson inbox. A lesson matching an open case's question is
    # attached to the case (support tracks whether it reduces confusion) and acted on.
    from sqlalchemy import select as _select

    from ..core.models import SupportCase as _Case
    from ..improve import consume

    lessons_used = []
    with ctx.db.session() as s:
        cases = [(c.id, c.question or "", list((c.detail or {}).get("lessons") or []))
                 for c in s.scalars(_select(_Case).where(_Case.resolved.is_(False)))]
    for case_id, question, have in cases:
        hits = [l for l in consume.matching(ctx.db, "customer_experience", question,
                                            min_shared=1,
                                            # W-B1: log the decision so its outcome can
                                            # be attributed (lane B policy loops).
                                            subject=f"support_case:{case_id}")
                if l["id"] not in have]
        if not hits:
            continue
        with ctx.db.session() as s:
            case = s.get(_Case, case_id)
            case.detail = {**(case.detail or {}),
                           "lessons": have + [l["id"] for l in hits]}
        consume.act(ctx.db, "customer_experience", hits,
                    how=f"attached to support case {case_id} to track whether it reduces "
                        f"confusion")
        lessons_used.append({"case": case_id, "lessons": [l["id"] for l in hits]})
    out["lessons_used"] = lessons_used
    ctx.audit("support.mined", detail={"cases": out["cases"],
                                       "hotspots": out["row_hotspots"][:5],
                                       "triaged": len(triaged["triaged"]),
                                       "reply_jobs": triaged["reply_jobs"],
                                       "confusion": triaged["confusion"],
                                       "case_window_known": bool(
                                           triaged["case_window"].get("known")),
                                       "sent": 0})
    for hotspot in out["row_hotspots"]:
        if hotspot["mentions"] >= 3:
            ctx.audit("support.defect_candidate", artifact=hotspot["product"],
                      detail=hotspot)
    return out


def _collection_siblings(slug: str) -> list[str]:
    """Other products in this product's family, for the cross-sell frame."""
    seed = _seed_for(slug)
    if seed is None or not seed.family:
        return []
    return [m.title for m in POOL
            if m.family == seed.family and m.slug != seed.slug and not m.is_bundle][:4]


def _persist_frames(ctx: JobContext, slug: str, version: str, frames, stored, blocking):
    """Record the frame plan so a later session can see what a listing was going to show."""
    from sqlalchemy import select

    reasons = list(blocking)
    # #228: the owner's veto over flagship creative quality holds at the asset gate too.
    from ..intel.mission_runtime import active_veto

    veto = active_veto(ctx.db, slug)
    if veto["vetoed"]:
        reasons.append(f"owner veto (#228): {veto['why']}")
    with ctx.db.session() as s:
        for frame, meta in zip(frames, stored):
            row = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version,
                ListingAsset.position == frame.position))
            if row is None:
                row = ListingAsset(product_slug=slug, version=version,
                                   position=frame.position)
                s.add(row)
            row.asset_class = frame.asset_class.value
            row.role = frame.role
            row.sha256 = meta["sha256"]
            row.claims = {"width_cm": frame.claims.finished_width_cm,
                          "height_cm": frame.claims.finished_height_cm,
                          "difficulty": frame.claims.difficulty,
                          "colors": list(frame.claims.colors)}
            row.approved = not reasons
            row.blocked_reasons = reasons[:10]
        s.flush()

        # One visual-truth row per frame, keyed by the frame's own row id and carrying the
        # rendered file's hash, so a frame that outlives its design is found by the same
        # sweep that finds a stale PDF (#171).
        from ..ops import artefacts as provenance

        design = provenance.design_inputs(s, slug, version)
        lineage = _lineage(ctx, validation_status="blocked" if reasons else "passed")
        certificate_ref = f"certificate:{provenance.release_key(slug, version)}"
        for frame in frames:
            row = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version,
                ListingAsset.position == frame.position))
            provenance.record_lineage(
                s, artefact_class="visual_truth",
                artefact_key=provenance.visual_key(slug, version, row.id),
                product_slug=slug, inputs=design, chain_version=CHAIN_VERSION,
                lineage=lineage.for_file(row.sha256).under(certificate_ref))


def _motifs_for(slug: str) -> list[str]:
    words = [w for w in slug.replace("_", "-").split("-")
             if w not in {"mosaic", "pattern", "concept", "throw", "blanket", "set",
                          "trio", "pair", "library", "bundle"} and not w.isdigit()]
    return words[:3]


def _difficulty(twin, cir) -> str:
    """What the listing claims, from the same ladder the PDF cover prints.

    This was its own copy of the arithmetic, including its own copy of the literal set of
    "advanced" stitches, and so was `publish/pdf.py`, and so was the gate that blocks an
    unsupported difficulty claim. Three copies written before the texture stitches existed
    agreed with each other that a cabled throw was beginner work. See `publish/difficulty`.
    """
    from ..publish.difficulty import difficulty

    return difficulty(cir, twin)


def enqueue_member_collections(ctx: JobContext, member_slug: str, release_hash: str) -> list[str]:
    """A member certified: give every collection it belongs to one assembly attempt.

    Collections assemble on their members' certification rather than by polling. The polling
    version (C-46 fallout) re-queued a waiting bundle outside every priority band (C-73) and,
    once put back inside its band, burned its bounded retries before the members' chains
    finished. An event cannot run early: this fires only when there is something new to
    assemble from, keyed on the member's release so a re-run of the same certificate adds
    nothing.
    """
    seed = _seed_for(member_slug)
    if seed is None or seed.is_bundle or not seed.family:
        return []
    started = []
    for bundle in POOL:
        if not bundle.is_bundle or bundle.family != seed.family:
            continue
        job = ctx.enqueue("listing", "collection.assemble",
                          {"slug": bundle.slug, "family": bundle.family,
                           "trigger": {"member": member_slug, "release": release_hash}},
                          idempotency_key=(chain_key("collection", bundle.slug, "collection")
                                           + f":member:{member_slug}:{(release_hash or '')[:16]}"))
        if job is not None:
            started.append(bundle.slug)
    return started


@handlers.register("collection.assemble")
def handle_collection_assemble(ctx: JobContext) -> dict:
    """Build a collection listing out of its members' real, certified releases.

    A bundle has no pattern of its own, so it has nothing to compile, nothing to reverse
    compile and nothing to render a chart from. What it has is members — and it may only be
    listed once every one of them has a certificate, because a bundle is a promise to deliver
    each of those patterns.

    When the members are not ready yet it waits rather than assembling a partial collection:
    it completes with a recorded `waiting` result, and each member's certification enqueues
    the assembly again (`enqueue_member_collections`). The bundle is not broken, it is early --
    and a retry budget spent in six seconds made it look broken (it went DEAD).
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..core.models import Collection, Listing, PatternVersion, Product
    from ..brand import bible

    slug = ctx.job.inputs["slug"]
    family = ctx.job.inputs.get("family")
    seed = _seed_for(slug)
    members = [m for m in POOL if m.family == family and not m.is_bundle]
    if not members:
        raise ValueError(f"{slug}: a bundle with no members cannot be assembled")

    with ctx.db.session() as s:
        certified: list[tuple[str, str]] = []
        for m in members:
            product = s.scalar(select(Product).where(Product.slug == m.slug))
            if product is None:
                continue
            pv = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id,
                PatternVersion.certified == True))  # noqa: E712
            if pv is not None:
                certified.append((m.slug, pv.version))

    # The collection is the members that actually shipped, not every concept in the family.
    # The pool holds more Nordic Forest concepts than the portfolio selected, and a bundle
    # advertising a stocking nobody engineered would be a promise we cannot keep. Two is the
    # floor: one pattern is not a collection.
    ready = {c[0] for c in certified}
    members = [m for m in members if m.slug in ready]
    if len(members) < 2:
        # An honest wait, not a death. Under band priority (C-46) this job can be claimed
        # before its members' certification jobs; raising here spent three retries in six
        # seconds and dead-lettered a bundle that was merely early. It completes as waiting
        # and does not re-queue itself: each member's gate.certify enqueues the assembly
        # again (`enqueue_member_collections`), so the next attempt comes exactly when there
        # is a new member to assemble from, and `chain.rebuild` remains the path for a rebuild.
        waiting = sorted(ready)
        detail = {"certified_members": waiting, "requeued": False,
                  "reassembles_on": "gate.certify of a member"}
        ctx.audit("collection.waiting", artifact=slug, detail=detail)
        return {"slug": slug, "waiting": True, **detail,
                "why": (f"only {len(members)} of {slug}'s patterns are certified. A bundle is "
                        f"a promise to deliver each of its patterns, so it waits for them")}

    prices = [m.price_cad for m in members]
    verdict = pricing_mod_intel.price_bundle(prices)

    # #289: the collection architecture's own test, on the members' concepts. A collection
    # must share a palette and story, differ structurally and span more than one price
    # point; the assessment is recorded with the listing rather than trusted to the name.
    architecture = _collection_architecture(slug, seed, [m.slug for m in members])
    ctx.audit("collection.assessed", artifact=slug, detail=architecture)
    # C-60 (#289): the assessment blocks. An incoherent collection -- no shared story, a
    # derivative pair, one price point, too few members -- is not drafted as a listing, and a
    # draft already on file for it is withdrawn. `chain.rebuild` re-runs this job, so the
    # collection is drafted on the day its members make it coherent.
    if not architecture.get("coherent"):
        with ctx.db.session() as s:
            stale = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                   Listing.version == "collection"))
            withdrawn = False
            if stale is not None and stale.state != "withdrawn":
                stale.state = "withdrawn"
                withdrawn = True
        ctx.audit("collection.refused", artifact=slug, detail={
            "problems": architecture.get("problems"), "withdrawn_draft": withdrawn,
            "members": [m.slug for m in members]})
        return {"slug": slug, "refused": True, "drafted": False,
                "members": [m.slug for m in members], "withdrawn_draft": withdrawn,
                "architecture": {k: architecture.get(k) for k in (
                    "coherent", "problems", "price_points", "members", "without_concept")}}

    # #234 (C-64): the bundle engine's own test on the members' product facts. A set whose
    # pairs do not share enough affinities, or that spans too many pods, is a shelf with a
    # discount rather than a bundle, and is not assembled into a listing.
    from ..commerce import bundles as bundles_mod
    from ..commerce.order_readings import bundle_items

    wanted = {m.slug for m in members}
    items = [i for i in bundle_items(ctx.db) if i.slug in wanted]
    bundle_check = (bundles_mod.check(items, price_cad=verdict.price_cad)
                    if len(items) >= 2 else None)
    if bundle_check is not None:
        ctx.audit("collection.bundle_check", artifact=slug, detail=bundle_check)
        incoherent = [r for r in bundle_check["reasons"]
                      if "holds every pair together" in r or "departments" in r]
        if incoherent:
            return {"slug": slug, "assembled": False, "bundle_check": bundle_check,
                    "why": incoherent[0][:300]}

    titles = [m.title for m in members]
    collection_name = (seed.family or slug).replace("-", " ").title()
    name_problems = bible.check_collection_name(collection_name)

    description = (
        f"{collection_name}: {len(members)} crochet patterns that share one motif library and "
        f"one palette, sold together.\n\n"
        + "\n".join(f"- {t}" for t in titles)
        + f"\n\nBuying them together saves CA${verdict.saving_cad:.2f} "
          f"({verdict.saving_pct:.0%}) against CA${verdict.member_total_cad:.2f} for the same "
          f"patterns bought separately. That is a saving against the prices we actually "
          f"charge, not against a reference price we invented.\n\n"
          f"Every pattern in this collection was compiled and checked row by row before "
          f"release, and each one's chart is generated from the same data as its written "
          f"instructions.")

    with ctx.db.session() as s:
        row = s.scalar(select(Collection).where(Collection.slug == slug))
        if row is None:
            row = Collection(slug=slug, family=family or slug)
            s.add(row)
        row.title = collection_name
        row.season = seed.season if seed else None
        row.palette = dict(bible.PALETTE)
        row.story = description

        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == "collection"))
        if listing is None:
            listing = Listing(product_slug=slug, version="collection")
            s.add(listing)
        listing.title = f"{collection_name} Collection | {len(members)} Crochet Patterns | PDF"
        listing.description = description
        listing.tags = [f"{collection_name.split()[0].lower()} collection",
                        "crochet pattern set", "pattern bundle pdf"]
        listing.price_cad = verdict.price_cad
        listing.state = "draft"
        listing.seo_score = 0.0
        listing.chain_version = CHAIN_VERSION
        s.flush()

        # A bundle has no design of its own, so its listing is derived from every member's
        # stored release: a redesign of any one member turns the collection stale (#171).
        from ..ops import artefacts as provenance

        inputs: dict[str, str] = {}
        parents: list[str] = []
        for member_slug, member_version in certified:
            if member_slug not in ready:
                continue
            inputs.update(provenance.design_inputs(s, member_slug, member_version,
                                                   chain=False))
            parents.append(f"certificate:{provenance.release_key(member_slug, member_version)}")
        inputs["chain:release"] = provenance.chain_fingerprint()
        key = provenance.release_key(slug, "collection")
        lineage = _lineage(ctx, validation_status="name_problems" if name_problems
                           else "passed")
        provenance.record_lineage(
            s, artefact_class="listing_copy", artefact_key=key, product_slug=slug,
            inputs=inputs, chain_version=CHAIN_VERSION,
            lineage=lineage.for_file(_content_hash(listing.title, listing.description))
                           .under(*parents))
        provenance.record_lineage(
            s, artefact_class="seo", artefact_key=key, product_slug=slug,
            inputs=inputs, chain_version=CHAIN_VERSION,
            lineage=lineage.for_file(_content_hash(listing.title, *listing.tags))
                           .under(f"listing_copy:{key}"))
        provenance.record_lineage(
            s, artefact_class="pricing", artefact_key=key, product_slug=slug,
            inputs=inputs, chain_version=CHAIN_VERSION, lineage=lineage.under(*parents))

    ctx.audit("collection.assembled", artifact=slug, detail={
        "members": [m[0] for m in certified], "price_cad": verdict.price_cad,
        "saving_cad": verdict.saving_cad, "name_problems": name_problems,
        "published": False})
    return {"slug": slug, "members": [m[0] for m in certified],
            "price_cad": verdict.price_cad, "saving_cad": verdict.saving_cad,
            "saving_pct": verdict.saving_pct, "name_problems": name_problems,
            "architecture": {k: architecture[k] for k in ("coherent", "problems",
                                                          "price_points", "members",
                                                          "without_concept")}}


def _collection_architecture(slug: str, seed, member_slugs: list[str]) -> dict:
    """`seasonal.collections.assemble` and `assess` over a bundle's certified members (#289).

    Members are read as concepts from the catalogue's own design records; a member with no
    design record is named rather than guessed into the vocabulary.
    """
    from collections import Counter

    from ..creative.audit import catalogue_concepts
    from ..seasonal import collections as coll
    from ..seasonal.daily import CONCEPT_OCCASION

    concepts = {c.key: c for c in catalogue_concepts()}
    found = [concepts[m] for m in member_slugs if m in concepts]
    missing = [m for m in member_slugs if m not in concepts]
    occasion = CONCEPT_OCCASION.get(seed.season if seed else "", "everyday")
    story = (Counter(c.palette_story for c in found).most_common(1)[0][0]
             if found else "")
    built = coll.assemble(occasion, key=slug, palette_story=story,
                          visual_language=(seed.family if seed and seed.family else slug),
                          candidates=found)
    whole = coll.assess(coll.Collection(key=slug, event=occasion, palette_story=story,
                                        visual_language=built["visual_language"],
                                        members=found))
    return {**whole, "assembled": {k: built[k] for k in ("members", "rejected",
                                                         "ineligible", "coherent")},
            "without_concept": missing}


@handlers.register("physical.record")
def handle_physical_record(ctx: JobContext) -> dict:
    """Take one real crocheted sample and let it change what the company claims.

    The only measured input in the system. It does two different things and the difference is
    the point: the yarn figure is *calibrated* against it, and the finished size is
    *falsified* by it. Folding a size disagreement into the calibration factor would turn the
    one check that can catch a wrong geometry model into a number that quietly absorbs it.

    A sample that disagrees about size raises a defect against the product, which halts its
    publication. That is the correct outcome: the listing's size claim is wrong, and no
    amount of yarn arithmetic fixes a basket that is not the size we said.
    """
    from ..gates.incidents import DefectReport, IncidentTracker
    from ..quality.physical import BallBand, SampleReport, assess, calibration_from_db, record

    i = ctx.job.inputs
    slug, version = i["slug"], i.get("version", "1.0.0")
    # A sample is most needed by a release that is blocked only on physical evidence (Class
    # C, a gauge outside its yarn's band, an uncalibrated stitch), so the CIR is the one the
    # chain examined for slug@version whatever its certification state -- and the content
    # hash the tester worked against is recorded with the sample, the same hash
    # `gate.certify` binds evidence to (F-078).
    cir, content_hash, certified = _load_examined_cir(ctx, slug, version,
                                                      content_hash=i.get("content_hash"))
    result = compile_cir(cir)
    twin = build_twin(cir, result)   # uncalibrated on purpose: this is what we predicted

    report = SampleReport(
        product_slug=slug, version=version, tester_ref=i.get("tester_ref", "owner"),
        grams_by_color={str(k): float(v) for k, v in (i.get("grams_by_color") or {}).items()},
        ball_band=BallBand(grams=float(i["ball_band_grams"]),
                           metres=float(i["ball_band_metres"])),
        hook_mm=i.get("hook_mm"),
        measured_width_cm=i.get("measured_width_cm"),
        measured_height_cm=i.get("measured_height_cm"),
        measured_around_cm=i.get("measured_around_cm"),
        hours=i.get("hours"),
        notes=i.get("notes", ""),
        instructions_followed=bool(i.get("instructions_followed", True)))

    assessment = assess(report, twin, cir)
    row_id = record(ctx.db, assessment, content_hash=content_hash)
    ctx.audit("physical.recorded", artifact=f"{slug}@{version}",
              detail={"row": row_id, "content_hash": content_hash,
                      "release_certified": certified, **assessment.to_dict()})

    if assessment.size_agrees is False:
        tracker = IncidentTracker(ctx.db)
        for finding in assessment.findings:
            if finding.code != "SAMPLE_SIZE_DISAGREES":
                continue
            tracker.report(DefectReport(
                product_slug=slug, pattern_version=version, component=None, row=None,
                customer_ref=f"physical-test:{row_id}", text=finding.message))
        ctx.audit("physical.size_disagreement", artifact=f"{slug}@{version}",
                  detail={"measured": assessment.to_dict()["measured_metres"],
                          "findings": [f.code for f in assessment.findings]})

    # A usable sample changes every yardage figure for its yarn and stitch, which means the
    # PDFs and listings built from the old estimate are now stale. Keyed on the factor, so
    # the rebuild happens once per calibration rather than once per rebuild cadence.
    factor = calibration_from_db(ctx.db, cir)
    rebuilt: list[str] = []
    # An uncertified release has no customer assets to rebuild; its next certification
    # renders from the calibrated figures.
    if certified and assessment.usable_for_calibration and factor != 1.0:
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": version,
                           "release": i.get("release", "")},
                          idempotency_key=chain_key("assets", slug, version,
                                                    f"cal{factor}"))
        if job is not None:
            rebuilt.append(f"{slug}@{version}")

    # #64: photographs of the finished sample arrive with the sample. Each is taken in and,
    # where a rights basis is recorded, becomes an upgrade task for the listing.
    photos = []
    for ph in i.get("photos") or []:
        photos.append(_intake_photo(ctx, {**ph, "slug": slug, "version": version,
                                          "physical_test_id": row_id}))

    return {"slug": slug, "version": version, "physical_test_id": row_id,
            "content_hash": content_hash, "release_certified": certified,
            "factor": assessment.factor, "calibration_now": factor,
            "size_agrees": assessment.size_agrees,
            "usable": assessment.usable_for_calibration,
            "findings": [f.code for f in assessment.findings],
            "rebuilt": rebuilt, "photos": photos}


def _intake_photo(ctx: JobContext, i: dict) -> dict:
    """Record one physical photo and queue its listing upgrade when rights permit (#64)."""
    from ..publish import physical_upgrade

    rec = physical_upgrade.intake(
        ctx.db, slug=i["slug"], version=i.get("version", ""),
        source=i.get("source", "tester"), sha256=i.get("sha256", ""),
        rights_basis=i.get("rights_basis", ""), taken_by=i.get("taken_by", ""),
        physical_test_id=i.get("physical_test_id"), note=i.get("note", ""))
    queued = None
    if rec["may_use"]:
        job = ctx.enqueue("publishing", "assets.physical_upgrade",
                          {"photo_id": rec["photo_id"]},
                          idempotency_key=f"physical_upgrade:{rec['photo_id']}")
        queued = job.id if job is not None else None
    ctx.audit("physical.photo_received", artifact=i["slug"],
              detail={**rec, "upgrade_job": queued})
    return {**rec, "upgrade_job": queued}


@handlers.register("physical.photo")
def handle_physical_photo(ctx: JobContext) -> dict:
    """#64 intake: a tester's or customer's photograph of a finished Brambleloop object.

    Recorded by hash with its rights basis; with a basis on file it becomes an
    `assets.physical_upgrade` task. GREEN: internal writes only; nothing is published.
    """
    return _intake_photo(ctx, dict(ctx.job.inputs or {}))


@handlers.register("assets.physical_upgrade")
def handle_physical_upgrade(ctx: JobContext) -> dict:
    """#64: supplement the listing with the physical photograph and record the baseline.

    The new frame is unapproved until asset truth and the listing-set certificate re-run; the
    changed frame set invalidates the old certificate by fingerprint (#70). GREEN.
    """
    from ..publish import physical_upgrade

    out = physical_upgrade.plan_upgrade(ctx.db, int(ctx.job.inputs["photo_id"]),
                                        today=_mjs_today(ctx))
    ctx.audit("physical.upgrade_planned", artifact=out.get("slug"), detail=out)
    return out


@handlers.register("creative.reference_reading")
def handle_reference_reading(ctx: JobContext) -> dict:
    """#116 / #278: construction readings recorded and department decompositions stored.

    Daily. Refused, with the reason, while image_vision is closed; otherwise reads a bounded
    batch of judged listings' first images inside the creative_director ceiling, records each
    reading, and stores each department's decomposition for ideation to read.
    """
    import os

    from ..creative import reference

    out = reference.run(ctx.db, env=dict(os.environ), today=_mjs_today(ctx))
    ctx.audit("creative.reference_reading" if out["ran"] else
              "creative.reference_reading_blocked", detail=out)
    return out


@handlers.register("visual.identity_drift")
def handle_identity_drift(ctx: JobContext) -> dict:
    """#201: the canonical model's identity checked across batches and over time, daily.

    Per-dimension drift share per render batch from the recorded identity verdicts; a
    dimension rising across batches opens a publication-halting incident. UNMEASURED with
    fewer than three batches. GREEN: reads audit rows, writes a reading and incidents.
    """
    from ..visual import drift_series

    out = drift_series.run(ctx.db, today=_mjs_today(ctx))
    ctx.audit("visual.identity_drift", detail={k: out[k] for k in (
        "batches", "frames", "gradual_drift", "measurable", "incidents_opened",
        "incidents_resolved")})
    return {"batches": out["batches"], "measurable": out["measurable"],
            "gradual_drift": [g["dimension"] for g in out["gradual_drift"]],
            "incidents_opened": out["incidents_opened"]}


@handlers.register("physical.upgrade_impact")
def handle_physical_upgrade_impact(ctx: JobContext) -> dict:
    """#64: CTR and conversion before/after each physical-proof upgrade, daily.

    UNMEASURED, with the reason, until a live listing produces outcome rows. GREEN.
    """
    from ..publish import physical_upgrade

    out = physical_upgrade.measure_impact(ctx.db, today=_mjs_today(ctx))
    ctx.audit("physical.upgrade_impact", detail=out)
    return {"upgrades": out["upgrades"],
            "measured": sum(1 for r in out["readings"] if r["impact"] == "measured")}



@handlers.register("model.probe")
def handle_model_probe(ctx: JobContext) -> dict:
    """Ask the model provider whether it can actually serve a request, and record the answer.

    A key is not a capability. The key the owner supplied on 2026-09-19 authenticates and the
    account behind it cannot serve a request, so the build executor's model gate reads this
    probe rather than an environment variable -- and when credits arrive, the next run of this
    cadence opens the gate with nobody having to remember.

    The probe is the smallest call the API accepts, on the cheapest model, checked against the
    monthly ceiling first like every other call. GREEN by the authority matrix: no
    publication, no customer contact, and spend bounded before the request is made.
    """
    from ..gateway import anthropic

    record = anthropic.probe(ctx.db, job_id=ctx.job.id)
    ctx.audit("model.probe.ok" if record["ok"] else "model.probe.unavailable",
              detail={k: v for k, v in record.items() if k != "key"})
    return record


@handlers.register("ops.continuity")
def handle_continuity(ctx: JobContext) -> dict:
    """Export the database portably and prove the export can be restored.

    Requirement 51, and the gap Build 1 wrote into its own baseline: production state was not
    backed up from the application environment. The proof is the point -- a backup nobody has
    restored is a hope, and the previous drill was honest that it had never verified a
    Postgres restore because it needed a scratch database to do it.

    This runs against whatever database it is pointed at, including production, because the
    export format is engine-independent and the scratch target is a local SQLite file. It
    reads; it never writes to the source.

    GREEN by the authority matrix: no publication, no spend, no customer contact. The
    connection string is redacted before anything is recorded.
    """
    from ..core import continuity, workspace

    # The directory holds the export the restore is proved against, so it has to live until
    # `continuity.retain` has read the file -- which is why the whole body is inside the
    # block rather than only the restore. It used to be `tempfile.mkdtemp`, which removes
    # nothing, on a daily cadence, writing a multi-megabyte archive each time.
    with workspace.work_dir(ctx.job.inputs.get("work_dir"),
                            prefix="continuity-") as work:
        proof = continuity.prove_restore(ctx.db, work)
        detail = proof.to_dict()
        detail["source"] = proof.export.source          # already redacted
        detail["bytes"] = proof.export.bytes_written
        detail["work_dir_is_durable"] = False

        ctx.audit("continuity.verified" if proof.ok else "continuity.failed", detail=detail)

        if not proof.ok:
            # A continuity failure is not a log line to scroll past: it means the company's
            # unrecoverable history is not actually recoverable. Raised as a correlated incident
            # so it re-uses the existing P1 machinery -- one incident that counts repeats rather
            # than a new row every scheduled run.
            from sqlalchemy import select

            from ..core.models import Incident

            signature = "continuity.restore_unproven"
            with ctx.db.session() as s:
                existing = s.scalar(select(Incident).where(
                    Incident.signature == signature, Incident.resolved == False))  # noqa: E712
                if existing is None:
                    s.add(Incident(
                        severity="P1", signature=signature,
                        summary="the continuity export could not be restored, so the "
                                "company's non-rederivable history is not recoverable",
                        detail=detail, halts_publication=False))
                else:
                    existing.report_count += 1
                    existing.detail = detail

        # Only a proved export is retained. Keeping one that failed its own restore would put a
        # file nobody can use where the next operator will find it and believe it.
        if proof.ok:
            retained = continuity.retain(ctx.db, proof.export.path, proof.export)
            detail["retained"] = retained
            ctx.audit("continuity.retained", detail=retained)

        # Recorded every run. The archive now survives the container -- it is held in the
        # database, which is what a redeploy and a crash cannot take away. It does not survive
        # the provider disappearing, which is the failure #51 actually names, so the claim stops
        # exactly where the evidence does and the owner queue carries the off-provider decision.
        ctx.audit("continuity.storage_not_offsite", detail={
            "reason": "the retained archive lives in the database it describes, so it survives "
                      "a container replacement, a redeploy and a crash, and not the loss of the "
                      "provider. An off-provider copy needs a bucket and a credential, which is "
                      "an owner decision and is not claimed here.",
            "retained_archives": continuity.RETAINED_ARCHIVES,
        })
        return detail


@handlers.register("seasonal.sentinel")
def handle_seasonal_sentinel(ctx: JobContext) -> dict:
    """Recompute every certified pattern's launch dates and escalate what is at risk.

    Requirements 283, 296, 310, 311, and the owner's instruction after the first run of this
    engine found something: use it continuously rather than rediscovering seasonal timing
    manually. Timing is not a fact anybody establishes once -- a date that was comfortable in
    September is missed in October without anything changing except the date.

    GREEN by the authority matrix: it computes dates and writes audit records. It publishes
    nothing, spends nothing and contacts nobody.
    """
    from datetime import date as _date

    from ..seasonal.leadtime import catalogue_plans

    # `as_of` lets an operator ask what the room looked like, or will look like, on a given
    # day -- and lets a test drive the at-risk branch deterministically instead of waiting for
    # the calendar to produce one. Absent, it is today.
    as_of = ctx.job.inputs.get("as_of")
    room = catalogue_plans(ctx.db, today=_date.fromisoformat(as_of) if as_of else None)
    counts = room["counts"]
    at_risk = [r for r in room["at_risk_or_missed"] if r["status"] == "at_risk"]
    missed = [r for r in room["at_risk_or_missed"] if r["status"] == "missed"]

    ctx.audit("seasonal.assessed", detail={
        "products_scheduled": room["products_scheduled"],
        "counts": counts,
        "calibration": room["calibration"],
        # The rows somebody can still act on, named. A count is not an action.
        "at_risk": [{"slug": r["slug"], "event": r["event"],
                     "days_to_latest": r["days_to_latest"]} for r in at_risk[:20]],
        "missed": [{"slug": r["slug"], "event": r["event"],
                    "recommendation": r["recommendation"]} for r in missed[:20]],
    })

    # Every detector below follows `ops.incident_lifecycle`: a condition that still holds is
    # restated on its open row, and a condition that stopped holding is resolved with the
    # sentence that says why. Signatures carry the event *and its year*, which is what lets
    # tomorrow's run recognise today's row -- and what lets Halloween 2026 close when it
    # passes instead of standing open as Halloween 2027.
    from ..ops import incident_lifecycle as lifecycle
    from ..seasonal.leadtime import next_occurrence, occasion_for
    from ..radar.market import SEASONAL_EVENTS

    today = _date.fromisoformat(as_of) if as_of else _date.today()
    plans = room["plans"]
    plan_for = {(r["slug"], r["event"]): r for r in plans}

    # ---- at risk ----------------------------------------------------------------------
    # An at-risk window is the last one in which reallocating effort changes the outcome, so
    # every at-risk (product, occasion) is raised -- not only the soonest, which opened one
    # new row a day and closed none. Missed windows are not incidents: #297 already decided
    # what happens to them, and the row that was at risk closes carrying that decision.
    wanted = {f"seasonal.at_risk:{r['slug']}:{r['event']}:{r['event_year']}": r
              for r in plans if r["status"] == "at_risk"}

    def _at_risk_resolution(row) -> str:
        parts = row.signature.split(":")
        slug, event = (parts[1:3] + ["", ""])[:2]
        year = parts[3] if len(parts) > 3 else None
        current = plan_for.get((slug, event))
        if current is None:
            return (f"{slug} is not merchandised for {event} (its occasion is "
                    f"{occasion_for(slug)}), so it has no {event} window to be at risk in. "
                    f"The row was raised when every product was scheduled against every "
                    f"event.")
        key = f"seasonal.at_risk:{slug}:{event}:{current['event_year']}"
        if year is None and key in wanted:
            return f"re-keyed as {key}, which carries the event year; still open there."
        if year is not None and str(current["event_year"]) != year:
            return (f"the {event} {year} occurrence has passed; {slug} is now scheduled "
                    f"for {event} {current['event_year']} ({current['status']}, "
                    f"{current['days_to_latest']} days to its latest launch).")
        if current["status"] == "missed":
            nxt = current.get("next_window") or {}
            return (f"missed for {event} {current['event_year']}: latest effective launch "
                    f"{current['latest_effective_launch']} has passed. Recommendation: "
                    f"{current['recommendation']} -- {current['because']}. Next window: "
                    f"{event} {str(nxt.get('event_date', ''))[:4]}, preferred launch "
                    f"{nxt.get('preferred_launch')}, latest {nxt.get('latest_effective_launch')}.")
        return (f"no longer at risk: {current['status']} with {current['days_to_latest']} "
                f"days to its latest launch ({current['latest_effective_launch']}).")

    with ctx.db.session() as s:
        at_risk_life = lifecycle.reconcile(
            s, "seasonal.at_risk:", lambda row: row.signature in wanted,
            resolution=_at_risk_resolution)
        for signature, r in wanted.items():
            if signature in at_risk_life["still_open"]:
                continue
            lifecycle.open_or_restate(
                s, signature=signature, severity="P2", product_slug=r["slug"],
                summary=(f"{r['slug']} has {r['days_to_latest']} days of runway left for "
                         f"{r['event']} {r['event_year']}: past its preferred launch date "
                         f"and inside the last window where reallocating effort still "
                         f"changes whether a customer can finish the object in time. After "
                         f"the latest effective date the only honest options are pivot, "
                         f"simplify or hold (#297)."),
                detail={"slug": r["slug"], "event": r["event"],
                        "event_year": r["event_year"],
                        "days_to_latest": r["days_to_latest"],
                        "latest_effective_launch": r["latest_effective_launch"]})

    # ---- collection calendar (#123) ---------------------------------------------------
    # The launch-date work above answers "can a customer still finish this"; this answers
    # "did the work that had to happen by now happen", which slips silently -- a phase that
    # is late does not announce itself, it becomes the next phase.
    #
    # Milestone completion is read from audit evidence for the products that target the
    # occasion, and a milestone due before the first such product existed is `preceded`
    # rather than missed. An incident needs all three of: a milestone genuinely missed, a
    # lane that can still reach a customer, and a product that targets the event. Without
    # the last two there is nothing anybody could do about it this cycle.
    from sqlalchemy import select as _select

    from ..core.models import Product
    from ..seasonal.calendar import (
        MILESTONES, collection_calendar, heaviest_launchable_lane, milestone_evidence,
    )

    targets: dict[str, list[str]] = {}
    for r in plans:
        targets.setdefault(r["event"], [])
        if r["slug"] not in targets[r["event"]]:
            targets[r["event"]].append(r["slug"])
    with ctx.db.session() as s:
        created = {p.slug: p.created_at for p in s.scalars(_select(Product).where(
            Product.slug.in_(sorted({x for v in targets.values() for x in v}) or [""])))}

    behind: list[dict] = []
    calendar_state: dict[str, dict] = {}
    for event in SEASONAL_EVENTS:
        event_date = next_occurrence(event.event_date, today)
        slugs = targets.get(event.name, [])
        births = [created[x] for x in slugs if created.get(x) is not None]
        not_before = min(births).date() if births else None
        completed = milestone_evidence(ctx.db, slugs=slugs, event_date=event_date,
                                       today=today)
        calendar = collection_calendar(event.name, event_date, today=today,
                                       completed=completed, not_before=not_before)
        lane = heaviest_launchable_lane((event_date - today).days, today=today)
        calendar_state[event.name] = {"year": event_date.year, "targets": slugs,
                                      "lane": lane, "on_schedule": calendar["on_schedule"]}
        if calendar["missed"]:
            behind.append({"event": event.name,
                           "event_date": event_date.isoformat(),
                           "missed": [m["milestone"] for m in calendar["missed"]],
                           "done": sorted(completed),
                           "targets": slugs,
                           "heaviest_launchable_lane": lane,
                           "raised": bool(slugs and lane),
                           "next_due": calendar["next_due"]})

    raise_behind = {f"seasonal.calendar_behind:{b['event']}:{b['event_date'][:4]}": b
                    for b in behind if b["raised"]}

    def _calendar_resolution(row) -> str:
        parts = row.signature.split(":")
        event = parts[1] if len(parts) > 1 else ""
        year = parts[2] if len(parts) > 2 else None
        state = calendar_state.get(event)
        if state is None:
            return f"{event} is no longer on the seasonal calendar."
        key = f"seasonal.calendar_behind:{event}:{state['year']}"
        if year is None and key in raise_behind:
            return f"re-keyed as {key}, which carries the event year; still open there."
        if year is not None and str(state["year"]) != year:
            return f"the {event} {year} occurrence has passed."
        if not state["targets"]:
            return (f"no certified product is merchandised for {event}, so there is no "
                    f"collection whose milestones could slip. The row was raised from dates "
                    f"alone, including milestones due before this company existed.")
        if not state["lane"]:
            return (f"no product lane can still reach a customer for {event} "
                    f"{state['year']}; the remaining work is next year's, which the "
                    f"compression programme carries.")
        return (f"{event} {state['year']} is on schedule: every milestone due so far has "
                f"audit evidence or fell before the first product for it existed.")

    with ctx.db.session() as s:
        calendar_life = lifecycle.reconcile(
            s, "seasonal.calendar_behind:", lambda row: row.signature in raise_behind,
            resolution=_calendar_resolution)
        for signature, b in raise_behind.items():
            if signature in calendar_life["still_open"]:
                continue
            lifecycle.open_or_restate(
                s, signature=signature, severity="P2",
                summary=(f"{b['event']} {b['event_date'][:4]}: {len(b['missed'])} of "
                         f"{len(MILESTONES)} collection milestones are already past with no "
                         f"evidence ({', '.join(b['missed'][:3])}) while "
                         f"{', '.join(b['targets'][:3])} target it and a "
                         f"{b['heaviest_launchable_lane']} product can still reach a "
                         f"customer. A missed date is a portfolio failure rather than a "
                         f"scheduling detail, and the failure is silent -- a phase that "
                         f"slips becomes the next phase, and the first visible symptom is a "
                         f"product that lists in December (#123)."),
                detail={"behind": [b], "as_of": today.isoformat()})

    ctx.audit("seasonal.calendar_checked", detail={
        "as_of": today.isoformat(),
        "events_behind": [b["event"] for b in behind],
        "events_raised": sorted(b["event"] for b in behind if b["raised"]),
        "resolved": calendar_life["resolved"],
        "events_checked": len(SEASONAL_EVENTS)})

    # The compression programme for every priority occasion, recomputed on the same cadence.
    # This is the half that makes the owner's correction automatic rather than remembered: as
    # a lane's runway closes, the mix moves into the fastest lane still open and the
    # departments that can no longer be finished drop out by themselves. A retirement is
    # recorded as a transition, because "FLAGSHIP closed today" is the sentence a reader
    # needs and "FLAGSHIP is closed" is the one they will misread a fortnight later.
    from ..seasonal import uncertainty
    from ..seasonal.compression import (
        PREPARATION_EVIDENCE, preparation_started, priority_shares, programme,
    )

    occurrence = {e.name: next_occurrence(e.event_date, today) for e in SEASONAL_EVENTS}
    samples = uncertainty.sample_count(ctx.db)
    programmes = []
    overdue_prep: list[dict] = []
    started_by_event: dict[str, dict] = {}
    for name in priority_shares()["shares"]:
        try:
            when = occurrence.get(name)
            started = (preparation_started(ctx.db, event_date=when, today=today)
                       if when else {})
            started_by_event[name] = started
            plan = programme(name, today=today, samples=samples, started=started)
        except Exception as exc:  # noqa: BLE001 - a calendar fault must not stop the sentinel
            ctx.audit("seasonal.compression_failed",
                      detail={"event": name, "error": str(exc)[:300]})
            continue
        late = [dict(row, event=name, event_year=plan["event_date"][:4])
                for row in plan["preparation"] if row["overdue"]]
        overdue_prep.extend(late)
        programmes.append({
            "event": name, "days_away": plan["days_away"], "mode": plan["mode"]["mode"],
            "leading_lane": plan["mix"]["leading_lane"],
            "shares": plan["mix"]["shares"],
            "retired_classes": [r["lane"] for r in plan["retired_classes"]],
            "departments": [a["department"] for a in plan["arenas"]],
            "capacity_share": plan["capacity"]["share"],
            "preparation_started": started,
            "overdue_preparation": [f"{r['lane']}:{r['stream']}" for r in late][:10],
        })
        ctx.audit("seasonal.compression", detail=programmes[-1])

    # One row per (occasion, year, stream): the lanes a stream serves share one start --
    # the earliest -- and one piece of evidence starts it for all of them.
    prep_rows: dict[str, list[dict]] = {}
    for row in overdue_prep:
        prep_rows.setdefault(
            f"seasonal.preparation_late:{row['event']}:{row['event_year']}:{row['stream']}",
            []).append(row)

    def _prep_resolution(row) -> str:
        parts = row.signature.split(":")
        if len(parts) == 3:  # the old shape: lane:stream, with no event in it
            stream = parts[2]
            open_now = [k for k in prep_rows if k.endswith(f":{stream}")]
            if open_now:
                return (f"re-keyed with the event and year as {', '.join(open_now)}; the "
                        f"old signature named a lane and no occasion, so it could never "
                        f"close.")
        else:
            stream = parts[-1]
        event = parts[1] if len(parts) == 5 else None
        year = parts[2] if len(parts) == 5 else None
        if event and year and occurrence.get(event) and str(occurrence[event].year) != year:
            return f"the {event} {year} occurrence has passed."
        for name, started in started_by_event.items():
            if event and name != event:
                continue
            if started.get(stream):
                return (f"{stream} has started: "
                        f"{'/'.join(PREPARATION_EVIDENCE.get(stream, ()))} recorded on "
                        f"{started[stream]}.")
        return (f"{stream} is no longer overdue for any open lane"
                + (f" of {event} {year}" if event else "") + ".")

    with ctx.db.session() as s:
        prep_life = lifecycle.reconcile(
            s, "seasonal.preparation_late:", lambda row: row.signature in prep_rows,
            resolution=_prep_resolution)
        for signature, rows in prep_rows.items():
            if signature in prep_life["still_open"]:
                continue
            first = min(rows, key=lambda r: r["days_until"])
            lifecycle.open_or_restate(
                s, signature=signature, severity="P3",
                summary=(f"{first['stream']} for {first['event']} {first['event_year']} "
                         f"({', '.join(sorted({r['lane'] for r in rows}))}) should have "
                         f"started {abs(first['days_until'])} days ago and nothing shows it "
                         f"has ({'/'.join(first['started_evidence'])}). {first['why']} A "
                         f"product ready on its launch date is late: indexing is not "
                         f"instant, and a listing nobody can find is not a launch."),
                detail={"overdue": rows[:20], "as_of": today.isoformat()})

    ctx.audit("seasonal.incidents_reconciled", detail={
        "at_risk": at_risk_life, "calendar_behind": calendar_life,
        "preparation_late": prep_life})

    return {"products_scheduled": room["products_scheduled"], "counts": counts,
            "at_risk": len(at_risk), "missed": len(missed),
            "collection_calendar_behind": behind,
            "compression": programmes}


@handlers.register("etsy.probe")
def handle_etsy_probe(ctx: JobContext) -> dict:
    """Ask the Etsy API whether these credentials can actually serve a request.

    The owner's condition on the credentials: the gate opens from a successful read, not from
    the variables existing. Etsy v3 refuses the keystring alone -- "Shared secret is required
    in x-api-key header" -- so a half-configured credential is indistinguishable from a
    working one until something asks.

    The smallest sanctioned read: an application ping, which returns an application id and
    nothing about anybody's shop. GREEN by the authority matrix -- read-only, public, no
    publication, no spend, no customer contact.
    """
    from ..intel import etsy_public

    record = etsy_public.probe(ctx.db)
    ctx.audit("etsy.probe.ok" if record["ok"] else "etsy.probe.unavailable",
              detail=record)
    return record


@handlers.register("mjs.scan")
def handle_mjs_scan(ctx: JobContext) -> dict:
    """Scan the named benchmark catalogue: baseline once, then only what changed.

    The owner's top-priority mandate (#301). Runs whether or not the credential exists: with
    one it observes, without one it reports precisely why it could not and which requirements
    stay unmet. It never substitutes search snippets or fixtures for observation (#224).

    GREEN by the authority matrix: it reads public marketplace data, writes observations and
    queues internal work. It publishes nothing, spends nothing and contacts nobody.
    """
    from ..intel.observe import reclassify, scan_or_explain

    outcome = scan_or_explain(ctx.db)
    if not outcome["ran"]:
        ctx.audit("mjs.scan_blocked", detail=outcome)
        # A scan that did not run this time does not un-store what earlier scans observed:
        # any new or changed listing still waiting for the mission pipeline is carried
        # through it now. Nothing here reads Etsy.
        mission = _run_mjs_mission(ctx)
        return {"ran": False, "reason": outcome["reason"][:200],
                "mission": {k: mission[k] for k in ("pending", "processed", "tournaments")}}

    # Every scan re-routes the whole stored catalogue through the current pod vocabulary.
    # The scan itself only routes what it read, and it deliberately skips anything whose
    # fingerprint is unchanged -- so without this, widening the vocabulary would reach only
    # the listings the benchmark shop edits afterwards, which is close to none of them. It
    # reads stored titles, makes no Etsy call and usually moves nothing.
    routing = reclassify(ctx.db)
    if routing["moved"]:
        ctx.audit("mjs.reclassified", detail=routing)

    # #98: four of the eight learning domains are answerable from a catalogue somebody has
    # actually read, and until now nothing fed any of them. Recorded here because this is
    # the moment the evidence exists; the other four stay unobserved and say why.
    from ..intel.learning import ingest_benchmark

    learned = ingest_benchmark(ctx.db)
    if learned.get("recorded"):
        ctx.audit("learning.ingested", detail=learned)

    report = outcome["report"]
    ctx.audit("mjs.scanned", detail=report)
    # #214/#309: every new or changed listing the scan just stored becomes a market event and
    # is carried through the mission pipeline (director routing, decomposition, panel gates,
    # lessons, memory, coverage, arena response, breakthrough tournament).
    mission = _run_mjs_mission(ctx)
    return {"ran": True,
            "listings_known": report["catalogue_coverage"]["listings_known"],
            "new": len(report["changes"]),
            "reclassified": routing["moved"],
            "learning_domains": len(learned.get("recorded") or []),
            "inspected": report["catalogue_coverage"]["listings_inspected"],
            "mission": {k: mission[k] for k in ("pending", "processed", "tournaments")}}


def _mjs_today(ctx: JobContext):
    """The date the mission reasons about: the job's `as_of` when a replay names one."""
    from datetime import datetime, timezone

    as_of = (ctx.job.inputs or {}).get("as_of")
    return date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()


def _run_mjs_mission(ctx: JobContext) -> dict:
    """The eight-step MJs pipeline over stored observations (intel.mission_runtime)."""
    from ..intel import mission_runtime

    result = mission_runtime.process(ctx.db, enqueue=ctx.enqueue, today=_mjs_today(ctx))
    result["tournaments"] = sorted({e["tournament_job_id"] for e in result["events"]
                                    if e.get("tournament_job_id")})
    # C-60 (#215): a CONCEPTING gap is consumed -- its same-arena original design starts.
    concepting = mission_runtime.consume_concepting(ctx.db, enqueue=ctx.enqueue,
                                                    today=_mjs_today(ctx))
    result["same_arena_started"] = concepting["started"]
    # C-60 (#211): the director's company-level view, persisted daily and acted on.
    standing = mission_runtime.company_standing(ctx.db, enqueue=ctx.enqueue,
                                                today=_mjs_today(ctx))
    result["company_standing"] = standing["counts"]
    if concepting["started"] or standing["photography_requested"]:
        ctx.audit("mjs.director_actions", detail={
            "same_arena_started": concepting["started"],
            "photography_requested": standing["photography_requested"],
            "counts": standing["counts"]})
    if result["pending"] or result["processed"]:
        ctx.audit("mjs.mission_events", detail={
            "pending": result["pending"], "processed": result["processed"],
            "deferred": result["deferred"], "events": result["events"][:50],
            "cross_category": result["cross_category"],
            "tournaments": result["tournaments"]})
    return result


@handlers.register("intel.benchmark_health")
def handle_intel_benchmark_health(ctx: JobContext) -> dict:
    """#206: resolve the benchmark URL and record its health, never re-pointing to a stranger.

    Without a proven fetch capability every benchmark reads `unverified`. `wrong_shop` or
    `unreachable` opens a P3 incident; a healthy or moved result resolves it.
    GREEN: at most one sanctioned rendered-page read per benchmark; nothing is published.
    """
    from ..intel import mission_runtime

    result = mission_runtime.benchmark_health(ctx.db)
    ctx.audit("mjs.benchmark_health", detail=result)
    return {"checked": result["checked"], "capability": result["capability"],
            "states": [r["state"] for r in result["results"]],
            "incidents_opened": result["incidents_opened"]}


@handlers.register("intel.pod_learning")
def handle_intel_pod_learning(ctx: JobContext) -> dict:
    """#226: every pod's discernment and creativity, computed from rows and stored.

    GREEN: reads pod lessons, mission events, coverage and vetoes; writes readings.
    """
    from ..intel import mission_runtime

    # #316: Brambleloop's own responses -- launches, sales, failures, complaints -- are
    # outcomes on the pods' interpretations, recorded before capability is computed from them.
    responses = mission_runtime.response_outcomes(ctx.db)
    ctx.audit("mjs.response_outcomes", detail=responses)
    result = mission_runtime.pod_capability(ctx.db)
    ctx.audit("mjs.pod_capability", detail=result)
    # C-60 (#210): each cell's opportunity map, persisted beside its capability reading.
    maps = mission_runtime.pod_maps(ctx.db, today=_mjs_today(ctx))
    result["pod_maps"] = sorted(maps["pods"])
    return {"pods": len(result["pods"]), "records": result["records"],
            "judgements": result["judgements"], "pod_maps": result["pod_maps"],
            "measured": sorted(p for p, r in result["pods"].items() if r["measured"]),
            "responses": {k: responses[k] for k in ("interpretations", "responses_launched",
                                                     "state")}}


@handlers.register("creative.benchmark_memory")
def handle_benchmark_memory(ctx: JobContext) -> dict:
    """#86: the creativity benchmark memory, folded daily from judged photographs and stored.

    Reads every `gallery_image_observation` for the commercial attributes the vision
    vocabulary judged (transformation, silhouette strength, characterisation, gift narrative,
    modularity ...), pairs each with the market outcome on file (favourites, a demand proxy)
    and with Brambleloop's own outcomes (UNMEASURED until orders exist), and stores the
    reading. `creative.ideation.lessons` reads it into every tournament and expedition brief.
    UNMEASURED, with the reason, while no judged image carries an attribute -- the judging runs
    behind image_vision. GREEN: reads rows, writes one reading, spends nothing.
    """
    from ..creative import benchmark_memory

    out = benchmark_memory.build(ctx.db, today=_mjs_today(ctx))
    ctx.audit(benchmark_memory.ACTION, detail={
        "state": out["state"], "judged_listings": out["judged_listings"],
        "attributes": sorted(out["attributes"]),
        "brambleloop_outcomes": out["outcomes"]["brambleloop"]["reading"],
        **({"reason": out["reason"]} if not out["measured"] else {})})
    return {"measured": out["measured"], "state": out["state"],
            "judged_listings": out["judged_listings"],
            "attributes": sorted(out["attributes"]),
            "rewarded": [a["attribute"] for a in benchmark_memory.rewarded(ctx.db)]}


@handlers.register("intel.panel_discovery")
def handle_intel_panel_discovery(ctx: JobContext) -> dict:
    """#219 / #268: category leaders found in the API search index join the panel and are scanned.

    Weekly. A shop in the index's top results for two or more target queries is read with
    `getShop` (for its name and its stated market), registered as a non-mandatory benchmark
    with the evidence that put it there, and its catalogue is scanned with the same sanctioned
    reader as the anchor. A market the panel does not yet cover is preferred. From then on
    `mission_runtime.panel_members` counts it and a mechanism shown by it and the anchor
    becomes learnable (#220). GREEN: public reads only; nothing is published or bought.
    """
    import os

    from ..intel import panel_discovery

    result = panel_discovery.discover(ctx.db, env=dict(os.environ))
    ctx.audit("intel.panel_discovered" if result["ran"] else "intel.panel_discovery_blocked",
              detail={k: v for k, v in result.items() if k != "note"})
    return {"ran": result["ran"], "candidates": result["candidates"],
            "joined": [j["key"] for j in result.get("joined", [])],
            "scanned": len(result.get("scanned", [])),
            "markets_observed": result.get("markets_observed", []),
            **({} if result["ran"] else {"reason": result["reason"][:200]})}


@handlers.register("intel.benchmark_refresh")
def handle_intel_benchmark_refresh(ctx: JobContext) -> dict:
    """#165: a new category, strong competitor, new format or market shift -> one purchase ask.

    Weekly, free. Reads the panel's observed listings, the SERP laboratory and the purchased
    library; the first reading is a baseline. Whatever warrants a refresh and is not duplicate
    information becomes an owner action naming one listing and its observed price as the
    maximum cost, never more than `benchmark_refresh.MAX_OPEN` open at once. GREEN: nothing
    is bought here -- buying is the owner's.
    """
    from ..intel import benchmark_refresh

    result = benchmark_refresh.assess(ctx.db, today=_mjs_today(ctx))
    ctx.audit("intel.benchmark_refresh", detail={
        k: result[k] for k in ("as_of", "baseline", "triggers", "duplicates", "raised",
                               "held")})
    return {"baseline": result["baseline"], "triggers": len(result["triggers"]),
            "raised": [r["key"] for r in result["raised"]], "held": len(result["held"])}


@handlers.register("mjs.seasonal_sentinel")
def handle_mjs_seasonal_sentinel(ctx: JobContext) -> dict:
    """#311: days to preferred and latest launch for every MJs-derived opportunity.

    At risk: a correlated P2 and the opportunity's work moved to the seasonal band (queued
    there if none exists). Missed: deferred to the next viable event, never an incident.
    GREEN: reads rows, re-prioritises internal jobs, queues internal work.
    """
    from ..intel import mission_runtime
    from ..swarm.orchestrate import priority_for

    today = _mjs_today(ctx)
    result = mission_runtime.seasonal_sentinel(ctx.db, today=today)
    queued = []
    if result["needs_tournament"]:
        from ..core.models import MjsMissionEvent
        from ..creative import breakthrough

        for event_id in result["needs_tournament"]:
            with ctx.db.session() as s:
                ev = s.get(MjsMissionEvent, event_id)
                arena, pod, ref, key = ev.arena, ev.pod, ev.listing_ref, ev.benchmark_key
                target = ((ev.seasonal or {}).get("target") or {}).get("event", "")
            inputs = breakthrough.release_brief(ctx.db, arena=arena, pod=pod, listing_ref=ref)
            inputs.update({"mjs_event_id": event_id, "reallocated_by": "mjs.seasonal_sentinel",
                           "seasonal_target": target})
            job = ctx.enqueue("creative_director", "creative.tournament", inputs,
                              priority=priority_for("mjs.seasonal_sentinel"),
                              idempotency_key=f"mjs.at_risk:{key}:{event_id}:{today}")
            if job is not None:
                with ctx.db.session() as s:
                    s.get(MjsMissionEvent, event_id).tournament_job_id = job.id
                queued.append(job.id)
    # #309: every entered event's response is walked forward from what the later stages
    # recorded, and winners that waited on a vision judgement are re-presented (C-61).
    from ..creative import intake as winner_intake

    regated = winner_intake.regate_held(ctx, today=today)
    pipeline = mission_runtime.advance_pipeline(ctx.db, today=today)
    ctx.audit("mjs.seasonal_sentinel", detail={**result, "queued": queued,
                                               "pipeline": pipeline["events"][:50],
                                               "regated": regated})
    return {"opportunities": result["opportunities"], "counts": result["counts"],
            "incidents_opened": result["incidents_opened"], "queued": queued,
            "reallocated": sum(len(r["reallocated"]) for r in result["rows"]),
            "pipeline": [{k: e[k] for k in ("event_id", "stopped_at", "winner")}
                         for e in pipeline["events"]], "regated": regated}


# Thumbnail judgements per run. Small on purpose: market_radar's CA$4.00 daily ceiling also
# pays for the benchmark gallery drain, and a SERP laboratory that ate it would starve the
# owner's top-priority mandate to judge thumbnails of listings the company does not track.
SERP_THUMBNAIL_SNAPSHOTS_PER_RUN = 2


@handlers.register("intel.serp_capture")
def handle_serp_capture(ctx: JobContext) -> dict:
    """Capture the SERP laboratory's target queries from the API search index (#15, #2, #98).

    One `findAllListingsActive` read per target query (sort_on=score) plus a gallery read for
    the top listings; a query captured within the last twenty hours is skipped. Rank is the
    API index's order and is directional; counts are `api_index_count`. Where image_vision
    has been demonstrated, a couple of snapshots per run get their top thumbnails judged by
    the existing vision path under the same budget checks; where it has not, the refusal is
    recorded rather than a composition guessed. Then the search_behaviour learning domain
    is fed from snapshot changes, labelled as a proxy.

    GREEN by the authority matrix: public reads, internal writes, no publication, and model
    spend only through the ceiling-checked gateway.
    """
    from ..intel import learning, serp

    inputs = ctx.job.inputs or {}
    outcome = serp.capture_targets(ctx.db)
    if not outcome["ran"]:
        ctx.audit("serp.capture_blocked", detail={"reason": outcome["reason"][:300]})
        return {"ran": False, "reason": outcome["reason"][:200]}

    thumbnails: list[dict] = []
    limit = int(inputs.get("thumbnail_snapshots", SERP_THUMBNAIL_SNAPSHOTS_PER_RUN))
    for snap in outcome["captured"][:max(0, limit)]:
        judged = serp.score_thumbnails(ctx.db, snap["id"], job_id=ctx.job.id)
        thumbnails.append({k: judged.get(k) for k in
                           ("snapshot", "judged", "refused", "reason", "stopped_by")})
        if judged.get("refused") or judged.get("stopped_by"):
            break

    learned = learning.ingest_search_behaviour(ctx.db)
    if learned.get("recorded"):
        ctx.audit("learning.ingested", detail=learned)

    ctx.audit("serp.captured", detail={
        "captured": [{k: c[k] for k in ("id", "query", "total_count", "ranked")}
                     for c in outcome["captured"]],
        "skipped_recent": len(outcome["skipped_recent"]),
        "failures": outcome["failures"][:20], "thumbnails": thumbnails,
        "basis": outcome["basis"]})
    return {"ran": True, "captured": len(outcome["captured"]),
            "skipped_recent": len(outcome["skipped_recent"]),
            "failures": len(outcome["failures"]),
            "thumbnails_judged": sum(t.get("judged") or 0 for t in thumbnails),
            "thumbnails_refused": any(t.get("refused") for t in thumbnails),
            "search_behaviour_recorded": bool(learned.get("recorded"))}


@handlers.register("improve.retrospective")
def handle_improvement_retrospective(ctx: JobContext) -> dict:
    """The weekly machine-readable business retrospective (#100).

    Reports what regressed as prominently as what improved, and names the bottleneck. A
    retrospective that lists only wins is a newsletter, and a newsletter is what a company
    reads instead of noticing.

    GREEN: reads rows and writes an audit record. It changes nothing.
    """
    from ..improve import roi
    from ..improve.bus import compounding
    from ..improve.cells import raise_plateau_defect, retrospective

    report = retrospective(ctx.db)
    report["compounding"] = compounding(ctx.db)
    # #99: what the promoted changes actually returned, against the baselines captured at
    # proposal time. Cost is known on the day and benefit is known later, so benefit is the
    # number nobody goes back for; the retrospective is where somebody reads, so it goes here.
    realised = roi.realised_benefit(ctx.db)
    report["realised_benefit"] = realised
    # #104: a creative plateau is a top-level business defect, so it opens an incident
    # rather than appearing in a paragraph. Opened and closed here, because a defect that
    # never resolves becomes furniture and a company learns to read past it.
    plateau = raise_plateau_defect(ctx.db)
    report["creative_plateau"] = plateau
    ctx.audit("improvement.retrospective", detail=report)
    return {"bottleneck": report["bottleneck"],
            "regressed": report["regressed_cells"],
            "unmeasured": len(report["unmeasured_cells"]),
            "creative_plateau": plateau["verdict"],
            "plateau_incident": plateau["incident"],
            "promotions_assessed": realised["assessed"],
            "returned": len(realised["returned"]),
            "no_return": len(realised["no_return"]),
            "regressed_promotions": len(realised["regressed"]),
            "hit_rate": realised["hit_rate"]}

@handlers.register("launch.readiness")
def handle_launch_readiness(ctx: JobContext) -> dict:
    """Assess what stands between this shop and a live customer, and queue what is owner-only.

    The owner-action table has had the directive's columns -- action, reason, maximum cost,
    minutes, consequence of delay -- since the first build, and nothing had ever written to
    them. That was correct: until the catalogue, the imagery, the pricing and the copy
    existed, every blocker was ours, and asking the owner for an Etsy account because it
    would eventually be needed is exactly what the directive forbids. Now the remaining
    blockers really are the owner's, so the system says so itself, on a cadence, instead of
    waiting for someone to ask.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from . import etsy_ops

    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))

    # C-80 defect 10 (#54): the rollback plan is rehearsed, per listed release, before it is
    # assessed -- a dry withdrawal round trip that checks the retained certificate, the
    # listing's state and that every deliverable a restore would re-serve is on disk.
    from ..core.models import Listing
    from ..launch import rollback as rollback_mod

    with ctx.db.session() as s:
        releases = sorted({(l.product_slug, l.version) for l in s.scalars(
            select(Listing).where(Listing.state != "withdrawn"))})
    rehearsed = {f"{slug}@{v}": rollback_mod.rehearse(ctx.db, slug=slug, version=v,
                                                      store=store, job_id=ctx.job.id)["ok"]
                 for slug, v in releases}

    # #195 is a launch-blocking acceptance test, so it is an item of this report and not an
    # endpoint beside it. PROVEN only on a window the rows show was worked unattended; a
    # proof that fails, or cannot be computed, is NOT PROVEN and holds `ready` false.
    # A3-07: computed by the one shared function the owner's launch packet also calls.
    from ..build2 import autonomy
    from ..launch.readiness import launch_assessment

    assessed = launch_assessment(ctx.db, phase=ctx.phase.value,
                                 artifact_dir=ctx.job.inputs.get("artifact_dir"))
    readiness = assessed.readiness
    off_device = assessed.off_device
    ready = assessed.ready

    # Build-2 access gates join the same queue rather than starting a second one beside it.
    # Section 14 is explicit that there is one owner queue, and the reason is arithmetic: two
    # queues means the owner reads whichever they remember. These are capability requests
    # (#223), not launch requirements, so they are queued but do not move `readiness.ready`.
    from ..launch import access
    from ..launch.readiness import LAUNCH_PACKAGE_KEYS, OPENS_LIVE_ETSY_KEYS

    requests = list(readiness.owner_requests()) + access.owner_requests()
    # F-160: an exposed credential is an owner card in the one queue until `rotated_at` is
    # set in `ops.credential_register` -- then the card stops being generated and the
    # closer below retires it. Security, not a launch requirement: `ready` is unchanged.
    from ..ops import credential_register

    requests += credential_register.owner_requests()

    # #54 (C-80 defect 10): "before asking the owner to open/connect live Etsy operations,
    # require ..." -- so while any item of that package is still ours to build, the requests
    # that open live Etsy are withheld from the queue, and the audit says which items held
    # them. The package items themselves stay in `ours_to_do`.
    package_blocked = sorted(r.key for r in readiness.buildable if r.key in LAUNCH_PACKAGE_KEYS)
    withheld: list[str] = []
    if package_blocked:
        withheld = sorted(r.key for r in requests if r.key in OPENS_LIVE_ETSY_KEYS)
        requests = [r for r in requests if r.key not in OPENS_LIVE_ETSY_KEYS]

    queued: list[str] = []
    restated: list[str] = []
    with ctx.db.session() as s:
        # Keyed on the requirement, not on the action's wording. Comparing text worked only
        # while every action was a frozen string: as soon as one derived its figure from the
        # catalogue, a changed number read as a new request and the owner got two entries
        # for one decision. An owner queue that grows by seven a day is a queue nobody reads,
        # and one that lists the same decision twice with different numbers is worse.
        open_actions = {
            a.requirement_key: a for a in s.scalars(
                select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if a.requirement_key
        }
        # Actions queued before this column existed are adopted rather than duplicated. The
        # first version of this matched them on their full text, which protects every action
        # whose wording is unchanged and fails for the one that made this fix necessary: the
        # fee request's text moved with the catalogue, so it would have matched nothing and
        # been added beside the row it replaces. Production held exactly that row.
        #
        # So a keyless row is matched on a prefix that no derived figure reaches. The
        # prefixes are asserted distinct by a test, because a prefix match that hit two
        # requests would adopt one row into the wrong decision.
        keyless = [a for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if not a.requirement_key]
        for request in requests:
            if request.key in open_actions:
                continue
            for row in keyless:
                if row.action[:ADOPT_PREFIX] == request.action[:ADOPT_PREFIX]:
                    row.requirement_key = request.key
                    open_actions[request.key] = row
                    break

        for request in requests:
            existing = open_actions.get(request.key)
            if existing is not None:
                # Same decision, possibly a different figure. Restate it in place: the owner
                # should see the number they would actually be charged, not two of them.
                if (existing.action != request.action
                        or existing.max_cost_cad != request.max_cost_cad):
                    existing.action = request.action
                    existing.reason = request.reason
                    existing.max_cost_cad = request.max_cost_cad
                    existing.minutes = request.minutes
                    existing.consequence_of_delay = request.consequence_of_delay
                    existing.blocks = request.blocks
                    restated.append(request.key)
                continue
            s.add(OwnerAction(requirement_key=request.key, action=request.action,
                              reason=request.reason,
                              max_cost_cad=request.max_cost_cad, minutes=request.minutes,
                              consequence_of_delay=request.consequence_of_delay,
                              blocks=request.blocks))
            queued.append(request.key)

        # Close what is no longer asked for. Without this the queue only ever grows: a
        # request stops being generated the moment its requirement is satisfied, but the row
        # it created stays open forever, so the owner opens the queue and is asked again for
        # the Etsy shop that exists, the developer app that is working and the model key that
        # is spending money. The owner's standing instruction is "do not ask me to repeat an
        # action already completed", and production was breaking it in four of ten rows.
        #
        # Guarded, because "not requested" and "not assessed" look identical from here. An
        # assessment that produced no requests at all is far more likely to be an assessment
        # that failed than a company with nothing left for its owner to do, and closing the
        # whole queue on that would destroy the record of what was asked.
        closed: list[str] = []
        kept_open_not_ours: list[str] = []
        if requests:
            wanted = {r.key for r in requests}

            # A3-03: default-keep. This closer may close ONLY an action it owns -- a key in
            # READINESS_OWNED_ACTIONS -- and only when that key's own condition re-check,
            # run now, proves the condition cleared. Every other owner action (correction
            # notices, stranded test drafts, spend ceilings, ad scaling, club decisions,
            # Search Visibility readings, improvement cards, Etsy queue items, ...) is closed
            # by the producer that raised it, on its evidence, or by the owner. "Not asked
            # for by this assessment" is no longer read as "satisfied".
            held_by_incident = _owner_actions_held_open_by_incidents(s)
            for key, row in open_actions.items():
                if key in wanted:
                    continue
                if key in held_by_incident:
                    # F-541: an open incident naming this action is its condition, now.
                    continue
                if key in withheld:
                    # withheld is not done: the request is not being made yet, and marking
                    # its earlier row done would read as the owner having completed it
                    continue
                if not readiness_may_close(key, readiness):
                    kept_open_not_ours.append(key)
                    continue
                row.done = True
                closed.append(key)

    # F-593 / F-547: the Etsy owner-only queue from `intel.etsy_surfaces`, adopted into the
    # one owner queue by key. Idempotent; closed only on evidence (see runtime.etsy_ops).
    # F-874: the KYC/tax and payout-settings steps are first-sale blockers, not launch-day
    # chores. They are queued only at the step before first sale (a listing exists on Etsy),
    # never on every daily run of a shadow shop; software never performs them either way.
    first_sale_step = _first_sale_step_reached(ctx.db)
    etsy_queue = etsy_ops.seed_owner_queue(
        ctx.db, defer=frozenset() if first_sale_step["reached"] else DEFERRED_UNTIL_FIRST_SALE)
    etsy_queue["first_sale_step"] = first_sale_step

    ctx.audit("launch.assessed", detail={
        "ready": ready,
        "rollback_rehearsed": rehearsed,
        "launch_package_blocked": package_blocked,
        "owner_requests_withheld_until_package_ready": withheld,
        "ready_before_off_device_proof": bool(readiness.ready),
        "off_device_proof": {k: off_device.get(k) for k in (
            "key", "blocking", "status", "unmet", "window_hours", "evidence", "why")},
        "ours_to_do": [r.key for r in readiness.buildable],
        "blocked_on_owner": [r.key for r in readiness.blocked_on("owner")],
        "blocked_on_integration": [r.key for r in readiness.blocked_on("integration")],
        "owner_actions_added": len(queued),
        "owner_actions_queued": queued,
        "owner_actions_restated": restated,
        "owner_actions_closed": closed,
        "owner_actions_kept_open_not_readiness_owned": kept_open_not_ours,
        "etsy_owner_queue": etsy_queue,
        "capabilities_unavailable": access.unmet_report()["unmet_capabilities"]})

    outstanding = [r.key for r in readiness.outstanding]
    if off_device["status"] != autonomy.PROVEN:
        outstanding.append(autonomy.LAUNCH_ITEM_KEY)
    # #259: the four before-the-first-customer priorities are launch items, each with the
    # blocker its evidence names. #17: whether paid traffic may be bought is read here too, so
    # the launch report says whether the shop is finished enough for ads, not only for buyers.
    from ..commerce import first_hundred, trust

    before = first_hundred.before_the_first_customer(db=ctx.db)
    outstanding += [f"first_hundred:{p}" for p in before["outstanding"]]
    paid = trust.may_scale_ads(ctx.db, disclosure_ok=not any(
        p == "truthful_expectations" for p in before["outstanding"]))
    ctx.audit("launch.first_customer", detail={
        "outstanding": before["outstanding"],
        "blockers": {r["priority"]: r["blocker"] for r in before["priorities"]
                     if not r["ready"]},
        "paid_traffic_may_scale": paid["may_scale"], "paid_traffic_blocking": paid["blocking"]})
    return {"ready": ready, "owner_actions_added": len(queued),
            "owner_actions_closed": closed,
            "outstanding": outstanding,
            "first_customer": {"outstanding": before["outstanding"],
                               "ready": before["ready"], "of": before["of"]},
            "paid_traffic": {"may_scale": paid["may_scale"], "blocking": paid["blocking"]},
            "blocking_items": [{"key": off_device["key"], "status": off_device["status"],
                                "unmet": off_device["unmet"], "why": off_device["why"]}]}


@handlers.register("chain.rebuild")
def handle_chain_rebuild(ctx: JobContext) -> dict:
    """Re-drive the post-certification chain for releases the current chain never reached.

    Certification is keyed per slug and version, correctly: a pattern is certified once. But
    everything *after* certification — assets, pricing, listing, launch, content — can change
    when the code changes, and a product certified under an older chain would otherwise never
    receive any of it.

    Production proved the need. Fifteen products were certified before listing imagery, search
    coverage and the content ecosystem existed. The next cycle ran, reported success, and
    produced nothing, because `gate.certify` had already run for those versions and so the
    downstream work was never enqueued.

    This looks for certified releases with no listing at the current chain version and starts
    them at `listing.draft`. It is idempotent: a release that already has one is left alone.

    C-69 (#172): a job enqueued by the dependency graph carries the exact stale artefacts, the
    old and new fingerprints and the reason; those inputs are honoured (`_targeted_rebuild`),
    and a release withheld by the teardown QA (#163) is never re-driven by either mode.
    """
    if ctx.job.inputs.get("artefacts") or ctx.job.inputs.get("artefact_key"):
        return _targeted_rebuild(ctx)

    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..gates.certificate import DOC_VERSION
    from ..publish import withholding
    from .pipeline import _engineered_cir

    # A request that names products (growth.steer's fast lane, #291: `slugs`) is scoped to
    # them. It used to fall through to the whole-catalogue scan, so "start this admitted
    # product's chain now" quietly meant "re-examine every release" (Codex G03). A request
    # naming products none of which exist is an error to record, not a scan.
    requested = ctx.job.inputs.get("slugs")
    scope = set(requested) if requested else None

    with ctx.db.session() as s:
        products = {p.id: p.slug for p in s.scalars(select(Product))}
        if scope is not None:
            known = set(products.values())
            unknown = sorted(scope - known)
            if unknown and not (scope & known):
                ctx.audit("chain.rebuild_refused", detail={
                    "reason": "requested slugs name no product", "slugs": sorted(scope),
                    "source": ctx.job.inputs.get("source")})
                return {"started": [], "scope": sorted(scope), "unknown": unknown,
                        "refused": "requested slugs name no product"}
            products = {pid: sl for pid, sl in products.items() if sl in scope}
        certified = [pv for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))  # noqa: E712
            if pv.product_id in products]
        # Current, not merely present. An earlier version of this looked only for *missing*
        # listings and so left every stale one exactly as it was: the fix reached nothing, and
        # a stuttering title stayed on every shipped product through two deploys.
        # Current means built by this chain *from this release*. The chain version catches a
        # code change; the release hash catches a design change, which keeps the same slug
        # and the same version and so is invisible to the chain version alone.
        # What each existing listing was actually built from. Staleness is then a comparison
        # rather than a guess, and the comparison is recorded: a rebuild that says "nothing
        # to do" without showing its reasoning is unfalsifiable from outside the process,
        # and this decision has now been wrong twice.
        built_from = {
            (l.product_slug, l.version): f"c{l.chain_version}:{l.release_hash or 'none'}"
            for l in s.scalars(select(Listing))
        }

    started: list[str] = []
    reasons: dict[str, str] = {}
    withheld_releases: list[str] = []
    for pv in certified:
        slug = products.get(pv.product_id)
        if not slug:
            continue
        # #163 / #228 (C-67, M10): the release's one withholding record, every build-blocking
        # reason on it, with the owner's ruling re-read; the rebuild must not draft the
        # listing any of them refused.
        withheld = withholding.current(ctx.db, slug, pv.version, stage="chain.rebuild")["summary"]
        if withheld:
            reasons[slug] = "withheld: " + str(withheld)[:120]
            withheld_releases.append(f"{slug}@{pv.version}")
            continue
        wanted = f"c{CHAIN_VERSION}:{pv.release_hash or 'none'}"
        actual = built_from.get((slug, pv.version), "missing")
        if actual == wanted:
            reasons[slug] = "current"
            continue
        token = hashlib.sha256(f"{actual}->{wanted}".encode()).hexdigest()[:12]
        # The key names the *transition*, not the destination. Keying it on the destination
        # alone is what stopped the previous fix from delivering itself: the listing had
        # already been built from this release once, so the key was taken, and a listing
        # that went stale for any other reason could never be rebuilt. Keyed this way the
        # job is enqueued once per stale state rather than once per cadence.
        job = ctx.enqueue("listing", "listing.draft",
                          {"slug": slug, "version": pv.version,
                           "release": pv.release_hash or "", "rebuild": token},
                          idempotency_key=chain_key("listing", slug, pv.version,
                                                    pv.release_hash or "", token))
        if job is not None:
            started.append(f"{slug}@{pv.version}")
            reasons[slug] = f"{actual} -> {wanted}: restarted"
        else:
            # Stale, and this exact transition has already been attempted: the key is taken
            # by a job that ran and did not deliver the transition. That is a different
            # situation from a stale listing nobody has tried yet, and reporting them
            # identically is what made this invisible -- the rebuild said "stale" for a
            # product whose rebuild had already run twice and been refused downstream, and
            # from the audit record alone the two were indistinguishable.
            #
            # It is not an error. `assets.build` stopping on blocked imagery is the system
            # working: a listing whose pictures misrepresent the pattern must not proceed.
            # But it means this rebuild cannot fix it, and the thing that can is a code
            # change -- which arrives as a CHAIN_VERSION bump, changing `wanted`, the
            # transition and therefore the key.
            reasons[slug] = (f"{actual} -> {wanted}: already attempted under this chain "
                             f"version and not delivered; a downstream stage refused it")

    # A stored design the code no longer produces, or a certificate issued against a
    # document the writer no longer writes. Restarting at `listing.draft` cannot fix either,
    # because both live *above* certification: the CIR in the database is the stale thing.
    # This is the fifth face of "code changed, the deployed database did not", and the one
    # that broke the previous four fixes' own delivery mechanism.
    redrafted: list[str] = []
    for pv in certified:
        slug = products.get(pv.product_id)
        if not slug:
            continue
        try:
            fresh = _engineered_cir(slug, pv.version)
        except Exception:  # noqa: BLE001 - a design that no longer builds is not a rebuild
            continue
        if fresh is None:
            continue
        stale_design = fresh.to_dict() != pv.cir_json
        stale_document = (pv.certificate or {}).get("doc_version") != DOC_VERSION
        if not (stale_design or stale_document):
            continue
        job = ctx.enqueue("crochet_engineer", "cir.draft", {"slug": slug},
                          idempotency_key=(f"redraft:{slug}:{fresh.fingerprint}"
                                           f":d{DOC_VERSION}"))
        if job is not None:
            redrafted.append(f"{slug}@{pv.version}"
                             f"{' design' if stale_design else ''}"
                             f"{' document' if stale_document else ''}")

    # Collections are listed under the pseudo-version "collection" rather than a
    # PatternVersion, so they need their own line here or a rebuild leaves the bundle behind.
    collections_started: list[str] = []
    for seed in POOL:
        if not seed.is_bundle:
            continue
        # A collection has no release of its own -- it is its members -- so "built by this
        # chain" is the whole of the check.
        if built_from.get((seed.slug, "collection"), "missing").startswith(
                f"c{CHAIN_VERSION}:"):
            continue
        job = ctx.enqueue("listing", "collection.assemble",
                          {"slug": seed.slug, "family": seed.family},
                          idempotency_key=chain_key("collection", seed.slug, "collection"))
        if job is not None:
            collections_started.append(seed.slug)

    ctx.audit("chain.rebuilt", detail={"chain_version": CHAIN_VERSION,
                                       "doc_version": DOC_VERSION,
                                       "certified": len(certified),
                                       "restarted": started[:20],
                                       "restarted_count": len(started),
                                       "redrafted": redrafted[:20],
                                       "redrafted_count": len(redrafted),
                                       "collections_restarted": collections_started,
                                       "withheld": withheld_releases,
                                       "listings": reasons})
    return {"chain_version": CHAIN_VERSION, "doc_version": DOC_VERSION,
            "certified": len(certified), "restarted": started,
            "redrafted": redrafted, "collections_restarted": collections_started,
            "withheld": withheld_releases}


# C-69 (#172): which chain stage re-derives each artefact class. Each stage cascades to the
# stages after it, so a rebuild enqueues the *earliest* stage any stale artefact needs and no
# other -- a stale marketing asset alone restarts pricing (which re-drives the listing, the
# support knowledge, the launch plan, the content and the release bundle from the current
# release), not the certificate.
REBUILD_STAGE: dict[str, str] = {
    "twin": "gate.certify", "geometry_proof": "gate.certify",
    "reverse_result": "gate.certify", "certificate": "gate.certify",
    "pdf": "assets.build", "chart": "assets.build", "visual_truth": "assets.build",
    "pricing": "pricing.position", "listing_copy": "pricing.position",
    "seo": "pricing.position", "support_knowledge": "pricing.position",
    "marketing_asset": "pricing.position", "release_bundle": "pricing.position",
}
STAGE_ORDER = ("gate.certify", "assets.build", "pricing.position")
STAGE_AGENT = {"gate.certify": "quality_director", "assets.build": "publishing",
               "pricing.position": "pricing"}
# How many times the rebuild comes back to collect completion evidence before it raises.
REBUILD_VERIFY_ATTEMPTS = 3
REBUILD_VERIFY_DELAY_MINUTES = 20
REBUILD_INCOMPLETE_SIGNATURE = "rebuild-incomplete"


def _targeted_rebuild(ctx: JobContext) -> dict:
    """Rebuild exactly the artefacts the dependency graph named, and prove each one was.

    Reads `ctx.job.inputs`: `product_slug`, `artefacts` (node keys 'class:key'; or the
    per-artefact form `artefact_class`/`artefact_key`), `fingerprints` ({ref: {old, new}}),
    `reason`. Per artefact it records the request (`chain.rebuild_requested`, with the old and
    new fingerprints, the reason and the stage job that will remake it). A later run of the
    same job with `verify` reads the provenance rows back and writes completion evidence per
    artefact (`chain.rebuild_completed`: the row's new inputs, build time and the job that
    wrote it), or raises an incident when the artefacts are still stale after
    REBUILD_VERIFY_ATTEMPTS checks. A withheld release (#163) is refused and audited.
    """
    from datetime import timedelta as _td

    from sqlalchemy import desc, select

    from ..core.models import (ArtefactProvenance, Incident, Job, JobStatus, PatternVersion,
                               Product, utcnow)
    from ..ops import artefacts as provenance

    i = dict(ctx.job.inputs)
    slug = i.get("product_slug") or i.get("slug") or ""
    keys = list(i.get("artefacts") or [])
    if not keys and i.get("artefact_key"):
        keys = [f"{i['artefact_class']}:{i['artefact_key']}"]
    fingerprints = dict(i.get("fingerprints") or {})
    reason = str(i.get("reason") or "")
    verify = int(i.get("verify") or 0)

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id)
                       .order_by(desc(PatternVersion.id)).limit(1))
              if product is not None else None)
        version = pv.version if pv is not None else ""
        release = pv.release_hash or "" if pv is not None else ""
        cir_json = dict(pv.cir_json) if pv is not None else None
        current = provenance.current_from_db(s)
        verdicts = {f"{v.artefact_class}:{v.artefact_key}": v
                    for v in provenance.check(s, current=current)}
        rows = {f"{r.artefact_class}:{r.artefact_key}": r for r in s.scalars(
            select(ArtefactProvenance).where(ArtefactProvenance.product_slug == slug))}
        row_facts = {k: {"inputs": dict(r.inputs or {}), "built_at": str(r.built_at),
                         "job_id": r.job_id, "created_by": r.created_by}
                     for k, r in rows.items()}

    if pv is None:
        ctx.audit("chain.rebuild_refused", artifact=slug,
                  detail={"why": "no stored release for this product", "artefacts": keys})
        return {"targeted": True, "slug": slug, "refused": "no stored release"}
    # #163 / #228 (C-67, M10): every build-blocking reason on the release's one withholding
    # record, the owner's ruling re-read, not a field one stage happened to write.
    from ..publish import withholding

    withheld = withholding.current(ctx.db, slug, version, stage="chain.rebuild")["summary"]
    if withheld:
        ctx.audit("chain.rebuild_refused", artifact=f"{slug}@{version}",
                  detail={"why": f"release withheld (#163/#228): {str(withheld)[:200]}",
                          "artefacts": keys, "reason": reason})
        return {"targeted": True, "slug": slug, "version": version, "withheld": True,
                "rebuilt": []}

    fresh_now = [k for k in keys if k in verdicts and verdicts[k].state == provenance.FRESH]

    # C-80 defect 12 (Codex P10): completion evidence is bound to *this* attempt. A row counts
    # as rebuilt only when (a) for every requested reference the row's recorded input equals
    # the fingerprint the request said it must become, and (b) on a verify pass, the row was
    # written by the stage job this attempt enqueued or a job enqueued after it -- never by
    # whatever happened to leave the row fresh before the request.
    def binding(k) -> dict:
        facts = row_facts.get(k) or {}
        inputs = facts.get("inputs") or {}
        mismatched = sorted(ref for ref, fp in fingerprints.items()
                            if isinstance(fp, dict) and fp.get("new")
                            and inputs.get(ref) != fp["new"])
        after = i.get("stage_job") or i.get("requested_by")
        row_job = facts.get("job_id")
        job_bound = (not verify) or (after is not None and row_job is not None
                                     and int(row_job) >= int(after))
        return {"fingerprints_match": not mismatched, "mismatched_refs": mismatched,
                "stage_job": i.get("stage_job"), "requested_by": i.get("requested_by"),
                "row_job": row_job, "job_bound": job_bound,
                "bound": not mismatched and job_bound}

    bindings = {k: binding(k) for k in fresh_now}
    fresh = [k for k in fresh_now if bindings[k]["bound"]]
    unbound = [k for k in fresh_now if not bindings[k]["bound"]]
    stale = [k for k in keys if k not in fresh]

    if verify:
        for k in fresh:
            ctx.audit("chain.rebuild_completed", artifact=k, detail={
                "product_slug": slug, "version": version, "reason": reason,
                "fingerprints": fingerprints, "evidence": row_facts.get(k),
                "bound": bindings[k], "verified_on_check": verify})
        for k in unbound:
            ctx.audit("chain.rebuild_unbound", artifact=k, detail={
                "product_slug": slug, "version": version, "reason": reason,
                "fingerprints": fingerprints, "evidence": row_facts.get(k),
                "bound": bindings[k], "check": verify,
                "why": "the row reads fresh but was not produced by this attempt's stage "
                       "job, or its inputs are not the fingerprints the request named"})
        if stale and verify < REBUILD_VERIFY_ATTEMPTS:
            ctx.enqueue("listing", "chain.rebuild", {**i, "artefacts": stale,
                                                     "verify": verify + 1},
                        idempotency_key=(f"rebuild-verify:{slug}:{ctx.job.id}:"
                                         f"{verify + 1}"),
                        run_after=utcnow() + _td(minutes=REBUILD_VERIFY_DELAY_MINUTES))
        elif stale:
            with ctx.db.session() as s:
                sig = f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}"
                inc = s.scalar(select(Incident).where(Incident.signature == sig,
                                                      Incident.resolved.is_(False)))
                if inc is None:
                    s.add(Incident(severity="P2", signature=sig, halts_publication=True,
                                   summary=(f"{len(stale)} artefact(s) of {slug} still carry "
                                            f"a moved input after {verify} rebuild checks: "
                                            f"{stale[:5]}"),
                                   detail={"stale": stale, "reason": reason,
                                           "fingerprints": fingerprints}))
                else:
                    inc.report_count += 1
        ctx.audit("chain.rebuild_verified", artifact=f"{slug}@{version}", detail={
            "completed": fresh, "outstanding": stale, "unbound": unbound, "check": verify})
        return {"targeted": True, "verify": verify, "slug": slug, "completed": fresh,
                "outstanding": stale, "unbound": unbound}

    classes = {k.split(":", 1)[0] for k in stale}
    unknown = sorted(c for c in classes if c not in REBUILD_STAGE)
    stages = [st for st in STAGE_ORDER if any(REBUILD_STAGE.get(c) == st for c in classes)]
    stage = stages[0] if stages else None
    token = hashlib.sha256(json.dumps(
        {"artefacts": sorted(stale), "fingerprints": fingerprints},
        sort_keys=True, default=str).encode()).hexdigest()[:12]
    stage_job = None
    if stage == "gate.certify":
        stage_job = ctx.enqueue(STAGE_AGENT[stage], stage, {"cir": cir_json},
                                idempotency_key=f"rebuild-cert:{slug}:{version}:{token}")
    elif stage == "assets.build":
        stage_job = ctx.enqueue(STAGE_AGENT[stage], stage,
                                {"slug": slug, "version": version, "release": release,
                                 "rebuild": token},
                                idempotency_key=chain_key("assets", slug, version, release,
                                                          token))
    elif stage == "pricing.position":
        # Pricing and everything after it read what assets.build measured; the latest
        # completed build's own payload is that measurement.
        with ctx.db.session() as s:
            built = next((dict(j.outputs or {}) for j in s.scalars(
                select(Job).where(Job.job_type == "assets.build",
                                  Job.status == JobStatus.DONE).order_by(desc(Job.id)))
                if (j.outputs or {}).get("slug") == slug
                and (j.outputs or {}).get("version") == version
                and (j.outputs or {}).get("pdf_sha256")), None)
        if built is None:
            stage = "assets.build"
            stage_job = ctx.enqueue("publishing", stage,
                                    {"slug": slug, "version": version, "release": release,
                                     "rebuild": token},
                                    idempotency_key=chain_key("assets", slug, version,
                                                              release, token))
        else:
            stage_job = ctx.enqueue(STAGE_AGENT[stage], stage,
                                    {**built, "release": release, "rebuild": token},
                                    idempotency_key=chain_key("price", slug, version,
                                                              release, token))
    for k in stale:
        ctx.audit("chain.rebuild_requested", artifact=k, detail={
            "product_slug": slug, "version": version, "reason": reason,
            "fingerprints": fingerprints, "old_inputs": (row_facts.get(k) or {}).get("inputs"),
            "stage": REBUILD_STAGE.get(k.split(":", 1)[0]), "enqueued_stage": stage,
            "stage_job": getattr(stage_job, "id", None)})
    for k in fresh:
        ctx.audit("chain.rebuild_completed", artifact=k, detail={
            "product_slug": slug, "version": version, "reason": reason,
            "fingerprints": fingerprints, "evidence": row_facts.get(k),
            "bound": bindings[k], "already_fresh": True})
    if stale:
        # the verify pass carries the attempt it must bind completion to
        ctx.enqueue("listing", "chain.rebuild", {**i, "artefacts": stale, "verify": 1,
                                                 "stage_job": getattr(stage_job, "id", None),
                                                 "requested_by": ctx.job.id},
                    idempotency_key=f"rebuild-verify:{slug}:{ctx.job.id}:1",
                    run_after=utcnow() + _td(minutes=REBUILD_VERIFY_DELAY_MINUTES))
    return {"targeted": True, "slug": slug, "version": version, "reason": reason,
            "requested": stale, "already_fresh": fresh, "stage": stage,
            "fresh_but_unbound": unbound,
            "stage_job": getattr(stage_job, "id", None), "unknown_classes": unknown}


@handlers.register("ops.policy_watch")
def handle_policy_watch(ctx: JobContext) -> dict:
    """Check how old this company's reading of Etsy's rules is, and block what it must.

    Requirement 39. Deliberately does *not* fetch: no policy fetcher is connected, and a
    cadence that fails on every run because a dependency is absent is a dead letter with a
    schedule. What it does is the part that does not need the network — notice that a reading
    is stale or missing, and open a blocking incident for the workflows that reading governs.

    The incident is per source and opened once. A blocking incident re-raised every six hours
    is an alert people filter, which is the same as no alert but with more rows.

    GREEN by the authority matrix: it reads its own tables, writes audit rows and opens
    incidents. It fetches nothing, publishes nothing and spends nothing.
    """
    from sqlalchemy import select

    from ..core.models import Incident, utcnow
    from ..gates.platform_policy import MAX_AGE_DAYS, POLICY_SOURCES, freshness
    from ..gates import policy_knowledge

    # A reading recorded in the repository (dated, sourced, digested, with its basis declared)
    # is a reading: seeded once for a source nobody has ever read, never over a page reading,
    # and reported stale on the same 30-day rule as any other snapshot.
    seeded = policy_knowledge.seed_snapshots(ctx.db)
    report = freshness(ctx.db)
    unread = list(report["never_checked"])
    stale = [e["source"] for e in report["stale"]]
    needs_attention = unread + stale

    opened: list[str] = []
    resolved: list[str] = []
    with ctx.db.session() as s:
        open_signatures = {
            i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved == False))  # noqa: E712
        }
        # A policy incident closes only with the evidence that opened it reversed: the source
        # now has a current snapshot. The resolution names the snapshot and its basis.
        current = {e["source"]: e for e in report["current"]}
        for inc in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            if not inc.signature.startswith("policy_stale:"):
                continue
            source = inc.signature.split(":", 1)[1]
            if source in current:
                detail = dict(inc.detail or {})
                detail["resolution"] = (f"{source} read on {current[source]['checked_on']} (version {current[source]['version']}); "
                                        f"the watch reports it current")
                detail["resolved_at"] = utcnow().isoformat()
                inc.detail = detail
                inc.resolved = True
                resolved.append(source)
        for source in needs_attention:
            signature = f"policy_stale:{source}"
            if signature in open_signatures:
                continue
            affects = ", ".join(POLICY_SOURCES[source][1])
            why = ("has never been read" if source in unread
                   else f"was last read more than {MAX_AGE_DAYS} days ago")
            s.add(Incident(
                severity="P2", signature=signature,
                summary=(f"Etsy {source.replace('_', ' ')} {why}. Until it is, "
                         f"{affects} cannot be certified against current policy, and a new "
                         f"asset or product class cannot be enabled (#35, #39)."),
                halts_publication=False,
                detail={"source": source, "url": POLICY_SOURCES[source][0],
                        "affects": list(POLICY_SOURCES[source][1]),
                        "owner_action": ("connect a policy reader, or read the page and "
                                         "record the snapshot by hand"),
                        "freshness": report}))
            opened.append(source)

    # #39: a material change -- a digest difference from the previous reading -- opens one
    # blocking incident per source until somebody records it reviewed and tested. The
    # incident halts publication; `release_gates.staleness` and `check_new_class` refuse on
    # the same unreviewed change, so the block is enforced where the workflows run.
    from ..gates.platform_policy import CHANGE_SIGNATURE, unreviewed_changes
    from ..ops import incident_lifecycle as lifecycle

    changed = {f"{CHANGE_SIGNATURE}{c['source']}": c for c in unreviewed_changes(ctx.db)}
    with ctx.db.session() as s:
        change_life = lifecycle.reconcile(
            s, CHANGE_SIGNATURE, lambda inc: inc.signature in changed,
            resolution="the material policy change was reviewed and the affected workflows "
                       "re-tested (review recorded on the snapshot)")
        changes_opened = []
        for signature, c in changed.items():
            _row, new = lifecycle.open_or_restate(
                s, signature=signature, severity="P1", halts_publication=True,
                summary=(f"Etsy {c['source'].replace('_', ' ')} changed materially "
                         f"(reading {c['checked_on']}, version {c['version']}). "
                         f"{', '.join(c['affects'])} are blocked until the change is "
                         f"reviewed and tested (#39)."),
                detail=c)
            if new:
                changes_opened.append(c["source"])

    ctx.audit("policy.watched", detail={
        "changes_opened": changes_opened, "changes_resolved": change_life["resolved"],
        "all_fresh": report["all_fresh"], "never_checked": unread, "stale": stale,
        "incidents_opened": opened, "incidents_resolved": resolved, "seeded": seeded["seeded"],
        "blocked_workflows": report["blocked_workflows"]})

    return {"all_fresh": report["all_fresh"], "never_checked": unread, "stale": stale,
            "changes_opened": changes_opened, "changes_unreviewed": sorted(
                c["source"] for c in changed.values()),
            "incidents_opened": opened, "incidents_resolved": resolved, "seeded": seeded["seeded"],
            "blocked_workflows": report["blocked_workflows"],
            "note": ("This cadence does not fetch: direct retrieval is refused by Etsy's bot "
                     "protection (recorded in gates.policy_knowledge.RETRIEVAL_BLOCK). It seeds the "
                     "repository's dated reading of a source nobody has read, and otherwise "
                     "reports staleness honestly.")}


@handlers.register("build.tick")
def handle_build_tick(ctx: JobContext) -> dict:
    """The never-idle build loop's heartbeat, running in the deployed worker.

    Reconciles the task graph against the registry and the owner gates, then reports what is
    ready, what is parked and whether the loop is actually moving. It deliberately does *not*
    write code -- that is what a session does. What it does is make the decision about *what
    to work on next* survive the session ending, which is the part that used to live in a
    conversation and evaporate with it.

    A gate that opened since the last tick un-parks its requirements here, with nobody having
    to remember. A loop that has completed nothing while work is ready raises an incident; a
    loop that has completed nothing because everything is parked does not, because those are
    opposite situations that look identical from outside.

    GREEN by the authority matrix: it reads the registry, writes its own tables and may open
    an incident. It publishes nothing, spends nothing and contacts nobody.
    """
    from ..build2 import executor

    synced = executor.sync(ctx.db)
    snapshot = executor.queue(ctx.db)
    health = executor.watchdog(ctx.db)

    # The canonical-model approval is *derived* here rather than only raised by the build
    # that produced the pack, because a question raised by an event survives exactly as
    # long as nothing else touches it. The readiness assessment closed this one, and the
    # pack build does not run again once a pack is on file -- so the row stayed shut with
    # a ready pack sitting behind it and nothing to reopen it. A condition that is still
    # true should keep asking; that is what a tick is for.
    _reconcile_canonical_model_action(ctx.db)

    if synced["unparked"]:
        executor.record(
            ctx.db, kind="unpark",
            summary=(f"{len(synced['unparked'])} requirements un-parked because their gate "
                     f"opened: {synced['unparked'][:10]}"),
            detail={"requirement_ids": synced["unparked"],
                    "gates_open": synced["gates_open"]})

    # Three verdicts, three responses. Only a claimed task that made no progress is an
    # incident. Ready work nobody has claimed is waiting for a build session -- the deployed
    # worker does not write code -- so it becomes an operator note naming where to start,
    # not a P2 about how often somebody opens a session. Every other verdict closes a stall
    # that is open, and says why it closed.
    from ..ops import incident_lifecycle

    operator_note = None
    lifecycle: dict = {}
    with ctx.db.session() as s:
        if health.get("alarm"):
            held = health.get("in_progress") or []
            incident_lifecycle.open_or_restate(
                s, signature="build.stalled", severity="P2",
                summary=(f"Build work was claimed and nothing has been completed in "
                         f"{health['window_hours']} hours "
                         f"({health.get('claims_in_window', 0)} claim(s) in the window, "
                         f"{len(held)} task(s) in progress: "
                         f"{[h['requirement_id'] for h in held][:10]}). A claim is a "
                         f"promise to make progress; a claim with no completion is a "
                         f"worker that took the task and stopped."),
                detail={"watchdog": health, "next": health.get("next")})
        else:
            verdict = health.get("verdict")
            top = (health.get("next") or {}).get("requirement_id")
            if verdict == executor.AWAITING_BUILD_SESSION:
                operator_note = (f"{health['ready_total']} requirements are ready and none "
                                 f"is claimed; the next build session should start with "
                                 f"#{top}.")
            reason = {
                "moving": (f"the loop is moving: {health.get('completions_in_window')} "
                           f"completion(s) in the last {health.get('window_hours')} hours"),
                executor.AWAITING_BUILD_SESSION: (
                    f"no task is claimed, so nothing is stalled: {health.get('ready_total')} "
                    f"requirements are ready and waiting for a build session (the deployed "
                    f"worker does not write code). Top ready: #{top}"),
                "waiting_on_owner": ("nothing is ready: every remaining requirement is "
                                     "parked on a gate, which is waiting rather than a stall"),
                "finished": "nothing is ready, parked or in progress: the queue is empty",
            }.get(verdict, f"watchdog verdict is {verdict!r}, which is not a stall")
            lifecycle = incident_lifecycle.reconcile(
                s, "build.stalled", lambda _row: False, resolution=reason)

    ctx.audit("build.ticked", detail={
        "ready": snapshot["ready_total"], "parked": snapshot["parked_total"],
        "blocked": snapshot["blocked_total"], "done": snapshot["done_total"],
        "unparked": synced["unparked"], "verdict": health["verdict"],
        "next": (snapshot["next"] or {}).get("requirement_id"),
        "operator_note": operator_note,
        "stall_resolved": lifecycle.get("resolved") or []})

    return {"ready": snapshot["ready_total"], "parked": snapshot["parked_total"],
            "blocked": snapshot["blocked_total"], "done": snapshot["done_total"],
            "parked_by_gate": snapshot["parked_by_capability"],
            "unparked": synced["unparked"],
            "next": snapshot["next"], "watchdog": health,
            "operator_note": operator_note}


@handlers.register("creative.blinded")
def handle_creative_blinded(ctx: JobContext) -> dict:
    """Judge this catalogue against the observed human one, blinded (#94).

    Monthly rather than weekly. Creative capability does not change in a week, and a
    measurement that costs real money every seven days becomes a line item somebody
    eventually switches off -- which is worse than a slower measurement that survives.

    GREEN: it reads its own catalogue and an already-observed benchmark, spends model budget
    bounded by the monthly ceiling, and writes a row. It publishes nothing and contacts
    nobody. If the ceiling is close it judges fewer pairs and says so; a run that reports
    `unmeasured` because it could not afford the floor is the correct outcome, not a failure.
    """
    from ..creative import blinded
    from ..creative.audit import catalogue_concepts
    from ..gateway import failover

    # The tier the task is routed to, rather than a model named here. Routing decides which
    # model answers which question and prices it; a handler picking its own would make the
    # ceiling's estimate a guess about a different call than the one being made.
    # W-8: the declared tier first, an approved *stronger* fallback when it is down and the
    # money fits, PARK (retry with backoff) when neither -- never a weaker model.
    gateway = failover.job_gateway(ctx.db, blinded.TASK, registry=ctx.registry,
                                   agent="creative_director", job_id=ctx.job.id)

    concepts = catalogue_concepts()
    try:
        result = blinded.run(ctx.db, concepts, gateway=gateway,
                             agent="creative_director",
                             max_pairs=blinded.MIN_PAIRS)
    except blinded.RunRefused as e:
        ctx.audit("creative.blinded_refused", detail={"reason": str(e)[:300]})
        return {"ran": False, "reason": str(e)[:200]}

    ctx.audit("creative.blinded", detail=result)
    return {"ran": True, "verdict": result["verdict"], "judged": result["pairs_judged"],
            "cost_cad": result["cost_cad"], "valid": result["valid"],
            "gateway_spend_cad": gateway.spend_cad()}


TOURNAMENT_ACTION = "creative.tournament"


@handlers.register("creative.tournament")
def handle_creative_tournament(ctx: JobContext) -> dict:
    """#3's staged tournament, run at its specified scale against one proven arena.

    The expedition asks "what could we make for this occasion" with a handful of deep
    concepts. This asks the harder question the owner put: **is there a Brambleloop answer to
    a proven arena we have no answer to at all**, and it asks it with a field wide enough
    that the answer is not an artefact of the sample.

    Three things make the number mean something this time.

    **The field is wide and cheap.** Roughly eighty concepts at the cheap tier, about CA$0.27,
    because the funnel's whole shape is to spend little across a wide field and concentrate
    cost after it has been cut. Eighty deep-tier concepts would cost nine times as much to
    learn the same thing.

    **It is one arena, not twelve.** A field spread across every department puts two or three
    concepts against each of them, which cannot support a comparison against anything.
    Breadth comes from the wheel moving the arena between cycles -- and the wheel reserves
    45% of its slots for Christmas, so the priority programme gets depth rather than a turn.

    **The gauntlet has something to fire on.** Our catalogue has no garments, so novelty
    against *us* is automatic and `sameness` cannot fire -- which is why the first
    expedition survived 18 of 18 and why that number meant "we have never made one of these"
    rather than "these are good". Screening against the benchmark's own listings is the half
    that can fail, and in a proven arena there are enough of them for it to.

    GREEN: reads observed listings and its own history, bounds spend before every batch,
    writes one row. Publishes nothing, contacts nobody. A tournament that survives nothing is
    stored exactly like one that survives ten.
    """
    from ..core.models import utcnow
    from ..creative import ideation, prospecting
    from ..creative.audit import catalogue_concepts
    from ..gateway import failover

    # C-61: winners that waited on a vision judgement are re-presented first, so a judgement
    # recorded since the last run reaches engineering without waiting for a new winner.
    from ..creative import intake as winner_intake

    regated = winner_intake.regate_held(ctx)

    found = prospecting.arenas(ctx.db)
    if not found:
        return {"ran": False, "reason": "no benchmark listing has been observed yet",
                "regated": regated}

    week = int(utcnow().timestamp() // (7 * 24 * 3600))
    # C-60 (#287): the strike teams' persisted shares decide the priority reservation.
    from ..seasonal.daily import active_shares
    team_shares = active_shares(ctx.db)
    arena = prospecting.choose(found, cycle=week, shares=team_shares)
    # #216: a benchmark release queues a divergent ("breakthrough") tournament with its own
    # arena and briefs. It is honoured rather than replaced by the weekly wheel: the arena the
    # release happened in is taken when it is a proven arena, and its divergent briefs are
    # carried into every generator brief below.
    from ..creative.breakthrough import BREAKTHROUGH_LANE
    inputs = ctx.job.inputs or {}
    from ..intel.mission_runtime import SAME_ARENA_LANE
    # #215: a same-arena response started from a CONCEPTING gap is honoured the same way.
    breakthrough = (inputs if inputs.get("lane") in (BREAKTHROUGH_LANE, SAME_ARENA_LANE,
                                                     "breakout_adjacent")
                    else None)
    if breakthrough:
        match = [a for a in found if a.pod == breakthrough.get("pod")]
        # The mission names the seasonal event its response is for (#309: demand and season
        # fit). When that event is one of the pod's proven arenas it is the arena; the wheel
        # only chooses when the mission named none it can still reach.
        targeted = [a for a in match if a.event == breakthrough.get("seasonal_target")]
        if targeted:
            arena = targeted[0]
        elif match:
            # The same chooser as the wheel, over the release's pod only, so an arena whose
            # event can no longer be made in time is not picked just because it matched.
            arena = prospecting.choose(match, cycle=week, shares=team_shares) or arena

    # Every ideation input is read before anything is generated (#85, #101, #105, #117-#122,
    # #124, #142, #232), and the arena moves if saturation leaves it nothing to enter.
    arena, plan, moved_from = _ideation_arena(ctx, found, arena, kind="tournament",
                                              cycle=week)
    if plan is None:
        return moved_from
    if breakthrough:
        plan["breakthrough"] = {k: breakthrough.get(k) for k in (
            "arena", "pod", "objective", "diverged_from", "briefs", "trigger", "lane",
            "entry_axes", "entry_how")}
    blocked = _ceiling_gate(ctx, plan, arena, kind="tournament")
    if blocked is not None:
        return blocked

    gateway = ideation.BriefingGateway(
        failover.job_gateway(ctx.db, prospecting.IDEATION_TASK, registry=ctx.registry,
                             agent="creative_director", job_id=ctx.job.id), plan)
    catalogue = catalogue_concepts() + prospecting.discovered(ctx.db)
    # #279: the seasonal transformations `seasonal.remerchandising` derived for this event
    # enter the field as entrants, and the funnel judges them beside the generated concepts.
    from ..seasonal import remerchandising as _rm

    seeded = _rm.derived_children(ctx.db, event=arena.event, pod=arena.pod)

    try:
        result = prospecting.tournament(
            ctx.db, gateway=gateway, catalogue=catalogue,
            only=(arena.event, arena.pod),
            exclude_forms=tuple(plan["saturation"]["excluded_forms"]), seeded=seeded)
    except prospecting.ProspectingRefused as e:
        ctx.audit("creative.tournament_blocked",
                  detail={"arena": arena.to_dict(), "reason": str(e)[:400],
                          "ideation": ideation.record(plan, gateway=gateway, selection=None,
                                                      gate=None)})
        return {"ran": False, "arena": f"{arena.event}/{arena.pod}",
                "reason": str(e)[:200]}

    selection = ideation.select(plan, candidates=result.get("candidate_objects") or [],
                                survivors=result.get("survivor_objects") or [],
                                window=result.get("window"))
    # C-61: the winner is taken into engineering intake -- a brief generated from it and its
    # evidence, the funnel asked whether it was carried to prototype (#3), the
    # pre-engineering gate run with that brief, and `cir.draft` queued only for a winner
    # that clears both. Nothing reaches engineering from here any other way.
    gate, took = _winner_intake(ctx, selection, plan, gateway=gateway, arena=arena,
                                source="creative.tournament",
                                funnel_rounds=result.get("funnel_rounds") or [],
                                mjs_event_id=inputs.get("mjs_event_id"))
    result["ideation"] = ideation.record(plan, gateway=gateway, selection=selection,
                                         gate=gate)
    result["intake"] = took
    result["regated"] = regated
    result["mjs_event_id"] = inputs.get("mjs_event_id")

    with ctx.db.session() as s:
        from ..core.models import AuditLog
        s.add(AuditLog(actor="creative_director", action=TOURNAMENT_ACTION,
                       artifact=f"{arena.event}/{arena.pod}",
                       detail={k: v for k, v in result.items()
                               if not k.endswith("_objects")}))

    # #309: the MJs response this tournament answers moves along its pipeline now, rather
    # than at the next daily sentinel.
    pipeline_moves = None
    if inputs.get("mjs_event_id"):
        from ..intel import mission_runtime

        pipeline_moves = mission_runtime.advance_pipeline(
            ctx.db, event_ids=[int(inputs["mjs_event_id"])])

    generated = result["field"]["generated"]
    attempted = generated > 0 or result["cost_cad"] > 0
    return {"ran": attempted, "arena": f"{arena.event}/{arena.pod}",
            "generated": generated, "survivors": len(result["survivors"]),
            "research_kill_rate": result["research_kill_rate"],
            "causes": result["causes"], "cost_cad": result["cost_cad"],
            "novelty_measurable": result["novelty_measurable"],
            "stages_run": result["stages_run"],
            "stages_not_run": result["stages_not_run"],
            "proposition_refused": result["proposition_refused"],
            "research_survivors": len(result["research_survivors"]),
            "winner": result["ideation"]["winner"],
            "role": plan["role"]["role"],
            "cleared_for_engineering": gate["cleared_for_engineering"],
            "intake": took, "days_to_event": result.get("days_to_event"),
            "pipeline": pipeline_moves, "seeded": result.get("seeded") or {},
            **({} if attempted else
               {"reason": "every batch came back malformed; nothing was generated or spent"})}


@handlers.register("creative.expedition")
def handle_creative_expedition(ctx: JobContext) -> dict:
    """Discovery into one proven-and-unserved arena (#104).

    Weekly, and it rotates: the arena is picked from the top proven gaps by the week number,
    so the catalogue broadens across departments instead of deepening in whichever one ranked
    first the day the cadence was written. Cost is roughly CA$0.32 a run at four slots, which
    is about 6% of the monthly ceiling a month.

    GREEN: it reads an already-observed benchmark and its own history, spends model budget
    bounded before each field, and writes a row. It publishes nothing and contacts nobody.
    An expedition that comes back empty is recorded as such -- that is evidence about this
    system's creative reach, and only keeping the successful runs would leave a record that
    flatters it.
    """
    from ..creative import ideation, prospecting
    from ..creative.audit import catalogue_concepts
    from ..gateway import failover

    # Deliberately not caught. `NoArenasContradictsEvidence` means the matrix disagrees with
    # the catalogue of listings behind it, and a defect that makes discovery report "nothing
    # to do" must fail loudly rather than complete: a job that fails is re-driven by the next
    # deploy, and a job that succeeds with a false negative consumes its window.
    found = prospecting.arenas(ctx.db)
    if not found:
        ctx.audit("creative.expedition_blocked",
                  detail={"reason": "no benchmark listing has been observed yet"})
        return {"ran": False, "reason": "no benchmark listing has been observed yet"}

    from ..core.models import utcnow

    week = int(utcnow().timestamp() // (7 * 24 * 3600))
    from ..seasonal.daily import active_shares
    arena = prospecting.choose(found, cycle=week, shares=active_shares(ctx.db))

    arena, plan, moved_from = _ideation_arena(ctx, found, arena, kind="expedition",
                                              cycle=week)
    if plan is None:
        return moved_from
    from ..creative import intake as winner_intake

    winner_intake.regate_held(ctx)

    blocked = _ceiling_gate(ctx, plan, arena, kind="expedition")
    if blocked is not None:
        return blocked
    # #117: the expedition's arena loses its saturated, angle-less forms before slots exist.
    arena = ideation.restrict(arena, plan["saturation"]["excluded_forms"])

    gateway = ideation.BriefingGateway(
        failover.job_gateway(ctx.db, prospecting.GENERATION_TASK, registry=ctx.registry,
                             agent="creative_director", job_id=ctx.job.id), plan)
    catalogue = catalogue_concepts() + prospecting.discovered(ctx.db)

    try:
        result = prospecting.expedition(ctx.db, arena, gateway=gateway, catalogue=catalogue)
    except prospecting.ProspectingRefused as e:
        ctx.audit("creative.expedition_blocked",
                  detail={"arena": arena.to_dict(), "reason": str(e)[:400],
                          "ideation": ideation.record(plan, gateway=gateway, selection=None,
                                                      gate=None)})
        return {"ran": False, "arena": f"{arena.event}/{arena.pod}", "reason": str(e)[:200]}

    survivors = result.get("survivor_objects") or []
    # The expedition's field is its survivors plus everything the gauntlet killed; only the
    # survivors are objects here, so the field diversity is measured over what it proposed
    # and survived, and says so through `entrants`.
    selection = ideation.select(plan, candidates=survivors, survivors=survivors)
    # An expedition is discovery, not the staged funnel: its winner gets the same generated
    # brief and gate, and `may_engineer` refuses it engineering (#3) -- recorded, not skipped.
    gate, took = _winner_intake(ctx, selection, plan, gateway=gateway, arena=arena,
                                source="creative.expedition", funnel_rounds=None)
    result["ideation"] = ideation.record(plan, gateway=gateway, selection=selection,
                                         gate=gate)
    result["intake"] = took

    prospecting.store(ctx.db, result)

    # A run that proposed nothing and spent nothing did not happen, whatever it returned.
    # The first live expedition reported `ran: true` while both of its fields came back as
    # truncated JSON -- a false success, and the per-deploy re-drive only picks up `ran:
    # false`, so a fixed prompt would have waited a week for its next window. "Ran" means
    # work was attempted, not that the function returned.
    attempted = result["proposed"] > 0 or result["cost_cad"] > 0
    return {"ran": attempted, "arena": f"{arena.event}/{arena.pod}",
            "proposed": result["proposed"], "survivors": len(result["survivors"]),
            "forms": result["forms_discovered"], "cost_cad": result["cost_cad"],
            "answered_the_arena": result["answered_the_arena"],
            "winner": result["ideation"]["winner"], "intake": took,
            "role": plan["role"]["role"],
            "cleared_for_engineering": gate["cleared_for_engineering"],
            **({} if attempted else
               {"reason": "every field came back malformed; nothing was proposed or spent"})}


def _winner_intake(ctx: JobContext, selection: dict, plan: dict, *, gateway, arena,
                   source: str, funnel_rounds, mjs_event_id=None) -> tuple[dict, dict | None]:
    """The winner through `creative.intake`, as the gate block `ideation.record` stores."""
    from ..creative import intake as winner_intake

    winner = selection.get("winner_object")
    if winner is None:
        return ({"gate": "not_called", "reason": "no winner",
                 "cleared_for_engineering": False}, None)
    took = winner_intake.intake(
        ctx, candidate=winner, plan=plan, source=source, arena=arena,
        funnel_rounds=funnel_rounds, mjs_event_id=mjs_event_id,
        culture_id=gateway.culture_origin(winner.concept.title))
    call = took.pop("gate_call")
    if selection.get("winner"):
        selection["winner"]["design_slug"] = took["slug"]
    gate = {**call, "cleared_for_engineering": took["decision"] == winner_intake.ENGINEERING,
            "gate_cleared": bool(call.get("cleared_for_engineering")),
            "funnel_carried": took["funnel"], "intake_decision": took["decision"]}
    return gate, took


def _ceiling_gate(ctx: JobContext, plan: dict, arena, *, kind: str) -> dict | None:
    """#227 on the real brief: every objective this run will send to a generator is checked.

    C-60: `ceiling_check` used to judge a default string the mission wrote for itself, so no
    agent's actual objective was ever read. Here the checked text is what the model is sent
    -- each rotation of the constraint paragraph `ideation.constraints_text` appends to a
    generator call, plus the breakthrough / same-arena objective carried in the job inputs.
    An objective that names matching a competitor as the goal blocks the run before any
    spend, and the refusal is audited with the offending text.
    """
    from ..creative import ideation
    from ..intel import panel

    texts: list[str] = []
    bt = plan.get("breakthrough") or {}
    if bt.get("objective"):
        texts.append(str(bt["objective"]))
    for i in range(max(1, len(plan.get("briefs") or []))):
        try:
            texts.append(ideation.constraints_text(plan, i)[0])
        except Exception:  # noqa: BLE001 - a plan without rotations has only its objective
            break
    checked = []
    for text in texts:
        verdict = panel.ceiling_check(objective=text)
        checked.append(verdict["permitted"])
        if not verdict["permitted"]:
            ctx.audit(f"creative.{kind}_ceiling_refused", artifact=f"{arena.event}/{arena.pod}",
                      detail={"objective": text[:1200], "matched": verdict.get("matched"),
                              "against": verdict.get("against"), "why": verdict["why"]})
            return {"ran": False, "arena": f"{arena.event}/{arena.pod}",
                    "reason": f"ceiling_check refused the brief: {verdict['why'][:200]}",
                    "ceiling_refused": True}
    plan["ceiling_checked"] = {"objectives": len(checked), "permitted": all(checked)}
    return None


def _ideation_arena(ctx: JobContext, found: list, arena, *, kind: str, cycle: int):
    """The ideation plan for this cycle's arena, moving arena if saturation empties it (#117).

    Returns `(arena, plan, moved_from)`. When every form of the chosen arena is crowded with
    no named unmet angle, the next arena with open ground is taken instead -- "move to a less
    saturated creative territory" -- and `moved_from` names what was left. When no arena has
    open ground the run is blocked, audited with the saturation evidence, and `plan` is None
    with the handler's return value in the third slot.
    """
    from ..core.models import utcnow
    from ..creative import ideation

    today = utcnow().date()
    ordered = [arena] + [a for a in found if a is not arena]
    left: list[dict] = []
    for candidate in ordered:
        plan = ideation.plan(ctx.db, kind=kind, event=candidate.event, pod=candidate.pod,
                             forms=list(candidate.forms), cycle=cycle, today=today)
        excluded = set(plan["saturation"]["excluded_forms"])
        if not candidate.forms or set(candidate.forms) - excluded:
            # Carried in the plan so the run's audit row -- including a blocked one --
            # names the saturated territory it left.
            plan["moved_from"] = left or None
            return candidate, plan, (left or None)
        left.append({"arena": f"{candidate.event}/{candidate.pod}",
                     "excluded_forms": sorted(excluded),
                     "why": "every form is crowded and no unmet angle was mined (#117)"})
    ctx.audit(f"creative.{kind}_blocked",
              detail={"reason": "every proven arena is saturated with no unmet angle",
                      "saturated": left})
    return arena, None, {"ran": False, "arena": f"{arena.event}/{arena.pod}",
                         "reason": ("every proven arena is saturated and the white-space "
                                    "agent has mined no unmet angle to enter one on (#117)"),
                         "saturated": left}


@handlers.register("creative.white_space")
def handle_white_space(ctx: JobContext) -> dict:
    """The white-space discovery agent (#118): what buyers want that results do not satisfy.

    Weekly. Mines recorded complaints -- the benchmark shop's classified review themes and
    this shop's own support questions -- into ranked hypotheses with `discovery.white_space`,
    and writes them as the row the ideation handlers read: the strongest hypothesis goes into
    every brief, and its angle is the only thing that lets a crowded form be entered (#117).
    With nothing recorded it says so and proposes nothing, because proposing from the
    category is how a white-space agent rediscovers the commodity.

    GREEN: reads stored evidence, writes one row. No model, no spend, no contact.
    """
    from ..core.models import AuditLog
    from ..creative import discovery, ideation

    complaints = ideation.mine_complaints(ctx.db)
    mined = discovery.white_space(complaints)
    sources = sorted({c.source.split(":")[0] for c in complaints})
    detail = {"minable": mined["minable"], "complaints": len(complaints),
              "sources": sources,
              "hypotheses": mined.get("hypotheses", []),
              "strongest": mined.get("strongest"),
              "reason": mined.get("reason", ""),
              "angles": {h["complaint_kind"]: discovery.COMPLAINT_ANGLE.get(h["complaint_kind"])
                         for h in mined.get("hypotheses", [])}}
    with ctx.db.session() as s:
        s.add(AuditLog(actor="creative_director", action=ideation.WHITE_SPACE_ACTION,
                       artifact="white_space", detail=detail))
    return {"ran": True, "minable": mined["minable"], "complaints": len(complaints),
            "hypotheses": len(mined.get("hypotheses", [])),
            "strongest": mined.get("strongest"),
            **({} if mined["minable"] else {"reason": mined["reason"][:200]})}


@handlers.register("creative.four_season")
def handle_four_season(ctx: JobContext) -> dict:
    """The four-season programme (#121) and the non-holiday occasion rotation (#122).

    Weekly. Assigns this week's program for the current season -- garden/floral, cottage,
    harvest/woodland, cozy winter neutral, home refresh, outdoor entertaining, seasonal
    wardrobe -- and one evergreen occasion, and writes them as the row the ideation handlers
    brief against. It also measures how much of the catalogue answers no named holiday, so
    "revenue collapses between holidays" is a number rather than a feeling.

    GREEN: reads the catalogue, writes one row. No model, no spend, no contact.
    """
    from ..core.models import AuditLog, utcnow
    from ..creative import ideation, universe
    from ..creative.audit import catalogue_concepts
    from ..creative.prospecting import EVENT_OCCASION

    today = utcnow().date()
    week = int(utcnow().timestamp() // (7 * 24 * 3600))
    assigned = ideation.programme_for(today, cycle=week)
    occasion = ideation.occasions(cycle=week, limit=1)[0]
    holidays = set(EVENT_OCCASION.values())
    concepts = catalogue_concepts()
    independent = [c.key for c in concepts if c.occasion not in holidays]
    detail = {"season": assigned["season"], "program": assigned["program"],
              "meaning": assigned["meaning"], "next_season": assigned["next_season"],
              "next_program": assigned["next_program"],
              "occasion": occasion["key"], "occasion_meaning": occasion["meaning"],
              "programs_this_season": list(universe.FOUR_SEASON_PROGRAMS[assigned["season"]]),
              "catalogue": len(concepts),
              "holiday_independent": len(independent),
              "holiday_independent_share": (round(len(independent) / len(concepts), 3)
                                            if concepts else None)}
    with ctx.db.session() as s:
        s.add(AuditLog(actor="creative_director", action=ideation.PROGRAMME_ACTION,
                       artifact=f'{assigned["season"]}/{assigned["program"]}', detail=detail))
    return {"ran": True, "season": assigned["season"], "program": assigned["program"],
            "occasion": occasion["key"],
            "holiday_independent_share": detail["holiday_independent_share"]}


@handlers.register("assets.model_photography")
def handle_model_photography(ctx: JobContext) -> dict:
    """One model-bearing listing frame for a certified product that needs her (#72, #130).

    The counterpart to `assets.owned_photography`, which photographs the forms that are
    shot flat. This one photographs the forms a buyer cannot judge without a body: it
    conditions the render on the frozen canonical reference image and then has the result
    described by a vision model that never saw the prompt, because conditioning is a
    request and the identity gate is what turns it into evidence.

    Idempotent by product and version, so a deploy re-attempts a frame that failed and
    does nothing once a release has one.

    GREEN: one render and its checks. Publishes nothing, contacts nobody, and refuses to
    spend at all when there is no frozen identity to verify the result against.
    """
    import tempfile

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..gateway import images
    from ..products.builder import for_slug
    from ..publish import listing_asset, model_photography

    # #203: the shot plan is decided before anything is rendered, and recorded whether or
    # not rendering is possible today -- it is what the sequence renders from, and a plan
    # nobody can see is a plan nobody can check a gallery against.
    slug = ctx.job.inputs.get("slug") or _model_bearing_slug(ctx.db)
    cir = for_slug(slug) if slug else None
    planned = model_photography.planned_shots(cir) if cir is not None else None
    if planned is not None:
        ctx.audit(model_photography.PLAN_ACTION, artifact=f"{slug}@{cir.version}",
                  detail=planned)

    if not images.usable(ctx.db):
        return {"ran": False, "reason": ("image generation has not been demonstrated in "
                                         "this environment, so there is nothing to render "
                                         "with"), "shot_plan": planned}

    if not slug:
        return {"ran": False, "reason": ("no certified product needs the model, so there "
                                         "is nothing for this job to photograph")}

    if cir is None:
        return {"ran": False, "reason": f"no CIR for {slug!r}"}

    next_move = model_photography.what_to_do_next(ctx.db, slug=slug, version=cir.version)
    if not next_move["render"]:
        return {"ran": False, "reason": next_move["reason"], "slug": slug,
                "attempts": next_move["attempts"], "why": next_move["why"],
                "usable": next_move["reason"] == "usable_frame_on_file"}

    result = compile_cir(cir)
    if not result.ok:
        return {"ran": False, "reason": f"{slug} does not compile"}

    with tempfile.TemporaryDirectory(prefix="model-frame-") as work_dir:
        record = listing_asset.make(ctx.db, cir, build_twin(cir, result),
                                    work_dir=work_dir, record=False,
                                    **({"shot_plan": planned}
                                       if listing_asset.needs_the_model(cir) else {}))

    ctx.audit(model_photography.ACTION, detail=record)
    # C-80 defect 8: a model-bearing product's rung attempt is persisted too, so the ladder
    # resumes rather than restarting (the model path carries no rung brief yet: it is the
    # same conditioned render, recorded as such).
    if str(ctx.job.inputs.get("reason") or "").startswith("parity_escalation:"):
        from ..visual.gallery import ESCALATION_RESULT_ACTION

        ctx.audit(ESCALATION_RESULT_ACTION, artifact=f"{slug}@{cir.version}",
                  detail={"rung": str(ctx.job.inputs["reason"]).split(":", 1)[1],
                          "failed": list(ctx.job.inputs.get("failed") or []),
                          "attempted": bool(record.get("made")), "made": record.get("made"),
                          "usable": bool(record.get("usable_as_listing_asset")),
                          "verdict": (record.get("floors") or {}).get("verdict")
                          if isinstance(record.get("floors"), dict) else None,
                          "strategy": "model_path_unchanged"})
    # #36: a generated frame is stored with its provenance -- simulated, AI-assisted, the
    # version it depicts -- the moment it exists.
    if record.get("made"):
        from ..commerce import buyer_trust

        buyer_trust.record_gallery(
            ctx.db, slug=slug, version=cir.version, job_id=ctx.job.id,
            source=model_photography.ACTION,
            records=buyer_trust.records_for_generated(
                list(record.get("frames") or [record]), slug=slug, version=cir.version))
    return {"ran": True, "made": record.get("made"), "slug": slug,
            "waiting_on": record.get("waiting_on"),
            "floors": record.get("floors"),
            "usable": record.get("usable_as_listing_asset"),
            "why": (record.get("why") or "")[:240]}


def _model_bearing_slug(db) -> str:
    """A certified product whose listing needs her, if the catalogue has one.

    Returns empty rather than falling back to the first product, which is the difference
    between "nothing here needs the model" and "photograph a blanket on a woman". The
    caller reports the empty answer as a reason rather than as a failure.
    """
    from sqlalchemy import select

    from ..core.models import Product
    from ..products.builder import for_slug
    from ..publish import listing_asset

    with db.session() as s:
        rows = [p.slug for p in s.scalars(select(Product).order_by(Product.id))]
    for slug in rows:
        cir = for_slug(slug)
        if cir is not None and listing_asset.needs_the_model(cir):
            return slug
    return ""


@handlers.register("seasonal.cycle_proof")
def handle_seasonal_cycle_proof(ctx: JobContext) -> dict:
    """Run #300's cycle as a job, and close the assets link it cannot close as a GET.

    #300 is a launch-blocking acceptance test, and its eighth link -- "create
    Brambleloop-owned assets" -- was the one it could never satisfy for its own product.
    The cycle authors and certifies its concept in memory and never files it in the
    catalogue, which is right for a *simulated* cycle and wrong for the daily photography
    job, which looks products up by slug and so can never reach it. For a while the step
    papered over that by handing in whichever product happened to be photographed last,
    including that product's motif failure, which made the test's verdict meaningless in
    both directions (B-611).

    So the asset is made here rather than there: `owned_photography.make` takes the CIR in
    hand, not a slug. It runs as a job because `/api/seasonal/cycle` is a GET and a GET
    that spends money spends it every time a sweep walks the routes -- and because filing
    the product instead would inflate the catalogue on every page view, which is the move
    #292 exists to refuse.

    GREEN: it renders one image and judges it. It publishes nothing, contacts nobody, and
    spends one render plus its checks -- and refuses to spend even that when the model
    provider's balance would leave the result unjudgeable.
    """
    import tempfile

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..core.resilience import PermanentError, TransientError
    from ..gateway.anthropic import AnthropicProvider
    from ..gateway import failover
    from ..publish import listing_asset
    from ..seasonal import cycle

    # The gateway is the difference between this job doing its job and this job reporting
    # that it could not start. Without one the generate step gates on `model_provider` and
    # the run stops at step 5, four links short of the assets link this job exists to
    # close -- which is exactly what the first live run did: `weakest_link: generate`,
    # `assets_state: None`. A proof that stops before the thing it proves is not a proof,
    # and it cost a scheduled run to find out because the handler asked the cycle for
    # everything except the one input it needed.
    gateway = None
    if AnthropicProvider.key():
        # Certification C-31: with the registry every call is checked against the monthly,
        # provider and agent ceilings, reserved before it leaves and billed to this job.
        # Without it the gateway did none of the three. W-8: through `failover.job_gateway`.
        gateway = failover.job_gateway(ctx.db, "concept_generation", registry=ctx.registry,
                                       agent="creative_director", job_id=ctx.job.id)
    if gateway is None:
        return {"ran": False, "reason": ("no model provider credential, so the cycle "
                                         "cannot generate concepts and would stop four "
                                         "links before the assets link this job exists "
                                         "to close")}

    with tempfile.TemporaryDirectory(prefix="cycle-proof-") as work_dir:
        def make_asset(cir):
            # Dispatched by form rather than by this handler's opinion: a cardigan needs
            # her in the frame and a blanket does not, and one place decides that so the
            # cycle, the daily job and the release chain cannot answer it differently.
            result = compile_cir(cir)
            if not result.ok:
                return None
            return listing_asset.make(ctx.db, cir, build_twin(cir, result),
                                      work_dir=work_dir)

        try:
            report = cycle.run(ctx.db, gateway=gateway, asset_maker=make_asset)
        except (PermanentError, TransientError) as exc:
            # A spent provider balance is a refusal, not a defect.
            #
            # This docstring already claimed the job "refuses to spend when the model
            # provider's balance would leave the result unjudgeable", and the asset maker
            # does exactly that -- but the cycle's own generate and engineer steps call the
            # gateway several links earlier, so a `ProviderUnusable` from an empty balance
            # escaped upstream of the guard and killed the job. Live, 2026-09-23: two dead
            # letters reading "Your credit balance is too low", which turned `/api/verify`
            # red and reported a funding problem as a broken worker.
            #
            # That is the distinction this codebase already draws for the freeze job: a
            # refusal is recorded rather than raised, because the job did its job by
            # declining. Retrying it cannot help -- no number of attempts adds money to an
            # account -- so a dead letter here is a queue entry nobody can action wearing
            # the costume of a bug.
            ctx.audit("seasonal.cycle_proof_refused",
                      detail={"why": str(exc)[:400],
                              "waiting_on": "model_provider_balance"})
            return {"ran": True, "complete": False,
                    "refused": "model_provider_balance",
                    "why": (f"the cycle could not be run because the model provider "
                            f"refused: {str(exc)[:200]}. Nothing about #300 is proved or "
                            f"disproved by this -- the proof did not run"),
                    "waiting_on": "model_provider_balance"}

    ctx.audit("seasonal.cycle_proof", detail=report)
    assets = next((s for s in report["steps"] if s["step"] == "assets"), {})
    return {"ran": True, "complete": report["complete"],
            "weakest_link": report["weakest_link"],
            "assets_state": assets.get("state"),
            "assets_slug": (assets.get("evidence") or {}).get("slug"),
            "customer_can_finish_in_time": report["customer_can_finish_in_time"]}


@handlers.register("seasonal.remerchandising")
def handle_remerchandising_review(ctx: JobContext) -> dict:
    """The periodic inspection #292 asks for, against the nearest priority occasion.

    Weekly. "Periodically inspect proven evergreen products" is a cadence, not a function
    somebody remembers to call, and a re-merchandising review that never runs is the same as
    one that does not exist.

    GREEN: it reads certified products, recorded sales and an already-observed benchmark
    catalogue. It changes no listing, publishes nothing and spends nothing -- and it cannot
    increment the catalogue by construction, because a re-merchandising move that changed
    construction, form, rows, stitch counts, gauge or the release hash is refused as a new
    product wearing a re-merchandising label.
    """
    from ..creative import prospecting
    from ..seasonal import remerchandising

    try:
        found = prospecting.arenas(ctx.db)
    except prospecting.NoArenasContradictsEvidence:
        found = []
    # The occasion to inspect against is the soonest proven one, because a review aimed at
    # an occasion nobody is shopping for yet is a report nobody can act on.
    arena = min(found, key=lambda a: a.days_away) if found else None
    event = arena.event if arena else "Christmas"
    pod = arena.pod if arena else ""

    report = remerchandising.review(ctx.db, event=event, pod=pod)
    ctx.audit("seasonal.remerchandising", detail=report)

    # #279: every proven evergreen concept is evaluated for this occasion's transformations,
    # automatically. Presentation layers route here (re-merchandising); object-changing ones
    # are derived from a brief generated from the parent (C-61) -- the promise is the
    # parent's own, executed where the parent's premise says it is -- and the derived child
    # enters the next `creative.tournament` for this event as an entrant, where the staged
    # funnel judges it (#3). Nothing is engineered from here.
    from ..seasonal import remerchandising as _rm

    # Transformations are engineering, so they are aimed at the soonest proven occasion a
    # tournament can still reach -- an occasion a fortnight away has no form that can be
    # made in time, and children derived for it could never enter a field. The review's own
    # occasion (presentation moves, which cost a photograph) stays the soonest.
    reachable = [a for a in found if prospecting.slots(a)["slots"]]
    transform_event = (min(reachable, key=lambda a: a.days_away).event if reachable
                       else event)
    transforms = _rm.transformations(ctx.db, event=transform_event,
                                     briefs=list(ctx.job.inputs.get("briefs") or []))
    ctx.audit(_rm.TRANSFORMATIONS_ACTION, detail={
        "event": transform_event, "season": transforms["season"],
        "evaluated": transforms["evaluated"], "routed": transforms["routed"],
        "derived": [d["key"] for d in transforms["derived"]],
        "derived_concepts": [d["concept"] for d in transforms["derived"]],
        "briefs_generated": transforms.get("briefs_generated", 0),
        "held": transforms.get("held", [])[:10],
        "refused": transforms["refused"][:10]})
    return {"event": event, "pod": pod or None,
            "candidates": len(report["candidates"]),
            "ready_moves": report["ready_moves"],
            "available": list(report["capabilities"]["available"]),
            "catalogue_growth": report["catalogue_growth"],
            "transformations": {**{k: transforms[k] for k in ("season", "evaluated", "routed")},
                                "event": transform_event},
            "derived": [d["key"] for d in transforms["derived"]]}


@handlers.register("improve.role_work")
def handle_role_work(ctx: JobContext) -> dict:
    """One meta-agent's pass over the rows it answers for (#179).

    The agent *is* the role, so `ctx.job.agent` dispatches. Each pass reads and reports; none
    of them promotes anything, because proposing runs through #190's pipeline and promotion
    through #178's tiers, and a meta-agent that could promote would be the company rewriting
    itself faster than it can observe the results.

    What comes back is a count of rows read and things found, never a count of changes made.
    On an empty database most of these find nothing and say so, which is the correct output
    for a company with no customers: a swarm reporting activity here would be reporting on
    work it invented.

    GREEN: reads rows, writes an audit record, spends nothing.
    """
    from sqlalchemy import func, select

    from ..core.models import (Incident, Job, JobStatus, LedgerEntry, Lesson,
                               ConfigVersion, ListingAsset)
    from ..improve import roles

    role_key = ctx.job.agent
    try:
        role = roles.role(role_key)
    except roles.RoleRefused as exc:
        raise ValueError(
            f"{role_key!r} ran {roles.ROLE_JOB_TYPE} and is not a meta-agent role. The agent "
            f"is the role here, so an agent with no role has no rows it answers for") from exc

    read = found = 0
    with ctx.db.session() as session:
        if role_key == "evaluator":
            rows = list(session.scalars(select(ConfigVersion)))
            read = len(rows)
            found = sum(1 for r in rows if r.incumbent and not (r.measured_outcome or {}))
        elif role_key == "failure_miner":
            incidents = list(session.scalars(
                select(Incident).where(Incident.resolved.is_(False))))
            dead = session.scalar(select(func.count()).select_from(Job)
                                  .where(Job.status == JobStatus.DEAD)) or 0
            read = len(incidents) + dead
            found = len(incidents)
        elif role_key == "lesson_router":
            lessons = list(session.scalars(select(Lesson)))
            read = len(lessons)
            found = sum(1 for r in lessons if r.routed_to and not r.acted_on_by)
        elif role_key == "prompt_tool_challenger":
            configs = list(session.scalars(select(ConfigVersion)))
            read = len(configs)
            keys = {(r.kind, r.key) for r in configs}
            challenged = {(r.kind, r.key) for r in configs if not r.incumbent}
            found = len(keys - challenged)
        elif role_key == "cost_optimiser":
            entries = list(session.scalars(select(LedgerEntry)))
            read = len(entries)
            found = sum(1 for r in entries if (r.gross_cad or 0) > 0)
        elif role_key == "reliability_engineer":
            dead = session.scalar(select(func.count()).select_from(Job)
                                  .where(Job.status == JobStatus.DEAD)) or 0
            total = session.scalar(select(func.count()).select_from(Job)) or 0
            read = total
            found = dead
        elif role_key == "creative_critic":
            assets = list(session.scalars(select(ListingAsset)))
            read = len(assets)
            found = sum(1 for r in assets if not r.approved)
        else:  # experiment_designer
            # The experiments it designed and the hypotheses it turns into tests: every
            # improvement the sandbox runner has taken, and the open ones no registered trial
            # can evaluate -- those are the ones waiting on its job.
            from ..core.models import Experiment, Improvement
            from ..improve import runner as _runner

            experiments = list(session.scalars(select(Experiment)))
            open_rows = list(session.scalars(select(Improvement).where(
                Improvement.state.in_(("proposed", "testing")))))
            read = len(experiments) + len(open_rows)
            found = sum(1 for r in open_rows
                        if _runner.trial_for(dict(r.evidence or {})) is None
                        and (r.evidence or {}).get("kind") not in _runner.MEASUREMENT_KINDS)

    # #179: what the role did, from the rows -- proposals it authored, the ones kept, and the
    # realised uplift `improve.roi` measured after promotion -- never a literal zero.
    activity, activity_detail = roles.activity_from_db(ctx.db, role_key)
    card = roles.scorecard(activity)
    detail = {
        "role": role_key, "reads": roles.ROLE_READS[role_key],
        "rows_read": read, "found": found,
        "measured_by": role.measured_by,
        "scorecard": card,
        "proposed": activity.proposals_made,
        "kept": activity.proposals_kept,
        "realised_uplift": activity.realised_uplift,
        "activity": activity_detail,
        "why": (f"read {read} row(s) and found {found}; {activity.proposals_made} "
                f"proposal(s) in the window, {activity.proposals_kept} kept, realised "
                f"uplift {activity.realised_uplift:+.4f}. Scored on uplift alone"),
    }
    ctx.audit("improve.role_work", detail=detail)
    return detail


@handlers.register("improve.nightly")
def handle_nightly_improvement(ctx: JobContext) -> dict:
    """The nightly improvement sweep, whose verdict is computed rather than asserted (#193).

    Seven stages. Each returns what it read and what it found, and a stage that read nothing
    reports `did_not_run` rather than a clean result -- because finding nothing in nothing has
    not established that there was nothing to find. A sweep is `complete` only when every
    stage ran, never because this handler returned without raising.

    In shadow mode several stages genuinely have nothing to read: there are no customers, no
    live listings and no challenger runs. The delta says so, night after night, and that is
    the correct output. A sweep that reported success on this state would be describing a
    company that does not exist.

    GREEN: it reads rows, writes an audit record and queues nothing that promotes itself.
    """
    from datetime import timezone

    from sqlalchemy import desc, select

    from ..core.models import AuditLog, CapabilityPoint, ConfigVersion, Lesson
    from ..improve import bootstrap, freshness, measure, mine, nightly, profiles

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    previous = None
    previous_at = None
    with ctx.db.session() as session:
        row = session.scalar(select(AuditLog).where(AuditLog.action == "improve.nightly")
                             .order_by(desc(AuditLog.id)).limit(1))
        if row is not None:
            previous = (row.detail or {}).get("delta")
            previous_at = _aware(row.at)

    results = []

    # INGEST measures every cell first (an identical reading is not re-recorded, so this and
    # the daily improve.measure cadence cannot double-count), then reads every capability
    # point; the ones recorded since the previous sweep are what was found. Twelve empty
    # sources read as zero and `did_not_run`, the honest reading of an unmeasured company.
    measured = measure.record_all(ctx.db)
    with ctx.db.session() as session:
        points = [(p.cell, _aware(p.at), (p.detail or {}).get("from", ""))
                  for p in session.scalars(select(CapabilityPoint))]
    fresh = [p for p in points if previous_at is None or p[1] > previous_at]
    results.append(nightly.stage_ran(
        nightly.INGEST, read=len(points) + measured["read"], found=len(fresh),
        cells_measured=sorted({cell for cell, _at, _src in fresh}),
        measured_tonight=[r["cell"] for r in measured["recorded"]],
        not_measurable={k: v["reason"] for k, v in measured["skipped"].items()},
        sources=sorted({src for _c, _at, src in fresh if src})))

    # MINE reads the failures -- unresolved incidents, gate and asset refusals, dead letters
    # -- groups them by signature and publishes each group through the lesson bus, once.
    mined = mine.mine(ctx.db)
    results.append(nightly.stage_ran(
        nightly.MINE, read=mined["read"], found=mined["found"],
        groups=mined["groups"], reused=len(mined["reused"]),
        incidents=mined["incidents"], blocked=mined["blocked"], dead=mined["dead"],
        regression_fixtures=len(mined["regression_fixtures"])))

    # LESSONS: what the bus now routes, and to whom. Found is the departments that received
    # something new tonight, because a lesson filed and routed nowhere is not learning.
    with ctx.db.session() as session:
        lessons = list(session.scalars(select(Lesson)))
    unacted = [row for row in lessons if row.routed_to and not row.acted_on_by]
    reached = sorted({cell for entry in mined["published"] for cell in entry["routed_to"]})
    results.append(nightly.stage_ran(
        nightly.LESSONS, read=len(lessons), found=len(reached),
        routed_to=reached, unacted=len(unacted),
        published=[e["evidence_ref"] for e in mined["published"]]))

    # CHALLENGERS: the league's incumbents are registered from the code that runs them, and
    # any trial verdict on file is copied onto the rows it judged. No challenger is run here;
    # that is a spending decision. What is found is every configuration with a challenger.
    booted = bootstrap.ensure(ctx.db)
    # #193: challenger evaluations run here, not only counted. The deterministic replay
    # evaluates the job-priority policy's incumbent and challengers on historical jobs and
    # their holdout (idempotent per window, so the daily improve.replay cadence and this
    # sweep never double-record); model challengers still wait for a run somebody pays for.
    from ..improve import replay as _replay

    evaluated = _replay.cycle(ctx.db)
    with ctx.db.session() as session:
        configs = [(row.kind, row.key, row.incumbent, bool(row.measured_outcome))
                   for row in session.scalars(select(ConfigVersion))]
    challengers = [c for c in configs if not c[2]]
    results.append(nightly.stage_ran(
        nightly.CHALLENGERS, read=len(configs), found=len(challengers),
        incumbents=sum(1 for c in configs if c[2]),
        incumbents_unmeasured=sum(1 for c in configs if c[2] and not c[3]),
        evaluated={"ran": evaluated["ran"], "runs": len(evaluated.get("runs") or []),
                   "compared": len(evaluated.get("compared") or []),
                   "proposed": evaluated.get("proposed") or [],
                   "why": evaluated.get("why")},
        bootstrap=booted))

    sweep = freshness.sweep(ctx.db)
    stuck = sorted(set(sweep["stale_learning"]) | set(sweep["churning"])
                   | set(sweep["never_measured"]))
    results.append(nightly.stage_ran(nightly.BOTTLENECKS,
                                     read=len(sweep["departments"]), found=len(stuck),
                                     stale=sweep["stale_learning"],
                                     churning=sweep["churning"],
                                     never_measured=sweep["never_measured"]))

    # QUEUE opens bounded proposals from each cell's own self-review and stops there. Every
    # one goes through cells.propose -- the governance boundary, the rollback requirement and
    # the declared surfaces -- and nothing here tests or promotes: #190's pipeline and #178's
    # tiers decide that, and a nightly job that could promote is a company rewriting itself
    # faster than it can observe the results.
    queued = profiles.queue_proposals(ctx.db)
    results.append(nightly.stage_ran(
        nightly.QUEUE, read=queued["cells_reviewed"], found=queued["persisted"],
        proposals_seen=queued["proposals_seen"],
        queued=[{"improvement": q["improvement"], "cell": q["cell"], "kind": q["kind"]}
                for q in queued["queued"]],
        already_open=len(queued["already_open"]),
        refused=queued["refused"],
        resolved_by_measurement=len(queued["resolved_by_measurement"])))

    results.append(nightly.stage_ran(nightly.DELTA, read=len(results), found=len(results)))
    delta = nightly.delta(results, previous=previous)

    detail = {"verdict": delta["verdict"], "did_not_run": delta["did_not_run"],
              "total_read": delta["total_read"], "total_found": delta["total_found"],
              "delta": delta}
    ctx.audit("improve.nightly", detail=detail)
    return detail


@handlers.register("improve.weekly")
def handle_weekly_evolution(ctx: JobContext) -> dict:
    """The weekly deep cycle, and the architecture review that must be able to subtract (#194).

    Eight domains, each audited rather than visited: a domain with nothing read is
    `not_audited`, and the cycle will not call itself complete while one remains. The
    architecture half proposes nothing on its own here -- it reports what the freshness sweep
    and the velocity review found, and a week that only added would be asked why.

    It also acts (#100, #192). The retirement review runs over the cells' own records and
    its merge/retire recommendations are the architecture changes the cycle judges -- never
    applied here, because retiring a department is the owner's decision. And the approved,
    tested, lowest-risk improvements are executed through `cells.promote` with its tier
    limits; everything else is queued for the authority its tier names.

    GREEN: reads rows, may promote a scoring-tier change an independent judge approved,
    writes an audit record. Spends nothing.
    """
    from sqlalchemy import func, select

    from ..core.models import (AuditLog, CapabilityPoint, Incident, Job, JobStatus,
                               LedgerEntry, PatternVersion, SupportCase)
    from ..improve import director, freshness, roi, weekly
    from ..swarm.orchestrate import retirement_review

    readings = []
    with ctx.db.session() as session:
        points = session.scalar(select(func.count()).select_from(CapabilityPoint)) or 0
        incidents = session.scalar(select(func.count()).select_from(Incident)) or 0
        open_incidents = session.scalar(select(func.count()).select_from(Incident)
                                        .where(Incident.resolved.is_(False))) or 0
        cases = session.scalar(select(func.count()).select_from(SupportCase)) or 0
        ledger = session.scalar(select(func.count()).select_from(LedgerEntry)) or 0
        versions = session.scalar(select(func.count()).select_from(PatternVersion)) or 0
        uncertified = session.scalar(select(func.count()).select_from(PatternVersion)
                                     .where(PatternVersion.certified.is_(False))) or 0
        jobs = session.scalar(select(func.count()).select_from(Job)) or 0
        dead = session.scalar(select(func.count()).select_from(Job)
                              .where(Job.status == JobStatus.DEAD)) or 0
        tournaments = session.scalar(select(func.count()).select_from(AuditLog)
                                     .where(AuditLog.action == "creative.tournament")) or 0

    sweep = freshness.sweep(ctx.db)
    stuck = sorted(set(sweep["stale_learning"]) | set(sweep["churning"]))

    # Each domain reports the rows it actually read. Several are zero in shadow mode, and a
    # zero here reads `not_audited` rather than clean, which is what keeps the weekly report
    # from describing a healthy business nobody has looked at. Conversion, ads, support and
    # cost are read from their own tables by `improve.evolution` (#194), never constants.
    from ..improve import evolution

    measured = evolution.domain_findings(ctx.db)
    for domain, read, found in (
            ("product_creativity", points + tournaments, len(stuck)),
            ("pattern_correctness", versions, uncertified),
            ("competitor_intelligence", len(sweep["departments"]),
             len(sweep["stale_learning"])),
            ("conversion", measured["conversion"]["read"], measured["conversion"]["findings"]),
            ("ads", measured["ads"]["read"], measured["ads"]["findings"]),
            ("support", measured["support"]["read"], measured["support"]["findings"]),
            ("infrastructure", incidents + jobs, open_incidents + dead),
            ("cost", measured["cost"]["read"], measured["cost"]["findings"])):
        note = (measured.get(domain) or {}).get("why", "")
        readings.append(weekly.DomainReading(domain=domain, read=read, findings=found,
                                             note=note[:300]))

    # #85: the catalogue's own jury autopsy, computed on every request and never kept, is
    # kept as a lesson -- once per distinct pattern of deaths, so a week with the same
    # catalogue adds nothing.
    from ..creative.audit import persist_catalogue_audit

    catalogue_memory = persist_catalogue_audit(ctx.db)["lesson"]

    # #192: the retirement review over the cells' own records, fed to the cycle as the
    # architecture changes it has to judge. Recommendations only: nothing is retired here.
    candidates = director.retirement_candidates(ctx.db)
    review = retirement_review(candidates["cells"])
    changes = [weekly.ArchitectureChange(
                   move=weekly.RETIRE, subject=r["cell"], proposed_by="improvement_director",
                   because=(f"{r['reason']}; preserve {len(r['preserve'])} lesson(s) "
                            f"before any retirement"))
               for r in review["retire"]]
    changes += [weekly.ArchitectureChange(
                    move=weekly.MERGE, subject=r["cell"], proposed_by="improvement_director",
                    because=(f"{r['reason']}, into {r['into']}; preserve "
                             f"{len(r['preserve'])} lesson(s) first"))
                for r in review["merge"]]
    # #194: the architecture review can add. A specialist is proposed where the rows show
    # work nothing can own -- a domain with findings and no agent holding its job types, or
    # unowned open work of one kind (#176) -- and the additions reach the owner as one card.
    added = evolution.additions(ctx.db, measured)
    changes += added
    # #194: the fourth move. A department's metric UNMEASURED for three cycles while a proxy
    # reads rows, or moving its good way while its realised outcomes contradict it, becomes
    # a REVISE_METRIC change under `improve.weekly`'s rules (never self-proposed, never
    # argued from the number), carded to the owner. `cells_unmeasured` is written into this
    # cycle's row so the streak is read from rows next week rather than remembered.
    unmeasured_now = evolution.unmeasured_cells(ctx.db)
    revisions = evolution.metric_revisions(ctx.db, unmeasured_now=unmeasured_now)
    changes += revisions["changes"]
    cycle = weekly.cycle(
        readings, changes,
        nothing_to_subtract_because=("" if review["retire"] or review["merge"] else
                                     "the retirement review found no idle or redundant cell "
                                     "this week"))
    add_card = evolution.route_owner_card(
        ctx.db, evolution.ADD_CARD_KEY, [f"add {c.subject}: {c.because}" for c in added],
        reason=("#194: adding a specialist agent is a permission change, reviewed like any "
                "other; the weekly cycle found work no current agent can own"))
    revise_card = evolution.route_owner_card(
        ctx.db, evolution.REVISE_CARD_KEY,
        [f"revise {c.subject}: {c.replaces_metric} -> {c.new_metric}: {c.because}"
         for c in revisions["changes"]],
        reason=("#194: revising a department's success measure is the dangerous move; the "
                "old metric's history is preserved and the change is the owner's to make"))
    # #53: the STOP half of the review, from rows. Stale experiments are stopped here; the
    # cadence, polish, query and infrastructure stops reach the owner as one card.
    stops = evolution.stop_list(ctx.db)
    stop_rows = stops["review"]["stop"]["stopped"]
    stop_card = evolution.route_owner_card(
        ctx.db, evolution.STOP_CARD_KEY,
        [f"stop {r['category']} {r['subject']}: {r['reason']}" for r in stop_rows
         if r["category"] != "experiment"],
        reason=("#53: every weekly review produces a STOP list; removing a cadence, a "
                "monitored query or a polishing loop changes how the company runs"))
    # ...and the recommendations reach the owner as one batched card rather than a report
    # (#192). Nothing is disabled: an agent disabled here would dead-letter its cadences.
    retirement_routing = director.route_retirements(ctx.db, review)

    # #100: execute what is approved, tested and low-risk; queue the rest for authority.
    executed = director.execute_approved(ctx.db)
    plan = weekly.roadmap(cycle, carried=[
        {"improvement": q["improvement"], "cell": q["cell"], "waiting_for": q["authority"],
         "why": q["why"]} for q in executed["queued_for_authority"]])
    realised = roi.realised_benefit(ctx.db)
    detail = {"complete": cycle["complete"], "not_audited": cycle["not_audited"],
              "total_read": cycle["total_read"], "total_findings": cycle["total_findings"],
              "architecture": cycle["architecture"],
              "retirement_review": {"keep": review["keep"], "merge": review["merge"],
                                    "retire": review["retire"],
                                    "waiting_for_data": candidates["waiting_for_data"],
                                    "routed": retirement_routing},
              "executed": executed["executed"],
              "queued_for_authority": executed["queued_for_authority"],
              "catalogue_autopsy_lesson": catalogue_memory.get("lesson"),
              "domains_measured": {k: {kk: v[kk] for kk in ("read", "findings", "reading",
                                                             "why")}
                                   for k, v in measured.items()},
              "added": [c.subject for c in added], "add_card": add_card,
              "cells_unmeasured": sorted(unmeasured_now),
              "metric_revisions": {
                  "changes": [c.to_dict() for c in revisions["changes"]],
                  "evidence": revisions["evidence"], "considered": revisions["considered"],
                  "history_cycles_read": revisions["history_cycles_read"],
                  "card": revise_card},
              "stop_list": {"stopped": stop_rows, "executed": stops["executed"],
                            "nothing_to_stop_because": stops["review"]["stop"].get(
                                "nothing_to_stop_because"),
                            "card": stop_card},
              "conflicts": director.conflicts(ctx.db),
              "roadmap": plan,
              "realised_benefit": {k: realised[k] for k in
                                   ("promotions", "assessed", "spent_cad", "hit_rate")}}
    ctx.audit("improve.weekly", detail=detail)
    return detail


@handlers.register("improve.measure")
def handle_capability_measure(ctx: JobContext) -> dict:
    """Measure every capability cell from the rows its `Cell.measure` string names (#90, #94).

    The department had twelve cells, each stating in words how its number is produced, and
    nothing ever produced it: production reported twelve of twelve UNMEASURED because
    `cells.record_capability` had no caller outside a test. This is the caller. One
    deterministic query per cell, the same every day; a cell whose source is empty records
    nothing and says which table has to fill first, because a zero written into an empty
    table reads downstream as "defects: none" when the truth is "defects: unknowable".

    GREEN: reads rows, writes capability points and an audit record. Spends nothing.
    """
    from ..improve import measure

    out = measure.record_all(ctx.db)
    detail = {"recorded": out["recorded"], "repeated": out["repeated"],
              "skipped": out["skipped"],
              "read": out["read"], "found": out["found"], "cells": out["cells"],
              "note": out["note"]}
    ctx.audit("improve.measure", detail=detail)
    return {"ran": True, "measured": out["found"], "of": out["cells"],
            "read": out["read"],
            "cells": [r["cell"] for r in out["recorded"]],
            "repeated": out["repeated"],
            "skipped": {k: v["reason"] for k, v in out["skipped"].items()}}


@handlers.register("improve.mine")
def handle_failure_mine(ctx: JobContext) -> dict:
    """Mine the failures for the pattern behind them and publish each as a routed lesson (#97).

    The nightly sweep runs this as its MINE stage; the handler exists so mining can also be
    driven on demand, because nightly is the minimum sweep and not the only one. Idempotent
    on evidence: an unresolved incident re-read on its thirtieth night is one lesson a month
    old, not thirty.

    GREEN: reads incidents, refusals and dead letters; writes lessons and an audit record.
    """
    from ..improve import mine

    out = mine.mine(ctx.db)
    return {"ran": True, "read": out["read"], "groups": out["groups"],
            "published": out["found"], "reused": len(out["reused"]),
            "regression_fixtures": [f for f in out["regression_fixtures"] if f["captured"]],
            "routed_to": sorted({c for e in out["published"] for c in e["routed_to"]})}


@handlers.register("improve.monitor")
def handle_promotion_monitor(ctx: JobContext) -> dict:
    """Judge every promoted change against its newest production reading (#93, #99).

    `cells.monitor` reverts a promotion whose metric came back worse than the sandbox said,
    and nothing called it, so every promotion stayed promoted because nobody was looking.
    This looks, once per new production reading, and only at readings neither the promotion
    nor the monitor wrote itself -- reading either back would make every promotion hold by
    construction.

    GREEN: reads capability points, may revert an improvement row, writes an audit record.
    """
    from ..improve import bootstrap, monitor, runner

    bootstrap.ensure(ctx.db)
    out = monitor.sweep(ctx.db)
    # Trial-metric promotions (#92, #164, #180) are judged by re-running their own trial on
    # data recorded since they won -- and reverted, with the change undone, when it reads worse.
    trials = runner.monitor_trials(ctx.db)
    ctx.audit("improve.monitor_trials", detail={
        "judged": trials["judged"], "reverted": trials["reverted"],
        "rollback_pending": trials["rollback_pending"],
        "waiting": len(trials["waiting"])})
    return {"ran": True, "promoted": out["promoted"], "judged": out["judged"],
            "held": len(out["held"]),
            "reverted": ([r["improvement"] for r in out["reverted"]]
                         + [r["improvement"] for r in trials["reverted"]]),
            "rollback_proposals": ([r["rollback"]["incident"] for r in out["reverted"]]
                                   + [r["incident"] for r in trials["reverted"]]),
            "trial_monitoring": {"judged": len(trials["judged"]),
                                 "reverted": trials["reverted"],
                                 "waiting": len(trials["waiting"])},
            # C-81: a rollback decided and not yet verified complete stays on the PROMOTED
            # row and is resumed next pass; it is never reported as reverted.
            "rollback_pending": [r["improvement"] for r in trials["rollback_pending"]],
            "waiting": len(out["waiting"]), "unchanged": len(out["unchanged"])}


@handlers.register("improve.sandbox")
def handle_improve_sandbox(ctx: JobContext) -> dict:
    """Take eligible proposals through a sandbox trial, test, judge, and promote or route (#92).

    Proposals were opened nightly and then sat in PROPOSED for ever: nothing moved one to
    TESTING, recorded its tests or approved it. `improve.runner` is that step. It evaluates a
    proposal only with a registered trial that re-derives the result from recorded rows,
    records regression and adversarial runs through `cells.record_test`, has the evaluator --
    never the proposer -- approve, promotes a pre-authorised tier through `cells.promote`, and
    puts every other tier in the owner queue until the owner's decision is recorded.

    GREEN: reads rows, may move improvement rows and promote a pre-authorised change, may
    queue an owner card. Spends nothing and calls no model.
    """
    from ..improve import runner

    out = runner.run(ctx.db)
    detail = {k: out[k] for k in ("sandboxed", "tested", "approved", "promoted",
                                  "owner_cards", "held", "cards_closed", "note", "anchored",
                                  "rejected", "executed", "prioritised", "unprioritised",
                                  "discipline")}
    detail["waiting"] = len(out["waiting"])
    ctx.audit(runner.ACTION, detail=detail)
    return {"ran": True, **detail, "waiting_detail": out["waiting"][:20]}


@handlers.register("improve.league")
def handle_improve_league(ctx: JobContext) -> dict:
    """Register challengers, compare them on recorded runs, promote or card, roll back (#95, #180).

    GREEN: registers configuration versions, judges recorded runs, may promote a
    pre-authorised configuration or roll back one the league promoted, may queue an owner
    card. Runs no challenger itself: producing a run is a model call, and this makes none.
    """
    from ..improve import league

    out = league.cycle(ctx.db)
    detail = {"challengers_registered": {k: out["challengers_registered"][k]
                                         for k in ("registered", "unchanged", "skipped")},
              "compared": out["compared"], "waiting": len(out["waiting"]),
              "refused": out["refused"], "promoted": out["promoted"],
              "owner_cards": out["owner_cards"], "held": out["held"],
              "rolled_back": out["rolled_back"], "cards_closed": out["cards_closed"],
              "note": out["note"]}
    ctx.audit("improve.league", detail=detail)
    return {"ran": True, **detail}


@handlers.register("improve.replay")
def handle_improve_replay(ctx: JobContext) -> dict:
    """Replay historical jobs under the job-priority policy and its challengers (#95, #180, #187).

    The league's producer of runs. Deterministic: the historical jobs are the tasks, the
    newest fifth of the days the holdout, and each configuration's showing is recorded with
    `league.record_run`. A challenger that beats the incumbent on the shared days and holds on
    the holdout becomes an improvement hypothesis the sandbox judges (#92); one that does not
    is retired with its verdict. Too little history is UNMEASURED, never a verdict.

    GREEN: reads jobs, registers configuration versions, records runs and may open an
    improvement proposal. Calls no model and spends nothing.
    """
    from ..improve import replay

    out = replay.cycle(ctx.db)
    ctx.audit(replay.ACTION, detail={k: out.get(k) for k in (
        "ran", "reading", "incumbent", "jobs", "days", "runs", "compared", "proposed",
        "retired", "challengers_registered", "why", "watched")})
    return out


@handlers.register("teardown.enforce")
def handle_teardown_enforce(ctx: JobContext) -> dict:
    """Teardown findings as enforced requirements, checked and routed to their consumers.

    #153-#161. Every certified product is checked against the requirements the recorded
    teardown findings imply (exceed a benchmark's strength, prevent its trap, settle what
    benchmarks disagree about, never fall below a floor the sandbox promoted); `store.publish`
    reads the same check through the release gates and refuses on it. Each requirement is
    published once on the lesson bus to the departments that consume it (Pattern Help,
    creative assets, quality), whose own handlers read their inboxes and record acting on it.

    GREEN: reads findings and products, writes lessons and an audit record. Spends nothing.
    """
    from ..improve import bus
    from ..teardown import enforce

    out = enforce.sweep(ctx.db)
    subjects = {"pdf": "instruction_clarity", "pattern_help": "instruction_clarity",
                "premium_standard": "chart_quality", "video": "delivery_experience",
                "delivery_bundle": "delivery_experience", "support": "delivery_experience"}
    published = []
    for req in enforce.requirements(ctx.db):
        if not req["binding"]:
            continue
        subject = subjects.get(req["consumers"][0], "delivery_experience")
        lesson = bus.publish(
            ctx.db, origin_cell="quality", subject=subject,
            statement=(f"Teardown requirement {req['key']} ({req['kind']}) binds "
                       f"{'/'.join(req['consumers'])}: {req['requirement'][:220]}"),
            evidence_ref=f"teardown_requirement:{req['key']}:{req['kind']}",
            confidence="observed")
        published.append(lesson)
    out["lessons"] = sorted(set(published))
    ctx.audit(enforce.ACTION, detail={k: out[k] for k in (
        "requirements", "binding", "provisional", "by_consumer", "blocked", "products",
        "reading", "note", "lessons")} | {"video_specification": out["video_specification"][:20],
                                           "pattern_help": out["pattern_help"][:20]})
    return out


@handlers.register("finance.governor")
def handle_finance_governor(ctx: JobContext) -> dict:
    """The governor's readings on a cadence, each acted on when it is measurable (#188).

    A per-agent spend spike opens an incident and pauses that agent's spend for the rest of
    its UTC day with a hold in the reservation table, which the ceiling check at dispatch
    refuses against; no ceiling is raised or rewritten. Marginal value below break-even opens
    an incident for the owner. The parallelism advice is written onto the latest swarm
    allocation, where `swarm.orchestrate.lane_concurrency` reads it. Unmeasurable readings
    act on nothing and say why.
    """
    from ..finance import governor

    out = governor.enforce(ctx.db)
    return {"ran": True, "paused": out["paused"], "incidents": out["incidents"],
            "unit_cost": out.get("unit_cost"),
            "marginal_value": out["marginal_value"], "parallelism": out["parallelism"],
            "allocation_fed": out["allocation_fed"],
            "company_anomaly_measurable": bool(out["company_anomaly"].get("measurable")),
            "agents_spiking": out["agent_anomalies"]["spiking"],
            "ceilings_changed": out["ceilings_changed"]}


@handlers.register("creative.style_learning")
def handle_style_learning(ctx: JobContext) -> dict:
    """Daily: creative performance by asset style, and promotion of measured winners (#82).

    Tags every listing frame from its record (no model call), aggregates recorded listing
    outcomes by style above stated minimums, and records a hero preference only for a style
    that beat the pooled alternative on a measured sample. Nothing live today, so the honest
    result is UNMEASURED with its reason.

    GREEN: reads listing assets and outcomes; writes brand_knowledge preferences only.
    """
    from ..creative import style_learning

    out = style_learning.learn(ctx.db)
    ctx.audit("creative.style_learning", detail={
        "status": out["status"], "why": out["why"], "promoted": out["promoted"],
        "refused": len(out["refused"]), "styles_tagged": out["styles_tagged"]})
    return {"ran": True, **out}


@handlers.register("creative.outcome_learning")
def handle_outcome_learning(ctx: JobContext) -> dict:
    """Daily: concept attributes joined to outcomes, and the novelty-is-not-success check (#89).

    GREEN: reads concepts, listing outcomes, orders and support cases; writes an audit record.
    """
    from ..creative import outcome_learning

    out = outcome_learning.learn(ctx.db)
    summary = {"status": out["status"], "why": out["why"], "concepts": out["concepts"],
               "concepts_with_outcomes": out["concepts_with_outcomes"],
               "novelty": {k: out["novelty"].get(k) for k in (
                   "status", "high_novelty_outperforms", "novelty_is_rewarded", "why")}}
    ctx.audit("creative.outcome_learning", detail=summary)
    return {"ran": True, **summary}


@handlers.register("seasonal.harvest")
def handle_season_harvest(ctx: JobContext) -> dict:
    """Daily: harvest every seasonal event's most recent *passed* occurrence (#298).

    An occurrence already harvested as measured is skipped; one refused for want of orders is
    re-read, because late orders and exports arrive. Never touches an event that has not
    passed.

    GREEN: reads orders, assets, support and market signals; writes season_harvests.
    """
    from ..seasonal import harvest

    out = harvest.harvest_due(ctx.db)
    ctx.audit("seasonal.harvest", detail={"measured": out["measured"],
                                          "ran": len(out["ran"]),
                                          "skipped": len(out["skipped"])})
    return {"ran": True, **out}


@handlers.register("ops.health")
def handle_health_sweep(ctx: JobContext) -> dict:
    """The continuous health sweep, and the repairs this system can actually perform (#185).

    Every fifteen minutes. The verdict this produces is deliberately allowed to say `idle`:
    a container can serve 200s, tick a worker, run a scheduler, hold an empty queue and
    complete nothing for a week, with every liveness signal green, because none of them is
    about work.

    It repairs nothing itself, and that is the finding rather than a gap. Both obvious
    repairs already happen: a lease is reclaimed on every queue claim, and a dead letter is
    re-driven once per deploy -- which is the right trigger, because a dead letter is fixed
    by a code change and a fifteen-minute timer would re-run a failure nothing has fixed,
    ninety-six times a day. What cannot be fixed at all -- a container restart, a missing
    credential, money already spent -- is escalated by name rather than attempted, because a
    repair that is announced and does not happen is worse than none: nobody looks.

    Escalation waits for persistence. One bad sweep is a blip and a deploy produces several;
    the same signal failing across consecutive sweeps is a condition, and only that raises an
    incident. The escalation carries the readings that produced it, because the first
    question anybody asks about an alert is what it actually saw.

    GREEN: it reads records, re-drives jobs the queue already permits, writes audit rows and
    incidents, and spends nothing.
    """
    import os
    from datetime import datetime, timezone

    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..ops import health

    with ctx.db.session() as session:
        readings = health.read(
            session, runner_state=_runner_state(), env=dict(os.environ),
            # Both are facts about this moment rather than about a shared variable: this
            # handler is running inside a worker's job, and the job arrived from a cadence.
            executing_worker=True,
            from_cadence=bool((ctx.job.inputs or {}).get("cadence")))
        verdict = health.verdict(readings)
        remediation = health.remediation(session, readings)

    # History for the persistence rule, from this handler's own audit trail. A record that
    # lives only in memory forgets every condition each time the container is replaced,
    # which is exactly when conditions happen.
    with ctx.db.session() as session:
        rows = list(session.scalars(
            select(AuditLog).where(AuditLog.action == "ops.health")
            .order_by(desc(AuditLog.id)).limit(health.ESCALATE_AFTER_SWEEPS - 1)))
    history = []
    for row in reversed(rows):
        bad = ((row.detail or {}).get("bad") or [])
        history.append([health.Reading(sig, health.DOWN) for sig in bad
                        if sig in health.SIGNALS])
    history.append(readings)
    persistence = health.persistence(history)

    detail = {
        "state": verdict["state"],
        "bad": sorted(set(verdict["down"]) | set(verdict["degraded"])),
        "why": verdict["why"],
        "repaired_elsewhere": remediation["repaired_elsewhere"],
        "must_escalate": remediation["must_escalate"],
        "persistent": persistence["persistent"],
    }
    ctx.audit("ops.health", detail=detail)

    # A health incident closes when its signal reads healthy again, and says what it read.
    # Before this, `health:<signal>` rows were opened on persistence and never closed, so a
    # signal that recovered stayed "bad for three sweeps" on the incident page indefinitely.
    from ..ops import incident_lifecycle

    by_signal = {r.signal: r for r in readings}
    raised = []
    with ctx.db.session() as session:
        def _still_bad(row) -> bool:
            reading = by_signal.get(row.signature.split(":", 1)[-1])
            # A signal this sweep did not read at all is not evidence of recovery.
            return reading is None or reading.bad

        def _recovered(row) -> str:
            reading = by_signal[row.signature.split(":", 1)[-1]]
            return (f"{reading.signal} read {reading.state} on the sweep at "
                    f"{datetime.now(timezone.utc).isoformat()}"
                    + (f": {reading.why}" if reading.why else "")
                    + f" (evidence: {reading.evidence})")

        life = incident_lifecycle.reconcile(session, "health:", _still_bad,
                                            resolution=_recovered)
        for signal in persistence["persistent"]:
            signature = f"health:{signal}"
            if signature in life["still_open"]:
                continue
            reading = by_signal.get(signal)
            incident_lifecycle.open_or_restate(
                session, signature=signature, severity="P1",
                summary=(f"{signal} has been bad for "
                         f"{health.ESCALATE_AFTER_SWEEPS} consecutive sweeps"),
                detail={"signal": signal,
                        "reading": reading.to_dict() if reading else None,
                        "consecutive": persistence["consecutive"].get(signal),
                        "escalation": [e for e in remediation["must_escalate"]
                                       if e["signal"] == signal]})
            raised.append(signature)
    detail["escalated"] = raised
    detail["recovered"] = life["resolved"]
    return detail


def _runner_state() -> dict:
    """What the in-process runner knows, when there is one."""
    try:
        from ..app import runner
    except Exception:  # pragma: no cover - the worker can run without the web app
        return {}
    return runner.STATE.to_dict()


@handlers.register("ops.sentinel")
def handle_stale_artefact_sentinel(ctx: JobContext) -> dict:
    """The permanent sentinel #173 asks for, against the artefacts that actually exist.

    Hourly. It compares every recorded artefact against the fingerprints the system holds
    now, and it also accounts for the artefacts that exist downstream with no provenance row
    at all -- because a sweep of the instrumented estate is not a sweep of the estate, and an
    artefact nobody fingerprinted has no mismatch to report.

    A mismatch raises a blocking incident against the product's own slug, which is the flag
    the publish path already consults, and asks for a rebuild. An absence raises a
    non-blocking one and joins the instrumentation backlog: blocking on absence today would
    halt the whole catalogue over instrumentation nobody fitted, which is a different problem
    from a stale artefact. `provenance.graduation()` says when that backlog is closed.

    GREEN: it reads records, writes incidents and audit rows, changes no artefact and spends
    nothing.
    """
    from ..ops import artefacts as provenance

    with ctx.db.session() as session:
        current = provenance.current_from_db(session)
        expected = provenance.expected_from_db(session)
        report = provenance.sweep(session, current=current, expected=expected)
        gate = provenance.graduation(session, current=current, expected=expected)

    detail = {
        "checked": report["checked"], "fresh": report["fresh"],
        "stale": report["stale"], "unproven": report["unproven"],
        "publication_blocked": report["publication_blocked"],
        "rebuild": report["rebuild"],
        "may_enforce_unproven": gate["may_enforce_unproven"],
    }
    ctx.audit("ops.sentinel", detail=detail)

    # A stale artefact is re-derivable, so the sentinel asks for the rebuild rather than
    # only reporting it -- through the dependency graph (#172), not per slug: the refs that
    # moved give the exact downstream rebuild set in topological order, enqueued once per
    # (product, new fingerprint) with the old and new fingerprints and the reason on the
    # job. Publication stays blocked until every descendant's provenance matches again
    # (`rebuild_graph.publication_gate`, read by store.publish and marketing.schedule).
    from ..ops import rebuild_graph

    changed: dict[str, str] = {}
    for v in report.get("verdicts", []):
        if v.get("state") == provenance.STALE:
            for ref in v.get("moved") or []:
                if ref in current:
                    changed[ref] = current[ref]
    detail["rebuild_enqueued"] = []
    detail["rebuild_already_queued"] = []
    if changed:
        from sqlalchemy import select

        from ..core.models import ArtefactProvenance

        with ctx.db.session() as session:
            previous: dict[str, str] = {}
            for row in session.scalars(select(ArtefactProvenance)):
                for ref, fp in (row.inputs or {}).items():
                    if ref in changed and fp != changed[ref]:
                        previous.setdefault(ref, fp)
            queued = rebuild_graph.enqueue(
                session, ctx.queue, changed=changed, per="product", previous=previous,
                reason=(f"stale-artefact sentinel: {sorted(changed)} moved under "
                        f"{report['stale']} recorded artefact(s)"))
        detail["rebuild_enqueued"] = queued["enqueued"][:50]
        detail["rebuild_already_queued"] = queued["already_queued"][:50]
        detail["rebuild_order"] = [r["key"] for r in queued["plan"]["rebuild"]][:50]
        detail["fingerprints"] = {ref: {"old": previous.get(ref), "new": fp}
                                  for ref, fp in sorted(changed.items())}
        ctx.audit("ops.rebuild_propagated", detail={
            k: detail[k] for k in ("rebuild_enqueued", "rebuild_already_queued",
                                   "rebuild_order", "fingerprints")})
    return detail


@handlers.register("ops.provenance_backfill")
def handle_provenance_backfill(ctx: JobContext) -> dict:
    """Lineage for the artefacts that already exist, from evidence already on file (#171).

    The write path now records every derived artefact as it is made. This is for the ones
    made before it did: production held 275 without a row. Each is tied to the job, audit
    row or output hash that proves what made it -- a certificate to its own release hash and
    the `gate.certified` row, a frame to the `assets.build` output carrying its sha256, a
    content piece to the `marketing.schedule` job whose window it was written in -- and an
    artefact nothing on file can account for is left unproven and counted, not invented.
    Every backfilled row says `code_commit=unknown`, because it is.

    GREEN: it reads records, writes provenance and audit rows, changes no artefact and spends
    nothing. Idempotent: a row that exists is never overwritten. `dry_run: true` reports
    without writing.
    """
    from ..ops import backfill

    dry_run = bool(ctx.job.inputs.get("dry_run"))
    with ctx.db.session() as session:
        report = backfill.run(session, dry_run=dry_run)
    ctx.audit("ops.provenance_backfill", detail={
        "dry_run": dry_run, "backfilled": report["backfilled"],
        "left_unproven": report["left_unproven"], "why": report["why"]})
    return report


@handlers.register("ops.capacity")
def handle_capacity_review(ctx: JobContext) -> dict:
    """This week's allocation, recorded rather than remembered (#30, #5).

    Weekly. The whole argument of #30 is that the mix has to arrive as a number, because the
    default for a system with no audience is to do more engineering -- engineering is the
    work that is here, it always finishes, and it never requires anybody outside this
    company. A module nobody calls *is* "whatever was easiest to pick up", so the allocation
    is a cadence on the same reasoning as #292's re-merchandising review: one that never
    runs is the same as one that does not exist.

    It also records whether the two production queues are open, because that condition and
    the allocation's phase read the same evidence and should be seen to agree.

    GREEN: it reads the regression corpus, certified releases and open incidents, writes an
    audit row, and changes nothing. It spends nothing -- no model call is made.

    Certification repair (C-48, #24, #25, #28, #45, #48, #229, #264, #270, #272): the funnel
    is now read from the database -- listing outcomes, orders, the ledger, published
    listings, support cases and cohorts -- instead of an empty `Observed()`. Every quantity
    with no source is UNMEASURED in the reading, never zero. The week's scale rule, CA$5K
    binding constraint, solver reallocation, per-visitor ranking, bundle attribution,
    holdouts, stress-tested confidence and scale-readiness verdict are written to
    `operating_readings` (kind `growth.weekly`), and a tilt toward more traffic is refused
    when no product passes the readiness gate.
    """
    from ..commerce import lanes
    from ..growth import weekly

    with ctx.db.session() as session:
        qa = lanes.qa_stable(lanes.observe(session))

    as_of = ctx.job.inputs.get("as_of")
    from datetime import date as _date

    today = _date.fromisoformat(as_of) if as_of else _date.today()
    reading = weekly.solve(ctx.db, today=today, qa=qa)
    plan = reading["allocation"]
    stored = weekly.record(ctx.db, reading)
    # #262: next week's forecast is written before the week starts, so that a later solve
    # can score it and lower confidence if the model has been optimistic.
    from ..scale import evidence as scale_evidence
    from ..scale.runrate import observe as _observe

    forecast = scale_evidence.record_forecast(
        ctx.db, _observe(ctx.db, today=today)["observed"], today=today)
    detail = {
        "mix": plan["mix"],
        "phase": plan["phase"],
        "tilted_toward": plan.get("tilted_toward"),
        "constraint": plan.get("constraint"),
        "two_queues_open": qa["stable"],
        "qa_reasons": qa["reasons"],
        "period": reading["period"],
        "reading_id": stored["id"],
        "observed": reading["observed"],
        "unmeasured": reading["unmeasured"],
        "scale_rule": reading["scale_rule"],
        "binding_constraint_5k": reading["binding_constraint_5k"].get("binding")
        or "UNMEASURED",
        "growth_constraint": reading["growth_constraint"].get("primary_constraint")
        or "UNMEASURED",
        "reallocation": reading["reallocation"],
        "scale_ready": reading["scale_readiness"]["ready"],
        "scale_tilt_refused": reading["scale_tilt_refused"],
        "winners_declarable": reading["bundle_attribution"]["winners_declarable"],
        "confidence": reading["confidence"]["probability"],  # F-189: None if UNMEASURED
        "confidence_state": reading["confidence"].get("state"),
        "resilience": reading["confidence"]["resilience_rung"]["evidence"].get("stress_test"),
        "conditions_met": reading["confidence"]["conditions_met"],
        "calibration_ceiling": reading["confidence"]["calibration_ceiling"],
        "forecast_recorded": forecast.get("recorded"),
        "scenario_conversion": reading["scenarios"]["conversion_source"],
        "cac_split": {k: (reading["cac_split"][k].get("value")
                          if isinstance(reading["cac_split"][k], dict) else None)
                      for k in ("new_customer_cac_cad", "blended_cac_cad",
                                "contribution_after_ads_cad")},
    }
    ctx.audit("ops.capacity", detail=detail)
    return detail


@handlers.register("ops.dependencies")
def handle_dependency_sweep(ctx: JobContext) -> dict:
    """#50 continuously and #29 acted on (C-69). Daily.

    The single-point dependency map is probed against the database -- the database itself and
    whether its recovery (the continuity restore) is proved, the model provider, the Etsy API,
    the tester roster -- and a failed probe, a recovery strategy that is missing or unproved,
    or a provider the cost ledger bills that the map does not name, opens an incident (and
    closes it when the probe recovers). The anti-fragility axes are read from the same rows
    and an existential concentration -- one AI provider the whole system runs on, today --
    is raised as an incident rather than written in a note.

    GREEN: reads rows and gates, writes incidents and one audit row. Spends nothing.
    """
    from ..ops import dependencies
    from ..scale import dependency as anti_fragility

    mapped = dependencies.sweep(ctx.db)
    fragility = anti_fragility.act(ctx.db)
    detail = {"failing": mapped["failing"], "unknown": mapped["unknown"],
              "unmapped": mapped["unmapped"], "opened": mapped["incidents_opened"]
              + fragility["incidents_opened"],
              "resolved": mapped["incidents_resolved"] + fragility["incidents_resolved"],
              "existential": fragility["existential"], "axes": fragility["axes"]}
    ctx.audit("ops.dependencies", detail=detail)
    return {**detail, "probes": mapped["probes"]}


@handlers.register("growth.conclude")
def handle_growth_conclude(ctx: JobContext) -> dict:
    """Feed results into pre-registered experiments and conclude what they allow (#265, #266).

    Daily. Per registered or running experiment: the expected value is re-estimated from
    measured contribution (None -- UNMEASURED -- while nothing has sold, and an experiment
    whose cost exceeds a measured value is killed), the metric is read from the rows that
    record it, and a reading goes through `record_persisted`, which concludes only at the
    pre-registered sample. A claim without its control present in the data is written as an
    association. With no data it concludes nothing, and says so per experiment. Also
    reports the quick/long balance.

    GREEN: reads outcomes, orders and cohorts; writes experiment rows and an audit row.
    """
    from ..growth.experiments import conclude_all

    out = conclude_all(ctx.db)
    ctx.audit("growth.concluded", detail={
        "examined": out["examined"], "concluded": out["concluded"],
        "killed": out["killed"], "no_data": out["no_data"],
        "balance": {k: out["balance"][k] for k in ("quick", "long", "long_runnable",
                                                   "balanced", "note")}})
    return {k: out[k] for k in ("examined", "concluded", "killed", "no_data", "balance",
                                "note")}


@handlers.register("ops.thrash")
def handle_thrash_sweep(ctx: JobContext) -> dict:
    """Break loops that repeat an identical call and result (#34).

    Hourly. `swarm.orchestrate.ThrashDetector` reads the last 72 hours of dead jobs and paid
    jobs; three identical (call, result) observations open or restate a P2 incident and
    cancel that call's queued retries, so a loop stops spending instead of being reported
    while it continues.
    """
    from ..swarm.orchestrate import thrash_sweep

    out = thrash_sweep(ctx.db)
    ctx.audit("ops.thrash", detail=out)
    return out


@handlers.register("seasonal.engine")
def handle_seasonal_engine(ctx: JobContext) -> dict:
    """The 365-day seasonal engine, daily (#33, #38, #131, #267, #286, #287, #289, #290,
    #291).

    Computes the rolling 30-365 day calendar, scores every occasion whose factors are all
    observed (none today: the reading lists what is UNMEASURED and the compression seed
    stays labelled as a seed), runs breakout mode where velocities exist, persists strike
    teams with what they own, plans storefront takeovers, rolls capacity forward, assembles
    collections from the catalogue's concepts, stamps a half-life on every culture signal,
    admits or refuses near-season products to the fast lane and checks admitted releases
    against the full gate list, and stamps provenance on every trend row. The reading is
    written to `operating_readings` (kind `seasonal.daily`).

    GREEN: computes, persists plans and stamps. Publishes nothing and spends nothing.
    """
    from ..seasonal import daily

    as_of = ctx.job.inputs.get("as_of")
    from datetime import date as _date

    reading = daily.run(ctx.db, today=_date.fromisoformat(as_of) if as_of else None)
    stored = daily.record(ctx.db, reading)
    summary = {
        "period": reading["period"], "reading_id": stored["id"],
        "horizons": {h["days"]: len(h["events"])
                     for h in reading["rolling_calendar"]["horizons"]},
        "scored_events": len(reading["engine"]["scored"]),
        "unscored_events": len(reading["engine"]["unscored"]),
        "priority_basis": reading["engine"]["priority_shares"]["basis"],
        "breakouts": reading["engine"]["breakout"].get("breakouts", []),
        "teams_active": reading["teams"]["persisted"]["active"],
        "teams_disbanded": reading["teams"]["persisted"]["disbanded"],
        "takeovers_planned": len(reading["takeovers"]["planned"]),
        "collections_coherent": reading["collections"]["coherent"],
        "half_lives": len(reading["half_lives"]["classified"]),
        "fast_lane_admitted": reading["fast_lane"]["admitted"],
        "trend_rows_stamped": reading["provenance"]["stamped"],
    }
    # C-60 (#128): a breakout's decomposition becomes an adjacent-original tournament now,
    # while the window is open, rather than a line in the reading.
    queued = []
    from ..swarm.orchestrate import priority_for

    for req in reading["engine"].get("breakout_mining", {}).get("requests", []):
        job = ctx.enqueue("creative_director", "creative.tournament", req,
                          priority=priority_for("creative.tournament"),
                          idempotency_key=(f"breakout_adjacent:{req['diverged_from']}:"
                                           f"{reading['period']}"))
        if job is not None:
            queued.append(job.id)
    summary["breakout_adjacent_queued"] = queued
    summary["collections_persisted"] = reading.get("collections_persisted", {})
    ctx.audit("seasonal.engine", detail=summary)
    return summary


@handlers.register("mjs.reviews")
def handle_mjs_reviews(ctx: JobContext) -> dict:
    """Read the benchmark shop's reviews and record which complaints recur (#2, #98).

    Weekly. Reviews move slowly and this is the one observation that reaches the
    `customer_pain` domain without this company having customers.

    GREEN by the authority matrix: a sanctioned read-only call to an endpoint already in the
    allowlist. Nothing is published, nobody is contacted, and no review text, reviewer or
    quotation is stored -- what is kept is a count per theme, because a complaint theme is a
    fact about this category and a review is somebody's words.
    """
    from ..intel import learning
    from ..intel.etsy_public import NotConfigured, ReadFailed
    from ..intel.observe import scan_reviews

    try:
        themes = scan_reviews(ctx.db)
    except (NotConfigured, ReadFailed) as e:
        ctx.audit("mjs.reviews_blocked", detail={"reason": str(e)[:300]})
        return {"ran": False, "reason": str(e)[:200]}

    learned = learning.ingest_complaints(ctx.db, themes=themes)
    ctx.audit("mjs.reviews", detail={"themes": themes, "learning": learned})
    return {"ran": True, "reviews_read": themes["reviews_read"],
            "recurring": len(themes["recurring"]),
            "learning_domains": len(learned.get("recorded") or [])}


@handlers.register("ops.capability_probes")
def handle_capability_probes(ctx: JobContext) -> dict:
    """Ask each capability whether it still works, and write down the answer.

    Six-hourly. Three of the build executor's gates now read a recorded successful use
    rather than a configured variable, and this is what records one. The rendered-page
    worker, the model's eyes and the culture source each fail in ways configuration cannot
    see: a worker answered with a bot-protection challenge, a vision call that returns a
    polite apology instead of a description, a free API that rate-limited us.

    Run on a cadence rather than once because a capability proven in March is not a
    capability. The gate this pattern replaced -- an environment variable holding
    twenty-eight requirements -- needed nobody to keep checking, which was the fault.

    GREEN by the authority matrix: three reads. The vision probe spends a fraction of a cent
    and is checked against the monthly ceiling first like every other model call.
    """
    from ..culture import feeds
    from ..gateway import anthropic as gw
    from ..gateway import images
    from ..intel import browser

    results = {
        "rendered_pages": browser.probe(ctx.db),
        "image_vision": gw.vision_probe(ctx.db, job_id=ctx.job.id),
        "culture_feed": feeds.probe(ctx.db),
        # `image_generation` was missing from this list, which is why the gate could not
        # open on its own. The probe existed, the gate read it, and nothing on any cadence
        # ever called it -- so a capability that had been demonstrably working for hours was
        # recorded nowhere, and twelve requirements stayed parked on the absence of a row
        # nobody was writing. A gate that reads evidence needs something that produces it.
        "image_generation": images.probe(ctx.db, job_id=ctx.job.id),
    }
    opened = sorted(k for k, v in results.items() if v.get("ok"))
    ctx.audit("ops.capability_probes", detail={
        "results": {k: {"ok": v.get("ok"), "reason": v.get("reason", "")[:200]}
                    for k, v in results.items()},
        "working": opened})
    return {"probed": sorted(results), "working": opened,
            "note": ("a capability proven once is not a capability. Each of these writes a "
                     "row a gate reads, and a gate whose evidence has gone stale closes")}


@handlers.register("culture.sweep")
def handle_culture_sweep(ctx: JobContext) -> dict:
    """Read reference interest for the topics this catalogue is merchandised against (#133).

    Daily. The radar has refused to report trends since it was written, correctly, because a
    source-less radar reporting nothing looks exactly like a radar with a quiet week. This
    connects the first of the two series #140 needs; the second is marketplace demand and
    arrives with listings, which is stated rather than papered over.

    GREEN: a free, keyless, sanctioned read with an identifying user agent, no spend and no
    account. Courtesy limits live in the module rather than in configuration.
    """
    from ..core.resilience import PermanentError, TransientError
    from ..culture import classify, demand, feeds, radar

    # Discovery first, so the radar can find what nobody thought to ask about (#133). A
    # hand-written topic list reflects its author rather than the culture, which is the
    # opposite of early discovery -- so the day's most-read articles are the candidates and
    # the fixed list is the floor.
    discovered: list[str] = []
    discovery_error = ""
    try:
        found = feeds.discover()
        discovered = [t["article"] for t in found["topics"]]
    except (PermanentError, TransientError) as exc:
        discovery_error = str(exc)[:300]

    filed = classify.classify(discovered, db=ctx.db) if discovered else {"filed": {}}
    # Sensitive topics are dropped here rather than filed and filtered later. The most-read
    # article on a given day is frequently a death or a disaster, and a radar that carries
    # those forward as opportunities is a radar nobody should have built.
    placed = {t: d for t, d in (filed.get("placed") or {}).items()
              if not classify.sensitive(t)}

    topics = feeds.env_override() or feeds.default_articles(ctx.db)
    watched = topics + [t for t in placed if t not in topics]
    result = feeds.sweep(ctx.db, watched[:feeds.MAX_ARTICLES_PER_SWEEP])

    # The marketplace half of #140's two series. Without it `lead_lag` has one series, and
    # one series cannot lead anything.
    demand_recorded = 0
    for reading in result["readings"]:
        got = demand.record(ctx.db, reading["article"], signal_key=reading["signal_key"])
        demand_recorded += got.get("recorded", 0)

    # Delivering the findings, not just listing where they could go (#147).
    routed = radar.route_findings(ctx.db)

    # The signals just stored, run through the culture engine (#134-#138, #141, #143-#146):
    # translate, score, route through clearance, era-combine, check the exit and persist the
    # translations as creative-development candidates -- then the white-space tournament for
    # strong signals, the rapid cell for actionable dated ones, collection architecture,
    # owned-IP proposals and launch outcomes. Nothing here reaches engineering.
    from ..culture import engine as culture_engine

    developed = culture_engine.run(
        ctx.db, [r for r in result["readings"] if not classify.sensitive(r["article"])],
        placed=placed)
    ctx.audit(culture_engine.ACTION_SWEEP, detail={
        k: v for k, v in developed.items() if k != "processed"})

    ctx.audit("culture.sweep", detail={
        "routed": routed["recorded"], "routed_skipped": routed["skipped"][:5],
        "source": result["source"], "recorded": result["recorded"],
        "attempted": result["attempted"], "failures": result["failures"][:5],
        "discovered": len(discovered), "placed": len(placed),
        "sensitive_dropped": len(filed.get("sensitive") or []),
        "discovery_error": discovery_error,
        "demand_points": demand_recorded,
        "translated": developed["translated"], "candidates": developed["candidates"]})
    return {"ran": True, "recorded": result["recorded"],
            "attempted": result["attempted"],
            "failures": len(result["failures"]),
            "discovered": len(discovered), "placed": len(placed),
            "demand_points": demand_recorded, "routed": routed["recorded"],
            "channel": result["channel"], "measures": result["measures"],
            "culture": {k: v for k, v in developed.items()
                        if k not in ("processed", "tournaments", "rapid")},
            "tournaments": len(developed["tournaments"]),
            "rapid_responses": len(developed["rapid"])}


# The cadence this handler runs on, by name. The *period* is read from
# `runtime.worker.CADENCES` and the *batch* is derived from the ceiling at run time, so there
# is no images-per-run constant here any more.
#
# There was: `GALLERY_BATCH = 25`, which with a two-hourly period is three hundred images a
# day and, at the padded per-image estimate, about CA$8.70 of spend under a `market_radar`
# ceiling of CA$4.00. Two authorised numbers in two files with nothing reconciling them. The
# owner ruled on 2026-09-25 to keep the CA$4.00 and adapt the cadence, so the number is gone
# rather than corrected -- a corrected literal drifts again the next time either side moves.
GALLERY_CADENCE = "gallery_analysis"


@handlers.register("intel.gallery_analysis")
def handle_gallery_analysis(ctx: JobContext) -> dict:
    """Judge as many observed gallery images as the ceiling allows, in listing-recency order.

    Requirement 209. Recency order because that is the order commercial value arrives in.

    **The batch size is derived from the budget, not declared beside it.** It used to be
    `GALLERY_BATCH = 25` on a two-hourly cadence -- three hundred images a day, about CA$8.70
    of spend, under a `market_radar` ceiling of CA$4.00 a day that nothing on this path
    checked. Two owner-derived numbers in two files, each defensible, disagreeing by a factor
    of two. The owner ruled on 2026-09-25: keep the CA$4.00 and adapt the cadence. So the
    batch is computed every run from that ceiling and this cadence's own period, and the
    per-image estimate is the padded one the ceiling check uses rather than the measured mean,
    because a batch sized on the average overshoots on the expensive half of it.

    **A run that fits nothing is a report, not a failure.** The images stay queued and the
    next run takes them. Three separate stops are reported by name, because they mean
    different things and have different answers: the agent's daily permission (wait for
    tomorrow), this purpose's share of the month (`may_spend` -- wait, or have the share
    raised), and the authorised monthly ceiling (an owner decision with measured usage
    attached). None of them is ever answered by a cheaper model.

    Still self-limiting: once the backlog empties this judges only new and changed listings,
    so the standing cost falls to whatever the benchmark shop publishes.

    Refuses to run before a vision probe has succeeded. Writing the call is not the same as
    the call working, and an analysis run against a broken vision path would record a batch
    of refusals as though the backlog had been attempted.

    GREEN: reads observed URLs, spends inside the ceiling, stores observations and never a
    picture or a description of the depicted design.
    """
    from ..finance import spend_policy
    from ..gateway import anthropic as gw
    from ..intel import benchmarks, vision
    from .worker import cadence_seconds

    if not gw.vision_usable(ctx.db):
        ctx.audit("intel.gallery_analysis_blocked",
                  detail={"reason": "no vision probe has succeeded"})
        return {"ran": False,
                "reason": ("no vision.probe has succeeded, so nothing has proven it can "
                           "look at an image. The backlog waits rather than filling with "
                           "refusals")}

    # This purpose's share of the month, checked before the batch rather than discovered at
    # the ceiling. Unchanged: it is a stop rather than a rate, and folding it into the batch
    # arithmetic below would quietly re-decide it.
    allowance = spend_policy.may_spend(ctx.db, vision.TASK)
    if not allowance["may_spend"]:
        ctx.audit("intel.gallery_analysis_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"], "allowance": allowance,
                "constrained": ("benchmark gallery analysis stopped at its share of the "
                                "month rather than being run on a weaker model")}

    # How many images fit, from the ceiling and this cadence's own period. The per-image
    # figure is read from the same estimator the pre-call ceiling check uses, so the batch and
    # the guard cannot be sized on different arithmetic.
    fit = spend_policy.work_that_fits(
        ctx.db, agent=vision.AGENT, purpose=vision.TASK,
        period_seconds=cadence_seconds(GALLERY_CADENCE),
        unit_cost_cad=vision.per_image_estimate_cad())
    if fit["units"] < 1:
        ctx.audit("intel.gallery_analysis_capped", detail=fit)
        return {"ran": False, "reason": fit["why"], "allowance": fit,
                "binding_ceiling": fit["binding_ceiling"],
                "constrained": ("benchmark gallery analysis judged nothing this run because "
                                "the cadence is sized to fit the authorised ceiling. The "
                                "backlog is unchanged and the next run takes it")}

    result = vision.analyse(ctx.db, benchmarks.MJS_KEY, limit=fit["units"],
                            job_id=ctx.job.id)
    ctx.audit("intel.gallery_analysis", detail={
        "judged": result["judged"], "attempted": result["attempted"],
        "remaining": result["remaining"], "cost_cad": result["cost_cad"],
        "batch_derived_from": fit["binding_ceiling"],
        "batch_units": fit["units"], "stopped_by": result.get("stopped_by", ""),
        "failures": result["failures"][:5]})
    return {"ran": True, "judged": result["judged"], "attempted": result["attempted"],
            "remaining": result["remaining"], "cost_cad": result["cost_cad"],
            "batch_units": fit["units"], "binding_ceiling": fit["binding_ceiling"],
            "stopped_by": result.get("stopped_by", ""),
            "failures": len(result["failures"])}


@handlers.register("creative.blind_review")
def handle_blind_review(ctx: JobContext) -> dict:
    """Write the competitive blind review row `visual.parity` reads (#75, #71, #218, #315).

    Deterministic and free: it compares the listing renders on file against what the
    category-matched benchmark galleries were *observed* to be -- the recorded vision
    vocabulary and the deep audit's API facts -- and asks no model anything. One row per
    catalogue product, every run, so the reader in `runtime.pipeline._benchmark_quality`
    finds a dated verdict rather than nothing.

    A pod nobody has judged enough of, or a product with no render, is written as
    `materially_inferior: None`, which parity reads as unjudged and blocks. Today's expected
    outcome is `inferior` or UNKNOWN across the catalogue; that is the finding, not a fault.

    GREEN: reads its own asset records and already-recorded observations, writes audit rows,
    spends nothing, publishes nothing.
    """
    from ..creative import blind_review

    result = blind_review.run(ctx.db, job_id=ctx.job.id)

    # #218: a product the MJs challenge finds materially inferior goes back to creative
    # development rather than waiting at the parity gate. The ladder is walked for the
    # failed competitive dimension and the product's photography job -- the department
    # that makes its listing creative -- is re-queued with the finding; that job gates
    # itself on image generation, so a closed capability refuses there honestly rather
    # than being bypassed here. Once per product per day.
    from ..products.builder import for_slug
    from ..publish import listing_asset
    from ..visual import parity
    from ..visual.gallery import escalation_plan, gates_now

    today = date.today().isoformat()
    returned = []
    for row in result["reviews"]:
        if not row.get("returns_to_development"):
            continue
        slug = row["slug"]
        cir = for_slug(slug)
        plan = escalation_plan([parity.COMPETITIVE], deterministic_available=cir is not None,
                               gate_open=gates_now(ctx.db))
        job_type = ("assets.model_photography"
                    if cir is not None and listing_asset.needs_the_model(cir)
                    else "assets.owned_photography")
        job = ctx.enqueue("publishing", job_type,
                          {"slug": slug, "reason": "blind_review_inferior",
                           "review_audit_id": row.get("audit_id"),
                           "why": str(row.get("why") or "")[:300]},
                          idempotency_key=f"return-to-development:{slug}:{today}")
        entry = {"slug": slug, "job_type": job_type, "job_id": getattr(job, "id", None),
                 "already_queued": job is None, "ladder": [r["action"] + ":" + r["status"]
                                                           for r in plan["rungs"]]}
        ctx.audit("creative.returned_to_development", artifact=slug,
                  detail={**entry, "why": row.get("why"), "review_audit_id": row.get("audit_id")})
        returned.append(entry)

    ctx.audit("creative.blind_review_run", detail={
        "reviewed": result["reviewed"], "counts": result["counts"],
        "method_version": result["method_version"],
        "returned_to_development": [r["slug"] for r in returned]})
    return {"ran": True, **{k: result[k] for k in ("reviewed", "counts", "method_version")},
            "returned_to_development": returned}


@handlers.register("creative.grid_tournament")
def handle_grid_tournament(ctx: JobContext) -> dict:
    """#126: the search-grid blind tournament, judged by an independent panel.

    For each pod with enough audited benchmark thumbnails and at least one render of ours,
    render the blinded grid, have three vision judges rank it (median, each in its own
    shuffled order, never told which cells are ours), and record the verdict. A pod that
    cannot be gridded is recorded as refused with its reason, not skipped silently.

    YELLOW-light spend inside the ceiling: every judge call is budget-checked and reserved
    before it is made, like gallery vision, and the run stops on the ceiling.
    """
    from ..creative import blind_review, blinded
    from ..gateway import anthropic as gw
    from ..publish import listing_asset

    provider = gw.provider_for("gallery_observation")
    by_pod: dict[str, list[dict]] = {}
    pod_of: dict[str, str] = {}
    for slug, title in blind_review.catalogue_slugs():
        pod_of[slug] = blind_review.pod_for(slug, title)
        frames = listing_asset.frames_for(ctx.db, slug=slug)
        hero = [dict(f, slug=slug) for f in frames if (f.get("role") or "hero") == "hero"][:1]
        if hero:
            by_pod.setdefault(pod_of[slug], []).extend(hero)
    results = {}
    stopped = False
    for pod, ours in sorted(by_pod.items()):
        try:
            out = blinded.grid_tournament(ctx.db, ours, pod=pod, provider=provider,
                                          seed=ctx.job.id or 0, job_id=ctx.job.id)
            results[pod] = {k: out[k] for k in ("verdict", "why", "our_scores",
                                                  "benchmark_cells", "our_cells")}
            results[pod]["panel"] = out["panel"]
        except (blinded.GridRefused, blinded.GridJudgeRefused) as exc:
            results[pod] = {"verdict": "refused", "why": str(exc)[:300]}
        if (results[pod].get("panel") or {}).get("stopped_by"):
            stopped = True
            break

    # #126's engineering half: concept boards the pre-engineering gate sent here, each gridded
    # on its own beside its category's benchmark set, so the verdict the gate reads is about
    # that concept and nothing else of ours. Recorded under `concepts` by concept key.
    concepts: dict[str, dict] = {}
    for board in (ctx.job.inputs.get("concepts") or []):
        key = str(board.get("key") or "")
        if not key:
            continue
        if stopped:
            concepts[key] = {"verdict": "refused", "why": "the run stopped on the budget "
                             "ceiling before this concept was gridded"}
            continue
        ours = [{"slug": key, "image_ref": str(board.get("board_image") or "")}]
        try:
            out = blinded.grid_tournament(ctx.db, ours, pod=str(board.get("pod") or ""),
                                          provider=provider, seed=ctx.job.id or 0,
                                          job_id=ctx.job.id)
            concepts[key] = {k: out[k] for k in ("verdict", "why", "our_scores",
                                                  "below_threshold", "unjudged",
                                                  "benchmark_cells")}
            if (out.get("panel") or {}).get("stopped_by"):
                stopped = True
        except (blinded.GridRefused, blinded.GridJudgeRefused) as exc:
            concepts[key] = {"verdict": "refused", "why": str(exc)[:300]}

    # #126's release half, per product: the verdict of the grid its pod was judged in. A
    # product whose pod was never gridded carries no verdict, which release reads as not
    # cleared -- never as cleared by default.
    products = {slug: {"pod": pod, "verdict": (results.get(pod) or {}).get("verdict"),
                       "why": (results.get(pod) or {}).get("why", "no render of ours in "
                                                                  "this pod was gridded")}
                for slug, pod in pod_of.items()}
    ctx.audit("creative.grid_tournament", detail={"pods": results, "concepts": concepts,
                                                   "products": products})
    return {"ran": True, "pods": {k: v["verdict"] for k, v in results.items()},
            "concepts": {k: v["verdict"] for k, v in concepts.items()}}


@handlers.register("gate.lanes")
def handle_lane_routing(ctx: JobContext) -> dict:
    """#5 and #43 over the certified catalogue, plus #126's release-side grid reading.

    For every certified release: route it to the Fast or Flagship queue from its own measured
    profile (`lanes.assign`, which keeps one queue until core QA is demonstrably stable),
    check that it ran every gate it was owed (`lanes.check_release`, from the stages its
    certificate records -- absent is not passing), and read whether the blind search grid
    cleared its pod. A release that skipped or failed an owed gate has its listing withdrawn
    and the refusal audited, exactly as a refused certificate does.

    Then #43: every Class B/C product whose sample has not passed becomes testing demand,
    needed by the day its buying window opens (evergreen: now), forecast from the calendar,
    checked against recorded tester capacity by specialty, and assigned to the least-loaded
    qualified tester -- or reported unassigned, which today is the `tester_roster` gate.

    GREEN: reads certificates, listings and physical-test rows; writes audit rows and at
    most a listing withdrawal. Spends nothing, calls no model, publishes nothing.
    """
    from sqlalchemy import select

    from ..commerce import lanes
    from ..core.models import Listing
    from ..creative import preengineering
    from ..quality import testers

    raw = ctx.job.inputs.get("as_of")
    today = date.fromisoformat(raw) if raw else date.today()
    routed = lanes.route_certified(ctx.db, today=today)

    withdrawn: list[str] = []
    for card in routed["products"]:
        artifact = f"{card['slug']}@{card['version']}"
        grid = preengineering.release_grid_verdict(ctx.db, card["slug"])
        card["grid"] = {k: grid.get(k) for k in ("cleared", "verdict", "why")}
        ctx.audit("gate.lane_routed", artifact=artifact, detail={
            "lane": card.get("lane"), "routed": card.get("routed"),
            "two_queues_open": routed["two_queues_open"],
            "why": card.get("why") or card.get("note"),
            "fast_refusals": card.get("fast_refusals"),
            "flagship_refusals": card.get("flagship_refusals"),
            "paced_by": card.get("paced_by"), "profile": card.get("profile"),
            "release": card.get("release"), "search_grid": card["grid"]})
        release = card.get("release")
        if release is not None and not release.get("ok"):
            with ctx.db.session() as s:
                rows = list(s.scalars(select(Listing).where(
                    Listing.product_slug == card["slug"], Listing.state != "withdrawn")))
                for listing in rows:
                    listing.state = "withdrawn"
            ctx.audit("gate.lane_release_refused", artifact=artifact,
                      detail={"why": release.get("why"), "listings_withdrawn": len(rows)})
            if rows:
                withdrawn.append(artifact)

    lane_capacity = _lane_capacity(ctx, lanes)

    seeds = {seed.slug: seed for seed in POOL}
    demand_rows = []
    for card in routed["products"]:
        profile, seed = card.get("profile"), (seeds.get(card["slug"])
                                              or lanes._launch0_seed(card["slug"]))
        if not profile or seed is None:
            continue
        event = _event(seed.season) if seed.season else None
        if event is None:
            needed_by = today
        else:
            if event.event_date < today:
                # This year's occasion has passed; the demand is for next year's.
                import dataclasses

                event = dataclasses.replace(event, event_date=event.event_date.replace(
                    year=event.event_date.year + 1))
            needed_by = shopping_window(event)[0]
        demand_rows.append({"slug": card["slug"], "risk_class": profile["risk_class"],
                            "specialty": profile["pod"],
                            "make_hours": sum(seed.maker_hours) / 2.0,
                            "needed_by": needed_by})
    tester_plan = testers.plan(ctx.db, demand_rows, today=today)
    ctx.audit("quality.tester_plan", detail={
        "as_of": today.isoformat(),
        "demands": tester_plan["forecast"]["demands"],
        "late": [r["product_slug"] for r in tester_plan["forecast"]["late"]],
        "tester_days_required": tester_plan["forecast"]["tester_days_required"],
        "capacity": {k: tester_plan["capacity"][k] for k in (
            "reliable_testers", "unproven_testers", "by_specialty",
            "single_points_of_failure", "uncovered_specialties", "schedulable")},
        "assignments": tester_plan["assignments"], "unassigned": tester_plan["unassigned"],
        "note": tester_plan["note"]})

    return {"products": len(routed["products"]),
            "two_queues_open": routed["two_queues_open"],
            "lanes": {c["slug"]: c.get("lane") for c in routed["products"]},
            "balance": routed["balance"]["counts"],
            "release_refused": routed["release_refused"], "withdrawn": withdrawn,
            "grid_uncleared": sorted(c["slug"] for c in routed["products"]
                                     if not c["grid"]["cleared"]),
            "testing_demands": len(tester_plan["forecast"]["demands"]),
            "testing_late": len(tester_plan["forecast"]["late"]),
            "testers_assigned": len(tester_plan["assignments"]),
            "testers_unassigned": len(tester_plan["unassigned"]),
            "lane_capacity": lane_capacity}


# How far a starved production lane's queued engineering work is moved up, and the most it
# may be moved above its own band in total: enough to be claimed first within its band's
# neighbourhood, never enough to outrank a customer or a truth defect.
LANE_STARVED_BOOST = 5


def _lane_capacity(ctx: JobContext, lanes) -> dict:
    """#5's two floors on making capacity, measured and acted on (C-68).

    The split the claim enforces is `lanes.allocate` over the engineering workers the #30 mix
    gives product/QA, recorded as `lanes.capacity` for `swarm.capacity.share_decision` to
    read. The split actually run -- engineering job-seconds per lane over seven days -- is
    checked against both floors with `lanes.check_mix`; a lane below its floor has its queued
    engineering work moved up (bounded), so the next claims go to it. With nothing run yet
    the measured split is UNMEASURED and nothing is moved.
    """
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..swarm import capacity as cap
    from ..swarm.orchestrate import priority_for

    budgets = cap.function_budgets(cap.latest_mix(ctx.db)["mix"], cap.worker_threads())
    plan = lanes.allocate(float(budgets.get(cap.PRODUCT_QA, 1)))
    split = cap.measured_lane_split(ctx.db)
    verdict, starved, boosted = None, [], []
    if split["shares"]:
        measured = {lane: split["shares"].get(lane, 0.0) for lane in lanes.LANES}
        verdict = lanes.check_mix(measured)
        floors = {lanes.FAST: lanes.FAST_FLOOR, lanes.FLAGSHIP: lanes.FLAGSHIP_FLOOR}
        starved = sorted(l for l in lanes.LANES if measured[l] < floors[l])
    if starved:
        with ctx.db.session() as s:
            for job in s.scalars(select(Job).where(
                    Job.status.in_((JobStatus.PENDING, JobStatus.FAILED)),
                    Job.job_type.in_(sorted(cap.ENGINEERING_JOB_TYPES)))):
                slug = cap.slug_of(job)          # cir.compile/gate.certify carry inputs.cir
                if cap.product_lane(ctx.db, slug) not in starved:
                    continue
                floor = max(0, priority_for(job.job_type) - LANE_STARVED_BOOST)
                if job.priority > floor:
                    job.priority = max(floor, job.priority - LANE_STARVED_BOOST)
                    boosted.append(job.id)
    detail = {"shares": plan["shares"], "units": plan["units"],
              "engineering_workers": budgets.get(cap.PRODUCT_QA, 1),
              "measured": split, "mix_check": verdict,
              "measured_status": "measured" if split["shares"] else "UNMEASURED",
              "starved": starved, "boosted_jobs": boosted}
    ctx.audit(cap.LANE_CAPACITY_ACTION, detail=detail)
    return detail


@handlers.register("intel.acceptance")
def handle_intel_acceptance(ctx: JobContext) -> dict:
    """Run the API+vision acceptance checklist offline against the DB (#222, #320).

    Files one mission report per step, each graded through `launch.access` under the
    evidence kind `api_gallery_traversal`, and records the run. Nothing is fetched: every
    step is proved or failed from evidence the scans and the gallery analysis already stored,
    which is the only kind of evidence an acceptance test should accept.

    GREEN: read-only against the DB apart from its own observation rows and audit row.
    """
    from ..intel import acceptance

    result = acceptance.run(ctx.db, job_id=ctx.job.id)
    ctx.audit("intel.acceptance", detail={
        "verdict": result["verdict"], "passed": result["passed"], "of": result["of"],
        "failed_steps": result["failed_steps"], "grade": result["grade"]})
    return {"ran": True, "verdict": result["verdict"], "passed": result["passed"],
            "of": result["of"], "failed_steps": result["failed_steps"]}


@handlers.register("ops.retention")
def handle_retention(ctx: JobContext) -> dict:
    """Prune what nothing reads, and never what a gate counts (2026-09-25).

    Nothing pruned anything before this. The audit log grows about 4,700 rows a day, the job
    table about 900 and the dead-letter queue 21; `JobQueue.purge_dead` existed and was called
    from nowhere in `src/`, which is a function without a policy behind it. At those rates the
    audit log passes 1.7 million rows within a year, on the Postgres instance that is the main
    cost under the CA$20/month infrastructure ceiling.

    The policy is in `ops.retention` and the reasoning with it. What matters here is what it
    will not do: it does not touch `cost_entries` or the ledger, it keeps every audit action a
    gate counts over all time, it keeps the most recent rows of every action whatever their
    age, it never removes a dead letter that is a defect, and it refuses to run at all when the
    code reads an audit action the policy has no decision about -- because that is precisely
    the state in which a retention run quietly lowers a number somebody is gating on.

    The refusal is recorded and returned rather than raised. A retention run that declines to
    run is not a failure of the queue, and dead-lettering it would turn "somebody added a
    reader" into an incident with the wrong name on it.

    GREEN: it deletes rows this policy names in this system's own operational tables. No
    publication, no spend, no customer contact.
    """
    from ..ops import retention

    try:
        result = retention.apply(ctx.db)
    except retention.RetentionRefused as exc:
        ctx.audit("ops.retention_refused",
                  detail={"why": str(exc)[:600],
                          "unknown_read_actions": retention.unknown_read_actions()})
        return {"ran": False, "reason": str(exc)[:600],
                "unknown_read_actions": retention.unknown_read_actions(),
                "what_to_do": ("add each action to `ops.retention.KNOWN_READ_ACTIONS` with "
                               "how it is read. Nothing was deleted")}

    # The policy in force is recorded with the run, not only the outcome. A deletion whose
    # horizon and protected list are not in the row beside it is a deletion a future session
    # cannot check against the policy it was made under -- and the policy is the part that will
    # have moved by then.
    ctx.audit("ops.retention", detail={
        "removed": result["removed"],
        "reservations": result["reservations"],
        "audit_kept_protected": result["audit_log"]["kept_because_protected"],
        "jobs_kept": result["jobs"]["kept"],
        "dead_letters_kept": result["dead_letters"]["kept"],
        "policy": retention.state()})
    return {"ran": True, "removed": result["removed"],
            "reservations": result["reservations"],
            "kept": {"audit_protected": result["audit_log"]["kept_because_protected"],
                     "audit_recent_per_action":
                         result["audit_log"]["kept_because_recent_for_their_action"],
                     "jobs": result["jobs"]["kept"],
                     "dead_letters": result["dead_letters"]["kept"]}}


@handlers.register("ops.offsite_archive")
def handle_offsite_archive(ctx: JobContext) -> dict:
    """Write the day's archive off this hosting provider, and prove it restores.

    Requirement 51's second half. `ops.continuity` proves the export restores; this proves a
    copy of it exists somewhere that losing Railway does not take with it. They are separate
    jobs because they answer separate questions, and a single job reporting one verdict would
    let a healthy local restore stand in for an archive that was never written.

    An unconfigured destination is recorded as a failed archive, not skipped. The gate reads
    these rows: a job that returned early on a missing variable would leave the last row
    saying `ok` from whenever the credential last worked, which is the shape of defect this
    build keeps finding.

    GREEN by the authority matrix: it reads the database, writes one object to a bucket the
    owner provisioned, and reads it back. No publication, no model spend, no customer
    contact.
    """
    from ..core import offsite, workspace

    # Only the archive needs the directory -- it writes the export there and uploads it, and
    # everything below this reads the database -- so the block is exactly that call. It was
    # `tempfile.mkdtemp`, which left one directory holding a full compressed export behind
    # every day this cadence ran.
    with workspace.work_dir(ctx.job.inputs.get("work_dir"), prefix="offsite-") as work:
        record = offsite.archive(ctx.db, work_dir=work)

    pruned: dict = {"skipped": "the archive did not complete, so nothing was aged out"}
    if record.get("ok"):
        # Only after a good write. Pruning on the day the upload failed would remove the
        # oldest copy at exactly the moment the newest one does not exist.
        pruned = offsite.prune(ctx.db)

    ctx.audit("offsite.archived" if record.get("ok") else "offsite.failed",
              detail={"ok": record.get("ok"), "stage": record.get("stage"),
                      "reason": record.get("reason", "")[:300],
                      "key": record.get("key", ""),
                      "rows_restored": record.get("rows_restored"),
                      "pruned": pruned.get("deleted")})

    if not record.get("ok") and offsite.configured():
        # Configured and failing is an incident; unconfigured is a gate the owner has not
        # opened yet and is already reported as an owner action.
        from ..core.models import Incident

        with ctx.db.session() as s:
            s.add(Incident(kind="offsite_archive_failed", severity="high",
                           summary=f"off-provider archive failed at {record.get('stage')}",
                           detail={"reason": record.get("reason", "")[:400]}))

    return {"ok": bool(record.get("ok")), "stage": record.get("stage"),
            "reason": record.get("reason", "")[:300], "pruned": pruned}


@handlers.register("creative.image_benchmark")
def handle_image_benchmark(ctx: JobContext) -> dict:
    """Render the same six Brambleloop trials on every credentialled candidate and score
    them blind (owner decision 2026-09-20: measure before locking a provider).

    Runs on a cadence rather than on a button because the button needs a credential nobody
    in a session holds, and because the benchmark is genuinely re-runnable: a provider's key
    arrives weeks after another's, and a candidate already measured under this exact rubric
    is reused rather than re-rendered. What that leaves is only the new work.

    It refuses to start when the month's allocation is spent rather than running on a
    cheaper judge, which is the policy stated as code: quality first, cost second, waste
    never.
    """
    import os

    from ..finance import spend_policy
    from ..gateway import image_bench

    # The approved benchmark budget as a stop, not as a number in a report. It was being
    # applied per run, so four runs each stayed inside a figure the owner approved once and
    # the cumulative total passed it while every individual run looked compliant.
    spent = image_bench.spent_to_date(ctx.db)
    if spent >= image_bench.BENCHMARK_CEILING_CAD:
        from ..core.models import OwnerAction

        with ctx.db.session() as s:
            from sqlalchemy import select

            already = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == "image_benchmark_budget",
                OwnerAction.done == False))  # noqa: E712
            if already is None:
                s.add(OwnerAction(
                    requirement_key="image_benchmark_budget",
                    action=("Decide whether to raise the image-provider benchmark budget "
                            "above CA$%.2f, or to stop the benchmark and choose from what "
                            "has been measured." % image_bench.BENCHMARK_CEILING_CAD),
                    reason=("The benchmark has spent CA$%.2f of an approved CA$%.2f and has "
                            "not finished. The overrun bought no measurement: it went to "
                            "defects in the benchmark itself -- an identity trial that ran "
                            "without its reference image, two providers whose reference "
                            "conditioning was wired wrong, a judge token budget too small "
                            "for the rubric, and a production ceiling variable still set to "
                            "CA$25. All are fixed; the runs that hit them are not "
                            "refundable." % (spent, image_bench.BENCHMARK_CEILING_CAD)),
                    max_cost_cad=10.0, minutes=2,
                    consequence_of_delay=("The image-provider choice stays unmade and the "
                                          "twelve requirements behind it stay parked."),
                    blocks="the canonical model pack and every listing image"))
        ctx.audit("image.benchmark_budget_reached", detail={
            "spent_to_date_cad": spent,
            "approved_cad": image_bench.BENCHMARK_CEILING_CAD})
        return {"ran": False, "reason": "the approved benchmark budget is spent",
                "spent_to_date_cad": spent,
                "approved_cad": image_bench.BENCHMARK_CEILING_CAD,
                "owner_action": "image_benchmark_budget"}

    allowance = spend_policy.may_spend(ctx.db, image_bench.JUDGE_TASK)
    if not allowance["may_spend"]:
        ctx.audit("image.benchmark_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"],
                "constrained": ("the image-provider benchmark stopped at its share of the "
                                "month rather than being judged on a weaker model")}

    # `run` owns the directory its renders land in and removes it when the judging is done --
    # the renders exist to be judged and nothing outside the run reads them. A `work_dir` from
    # the job inputs overrides that, for an operator who wants to keep the images.
    result = image_bench.run(ctx.db, env=dict(os.environ),
                             work_dir=ctx.job.inputs.get("work_dir"))
    decision = result.get("decision") or {}
    ctx.audit("image.benchmark" if result.get("ran") else "image.benchmark_blocked", detail={
        "ran": result.get("ran"),
        "reason": result.get("reason", "")[:300],
        "spent_cad": result.get("spent_cad"),
        "reused": result.get("reused"),
        "unmeasured": result.get("unmeasured"),
        "decided": decision.get("decided"),
        "locked": decision.get("locked"),
        "winner": decision.get("winner"),
        "why": str(decision.get("why") or "")[:400],
    })
    # An incomplete benchmark tries again soon; a complete one waits for the weekly cadence.
    #
    # Learned the hard way within an hour of shipping this: a deploy went out while the first
    # run was working through its second candidate, the container was replaced, and the
    # durable queue re-drove the job -- which worked only because each candidate's scores are
    # stored as it finishes. Had it not been, the weekly cadence would have left a half-
    # measured benchmark sitting for seven days with a winner it must not name.
    #
    # The re-enqueue is conditional on *progress*, not on incompleteness. A candidate that
    # holds a credential and fails every time -- which is exactly the state of the Google
    # project denied access on 2026-09-21 -- would otherwise re-queue this job for ever.
    from ..gateway import images

    # Progress means a *stored* measurement, which means a complete schedule. Computing it
    # from the run's own results instead put this job in a paid loop: a candidate that
    # scored but did not finish its schedule counted as progress, was never stored, so the
    # outstanding set never shrank and the job re-queued itself every few minutes at about
    # CA$1.85 a time. A follow-up condition that cannot become false is a spend with no
    # stopping rule.
    from ..gateway import image_bench

    measured_now = {c.key for c in image_bench.CANDIDATES
                    if c.can_hold_an_identity
                    and image_bench.stored_result(ctx.db, c) is not None}
    credentialled = set(images.available(dict(os.environ)))
    outstanding = credentialled - measured_now
    progressed = bool(measured_now - {r["model"] for r in (result.get("reused") or [])})
    if outstanding and progressed and result.get("ran"):
        ctx.enqueue("creative_director", "creative.image_benchmark",
                    {"because": sorted(outstanding)},
                    idempotency_key=f"image-benchmark-{sorted(outstanding)}")

    return {"ran": result.get("ran"), "spent_cad": result.get("spent_cad"),
            "winner": decision.get("winner"), "locked": decision.get("locked"),
            "outstanding": sorted(outstanding),
            "unmeasured": [u["model"] for u in result.get("unmeasured") or []]}


@handlers.register("creative.model_tournament")
def handle_model_tournament(ctx: JobContext) -> dict:
    """Run the canonical-model tournament and stop before choosing (#199).

    The owner's direction is the design: do not generate one woman and make her canonical
    because she happened to be first. So this generates a field, screens it, stress-tests the
    survivors across materially different scenes, and presents them. There is no branch in
    here that selects, and `visual.tournament` contains no function that could.

    Runs once: `already_run` is keyed on the brief, so a re-deploy does not re-render
    twenty-four faces, and a changed brief does.
    """
    import os

    from ..core import workspace
    from ..finance import spend_policy
    from ..visual import brief, tournament

    if brief.owner_candidate_supplied():
        # The owner saw the field, rejected all five finalists and supplied their own
        # candidate. A tournament now would render twenty more women to answer a question
        # that has been answered -- and it would do it again every time the brief changed,
        # because the brief is what this job is keyed on.
        return {"ran": False,
                "reason": ("the owner supplied a canonical-model candidate on "
                           f"{brief.CANDIDATE_GIVEN_AT} and rejected the finalists. "
                           "The pack is built by creative.model_reference_pack"),
                "rejected_finalists": brief.REJECTED_FINALISTS_NOTE}

    allowance = spend_policy.may_spend(ctx.db, "model_tournament")
    if not allowance["may_spend"]:
        ctx.audit("model.tournament_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"]}

    previous = _tournament_on_file(ctx.db)
    if previous is not None:
        return {"ran": False, "reason": "this brief's tournament has already run",
                "finalists": previous.get("clear_both_floors", []),
                "awaiting": "owner selection"}

    env = dict(os.environ)
    # The whole run is inside the block because the renders live in this directory and the
    # presentation reads them: releasing it earlier would delete the images the package is
    # built from. It was `tempfile.mkdtemp`, which is the worst of the ten sites -- a
    # tournament renders a field of candidate images and kept every one of them forever.
    with workspace.work_dir(ctx.job.inputs.get("work_dir"),
                            prefix="tournament-") as work:
        field = tournament.generate_candidates(
            ctx.db, count=ctx.job.inputs.get("count") or tournament.DEFAULT_CANDIDATES,
            env=env, work_dir=work)
        if not field.get("ran") or not field.get("candidates"):
            # A field of nothing is recorded with its reasons rather than returned quietly. The
            # first live run produced no candidates and the only trace was a job-completed
            # count; why every render or screen failed was not readable from anywhere.
            detail = {**field, "brief_fingerprint": _brief_fingerprint(), "finalists": [],
                      "clear_both_floors": [],
                      "why_empty": ("no candidate survived generation and screening. The "
                                    "per-candidate reasons are in `failures`")}
            ctx.audit(tournament.TOURNAMENT_ACTION, detail=detail)
            return {"ran": bool(field.get("ran")), "candidates": 0,
                    "failures": field.get("failures", [])[:5]}

        finalists = field["candidates"][:brief.TARGET_FINALISTS]
        results = [tournament.stress_test(ctx.db, f, env=env, work_dir=work) for f in finalists]
        package = tournament.present(ctx.db, results)
        package["field"] = {"generated": field["generated"], "excluded": field["excluded"],
                            "failures": field["failures"][:5], "provider": field["provider"]}
        package["spent_cad"] = round(
            float(field.get("spent_cad") or 0.0)
            + sum(float(r.get("spent_cad") or 0.0) for r in results), 4)
        package["brief_fingerprint"] = _brief_fingerprint()

        ctx.audit(tournament.TOURNAMENT_ACTION, detail=package)

        # The owner asked to be shown the finalists. That is a consequential decision, so it
        # goes in the one owner queue rather than into a log somebody might read.
        from sqlalchemy import select

        from ..core.models import OwnerAction

        with ctx.db.session() as s:
            open_row = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == "canonical_model_selection",
                OwnerAction.done == False))  # noqa: E712
            if open_row is None:
                s.add(OwnerAction(
                    requirement_key="canonical_model_selection",
                    action=("Choose the permanent Brambleloop model from the finalists at "
                            "/api/model-tournament, then confirm the selection."),
                    reason=(f"{len(results)} finalists were stress-tested across "
                            f"{len(brief.STRESS_SCENES)} controlled scenes; "
                            f"{len(package['clear_both_floors'])} cleared both hard floors "
                            f"(facial identity and whole-person morphology, independently). "
                            f"Nothing selects itself: a candidate that became canonical by "
                            f"topping a table is an identity nobody chose."),
                    max_cost_cad=0.0, minutes=10,
                    consequence_of_delay=("Every model-bearing frame stays blocked, because a "
                                          "drift check with no reference pack is unavailable "
                                          "rather than passing."),
                    blocks="all model-led listing imagery and the creative parity gate"))

        return {"ran": True, "finalists": len(results),
                "clear_both_floors": package["clear_both_floors"],
                "spent_cad": package["spent_cad"], "selected": None}


@handlers.register("visual.portrait_repair")
def handle_portrait_repair(ctx: JobContext) -> dict:
    """A bounded repair attempt on the approved canonical portrait (owner, 2026-09-23).

    A job rather than an endpoint, for the reason this codebase already learned: a GET that
    spends money spends it every time a sweep walks the routes.

    Idempotent by the portrait's content hash, so a redeploy does not re-buy an attempt
    that has already been made, and a replaced portrait is a new question asked
    automatically.

    AMBER: it renders up to `MAX_CANDIDATES` images of a person and makes vision calls,
    inside a CA$1.00 ceiling, and refuses to render at all when the judging balance would
    leave a candidate unassessable. It adopts nothing: the canonical reference is replaced
    only on the owner's visual approval of the side-by-side evidence.
    """
    import tempfile

    from ..visual import brief, photoreal, portrait_repair

    fingerprint = photoreal._portrait_fingerprint(brief.approved_portrait())
    already = _repair_on_file(ctx.db, fingerprint=fingerprint)
    if already:
        return {"ran": False, "reason": "repair_already_attempted",
                "verdict": already.get("verdict"),
                "spent_cad": already.get("spent_cad")}

    with tempfile.TemporaryDirectory(prefix="portrait-repair-") as work_dir:
        out = portrait_repair.propose(ctx.db, work_dir=work_dir)

    out["portrait_fingerprint"] = fingerprint
    ctx.audit(portrait_repair.ACTION, detail=out)
    return {"ran": out.get("ran"), "verdict": out.get("verdict"),
            "waiting_on": out.get("waiting_on"),
            "spent_cad": out.get("spent_cad"),
            "candidates": len(out.get("candidates") or []),
            "why": (out.get("why") or "")[:300]}


def _repair_on_file(db, *, fingerprint: str) -> dict | None:
    """A repair attempt already made against exactly these bytes."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import portrait_repair

    if not fingerprint:
        return None
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == portrait_repair.ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            # A refusal is not an attempt. If it never rendered because the balance was
            # spent, the question is still open and must be asked again when it is not.
            if detail.get("ran") and detail.get("portrait_fingerprint") == fingerprint:
                return detail
    return None


@handlers.register("visual.provider_trial")
def handle_provider_trial(ctx: JobContext) -> dict:
    """Measure whether the tiling blocker is specific to the incumbent image provider.

    A job rather than an endpoint for the reason this codebase already learned: a GET that
    spends money spends it every time a sweep walks the routes.

    Authorised by the owner on 2026-09-23 up to CA$4.00, enforced in
    `provider_trial.CEILING_CAD` rather than remembered. Idempotent by challenger and
    method version, so a redeploy does not re-buy a trial that has already run.

    AMBER: it renders images and makes vision calls, inside a ceiling checked before every
    render. It publishes nothing, switches nothing and never renders the canonical model.
    """
    import tempfile

    from ..gateway import images
    from ..visual import provider_trial

    challenger = ctx.job.inputs.get("challenger") or "nano-banana-2"
    if challenger not in images.available():
        return {"ran": False, "reason": ("this challenger has no credential in this "
                                         "environment, so nothing could be rendered with "
                                         "it"), "challenger": challenger}

    already = _trial_on_file(ctx.db, challenger=challenger)
    if already:
        return {"ran": False, "reason": "trial_already_run", "challenger": challenger,
                "verdict": already.get("verdict"), "spent_cad": already.get("spent_cad")}

    with tempfile.TemporaryDirectory(prefix="provider-trial-") as work_dir:
        out = provider_trial.run(
            ctx.db, challenger=challenger, work_dir=work_dir,
            prior_incumbent=provider_trial.incumbent_evidence(ctx.db))

    ctx.audit(provider_trial.ACTION, detail=out)
    return {"ran": True, "challenger": challenger,
            "spent_cad": out.get("spent_cad"),
            "stopped_at_ceiling": out.get("stopped_at_ceiling"),
            "recommendation": (out.get("verdict") or {}).get("recommendation"),
            "why": ((out.get("verdict") or {}).get("why") or "")[:300]}


def _trial_on_file(db, *, challenger: str) -> dict | None:
    """A completed trial for this challenger under the current render method."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..publish import owned_photography
    from ..visual import provider_trial

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == provider_trial.ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if detail.get("challenger") != challenger:
                continue
            # Was *this challenger* actually put to the question?
            #
            # The question is asked of the challenger's own attempts, and only of the ones
            # that produced an image. Three ways to get this wrong and all three were live
            # at some point in this file:
            #
            #   A funding refusal files a row with no attempts at all, and reading that as
            #   "already run" would have blocked the real trial permanently the moment the
            #   balance returned.
            #
            #   A trial where the challenger returned 402 on every attempt still contains
            #   the incumbent's renders, so counting *any* rendered attempt would credit the
            #   challenger with an experiment it never took part in.
            #
            #   And -- the one this comment used to get wrong -- counting the challenger's
            #   unrendered attempts as evidence. `nano-banana-2` answered 402 "prepayment
            #   credits are depleted" to every attempt on 2026-09-23, and that ran the
            #   challenger out of the trial for good: the row said tried, so no later deploy
            #   would ask again, and when the owner funded the account the next morning and
            #   said "re-probe the actual production credential, do not rely on the previous
            #   failed probe", the boot enqueue answered "not needed". A refusal is not a
            #   measurement. `made: False` means the provider was never asked to draw
            #   anything, so nothing was learned about it that funding could not change.
            #
            # Re-asking is close to free, which is what makes this the safe direction to be
            # wrong in: an attempt that never renders spends CA$0.00 and is judged by
            # nothing, and the incumbent arm is reused rather than re-bought. A provider
            # that keeps refusing therefore costs a job per deploy and no money, while the
            # old rule cost the entire experiment.
            theirs = [a for a in (detail.get("attempts") or [])
                      if a.get("provider") == challenger and a.get("made")]
            if not theirs:
                continue
            # A trial run under a superseded render method is evidence about that method,
            # not about this one -- the same rule the assets themselves follow. Read from
            # the challenger's own render rather than the first made attempt of any
            # provider, which could be the incumbent's.
            if theirs[0].get("method_version") != owned_photography.METHOD_VERSION:
                continue
            return detail
    return None


@handlers.register("assets.owned_photography")
def handle_owned_photography(ctx: JobContext) -> dict:
    """Render one owned product image for a certified product, and judge it.

    A job rather than an endpoint, for the reason the benchmark learned the hard way: a GET
    that spends money is a GET that spends money every time a test sweep walks the routes.
    The seasonal cycle reads what this produced; it does not produce it.

    Idempotent by product and version: an asset already made for this release is not remade,
    so the cadence costs nothing after the first run and a new release gets its own picture.
    """
    import os

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..core import workspace
    from ..gateway import images
    from ..products.builder import for_slug
    from ..publish import owned_photography

    if not images.usable(ctx.db):
        return {"ran": False, "reason": ("image generation has not been demonstrated in "
                                         "this environment, so there is nothing to render "
                                         "with. `ops.capability_probes` records it")}

    slug = ctx.job.inputs.get("slug") or _representative_slug(ctx.db)
    if not slug:
        return {"ran": False, "reason": "no certified product to photograph"}

    cir = for_slug(slug)
    if cir is None:
        return {"ran": False, "reason": f"no CIR for {slug!r}"}

    # C-80 defect 8 (Codex P11): a job enqueued as a #81 rung is a distinct strategy. It
    # reads the rung and the failed dimensions, has its own one-attempt budget, changes what
    # the rung says it changes (brief, composition or tool), and persists its result so the
    # next parity verdict resumes the ladder from here instead of at the first rung.
    rung = str(ctx.job.inputs.get("rung") or "")
    if not rung and str(ctx.job.inputs.get("reason") or "").startswith("parity_escalation:"):
        rung = str(ctx.job.inputs["reason"]).split(":", 1)[1]
    failed = list(ctx.job.inputs.get("failed") or [])
    if rung:
        return _owned_photography_rung(ctx, cir, slug, rung, failed)

    next_move = owned_photography.what_to_do_next(ctx.db, slug=slug, version=cir.version)
    if not next_move["render"]:
        return {"ran": False, "reason": next_move["reason"], "slug": slug,
                "attempts": next_move["attempts"], "why": next_move["why"],
                "verdict": next_move.get("verdict"),
                "usable": next_move["reason"] == "usable_asset_on_file"}

    result = compile_cir(cir)
    if not result.ok:
        return {"ran": False, "reason": f"{slug} does not compile, so there is nothing true "
                                        f"to photograph"}

    # The render and its verdict both happen inside `make`, which puts the bytes it must keep
    # in the artifact store before it returns, so the directory is only needed for that call.
    # It was `tempfile.mkdtemp`, on a cadence, writing rendered photography.
    with workspace.work_dir(ctx.job.inputs.get("work_dir"),
                            prefix="owned-asset-") as work:
        record = owned_photography.make(
            ctx.db, cir, build_twin(cir, result),
            occasion=ctx.job.inputs.get("occasion", ""),
            env=dict(os.environ), work_dir=work)
    ctx.audit(owned_photography.ACTION, detail=record)
    return {"ran": True, "slug": slug, "made": record.get("made"),
            "verdict": record.get("verdict"), "why": record.get("why"),
            "usable_as_listing_asset": record.get("usable_as_listing_asset"),
            "spent_cad": record.get("spent_cad", 0.0)}


def _owned_photography_rung(ctx: JobContext, cir, slug: str, rung: str,
                            failed: list[str]) -> dict:
    """One #81 rung, executed as the strategy it names and recorded as attempted or not."""
    import os

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..core import workspace
    from ..publish import owned_photography
    from ..visual import tournament
    from ..visual.gallery import ESCALATION_RESULT_ACTION, GENERATION_RUNGS, RUNG_BRIEFS

    version = cir.version
    # Codex CB2-P11: a rung is enqueued for the release whose parity failed, named by
    # job.inputs["version"]. The catalogue may since have rebuilt the CIR under a new version;
    # rendering that one and filing it as the old release's rung result would be a result for
    # a release nobody asked about. Refused explicitly, recorded under the requested release,
    # nothing rendered or spent; the new release walks its own ladder.
    requested = str(ctx.job.inputs.get("version") or "").strip()
    stale = bool(requested) and requested != str(version)
    if stale:
        version = requested
    key = f"{slug}@{version}"

    def result(**detail):
        ctx.audit(ESCALATION_RESULT_ACTION, artifact=key,
                  detail={"rung": rung, "failed": failed, **detail})
        return {"ran": bool(detail.get("attempted")), "slug": slug, "version": version,
                "rung": rung, **detail}

    if stale:
        return result(attempted=False, reason="stale_version", current_version=cir.version,
                      why=(f"this rung was asked for {slug}@{requested}, but the CIR on file "
                           f"is {cir.version}; a render of {cir.version} is not a result for "
                           f"{requested}, so nothing was rendered"))
    if rung not in GENERATION_RUNGS:
        return result(attempted=False, reason="not_a_generation_rung",
                      why=f"{rung!r} is not a rung this job executes")
    if owned_photography.rung_attempts(ctx.db, slug=slug, version=version, rung=rung):
        return result(attempted=False, reason="rung_already_attempted",
                      why="this rung was already attempted for this release; the ladder "
                          "advances rather than repeating a strategy")
    brief = RUNG_BRIEFS[rung]
    env = dict(os.environ)
    earlier = {a.get("provider") for a in owned_photography.assets_for(
        ctx.db, slug=slug, version=version) if a.get("provider")}
    provider_key = ""
    if brief["provider"] == "alternate":
        provider_key = tournament.alternate_provider(ctx.db, env, exclude=earlier)
        if not provider_key:
            return result(attempted=False, reason="no_alternate_tool",
                          why=f"no permitted image model other than {sorted(earlier)} is "
                              f"available in this environment; the rung cannot be executed "
                              f"and is recorded so, not skipped")
    constraints = tuple(brief["constraints"])
    if rung == "regenerate_constrained":
        constraints += (f"The previous render of this product failed these checks: "
                        f"{', '.join(failed) or 'unnamed'}. Each must be visibly answered.",)
    compiled = compile_cir(cir)
    if not compiled.ok:
        return result(attempted=False, reason="does_not_compile",
                      why=f"{slug} does not compile, so there is nothing true to photograph")
    with workspace.work_dir(ctx.job.inputs.get("work_dir"), prefix="owned-rung-") as work:
        record = owned_photography.make(
            ctx.db, cir, build_twin(cir, compiled), occasion=ctx.job.inputs.get("occasion", ""),
            env=env, work_dir=work, provider_key=provider_key, rung=rung,
            constraints=constraints)
    ctx.audit(owned_photography.ACTION, detail=record)
    return result(attempted=bool(record.get("made")), made=record.get("made"),
                  usable=bool(record.get("usable_as_listing_asset")),
                  verdict=record.get("verdict"), why=(record.get("why") or "")[:300],
                  provider=record.get("provider") or provider_key or None,
                  composition=brief["composition"], constraints=list(constraints),
                  spent_cad=record.get("spent_cad", 0.0))


def _representative_slug(db) -> str:
    """The certified product-first product that most needs an asset next.

    It used to return the first product-first slug by row id, unconditionally -- so it
    returned the same product every day for ever. One product was photographed and the
    other ten certified products never were, while the cadence reported success daily and
    nothing anywhere counted the difference. A launch that depends on listing imagery had,
    in truth, no usable assets at all.

    Now it skips the products that are finished with and returns one that still needs work,
    so the cadence walks the catalogue instead of standing still on its first row. Products
    whose attempts are exhausted are skipped too: spending on them again is the same method
    asked the same question, and leaving them selected would block every product behind
    them.

    Falls back to the old behaviour when every product is done or exhausted, because
    returning nothing would make the handler report "no certified product to photograph"
    for a catalogue that is simply finished -- a different thing, and the honest reply
    belongs to `what_to_do_next` rather than to this.
    """
    from sqlalchemy import select

    from ..core.models import Product

    with db.session() as s:
        rows = [p.slug for p in s.scalars(select(Product).order_by(Product.id))]

    from ..products.builder import for_slug
    from ..publish import owned_photography

    product_first = []
    for slug in rows:
        cir = for_slug(slug)
        if cir is not None and owned_photography.needs_no_model(cir):
            product_first.append((slug, cir))

    # Untried products first, then the ones with attempts already spent.
    #
    # Row order alone put `winter-village-graphghan` first, and a pictorial graphghan is
    # the hardest thing in this catalogue for a generator to reproduce -- so the whole
    # catalogue queued behind three attempts at its worst case while nine simpler products
    # (garlands, placemats, ornaments, a table runner) had no asset at all.
    #
    # It is also the weaker measurement. Nine products at one attempt each says far more
    # about whether the method works than one product at three, which is the sampling rule
    # `visual.reliability` is built on: a dimension asked once cannot be classified, and
    # three tries at a single hard case is one case, not three.
    # Ordered by attempts on this release, then by how often this product has failed under
    # any method, and only then by row order.
    #
    # The second key is what row id used to decide. When v5 reset every product to zero
    # attempts the first key went flat and the cadence went straight back to
    # `winter-village-graphghan` -- the hardest thing in this catalogue -- which is exactly
    # the arbitrary tie-break the ordering fix existed to remove. History survives a version
    # bump: a product that has failed five times under three methods is evidence about the
    # product, and it belongs behind the ones that have never failed at all.
    waiting = []
    for index, (slug, cir) in enumerate(product_first):
        move = owned_photography.what_to_do_next(db, slug=slug, version=cir.version)
        if move["render"]:
            waiting.append((move["attempts"],
                            owned_photography.historical_failures(db, slug=slug),
                            index, slug))
    if waiting:
        waiting.sort()
        return waiting[0][-1]
    return product_first[0][0] if product_first else (rows[0] if rows else "")


def owned_asset_coverage(db) -> dict:
    """How much of the certified catalogue actually has a usable listing asset."""
    from sqlalchemy import select

    from ..core.models import Product
    from ..products.builder import for_slug
    from ..publish import owned_photography

    with db.session() as s:
        rows = [p.slug for p in s.scalars(select(Product).order_by(Product.id))]

    slugs, versions = [], {}
    for slug in rows:
        cir = for_slug(slug)
        if cir is not None and owned_photography.needs_no_model(cir):
            slugs.append(slug)
            versions[slug] = cir.version
    return owned_photography.coverage(db, slugs=slugs, versions=versions)


# Owner-action keys this assessment does not produce and must never close.
#
# The closer above exists because the queue only ever grew, and it was right to build it.
# What it did not know is that it is not the only thing that writes to that queue: the
# reference-pack build raises `canonical_model_approval`, the tournament raises
# `canonical_model_selection`, the image benchmark raises `image_benchmark_budget`, and
# `ops/funding.py` raises the provider-balance row. To the readiness assessment every one
# of those is a key it did not generate, which is indistinguishable from a request that
# has been satisfied -- so it closed them.
#
# It closed the canonical-model approval on the run after the pack passed all nine of its
# conditions. The owner was not asked to approve the identity, the pack sat ready, and
# nothing anywhere reported a problem: one subsystem tidying away another subsystem's
# question, in the name of not asking twice.
#
# A closer may only close what it opens. This list is that rule, written down.
NOT_THE_READINESS_ASSESSMENTS_TO_CLOSE: frozenset[str] = frozenset({
    "canonical_model_approval",
    "canonical_model_selection",
    "image_benchmark_budget",
    "model_provider_balance",
})


# Prefixes of owner-queue keys other subsystems raise and close on their own evidence. Kept
# beside the key list above for the same reason: a closer may only close what it opens.
#   support.first_response:  the 24h/36h buyer first-response watch (F-043), closed when the
#                            reply is recorded as sent;
#   etsy.oauth.              the legacy orders re-authorisation key (F-541), adopted into
#                            `etsy.auth:reauthorise` by the next orders run, never swept.
NOT_THE_READINESS_PREFIXES_TO_CLOSE: tuple[str, ...] = (
    "support.first_response:",
    "etsy.oauth.",
)

#: Etsy owner-queue items (`intel.etsy_surfaces` keys) that are deferred until the step
#: before first sale (F-874): identity/tax and payment settings.
DEFERRED_UNTIL_FIRST_SALE: frozenset[str] = frozenset({
    "legal_and_tax_setup",
    "payment_settings_setup",
})


# ---- A3-03: the owner actions launch.readiness owns, and how each proves it cleared ----
#
# The closer used to close every open key it had not generated this run, minus an exemption
# list. That is default-close: any subsystem whose prefix was missing from the list -- the
# buyer correction-notice approval, a test draft stranded in the live shop, the monthly
# spend-ceiling escalation, the launch-week Search Visibility reading -- vanished from the
# owner's queue with its condition still true. The rule is now inverted: an action is closed
# here only if its key is one this assessment raises AND its condition re-check passes.

#: Requirement keys whose owner request `launch.readiness.assess` itself generates.
READINESS_REQUIREMENT_KEYS: frozenset[str] = frozenset({
    "etsy_shop", "payout", "listing_fees", "physical_calibration", "model_credits",
    "benchmark_challenge", "brand_clearance", "artifact_storage", "phase",
})


def _requirement_cleared(key: str, readiness) -> bool:
    """The requirement was assessed on this run and no longer asks the owner for anything."""
    for r in getattr(readiness, "requirements", ()):
        if r.key == key:
            return bool(r.ready) or r.owner_request is None
    return False  # not assessed this run: unknown is not cleared


def _access_cleared(key: str, readiness) -> bool:
    from ..launch import access

    try:
        return bool(access.available(key))
    except KeyError:
        return False


def _credential_cleared(key: str, readiness) -> bool:
    from ..ops import credential_register as cr

    name = key[len(cr.KEY_PREFIX):]
    for e in cr.REGISTER:
        if e.name == name:
            return e.status == cr.ROTATED
    return False  # a credential the register does not name cannot be proven rotated


def _access_keys() -> frozenset[str]:
    from ..launch import access

    return frozenset(c.key for c in access.CAPABILITIES)


def _credential_prefix() -> str:
    from ..ops import credential_register as cr

    return cr.KEY_PREFIX


#: (matcher, re-check). The matcher says the key is readiness-owned; the re-check proves the
#: condition behind it is satisfied now. Both must hold for the closer to touch the row.
READINESS_OWNED_ACTIONS: tuple[tuple[str, object, object], ...] = (
    ("launch.readiness requirements", lambda k: k in READINESS_REQUIREMENT_KEYS,
     _requirement_cleared),
    ("launch.access capability requests", lambda k: k in _access_keys(), _access_cleared),
    ("ops.credential_register rotations", lambda k: k.startswith(_credential_prefix()),
     _credential_cleared),
)


def readiness_may_close(key: str, readiness) -> bool:
    """True only for a readiness-owned key whose condition re-check proves it cleared."""
    if not key:
        return False
    for _name, owns, cleared in READINESS_OWNED_ACTIONS:
        if owns(key):
            try:
                return bool(cleared(key, readiness))
            except Exception:  # noqa: BLE001 - a re-check that fails proves nothing
                return False
    return False


def _owner_actions_held_open_by_incidents(session) -> set[str]:
    """Owner-action keys an open incident names as its remedy: their condition still holds."""
    from sqlalchemy import select

    from ..core.models import Incident

    held: set[str] = set()
    for inc in session.scalars(select(Incident).where(
            Incident.resolved == False)):  # noqa: E712
        key = (inc.detail or {}).get("owner_action")
        if isinstance(key, str) and key:
            held.add(key)
    return held


def _first_sale_step_reached(db) -> dict:
    """Whether the shop is at the step before first sale, from observed rows only (F-874).

    Reached when a listing exists on Etsy (an `etsy_listing_id` was recorded by the publish
    path) or a listing is active: the next thing that can happen is a buyer. Before that,
    asking the owner for identity verification and a tax position is asking early for a
    legal step nothing yet needs.
    """
    from sqlalchemy import func, or_, select

    from ..core.models import Listing

    with db.session() as s:
        on_etsy = int(s.scalar(select(func.count()).select_from(Listing).where(or_(
            Listing.etsy_listing_id != "", Listing.state == "active"))) or 0)
    return {"reached": on_etsy > 0, "listings_on_etsy": on_etsy,
            "deferred_until_then": sorted(DEFERRED_UNTIL_FIRST_SALE) if not on_etsy else []}


def _reconcile_canonical_model_action(db) -> None:
    """Keep the approval question open for as long as an unapproved pack is waiting."""
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..visual import model_registry

    pack = model_registry.canonical_pack(db)
    if pack is not None:
        # Approved and frozen, so the question is answered -- and answering it has to
        # close the row, not merely stop reopening it. Returning early left the owner
        # being asked to approve an identity they had already approved, which is the
        # standing instruction this queue breaks most easily: do not ask me to repeat an
        # action already completed. A condition that stops being true has to take its
        # question with it.
        with db.session() as s:
            row = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == "canonical_model_approval",
                OwnerAction.done == False))  # noqa: E712
            if row is not None:
                row.done = True
                row.reason = (f"Approved and frozen as canonical pack version "
                              f"{pack.version} at {pack.approved_by_owner_at}. Closed "
                              f"because the decision was made, not because the question "
                              f"expired.")
        return
    package = _pack_on_file(db)
    if package and package.get("approval_conditions"):
        _refresh_canonical_model_action(db, package)


def cycle_proof_incomplete(db) -> bool:
    """Whether #300's chain still has not closed its assets link.

    Used to decide whether a deploy re-asks the question. A weekly cadence is right
    unattended and wrong right after the thing that was blocking it changes: the canonical
    identity was frozen minutes after this week's run had already happened, so the next
    scheduled answer would have been seven days stale. A deploy is what re-asks.

    Self-limiting on purpose. It reads the last recorded run and returns False once the
    assets step actually ran, so this costs one cycle per deploy only while the chain is
    still open and nothing once it closes -- rather than spending on every deploy forever
    to re-prove something already proved.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "seasonal.cycle_proof")
                       .order_by(desc(AuditLog.id)).limit(1))
    if row is None:
        return True
    steps = (row.detail or {}).get("steps") or []
    assets = next((x for x in steps if x.get("step") == "assets"), {})
    return assets.get("state") != "ran"


def _refresh_canonical_model_action(db, package: dict) -> None:
    """Keep the owner's approval row describing the pack that exists now.

    It told the owner "face unverifiable, whole-person morphology unverifiable" for a day
    after those stopped being true, because the row was created on the first build and
    never touched again. The one sentence somebody reads to decide whether to look was
    describing a pack five versions old -- a value written once and read for a week, which
    is the same defect as a gate reading configuration: right at the moment it was written
    and nothing keeping it right.

    The two floors were also the wrong summary. `morphology_floor: unverifiable` is the
    correct and expected answer when a stress scene puts her in a winter coat, so quoting
    it made a healthy pack read as a failed one. The approval decision rests on the nine
    conditions, so those are what this says.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction

    conditions = package["approval_conditions"]
    total = len(conditions)
    met = sum(1 for c in conditions.values() if c["met"])
    unmet = [k for k, c in conditions.items() if not c["met"]]
    standing = (
        f"All {total} approval conditions are met and the pack is ready for your review."
        if package["ready_for_owner_approval"] else
        f"{met} of {total} approval conditions are met; still outstanding: "
        f"{', '.join(unmet)}. It is not ready yet -- this row is here so the work is "
        f"visible, not so you approve something that has not passed.")
    reason = (f"{standing} Built from your supplied candidate, pack "
              f"{package['pack_version']}, fingerprint "
              f"{package.get('candidate_fingerprint')}. Approval freezes the identity, "
              f"versions the reference pack and makes it the conditioning source for "
              f"every model-bearing frame; nothing is frozen until you say so.")

    with db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "canonical_model_approval",
            OwnerAction.done == False))  # noqa: E712
        if open_row is not None:
            open_row.reason = reason
            return
        s.add(OwnerAction(
            requirement_key="canonical_model_approval",
            action=("Approve or reject the canonical Brambleloop model at "
                    "/api/model-pack: the neutral portrait, the torso and full-length "
                    "body references, the close-fitting validation frame, the stress set "
                    "and the measured results."),
            reason=reason,
            max_cost_cad=0.0, minutes=10,
            consequence_of_delay=("Every model-bearing frame stays blocked, because a "
                                  "drift check with no reference pack is unavailable "
                                  "rather than passing."),
            blocks="all model-led listing imagery and the creative parity gate"))


@handlers.register("creative.model_freeze")
def handle_model_freeze(ctx: JobContext) -> dict:
    """Freeze the approved reference pack, then prove the identity gate on it (#200, #201).

    A job rather than an authenticated endpoint, because the operator token is a secret
    this repository must never hold and the owner's decision is not a secret: it is
    recorded in `freeze.OWNER_APPROVAL` for the same reason `brief.py` holds the aesthetic
    direction as code. An approval living only in a chat log is one the next prompt
    paraphrases.

    Naturally idempotent. `select_canonical` refuses a second canonical outright, so a
    re-run reports the identity that exists rather than replacing her -- replacing her is
    a redesign and a separate owner decision.

    GREEN: it writes one row, runs deterministic checks, and makes two vision calls -- the
    freeze-time realism gate, which asks whether the candidate's own reference images read
    as photographs before making her the one every render is conditioned on. About one cent,
    once, at a decision that cannot be taken back. No render, nothing published. That
    sentence used to say "no model call, no spend" and stopped being true when the gate was
    added; leaving it would have been a docstring asserting a property the code no longer
    had, which is the same defect as a test asserting one.
    """
    from ..visual import freeze as freeze_mod

    record = freeze_mod.approved()
    if not record:
        return {"ran": False, "reason": ("no owner approval is recorded, and freezing an "
                                         "identity nobody chose is the one thing this "
                                         "path exists to prevent")}
    try:
        outcome = freeze_mod.freeze(ctx.db, owner_approved=True)
    except freeze_mod.FreezeRefused as exc:
        # A refusal is the correct outcome when no pack can state every dimension, and it
        # is recorded rather than raised: the job did its job by declining.
        ctx.audit("model.freeze_refused", detail={"why": str(exc)[:400]})
        return {"ran": True, "frozen": False, "refused": str(exc)[:300]}

    proof = freeze_mod.enforcement_proof(ctx.db)
    ctx.audit("model.frozen", detail={"freeze": outcome, "enforcement": proof,
                                      "approval": record})
    return {"ran": True, "frozen": outcome.get("frozen"),
            "already_canonical": outcome.get("already_canonical", False),
            "pack_version": outcome.get("pack_version"),
            "skipped_newer": [s.get("pack_version")
                              for s in outcome.get("skipped_newer", [])],
            "enforcement_proved": proof.get("proved"),
            "enforcement_failed": proof.get("failed", [])}


@handlers.register("creative.model_reference_pack")
def handle_model_reference_pack(ctx: JobContext) -> dict:
    """Build the reference pack from the owner's candidate and stop before freezing it.

    The owner rejected all five tournament finalists and supplied their own concept. What
    that changes is *which* woman; what it does not change is that she is not canonical
    until she is proven and approved. So this renders the two reference frames and the
    controlled scenes, measures face and whole-person morphology separately, and raises the
    approval as an owner action. There is no branch in here that selects.
    """
    import os

    from ..core import workspace
    from ..finance import spend_policy
    from ..visual import reference_pack

    # A rolling deploy runs two commits at once, and the queue does not care which replica
    # picks a job up. The boot enqueue stamps the version it wanted; a replica still running
    # the previous build would otherwise consume the key, compute the *old* fingerprint,
    # find the old pack, report "already built" and leave the corrected pack unrun with its
    # key spent -- which is what happened at 16:12, invisibly, because the answer it gave
    # was a true sentence about a different question.
    wanted = ctx.job.inputs.get("pack_version")
    if wanted and wanted != reference_pack.PACK_VERSION:
        asked, produces = (reference_pack.pack_number(wanted),
                           reference_pack.pack_number(reference_pack.PACK_VERSION))
        if asked and produces and asked < produces:
            # The opposite case, found in the dead-letter queue: a job stamped for a pack
            # *older* than any running build produces. No replica will ever take it, so
            # raising would fail it on every attempt for ever -- a poisoned row that reads
            # as a defect. The work it asked for is superseded; completing it as a
            # stand-aside says so once and lets the row rest.
            return {"ran": False, "superseded_by": reference_pack.PACK_VERSION,
                    "asked_for": wanted,
                    "why": (f"this job asked for pack {wanted!r}, which is older than the "
                            f"{reference_pack.PACK_VERSION!r} every running build now "
                            f"produces. Nothing will ever build the older pack again, so "
                            f"the job is completed as superseded rather than failed for "
                            f"another replica that does not exist")}
        raise RuntimeError(
            f"this job asked for pack {wanted!r} and this build produces "
            f"{reference_pack.PACK_VERSION!r}. Failing so another replica takes it, rather "
            f"than answering about a pack nobody asked for")

    allowance = spend_policy.may_spend(ctx.db, "model_reference_pack")
    if not allowance["may_spend"]:
        ctx.audit("model.reference_pack_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"]}

    previous = _pack_on_file(ctx.db)
    if previous is not None:
        return {"ran": False, "reason": "this candidate's pack has already been built",
                "ready_for_owner_approval": previous.get("ready_for_owner_approval"),
                "awaiting": "owner approval"}

    env = dict(os.environ)
    # `reference_pack.build` keeps the frames it must not lose in the artifact store before
    # it returns -- that is what the 2026-09-22 404s bought -- so the working directory is
    # only needed for the build itself. It was `tempfile.mkdtemp`, and this handler renders
    # eight images a run.
    with workspace.work_dir(ctx.job.inputs.get("work_dir"),
                            prefix="reference-pack-") as work:
        package = reference_pack.build(ctx.db, env=env, work_dir=work)
    package["candidate_fingerprint"] = _candidate_fingerprint()
    ctx.audit(reference_pack.PACK_ACTION, detail=package)

    if not package.get("built"):
        return {"ran": True, "built": False, "stage": package.get("stage"),
                "why": package.get("why")}

    _refresh_canonical_model_action(ctx.db, package)

    return {"ran": True, "built": True,
            "face_floor": package["face_floor"],
            "morphology_floor": package["morphology_floor"],
            "required_morphology_ok": package["required_morphology_ok"],
            "ready_for_owner_approval": package["ready_for_owner_approval"],
            "spent_cad": package["spent_cad"], "frozen": False}


def _candidate_fingerprint() -> str:
    """Identity of the run: the brief, the pack method, and the candidate's own bytes.

    The candidate image is part of it because a different concept is a different woman, and
    an audit row from the previous candidate is exactly the row that would read as "already
    built" for the next one.
    """
    import hashlib
    import json
    from pathlib import Path

    from ..visual import brief, reference_pack

    concept = Path(brief.candidate_reference())
    digest = (hashlib.sha256(concept.read_bytes()).hexdigest()[:16]
              if concept.is_file() else "absent")
    material = json.dumps({"brief": brief.state(), "pack": reference_pack.PACK_VERSION,
                           "candidate": digest}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def pack_boot_key(now) -> str:
    """The idempotency key a deploy uses to enqueue the reference-pack build.

    Keyed on the candidate and the running commit rather than on the hour. The hour looked
    like the retry mechanism and is really a lockout: a job created under one commit holds
    that key for the rest of the hour, so the deploy that corrects the method finds the key
    spent by the run it was correcting -- which is exactly what happened here, twice, first
    with the tournament and then with this. A deploy is what re-asks the question, and the
    hourly cadence is what retries a failure; the key does not have to be both.
    """
    from ..core.build import identity

    return f"boot-pack-{_candidate_fingerprint()}-{identity().get('commit_short', 'dev')}"


def _pack_attempts(db, limit: int = 5) -> list[dict]:
    """The recent pack builds, successful or not.

    Reported because the endpoint that showed only successes could not tell "never ran"
    from "ran and could not finish" -- which is the same defect the tournament endpoint had
    and the same one `_pack_on_file`'s own comment warns about, one layer up.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import reference_pack

    out: list[dict] = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == reference_pack.PACK_ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            detail = row.detail or {}
            out.append({"at": str(row.at), "built": detail.get("built"),
                        "stage": detail.get("stage"), "why": detail.get("why"),
                        "pack_version": detail.get("pack_version"),
                        "candidate_fingerprint": detail.get("candidate_fingerprint"),
                        "spent_cad": detail.get("spent_cad")})
    return out


def _pack_on_file(db) -> dict | None:
    """A completed pack for the candidate as it now stands, if there is one."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import reference_pack

    want = _candidate_fingerprint()
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == reference_pack.PACK_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            # A build that ran and failed is a different fact from one that never ran, and
            # both are different from one that succeeded -- but only a successful build is
            # a reason not to try again.
            if detail.get("candidate_fingerprint") == want and detail.get("built"):
                return detail
    return None


def _brief_fingerprint() -> str:
    import hashlib
    import json

    from ..visual import brief, tournament

    material = json.dumps({"brief": brief.state(), "seeds": list(tournament.SEED_NOTES),
                           "presentation": tournament.PRESENTATION_VERSION},
                          sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def tournament_boot_key(now) -> str:
    """The idempotency key a deploy uses to enqueue the canonical-model tournament.

    It carries the brief fingerprint because that is what the work is keyed on. A key made
    only of the hour guards the clock instead, and the difference showed up the first time a
    corrected brief was deployed twice in one hour: the second deploy found the hour's key
    already spent, enqueued nothing, and the endpoint went on reporting that the corrected
    tournament had not run.

    Keyed on the running commit rather than the hour, for the reason `pack_boot_key` gives:
    the hour is a lockout dressed as a retry. The hourly cadence is what retries a failure.
    """
    from ..core.build import identity

    return f"boot-tourney-{_brief_fingerprint()}-{identity().get('commit_short', 'dev')}"


def _tournament_on_file(db) -> dict | None:
    """A completed tournament for the brief as it now stands, if there is one."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import tournament

    want = _brief_fingerprint()
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == tournament.TOURNAMENT_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            # Not `and detail.get("finalists")`. A tournament that ran and produced nothing
            # is a different fact from one that never ran, and reading an empty finalist
            # list as "not yet run" hid exactly that: the job completed, the audit row was
            # written, and the endpoint reported it had not happened -- so the reason it
            # produced nothing was unreachable from outside the database.
            if detail.get("brief_fingerprint") == want:
                return detail
    return None


@handlers.register("creative.photoreal_calibration")
def handle_photoreal_calibration(ctx: JobContext) -> dict:
    """Ask the photographic-realism judge about a photograph nobody generated.

    Two renders in a row were blocked on the same three checks and the second of them
    plainly had pores, freckles and fine lines in it. Either the renders are unphotographic
    or the judge cannot pass a photograph, and those need opposite fixes -- so this asks
    rather than assuming the flattering answer.

    GREEN: one vision call about a public benchmark image. It renders nothing, copies
    nothing, re-hosts nothing, and never describes what the photograph depicts.
    """
    from ..visual import photoreal

    control = photoreal.control_image(ctx.db)
    if not control:
        return {"ran": False, "reason": ("no observed benchmark listing carries an image "
                                         "URL, so there is no real photograph on file to "
                                         "calibrate against")}
    result = photoreal.calibrate(ctx.db, image_url=control)
    result["checks_version"] = photoreal.CHECKS_VERSION
    ctx.audit(photoreal.CALIBRATION_ACTION, detail=result)
    return {"ran": True, "verdict": result["verdict"], "reachable": result["reachable"],
            "failed": result["failed"], "what_it_means": result["what_it_means"]}


def photoreal_calibration(db) -> dict | None:
    """The most recent calibration of the current checks, if one has been made."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import photoreal

    with db.session() as s:
        for row in s.scalars(
                select(AuditLog).where(AuditLog.action == photoreal.CALIBRATION_ACTION)
                .order_by(desc(AuditLog.id)).limit(5)):
            detail = row.detail or {}
            if detail.get("checks_version") == photoreal.CHECKS_VERSION:
                return detail
    return None


@handlers.register("growth.preproduction")
def handle_preproduction(ctx: JobContext) -> dict:
    """#4: test concepts before engineering them, without ever implying they can be bought.

    `commerce.preproduction` had the refusals and no caller. This is the caller, daily: the
    held winners and the newest field's survivors get one concept post per channel, each
    passing `check_post` or refused by name; posting is refused while the `owned_surfaces`
    gate is closed and the refusal is recorded; interest is read only from a platform-written
    `preproduction.interest_observed` row and otherwise recorded UNMEASURED; and a concept
    whose interest a platform did report becomes a brief input the next tournament is
    generated under (`creative.ideation.preproduction_interest`), with its receipt.

    GREEN: reads rows, writes its own audit rows. Posts nothing, spends nothing, fetches
    nothing, and has no path that can write an engagement number.
    """
    from ..commerce import preproduction_cycle

    out = preproduction_cycle.run(ctx)
    ctx.audit(preproduction_cycle.CYCLE_ACTION, detail={
        k: out[k] for k in ("concepts", "prepared", "refused", "held_for_gate", "publish",
                            "interest", "unmeasured", "acted_on")})
    return {"ran": True, "concepts": out["concepts"], "prepared": len(out["prepared"]),
            "refused": len(out["refused"]), "held_for_gate": out["held_for_gate"],
            "publish": out["publish"], "unmeasured": out["unmeasured"],
            "acted_on": out["acted_on"], "brief": out["brief"]["reason"]}
