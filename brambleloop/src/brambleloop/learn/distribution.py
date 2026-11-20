"""Multi-channel product distribution from one canonical record (F-772) -- W4-C11.

"A pattern can be distributed through multiple appropriate storefronts/content channels from one
canonical product record. Pricing, version, files, description claims and update state stay
synchronized."

`canonical(db, slug)` is the one record: the product, its newest certified pattern version
(`release_hash`), and the price, files (name -> sha256) and description claims supplied with
it. Every channel's payload is *derived* from that record by `fan_out` -- nothing a channel
shows is typed separately -- so a channel cannot carry a price, version, file or claim the
record does not.

`sync(record, observed)` compares what each channel was last observed showing against the
record and gives each channel one state:

* IN_SYNC -- price, version, every file digest and every claim match;
* UPDATE_PENDING -- something differs, each difference listed;
* UNKNOWN -- the channel has not been observed (never assumed in sync).

Channels are CLOSED unless the owner opens them (`OPEN_CHANNELS` is empty): `fan_out` returns
the payloads it would send and sends none. Nothing here writes to Etsy or anywhere else.
"""
from __future__ import annotations

CHANNELS = ("etsy", "own_site", "pattern_marketplace", "email_store")
OPEN_CHANNELS: frozenset[str] = frozenset()
FIELDS = ("price_cad", "version", "release_hash", "files", "claims")


class RecordRefused(ValueError):
    pass


def canonical(db, slug: str, *, price_cad: float, files: dict, claims) -> dict:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            raise RecordRefused(f"no product {slug!r}")
        pv = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.certified.is_(True))
            .order_by(PatternVersion.created_at.desc(), PatternVersion.id.desc()))
        if pv is None:
            raise RecordRefused(f"{slug!r} has no certified version to distribute")
        record = {"slug": slug, "title": product.title, "version": pv.version,
                  "release_hash": pv.release_hash, "price_cad": round(float(price_cad), 2),
                  "files": dict(sorted(files.items())), "claims": sorted(set(claims))}
    if not record["files"] or any(len(str(v)) != 64 for v in record["files"].values()):
        raise RecordRefused("every file needs its sha256")
    return record


def fan_out(record: dict, channels=CHANNELS) -> dict:
    out = {}
    for ch in channels:
        if ch not in CHANNELS:
            raise RecordRefused(f"unknown channel {ch!r}")
        payload = {k: record[k] for k in ("slug", "title", *FIELDS)}
        out[ch] = {"payload": payload, "state": "OPEN" if ch in OPEN_CHANNELS else "CLOSED",
                   "sent": False}
    return {"record_version": record["version"], "channels": out,
            "note": "derived from one record; no channel is written from here"}


def sync(record: dict, observed: dict) -> dict:
    out = {}
    for ch in CHANNELS:
        seen = (observed or {}).get(ch)
        if seen is None:
            out[ch] = {"state": "UNKNOWN", "why": "not observed; never assumed in sync"}
            continue
        diffs = []
        for f in FIELDS:
            want, have = record.get(f), seen.get(f)
            if f == "claims":
                want, have = sorted(want or []), sorted(have or [])
            if want != have:
                diffs.append({"field": f, "record": want, "channel": have})
        out[ch] = ({"state": "IN_SYNC"} if not diffs else
                   {"state": "UPDATE_PENDING", "differences": diffs})
    return {"version": record["version"], "channels": out}
