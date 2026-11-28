"""TOY-BOARD: a toy concept board the provider refused is not held forever; holds carry codes.

Production (19i31, hourly concept re-judge; production rows NOT read here): 3 concepts held,
2 as `board_render_failed` (the toy concept render) and 1 as `board_missing` /
`engine_draft_refused`; the concept gate refused 52 intake concepts in 24 h. The readback
named none of the reasons.

Root cause reproduced here with the real toy inputs (an approved scan-style frog drafted on the
animal engine exactly as `cir.draft` will) and the real BFL wire shape: when Black Forest Labs
refuses the submit with a 4xx (a rejected key -- production saw `403 not_authenticated` -- or a
refused request), `gateway.images._post` raises `ImagesRefused` with `never_accepted_status`:
no task id, nothing billed (`images.generate` releases the claim unbilled). `toy_board` caught
only the gate's own refusals as "declined" and wrote everything else as PAID_UNFILED, "may have
been paid for; never bought again". So a toy whose first render met a rejected key was held
at `board_render_failed` on every re-judge forever, after the key was fixed, with no money ever
spent on it. Two concepts is exactly `MAX_RENDERS_PER_RUN`.

The fix records that case as PROVIDER_REFUSED (asked again on a later UTC day only, still
counted against MAX_RENDERS_PER_DAY, every owner gate and ceiling unchanged), and reads a
legacy PAID_UNFILED row the same way only when its message is the submit-refusal message AND
the ledger has no cost row for the board. Anything that may have been accepted stays
never-bought-again.

Every listing, render, key and judgement here is a TEST FIXTURE; no request leaves the process.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_toy_board.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import json
import socket
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse  # type: ignore[assignment]
socket.create_connection = _refuse  # type: ignore[assignment]

import test_amigurumi_judging as AJ  # noqa: E402 - FLUX activation at the owner's ceilings
import test_next_fixes_engine_board as NF  # noqa: E402 - a fast approved intake concept

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, CostEntry  # noqa: E402
from brambleloop.creative import board as B  # noqa: E402
from brambleloop.creative import intake as CI  # noqa: E402
from brambleloop.creative import toy_board as TB  # noqa: E402
from brambleloop.creative.preengineering import CHECKS  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402

T = NF.T
FROG = T._proposal(
    "puddle-frog-amigurumi", "Low-Sew Puddle Frog Amigurumi", "amigurumi", form="toy",
    construction="amigurumi_shaping", motif="plain frog", pod="home_decor",
    function="a soft keepsake to hold", palette_story="moss and cream", recipient="child",
    premise="A chunky low-sew frog with limbs worked into the body rounds, ready for "
            "puddle games")
SLUG = FROG["slug"]
NOW = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)


def _jpeg() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (1024, 1024), (110, 140, 80)).save(out, format="JPEG")
    return out.getvalue()


JPEG = _jpeg()


class Bfl:
    """FIXTURE BFL wire, at the HTTP layer `images._post` / `_get` read (the real functions
    run). `submit` is "ok", an HTTP status the submit is refused with, or "moderated" (accepted,
    then a terminal poll status). Records every request; sends nothing."""

    def __init__(self, submit="ok"):
        self.submit = submit
        self.requests: list[str] = []

    def __enter__(self):
        import urllib.request

        self._saved = (images._no_redirect, urllib.request.urlopen, images._poll_sleep)
        wire = self

        class Resp:
            def __init__(self, body: bytes, ctype="application/json"):
                self.body, self.headers = body, {"content-type": ctype}

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def open(self, request, timeout=None):
                wire.requests.append(f"{request.get_method()} {request.full_url}")
                if request.get_method() == "POST":
                    if isinstance(wire.submit, int):
                        raise urllib.error.HTTPError(
                            request.full_url, wire.submit, "refused", {},
                            io.BytesIO(b'{"detail":"Not authenticated"}'))
                    return Resp(json.dumps({"id": "t1", "cost": 4.0, "polling_url":
                                            "https://api.us.bfl.ai/v1/get_result?id=t1"})
                                .encode())
                status = "Request Moderated" if wire.submit == "moderated" else "Ready"
                return Resp(json.dumps({"id": "t1", "status": status, "result": {
                    "sample": "https://delivery.bfl.ai/t1.jpeg?se=x", "seed": 7}}).encode())

        images._no_redirect = lambda: Opener()
        urllib.request.urlopen = lambda url, timeout=None: Resp(JPEG, "image/jpeg")
        images._poll_sleep = lambda s: None
        return self

    def __exit__(self, *exc):
        import urllib.request

        images._no_redirect, urllib.request.urlopen, images._poll_sleep = self._saved
        return False


def _frog_db():
    db = NF._approved(FROG)
    AJ._activate_flux(db)
    return db


def _render(db, wire, *, now=NOW):
    with AJ._env(**AJ.KEY_ENV), wire:
        return TB.render_board(db, SLUG, now=now)


def _toy_costs(db) -> list:
    with db.session() as s:
        return [d for d in s.scalars(select(CostEntry.detail).where(CostEntry.kind == "image"))
                if (d or {}).get("slug") == SLUG]


def test_the_frog_is_a_toy_the_animal_engine_drafts():
    db = _frog_db()
    assert TB.toy_concept(db, SLUG)
    cir, route, _i = TB.engine_draft(db, SLUG)
    assert route["family"] == "amigurumi_animal" and TB.safety_preconditions(cir) == []


def test_a_render_through_the_real_bfl_wire_shape_is_filed():
    db = _frog_db()
    wire = Bfl()
    got = _render(db, wire)
    assert got["board"].startswith("sha256:") and got["paid"], got
    assert TB.state(db, SLUG)["state"] == TB.FILED
    assert [r.split()[0] for r in wire.requests] == ["POST", "GET"], wire.requests


def test_a_403_on_submit_is_not_paid_for_and_is_asked_again_on_a_later_day():
    """REGRESSION: before TOY-BOARD this was PAID_UNFILED and the concept was held forever."""
    db = _frog_db()
    got = _render(db, Bfl(submit=403))
    assert got["why_code"] == "provider_refused" and not got["paid"] and got["retry"], got
    assert TB.state(db, SLUG)["state"] == TB.PROVIDER_REFUSED, TB.state(db, SLUG)
    assert TB.state(db, SLUG)["provider_status"] == 403
    assert _toy_costs(db) == [], "a refused submit wrote a cost row"
    # Same UTC day: not asked again, nothing sent.
    wire = Bfl()
    again = _render(db, wire, now=NOW + timedelta(hours=1))
    assert again["why_code"] == "provider_refused_today" and wire.requests == [], again
    # The owner gate is unchanged and still binds: it counted the refused submit as an
    # outcome-unknown call, so the identical request is refused before sending for the rest
    # of the gate's UTC day, whatever this module decides.
    wire = Bfl()
    gated = _render(db, wire, now=NOW + timedelta(days=1))
    assert gated["why_code"] == "refused_before_sending" and wire.requests == [], gated
    assert "already_billed" in gated["why"], gated
    # A later UTC day for the gate too, the key fixed: the board is rendered and filed once.
    real = G._run_key
    G._run_key = lambda now: f"day:{(NOW + timedelta(days=1)).date().isoformat()}"
    try:
        wire = Bfl()
        later = _render(db, wire, now=NOW + timedelta(days=1))
    finally:
        G._run_key = real
    assert later["board"].startswith("sha256:"), later
    assert TB.state(db, SLUG)["state"] == TB.FILED


def test_a_refused_submit_still_uses_the_daily_render_cap():
    db = _frog_db()
    with db.session() as s:
        for k in range(TB.MAX_RENDERS_PER_DAY - 1):
            s.add(AuditLog(actor="creative", action=TB.ACTION, artifact=f"other-{k}",
                           detail={"state": TB.REQUESTED}))
    now = datetime.now(timezone.utc)
    got = _render(db, Bfl(submit=403), now=now)
    assert got["why_code"] == "provider_refused", got
    with db.session() as s:
        assert TB._requested_today(s, now) == TB.MAX_RENDERS_PER_DAY, "a refusal was uncounted"


def test_a_failure_after_acceptance_is_still_never_bought_again():
    db = _frog_db()
    got = _render(db, Bfl(submit="moderated"))
    assert got["why_code"] == "failed_after_paid" and got["paid"], got
    assert TB.state(db, SLUG)["state"] == TB.PAID_UNFILED
    wire = Bfl()
    again = _render(db, wire, now=NOW + timedelta(days=3))
    assert again["why_code"] == "already_requested" and wire.requests == [], again


def _legacy(db, why: str, *, cost: bool = False):
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=TB.ACTION, artifact=SLUG,
                       detail={"state": TB.REQUESTED, "job_id": 9}))
        s.add(AuditLog(actor="creative", action=TB.ACTION, artifact=SLUG,
                       detail={"state": TB.PAID_UNFILED, "job_id": 9, "why": why}))
        if cost:
            s.add(CostEntry(agent="creative", kind="image", amount_cad=0.07,
                            detail={"slug": SLUG, "what": "toy concept board"}))


def test_a_legacy_paid_unfiled_submit_refusal_with_no_cost_row_is_asked_again():
    db = _frog_db()
    _legacy(db, 'ImagesRefused: flux-3-image 403: {"detail":"Not authenticated"}')
    got = _render(db, Bfl())
    assert got["board"].startswith("sha256:"), got


def test_a_legacy_paid_unfiled_that_may_have_been_accepted_stays_held():
    for why, cost in (('ImagesRefused: flux-3-image 403: {"detail":"x"}', True),
                      ("ImagesRefused: flux-3-image returned request_moderated: {}", False),
                      ("TransientError: flux-3-image poll 404", False),
                      ("TimeoutError: timed out", False)):
        db = _frog_db()
        _legacy(db, why, cost=cost)
        wire = Bfl()
        got = _render(db, wire)
        assert got["why_code"] == "already_requested" and wire.requests == [], (why, got)


def _waiting_on_vision(db):
    with db.session() as s:
        s.add(AuditLog(actor="creative", action="concept.gate_waiting", artifact=SLUG,
                       detail={"waiting_on": ["image_vision"]}))


def _ctx(db):
    return SimpleNamespace(db=db, job=SimpleNamespace(id=None),
                           audit=lambda *a, **k: None, enqueue=lambda *a, **k: None)


def test_the_rejudge_hold_carries_the_render_reason_code_and_the_readback_counts_it():
    db = _frog_db()
    _waiting_on_vision(db)
    with AJ._env(**AJ.KEY_ENV), Bfl(submit=403):
        out = CI.judge_radar_waiting(_ctx(db), vision_ok=True, provider=object())
    held = [h for h in out["held"] if h["slug"] == SLUG]
    assert held and held[0]["code"] == "board_render_failed", out["held"]
    assert held[0]["render_why"] == "provider_refused", held
    assert PE._render_why_codes(out["held"]) == {"provider_refused": 1}
    assert PE._render_why_codes([{"code": "board_render_failed", "render_why": "free text"}]) \
        == {"other": 1}
    assert set(TB.WHY_CODES) >= {"provider_refused", "failed_after_paid", "other"}


def test_an_engine_draft_refusal_names_its_step():
    db = _frog_db()
    filed = CI.file_radar_board(db, SLUG)
    assert filed["why_code"] == "engine_draft_refused", filed
    assert filed["engine_why"] == "stuffed_animal_route", filed
    out = B.make_engine_board(db, "never-approved")
    assert out["engine_why"] == "not_approved", out
    held = [{"code": "board_missing", "board_why": "engine_draft_refused",
             "engine_why": "no_engine_board"},
            {"code": "board_missing", "board_why": "engine_draft_refused"},
            {"code": "board_missing", "board_why": "prototype_refused"}]
    assert PE._engine_why_codes(held) == {"no_engine_board": 1, "other": 1}


def test_gate_refusals_are_counted_by_failed_check_in_the_readback():
    db = T._db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for failed in (["motif_grammar"], ["jury", "motif_grammar"], [], ["not-a-check"]):
            s.add(AuditLog(actor="creative", action="concept.gate_refused", artifact="x",
                           detail={"decision": "refused", "failed": failed,
                                   "reasons": ["free text never read back"]}))
    got = PE.after_admission(db, now=now + timedelta(minutes=1))
    assert got["gate_refused"] == 4, got
    assert got["gate_refused_by_check"] == {"jury": 1, "motif_grammar": 2,
                                            "none_recorded": 1, "unrecognised": 1}, got
    assert set(got["gate_refused_by_check"]) <= set(CHECKS) | {"none_recorded",
                                                               "unrecognised"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("OK")
