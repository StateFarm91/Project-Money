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
                        UniqueConstraint, event, text)
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
CLOCK_SKEW = timedelta(seconds=30)   # process clock vs database clock, either direction
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


WRITE_ONCE_TRIGGER = "standing_grants_write_once"
_WRITE_ONCE_MSG = "standing grant consumption is write-once"
_SQLITE_WRITE_ONCE = f"""
CREATE TRIGGER IF NOT EXISTS {WRITE_ONCE_TRIGGER} BEFORE UPDATE ON standing_grants
WHEN OLD.consumed_at IS NOT NULL OR OLD.consumed_job_id IS NOT NULL
     OR NEW.consumed_at IS NULL OR NEW.consumed_job_id IS NULL
BEGIN SELECT RAISE(ABORT, '{_WRITE_ONCE_MSG}'); END
"""
_PG_WRITE_ONCE_FN = f"""
CREATE OR REPLACE FUNCTION {WRITE_ONCE_TRIGGER}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.consumed_at IS NOT NULL OR OLD.consumed_job_id IS NOT NULL
     OR NEW.consumed_at IS NULL OR NEW.consumed_job_id IS NULL THEN
    RAISE EXCEPTION '{_WRITE_ONCE_MSG} (grant %)', OLD.id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$
"""
_PG_WRITE_ONCE_TRIGGER = (f"CREATE TRIGGER {WRITE_ONCE_TRIGGER} BEFORE UPDATE ON standing_grants "
                          f"FOR EACH ROW EXECUTE FUNCTION {WRITE_ONCE_TRIGGER}()")


def _create_write_once(target, connection, **_kw) -> None:
    """The guard is created WITH the table (so a fresh database needs no migration);
    `install_guards` adds it to a table that predates it."""
    if connection.dialect.name == "postgresql":
        connection.execute(text(_PG_WRITE_ONCE_FN))
        connection.execute(text(_PG_WRITE_ONCE_TRIGGER))
    else:
        connection.execute(text(_SQLITE_WRITE_ONCE))


event.listen(StandingGrant.__table__, "after_create", _create_write_once)


def _has_write_once(conn) -> bool:
    if conn.dialect.name == "postgresql":
        return bool(conn.execute(text(
            "SELECT 1 FROM pg_trigger WHERE tgname = :n AND NOT tgisinternal "
            "AND tgrelid = 'standing_grants'::regclass AND tgenabled <> 'D'"),
            {"n": WRITE_ONCE_TRIGGER}).scalar())
    return bool(conn.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=:n"),
        {"n": WRITE_ONCE_TRIGGER}).scalar())


def install_guards(engine) -> list[str]:
    """M-3: make consumption write-once IN THE DATABASE. Any UPDATE of a grant row that is
    already consumed, or that leaves it unconsumed, is refused by a trigger -- so a role with
    the runbook's column UPDATE cannot reset consumed_at to NULL and re-consume, and no UPDATE
    can touch a grant except the one NULL -> consumed transition. Run by the migration owner
    (`Database.create_all`); idempotent; never by the issuer or worker role."""
    Base.metadata.create_all(engine, tables=[StandingGrant.__table__,
                                             StandingGrantSlot.__table__], checkfirst=True)
    with engine.begin() as conn:
        if _has_write_once(conn):
            return []
        _create_write_once(None, conn)
    return [f"standing_grants: {WRITE_ONCE_TRIGGER} trigger installed"]


def ensure_tables(db) -> None:
    """The grant store must exist WITH its write-once guard. A role that may not create them
    (the issuer and worker under the runbook) only checks: the migration owner creates them
    (`Database.create_all` -> `install_guards`). Missing -> a refusal, never a lazy CREATE
    that would fail with a permission error mid-pass (review M-5)."""
    from sqlalchemy import inspect

    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        insp = inspect(engine)
        have = all(insp.has_table(t) for t in ("standing_grants", "standing_grant_slots"))
        if have:
            with engine.connect() as conn:
                have = _has_write_once(conn)
        if not have:
            try:
                install_guards(engine)
            except Exception as exc:  # noqa: BLE001 - not the owner: refuse, do not crash
                raise GrantRefused(
                    "the grant store or its write-once guard is missing and this role may "
                    f"not create it ({type(exc).__name__}); the migration owner creates it "
                    "(Database.create_all)") from None
        setattr(engine, _FLAG, True)


# ---- who may sign --------------------------------------------------------------------------

_PROCESS = {"issuer": False, "job": False, "issuer_key_at_boot": False}
KEY_EXPOSED_INCIDENT = "standing_grant_issuer_key_exposed:"


def mark_issuer_process() -> None:
    """Called only by `app/issuer_entry.main`: this process is the policy issuer."""
    _PROCESS["issuer"] = True


def mark_job_process() -> bool:
    """A job process never mints a grant: the issuer signing key is scrubbed (worker boot).

    HIGH-2: the scrub is NOT the boundary. `os.environ.pop` leaves the key in the process's
    exec environment (/proc/<pid>/environ) and in the service's settings, so whether the key
    was here is recorded BEFORE the scrub and the boot report states it (Mode S + a P1)."""
    _PROCESS["job"] = True
    if str(os.environ.get(SP.ISSUER_KEY_VAR) or "").strip():
        _PROCESS["issuer_key_at_boot"] = True
    return os.environ.pop(SP.ISSUER_KEY_VAR, None) is not None


def _exec_environ_has(var: str) -> bool:
    """The process's exec environment (Linux /proc/self/environ): what a scrub cannot undo."""
    try:
        with open("/proc/self/environ", "rb") as fh:
            raw = fh.read()
    except OSError:
        return False
    prefix = var.encode() + b"="
    return any(item.startswith(prefix) and item[len(prefix):].strip()
               for item in raw.split(b"\0"))


def issuer_key_present(env=None) -> bool:
    """Was the issuer signing key ever in THIS process: its env now, before a scrub, or its
    exec environment. `env` given (a test or a report about another environment) reads only
    that mapping plus the recorded boot fact."""
    if _PROCESS["issuer_key_at_boot"]:
        return True
    if env is not None:
        return bool(str(env.get(SP.ISSUER_KEY_VAR) or "").strip())
    return (bool(str(os.environ.get(SP.ISSUER_KEY_VAR) or "").strip())
            or _exec_environ_has(SP.ISSUER_KEY_VAR))


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


# M-3: what a role can actually do to the grant store, not what it is called. Every entry is
# a power a WORKER must not have; the issuer may have only the INSERTs.
_TABLE_POWERS = (("standing_grants", "INSERT"), ("standing_grants", "DELETE"),
                 ("standing_grants", "TRUNCATE"), ("standing_grants", "TRIGGER"),
                 ("standing_grant_slots", "INSERT"), ("standing_grant_slots", "UPDATE"),
                 ("standing_grant_slots", "DELETE"), ("standing_grant_slots", "TRUNCATE"),
                 ("standing_grant_slots", "TRIGGER"))
_SIGNED_COLUMNS = ("policy_row_id", "policy_version", "scope", "release", "digest",
                   "detail_json", "seal", "issued_at", "expires_at", "id")
_ISSUER_MAY = {"INSERT standing_grants", "INSERT standing_grant_slots"}


def _role_powers(session, role: str | None = None) -> list[str]:
    """Write powers `role` (default: this session's role) has over the grant store, read from
    PostgreSQL's own catalogue: superuser, membership in the tables' owner role (an owner can
    drop the write-once guard), table privileges and UPDATE on any signed column."""
    who = role if role is not None else str(session.execute(text("SELECT current_user"))
                                            .scalar())
    out = []
    r = session.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
                        {"r": who}).first()
    if r is None:
        return [f"role {who!r} does not exist"]
    if r[0]:
        out.append("superuser")
    for table in ("standing_grants", "standing_grant_slots"):
        if session.execute(text(
                "SELECT pg_has_role(:r, c.relowner, 'MEMBER') FROM pg_class c "
                "WHERE c.oid = to_regclass(:t)"), {"r": who, "t": table}).scalar():
            out.append(f"owns {table}")
    for table, priv in _TABLE_POWERS:
        if session.execute(text("SELECT has_table_privilege(:r, :t, :p)"),
                           {"r": who, "t": table, "p": priv}).scalar():
            out.append(f"{priv} {table}")
    for col in _SIGNED_COLUMNS:
        if session.execute(text("SELECT has_column_privilege(:r, 'standing_grants', :c, "
                                "'UPDATE')"), {"r": who, "c": col}).scalar():
            out.append(f"UPDATE standing_grants.{col}")
    return out


def _db_powers(db, role: str | None = None) -> list[str] | None:
    """None off PostgreSQL (no roles to separate), ["unreadable ..."] if the catalogue read
    fails (which keeps Mode S)."""
    try:
        with db.session() as s:
            if s.get_bind().dialect.name != "postgresql":
                return None
            return _role_powers(s, role)
    except Exception as exc:  # noqa: BLE001
        return [f"unreadable ({type(exc).__name__})"]


def clock_skew_seconds(db) -> float | None:
    """This process's clock minus the database's, in seconds (LOW: refuse beyond 30 s)."""
    try:
        return (datetime.now(timezone.utc) - _db_now(db)).total_seconds()
    except Exception:  # noqa: BLE001
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
        "db_powers": _db_powers(db),
        "clock_skew_s": clock_skew_seconds(db),
        "at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    # The issuer's own (signed) reading of the role the worker says it uses: a worker report
    # can be wrong or forged, the issuer's catalogue read of that role cannot be.
    try:
        _wat, wrk = _latest(db, WORKER_COMPONENT)
    except Exception:  # noqa: BLE001
        wrk = None
    wrole = (wrk or {}).get("db_user")
    detail["worker_role"] = wrole
    detail["worker_role_powers"] = _db_powers(db, wrole) if wrole else None
    detail["seal"] = _sign(HEARTBEAT_DOMAIN, detail)
    slo.record_heartbeat(db, ISSUER_COMPONENT, instance=ISSUER_HOST, detail=detail, now=now)
    return detail


def process_report(db, component: str, *, now: datetime | None = None, env=None) -> dict:
    """A worker's or web process's own report: which keys it holds (fingerprints only)."""
    from . import slo

    present = issuer_key_present(env)
    env = os.environ if env is None else env
    detail = {
        "issuer_verify_fp": _env_fp(SP.ISSUER_VERIFY_KEY_VAR, env),
        "issuer_signing_present": present,
        "policy_signing_fp": _env_fp(SP.SIGNING_KEY_VAR, env),
        "policy_verify_fp": _env_fp(SP.VERIFY_KEY_VAR, env),
        "embedded_worker": str(env.get(SP.EMBEDDED_VAR, "1")),
        "db_user": _db_user(db),
        "db_powers": _db_powers(db),
        "at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    slo.record_heartbeat(db, component, instance=component, detail=detail, now=now)
    if present:
        _key_exposed_incident(db, component, now=now)
    return detail


def _key_exposed_incident(db, component: str, *, now=None) -> None:
    """A non-issuer process held the grant-issuer signing key: P1. Mode T is refused while
    that process's latest report says so; the key must be rotated (it may have been read)."""
    from . import incident_lifecycle

    with db.session() as s:
        incident_lifecycle.open_or_restate(
            s, signature=f"{KEY_EXPOSED_INCIDENT}{component}", severity="P1",
            summary=(f"The {component} process held {SP.ISSUER_KEY_VAR} (the standing-grant "
                     f"signing key). Only the policy-issuer service may hold it: remove the "
                     f"variable from that service and rotate the issuer key pair. Mode T is "
                     f"refused until a clean report."),
            detail={"component": component, "var": SP.ISSUER_KEY_VAR}, now=now)


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
            continue
        if comp == ISSUER_COMPONENT:
            # LOW: the issuer's freshness is its SIGNED time, never the row's own `at` (any
            # writer could re-insert an old signed heartbeat as a new row).
            try:
                at = _aware(datetime.fromisoformat(str(d.get("at"))))
            except (TypeError, ValueError):
                reasons.append("the issuer heartbeat carries no readable signed time")
                continue
        if now - at > HEARTBEAT_FRESH:
            reasons.append(f"the {comp} report is older than {HEARTBEAT_FRESH}")
        elif at - now > CLOCK_SKEW:
            reasons.append(f"the {comp} report is dated after now (clock disagreement)")
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
    if iss is not None:
        skew = iss.get("clock_skew_s")
        if skew is not None and (not isinstance(skew, (int, float))
                                 or abs(skew) > CLOCK_SKEW.total_seconds()):
            reasons.append(f"the issuer's clock and the database's disagree by {skew!r} s "
                           f"(at most {CLOCK_SKEW.total_seconds():g})")
    users = {c: (rows[c] or {}).get("db_user") for c in rows}
    iu, wu = users[ISSUER_COMPONENT], users[WORKER_COMPONENT]
    separated = False
    if iu and iu == wu:
        reasons.append("the worker and the issuer use the same database role (runbook §2.3 "
                       "not applied)")
    elif iu or wu:
        # On PostgreSQL the separation is judged by real privileges (M-3), not role names: a
        # worker on the owner or a superuser role can write grants whatever it is called.
        before = len(reasons)
        wp = (wrk or {}).get("db_powers")
        if not wu or wp is None:
            reasons.append("the worker reports no database role or privileges")
        elif wp:
            reasons.append(f"the worker's database role {wu!r} can write the grant store: "
                           f"{wp[:4]}")
        xp = (iss or {}).get("worker_role_powers")
        if (iss or {}).get("worker_role") != wu or xp is None:
            reasons.append("the issuer has not checked the worker's database role")
        elif xp:
            reasons.append(f"the issuer reads role {wu!r} as able to write the grant store: "
                           f"{xp[:4]}")
        ip = (iss or {}).get("db_powers")
        if not iu or ip is None:
            reasons.append("the issuer reports no database role or privileges")
        else:
            extra = [x for x in ip if x not in _ISSUER_MAY]
            if extra:
                reasons.append(f"the issuer's database role {iu!r} can bypass the grant "
                               f"store's own limits: {extra[:4]}")
        separated = len(reasons) == before
    return {"mode": "S" if reasons else "T", "reasons": reasons,
            "db_roles_separated": separated}


# ---- the owner's database-role runbook (§2.3), one source for the doc and the PG test --------

ISSUER_ROLE, WORKER_ROLE = "bl_issuer", "bl_worker"
# Tables the issuer writes. owner_actions/incidents: a HOLD becomes an owner card (review M-5:
# without these the first out-of-policy request raised a permission error mid-pass).
ISSUER_INSERT_TABLES = ("standing_grants", "standing_grant_slots", "audit_log",
                        "ops_runtime_samples", "incidents", "owner_actions")
ISSUER_UPDATE_TABLES = ("ops_leases", "incidents", "owner_actions")


def runbook_sql(owner: str, issuer_password: str, worker_password: str) -> list[str]:
    """The statements the owner runs ONCE, as the migration owner `owner` (the role web uses,
    which creates every table), after web has started on this release. Not run by code."""
    def q(v: str) -> str:
        return "'" + str(v).replace("'", "''") + "'"

    def ident(v: str) -> str:
        return '"' + str(v).replace('"', '""') + '"'

    o, i, w = ident(owner), ISSUER_ROLE, WORKER_ROLE
    return [
        f"CREATE ROLE {i} LOGIN PASSWORD {q(issuer_password)} NOSUPERUSER NOCREATEDB "
        f"NOCREATEROLE NOBYPASSRLS",
        f"CREATE ROLE {w} LOGIN PASSWORD {q(worker_password)} NOSUPERUSER NOCREATEDB "
        f"NOCREATEROLE NOBYPASSRLS",
        f"GRANT USAGE ON SCHEMA public TO {i}, {w}",
        # The issuer reads everything and writes only its own rows.
        f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {i}",
        f"GRANT INSERT ON {', '.join(ISSUER_INSERT_TABLES)} TO {i}",
        f"GRANT UPDATE ON {', '.join(ISSUER_UPDATE_TABLES)} TO {i}",
        f"GRANT INSERT ON ops_leases TO {i}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {i}",
        # The worker keeps the DML it has today on every table except the grant store, where
        # it may only mark a grant consumed (and the write-once trigger allows that once).
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {w}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {w}",
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES ON standing_grants, "
        f"standing_grant_slots FROM {w}",
        f"GRANT UPDATE (consumed_at, consumed_job_id, consumed_stage) ON standing_grants "
        f"TO {w}",
        # Several job handlers create their own tables on first use (e.g. radar_concepts):
        # the worker keeps CREATE in the schema. It owns only what it creates, so it still
        # cannot alter, drop or add a trigger to the grant store (owned by `owner`).
        f"GRANT CREATE ON SCHEMA public TO {w}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {w} IN SCHEMA public GRANT ALL ON TABLES TO {o}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {w} IN SCHEMA public GRANT SELECT ON TABLES TO {i}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {w} IN SCHEMA public GRANT ALL ON SEQUENCES "
        f"TO {o}",
        # Tables a later release creates (always by the migration owner).
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {o} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, "
        f"DELETE ON TABLES TO {w}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {o} IN SCHEMA public GRANT SELECT ON TABLES TO {i}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {o} IN SCHEMA public GRANT USAGE, SELECT ON "
        f"SEQUENCES TO {i}, {w}",
    ]


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


# ---- pace (HIGH-1): the owner's signed limits AND the code ceilings, read from the store ----

GRANT_STORE_LOCK = 734543631   # pg_advisory_xact_lock key; distinct from every other in src/


def _serialize(session) -> None:
    """One issuance at a time across every issuer process: the pace read and the slot insert
    happen under this lock, in one transaction."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": GRANT_STORE_LOCK})
    elif dialect == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    else:
        raise GrantRefused(f"the grant store cannot serialize issuance on {dialect}")


def pace_limits(content: dict) -> dict:
    """min(signed policy, code ceiling) on every pace dimension. Unreadable is a refusal."""
    fr = (content or {}).get("frequency") or {}
    out = {}
    for key, name, ceiling in (("max_per_day", "per_day", SP.MAX_PER_DAY),
                               ("max_per_7d", "per_7d", SP.MAX_PER_7D),
                               ("max_outstanding_unconsumed_grants", "outstanding",
                                SP.MAX_OUTSTANDING),
                               ("min_spacing_minutes", "spacing_minutes", None)):
        v = fr.get(key)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise GrantRefused(f"policy frequency.{key} is unreadable ({v!r})")
        out[name] = v if ceiling is None else min(v, ceiling)
    return out


def _aware(at):
    return at if at is None or at.tzinfo else at.replace(tzinfo=timezone.utc)


def pace(session, now: datetime) -> dict:
    """What has been issued, from the grant store itself (every policy: a new policy version
    does not get a fresh day). A grant counts from its issue until the window passes, used
    or not: an expired, unused grant spent its slot ("consumed" here means not outstanding).
    """
    from sqlalchemy import select

    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = now - timedelta(days=7)
    rows = [(_aware(i), _aware(c), _aware(e)) for i, c, e in session.execute(
        select(StandingGrant.issued_at, StandingGrant.consumed_at, StandingGrant.expires_at))]

    def window(start):
        ins = [r for r in rows if r[0] >= start]
        out = sum(1 for _i, c, e in ins if c is None and e > now)
        return {"consumed": len(ins) - out, "outstanding": out}

    last = max((i for i, _c, _e in rows), default=None)
    return {"grants_today": window(day_start), "grants_7d": window(week_start),
            "outstanding": sum(1 for _i, c, e in rows if c is None and e > now),
            "minutes_since_last": None if last is None
            else (now - last).total_seconds() / 60.0}


def pace_facts(db, *, now: datetime | None = None) -> dict:
    """`pace` as the four facts `standing_boundary.classify` reads."""
    ensure_tables(db)
    now = now or _db_now(db)
    with db.session() as s:
        return pace(s, now)


def pace_refusals(p: dict, limits: dict) -> list[str]:
    out = []
    for name, cap in (("grants_today", limits["per_day"]), ("grants_7d", limits["per_7d"])):
        n = p[name]["consumed"] + p[name]["outstanding"]
        if n >= cap:
            out.append(f"{name}: {n} issued; the limit is {cap} (min of policy and code)")
    if p["outstanding"] >= limits["outstanding"]:
        out.append(f"{p['outstanding']} grants outstanding; the limit is "
                   f"{limits['outstanding']} (min of policy and code)")
    m = p["minutes_since_last"]
    if m is not None and m < 0:
        out.append("a standing grant is dated after now: clock disagreement, refused")
    elif m is not None and m < limits["spacing_minutes"]:
        out.append(f"only {m:.1f} minutes since the last grant; the policy needs "
                   f"{limits['spacing_minutes']}")
    return out


PUBLISH_JOB_TYPE = "store.publish"


def job_refusal(db, job_id, slug: str, version: str) -> str | None:
    """LOW: a request's job id is a claim. The grant binds to a job only if that job exists,
    is a store.publish job for this exact slug@version, and has not finished."""
    from ..core.models import Job, JobStatus

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
        inputs = dict(job.inputs or {})
        status = job.status.value if hasattr(job.status, "value") else str(job.status)
        jtype = job.job_type
    if jtype != PUBLISH_JOB_TYPE:
        return f"job {jid} is a {jtype} job, not {PUBLISH_JOB_TYPE}"
    if status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
        return f"job {jid} is {status}"
    if str(inputs.get("slug")) != str(slug) or str(inputs.get("version")) != str(version):
        return (f"job {jid} publishes {inputs.get('slug')}@{inputs.get('version')}, "
                f"not {slug}@{version}")
    return None


def issue(db, *, slug: str, version: str, release: str, job_id: int,
          now: datetime | None = None, request_id: int | None = None) -> dict:
    """Issue one SEG, or raise `GrantRefused` with every reason. Issuer process only."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from ..core.models import AuditLog
    from . import publication_authority as PA
    from . import standing_issuer as SI

    why = issuer_signing_refusal()
    if why:
        raise GrantRefused(why)
    ensure_tables(db)
    if now is None:
        # LOW: the issuer's clock must agree with the database's (both directions).
        skew = clock_skew_seconds(db)
        if skew is None or abs(skew) > CLOCK_SKEW.total_seconds():
            raise GrantRefused(f"the issuer's clock and the database's disagree by {skew!r} s")
        now = _db_now(db)
    if (mode := mode_report(db, now=now))["mode"] != "T":
        raise GrantRefused("deployment is not Mode T: " + "; ".join(mode["reasons"][:4]))
    eff = SP.effective(db, now=now)
    if eff.get("state") != SP.EFFECTIVE:
        raise GrantRefused(f"no effective standing policy: {eff.get('why')}")
    if why := job_refusal(db, job_id, slug, version):
        raise GrantRefused(f"the request's job is not valid: {why}")
    decided = SI.decide(db, slug, version, release, now=now)
    if decided.get("decision") != "ISSUE":
        raise GrantRefused(f"out of policy: {decided.get('reasons') or decided.get('why')}")
    content_policy = eff["content"]
    limits = pace_limits(content_policy)          # min(signed policy, code ceiling), each
    scope = f"{slug}@{version}"
    day = now.date().isoformat()
    with db.session() as s:                       # a cheap refusal before any snapshot
        why = pace_refusals(pace(s, now), limits)
    if why:
        raise GrantRefused("; ".join(why))
    snapshot = PA.snapshot(db, slug, version, release)
    ttl = min(int(SP.SEG_TTL_MINUTES), int(SP.SEG_TTL_CEILING_MINUTES))
    try:
        with db.session() as s:
            # HIGH-1: the pace is re-read and enforced in the SAME transaction as the slot
            # insert, under one store-wide lock, so two passes (or two issuers) cannot both
            # read "one left" and both insert.
            _serialize(s)
            p = pace(s, now)
            why = pace_refusals(p, limits)
            if why:
                raise GrantRefused("; ".join(why))
            used_today = set(s.scalars(select(StandingGrantSlot.slot_no).where(
                StandingGrantSlot.policy_row_id == eff["approval_id"],
                StandingGrantSlot.day == day)))
            free = [n for n in range(1, SP.MAX_PER_DAY + 1) if n not in used_today]
            if not free:
                raise GrantRefused(f"all {SP.MAX_PER_DAY} of today's grant slots are used")
            body = {
                "schema": SCHEMA, "action": "store.publish", "scope": scope,
                "release": str(release), "content": snapshot, "digest": PA.digest(snapshot),
                "shop": {"shop_id": SI._shop_id(db), "shop_name": SI._shop_name()},
                "classification": {"class_id": decided.get("class_id"),
                                   "effective_risk_class": decided.get("effective_risk")},
                "policy": {"row_id": eff["approval_id"],
                           "version": int(content_policy.get("version") or 0),
                           "seal": eff.get("seal"), "activation_row_id": eff.get("activation_id")},
                "budget": {"day": day, "slot_no": free[0],
                           "seven_day_count_before": p["grants_7d"]["consumed"]
                           + p["grants_7d"]["outstanding"], "limits": limits},
                "job_id": int(job_id), "nonce": secrets.token_hex(16),
                "issued_at": now.isoformat(), "not_before": now.isoformat(),
                "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
                "issuer_key_fp": fingerprint(_public_of(_key(SP.ISSUER_KEY_VAR))),
                "issuer_host": ISSUER_HOST,
            }
            seal = _sign(DOMAIN, body)
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
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError

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
    # M-3: the SIGNED window decides, not the unsigned expires_at column.
    try:
        nb = datetime.fromisoformat(str(body["not_before"]))
        ex = datetime.fromisoformat(str(body["expires_at"]))
    except (KeyError, TypeError, ValueError):
        raise GrantRefused(f"standing grant {grant_id} carries no readable signed window") \
            from None
    nb, ex = _aware(nb), _aware(ex)
    if now >= ex:
        raise GrantRefused(f"standing grant {grant_id} expired at {ex.isoformat()} (signed)")
    if now < nb - CLOCK_SKEW:
        raise GrantRefused(f"standing grant {grant_id} is not valid before {nb.isoformat()}")
    # M-3: the policy is re-read at use. A suspended, revoked, expired or replaced policy (or
    # a deployment no longer in Mode T) voids every grant it backed that is still unused.
    eff = SP.effective(db, now=now)
    pol = body.get("policy") or {}
    if eff.get("state") != SP.EFFECTIVE:
        raise GrantRefused(f"standing grant {grant_id} is void: no effective standing policy "
                           f"at use ({eff.get('why')})")
    if eff.get("approval_id") != pol.get("row_id") or eff.get("seal") != pol.get("seal"):
        raise GrantRefused(f"standing grant {grant_id} is void: it was issued under policy "
                           f"row {pol.get('row_id')}, and the effective policy is row "
                           f"{eff.get('approval_id')}")
    try:
        with db.session() as s:
            hit = s.execute(update(StandingGrant).where(
                StandingGrant.id == int(grant_id), StandingGrant.consumed_at.is_(None),
                StandingGrant.consumed_job_id.is_(None), StandingGrant.expires_at > now).values(
                consumed_at=now, consumed_job_id=int(job_id), consumed_stage=str(stage)[:40]))
            if hit.rowcount != 1:
                raise GrantRefused(f"standing grant {grant_id} is used, expired or gone")
            s.add(AuditLog(actor="worker", action=CONSUMED, artifact=body.get("scope", ""),
                           detail={"grant_id": int(grant_id), "job_id": int(job_id),
                                   "stage": str(stage)[:40]}))
    except DBAPIError as exc:
        # The database's own write-once guard or UNIQUE(consumed_job_id).
        raise GrantRefused(f"the grant store refused consumption of {grant_id} "
                           f"({type(exc.orig).__name__})") from None
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
    """The issuer's answer to one request: a grant, or a recorded refusal.

    Review M-5: ANY failure (a permission error writing the HOLD card, a database error) is a
    refusal for this request, recorded, so the request is answered and never re-read first on
    every later pass. Fail closed: no grant was issued (issue() inserts in one transaction)."""
    import logging

    from ..core.models import AuditLog

    try:
        got = issue(db, slug=req["slug"], version=req["version"], release=req["release"],
                    job_id=req["job_id"], now=now, request_id=req["request_id"])
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded refusal
        why = (str(exc) if isinstance(exc, GrantRefused)
               else f"issuer error, refused ({type(exc).__name__}: {str(exc)[:200]})")
        try:
            with db.session() as s:
                s.add(AuditLog(actor=ACTOR, action=HELD,
                               artifact=f"{req['slug']}@{req['version']}",
                               detail={"request_id": req["request_id"], "why": why[:400]}))
        except Exception:  # noqa: BLE001 - cannot even record: logged, the pass goes on
            logging.getLogger("brambleloop.issuer").exception(
                "could not record the refusal of grant request %s", req.get("request_id"))
        return {"request_id": req["request_id"], "issued": False, "why": why}
    return {"request_id": req["request_id"], "issued": True, "grant_id": got["grant_id"]}
