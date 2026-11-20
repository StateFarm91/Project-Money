"""Deterministic prompt assembly for one gallery frame (ENG-WARDROBE-SCENES).

A frame's prompt combines four things, each from its own source of truth:

* the **scene** (`scene_library.Scene`): place, vantage, light, camera, props;
* the **outfit** (`outfit_library.Outfit`), only when Laura is in the frame;
* the **product reference** (`product_ref`), read from the certified CIR: title, release
  identity, fingerprint, components and the exact yarn colours. The product block is the
  same text, byte for byte, in every frame of a gallery: the product never changes;
* the **frame role** and its template (`TEMPLATES`).

**Versioned templates.** Every template has an id such as `ws.hero@1`. A new wording is a new
version, never an edit of an old one, so a frame's `template_id` always names the words it
was made from. ENG-LEARN's champion/challenger (`learning.image_lessons`, contract
`image_lessons/1`) evolves templates through the interface it defined:
* `learn_default_template(family, role)` returns this module's code default in ENG-LEARN's
  template shape (`brief`, `camera`, `lighting`, `negatives`), using its closed CAMERA and
  LIGHTING vocabularies, so it can seed a scope's first champion;
* `assemble(..., learned=prompt_for(...))` takes ENG-LEARN's `prompt_for` result: its brief
  replaces the role brief, its camera and lighting replace the scene's phrases, and its
  `prompt_version` is carried onto the frame for `image_production.record_candidate`;
* `learn_scene(frame)` is the `scene` dict ENG-LEARN's `features` reads.
A learned brief is held to the same rules as a code template: the misleading-prop rule and
`laura_home.check`. A learned template can change words, never the product block, the
outfit or Laura's identity lock.

**Deterministic.** The same inputs give the same prompt, byte for byte (`prompt_sha256`).
No clock, no randomness, no model call, no network, CA$0.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import scene_library as SL

ASSEMBLY_VERSION = "prompt-assembly/1"


class PromptAssemblyRefused(ValueError):
    pass


# ---- the product reference, from the CIR ----------------------------------------------------

@dataclass(frozen=True)
class ProductRef:
    slug: str
    title: str
    version: str
    fingerprint: str
    family: str
    colours: tuple[tuple[str, str], ...]
    components: tuple[str, ...]

    def block(self) -> str:
        cols = ", ".join(f"{n} ({h})" for n, h in self.colours)
        comps = ", ".join(self.components)
        return (f"PRODUCT: {self.title}, Brambleloop {self.slug} version {self.version} "
                f"(certified CIR {self.fingerprint}), made exactly to the certified pattern. "
                f"Pieces: {len(self.components)} ({comps}). Yarn colours, exact and only "
                f"these: {cols}. Real crochet at true stitch scale. The product is identical "
                f"in every frame of this gallery: the same shape, colour placement, "
                f"proportions, stitch texture and piece count; nothing is added to it and "
                f"nothing is taken away.")

    def digest(self) -> str:
        return hashlib.sha256(self.block().encode()).hexdigest()

    def view(self) -> dict:
        return {"slug": self.slug, "title": self.title, "version": self.version,
                "fingerprint": self.fingerprint, "family": self.family,
                "colours": [list(c) for c in self.colours],
                "components": list(self.components), "digest": self.digest()}


def product_ref(cir, *, family: str) -> ProductRef:
    """The product reference description of a certified CIR."""
    colours = tuple((str(k), str(v)) for k, v in (cir.colors or {}).items())
    if not colours:
        raise PromptAssemblyRefused(f"{cir.slug}: the CIR declares no yarn colours; the "
                                    f"product is described from certified data only")
    fp = getattr(cir, "fingerprint", "")
    fp = fp() if callable(fp) else fp
    return ProductRef(slug=cir.slug, title=cir.title, version=str(cir.version),
                      fingerprint=str(fp), family=str(family),
                      colours=colours, components=tuple(c.name for c in cir.components))


# ---- templates ------------------------------------------------------------------------------
# Per frame role, the brief for each way the product meets Laura (outfit_library.interaction)
# and for a frame without her. {product} is "the finished piece".
_P = "the finished piece"
TEMPLATES: dict[str, dict] = {
    "ws.hero@1": {"role": "hero", "briefs": {
        "worn": f"Hero: Laura wearing {_P}, relaxed and natural, {_P} fully in view.",
        "held": f"Hero: {_P} in the room it lives in, styled as it is really used.",
        "near": f"Hero: {_P} in everyday use where it lives, every piece in view.",
        "none": f"Hero: {_P} where it lives, every piece in view."}},
    "ws.flat_lay@1": {"role": "flat_lay", "briefs": {
        "none": f"Flat lay: {_P} laid out flat and complete, every piece and edge visible, "
                f"nothing overlapping it."}},
    "ws.lifestyle@1": {"role": "lifestyle", "briefs": {
        "worn": f"Lifestyle: Laura wearing {_P} in an ordinary moment of her day.",
        "held": f"Lifestyle: Laura using {_P} where it lives, unhurried and candid.",
        "near": f"Lifestyle: Laura in an everyday moment with {_P} in use beside her.",
        "none": f"Lifestyle: {_P} in an everyday moment of use."}},
    "ws.alt_angle@1": {"role": "alt_angle", "briefs": {
        "worn": f"Alternative angle: Laura wearing {_P}, seen from behind or the side.",
        "none": f"Alternative angle: {_P} from another side, showing its back, base or "
                f"reverse."}},
    "ws.close_up@1": {"role": "close_up", "briefs": {
        "none": f"Close-up: the stitch texture and edge of {_P}, sharp and true to scale."}},
    "ws.scale_in_use@1": {"role": "scale_in_use", "briefs": {
        "worn": f"Scale: Laura wearing {_P}, showing how it fits and its length on her.",
        "held": f"Scale: Laura with {_P}, showing its size against her.",
        "near": f"Scale: Laura using {_P}, showing its size against her hands.",
        "none": f"Scale: {_P} beside everyday objects of known size."}},
    "ws.extra@1": {"role": "extra", "briefs": {
        "none": f"Construction: {_P} from an angle that shows how it is put together: its "
                f"base, joins or seams."}},
}
CURRENT: dict[str, str] = {t["role"]: tid for tid, t in TEMPLATES.items()}
NEGATIVES: tuple[str, ...] = (
    "any other crocheted or knitted item", "text, logos, watermarks or borders",
    "a plain photographic backdrop", "a generic catalogue pose", "extra or missing product pieces",
    "colours the product does not have")
IDENTITY_LOCK = ("Laura is the canonical Brambleloop model (laura-r2-a42aeac7): her face, hair, "
                 "eyes, apparent age, facial structure and body proportions exactly as in the "
                 "three canonical references.")
REALISM = ("A natural, believable photograph: real handmade crochet with visible yarn texture, "
           "natural light, anatomically correct hands, no over-staged composition.")

_LEARN_CAMERA = {"three_quarter": "three_quarter", "overhead": "overhead", "side": "side",
                 "front": "front", "close": "close", "full_length": "full_length"}
_LEARN_CAMERA_PHRASE = {
    "three_quarter": "seen from a three-quarter angle", "overhead": "seen from directly above",
    "side": "seen from the side", "front": "seen straight on", "close": "a close detail view",
    "full_length": "full length"}
_LEARN_LIGHTING_PHRASE = {"daylight": "soft daylight", "warm_lamp": "warm lamp light",
                          "studio": None}


def _brief(template_id: str, mode: str) -> str:
    t = TEMPLATES.get(template_id)
    if t is None:
        raise PromptAssemblyRefused(f"unknown template {template_id!r}")
    b = t["briefs"]
    return b.get(mode) or b["none"]


def learn_role(frame_role: str) -> str:
    """The shot_plans role key ENG-LEARN and the image producer record for a frame role."""
    from .shot_plans import ROLE_OF_JOB

    from .gallery_planner import JOB_OF_FRAME

    return ROLE_OF_JOB[JOB_OF_FRAME[frame_role]] if frame_role != "extra" else "construction"


def learn_default_template(family: str, role: str, *, laura_mode: str = "none") -> dict:
    """This module's code default in ENG-LEARN's template shape (image_lessons/1).

    `role` may be a frame role ("close_up") or a shot_plans role key ("detail")."""
    frame_role = role if role in SL.FRAME_ROLES else _frame_of_learn_role(role)
    tid = CURRENT[frame_role]
    camera = {"hero": "three_quarter", "flat_lay": "overhead", "lifestyle": "three_quarter",
              "alt_angle": "side", "close_up": "close", "scale_in_use": "front",
              "extra": "side"}[frame_role]
    return {"brief": _brief(tid, laura_mode), "camera": camera, "lighting": "daylight",
            "negatives": list(NEGATIVES), "source": tid, "family": family}


def _frame_of_learn_role(role: str) -> str:
    from .gallery_planner import JOB_OF_FRAME
    from .shot_plans import JOB_OF_ROLE

    job = JOB_OF_ROLE.get(role)
    for fr, j in JOB_OF_FRAME.items():
        if j == job:
            return fr
    if role == "construction":
        return "extra"
    raise PromptAssemblyRefused(f"{role!r} is not a frame role or a shot_plans role key")


# ---- assembly --------------------------------------------------------------------------------

def _check_text(text: str, family: str, what: str) -> None:
    from .laura_home import problems as home_problems

    bad = SL.misleading_text(text, family) + home_problems(text)
    if bad:
        raise PromptAssemblyRefused(f"{what} breaks a scene rule: {bad}")


def assemble(*, scene: SL.Scene, product: ProductRef, frame_role: str, laura: bool,
             outfit=None, template_id: str | None = None, learned: dict | None = None) -> dict:
    """The prompt for one frame. Deterministic: same inputs, same bytes.

    Refused when: the frame role is not the scene's; Laura is in the frame without an outfit
    (or the outfit's family check fails); the scene cannot host Laura; or any non-product
    text breaks the misleading-prop rule or `laura_home.check`."""
    from . import outfit_library as OL

    family = product.family
    if frame_role not in SL.FRAME_ROLES:
        raise PromptAssemblyRefused(f"{frame_role!r} is not a frame role")
    if frame_role not in scene.roles:
        raise PromptAssemblyRefused(f"{scene.scene_id} does not serve the {frame_role} role")
    if family not in scene.families:
        raise PromptAssemblyRefused(f"{scene.scene_id} does not suit the {family} family")
    if laura and not scene.laura:
        raise PromptAssemblyRefused(f"{scene.scene_id} is a product-only scene")
    if laura and outfit is None:
        raise PromptAssemblyRefused("Laura is in the frame and no outfit is given; every Laura "
                                    "frame names the listing's one outfit")
    if laura:
        comp = OL.compatible(outfit, family)
        if not comp["ok"]:
            raise PromptAssemblyRefused(f"{outfit.outfit_id} is not compatible with {family}: "
                                        f"{comp['why']}")
    tid = template_id or CURRENT[frame_role]
    if TEMPLATES.get(tid, {}).get("role") != frame_role:
        raise PromptAssemblyRefused(f"template {tid!r} is not a {frame_role} template")
    mode = OL.interaction(family) if laura else "none"
    brief = _brief(tid, mode)
    camera = scene.camera_text()
    lighting = SL.LIGHTING[scene.lighting]
    negatives = list(NEGATIVES)
    prompt_version = tid
    if learned:
        t = dict(learned.get("template") or {})
        if t.get("brief"):
            brief = str(t["brief"]).strip()
        if t.get("camera") in _LEARN_CAMERA_PHRASE:
            camera = f"{_LEARN_CAMERA_PHRASE[t['camera']]}; {scene.focal_mm}mm lens, " \
                     f"{scene.dof} depth of field"
        if _LEARN_LIGHTING_PHRASE.get(t.get("lighting")):
            lighting = _LEARN_LIGHTING_PHRASE[t["lighting"]]
        negatives += [str(n) for n in t.get("negatives") or [] if str(n) not in negatives]
        prompt_version = str(learned.get("prompt_version") or tid)
    props, dropped = SL.props_for(scene, family)
    prop_text = ", ".join(SL.PROPS[p] for p in props)
    environment = scene.environment()
    scene_text = (f"{brief} Setting: {environment} Light: {lighting}. Camera: {camera}."
                  + (f" Props: {prop_text}." if prop_text else "")
                  + f" {SL.NOT_INCLUDED}")
    _check_text(scene_text, family, "the scene")
    sections = {"scene": scene_text}
    if laura:
        sections["laura"] = (f"{IDENTITY_LOCK} Outfit (the listing's one outfit, "
                             f"{outfit.outfit_id}): {outfit.text_spec()}. Hair: "
                             f"{OL.HAIR_STYLINGS[outfit.hair]}, {OL.HAIR_LOCK}.")
    else:
        sections["laura"] = "No person in the frame."
    sections["product"] = product.block()
    sections["realism"] = REALISM
    sections["negatives"] = "Never show: " + "; ".join(negatives) + "."
    text = "\n".join(sections[k] for k in ("scene", "laura", "product", "realism", "negatives"))
    return {
        "assembly_version": ASSEMBLY_VERSION, "template_id": tid,
        "prompt_version": prompt_version, "frame_role": frame_role,
        "scene_id": scene.scene_id, "family": family, "laura": bool(laura),
        "outfit_id": outfit.outfit_id if laura else None,
        "product_digest": product.digest(), "sections": sections, "prompt": text,
        "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "props": props, "props_dropped": dropped,
        # What varies between frames: the room's fixed architecture is left out, so two
        # frames in the same room are compared on what the camera actually sees differently.
        "variable_text": " ".join([brief, scene.vantage, lighting, camera, prop_text]),
        "flux_scene": {"outfit": ({"outfit_id": outfit.outfit_id,
                                   "garments": outfit.garments,
                                   "description": outfit.text_spec()} if laura else {}),
                       "environment": f"{environment} Light: {lighting}.",
                       "pose": brief, "framing": camera},
        "learn_scene": {"camera": scene.angle, "lighting": SL.LEARN_LIGHTING[scene.lighting],
                        "room": _learn_room(scene.place), "scene_id": scene.scene_id,
                        "template_id": tid},
    }


def _learn_room(place: str) -> str | None:
    return {"living_room": "living_room", "reading_nook": "living_room",
            "nursery": "nursery", "kitchen": "kitchen", "dining": "dining",
            "bedroom": "bedroom", "entry": "entry"}.get(place)


def learn_scene(frame: dict) -> dict:
    """The `scene` dict ENG-LEARN's `features` reads for an assembled frame."""
    return dict(frame.get("learn_scene") or {})


def fingerprint(frame: dict) -> str:
    """A stable digest of everything that decided a frame's prompt."""
    keep = {k: frame[k] for k in ("template_id", "prompt_version", "frame_role", "scene_id",
                                  "outfit_id", "product_digest", "prompt_sha256")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()
