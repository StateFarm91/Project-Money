"""The presentation gate's two categories, tested against E3's actual evidence. NOT integrated.

The invariant in `visual/presentation.py` stands: a generative operation that reaches the
product can invent a product. What E3 adds is the evidence that lets one such operation be
told apart from redesign -- not by permission, by measurement:

  UNAUTHORISED REDESIGN        a generative operation touched the product and (a) declared no
                               certified structural reference, or (b) its output was never
                               revalidated, or (c) revalidation FAILED on any property.
  CERTIFIED PRESENTATION       the operation declares the frozen certified reference it was
  TRANSFORMATION               conditioned on (geometry digest AND reference-image digest), the
                               output's structural correspondence PASSED on every property, and
                               the output's photographic reading is recorded.
  UNKNOWN (blocks)             reference declared, correspondence has an UNKNOWN and no FAIL.

Fails closed: nothing here can be satisfied by declining to measure. The photographic verdict
is carried, not gated here -- realism is Milestone D's floor, and a certified transformation
that is structurally the same product and photographically not yet good enough is exactly the
state that needs a better photograph rather than a different product.
"""
from __future__ import annotations
from dataclasses import dataclass, field

UNAUTHORISED_REDESIGN = "UNAUTHORISED_REDESIGN"
CERTIFIED_PRESENTATION = "CERTIFIED_PRESENTATION_TRANSFORMATION"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class GenerativeOperation:
    name: str
    conditioned_on_geometry_sha256: str | None = None
    conditioned_on_reference_sha256: str | None = None
    output_sha256: str | None = None


@dataclass(frozen=True)
class Correspondence:
    """`correspond.py`'s per-image result: property -> PASS/FAIL/UNKNOWN."""
    properties: dict = field(default_factory=dict)
    reference_sha256: str | None = None
    geometry_sha256: str | None = None


def classify(op: GenerativeOperation, corr: Correspondence | None, *, frozen_geometry_sha256: str,
             frozen_reference_sha256: str) -> dict:
    why = []
    if not op.conditioned_on_geometry_sha256 or not op.conditioned_on_reference_sha256:
        why.append("no certified structural reference was declared for the operation")
        return {"category": UNAUTHORISED_REDESIGN, "why": why}
    if (op.conditioned_on_geometry_sha256 != frozen_geometry_sha256
            or op.conditioned_on_reference_sha256 != frozen_reference_sha256):
        why.append("the declared reference is not the frozen certified one")
        return {"category": UNAUTHORISED_REDESIGN, "why": why}
    if corr is None or not corr.properties:
        why.append("the output was never revalidated against the reference")
        return {"category": UNAUTHORISED_REDESIGN, "why": why}
    if corr.reference_sha256 != op.conditioned_on_reference_sha256 or corr.geometry_sha256 != op.conditioned_on_geometry_sha256:
        why.append("the revalidation was made against a different reference than the operation declared")
        return {"category": UNAUTHORISED_REDESIGN, "why": why}
    failed = sorted(k for k, s in corr.properties.items() if s == "FAIL")
    unknown = sorted(k for k, s in corr.properties.items() if s == "UNKNOWN")
    if failed:
        return {"category": UNAUTHORISED_REDESIGN, "why": [f"structural correspondence failed on {failed}"], "failed": failed, "unknown": unknown}
    if unknown:
        return {"category": UNKNOWN, "why": [f"structural correspondence could not be established on {unknown}; unknown blocks exactly as failure does"], "unknown": unknown}
    return {"category": CERTIFIED_PRESENTATION, "why": [f"conditioned on the frozen certified reference and every one of {len(corr.properties)} structural properties survived"]}
