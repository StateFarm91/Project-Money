"""Risk-based physical evidence: which products need a tester's hands, how much, and when.

Master Plan v1.0 section 8 (F-072, F-073, F-078, F-080, F-081, F-086) and section 12 (F-117).

Section 8 replaces "the owner must crochet a sample" with a risk-based evidence requirement.
That has three halves, and this module is all three so they cannot drift apart:

**Evidence classes are distinct (F-072).** A digital twin, a teardown of somebody else's
pattern, a model looking at a render, a human reading the text, a tester working a swatch and a
tester making the whole object establish *different things*. They are named here once, each
with what it can establish, and `satisfies` is the only substitution rule: a full make
satisfies a partial-physical requirement (it contains one), and nothing else substitutes for
anything. A benchmark teardown never stands in for our own physical evidence (F-079).

**The minimum evidence is derived from the product, not typed in (F-073).** `features` reads
the CIR and its twin for the things section 8 names -- body-sized wearables, grading,
dimensional and closed 3-D forms, multi-seam assemblies, high-yardage claims, uncalibrated
primitives -- and each sets a floor on the risk class. The effective class is the higher of
the declared class and the derived floor. A declared class can raise the floor (a fitted
garment is declared C by its generator from its ease, which the CIR does not carry); it can
never lower it.

**Low risk does not need a full make (F-080).** Class A clears on deterministic evidence when
the `automated_threshold` criteria are all met: it compiles, an independent reverse compile of
the written text agrees, every stated finished dimension is inside tolerance of the twin
(F-117), every stitch is a convention or calibrated primitive, and the gauge sits in the
declared yarn's published band. Class B needs a partial physical test (a gauge/yardage swatch
or a component) of this exact content; Class C needs a full physical make of it. "This exact
content" is `gates.certificate.bind_physical_evidence` -- the content hash (F-078).

What this module never does: create, infer or assume physical evidence. A product whose
required evidence is missing stays blocked, and `owner_action_spec` writes the request in the
Execution Directive's format (exact action, why, maximum cost, minutes, consequence of delay).
The owner is not the tester (F-071): the action the owner takes is approving the spend for an
independent tester, never crocheting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- evidence classes (F-072) ----------------------------------------------------------

DETERMINISTIC = "deterministic"
BENCHMARK_TEARDOWN = "benchmark_teardown"
MODEL_VISUAL_REVIEW = "model_visual_review"
INDEPENDENT_HUMAN_REVIEW = "independent_human_review"
PARTIAL_PHYSICAL = "partial_physical"
FULL_PHYSICAL_MAKE = "full_physical_make"


@dataclass(frozen=True)
class EvidenceClass:
    key: str
    what: str
    establishes: tuple[str, ...]
    cannot_establish: tuple[str, ...]


EVIDENCE_CLASSES: tuple[EvidenceClass, ...] = (
    EvidenceClass(DETERMINISTIC,
                  "compile, independent reverse compile and digital twin of this content",
                  ("stitch counts", "text-structure agreement", "computed dimensions"),
                  ("real gauge", "drape", "fit", "real yardage", "make time")),
    EvidenceClass(BENCHMARK_TEARDOWN,
                  "a purchased competitor pattern taken apart for market expectations",
                  ("customer-experience standards", "market expectations"),
                  ("that our counts, yardage, sizing or assembly physically work (F-079)",)),
    EvidenceClass(MODEL_VISUAL_REVIEW,
                  "a model's review of renders or text",
                  ("presentation defects a reader would notice",),
                  ("anything physical", "that a human can follow the text")),
    EvidenceClass(INDEPENDENT_HUMAN_REVIEW,
                  "a person other than the generator reads the customer-facing text",
                  ("readability", "ambiguity"),
                  ("real gauge", "real yardage", "fit", "drape")),
    EvidenceClass(PARTIAL_PHYSICAL,
                  "an independent tester works a gauge/yardage swatch or one component",
                  ("real gauge", "per-stitch yardage", "primitive calibration"),
                  ("whole-object size", "assembly", "fit", "full make time")),
    EvidenceClass(FULL_PHYSICAL_MAKE,
                  "an independent tester makes the whole object from the customer text",
                  ("real gauge", "real yardage", "finished size", "assembly", "fit", "drape",
                   "make time"),
                  ("that it comes out for every maker at every gauge",)),
)
CLASS_BY_KEY: dict[str, EvidenceClass] = {c.key: c for c in EVIDENCE_CLASSES}

# The only substitution: a full make contains a swatch-level measurement of the same content.
_CONTAINS: dict[str, frozenset[str]] = {FULL_PHYSICAL_MAKE: frozenset({PARTIAL_PHYSICAL})}

# What a tester reports as the scope of a physical test, and the class it is.
SCOPE_CLASS: dict[str, str] = {
    "full_make": FULL_PHYSICAL_MAKE,
    "swatch": PARTIAL_PHYSICAL,
    "component": PARTIAL_PHYSICAL,
}


def satisfies(held: str, required: str) -> bool:
    """Whether evidence of class `held` meets a requirement for class `required` (F-072)."""
    if held not in CLASS_BY_KEY or required not in CLASS_BY_KEY:
        raise ValueError(f"unknown evidence class: {held!r} / {required!r}")
    return held == required or required in _CONTAINS.get(held, frozenset())


def scope_to_class(scope: str | None, *, measured_finished_size: bool) -> str:
    """The evidence class of a physical test from its reported scope.

    An explicit scope wins. With none, a sample that reported a finished measurement of the
    product is a full make (that is what the size comparison measured); one that reported only
    yarn used is partial. Unknown scope words are refused, never guessed.
    """
    if scope:
        key = str(scope).strip().lower()
        if key not in SCOPE_CLASS:
            raise ValueError(f"physical test scope {scope!r} is not one of {sorted(SCOPE_CLASS)}")
        if SCOPE_CLASS[key] == FULL_PHYSICAL_MAKE and not measured_finished_size:
            # F-076: a full make records its actual dimensions; without them it cannot
            # establish the size claim that is the point of a full make.
            raise ValueError("a full_make physical test must report a finished measurement")
        return SCOPE_CLASS[key]
    return FULL_PHYSICAL_MAKE if measured_finished_size else PARTIAL_PHYSICAL


def physical_class_of(measured: dict | None) -> tuple[str, bool]:
    """(evidence class, legacy_unstamped) of a stored PhysicalTest's `measured` payload.

    Rows written by `physical.record` from this version on carry `evidence_class`. A row
    without it predates the stamp: `physical.record` then took one sample *of the product*
    and compared it against the whole-object twin, so it is read as a full make and flagged
    `legacy_unstamped` so the reading is visible rather than silent.
    """
    measured = measured or {}
    cls = measured.get("evidence_class")
    if cls in (PARTIAL_PHYSICAL, FULL_PHYSICAL_MAKE):
        return cls, False
    return FULL_PHYSICAL_MAKE, True


# Customer-facing phrases that claim one specific evidence class. Checked against the classes
# actually held, so a swatch never licenses "made by a tester" and a teardown never licenses
# "tested" (F-072 "never substitute one class while claiming another").
CLAIM_PHRASES: dict[str, str] = {
    "swatch tested": PARTIAL_PHYSICAL,
    "gauge tested": PARTIAL_PHYSICAL,
    "test made": FULL_PHYSICAL_MAKE,
    "tester made": FULL_PHYSICAL_MAKE,
    "made by a tester": FULL_PHYSICAL_MAKE,
    "maker tested": FULL_PHYSICAL_MAKE,
    "test crocheted": FULL_PHYSICAL_MAKE,
    "physically tested": FULL_PHYSICAL_MAKE,
    "tech edited": INDEPENDENT_HUMAN_REVIEW,
    "technically edited": INDEPENDENT_HUMAN_REVIEW,
    "human reviewed": INDEPENDENT_HUMAN_REVIEW,
}


def claim_refusals(text: str, held: set[str] | frozenset[str]) -> list[dict]:
    """Every class-specific claim in `text` that the held evidence classes do not support."""
    low = (text or "").lower()
    out = []
    for phrase, needs in sorted(CLAIM_PHRASES.items()):
        if phrase in low and not any(satisfies(h, needs) for h in held if h in CLASS_BY_KEY):
            out.append({"phrase": phrase, "needs": needs, "held": sorted(held),
                        "why": (f"{phrase!r} claims {CLASS_BY_KEY[needs].what}; the evidence "
                                f"held is {sorted(held) or 'none'}, and no other class may "
                                f"stand in for it (F-072)")})
    return out


# ---- the matrix (F-073) ------------------------------------------------------------------

RANK = {"A": 0, "B": 1, "C": 2}

# Required physical evidence per effective class. None = deterministic evidence at the
# automated threshold (F-080).
REQUIRED_PHYSICAL: dict[str, str | None] = {
    "A": None, "B": PARTIAL_PHYSICAL, "C": FULL_PHYSICAL_MAKE,
}

# Above this many metres the +/-20% uncalibrated tolerance is ~100 m or more -- about half a
# standard 100 g worsted ball -- so the yardage figure decides how many balls a buyer buys and
# is a high-yardage claim needing a measured per-stitch figure (F-073, F-075, F-084).
HIGH_YARDAGE_M = 500.0

# More seams than this is an assembly a buyer can get wrong in ways no per-piece check sees.
NOVEL_ASSEMBLY_SEAMS = 3

# Twin shapes that are three-dimensional objects rather than flat fabric.
DIMENSIONAL_SHAPES = frozenset({"vessel", "tube", "cone", "dome", "shaped", "gathered"})

GRADING_MARKERS = ("cir.graded", "grading", "graded")


@dataclass(frozen=True)
class Feature:
    key: str
    floor: str          # minimum risk class this feature imposes
    detail: str
    requirement: str    # which row of section 8 names it

    def to_dict(self) -> dict:
        return {"key": self.key, "floor": self.floor, "detail": self.detail,
                "requirement": self.requirement}


def _is_wearable(cir) -> bool:
    note = (cir.finished_size_note or "").lower()
    return "to fit" in note or any(c.holds for c in cir.components) or any(
        getattr(c, "resumes", None) for c in cir.components)


def features(cir, twin_summary: dict | None, primitive_status: dict | None = None,
             calibrated_primitives=frozenset()) -> list[Feature]:
    """The section 8 risk features this product actually has, each with its class floor."""
    out: list[Feature] = []
    if _is_wearable(cir):
        out.append(Feature("body_sized_wearable", "B",
                           "sized to a body (a 'to fit' measurement or an armhole hold); a "
                           "fitted one is declared C by its generator from its ease", "F-073/F-081"))
    prims = tuple(getattr(cir.provenance, "primitives_used", ()) or ()) if cir.provenance else ()
    if any(m in p for p in prims for m in GRADING_MARKERS):
        out.append(Feature("graded", "B", "one size of a graded design", "F-073"))
    if any(s.stuff_before_closing for s in cir.assembly):
        out.append(Feature("closed_3d_form", "C",
                           "stuffed and closed: a complex dimensional form whose shape only "
                           "a full make shows", "F-073/F-081"))
    shape = (twin_summary or {}).get("shape")
    if shape in DIMENSIONAL_SHAPES:
        out.append(Feature("dimensional_form", "B",
                           f"the twin reads this as a {shape}, not flat fabric", "F-073"))
    if len(cir.assembly) > NOVEL_ASSEMBLY_SEAMS:
        out.append(Feature("multi_seam_assembly", "B",
                           f"{len(cir.assembly)} seams (> {NOVEL_ASSEMBLY_SEAMS})", "F-073"))
    metres = sum(((twin_summary or {}).get("yarn_metres") or {}).values())
    if metres > HIGH_YARDAGE_M:
        out.append(Feature("high_yardage", "B",
                           f"{metres:.0f} m estimated (> {HIGH_YARDAGE_M:.0f} m), where the "
                           f"uncalibrated tolerance is a ball or more", "F-073/F-075"))
    status = (primitive_status or {}).get("status") or {}
    new = sorted(code for code, st in status.items()
                 if st == "uncalibrated" and code not in calibrated_primitives)
    if new:
        out.append(Feature("uncalibrated_primitive", "B",
                           f"{new} have no physical calibration", "F-073/F-074"))
    return out


def assess(cir, *, twin_summary: dict | None, primitive_status: dict | None = None,
           calibrated_primitives=frozenset()) -> dict:
    """Derived, declared and effective risk class, and the minimum evidence it requires."""
    feats = features(cir, twin_summary, primitive_status, calibrated_primitives)
    derived = max((f.floor for f in feats), key=RANK.__getitem__, default="A")
    declared = cir.risk_class if cir.risk_class in RANK else "C"
    effective = max(declared, derived, key=RANK.__getitem__)
    required = [DETERMINISTIC] + ([REQUIRED_PHYSICAL[effective]]
                                  if REQUIRED_PHYSICAL[effective] else [])
    return {
        "declared": declared, "derived": derived, "effective": effective,
        "raised_by_matrix": RANK[derived] > RANK[declared],
        "features": [f.to_dict() for f in feats],
        "required_evidence": required,
        "required_physical": REQUIRED_PHYSICAL[effective],
        "basis": ("derived from the CIR and its twin by gates.risk_matrix.features; the "
                  "effective class is max(declared, derived)"),
    }


def automated_threshold(matrix: dict, *, compiled: bool, reverse_agrees: bool,
                        error_codes: set[str]) -> dict:
    """F-080: whether deterministic evidence alone meets the defined confidence threshold.

    Every criterion is a measurement this certification run made. Only an effective Class A
    product can qualify: B and C need physical evidence by definition (F-073).
    """
    criteria = [
        {"key": "effective_class_a", "met": matrix["effective"] == "A",
         "why": f"effective class {matrix['effective']}"},
        {"key": "compiles", "met": bool(compiled), "why": "deterministic compile"},
        {"key": "reverse_compile_agrees", "met": bool(reverse_agrees),
         "why": "independent reverse compile of the written text"},
        {"key": "twin_plausible",
         "met": not (error_codes & {"TWIN_DIMENSION_IMPLAUSIBLE", "TWIN_DIMENSION_UNSUPPORTED"}),
         "why": "stated finished dimensions inside tolerance of the twin (F-117)"},
        {"key": "primitives_proven",
         "met": "UNCALIBRATED_PRIMITIVE" not in error_codes and not any(
             f["key"] == "uncalibrated_primitive" for f in matrix["features"]),
         "why": "every stitch a convention or calibrated primitive"},
        {"key": "gauge_evidenced",
         "met": not (error_codes & {"GAUGE_OUTSIDE_DECLARED_YARN_BAND",
                                    "GAUGE_WITHOUT_YARN_EVIDENCE"}),
         "why": "gauge inside the declared yarn's published band"},
    ]
    return {"qualifies": all(c["met"] for c in criteria), "criteria": criteria,
            "unmet": [c["key"] for c in criteria if not c["met"]]}


def bound_classes(binding: dict | None) -> list[str]:
    """The physical evidence classes bound to this content by `bind_physical_evidence`."""
    return sorted({c for c in ((binding or {}).get("bound_classes") or {}).values()})


def requirement_status(matrix: dict, binding: dict | None, *,
                       automated: dict | None = None) -> dict:
    """Whether the required evidence for this product is held for this exact content."""
    need = matrix.get("required_physical")
    held = bound_classes(binding)
    if need is None:
        met = True if automated is None else bool(automated.get("qualifies"))
        why = ("deterministic evidence meets the automated threshold (F-080)" if met else
               f"Class A but the automated threshold is unmet: {automated.get('unmet')}")
        return {"met": met, "required": DETERMINISTIC, "held": held, "why": why}
    met = any(satisfies(h, need) for h in held)
    invalidated = [u for u in (binding or {}).get("unbound") or []
                   if str(u.get("why", "")).startswith("invalidated")]
    why = (f"{need} of this content is bound ({held})" if met else
           f"effective class {matrix['effective']} requires {need} of this exact content "
           f"({str((binding or {}).get('content_hash') or '')[:12]}); held: {held or 'none'}"
           + ("; earlier evidence was invalidated by a material change -- re-test required"
              if invalidated else ""))
    return {"met": met, "required": need, "held": held, "why": why,
            "retest_required": bool(invalidated) and not met}


# ---- the owner action, in the Directive's format -----------------------------------------

# ESTIMATED, not sourced: no tester has been paid yet, so there is no measured rate. These are
# ceilings for the owner to approve or lower, never figures to report as spend.
TESTER_FEE_CAD_PER_HOUR = 20.0
YARN_CAD_PER_METRE = 0.06
SWATCH_TESTER_HOURS = 1.5
SWATCH_YARN_METRES = 40.0
# A full make with no make-time estimate is priced on this conservative ceiling, never on the
# swatch's hours (which would under-state the approval the owner is asked for).
FULL_MAKE_FALLBACK_HOURS = 12.0
FULL_MAKE_FALLBACK_METRES = 300.0
# What the owner spends: reading the request, approving the ceiling, and nothing physical.
OWNER_MINUTES = 5


def retest_key(slug: str, version: str, content_hash: str | None) -> str:
    return f"physical_evidence:{slug}@{version}:{(content_hash or '')[:12]}"


def owner_action_spec(*, slug: str, version: str, content_hash: str | None, required: str,
                      effective_class: str, make_hours: float | None,
                      yarn_metres: float | None, retest: bool = False) -> dict:
    """The owner request for a missing physical requirement (exact what/why/cost/minutes).

    The owner approves commissioning an independent tester (F-071, F-085): the spend is the
    owner's decision; the crocheting is never the owner's labour.
    """
    full = required == FULL_PHYSICAL_MAKE
    if full:
        hours = float(make_hours) * 1.3 if make_hours else FULL_MAKE_FALLBACK_HOURS
        metres = float(yarn_metres) * 1.2 if yarn_metres else FULL_MAKE_FALLBACK_METRES
    else:
        hours, metres = SWATCH_TESTER_HOURS, SWATCH_YARN_METRES
    cost = round(hours * TESTER_FEE_CAD_PER_HOUR + metres * YARN_CAD_PER_METRE, 2)
    scope = ("make the whole object" if full else
             "work a 15 x 15 cm gauge/yardage swatch (or the named component)")
    return {
        "requirement_key": retest_key(slug, version, content_hash),
        "action": (f"Approve commissioning one independent tester (not the owner) to {scope} "
                   f"from the customer PDF of {slug}@{version} (content "
                   f"{(content_hash or 'unknown')[:12]}), then record the result through the "
                   f"physical.record job with scope "
                   f"{'full_make' if full else 'swatch'}, grams per colour, ball band, hook "
                   f"and finished measurements. Maximum CA${cost:.2f}."),
        "reason": ((f"{'Re-test: a material change invalidated the earlier evidence. ' if retest else ''}"
                    f"Effective risk class {effective_class} requires {required} of this exact "
                    f"content before live sale (F-073/F-078/F-081); nothing computed can stand "
                    f"in for it (F-072).")),
        "max_cost_cad": cost,
        "minutes": OWNER_MINUTES,
        "consequence_of_delay": (f"{slug}@{version} stays blocked from live sale; its size "
                                 f"and yardage claims stay estimates."),
        "blocks": f"live sale of {slug}@{version}",
        "cost_basis": (f"ESTIMATED ceiling: {hours:.1f} tester hours at "
                       f"CA${TESTER_FEE_CAD_PER_HOUR:.0f}/h + {metres:.0f} m yarn at "
                       f"CA${YARN_CAD_PER_METRE:.2f}/m; no measured tester rate exists"),
        "tester_hours": round(hours, 1),
    }


# ---- twin plausibility (F-117) ------------------------------------------------------------

# How far a stated finished dimension may sit from the twin's figure. The notes are written
# from the twin and rounded, so a larger drift is a stale or wrong statement, not rounding.
DIMENSION_TOLERANCE = 0.10

# "about 16.0 cm", "Finished chest 93 cm", "length 57 cm", "measures 44 cm" -- a stated
# finished dimension. "to fit chest 73.5 cm" is a body measurement and is excluded.
_DIM_RE = re.compile(
    r"(to fit\s+)?(?:about|approximately|measures|finished\s+\w+|length|width|chest)"
    r"\s+(\d+(?:\.\d+)?)\s*cm", re.IGNORECASE)


def stated_dimensions(note: str | None) -> list[float]:
    return [float(m.group(2)) for m in _DIM_RE.finditer(note or "") if not m.group(1)]


def plausibility_findings(cir, twins: dict) -> list:
    """Every stated finished dimension must lie within tolerance of a twin-derived figure."""
    from ..cir.compiler import ERROR, Finding

    stated = stated_dimensions(cir.finished_size_note)
    if not stated or cir.authored == "benchmark":
        return []
    figures: list[float] = []
    refusal = None
    for t in twins.values():
        refusal = refusal or getattr(t, "size_refusal", None)
        for name in ("width_cm", "height_cm", "circumference_cm", "across_points_cm",
                     "across_flats_cm"):
            v = getattr(t, name, None)
            if v:
                figures.append(float(v))
    if _is_wearable(cir):
        # A garment's chest and length are not one piece's width and height (a drop-shoulder
        # body is worked over the shoulder; a raglan yoke divides for the sleeves), so they
        # are measured from the compiled rows by the garment module's own instrument.
        try:
            from ..products.garments import built_measures

            figures += [float(v) for v in built_measures(cir).values() if v]
        except Exception:  # noqa: BLE001 - not a generator garment: piece figures only
            pass
    out = []
    if not figures:
        return [Finding(ERROR, "TWIN_DIMENSION_UNSUPPORTED", (
            f"the finished size note states {stated} cm but the twin gives no dimension"
            f"{(' (' + str(refusal) + ')') if refusal else ''}; compilation alone cannot "
            f"certify a size (F-117)"))]
    for value in stated:
        best = min(figures, key=lambda f: abs(f - value))
        drift = abs(best - value) / max(value, 1e-9)
        if drift > DIMENSION_TOLERANCE:
            out.append(Finding(ERROR, "TWIN_DIMENSION_IMPLAUSIBLE", (
                f"the pattern states a finished {value:g} cm; the nearest twin figure is "
                f"{best:.1f} cm ({drift:.0%} out, tolerance {DIMENSION_TOLERANCE:.0%}). A "
                f"pattern that compiles and states the wrong size is not certifiable (F-117)")))
    return out


# ---- standalone use: readiness, the first-customer gate, the tester plan -----------------

def matrix_for(cir, result=None, *, calibrated_primitives=frozenset()) -> dict:
    """The matrix for a CIR outside certification, computed the way `certify` computes it."""
    from ..cir import assembly as _assembly
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from .certificate import primitive_findings, twin_summary

    result = result if result is not None else compile_cir(cir)
    if not result.ok:
        return {"declared": cir.risk_class, "derived": None, "effective": "C",
                "raised_by_matrix": False, "features": [],
                "required_evidence": [DETERMINISTIC, FULL_PHYSICAL_MAKE],
                "required_physical": FULL_PHYSICAL_MAKE,
                "basis": "does not compile: nothing is derivable, so the strictest class holds"}
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    block = twin_summary(cir, twins, _assembly.assemble(cir, twins))
    status, _ = primitive_findings(cir, physically_evidenced=False,
                                   calibrated_primitives=calibrated_primitives)
    return assess(cir, twin_summary=block, primitive_status=status,
                  calibrated_primitives=calibrated_primitives)


def first_customer_requirement(matrix: dict, binding: dict | None) -> dict:
    """What the first-customer gate needs: at least a partial physical test of this content,
    and a full make where the effective class needs one.

    The first paid products carry extraordinary scrutiny (gates.first_customer), so even a
    Class A product needs *some* measured sample before its size claims clear there; F-080
    still holds -- nothing below Class C is forced to a full make.
    """
    need = matrix.get("required_physical") or PARTIAL_PHYSICAL
    held = bound_classes(binding)
    met = any(satisfies(h, need) for h in held)
    return {"required": need, "effective_class": matrix.get("effective"), "held": held,
            "met": met,
            "why": (f"{need} of this content is bound" if met else
                    f"effective class {matrix.get('effective')} needs {need} of this exact "
                    f"content before a first customer; held: {held or 'none'}")}


def catalogue_status(db) -> dict:
    """Every certified release's risk tier and whether its required evidence is held (F-086).

    Read from the stored certificate where it carries a matrix; a certificate issued before
    the matrix existed is recomputed from its stored CIR rather than read as "no requirement".
    Evidence is re-bound live against the certificate's content hash, so a sample recorded
    after certification counts and an invalidated one does not.
    """
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product
    from ..runtime.pipeline import physical_evidence_rows
    from .certificate import bind_physical_evidence

    rows: list[dict] = []
    with db.session() as s:
        slugs = {p.id: p.slug for p in s.scalars(select(Product))}
        certified = [(slugs.get(pv.product_id), pv.version, pv.cir_json, pv.certificate)
                     for pv in s.scalars(select(PatternVersion).where(
                         PatternVersion.certified == True))]  # noqa: E712
    for slug, version, cir_json, cert in certified:
        if slug is None:
            continue
        cert = cert or {}
        matrix = cert.get("risk_matrix")
        source = "certificate"
        if not matrix:
            try:
                matrix = matrix_for(CIR.from_dict(cir_json))
                source = "recomputed (certificate predates the matrix)"
            except Exception as exc:  # noqa: BLE001 - unreadable record: strictest class
                matrix = {"effective": "C", "required_physical": FULL_PHYSICAL_MAKE,
                          "features": [], "declared": None, "derived": None}
                source = f"unreadable stored CIR ({type(exc).__name__}): strictest class"
        content = cert.get("content_hash") or cert.get("release_hash")
        binding = (bind_physical_evidence(physical_evidence_rows(db, slug), slug=slug,
                                          version=version, content_hash=content)
                   if content else None)
        automated = matrix.get("automated_threshold")
        status = requirement_status(matrix, binding, automated=automated)
        if not content:
            status = {**status, "met": False if matrix.get("required_physical") else
                      status["met"], "why": status["why"] + "; no content hash on file"}
        twin = cert.get("twin") or {}
        row = {"slug": slug, "version": version, "effective_class": matrix.get("effective"),
               "declared_class": matrix.get("declared"), "derived_class": matrix.get("derived"),
               "features": [f.get("key") for f in matrix.get("features") or []],
               "required": status["required"], "held": status["held"], "met": status["met"],
               "why": status["why"], "matrix_source": source,
               "content_hash": (content or "")[:12]}
        if not status["met"] and status["required"] != DETERMINISTIC:
            hours = None
            if status["required"] == FULL_PHYSICAL_MAKE:
                # A full make is priced on the product's own make time, never the swatch's.
                try:
                    from ..cir.compiler import compile_cir
                    from ..seasonal.leadtime import estimate_for

                    _cir = CIR.from_dict(cir_json)
                    hours = estimate_for(_cir, compile_cir(_cir)).hours
                except Exception:  # noqa: BLE001 - no estimate: the fallback ceiling stands
                    hours = None
            row["owner_action_spec"] = owner_action_spec(
                slug=slug, version=version, content_hash=content,
                required=status["required"], effective_class=matrix.get("effective", "C"),
                make_hours=hours,
                yarn_metres=sum((twin.get("yarn_metres") or {}).values()) or None,
                retest=bool(status.get("retest_required")))
        rows.append(row)
    unmet = [r for r in rows if not r["met"]]
    by_class: dict[str, int] = {}
    for r in rows:
        by_class[r["effective_class"]] = by_class.get(r["effective_class"], 0) + 1
    return {"products": rows, "unmet": [f"{r['slug']}@{r['version']}" for r in unmet],
            "by_effective_class": by_class,
            "ready": bool(rows) and not unmet,
            "note": ("no certified release: nothing has a risk tier yet" if not rows else
                     f"{len(unmet)} of {len(rows)} certified release(s) lack the physical "
                     f"evidence their risk tier requires")}
