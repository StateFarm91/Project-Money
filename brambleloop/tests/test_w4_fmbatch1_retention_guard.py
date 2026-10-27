"""Retention guard: audit actions read through constants are found, classified, and the guard
fails closed on anything it cannot resolve.

The old guard matched `AuditLog.action == "literal"` with a regex; an action read through a
constant, an imported constant, a dict's keys, a loop tuple or a helper's parameter was
invisible, so retention could prune evidence that is still read (101 such actions here).
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1rg_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/r.db"

from brambleloop.ops import read_actions, retention  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "brambleloop"

FAKE = {
    "consts.py": 'ACTION = "x.const"\nPAIR = ("x.tuple_a", "x.tuple_b")\n',
    "reader.py": '''
from . import consts
from .consts import PAIR
LEGACY = {"x.dict_key": "ignored value"}
PROBES = {"x.loop_key": 3600}
OTHER = "x.param_const"


def _rows(db, action, *, limit=5):
    return select(AuditLog).where(AuditLog.action == action)


def readers(db):
    _rows(db, "x.param_literal")
    _rows(db, OTHER)
    select(AuditLog).where(AuditLog.action == consts.ACTION)
    select(AuditLog).where(AuditLog.action.in_(PAIR))
    select(AuditLog).where(AuditLog.action.in_(tuple(LEGACY)))
    for act, period in PROBES.items():
        select(AuditLog).where(AuditLog.action == act)

    def count(name):
        return select(AuditLog).where(AuditLog.action == name)
    count("x.nested")
    select(AuditLog).where(AuditLog.action.like("x.prefix.%"))


def opaque(db, suffix):
    return select(AuditLog).where(AuditLog.action == f"x.{suffix}")
''',
}
EXPECTED = {"x.const", "x.tuple_a", "x.tuple_b", "x.dict_key", "x.loop_key",
            "x.param_literal", "x.param_const", "x.nested"}


def _fake_tree():
    d = Path(tempfile.mkdtemp(prefix="fmb1rg_src_"))
    for name, text in FAKE.items():
        (d / name).write_text(text)
    return d


def test_constants_imports_dict_keys_loops_params_and_nested_helpers_are_resolved():
    d = _fake_tree()
    s = read_actions.scan(d)
    assert set(s.exact) == EXPECTED, sorted(s.exact)
    assert "ignored value" not in s.exact, "a dict read with tuple()/in_ yields its keys"
    assert list(s.prefixes) == ["x.prefix."]
    assert [u["key"] for u in s.unresolved] == ["reader.py::opaque"], s.unresolved


def test_the_guard_reports_every_unclassified_read_and_fails_closed_on_the_unresolvable():
    out = retention.unknown_read_actions(_fake_tree())
    assert set(out) == EXPECTED | {"prefix:x.prefix.", "unresolved:reader.py::opaque"}, out


def test_every_action_the_real_code_reads_is_classified():
    assert retention.unknown_read_actions() == []
    s = read_actions.scan()
    assert len(s.exact) > 150, len(s.exact)   # the scan is not vacuous
    for a in ("etsy.shop_observation", "store.live_observation", "store.owner_confirmed",
              "commerce.orders_ingested", "routing.evidence", "spend.provider_settlement",
              "visual.hero_review"):
        assert a in s.exact and a in retention.KNOWN_READ_ACTIONS, a
    # A per-artifact newest-row read is protected: keep-per-action is global.
    assert "visual.hero_review" in retention.PROTECTED_ACTIONS


def test_the_unresolved_allowlist_is_current_and_every_sealed_chain_is_protected():
    s = read_actions.scan()
    keys = {u["key"] for u in s.unresolved}
    assert set(retention.UNRESOLVED_READ_SITES) == keys, (keys, retention.UNRESOLVED_READ_SITES)
    r = read_actions._Resolver(read_actions._load(SRC))
    chains = 0
    for mod in r.mods.values():
        for node in ast.walk(mod.tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "GrantLedger":
                for kw in node.keywords:
                    if kw.arg in ("approved", "revoked", "rebased"):
                        vals, _ = r.value(kw.value, mod, None)
                        for v in vals:
                            chains += 1
                            assert v in retention.PROTECTED_ACTIONS, (mod.name, v)
    assert chains >= 9, chains
    for a in ("owner.publication.approved", "owner.activation.approved"):
        assert a in retention.PROTECTED_ACTIONS


def test_a_protected_prefix_survives_the_horizon():
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog

    db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
    db.create_all()
    old = datetime.now(timezone.utc) - timedelta(days=400)
    with db.session() as s:
        for i in range(5):
            s.add(AuditLog(actor="t", action="recovery.requested", artifact=f"r{i}", at=old))
            s.add(AuditLog(actor="t", action="plain.noise", artifact=f"n{i}", at=old))
    plan = retention.audit_plan(db)
    with db.session() as s:
        ids = {r.id: r.action for r in s.query(AuditLog)}
    doomed = {ids[i] for i in plan["deletable_ids"]}
    assert "recovery.requested" not in doomed and "plain.noise" in doomed, plan


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
