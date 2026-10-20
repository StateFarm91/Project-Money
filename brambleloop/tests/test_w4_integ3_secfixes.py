"""W4-INTEG3: the independent security review of 5f18d11 -- M1, L1, L2 and L3, each proven.

  M1  the public webhook's database work runs in the threadpool, never on the event loop, and
      one refusal is ONE transaction (counter upsert + sample claim + sampled audit row)
  L1  the refusal counter is BIGINT: it counts past 2^31 - 1 instead of freezing
  L2  reference.run's persisted `failed[].why` carries the refusal class, never model text
  L3  the "current release deployed" prerequisite is enforced: enablement and the reply path
      refuse on an unproven release, not only display it

Local, deterministic; sockets refused by the REL2 harness; no provider is called.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_integ3_secfixes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import json
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_rel2 as R  # noqa: E402  (its temp DB, socket guard and reference fixtures)

from sqlalchemy import BigInteger, func, select  # noqa: E402


# ------------------------------------------------------------------------------- M1

def test_m1_the_webhook_route_runs_its_database_work_in_the_threadpool():
    tree = ast.parse((ROOT / "src/brambleloop/app/main.py").read_text())
    route = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                 and n.name == "api_etsy_webhook")
    awaited = [n.value for n in ast.walk(route) if isinstance(n, ast.Await)]
    pooled = {a.args[0].attr for a in awaited if isinstance(a, ast.Call)
              and getattr(a.func, "id", "") == "run_in_threadpool"
              and isinstance(a.args[0], ast.Attribute)}
    assert pooled == {"refuse", "receive"}, pooled
    # No direct (event-loop) call of either remains in the route.
    direct = [n for n in ast.walk(route) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr in ("refuse", "receive")]
    assert not direct, "refuse/receive called on the event loop"


def test_m1_one_refusal_is_one_transaction_and_counts_exactly_under_concurrency():
    from brambleloop.integrations import etsy_webhooks as W

    db = R._db()
    W.ensure_table(db)
    opened = [0]
    real = db.session

    def counting():
        opened[0] += 1
        return real()

    db.session = counting
    try:
        W._refused(db, W.WebhookRefused("bad_signature", "x", status=401))
        assert opened[0] == 1, f"{opened[0]} transactions for one first refusal"
        opened[0] = 0
        W._refused(db, W.WebhookRefused("bad_signature", "x", status=401))
        assert opened[0] == 1, f"{opened[0]} transactions for a repeat refusal"
    finally:
        db.session = real
    errors: list = []

    def flood():
        try:
            for _ in range(15):
                W._refused(db, W.WebhookRefused("stale", "x", status=400))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=flood) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    refused = W.summary(db)["refused"]
    assert refused == {"bad_signature": 2, "stale": 90}, refused
    from brambleloop.core.models import AuditLog
    with db.session() as s:
        sampled = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == W.REFUSAL_SAMPLE_ACTION))
    assert sampled == 2, "one sampled audit row per reason per window"


# ------------------------------------------------------------------------------- L1

def test_l1_the_refusal_counter_is_bigint_and_counts_past_int4():
    from brambleloop.integrations import etsy_webhooks as W

    cols = W.EtsyWebhookRefusal.__table__.c
    assert isinstance(cols["count"].type, BigInteger)
    assert isinstance(cols["last_audit_epoch"].type, BigInteger)
    db = R._db()
    W._refused(db, W.WebhookRefused("too_large", "x", status=413))
    with db.session() as s:
        s.get(W.EtsyWebhookRefusal, "too_large").count = 2 ** 31 - 1
    W._refused(db, W.WebhookRefused("too_large", "x", status=413))
    assert W.summary(db)["refused"]["too_large"] == 2 ** 31


# ------------------------------------------------------------------------------- L2

def test_l2_a_refused_readings_text_never_reaches_the_persisted_job_result():
    from brambleloop.creative import reference

    db = R._reference_db()
    seer = R._Seer(lambda url: '{"neckline": "a gnome face applique"}' if url.endswith("toys0")
                   else 'not json: SECRET-MODEL-PROSE' if url.endswith("toys1")
                   else R.CLEAN)
    out = reference.run(db, provider=seer, today=date(2026, 10, 20))
    failed = {f["listing_ref"]: f for f in out["failed"]}
    assert set(failed) >= {"toys0", "toys1"}, out["failed"]
    assert failed["toys0"]["why"] == "ReferenceRefused: depiction", failed
    assert failed["toys1"]["why"].startswith("ReferenceRefused: "), failed
    text = json.dumps(out)
    assert "gnome" not in text and "SECRET-MODEL-PROSE" not in text, text


def test_l2_any_other_failure_keeps_only_its_exception_class():
    from brambleloop.creative import reference

    def boom(*a, **k):
        raise RuntimeError("provider said: SECRET-ECHO of the answer")

    db = R._reference_db()
    real = reference.read_listing
    reference.read_listing = boom
    try:
        out = reference.run(db, provider=object(), today=date(2026, 10, 20))
    finally:
        reference.read_listing = real
    assert out["failed"], out
    assert all(f["why"] == "RuntimeError" for f in out["failed"]), out["failed"]
    assert "SECRET-ECHO" not in json.dumps(out)


# ------------------------------------------------------------------------------- L3

def test_l3_an_unproven_release_gets_no_reply_and_no_spend():
    import w4_pl_harness as PL
    from w3_laura_memory_harness import fresh_db

    from brambleloop.agents.registry import Registry
    from brambleloop.app.command_center import private_context
    from brambleloop.core.models import CostEntry, SpendReservation
    from brambleloop.gateway import laura_register as LR

    db = fresh_db()
    Registry(db).seed_defaults()
    stub = PL.Stub()
    with PL.enabled(stub, release_proven=False):
        try:
            LR.reply(db, system=LR.PROMPT.system, user="hello")
            raise AssertionError("a reply was generated on an unproven release")
        except LR.ReplyUnavailable as exc:
            assert exc.code == "RELEASE_UNPROVEN", exc.code
        en = private_context._enablement(db)
        assert en["current_release_deployed"] is False and en["enabled"] is False, en
    assert stub.calls == [], "the provider was called"
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(CostEntry)) == 0
        assert s.scalar(select(func.count()).select_from(SpendReservation)) == 0
    # Every other prerequisite unchanged: the same call on a proven release replies.
    with PL.enabled(PL.Stub(), release_proven=True):
        en = private_context._enablement(db)
        assert en["current_release_deployed"] is True, en
        assert en["enabled"] is (en["key_configured"] and en["laura_private_agent"]), en
        assert LR.reply(db, system=LR.PROMPT.system, user="hello")["text"] == PL.REPLY


def test_l3_the_real_check_is_unmet_in_a_process_the_boot_guard_did_not_prove():
    from brambleloop.gateway import laura_register as LR

    sha = "1b21e81c6d1b228a93f72be44cfdf8193740b61b"
    assert LR.release_proven({}, {"ok": True, "platform_markers": ["X"]})["met"] is False
    assert LR.release_proven({"RAILWAY_GIT_COMMIT_SHA": sha}, {"ok": False,
                                                               "platform_markers": ["X"]}
                             )["met"] is False
    assert LR.release_proven({"RAILWAY_GIT_COMMIT_SHA": sha}, {"ok": True})["met"] is False
    ok = LR.release_proven({"RAILWAY_GIT_COMMIT_SHA": sha},
                           {"ok": True, "platform_markers": ["RAILWAY_GIT_COMMIT_SHA"],
                            "record": {"file": "RELEASE_x.json"}})
    assert ok["met"] is True and ok["commit_short"] == sha[:12]


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 7, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
