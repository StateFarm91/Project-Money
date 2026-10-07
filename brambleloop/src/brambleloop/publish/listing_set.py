"""A certificate for the listing, and the thing that invalidates it without being told.

Requirement 70. A listing-set certificate tied to product and version, recording the exact
approved asset hashes, frame order, measurement sources, provenance, disclosures, QA results
and policy version. Any product revision that changes geometry or claims invalidates the
affected listing assets until they are re-certified.

`gates.certificate` certifies the *pattern*: that the document is what the compiler says it
is. This certifies the *listing*: that what a buyer will see was checked, by which gates,
against which geometry, under which policy. They are different objects because they go stale
for different reasons — a pattern stops being certified when its CIR changes, and a listing
stops being certified when the geometry a size card quotes changes underneath it, which can
happen while the pattern's own certificate stays perfectly valid.

The load-bearing sentence is the last one, and the word in it is *invalidates*.

**A certificate is invalidated by its inputs changing, not by somebody revoking it.** A
revocation step is a step somebody forgets, and the forgetting is silent: the listing goes on
carrying a certificate that was true about a version nobody sells any more. So the
certificate stores a fingerprint of the geometry and the claims it was issued against, and
`still_valid()` recomputes rather than looking up a flag. This is the same mechanism
`ops.artefacts` uses for derived files and `improve.upgrades` uses for promotion evidence,
which is not a coincidence: all three are the same question about whether a record still
describes the thing it was made from.

**It records what was checked, not that checking happened.** The gate results go in by name
with their outcomes, so a certificate issued while `COMMERCIAL_QA` never ran is refused
rather than granted with a quiet gap — `publish.eligibility` already holds that rule and this
reuses it instead of restating it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import eligibility


class ListingSetRefused(ValueError):
    """A certificate for a set whose gates did not all run, or whose inputs are unrecorded."""


DISCLOSED_RENDER = "disclosed_render"
# F-030 / F-254: a disclosed gallery frame (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING,
# ANGLE) drawn from the certified CIR and re-verified on its bytes
# (`visual.launch_imagery.check_supplement`). Held to the same disclosure rules as a
# disclosed render. Mirrors `visual.launch_imagery.SUPPLEMENT_KIND`.
DISCLOSED_SUPPLEMENT = "disclosed_gallery_frame"
# Mirrors `cir.model.SINGLE_VARIANT`: a product with no optional features has one variant.
SINGLE_VARIANT = "single"


def fingerprint(payload: dict) -> str:
    """A stable hash of whatever the certificate was issued against."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CertifiedFrame:
    """One approved frame: its hash, its place in the order, and what it is for."""

    position: int
    asset_id: str
    sha256: str
    job: str
    purpose: str
    medium: str
    honesty_label: str = ""
    measurement_sources: tuple[str, ...] = ()
    # D-FB-7: a disclosed deterministic render is certified as what it is, and its alt text --
    # which carries the disclosure -- is part of what was approved, so it travels with the
    # bytes to the upload rather than being re-derived there.
    kind: str = ""
    alt_text: str = ""
    # F-757: which configuration of the product this frame shows (`cir.model.variant_key`).
    # Empty means unrecorded, which only a legacy single-variant frame may be.
    represented_variant: str = ""

    def __post_init__(self) -> None:
        if self.kind in (DISCLOSED_RENDER, DISCLOSED_SUPPLEMENT):
            from .disclosed_listing import ALT_TEXT_MAX, DISCLOSURE, _phrase_in

            if not _phrase_in(self.alt_text):
                raise ListingSetRefused(
                    f"{self.asset_id}: a disclosed render is certified only with the "
                    f"disclosure in its alt text")
            if len(self.alt_text) > ALT_TEXT_MAX:
                raise ListingSetRefused(f"{self.asset_id}: alt text longer than Etsy allows")
            if self.honesty_label != DISCLOSURE:
                raise ListingSetRefused(
                    f"{self.asset_id}: a disclosed render carries the disclosure wording as "
                    f"its honesty label")
        if self.position < 1:
            raise ListingSetRefused(f"{self.asset_id}: frame positions start at 1")
        if len(self.sha256) < 16:
            raise ListingSetRefused(
                f"{self.asset_id}: a certificate records the exact asset hash, so that the "
                f"file it approved can be told from the one that is live")
        if self.job not in eligibility.JOBS:
            raise ListingSetRefused(f"{self.asset_id}: {self.job!r} is not a frame job")
        if self.purpose not in eligibility.PURPOSES:
            raise ListingSetRefused(f"{self.asset_id}: {self.purpose!r} is not a purpose")

    def to_dict(self) -> dict:
        return {"position": self.position, "asset_id": self.asset_id,
                "sha256": self.sha256, "job": self.job, "purpose": self.purpose,
                "medium": self.medium, "honesty_label": self.honesty_label,
                "measurement_sources": list(self.measurement_sources)} | (
                    {"kind": self.kind, "alt_text": self.alt_text} if self.kind else {}) | (
                    {"represented_variant": self.represented_variant}
                    if self.represented_variant else {})


@dataclass(frozen=True)
class ListingCertificate:
    """What a buyer will see, and everything it was checked against."""

    slug: str
    version: str
    frames: tuple[CertifiedFrame, ...]
    gate_results: dict               # gate -> outcome, from publish.eligibility
    geometry_fingerprint: str
    claims_fingerprint: str
    policy_version: str
    platform_policy: dict = field(default_factory=dict)
    disclosures: tuple[str, ...] = ()
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # F-757: the one configuration every frame in this set represents.
    represented_variant: str = SINGLE_VARIANT

    @property
    def frame_order(self) -> tuple[str, ...]:
        return tuple(f.asset_id for f in sorted(self.frames, key=lambda f: f.position))

    def to_dict(self) -> dict:
        return {
            "slug": self.slug, "version": self.version,
            "frames": [f.to_dict() for f in sorted(self.frames, key=lambda f: f.position)],
            "frame_order": list(self.frame_order),
            "gate_results": dict(self.gate_results),
            "geometry_fingerprint": self.geometry_fingerprint,
            "claims_fingerprint": self.claims_fingerprint,
            "policy_version": self.policy_version,
            "platform_policy": dict(self.platform_policy),
            "disclosures": list(self.disclosures),
            "represented_variant": self.represented_variant,
            "issued_at": self.issued_at.isoformat(),
            "measurement_sources": sorted({s for f in self.frames
                                           for s in f.measurement_sources}),
        }


def certify(*, slug: str, version: str, frames: list[CertifiedFrame],
            gate_results: dict, geometry: dict, claims: dict,
            policy_version: str, platform_policy: dict | None = None,
            disclosures: tuple[str, ...] = (),
            variant: str | None = None) -> ListingCertificate:
    """Issue a certificate, refusing one for a set that was not fully checked.

    `variant` is the configuration the listing claims (F-757). Every frame must represent
    exactly that configuration; a frame recording none is read as the single variant, which
    is what every frame drawn before configurations existed showed. With `variant` None the
    frames must agree among themselves and the certificate records what they agree on.
    """
    if not frames:
        raise ListingSetRefused(f"{slug}: a listing set with no frames is not a set")
    shown = {f.asset_id: (f.represented_variant or SINGLE_VARIANT) for f in frames}
    claimed = variant if variant is not None else (
        next(iter(shown.values())) if len(set(shown.values())) == 1 else None)
    if claimed is None:
        raise ListingSetRefused(
            f"{slug}: the frames show different configurations {sorted(set(shown.values()))} "
            f"and the listing does not say which it represents (F-757)")
    wrong = sorted(a for a, v in shown.items() if v != claimed)
    if wrong:
        raise ListingSetRefused(
            f"{slug}: frames {wrong} show a configuration other than the {claimed!r} the "
            f"listing claims; an image must state the configuration it shows (F-757)")

    unknown = sorted(set(gate_results) - set(eligibility.GATES))
    if unknown:
        raise ListingSetRefused(f"{slug}: {unknown} are not promotion gates")
    unrun = [g for g in eligibility.GATES
             if gate_results.get(g, eligibility.NOT_RUN) == eligibility.NOT_RUN]
    failed = [g for g in eligibility.GATES if gate_results.get(g) == eligibility.FAILED]
    if unrun or failed:
        raise ListingSetRefused(
            f"{slug}: cannot certify a listing set with "
            + (f"gates that never ran ({', '.join(unrun)})" if unrun else "")
            + ("; " if unrun and failed else "")
            + (f"failing gates ({', '.join(failed)})" if failed else "")
            + ". A certificate records what was checked, not that checking happened")

    positions = [f.position for f in frames]
    if len(set(positions)) != len(positions):
        raise ListingSetRefused(f"{slug}: two frames claim the same position")
    if not geometry:
        raise ListingSetRefused(
            f"{slug}: a certificate with no geometry recorded cannot be invalidated by the "
            f"geometry changing, which is the one thing it is for")

    return ListingCertificate(
        slug=slug, version=version, frames=tuple(frames),
        gate_results={g: gate_results.get(g, eligibility.NOT_RUN)
                      for g in eligibility.GATES},
        geometry_fingerprint=fingerprint(geometry),
        claims_fingerprint=fingerprint(claims or {}),
        policy_version=policy_version,
        platform_policy=dict(platform_policy or {}),
        disclosures=tuple(disclosures), represented_variant=claimed)


# ---- D-FB-7: the disclosed-render listing set -----------------------------------------------

_DISCLOSED_PURPOSE = {"hero": eligibility.CONVERSION_CREATIVE,
                      "scale": eligibility.CUSTOMER_INFORMATION,
                      "detail": eligibility.ENGINEERING_EVIDENCE}


def _ok(block) -> bool | None:
    return bool(block["ok"]) if isinstance(block, dict) and "ok" in block else None


def _outcome(*readings: bool | None) -> str:
    if any(r is False for r in readings):
        return eligibility.FAILED
    if any(r is None for r in readings) or not readings:
        return eligibility.NOT_RUN
    return eligibility.PASSED


def disclosed_gate_results(rec: dict, *, exported: bool, dimensions_ok: bool | None,
                           supplement_qa: dict | None = None) -> dict:
    """The four promotion gates, read off the disclosed set's own evidence.

    DATA_TRUTH         structural truth PASS on every frame, Asset Truth, and the listing's
                       dimensions consistent with the certified geometry
    LAYOUT_QA          layout QA over the ordered set and 340 px legibility of every frame
    COMMERCIAL_QA      the frame set (#65), the rendered mobile contexts (#66), the hero
                       thumbnail
    POLICY_PROVENANCE  `disclosed_listing.export_images` passed: the bytes are the frames on
                       record and the disclosure is in the pixels, the alt text and the copy
    """
    qa = rec.get("qa") or {}
    frames = rec.get("frames") or []
    truth = [((f.get("structural_truth") or {}).get("status") == "PASS") for f in frames]
    legible = [_ok(((qa.get("frames") or {}).get(f.get("view")) or {}).get("legibility_340"))
               for f in frames]
    # Supplement frames (F-030/F-254) add their own readings; they never replace the set's.
    # `supplement_qa` is {"verified": [bool per frame], "layout_qa": {"ok"}, "frame_set": {"ok"}}
    # measured over the whole ordered set including them.
    sq = supplement_qa or {}
    s_truth = [bool(v) for v in sq.get("verified") or []]
    s_layout = [_ok(sq.get("layout_qa"))] if supplement_qa else []
    s_set = [_ok(sq.get("frame_set"))] if supplement_qa else []
    return {
        eligibility.DATA_TRUTH: _outcome(*(truth or [None]), _ok(qa.get("asset_truth")),
                                         dimensions_ok, *s_truth),
        eligibility.LAYOUT_QA: _outcome(_ok(qa.get("layout_qa")), *(legible or [None]),
                                        *s_layout),
        eligibility.COMMERCIAL_QA: _outcome(_ok(qa.get("frame_set")), _ok(qa.get("mobile")),
                                            _ok(qa.get("hero_thumbnail")), *s_set),
        eligibility.POLICY_PROVENANCE: _outcome(bool(exported)),
    }


def disclosed_frames(rec: dict, images: list[tuple[str, bytes, str]], *,
                     slug: str) -> list[CertifiedFrame]:
    """One CertifiedFrame per disclosed frame, bound to the exact bytes the exporter released.

    `images` is `disclosed_listing.export_images`' output -- the only proof that each frame's
    disclosure is in its pixels, alt text and the copy and that its structural truth is PASS
    on these bytes. A frame the exporter did not release cannot be certified.
    """
    from ..gates.asset_truth import AssetClass
    from .disclosed_listing import DISCLOSURE

    ordered = sorted(rec.get("frames") or [], key=lambda f: int(f.get("position") or 0))
    if len(images) != len(ordered):
        raise ListingSetRefused(f"{slug}: the exporter released {len(images)} of "
                                f"{len(ordered)} disclosed frames")
    out = []
    for f, (_name, data, alt) in zip(ordered, images):
        sha = hashlib.sha256(data).hexdigest()
        if sha != (f.get("image") or {}).get("sha256"):
            raise ListingSetRefused(f"{slug}: frame {f.get('position')} bytes are not the "
                                    f"frame on record")
        if alt != f.get("alt_text"):
            raise ListingSetRefused(f"{slug}: frame {f.get('position')} alt text differs "
                                    f"from the one filed with it")
        manifest = f.get("disclosed_render") or {}
        job = manifest.get("job") or ""
        purpose = _DISCLOSED_PURPOSE.get(f.get("view") or "", "")
        dims = manifest.get("finished_dimensions_cm") or {}
        shown = (manifest.get("represented_variant") or {}).get("key") or SINGLE_VARIANT
        out.append(CertifiedFrame(
            position=int(f["position"]), asset_id=f"{slug}-disclosed-{f.get('view')}",
            sha256=sha, job=job, purpose=purpose,
            medium=AssetClass.DIGITAL_TWIN_RENDER.value, honesty_label=DISCLOSURE,
            measurement_sources=(("finished.width", "finished.length")
                                 if dims.get("width") and dims.get("height") else ()),
            kind=DISCLOSED_RENDER, alt_text=alt, represented_variant=shown))
    return out


def certify_disclosed(*, slug: str, version: str, rec: dict,
                      images: list[tuple[str, bytes, str]], geometry: dict, claims: dict,
                      policy_version: str, platform_policy: dict | None = None,
                      dimensions_ok: bool | None,
                      listing_variant: str | None = None,
                      supplements: list[CertifiedFrame] | tuple = (),
                      supplement_qa: dict | None = None) -> ListingCertificate:
    """Certify a disclosed-render listing set through the same `certify` every set goes through.

    Nothing is relaxed: the four gates must each have run and passed, the frames are bound by
    hash, and the certificate records the disclosure. The extra precondition is the
    exporter's: no frame enters a certificate unless `export_images` released it.
    """
    if rec.get("kind") != DISCLOSED_RENDER or rec.get("version") != version \
            or rec.get("slug") != slug:
        raise ListingSetRefused(f"{slug}@{version}: the record is not this release's disclosed set")
    if not rec.get("usable_as_listing_asset"):
        raise ListingSetRefused(f"{slug}: the disclosed set is launch-blocked: "
                                f"{(rec.get('launch_blocked') or [])[:3]}")
    # F-757 / PT-13: the configuration the LISTING declares -- the certified release's own
    # variant, supplied by the caller -- must be the one the set was rendered for. Taking it
    # from the record alone compared the record with itself.
    filed = rec.get("represented_variant") or SINGLE_VARIANT
    if listing_variant is not None and listing_variant != filed:
        raise ListingSetRefused(
            f"{slug}@{version}: the listing declares configuration {listing_variant!r} and the "
            f"disclosed set was rendered for {filed!r}; a listing may only show the "
            f"configuration it sells (F-757)")
    frames = disclosed_frames(rec, images, slug=slug)
    # F-030 / F-254: verified supplement frames follow the disclosed set, in order, each a
    # different job, each certified as a disclosed gallery frame with its readings recorded.
    supplements = list(supplements or ())
    if supplements:
        if supplement_qa is None or len(supplement_qa.get("verified") or []) != len(supplements):
            raise ListingSetRefused(f"{slug}: supplement frames offered without a verification "
                                    f"reading for each")
        expected = list(range(len(frames) + 1, len(frames) + 1 + len(supplements)))
        if sorted(f.position for f in supplements) != expected:
            raise ListingSetRefused(f"{slug}: supplement frames must follow the disclosed set "
                                    f"at positions {expected}")
        taken = {f.job for f in frames}
        for f in supplements:
            if f.kind != DISCLOSED_SUPPLEMENT or f.medium != frames[0].medium:
                raise ListingSetRefused(f"{f.asset_id}: only a disclosed gallery frame may "
                                        f"supplement a disclosed set")
            if f.job in taken:
                raise ListingSetRefused(f"{f.asset_id}: {f.job} is already done by another "
                                        f"frame; a second frame doing one job is the defect")
            taken.add(f.job)
        frames = frames + supplements
    shown = {f.represented_variant for f in frames}
    if listing_variant is not None and shown - {listing_variant}:
        raise ListingSetRefused(
            f"{slug}@{version}: frames show {sorted(shown)}, the listing declares "
            f"{listing_variant!r} (F-757)")
    from .disclosed_listing import DISCLOSURE

    return certify(slug=slug, version=version, frames=frames,
                   gate_results=disclosed_gate_results(rec, exported=True,
                                                       dimensions_ok=dimensions_ok,
                                                       supplement_qa=supplement_qa
                                                       if supplements else None),
                   geometry=geometry, claims=claims, policy_version=policy_version,
                   platform_policy=platform_policy, disclosures=(DISCLOSURE,),
                   variant=listing_variant if listing_variant is not None else filed)


VALID = "valid"
GEOMETRY_CHANGED = "geometry_changed"
CLAIMS_CHANGED = "claims_changed"
POLICY_CHANGED = "policy_changed"


def still_valid(certificate: ListingCertificate, *, geometry: dict, claims: dict,
                policy_version: str | None = None) -> dict:
    """Whether this certificate still describes the product, recomputed rather than looked up.

    A revocation step is a step somebody forgets, and the forgetting is silent: the listing
    goes on carrying a certificate that was true about a version nobody sells any more.
    """
    reasons = []
    now_geometry = fingerprint(geometry or {})
    now_claims = fingerprint(claims or {})
    if now_geometry != certificate.geometry_fingerprint:
        reasons.append(GEOMETRY_CHANGED)
    if now_claims != certificate.claims_fingerprint:
        reasons.append(CLAIMS_CHANGED)
    if policy_version is not None and policy_version != certificate.policy_version:
        reasons.append(POLICY_CHANGED)

    affected = sorted({f.asset_id for f in certificate.frames
                       if GEOMETRY_CHANGED in reasons and f.measurement_sources}
                      | ({f.asset_id for f in certificate.frames}
                         if (CLAIMS_CHANGED in reasons or POLICY_CHANGED in reasons)
                         else set()))
    return {
        "slug": certificate.slug, "version": certificate.version,
        "valid": not reasons, "invalidated_by": reasons,
        "affected_assets": affected,
        "why": ("the geometry, the claims and the policy are the ones this was issued "
                "against" if not reasons else
                f"invalidated by {', '.join(reasons)}: "
                + ("every frame quoting a measurement is affected"
                   if reasons == [GEOMETRY_CHANGED] else
                   "the whole set is affected, because a claim or policy change is not "
                   "confined to the frames that show numbers")),
        "recomputed": ("compared against the current inputs rather than read from a flag. A "
                       "revocation step is a step somebody forgets, and the forgetting is "
                       "silent"),
    }


def state() -> dict:
    """What the listing certificate holds, and why it is not the release certificate."""
    return {
        "requirement": 70,
        "records": ["asset hashes", "frame order", "measurement sources", "provenance",
                    "disclosures", "QA results", "policy version"],
        "distinct_from": (
            "gates.certificate certifies the pattern -- that the document is what the "
            "compiler says. This certifies the listing -- that what a buyer sees was checked, "
            "against which geometry, under which policy. A listing can go stale while the "
            "pattern's certificate stays perfectly valid, which is the case that needs two "
            "objects"),
        "invalidated_by": [GEOMETRY_CHANGED, CLAIMS_CHANGED, POLICY_CHANGED],
        "refuses": [
            "a certificate for a set with a gate that never ran",
            "a certificate for a set with a failing gate",
            "a certificate with no geometry recorded, which could never be invalidated",
            "two frames claiming one position",
            "a frame with no recorded asset hash",
            "a frame showing a configuration other than the one the listing claims (F-757)",
        ],
        "note": ("validity is recomputed from the current inputs, never read from a flag. "
                 "The same mechanism as ops.artefacts for derived files and improve.upgrades "
                 "for promotion evidence -- all three ask whether a record still describes "
                 "the thing it was made from"),
    }
