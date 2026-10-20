"""Provider credential health: BFL (FLUX 3 Image) and Anthropic (W4-CREDHEALTH).

Architecture (owner directive, binding): Railway is the only secret store. Every generation
and vision call comes from an authorised backend job. Claude Code is never a runtime and never
holds a key. This module is the permanent check that the keys in Railway work, using the
cheapest documented authenticated call for each provider:

* **Anthropic:** `POST /v1/messages/count_tokens`, with a tiny image block plus text. It is
  free ("Token counting is free to use", docs.anthropic.com, "Token counting"). It proves the
  key authenticates and that the vision model accepts image input. It does NOT prove the
  account has credit: counting tokens is not billed. Credit is therefore read from the most
  recent real call this system recorded (`model.probe` / `vision.probe`). A credit-balance
  refusal there is INSUFFICIENT_CREDIT, and with no such record credit stays unproven, never
  assumed.
* **BFL:** `GET https://api.bfl.ai/v1/credits` with header `x-key` (docs.bfl.ml, API
  reference "Get the user's credits", OpenAPI `get_credits_v1_credits_get`, response
  `{"credits": number}`; 1 credit = US$0.01, docs.bfl.ml "Pricing"). It is free. It proves the
  key authenticates and reads the balance. A balance below the price of one 2k FLUX 3 image is
  INSUFFICIENT_CREDIT. BFL documents no free per-model entitlement check, so whether
  flux-3-image is enabled is learned only from a real render; a 403 from one is PERMISSION.

Both checks cost nothing. A zero estimate is still recorded per check (`estimate_cad: 0.0`,
with its documentation basis), so a reader can see the price was looked up rather than
assumed.

* **Venice (W4-VENICE, Private Laura's provider, D-W4-PL-VENICE):** `GET
  https://api.venice.ai/api/v1/api_keys/rate_limits` with `Authorization: Bearer <key>`
  (docs.venice.ai/api-reference/endpoint/api_keys/rate_limits: "Return details about user
  balances and rate limits"). It runs no inference and proves the key authenticates
  (`accessPermitted`) AND reads the balance (`balances.USD/DIEM/BUNDLED_CREDITS`), so credit
  is proven, not assumed. Venice does NOT document whether this call is billed: its cost is
  recorded as UNKNOWN (`estimate_cad: None`), never as 0. It therefore runs only when the owner
  has selected Venice (`BRAMBLELOOP_PRIVATE_PROVIDER=venice`); until then Venice is not
  checked at all (no request, no record, no card).

**Statuses:** OK, MISSING (variable absent), REJECTED (401/403 on the auth call),
INSUFFICIENT_CREDIT (402, or the provider's own credit error), PERMISSION (model or feature
not enabled), OUTAGE (5xx or timeout), RATE_LIMITED (429) and UNKNOWN.

**Secrets.** No key value is ever logged, stored, audited, returned or put in a job row. The
most the owner-authenticated view shows is a fingerprint: the last 4 characters and a 12-hex
sha256 prefix, so a rotation can be confirmed. Every other surface shows neither.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

ACTION = "provider.credential_health"
JOB_TYPE = "ops.provider_credentials"
OK, MISSING, REJECTED, INSUFFICIENT_CREDIT = "OK", "MISSING", "REJECTED", "INSUFFICIENT_CREDIT"
PERMISSION, OUTAGE, RATE_LIMITED, UNKNOWN = "PERMISSION", "OUTAGE", "RATE_LIMITED", "UNKNOWN"
STATUSES = (OK, MISSING, REJECTED, INSUFFICIENT_CREDIT, PERMISSION, OUTAGE, RATE_LIMITED,
            UNKNOWN)
# Owner-actionable at once; transient ones only after this many consecutive failures.
OWNER_STATUSES = (MISSING, REJECTED, INSUFFICIENT_CREDIT, PERMISSION)
TRANSIENT_STATUSES = (OUTAGE, RATE_LIMITED, UNKNOWN)
ALERT_AFTER_CONSECUTIVE = 3

BFL_CREDITS_URL = "https://api.bfl.ai/v1/credits"
ANTHROPIC_COUNT_URL = "https://api.anthropic.com/v1/messages/count_tokens"
ANTHROPIC_VERSION = "2023-06-01"
# A 1x1 PNG: the smallest image block that proves the model accepts image input.
_PIXEL_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
                  "IQAAAABJRU5ErkJggg==")

PROVIDERS: dict[str, dict] = {
    "bfl": {"label": "Black Forest Labs (FLUX 3 Image)", "var": "BRAMBLELOOP_IMAGE_KEY_BFL",
            "model": "flux-3-image",
            "check": "GET https://api.bfl.ai/v1/credits (x-key)",
            "doc": "docs.bfl.ml/api-reference/get-the-users-credits (free; 1 credit = US$0.01)",
            "console": "dashboard.bfl.ai > API Keys / Credits"},
    "anthropic": {"label": "Anthropic (Claude vision)", "var": "ANTHROPIC_API_KEY",
                  "model": "claude-haiku-4-5-20251001",
                  "check": "POST /v1/messages/count_tokens with an image block (free)",
                  "doc": "docs.anthropic.com > Token counting (free to use)",
                  "console": "console.anthropic.com > API Keys / Billing"},
    "venice": {"label": "Venice AI (Private Laura)", "var": "VENICE_API_KEY",
               "model": "venice-uncensored-1-2",
               "check": "GET https://api.venice.ai/api/v1/api_keys/rate_limits (Bearer); "
                        "runs only when BRAMBLELOOP_PRIVATE_PROVIDER=venice",
               "doc": "docs.venice.ai/api-reference/endpoint/api_keys/rate_limits (balances + "
                      "limits; no inference; billing of this call UNKNOWN, not documented)",
               "console": "venice.ai > Settings > API (keys) / API credits"},
}
VENICE_RATE_LIMITS_URL = "https://api.venice.ai/api/v1/api_keys/rate_limits"
# Public model list (documented; no key is sent): the live privacy class / availability of the
# Private Laura models, so the reply path can fail closed if Venice reclassifies one.
VENICE_MODELS_URL = "https://api.venice.ai/api/v1/models?type=text"
#: The cost of this check is not documented by Venice: UNKNOWN, never 0 (worker rules).
VENICE_CHECK_COST_BASIS = ("UNKNOWN: Venice does not document whether GET /api_keys/rate_limits "
                           "is billed; it performs no inference. Owner-enabled only.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(key: str) -> dict | None:
    """What may be shown to the authenticated owner to confirm a rotation. Never the key."""
    k = (key or "").strip()
    if not k:
        return None
    # INTEG4 / security review of 17bc373 (I8): domain-separated, so the prefix is not the
    # plain sha256 of the key that other tools publish and cannot confirm a guess made there.
    return {"last4": k[-4:], "sha256_prefix": hashlib.sha256(
        FINGERPRINT_DOMAIN + k.encode()).hexdigest()[:12]}


FINGERPRINT_DOMAIN = b"brambleloop-owner-key-fingerprint:v1:"


def _key(provider: str, env) -> str:
    if provider == "bfl":
        from .images import key_for

        return key_for("flux-3-image", env)
    return (env.get(PROVIDERS[provider]["var"]) or "").strip()


#: Largest response body read for parsing (security review M-1: never truncate BEFORE parsing;
#: Venice's model list is far longer than the old 2,000-character cut). Larger is refused.
MAX_BODY_BYTES = 2 * 1024 * 1024
TOO_LARGE = "response body over the size cap"


def _http(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    """(status, text). The one network call; tests replace it. Errors are statuses.
    Redirects are refused (security review M-2: no credential is ever re-sent to a redirect
    target); the full body is returned for parsing, up to MAX_BODY_BYTES."""
    import urllib.error
    import urllib.request

    from .venice import no_redirect_opener

    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with no_redirect_opener().open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                return 0, TOO_LARGE
            return int(resp.status), raw.decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode(errors="replace")[:2000]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, f"unreachable: {type(exc).__name__}"


# The provider's own credit words. `ops.funding.MARKERS` is the single list already used for
# the owner's funding action; BFL's "insufficient credits" spelling is added here.
_EXTRA_CREDIT_WORDS = ("insufficient_credits", "insufficient credits", "purchase credits",
                       "not enough credits")


def _credit_error(text: str) -> bool:
    from ..ops import funding

    low = (text or "").lower()
    return funding.detect(low) or any(w in low for w in _EXTRA_CREDIT_WORDS)


def classify(status: int, text: str) -> str:
    """One provider answer as a credential status. A transport failure is status 0."""
    low = (text or "").lower()
    if status == 0:
        return OUTAGE
    if 200 <= status < 300:
        return OK
    if status == 402 or _credit_error(low):
        return INSUFFICIENT_CREDIT
    if status == 401:
        return REJECTED
    if status == 403:
        # 403 on an authenticated call is a permission (model/feature/org) refusal when the
        # provider says so; a plain 403 on the auth call itself is a rejected key.
        return PERMISSION if any(w in low for w in ("permission", "not enabled",
                                                     "not available", "access to")) \
            else REJECTED
    if status == 404 and ("model" in low or "not_found" in low):
        return PERMISSION
    if status == 429:
        return RATE_LIMITED
    if status >= 500 or status == 529:
        return OUTAGE
    return UNKNOWN


def _redact(text: str, key: str) -> str:
    return (text or "").replace(key, "[redacted]") if key else (text or "")


def check_bfl(env, http=None) -> dict:
    http = http or _http
    key = _key("bfl", env)
    if not key:
        return {"status": MISSING, "why": f"{PROVIDERS['bfl']['var']} is not set"}
    status, text = http("GET", BFL_CREDITS_URL, {"x-key": key, "accept": "application/json"},
                        None, 20.0)
    cls = classify(status, text)
    out = {"status": cls, "http_status": status, "why": _redact(text, key)[:300]}
    if cls == OK:
        try:
            credits = float(json.loads(text).get("credits"))
        except (ValueError, TypeError, AttributeError):
            return {**out, "status": UNKNOWN, "why": "authenticated, but the balance was "
                                                     "unreadable"}
        from .images import BFL3_TIER_USD, USD_TO_CAD

        need = BFL3_TIER_USD["2k"] * 100.0           # credits for one 2k FLUX 3 image
        out.update(credits=credits, credits_usd=round(credits / 100.0, 2),
                   one_2k_image_credits=need,
                   why=f"authenticated; balance {credits:g} credits "
                       f"(about US${credits / 100.0:.2f}; one 2k image is {need:g})")
        if credits < need:
            out.update(status=INSUFFICIENT_CREDIT,
                       why=f"authenticated, but {credits:g} credits is less than one 2k "
                           f"FLUX 3 image ({need:g} credits)")
        out["model_permission"] = ("not checkable for free: BFL documents no entitlement "
                                   "endpoint; a 403 from a real render is PERMISSION")
    return out


def check_anthropic(env, http=None, *, db=None) -> dict:
    http = http or _http
    key = _key("anthropic", env)
    if not key:
        return {"status": MISSING, "why": f"{PROVIDERS['anthropic']['var']} is not set"}
    body = json.dumps({"model": PROVIDERS["anthropic"]["model"], "messages": [{
        "role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": _PIXEL_PNG_B64}},
            {"type": "text", "text": "ok"}]}]}).encode()
    status, text = http("POST", ANTHROPIC_COUNT_URL,
                        {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
                         "content-type": "application/json"}, body, 20.0)
    cls = classify(status, text)
    out = {"status": cls, "http_status": status, "why": _redact(text, key)[:300]}
    if cls == OK:
        out.update(why="authenticated; the model accepts an image block (count_tokens)",
                   image_input=True)
        credit = _anthropic_credit_from_record(db)
        out["credit"] = credit
        if credit.get("status") == INSUFFICIENT_CREDIT:
            out.update(status=INSUFFICIENT_CREDIT,
                       why="authenticated, but the last real call was refused for credit: "
                           + credit["why"])
    return out


def _anthropic_credit_from_record(db) -> dict:
    """Credit is not provable for free; read the last real call this system recorded."""
    if db is None:
        return {"status": UNKNOWN, "why": "no recorded real call to read"}
    try:
        from . import anthropic as A

        rows = [r for r in (A.last_probe(db), A.last_vision_probe(db)) if r]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"status": UNKNOWN, "why": "no model.probe or vision.probe on record yet"}
    latest = max(rows, key=lambda r: str(r.get("at") or ""))
    reason = str(latest.get("reason") or "")
    if latest.get("ok"):
        return {"status": OK, "why": f"a real call succeeded at {latest.get('at')}"}
    if classify(400, reason) == INSUFFICIENT_CREDIT:
        return {"status": INSUFFICIENT_CREDIT, "why": reason[:200]}
    return {"status": UNKNOWN, "why": f"the last real call failed for another reason: "
                                      f"{reason[:150]}"}


def _previous(db, provider: str, n: int = 10) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == ACTION,
                                                     AuditLog.artifact == provider)
                              .order_by(desc(AuditLog.id)).limit(n)))
        return [dict(r.detail or {}) for r in rows]


def _venice_one_reply_usd() -> float:
    """A generous single Private Laura reply on the pinned Venice model, in USD (unpadded):
    6,000 input tokens and the 400-token output cap. Credit below this cannot pay a reply."""
    from . import venice

    pin, pout = venice.PRICES_USD_PER_MTOK[venice.MODEL]
    return round(6000 / 1e6 * pin + 400 / 1e6 * pout, 6)


def check_venice(env, http=None) -> dict:
    http = http or _http
    key = _key("venice", env)
    if not key:
        return {"status": MISSING, "why": f"{PROVIDERS['venice']['var']} is not set"}
    status, text = http("GET", VENICE_RATE_LIMITS_URL,
                        {"Authorization": f"Bearer {key}", "accept": "application/json"},
                        None, 20.0)
    cls = classify(status, text)
    if status == 403:
        cls = PERMISSION      # documented: key IP-restricted, or API access disabled
    out = {"status": cls, "http_status": status, "why": _redact(text, key)[:300]}
    if cls != OK:
        return out
    try:
        data = json.loads(text).get("data") or {}
        bal = data.get("balances") or {}
        usd = float(bal.get("USD") or 0.0)
        diem = float(bal.get("DIEM") or 0.0)
        bundled = float(bal.get("BUNDLED_CREDITS") or 0.0)
        permitted = data.get("accessPermitted")
    except (ValueError, TypeError, AttributeError):
        return {**out, "status": UNKNOWN, "why": "authenticated, but the balance was "
                                                 "unreadable"}
    need = _venice_one_reply_usd()
    total = round(usd + diem + bundled, 6)
    out.update(balance_usd=round(usd, 4), balance_diem=round(diem, 4),
               balance_bundled_usd=round(bundled, 4), one_reply_usd=need,
               access_permitted=permitted,
               why=f"authenticated; balance about US${total:.2f} (USD {usd:g}, DIEM {diem:g}, "
                   f"bundled {bundled:g}); one reply is at most about US${need:.4f}")
    out["models"] = _venice_models(http)
    if permitted is False:
        out.update(status=PERMISSION, why="authenticated, but Venice reports API access is "
                                          "not permitted for this key (accessPermitted=false)")
    elif total < need:
        out.update(status=INSUFFICIENT_CREDIT,
                   why=f"authenticated, but the balance (about US${total:.4f}) is less than "
                       f"one Private Laura reply (about US${need:.4f})")
    return out


def _venice_models(http) -> dict:
    """Venice's live metadata for each pinned Private Laura model ({privacy, offline, present}),
    from the public GET /models (no Authorization header). {} if it could not be read."""
    from . import venice

    status, text = http("GET", VENICE_MODELS_URL, {"accept": "application/json"}, None, 20.0)
    if status != 200:
        return {UNREADABLE: True}
    try:
        rows = {m.get("id"): m for m in (json.loads(text).get("data") or [])}
    except (ValueError, TypeError, AttributeError):
        return {UNREADABLE: True}
    out = {}
    for mid in venice.VERIFIED_MODELS:
        m = rows.get(mid)
        spec = (m or {}).get("model_spec") or {}
        out[mid] = {"present": m is not None, "privacy": spec.get("privacy"),
                    "offline": bool(spec.get("offline")), "owned_by": (m or {}).get("owned_by")}
    return out


UNREADABLE = "__unreadable__"


def venice_model_reading(db, model: str) -> dict | None:
    """The live reading that decides `model`'s eligibility (security review M-1).

    * None: no credential check has ever tried to read the model list (the pinned verified row
      decides, as designed until the owner-enabled check runs).
    * The NEWEST successfully parsed reading among recent checks. A later check that could not
      read the list does not clear it, so a contradicting reading stays sticky until a later
      successful reading replaces it.
    * {"unreadable": True}: checks tried, and none in the recent window could be read. The
      pinned row is then NOT used as a silent substitute; `venice.eligible` fails closed."""
    tried = False
    for rec in _previous(db, "venice", 50):
        models = rec.get("models")
        if not isinstance(models, dict):
            continue
        tried = True
        if models.get(UNREADABLE) or not models:
            continue
        return models.get(model) or {"present": False, "privacy": None, "offline": False}
    return {"unreadable": True} if tried else None


def _venice_selected(env) -> bool:
    from . import venice

    return venice.selected(env) == venice.PROVIDER_VALUE


def check_all(db, *, env=None, http=None, trigger: str = "cadence") -> list[dict]:
    """Check every provider, record one audit row each, and return the records.

    The stored record holds no key and no fingerprint: the status, the evidence, the
    consecutive-failure count and a 4-hex rotation marker (`_rotation_marker`)."""
    from ..core.models import AuditLog

    e = env if env is not None else os.environ
    out = []
    for provider in PROVIDERS:
        if provider == "venice" and not _venice_selected(e):
            continue          # owner-enabled only (billing of the check is UNKNOWN)
        key = _key(provider, e)
        try:
            got = (check_bfl(e, http) if provider == "bfl" else
                   check_venice(e, http) if provider == "venice" else
                   check_anthropic(e, http, db=db))
        except Exception as exc:  # noqa: BLE001 - a check that broke is UNKNOWN, not OK
            got = {"status": UNKNOWN, "why": _redact(f"{type(exc).__name__}: {exc}", key)[:300]}
        prev = _previous(db, provider, 1)
        prev_status = prev[0].get("status") if prev else None
        consecutive = (int(prev[0].get("consecutive_failures") or 0) + 1
                       if prev and got["status"] != OK and prev_status != OK else
                       (1 if got["status"] != OK else 0))
        record = {"provider": provider, "at": _now().isoformat(), "trigger": trigger,
                  "var": PROVIDERS[provider]["var"], "check": PROVIDERS[provider]["check"],
                  "doc": PROVIDERS[provider]["doc"],
                  "estimate_cad": (None if provider == "venice" else 0.0),
                  **({"estimate_basis": VENICE_CHECK_COST_BASIS} if provider == "venice"
                     else {}),
                  "previous_status": prev_status, "consecutive_failures": consecutive,
                  "rotation_marker": _rotation_marker(key),
                  **{k: v for k, v in got.items()}}
        record = json.loads(_redact(json.dumps(record, default=str), key)) if key else record
        with db.session() as s:
            s.add(AuditLog(actor="orchestrator", action=ACTION, artifact=provider,
                           detail=record))
        out.append(record)
    return out


def _rotation_marker(key: str) -> str | None:
    """A short marker that changes when the key changes, so a rotation shows in the history
    without storing anything derived from the key that could be used against it: 4 hex of a
    sha256 cannot be reversed or searched usefully. The owner view adds the fuller
    fingerprint, computed live from the environment and never stored. Domain-separated, so
    it shares no characters by construction with the owner-view fingerprint."""
    return hashlib.sha256(b"brambleloop-rotation-marker:" + key.encode()).hexdigest()[:4] \
        if key else None


def state(db, *, owner: bool = False, env=None) -> list[dict]:
    """The latest reading per provider. `owner=True` (the owner-authenticated view only) adds
    the live key fingerprint so a rotation can be confirmed."""
    e = env if env is not None else os.environ
    out = []
    for provider, meta in PROVIDERS.items():
        prev = _previous(db, provider, 1)
        row = {"provider": provider, "label": meta["label"], "var": meta["var"],
               "check": meta["check"], "doc": meta["doc"],
               "latest": prev[0] if prev else None,
               "status": (prev[0].get("status") if prev else UNKNOWN),
               "owner_action": owner_action(provider, prev[0].get("status") if prev else None)}
        if owner:
            row["fingerprint"] = fingerprint(_key(provider, e))
        out.append(row)
    return out


def owner_action(provider: str, status: str | None) -> str:
    meta = PROVIDERS[provider]
    var, console = meta["var"], meta["console"]
    if status == MISSING:
        return (f"Set {var} in Railway → the service → Variables (create the key at "
                f"{console}). The service restarts; then tap 'Check now'.")
    if status == REJECTED:
        return (f"The key was refused. Create a new key at {console}, then rotate it in "
                f"Railway → Variables → {var}. Tap 'Check now', confirm the new fingerprint "
                f"shows OK, then delete the old key at the provider.")
    if status == INSUFFICIENT_CREDIT:
        return f"Add credit at {console}. Nothing in Railway changes; tap 'Check now' after."
    if status == PERMISSION:
        return (f"The key authenticates but the model or feature is not enabled for it "
                f"({meta['model']}). Enable it at {console}, or use a key from an account "
                f"that has it, set in Railway → Variables → {var}.")
    if status in TRANSIENT_STATUSES:
        return "Nothing to do yet: the provider is unavailable; the check repeats."
    return ""


def notification_candidates(db) -> list[dict]:
    """One deduplicated owner card per provider state that needs the owner, one on recovery,
    and nothing for a transient failure until it has repeated ALERT_AFTER_CONSECUTIVE
    times."""
    out = []
    for provider, meta in PROVIDERS.items():
        rows = _previous(db, provider, ALERT_AFTER_CONSECUTIVE + 1)
        if not rows:
            continue
        latest = rows[0]
        st = latest.get("status")
        marker = latest.get("rotation_marker") or "none"
        if st in OWNER_STATUSES:
            out.append({"dedupe_key": f"credential:{provider}:{st}:{marker}",
                        "severity": "high", "category": "decision",
                        "title": f"{meta['label']}: {st.replace('_', ' ').lower()}"[:300],
                        "body": (f"{latest.get('why') or ''}. {owner_action(provider, st)}"
                                 )[:1000],
                        "consequence": ("image generation is unavailable" if provider == "bfl"
                                        else "Private Laura cannot reply (Venice)"
                                        if provider == "venice"
                                        else "vision checks read UNKNOWN"),
                        "evidence": [f"audit_log:{ACTION}:{provider}"],
                        "deep_link": "/cc/#/credentials", "count": 1})
        elif st in TRANSIENT_STATUSES and int(latest.get("consecutive_failures") or 0) >= \
                ALERT_AFTER_CONSECUTIVE:
            out.append({"dedupe_key": f"credential:{provider}:{st}:streak",
                        "severity": "normal", "category": "anomaly",
                        "title": f"{meta['label']}: {st.replace('_', ' ').lower()} "
                                 f"({latest.get('consecutive_failures')} checks in a row)"[:300],
                        "body": str(latest.get("why") or "")[:1000],
                        "consequence": "paid calls to this provider fail until it recovers",
                        "evidence": [f"audit_log:{ACTION}:{provider}"],
                        "deep_link": "/cc/#/credentials", "count": 1})
        elif st == OK and latest.get("previous_status") not in (None, OK):
            out.append({"dedupe_key": f"credential:{provider}:recovered:{latest.get('at')}",
                        "severity": "normal", "category": "info",
                        "title": f"{meta['label']}: credentials healthy again"[:300],
                        "body": f"was {latest.get('previous_status')}; now OK. "
                                f"{latest.get('why') or ''}"[:1000],
                        "consequence": "nothing to do",
                        "evidence": [f"audit_log:{ACTION}:{provider}"],
                        "deep_link": "/cc/#/credentials", "count": 1})
    return out
