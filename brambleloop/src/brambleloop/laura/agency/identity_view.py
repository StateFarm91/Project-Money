"""Who is answering: Laura's identity as the Command Center shows it (read-only).

Lane D owns `brambleloop.laura.identity` (canonical identity record, charter, voice spec,
authority). This module only *reads* it, and tolerates its absence: when lane D's module is
not merged, the identity falls back to the owner-ruled constants already in
`visual.canonical` (D-FB-11..13) -- the same identity id, role and truthfulness rule, never a
new or invented identity. Nothing here can change Laura's identity.
"""
from __future__ import annotations

from typing import Any

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


def _call(mod, *names) -> Any:
    for n in names:
        v = getattr(mod, n, None)
        if v is None:
            continue
        try:
            return v() if callable(v) else v
        except TypeError:
            continue
        except Exception:  # noqa: BLE001 - a broken peer reader falls back below
            return None
    return None


def identity() -> dict:
    """{identity_id, name, role, public_identity, truthful_identity, authority, voice, source}."""
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
            "model_independent": True}
    try:
        import importlib

        mod = importlib.import_module("brambleloop.laura.identity")
    except ImportError:
        return base
    rec = _call(mod, "canonical_record", "record", "identity", "canonical", "IDENTITY",
                "CANONICAL")
    out = dict(base)
    out["source"] = "brambleloop.laura.identity"
    if isinstance(rec, dict):
        for k in ("identity_id", "name", "role", "public_identity", "truthful_identity"):
            if rec.get(k):
                out[k] = rec[k]
        # The visual identity id is owner-locked (D-FB-11). If the record names a different
        # one, the canonical constant wins and the disagreement is reported, never adopted.
        vis = rec.get("visual_identity_id") or rec.get("identity_id")
        if vis and vis != canonical.IDENTITY_ID and str(vis).startswith("laura-v"):
            out["identity_id"] = canonical.IDENTITY_ID
            out["identity_disagreement"] = str(vis)
    auth = _call(mod, "authority", "AUTHORITY")
    if isinstance(auth, dict):
        out["authority"] = auth
    voice = _call(mod, "voice_spec", "voice", "VOICE", "VOICE_SPEC")
    if isinstance(voice, dict):
        # Only the business/public register is shown here; a private register is never read.
        out["voice"] = {k: v for k, v in voice.items()
                        if "private" not in str(k).lower() and "spous" not in str(k).lower()}
    return out


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
