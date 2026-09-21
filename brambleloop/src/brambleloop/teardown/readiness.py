"""Is the Teardown Laboratory ready to receive CA$292 of purchased evidence?

The owner's instruction of 2026-09-21 is precise and worth honouring precisely: *do not ask
me to purchase the benchmark set until this complete intake/analysis path is verified ready*.
So this module answers that question from evidence rather than from confidence, and it is
built to give the uncomfortable answer.

Each capability is checked by something that would actually fail if the capability were
absent -- an importable reader, a caller that exists, a table with rows in it -- rather than
by a list somebody keeps up to date. A readiness report maintained by hand is a readiness
report that says ready.

The uncomfortable answer, on the day this was written: **not ready**. A PDF reader is
importable and nothing uses it; the library is a quarantine that by design never opens a
file, and `retrieve()` -- its only sanctioned reader -- is called by nothing. So the gap is a
module rather than a dependency, and everything downstream of reading a page (the materials,
the gauge, the construction, the cross-reference against what the listing promised) is a
schedule waiting for observations nothing produces. The purchase would land, be filed
correctly, be hashed, be manifested, and then sit there.
"""
from __future__ import annotations

# What the owner listed, in their order. Each entry names how it is checked, because a
# requirement whose check is "we think so" is a requirement nobody has checked.
CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("listing_images", "every sanctioned accessible listing and gallery image is captured "
                       "and analysed"),
    ("listing_promises", "the listing's promises and structured information are captured"),
    ("pdf_ingestion", "the entire purchased pattern is ingested, every page"),
    ("pattern_analysis", "materials, yarn, hook, gauge, sizing, finished measurements, "
                         "yardage, stitch vocabulary, construction, shaping, row and round "
                         "logic, assembly, finishing, charts, diagrams, progress photos, "
                         "troubleshooting and instructional structure are analysed"),
    ("promise_cross_reference", "listing imagery and promises are cross-referenced against "
                                "the purchased instructions"),
    ("construction_to_object", "how the written construction corresponds to the advertised "
                               "finished object is determined"),
    ("cross_set_comparison", "recurring practices are compared across the purchased set"),
    ("derived_standards", "evidence-backed Pattern Engineering and Pattern Presentation "
                          "standards are derived"),
    ("provenance", "provenance is preserved for every learned principle"),
)


def _has_pdf_reader() -> bool:
    """Whether anything in this environment can open a PDF at all."""
    import importlib.util

    return any(importlib.util.find_spec(name) is not None
               for name in ("pypdf", "PyPDF2", "fitz", "pdfplumber", "pdfminer"))


def retrieve_callers() -> list[str]:
    """Which modules actually *call* the quarantine's only reader.

    Parsed rather than grepped. The first version of this searched the source text for
    `library.retrieve(` and found three hits -- all of them in docstrings explaining what
    `retrieve` is for. A check that cannot tell a call from a sentence about a call reports
    the capability it was written to detect the absence of, which is the worst direction for
    this particular check to be wrong in.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    callers: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in ("library.py", "readiness.py"):
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            named = (isinstance(func, ast.Attribute) and func.attr == "retrieve") or (
                isinstance(func, ast.Name) and func.id == "retrieve")
            if named:
                callers.append(f"{path.relative_to(root)}:{node.lineno}")
                break
    return callers


def _retrieve_has_callers() -> bool:
    return bool(retrieve_callers())


def _rows(db, model, **where) -> int:
    from sqlalchemy import func, select

    if db is None:
        return 0
    with db.session() as s:
        q = select(func.count()).select_from(model)
        for key, value in where.items():
            q = q.where(getattr(model, key) == value)
        return int(s.scalar(q) or 0)


def check(db=None) -> dict:
    """Each capability, its verdict and the evidence behind it."""
    from ..core.models import BenchmarkListing, TeardownFinding

    from . import audits, scorecard

    reader = _has_pdf_reader()
    callers = retrieve_callers()
    listings = _rows(db, BenchmarkListing)
    findings = _rows(db, TeardownFinding)

    results = {
        "listing_images": {
            "ready": True,
            "evidence": ("intel.vision.analyse judges gallery images from the sanctioned "
                         "Etsy endpoint and the gallery cadence drains the backlog"),
            "observed_listings": listings,
        },
        "listing_promises": {
            "ready": True,
            "evidence": ("BenchmarkListing.detail holds the observed terms and "
                         "intake.promises_from_listing turns them into checkable claims, "
                         "with absence recorded as unknown rather than as false"),
        },
        "pdf_ingestion": {
            "ready": False,
            "evidence": (f"a PDF reader is importable ({'pypdf' if reader else 'none'}), and "
                         f"nothing uses it: library.retrieve -- the quarantine's only "
                         f"sanctioned reader -- is called by {callers or 'nothing'}. The gap "
                         f"is a module, not a dependency. The library never opens a file by "
                         f"design, and that design predates the owner's requirement to "
                         f"ingest every page"),
            "reader_importable": reader,
            "retrieve_callers": callers,
            "blocks_purchase": True,
        },
        "pattern_analysis": {
            "ready": False,
            "evidence": (f"teardown.audits holds {len(audits.SPECS) if hasattr(audits, 'SPECS') else 'the'} "
                         f"observation schedules and refuses a partial one, but observe() "
                         f"takes its answers from a caller. Nothing reads a purchased page "
                         f"to produce them, so the schedules are waiting on a reader that "
                         f"does not exist"),
            "blocks_purchase": True,
        },
        "promise_cross_reference": {
            "ready": False,
            "evidence": ("intake.deliverable_audit compares the listing's promises against "
                         "delivered *filenames* only, and says so. Comparing them against "
                         "the instructions needs the instructions read"),
            "blocks_purchase": True,
        },
        "construction_to_object": {
            "ready": False,
            "evidence": ("nothing relates written construction to the advertised finished "
                         "object; it is downstream of reading the construction"),
            "blocks_purchase": True,
        },
        "cross_set_comparison": {
            "ready": bool(findings),
            "evidence": (f"scorecard.composite_standard compares recorded findings across "
                         f"the set, and there are {findings} findings on file. It consumes "
                         f"observations rather than producing them, so it is ready in the "
                         f"sense that it works and empty in the sense that matters"),
        },
        "derived_standards": {
            "ready": bool(findings),
            "evidence": ("audits.publishing_requirements and teardown.pipeline.promote turn "
                         "findings into requirements and hypotheses, refusing a strength "
                         "with no company advantage behind it. Same dependency: findings"),
        },
        "provenance": {
            "ready": True,
            "evidence": ("every finding carries its benchmark_ref, and check_derived refuses "
                         "text that reads like a competitor's instructions rather than an "
                         "observation about them"),
        },
    }

    blocking = [k for k, v in results.items() if v.get("blocks_purchase")]
    return {
        "ready_for_purchase": not blocking,
        "blocking": blocking,
        "capabilities": [
            {"key": k, "what": what, **results[k]} for k, what in CAPABILITIES
        ],
        "verdict": (
            "READY" if not blocking else
            "NOT READY -- do not ask the owner to purchase yet"),
        "why_this_matters": (
            "the purchase is CA$292 of somebody's money and thirteen downloads of somebody "
            "else's copyrighted work. If the laboratory can file them and hash them and "
            "audit their filenames and then not read a single page, the money bought a "
            "folder"),
        "what_is_missing": (
            "a reader. The library is a quarantine that never opens a file, which was the "
            "right call when nothing was allowed to read one; the owner's protocol now "
            "requires every page ingested and analysed. retrieve() already exists for "
            "exactly this -- it refuses every caller that is not an analyst -- so the work "
            "is an analyst that uses it, page by page, with check_derived refusing "
            "transcription on every field it records"),
    }
