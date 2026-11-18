"""WS4-7 (Mode T): the Standing Execution Grant (SEG) store and the issuer's signing.

Design: `research/final_build/ws4/WS4_DESIGN.md` §2-§3 (the trusted issuer service boundary,
Main S3 of 6953884261). The three facts this module makes true:

1. **Only the issuer process can mint.** A SEG is an Ed25519 signature under
   `BRAMBLELOOP_GRANT_ISSUER_KEY`, and `issuer_signing_refusal()` refuses in any process that
   has not marked itself the issuer (`mark_issuer_process`, called only by
   `app/issuer_entry.py`) -- and in any job process, whatever it marked. The worker scrubs the
   key at boot (`mark_job_process`) and holds only the verify key. An env-scrub inside a shared
   process is NOT the boundary: the boundary is that the key is set only on the issuer's own
   service, and `deployment_mode()` reports Mode T only when each process's own report agrees.
2. **The database bounds what a key can do.** `standing_grants` has
   `UNIQUE(consumed_job_id)`, one open grant per (policy, scope, release), and a TTL check;
   `standing_grant_slots` has `UNIQUE(policy_row_id, day, slot_no)` and `slot_no` 1..3, so the
   database itself refuses the 4th grant of a day.
3. **A grant is single use.** `consume` is one conditional UPDATE that must affect exactly one
   row, after the signature verifies against the stored content.

Nothing here is live: no standing policy can be EFFECTIVE until the owner approves and
activates one (`standing_policy.activation_refusals`, which needs a fresh G-SHADOW MET), and
activation needs Mode T, which needs a separate Railway service -- an owner spend decision.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import (JSON, CheckConstraint, DateTime, Index, Integer, String,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow
from . import standing_policy as SP

SCHEMA = "brambleloop.seg/1"
DOMAIN = "brambleloop/standing-grant/v1"
HEARTBEAT_DOMAIN = "brambleloop/policy-issuer/heartbeat/v1"
ISSUER_HOST = "policy-issuer"
ISSUER_COMPONENT = "policy_issuer"
WORKER_COMPONENT = "worker_keys"
WEB_COMPONENT = "web_keys"
REQUESTED = "policy.grant_requested"
ISSUED = "policy.grant_issued"
CONSUMED = "policy.grant_consumed"
HELD = "policy.grant_held"
_REQUEST_SCAN = 500   # request rows read per pass, after answered ones are excluded
ACTOR = "policy_issuer"
HEARTBEAT_FRESH = timedelta(minutes=5)
_ETSY_CREDENTIAL_VARS = ("ETSY_API_KEY", "ETSY_KEYSTRING", "ETSY_SHARED_SECRET",
                         "ETSY_ACCESS_TOKEN", "ETSY_REFRESH_TOKEN")


class GrantRefused(ValueError):
    """No grant: a refusal with its reason, never a partial grant."""


class StandingGrant(Base):
    __tablename__ = "standing_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_row_id: Mapped[int] = mapped_column(Integer, index=True)
    policy_version: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(160))
    release: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    detail_json: Mapped[dict] = mapped_column(JSON)
    seal: Mapped[str] = mapped_column(String(160))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consumed_stage: Mapped[str] = mapped_column(String(40), default="")

    __table_args__ = (
        UniqueConstraint("consumed_job_id", name="uq_standing_grants_consumed_job"),
        # One open (unconsumed) grant per policy, scope and release.
        Index("uq_standing_grants_open", "policy_row_id", "scope", "release", unique=True,
              sqlite_where=text("consumed_at IS NULL"),
              postgresql_where=text("consumed_at IS NULL")),
        CheckConstraint("expires_at > issued_at", name="ck_standing_grants_ttl_positive"),
    )


class StandingGrantSlot(Base):
    __tablename__ = "standing_grant_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_row_id: Mapped[int] = mapped_column(Integer)
    day: Mapped[str] = mapped_column(String(10))
    slot_no: Mapped[int] = mapped_column(Integer)
    grant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("policy_row_id", "day", "slot_no", name="uq_standing_grant_slot"),
        CheckConstraint(f"slot_no BETWEEN 1 AND {SP.MAX_PER_DAY}",
                        name="ck_standing_grant_slot_no"),
    )


_LOCK = threading.Lock()
_FLAG = "_brambleloop_standing_grants_ready"


def ensure_tables(db) -> None:
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[StandingGrant.__table__,
                                                 StandingGrantSlot.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


# ---- who may sign --------------------------------------------------------------------------

_PROCESS = {"issuer": False, "job": False}


def mark_issuer_process() -> None:
    """Called only by `app/issuer_entry.main`: this process is the policy issuer."""
    _PROCESS["issuer"] = True


def mark_job_process() -> bool:
    """A job process never mints a grant: the issuer signing key is scrubbed (worker boot)."""
    _PROCESS["job"] = True
    return os.environ.pop(SP.ISSUER_KEY_VAR, None) is not None


def issuer_signing_refusal(env=None) -> str | None:
    env = os.environ if env is None else env
    if _PROCESS["job"]:
        return "this process runs jobs, so it may never sign a standing grant"
    if not _PROCESS["issuer"]:
        return ("only the policy-issuer process (app/issuer_entry.py) signs a standing grant; "
                "this process has not marked itself the issuer")
    if str(env.get(SP.EMBEDDED_VAR, "1")) == "1":
        return (f"{SP.EMBEDDED_VAR} is on here: the issuer runs as its own service with no job "
                f"handlers and no web listener")
    held = [v for v in _ETSY_CREDENTIAL_VARS if str(env.get(v) or "").strip()]
    if held:
        return f"the issuer holds no Etsy credentials, and {held} are set in this process"
    return None


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _key(var: str, env=None) -> bytes:
    env = os.environ if env is None else env
    raw = str(env.get(var) or "").strip()
    if not raw:
        raise GrantRefused(f"{var} is not set in this process")
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise GrantRefused(f"{var} must be a base64 32-byte Ed25519 key")
    return key


def fingerprint(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest()[:16] if raw else None


def _public_of(private_raw: bytes) -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.from_private_bytes(private_raw).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _sign(domain: str, body: dict) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    why = issuer_signing_refusal()
    if why:
        raise GrantRefused(f"standing grant signing refused: {why}")
    key = Ed25519PrivateKey.from_private_bytes(_key(SP.ISSUER_KEY_VAR))
    return key.sign(f"{domain}\n{_json(body)}".encode()).hex()


def verify(domain: str, body: dict, seal: str, env=None) -> bool:
    """Any process with the issuer VERIFY key checks a grant or a heartbeat."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(_key(SP.ISSUER_VERIFY_KEY_VAR, env))
        pub.verify(bytes.fromhex(seal), f"{domain}\n{_json(body)}".encode())
        return True
    except (InvalidSignature, ValueError, GrantRefused):
        return False


# ---- process reports (each process is the only witness to its own environment) --------------

def _db_user(db) -> str | None:
    try:
        with db.session() as s:
            if s.get_bind().dialect.name != "postgresql":
                return None
            return str(s.execute(text("SELECT current_user")).scalar())
    except Exception:  # noqa: BLE001 - unreadable is UNKNOWN
        return None


def _env_fp(var: str, env) -> str | None:
    raw = str(env.get(var) or "").strip()
    if not raw:
        return None
    try:
        return fingerprint(base64.b64decode(raw, validate=True))
    except Exception:  # noqa: BLE001
        return "malformed"


def issuer_heartbeat(db, *, now: datetime | None = None, env=None) -> dict:
    """The issuer's signed report of its own environment, one RuntimeSample row."""
    from . import slo

    env = os.environ if env is None else env
    detail = {
        "host": ISSUER_HOST,
        "issuer_key_fp": fingerprint(_public_of(_key(SP.ISSUER_KEY_VAR, env))),
        "policy_verify_fp": _env_fp(SP.VERIFY_KEY_VAR, env),
        "policy_signing_present": bool(str(env.get(SP.SIGNING_KEY_VAR) or "").strip()),
        "embedded_worker": str(env.get(SP.EMBEDDED_VAR, "1")),
        "etsy_credentials_present": any(str(env.get(v) or "").strip()
                                        for v in _ETSY_CREDENTIAL_VARS),
        "db_user": _db_user(db),
        "at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    detail["seal"] = _sign(HEARTBEAT_DOMAIN, detail)
    slo.record_heartbeat(db, ISSUER_COMPONENT, instance=ISSUER_HOST, detail=detail, now=now)
    return detail


def process_report(db, component: str, *, now: datetime | None = None, env=None) -> dict:
    """A worker's or web process's own report: which keys it holds (fingerprints only)."""
    from . import slo

    env = os.environ if env is None else env
    detail = {
        "issuer_verify_fp": _env_fp(SP.ISSUER_VERIFY_KEY_VAR, env),
        "issuer_signing_present": bool(str(env.get(SP.ISSUER_KEY_VAR) or "").strip()),
        "policy_signing_fp": _env_fp(SP.SIGNING_KEY_VAR, env),
        "policy_verify_fp": _env_fp(SP.VERIFY_KEY_VAR, env),
        "embedded_worker": str(env.get(SP.EMBEDDED_VAR, "1")),
        "db_user": _db_user(db),
    }
    slo.record_heartbeat(db, component, instance=component, detail=detail, now=now)
    return detail


def _latest(db, component: str):
    from sqlalchemy import select

    from .slo import RuntimeSample

    with db.session() as s:
        row = s.scalar(select(RuntimeSample).where(
            RuntimeSample.kind == "heartbeat", RuntimeSample.component == component)
            .order_by(RuntimeSample.id.desc()).limit(1))
        if row is None:
            return None, None
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        return at, dict(row.detail or {})


def mode_report(db, *, now: datetime | None = None, env=None) -> dict:
    """Design §2.4: Mode T only when every process's latest report agrees. A check against
    misconfiguration, not against an attacker (each process is the only witness to itself)."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    rows = {}
    for comp in (ISSUER_COMPONENT, WORKER_COMPONENT, WEB_COMPONENT):
        try:
            at, d = _latest(db, comp)
        except Exception as exc:  # noqa: BLE001 - unreadable evidence is not Mode T
            at, d = None, None
            reasons.append(f"{comp} report unreadable ({type(exc).__name__})")
        rows[comp] = d
        if d is None:
            reasons.append(f"no {comp} report")
        elif now - at > HEARTBEAT_FRESH:
            reasons.append(f"the {comp} report is older than {HEARTBEAT_FRESH}")
    iss, wrk, web = rows[ISSUER_COMPONENT], rows[WORKER_COMPONENT], rows[WEB_COMPONENT]
    if iss is not None:
        body = {k: v for k, v in iss.items() if k != "seal"}
        if not verify(HEARTBEAT_DOMAIN, body, str(iss.get("seal") or ""), env):
            reasons.append("the issuer heartbeat does not verify under the issuer verify key")
        if iss.get("embedded_worker") != "0":
            reasons.append("the issuer process reports job handlers embedded")
        if iss.get("etsy_credentials_present"):
            reasons.append("the issuer process holds Etsy credentials")
        if iss.get("policy_signing_present"):
            reasons.append("the issuer process holds the policy signing key")
    if wrk is not None:
        if wrk.get("issuer_signing_present"):
            reasons.append("the worker holds the issuer signing key")
        if not wrk.get("issuer_verify_fp"):
            reasons.append("the worker has no issuer verify key")
        elif iss is not None and wrk.get("issuer_verify_fp") != iss.get("issuer_key_fp"):
            reasons.append("the worker's issuer verify key is not the issuer's key")
    if web is not None:
        if web.get("embedded_worker") != "0":
            reasons.append(f"web reports {SP.EMBEDDED_VAR} on")
        if web.get("issuer_signing_present"):
            reasons.append("web holds the issuer signing key")
    fps = [x for x in ((iss or {}).get("issuer_key_fp"), (web or {}).get("policy_signing_fp")
                       or (web or {}).get("policy_verify_fp")) if x]
    if len(fps) == 2 and fps[0] == fps[1]:
        reasons.append("the issuer key and the policy key are the same key")
    users = {c: (rows[c] or {}).get("db_user") for c in rows}
    if users[ISSUER_COMPONENT] and users[ISSUER_COMPONENT] == users[WORKER_COMPONENT]:
        reasons.append("the worker and the issuer use the same database role (runbook §2.3 "
                       "not applied)")
    return {"mode": "S" if reasons else "T", "reasons": reasons,
            "db_roles_separated": bool(users[ISSUER_COMPONENT] and users[WORKER_COMPONENT]
                                       and users[ISSUER_COMPONENT] != users[WORKER_COMPONENT])}


# ---- requests, issue, consume --------------------------------------------------------------

def request_grant(db, *, slug: str, version: str, release: str, job_id: int) -> int:
    """What a worker may do: ASK. A request row carries no authority; the issuer re-derives
    every fact and reads only (slug, version, release, job_id) from it."""
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor="worker", action=REQUESTED, artifact=f"{slug}@{version}",
                       detail={"slug": str(slug), "version": str(version),
                               "release": str(release), "job_id": int(job_id)})
        s.add(row)
        s.flush()
        return row.id


def _db_now(db) -> datetime:
    with db.session() as s:
        v = s.execute(text("SELECT CURRENT_TIMESTAMP")).scalar()
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def issue(db, *, slug: str, version: str, release: str, job_id: int,
          now: datetime | None = None, request_id: int | None = None) -> dict:
    """Issue one SEG, or raise `GrantRefused` with every reason. Issuer process only."""
    from sqlalchemy import func, select
    from sqlalchemy.exc import IntegrityError

    from ..core.models import AuditLog
    from . import publication_authority as PA
    from . import standing_issuer as SI

    why = issuer_signing_refusal()
    if why:
        raise GrantRefused(why)
    ensure_tables(db)
    now = now or _db_now(db)
    if (mode := mode_report(db, now=now))["mode"] != "T":
        raise GrantRefused("deployment is not Mode T: " + "; ".join(mode["reasons"][:4]))
    eff = SP.effective(db, now=now)
    if eff.get("state") != SP.EFFECTIVE:
        raise GrantRefused(f"no effective standing policy: {eff.get('why')}")
    decided = SI.decide(db, slug, version, release, now=now)
    if decided.get("decision") != "ISSUE":
        raise GrantRefused(f"out of policy: {decided.get('reasons') or decided.get('why')}")
    content_policy = eff["content"]
    scope = f"{slug}@{version}"
    day = now.date().isoformat()
    week_ago = now - timedelta(days=7)
    with db.session() as s:
        outstanding = int(s.scalar(select(func.count(StandingGrant.id)).where(
            StandingGrant.policy_row_id == eff["approval_id"],
            StandingGrant.consumed_at.is_(None), StandingGrant.expires_at > now)) or 0)
        week = int(s.scalar(select(func.count(StandingGrantSlot.id)).where(
            StandingGrantSlot.policy_row_id == eff["approval_id"],
            StandingGrantSlot.at >= week_ago)) or 0)
        used_today = sorted(s.scalars(select(StandingGrantSlot.slot_no).where(
            StandingGrantSlot.policy_row_id == eff["approval_id"],
            StandingGrantSlot.day == day)))
    if outstanding >= SP.MAX_OUTSTANDING:
        raise GrantRefused(f"{outstanding} grants outstanding (at most {SP.MAX_OUTSTANDING})")
    free = [n for n in range(1, SP.MAX_PER_DAY + 1) if n not in used_today]
    if not free:
        raise GrantRefused(f"all {SP.MAX_PER_DAY} of today's grant slots are used")
    snapshot = PA.snapshot(db, slug, version, release)
    ttl = min(int(SP.SEG_TTL_MINUTES), int(SP.SEG_TTL_CEILING_MINUTES))
    body = {
        "schema": SCHEMA, "action": "store.publish", "scope": scope, "release": str(release),
        "content": snapshot, "digest": PA.digest(snapshot),
        "shop": {"shop_id": SI._shop_id(db), "shop_name": SI._shop_name()},
        "classification": {"class_id": decided.get("class_id"),
                           "effective_risk_class": decided.get("effective_risk")},
        "policy": {"row_id": eff["approval_id"],
                   "version": int(content_policy.get("version") or 0),
                   "seal": eff.get("seal"), "activation_row_id": eff.get("activation_id")},
        "budget": {"day": day, "slot_no": free[0], "seven_day_count_before": week},
        "job_id": int(job_id), "nonce": secrets.token_hex(16),
        "issued_at": now.isoformat(), "not_before": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
        "issuer_key_fp": fingerprint(_public_of(_key(SP.ISSUER_KEY_VAR))),
        "issuer_host": ISSUER_HOST,
    }
    seal = _sign(DOMAIN, body)
    try:
        with db.session() as s:
            row = StandingGrant(policy_row_id=eff["approval_id"],
                                policy_version=body["policy"]["version"], scope=scope,
                                release=str(release), digest=body["digest"], detail_json=body,
                                seal=seal, issued_at=now,
                                expires_at=now + timedelta(minutes=ttl))
            s.add(row)
            s.flush()
            s.add(StandingGrantSlot(policy_row_id=eff["approval_id"], day=day,
                                    slot_no=free[0], grant_id=row.id, at=now))
            s.add(AuditLog(actor=ACTOR, action=ISSUED, artifact=scope,
                           detail={"grant_id": row.id, "digest": body["digest"],
                                   "job_id": int(job_id), "slot_no": free[0], "seal": seal,
                                   "request_id": request_id}))
            s.flush()
            gid = row.id
    except IntegrityError as exc:
        # The database's own limits: a second open grant for this release, a reused job, or
        # a slot another issuer took first. Refused, never retried into a 4th slot.
        raise GrantRefused(f"the grant store refused it ({type(exc.orig).__name__})") from None
    return {"grant_id": gid, "seal": seal, "content": body}


def consume(db, grant_id: int, *, job_id: int, stage: str = "pre_claim",
            now: datetime | None = None, env=None) -> dict:
    """Use a SEG once: verify, then one conditional UPDATE that must hit exactly one row."""
    from sqlalchemy import select, update

    from ..core.models import AuditLog

    ensure_tables(db)
    now = now or _db_now(db)
    with db.session() as s:
        row = s.get(StandingGrant, int(grant_id))
        if row is None:
            raise GrantRefused(f"no standing grant {grant_id}")
        body, seal = dict(row.detail_json or {}), str(row.seal or "")
    if not verify(DOMAIN, body, seal, env):
        raise GrantRefused(f"standing grant {grant_id} does not verify under the issuer key")
    if int(body.get("job_id", -1)) != int(job_id):
        raise GrantRefused(f"standing grant {grant_id} was issued for job {body.get('job_id')}")
    with db.session() as s:
        hit = s.execute(update(StandingGrant).where(
            StandingGrant.id == int(grant_id), StandingGrant.consumed_at.is_(None),
            StandingGrant.expires_at > now).values(
            consumed_at=now, consumed_job_id=int(job_id), consumed_stage=str(stage)[:40]))
        if hit.rowcount != 1:
            raise GrantRefused(f"standing grant {grant_id} is used, expired or gone")
        s.add(AuditLog(actor="worker", action=CONSUMED, artifact=body.get("scope", ""),
                       detail={"grant_id": int(grant_id), "job_id": int(job_id),
                               "stage": str(stage)[:40]}))
    return body


def pending_requests(db, *, limit: int = 20) -> list[dict]:
    """Request rows with no issued or held answer yet, oldest first."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        answered = {int((d or {}).get("request_id") or 0) for d in s.scalars(
            select(AuditLog.detail).where(AuditLog.action.in_((ISSUED, HELD))))}
        # Answered rows are excluded in SQL, before the limit: a limit taken first would
        # fill with answered requests and never reach a new one.
        q = select(AuditLog.id, AuditLog.detail).where(AuditLog.action == REQUESTED)
        if answered:
            q = q.where(AuditLog.id.notin_(answered))
        rows = list(s.execute(q.order_by(AuditLog.id).limit(_REQUEST_SCAN)))
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


def answer(db, req: dict, *, now: datetime | None = None) -> dict:
    """The issuer's answer to one request: a grant, or a recorded refusal."""
    from ..core.models import AuditLog

    try:
        got = issue(db, slug=req["slug"], version=req["version"], release=req["release"],
                    job_id=req["job_id"], now=now, request_id=req["request_id"])
    except GrantRefused as exc:
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR, action=HELD, artifact=f"{req['slug']}@{req['version']}",
                           detail={"request_id": req["request_id"], "why": str(exc)[:400]}))
        return {"request_id": req["request_id"], "issued": False, "why": str(exc)}
    return {"request_id": req["request_id"], "issued": True, "grant_id": got["grant_id"]}
