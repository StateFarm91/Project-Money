"""W4-FLUXAPI: the BFL adapter transmits every reference, prices before it calls, and keeps bytes.

Every outbound request is captured by a mock transport (`images._post`, `images._get` and the
delivery-URL fetch are replaced); nothing here touches the network or spends money.

Proves:
- the defect: until 2026-10-19 the BFL dialect sent only `refs[0]`, as `image_prompt` (a field
  FLUX.2 does not define). Now FLUX.2 [pro] gets `input_image` .. `input_image_N` and FLUX 3
  Image gets `images: [...]`, every reference, in order;
- more references than the documented limit (8 / 10) are refused before any spend;
- the conditioning receipt lists every transmitted reference's sha256 and field;
- the documented price is reserved before the POST, and an exhausted budget sends nothing;
- attempts are bounded: one POST per render, a bounded poll, terminal statuses stop it;
- the result bytes are stored and fingerprinted at once, with the provider's receipt fields.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_fluxapi.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, SpendReservation  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402

ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": "stand-in-not-a-key"}
OUT_PNG = b"\x89PNG\r\n\x1a\n stand-in render bytes"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _refs(n: int, root: Path, px: int = 512) -> list[str]:
    out = []
    for i in range(n):
        buf = io.BytesIO()
        Image.new("RGB", (px, px), (i * 20 % 255, 80, 120)).save(buf, format="PNG")
        p = root / f"ref_{i}.png"
        p.write_bytes(buf.getvalue())
        out.append(str(p))
    return out


class Transport:
    """Mock BFL: captures every POST body, answers with a job, then a Ready poll and bytes."""

    def __init__(self, *, statuses=("Pending", "Reasoning", "Generating", "Ready"),
                 post_error: Exception | None = None, events: list | None = None):
        self.posts: list[dict] = []
        self.gets = 0
        self.fetches = 0
        self.statuses = list(statuses)
        self.post_error = post_error
        self.events = events if events is not None else []

    def post(self, url, headers, payload, *, label, timeout):
        self.events.append("post")
        self.posts.append({"url": url, "headers": dict(headers), "body": json.loads(payload)})
        if self.post_error:
            raise self.post_error
        return {"id": "task-123", "polling_url": "https://api.bfl.ai/v1/get_result?id=task-123",
                "cost": 4.8, "input_mp": 0.75, "output_mp": 1.05}

    def get(self, url, headers, *, label, timeout):
        self.gets += 1
        status = self.statuses[min(self.gets - 1, len(self.statuses) - 1)]
        body = {"id": "task-123", "status": status}
        if status == "Ready":
            body["result"] = {"sample": "https://delivery.eu.bfl.ai/x.png?se=soon",
                              "prompt": "expanded prompt", "duration": 41.5}
        return body

    def urlopen(self, url, timeout=None):
        self.fetches += 1
        assert str(url).startswith("https://delivery."), url

        class _R(io.BytesIO):
            headers = {"content-type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R(OUT_PNG)

    def __enter__(self):
        import urllib.request

        self._saved = (I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS)
        I._post, I._get = self.post, self.get
        urllib.request.urlopen = self.urlopen
        I.BFL_POLL_SECONDS = 0.0
        return self

    def __exit__(self, *exc):
        import urllib.request

        I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS = self._saved
        return False


def _gen(transport, refs, *, provider="flux-3-image", db=None, size="1024x1024", **kw):
    with transport, tempfile.TemporaryDirectory() as work:
        out = I.generate("Laura wears the cardigan from image 4", env=ENV, provider_key=provider,
                         reference_urls=refs, work_dir=work, db=db or _db(), size=size,
                         purpose="test.fluxapi", **kw)
        out["_stored_bytes"] = Path(out["path"]).read_bytes()
        return out


def _reservations(db):
    with db.session() as s:
        rows = list(s.scalars(select(SpendReservation)))
        for r in rows:
            s.expunge(r)
        return rows


# ------------------------------------------------------------------------------------------
def test_flux3_is_registered_with_documented_endpoint_limit_and_price():
    p = I.BY_KEY["flux-3-image"]
    assert p.endpoint == "https://api.bfl.ai/v1/flux-3-image" and p.model == "flux-3-image"
    assert p.dialect == "bfl3" and p.reference_images == 10 and p.supports_lock
    assert p.usd_per_image == 0.048 == I.BFL3_TIER_USD["1k"]
    assert I.key_for("flux-3-image", ENV) == ENV["BRAMBLELOOP_IMAGE_KEY_BFL"]
    assert I.BY_KEY["flux-2-pro"].reference_images == 8


def test_flux3_transmits_every_reference_in_images_in_order():
    with tempfile.TemporaryDirectory() as d:
        refs = _refs(3, Path(d))
        t = Transport()
        out = _gen(t, refs)
        (sent,) = t.posts
        body = sent["body"]
        assert sent["url"] == "https://api.bfl.ai/v1/flux-3-image"
        assert sent["headers"] == {"x-key": ENV["BRAMBLELOOP_IMAGE_KEY_BFL"]}
        expect = [base64.standard_b64encode(Path(r).read_bytes()).decode() for r in refs]
        assert body["images"] == expect                      # all three, in order
        assert set(body) <= I.BFL3_FIELDS                    # no field FLUX 3 would 422
        assert body["aspect_ratio"] == "1:1" and body["resolution"] == "1k"
        assert body["grounding"] is False
        assert "image_prompt" not in body and "seed" not in body
        rec = out["conditioning"]
        assert rec["requested"] == rec["transmitted"] == 3 and rec["proven"] is True
        assert rec["reference_sha256s"] == [hashlib.sha256(Path(r).read_bytes()).hexdigest()
                                            for r in refs]
        assert [r["field"] for r in rec["references"]] == ["images[0]", "images[1]",
                                                           "images[2]"]


def test_flux2_transmits_every_reference_in_documented_input_image_fields():
    with tempfile.TemporaryDirectory() as d:
        refs = _refs(8, Path(d), px=256)
        t = Transport()
        out = _gen(t, refs, provider="flux-2-pro")
        body = t.posts[0]["body"]
        fields = ["input_image"] + [f"input_image_{i}" for i in range(2, 9)]
        for field, ref in zip(fields, refs):
            assert body[field] == base64.standard_b64encode(Path(ref).read_bytes()).decode()
        assert "image_prompt" not in body                    # the FLUX1.1 field, never again
        assert out["conditioning"]["transmitted"] == 8
        assert [r["field"] for r in out["conditioning"]["references"]] == fields


def test_the_old_defect_shape_is_gone_at_the_request_builder():
    """The captured payload the defect produced: one reference, `image_prompt`. Not any more."""
    with tempfile.TemporaryDirectory() as d:
        refs = _refs(3, Path(d))
        for key in ("flux-2-pro", "flux-3-image"):
            _, _, payload = I._request_for(I.BY_KEY[key], "k", "p", refs, "1024x1024")
            rec = I.conditioning_receipt(I.BY_KEY[key], refs, payload)
            assert rec["transmitted"] == 3 and rec["proven"], (key, rec)
            assert b"image_prompt" not in payload


def test_more_references_than_the_documented_limit_are_refused_before_any_spend():
    for key, limit in (("flux-3-image", 10), ("flux-2-pro", 8)):
        with tempfile.TemporaryDirectory() as d:
            refs = _refs(limit + 1, Path(d), px=256)
            db = _db()
            t = Transport()
            try:
                _gen(t, refs, provider=key, db=db)
                raise AssertionError(f"{key}: {limit + 1} references must be refused")
            except I.ImagesRefused as exc:
                assert f"at most {limit}" in str(exc)
            assert t.posts == [] and _reservations(db) == []
            # Exactly at the limit goes through, every reference carried.
            out = _gen(Transport(), refs[:limit], provider=key)
            assert out["conditioning"]["transmitted"] == limit


def test_the_documented_price_is_reserved_before_the_post():
    events: list = []
    real = I.reserve_render

    def spy(*a, **k):
        events.append(("reserve", k.get("estimate_cad")))
        return real(*a, **k)

    I.reserve_render = spy
    try:
        db = _db()
        with tempfile.TemporaryDirectory() as d:
            out = _gen(Transport(events=events), _refs(2, Path(d)), db=db, size="1536x1024")
    finally:
        I.reserve_render = real
    assert events[0][0] == "reserve" and events[1] == "post", events
    cad_15k = round(I.BFL3_TIER_USD["1.5k"] * I.USD_TO_CAD, 6)
    assert events[0][1] == cad_15k                           # 1536x1024 is the 1.5k tier
    assert out["conditioning"]["price"]["tier"] == "1.5k"
    (row,) = _reservations(db)
    assert abs(row.amount_cad - cad_15k) < 1e-9 and abs(row.actual_cad - cad_15k) < 1e-9
    with db.session() as s:
        entry = s.scalar(select(CostEntry).where(CostEntry.kind == routing.IMAGE_COST_KIND))
        assert abs(entry.amount_cad - cad_15k) < 1e-9


def test_flux2_reservation_uses_the_megapixel_formula_with_inputs():
    with tempfile.TemporaryDirectory() as d:
        refs = _refs(3, Path(d), px=1024)                    # 3 x 1 MP of input
        est = I.render_estimate_usd(I.BY_KEY["flux-2-pro"], "1024x1024", refs)
        assert abs(est["usd"] - (0.03 + 3 * 0.015)) < 1e-9, est
        assert I.render_estimate_usd(I.BY_KEY["flux-2-pro"], "1024x1024")["usd"] == 0.03
        # Never below the table price, for any provider.
        for p in I.PROVIDERS:
            assert I.render_estimate_usd(p)["usd"] >= p.usd_per_image


def test_no_call_when_the_budget_is_exhausted():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind=routing.IMAGE_COST_KIND,
                        amount_cad=gw.monthly_ceiling_cad() - 0.01, purpose="renders"))
    t = Transport()
    with tempfile.TemporaryDirectory() as d:
        try:
            _gen(t, _refs(1, Path(d)), db=db)
            raise AssertionError("an exhausted month must refuse the render")
        except gw.BudgetExceeded:
            pass
    assert t.posts == [] and t.gets == 0


def test_bounded_attempts_one_post_and_a_bounded_poll():
    # A transient failure on submit is one POST, not a retry loop.
    t = Transport(post_error=TransientError("bfl 503"))
    with tempfile.TemporaryDirectory() as d:
        try:
            _gen(t, _refs(1, Path(d)))
            raise AssertionError("must raise")
        except TransientError:
            pass
    assert len(t.posts) == 1
    # A job that never finishes is polled at most BFL_POLL_ATTEMPTS times.
    t = Transport(statuses=("Generating",))
    saved = I.BFL_POLL_ATTEMPTS
    I.BFL_POLL_ATTEMPTS = 7
    try:
        with tempfile.TemporaryDirectory() as d:
            try:
                _gen(t, _refs(1, Path(d)))
                raise AssertionError("must time out")
            except TransientError:
                pass
    finally:
        I.BFL_POLL_ATTEMPTS = saved
    assert len(t.posts) == 1 and t.gets == 7
    assert 150 * 2.0 >= 216                                  # owner's slowest render fits


def test_documented_terminal_statuses_stop_the_poll_at_once():
    for status in ("Request Moderated", "Content Moderated", "Error", "Task not found",
                   "No Card Generated"):
        t = Transport(statuses=("Pending", status))
        db = _db()
        with tempfile.TemporaryDirectory() as d:
            try:
                _gen(t, _refs(1, Path(d)), db=db)
                raise AssertionError(status)
            except I.ImagesRefused as exc:
                assert status.lower().replace(" ", "_") in str(exc)
        assert t.gets == 2, (status, t.gets)
        # Accepted then failed: billed, never released as free.
        with db.session() as s:
            entry = s.scalar(select(CostEntry).where(CostEntry.kind == routing.IMAGE_COST_KIND))
            assert entry.detail["billing"] == "accepted_then_failed"


def test_result_bytes_are_stored_immediately_and_fingerprinted_with_provider_receipt():
    t = Transport()
    with tempfile.TemporaryDirectory() as d:
        out = _gen(t, _refs(2, Path(d)))
    assert t.fetches == 1 and out["_stored_bytes"] == OUT_PNG
    assert out["sha256"] == hashlib.sha256(OUT_PNG).hexdigest()
    pr = out["provider_receipt"]
    assert pr["id"] == pr["task_id"] == "task-123" and pr["cost"] == 4.8
    assert pr["input_mp"] == 0.75 and pr["output_mp"] == 1.05 and pr["duration_s"] == 41.5
    assert pr["seed"] is None                                # FLUX 3 does not return one
    assert pr["expanded_prompt_sha256"] == hashlib.sha256(b"expanded prompt").hexdigest()
    assert out["model"] == "flux-3-image"


def test_a_503_poll_with_a_status_body_is_read_not_retried_blind():
    import urllib.error

    class _Resp(io.BytesIO):
        pass

    def boom(request, timeout=None):
        raise urllib.error.HTTPError("u", 503, "x", {}, _Resp(b'{"status": "Error"}'))

    import urllib.request
    saved = urllib.request.urlopen
    urllib.request.urlopen = boom
    try:
        body = I._get("https://api.bfl.ai/v1/get_result?id=1", {}, label="t", timeout=1)
    finally:
        urllib.request.urlopen = saved
    assert body == {"status": "Error"}


def test_aspect_and_tier_mapping_and_unknown_fields():
    assert I.bfl3_aspect("1024x1536") == "2:3" and I.bfl3_tier("1024x1536") == "1.5k"
    assert I.bfl3_tier("768x768") == "768sq" and I.bfl3_tier("2048x2048") == "2k"
    assert I.bfl3_tier("4096x4096") == "4k"
    try:
        I.bfl3_aspect("1000x333")
        raise AssertionError("an undocumented ratio must be refused")
    except I.ImagesRefused:
        pass
    try:
        I._request_for(I.BY_KEY["flux-3-image"], "k", "p", [], "1024x1024",
                       {"seed": 42})
        raise AssertionError("seed is not a FLUX 3 field")
    except I.ImagesRefused as exc:
        assert "seed" in str(exc)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
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
    sys.exit(bool(failures))
