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
