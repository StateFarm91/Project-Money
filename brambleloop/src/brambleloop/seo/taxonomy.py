"""Taxonomy readiness: which Launch-0 products have a confirmed Etsy category, and which assume one.

A category is **CONFIRMED** only when it was chosen (`commerce.category.choose`) from a
taxonomy snapshot that Etsy itself returned (`integrations.etsy_taxonomy.refresh`, source
`etsy_open_api_v3` *and* a `confirmed_at` stamp, which only `refresh` sets). Anything else is an assumption:

- `GATED(etsy_api)`  no Etsy-read snapshot, and the `etsy_api` gate is closed (no recorded
                     successful `etsy.probe`), so the tree cannot be read. This is the
                     current state of the company.
- `PENDING_REFRESH`  the gate is open but no Etsy-read snapshot exists yet: the next work is
                     `listing.taxonomy_refresh`.
- `UNRESOLVED`       a snapshot exists but holds no crochet-pattern node naming the product.

The numeric ids 2112/2114/2115 seen in earlier rehearsals (Blankets & Afghans, Coasters,
Baskets & Storage) come from `tests/fixtures_etsy_taxonomy.py`, whose docstring says
"The ids and names are illustrative, not Etsy's". They are never reported here as a
category: an assumed category is reported as the product's *intent* (its
`ListingIdentity.etsy_category` and the node terms it would descend by), with no id.
"""
from __future__ import annotations

from datetime import datetime, timezone

CONFIRMED = "CONFIRMED"
GATED = "GATED(etsy_api)"
PENDING_REFRESH = "PENDING_REFRESH"
UNRESOLVED = "UNRESOLVED"
STALE_AFTER_DAYS = 30
FIXTURE_IDS_NOTE = ("2112/2114/2115 are illustrative ids from tests/fixtures_etsy_taxonomy.py, "
                    "not Etsy's; no Launch-0 category id has been read from Etsy")


def _gate(db) -> dict:
    from ..integrations import etsy_taxonomy

    try:
        return etsy_taxonomy.gate(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable gate is a closed one
        return {"open": False, "missing": [f"etsy_api: gate unreadable ({type(exc).__name__})"]}


def _snapshot(db) -> dict | None:
    from ..integrations import etsy_taxonomy

    try:
        return etsy_taxonomy.latest(db)
    except Exception:  # noqa: BLE001 - no table, no snapshot
        return None


def readiness(db, facts_list=None, *, now: datetime | None = None) -> list[dict]:
    """One row per Launch-0 variant: status, the assumed intent, and (when confirmed) the node."""
    from ..commerce import category as category_mod
    from ..integrations import etsy_taxonomy
    from . import facts as facts_mod
    from ._db import as_database

    now = now or datetime.now(timezone.utc)
    dbw = as_database(db)
    facts_list = facts_list if facts_list is not None else facts_mod.launch0_facts()
    gate = _gate(dbw)
    snap = _snapshot(dbw)
    # `refresh` is the only writer that sets `confirmed_at`; a row inserted any other way (a
    # test fixture, a hand insert) carries the column default source but no confirmation.
    etsy_read = bool(snap and snap.get("source") == etsy_taxonomy.SOURCE
                     and snap.get("confirmed_at"))
    rows = []
    for f in facts_list:
        terms = category_mod.CATEGORY_NODE_TERMS.get(f.category, {})
        row = {"slug": f.slug, "candidate": f.candidate, "category_intent": f.category,
               "intent_terms": {k: list(v) for k, v in terms.items()},
               "taxonomy_id": None, "path": [], "properties_complete": None,
               "snapshot": None, "basis": "assumed", "note": FIXTURE_IDS_NOTE}
        if etsy_read:
            choice = category_mod.choose(snap, f.category)
            row["snapshot"] = {"id": snap["id"], "fetched_at": snap["fetched_at"],
                               "source": snap["source"]}
            if choice.status == category_mod.CHOSEN:
                props = category_mod.properties_for(snap, choice, category_mod.Facts(
                    category=f.category, difficulty=f.difficulty,
                    colors=[(c, None) for c in f.colors], season=f.season,
                    width_cm=f.width_cm, height_cm=f.height_cm))
                fetched = snap.get("fetched_at")
                age = None
                if fetched:
                    t = datetime.fromisoformat(fetched)
                    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
                    age = round((now - t).total_seconds() / 86400, 1)
                row.update(status=CONFIRMED, taxonomy_id=choice.taxonomy_id,
                           path=list(choice.path_names), basis="measured",
                           properties_complete=bool(props.get("complete")),
                           property_gaps=list(props.get("gaps") or []),
                           age_days=age, stale=bool(age is not None and age > STALE_AFTER_DAYS),
                           why=choice.why, note="")
            else:
                row.update(status=UNRESOLVED, why=choice.why)
        elif gate.get("open"):
            row.update(status=PENDING_REFRESH,
                       why=("the etsy_api gate is open and no Etsy-read taxonomy snapshot "
                            "exists; run listing.taxonomy_refresh"))
        else:
            why = "; ".join(gate.get("missing") or ["etsy_api gate closed"])
            if snap and not etsy_read:
                why += ("; the stored snapshot was not written by an Etsy read "
                        f"(source {snap.get('source')!r}, confirmed_at "
                        f"{snap.get('confirmed_at')!r})")
            row.update(status=GATED, gated_by="etsy_api", why=why)
        rows.append(row)
    return rows


def counts(rows: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out
