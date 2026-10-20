"""Durable customer deliverables: a paid download never resolves to nothing (W4-FIRSTSALE B5).

The artifact store writes to a container filesystem a redeploy reclaims, and says so
(`core.artifacts.ArtifactStore.durable` is False). Production's daily rollback rehearsal found
every recorded PDF and frame of every listed release "not on disk" (2026-10-20, 8 of 8 per
release), so `deliverables_restorable` failed and the first-customer gate's
`fulfilment_and_download` failed with it.

The smallest durable design, using what already exists:

1. **Postgres holds the certified bytes.** `core.models.DurableArtifact` (sha256 primary key,
   payload) is already in production's schema, already restored by the offsite continuity
   archive, and already what `ArtifactStore.get(sha, db=db)` falls back to when a file is gone.
   `assets.build` now keeps every certified PDF (both terminologies) and every stored listing
   frame there. Bounded: one row per distinct hash, a few MB per release.
2. **Re-render is a fallback that must reproduce the certified bytes.** A certified PDF that is
   neither on disk nor in Postgres is re-rendered from the certified CIR with the release date
   pinned (`released_on` = the release row's creation date), the calibration and the lesson
   links `assets.build` used. It is accepted only if its sha256 equals the certified one, and
   is then kept. Anything else is `DeliveryRefused`: the buyer is never handed a file nobody
   certified, and never handed nothing silently.

`secure_release` brings an already-built release up to that standard (keeps from disk, or
re-renders byte-identically); `durable_state` is what the gates read. Nothing here contacts a
provider, publishes or spends.
"""
from __future__ import annotations

import hashlib

SECURED_ACTION = "deliverables.secured"
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


class DeliveryRefused(RuntimeError):
    """No byte-identical certified file can be produced. Never serve anything else."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def keep_why(slug: str, version: str, what: str) -> str:
    return f"certified customer deliverable {slug}@{version} {what}"[:200]


def held(db, sha256: str) -> bool:
    """True only when Postgres holds bytes that hash to `sha256` (read back, not assumed)."""
    from ..core.models import DurableArtifact

    try:
        with db.session() as s:
            row = s.get(DurableArtifact, sha256)
            return row is not None and _sha(bytes(row.payload)) == sha256
    except Exception:  # noqa: BLE001 - unreadable is not held
        return False


def keep(db, payload: bytes, content_type: str, why: str) -> bool:
    """Write the bytes to Postgres (idempotent on the hash); True when read back."""
    from ..core.artifacts import _keep

    return bool(_keep(db, _sha(payload), payload, content_type, why)) and held(db, _sha(payload))


def certified(db, slug: str, version: str, release: str = "") -> dict:
    """The hashes this release certified: {"pdfs": {terminology: sha}, "frames": [sha]}."""
    from sqlalchemy import select

    from ..core.models import ListingAsset
    from ..runtime.pipeline import _certified_pdf_hashes

    pdfs = _certified_pdf_hashes(db, slug, version, release) or {}
    with db.session() as s:
        frames = sorted({r.sha256 for r in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version)) if r.sha256})
    return {"pdfs": dict(pdfs), "frames": frames}


def render_certified_pdfs(db, slug: str, version: str) -> dict[str, bytes]:
    """Re-render both documents exactly as `assets.build` did: certified CIR, stored
    calibration, lesson links, and the release date pinned to the release row."""
    from sqlalchemy import select

    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.twin import build_twin
    from ..core.models import PatternVersion, Product
    from ..learn.service import pdf_help_links
    from ..publish.pdf import TERMINOLOGIES, build_pattern_pdf
    from ..quality.physical import calibration_from_db

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id,
            PatternVersion.version == version)) if product is not None else None
        if pv is None or not pv.certified:
            raise DeliveryRefused(f"{slug}@{version} has no certified release to re-render")
        cir = CIR.from_dict(pv.cir_json)
        released_on = pv.created_at.date() if pv.created_at else None
    if released_on is None:
        raise DeliveryRefused(f"{slug}@{version} has no release date to pin; a re-render "
                              "would print today's date and cannot be the certified file")
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(db, cir))
    links = pdf_help_links(db, cir.to_dict())
    return {t: build_pattern_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                 lesson_links=links).pdf_bytes for t in TERMINOLOGIES}


def resolve_pdf(db, slug: str, version: str, terminology: str = "US", *, release: str = "",
                store=None, render=None) -> dict:
    """The certified PDF's bytes, or `DeliveryRefused`. Never a different file, never None.

    Order: disk -> Postgres -> byte-identical re-render (then kept). `render` is injectable
    for tests; it defaults to `render_certified_pdfs`.
    """
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    want = certified(db, slug, version, release)["pdfs"].get(terminology)
    if not want:
        raise DeliveryRefused(f"no certified {terminology} PDF hash is on record for "
                              f"{slug}@{version}; nothing can be shown to be the sold file")
    store = store or ArtifactStore()
    try:
        data = store.get(want, db=db)
        source = "disk" if not held(db, want) else "durable"
    except ArtifactMissing:
        data, source = None, ""
    if data is None:
        rendered = (render or render_certified_pdfs)(db, slug, version).get(terminology)
        if rendered is None or _sha(rendered) != want:
            raise DeliveryRefused(
                f"the {terminology} PDF of {slug}@{version} is not stored and a re-render "
                f"from the certified CIR is {_sha(rendered)[:12] if rendered else 'absent'}, "
                f"not the certified {want[:12]}: refused rather than serving another file")
        keep(db, rendered, "application/pdf", keep_why(slug, version, f"pdf:{terminology}"))
        data, source = rendered, "re-render (byte-identical to the certified sha256)"
    elif not held(db, want):
        keep(db, data, "application/pdf", keep_why(slug, version, f"pdf:{terminology}"))
    if _sha(data) != want:  # pragma: no cover - the store verifies; defence in depth
        raise DeliveryRefused(f"{slug}@{version} {terminology}: bytes do not match")
    return {"bytes": data, "sha256": want, "source": source, "terminology": terminology}


def secure_release(db, slug: str, version: str, *, store=None, render=None,
                   audit: bool = True) -> dict:
    """Make every certified deliverable of one release durable, or say exactly what is not.

    PDFs: kept from disk, or re-rendered byte-identically and kept, or refused. Frames: kept
    from disk when present (frames are re-made by the next `assets.build`, which keeps them).
    """
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    store = store or ArtifactStore()
    want = certified(db, slug, version)
    pdfs, frames = {}, {}
    for t, sha in sorted(want["pdfs"].items()):
        try:
            got = resolve_pdf(db, slug, version, t, store=store, render=render)
            pdfs[t] = {"sha256": sha, "held": held(db, sha), "source": got["source"]}
        except DeliveryRefused as exc:
            pdfs[t] = {"sha256": sha, "held": False, "refused": str(exc)[:300]}
    try:
        from ..runtime.etsy_ops import certified_frames

        listing_set = [str(f.get("sha256") or "") for f in
                       certified_frames(db, slug, version)["frames"]]
    except Exception:  # noqa: BLE001 - no certificate: nothing more to keep
        listing_set = []
    for sha in sorted(set(want["frames"]) | {x for x in listing_set if x}):
        if held(db, sha):
            frames[sha] = True
            continue
        try:
            data = store.get(sha)
            frames[sha] = keep(db, data, "image/png", keep_why(slug, version, "frame"))
        except ArtifactMissing:
            frames[sha] = False
    out = {"slug": slug, "version": version, "pdfs": pdfs,
           "frames_held": sum(frames.values()), "frames": len(frames),
           "frames_missing": [s[:12] for s, ok in frames.items() if not ok][:8],
           "ok": bool(pdfs) and all(p["held"] for p in pdfs.values()) and bool(frames)
           and all(frames.values())}
    if audit:
        from ..core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor="orchestrator", action=SECURED_ACTION,
                           artifact=f"{slug}@{version}", detail=out))
    return out


def keep_frames(db, shas, *, slug: str, version: str, store=None) -> dict:
    """Keep certified listing-image bytes from disk in Postgres (the uploaded image set).

    Called when a listing-set certificate is issued: the gallery supplements and CONTENTS
    frame are certified by hash but stored only on the ephemeral disk, so after a redeploy
    `etsy_ops.certified_images` could not read them and publication would refuse. Never
    raises; returns {sha: held}."""
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    store = store or ArtifactStore()
    out = {}
    for sha in [s for s in shas if s]:
        try:
            if held(db, sha):
                out[sha] = True
                continue
            out[sha] = keep(db, store.get(sha), "image/png",
                            keep_why(slug, version, "certified listing image"))
        except (ArtifactMissing, Exception):  # noqa: BLE001 - reported, never fatal
            out[sha] = False
    return out


def restorable(db, sha256: str, store=None) -> bool:
    """On disk under its hash, or held in Postgres -- either is re-servable as the same bytes."""
    if store is not None and store.exists(sha256):
        return True
    return db is not None and held(db, sha256)


def durable_state(db, slug: str, version: str) -> dict:
    """PASS when every certified PDF of this release is held in Postgres; FAIL when one is
    not; UNKNOWN when nothing certifies a PDF for it (never read as PASS)."""
    try:
        want = certified(db, slug, version)["pdfs"]
    except Exception as exc:  # noqa: BLE001
        return {"state": UNKNOWN, "why": f"unreadable: {type(exc).__name__}: {exc}"[:240]}
    if not want:
        return {"state": UNKNOWN, "why": f"no certified PDF hash is recorded for {slug}@{version}"}
    missing = sorted(t for t, sha in want.items() if not held(db, sha))
    if missing:
        return {"state": FAIL, "pdfs": want, "missing": missing,
                "why": (f"certified {missing} PDF(s) of {slug}@{version} are not held in "
                        "Postgres; deliverables.secure_release keeps them or refuses")}
    return {"state": PASS, "pdfs": want,
            "why": (f"both certified PDFs of {slug}@{version} are held in Postgres "
                    "(durable_artifacts) under their sha256")}


# ---- purchase -> download rehearsal (shadow; no Etsy call) --------------------------------

def delivery_links(receipt: dict, listings: dict) -> list[dict]:
    """The delivery links one paid receipt owes, per digital line and per terminology.

    `receipt` is shaped as Etsy's ShopReceipt (receipt_id, is_paid/status, transactions[]
    with transaction_id, listing_id, is_digital). `listings` maps an Etsy listing id to the
    release it sells, `(slug, version)`, as the Listing row's `etsy_listing_id` does once a
    listing exists. A link is an internal reference resolved by `resolve_pdf`, never a public
    URL: the certified bytes it resolves to are what the Etsy upload carries and what a
    support redelivery sends. Unpaid receipts and non-digital lines owe nothing.
    """
    from ..publish.pdf import TERMINOLOGIES

    paid = bool(receipt.get("is_paid")) or str(receipt.get("status", "")).lower() in (
        "paid", "completed")
    if not paid:
        return []
    out = []
    for tx in receipt.get("transactions") or []:
        if not tx.get("is_digital"):
            continue
        rel = listings.get(str(tx.get("listing_id")))
        for t in TERMINOLOGIES:
            out.append({"receipt_id": receipt.get("receipt_id"),
                        "transaction_id": tx.get("transaction_id"),
                        "listing_id": tx.get("listing_id"),
                        "release": f"{rel[0]}@{rel[1]}" if rel else None,
                        "terminology": t,
                        "href": (f"deliverable:{rel[0]}@{rel[1]}/{t}" if rel else None)})
    return out


def rehearse_purchase(db, receipt: dict, listings: dict, *, store=None, render=None) -> dict:
    """Receipt -> delivery link -> bytes -> sha256 equal to the certified PDF. PASS only when
    every owed file resolves to its certified bytes; an unmapped line or a refusal is FAIL."""
    links = delivery_links(receipt, listings)
    files = []
    for link in links:
        row = {k: link[k] for k in ("transaction_id", "listing_id", "release", "terminology",
                                    "href")}
        if link["release"] is None:
            files.append({**row, "state": FAIL, "why": "the line maps to no release"})
            continue
        slug, version = link["release"].split("@", 1)
        want = certified(db, slug, version)["pdfs"].get(link["terminology"])
        try:
            got = resolve_pdf(db, slug, version, link["terminology"], store=store,
                              render=render)
        except DeliveryRefused as exc:
            files.append({**row, "state": FAIL, "certified_sha256": want,
                          "why": str(exc)[:300]})
            continue
        sha = _sha(got["bytes"])
        ok = bool(want) and sha == want and got["bytes"][:5] == b"%PDF-"
        files.append({**row, "state": PASS if ok else FAIL, "certified_sha256": want,
                      "served_sha256": sha, "bytes": len(got["bytes"]),
                      "source": got["source"]})
    return {"receipt_id": receipt.get("receipt_id"), "links": len(links),
            "state": (PASS if files and all(f["state"] == PASS for f in files) else FAIL),
            "files": files, "etsy_called": False}
