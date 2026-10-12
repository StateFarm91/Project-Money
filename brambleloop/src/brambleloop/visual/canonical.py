"""Laura: the canonical identity of the Brambleloop brand face, held as data and enforced.

Owner ruling of 2026-10-06 (DECISION_LOG D-FB-11): the recurring woman frozen on 2026-09-22 is
**Laura**, the official, canonical human face of Brambleloop -- a permanent brand asset whose
identity must stay consistent for the lifetime of the business unless the owner explicitly
authorises a change. Build 2 task #59 ("re-make the canonical model") means repairing the image
system so it reproduces *this* woman; it never authorises a different one.

What this module pins, and why each is separate:

* `IDENTITY_ID` -- the canonical identity: Laura, revision 2 (`laura-r2-a42aeac7`, owner
  decision D-FB-14): the unchanged approved face a42aeac7... plus the owner-approved v6 revised
  torso and full-length. Revision 1 (`laura-v15-a42aeac7`, frozen build v15) and its missing
  frames stay as history in `REVISIONS` and the manifest. Neither is
  `reference_pack.PACK_VERSION`, which labels the pack-building procedure.
* the asset manifest (`assets/MANIFEST.json`, version 2) -- every committed image with its
  sha256, bytes, dimensions, role and provenance, plus the frozen v15 frames whose bytes exist
  only in production (`missing_canonical`). `verify()` fails on any byte change, deletion or
  identity-id change without a recorded owner decision.
* `AUTHORISED_IDENTITY_CHANGES` -- the owner decision ids that each authorise exactly one
  change (D-FB-14: revision 1 -> 2, spent once applied). `require_identity_change_authorised` is called
  by every path that can retire or create a canonical identity.
* `IDENTITY_RULE` -- "An image depicting a woman similar to Laura is NOT Laura and fails the
  identity gate." `laura_verdict` applies it on top of `identity.drift_check`: every locked
  face dimension must be read as a match; anything else is not Laura (drift) or not verified.
* the customer-facing chain -- canonical identity -> photorealism -> anatomy -> Product Truth
  -> composition/brand QA -> disclosure/policy -> publication. Preserving assets satisfies none
  of these. `PUBLICATION_APPROVED` is empty, and `customer_ready()` says so.

She is a persistent AI person and the Founder/CEO of Brambleloop (D-FB-12, D-FB-13); the
approved woman is her permanent visual identity. Customer copy may call her Brambleloop's AI
founder, and may never claim she is biologically human or has human experiences --
childhood, family, physically crocheting or testing, an address (`TRUTHFUL_IDENTITY`;
enforced by `store_foundation.lint` TRUTH_LAURA_HUMAN_CLAIM).

Nothing here generates, judges with a model, or spends.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

IDENTITY_NAME = "Laura"
FACE_SHA256 = "a42aeac72ba5733e42f55f9eb527218242c50610531ec9263ffb6f3e82519bc9"
# The build frozen in production on 2026-09-22 (registry version 1). Revision 1 of her identity
# was this build; a fresh database may still only ever freeze this build (`freeze.freeze`).
FROZEN_IDENTITY_VERSION = "v15-the-revised-dimension-is-judged-by-the-frame-whose-job-it-is"
FROZEN_PACK_NUMBER = 15
PRIOR_IDENTITY_ID = f"laura-v{FROZEN_PACK_NUMBER}-{FACE_SHA256[:8]}"
REGISTRY_KEY = "brambleloop-canonical"

# Revision 2 (owner decision D-FB-14, 2026-10-06): the unchanged approved face plus the v6
# bust-revision run's torso and full-length frames, approved by the owner as her canonical
# body/proportion references going forward. Their provenance stays what it is -- the v6 run
# of 2026-09-21 -- and they are NOT the missing frozen-v15 frames, which stay recorded as
# missing on revision 1.
TORSO_SHA256 = "afe6191fb4c68d0a9c61229fe822a1032ee7c54150597210888db25b0f9ef0db"
FULL_LENGTH_SHA256 = "f32bac686cba46c75e3ac193e72f2bcea4ba7ebc80355a102a4bed4bca3931e0"
REVISION_NUMBER = 2
REVISION_DECISION_ID = "D-FB-14"
IDENTITY_ID = f"laura-r{REVISION_NUMBER}-{FACE_SHA256[:8]}"
CURRENT_REFERENCE_HASHES: dict[str, str] = {
    "neutral_portrait": FACE_SHA256,
    "torso_fit_reference": TORSO_SHA256,
    "full_length_standing": FULL_LENGTH_SHA256,
}
REVISION_FIELD = "canonical_revision"

OWNER_RULING_ID = "D-FB-11"
OWNER_RULING_AT = "2026-10-06"
# Decision ids that established or confirmed this identity. Changing IDENTITY_ID, the face
# hash or the frozen version requires a new id here AND in AUTHORISED_IDENTITY_CHANGES, and
# both must appear in DECISION_LOG.md (tests/test_canon_manifest.py checks all three).
AGENT_RULING_ID = "D-FB-12"
FOUNDER_RULING_ID = "D-FB-13"
IDENTITY_DECISIONS: tuple[str, ...] = (OWNER_RULING_ID, AGENT_RULING_ID, FOUNDER_RULING_ID,
                                       REVISION_DECISION_ID)
# The protected-authority mechanism. Each entry is an owner decision (recorded in
# DECISION_LOG.md) that authorises exactly one identity change, described by the revision in
# REVISIONS that cites it: from the revision it supersedes to that revision, with exactly
# those reference hashes. A spent decision authorises nothing further, so any future change
# to Laura needs a NEW owner decision id here, a new revision, and a DECISION_LOG entry.
AUTHORISED_IDENTITY_CHANGES: tuple[str, ...] = (REVISION_DECISION_ID,)
REVISIONS: tuple[dict, ...] = (
    {"identity_id": PRIOR_IDENTITY_ID, "revision": 1, "decision": OWNER_RULING_ID,
     "supersedes": None, "status": "superseded",
     "basis": f"frozen build {FROZEN_IDENTITY_VERSION} (production registry version 1)",
     "reference_hashes": {"neutral_portrait": FACE_SHA256}},
    {"identity_id": IDENTITY_ID, "revision": REVISION_NUMBER,
     "decision": REVISION_DECISION_ID, "supersedes": PRIOR_IDENTITY_ID, "status": "current",
     "basis": ("approved face a42aeac7 + v6 bust-revision run torso and full-length "
               "(2026-09-21), owner-approved as canonical body references 2026-10-06"),
     "reference_hashes": dict(CURRENT_REFERENCE_HASHES)},
)

IDENTITY_RULE = ("An image depicting a woman similar to Laura is NOT Laura and fails the "
                 "identity gate.")
LOCKED: tuple[str, ...] = (
    "face", "hair", "eyes", "apparent age", "facial structure",
    "body proportions where established", "canonical 3-frame reference pack",
    "5-frame stress set", "frozen body-reference evidence")
# The face dimensions (identity.FACE_DIMENSIONS minus stylisation, which is expression and
# styling rather than who she is) that must each be read as a match for a frame to be Laura.
LOCKED_FACE_DIMENSIONS: tuple[str, ...] = ("face", "hair", "eyes", "age")

# D-FB-12 (owner ruling 2026-10-06, spec/07_Laura_Owner_Ruling_2026-10-06.md): Laura is the
# permanent canonical AI Brand & Customer Experience Director and public-facing AI
# representative of Brambleloop. The approved woman is her visual identity. She is a real
# Brambleloop AI agent/person whose identity, memory, role and history persist independently
# of any underlying model -- never a disposable image model.
# D-FB-13 supersedes the narrower role: "Laura is a persistent AI person and the Founder/CEO of
# Brambleloop." Brand & Customer Experience remain hers within that executive role.
ROLE = "Founder/CEO (AI person)"
PUBLIC_IDENTITY = "Brambleloop's AI founder"
TRUTHFUL_IDENTITY = (
    "Laura is a persistent AI person and the Founder/CEO of Brambleloop (D-FB-13). Publicly "
    "the Founder/CEO wording is used only with truthful AI disclosure (\"Laura, Brambleloop's "
    "AI founder\"), and her durable software actions are her genuine history. She is never "
    "claimed to be biologically human and is never given fabricated human experiences: a "
    "childhood, a family, learning to crochet from a relative, physically crocheting, "
    "designing or testing samples by hand, a home address, or events she attended. Laura copy "
    "never makes legal-ownership or seller-of-record statements; those must match the actual "
    "legal person(s).")
NOT_A_REAL_PERSON = TRUTHFUL_IDENTITY  # earlier name, kept for callers

CUSTOMER_FACING_GATES: tuple[str, ...] = (
    "canonical_identity", "photorealism", "anatomy", "product_truth_if_product_shown",
    "composition_brand_qa", "disclosure_policy", "publication_gate")

# Asset publication status. `canonical_reference` defines her; it is not a licence to show
# her to customers. Only `publication_approved` is, and nothing is.
CANONICAL_REFERENCE = "canonical_reference"
PUBLICATION_APPROVED_STATUS = "publication_approved"
NOT_FOR_PUBLICATION = "not_for_publication"
PUBLICATION_STATUSES = (CANONICAL_REFERENCE, PUBLICATION_APPROVED_STATUS, NOT_FOR_PUBLICATION)
PUBLICATION_APPROVED: frozenset[str] = frozenset()

# W3-B2 wiring 5 (W3-WIRE4): owner publication approvals scoped to ONE asset on ONE surface.
#
# `PUBLICATION_APPROVED` is global (every surface) and implies every CUSTOMER_FACING_GATE
# passed, so it cannot say what the owner actually decided about the canonical storefront
# banner. This table can, and it changes nothing global: `asset_status(sha)` and
# `customer_ready(sha)` are untouched; only `asset_status(sha, surface=...)` and
# `surface_publication(...)` read it, for that sha on that surface.
#
# What the owner approved for the banner bytes 048a1991... (DECISION_LOG):
# * D-FB-17 item 2 -- these exact bytes ARE the canonical storefront banner, to be used IF
#   they pass every applicable publication gate (a conditional designation, not a waiver);
# * D-FB-18 item 1 -- an owner human identity review: the woman in THIS depiction is Laura.
# What the owner did NOT approve, which therefore stays a finding: the baked-in navigation
# listing empty categories (D-FB-18 item 3) and the concept crochet as evidence of any
# Brambleloop product (D-FB-18 item 2; Product Truth not weakened). No gate is waived.
SURFACE_STOREFRONT_BANNER = "storefront_banner"
SURFACE_APPROVED_CONDITIONAL = "owner_surface_approval_conditional"
PUBLICATION_APPROVALS: dict[str, dict] = {
    "048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98": {
        "surfaces": (SURFACE_STOREFRONT_BANNER,),
        "decisions": ("D-FB-17", "D-FB-18"),
        "owner_approved": ("canonical_identity",),
        "designation": ("D-FB-17 item 2: the exact file is the canonical storefront banner, "
                        "used only if it passes every applicable publication gate"),
        "identity_review": "D-FB-18 item 1: the woman in this depiction is Laura (this "
                           "depiction only; every other frame keeps the identity gate)",
        "gates_waived_by_owner": (),
        "not_approved": (
            "public navigation listing empty categories (D-FB-18 item 3)",
            "the concept crochet as evidence of any Brambleloop product (D-FB-18 item 2)"),
    },
}

ROLES_V2: tuple[str, ...] = (
    "approved_face", "canonical_reference_pack", "canonical_stress_set", "superseded_body",
    "historical", "owner_concept", "missing_canonical", "prior_revision_reference")
REFERENCE_FRAMES: tuple[str, ...] = (
    "neutral_portrait", "torso_fit_reference", "full_length_standing")
STRESS_FRAMES: tuple[str, ...] = (
    "fitted_garment", "fitted_garment_close", "loose_layered_garment",
    "non_garment_lifestyle", "winter_seasonal")


from .identity import IdentityRefused  # noqa: E402 - identity imports nothing from here


class CanonRefused(IdentityRefused):
    """An act that would change, replace or misuse Laura without the owner's decision.

    An `IdentityRefused`, so every caller that already fails closed on a refused identity
    fails closed on this too."""


def _assets_dir() -> Path:
    from . import brief

    return Path(brief.ASSETS_DIR)


def manifest() -> dict:
    """The whole manifest (v2). Raises `CanonRefused` when it cannot be read."""
    from . import brief

    path = _assets_dir() / brief.MANIFEST_NAME
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CanonRefused(f"the asset manifest at {path} cannot be read ({exc})") from exc
    if not isinstance(loaded, dict):
        raise CanonRefused("the asset manifest is not an object")
    return loaded


def all_entries(m: dict | None = None) -> list[dict]:
    """Every committed asset: the top-level five plus the versioned library."""
    m = m if m is not None else manifest()
    return [dict(e) for e in (m.get("assets") or [])] + [dict(e) for e in (m.get("library") or [])]


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def verify(m: dict | None = None) -> dict:
    """Every integrity property of the canonical identity, as a list of problems.

    Empty `problems` means: every committed asset is present with the recorded bytes; the
    identity block names `IDENTITY_ID` with this face and frozen version; the approved face is
    exactly one file; the canonical reference-pack face is the approved bytes; every missing
    canonical frame is still declared; no asset is `publication_approved`; and every
    identity decision id the manifest cites is one this code recognises.
    """
    problems: list[str] = []
    try:
        m = m if m is not None else manifest()
    except CanonRefused as exc:
        return {"ok": False, "problems": [str(exc)]}
    root = _assets_dir()
    ident = m.get("identity") or {}
    if m.get("manifest_version") != 2:
        problems.append(f"manifest_version is {m.get('manifest_version')!r}, not 2")
    if ident.get("identity_id") != IDENTITY_ID:
        problems.append(f"identity_id is {ident.get('identity_id')!r}, not {IDENTITY_ID!r}; "
                        f"a new identity needs an owner decision in AUTHORISED_IDENTITY_CHANGES")
    if ident.get("name") != IDENTITY_NAME:
        problems.append(f"identity name is {ident.get('name')!r}, not {IDENTITY_NAME!r}")
    if ident.get("face_sha256") != FACE_SHA256:
        problems.append("identity face_sha256 differs from the approved face")
    if ident.get("revision") != REVISION_NUMBER or \
            ident.get("revision_decision") != REVISION_DECISION_ID:
        problems.append(f"identity revision is {ident.get('revision')!r} on "
                        f"{ident.get('revision_decision')!r}, not {REVISION_NUMBER} on "
                        f"{REVISION_DECISION_ID}")
    if ident.get("prior_identity_id") != PRIOR_IDENTITY_ID or \
            ident.get("prior_frozen_identity_version") != FROZEN_IDENTITY_VERSION:
        problems.append("the prior revision (frozen v15 build) is not recorded")
    if dict(ident.get("reference_hashes") or {}) != CURRENT_REFERENCE_HASHES:
        problems.append("identity reference_hashes differ from the approved revision")
    listed = [(r.get("identity_id"), r.get("decision"), r.get("supersedes"))
              for r in m.get("revisions") or []]
    if listed != [(r["identity_id"], r["decision"], r["supersedes"]) for r in REVISIONS]:
        problems.append(f"revision history {listed} differs from canonical.REVISIONS")
    cited = set(ident.get("owner_decision_ids") or [])
    if not cited or not cited <= set(IDENTITY_DECISIONS) | set(AUTHORISED_IDENTITY_CHANGES):
        problems.append(f"identity cites decisions {sorted(cited)} not recorded in code "
                        f"({sorted(IDENTITY_DECISIONS)})")
    if ident.get("publication_approved_assets"):
        problems.append("the manifest lists publication-approved Laura assets; none exist")

    entries = all_entries(m)
    if not entries:
        problems.append("the manifest lists no assets")
    faces = [e for e in entries if e.get("role") == "approved_face"]
    if len(faces) != 1 or faces[0].get("sha256") != FACE_SHA256:
        problems.append(f"expected exactly one approved_face with sha {FACE_SHA256[:8]}")
    for e in entries:
        rel = str(e.get("file") or "")
        if e.get("role") not in ROLES_V2:
            problems.append(f"{rel}: role {e.get('role')!r} not in {ROLES_V2}")
        if e.get("publication_status") not in PUBLICATION_STATUSES:
            problems.append(f"{rel}: publication_status {e.get('publication_status')!r}")
        if e.get("publication_status") == PUBLICATION_APPROVED_STATUS and \
                e.get("sha256") not in PUBLICATION_APPROVED:
            problems.append(f"{rel}: marked publication_approved with no approval in code")
        if "forbidden_as_fallback" not in e:
            problems.append(f"{rel}: forbidden_as_fallback is not stated")
        path = root / rel
        if not rel or not path.is_file():
            problems.append(f"{rel or '?'}: listed and not on disk")
            continue
        if _sha(path) != e.get("sha256"):
            problems.append(f"{rel}: bytes changed (sha256 no longer {str(e.get('sha256'))[:12]})")
        if "bytes" in e and path.stat().st_size != e["bytes"]:
            problems.append(f"{rel}: size changed")
        if e.get("role") in ("superseded_body", "historical", "owner_concept") and \
                not e.get("forbidden_as_fallback"):
            problems.append(f"{rel}: a {e['role']} asset must be forbidden as a fallback")
    pack = {e.get("frame"): e.get("sha256") for e in entries
            if e.get("role") == "canonical_reference_pack"
            and e.get("identity_id") == IDENTITY_ID}
    if pack != CURRENT_REFERENCE_HASHES:
        problems.append(f"the canonical reference pack of {IDENTITY_ID} is "
                        f"{ {k: str(v)[:8] for k, v in pack.items()} }, not the approved "
                        f"face + revised torso + revised full-length")
    stray = [e.get("file") for e in entries if e.get("role") == "canonical_reference_pack"
             and e.get("identity_id") != IDENTITY_ID]
    if stray:
        problems.append(f"canonical_reference_pack entries outside {IDENTITY_ID}: {stray}")
    for e in entries:
        if e.get("sha256") in CURRENT_REFERENCE_HASHES.values() and e.get("forbidden_as_fallback"):
            problems.append(f"{e.get('file')}: a current canonical reference is marked forbidden")

    missing = m.get("missing_canonical") or []
    declared = {(x.get("group"), x.get("frame")) for x in missing}
    committed = {("reference_pack", e.get("frame")) for e in entries
                 if e.get("role") == "canonical_reference_pack"} | \
                {("stress_set", e.get("frame")) for e in entries
                 if e.get("role") == "canonical_stress_set"}
    for group, frames in (("reference_pack", REFERENCE_FRAMES), ("stress_set", STRESS_FRAMES)):
        for frame in frames:
            if (group, frame) not in declared | committed:
                problems.append(f"{group}/{frame}: neither committed nor declared missing")
    for x in missing:
        if x.get("role") != "missing_canonical" or x.get("sha256") and not x.get("sha256_known"):
            problems.append(f"missing {x.get('frame')}: malformed entry")
        # The v15 frames stay missing history of revision 1. A file standing in for one is a
        # relabel, which the owner ruled out (D-FB-14).
        if x.get("identity_id") != PRIOR_IDENTITY_ID:
            problems.append(f"missing {x.get('frame')}: belongs to {x.get('identity_id')!r}, "
                            f"not the prior revision {PRIOR_IDENTITY_ID}")
    for x in ("torso_fit_reference", "full_length_standing"):
        if ("reference_pack", x) not in declared:
            problems.append(f"the missing frozen-v15 {x} is no longer recorded as missing")
    return {"ok": not problems, "problems": problems, "identity_id": IDENTITY_ID,
            "assets": len(entries), "missing_canonical": len(missing)}


def forbidden_hashes(m: dict | None = None) -> frozenset[str]:
    """Every sha256 the manifest marks forbidden as a fallback reference.

    Raises `CanonRefused` when the manifest cannot be read: callers fail closed.
    """
    return frozenset(str(e["sha256"]).lower() for e in all_entries(m)
                     if e.get("forbidden_as_fallback") and e.get("sha256"))


def refuse_forbidden_reference(path_or_sha: str) -> None:
    """Raise if a reference names bytes the manifest says may never be one."""
    value = str(path_or_sha or "")
    sha = value.lower() if len(value) == 64 and all(c in "0123456789abcdef"
                                                     for c in value.lower()) else _sha(Path(value))
    try:
        forbidden = forbidden_hashes()
    except CanonRefused as exc:
        raise CanonRefused(f"no reference can be vouched for: {exc}") from exc
    if sha and sha in forbidden:
        raise CanonRefused(
            f"{value[:80]} is a superseded/historical/concept asset (sha {sha[:12]}); it is "
            f"evidence, never a reference or fallback for Laura")


def face_hash_of(pack) -> str:
    """The sha256 of a reference pack's face, from its record or its reference image."""
    from . import identity

    fields = dict(getattr(pack, "fields", None) or {})
    recorded = str((fields.get("reference_hashes") or {}).get(identity.FACE_HASH_KEY) or "")
    if identity._is_sha256(recorded):
        return recorded.lower()
    ref = str(fields.get("reference_image") or "")
    if identity._is_sha256(ref):
        return ref.lower()
    if ref:
        got = _sha(Path(ref))
        if got:
            return got
        if Path(ref).name == "identity_portrait.jpg":
            # The production row recorded the committed portrait's path at freeze time.
            return FACE_SHA256
    return ""


def is_laura(pack) -> bool:
    """Whether a canonical pack is Laura's: her approved face is its face."""
    return pack is not None and face_hash_of(pack) == FACE_SHA256


def revision_of(pack) -> str:
    """Which identity revision a registry pack holds. A Laura pack with no record is r1."""
    if pack is None:
        return ""
    recorded = str(dict(getattr(pack, "fields", None) or {}).get(REVISION_FIELD) or "")
    return recorded or (PRIOR_IDENTITY_ID if is_laura(pack) else "")


def require_identity_change_authorised(approval: dict | None, *, current=None,
                                       action: str = "replace",
                                       reference_hashes: dict | None = None) -> None:
    """Refuse to retire, replace, regenerate or alter Laura without a recorded owner decision.

    Applies when `current` is Laura's pack (or no pack is given, for paths that would create a
    canonical identity). `approval['owner_decision_id']` must be in
    `AUTHORISED_IDENTITY_CHANGES` AND name the one change its revision describes: from the
    revision `current` holds to the next, with exactly that revision's reference hashes. A
    decision that has been applied, or is offered for any other change, authorises nothing.
    """
    if current is not None and not is_laura(current):
        return
    decision = str((approval or {}).get("owner_decision_id") or "").strip()
    rev = next((r for r in REVISIONS if r["decision"] == decision and r["supersedes"]), None)
    if decision and decision in AUTHORISED_IDENTITY_CHANGES and rev is not None:
        want = {k: str(v).lower() for k, v in rev["reference_hashes"].items()}
        got = {k: str(v).lower() for k, v in (reference_hashes or {}).items()}
        if current is not None and revision_of(current) == rev["supersedes"] and got == want:
            return
        raise CanonRefused(
            f"{action} refused: {decision} authorises exactly one change, "
            f"{rev['supersedes']} -> {rev['identity_id']} with its recorded reference hashes. "
            f"The canonical pack holds {revision_of(current) or 'nothing'} and the change "
            f"offered does not match, so the decision is spent or misapplied. A further "
            f"change to Laura needs a new owner decision")
    raise CanonRefused(
        f"{action} refused: Laura ({IDENTITY_ID}) is the canonical face of Brambleloop "
        f"({OWNER_RULING_ID}). Replacing, regenerating or altering her needs an owner "
        f"decision recorded in DECISION_LOG and listed in "
        f"canonical.AUTHORISED_IDENTITY_CHANGES; got {decision or 'none'}. "
        f"Task #59 means repairing the image system so it reproduces her, not a new woman")


def reference_file(frame: str) -> str:
    """The committed file for one frame of the current revision, verified by its bytes.

    '' when the frame is not part of the revision or the file's bytes are not the recorded
    bytes -- the caller's answer is then "no approved reference", never a substitute.
    """
    want = CURRENT_REFERENCE_HASHES.get(frame)
    if not want:
        return ""
    try:
        entries = all_entries()
    except CanonRefused:
        return ""
    for e in entries:
        if (e.get("role") == "canonical_reference_pack" and e.get("identity_id") == IDENTITY_ID
                and e.get("frame") == frame and e.get("sha256") == want):
            path = _assets_dir() / str(e["file"])
            return str(path) if _sha(path) == want else ""
    return ""


def adopt_revision(db, *, approved_by: str = "owner") -> dict:
    """Move a registry holding revision 1 of Laura to the current revision (D-FB-14).

    The face is unchanged; the body references become the owner-approved v6 frames, pinned by
    hash. Refused unless the registry holds Laura at the revision this one supersedes, so it
    applies once. Nothing in the repository calls it; it is the deploy step the decision
    authorises.
    """
    from . import brief, model_registry

    current = model_registry.canonical_pack(db)
    rev = next(r for r in REVISIONS if r["identity_id"] == IDENTITY_ID)
    if current is None or revision_of(current) != rev["supersedes"]:
        raise CanonRefused(
            f"adopt_revision refused: the registry holds {revision_of(current) or 'nothing'}, "
            f"and {REVISION_DECISION_ID} moves {rev['supersedes']} only")
    refs = [brief.approved_portrait(), reference_file("torso_fit_reference"),
            reference_file("full_length_standing")]
    if not all(refs):
        raise CanonRefused("a revision reference file does not verify; nothing adopted")
    fields = {k: v for k, v in current.fields.items()
              if k not in ("reference_image", "reference_hashes")}
    fields[REVISION_FIELD] = IDENTITY_ID
    pack = model_registry.replace_canonical(
        db, new_key=f"{REGISTRY_KEY}-{IDENTITY_ID}", fields=fields, image_refs=refs,
        reference_hashes=dict(CURRENT_REFERENCE_HASHES),
        redesign_approval={
            "at": "2026-10-06", "scope": "reference_revision", "approved_by": approved_by,
            "supersedes_version": current.version, "owner_decision_id": REVISION_DECISION_ID,
            "decision": ("owner-approved canonical identity revision: approved face "
                         "unchanged, v6 revised torso and full-length as canonical body "
                         "references")},
        note=(f"{IDENTITY_ID}: {REVISION_DECISION_ID}. Body references are the v6 "
              f"bust-revision run of 2026-09-21, not the missing frozen-v15 frames"))
    return {"identity_id": IDENTITY_ID, "version": pack.version,
            "reference_hashes": dict(CURRENT_REFERENCE_HASHES)}


def require_frozen_build(pack_version) -> None:
    """A (re-)freeze may only ever reproduce the approved v15 build of Laura."""
    from . import reference_pack

    if reference_pack.pack_number(pack_version) != FROZEN_PACK_NUMBER:
        require_identity_change_authorised(
            None, action=f"freezing pack {str(pack_version)[:40]!r} as canonical")


def laura_verdict(scored: dict) -> dict:
    """The identity rule applied to per-dimension verdicts (match / drift / unmeasurable).

    Laura only when every locked face dimension is a match and no dimension drifted. Any
    drift is `not_laura` -- a similar woman is not Laura. Anything unread is `unverified`,
    which blocks exactly as `not_laura` does; it is never a pass.
    """
    from . import identity

    scored = dict(scored or {})
    drifted = [d for d, v in scored.items() if v == identity.DRIFT]
    unread = [d for d in LOCKED_FACE_DIMENSIONS if scored.get(d) != identity.MATCH]
    if drifted:
        verdict, why = "not_laura", f"drift on {drifted}. {IDENTITY_RULE}"
    elif unread:
        verdict, why = "unverified", (f"locked dimensions {unread} were not read as a match; "
                                      f"an unconfirmed likeness is not Laura")
    else:
        verdict, why = "laura", ""
    return {"verdict": verdict, "blocks": verdict != "laura", "why": why,
            "drifted": drifted, "unread_locked": unread, "rule": IDENTITY_RULE}


def surface_approval(sha256: str | None, surface: str | None) -> dict | None:
    """The owner's publication approval for exactly this asset on exactly this surface."""
    entry = PUBLICATION_APPROVALS.get(str(sha256 or "").lower())
    if not entry or not surface or surface not in entry["surfaces"]:
        return None
    return {"sha256": str(sha256).lower(), "surface": surface, **entry}


def surface_publication(sha256: str | None, surface: str, conditions: dict[str, str]) -> dict:
    """Publication of one asset on one surface: the owner's scoped approval AND every
    applicable gate the caller measured (`conditions`: gate -> PASS/FAIL/UNKNOWN).

    PASS only when a scoped owner approval exists and every condition is PASS (UNKNOWN never
    passes). Without an approval: FAIL. With one but a gate outstanding: FAIL if any gate
    failed, else UNKNOWN. Nothing global changes either way."""
    approval = surface_approval(sha256, surface)
    if not conditions:
        conds_ok, failing, unknown = False, [], ["no applicable gate was measured"]
    else:
        failing = sorted(g for g, st in conditions.items() if st == "FAIL")
        unknown = sorted(g for g, st in conditions.items() if st not in ("PASS", "FAIL"))
        conds_ok = not failing and not unknown
    if approval is None:
        status = "FAIL"
        why = (f"no owner publication approval covers these bytes on '{surface}'; "
               f"asset status '{asset_status(sha256 or '')}'")
    elif conds_ok:
        status = "PASS"
        why = (f"owner approval {list(approval['decisions'])} for '{surface}' and every "
               f"applicable gate passed")
    else:
        status = "FAIL" if failing else "UNKNOWN"
        why = (f"the owner approved {list(approval['owner_approved'])} for '{surface}' "
               f"({'; '.join(approval['decisions'])}), conditional on every applicable gate; "
               f"outstanding: failed {failing or 'none'}, unknown {unknown or 'none'}")
    return {"status": status, "surface": surface, "approval": approval,
            "failing": failing, "unknown": unknown, "why": why,
            "global_asset_status": asset_status(sha256 or ""),
            "global_customer_ready": customer_ready(sha256)["customer_ready"]}


def asset_status(sha256: str, surface: str | None = None) -> str:
    """The publication status of one image by its bytes. Unknown bytes are never approved.

    With `surface`, an owner approval scoped to that asset and surface reads as
    `owner_surface_approval_conditional` (conditional on that surface's gates; see
    `surface_publication`); without it, or on any other surface, the global status."""
    sha = str(sha256 or "").lower()
    if surface is not None and surface_approval(sha, surface) is not None:
        return SURFACE_APPROVED_CONDITIONAL
    if sha in PUBLICATION_APPROVED:
        return PUBLICATION_APPROVED_STATUS
    for e in all_entries():
        if e.get("sha256") == sha:
            return str(e.get("publication_status") or NOT_FOR_PUBLICATION)
    return NOT_FOR_PUBLICATION


def customer_ready(sha256: str | None = None) -> dict:
    """Whether Laura imagery may be shown to customers. Today: no, for every image.

    Preserving canonical references satisfies none of the gates after `canonical_identity`.
    The existing photorealism verdict on the frozen pack (B-657: `pack_is_the_cause`) stands.
    """
    approved = bool(sha256) and str(sha256).lower() in PUBLICATION_APPROVED
    return {
        "customer_ready": approved,
        "status": "READY" if approved else "GATED",
        "gates": list(CUSTOMER_FACING_GATES),
        "passed": ["canonical_identity"] if sha256 else [],
        "blocking": [] if approved else [g for g in CUSTOMER_FACING_GATES
                                         if g != "canonical_identity"],
        "why": ("no Laura image is publication_approved. Canonical references define her; "
                "they are not customer imagery. Photorealism failures on the frozen pack "
                "(B-657) remain valid, and the repair path is task #59: make the visual "
                "system reproduce her at customer quality, then pass every gate in order"),
    }


def summary() -> dict:
    """What defines Laura and what does not, for docs, the Store and the Command Center."""
    try:
        m = manifest()
    except CanonRefused as exc:
        return {"identity_id": IDENTITY_ID, "ok": False, "problems": [str(exc)]}
    entries = all_entries(m)
    check = verify(m)
    return {
        "identity_id": IDENTITY_ID, "name": IDENTITY_NAME, "face_sha256": FACE_SHA256,
        "frozen_identity_version": FROZEN_IDENTITY_VERSION,
        "pack_procedure_version_is_not_identity": True,
        "rule": IDENTITY_RULE, "locked": list(LOCKED),
        "role": ROLE, "truthful_identity": TRUTHFUL_IDENTITY,
        "ok": check["ok"], "problems": check["problems"],
        "canonical": [e["file"] for e in entries
                      if e.get("role") in ("approved_face", "canonical_reference_pack",
                                           "canonical_stress_set")],
        "historical": [e["file"] for e in entries
                       if e.get("role") in ("historical", "superseded_body")],
        "missing_canonical": [f"{x['group']}/{x['frame']}" for x in
                              m.get("missing_canonical") or []],
        "publication_approved": sorted(PUBLICATION_APPROVED),
        "surface_approvals": {sha: list(v["surfaces"]) for sha, v in
                              PUBLICATION_APPROVALS.items()},
        "customer_ready": False,
    }
