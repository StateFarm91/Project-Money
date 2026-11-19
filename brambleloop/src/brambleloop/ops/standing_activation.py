"""WS4 Stage A, part 1: the bounded public-activation authority. OFF IN CODE.

Design: research/final_build/w6/WS4_standing_policy_design.md §1.5, §5.3, §7.3, and Main's
binding §9 M1 (going live is P0 scope, in two stages) and M6 item 11 (Stage A: activation
grant, `deactivate`, rollback). This module is the activation grant. `EtsyClient.deactivate`
and the rollback job are part 2, a separate increment.

What it adds: a standing policy whose signed `actions` include `store.activate` may have the
policy-issuer process mint a single-use, job-bound, Ed25519-signed activation grant (an
"activation SEG") for ONE draft that the same policy created. The grant binds everything
today's per-product owner activation binds (`activation_authority.snapshot`: the listing id,
the certified payload, the certified frames and the files the verified publish sent).

Why it is OFF: `STAGE_A_ENABLED` is a code constant and is False. While it is False:

* `standing_policy.ceiling_refusals` refuses any policy content naming `store.activate`, so no
  such policy can be approved, let alone activated;
* `issue` refuses before reading anything else;
* `use_refusal` (the worker's use-time check, reached through `OwnerGrant`) refuses.

Turning it on is the owner's decision about a new power (it goes public and spends Etsy's
listing fee), and it is a reviewed code change, like every other ceiling (§9 M5). Even then
nothing issues until ALL of these hold, each read at issue time:

1. Mode T (the separate issuer service, WS4-7) and an EFFECTIVE policy naming the action;
2. Stage D's G-SHADOW reading is MET for that same approval (§9 M1: "Stage A may not begin
   issuing until Stage D has passed its shadow gate");
3. Stage A's own shadow gate (`a_shadow`) is met: at least `MIN_A_SHADOW_DAYS` days and
   `MIN_A_CANDIDATES` would-activate decisions, with ZERO cases where the policy would have
   activated a release the owner never approved for activation;
4. the release is still in policy (the same boundary classifier as publication, with
   "not on Etsy" replaced by SP lineage);
5. SP lineage: a `store.publish` SEG of this same policy was consumed for this exact release,
   and the verified `store.published` row naming the recorded listing was written by the job
   that consumed it. A draft the owner made, or any other draft, is never in lineage;
6. code ceilings: at most `MAX_ACTIVATIONS_PER_DAY` per day (also a database CHECK on the
   slot number), `MAX_ACTIVATIONS_PER_7D` per 7 days, and listing fees inside the lower of
   the policy's own 30-day figure and `MAX_ACTIVATION_FEES_CAD_PER_30D`.

At use (the worker, which holds Etsy credentials and reads the listing back): the grant must
verify under the issuer key, be for `store.activate`, name this listing, have been consumed by
this job, still match `activation_authority.snapshot`, and the listing Etsy holds must have
`should_auto_renew` exactly False (a renewal is a recurring fee no ceiling here counts).

Nothing in the publish path calls this yet: wiring consume-at-claim into `store.publish` and
`store.activate` is WS4-8, the use path, for both kinds together.
"""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow
from . import standing_boundary as SB
from . import standing_policy as SP

# ---- code ceilings (a change to any of these is a reviewed code change) --------------------
STAGE_A_ENABLED = False             # the power itself; the owner decides, a review lands it
ACTION = "store.activate"
PUBLISH = "store.publish"
SCHEMA = "brambleloop.seg-activate/1"
DOMAIN = "brambleloop/standing-grant/activate/v1"
MAX_ACTIVATIONS_PER_DAY = 1         # §7.3 G-LIMITED first-14-day pace
MAX_ACTIVATIONS_PER_7D = 3
MAX_ACTIVATION_FEES_CAD_PER_30D = 4.00   # 1/day and 3 per rolling 7 days allow at most 14
#                                          in 30 days (days 0-2, 7-9, 14-16, 21-23, 28-29):
#                                          14 x CA$0.28 (US$0.20 x 1.4154) = CA$3.92
MIN_A_SHADOW_DAYS = 7
MIN_A_CANDIDATES = 3
SHADOW_DECISION = "standing_activation.shadow_decision"
ISSUED = "policy.activation_grant_issued"
# Verdict 6998051067 M2: the one event that puts a listing in SP lineage. Written only after
# Etsy reads the listing back `active` following a request this grant authorised.
ACTIVATED = "standing_policy.activation_verified"
ACTIVATED_ACTOR = "standing_activation"
SHADOW_ACTOR = "standing_issuer"
OFF = ("store.activate is off in code (Stage A): making listings live without a per-product "
       "owner approval is a power the owner has not granted, and enabling it is a reviewed "
       "code change")


class ActivationRefused(ValueError):
    """No activation grant: a refusal with its reason."""


class StandingActivationSlot(Base):
    __tablename__ = "standing_activation_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_row_id: Mapped[int] = mapped_column(Integer)
    day: Mapped[str] = mapped_column(String(10))
    slot_no: Mapped[int] = mapped_column(Integer)
    grant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("policy_row_id", "day", "slot_no", name="uq_standing_activation_slot"),
        CheckConstraint(f"slot_no BETWEEN 1 AND {MAX_ACTIVATIONS_PER_DAY}",
                        name="ck_standing_activation_slot_no"),
    )


_LOCK = threading.Lock()
_FLAG = "_brambleloop_standing_activation_ready"


def ensure_tables(db) -> None:
    from . import standing_grants as SG

    SG.ensure_tables(db)
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if not getattr(engine, _FLAG, False):
            Base.metadata.create_all(engine, tables=[StandingActivationSlot.__table__],
                                     checkfirst=True)
            setattr(engine, _FLAG, True)


def fee_cad() -> float:
    from ..core.fx import ASSUMED_CAD_PER_USD
    from ..integrations.etsy import LISTING_FEE_USD

    return round(LISTING_FEE_USD * ASSUMED_CAD_PER_USD, 2)


# ---- the policy content (called from standing_policy.ceiling_refusals) ---------------------

def content_refusals(content: dict) -> list[str]:
    """Activation-specific ceilings for a policy naming `store.activate`. [] = acceptable."""
    acts = content.get("actions") if isinstance(content, dict) else None
    if not isinstance(acts, list) or ACTION not in acts:
        return []
    if not STAGE_A_ENABLED:
        return [OFF]
    out = []
    if PUBLISH not in acts:
        out.append("store.activate may only make live drafts the same policy created, so the "
                   "policy must also name store.publish")
    return out


def fee_ceiling_cad(content: dict) -> float:
    """The 30-day listing-fee ceiling the policy content may name."""
    acts = content.get("actions") if isinstance(content, dict) else None
    if STAGE_A_ENABLED and isinstance(acts, list) and ACTION in acts:
        return MAX_ACTIVATION_FEES_CAD_PER_30D
    return SP.MAX_LISTING_FEES_CAD_PER_30D


def statement(content: dict) -> tuple[str, str]:
    """(what is authorised, what is not) for `render_statement`, so the text the owner signs
    says plainly when the policy can go public."""
    if ACTION in (content.get("actions") or []):
        return ("create Etsy DRAFT listings and make those same drafts LIVE (public on "
                f"Etsy, each charging Etsy's listing fee of about CA${fee_cad():.2f}), at most "
                f"{MAX_ACTIVATIONS_PER_DAY} going live per day and {MAX_ACTIVATIONS_PER_7D} per "
                "7 days,",
                "This policy can make live only a draft it created itself; it cannot change a "
                "price, renew a listing, spend on advertising, or change itself.")
    return ("create Etsy DRAFT listings",
            "This policy cannot activate a listing, change a price, spend on advertising, or "
            "change itself.")


# ---- issue-time readers ---------------------------------------------------------------------

def _fact(state, value=None, why=None) -> dict:
    return {"state": state, "value": value, "why": why}


def lineage(db, slug: str, version: str, release: str, policy_row_id: int) -> dict:
    """Design §5.4 "SP lineage": the recorded listing is the draft THIS policy created."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Listing
    from . import standing_grants as SG

    scope = f"{slug}@{version}"
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if listing is None or not listing.etsy_listing_id:
            return _fact(SB.FAIL, None, "no Etsy draft is recorded for this release")
        if listing.state == "active":
            return _fact(SB.FAIL, None, "the listing is already active")
        listing_id = str(listing.etsy_listing_id)
        grants = list(s.scalars(select(SG.StandingGrant).where(
            SG.StandingGrant.policy_row_id == int(policy_row_id),
            SG.StandingGrant.scope == scope, SG.StandingGrant.release == str(release),
            SG.StandingGrant.consumed_at.is_not(None))))
        publish_jobs = {int(g.consumed_job_id) for g in grants
                        if (g.detail_json or {}).get("action") == PUBLISH
                        and g.consumed_job_id is not None}
        if not publish_jobs:
            return _fact(SB.FAIL, None, "no store.publish grant of this policy was consumed "
                                        "for this release: the draft is not in SP lineage")
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == "store.published", AuditLog.artifact == scope)
                .order_by(desc(AuditLog.id))):
            if str((row.detail or {}).get("etsy_listing_id") or "") != listing_id:
                continue
            if row.job_id is not None and int(row.job_id) in publish_jobs:
                return _fact(SB.PASS, {"listing_id": listing_id, "publish_job": row.job_id})
            return _fact(SB.FAIL, None, f"listing {listing_id} was published by job "
                                        f"{row.job_id}, not by a job that consumed this "
                                        "policy's grant: not in SP lineage")
    return _fact(SB.FAIL, None, f"no verified store.published row names listing {listing_id}")


def _shadow_rows(db, approval_id: int, *, since, now) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == SHADOW_DECISION, AuditLog.actor == SHADOW_ACTOR)
                .order_by(AuditLog.id)):
            d = row.detail or {}
            at = SP._when(d.get("at"))
            if (int(d.get("approval_id") or -1) != int(approval_id) or at is None
                    or (since is not None and at < since) or at > now):
                continue
            out.append({"at": at, "slug": d.get("slug"), "version": d.get("version"),
                        "release": d.get("release"), "would": d.get("decision")})
    return out


def _owner_approved_activation(db, slug, version) -> bool:
    """Did the owner record a per-product activation approval for this release?"""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import activation_authority as AA

    with db.session() as s:
        ids = list(s.scalars(select(AuditLog.id).where(
            AuditLog.action == AA.APPROVED, AuditLog.actor == AA.PRINCIPAL,
            AuditLog.artifact == f"{slug}@{version}")))
    return any(AA.LEDGER.refusal(db, i) is None for i in ids)


def a_shadow(db, approval_id: int, *, approved_at, now) -> dict:
    """Stage A's own shadow gate. A reading; it authorises nothing by itself."""
    rows = _shadow_rows(db, approval_id, since=approved_at, now=now)
    would = [r for r in rows if r["would"] == "ACTIVATE"]
    span = (max(r["at"] for r in rows) - min(r["at"] for r in rows)) if rows else timedelta(0)
    short = []
    if span < timedelta(days=MIN_A_SHADOW_DAYS):
        short.append(f"{span.days} of {MIN_A_SHADOW_DAYS} shadow days")
    if len(would) < MIN_A_CANDIDATES:
        short.append(f"{len(would)} of {MIN_A_CANDIDATES} would-activate decisions")
    if short:
        return _fact(SB.FAIL, {"days": span.days, "would_activate": len(would)},
                     "Stage A shadow is short: " + ", ".join(short))
    disagree = [f"{r['slug']}@{r['version']}" for r in would
                if not _owner_approved_activation(db, r["slug"], r["version"])]
    if disagree:
        return _fact(SB.FAIL, {"disagreements": disagree[:10]},
                     "the policy would have activated a release the owner never approved")
    return _fact(SB.PASS, {"days": span.days, "would_activate": len(would)})


def _counts(db, policy_row_id: int, now: datetime) -> dict:
    from sqlalchemy import func, select

    ensure_tables(db)
    with db.session() as s:
        def n(since):
            return int(s.scalar(select(func.count(StandingActivationSlot.id)).where(
                StandingActivationSlot.policy_row_id == int(policy_row_id),
                StandingActivationSlot.at >= since)) or 0)
        used_today = sorted(s.scalars(select(StandingActivationSlot.slot_no).where(
            StandingActivationSlot.policy_row_id == int(policy_row_id),
            StandingActivationSlot.day == now.date().isoformat())))
        return {"today": used_today, "7d": n(now - timedelta(days=7)),
                "30d": n(now - timedelta(days=30))}


def decide(db, slug: str, version: str, release: str, *, now: datetime | None = None) -> dict:
    """The live activation decision for one release. Returns {decision, reasons}."""
    from . import standing_issuer as SI
    from . import standing_shadow_gate as SG_GATE

    now = SI._now(now)
    if not STAGE_A_ENABLED:
        return {"decision": "HOLD", "reasons": [OFF]}
    eff = SP.effective(db, now=now)
    if eff.get("state") != SP.EFFECTIVE:
        return {"decision": None, "reasons": [f"no effective policy: {eff.get('why')}"]}
    content, aid = eff["content"], eff["approval_id"]
    reasons: list[str] = []
    if ACTION not in (content.get("actions") or []):
        reasons.append("the effective policy does not name store.activate")
    gate = SG_GATE.g_shadow(db, now=now, record=False)
    if gate.get("verdict") != "MET" or gate.get("approval_id") != aid:
        reasons.append("Stage D's G-SHADOW is not met for this policy (§9 M1)")
    a = a_shadow(db, aid, approved_at=SP._when(eff.get("approved_at")), now=now)
    if a["state"] != SB.PASS:
        reasons.append(f"Stage A shadow gate: {a['why']}")
    lin = lineage(db, slug, version, release, aid)
    if lin["state"] != SB.PASS:
        reasons.append(f"lineage: {lin['why']}")
    # The same in/out decision as publication, with "not on Etsy" replaced by lineage.
    facts = SI.read_facts(db, slug, version, release, content, shadow=False)
    facts["not_on_etsy"] = lin
    verdict = SB.classify(content, facts)
    if not verdict["in_policy"]:
        reasons.extend(f"boundary: {r}" for r in verdict["reasons"][:10])
    c = _counts(db, aid, now)
    if len(c["today"]) >= MAX_ACTIVATIONS_PER_DAY:
        reasons.append(f"at most {MAX_ACTIVATIONS_PER_DAY} activation(s) per day")
    if c["7d"] >= MAX_ACTIVATIONS_PER_7D:
        reasons.append(f"at most {MAX_ACTIVATIONS_PER_7D} activations per 7 days")
    fees = SP._num((content.get("spend") or {}).get("max_listing_fees_cad_per_30d"))
    ceiling = min(fees if fees is not None else 0.0, MAX_ACTIVATION_FEES_CAD_PER_30D)
    if round((c["30d"] + 1) * fee_cad(), 2) > ceiling:
        reasons.append(f"listing fees would pass CA${ceiling:.2f} in 30 days")
    return {"decision": "HOLD" if reasons else "ACTIVATE", "reasons": reasons,
            "class_id": verdict.get("class_id"), "effective_risk": verdict.get("effective_risk"),
            "approval_id": aid, "counts": c}


def record_shadow(db, slug, version, release, *, approval_id: int, decision: str,
                  reasons=(), now: datetime | None = None) -> None:
    """One Stage A shadow decision (the evidence `a_shadow` reads)."""
    from ..core.models import AuditLog
    from . import standing_issuer as SI

    now = SI._now(now)
    with db.session() as s:
        s.add(AuditLog(actor=SHADOW_ACTOR, action=SHADOW_DECISION, artifact=f"{slug}@{version}",
                       detail={"approval_id": int(approval_id), "slug": slug,
                               "version": version, "release": release,
                               "decision": decision, "reasons": list(reasons)[:10],
                               "at": now.isoformat()}))


# ---- issue (policy-issuer process only) -----------------------------------------------------

def issue(db, *, slug: str, version: str, release: str, job_id: int,
          now: datetime | None = None) -> dict:
    """Mint one activation SEG, or raise `ActivationRefused` with every reason."""
    from sqlalchemy.exc import IntegrityError

    from ..core.models import AuditLog
    from . import activation_authority as AA
    from . import standing_grants as SG
    from . import standing_issuer as SI

    if not STAGE_A_ENABLED:
        raise ActivationRefused(OFF)
    why = SG.issuer_signing_refusal()
    if why:
        raise ActivationRefused(why)
    ensure_tables(db)
    now = now or SG._db_now(db)
    if (mode := SG.mode_report(db, now=now))["mode"] != "T":
        raise ActivationRefused("deployment is not Mode T: " + "; ".join(mode["reasons"][:4]))
    decided = decide(db, slug, version, release, now=now)
    if decided.get("decision") != "ACTIVATE":
        raise ActivationRefused("; ".join(decided.get("reasons") or ["no decision"]))
    aid = decided["approval_id"]
    eff = SP.effective(db, now=now)
    snapshot = AA.snapshot(db, slug, version, release)
    slot = next(n for n in range(1, MAX_ACTIVATIONS_PER_DAY + 1)
                if n not in decided["counts"]["today"])
    ttl = min(int(SP.SEG_TTL_MINUTES), int(SP.SEG_TTL_CEILING_MINUTES))
    scope = f"{slug}@{version}"
    body = {
        "schema": SCHEMA, "action": ACTION, "scope": scope, "release": str(release),
        "listing_id": snapshot["listing_id"], "content": snapshot,
        "digest": AA.digest(snapshot), "fee_cad": fee_cad(),
        # WS4-7 round 2 L3 (consume -> shop_refusal): the shop is signed and re-read at use,
        # exactly as for a publish grant.
        "shop": {"shop_id": SI._shop_id(db), "shop_name": SI._shop_name()},
        "classification": {"class_id": decided.get("class_id"),
                           "effective_risk_class": decided.get("effective_risk")},
        "policy": {"row_id": aid, "version": int(eff["content"].get("version") or 0),
                   "seal": eff.get("seal"), "activation_row_id": eff.get("activation_id")},
        "budget": {"day": now.date().isoformat(), "slot_no": slot,
                   "seven_day_count_before": decided["counts"]["7d"]},
        "job_id": int(job_id), "nonce": secrets.token_hex(16),
        "issued_at": now.isoformat(), "not_before": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
        "issuer_key_fp": SG.fingerprint(SG._public_of(SG._key(SP.ISSUER_KEY_VAR))),
        "issuer_host": SG.ISSUER_HOST,
    }
    seal = SG._sign(DOMAIN, body)
    try:
        with db.session() as s:
            row = SG.StandingGrant(policy_row_id=aid, policy_version=body["policy"]["version"],
                                   scope=scope, release=str(release), digest=body["digest"],
                                   detail_json=body, seal=seal, issued_at=now,
                                   expires_at=now + timedelta(minutes=ttl))
            s.add(row)
            s.flush()
            s.add(StandingActivationSlot(policy_row_id=aid, day=body["budget"]["day"],
                                         slot_no=slot, grant_id=row.id, at=now))
            s.add(AuditLog(actor=SG.ACTOR, action=ISSUED, artifact=scope,
                           detail={"grant_id": row.id, "digest": body["digest"],
                                   "listing_id": body["listing_id"], "job_id": int(job_id),
                                   "slot_no": slot, "seal": seal}))
            s.flush()
            gid = row.id
    except IntegrityError as exc:
        raise ActivationRefused(f"the grant store refused it ({type(exc.orig).__name__})") \
            from None
    return {"grant_id": gid, "seal": seal, "content": body}


# ---- use (the worker; reached through integrations.etsy.OwnerGrant) -------------------------

SEG_PREFIX = "seg:"


def use_refusal(db, approval_id, *, slug: str, version: str, listing_id: str,
                release: str = "", job_id: int | None = None, remote: dict | None = None,
                env=None, now: datetime | None = None) -> str | None:
    """Why this activation SEG does not authorise going live now, or None. Fails closed.

    `approval_id` is "seg:<grant id>". The grant must already have been consumed by `job_id`
    (single use, at claim); `remote` is the listing as Etsy holds it, read back by the caller."""
    from . import activation_authority as AA
    from . import standing_grants as SG

    try:
        if not STAGE_A_ENABLED:
            return OFF
        gid = int(str(approval_id)[len(SEG_PREFIX):]) \
            if str(approval_id).startswith(SEG_PREFIX) else None
        if gid is None:
            return "not a standing activation grant"
        SG.ensure_tables(db)
        with db.session() as s:
            row = s.get(SG.StandingGrant, gid)
            if row is None:
                return f"no standing grant {gid}"
            body, seal = dict(row.detail_json or {}), str(row.seal or "")
            consumed_job = row.consumed_job_id
        if not SG.verify(DOMAIN, body, seal, env):
            return f"standing activation grant {gid} does not verify under the issuer key"
        if body.get("action") != ACTION:
            return f"standing grant {gid} is for {body.get('action')}, not {ACTION}"
        if body.get("scope") != f"{slug}@{version}" or str(body.get("release")) != str(release):
            return f"standing activation grant {gid} is for another release"
        if str(body.get("listing_id")) != str(listing_id):
            return f"standing activation grant {gid} names another listing"
        if job_id is None or consumed_job is None or int(consumed_job) != int(job_id):
            return f"standing activation grant {gid} was not consumed by this job"
        if AA.digest(AA.snapshot(db, slug, version, release)) != body.get("digest"):
            return "the listing no longer matches what the activation grant bound"
        if not isinstance(remote, dict) or remote.get("should_auto_renew") is not False:
            return ("the listing Etsy holds must have should_auto_renew false: a renewal is a "
                    "recurring fee no standing ceiling counts")
        # Verdict 6998051067 M3: consumed at claim is not authorised at use. A delayed or
        # reclaimed job re-reads, immediately before the request, the owner's policy (still
        # EFFECTIVE, and the very approval the grant was signed under), the grant's signed
        # expiry, and the shop it was signed for.
        from . import standing_issuer as SI

        now = SI._now(now)
        eff = SP.effective(db, now=now)
        if eff.get("state") != SP.EFFECTIVE:
            return (f"the standing policy is {eff.get('state')} at use ({eff.get('why')}); a "
                    "consumed grant does not outlive it")
        signed_row = (body.get("policy") or {}).get("row_id")
        if signed_row is None or int(eff.get("approval_id") or -1) != int(signed_row):
            return "the effective policy is no longer the approval this grant was signed under"
        expires = SP._when(body.get("expires_at"))
        if expires is None or now > expires:
            return f"standing activation grant {gid} expired at {body.get('expires_at')}"
        shop = SG.shop_refusal(db, body)
        if shop is not None:
            return f"standing activation grant {gid} is void: {shop}"
        return None
    except Exception as exc:  # noqa: BLE001 - an unverifiable grant is no grant
        return f"standing activation grant could not be verified: {type(exc).__name__}"


def record_activated(db, grant_id: int, *, listing_id: str, after: dict | None,
                     now: datetime | None = None) -> bool:
    """Verdict 6998051067 M2: record that the activation this grant authorised happened.

    Called by the Stage A activation path after the request, with the listing as Etsy reads it
    back. Only a read-back that is this listing and `active` is recorded; anything else
    records nothing and returns False (the listing is then never in SP lineage)."""
    from ..core.models import AuditLog
    from . import standing_grants as SG
    from . import standing_issuer as SI

    if not isinstance(after, dict) or str(after.get("listing_id")) != str(listing_id) \
            or str(after.get("state") or "").lower() != "active":
        return False
    SG.ensure_tables(db)
    with db.session() as s:
        row = s.get(SG.StandingGrant, int(grant_id))
        if row is None or row.consumed_at is None:
            return False
        body = dict(row.detail_json or {})
        if body.get("action") != ACTION or str(body.get("listing_id")) != str(listing_id):
            return False
        s.add(AuditLog(actor=ACTIVATED_ACTOR, action=ACTIVATED, artifact=row.scope,
                       detail={"grant_id": int(grant_id), "etsy_listing_id": str(listing_id),
                               "state_on_etsy": "active", "at": SI._now(now).isoformat()}))
    return True
