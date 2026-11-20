"""ENG-ETSY-PUBLISH slice 2: before any create, adopt the draft that already exists.

`draft_intent` refuses a second create while this system's own intent record exists, and
`draft_resolver` settles an intent whose outcome is unknown. Neither covers a draft that is
on Etsy with **no local intent at all**. That happens after a database restore from before the
create, after `listing.draft_withdrawn` raced a create, or when someone drafted the listing by
hand. The next `store.publish` then created a second listing with the same title.

So, before the intent is claimed, the shop is read in every listing state
(`LISTING_STATES`, read-only) and judged on content, as `draft_resolver` does:

* **none**: no unbound listing carries the certified title. Create as before.
* **adopt**: exactly one unbound **draft** carries the certified title and the certified
  price. It is adopted: the intent is claimed and checkpointed to that id (the path a
  successful create takes), and the publish completes it in place (missing files, images and
  properties) and reads it back. No create request is sent.
* **escalate**: anything else that carries the title. That means two or more drafts, a
  price that differs, or a listing in another state (active, inactive, expired). Nothing is
  created or adopted. One halting incident lists every listing found.
* **unread**: the read failed, hit the paging limit, or returned a row without its own
  state. Nothing is created (fail closed, transient, so the job retries).

Nothing here writes to Etsy.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

NONE, ADOPT, ESCALATE, UNREAD = "none", "adopt", "escalate", "unread"
ADOPTED = "store.draft_adopted"
ESCALATED = "store.draft_adoption_escalated"
INCIDENT = "store.draft_adoption:"
PAGE = 100
MAX_PAGES = 50


def _certified(db, slug: str, version: str) -> dict | None:
    from ..core.models import Listing

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version)
                       .order_by(desc(Listing.id)).limit(1))
        if row is None:
            return None
        return {"title": row.title, "price_cad": round(float(row.price_cad or 0), 2)}


def read_shop(client) -> tuple[list[dict] | None, str | None]:
    """Every shop listing in every state, or (None, why). An incomplete read is None."""
    from ..integrations.etsy import LISTING_STATES

    out: list[dict] = []
    try:
        for state in LISTING_STATES:
            got = list(client.get_shop_listings(state=state, limit=PAGE,
                                                max_pages=MAX_PAGES) or [])
            if len(got) >= PAGE * MAX_PAGES:
                return None, f"{len(got)} {state} listings read, the paging limit"
            stateless = [str(d.get("listing_id") or "?") for d in got if not d.get("state")]
            if stateless:
                return None, (f"{len(stateless)} listing(s) under state={state!r} carry no "
                              f"state of their own")
            out.extend(got)
    except Exception as exc:  # noqa: BLE001 - an unread shop is UNKNOWN, never empty
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(exc, EtsyAuthNeedsOwner):
            raise
        return None, f"{type(exc).__name__}: {str(exc)[:200]}"
    return out, None


def judge(db, *, slug: str, version: str, listings: list[dict]) -> dict:
    """Pure: the verdict for one release against the shop's listings."""
    from .draft_resolver import _bound_ids, _price, norm_title

    certified = _certified(db, slug, version)
    if certified is None:
        return {"verdict": ESCALATE, "why": "no local listing for this release",
                "found": []}
    bound = _bound_ids(db)
    want = norm_title(certified["title"])
    found: list[dict[str, Any]] = []
    for d in listings:
        lid = str(d.get("listing_id") or "")
        if not lid or lid in bound or norm_title(d.get("title")) != want:
            continue
        found.append({"listing_id": lid, "state": str(d.get("state") or ""),
                      "price": _price(d)})
    if not found:
        return {"verdict": NONE, "why": None, "found": [], "certified": certified}
    drafts = [f for f in found if f["state"] == "draft"
              and f["price"] == certified["price_cad"]]
    if len(found) == 1 and len(drafts) == 1:
        return {"verdict": ADOPT, "listing_id": drafts[0]["listing_id"], "found": found,
                "certified": certified, "why": None}
    why = ("more than one unbound listing carries the certified title" if len(found) > 1 else
           f"the listing carrying the certified title is {found[0]['state']!r}"
           if found[0]["state"] != "draft" else
           "the draft carrying the certified title has a different price")
    return {"verdict": ESCALATE, "found": found, "certified": certified, "why": why}


def check(db, client, *, slug: str, version: str) -> dict:
    """Read the shop and judge. Escalations open one halting incident (idempotent)."""
    listings, why = read_shop(client)
    if listings is None:
        return {"verdict": UNREAD, "why": why, "found": []}
    out = judge(db, slug=slug, version=version, listings=listings)
    if out["verdict"] == ESCALATE:
        from ..ops import incident_lifecycle as lifecycle

        with db.session() as s:
            lifecycle.open_or_restate(
                s, signature=f"{INCIDENT}{slug}@{version}", severity="P1",
                product_slug=slug, halts_publication=True,
                summary=(f"An Etsy listing already carries the certified title of "
                         f"{slug}@{version} and cannot be adopted automatically "
                         f"({out['why']}); no second listing was created."),
                detail={"found": out["found"][:10], "why": out["why"]})
    return out
