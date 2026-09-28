"""The eight-part creative parity gate (#75), all eight of it.

The requirement names eight checks that must *independently* pass before listing export,
and says any failure blocks release. Four of them already existed as real gates and four
did not, and the tempting move -- report the four that exist, call the requirement mostly
met -- is the averaging this requirement is written against. Eight checks where four are
imaginary is a four-check gate with a better name.

So this runs all eight, each against its own evidence, and refuses to produce a verdict at
all from a partial set: a dimension nobody judged is `unjudged`, and `unjudged` blocks
exactly as `fail` does. That is the difference between "we checked and it is fine" and "we
did not check", and a listing that ships on the second is shipping on nothing.

Where each answer comes from, and none of it is new opinion:

  IDENTITY              `identity.drift_check` against the frozen pack -- face and
                        whole-person morphology, which are themselves two floors that
                        never average into one another.
  PRODUCT TRUTH         independent construction evidence; motif labels and preservation
                        alone cannot certify the product being depicted.
  HERO                  whether the frame communicates a finished object at a glance,
                        read off the blind description rather than asserted by the brief.
  MOBILE GRID           legibility at Etsy's search-thumbnail scale, which is where the
                        buying decision actually starts.
  LIFESTYLE QUALITY     the natural-photography standard, which is a gate of its own.
  GALLERY               the sequence: every frame doing a declared job, no filler, and the
                        evidence frames present.
  BRAND                 recognisably Brambleloop -- the identity being the *same* one
                        across the set, which is a property of the gallery rather than of
                        any single frame.
  COMPETITIVE           not materially inferior beside the benchmark listings this company
                        actually observed.

Two of these can be answered without asking anybody anything, and that is deliberate:
GALLERY and BRAND are structural, and a structural question answered by a vision model is
an opinion where a fact was available.
"""
from __future__ import annotations

IDENTITY = "identity"
PRODUCT_TRUTH = "product_truth"
HERO = "hero"
MOBILE_GRID = "mobile_grid"
LIFESTYLE_QUALITY = "lifestyle_quality"
GALLERY = "gallery"
BRAND = "brand"
COMPETITIVE = "competitive_blind_review"

DIMENSIONS: tuple[str, ...] = (IDENTITY, PRODUCT_TRUTH, HERO, MOBILE_GRID,
                               LIFESTYLE_QUALITY, GALLERY, BRAND, COMPETITIVE)

PASS = "pass"
FAIL = "fail"
UNJUDGED = "unjudged"

WHAT: dict[str, str] = {
    IDENTITY: "the correct Brambleloop model, where a frame carries her at all",
    PRODUCT_TRUTH: "the crochet shown is the crochet the certified pattern makes",
    HERO: "a buyer understands the finished result immediately",
    MOBILE_GRID: "the frame still reads at Etsy search-thumbnail scale",
    LIFESTYLE_QUALITY: "premium lighting, composition and material realism",
    GALLERY: "a complete purposeful sequence with no filler",
    BRAND: "recognisably Brambleloop across the set",
    COMPETITIVE: "not materially inferior beside the observed benchmark listings",
}


class ParityRefused(ValueError):
    """A parity verdict computed from fewer than eight dimensions."""


def _verdict(ok: bool | None, why: str) -> dict:
    return {"verdict": PASS if ok is True else FAIL if ok is False else UNJUDGED,
            "why": why}


def _deterministic_available(frames: list[dict]) -> bool:
    """Whether a deterministic representation of this product is on file.

    A chart frame, or any frame recorded as deterministic, is a render of the certified CIR
    rather than a generated picture of it -- the one rung of #81 that costs nothing.
    """
    return any(f.get("role") == "chart" or f.get("deterministic") is True
               or f.get("kind") in ("chart_render", "twin_render") for f in frames)



def _realism_of(frame: dict) -> dict | None:
    """The photography-standard verdict a frame carries, wherever its writer put it.

    `model_photography` records a top-level `photographic_realism` block; `owned_photography`
    (every product-first frame) records the same judgement as named checks under
    `inspection.realism` and never wrote the top-level field. Parity read only the first, so
    every flat product read as unjudged and LIFESTYLE_QUALITY could never pass for any of
    them (found 2026-09-27, Build 2 closeout). The named checks are mapped conservatively:
    any check failed is `blocked`; `clear` only when the realism judge ran and every check it
    asked was answered and passed; anything else stays unjudged.
    """
    top = frame.get("photographic_realism")
    if top is not None:
        return top
    inspection = frame.get("inspection") or {}
    checks = inspection.get("realism")
    if not inspection.get("realism_judged") or not isinstance(checks, dict) or not checks:
        return None
    answers = list(checks.values())
    if any(a is False for a in answers):
        return {"verdict": "blocked", "from": "inspection.realism", "checks": checks}
    if all(a is True for a in answers):
        return {"verdict": "clear", "from": "inspection.realism", "checks": checks}
    return {"verdict": "unjudged", "from": "inspection.realism", "checks": checks}

def assess(frames: list[dict], *, benchmark_quality: dict | None = None,
           deterministic_available: bool | None = None,
           gate_open: dict[str, bool] | None = None, start_attempt: int = 0) -> dict:
    """Judge all eight from evidence already gathered. Never renders, never asks again.

    `frames` are asset records -- what `model_photography.make` and
    `owned_photography.make` produce -- so every per-frame answer is a reading of evidence
    that already exists rather than a fresh opinion about the same picture.
    """
    results: dict[str, dict] = {}
    modelled = [f for f in frames if f.get("carries_model")]

    # 1. IDENTITY -- only where a frame carries her. A product-only gallery is not
    # failing this; it is not being asked, which is a different answer.
    if not frames:
        results[IDENTITY] = _verdict(None, "no frames to judge")
    elif not modelled:
        results[IDENTITY] = _verdict(
            True, "no frame carries the model, so there is no identity to be wrong")
    else:
        verdicts = [str((f.get("identity") or {}).get("verdict") or "") for f in modelled]
        if any(v == "fail" for v in verdicts):
            results[IDENTITY] = _verdict(False, f"identity drifted: {verdicts}")
        elif all(v == "pass" for v in verdicts):
            results[IDENTITY] = _verdict(True, f"{len(modelled)} model frame(s) verified")
        else:
            results[IDENTITY] = _verdict(
                None, f"identity unverified on at least one frame: {verdicts}")

    # F-752/F-760/F-856: motif labels cannot satisfy structural product truth.
    # Evaluate every exported frame; omitted motif metadata is not an exemption.
    from .product_authority import structural_floor
    structures = [structural_floor(frame) for frame in frames]
    if any(v["status"] == "FAIL" for v in structures):
        results[PRODUCT_TRUTH] = _verdict(False, "structural product truth failed on an exported frame")
    elif structures and all(v["status"] == "PASS" for v in structures):
        results[PRODUCT_TRUTH] = _verdict(True, "all exported frames independently structurally verified")
    else:
        results[PRODUCT_TRUTH] = _verdict(None, "whole-product construction/stitch/gauge evidence UNKNOWN; motif match or preserved schematic is insufficient")

    # 3. HERO -- read off the blind description, not asserted.
    hero = next((f for f in frames if (f.get("role") or "hero") == "hero"), None)
    if hero is None:
        results[HERO] = _verdict(None, "no hero frame in the set")
    else:
        described = ((hero.get("inspection") or {}).get("described"))
        description = ((hero.get("inspection") or {}).get("semantic") or {})
        finished = description.get("finished_or_in_progress_agrees")
        if described is not True:
            results[HERO] = _verdict(None, "the hero frame was never described")
        elif finished is False:
            results[HERO] = _verdict(
                False, "the hero frame does not read as a finished object")
        elif finished is True:
            results[HERO] = _verdict(True, "the hero frame reads as the finished object")
        else:
            results[HERO] = _verdict(
                None, "whether the hero shows a finished object was not established")

    # 4. MOBILE GRID -- a fact about the frame, recorded when it was built.
    grid = [f.get("readable_at_grid") for f in frames]
    if not grid or all(g is None for g in grid):
        results[MOBILE_GRID] = _verdict(
            None, "no frame was checked at search-thumbnail scale")
    elif any(g is False for g in grid):
        results[MOBILE_GRID] = _verdict(False, "a frame does not read in the mobile grid")
    elif any(g is None for g in grid):
        results[MOBILE_GRID] = _verdict(
            None, "at least one frame was not checked at grid scale")
    else:
        results[MOBILE_GRID] = _verdict(True, "every frame reads at grid scale")

    # 5. LIFESTYLE QUALITY -- the natural-photography standard.
    judged = [f for f in frames if _realism_of(f) is not None]
    if not judged:
        results[LIFESTYLE_QUALITY] = _verdict(
            None, "no frame was judged against the photography standard")
    else:
        states = [str((_realism_of(f) or {}).get("verdict") or "") for f in judged]
        if any(s == "blocked" for s in states):
            results[LIFESTYLE_QUALITY] = _verdict(
                False, "a frame reads as generated rather than photographed")
        elif all(s == "clear" for s in states):
            results[LIFESTYLE_QUALITY] = _verdict(
                True, f"{len(judged)} frame(s) read as believable photography")
        else:
            results[LIFESTYLE_QUALITY] = _verdict(
                None, f"the photography standard could not be judged: {states}")

    # 6. GALLERY -- structural, so answered structurally.
    from .gallery import JOBS

    if not frames:
        results[GALLERY] = _verdict(None, "no gallery to judge")
    else:
        roles = [f.get("role") for f in frames]
        unknown = [r for r in roles if r is not None and r not in JOBS]
        no_role = [r for r in roles if r is None]
        if unknown:
            results[GALLERY] = _verdict(False, f"frames with no declared job: {unknown}")
        elif no_role:
            results[GALLERY] = _verdict(
                None, f"{len(no_role)} frame(s) carry no role, so filler cannot be ruled out")
        elif not any(JOBS.get(r) == "engineering_evidence" for r in roles):
            results[GALLERY] = _verdict(
                False, "the sequence carries no engineering-evidence frame")
        else:
            results[GALLERY] = _verdict(
                True, f"{len(frames)} frames, each doing a declared job")

    # 7. BRAND -- one identity across the set, which is a property of the set.
    if not modelled:
        results[BRAND] = _verdict(
            True, "a product-only set is Brambleloop by its pattern and its chart")
    else:
        packs = {(f.get("conditioned_on") or {}).get("pack_version") for f in modelled}
        packs.discard(None)
        if not packs:
            results[BRAND] = _verdict(
                None, "no model frame records which identity it was conditioned on")
        elif len(packs) > 1:
            results[BRAND] = _verdict(
                False, f"the set uses more than one identity: {sorted(packs)}")
        else:
            results[BRAND] = _verdict(
                True, f"every model frame conditioned on pack version {packs.pop()}")

    # 8. COMPETITIVE -- against observation, or unjudged. Never assumed favourable.
    if not benchmark_quality:
        results[COMPETITIVE] = _verdict(
            None, ("no benchmark comparison has been made, and assuming this company "
                   "compares well is the one answer nobody has evidence for"))
    elif benchmark_quality.get("materially_inferior") is True:
        results[COMPETITIVE] = _verdict(
            False, str(benchmark_quality.get("why") or "materially inferior"))
    elif benchmark_quality.get("materially_inferior") is False:
        results[COMPETITIVE] = _verdict(
            True, str(benchmark_quality.get("why") or "not materially inferior"))
    else:
        # A stale or refused comparison says why; that reason is the actionable part.
        results[COMPETITIVE] = _verdict(
            None, str(benchmark_quality.get("why") or "the comparison did not reach a verdict"))

    if set(results) != set(DIMENSIONS):
        raise ParityRefused(
            f"parity was computed from {sorted(results)} rather than all eight of "
            f"{sorted(DIMENSIONS)}. A partial set cannot satisfy #75")

    failed = [d for d in DIMENSIONS if results[d]["verdict"] == FAIL]
    unjudged = [d for d in DIMENSIONS if results[d]["verdict"] == UNJUDGED]

    # The hand-off to #81. A failure used to stop at `blocks_release`; it now carries the
    # ladder it walks next, recorded wherever this verdict is. Unjudged is not routed: the
    # answer to "nobody looked" is to look, not to regenerate.
    escalation = None
    if failed:
        from .gallery import escalation_plan

        available = (deterministic_available if deterministic_available is not None
                     else _deterministic_available(frames))
        # C-80 defect 8: the walk starts where the persisted rung results left it, so a
        # rung already attempted without a usable frame is not taken again.
        escalation = escalation_plan(failed, deterministic_available=available,
                                     gate_open=gate_open, start_attempt=int(start_attempt))

    return {
        "escalation": escalation,
        "dimensions": results,
        "judged": len(DIMENSIONS) - len(unjudged),
        "of": len(DIMENSIONS),
        "failed": failed,
        "unjudged": unjudged,
        "verdict": FAIL if failed else UNJUDGED if unjudged else PASS,
        "blocks_release": bool(failed or unjudged),
        "why": (f"parity failed on {failed}" if failed else
                f"parity is unjudged on {unjudged}, and unjudged is not a pass"
                if unjudged else "all eight parity dimensions pass"),
        "never_averaged": (
            "eight independent dimensions, and any one failing blocks release. There is "
            "no score here and no majority: reporting the four that were built as though "
            "they were the whole gate is the averaging this requirement exists to refuse"),
    }
