"""Who is answering: Laura's identity as the Command Center shows it (read-only).

Lane D owns `brambleloop.laura.identity` (canonical identity record, charter, voice spec,
authority). This module only *reads* it, and tolerates its absence: when lane D's module is
not merged, the identity falls back to the owner-ruled constants already in
`visual.canonical` (D-FB-11..13) -- the same identity id, role and truthfulness rule, never a
new or invented identity. Nothing here can change Laura's identity.
"""
from __future__ import annotations

# Laura's authority in a business conversation (spec/07 item 11, D-FB-13): what she may do
# herself, and what stays with the owner. The follow-on code enforces this; the text is shown.
AUTHORITY_FALLBACK = {
    "may": ["analyse", "review", "recommend", "draft",
            "create internal GREEN follow-on work through the COO orchestrator"],
    "may_not": ["publish or change live Etsy listings", "spend beyond granted authority",
                "change Product Truth or financial truth", "fabricate evidence",
                "weaken gates", "change her canonical identity", "expand her own authority"],
    "challengers": ["Finance", "Product Truth", "Security"],
}


def identity(db=None) -> dict:
    """{identity_id, name, role, public_identity, truthful_identity, authority, voice, source}.

    With lane D merged: `laura.identity.public_profile()` (nothing owner-private in it) and
    `AUTHORITY`, and -- given `db` -- the *verified* durable record's version and sha256 via
    `laura.identity.summary(db)` (a tampered record reports BLOCKED, never a silent pass)."""
    from ...visual import canonical

    base = {"identity_id": canonical.IDENTITY_ID, "name": canonical.IDENTITY_NAME,
            "role": canonical.ROLE, "public_identity": canonical.PUBLIC_IDENTITY,
            "truthful_identity": canonical.TRUTHFUL_IDENTITY,
            "rulings": list(canonical.IDENTITY_DECISIONS),
            "authority": AUTHORITY_FALLBACK,
            "voice": {"business": "warm, intelligent, confident, calm, concise; no fake "
                                  "enthusiasm, no invented personal experiences, no "
                                  "unsupported claims"},
            "source": "brambleloop.visual.canonical (lane D laura.identity not merged)",
            "sources": ["visual.canonical"], "verified": None,
            "model_independent": True}
    try:
        import importlib

        mod = importlib.import_module("brambleloop.laura.identity")
        prof = mod.public_profile()
    except Exception:  # noqa: BLE001 - ImportError or a broken peer: owner-ruled constants
        return base
    out = dict(base)
    out["source"] = "brambleloop.laura.identity"
    out["sources"] = ["laura.core.identity.GENESIS", "visual.canonical"]
    for k in ("name", "role", "public_identity", "truthful_identity"):
        if prof.get(k):
            out[k] = prof[k]
    if prof.get("kind"):
        out["role"] = f"{out['role']} ({prof['kind']})"
    # The visual identity id is owner-locked (D-FB-11). A record that names a different one
    # is reported as a disagreement; the canonical constant is kept.
    vis = prof.get("visual_identity_id")
    if vis and vis != canonical.IDENTITY_ID:
        out["identity_disagreement"] = str(vis)
    auth = getattr(mod, "AUTHORITY", None)
    if isinstance(auth, dict):
        out["authority"] = {k: auth[k] for k in ("may", "may_not") if k in auth}
    voice = prof.get("voice")
    if isinstance(voice, dict):
        out["voice"] = {k: v for k, v in voice.items()
                        if "private" not in str(k).lower() and "spous" not in str(k).lower()}
    if db is not None:
        try:
            summ = mod.summary(db)
        except Exception as exc:  # noqa: BLE001
            summ = {"status": "UNKNOWN", "reason": type(exc).__name__, "items": []}
        item = (summ.get("items") or [{}])[0] if summ.get("status") == "OK" else {}
        out["verified"] = {"status": summ.get("status"), "reason": summ.get("reason"),
                           "identity_version": item.get("identity_version"),
                           "identity_sha256": item.get("identity_sha256")}
        if item.get("identity_version"):
            out["sources"] = [f"laura_identity_versions:{item['identity_version']}",
                              *out["sources"]]
    return out


def voice_findings(text: str) -> list[dict]:
    """Lane D's deterministic voice check on a business answer, if merged (else [])."""
    try:
        from .. import identity as ident_mod

        return [{"rule": f.get("rule"), "match": f.get("match")}
                for f in ident_mod.voice_lint(text, surface="business")
                if f.get("rule") not in ("LINT_UNAVAILABLE",)]
    except Exception:  # noqa: BLE001
        return []


def portrait() -> dict:
    """The canonical portrait for the owner's Laura view: bytes + the label it must carry.

    Internal only. `store_foundation.brand_face.image_for(..., for_customers=False)` is the
    one place that hands out her portrait for owner previews; it labels it and refuses it for
    customers. If that module is unavailable the portrait is not shown (never substituted)."""
    from ...store_foundation import brand_face

    data, sha = brand_face.portrait_bytes()
    from ...visual import canonical

    return {"bytes": data, "sha256": sha, "identity_id": canonical.IDENTITY_ID,
            "status": canonical.asset_status(sha),
            "customer_ready": bool(canonical.customer_ready(sha).get("customer_ready")),
            "label": brand_face.PREVIEW_IMAGE_LABEL}
