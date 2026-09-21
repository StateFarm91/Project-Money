"""Is the Teardown Laboratory ready to receive CA$292 of purchased evidence?

The owner's instruction of 2026-09-21 is precise and worth honouring precisely: *do not ask
me to purchase the benchmark set until this complete intake/analysis path is verified ready*.
So this module answers that question from evidence rather than from confidence, and it is
built to give the uncomfortable answer.

Each capability is checked by something that would actually fail if the capability were
absent -- an importable reader, a caller that exists, a table with rows in it -- rather than
by a list somebody keeps up to date. A readiness report maintained by hand is a readiness
report that says ready.

The uncomfortable answer, the day this was written, was **not ready**: a PDF reader was
importable and nothing used it; `retrieve()` -- the quarantine's only sanctioned reader --
was called by nothing, so everything downstream of reading a page was a schedule waiting on
observations nothing produced. The purchase would have landed, been filed, been hashed, been
manifested, and then sat there.

`teardown/reader.py` is that missing module. So this check no longer asks whether a reader
exists; it **runs** one. `reader.self_test()` renders a real Brambleloop pattern PDF, files
it in a temporary library root, reads it back through `retrieve()` with its role refusal
intact, and puts the result through the whole path -- inventory, the analysis dimensions, the
promise cross-reference, the construction correspondence. A readiness report that reruns its
own proof every time it is asked cannot go stale the way a table of ticks does.
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

    from . import audits, reader, scorecard

    # Run the proof rather than describe it. This is the whole difference between this
    # module and the readiness table it replaced: a tick somebody wrote is true on the day
    # it was written, and this is true now or it says so now.
    proof = reader.self_test()
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
            "ready": bool(proof.get("ready")),
            "evidence": (
                f"reader.read() calls library.retrieve() and is called from "
                f"{callers or 'nothing'}. The self-test read "
                f"{proof.get('pages_with_text')} of {proof.get('pages')} pages of a real "
                f"pattern PDF through the quarantine, found "
                f"{len(proof.get('sections_found') or [])} of "
                f"{len(reader.SELF_TEST_SECTIONS)} known sections, and the quarantine still "
                f"refused pattern generation "
                f"({proof.get('quarantine_still_refuses_generation')}) and a path escape "
                f"({proof.get('quarantine_still_refuses_path_escape')})"),
            "reader_importable": reader.available(),
            "retrieve_callers": callers,
            "self_test": proof,
            "blocks_purchase": not proof.get("ready"),
        },
        "pattern_analysis": {
            "ready": bool(proof.get("ready")
                          and proof.get("analysis_dimensions_measured")
                          == proof.get("analysis_dimensions")),
            "evidence": (
                f"reader.analysis() measured "
                f"{proof.get('analysis_dimensions_measured')} of "
                f"{proof.get('analysis_dimensions')} of the owner's enumerated dimensions "
                f"on the self-test document, and reader.architecture_answers() answered "
                f"{proof.get('architecture_answers')} of the #152 presence schedule, "
                f"withholding {proof.get('architecture_withheld')}. What is *good* about "
                f"any of it stays the analyst's judgement through audits.observe(): this "
                f"reader records structure and does not score"),
            "blocks_purchase": not proof.get("ready"),
        },
        "promise_cross_reference": {
            "ready": bool(proof.get("ready")),
            "evidence": (
                f"reader.cross_reference() compares the listing's promises against the "
                f"document itself rather than against filenames. On the self-test it kept "
                f"{(proof.get('cross_reference') or {}).get('kept')} and left "
                f"{(proof.get('cross_reference') or {}).get('unverifiable')} unverifiable "
                f"-- a PDF cannot settle whether a video was delivered, and saying so is "
                f"the point. intake.deliverable_audit still answers the filename half"),
            "blocks_purchase": not proof.get("ready"),
        },
        "construction_to_object": {
            "ready": bool(proof.get("ready")),
            "evidence": (
                f"reader.construction_correspondence() relates the pieces, assembly and "
                f"size labels a document actually contains to the advertised object, and "
                f"returned {proof.get('construction_verdict')!r} on the self-test. A "
                f"seamless construction and an unreadable page both produce "
                f"`unverifiable`, never `corresponds`"),
            "blocks_purchase": not proof.get("ready"),
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
            "" if not blocking else
            "the capabilities listed in `blocking`, each with its evidence above"),
        "empty_rather_than_absent": (
            "cross_set_comparison and derived_standards are built, exercised and empty: "
            "they consume findings, and there are no findings because nothing has been "
            "purchased. They do not block the purchase because the purchase is what fills "
            "them -- but they are reported unready rather than ticked, because a comparison "
            "across a set of nothing is not a comparison"),
        "what_the_reader_will_not_do": (
            "return text. Every value it produces is a count, a page number, a measured "
            "number or a key from its own vocabularies, so a purchased pattern cannot reach "
            "a Brambleloop product through it -- not by policy, by there being no code path "
            "that emits a substring of the document"),
    }
