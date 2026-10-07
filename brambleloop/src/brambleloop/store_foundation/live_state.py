"""The live Etsy shop is authoritative: live-state snapshot, drift report, owner-field protection.

Wave-4 lane STORE (owner context 2026-10-06). The owner configured the REAL shop by hand today:
logo (shop icon), banner, shop title/tagline, About headline and story, and Laura's shop-member
profile with the Designer role. That live state is newer than every repository preview. This
module makes the storefront code treat it that way:

* **Owner-configured fields are protected.** `OWNER_CONFIGURED` names them. Nothing in this
  repository may propose writing them (`write_refusal` refuses), and
  `commerce.shop_package.api_shop_fields` -- the only "what may be sent to updateShop" list --
  leaves them out. When the live value differs from the repository draft, the *draft* is the
  stale side: the proposal is ADOPT_LIVE_INTO_REPO (re-render previews from the live value),
  never "push the draft".
* **A live-state snapshot record** merges the two read paths that exist: the daily `getShop`
  reading (`runtime.etsy_ops` stores it as `etsy.shop_snapshot`) and the owner's dated
  observation of fields no API returns (About headline/story, shop-member profile and role),
  recorded here as an append-only `store.live_observation` audit row. Every field carries its
  source, observed_at and freshness; a field nobody read is UNKNOWN, never "matches".
* **A drift report** compares repo draft vs live for every field and only ever *proposes*:
  every proposal has `auto_apply: False` and `write_allowed: False`. Live owner fields also
  get advisory compliance findings (title length, Laura disclosed as AI, Laura not in the
  Owner role) that go to the owner as findings, never as edits.
* `annotate(db, surfaces)` feeds the live status into `store_foundation.content` so the
  content model and previews report `entered_on_etsy` from evidence instead of UNKNOWN.

Nothing here contacts the network or writes to Etsy. The cadence handler that runs the drift
job in production is `store.live_drift` in `runtime.etsy_ops` (reads stored readings only).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

UNKNOWN = "UNKNOWN"

#: Audit action for the owner's dated readings of storefront fields.
OBSERVATION_ACTION = "store.live_observation"
#: operating_readings kind the drift job stores.
DRIFT_READING = "store.live_drift"
#: operating_readings kind `runtime.etsy_ops.handle_shop_snapshot` stores (getShop body).
SHOP_READING = "etsy.shop_snapshot"

#: The date the owner configured the live shop by hand. Recorded from the owner's statement
#: relayed by the integrator; it establishes *protection*, not the values (those are UNKNOWN
#: until read back).
OWNER_CONFIGURED_ON = "2026-10-06"

API_MAX_AGE_DAYS = 7
OBSERVATION_MAX_AGE_DAYS = 30

# field statuses
MATCH = "MATCH"
LIVE_AUTHORITATIVE_DIFFERS = "LIVE_AUTHORITATIVE_DIFFERS"
LIVE_SET_NOT_COMPARABLE = "LIVE_SET_NOT_COMPARABLE"
LIVE_BLANK_OWNER_FIELD = "LIVE_BLANK_OWNER_FIELD"
DRIFT = "DRIFT"
LIVE_MISSING = "LIVE_MISSING"
LIVE_UNEXPECTED = "LIVE_UNEXPECTED"
STALE = "STALE"

# proposal kinds -- none of them is ever executed by software
ADOPT_LIVE_INTO_REPO = "ADOPT_LIVE_INTO_REPO"
OWNER_CONFIRM = "OWNER_CONFIRM"
OWNER_REVIEW_UPDATE = "OWNER_REVIEW_UPDATE"
OWNER_ENTER = "OWNER_ENTER"
OWNER_CLEAR = "OWNER_CLEAR"
OWNER_OBSERVE = "OWNER_OBSERVE"


@dataclass(frozen=True)
class LiveField:
    key: str
    label: str
    getshop_field: str | None      # the getShop key, None when no API returns it
    draft_surface: str | None      # store_foundation.content surface holding the repo draft
    owner_configured: bool         # configured by the owner on the live shop: never overwrite
    kind: str = "text"             # text | image | role | blank | equals
    expect: Any = None
    where: str = ""


FIELDS: tuple[LiveField, ...] = (
    LiveField("shop_name", "Shop name", "shop_name", None, True, "equals", "BrambleloopStudio",
              "Settings > Your shop > Shop name (Etsy limits renames; never changed by software)"),
    LiveField("shop_icon", "Logo / shop icon", "icon_url_fullxfull", "icon", True, "image",
              None, "Settings > Your shop > Logo"),
    LiveField("shop_banner", "Banner", "image_url_760x100", "banner", True, "image", None,
              "Shop home editor > Banner"),
    LiveField("shop_title", "Shop title (tagline)", "title", "shop_title", True, "text", None,
              "Shop home editor > Shop title"),
    LiveField("about_headline", "About headline", None, None, True, "text", None,
              "Shop home editor > About > headline"),
    LiveField("about_story", "About story", None, "about", True, "text", None,
              "Shop home editor > About > story"),
    LiveField("laura_member_profile", "Laura shop-member profile (bio)", None, None, True,
              "text", None, "Settings > Your shop > Shop team / About > Shop members"),
    LiveField("laura_member_role", "Laura shop-member role", None, None, True, "role",
              "Designer", "Settings > Your shop > Shop team"),
    LiveField("announcement", "Announcement", "announcement", "announcement", False, "text",
              None, "Shop home editor > Announcement"),
    LiveField("digital_sale_message", "Message to buyers (digital items)",
              "digital_sale_message", "digital_sale_message", False, "text", None,
              "Settings > Info & Appearance > Message to Buyers for Digital Items"),
    LiveField("policy_privacy", "Privacy policy", "policy_privacy", "policy_privacy", False,
              "text", None, "Settings > Policy Settings > Privacy"),
    LiveField("policy_refunds", "Refunds / returns policy text", "policy_refunds",
              "policy_returns", False, "text", None, "Settings > Policy Settings"),
    LiveField("policy_shipping", "Delivery policy text", "policy_shipping", "policy_delivery",
              False, "text", None, "Settings > Policy Settings"),
    LiveField("policy_additional", "EU-only additional policy", "policy_additional", None,
              False, "blank", None, "must stay empty for a Canadian shop (Open API)"),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}

#: Every field the owner configured on the live shop, by our key.
OWNER_CONFIGURED: frozenset[str] = frozenset(f.key for f in FIELDS if f.owner_configured)
#: The same set expressed as getShop / updateShop field names (what an API write would name).
OWNER_CONFIGURED_API_FIELDS: frozenset[str] = frozenset(
    f.getshop_field for f in FIELDS if f.owner_configured and f.getshop_field)
#: Fields only an owner observation can evidence (no API returns them).
OBSERVATION_ONLY: frozenset[str] = frozenset(f.key for f in FIELDS if f.getshop_field is None)

#: Etsy's shop-title limit (Help Center 360000343708, research/final_build/w3).
TITLE_MAX = 55


class ObservationRefused(ValueError):
    """Not evidence: undated, from the future, unknown field, or no statement."""


class OwnerFieldProtected(PermissionError):
    """An attempt to write a field the owner configured on the live shop."""


# ---- protection -------------------------------------------------------------------------


def write_refusal(field: str) -> str | None:
    """Why software may not write `field` to the live shop (always a reason in shadow).

    Accepts our key or the getShop/updateShop field name. Owner-configured fields are refused
    permanently (a new explicit owner decision is the only route); every other field is refused
    while no Etsy write authority exists (Shadow Mode) -- the drift job only proposes.
    """
    key = _key_for(field)
    if key in OWNER_CONFIGURED:
        return (f"{field}: configured by the owner on the live shop ({OWNER_CONFIGURED_ON}); "
                f"live is authoritative and software never overwrites it -- propose to the "
                f"owner instead")
    return (f"{field}: no Etsy write authority in Shadow Mode; the drift report proposes, "
            f"the owner decides")


def guard(fields) -> None:
    """Raise `OwnerFieldProtected` if any of `fields` is owner-configured."""
    hit = sorted(f for f in fields if _key_for(f) in OWNER_CONFIGURED)
    if hit:
        raise OwnerFieldProtected(f"owner-configured live fields may not be written: {hit}")


def _key_for(field: str) -> str:
    for f in FIELDS:
        if field in (f.key, f.getshop_field):
            return f.key
    return field


# ---- observation intake -----------------------------------------------------------------


def _parse(at) -> datetime:
    if isinstance(at, datetime):
        value = at
    else:
        try:
            value = datetime.fromisoformat(str(at or "").replace("Z", "+00:00"))
        except ValueError as e:
            raise ObservationRefused("observed_at must be ISO 8601: an undated statement is "
                                     "not evidence") from e
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def record_observation(db, *, observed_at, fields: dict, statement: str,
                       recorded_by: str = "owner", now: datetime | None = None) -> dict:
    """Append the owner's dated reading of live storefront fields (append-only audit row).

    `fields` maps our field keys to what the live page shows: a string for text fields, the
    role name for `laura_member_role`, or {"present": bool} for an image. Only keys in FIELDS
    are accepted. The observation never changes the live shop and never closes anything on
    its own: the drift job reads it.
    """
    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    when = _parse(observed_at)
    if when > now:
        raise ObservationRefused("observed_at is in the future")
    if not isinstance(fields, dict) or not fields:
        raise ObservationRefused("fields must be a non-empty object of field -> live value")
    unknown = sorted(k for k in fields if k not in FIELD_BY_KEY)
    if unknown:
        raise ObservationRefused(f"unknown fields {unknown}; one of {sorted(FIELD_BY_KEY)}")
    if not str(statement or "").strip():
        raise ObservationRefused("a statement of what the live page shows is required")
    clean: dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, str):
            clean[k] = v[:6000]
        elif isinstance(v, dict) and isinstance(v.get("present"), bool):
            clean[k] = {"present": v["present"], "note": str(v.get("note") or "")[:300]}
        elif v is None:
            clean[k] = None
        else:
            raise ObservationRefused(f"{k}: a string, null, or {{present: bool}}")
    detail = {"observed_at": when.isoformat(), "fields": clean,
              "statement": str(statement)[:500]}
    with db.session() as s:
        row = AuditLog(actor=recorded_by[:64], action=OBSERVATION_ACTION,
                       artifact="etsy_shop:storefront", detail=detail)
        s.add(row)
        s.flush()
        return {"id": row.id, "fields": sorted(clean), "observed_at": detail["observed_at"]}


def _observations(db) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == OBSERVATION_ACTION)
                              .order_by(desc(AuditLog.id)).limit(200)))
        return [dict(r.detail or {}, id=r.id) for r in rows]


def _shop_reading(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == SHOP_READING)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        return dict(row.payload or {}) if row is not None else None


# ---- snapshot ---------------------------------------------------------------------------


def _digest(value: Any) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(repr(value).encode()).hexdigest()[:16]


def snapshot(db, *, now: datetime | None = None) -> dict:
    """Per field: the freshest live value we hold, its source, age and freshness.

    Sources, freshest wins: `getShop` (API_GETSHOP, tolerance 7 days) and the owner's dated
    observation (OWNER_OBSERVATION, tolerance 30 days). No source -> UNKNOWN.
    """
    now = now or datetime.now(timezone.utc)
    candidates: dict[str, list[dict]] = {f.key: [] for f in FIELDS}
    reading = _shop_reading(db) if db is not None else None
    if reading and isinstance(reading.get("shop"), dict) and reading.get("observed_at"):
        at = datetime.fromtimestamp(float(reading["observed_at"]), tz=timezone.utc)
        body = reading["shop"]
        for f in FIELDS:
            if f.getshop_field and f.getshop_field in body:
                candidates[f.key].append({"source": "API_GETSHOP", "at": at,
                                          "value": body[f.getshop_field],
                                          "max_age": API_MAX_AGE_DAYS})
    for obs in (_observations(db) if db is not None else []):
        at = _parse(obs.get("observed_at"))
        for k, v in (obs.get("fields") or {}).items():
            if k in candidates and not any(c["source"] == "OWNER_OBSERVATION"
                                           for c in candidates[k]):
                candidates[k].append({"source": "OWNER_OBSERVATION", "at": at, "value": v,
                                      "max_age": OBSERVATION_MAX_AGE_DAYS,
                                      "observation_id": obs["id"]})
    out: dict[str, dict] = {}
    for f in FIELDS:
        cands = sorted(candidates[f.key], key=lambda c: c["at"], reverse=True)
        if not cands:
            out[f.key] = {"field": f.key, "state": UNKNOWN, "source": None,
                          "observed_at": None, "value": None, "value_sha": None,
                          "owner_configured": f.owner_configured,
                          "readable_by": "getShop" if f.getshop_field else "owner observation"}
            continue
        c = cands[0]
        age = (now - c["at"]).total_seconds() / 86400.0
        state = "FRESH" if 0 <= age <= c["max_age"] else STALE
        out[f.key] = {"field": f.key, "state": state, "source": c["source"],
                      "observed_at": c["at"].isoformat(), "age_days": round(age, 2),
                      "value": c["value"], "value_sha": _digest(c["value"]),
                      "owner_configured": f.owner_configured,
                      "readable_by": "getShop" if f.getshop_field else "owner observation"}
    return out


# ---- drift ------------------------------------------------------------------------------


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _blank(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("present") is False
    return value is None or (isinstance(value, str) and not value.strip())


def repo_drafts(surfaces: dict | None = None) -> dict[str, Any]:
    """The repository draft for each field (from `store_foundation.content`)."""
    if surfaces is None:
        from . import content

        surfaces = content.build()
    out: dict[str, Any] = {}
    for f in FIELDS:
        if f.draft_surface and f.draft_surface in surfaces:
            out[f.key] = surfaces[f.draft_surface].value
        elif f.kind in ("equals", "role"):
            out[f.key] = f.expect
        else:
            out[f.key] = None
    return out


def _compliance(f: LiveField, value: Any) -> list[dict]:
    """Advisory findings on a live owner field. Reported to the owner, never edited."""
    out: list[dict] = []
    if _blank(value):
        return out
    text = str(value) if isinstance(value, str) else ""
    if f.key == "shop_title" and len(text) > TITLE_MAX:
        out.append({"code": "title_over_limit",
                    "detail": f"live title is {len(text)} chars; Etsy's limit is {TITLE_MAX}"})
    if f.key == "laura_member_role" and _norm(text) == "owner":
        out.append({"code": "laura_in_owner_role",
                    "detail": "Laura is an AI persona and must not hold Etsy's Owner role "
                              "(spec/07; Etsy: an Owner is responsible for the account)"})
    if f.key == "laura_member_profile":
        low = text.casefold()
        if not re.search(r"\bai\b|artificial intelligence", low):
            out.append({"code": "laura_ai_not_disclosed",
                        "detail": "the live Laura member bio does not say she is an AI "
                                  "(spec/07, D-FB-11..13: Laura is always disclosed as an AI)"})
        if re.search(r"\bi (?:crochet|hand ?made|stitch(?:ed)?|knit)\b|\breal person\b", low):
            out.append({"code": "laura_human_claim",
                        "detail": "the live Laura bio reads as a human making claim"})
    if f.key in ("about_story", "about_headline", "shop_title", "laura_member_profile"):
        from . import lint

        for finding in lint.lint(text, surface=f.key, voice=False):
            if finding["kind"] == lint.TRUTH:
                out.append({"code": f"truth_lint:{finding['code']}",
                            "detail": finding["detail"][:240]})
    return out


def drift(db, *, now: datetime | None = None, surfaces: dict | None = None) -> dict:
    """Repo draft vs live, field by field. Proposals only; nothing here writes anything."""
    now = now or datetime.now(timezone.utc)
    snap = snapshot(db, now=now)
    drafts = repo_drafts(surfaces)
    rows: list[dict] = []
    for f in FIELDS:
        live = snap[f.key]
        draft = drafts.get(f.key)
        row: dict[str, Any] = {"field": f.key, "label": f.label,
                               "owner_configured": f.owner_configured,
                               "live_state": live["state"], "live_source": live["source"],
                               "observed_at": live["observed_at"],
                               "live_sha": live["value_sha"], "draft_sha": _digest(draft),
                               "where": f.where, "proposal": None, "findings": [],
                               "write_refusal": write_refusal(f.key)}
        if live["state"] == UNKNOWN:
            row["status"] = UNKNOWN
            row["proposal"] = _proposal(
                OWNER_OBSERVE if f.getshop_field is None else OWNER_CONFIRM, f,
                "no live reading: run getShop after re-authorisation (Batch A1)"
                if f.getshop_field else
                "no API returns this field: record a dated owner observation "
                "(POST store.live_observation)")
            rows.append(row)
            continue
        value = live["value"]
        if f.kind == "image":
            if _blank(value):
                row["status"] = LIVE_BLANK_OWNER_FIELD
                row["proposal"] = _proposal(OWNER_CONFIRM, f, "the owner reported setting this "
                                            "today but the live read shows none")
            else:
                row["status"] = LIVE_SET_NOT_COMPARABLE
                row["detail"] = ("live image present; Etsy re-encodes uploads, so bytes are not "
                                 "comparable with the repo file -- live is authoritative")
        elif f.kind == "blank":
            row["status"] = MATCH if _blank(value) else LIVE_UNEXPECTED
            if not _blank(value):
                row["proposal"] = _proposal(OWNER_CLEAR, f, "EU-only field set on a Canadian "
                                            "shop")
        elif f.kind in ("equals", "role"):
            if _blank(value):
                row["status"] = LIVE_BLANK_OWNER_FIELD if f.owner_configured else LIVE_MISSING
            elif _norm(value) == _norm(f.expect):
                row["status"] = MATCH
            else:
                row["status"] = LIVE_AUTHORITATIVE_DIFFERS
                row["proposal"] = _proposal(ADOPT_LIVE_INTO_REPO, f,
                                            f"live is {value!r}; repo expected {f.expect!r}")
        else:
            draft_text = draft if isinstance(draft, str) else None
            if _blank(value):
                if f.owner_configured:
                    row["status"] = LIVE_BLANK_OWNER_FIELD
                    row["proposal"] = _proposal(OWNER_CONFIRM, f, "the owner reported "
                                                "setting this today but the live read is "
                                                "blank")
                else:
                    row["status"] = LIVE_MISSING
                    if draft_text:
                        row["proposal"] = _proposal(OWNER_ENTER, f, "live is blank; the repo "
                                                    "draft is ready to paste", draft_text)
            elif draft_text is not None and _norm(value) == _norm(draft_text):
                row["status"] = MATCH
            elif f.owner_configured:
                row["status"] = LIVE_AUTHORITATIVE_DIFFERS
                row["proposal"] = _proposal(ADOPT_LIVE_INTO_REPO, f, "live differs from the "
                                            "repo draft; the draft is stale -- re-render "
                                            "previews and copy from the live value")
            else:
                row["status"] = DRIFT
                row["proposal"] = _proposal(OWNER_REVIEW_UPDATE, f, "live differs from the "
                                            "certified draft", draft_text)
        if f.owner_configured:
            row["findings"] = _compliance(f, value)
        if live["state"] == STALE:
            row["status_note"] = "reading is stale: describes the shop as it was"
        rows.append(row)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"generated_at": now.isoformat(), "fields": rows, "counts": counts,
            "owner_configured": sorted(OWNER_CONFIGURED),
            "unknown": [r["field"] for r in rows if r["status"] == UNKNOWN],
            "proposals": [dict(r["proposal"], field=r["field"]) for r in rows if r["proposal"]],
            "findings": [dict(x, field=r["field"]) for r in rows for x in r["findings"]],
            "writes_performed": 0}


def _proposal(kind: str, f: LiveField, why: str, draft: str | None = None) -> dict:
    p = {"kind": kind, "why": why, "where": f.where, "auto_apply": False,
         "write_allowed": False}
    if draft and kind in (OWNER_ENTER, OWNER_REVIEW_UPDATE):
        p["draft_excerpt"] = draft[:200]
    return p


# ---- storefront consumption -------------------------------------------------------------

#: content surface -> our live field key, for `annotate`.
SURFACE_TO_FIELD = {f.draft_surface: f.key for f in FIELDS if f.draft_surface}


def authoritative(db, *, now: datetime | None = None) -> dict[str, dict]:
    """What the storefront should show per field: live when read, else the draft labelled."""
    snap = snapshot(db, now=now)
    out = {}
    for f in FIELDS:
        s = snap[f.key]
        if s["state"] == UNKNOWN:
            out[f.key] = {"use": "REPO_DRAFT_NOT_VERIFIED_LIVE", "live": UNKNOWN}
        else:
            out[f.key] = {"use": "LIVE", "live": s["value"], "source": s["source"],
                          "observed_at": s["observed_at"], "state": s["state"]}
    return out


def annotate(db, surfaces: dict) -> dict:
    """Set each content surface's `live` status from the snapshot (UNKNOWN when unread)."""
    snap = snapshot(db)
    for key, surface in surfaces.items():
        field = SURFACE_TO_FIELD.get(key)
        if field is None:
            continue
        s = snap[field]
        if s["state"] == UNKNOWN:
            surface.live = {"entered_on_etsy": UNKNOWN}
        else:
            surface.live = {"entered_on_etsy": "SET" if not _blank(s["value"]) else "BLANK",
                            "source": s["source"], "observed_at": s["observed_at"],
                            "state": s["state"],
                            "owner_configured": FIELD_BY_KEY[field].owner_configured}
    return surfaces
