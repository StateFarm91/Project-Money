"""W3-E: public/customer surfaces never read Laura's non-public memory tiers.

Every tier is seeded with a unique canary. Then the real public/customer surfaces run --
the Owner Store Preview (both variants, both viewports) and its provider, Ask Company
(answering without an owner principal), and Customer Support drafts -- while three
independent detectors watch:

  1. the memory API (`read`/`context`/`history`) is never called;
  2. no SQL statement touches Laura's rows (`laura:` keys or `laura.mem` kinds);
  3. no canary appears in anything the surface produced.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_memory_isolation.py
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from sqlalchemy import event
from w3_laura_memory_harness import check, finish, fresh_db, owner_session

from brambleloop.laura import memory as lm
from brambleloop.laura.memory import store as lm_store

CANARIES = {t: f"CANARY-{t.upper()}-7f3a" for t in lm.TIERS}


def _seeded():
    db = fresh_db()
    owner = lm.Principal.owner(owner_session(db))
    for tier, canary in CANARIES.items():
        key = "context/canary" if tier == "relationship" else "canary"
        lm.write(db, tier, key, {"text": canary}, "decision:D-FB-13", owner, subject=canary)
    return db


@contextmanager
def _watch(db):
    calls: list[str] = []
    sql: list[str] = []
    originals = {n: getattr(lm_store, n) for n in ("read", "context", "history")}

    def wrap(name):
        def inner(*a, **kw):
            calls.append(name)
            return originals[name](*a, **kw)
        return inner

    def on_sql(conn, cursor, statement, params, context, executemany):
        blob = statement + " " + json.dumps(params, default=str)
        if "laura:" in blob or "laura.mem" in blob:
            sql.append(statement[:120])

    for n in originals:
        setattr(lm_store, n, wrap(n))
        setattr(lm, n, getattr(lm_store, n))
    event.listen(db.engine, "before_cursor_execute", on_sql)
    try:
        yield calls, sql
    finally:
        event.remove(db.engine, "before_cursor_execute", on_sql)
        for n, f in originals.items():
            setattr(lm_store, n, f)
            setattr(lm, n, f)


def _no_canary(text: str) -> None:
    assert text, "the surface produced nothing to inspect"
    leaked = [c for c in CANARIES.values() if c in text]
    assert not leaked, leaked


def test_the_watch_itself_detects_a_memory_read():
    db = _seeded()
    with _watch(db) as (calls, sql):
        got = lm.read(db, "brand", None, lm.Principal.laura())
    assert calls == ["read"] and sql, (calls, sql)
    assert CANARIES["brand"] in json.dumps(got)


def test_store_preview_never_reads_laura_memory():
    from brambleloop.store_foundation import preview

    db = _seeded()
    outputs = []
    with _watch(db) as (calls, sql):
        outputs.append(json.dumps(preview.summary(db), default=str))
        for variant in ("standard", "brand_face"):
            for viewport in ("mobile", "desktop"):
                outputs.append(preview.render_preview(db, viewport, variant=variant))
    assert len(outputs) == 5
    assert calls == [] and sql == [], (calls, sql)
    for out in outputs:
        _no_canary(out)


def test_ask_company_without_an_owner_principal_never_reads_laura_memory():
    from brambleloop.app.command_center import ask

    db = _seeded()
    questions = ["What happened overnight?", "Why is the coaster pattern blocked?",
                 "What is blocking launch?", "Are we making money?",
                 "Why do you need my approval?", "Any incidents?",
                 "What is Laura's visual identity id?", "Tell me about the brand palette"]
    with _watch(db) as (calls, sql):
        answers = [json.dumps(ask.ask(db, q), default=str) for q in questions]
    assert len(answers) == len(questions)
    assert calls == [] and sql == [], (calls, sql)
    for a in answers:
        _no_canary(a)
    assert lm.principal_for_surface("ask_company_non_owner").kind == "public"


def test_support_drafts_never_read_laura_memory():
    from brambleloop.support.department import CustomerExperience

    db = _seeded()
    messages = ["I can't download my pattern", "I love it, thank you!",
                "Which version of the pattern do I have?",
                "Row 7 doesn't add up, the count is wrong",
                "I want a refund and I am contacting my bank"]
    with _watch(db) as (calls, sql):
        drafts = []
        for i, m in enumerate(messages):
            r = CustomerExperience(db).handle(customer_ref=f"cust-{i:04d}", message=m)
            drafts.append(json.dumps(r.__dict__, default=str))
    assert len(drafts) == len(messages)
    assert calls == [] and sql == [], (calls, sql)
    for d in drafts:
        _no_canary(d)
    assert lm.principal_for_surface("support_draft").kind == "customer"


def test_even_if_a_surface_tried_its_principal_gets_nothing():
    db = _seeded()
    surfaces = ["store_preview", "ask_company_non_owner", "support_draft", "etsy_message",
                "listing", "public_api"]
    refused = 0
    for name in surfaces:
        p = lm.principal_for_surface(name)
        for tier in lm.TIERS:
            try:
                lm.read(db, tier, None, p)
            except lm.PermissionRefused:
                refused += 1
    assert refused == len(surfaces) * len(lm.TIERS)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
