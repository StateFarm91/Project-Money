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


def delight_for(db, ref: str) -> dict:
    """'After paying, does this feel better than expected?' from the recorded scorecard."""
    card = scorecard.scorecard(db, ref)
    scores = {d: v["score"] for d, v in card["scores"].items()}
    return {"ref": ref, **scorecard.delight_question(scores)}


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
    try:
        unique = scorecard.check_unique_value(category, advantages)
        parity = {"refused": False, **unique}
    except scorecard.ParityRefused as exc:
        parity = {"refused": True, "product_class": category, "reason": str(exc)}
    delight = delight_for(db, f"{SELF_PREFIX}{slug}")
    result = {
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
