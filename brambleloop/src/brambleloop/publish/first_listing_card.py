"""ENG-ETSY-PUBLISH slice 2: ONE owner card, "Approve first public listing (step-up)".

The first public listing is a publication and a spend (Etsy's US$0.20 listing fee), so it is a
genuine exception under D-OWNER-STANDING-INTERNAL: the owner approves it as a step-up act
(Approvals tab, activation card, `activation.preview` then `activation.approve` then
`activation.execute`). No standing grant covers it while `STAGE_A_ENABLED` is False, and
nothing here grants, signs or activates anything.

This module keeps exactly one OwnerAction for it (`CARD_KEY`), naming the exact listing and
carrying its evidence. **The card is never raised with empty evidence.** It exists only while:

* no listing is live on Etsy yet (a first listing, not the next one);
* a Launch-0 release has a verified Etsy draft (`listing_state.PUBLISHED`, with an id);
* that draft's latest `store.published` row has a clean read-back (fields, files and
  images verified);
* both certified PDF hashes are on record and every image rank's sent hash matched the
  listing-set certificate;
* the publication gate readings are attached, section by section, PASS or not.

If any piece is missing, no card is raised, and an open one is withdrawn with the missing
pieces named. Once a listing is live, the card closes as satisfied. The full evidence is kept
in an audit row (`first_listing.card_evidence`), and the card's text cites that row and states
the hashes and gate results.
"""
from __future__ import annotations

from sqlalchemy import desc, select

CARD_KEY = "first_public_listing:approve"
TITLE = "Approve first public listing (step-up)"
EVIDENCE_ACTION = "first_listing.card_evidence"
#: The runbook's order (first_listing_runbook.md §1); other Launch-0 releases follow.
PREFERENCE = ("hexagonal-bread-basket", "hexagon-coaster-set", "nordic-star-ornaments",
              "winter-village-graphghan", "cloudline-baby-blanket")


def _candidates(db) -> list[dict]:
    from ..core.listing_state import PUBLISHED
    from ..core.models import Listing
    from ..products.launch0 import LAUNCH0_SLUGS

    with db.session() as s:
        rows = list(s.scalars(select(Listing).where(
            Listing.product_slug.in_(tuple(LAUNCH0_SLUGS)),
            Listing.state == PUBLISHED, Listing.etsy_listing_id != "")))
        out = [{"slug": r.product_slug, "version": r.version, "release": r.release_hash or "",
                "etsy_listing_id": str(r.etsy_listing_id), "title": r.title,
                "price_cad": r.price_cad} for r in rows if r.etsy_listing_id]
    rank = {s: i for i, s in enumerate(PREFERENCE)}
    return sorted(out, key=lambda c: (rank.get(c["slug"], len(rank)), c["slug"]))


def _live_count(db) -> int:
    from ..core.models import Listing

    with db.session() as s:
        # Live: activated through the gated path, or made by hand and adopted. A verified
        # draft (`PUBLISHED`) is not public.
        from ..core.listing_state import PUBLISHED_MANUALLY

        return len(list(s.scalars(select(Listing.id).where(
            Listing.state.in_(("active", PUBLISHED_MANUALLY))))))


def _published_row(db, c) -> dict | None:
    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == "store.published",
                AuditLog.artifact == f"{c['slug']}@{c['version']}")
                .order_by(desc(AuditLog.id)).limit(20)):
            d = dict(row.detail or {})
            if str(d.get("etsy_listing_id") or "") == c["etsy_listing_id"]:
                return {"audit_id": row.id, **d}
    return None


def evidence(db, c: dict) -> tuple[dict, list[str]]:
    """The card's evidence for one candidate, and what is missing (empty = complete)."""
    from ..finance import listing_costs
    from ..ops import publication_authority as pa
    from ..runtime.pipeline import _certified_pdf_hashes

    missing: list[str] = []
    pub = _published_row(db, c)
    rb = (pub or {}).get("read_back") or {}
    images = rb.get("images") or {}
    by_rank = list(images.get("by_rank") or [])
    readback = {"audit_id": (pub or {}).get("audit_id"), "verified": rb.get("verified"),
                "fields_verified": (rb.get("fields") or {}).get("verified"),
                "files_verified": (rb.get("files") or {}).get("verified"),
                "images_verified": images.get("verified"),
                "files_on_etsy": [{"file": f.get("file"), "size_on_etsy": f.get("size_on_etsy"),
                                   "sent_sha256": f.get("sent_sha256"),
                                   "certified": f.get("certified")}
                                  for f in (rb.get("files") or {}).get("files") or []]}
    if pub is None:
        missing.append("no store.published row for this draft")
    elif not rb.get("verified"):
        missing.append("the draft's read-back is not verified")
    pdfs = _certified_pdf_hashes(db, c["slug"], c["version"], c["release"]) or {}
    if set(pdfs) != {"US", "UK"}:
        missing.append(f"certified PDF hashes on record: {sorted(pdfs)} (both US and UK needed)")
    images_hashes = [{"rank": r.get("rank"), "sha256": r.get("sent_sha256"),
                      "matches_certificate": r.get("hash_matches_certificate")}
                     for r in by_rank]
    if not images_hashes or not all(r["matches_certificate"] for r in images_hashes):
        missing.append("image hashes by rank are absent or do not all match the certificate")
    try:
        ev = pa.evidence(db, c["slug"], c["version"], c["release"])
        gates = {k: str((ev.get(k) or {}).get("state") or pa.UNKNOWN) for k in pa.GATED_SECTIONS}
    except Exception as exc:  # noqa: BLE001 - an unreadable gate set is missing evidence
        gates = {}
        missing.append(f"publication gates unreadable: {type(exc).__name__}")
    if not gates:
        missing.append("no publication gate results")
    budget = listing_costs.opening_budget(db)
    return ({"listing": c, "readback": readback,
             "hashes": {"pdfs": pdfs, "images": images_hashes},
             "gates": gates, "gates_all_pass": bool(gates) and all(
                 v == pa.PASS for v in gates.values()),
             "fee": {"per_listing_cap_cad": listing_costs.per_listing_cap_cad(),
                     "usd": listing_costs.PER_LISTING_FEE_USD,
                     "opening_budget_remaining_cad": budget["remaining_cad"]}},
            missing)


def _reason(ev: dict, audit_id: int) -> str:
    c, h, g = ev["listing"], ev["hashes"], ev["gates"]
    gates = ", ".join(f"{k} {v}" for k, v in sorted(g.items()))
    not_pass = sorted(k for k, v in g.items() if v != "PASS")
    return (f"Make {c['slug']}@{c['version']} (Etsy draft {c['etsy_listing_id']}, "
            f"\"{c['title']}\", CA${float(c['price_cad'] or 0):.2f}) the shop's first public "
            f"listing. Release {c['release'][:12]}. Read-back verified (audit "
            f"{ev['readback']['audit_id']}): fields, both PDFs and {len(h['images'])} images. "
            f"PDF sha256 US {h['pdfs'].get('US', '')[:12]}, UK {h['pdfs'].get('UK', '')[:12]}; "
            f"every image rank's sent sha256 matches the listing-set certificate. Gates: "
            f"{gates}." + (f" Not passing: {', '.join(not_pass)}; activation refuses until "
                           f"they pass, whatever is approved." if not_pass else "")
            + f" Fee US${ev['fee']['usd']:.2f} (≤ CA${ev['fee']['per_listing_cap_cad']:.2f}) "
            f"from the CA$6 opening budget (CA${ev['fee']['opening_budget_remaining_cad']:.2f} "
            f"left). Full evidence: audit {audit_id}. Approve in Approvals > activation card "
            f"(preview, approve with step-up, execute).")


def refresh(db) -> dict:
    """Keep the one card in step with the evidence. Idempotent; writes no grant."""
    from ..core.models import AuditLog, OwnerAction
    from ..ops import owner_queue

    with db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == CARD_KEY, OwnerAction.done == False))  # noqa: E712
        open_id = open_row.id if open_row is not None else None
    if _live_count(db):
        if open_id is not None:
            with db.session() as s:
                owner_queue.close(s.get(OwnerAction, open_id), owner_queue.SATISFIED,
                                  "a listing is live on Etsy: the first public listing exists")
        return {"state": "satisfied" if open_id else "none", "why": "a listing is live"}
    chosen, why_not = None, []
    for c in _candidates(db):
        ev, missing = evidence(db, c)
        if not missing:
            chosen = ev
            break
        why_not.append({"release": f"{c['slug']}@{c['version']}", "missing": missing[:5]})
    if chosen is None:
        if open_id is not None:
            with db.session() as s:
                owner_queue.close(s.get(OwnerAction, open_id), owner_queue.WITHDRAWN,
                                  "no verified draft has complete evidence: "
                                  + "; ".join(m for w in why_not for m in w["missing"])[:400])
        return {"state": "withdrawn" if open_id else "none", "not_ready": why_not}
    with db.session() as s:
        audit = AuditLog(actor="orchestrator", action=EVIDENCE_ACTION,
                         artifact=f"{chosen['listing']['slug']}@{chosen['listing']['version']}",
                         detail=chosen)
        s.add(audit)
        s.flush()
        fields = dict(reason=_reason(chosen, audit.id),
                      max_cost_cad=chosen["fee"]["per_listing_cap_cad"], minutes=5,
                      consequence_of_delay=("the shop has no public listing, so nothing can "
                                            "sell; the verified draft waits on Etsy and is "
                                            "read back again before activation"),
                      blocks="first sale",
                      why_software_cannot=("publication and its fee are the owner's step-up "
                                           "act; no standing grant covers them "
                                           "(STAGE_A_ENABLED is False) and software never "
                                           "grants itself"))
        row = owner_queue.ensure(s, CARD_KEY, action=TITLE, **fields)
        for k, v in fields.items():
            setattr(row, k, v)
        row.action = TITLE
        row_id, audit_id = row.id, audit.id
    return {"state": "raised", "id": row_id, "evidence_audit": audit_id,
            "listing": chosen["listing"], "gates": chosen["gates"]}
