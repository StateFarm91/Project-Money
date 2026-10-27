"""W4-C08 Visual Production: canonical model and evidence (F-226, F-733, F-739, F-859, F-737,
F-745, F-738 rollback, F-679, F-680, F-748, F-527 colour/typography). No provider is called and
nothing is spent: every test reads fixtures, committed files and rows.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_c08_visual.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4c08_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(Path(_TMP) / "artifacts")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402

_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _png(seed: int, *, shift: int = 0) -> bytes:
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    arr = (rng.integers(0, 200, size=(64, 64, 3)) + shift).clip(0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _cand(db, *, provider="p1", model="m1", identity="PASS", truth="PASS", realism="PASS",
          outcome="accepted", cost=0.1, latency=10.0, run_key="r1", cats=(), laura=True,
          listing="L1", slug="s1", sha="x"):
    from brambleloop.visual.image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        s.add(ImageCandidate(
            sha256=sha, run_key=run_key, method="autonomous", provenance_kind="ai",
            slug=slug, listing=listing, role="lifestyle", provider=provider, model=model,
            laura_present=laura, cost_cad=cost, latency_s=latency,
            checks={"identity": {"status": identity}, "product_truth": {"status": truth},
                    "realism": {"status": realism}},
            technical_status="PASS" if outcome == "accepted" else "FAIL",
            outcome=outcome, failure_categories=list(cats)))


# ---- F-226 -----------------------------------------------------------------------------------

def test_f226_copy_paste_sameness_is_rejected_and_natural_variation_is_permitted():
    from brambleloop.visual import naturalism as N

    a, b = _png(1), _png(2)
    retoned = _png(1, shift=6)                       # the same photograph, lightly re-toned
    base = {"identity": "PASS", "realism": "PASS"}
    varied = [dict(base, data=a, pose="seated", expression="smile", hair="down",
                   setting="porch"),
              dict(base, data=b, pose="standing", expression="neutral", hair="up",
                   setting="kitchen"),
              dict(base, data=_png(3), pose="walking", expression="laugh", hair="down",
                   setting="park")]
    assert N.check_sequence(varied)["status"] == "PASS"
    same = N.check_sequence([dict(base, data=a), dict(base, data=retoned)])
    assert same["status"] == "FAIL"
    assert [f["code"] for f in same["findings"]] == ["COPY_PASTE_SAMENESS"]
    frozen = [dict(v, pose="seated", expression="smile", hair="down", setting="porch")
              for v in varied]
    assert "NO_NATURAL_VARIATION" in {f["code"] for f in N.check_sequence(frozen)["findings"]}
    glam = [dict(varied[0]), dict(varied[1], realism="FAIL")]
    assert "SYNTHETIC_LOOK" in {f["code"] for f in N.check_sequence(glam)["findings"]}
    drift = [dict(varied[0]), dict(varied[1], identity="FAIL")]
    assert "IDENTITY_NOT_LOCKED" in {f["code"] for f in N.check_sequence(drift)["findings"]}
    # a flat fill has no picture to compare: unmeasurable (UNKNOWN), not copy-paste
    from PIL import Image

    flat = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 180, 160)).save(flat, format="PNG")
    flats = N.check_sequence([dict(base, data=flat.getvalue()), dict(base, data=flat.getvalue())])
    assert flats["status"] == "UNKNOWN" and not flats["findings"]
    # undeclared variation is UNKNOWN, never a pass
    bare = [dict(base, data=x) for x in (a, b, _png(3))]
    assert N.check_sequence(bare)["status"] == "UNKNOWN"


def test_f226_a_gallery_of_two_laura_frames_that_are_one_photo_cannot_be_published():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual import image_production as IP, naturalism as N
    from brambleloop.visual import shot_plans as SP

    st = ArtifactStore()
    s1 = st.put("a", _png(11), "image/png").sha256
    s2 = st.put("b", _png(11, shift=4), "image/png").sha256
    s3 = st.put("c", _png(12), "image/png").sha256
    row = {"listing": "L", "version": "1", "release": "r", "cir_fingerprint": "f",
           "laura_present": True, "outfit_id": "o1", "publishable": False, "blockers": [],
           "technical_status": "PASS"}
    assert N.sameness_only([dict(row, sha256=s1), dict(row, sha256=s3)])["status"] == "PASS"
    # a product-only frame is never compared as Laura
    assert N.sameness_only([dict(row, sha256=s1),
                            dict(row, sha256=s2, laura_present=False)])["status"] == "PASS"
    role = {"position": 0, "job": "LIFESTYLE", "campaign_role": "x", "laura": True,
            "required_by": [], "conditional": False, "preferred_source": "generated",
            "generate": True, "sources": {SP.DISCLOSED: SP.NOT_DRAWABLE}}
    plan = {"category": "c", "image_count": 2,
            "roles": [dict(role, position=1, role="lifestyle"),
                      dict(role, position=2, role="fit")]}
    db = _db()
    for pair, bad in (((s1, s3), False), ((s1, s2), True)):
        picks = {"lifestyle": dict(row, sha256=pair[0]), "fit": dict(row, sha256=pair[1])}
        saved = IP._best
        IP._best = lambda _db, *, listing, role, run=None: picks[role]
        try:
            view = IP.readiness(db, "L", plan=plan)
        finally:
            IP._best = saved
        blocked = [b for b in view["publication_blockers"] if b.startswith("F-226")]
        assert bool(blocked) is bad, view["publication_blockers"]
        assert view["naturalism"]["status"] == ("FAIL" if bad else "PASS")


# ---- F-733 -----------------------------------------------------------------------------------

def test_f733_agents_resolve_the_current_canonical_version_from_one_verified_registry():
    import shutil

    from brambleloop.visual import canonical, canonical_registry as CR

    rec = CR.require_current()
    assert rec["ok"] and rec["identity_id"] == canonical.IDENTITY_ID
    assert set(rec["approved_views"]) == set(canonical.CURRENT_REFERENCE_HASHES)
    for v in rec["approved_views"].values():
        assert v["hash_verified"] and v["approved"] and v["provenance"]
    assert rec["conditioning_packages"] and all(p["ok"] for p in
                                                 rec["conditioning_packages"].values())
    assert rec["specification"]["locked"] and rec["history"][-1]["status"] == "current"
    db = _db()
    assert CR.resolve(db)["approval_record"]["state"] == "NO_ROW"     # fresh db: not a pass
    # a changed reference byte makes the registry refuse instead of answering from memory
    copy = Path(_TMP) / "assets_copy"
    shutil.copytree(canonical._assets_dir(), copy)
    face = copy / rec["approved_views"]["neutral_portrait"]["file"]
    face.write_bytes(face.read_bytes() + b"\0")
    orig = canonical._assets_dir
    canonical._assets_dir = lambda: copy
    try:
        try:
            CR.require_current()
            raise AssertionError("a tampered pack resolved")
        except canonical.CanonRefused as exc:
            assert "does not verify" in str(exc)
    finally:
        canonical._assets_dir = orig


# ---- F-739 -----------------------------------------------------------------------------------

def test_f739_on_model_work_routes_to_the_best_demonstrated_configuration():
    from brambleloop.visual import image_production as IP, provider_routing as PR

    db = _db()
    for i in range(6):                                    # strong identity, slower, dearer
        _cand(db, provider="alpha", identity="PASS", cost=0.30, latency=40, sha=f"a{i}")
    for i in range(6):                                    # cheaper, but drifts identity
        _cand(db, provider="beta", identity="PASS" if i < 3 else "FAIL", cost=0.05,
              outcome="accepted" if i < 3 else "rejected", sha=f"b{i}")
    for i in range(2):                                    # too little evidence
        _cand(db, provider="gamma", sha=f"g{i}")
    board = {r["provider"]: r for r in PR.scoreboard(db)}
    assert board["alpha"]["identity_retention"] == 1.0
    assert board["beta"]["identity_retention"] == 0.5
    for k in ("product_truth_retention", "realism", "yield", "latency_s_mean",
              "cost_per_accepted_cad"):
        assert k in board["alpha"]
    r = PR.route(db, default="beta")
    assert r["provider"] == "alpha" and r["basis"] == "demonstrated"
    assert "gamma/m1" in r["refused"] and "beta/m1" in r["refused"]
    # nothing demonstrated -> the default, said to be a fallback
    fb = PR.route(db, available=["gamma"], default="gamma")
    assert fb["basis"] == "default" and fb["provider"] == "gamma"
    # the orchestrator consults the route when it has a choice of generators
    class G:
        paid = False

        def __init__(self, provider):
            self.provider, self.name = provider, provider

    saved = dict(IP._GENERATORS)
    IP._GENERATORS.clear()
    IP.register_generator("a-beta", lambda _db: G("beta"))
    IP.register_generator("b-alpha", lambda _db: G("alpha"))
    try:
        assert IP.resolve_generator(db).provider == "alpha"     # not the first name
    finally:
        IP._GENERATORS.clear()
        IP._GENERATORS.update(saved)
    assert PR.record(db)["route"]["provider"] == "alpha"


# ---- F-859 -----------------------------------------------------------------------------------

def test_f859_cost_per_certified_listing_set_counts_every_gallery_spend():
    from brambleloop.visual import economics as E
    from brambleloop.visual.image_records import ImageProductionRun, ensure_tables

    db = _db()
    ensure_tables(db)
    assert E.summary(db)["cost_per_certified_listing_set_cad"] is None   # never 0
    with db.session() as s:
        s.add(ImageProductionRun(run_key="r1", slug="s1", listing="L1", generation_calls=3,
                                 spent_cad=0.6, status="ready_for_owner_review"))
        s.add(ImageProductionRun(run_key="r2", slug="s2", listing="L2", generation_calls=2,
                                 spent_cad=0.4, status="blocked"))
    _cand(db, run_key="r1", cost=0.2, latency=12, sha="1")
    _cand(db, run_key="r1", cost=0.2, latency=8, sha="2")
    _cand(db, run_key="r1", cost=0.2, latency=10, outcome="rejected",
          cats=["identity_drift"], sha="3")
    _cand(db, run_key="r2", cost=0.2, outcome="rejected", cats=["product_fidelity"], sha="4")
    _cand(db, run_key="r2", cost=0.2, outcome="rejected",
          cats=["product_fidelity", "realism"], sha="5")
    out = E.summary(db)
    assert out["certified_listing_sets"] == 1 and out["listing_sets"] == 2
    assert out["spent_cad"] == 1.0
    assert out["cost_per_certified_listing_set_cad"] == 1.0     # the blocked set's spend counts
    assert out["yield"] == 0.4
    assert out["rejection_reasons"] == {"product_fidelity": 2, "identity_drift": 1,
                                        "realism": 1}
    assert out["latency_s"]["measured"] == 5 and out["compute"]["generation_calls"] == 5
    _cand(db, run_key="r1", cost=None, sha="6")
    assert E.summary(db)["cost_per_certified_listing_set_cad"] is None   # unknown cost
    assert "per_set" not in E.record(db)


# ---- F-737 / F-745 / F-738 ------------------------------------------------------------------

def test_f737_f745_the_improvement_loop_proposes_bounded_work_and_never_changes_her():
    from brambleloop.core.models import Incident, Job, JobStatus
    from brambleloop.visual import model_rnd as MR
    from brambleloop.visual.rnd import loop

    db = _db()
    for i in range(6):
        _cand(db, realism="FAIL" if i < 4 else "PASS", sha=f"r{i}")
    out = MR.cycle(db)
    assert out["ran"] and out["spent_cad"] == 0.0 and out["identity_id"].startswith("laura-")
    assert out["diagnosis"]["weakest"][0] == "realism"
    assert set(MR.AXES) >= {"skin_hair_detail", "lighting_response", "cross_view_consistency",
                            "provider_conditioning", "garment_interaction", "camera_realism"}
    (prop,) = out["proposed"]
    assert prop["axis"] == "realism" and prop["state"] == "awaiting_controlled_experiment"
    again = MR.cycle(db)                     # idempotent per axis: the next axis, not a repeat
    assert again["proposed"] and again["proposed"][0]["axis"] != "realism"
    # an unmeasured axis becomes a CA$0 instrumentation task that runs without the owner
    for _ in range(12):
        r = MR.cycle(db)
        if r["proposed"] and r["proposed"][0]["kind"] == "instrumentation":
            assert r["proposed"][0]["state"] == "ran"
            break
    else:
        raise AssertionError("no CA$0 instrumentation proposal ran")
    # improvements may not touch who she is
    for bad in ({"face": "softer"}, {"hair": "blonde"}, {"identity_id": "x"}):
        try:
            MR.refuse_identity_change(bad)
            raise AssertionError(f"accepted {bad}")
        except MR.ProposalRefused:
            pass
    MR.refuse_identity_change({"lighting_brief": "window light"})
    # no safe capacity: a backed-up publishing queue stops new work
    with db.session() as s:
        for i in range(MR.MAX_BACKLOG + 1):
            s.add(Job(agent="publishing", job_type="x", status=JobStatus.PENDING, inputs={},
                      idempotency_key=f"k{i}"))
    blocked = MR.cycle(db)
    assert blocked["ran"] is False and blocked["capacity"]["safe"] is False
    # the loop rides the existing 6-hourly Visual R&D cycle
    cell = loop.canonical_model_cell(db)
    assert set(cell) == {"improvement", "provider_benchmark", "economics"}
    assert not any("error" in v for v in cell.values()), cell
    assert MR.active(db)
    del Incident


def test_f738_a_regressed_canonical_version_opens_a_rollback_incident_until_it_holds():
    from sqlalchemy import select

    from brambleloop.core.models import Incident
    from brambleloop.visual import model_rnd as MR

    db = _db()
    good = [{"canonical_version": "1", "at": "2026-09-01", "identity": {"verdict": "pass"},
             "realism": "pass"} for _ in range(6)]
    worse = [{"canonical_version": "2", "at": "2026-10-01",
              "identity": {"verdict": "pass" if i < 3 else "drift"}, "realism": "pass"}
             for i in range(6)]
    out = MR.regression_watch(db, records=good + worse)
    assert out["rollback"] is True and out["restore"] == "1" and out["incident_opened"]
    with db.session() as s:
        inc = s.scalars(select(Incident).where(Incident.resolved == False)).all()  # noqa: E712
        assert [i.signature for i in inc] == [MR.REGRESSION_SIGNATURE + "2"]
    assert MR.capacity(db)["safe"] is False          # an identity incident comes first
    held = [dict(r, identity={"verdict": "pass"}) for r in worse]
    cleared = MR.regression_watch(db, records=good + held)
    assert cleared["rollback"] is False and cleared["incidents_resolved"]


# ---- F-679 -----------------------------------------------------------------------------------

def test_f679_the_conditioning_matrix_finds_the_minimum_deterministic_fidelity():
    import hashlib

    from PIL import Image

    from brambleloop.visual import conditioning_matrix as CM

    img = Image.new("RGB", (40, 40), (243, 238, 231))
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (164, 139, 90) if x < 20 else (47, 62, 51))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    p1 = CM.derive_passes(buf.getvalue(), ["#A48B5A", "#2F3E33"])
    p2 = CM.derive_passes(buf.getvalue(), ["#A48B5A", "#2F3E33"])
    assert p1["sha256"] == p2["sha256"]                    # deterministic
    assert 0.2 < p1["foreground_share"] < 0.3
    assert set(p1["passes"]["material_masks"]) == {"#A48B5A", "#2F3E33"}
    assert p1["not_produced"] == ["depth", "normals"]
    modalities = {m for arm in CM.ARMS for m in arm}
    assert modalities == set(CM.MODALITIES)
    assert any(len(a) > 1 for a in CM.ARMS)                # hybrids are arms
    db = _db()
    assert CM.minimum_fidelity(db)["state"] == "UNDETERMINED"
    try:
        CM.record_trial(db, arm=("rgb", "depth"), product="p", fidelity="PASS", cost_cad=0.1,
                        output_sha256="d" * 64)
        raise AssertionError("a trial under an unproduced pass was recorded")
    except ValueError:
        pass

    def trial(arm, ok, i):
        CM.record_trial(db, arm=arm, product="p", fidelity="PASS" if ok else "FAIL",
                        cost_cad=0.1, output_sha256=hashlib.sha256(f"{arm}{i}".encode())
                        .hexdigest())
    for i in range(6):
        trial(("rgb",), i < 3, i)                           # RGB alone: 50 %
        trial(("rgb", "material_masks"), True, i)           # hybrid: 100 %
        trial(("rgb", "material_masks", "edges"), True, i)  # more fidelity, also 100 %
    best = CM.minimum_fidelity(db)
    assert best["state"] == "DETERMINED" and best["arm"] == "rgb+material_masks"
    plan = {p["arm"]: p["state"] for p in CM.plan(db)}
    assert plan["depth"] == "UNAVAILABLE" and plan["edges"] == "NEEDS_TRIALS"
    assert "rgb" not in plan


# ---- F-748 / F-680 ---------------------------------------------------------------------------

def test_f748_studio_view_shows_version_route_yield_drift_experiments_and_both_gates():
    from brambleloop.visual import studio_view as SV

    db = _db()
    for i in range(6):
        _cand(db, provider="alpha", sha=f"a{i}")
    _cand(db, provider="alpha", identity="FAIL", outcome="rejected", sha="drift1")
    _cand(db, provider="alpha", truth="FAIL", outcome="rejected", sha="untrue1")
    _cand(db, provider="alpha", laura=False, sha="product1")
    v = SV.canonical_model(db)
    assert v["canonical"]["identity_id"].startswith("laura-r") and v["canonical"]["verified"]
    assert v["best_provider_mode"]["provider"] == "alpha"
    assert v["recent_yield"]["identity"]["judged"] == 8
    assert [d["sha256"] for d in v["rejected_drift_examples"]] == ["drift1"]
    assert "proposals" in v["active_improvement_experiments"]
    by = {i["sha256"]: i for i in v["listing_images"]}
    assert by["a0"]["passed_both"] and not by["drift1"]["passed_both"]
    assert not by["untrue1"]["passed_both"]
    assert by["product1"]["model_identity"] == "NOT_APPLICABLE" and by["product1"]["passed_both"]


def test_f680_evidence_panel_puts_reference_3d_passes_candidates_rejections_final_together():
    from brambleloop.visual import studio_view as SV
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun

    db = _db()
    empty = SV.evidence_panel(db, "s1")
    for part in ("real_benchmark_reference", "brambleloop_3d", "conditioning_passes",
                 "generated_candidates", "final_approved_asset"):
        assert empty[part]["state"] == "ABSENT", part      # absent, never an empty success
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action="assets.gallery_frames", artifact="s1@1.0.0",
                       detail={"slug": "s1", "version": "1.0.0", "disclosed": {
                           "s1": {"frames": [{"sha256": "3d-hero"}]}},
                           "gallery_frames": [{"job": "ANGLE", "sha256": "3d-angle",
                                               "verification": "PASS"}]}))
        s.add(ImageProductionRun(run_key="r1", slug="s1", listing="L1",
                                 status="approved_for_publication"))
        s.add(ImageCandidate(sha256="good", run_key="r1", method="autonomous",
                             provenance_kind="ai", slug="s1", listing="L1", role="hero",
                             references=[{"sha256": "photo1", "kind": "physical_product_photo"},
                                         {"sha256": "cir1", "kind": "pattern_derived"}],
                             checks={"_identity_evidence": {"conditioning": {"refs": 2}}},
                             technical_status="PASS", publishable=True, outcome="accepted"))
        s.add(ImageCandidate(sha256="bad", run_key="r1", method="autonomous",
                             provenance_kind="ai", slug="s1", listing="L1", role="hero",
                             checks={"product_truth": {"status": "FAIL",
                                                       "why": "wrong stitch count"}},
                             technical_status="FAIL", outcome="rejected",
                             failure_categories=["product_fidelity"]))
    p = SV.evidence_panel(db, "s1")
    assert p["real_benchmark_reference"] == ["photo1"]
    assert p["brambleloop_3d"]["disclosed"] == {"s1": ["3d-hero"]}
    assert p["conditioning_passes"]["references_by_kind"]["pattern_derived"] == ["cir1"]
    assert {c["sha256"] for c in p["generated_candidates"]} == {"good", "bad"}
    (rej,) = p["rejected_candidates"]
    assert rej["sha256"] == "bad" and "stitch" in rej["reasons"]["product_truth"]
    assert p["final_approved_asset"] == [{"sha256": "good", "role": "hero"}]


# ---- F-527 -----------------------------------------------------------------------------------

def test_f527_off_palette_and_off_brand_typography_are_detected_and_routed():
    import shutil

    from PIL import Image

    from brambleloop.brand import asset_consistency as AC

    clean = AC.sweep()
    assert clean["marks_checked"] >= 10 and clean["fix_count"] == 0, clean["findings"][:3]
    d = Path(_TMP) / "marks"
    shutil.copytree(AC.MASTERS, d)
    victim = sorted(d.glob("*-colour.svg"))[0]
    victim.write_text(victim.read_text().replace("#2F3E33", "#FF00AA", 1)
                      .replace("#2f3e33", "#FF00AA", 1) + '<text x="0">Brambleloop</text>')
    page = "h1{font-family:'Comic Sans MS',serif;color:#123456} p{font-family:Lora,Georgia,serif}"
    out = AC.sweep(masters=d, pages={"storefront.css": page})
    codes = {(f["code"], f["subject"]) for f in out["findings"]}
    assert ("MARK_OFF_PALETTE", victim.name) in codes and ("MARK_LIVE_TEXT", victim.name) in codes
    assert ("OFF_BRAND_TYPEFACE", "storefront.css") in codes
    assert ("PAGE_OFF_PALETTE", "storefront.css") in codes
    assert out["routes"] == ["brand"]
    small = io.BytesIO()
    Image.new("RGB", (1200, 900)).save(small, format="PNG")
    (f,) = AC.check_raster("hero.png", small.getvalue(), "listing_image")
    assert f["code"] == "ASSET_LOW_RESOLUTION" and f["route_to"] == "publishing"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
