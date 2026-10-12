"""W4-B2CLOSE (second pass, test_w4_b2close2): Build 2 #61 (Visual Semantic QA) and #195 (Proof of Off-Device Autonomy).

#61, quoted: "The system must test whether an image communicates what its caption/title
claims. A finished-result frame cannot be only abstract horizontal rows. A chart preview must
look like a chart preview. A size card must communicate scale clearly. Use independent visual
review plus deterministic metadata assertions; do not rely on the generator grading itself."
One test per clause below, with stub providers (no spend).

#195's only unmet production condition is `no_unexpected_dead_letters`. Production 7bbbe72
(read-only GET /api/queue/dead, 2026-10-12) dead-lettered three company defects after the
hotfix deploy: radar.score KeyError 'slug', ops.policy_watch VARCHAR(40) overflow and
ops.offsite_archive EphemeralStorageRefused. One regression test per defect.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="w4_b2close2_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from PIL import Image  # noqa: E402

from brambleloop.visual import inspect as I  # noqa: E402


def _desc(**over):
    base = {"object_shown": "a set of four hexagon coasters", "object_count": 4,
            "finished_or_in_progress": "finished", "human_present": False,
            "text_present": True, "chart_or_diagram": False,
            "dominant_colours": "cream, wine", "clarity": "clear",
            "third_party_marks": "none"}
    base.update(over)
    return base


def _checks(result):
    return {p["check"] for p in result["problems"]}


def _db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _png(name="frame.png"):
    path = os.path.join(_TMP, name)
    if not os.path.exists(path):
        Image.new("RGB", (2000, 2000), (230, 226, 214)).save(path)
    return path


# ---- #61 clause 1: "test whether an image communicates what its caption/title claims" ------

def test_61_every_listing_role_is_compared_against_its_claim():
    from brambleloop.runtime import release

    roles = ("hero", "whats_included", "size", "materials", "pattern_preview", "chart",
             "collection")
    assert set(roles) <= set(release.ROLE_CLAIMS)
    for role in roles:
        assert release.ROLE_CLAIMS[role], role  # never an empty claim that passes vacuously


# ---- #61 clause 2: "A finished-result frame cannot be only abstract horizontal rows" -------

def test_61_a_finished_result_frame_of_abstract_rows_is_blocked():
    from brambleloop.runtime import release

    claim = {**release.ROLE_CLAIMS["hero"], "identifies_as": ["coaster"]}
    rows = _desc(object_shown="horizontal bands of colour", object_count="unclear",
                 finished_or_in_progress="unclear", text_present=False)
    got = I.compare(rows, claim)
    assert {"finished_result", "product_identity"} <= _checks(got), got["problems"]
    verdict = I.gate({"realism": {}, "realism_unjudged": [], "semantic": got,
                      "description": rows})
    assert verdict["verdict"] == "blocked"
    # the same frame read as a chart is a chart, not a finished result
    as_chart = I.compare(_desc(chart_or_diagram=True, finished_or_in_progress="unclear"), claim)
    assert "chart_as_hero" in _checks(as_chart)
    # and a genuinely finished, identified object is not refused
    assert I.compare(_desc(), claim)["communicates"] is True


def test_61_deterministic_half_refuses_a_flat_hero():
    from brambleloop.gates.asset_truth import AssetClass
    from brambleloop.publish.listing_assets import Frame, check_frame_plan

    frames = [Frame(position=1, role="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                    caption="hero", fabric_is_flat=True)]
    assert any("LISTING_HERO_FABRIC_FLAT" in p for p in check_frame_plan(frames))


# ---- #61 clause 3: "A chart preview must look like a chart preview" -----------------------

def test_61_a_chart_preview_that_is_not_a_chart_is_blocked():
    from brambleloop.runtime import release

    claim = release.ROLE_CLAIMS["chart"]
    assert "chart_preview" in _checks(I.compare(_desc(chart_or_diagram=False), claim))
    assert I.compare(_desc(object_shown="a stitch chart", chart_or_diagram=True),
                     claim)["communicates"] is True


# ---- #61 clause 4: "A size card must communicate scale clearly" ---------------------------

def test_61_a_size_card_without_a_legible_measurement_is_blocked():
    from brambleloop.runtime import release

    claim = release.ROLE_CLAIMS["size"]
    assert "size_label" in _checks(I.compare(_desc(text_present=False), claim))
    assert "size_label" in _checks(I.compare(_desc(text_present="unclear"), claim))
    assert "size_reference" in _checks(I.compare(_desc(object_count="unclear"), claim))
    assert I.compare(_desc(object_count=1, text_present=True), claim)["communicates"] is True


def test_61_a_rendered_size_card_with_no_scale_is_refused_deterministically():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import write_pattern
    from brambleloop.publish.listing_assets import build_frames, check_frame_plan
    from brambleloop.runtime import pipeline
    from brambleloop.cir.twin import build_twin

    cir = pipeline._engineered_cir("hexagon-coaster-set")
    result = compile_cir(cir)
    assert result.ok
    twin = build_twin(cir, result)
    frames = build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                          difficulty="confident beginner", pages=7)
    size = next(f for f in frames if f.role == "size")
    assert size.scale_shown in ("reference", "circumference"), size.scale_shown
    assert not any("LISTING_SIZE_CARD_NO_SCALE" in p for p in check_frame_plan(frames))
    size.scale_shown = ""
    assert any("LISTING_SIZE_CARD_NO_SCALE" in p and "frame 3" in p
               for p in check_frame_plan(frames))


# ---- #61 clause 5: independent review, not the generator grading itself ------------------

class _RecordingProvider:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, description):
        self.description = description
        self.calls = []

    def see(self, system, prompt, images, max_tokens=0):
        self.calls.append(system + "\n" + prompt)
        body = (json.dumps(self.description) if "JSON object and nothing else. Keys" in prompt
                else json.dumps({c: True for c in I.REALISM_CHECKS}))

        class R:
            text = body
            input_tokens = 10
            output_tokens = 10
        return R()


def test_61_the_describer_never_sees_the_claim_and_code_compares():
    from brambleloop.runtime import release

    claim = release.ROLE_CLAIMS["chart"]
    p = _RecordingProvider(_desc(chart_or_diagram=False))
    out = I.inspect_image(_png(), provider=p, claim=claim)
    assert out["described"] and out["realism_judged"]
    sent = " ".join(p.calls).lower()
    for word in ("chart preview", "shows_chart_preview", "caption", "claim"):
        assert word not in sent, word
    assert out["semantic"]["communicates"] is False
    assert "chart_preview" in _checks(out["semantic"])


def test_61_review_record_names_why_a_frame_was_blocked():
    """Production 7bbbe72 recorded a size card `blocked` with an empty semantic list; the
    record now carries the failed realism checks and third-party marks too."""
    from brambleloop.build2 import executor
    from brambleloop.runtime import release

    gate = executor.GATE_BY_KEY["image_vision"]
    original = (gate.check, I.inspect_image)

    def fake_inspect(ref, *, db=None, provider=None, claim=None):
        d = _desc(object_count=1, text_present=True, third_party_marks="KINFOLK")
        return {"described": True, "description": d, "realism": {"drape": False},
                "realism_unjudged": [], "semantic": I.compare(d, claim or {})}

    audits = []
    ctx = SimpleNamespace(db=_db(), audit=lambda action, **k: audits.append((action, k)))
    gate.check = lambda db_, env: True
    I.inspect_image = fake_inspect
    try:
        out = release._review_frames(ctx, "hexagon-coaster-set", "1.2.0",
                                     [SimpleNamespace(position=3, role="size")],
                                     {3: _png()}, shas={3: "c" * 64}, families=["coaster"])
    finally:
        gate.check, I.inspect_image = original
    v = out["verdicts"][3]
    assert v["verdict"] == "blocked" and v["semantic"] == []
    assert v["failed_realism"] == ["drape"] and v["third_party_marks"] == ["KINFOLK"]
    assert any("FRAME_REVIEW_BLOCKED" in b for b in out["blocking"])
    recorded = audits[-1][1]["detail"]["frames"]["3"]
    assert recorded["failed_realism"] == ["drape"]


# ---- #195: the three production dead letters --------------------------------------------

def test_195_radar_score_without_a_slug_scores_the_gap_queue_instead_of_dying():
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus
    from brambleloop.intel import coverage
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401  (registers handlers)
    from brambleloop.runtime.worker import Worker

    db = _db()
    gap = coverage.upsert(db, benchmark_key="mjs", arena="stockings", pod="christmas",
                          components={"apparent_demand": 0.8})
    coverage.upsert(db, benchmark_key="mjs", arena="unknown-arena", pod="misc")
    from brambleloop.core.models import CoverageGap

    with db.session() as s:
        s.get(CoverageGap, gap).product_slug = "nordic-forest-stocking"
    # the shape the Intelligence charter's CoverageGap handoff enqueues: no slug
    job = JobQueue(db).enqueue("market_radar", "radar.score",
                               {"handoff": {"table": "coverage_gaps", "max_id": gap,
                                            "rows": 2}},
                               idempotency_key="handoff:radar.score:1", priority=0)
    Worker(db, "w", job_types=["radar.score"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        out = dict(row.outputs)
        fanned = [j.inputs.get("slug") for j in s.scalars(select(Job).where(
            Job.job_type == "radar.score", Job.id != job.id))]
    assert out["queued"] == ["nordic-forest-stocking"] and out["open_gaps"] == 2
    assert out["without_a_pool_concept"] == 1 and out["score"] is None
    assert fanned == ["nordic-forest-stocking"]


def test_195_policy_snapshot_versions_fit_their_column():
    from sqlalchemy import select

    from brambleloop.core.models import PolicySnapshot
    from brambleloop.gates import platform_policy, policy_knowledge

    limit = PolicySnapshot.__table__.c.version.type.length
    db = _db()
    seeded = policy_knowledge.seed_snapshots(db)
    assert seeded["seeded"], "the repository seed must write at least one reading"
    with db.session() as s:
        rows = list(s.scalars(select(PolicySnapshot)))
    assert rows, "no snapshot was written, so nothing was measured"
    for r in rows:
        assert len(r.version) <= limit, (r.source, r.version)
        for col in ("source", "checked_on", "digest"):
            n = PolicySnapshot.__table__.c[col].type.length
            assert len(getattr(r, col) or "") <= n, (col, getattr(r, col))
    # INTEG3 kept ONE fix for this defect: the column was widened (migrate.widen, VARCHAR(40)
    # -> VARCHAR(120)) instead of shortening the label (W4-B2CLOSE's fit_version), so the
    # 49-character production seed label is stored verbatim, and a label past the column is
    # refused rather than clipped (test_w4_integ3_defects).
    long_rows = [r for r in rows if len(r.version) > 40]
    assert long_rows, "the 49-character seed label is the production case"
    for r in long_rows:
        assert ":" in r.version and "~" not in r.version, r.version
    assert platform_policy.version_of(long_rows[0]) == long_rows[0].version


def test_195_offsite_restore_proof_runs_under_require_postgres():
    from brambleloop.core import offsite
    from brambleloop.core.db import Database
    from brambleloop.core.models import Product

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(Product(slug="test-throw", title="Test throw"))
    objects: dict = {}

    def put(key, payload, *, env=None):
        objects[key] = payload
        return {"key": key, "bytes": len(payload), "bucket": "t", "host": "t"}

    env = {offsite.ENDPOINT_VAR: "https://s3.us-west-004.backblazeb2.com",
           offsite.BUCKET_VAR: "brambleloop-archive", offsite.KEY_ID_VAR: "004aabb",
           offsite.SECRET_VAR: "K004" + "x" * 27,
           offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to be stretched into a key",
           offsite.REGION_VAR: "us-west-004"}
    before = os.environ.get("BRAMBLELOOP_REQUIRE_POSTGRES")
    os.environ["BRAMBLELOOP_REQUIRE_POSTGRES"] = "1"
    try:
        record = offsite.archive(db, env=env, transport=(put, lambda k, *, env=None: objects[k]),
                                 work_dir=tempfile.mkdtemp(dir=_TMP))
    finally:
        if before is None:
            os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
        else:
            os.environ["BRAMBLELOOP_REQUIRE_POSTGRES"] = before
    assert record["ok"] is True and record["stage"] == "complete", record.get("reason")
    assert record["tables_restored"] > 0


if __name__ == "__main__":
    failed = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
