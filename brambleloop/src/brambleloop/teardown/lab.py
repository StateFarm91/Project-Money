"""The teardown laboratory's runtime: recording audits, promoting findings, QA and the manifest.

Requirements 151-164, 169 and 170, joined to the routes that write. Every library here was
built and tested; the proof-chain audit of 2026-09-27 found none of them reachable, so nothing
could ever write a `TeardownFinding`, the composite standard read a table with no writer, and
the delight question was asked of nobody. This module is the join:

- `record_audit()` -- one complete per-dimension audit (#152-#160), prefilled from the intake
  manifest, recorded as scorecard findings, each finding promoted into the Improvement
  Department (#164), and the delight question asked of the benchmark it describes (#169).
- `record_finding()` -- one twelve-dimension scorecard finding (#161), promoted likewise.
- `product_qa()` -- Brambleloop's own product through #163 and #169: the advantages are read
  from the product's release certificate rather than claimed, and the delight answer comes
  from audits of our own product recorded under `brambleloop:<slug>`.
- `write_manifest()` -- BENCHMARK_MANIFEST.md (#170), written into the quarantined library
  (outside the repository) on every intake.

Nothing here opens a benchmark file. Purchased content never enters a row: every free-text
field still passes `check_derived()` in the constructors this module calls.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from . import audits, library, pipeline, scorecard

ACTION_AUDIT = "teardown.audit_recorded"
ACTION_FINDING = "teardown.finding_recorded"
ACTION_PROMOTION = "teardown.finding_promoted"
ACTION_QA = "teardown.product_qa"
ACTION_MANIFEST = "teardown.manifest_written"

MANIFEST_NAME = "BENCHMARK_MANIFEST.md"
SELF_PREFIX = scorecard.SELF_PREFIX


class LabRefused(Exception):
    """A recording against something that is neither a purchased benchmark nor our product."""


def _audit(db, action: str, detail: dict, artifact: str = "") -> None:
    from ..agents.registry import Registry

    Registry(db).audit("orchestrator", action, artifact=artifact or None, detail=detail)


# ---------------------------------------------------------------------------
# What the manifest settles about one benchmark


def inferred_for(db, benchmark_ref: str) -> dict | None:
    """The filename inferences for a purchased benchmark, or None for our own product.

    Recomputed from the manifest row's file roles rather than stored, so a re-upload that
    changes the files changes the answer.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct, Product

    if benchmark_ref.startswith(SELF_PREFIX):
        slug = benchmark_ref[len(SELF_PREFIX):]
        with db.session() as s:
            if s.scalar(select(Product).where(Product.slug == slug)) is None:
                raise LabRefused(f"{slug!r} is not a Brambleloop product")
        return None
    with db.session() as s:
        row = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.ref == benchmark_ref))
        if row is None:
            raise LabRefused(
                f"{benchmark_ref!r} is not a purchased benchmark in the manifest. A teardown "
                f"of something nobody bought is an opinion about crochet in general")
        return library.inferred_from_files(list(row.files or []))


# ---------------------------------------------------------------------------
# #164: every new finding goes into the Improvement Department


def promote_finding(db, finding_id: int) -> dict:
    """Promote one finding, recording a refusal on the finding rather than losing it.

    The surfaces come from `pipeline.TOUCHES_FOR_DIMENSION` and the rollback reference names
    the finding, so governance sees exactly what the change would touch before any work.
    A refusal -- a finding whose implied change would weaken a protected gate -- is kept on
    the finding with its reason: that is a finding about the competitor, not a hypothesis.
    """
    from ..core.models import TeardownFinding
    from ..improve import cells, governance

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        if row is None:
            raise LabRefused(f"no teardown finding {finding_id}")
        dimension = row.dimension
    touches = pipeline.TOUCHES_FOR_DIMENSION[dimension]
    try:
        got = pipeline.promote(db, finding_id, touches=touches,
                               rollback_ref=f"teardown-finding:{finding_id}")
    except (pipeline.PipelineRefused, governance.GovernanceRefused,
            cells.ImprovementRefused) as exc:
        with db.session() as s:
            row = s.get(TeardownFinding, finding_id)
            row.detail = {**(row.detail or {}), "promotion_refused": str(exc)[:500]}
        _audit(db, ACTION_PROMOTION, {"finding": finding_id, "promoted": False,
                                      "reason": str(exc)[:300]})
        return {"finding": finding_id, "promoted": False, "reason": str(exc)[:300]}
    _audit(db, ACTION_PROMOTION, {"finding": finding_id, "promoted": True,
                                  "improvement": got["improvement"], "cell": got["cell"]})
    return {**got, "promoted": True}


# ---------------------------------------------------------------------------
# #152-#161: recording


def record_audit(db, benchmark_ref: str, spec_key: str, answers: dict) -> dict:
    """One complete audit, recorded, promoted, and asked the delight question."""
    inferred = inferred_for(db, benchmark_ref)
    audit = audits.observe(spec_key, benchmark_ref, answers, inferred=inferred)
    recorded = audits.record(db, audit)
    promotions = [promote_finding(db, fid) for fid in recorded["findings_recorded"]]
    delight = delight_for(db, benchmark_ref)
    _set_state_after_audit(db, benchmark_ref)
    _audit(db, ACTION_AUDIT, {"benchmark": benchmark_ref, "audit": spec_key,
                              "findings": recorded["findings_recorded"],
                              "promoted": sum(1 for p in promotions if p["promoted"]),
                              "delight": delight}, artifact=benchmark_ref)
    return {**recorded, "promotions": promotions, "delight": delight}


def record_finding(db, benchmark_ref: str, dimension: str, score: int, mechanism: str,
                   improvement: str) -> dict:
    """One scorecard finding (#161), recorded and promoted (#164)."""
    inferred_for(db, benchmark_ref)
    f = scorecard.finding(benchmark_ref, dimension, int(score), mechanism, improvement)
    finding_id = scorecard.record(db, f)
    promotion = promote_finding(db, finding_id)
    delight = delight_for(db, benchmark_ref)
    _audit(db, ACTION_FINDING, {"benchmark": benchmark_ref, "finding": finding_id,
                                "dimension": dimension, "promoted": promotion["promoted"],
                                "delight": delight}, artifact=benchmark_ref)
    return {"finding": finding_id, "promotion": promotion, "delight": delight,
            "scorecard": scorecard.scorecard(db, benchmark_ref)}


def _set_state_after_audit(db, benchmark_ref: str) -> None:
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct

    if benchmark_ref.startswith(SELF_PREFIX):
        return
    coverage = audits.coverage(db)
    outstanding = [o for o in coverage.get("outstanding") or []
                   if o["benchmark"] == benchmark_ref]
    with db.session() as s:
        row = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.ref == benchmark_ref))
        if row is not None:
            row.teardown_state = "audited" if not outstanding else "in_teardown"


# ---------------------------------------------------------------------------
# #169: the delight question, of a benchmark or of our own product


def delight_for(db, ref: str, *, measured: dict | None = None) -> dict:
    """'After paying, does this feel better than expected?' from the recorded scorecard.

    For our own product, `measured` carries the scores read from its own artefacts
    (`measured_self_scores`); a recorded audit of the product overrides a measured score on
    the same driver, because a person who used the pattern saw more than its files show."""
    card = scorecard.scorecard(db, ref)
    scores = {k: v["score"] for k, v in (measured or {}).items()}
    scores.update({d: v["score"] for d, v in card["scores"].items()})
    return {"ref": ref, **scorecard.delight_question(scores),
            "measured_from_artefacts": sorted((measured or {}).keys())}


# C-69 (#169): our own product's delight mechanisms, measured from what the chain produced
# rather than waiting for somebody to POST an audit. Each score is on the teardown scale and
# says what it read; a mechanism with nothing to read is left unscored, never neutral.
DELIGHT_CELL: dict[str, str] = {
    "instruction_clarity": "pattern_engineering", "chart_quality": "pattern_engineering",
    "beginner_support": "customer_experience", "premium_presentation": "creative_assets",
    "delivery_packaging": "pattern_engineering", "support_experience": "customer_experience",
    "bonus_utility": "product_creativity", "navigation": "pattern_engineering",
    "customization": "product_creativity", "confidence": "quality",
}


def measured_self_scores(db, slug: str) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import (ArtefactProvenance, AuditLog, Job, JobStatus, PatternVersion,
                               Product)

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id)
                      .order_by(desc(PatternVersion.id))) if product is not None else None
        if pv is None:
            return {}
        cert = dict(pv.certificate or {})
        built = next((dict(j.outputs or {}) for j in s.scalars(
            select(Job).where(Job.job_type == "assets.build", Job.status == JobStatus.DONE)
            .order_by(desc(Job.id))) if (j.outputs or {}).get("slug") == slug
            and (j.outputs or {}).get("version") == pv.version), None)
        problems = s.scalar(select(AuditLog).where(
            AuditLog.action == "assets.deliverable_problems",
            AuditLog.artifact == f"{slug}@{pv.version}").limit(1)) is not None
        prov = [(r.artefact_class, r.validation_status) for r in s.scalars(
            select(ArtefactProvenance).where(ArtefactProvenance.product_slug == slug))]
    stages = set(cert.get("stages_run") or [])
    out: dict[str, dict] = {}

    def put(key, score, why):
        out[key] = {"score": score, "evidence": why}

    if built:
        terms = len(built.get("pdf_sha256_by_terminology") or {}) or 1
        put("instruction_clarity", 2 if problems else (4 if "reverse" in stages else 3),
            "deliverable problems recorded" if problems else
            "PDF built with no deliverable problems; the written text reverse-compiles")
        put("chart_quality", 4 if built.get("chart_sha256") and built.get("legend_sha256")
            else 3, "chart and legend rendered from the certified design")
        put("navigation", 4 if built.get("pages") and built.get("legend_sha256") else 3,
            f"{built.get('pages')} page(s) with a stitch key and legend")
        put("delivery_packaging", 4 if terms >= 2 else 3,
            f"{terms} terminology edition(s) of the PDF")
        put("bonus_utility", 4 if terms >= 2 and built.get("legend_sha256") else 3,
            "US and UK editions plus a separate chart legend" if terms >= 2 else
            "one edition")
    visual = [v for c, v in prov if c == "visual_truth"]
    if visual:
        put("premium_presentation", 2 if any(v == "blocked" for v in visual) else 4,
            f"{len(visual)} listing frame(s) through asset truth")
    support = [v for c, v in prov if c == "support_knowledge"]
    if support:
        good = all(v == "passed" for v in support)
        put("support_experience", 4 if good else 1,
            "a version-keyed FAQ consistent with the PDF and the listing" if good else
            "the FAQ diverges from the PDF or listing")
        put("beginner_support", 4 if good else 2, "the FAQ states stitches, yardage and "
            "difficulty for this release")
    sizes = len((pv.cir_json or {}).get("sizes") or [])
    put("customization", 4 if sizes > 1 else 3,
        f"{sizes} graded sizes" if sizes > 1 else "one size, as the listing states")
    put("confidence", 5 if cert.get("physical_test_passed") else
        (3 if cert.get("granted") else 1),
        "a physical sample passed" if cert.get("physical_test_passed") else
        "deterministically certified; no physical sample yet")
    return out


def _act_on_delight(db, slug: str, delight: dict) -> dict | None:
    """The weakest driver below 'strong' becomes an improvement hypothesis, once."""
    from sqlalchemy import select

    from ..core.models import Improvement
    from ..improve import cells

    if not delight.get("answerable"):
        return None
    weakest = delight.get("weakest")
    score = (delight.get("drivers") or {}).get(weakest)
    if weakest is None or score is None or score >= 4:
        return None
    ref = f"delight:{slug}:{weakest}"
    with db.session() as s:
        if s.scalar(select(Improvement).where(Improvement.baseline_ref == ref,
                                              Improvement.state.in_(("proposed",
                                                                     "testing")))):
            return {"improvement": None, "already_open": ref}
    try:
        iid = cells.propose(
            db, cell=DELIGHT_CELL.get(weakest, "quality"),
            hypothesis=(f"Raising {weakest} on {slug} from {score} to at least 4 would make "
                        f"the product feel better than expected after purchase (#169)"),
            expected_effect=f"{weakest} scores 4 or more on the next measured QA",
            rollback_ref=f"teardown-product-qa:{slug}", proposed_by="teardown_lab")
    except Exception as exc:  # noqa: BLE001 - a refused hypothesis is recorded, not raised
        return {"improvement": None, "refused": str(exc)[:200]}
    with db.session() as s:
        row = s.get(Improvement, iid)
        row.baseline_ref = ref
        row.baseline_value = float(score)
    return {"improvement": iid, "ref": ref}


# ---------------------------------------------------------------------------
# #163 and #169 in Brambleloop's own QA


def advantages_from_certificate(certificate: dict | None) -> list[str]:
    """The advantages a release certificate evidences, and only those.

    Read from what the chain actually ran. An advantage the certificate cannot show -- a
    colour-independent chart, version-aware support -- is not claimed here, because an
    advantage is something already built *and checkable for this product*.
    """
    cert = certificate or {}
    if not cert.get("granted"):
        return []
    stages = set(cert.get("stages_run") or [])
    errors = [f for f in cert.get("findings") or [] if f.get("severity") == "error"]
    out = []
    if {"compile", "specification"} <= stages and not errors:
        out.append("deterministic_validation")
    if "reverse" in stages and not any(str(f.get("code", "")).startswith("reverse")
                                       for f in errors):
        out.append("reverse_compilation")
    if "geometry" in stages:
        out.append("size_refusal")
    if cert.get("physical_test_passed"):
        out.append("measured_yardage")
    return out


# C-69 (#163): an advantage is "beyond what purchased competitors provide" only when the
# purchased benchmarks do not already provide it. Each advantage is observable on one of the
# twelve teardown dimensions; a benchmark scored at the top of the scale there (5, "the best
# example in the library") already provides it, and the advantage is parity, not a position.
ADVANTAGE_DIMENSION: dict[str, str] = {
    "deterministic_validation": "pattern_correctness_evidence",
    "reverse_compilation": "pattern_correctness_evidence",
    "size_refusal": "listing_promise_alignment",
    "measured_yardage": "materials_clarity",
    "colour_independent_charts": "chart_quality",
    "version_aware_support": "support_experience",
}
MATCHED_AT = 5


def _class_composite(db, product_class: str) -> dict:
    """The composite over this product class's purchased benchmarks, else over all of them."""
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct, TeardownFinding

    with db.session() as s:
        in_class = {b.ref for b in s.scalars(select(BenchmarkProduct))
                    if product_class and product_class in (b.category, b.pod)}
        rows = [(r.benchmark_ref, r.dimension, r.score) for r in s.scalars(
            select(TeardownFinding)) if not r.benchmark_ref.startswith(SELF_PREFIX)]
    scope = "class" if any(ref in in_class for ref, _d, _s in rows) else "all"
    best: dict[str, tuple[float, str]] = {}
    for ref, dim, score in rows:
        if scope == "class" and ref not in in_class:
            continue
        if score > best.get(dim, (-1.0, ""))[0]:
            best[dim] = (score, ref)
    return {"scope": scope, "best": best}


def compare_advantages(db, advantages: list[str], product_class: str) -> dict:
    """Each evidenced advantage against the purchased benchmarks: beyond, matched or unmeasured."""
    composite = _class_composite(db, product_class)
    verdicts = {}
    for adv in advantages:
        dim = ADVANTAGE_DIMENSION.get(adv)
        top = composite["best"].get(dim)
        if top is None:
            verdicts[adv] = {"dimension": dim, "state": "unmeasured",
                             "why": f"no purchased benchmark has been scored on {dim}"}
        elif top[0] >= MATCHED_AT:
            verdicts[adv] = {"dimension": dim, "state": "matched", "by": top[1],
                             "benchmark_score": top[0],
                             "why": f"{top[1]} already scores {top[0]} on {dim}"}
        else:
            verdicts[adv] = {"dimension": dim, "state": "beyond", "benchmark_best": top[0],
                             "by": top[1],
                             "why": f"the best purchased benchmark scores {top[0]} on {dim}"}
    beyond = sorted(a for a, v in verdicts.items() if v["state"] == "beyond")
    measured = [a for a, v in verdicts.items() if v["state"] != "unmeasured"]
    return {"scope": composite["scope"], "verdicts": verdicts, "beyond": beyond,
            "measured": bool(measured),
            "parity_only": bool(measured) and not beyond
            and all(v["state"] != "unmeasured" for v in verdicts.values())}


def _evidenced_beyond_certificate(db, slug: str) -> list[str]:
    """Advantages a product's own recorded artefacts evidence (not its certificate)."""
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    with db.session() as s:
        classes = {(r.artefact_class, r.validation_status) for r in s.scalars(
            select(ArtefactProvenance).where(ArtefactProvenance.product_slug == slug))}
    out = []
    if any(c == "support_knowledge" and v in ("passed",) for c, v in classes):
        # a version-keyed FAQ built from this release, consistent with PDF and listing
        out.append("version_aware_support")
    return out


def product_qa(db, slug: str, *, product_class: str = "") -> dict:
    """Brambleloop's own product through the parity check (#163) and the delight question.

    Returns `blocks_release` when the product class can name no evidenced advantage beyond
    the purchased benchmarks. The delight answer is `answerable: false` until an audit of
    this product has been recorded under `brambleloop:<slug>` -- unscored is unanswerable,
    never neutral. Writes one audit row either way.
    """
    from sqlalchemy import desc, select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            raise LabRefused(f"{slug!r} is not a Brambleloop product")
        version = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.certified == True)  # noqa: E712
            .order_by(desc(PatternVersion.id)))
        certificate = dict(version.certificate or {}) if version is not None else None
        category = (product_class
                    or str(((version.cir_json or {}) if version is not None else {})
                           .get("category") or "") or slug)
        version_label = version.version if version is not None else None

    advantages = advantages_from_certificate(certificate)
    advantages += [a for a in _evidenced_beyond_certificate(db, slug) if a not in advantages]
    try:
        unique = scorecard.check_unique_value(category, advantages)
        parity = {"refused": False, **unique}
    except scorecard.ParityRefused as exc:
        parity = {"refused": True, "product_class": category, "reason": str(exc)}
    # #163 is "beyond what purchased competitors provide", which is a comparison: every
    # evidenced advantage against the purchased benchmarks' composite. Advantages the
    # benchmarks all match are parity; with no benchmark scored on those dimensions the
    # comparison is UNMEASURED (the purchases are the owner's), recorded and not blocking.
    comparison = compare_advantages(db, advantages, category)
    parity["comparison"] = comparison
    if not parity["refused"] and comparison["parity_only"]:
        parity = {**parity, "refused": True,
                  "reason": (f"{category!r}: every advantage this release evidences is "
                             f"already provided by a purchased benchmark "
                             f"({ {a: v.get('by') for a, v in comparison['verdicts'].items()} }). "
                             f"Parity with the composite is a floor, not a position (#163)")}
    parity["status"] = ("refused" if parity["refused"] else
                        "beyond" if comparison["beyond"] else "UNMEASURED")
    delight = delight_for(db, f"{SELF_PREFIX}{slug}", measured=measured_self_scores(db, slug))
    acted = _act_on_delight(db, slug, delight)
    result = {
        "delight_action": acted,
        "product": slug, "version": version_label, "product_class": category,
        "certificate_seen": certificate is not None,
        "unique_value": parity, "delight": delight,
        "blocks_release": parity["refused"],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _audit(db, ACTION_QA, result, artifact=slug)
    return result


def product_qa_all(db) -> dict:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        slugs = sorted({p.slug for p, v in s.execute(
            select(Product, PatternVersion).where(PatternVersion.product_id == Product.id,
                                                  PatternVersion.certified == True))})  # noqa: E712
    results = [product_qa(db, slug) for slug in slugs]
    return {"products": len(results), "blocked": [r["product"] for r in results
                                                  if r["blocks_release"]],
            "results": results}


# ---------------------------------------------------------------------------
# #170: BENCHMARK_MANIFEST.md


def write_manifest(db, *, env: dict[str, str] | None = None) -> dict:
    """Generate BENCHMARK_MANIFEST.md into the quarantined library, never the repository."""
    text = library.manifest_markdown(db)
    root = library.library_root(env)
    root.mkdir(parents=True, exist_ok=True)
    path = root / MANIFEST_NAME
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    result = {"path": str(path), "bytes": len(text.encode()), "sha256": digest,
              "teardown_queue": len((audits.coverage(db).get("outstanding") or []))}
    _audit(db, ACTION_MANIFEST, result)
    return {**result, "markdown": text}
