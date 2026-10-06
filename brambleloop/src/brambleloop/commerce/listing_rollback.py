"""A defined rollback for a live listing field that changed behind our back (F-518).

The census (`etsy.listing_census`) detects a certified field Etsy no longer holds and opens a
halting reconcile incident; it never overwrites (F-544). What was missing was the other half
of a safe change: *what exactly would restore it, and when must a restore stop*. This module
is that half.

- `plan()` turns one drift observation into a rollback plan: for every drifted field that
  `updateListing` can write, the certified value to restore; for every drifted field it
  cannot (price and quantity go through the inventory endpoint; state goes only through
  activation), an explicit owner step. The plan carries a fingerprint of the remote listing
  it was computed from and its stop conditions.
- `execute()` is the only path that sends it, and it refuses unless every stop condition is
  clear at the moment of execution: the phase is past shadow, the owner's write grant is
  present, the listing still holds exactly what the plan was computed from (anything else
  means somebody changed it again, and a blind restore would overwrite their change), and the
  read-back after the write shows the certified values. Every attempt -- refused, failed or
  restored -- is a `listing.lifecycle` row with before/after state.

In shadow this module never writes; the plan is attached to the drift incident so the owner
sees the exact restore that would run.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

#: Fields the census compares that the inventory endpoint, not updateListing, owns.
INVENTORY_FIELDS = ("price", "quantity")


class RollbackRefused(RuntimeError):
    """A stop condition held; nothing was sent."""


def fingerprint(remote: dict) -> str:
    """A stable digest of the fields a restore would touch, as Etsy holds them."""
    keep = {k: remote.get(k) for k in sorted(remote) if k in _COMPARED}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


_COMPARED = ("title", "description", "tags", "materials", "taxonomy_id", "type", "price",
             "quantity", "who_made", "when_made", "is_supply", "should_auto_renew")


def _writable() -> frozenset[str]:
    from ..integrations.etsy import UPDATE_WRITABLE

    return frozenset(UPDATE_WRITABLE) - {"state"}


def _norm(v: Any) -> Any:
    if isinstance(v, list):
        return sorted(str(x).strip().lower() for x in v)
    if isinstance(v, str):
        return v.strip()
    return v


def plan(*, listing_id: str, slug: str | None, version: str | None, certified: dict,
         remote: dict) -> dict:
    """The restore that would bring `remote` back to `certified`, and when it must stop."""
    from ..integrations import etsy_verify

    writable = _writable()
    restore: dict[str, Any] = {}
    owner_steps: list[str] = []
    # The same comparison the census used to call it drift, so a plan never restores a
    # field the census did not report and never misses one it did.
    verdict = etsy_verify.verify(certified, remote, expect_state="")
    for m in verdict.summary()["mismatched"]:
        field_name, want, have = m["field"], certified.get(m["field"]), m["remote"]
        if field_name in writable:
            restore[field_name] = want
        elif field_name in INVENTORY_FIELDS:
            owner_steps.append(f"{field_name}: certified {want!r}, Etsy holds {have!r} -- "
                               f"restored through the inventory endpoint, not updateListing")
        else:
            owner_steps.append(f"{field_name}: certified {m['sent']!r}, Etsy holds {have!r}; "
                               f"not writable by updateListing")
    return {
        "listing_id": str(listing_id), "slug": slug, "version": version,
        "restore": restore, "owner_steps": owner_steps,
        "remote_fingerprint": fingerprint(remote),
        "stop_conditions": [
            "phase is shadow: nothing is sent",
            "no owner write grant at execution time",
            "the listing changed again since this plan was computed (fingerprint differs)",
            "the read-back after the write does not show the certified values",
        ],
        "executes_automatically": False,
    }


def _live_phase(db) -> str:
    """The effective phase re-resolved now (environment AND the owner's recorded path)."""
    try:
        from ..core.phase import effective

        return str(effective(db, record_incident=False))
    except Exception:  # noqa: BLE001 - an unresolvable phase is no authority
        return "shadow"


def _publishing_phases() -> frozenset[str]:
    from ..integrations.etsy import PHASES_THAT_MAY_PUBLISH

    return frozenset(PHASES_THAT_MAY_PUBLISH)


def execute(db, client, rollback: dict, *, grant=None, actor: str = "store_operator") -> dict:
    """Send the plan's restore once every stop condition is clear; record the outcome.

    Raises `RollbackRefused` (after recording the refusal) when a stop condition holds.
    """
    from . import listing_lifecycle as lifecycle

    lid = rollback["listing_id"]

    def refuse(why: str, before: dict | None = None) -> None:
        lifecycle.record(db, action="rollback", listing_id=lid, actor=actor,
                         evidence="commerce.listing_rollback.execute", before=before or {},
                         result=f"refused: {why}", slug=rollback.get("slug"),
                         version=rollback.get("version"),
                         rollback={"plan": rollback, "sent": False})
        raise RollbackRefused(why)

    if not rollback.get("restore"):
        refuse("the plan restores no updateListing field")
    phase = _live_phase(db)
    if phase not in _publishing_phases():
        refuse(f"phase is {phase}: a rollback is a live write")
    if grant is None:
        refuse("no owner write grant was presented at execution time")
    current = client.get_listing(lid)
    before = {k: current.get(k) for k in rollback["restore"]}
    if fingerprint(current) != rollback["remote_fingerprint"]:
        refuse("the listing changed again after the plan was computed; a blind restore "
               "would overwrite that change", before)
    client.update_listing(lid, dict(rollback["restore"]), grant=grant)
    after_full = client.get_listing(lid)
    after = {k: after_full.get(k) for k in rollback["restore"]}
    still = [k for k, v in rollback["restore"].items() if _norm(after.get(k)) != _norm(v)]
    result = "restored" if not still else f"read-back still differs on {still}"
    lifecycle.record(db, action="rollback", listing_id=lid, actor=actor,
                     evidence="updateListing then getListing read-back", before=before,
                     after=after, result=result, slug=rollback.get("slug"),
                     version=rollback.get("version"),
                     rollback={"plan": rollback, "sent": True, "unrestored": still})
    return {"listing_id": lid, "restored": not still, "unrestored": still,
            "before": before, "after": after}
