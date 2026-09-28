"""Quality Release Certificate (Master Plan sections 2, 17, 36).

The release chain, in one place, with a single honest verdict at the end:

    CIR -> Compiler -> Digital Twin -> Written Pattern -> Reverse Compiler
        -> Asset Truth -> Policy -> Certificate

Any unresolved arithmetic error, invalid repeat, reverse-compile mismatch, unsupported claim,
asset misrepresentation, IP concern or policy failure blocks the release. The certificate is
not a summary of how it went; it is the thing that either exists or does not.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..cir import assembly as _assembly
from ..cir import specification as _specification
from ..cir.compiler import ERROR, WARNING, Finding, compile_cir
from ..cir.model import CIR
from ..cir.reverse import compare as reverse_compare
from ..cir.twin import TwinModel, build_twin
from ..cir.writer import write_pattern
from .asset_truth import (
    Asset, check_assets, check_shape_claims, check_technique_claims,
)
from .confidence import assess
from . import originality as _originality
from .policy import (
    POLICY_VERSION, ListingDraft, check_listing, check_originality, check_text,
)


# The customer-facing document's own version. The CIR is the design; this is the rendering of
# it, and the certificate covers both -- the release hash is taken over the CIR *and* the
# written text. So when the writer's output changes (row colours named, a construction line
# added, repeats collapsed), every certificate issued before that describes a document that no
# longer exists. Bumping this makes certification re-run for products already certified, which
# is the only way the stored certificate keeps matching the PDF a buyer would download.
DOC_VERSION = "2"


@dataclass
class ReleaseCertificate:
    slug: str
    version: str
    granted: bool
    release_hash: str | None
    findings: list[Finding] = field(default_factory=list)
    stages_run: list[str] = field(default_factory=list)
    confidence: dict | None = None
    pattern_text: str | None = None
    twin_summary: dict | None = None
    policy_version: str = POLICY_VERSION
    # Which version of *Etsy's* rules this was read against (#39). `policy_version` answers
    # the same question about our own rules, and it is the other one that changes without
    # telling us -- a certificate that cannot name it cannot be re-examined after the
    # platform moves, which is the only time anybody wants to.
    platform_policy: dict | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    physical_test_required: bool = False
    physical_test_passed: bool = False
    # The hash of the content this run examined -- the CIR and the written text -- whether or
    # not the certificate was granted. `release_hash` exists only on a grant, and a Class C
    # pattern cannot be granted until a tester has worked it, so the tester needs a name for
    # the exact text they were handed before any grant exists (F-078). It is the same digest
    # a grant would carry, so evidence bound to it is bound to the release.
    content_hash: str | None = None
    # Which physical evidence this run bound, and which it refused and why (F-078).
    physical_evidence: dict | None = None
    # The gauge standard this certificate was examined under (F-112/F-116/F-119). A stored
    # certificate without it predates the yarn-band check and is legacy by construction.
    gauge_standard: str | None = None
    # Per-primitive calibration status of every stitch this pattern uses (F-074).
    primitives: dict | None = None

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def blocking_reasons(self) -> list[str]:
        return [str(f) for f in self.errors]

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "version": self.version,
            "doc_version": DOC_VERSION,
            "granted": self.granted,
            "release_hash": self.release_hash,
            "stages_run": self.stages_run,
            "confidence": self.confidence,
            "policy_version": self.policy_version,
            "platform_policy": self.platform_policy,
            "issued_at": self.issued_at.isoformat(),
            "physical_test_required": self.physical_test_required,
            "physical_test_passed": self.physical_test_passed,
            "content_hash": self.content_hash,
            "physical_evidence": self.physical_evidence,
            "gauge_standard": self.gauge_standard,
            "primitives": self.primitives,
            "findings": [
                {"severity": f.severity, "code": f.code, "message": f.message,
                 "component": f.component, "row": f.row}
                for f in self.findings
            ],
            "twin": self.twin_summary,
        }

    def __str__(self) -> str:
        if self.granted:
            return f"CERTIFIED {self.slug}@{self.version} ({self.release_hash[:12]})"
        return (f"BLOCKED {self.slug}@{self.version}: "
                + "; ".join(self.blocking_reasons[:5]))


def _release_hash(cir: CIR, pattern_text: str) -> str:
    payload = json.dumps(
        {"cir": cir.to_dict(), "text": pattern_text}, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# Every stage the release chain can run, in the order it runs them. Three are conditional on
# the product -- geometry on a closed form, asset_truth and policy on a listing existing --
# and the rest always run. Named here so another module can state what the full chain is
# without reimplementing it: the fast lane (#291) shortens the queue and never this list, and
# a copy of the list somewhere else is how that guarantee would quietly stop being true.
CANONICAL_STAGES: tuple[str, ...] = (
    "compile", "specification", "twin", "assembly", "geometry", "write", "reverse",
    "originality", "asset_truth", "policy", "physical_test", "confidence",
)

CONDITIONAL_STAGES: tuple[str, ...] = ("geometry", "asset_truth", "policy")


def certify(
    cir: CIR,
    *,
    db=None,
    assets: list[Asset] | None = None,
    listing: ListingDraft | None = None,
    physical_test_passed: bool = False,
    terminology: str = "US",
    cleared_names: set[str] | None = None,
    calibration: float = 1.0,
    platform_policy: dict | None = None,
    physical_evidence: list[dict] | None = None,
    prior_risk_class: str | None = None,
    calibrated_primitives: frozenset[str] | set[str] = frozenset(),
) -> ReleaseCertificate:
    """Run the full release chain and issue -- or refuse -- a certificate.

    `physical_test_passed` is the old direct assertion, kept for callers that construct a
    certificate by hand. The runtime passes `physical_evidence` instead -- the stored
    PhysicalTest rows, each carrying the content hash it was worked against -- and this
    function decides which of them bind to the content it is examining (F-078). A test of a
    different text is not evidence for this one, however close the version string.
    """
    findings: list[Finding] = []
    stages: list[str] = []

    # 1. Deterministic compile.
    result = compile_cir(cir)
    stages.append("compile")
    findings.extend(result.findings)
    if not result.ok:
        return ReleaseCertificate(cir.slug, cir.version, False, None, findings, stages,
                                  platform_policy=platform_policy)

    # 1b. Specification. A Brambleloop design must state every fact its finished object
    #     depends on, and must not be somebody else's stitch tables under our name. Both
    #     functions existed and ran nowhere in the chain until 2026-09-26, so a design with
    #     reconstructive gaps -- or a benchmark relabelled as ours -- could be certified.
    #     Benchmarks pass through: they are records of someone else's work, never products.
    findings.extend(specification_findings(cir))
    stages.append("specification")

    # 2. Digital twin -- one per piece. Only the first component used to be modelled, so a
    #    sleeve's yarn was never counted and a garment's pieces were never measured at all.
    twins: dict[str, TwinModel] = {
        comp.name: build_twin(cir, result, component=comp.name, calibration=calibration)
        for comp in cir.components}
    twin: TwinModel = twins[cir.components[0].name]
    stages.append("twin")

    # 2b. Assembly: every piece placed and every join measured on both sides. A garment
    #     whose sleeve top is not the length of its armhole is correct pieces that do not
    #     sew together, and no per-piece check can see it.
    geo = _assembly.assemble(cir, twins)
    findings.extend(assembly_findings(cir, geo))
    stages.append("assembly")

    if any(t.geometry is not None for t in twins.values()):
        # What the fabric does with the shaping: a round that has to gather, and therefore a
        # shape no diameter describes. Warnings, not errors -- a frill is a legitimate design.
        # The protection is that the twin refuses the dimensions, not that the release stops.
        for t in twins.values():
            if t.geometry is not None:
                findings.extend(t.geometry.findings)
        stages.append("geometry")

    # 3. Written pattern, then an independent reverse compile of that exact text.
    pattern_text = write_pattern(cir, result, terminology)
    stages.append("write")
    # The content this run examines, named before anything decides whether it is granted.
    content = _release_hash(cir, pattern_text)
    binding = bind_physical_evidence(physical_evidence or [], slug=cir.slug,
                                     version=cir.version, content_hash=content)
    physical_test_passed = bool(physical_test_passed) or binding["passed"]
    reverse_findings = reverse_compare(cir, pattern_text, terminology)
    findings.extend(reverse_findings)
    stages.append("reverse")

    # 3b. Originality and IP. Section 17 puts this in the release chain, before the product
    #     acquires assets and a listing and becomes expensive to withdraw.
    findings.extend(check_originality(cir.title, cleared_names=cleared_names))
    # The product's own name is a claim about the shape of the object, checked against the
    # twin before it acquires assets and a listing: a flat panel named "Market Basket" is a
    # different product from the one the buyer would be paying for.
    findings.extend(check_shape_claims(cir.title, cir, twin, "cir.title"))
    findings.extend(check_technique_claims(cir.title, cir, twin, "cir.title"))
    findings.extend(check_text(cir.designer_notes or "", "cir.designer_notes"))
    # The designer notes go through the technique check too.
    #
    # Only `check_text` -- originality and IP -- used to read them, so a claim about the fabric
    # was checked in the title and unchecked three lines further down the same document. The
    # Cloudline baby blanket's note promised "no long floats for small fingers to catch" on a
    # fabric with no floats in it, and no gate could see it: the checker existed, the twin held
    # the fact, and the text carrying the claim was never passed in.
    #
    # `check_shape_claims` is deliberately NOT run on the notes. Measured across all 16
    # catalogue patterns before wiring it up: it fires on the pet snuggle mat, whose motif note
    # reads "dense and structural, suited to baskets and pillows". That check is written for a
    # *name*, where a noun is the object being sold; in prose the same noun can be a
    # suitability note or a comparison, and telling those apart is parsing English rather than
    # measuring the fabric. A technique claim has no such reading -- the fabric either works
    # that way or it does not -- which is why this half is safe on prose and that half is not.
    findings.extend(check_technique_claims(cir.designer_notes or "", cir, twin,
                                           "cir.designer_notes"))
    # Design provenance, the design-difference ledger and the similarity review against
    # every purchased benchmark (F-783, F-798, F-794, F-791, F-795): `gates/originality.py`.
    findings.extend(_originality.release_findings(cir, pattern_text=pattern_text, db=db))
    stages.append("originality")

    # 4. Asset truth.
    asset_findings: list[Finding] = []
    if assets:
        asset_findings = check_assets(assets, cir, twin)
        findings.extend(asset_findings)
        stages.append("asset_truth")

    # 5. Policy.
    #
    # The proof position is computed from this run's own stages rather than looked up, which
    # is not circular: it is the same evidence, and looking it up would read a certificate
    # this call has not issued yet. Rungs four and five cannot be established here at all --
    # a customer project is not a thing a release chain knows about -- so they are False, and
    # a listing claiming them is refused, which is the correct answer while this company has
    # no customers.
    proof_states = {
        "deterministic_validation": result.ok,
        "independent_reverse_compilation": (
            result.ok and not any(f.severity == ERROR for f in reverse_findings)),
        "physical_tester_example": bool(physical_test_passed),
        "customer_project": False,
        "repeat_purchase": False,
    }
    if listing is not None:
        findings.extend(check_listing(listing, cir, proof_states=proof_states))
        findings.extend(check_shape_claims(listing.title, cir, twin, "listing.title"))
        findings.extend(check_technique_claims(listing.title, cir, twin, "listing.title"))
        stages.append("policy")

    # 6. Physical testing. Class C (fitted garments, complex structures) does not ship on
    #    computation alone -- section 3 is explicit that it normally requires a real sample.
    physical_required = cir.risk_class == "C"
    if physical_required and not physical_test_passed:
        findings.append(Finding(
            ERROR, "PHYSICAL_TEST_REQUIRED",
            f"risk class {cir.risk_class} requires a physical test before release; "
            "computation alone cannot confirm fit and drape"))
    # 6b. The gauge against the declared yarn (F-112, F-116). A gauge the declared yarn's
    #     published band cannot hold is a known-implausible assumption, and every finished
    #     size and yardage figure in the document is arithmetic from it. It used to reach the
    #     buyer as a "swatch before you buy" note in the PDF; a warning cannot stand in for
    #     truth, so it is refused here unless a tester's measured sample of this exact content
    #     is the evidence for it instead.
    findings.extend(gauge_findings(cir, physically_evidenced=physical_test_passed))
    # 6c. New primitives (F-074): a stitch whose real-world height and yarn behaviour no
    #     sample has measured does not carry unrestricted size or yardage claims.
    primitive_status, primitive_errors = primitive_findings(
        cir, physically_evidenced=physical_test_passed,
        calibrated_primitives=calibrated_primitives)
    findings.extend(primitive_errors)
    # 6d. No convenience downgrade (F-090): a lower risk class than this product has held
    #     before needs evidence, and the only evidence that reduces physical testing is a
    #     physical test of this content.
    findings.extend(risk_downgrade_findings(cir, prior_risk_class,
                                            physically_evidenced=physical_test_passed))
    stages.append("physical_test")

    # 7. Confidence, tracked per dimension (section 3). Deliberately computed after every
    #    other stage so it reflects what was actually established rather than what was hoped.
    profile = assess(cir, result, twin, reverse_findings=reverse_findings,
                     asset_findings=asset_findings,
                     physical_passed=physical_test_passed if physical_required else None)
    stages.append("confidence")

    granted = not any(f.severity == ERROR for f in findings)
    rhash = _release_hash(cir, pattern_text) if granted else None

    return ReleaseCertificate(
        slug=cir.slug,
        version=cir.version,
        granted=granted,
        release_hash=rhash,
        findings=findings,
        stages_run=stages,
        platform_policy=platform_policy,
        pattern_text=pattern_text if granted else None,
        confidence=profile.to_dict(),
        twin_summary=twin_summary(cir, twins, geo),
        physical_test_required=physical_required,
        physical_test_passed=physical_test_passed,
        content_hash=content,
        physical_evidence=binding,
        # Every certificate from here was examined by `gauge_findings`; a stored one without
        # this stamp predates the check and is legacy (F-111, F-119).
        gauge_standard=GAUGE_STANDARD,
        primitives=primitive_status,
    )


# ---- physical evidence bound to content (F-078, F-081) ----------------------

def bind_physical_evidence(evidence: list[dict], *, slug: str, version: str,
                           content_hash: str) -> dict:
    """Which physical tests are evidence for exactly this content, and why the rest are not.

    Each evidence row is a stored PhysicalTest reduced to what binding needs:
    `{"id", "slug", "version", "passed", "completed_at", "content_hash",
    "compatible_variants"}`. A row binds when it passed, was completed, and either

    - is for this slug@version and was worked against this exact content hash, or
    - is for another release and declares this one a compatible variant *with this content
      hash* (`compatible_variants: [{"slug", "version", "content_hash"}]`), so a variant's
      own later change invalidates the declaration too.

    A row with no content hash recorded does not bind: "which text did the tester follow" is
    the whole question, and an absent answer is not a yes. A changed hash is a material change
    and the evidence is reported as invalidated, never silently dropped.
    """
    bound: list = []
    unbound: list[dict] = []
    for ev in evidence:
        ref = ev.get("id")
        if ev.get("passed") is not True:
            unbound.append({"id": ref, "why": "did not pass" if ev.get("passed") is False
                            else "no result recorded"})
            continue
        if not ev.get("completed_at"):
            unbound.append({"id": ref, "why": "not completed"})
            continue
        if ev.get("slug") == slug and ev.get("version") == version:
            tested = ev.get("content_hash")
            if not tested:
                unbound.append({"id": ref, "why": "no content hash recorded: which text was "
                                                  "worked is unknown"})
            elif tested != content_hash:
                unbound.append({"id": ref, "why": (
                    f"invalidated: worked against {tested[:12]}, the content is now "
                    f"{content_hash[:12]} -- a material change needs a re-test")})
            else:
                bound.append(ref)
            continue
        declared = [v for v in (ev.get("compatible_variants") or [])
                    if isinstance(v, dict) and v.get("slug") == slug
                    and v.get("version") == version]
        if not declared:
            continue            # evidence for some other product; not ours to report
        if any(v.get("content_hash") == content_hash for v in declared):
            bound.append(ref)
        else:
            unbound.append({"id": ref, "why": (
                "declared this release a compatible variant, but not at its current content "
                f"{content_hash[:12]}")})
    return {"content_hash": content_hash, "passed": bool(bound), "bound": bound,
            "unbound": unbound}


# ---- gauge evidence (F-112, F-116) -----------------------------------------

# The standard every certificate issued from here is examined under. A stored certificate
# without it predates the check -- that is what makes a Build-1 product legacy (F-111/F-119).
GAUGE_STANDARD = "cyc-sc-band/1"


def declared_weight(cir: CIR) -> str | None:
    """The yarn weight the pattern tells a buyer to use, as written on the pattern."""
    if cir.gauge is not None and cir.gauge.yarn_weight:
        return cir.gauge.yarn_weight
    return next((m.yarn_weight for m in cir.materials if m.yarn_weight), None)


def gauge_findings(cir: CIR, *, physically_evidenced: bool = False) -> list[Finding]:
    """The stated gauge against the declared yarn's published single-crochet band.

    - gauge in band: the band is the evidence (F-116's "declared yarn/material evidence").
    - gauge outside the band: ERROR, unless a physical test of this content is bound, which
      is the calibrated evidence F-116 names as the other way through.
    - a Brambleloop design stating a gauge and no recognisable yarn weight: ERROR -- a gauge
      with neither yarn nor calibration behind it is a typed constant.
    - a gauge stated in a stitch other than sc: WARNING, because the published bands are
      single-crochet bands and nothing here can place a dc gauge in one.

    Benchmarks are records of somebody else's pattern and pass through, as they do the
    specification gate.
    """
    from ..publish.substitution import WEIGHT_BY_KEY, holds_gauge, normalise

    if cir.gauge is None or cir.authored == "benchmark":
        return []
    declared = declared_weight(cir)
    key = normalise(declared or "")
    sts = cir.gauge.stitches_per_10cm
    if not key:
        return [Finding(ERROR, "GAUGE_WITHOUT_YARN_EVIDENCE", (
            f"the gauge ({sts} sts/10cm) is stated against no standard yarn weight "
            f"({declared!r}), so nothing but a typed number stands behind every size and "
            f"yardage figure in the document"))]
    if (cir.gauge.stitch_type or "sc") != "sc":
        return [Finding(WARNING, "GAUGE_BAND_NOT_APPLICABLE", (
            f"the gauge is stated in {cir.gauge.stitch_type}; the published {key} band is a "
            f"single-crochet band, so this gauge is not evidenced by the declared yarn"))]
    weight = WEIGHT_BY_KEY[key]
    if holds_gauge(weight, sts):
        return []
    low, high = weight.sc_per_10cm
    if physically_evidenced:
        return [Finding(WARNING, "GAUGE_OUTSIDE_BAND_PHYSICALLY_EVIDENCED", (
            f"{sts} sc/10cm is outside the {key} band ({low:g}-{high:g}); a bound physical "
            f"test of this content is the evidence for it"))]
    return [Finding(ERROR, "GAUGE_OUTSIDE_DECLARED_YARN_BAND", (
        f"{sts} sc/10cm is outside the published {key} band of {low:g}-{high:g} for the "
        f"declared yarn ({declared}). Every finished size and yardage figure is arithmetic "
        f"from this gauge, and a 'swatch first' note cannot make it true: derive the gauge "
        f"from the yarn (creative.prototype.gauge_for), declare the weight that holds it, or "
        f"bind a physical test of this content"))]


# ---- new primitives (F-074) -------------------------------------------------

def primitive_findings(cir: CIR, *, physically_evidenced: bool,
                       calibrated_primitives=frozenset()) -> tuple[dict, list[Finding]]:
    """Every stitch this pattern uses, with its calibration status, and what that blocks."""
    from ..cir.stitches import CALIBRATED, UNCALIBRATED, calibration_status

    used: set[str] = set()

    def walk(nodes):
        for n in nodes:
            if hasattr(n, "stitch"):
                used.add(n.stitch)
            else:
                walk(n.ops)

    for _, row in cir.iter_rows():
        walk(row.ops)
    status = {code: (CALIBRATED if code in calibrated_primitives
                     else calibration_status(code)) for code in sorted(used)}
    uncalibrated = sorted(c for c, st in status.items() if st == UNCALIBRATED)
    view = {"status": status, "uncalibrated": uncalibrated,
            "unrestricted": not uncalibrated or physically_evidenced}
    if not uncalibrated or cir.authored == "benchmark":
        return view, []
    if physically_evidenced:
        return view, [Finding(WARNING, "UNCALIBRATED_PRIMITIVE_EVIDENCED", (
            f"{uncalibrated} have no calibration on file; a bound physical test of this "
            f"content stands behind this pattern's claims"))]
    return view, [Finding(ERROR, "UNCALIBRATED_PRIMITIVE", (
        f"{uncalibrated} are new primitives no sample has calibrated: their height and yarn "
        f"behaviour decide this pattern's size and yardage claims, so it is not released for "
        f"unrestricted use until a physical test of it passes"))]


# ---- no convenience downgrade (F-090) ---------------------------------------

_RISK_RANK = {"A": 0, "B": 1, "C": 2}


def risk_downgrade_findings(cir: CIR, prior_risk_class: str | None, *,
                            physically_evidenced: bool) -> list[Finding]:
    """A lower risk class than the product has held needs evidence, never a deadline."""
    if prior_risk_class not in _RISK_RANK:
        return []
    if _RISK_RANK[cir.risk_class] >= _RISK_RANK[prior_risk_class]:
        return []
    if physically_evidenced:
        return [Finding(WARNING, "RISK_CLASS_DOWNGRADED_ON_EVIDENCE", (
            f"risk class {prior_risk_class} -> {cir.risk_class}, justified by a bound "
            f"physical test of this content"))]
    return [Finding(ERROR, "RISK_CLASS_DOWNGRADE_UNJUSTIFIED", (
        f"this product has been risk class {prior_risk_class} and is now declared "
        f"{cir.risk_class} with no recorded evidence. Testing is reduced only because "
        f"evidence justifies it: bind a passed physical test of this content, or keep the "
        f"class"))]


def specification_findings(cir: CIR) -> list[Finding]:
    """The specification gate as findings: gaps, and a benchmark in our clothes."""
    out: list[Finding] = []
    try:
        _specification.refuse_an_underspecified_design(cir)
    except _specification.SpecificationIncomplete as exc:
        out.append(Finding(ERROR, "SPECIFICATION_INCOMPLETE", str(exc)))
    try:
        _specification.refuse_a_benchmark_in_our_clothes(cir)
    except _specification.BenchmarkDerived as exc:
        out.append(Finding(ERROR, "BENCHMARK_DERIVED", str(exc)))
    return out


def assembly_findings(cir: CIR, geo) -> list[Finding]:
    """A join that does not sew together blocks; one that cannot be checked is flagged.

    `partially_placed` is a warning rather than an error because the specification stage
    already refuses a Brambleloop design whose joins do not name their edges; what is left
    is a join whose lengths fall inside a stated chain-gauge uncertainty, which is a
    measurement limit, not a defect.
    """
    if geo.verdict == "does_not_assemble":
        return [Finding(ERROR, "ASSEMBLY_MISMATCH", geo.why)]
    if geo.verdict == "partially_placed":
        return [Finding(WARNING, "ASSEMBLY_PARTIAL", geo.why)]
    if geo.verdict == "unmeasurable" and cir.assembly:
        return [Finding(WARNING, "ASSEMBLY_UNMEASURABLE", geo.why)]
    return []


def twin_summary(cir: CIR, twins: dict, geo) -> dict:
    """The certificate's twin block.

    Backwards compatible: the top-level size fields are still the first piece's, which is
    what every existing reader was written against and what a one-piece product has always
    reported. Yardage is the whole pattern -- every piece, times the number of copies each
    is made -- because a buyer buys yarn for the whole garment, not for its first panel.
    `pieces` carries the per-piece figures.
    """
    first = twins[cir.components[0].name]
    yarn: dict[str, float] = {}
    for t in twins.values():
        for colour, metres in t.yarn_metres_by_color.items():
            yarn[colour] = round(yarn.get(colour, 0.0) + metres, 1)
    return {
        "stitch_total": first.stitch_total,
        "width_cm": first.width_cm,
        "height_cm": first.height_cm,
        "shape": first.shape,
        "circumference_cm": first.circumference_cm,
        "size_refusal": first.size_refusal,
        "colors": sorted(set().union(*(t.colors_used for t in twins.values()))),
        "stitches": sorted(set().union(*(t.stitch_types_used for t in twins.values()))),
        "yarn_metres": yarn,
        "yardage_tolerance": first.yardage_tolerance,
        "pieces": {
            comp.name: {
                "make": comp.make,
                "stitch_total": twins[comp.name].stitch_total,
                "width_cm": twins[comp.name].width_cm,
                "height_cm": twins[comp.name].height_cm,
                "shape": twins[comp.name].shape,
                "yarn_metres": twins[comp.name].yarn_metres_by_color,
            } for comp in cir.components},
        "assembly": geo.verdict,
    }
