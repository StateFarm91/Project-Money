"""Every derived artefact tied to the evidence that made it, and a sentinel that checks.

Requirements 171 and 173. The chain already fingerprints the things it was burned by -- a
design's own hash, the release hash, the chain version -- and those fixed the specific
deliveries that went wrong. What did not exist is the general statement: *every* derived
artefact recorded against *immutable fingerprints of its upstream evidence*, so a design
change invalidates the twin, the geometry proof, the reverse-compiler result, the
certificate, the PDF, the chart, the visual-truth package, the listing copy, the SEO, the
pricing assumptions, the support knowledge, the marketing assets and the release bundle,
rather than invalidating the ones somebody remembered to wire up.

The requirement's own sentence names the failure exactly: *a stable slug must never make
stale output appear current*. A slug is the most stable thing in the system and the most
misleading, because everything downstream keys on it and nothing downstream is re-derived by
it changing -- it does not change. The PDF at `hex-coaster.pdf` is the PDF at
`hex-coaster.pdf` whether or not the design under it was rebuilt last night.

So two rules, and the second is the one that does the work.

**A recorded input that no longer matches its upstream is stale.** Ordinary, and the easy
half.

**An artefact with no recorded provenance at all is stale, not fresh.** This is the same
shape this build keeps finding: an artefact nobody fingerprinted has no mismatch to report,
so a sweep that only compares recorded rows reports a clean estate and leaves every
un-instrumented file exactly as it found it -- current-looking, because nothing said
otherwise. Freshness has to be proved, and the proof is a row.

The sentinel (#173) sweeps production against current fingerprints, raises an incident per
stale artefact and asks for a rebuild. Its block is not a claim: the incident carries
`halts_publication` against the product's own slug, which is the flag `runtime.pipeline`
already consults before it publishes anything, and the test asserts the publish path
actually refuses rather than asserting a row exists.

A mismatch and an absence are graded differently on purpose, and the line is the requirement's
own: it says *any mismatch* creates an incident and blocks. A mismatch is a proven defect --
this artefact was built from something that has since changed -- and it blocks. An unproven
artefact is a known backlog: nothing is established about it either way, and blocking on it
the first time this sentinel runs would halt an entire catalogue over instrumentation that
was never fitted. So unproven is raised as a non-blocking incident, counted every sweep, and
never called fresh. `block_unproven` exists for the day the backlog is closed, and
`graduation()` says when that is -- which is the SHADOW -> STAGING rule applied to this
capability rather than a delay dressed up as one.

Both of the requirement's test conditions are exercised: a deliberate stale-data injection,
where an upstream fingerprint is moved under an artefact that was fresh a moment earlier;
and a restart, where the provenance is read back through a new session because a record that
does not survive a container replacement is a record of nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Every derived artefact class the requirement names. Closed, because an artefact class
# nobody named is one the sweep will never look at, which is how an estate is clean and
# wrong at the same time.
ARTEFACT_CLASSES: dict[str, str] = {
    "twin": "the digital twin's measurement of the design",
    "geometry_proof": "what the shape is proved to be",
    "reverse_result": "the independent reverse compiler's reading",
    "certificate": "the release certificate",
    "pdf": "the pattern document a buyer receives",
    "chart": "the stitch chart",
    "visual_truth": "the asset-truth package for the imagery",
    "listing_copy": "the words on the listing",
    "seo": "the tags and phrases the listing reaches for",
    "pricing": "the price and the assumptions under it",
    "support_knowledge": "what support answers about this product",
    "marketing_asset": "a pin, an article, an email or a teaser",
    "release_bundle": "everything shipped together as one release",
}

# What an artefact can be derived *from*. Also closed: an upstream nobody named is an
# upstream nobody watches.
UPSTREAM_KINDS: dict[str, str] = {
    "cir": "the design itself, by its own content hash",
    "release": "what was certified, by release hash",
    "chain": "the version of the code that produced it",
    "policy": "the marketplace policy snapshot it was checked against",
    "asset": "an image or a rendering it was built from",
    "price_observation": "the observed prices the pricing rested on",
}

_REF = re.compile(r"^(?P<kind>[a-z_]+):(?P<name>[A-Za-z0-9._-]+)$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{8,64}$")

FRESH = "fresh"
STALE = "stale"
UNPROVEN = "unproven"          # no provenance row at all, which is not the same as fresh

SENTINEL_SIGNATURE = "stale-artefact"


class ProvenanceRefused(ValueError):
    """An artefact class nobody named, an upstream nobody named, or a derivation with none."""


def fingerprint(payload) -> str:
    """A content hash of anything canonically serialisable."""
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _check_ref(ref: str) -> None:
    match = _REF.match(ref)
    if match is None:
        raise ProvenanceRefused(
            f"{ref!r} is not an upstream reference. The form is 'kind:name', because a bare "
            f"name cannot be looked up against anything")
    if match.group("kind") not in UPSTREAM_KINDS:
        raise ProvenanceRefused(
            f"{match.group('kind')!r} is not an upstream kind: {sorted(UPSTREAM_KINDS)}. An "
            f"upstream nobody named is an upstream nobody watches")


@dataclass(frozen=True)
class Verdict:
    """One artefact's standing against its upstreams."""

    artefact_class: str
    artefact_key: str
    product_slug: str
    state: str
    moved: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    why: str = ""

    def to_dict(self) -> dict:
        return {"artefact_class": self.artefact_class, "artefact_key": self.artefact_key,
                "product_slug": self.product_slug, "state": self.state,
                "moved": list(self.moved), "unknown": list(self.unknown), "why": self.why}


def record(db, *, artefact_class: str, artefact_key: str, product_slug: str,
           inputs: dict[str, str], chain_version: str = "") -> dict:
    """Tie one derived artefact to the fingerprints of everything it was made from."""
    from ..core.models import ArtefactProvenance

    if artefact_class not in ARTEFACT_CLASSES:
        raise ProvenanceRefused(
            f"{artefact_class!r} is not an artefact class: {sorted(ARTEFACT_CLASSES)}")
    if not inputs:
        raise ProvenanceRefused(
            "a derived artefact with no inputs is not derived, it is a file. Recording it "
            "with an empty upstream would make it permanently fresh, which is the state "
            "this module exists to make unavailable")
    for ref, value in inputs.items():
        _check_ref(ref)
        if not _FINGERPRINT.match(str(value)):
            raise ProvenanceRefused(
                f"{ref} carries {value!r}, which is not a fingerprint. A human-readable "
                f"version string compares equal to itself forever, which is exactly how a "
                f"rebuilt design keeps its old artefacts")

    from sqlalchemy import select

    row = db.scalar(select(ArtefactProvenance)
                    .where(ArtefactProvenance.artefact_class == artefact_class)
                    .where(ArtefactProvenance.artefact_key == artefact_key))
    if row is None:
        row = ArtefactProvenance(artefact_class=artefact_class, artefact_key=artefact_key,
                                 product_slug=product_slug)
        db.add(row)
    row.product_slug = product_slug
    row.inputs = dict(inputs)
    row.chain_version = chain_version
    row.built_at = datetime.now(timezone.utc)
    db.flush()
    return {"artefact_class": artefact_class, "artefact_key": artefact_key,
            "product_slug": product_slug, "inputs": dict(inputs)}


def check(db, *, current: dict[str, str],
          expected: list[tuple[str, str, str]] | None = None) -> list[Verdict]:
    """Every artefact's standing: fresh, stale, or never proved fresh at all.

    `current` maps each upstream reference to the fingerprint it holds *now*. `expected`
    lists artefacts known to exist downstream as (class, key, slug); anything in it without a
    provenance row comes back `unproven`, because an artefact nobody fingerprinted has no
    mismatch to report and a sweep that only compares rows would call the estate clean.
    """
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    for ref in current:
        _check_ref(ref)

    verdicts: list[Verdict] = []
    seen: set[tuple[str, str]] = set()
    for row in db.scalars(select(ArtefactProvenance)):
        seen.add((row.artefact_class, row.artefact_key))
        moved, unknown = [], []
        for ref, recorded in (row.inputs or {}).items():
            now = current.get(ref)
            if now is None:
                unknown.append(ref)
            elif now != recorded:
                moved.append(ref)
        if moved or unknown:
            why = []
            if moved:
                why.append(f"{moved} changed since this was built")
            if unknown:
                why.append(f"{unknown} has no current fingerprint, so freshness cannot be "
                           f"proved and an unprovable artefact is not a fresh one")
            verdicts.append(Verdict(row.artefact_class, row.artefact_key, row.product_slug,
                                    STALE, tuple(moved), tuple(unknown), "; ".join(why)))
        else:
            verdicts.append(Verdict(row.artefact_class, row.artefact_key, row.product_slug,
                                    FRESH, why="every upstream matches"))

    for artefact_class, artefact_key, slug in (expected or []):
        if artefact_class not in ARTEFACT_CLASSES:
            raise ProvenanceRefused(f"{artefact_class!r} is not an artefact class")
        if (artefact_class, artefact_key) in seen:
            continue
        verdicts.append(Verdict(
            artefact_class, artefact_key, slug, UNPROVEN,
            why=("nothing records what this was made from, so it has no mismatch to report "
                 "and would pass any sweep that only compares recorded rows. A stable slug "
                 "must never make stale output appear current")))
    return verdicts


def sweep(db, *, current: dict[str, str],
          expected: list[tuple[str, str, str]] | None = None,
          block_unproven: bool = False) -> dict:
    """The permanent sentinel: raise an incident per stale artefact and block its product.

    The block is the existing one rather than a new one. `halts_publication` against the
    product's slug is the flag the publish path already consults, so a stale artefact stops
    a publication by the same mechanism a quality incident does -- and a test asserts the
    publish path refuses, rather than asserting that a row was written.
    """
    from sqlalchemy import select

    from ..core.models import Incident

    verdicts = check(db, current=current, expected=expected)
    bad = [v for v in verdicts if v.state != FRESH]

    blocked: set[str] = set()
    raised: list[dict] = []
    for verdict in bad:
        if not verdict.product_slug:
            continue
        blocking = verdict.state == STALE or block_unproven
        if verdict.state == UNPROVEN and not block_unproven:
            # Deliberately not one incident each. The first sweep of an un-instrumented
            # estate would raise one row per artefact -- hundreds of them -- and an alarm
            # that arrives in hundreds is an alarm nobody reads, which is the same as no
            # alarm and costs more. The backlog is one incident carrying its own size,
            # below; a mismatch keeps its own row because each is a distinct defect.
            continue
        signature = f"{SENTINEL_SIGNATURE}:{verdict.artefact_class}:{verdict.artefact_key}"
        existing = db.scalar(select(Incident)
                             .where(Incident.signature == signature)
                             .where(Incident.resolved.is_(False)))
        if existing is None:
            db.add(Incident(
                signature=signature, product_slug=verdict.product_slug,
                severity="P1" if blocking else "P3", halts_publication=blocking,
                summary=(f"{verdict.artefact_class} {verdict.artefact_key} is "
                         f"{verdict.state}: {verdict.why}")[:500],
                detail=dict(verdict.to_dict(), blocking=blocking)))
            raised.append(dict(verdict.to_dict(), blocking=blocking))
        if blocking:
            blocked.add(verdict.product_slug)

    unproven = [v for v in verdicts if v.state == UNPROVEN]
    backlog_signature = f"{SENTINEL_SIGNATURE}:backlog"
    backlog_row = db.scalar(select(Incident)
                            .where(Incident.signature == backlog_signature)
                            .where(Incident.resolved.is_(False)))
    if unproven and not block_unproven:
        summary = (f"{len(unproven)} derived artefact(s) carry no provenance row, so their "
                   f"freshness cannot be proved. Not stale -- unproven, which is the "
                   f"instrumentation backlog rather than a defect")
        if backlog_row is None:
            db.add(Incident(signature=backlog_signature, product_slug=None, severity="P3",
                            halts_publication=False, summary=summary,
                            detail={"unproven": len(unproven),
                                    "classes": sorted({v.artefact_class
                                                       for v in unproven})}))
            raised.append({"state": UNPROVEN, "count": len(unproven), "blocking": False})
        else:
            backlog_row.summary = summary
            backlog_row.report_count = len(unproven)
            backlog_row.detail = {"unproven": len(unproven),
                                  "classes": sorted({v.artefact_class for v in unproven})}
    elif backlog_row is not None and not unproven:
        backlog_row.resolved = True
        backlog_row.detail = dict(backlog_row.detail or {},
                                  resolution="every artefact that exists carries a row")

    # A stale artefact whose upstreams have since come back into line is resolved here, so
    # the sweep can clear a block it raised. A sentinel that can only ever add incidents
    # stops the company permanently the first time anything is rebuilt.
    fresh_signatures = {f"{SENTINEL_SIGNATURE}:{v.artefact_class}:{v.artefact_key}"
                        for v in verdicts if v.state == FRESH}
    cleared = []
    for row in db.scalars(select(Incident)
                          .where(Incident.signature.like(f"{SENTINEL_SIGNATURE}:%"))
                          .where(Incident.resolved.is_(False))):
        if row.signature in fresh_signatures:
            row.resolved = True
            detail = dict(row.detail or {})
            detail["resolution"] = "the upstreams match again; the artefact was rebuilt"
            row.detail = detail
            cleared.append(row.signature)
    db.flush()

    return {
        "checked": len(verdicts),
        "fresh": sum(1 for v in verdicts if v.state == FRESH),
        "stale": sum(1 for v in verdicts if v.state == STALE),
        "unproven": sum(1 for v in verdicts if v.state == UNPROVEN),
        "incidents_raised": raised,
        "incidents_cleared": cleared,
        "publication_blocked": sorted(blocked),
        "rebuild": sorted({v.product_slug for v in bad if v.state == STALE
                           and v.product_slug}),
        "instrument": sorted({(v.artefact_class, v.artefact_key) for v in verdicts
                              if v.state == UNPROVEN}),
        "enforcing_unproven": block_unproven,
        "verdicts": [v.to_dict() for v in verdicts],
        "note": ("an artefact with no provenance is unproven rather than fresh, because it "
                 "has no mismatch to report and would pass any sweep that only compares "
                 "recorded rows. A mismatch blocks; an absence is a backlog, counted every "
                 "sweep and never called fresh"),
    }


def graduation(db, *, current: dict[str, str],
               expected: list[tuple[str, str, str]] | None = None) -> dict:
    """Whether this sentinel may start blocking on absence as well as on mismatch.

    The SHADOW -> STAGING rule applied to this capability. Enforcement on absence is correct
    once every artefact that exists has a provenance row, and catastrophic before then: the
    first sweep would halt the whole catalogue over instrumentation nobody had fitted. The
    condition is a count rather than a judgement, so it can be checked rather than argued.
    """
    verdicts = check(db, current=current, expected=expected)
    unproven = [v for v in verdicts if v.state == UNPROVEN]
    return {
        "may_enforce_unproven": not unproven,
        "unproven": len(unproven),
        "of": len(verdicts),
        "instrument": sorted({(v.artefact_class, v.artefact_key) for v in unproven}),
        "why": ("every artefact that exists carries a provenance row, so an absent row now "
                "means something is wrong rather than something is unfitted"
                if not unproven else
                f"{len(unproven)} artefact(s) have no provenance row. Blocking on absence "
                f"today would halt the catalogue over instrumentation that was never "
                f"fitted, which is a different problem from a stale artefact"),
    }


def current_from_db(db) -> dict[str, str]:
    """The fingerprints the system holds right now, for the references it can answer for."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product
    from ..runtime.release import CHAIN_VERSION

    current: dict[str, str] = {"chain:release": fingerprint(CHAIN_VERSION)}
    for product in db.scalars(select(Product)):
        latest = None
        for version in db.scalars(select(PatternVersion)
                                  .where(PatternVersion.product_id == product.id)):
            if latest is None or version.id > latest.id:
                latest = version
        if latest is None:
            continue
        current[f"cir:{product.slug}"] = fingerprint(latest.cir_json)
        if latest.release_hash:
            current[f"release:{product.slug}"] = latest.release_hash[:16]
    return current


def expected_from_db(db) -> list[tuple[str, str, str]]:
    """The derived artefacts that actually exist downstream, for the sweep to account for.

    This is the half that makes "unproven" mean anything. Without it the sentinel can only
    check the rows somebody remembered to write, which is a sweep of the instrumented
    estate rather than of the estate.
    """
    from sqlalchemy import select

    from ..core.models import (ContentPiece, Listing, ListingAsset, PatternVersion, Product)

    slugs = {p.id: p.slug for p in db.scalars(select(Product))}
    out: list[tuple[str, str, str]] = []
    for version in db.scalars(select(PatternVersion).where(
            PatternVersion.certified.is_(True))):
        slug = slugs.get(version.product_id, "")
        out.append(("certificate", f"{slug}@{version.version}", slug))
    for listing in db.scalars(select(Listing)):
        key = f"{listing.product_slug}@{listing.version}"
        out.append(("listing_copy", key, listing.product_slug))
        out.append(("seo", key, listing.product_slug))
    for asset in db.scalars(select(ListingAsset)):
        out.append(("visual_truth", f"{asset.product_slug}@{asset.version}#{asset.id}",
                    asset.product_slug))
    for piece in db.scalars(select(ContentPiece)):
        out.append(("marketing_asset", f"content#{piece.id}", piece.product_slug))
    return out


def state() -> dict:
    """What is watched, what counts as proof, and what absence means here."""
    return {
        "artefact_classes": dict(ARTEFACT_CLASSES),
        "upstream_kinds": dict(UPSTREAM_KINDS),
        "states": [FRESH, STALE, UNPROVEN],
        "note": ("A stable slug must never make stale output appear current, so freshness "
                 "is proved rather than assumed: an artefact with no provenance row is "
                 "unproven, not fresh. The sentinel's block is the existing "
                 "halts_publication flag the publish path already consults, so it stops a "
                 "publication rather than reporting that it would (#171, #173)."),
    }
