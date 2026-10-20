"""Provider conditioning packages for Laura's canonical identity (F-733).

F-733 asks for a canonical asset registry that also stores, per image provider, the exact
conditioning package an identity-locked render is built from. Until now the package existed
only implicitly, inside each request body (`gateway.images.conditioning_receipt` proves the
bytes left, per request). Nothing recorded, ahead of any call, which canonical frames each
provider will receive, in which order, and how many of them its dialect actually transmits.
Until W4-FLUXAPI (2026-10-19) BFL carried only the first reference, in a field FLUX.2 does not
define; every BFL dialect now carries every reference up to the documented limit.

A package is derived from the canonical revision alone (`visual.canonical`,
laura-r2-a42aeac7, D-FB-14). It is never derived from a session, a scratch file or a
historical frame, and a forbidden hash can never enter it. The file is stored under
`visual/assets/conditioning/<identity_id>/<provider>.json`.
`verify_stored` recomputes the package from the canonical files and compares it field by
field, so a changed reference, a reordered pack or an edited JSON is caught. Building and
verifying are local and deterministic: no provider call, no spend. Laura's images are only
read; nothing here writes, regenerates or alters them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "conditioning-package/1.0.0"
# Face first. A dialect that carries a single reference (BFL) must receive the face: identity
# is judged on it first (`model_registry.gate_frames`), and the body frames answer only for
# the dimensions whose job they are.
FRAME_ORDER: tuple[str, ...] = ("neutral_portrait", "torso_fit_reference",
                                "full_length_standing")
# How many references each dialect actually places in the request body
# (`gateway.images._request_for`): every dialect carries up to the provider's own documented
# limit, and refuses more. BFL was single-reference until W4-FLUXAPI; the set is kept, empty,
# so a dialect that regresses to one reference has one place to be declared.
SINGLE_REFERENCE_DIALECTS: frozenset[str] = frozenset()


class ConditioningRefused(ValueError):
    """A package that cannot be built honestly: no lock, a missing or forbidden reference."""


def _root() -> Path:
    from . import canonical

    return canonical._assets_dir() / "conditioning"


def lock_providers() -> list[str]:
    from ..gateway import images

    return [p.key for p in images.PROVIDERS if p.supports_lock]


def package(provider_key: str) -> dict:
    """The conditioning package `provider_key` receives for the current canonical revision."""
    from ..gateway import images
    from . import canonical

    provider = images.BY_KEY.get(provider_key)
    if provider is None:
        raise ConditioningRefused(f"{provider_key!r} is not an image provider")
    if not provider.supports_lock:
        raise ConditioningRefused(f"{provider_key} cannot condition on reference images, so "
                                  f"it has no identity package")
    forbidden = canonical.forbidden_hashes()
    refs = []
    assets = canonical._assets_dir()
    for frame in FRAME_ORDER:
        want = canonical.CURRENT_REFERENCE_HASHES.get(frame)
        path = canonical.reference_file(frame)       # '' unless the bytes are the approved bytes
        if not want or not path:
            raise ConditioningRefused(f"{frame}: the approved reference is not on this disk with "
                                      f"its approved bytes; a package without it would "
                                      f"condition on something else")
        if want.lower() in forbidden:
            raise ConditioningRefused(f"{frame}: {want[:12]} is forbidden as a reference")
        refs.append({"frame": frame, "file": str(Path(path).relative_to(assets)),
                     "sha256": want, "bytes": Path(path).stat().st_size})
    carried = 1 if provider.dialect in SINGLE_REFERENCE_DIALECTS else min(
        len(refs), int(provider.reference_images))
    for i, r in enumerate(refs):
        r["transmitted"] = i < carried
    body = {"version": VERSION, "identity_id": canonical.IDENTITY_ID,
            "identity_decision": canonical.REVISION_DECISION_ID,
            "provider": provider.key, "model": provider.model, "dialect": provider.dialect,
            "provider_reference_limit": int(provider.reference_images),
            "references": refs, "transmitted": carried,
            "complete_pack_transmitted": carried == len(refs)}
    body["package_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    body["note"] = (
        "Derived from the canonical revision only. A render conditioned with this package "
        "proves the bytes left through `gateway.images.conditioning_receipt`; this file says, "
        "before any call, which bytes those must be. Not publication approval: Laura's "
        "customer-facing gates are unchanged (identity, photorealism, anatomy, Product Truth, "
        "brand QA, disclosure, publication)")
    if not body["complete_pack_transmitted"]:
        body["limitation"] = (
            f"the {provider.dialect} dialect carries {carried} of {len(refs)} references, so "
            f"only {', '.join(r['frame'] for r in refs[:carried])} conditions a render; the "
            f"body dimensions are then judged on the output, never assumed held")
    return body


def path_for(provider_key: str) -> Path:
    from . import canonical

    return _root() / canonical.IDENTITY_ID / f"{provider_key}.json"


def write_all() -> list[str]:
    """Build and store every identity-lock provider's package. Returns the paths written."""
    out = []
    for key in lock_providers():
        p = path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(package(key), indent=1, sort_keys=True) + "\n")
        out.append(str(p))
    return out


def verify_stored(provider_key: str) -> dict:
    """The stored package against a fresh derivation from the canonical files."""
    p = path_for(provider_key)
    if not p.is_file():
        return {"ok": False, "provider": provider_key, "problems": ["no stored package"]}
    try:
        stored = json.loads(p.read_text())
    except ValueError as exc:
        return {"ok": False, "provider": provider_key, "problems": [f"unreadable: {exc}"]}
    try:
        fresh = package(provider_key)
    except ConditioningRefused as exc:
        return {"ok": False, "provider": provider_key, "problems": [str(exc)]}
    problems = [f"{k}: stored {stored.get(k)!r} != derived {fresh.get(k)!r}"
                for k in ("version", "identity_id", "provider", "dialect", "references",
                          "transmitted", "package_sha256") if stored.get(k) != fresh.get(k)]
    return {"ok": not problems, "provider": provider_key, "problems": problems,
            "package_sha256": fresh["package_sha256"]}


def registry() -> dict:
    """Every identity-lock provider's package status, for the canonical asset registry."""
    rows = [verify_stored(k) for k in lock_providers()]
    return {"identity": __import__("brambleloop.visual.canonical",
                                   fromlist=["IDENTITY_ID"]).IDENTITY_ID,
            "providers": rows, "ok": bool(rows) and all(r["ok"] for r in rows)}
