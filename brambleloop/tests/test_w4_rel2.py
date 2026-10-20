"""W4-REL2: the a25a377 security findings (M1, L1, L2, I2, I3) and October's model-spend waste.

Every test drives the real code on a temp database. Sockets are refused; nothing calls Etsy
or a model provider. Fakes stand in for the provider and record what they were asked.

  A-M1  a refusal flood grows one counter row per reason, never one audit row per request;
        `summary` aggregates refusals in SQL
  A-L1  a body over the cap is refused on Content-Length or mid-stream, never buffered whole
  A-L2  a non-ASCII signature header is a clean bad_signature refusal, not a 500
  A-I2  VISROLE's lighter path cannot be chosen by a model or a request (pinned)
  A-I3  attribution evidence is capped
  B1    one seasonal tournament per (pod, arena, target event, ISO week), shared by the group
  B2    concept_field@3 names the motif grammar and the silhouette qualifiers; selection
        picks the best shortlisted concept the free #108/#110 gates pass; the gates are unchanged
  B3    each arena's brief walk resumes where the last run stopped
  B4    construction_reading: a refused reading is recorded and not re-bought; one
        department's depiction refusal no longer stops every department's decomposition
  B5    gallery_observation asks for structured output (json_schema), not prose

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_rel2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import asyncio
import base64
import json
import os
import socket
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="w4_rel2_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the REL2 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, MjsMissionEvent  # noqa: E402
from brambleloop.integrations import etsy_webhooks as wh  # noqa: E402

NOW = datetime.now(timezone.utc)
SECRET = "whsec_" + base64.b64encode(b"rel2-test-signing-key-32-bytes!!").decode()
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/rel2_{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _delivery(*, wid="msg_1", at=None, body=None):
    body = body if body is not None else json.dumps(
        {"event_type": "order.paid", "shop_id": "555",
         "resource_url": "https://openapi.etsy.com/v3/application/shops/555/receipts/1"}
    ).encode()
    ts = str(int((at or NOW).timestamp()))
    return ({"webhook-id": wid, "webhook-timestamp": ts,
             "webhook-signature": wh.sign(SECRET, wid, ts, body)}, body)


# ---------------------------------------------------------------------------
# A-M1


def test_m1_a_refusal_flood_is_counted_not_stored_per_request():
    db = _db()
    for _ in range(500):
        status, got = wh.receive(db, {}, b"{}", secret="", now=NOW)
        assert (status, got["reason"]) == (503, "not_configured")
    for _ in range(40):
        wh.receive(db, {"webhook-id": "x"}, b"{}", secret=SECRET, now=NOW)
    with db.session() as s:
        counters = dict(s.execute(select(wh.EtsyWebhookRefusal.reason,
                                         wh.EtsyWebhookRefusal.count)).all())
        sampled = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == wh.REFUSAL_SAMPLE_ACTION))
        legacy = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == wh.REFUSED_ACTION))
    assert counters == {"not_configured": 500, "missing_headers": 40}, counters
    # 540 refusals -> 2 counter rows and one sampled audit row per reason, not 540 rows.
    assert sampled == 2 and legacy == 0, (sampled, legacy)
    assert wh.summary(db)["refused"] == {"not_configured": 500, "missing_headers": 40}


def test_m1_the_sample_reopens_after_the_window_and_unknown_reasons_cannot_grow_the_table():
    db = _db()
    wh._refused(db, wh.WebhookRefused("not_configured", "x", 503), now=NOW)
    wh._refused(db, wh.WebhookRefused("not_configured", "x", 503),
                now=NOW + timedelta(seconds=wh.AUDIT_SAMPLE_SECONDS - 5))
    wh._refused(db, wh.WebhookRefused("not_configured", "x", 503),
                now=NOW + timedelta(seconds=wh.AUDIT_SAMPLE_SECONDS + 5))
    for i in range(20):  # a reason outside the closed set is one bucket, whatever it says
        wh._refused(db, wh.WebhookRefused(f"invented_{i}", "x", 400), now=NOW)
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == wh.REFUSAL_SAMPLE_ACTION).order_by(AuditLog.id)))
        reasons = sorted(s.scalars(select(wh.EtsyWebhookRefusal.reason)))
    assert [r.detail["reason"] for r in rows] == ["not_configured", "not_configured", "other"]
    assert rows[1].detail["count_so_far"] == 3
    assert reasons == ["not_configured", "other"], reasons


def test_m1_summary_aggregates_legacy_refusal_rows_in_sql():
    db = _db()
    with db.session() as s:   # rows written by a25a377 and earlier, one per refusal
        for reason in ("bad_signature", "bad_signature", "stale"):
            s.add(AuditLog(actor="orchestrator", action=wh.REFUSED_ACTION,
                           detail={"reason": reason, "why": "x", "status": 401}))
    wh.receive(db, {}, b"{}", secret="", now=NOW)
    refused = wh.summary(db)["refused"]
    assert refused == {"bad_signature": 2, "stale": 1, "not_configured": 1}, refused
    # No Python pass over the audit rows remains in summary.
    import inspect

    src = inspect.getsource(wh.summary)
    assert "for d in s.scalars(select(AuditLog.detail)" not in src
    assert "group_by(legacy_reason)" in src


def test_m1_existing_refusal_semantics_are_unchanged():
    """Every reason still refuses with its status, and nothing is stored or enqueued."""
    db = _db()
    h, body = _delivery()
    cases = [
        ("bad_signature", {**h, "webhook-signature": "v1,AAAA"}, body, 401),
        ("stale", *_delivery(at=NOW - timedelta(seconds=301)), 401),
    ]
    for reason, headers, raw, status in cases:
        got_status, got = wh.receive(db, headers, raw, secret=SECRET, shop_id=None, now=NOW)
        assert (got_status, got["reason"]) == (status, reason), got
    status, got = wh.receive(db, h, body, secret=SECRET, shop_id="555", now=NOW)
    assert status == 202 and got["accepted"], got


# ---------------------------------------------------------------------------
# A-L1


class _Stream:
    def __init__(self, chunks):
        self.chunks, self.read = list(chunks), 0

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self.chunks:
            self.read += 1
            yield c


def _read(stream, cl):
    return asyncio.run(wh.read_body(stream, cl))


def test_l1_a_declared_oversize_body_is_refused_before_a_byte_is_read():
    s = _Stream([b"x" * 1024] * 100)
    try:
        _read(s, str(wh.MAX_BODY_BYTES + 1))
    except wh.WebhookRefused as exc:
        assert (exc.reason, exc.status) == ("too_large", 413)
    else:
        raise AssertionError("an oversize Content-Length was read")
    assert s.read == 0, "the body was consumed before the refusal"
    for bad in ("abc", "-1"):
        try:
            _read(_Stream([b"{}"]), bad)
        except wh.WebhookRefused as exc:
            assert exc.reason == "malformed" and exc.status == 400
        else:
            raise AssertionError(f"Content-Length {bad!r} was accepted")


def test_l1_an_undeclared_or_understated_body_stops_at_the_running_cap():
    chunk = 8 * 1024
    total = (wh.MAX_BODY_BYTES // chunk) + 40
    for cl in (None, "10"):
        s = _Stream([b"x" * chunk] * total)
        try:
            _read(s, cl)
        except wh.WebhookRefused as exc:
            assert exc.reason == "too_large"
        else:
            raise AssertionError("an oversize stream was buffered")
        assert s.read == wh.MAX_BODY_BYTES // chunk + 1, (cl, s.read)
    assert _read(_Stream([b'{"a":', b" 1}"]), None) == b'{"a": 1}'


_APP: dict = {}


def _app():
    if "c" not in _APP:
        os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/route.sqlite"
        os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
        from fastapi.testclient import TestClient

        from brambleloop.app import main

        main.db.create_all()
        Registry(main.db).seed_defaults()
        _APP.update(c=TestClient(main.app), main=main)
    return _APP["c"], _APP["main"]


def test_l1_l2_the_route_refuses_oversize_and_non_ascii_cleanly():
    os.environ[wh.SECRET_ENV] = SECRET
    os.environ["ETSY_SHOP_ID"] = "555"
    try:
        c, main = _app()
        big = b"{" + b" " * (wh.MAX_BODY_BYTES + 10) + b"}"
        r = c.post("/api/etsy/webhook", content=big,
                   headers={"content-type": "application/json"})
        assert r.status_code == 413 and r.json()["reason"] == "too_large", r.text
        h, body = _delivery(wid="msg_l2")
        r = c.post("/api/etsy/webhook", content=body,
                   headers={**{k: v for k, v in h.items() if k != "webhook-signature"},
                            "webhook-signature": "v1,été".encode("latin-1"),
                            "content-type": "application/json"})
        assert r.status_code == 401 and r.json()["reason"] == "bad_signature", r.text
        r = c.post("/api/etsy/webhook", content=body,
                   headers={**h, "content-type": "application/json"})
        assert r.status_code == 202, r.text
        refused = c.get("/api/etsy").json()["webhooks"]["refused"]
        assert refused.get("too_large", 0) >= 1 and refused.get("bad_signature", 0) >= 1
    finally:
        os.environ.pop(wh.SECRET_ENV, None)
        os.environ.pop("ETSY_SHOP_ID", None)


# ---------------------------------------------------------------------------
# A-L2


def test_l2_a_non_ascii_signature_is_a_refusal_not_a_type_error():
    db = _db()
    h, body = _delivery(wid="msg_na")
    for sig in ("v1,é", "v1,AAAA v1,ÿþ", "v1,☃", "v1,\udcff"):
        status, got = wh.receive(db, {**h, "webhook-signature": sig}, body, secret=SECRET,
                                 shop_id="555", now=NOW)
        assert (status, got["reason"]) == (401, "bad_signature"), (sig, status, got)
    # A valid entry beside a non-ASCII one is still accepted (any entry may match).
    status, got = wh.receive(db, {**h, "webhook-signature": "v1,é "
                                  + h["webhook-signature"]}, body, secret=SECRET,
                             shop_id="555", now=NOW)
    assert status == 202, got


# ---------------------------------------------------------------------------
# A-I2, A-I3


def test_i2_the_lighter_visual_path_is_chosen_only_by_deterministic_builders():
    from brambleloop.visual import frame_role as FR

    assert FR.classify(SimpleNamespace(has_model=True, asset_class="INFOGRAPHIC",
                                       role="size")) == FR.PHOTOGRAPHIC
    assert FR.classify(SimpleNamespace(has_model=False, asset_class="AI_GENERATED",
                                       role="hero")) == FR.PHOTOGRAPHIC
    assert FR.classify(SimpleNamespace(asset_class=None, role=None)) == FR.PHOTOGRAPHIC
    # Pin who may assign the classes that skip the realism checks: only the deterministic
    # frame builders. A new assigner must be reviewed, and this test is where it shows.
    src = ROOT / "src" / "brambleloop"
    assigners = sorted(
        str(p.relative_to(src)) for p in src.rglob("*.py")
        if any(n in p.read_text(encoding="utf-8")
               for n in ("AssetClass.INFOGRAPHIC", "AssetClass.PATTERN_PREVIEW"))
        and p.name != "frame_role.py")
    # Reviewed 2026-10-19: listing_assets.py builds the frames, launch_imagery.py maps a
    # deterministic CONTENTS job; eligibility.py and listing_set.py only read the class
    # (lookup tables / a value constant).
    assert assigners == ["publish/eligibility.py", "publish/listing_assets.py",
                         "publish/listing_set.py", "visual/launch_imagery.py"], assigners


def test_i3_attribution_evidence_is_capped():
    from brambleloop.finance import sources

    db = _db()
    try:
        sources.attribute(db, "etsy:1:1", "etsy_ads",
                          evidence="x" * (sources.MAX_EVIDENCE_CHARS + 1))
    except sources.AttributionRefused as exc:
        assert "at most" in str(exc)
    else:
        raise AssertionError("over-long evidence was stored")


# ---------------------------------------------------------------------------
# B1: one seasonal tournament per group per ISO week


def _at_risk_day(event="Christmas", event_date=date(2026, 12, 25), make_hours=6.0):
    from brambleloop.seasonal.leadtime import AT_RISK, compile_launch

    plan = compile_launch(event, event_date, make_hours=make_hours)
    day = plan.preferred_launch + timedelta(days=1)
    while plan.status(day) != AT_RISK:
        day += timedelta(days=1)
        assert day <= plan.latest_effective_launch, "no at-risk day for this target"
    return day


def _events(db, n, *, pod="hats", arena="hat", event="Christmas"):
    target = {"event": event, "event_date": "2026-12-25", "make_hours": 6.0}
    ids = []
    with db.session() as s:
        for i in range(n):
            ev = MjsMissionEvent(benchmark_key="mjs", listing_ref=f"L{pod}{arena}{i}",
                                 fingerprint=f"fp{pod}{arena}{i}", pod=pod, arena=arena,
                                 entered=True, seasonal={"target": target})
            s.add(ev)
            s.flush()
            ids.append(ev.id)
    return ids


def test_b1_a_sibling_with_a_tournament_lends_it_to_its_group():
    from brambleloop.intel import mission_runtime
    from brambleloop.queue.durable import JobQueue

    db = _db()
    ids = _events(db, 3)
    other = _events(db, 1, arena="scarf")
    job = JobQueue(db).enqueue("creative_director", "creative.tournament",
                               {"mjs_event_id": ids[0]}, idempotency_key="t-existing")
    with db.session() as s:
        s.get(MjsMissionEvent, ids[0]).tournament_job_id = job.id
    out = mission_runtime.seasonal_sentinel(db, today=_at_risk_day())
    # Only the other arena still needs a tournament; the two siblings attach to job.id.
    assert out["needs_tournament"] == other, out["needs_tournament"]
    with db.session() as s:
        assert [s.get(MjsMissionEvent, i).tournament_job_id for i in ids] == [job.id] * 3


def test_b1_the_handler_buys_one_tournament_per_group_per_iso_week():
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    db = _db()
    with db.session() as s:
        from brambleloop.core.models import Agent

        agent = s.scalar(select(Agent).where(Agent.name == "market_radar"))
        agent.allowed_job_types = list(agent.allowed_job_types or []) + [
            "mjs.seasonal_sentinel"]
    hats = _events(db, 4)
    scarves = _events(db, 2, arena="scarf")
    day = _at_risk_day()

    def sentinel(on):
        JobQueue(db).enqueue("market_radar", "mjs.seasonal_sentinel", {"as_of": on.isoformat()},
                             priority=0, idempotency_key=f"s:{on}:{os.urandom(3).hex()}")
        assert Worker(db, "rel2", job_types=["mjs.seasonal_sentinel"]).run_once()

    sentinel(day)
    with db.session() as s:
        tournaments = list(s.scalars(select(Job).where(
            Job.job_type == "creative.tournament")))
        bound = {i: s.get(MjsMissionEvent, i).tournament_job_id for i in hats + scarves}
    assert len(tournaments) == 2, [t.idempotency_key for t in tournaments]
    by_ids = {tuple(t.inputs["mjs_event_ids"]): t.id for t in tournaments}
    assert by_ids == {tuple(hats): bound[hats[0]], tuple(scarves): bound[scarves[0]]}
    assert len({bound[i] for i in hats}) == 1 and len({bound[i] for i in scarves}) == 1
    key = next(t.idempotency_key for t in tournaments if t.id == bound[hats[0]])
    y, w, _ = day.isocalendar()
    assert key == f"mjs.at_risk:hats:hat:Christmas:{y}-W{w:02d}", key
    # Re-running the sentinel the next day buys nothing more: every event is bound.
    sentinel(day + timedelta(days=1))
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "creative.tournament")) == 2


# ---------------------------------------------------------------------------
# B2: the prompt names the free gates; selection prefers a concept that passes them


def _slot(form="hat", event="Christmas", pod="hats", constructions=None):
    from brambleloop.creative import prospecting as P
    from brambleloop.creative.family import FORM_CONSTRUCTIONS

    arena = P.Arena(event=event, pod=pod, benchmark_listings=40, days_away=60,
                    forms={form: 20})
    cons = tuple(sorted(FORM_CONSTRUCTIONS.get(form, ()))) if constructions is None \
        else constructions
    return P.Slot(arena=arena, form=form, make_lane="QUICK", benchmark_examples=20,
                  constructions=cons, engine_ready=True, needs_engineering=())


class _Recorder:
    def __init__(self):
        self.calls = []

    def complete_json(self, ref, *, agent, values, required=None):
        from brambleloop.gateway import prompts

        self.calls.append((ref, dict(values)))
        prompts.get(ref).render(**values)      # every placeholder is supplied
        return {"concepts": []}


def test_b2_concept_field_v3_names_the_motif_grammar_and_the_qualifiers():
    from brambleloop.creative import prospecting as P
    from brambleloop.creative.invention import MOTIF_GRAMMAR, SATURATED
    from brambleloop.gateway import prompts

    assert P.PROMPT == "creative.concept_field@3"
    assert prompts.get("creative.concept_field@2"), "the old version stays explainable"
    gw = _Recorder()
    P.propose(_slot("coaster", pod="home_decor"), gateway=gw, count=3)
    ref, values = gw.calls[-1]
    assert ref == "creative.concept_field@3"
    fresh = [m for m in MOTIF_GRAMMAR["christmas"] if m not in SATURATED["christmas"]]
    assert all(m.replace("_", " ") in values["motif_grammar"] for m in fresh)
    assert "post box" in values["motif_grammar"] and "clichés" in values["motif_grammar"]
    sil = values["silhouette"]
    assert "silhouette qualifier" in sil and "tapestry" in sil and "pocket" in sil, sil
    P.propose(_slot("hat"), gateway=gw, count=3)
    assert "no silhouette qualifier is required" in gw.calls[-1][1]["silhouette"]
    P.propose(_slot("hat", event="Valentine's Day"), gateway=gw, count=3)
    assert gw.calls[-1][1]["motif_grammar"] == "none applies to this occasion"
    # The prompt is still pinned: editing v3 in place is refused.
    try:
        prompts.register(prompts.Prompt(name="creative.concept_field", version="3",
                                        system="x", template="y", output_schema=("concepts",),
                                        max_output_tokens=10))
    except prompts.PromptIsImmutable:
        pass
    else:
        raise AssertionError("a released prompt was edited in place")


def test_b2_a_generic_slot_no_construction_can_qualify_is_skipped():
    from brambleloop.creative import prospecting as P

    assert P.qualifier_possible(_slot("hat"))                       # an outline
    assert P.qualifier_possible(_slot("coaster", pod="home_decor"))  # tapestry/motif_join
    bare = _slot("tube", pod="home_decor", constructions=("in_the_round", "flat_rows"))
    assert not P.qualifier_possible(bare)
    import inspect

    assert "qualifier_possible(s)" in inspect.getsource(P.field)
    assert "qualifier_possible(s)" in inspect.getsource(P.expedition)


def _concept(key, *, motif, premise, form="hat", construction="in_the_round",
             occasion="christmas", pod="hats"):
    from brambleloop.creative.concept import Concept

    return Concept(key=key, title=f"Concept {key}", premise=premise, pod=pod, form=form,
                   construction=construction, motif=motif, palette_story="pine and cream",
                   recipient="child", occasion=occasion, feeling="festive",
                   function="keeps a child warm on the walk to school", make_lane="QUICK")


def test_b2_free_gate_check_is_the_gate_itself():
    from brambleloop.creative import intake

    bad = _concept("a", motif="geometric",
                   premise=("a ribbed beanie with a deep folded brim whose crown gathers "
                            "into a neat tidy point above the ears"))
    good = _concept("b", motif="lantern",
                    premise=("a ribbed beanie whose folded brim carries a ring of lantern "
                             "shapes glowing in contrasting yarn around the head"))
    assert intake.free_gate_check(bad)["failed"] == ["motif_grammar"]
    assert intake.free_gate_check(good)["passes"] is True
    generic = _concept("c", motif="lantern", form="round_disc", construction="flat_rows",
                       pod="home_decor",
                       premise=("a round mat carrying a ring of lantern shapes in "
                                "contrasting yarn around a plain cream centre"))
    assert "silhouette" in intake.free_gate_check(generic)["failed"]
    qualified = _concept("d", motif="lantern", form="round_disc", construction="tapestry",
                         pod="home_decor",
                         premise=("a round mat carrying a ring of lantern shapes in "
                                  "contrasting yarn around a plain cream centre"))
    assert intake.free_gate_check(qualified)["passes"] is True
    # The gate it mirrors refuses the same concept (nothing is loosened).
    from brambleloop.creative.preengineering import _motif_grammar

    assert _motif_grammar(bad, {"motifs": [], "season": "christmas"})["status"] == "fail"


def test_b2_selection_picks_the_best_shortlisted_concept_that_passes_the_free_gates():
    from brambleloop.creative import ideation, intake

    fails = _concept("t1-fails", motif="geometric",
                     premise=("a ribbed beanie with a deep folded brim whose crown gathers "
                              "into a neat tidy point above the ears"))
    passes = _concept("t2-passes", motif="acorn", form="toy",
                      construction="amigurumi_shaping", pod="toys",
                      premise=("a small standing woodland figure holding a lantern whose "
                               "felted coat buttons with a carved wooden toggle"))
    survivors = [SimpleNamespace(concept=fails, nearest_distance=0.9),
                 SimpleNamespace(concept=passes, nearest_distance=0.8)]
    plan = {"floor": {"floor": 0.1}, "role": {"lanes": ["QUICK"], "role": "core"},
            "history": [], "skill_gap": {}}
    plain = ideation.select(plan, candidates=survivors, survivors=survivors)
    shortlist = plain["shortlist"]
    assert "t1-fails" in shortlist and "t2-passes" in shortlist, plain
    assert plain["winner"]["key"] == "t1-fails" and plain["free_gate_screen"] is None
    screened = ideation.select(plan, candidates=survivors, survivors=survivors,
                               free_gates=lambda c: intake.free_gate_check(c.concept))
    assert screened["winner"]["key"] == "t2-passes", screened["free_gate_screen"]
    assert screened["free_gate_screen"]["t1-fails"]["failed"] == ["motif_grammar"]
    # With nothing passing, the old order stands and intake's gate refuses as before.
    none_pass = ideation.select(plan, candidates=survivors, survivors=survivors,
                                free_gates=lambda c: {"passes": False, "failed": ["x"]})
    assert none_pass["winner"]["key"] == "t1-fails"


# ---------------------------------------------------------------------------
# B3: the brief walk resumes across runs


def test_b3_repeat_runs_ask_new_questions():
    from brambleloop.creative import prospecting as P

    db = _db()
    arena = P.Arena(event="Christmas", pod="hats", benchmark_listings=40, days_away=97,
                    forms={"hat": 40})
    briefs = []
    for _ in range(3):
        gw = _Recorder()
        P.expedition(db, arena, gateway=gw, count=6)
        briefs.append(gw.calls[0][1]["brief"])
    assert len(set(briefs)) == 3, "a repeat run asked the same questions again"
    slot = P.slots(arena)["slot_objects"][0]
    assert P.brief_offset(db, slot) == 18
    # The questions themselves are the stable walk: run 2 asks pairings 6..11.
    assert briefs[1] == P._brief_for(slot, 6, offset=6)


# ---------------------------------------------------------------------------
# B4: construction readings


def _reference_db():
    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation
    from brambleloop.intel import benchmarks

    db = _db()
    with db.session() as s:
        for pod, tone in (("garments", "calm"), ("toys", "calm")):
            for i in range(2):
                ref = f"{pod}{i}"
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=ref,
                                       title="Pattern", pod=pod,
                                       detail={"image_urls": [f"https://fixture.invalid/{ref}"]}))
                s.add(BenchmarkObservation(
                    benchmark_key=benchmarks.MJS_KEY, listing_ref=ref,
                    kind="gallery_image_observation", grade="primary",
                    detail={"observation": {"palette_role": "accent", "setting": "studio",
                                            "emotional_merchandising": tone}}))
    return db


class _Seer:
    def __init__(self, text_for):
        from brambleloop.creative import reference
        from brambleloop.gateway import anthropic as gw

        self.model = gw.provider_for(reference.TASK).model
        self.cost_per_1k_input_cad = self.cost_per_1k_output_cad = 0.0
        self.text_for, self.seen = text_for, []

    def see(self, system, prompt, images, max_tokens=0):
        from brambleloop.gateway.model_gateway import ModelResponse

        self.seen.append(images[0])
        return ModelResponse(text=self.text_for(images[0]), input_tokens=10, output_tokens=10,
                             provider="fixture", model=self.model, latency_ms=1.0)


CLEAN = ('{"silhouette_class": "boxy", "neckline": "crew", "edge_finish": "ribbed", '
         '"styling_context": "layering"}')


def test_b4_a_refused_reading_is_recorded_and_not_bought_again():
    from brambleloop.creative import reference

    db = _reference_db()
    seer = _Seer(lambda url: '{"neckline": "a gnome face applique"}' if url.endswith("toys0")
                 else CLEAN)
    first = reference.run(db, provider=seer, today=date(2026, 10, 19))
    assert any(f["listing_ref"] == "toys0" and f.get("recorded_refusal")
               for f in first["failed"]), first
    assert len(seer.seen) == 4
    second = reference.run(db, provider=seer, today=date(2026, 10, 20))
    assert len(seer.seen) == 4, "a refused reading was bought again"
    assert second["skipped_refused_readings"] == ["toys0"]
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == reference.READING_REFUSED_ACTION))
        assert row.detail == {"refusal": "depiction", "image": "https://fixture.invalid/toys0"}
        assert "gnome" not in json.dumps(row.detail), "a refused reading's text is not kept"


def test_b4_one_departments_depiction_refusal_does_not_stop_the_others():
    from brambleloop.core.models import BenchmarkObservation
    from brambleloop.creative import reference
    from brambleloop.intel import benchmarks

    db = _reference_db()
    with db.session() as s:   # a judged observation that names what is depicted
        for o in s.scalars(select(BenchmarkObservation).where(
                BenchmarkObservation.listing_ref.like("toys%"))):
            o.detail = {"observation": {"palette_role": "accent", "setting": "studio",
                                        "emotional_merchandising": "a gnome family scene"}}
    out = reference.run(db, provider=_Seer(lambda url: CLEAN), today=date(2026, 10, 19))
    assert out["ran"] and "garments" in out["decompositions_stored"], out
    assert "toys" in out["decompositions_stored"], out
    toys = reference.stored_decomposition(db, "toys")
    assert "emotional_tone" in toys["withheld"] and "emotional_tone" not in toys["primitives"]
    assert "gnome" not in json.dumps(toys), "a depicting value reached the stored record"
    # A refusal the per-value withholding cannot resolve is that department's alone.
    real = reference.brief

    def brief(db_, pod, **kw):
        if pod == "toys":
            raise reference.ReferenceRefused("names what the product depicts")
        return real(db_, pod, **kw)

    reference.brief = brief
    try:
        out = reference.run(db, provider=_Seer(lambda url: CLEAN), today=date(2026, 10, 20))
    finally:
        reference.brief = real
    assert out["decompositions_stored"] == ["garments"], out
    assert out["decompositions_refused"][0]["pod"] == "toys"
    assert benchmarks.MJS_KEY


# ---------------------------------------------------------------------------
# B5: gallery observation asks for structured output


def test_b5_gallery_observation_requests_json_schema_output():
    from brambleloop.gateway import anthropic as gw
    from brambleloop.intel import vision

    schema = vision.observation_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(vision.OBSERVATION_FIELDS)
    # W4-CLOSE5: every field is required and "unjudgeable" is the empty string, which the
    # parser drops exactly as it dropped an omitted key (24 optional properties timed every
    # production call out on b931d17; see tests/test_w4_close5_vision_timeout.py).
    assert schema["properties"]["shot_type"]["enum"] == [*vision.SHOT_TYPES, ""]
    assert schema["required"] == list(vision.OBSERVATION_FIELDS)
    assert vision.parse_observation(json.dumps(
        {**{f: "" for f in vision.OBSERVATION_FIELDS}, "composition": "centred"})) == \
        {"composition": "centred"}, "an unjudgeable field is still left out of the observation"

    sent = {}
    p = gw.AnthropicProvider(model="claude-sonnet-5")
    p.key = staticmethod(lambda: "test-key")          # type: ignore[method-assign]
    p._guarded = lambda payload, key, effect, **kw: sent.update(  # type: ignore[method-assign]
        body=json.loads(payload), effect=effect) or SimpleNamespace(text="{}")
    p.see("sys", "prompt", ["https://fixture.invalid/a.jpg"], max_tokens=100,
          json_schema=schema)
    assert sent["body"]["output_config"] == {"format": {"type": "json_schema",
                                                       "schema": schema}}
    assert sent["body"]["messages"][-1]["role"] == "user", "no assistant prefill"
    p.see("sys", "prompt", ["https://fixture.invalid/a.jpg"], max_tokens=100)
    assert "output_config" not in sent["body"], "other vision callers are unchanged"
    assert vision._accepts_schema(p)

    class Old:
        def see(self, system, prompt, images, max_tokens=0):
            return None

    assert not vision._accepts_schema(Old()), "a provider without the kwarg is not sent it"
    # The method identity includes the schema, so the F-309 breaker sees a new method.
    assert len(vision.method_version()) == 12


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
