"""Physical testing: a real sample, and what it is allowed to change (Master Plan section 3).

Everything else in this system is computed. This is the one input that is measured, and it is
the only thing that can turn an estimate into a figure.

Two jobs, and they are different:

**Calibration.** Yardage is derived from per-stitch constants anchored on a checkable
reference, carrying an explicit plus or minus 20%. A sample reports grams used per colour and
the ball band, which converts to metres, which divides by the estimate to give a factor. The
factor applies to the yarn weight and stitch it was measured at -- not globally, because a
cotton basket at a firm gauge tells you nothing about acrylic worked loose.

**Falsification.** The twin also predicts the finished size, and for a round-worked piece
that prediction comes from the surface geometry rather than from a rule of thumb. A sample
that comes out a different size is not a calibration input; it is evidence that the model is
wrong about the object, and it raises a defect. The distinction matters: quietly folding a
size disagreement into a "calibration factor" would hide exactly the failure this is for.

A sample is never assumed. Until one exists, `calibration_for` returns 1.0 and the twin keeps
saying its estimate is uncalibrated, which is the honest answer and the one the listing
copy already states.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# How far the measured finished size may differ from the twin's prediction before the model,
# rather than the estimate, is what needs fixing. Gauge varies between makers; geometry does
# not, so this is tighter than the yardage tolerance.
SIZE_DISAGREEMENT = 0.12

# A factor outside this range means something is wrong with the report or with the constants
# in a way averaging will not fix: a factor of four is a transcription error or the wrong
# ball band, not a calibration.
FACTOR_FLOOR, FACTOR_CEILING = 0.4, 2.5


@dataclass(frozen=True)
class BallBand:
    """What the label says: one ball is `grams` and `metres`.

    Required, because grams cannot become metres without it and a sample reported in grams
    alone is unusable. Asking for it costs the tester nothing -- it is printed on the yarn.
    """

    grams: float
    metres: float

    def metres_for(self, grams_used: float) -> float:
        if self.grams <= 0 or self.metres <= 0:
            raise ValueError("ball band must state positive grams and metres")
        return grams_used * (self.metres / self.grams)


@dataclass
class SampleReport:
    """What a tester hands back. Measured, not computed."""

    product_slug: str
    version: str
    tester_ref: str
    grams_by_color: dict[str, float]
    ball_band: BallBand
    hook_mm: float | None = None
    measured_width_cm: float | None = None
    measured_height_cm: float | None = None
    measured_around_cm: float | None = None
    hours: float | None = None
    notes: str = ""
    instructions_followed: bool = True

    def metres_by_color(self) -> dict[str, float]:
        return {colour: round(self.ball_band.metres_for(grams), 1)
                for colour, grams in self.grams_by_color.items()}


@dataclass
class Finding:
    code: str
    message: str
    severity: str = "WARNING"


@dataclass
class SampleAssessment:
    """What the sample established, and what it calls into question."""

    report: SampleReport
    estimated_metres: dict[str, float]
    measured_metres: dict[str, float]
    factor: float | None = None
    size_agrees: bool | None = None
    # What the sample was worked in. Carried on the assessment so a factor can never be
    # applied to a yarn or a stitch it was not measured on.
    yarn: str | None = None
    stitch: str | None = None
    findings: list[Finding] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def usable_for_calibration(self) -> bool:
        return self.factor is not None and not any(
            f.severity == "ERROR" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "slug": self.report.product_slug,
            "version": self.report.version,
            "tester": self.report.tester_ref,
            "estimated_metres": self.estimated_metres,
            "measured_metres": self.measured_metres,
            "factor": self.factor,
            "size_agrees": self.size_agrees,
            "yarn": self.yarn,
            "stitch": self.stitch,
            "hours": self.report.hours,
            "hook_mm": self.report.hook_mm,
            "findings": [{"code": f.code, "message": f.message, "severity": f.severity}
                         for f in self.findings],
            "assessed_at": self.assessed_at.isoformat(),
        }


def assess(report: SampleReport, twin, cir=None) -> SampleAssessment:
    """Compare one real sample against what the twin predicted for it."""
    estimated = dict(twin.yarn_metres_by_color)
    measured = report.metres_by_color()
    out = SampleAssessment(
        report=report, estimated_metres=estimated, measured_metres=measured,
        yarn=next((m.name for m in (cir.materials if cir else []) if m.name), None),
        stitch=(cir.gauge.stitch_type if cir is not None and cir.gauge else None))

    unknown = sorted(set(measured) - set(estimated))
    if unknown:
        out.findings.append(Finding(
            "SAMPLE_UNKNOWN_COLOUR",
            f"the sample reports yarn for {unknown}, which the pattern does not use; either "
            f"the wrong pattern was worked or the colours were recorded under other names",
            "ERROR"))

    shared = [c for c in measured if c in estimated and estimated[c] > 0]
    total_measured = sum(measured[c] for c in shared)
    total_estimated = sum(estimated[c] for c in shared)
    if shared and total_estimated > 0:
        factor = total_measured / total_estimated
        if FACTOR_FLOOR <= factor <= FACTOR_CEILING:
            out.factor = round(factor, 3)
        else:
            out.findings.append(Finding(
                "SAMPLE_FACTOR_IMPLAUSIBLE",
                f"measured yarn is {factor:.2f}x the estimate, which is outside the range a "
                f"calibration can explain. Check the ball band and the grams before this "
                f"changes any published figure",
                "ERROR"))
    else:
        out.findings.append(Finding(
            "SAMPLE_NO_COMPARISON",
            "no colour in the sample matches a colour the pattern estimates, so there is "
            "nothing to calibrate against", "ERROR"))

    # Size is falsification, not calibration.
    claims = [("width", report.measured_width_cm, twin.width_cm),
              ("height", report.measured_height_cm, twin.height_cm),
              ("circumference", report.measured_around_cm, twin.circumference_cm)]
    checked = [(label, m, p) for label, m, p in claims if m is not None and p]
    if checked:
        out.size_agrees = True
        for label, measured_cm, predicted_cm in checked:
            drift = abs(measured_cm - predicted_cm) / predicted_cm
            if drift > SIZE_DISAGREEMENT:
                out.size_agrees = False
                out.findings.append(Finding(
                    "SAMPLE_SIZE_DISAGREES",
                    f"the sample measures {measured_cm:.1f} cm {label} where the pattern "
                    f"claims {predicted_cm:.1f} cm ({drift:.0%} out). That is the listing's "
                    f"size claim, so it is a defect in the model or the pattern, not a "
                    f"calibration input",
                    "ERROR"))

    if not report.instructions_followed:
        out.findings.append(Finding(
            "SAMPLE_DEVIATED",
            "the tester reports not following the written instructions, so neither the "
            "yardage nor the size measures what was published", "ERROR"))

    if report.notes.strip():
        out.findings.append(Finding(
            "SAMPLE_TESTER_NOTES",
            f"tester notes to read before the next release: {report.notes.strip()[:300]}",
            "WARNING"))

    return out


def calibration_key(yarn: str | None, stitch: str | None) -> str:
    """What a factor is allowed to apply to: this yarn, worked in this stitch.

    The yarn is its full description, not just its weight. An earlier version keyed on weight
    alone, and a test caught what that meant: "worsted cotton" and "worsted acrylic" produced
    the same key, so a factor measured on a firm cotton basket would have silently rewritten
    the yardage on an acrylic throw. Cotton and acrylic at the same weight do not use the
    same length of yarn per stitch, which is the entire reason a factor exists.

    Gauge is deliberately *not* in the key: the per-stitch constants are expressed per
    stitch-width, so gauge is already normalised out of them. Including it would fragment
    calibration to one factor per design, which is the same as having none.
    """
    return f"{(yarn or 'unknown').strip().lower()}:{(stitch or 'sc').lower()}"


def calibration_for(cir, assessments: list[SampleAssessment]) -> float:
    """The factor to apply to this pattern's yardage: the mean of what applies, or 1.0.

    1.0 means uncalibrated, which is what the twin reports and what the listing says. There
    is deliberately no fallback to "the nearest sample": a pattern with no applicable
    measurement has no measurement.
    """
    if not assessments or cir.gauge is None:
        return 1.0
    want = calibration_key(
        next((m.name for m in cir.materials if m.name), None), cir.gauge.stitch_type)
    applicable = [a.factor for a in assessments
                  if a.usable_for_calibration and a.factor
                  and calibration_key(a.yarn, a.stitch) == want]
    if not applicable:
        return 1.0
    return round(sum(applicable) / len(applicable), 3)


# ---- persistence -----------------------------------------------------------


def record(db, assessment: SampleAssessment) -> int:
    """Store the sample. The row is the evidence; the assessment is what we concluded.

    `passed` is not "the tester liked it": it is whether this sample can be used, which
    means a plausible factor, a size that agrees with the claim, and instructions actually
    followed. A sample that fails still gets stored, because a disagreement is the most
    valuable thing a sample can produce.
    """
    from ..core.models import PhysicalTest

    with db.session() as s:
        row = PhysicalTest(
            product_slug=assessment.report.product_slug,
            version=assessment.report.version,
            tester_ref=assessment.report.tester_ref,
            completed_at=assessment.assessed_at,
            passed=assessment.usable_for_calibration and assessment.size_agrees is not False,
            measured=assessment.to_dict(),
            notes=assessment.report.notes[:2000],
        )
        s.add(row)
        s.flush()
        return row.id


def stored_assessments(db) -> list[SampleAssessment]:
    """Rebuild the assessments from stored rows, for calibration only.

    Only the fields calibration depends on are reconstructed: a stored row is a record, not
    an object to resurrect. A row written by an older version without a factor is skipped
    rather than guessed at.
    """
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    out: list[SampleAssessment] = []
    with db.session() as s:
        for row in s.scalars(select(PhysicalTest).where(
                PhysicalTest.passed == True)):  # noqa: E712
            measured = row.measured or {}
            factor = measured.get("factor")
            if not factor:
                continue
            out.append(SampleAssessment(
                report=SampleReport(
                    product_slug=row.product_slug, version=row.version,
                    tester_ref=row.tester_ref, grams_by_color={},
                    ball_band=BallBand(grams=1.0, metres=1.0)),
                estimated_metres=measured.get("estimated_metres", {}),
                measured_metres=measured.get("measured_metres", {}),
                factor=float(factor),
                size_agrees=measured.get("size_agrees"),
                yarn=measured.get("yarn"),
                stitch=measured.get("stitch")))
    return out


def calibration_from_db(db, cir) -> float:
    """The calibration factor this pattern's yardage should use, from stored samples."""
    return calibration_for(cir, stored_assessments(db))
