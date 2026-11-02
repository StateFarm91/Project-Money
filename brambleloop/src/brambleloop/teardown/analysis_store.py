"""Record a private, structured reading of a manifested benchmark PDF.

The output is deliberately narrower than the reader's report: vocabulary keys,
presence flags, page numbers and counts only. It never contains document text.
It does not promote findings or write to the originality fingerprint.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.models import BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct
from . import enforce, library, reader, size_family

_SHA = re.compile(r"^[0-9a-f]{64}$")


class AnalysisRefused(ValueError):
    """The file is not the exact manifested and licensed purchase."""


def analyse_file(db, benchmark_id: int, file_sha256: str, *, env=None) -> dict:
    """Analyse an exact manifest version and persist the result once.

    Reads are checked against the current purchase licence and hash. Existing
    analysis is reusable only while the hash is still present in the manifest.
    """
    if type(benchmark_id) is not int or benchmark_id <= 0 or not isinstance(file_sha256, str) \
            or not _SHA.fullmatch(file_sha256):
        raise AnalysisRefused("invalid benchmark or file hash")
    with db.session() as s:
        product = s.get(BenchmarkProduct, benchmark_id)
        if product is None:
            raise AnalysisRefused("purchase not found")
        matches = [f for f in (product.files or []) if f.get("sha256") == file_sha256
                   and str(f.get("name") or "").lower().endswith(".pdf")]
        if not matches:
            raise AnalysisRefused("PDF hash not in current purchase manifest")
        name, ref = matches[0]["name"], product.ref

    # This is the same licensed quarantine used by reader.read. Unlike that
    # function, this path does not replace the aggregate originality fingerprint
    # with the fingerprint of just one PDF.
    data = library.retrieve(f"{ref}/{name}", reader.ANALYST_ROLE, env=env, db=db,
                            use="private_analysis")
    if hashlib.sha256(data).hexdigest() != file_sha256:
        raise AnalysisRefused("file no longer matches its manifested hash")
    inventory = reader.inventory(data).to_dict()
    measured = reader.analysis(inventory)
    architecture = reader.architecture_answers(inventory)
    construction = reader.construction_correspondence(inventory)
    pages, _images, _encrypted = reader._pages(data)
    sizes = size_family.numeric_summary(size_family.all_size_parse(pages))
    observations = {
        "pages": inventory["pages"], "pages_with_text": inventory["pages_with_text"],
        "fully_readable": inventory["fully_readable"],
        "dimensions": {key: value["verdict"] for key, value in measured["dimensions"].items()},
        "architecture": {key: {"present": value["score"], "pages": value.get("pages", [])}
                         for key, value in architecture["answers"].items()},
        # Unknowns must remain visible for the analyst; they are not false answers.
        "architecture_withheld": architecture["withheld"],
        "architecture_mentioned_not_headed": architecture["mentioned_but_not_a_heading"],
        "architecture_complete": architecture["complete"],
        "construction": {"verdict": construction["verdict"],
                         "worked_in_rounds": construction["worked_in_rounds"],
                         "pieces": construction["pieces_named"]},
        "size_family": sizes,
        # Empty inputs to schematic_cross_check return AGREE, which is not evidence.
        "schematic_state": "UNKNOWN",
    }
    try:
        with db.session() as s:
            current = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id)
                               .with_for_update())
            if current is None or not any(f.get("sha256") == file_sha256 and f.get("name") == name
                                          for f in (current.files or [])):
                raise AnalysisRefused("purchase manifest changed during analysis")
            terms = s.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == current.ref).with_for_update())
            if (terms is None or "private_analysis" not in (terms.allowed_uses or [])
                    or "private_analysis" in (terms.prohibited_uses or [])):
                raise AnalysisRefused("licence changed during analysis")
            existing = s.scalar(select(BenchmarkAnalysis).where(
                BenchmarkAnalysis.benchmark_id == benchmark_id,
                BenchmarkAnalysis.file_sha256 == file_sha256))
            if existing is not None:
                return {"id": existing.id, "created": False}
            row = BenchmarkAnalysis(benchmark_id=benchmark_id, file_sha256=file_sha256,
                                    observations=observations)
            s.add(row)
            s.flush()
            return {"id": row.id, "created": True}
    except IntegrityError:
        # A concurrent worker may have committed the same manifest hash first.
        with db.session() as s:
            existing = s.scalar(select(BenchmarkAnalysis).where(
                BenchmarkAnalysis.benchmark_id == benchmark_id,
                BenchmarkAnalysis.file_sha256 == file_sha256))
            if existing is None:
                raise
            return {"id": existing.id, "created": False}


def reconcile_state(db, benchmark_id: int) -> dict:
    """Recompute analysis progress from the current manifest and durable rows.

    This is safe to repeat after a crash and never treats a missing analysis or
    a missing licence as a completed read. Review remains a separate decision.
    """
    with db.session() as s:
        product = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id)
                           .with_for_update())
        if product is None:
            raise AnalysisRefused("purchase not found")
        if product.teardown_state not in ("queued", "awaiting_analyst", "needs_analyst", "analysed"):
            return {"state": product.teardown_state, "changed": False}
        pdfs = [f for f in (product.files or [])
                if str(f.get("name") or "").lower().endswith(".pdf")]
        if not pdfs:
            return {"state": product.teardown_state, "changed": False, "reason": "no_pdf"}
        lic = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == product.ref))
        if lic is None or "private_analysis" not in (lic.allowed_uses or []) \
                or "private_analysis" in (lic.prohibited_uses or []):
            new_state, reason = "needs_analyst", "licence_not_permitted"
        elif any(not isinstance(f.get("sha256"), str) or not _SHA.fullmatch(f["sha256"])
                 for f in pdfs):
            new_state, reason = "needs_analyst", "manifest_hash_unknown"
        else:
            expected = {f["sha256"] for f in pdfs}
            rows = list(s.scalars(select(BenchmarkAnalysis).where(
                BenchmarkAnalysis.benchmark_id == benchmark_id,
                BenchmarkAnalysis.file_sha256.in_(expected))))
            by_hash = {r.file_sha256: r for r in rows}
            low_confidence = False
            for row in rows:
                data = row.observations or {}
                total, readable = data.get("pages"), data.get("pages_with_text")
                if (type(total) is not int or type(readable) is not int or total <= 0
                        or readable < 0 or readable > total
                        or readable / total < enforce.MIN_BINDING_CONFIDENCE):
                    low_confidence = True
            if low_confidence:
                new_state, reason = "needs_analyst", "low_confidence"
            elif expected - set(by_hash):
                new_state, reason = "queued", "analysis_pending"
            else:
                new_state, reason = "analysed", "analysis_complete"
        changed = product.teardown_state != new_state
        product.teardown_state = new_state
        return {"state": new_state, "changed": changed, "reason": reason}
