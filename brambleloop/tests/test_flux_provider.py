"""ENG-FLUX-PROVIDER (2026-11-23): transient BFL answers no longer park a gallery.

Production: 503 x8 and transport failures x6 on submit during the Nov 22 burst, each retried
at once (no wait) and then recorded as a provider error; nothing re-drove a provider-blocked
run, so 4 galleries stopped calling FLUX for hours. Fixed here:
  1. a transient submit failure is retried after a wait (TRANSIENT_BACKOFF_S);
  2. an accepted (billed) job keeps polling through a short run of transient poll errors;
  3. a run blocked on a transient provider answer is restarted by the sweep, at most once per
     UTC hour, after PROVIDER_REDRIVE_AFTER, under every existing cap;
  4. the readback names the provider's words for provider blocks;
  plus insurance: a reference above 4 MP is sent as a bounded copy.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

from test_image_daily_ceiling_redrive import _blocked, _db, _follow  # noqa: E402
from test_w4_fluxapi import Transport, _gen, _refs  # noqa: E402
from test_w4_fluxstages import _WORK, _release  # noqa: E402

NOW = datetime.now(timezone.utc)
P503 = ("vessel side view could not be rendered: TransientError: flux-3-image 503: "
        '{"detail": "service unavailable"}')


def test_a_transient_submit_failure_is_retried_after_a_wait():
    waits: list[float] = []
    saved = S._sleep
    S._sleep = waits.append
    try:
        stub = S.StubRenderer(fail_with=[TransientError("503")])
        c = S.product_only(_release(), renderer=stub, work_dir=str(_WORK / "fp1"),
                           max_attempts=2)
    finally:
        S._sleep = saved
    assert len(stub.calls) == 2 and c.receipt["attempts"] == 2
    assert waits == [S.TRANSIENT_BACKOFF_S[0]] and waits[0] >= 10, waits


class _FlakyPoll(Transport):
    def __init__(self, fails: int, **kw):
        super().__init__(**kw)
        self.fails = fails

    def get(self, url, headers, *, label, timeout):
        if self.fails:
            self.fails -= 1
            self.gets += 1
            raise TransientError(f"{label} poll 503")
        return super().get(url, headers, label=label, timeout=timeout)


def test_an_accepted_job_keeps_polling_through_transient_poll_errors():
    t = _FlakyPoll(3, statuses=("Ready",))
    with tempfile.TemporaryDirectory() as d:
        out = _gen(t, _refs(1, Path(d)))
    assert len(t.posts) == 1 and out["sha256"], out       # one paid submit, the picture kept
    t = _FlakyPoll(I.BFL_POLL_TRANSIENT_MAX + 1, statuses=("Ready",))
    with tempfile.TemporaryDirectory() as d:
        try:
            _gen(t, _refs(1, Path(d)))
            raise AssertionError("a poll that never answers must still end")
        except TransientError:
            pass
    assert len(t.posts) == 1 and t.gets == I.BFL_POLL_TRANSIENT_MAX + 1


def test_transient_provider_blocks_are_recognised_and_final_ones_are_not():
    assert IP.provider_transient_block(P503)
    assert IP.provider_transient_block("identity anchor: provider error TransientError: "
                                       "flux-3-image unreachable: timed out")
    for final in ("budget stop: per-gallery cap CA$2.00 reached",
                  "vessel side view could not be rendered: ImagesRefused: flux-3-image 422: x",
                  "product fidelity FAIL after 3 attempts: bands",
                  "generator refused: GeneratorRefused: no certified release"):
        assert not IP.provider_transient_block(final), final


def test_a_transient_provider_block_is_redriven_once_per_hour_after_the_wait():
    real, IP._now = IP._now, (lambda: NOW)     # one UTC hour throughout
    try:
        _redrive_once_per_hour()
    finally:
        IP._now = real


def _redrive_once_per_hour():
    db = _db()
    fresh = _blocked(db, "basket-fresh", P503, when=NOW - timedelta(minutes=2))
    old = _blocked(db, "basket-old", P503, when=NOW - timedelta(hours=1))
    with db.session() as s:
        due = IP.redrive_due(s, None, now=NOW)
    assert due and due["kind"] == "provider_transient" and due["run_key"] == old, due
    calls: list = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [old], out
    assert fresh in [w["run_key"] for w in out["waiting"]], out
    assert len(calls) == 1
    # Blocked again within the same UTC hour: not redriven a second time this hour.
    from brambleloop.visual.image_records import ImageProductionRun
    from sqlalchemy import select
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == old))
        r.status, r.blocked_reason = "blocked", P503
        r.updated_at = NOW - timedelta(hours=1)
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert old not in [r["run_key"] for r in out["restarted"]], out
    assert len(calls) == 1


def test_an_oversized_reference_is_sent_as_a_bounded_copy():
    d = Path(tempfile.mkdtemp(prefix="fpbig_"))
    big = d / "big.png"
    Image.new("RGB", (3000, 2000), (120, 90, 60)).save(big)       # 5.7 MP
    small = d / "small.png"
    Image.new("RGB", (1000, 1000), (10, 20, 30)).save(small)
    import hashlib
    refs = {"paths": [str(small), str(big)],
            "sha256s": [hashlib.sha256(p.read_bytes()).hexdigest() for p in (small, big)],
            "roles": ["product", "pdf_page"]}
    out = S._bounded_references(refs, str(d / "work"))
    assert out["paths"][0] == str(small) and out["paths"][1] != str(big)
    with Image.open(out["paths"][1]) as im:
        assert im.size[0] * im.size[1] / 1_048_576 <= S.MAX_REFERENCE_MP
    assert out["sha256s"][1] == hashlib.sha256(Path(out["paths"][1]).read_bytes()).hexdigest()
    assert out["downscaled"][0]["position"] == 2
    assert S._bounded_references({**refs, "paths": [str(small)], "sha256s": refs["sha256s"][:1]},
                                 str(d / "w2"))["paths"] == [str(small)]


if __name__ == "__main__":
    import inspect
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                traceback.print_exc()
                print(f"FAIL {name} {exc!r}")
    print(f"PASS: {failed} failing" if not failed else f"FAIL: {failed} failing")
    sys.exit(1 if failed else 0)
