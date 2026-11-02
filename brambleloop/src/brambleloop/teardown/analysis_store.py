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

from ..core.models import BenchmarkAnalysis, BenchmarkProduct
from . import library, reader, size_family

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
