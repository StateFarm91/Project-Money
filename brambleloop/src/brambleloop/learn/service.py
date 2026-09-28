"""Deterministic source ingestion and fail-closed lesson release contract.

This is not a prose judge. Arithmetic/terminology are machine checked, while pedagogical
and visual judgements must be explicitly recorded against the exact canonical revision.
No review is manufactured by the scanner; absent reviews never mean approval.
"""
from __future__ import annotations
import hashlib
import json
import re
from sqlalchemy import select
from ..cir import stitches
from ..core.models import PatternVersion, Product, SupportCase
from .models import LearnNode, LearnEdge, LearnGap, Lesson

DIMENSIONS = ("correctness", "completeness", "sequencing", "clarity", "accessibility",
              "visual_accuracy", "executable_skill")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def topics(value):
    """Extract explicit CIR structure, never infer technique truth from marketing prose."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "stitch" and isinstance(item, str):
                stitches.get(item)
                found.add("stitch:" + item)
            elif key == "construction" and isinstance(item, str):
                found.add("construction:" + item)
            elif key == "loop" and item in ("front", "back"):
                found.add("technique:" + item + "_loop")
            elif key == "gauge" and item:
                found.add("technique:gauge")
            elif key == "yarn_weight" and isinstance(item, str):
                found.add("yarn:" + item)
            elif key == "hook_mm" and isinstance(item, (int, float)):
                found.add("hook_mm:" + str(item))
            elif key == "yarn" and isinstance(item, dict):
                if item.get("weight"):
                    found.add("yarn:" + str(item["weight"]))
            found.update(topics(item))
    elif isinstance(value, list):
        for item in value:
            found.update(topics(item))
    return found


def validate_spec(spec):
    # Reject malformed external JSON before semantic checks dereference nested fields.
    # Return validation errors (rather than catching arbitrary implementation failures),
    # so save_lesson raises ValueError and the editor API maps refusal to HTTP 422.
    if not isinstance(spec, dict):
        return ["lesson specification must be an object"]
    errors = []
    for field in ("author", "learner_problem", "terminology"):
        if not isinstance(spec.get(field), str):
            errors.append(f"{field} must be a string")
    lesson_topics = spec.get("topics")
    if (not isinstance(lesson_topics, list)
            or any(not isinstance(topic, str) or not topic for topic in lesson_topics)):
        errors.append("topics must be a list of nonempty strings")
    assumptions = spec.get("assumptions")
    if not isinstance(assumptions, dict):
        errors.append("assumptions must be an object")
    else:
        if type(assumptions.get("hook_mm")) not in (int, float):
            errors.append("hook_mm must be a number")
        if not isinstance(assumptions.get("yarn_weight"), str):
            errors.append("yarn_weight must be a string")
    for field in ("assets", "steps"):
        entries = spec.get(field, [])
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            errors.append(f"{field} must be a list of objects")
            continue
        text_fields = ("rights", "source", "sha256") if field == "assets" else ("stitch", "term", "instruction")
        for entry in entries:
            if any(not isinstance(entry.get(key), str) for key in text_fields):
                errors.append(f"{field} entries require string fields: {', '.join(text_fields)}")
            if field == "assets" and "license_ref" in entry and not isinstance(entry["license_ref"], str):
                errors.append("license_ref must be a string")
    if errors:
        return errors

    if not spec.get("author") or not spec.get("learner_problem") or not spec.get("topics") or not spec.get("steps"):
        errors.append("learner problem, topics and executable steps required")
    if spec.get("terminology") not in ("US", "UK"):
        errors.append("explicit US/UK terminology required")
    if not spec.get("assumptions", {}).get("hook_mm") or not spec.get("assumptions", {}).get("yarn_weight"):
        errors.append("hook/yarn assumptions required")
    assets = spec.get("assets", [])
    if not assets:
        errors.append("canonical teaching asset/prose provenance required")
    for asset in assets:
        if (asset.get("rights") not in ("brambleloop_original", "licensed")
                or not asset.get("source") or not re.fullmatch(r"[a-f0-9]{64}", str(asset.get("sha256", "")))
                or (asset.get("rights") == "licensed" and not asset.get("license_ref"))):
            errors.append("asset provenance incomplete")
    for step in spec.get("steps", []):
        try:
            st = stitches.get(step["stitch"])
            n = step["repeat"]
            if type(n) is not int or n < 1 or step["consumes"] != st.consumes*n or step["produces"] != st.produces*n:
                errors.append("step count disagrees with canonical stitch semantics")
            if step.get("term") != stitches.term(st.code, spec.get("terminology", "US")):
                errors.append("step terminology disagrees with taxonomy")
            if not step.get("instruction"):
                errors.append("step instruction missing")
        except (KeyError, ValueError, TypeError):
            errors.append("unrecognized or incomplete stitch step")
    return errors


def save_lesson(db, slug, spec):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("invalid lesson slug")
    errors = validate_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))
    revision = digest(spec)
    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None:
            s.add(Lesson(slug=slug, revision=revision, spec=spec, reviews=[], state="DRAFT"))
        elif row.revision != revision:
            row.spec, row.revision, row.reviews, row.state = spec, revision, [], "DRAFT"
        s.merge(LearnNode(key="lesson:" + slug, kind="lesson",
                          detail={"revision": revision}))
        for topic in spec["topics"]:
            s.merge(LearnNode(key=topic, kind=topic.split(":")[0], detail={}))
            s.merge(LearnEdge(key=digest(["lesson:"+slug, revision, topic]),
                              source="lesson:"+slug, target=topic, relation="teaches",
                              evidence={"lesson_revision": revision, "approval": "not_implied"}))
    return revision


def review_lesson(db, slug, revision, reviewer, verdicts, evidence_ref):
    if not reviewer or not evidence_ref or set(verdicts) != set(DIMENSIONS):
        raise ValueError("complete independent review evidence required")
    if any(v not in ("PASS", "FAIL", "UNKNOWN") for v in verdicts.values()):
        raise ValueError("invalid verdict")
    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None or row.revision != revision or digest(row.spec) != revision:
            raise ValueError("review revision is stale")
        if reviewer == row.spec.get("author"):
            raise ValueError("lesson author cannot self-approve")
        row.reviews = [{"revision": revision, "reviewer": reviewer,
                        "verdicts": verdicts, "evidence_ref": evidence_ref,
                        "evidence_class": "human_attestation", "automated_truth_proof": False}]
        row.state = "APPROVED" if eligible(row) else "WITHHELD"


def eligible(row):
    if validate_spec(row.spec) or digest(row.spec) != row.revision:
        return False
    return any(r.get("revision") == row.revision and r.get("reviewer") != row.spec.get("author")
               and r.get("evidence_ref") and all(r.get("verdicts", {}).get(d) == "PASS" for d in DIMENSIONS)
               for r in row.reviews)


def help_links(db, requested):
    """Internal routes only; approval is revalidated at consumption, not trusted by label."""
    with db.session() as s:
        return [{"slug": row.slug, "href": "/learn/" + row.slug + "?revision=" + row.revision, "revision": row.revision,
                 "topics": sorted(set(row.spec["topics"]) & set(requested))}
                for row in s.scalars(select(Lesson)).all()
                if eligible(row) and set(row.spec["topics"]) & set(requested)]


def scan(db):
    """Periodic production consumer; durable gaps are the department's work queue.

    One row per topic prevents repeated pattern releases from creating duplicate lessons.
    Edges retain exact version hashes and support IDs without copying customer prose/PII.
    Transaction rollback prevents half-ingested graph state on malformed CIR.
    """
    with db.session() as s:
        sources = []
        for pv, product in s.execute(select(PatternVersion, Product).join(Product)).all():
            source = "pattern:" + str(pv.id) + ":" + digest(pv.cir_json)
            sources.append((source, "pattern", topics(pv.cir_json),
                            {"pattern_version_id": pv.id, "product_slug": product.slug,
                             "cir_digest": digest(pv.cir_json), "version": pv.version}))
        for case in s.scalars(select(SupportCase)).all():
            # Product-linked support remains useful without guessing the customer's intent.
            # Explicit concern IDs are conservative routing labels, not technical claims.
            refs = {"support:" + case.specialist} if case.specialist else set()
            sources.append(("support:" + str(case.id), "support", refs,
                            {"support_case_id": case.id, "product_slug": case.product_slug}))
        approved = set()
        for lesson in s.scalars(select(Lesson)).all():
            if eligible(lesson):
                approved.update(lesson.spec["topics"])
        for source, kind, needs, evidence in sources:
            s.merge(LearnNode(key=source, kind=kind, detail=evidence))
            for topic in sorted(needs):
                s.merge(LearnNode(key=topic, kind=topic.split(":")[0], detail={}))
                s.merge(LearnEdge(key=digest([source, topic]), source=source, target=topic,
                                  relation="needs_help", evidence=evidence))
                gap = s.get(LearnGap, topic)
                if gap is None:
                    gap = LearnGap(topic=topic, state="QUEUED", owner="learn", evidence=[])
                    s.add(gap)
                if evidence not in gap.evidence:
                    gap.evidence = [*gap.evidence, evidence]
                gap.state = "COVERED" if topic in approved else "QUEUED"
        # Revoked coverage reopens even when its source is no longer returned by a scan.
        for gap in s.scalars(select(LearnGap)).all():
            gap.state = "COVERED" if gap.topic in approved else "QUEUED"
        gaps = s.scalars(select(LearnGap)).all()
        return {"decision": "QUEUE" if any(g.state == "QUEUED" for g in gaps) else "WATCH",
                "queued": sum(g.state == "QUEUED" for g in gaps), "sources": len(sources),
                "generated": 0, "published": 0}


def approved_lesson(db, slug):
    """Public read returns approved factual spec only; caller must escape/render safely."""
    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None or not eligible(row):
            return None
        return {"slug": row.slug, "revision": row.revision, "spec": row.spec}


def pdf_help_links(db, cir):
    """An operator-configured HTTPS origin is necessary for portable PDF links.

    Never put a relative route into a downloadable PDF. With no deployed owned origin,
    return no links; the architecture does not invent a live website.
    """
    import os
    from urllib.parse import urlsplit
    base = os.environ.get("BRAMBLELOOP_LEARN_PUBLIC_ORIGIN", "").strip()
    if not base:
        return []
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Learn public origin must be an operator-owned HTTPS origin")
    return [{**link, "url": base.rstrip("/") + link["href"]}
            for link in help_links(db, topics(cir))]
