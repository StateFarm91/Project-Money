"""F-733 Canonical Asset Registry: one resolver for the current approved canonical model (W4-C08).

"Maintain versioned canonical model reference assets, identity specification, hashes,
provenance, approved views and provider-specific conditioning packages. Agents must resolve the
current approved canonical version from this registry rather than from chat memory."

Each part already existed in its own place, and this module does not copy any of them:
* the version and its history -- `visual.canonical` (`IDENTITY_ID`, `REVISIONS`, the owner
  decisions that authorise each change);
* reference assets with hashes and provenance -- `visual/assets/MANIFEST.json`, verified byte
  for byte by `canonical.verify`;
* the identity specification -- `canonical.LOCKED` / `IDENTITY_RULE`;
* provider conditioning packages -- `visual.conditioning` (`verify_stored` re-derives each one);
* the owner's approval, held by the repository -- `visual.approval_record`.

What was missing is the single door. `resolve(db=None)` joins them into ONE record and states
whether it is whole; `require_current()` returns that record or raises `CanonRefused`, so a
caller that resolves Laura gets the verified current version or nothing -- never a remembered
hash, a stale revision or a frame whose bytes changed. Read-only, deterministic, CA$0.
"""
from __future__ import annotations

REGISTRY_VERSION = "canonical-registry/1"


def _views(entries: list[dict], identity_id: str, want: dict[str, str]) -> dict:
    from . import canonical

    out = {}
    for frame, sha in want.items():
        e = next((x for x in entries if x.get("role") == "canonical_reference_pack"
                  and x.get("identity_id") == identity_id and x.get("frame") == frame), None)
        path = canonical.reference_file(frame)
        out[frame] = {"sha256": sha, "file": (e or {}).get("file"),
                      "dimensions": (e or {}).get("dimensions"),
                      "provenance": (e or {}).get("provenance"),
                      "hash_verified": bool(path),
                      "approved": bool(e) and e.get("sha256") == sha}
    return out


def resolve(db=None) -> dict:
    """The current approved canonical model, assembled from the authoritative sources."""
    from . import canonical, conditioning

    problems: list[str] = []
    try:
        m = canonical.manifest()
        entries = canonical.all_entries(m)
    except canonical.CanonRefused as exc:
        return {"registry": REGISTRY_VERSION, "ok": False, "problems": [str(exc)],
                "identity_id": None}
    check = canonical.verify(m)
    problems += [f"manifest: {p}" for p in check["problems"]]
    current = [r for r in canonical.REVISIONS if r["status"] == "current"]
    if len(current) != 1 or current[0]["identity_id"] != canonical.IDENTITY_ID:
        problems.append("exactly one current revision naming IDENTITY_ID is required")
    views = _views(entries, canonical.IDENTITY_ID, canonical.CURRENT_REFERENCE_HASHES)
    problems += [f"view {f}: bytes not verified" for f, v in views.items()
                 if not (v["hash_verified"] and v["approved"])]
    try:
        cond = conditioning.registry()
    except Exception as exc:  # noqa: BLE001 - an unreadable package is a problem, not a pass
        cond = {"ok": False, "providers": [], "why": f"{type(exc).__name__}: {exc}"[:200]}
    if not cond.get("ok"):
        problems.append("conditioning packages: not every lock provider's package verifies")
    approval = None
    if db is not None:
        from . import approval_record

        approval = approval_record.compare(db)
        if approval.get("state") in ("MISMATCH", "UNREADABLE"):
            problems.append(f"approval record: {approval['state']}")
    return {
        "registry": REGISTRY_VERSION, "ok": not problems, "problems": problems,
        "identity_id": canonical.IDENTITY_ID, "name": canonical.IDENTITY_NAME,
        "revision": canonical.REVISION_NUMBER, "decision": canonical.REVISION_DECISION_ID,
        "decisions": list(canonical.IDENTITY_DECISIONS),
        "history": [dict(r) for r in canonical.REVISIONS],
        "specification": {"locked": list(canonical.LOCKED), "rule": canonical.IDENTITY_RULE},
        "approved_views": views,
        "conditioning_packages": {r["provider"]: {"ok": r["ok"],
                                                  "package_sha256": r.get("package_sha256")}
                                  for r in cond.get("providers") or []},
        "approval_record": approval,
        "how_to_change": ("only an owner decision listed in canonical.AUTHORISED_IDENTITY_CHANGES "
                          "and model_registry.replace_canonical; never by editing this record"),
    }


def require_current(db=None) -> dict:
    """The verified current canonical record, or `CanonRefused` -- never a guess."""
    from . import canonical

    rec = resolve(db)
    if not rec["ok"]:
        raise canonical.CanonRefused("the canonical asset registry does not verify: "
                                     + "; ".join(rec["problems"])[:600])
    return rec


def current_identity_id(db=None) -> str:
    """The id an agent stamps on work for Laura, resolved -- not remembered."""
    return require_current(db)["identity_id"]
