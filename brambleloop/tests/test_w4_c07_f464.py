"""W4-C07 F-464 PROPOSAL: the deferred render (submit, then one poll per durable job). Fakes
only (tests/test_w4_fluxapi.Transport); no render is bought."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import CostEntry  # noqa: E402


# ---- F-464 -----------------------------------------------------------------------------------

def test_f464_deferred_render_never_resubmits_and_bills_once():
    import test_w4_fluxapi as FX

    from brambleloop.gateway import images as I
    from brambleloop.gateway import paid_calls

    db = FX._db()
    prompt = "a deterministic render of the certified blanket, laid flat"
    with FX.Transport(statuses=("Pending", "Generating", "Ready")) as t:
        sub = I.submit_render(prompt, provider_key="flux-3-image", env=FX.ENV, db=db,
                              purpose="test.deferred")
        assert sub["state"] == I.ACCEPTED and len(t.posts) == 1
        again = I.submit_render(prompt, provider_key="flux-3-image", env=FX.ENV, db=db,
                                purpose="test.deferred")
        assert again["resubmitted"] is False and len(t.posts) == 1     # never re-sent
        with db.session() as s:
            assert not list(s.scalars(select(CostEntry)))               # not billed yet
        with tempfile.TemporaryDirectory() as work:
            assert I.poll_render(sub["fingerprint"], work_dir=work, env=FX.ENV,
                                 db=db)["done"] is False
            assert I.poll_render(sub["fingerprint"], work_dir=work, env=FX.ENV,
                                 db=db)["done"] is False
            done = I.poll_render(sub["fingerprint"], work_dir=work, env=FX.ENV, db=db)
            assert done["done"] and Path(done["path"]).read_bytes() == FX.OUT_PNG
            replay = I.poll_render(sub["fingerprint"], work_dir=work, env=FX.ENV, db=db)
            assert replay["replayed"] and replay["cad"] == 0.0
        assert t.gets == 3
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
        assert len(rows) == 1 and rows[0].detail["billing"] == "rendered"   # exactly once

    with FX.Transport(statuses=("Request Moderated",)):
        bad = I.submit_render(prompt + " v2", provider_key="flux-3-image", env=FX.ENV, db=db)
        with tempfile.TemporaryDirectory() as work:
            try:
                I.poll_render(bad["fingerprint"], work_dir=work, env=FX.ENV, db=db)
                raise AssertionError("a moderated render was accepted")
            except I.ImagesRefused:
                pass
        try:
            I.submit_render(prompt + " v2", provider_key="flux-3-image", env=FX.ENV, db=db)
            raise AssertionError("a billed failure was re-sent")
        except paid_calls.PaidCallReplayedFailure:
            pass
    with db.session() as s:
        billing = sorted(r.detail["billing"] for r in s.scalars(select(CostEntry)))
    assert billing == ["accepted_then_failed", "rendered"]          # a 2xx is always billed
    try:
        I.submit_render(prompt, provider_key="gpt-image-1", env=FX.ENV, db=db)
        raise AssertionError("an inline provider was deferred")
    except (I.ImagesRefused, I.ImagesNotConfigured):
        pass


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
