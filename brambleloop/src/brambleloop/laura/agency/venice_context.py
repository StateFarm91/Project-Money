"""The restricted business-context feed to Venice (W4-LAURAONE; D-W4-LAURA-UNIFIED-FEED;
spec/13 ADD-LCONT-10). Owner-approved for DESIGN on 2026-10-20; activation is a separate owner
decision (`BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1`, OFF by default).

So that the one Laura can talk like the CEO she is, Venice may receive a SMALL, STRUCTURED,
ALLOWLISTED pack of company context. Nothing else about the company reaches Venice.

* **Schema in code** (`FIELDS`): every field has a name, a type, a declared source (one read
  function below -- never the raw database or an arbitrary table), a size cap and a sensitivity
  class. A field not in `FIELDS` cannot be emitted.
* **Validators, fail closed**: every string is checked against deny patterns (email, phone,
  postal codes, card/IBAN shapes, key/token shapes, long digit runs such as Etsy receipt or buyer
  ids, customer/payment vocabulary) and the private-value firewall (`reject_private`). Numbers
  must be finite, non-negative aggregates. Any hit drops the WHOLE field and records its NAME
  (never its value).
* **Size cap**: the serialised pack is at most `MAX_PACK_BYTES`; lower-priority fields are dropped
  (by name) to fit.
* **Audit**: every pack actually sent is recorded in `audit_log` as `laura.venice_context.sent`
  with its sha256, field names, counts and dropped names -- never a value.
* **Preview**: `preview(db)` is exactly what `build(db)` would send (same sha256), shown to the
  owner in the Command Center.

Excluded by construction: credentials, keys and tokens; customer names, emails, addresses, Etsy
buyer data and messages; payment details; protected personal records; private conversation
(this module imports nothing private and reads no `laura_private_*` table); and anything
outside `FIELDS`. Business register only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

SWITCH_ENV = "BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE"
FORMAT = "brambleloop.laura.venice_context.v1"
MAX_PACK_BYTES = 3000
AUDIT_ACTION = "laura.venice_context.sent"

#: Sensitivity classes allowed in a pack. Anything else is never emitted.
STATUS, AGGREGATE, DECISION_TITLE = "status", "aggregate", "decision_title"
CLASSES = (STATUS, AGGREGATE, DECISION_TITLE)


def enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(SWITCH_ENV) or "").strip() == "1"


# ---------------------------------------------------------------------------
# Declared read functions (the ONLY sources). Each returns plain values, or None = UNKNOWN.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def read_company_phase(db):
    from ...core import phase as phase_mod

    return str(phase_mod.resolve(db)["phase"]).lower()


def read_open_owner_decisions(db):
    from ...app.command_center import approvals

    box = approvals.inbox(db)
    return int(box.get("open") or len(box.get("cards") or []))


def read_owner_decision_titles(db):
    from ...app.command_center import approvals

    return [str(c.get("title") or "") for c in (approvals.inbox(db).get("cards") or [])[:5]]


def read_products_by_status(db):
    from sqlalchemy import func, select

    from ...core.models import Product

    with db.session() as s:
        return {str(st): int(n) for st, n in s.execute(
            select(Product.status, func.count(Product.id)).group_by(Product.status))}


def read_certified_pattern_versions(db):
    from sqlalchemy import func, select

    from ...core.models import PatternVersion

    with db.session() as s:
        return int(s.scalar(select(func.count(PatternVersion.id)).where(
            PatternVersion.certified.is_(True))) or 0)


def read_department_jobs_24h(db):
    from sqlalchemy import func, select

    from ...core.models import Job

    since = _now() - timedelta(hours=24)
    out: dict[str, dict[str, int]] = {}
    with db.session() as s:
        for agent, status, n in s.execute(
                select(Job.agent, Job.status, func.count(Job.id))
                .where(Job.created_at >= since).group_by(Job.agent, Job.status)):
            st = getattr(status, "value", status)
            out.setdefault(str(agent), {})[str(st).lower()] = int(n)
    return out


def read_laura_priorities(db):
    from .. import executive as ex

    out = []
    for p in ex.priorities(db, limit=30):
        if p.get("status") == "closed":
            continue
        out.append({"department": str(p.get("department") or ""),
                    "status": str(p.get("status") or ""), "title": str(p.get("title") or "")})
        if len(out) >= 5:
            break
    return out


def read_laura_decisions(db):
    from .. import executive as ex

    return [{"kind": str(d.get("kind") or ""), "subject": str(d.get("subject") or "")}
            for d in ex.history(db, limit=5)]


def read_model_spend_month_cad(db):
    from sqlalchemy import func, select

    from ...core.models import CostEntry

    start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.session() as s:
        return round(float(s.scalar(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
                                    .where(CostEntry.at >= start)) or 0.0), 2)


def read_model_ceiling_month_cad(db):
    from ...finance import spend_policy

    return float(spend_policy.CEILING_CAD)


def read_revenue_total_cad(db):
    """The reconciled revenue TOTAL when measured; None (UNKNOWN, never 0) otherwise."""
    from ...app.command_center import readers

    rev = readers.revenue(db)
    if rev.get("state") != "MEASURED" or rev.get("value_cad") is None:
        return None
    return round(float(rev["value_cad"]), 2)


# ---------------------------------------------------------------------------
# The allowlist.


@dataclass(frozen=True)
class Field:
    name: str
    kind: str             # str | int | float | list_str | dict_int | dict_dict_int | list_dict
    source: str           # the declared read function's dotted name
    read: Callable
    max_size: int         # characters for text; items for collections
    sensitivity: str      # one of CLASSES
    keys: tuple[str, ...] = ()   # list_dict: the only keys kept


FIELDS: tuple[Field, ...] = (
    Field("company_phase", "str", "core.phase.resolve", read_company_phase, 20, STATUS),
    Field("open_owner_decisions", "int", "command_center.approvals.inbox (count)",
          read_open_owner_decisions, 1, AGGREGATE),
    Field("products_by_status", "dict_int", "products GROUP BY status (counts)",
          read_products_by_status, 12, AGGREGATE),
    Field("certified_pattern_versions", "int", "pattern_versions WHERE certified (count)",
          read_certified_pattern_versions, 1, AGGREGATE),
    Field("department_jobs_24h", "dict_dict_int", "jobs last 24 h GROUP BY agent, status (counts)",
          read_department_jobs_24h, 20, AGGREGATE),
    Field("model_spend_month_cad", "float", "cost_entries this UTC month (sum)",
          read_model_spend_month_cad, 1, AGGREGATE),
    Field("model_ceiling_month_cad", "float", "finance.spend_policy.CEILING_CAD",
          read_model_ceiling_month_cad, 1, AGGREGATE),
    Field("revenue_total_cad", "float", "command_center.readers.revenue (reconciled total)",
          read_revenue_total_cad, 1, AGGREGATE),
    Field("laura_priorities", "list_dict", "laura.executive.priorities (open, top 5)",
          read_laura_priorities, 5, DECISION_TITLE, keys=("department", "status", "title")),
    Field("laura_recent_decisions", "list_dict", "laura.executive.history (top 5)",
          read_laura_decisions, 5, DECISION_TITLE, keys=("kind", "subject")),
    Field("owner_decision_titles", "list_str", "command_center.approvals.inbox (titles, top 5)",
          read_owner_decision_titles, 5, DECISION_TITLE),
)
FIELD_NAMES = tuple(f.name for f in FIELDS)
MAX_TEXT = 140                 # any one string value
_IDENT = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,39}$")

# ---------------------------------------------------------------------------
# Validators (deny patterns). A hit drops the field; only its NAME is recorded.

DENY: tuple[tuple[str, re.Pattern], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", re.compile(r"\+?\d[\d\s().-]{7,}\d")),
    ("postal_ca", re.compile(r"\b[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d\b")),
    ("long_digits", re.compile(r"\d{5,}")),               # zip, receipt/buyer/order ids, cards
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("key_prefix", re.compile(r"\b(?:sk|pk|rk|xox[abp]|ghp|gho|ya29|AKIA|AIza)[-_A-Za-z0-9]{6,}")),
    ("bearer", re.compile(r"(?i)\bbearer\b|-----BEGIN|\b(?:api[_ -]?key|secret|token|password|"
                          r"passphrase)\b")),
    ("hex_or_b64_blob", re.compile(r"[A-Fa-f0-9]{24,}|[A-Za-z0-9+/_=-]{32,}")),
    ("street_address", re.compile(r"(?i)\b\d+\s+\w+\s+(?:st|street|ave|avenue|rd|road|blvd|"
                                  r"drive|dr|lane|ln|way|crescent|court)\b")),
    ("customer_payment_vocab", re.compile(
        r"(?i)\b(?:customer|buyer|receipt|transaction|refund|chargeback|payment|card|iban|"
        r"paypal|stripe|invoice|address|e-?mail|phone|message from|messages?|dm|"
        r"etsy user|shipping to)\b")),
)


class FieldRefused(ValueError):
    """A value failed validation. Carries the validator name only."""


def _check_text(v: str, max_len: int) -> str:
    from ..private.firewall import reject_private

    reject_private(v, context="laura.venice_context")
    if not isinstance(v, str):
        raise FieldRefused("type")
    v = " ".join(v.split())
    if len(v) > max_len:
        v = v[:max_len].rstrip()
    for name, pat in DENY:
        if pat.search(v):
            raise FieldRefused(name)
    return v


def _check_ident(v) -> str:
    v = str(v).strip().lower()
    if not _IDENT.match(v):
        raise FieldRefused("identifier")
    return v


def _check_number(v, *, integer: bool):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise FieldRefused("aggregate_type")
    if not math.isfinite(float(v)) or v < 0:
        raise FieldRefused("aggregate_range")
    return int(v) if integer else round(float(v), 2)


def validate(field: Field, value):
    """The value as it may be sent, or raise FieldRefused. None = UNKNOWN (sent as null)."""
    from ..private.firewall import reject_private

    reject_private(value, context="laura.venice_context")
    if field.sensitivity not in CLASSES:
        raise FieldRefused("class")
    if value is None:
        return None
    k = field.kind
    if k == "str":
        return _check_ident(_check_text(value, field.max_size))
    if k == "int":
        return _check_number(value, integer=True)
    if k == "float":
        return _check_number(value, integer=False)
    if k == "dict_int":
        if not isinstance(value, dict) or len(value) > field.max_size:
            raise FieldRefused("shape")
        return {_check_ident(a): _check_number(b, integer=True) for a, b in value.items()}
    if k == "dict_dict_int":
        if not isinstance(value, dict) or len(value) > field.max_size:
            raise FieldRefused("shape")
        return {_check_ident(a): {_check_ident(x): _check_number(y, integer=True)
                                  for x, y in (b or {}).items()} for a, b in value.items()}
    if k == "list_str":
        if field.sensitivity != DECISION_TITLE or not isinstance(value, list):
            raise FieldRefused("class")
        return [_check_text(x, MAX_TEXT) for x in value[:field.max_size]]
    if k == "list_dict":
        if field.sensitivity != DECISION_TITLE or not isinstance(value, list):
            raise FieldRefused("class")
        out = []
        for row in value[:field.max_size]:
            if not isinstance(row, dict):
                raise FieldRefused("shape")
            out.append({key: _check_text(str(row.get(key) or ""), MAX_TEXT)
                        for key in field.keys})
        return out
    raise FieldRefused("kind")


# ---------------------------------------------------------------------------
# Building, previewing and recording.


def _serialise(fields: dict) -> str:
    return json.dumps({"format": FORMAT, "fields": fields}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)


def _counts(v) -> int:
    if isinstance(v, (list, dict)):
        return len(v)
    return 0 if v is None else 1


def build(db, *, fields: tuple[Field, ...] = FIELDS) -> dict:
    """{text, sha256, fields: [names], counts, dropped: [{name, why}], bytes}. Values only in
    `text` (and `values`, for the owner's preview). Never raises."""
    values: dict = {}
    dropped: list[dict] = []
    unknown: list[str] = []
    for f in fields:
        if f.name not in FIELD_NAMES:
            dropped.append({"name": f.name, "why": "not_allowlisted"})
            continue
        try:
            raw = f.read(db)
        except Exception:  # noqa: BLE001 - unreadable is UNKNOWN (null), never 0
            values[f.name] = None
            unknown.append(f.name)
            continue
        try:
            values[f.name] = validate(f, raw)
        except Exception as exc:  # noqa: BLE001 - every refusal fails closed (field dropped)
            dropped.append({"name": f.name, "why": (str(exc)[:40] if isinstance(
                exc, FieldRefused) else type(exc).__name__)})
    # Size cap: drop from the end of the declared order (lowest priority) until it fits.
    order = [f.name for f in fields if f.name in values]
    text = _serialise(values)
    while len(text.encode("utf-8")) > MAX_PACK_BYTES and order:
        name = order.pop()
        values.pop(name, None)
        dropped.append({"name": name, "why": "size_cap"})
        text = _serialise(values)
    return {"text": text, "values": values,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "fields": sorted(values), "counts": {k: _counts(v) for k, v in values.items()},
            "dropped": dropped, "unknown": unknown, "bytes": len(text.encode("utf-8"))}


def preview(db) -> dict:
    """Exactly what would be sent (same sha256 as `build`), with each field's declared source
    and class, for the owner's Command Center view."""
    pack = build(db)
    meta = {f.name: {"source": f.source, "sensitivity": f.sensitivity, "kind": f.kind}
            for f in FIELDS}
    return {"enabled": enabled(), "switch": SWITCH_ENV, "sha256": pack["sha256"],
            "bytes": pack["bytes"], "max_bytes": MAX_PACK_BYTES, "payload": pack["text"],
            "fields": [{"name": n, "value": pack["values"][n], **meta[n]}
                       for n in pack["fields"]],
            "dropped": pack["dropped"], "unknown": pack["unknown"],
            "allowlist": [{"name": f.name, "source": f.source, "sensitivity": f.sensitivity,
                           "kind": f.kind, "max_size": f.max_size} for f in FIELDS]}


def record_sent(db, pack: dict) -> None:
    """The audit row for one pack actually sent: hash, names, counts -- never a value."""
    from ...core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="laura", action=AUDIT_ACTION, artifact=f"sha256:{pack['sha256']}",
                       detail={"sha256": pack["sha256"], "fields": list(pack["fields"]),
                               "counts": dict(pack["counts"]), "bytes": int(pack["bytes"]),
                               "dropped": [d["name"] for d in pack["dropped"]],
                               "format": FORMAT}))
