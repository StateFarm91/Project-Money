"""W4-FIRSTIMG: F-027 / F-031 / F-041, the first image must clearly show what is sold.

With `image_vision` open, the hero of every release is now:
* described blind, and compared in deterministic code against the product families the
  certified CIR makes (`inspect.compare` claim `identifies_as`). A misidentified hero blocks
  the chain (F-027);
* described again at search-grid size (`commerce.thumbnail.GRID_PX`) by `identify_at_grid`
  and blocked when it is not identifiable as the product, or reads ambiguous or unreadable
  there (F-031);
* never cleared on missing evidence. A call that failed, a CIR naming no product family, or
  an out-of-vocabulary clarity reads `unjudged`, and the publish path treats that as not
  reviewed (F-041).
Every call goes through the same budget reservation as `inspect_image`. The providers here
are stubs: no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstimg.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_firstimg_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))
os.environ.pop("ANTHROPIC_API_KEY", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-FIRSTIMG harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from PIL import Image  # noqa: E402

from brambleloop.core.resilience import PermanentError  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402


def _description(**over):
    base = {"object_shown": "a set of four hexagon coasters", "object_count": 4,
            "finished_or_in_progress": "finished", "human_present": False,
            "text_present": False, "chart_or_diagram": False,
            "dominant_colours": "cream, wine", "clarity": "clear",
            "third_party_marks": "none"}
    base.update(over)
    return base


class _Provider:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.003 * 1.37
    cost_per_1k_output_cad = 0.015 * 1.37

    def __init__(self, description=None, fail=False):
        self.description = description or _description()
        self.fail = fail
        self.calls = []

    def see(self, system, prompt, images, max_tokens=0):
        with Image.open(images[0]) as im:
            size = im.size
        self.calls.append({"system": system, "prompt": prompt, "size": size})
        if self.fail:
            raise PermanentError("stub provider refused")
        payload = json.dumps(self.description)

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


def _hero_png() -> str:
    path = os.path.join(_TMP, "hero.png")
    if not os.path.exists(path):
        Image.new("RGB", (2000, 2000), (230, 226, 214)).save(path)
    return path


def _seeded_db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


# ---- F-027: the comparison ------------------------------------------------------------

def test_identification_reads_the_family_and_never_defaults_to_true():
    ok = I.identification(_description(), ["coaster"])
    assert ok["identified"] is True and ok["named"] == ["coaster"]
    bad = I.identification(_description(object_shown="a striped blanket"), ["coaster"])
    assert bad["identified"] is False
    assert I.identification(_description(), [])["identified"] is None
    assert I.identification({}, ["coaster"])["identified"] is False


def test_a_hero_that_shows_something_else_does_not_communicate_its_claim():
    claim = {"shows_finished_object": True, "identifies_as": ["coaster"]}
    out = I.compare(_description(object_shown="a striped blanket"), claim)
    assert out["communicates"] is False
    assert [p["check"] for p in out["problems"]] == ["product_identity"]
    assert I.compare(_description(), claim)["communicates"] is True
    # Without the claim the comparison is unchanged (no family, nothing to compare).
    assert I.compare(_description(object_shown="a striped blanket"),
                     {"shows_finished_object": True})["communicates"] is True


def test_product_families_come_from_the_certified_cir():
    from brambleloop.products import launch0 as L

    assert I.product_families(L.cir_for("hexagon_coasters")) == ["coaster"]
    assert I.product_families(L.cir_for("basket_medium")) == ["basket"]


# ---- F-031: identification at grid size ---------------------------------------------

def test_the_grid_check_describes_the_downscaled_hero_blind():
    p = _Provider()
    out = I.identify_at_grid(_hero_png(), families=["coaster"], provider=p)
    assert out["verdict"] == "clear", out
    assert len(p.calls) == 1 and p.calls[0]["size"] == (230, 230)
    seen = (p.calls[0]["system"] + p.calls[0]["prompt"]).lower()
    assert "coaster" not in seen, "the describer was shown what it should find"


def test_misidentified_ambiguous_or_marked_heroes_are_blocked_at_grid_size():
    cases = {"GRID_NOT_IDENTIFIED": _description(object_shown="a patterned square"),
             "GRID_AMBIGUOUS": _description(clarity="ambiguous"),
             "GRID_UNREADABLE": _description(clarity="unreadable"),
             "GRID_THIRD_PARTY_MARKS": _description(third_party_marks=["KINFOLK"])}
    assert cases
    for code, desc in cases.items():
        out = I.identify_at_grid(_hero_png(), families=["coaster"], provider=_Provider(desc))
        assert out["verdict"] == "blocked", (code, out)
        assert any(p.startswith(code) for p in out["problems"]), (code, out["problems"])


def test_missing_evidence_is_unjudged_never_clear():
    out = I.identify_at_grid(_hero_png(), families=["coaster"], provider=_Provider(fail=True))
    assert out["verdict"] == "unjudged"
    p = _Provider()
    out = I.identify_at_grid(_hero_png(), families=[], provider=p)
    assert out["verdict"] == "unjudged" and not p.calls
    out = I.identify_at_grid(_hero_png(), families=["coaster"],
                             provider=_Provider(_description(clarity="unclear")))
    assert out["verdict"] == "unjudged", out
    out = I.identify_at_grid(os.path.join(_TMP, "missing.png"), families=["coaster"],
                             provider=_Provider())
    assert out["verdict"] == "unjudged"


def test_the_grid_call_reserves_bills_and_releases_through_the_budget():
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry, SpendReservation
    from brambleloop.finance import reservations

    db = _seeded_db()
    out = I.identify_at_grid(_hero_png(), families=["coaster"], db=db, provider=_Provider())
    assert out["verdict"] == "clear"
    assert reservations.outstanding(db)["cad"] == 0.0
    with db.session() as s:
        rows = list(s.scalars(select(SpendReservation)))
        assert len(rows) == 1 and rows[0].released_at is not None
        assert rows[0].agent == I.AGENT and rows[0].purpose == I.TASK
        costs = list(s.scalars(select(CostEntry).where(CostEntry.purpose == I.TASK)))
        assert len(costs) == 1 and costs[0].amount_cad > 0


def test_a_spent_daily_permission_refuses_before_the_provider():
    from datetime import datetime, timezone

    from brambleloop.core.models import CostEntry

    db = _seeded_db()
    with db.session() as s:
        s.add(CostEntry(agent=I.AGENT, amount_cad=0.999, kind="llm", purpose=I.TASK,
                        at=datetime.now(timezone.utc)))
    p = _Provider()
    out = I.identify_at_grid(_hero_png(), families=["coaster"], db=db, provider=p)
    assert not p.calls and out["verdict"] == "unjudged", out


# ---- wiring: the hero review in assets.build (`release._review_frames`) ---------------

def _review(inspect_desc, grid_verdict, families=("coaster",)):
    from brambleloop.build2 import executor
    from brambleloop.runtime import release

    gate = executor.GATE_BY_KEY["image_vision"]
    originals = (gate.check, I.inspect_image, I.identify_at_grid)

    def fake_inspect(ref, *, db=None, provider=None, claim=None):
        desc = inspect_desc if claim.get("shows_finished_object") else _description(
            object_shown="a page of pattern text", text_present=True)
        return {"described": True, "description": desc, "realism": {},
                "realism_unjudged": [], "semantic": I.compare(desc, claim or {})}

    def fake_grid(ref, *, families, db=None, provider=None, **_k):
        return {"verdict": grid_verdict, "why": f"stub {grid_verdict}", "grid_px": 230,
                "families": list(families or ())}

    audits = []
    ctx = SimpleNamespace(db=_seeded_db(),
                          audit=lambda action, **k: audits.append((action, k)))
    frames = [SimpleNamespace(position=1, role="hero"),
              SimpleNamespace(position=2, role="materials")]
    gate.check = lambda db_, env: True
    I.inspect_image, I.identify_at_grid = fake_inspect, fake_grid
    try:
        out = release._review_frames(ctx, "hexagon-coaster-set", "1.2.0", frames,
                                     {1: _hero_png(), 2: _hero_png()},
                                     shas={1: "a" * 64, 2: "b" * 64}, families=list(families))
    finally:
        gate.check, I.inspect_image, I.identify_at_grid = originals
    return out, audits


def test_a_clear_identified_hero_is_clear_and_records_both_readings():
    out, audits = _review(_description(), "clear")
    hero = out["verdicts"][1]
    assert hero["verdict"] == "clear" and not out["blocking"], out
    assert hero["identification"]["identified"] is True and hero["grid"]["verdict"] == "clear"
    assert audits and audits[0][1]["detail"]["frames"]["1"]["grid"]["verdict"] == "clear"


def test_a_misidentified_hero_stops_the_chain():
    out, _ = _review(_description(object_shown="a striped blanket"), "clear")
    assert out["verdicts"][1]["verdict"] == "blocked"
    assert any("FRAME_REVIEW_BLOCKED" in b and "product_identity" in b
               for b in out["blocking"]), out["blocking"]


def test_a_hero_not_identifiable_at_grid_size_stops_the_chain():
    out, _ = _review(_description(), "blocked")
    assert out["verdicts"][1]["verdict"] == "blocked"
    assert any("FRAME_REVIEW_HERO_NOT_IDENTIFIABLE" in b for b in out["blocking"])


def test_an_unmade_grid_check_or_unclaimed_family_leaves_the_hero_unjudged():
    out, _ = _review(_description(), "unjudged")
    assert out["verdicts"][1]["verdict"] == "unjudged" and not out["blocking"]
    out, _ = _review(_description(), "clear", families=())
    assert out["verdicts"][1]["verdict"] == "unjudged", out["verdicts"][1]
    assert out["verdicts"][2]["verdict"] == "clear"


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
