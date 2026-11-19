"""ENG-MOTIF: the motif judge's vision call is reserved, and a refused one is re-asked.

`publish/motif_fidelity.py::check` called `provider.see` with no `check_budget`. Every
paid vision call passes the paid-provider gate, and the gate refuses a call with no live
reservation (`no_budget_reservation`). So in production the comparison was never sent, the
refusal was swallowed as UNMEASURABLE, and a render that was already paid for came out
unusable. Spend failed closed. The quality gate was dead.

These tests drive the real `AnthropicProvider` through the real gate with `_send` replaced,
so "nothing was sent" is counted at the last point before the network:

* with a reservation the comparison is measured and the verdict reaches `motif_verified`;
* with no budget it is UNMEASURABLE with a coded reason and `rejudge`, and nothing is sent;
* the reservation and the bill are under `quality_director` / `asset_inspection`;
* the mutation: the same call with the reservation taken away is refused by the gate;
* the photo jobs re-ask about the same kept render rather than charging it as an attempt,
  but only when a match could make it usable (F-852 redraws are not waited on).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR",
                      os.path.join(tempfile.mkdtemp(prefix="motif_res_"), "artifacts"))

from sqlalchemy import select  # noqa: E402

import _paid_activation as _paid  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.gateway import anthropic as A  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish import model_photography as mp  # noqa: E402
from brambleloop.publish import motif_fidelity as mf  # noqa: E402
from brambleloop.publish import owned_photography as op  # noqa: E402

SLUG = "cloudline-baby-blanket"
MATCHING = ('{"repeating_unit_shape": "diamond outline lattice", "repeats_across": 14, '
            '"colour_arrangement": "two colours alternating", '
            '"same_pattern_as_chart": true, "fabric_readable": true}')
CHECKERBOARD = ('{"repeating_unit_shape": "solid square", "repeats_across": 8, '
                '"colour_arrangement": "two colours alternating", '
                '"same_pattern_as_chart": false, "fabric_readable": true}')


def _subject():
    cir = for_slug(SLUG)
    return cir, build_twin(cir, compile_cir(cir))


def _db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _png(name: str = "render.png") -> str:
    """A small real picture, different per name so two renders never share a digest."""
    import zlib

    from PIL import Image

    path = Path(tempfile.mkdtemp(prefix="motif-render-")) / name
    shade = zlib.crc32(name.encode()) % 200
    Image.new("RGB", (64, 64), (shade, 180, 160)).save(path)
    return str(path)


class _Wire:
    """`AnthropicProvider._send`, counted. Reached only after the gate let the call through."""

    def __init__(self, text: str = MATCHING):
        self.text, self.sends = text, 0

    def __call__(self, provider, payload, key, *, timeout=None):
        from brambleloop.gateway.model_gateway import ModelResponse

        self.sends += 1
        return ModelResponse(text=self.text, provider="anthropic", model=provider.model,
                             input_tokens=2400, output_tokens=120, latency_ms=1.0)


@contextmanager
def _live(db, text: str = MATCHING, *, activate: bool = True):
    """The real provider and the real gate, with the wire replaced and a job scope open."""
    from brambleloop.gateway import paid_calls
    from brambleloop.queue.durable import JobQueue

    if activate:
        _paid.activate(db, G.ANTHROPIC_VISION)
    wire = _Wire(text)
    job = JobQueue(db).enqueue("quality_director", "assets.owned_photography", {},
                               idempotency_key=f"motif-res:{id(wire)}")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-dummy"}), \
            patch.object(A.AnthropicProvider, "_send",
                         lambda self, payload, key, timeout=None:
                         wire(self, payload, key, timeout=timeout)), \
            paid_calls.job_scope(db, job):
        G.take_budget()  # start from no noted reservation, whatever an earlier test left
        yield wire


def _spend_the_day(db):
    """`quality_director` may spend CA$1.00 a day; leave it nothing."""
    from datetime import datetime, timezone

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        s.add(CostEntry(agent="quality_director", amount_cad=0.999, kind="llm",
                        purpose="asset_inspection", at=datetime.now(timezone.utc)))


# ---------------------------------------------------------------------------------------------
# The call


def test_with_a_reservation_the_motif_is_measured_through_the_real_gate():
    cir, twin = _subject()
    db = _db()
    with _live(db) as wire:
        out = mf.check(db, _png(), cir, twin)
    assert wire.sends == 1, "the reserved comparison never reached the wire"
    assert out["verdict"] == mf.MATCH, out
    assert "unmeasured" not in out


def test_the_reservation_and_the_bill_are_the_quality_directors_asset_inspection():
    from brambleloop.core.models import CostEntry, SpendReservation
    from brambleloop.finance import reservations

    cir, twin = _subject()
    db = _db()
    with _live(db):
        mf.check(db, _png(), cir, twin)
    with db.session() as s:
        held = list(s.scalars(select(SpendReservation)))
        mine = [r for r in held if r.purpose == mf.TASK]
        assert len(mine) == 1, [(r.agent, r.purpose) for r in held]
        row = mine[0]
        assert row.agent == "quality_director" and mf.AGENT == "quality_director"
        assert row.released_at is not None, "the reservation was left to expire"
        assert 0 < row.actual_cad <= row.amount_cad
        bills = [c for c in s.scalars(select(CostEntry))
                 if c.agent == "quality_director" and c.purpose == "asset_inspection"]
        assert len(bills) == 1, "the comparison wrote no spend row, so the month cannot see it"
        assert abs(bills[0].amount_cad - row.actual_cad) < 1e-9
    assert reservations.outstanding(db)["cad"] == 0.0


def test_the_reservation_covers_both_pictures_at_the_gates_own_figure():
    """The gate prices the request it sees -- two images -- and refuses a smaller
    reservation as `reservation_underfunded`. A one-image estimate would fail here."""
    from brambleloop.core.models import SpendReservation

    cir, twin = _subject()
    db = _db()
    with _live(db) as wire:
        mf.check(db, _png(), cir, twin)
    own = A.estimate_cad(A.AnthropicProvider(model=A.provider_for(mf.TASK).model).model,
                         input_tokens=A.IMAGE_TOKENS_ESTIMATE * 2 + len(mf.prompt()) // 4,
                         output_tokens=mf.MAX_TOKENS)
    with db.session() as s:
        row = [r for r in s.scalars(select(SpendReservation)) if r.purpose == mf.TASK][0]
    assert wire.sends == 1 and row.amount_cad + 1e-9 >= own


def test_with_no_budget_it_is_unmeasurable_with_a_reason_and_nothing_is_sent():
    from brambleloop.core.models import AuditLog

    cir, twin = _subject()
    db = _db()
    _spend_the_day(db)
    with _live(db) as wire:
        out = mf.check(db, _png(), cir, twin)
    assert wire.sends == 0, "the ceiling was checked after the money had already left"
    assert out["verdict"] == mf.UNMEASURABLE
    assert out["unmeasured"] == mf.UNMEASURED_BUDGET and out["rejudge"] is True
    assert "quality_director" in out["why"] and "nothing was sent" in out["why"]
    with db.session() as s:
        refused = [r for r in s.scalars(select(AuditLog)) if r.action == "spend.refused"]
    assert refused, "the refusal left no row, so it cannot be told from a guard that never fires"
    assert mf.rejudgeable(out)


def test_mutation_without_the_reservation_the_gate_refuses_and_nothing_is_sent():
    """Removing the reservation -- the defect -- is caught by the gate, not by luck.

    `check_budget` is made to answer without writing a reservation (`reserve=False`), which
    is the old unreserved call in every respect that matters to the gate. The comparison is
    not sent, the reason is the gate's `no_budget_reservation`, and the first test in this
    file would read UNMEASURABLE instead of MATCH.
    """
    from brambleloop.gateway import providers as gw

    real = gw.check_budget

    def unreserved(db, **kw):
        kw["reserve"] = False
        return real(db, **kw)

    cir, twin = _subject()
    db = _db()
    with _live(db) as wire, patch.object(gw, "check_budget", unreserved):
        out = mf.check(db, _png(), cir, twin)
    assert wire.sends == 0
    assert out["verdict"] == mf.UNMEASURABLE
    assert out["unmeasured"] == mf.UNMEASURED_BUDGET
    assert "no_budget_reservation" in out["why"]


def test_a_permission_refusal_is_coded_apart_from_a_budget_one():
    """Not activated by the owner: still nothing sent, still re-askable, but named as the
    gate's permission rather than as money."""
    cir, twin = _subject()
    db = _db()
    with _live(db, activate=False) as wire:
        out = mf.check(db, _png(), cir, twin)
    assert wire.sends == 0
    assert out["unmeasured"] == mf.UNMEASURED_GATE and out["rejudge"] is True
    assert "not_activated_by_owner" in out["why"]


def test_no_accounting_store_is_refused_before_anything_is_built():
    cir, twin = _subject()

    class Provider:
        model = A.provider_for(mf.TASK).model
        calls = 0

        def see(self, *a, **k):
            Provider.calls += 1
            raise AssertionError("reached")

    out = mf.check(None, _png(), cir, twin, provider=Provider())
    assert Provider.calls == 0
    assert out["unmeasured"] == mf.UNMEASURED_NO_LEDGER and out["rejudge"] is True


def test_an_unreadable_answer_is_paid_for_and_is_not_re_asked():
    """The answer was bought; asking again would buy the same unreadable answer."""
    cir, twin = _subject()
    db = _db()
    with _live(db, text="I think it is lovely") as wire:
        out = mf.check(db, _png(), cir, twin)
    assert wire.sends == 1
    assert out["unmeasured"] == mf.UNMEASURED_ANSWER and out["rejudge"] is False
    assert not mf.rejudgeable(out)


def test_a_legacy_unreserved_refusal_is_recognised_as_re_askable():
    """Production records filed before the reason was a code carry only the gate's words."""
    legacy = {"verdict": mf.UNMEASURABLE, "expected": {},
              "why": "the comparison call failed: ('no live company-budget reservation for "
                     "this call (reservation None); the accounting evidence ...')"}
    assert mf.rejudgeable(legacy)
    assert not mf.rejudgeable(dict(legacy, why="the comparison call failed: timeout"))
    assert not mf.rejudgeable({"verdict": mf.MISMATCH, "why": legacy["why"]})


# ---------------------------------------------------------------------------------------------
# The photo jobs: a paid render is re-asked about, not thrown away


def _kept(path: str) -> dict:
    from brambleloop.visual import tournament

    return tournament._keep(path)


def _qualified_floor(frame):
    """A stand-in for a qualified whole-product producer, which this base does not have:
    PASS exactly when the motif matched. F-852 gives a generated frame no PASS today."""
    verdict = ((frame or {}).get("motif") or {}).get("verdict")
    return {"status": "PASS" if verdict == mf.MATCH else
            "FAIL" if verdict == mf.MISMATCH else "UNKNOWN"}


def _refused_motif() -> dict:
    return {"verdict": mf.UNMEASURABLE, "expected": {}, "unmeasured": mf.UNMEASURED_BUDGET,
            "rejudge": True, "why": "no budget to ask (fail closed), nothing was sent"}


def _file(db, action: str, detail: dict) -> None:
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=SLUG, detail=detail))


def _owned_asset(cir, image: dict, **over) -> dict:
    out = {"made": True, "slug": cir.slug, "version": cir.version,
           "method_version": op.METHOD_VERSION, "verdict": "clear", "why": "clear",
           "image": image, "motif": _refused_motif(), "motif_verified": False,
           "usable_as_listing_asset": False, "spent_cad": 0.04,
           "inspection": {"realism": {}}}
    out.update(over)
    return out


def test_an_owned_render_waiting_on_its_motif_is_re_asked_not_charged():
    cir, twin = _subject()
    db = _db()
    _file(db, op.ACTION, _owned_asset(cir, _kept(_png())))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        assert op.ordinary_attempts(db, slug=cir.slug, version=cir.version) == []
        move = op.what_to_do_next(db, slug=cir.slug, version=cir.version)
        assert move["render"] is False and move["reason"] == "motif_rejudge_pending"

        with _live(db) as wire:
            again = op.rejudge_motif(db, move["asset"], cir, twin,
                                     work_dir=tempfile.mkdtemp(prefix="rejudge-"))
        assert wire.sends == 1 and again["filed"] is True
        record = again["record"]
        assert record["motif"]["verdict"] == mf.MATCH
        assert record["motif_verified"] is True and record["usable_as_listing_asset"] is True
        assert record["spent_cad"] == 0.0
        assert record["motif_rejudge"]["previous_unmeasured"] == mf.UNMEASURED_BUDGET
        _file(db, op.ACTION, record)

        # One render, one attempt, and now it is the usable asset.
        assert len(op.current_states(db, slug=cir.slug, version=cir.version)) == 1
        move = op.what_to_do_next(db, slug=cir.slug, version=cir.version)
        assert move["reason"] == "usable_asset_on_file"


def test_a_re_asked_mismatch_is_charged_once_and_is_not_usable():
    cir, twin = _subject()
    db = _db()
    _file(db, op.ACTION, _owned_asset(cir, _kept(_png())))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        asset = op.pending_rejudge(db, slug=cir.slug, version=cir.version)
        with _live(db, text=CHECKERBOARD):
            again = op.rejudge_motif(db, asset, cir, twin,
                                     work_dir=tempfile.mkdtemp(prefix="rejudge-"))
        record = again["record"]
        assert record["motif_verified"] is False and not record["usable_as_listing_asset"]
        _file(db, op.ACTION, record)
        assert len(op.ordinary_attempts(db, slug=cir.slug, version=cir.version)) == 1
        assert op.pending_rejudge(db, slug=cir.slug, version=cir.version) is None


def test_a_still_refused_re_ask_files_nothing_and_keeps_the_render_waiting():
    cir, twin = _subject()
    db = _db()
    _spend_the_day(db)
    _file(db, op.ACTION, _owned_asset(cir, _kept(_png())))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        asset = op.pending_rejudge(db, slug=cir.slug, version=cir.version)
        with _live(db) as wire:
            again = op.rejudge_motif(db, asset, cir, twin,
                                     work_dir=tempfile.mkdtemp(prefix="rejudge-"))
        assert wire.sends == 0 and again["filed"] is False
        assert again["motif"]["unmeasured"] == mf.UNMEASURED_BUDGET
        assert op.pending_rejudge(db, slug=cir.slug, version=cir.version) is not None


def test_a_render_whose_bytes_are_gone_stops_waiting():
    cir, twin = _subject()
    db = _db()
    gone = {"sha256": "0" * 64, "content_type": "image/png"}
    _file(db, op.ACTION, _owned_asset(cir, gone))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        asset = op.pending_rejudge(db, slug=cir.slug, version=cir.version)
        with _live(db) as wire:
            again = op.rejudge_motif(db, asset, cir, twin,
                                     work_dir=tempfile.mkdtemp(prefix="rejudge-"))
        assert wire.sends == 0 and again["filed"] is True
        assert again["record"]["motif"]["unmeasured"] == mf.UNMEASURED_IMAGE_MISSING
        _file(db, op.ACTION, again["record"])
        assert op.pending_rejudge(db, slug=cir.slug, version=cir.version) is None
        assert len(op.ordinary_attempts(db, slug=cir.slug, version=cir.version)) == 1


def test_an_f852_redraw_is_not_waited_on_and_buys_no_call():
    """At this base a generated frame never reaches a structural PASS, so a match could not
    make it usable. It is counted as the attempt it was and nobody pays to re-ask."""
    cir, _twin = _subject()
    db = _db()
    _file(db, op.ACTION, _owned_asset(cir, _kept(_png())))
    assert op.pending_rejudge(db, slug=cir.slug, version=cir.version) is None
    assert len(op.ordinary_attempts(db, slug=cir.slug, version=cir.version)) == 1
    move = op.what_to_do_next(db, slug=cir.slug, version=cir.version)
    assert move["reason"] != "motif_rejudge_pending"


def _frame(cir, shot: str, image: dict, *, motif: dict, product_truth: str) -> dict:
    floors = {name: "pass" for name in mp.FLOORS}
    floors["product_truth"] = product_truth
    return {"made": True, "shot": shot, "slug": cir.slug, "version": cir.version,
            "image": image, "motif": motif, "floors": floors,
            "usable_as_listing_asset": product_truth == "pass", "spent_cad": 0.04}


def _sequence_record(cir, frames: list[dict]) -> dict:
    floors = mp._combine_floors(frames)
    return {"made": True, "slug": cir.slug, "version": cir.version,
            "method_version": mp.METHOD_VERSION, "frames": frames, "floors": floors,
            "usable_as_listing_asset": all(v == "pass" for v in floors.values())}


def _waiting_sequence(cir) -> dict:
    fit = _frame(cir, "fit", _kept(_png("fit.png")),
                 motif={"verdict": mf.MATCH, "why": "match"}, product_truth="pass")
    detail = _frame(cir, "detail", _kept(_png("detail.png")), motif=_refused_motif(),
                    product_truth="unverifiable")
    return _sequence_record(cir, [fit, detail])


_PLAN = {"render_here": ["fit", "detail"], "plan": {"product_form": "blanket"}}


def test_a_model_frame_waiting_on_its_motif_is_not_an_attempt_and_is_re_asked():
    cir, twin = _subject()
    db = _db()
    _file(db, mp.ACTION, _waiting_sequence(cir))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        assert mp.attempts_for(db, slug=cir.slug, version=cir.version) == 0
        rendered = []
        with _live(db) as wire, patch.object(mp, "make",
                                             lambda *a, **k: rendered.append(k) or {}):
            out = mp.sequence(db, cir, twin, shot_plan=_PLAN,
                              work_dir=tempfile.mkdtemp(prefix="seq-"))
        assert rendered == [], "a frame was re-rendered instead of re-asked about"
        assert wire.sends == 1
        assert out["rejudged_frames"] == ["detail"] and out["reused_frames"] == ["fit"]
        assert out["motif_rejudge_only"] is True
        assert out["floors"]["product_truth"] == "pass" and out["usable_as_listing_asset"]
        detail = out["frames"][1]
        assert detail["motif_verified"] is True and detail["spent_cad"] == 0.0
        assert out["spent_cad"] == 0.0
        _file(db, mp.ACTION, out)
        # One answered render: charged once. Nothing is waiting any more.
        assert mp.attempts_for(db, slug=cir.slug, version=cir.version) == 1
        assert mp._rejudgeable_frame(db, cir, shot="detail") is None


def test_a_model_sequence_whose_re_ask_is_still_refused_waits_and_renders_nothing():
    cir, twin = _subject()
    db = _db()
    _spend_the_day(db)
    _file(db, mp.ACTION, _waiting_sequence(cir))
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        rendered = []
        with _live(db) as wire, patch.object(mp, "make",
                                             lambda *a, **k: rendered.append(k) or {}):
            out = mp.sequence(db, cir, twin, shot_plan=_PLAN,
                              work_dir=tempfile.mkdtemp(prefix="seq-"))
        assert wire.sends == 0 and rendered == []
        assert out["made"] is False and out["waiting_on"] == "motif_judgement"
        assert out["unmeasured"] == mf.UNMEASURED_BUDGET
        assert mp._rejudgeable_frame(db, cir, shot="detail") is not None


def test_a_model_frame_f852_cannot_use_is_charged_and_not_waited_on():
    cir, _twin = _subject()
    db = _db()
    _file(db, mp.ACTION, _waiting_sequence(cir))
    assert mp._rejudgeable_frame(db, cir, shot="detail") is None
    assert mp.attempts_for(db, slug=cir.slug, version=cir.version) == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
