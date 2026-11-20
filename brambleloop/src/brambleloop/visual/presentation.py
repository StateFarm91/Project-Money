"""How a deterministic product becomes a photograph without stopping being that product.

Milestone D. The owner's invariant is that AI may photograph the product and may not redesign
it, and the whole difficulty is that the obvious way to make a render look photographic --
hand it to a generative model and ask for realism -- is exactly the thing that redesigns it.
Twelve renders across three providers already established what happens when a model is asked
to produce certified crochet: product truth 0 of 12.

So the lock is not enforced by inspecting the finished image. It is enforced by provenance.

**Measuring structure out of a final JPEG is the wrong instrument.** By the time an image is
lit, posed, draped, blurred and compressed, recovering "is this the certified stitch pattern"
from pixels is a vision judgement -- expensive, approximate, and exactly the kind of check
that returns `unmeasurable` on the cases that matter most. A gate that can only sometimes
tell whether the product survived is not a lock.

**Provenance is exact and free.** Every operation applied to the product region is declared,
and the lock holds if and only if all of them are structure-preserving. That is a property of
the pipeline rather than of a picture, so it can be checked deterministically, before any
money is spent, and it cannot return `unmeasurable`.

The line between the two kinds of operation is not a matter of degree:

  * A **structure-preserving** operation is a function of the pixels that are already there.
    Relighting, shading, tonal grading, colour transforms, warping onto a draped surface,
    depth-of-field blur, compositing, occlusion masking, adding grain -- every one of these
    moves or reweights existing pixels. None of them can invent a stitch, because none of
    them knows what a stitch is. Fabric that is blurred or shadowed may become harder to
    read; it does not become different fabric.

  * A **generative** operation samples new pixels from a model. Image-to-image, inpainting,
    outpainting, upscaling by diffusion, "enhance", style transfer, a face restorer applied
    to the whole frame. Each of these is capable of producing a plausible crochet texture
    that is not the certified one, and a plausible texture is the failure mode -- it looks
    right and is wrong, which is the only failure that reaches a customer.

The scene, the environment, the lighting design, the pose and the model may all be generative.
They are not the certified product. What must never happen is a generative operation whose
output region overlaps the product, and that is precisely what this module refuses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Operations that are functions of existing pixels. Each can degrade legibility; none can
# invent structure, because none of them has a model of what crochet is.
STRUCTURE_PRESERVING = frozenset({
    "relight", "shade", "tonal_grade", "colour_transform", "white_balance",
    "warp_to_surface", "perspective", "scale", "rotate",
    "depth_of_field_blur", "motion_blur", "grain", "vignette",
    "composite", "occlusion_mask", "alpha_blend", "shadow_cast",
    "lens_distortion", "chromatic_aberration", "compress",
})

# Operations that sample new pixels from a model. Any of these over the product region is a
# redesign, whatever it is called and however good the result looks.
GENERATIVE = frozenset({
    "image_to_image", "inpaint", "outpaint", "diffusion_upscale", "enhance",
    "style_transfer", "face_restore", "generate", "refine", "denoise_generative",
    "relight_generative", "texture_synthesis",
})


class ProductRedesigned(AssertionError):
    """A generative operation reached the certified product region."""


@dataclass
class Operation:
    """One step of the presentation pipeline, and what it touched."""

    name: str
    touches_product: bool
    note: str = ""

    @property
    def is_generative(self) -> bool:
        return self.name in GENERATIVE

    @property
    def is_known(self) -> bool:
        return self.name in STRUCTURE_PRESERVING or self.name in GENERATIVE


@dataclass
class PresentationPlan:
    """The operations that turn a deterministic product into a photograph."""

    operations: list[Operation] = field(default_factory=list)

    def add(self, name: str, *, touches_product: bool, note: str = "") -> "PresentationPlan":
        self.operations.append(Operation(name, touches_product, note))
        return self

    @property
    def offending(self) -> list[Operation]:
        """Generative operations that reach the product, and unknown ones that claim to."""
        return [o for o in self.operations
                if o.touches_product and (o.is_generative or not o.is_known)]

    def lock_verdict(self) -> dict:
        """Whether the product survives this pipeline, decided before it is run."""
        from .final_standard import FAIL, PASS, UNMEASURABLE, FloorResult, PRODUCT_TRUTH

        unknown = [o.name for o in self.operations if not o.is_known]
        if not self.operations:
            return FloorResult(PRODUCT_TRUTH, UNMEASURABLE,
                               "no operations were declared, so what happened to the product "
                               "is unknown; an undeclared pipeline is not a safe one").__dict__
        bad = self.offending
        if bad:
            names = sorted({o.name for o in bad})
            return FloorResult(
                PRODUCT_TRUTH, FAIL,
                f"{names} " + ("sample new pixels over the certified product, which is a "
                               "redesign however good it looks" if any(o.is_generative for o in bad)
                               else "are not recognised, and an operation nobody has "
                                    "classified may not touch the product"),
                tuple(names)).__dict__
        touched = [o.name for o in self.operations if o.touches_product]
        return FloorResult(
            PRODUCT_TRUTH, PASS,
            f"the product region is touched only by structure-preserving operations "
            f"({sorted(set(touched)) or 'none'}); nothing that samples new pixels reaches it. "
            f"Unknown operations elsewhere in the frame: {unknown or 'none'}").__dict__

    def refuse_if_the_product_is_redesigned(self) -> None:
        v = self.lock_verdict()
        if v["verdict"] != "pass":
            raise ProductRedesigned(v["why"])


def scene_generation_is_allowed(plan: PresentationPlan) -> bool:
    """Generative work on everything that is NOT the product is fine and is the point.

    The pose, the room, the light, the styling and the model may all be generated. This
    exists so the rule does not read as "no generative AI": it reads as "generative AI may
    photograph the product, and may not be the thing that draws it".
    """
    return any(o.is_generative and not o.touches_product for o in plan.operations)


# ---------------------------------------------------------------------------
# The second lock: geometry.
#
# The provenance lock above proves the product's pixels were never invented. That is
# necessary and it is not sufficient, and the owner's framing is the exact one: a
# transformation being deterministic does not automatically make it truthful. Authentic
# pixels stretched into the wrong garment shape are still the wrong garment. A cardigan
# squashed 20% narrower to fit a pose has every certified stitch in it and is not the
# product the customer's pattern makes.
#
# So this lock asks a different question from the first, and the two cannot substitute for
# each other: not "were these pixels drawn by a model" but "does the thing they now depict
# still have the certified object's shape".
# ---------------------------------------------------------------------------

# How far a ratio may drift before the garment is a different garment.
#
# Two percent. Crochet is not rigid and a real photograph of a real cardigan on a real body
# will not measure exactly, but the tolerance is for photographic reality rather than for
# convenience: a seam eases, a drape foreshortens slightly, a sleeve twists. Beyond a couple
# of percent the difference stops being how the fabric fell and starts being how the image
# was fitted to the frame, which is the thing this exists to refuse.
GEOMETRY_TOLERANCE = 0.02

# The ratios that have to survive. Ratios rather than absolute sizes, because a photograph
# may legitimately show the garment at any scale -- what it may not do is change its shape.
# Named generically so a basket's height-to-width or a blanket's motif aspect is covered by
# the same machinery as a cardigan's sleeve-to-body.
GEOMETRY_INVARIANTS = (
    "garment_aspect",          # overall up : across
    "stitch_aspect",           # one stitch's width : height -- the motif's shape
    "sleeve_to_body",          # each component's size relative to the body
    "pocket_to_body",
    "band_to_body",
)


def certified_ratios(geo, gauge) -> dict:
    """The shape facts a presentation must not change, from the assembled object geometry.

    Computed from the CIR's own object space, so this is the reference the placed image is
    measured against rather than a description of it.
    """
    out: dict[str, float] = {}
    body = geo.footprints.get("body") or (
        max(geo.footprints.values(), key=lambda f: f.across_cm * f.up_cm)
        if geo.footprints else None)
    if body is None or not body.across_cm:
        return out
    out["garment_aspect"] = body.up_cm / body.across_cm
    if gauge and gauge.rows_per_10cm:
        # A stitch is wider than it is tall in most crochet, and that ratio is what makes a
        # motif the shape it is. Stretch it and every stitch in the fabric is subtly wrong
        # while each one is still, pixel for pixel, ours.
        out["stitch_aspect"] = ((10.0 / gauge.stitches_per_10cm) /
                                (10.0 / gauge.rows_per_10cm))
    for name, key in (("sleeve", "sleeve_to_body"), ("pocket", "pocket_to_body"),
                      ("neck_ribbing", "band_to_body")):
        f = geo.footprints.get(name)
        if f is not None:
            out[key] = (f.across_cm * f.up_cm) / (body.across_cm * body.up_cm)
    return out


def geometry_lock_held(certified: dict, placed: dict, *,
                       tolerance: float = GEOMETRY_TOLERANCE):
    """Did the placed product keep the certified object's shape?

    `certified` comes from `certified_ratios`; `placed` is the same ratios measured on the
    product as it appears in the presented image. Compared as ratios so scale is free and
    shape is not.

    Fails closed. A ratio nobody measured is not a ratio that held -- and the specific way
    this check would otherwise be defeated is by a pipeline that simply declines to report
    the geometry it produced, which would turn the strictest lock in the system into the
    easiest one to pass.
    """
    from .final_standard import FAIL, PASS, UNMEASURABLE, FloorResult, PRODUCT_TRUTH

    if not certified:
        return FloorResult(PRODUCT_TRUTH, UNMEASURABLE,
                           "the certified object has no measured geometry to compare "
                           "against, so whether the placement preserved it is unknown")
    missing = tuple(sorted(k for k in certified if k not in placed))
    if missing:
        return FloorResult(
            PRODUCT_TRUTH, UNMEASURABLE,
            f"{list(missing)} were not measured on the placed product. A ratio nobody "
            f"measured is not a ratio that held, and a pipeline that declines to report its "
            f"own geometry must not thereby pass the check",
            (), missing)

    drifted: list[str] = []
    detail: list[str] = []
    for key, want in certified.items():
        got = placed[key]
        if not want:
            continue
        drift = abs(got - want) / abs(want)
        if drift > tolerance:
            drifted.append(key)
            detail.append(f"{key} {want:.4f} -> {got:.4f} ({drift:+.1%})")
    if drifted:
        return FloorResult(
            PRODUCT_TRUTH, FAIL,
            f"the placement changed the certified object's shape: {'; '.join(detail)}. "
            f"Authentic pixels in the wrong shape are still the wrong garment, and a "
            f"transformation being deterministic does not make it truthful",
            tuple(sorted(drifted)))
    return FloorResult(PRODUCT_TRUTH, PASS,
                       f"all {len(certified)} certified shape ratios survived placement "
                       f"within {tolerance:.0%}")


def both_product_locks(plan: "PresentationPlan", certified: dict, placed: dict) -> dict:
    """Product Truth for a presented asset: provenance AND geometry, independently.

    Reported separately and never averaged. A pipeline can keep every pixel authentic and
    still stretch the garment; it can preserve the shape perfectly and still have let a model
    repaint the stitches. Either one failing fails Product Truth, which is why they are two
    locks rather than one score.
    """
    structure = plan.lock_verdict()
    geometry = geometry_lock_held(certified, placed)
    holds = structure["verdict"] == "pass" and geometry.verdict == "pass"
    return {
        "product_truth": "pass" if holds else (
            "fail" if "fail" in (structure["verdict"], geometry.verdict) else "unmeasurable"),
        "structure_lock": structure,
        "geometry_lock": {"verdict": geometry.verdict, "why": geometry.why,
                          "failed": list(geometry.failed_checks),
                          "unjudged": list(geometry.unjudged_checks)},
        "why": ("both product locks hold" if holds else
                "Product Truth requires provenance AND geometry; they do not substitute for "
                "one another"),
    }
