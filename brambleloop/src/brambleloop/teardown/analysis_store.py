"""Record a private, structured reading of a manifested benchmark PDF.

The output is deliberately narrower than the reader's report: vocabulary keys,
presence flags, page numbers and counts only. It never contains document text.
It does not promote findings or write to the originality fingerprint.
"""
from __future__ import annotations

import hashlib
import inspect
import platform
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.models import BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct
from . import enforce, library, reader, size_family

_SHA = re.compile(r"^[0-9a-f]{64}$")
_JOINED_CUE = re.compile(r"\bjoin\s+each\s+round\b", re.I)
_SPIRAL_CUE = re.compile(r"\bcontinuous\s+spiral\b", re.I)
_AMBIGUOUS_CUE = re.compile(
    r"\b(?:not|no|never|avoid|without|don't|may|might|optional|if|unless|can|could)\b"
    r"[^.\n;]{0,80}\b(?:join\s+each\s+round|continuous\s+spiral)\b", re.I)
_AMBIGUOUS_AFTER_CUE = re.compile(
    r"\b(?:join\s+each\s+round|continuous\s+spiral)\b[^.\n;]{0,80}"
    r"\b(?:not|never|optional|if|unless|may|might)\b", re.I)
TECHNIQUE_EXTRACTOR_VERSION = "round_joining_v1"


class AnalysisRefused(ValueError):
    """The file is not the exact manifested and licensed purchase."""


def manifested_pdf(product, sha256: str) -> bool:
    """The exact analysed bytes must still be listed as a PDF on this purchase."""
    return product is not None and any(
        isinstance(item, dict) and item.get("sha256") == sha256
        and isinstance(item.get("name"), str) and item["name"].lower().endswith(".pdf")
        for item in (product.files or []))


def round_joining_observation(pages: list[str], *, fully_readable: bool) -> dict:
    """Record explicit joined/spiral cues as vocabulary and page numbers only.

    Mixed cues can describe different pieces, so they are not a conflict or a
    single construction rule. Missing or unreadable pages remain unknown.
    """
    if fully_readable is not True or not isinstance(pages, list) or not pages:
        return {"kind": "unknown", "pages": []}
    kinds, cited = set(), []
    for number, page in enumerate(pages, start=1):
        if (not isinstance(page, str) or not page.strip() or _AMBIGUOUS_CUE.search(page)
                or _AMBIGUOUS_AFTER_CUE.search(page)):
            return {"kind": "unknown", "pages": []}
        found = set()
        if _JOINED_CUE.search(page):
            found.add("joined_rounds_cue")
        if _SPIRAL_CUE.search(page):
            found.add("spiral_rounds_cue")
        if found:
            kinds.update(found)
            cited.append(number)
    kind = "mixed_cues" if len(kinds) > 1 else next(iter(kinds)) if kinds else "unknown"
    return {"kind": kind, "pages": cited}


def technique_extractor_digest() -> str:
    """Bind an observation to its extractor, PDF reader and runtime versions."""
    from importlib import metadata

    backend = reader.available() or "unavailable"
    try:
        version = metadata.version(backend) if backend != "unavailable" else "unavailable"
    except metadata.PackageNotFoundError:
        version = "unavailable"
    material = "\n".join((TECHNIQUE_EXTRACTOR_VERSION, inspect.getsource(round_joining_observation),
        _JOINED_CUE.pattern, _SPIRAL_CUE.pattern, _AMBIGUOUS_CUE.pattern,
        _AMBIGUOUS_AFTER_CUE.pattern, inspect.getsource(reader), backend, version,
        platform.python_version()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def needs_technique_supplement(source, *, extractor_sha256: str | None = None) -> bool:
    """Historical source evidence is never edited just to add a new extractor."""
    data = source.observations if isinstance(source.observations, dict) else {}
    construction = data.get("construction")
    expected = {"version": TECHNIQUE_EXTRACTOR_VERSION,
                "sha256": extractor_sha256 or technique_extractor_digest()}
    return (not isinstance(construction, dict) or "round_joining" not in construction
            or construction.get("round_joining_extractor") != expected)


def supplement_technique(db, analysis_id: int, *, expected_source_digest: str,
                         expected_extractor_sha256: str, env=None) -> dict:
    """Add a proposed, versioned cue without changing the reviewed source row."""
    from ..core.models import BenchmarkTechniqueObservation
    from .review import evidence_digest

    if type(analysis_id) is not int or analysis_id <= 0 or not isinstance(expected_source_digest, str) \
            or not _SHA.fullmatch(expected_source_digest) or not isinstance(expected_extractor_sha256, str) \
            or not _SHA.fullmatch(expected_extractor_sha256):
        raise AnalysisRefused("invalid technique observation source")
    if technique_extractor_digest() != expected_extractor_sha256:
        return {"created": False, "state": "stale"}
    with db.session() as s:
        source = s.get(BenchmarkAnalysis, analysis_id)
        if source is None or evidence_digest(source) != expected_source_digest:
            return {"created": False, "state": "stale"}
        if not needs_technique_supplement(source, extractor_sha256=expected_extractor_sha256):
            return {"created": False, "state": "already_in_analysis"}
        product = s.get(BenchmarkProduct, source.benchmark_id)
        if not manifested_pdf(product, source.file_sha256):
            raise AnalysisRefused("analysis source is not in the current purchase manifest")
        file = next(f for f in product.files if isinstance(f, dict)
                    and f.get("sha256") == source.file_sha256
                    and isinstance(f.get("name"), str) and f["name"].lower().endswith(".pdf"))
        ref, name, sha = product.ref, file["name"], source.file_sha256
    data = library.retrieve(f"{ref}/{name}", reader.ANALYST_ROLE, env=env, db=db,
                            use="private_analysis")
    if hashlib.sha256(data).hexdigest() != sha:
        raise AnalysisRefused("file no longer matches its manifested hash")
    inventory = reader.inventory(data).to_dict()
    pages, _images, _encrypted = reader._pages(data)
    observation = round_joining_observation(pages, fully_readable=inventory["fully_readable"])
    if technique_extractor_digest() != expected_extractor_sha256:
        return {"created": False, "state": "stale"}
    try:
        with db.session() as s:
            source = s.scalar(select(BenchmarkAnalysis).where(
                BenchmarkAnalysis.id == analysis_id).with_for_update())
            if source is None or evidence_digest(source) != expected_source_digest:
                return {"created": False, "state": "stale"}
            product = s.scalar(select(BenchmarkProduct).where(
                BenchmarkProduct.id == source.benchmark_id).with_for_update())
            if product is None or product.ref != ref or not any(
                    isinstance(f, dict) and f.get("name") == name and f.get("sha256") == sha
                    for f in (product.files or [])):
                raise AnalysisRefused("purchase manifest changed during technique extraction")
            terms = s.scalar(select(BenchmarkLicence).where(
                BenchmarkLicence.source_ref == ref).with_for_update())
            if terms is None or "private_analysis" not in (terms.allowed_uses or []) \
                    or "private_analysis" in (terms.prohibited_uses or []):
                raise AnalysisRefused("licence changed during technique extraction")
            existing = s.scalar(select(BenchmarkTechniqueObservation).where(
                BenchmarkTechniqueObservation.analysis_id == analysis_id,
                BenchmarkTechniqueObservation.extractor_version == TECHNIQUE_EXTRACTOR_VERSION,
                BenchmarkTechniqueObservation.extractor_sha256 == expected_extractor_sha256,
                BenchmarkTechniqueObservation.source_digest == expected_source_digest))
            if existing is not None:
                return {"created": False, "state": existing.review_state, "id": existing.id}
            row = BenchmarkTechniqueObservation(analysis_id=analysis_id,
                extractor_version=TECHNIQUE_EXTRACTOR_VERSION, source_digest=expected_source_digest,
                extractor_sha256=expected_extractor_sha256, file_sha256=sha,
                observation=observation, recorded_by="teardown_analyst")
            s.add(row)
            s.flush()
            return {"created": True, "state": "proposed", "id": row.id}
    except IntegrityError:
        with db.session() as s:
            existing = s.scalar(select(BenchmarkTechniqueObservation).where(
                BenchmarkTechniqueObservation.analysis_id == analysis_id,
                BenchmarkTechniqueObservation.extractor_version == TECHNIQUE_EXTRACTOR_VERSION,
                BenchmarkTechniqueObservation.extractor_sha256 == expected_extractor_sha256,
                BenchmarkTechniqueObservation.source_digest == expected_source_digest))
            if existing is None:
                raise
            return {"created": False, "state": existing.review_state, "id": existing.id}


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
    extractor_sha256 = technique_extractor_digest()
    inventory = reader.inventory(data).to_dict()
    measured = reader.analysis(inventory)
    architecture = reader.architecture_answers(inventory)
    construction = reader.construction_correspondence(inventory)
    pages, _images, _encrypted = reader._pages(data)
    sizes = size_family.numeric_summary(size_family.all_size_parse(pages))
    joining = round_joining_observation(pages, fully_readable=inventory["fully_readable"])
    if technique_extractor_digest() != extractor_sha256:
        raise AnalysisRefused("technique extractor changed during analysis")
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
                         "pieces": construction["pieces_named"], "round_joining": joining,
                         "round_joining_extractor": {"version": TECHNIQUE_EXTRACTOR_VERSION,
                                                     "sha256": extractor_sha256}},
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
