"""The full FLUX 3 prompt, generated from certified data and brand rules (D-W4-LAURA-FLUX3 rule 7).

No caller writes a prompt. A prompt is assembled from six pinned sections, each an immutable,
content-hashed `gateway.prompts` entry (`image.flux3.<section>@<version>`), filled only from:

- the reference manifest (which image is which, by position: identity first);
- the certified technical rules (`creative.pattern_refs.technical_rules`): product id, version,
  release, construction, pieces, size, colours (hex), stitches, assembly, prohibited additions;
- the scene W-OWNERIMG selected (outfit, environment, pose, framing), taken as inputs;
- the image role, the AI-disclosure status and the publication restrictions.

The result carries every section's ref and sha256, the builder version and the sha256 of the
final text, so a receipt says exactly which prompt produced an image.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..gateway import prompts

BUILDER_VERSION = "flux3-prompt-builder/2.0.0"
_IMG = dict(system="", output_schema=("image",), max_output_tokens=1)

# The references, by position. The hierarchy is stated, not implied: identity comes from the
# canonical Laura originals, the product from the certified references, and anything
# supplementary may add context but never overrides either.
REFERENCES = prompts.register(prompts.Prompt(
    name="image.flux3.references", version="1", **_IMG, template=(
        "REFERENCE IMAGES, in order of authority: {reference_map}. The canonical Laura "
        "images decide who she is; the certified product images decide what the product is; "
        "any supplementary image adds context only and never overrides either.")))

IDENTITY_V1 = prompts.register(prompts.Prompt(
    name="image.flux3.identity", version="1", **_IMG, template=(
        "IDENTITY: the woman is Laura, exactly the person in {face}, {torso} and {body}. "
        "Preserve her face from {face}: eyes, eyebrows, nose, lips, cheekbones, jawline, "
        "freckles, apparent age, hairline and her highlighted wavy hair. Preserve her torso and "
        "bust from {torso}: bust fullness, chest projection, shoulders and waist; never "
        "flatten, reduce, exaggerate or redesign the bust; clothing fits and drapes over these "
        "approved proportions. Preserve her full-body silhouette from {body}: waist-to-hip and "
        "legs. Do not change her identity, body shape or proportions.")))

# Version 2 (owner wardrobe fix, 2026-10-19). FLUX copied the clothes in the canonical body
# references into lifestyle frames. The references fix identity and anatomy only. The prompt
# says so, names the selected complete outfit and replaces all reference clothing with it.
# Version 1 stays registered and immutable. It is no longer used for a Laura image.
IDENTITY = prompts.register(prompts.Prompt(
    name="image.flux3.identity", version="2", **_IMG, template=(
        "IDENTITY: the woman is Laura, exactly the person in {face}, {torso} and {body}. These "
        "three references fix her identity and anatomy ONLY, never her clothing. Preserve her "
        "face from {face}: eyes, eyebrows, nose, lips, cheekbones, jawline, freckles, apparent "
        "age, hairline and her highlighted wavy hair. Preserve face, bust fullness and "
        "projection, shoulders, waist, hips, legs and silhouette exactly as in {torso} and "
        "{body}; never flatten, reduce, exaggerate or redesign the bust; clothing fits and "
        "drapes over these approved proportions. Keep her full-body silhouette from {body}: "
        "waist-to-hip and legs. REPLACE ALL clothing from the reference images "
        "with the selected outfit: {outfit}; do not reuse the reference beige trousers, "
        "ivory/cream tops or tan sandals. Do not change her identity, body shape or "
        "proportions.")))

# CIR-independent: whatever the product, the reference clothing never reaches the image.
REFERENCE_CLOTHING = prompts.register(prompts.Prompt(
    name="image.flux3.reference_clothing", version="1", **_IMG, template=(
        "LAURA MUST NOT WEAR: {negatives}.")))

PRODUCT = prompts.register(prompts.Prompt(
    name="image.flux3.product", version="2", **_IMG, template=(
        "PRODUCT: {title}, Brambleloop {slug} version {version} (release {release}), shown "
        "exactly as in {layout} (complete product: shape, colour placement, proportions and "
        "pieces). The fabric looks exactly like {texture}: real crochet, its stitch posts, "
        "top loops and crossings at true scale. Stitch placement is charted in {detail}; the "
        "technical rules are in {rules}. "
        "Construction: {construction}. Pieces: {pieces}. Size: {size}. Colours, exact and "
        "only these: {colours}. Stitches: {stitches}. {assembly}Never add: {prohibited}.")))

# Category-aware prohibitions derived from the CIR (`pattern_refs.negatives`): always "crochet,
# not knitting"; no ribbing or edging unless declared; end bands exactly as declared; exact
# cable/motif count and spacing; colour changes only where the pattern changes colour.
NEGATIVES = prompts.register(prompts.Prompt(
    name="image.flux3.negatives", version="1", **_IMG, template=(
        "THIS FABRIC MUST NOT SHOW: {negatives}.")))

SCENE = prompts.register(prompts.Prompt(
    name="image.flux3.scene", version="1", **_IMG, template=(
        "SCENE ({role}): {subject} {outfit} Environment: {environment}. Pose and action: "
        "{pose}. Framing: {framing}.")))

REALISM = prompts.register(prompts.Prompt(
    name="image.flux3.realism", version="1", **_IMG, template=(
        "REALISM: a natural, believable photograph, not an illustration or a render. Real "
        "handmade crochet with visible yarn texture and true stitch scale; natural light; "
        "anatomically correct hands with five fingers; no over-staged composition. The "
        "product is in focus and fully legible for its role. No text, logos, watermarks or "
        "borders in the image.")))

DISCLOSURE = prompts.register(prompts.Prompt(
    name="image.flux3.disclosure", version="1", **_IMG, template=(
        "STATUS: {disclosure} {restrictions}")))

SECTIONS = (REFERENCES, IDENTITY, REFERENCE_CLOTHING, PRODUCT, NEGATIVES, SCENE, REALISM,
            DISCLOSURE)

DEFAULT_DISCLOSURE = ("This is an AI-generated image of a certified Brambleloop product and "
                      "will be disclosed as AI-generated wherever it is shown.")
DEFAULT_RESTRICTIONS = ("It is a candidate only: it is not published until identity, bust "
                        "and body proportion, outfit, Product Truth, anatomy, realism and "
                        "disclosure checks pass and the owner approves.")


class PromptBuildRefused(ValueError):
    """The prompt cannot be built from certified data and the declared references."""


@dataclass(frozen=True)
class BuiltPrompt:
    text: str
    sections: tuple[dict, ...]
    builder_version: str = BUILDER_VERSION
    inputs: dict = field(default_factory=dict)

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def ref(self) -> str:
        return "+".join(s["ref"] for s in self.sections)

    def receipt(self) -> dict:
        return {"builder_version": self.builder_version, "prompt_ref": self.ref,
                "sections": list(self.sections), "prompt_text_sha256": self.text_sha256,
                "inputs_sha256": hashlib.sha256(repr(sorted(self.inputs.items()))
                                                .encode()).hexdigest()}


PRODUCT_ROLES = ("product_layout", "product_texture", "product_detail", "product_rules")


def _img(position: int) -> str:
    return f"image {position}"


def _pieces(rules: dict) -> str:
    parts = [f"{c['name']} x{c['make']} ({c['worked']}"
             + (f", {c['width_cm']} x {c['height_cm']} cm" if c["width_cm"] and c["height_cm"]
                else "") + ")" for c in rules["components"]]
    return f"{rules['piece_count']} in total: " + "; ".join(parts)


def _size(rules: dict) -> str:
    if rules.get("garment") and rules["garment"].get("measures_cm"):
        gm = rules["garment"]
        return (f"garment size {gm.get('size')}, built measures "
                + ", ".join(f"{k} {v} cm" for k, v in gm["measures_cm"].items()))
    if rules.get("finished_size_note"):
        return rules["finished_size_note"]
    c = rules["components"][0]
    if c["width_cm"] and c["height_cm"]:
        return f"{c['width_cm']} x {c['height_cm']} cm finished"
    return "true to the layout reference's proportions"


def _outfit_text(outfit: Mapping) -> str:
    g = dict(outfit.get("garments") or {})
    if g:
        names = {"top_or_dress": "top/dress", "lower": "bottoms", "shoes": "footwear",
                 "outerwear": "outerwear", "accessories": "accessories"}
        return "; ".join(f"{names.get(k, k)}: {v}" for k, v in g.items()
                         if v and str(v).lower() != "none")
    return str(outfit.get("description") or "")


def build(*, rules: Mapping, roles: Sequence[str], role: str,
          scene: Mapping | None = None, edit: str = "", disclosure: str = DEFAULT_DISCLOSURE,
          restrictions: str = DEFAULT_RESTRICTIONS) -> BuiltPrompt:
    """Assemble the prompt for one generation.

    `roles` is the reference manifest, position by position (1-based in the prompt), e.g.
    ("laura_face", "laura_torso", "laura_body", "product_layout", "product_detail",
    "product_rules", "product_candidate", "outfit"). `scene` is W-OWNERIMG's selection:
    `outfit` ({description} and optionally an image among the references), `environment`,
    `pose`, `framing`. Missing certified data or a missing required reference is refused."""
    roles = list(roles)
    pos = {r: i + 1 for i, r in enumerate(roles)}
    if "product_combined" in pos:
        # A provider below the campaign set gets 4-7 merged into one sheet: one position.
        for k in PRODUCT_ROLES:
            pos.setdefault(k, pos["product_combined"])
    for need in PRODUCT_ROLES:
        if need not in pos:
            raise PromptBuildRefused(f"{need} is not among the references; the product is "
                                     f"described from its certified images, never from text "
                                     f"alone")
    features_laura = any(r.startswith("laura_") for r in roles)
    if features_laura and not all(r in pos for r in ("laura_face", "laura_torso",
                                                     "laura_body")):
        raise PromptBuildRefused("a Laura image needs all three canonical references")
    for key in ("slug", "version", "release_hash", "title", "components", "colours"):
        if not rules.get(key):
            raise PromptBuildRefused(f"certified rules are missing {key!r}")

    labels = {
        "laura_face": "canonical Laura face (neutral portrait)",
        "laura_torso": "canonical Laura torso and bust", "laura_body": "canonical Laura full "
        "body", "product_layout": "certified product layout", "product_texture": "certified "
        "crochet stitch texture close-up", "product_detail": "certified stitch chart", "product_rules": "certified technical rules",
        "product_combined": "certified product sheet (layout, texture, chart and rules, top "
        "to bottom)", "product_candidate": "approved product photograph of this exact product",
        "base": "the image to edit", "outfit": "the outfit", "supplementary": "supplementary "
        "context"}
    ref_map = "; ".join(f"{_img(i + 1)} = {labels.get(r.split(':')[0], r)}"
                        for i, r in enumerate(roles))
    scene = dict(scene or {})
    outfit = dict(scene.get("outfit") or {})
    texts = [REFERENCES.render(reference_map=ref_map)]
    used = [REFERENCES]
    if features_laura:
        if not (outfit.get("description") or outfit.get("garments") or "outfit" in pos):
            raise PromptBuildRefused("a Laura image needs the listing's complete outfit")
        from ..visual.wardrobe import REFERENCE_CLOTHING_NEGATIVES

        texts.append(IDENTITY.render(face=_img(pos["laura_face"]),
                                     torso=_img(pos["laura_torso"]),
                                     body=_img(pos["laura_body"]),
                                     outfit=_outfit_text(outfit) or (
                                         f"the outfit in {_img(pos['outfit'])}")))
        used.append(IDENTITY)
        texts.append(REFERENCE_CLOTHING.render(
            negatives="; ".join(REFERENCE_CLOTHING_NEGATIVES)))
        used.append(REFERENCE_CLOTHING)
    colours = ", ".join(f"{c['id']} {c['hex']}" if c.get("hex") else f"{c['id']} "
                        f"({c.get('yarn') or 'yarn'})" for c in rules["colours"])
    assembly = (("Assembly: " + "; ".join(rules["assembly"][:6]) + ". ")
                if rules.get("assembly") else "")
    texts.append(PRODUCT.render(
        title=rules["title"], slug=rules["slug"], version=rules["version"],
        release=str(rules["release_hash"])[:16], layout=_img(pos["product_layout"]),
        texture=_img(pos["product_texture"]), detail=_img(pos["product_detail"]),
        rules=_img(pos["product_rules"]),
        construction=f"{rules['construction']}, gauge {rules['gauge']['stitches_per_10cm']} "
                     f"sts x {rules['gauge']['rows_per_10cm']} rows per 10 cm in "
                     f"{rules['gauge']['stitch']}",
        pieces=_pieces(rules), size=_size(rules), colours=colours,
        stitches=", ".join(rules.get("stitches") or []) or "as charted",
        assembly=assembly, prohibited="; ".join(rules["prohibited_additions"])))
    used.append(PRODUCT)
    negs = list(rules.get("negatives") or [])
    if not negs or not negs[0].startswith("knitting"):
        raise PromptBuildRefused("certified rules carry no fabric negatives; the prompt "
                                 "would not forbid knitting, invented edging or end bands")
    texts.append(NEGATIVES.render(negatives="; ".join(negs)))
    used.append(NEGATIVES)
    if features_laura:
        subject = "Laura with the product."
        if outfit.get("description") or outfit.get("garments") or "outfit" in pos:
            o = f"She wears {_outfit_text(outfit) or 'the outfit'}"
            o += f", exactly as in {_img(pos['outfit'])}" if "outfit" in pos else ""
            outfit_text = o + "; the outfit is the same in every image of this listing."
        else:
            raise PromptBuildRefused("a Laura image needs the listing's outfit")
    else:
        subject, outfit_text = "The product alone; no person.", ""
    if edit:
        subject = (f"Edit {_img(pos['base'])}: {edit}. Keep everything else in "
                   f"{_img(pos['base'])} unchanged. " + subject) if "base" in pos else subject
    texts.append(SCENE.render(
        role=role, subject=subject, outfit=outfit_text,
        environment=scene.get("environment") or "a calm, natural setting suited to the "
        "product", pose=scene.get("pose") or ("Laura uses the product naturally"
                                              if features_laura else "the product at rest,"
                                              " whole piece visible"),
        framing=scene.get("framing") or "the whole product in frame"))
    used.append(SCENE)
    texts.append(REALISM.render())
    used.append(REALISM)
    texts.append(DISCLOSURE.render(disclosure=disclosure, restrictions=restrictions))
    used.append(DISCLOSURE)
    return BuiltPrompt(
        text="\n".join(t.strip() for t in texts),
        sections=tuple({"ref": p.ref, "sha256": p.sha256} for p in used),
        inputs={"roles": tuple(roles), "role": role, "release": rules["release_hash"],
                "scene": repr(sorted(scene.items())), "edit": edit})
