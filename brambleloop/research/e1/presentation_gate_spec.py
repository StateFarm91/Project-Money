"""The presentation gate, refined: redesign versus authorised presentation.

The invariant behind the current `presentation.py` is sound and is kept: A GENERATIVE
OPERATION THAT REACHES THE PRODUCT CAN INVENT A PRODUCT, and a plausible invention is the
only failure that reaches a customer. What the current rule cannot express is the case E1
just demonstrated -- a generative operation that was CONDITIONED on the certified structure
and whose output was INDEPENDENTLY RE-MEASURED against that structure and found to preserve
it. Under the current rule that is `ProductRedesigned`; under this one it is
`AUTHORISED_PRESENTATION`, and the difference is evidence, not permission.

Two categories, decided per pipeline before spend:

  UNAUTHORISED REDESIGN  -- a generative operation touches the product and EITHER
      (a) no certified structural reference was declared for it, OR
      (b) its output was never revalidated, OR
      (c) revalidation FAILED.
  AUTHORISED PRESENTATION -- a generative operation touches the product AND it declares
      the certified reference it was conditioned on (by digest) AND the output's
      Milestone-D assessment PASSED.

Everything in between -- reference declared, revalidation UNKNOWN -- is UNKNOWN, which
blocks exactly as FAIL does and differs only in what to do next. It is the state E1's best
output is in today (calibration missing), and this gate says so rather than promoting it.

Structure-preserving operations are unchanged: they need neither reference nor revalidation,
because they cannot invent a stitch.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Reused verbatim from the existing gate: the classification is not re-decided here.
STRUCTURE_PRESERVING = frozenset({
    "relight", "shade", "tonal_grade", "colour_transform", "white_balance",
    "warp_to_surface", "perspective", "scale", "rotate",
    "depth_of_field_blur", "motion_blur", "grain", "vignette",
    "composite", "occlusion_mask", "alpha_blend", "shadow_cast",
    "lens_distortion", "chromatic_aberration", "compress",
})
GENERATIVE = frozenset({
    "image_to_image", "inpaint", "outpaint", "diffusion_upscale", "enhance",
    "style_transfer", "face_restore", "generate", "refine", "denoise_generative",
    "relight_generative", "texture_synthesis",
})

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
UNAUTHORISED_REDESIGN = "UNAUTHORISED_REDESIGN"
AUTHORISED_PRESENTATION = "AUTHORISED_PRESENTATION"
STRUCTURE_PRESERVED = "STRUCTURE_PRESERVED"


@dataclass
class Operation:
    name: str
    touches_product: bool
    # The digest of the certified structural reference this operation was conditioned on
    # (structure.json + reference render). None means "not conditioned on anything certified".
    conditioned_on: str | None = None

    @property
    def is_generative(self) -> bool:
        return self.name in GENERATIVE

    @property
    def is_known(self) -> bool:
        return self.name in STRUCTURE_PRESERVING or self.name in GENERATIVE


@dataclass
class PresentationPlan:
    operations: list[Operation] = field(default_factory=list)
    # The Milestone D assessment of the OUTPUT image (its `.verdict`), or None if never run.
    revalidation_verdict: str | None = None
    # Digest of the certified structure the whole plan claims to present.
    certified_reference: str | None = None

    def verdict(self) -> dict:
        if not self.operations:
            return {"category": UNAUTHORISED_REDESIGN, "verdict": FAIL,
                    "why": "no operations declared; an undeclared pipeline is not a safe one"}
        unknown_ops = [o.name for o in self.operations if not o.is_known]
        touching = [o for o in self.operations if o.touches_product]
        if any(not o.is_known for o in touching):
            return {"category": UNAUTHORISED_REDESIGN, "verdict": FAIL,
                    "why": f"unclassified operations touch the product: {unknown_ops}"}
        gen = [o for o in touching if o.is_generative]
        if not gen:
            return {"category": STRUCTURE_PRESERVED, "verdict": PASS,
                    "why": "only structure-preserving operations reach the product"}
        # Generative over the product: this is where the refinement lives.
        unconditioned = [o.name for o in gen
                         if not o.conditioned_on or o.conditioned_on != self.certified_reference]
        if not self.certified_reference or unconditioned:
            return {"category": UNAUTHORISED_REDESIGN, "verdict": FAIL,
                    "why": (f"generative operations {unconditioned or [o.name for o in gen]} reach "
                            f"the product without being conditioned on the certified reference")}
        if self.revalidation_verdict is None:
            return {"category": UNAUTHORISED_REDESIGN, "verdict": FAIL,
                    "why": "conditioned on the certified reference but the output was never "
                           "revalidated against it; conditioning is a claim, revalidation is the proof"}
        if self.revalidation_verdict == PASS:
            return {"category": AUTHORISED_PRESENTATION, "verdict": PASS,
                    "why": "conditioned on the certified reference and the output's Milestone D "
                           "assessment passed every applicable property"}
        if self.revalidation_verdict == UNKNOWN:
            return {"category": AUTHORISED_PRESENTATION, "verdict": UNKNOWN,
                    "why": "conditioned and revalidated, but a property could not be measured "
                           "(typically gauge/scale while the twin is uncalibrated). Blocks like "
                           "FAIL; differs only in what to do next"}
        return {"category": UNAUTHORISED_REDESIGN, "verdict": FAIL,
                "why": "revalidation FAILED: the output does not preserve the certified product"}
