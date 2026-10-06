"""The first customer's gate: nine areas, measured on artefacts, and it never says yes.

The owner's instruction, and it is the whole design: **do not reinterpret Launch-0 as beta
quality. The first paid products require extraordinary scrutiny because early reviews have
disproportionate business value.** A shop with no history is carried by its first few reviews
for months, so the first three listings are not a soft launch -- they are the most expensive
products this company will ever ship, measured in what a bad one costs later.

This gate is deliberately NOT `gates.certificate.certify`. Certification asks whether a pattern
is correct. This asks whether *a stranger who paid us* would be right to be pleased, which
takes in the document, the listing, the imagery, the remote state of a marketplace we do not
control, how the file reaches them, and what we told them about safety and licence. Those live
in nine different modules, and a product can pass every one of them separately while the thing
the customer receives is wrong.

**Four states, and the third is the one that matters.**

`PASS` means measured and good. `FAIL` means measured and bad. `UNVERIFIABLE` means the check
could not be run here and says why -- an Etsy round trip with no credentials, an image nobody
has rendered. `UNRESOLVED` means the answer needs a physical act nobody has performed, which
today is every claim resting on `twin.calibrated`.

UNVERIFIABLE and UNRESOLVED are **not** passes and are never counted as passes. That is the
defect this repository keeps meeting -- a verdict computed from the absence of evidence -- and
a first-customer gate is the worst possible place to repeat it. `blocking()` is the list a
human has to clear, and it contains all three non-PASS states.

**It never authorises publication.** `authorises_publication` is a constant False with its
reason attached, because the owner's rule is that automated PASS alone does not authorize
publication and owner review remains required for the first Launch-0 listings. Encoding that as
a field rather than as a sentence in a document is the difference between a rule and a memory:
a caller that wants a yes has to go and ask a person for it.

**It cannot mark anything calibrated.** `twin.calibrated` is False catalogue-wide because no
sample has been crocheted. This gate reports that as UNRESOLVED against the claims that need it
and has no code path that could set it True. Physical validation stays unresolved and must be
explicitly resolved before a claim requiring measurement is published.

**It can clear on evidence (PT-02).** On the publication path the gate is handed the database:
its twin is built with the stored calibration, the size claims clear only on a passed physical
sample bound to this exact content by the certificate's own `bind_physical_evidence`, and the
imagery is read from the disclosed set and the valid listing-set certificate that covers it.
A gate that no owner action could ever clear invites somebody to weaken it under pressure.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"
UNVERIFIABLE = "UNVERIFIABLE"
UNRESOLVED = "UNRESOLVED"

#: Every state that stops a first listing. UNVERIFIABLE and UNRESOLVED are in here on purpose.
BLOCKING_STATES: frozenset[str] = frozenset({FAIL, UNVERIFIABLE, UNRESOLVED})

#: The nine areas the owner named, in the order a customer meets them.
AREAS: tuple[str, ...] = (
    "final_pdf",
    "terminology",
    "counts_and_construction",
    "gauge_and_size_claims",
    "listing_claims",
    "imagery",
    "etsy_remote_state",
    "fulfilment_and_download",
    "licence_and_safety_statements",
)

NEVER_AUTHORISES = (
    "This gate does not authorise publication and has no code path that could. An automated "
    "PASS on all nine areas is evidence for an owner review, not a substitute for one. The "
    "first Launch-0 listings are published by a person who has read the document."
)


@dataclass(frozen=True)
class Check:
    """One area, its state, and what the state was read off."""

    area: str
    state: str
    detail: str
    measured_on: str

    def __post_init__(self) -> None:
        if self.area not in AREAS:
            raise ValueError(f"{self.area!r} is not one of the nine areas: {AREAS}")
        if self.state not in (PASS, FAIL, UNVERIFIABLE, UNRESOLVED):
            raise ValueError(f"{self.state!r} is not a gate state")
        if not self.detail or not self.measured_on:
            raise ValueError(
                f"{self.area}: a check with no detail or no stated instrument is not a check. "
                f"Every state has to say what it read and where")

    @property
    def blocks(self) -> bool:
        return self.state in BLOCKING_STATES

    def to_dict(self) -> dict:
        return {"area": self.area, "state": self.state, "detail": self.detail,
                "measured_on": self.measured_on, "blocks": self.blocks}


@dataclass(frozen=True)
class ProductGate:
    """Every area for one product, and what a person still has to clear."""

    slug: str
    checks: tuple[Check, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen = [c.area for c in self.checks]
        missing = [a for a in AREAS if a not in seen]
        if missing:
            # An area nobody reported is not an area that passed. The gate refuses to exist
            # in a state where a reader could count nine minus the silent ones.
            raise ValueError(
                f"{self.slug}: no check for {missing}. A first-customer gate with a silent "
                f"area is a gate that passes by omission")
        duplicates = sorted({a for a in seen if seen.count(a) > 1})
        if duplicates:
            raise ValueError(f"{self.slug}: {duplicates} reported twice")

    @property
    def blocking(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.blocks)

    @property
    def ready_for_owner_review(self) -> bool:
        """True when nothing is left for software to establish. Still not a yes to publish."""
        return not self.blocking

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "checks": [c.to_dict() for c in self.checks],
            "counts": {state: sum(1 for c in self.checks if c.state == state)
                       for state in (PASS, FAIL, UNVERIFIABLE, UNRESOLVED)},
            "blocking": [c.to_dict() for c in self.blocking],
            "ready_for_owner_review": self.ready_for_owner_review,
            "authorises_publication": False,
            "why": NEVER_AUTHORISES,
        }


# ---------------------------------------------------------------------------
# The nine measurements.
#
# Each takes the rendered artefacts and returns one Check. None of them consults a plan, a
# constant or another module's opinion of itself: every state is read off the document, the
# twin, the listing text or the marketplace.


def _documents(cir, twin, result):
    """Both customer documents, rendered, or the refusal that stopped them."""
    from ..publish.pdf import TERMINOLOGIES, build_pattern_pdf

    out, refusals = {}, {}
    for terminology in TERMINOLOGIES:
        try:
            out[terminology] = build_pattern_pdf(cir, twin=twin, terminology=terminology)
        except Exception as e:  # noqa: BLE001 - the refusal IS the finding
            refusals[terminology] = f"{type(e).__name__}: {e}"
    return out, refusals


def check_final_pdf(cir, docs: dict, refusals: dict) -> Check:
    """Both documents render, carry pages, and report no problems of their own."""
    if refusals:
        return Check("final_pdf", FAIL,
                     "; ".join(f"{t}: {why}" for t, why in sorted(refusals.items())),
                     "publish.pdf.build_pattern_pdf")
    problems = {t: d.problems for t, d in docs.items() if d.problems}
    if problems:
        return Check("final_pdf", FAIL, f"the renderer reports {problems}",
                     "PatternDocument.problems on the rendered bytes")
    pages = {t: d.pages for t, d in sorted(docs.items())}
    if not all(pages.values()):
        return Check("final_pdf", FAIL, f"a document with no pages: {pages}", "rendered bytes")
    return Check("final_pdf", PASS,
                 f"both documents render with no problems: {pages}",
                 "publish.pdf.build_pattern_pdf, problems read off the rendered document")


def check_terminology(cir, docs: dict) -> Check:
    """No stitch reaches either document under a word that means something else there.

    The UK failure this defends against is not theoretical: every UK PDF once stated its gauge
    "in sc" -- not a UK abbreviation at all -- and every special-stitch method said "double
    crochet", which in UK terms is the stitch a US pattern calls single crochet, half the
    height. Both were invisible to a check that localised tokens, because neither was a token.
    """
    from ..publish import abbreviations as ab
    from ..publish.pdf import extracted_text

    unlocalised = ab.unlocalised("UK")
    if unlocalised:
        return Check("terminology", FAIL,
                     f"the writer prints {list(unlocalised)} unchanged where UK needs another "
                     f"word", "publish.abbreviations.unlocalised, measured against the writer")

    for terminology, doc in sorted(docs.items()):
        # This used to call `ab.undefined_tokens(text, terminology)` with no `defined`, which
        # that function's own docstring calls vacuous: the key is then derived from the same
        # string being checked, so every token is in the key by construction and the failing
        # branch is unreachable. It could only ever report PASS, and did -- on eight documents
        # containing an abbreviation no key defined. A gate that cannot fail is not a gate.
        #
        # The honest measurement needs the key the document actually PRINTED, which is in
        # scope in `pdf.py` and not here. So this reads that verdict rather than re-deriving
        # it: re-deriving would put one value in two places, which is how the first version
        # drifted into vacuity. `pdf` measures the document's whole prose against its printed
        # key -- a comparison that can fail, and has.
        undefined = [p for p in doc.problems if p.startswith("PDF_ABBREVIATION_UNDEFINED")]
        if undefined:
            return Check("terminology", FAIL,
                         f"the {terminology} document uses an abbreviation its printed key "
                         f"does not define: {undefined[0]}",
                         "publish.pdf's key-completeness check, measured on the document's "
                         "whole prose against the key it actually printed")
        # And the guard that stops this becoming absence-of-evidence again: `pdf`'s check
        # finds nothing in an empty string too. If the prose never reached the document, the
        # verdict above is silence rather than a pass, and silence must not read as clean.
        if not (doc.prose or "").strip():
            return Check("terminology", UNVERIFIABLE,
                         f"the {terminology} document carries no prose, so the "
                         f"key-completeness check had nothing to measure and its silence "
                         f"cannot be read as a pass",
                         "PatternDocument.prose, checked before trusting an empty problem list")
    return Check("terminology", PASS,
                 "every stitch in both documents is defined by that document's own key, and "
                 "the writer localises every code UK renders differently",
                 "text extracted from both rendered documents")


def check_counts_and_construction(cir, result, twin) -> Check:
    """The arithmetic, and an independent parse of the words that arithmetic produced."""
    from ..cir.reverse import compare
    from ..cir.writer import write_pattern
    from ..products import launch0 as l0

    errors = [f for f in result.findings if f.is_error]
    if errors or not result.ok:
        return Check("counts_and_construction", FAIL,
                     f"the pattern does not compile cleanly: {[f.code for f in errors]}",
                     "cir.compiler.compile_cir")

    for terminology in ("US", "UK"):
        text = write_pattern(cir, result, terminology)
        back = [f for f in compare(cir, text, terminology) if f.is_error]
        if back:
            return Check("counts_and_construction", FAIL,
                         f"the {terminology} document does not read back as the pattern it "
                         f"came from: {[f.code for f in back]}",
                         "cir.reverse.compare, which shares no parsing code with the writer")

    promise = l0.title_promise(cir)
    if not promise["backed"]:
        return Check("counts_and_construction", FAIL, promise["why"],
                     "products.launch0.title_promise against Component.make")
    assembly = l0.assembly_promise(cir)
    if not assembly["backed"]:
        return Check("counts_and_construction", FAIL, assembly["why"],
                     "products.launch0.assembly_promise against cir.assembly")

    return Check("counts_and_construction", PASS,
                 f"compiles with no errors, both documents reverse-compile back to this CIR, "
                 f"and the title's count claim is backed ({promise['why']})",
                 "cir.compiler, cir.reverse on both rendered texts, launch0 promise gates")


def physical_binding(db, cir, result=None) -> dict:
    """The stored physical samples bound to exactly this content, as certification binds them.

    PT-02: the gate built its twin with the default calibration, so a recorded sample could
    never reach it. This reads the same evidence `gate.certify` reads -- the stored
    PhysicalTest rows (`runtime.pipeline.physical_evidence_rows`) -- and binds it with the
    certificate's own `bind_physical_evidence` against the content hash of this CIR's written
    pattern, so a sample of another text, an unfinished sample or a failed one binds nothing.
    """
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..runtime.pipeline import physical_evidence_rows
    from .certificate import _release_hash, bind_physical_evidence

    from ..runtime.pipeline import calibrated_primitives
    from .risk_matrix import first_customer_requirement, matrix_for

    result = result if result is not None else compile_cir(cir)
    content = _release_hash(cir, write_pattern(cir, result, "US"))
    binding = bind_physical_evidence(physical_evidence_rows(db, cir.slug), slug=cir.slug,
                                     version=cir.version, content_hash=content)
    # F-073/F-081: which physical evidence class this product's risk tier needs here.
    matrix = matrix_for(cir, result, calibrated_primitives=calibrated_primitives(db))
    return {**binding, "risk_matrix": matrix,
            "first_customer": first_customer_requirement(matrix, binding)}


def check_gauge_and_size_claims(cir, twin, physical: dict | None = None) -> Check:
    """Every size in the document is arithmetic from a gauge nobody has crocheted.

    This is the area that must not be allowed to go green by being forgotten. `twin.calibrated`
    is False for every product in the catalogue because no sample has been worked, so every
    finished measurement is a computation from the CIR's stated gauge. That is honest to
    print -- the documents label it -- and it is NOT the same as a measured size, so the state
    is UNRESOLVED rather than PASS, and nothing here can set `calibrated` True.
    """
    if physical is not None:
        # PT-02: the runtime path. Only a passed, completed sample bound to this exact
        # content clears this area; the twin's calibration factor is reported with it.
        if not physical.get("passed"):
            unbound = "; ".join(f"{u.get('id')}: {u.get('why')}"
                                for u in (physical.get("unbound") or [])[:3])
            return Check("gauge_and_size_claims", UNRESOLVED,
                         "no passed physical sample is bound to this content "
                         f"({str(physical.get('content_hash') or '')[:12]})"
                         + (f"; samples on file that do not bind: {unbound}" if unbound
                            else "; none on file")
                         + ". Every finished dimension is arithmetic from the stated gauge "
                           "until somebody works this text",
                         "gates.certificate.bind_physical_evidence on stored PhysicalTest rows")
        tier = physical.get("first_customer")
        if tier is not None and not tier.get("met"):
            # F-072/F-081: a bound sample of the wrong class (a swatch where the risk tier
            # needs a full make) is not the evidence this product needs.
            return Check("gauge_and_size_claims", UNRESOLVED, tier["why"],
                         "gates.risk_matrix.first_customer_requirement on bound PhysicalTest "
                         "rows")
        if twin.width_caveat:
            return Check("gauge_and_size_claims", FAIL,
                         f"a width rests on an assumed chain gauge: {twin.width_caveat}",
                         "TwinModel.width_caveat")
        return Check("gauge_and_size_claims", PASS,
                     f"physical sample(s) {physical.get('bound')} passed against this exact "
                     f"content ({str(physical.get('content_hash'))[:12]}); twin calibrated="
                     f"{twin.calibrated}; {twin.width_cm:.1f} x {twin.height_cm:.1f} cm",
                     "gates.certificate.bind_physical_evidence on stored PhysicalTest rows, "
                     "twin built with quality.physical.calibration_from_db")
    if not twin.calibrated:
        return Check("gauge_and_size_claims", UNRESOLVED,
                     "twin.calibrated is False: every finished dimension is arithmetic from "
                     "the gauge the CIR states, and no sample has been crocheted. The "
                     "documents say so, which keeps the claim truthful, but a claim that a "
                     "measurement is measured cannot be published until somebody works one",
                     "cir.twin.TwinModel.calibrated")
    if twin.width_caveat:
        return Check("gauge_and_size_claims", FAIL,
                     f"a width rests on an assumed chain gauge: {twin.width_caveat}",
                     "TwinModel.width_caveat")
    return Check("gauge_and_size_claims", PASS,
                 f"calibrated against a worked sample; {twin.width_cm:.1f} x "
                 f"{twin.height_cm:.1f} cm", "TwinModel, calibrated")


# ---- what the listing says the product IS (PT-01) ----------------------------------------
#
# A closed vocabulary of product-type words, grouped into families of words that name the same
# object. Closed on purpose, for the same reason `launch0.COLOURWORK_CLAIMS` is: an open
# detector argues with prose, and these are nouns that mean one specific object. A word in a
# listing's title or tags that names a family the CIR does not name is a listing for another
# product -- the basket titled "Market Mosaic Blanket" that every gate passed.

PRODUCT_TYPE_FAMILIES: dict[str, tuple[str, ...]] = {
    "blanket": ("blanket", "afghan", "throw", "graphghan"),
    "basket": ("basket",),
    "coaster": ("coaster",),
    "placemat": ("placemat",),
    "runner": ("runner",),
    "pillow": ("pillow", "cushion"),
    "scarf": ("scarf", "scarves", "cowl"),
    "hat": ("hat", "beanie"),
    "shawl": ("shawl",),
    "bag": ("bag", "tote", "purse"),
    "ornament": ("ornament",),
    "stocking": ("stocking",),
    "garland": ("garland", "bunting"),
    "mobile": ("mobile",),
    "wreath": ("wreath",),
    "toy": ("toy", "amigurumi", "doll", "lovey"),
    "garment": ("sweater", "cardigan", "pullover"),
    "rug": ("rug",),
    "wall_hanging": ("wall hanging",),
}


def _family_hits(text: str) -> dict[str, list[str]]:
    import re

    low = " ".join(str(text or "").lower().replace("-", " ").split())
    out: dict[str, list[str]] = {}
    for family, words in PRODUCT_TYPE_FAMILIES.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}(?:s|es)?\b", low):
                out.setdefault(family, []).append(w)
    return out


def product_type_words_in_cir(cir) -> frozenset[str]:
    """The product-type families the CIR itself names: its title and its component names."""
    text = " ".join([cir.title or ""] + [c.name or "" for c in cir.components])
    return frozenset(_family_hits(text))


def product_type_findings(cir, *, title: str, tags=()) -> list[str]:
    """Product-type words in a listing's title or tags that the CIR does not name (PT-01).

    The description is not read: a children's statement may name a blanket or a toy as the
    thing this product is NOT, and that is a statement, not a type claim.
    """
    own = product_type_words_in_cir(cir)
    out = []
    for where, text in [("title", title)] + [(f"tag {t!r}", t) for t in (tags or ())]:
        for family, words in sorted(_family_hits(text).items()):
            if family not in own:
                out.append(f"LISTING_PRODUCT_TYPE_UNSUPPORTED: the {where} names a "
                           f"{words[0]!r}, and the CIR ({cir.slug}) makes "
                           f"{sorted(own) or 'no named product type'}")
    return out


def colourwork_findings(cir, twin, *, title: str, tags=()) -> list[str]:
    """A colourwork technique in the title or tags that the fabric cannot make (PT-01).

    `launch0.fabric_truth` measures colours per row; a mosaic needs two in one row and a CIR
    row carries one colour, so the claim is refused unless the twin shows otherwise.
    """
    from ..products import launch0 as l0

    grid = twin.color_grid() if twin is not None else []
    per_row = max((len({c for c in row}) for row in grid), default=0)
    if per_row >= 2:
        return []
    out = []
    for where, text in [("title", title)] + [(f"tag {t!r}", t) for t in (tags or ())]:
        low = str(text or "").lower()
        hit = next((c for c in l0.COLOURWORK_CLAIMS if c in low), None)
        if hit:
            out.append(f"LISTING_COLOURWORK_UNSUPPORTED: the {where} claims {hit!r}; the "
                       f"fabric puts at most {per_row} colour(s) in any one row")
    return out


def check_listing_claims(cir, twin, listing, *, physically_evidenced: bool | None = None) -> Check:
    """What the listing says, against what the pattern is -- and a listing must exist.

    `listing` is the assembled draft. A product with no listing text is UNVERIFIABLE here, not
    PASS: nothing has been said yet, so nothing has been checked, and those are different.
    """
    from .asset_truth import check_shape_claims, check_technique_claims
    from .policy import ListingDraft, check_listing

    if listing is None:
        return Check("listing_claims", UNVERIFIABLE,
                     "no listing draft has been assembled for this product, so there is no "
                     "copy to check. An unwritten listing is unchecked, not clean",
                     "absence of a ListingDraft")

    draft = listing if isinstance(listing, ListingDraft) else ListingDraft(
        title=listing["title"], description=listing["description"],
        tags=list(listing.get("tags") or []), price_cad=float(listing.get("price_cad", 0.0)))

    # `check_listing` needs the proof states this release actually established. Rungs four and
    # five are customer facts and are False while this company has no customers; claiming
    # either is refused there rather than argued about here.
    proof = {"deterministic_validation": True,
             "independent_reverse_compilation": True,
             "physical_tester_example": bool(twin.calibrated if physically_evidenced is None
                                             else physically_evidenced),
             "customer_project": False,
             "repeat_purchase": False}
    findings = [f for f in check_listing(draft, cir, proof_states=proof) if f.is_error]
    findings += [f for f in check_shape_claims(draft.title, cir, twin, "listing.title")
                 if f.is_error]
    findings += [f for f in check_technique_claims(draft.title, cir, twin, "listing.title")
                 if f.is_error]
    findings += [f for f in check_technique_claims(draft.description, cir, twin,
                                                   "listing.description") if f.is_error]
    if findings:
        return Check("listing_claims", FAIL,
                     f"{[f.code for f in findings]}: {findings[0].message[:160]}",
                     "gates.policy.check_listing and gates.asset_truth claim checks")
    # PT-01: the listing must name the product the CIR makes, and no fabric it cannot make.
    wrong = (product_type_findings(cir, title=draft.title, tags=draft.tags)
             + colourwork_findings(cir, twin, title=draft.title, tags=draft.tags))
    if wrong:
        return Check("listing_claims", FAIL, "; ".join(wrong[:3])[:400],
                     "gates.first_customer.product_type_findings and colourwork_findings on "
                     "the listing's title and tags")
    return Check("listing_claims", PASS,
                 "the listing's shape, technique and proof claims are all backed by the twin "
                 "and by this release's own evidence",
                 "gates.policy.check_listing and gates.asset_truth on the assembled draft")


def disclosed_imagery(db, slug: str, version: str) -> dict | None:
    """The disclosed listing set for this release and the certificate that covers it (PT-02).

    D-FB-7 made the disclosed render set the Launch-0 imagery, and the gate only ever read the
    legacy frame plan, so imagery read UNVERIFIABLE with a certified set on file. This reads
    what publication actually uploads: `disclosed_listing.usable_set` (every frame's bound
    bytes structurally PASS now) and the current valid listing-set certificate for the
    release, which must cover exactly those frames as disclosed renders, bound to a release
    hash. None when no disclosed set is on file for this release.
    """
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord
    from ..publish import disclosed_listing

    rec = disclosed_listing.last_asset(db, slug=slug)
    if rec is None or rec.get("version") != version:
        return None
    usable = disclosed_listing.usable_set(db, slug=slug, version=version)
    if usable is None:
        return {"state": FAIL, "detail": (
            "a disclosed set is on file for this release and is not usable: "
            + ("; ".join(rec.get("launch_blocked") or [])[:300]
               or "structural truth is not PASS on every frame's bytes"))}
    with db.session() as s:
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        cert_frames = list((cert.certificate or {}).get("frames") or []) if cert else []
        cert_release = (cert.release_hash or "") if cert else ""
        cert_id = cert.id if cert else None
    if cert is None:
        return {"state": FAIL, "detail": (
            "the disclosed set is usable but no valid listing-set certificate covers it; "
            "imagery is certified by release_gates.listing_set before it is published")}
    on_file = {(f.get("image") or {}).get("sha256") for f in usable.get("frames") or []}
    certified = {f.get("sha256") for f in cert_frames}
    problems = []
    if not cert_release:
        problems.append(f"certificate {cert_id} is bound to no release hash")
    if certified != on_file:
        problems.append(f"certificate {cert_id} covers {len(certified)} frame(s) that are not "
                        f"exactly the {len(on_file)} disclosed frame(s) on file")
    if any(f.get("kind") != "disclosed_render" for f in cert_frames):
        problems.append(f"certificate {cert_id} does not certify every frame as a disclosed "
                        f"render")
    if problems:
        return {"state": FAIL, "detail": "; ".join(problems)}
    return {"state": PASS, "detail": (
        f"{len(on_file)} disclosed frames, structurally PASS on their bound bytes, covered "
        f"by valid listing-set certificate {cert_id} for release {cert_release[:12]}"),
        "certificate": cert_id}


def check_imagery(cir, twin, frames, disclosed: dict | None = None) -> Check:
    """The images a buyer scrolls, and the structural rules that come before Asset Truth.

    `frames` is what `publish.listing_assets.build_frames` produced. None means no imagery has
    been built, which is UNVERIFIABLE: a listing with no pictures is not a listing with clean
    pictures. The blank-hero defect is why this reads the plan rather than trusting it -- a
    hero that rendered as an empty cream rectangle satisfied every check that asked whether a
    hero existed.
    """
    from ..publish.listing_assets import check_frame_plan

    if disclosed is not None:
        return Check("imagery", disclosed["state"], disclosed["detail"],
                     "publish.disclosed_listing.usable_set and the valid "
                     "ListingSetCertificateRecord for this release")
    if not frames:
        return Check("imagery", UNVERIFIABLE,
                     "no listing frames have been built for this product, so there is nothing "
                     "to check. An unbuilt image set is unchecked, not clean",
                     "absence of publish.listing_assets frames")
    problems = check_frame_plan(list(frames))
    if problems:
        return Check("imagery", FAIL, "; ".join(problems[:3]),
                     "publish.listing_assets.check_frame_plan")
    return Check("imagery", PASS,
                 f"{len(frames)} frames, and the structural rules Asset Truth runs after are "
                 f"satisfied", "publish.listing_assets.check_frame_plan")


def check_etsy_remote_state() -> Check:
    """What Etsy says is there -- which today nothing has ever asked it.

    The three launch gaps in `publish.listing_schema` are open on missing *evidence*, not on
    missing capability: the transport is built and exercised against a faithful local model of
    Etsy, and Etsy itself has confirmed only that it is reachable, that the key header format
    is right, that a bad key is 403, and that it refuses on the key before reading a body. One
    authenticated round trip closes this area; nothing in software can.
    """
    from ..publish import listing_schema

    open_gaps = [g for g in listing_schema.gaps()]
    if open_gaps:
        return Check("etsy_remote_state", UNVERIFIABLE,
                     f"{len(open_gaps)} open: {open_gaps[0]}. Nothing has ever authenticated "
                     f"against Etsy, so no remote state has ever been read back. One owner "
                     f"browser authorisation and one controlled round trip settle this",
                     "publish.listing_schema.gaps")
    return Check("etsy_remote_state", PASS,
                 "the remote listing has been read back from Etsy and matches what we sent",
                 "publish.listing_schema.gaps, empty")


def check_fulfilment_and_download(store=None) -> Check:
    """Whether the file the customer paid for survives long enough to reach them.

    The artifact store announces its own ephemerality -- `ArtifactStore.durable` is False in a
    container, and the release chain audits `assets.storage_not_durable` every time. A buyer
    whose download link resolves to a file a redeploy deleted is the single worst first-customer
    outcome available to us, worse than a wrong stitch count, because it looks like theft.
    """
    from ..core.artifacts import ArtifactStore

    store = store or ArtifactStore()
    if not getattr(store, "durable", False):
        return Check("fulfilment_and_download", FAIL,
                     "the artifact store is not durable: the rendered PDF lives on a container "
                     "filesystem that a redeploy reclaims, so a paid download can resolve to "
                     "nothing. Object storage is the fix and it is an owner decision",
                     "core.artifacts.ArtifactStore.durable")
    return Check("fulfilment_and_download", PASS,
                 "the artifact store is durable, so a paid download outlives a redeploy",
                 "core.artifacts.ArtifactStore.durable")


def check_licence_and_safety_statements(cir, docs: dict, assignment) -> Check:
    """The licence and, for a children's product, the safety set -- read off the bytes.

    Both are read from the rendered document rather than from the module that generates them,
    because the licence defect this defends against was exactly that: the consistency check ran
    on `terms.render(terms, "pdf")` -- the decision rendered *for* the PDF surface -- while the
    PDF itself carried a fourth copy granting the opposite on two points.
    """
    from ..commerce import terms as terms_mod
    from ..publish.pdf import childrens_statements_in, extracted_text

    for terminology, doc in sorted(docs.items()):
        text = extracted_text(doc.pdf_bytes)
        # Each axis of the decision, looked for in this document's own extracted text. The
        # other two surfaces are checked where they are assembled; what is being established
        # here is that the copy the customer KEEPS says what the decision says.
        missing = [axis for axis in terms_mod.AXES
                   if terms_mod.BRAMBLELOOP_TERMS.sentence(axis) not in text]
        if missing:
            return Check("licence_and_safety_statements", FAIL,
                         f"the {terminology} document does not carry the canonical licence on "
                         f"{missing}",
                         "commerce.terms.BRAMBLELOOP_TERMS sentence by sentence, against the "
                         "text extracted from the rendered PDF")

    if assignment is not None:
        for terminology, doc in sorted(docs.items()):
            carried = childrens_statements_in(doc.pdf_bytes, assignment)
            if not carried.get("complete"):
                return Check("licence_and_safety_statements", FAIL,
                             f"the {terminology} document is missing "
                             f"{carried.get('missing')}",
                             "publish.pdf.childrens_statements_in on the rendered bytes")
        return Check("licence_and_safety_statements", PASS,
                     "both documents carry the canonical licence and the full children's "
                     "statement set for this audience",
                     "text extracted from both rendered documents")

    return Check("licence_and_safety_statements", PASS,
                 "both documents carry the canonical licence; this product is not "
                 "merchandised to a child, so no safety statement set attaches to it",
                 "text extracted from both rendered documents")


# ---------------------------------------------------------------------------
# The driver.


def gate_product(cir, *, listing=None, frames=None, store=None, db=None,
                 version: str | None = None) -> ProductGate:
    """All nine areas for one product, measured on what it actually produces.

    `listing` and `frames` are passed in rather than built here on purpose: this gate reports
    on the artefacts a release produced, and building them itself would make it a test of the
    generator rather than a check on the output. Absent, they read UNVERIFIABLE, which is the
    honest answer for a product nobody has written a listing or an image set for yet.
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..products import launch0 as l0

    result = compile_cir(cir)
    if not result.ok:
        # Without a twin nothing downstream can be measured at all, and eight FAILs from one
        # cause would read as eight problems. One honest cause, eight times.
        why = f"does not compile: {[f.code for f in result.findings if f.is_error]}"
        return ProductGate(cir.slug, tuple(
            Check(area, FAIL, why, "cir.compiler.compile_cir") for area in AREAS))

    # PT-02: with a database, the twin carries the stored calibration and the size claims are
    # judged on content-bound physical evidence; the imagery is the disclosed set and its
    # certificate. Without one (a report, a test of the artefacts alone) both stay as they
    # were: uncalibrated and unbuilt, which block.
    physical = disclosed = None
    if db is not None:
        from ..quality.physical import calibration_from_db

        twin = build_twin(cir, result, calibration=calibration_from_db(db, cir))
        physical = physical_binding(db, cir, result)
        disclosed = disclosed_imagery(db, cir.slug, version or cir.version)
    else:
        twin = build_twin(cir, result)
    # "Made by a tester" needs a full make bound to this content, not a swatch (F-072).
    evidenced = None if physical is None else any(
        c == "full_physical_make" for c in (physical.get("bound_classes") or {}).values())
    docs, refusals = _documents(cir, twin, result)
    assignment = l0.childrens_assignment(cir.slug)

    if refusals:
        # The document refused to render. Everything read off the document is unmeasurable,
        # and says so rather than failing for a reason that is not its own.
        unreadable = "; ".join(f"{t}: {w}" for t, w in sorted(refusals.items()))
        from_docs = ("terminology", "licence_and_safety_statements")
        checks = [check_final_pdf(cir, docs, refusals)]
        checks += [Check(a, UNVERIFIABLE,
                         f"the document did not render, so nothing could be read off it "
                         f"({unreadable})", "publish.pdf.build_pattern_pdf refusal")
                   for a in from_docs]
        checks.append(check_counts_and_construction(cir, result, twin))
        checks.append(check_gauge_and_size_claims(cir, twin, physical))
        checks.append(check_listing_claims(cir, twin, listing, physically_evidenced=evidenced))
        checks.append(check_imagery(cir, twin, frames, disclosed))
        checks.append(check_etsy_remote_state())
        checks.append(check_fulfilment_and_download(store))
        return ProductGate(cir.slug, tuple(checks))

    return ProductGate(cir.slug, (
        check_final_pdf(cir, docs, refusals),
        check_terminology(cir, docs),
        check_counts_and_construction(cir, result, twin),
        check_gauge_and_size_claims(cir, twin, physical),
        check_listing_claims(cir, twin, listing, physically_evidenced=evidenced),
        check_imagery(cir, twin, frames, disclosed),
        check_etsy_remote_state(),
        check_fulfilment_and_download(store),
        check_licence_and_safety_statements(cir, docs, assignment),
    ))


def blocking(cir, *, listing=None, frames=None, store=None, db=None,
             version: str | None = None) -> list[dict]:
    """What still stops this product's first listing, as the runtime reads it (F-118).

    The nine-area gate had no runtime caller: it reported UNRESOLVED physical claims to a test
    and to nobody else. `publish.eligibility.product_publication` calls this for every
    Launch-0 slug on the way to publication, so a claim resting on an uncalibrated twin, an
    unbuilt image set or an unread Etsy listing refuses publication instead of being a line
    in a report. Empty means ready for *owner review*, never authorised: see NEVER_AUTHORISES.
    """
    gate = gate_product(cir, listing=listing, frames=frames, store=store, db=db,
                        version=version)
    return [c.to_dict() for c in gate.blocking]


def gate_launch0(*, listings=None, frames=None, store=None) -> dict:
    """Every Launch-0 variant, and the one sentence the whole module exists to make true.

    `LAUNCH0_SLUGS` drives it rather than a list kept here, so a product that leaves Launch-0
    leaves this gate with it and a product that joins cannot join unchecked.
    """
    from ..products import launch0 as l0

    listings = listings or {}
    frames = frames or {}
    gates: list[ProductGate] = []
    for slug in l0.LAUNCH0_SLUGS:
        for variant in l0.candidate(slug).variants:
            cir = l0.cir_for(variant.build)
            gates.append(gate_product(cir, listing=listings.get(cir.slug),
                                      frames=frames.get(cir.slug), store=store))

    blocking = {g.slug: [c.to_dict() for c in g.blocking] for g in gates if g.blocking}
    return {
        "products": [g.to_dict() for g in gates],
        "variants_checked": len(gates),
        "ready_for_owner_review": [g.slug for g in gates if g.ready_for_owner_review],
        "blocking": blocking,
        "authorises_publication": False,
        "why": NEVER_AUTHORISES,
        "physical_validation": (
            "unresolved: twin.calibrated is False for every Launch-0 product, and this module "
            "has no code path that could set it True. Any claim that a measurement is measured "
            "stays unpublishable until a sample is crocheted"),
    }
