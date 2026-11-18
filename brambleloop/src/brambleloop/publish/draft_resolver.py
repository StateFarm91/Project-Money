"""WS5 E6: resolve a draft-creation intent whose remote outcome is unknown (option B).

`draft_intent` refuses every second create once a create may have reached Etsy. The intent
then sits in RECONCILE_REQUIRED, or stays CREATING if the process died, behind a P1
incident that halts publication. Until now nothing ever resolved it.

The create request does not carry our intent key to Etsy, so there is no key to match on.
This resolver matches on content instead, and never adopts on ambiguity. Each run reads the
shop's listings in every state (`getListingsByShop`, LISTING_STATES; read-only) once, then for each unresolved
intent:

* A **candidate** is a draft that:
  - has a title equal to the certified listing's title;
  - has a price equal to the certified price;
  - was created no earlier than the intent minus `CREATE_SKEW`;
  - is not already bound to another local listing or intent.
* **Exactly one candidate** is adopted. It goes through `draft_intent.checkpoint`, the same
  path a successful create takes, so the local listing and the intent record the remote id
  together. The incident resolves with the evidence, and any owner card for it closes.
* **Two or more candidates**, or a draft with the certified title but a different price,
  are **escalated**. One owner card names every candidate, the incident's detail lists
  them, and nothing is adopted. Two identical drafts cannot be told apart, so that case
  always needs a person.
* **Nothing carries the certified title, but a listing was created inside the intent's create
  window under another title** (the draft may have been renamed by hand during the halt; no
  remote id came back to bind on): escalated, never released (review 6957411211, N1).
* **A listing read without its own `state`** makes the whole read undecided (N2).
* **No candidate** is never read as "not created" from one look. The run records the empty
  read on the intent. After `EMPTY_READS` complete empty reads spanning at least
  `EMPTY_SPAN`, the intent is released (deleted, audited) and the incident resolves, so the
  next publish may create once.

A read that fails or is incomplete changes nothing: it is reported unread.

It never creates, edits or deletes anything on Etsy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

CREATE_SKEW = timedelta(minutes=10)
STALE_CREATING = timedelta(hours=2)
EMPTY_READS = 2
EMPTY_SPAN = timedelta(minutes=30)
PAGE = 100
MAX_PAGES = 50
# Review 6954619488 (E6 MEDIUM): every state a shop listing can hold. A draft that was created
# and then activated (or deactivated, expired, sold out) is no longer a draft; reading drafts
# only made it invisible, so its intent was released and the next publish duplicated it.
from ..integrations.etsy import LISTING_STATES  # noqa: E402  (the one list, ws5 N3)

ADOPTED = "draft_intent.adopted_by_match"
ESCALATED = "draft_intent.escalated"
RELEASED = "draft_intent.released_no_remote"
CARD_PREFIX = "draft_reconcile:"


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _created_at(remote: dict) -> datetime | None:
    ts = remote.get("original_creation_timestamp") or remote.get("created_timestamp")
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _price(remote: dict) -> float | None:
    from .manual_adoption import _price as price_of

    amount = price_of(remote).get("amount")
    return None if amount is None else round(float(amount), 2)


def unresolved(db, *, now: datetime) -> list:
    """Intents with no remote id whose outcome is unknown: RECONCILE_REQUIRED, or CREATING
    older than STALE_CREATING (a process that died mid-create runs no `uncertain`)."""
    from .draft_intent import DraftIntent

    with db.session() as s:
        rows = list(s.scalars(select(DraftIntent).where(DraftIntent.remote_id.is_(None))))
        s.expunge_all()
    out = []
    for r in rows:
        if r.state == "RECONCILE_REQUIRED":
            out.append(r)
        elif r.state == "CREATING" and (now - (_aware(r.at) or now)) >= STALE_CREATING:
            out.append(r)
    return out


def _bound_ids(db) -> set[str]:
    """Remote ids some local listing or intent already owns."""
    from ..core.models import Listing
    from .draft_intent import DraftIntent

    with db.session() as s:
        ids = {str(x) for x in s.scalars(select(Listing.etsy_listing_id)) if x}
        ids |= {str(x) for x in s.scalars(select(DraftIntent.remote_id)) if x}
    return ids


def _certified(db, intent) -> dict | None:
    from ..core.models import Listing

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == intent.slug,
                                                 Listing.version == intent.version))
        if listing is None or (listing.release_hash and listing.release_hash != intent.release):
            return None
        return {"title": listing.title, "price_cad": round(float(listing.price_cad or 0), 2)}


def norm_title(title) -> str:
    """A title as two readers of one listing agree on it (review 6954619488, E6 HIGH): Etsy
    returns titles HTML-escaped ("Hat &amp; Scarf"), so both sides are unescaped and their
    whitespace collapsed before they are compared. No other folding: a title that differs in
    any letter is a different title."""
    import html
    import re

    return re.sub(r"\s+", " ", html.unescape(str(title or ""))).strip()


def match(db, intent, drafts: list[dict]) -> dict:
    """{"candidates": [...], "near": [...], "why": str | None} for one intent. Pure read."""
    certified = _certified(db, intent)
    if certified is None:
        return {"candidates": [], "near": [], "certified": None,
                "why": "no local listing bound to the intent's certified release"}
    bound = _bound_ids(db)
    started = _aware(intent.at) or datetime.now(timezone.utc)
    floor, ceiling = started - CREATE_SKEW, started + CREATE_SKEW
    candidates, near, window = [], [], []
    for d in drafts:
        lid = str(d.get("listing_id") or "")
        if not lid or lid in bound:
            continue
        state = str(d.get("state") or "")
        created = _created_at(d)
        entry = {"listing_id": lid, "price": _price(d), "state": state or None,
                 "created": created.isoformat() if created else None}
        if norm_title(d.get("title")) != norm_title(certified["title"]):
            # Review 6957411211 (ws5 N1): the create may have reached Etsy and the draft been
            # renamed by hand during the halt. No remote id came back, so there is no id to
            # bind on; the create's own time window is the binding. An unbound listing created
            # inside it is never read as "no listing", whatever its title: escalated, never
            # released and never adopted.
            if created is not None and floor <= created <= ceiling:
                window.append({**entry, "why": "created inside this intent's create window "
                                               "under another title (renamed by hand?)"})
            continue
        if not state:
            near.append({**entry, "why": "listing state unread"})
        elif state != "draft":
            # The create reached Etsy and the listing has since moved on (activated by hand,
            # deactivated, expired, sold out): never released, never adopted automatically.
            near.append({**entry, "why": f"certified title on a listing now {state!r}"})
        elif created is None or created < floor:
            near.append({**entry, "why": "created before the intent, or creation time unread"})
        elif entry["price"] != certified["price_cad"]:
            near.append({**entry, "why": "certified title but a different price"})
        else:
            candidates.append(entry)
    return {"candidates": candidates, "near": near, "window": window, "certified": certified,
            "why": None}


def _signature(intent) -> str:
    from .draft_intent import key_for

    return "draft-create:" + key_for(intent.slug, intent.version)


def _adopt(db, intent, found: dict, audit) -> dict:
    from ..ops import incident_lifecycle as lifecycle
    from ..ops import owner_queue
    from ..core.models import OwnerAction
    from .draft_intent import checkpoint

    lid = found["candidates"][0]["listing_id"]
    checkpoint(db, intent.key, intent.token, lid)
    why = (f"exactly one shop draft ({lid}) carries the certified title and price and was "
           f"created after the intent; adopted through draft_intent.checkpoint")
    with db.session() as s:
        lifecycle.resolve_signatures(s, [_signature(intent)], resolution=why)
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == CARD_PREFIX + intent.key,
            OwnerAction.done == False))  # noqa: E712
        if row is not None:
            owner_queue.close(row, owner_queue.SATISFIED, why)
    audit(ADOPTED, artifact=f"{intent.slug}@{intent.version}",
          detail={"listing_id": lid, "evidence": found["candidates"][0], "why": why})
    return {"slug": intent.slug, "version": intent.version, "outcome": "adopted",
            "listing_id": lid}


def _escalate(db, intent, found: dict, audit) -> dict:
    from ..core.models import Incident
    from ..ops import owner_queue

    named = found["candidates"] + found["near"]
    ids = ", ".join(c["listing_id"] for c in named) or "none"
    why = found["why"] or (
        f"{len(found['candidates'])} shop draft(s) match the certified listing and "
        f"{len(found['near'])} nearly match; the resolver never adopts on ambiguity")
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == _signature(intent),
                                              Incident.resolved == False))  # noqa: E712
        if inc is not None:
            inc.detail = {**(inc.detail or {}), "candidates": named, "resolver": why}
        owner_queue.ensure(
            s, CARD_PREFIX + intent.key,
            action=(f"Choose which Etsy draft is {intent.slug} {intent.version} "
                    f"(candidates: {ids}), or confirm none is"),
            reason=why, minutes=5, max_cost_cad=0.0,
            consequence_of_delay="publication of this version stays halted",
            blocks=f"{intent.slug}@{intent.version}")
    audit(ESCALATED, artifact=f"{intent.slug}@{intent.version}",
          detail={"candidates": named, "why": why})
    return {"slug": intent.slug, "version": intent.version, "outcome": "escalated",
            "candidates": [c["listing_id"] for c in named]}


def _empty(db, intent, now: datetime, audit) -> dict:
    from ..ops import incident_lifecycle as lifecycle
    from .draft_intent import DraftIntent

    with db.session() as s:
        row = s.get(DraftIntent, intent.key)
        if row is None or row.remote_id:
            return {"slug": intent.slug, "version": intent.version, "outcome": "changed"}
        reads = list((row.detail or {}).get("empty_reads") or []) + [now.isoformat()]
        first = datetime.fromisoformat(reads[0])
        if len(reads) >= EMPTY_READS and now - _aware(first) >= EMPTY_SPAN:
            s.delete(row)
            why = (f"{len(reads)} complete reads of the shop's listings (every state) from "
                   f"{reads[0]} to {reads[-1]} found no listing with the certified title; the "
                   f"create never "
                   f"reached Etsy, so the intent is released")
            lifecycle.resolve_signatures(s, [_signature(intent)], resolution=why)
            released = True
        else:
            row.detail = {**(row.detail or {}), "empty_reads": reads}
            released = False
    if released:
        audit(RELEASED, artifact=f"{intent.slug}@{intent.version}",
              detail={"empty_reads": reads, "why": why})
        return {"slug": intent.slug, "version": intent.version, "outcome": "released"}
    return {"slug": intent.slug, "version": intent.version, "outcome": "awaiting_second_read",
            "empty_reads": len(reads)}


def resolve(db, drafts: list[dict], *, audit, now: datetime | None = None) -> dict:
    """Act on every unresolved intent from one complete read of the shop's drafts."""
    now = now or datetime.now(timezone.utc)
    results = []
    for intent in unresolved(db, now=now):
        found = match(db, intent, drafts)
        if found["why"] is None and len(found["candidates"]) == 1 and not found["near"]:
            results.append(_adopt(db, intent, found, audit))
        elif found["why"] is not None or found["candidates"] or found["near"]:
            results.append(_escalate(db, intent, found, audit))
        elif found.get("window"):
            # N1: nothing carries the certified title, but a listing was created inside the
            # create window under another title. Never an empty read: escalate.
            results.append(_escalate(db, intent, {**found, "near": found["window"]}, audit))
        else:
            results.append(_empty(db, intent, now, audit))
    return {"read": True, "drafts_seen": len(drafts), "intents": results,
            "writes_to_etsy": 0}


def run(db, *, audit, client=None, now: datetime | None = None) -> dict:
    """Read the shop's drafts once and resolve. An unread shop changes nothing."""
    now = now or datetime.now(timezone.utc)
    if not unresolved(db, now=now):
        return {"read": False, "why": "no unresolved draft intent", "intents": []}
    try:
        if client is None:
            from .manual_adoption import _client, _transport

            client = _client(db, _transport())
        if client is None or getattr(client, "credentials", None) is None:
            return {"read": False, "why": "no Etsy read credential; nothing was read",
                    "intents": []}
        drafts = []
        for state in LISTING_STATES:
            got = list(client.get_shop_listings(state=state, limit=PAGE,
                                                max_pages=MAX_PAGES) or [])
            if len(got) >= PAGE * MAX_PAGES:
                # The reader stops at MAX_PAGES without saying so: a full last page may hide
                # more, so nothing is decided on an incomplete read of any state.
                return {"read": False, "intents": [],
                        "why": f"{len(got)} {state} listings read, the paging limit; the read "
                               f"may be incomplete, so nothing was decided"}
            # Review 6957411211 (ws5 N2): a row without its own `state` is refused, never
            # tagged with the state it was queried under -- a filter Etsy did not apply would
            # otherwise let a live listing read as a draft. The whole read is undecided.
            stateless = [str(d.get("listing_id") or "?") for d in got if not d.get("state")]
            if stateless:
                return {"read": False, "intents": [],
                        "why": f"{len(stateless)} listing(s) read under state={state!r} carry "
                               f"no state of their own ({', '.join(stateless[:5])}); nothing "
                               f"was decided"}
            drafts.extend(got)
    except Exception as e:  # noqa: BLE001 - an unread shop is UNKNOWN, never "empty"
        return {"read": False, "why": f"{type(e).__name__}: {e}"[:300], "intents": []}
    return resolve(db, drafts, audit=audit, now=now)
