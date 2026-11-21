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

    def create_draft(self, payload, **kw) -> str:      # type: ignore[override]
        listing_id = super().create_draft(payload, **kw)
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
# Leftover and duplicate recovery (ENG-ETSY-RECOVERY, D-OWNER-ETSY-EXERCISE-2)
#
# A leftover is a draft the exercise created and has not confirmed gone. A duplicate is a
# second such draft, left when an earlier run's cleanup failed and the next run made another.
# Both are recovered the same way, under one rule: this code deletes a listing only when all
# of the following hold, and leaves everything else alone and reports it.
#
# 1. OWN. The ledger (`DRAFT_CREATED`, written by `_Breadcrumbs` before the id was returned)
#    names the listing id, the ledger title carries the exercise marker, Etsy's title equals
#    the ledger title exactly (or the exercise's own "<title> updated" rename of it), and the ledger's shop id (when recorded) is this client's shop.
#    A marked draft that is not in the ledger is FOREIGN: a marker can be typed by anybody.
# 2. DRAFT. Etsy lists the id in the shop's own `state=draft` listing read, and that row says
#    `state == "draft"`.
# 3. NEVER ACTIVE. Etsy has no transition from active back to draft (deactivation gives
#    `inactive`), so an Etsy draft has not been live. Separately, this system holds no
#    `etsy.activate` effect intent for the id, and Etsy reports no views or favourites. If the
#    intent table cannot be read, "never active" is not provable and nothing is deleted.
#
# A delete counts only after read-back: `getListing` answers 404 AND the id is absent from a
# fresh `state=draft` shop read. Both, because a `getListing` that cannot see drafts would
# make a single 404 look like success. A failed or unverified delete is reported, never hidden.

#: The fixed vocabulary of a recovery's per-listing outcomes. Counts are reported by these
#: names only; ids and titles stay inside the report for the owner queue and never reach
#: `factory_visibility`.
RECOVERY_OUTCOMES = (
    "removed_verified",    # own draft deleted; read-back confirms it is gone
    "already_gone",        # in the ledger, and Etsy no longer holds it; ledger settled
    "delete_failed",       # own draft; the delete raised (status class recorded)
    "delete_unverified",   # own draft; the delete was accepted but read-back still finds it
    "left_not_draft",      # in the ledger, but Etsy holds it in a non-draft state: untouched
    "left_not_provable",   # in the ledger and a draft, but a check failed: untouched
    "left_foreign",        # a marked draft that the ledger does not name: untouched
    "index_lag_gone",      # listed as a marked draft, but the ledger verified it gone and a
                           # fresh getListing 404s: Etsy's listings index lagging the delete
    "could_not_ask",       # Etsy could not be read for this listing: untouched
)
RECOVERED = "etsy.exercise_recovery"


def _status_class(error: BaseException | None, client: EtsyClient | None = None) -> str:
    """A fixed-vocabulary class for a failure: the HTTP status bucket, or the error type."""
    if error is not None and type(error).__name__ == "EtsyNotPermitted":
        return "refused_by_client"
    status = 0
    if client is not None and client.calls:
        try:
            status = int(client.calls[-1].get("status") or 0)
        except (TypeError, ValueError):
            status = 0
    if status in (401, 403, 404, 409, 429):
        return f"http_{status}"
    if status >= 500:
        return "http_5xx"
    if status >= 400:
        return "http_4xx"
    if isinstance(error, TransientError):
        return "transient"
    return "other"


def _state_class(state: str) -> str:
    state = str(state or "").lower()
    return state if state in ("draft", "active", "inactive", "removed", "expired",
                              "sold_out", "edit") else ("" if not state else "other")


def _activation_recorded(db, listing_id: str) -> bool | None:
    """Whether this system ever recorded an activation intent for the id. None: unreadable."""
    try:
        from ..queue.effects import EffectIntent, ensure_table

        ensure_table(db)   # idempotent; an absent table means no intent was ever written
        with db.session() as s:
            rows = list(s.scalars(select(EffectIntent.idem).where(
                EffectIntent.effect == "etsy.activate")))
    except Exception:   # noqa: BLE001 - unreadable means "not provable", never "no"
        return None
    return any(str(idem).split(":", 1)[0] == str(listing_id) for idem in rows)


def _ledger_rows(db) -> list[dict]:
    """Every exercise draft the ledger names and has not settled, with its recorded shop id."""
    from ..core.models import AuditLog

    open_ids = {r["listing_id"]: r for r in outstanding_drafts(db)}
    if not open_ids:
        return []
    shops: dict[str, str] = {}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == DRAFT_CREATED)):
            d = row.detail or {}
            lid = str(d.get("listing_id") or "")
            if lid in open_ids:
                shops[lid] = str(d.get("shop_id") or "")
    return [{**r, "shop_id": shops.get(lid, "")} for lid, r in open_ids.items()]


def _drafts_by_id(client: EtsyClient) -> dict[str, dict]:
    return {str(row.get("listing_id") or ""): row
            for row in client.get_shop_listings(state="draft")}


def recover_with(client: EtsyClient, db, *,
                 sleep: Callable[[float], None] = time.sleep) -> dict:
    """Remove the exercise's own leftover and duplicate drafts; leave and report the rest.

    Never raises for an Etsy failure: each listing's outcome is one of `RECOVERY_OUTCOMES`.
    The returned `listings` carry ids and titles for the owner queue; `counts` and `cleaned`
    are the only parts meant for wider reporting.
    """
    counts = {k: 0 for k in RECOVERY_OUTCOMES}
    listings: list[dict] = []
    status_classes: dict[str, int] = {}

    def note(outcome: str, row: dict, **extra) -> None:
        counts[outcome] += 1
        listings.append({"listing_id": row.get("listing_id", ""),
                         "title": row.get("title", ""), "outcome": outcome, **extra})
        if extra.get("status_class"):
            status_classes[extra["status_class"]] = status_classes.get(
                extra["status_class"], 0) + 1

    our_shop = str(getattr(client.credentials, "shop_id", "") or "")
    try:
        drafts = _drafts_by_id(client)
    except (PermanentError, TransientError) as e:
        ledger = _ledger_rows(db)
        for row in ledger:
            note("could_not_ask", row, status_class=_status_class(e, client))
        return {"ok": False, "counts": counts, "cleaned": 0, "listings": listings,
                "status_classes": status_classes, "shop_read": False}

    ledger = _ledger_rows(db)
    ledger_ids = {r["listing_id"] for r in ledger}

    # Marked drafts the ledger does not name: never touched. A marked draft whose id the
    # ledger already verified gone is Etsy's index lagging the delete, but only if Etsy
    # also answers 404 for it now. Anything else is left_foreign.
    gone = verified_gone_ids(db)
    for lid, row in drafts.items():
        title = str(row.get("title") or "")
        if title.startswith(etsy_probe.TEST_TITLE_PREFIX) and lid not in ledger_ids:
            if lid in gone and _gone_now(client, lid) is True:
                note("index_lag_gone", {"listing_id": lid, "title": title})
            else:
                note("left_foreign", {"listing_id": lid, "title": title})

    for row in ledger:
        lid = row["listing_id"]
        on_etsy = drafts.get(lid)
        if on_etsy is None:
            # Not among the shop's drafts. Gone, or held in another state: ask the listing.
            try:
                exists, state = client.listing_exists(lid)
            except (PermanentError, TransientError) as e:
                note("could_not_ask", row, status_class=_status_class(e, client))
                continue
            if not exists:
                _audit(db, DRAFT_REMOVED, {
                    "listing_id": lid, "title": row["title"],
                    "confirmed_by": ("recovery read of Etsy: getListing 404 and absent from "
                                     "the shop's draft listing")})
                note("already_gone", row)
            else:
                note("left_not_draft", row, state_class=_state_class(state))
            continue

        # Provably own, draft, never active -- every check, or nothing is deleted.
        checks = {
            "ledger_title_marked": row["title"].startswith(etsy_probe.TEST_TITLE_PREFIX),
            # Exactly the ledger title, or the exercise's own step-3 rename of it
            # (`etsy_probe.run_exercise` sends "<title> updated"). Nothing looser.
            "etsy_title_matches_ledger": str(on_etsy.get("title") or "") in (
                row["title"], f"{row['title']} updated"),
            "same_shop": (not row.get("shop_id") or not our_shop
                          or str(row["shop_id"]) == our_shop)
                         and (on_etsy.get("shop_id") in (None, "")
                              or not our_shop or str(on_etsy.get("shop_id")) == our_shop),
            "state_is_draft": str(on_etsy.get("state") or "").lower() == "draft",
            "no_views_or_favourites": not any(
                isinstance(on_etsy.get(k), (int, float)) and on_etsy.get(k) > 0
                for k in ("views", "num_favorers")),
            "no_activation_recorded": _activation_recorded(db, lid) is False,
        }
        failed = sorted(k for k, ok in checks.items() if not ok)
        if failed:
            note("left_not_provable", row, failed_checks=failed)
            continue

        try:
            accepted = bool(client.delete_listing(lid, expect_states=("draft",)))
        except (PermanentError, TransientError) as e:
            note("delete_failed", row, status_class=_status_class(e, client))
            continue
        if not accepted:
            note("delete_failed", row, status_class="not_accepted")
            continue
        try:
            exists, state = client.listing_exists(lid)
            still_draft = lid in _drafts_by_id(client)
            # ETSY-EXERCISE-FIX: both signals are still required. When getListing already
            # 404s but the listings index still lists the id, the index is given a bounded
            # time to catch up (READ_BACK_WAITS) before the delete is called unverified.
            for wait in READ_BACK_WAITS[1:]:
                if exists or not still_draft:
                    break
                sleep(wait)
                exists, state = client.listing_exists(lid)
                still_draft = lid in _drafts_by_id(client)
        except (PermanentError, TransientError) as e:
            note("delete_unverified", row, status_class=_status_class(e, client))
            continue
        if exists or still_draft:
            note("delete_unverified", row,
                 state_class=_state_class(state) if exists else "draft")
            continue
        _audit(db, DRAFT_REMOVED, {
            "listing_id": lid, "title": row["title"],
            "confirmed_by": ("recovery delete, then getListing 404 and absent from the "
                             "shop's draft listing")})
        note("removed_verified", row)

    left = sum(counts[k] for k in RECOVERY_OUTCOMES
               if k not in ("removed_verified", "already_gone", "index_lag_gone"))
    report = {"ok": left == 0, "counts": counts,
              "cleaned": counts["removed_verified"] + counts["already_gone"],
              "listings": listings, "status_classes": status_classes, "shop_read": True}
    _audit(db, RECOVERED, {"ok": report["ok"], "counts": counts,
                           "cleaned": report["cleaned"], "status_classes": status_classes})
    return report


def recover(db, *, env: dict[str, str] | None = None, transport: Any = None) -> dict:
    """`recover_with`, on the exercise's own non-activating client, under `single_flight`.

    Raises `ExerciseRefused` / `ExerciseBusy` exactly as `run` does. Stranded own drafts still
    on Etsy afterwards go to the owner queue (once per listing) as before.
    """
    import os

    env = env if env is not None else dict(os.environ)
    transport = transport if transport is not None else UrllibTransport()
    with single_flight(db):
        client = _client(db, env, transport, breadcrumbs=False)
        report = recover_with(client, db)
        stuck = [r for r in report["listings"]
                 if r["outcome"] in ("delete_failed", "delete_unverified")]
        report["owner_actions"] = raise_owner_actions(db, stuck)
        return _redactor(client)(report)


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


#: ETSY-EXERCISE-FIX: waits (seconds) between shop read-backs while a marked draft that the
#: ledger has verified gone is still listed. Etsy's listings index lags a delete that
#: getListing already reports (production attempt 1: verify_cleanup deleted_and_gone and
#: ledger_confirmed_gone 1, yet the read-back listed the draft). The total is bounded at
#: 195 s. Retries happen only while such a lagging row exists, never for a draft that is not
#: proven gone.
READ_BACK_WAITS = (0, 5, 10, 20, 40, 60, 60)


def verified_gone_ids(db) -> set[str]:
    """Listing ids the ledger closed with a read of Etsy (`DRAFT_REMOVED` + `confirmed_by`)."""
    from ..core.models import AuditLog

    if db is None:
        return set()
    out: set[str] = set()
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == DRAFT_REMOVED)):
            d = row.detail or {}
            if str(d.get("listing_id") or "") and str(d.get("confirmed_by") or "").strip():
                out.add(str(d["listing_id"]))
    return out


def _gone_now(client: EtsyClient, listing_id: str) -> bool | None:
    """True only if Etsy answers getListing 404 for this id now. None: could not ask."""
    try:
        exists, _state = client.listing_exists(listing_id)
    except (PermanentError, TransientError):
        return None
    return not exists


def shop_read_back(client: EtsyClient, db=None, *,
                   waits: tuple = READ_BACK_WAITS,
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    """Ask Etsy what drafts the shop holds. The report's own opinion is not evidence.

    `run_exercise` reports `shop_is_clean` from the list it kept while it worked. That list is
    right about what this run did and knows nothing about what a killed run did, so the state
    that decides whether the shop is clean is read from Etsy here, after everything else.

    The query is `getListingsByShop?state=draft`: drafts are the only state the exercise
    creates, and Etsy's `state` filter is what keeps active products out of it. Each marked
    row is judged **by id**:

    - not in the ledger's verified-gone set: it remains, and the shop is not clean;
    - in that set, and getListing answers 404 *now*: it is the listings index lagging a
      delete that Etsy has already carried out. The read is repeated (`waits`, bounded)
      while any such row is listed. If the index still lists it at the end, it is reported
      as `index_lag_verified_gone`, not as remaining;
    - in that set, but getListing finds it, or cannot be asked: it remains. The ledger
      being wrong does not make the shop clean.
    """
    gone = verified_gone_ids(db)
    attempts, waited = 0, 0.0
    last_error = None
    remaining: list[dict] = []
    lagging: list[dict] = []
    drafts: list[dict] = []
    for i, wait in enumerate(waits or (0,)):
        if i and wait:
            sleep(wait)
            waited += wait
        attempts += 1
        try:
            drafts = list(client.get_shop_listings(state="draft"))
        except (PermanentError, TransientError) as e:
            last_error = e
            continue
        last_error = None
        remaining, lagging = [], []
        for row in drafts:
            title = str(row.get("title") or "")
            if not title.startswith(etsy_probe.TEST_TITLE_PREFIX):
                continue
            lid = str(row.get("listing_id") or "")
            entry = {"listing_id": lid, "title": title,
                     "state_class": _state_class(str(row.get("state") or ""))}
            if lid and lid in gone:
                now_gone = _gone_now(client, lid)
                if now_gone is True:
                    lagging.append(entry)
                    continue
                entry["ledger_says_gone_but"] = ("still_held" if now_gone is False
                                                 else "could_not_ask")
            remaining.append(entry)
        if not lagging:
            break
    if last_error is not None:
        return {"ok": False, "error": str(last_error), "attempts": attempts,
                "waited_seconds": waited,
                "note": ("Etsy could not be asked for the shop's drafts, so this run cannot "
                         "state that the shop is clean. The breadcrumb ledger is the only "
                         "remaining record")}
    return {"ok": not remaining, "drafts_in_shop": len(drafts),
            "test_drafts_remaining": remaining,
            "index_lag_verified_gone": lagging,
            "attempts": attempts, "waited_seconds": waited,
            "measured_by": ("a read of Etsy's own draft list filtered on this module's "
                            "title marker, each marked row judged by id against the "
                            "ledger's verified-gone set and a fresh getListing, not by "
                            "anything the run recorded about itself")}


def chosen_test_node(db) -> dict:
    """WS5 E2: the node and craft property the exercise's test draft is filed under.

    From the newest `etsy.taxonomy_refreshed` row (the category matcher's choices against
    Etsy's real tree): the first CHOSEN category's node and, from the stored schema, its
    property that offers "Crochet". Nothing recorded, nothing chosen, or no stored schema:
    UNKNOWN, and the run files under the default node and skips the property step -- so the
    two claims stay unsettled rather than reading as proven."""
    from sqlalchemy import select

    from ..commerce import category as cat
    from ..core.models import AuditLog, EtsyTaxonomySnapshot
    from .etsy_taxonomy import REFRESHED_ACTION

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == REFRESHED_ACTION)
                       .order_by(AuditLog.id.desc()).limit(1))
        detail = dict(row.detail or {}) if row is not None else {}
        sid = detail.get("snapshot_id")
        snap = s.get(EtsyTaxonomySnapshot, sid) if isinstance(sid, int) else None
        properties = dict(snap.properties or {}) if snap is not None else {}
    for category, choice in sorted((detail.get("category_choices") or {}).items()):
        if not isinstance(choice, dict) or choice.get("status") != cat.CHOSEN:
            continue
        node = choice.get("taxonomy_id")
        if not isinstance(node, int):
            continue
        prop = cat.crochet_property({"properties": properties}, node) if properties else None
        # Review 6818959626 (E2 HIGH): updateListingProperty requires `values` as well as
        # `value_ids` (Etsy's OpenAPI; ETSY_REQUIREMENTS.md); the value's own name is sent.
        if prop and not (isinstance(prop.get("value"), str) and prop["value"].strip()):
            prop = None
        return {"status": "CHOSEN", "category": str(category)[:40], "taxonomy_id": node,
                "property": ({"property_id": prop["property_id"],
                              "value_ids": [prop["value_id"]],
                              "values": [prop["value"]]} if prop else None),
                "why": "" if prop else "no stored schema offers 'Crochet' (with its value name) "
                                       "for this node"}
    return {"status": "UNKNOWN", "taxonomy_id": None, "property": None,
            "why": ("no etsy.taxonomy_refreshed row with a CHOSEN category; the test draft is "
                    "filed under the default node and the property step is skipped")}


def run(db, *, env: dict[str, str] | None = None, transport: Any = None,
        mode: str = "full", verify: Callable[[], dict] | None = None,
        sweep_first: bool = True,
        read_back_sleep: Callable[[float], None] = time.sleep) -> dict:
    """The whole operator-triggered run. Returns a report; raises only for a refusal.

    `sweep_first=False` (the autonomous directive path) skips `etsy_probe.sweep`, which
    deletes any marked draft by title alone; that path runs `recover` first instead, which
    deletes only drafts the ledger proves are its own.

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
        # W4-LAUNCHFIX review F-4: the run's own breadcrumbs are those written after this id.
        start_id = _last_audit_id(db)
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
            # WS5 E2: the minimal operation also proves the digital file, the category
            # matcher's chosen node and its craft property -- each written and read back.
            chosen = chosen_test_node(db)
            report["chosen_node"] = chosen
            # ENG-ETSY-RECOVERY: settle the exercise's own leftover/duplicate drafts first.
            # If one of its own drafts cannot be removed, no new draft is created: a delete
            # that fails now would fail again and strand one more draft per run.
            report["recovery"] = recover_with(client, db, sleep=read_back_sleep)
            rc = report["recovery"]["counts"]
            if rc["delete_failed"] or rc["delete_unverified"]:
                report["exercise"] = {
                    "skipped": ("recovery could not remove one of this exercise's own "
                                "drafts, so no new draft was created"),
                    "verified": False, "steps": [], "claims": [],
                    "against_etsy": etsy_probe.against_etsy(client)}
            else:
                report["exercise"] = etsy_probe.run_exercise(
                    client, cleanup=True, sweep_first=sweep_first,
                    ping_reachable=reachable,
                    pattern=etsy_probe.transport_test_pdf("brambleloop-exercise"),
                    taxonomy_id=chosen.get("taxonomy_id"),
                    listing_property=chosen.get("property"))
            report["against_etsy"] = report["exercise"].get("against_etsy")
            # ETSY-EXERCISE-FIX: the ledger is settled first, so the read-back can judge a
            # listed marked draft by id against what Etsy has already confirmed gone.
            report["breadcrumbs"] = reconcile(client, db)
            report["shop_read_back"] = shop_read_back(client, db, sleep=read_back_sleep)
            stranded = report["breadcrumbs"]["still_on_etsy"]
        else:
            report["against_etsy"] = etsy_probe.against_etsy(client)
            report["exercise"] = {
                "skipped": ("mode=rotation. No draft is created, no image is uploaded and "
                            "nothing is deleted: the rotation proof is two authenticated "
                            "shop reads, which is the safest form this evidence takes.")}
            report["breadcrumbs"] = reconcile(client, db)
            report["shop_read_back"] = shop_read_back(client, db, sleep=read_back_sleep)
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
                "failed": [c.get("check") for c in checks
                           if not c.get("ok") and not c.get("advisory")],
                # review 6789501427: an advisory is degraded, never a failure
                "warnings": [c.get("check") for c in checks
                             if not c.get("ok") and c.get("advisory")]}
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
                                  "rotations": redacted["after"]["oauth"]["rotations"],
                                  # W4-LAUNCHFIX D1: which claim this run settled, per claim,
                                  # so `gates.first_customer.check_etsy_remote_state` judges
                                  # recorded evidence. Names and states only, after redaction.
                                  "against_etsy": bool(redacted.get("against_etsy")),
                                  "claims": _claim_states(redacted),
                                  # ENG-ETSY-RECOVERY: why, in fixed vocabulary only.
                                  "cause": outcome_cause(redacted)})
        # W4-LAUNCHFIX review F-2/F-4/F-5: the evidence the first-customer gate reads is a
        # sealed, chained row, bound to this run's own drafts and to the transport it used.
        report_seal = _seal_evidence(db, mode=mode, report=redacted, start_id=start_id,
                                     transport=transport)
        redacted["evidence"] = report_seal
        return redacted


_WORD = __import__("re").compile(r"^[a-z][a-z0-9_]{0,47}$")


def _word(value: Any) -> str | None:
    v = str(value or "")
    return v if _WORD.match(v) else None


def status_class(status: Any) -> str:
    """The fixed class of a `_status` string."""
    s = str(status or "")
    if s.startswith(LIVE_STATUS_PREFIX):
        return "clean"
    if s.startswith("ATTEMPTED, AND THE SHOP IS NOT CLEAN"):
        return "shop_not_clean"
    if s.startswith("ATTEMPTED -- the shop is clean"):
        return "failed_shop_clean"
    if s.startswith("RAN AGAINST A LOCAL MODEL"):
        return "not_against_etsy"
    return "unknown" if s else "none"


def status_class_of(status: Any) -> str:
    """The fixed class of an HTTP status recorded on a step (0: never reached Etsy)."""
    try:
        code = int(status or 0)
    except (TypeError, ValueError):
        return "other"
    if code == 0:
        return "not_sent"
    if code in (400, 401, 403, 404, 409, 413, 415, 429):
        return f"http_{code}"
    if code >= 500:
        return "http_5xx"
    return "http_4xx" if code >= 400 else f"http_{code // 100}xx"


def outcome_cause(report: dict) -> dict:
    """Why a run was or was not clean: step names, taxonomy outcome names and counts only.

    No listing id, title or Etsy message: every string is checked against `_WORD`, so this is
    safe to show wherever a count may be shown (`factory_visibility`).
    """
    ex = report.get("exercise") or {}
    steps = [st for st in ex.get("steps") or [] if isinstance(st, dict)]
    failed = [w for w in (_word(st.get("step")) for st in steps if st.get("ok") is False) if w]
    outcomes: dict[str, int] = {}
    for st in steps:
        name = _word(st.get("step"))
        if name not in ("sweep", "create_draft", "cleanup", "verify_cleanup"):
            continue
        for f in st.get("classified") or []:
            w = _word((f or {}).get("outcome") if isinstance(f, dict) else None)
            if w:
                outcomes[f"{name}:{w}"] = outcomes.get(f"{name}:{w}", 0) + 1
    # ETSY-EXERCISE-FIX: attempt 1 recorded that upload_image and verify_contract failed and
    # not why. Every other step's taxonomy outcomes are recorded too, plus the HTTP status
    # class of each failed step that reached Etsy.
    step_outcomes: dict[str, int] = {}
    failed_status: dict[str, str] = {}
    for st in steps:
        name = _word(st.get("step"))
        if not name or name in ("sweep", "create_draft", "cleanup", "verify_cleanup"):
            continue
        for f in st.get("classified") or []:
            w = _word((f or {}).get("outcome") if isinstance(f, dict) else None)
            if w is None and isinstance(f, dict) and f.get("outcome") == "UNCLASSIFIED":
                w = "unclassified"
            if w:
                step_outcomes[f"{name}:{w}"] = step_outcomes.get(f"{name}:{w}", 0) + 1
        if st.get("ok") is False and "http_status" in st:
            failed_status[name] = status_class_of(st.get("http_status"))
    image = next((st.get("image") for st in steps
                  if st.get("step") == "upload_image" and isinstance(st.get("image"), dict)),
                 None) or {}
    rb = report.get("shop_read_back") or {}
    bc = report.get("breadcrumbs") or {}
    rec = report.get("recovery") or {}
    return {"failed_steps": failed[:12], "cleanup_outcomes": outcomes,
            "exercise_skipped": bool(ex.get("skipped")),
            "step_outcomes": step_outcomes,
            "failed_status_classes": failed_status,
            "image_sent": {"format": _word(str(image.get("format") or "").lower()),
                           "width": int(image.get("width") or 0),
                           "height": int(image.get("height") or 0),
                           "bytes": int(image.get("bytes") or 0)} if image else {},
            "read_back_ok": rb.get("ok") is True,
            "marked_drafts_in_shop": len(rb.get("test_drafts_remaining") or []),
            "index_lag_verified_gone": len(rb.get("index_lag_verified_gone") or []),
            "read_back_attempts": int(rb.get("attempts") or 0),
            "ledger_confirmed_gone": len(bc.get("confirmed_gone") or []),
            "ledger_still_on_etsy": len(bc.get("still_on_etsy") or []),
            "ledger_could_not_ask": len(bc.get("could_not_ask") or []),
            "owner_actions": len(report.get("owner_actions") or []),
            "recovery_counts": {k: int((rec.get("counts") or {}).get(k) or 0)
                                for k in RECOVERY_OUTCOMES} if rec else {},
            "recovery_cleaned": int(rec.get("cleaned") or 0) if rec else 0}


def _last_audit_id(db) -> int:
    from sqlalchemy import func

    from ..core.models import AuditLog

    with db.session() as s:
        return int(s.scalar(select(func.max(AuditLog.id))) or 0)


def _run_drafts(db, start_id: int) -> tuple[list[str], list[str]]:
    """The drafts this run created, and those it confirmed gone by a read of Etsy."""
    from ..core.models import AuditLog

    created, removed = [], []
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.id > start_id,
                AuditLog.action.in_((DRAFT_CREATED, DRAFT_REMOVED))).order_by(AuditLog.id)):
            d = row.detail or {}
            lid = str(d.get("listing_id") or "")
            if not lid:
                continue
            if row.action == DRAFT_CREATED:
                created.append(lid)
            elif str(d.get("confirmed_by") or "").strip():
                removed.append(lid)
    return created, removed


def _seal_evidence(db, *, mode: str, report: dict, start_id: int, transport: Any) -> dict:
    """Append the sealed evidence row. Never raises: an unsealable run is reported as such
    and simply proves nothing to the gate (fail closed)."""
    from datetime import datetime, timezone

    created, removed = _run_drafts(db, start_id)
    detail = {"principal": EVIDENCE_PRINCIPAL, "mode": mode, "ok": bool(report.get("ok")),
              "status": str(report.get("status") or ""),
              "against_etsy": bool(report.get("against_etsy")),
              "transport": type(transport).__name__,
              "transport_is_urllib": type(transport) is UrllibTransport,
              "claims": _claim_states(report), "drafts_created": created,
              "drafts_removed_confirmed": removed,
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    try:
        ident = EVIDENCE.append(db, action=EVIDENCE_ACTION, artifact=f"exercise:{mode}",
                                detail=detail)
    except ValueError as exc:
        return {"sealed": False, "why": str(exc)[:200]}
    return {"sealed": True, "evidence_id": ident}


#: W4-LAUNCHFIX review F-2: the sealed family the first-customer gate reads. HMAC under the
#: operator credential (as the owner grant families), hash-chained by `core.sealed_chain`,
#: so a hand-inserted, edited, replayed or deleted row breaks the chain and proves nothing.
EVIDENCE_ACTION = "etsy.exercise_evidence"
EVIDENCE_REVOKED = "etsy.exercise_evidence_revoked"
EVIDENCE_REBASED = "etsy.exercise_evidence_rebased"
EVIDENCE_PRINCIPAL = "system:etsy_exercise"

#: W4-LAUNCHFIX review F-3: Etsy's contract drifts; a round trip older than this proves
#: nothing about today (the policy-reading window is 30 days; the exercise is costlier).
EVIDENCE_MAX_AGE_DAYS = 90


def _seal(detail: dict) -> str:
    import hashlib
    import hmac
    import json
    import os

    from ..core import opsauth

    if not opsauth.configured():
        raise ValueError("operator credential unavailable, so the evidence cannot be sealed")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(),
                    json.dumps(detail, sort_keys=True, separators=(",", ":"),
                               default=str).encode(), hashlib.sha256).hexdigest()


def _make_evidence_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=EVIDENCE_ACTION, revoked=EVIDENCE_REVOKED,
                       rebased=EVIDENCE_REBASED, principal=EVIDENCE_PRINCIPAL, seal=_seal,
                       signature="authority_chain_tamper:etsy_exercise_evidence",
                       label="Etsy exercise evidence")


EVIDENCE = _make_evidence_ledger()


def _claim_states(report: dict) -> list[dict]:
    """`[{claim, state_after}]` from a run's own `etsy_probe.claims()` output, or []."""
    out = []
    for row in (report.get("exercise") or {}).get("claims") or []:
        if isinstance(row, dict) and row.get("claim"):
            out.append({"claim": str(row["claim"]),
                        "state_after": str(row.get("state_after") or "")})
    return out


LIVE_STATUS_PREFIX = "EXERCISED against openapi.etsy.com"


def remote_state_evidence(db, *, now=None) -> dict:
    """W4-LAUNCHFIX D1 (hardened after review F-2..F-5): what the SEALED runs prove. Reads only.

    Only `etsy.exercise_evidence` rows count, and only while their sealed chain verifies
    (`EVIDENCE.refusal`). The newest sealed row that is a full run, finished ok, whose status
    says it ran against openapi.etsy.com, whose requests went to the Etsy host
    (`etsy_probe.against_etsy`, exact host) over the production `UrllibTransport`, is the live
    run. It counts only while younger than `EVIDENCE_MAX_AGE_DAYS`, and its round trip is its
    OWN: at least one draft it created, every one confirmed gone by a read of Etsy, and no
    exercise draft anywhere still outstanding. Claims a later run (sealed or not) marked
    CONTRADICTED are reported; a contradiction can only make the gate fail.
    """
    from datetime import datetime, timezone

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    out = {"live_run_at": None, "live_run_id": None, "verified_claims": [],
           "contradicted_claims": [], "round_trip_clean": False, "drafts_created": 0,
           "drafts_unmatched": [], "runs": 0, "stale": False, "rejected": []}
    if db is None:
        return out
    with db.session() as s:
        sealed = [(r.id, r.actor, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == EVIDENCE_ACTION).order_by(AuditLog.id))]
        finished = [(r.id, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == RUN_FINISHED).order_by(AuditLog.id))]
    out["runs"] = len(sealed)
    live = None
    for rid, actor, d in reversed(sealed):
        why = None
        if actor != EVIDENCE_PRINCIPAL:
            why = "not written by the exercise principal"
        else:
            try:
                why = EVIDENCE.refusal(db, rid)
            except Exception as exc:  # noqa: BLE001 - unverifiable is no evidence
                why = f"unverifiable: {type(exc).__name__}"
        if why is not None:
            out["rejected"].append({"id": rid, "why": str(why)[:160]})
            continue
        if not (d.get("mode") == "full" and d.get("ok") is True
                and str(d.get("status") or "").startswith(LIVE_STATUS_PREFIX)
                and d.get("against_etsy") is True and d.get("transport_is_urllib") is True):
            continue
        live = (rid, d)
        break
    if live is not None:
        rid, d = live
        out["live_run_id"] = rid
        out["live_run_at"] = d.get("recorded_at")
        try:
            at = datetime.fromisoformat(str(d.get("recorded_at")))
            age = (now - at).total_seconds() / 86400.0
        except (TypeError, ValueError):
            age = None
        if age is None or age < 0 or age > EVIDENCE_MAX_AGE_DAYS:
            out["stale"] = True
        else:
            out["verified_claims"] = sorted({
                str(c.get("claim")) for c in d.get("claims") or [] if isinstance(c, dict)
                and c.get("state_after") == "VERIFIED_AGAINST_ETSY"})
        created = [str(x) for x in d.get("drafts_created") or []]
        removed = set(str(x) for x in d.get("drafts_removed_confirmed") or [])
        outstanding = [r["listing_id"] for r in outstanding_drafts(db)]
        out["drafts_created"] = len(created)
        out["drafts_unmatched"] = sorted((set(created) - removed) | set(outstanding))[:10]
        out["round_trip_clean"] = bool(created) and not out["drafts_unmatched"]
        # The live run's own RUN_FINISHED row precedes its sealed row; later ones follow it.
        since_sealed = since_finished = rid
    else:
        since_sealed = since_finished = -1
    contradicted = set()
    for sid, _actor, d in sealed:
        if sid >= since_sealed:
            contradicted |= {str(c.get("claim")) for c in d.get("claims") or []
                             if isinstance(c, dict) and c.get("state_after") == "CONTRADICTED"}
    for fid, d in finished:
        if fid > since_finished:
            contradicted |= {str(c.get("claim")) for c in d.get("claims") or []
                             if isinstance(c, dict) and c.get("state_after") == "CONTRADICTED"}
    out["contradicted_claims"] = sorted(contradicted)
    return out


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
