"""WS4-2: the Standing Publication Policy (SP) object and its sealed chain.

Design: research/final_build/w6/WS4_standing_policy_design.md §1, §2.2, §2.4, §5.2, with
Main's binding amendments in §9 (M1-M6). This module is increment 2 of M6: the policy object
and its chain. It ISSUES NOTHING. The issuer (WS4-6/7), the per-product grant (SEG, WS4-7/8),
the boundary classifier (`ops/standing_boundary.py`) and the stop watch
(`ops/standing_stop.py`, the default reader of `resume`) are separate modules. Until the
issuer process exists, `effective()` can report a policy as effective only in a deployment that
`deployment_mode()` reports as Mode T, and Mode T cannot be reported today. So no policy can
be activated, and nothing here can authorise a listing.

What an SP is: an owner-signed, versioned, revocable statement of exactly which products the
system may create Etsy DRAFT listings for without asking per product (v1: `store.publish`
only; going live stays per product, §9 M1 Stage A is a later increment).

Rows (AuditLog, one GrantLedger chain, `extra_actions` from WS4-1):

* `owner.standing_policy.approved`: the signed content. Owner request + step-up.
* `owner.standing_policy.activated`: points at one approved row. Owner request + step-up.
* `owner.standing_policy.revoked`: deny-direction (GrantLedger.revoke). Any process that can
  sign may write it. If none can, an unsealed row is written, which still revokes and breaks
  the chain (fail closed, reported as tampering).
* `owner.standing_policy.rebased`: owner request + step-up. Voids every earlier row.
* `system.standing_policy.suspended`: deny-direction, written by the stop watch, the issuer or
  the worker. It verifies under the policy key OR under the ops-token HMAC with this family's
  own domain, so a process that holds only the ops token can suspend and can never approve.
  An unsealed suspension still suspends (it breaks the chain: T-CH-3).
* `owner.standing_policy.resumed`: owner request + step-up, and only while no stop condition
  holds.

Keys: `BRAMBLELOOP_POLICY_SIGNING_KEY` / `BRAMBLELOOP_POLICY_VERIFY_KEY` (Ed25519, base64 of
the raw 32 bytes). They must differ from every other key (`key_health`). The signing rules
are the storefront rules: never in a job process, never while the embedded worker is on, and
only inside the owner's Command Center request (`owner_grant_keys.owner_request`, the one
owner-request context WS4-0 introduced) for anything that grants or re-anchors.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone

SCHEMA = "brambleloop.standing_policy/1"
CEILINGS_VERSION = "ws4-ceilings/1"
PRINCIPAL = "owner:command-center"
SIGNATURE = "standing_policy:chain"
LABEL = "standing publication policy"
DOMAIN = "brambleloop/standing-policy/v1"
SUSPENSION_DOMAIN = "brambleloop/standing-policy/suspension/v1"

APPROVED = "owner.standing_policy.approved"
ACTIVATED = "owner.standing_policy.activated"
REVOKED = "owner.standing_policy.revoked"
REBASED = "owner.standing_policy.rebased"
SUSPENDED = "system.standing_policy.suspended"
RESUMED = "owner.standing_policy.resumed"
SHADOW_DECISION = "standing_policy.shadow_decision"

SIGNING_KEY_VAR = "BRAMBLELOOP_POLICY_SIGNING_KEY"
VERIFY_KEY_VAR = "BRAMBLELOOP_POLICY_VERIFY_KEY"
ISSUER_KEY_VAR = "BRAMBLELOOP_GRANT_ISSUER_KEY"
ISSUER_VERIFY_KEY_VAR = "BRAMBLELOOP_GRANT_ISSUER_VERIFY_KEY"
ENABLED_VAR = "BRAMBLELOOP_STANDING_POLICY_ENABLED"
EMBEDDED_VAR = "BRAMBLELOOP_EMBEDDED_WORKER"

# States `effective()` reports. Only EFFECTIVE may ever back an issuance.
EFFECTIVE, ISSUE_PAUSED, SUSPENDED_STATE, NOT_YET, DEAD, NONE, BROKEN = (
    "EFFECTIVE", "ISSUE_PAUSED", "SUSPENDED", "NOT_YET", "DEAD", "NONE", "BROKEN")

# ---------------------------------------------------------------------------------------------
# Code ceilings (§1.2, approved as drafted in §9 M5). Changing one is a reviewed code change.
# `approve()` refuses any policy that exceeds one; the issuer re-checks them before every
# issuance (WS4-6).
# ---------------------------------------------------------------------------------------------
MAX_PER_DAY = 3
MAX_PER_7D = 10
MAX_OUTSTANDING = 2
SEG_TTL_MINUTES = 15
SEG_TTL_CEILING_MINUTES = 30
MAX_REVIEW_WINDOW_DAYS = 90
MAX_EXPIRY_AFTER_REVIEW_DAYS = 30
MAX_RISK_CLASS = "B"
RISK_ORDER = ("A", "B", "C")
PRICE_FLOOR_CAD, PRICE_CEILING_CAD = 1.00, 40.00
ALLOWED_ACTIONS = frozenset({"store.publish"})
MIN_SHADOW_DAYS = 7
MAX_LISTING_FEES_CAD_PER_30D = 0.00          # v1 is draft-only: drafts are free
MAX_ROLLBACK_REHEARSAL_AGE_DAYS = 14
MAX_POLICY_READING_AGE_DAYS = 7
MAX_STOP_WATCH_SILENCE_MINUTES = 30
# The evidence-class keys of `gates.risk_matrix` (so `risk_matrix.satisfies` can compare them).
PHYSICAL_ORDER = ("none", "partial_physical", "full_physical_make")
# Every one of these must be required (a policy may add more, never drop one).
REQUIRED_CERTIFICATIONS_FLOOR = frozenset({
    "certification", "parity", "listing_set", "disclosure", "policy", "search", "rollback",
    "first_customer_blocking_empty", "release_gates_for_publish", "originality",
    "standards", "size_claims", "exported_frame_review", "independent_vision_review"})
# Every stop condition must be present; the booleans must be on, the counts at most these.
STOP_BOOLEANS = ("etsy_policy_notice_any", "open_p0_any", "authority_tamper_any",
                 "publish_incomplete_any", "census_drift_on_policy_listing")
STOP_COUNT_CEILINGS = {"open_defect_incident_on_policy_product": 1, "refunds_7d_count": 2,
                       "refund_rate_30d_pct": 10.0, "dead_letters_60m": 5,
                       "stop_watch_max_silence_minutes": MAX_STOP_WATCH_SILENCE_MINUTES}

_POLICY_ID = re.compile(r"^sp-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TOP_KEYS = frozenset({"schema", "policy_id", "version", "supersedes", "actions", "etsy",
                       "product_classes", "exclusions", "required_certifications", "evidence",
                       "frequency", "spend", "stop_conditions", "validity",
                       "owner_statement_digest", "code_ceilings_version"})
_CLASS_KEYS = frozenset({"class_id", "categories", "max_effective_risk_class",
                         "physical_required", "price_band_cad", "max_sizes",
                         "colourwork_allowed", "wearable_allowed"})


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _when(value) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None   # a naive timestamp is ambiguous: refused


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if v == v and v not in (float("inf"), float("-inf")) else None


# ---------------------------------------------------------------------------------------------
# Content: validation against the schema and the code ceilings
# ---------------------------------------------------------------------------------------------

def ceiling_refusals(content: dict) -> list[str]:
    """Every reason this content is not an acceptable v1 policy. [] means acceptable.

    Strict: an unknown key, a missing key, a wrong type or an unparseable value is a refusal,
    never a default. A ceiling is a bound the owner cannot sign past."""
    out: list[str] = []
    c = content if isinstance(content, dict) else None
    if c is None:
        return ["policy content is not a mapping"]
    keys = set(c)
    if keys != _TOP_KEYS:
        if keys - _TOP_KEYS:
            out.append(f"unknown policy fields: {sorted(keys - _TOP_KEYS)}")
        if _TOP_KEYS - keys:
            out.append(f"missing policy fields: {sorted(_TOP_KEYS - keys)}")
        return out
    if c["schema"] != SCHEMA:
        out.append(f"schema must be {SCHEMA}")
    if c["code_ceilings_version"] != CEILINGS_VERSION:
        out.append(f"code_ceilings_version must be {CEILINGS_VERSION}")
    if not isinstance(c["policy_id"], str) or not _POLICY_ID.match(c["policy_id"]):
        out.append("policy_id must be sp-<uuid4>")
    if not isinstance(c["version"], int) or isinstance(c["version"], bool) or c["version"] < 1:
        out.append("version must be an integer >= 1")
    sup = c["supersedes"]
    if sup is not None and (not isinstance(sup, dict) or set(sup) != {"row_id", "seal"}
                            or not isinstance(sup.get("row_id"), int)
                            or not isinstance(sup.get("seal"), str)):
        out.append("supersedes must be null or {row_id, seal}")
    acts = c["actions"]
    if (not isinstance(acts, list) or not acts or len(set(acts)) != len(acts)
            or not set(acts) <= ALLOWED_ACTIONS):
        out.append(f"actions must be a non-empty subset of {sorted(ALLOWED_ACTIONS)} in v1")
    etsy = c["etsy"]
    if (not isinstance(etsy, dict) or set(etsy) != {"shop_id", "shop_name"}
            or not isinstance(etsy.get("shop_id"), str)
            or not re.fullmatch(r"[0-9]{1,20}", etsy.get("shop_id") or "")
            or not isinstance(etsy.get("shop_name"), str) or not etsy["shop_name"].strip()):
        out.append("etsy must name a numeric shop_id and a shop_name")
    out += _class_refusals(c["product_classes"])
    ex = c["exclusions"]
    if (not isinstance(ex, dict) or set(ex) != {"launch0_slugs", "slugs", "categories"}
            or ex.get("launch0_slugs") != "ALWAYS"
            or not isinstance(ex.get("slugs"), list)
            or not all(isinstance(s, str) for s in ex.get("slugs") or [])
            or not isinstance(ex.get("categories"), list)
            or not all(isinstance(s, str) for s in ex.get("categories") or [])):
        out.append("exclusions must be {launch0_slugs: 'ALWAYS', slugs: [..], categories: [..]}")
    certs = c["required_certifications"]
    if not isinstance(certs, list) or not all(isinstance(x, str) for x in certs):
        out.append("required_certifications must be a list of names")
    elif missing := REQUIRED_CERTIFICATIONS_FLOOR - set(certs):
        out.append(f"required_certifications may not drop {sorted(missing)}")
    out += _evidence_refusals(c["evidence"])
    out += _frequency_refusals(c["frequency"])
    sp = c["spend"]
    fees = _num((sp or {}).get("max_listing_fees_cad_per_30d")) if isinstance(sp, dict) else None
    if (not isinstance(sp, dict) or set(sp) != {"max_listing_fees_cad_per_30d", "ads"}
            or fees is None or fees < 0 or fees > MAX_LISTING_FEES_CAD_PER_30D):
        out.append(f"spend.max_listing_fees_cad_per_30d must be within "
                   f"[0, {MAX_LISTING_FEES_CAD_PER_30D:.2f}] in v1")
    if not isinstance(sp, dict) or sp.get("ads") != "NONE":
        out.append("spend.ads must be NONE")
    out += _stop_refusals(c["stop_conditions"])
    out += _validity_refusals(c["validity"])
    if not isinstance(c["owner_statement_digest"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", c["owner_statement_digest"]):
        out.append("owner_statement_digest must be a sha256 hex digest")
    return out


def _class_refusals(classes) -> list[str]:
    if not isinstance(classes, list) or not classes:
        return ["product_classes must be a non-empty list"]
    out, ids = [], set()
    for i, pc in enumerate(classes):
        tag = f"product_classes[{i}]"
        if not isinstance(pc, dict) or set(pc) != _CLASS_KEYS:
            out.append(f"{tag} must have exactly {sorted(_CLASS_KEYS)}")
            continue
        if not isinstance(pc["class_id"], str) or not pc["class_id"].strip() \
                or pc["class_id"] in ids:
            out.append(f"{tag}.class_id must be a unique name")
        ids.add(pc["class_id"])
        cats = pc["categories"]
        if not isinstance(cats, list) or not cats or not all(
                isinstance(x, str) and x.strip() for x in cats):
            out.append(f"{tag}.categories must be a non-empty list of names")
        risk = pc["max_effective_risk_class"]
        if risk not in RISK_ORDER or RISK_ORDER.index(risk) > RISK_ORDER.index(MAX_RISK_CLASS):
            out.append(f"{tag}.max_effective_risk_class must be at most {MAX_RISK_CLASS}")
        if pc["physical_required"] not in PHYSICAL_ORDER:
            out.append(f"{tag}.physical_required must be one of {PHYSICAL_ORDER}")
        band = pc["price_band_cad"]
        lo, hi = ((_num(band[0]), _num(band[1]))
                  if isinstance(band, list) and len(band) == 2 else (None, None))
        if lo is None or hi is None or not (PRICE_FLOOR_CAD <= lo <= hi <= PRICE_CEILING_CAD):
            out.append(f"{tag}.price_band_cad must be [lo, hi] within "
                       f"[{PRICE_FLOOR_CAD:.2f}, {PRICE_CEILING_CAD:.2f}]")
        ms = pc["max_sizes"]
        if not isinstance(ms, int) or isinstance(ms, bool) or ms < 1:
            out.append(f"{tag}.max_sizes must be an integer >= 1")
        for flag in ("colourwork_allowed", "wearable_allowed"):
            if not isinstance(pc[flag], bool):
                out.append(f"{tag}.{flag} must be true or false")
    return out


def _evidence_refusals(ev) -> list[str]:
    keys = {"rollback_rehearsal_max_age_days", "policy_reading_max_age_days",
            "vision_reviewer_must_differ_from_generator", "min_shadow_days_before_activation"}
    if not isinstance(ev, dict) or set(ev) != keys:
        return [f"evidence must have exactly {sorted(keys)}"]
    out = []
    for k, ceiling in (("rollback_rehearsal_max_age_days", MAX_ROLLBACK_REHEARSAL_AGE_DAYS),
                       ("policy_reading_max_age_days", MAX_POLICY_READING_AGE_DAYS)):
        v = _num(ev[k])
        if v is None or v <= 0 or v > ceiling:
            out.append(f"evidence.{k} must be within (0, {ceiling}]")
    if ev["vision_reviewer_must_differ_from_generator"] is not True:
        out.append("evidence.vision_reviewer_must_differ_from_generator must be true")
    v = ev["min_shadow_days_before_activation"]
    if not isinstance(v, int) or isinstance(v, bool) or v < MIN_SHADOW_DAYS:
        out.append(f"evidence.min_shadow_days_before_activation must be at least "
                   f"{MIN_SHADOW_DAYS}")
    return out


def _frequency_refusals(fr) -> list[str]:
    keys = {"max_per_day", "max_per_7d", "min_spacing_minutes",
            "max_outstanding_unconsumed_grants"}
    if not isinstance(fr, dict) or set(fr) != keys:
        return [f"frequency must have exactly {sorted(keys)}"]
    out = []
    for k, ceiling in (("max_per_day", MAX_PER_DAY), ("max_per_7d", MAX_PER_7D),
                       ("max_outstanding_unconsumed_grants", MAX_OUTSTANDING)):
        v = fr[k]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > ceiling:
            out.append(f"frequency.{k} must be an integer within [1, {ceiling}]")
    v = fr["min_spacing_minutes"]
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        out.append("frequency.min_spacing_minutes must be an integer >= 0")
    if (isinstance(fr["max_per_day"], int) and isinstance(fr["max_per_7d"], int)
            and fr["max_per_day"] > fr["max_per_7d"]):
        out.append("frequency.max_per_day may not exceed max_per_7d")
    return out


def _stop_refusals(st) -> list[str]:
    keys = set(STOP_BOOLEANS) | set(STOP_COUNT_CEILINGS)
    if not isinstance(st, dict) or set(st) != keys:
        return [f"stop_conditions must have exactly {sorted(keys)}"]
    out = [f"stop_conditions.{k} must be true" for k in STOP_BOOLEANS if st[k] is not True]
    for k, ceiling in STOP_COUNT_CEILINGS.items():
        v = _num(st[k])
        if v is None or v <= 0 or v > ceiling:
            out.append(f"stop_conditions.{k} must be within (0, {ceiling}]")
    return out


def _validity_refusals(va) -> list[str]:
    if not isinstance(va, dict) or set(va) != {"not_before", "review_by", "expires_at"}:
        return ["validity must have exactly not_before, review_by, expires_at"]
    nb, rb, ex = (_when(va["not_before"]), _when(va["review_by"]), _when(va["expires_at"]))
    if nb is None or rb is None or ex is None:
        return ["validity times must be ISO 8601 with a UTC offset"]
    out = []
    if not nb < rb <= ex:
        out.append("validity must satisfy not_before < review_by <= expires_at")
    if rb - nb > timedelta(days=MAX_REVIEW_WINDOW_DAYS):
        out.append(f"validity: review_by may be at most {MAX_REVIEW_WINDOW_DAYS} days after "
                   f"not_before")
    if ex - rb > timedelta(days=MAX_EXPIRY_AFTER_REVIEW_DAYS):
        out.append(f"validity: expires_at may be at most {MAX_EXPIRY_AFTER_REVIEW_DAYS} days "
                   f"after review_by")
    return out


# ---------------------------------------------------------------------------------------------
# The statement the owner signs (§1.3)
# ---------------------------------------------------------------------------------------------

def render_statement(content: dict) -> str:
    """The exact text the owner reads and confirms. Deterministic: every field that changes
    what the policy allows appears in it, so `statement_digest` changes with any of them."""
    c = content
    classes = "; ".join(
        f"{pc['class_id']} = {', '.join(pc['categories'])}, risk class at most "
        f"{pc['max_effective_risk_class']}, CA${float(pc['price_band_cad'][0]):.2f}-"
        f"CA${float(pc['price_band_cad'][1]):.2f}, physical evidence {pc['physical_required']}"
        f", at most {pc['max_sizes']} size(s), colourwork "
        f"{'allowed' if pc['colourwork_allowed'] else 'not allowed'}, wearables "
        f"{'allowed' if pc['wearable_allowed'] else 'not allowed'}"
        for pc in c["product_classes"])
    ex = c["exclusions"]
    never = ", ".join(["Launch-0 products (always)"]
                      + [f"category {x}" for x in ex["categories"]]
                      + [f"product {x}" for x in ex["slugs"]])
    st = c["stop_conditions"]
    stops = "; ".join([f"{k} = {st[k]}" for k in sorted(st)])
    ev, fr, va, sp = c["evidence"], c["frequency"], c["validity"], c["spend"]
    sup = c["supersedes"]
    lines = [
        f"STANDING PUBLICATION POLICY {c['policy_id']} version {c['version']}",
        f"Schema {c['schema']}; code ceilings {c['code_ceilings_version']}; supersedes "
        + (f"row {sup['row_id']} (seal {sup['seal'][:16]})" if sup else "nothing") + ".",
        "",
        "I, the owner of Brambleloop Studio, authorise the Brambleloop policy authority to "
        f"create Etsy DRAFT listings on shop {c['etsy']['shop_name']} (id "
        f"{c['etsy']['shop_id']}) without asking me for each product, only while ALL of the "
        "following hold:",
        "",
        f"  Actions: {', '.join(sorted(c['actions']))} only.",
        f"  Products: only {classes}.",
        f"  Never: {never}, or anything not listed above.",
        f"  Evidence: every one of {', '.join(sorted(c['required_certifications']))} reads "
        "PASS on the exact release; UNKNOWN is a refusal. Rollback rehearsal at most "
        f"{ev['rollback_rehearsal_max_age_days']} days old; policy reading at most "
        f"{ev['policy_reading_max_age_days']} days old; the vision reviewer must differ from "
        f"the generator: {ev['vision_reviewer_must_differ_from_generator']}; at least "
        f"{ev['min_shadow_days_before_activation']} days of shadow before activation.",
        f"  Pace: at most {fr['max_per_day']} per day, {fr['max_per_7d']} per 7 days, "
        f"{fr['min_spacing_minutes']} minutes apart, {fr['max_outstanding_unconsumed_grants']}"
        " outstanding unused grant(s).",
        f"  Money: CA${float(sp['max_listing_fees_cad_per_30d']):.2f} in listing fees per 30 "
        f"days; advertising: {sp['ads']}.",
        f"  Stops: the policy suspends itself on {stops}.",
        f"  Period: from {va['not_before']} until {va['expires_at']}; I will review it by "
        f"{va['review_by']}.",
        "",
        "This policy cannot activate a listing, change a price, spend on advertising, or "
        "change itself. Any product outside it is held for my individual decision. I can "
        "suspend or revoke it at any time, and either takes effect at the next check (at most "
        "15 minutes).",
    ]
    return "\n".join(lines) + "\n"


def statement_digest(content: dict) -> str:
    return hashlib.sha256(render_statement(content).encode("utf-8")).hexdigest()


def confirmation_phrase(content: dict) -> str:
    """What the owner types: `AUTHORISE <policy_id> v<version> <digest[:8]>`."""
    return f"AUTHORISE {content['policy_id']} v{content['version']} " \
           f"{statement_digest(content)[:8]}"


# ---------------------------------------------------------------------------------------------
# Keys and sealing
# ---------------------------------------------------------------------------------------------
_JOB_PROCESS = {"is": False}
_REVOCATION_KEYS = frozenset({"principal", "approval_id", "grant_seal", "revoked_at", "event",
                              "seq", "prev_id", "prev_seal"})
_SUSPENSION_KEYS = frozenset({"principal", "policy_id", "reason", "by", "suspended_at",
                              "event", "seq", "prev_id", "prev_seal"})
_LINK_OPTIONAL = frozenset({"rebase"})


def mark_job_process() -> bool:
    """A job process may never sign a policy row; scrubs the signing key. (The worker entry
    calls every family's `mark_job_process`; WS4-3 wires this one.)"""
    _JOB_PROCESS["is"] = True
    return os.environ.pop(SIGNING_KEY_VAR, None) is not None


def signing_refusal() -> str | None:
    """The storefront rules (design §1.1): never in a job process, never while job handlers
    share this process."""
    if _JOB_PROCESS["is"]:
        return "this process runs jobs, so it may never sign a standing policy row"
    if os.environ.get(EMBEDDED_VAR, "1") == "1":
        return (f"{EMBEDDED_VAR} is on: job handlers share this process, so it may not sign a "
                f"standing policy row until the worker runs as its own service")
    return None


def _b64(var: str) -> bytes:
    raw = os.environ.get(var, "").strip()
    if not raw:
        raise ValueError(f"{var} is not set in this process")
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise ValueError(f"{var} must be a base64 32-byte Ed25519 key")
    return key


def _exact(detail: dict, keys: frozenset, event: str) -> bool:
    d = detail or {}
    return d.get("event") == event and keys <= set(d) <= (keys | _LINK_OPTIONAL)


def _deny_only(detail: dict) -> bool:
    """A body that can only tighten: an exact revocation or an exact suspension."""
    return (_exact(detail, _REVOCATION_KEYS, REVOKED)
            or _exact(detail, _SUSPENSION_KEYS, SUSPENDED))


def _sign(detail: dict) -> str:
    """Ed25519 over the family domain and the canonical JSON."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ..core import owner_grant_keys

    why = signing_refusal()
    if why:
        raise ValueError(f"standing policy signing refused: {why}")
    if not _deny_only(detail) and not owner_grant_keys.in_owner_request():
        raise ValueError("a standing policy approval, activation, resume or rebase is signed "
                         "only inside the owner's Command Center request (session, "
                         "CSRF/nonce and step-up)")
    try:
        key = Ed25519PrivateKey.from_private_bytes(_b64(SIGNING_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"standing policy signing key unavailable: {exc}") from None
    return key.sign(f"{DOMAIN}\n{_json(detail)}".encode()).hex()


def _suspension_hmac(detail: dict) -> str:
    """The deny-direction seal a process holding only the ops token can produce. It verifies
    ONLY an exact suspension body (`_verify`), so it can suspend and can never grant."""
    from ..core import opsauth

    if not opsauth.configured():
        raise ValueError("ops token unavailable")
    key = os.environ[opsauth.TOKEN_VAR].strip().encode()
    return "h:" + hmac.new(key, f"{SUSPENSION_DOMAIN}\n{_json(detail)}".encode(),
                           hashlib.sha256).hexdigest()


def _seal(detail: dict) -> str:
    if _exact(detail, _SUSPENSION_KEYS, SUSPENDED):
        try:
            return _sign(detail)
        except ValueError:
            return _suspension_hmac(detail)
    return _sign(detail)


def _verify(detail: dict, seal: str) -> bool:
    """True only for a valid policy-key signature, or (for an exact suspension body only) a
    valid suspension HMAC. A missing verify key raises ValueError (the ledger refuses)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from ..core import owner_grant_keys

    s = str(seal or "")
    if s.startswith("h:"):
        if not _exact(detail, _SUSPENSION_KEYS, SUSPENDED):
            return False
        try:
            return hmac.compare_digest(s, _suspension_hmac(detail))
        except ValueError:
            return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64(VERIFY_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"standing policy verify key unavailable: {exc}") from None
    if not owner_grant_keys.is_signature(s):
        return False
    try:
        pub.verify(bytes.fromhex(s), f"{DOMAIN}\n{_json(detail)}".encode())
        return True
    except (InvalidSignature, ValueError):
        return False


def _make_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED,
                       principal=PRINCIPAL, seal=_seal, verify=_verify, signature=SIGNATURE,
                       label=LABEL, extra_actions=(ACTIVATED, SUSPENDED, RESUMED))


LEDGER = _make_ledger()


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def key_health(env: dict | None = None) -> dict:
    """Whether the policy keys are configured AND distinct from every other key (§1.1).

    A policy key equal to the storefront, issuer, owner-grant or ops-token key (raw bytes, or
    the same derived public key) is reported NOT configured: a key shared with another
    authority would let that authority's holder sign a policy."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ..core import opsauth, owner_grant_keys
    from . import storefront_authority

    env = os.environ if env is None else env

    def raw(var):
        v = (env.get(var) or "").strip()
        if not v:
            return None
        try:
            return base64.b64decode(v, validate=True)
        except Exception:  # noqa: BLE001
            return b"\x00malformed:" + v.encode()

    def pub_of(priv):
        try:
            return Ed25519PrivateKey.from_private_bytes(priv).public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        except Exception:  # noqa: BLE001
            return None

    sign_raw, verify_raw = raw(SIGNING_KEY_VAR), raw(VERIFY_KEY_VAR)
    problems = []
    if verify_raw is None or len(verify_raw) != 32:
        problems.append(f"{VERIFY_KEY_VAR} missing or not a 32-byte key")
    if sign_raw is not None:
        derived = pub_of(sign_raw) if len(sign_raw) == 32 else None
        if derived is None:
            problems.append(f"{SIGNING_KEY_VAR} is not a 32-byte Ed25519 key")
        elif verify_raw is not None and derived != verify_raw:
            problems.append(f"{SIGNING_KEY_VAR} does not match {VERIFY_KEY_VAR}")
    others = {
        "storefront": (getattr(storefront_authority, "SIGNING_KEY_VAR", None),
                       getattr(storefront_authority, "VERIFY_KEY_VAR", None)),
        "owner grant": (owner_grant_keys.SIGNING_KEY_VAR, owner_grant_keys.VERIFY_KEY_VAR),
        "grant issuer": (ISSUER_KEY_VAR, ISSUER_VERIFY_KEY_VAR),
    }
    mine = {b for b in (sign_raw, verify_raw,
                        pub_of(sign_raw) if sign_raw and len(sign_raw) == 32 else None) if b}
    for name, (svar, vvar) in others.items():
        theirs = set()
        for var in (svar, vvar):
            if var:
                b = raw(var)
                if b:
                    theirs.add(b)
                    if var == svar and len(b) == 32 and pub_of(b):
                        theirs.add(pub_of(b))
        if mine & theirs:
            problems.append(f"policy key is shared with the {name} key")
    token = (env.get(opsauth.TOKEN_VAR) or "").strip().encode()
    if token and any(token == b or base64.b64encode(b) == token for b in mine):
        problems.append("policy key is shared with the ops token")
    return {"configured": not problems, "problems": problems,
            "verify_key_fingerprint": _fingerprint(verify_raw) if verify_raw else None}


def generate_keypairs() -> dict:
    """Fresh policy and issuer pairs (base64) for the operator. Never committed or logged."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    out = {}
    for svar, vvar in ((SIGNING_KEY_VAR, VERIFY_KEY_VAR),
                       (ISSUER_KEY_VAR, ISSUER_VERIFY_KEY_VAR)):
        key = Ed25519PrivateKey.generate()
        out[svar] = base64.b64encode(key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption())).decode()
        out[vvar] = base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    return out


def deployment_mode() -> str:
    """'T' only when the issuer process has reported Mode T readiness (§2.4). The issuer
    process and its sealed heartbeat are WS4-7 and do not exist yet, so this is 'S' and every
    activation is refused. Stated plainly: no standing policy can be activated today."""
    return "S"


# ---------------------------------------------------------------------------------------------
# Reading the chain
# ---------------------------------------------------------------------------------------------

def _segment(db) -> tuple[dict, list[tuple[int, dict]]]:
    """The chain verdict and the rows of its current valid segment (after the newest rebase),
    oldest first. An invalid chain yields no rows: nothing in it is trusted."""
    from ..core.sealed_chain import load

    c = LEDGER.chain(db)
    if not c["valid"] or c.get("start_id") is None:
        return c, []
    with db.session() as s:
        rows = [(rid, d) for rid, d in load(s, LEDGER.actions) if rid >= int(c["start_id"])]
    flags = {rid: ok for rid, ok, _why in c["rows"]}
    return c, [(rid, d) for rid, d in rows if flags.get(rid)]


def _approvals(rows) -> dict[int, dict]:
    return {rid: d for rid, d in rows if d.get("event") == APPROVED}


def effective(db, *, now: datetime | None = None) -> dict:
    """The one effective policy, or why there is none.

    Returns {"state", "why", "approval_id", "activation_id", "content", "seal"}. Only
    `state == EFFECTIVE` may ever back an issuance; every other state (and any error) is a
    refusal. Fails closed: a chain that does not verify is BROKEN (and a P1 tamper incident),
    whatever any row says."""
    now = _now(now)
    out = {"state": NONE, "why": "no standing policy is active", "approval_id": None,
           "activation_id": None, "content": None, "seal": None}
    if deployment_mode() != "T":
        out_mode = "deployment is not Mode T (the issuer process does not exist yet)"
    else:
        out_mode = None
    try:
        c, rows = _segment(db)
    except Exception as exc:  # noqa: BLE001 - unreadable chain is a refusal
        return {**out, "state": BROKEN, "why": f"policy chain unreadable "
                                               f"({type(exc).__name__}): UNKNOWN"}
    if not c["valid"]:
        return {**out, "state": BROKEN,
                "why": f"policy chain does not verify ({c.get('why')}); every policy refused"}
    approvals = _approvals(rows)
    revoked = {int(d.get("approval_id")) for _rid, d in rows
               if d.get("event") == REVOKED and isinstance(d.get("approval_id"), int)}
    activation = None
    for rid, d in rows:
        if d.get("event") == ACTIVATED:
            activation = (rid, d)
    if activation is None:
        return out
    act_id, act = activation
    aid = act.get("approval_id")
    approval = approvals.get(aid) if isinstance(aid, int) else None
    if approval is None:
        return {**out, "state": BROKEN, "activation_id": act_id,
                "why": "the newest activation names no approval in the current chain segment"}
    content = approval.get("content") or {}
    base = {**out, "approval_id": aid, "activation_id": act_id, "content": content,
            "seal": approval.get("seal")}
    if aid in revoked:
        return {**base, "state": NONE, "why": f"policy approval {aid} is revoked"}
    refusals = ceiling_refusals(content)
    if refusals:
        return {**base, "state": BROKEN, "why": "approved content fails the code ceilings: "
                                                + "; ".join(refusals[:3])}
    # Suspension is per policy_id and sticky: the last suspend/resume row decides.
    suspended = None
    for _rid, d in rows:
        if d.get("policy_id") == content.get("policy_id"):
            if d.get("event") == SUSPENDED:
                suspended = d.get("reason") or "suspended"
            elif d.get("event") == RESUMED:
                suspended = None
    if suspended:
        return {**base, "state": SUSPENDED_STATE, "why": f"policy suspended: {suspended}"}
    va = content["validity"]
    nb, rb, ex = _when(va["not_before"]), _when(va["review_by"]), _when(va["expires_at"])
    if now < nb:
        return {**base, "state": NOT_YET, "why": f"policy not valid before {va['not_before']}"}
    if now >= ex:
        return {**base, "state": DEAD,
                "why": f"policy expired at {va['expires_at']}; renew it as a new version"}
    if now >= rb:
        return {**base, "state": ISSUE_PAUSED,
                "why": f"policy review was due by {va['review_by']}; issuance paused until "
                       f"the owner reviews it"}
    if out_mode:
        return {**base, "state": NONE, "why": out_mode}
    return {**base, "state": EFFECTIVE, "why": None}


# ---------------------------------------------------------------------------------------------
# Owner acts
# ---------------------------------------------------------------------------------------------

def _require_owner(stepped_up: bool, what: str) -> None:
    from ..core import owner_grant_keys

    if not owner_grant_keys.in_owner_request():
        raise ValueError(f"{what} happens only inside the owner's Command Center request")
    if stepped_up is not True:
        raise ValueError(f"{what} needs a fresh step-up")


def preview(db, content: dict) -> dict:
    """Read-only: what the owner would sign. An agent may propose a draft; nothing it writes
    is signed."""
    refusals = ceiling_refusals(content)
    try:
        text = render_statement(content) if not refusals else None
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        text, refusals = None, refusals + [f"statement cannot be rendered ({exc})"]
    return {"content": content, "statement": text,
            "digest": statement_digest(content) if text else None,
            "confirmation": confirmation_phrase(content) if text else None,
            "ceiling_refusals": refusals, "effective": effective(db)}


def approve(db, content: dict, *, digest: str, typed_confirmation: str, stepped_up: bool,
            owner_session: str, actor: str, reason: str,
            now: datetime | None = None) -> int:
    """Sign an owner-approved policy version (§1.7 step 2). APPROVED is not yet effective."""
    _require_owner(stepped_up, "approving a standing policy")
    refusals = ceiling_refusals(content)
    if refusals:
        raise ValueError("policy refused by the code ceilings: " + "; ".join(refusals))
    expected = statement_digest(content)
    if not (isinstance(digest, str) and hmac.compare_digest(digest, expected)
            and hmac.compare_digest(content["owner_statement_digest"], expected)):
        raise ValueError("the statement the owner saw is not this content (digest mismatch)")
    if not isinstance(typed_confirmation, str) or not hmac.compare_digest(
            typed_confirmation, confirmation_phrase(content)):
        raise ValueError(f"type exactly: {confirmation_phrase(content)}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    c, rows = _segment(db)
    if not c["valid"]:
        raise ValueError(f"policy chain does not verify ({c.get('why')}); the owner must "
                         f"rebase it first")
    same = [(rid, d) for rid, d in _approvals(rows).items()
            if (d.get("content") or {}).get("policy_id") == content["policy_id"]]
    if not same:
        if content["version"] != 1 or content["supersedes"] is not None:
            raise ValueError("the first version of a policy is version 1 and supersedes "
                             "nothing")
    else:
        prev_id, prev = max(same, key=lambda r: r[1]["content"]["version"])
        if content["version"] != prev["content"]["version"] + 1:
            raise ValueError(f"version must be {prev['content']['version'] + 1}")
        sup = content["supersedes"] or {}
        if sup.get("row_id") != prev_id or not hmac.compare_digest(
                str(sup.get("seal", "")), str(prev.get("seal", ""))):
            raise ValueError(f"supersedes must name row {prev_id} and its seal")
    detail = {"principal": PRINCIPAL, "actor": str(actor), "owner_session": str(owner_session),
              "stepped_up": True, "content": content, "digest": expected,
              "reason": reason.strip(), "approved_at": _now(now).isoformat()}
    return LEDGER.append(db, action=APPROVED, artifact=content["policy_id"], detail=detail)


def activate(db, approval_id: int, *, stepped_up: bool, owner_session: str, actor: str,
             now: datetime | None = None) -> int:
    """A separate owner act on a separate day (§1.7 step 4). Refused unless every
    precondition holds. Today `deployment_mode()` is 'S', so this always refuses."""
    _require_owner(stepped_up, "activating a standing policy")
    now = _now(now)
    why = activation_refusals(db, approval_id, now=now)
    if why:
        raise ValueError("activation refused: " + "; ".join(why))
    with db.session() as s:
        from ..core.models import AuditLog

        content = (s.get(AuditLog, int(approval_id)).detail or {})["content"]
    return LEDGER.append(db, action=ACTIVATED, artifact=content["policy_id"], detail={
        "principal": PRINCIPAL, "actor": str(actor), "owner_session": str(owner_session),
        "stepped_up": True, "approval_id": int(approval_id),
        "policy_id": content["policy_id"], "version": content["version"],
        "activated_at": now.isoformat()})


def activation_refusals(db, approval_id: int, *, now: datetime | None = None) -> list[str]:
    """Every reason `activate` would refuse. [] only when all preconditions hold."""
    from ..core import phase
    from ..core.models import AuditLog

    now = _now(now)
    out = []
    if deployment_mode() != "T":
        out.append("deployment is not Mode T: live standing issuance needs a separate issuer "
                   "process, an owner spend decision (design §9 M4)")
    if os.environ.get(ENABLED_VAR, "") != "1":
        out.append(f"{ENABLED_VAR} is not '1'")
    try:
        p = phase.effective(db, record_incident=False)
    except Exception as exc:  # noqa: BLE001
        p = f"UNKNOWN ({type(exc).__name__})"
    if p not in ("limited_production", "production"):
        out.append(f"effective phase is {p}, not limited_production or production")
    c, rows = _segment(db)
    approval = _approvals(rows).get(int(approval_id))
    if approval is None:
        out.append(f"{approval_id} is not a verified approval in the current chain segment")
        return out
    why = LEDGER.refusal(db, int(approval_id))
    if why:
        out.append(why)
    content = approval.get("content") or {}
    if ceiling_refusals(content):
        out.append("approved content fails the code ceilings")
        return out
    approved_at = _when(approval.get("approved_at"))
    days = content["evidence"]["min_shadow_days_before_activation"]
    if approved_at is None or now - approved_at < timedelta(days=days):
        out.append(f"the shadow period ({days} days after approval) has not passed")
    if now.date() == (approved_at or now).date():
        out.append("activation must be a separate act on a separate day from approval")
    with db.session() as s:
        from sqlalchemy import select

        shadow = s.scalars(select(AuditLog.id).where(
            AuditLog.action == SHADOW_DECISION,
            AuditLog.artifact == content["policy_id"])).first()
    if shadow is None:
        out.append("no shadow decision has been recorded for this policy (the issuer in "
                   "shadow mode, WS4-6, must run first)")
    va = content["validity"]
    if now >= _when(va["review_by"]):
        out.append("the policy's review date has passed; approve a new version")
    return out


def revoke(db, approval_id: int) -> int:
    """Deny-direction: no step-up. A revocation the process cannot seal is still written,
    unsealed: it revokes, breaks the chain, and is reported as tampering (fail closed)."""
    try:
        return LEDGER.revoke(db, int(approval_id))
    except ValueError:
        return _write_unsealed(db, REVOKED, str(int(approval_id)), {
            "principal": PRINCIPAL, "approval_id": int(approval_id),
            "revoked_at": _now().isoformat(), "unsealed": True})


def suspend(db, policy_id: str, *, reason: str, by: str, now: datetime | None = None) -> int:
    """Deny-direction (stop watch, issuer, worker, owner). Sticky until an owner resume."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("a suspension names its reason")
    detail = {"principal": PRINCIPAL, "policy_id": str(policy_id), "reason": reason.strip(),
              "by": str(by), "suspended_at": _now(now).isoformat()}
    try:
        return LEDGER.append(db, action=SUSPENDED, artifact=str(policy_id), detail=detail)
    except ValueError:
        return _write_unsealed(db, SUSPENDED, str(policy_id), {**detail, "unsealed": True})


def resume(db, policy_id: str, *, stepped_up: bool, owner_session: str, actor: str,
           stop_conditions_holding=None, now: datetime | None = None) -> int:
    """Owner + step-up, and only while no stop condition holds. The default reader is the
    stop watch (`standing_stop.holding`): every §5.1 condition plus the stop watch's silence;
    a source it cannot read is UNKNOWN, and UNKNOWN refuses."""
    _require_owner(stepped_up, "resuming a standing policy")
    if stop_conditions_holding is None:
        from . import standing_stop

        stop_conditions_holding = standing_stop.holding
    holding = stop_conditions_holding(db, policy_id)
    if holding:
        raise ValueError("resume refused while stop conditions hold: " + "; ".join(holding))
    return LEDGER.append(db, action=RESUMED, artifact=str(policy_id), detail={
        "principal": PRINCIPAL, "actor": str(actor), "owner_session": str(owner_session),
        "stepped_up": True, "policy_id": str(policy_id),
        "resumed_at": _now(now).isoformat()})


def rebase(db, reason: str, *, stepped_up: bool) -> int:
    """Owner + step-up. Voids every earlier row, so every policy must be re-approved."""
    _require_owner(stepped_up, "rebasing the standing policy chain")
    return LEDGER.rebase(db, reason)


def _write_unsealed(db, action: str, artifact: str, detail: dict) -> int:
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor=PRINCIPAL, action=action, artifact=artifact,
                       detail={**detail, "event": action})
        s.add(row)
        s.flush()
        ident = row.id
    LEDGER.chain(db)  # opens the P1 tamper incident: the chain no longer verifies
    return ident


if __name__ == "__main__":  # pragma: no cover - operator tool: prints fresh pairs once
    for name, value in generate_keypairs().items():
        print(f"{name}={value}")
