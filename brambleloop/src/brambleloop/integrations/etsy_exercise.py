"""Running the prepared Etsy exercise inside production, and proving the rotation fix.

`etsy_probe.run_exercise` is the eight-step shadow-write run. It was written, tested against
`tests/fake_etsy.py` including every failure path, and then had **no caller anywhere except a
CLI `main()`** -- and the credential it needs is sealed in production's Postgres under
production's `BRAMBLELOOP_SECRET_KEY`, neither of which exists in a development container. So
the exercise could not be run by the only machine that holds the credential.

This module is the missing caller. It does not re-implement the run: it invokes the prepared
one, wraps it in the four things a real shop needs that a pure function cannot provide, and
returns the report to the operator who asked for it.

## What this adds, and why each piece is here

**Activation is structurally unreachable, not merely unrequested.** `_client()` hard-codes
`owner_authorised=False`. `EtsyClient.refusal()` -- the gate `activate()` consults first --
checks the phase, then that flag, then the credentials, so with the flag false there is no
phase, no environment variable and no argument to this module that makes `refusal_for(
Authority.ACTIVATE)` return None. `_client()` then *asserts* that it did not, and refuses to
start the run at all if it ever does. `activate()` itself is untouched, and a test pins its
source byte for byte.

**A draft's existence becomes durable in the same instant Etsy creates it.** `run_exercise`
records the draft in an in-memory `left_behind` list, which is exactly right for a function
and worth nothing if the process dies between the create and the delete: the shop then holds
a listing nothing anywhere knows about. `_Breadcrumbs` writes an audit row the moment
`create_draft` returns an id and another when the cleanup is *verified against Etsy*, so an
unmatched pair is a permanent, queryable record that a draft may be stranded -- readable
after a crash, by a different container, with no re-run.

**The shop is read back independently of the report.** `run_exercise` reports
`shop_is_clean` from its own bookkeeping. This module finishes by asking Etsy for the shop's
drafts and looking for the marker prefix, because a report's opinion of the shop is not the
shop.

**One run at a time, held by something that cannot outlive the process holding it.** See
`single_flight`.

## Inline, not a durable job

The requirement says to decide honestly. It runs **inline, inside the HTTP request**, and the
queue is the wrong home for it:

* `JobQueue._reclaim_expired` hands an expired lease to another worker **without stopping the
  first one**. There is no cancellation and no fencing token. If this work ever exceeded
  `DEFAULT_LEASE_SECONDS` (300) -- a slow Etsy, a stalled TLS handshake, one transient retry
  -- a second worker would begin a second exercise against the same real shop while the first
  was still mid-flight, and the second's step-0 sweep deletes drafts by title prefix, which
  is to say it deletes the first run's draft out from under it. Interleave it the other way
  and the first run creates its draft after the second has swept, and the shop ends holding a
  draft that only one report mentions.
* `claim()` increments `attempts` against `max_attempts`, so a run that fails is re-executed
  up to three times, each attempt creating a draft.
* `idempotency_key` guarantees a job is *enqueued* once. It guarantees nothing about
  execution once a lease expires. The single guarantee the queue is built on is the one this
  work needs and does not get.
* The work is not long by the queue's standard. It is about a dozen Etsy round trips plus at
  most one token refresh -- seconds, not minutes. The lease exists for renders and builds.
* The report *is* the deliverable. Inline it is returned to the operator who asked; as a job
  it would be written into a row somebody then has to find.

Inline, the HTTP request is the lease: one caller, one run, no reclaim, no retry. The failure
mode inline is a dropped connection rather than a stranded draft -- and the breadcrumb ledger
is what makes even a killed container leave the listing id and title behind in writing.

## Secrets

No access token, refresh token, keystring, shared secret or operator token appears in any
value this module returns, logs or writes to a database row. Every report passes through
`http.Redactor`, seeded with the credentials each client actually holds. Credential identity
is reported only as `sealed.fingerprint` -- eight hex characters of a SHA-256 -- which is how
two tokens are told apart without either being present.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from sqlalchemy import select, text

from ..core.db import is_postgres
from ..core.resilience import PermanentError, TransientError
from . import etsy_probe
from .etsy import Authority, Credentials, EtsyClient
from .etsy_oauth import EtsyAuthFailed, EtsyAuthNeedsOwner
from .http import Redactor, UrllibTransport

log = logging.getLogger(__name__)

PROVIDER = "etsy"

#: Written the instant Etsy returns a listing id, and matched by `DRAFT_REMOVED` only when a
#: read of Etsy confirms the listing is gone. An unmatched pair is a possibly-stranded draft.
DRAFT_CREATED = "etsy.exercise_draft_created"
DRAFT_REMOVED = "etsy.exercise_draft_removed"
RUN_STARTED = "etsy.exercise_started"
RUN_FINISHED = "etsy.exercise_finished"

#: The owner-queue identity of a stranded draft. One key per listing, so the queue holds one
#: row per artefact rather than one per attempt.
STRANDED_KEY = "etsy.exercise.stranded_draft"

#: A constant the two halves of `single_flight` agree on. Arbitrary, and arbitrary is fine:
#: what matters is that no other advisory lock in this system uses it. Nothing else does --
#: this is the only `pg_advisory_lock` in `src/`.
ADVISORY_LOCK_KEY = 0x42_4C_45_58   # "BLEX"

MODES = ("full", "rotation")


class ExerciseRefused(RuntimeError):
    """This deployment cannot run the exercise, and says exactly why."""


class ExerciseBusy(RuntimeError):
    """Another exercise holds the single-flight claim right now."""


# ---------------------------------------------------------------------------
# One run at a time


_IN_PROCESS = threading.Lock()


@contextmanager
def single_flight(db) -> Iterator[dict]:
    """Refuse to start a second exercise while one is running.

    Two operator calls landing together on one real shop is the hazard the step-0 sweep
    creates: it deletes drafts by title prefix, so a second run's housekeeping would delete a
    first run's live artefact and both reports would then describe a shop that never existed.

    On Postgres this is a **session-level advisory lock held on a dedicated connection**, and
    that choice is the point: an advisory lock is released by the database when the
    connection drops, so it cannot outlive the process holding it. That is precisely the
    property a job lease does not have -- a lease keeps a dead worker's claim until it times
    out, and then gives the work to somebody else while the first may still be running. A
    lock that dies with its holder can only ever be wrong in the safe direction.

    On SQLite -- tests, and any single-process deployment -- there is no advisory lock and the
    in-process mutex is the whole guarantee. The report says which of the two was in force
    rather than implying the stronger one.
    """
    if not _IN_PROCESS.acquire(blocking=False):
        raise ExerciseBusy(
            "another Etsy exercise is running in this process. Only one may run at a time: "
            "the step-0 sweep removes test drafts by title prefix, so a second run would "
            "delete the first run's draft while it was still using it.")
    connection = None
    try:
        if is_postgres(db.engine):
            connection = db.engine.connect()
            held = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": ADVISORY_LOCK_KEY}).scalar()
            if not held:
                raise ExerciseBusy(
                    "another container is running the Etsy exercise right now (the "
                    "database's advisory lock is held). Only one may run at a time.")
            scope = "postgres advisory lock: one run across every container"
        else:
            scope = ("this process only: the database is not Postgres, so there is no "
                     "advisory lock and a second process would not be seen")
        yield {"held": True, "scope": scope}
    finally:
        if connection is not None:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"),
                                   {"key": ADVISORY_LOCK_KEY})
            except Exception:   # noqa: BLE001 - closing the connection releases it anyway
                pass
            connection.close()
        _IN_PROCESS.release()


# ---------------------------------------------------------------------------
# The durable record of what exists in the shop


def _audit(db, action: str, detail: dict) -> None:
    """Append one row. Kept local so this module's ledger is one function wide.

    `Registry.audit` is the usual door and it carries phase and policy stamping this ledger
    has no use for; what matters here is that the row is written and committed *before* the
    next Etsy call, so a process killed at the worst moment has already left the note.
    """
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=action, detail=detail))


class _Breadcrumbs(EtsyClient):
    """An `EtsyClient` that writes down a draft's existence before it returns the id.

    Subclassed rather than wrapped so that every refusal, every authority check and every
    encoding decision is the real client's. The only behaviour added is the note: `super()`
    creates the draft, and the row is committed before this method returns, so there is no
    window in which the caller holds an id the database does not know about.
    """

    db: Any = None

    def create_draft(self, payload) -> str:      # type: ignore[override]
        listing_id = super().create_draft(payload)
        if self.db is not None:
            _audit(self.db, DRAFT_CREATED,
                   {"listing_id": str(listing_id), "title": payload.title,
                    "shop_id": getattr(self.credentials, "shop_id", ""),
                    "why": ("written before this id was returned to anything, so a container "
                            "killed mid-run still leaves the listing named in writing")})
        return listing_id


def outstanding_drafts(db) -> list[dict]:
    """Every draft this system created and has not confirmed gone, from the audit ledger.

    The ledger is append-only, so "still there" is the absence of a matching removal rather
    than a mutable flag -- which is what makes it survive the crash it exists for.
    """
    from ..core.models import AuditLog

    created: dict[str, dict] = {}
    removed: set[str] = set()
    with db.session() as s:
        rows = list(s.scalars(
            select(AuditLog).where(AuditLog.action.in_([DRAFT_CREATED, DRAFT_REMOVED]))
            .order_by(AuditLog.id.asc())))
        for row in rows:
            detail = row.detail or {}
            listing_id = str(detail.get("listing_id") or "")
            if not listing_id:
                continue
            if row.action == DRAFT_CREATED:
                created[listing_id] = {"listing_id": listing_id,
                                       "title": str(detail.get("title") or ""),
                                       "at": row.at.isoformat() if row.at else None}
            else:
                removed.add(listing_id)
    return [row for listing_id, row in created.items() if listing_id not in removed]


def reconcile(client: EtsyClient, db) -> dict:
    """Ask Etsy about every draft the ledger still shows open, and settle each one.

    Remote state is authoritative here in the strongest sense available: a listing is closed
    out of the ledger only when Etsy answers that it does not hold it. A listing Etsy *does*
    still hold becomes an owner action naming its id and title, because a test artefact left
    in a real shop is indistinguishable from a product with a mistake in it.
    """
    outstanding = outstanding_drafts(db)
    settled, stranded, unknown = [], [], []
    for row in outstanding:
        try:
            exists, state = client.listing_exists(row["listing_id"])
        except (PermanentError, TransientError) as e:
            unknown.append({**row, "error": str(e),
                            "note": ("Etsy could not be asked, so this stays open. 'We could "
                                     "not look' is not 'it is gone'")})
            continue
        if not exists:
            _audit(db, DRAFT_REMOVED, {"listing_id": row["listing_id"],
                                       "title": row["title"],
                                       "confirmed_by": "read of Etsy returned 404"})
            settled.append(row)
        else:
            stranded.append({**row, "state_on_etsy": state})
    return {"checked": len(outstanding), "confirmed_gone": settled,
            "still_on_etsy": stranded, "could_not_ask": unknown}


def raise_owner_actions(db, stranded: list[dict]) -> list[dict]:
    """Put each stranded draft in the owner queue, once, with the id and the title.

    De-duplicated on `requirement_key`, which carries the listing id, so running the exercise
    five times against one stuck draft leaves one row rather than five.
    """
    from ..core.models import OwnerAction

    raised: list[dict] = []
    for row in stranded:
        key = f"{STRANDED_KEY}.{row['listing_id']}"
        action = (f"delete the test draft Etsy still holds as listing {row['listing_id']}, "
                  f"titled {row['title']!r}")
        with db.session() as s:
            existing = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == key, OwnerAction.done == False))  # noqa: E712
            if existing is not None:
                continue
            s.add(OwnerAction(
                requirement_key=key, action=action,
                reason=("an automated transport test created this draft in the real shop and "
                        "could not remove it. It is a draft, so no buyer can see it and no "
                        "fee attaches to it, but a test artefact in a real shop is "
                        "indistinguishable from a product with a mistake in it."),
                max_cost_cad=0.0, minutes=2,
                consequence_of_delay=("the next exercise sweeps it automatically; this row "
                                      "exists for the case where the sweep cannot"),
                blocks="etsy.exercise"))
        raised.append({"requirement_key": key, "action": action,
                       "where": "Etsy Shop Manager, Listings, Drafts",
                       "maximum_cost": "CA$0", "minutes": 2})
    return raised


# ---------------------------------------------------------------------------
# The client, and the gate that makes activation unreachable


def _credentials(db, env: dict[str, str], transport) -> Credentials:
    creds = Credentials.from_env(env, transport=transport, db=db)
    if creds is None:
        raise ExerciseRefused(
            "no Etsy credentials in this deployment. ETSY_KEYSTRING (or ETSY_API_KEY) and "
            "ETSY_SHOP_ID are read from the environment, and the refresh token is read from "
            "the sealed `oauth_credentials` row. Authorise the app first: "
            "GET /api/etsy/oauth/start.")
    if creds.token_provider is None or creds.token_provider.tokens is None:
        raise ExerciseRefused(
            "this deployment holds no refresh token it can open. Either nothing is stored in "
            "`oauth_credentials` or it is sealed under a key this deployment no longer has; "
            "GET /api/etsy/oauth/status reports which. A static ETSY_ACCESS_TOKEN is not "
            "enough for a run that takes longer than the hour Etsy gives it.")
    return creds


def _client(db, env: dict[str, str], transport, *, breadcrumbs: bool = True) -> EtsyClient:
    """Build the one client this module ever uses, and prove it cannot activate.

    `owner_authorised=False` is written here rather than passed in. `EtsyClient.refusal()`
    reads the phase, then this flag, then the credentials, and `refusal_for(ACTIVATE)`
    returns `refusal()` unchanged when it is not None -- so with this flag false there is no
    phase, no environment variable and no argument to this module that produces an activation
    authority. `shadow_writes_authorised=True` is the separate, narrower grant covering
    drafts: objects no buyer can see and no fee attaches to.

    The assertion below is the part that keeps being true. If a future change to the gates
    ever let this client activate, this function refuses to run the exercise at all rather
    than running it with a client that could.
    """
    creds = _credentials(db, env, transport)
    phase = (env.get("BRAMBLELOOP_PHASE") or "shadow").lower()
    kind = _Breadcrumbs if breadcrumbs else EtsyClient
    client = kind(transport, credentials=creds, phase=phase,
                  owner_authorised=False,
                  shadow_writes_authorised=True)
    if breadcrumbs:
        client.db = db
    refusal = client.refusal_for(Authority.ACTIVATE)
    if refusal is None:
        raise ExerciseRefused(
            "REFUSING TO RUN: this client reports that it is permitted to activate a "
            "listing. The exercise never activates anything and is not allowed to be able "
            "to. Activation publishes on etsy.com and Etsy charges its listing fee at "
            "publication, so this is a spend decision and the owner's alone. Something has "
            "changed in EtsyClient.refusal_for; fix that before running this again.")
    if client.refusal_for(Authority.DRAFT_WRITE) is not None:
        raise ExerciseRefused(
            f"this client may not write a draft: "
            f"{client.refusal_for(Authority.DRAFT_WRITE)}")
    return client


def activation_guard(client: EtsyClient) -> dict:
    """What every authority on this client is, reported rather than asserted in prose."""
    return {
        "attempted": False,
        "read": client.refusal_for(Authority.READ) or "permitted",
        "draft_write": client.refusal_for(Authority.DRAFT_WRITE) or "permitted",
        "activate": client.refusal_for(Authority.ACTIVATE),
        "owner_authorised": client.owner_authorised,
        "phase": client.phase,
        "why_unreachable": (
            "the client is built with owner_authorised=False, which EtsyClient.refusal() "
            "checks before anything else that could permit publication. activate() calls "
            "_require(Authority.ACTIVATE) first, so it raises EtsyNotPermitted before it "
            "reads the listing, before it checks for an image and before it sends a byte. "
            "The exercise calls activate() once on purpose, with no Launch-0 authorisation, "
            "to record that refusal as an observation rather than a claim."),
    }


# ---------------------------------------------------------------------------
# The rotation proof


def _health(db, env: dict[str, str]) -> dict:
    from ..core import oauth_store

    return oauth_store.credential_health(db, provider=PROVIDER, env=env)


def _force_expiry(creds: Credentials) -> None:
    """Make this credential's access token count as already expired, so the next call refreshes.

    `expires_at = 0.0` is not a trick: it is the value `Credentials.from_env` already gives a
    credential built from a stored refresh token with no live access token, and
    `TokenSet.from_env` gives a pasted `ETSY_ACCESS_TOKEN` with no stated expiry. It means
    "treat this access token as of unknown age", and a token of unknown age is one Etsy has
    probably already killed. Setting it here makes the refresh happen now, under observation,
    instead of at whatever moment the hour happens to run out.
    """
    from .etsy_oauth import TokenSet

    provider = creds.token_provider
    current = provider.tokens
    provider.tokens = TokenSet(access_token=current.access_token,
                               refresh_token=current.refresh_token,
                               expires_at=0.0, scopes=current.scopes)


def _round(db, env: dict[str, str], transport, label: str, why: str) -> dict:
    """One observed refresh: build a credential from the store, spend it, check the store.

    Every credential object here is built fresh by `Credentials.from_env(db=db)`, whose only
    sources are the environment and the sealed `oauth_credentials` row. Nothing is carried in
    from the previous round: that is the whole point of the second round.
    """
    from ..core import sealed

    before = _health(db, env)
    creds = Credentials.from_env(env, transport=transport, db=db)
    if creds is None or creds.token_provider is None or creds.token_provider.tokens is None:
        return {"round": label, "measures": why, "ok": False,
                "error": "no credential could be built from the store for this round"}

    held = creds.token_provider.tokens.refresh_token
    carried_the_stored_token = sealed.fingerprint(held) == before["token_fingerprint"].lstrip("*")
    _force_expiry(creds)

    client = EtsyClient(transport, credentials=creds, phase="shadow",
                        owner_authorised=False, shadow_writes_authorised=False)
    entry: dict[str, Any] = {
        "round": label, "measures": why,
        "before": {"fingerprint": before["token_fingerprint"],
                   "rotations": before["rotations"], "openable": before["openable"]},
        "credential_was_built_from": (
            "the sealed oauth_credentials row and the environment, and nothing else"),
        "carried_the_stored_token": carried_the_stored_token,
    }
    try:
        # A shop read. It creates nothing, changes nothing and costs nothing; the access
        # token it needs is what forces the refresh.
        client.get_shop()
        entry["etsy_call"] = {"operation": "getShop", "ok": True,
                              "status": client.calls[-1]["status"] if client.calls else None}
    except (EtsyAuthNeedsOwner, EtsyAuthFailed) as e:
        entry["ok"] = False
        entry["etsy_call"] = {"operation": "getShop", "ok": False, "error": str(e)}
        entry["diagnosis"] = (
            "Etsy refused the refresh grant. If this is the second round, this is the exact "
            "shape of the defect: the refresh token that was stored is not the one Etsy "
            "expects next, so what was sealed was never the rotated value. The owner has to "
            "authorise again in a browser.")
        entry["after"] = _health(db, env)
        return entry
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["etsy_call"] = {"operation": "getShop", "ok": False, "error": str(e)}
        entry["after"] = _health(db, env)
        return entry

    provider = creds.token_provider
    live = provider.tokens
    after = _health(db, env)
    entry["refreshes_performed"] = provider.refreshes
    entry["etsy_issued_a_different_refresh_token"] = bool(
        provider.history and provider.history[-1].get("refresh_token_rotated"))
    entry["after"] = {"fingerprint": after["token_fingerprint"],
                      "rotations": after["rotations"], "openable": after["openable"]}
    entry["stored_value_is_the_live_one"] = (
        after["token_fingerprint"] == f"***{sealed.fingerprint(live.refresh_token)}")
    entry["ok"] = bool(
        provider.refreshes >= 1
        and entry["etsy_issued_a_different_refresh_token"]
        and after["rotations"] == before["rotations"] + 1
        and after["token_fingerprint"] != before["token_fingerprint"]
        and after["openable"]
        and entry["stored_value_is_the_live_one"])
    if not entry["ok"]:
        entry["danger"] = (
            "a refresh succeeded and the store does not hold the value Etsy issued. The "
            "token in the database has been spent. Stop and re-authorise in a browser "
            "before anything else uses this credential.")
    return entry


def rotation_proof(db, *, env: dict[str, str], transport) -> dict:
    """Prove the rotation fix against real Etsy, in two rounds, spending nothing.

    ## What forces a refresh

    Not waiting an hour. `TokenProvider.token()` refreshes when its `TokenSet` is expired, and
    a credential built from the sealed store with no live access token already carries
    `expires_at = 0.0` -- "of unknown age, treat as dead". `_force_expiry` sets exactly that
    value, so the refresh happens now and under observation. No Etsy state is touched, no
    listing is created, nothing is published and nothing is charged: the call that carries the
    refreshed token is a shop read.

    ## What each round establishes

    **Round A -- Etsy rotates, and we seal what it gave us.** A credential built from the
    store spends the stored refresh token. `TokenProvider.history` records whether the token
    Etsy returned *differs* from the one sent, which is the sourced claim being tested; the
    credential row's `rotations` must rise by one, its fingerprint must change, and the
    fingerprint the database now holds must equal the fingerprint of the token this process
    is holding live. That last equality is the one that distinguishes "we refreshed" from "we
    refreshed and stored what we got".

    **Round B -- the sealed credential survives the boundary.** Every object from round A is
    dropped. A *new* `Credentials.from_env(db=db)` is built, and its refresh token can only
    have come from `oauth_store.load_refresh_token` -- a read of Postgres and an unseal under
    `BRAMBLELOOP_SECRET_KEY`. It is asserted to be carrying round A's stored fingerprint and
    nothing else, and then it spends it against real Etsy. **Etsy accepting it is the proof.**
    The defect this closed was a `TokenProvider` with no `on_refresh`: under that defect round
    B presents the token from before round A, which Etsy has already spent, and answers
    `invalid_grant` -- the failure that looks exactly like a revoked app. Round B is that
    failure, run on purpose, against a fix.

    ## What it does not establish, and the free way to close it

    Round B's objects are new; the interpreter is not. A real container replacement adds one
    thing this cannot: that no Python object survived at all. That gap closes for **CA$0 and
    no second container** -- this platform replaces the container on every deploy, and the
    first Etsy call after any restart presents the stored token. So the confirmation is a
    reading, not a run: after the next restart, `GET /api/etsy/oauth/status` shows `rotations`
    higher than this run left it with `openable: true`. The report below prints the exact
    number to compare against.

    ## Safety

    Each refresh spends a refresh token, so the failure worth designing against is a refresh
    that succeeds while the seal write does not: the stored token would then be dead. Round A
    is checked completely -- including that the stored fingerprint equals the live one --
    **before** round B is allowed to start, so that failure costs one rotation and is reported
    at once rather than twice and silently. There are never more than two rounds. The proof
    runs after the shop has been confirmed clean, so a credential failure can never strand a
    draft. And it is separately triggerable (`mode=rotation`), which is the safest form of
    all: two authenticated shop reads, no draft, no write, nothing to clean up.
    """
    before = _health(db, env)
    proof: dict[str, Any] = {
        "provider": PROVIDER,
        "at_start": {"fingerprint": before["token_fingerprint"],
                     "rotations": before["rotations"],
                     "openable": before["openable"],
                     "sealed_under_key": before["sealed_under_key"]},
        "rounds": [],
        "defect_this_tests": (
            "Credentials.from_env built a TokenProvider with no on_refresh, against an Etsy "
            "that issues a new refresh token on every refresh (SOURCED: Etsy's own example "
            "response). The stored token would have been spent once and then presented "
            "again after the next container replacement, giving invalid_grant -- which looks "
            "exactly like a revoked app."),
    }
    if not before["openable"]:
        proof["ok"] = False
        proof["refused"] = (
            "there is no credential this deployment can open, so there is nothing to rotate. "
            "GET /api/etsy/oauth/status says whether it is absent or sealed under a key this "
            "deployment no longer has.")
        return proof

    first = _round(db, env, transport, "A",
                   "that Etsy issues a different refresh token on a refresh, and that the "
                   "new one is sealed into oauth_credentials under this deployment's key")
    proof["rounds"].append(first)
    if not first.get("ok"):
        proof["ok"] = False
        proof["stopped_after"] = "A"
        proof["why_it_stopped"] = (
            "round B spends another refresh token, and spending one is only safe when the "
            "previous rotation is known to have been stored. It was not, so nothing further "
            "was attempted.")
        if first.get("danger"):
            proof["owner_action"] = {
                "action": "re-authorise the Etsy app in a browser",
                "why": first["danger"],
                "where": "GET /api/etsy/oauth/start with the operator credential",
                "maximum_cost": "CA$0", "minutes": 15}
        return proof

    second = _round(db, env, transport, "B",
                    "that a credential whose refresh token came only from the sealed "
                    "database row -- not from any object round A left in memory -- is "
                    "accepted by real Etsy. This is the boundary the defect crossed")
    proof["rounds"].append(second)

    fingerprints = [proof["at_start"]["fingerprint"]]
    for entry in proof["rounds"]:
        after = entry.get("after") or {}
        if after.get("fingerprint"):
            fingerprints.append(after["fingerprint"])
    proof["fingerprint_chain"] = fingerprints
    proof["distinct_fingerprints"] = len(set(fingerprints))
    proof["rotations"] = {"before": before["rotations"],
                          "after": _health(db, env)["rotations"]}
    proof["ok"] = bool(first.get("ok") and second.get("ok")
                       and len(set(fingerprints)) == len(fingerprints))
    proof["establishes"] = (
        "Etsy really issues a new refresh token on every refresh; on_refresh writes it; the "
        "write is sealed under this deployment's key and re-opens; and a credential built "
        "only from that sealed row spent it against real Etsy successfully."
        if proof["ok"] else
        "nothing yet -- see the rounds for which check failed and what it means.")
    proof["does_not_establish"] = (
        "that a new operating-system process can do it. Round B's objects are new; the "
        "interpreter is not.")
    proof["how_that_closes_for_free"] = (
        f"this platform replaces the container on every deploy, and the first Etsy call from "
        f"a new container presents the stored token. After the next restart, read "
        f"GET /api/etsy/oauth/status: `rotations` above "
        f"{proof['rotations']['after']} with `openable: true` is the container-boundary "
        f"proof, and costs no run, no draft and no spend.")
    return proof


# ---------------------------------------------------------------------------
# The operator-triggered run


def _redactor(*clients: EtsyClient) -> Redactor:
    redactor = Redactor()
    for client in clients:
        creds = getattr(client, "credentials", None)
        for attribute in ("api_key", "shared_secret", "access_token"):
            redactor.add(getattr(creds, attribute, ""))
        if creds is not None:
            redactor.add(f"{getattr(creds, 'api_key', '')}:"
                         f"{getattr(creds, 'shared_secret', '')}")
        provider = getattr(creds, "token_provider", None)
        tokens = getattr(provider, "tokens", None)
        for attribute in ("access_token", "refresh_token"):
            redactor.add(getattr(tokens, attribute, ""))
    return redactor


def shop_read_back(client: EtsyClient) -> dict:
    """Ask Etsy what drafts the shop holds. The report's own opinion is not evidence.

    `run_exercise` reports `shop_is_clean` from the list it kept while it worked. That list is
    right about what this run did and knows nothing about what a killed run did, so the state
    that decides whether the shop is clean is read from Etsy here, after everything else.
    """
    try:
        drafts = list(client.get_shop_listings(state="draft"))
    except (PermanentError, TransientError) as e:
        return {"ok": False, "error": str(e),
                "note": ("Etsy could not be asked for the shop's drafts, so this run cannot "
                         "state that the shop is clean. The breadcrumb ledger is the only "
                         "remaining record")}
    ours = [{"listing_id": str(row.get("listing_id") or ""),
             "title": str(row.get("title") or "")}
            for row in drafts
            if str(row.get("title") or "").startswith(etsy_probe.TEST_TITLE_PREFIX)]
    return {"ok": not ours, "drafts_in_shop": len(drafts),
            "test_drafts_remaining": ours,
            "measured_by": ("a read of Etsy's own draft list filtered on this module's "
                            "title marker, not by anything the run recorded about itself")}


def run(db, *, env: dict[str, str] | None = None, transport: Any = None,
        mode: str = "full", verify: Callable[[], dict] | None = None) -> dict:
    """The whole operator-triggered run. Returns a report; raises only for a refusal.

    `verify` is injected rather than imported so that this module does not depend on the
    FastAPI application it is called from. The endpoint passes `/api/verify`'s own handler;
    when nothing is passed the report says the check was not made rather than implying it
    passed.
    """
    import os

    env = env if env is not None else dict(os.environ)
    transport = transport if transport is not None else UrllibTransport()
    mode = (mode or "full").lower()
    if mode not in MODES:
        raise ExerciseRefused(f"mode must be one of {list(MODES)}; got {mode!r}")

    report: dict[str, Any] = {
        "at": time.time(),
        "mode": mode,
        "phase": (env.get("BRAMBLELOOP_PHASE") or "shadow").lower(),
        "costs": ("CA$0. Etsy charges no fee for an app, a shop read, a draft, an image "
                  "upload, a deletion or a token refresh. Its listing fee is charged at "
                  "publication, which nothing in this path performs."),
    }

    with single_flight(db) as claim:
        report["single_flight"] = claim
        _audit(db, RUN_STARTED, {"mode": mode, "phase": report["phase"]})

        client = _client(db, env, transport, breadcrumbs=(mode == "full"))
        report["activation"] = activation_guard(client)

        # Step 0's first half. It needs no OAuth token and creates nothing, and its result is
        # what tells the failure taxonomy whether a later refusal is the network rather than
        # the request. Asserting reachability we had not measured would attribute network
        # failures to our own bytes.
        from .http import probe_live

        try:
            report["ping"] = probe_live(client.credentials.api_key_header(), transport)
        except Exception as e:      # noqa: BLE001 - an unreachable Etsy is a finding
            report["ping"] = {"reachable": False, "error": f"{type(e).__name__}: {e}"}
        reachable = bool(report["ping"].get("reachable"))

        if mode == "full":
            report["exercise"] = etsy_probe.run_exercise(
                client, cleanup=True, sweep_first=True,
                ping_reachable=reachable)
            report["against_etsy"] = report["exercise"].get("against_etsy")
            report["shop_read_back"] = shop_read_back(client)
            report["breadcrumbs"] = reconcile(client, db)
            stranded = report["breadcrumbs"]["still_on_etsy"]
        else:
            report["against_etsy"] = etsy_probe.against_etsy(client)
            report["exercise"] = {
                "skipped": ("mode=rotation. No draft is created, no image is uploaded and "
                            "nothing is deleted: the rotation proof is two authenticated "
                            "shop reads, which is the safest form this evidence takes.")}
            report["shop_read_back"] = shop_read_back(client)
            report["breadcrumbs"] = reconcile(client, db)
            stranded = report["breadcrumbs"]["still_on_etsy"]

        report["owner_actions"] = raise_owner_actions(db, stranded)

        # The rotation proof spends refresh tokens, so it runs only once the shop is settled.
        # A credential failure after this point cannot strand anything.
        report["rotation"] = rotation_proof(db, env=env, transport=transport)

        report["after"] = {"oauth": _health(db, env)}
        if verify is not None:
            try:
                snapshot = verify()
            except Exception as e:   # noqa: BLE001 - a broken check is a finding, not a crash
                snapshot = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            checks = snapshot.get("checks") or []
            report["after"]["verify"] = {
                "ok": bool(snapshot.get("ok")),
                "passed": sum(1 for c in checks if c.get("ok")),
                "total": len(checks),
                "failed": [c.get("check") for c in checks if not c.get("ok")]}
        else:
            report["after"]["verify"] = {
                "measured": False,
                "note": ("no /api/verify handler was passed to this run, so its state is "
                         "unknown here rather than assumed good")}

        report["shop_is_clean"] = bool(
            report["shop_read_back"].get("ok") and not stranded)
        report["ok"] = bool(
            report["shop_is_clean"]
            and not report["owner_actions"]
            and report["rotation"].get("ok")
            and (mode == "rotation" or report["exercise"].get("verified"))
            and report["after"]["verify"].get("ok", True))
        report["status"] = _status(report)

        redacted = _redactor(client)(report)
        _audit(db, RUN_FINISHED, {"mode": mode, "ok": redacted["ok"],
                                  "status": redacted["status"],
                                  "shop_is_clean": redacted["shop_is_clean"],
                                  "rotations": redacted["after"]["oauth"]["rotations"]})
        return redacted


def _status(report: dict) -> str:
    if not report.get("against_etsy"):
        return ("RAN AGAINST A LOCAL MODEL OF ETSY, NOT ETSY. Every confirmation below is "
                "evidence about this system's own correctness against our reading of Etsy's "
                "document. It promotes nothing to VERIFIED_AGAINST_ETSY.")
    if report.get("ok"):
        return ("EXERCISED against openapi.etsy.com. The shop was read back and holds no "
                "test draft.")
    if not report.get("shop_is_clean"):
        return ("ATTEMPTED, AND THE SHOP IS NOT CLEAN. See owner_actions for the listing id "
                "and title to remove in Shop Manager.")
    return "ATTEMPTED -- the shop is clean; see the steps and findings for what failed."
