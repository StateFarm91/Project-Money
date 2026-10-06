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
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from ..core.build import UNKNOWN as UNKNOWN_COMMIT
from ..core.build import commit as build_commit

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
# F-115 / F-167 (wave-3 K7): an un-instrumented artefact describing a release the product has
# since been re-engineered past (or a retired legacy-duplicate slug) is not a backlog item to
# fingerprint later: it is legacy output of a superseded design, invalidated and retired. Its
# state stays `unproven` (it is still never fresh) and the verdict carries `retired` = why; it
# leaves the instrumentation backlog and the coverage denominator, and is listed apart.
INVALIDATED = "invalidated"


def retired(v) -> bool:
    return v.state == UNPROVEN and bool(getattr(v, "retired", ""))
_VERSIONED_KEY = re.compile(r"^(?P<slug>[^@:#]+)@(?P<version>[^#]+)")
GRADUATION_ACTION = "provenance.class_graduated"

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


# --- lineage: who made it, under what authority, and how that is known --------------------------
#
# `inputs` says what an artefact was made *from*. Lineage says who made it: the job, the
# agent, the code commit, the model and provider if one was called, what it cost, the hash of
# the file, the artefacts it was built on top of, whether it passed its own validation, and
# under which publication authority. The 2026-09-26 audit of production found 275 derived
# artefacts and 275 without a row: only the video planner ever called `record`, and every
# chain handler wrote its listing, frame, certificate and content piece with nothing attached.
# The fix is not a reminder to call `record`. It is a write path that refuses to store a
# derived artefact without its lineage, and a worker that checks after every job.

SOURCES = ("recorded", "backfilled")

# Classes whose artefact is a file the customer or shopper receives. A row for one of these
# without the file's hash cannot answer "is the file we are about to ship the one that was
# built", which is the question the artifact store exists to answer.
FILE_CLASSES = frozenset({"pdf", "chart", "visual_truth"})

REQUIRED_LINEAGE = ("created_by", "code_commit", "validation_status",
                    "publication_authority", "source")

_PARENT = re.compile(r"^(?P<cls>[a-z_]+):(?P<key>.+)$")


@dataclass
class Lineage:
    """Who made a derived artefact, under what authority, and how that is known.

    `code_commit` defaults to the running build's commit, which is `unknown` when the
    platform did not say -- reported as such rather than invented, for the same reason
    `core.build` does. `source` is `recorded` for a row written by the build that made the
    artefact and `backfilled` for one derived later from evidence already on file; a
    backfilled row must carry that evidence, because a lineage nobody can check is a claim.
    """

    created_by: str
    job_id: int | None = None
    code_commit: str = field(default_factory=build_commit)
    model: str = ""
    provider: str = ""
    cost_cad: float | None = None
    sha256: str = ""
    parents: tuple[str, ...] = ()
    validation_status: str = "unknown"
    publication_authority: str = "shadow"
    source: str = "recorded"
    evidence: dict = field(default_factory=dict)

    def for_file(self, sha256: str) -> "Lineage":
        """The same lineage, for the file whose hash this is."""
        return replace(self, sha256=sha256)

    def under(self, *parents: str) -> "Lineage":
        """The same lineage, built on top of these artefacts (as 'class:key')."""
        return replace(self, parents=tuple(self.parents) + tuple(parents))

    def validated(self, status: str) -> "Lineage":
        return replace(self, validation_status=status)

    def to_dict(self) -> dict:
        return {"created_by": self.created_by, "job_id": self.job_id,
                "code_commit": self.code_commit, "model": self.model,
                "provider": self.provider, "cost_cad": self.cost_cad, "sha256": self.sha256,
                "parents": list(self.parents), "validation_status": self.validation_status,
                "publication_authority": self.publication_authority, "source": self.source,
                "evidence": dict(self.evidence)}


def _check_lineage(artefact_class: str, lineage) -> None:
    if lineage is None:
        raise ProvenanceRefused(
            f"a {artefact_class} was about to be stored with no lineage. A derived artefact "
            f"that cannot say which job, commit and authority made it is exactly the row the "
            f"production audit found 275 of, so the write path refuses it rather than "
            f"remembering to add one later")
    if not isinstance(lineage, Lineage):
        # Certification C-28: a dict, a string or any other stand-in is not a lineage, and
        # reading attributes off it with defaults would let `{}` through as "complete".
        raise ProvenanceRefused(
            f"a {artefact_class} lineage must be a Lineage; got {type(lineage).__name__} "
            f"{str(lineage)[:40]!r}. A shape that merely resembles one is refused")
    missing = [name for name in REQUIRED_LINEAGE if not str(getattr(lineage, name, "") or "")]
    if missing:
        raise ProvenanceRefused(
            f"{artefact_class} lineage is missing {missing}. An empty field here is not a "
            f"default, it is an unanswered question about who made this")
    if lineage.source not in SOURCES:
        raise ProvenanceRefused(
            f"{lineage.source!r} is not a lineage source: {list(SOURCES)}. A row is either "
            f"recorded by the build that made the artefact or backfilled from evidence")
    if lineage.source == "recorded" and lineage.job_id is None:
        raise ProvenanceRefused(
            f"{artefact_class} lineage says it was recorded at build time but names no job. "
            f"Every build in this system runs as a job, so a recorded row without one was "
            f"not recorded by the build that made the artefact")
    if lineage.source == "backfilled":
        evidence = dict(lineage.evidence or {})
        if not evidence.get("matched_on") or (
                evidence.get("job_id") is None and evidence.get("audit_id") is None):
            raise ProvenanceRefused(
                f"a backfilled {artefact_class} must cite the evidence it was derived from: "
                f"the job or audit row it was matched to and what matched. Without that it "
                f"is a manufactured lineage, and the artefact stays unproven instead")
    if artefact_class in FILE_CLASSES and not re.match(r"^[0-9a-f]{64}$", lineage.sha256 or ""):
        raise ProvenanceRefused(
            f"a {artefact_class} is a file the customer receives, so its lineage must carry "
            f"the file's sha256; got {lineage.sha256!r}")
    for parent in lineage.parents or ():
        match = _PARENT.match(parent)
        if match is None or match.group("cls") not in ARTEFACT_CLASSES:
            raise ProvenanceRefused(
                f"{parent!r} is not a parent artefact. The form is 'class:key' with a class "
                f"this module watches, so the rebuild graph can follow it")


def record_lineage(db, *, artefact_class: str, artefact_key: str, product_slug: str,
                   inputs: dict[str, str], lineage: Lineage,
                   chain_version: str = "") -> dict:
    """Record a derived artefact with its upstream fingerprints *and* its lineage.

    Fail-closed: a class this module watches is refused when any required lineage field is
    missing. `record` remains the low-level writer for the inputs half; nothing in the release
    chain should call it directly any more.
    """
    from ..core.models import ArtefactProvenance

    if artefact_class not in ARTEFACT_CLASSES:
        raise ProvenanceRefused(
            f"{artefact_class!r} is not an artefact class: {sorted(ARTEFACT_CLASSES)}")
    _check_lineage(artefact_class, lineage)

    from sqlalchemy import select

    prior = db.scalar(select(ArtefactProvenance)
                      .where(ArtefactProvenance.artefact_class == artefact_class)
                      .where(ArtefactProvenance.artefact_key == artefact_key))
    if prior is not None and lineage.source == "backfilled" and _is_recorded(prior):
        # Certification C-30: the build's own lineage outranks anything inferred later. The
        # backfill skips existing keys; this is the boundary that makes sure of it.
        raise ProvenanceRefused(
            f"{artefact_class} {artefact_key} already carries the lineage recorded by job "
            f"{prior.job_id} ({prior.created_by}). A backfilled row is inferred from evidence "
            f"and may fill an absence, never replace a recorded derivation")
    previous = _snapshot(prior) if prior is not None else None

    out = _write_inputs(db, artefact_class=artefact_class, artefact_key=artefact_key,
                        product_slug=product_slug, inputs=inputs,
                        chain_version=chain_version)
    row = db.scalar(select(ArtefactProvenance)
                    .where(ArtefactProvenance.artefact_class == artefact_class)
                    .where(ArtefactProvenance.artefact_key == artefact_key))
    row.created_by = lineage.created_by[:64]
    row.job_id = lineage.job_id
    row.code_commit = (lineage.code_commit or UNKNOWN_COMMIT)[:40]
    row.model = (lineage.model or "")[:80]
    row.provider = (lineage.provider or "")[:40]
    row.cost_cad = lineage.cost_cad
    row.sha256 = lineage.sha256 or ""
    row.parents = list(lineage.parents)
    row.validation_status = lineage.validation_status[:20]
    row.publication_authority = lineage.publication_authority[:20]
    row.source = lineage.source
    row.evidence = dict(lineage.evidence or {})
    db.flush()
    _audit_replacement(db, artefact_class, artefact_key, previous, _snapshot(row),
                       writer=lineage.created_by)
    out["lineage"] = lineage.to_dict()
    return out


OVERWRITTEN_ACTION = "provenance.overwritten"

# The fields whose change means the row now tells a different story about the artefact.
_SNAPSHOT_FIELDS = ("inputs", "chain_version", "created_by", "job_id", "code_commit", "model",
                    "provider", "cost_cad", "sha256", "parents", "validation_status",
                    "publication_authority", "source", "evidence")


def _is_recorded(row) -> bool:
    """A row the build that made the artefact wrote, with its lineage complete."""
    return bool(row is not None and (row.created_by or "").strip()
                and row.source == "recorded" and row.job_id is not None)


def _snapshot(row) -> dict:
    out = {name: getattr(row, name, None) for name in _SNAPSHOT_FIELDS}
    out["inputs"] = dict(out["inputs"] or {})
    out["parents"] = list(out["parents"] or [])
    out["evidence"] = dict(out["evidence"] or {})
    out["built_at"] = row.built_at.isoformat() if getattr(row, "built_at", None) else None
    return out


def _audit_replacement(db, artefact_class: str, artefact_key: str, previous: dict | None,
                       now: dict, *, writer: str) -> None:
    """Certification C-29: a row is one-per-artefact, so a rewrite keeps its history here.

    The provenance table holds the current derivation; the audit log (append-only) holds
    every derivation it replaced, verbatim, so the first lineage is never unrecoverable.
    Rewriting an identical row (a retried job recording the same facts) is not a change.
    """
    if previous is None:
        return
    changed = sorted(k for k in _SNAPSHOT_FIELDS if previous.get(k) != now.get(k))
    if not changed:
        return
    from ..core.models import AuditLog

    db.add(AuditLog(
        actor=(writer or "unattributed")[:64], action=OVERWRITTEN_ACTION,
        artifact=f"{artefact_class}:{artefact_key}"[:200],
        detail={"artefact_class": artefact_class, "artefact_key": artefact_key,
                "changed": changed, "previous": previous,
                "replacement": {k: now.get(k) for k in changed},
                "why": ("one row per artefact holds the current derivation; the one it "
                        "replaced is kept here so it is never lost without trace")}))
    db.flush()


# --- keys: one spelling per artefact, shared by the write path, the sweep and the backfill -----
#
# The sweep decides "unproven" by set difference between the artefacts that exist and the rows
# that were written, so a write path and an enumerator that spell the same artefact two ways
# produce a permanently unproven estate with every row present. These are the only spellings.

def release_key(slug: str, version: str) -> str:
    """certificate, listing_copy, seo and pricing are keyed by the release they describe."""
    return f"{slug}@{version}"


def pdf_key(slug: str, version: str, terminology: str) -> str:
    return f"{slug}@{version}#pdf-{terminology.lower()}"


def chart_key(slug: str, version: str, which: str = "chart") -> str:
    return f"{slug}@{version}#{which}"


def visual_key(slug: str, version: str, asset_id: int) -> str:
    return f"{slug}@{version}#{asset_id}"


def marketing_key(slug: str, channel: str, title: str) -> str:
    """Keyed by content rather than by row id, so a re-drafted piece with the same title is
    the same artefact and a row id that differs between databases is not."""
    digest = hashlib.sha256((title or "").encode()).hexdigest()[:16]
    return f"{slug}:{channel}:{digest}"


def chain_fingerprint(chain_version: str | None = None) -> str:
    """The fingerprint `current_from_db` publishes for `chain:release`."""
    if chain_version is None:
        from ..runtime.release import CHAIN_VERSION
        chain_version = CHAIN_VERSION
    return fingerprint(chain_version)


def design_inputs(db, slug: str, version: str, *, chain: bool = True) -> dict[str, str]:
    """The upstream fingerprints for anything derived from one certified release.

    Fingerprinted from the stored `cir_json` rather than from a CIR object in hand, because
    `current_from_db` fingerprints the stored JSON and `CIR.fingerprint` is a different,
    shorter hash of a different serialisation. Two spellings of the same design would make
    every artefact read stale the moment it was built.
    """
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    product = db.scalar(select(Product).where(Product.slug == slug))
    pv = db.scalar(select(PatternVersion).where(
        PatternVersion.product_id == product.id,
        PatternVersion.version == version)) if product is not None else None
    if pv is None:
        raise ProvenanceRefused(
            f"{slug}@{version} has no stored release, so nothing derived from it can name "
            f"what it was derived from")
    out = {f"cir:{slug}": fingerprint(pv.cir_json)}
    if pv.release_hash:
        out[f"release:{slug}"] = pv.release_hash[:16]
    if chain:
        out["chain:release"] = chain_fingerprint()
    return out


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
    retired: str = ""

    def to_dict(self) -> dict:
        return {"artefact_class": self.artefact_class, "artefact_key": self.artefact_key,
                "product_slug": self.product_slug, "state": self.state,
                "moved": list(self.moved), "unknown": list(self.unknown), "why": self.why,
                **({"retired": self.retired, "invalidated": True} if self.retired else {})}


def record(db, *, artefact_class: str, artefact_key: str, product_slug: str,
           inputs: dict[str, str], chain_version: str = "") -> dict:
    """Tie one derived artefact to the fingerprints of everything it was made from.

    The inputs half only, with no lineage. Certification C-27: a row written here says what
    the artefact was made from but not who made it, so it must not be able to pass for a
    lineage-complete row. Rewriting a row that did carry lineage therefore strips it (the
    lineage no longer describes these inputs) and audits the replacement; the worker's
    backstop then reads the row as incomplete rather than instrumented.
    """
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    prior = db.scalar(select(ArtefactProvenance)
                      .where(ArtefactProvenance.artefact_class == artefact_class)
                      .where(ArtefactProvenance.artefact_key == artefact_key)
                      ) if artefact_class in ARTEFACT_CLASSES else None
    previous = _snapshot(prior) if prior is not None else None
    out = _write_inputs(db, artefact_class=artefact_class, artefact_key=artefact_key,
                        product_slug=product_slug, inputs=inputs,
                        chain_version=chain_version)
    row = db.scalar(select(ArtefactProvenance)
                    .where(ArtefactProvenance.artefact_class == artefact_class)
                    .where(ArtefactProvenance.artefact_key == artefact_key))
    if previous is not None and (previous["created_by"] or "").strip() and (
            previous["inputs"] != dict(inputs) or previous["chain_version"] != chain_version):
        row.created_by = ""
        row.job_id = None
        db.flush()
    _audit_replacement(db, artefact_class, artefact_key, previous, _snapshot(row),
                       writer="")
    return out


def _write_inputs(db, *, artefact_class: str, artefact_key: str, product_slug: str,
                  inputs: dict[str, str], chain_version: str = "") -> dict:
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

    superseded = _superseded_lookup(db) if expected else (lambda *_: None)
    for artefact_class, artefact_key, slug in (expected or []):
        if artefact_class not in ARTEFACT_CLASSES:
            raise ProvenanceRefused(f"{artefact_class!r} is not an artefact class")
        if (artefact_class, artefact_key) in seen:
            continue
        why_retired = superseded(artefact_key, slug)
        if why_retired:
            verdicts.append(Verdict(artefact_class, artefact_key, slug, UNPROVEN,
                                    why=why_retired, retired=why_retired))
            continue
        verdicts.append(Verdict(
            artefact_class, artefact_key, slug, UNPROVEN,
            why=("nothing records what this was made from, so it has no mismatch to report "
                 "and would pass any sweep that only compares recorded rows. A stable slug "
                 "must never make stale output appear current")))
    return verdicts


def _superseded_lookup(db):
    """A function (key, slug) -> reason when an unproven artefact is legacy of a superseded
    design (F-115), else None. Latest version = the product's newest PatternVersion row."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    latest: dict[str, str] = {}
    newest_id: dict[str, int] = {}
    for slug, vid, version in db.execute(
            select(Product.slug, PatternVersion.id, PatternVersion.version)
            .join(PatternVersion, PatternVersion.product_id == Product.id)):
        if vid > newest_id.get(slug, -1):
            newest_id[slug], latest[slug] = vid, version
    try:
        from ..products.launch0 import LEGACY_DUPLICATES
        retired = set(LEGACY_DUPLICATES)
    except Exception:  # noqa: BLE001 - without the list, nothing is retired by slug
        retired = set()

    def why(key: str, slug: str) -> str | None:
        if slug in retired:
            return (f"{slug} is a retired legacy-duplicate concept slug; its un-instrumented "
                    f"output is invalidated and retired, never served as current")
        m = _VERSIONED_KEY.match(key or "")
        if m is None or slug not in latest:
            return None
        if m.group("version") != latest[slug] and m.group("version") != "collection":
            return (f"{slug} was re-engineered to {latest[slug]} after this "
                    f"{m.group('version')} artefact was made, and nothing proves what it was "
                    f"made from: legacy output of a superseded design is invalidated")
        return None
    return why


def coverage(verdicts: list[Verdict]) -> dict:
    """F-161: provenance coverage numerator/denominator per class. Absence is unproven.

    numerator = artefacts carrying a provenance row (fresh or stale); denominator = every
    current artefact (rows + unproven). Invalidated legacy artefacts are retired and counted
    apart. A class with no artefacts is UNMEASURED, never 100% or 0%.
    """
    out: dict[str, dict] = {}
    for cls in ARTEFACT_CLASSES:
        vs = [v for v in verdicts if v.artefact_class == cls]
        rowed = sum(1 for v in vs if v.state in (FRESH, STALE))
        denom = rowed + sum(1 for v in vs if v.state == UNPROVEN and not retired(v))
        out[cls] = {"numerator": rowed, "denominator": denom,
                    "ratio": round(rowed / denom, 4) if denom else "UNMEASURED",
                    "invalidated": sum(1 for v in vs if retired(v))}
    num = sum(c["numerator"] for c in out.values())
    den = sum(c["denominator"] for c in out.values())
    return {"by_class": out, "numerator": num, "denominator": den,
            "ratio": round(num / den, 4) if den else "UNMEASURED",
            "rule": "rows / (rows + unproven); absence is unproven, never fresh"}


def graduated_classes(db) -> dict[str, dict]:
    """F-162: classes whose graduation was declared, from the audit trail (append-only)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    for row in db.scalars(select(AuditLog).where(AuditLog.action == GRADUATION_ACTION)
                          .order_by(AuditLog.id)):
        cls = (row.artifact or "").split(":", 1)[-1]
        if cls in ARTEFACT_CLASSES:
            out[cls] = {"declared_at": _aware(row.at).isoformat() if row.at else None,
                        "by": row.actor, "evidence": row.detail or {}}
    return out


def declare_graduations(db, *, current: dict[str, str], expected, actor: str = "ops.sentinel",
                        verdicts: list[Verdict] | None = None) -> list[str]:
    """Declare graduation for every class whose backlog is closed: at least one artefact,
    none unproven. Declared once; from then on an absent row in that class blocks release."""
    from ..core.models import AuditLog

    verdicts = verdicts if verdicts is not None else check(db, current=current,
                                                            expected=expected)
    cov = coverage(verdicts)["by_class"]
    already = graduated_classes(db)
    declared = []
    for cls, c in cov.items():
        if cls in already or not c["denominator"] or c["numerator"] != c["denominator"]:
            continue
        db.add(AuditLog(actor=actor, action=GRADUATION_ACTION,
                        artifact=f"artefact_class:{cls}",
                        detail={"numerator": c["numerator"], "denominator": c["denominator"],
                                "rule": "no artefact of this class is unproven; absence now "
                                        "blocks release for this class"}))
        declared.append(cls)
    if declared:
        db.flush()
    return declared


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
    bad = [v for v in verdicts if v.state in (STALE, UNPROVEN) and not retired(v)]
    # F-162: in a class whose graduation was declared, absence is release-blocking.
    graduated = set(graduated_classes(db))

    blocked: set[str] = set()
    raised: list[dict] = []
    for verdict in bad:
        if not verdict.product_slug:
            continue
        enforce = block_unproven or verdict.artefact_class in graduated
        blocking = verdict.state == STALE or enforce
        if verdict.state == UNPROVEN and not enforce:
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

    unproven = [v for v in verdicts if v.state == UNPROVEN and not retired(v)
                and v.artefact_class not in graduated]
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
        "graduated_classes": sorted(graduated),
        "invalidated": sum(1 for v in verdicts if retired(v)),
        "retired": sorted({(v.artefact_class, v.artefact_key) for v in verdicts
                           if retired(v)}),
        "coverage": coverage(verdicts),
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
    unproven = [v for v in verdicts if v.state == UNPROVEN and not retired(v)]
    cov = coverage(verdicts)
    declared = graduated_classes(db)
    return {
        # F-161 / F-162: coverage per class, and the per-class graduation state.
        "coverage": cov,
        "classes": {cls: {"declared": cls in declared,
                          "declared_at": (declared.get(cls) or {}).get("declared_at"),
                          "may_graduate": bool(c["denominator"])
                          and c["numerator"] == c["denominator"],
                          "absence_blocks": cls in declared}
                    for cls, c in cov["by_class"].items()},
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


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _after(value, since) -> bool:
    if since is None:
        return True
    value = _aware(value)
    return value is not None and value >= _aware(since)


def expected_from_db(db, *, since=None) -> list[tuple[str, str, str]]:
    """The derived artefacts that actually exist downstream, for the sweep to account for.

    This is the half that makes "unproven" mean anything. Without it the sentinel can only
    check the rows somebody remembered to write, which is a sweep of the instrumented
    estate rather than of the estate.

    The 275 the production audit counted (marketing_asset 134, visual_truth 94, listing_copy
    16, seo 16, certificate 15) was a *lower bound*: this enumerated only the tables it knew
    about. The PDF and the charts exist as hashes in the outputs of every completed
    `assets.build` job, and a price exists on every listing that carries one, and none of
    them was counted -- so they could not be unproven, which is the same failure one level
    up. They are enumerated now. `since` narrows to rows created at or after a moment,
    which is how the worker checks the rows one job just wrote.
    """
    from sqlalchemy import select

    from ..core.models import (ContentPiece, Job, JobStatus, Listing, ListingAsset,
                               PatternVersion, Product)

    slugs = {p.id: p.slug for p in db.scalars(select(Product))}
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(cls: str, key: str, slug: str) -> None:
        if (cls, key) not in seen:
            seen.add((cls, key))
            out.append((cls, key, slug))

    for version in db.scalars(select(PatternVersion).where(
            PatternVersion.certified.is_(True))):
        if not _after(version.created_at, since):
            continue
        slug = slugs.get(version.product_id, "")
        add("certificate", release_key(slug, version.version), slug)
    for listing in db.scalars(select(Listing)):
        if not _after(listing.created_at, since):
            continue
        key = release_key(listing.product_slug, listing.version)
        add("listing_copy", key, listing.product_slug)
        add("seo", key, listing.product_slug)
        if (listing.price_cad or 0) > 0:
            add("pricing", key, listing.product_slug)
    for asset in db.scalars(select(ListingAsset)):
        if not _after(asset.created_at, since):
            continue
        add("visual_truth", visual_key(asset.product_slug, asset.version, asset.id),
            asset.product_slug)
    for piece in db.scalars(select(ContentPiece)):
        if not _after(piece.created_at, since):
            continue
        add("marketing_asset", marketing_key(piece.product_slug, piece.channel, piece.title),
            piece.product_slug)
    for job in db.scalars(select(Job).where(Job.job_type == "assets.build",
                                            Job.status == JobStatus.DONE)):
        if not _after(job.finished_at, since):
            continue
        outputs = job.outputs or {}
        slug, version = outputs.get("slug"), outputs.get("version")
        if not slug or not version:
            continue
        for terminology, sha in (outputs.get("pdf_sha256_by_terminology")
                                 or ({"US": outputs["pdf_sha256"]}
                                     if outputs.get("pdf_sha256") else {})).items():
            if sha:
                add("pdf", pdf_key(slug, version, terminology), slug)
        for which in ("chart", "legend"):
            if outputs.get(f"{which}_sha256"):
                add("chart", chart_key(slug, version, which), slug)
    return out


def assert_instrumented(db, *, since, job_id: int | None = None) -> dict:
    """The rows created since `since` that no provenance row accounts for.

    The worker's backstop. The write path records lineage as it writes, and this is the check
    that it did: a handler that created a listing, a frame, a certificate or a content piece
    during this job and left it without a row is named here, after the handler and before the
    job is marked done. It reports; the worker decides whether reporting is enough.
    """
    expected = expected_from_db(db, since=since)
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    rows = {(r.artefact_class, r.artefact_key): r
            for r in db.scalars(select(ArtefactProvenance))}
    missing: list[tuple[str, str, str]] = []
    incomplete: list[dict] = []
    for cls, key, slug in expected:
        row = rows.get((cls, key))
        if row is None:
            missing.append((cls, key, slug))
            continue
        # Certification C-27: a row existing is not a row instrumented. An artefact created
        # during this job is accounted for only by a row this job recorded with its lineage:
        # a creator, `source == recorded`, and `job_id` naming this job. A bare `record()`
        # row (no creator, no job) or a row left by some other job does not qualify.
        gaps = lineage_gaps(row, job_id=job_id)
        if gaps:
            missing.append((cls, key, slug))
            incomplete.append({"artefact_class": cls, "artefact_key": key, "gaps": gaps})
    return {"job_id": job_id, "since": _aware(since).isoformat() if since else None,
            "checked": len(expected), "missing": missing, "incomplete": incomplete}


def lineage_gaps(row, *, job_id: int | None = None) -> list[str]:
    """What a provenance row lacks to count as recorded by the job that made it."""
    gaps: list[str] = []
    if not (row.created_by or "").strip():
        gaps.append("created_by")
    if row.source != "recorded":
        gaps.append(f"source={row.source!r}")
    if row.job_id is None:
        gaps.append("job_id")
    elif job_id is not None and row.job_id != job_id:
        gaps.append(f"job_id={row.job_id} (not this job, {job_id})")
    return gaps


def may_enforce_unproven(db, *, ignoring=()) -> dict:
    """`graduation`, read without the rows one job just failed to instrument.

    The SHADOW -> STAGING rule for this capability is that absence may block once the backlog
    is closed. Read naively after a job that just created an unproven row, the backlog is never
    closed -- the row that should fail the job is the row that says enforcement is premature.
    So the rows in `ignoring` are set aside and the question is asked of everything else.
    """
    ignored = {(cls, key) for cls, key, *_ in ignoring}
    gate = graduation(db, current=current_from_db(db), expected=expected_from_db(db))
    prior = [k for k in gate["instrument"] if tuple(k) not in ignored]
    return {"may_enforce_unproven": not prior, "prior_unproven": len(prior),
            "why": ("the backlog was closed before this job, so an absent row now means "
                    "something is wrong rather than something is unfitted"
                    if not prior else
                    f"{len(prior)} artefact(s) from before this job still carry no row, so "
                    f"an absence is logged and audited rather than failing the job")}


def summary(db, *, current: dict[str, str], expected) -> dict:
    """The estate by class and by how each row came to exist, for `/api/provenance`."""
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    verdicts = check(db, current=current, expected=expected)
    by_class: dict[str, dict[str, int]] = {}
    for v in verdicts:
        bucket = by_class.setdefault(v.artefact_class, {FRESH: 0, STALE: 0, UNPROVEN: 0})
        bucket[v.state] = bucket.get(v.state, 0) + 1
    by_source: dict[str, int] = {}
    unknown = {"created_by": 0, "job_id": 0, "code_commit": 0, "model": 0, "cost_cad": 0}
    rows = 0
    for row in db.scalars(select(ArtefactProvenance)):
        rows += 1
        by_source[row.source or "recorded"] = by_source.get(row.source or "recorded", 0) + 1
        if not row.created_by:
            unknown["created_by"] += 1
        if row.job_id is None:
            unknown["job_id"] += 1
        if (row.code_commit or UNKNOWN_COMMIT) == UNKNOWN_COMMIT:
            unknown["code_commit"] += 1
        if not row.model:
            unknown["model"] += 1
        if row.cost_cad is None:
            unknown["cost_cad"] += 1
    gate = graduation(db, current=current, expected=expected)
    return {
        "rows": rows,
        "by_class": by_class,
        "by_source": by_source,
        "unknown_fields": unknown,
        "enforcing": gate["may_enforce_unproven"],
        "estate": {"checked": len(verdicts),
                   "fresh": sum(1 for v in verdicts if v.state == FRESH),
                   "stale": sum(1 for v in verdicts if v.state == STALE),
                   "unproven": sum(1 for v in verdicts if v.state == UNPROVEN),
                   "invalidated": sum(1 for v in verdicts if retired(v))},
        "coverage": coverage(verdicts),
        "note": ("`unknown_fields` counts rows that could not say a thing rather than rows "
                 "that said it was unknown by accident: a backfilled row carries "
                 "code_commit='unknown' because the commit that built it was never recorded, "
                 "and a deterministic build carries no model because none was called"),
    }


def state() -> dict:
    """What is watched, what counts as proof, and what absence means here."""
    return {
        "artefact_classes": dict(ARTEFACT_CLASSES),
        "upstream_kinds": dict(UPSTREAM_KINDS),
        "states": [FRESH, STALE, UNPROVEN],
        # F-115 (K7): legacy output of a superseded design, retired rather than backlogged.
        "retired_states": [INVALIDATED],
        "sources": list(SOURCES),
        "required_lineage": list(REQUIRED_LINEAGE),
        "file_classes": sorted(FILE_CLASSES),
        "note": ("A stable slug must never make stale output appear current, so freshness "
                 "is proved rather than assumed: an artefact with no provenance row is "
                 "unproven, not fresh. The sentinel's block is the existing "
                 "halts_publication flag the publish path already consults, so it stops a "
                 "publication rather than reporting that it would (#171, #173)."),
    }
