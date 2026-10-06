"""Owner/operator-authenticated, content-bound *publication* authority (FB3-P).

The draft-creation counterpart of `activation_authority`. Before this module, the owner's
permission to create an Etsy draft was read only from the environment flag
`BRAMBLELOOP_PUBLISH_AUTHORISED=1`: no record of who granted it, for what, or until when.
A durable grant is now required at the pre-create boundary:

* **sealed** -- HMAC over the whole grant under the ops credential (`BRAMBLELOOP_OPS_TOKEN`),
  so an edited row, a hand-inserted row, or a credential rotation invalidates it;
* **scoped** -- bound to one `slug@version`, its certified release hash, the digest of the
  certified CIR and the exact listing fields that will be sent (taxonomy included);
* **expiring** -- 24 hours from approval, never future-dated;
* **revocable** -- a sealed revocation row bound to the grant's seal, checked at every use;
* **chained** (rc1-AUTH D2) -- approvals, revocations and owner rebases form one sealed hash
  chain (`core.sealed_chain.GrantLedger`). Deleting a revocation or inserting/replaying a row
  breaks it, which refuses every grant and opens a P1 tamper incident; an unsealed inserted
  revocation still revokes (fail closed) and is reported as tampering;
* **audited** -- approval and revocation are `AuditLog` rows under the owner principal.

The environment flag remains only as a global kill-switch: it can additionally DENY (unset
or anything but "1" refuses every publication) but can no longer grant on its own.

As with activation, the principal is the holder of the ops credential, not a separately
verified natural person. Nothing here contacts Etsy or enqueues a job.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..core import opsauth
from ..core.models import AuditLog, Listing, PatternVersion, Product

APPROVED = "owner.publication.approved"
REVOKED = "owner.publication.revoked"
REBASED = "owner.publication.rebased"
PRINCIPAL = "owner:ops-token"
ACTION = "store.publish"
KILL_SWITCH_VAR = "BRAMBLELOOP_PUBLISH_AUTHORISED"
GRANT_HOURS = 24


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _seal(detail):
    if not opsauth.configured():
        raise ValueError("owner credential unavailable")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(),
                    _json(detail).encode(), hashlib.sha256).hexdigest()


def digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def kill_switch_refusal() -> str | None:
    """The global environment switch: it may only deny."""
    if os.environ.get(KILL_SWITCH_VAR, "") != "1":
        return (f"global publication kill-switch is off ({KILL_SWITCH_VAR} is not '1'); "
                f"no grant can override it")
    return None


def snapshot(db, slug, version, release):
    """What a grant is bound to: the certified release and the exact fields to be sent."""
    from ..runtime import etsy_ops

    if not slug or not version or not release:
        raise ValueError("slug, version and certified release hash are required")
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if pv is None or not pv.certified or not pv.cir_json or pv.release_hash != release:
            raise ValueError("no certified release with that hash for this version")
        if listing is None or listing.release_hash != release:
            raise ValueError("no drafted listing bound to that certified release")
        if listing.etsy_listing_id:
            raise ValueError("already on Etsy; publication grants cover draft creation only")
        cir = pv.cir_json
    return {"action": ACTION, "slug": slug, "version": version, "release": release,
            "cir_digest": digest(cir),
            "payload": etsy_ops.sent_fields(etsy_ops.certified_payload(db, slug, version)),
            # F-704: the owner approves on evidence, and the evidence is part of what the
            # grant digest binds -- a change in any element below voids the grant.
            "evidence": evidence(db, slug, version, release)}


# ---- F-704: the approval packet's evidence --------------------------------------------------
#
# Every section has a `state`. Only PASS displays as passing; FAIL, UNKNOWN (never read, or
# unreadable) and the informational states (MODELLED / MEASURED for economics, DESCRIBED for the
# rollback path) never do. Nothing here writes, renders, enqueues or asks a model: every reading
# is of evidence already on file. Volatile readings (ages, "now" timestamps) are left out of the
# bound content so a grant is voided by a changed verdict, not by the clock ticking.

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
GATED_SECTIONS = ("certification", "parity", "listing_set", "disclosure", "policy", "search",
                  "rollback")


def _unknown(why: str) -> dict:
    return {"state": UNKNOWN, "why": str(why)[:300]}


def _guard(fn) -> dict:
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001 - an unreadable verdict is UNKNOWN, never PASS
        return _unknown(f"could not be read: {type(exc).__name__}: {str(exc)[:200]}")
    if not isinstance(out, dict) or out.get("state") not in (PASS, FAIL, UNKNOWN, "MODELLED",
                                                              "MEASURED", "DESCRIBED"):
        return _unknown("reader returned no recognisable state")
    return out


def _release_row(db, slug, version):
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(Listing.id.desc()).limit(1))
        return ((None if pv is None else {"certified": bool(pv.certified),
                                           "release_hash": pv.release_hash or "",
                                           "certificate": dict(pv.certificate or {})}),
                (None if listing is None else {"state": listing.state,
                                               "price_cad": listing.price_cad,
                                               "release_hash": listing.release_hash,
                                               "etsy_listing_id": listing.etsy_listing_id}))


def _certification(db, slug, version, release):
    from ..publish import withholding

    pv, _listing = _release_row(db, slug, version)
    if pv is None:
        return _unknown("no stored release for this version")
    cert = pv["certificate"]
    findings = [f for f in (cert.get("findings") or []) if isinstance(f, dict)]
    blocking = sorted({str(f.get("code")) for f in findings
                       if str(f.get("severity", "")).lower() in ("error", "blocker", "critical")})
    held = withholding.reasons(db, slug, version)
    granted = cert.get("granted") is True
    ok = (pv["certified"] and granted and pv["release_hash"] == release
          and cert.get("release_hash") in (None, release) and not held["withheld"])
    physical = ("not_required" if cert.get("physical_test_required") is False else
                "passed" if cert.get("physical_test_passed") is True else
                "required_not_passed" if cert.get("physical_test_required") else UNKNOWN)
    return {"state": PASS if ok else FAIL if cert else UNKNOWN,
            "certified": pv["certified"], "certificate_granted": granted,
            "release_matches": pv["release_hash"] == release,
            "content_hash": cert.get("content_hash"), "policy_version": cert.get("policy_version"),
            "stages_run": cert.get("stages_run"), "blocking_finding_codes": blocking,
            "physical_proof": physical, "withheld": held["withheld"],
            "withheld_reasons": held["publish_reasons"],
            "why": ("certificate granted for this release, nothing withheld" if ok else
                    "no certificate recorded" if not cert else
                    "release is not certified for this hash, or is withheld")}


def _parity(db, slug, version):
    """#75, read-only: the same assessment `_listing_parity` makes, without its escalations."""
    from ..creative import blind_review
    from ..publish import listing_asset
    from ..runtime.release import frame_review_state
    from ..visual import parity
    from ..visual.gallery import escalation_progress, gates_now

    frames = listing_asset.frames_for(db, slug=slug)
    try:
        verdict = parity.assess(
            frames, benchmark_quality=blind_review.current_review(db, slug=slug),
            deterministic_available=parity._deterministic_available(frames),
            gate_open=gates_now(db),
            start_attempt=escalation_progress(db, slug=slug, version=version)["start_attempt"])
    except parity.ParityRefused as exc:
        return {"state": FAIL, "verdict": parity.UNJUDGED, "dimensions": {},
                "unjudged": list(parity.DIMENSIONS), "failed": [], "why": str(exc)[:300]}
    dims = {d: (verdict.get("dimensions") or {}).get(d, {}).get("verdict", parity.UNJUDGED)
            for d in parity.DIMENSIONS}
    unjudged = sorted(d for d, v in dims.items() if v not in (parity.PASS, parity.FAIL))
    failed = sorted(d for d, v in dims.items() if v == parity.FAIL)
    review = frame_review_state(db, slug, version)
    ok = not unjudged and not failed and verdict.get("verdict") == parity.PASS and bool(
        review.get("reviewed"))
    return {"state": PASS if ok else FAIL if failed else UNKNOWN,
            "verdict": verdict.get("verdict"), "dimensions": dims, "unjudged": unjudged,
            "failed": failed, "frames_judged": len(frames),
            "frame_review": {"reviewed": bool(review.get("reviewed")),
                             "why": str(review.get("why") or "")[:300]},
            "why": ("every dimension passed and the frames were independently reviewed" if ok
                    else f"failed {failed}" if failed else
                    f"unjudged {unjudged}" if unjudged else
                    "frames not independently reviewed")}


def _listing_set(db, slug, version):
    from ..publish import release_gates

    out = release_gates.listing_set(db, slug=slug, version=version, issue=False)
    cert = out.get("certificate") or {}
    ok = out.get("blocks_release") is False and cert.get("valid") is True
    return {"state": PASS if ok else FAIL if out.get("frames") else UNKNOWN,
            "blocks_release": out.get("blocks_release"),
            "certificate": {k: cert.get(k) for k in ("valid", "record_id", "why")
                            if k in cert} if isinstance(cert, dict) else None,
            "frames": [{"position": f.get("position"), "may_export": f.get("may_export")}
                       for f in (out.get("frames") or [])],
            "reasons": [str(r)[:300] for r in (out.get("reasons") or [])][:12],
            "why": ("listing set certified" if ok else "listing set not certified")}, out


def _disclosure(db, slug, version):
    from ..commerce.buyer_trust import listing_disclosure_finding

    f = listing_disclosure_finding(db, slug=slug, version=version)
    if not f.get("checked"):
        return _unknown(f.get("why") or "disclosure UNMEASURED")
    ok = f.get("complete") is True
    return {"state": PASS if ok else FAIL, "complete": f.get("complete"),
            "missing": list(f.get("missing") or []), "misplaced": list(f.get("misplaced") or []),
            "why": "every owed disclosure is in the stored copy" if ok else
                   "an owed disclosure is missing or misplaced"}


def _policy(db):
    from ..gates.platform_policy import freshness

    f = freshness(db)
    if f["never_checked"]:
        state = UNKNOWN
    elif f["stale"] or f["changed_unreviewed"]:
        state = FAIL
    else:
        state = PASS if f["all_fresh"] else UNKNOWN
    return {"state": state,
            "current": sorted((e["source"], e["checked_on"], e["version"])
                              for e in f["current"]),
            "stale": sorted(e["source"] for e in f["stale"]),
            "never_checked": sorted(f["never_checked"]),
            "changed_unreviewed": sorted(f["changed_unreviewed"]),
            "max_age_days": f["max_age_days"],
            "why": ("every policy reading is fresh and reviewed" if state == PASS else
                    "a policy source has never been read" if state == UNKNOWN else
                    "a policy reading is stale or changed and unreviewed")}


def _search(db, slug, version, set_verdict):
    from ..publish import release_gates

    if set_verdict is None:
        return _unknown("listing set unreadable, so the hero check cannot be made")
    out = release_gates.search_gate(db, slug=slug, version=version, set_verdict=set_verdict)
    reasons = [str(r)[:300] for r in out.get("reasons") or []]
    if out.get("verdict") == "PASS" and out.get("ok") is True:
        state = PASS
    elif any("no search profile" in r for r in reasons):
        state = UNKNOWN
    else:
        state = FAIL
    return {"state": state, "verdict": out.get("verdict"),
            "category_status": out.get("category_status"),
            "taxonomy_id": out.get("taxonomy_id"), "reasons": reasons[:12],
            "why": "search certificate current" if state == PASS else
                   "no search certificate recorded" if state == UNKNOWN else
                   "search certificate refuses"}


def _economics(db, slug, version):
    """Price and per-sale economics, each figure carrying its basis."""
    from ..commerce import pricing
    from ..core.models import Order

    _pv, listing = _release_row(db, slug, version)
    price = (listing or {}).get("price_cad")
    if not price or float(price) <= 0:
        return _unknown("no positive listing price is stored for this release")
    breakdown = pricing.fees(float(price)).to_dict()
    with db.session() as s:
        try:
            orders = s.scalar(select(Order.id).where(Order.product_slug == slug).limit(1))
        except Exception:  # noqa: BLE001 - schema without the column reads as unmeasured
            orders = None
    return {"state": "MODELLED",
            "price_cad": round(float(price), 2), "price_basis": "measured",
            "price_source": "stored Listing.price_cad for this release",
            "fees_cad": breakdown["total_fees"], "net_per_sale_cad": breakdown["net_cad"],
            "fees_basis": "modelled",
            "fee_schedule": breakdown.get("fee_schedule"),
            "unmodelled_fees": breakdown.get("unmodelled_fees"),
            "sales_volume_basis": "measured" if orders else "unknown",
            "why": ("price is the stored listing price; fees and net are modelled from the "
                    "recorded fee schedule; sales volume is "
                    + ("measured from ingested orders" if orders else
                       "unknown -- no order has been ingested"))}


ROLLBACK_PATH = {
    "this_grant": ("covers draft creation only: an Etsy draft is never visible to buyers, so "
                   "no buyer can exist for it"),
    "remove_draft": ("EtsyClient.delete_listing(listing_id) -- reads the listing back first and "
                     "refuses unless Etsy reports it as draft or inactive"),
    "if_later_activated": ("activation is a separate owner grant (store.activate). To withdraw "
                           "a live listing the owner deactivates it in Etsy Shop Manager -- no "
                           "automated deactivation job exists in this system -- and the "
                           "release chain marks the local Listing 'withdrawn' (audited "
                           "listing.withdrawn); it is restored via "
                           "chain.rebuild from the retained release"),
    "buyers": ("deactivation does not reach buyers who already purchased; the shop's buyer "
               "copy tells them downloads stay under Etsy Purchases. That Etsy behaviour is "
               "UNKNOWN to this system (not verified); a correcting release prepares buyer "
               "notices that the owner sends"),
}


def _rollback(db, slug, version):
    from ..launch import rollback

    rec = rollback.latest(db, slug=slug, version=version)
    steps = [{"step": st.get("step"), "ok": st.get("ok")} for st in (rec or {}).get("steps") or []]
    state = (UNKNOWN if rec is None else PASS if rec.get("ok") is True else FAIL)
    return {"state": state, "path": ROLLBACK_PATH,
            "rehearsal": ({"ok": rec.get("ok"), "steps": steps} if rec else None),
            "rehearsal_max_age_days": rollback.MAX_AGE_DAYS,
            "why": ("withdrawal round trip rehearsed recently and every step held" if state == PASS
                    else "no rollback rehearsal within the last "
                         f"{rollback.MAX_AGE_DAYS} days" if rec is None else
                    "the latest rollback rehearsal found a failing step")}


def evidence(db, slug, version, release) -> dict:
    """The approval packet's evidence for one release. Never raises; UNKNOWN is never PASS."""
    out = {"certification": _guard(lambda: _certification(db, slug, version, release)),
           "parity": _guard(lambda: _parity(db, slug, version))}
    set_full = None
    try:
        summary, set_full = _listing_set(db, slug, version)
        out["listing_set"] = _guard(lambda: summary)
    except Exception as exc:  # noqa: BLE001
        out["listing_set"] = _unknown(f"could not be read: {type(exc).__name__}: "
                                      f"{str(exc)[:200]}")
    out["disclosure"] = _guard(lambda: _disclosure(db, slug, version))
    out["policy"] = _guard(lambda: _policy(db))
    out["search"] = _guard(lambda: _search(db, slug, version, set_full))
    out["economics"] = _guard(lambda: _economics(db, slug, version))
    out["rollback"] = _guard(lambda: _rollback(db, slug, version))
    not_passing = [k for k in GATED_SECTIONS if out[k]["state"] != PASS]
    out["summary"] = {"all_gated_sections_pass": not not_passing,
                      "not_passing": not_passing,
                      "unknown": [k for k in GATED_SECTIONS if out[k]["state"] == UNKNOWN],
                      "economics_basis": out["economics"]["state"]}
    return out


def display(evidence_: dict) -> list[dict]:
    """One line per section for the owner. Only a PASS state is shown as passing."""
    rows = []
    for key in GATED_SECTIONS + ("economics",):
        sec = evidence_.get(key) or _unknown("absent")
        rows.append({"section": key, "state": sec.get("state", UNKNOWN),
                     "passing": sec.get("state") == PASS, "why": sec.get("why", "")})
    return rows


def approve(db, *, authorization, slug, version, release, expected_digest, reason):
    """Record a sealed owner grant for exactly the previewed content."""
    opsauth.check(authorization)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    content = snapshot(db, slug, version, release)
    if not hmac.compare_digest(digest(content), str(expected_digest)):
        raise ValueError("approval preview changed; review the current content")
    now = _now()
    detail = {"principal": PRINCIPAL, "action": ACTION, "scope": f"{slug}@{version}",
              "release": release, "content": content, "digest": digest(content),
              "reason": reason.strip(), "approved_at": now.isoformat(),
              "expires_at": (now + timedelta(hours=GRANT_HOURS)).isoformat()}
    ident = LEDGER.append(db, action=APPROVED, artifact=f"{slug}@{version}", detail=detail)
    return {"approval_id": ident, "digest": detail["digest"],
            "expires_at": detail["expires_at"], "principal": PRINCIPAL}


def revoke(db, *, authorization, approval_id):
    opsauth.check(authorization)
    LEDGER.revoke(db, int(approval_id))
    return {"revoked": int(approval_id)}


def rebase(db, *, authorization, reason):
    """Owner re-anchors a broken grant chain. Voids every earlier publication grant."""
    opsauth.check(authorization)
    return {"rebase_id": LEDGER.rebase(db, reason), "voids_grants_before": True}


def _check_one(db, ident, *, slug, version, release, current):
    with db.session() as s:
        row = s.get(AuditLog, ident)
        if row is None or row.action != APPROVED or row.actor != PRINCIPAL:
            return "recorded owner publication grant required"
        if row.artifact != f"{slug}@{version}":
            return "owner publication grant is for another product or version"
        detail = dict(row.detail or {})
    chained = LEDGER.refusal(db, ident)
    if chained is not None:
        return f"owner publication grant refused: {chained}"
    seal = detail.pop("seal", "")
    if not hmac.compare_digest(str(seal), _seal(detail)):
        return "owner publication grant invalid or credential rotated"
    now = _now()
    if not (datetime.fromisoformat(detail["approved_at"]) <= now
            < datetime.fromisoformat(detail["expires_at"])):
        return "owner publication grant expired or future-dated"
    if (detail.get("action") != ACTION or detail.get("scope") != f"{slug}@{version}"
            or detail.get("release") != release):
        return "owner publication grant does not cover this release"
    if digest(current) != detail.get("digest"):
        return "owner publication grant does not match current content"
    return None


def _make_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED, principal=PRINCIPAL,
                       seal=_seal, signature=f"authority_chain_tamper:{ACTION}",
                       label="owner publication grant")


LEDGER = _make_ledger()


def resolve(db, *, slug, version, release, approval_id=None) -> tuple[str | None, int | None]:
    """(refusal, grant id). Fails closed; resolved anew at every execution boundary.

    With `approval_id` only that grant is considered. Without it, the newest grant recorded
    for `slug@version` that is valid now is used, so a queued store.publish need not carry an
    id -- but the grant must still bind this release and the content about to be sent.
    """
    try:
        deny = kill_switch_refusal()
        if deny:
            return deny, None
        current = snapshot(db, slug, version, release)
        if approval_id is not None:
            ident = int(approval_id)
            return _check_one(db, ident, slug=slug, version=version, release=release,
                              current=current), (ident)
        with db.session() as s:
            ids = list(s.scalars(select(AuditLog.id).where(
                AuditLog.action == APPROVED, AuditLog.artifact == f"{slug}@{version}")
                .order_by(AuditLog.id.desc())))
        if not ids:
            return "recorded owner publication grant required", None
        first = None
        for ident in ids:
            why = _check_one(db, ident, slug=slug, version=version, release=release,
                             current=current)
            if why is None:
                return None, ident
            first = first or why
        return first, None
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return f"recorded valid owner publication grant required ({str(exc)[:200]})", None


def validate(db, approval_id=None, *, slug, version, release) -> str | None:
    return resolve(db, slug=slug, version=version, release=release,
                   approval_id=approval_id)[0]
