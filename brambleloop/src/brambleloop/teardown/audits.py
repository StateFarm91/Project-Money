"""The nine per-dimension teardowns, and the rule that stops them becoming a rating.

Requirements 152-160. The laboratory already had a twelve-dimension scorecard; what it did not
have was the thing that makes a score mean anything. "Chart quality: 4" is a feeling with a
number attached. Requirement 154 does not ask for a number — it asks about legibility, symbols,
legends, colour independence, pagination, row numbering, motif boundaries, print quality,
scale, schematics, assembly diagrams and correspondence with the written instructions. Twelve
named things a person can actually look at and disagree about.

So each audit is a closed schedule of elements taken from its requirement, and four rules hold
it to being evidence rather than an impression.

**An audit is complete or it is not scored.** Scoring five of twelve chart elements and
reporting the mean would let a teardown that looked at the easy things outrank one that looked
at all of them. `observe()` refuses a partial schedule, exactly as `scorecard()` refuses to
average over the dimensions somebody happened to reach.

**Only the extremes owe a mechanism.** A 3 is "competent; what a buyer expects" and teaches
this company nothing, so it needs no essay. A 4 or 5 is a mechanism worth adopting and a 0-2 is
a trap worth making impossible, and both have to say what produced them. Demanding a paragraph
for all thirty-four elements of a full teardown is how ten purchases become a task nobody
finishes — the same failure #170 exists to prevent at intake.

**A strength with no answer is reported, not converted.** #163 already refuses parity as a
position. Here that becomes mechanical: a benchmark element scoring 4 or 5 becomes a
Brambleloop publishing requirement only when the analyst can name the company advantage that
beats it. When nobody can, it is recorded as an unmatched strength — a competitor does
something this company has no answer to, which is worth knowing and worth not papering over.

**An audit nobody could run is not a pass.** With no purchased benchmarks the audits report
that they are unrun. They do not return empty structures that read as all-clear, and #168's
pre-launch challenge blocks rather than waves through.

Nothing here opens a benchmark file. The analyst reads the purchased document under
`library.retrieve()` and records observations about it; every free-text field goes through
`check_derived()`, so a mechanism that is really the competitor's instructions is refused at
the point of recording (#167).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .library import check_derived
from .scorecard import ADVANTAGES, DIMENSIONS, SCALE, Finding, ScoreRefused

PRESENCE = "presence"
QUALITY = "quality"

# What counts as a mechanism worth adopting, and what counts as a trap worth preventing.
STRONG = 4
WEAK = 2


class AuditRefused(Exception):
    """A schedule answered partially, an element that does not exist, or a silent extreme."""


@dataclass(frozen=True)
class Element:
    key: str
    what: str
    kind: str = QUALITY


@dataclass(frozen=True)
class AuditSpec:
    """One requirement's observation schedule."""

    key: str
    requirement: int
    dimension: str
    title: str
    elements: tuple[Element, ...]
    # The manifest flag that must be true for this audit to apply. A product that never
    # promised video does not have bad video; it has no video, and scoring it zero would
    # manufacture a weakness out of a category difference.
    applies_when: str = ""
    note: str = ""

    @property
    def element_keys(self) -> tuple[str, ...]:
        return tuple(e.key for e in self.elements)

    def element(self, key: str) -> Element:
        for e in self.elements:
            if e.key == key:
                return e
        raise AuditRefused(
            f"{key!r} is not part of the {self.key} schedule: {list(self.element_keys)}. "
            f"The schedule is closed so two teardowns of two products are comparable")

    def to_dict(self) -> dict:
        return {"key": self.key, "requirement": self.requirement,
                "dimension": self.dimension, "title": self.title,
                "applies_when": self.applies_when, "note": self.note,
                "elements": [{"key": e.key, "what": e.what, "kind": e.kind}
                             for e in self.elements]}


# ---------------------------------------------------------------------------
# The schedules. Each element list is the requirement's own enumeration, in its own order,
# so the document and the code can be read side by side.

PDF_ARCHITECTURE = AuditSpec(
    "pdf_architecture", 152, "premium_presentation",
    "PDF information architecture",
    tuple(Element(k, w, PRESENCE) for k, w in (
        ("cover", "a cover that identifies the product before anything else"),
        ("table_of_contents", "a contents page that makes the document navigable"),
        ("quick_start", "a route for a maker who wants to begin immediately"),
        ("materials", "the materials list as its own addressable section"),
        ("gauge", "gauge stated where it is read before starting, not after"),
        ("sizing", "the size table or finished dimensions"),
        ("abbreviations", "the abbreviation key"),
        ("technique_explanations", "explanations of the techniques the pattern assumes"),
        ("construction_overview", "how the object is built, before the row instructions"),
        ("row_round_instructions", "the instruction body itself"),
        ("charts", "charts as part of the document's structure"),
        ("assembly", "how the pieces become the object"),
        ("finishing", "finishing as an addressed step rather than an afterthought"),
        ("blocking", "blocking instructions"),
        ("troubleshooting", "what to do when it goes wrong"),
        ("credits", "designer, photographer and tester credits"),
        ("rights_terms", "what the buyer may do with the pattern and the finished item"),
        ("support", "how to reach a human"),
        ("cross_sell", "where the next purchase is offered"),
    )),
    note=("Information architecture, recorded as which sections exist and where. The prose "
          "is never copied — what transfers is the shape of the document (#152)."),
)

INSTRUCTION_CLARITY = AuditSpec(
    "instruction_clarity", 153, "instruction_clarity",
    "Instruction clarity",
    (
        Element("scanability", "whether a maker can find their place after looking away"),
        Element("repeat_notation", "how repeats are written, and whether they nest legibly"),
        Element("row_grouping", "whether rows are grouped the way the work is actually done"),
        Element("stitch_count_visibility", "whether the count at the end of a row is findable"),
        Element("terminology_consistency", "whether the same stitch is named the same way"),
        Element("size_grading", "whether every size is followed through the whole pattern"),
        Element("colour_change_clarity", "when and where a colour change happens"),
        Element("assembly_clarity", "whether assembly can be followed without the photograph"),
        Element("cognitive_load", "how much a maker must hold in their head at once"),
    ),
    note=("Mechanisms that make instructions easier or harder to follow. Winning mechanisms "
          "become Brambleloop publishing requirements rather than admiration (#153)."),
)

CHART_BENCHMARK = AuditSpec(
    "chart_benchmark", 154, "chart_quality",
    "Charts and diagrams",
    (
        Element("legibility", "whether the chart is readable at the size it is delivered"),
        Element("symbols", "whether the symbol set is standard and internally consistent"),
        Element("legends", "whether the legend is complete and on the page that needs it"),
        Element("colour_independence", "whether the chart survives being printed in grey"),
        Element("pagination", "how a chart larger than a page is split"),
        Element("row_numbering", "whether row numbers sit where the row is read from"),
        Element("motif_boundaries", "whether the repeat boundary is visible"),
        Element("print_quality", "whether it holds up on a home printer"),
        Element("scale", "whether the chart's scale matches the work"),
        Element("schematics", "finished-dimension schematics"),
        Element("assembly_diagrams", "diagrams showing how pieces relate"),
        Element("written_correspondence", "whether the chart and the written rows agree"),
    ),
    note=("#154 asks for clearer charts and stronger written/chart cross-validation than the "
          "best benchmark, not parity with it."),
)

BEGINNER_EXPERIENCE = AuditSpec(
    "beginner_experience", 155, "beginner_support",
    "Beginner experience",
    (
        Element("prior_knowledge_assumptions", "what the pattern assumes the buyer already knows"),
        Element("technique_links", "links or references to the techniques it assumes"),
        Element("photo_video_support", "photographic or video support at the hard moments"),
        Element("error_recovery", "what to do after a mistake is discovered late"),
        Element("terminology_variants", "whether UK and US terms are both addressed"),
        Element("tips", "tips placed where the difficulty is, not collected at the end"),
        Element("progress_checkpoints", "checkpoints that confirm the work is still correct"),
        Element("confidence_building", "whether an anxious maker is given reason to continue"),
    ),
    note=("The question is what an anxious or inexperienced buyer would struggle with. "
          "Findings feed Pattern Help and PDF generation (#155)."),
)

PREMIUM_EXPERIENCE = AuditSpec(
    "premium_experience", 156, "premium_presentation",
    "Premium experience",
    (
        Element("typography", "typeface choice and whether it is readable at length"),
        Element("spacing", "whether the page breathes or is packed"),
        Element("hierarchy", "whether importance is visible before it is read"),
        Element("photography", "photographic quality and whether it shows the stitch"),
        Element("brand_consistency", "whether the document looks like one product"),
        Element("editorial_polish", "proofreading, captions, consistency of voice"),
        Element("file_naming", "whether the filenames make sense in a downloads folder"),
        Element("cover_quality", "the cover as the first thing seen after paying"),
        Element("navigation", "whether a long document can be moved around in"),
        Element("hyperlinks", "working internal and external links"),
        Element("print_friendly_option", "an edition that does not cost a cartridge"),
        Element("bonus_content", "anything included beyond what was promised"),
        Element("perceived_value", "whether the whole feels worth what was paid"),
    ),
    note=("Benchmarked against the best purchased experience, not the average of them "
          "(#156). An average is a description of the category, not a standard."),
)

VIDEO_TEARDOWN = AuditSpec(
    "video_teardown", 157, "video_support",
    "Video and tutorial support",
    (
        Element("structure", "whether the video has a shape a maker can navigate"),
        Element("chaptering", "chapters or timestamps that match the pattern's sections"),
        Element("technique_coverage", "which techniques are actually demonstrated"),
        Element("pacing", "whether the hard part is slowed down"),
        Element("section_correspondence", "whether the video maps onto the written pattern"),
        Element("accessibility", "captions, audio description, readable on a phone"),
        Element("ambiguity_reduction", "whether the video settles something the text cannot"),
    ),
    applies_when="has_video",
    note=("Only where the purchase included video. Footage and scripts are never copied; "
          "what transfers is the mechanism (#157)."),
)

MATERIALS_AUDIT = AuditSpec(
    "materials_audit", 158, "materials_clarity",
    "Materials, yardage and substitution",
    (
        Element("yarn_specification", "how precisely the yarn is identified"),
        Element("fibre", "whether fibre content is given, and why it matters here"),
        Element("colour_quantities", "quantity per colour rather than a total"),
        Element("hooks", "hook sizes, including the ones used for edging"),
        Element("notions", "everything else the maker needs before starting"),
        Element("gauge", "how gauge is specified and how it is to be measured"),
        Element("substitutions", "guidance for substituting the named yarn"),
        Element("finished_dimensions", "expected finished dimensions per size"),
    ),
    note=("Observations improve Brambleloop's own explanation and validation. A competitor's "
          "material constants are never imported into an unrelated pattern (#158)."),
)

DELIVERY_PACKAGING = AuditSpec(
    "delivery_packaging", 159, "delivery_packaging",
    "Digital delivery packaging",
    (
        Element("file_count", "how many files arrive", PRESENCE),
        Element("filenames", "whether the names say what the files are"),
        Element("versions", "whether the version is visible without opening anything"),
        Element("print_vs_screen", "separate print and screen editions", PRESENCE),
        Element("charts_separate", "charts as their own file", PRESENCE),
        Element("bonus_files", "bonus files", PRESENCE),
        Element("language_variants", "language variants", PRESENCE),
        Element("file_sizes", "whether anything is too large to open on a phone"),
        Element("organization", "whether the bundle explains itself in the first ten seconds"),
    ),
    note=("Half of this schedule is already in the intake manifest, so `prefill()` answers it "
          "from filenames and the analyst answers only the rest (#159, #170)."),
)

SUPPORT_RIGHTS = AuditSpec(
    "support_rights", 160, "support_experience",
    "Support and rights experience",
    (
        Element("support_instructions", "how the buyer is told to ask for help"),
        Element("faq", "questions answered before they are asked"),
        Element("update_policy", "what happens when the pattern changes"),
        Element("errata_version_handling", "how a correction reaches somebody who already bought"),
        Element("finished_item_permissions", "what the buyer may do with what they make"),
        Element("redistribution_language", "what may not be shared, said clearly"),
        Element("contact_path", "whether a human is reachable and how quickly"),
    ),
    note=("Inconsistencies across benchmarks become a clearer Brambleloop customer "
          "experience. Legal enforceability remains subject to appropriate review (#160)."),
)

AUDITS: tuple[AuditSpec, ...] = (
    PDF_ARCHITECTURE, INSTRUCTION_CLARITY, CHART_BENCHMARK, BEGINNER_EXPERIENCE,
    PREMIUM_EXPERIENCE, VIDEO_TEARDOWN, MATERIALS_AUDIT, DELIVERY_PACKAGING, SUPPORT_RIGHTS,
)

BY_KEY: dict[str, AuditSpec] = {a.key: a for a in AUDITS}

# Every audit feeds a dimension the scorecard already has, so the audits deepen the existing
# standard rather than starting a second one beside it.
assert all(a.dimension in DIMENSIONS for a in AUDITS)

# What the manifest can answer on the analyst's behalf (#170 applied to #159).
_PREFILL_FROM_MANIFEST: dict[str, str] = {
    "file_count": "file_count",
    "charts_separate": "has_chart",
    "bonus_files": "has_bonus",
    "print_vs_screen": "has_print_edition",
}


def prefill(spec_key: str, inferred: dict | None) -> dict:
    """Answer from the intake manifest what filenames can settle.

    Making somebody retype what `library.scan()` already worked out is how a nine-audit
    teardown becomes a task that is started once.
    """
    spec = BY_KEY.get(spec_key)
    if spec is None:
        raise AuditRefused(f"{spec_key!r} is not an audit: {sorted(BY_KEY)}")
    inferred = inferred or {}
    out: dict = {}
    for element_key, manifest_key in _PREFILL_FROM_MANIFEST.items():
        if element_key not in spec.element_keys or manifest_key not in inferred:
            continue
        value = inferred[manifest_key]
        entry = {"score": bool(value), "mechanism": "", "from_manifest": manifest_key}
        if element_key == "file_count":
            # The manifest counts files; the schedule asks whether any arrived. Both are
            # kept: the count is the useful number and the flag is what the schedule wants.
            entry["files"] = int(value) if isinstance(value, int) else 0
            entry["score"] = entry["files"] > 0
        out[element_key] = entry
    return out


def applies(spec: AuditSpec, inferred: dict | None) -> bool:
    """Whether this audit is one the product can be judged on at all."""
    if not spec.applies_when:
        return True
    return bool((inferred or {}).get(spec.applies_when))


# ---------------------------------------------------------------------------
# Recording an audit


@dataclass(frozen=True)
class Observation:
    element: str
    kind: str
    score: float
    mechanism: str = ""
    advantage: str = ""
    source: str = "analyst"

    @property
    def notable(self) -> bool:
        """Whether this element teaches anything: a mechanism to beat, or a trap to prevent."""
        if self.kind == PRESENCE:
            return False
        return self.score >= STRONG or self.score <= WEAK

    def to_dict(self) -> dict:
        return {"element": self.element, "kind": self.kind, "score": self.score,
                "mechanism": self.mechanism, "advantage": self.advantage,
                "source": self.source}


@dataclass
class Audit:
    spec: AuditSpec
    benchmark_ref: str
    observations: list[Observation] = field(default_factory=list)
    unmatched_strengths: list[dict] = field(default_factory=list)

    @property
    def quality_scores(self) -> dict[str, float]:
        return {o.element: o.score for o in self.observations if o.kind == QUALITY}

    def summary(self) -> dict:
        quality = self.quality_scores
        present = [o.element for o in self.observations
                   if o.kind == PRESENCE and o.score >= 1]
        absent = [o.element for o in self.observations
                  if o.kind == PRESENCE and o.score < 1]
        weakest = min(quality, key=quality.get) if quality else None
        return {
            "audit": self.spec.key,
            "requirement": self.spec.requirement,
            "dimension": self.spec.dimension,
            "benchmark": self.benchmark_ref,
            "sections_present": present,
            "sections_absent": absent,
            "scores": quality,
            # Both numbers, because they answer different questions. The mean describes the
            # document; the weakest element is the one a buyer actually meets, and a chart
            # with excellent symbols and no legend is a bad chart however it averages.
            "mean": round(sum(quality.values()) / len(quality), 2) if quality else None,
            "weakest": weakest,
            "weakest_score": quality[weakest] if weakest else None,
            "strengths": [o.to_dict() for o in self.observations if o.score >= STRONG
                          and o.kind == QUALITY],
            "traps": [o.to_dict() for o in self.observations if o.score <= WEAK
                      and o.kind == QUALITY],
            "unmatched_strengths": list(self.unmatched_strengths),
            "note": self.spec.note,
        }

    def findings(self) -> list[Finding]:
        """The notable elements, as scorecard findings the composite standard can use.

        Only the extremes become findings. A schedule of thirty-four "competent" observations
        would bury the two mechanisms worth adopting under the thirty-two that teach nothing,
        and the improvement queue is read by somebody with a finite evening.
        """
        from .scorecard import finding as make_finding

        out: list[Finding] = []
        for o in self.observations:
            if not o.notable:
                continue
            # Routed through the scorecard's own constructor rather than built directly, so
            # an audit cannot record a finding the scorecard would have refused.
            out.append(make_finding(
                self.benchmark_ref, self.spec.dimension, int(round(o.score)),
                f"{self.spec.title} / {o.element}: {o.mechanism}",
                _improvement_for(self.spec, o)))
        return out


def _improvement_for(spec: AuditSpec, o: Observation) -> str:
    """What Brambleloop does about this element, derived rather than typed.

    A strength converts into a beat requirement naming the advantage that beats it — matching
    it would be the parity #163 refuses. A trap converts into a checklist obligation, because
    "we will be careful about legends" is not a mechanism and will not survive a deadline.
    """
    if o.score >= STRONG:
        advantage = ADVANTAGES.get(o.advantage, "")
        return (f"Brambleloop's publishing standard for {spec.dimension} must exceed this "
                f"on {o.element}, not match it: {advantage}")
    return (f"{o.element} is {SCALE[int(round(o.score))]} here. The Brambleloop publishing "
            f"checklist must make this outcome impossible rather than unlikely")


def observe(spec_key: str, benchmark_ref: str, answers: dict, *,
            inferred: dict | None = None) -> Audit:
    """Record one complete audit of one purchased benchmark.

    Refuses a partial schedule, an unknown element, an extreme with no mechanism, and a
    strength with an advantage this company cannot evidence.
    """
    spec = BY_KEY.get(spec_key)
    if spec is None:
        raise AuditRefused(f"{spec_key!r} is not an audit: {sorted(BY_KEY)}")
    if not benchmark_ref:
        raise AuditRefused("an audit with no benchmark is an opinion about crochet in general")
    if not applies(spec, inferred):
        raise AuditRefused(
            f"{spec.key} does not apply to {benchmark_ref}: the manifest records no "
            f"{spec.applies_when}. Scoring it zero would manufacture a weakness out of a "
            f"category difference — this product did not promise it")

    merged: dict = dict(prefill(spec_key, inferred))
    merged.update(answers or {})

    unknown = [k for k in merged if k not in spec.element_keys]
    if unknown:
        raise AuditRefused(
            f"{sorted(unknown)} are not part of the {spec.key} schedule. The schedule is "
            f"closed so two teardowns of two products can be compared")
    absent = [k for k in spec.element_keys if k not in merged]
    if absent:
        raise AuditRefused(
            f"{spec.key} is incomplete: {absent} unanswered. An audit scored on the elements "
            f"somebody reached would let a teardown that looked at the easy things outrank "
            f"one that looked at all of them (#{spec.requirement})")

    observations: list[Observation] = []
    unmatched: list[dict] = []
    for element_key in spec.element_keys:
        raw = merged[element_key]
        element = spec.element(element_key)
        if not isinstance(raw, dict):
            raw = {"score": raw}
        score = raw.get("score")
        mechanism = str(raw.get("mechanism") or "").strip()
        advantage = str(raw.get("advantage") or "").strip()
        source = "manifest" if raw.get("from_manifest") else "analyst"

        if element.kind == PRESENCE:
            if not isinstance(score, (bool, int)) or isinstance(score, float):
                raise AuditRefused(
                    f"{element_key} records whether it is there: give true or false, not "
                    f"{score!r}")
            score = 1.0 if bool(score) else 0.0
        else:
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise AuditRefused(
                    f"{element_key} is scored on the 0-5 scale, not {score!r}")
            if int(score) not in SCALE or score != int(score):
                raise AuditRefused(
                    f"{element_key}: {score!r} is not on the 0-5 scale: {SCALE}")
            score = float(score)

        if mechanism:
            check_derived(mechanism)

        o = Observation(element_key, element.kind, score, mechanism, advantage, source)
        if o.notable and len(mechanism) < 15:
            raise AuditRefused(
                f"{element_key} scored {int(score)} with no mechanism. A {int(score)} is "
                f"{SCALE[int(score)]!r} — the whole value of recording it is what produced "
                f"it (#{spec.requirement})")
        if o.score >= STRONG and o.kind == QUALITY:
            if advantage and advantage not in ADVANTAGES:
                raise ScoreRefused(
                    f"{advantage!r} is not an advantage this company can evidence: "
                    f"{sorted(ADVANTAGES)}. An advantage is something already built and "
                    f"checkable, not an aspiration (#163)")
            if not advantage:
                # Not an error. A competitor doing something this company has no answer to is
                # the most useful thing a teardown can find, and inventing a differentiator to
                # make the row look finished would destroy exactly that signal.
                unmatched.append({"element": element_key, "score": score,
                                  "mechanism": mechanism,
                                  "why": ("no Brambleloop advantage was named that beats "
                                          "this, so it is recorded as unanswered rather "
                                          "than converted into a requirement we cannot "
                                          "meet")})
                o = Observation(element_key, element.kind, score, mechanism, "", source)
        observations.append(o)

    return Audit(spec=spec, benchmark_ref=benchmark_ref, observations=observations,
                 unmatched_strengths=unmatched)


def record(db, audit: Audit) -> dict:
    """Persist the audit as scorecard findings, with the element detail kept alongside.

    The findings land in the same table the twelve-dimension scorecard and the composite
    standard already read, so the audits deepen the existing standard instead of starting a
    parallel one that would disagree with it next month.
    """
    from ..core.models import TeardownFinding

    ids: list[int] = []
    with db.session() as s:
        for f, o in zip(audit.findings(),
                        [o for o in audit.observations if o.notable]):
            row = TeardownFinding(
                benchmark_ref=f.benchmark_ref, dimension=f.dimension, score=float(f.score),
                mechanism=f.mechanism, improvement=f.improvement,
                detail={"audit": audit.spec.key, "requirement": audit.spec.requirement,
                        "element": o.element, "element_score": o.score,
                        "advantage": o.advantage, "source": o.source})
            s.add(row)
            s.flush()
            ids.append(row.id)
    return {"benchmark": audit.benchmark_ref, "audit": audit.spec.key,
            "findings_recorded": ids, "summary": audit.summary()}


# ---------------------------------------------------------------------------
# Turning what the benchmarks do well into what this company must do (#153, #154, #156, #157)


def publishing_requirements(db) -> dict:
    """The publishing standard the audits imply, per element, across the whole library.

    Each element takes the best score anybody achieved and the mechanism that achieved it.
    The Brambleloop requirement is to beat it — #154 says clearer charts than the best
    benchmark, #156 says the best purchased experience rather than the average, and neither
    is satisfied by drawing level.
    """
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    with db.session() as s:
        rows = [r for r in s.scalars(select(TeardownFinding))
                if (r.detail or {}).get("element")]

    if not rows:
        return {"derivable": False,
                "reason": ("no per-dimension audit has been recorded. The audits describe "
                           "purchased products, and nothing has been purchased yet — an "
                           "empty standard is not a lenient one, it is an absent one"),
                "requirements": [], "unmatched_strengths": [], "audits": len(AUDITS)}

    best: dict[str, dict] = {}
    unmatched: list[dict] = []
    for r in rows:
        detail = r.detail or {}
        element = detail["element"]
        if r.score < STRONG:
            continue
        current = best.get(element)
        if current is None or r.score > current["benchmark_score"]:
            best[element] = {
                "audit": detail.get("audit"), "requirement_id": detail.get("requirement"),
                "element": element, "dimension": r.dimension,
                "benchmark": r.benchmark_ref, "benchmark_score": r.score,
                "mechanism": r.mechanism, "must_exceed": r.improvement,
                "differentiator": ADVANTAGES.get(detail.get("advantage") or "", ""),
            }
        if not detail.get("advantage"):
            unmatched.append({"element": element, "benchmark": r.benchmark_ref,
                              "score": r.score, "mechanism": r.mechanism})

    requirements = sorted(best.values(), key=lambda d: (d["audit"] or "", d["element"]))
    answered = [r for r in requirements if r["differentiator"]]
    return {
        "derivable": True,
        "requirements": requirements,
        "answered": len(answered),
        "unanswered": len(requirements) - len(answered),
        "unmatched_strengths": unmatched,
        "note": ("Each requirement is to exceed the best benchmark on that element. Matching "
                 "it is the parity #163 refuses: a composite of other people's strengths is "
                 "a floor. Where no Brambleloop advantage was named, the element is listed "
                 "as an unmatched strength rather than given an invented differentiator."),
    }


def coverage(db) -> dict:
    """Which audits have been run on which benchmarks, and what is still unexamined."""
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct, TeardownFinding

    with db.session() as s:
        benchmarks = [{"ref": b.ref, "inferred_video": bool(
            (b.listing_promises or {}).get("video_included"))}
            for b in s.scalars(select(BenchmarkProduct))]
        done: set[tuple[str, str]] = set()
        for r in s.scalars(select(TeardownFinding)):
            audit = (r.detail or {}).get("audit")
            if audit:
                done.add((r.benchmark_ref, audit))

    if not benchmarks:
        return {"runnable": False,
                "reason": ("no benchmark products have been purchased, so there is nothing "
                           "to audit. The nine schedules exist and are unrun"),
                "audits": [a.to_dict() for a in AUDITS],
                "benchmarks": 0, "run": 0, "outstanding": []}

    outstanding = []
    for b in benchmarks:
        for spec in AUDITS:
            if spec.applies_when == "has_video" and not b["inferred_video"]:
                continue
            if (b["ref"], spec.key) not in done:
                outstanding.append({"benchmark": b["ref"], "audit": spec.key,
                                    "requirement": spec.requirement})
    total = len(done) + len(outstanding)
    return {
        "runnable": True,
        "benchmarks": len(benchmarks),
        "run": len(done),
        "outstanding": outstanding,
        "completeness": round(len(done) / total, 3) if total else 0.0,
        "audits": [a.to_dict() for a in AUDITS],
    }
