"""Which `Listing.state` values mean "live on Etsy" (W-ADOPT).

A listing reaches Etsy two ways: the gated `store.publish` path (state `published`) and a
listing the owner made by hand in Shop Manager and adopted with `listing.adopt_manual`
(state `published_manually`). Every reader whose meaning is "live on Etsy" -- verify checks,
readiness, dashboards, the catalogue, ledger evidence, launch gates -- asks here, so a
manually published listing is never counted as not live (a false safety signal) and a new
live state cannot be added in one reader and missed in another.
"""
from __future__ import annotations

PUBLISHED = "published"
PUBLISHED_MANUALLY = "published_manually"

#: Every Listing.state that means the listing is live on Etsy.
LIVE_ON_ETSY: tuple[str, ...] = (PUBLISHED, PUBLISHED_MANUALLY)


def is_live_on_etsy(state) -> bool:
    return str(state or "") in LIVE_ON_ETSY
