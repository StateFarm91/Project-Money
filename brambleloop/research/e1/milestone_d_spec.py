"""Milestone D, given a definition for the first time: executable, fail-closed, four-valued.

The claim D makes: Brambleloop POSSESSES A STRUCTURALLY TRUSTWORTHY REPRESENTATION OF THE
PRODUCT THAT IS ADEQUATE FOR DOWNSTREAM PRESENTATION, and a presentation made from it
preserved the product. That is eight separable properties, each with its own evidence and its
own verdict. They are reported separately and never averaged; a single magic score is how one
property covers for another.

Verdicts: PASS (measured, within tolerance) / FAIL (measured, outside) / UNKNOWN (the evidence
needed does not exist) / NOT_APPLICABLE (the product has no such feature -- a basket has no
neckline -- and that is recorded, not silently passed).

Fail-closed rules, stated once:
  * UNKNOWN is never PASS. An overall PASS requires every applicable property to PASS.
  * Any FAIL fails the milestone, whatever else passed.
  * `gauge_scale_confidence` is UNKNOWN whenever `twin.calibrated` is False. A photograph
    can be checked against the twin's PREDICTED dimensions, and that check lives in
    `silhouette_proportion`; but whether those predictions are the real object's dimensions
    is exactly what calibration establishes, and nothing in an image can stand in for it.
    So while the catalogue is uncalibrated, Milestone D's best possible overall verdict is
    UNKNOWN. That is the truthful state and this module refuses to report a better one.

This module does not measure anything itself. It takes the deterministic layer's
`structure` (what the product IS, from the CIR and twin) and a `measured` dict of what an
independent judge found in the OUTPUT image, and decides. Missing measurements are UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PASS, FAIL, UNKNOWN, NOT_APPLICABLE = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"

# Tolerances. The 2% ratio tolerance is B-703's, reused rather than re-chosen.
RATIO_TOLERANCE = 0.02
COLOUR_POSITION_TOLERANCE_FRAC = 0.03      # of product height, per colour boundary
STITCH_SCALE_TOLERANCE = 0.10              # relative, on a per-cm or per-round count

PROPERTIES = (
    "silhouette_proportion", "stitch_family", "gauge_scale_confidence",
    "topology_construction", "shaping_openings", "colour_regions",
    "conditioning_reference_complete", "final_image_product_truth",
)


@dataclass
class Property:
    name: str
    verdict: str
    evidence: str
    measured: object = None
    expected: object = None


@dataclass
class MilestoneD:
    subject: str
    properties: list[Property] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        vs = [p.verdict for p in self.properties]
        if any(v == FAIL for v in vs):
            return FAIL
        if any(v == UNKNOWN for v in vs):
            return UNKNOWN
        return PASS

    def to_dict(self) -> dict:
        return {"milestone": "D", "subject": self.subject, "verdict": self.verdict,
                "properties": [p.__dict__ for p in self.properties],
                "rule": "any FAIL -> FAIL; else any UNKNOWN -> UNKNOWN; else PASS. "
                        "UNKNOWN is not a pass."}


def _within(measured: float, expected: float, tol: float) -> bool:
    return expected != 0 and abs(measured - expected) / abs(expected) <= tol


def assess(structure: dict, measured: dict | None, *, twin_calibrated: bool) -> MilestoneD:
    """`structure` is the deterministic layer's output; `measured` is what a judge found in
    the presentation image. `measured=None` means no image was assessed at all."""
    m = measured or {}
    out = MilestoneD(subject=structure.get("slug", "?"))
    A = out.properties.append

    # 1. Silhouette / proportion -- ratios, because scale is free in a photograph.
    exp = structure.get("silhouette_ratio_diameter_over_height") or structure.get("silhouette_ratio")
    got = m.get("silhouette_ratio")
    if exp is None:
        A(Property("silhouette_proportion", UNKNOWN, "structure carries no silhouette ratio"))
    elif got is None:
        A(Property("silhouette_proportion", UNKNOWN, "not measured on the image", None, exp))
    else:
        A(Property("silhouette_proportion", PASS if _within(got, exp, RATIO_TOLERANCE) else FAIL,
                   f"|{got:.3f}-{exp:.3f}|/{exp:.3f} vs {RATIO_TOLERANCE}", got, exp))

    # 2. Stitch family -- exact, no tolerance; sc is not hdc.
    exp = structure.get("stitch_family")
    got = m.get("stitch_family")
    if not exp:
        A(Property("stitch_family", UNKNOWN, "structure names no stitch family"))
    elif got is None:
        A(Property("stitch_family", UNKNOWN, "not judged on the image", None, exp))
    else:
        A(Property("stitch_family", PASS if got == exp else FAIL, f"judge saw {got!r}", got, exp))

    # 3. Gauge / scale confidence -- UNKNOWN until the twin is calibrated. Not negotiable.
    if not twin_calibrated:
        A(Property("gauge_scale_confidence", UNKNOWN,
                   "twin.calibrated is False: every centimetre is a gauge prediction and no "
                   "image can confirm a prediction against a real object"))
    else:
        exp = structure.get("stitches_top_round"); got = m.get("stitches_counted_top_round")
        if exp is None or got is None:
            A(Property("gauge_scale_confidence", UNKNOWN, "no stitch count to compare", got, exp))
        else:
            A(Property("gauge_scale_confidence",
                       PASS if _within(got, exp, STITCH_SCALE_TOLERANCE) else FAIL,
                       "counted stitches on the top round vs the CIR's", got, exp))

    # 4. Topology / construction cues the CIR makes: base type, wall, joined-round seam.
    exp = structure.get("construction_cues")           # e.g. ["flat_disc_base","straight_wall","open_top"]
    got = m.get("construction_cues_seen")
    if not exp:
        A(Property("topology_construction", UNKNOWN, "structure lists no construction cues"))
    elif got is None:
        A(Property("topology_construction", UNKNOWN, "not judged on the image", None, exp))
    else:
        missing = [c for c in exp if c not in got]
        A(Property("topology_construction", PASS if not missing else FAIL,
                   f"missing {missing}" if missing else "every cue present", got, exp))

    # 5. Shaping / openings -- neckline, armholes, handles. A basket has none: recorded.
    exp = structure.get("openings")
    if exp is None:
        A(Property("shaping_openings", UNKNOWN, "structure does not say whether openings exist"))
    elif not exp:
        A(Property("shaping_openings", NOT_APPLICABLE, "the product has no openings to preserve"))
    else:
        got = m.get("openings_seen")
        if got is None:
            A(Property("shaping_openings", UNKNOWN, "not judged", None, exp))
        else:
            missing = [o for o in exp if o not in got]
            A(Property("shaping_openings", PASS if not missing else FAIL, f"missing {missing}", got, exp))

    # 6. Colour regions -- count and position of every colour boundary.
    exp = structure.get("colour_boundaries_frac")     # e.g. [0.435, 0.457, 0.696, 0.717]
    got = m.get("colour_boundaries_frac")
    if exp is None:
        A(Property("colour_regions", UNKNOWN, "structure carries no colour boundaries"))
    elif got is None:
        A(Property("colour_regions", UNKNOWN, "not measured on the image", None, exp))
    elif len(got) != len(exp):
        A(Property("colour_regions", FAIL, f"{len(got)} boundaries seen, {len(exp)} expected", got, exp))
    else:
        worst = max(abs(a - b) for a, b in zip(sorted(got), sorted(exp)))
        A(Property("colour_regions", PASS if worst <= COLOUR_POSITION_TOLERANCE_FRAC else FAIL,
                   f"worst boundary error {worst:.3f} of height vs {COLOUR_POSITION_TOLERANCE_FRAC}",
                   got, exp))

    # 7. Conditioning reference complete -- does the deterministic layer carry what a
    #    presentation needs? Checked on `structure`, not on the image.
    need = ("stitch_family", "colour_boundaries_frac", "construction_cues", "openings")
    absent = [k for k in need if k not in structure] + (
        [] if any(k in structure for k in ("silhouette_ratio_diameter_over_height", "silhouette_ratio"))
        else ["silhouette_ratio"])
    A(Property("conditioning_reference_complete", PASS if not absent else FAIL,
               f"missing {absent}" if absent else "every field a presentation needs is present"))

    # 8. Final image Product Truth -- the conjunction of the image-side properties above,
    #    stated separately so a reader sees whether the IMAGE was ever checked at all.
    image_side = [p for p in out.properties
                  if p.name in ("silhouette_proportion", "stitch_family", "topology_construction",
                                "shaping_openings", "colour_regions")]
    if measured is None:
        A(Property("final_image_product_truth", UNKNOWN, "no presentation image was assessed"))
    elif any(p.verdict == FAIL for p in image_side):
        A(Property("final_image_product_truth", FAIL, "an image-side property failed"))
    elif any(p.verdict == UNKNOWN for p in image_side):
        A(Property("final_image_product_truth", UNKNOWN, "an image-side property is unmeasured"))
    else:
        A(Property("final_image_product_truth", PASS, "every image-side property passed"))
    return out
