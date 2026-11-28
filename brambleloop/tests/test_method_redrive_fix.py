"""METHOD-REDRIVE-FIX (19i34 readback, 2026-11-28): manual_method/1 is live, yet no run made a
new candidate.

- market-basket-small (both runs) stopped at product_generation on the paid-provider gate's OLD
  per-gallery image cap ("budget stop: paid provider gate refused before sending
  (gallery_image_cap) ... cap of 16"). The owner raised that cap (16 -> 60, CA$2.50 -> 6.00),
  but the redrive only recognised the spend PLAN's wording, so the run read `final_block`.
- Any restart that resumes at product_generation (a raised cap, the daily reset, a transient
  provider answer) hit the OLD method's spent attempt cap and blocked again without a call:
  only a fidelity-gate method redrive scoped attempts to the current method.

Fixtures in the real tables; `restartable`, `restart`, `_attempts` and the hourly sweep are the
real functions. Nothing generates and nothing is paid.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_method_redrive_fix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_image_method_redrive as T  # noqa: E402

from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

CAP_REASON = ("budget stop: paid provider gate refused before sending (gallery_image_cap): "
              "[gallery_image_cap] gallery 'imgprod:market-basket-small@1.0.0@x' already has "
              "16 image(s) against the code's cap of 16 per gallery "
              "(BRAMBLELOOP_IMAGE_GALLERY_CAP may lower it, never raise it)")
TRANSIENT_REASON = ("vessel side view could not be rendered: TransientError: flux-3-image 503: "
                    "over capacity")


def _gallery(images: int, cad: float):
    real = G.gallery_spend

    def fake(db, gallery):
        return {"gallery": gallery, "images": images, "cad": cad, "by_provider": {}}
    G.gallery_spend = fake
    return real


def test_a_stop_on_the_old_gallery_image_cap_is_a_raised_cap_stop():
    assert IP.plan_budget_block(CAP_REASON)
    assert IP._redrive_kind(CAP_REASON, "product_generation") == "spend_plan_raised"
    assert IP.plan_budget_block("budget stop: paid provider gate refused before sending "
                                "(gallery_cad_cap): ...")
    # a daily ceiling and any other stop keep their own route
    assert not IP.plan_budget_block("budget stop: ... (provider_daily_ceiling) ...")
    assert not IP.plan_budget_block("vessel side view could not be rendered")


def test_it_restarts_under_the_current_method_with_a_fresh_attempt_budget():
    db = T._db()
    key = T._blocked(db, "market-basket-small", calls=16, spent=1.70, stamp=T.OLD,
                     stage="product_generation", reason=CAP_REASON)
    real = _gallery(16, 1.70)          # 16 of 60 images, CA$1.70 of 6.00
    try:
        assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 3
        can = IP.restartable(db, key)
        assert can["restartable"] and can["resume_at"] == "product_generation", can
        assert can["method_redrive"]["version"] == IP.current_method_version(), can
        calls = []
        out = IP.redrive_capability_blocked(db, follow=T._follow(calls))
        assert len(calls) == 1 and calls[0][0]["stage"] == "product_generation", (out, calls)
        rec = T._row(db, key)["stages"][IP.RESTART_KEY]
        assert rec["history"][-1]["by"] == IP.PLAN_REDRIVE_BY, rec
        assert rec["history"][-1]["method_version"] == IP.current_method_version()
        assert rec["method_redrive"]["version"] == IP.current_method_version()
        # the old method's three spent attempts no longer bind; calls and spend are untouched
        assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 0
        row = T._row(db, key)
        assert row["calls"] == 16 and abs(row["spent"] - 1.70) < 1e-9
    finally:
        G.gallery_spend = real


def test_it_stays_blocked_while_the_gallery_cap_in_force_still_binds():
    db = T._db()
    key = T._blocked(db, "market-basket-small", calls=16, spent=1.70, stamp=T.OLD,
                     stage="product_generation", reason=CAP_REASON)
    real = _gallery(int(G.image_caps()["gallery_images"]), 1.70)   # the cap is full
    try:
        room = IP.method_headroom(db, key, IP.get_run(db, key))
        assert room["ok"] is False and room["gallery"]["images_left"] == 0, room
        can = IP.restartable(db, key)
        assert not can["restartable"] and "final" in can["why"], can
        calls = []
        IP.redrive_capability_blocked(db, follow=T._follow(calls))
        assert calls == [] and T._row(db, key)["status"] == "blocked"
    finally:
        G.gallery_spend = real
    # and the CA$ cap binds the same way
    real = _gallery(16, float(G.image_caps()["gallery_cad"]))
    try:
        assert IP.method_headroom(db, key, IP.get_run(db, key))["ok"] is False
    finally:
        G.gallery_spend = real


def test_a_transient_resume_at_product_generation_is_scoped_to_the_current_method():
    db = T._db()
    key = T._blocked(db, "housewarming-key-basket", stamp=T.OLD, stage="product_generation",
                     reason=TRANSIENT_REASON)
    can = IP.restartable(db, key)
    assert can["restartable"] and can["resume_at"] == "product_generation", can
    assert can["method_redrive"]["eligible"] and can["method_redrive"]["ok"], can
    IP.restart(db, key, follow=T._follow([]), by=IP.PROVIDER_REDRIVE_BY, reason="test")
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 0
    # once per method: a later resume under the same method is not scoped again
    T._reblock(db, key, TRANSIENT_REASON)
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.stage = "product_generation"
    again = IP.restartable(db, key)
    assert not again["restartable"] and again.get("code") == IP.METHOD_REDRIVE_ALREADY, again


def test_failures_under_the_current_method_are_never_rescoped():
    db = T._db()
    key = T._blocked(db, "market-basket-small", stamp=IP.generation_method(),
                     stage="product_generation", reason=TRANSIENT_REASON)
    can = IP.restartable(db, key)
    assert not can["restartable"] and can.get("code") == IP.METHOD_REDRIVE_CURRENT, can
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 3


def test_caps_are_unchanged():
    assert G.GALLERY_IMAGE_CAP == 60 and G.GALLERY_CAD_CAP == 6.00 and G.DAILY_IMAGE_CAP == 120
    assert IP.MAX_RESTARTS == 3 and IP.MAX_ATTEMPTS_PER_ROLE == 3


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
