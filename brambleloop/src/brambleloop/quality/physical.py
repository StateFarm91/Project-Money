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

PARTIAL_PHYSICAL_CLASS = "partial_physical"   # gates.risk_matrix.PARTIAL_PHYSICAL


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
    # SECREVIEW F2/F4: whether the tester followed the text exactly is a recorded answer, never
    # a default. None (unanswered) is an incomplete record and is refused.
    instructions_followed: bool | None = None
    # PHYSFIX: what was actually made. `scope` is one of SCOPES; `made` maps a component name
    # to how many of it were made (`{"coaster": 2}`). None means the legacy reading: the whole
    # pattern, which `parts_made` only accepts where the pattern is a single piece.
    scope: str | None = None
    made: dict[str, int] | None = None
    # Which made piece the finished measurements are of, where more than one kind was made.
    measured_component: str | None = None
    # A swatch's gauge, as the tester measured it. Gauge evidence -- never yardage evidence.
    swatch_stitches_per_10cm: float | None = None
    swatch_rows_per_10cm: float | None = None
    # The protocol's shape observations: flat pieces must lie flat, 3-D pieces hold shape.
    lies_flat: bool | None = None
    holds_shape: bool | None = None
    # The tester's free-text report of anything wrong. Any entry routes to the owner.
    problem_notes: str = ""
    # The one size the tester worked, as the tester's sheet names it (optional; checked).
    size: str | None = None
    # SECREVIEW F6: every made piece's own finished measurements, each compared with its
    # component's twin: [{"component": "coaster", "width_cm": 9.6, "height_cm": 8.3}, ...].
    # Required, one per piece, wherever a component is made more than once.
    piece_measurements: list | None = None
    # The across-the-flats span of a polygonal piece, compared with `twin.across_flats_cm`.
    measured_flats_cm: float | None = None
    # Construction-review observations of a vessel (CONSTRUCTION_REVIEW_basket_small_1.2.0 §5),
    # recorded in structured form: how the base turns into the wall, whether the polygon
    # survives to the rim, and an in-progress height. Validated, stored, never guessed.
    base_edge: str | None = None               # "crisp" or "rounded"
    wall_vertical_from_rnd: int | None = None  # required when base_edge is "rounded"
    corners_at_rim: bool | None = None
    rim_across_points_cm: float | None = None
    inside_depth_cm: float | None = None
    rnd11_height_cm: float | None = None

    def metres_by_color(self) -> dict[str, float]:
        return {colour: round(self.ball_band.metres_for(grams), 1)
                for colour, grams in self.grams_by_color.items()}


# PHYSFIX: the three outcomes of a sample. Only PASS binds as evidence and calibrates.
# PARTIAL is a made object with a recorded problem (does not lie flat, does not hold its shape,
# a problem the tester wrote down): it goes to the owner and never passes by itself.
PASS, PARTIAL, FAIL = "PASS", "PARTIAL", "FAIL"
# A finding that routes the sample to owner review rather than failing it outright.
REVIEW = "REVIEW"

SCOPES = ("full_make", "component", "swatch")
# How a vessel's wall height is measured (construction review §5): one method, printed on the
# sheet and stored with every reading, so the number the twin is compared with is unambiguous.
WALL_HEIGHT_METHOD = ("outside, from the flat table to the top of the rim, at the middle of a "
                      "flat side")
BASE_EDGES = ("crisp", "rounded")
# A swatch's gauge may sit this far from the pattern's before it disagrees: the same 12% the
# finished size may, because gauge maps one-to-one onto every finished dimension.
GAUGE_DISAGREEMENT = SIZE_DISAGREEMENT

# What each scope's intake must carry, beyond the slug, ball band and grams (which the API
# requires of every sample). One table, read by the intake and by the owner's cost request
# (`gates.risk_matrix.owner_action_spec`), so what is offered is what is accepted.
SCOPE_FIELDS: dict[str, tuple[str, ...]] = {
    "full_make": ("made", "measured_width_cm", "lies_flat|holds_shape", "problem_notes",
                  "instructions_followed"),
    "component": ("made", "measured_width_cm", "lies_flat|holds_shape", "problem_notes",
                  "instructions_followed"),
    "swatch": ("swatch_stitches_per_10cm", "swatch_rows_per_10cm", "hook_mm",
               "instructions_followed"),
}


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
    # PHYSFIX: what was made, and the one size it covers.
    scope: str = "full_make"
    made: dict[str, int] = field(default_factory=dict)
    whole_pattern: bool = True
    gauge_agrees: bool | None = None
    covers_size: dict = field(default_factory=dict)

    @property
    def usable_for_calibration(self) -> bool:
        """A factor that may change published yardage: a PASS with a factor, nothing less.

        A swatch never has a factor (it is gauge evidence only), and a PARTIAL never
        calibrates: it has not passed, and calibration rewrites published figures."""
        return self.factor is not None and not any(
            f.severity in ("ERROR", REVIEW) for f in self.findings)

    @property
    def size_proof(self) -> bool:
        """SECREVIEW F3: whether this sample physically proves the finished size of its one size.

        Only a PASS of made pieces whose measured size agreed. A swatch is gauge evidence
        only and never proves a size, however well its gauge agrees."""
        return (self.outcome == PASS and self.scope != "swatch" and bool(self.made)
                and self.size_agrees is True)

    @property
    def outcome(self) -> str:
        if any(f.severity == "ERROR" for f in self.findings) or self.size_agrees is False:
            return FAIL
        if any(f.severity == REVIEW for f in self.findings):
            return PARTIAL
        if self.scope == "swatch":
            return PASS if self.gauge_agrees is True else FAIL
        return PASS if self.factor is not None else FAIL

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
            "scope": self.scope,
            "made": dict(self.made),
            "whole_pattern": self.whole_pattern,
            "swatch_gauge": {"stitches_per_10cm": self.report.swatch_stitches_per_10cm,
                             "rows_per_10cm": self.report.swatch_rows_per_10cm},
            "gauge_agrees": self.gauge_agrees,
            "lies_flat": self.report.lies_flat,
            "holds_shape": self.report.holds_shape,
            "problem_notes": self.report.problem_notes,
            "covers_size": dict(self.covers_size),
            "outcome": self.outcome,
            "size_proof": self.size_proof,
            "piece_measurements": list(self.report.piece_measurements or []),
            "measured_flats_cm": self.report.measured_flats_cm,
            "observations": {
                "wall_height_method": WALL_HEIGHT_METHOD,
                "base_edge": self.report.base_edge,
                "wall_vertical_from_rnd": self.report.wall_vertical_from_rnd,
                "corners_at_rim": self.report.corners_at_rim,
                "rim_across_points_cm": self.report.rim_across_points_cm,
                "inside_depth_cm": self.report.inside_depth_cm,
                "rnd11_height_cm": self.report.rnd11_height_cm},
            "findings": [{"code": f.code, "message": f.message, "severity": f.severity}
                         for f in self.findings],
            "assessed_at": self.assessed_at.isoformat(),
        }


def parts_made(cir, scope: str | None, made: dict | None) -> tuple[str, dict[str, int], bool]:
    """(scope, {component: count made}, whole pattern?) for a sample of `cir`, or ValueError.

    PHYSFIX G1. A sample is compared against the estimate for exactly what was made, so what
    was made is part of the record, and is never assumed:

    - `swatch`: no pieces. Gauge evidence only; never yardage evidence for anything.
    - `full_make`: every component, `Component.make` times each. A pattern of more than one
      piece must say so (`made`), and a `made` short of the whole is refused, never read as
      a whole: two coasters of four are not a coaster set.
    - `component`: the named pieces, each between 1 and its `make`. Its evidence class is
      always `partial_physical`, even when the pieces named add up to the whole (the third
      value returned, "whole pattern?", is then True: it says what was made, not what class
      the sample is recorded as).

    With no scope (the legacy intake) a sample is a full make, under the same rules.
    """
    full = {c.name: int(c.make or 1) for c in cir.components}
    key = str(scope or "full_make").strip().lower()
    if key not in SCOPES:
        raise ValueError(f"physical test scope {scope!r} is not one of {list(SCOPES)}")
    if made is not None and not isinstance(made, dict):
        raise ValueError("`made` must map a component name to how many were made")
    given: dict[str, int] = {}
    for name, count in (made or {}).items():
        if name not in full:
            raise ValueError(f"`made` names {name!r}, which is not a component of "
                             f"{cir.slug} ({sorted(full)})")
        try:
            n = int(count)
        except (TypeError, ValueError):
            raise ValueError(f"`made[{name!r}]` must be a whole number of pieces") from None
        if n != count and not (isinstance(count, float) and count == n):
            raise ValueError(f"`made[{name!r}]` must be a whole number of pieces")
        if n < 0 or n > full[name]:
            raise ValueError(f"`made[{name!r}]` = {count}: the pattern makes {full[name]}")
        if n:
            given[name] = n
    if key == "swatch":
        if given:
            raise ValueError("a swatch makes no pieces; record pieces with scope component")
        return key, {}, False
    if key == "full_make":
        if made is None:
            if sum(full.values()) > 1:
                raise ValueError(
                    f"{cir.slug} is {sum(full.values())} pieces ({full}); a full make must "
                    f"state `made`, so a partial set is never counted as the whole")
            return key, dict(full), True
        if given != full:
            raise ValueError(
                f"a full make of {cir.slug} is {full}; the sample made {given}. A partial "
                f"make is recorded with scope component, never as the whole pattern")
        return key, dict(full), True
    if not given:
        raise ValueError("a component sample must state `made`: which pieces, how many")
    return key, given, given == full


def estimate_for_parts(cir, result, made: dict[str, int]) -> dict[str, float]:
    """Estimated metres per colour for exactly the pieces made (uncalibrated)."""
    from ..cir.twin import build_twin

    makes = {c.name: int(c.make or 1) for c in cir.components}
    totals: dict[str, float] = {}
    for name, count in made.items():
        whole = build_twin(cir, result, component=name).yarn_metres_by_color
        for colour, metres in whole.items():
            totals[colour] = totals.get(colour, 0.0) + metres * count / makes[name]
    return {k: round(v, 1) for k, v in totals.items()}


def size_identity(cir) -> dict:
    """The one size a sample of `cir` covers: its release, and its size within a listing.

    A sample is one object worked from one text, so it covers exactly one size. A graded
    release names its size; a Launch-0 variant names its variant; anything else is the one
    size the release is. Nothing here extends a sample to another size (F-078: only a
    declared compatible variant could, and the intake does not take one)."""
    size, listing = "one size", None
    graded = getattr(cir, "graded", None)
    if graded is not None and getattr(graded, "size", None):
        size = str(graded.size)
    try:
        from ..products import launch0

        cand = launch0.candidate_for_cir(cir.slug)
        if cand is not None:
            listing = cand.slug
            for v in cand.variants:
                if launch0.cir_for(v.build).slug == cir.slug:
                    size = v.key if graded is None else size
                    break
    except Exception:  # noqa: BLE001 - outside Launch-0: the release is its own one size
        pass
    return {"slug": cir.slug, "version": cir.version, "size": size, "listing": listing}


def _is_flat_piece(cir, result, name: str) -> bool:
    from ..cir.twin import build_twin

    comp = next(c for c in cir.components if c.name == name)
    if comp.construction == "flat_rows":
        return True
    return build_twin(cir, result, component=name).shape == "disc"


def assess(report: SampleReport, twin, cir=None, result=None) -> SampleAssessment:
    """Compare one real sample against what the twin predicted for exactly what was made."""
    if cir is not None and result is None:
        from ..cir.compiler import compile_cir

        result = compile_cir(cir)
    out = SampleAssessment(
        report=report, estimated_metres={}, measured_metres=report.metres_by_color(),
        yarn=next((m.name for m in (cir.materials if cir else []) if m.name), None),
        stitch=(cir.gauge.stitch_type if cir is not None and cir.gauge else None))
    measured = out.measured_metres

    # What was made (PHYSFIX G1). Without the CIR, only the legacy whole-object reading.
    try:
        if cir is not None:
            out.scope, out.made, out.whole_pattern = parts_made(cir, report.scope, report.made)
            out.covers_size = size_identity(cir)
        elif report.scope not in (None, "full_make") or report.made is not None:
            raise ValueError("a sample of part of a pattern can only be assessed with its CIR")
    except ValueError as exc:
        out.findings.append(Finding("SAMPLE_SCOPE_INVALID", str(exc), "ERROR"))
        return out

    if report.size is not None and out.covers_size:
        named = report.size if isinstance(report.size, str) else None
        if named is None or "," in named or named.strip().lower() not in (
                str(out.covers_size.get("size", "")).lower(), cir.slug.lower()):
            out.findings.append(Finding(
                "SAMPLE_SIZE_NOT_THIS_RELEASE",
                f"the sheet names size {report.size!r}; this release is size "
                f"{out.covers_size.get('size')!r} ({cir.slug}@{cir.version}). A sample covers "
                f"exactly the one size it was worked in", "ERROR"))

    if out.scope == "swatch":
        _assess_swatch(out, report, cir)
    else:
        if cir is not None:
            out.estimated_metres = estimate_for_parts(cir, result, out.made)
        else:
            out.estimated_metres = dict(twin.yarn_metres_by_color)
        _assess_yarn(out, measured)
        size_twin = twin
        if cir is not None:
            size_twin = _measured_piece_twin(out, report, cir, result, twin)
        _assess_size(out, report, size_twin)
        _assess_observations(out, report)
        if cir is not None:
            _assess_pieces(out, report, cir, result)
            _assess_shape(out, report, cir, result)

    if report.instructions_followed is None:
        out.findings.append(Finding(
            "SAMPLE_FOLLOWED_UNRECORDED",
            "the record does not say whether the tester followed the written instructions "
            "exactly; unknown is not yes", "ERROR"))
    elif report.instructions_followed is not True:
        out.findings.append(Finding(
            "SAMPLE_DEVIATED",
            "the tester reports not following the written instructions, so neither the "
            "yardage nor the size measures what was published", "ERROR"))

    if report.problem_notes.strip():
        out.findings.append(Finding(
            "SAMPLE_PROBLEM_REPORTED",
            f"the tester recorded a problem, so this sample goes to the owner and does not "
            f"pass by itself: {report.problem_notes.strip()[:300]}", REVIEW))

    if report.notes.strip():
        # SECREVIEW F5: free text is read by a person, not parsed for "no problem". A tester
        # who writes a problem under notes instead of the problems box is still heard, so any
        # note routes the sample to the owner exactly as a recorded problem does.
        out.findings.append(Finding(
            "SAMPLE_TESTER_NOTES",
            f"the tester wrote notes, which go to the owner before this sample can count: "
            f"{report.notes.strip()[:300]}", REVIEW))

    return out


def _assess_yarn(out: SampleAssessment, measured: dict[str, float]) -> None:
    estimated = out.estimated_metres
    unknown = sorted(set(measured) - set(estimated))
    if unknown:
        out.findings.append(Finding(
            "SAMPLE_UNKNOWN_COLOUR",
            f"the sample reports yarn for {unknown}, which the pieces made do not use; either "
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
                f"measured yarn is {factor:.2f}x the estimate for the pieces made "
                f"({out.made}), which is outside the range a calibration can explain. Check "
                f"the ball band, the grams and which pieces were made before this changes "
                f"any published figure",
                "ERROR"))
    else:
        out.findings.append(Finding(
            "SAMPLE_NO_COMPARISON",
            "no colour in the sample matches a colour the pieces made are estimated to use, "
            "so there is nothing to calibrate against", "ERROR"))


def _measured_piece_twin(out, report, cir, result, whole_twin):
    """The twin of the piece the finished measurements are of."""
    from ..cir.twin import build_twin

    if report.measured_component:
        if report.measured_component not in out.made:
            out.findings.append(Finding(
                "SAMPLE_MEASURED_PIECE_UNKNOWN",
                f"the measurements are said to be of {report.measured_component!r}, which "
                f"the sample did not make ({out.made})", "ERROR"))
            return None
        return build_twin(cir, result, component=report.measured_component)
    if out.scope == "full_make":
        return whole_twin
    if len(out.made) == 1:
        return build_twin(cir, result, component=next(iter(out.made)))
    if any(getattr(report, k) is not None for k in
           ("measured_width_cm", "measured_height_cm", "measured_around_cm",
            "measured_flats_cm")):
        out.findings.append(Finding(
            "SAMPLE_MEASURED_PIECE_UNKNOWN",
            f"finished measurements were given for a sample of {sorted(out.made)} without "
            f"naming which piece they are of (`measured_component`)", "ERROR"))
    return None


def _assess_size(out: SampleAssessment, report: SampleReport, twin) -> None:
    # Size is falsification, not calibration.
    if twin is None:
        return
    claims = [("width", report.measured_width_cm, twin.width_cm),
              ("height", report.measured_height_cm, twin.height_cm),
              ("circumference", report.measured_around_cm, twin.circumference_cm),
              ("across the flats", report.measured_flats_cm,
               getattr(twin, "across_flats_cm", None))]
    _compare_sizes(out, [(label, m, p) for label, m, p in claims if m is not None and p])


def _compare_sizes(out: SampleAssessment, checked: list) -> None:
    if checked:
        out.size_agrees = out.size_agrees is not False
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


def _assess_observations(out: SampleAssessment, report: SampleReport) -> None:
    """The construction-review observations are typed: malformed is refused, never stored."""
    problems = []
    if report.base_edge is not None and report.base_edge not in BASE_EDGES:
        problems.append(f"base_edge {report.base_edge!r} is not one of {BASE_EDGES}")
    rnd = report.wall_vertical_from_rnd
    if report.base_edge == "rounded" and rnd is None:
        problems.append("a rounded base edge must say from which round the wall is upright")
    if rnd is not None and (isinstance(rnd, bool) or not isinstance(rnd, int) or rnd < 1):
        problems.append(f"wall_vertical_from_rnd {rnd!r} is not a round number")
    if report.corners_at_rim is not None and not isinstance(report.corners_at_rim, bool):
        problems.append(f"corners_at_rim {report.corners_at_rim!r} is not yes or no")
    for key in ("rim_across_points_cm", "inside_depth_cm", "rnd11_height_cm"):
        v = getattr(report, key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            problems.append(f"{key} {v!r} is not a measurement in cm")
    if problems:
        out.findings.append(Finding("SAMPLE_OBSERVATION_INVALID", "; ".join(problems),
                                    "ERROR"))


def _assess_pieces(out: SampleAssessment, report: SampleReport, cir, result) -> None:
    """SECREVIEW F6: each made piece measured in a checked field, against its own twin.

    A component made more than once must have one measurement per piece made, so a set of
    four is four checked sizes rather than one checked size and three lines of free text."""
    from ..cir.twin import build_twin

    pieces = list(report.piece_measurements or [])
    by_comp: dict[str, list] = {}
    for i, entry in enumerate(pieces, start=1):
        comp = (entry or {}).get("component") if isinstance(entry, dict) else None
        width = (entry or {}).get("width_cm") if isinstance(entry, dict) else None
        height = (entry or {}).get("height_cm") if isinstance(entry, dict) else None

        def _cm(v) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0

        # SECREVIEW R3: a height that is given must be a number, as the width must; a string
        # or a negative is refused, never skipped.
        if comp not in out.made or not _cm(width) or (height is not None and not _cm(height)):
            out.findings.append(Finding(
                "SAMPLE_PIECES_UNMEASURED",
                f"piece measurement {i} ({entry!r}) must name a made component and give its "
                f"width (and any height) in cm as numbers", "ERROR"))
            return
        by_comp.setdefault(comp, []).append(entry)
    for comp, count in out.made.items():
        have = len(by_comp.get(comp, []))
        if (count > 1 or have) and have != count:
            out.findings.append(Finding(
                "SAMPLE_PIECES_UNMEASURED",
                f"{count} x {comp} were made and {have} were measured; every piece is "
                f"measured in its own checked field", "ERROR"))
            return
    for comp, entries in by_comp.items():
        twin = build_twin(cir, result, component=comp)
        for n, entry in enumerate(entries, start=1):
            checked = [(f"{comp} {n} width", float(entry["width_cm"]), twin.width_cm)]
            if entry.get("height_cm") is not None:
                checked.append((f"{comp} {n} height", float(entry["height_cm"]),
                                twin.height_cm))
            _compare_sizes(out, [(lbl, m, p) for lbl, m, p in checked if p])


def _assess_shape(out: SampleAssessment, report: SampleReport, cir, result) -> None:
    """PHYSFIX G3: flat pieces must lie flat, 3-D pieces must hold their shape.

    The observation is required for every made piece's kind. Not recorded is an incomplete
    record (ERROR); recorded as failing is a made object with a problem, which goes to the
    owner as PARTIAL and never passes by itself."""
    kinds = {_is_flat_piece(cir, result, name) for name in out.made}
    # A "no" is a problem whichever piece it is about (a vessel's base that rocks, a flat
    # piece that will not keep its outline): it is never ignored because it was not required.
    if report.lies_flat is False and True not in kinds:
        out.findings.append(Finding(
            "SAMPLE_NOT_FLAT",
            "the tester reports a part that should sit flat does not (rocks, cups or ruffles); "
            "the owner reviews it", REVIEW))
    if report.holds_shape is False and False not in kinds:
        out.findings.append(Finding(
            "SAMPLE_SHAPE_NOT_HELD",
            "the tester reports the piece does not keep its shape; the owner reviews it",
            REVIEW))
    if True in kinds:
        if report.lies_flat is None:
            out.findings.append(Finding(
                "SAMPLE_SHAPE_UNRECORDED",
                "the sample includes a flat piece and the record does not say whether it "
                "lies flat", "ERROR"))
        elif report.lies_flat is False:
            out.findings.append(Finding(
                "SAMPLE_NOT_FLAT",
                "the tester reports a flat piece that does not lie flat (cups or ruffles); "
                "the pattern's shape claim is in question, so the owner reviews it", REVIEW))
    if False in kinds:
        if report.holds_shape is None:
            out.findings.append(Finding(
                "SAMPLE_SHAPE_UNRECORDED",
                "the sample includes a three-dimensional piece and the record does not say "
                "whether it holds its shape", "ERROR"))
        elif report.holds_shape is False:
            out.findings.append(Finding(
                "SAMPLE_SHAPE_NOT_HELD",
                "the tester reports a three-dimensional piece that does not hold its shape "
                "(collapses, leans or flares); the owner reviews it", REVIEW))


def _assess_swatch(out: SampleAssessment, report: SampleReport, cir) -> None:
    """A swatch is gauge evidence only: no factor, no finished size, no yardage claim."""
    if any(getattr(report, k) is not None for k in
           ("measured_width_cm", "measured_height_cm", "measured_around_cm",
            "measured_flats_cm")) or report.piece_measurements:
        out.findings.append(Finding(
            "SAMPLE_SCOPE_INVALID",
            "a swatch has no finished size; finished measurements belong to a made piece",
            "ERROR"))
    gauge = cir.gauge if cir is not None else None
    sts, rows = report.swatch_stitches_per_10cm, report.swatch_rows_per_10cm
    if gauge is None or sts is None or rows is None:
        out.findings.append(Finding(
            "SAMPLE_SWATCH_GAUGE_MISSING",
            "a swatch must record stitches and rows per 10 cm against the pattern's gauge",
            "ERROR"))
        return
    out.gauge_agrees = True
    for label, got, want in (("stitches", sts, gauge.stitches_per_10cm),
                             ("rows", rows, gauge.rows_per_10cm)):
        drift = abs(float(got) - want) / want
        if drift > GAUGE_DISAGREEMENT:
            out.gauge_agrees = False
            out.findings.append(Finding(
                "SAMPLE_GAUGE_DISAGREES",
                f"the swatch has {float(got):g} {label} per 10 cm where the pattern states "
                f"{want:g} ({drift:.0%} out)", "ERROR"))


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


def record(db, assessment: SampleAssessment, *, content_hash: str | None = None,
           evidence_class: str | None = None) -> int:
    """Store the sample. The row is the evidence; the assessment is what we concluded.

    `passed` is not "the tester liked it": it is whether this sample can be used, which
    means a plausible factor, a size that agrees with the claim, and instructions actually
    followed. A sample that fails still gets stored, because a disagreement is the most
    valuable thing a sample can produce.
    """
    from ..laura.private.firewall import reject_private

    # PRIV Step 4 (spec/07 Ruling 2): owner-private input never reaches this protected path.
    reject_private((assessment, content_hash, evidence_class), context="product_truth")
    from ..core.models import PhysicalTest

    measured = assessment.to_dict()
    if content_hash:
        # The text the tester worked against (F-078): what certification binds evidence to.
        measured["content_hash"] = content_hash
    # F-072: a swatch and a full make are different evidence and are never substituted. The
    # class is stamped on the row so binding reads it rather than inferring it later.
    from ..gates.risk_matrix import scope_to_class

    measured["evidence_class"] = evidence_class or scope_to_class(
        assessment.scope if assessment.report.scope is not None else None,
        measured_finished_size=assessment.size_agrees is not None)
    if (measured["evidence_class"] != PARTIAL_PHYSICAL_CLASS
            and not assessment.whole_pattern):
        # PHYSFIX G1: a partial make is never stamped as a whole-pattern make.
        raise ValueError(f"a sample of {assessment.made} is not the whole pattern and cannot "
                         f"be recorded as {measured['evidence_class']}")
    with db.session() as s:
        row = PhysicalTest(
            product_slug=assessment.report.product_slug,
            version=assessment.report.version,
            tester_ref=assessment.report.tester_ref,
            completed_at=assessment.assessed_at,
            # PHYSFIX: only a PASS passes. PARTIAL (a recorded problem) and FAIL are stored,
            # bind nothing and calibrate nothing.
            passed=assessment.outcome == PASS,
            measured=measured,
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


def size_coverage(db, cir) -> dict:
    """PHYSFIX G5: which sizes of this product's listing a passed sample physically proves.

    A sample covers exactly one size -- the release it was worked from, bound by content hash
    (`gates.certificate.bind_physical_evidence`). For a Launch-0 listing of several sizes each
    size is bound on its own; nothing is extended from one size to another. Outside a
    multi-size listing the release is its own one size."""
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..gates.certificate import _release_hash, bind_physical_evidence
    from ..runtime.pipeline import physical_evidence_rows

    me = size_identity(cir)
    members = [(me["size"], cir)]
    if me.get("listing"):
        from ..products import launch0

        members = [(v.key, cir if launch0.cir_for(v.build).slug == cir.slug
                    else launch0.cir_for(v.build))
                   for v in launch0.candidate(me["listing"]).variants]
    sizes = []
    for size, member in members:
        result = compile_cir(member)
        entry = {"size": size, "slug": member.slug, "version": member.version,
                 "proven": False, "samples": []}
        if result.ok:
            content = _release_hash(member, write_pattern(member, result, "US"))
            bound = bind_physical_evidence(physical_evidence_rows(db, member.slug),
                                           slug=member.slug, version=member.version,
                                           content_hash=content)
            # SECREVIEW F3: proven means a bound sample that proved the size -- made pieces
            # whose measurements agreed -- never a swatch or any other gauge-only sample.
            proof = list(bound.get("size_proven") or [])
            entry.update(proven=bool(proof), samples=proof,
                         gauge_only=[r for r in bound["bound"] if r not in proof],
                         content_hash=content[:12])
        sizes.append(entry)
    proven = [e["size"] for e in sizes if e["proven"]]
    return {"listing": me.get("listing") or cir.slug, "this_size": me["size"],
            "sizes": sizes, "proven": proven,
            "unproven": [e["size"] for e in sizes if not e["proven"]],
            "rule": "a physical sample covers exactly the one size it was worked in"}


# SECREVIEW R1 (42eac69): what a design digest covers -- only what decides the made object's
# finished size and shape. Everything else (title, notes, colour names and hexes, provenance,
# list order where order means nothing) is canonicalised away, so a cosmetic edit is the
# same design and never certifies past, or resolves, a size halt.
_PIECE_KEYS = ("construction", "foundation", "foundation_kind", "make", "holds", "resumes",
               "grain")
_ROW_KEYS = ("index", "declared_count", "turning_chain", "turning_chain_counts", "into",
             "allow_remainder", "skips")
_GAUGE_KEYS = ("stitches_per_10cm", "rows_per_10cm", "stitch_type", "hook_mm", "yarn_weight",
               "chains_per_10cm")
# Free text and labels: never geometry, at any depth.
_COSMETIC = frozenset({"note", "notes", "name", "title", "color", "colour", "colorway",
                       "color_id", "label", "description", "designer_notes"})


def _canon(value):
    """Drop cosmetic keys at any depth; sort dict keys (json does) and keep list order."""
    if isinstance(value, dict):
        return {k: _canon(v) for k, v in value.items() if k not in _COSMETIC}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, str):
        return value.strip()
    return value


def design_geometry(cir) -> dict:
    """The canonical geometry of a design: the input to `design_digest`.

    - every piece: construction, foundation, quantity (`make`), holds/resumes, grain, and each
      row/round's stitch ops and counts (`into`, skips, turning chains), in working order;
    - the gauge (stitches and rows per 10 cm, stitch, hook, yarn weight, chain gauge);
    - the yarn weights and fibres, as a sorted set (names, colourways and order dropped);
    - assembly, the size set (graded size and its matrix) and the represented configuration.

    Pieces are sorted by their canonical content, so naming or listing them in another order is
    the same design; rows keep their order, because working order is geometry."""
    body = cir.to_dict()
    pieces = []
    for comp in body.get("components") or []:
        piece = {k: _canon(comp.get(k)) for k in _PIECE_KEYS}
        piece["rows"] = [{**{k: _canon(r.get(k)) for k in _ROW_KEYS},
                          "ops": _canon(r.get("ops"))} for r in comp.get("rows") or []]
        pieces.append(piece)
    import json

    pieces.sort(key=lambda p: json.dumps(p, sort_keys=True, default=str))
    gauge = body.get("gauge") or {}
    materials = sorted({json.dumps({"yarn_weight": (m.get("yarn_weight") or "").strip().lower(),
                                    "fibre": sorted(str(f).strip().lower()
                                                    for f in (m.get("fibre_content") or ()))},
                                   sort_keys=True)
                        for m in body.get("materials") or []})
    graded = body.get("graded") or {}
    return {
        "construction": _canon(body.get("construction")),
        "pieces": pieces,
        "gauge": {k: gauge.get(k) for k in _GAUGE_KEYS},
        "materials": materials,
        "assembly": _canon(body.get("assembly") or []),
        "sizes": {"size": graded.get("size"), "ease_cm": _canon(graded.get("ease_cm")),
                  "matrix": _canon(graded.get("sizes"))} if graded else None,
        "variant": dict(getattr(cir, "represented_variant", {}) or {}),
    }


def design_digest(cir, result=None) -> str | None:
    """SECREVIEW F1/R1: what a release IS for its size claim, independent of its labels.

    `gates.certificate._release_hash` covers the whole CIR, version and title included, so a
    relabel or a retitle of identical geometry is "different content". A size halt is a
    statement about the made object, so it is keyed on `design_geometry` alone: a version,
    title, whitespace, notes, colour-name or list-order change is the same design.
    Unreadable or uncompilable is None, and callers fail closed."""
    import hashlib
    import json

    try:
        from ..cir.compiler import compile_cir

        result = result if result is not None else compile_cir(cir)
        if not result.ok:
            return None
        payload = json.dumps(design_geometry(cir), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
    except Exception:  # noqa: BLE001 - unreadable design: callers fail closed
        return None
