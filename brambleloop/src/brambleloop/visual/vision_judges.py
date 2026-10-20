"""Blind, structured vision-judge adapters for generated listing images (W-VISNEXT; OWNERIMG E2).

Every check that needs eyes is asked here, and every one follows the same three rules:

1. **Blind.** The question never states the expected answer. The judge is not told the
   reserved outfit, the pattern's palette, edging or craft, or that the person "should be"
   Laura. Comparison questions (identity, body) show the canonical references and ask, per
   dimension, whether two people are the same; they never say which answer is wanted.
2. **Structured, compared in code.** The judge returns one JSON object in a closed
   vocabulary. This module compares that reading against the certified CIR
   (`visual.fidelity.Expectation`), the wardrobe registry (`visual.outfits`,
   `visual.wardrobe`) or the identity rule (`visual.identity_gate.assess`). Deterministic
   comparison decides; the judge only reports what it saw.
3. **Budget-reserved, UNKNOWN when it cannot be asked.** The transport is the existing
   vision judge interface, `read(prompt, images, *, system, max_tokens)` ->
   {"answered", "reading", "why"}. In production that is `fidelity.GatewayVisionJudge`:
   gated on `image_vision`, reserved through `gateway.anthropic.check_budget` before the
   call and billed after it. Gate closed, budget refused, provider down or an unparseable
   answer: the check reads UNKNOWN. UNKNOWN is never PASS.

| check | images | compared against | FAIL code / category |
|---|---|---|---|
| identity | 3 canonical references + candidate, two independent judges | `identity_gate.assess` (conditioning receipt, judge pair, biometric floor) | identity_drift |
| body_proportions | the same readings, morphology group | `identity._group_verdict` (bust and torso required) | body_proportion_drift |
| outfit_consistency | candidate | the listing's reserved outfit, per slot (5 slots); the reference clothing; other listings' outfits | outfit_consistency, REFERENCE_CLOTHING_CARRYOVER, WARDROBE_REPETITION |
| anatomy | candidate | one person in a Laura frame; five fingers on every fully visible hand; no defect | anatomy |
| realism | candidate | `gallery.REALISM_CHECKS` defects, plus render/illustration and text | realism |
| craft_texture | candidate | `fidelity.compare_craft` (already in `visual.fidelity`) | WRONG_CRAFT_TEXTURE |
| anchor_consistency | anchor + candidate, each described separately | each other and the CIR (craft, edging, end bands, cables, colour count) | INVENTED_EDGING, INVENTED_END_BAND_TREATMENT, WRONG_CRAFT_TEXTURE, WRONG_COLOUR_LAYOUT |
| product region | candidate | interior fabric patches located by the judge; the palette is then measured in code | (feeds `fidelity.verify_lifestyle` region_palette) |

Independence: identity and body proportions need two readings from two *different* judges
(different transport name or model). One judge can refuse (any drift is a FAIL) but never
pass. Identity additionally needs the biometric floor, which no qualified embedder provides
in this build (`identity_gate.QUALIFIED_EMBEDDERS` is empty), so identity tops out at the
REVIEW band (UNKNOWN). That is the honest state.

Nothing here generates, publishes, or relaxes a gate.
"""
from __future__ import annotations

import hashlib
import json

from ..creative import failure_codes as FC

VERSION = "vision-judges/1.0.0"
PASS, FAIL, UNKNOWN, NA = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"

SYSTEM = ("You are a careful visual inspector. Report only what the picture shows. When you "
          "cannot tell, say so with the 'cannot_tell' or 'unclear' option. Reply with one JSON "
          "object and nothing else.")

# Answer vocabularies. Closed, so a reading cannot smuggle in a verdict.
SAME, DIFFERENT, CANNOT_TELL = "same", "different", "cannot_tell"
YES, NO, UNCLEAR = "yes", "no", "unclear"


def _c(check: str, status: str, why: str, **kw) -> dict:
    return {"check": check, "status": status, "why": str(why)[:400], "checker": VERSION, **kw}


def _tri(v) -> bool | None:
    """yes/true -> True, no/false -> False, anything else (unclear, missing) -> None."""
    if isinstance(v, bool):
        return v
    s = str(v if v is not None else "").strip().lower()
    if s in ("yes", "true", "y"):
        return True
    if s in ("no", "false", "n"):
        return False
    return None


def _int(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    t = str(v if v is not None else "").strip()
    return int(t) if t.isdigit() else None


def judge_id(judge, answer: dict | None = None) -> str:
    """A judge's identity for independence: transport name plus the model that answered."""
    name = str(getattr(judge, "name", "") or type(judge).__name__)
    model = str((answer or {}).get("model") or getattr(getattr(judge, "provider", None),
                                                          "model", "") or "")
    return f"{name}:{model}" if model else name


def ask(judge, task: str, prompt: str, images: list[bytes], *, max_tokens: int = 500) -> dict:
    """One blind question through the judge transport. Never raises.

    Returns {"answered": bool, "reading": dict | None, "why": str, "judge": id}. The
    transport does the gating and the budget reservation; an unanswered read is UNKNOWN."""
    if judge is None:
        return {"answered": False, "reading": None, "judge": None,
                "why": "no vision judge is configured"}
    if not images or any(not b for b in images):
        return {"answered": False, "reading": None, "judge": judge_id(judge),
                "why": "an image this question needs is missing"}
    try:
        got = judge.read(f"Task: {task}\n" + prompt, list(images), system=SYSTEM,
                         max_tokens=max_tokens) or {}
    except Exception as exc:  # noqa: BLE001 - an unmade reading is UNKNOWN, never PASS
        return {"answered": False, "reading": None, "judge": judge_id(judge),
                "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if not got.get("answered"):
        return {"answered": False, "reading": None, "judge": judge_id(judge, got),
                "why": str(got.get("why") or "not answered")[:300]}
    reading = got.get("reading")
    if isinstance(reading, str):
        try:
            reading = json.loads(reading)
        except ValueError:
            reading = None
    if not isinstance(reading, dict) or not reading or "_unread" in reading:
        return {"answered": False, "reading": None, "judge": judge_id(judge, got),
                "why": "the answer was not the requested JSON object"}
    return {"answered": True, "reading": reading, "judge": judge_id(judge, got), "why": ""}


# ---- identity and body proportions ----------------------------------------------------------

def person_prompt(order: str) -> str:
    """Per-dimension comparison of one photographed person with the reference woman.

    `order` "refs_first": images 1-3 are the references, image 4 the photograph;
    "photo_first": image 1 is the photograph, images 2-4 the references. The second judge gets
    the other order, so a position bias cannot be shared."""
    from . import identity

    if order == "refs_first":
        layout = ("Images 1, 2 and 3 are reference photographs of one woman (1: face portrait, "
                  "2: torso, 3: full length). Image 4 is another photograph.")
        other = "image 4"
    else:
        layout = ("Image 1 is a photograph. Images 2, 3 and 4 are reference photographs of one "
                  "woman (2: face portrait, 3: torso, 4: full length).")
        other = "image 1"
    dims = ", ".join(identity.DRIFT_DIMENSIONS)
    return (f"{layout}\nFor each dimension below, compare the person in {other} with the "
            f"reference woman and answer exactly one of: \"same\", \"different\", "
            f"\"cannot_tell\". Use \"cannot_tell\" whenever clothing, pose, crop, angle or "
            f"blur hides the dimension. Clothing, make-up and expression are not identity; "
            f"judge the person, not the outfit.\n"
            f"Dimensions: {dims}. (stylisation: whether the person is rendered in the same "
            f"photographic style rather than as an illustration or a different-looking "
            f"render.)\n"
            f"Reply with one JSON object whose keys are exactly those dimensions, plus "
            f"\"people_in_photograph\": the number of people in {other}.")


def _scored(reading: dict) -> dict:
    """Closed answers to the identity vocabulary (match / drift / unmeasurable)."""
    from . import identity

    m = {SAME: identity.MATCH, DIFFERENT: identity.DRIFT}
    out = {}
    for d in identity.DRIFT_DIMENSIONS:
        v = str(reading.get(d, CANNOT_TELL)).strip().lower().replace(" ", "_")
        out[d] = m.get(v, identity.UNMEASURABLE)
    return out


def canonical_reference_bytes() -> dict:
    """The current revision's three reference frames, verified by sha256 ('' if not)."""
    from pathlib import Path

    from . import canonical

    out = {}
    for frame, want in canonical.CURRENT_REFERENCE_HASHES.items():
        path = canonical.reference_file(frame)
        data = Path(path).read_bytes() if path else b""
        out[frame] = data if data and hashlib.sha256(data).hexdigest() == want else b""
    return out


REF_ORDER = ("neutral_portrait", "torso_fit_reference", "full_length_standing")


def person_readings(judges: list, data: bytes, refs: dict) -> list[dict]:
    """One person reading per distinct judge (first two), alternating image order."""
    readings, seen = [], set()
    ref_list = [refs.get(f) or b"" for f in REF_ORDER]
    for i, j in enumerate([j for j in judges if j is not None][:2]):
        order = "refs_first" if i == 0 else "photo_first"
        imgs = ref_list + [data] if order == "refs_first" else [data] + ref_list
        got = ask(j, "identity_morphology", person_prompt(order), imgs, max_tokens=400)
        jid = got["judge"]
        if jid in seen:      # the same judge twice is one reading, not two
            continue
        seen.add(jid)
        readings.append({**got, "order": order,
                         "scored": _scored(got["reading"]) if got["answered"] else None})
    return readings


def conditioning_of(cand: dict, size_of) -> dict:
    """The conditioning receipt for `identity_gate`, from the generator's stage receipt.

    The receipt (`creative.image_stages`) names every reference sent by sha256 and whether the
    request body was proven to carry them (`request.conditioning_proven`, measured by
    `gateway.images.conditioning_receipt`). Byte counts are measured here from the stored
    bytes of each named reference (`size_of(sha)`); a reference whose bytes cannot be found
    counts 0 and the trial is invalid. Without a receipt nothing is proven."""
    ev = dict(cand.get("identity_evidence") or {})
    if isinstance(ev.get("conditioning"), dict):
        return ev["conditioning"]
    named = [r.get("sha256") for r in ev.get("references") or [] if isinstance(r, dict)]
    proven = bool((ev.get("request") or {}).get("conditioning_proven"))
    if not named:
        named = [r.get("sha256") for r in cand.get("references") or []
                 if r.get("kind") == "laura_canonical"]
        proven = False
    return {"references": [{"sha256": s_, "bytes": int(size_of(s_) or 0)} for s_ in named
                           if s_], "proven": proven}


def identity_check(cand: dict, readings: list[dict], *, size_of=lambda sha: 0) -> dict:
    """`identity_gate.assess` on the conditioning receipt and the blind judge readings.

    Generator-supplied judge readings are never used (a generator does not grade itself);
    only its conditioning receipt, which proves which reference bytes were sent."""
    from . import identity_gate

    ev = dict(cand.get("identity_evidence") or {})
    evidence = {"conditioning": conditioning_of(cand, size_of),
                "non_identity_references": ev.get("non_identity_references") or [
                    r.get("sha256") for r in cand.get("references") or []
                    if r.get("kind") != "laura_canonical" and r.get("sha256")],
                "biometric": ev.get("biometric"),
                "judges": [{"judge": r["judge"], "scored": r["scored"]} for r in readings
                           if r.get("answered") and r.get("scored")]}
    g = identity_gate.assess(evidence)
    unread = [f"{r.get('judge') or 'judge'}: {r['why']}" for r in readings
              if not r.get("answered")]
    why = g["why"] + (f" (unanswered: {'; '.join(unread)})" if unread else "")
    return _c("identity", g["status"], why, band=g.get("band"),
              validity=(g.get("validity") or {}).get("validity"),
              judges=[r.get("judge") for r in readings if r.get("answered")],
              failed=g.get("failed") or [])


def body_check(readings: list[dict]) -> dict:
    """Morphology (bust, torso, ...) against the canonical torso and full-length frames.

    Any judge reading drift is a FAIL. PASS needs two distinct judges whose morphology group
    each passes (`identity._group_verdict`: >= 3 readable dimensions, bust and torso among
    them). Anything less is UNKNOWN."""
    from . import identity

    answered = [r for r in readings if r.get("answered") and r.get("scored")]
    groups = [{"judge": r["judge"], **identity._group_verdict(
        r["scored"], identity.MORPHOLOGY_DIMENSIONS, identity.MIN_MEASURABLE["morphology"],
        identity.REQUIRED_MEASURABLE["morphology"])} for r in answered]
    drifted = sorted({d for g in groups for d in g["drifted"]})
    if drifted:
        return _c("body_proportions", FAIL, f"body proportions differ from the canonical "
                                            f"torso/full-length references on {drifted}",
                  drifted=drifted, groups=groups)
    if not groups:
        why = "; ".join(r["why"] for r in readings) or "no reading"
        return _c("body_proportions", UNKNOWN, f"not judged: {why}", groups=[])
    unverifiable = [g["judge"] for g in groups if g["verdict"] != "pass"]
    if unverifiable:
        return _c("body_proportions", UNKNOWN,
                  f"morphology not readable enough (bust and torso required, >= "
                  f"{identity.MIN_MEASURABLE['morphology']} dimensions) for {unverifiable}",
                  groups=groups)
    if len(groups) < 2:
        return _c("body_proportions", UNKNOWN, "one judge read every readable dimension as "
                                               "the same; two independent readings are "
                                               "required for a pass", groups=groups)
    return _c("body_proportions", PASS, "two independent judges read bust, torso and the "
                                        "readable morphology as the canonical woman",
              groups=groups)


# ---- outfit consistency (five slots) ---------------------------------------------------------

def _slot_vocab():
    from . import wardrobe as W

    cats = {s: [c for c, _ in W._CATEGORIES[s]] for s in W.SLOTS}
    return cats, sorted(W._COLOUR_FAMILY), list(W._FEATURES)


def outfit_prompt() -> str:
    from . import wardrobe as W

    cats, colours, feats = _slot_vocab()
    lines = []
    for s in W.SLOTS:
        lines.append(f"- {s}: {{\"visible\": \"yes\"|\"no\"|\"unclear\", \"garment\": one of "
                     f"{cats[s] + ['none', 'other']}, \"colour\": one of "
                     f"{colours + ['other', 'unclear']}, \"features\": a list chosen from "
                     f"{feats}}}")
    return ("Describe what the person in this image is wearing. Do not describe any crochet "
            "or knitted item they hold or wear as part of the product; describe their "
            "clothing. A slot hidden by crop, pose or the product is \"visible\": \"no\". "
            "Reply with one JSON object with the key \"person_present\" (\"yes\"|\"no\") and "
            "one key per slot:\n" + "\n".join(lines))


def _observed_text(slot: str, obs: dict) -> str:
    """The observed garment as wardrobe text, so `wardrobe.parse_garment` reads it back."""
    from . import wardrobe as W

    g = str(obs.get("garment") or "").strip().lower()
    if g in ("", "none"):
        return "none"
    kw = dict(W._CATEGORIES[slot]).get(g)
    noun = kw[0] if kw else g
    colour = str(obs.get("colour") or "").strip().lower()
    colour = colour if colour in W._COLOUR_FAMILY else ""
    feats = [f for f in obs.get("features") or [] if f in W._FEATURES]
    # The noun first: a feature word before it ("pleated trousers") could otherwise be read
    # back as another category by `parse_garment`'s substring keys.
    return " ".join([noun, colour] + feats).strip()


def _visible_similarity(observed: dict, other: dict, visible: list[str]) -> float | None:
    """Weighted outfit similarity over the visible slots only (renormalised)."""
    from . import wardrobe as W

    w = sum(W.WEIGHTS[s] for s in visible)
    if w < 0.45:          # less than top + lower in view: too little to call a repeat
        return None
    pa, pb = W.parse_outfit(observed), W.parse_outfit(other)
    return round(sum(W.WEIGHTS[s] * W.slot_similarity(pa[s], pb[s]) for s in visible) / w, 4)


def compare_outfit(reading: dict, reserved: dict, *, others: list[tuple[str, dict]] = ()) -> dict:
    """The blind clothing description against the reserved outfit, slot by slot.

    FAIL REFERENCE_CLOTHING_CARRYOVER when the visible clothing is the canonical references'
    clothing; FAIL WARDROBE_REPETITION when it is another listing's outfit; FAIL (outfit
    consistency) when a visible slot is a different garment or colour family than reserved.
    PASS needs the top (or dress) and, unless it is a dress, the lower garment visible and
    matching; the other slots must match or be honestly out of view."""
    from . import wardrobe as W

    if _tri(reading.get("person_present")) is False:
        return _c("outfit_consistency", FAIL, "no person in a frame reserved for Laura",
                  slots={})
    want = W.parse_outfit(reserved.get("garments") or {})
    observed_text, slots, visible, mismatched, unclear = {}, {}, [], [], []
    for s in W.SLOTS:
        obs = reading.get(s) if isinstance(reading.get(s), dict) else {}
        vis = _tri(obs.get("visible"))
        observed_text[s] = _observed_text(s, obs) if vis else ""
        if vis is None:
            slots[s] = {"result": "unclear"}
            unclear.append(s)
            continue
        if vis is False:
            slots[s] = {"result": "not_shown"}
            continue
        got = W.parse_garment(s, observed_text[s])
        visible.append(s)
        cat_ok = got["category"] == want[s]["category"] or (
            str(obs.get("garment")).lower() == "other" and want[s]["category"] == "other")
        col = str(obs.get("colour") or "").lower()
        if want[s]["category"] == "none" or got["category"] == "none" or \
                not want[s]["colours"]:
            col_ok = True       # nothing declared to contradict (or nothing worn)
        elif col in ("", "unclear"):
            col_ok = None
        else:
            col_ok = W._colour_score(got["colours"], want[s]["colours"]) > 0
        res = ("match" if cat_ok and col_ok else "mismatch" if not cat_ok or col_ok is False
               else "unclear")
        slots[s] = {"result": res, "observed": observed_text[s] or "none",
                    "reserved": want[s]["text"] or "none"}
        if res == "mismatch":
            mismatched.append(s)
        elif res == "unclear":
            unclear.append(s)
    sim_ref = _visible_similarity(observed_text, W.REFERENCE_OUTFIT, visible)
    if sim_ref is not None and sim_ref >= W.MAX_SIMILARITY:
        return _c("outfit_consistency", FAIL, f"REFERENCE_CLOTHING_CARRYOVER: the visible "
                                              f"clothing is the canonical references' clothing "
                                              f"(similarity {sim_ref})",
                  codes=[FC.REFERENCE_CLOTHING_CARRYOVER], slots=slots, similarity=sim_ref)
    sim_res = _visible_similarity(observed_text, reserved.get("garments") or {}, visible)
    for name, other in others:
        sim = _visible_similarity(observed_text, other, visible)
        if sim is not None and sim >= W.MAX_SIMILARITY and (sim_res is None or sim > sim_res):
            return _c("outfit_consistency", FAIL, f"WARDROBE_REPETITION: the visible clothing "
                                                  f"is {name}'s outfit (similarity {sim})",
                      codes=[FC.WARDROBE_REPETITION], slots=slots, similarity=sim)
    if mismatched:
        return _c("outfit_consistency", FAIL, "the image does not show the reserved outfit: "
                  + "; ".join(f"{s} is {slots[s]['observed']!r}, reserved "
                              f"{slots[s]['reserved']!r}" for s in mismatched), slots=slots)
    dress = want["top_or_dress"]["category"] == "dress"
    needed = ["top_or_dress"] + ([] if dress else ["lower"])
    missing = [s for s in needed if slots.get(s, {}).get("result") != "match"]
    if missing or unclear:
        return _c("outfit_consistency", UNKNOWN,
                  f"cannot confirm the reserved outfit: {sorted(set(missing + unclear))} not "
                  f"readable as matching", slots=slots)
    return _c("outfit_consistency", PASS, "every visible slot shows the reserved outfit "
                                          "(" + ", ".join(f"{s}: {slots[s]['result']}"
                                                          for s in W.SLOTS) + ")",
              slots=slots)


# ---- anatomy and realism ---------------------------------------------------------------------

ANATOMY_DEFECTS = ("extra_limbs", "missing_limbs_not_explained_by_crop",
                   "fused_or_merged_body_parts", "impossible_joints", "face_distorted",
                   "hand_merged_with_object")


def anatomy_prompt() -> str:
    return ("Look at the people in this image. Reply with one JSON object with keys:\n"
            "- people: the number of people visible (integer)\n"
            "- hands: a list, one entry per hand you can see: {\"fully_visible\": "
            "\"yes\"|\"no\", \"fingers_counted\": an integer or \"unclear\"}\n"
            + "".join(f"- {d}: \"yes\"|\"no\"|\"unclear\"\n" for d in ANATOMY_DEFECTS))


def compare_anatomy(reading: dict, *, laura: bool) -> dict:
    people = _int(reading.get("people"))
    problems, unclear = [], []
    if people is None:
        unclear.append("people count unclear")
    elif laura and people != 1:
        problems.append(f"{people} people in a frame of one person")
    for d in ANATOMY_DEFECTS:
        v = _tri(reading.get(d))
        if v is True:
            problems.append(d)
        elif v is None and (people or 0) > 0:
            unclear.append(d)
    hands = reading.get("hands") if isinstance(reading.get("hands"), list) else None
    if hands is None and (people or 0) > 0:
        unclear.append("hands not reported")
    for i, h in enumerate(hands or []):
        h = h if isinstance(h, dict) else {}
        if _tri(h.get("fully_visible")) is True:
            n = _int(h.get("fingers_counted"))
            if n is None:
                unclear.append(f"hand {i + 1}: fingers not countable")
            elif n != 5:
                problems.append(f"hand {i + 1} has {n} fingers")
    if problems:
        return _c("anatomy", FAIL, "; ".join(problems), reading=reading)
    if unclear:
        return _c("anatomy", UNKNOWN, "; ".join(unclear), reading=reading)
    if not people:
        return _c("anatomy", PASS, "no person or hand in the frame", reading=reading)
    return _c("anatomy", PASS, f"{people} person, every fully visible hand has five fingers, "
                               f"no anatomical defect seen", reading=reading)


# One observable defect per `gallery.REALISM_CHECKS` entry, phrased as what a maker would see.
REALISM_DEFECTS = {
    "stitch_scale_plausible": "stitches_implausibly_large_or_small_for_the_item",
    "yarn_continuity": "yarn_strands_breaking_merging_or_ending_abruptly",
    "edge_construction": "fabric_edges_melting_or_undefined",
    "drape": "fabric_drape_physically_impossible",
    "joins_make_sense": "seams_or_joins_that_could_not_be_made",
    "hands_and_fingers": "hands_or_fingers_malformed",
    "garment_fit": "clothing_fit_physically_impossible",
    "shadows_consistent": "shadows_or_lighting_inconsistent",
    "texture_not_repeating": "texture_visibly_tiled_or_copy_pasted",
    "no_impossible_seams": "impossible_seams",
}
REALISM_EXTRA = ("looks_like_an_illustration_or_3d_render", "garbled_text_or_watermark")


def realism_prompt() -> str:
    keys = list(REALISM_DEFECTS.values()) + list(REALISM_EXTRA)
    return ("Inspect this image for visual defects. For each key answer \"yes\" (the defect "
            "is visible), \"no\" (it is not), \"unclear\", or \"not_applicable\" (nothing in "
            "the image it could apply to). Reply with one JSON object with exactly these "
            "keys:\n" + "\n".join(f"- {k}" for k in keys))


def compare_realism(reading: dict) -> dict:
    from .gallery import REALISM_CHECKS

    failed, unclear, per = [], [], {}
    for check in REALISM_CHECKS:
        key = REALISM_DEFECTS[check]
        raw = str(reading.get(key, "unclear")).strip().lower()
        v = None if raw == "not_applicable" else _tri(raw)
        per[check] = ("not_applicable" if raw == "not_applicable" else
                      "defect" if v is True else "ok" if v is False else "unclear")
        if v is True:
            failed.append(check)
        elif v is None and raw != "not_applicable":
            unclear.append(check)
    for key in REALISM_EXTRA:
        v = _tri(reading.get(key, "unclear"))
        per[key] = "defect" if v is True else "ok" if v is False else "unclear"
        if v is True:
            failed.append(key)
        elif v is None:
            unclear.append(key)
    if failed:
        return _c("realism", FAIL, f"visible defects: {failed}", checks=per)
    if unclear:
        return _c("realism", UNKNOWN, f"not readable: {unclear}", checks=per)
    return _c("realism", PASS, "no realism defect seen", checks=per)


# ---- anchor consistency (blind) and the product region ---------------------------------------

ITEM_FIELDS = ("item_visible", "craft", "border_or_edging_visible", "plain_end_bands_visible",
               "raised_cables_visible", "distinct_yarn_colours")


def item_prompt() -> str:
    one = ("{\"item_visible\": \"yes\"|\"no\", \"craft\": one of crochet, knitting, woven, "
           "printed, unclear, \"border_or_edging_visible\": \"yes\"|\"no\"|\"unclear\", "
           "\"plain_end_bands_visible\": \"yes\"|\"no\"|\"unclear\" (solid bands of one colour "
           "across the two ends), \"raised_cables_visible\": \"yes\"|\"no\"|\"unclear\", "
           "\"distinct_yarn_colours\": an integer or \"unclear\"}")
    return ("Each image contains a handmade textile item. Describe the item in each image on "
            "its own; do not compare them. Reply with one JSON object: {\"image_1\": "
            f"{one}, \"image_2\": the same keys for image 2}}.")


def _has_bands(exp) -> bool:
    return any(p.bands for p in getattr(exp, "pieces", []) or [])


def _has_cables(exp) -> bool:
    return any(p.repeat and "cable" in str(p.repeat.get("what", ""))
               for p in getattr(exp, "pieces", []) or [])


def compare_items(reading: dict, exp) -> dict:
    """Two independent descriptions (anchor, candidate) compared with each other and the CIR."""
    a = reading.get("image_1") if isinstance(reading.get("image_1"), dict) else None
    b = reading.get("image_2") if isinstance(reading.get("image_2"), dict) else None
    if a is None or b is None:
        return _c("anchor_consistency", UNKNOWN, "the reading did not describe both images")
    if _tri(b.get("item_visible")) is not True or _tri(a.get("item_visible")) is not True:
        return _c("anchor_consistency", UNKNOWN, "the item is not clearly visible in both "
                                                 "images", reading=reading)
    problems, unclear = [], []
    craft_b, craft_a = (str(b.get("craft", "unclear")).lower(),
                        str(a.get("craft", "unclear")).lower())
    if craft_b == "unclear":
        unclear.append("craft unclear in the candidate")
    elif craft_b != getattr(exp, "craft", "crochet") or (craft_a != "unclear" and
                                                          craft_a != craft_b):
        problems.append((FC.WRONG_CRAFT_TEXTURE, f"reads as {craft_b} (anchor {craft_a}, "
                                                 f"pattern {getattr(exp, 'craft', '?')})"))
    eb, ea = _tri(b.get("border_or_edging_visible")), _tri(a.get("border_or_edging_visible"))
    if eb is True and not getattr(exp, "edging_declared", False) and ea is not True:
        problems.append((FC.INVENTED_EDGING, "an edging the anchor and the pattern do not have"))
    elif eb is None:
        unclear.append("edging unclear")
    bb, ba = _tri(b.get("plain_end_bands_visible")), _tri(a.get("plain_end_bands_visible"))
    if bb is True and not _has_bands(exp) and ba is not True:
        problems.append((FC.INVENTED_END_BAND_TREATMENT, "end bands the pattern does not have"))
    cb, ca = _tri(b.get("raised_cables_visible")), _tri(a.get("raised_cables_visible"))
    if cb is True and not _has_cables(exp) and ca is not True:
        problems.append((FC.WRONG_CRAFT_TEXTURE, "raised cables the pattern does not have"))
    nb, na = _int(b.get("distinct_yarn_colours")), _int(a.get("distinct_yarn_colours"))
    declared = len(getattr(exp, "palette_hex", []) or [])
    if nb is not None and declared and nb > declared:
        problems.append((FC.WRONG_COLOUR_LAYOUT, f"{nb} yarn colours; the pattern has "
                                                 f"{declared}"))
    elif nb is not None and na is not None and nb > na:
        problems.append((FC.WRONG_COLOUR_LAYOUT, f"{nb} yarn colours; the anchor shows {na}"))
    elif nb is None:
        unclear.append("colour count unclear")
    if problems:
        return _c("anchor_consistency", FAIL, "; ".join(p[1] for p in problems),
                  code=problems[0][0], codes=sorted({p[0] for p in problems}), reading=reading)
    if unclear:
        return _c("anchor_consistency", UNKNOWN, "; ".join(unclear), reading=reading)
    return _c("anchor_consistency", PASS, "the candidate's item reads as the anchor's and the "
                                          "pattern's (craft, edging, bands, cables, colours)",
              reading=reading)


def blind_consistency(judge, anchor_data: bytes, data: bytes, exp) -> dict:
    """The blind anchor-consistency check `fidelity.verify_lifestyle` runs when given it."""
    got = ask(judge, "item_description", item_prompt(), [anchor_data, data])
    if not got["answered"]:
        return _c("anchor_consistency", UNKNOWN, f"not judged: {got['why']}",
                  needs="vision judge")
    out = compare_items(got["reading"], exp)
    out["judge"] = got["judge"]
    return out


MAX_PATCHES = 4
MIN_PATCH_AREA = 0.002       # of the image, per patch
MIN_TOTAL_AREA = 0.01        # of the image, all patches together


def region_prompt() -> str:
    return ("Find the handmade crochet or knitted textile item in this image. Return up to "
            f"{MAX_PATCHES} rectangles that lie ENTIRELY on the item's fabric: no skin, no "
            "other clothing, no furniture, no background. Each rectangle is [x0, y0, x1, y1] as "
            "fractions (0 to 1) of the image width and height. Reply with one JSON object: "
            "{\"item_visible\": \"yes\"|\"no\"|\"unclear\", \"patches\": [rectangles]}. If you "
            "are not sure a rectangle is only fabric, leave it out.")


def validate_patches(reading: dict, size: tuple[int, int]) -> dict:
    """Interior fabric patches in pixels, or why there are none. Deterministic."""
    w, h = size
    if _tri(reading.get("item_visible")) is not True:
        return {"patches": [], "why": "the item is not clearly visible"}
    raw = reading.get("patches") if isinstance(reading.get("patches"), list) else []
    out, rejected = [], []
    for p in raw[:MAX_PATCHES]:
        try:
            x0, y0, x1, y1 = (float(v) for v in p)
        except (TypeError, ValueError):
            rejected.append("not four numbers")
            continue
        if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
            rejected.append("outside the image")
            continue
        if (x1 - x0) * (y1 - y0) < MIN_PATCH_AREA:
            rejected.append("too small")
            continue
        out.append((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    total = sum((b[2] - b[0]) * (b[3] - b[1]) for b in out) / float(max(w * h, 1))
    if not out or total < MIN_TOTAL_AREA:
        return {"patches": [], "why": f"no usable fabric patch (total {round(total, 4)} of the "
                                      f"image; rejected {rejected})"}
    return {"patches": out, "why": "", "area": round(total, 4), "rejected": rejected}


def locate_product(judge, data: bytes) -> dict:
    """The lifestyle product-region detector: the judge points at fabric, code measures colour.

    The judge is never told the palette, so it cannot steer the colour check; it only says
    where the item's fabric is. `fidelity.verify_lifestyle` then measures the palette inside
    those patches. No patch, no region: region_palette stays UNKNOWN."""
    from PIL import Image
    import io

    got = ask(judge, "product_region", region_prompt(), [data], max_tokens=300)
    if not got["answered"]:
        return {"patches": [], "why": got["why"], "judge": got["judge"]}
    try:
        size = Image.open(io.BytesIO(data)).size
    except Exception as exc:  # noqa: BLE001
        return {"patches": [], "why": f"undecodable image ({type(exc).__name__})"}
    return {**validate_patches(got["reading"], size), "judge": got["judge"]}


# ---- the adapter set used by candidate_gates.RealJudges --------------------------------------

class Adapters:
    """The blind adapters on one or two judge transports, with per-image caching."""

    def __init__(self, db, judge, *, second=None, references: dict | None = None):
        self.db, self.judge, self.second = db, judge, second
        self._refs = references
        self._cache: dict = {}

    def refs(self) -> dict:
        if self._refs is None:
            try:
                self._refs = canonical_reference_bytes()
            except Exception:  # noqa: BLE001 - unreadable canon: no reference, UNKNOWN
                self._refs = {}
        return self._refs

    def _data(self, cand: dict) -> bytes:
        data = cand.get("data") or b""
        if data or not cand.get("sha256"):
            return data
        try:
            from ..core.artifacts import ArtifactStore

            return ArtifactStore().get(cand["sha256"], db=self.db) or b""
        except Exception:  # noqa: BLE001
            return b""

    def _person(self, cand: dict) -> list[dict]:
        data = self._data(cand)
        key = ("person", hashlib.sha256(data).hexdigest() if data else "")
        if key not in self._cache:
            refs = self.refs()
            if not data:
                self._cache[key] = [{"answered": False, "why": "no image bytes", "judge": None}]
            elif not all(refs.get(f) for f in REF_ORDER):
                self._cache[key] = [{"answered": False, "judge": None,
                                     "why": "the canonical references could not be read by "
                                            "their recorded sha256"}]
            else:
                self._cache[key] = person_readings([self.judge, self.second], data, refs)
        return self._cache[key]

    def _size_of(self, sha: str) -> int:
        from . import canonical

        for frame, want in canonical.CURRENT_REFERENCE_HASHES.items():
            if want == sha and self.refs().get(frame):
                return len(self.refs()[frame])
        try:
            from ..core.artifacts import ArtifactStore

            return len(ArtifactStore().get(sha, db=self.db) or b"")
        except Exception:  # noqa: BLE001 - bytes not found: not measured
            return 0

    def identity(self, cand: dict) -> dict:
        return identity_check(cand, self._person(cand), size_of=self._size_of)

    def body_proportions(self, cand: dict) -> dict:
        return body_check(self._person(cand))

    def outfit_consistency(self, cand: dict, outfit: dict | None) -> dict:
        if not outfit or not outfit.get("garments"):
            return _c("outfit_consistency", UNKNOWN, "no reserved outfit to compare against")
        data = self._data(cand)
        got = ask(self.judge, "outfit_description", outfit_prompt(), [data])
        if not got["answered"]:
            return _c("outfit_consistency", UNKNOWN, f"not judged: {got['why']}")
        others = []
        try:
            from . import outfits as O

            listing = cand.get("listing") or O.listing_of(cand.get("slug", ""))
            others = [(f"{o['outfit_id']} ({o['listing']})", o["garments"])
                      for o in O.registry(self.db)
                      if o.get("listing") and o["listing"] != listing
                      and o["outfit_id"] != outfit.get("outfit_id")]
        except Exception:  # noqa: BLE001 - no registry: no repetition reading
            others = []
        out = compare_outfit(got["reading"], outfit, others=others)
        out["judge"] = got["judge"]
        return out

    def anatomy(self, cand: dict) -> dict:
        got = ask(self.judge, "anatomy", anatomy_prompt(), [self._data(cand)])
        if not got["answered"]:
            return _c("anatomy", UNKNOWN, f"anatomy not judged: {got['why']}")
        out = compare_anatomy(got["reading"], laura=bool(cand.get("laura_present")))
        out["judge"] = got["judge"]
        return out

    def realism(self, cand: dict) -> dict:
        got = ask(self.judge, "realism", realism_prompt(), [self._data(cand)])
        if not got["answered"]:
            return _c("realism", UNKNOWN, f"photographic realism not judged: {got['why']}")
        out = compare_realism(got["reading"])
        out["judge"] = got["judge"]
        return out

    def product_region(self, cand: dict) -> dict:
        return locate_product(self.judge, self._data(cand))
