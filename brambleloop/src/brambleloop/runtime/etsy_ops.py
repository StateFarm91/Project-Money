"""The Etsy shop as it actually is: read-back, activation evidence and daily observation.

Final Build cluster B. Everything in this module answers one question the publish path could
not: *what does Etsy hold now*, as opposed to what we sent or what we intended.

- **The publish path** (`runtime.pipeline.handle_store_publish`) uploads the certified listing
  images in certificate order (F-524) and reads the draft and its files back afterwards
  (F-542, F-559). The helpers it uses are here so the activation handler and the daily
  census compare against the same certified payload the publish sent.
- **Activation** (`store.activate`, F-543) reads the remote draft back and checks images,
  files, price, inventory, taxonomy and disclosures against the certified listing, re-runs
  the release gates, and only then asks for the owner's authority -- revalidated at
  execution time, never carried from when the job was planned (F-835).
- **Three daily cadences** observe the shop through reads the granted scopes allow:
  `etsy.credential_health` (F-540), `etsy.shop_snapshot` (F-515, F-577, F-585) and
  `etsy.listing_census` (F-553, F-544, F-568). Each stores its reading in
  `operating_readings` and opens or resolves incidents from it. None of them writes to Etsy.
- **Owner actions**: an Etsy credential only a browser can repair becomes one idempotent
  owner action plus an incident (F-541), and the Etsy owner-only queue in
  `intel.etsy_surfaces` is seeded into the one owner queue by key (F-593, F-547), closed on
  the reading its evidence names and never on a statement.

The rule every handler here follows: **an unread shop is UNKNOWN, never clean.** A census
that could not run resolves nothing and opens nothing; a snapshot with no credential stores
no reading. Only an observation moves an incident in either direction.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .worker import JobContext, handlers

# ---- identities ----------------------------------------------------------------------

#: Owner-queue keys this module writes. `launch.readiness` closes every open action it did
#: not ask for, so these prefixes are excluded from that sweep: they are closed here, on
#: evidence, and nowhere else.
SURFACE_PREFIX = "etsy_surface:"
#: How much of an action's opening text identifies a keyless row being adopted.
ADOPT_PREFIX = 60
AUTH_KEY = "etsy.auth:reauthorise"
OWNER_PREFIXES = (SURFACE_PREFIX, "etsy.auth:")

AUTH_INCIDENT = "etsy.auth_needs_owner"
PUBLISH_INCOMPLETE = "store.publish_incomplete:"
POLICY_SUSPECTED = "policy_violation_suspected:"
UNEXPECTED_LISTING = "etsy.unexpected_listing:"
LISTING_DRIFT = "etsy.listing_drift:"
SHOP_INCIDENTS = "etsy.shop:"
SECURITY_INCIDENT = "etsy.security:"
#: K8 F-250: a listing of ours renewed for recency (the rule refuses it), and an expired
#: listing of ours whose renewal the rule allows (proposed to the owner, never executed).
RENEWAL_REFUSED = "etsy.renewal_refused:"
LISTING_EXPIRED = "etsy.listing_expired:"

SHOP_READING = "etsy.shop_snapshot"
CENSUS_READING = "etsy.listing_census"
CREDENTIAL_READING = "etsy.credential_health"
INVENTORY_READING = "etsy.surface_inventory"
LIFECYCLE_READING = "etsy.listing_lifecycle"
OPENAPI_READING = "etsy.openapi_reverification"
OPENAPI_DRIFT = "etsy.openapi_drift"
#: How long one re-verification of the surface classifications stands (F-514).
OPENAPI_REVERIFY_DAYS = 7

#: The scopes the publish, read-back and census paths use. A stored credential missing any
#: of them is scope drift (F-540/F-541): the next write or read would be refused.
REQUIRED_SCOPES = ("listings_r", "listings_w", "listings_d", "shops_r", "shops_w")

#: Etsy's getListingsByShop `state` filter values. Every one is read so a listing moved to
#: any of them is observed rather than inferred from its absence.
CENSUS_STATES = ("active", "draft", "inactive", "sold_out", "expired")

#: How our Listing.state maps to the state Etsy should report. store.publish creates drafts
#: and only store.activate makes one active.
EXPECTED_REMOTE_STATE = {"active": "active", "withdrawn": "inactive"}

#: Days allowed for the owner to read Shop Manager > Policy Violations after a listing
#: vanishes or changes state behind our back (F-568).
POLICY_DEADLINE_DAYS = 2

#: The owner actions a shop snapshot can close, and the `assess_shop` checks that must all
#: PASS on a fresh reading to close each. Anything not listed closes only on its own
#: evidence, which no API returns.
CLOSES_ON_SHOP_CHECKS: dict[str, tuple[str, ...]] = {
    "info_and_appearance_setup": ("icon_set", "banner_set"),
    "payment_settings_setup": ("etsy_payments_onboarded",),
    "policy_settings_paste": ("policy_payment_set", "policy_shipping_set",
                              "policy_refunds_set", "policy_privacy_set",
                              "policy_additional_unset"),
}

#: The storefront checks whose failure means the shop is missing a trust surface (F-515).
TRUST_SURFACE_CHECKS = ("icon_set", "banner_set", "title_set", "announcement_set",
                        "policy_payment_set", "policy_shipping_set", "policy_refunds_set",
                        "policy_privacy_set",
                        "digital_sale_message_set")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- the client ----------------------------------------------------------------------


def build_client(db, phase: str, *, owner_authorised: bool = False, transport=None):
    """The one EtsyClient every handler in cluster B uses, or None without credentials.

    Kept as one function so a test can point it at `tests/fake_etsy.py` in one place, and so
    `owner_authorised` is always an argument the caller read *now*: activation passes the
    environment's value at execution time (F-835), the observation cadences pass False.
    """
    from ..integrations.etsy import Credentials, EtsyClient
    from ..integrations.http import UrllibTransport

    transport = transport or UrllibTransport()
    creds = Credentials.from_env(transport=transport, db=db)
    return EtsyClient(transport, credentials=creds, phase=phase,
                      owner_authorised=owner_authorised)


# ---- F-541: a credential only the owner can repair -----------------------------------


def classify_auth_failure(message: str) -> str:
    """Which of the failure classes F-541 names this is, from Etsy's own refusal text."""
    text = (message or "").lower()
    if "missing [" in text or "cannot perform" in text:
        return "scope_drift"
    if "invalid_grant" in text or "spent or expired" in text:
        return "invalid_grant"
    if "no refresh token" in text or "no etsy token" in text:
        return "no_token"
    if " 401" in text or " 403" in text or "revoked" in text:
        return "revoked_access"
    if "not openable" in text or "sealing key" in text:
        return "changed_encryption_key"
    return "refused_by_etsy"


def record_auth_needs_owner(db, error: BaseException | str, *, where: str,
                            now: datetime | None = None) -> dict:
    """One owner action and one incident for an Etsy credential a browser must repair.

    Idempotent by key: the tenth failed publish restates the same owner action and the same
    incident rather than adding nine more. This is the ONE path for the remedy (F-541): the
    orders path (`commerce.orders_ingest.needs_owner`) calls it with its operation as
    `where`, so publish, read-back, census and order ingest share one key, one incident and
    one severity instead of two parallel requests for the same browser step.

    `launch.readiness` never closes this row (its key starts with an `OWNER_PREFIXES`
    entry and the open incident names it in `detail.owner_action`); only
    `resolve_auth_needs_owner`, on an authenticated call that worked, or the owner does.
    An action the owner marked done while the incident is still open is not re-added: their
    "done" is theirs, and the incident's report count says the failure recurred. Once the
    incident has been resolved on evidence, a new failure is a new episode and queues anew.
    """
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction
    from ..ops import incident_lifecycle as lifecycle

    message = str(error)[:600]
    kind = classify_auth_failure(message)
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == AUTH_KEY,
                                                 OwnerAction.done == False))  # noqa: E712
        open_incident = s.scalar(select(Incident).where(
            Incident.signature == AUTH_INCIDENT, Incident.resolved == False))  # noqa: E712
        owner_closed = None
        if row is None and open_incident is not None:
            owner_closed = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == AUTH_KEY,
                OwnerAction.done == True).order_by(OwnerAction.id.desc()))  # noqa: E712
        action = ("Re-authorise the Brambleloop Etsy app once in a browser: open "
                  "/api/etsy/oauth/start while signed in to the shop's Etsy account and "
                  "approve every scope listed (including transactions_r for orders).")
        reason = (f"Etsy refused this system's credential ({kind}) during {where}: "
                  f"{message[:300]}. A refresh cannot widen or revive a grant; only the "
                  f"account holder's consent can.")
        if row is None and owner_closed is not None:
            state = "already_decided"
        elif row is None:
            s.add(OwnerAction(requirement_key=AUTH_KEY, action=action, reason=reason,
                              max_cost_cad=0.0, minutes=5,
                              consequence_of_delay=("no Etsy read or write succeeds: "
                                                    "publishing, read-back, the shop "
                                                    "snapshot, the census and order ingest "
                                                    "all stop; sales stay UNMEASURED"),
                              blocks=("Etsy publish, read-back, observation and order "
                                      "ingest")))
            state = "queued"
        else:
            row.reason = reason
            state = "restated"
        wheres = sorted(set((open_incident.detail or {}).get("seen_during") or [])
                        | {where}) if open_incident is not None else [where]
        incident, opened = lifecycle.open_or_restate(
            s, signature=AUTH_INCIDENT, severity="P1",
            summary=(f"Etsy credential needs the owner ({kind}) -- seen during {where}. "
                     f"Owner action {AUTH_KEY} carries the one step that fixes it."),
            detail={"class": kind, "where": where, "error": message[:300],
                    "owner_action": AUTH_KEY, "seen_during": wheres}, now=now)
    return {"owner_action": AUTH_KEY, "queued": state == "queued", "state": state,
            "incident": AUTH_INCIDENT, "incident_opened": opened, "class": kind,
            "where": where}


def resolve_auth_needs_owner(db, *, evidence: str, granted_scopes=()) -> dict:
    """Close the re-authorisation action and incident once an authenticated call worked.

    Not when the failure named a scope the credential still lacks: a working `getMe` says
    nothing about `transactions_r`, and closing an action the next orders run would reopen
    is a queue that flickers instead of one that is true.
    """
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction
    from ..integrations.etsy_oauth import SCOPE_MEANINGS
    from ..ops import incident_lifecycle as lifecycle

    granted = set(granted_scopes or ())
    with db.session() as s:
        open_row = s.scalar(select(Incident).where(Incident.signature == AUTH_INCIDENT,
                                                   Incident.resolved == False))  # noqa: E712
        if open_row is not None:
            error = str((open_row.detail or {}).get("error") or "")
            still_missing = [sc for sc in SCOPE_MEANINGS if sc in error and sc not in granted]
            if (open_row.detail or {}).get("class") == "scope_drift" and still_missing:
                return {"owner_actions_closed": 0, "incidents_resolved": [],
                        "kept_open_for": still_missing}
        closed = 0
        for row in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == AUTH_KEY,
                OwnerAction.done == False)):  # noqa: E712
            from ..ops import owner_queue
            owner_queue.close(row, owner_queue.SATISFIED,
                              "a later Etsy call succeeded with the scopes this card asked for")
            closed += 1
        resolved = lifecycle.resolve_signatures(s, [AUTH_INCIDENT], resolution=evidence)
    return {"owner_actions_closed": closed, "incidents_resolved": resolved}


# ---- F-593 / F-547: the Etsy owner-only queue, in the one owner queue ----------------


def seed_owner_queue(db, *, defer: frozenset[str] | set[str] = frozenset()) -> dict:
    """Adopt `etsy_surfaces.owner_queue()` into `owner_actions`, idempotently by key.

    Each row carries the action, why software cannot do it, minutes, cost, consequence and
    the evidence that closes it. Items whose surface key is in `defer` are not added yet
    (F-874: `launch.readiness` defers the KYC/tax step until the step before first sale);
    a row already queued for one is left as it is. A key that already has a row (open or
    done) is not added again: a done row was closed on evidence, and re-adding it would ask the owner to repeat
    an action already completed. Open rows are restated in place when the wording moved.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..intel import etsy_surfaces

    queued, restated = [], []
    with db.session() as s:
        existing: dict[str, OwnerAction] = {}
        for row in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key.like(f"{SURFACE_PREFIX}%"))):
            # An open row wins over a done one for the same key.
            if row.requirement_key not in existing or not row.done:
                existing[row.requirement_key] = row
        # A row queued before it carried its key is adopted, not duplicated: matched on the
        # opening of its action text, the same rule `launch.readiness` applies to its own.
        keyless = [r for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "", OwnerAction.done == False))]  # noqa: E712
        deferred = []
        for item in etsy_surfaces.owner_queue():
            key = f"{SURFACE_PREFIX}{item.key}"
            if item.key in defer and key not in existing:
                deferred.append(key)
                continue
            if key not in existing:
                for row in keyless:
                    if row.action[:ADOPT_PREFIX] == item.action[:ADOPT_PREFIX]:
                        row.requirement_key = key
                        existing[key] = row
                        keyless.remove(row)
                        break
            reason = (f"{item.why_software_cannot} Risk: {item.risk}. Closes on: "
                      f"{item.evidence_required}")
            blocks = ("first sale" if item.blocks_first_sale else
                      f"Etsy surface: {item.surface}")
            row = existing.get(key)
            if row is None:
                s.add(OwnerAction(requirement_key=key, action=item.action, reason=reason,
                                  max_cost_cad=item.max_cost_cad, minutes=item.minutes,
                                  consequence_of_delay=item.consequence_of_delay,
                                  blocks=blocks))
                queued.append(key)
            elif not row.done and (row.action != item.action or row.reason != reason):
                row.action, row.reason = item.action, reason
                row.minutes, row.max_cost_cad = item.minutes, item.max_cost_cad
                row.consequence_of_delay, row.blocks = item.consequence_of_delay, blocks
                restated.append(key)
    return {"queued": queued, "restated": restated, "deferred": deferred,
            "total": len(etsy_surfaces.owner_queue())}


def _set_owner_action(s, key: str, *, done: bool) -> bool:
    """Close (or reopen) one seeded owner action. Returns whether anything changed."""
    from sqlalchemy import desc, select

    from ..core.models import OwnerAction

    row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)
                   .order_by(desc(OwnerAction.id)).limit(1))
    if row is None or bool(row.done) == done:
        return False
    row.done = done
    return True


# ---- readings ------------------------------------------------------------------------


def store_reading(db, kind: str, payload: dict, *, now: datetime | None = None) -> None:
    """One row per kind per UTC day; a rerun the same day replaces that day's reading."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    now = now or _now()
    period = now.date().isoformat()
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind,
                                                      OperatingReading.period_key == period))
        if row is None:
            s.add(OperatingReading(kind=kind, period_key=period, payload=payload, at=now))
        else:
            row.payload = payload
            row.at = now


def latest_reading(db, kind: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id))
                       .limit(1))
        return dict(row.payload or {}) if row is not None else None


# ---- the certified listing -----------------------------------------------------------


def certified_payload(db, slug: str, version: str):
    """The Etsy payload for a certified release, built exactly as store.publish builds it.

    One builder for publish, activation and the census, so the three compare against the
    same thing. Taxonomy flows through `build_payload` unchanged (cluster A owns choosing it).
    """
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import Listing, PatternVersion, Product
    from ..integrations.etsy import build_payload

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if listing is None:
            raise ValueError(f"no drafted listing for {slug}@{version}")
        copy = dict(title=listing.title, description=listing.description,
                    price_cad=listing.price_cad, tags=list(listing.tags))
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        if pv is None or not pv.certified or not pv.cir_json:
            raise ValueError(f"{slug}@{version} has no certified release")
        cir = CIR.from_dict(pv.cir_json)
    from ..commerce import category
    selected = category.publish_inputs(db, slug=slug, version=version)
    if selected.get("status") != category.CHOSEN or not selected.get("taxonomy_id"):
        raise ValueError("certified listing taxonomy UNKNOWN; default fallback prohibited")
    # F-004: PASS is written back only once the hero was judged on the certified listing
    # set (`search.judge_hero`) and only while that evidence and the copy are current;
    # PENDING (hero unjudged), REFUSED and STALE all refuse here.
    if selected.get("certified") != "PASS":
        raise ValueError(
            f"listing search profile not certified PASS "
            f"({selected.get('certified')}: "
            f"{'; '.join(selected.get('certified_problems') or []) or 'see the search certificate'})")
    payload = build_payload(materials=[m.name for m in cir.materials], **copy)
    payload.taxonomy_id = int(selected["taxonomy_id"])
    payload.properties = canonical_properties(selected.get("properties"))
    return payload


def canonical_properties(properties):
    if not isinstance(properties, list):
        raise ValueError("listing properties UNKNOWN")
    out = []
    for prop in properties:
        if not isinstance(prop, dict) or not prop.get("property_id"):
            raise ValueError("invalid listing property")
        values, ids = prop.get("values"), prop.get("value_ids")
        if not isinstance(values, list) or not isinstance(ids, list):
            raise ValueError("listing property values UNKNOWN")
        out.append({"property_id": int(prop["property_id"]),
                    "value_ids": sorted(int(v) for v in ids),
                    "values": sorted(str(v) for v in values),
                    "scale_id": int(prop["scale_id"]) if prop.get("scale_id") is not None else None})
    if len({p["property_id"] for p in out}) != len(out):
        raise ValueError("duplicate listing property")
    return sorted(out, key=lambda p: p["property_id"])


def with_properties(client, listing_id, remote):
    return {**remote, "properties": canonical_properties(client.get_listing_properties(listing_id))}


def sent_fields(payload) -> dict[str, Any]:
    """What a createDraftListing carried, in the shape `etsy_verify.verify` compares."""
    fields = payload.to_dict()
    fields.pop("state", None)
    fields["properties"] = canonical_properties(payload.properties)
    return fields


_IMAGE_MAGIC = ((b"\x89PNG", "png"), (b"\xff\xd8", "jpg"), (b"GIF8", "gif"))


def _image_suffix(data: bytes) -> str | None:
    for magic, suffix in _IMAGE_MAGIC:
        if data.startswith(magic):
            return suffix
    return None


def certified_frames(db, slug: str, version: str, *, release: str = "") -> dict:
    """The current valid listing-set certificate's frames, in certificate order (F-524).

    Returns `{"frames": [...], "record_id", "problems"}`. No valid certificate, or one issued
    for a different release than the listing's, is a problem -- the images a buyer sees are
    the ones that were certified, or none are sent.
    """
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord

    with db.session() as s:
        rec = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        if rec is None:
            return {"frames": [], "record_id": None,
                    "problems": [f"no valid listing-set certificate for {slug}@{version}: "
                                 f"there are no certified images to upload"]}
        frames = sorted((rec.certificate or {}).get("frames") or [],
                        key=lambda f: int(f.get("position") or 0))
        problems = []
        # PT-13: an empty hash on either side used to skip the binding. A caller that names
        # no release is bound to the release on file for slug@version; a certificate bound to
        # no release, or a release nobody can name, refuses.
        if not release:
            from ..core.models import PatternVersion, Product

            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = None if product is None else s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id, PatternVersion.version == version))
            release = (pv.release_hash or "") if pv is not None and pv.certified else ""
        if not rec.release_hash:
            problems.append(f"the valid listing-set certificate {rec.id} is bound to no "
                            f"release hash, so it cannot be checked against the release "
                            f"being published")
        elif not release:
            problems.append(f"no certified release hash is on file for {slug}@{version} to "
                            f"bind listing-set certificate {rec.id} to")
        elif rec.release_hash != release:
            problems.append(f"the valid listing-set certificate {rec.id} was issued for "
                            f"release {rec.release_hash[:12]}, not {release[:12]}")
        # F-757 / PT-13: the certified set must show the configuration the release encodes.
        declared = (rec.certificate or {}).get("represented_variant")
        if declared and release:
            from ..core.models import PatternVersion, Product
            from ..cir.model import CIR

            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = None if product is None else s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id, PatternVersion.version == version))
            if pv is not None and pv.cir_json:
                try:
                    encoded = CIR.from_dict(pv.cir_json).variant_key
                except Exception:  # noqa: BLE001 - an unparsable release binds nothing
                    encoded = None
                if encoded is None or encoded != declared:
                    problems.append(f"listing-set certificate {rec.id} certifies configuration "
                                    f"{declared!r}; the release encodes {encoded!r} (F-757)")
        if not frames:
            problems.append(f"listing-set certificate {rec.id} names no frame")
        return {"frames": frames, "record_id": rec.id, "problems": problems}


class CertifiedImage(tuple):
    """A certified listing image: `(filename, bytes)` that also carries its certified alt text.

    Still a 2-tuple, so every reader that unpacks `name, data` is unchanged; the alt text a
    disclosed render was certified with (D-FB-7: the disclosure lives in it) rides on the
    entry to `EtsyClient.publish`, which sends it with the upload.
    """

    def __new__(cls, name: str, data: bytes, alt_text: str = ""):
        entry = super().__new__(cls, (name, data))
        entry.alt_text = alt_text
        return entry


def certified_images(db, slug: str, version: str, *, release: str = "",
                     store_root=None) -> dict:
    """The certified listing image bytes, ordered by the listing-set certificate (F-524).

    Every frame's bytes are read from the artifact store by the hash the certificate
    recorded -- `ArtifactStore.get` re-hashes what it reads, so a file that changed on disk
    is refused rather than uploaded. A missing frame is a problem for the whole set: a
    listing whose second image silently fell out is not the listing that was certified.

    D-FB-7: a disclosed render is served only when the certificate certified it as one
    (`kind` and its alt text recorded), and only after `disclosed_listing.export_check`
    passes again on the exact bytes against the listing copy on file -- the disclosure in
    the pixels, the alt text and the copy, and structural truth PASS. A disclosed render's
    bytes under a certificate that did not certify them as one are refused. This is the one
    upload path; there is no other exporter.
    """
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    cert = certified_frames(db, slug, version, release=release)
    problems = list(cert["problems"])
    images: list[tuple[str, bytes]] = []
    order: list[dict] = []
    store = ArtifactStore(store_root)
    from ..publish import disclosed_listing

    disclosed = disclosed_listing.disclosed_shas(db)
    on_file: dict[str, dict] = {}
    if any(f.get("kind") == "disclosed_render" for f in cert["frames"]):
        rec = disclosed_listing.last_asset(db, slug=slug) or {}
        on_file = {(f.get("image") or {}).get("sha256"): f for f in rec.get("frames") or []}
    copy_text = None
    cir = None
    for frame in cert["frames"]:
        sha = str(frame.get("sha256") or "")
        position = int(frame.get("position") or 0)
        is_disclosed = frame.get("kind") == "disclosed_render"
        if sha in disclosed and not is_disclosed:
            problems.append(f"frame {position} ({sha[:12]}) is a disclosed render the "
                            f"certificate did not certify as one, so it has no certified "
                            f"disclosure alt text and is not uploaded")
            continue
        if is_disclosed and (sha not in on_file or not frame.get("alt_text")):
            problems.append(f"frame {position} ({sha[:12]}) is certified as a disclosed render "
                            f"but is not a frame of the disclosed set on file, or carries no "
                            f"alt text")
            continue
        try:
            data = store.get(sha, db=db)
        except ArtifactMissing as e:
            problems.append(f"frame {position} ({sha[:12]}): {str(e)[:200]}")
            continue
        suffix = _image_suffix(data)
        if suffix is None:
            problems.append(f"frame {position} ({sha[:12]}) is not a PNG, JPEG or GIF")
            continue
        alt = ""
        if frame.get("kind") == "disclosed_gallery_frame":
            # F-030 / F-254: a disclosed gallery frame is re-verified on these exact bytes
            # against the certified CIR, and its alt text must be the one it would be
            # certified with today; otherwise it is refused, never uploaded on trust.
            from ..visual import launch_imagery as _li

            job = str(frame.get("job") or "")
            verdict = _li.check_supplement(slug, version, job, data, db=db, store=store)
            want_alt = _li.expected_alt_text(slug, job)
            if verdict["status"] != "PASS":
                problems.append(f"frame {position} ({sha[:12]}) gallery frame refused at "
                                f"export: {verdict['why']}"[:400])
                continue
            if not frame.get("alt_text") or frame["alt_text"] != want_alt:
                problems.append(f"frame {position} ({sha[:12]}): certified alt text is not "
                                f"the gallery frame's disclosed alt text")
                continue
            alt = frame["alt_text"]
        if is_disclosed:
            if copy_text is None:
                from ..visual.render_verification import authoritative_cir

                copy_text = disclosed_listing.listing_copy(db, slug=slug, version=version) or ""
                cir = authoritative_cir(slug, version)
            if frame["alt_text"] != on_file[sha].get("alt_text"):
                problems.append(f"frame {position} ({sha[:12]}): certified alt text differs "
                                f"from the alt text filed with the render")
                continue
            verdict = disclosed_listing.export_check(on_file[sha], image_bytes=data,
                                                     description=copy_text, cir=cir)
            if not verdict["ok"]:
                problems.append(f"frame {position} ({sha[:12]}) disclosed render refused at "
                                f"export: {verdict['problems']}"[:400])
                continue
            alt = frame["alt_text"]
        name = f"{slug}-frame-{position}.{suffix}"
        images.append(CertifiedImage(name, data, alt))
        order.append({"position": position, "sha256": sha, "filename": name,
                      "bytes": len(data), "job": frame.get("job"),
                      "honesty_label": frame.get("honesty_label", "")}
                     | ({"kind": frame.get("kind"), "alt_text": alt}
                        if frame.get("kind") in ("disclosed_render", "disclosed_gallery_frame")
                        else {}))
    return {"images": images if not problems else [], "order": order,
            "record_id": cert["record_id"], "problems": problems}


def file_expectations(docs_by_name: dict[str, bytes],
                      certified_by_name: dict[str, str]) -> list[dict]:
    """What `etsy_verify.verify_files` compares: name, size and hash of each file sent."""
    return [{"name": name, "size": len(data),
             "sha256": hashlib.sha256(data).hexdigest(),
             "certified_sha256": certified_by_name.get(name)}
            for name, data in sorted(docs_by_name.items())]


def images_read_back(client, listing_id: str, expected_alt_texts: list[str]) -> dict:
    """PT-12: the listing's images as Etsy holds them, rank by rank, against the alt text sent.

    The disclosure lives in each disclosed frame's alt text (D-FB-9), and the upload response
    is not the listing: if Etsy dropped or truncated it, only a read of the listing's images
    shows it. Compared exactly, in rank order; a failed read is unverified, never a pass.
    """
    try:
        remote = client.get_listing_images(listing_id)
    except Exception as e:  # noqa: BLE001 - a failed read is an unverified write
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(e, EtsyAuthNeedsOwner):
            raise
        return {"verified": False, "problems": [
            f"listing images read failed: {type(e).__name__}: {str(e)[:200]}"]}
    ordered = sorted(remote or [], key=lambda r: int(r.get("rank") or 0))
    held = [str(r.get("alt_text") or "") for r in ordered]
    problems = []
    if len(held) != len(expected_alt_texts):
        problems.append(f"images: sent {len(expected_alt_texts)}, Etsy holds {len(held)}")
    for rank, (sent_alt, got) in enumerate(zip(expected_alt_texts, held), start=1):
        if (sent_alt or "") != got:
            problems.append(f"image rank {rank} alt_text: sent {sent_alt!r}, Etsy holds "
                            f"{got!r}")
    return {"verified": not problems, "problems": problems, "alt_texts_on_etsy": held}


def read_back(client, listing_id: str, *, sent: dict, expected_files: list[dict],
              expected_images: int, expected_alt_texts: list[str] | None = None) -> dict:
    """F-542 / F-559: getListing and getAllListingFiles after the writes, judged.

    A read that fails is reported as unverified with the reason, never as verified.
    `expected_alt_texts` (PT-12) are the certified frames' alt texts in upload order; when
    given, the listing's images are read back and compared rank by rank.
    """
    from ..integrations import etsy_verify

    try:
        remote = with_properties(client, listing_id, client.get_listing(listing_id))
    except Exception as e:  # noqa: BLE001 - a failed read is an unverified write
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(e, EtsyAuthNeedsOwner):
            raise
        remote = {}
        read_error = f"{type(e).__name__}: {str(e)[:200]}"
    else:
        read_error = ""
    try:
        remote_files = client.get_listing_files(listing_id)
    except Exception as e:  # noqa: BLE001
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(e, EtsyAuthNeedsOwner):
            raise
        remote_files = None
        read_error = read_error or f"{type(e).__name__}: {str(e)[:200]}"
    fields = etsy_verify.verify(sent, remote, listing_id=listing_id, expect_state="draft",
                                expect_images=expected_images)
    files = etsy_verify.verify_files(expected_files, remote_files, listing_id=listing_id)
    images = (images_read_back(client, listing_id, list(expected_alt_texts))
              if expected_alt_texts is not None else None)
    verified = fields.verified and files.verified and (images is None or images["verified"])
    return {"verified": verified, "fields": fields.summary(), "files": files.summary(),
            "images": images,
            "read_error": read_error,
            "reasons": (list(fields.summary()["problems"])
                        + [f"{m['field']}: sent {m['sent']!r}, Etsy holds {m['remote']!r}"
                           for m in fields.summary()["mismatched"]]
                        + [f"{f}: not returned" for f in fields.summary()["not_returned"]]
                        + list(files.problems)
                        + (list(images["problems"]) if images else [])
                        + ([f"read failed: {read_error}"] if read_error else []))}


def open_publish_incomplete(db, *, slug: str, version: str, listing_id: str | None,
                            reasons: list[str]) -> None:
    """A draft on Etsy that does not match what was certified halts its activation."""
    from ..ops import incident_lifecycle as lifecycle

    with db.session() as s:
        lifecycle.open_or_restate(
            s, signature=f"{PUBLISH_INCOMPLETE}{slug}@{version}", severity="P1",
            product_slug=slug, halts_publication=True,
            summary=(f"Etsy listing {listing_id} for {slug}@{version} does not match the "
                     f"certified listing on read-back: {'; '.join(reasons[:3])}. It must be "
                     f"completed or deleted; it cannot be activated as it stands."),
            detail={"listing_id": listing_id, "reasons": reasons[:10]})


def disclosure_on_remote(remote: dict) -> dict:
    """#41 run on the copy Etsy actually holds, not on the copy we stored."""
    from ..commerce.buyer_trust import disclosure_check, disclosures_from_copy

    title, description = remote.get("title"), remote.get("description")
    if not isinstance(title, str) or not isinstance(description, str):
        return {"checked": False, "why": "Etsy returned no title/description to check"}
    result = disclosure_check(disclosures_from_copy(title=title, description=description))
    return {"checked": True, "complete": result["complete"], "missing": result["missing"],
            "misplaced": result["misplaced"], "finding": not result["complete"]}


def published_files(db, slug: str, version: str, listing_id: str) -> list[dict] | None:
    """The files the verified publish sent, from its `store.published` row."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == "store.published",
                AuditLog.artifact == f"{slug}@{version}").order_by(desc(AuditLog.id))):
            detail = row.detail or {}
            if str(detail.get("etsy_listing_id") or "") == str(listing_id):
                return list(detail.get("files_sent") or [])
    return None


# ---- F-540: credential health --------------------------------------------------------


@handlers.register("etsy.credential_health")
def handle_credential_health(ctx: JobContext) -> dict:
    """Daily: is the stored Etsy credential openable, correctly scoped and still refreshing.

    Reads `oauth_store.credential_health` (no values, only fingerprints) and then, when a
    credential is stored and openable, makes one authenticated read (`getMe`, `shops_r`).
    That read refreshes the access token through the same provider every job uses, so a
    rotation happens here and is persisted under compare-and-set -- the production proof of
    rotation F-540 asks for accumulates as `rotations` in the stored row. An
    `EtsyAuthNeedsOwner` becomes the owner action and incident of F-541.
    """
    from ..core import oauth_store
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner
    from ..ops import incident_lifecycle as lifecycle

    health = oauth_store.credential_health(ctx.db)
    scopes = set(str(health.get("scopes") or "").split())
    missing = [s for s in REQUIRED_SCOPES if s not in scopes] if health["stored"] else []
    findings: list[str] = []
    if health["stored"] and not health["openable"]:
        findings.append("stored credential is not openable under the current sealing key")
    if missing:
        findings.append(f"stored credential is missing scopes {missing}")
    live: dict[str, Any] = {"attempted": False}
    auth: dict | None = None
    if health["stored"] and health["openable"]:
        client = build_client(ctx.db, ctx.phase.value)
        if client.credentials is not None:
            live["attempted"] = True
            try:
                client.get_me()
                live["ok"] = True
            except EtsyAuthNeedsOwner as e:
                live["ok"] = False
                live["error"] = str(e)[:300]
                auth = record_auth_needs_owner(ctx.db, e, where="etsy.credential_health")
            except Exception as e:  # noqa: BLE001 - a network failure is not a verdict
                live["ok"] = None
                live["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        after = oauth_store.credential_health(ctx.db)
        live["rotations_before"] = health.get("rotations")
        live["rotations_after"] = after.get("rotations")
    if not health["stored"]:
        status = "ABSENT"
    elif findings or live.get("ok") is False:
        status = "UNHEALTHY"
    elif live.get("ok"):
        status = "HEALTHY"
    else:
        status = "UNKNOWN"
    if findings:
        auth = auth or record_auth_needs_owner(
            ctx.db, "; ".join(findings) + (" (not openable)" if not health["openable"]
                                           else f" (cannot perform: missing [{missing}])"),
            where="etsy.credential_health")
    with ctx.db.session() as s:
        if findings or live.get("ok") is False:
            lifecycle.open_or_restate(
                s, signature=f"{CREDENTIAL_READING}:unhealthy", severity="P1",
                summary=f"Etsy credential unhealthy: {'; '.join(findings) or live.get('error')}",
                detail={"findings": findings, "live": live})
        elif status == "HEALTHY":
            lifecycle.resolve_signatures(
                s, [f"{CREDENTIAL_READING}:unhealthy"],
                resolution=f"credential openable, scopes complete and getMe succeeded at "
                           f"{_now().isoformat()}")
    if status == "HEALTHY":
        resolve_auth_needs_owner(ctx.db, evidence="an authenticated getMe succeeded on the "
                                                  "daily credential-health check",
                                 granted_scopes=scopes)
        if "transactions_r" in scopes:
            with ctx.db.session() as s:
                _set_owner_action(s, f"{SURFACE_PREFIX}reauthorise_transactions_r", done=True)
    reading = {"observed_at": time.time(), "status": status, "stored": health["stored"],
               "openable": health["openable"], "scopes": sorted(scopes),
               "missing_scopes": missing, "rotations": health.get("rotations"),
               "updated_at": health.get("updated_at"), "live": live, "findings": findings,
               # A masked fingerprint ("***abcd"), never the token: F-592 compares it day
               # to day to see a credential replaced outside this system's refresh.
               "token_fingerprint": health.get("token_fingerprint")}
    reading["security_posture"] = _security_posture(ctx.db, reading)
    store_reading(ctx.db, CREDENTIAL_READING, reading)
    ctx.audit("etsy.credential_health", detail={**reading, "auth": auth})
    return {"status": status, "findings": findings, "live_ok": live.get("ok")}


def _security_posture(db, reading: dict) -> dict:
    """K8 F-592: the day's posture (commerce.shop_security), and its incident."""
    from ..commerce import shop_observations, shop_security
    from ..ops import incident_lifecycle as lifecycle

    try:
        from ..integrations import etsy_authorise

        callback = etsy_authorise.configuration()
        callback = {"problems": callback.get("problems") or [],
                    "redirect_uri": bool(callback.get("redirect_uri"))}
    except Exception as e:  # noqa: BLE001 - an unreadable configuration is a finding
        callback = {"problems": [f"REDIRECT configuration unreadable: {type(e).__name__}"]}
    previous = latest_reading(db, CREDENTIAL_READING)
    posture = shop_security.posture(
        reading, previous if previous and previous.get("observed_at") != reading.get(
            "observed_at") else None,
        observations={p: shop_observations.latest(db, p) for p in ("apps", "shared_access")},
        callback=callback)
    signature = f"{SECURITY_INCIDENT}posture"
    with db.session() as s:
        if posture["findings"]:
            suspicious = any(f.get("suspicious") for f in posture["findings"])
            lifecycle.open_or_restate(
                s, signature=signature, severity="P1" if suspicious else "P2",
                summary=("Etsy shop security posture: "
                         + "; ".join(f["detail"] for f in posture["findings"][:3])),
                detail={"findings": posture["findings"], "checks": posture["checks"]})
        elif posture["status"] == "OK":
            lifecycle.resolve_signatures(
                s, [signature], resolution=f"posture OK at {_now().isoformat()}: scopes, "
                                           f"rotation, callback, apps and shared access clear")
    return posture


# ---- F-515 / F-577 / F-585: the shop snapshot ----------------------------------------


@handlers.register("etsy.shop_snapshot")
def handle_shop_snapshot(ctx: JobContext) -> dict:
    """Daily getShop, stored, judged by `assess_shop`, turned into incidents and closures.

    Vacation mode, a currency that is not CAD and Etsy Payments going from onboarded to not
    each open a halting P1: any of them silently stops or misprices every sale. Missing trust
    surfaces (icon, banner, policies, messages) open one non-halting P1 so launch readiness
    cannot pass on the package we intend while the shop Etsy shows is incomplete. A check
    that passes on a fresh reading closes the seeded owner action whose evidence it is.
    """
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner
    from ..intel import etsy_surfaces
    from ..ops import incident_lifecycle as lifecycle

    client = build_client(ctx.db, ctx.phase.value)
    if client.credentials is None:
        ctx.audit("etsy.shop_snapshot", detail={"evidence": "NO_EVIDENCE",
                                                "why": "no Etsy credentials in this "
                                                       "environment; nothing was read"})
        return {"evidence": "NO_EVIDENCE", "reason": "no credentials"}
    try:
        body = client.get_shop()
    except EtsyAuthNeedsOwner as e:
        auth = record_auth_needs_owner(ctx.db, e, where="etsy.shop_snapshot")
        ctx.audit("etsy.shop_snapshot", detail={"evidence": "NO_EVIDENCE", "auth": auth})
        return {"evidence": "NO_EVIDENCE", "reason": "credential needs the owner"}
    except Exception as e:  # noqa: BLE001 - an unread shop is unknown, not clean
        ctx.audit("etsy.shop_snapshot", detail={"evidence": "NO_EVIDENCE",
                                                "error": f"{type(e).__name__}: {e}"[:300]})
        return {"evidence": "NO_EVIDENCE", "reason": f"{type(e).__name__}"}

    now = time.time()
    previous = latest_reading(ctx.db, SHOP_READING)
    snapshot = {"observed_at": now, "shop": body}
    status = etsy_surfaces.assess_shop(snapshot, now=now)
    # K8: F-537 live policy text vs its canonical sources; F-585 the Options registry;
    # F-514 the surface inventory re-verified against what is held today.
    from ..commerce import policy_consistency, shop_observations, shop_options, \
        surface_inventory

    policy = policy_consistency.check(body)
    options = shop_options.evaluate(
        body, (previous or {}).get("shop"),
        shop_observations.latest(ctx.db, "options").get("observation"))
    store_reading(ctx.db, SHOP_READING, {**snapshot, "status": status.to_dict(),
                                         "policy_consistency": policy,
                                         "options_registry": options})
    inventory = surface_inventory.reverify(ctx.db, now=now)
    store_reading(ctx.db, INVENTORY_READING, inventory)
    checks = {c.key: c for c in status.checks}

    def failed(key: str) -> bool:
        return key in checks and checks[key].result == etsy_surfaces.FAIL

    was_onboarded = bool(((previous or {}).get("shop") or {}).get(
        "is_etsy_payments_onboarded") is True)
    conditions = {
        f"{SHOP_INCIDENTS}vacation": (failed("not_on_vacation"), True,
                                      "the shop is in vacation mode: no buyer can purchase"),
        f"{SHOP_INCIDENTS}currency_drift": (
            failed("currency_is_cad"), True,
            f"the shop currency is {body.get('currency_code')!r}, not CAD: every price "
            f"decision here is computed in CAD"),
        f"{SHOP_INCIDENTS}payments_drift": (
            failed("etsy_payments_onboarded") and was_onboarded, True,
            "Etsy Payments went from onboarded to not onboarded: payouts have stopped"),
        f"{SHOP_INCIDENTS}incomplete": (
            any(failed(k) for k in TRUST_SURFACE_CHECKS), False,
            "the shop Etsy shows is missing trust surfaces: "
            + ", ".join(k for k in TRUST_SURFACE_CHECKS if failed(k))),
    }
    opened, resolved = [], []
    with ctx.db.session() as s:
        for signature, (holds, halts, summary) in conditions.items():
            if holds:
                _, new = lifecycle.open_or_restate(
                    s, signature=signature, severity="P1", halts_publication=halts,
                    summary=summary, detail={"observed_at": now})
                if new:
                    opened.append(signature)
            else:
                resolved += lifecycle.resolve_signatures(
                    s, [signature], resolution=f"getShop read at {_now().isoformat()} no "
                                               f"longer shows this condition")
        k8 = {
            f"{SHOP_INCIDENTS}policy_inconsistent": (
                not policy["consistent"],
                "P1" if policy["contradictions"] else "P2",
                "the live shop's policy text disagrees with its canonical source: "
                + "; ".join([f"{c['field']} contradicts {c['fact']} ({c['found']!r})"
                             for c in policy["contradictions"]][:3]
                            + [f"{f} differs from canonical" for f in policy["differs"]][:3]
                            + policy["internal_problems"][:2]),
                {"policy_consistency": policy}),
            f"{SHOP_INCIDENTS}options_drift": (
                bool(options["drift"]), "P2",
                f"Settings > Options drifted: {options['drift']}",
                {"options": [c for c in options["controls"]
                             if c["status"] in ("DRIFT", "CHANGED")],
                 "ui_change": options["ui_change"]}),
        }
        for signature, (holds, severity, summary, detail) in k8.items():
            if holds:
                _, new = lifecycle.open_or_restate(
                    s, signature=signature, severity=severity, summary=summary,
                    detail={"observed_at": now, **detail})
                if new:
                    opened.append(signature)
            else:
                resolved += lifecycle.resolve_signatures(
                    s, [signature], resolution=f"getShop read at {_now().isoformat()} no "
                                               f"longer shows this condition")
        closed, reopened = [], []
        if status.evidence_state == etsy_surfaces.FRESH:
            for key, needed in CLOSES_ON_SHOP_CHECKS.items():
                results = [checks[k].result if k in checks else etsy_surfaces.UNEVIDENCED
                           for k in needed]
                full = f"{SURFACE_PREFIX}{key}"
                if all(r == etsy_surfaces.PASS for r in results):
                    if _set_owner_action(s, full, done=True):
                        closed.append(full)
                elif any(r == etsy_surfaces.FAIL for r in results):
                    if _set_owner_action(s, full, done=False):
                        reopened.append(full)
    ctx.audit("etsy.shop_snapshot", detail={
        "evidence": status.evidence_state, "green": status.green,
        "failures": [c.key for c in status.failures],
        "unevidenced": [c.key for c in status.unevidenced],
        "incidents_opened": opened, "incidents_resolved": resolved,
        "owner_actions_closed": closed, "owner_actions_reopened": reopened})
    return {"evidence": status.evidence_state, "green": status.green,
            "failures": [c.key for c in status.failures], "incidents_opened": opened,
            "policy_consistent": policy["consistent"], "options_drift": options["drift"],
            "inventory_problems": len(inventory["problems"])}


# ---- F-553 / F-544 / F-568: the listing census ---------------------------------------


def _expected_listings(db) -> dict[str, dict]:
    """listing_id -> what we believe about it, from our Listing rows and exercise drafts."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ..integrations import etsy_exercise

    out: dict[str, dict] = {}
    with db.session() as s:
        for row in s.scalars(select(Listing).where(Listing.etsy_listing_id != "")):
            out[str(row.etsy_listing_id)] = {
                "slug": row.product_slug, "version": row.version,
                "state": EXPECTED_REMOTE_STATE.get(row.state, "draft"),
                "local_state": row.state}
    for draft in etsy_exercise.outstanding_drafts(db):
        out.setdefault(str(draft["listing_id"]), {"slug": None, "version": None,
                                                  "state": "draft",
                                                  "local_state": "exercise_draft"})
    return out


def _field_drift(db, known: dict, remote: dict) -> list[str]:
    """Title, description, tags, materials, price, quantity, taxonomy and type drift."""
    from ..integrations import etsy_verify

    if not known.get("slug"):
        return []
    try:
        payload = certified_payload(db, known["slug"], known["version"])
    except Exception as e:  # noqa: BLE001 - no certified payload is itself a finding
        return [f"no certified payload to compare against: {str(e)[:160]}"]
    sent = sent_fields(payload)
    verdict = etsy_verify.verify(sent, remote, expect_state="")
    return ([f"{m['field']}: certified {m['sent']!r}, Etsy holds {m['remote']!r}"
             for m in verdict.summary()["mismatched"]]
            + [f"{f}: not returned" for f in verdict.summary()["not_returned"]])


@handlers.register("etsy.listing_census")
def handle_listing_census(ctx: JobContext) -> dict:
    """Daily inventory of every listing in every state, compared with what we created.

    getListingsByShop for each state (listings_r is granted) is the estate (F-553). The
    state comparison is `etsy_surfaces.listing_census_drift`; a listing we created that
    vanished or changed state becomes `policy_violation_suspected:<id>` -- halting, with a
    deadline and the closure evidence it needs, because a takedown and a deletion look the
    same from here and a person must read Policy Violations (F-568). Present listings are
    compared field by field with the certified payload and every drift is a reconcile
    incident; nothing is overwritten (F-544). A listing nobody here created is reported.
    """
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner
    from ..intel import etsy_surfaces
    from ..ops import incident_lifecycle as lifecycle

    client = build_client(ctx.db, ctx.phase.value)
    if client.credentials is None:
        ctx.audit("etsy.listing_census", detail={"evidence": "NO_EVIDENCE",
                                                 "why": "no Etsy credentials; nothing read"})
        return {"evidence": "NO_EVIDENCE", "reason": "no credentials"}
    observed: list[dict] = []
    try:
        for state in CENSUS_STATES:
            observed.extend(client.get_shop_listings(state=state))
    except EtsyAuthNeedsOwner as e:
        auth = record_auth_needs_owner(ctx.db, e, where="etsy.listing_census")
        ctx.audit("etsy.listing_census", detail={"evidence": "NO_EVIDENCE", "auth": auth})
        return {"evidence": "NO_EVIDENCE", "reason": "credential needs the owner"}
    except Exception as e:  # noqa: BLE001 - a partial census is not a census
        ctx.audit("etsy.listing_census", detail={"evidence": "NO_EVIDENCE",
                                                 "error": f"{type(e).__name__}: {e}"[:300]})
        return {"evidence": "NO_EVIDENCE", "reason": type(e).__name__}

    now = time.time()
    known = _expected_listings(ctx.db)
    status = etsy_surfaces.listing_census_drift(
        {lid: k["state"] for lid, k in known.items()}, observed, observed_at=now, now=now)
    by_id = {str(r.get("listing_id")): r for r in observed}

    from ..commerce import listing_estate, listing_lifecycle, listing_rollback

    drift: dict[str, list[str]] = {}
    fulls: dict[str, dict] = {}
    assets: dict[str, dict] = {}
    plans: dict[str, dict] = {}
    for lid, k in known.items():
        remote = by_id.get(lid)
        if remote is not None and k.get("slug"):
            try:
                full = with_properties(client, lid, client.get_listing(lid))
            except Exception:  # noqa: BLE001 - fall back to the census row
                full = remote
            fulls[lid] = full
            found = _field_drift(ctx.db, k, full)
            # K8 F-544/F-559: images and the exact customer files, re-read every day.
            try:
                assets[lid] = listing_estate.asset_audit(ctx.db, client, lid, k)
                found = found + assets[lid]["drift"]
            except EtsyAuthNeedsOwner as e:
                auth = record_auth_needs_owner(ctx.db, e, where="etsy.listing_census")
                ctx.audit("etsy.listing_census", detail={"evidence": "NO_EVIDENCE",
                                                         "auth": auth})
                return {"evidence": "NO_EVIDENCE", "reason": "credential needs the owner"}
            except Exception as e:  # noqa: BLE001 - an unread asset is unverified
                assets[lid] = None
                found = found + [f"assets: read failed ({type(e).__name__}); delivery "
                                 f"UNVERIFIED"]
            if found:
                drift[lid] = found
                # K8 F-518: the defined restore and its stop conditions, never executed here.
                try:
                    plans[lid] = listing_rollback.plan(
                        listing_id=lid, slug=k.get("slug"), version=k.get("version"),
                        certified=sent_fields(certified_payload(ctx.db, k["slug"],
                                                                k["version"])),
                        remote=full)
                except Exception as e:  # noqa: BLE001 - no plan is stated, not hidden
                    plans[lid] = {"listing_id": lid, "restore": {}, "owner_steps": [
                        f"no rollback plan: {type(e).__name__}: {str(e)[:160]}"]}

    # K8 F-553: the estate row carries assets, files, properties, expiry, renewal and fee.
    estate = [listing_estate.estate_row(
        r, known.get(str(r.get("listing_id"))), now=now,
        assets=assets.get(str(r.get("listing_id"))),
        properties=(fulls.get(str(r.get("listing_id"))) or {}).get("properties"))
        for r in observed]
    previous_census = latest_reading(ctx.db, CENSUS_READING)
    # K8 F-250: the renewal rule (publish.release_gates.renewal_decision) on every census.
    renewals = listing_estate.renewal_review(
        (previous_census or {}).get("estate"), estate,
        material_changes=listing_estate.material_changes(ctx.db))
    delivery = {lid: (a or {}).get("delivery", {}).get("status",
                                                       listing_estate.DELIVERY_UNVERIFIED)
                for lid, a in assets.items()}
    store_reading(ctx.db, CENSUS_READING, {"observed_at": now, "estate": estate,
                                           "status": status.to_dict(), "drift": drift,
                                           "delivery": delivery, "renewals": renewals,
                                           "rollback_plans": plans})

    deadline = (_now() + timedelta(days=POLICY_DEADLINE_DAYS)).isoformat()
    suspected, unexpected = {}, {}
    for check in status.failures:
        if check.key.startswith("listing_"):
            suspected[check.key[len("listing_"):]] = check.detail
        elif check.key.startswith("unexpected_"):
            unexpected[check.key[len("unexpected_"):]] = check.detail
    opened: list[str] = []
    with ctx.db.session() as s:
        for lid, detail in suspected.items():
            k = known.get(lid) or {}
            _, new = lifecycle.open_or_restate(
                s, signature=f"{POLICY_SUSPECTED}{lid}", severity="P1",
                product_slug=k.get("slug"), halts_publication=True,
                summary=(f"{detail}. Remediation owner: the owner (Shop Manager > Policy "
                         f"Violations). Deadline {deadline}."),
                detail={"listing_id": lid, "source_text": detail, "deadline": deadline,
                        "remediation_owner": "owner",
                        "closure_evidence": ("the listing observed again in its expected "
                                             "state by this census, or a dated Policy "
                                             "Violations statement recorded against "
                                             f"{SURFACE_PREFIX}policy_violations_check")})
            if new:
                opened.append(f"{POLICY_SUSPECTED}{lid}")
        if suspected:
            _set_owner_action(s, f"{SURFACE_PREFIX}policy_violations_check", done=False)
        for lid, detail in unexpected.items():
            _, new = lifecycle.open_or_restate(
                s, signature=f"{UNEXPECTED_LISTING}{lid}", severity="P2", summary=detail,
                detail={"listing_id": lid})
            if new:
                opened.append(f"{UNEXPECTED_LISTING}{lid}")
        drift_opened: list[str] = []
        for lid, found in drift.items():
            k = known.get(lid) or {}
            _, new = lifecycle.open_or_restate(
                s, signature=f"{LISTING_DRIFT}{lid}", severity="P1",
                product_slug=k.get("slug"), halts_publication=True,
                summary=(f"Etsy listing {lid} ({k.get('slug')}@{k.get('version')}) no longer "
                         f"matches its certified listing: {'; '.join(found[:3])}. Reconcile "
                         f"deliberately; nothing here overwrites it."),
                detail={"listing_id": lid, "drift": found[:10],
                        "rollback_plan": plans.get(lid)})
            if new:
                opened.append(f"{LISTING_DRIFT}{lid}")
                drift_opened.append(lid)
        for item in renewals["refused_renewals"]:
            _, new = lifecycle.open_or_restate(
                s, signature=f"{RENEWAL_REFUSED}{item['listing_id']}", severity="P2",
                product_slug=item.get("slug"),
                summary=(f"Etsy listing {item['listing_id']} was renewed while "
                         f"{item.get('was_state')} (expiry moved {item['expiry_moved_days']} "
                         f"days) with no material change: {item['why']}"),
                detail=item)
            if new:
                opened.append(f"{RENEWAL_REFUSED}{item['listing_id']}")
        for item in renewals["proposals"]:
            _, new = lifecycle.open_or_restate(
                s, signature=f"{LISTING_EXPIRED}{item['listing_id']}", severity="P2",
                product_slug=item.get("slug"),
                summary=(f"Etsy listing {item['listing_id']} ({item.get('slug')}) has expired. "
                         f"Renewal is allowed by the rule ({item['why']}); proposed to the "
                         f"owner, not executed."),
                detail=item)
            if new:
                opened.append(f"{LISTING_EXPIRED}{item['listing_id']}")
        # Only a census that was actually read may close anything.
        resolved = []
        expired_ids = {p["listing_id"] for p in renewals["proposals"]}
        for prefix, still in ((POLICY_SUSPECTED, suspected), (UNEXPECTED_LISTING, unexpected),
                              (LISTING_DRIFT, drift), (LISTING_EXPIRED, expired_ids)):
            life = lifecycle.reconcile(
                s, prefix, lambda row, p=prefix, st=still: row.signature[len(p):] in st,
                resolution=f"the census at {_now().isoformat()} observed the listing as "
                           f"expected")
            resolved += life["resolved"]
    # K8 F-568: an owner-recorded violation past its deadline is restated OVERDUE daily.
    from ..commerce import policy_violations

    violations = policy_violations.escalate_overdue(ctx.db)
    # K8 F-545: the unified lifecycle (incl. stranded test listings) beside the census.
    store_reading(ctx.db, LIFECYCLE_READING, listing_lifecycle.summary(ctx.db))
    for lid in drift_opened:
        k = known.get(lid) or {}
        listing_lifecycle.record(
            ctx.db, action="observe_drift", listing_id=lid, actor="etsy.listing_census",
            evidence="getListing + getAllListingFiles + getListingImages read-back",
            before={"certified_restore": (plans.get(lid) or {}).get("restore")},
            after={"drift": drift[lid][:10]}, result="reconcile incident opened",
            slug=k.get("slug"), version=k.get("version"))
    ctx.audit("etsy.listing_census", detail={
        "evidence": status.evidence_state, "observed": len(observed), "known": len(known),
        "delivery": delivery, "refused_renewals": len(renewals["refused_renewals"]),
        "overdue_violations": violations["overdue"],
        "expired_proposals": len(renewals["proposals"]),
        "suspected_policy": sorted(suspected), "unexpected": sorted(unexpected),
        "field_drift": sorted(drift), "incidents_opened": opened,
        "incidents_resolved": resolved})
    return {"evidence": status.evidence_state, "observed": len(observed),
            "suspected_policy": sorted(suspected), "unexpected": sorted(unexpected),
            "field_drift": sorted(drift), "delivery": delivery,
            "refused_renewals": [r["listing_id"] for r in renewals["refused_renewals"]],
            "expired": sorted({p["listing_id"] for p in renewals["proposals"]})}


# ---- W4-STORE: the live storefront is authoritative -- read-back drift job --------------

LIVE_DRIFT_READING = "store.live_drift"
LIVE_OWNER_FIELD_BLANK = "store.live:owner_field_blank:"


@handlers.register("store.live_drift")
def handle_store_live_drift(ctx: JobContext) -> dict:
    """Repo draft vs live shop, from stored readings only (getShop snapshot + owner
    observations). Stores the drift report; never writes to Etsy and never edits a draft.

    Owner-configured fields (logo, banner, title, About, Laura's member profile/role) are
    authoritative live: a difference proposes ADOPT_LIVE_INTO_REPO, never a write. An owner
    field the live read shows blank opens a P3 incident (the owner reported setting it), which
    resolves on a later reading that shows it set. UNKNOWN fields open and resolve nothing.
    """
    from ..ops import incident_lifecycle as lifecycle
    from ..store_foundation import live_state

    report = live_state.drift(ctx.db)
    store_reading(ctx.db, LIVE_DRIFT_READING, report)
    opened, resolved = [], []
    with ctx.db.session() as s:
        for row in report["fields"]:
            if not row["owner_configured"] or row["status"] == live_state.UNKNOWN:
                continue
            signature = f"{LIVE_OWNER_FIELD_BLANK}{row['field']}"
            if row["status"] == live_state.LIVE_BLANK_OWNER_FIELD:
                _, new = lifecycle.open_or_restate(
                    s, signature=signature, severity="P3", halts_publication=False,
                    summary=f"{row['label']}: the owner configured it but the live read "
                            f"({row['live_source']}, {row['observed_at']}) shows it blank",
                    detail={"field": row["field"], "proposal": row["proposal"]})
                if new:
                    opened.append(signature)
            else:
                resolved += lifecycle.resolve_signatures(
                    s, [signature], resolution=f"live read at {row['observed_at']} shows "
                                               f"{row['field']} set")
    # W4-GATESB: the store owner actions become OwnerAction rows, so the inbox batches them.
    from ..store_foundation import store_readiness

    owner_rows = store_readiness.sync_owner_actions(ctx.db, report)
    ctx.audit("store.live_drift", detail={
        "owner_actions": owner_rows,
        "counts": report["counts"], "unknown": report["unknown"],
        "proposals": len(report["proposals"]), "findings": report["findings"][:10],
        "incidents_opened": opened, "incidents_resolved": resolved, "writes_performed": 0})
    return {"counts": report["counts"], "unknown": len(report["unknown"]),
            "proposals": len(report["proposals"]), "findings": len(report["findings"]),
            "incidents_opened": opened, "writes_performed": 0}


# ---- F-514: the surface classifications re-verified against Etsy's API document --------


def reverify_openapi(db, *, transport=None, now: datetime | None = None,
                     force: bool = False) -> dict:
    """Read Etsy's public OpenAPI document (read-only, no credential) and re-verify every
    surface's classification against it (`etsy_surfaces.openapi_reverify`).

    A reading younger than OPENAPI_REVERIFY_DAYS stands unless `force`. A failed fetch or an
    unreadable document is stored as UNREADABLE -- the classifications are then unconfirmed,
    never assumed current. DRIFTED opens one P2 incident naming the affected surfaces; a later
    CURRENT reading resolves it. Nothing is written to Etsy.
    """
    from ..integrations.http import UrllibTransport
    from ..intel import etsy_surfaces
    from ..ops import incident_lifecycle as lifecycle

    now = now or _now()
    previous = latest_reading(db, OPENAPI_READING)
    if previous and not force and previous.get("status") != etsy_surfaces.OPENAPI_UNREADABLE:
        try:
            age = now - datetime.fromisoformat(previous["checked_at"])
        except (KeyError, TypeError, ValueError):
            age = None
        if age is not None and age < timedelta(days=OPENAPI_REVERIFY_DAYS):
            return {**previous, "reused": True}
    transport = transport or UrllibTransport()
    try:
        response = transport.request("GET", etsy_surfaces.OPENAPI_URL, headers={})
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        result = etsy_surfaces.openapi_reverify(response.body)
    except Exception as e:  # noqa: BLE001 - an unread document confirms nothing
        result = {"status": etsy_surfaces.OPENAPI_UNREADABLE, "affected": [],
                  "why": f"Etsy's OpenAPI document could not be read: "
                         f"{type(e).__name__}: {str(e)[:200]}"}
    result = {**result, "checked_at": now.isoformat(), "source": etsy_surfaces.OPENAPI_URL}
    store_reading(db, OPENAPI_READING, result, now=now)
    with db.session() as s:
        if result["status"] == etsy_surfaces.OPENAPI_DRIFTED:
            lifecycle.open_or_restate(
                s, signature=OPENAPI_DRIFT, severity="P2",
                summary=("Etsy's API document moved under the surface registry: "
                         + ", ".join(a["surface"] for a in result["affected"][:6])
                         + (" (operations added/removed)" if not result["affected"] else "")),
                detail={k: result.get(k) for k in ("version", "removed_operations",
                                                   "added_operations", "absence_drift",
                                                   "affected")})
        elif result["status"] == etsy_surfaces.OPENAPI_CURRENT:
            lifecycle.resolve_signatures(
                s, [OPENAPI_DRIFT], resolution=f"re-verified CURRENT at {now.isoformat()}")
    return result


@handlers.register("etsy.openapi_reverify")
def handle_openapi_reverify(ctx: JobContext) -> dict:
    """Weekly: the surface classifications re-verified against Etsy's published document."""
    result = reverify_openapi(ctx.db)
    ctx.audit("etsy.openapi_reverify", detail={
        "status": result["status"], "reused": bool(result.get("reused")),
        "affected": [a["surface"] for a in result.get("affected") or []][:20],
        "writes_performed": 0})
    return {"status": result["status"], "affected": len(result.get("affected") or []),
            "writes_performed": 0}
