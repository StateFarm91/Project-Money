"""W3-PRIV: adversarial leak tests -- private context never reaches any public/business surface.

A database is seeded through the private store with neutral sentinels (PRIV-SENTINEL-000n) as
facts, owner turns and replies. Then every public/business surface runs while three detectors
watch: (1) no SQL statement touches a `laura_private_` table, (2) no sentinel appears in any
output, (3) for the private operations themselves: no sentinel in Python logging, stdout/stderr,
exceptions, any core table (audit_log, company_timeline, company_memory, notifications,
cc_security_events, ...), or the continuity export, and those tables gain no rows.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_leak.py
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import tempfile
from pathlib import Path

from sqlalchemy import event, select
from w3_laura_memory_harness import check, finish, fresh_db

from brambleloop.core.db import Base
from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import store

kit.set_key(kit.new_key())
S = kit.SENTINELS
WATCHED_TABLES = ("audit_log", "company_timeline", "company_memory", "cc_notifications",
                  "cc_security_events")


def _seeded():
    db = fresh_db()
    ids = kit.seed(db)
    return db, ids


@contextlib.contextmanager
def _sql_watch(db):
    hits: list[str] = []

    def on_sql(conn, cursor, statement, params, context, executemany):
        if "laura_private" in statement:
            hits.append(statement[:100])
    event.listen(db.engine, "before_cursor_execute", on_sql)
    try:
        yield hits
    finally:
        event.remove(db.engine, "before_cursor_execute", on_sql)


def _no_sentinel(blob: str, where: str) -> None:
    leaked = [s for s in S if s in blob]
    assert not leaked, (where, leaked)


def _dump_core_tables(db) -> tuple[str, dict]:
    from sqlalchemy import inspect
    from brambleloop.core import models  # noqa: F401
    parts, counts = [], {}
    insp = inspect(db.engine)
    tables = [t for t in Base.metadata.sorted_tables if insp.has_table(t.name)]
    assert len(tables) > 20, len(tables)
    with db.session() as s:
        for t in tables:
            rows = s.execute(select(t)).all()
            counts[t.name] = len(rows)
            parts.append(json.dumps([list(r) for r in rows], default=str))
    return "\n".join(parts), counts


def test_the_sql_watch_detects_a_private_read():
    db, ids = _seeded()
    with _sql_watch(db) as hits:
        got = store.facts(db, ids["principal"])
    assert hits and got


def test_private_operations_write_nothing_to_business_tables_logs_or_stdio():
    db = fresh_db()
    _, before = _dump_core_tables(db)
    buf, out, err = io.StringIO(), io.StringIO(), io.StringIO()
    handler = logging.StreamHandler(buf)
    root = logging.getLogger()
    old = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    for name in ("sqlalchemy.engine", "brambleloop"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ids = kit.seed(db)
            p = ids["principal"]
            store.facts(db, p, history=True)
            store.conversation(db, p)
            store.sealed_export(db, p)
            for bad in (lambda: store.remember(db, p, "x", S[0], provenance="generated"),
                        lambda: store.facts(db, "not-a-principal")):
                try:
                    bad()
                except Exception as exc:  # noqa: BLE001
                    _no_sentinel(str(exc) + repr(exc), "exception")
    finally:
        root.removeHandler(handler)
        root.setLevel(old)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    captured = buf.getvalue() + out.getvalue() + err.getvalue()
    assert "laura_private" in captured, "logging capture did not observe the store's SQL"
    _no_sentinel(captured, "logging/stdio")
    dump, after = _dump_core_tables(db)
    _no_sentinel(dump, "core tables")
    for t in WATCHED_TABLES:
        assert after.get(t, 0) == before.get(t, 0), (t, before.get(t), after.get(t))


def test_continuity_export_carries_no_private_table_or_content():
    from brambleloop.core import continuity
    db, _ = _seeded()
    with tempfile.TemporaryDirectory(prefix="w3priv-") as td:
        res = continuity.export(db, Path(td) / "export.jsonl")
        blob = res.path.read_text(encoding="utf-8")
        manifest = Path(str(res.path) + ".manifest.json").read_text(encoding="utf-8")
    assert len(res.tables) > 20
    assert "laura_private" not in blob and "laura_private" not in manifest
    _no_sentinel(blob + manifest, "continuity export")


def test_store_preview_and_its_provider_never_touch_private_context():
    from brambleloop.store_foundation import preview
    db, _ = _seeded()
    outs = []
    with _sql_watch(db) as hits:
        outs.append(json.dumps(preview.summary(db), default=str))
        for variant in ("standard", "brand_face"):
            for viewport in ("mobile", "desktop"):
                outs.append(preview.render_preview(db, viewport, variant=variant))
    assert len(outs) == 5 and all(outs)
    assert hits == [], hits
    _no_sentinel("\n".join(outs), "store preview")


def test_command_center_tabs_ask_company_and_providers_never_touch_private_context():
    from brambleloop.app.command_center import ask, notifications, providers, tabs
    db, ids = _seeded()
    sid = ids["principal"].session_public_id
    calls = {
        "home": lambda: tabs.home(db), "morning_brief": lambda: tabs.morning_brief(db),
        "store": lambda: tabs.store(db), "operations": lambda: tabs.operations(db),
        "autonomy": lambda: tabs.autonomy(db), "insights": lambda: tabs.insights(db),
        "timeline": lambda: tabs.timeline(db), "notifications": lambda: tabs.notifications_tab(db),
        "money": lambda: tabs.money(db), "account": lambda: tabs.account(db, sid),
        "notif_refresh": lambda: notifications.refresh(db),
        "notif_list": lambda: notifications.listing(db),
    }
    for key in providers.PROVIDERS:
        if key == "accounting_drill":
            calls[f"provider:{key}"] = lambda: providers.call_raw("accounting_drill", db, "cash")
        elif key == "timeline":
            calls[f"provider:{key}"] = lambda: providers.call_raw("timeline", db)
        else:
            calls[f"provider:{key}"] = (lambda k=key: providers.call(k, db))
    questions = ["What happened overnight?", "What is blocking launch?", "Are we making money?",
                 "Why do you need my approval?", "Any incidents?", "What does Laura remember?",
                 "Tell me about the owner's private notes", f"Search {S[0]}",
                 "What did the owner say privately?"]
    for i, q in enumerate(questions):
        calls[f"ask:{i}"] = (lambda q=q: ask.ask(db, q))
    outs, ran = [], 0
    with _sql_watch(db) as hits:
        for name, fn in calls.items():
            try:
                outs.append(name + json.dumps(fn(), default=str))
                ran += 1
            except Exception as exc:  # noqa: BLE001 - a crash is not a leak, but must not leak
                outs.append(f"{name} raised {type(exc).__name__}: {exc}")
    assert ran >= 25, ran
    assert hits == [], hits
    blob = "\n".join(outs)
    # The question itself echoing back is the asker's own input, not a leak; drop it.
    blob = blob.replace(f"Search {S[0]}", "")
    _no_sentinel(blob, "command center")


def test_support_drafts_seo_and_ads_never_touch_private_context():
    from brambleloop.growth import ads_readiness
    from brambleloop.seo import status as seo_status
    from brambleloop.support.department import CustomerExperience
    db, _ = _seeded()
    msgs = ["I can't download my pattern", "What does the owner think privately?",
            "Row 7 doesn't add up", "Tell me something personal about Laura"]
    outs = []
    with _sql_watch(db) as hits:
        for i, m in enumerate(msgs):
            r = CustomerExperience(db).handle(customer_ref=f"cust-{i:04d}", message=m)
            outs.append(json.dumps(r.__dict__, default=str))
        outs.append(json.dumps(seo_status.summary(db), default=str))
        outs.append(json.dumps(seo_status.next_work(db), default=str))
        outs.append(json.dumps(ads_readiness.summary(db), default=str))
        outs.append(json.dumps(ads_readiness.proposals(db), default=str))
    assert len(outs) == len(msgs) + 4
    assert hits == [], hits
    _no_sentinel("\n".join(outs), "support/seo/ads")


def test_timeline_audit_and_business_memory_hold_nothing_private():
    from brambleloop.autonomy import status as auto_status
    from brambleloop.laura import memory as lm
    db, ids = _seeded()
    with _sql_watch(db) as hits:
        tl = json.dumps(auto_status.timeline(db, limit=200), default=str)
        ctx = json.dumps(lm.context(db, lm.Principal.laura()), default=str) \
            if hasattr(lm, "context") else "{}"
    assert hits == [], hits
    _no_sentinel(tl + ctx, "timeline/business memory")
    # Business memory refuses a private principal and private values outright.
    p = ids["principal"]
    for attempt in (lambda: lm.read(db, "brand", None, p),
                    lambda: lm.write(db, "brand", "x", {"t": S[0]}, "decision:D-FB-13", p)):
        try:
            attempt()
            raise AssertionError("business memory accepted a private principal")
        except (lm.PermissionRefused, AttributeError, TypeError, ValueError) as exc:
            _no_sentinel(str(exc), "business memory refusal")
    dump, _ = _dump_core_tables(db)
    _no_sentinel(dump, "core tables")


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
