"""Not misled before the purchase, not stranded after it.

Requirements 36, 41, 42. Three requirements about the same customer at three moments, and all
three failures are quiet: nobody complains, they just refund, or they do not come back.

**#36 — proof and promise are different pictures.** A photograph of a finished object made
from this pattern is evidence. A render of what it might look like is a promise. Both belong
in a listing and they may not be confused, so an image carries its provenance, its consent and
licence basis, the pattern version it depicts, the yarn and colourway used, and whether it is
physical or simulated. A tester's photograph without recorded consent is somebody's property,
and using it is the same error as using a competitor's — arriving from the friendly direction,
which is why it needs a mechanical check rather than good intentions.

**#41 — a refund is usually a misunderstanding that was allowed to happen.** The buyer thought
they were buying a blanket. Everything needed to prevent that is knowable before the sale:
that it is a digital pattern, what skill it assumes, what materials they must already own,
which terminology it uses, how the file arrives. The disclosure set is therefore closed and
checked, because "it says so in the description" is true of a description nobody read, and the
cost lands as a refund plus a support case plus a rating.

**#42 — support has to answer against the version the buyer owns.** A pattern is a software
release and a customer runs an old build. When a correction is material, the company has to be
able to say *which buyers are affected* — which requires the order-to-version map to have been
written at sale time, because it cannot be reconstructed afterwards. This is the requirement
that is impossible to retrofit, which is why it is built before there is a single order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# #36: what an image is, and what it is allowed to claim

PHYSICAL = "physical"
SIMULATED = "simulated"

# Where an image came from, and whether it can serve as proof. Proof requires a real object.
IMAGE_KINDS: dict[str, tuple[str, str]] = {
    "tester_photo": (PHYSICAL, "a tester's photograph of an object they actually made"),
    "customer_photo": (PHYSICAL, "a buyer's photograph, used with recorded permission"),
    "studio_photo": (PHYSICAL, "our own photograph of a finished object"),
    "twin_render": (SIMULATED, "a deterministic render of the pattern's own geometry"),
    "chart_render": (SIMULATED, "a render of the chart being sold"),
    "concept_illustration": (SIMULATED, "an illustration of an idea, not of an object"),
}

# What makes third-party imagery usable. `assumed` is not on the list on purpose.
CONSENT_BASES: dict[str, str] = {
    "written_permission": "the person agreed in writing, for this use",
    "tester_agreement": "covered by the signed tester agreement in force at the time",
    "our_own_work": "photographed by this company, of an object it owns",
    "licensed": "licensed, with the licence reference recorded",
}


class TrustRefused(ValueError):
    """An image that cannot prove what it is used for, or a disclosure that is missing."""


@dataclass(frozen=True)
class ImageRecord:
    """One listing image and everything a later question would need."""

    ref: str
    kind: str
    pattern_version: str
    consent_basis: str = ""
    consent_ref: str = ""
    yarn: str = ""
    colourway: str = ""
    photographer: str = ""
    recorded_on: str = ""

    @property
    def nature(self) -> str:
        return IMAGE_KINDS[self.kind][0]

    @property
    def is_proof(self) -> bool:
        return self.nature == PHYSICAL

    def to_dict(self) -> dict:
        return {"ref": self.ref, "kind": self.kind, "nature": self.nature,
                "is_proof": self.is_proof, "pattern_version": self.pattern_version,
                "consent_basis": self.consent_basis, "consent_ref": self.consent_ref,
                "yarn": self.yarn, "colourway": self.colourway,
                "photographer": self.photographer,
                "recorded_on": self.recorded_on or date.today().isoformat(),
                "meaning": IMAGE_KINDS[self.kind][1]}


def record_image(ref: str, kind: str, *, pattern_version: str, consent_basis: str = "",
                 consent_ref: str = "", yarn: str = "", colourway: str = "",
                 photographer: str = "") -> ImageRecord:
    """Record an image with the provenance a later question would need.

    Third-party imagery needs a recorded consent basis before it exists as a record. A
    tester's photograph without one is somebody's property, and using it is the same error as
    using a competitor's — arriving from the friendly direction, which is exactly why it gets
    a mechanical check instead of good intentions.
    """
    if kind not in IMAGE_KINDS:
        raise TrustRefused(f"{kind!r} is not an image kind: {sorted(IMAGE_KINDS)}")
    if not pattern_version:
        raise TrustRefused(
            f"{ref}: an image depicts a specific version of the pattern. Without that, a "
            f"correction cannot tell which images are now wrong")

    third_party = kind in ("tester_photo", "customer_photo")
    if third_party:
        if consent_basis not in CONSENT_BASES:
            raise TrustRefused(
                f"{ref}: a {kind} needs a recorded consent basis "
                f"({sorted(CONSENT_BASES)}). Using somebody's photograph because they "
                f"seemed happy about it is the same error as using a competitor's, arriving "
                f"from the friendly direction")
        if not consent_ref.strip():
            raise TrustRefused(
                f"{ref}: name where the consent is recorded, or the basis is an assertion")
    if IMAGE_KINDS[kind][0] == PHYSICAL and not yarn:
        raise TrustRefused(
            f"{ref}: a photograph of a real object records the yarn it was made in. A buyer "
            f"choosing a substitute is choosing against this picture")

    return ImageRecord(ref=ref, kind=kind, pattern_version=pattern_version,
                       consent_basis=consent_basis, consent_ref=consent_ref,
                       yarn=yarn, colourway=colourway, photographer=photographer,
                       recorded_on=date.today().isoformat())


def gallery_proof(images: list[ImageRecord]) -> dict:
    """Does this gallery contain evidence, or only promises? (#36)

    A listing of renders is not dishonest, and it is also not proof. The distinction is
    reported rather than enforced, because a pattern with no finished object yet genuinely
    has no proof to show — and saying so is better than pretending either way.
    """
    proof = [i for i in images if i.is_proof]
    simulated = [i for i in images if not i.is_proof]
    versions = sorted({i.pattern_version for i in images})
    return {
        "images": len(images),
        "proof_images": len(proof),
        "simulated_images": len(simulated),
        "has_physical_proof": bool(proof),
        "pattern_versions_depicted": versions,
        "mixed_versions": len(versions) > 1,
        "note": ("no photograph of a finished object: this gallery shows what the pattern "
                 "would produce, not what it has produced. That is honest and it is not "
                 "proof (#36)" if not proof else
                 f"{len(proof)} of {len(images)} images are photographs of real objects"),
    }


# ---------------------------------------------------------------------------
# #41: the misunderstanding that becomes a refund

# Everything a buyer needs before paying in order not to be surprised afterwards. Closed,
# because "it says so in the description" is true of a description nobody read.
REQUIRED_DISCLOSURES: dict[str, str] = {
    "digital_not_finished": "DIGITAL CROCHET PATTERN — NOT A FINISHED ITEM",
    "skill_level": "the skill the pattern is written for",
    "required_materials": "what the buyer must already own or buy",
    "terminology": "US or UK crochet terms",
    "delivery": "how and when the file arrives",
    "support": "how to ask a question, and from which version it is answered",
}

# Where a disclosure has to appear. The title is included deliberately: it is the only one
# some buyers read.
SURFACES: tuple[str, ...] = ("title", "first_screen", "description", "file")

# The one disclosure that must be in the title, because a refund for this reason is the
# single most preventable one in the category.
TITLE_CRITICAL = "digital_not_finished"


# ---------------------------------------------------------------------------
# #258: the gallery of real finished projects, and the version it belongs to

# A gallery entry is a photograph plus the facts that make it usable as proof. The pattern
# version is not decoration: a customer's photograph of v1.0.0 shown beside a listing selling
# v1.2.0 is proof of a different object, and it is the most believable wrong thing on the
# page because it is real.
GALLERY_KINDS: tuple[str, ...] = ("tester_photo", "customer_photo")

# What a gallery entry has to carry beyond what `record_image` already requires. The yarn is
# not on this list because the constructor above already refuses a physical photograph
# without one; the colourway is, because it is the thing a browser is actually choosing from
# and nothing has required it until now.
GALLERY_NOTES: tuple[str, ...] = ("colourway",)


def customer_gallery(images: list[ImageRecord], *, selling_version: str = "") -> dict:
    """The gallery as proof, and which entries are proof of a different object (#258).

    `selling_version` is the version the listing currently sells. An entry against an older
    version is not removed -- it is real, and it is the strongest kind of evidence this shop
    can hold -- but it is marked, because the yarn note and the colour note belong to the
    pattern that was current when the photograph was taken. That marking is the new thing
    here; the consent check below is a second line rather than the line, since `record_image`
    already refuses a third-party photograph without a recorded basis and reference, and a
    record that reaches this function without one was not built through it.
    """
    entries, problems = [], []
    for image in images:
        if image.kind not in GALLERY_KINDS:
            continue
        missing = [n for n in GALLERY_NOTES if not getattr(image, n, "")]
        superseded = bool(selling_version and image.pattern_version != selling_version)
        if not image.consent_ref.strip():
            problems.append({"ref": image.ref, "why": (
                "no recorded consent reference. A customer's photograph without one is "
                "somebody's property, and a gallery is the most public place to be wrong "
                "about that")})
            continue
        entries.append({
            "ref": image.ref, "kind": image.kind,
            "pattern_version": image.pattern_version,
            "yarn": image.yarn, "colourway": image.colourway,
            "missing_notes": missing,
            "superseded": superseded,
            "why": ((f"made from {image.pattern_version}, and the listing sells "
                     f"{selling_version}: real, and proof of a different object")
                    if superseded else
                    (f"missing {missing}: evidence that somebody made something, rather than "
                     f"proof of what this pattern produces in a named yarn")
                    if missing else ""),
        })
    return {
        "entries": entries,
        "usable": sum(1 for e in entries if not e["superseded"] and not e["missing_notes"]),
        "refused": problems,
        "note": ("no customer or tester photograph exists yet, so this gallery is empty "
                 "rather than thin" if not entries and not problems else ""),
    }


def proof_lift(*, design: str, with_gallery: dict | None = None,
               without_gallery: dict | None = None) -> dict:
    """Whether the gallery improved conversion, or why that cannot be said (#258).

    A gallery added to every listing measures the month it was added. The design decides
    what may be claimed, and `growth.experiments` already holds which designs carry a causal
    claim rather than an association.
    """
    from ..growth.experiments import CAUSAL_DESIGNS

    causal = design in CAUSAL_DESIGNS
    if not (with_gallery and without_gallery):
        return {"measurable": False, "causal": causal,
                "why": ("both arms are needed: a gallery added to every listing measures the "
                        "month it was added, not the gallery")}
    a, b = with_gallery, without_gallery
    lift = ((a["conversion"] - b["conversion"]) / b["conversion"]) if b["conversion"] else None
    return {
        "measurable": True, "causal": causal,
        "lift": None if lift is None else round(lift, 4),
        "claim": ("the gallery moved conversion" if causal else
                  "an association: this design cannot separate the gallery from the week"),
    }


def disclosure_check(present: dict) -> dict:
    """Which purchase-protecting disclosures are in place, and where (#41)."""
    unknown = [k for k in present if k not in REQUIRED_DISCLOSURES]
    if unknown:
        raise TrustRefused(f"{sorted(unknown)} are not required disclosures: "
                           f"{sorted(REQUIRED_DISCLOSURES)}")

    missing, misplaced = [], []
    for key, meaning in REQUIRED_DISCLOSURES.items():
        surfaces = present.get(key) or []
        bad = [s for s in surfaces if s not in SURFACES]
        if bad:
            raise TrustRefused(f"{key}: {bad} are not listing surfaces: {list(SURFACES)}")
        if not surfaces:
            missing.append({"disclosure": key, "meaning": meaning})
        elif key == TITLE_CRITICAL and "title" not in surfaces:
            misplaced.append({
                "disclosure": key,
                "why": ("this one belongs in the title: a buyer who thinks they are buying a "
                        "blanket does not read the description, and that refund is the most "
                        "preventable one in the category")})

    return {
        "complete": not missing and not misplaced,
        "missing": missing,
        "misplaced": misplaced,
        "required": REQUIRED_DISCLOSURES,
        "note": ("A refund is usually a misunderstanding that was allowed to happen, and "
                 "everything needed to prevent it is knowable before the sale (#41)."),
    }


def confusion_rate(db, *, days: int = 90) -> dict:
    """Confusion-driven contacts and refunds as a product defect, not a cost of doing business.

    Treated as a defect because that is what it is: the listing failed to say something, and
    the same listing will fail again tomorrow. Counting it as a cost budgets for it instead.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry, SupportCase

    with db.session() as s:
        cases = list(s.scalars(select(SupportCase)))
        sales = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))
        refunds = [x for x in sales if x.refunds_cad > 0]

    confused = [c for c in cases if "confus" in (getattr(c, "theme", "") or "").lower()
                or "not a finished" in (getattr(c, "question", "") or "").lower()]
    orders = len(sales)
    if not orders:
        return {"measurable": False,
                "reason": ("no orders, so there is no confusion rate. This is the state the "
                           "disclosures are built for rather than measured from"),
                "orders": 0, "confusion_contacts": len(confused)}
    return {
        "measurable": True,
        "orders": orders,
        "confusion_contacts": len(confused),
        "refunds": len(refunds),
        "confusion_rate": round(len(confused) / orders, 4),
        "refund_rate": round(len(refunds) / orders, 4),
        "note": ("Confusion contacts are a listing defect, not a cost of doing business. "
                 "Counting them as a cost budgets for them (#41)."),
    }


# ---------------------------------------------------------------------------
# #42: the buyer runs an old build

@dataclass
class VersionMap:
    """Order to purchased version to current safe version.

    Written at sale time because it cannot be reconstructed afterwards: once the listing has
    moved to 1.2.0 there is no record of who bought 1.1.0 unless somebody wrote it down. This
    is the requirement that is impossible to retrofit, which is why it exists before the first
    order does.
    """

    rows: list = field(default_factory=list)

    def record_sale(self, *, order_ref: str, product_slug: str, version: str,
                    sold_on: str = "") -> dict:
        if not order_ref or not version:
            raise TrustRefused("an order maps to a version, or support cannot answer it")
        row = {"order_ref": order_ref, "product_slug": product_slug,
               "purchased_version": version,
               "sold_on": sold_on or date.today().isoformat()}
        self.rows.append(row)
        return row

    def affected_by(self, *, product_slug: str, corrected_from: tuple[str, ...]) -> list[dict]:
        """Exactly which buyers hold a version a material correction applies to."""
        return [r for r in self.rows
                if r["product_slug"] == product_slug
                and r["purchased_version"] in corrected_from]

    def to_dict(self) -> dict:
        return {"orders": len(self.rows), "rows": list(self.rows)}


def correction_notice(*, product_slug: str, affected: list[dict], from_versions: tuple,
                      to_version: str, what_changed: str) -> dict:
    """The communication a material correction owes its buyers (#42).

    Prepared, never sent: messaging customers is owner-gated and shadow mode refuses it. What
    this produces is the thing that would otherwise have to be written in a hurry, by
    somebody who does not have the version list.
    """
    if len(what_changed.split()) < 6:
        raise TrustRefused(
            "a correction notice says what was wrong and what it means for work in "
            "progress; anything shorter makes the buyer ask")
    return {
        "product_slug": product_slug,
        "from_versions": list(from_versions),
        "to_version": to_version,
        "affected_orders": [r["order_ref"] for r in affected],
        "affected_count": len(affected),
        "what_changed": what_changed.strip(),
        "subject": f"Corrected pattern: {product_slug} {to_version}",
        "body": (f"You bought {product_slug} at version "
                 f"{', '.join(sorted({r['purchased_version'] for r in affected})) or '—'}. "
                 f"{what_changed.strip()} Version {to_version} is attached and your original "
                 f"download has been updated. If you have already started, the change affects "
                 f"work from the point described above."),
        "sent": False,
        "why_not_sent": ("customer messaging is owner-gated and refused in shadow mode. This "
                         "is prepared so it does not have to be written in a hurry by "
                         "somebody who does not have the version list"),
    }
