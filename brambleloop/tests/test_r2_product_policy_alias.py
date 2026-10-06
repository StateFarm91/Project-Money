"""R2 / J-product P-6: policy-loop key aliases are canonicalised by the guard AND the readers.

`invariants._norm` collapsed "Min-Shared" to `min_shared`, but `policy_loops.active()` then
read `payload[lp.param]` and raised KeyError -- so a registry incumbent spelled with an alias
broke listing.seo instead of falling back. Repro: audit_ddf9c6e/j_product_learn.py.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_policy_alias.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import tempfile

from _r2_harness import run

from brambleloop.core.db import Database
from brambleloop.improve import invariants as I, league, policy_loops as P

LP = P.BY_KEY["seo_lesson_match"]
ALIASES = ["Min-Shared", "MIN_SHARED", "min shared", "min_shared​", "ｍｉｎ_shared",
           " min-shared "]


def _db():
    d = tempfile.mkdtemp(prefix="r2alias_")
    db = Database(f"sqlite:///{d}/x.sqlite")
    db.create_all()
    return db


def _plant(db, payload):
    league.register(db, kind="scoring", key=LP.registry_key, payload=json.dumps(payload),
                    why_changed="alias payload planted to probe the read guard",
                    tests_declared=("t",), affected_departments=("seo_search",),
                    incumbent=True)


def test_every_alias_canonicalises_to_the_declared_param():
    assert ALIASES
    for a in ALIASES:
        assert I.canonical_key(a) == "min_shared", (a, I.canonical_key(a))


def test_active_reads_an_alias_payload_without_keyerror():
    for a in ("Min-Shared", "min_shared​", "ｍｉｎ_shared"):
        db = _db()
        _plant(db, {a: 3})
        out = P.active(db, LP.key)
        assert out["value"] == 3 and out["source"] == "registry", out


def test_active_falls_back_when_the_payload_names_nothing_readable():
    db = _db()
    _plant(db, {"Min-Shared": 3, "min_shared": 2})        # ambiguous twins
    out = P.active(db, LP.key)
    assert out["source"] == "code_default" and "refused_registry_value" in out, out


def test_aliases_of_protected_names_stay_protected():
    t = LP.tunable()
    for name in ("MIN-MATCHED", "min​matched", "ｍｉｎ_ｍａｔｃｈｅｄ", "Regression-Margin",
                 "catalogue​_depth", "Price Floor"):
        v = I.check(name, 1, tunable=t)
        assert not v.ok, (name, v)


def test_alias_values_are_still_bounds_checked():
    t = LP.tunable()
    assert not I.check("Min-Shared", 99, tunable=t).ok
    assert not I.check("ｍｉｎ_shared", True, tunable=t).ok


def test_twin_alias_keys_are_refused():
    bad = I.check_payload({"min_shared": 2, "Min-Shared": 3}, tunable=LP.tunable())
    assert bad and "more than one key" in bad[0].reason, bad


def test_submit_with_an_alias_does_not_raise():
    db = _db()
    out = P.submit(db, LP.key, {"Min-Shared": 3}, proposed_by="experiment_designer")
    assert "proposal" in out, out


run(globals())
