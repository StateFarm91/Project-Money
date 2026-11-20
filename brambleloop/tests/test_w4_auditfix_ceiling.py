"""Re-audit D-1 (INDEPENDENT_REAUDIT_7421ef6): a NaN ceiling must never disable the ceiling.

`BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD=nan` parsed, `min(nan, 100.0)` returned `nan`, and
`committed + estimate > nan` is always False -- a month already spent five times over was
granted another reservation. Every non-finite or non-positive environment value now falls back
to the authorised ceiling; the check itself refuses a non-finite ceiling; an agent's NaN daily
permission refuses rather than grants; an ads budget of NaN is refused.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "ETSY", "BRAMBLELOOP")):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent  # noqa: E402
from brambleloop.finance import spend_policy, spend_report  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402

VAR = "BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"
_TMP = tempfile.mkdtemp(prefix="w4-auditfix-ceiling-")


def _db():
    db = Database(f"sqlite:///{_TMP}/{os.urandom(4).hex()}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class _env:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self.old = os.environ.get(VAR)
        if self.value is None:
            os.environ.pop(VAR, None)
        else:
            os.environ[VAR] = self.value

    def __exit__(self, *a):
        if self.old is None:
            os.environ.pop(VAR, None)
        else:
            os.environ[VAR] = self.old


def test_bad_environment_values_fall_back_to_the_authorised_ceiling():
    authorised = spend_policy.ceiling_cad()
    for bad in ("nan", "NaN", "-nan", "inf", "-inf", "Infinity", "0", "-5", "0.0",
                "-0", "abc", ""):
        with _env(bad):
            got = gw.monthly_ceiling_cad()
            assert got == authorised, (bad, got)
    with _env(None):
        assert gw.monthly_ceiling_cad() == authorised


def test_environment_may_still_lower_but_never_raise_the_ceiling():
    authorised = spend_policy.ceiling_cad()
    with _env("12.5"):
        assert gw.monthly_ceiling_cad() == min(12.5, authorised)
    with _env(str(authorised * 10)):
        assert gw.monthly_ceiling_cad() == authorised


def test_the_audit_repro_is_refused_with_nan_in_the_environment():
    db = _db()
    spend_report.record(db, agent="gateway", amount_cad=500.0, purpose="spent month")
    with _env("nan"):
        try:
            gw.check_budget_cad(db, estimate_cad=50.0, purpose="re-audit D-1 repro")
        except gw.BudgetExceeded:
            pass
        else:
            raise AssertionError("a NaN ceiling granted a reservation on a spent month")


def test_the_check_refuses_a_non_finite_ceiling_handed_to_it_directly():
    db = _db()
    real = gw.monthly_ceiling_cad
    for bad in (float("nan"), float("inf"), 0.0, -1.0):
        gw.monthly_ceiling_cad = lambda bad=bad: bad
        try:
            try:
                gw.check_budget_cad(db, estimate_cad=0.01, purpose="direct bad ceiling")
            except gw.BudgetExceeded:
                pass
            else:
                raise AssertionError(f"ceiling {bad!r} granted a reservation")
        finally:
            gw.monthly_ceiling_cad = real


def test_a_nan_agent_daily_permission_refuses_rather_than_grants():
    # SQLite stores NaN as NULL (and the column is NOT NULL), but Postgres's float column
    # holds 'NaN' -- so the row the registry returns is patched to carry one.
    db = _db()
    with db.session() as s:
        row = s.scalars(select(Agent).where(Agent.daily_cost_ceiling_cad > 0)).first()
        assert row is not None, "seeded registry has no agent with a daily ceiling"
        name = row.name
    real_get = Registry.get

    def nan_get(self, agent_name):
        got = real_get(self, agent_name)
        if agent_name == name:
            got.daily_cost_ceiling_cad = float("nan")
        return got

    Registry.get = nan_get
    try:
        permission = gw.agent_daily_ceiling(db, name)
        assert permission is not None and permission["daily_ceiling_cad"] == 0.0, permission
        try:
            gw.check_budget_cad(db, estimate_cad=0.01, agent=name, purpose="nan permission")
        except gw.AgentCeilingExceeded:
            pass
        else:
            raise AssertionError("a NaN daily permission granted spend")
    finally:
        Registry.get = real_get


def test_ads_campaign_budget_rejects_non_finite_amounts_statically():
    # The handler needs live ad authority to reach the check; pin the guard in source so a
    # refactor cannot drop it silently (the behavioural gates above it all refuse today).
    src = (ROOT / "src/brambleloop/runtime/growth_ops.py").read_text()
    assert "not math.isfinite(amount)" in src and "not math.isfinite(headroom)" in src


if __name__ == "__main__":
    import shutil
    fails = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("OK  ", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    import traceback
                    traceback.print_exc()
                    print("FAIL", name, repr(e))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"{fails} failing")
    sys.exit(1 if fails else 0)
