"""WS4-8: the Stage A use path -- how a standing activation grant reaches `store.activate`.

`ops.standing_activation` (Stage A part 1, OFF in code) can mint a signed, single-use,
job-bound activation grant ("seg:<id>"). This module is the wiring around it, and nothing in
it widens what that grant may do:

1. **Schedule** (`schedule`, the `policy.activation_schedule` job). Deterministic, no network,
   no spend. While `STAGE_A_ENABLED` is False, or no approved standing policy is in effect, or
   the policy does not name `store.activate`, it is a no-op that records why
   (`standing_activation.schedule_skipped`). Otherwise it walks the certified releases whose
   verified Etsy draft is in SP lineage, records one Stage A shadow decision per release and
   decision (the evidence `standing_activation.a_shadow` reads), and for at most ONE release a
   run -- never while another standing activation is outstanding -- whose live decision
   (`standing_activation.decide`: every gate, the pace and fee ceilings) is ACTIVATE, it
   queues a `store.activate` job marked `standing_activation` and ASKS the issuer for a grant
   bound to that job (`policy.activation_grant_requested`). The request carries no authority.
2. **Answer** (`pending_requests` / `answer`, the policy-issuer service only). The issuer
   checks the job is a live `store.activate` job for this exact release that asked for a
   standing grant, then calls `standing_activation.issue`, which re-derives every fact. A
   refusal is recorded (`policy.activation_grant_held`), so the request is answered once.
3. **Use** (`runtime.pipeline.handle_store_activate`, the ONLY handler). It finds the grant
   issued for its own job (`grant_for_job`), consumes it once (`claim`), and then runs every
   guard it runs for an owner's per-product approval -- kill switch, phase, spend reservation,
   the write-ahead `etsy.activate` intent (`<listing>:seg:<id>`), `use_refusal` at the client
   -- and reads the listing back. Only a read-back showing this listing `active`, after the
   handler's `store.activated` row, records SP lineage (`standing_activation.record_activated`).
4. **Reconcile** (`reconcile`). A job retried after a crash that followed the Etsy request
   finds its own intent, reads the listing back, and if Etsy holds it `active` records the
   activation it already paid for. Nothing is re-sent and the fee is not reserved twice.

A listing the owner activated with a per-product approval never passes through `reconcile`
or `record_activated`, so it is never in Stage A lineage and never reachable by withdrawal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import standing_activation as SA
from . import standing_boundary as SB
from . import standing_policy as SP

JOB_TYPE = "policy.activation_schedule"
#: The marker on a store.activate job that asks for a standing grant instead of carrying an
#: owner approval. It is a request, never authority: the handler finds the grant itself.
STANDING_INPUT = "standing_activation"
REQUESTED = "policy.activation_grant_requested"
HELD = "policy.activation_grant_held"
SKIPPED = "standing_activation.schedule_skipped"
SCHEDULED = "standing_activation.scheduled"
LINEAGE_UNRECORDED = "standing_activation.lineage_unrecorded:"
_log = logging.getLogger(__name__)


from ..core.resilience import TransientError as _TransientError  # noqa: E402


class LineageUnrecorded(_TransientError):
    """Verdict 7012067586 item 1: the listing is live, its lineage could not be recorded AND
    the P1 incident could not be written. Raised so the job retries (the retry reconciles from
    the read-back and sends nothing), never returned as a silent False."""
REQUEST_ACTOR = "standing_scheduler"
#: The job runs no earlier than this after it is queued, so the issuer (a 60-second pull loop)
#: has answered before the worker looks for the grant. Inside the grant's 15-minute life.
ISSUE_DELAY = timedelta(minutes=3)
_LIVE = ("pending", "running")


def _now(now=None) -> datetime:
    from . import standing_issuer as SI

    return SI._now(now)


def _status(job) -> str:
    return job.status.value if hasattr(job.status, "value") else str(job.status)


# ---- 1. schedule ----------------------------------------------------------------------------

def _skip(db, why: str, now: datetime) -> dict:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=REQUEST_ACTOR, action=SKIPPED, artifact="standing_policy",
                       detail={"why": why, "at": now.isoformat()}))
    return {"scheduled": [], "skipped": why, "shadow_recorded": 0}


def candidates(db) -> list[tuple[str, str, str]]:
    """(slug, version, release) of every certified release with a verified Etsy draft, in a
    fixed order. Lineage, gates and ceilings are `standing_activation.decide`'s to judge."""
    from sqlalchemy import select

    from ..core.listing_state import PUBLISHED
    from ..core.models import Listing, PatternVersion, Product

    out = []
    with db.session() as s:
        # Only drafts the gated store.publish made (PUBLISHED). A listing the owner made by
        # hand and adopted (PUBLISHED_MANUALLY) is deliberately not a candidate: it was never
        # an SP draft, so it can never be in Stage A lineage.
        for row in s.scalars(select(Listing).where(Listing.state == PUBLISHED)
                             .order_by(Listing.product_slug, Listing.version)):
            if not row.etsy_listing_id or not row.release_hash:
                continue
            certified = s.scalar(select(PatternVersion.id).join(
                Product, Product.id == PatternVersion.product_id).where(
                Product.slug == row.product_slug, PatternVersion.version == row.version,
                PatternVersion.certified.is_(True)))
            if certified is not None:
                out.append((row.product_slug, row.version, str(row.release_hash)))
    return out


def outstanding(db) -> list[dict]:
    """Standing activation work that is not finished: a live standing store.activate job, or
    a request the issuer has not answered. While any exists nothing new is scheduled."""
    from sqlalchemy import select

    from ..core.models import Job

    out = []
    with db.session() as s:
        for job in s.scalars(select(Job).where(Job.job_type == SA.ACTIVATE_JOB)):
            if (job.inputs or {}).get(STANDING_INPUT) and _status(job) in _LIVE:
                out.append({"job_id": job.id, "slug": (job.inputs or {}).get("slug")})
    out += [{"request_id": r["request_id"], "slug": r["slug"]} for r in pending_requests(db)]
    return out


def _shadow_once(db, slug, version, release, *, approval_id, decision, reasons, now) -> bool:
    """One Stage A shadow decision per (approval, release, decision): a release re-read every
    run is one candidate, not one a run, so the gate's count is of releases decided."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        for d in s.scalars(select(AuditLog.detail).where(
                AuditLog.action == SA.SHADOW_DECISION, AuditLog.actor == SA.SHADOW_ACTOR,
                AuditLog.artifact == f"{slug}@{version}")):
            d = d or {}
            if (int(d.get("approval_id") or -1) == int(approval_id)
                    and str(d.get("release")) == str(release) and d.get("decision") == decision):
                return False
    SA.record_shadow(db, slug, version, release, approval_id=approval_id, decision=decision,
                     reasons=reasons, now=now)
    return True


def _is_shadow_reason(reason: str) -> bool:
    return str(reason).startswith("Stage A shadow gate:")


def schedule(db, *, enqueue, now: datetime | None = None) -> dict:
    """One scheduling pass. `enqueue(agent, job_type, inputs, **kw)` queues a job (the
    handler's `ctx.enqueue`) and returns it, or None for a duplicate key."""
    now = _now(now)
    if not SA.STAGE_A_ENABLED:
        return _skip(db, SA.OFF, now)
    eff = SP.effective(db, now=now)
    if eff.get("state") != SP.EFFECTIVE:
        return _skip(db, f"no approved standing policy is in effect: {eff.get('why')}", now)
    if SA.ACTION not in (eff.get("content") or {}).get("actions") or []:
        return _skip(db, "the effective standing policy does not name store.activate", now)
    aid = eff["approval_id"]
    busy = outstanding(db)
    recorded, decisions, scheduled = 0, [], []
    for slug, version, release in candidates(db):
        if SA.lineage(db, slug, version, release, aid)["state"] != SB.PASS:
            continue                     # a draft this policy did not create: never a candidate
        d = SA.decide(db, slug, version, release, now=now)
        reasons = list(d.get("reasons") or [])
        # The shadow decision is what the policy WOULD do: every gate except Stage A's own
        # shadow gate, which these rows are the evidence for.
        would = "ACTIVATE" if not [r for r in reasons if not _is_shadow_reason(r)] else "HOLD"
        recorded += _shadow_once(db, slug, version, release, approval_id=aid, decision=would,
                                 reasons=reasons, now=now)
        decisions.append({"artifact": f"{slug}@{version}", "decision": d.get("decision"),
                          "reasons": reasons[:5]})
        if d.get("decision") != "ACTIVATE" or busy or scheduled:
            continue
        from ..runtime.release import chain_key

        job = enqueue("store_operator", SA.ACTIVATE_JOB,
                      {"slug": slug, "version": version, "release": release,
                       STANDING_INPUT: True},
                      idempotency_key=chain_key("standing-activate", slug, version, release,
                                                now.date().isoformat()),
                      run_after=now + ISSUE_DELAY)
        if job is None:
            continue                     # today's job for this release already exists
        rid = request(db, slug=slug, version=version, release=release, job_id=job.id)
        scheduled.append({"slug": slug, "version": version, "job_id": job.id,
                          "request_id": rid})
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=REQUEST_ACTOR, action=SCHEDULED, artifact="standing_policy",
                       detail={"approval_id": aid, "scheduled": scheduled,
                               "outstanding": busy[:5], "decisions": decisions[:10],
                               "at": now.isoformat()}))
    return {"scheduled": scheduled, "skipped": None, "shadow_recorded": recorded,
            "outstanding": len(busy), "decisions": decisions}


# ---- 2. request and answer ------------------------------------------------------------------

def request(db, *, slug: str, version: str, release: str, job_id: int) -> int:
    """ASK for an activation grant. Carries no authority; the issuer re-derives every fact."""
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor=REQUEST_ACTOR, action=REQUESTED, artifact=f"{slug}@{version}",
                       job_id=int(job_id),
                       detail={"slug": str(slug), "version": str(version),
                               "release": str(release), "job_id": int(job_id)})
        s.add(row)
        s.flush()
        return row.id


def pending_requests(db, *, limit: int = 10) -> list[dict]:
    """Activation requests with no issued or held answer yet, oldest first."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        answered = {int((d or {}).get("request_id") or 0) for d in s.scalars(
            select(AuditLog.detail).where(AuditLog.action.in_((SA.ISSUED, HELD))))}
        rows = list(s.execute(select(AuditLog.id, AuditLog.detail).where(
            AuditLog.action == REQUESTED).order_by(AuditLog.id)))
    out = []
    for rid, d in rows:
        if rid in answered:
            continue
        d = d or {}
        try:
            out.append({"request_id": rid, "slug": str(d["slug"]), "version": str(d["version"]),
                        "release": str(d["release"]), "job_id": int(d["job_id"])})
        except (KeyError, TypeError, ValueError):
            continue
        if len(out) >= limit:
            break
    return out


def job_refusal(db, job_id, slug: str, version: str, release: str) -> str | None:
    """The grant binds to a job only if it is a live store.activate job for this exact release
    that asked for a standing grant (and carries no owner approval of its own)."""
    from ..core.models import Job

    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return f"job id {job_id!r} is not an integer"
    if isinstance(job_id, bool) or jid <= 0:
        return f"job id {job_id!r} is not a job"
    with db.session() as s:
        job = s.get(Job, jid)
        if job is None:
            return f"no job {jid}"
        inputs, status, jtype = dict(job.inputs or {}), _status(job), job.job_type
    if jtype != SA.ACTIVATE_JOB:
        return f"job {jid} is a {jtype} job, not {SA.ACTIVATE_JOB}"
    if status not in _LIVE:
        return f"job {jid} is {status}"
    if not inputs.get(STANDING_INPUT) or inputs.get("owner_activation_approval_id"):
        return f"job {jid} did not ask for a standing activation grant"
    if (str(inputs.get("slug")), str(inputs.get("version")), str(inputs.get("release"))) != \
            (str(slug), str(version), str(release)):
        return f"job {jid} activates another release"
    return None


def answer(db, req: dict, *, now: datetime | None = None) -> dict:
    """The issuer's answer to one activation request: a grant, or a recorded refusal. Any
    failure is a refusal, recorded, so a request is answered exactly once (fail closed)."""
    import logging

    from ..core.models import AuditLog

    try:
        why = job_refusal(db, req["job_id"], req["slug"], req["version"], req["release"])
        if why:
            raise SA.ActivationRefused(f"the request's job is not valid: {why}")
        got = SA.issue(db, slug=req["slug"], version=req["version"], release=req["release"],
                       job_id=req["job_id"], now=now, request_id=req["request_id"])
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded refusal
        why = (str(exc) if isinstance(exc, SA.ActivationRefused)
               else f"issuer error, refused ({type(exc).__name__}: {str(exc)[:200]})")
        try:
            with db.session() as s:
                s.add(AuditLog(actor="policy_issuer", action=HELD,
                               artifact=f"{req['slug']}@{req['version']}",
                               detail={"request_id": req["request_id"],
                                       "job_id": req.get("job_id"), "why": why[:400]}))
        except Exception:  # noqa: BLE001
            logging.getLogger("brambleloop.issuer").exception(
                "could not record the refusal of activation request %s", req.get("request_id"))
        return {"request_id": req["request_id"], "issued": False, "why": why}
    return {"request_id": req["request_id"], "issued": True, "grant_id": got["grant_id"]}


# ---- 3. use (runtime.pipeline.handle_store_activate only) -----------------------------------

def grant_for_job(db, job_id: int) -> dict:
    """The activation grant issued for `job_id`: {"grant_id": int} or {"grant_id": None,
    "why": ...}. Read from the grant store itself, never from the job's inputs."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import standing_grants as SG

    SG.ensure_tables(db)
    with db.session() as s:
        for g in s.scalars(select(SG.StandingGrant).order_by(SG.StandingGrant.id.desc())):
            body = g.detail_json or {}
            if body.get("action") == SA.ACTION and int(body.get("job_id") or -1) == int(job_id):
                return {"grant_id": g.id}
        held = None
        for d in s.scalars(select(AuditLog.detail).where(AuditLog.action == HELD)
                           .order_by(AuditLog.id.desc())):
            if int((d or {}).get("job_id") or -1) == int(job_id):
                held = (d or {}).get("why")
                break
    if held:
        return {"grant_id": None, "why": f"the policy issuer refused this job a standing "
                                         f"activation grant: {held}"}
    return {"grant_id": None, "why": "no standing activation grant has been issued for this "
                                     "job (the issuer has not answered its request)"}


def claim(db, grant_id: int, *, job_id: int, now: datetime | None = None) -> str | None:
    """Consume the grant for this job, once. A retry of the SAME job finds it already
    consumed by itself and goes on (the effect intent, not the grant, stops a second send);
    anything else is a refusal. Returns why not, or None."""
    from . import standing_grants as SG

    SG.ensure_tables(db)
    with db.session() as s:
        row = s.get(SG.StandingGrant, int(grant_id))
        if row is None:
            return f"no standing grant {grant_id}"
        consumed_by = row.consumed_job_id
    if consumed_by is not None:
        return None if int(consumed_by) == int(job_id) else \
            f"standing activation grant {grant_id} was consumed by job {consumed_by}"
    try:
        SG.consume(db, int(grant_id), job_id=int(job_id), stage="store.activate",
                   action=SA.ACTION, now=now)
    except SG.GrantRefused as exc:
        return str(exc)
    return None


def lineage_recorded(db, grant_id: int, listing_id: str) -> bool:
    """True when `standing_policy.activation_verified` already names this listing under this
    grant: the listing is in SP lineage and a retry has nothing to repair."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        for d in s.scalars(select(AuditLog.detail).where(AuditLog.action == SA.ACTIVATED)):
            d = d or {}
            if int(d.get("grant_id") or -1) == int(grant_id) and \
                    str(d.get("etsy_listing_id")) == str(listing_id):
                return True
    return False


def open_lineage_unrecorded(db, *, grant_id: int, listing_id: str, artifact: str,
                            why: str) -> bool:
    """Open (or restate) the P1 `standing_activation.lineage_unrecorded:<listing>` incident.
    Best effort: an incident that cannot be written is logged, never raised over the caller's
    own outcome. Returns whether it was written."""
    try:
        from . import incident_lifecycle as lifecycle

        with db.session() as s:
            lifecycle.open_or_restate(
                s, signature=f"{LINEAGE_UNRECORDED}{listing_id}", severity="P1",
                summary=(f"listing {listing_id} went live under standing grant {grant_id} but "
                         f"its Stage A lineage could not be recorded ({why[:200]}); the "
                         f"rollback cannot reach it. Check it on Etsy."),
                detail={"etsy_listing_id": str(listing_id), "grant_id": int(grant_id),
                        "artifact": artifact, "why": why[:300]})
        return True
    except Exception:  # noqa: BLE001 - best effort; the caller's result still says unrecorded
        _log.exception("could not open %s%s", LINEAGE_UNRECORDED, listing_id)
        return False


def owner_activated(db, listing_id: str) -> bool:
    """Verdict 7012067586 item 2: the newest `store.activated` for this listing was the owner's
    (authority "owner", or a pre-WS4-8 row with no authority, which was always the owner's
    per-product path). Such a listing went live on the owner's approval, not this grant, so it
    is no lineage gap and raises no `lineage_unrecorded` P1."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        for r in s.scalars(select(AuditLog).where(AuditLog.action == "store.activated")
                           .order_by(AuditLog.id.desc())):
            d = r.detail or {}
            if str(d.get("etsy_listing_id")) == str(listing_id):
                return d.get("authority", "owner") == "owner"
    return False


def record_live(ctx, *, grant_id: int, listing_id: str, after: dict, artifact: str) -> bool:
    """L-B: after the handler's `store.activated` row and a read-back showing the listing
    `active`, put it in SP lineage. A read-back that does not show it is recorded nothing; a
    live listing whose lineage cannot be recorded -- refused, or `record_activated` raising --
    is an incident (withdrawal could not reach it), never silence. Idempotent: a listing
    already in lineage under this grant is not recorded twice."""
    live = str((after or {}).get("state") or "").lower() == "active"
    why = "standing_activation.record_activated refused the read-back"
    try:
        if lineage_recorded(ctx.db, grant_id, listing_id):
            return True
        ok = SA.record_activated(ctx.db, int(grant_id), listing_id=str(listing_id),
                                 after=after)
    except Exception as exc:  # noqa: BLE001 - MEDIUM-1: a DB error here must not be silent
        ok, live = False, True
        why = f"recording raised {type(exc).__name__}: {str(exc)[:200]}"
    if not ok and live:
        written = open_lineage_unrecorded(ctx.db, grant_id=grant_id, listing_id=listing_id,
                                          artifact=artifact, why=why)
        if not written:
            # Double fault: no lineage and no incident would leave a live listing invisible to
            # the rollback and to the owner. Fail the attempt so the job is retried.
            raise LineageUnrecorded(
                f"listing {listing_id} is live under standing grant {grant_id}; its lineage "
                f"and its incident could not be recorded ({why[:160]})")
    elif ok:
        _resolve_lineage_unrecorded(ctx.db, listing_id=listing_id, grant_id=grant_id)
    return ok


def _resolve_lineage_unrecorded(db, *, listing_id: str, grant_id: int) -> None:
    """A retry that recorded the lineage closes the incident an earlier attempt opened."""
    try:
        from . import incident_lifecycle as lifecycle

        with db.session() as s:
            lifecycle.resolve_signatures(
                s, [f"{LINEAGE_UNRECORDED}{listing_id}"],
                resolution=f"listing {listing_id} is now in Stage A lineage under standing "
                           f"grant {grant_id}")
    except Exception:  # noqa: BLE001 - best effort; the lineage itself is recorded
        _log.exception("could not resolve %s%s", LINEAGE_UNRECORDED, listing_id)


# ---- 4. reconcile a crash after the Etsy request --------------------------------------------

def _activated_audited(db, grant_id: int, listing_id: str) -> bool:
    """A `store.activated` row already names this listing under this standing grant (an
    earlier attempt got that far), so a reconcile does not write a second one."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        for d in s.scalars(select(AuditLog.detail).where(AuditLog.action == "store.activated")):
            d = d or {}
            if d.get("authority") == "standing" and \
                    int(d.get("grant_id") or -1) == int(grant_id) and \
                    str(d.get("etsy_listing_id")) == str(listing_id):
                return True
    return False


def reconcile(ctx, *, grant_id: int, listing_id: str, remote: dict, slug: str,
              version: str) -> dict | None:
    """A retried standing job whose earlier attempt claimed the `etsy.activate` intent and
    then stopped. If Etsy reads this listing `active`, the activation happened: record it from
    the read-back (state, `store.activated`, lineage) and send nothing. Otherwise None, and
    the handler goes on, where the intent refuses any second send."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ..queue import effects

    effects.ensure_table(ctx.db)
    idem = f"{listing_id}:{SA.SEG_PREFIX}{int(grant_id)}"
    with ctx.db.session() as s:
        intent = s.get(effects.EffectIntent, effects.key_for(SA.ACTIVATE_EFFECT, idem))
        state = intent.state if intent is not None else None
        intent_job = intent.job_id if intent is not None else None
    if state is None or state == effects.RELEASED or intent_job != ctx.job.id:
        return None
    if str(remote.get("listing_id")) != str(listing_id) or \
            str(remote.get("state") or "").lower() != "active":
        return None
    artifact = f"{slug}@{version}"
    with ctx.db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is not None:
            row.state = "active"
    if not _activated_audited(ctx.db, grant_id, listing_id):
        ctx.audit("store.activated", artifact=artifact,
                  detail={"etsy_listing_id": str(listing_id),
                          "state_on_etsy": remote.get("state"), "authority": "standing",
                          "grant_id": int(grant_id), "reconciled": True,
                          "intent_state": state})
    recorded = record_live(ctx, grant_id=grant_id, listing_id=listing_id, after=remote,
                           artifact=artifact)
    from . import incident_lifecycle as lifecycle

    with ctx.db.session() as s:
        lifecycle.resolve_signatures(
            s, [f"effect.reconcile:{effects.key_for(SA.ACTIVATE_EFFECT, idem)[:40]}"],
            resolution=f"listing {listing_id} reads active on Etsy: the earlier attempt's "
                       f"activation applied and is recorded from the read-back")
    return {"slug": slug, "version": version, "activated": True, "reconciled": True,
            "etsy_listing_id": str(listing_id), "state_on_etsy": remote.get("state"),
            "lineage_recorded": recorded}
