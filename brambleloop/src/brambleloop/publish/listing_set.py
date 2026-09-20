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

    def __post_init__(self) -> None:
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
                "measurement_sources": list(self.measurement_sources)}


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
            "issued_at": self.issued_at.isoformat(),
            "measurement_sources": sorted({s for f in self.frames
                                           for s in f.measurement_sources}),
        }


def certify(*, slug: str, version: str, frames: list[CertifiedFrame],
            gate_results: dict, geometry: dict, claims: dict,
            policy_version: str, platform_policy: dict | None = None,
            disclosures: tuple[str, ...] = ()) -> ListingCertificate:
    """Issue a certificate, refusing one for a set that was not fully checked."""
    if not frames:
        raise ListingSetRefused(f"{slug}: a listing set with no frames is not a set")

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
        disclosures=tuple(disclosures))


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
        ],
        "note": ("validity is recomputed from the current inputs, never read from a flag. "
                 "The same mechanism as ops.artefacts for derived files and improve.upgrades "
                 "for promotion evidence -- all three ask whether a record still describes "
                 "the thing it was made from"),
    }
