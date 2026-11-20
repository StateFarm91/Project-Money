"""D-OWNER-APPROVE-ALL: the owner's recorded directive activates exactly the listed paid
providers, once, inside the ceilings -- and gives nothing else directive authority."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import owner_directives as D  # noqa: E402

_TMP = tempfile.mkdtemp()
_N = [0]
NOW = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_N[0]}.db")
    db.create_all()
    G.ensure_tables(db)
    return db


def test_the_directive_activates_flux_generation_and_the_vision_judge_only():
    db = _db()
    assert not G.activation_state(db, "flux-3-image", "generation", now=NOW)["active"]
    out = D.apply(db, now=NOW)
    assert sorted(out["activated"]) == ["flux-3-image:generation", "openai-vision:vision"], out
    assert G.activation_state(db, "flux-3-image", "generation", now=NOW)["active"]
    assert G.activation_state(db, "openai-vision", "vision", now=NOW)["active"]
    act = G.activation_state(db, "flux-3-image", "generation", now=NOW)["activation"]
    assert act["monthly_ceiling_cad"] <= 40.0 and act["daily_ceiling_cad"] <= 5.0, act


def test_it_is_applied_once_and_never_renewed():
    db = _db()
    D.apply(db, now=NOW)
    again = D.apply(db, now=NOW + timedelta(hours=1))
    assert again["activated"] == [] and len(again["already"]) == 2, again
    later = NOW + D.EXPIRY + timedelta(days=1)
    assert not G.activation_state(db, "flux-3-image", "generation", now=later)["active"]
    assert D.apply(db, now=later)["activated"] == []      # expired: never renewed by the system


def test_no_other_provider_or_scope_can_claim_directive_authority():
    db = _db()
    with db.session() as s:
        s.add(G.PaidProviderActivation(
            provider="openai-vision", scope="generation", activated_by=D.ACTOR,
            activated_at=NOW, step_up={"owner_directive": D.DIRECTIVE_ID,
                                       "session_public_id": None},
            daily_ceiling_cad=1.0, monthly_ceiling_cad=1.0, per_gallery_cad=1.0,
            expires_at=NOW + timedelta(days=1)))
        s.add(G.PaidProviderActivation(
            provider="flux-3-image", scope="generation", activated_by="someone-else",
            activated_at=NOW, step_up={"owner_directive": D.DIRECTIVE_ID,
                                       "session_public_id": None},
            daily_ceiling_cad=1.0, monthly_ceiling_cad=1.0, per_gallery_cad=1.0,
            expires_at=NOW + timedelta(days=1)))
    assert not G.activation_state(db, "openai-vision", "generation", now=NOW)["active"]
    assert not G.activation_state(db, "flux-3-image", "generation", now=NOW)["active"]


def test_the_row_says_plainly_that_no_step_up_happened():
    db = _db()
    D.apply(db, now=NOW)
    from sqlalchemy import select
    with db.session() as s:
        rows = list(s.scalars(select(G.PaidProviderActivation)))
    assert rows and all(r.step_up.get("session_public_id") is None
                        and r.step_up.get("step_up_performed") is False for r in rows)


def test_the_hourly_job_applies_it_and_the_sweep_itself_signs_nothing():
    import ast
    from brambleloop.ops import owner_queue_consolidate as OQC
    from brambleloop.runtime import owner_queue_ops as J
    assert "owner_directives" not in open(OQC.__file__).read()
    tree = ast.parse(open(J.__file__).read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "apply"]
    assert calls, "the hourly job must apply the directive"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
