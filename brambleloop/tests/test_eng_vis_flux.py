"""ENG-VIS-FLUX: the FLUX 3 provider -- verified contract, spend, caps, QC, provenance, activation.

No network and no spend: every BFL exchange is replayed from recorded response SHAPES
(`tests/fixtures/bfl_flux3/`, built to the official schema read 2026-11-20 -- not live captures)
through a mock transport that replaces `images._post`, `images._get` and the delivery fetch.

Proves:
- the contract module equals the official OpenAPI snapshot and the pricing page's rate card;
- the request builder refuses a seed, a negative prompt, an over-range safety_tolerance and an
  over-bound exact size before any reservation;
- a listing frame that is the wrong size, the wrong shape, not PNG/JPEG or corrupt is rejected
  at generation -- billed, its bytes kept, an audit row written -- and a corrupt download is
  re-fetched (free, bounded) before it is called corrupt;
- every render reserves through the existing path; an exhausted month sends nothing;
- the per-day and per-gallery image caps bite, and the environment can lower them, never raise;
- the provenance record is complete for a framed render and `missing` names what is absent;
- no render without the owner's activation and a key; readiness is UNKNOWN with the exact
  reason and the variable NAME, never its value; the generation job refuses before spending;
- a replacement is not bought while a paid render awaits recovery and re-check;
- each guard, mutated away, is caught by its test (`test_mutations_on_each_guard`).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_eng_vis_flux.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

import _paid_activation as _paid  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import flux_contract as FC  # noqa: E402
from brambleloop.gateway import flux_provenance as FP  # noqa: E402
from brambleloop.gateway import flux_provider as FPR  # noqa: E402
from brambleloop.gateway import flux_qc as Q  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "bfl_flux3"
SHAPES = json.loads((FIX / "response_shapes.json").read_text())
SECRET = "stand-in-not-a-key-7f3a9c"          # never a real key; must never be echoed
ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": SECRET}
CAP_ENVS = (G.DAILY_IMAGE_CAP_ENV, G.GALLERY_IMAGE_CAP_ENV, G.GALLERY_CAD_CAP_ENV)


def _img(w: int, h: int, fmt: str = "PNG", mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    colour = (120, 90, 60, 255) if mode == "RGBA" else (120, 90, 60)
    Image.new(mode, (w, h), colour).save(buf, format=fmt)
    return buf.getvalue()


GOOD = _img(2048, 2048, "JPEG")


def _db(*, activate: bool = True) -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    if activate:
        _paid.activate(db, "flux-3-image")
    return db


def _refs(root: Path, n: int = 2) -> list[str]:
    out = []
    for i in range(n):
        p = root / f"ref_{i}.png"
        p.write_bytes(_img(256 + i, 256))
        out.append(str(p))
    return out


class Replay:
    """The BFL exchange from the recorded shapes: submit, Pending -> Ready, then `delivered`
    (one bytes value per delivery fetch, the last repeating)."""

    def __init__(self, delivered=(GOOD,), polls=("poll_pending", "poll_generating",
                                                  "poll_ready")):
        self.delivered = list(delivered)
        self.polls = list(polls)
        self.posts: list[dict] = []
        self.gets = 0
        self.fetches = 0

    def post(self, url, headers, payload, *, label, timeout):
        assert url == FC.ENDPOINT and FC.AUTH_HEADER in headers
        self.posts.append(json.loads(payload))
        return dict(SHAPES["submit"])

    def get(self, url, headers, *, label, timeout):
        assert url == SHAPES["submit"]["polling_url"]
        self.gets += 1
        return json.loads(json.dumps(SHAPES[self.polls[min(self.gets, len(self.polls)) - 1]]))

    def urlopen(self, url, timeout=None):
        assert str(url).startswith("https://delivery."), url
        self.fetches += 1
        raw = self.delivered[min(self.fetches, len(self.delivered)) - 1]

        class _R(io.BytesIO):
            headers = {"content-type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R(raw)

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


@contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _gen(db, work, *, prompt="a crochet blanket from image 1", size="2048x2048",
         frame_role=Q.LISTING, refs=None, **kw):
    return I.generate(prompt, env=ENV, provider_key="flux-3-image", work_dir=str(work),
                      reference_urls=refs if refs is not None else _refs(Path(work)),
                      size=size, db=db, purpose="test.vis_flux", frame_role=frame_role,
                      prompt_version="flux3-prompt-builder/2.1.1#fixture",
                      product="fixture-blanket@1.0.0", **kw)


def _raises(fn, cls):
    try:
        fn()
    except cls as exc:
        return exc
    raise AssertionError(f"expected {cls.__name__}")


def _costs(db):
    with db.session() as s:
        return list(s.scalars(select(CostEntry)))


def _live_reservations(db):
    with db.session() as s:
        return [r for r in s.scalars(select(SpendReservation)) if r.released_at is None]


# ---- 1. the verified contract, against the official snapshot ---------------------------

def test_contract_equals_the_official_openapi_snapshot():
    snap = json.loads((FIX / "openapi_snapshot.json").read_text())
    f3 = snap["Flux3ImageInputs"]
    assert set(f3["properties"]) == set(FC.REQUEST_FIELDS)
    assert f3["additionalProperties"] is False and f3["required"] == ["prompt"]
    assert "seed" not in f3["properties"] and FC.summary()["seed_supported"] is False
    assert [a for a in f3["aspect_ratio"] if a != "auto"] == list(FC.ASPECT_RATIOS)
    assert f3["resolution"] == list(FC.RESOLUTIONS)
    assert f3["version"] == list(FC.VERSION_VALUES)
    assert f3["safety_tolerance"]["default"] == FC.SAFETY_TOLERANCE_DEFAULT
    # The schema's general 0-7 is narrowed by the errors page to 0-4 for FLUX 3 Image.
    assert FC.SAFETY_TOLERANCE_RANGE[1] <= f3["safety_tolerance"]["maximum"]
    assert "one to 10" in f3["images_description"] and FC.MAX_REFERENCES == 10
    assert str(FC.EXACT_MAX_PIXELS_WITH_REFERENCES) in f3["height_description"]
    assert str(FC.EXACT_MAX_PIXELS) in f3["height_description"]
    assert snap["StatusResponse"] == list(FC.STATUSES)
    assert snap["AsyncResponse"]["required"] == list(FC.SUBMIT_REQUIRED)
    assert set(FC.SUBMIT_OPTIONAL) <= set(snap["AsyncResponse"]["properties"])
    assert snap["ResultResponse"]["required"] == list(FC.RESULT_REQUIRED)
    assert snap["security_scheme"] == {"type": "apiKey", "in": "header", "name": FC.AUTH_HEADER}
    # The snapshot names BFL's global server; requests go to the regional BFL API host
    # (D-ENG-BFL-REGIONAL-HOST). The path is the contract; the host is one of BFL's own.
    assert "/v1/flux-3-image" in snap["paths"] and FC.HOST.removeprefix("https://") in FC.BFL_HOSTS
    assert any(str(s_).rstrip("/").endswith(".bfl.ai") for s_ in snap["servers"])
    # The gateway's provider row and price table are the contract's.
    p = I.BY_KEY["flux-3-image"]
    assert p.endpoint == FC.ENDPOINT and p.reference_images == FC.MAX_REFERENCES
    assert I.BFL3_FIELDS == FC.REQUEST_FIELDS
    assert tuple(I.BFL3_ASPECT_RATIOS) == FC.ASPECT_RATIOS


def test_prices_equal_the_official_rate_card():
    card = json.loads((FIX / "pricing_rate_card.json").read_text())
    rates = card["/v1/flux-3-image"]
    by_tier = {"768sq": "tier768", "1k": "tier1k", "1.5k": "tier1_5k", "2k": "tier2k",
               "4k": "tier4k"}
    assert len(by_tier) == 5 and set(by_tier) == set(FC.CREDITS_PER_IMAGE)
    for tier, field in by_tier.items():
        assert FC.CREDITS_PER_IMAGE[tier] == rates[field]
        assert abs(I.BFL3_TIER_USD[tier] - rates[field] * card["usd_per_credit"]) < 1e-9
        assert abs(FC.usd_per_image(tier) - I.BFL3_TIER_USD[tier]) < 1e-9
    assert FC.SOURCES
    for source in FC.SOURCES.values():
        assert source["url"].startswith("https://") and source["accessed"] == "2026-11-20"


def test_recorded_response_shapes_validate_and_classify():
    FC.validate_submit(SHAPES["submit"])
    assert FC.classify_result(SHAPES["poll_pending"]) == "in_progress"
    assert FC.classify_result(SHAPES["poll_generating"]) == "in_progress"
    assert FC.classify_result(SHAPES["poll_ready"]) == "ready"
    for k in ("poll_request_moderated", "poll_content_moderated", "poll_error",
              "poll_task_not_found"):
        assert FC.classify_result(SHAPES[k]) == "terminal", k
        assert I.classify_poll(SHAPES[k]) == "terminal", k
    assert FC.moderation_reasons(SHAPES["poll_request_moderated"]) == ["Sexual Content"]
    assert FC.classify_result({"id": "x", "status": "Brand New"}) == "terminal"
    _raises(lambda: FC.validate_submit({"id": "x"}), FC.ContractViolation)
    _raises(lambda: FC.validate_submit({**SHAPES["submit"], "cost": -1}), FC.ContractViolation)


def test_the_builder_refuses_what_the_contract_does_not_offer_before_any_spend():
    db = _db()
    with tempfile.TemporaryDirectory() as work, Replay() as t:
        for extra in ({"seed": 42}, {"negative_prompt": "blur"}, {"safety_tolerance": 5},
                      {"output_format": "png"}, {"width": 2048}):
            exc = _raises(lambda: _gen(db, work, extra_fields=extra), I.ImagesRefused)
            assert "contract" in str(exc) or "unknown" in str(exc).lower(), (extra, exc)
        # an exact size over the 4 MP bound that applies with reference images
        _raises(lambda: _gen(db, work, extra_fields={"width": 2500, "height": 2500}),
                I.ImagesRefused)
    assert t.posts == [] and _costs(db) == [] and _live_reservations(db) == []
    body = FC.validate_request({"prompt": "x", "images": ["a"], "aspect_ratio": "1:1",
                                "resolution": "2k", "grounding": False})
    assert body["resolution"] == "2k"


# ---- 2. a good render: reserved, billed once, QC passed, provenance complete -----------

def test_a_listing_frame_reserves_bills_once_passes_qc_and_carries_complete_provenance():
    db = _db()
    with tempfile.TemporaryDirectory() as work, Replay() as t:
        out = _gen(db, work)
        assert Path(out["path"]).read_bytes() == GOOD
    body = t.posts[0]
    assert body["aspect_ratio"] == "1:1" and body["resolution"] == "2k"
    assert body["grounding"] is False and "seed" not in body
    assert out["generation_check"]["ok"] is True and out["generation_check"]["px"] == [2048,
                                                                                        2048]
    (cost,) = _costs(db)
    cad = round(0.100 * I.USD_TO_CAD, 6)
    assert abs(cost.amount_cad - cad) < 1e-9 and out["cost_entry_id"] == cost.id
    assert _live_reservations(db) == []
    prov = out["provenance"]
    assert FP.missing(prov) == [] and out["provenance_missing"] == []
    assert prov["model"] == "flux-3-image" and prov["receipt_id"] == "fixture-task-0001"
    assert prov["prompt_version"] == "flux3-prompt-builder/2.1.1#fixture"
    assert [r["position"] for r in prov["references"]] == [1, 2]
    assert all(len(r["sha256"]) == 64 and r["transmitted"] for r in prov["references"])
    assert prov["seed_supported"] is False and prov["seed"] is None
    assert prov["provider_cost_credits"] == 10.0 and abs(prov["cost_cad"] - cad) < 1e-9
    assert prov["output_px"] == [2048, 2048] and prov["output_format"] == "JPEG"
    assert prov["disclosure"].startswith("AI-generated")
    spend = G.gallery_spend(db, prov["gallery"])
    assert spend["images"] == 1 and abs(spend["cad"] - cad) < 1e-6


def test_laura_canonical_references_are_marked_by_fingerprint_in_provenance():
    from brambleloop.visual import canonical, conditioning

    db = _db()
    laura = [str(canonical.reference_file(f)) for f in conditioning.FRAME_ORDER]
    with tempfile.TemporaryDirectory() as work, Replay():
        out = _gen(db, work, refs=laura + _refs(Path(work), 1))
    prov = out["provenance"]
    assert prov["laura_canonical_positions"] == [1, 2, 3]
    want = [canonical.CURRENT_REFERENCE_HASHES[f] for f in conditioning.FRAME_ORDER]
    assert [r["sha256"] for r in prov["references"][:3]] == want
    assert prov["references"][3]["canonical_laura"] is None


def test_provenance_missing_names_each_absent_field():
    db = _db()
    with tempfile.TemporaryDirectory() as work, Replay():
        out = _gen(db, work)
    prov = dict(out["provenance"])
    for field in ("receipt_id", "prompt_version", "cost_cad", "output_sha256", "gallery"):
        broken = {**prov, field: ""}
        assert field in FP.missing(broken), field
    broken = {**prov, "references": [{**prov["references"][0], "transmitted": False}]}
    assert "references[0].transmitted" in FP.missing(broken)
    assert "references" in FP.missing({**prov, "references": []})
    assert not FP.complete({})


# ---- 3. generation-time QC -------------------------------------------------------------

def _rejected(db, work, delivered, **kw):
    with Replay(delivered=delivered) as t:
        exc = _raises(lambda: _gen(db, work, **kw), I.ImagesRejectedAtGeneration)
    return exc, t


def test_wrong_resolution_is_rejected_at_generation_billed_and_kept():
    db = _db()
    with tempfile.TemporaryDirectory() as work:
        exc, t = _rejected(db, work, [_img(1024, 1024, "JPEG")])
        assert exc.reasons == [Q.BELOW_RESOLUTION]
        assert Path(exc.result["path"]).read_bytes() == _img(1024, 1024, "JPEG")
    assert len(t.posts) == 1 and t.fetches == 1
    (cost,) = _costs(db)
    assert exc.result["cost_entry_id"] == cost.id and _live_reservations(db) == []
    with db.session() as s:
        (row,) = list(s.scalars(select(AuditLog).where(
            AuditLog.action == I.GENERATION_REJECTED_ACTION)))
        assert row.detail["reasons"] == [Q.BELOW_RESOLUTION] and row.detail["cost_entry_id"]


def test_wrong_aspect_for_the_frame_role_is_rejected():
    db = _db()
    with tempfile.TemporaryDirectory() as work:
        exc, _ = _rejected(db, work, [_img(2400, 2048, "JPEG")])
    assert exc.reasons == [Q.WRONG_ASPECT]


def test_wrong_format_and_transparency_are_rejected():
    db = _db()
    with tempfile.TemporaryDirectory() as work:
        exc, _ = _rejected(db, work, [_img(2048, 2048, "WEBP")])
        assert exc.reasons == [Q.WRONG_FORMAT]
    clear = io.BytesIO()
    Image.new("RGBA", (2048, 2048), (1, 2, 3, 0)).save(clear, format="PNG")
    v = Q.inspect(clear.getvalue(), requested_size="2048x2048", frame_role=Q.LISTING)
    assert v["reasons"] == [Q.NOT_OPAQUE]


def test_a_corrupt_download_is_refetched_free_then_passes():
    db = _db()
    with tempfile.TemporaryDirectory() as work, Replay(delivered=[GOOD[:500], GOOD]) as t:
        out = _gen(db, work)
    assert t.fetches == 2 and len(t.posts) == 1 and len(_costs(db)) == 1
    assert out["generation_check"]["ok"] and len(out["generation_check"]["refetches"]) == 1


def test_persistently_corrupt_bytes_are_rejected_after_bounded_refetches():
    db = _db()
    with tempfile.TemporaryDirectory() as work:
        exc, t = _rejected(db, work, [b"\xff\xd8 not a jpeg"])
    assert exc.reasons == [Q.CORRUPT_BYTES]
    assert t.fetches == 1 + I.CORRUPT_REFETCHES and len(t.posts) == 1 and len(_costs(db)) == 1


def test_an_intermediate_frame_has_its_own_floor_and_an_unframed_render_is_unchecked():
    db = _db()
    with tempfile.TemporaryDirectory() as work, Replay(delivered=[_img(1024, 1024, "JPEG")]):
        out = _gen(db, work, prompt="identity anchor", size="1024x1024",
                   frame_role=Q.INTERMEDIATE)
        assert out["generation_check"]["ok"]
    with tempfile.TemporaryDirectory() as work, Replay(delivered=[_img(64, 64, "JPEG")]):
        out = _gen(db, work, prompt="bench", size="1024x1024", frame_role=None)
        assert "generation_check" not in out
    with tempfile.TemporaryDirectory() as work, Replay() as t:
        _raises(lambda: _gen(db, work, frame_role="hero"), I.ImagesRefused)
    assert t.posts == [] and _live_reservations(db) == []


def test_terminal_statuses_from_the_recorded_shapes_stop_and_bill_once():
    for status in ("poll_request_moderated", "poll_content_moderated", "poll_error"):
        db = _db()
        with tempfile.TemporaryDirectory() as work, Replay(polls=(status,)) as t:
            _raises(lambda: _gen(db, work), I.ImagesRefused)
        assert len(t.posts) == 1 and t.gets == 1 and t.fetches == 0, status
        (cost,) = _costs(db)
        assert cost.detail["billing"] == "accepted_then_failed", status


# ---- 4. spend: reservation, refusal, caps ----------------------------------------------

def test_an_exhausted_month_sends_nothing():
    db = _db()
    with _env(BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD="0.05"), \
            tempfile.TemporaryDirectory() as work, Replay() as t:
        _raises(lambda: _gen(db, work), gw.BudgetExceeded)
    assert t.posts == [] and _costs(db) == [] and _live_reservations(db) == []


def test_the_daily_image_cap_bites_and_can_only_be_lowered():
    db = _db()
    with _env(**{G.DAILY_IMAGE_CAP_ENV: "1"}), tempfile.TemporaryDirectory() as work, \
            Replay() as t:
        _gen(db, work, prompt="first")
        exc = _raises(lambda: _gen(db, work, prompt="second"), I.ImagesGateRefused)
        assert exc.code == "daily_image_cap"
    assert len(t.posts) == 1 and len(_costs(db)) == 1
    for raw in ("1000", "-3", "nan", "two"):
        with _env(**{G.DAILY_IMAGE_CAP_ENV: raw}):
            assert G.image_caps()["daily_images"] == G.DAILY_IMAGE_CAP, raw
    with _env(**{G.GALLERY_CAD_CAP_ENV: "9999"}):
        assert G.image_caps()["gallery_cad"] == G.GALLERY_CAD_CAP


def test_the_per_gallery_image_and_cad_caps_bite_inside_a_gallery_only():
    db = _db()
    with _env(**{G.GALLERY_IMAGE_CAP_ENV: "1"}), tempfile.TemporaryDirectory() as work, \
            Replay() as t:
        with G.gallery_scope("imgprod:fixture@1#run1"):
            _gen(db, work, prompt="frame one")
            exc = _raises(lambda: _gen(db, work, prompt="frame two"), I.ImagesGateRefused)
            assert exc.code == "gallery_image_cap"
        with G.gallery_scope("imgprod:fixture@1#run2"):
            _gen(db, work, prompt="another gallery")
        _gen(db, work, prompt="outside any gallery")         # bounded by the day cap only
    assert len(t.posts) == 3
    with _env(**{G.GALLERY_CAD_CAP_ENV: "0.20"}), tempfile.TemporaryDirectory() as work, \
            Replay():
        with G.gallery_scope("imgprod:fixture@1#run3"):
            _gen(db, work, prompt="cad one")
            exc = _raises(lambda: _gen(db, work, prompt="cad two"), I.ImagesGateRefused)
            assert exc.code == "gallery_cad_cap"
    spend = G.gallery_spend(db, "imgprod:fixture@1#run1")
    assert spend["images"] == 1 and spend["by_provider"]["flux-3-image"]["images"] == 1
    assert G.is_gallery_key("imgprod:x") and not G.is_gallery_key("shared")
    assert not G.is_gallery_key("job:7") and not G.is_gallery_key("product:x")


# ---- 5. activation and readiness -------------------------------------------------------

def test_no_call_without_the_owner_activation():
    db = _db(activate=False)
    with tempfile.TemporaryDirectory() as work, Replay() as t:
        exc = _raises(lambda: _gen(db, work), I.ImagesGateRefused)
    assert exc.code == G.NOT_ACTIVATED and t.posts == [] and _costs(db) == []
    assert _live_reservations(db) == []


def test_readiness_is_unknown_with_the_exact_reason_and_never_prints_the_key():
    db = _db(activate=False)
    no_key = FPR.readiness(db, env={})
    assert no_key["state"] == FPR.UNKNOWN and no_key["code"] == FPR.NO_KEY
    assert no_key["key_env_var"] == "BRAMBLELOOP_IMAGE_KEY_BFL" == I.key_var("bfl")
    assert no_key["spends"] == 0.0
    no_act = FPR.readiness(db, env=ENV)
    assert no_act["state"] == FPR.UNKNOWN and no_act["code"] == G.NOT_ACTIVATED
    assert no_act["key_present"] is True
    _paid.activate(db, "flux-3-image", G.GENERATION)
    ready = FPR.readiness(db, env=ENV)
    assert ready["state"] == FPR.READY and ready["code"] == ""
    for report in (no_key, no_act, ready, FPR.env_var_report(ENV)):
        assert SECRET not in json.dumps(report, default=str)
        assert SECRET[:8] not in json.dumps(report, default=str)
    _raises(lambda: FPR.require_ready(_db(activate=False), env=ENV), FPR.FluxNotReady)


def test_the_generation_job_refuses_before_any_spend_without_key_or_activation():
    from brambleloop.creative import flux3_generator as FG

    class PaidFake:
        provider_key = "flux-3-image"
        reference_limit = 10
        calls = 0

        def __call__(self, *a, **k):
            PaidFake.calls += 1
            raise AssertionError("the renderer must not be reached")

    for db, env in ((_db(activate=False), ENV), (_db(), {})):
        g = FG.Flux3Generator(db, renderer=PaidFake())
        g._bind = lambda refs: (None, "fixture", "1.0.0", "a" * 64)
        with _env(BRAMBLELOOP_IMAGE_KEY_BFL=env.get("BRAMBLELOOP_IMAGE_KEY_BFL")):
            exc = _raises(lambda: g._generate(stage="product_generation",
                                              role=FG.ANCHOR_ROLE, brief="", references=[],
                                              outfit=None, attempt=1, repair=None),
                          FG.GeneratorRefused)
        assert "UNKNOWN" in str(exc) and SECRET not in str(exc)
        with db.session() as s:
            assert list(s.scalars(select(SpendReservation))) == []
    assert PaidFake.calls == 0


# ---- 6. never buy a replacement before recovery and re-check ---------------------------

def test_a_rejected_render_is_rechecked_before_a_replacement_and_recovered_if_it_passes():
    gallery = "imgprod:fixture@1#recover"
    db = _db()
    with tempfile.TemporaryDirectory() as work:
        with G.gallery_scope(gallery):
            exc, _ = _rejected(db, work, [_img(1024, 1024, "JPEG")])
        got = FPR.replacement_allowed(db, gallery=gallery)
        assert got["allowed"] and got["rechecked"][0]["outcome"] == "CONFIRMED"
        assert FPR.replacement_allowed(db, gallery=gallery)["rechecked"] == []   # once
        with G.gallery_scope(gallery):
            exc, _ = _rejected(db, work, [_img(1024, 1024, "JPEG")], prompt="second try")
        Path(exc.result["path"]).write_bytes(GOOD)           # the kept bytes are fine after all
        got = FPR.replacement_allowed(db, gallery=gallery)
        assert not got["allowed"] and got["recovered"][0]["outcome"] == "RECOVERED"
        _raises(lambda: FPR.require_replacement_allowed(db, gallery=gallery),
                FPR.ReplacementRefused)
    other = "imgprod:fixture@1#gone"
    with tempfile.TemporaryDirectory() as work:
        with G.gallery_scope(other):
            exc, _ = _rejected(db, work, [_img(1024, 1024, "JPEG")], prompt="gone")
    got = FPR.replacement_allowed(db, gallery=other)                # work dir removed
    assert got["allowed"] and got["rechecked"][0]["outcome"] == "BYTES_MISSING"


def test_open_motif_recoveries_block_a_replacement():
    db = _db()
    # The real table (publish.motif_backlog, now registered on the shared metadata).
    from brambleloop.publish import motif_backlog as MB

    MB.ensure_tables(db)
    with db.session() as s:
        for i, (slug, state) in enumerate((("fixture", "QUEUED_BUDGET"), ("other", "BLOCKED"),
                                           ("fixture", "PASSED"))):
            s.add(MB.MotifRecovery(render_key=f"rk-{i}", source_action="test", audit_id=i,
                                   slug=slug, version="1.0.0", image_sha256="0" * 64,
                                   refusal_code="test", state=state))
    got = FPR.replacement_allowed(db, gallery="imgprod:none", slug="fixture")
    assert not got["allowed"] and got["open_motif_recoveries"] == 1
    assert FPR.replacement_allowed(db, gallery="imgprod:none", slug="third")["allowed"]


# ---- 7. mutations on each guard --------------------------------------------------------

@contextmanager
def _patched(obj, name, value):
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


MUTANTS = {
    "contract validation removed": (
        lambda: _patched(FC, "validate_request", lambda body: body),
        test_the_builder_refuses_what_the_contract_does_not_offer_before_any_spend),
    "QC always passes": (
        lambda: _patched(Q, "inspect", lambda raw, **k: {"ok": True, "reasons": [],
                                                          "px": [2048, 2048],
                                                          "format": "JPEG", "role": "listing"}),
        test_wrong_resolution_is_rejected_at_generation_billed_and_kept),
    "aspect check removed": (
        lambda: _patched(Q, "ASPECT_TOLERANCE", 10.0),
        test_wrong_aspect_for_the_frame_role_is_rejected),
    "no corrupt re-fetch": (
        lambda: _patched(I, "CORRUPT_REFETCHES", 0),
        test_a_corrupt_download_is_refetched_free_then_passes),
    "image caps removed": (
        lambda: _patched(G, "_image_cap_refusal", lambda *a, **k: None),
        test_the_daily_image_cap_bites_and_can_only_be_lowered),
    "gallery cap ignores galleries": (
        lambda: _patched(G, "is_gallery_key", lambda key: False),
        test_the_per_gallery_image_and_cad_caps_bite_inside_a_gallery_only),
    "caps may be raised": (
        lambda: _patched(G, "_lower_only", lambda name, default, cast:
                         cast(os.environ.get(name) or default)),
        test_the_daily_image_cap_bites_and_can_only_be_lowered),
    "readiness ignores the key": (
        lambda: _patched(FPR, "key_present", lambda env=None: True),
        test_readiness_is_unknown_with_the_exact_reason_and_never_prints_the_key),
    "provenance never incomplete": (
        lambda: _patched(FP, "missing", lambda record: []),
        test_provenance_missing_names_each_absent_field),
    "no recheck before replacement": (
        lambda: _patched(FPR, "_rejections", lambda db, gallery: []),
        test_a_rejected_render_is_rechecked_before_a_replacement_and_recovered_if_it_passes),
    "motif backlog ignored": (
        lambda: _patched(FPR, "_open_motif_recoveries", lambda db, slug: 0),
        test_open_motif_recoveries_block_a_replacement),
}


def test_mutations_on_each_guard():
    survived = []
    for name, (mutate, test) in MUTANTS.items():
        try:
            with mutate():
                test()
        except Exception:  # noqa: BLE001 - the test caught the mutant (assertion or crash)
            continue
        survived.append(name)
    assert not survived, f"mutants survived: {survived}"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            traceback.print_exc()
            print(f"FAIL {name}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
