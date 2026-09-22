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
  PRODUCT TRUTH         the motif judge, comparing the fabric against the deterministically
                        rendered chart rather than against a sentence about it.
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


def assess(frames: list[dict], *, benchmark_quality: dict | None = None) -> dict:
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

    # 2. PRODUCT TRUTH -- every frame showing the object, against the chart.
    showing = [f for f in frames if f.get("motif") is not None]
    if not showing:
        results[PRODUCT_TRUTH] = _verdict(None, "no frame was compared against the chart")
    else:
        motifs = [str((f.get("motif") or {}).get("verdict") or "") for f in showing]
        if any(m == "mismatch" for m in motifs):
            results[PRODUCT_TRUTH] = _verdict(
                False, "the fabric is not the pattern's fabric on at least one frame")
        elif all(m == "match" for m in motifs):
            results[PRODUCT_TRUTH] = _verdict(True, f"{len(showing)} frame(s) match")
        else:
            results[PRODUCT_TRUTH] = _verdict(
                None, f"the fabric could not be read on at least one frame: {motifs}")

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
    judged = [f for f in frames if f.get("photographic_realism") is not None]
    if not judged:
        results[LIFESTYLE_QUALITY] = _verdict(
            None, "no frame was judged against the photography standard")
    else:
        states = [str((f.get("photographic_realism") or {}).get("verdict") or "")
                  for f in judged]
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
        results[COMPETITIVE] = _verdict(None, "the comparison did not reach a verdict")

    if set(results) != set(DIMENSIONS):
        raise ParityRefused(
            f"parity was computed from {sorted(results)} rather than all eight of "
            f"{sorted(DIMENSIONS)}. A partial set cannot satisfy #75")

    failed = [d for d in DIMENSIONS if results[d]["verdict"] == FAIL]
    unjudged = [d for d in DIMENSIONS if results[d]["verdict"] == UNJUDGED]
    return {
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
