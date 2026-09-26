"""Lineage for the artefacts that already exist, derived only from evidence already on file.

The write path (`ops.artefacts.record_lineage`, called from every release-chain handler)
records a derived artefact as it is made. This is for the ones made before it did. The
2026-09-26 audit of production found 275 derived artefacts and 275 without a provenance row --
marketing_asset 134, visual_truth 94, listing_copy 16, seo 16, certificate 15 -- and that was
a lower bound, because the PDFs and charts in every `assets.build` job's outputs and the
price on every listing were not being counted at all.

The rule that shapes every function here: **a backfilled row must cite the evidence it was
derived from, and where none exists the artefact stays unproven.** It would be easy to write
275 rows tonight by reading each artefact's current slug and the current design and calling
the estate instrumented. That is not lineage, it is a claim of lineage, and it would make the
sentinel's `unproven` count -- the one honest number about this backlog -- read zero for a
reason that has nothing to do with anything being proved. So each class has a matching rule,
each rule names the record it matched on, and a miss is counted by reason rather than filled.

- certificate: only when the certificate stored on the release names the release's own hash,
  and a `gate.certified` audit row names the release.
- listing_copy / seo / pricing: from the listing's own recorded `release_hash` and
  `chain_version`, and a `listing.seo_drafted` audit row naming it. A listing built under a
  superseded chain version reads STALE afterwards, which is the honest reading; a collection
  listing derives from its members and stays unproven here.
- visual_truth: only when the frame's sha256 appears among the frames in a completed
  `assets.build` job's outputs.
- pdf / chart: from the hashes in a completed `assets.build` job's outputs.
- marketing_asset: only when the content piece was created inside the window of a completed
  `marketing.schedule` job for its slug.

Cost, model and provider come from the cost entries the matched job wrote, or stay NULL and
empty. `code_commit` is `unknown` on every row this module writes, because the commit that
built the artefact was never recorded, and `source` is `backfilled` so the two kinds of row
can never be mistaken for each other.
"""
from __future__ import annotations

import hashlib
import re
from datetime import timezone

from ..core.build import UNKNOWN as UNKNOWN_COMMIT
from . import artefacts as P

# The audit actions read as evidence. Held as data rather than as literals beside the column
# so the reads are visible in one place; `ops.retention` should list them as `latest` reads.
EVIDENCE_ACTIONS: dict[str, str] = {
    "certificate": "gate.certified",
    "listing": "listing.seo_drafted",
}

# The chain version rides every post-certification idempotency key as its last part
# ("assets:slug:1.0.0:abcdef123456:c7"), which is the only record of which chain built a job.
_CHAIN_IN_KEY = re.compile(r":c(\d+)$")

_UNPROVEN = {
    "collection": "a collection listing derives from its members, not from one release; it "
                  "is recorded by the write path from now on and stays unproven for the past",
    "no_release_hash": "the listing carries no release_hash, so nothing says which certified "
                       "release it was built from",
    "no_stored_release": "no stored release exists for this slug and version",
    "certificate_hash_mismatch": "the stored certificate does not name the release's own hash",
    "no_audit_row": "no audit row names this artefact, so the job that made it is unknown",
    "no_sha256": "the frame carries no sha256 to match against any build output",
    "no_build_output": "no completed assets.build job's outputs carry this hash",
    "outside_job_window": "created outside every completed marketing.schedule job window for "
                          "its slug, so no job can be shown to have written it",
}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _chain_from_key(key: str | None) -> str | None:
    match = _CHAIN_IN_KEY.search(key or "")
    return match.group(1) if match else None


def _content_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


class _Report:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.backfilled: dict[str, int] = {}
        self.left_unproven: dict[str, int] = {}
        self.why: dict[str, dict[str, int]] = {}
        self.rows: list[dict] = []
        self.skipped_existing = 0

    def unproven(self, cls: str, key: str, reason: str) -> None:
        self.left_unproven[cls] = self.left_unproven.get(cls, 0) + 1
        bucket = self.why.setdefault(cls, {})
        bucket[reason] = bucket.get(reason, 0) + 1

    def done(self, cls: str, key: str, evidence: dict) -> None:
        self.backfilled[cls] = self.backfilled.get(cls, 0) + 1
        if len(self.rows) < 500:
            self.rows.append({"artefact_class": cls, "artefact_key": key,
                              "evidence": evidence})

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "backfilled": dict(sorted(self.backfilled.items())),
            "left_unproven": dict(sorted(self.left_unproven.items())),
            "why": {cls: dict(sorted(v.items())) for cls, v in sorted(self.why.items())},
            "skipped_existing": self.skipped_existing,
            "rows": self.rows,
            "code_commit": UNKNOWN_COMMIT,
            "source": "backfilled",
            "note": ("every row cites the job, audit row or output hash it was derived from; "
                     "an artefact nothing on file accounts for stays unproven and is counted "
                     "by reason rather than filled. code_commit is unknown on every row "
                     "because the commit that built the artefact was never recorded"),
        }


def _cost(db, job_id: int | None) -> tuple[float | None, str, str]:
    """What the matched job's cost entries say, or nothing."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    if job_id is None:
        return None, "", ""
    entries = list(db.scalars(select(CostEntry).where(CostEntry.job_id == job_id)))
    if not entries:
        return None, "", ""
    total = float(sum(e.amount_cad or 0.0 for e in entries))
    model = next((e.model for e in entries if e.model), "")
    provider = next((e.provider for e in entries if e.provider), "")
    return total, model, provider


def _lineage(db, *, created_by: str, job_id: int | None, audit_id: int | None,
             matched_on: str, phase: str = "shadow", sha256: str = "",
             parents=(), validation_status: str = "unknown", **extra) -> P.Lineage:
    cost, model, provider = _cost(db, job_id)
    evidence = {"job_id": job_id, "audit_id": audit_id, "matched_on": matched_on}
    evidence.update(extra)
    return P.Lineage(created_by=created_by or "unknown", job_id=job_id,
                     code_commit=UNKNOWN_COMMIT, model=model, provider=provider,
                     cost_cad=cost, sha256=sha256, parents=tuple(parents),
                     validation_status=validation_status,
                     publication_authority=phase or "shadow", source="backfilled",
                     evidence=evidence)


def _latest_audit(db, action: str, artifact: str):
    from sqlalchemy import select

    from ..core.models import AuditLog

    return db.scalar(select(AuditLog).where(AuditLog.action == action,
                                            AuditLog.artifact == artifact)
                     .order_by(AuditLog.id.desc()).limit(1))


def _releases(db) -> dict[tuple[str, str], object]:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    slugs = {p.id: p.slug for p in db.scalars(select(Product))}
    return {(slugs.get(pv.product_id, ""), pv.version): pv
            for pv in db.scalars(select(PatternVersion))}


def _done_jobs(db, job_type: str) -> list:
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    return list(db.scalars(select(Job).where(Job.job_type == job_type,
                                             Job.status == JobStatus.DONE)
                           .order_by(Job.id.asc())))


def run(db, *, dry_run: bool = False) -> dict:
    """Backfill every derivable row, once, and account for every one that is not."""
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance, ContentPiece, Listing, ListingAsset

    report = _Report(dry_run)
    have = {(r.artefact_class, r.artefact_key)
            for r in db.scalars(select(ArtefactProvenance))}
    releases = _releases(db)

    def write(cls: str, key: str, slug: str, inputs: dict, lineage: P.Lineage,
              chain_version: str = "") -> None:
        if (cls, key) in have:
            report.skipped_existing += 1
            return
        if not dry_run:
            P.record_lineage(db, artefact_class=cls, artefact_key=key, product_slug=slug,
                             inputs=inputs, lineage=lineage, chain_version=chain_version)
        have.add((cls, key))
        report.done(cls, key, lineage.evidence)

    def release_inputs(slug: str, version: str, *, release: str | None,
                       chain: str | None) -> dict | None:
        pv = releases.get((slug, version))
        if pv is None:
            return None
        inputs = {f"cir:{slug}": P.fingerprint(pv.cir_json)}
        release = release or pv.release_hash
        if release:
            inputs[f"release:{slug}"] = release[:16]
        if chain:
            inputs["chain:release"] = P.chain_fingerprint(chain)
        return inputs

    # --- certificates -----------------------------------------------------------------
    for (slug, version), pv in releases.items():
        if not pv.certified:
            continue
        key = P.release_key(slug, version)
        if ("certificate", key) in have:
            report.skipped_existing += 1
            continue
        cert = pv.certificate or {}
        if not pv.release_hash or cert.get("release_hash") != pv.release_hash:
            report.unproven("certificate", key, _UNPROVEN["certificate_hash_mismatch"])
            continue
        audit = _latest_audit(db, EVIDENCE_ACTIONS["certificate"], key)
        if audit is None:
            report.unproven("certificate", key, _UNPROVEN["no_audit_row"])
            continue
        inputs = {f"cir:{slug}": P.fingerprint(pv.cir_json),
                  f"release:{slug}": pv.release_hash[:16]}
        write("certificate", key, slug, inputs, _lineage(
            db, created_by=audit.actor, job_id=audit.job_id, audit_id=audit.id,
            matched_on="PatternVersion.certificate.release_hash == PatternVersion."
                       "release_hash; AuditLog gate.certified artifact == slug@version",
            phase=audit.phase.value if audit.phase else "shadow",
            sha256=pv.release_hash if len(pv.release_hash) == 64 else "",
            validation_status="certified"),
            chain_version=str(cert.get("doc_version") or ""))

    # --- listings: copy, seo, pricing --------------------------------------------------
    for listing in db.scalars(select(Listing)):
        slug, version = listing.product_slug, listing.version
        key = P.release_key(slug, version)
        classes = ["listing_copy", "seo"] + (["pricing"] if (listing.price_cad or 0) > 0
                                             else [])
        missing = [c for c in classes if (c, key) not in have]
        report.skipped_existing += len(classes) - len(missing)
        if not missing:
            continue
        if version == "collection":
            reason = _UNPROVEN["collection"]
        elif not listing.release_hash:
            reason = _UNPROVEN["no_release_hash"]
        elif (slug, version) not in releases:
            reason = _UNPROVEN["no_stored_release"]
        else:
            reason = None
        audit = (_latest_audit(db, EVIDENCE_ACTIONS["listing"], key)
                 if reason is None else None)
        if reason is None and audit is None:
            reason = _UNPROVEN["no_audit_row"]
        if reason is not None:
            for cls in missing:
                report.unproven(cls, key, reason)
            continue
        inputs = release_inputs(slug, version, release=listing.release_hash,
                                chain=listing.chain_version or None)
        common = dict(created_by=audit.actor, job_id=audit.job_id, audit_id=audit.id,
                      matched_on="Listing.release_hash and Listing.chain_version; AuditLog "
                                 "listing.seo_drafted artifact == slug@version",
                      phase=audit.phase.value if audit.phase else "shadow",
                      validation_status="passed")
        certificate_ref = f"certificate:{key}"
        for cls in missing:
            if cls == "listing_copy":
                lineage = _lineage(db, sha256=_content_hash(listing.title, listing.description),
                                   parents=(certificate_ref,), **common)
            elif cls == "seo":
                lineage = _lineage(db, sha256=_content_hash(listing.title,
                                                            *sorted(listing.tags or [])),
                                   parents=(f"listing_copy:{key}",), **common)
            else:
                lineage = _lineage(db, parents=(certificate_ref,), **common)
            write(cls, key, slug, inputs, lineage, chain_version=listing.chain_version or "")

    # --- assets.build outputs: pdf, chart, and the frame index for visual_truth ---------
    builds = _done_jobs(db, "assets.build")
    frame_index: dict[tuple[str, str, str], object] = {}
    latest_output: dict[tuple[str, str], tuple[object, str, str]] = {}
    for job in builds:
        outputs = job.outputs or {}
        slug, version = outputs.get("slug"), outputs.get("version")
        if not slug or not version:
            continue
        for frame in outputs.get("frames") or []:
            if frame.get("sha256"):
                frame_index[(slug, version, frame["sha256"])] = job
        by_terminology = (outputs.get("pdf_sha256_by_terminology")
                          or ({"US": outputs["pdf_sha256"]} if outputs.get("pdf_sha256")
                              else {}))
        for terminology, sha in by_terminology.items():
            if sha:
                latest_output[("pdf", P.pdf_key(slug, version, terminology))] = (
                    job, sha, f"Job.outputs.pdf_sha256_by_terminology[{terminology}]")
        for which in ("chart", "legend"):
            if outputs.get(f"{which}_sha256"):
                latest_output[("chart", P.chart_key(slug, version, which))] = (
                    job, outputs[f"{which}_sha256"], f"Job.outputs.{which}_sha256")

    for (cls, key), (job, sha, matched_on) in latest_output.items():
        if (cls, key) in have:
            report.skipped_existing += 1
            continue
        slug, version = job.outputs["slug"], job.outputs["version"]
        inputs = release_inputs(slug, version, release=(job.inputs or {}).get("release"),
                                chain=_chain_from_key(job.idempotency_key))
        if inputs is None:
            report.unproven(cls, key, _UNPROVEN["no_stored_release"])
            continue
        write(cls, key, slug, inputs, _lineage(
            db, created_by=job.agent, job_id=job.id, audit_id=None, matched_on=matched_on,
            sha256=sha, parents=(f"certificate:{P.release_key(slug, version)}",),
            validation_status="passed"),
            chain_version=_chain_from_key(job.idempotency_key) or "")

    # --- visual_truth ----------------------------------------------------------------
    for asset in db.scalars(select(ListingAsset)):
        slug, version = asset.product_slug, asset.version
        key = P.visual_key(slug, version, asset.id)
        if ("visual_truth", key) in have:
            report.skipped_existing += 1
            continue
        if not asset.sha256:
            report.unproven("visual_truth", key, _UNPROVEN["no_sha256"])
            continue
        job = frame_index.get((slug, version, asset.sha256))
        if job is None:
            report.unproven("visual_truth", key, _UNPROVEN["no_build_output"])
            continue
        inputs = release_inputs(slug, version, release=(job.inputs or {}).get("release"),
                                chain=_chain_from_key(job.idempotency_key))
        if inputs is None:
            report.unproven("visual_truth", key, _UNPROVEN["no_stored_release"])
            continue
        write("visual_truth", key, slug, inputs, _lineage(
            db, created_by=job.agent, job_id=job.id, audit_id=None,
            matched_on="ListingAsset.sha256 == Job(assets.build).outputs.frames[].sha256",
            sha256=asset.sha256, parents=(f"certificate:{P.release_key(slug, version)}",),
            validation_status="passed" if asset.approved else "blocked"),
            chain_version=_chain_from_key(job.idempotency_key) or "")

    # --- marketing_asset -------------------------------------------------------------
    windows: dict[str, list] = {}
    for job in _done_jobs(db, "marketing.schedule"):
        slug = (job.inputs or {}).get("slug")
        if slug and job.started_at and job.finished_at:
            windows.setdefault(slug, []).append(job)
    for piece in db.scalars(select(ContentPiece)):
        slug = piece.product_slug
        key = P.marketing_key(slug, piece.channel, piece.title)
        if ("marketing_asset", key) in have:
            report.skipped_existing += 1
            continue
        created = _aware(piece.created_at)
        job = next((j for j in windows.get(slug, [])
                    if created is not None
                    and _aware(j.started_at) <= created <= _aware(j.finished_at)), None)
        if job is None:
            report.unproven("marketing_asset", key, _UNPROVEN["outside_job_window"])
            continue
        version = (job.inputs or {}).get("version", "")
        inputs = release_inputs(slug, version, release=(job.inputs or {}).get("release"),
                                chain=_chain_from_key(job.idempotency_key))
        if inputs is None:
            report.unproven("marketing_asset", key, _UNPROVEN["no_stored_release"])
            continue
        write("marketing_asset", key, slug, inputs, _lineage(
            db, created_by=job.agent, job_id=job.id, audit_id=None,
            matched_on="ContentPiece.created_at within Job(marketing.schedule).started_at.."
                       "finished_at and Job.inputs.slug == ContentPiece.product_slug",
            sha256=_content_hash(piece.title, piece.body),
            parents=(f"listing_copy:{P.release_key(slug, version)}",),
            validation_status="passed"),
            chain_version=_chain_from_key(job.idempotency_key) or "")

    if not dry_run:
        db.flush()
    return report.to_dict()


def state() -> dict:
    return {
        "rules": {
            "certificate": "PatternVersion.certificate.release_hash == release_hash, and a "
                           "gate.certified audit row names the release",
            "listing_copy/seo/pricing": "Listing.release_hash + chain_version, and a "
                                        "listing.seo_drafted audit row names the listing; "
                                        "a superseded chain version reads STALE; a "
                                        "collection stays unproven",
            "visual_truth": "ListingAsset.sha256 appears in a completed assets.build "
                            "job's output frames",
            "pdf/chart": "hashes in a completed assets.build job's outputs",
            "marketing_asset": "ContentPiece.created_at inside a completed "
                               "marketing.schedule job window for its slug",
        },
        "evidence_actions": dict(EVIDENCE_ACTIONS),
        "left_unproven_when": dict(_UNPROVEN),
        "code_commit": UNKNOWN_COMMIT,
        "note": ("a backfilled row must cite the evidence it was derived from; where none "
                 "exists the artefact stays unproven"),
    }
