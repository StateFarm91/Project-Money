"""CC provider contract (CC_VERIFY_7421ef6 FU-1): a provider that needs the `Database` facade but
is first handed a bare Session is retried with the facade -- whether it raises or reports the
mismatch as an UNKNOWN reason, and whichever attribute it missed ('session', 'engine', ...).
Anything else stays the provider's own UNKNOWN (fail-safe preserved). Pure Python, no database.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.app.command_center import providers  # noqa: E402

passes = 0
failures = 0


def check(cond: bool, name: str, why: str = "") -> None:
    global passes, failures
    if cond:
        passes += 1
        print(f"OK {name}")
    else:
        failures += 1
        print(f"FAIL {name}: {why}")


class Session:  # the name matters: the reason text says "'Session' object ..."
    def rollback(self):
        pass

    def close(self):
        pass


class Facade:
    engine = "engine"
    session = "session"

    def new_session(self):
        return Session()


def _reporting(attr):
    """Like growth.ads_readiness.summary: catches its own error and reports UNKNOWN."""
    def fn(db):
        try:
            getattr(db, attr)
        except AttributeError as e:
            return {"status": "UNKNOWN", "items": [], "reason": f"unreadable: {e!r}"}
        return {"status": "OK", "items": [{"via": type(db).__name__}], "as_of": "t"}
    return fn


def _raising(attr):
    def fn(db):
        getattr(db, attr)
        return {"status": "OK", "items": [{"via": type(db).__name__}], "as_of": "t"}
    return fn


def test_reported_engine_mismatch_is_retried_with_the_facade() -> None:
    out = providers._invoke(_reporting("engine"), Facade())
    check(out.get("status") == "OK" and out["items"] == [{"via": "Facade"}],
          "reported \"'Session' object has no attribute 'engine'\" -> retried with the facade", str(out))


def test_reported_session_mismatch_still_retried() -> None:
    out = providers._invoke(_reporting("session"), Facade())
    check(out.get("status") == "OK", "reported 'session' mismatch -> retried (unchanged)", str(out))


def test_raised_engine_mismatch_is_retried_with_the_facade() -> None:
    out = providers._invoke(_raising("engine"), Facade())
    check(out.get("status") == "OK" and out["items"] == [{"via": "Facade"}],
          "raised \"'Session' object has no attribute 'engine'\" -> retried with the facade", str(out))


def test_other_unknown_is_not_retried() -> None:
    calls = []

    def fn(db):
        calls.append(type(db).__name__)
        return {"status": "UNKNOWN", "items": [], "reason": "no evidence yet"}
    out = providers._invoke(fn, Facade())
    check(out.get("status") == "UNKNOWN" and calls == ["Session"],
          "an ordinary UNKNOWN stays UNKNOWN and is not retried (fail-safe)", f"{out} {calls}")


def test_other_attribute_error_still_raises() -> None:
    def fn(db):
        raise AttributeError("'NoneType' object has no attribute 'x'")
    try:
        providers._invoke(fn, Facade())
        raised = False
    except AttributeError:
        raised = True
    check(raised, "an unrelated AttributeError is not swallowed by the retry (call() turns it UNKNOWN)")


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            f()
    print(f"\n{passes} passed, {failures} failed")
    sys.exit(1 if failures or not passes else 0)
