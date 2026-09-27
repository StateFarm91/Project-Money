"""Teardown findings as enforced requirements, read by the things they are requirements on.

Requirements 153-161. `audits.publishing_requirements()` converted every winning mechanism into
a Brambleloop requirement and the only place anybody read it was GET /api/teardown -- a
requirement that is displayed and never checked is advice. This module is the conversion into
something that binds, and the named consumers that read it:

- **pdf** (#152-#155, #158): the instruction-clarity, chart, beginner and materials audits --
  what our pattern document must exceed or make impossible.
- **pattern_help** (#155, #158): the beginner traps and materials observations, attached by
  the Pattern Help triage (`support.triage`) to every case whose question is about that trap.
- **premium_standard** (#156): the best purchased premium experience, never the average.
- **video** (#157): video mechanisms become the Brambleloop video specification; a product that
  ships video is held to it at publish, and one that ships none is `not_applicable`.
- **delivery_bundle** (#159): the packaging audit, against what our delivery bundle is.
- **support** (#160): support and rights elements, including every element the benchmarks
  *disagree* about -- an inconsistency across sellers becomes a clarity requirement on ours,
  checked against the shop package text we actually publish.

Three kinds of requirement. **exceed**: a benchmark scored 4-5 on an element, so ours must score
higher (or equal at the top of the scale, where nothing is higher). **prevent**: a benchmark
scored 0-2, a trap, so ours must be at least competent (3). **clarify**: benchmarks disagree by
three points or more, so ours must be unambiguous. Plus **floors**: an improvement the sandbox
promoted (#164) locks the score it reached as a floor no later release may fall below.

Confidence (#161) is carried on every requirement. A finding the analyst recorded with a
stated confidence below `MIN_BINDING_CONFIDENCE` is *provisional*: listed, routed and shown,
and not allowed to block a release until it is re-observed with more confidence. An unstated
confidence binds -- an existing requirement is never weakened for lacking a number.

Our own side is read, never assumed: the self-audits recorded under `brambleloop:<slug>` (the
same schedules, run on our product) and, for the support and rights elements, the shop package
text this company publishes. A binding requirement with nothing measured on our side is
`unmeasured`, and unmeasured blocks exactly as #168's unrun challenge does.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .audits import STRONG, WEAK
from .scorecard import SCALE, SELF_PREFIX

ACTION = "teardown.enforcement"

CONSUMERS_BY_AUDIT: dict[str, tuple[str, ...]] = {
    "pdf_architecture": ("pdf",),
    "instruction_clarity": ("pdf",),
    "chart_benchmark": ("pdf",),
    "beginner_experience": ("pattern_help", "pdf"),
    "premium_experience": ("premium_standard",),
    "video_teardown": ("video",),
    "materials_audit": ("pdf", "pattern_help"),
    "delivery_packaging": ("delivery_bundle",),
    "support_rights": ("support",),
}
# A twelve-dimension scorecard finding with no audit element, by its dimension.
CONSUMERS_BY_DIMENSION: dict[str, tuple[str, ...]] = {
    "product_creativity": ("premium_standard",),
    "pattern_correctness_evidence": ("pdf",),
    "instruction_clarity": ("pdf",),
    "chart_quality": ("pdf",),
    "beginner_support": ("pattern_help", "pdf"),
    "premium_presentation": ("premium_standard",),
    "video_support": ("video",),
    "materials_clarity": ("pdf", "pattern_help"),
    "delivery_packaging": ("delivery_bundle",),
    "support_experience": ("support",),
    "listing_promise_alignment": ("premium_standard",),
    "perceived_value": ("premium_standard",),
}
# The consumers `store.publish`'s release gates enforce. Pattern Help is enforced at triage.
PUBLISH_CONSUMERS: tuple[str, ...] = ("pdf", "premium_standard", "delivery_bundle", "video",
                                      "support")
MIN_BINDING_CONFIDENCE = 0.5
DISAGREEMENT = 3.0
COMPETENT = 3.0

# The words a customer question uses when it is about a Pattern Help trap (#155, #158).
TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "prior_knowledge_assumptions": ("how do i", "what is", "what does", "never done"),
    "technique_links": ("technique", "how to", "tutorial"),
    "photo_video_support": ("photo", "video", "picture"),
    "error_recovery": ("mistake", "wrong", "frog", "undo", "rip", "messed"),
    "terminology_variants": ("uk", "us terms", "british", "american", "terminology"),
    "tips": ("tip", "trick", "easier"),
    "progress_checkpoints": ("count", "should i have", "check", "correct so far"),
    "confidence_building": ("nervous", "beginner", "first time", "hard"),
    "yarn_specification": ("yarn", "brand", "weight"),
    "fibre": ("fibre", "fiber", "cotton", "wool", "acrylic"),
    "colour_quantities": ("how much", "how many balls", "skeins", "yardage"),
    "hooks": ("hook",),
    "notions": ("needle", "marker", "notions"),
    "gauge": ("gauge", "tension", "swatch"),
    "substitutions": ("substitute", "instead of", "different yarn"),
    "finished_dimensions": ("how big", "size", "dimensions", "measure"),
}

# What our published shop package says, per support and rights element (#160). A keyword is
# evidence that the element is addressed in the text a buyer actually reads.
SUPPORT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "support_instructions": ("message us", "tell us"),
    "faq": ("?",),
    "update_policy": ("fix the pattern", "version"),
    "errata_version_handling": ("version", "fix"),
    "finished_item_permissions": ("sell what i make", "sell what you make", "finished"),
    "redistribution_language": ("pass on the pattern", "share", "redistribut"),
    "contact_path": ("message us",),
}


def _key(row) -> tuple[str, str, str, str]:
    detail = row.detail or {}
    audit = str(detail.get("audit") or "")
    element = str(detail.get("element") or "")
    if audit and element:
        return f"{audit}:{element}", audit, element, row.dimension
    return f"dimension:{row.dimension}", "", "", row.dimension


def _consumers(audit: str, dimension: str) -> tuple[str, ...]:
    if audit:
        return CONSUMERS_BY_AUDIT.get(audit, ("premium_standard",))
    return CONSUMERS_BY_DIMENSION.get(dimension, ("premium_standard",))


def _score(row) -> float:
    detail = row.detail or {}
    value = detail.get("element_score")
    return float(value if value is not None else row.score)


def requirements(db, *, consumer: str | None = None) -> list[dict]:
    """Every requirement the recorded teardown findings imply, with who must meet it."""
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    with db.session() as s:
        rows = [r for r in s.scalars(select(TeardownFinding).order_by(TeardownFinding.id))
                if not r.benchmark_ref.startswith(SELF_PREFIX)]
    by_key: dict[str, list] = {}
    for r in rows:
        by_key.setdefault(_key(r)[0], []).append(r)

    out: list[dict] = []
    for key, group in sorted(by_key.items()):
        _k, audit, element, dimension = _key(group[0])
        consumers = _consumers(audit, dimension)
        if consumer and consumer not in consumers:
            continue
        scores = [_score(r) for r in group]
        best = max(group, key=lambda r: (_score(r), r.id))
        worst = min(group, key=lambda r: (_score(r), r.id))
        confidences = [r.confidence for r in group if r.confidence is not None]
        floor = None
        for r in group:
            adopted = (r.detail or {}).get("adopted")
            if adopted and adopted.get("floor") is not None:
                floor = max(floor or 0.0, float(adopted["floor"]))
        base = {"key": key, "audit": audit or None, "element": element or None,
                "dimension": dimension, "consumers": list(consumers),
                "benchmarks": sorted({r.benchmark_ref for r in group}),
                "findings": [r.id for r in group], "adopted_floor": floor}
        kinds = []
        if max(scores) >= STRONG:
            kinds.append(("exceed", best, _score(best)))
        if min(scores) <= WEAK:
            kinds.append(("prevent", worst, _score(worst)))
        if len({r.benchmark_ref for r in group}) >= 2 and max(scores) - min(scores) >= DISAGREEMENT:
            kinds.append(("clarify", best, max(scores)))
        for kind, source, score in kinds:
            conf = source.confidence
            binding = conf is None or conf >= MIN_BINDING_CONFIDENCE
            out.append({**base, "kind": kind, "benchmark_score": score,
                        "from_benchmark": source.benchmark_ref, "finding": source.id,
                        "requirement": source.improvement, "mechanism": source.mechanism,
                        "confidence": conf,
                        "confidence_range": ([min(confidences), max(confidences)]
                                             if confidences else None),
                        "binding": binding,
                        "status": "binding" if binding else "provisional"})
    return out


def our_scores(db, slug: str) -> dict[str, float]:
    """This product's newest self-audit score per requirement key."""
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    ref = f"{SELF_PREFIX}{slug}"
    out: dict[str, tuple[int, float]] = {}
    with db.session() as s:
        for r in s.scalars(select(TeardownFinding).where(TeardownFinding.benchmark_ref == ref)):
            key = _key(r)[0]
            if key not in out or r.id > out[key][0]:
                out[key] = (r.id, _score(r))
    return {k: v for k, (_i, v) in out.items()}


def catalogue_scores(db, key: str, *, after: datetime | None = None) -> list[tuple[int, float]]:
    """(finding id, score) for every product's newest self-audit on one key, optionally since."""
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    latest: dict[str, tuple[int, float]] = {}
    with db.session() as s:
        for r in s.scalars(select(TeardownFinding).order_by(TeardownFinding.id)):
            if not r.benchmark_ref.startswith(SELF_PREFIX) or _key(r)[0] != key:
                continue
            at = r.at if r.at.tzinfo else r.at.replace(tzinfo=timezone.utc)
            if after is not None and at <= after:
                continue
            latest[r.benchmark_ref] = (r.id, _score(r))
    return sorted(latest.values())


def support_text_evidence() -> dict[str, bool]:
    """Which support and rights elements the shop package we publish actually addresses."""
    from ..commerce import shop_package

    text = " ".join([shop_package.faq_text(),
                     " ".join(shop_package.policies().values())]).lower()
    return {element: any(w in text for w in words)
            for element, words in SUPPORT_EVIDENCE.items()}


def _judge(req: dict, ours: float | None, automated: bool | None) -> tuple[str, str]:
    bench = float(req["benchmark_score"])
    if req.get("adopted_floor") is not None and ours is not None and ours < req["adopted_floor"]:
        return "unmet", (f"fell below the floor {req['adopted_floor']} this company reached "
                         f"and promoted (#164)")
    if req["kind"] == "exceed":
        if ours is None:
            return "unmeasured", "no self-audit of this product on this element"
        if ours > bench or (bench >= 5 and ours >= 5):
            return "met", f"ours {ours} against the best benchmark's {bench}"
        return "unmet", (f"ours {ours} does not exceed {req['from_benchmark']}'s {bench} "
                         f"({SCALE.get(int(bench), '')})")
    if req["kind"] == "prevent":
        if automated:
            return "met", "addressed in the text this company publishes"
        if ours is None:
            return "unmeasured", "no self-audit shows this trap is prevented in our product"
        if ours >= COMPETENT:
            return "met", f"ours {ours}: competent or better where a benchmark scored {bench}"
        return "unmet", f"ours {ours}: the trap a benchmark fell into is present in ours"
    # clarify
    if automated or (ours is not None and ours >= STRONG):
        return "met", "unambiguous in what this company publishes"
    if ours is None and automated is None:
        return "unmeasured", "benchmarks disagree here and nothing shows ours is clear"
    return "unmet", "benchmarks disagree here and ours does not settle it"


def check(db, slug: str, *, consumers: tuple[str, ...] | None = None,
          has_video: bool | None = None) -> dict:
    """Whether this product meets every requirement its consumers enforce."""
    reqs = [r for r in requirements(db)
            if consumers is None or set(r["consumers"]) & set(consumers)]
    ours = our_scores(db, slug)
    support = support_text_evidence() if any("support" in r["consumers"] for r in reqs) else {}
    if has_video is None:
        has_video = product_has_video(db, slug)
    rows, reasons = [], []
    for r in reqs:
        if r["consumers"] == ["video"] and not has_video:
            rows.append({**r, "verdict": "not_applicable",
                         "why": "this product ships no video; the specification waits for one"})
            continue
        automated = (support.get(r["element"]) if "support" in r["consumers"]
                     and r["element"] else None)
        verdict, why = _judge(r, ours.get(r["key"]), automated)
        rows.append({**r, "ours": ours.get(r["key"]), "verdict": verdict, "why": why})
        if verdict in ("unmet", "unmeasured") and r["binding"]:
            reasons.append(f"teardown requirement {r['key']} ({r['kind']}, "
                           f"{'/'.join(r['consumers'])}): {verdict} -- {why}")
    return {"product": slug, "requirements": len(reqs),
            "met": sum(1 for r in rows if r["verdict"] == "met"),
            "unmet": [r["key"] for r in rows if r["verdict"] == "unmet"],
            "unmeasured": [r["key"] for r in rows if r["verdict"] == "unmeasured"],
            "provisional": [r["key"] for r in rows if not r["binding"]],
            "blocks": bool(reasons), "reasons": reasons, "rows": rows}


def product_has_video(db, slug: str) -> bool:
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        return any("video" in (a.asset_class or "") for a in s.scalars(
            select(ListingAsset).where(ListingAsset.product_slug == slug)))


def pattern_help_obligations(db) -> list[dict]:
    """What Pattern Help must cover: every beginner and materials trap, with its topic words."""
    out = []
    for r in requirements(db, consumer="pattern_help"):
        if r["kind"] not in ("prevent", "clarify") or not r["element"]:
            continue
        out.append({"key": r["key"], "element": r["element"], "kind": r["kind"],
                    "topic_words": list(TOPIC_WORDS.get(r["element"], ())),
                    "guidance": r["requirement"], "confidence": r["confidence"],
                    "binding": r["binding"]})
    return out


def video_specification(db) -> list[dict]:
    """The Brambleloop video requirements the video teardowns imply (#157)."""
    return [{"key": r["key"], "element": r["element"], "kind": r["kind"],
             "must": r["requirement"], "benchmark_score": r["benchmark_score"],
             "binding": r["binding"]}
            for r in requirements(db, consumer="video")]


def adopt_floor(db, finding_id: int, *, floor: float, improvement_id: int) -> dict:
    """Lock the level a promoted improvement reached as a floor on its requirement (#164)."""
    from ..core.models import TeardownFinding

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        if row is None:
            return {"adopted": False, "why": f"no finding {finding_id}"}
        row.detail = {**(row.detail or {}), "adopted": {
            "floor": float(floor), "improvement": improvement_id,
            "at": datetime.now(timezone.utc).isoformat()}}
    return {"adopted": True, "finding": finding_id, "floor": float(floor)}


def drop_floor(db, finding_id: int, *, why: str) -> dict:
    """Remove an adopted floor. Idempotent: a floor already gone is reported, not re-dropped,
    so a rollback resumed after an interruption (C-81) changes nothing the first run did."""
    from ..core.models import TeardownFinding

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        if row is None:
            return {"dropped": False, "why": f"no finding {finding_id}"}
        detail = dict(row.detail or {})
        prior = detail.pop("adopted", None)
        if prior is None:
            return {"dropped": False, "finding": finding_id, "already": True,
                    "why": "no floor is adopted on this finding"}
        detail["floor_dropped"] = {"was": prior, "why": why,
                                   "at": datetime.now(timezone.utc).isoformat()}
        row.detail = detail
    return {"dropped": True, "finding": finding_id}


def floor_absent(db, finding_id: int) -> dict:
    """The rollback verifier for an adopted floor: is the requirement free of it now?"""
    from ..core.models import TeardownFinding

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        detail = dict(row.detail or {}) if row is not None else {}
    adopted = detail.get("adopted")
    verified = row is not None and not adopted
    return {"verified": verified, "check": "self_audit.floor_absent", "finding": finding_id,
            "why": ("no floor is adopted on the finding" if verified else
                    f"finding {finding_id} still carries floor {adopted}" if row is not None
                    else f"no finding {finding_id}")}


def sweep(db) -> dict:
    """The cadence's pass: every certified product checked, every consumer's list refreshed."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    reqs = requirements(db)
    with db.session() as s:
        slugs = sorted({p.slug for p, _v in s.execute(
            select(Product, PatternVersion).where(
                PatternVersion.product_id == Product.id,
                PatternVersion.certified == True))})  # noqa: E712
    products = {slug: check(db, slug, consumers=PUBLISH_CONSUMERS) for slug in slugs}
    return {"at": datetime.now(timezone.utc).isoformat(),
            "requirements": len(reqs),
            "binding": sum(1 for r in reqs if r["binding"]),
            "provisional": sum(1 for r in reqs if not r["binding"]),
            "by_consumer": {c: sum(1 for r in reqs if c in r["consumers"])
                            for c in ("pdf", "pattern_help", "premium_standard", "video",
                                      "delivery_bundle", "support")},
            "pattern_help": pattern_help_obligations(db),
            "video_specification": video_specification(db),
            "products": {k: {"blocks": v["blocks"], "unmet": v["unmet"],
                             "unmeasured": v["unmeasured"]} for k, v in products.items()},
            "blocked": sorted(k for k, v in products.items() if v["blocks"]),
            "reading": "measured" if reqs else "UNMEASURED",
            "note": ("no purchased benchmark has been torn down, so there is nothing to "
                     "enforce yet; an absent standard is not a lenient one" if not reqs else
                     f"{len(reqs)} requirement(s) enforced across {len(slugs)} product(s)")}


PATTERN_HELP = "pattern_help"


def apply_pattern_help(db) -> dict:
    """Attach every matching Pattern Help obligation to the open support cases it concerns.

    #155 / #158: the beginner traps and materials observations are consumed where a customer
    meets them. A case whose question is about a trap the benchmarks fell into is routed to
    the `pattern_help` specialist with the obligation and its guidance on the case, so the
    draft reply and the person reading it answer the trap rather than the words. Idempotent:
    a case already carrying an obligation is not re-annotated.
    """
    from sqlalchemy import select

    from ..core.models import SupportCase

    obligations = [o for o in pattern_help_obligations(db) if o["topic_words"]]
    routed = []
    if not obligations:
        return {"obligations": 0, "routed": [], "reading": "UNMEASURED",
                "why": "no beginner or materials trap has been recorded from a teardown"}
    with db.session() as s:
        for case in s.scalars(select(SupportCase).where(SupportCase.resolved.is_(False))):
            question = (case.question or "").lower()
            have = {o["key"] for o in (case.detail or {}).get(PATTERN_HELP) or []}
            hits = [o for o in obligations if o["key"] not in have
                    and any(w in question for w in o["topic_words"])]
            if not hits:
                continue
            case.detail = {**(case.detail or {}), PATTERN_HELP: list(
                (case.detail or {}).get(PATTERN_HELP) or []) + [
                    {"key": o["key"], "element": o["element"], "guidance": o["guidance"],
                     "binding": o["binding"], "confidence": o["confidence"]} for o in hits]}
            if any(o["binding"] for o in hits) and case.specialist == "concierge":
                case.specialist = PATTERN_HELP
            routed.append({"case": case.id, "obligations": [o["key"] for o in hits],
                           "specialist": case.specialist})
    return {"obligations": len(obligations), "routed": routed, "reading": "measured"}
