"""Role-appropriate independent review of a listing frame (owner decision D-W4-VISROLE).

`release._review_frames` (#61) used to ask every frame the ten photographic realism checks
(`gallery.REALISM_CHECKS`: drape, hands_and_fingers, ...). A chart, a size card or a "what
you get" infographic cannot answer them. The reviewer said "unclear", an unmade check is
never a pass, and so in production every deterministic non-photo frame stayed `unjudged`
and blocked publication for a reason that had nothing to do with the frame.

The owner's ruling, 2026-10-12: photographic renders are told apart from charts, diagrams
and infographics, and each is held to checks that fit its role. No frame is exempted from
verification:

* **Every frame keeps:**
  - product truth (Asset Truth and the frame plan);
  - semantic accuracy (`inspect.compare` on a blind description);
  - legibility at listing sizes;
  - disclosure;
  - every publication veto.
* **A photographic frame** still needs every realism check. An unclear one is unjudged.
* **A non-photo frame** gets role checks in place of the realism checks:
  - its data and labels match the record;
  - its text is legible at 340 px;
  - its scale is not misleading;
  - it carries no third-party marks;
  - its disclosure is present.

A role check that was not answered is `None`, and `None` is not passed.

The role is classified **deterministically from the frame plan** (asset class and frame
role). The model is never asked what kind of frame it is looking at. Anything this table
does not name is treated as photographic, which is the strictest rule, so an unknown frame
never receives the lighter one.
"""
from __future__ import annotations

PHOTOGRAPHIC = "photographic"
DISCLOSED_RENDER = "disclosed_render"   # the deterministic twin drawing of the product (D-FB-9)
CHART = "chart"
INFOGRAPHIC = "infographic"
PATTERN_PREVIEW = "pattern_preview"
NON_PHOTO = frozenset({DISCLOSED_RENDER, CHART, INFOGRAPHIC, PATTERN_PREVIEW})

# (asset class, frame role) -> visual role. "*" matches any frame role. Nothing else is
# non-photo. PHYSICAL_PRODUCT_PHOTO and AI_LIFESTYLE_CONCEPT are photographic by name;
# anything unlisted falls through to photographic as well.
_BY_PLAN: dict[tuple[str, str], str] = {
    ("DIGITAL_TWIN_RENDER", "hero"): DISCLOSED_RENDER,
    ("DIGITAL_TWIN_RENDER", "chart"): CHART,
    ("INFOGRAPHIC", "*"): INFOGRAPHIC,
    ("PATTERN_PREVIEW", "*"): PATTERN_PREVIEW,
}

# The role checks a non-photo frame must pass, in place of the photographic realism checks.
ROLE_CHECKS: tuple[str, ...] = (
    "data_matches_record", "text_legible_340", "scale_not_misleading",
    "no_third_party_marks", "disclosure_present",
)

LEGIBILITY_PX = 340
# The words a frame that draws the product must carry, in its own pixels (D-FB-7 / D-FB-9).
# The listing hero draws "Digital (pattern) render ..., not a photograph of a finished item".
DRAWN_DISCLOSURE = "not a photograph"
# Asset Truth codes about size or scale. Any of them on a frame means its scale misleads.
_SCALE_CODES = ("CLAIM_SIZE_", "ASSET_STITCH_SCALE_")


# ---- legibility at the real display size (owner ruling 2026-10-19, D-W4-VISROLE) ----------
#
# "Essential customer-facing text must be readable at the ACTUAL display size; there is no
# blanket pixel floor." Each line a listing frame draws is recorded with its `slot` (what the
# line is in the frame plan), and this table -- never a model, never the pixels -- decides
# whether the line is essential and where it is really displayed:
#
# * GRID_PX (340): the frame's headline/title, the text that must read in the gallery strip
#   and grid (the existing 340 px rule for headlines, unchanged).
# * LISTING_VIEW_PX (390): every other essential line, read in the phone gallery
#   (`publish.mobile.CONTEXT_MEANS[PHONE_GALLERY]["px"]`; a test pins the two together).
#
# Essential text must clear `thumbnail.MIN_LEGIBLE_TEXT_PX` at that size. Secondary text (the
# brand line, the excerpt that shows what the pattern looks like) is measured and reported,
# never blocked. A slot this table does not name is essential at the grid size: an unknown
# line always gets the strictest rule.
GRID_PX = 340
LISTING_VIEW_PX = 390
ESSENTIAL, SECONDARY = "essential", "secondary"
_SECONDARY_SLOTS = frozenset({"brand", "excerpt"})
_GRID_SLOTS = frozenset({"title", "headline"})
_LISTING_VIEW_SLOTS = frozenset({
    "product_type",      # hero: CROCHET PATTERN · PDF -- what is being sold
    "disclosure",        # hero: not a photograph of a finished item (D-FB-7 / D-FB-9)
    "row_label", "row_value",   # what you get / what it takes / collection rows
    "size_label",        # size card: the finished measurement
    "scale_reference",   # size card: the named reference ("180 cm adult")
    "colour_name",       # materials card: every CIR colour, a record label
    "caption",           # pattern preview: "Actual pattern text from this release"
})


def text_tier(role: str, slot: str | None) -> dict:
    """Essential or secondary, and the px width the line is really displayed at."""
    slot = str(slot or "")
    if slot in _SECONDARY_SLOTS:
        return {"tier": SECONDARY, "essential": False, "display_px": LISTING_VIEW_PX,
                "slot": slot}
    if slot in _LISTING_VIEW_SLOTS:
        return {"tier": ESSENTIAL, "essential": True, "display_px": LISTING_VIEW_PX,
                "slot": slot}
    # titles, headlines and any slot not named above: essential at the smaller grid size
    return {"tier": ESSENTIAL, "essential": True, "display_px": GRID_PX, "slot": slot or None}


def legibility(frame) -> dict | None:
    """Every recorded line's rendered px at its real display size, split essential/secondary.

    None when the frame has no recorded layout. `ok` is whether every essential line clears
    `thumbnail.MIN_LEGIBLE_TEXT_PX`; secondary lines below it are listed, not failed. A line
    with no recorded size is reported as unmeasured (`ok` None), never as legible.
    """
    from ..commerce.thumbnail import MIN_LEGIBLE_TEXT_PX

    texts = _texts(frame)
    if texts is None:
        return None
    width = getattr(getattr(frame, "image", None), "size", (2000, 2000))[0] or 2000
    role = str(getattr(frame, "role", "") or "")
    lines, unmeasured = [], []
    for e in texts:
        tier = text_tier(role, e.get("slot"))
        if e.get("pt") is None:
            unmeasured.append(str(e.get("text"))[:60])
            continue
        px = round(e["pt"] * tier["display_px"] / width, 1)
        lines.append({"text": str(e.get("text"))[:60], "slot": tier["slot"],
                      "tier": tier["tier"], "display_px": tier["display_px"],
                      "pt": e["pt"], "px": px, "legible": px >= MIN_LEGIBLE_TEXT_PX})
    essential_fail = [ln for ln in lines if ln["tier"] == ESSENTIAL and not ln["legible"]]
    secondary_small = [ln for ln in lines if ln["tier"] == SECONDARY and not ln["legible"]]
    ess = [ln["px"] for ln in lines if ln["tier"] == ESSENTIAL]
    return {"floor_px": MIN_LEGIBLE_TEXT_PX,
            "ok": None if unmeasured else not essential_fail,
            "essential_failing": essential_fail, "secondary_below_floor": secondary_small,
            "unmeasured": unmeasured,
            "smallest_essential_px": min(ess) if ess else None,
            "smallest_px": min((ln["px"] for ln in lines), default=None),
            "lines": lines}


def classify(frame) -> str:
    """The frame's visual role, from its plan alone (asset class and frame role)."""
    if getattr(frame, "has_model", False):
        return PHOTOGRAPHIC
    cls = getattr(getattr(frame, "asset_class", None), "value",
                  getattr(frame, "asset_class", None))
    cls, role = str(cls or ""), str(getattr(frame, "role", "") or "")
    return _BY_PLAN.get((cls, role)) or _BY_PLAN.get((cls, "*")) or PHOTOGRAPHIC


def expected_labels(frames, cir, twin) -> dict[int, list[str]]:
    """Text each frame must draw because the record says so, keyed by position.

    The size card draws its label from `size_frame_displays`, the same list the dimensional
    auditor reads. The materials card names every colour in the CIR. Other frames draw no
    record values that can be matched character for character, so their record agreement is
    Asset Truth's and the frame plan's (see `role_checks`).
    """
    from ..publish.listing_assets import size_frame_displays

    out: dict[int, list[str]] = {}
    for f in frames:
        if f.role == "size" and twin.width_cm and twin.height_cm:
            shown = size_frame_displays(width_cm=twin.width_cm, height_cm=twin.height_cm,
                                        shape=getattr(twin, "shape", None))
            out[f.position] = [shown["label"], shown["reference_label"]]
        elif f.role == "size" and twin.circumference_cm:
            out[f.position] = [f"{twin.circumference_cm:.0f} cm"]
        elif f.role == "materials":
            out[f.position] = sorted(cir.colors)
    return out


def _texts(frame) -> list[dict] | None:
    image = getattr(frame, "image", None)
    layout = (getattr(image, "info", None) or {}).get("layout")
    if layout is None:
        return None
    return [e for e in layout if e.get("kind") == "text" and str(e.get("text") or "").strip()]


def _check(passed, why: str, **extra) -> dict:
    return {"passed": passed, "why": why, **extra}


def role_checks(frame, *, slug: str, visual_role: str, description: dict | None,
                truth_findings=(), plan_findings=(), labels=None) -> dict[str, dict]:
    """The five role checks for a non-photo frame. Each `passed` is True, False or None."""
    from ..commerce import buyer_trust
    from ..commerce.thumbnail import MIN_LEGIBLE_TEXT_PX
    from ..publish.layout_qa import MIN_TEXT_PT
    from .inspect import marks_found

    pos = frame.position
    texts = _texts(frame)
    where = f"asset:{slug}-frame-{pos}"
    mine = [f for f in truth_findings
            if getattr(f, "is_error", False) and getattr(f, "component", None) == where]
    tag = f"frame {pos}"
    plan = [p for p in plan_findings
            if f"{tag}:" in p or f"{tag} " in p or p.endswith(tag)]
    out: dict[str, dict] = {}

    # 1. Data and labels match the record.
    problems = [f"{f.code}: {f.message}"[:160] for f in mine] + [p[:160] for p in plan]
    missing = []
    if labels:
        if texts is None:
            out["data_matches_record"] = _check(
                None, "the frame carries no recorded layout, so its labels cannot be read")
        else:
            drawn = " | ".join(str(e.get("text")) for e in texts)
            missing = [lbl for lbl in labels if lbl not in drawn]
    if "data_matches_record" not in out:
        bad = problems + [f"label {m!r} from the record is not drawn" for m in missing]
        out["data_matches_record"] = _check(
            not bad, "; ".join(bad)[:400] if bad else
            "Asset Truth and the frame plan found nothing on this frame"
            + (f"; every record label is drawn ({len(labels)})" if labels else ""))

    # 2. Text legible where it is shown (owner ruling 2026-10-19): every ESSENTIAL line clears
    # `thumbnail.MIN_LEGIBLE_TEXT_PX` at its real display size (`text_tier`: headlines at the
    # 340 px grid, other essential lines at the 390 px phone gallery), the headline still
    # clears it at 340 px, and no line of any tier is under layout QA's minimum face.
    # Secondary lines below the floor are reported with the verdict, never blocking.
    if texts is None:
        out["text_legible_340"] = _check(None, "no recorded layout to measure")
    elif not texts:
        out["text_legible_340"] = _check(False, "a non-photo frame states its role in type, "
                                                "and this frame drew none")
    else:
        width = getattr(frame.image, "size", (2000, 2000))[0] or 2000
        sizes = [e.get("pt") for e in texts]
        leg = legibility(frame)
        if any(s is None for s in sizes) or leg is None or leg["ok"] is None:
            out["text_legible_340"] = _check(None, "a line of type has no recorded size")
        else:
            scale = LEGIBILITY_PX / width
            head_px = round(max(sizes) * scale, 1)
            small_px = round(min(sizes) * scale, 1)
            under = sorted({s for s in sizes if s < MIN_TEXT_PT})
            failing = leg["essential_failing"]
            ok = head_px >= MIN_LEGIBLE_TEXT_PX and not under and not failing
            why = (f"headline {head_px}px at {LEGIBILITY_PX}px (floor {MIN_LEGIBLE_TEXT_PX}px)"
                   + (f"; lines set under {MIN_TEXT_PT}pt: {under}" if under else "")
                   + (f"; essential text below the floor at its display size: "
                      + ", ".join(f"{ln['text']!r} {ln['px']}px at {ln['display_px']}px"
                                  for ln in failing) if failing else
                      f"; every essential line >= {MIN_LEGIBLE_TEXT_PX}px where shown "
                      f"(smallest {leg['smallest_essential_px']}px)")
                   + (f"; secondary below the floor (reported): "
                      f"{len(leg['secondary_below_floor'])}"
                      if leg["secondary_below_floor"] else ""))
            out["text_legible_340"] = _check(
                ok, why[:400], headline_px=head_px, smallest_px=small_px,
                smallest_essential_px=leg["smallest_essential_px"],
                essential_failing=[{k: ln[k] for k in ("text", "slot", "px", "display_px")}
                                   for ln in failing],
                secondary_below_floor=[{k: ln[k] for k in ("text", "slot", "px")}
                                       for ln in leg["secondary_below_floor"]])

    # 3. No misleading scale.
    scale_bad = [f"{f.code}" for f in mine if f.code.startswith(_SCALE_CODES)]
    if frame.role == "size" and not getattr(frame, "scale_shown", ""):
        scale_bad.append("size card draws no measurement or scale reference")
    out["scale_not_misleading"] = _check(
        not scale_bad, "; ".join(scale_bad) if scale_bad else
        ("the size card's scale is drawn and agrees with the twin" if frame.role == "size"
         else "no size or scale claim on this frame disagrees with the twin"))

    # 4. No third-party marks: the blind describer's answer. `unclear` or no answer is
    # unanswered, not "none".
    raw = (description or {}).get("third_party_marks") if description else None
    answered = raw is not None and str(raw).strip().lower() not in ("", "unclear")
    if not description or not answered:
        out["no_third_party_marks"] = _check(
            None, "the describer did not answer whether third-party marks are present")
    else:
        marks = marks_found(description)
        out["no_third_party_marks"] = _check(not marks, f"marks seen: {marks}" if marks
                                             else "the describer saw none")

    # 5. Disclosure present. Every non-photo frame is recorded with its buyer's provenance
    # (#36) as a simulated render, never proof. A frame that draws the product must also say
    # so in its own pixels.
    kind = "chart_render" if frame.role == "chart" else buyer_trust._FRAME_KIND.get(
        str(getattr(frame.asset_class, "value", frame.asset_class)))
    nature = buyer_trust.IMAGE_KINDS.get(kind, (None,))[0] if kind else None
    if nature != buyer_trust.SIMULATED:
        out["disclosure_present"] = _check(
            False, f"no simulated-render provenance kind for this frame (kind {kind!r})")
    elif visual_role == DISCLOSED_RENDER:
        if texts is None:
            out["disclosure_present"] = _check(None, "no recorded layout to read the "
                                                     "drawn disclosure from")
        else:
            # One line, or the disclosure lines read together (the hero sets it on two).
            joined = " ".join(str(e.get("text") or "") for e in texts
                              if e.get("slot") == "disclosure").lower()
            drawn = (any(DRAWN_DISCLOSURE in str(e.get("text") or "").lower() for e in texts)
                     or DRAWN_DISCLOSURE in joined)
            out["disclosure_present"] = _check(
                drawn, f"provenance {kind} (simulated); drawn {DRAWN_DISCLOSURE!r}: {drawn}")
    else:
        out["disclosure_present"] = _check(
            True, f"recorded as {kind} (simulated, never proof) in the image provenance; the "
                  f"frame does not draw the product as an object")
    return out


def verdict(*, described: bool, semantic_problems, marks, checks: dict[str, dict]) -> dict:
    """blocked / unjudged / clear for a non-photo frame. Unanswered is never passed."""
    failed = sorted(k for k, v in checks.items() if v.get("passed") is False)
    unanswered = sorted(k for k, v in checks.items() if v.get("passed") is None)
    missing = sorted(set(ROLE_CHECKS) - set(checks))
    if semantic_problems or marks or failed:
        return {"verdict": "blocked", "failed_role_checks": failed,
                "why": ("; ".join([f"{k}: {checks[k]['why']}" for k in failed]
                                  + [str(p.get("check") if isinstance(p, dict) else p)
                                     for p in (semantic_problems or [])]
                                  + ([f"marks {marks}"] if marks else [])))[:400]}
    if not described or unanswered or missing:
        return {"verdict": "unjudged", "unmade": unanswered + missing
                + ([] if described else ["description"]),
                "why": "role checks not answered are not passed: "
                       f"{unanswered + missing + ([] if described else ['description'])}"}
    return {"verdict": "clear", "failed_role_checks": [],
            "why": "every role check was made and passed, and the frame says what it claims"}
