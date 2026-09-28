"""Machine-readable licence terms for every benchmark source (F-786, F-787, F-788).

The quarantine in `library.py` stops the wrong *role* reading a purchased pattern. It could not
say what the purchase *permits*, because nothing recorded it: the Mini Star Stitch Cardigan's
terms -- personal use; its photographs, images and text may not be used to sell finished items
-- lived only in a paragraph of research/VISUAL_BENCH2.md, where no agent deciding whether it
may use something would ever look. This module is where those terms live as data, so the
boundary is checked rather than remembered.

**Three rights, never one.** A purchase can permit selling what you make from it and still
forbid selling, adapting or redistributing the instructions (F-788). `finished_item_rights` and
`pattern_rights` are separate fields, and the use vocabulary below has no entry that grants
both at once.

**Free to view is not free to publish (F-787).** A creator's blog post or video carries a
licence record too, with `pattern_rights` "none": public material may inform general
research and is never a source for publishable output.

**Unstated terms read conservatively.** A purchase whose terms nobody has recorded gets the
personal-use reading: every private research use (which v0.23 encourages, F-789/F-797) and no
publishing use. An unknown licence is never a permissive one.
"""
from __future__ import annotations

from dataclasses import dataclass

# Uses a benchmark source can be put to. Private research is what the teardown laboratory is
# for (Final Build supersession S1: full private reverse-engineering is allowed).
PRIVATE_RESEARCH_USES: tuple[str, ...] = (
    "private_analysis", "functional_reconstruction", "demand_research",
    "merchandising_research", "similarity_review",
)
# General-technique research: what a public tutorial may inform (F-787).
PUBLIC_RESEARCH_USES: tuple[str, ...] = (
    "demand_research", "merchandising_research", "general_technique_research",
    "similarity_review",
)
# Anything that puts the source's expression, or a light derivative of it, in front of a buyer.
PUBLISHING_USES: tuple[str, ...] = (
    "republish_pattern", "adapt_pattern_for_sale", "instruction_drafting", "listing_copy",
    "listing_image", "generation_reference", "marketing_quote",
)
USES: tuple[str, ...] = tuple(dict.fromkeys(
    PRIVATE_RESEARCH_USES + PUBLIC_RESEARCH_USES + PUBLISHING_USES))

SOURCE_KINDS: tuple[str, ...] = ("purchased", "public_web", "public_video", "owner_supplied")
FINISHED_ITEM_RIGHTS: tuple[str, ...] = ("permitted", "permitted_with_attribution",
                                         "not_permitted", "unstated", "unknown")
PATTERN_RIGHTS: tuple[str, ...] = ("none", "personal_use", "licensed_commercial")

CAPTURE_ACTION = "benchmark.licence_recorded"
REFUSED_ACTION = "benchmark.licence_refused"


class LicenceRefused(PermissionError):
    """A use of a benchmark source its licence does not grant."""


@dataclass(frozen=True)
class Licence:
    source_ref: str
    source_kind: str
    terms_source: str
    allowed_uses: tuple[str, ...]
    prohibited_uses: tuple[str, ...]
    attribution: str = ""
    finished_item_rights: str = "unknown"
    pattern_rights: str = "personal_use"
    source_url: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"source_kind {self.source_kind!r} is not one of {SOURCE_KINDS}")
        if self.finished_item_rights not in FINISHED_ITEM_RIGHTS:
            raise ValueError(f"finished_item_rights {self.finished_item_rights!r} is not one "
                             f"of {FINISHED_ITEM_RIGHTS}")
        if self.pattern_rights not in PATTERN_RIGHTS:
            raise ValueError(f"pattern_rights {self.pattern_rights!r} is not one of "
                             f"{PATTERN_RIGHTS}")
        unknown = set(self.allowed_uses) | set(self.prohibited_uses)
        unknown -= set(USES)
        if unknown:
            raise ValueError(f"uses outside the vocabulary: {sorted(unknown)}")
        both = set(self.allowed_uses) & set(self.prohibited_uses)
        if both:
            raise ValueError(f"uses both allowed and prohibited: {sorted(both)}")
        # F-787: a public source never grants a publishing use, whatever was typed.
        if self.source_kind in ("public_web", "public_video"):
            granted = set(self.allowed_uses) & set(PUBLISHING_USES)
            if granted or self.pattern_rights != "none":
                raise ValueError(
                    f"{self.source_ref}: a public source carries pattern_rights 'none' and no "
                    f"publishing use (F-787); got {sorted(granted)} / {self.pattern_rights}")

    def permits(self, use: str) -> tuple[bool, str]:
        if use not in USES:
            return False, f"{use!r} is not a recognised use of a benchmark source"
        if use in self.prohibited_uses:
            return False, (f"{self.source_ref}'s licence prohibits {use!r} "
                           f"(terms: {self.terms_source})")
        if use not in self.allowed_uses:
            return False, (f"{self.source_ref}'s licence does not grant {use!r}; granted: "
                           f"{list(self.allowed_uses)}")
        return True, "granted"

    def to_dict(self) -> dict:
        return {"source_ref": self.source_ref, "source_kind": self.source_kind,
                "terms_source": self.terms_source, "allowed_uses": list(self.allowed_uses),
                "prohibited_uses": list(self.prohibited_uses), "attribution": self.attribution,
                "finished_item_rights": self.finished_item_rights,
                "pattern_rights": self.pattern_rights, "source_url": self.source_url,
                "notes": self.notes}


def conservative(source_ref: str, *, source_kind: str = "purchased", source_url: str = "",
                 attribution: str = "") -> Licence:
    """The reading applied when nobody has recorded the terms. Never permissive."""
    public = source_kind in ("public_web", "public_video")
    return Licence(
        source_ref=source_ref, source_kind=source_kind,
        terms_source=("unstated: public material, general research only (F-787)" if public
                      else "unstated: conservative personal-use reading of a purchase"),
        allowed_uses=PUBLIC_RESEARCH_USES if public else PRIVATE_RESEARCH_USES,
        prohibited_uses=PUBLISHING_USES,
        attribution=attribution, finished_item_rights="unknown",
        pattern_rights="none" if public else "personal_use", source_url=source_url)


# Terms already read from the purchased benchmarks, as data. Benchmark 2's are the pattern's
# own licence note (research/VISUAL_BENCH2.md section 1, read from the PDF). Benchmark 1's were
# never recorded, so it carries the conservative reading and says so.
KNOWN_LICENCES: dict[str, Licence] = {
    "benchmark-2-mini-star-stitch-cardigan": Licence(
        source_ref="benchmark-2-mini-star-stitch-cardigan", source_kind="purchased",
        terms_source=("pattern PDF licence note (cover, p2, p14), recorded in "
                      "research/VISUAL_BENCH2.md s1"),
        allowed_uses=PRIVATE_RESEARCH_USES, prohibited_uses=PUBLISHING_USES,
        attribution="MJ's Off The Hook Designs Inc. (designer); no attribution terms stated",
        finished_item_rights="unstated", pattern_rights="personal_use",
        notes=("personal-use licence; the pattern's photographs, images and text may not be "
               "used to sell finished items, so they are evidence here and never assets")),
    "benchmark-1-side-to-side-cardigan": conservative("benchmark-1-side-to-side-cardigan"),
}


def _from_row(r) -> Licence:
    return Licence(source_ref=r.source_ref, source_kind=r.source_kind,
                   terms_source=r.terms_source or "",
                   allowed_uses=tuple(r.allowed_uses or ()),
                   prohibited_uses=tuple(r.prohibited_uses or ()),
                   attribution=r.attribution or "",
                   finished_item_rights=r.finished_item_rights or "unknown",
                   pattern_rights=r.pattern_rights or "none",
                   source_url=r.source_url or "", notes=r.notes or "")


def record(db, lic: Licence, *, recorded_by: str = "orchestrator",
           overwrite: bool = True) -> dict:
    """Write one licence record. `overwrite=False` keeps terms somebody already recorded."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import BenchmarkLicence

    with db.session() as s:
        row = s.scalar(select(BenchmarkLicence).where(
            BenchmarkLicence.source_ref == lic.source_ref))
        if row is not None and not overwrite:
            return {"source_ref": lic.source_ref, "written": False, **_from_row(row).to_dict()}
        if row is None:
            row = BenchmarkLicence(source_ref=lic.source_ref)
            s.add(row)
        row.source_kind = lic.source_kind
        row.source_url = lic.source_url
        row.terms_source = lic.terms_source
        row.allowed_uses = list(lic.allowed_uses)
        row.prohibited_uses = list(lic.prohibited_uses)
        row.attribution = lic.attribution
        row.finished_item_rights = lic.finished_item_rights
        row.pattern_rights = lic.pattern_rights
        row.notes = lic.notes
        row.recorded_by = recorded_by
        row.recorded_at = datetime.now(timezone.utc)
    return {"source_ref": lic.source_ref, "written": True, **lic.to_dict()}


def capture_purchase(db, ref: str, *, terms: dict | None = None, source_url: str = "",
                     attribution: str = "", recorded_by: str = "orchestrator") -> dict:
    """At intake: the purchase's licence, from terms supplied or the conservative reading.

    Supplied terms are validated against the vocabulary; a terms dict that grants a use not in
    it is refused rather than stored.
    """
    if terms:
        lic = Licence(source_ref=ref, source_kind="purchased",
                      terms_source=str(terms.get("terms_source") or "owner-supplied at intake"),
                      allowed_uses=tuple(terms.get("allowed_uses") or PRIVATE_RESEARCH_USES),
                      prohibited_uses=tuple(terms.get("prohibited_uses") or PUBLISHING_USES),
                      attribution=str(terms.get("attribution") or attribution),
                      finished_item_rights=str(terms.get("finished_item_rights") or "unknown"),
                      pattern_rights=str(terms.get("pattern_rights") or "personal_use"),
                      source_url=source_url, notes=str(terms.get("notes") or ""))
        return record(db, lic, recorded_by=recorded_by)
    # Never downgrade terms somebody recorded by hand to the default on a re-upload.
    return record(db, conservative(ref, source_url=source_url, attribution=attribution),
                  recorded_by=recorded_by, overwrite=False)


def register_public_source(db, ref: str, *, url: str, kind: str = "public_web",
                           attribution: str = "", notes: str = "",
                           recorded_by: str = "orchestrator") -> dict:
    """A public tutorial or free pattern: research only, never a publishable source (F-787)."""
    lic = Licence(source_ref=ref, source_kind=kind,
                  terms_source="public material: viewing does not license republication",
                  allowed_uses=PUBLIC_RESEARCH_USES, prohibited_uses=PUBLISHING_USES,
                  attribution=attribution, finished_item_rights="unknown",
                  pattern_rights="none", source_url=url, notes=notes)
    return record(db, lic, recorded_by=recorded_by)


def seed_known(db) -> list[str]:
    """Write the code-declared licences that are not in the database yet."""
    return [ref for ref, lic in KNOWN_LICENCES.items()
            if record(db, lic, recorded_by="code", overwrite=False)["written"]]


def licence_for(db, ref: str) -> Licence:
    """The recorded licence, else the code-declared one, else the conservative reading."""
    if db is not None:
        from sqlalchemy import select

        from ..core.models import BenchmarkLicence

        with db.session() as s:
            row = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == ref))
            if row is not None:
                return _from_row(row)
    return KNOWN_LICENCES.get(ref) or conservative(ref)


def refuse_unless_permitted(db, ref: str, use: str) -> Licence:
    lic = licence_for(db, ref)
    ok, why = lic.permits(use)
    if not ok:
        raise LicenceRefused(why)
    return lic


def ref_of(relative_path: str) -> str:
    """The purchase a library path belongs to: its first component (`mjs-<listing>/...`)."""
    parts = [p for p in str(relative_path).replace("\\", "/").split("/") if p not in ("", ".")]
    return parts[0] if parts else ""
