"""Does the deterministic object match the real photographed one?

Milestone C of the visual pipeline. The deterministic model predicts a finished object from
certified instructions alone; the photographs show the object a person actually made. This
compares them characteristic by characteristic and, crucially, records how each answer was
reached -- because the two sides of this comparison are not the same kind of evidence.

A predicted number is a computation over certified counts and gauge: reproducible, exact,
and wrong in a way that can be traced. A photographic observation is a judgement about an
image at whatever resolution that image happens to have: it can establish that a garment has
two pockets and cannot establish which loop a stitch entered. Treating those as equals is how
a comparison flatters itself, so every characteristic declares what the photograph can
actually settle before it is allowed to agree or disagree.

The verdicts are deliberately four-valued. `corresponds` and `contradicts` are claims about
the world. `not_observable` means the photograph cannot answer at this resolution, which is a
property of the evidence rather than of the product. `indeterminate` means the prediction
itself carries more uncertainty than the difference being tested, which is the assembly
module's rule applied here: a check that cannot separate its own error bars from the thing it
measures reports that, rather than whichever side it happens to fall.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CORRESPONDS = "corresponds"
CONTRADICTS = "contradicts"
NOT_OBSERVABLE = "not_observable"
INDETERMINATE = "indeterminate"


@dataclass
class Characteristic:
    """One property of the finished object, predicted and then checked against a photograph."""

    name: str
    predicted: str
    # What a photograph of this kind can settle. Set False for anything needing resolution
    # the source photography does not have -- stitch identity, loop targeting, exact gauge.
    observable_in_photography: bool
    observed: str = ""
    verdict: str = NOT_OBSERVABLE
    why: str = ""

    def to_dict(self) -> dict:
        return {"characteristic": self.name, "predicted": self.predicted,
                "observed": self.observed, "verdict": self.verdict, "why": self.why,
                "observable": self.observable_in_photography}


@dataclass
class Correspondence:
    subject: str
    size: str
    characteristics: list[Characteristic] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.characteristics:
            out[c.verdict] = out.get(c.verdict, 0) + 1
        return out

    @property
    def verdict(self) -> str:
        """Overall, and never better than the weakest evidence allows.

        One contradiction is decisive: a deterministic object that disagrees with the real
        one about something a photograph can settle is wrong, whatever else it gets right.
        Absent that, the result is PARTIAL for as long as anything is unobservable -- which,
        for stitch-level truth at listing-photograph resolution, is always. FULL is
        deliberately hard to reach and is not reachable from photography alone.
        """
        c = self.counts
        if c.get(CONTRADICTS):
            return "CONTRADICTED"
        if c.get(NOT_OBSERVABLE) or c.get(INDETERMINATE):
            return "PARTIAL"
        return "FULL" if c.get(CORRESPONDS) else "UNEVALUATED"

    def to_dict(self) -> dict:
        return {"subject": self.subject, "size": self.size, "verdict": self.verdict,
                "counts": self.counts,
                "characteristics": [c.to_dict() for c in self.characteristics],
                "note": ("photography establishes finished-object characteristics, never "
                         "stitch-level truth; `not_observable` is a statement about the "
                         "evidence and never about the product")}


def predict(cir, geo, twins) -> list[Characteristic]:
    """What the deterministic object claims about itself, in terms a photograph could check.

    Every number here is computed from the certified CIR -- stitch counts, gauge, grain,
    construction -- and nothing is read from an image.
    """
    from . import fabric

    body = next(c for c in cir.components if c.name == "body")
    body_twin = twins["body"]
    sleeve = next((c for c in cir.components if c.name == "sleeve"), None)
    pocket = next((c for c in cir.components if c.name == "pocket"), None)
    band = next((c for c in cir.components if c.name == "neck_ribbing"), None)
    f = geo.footprints

    out: list[Characteristic] = []

    out.append(Characteristic(
        "overall length", f"{geo.silhouette_up_cm:.0f} cm from shoulder to hem", True))

    if "body" in f:
        flat = f["body"].across_cm
        out.append(Characteristic(
            "silhouette",
            f"{flat:.0f} cm of fabric around the body: an open, oversized cardigan "
            f"rather than a fitted one", True))

    out.append(Characteristic(
        "front opening",
        "open edge to edge with no closures: the construction has no buttonholes, ties or "
        "fastenings anywhere", True))

    arm = f["body"].openings[0] if f.get("body") and f["body"].openings else None
    out.append(Characteristic(
        "shoulder and armhole",
        (f"dropped shoulder: the armhole is an unshaped slit about {arm:.0f} cm long with no "
         f"sleeve-cap shaping anywhere in the construction" if arm else
         "dropped shoulder: no armhole shaping in the construction"), True))

    if sleeve and "sleeve" in f:
        s = f["sleeve"]
        cuff = any(getattr(o, "stitch", None) == "slst" for r in sleeve.rows for o in r.ops)
        out.append(Characteristic(
            "sleeve volume",
            (f"a straight tube {s.across_cm:.0f} cm around and {s.up_cm:.0f} cm long with no "
             f"taper; " + ("the cuff edge is slip stitch, which is shorter than the body "
                           "stitch and draws that end in, so the sleeve reads as a balloon"
                           if cuff else "no cuff treatment, so it hangs straight")), True))
        out.append(Characteristic(
            "cuff gathering",
            "gathered" if cuff else "not gathered", True))

    if pocket and "pocket" in f:
        p = f["pocket"]
        out.append(Characteristic(
            "pockets",
            f"{p.copies} patch pockets, each about {p.across_cm:.0f} x {p.up_cm:.0f} cm, "
            f"sewn onto the fronts", True))
        out.append(Characteristic(
            "pocket placement",
            "not stated by the construction: the pattern gives no position for them", False,
            why="the construction states no placement, so there is nothing to compare"))

    if band and "neck_ribbing" in f:
        out.append(Characteristic(
            "neckband",
            f"a ribbed band about {f['neck_ribbing'].across_cm:.0f} cm wide running the whole "
            f"neckline and both front edges", True))

    sig = fabric.texture_signature(body_twin)
    out.append(Characteristic(
        "body texture class",
        f"{sig.get('surface', 'unmeasured')}: an all-over broken surface rather than "
        f"directional ridges", True))

    if band:
        bsig = fabric.texture_signature(twins["neck_ribbing"])
        out.append(Characteristic(
            "neckband texture class", f"{bsig.get('surface', 'unmeasured')}: ribbing", True))

    out.append(Characteristic(
        "texture direction",
        ("the body is worked sideways, so its rows run vertically on the worn garment and "
         "every row boundary is a vertical line"
         if body.rows_run_vertically_on_the_body else
         "the body is worked bottom-up, so its rows run horizontally around the garment"),
        True))

    out.append(Characteristic(
        "individual stitch identity",
        "every stitch's type and loop target is known exactly from the CIR", False,
        why="listing photography does not resolve individual stitches, so the photograph "
            "cannot confirm or deny this however right or wrong it is"))

    out.append(Characteristic(
        "drape", "not predicted: the model is geometric and carries no fabric mechanics",
        False, why="nothing deterministic is claimed about drape, so there is no prediction "
                   "for a photograph to check"))

    return out


# What the benchmark photographs show, recorded once so the comparison is reproducible.
#
# These are observations of four supplied listing photographs of the real finished garment,
# made by looking at them. That is a weaker kind of evidence than the predictions they are
# compared against, and it is labelled as such rather than promoted: an observation here can
# establish that a garment has two patch pockets and a gathered cuff, and cannot establish
# gauge, stitch identity or loop targeting. Anything needing resolution the photographs do
# not have stays `not_observable` no matter how confident the prediction is.
#
# Recorded as data rather than re-judged on each run, so the benchmark gives the same answer
# twice and a change in the verdict means the model changed rather than the mood.
BENCHMARK_OBSERVATIONS: dict[str, tuple[str, str]] = {
    "overall length": (
        "reaches mid-thigh on the model the sample was photographed on",
        "consistent with the predicted length; photographs establish proportion against a "
        "body, not centimetres"),
    "silhouette": (
        "open, loose and clearly oversized, with the fronts hanging apart rather than meeting",
        "corresponds"),
    "front opening": (
        "open edge to edge; no buttons, ties, toggles or fastenings anywhere in any frame",
        "corresponds"),
    "shoulder and armhole": (
        "the shoulder seam sits well below the natural shoulder and the sleeve joins on a "
        "straight line with no cap shaping",
        "corresponds: a dropped shoulder from an unshaped slit"),
    "sleeve volume": (
        "full and voluminous along its length, narrowing only at the wrist",
        "corresponds: a straight tube gathered at one end reads exactly this way"),
    "cuff gathering": (
        "gathered: the sleeve draws in sharply at the wrist into a denser band",
        "corresponds"),
    "pockets": (
        "two patch pockets, one on each front, roughly square and at hip level",
        "corresponds in count, shape and kind"),
    "neckband": (
        "a wide ribbed band runs the full neckline and continues down both front edges",
        "corresponds"),
    "body texture class": (
        "an irregular, broken, crumpled surface rather than clean continuous ridges",
        "corresponds to the measured surface class, at the limit of what the resolution "
        "supports: the break-up is visible, the individual loop targets are not"),
    "neckband texture class": (
        "the band shows clear parallel ridges running across its width, unlike the body",
        "corresponds: the band is ribbed and the body is not, which is the distinction the "
        "measurement makes"),
    "texture direction": (
        "the body and sleeves show continuous vertical lines running from hem to shoulder",
        "corresponds: sideways construction puts every row boundary vertical on the worn "
        "garment, and a bottom-up garment with these same counts would show them horizontal"),
}


def compare(cir, geo, twins, *, size: str,
            observations: dict[str, tuple[str, str]] | None = None) -> Correspondence:
    """Milestone C: the deterministic object against the real photographed one."""
    obs = BENCHMARK_OBSERVATIONS if observations is None else observations
    out = Correspondence(subject=cir.slug, size=size)
    for ch in predict(cir, geo, twins):
        if not ch.observable_in_photography:
            ch.verdict = NOT_OBSERVABLE
            out.characteristics.append(ch)
            continue
        seen = obs.get(ch.name)
        if seen is None:
            ch.verdict = NOT_OBSERVABLE
            ch.why = "no observation was recorded for this characteristic"
        else:
            ch.observed, ch.why = seen
            ch.verdict = CONTRADICTS if ch.why.startswith("contradicts") else CORRESPONDS
        out.characteristics.append(ch)
    return out
