"""Laura: the canonical identity of the Brambleloop brand face, held as data and enforced.

Owner ruling of 2026-10-06 (DECISION_LOG D-FB-11): the recurring woman frozen on 2026-09-22 is
**Laura**, the official, canonical human face of Brambleloop -- a permanent brand asset whose
identity must stay consistent for the lifetime of the business unless the owner explicitly
authorises a change. Build 2 task #59 ("re-make the canonical model") means repairing the image
system so it reproduces *this* woman; it never authorises a different one.

What this module pins, and why each is separate:

* `IDENTITY_ID` -- the canonical identity: Laura, frozen identity build v15, face sha256
  a42aeac7.... It is *not* `reference_pack.PACK_VERSION`, which labels the pack-building
  procedure (currently v16-...). A newer procedure label never means a newer woman.
* the asset manifest (`assets/MANIFEST.json`, version 2) -- every committed image with its
  sha256, bytes, dimensions, role and provenance, plus the frozen v15 frames whose bytes exist
  only in production (`missing_canonical`). `verify()` fails on any byte change, deletion or
  identity-id change without a recorded owner decision.
* `AUTHORISED_IDENTITY_CHANGES` -- the owner decision ids that authorise replacing or altering
  her. Empty: the owner has authorised none. `require_identity_change_authorised` is called
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
FROZEN_IDENTITY_VERSION = "v15-the-revised-dimension-is-judged-by-the-frame-whose-job-it-is"
FROZEN_PACK_NUMBER = 15
IDENTITY_ID = f"laura-v{FROZEN_PACK_NUMBER}-{FACE_SHA256[:8]}"
REGISTRY_KEY = "brambleloop-canonical"

OWNER_RULING_ID = "D-FB-11"
OWNER_RULING_AT = "2026-10-06"
# Decision ids that established or confirmed this identity. Changing IDENTITY_ID, the face
# hash or the frozen version requires a new id here AND in AUTHORISED_IDENTITY_CHANGES, and
# both must appear in DECISION_LOG.md (tests/test_canon_manifest.py checks all three).
AGENT_RULING_ID = "D-FB-12"
FOUNDER_RULING_ID = "D-FB-13"
IDENTITY_DECISIONS: tuple[str, ...] = (OWNER_RULING_ID, AGENT_RULING_ID, FOUNDER_RULING_ID)
# Owner decisions that authorise replacing, regenerating or altering her. None exist.
AUTHORISED_IDENTITY_CHANGES: tuple[str, ...] = ()

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

ROLES_V2: tuple[str, ...] = (
    "approved_face", "canonical_reference_pack", "canonical_stress_set", "superseded_body",
    "historical", "owner_concept", "missing_canonical")
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
    if ident.get("frozen_identity_version") != FROZEN_IDENTITY_VERSION:
        problems.append("frozen_identity_version differs from the frozen v15 build")
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
    pack_face = [e for e in entries if e.get("role") == "canonical_reference_pack"
                 and e.get("frame") == "neutral_portrait"]
    if len(pack_face) != 1 or pack_face[0].get("sha256") != FACE_SHA256:
        problems.append("the canonical reference pack's face frame is not the approved face")

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


def require_identity_change_authorised(approval: dict | None, *, current=None,
                                       action: str = "replace") -> None:
    """Refuse to retire, replace, regenerate or alter Laura without a recorded owner decision.

    Applies when `current` is Laura's pack (or no pack is given, for paths that would create a
    canonical identity). `approval['owner_decision_id']` must be one of
    `AUTHORISED_IDENTITY_CHANGES`, which the owner alone populates and which is empty.
    """
    if current is not None and not is_laura(current):
        return
    decision = str((approval or {}).get("owner_decision_id") or "").strip()
    if decision and decision in AUTHORISED_IDENTITY_CHANGES:
        return
    raise CanonRefused(
        f"{action} refused: Laura ({IDENTITY_ID}) is the canonical face of Brambleloop "
        f"({OWNER_RULING_ID}). Replacing, regenerating or altering her needs an owner "
        f"decision recorded in DECISION_LOG and listed in "
        f"canonical.AUTHORISED_IDENTITY_CHANGES; got {decision or 'none'}. "
        f"Task #59 means repairing the image system so it reproduces her, not a new woman")


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


def asset_status(sha256: str) -> str:
    """The publication status of one image by its bytes. Unknown bytes are never approved."""
    sha = str(sha256 or "").lower()
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
        "customer_ready": False,
    }
