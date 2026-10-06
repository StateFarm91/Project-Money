"""Reading departments through the cross-lane provider contract, tolerating absence.

Each department lane exposes `summary(db) -> dict` with `status`, `as_of`, `basis`, `items`,
`sources`. The command center never trusts one blindly:

* an ImportError (lane not built / not merged) -> UNKNOWN, reason "not built";
* an exception -> UNKNOWN, reason names the exception type (never its secret-bearing text);
* a malformed return (no recognised status) -> UNKNOWN, "provider returned a malformed summary".

The contract says `db` is a SQLAlchemy Session; this repository's own readers take the
`Database` facade. `call` hands the provider a Session, and if the provider instead needs the
facade (AttributeError on `.session`), retries once with it.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone

STATUSES = ("OK", "DEGRADED", "BLOCKED", "UNKNOWN")
BASES = ("measured", "estimated", "modelled", "unknown")

PROVIDERS: dict[str, tuple[str, str]] = {
    "autonomy": ("brambleloop.autonomy.status", "summary"),
    "timeline": ("brambleloop.autonomy.status", "timeline"),
    "improvement": ("brambleloop.learn.improvement_status", "summary"),
    "accounting": ("brambleloop.finance.accounting.dashboard", "summary"),
    "accounting_drill": ("brambleloop.finance.accounting.dashboard", "drill"),
    "store_foundation": ("brambleloop.store_foundation.preview", "summary"),
    "seo": ("brambleloop.seo.status", "summary"),
    "ads": ("brambleloop.growth.ads_readiness", "summary"),
    "slo": ("brambleloop.ops.slo", "summary"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def unknown(reason: str, provider: str = "", sources: list | None = None) -> dict:
    return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
            "sources": list(sources or []), "reason": reason, "provider": provider}


def envelope(status: str, items: list, sources: list, *, basis: str = "measured",
             reason: str | None = None, provider: str = "", as_of: str | None = None,
             **extra) -> dict:
    out = {"status": status if status in STATUSES else "UNKNOWN",
           "as_of": as_of or now_iso(), "basis": basis if basis in BASES else "unknown",
           "items": items, "sources": sources, "provider": provider}
    if reason:
        out["reason"] = reason
    out.update(extra)
    return out


def _resolve(key: str):
    mod_name, fn_name = PROVIDERS[key]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError:
        return None, f"{mod_name}.{fn_name}", "not built"
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        return None, f"{mod_name}.{fn_name}", "not built"
    return fn, f"{mod_name}.{fn_name}", None


def available(key: str) -> bool:
    return _resolve(key)[0] is not None


def _invoke(fn, db, *args, **kwargs):
    session = db.new_session()
    try:
        try:
            out = fn(session, *args, **kwargs)
        except AttributeError as exc:
            if "session" not in str(exc):
                raise
            session.rollback()
            return fn(db, *args, **kwargs)
        # W3-F: a provider that needs the `Database` facade but catches its own exceptions
        # reports "'Session' object has no attribute 'session'" as an UNKNOWN reason instead
        # of raising. That is the same contract mismatch; retry once with the facade.
        if (isinstance(out, dict) and out.get("status") == "UNKNOWN"
                and "has no attribute 'session'" in str(out.get("reason") or "")):
            session.rollback()
            return fn(db, *args, **kwargs)
        return out
    finally:
        try:
            session.rollback()
        finally:
            session.close()


def validate(out, name: str) -> dict:
    if not isinstance(out, dict) or out.get("status") not in STATUSES:
        return unknown("provider returned a malformed summary", name)
    out = dict(out)
    out.setdefault("as_of", None)
    out["basis"] = out.get("basis") if out.get("basis") in BASES else "unknown"
    out["items"] = out.get("items") if isinstance(out.get("items"), list) else []
    out["sources"] = out.get("sources") if isinstance(out.get("sources"), list) else []
    out["provider"] = name
    if out["status"] != "OK" and not out.get("reason"):
        out["reason"] = "provider gave no reason"
    return out


def call(key: str, db, *args, **kwargs) -> dict:
    fn, name, why = _resolve(key)
    if fn is None:
        return unknown(why, name)
    try:
        return validate(_invoke(fn, db, *args, **kwargs), name)
    except Exception as exc:  # noqa: BLE001 - an unreadable department is UNKNOWN
        return unknown(f"provider failed: {type(exc).__name__}", name)


def call_raw(key: str, db, *args, **kwargs):
    """For providers whose return is not an envelope (timeline lists). (value, why)."""
    fn, name, why = _resolve(key)
    if fn is None:
        return None, why
    try:
        return _invoke(fn, db, *args, **kwargs), None
    except Exception as exc:  # noqa: BLE001
        return None, f"provider failed: {type(exc).__name__}"


def guard(name: str, fn, *, sources: list | None = None) -> dict:
    """Run one of this package's own readers; any failure is UNKNOWN with the reason."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return unknown(f"could not be read: {type(exc).__name__}: {str(exc)[:160]}", name,
                       sources)
