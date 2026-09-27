"""What a competitor would have to copy, and how long each one would take them.

Requirement 44. The recurring fictional model is one brand asset and it is the most copyable
one in the list — a competitor with an image generator has an equivalent by Friday. Treating
it as the brand is the mistake this requirement names, and it is an easy mistake because the
model is the most *visible* asset, which feels like the same thing as the most valuable.

So the moat is an inventory, and every entry carries the only number that matters: how long a
determined competitor would need to reproduce it. That reframes the whole list. A photography
style is weeks. A naming architecture is an afternoon. A support experience answered from the
exact pattern version somebody bought requires building the version map first, and the version
map cannot be backfilled — so it is years, or never, depending on when they start.

Two rules keep the inventory honest.

**An asset nobody has built is not a moat.** A planned signature is a plan, and listing it
alongside real ones produces a page that says the company is defensible when it is aspiring.
Every entry states whether it exists today.

**Replication time is measured in what it would cost *them*, not what it cost us.** Those
differ wildly and only one of them is a moat: an expensive thing that is easy to copy is a
sunk cost, and a cheap thing that is hard to copy is the whole game.
"""
from __future__ import annotations

from dataclasses import dataclass

# Roughly how long a determined competitor needs. The bands are coarse on purpose: the
# difference between four and six weeks is noise, and the difference between weeks and never
# is the entire strategy.
DAYS = "days"
WEEKS = "weeks"
MONTHS = "months"
STRUCTURAL = "structural"     # needs a decision made early, or data accumulated since then

REPLICATION: tuple[str, ...] = (DAYS, WEEKS, MONTHS, STRUCTURAL)

REPLICATION_MEANING: dict[str, str] = {
    DAYS: "a competent competitor has an equivalent this week",
    WEEKS: "requires sustained effort and a person who cares",
    MONTHS: "requires a programme, and they would have to decide to start",
    STRUCTURAL: ("cannot be bought later at any speed: it needed a decision taken early or "
                 "data accumulated since then"),
}


class MoatRefused(ValueError):
    """An asset counted as a moat that does not exist, or has no replication estimate."""


@dataclass(frozen=True)
class Signature:
    key: str
    what: str
    replication: str
    why: str
    exists: bool

    def __post_init__(self) -> None:
        if self.replication not in REPLICATION:
            raise MoatRefused(
                f"{self.key}: {self.replication!r} is not a replication band: {REPLICATION}")
        if len(self.why.split()) < 6:
            raise MoatRefused(
                f"{self.key}: say why it would take that long for somebody else. Without "
                f"that the band is a feeling about how proud we are of it")

    def to_dict(self) -> dict:
        return {"key": self.key, "what": self.what, "exists": self.exists,
                "replication": self.replication,
                "replication_meaning": REPLICATION_MEANING[self.replication],
                "why": self.why}


SIGNATURES: tuple[Signature, ...] = (
    Signature("canonical_model", "a recurring fictional model across the gallery", DAYS,
              "any competitor with an image generator has an equivalent by Friday, which is "
              "why this is one asset and not the brand", exists=False),
    Signature("naming_architecture", "how products and collections are named", DAYS,
              "a naming scheme is an afternoon's work to imitate once it is visible",
              exists=True),
    Signature("editorial_layout", "the document's typography, hierarchy and rhythm", WEEKS,
              "copying a layout is easy and copying the judgement that produced it is not, "
              "so an imitation reads as an imitation", exists=True),
    Signature("photography_language", "how finished objects are lit, styled and cropped",
              WEEKS,
              "a style is learnable from the gallery, and doing it consistently across a "
              "growing catalogue is the part that takes a person who cares", exists=False),
    Signature("chart_style", "colour-independent charts with a per-yarn letter in every cell",
              MONTHS,
              "the style is visible and reproducing it means rebuilding chart generation "
              "around accessibility rather than adding it afterwards", exists=True),
    Signature("tutorial_voice", "how a difficult step is explained", MONTHS,
              "a voice is the accumulation of decisions about what to leave out, and a "
              "competitor starts from zero on every one of them", exists=False),
    Signature("collection_families", "products that mean more beside their siblings", MONTHS,
              "requires a catalogue designed as families rather than a catalogue with "
              "families found in it afterwards", exists=False),
    Signature("deterministic_validation",
              "every count, repeat and dimension machine-checked and reverse-compiled",
              STRUCTURAL,
              "a competitor would have to rebuild their pattern production around a formal "
              "representation, which is a different company rather than a feature",
              exists=True),
    Signature("version_aware_support",
              "answers given from the exact pattern version the customer bought", STRUCTURAL,
              "needs an order-to-version map written at sale time, and it cannot be "
              "backfilled: whoever did not record it has lost those orders permanently",
              exists=True),
    Signature("measured_yardage",
              "yardage computed from the twin and calibrated against physical samples",
              STRUCTURAL,
              "the calibration is accumulated evidence, so a competitor starting today is "
              "as many samples behind as we have taken", exists=False),
)

BY_KEY: dict[str, Signature] = {s.key: s for s in SIGNATURES}


# How each signature's existence is proved from what the running system produced (C-69,
# #44). The hand-set `exists` flags above are the plan; with a database the inventory reads
# evidence instead, and a signature with nothing to show for it is planned whatever the plan
# says.
EVIDENCE_FOR: dict[str, str] = {
    "canonical_model": "the canonical_model gate is open (an owner-approved identity)",
    "naming_architecture": "certified products listed under their own titles",
    "editorial_layout": "a customer PDF recorded as passed",
    "photography_language": "a product photograph that cleared its floors",
    "chart_style": "a chart recorded as passed with the colour cue present",
    "tutorial_voice": "nothing measures a voice yet; UNMEASURED is not built",
    "collection_families": "a collection assembled from certified members",
    "deterministic_validation": "a certificate whose chain ran compile and reverse",
    "version_aware_support": "a version-keyed support knowledge pack recorded as passed",
    "measured_yardage": "a completed physical test that passed",
}
# A product-first listing is recognisable without the model when it carries at least this
# many built non-model signatures of its own.
RECOGNISABLE_MIN = 3


def evidence(db) -> dict:
    """Per signature: exists (from rows), and per listed product: which signatures it shows."""
    from sqlalchemy import select

    from ..core.models import (ArtefactProvenance, AuditLog, Collection, Listing,
                               PatternVersion, PhysicalTest, Product)

    with db.session() as s:
        # Bounded (C-80 defect 17): only the classes the signatures read, not every row daily.
        prov = [(r.artefact_class, r.product_slug, r.validation_status)
                for r in s.scalars(select(ArtefactProvenance).where(
                    ArtefactProvenance.artefact_class.in_(
                        ("pdf", "chart", "support_knowledge"))))]
        listings = sorted({l.product_slug for l in s.scalars(
            select(Listing).where(Listing.state != "withdrawn"))})
        certs = {p.slug: dict(pv.certificate or {}) for pv, p in s.execute(
            select(PatternVersion, Product).join(Product, Product.id == PatternVersion.product_id)
            .where(PatternVersion.certified.is_(True)))}
        photos = {str((r.detail or {}).get("slug") or r.artifact or "")
                  for r in s.scalars(select(AuditLog).where(
                      AuditLog.action == "assets.owned_photography"))
                  if (r.detail or {}).get("made")}
        collections = s.scalar(select(Collection).limit(1)) is not None
        physical = any(t.passed for t in s.scalars(select(PhysicalTest)))
    try:
        from ..build2 import executor

        model_open = bool(executor.GATE_BY_KEY["canonical_model"].open(db))
    except Exception:  # noqa: BLE001 - an unreadable gate is closed
        model_open = False

    def passed(cls, slug=None):
        return any(c == cls and v == "passed" and (slug is None or sl == slug)
                   for c, sl, v in prov)

    def validated(slug):
        stages = set((certs.get(slug) or {}).get("stages_run") or [])
        return {"compile", "reverse"} <= stages

    exists = {
        "canonical_model": model_open,
        "naming_architecture": bool(listings),
        "editorial_layout": passed("pdf"),
        "photography_language": bool(photos),
        "chart_style": passed("chart"),
        "tutorial_voice": False,
        "collection_families": collections,
        "deterministic_validation": any(validated(sl) for sl in certs),
        "version_aware_support": passed("support_knowledge"),
        "measured_yardage": physical,
    }
    per_listing = {}
    for slug in listings:
        shown = [k for k, ok in (
            ("naming_architecture", True), ("editorial_layout", passed("pdf", slug)),
            ("chart_style", passed("chart", slug)),
            ("deterministic_validation", validated(slug)),
            ("version_aware_support", passed("support_knowledge", slug)),
            ("photography_language", slug in photos)) if ok]
        per_listing[slug] = {"signatures": shown,
                             "recognisable_without_model": len(shown) >= RECOGNISABLE_MIN}
    return {"exists": exists, "per_listing": per_listing}


def inventory(db=None) -> dict:
    """The moat as it actually stands, separating what exists from what is planned.

    An asset nobody has built is not a moat, and listing it beside the real ones produces a
    page saying the company is defensible when it is aspiring. With a database, existence is
    read from evidence (`evidence`), and recognisability on product-first listings -- the
    requirement's own test -- is measured per listing.
    """
    measured = evidence(db) if db is not None else None
    signatures = (tuple(Signature(s.key, s.what, s.replication, s.why,
                                  exists=bool(measured["exists"].get(s.key)))
                        for s in SIGNATURES) if measured else SIGNATURES)
    built = [s for s in signatures if s.exists]
    planned = [s for s in signatures if not s.exists]

    by_band: dict[str, list[str]] = {}
    for s in built:
        by_band.setdefault(s.replication, []).append(s.key)

    structural = [s.key for s in built if s.replication == STRUCTURAL]
    recognisable = None
    if measured is not None:
        rows = measured["per_listing"]
        recognisable = {"listings": len(rows),
                        "recognisable": sorted(k for k, v in rows.items()
                                               if v["recognisable_without_model"]),
                        "not_recognisable": sorted(k for k, v in rows.items()
                                                   if not v["recognisable_without_model"]),
                        "min_signatures": RECOGNISABLE_MIN, "per_listing": rows}
    return {
        "measured_from_evidence": measured is not None,
        "evidence_rules": EVIDENCE_FOR,
        "recognisable_without_model": recognisable,
        "signatures": [s.to_dict() for s in signatures],
        "built": [s.key for s in built],
        "planned": [s.key for s in planned],
        "built_by_replication": {band: by_band.get(band, []) for band in REPLICATION},
        "structural_advantages": structural,
        "model_is_one_asset_of": len(SIGNATURES),
        "note": (f"{len(structural)} structural advantage(s) exist today and the canonical "
                 f"model is not among them -- it is the most visible asset, which feels like "
                 f"the most valuable and is the most copyable (#44)."),
    }


def without(key: str) -> dict:
    """What the brand still has if one signature is lost or copied.

    Asked of the model specifically, because the requirement's whole point is that the answer
    should not be "not much".
    """
    if key not in BY_KEY:
        raise MoatRefused(f"{key!r} is not a brand signature: {sorted(BY_KEY)}")
    remaining = [s for s in SIGNATURES if s.key != key and s.exists]
    structural = [s.key for s in remaining if s.replication == STRUCTURAL]
    return {
        "lost": key,
        "remaining_built": [s.key for s in remaining],
        "remaining_structural": structural,
        "brand_survives": bool(structural),
        "note": (f"losing {key} leaves {len(structural)} structural advantage(s) intact"
                 if structural else
                 f"losing {key} leaves nothing a competitor could not reproduce in weeks"),
    }
