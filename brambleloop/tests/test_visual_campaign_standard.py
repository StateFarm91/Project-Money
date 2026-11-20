"""ENG-VISUAL: the seven-frame campaign standard (`visual.shot_plans.campaign_standard`).

1. every Launch-0 campaign plan meets it (seven or more frames, one job each);
2. a plan below seven, or with a repeated job, is refused -- never padded;
3. `image_production.readiness` is never gallery-ready below the standard, and reports the
   shortfall as a set-check problem.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_visual_campaign_standard.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.pop("DATABASE_URL", None)
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import shot_plans as SP  # noqa: E402


def test_the_minimum_is_seven():
    assert SP.CAMPAIGN_MIN_FRAMES == 7


def test_every_launch0_campaign_meets_the_standard():
    slugs = list(launch0.LAUNCH0_SLUGS)
    assert len(slugs) >= 1
    for slug in slugs:
        st = SP.campaign_standard(SP.campaign_plan(slug))
        assert st["ok"] is True and st["frames"] >= 7, (slug, st)


def _short(plan, n):
    return {**plan, "roles": plan["roles"][:n], "image_count": n}


def test_a_plan_below_seven_or_with_a_repeated_job_is_refused():
    plan = SP.campaign_plan(next(iter(launch0.LAUNCH0_SLUGS)))
    st = SP.campaign_standard(_short(plan, 6))
    assert st["ok"] is False
    assert st["problems"] == [{"kind": "campaign_below_standard", "frames": 6, "minimum": 7}]
    roles = plan["roles"]
    dup = {**plan, "roles": roles[:6] + [dict(roles[1])]}
    st = SP.campaign_standard(dup)
    assert st["ok"] is False and st["problems"][0]["kind"] == "campaign_duplicate_job", st


def test_readiness_is_never_gallery_ready_below_the_standard():
    d = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cs_')}/c.db")
    d.create_all()
    slug = next(iter(launch0.LAUNCH0_SLUGS))
    plan = SP.campaign_plan(slug)
    full = IP.readiness(d, slug, plan=plan)
    assert full["campaign_standard"]["ok"] is True
    short = IP.readiness(d, slug, plan=_short(plan, 6))
    assert short["campaign_standard"]["ok"] is False
    assert short["gallery_ready"] is False
    kinds = [p.get("kind") for p in short["set_check"]["problems"]]
    assert "campaign_below_standard" in kinds, kinds
    assert short["set_check"]["ok"] is False


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
