"""W-OWNERIMG: autonomous image production, shared candidate gates, outfit registry, shot
plans and the owner-upload fallback. Offline, SHADOW, no provider, no spend.

The stub generator and stub judges below are test doubles. Production resolves no generator
until W-FLUXAPI registers one, and production judges are `candidate_gates.RealJudges`.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import inspect
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_ART = tempfile.mkdtemp(prefix="ownerimg-art-")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART

from PIL import Image  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, PatternVersion, Product  # noqa: E402

def _release_of(listing):
    from brambleloop.creative.pattern_refs import release_hash_of

    return release_hash_of(_cir(listing))
_colour = [0]


def png(w=2000, h=2000, mode="RGB", fmt="PNG", alpha=255):
    _colour[0] += 7
    c = (_colour[0] % 250, (_colour[0] * 3) % 250, (_colour[0] * 5) % 250)
    im = Image.new(mode, (w, h), c + ((alpha,) if mode == "RGBA" else ()))
    out = io.BytesIO()
    im.save(out, format=fmt)
    return out.getvalue()


def _cir(listing):
    from brambleloop.visual.launch_imagery import _listing_parts

    return _listing_parts(listing)[1][0]


RELEASE = None
RELEASE_GV = None


def make_db():
    global RELEASE, RELEASE_GV
    RELEASE = RELEASE or _release_of("cloudline-baby-blanket")
    RELEASE_GV = RELEASE_GV or _release_of("winter-village-graphghan")
    tmp = tempfile.mkdtemp(prefix="ownerimg-db-")
    db = Database("sqlite:///" + str(Path(tmp) / "s.db"), scratch=True)
    db.create_all()
    for listing, rel in (("cloudline-baby-blanket", RELEASE),
                         ("winter-village-graphghan", RELEASE_GV)):
        cir = _cir(listing)
        with db.session() as s:
            p = Product(slug=cir.slug, title=cir.title or cir.slug)
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                                 certified=True, release_hash=rel))
            j = Job(agent="synthetic", job_type="assets.build", inputs={"release": rel})
            s.add(j)
            s.flush()
            s.add(AuditLog(actor="synthetic", action="assets.built",
                           artifact=f"{cir.slug}@{cir.version}", job_id=j.id,
                           detail={"pdf_sha256_by_terminology": {"US": "a" * 64,
                                                                 "UK": "b" * 64}}))
    return db


def cand(**kw):
    data = kw.pop("data", None) or png()
    base = {"data": data, "slug": "cloudline-baby-blanket", "version": "1.2.0",
            "release": RELEASE[:12], "role": "lifestyle", "provider": "bfl-dashboard",
            "model": "FLUX 3 Image", "prompt": "Laura on a sofa, blanket on her lap",
            "references": [], "laura_present": False, "outfit_id": None,
            "provenance_kind": "ai_generated_owner_submitted"}
    base.update(kw)
    return base


class StubJudges:
    def __init__(self, product="PASS", identity="PASS"):
        self.p, self.i = product, identity

    def product_truth(self, c, bind):
        return {"status": self.p, "why": "stub"}

    def identity(self, c):
        return {"status": self.i, "why": "stub"}

    def anatomy(self, c):
        return {"status": "PASS", "why": "stub"}

    def realism(self, c):
        return {"status": "PASS", "why": "stub"}

    def body_proportions(self, c):
        return {"status": "PASS", "why": "stub"}

    def outfit_consistency(self, c, outfit):
        return {"status": "PASS", "why": "stub"}


class StubGenerator:
    name, paid, max_cost_cad_per_call = "stub", False, 0.0

    def __init__(self):
        self.calls = 0
        self.seen = []

    def prepare_references(self, **kw):
        return [{"kind": "pattern_derived", "data": png(64, 64), "label": "layout"}]

    def generate(self, **kw):
        self.calls += 1
        self.seen.append((kw["role"], [r["kind"] for r in kw["references"]], kw["outfit"]))
        self.repairs = getattr(self, "repairs", []) + [kw.get("repair")]
        return {"data": png(), "provider": "stub", "model": "stub-1",
                "prompt": kw["brief"], "cost_cad": 0.0, "latency_s": 0.01}


GARMENTS = {
    "sage-cardigan-01": {"top_or_dress": "sage-green cardigan over a cream tee",
                         "lower": "dark straight-leg jeans", "shoes": "tan leather loafers",
                         "outerwear": "none", "accessories": "small gold hoops"},
    "oat-jumper-02": {"top_or_dress": "oatmeal crew-neck jumper",
                      "lower": "camel wide-leg trousers", "shoes": "brown ankle boots",
                      "outerwear": "none", "accessories": "thin gold chain"},
}


def approved_outfit(db, oid="sage-cardigan-01"):
    from brambleloop.visual import outfits

    outfits.register(db, outfit_id=oid, garments=GARMENTS[oid], colours=["sage", "cream"])
    return outfits.approve(db, oid)


# ---- intake ------------------------------------------------------------------------------

def test_owner_intake_stores_bytes_unchanged_ai_never_photo_and_approval_separate():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import owner_images
    from brambleloop.visual.image_records import ImageCandidate

    db = make_db()
    data = png()
    out = owner_images.intake(db, data=data, slug="cloudline-baby-blanket", version="1.2.0",
                              release=RELEASE[:12], role="detail", provider="bfl-dashboard",
                              model="FLUX 3 Image", prompt="flat lay", cost_usd=0.048,
                              owner_visual_approval=True)
    assert out["sha256"] == hashlib.sha256(data).hexdigest()
    assert ArtifactStore().get(out["sha256"], db=db) == data
    assert out["provenance_kind"] == "ai_generated_owner_submitted" and out["is_photograph"] is False
    assert out["checks"]["binding"]["status"] == "PASS"
    assert out["checks"]["binding"]["pdf_sha256_by_terminology"]["US"] == "a" * 64
    # Owner liked the look; technical verification is still not PASS, and nothing publishes.
    assert out["owner_visual_approval"] is True
    assert out["technical_status"] != "PASS" and out["publishable"] is False
    assert "realism" in out["unknown"]
    with db.session() as s:
        row = s.get(ImageCandidate, out["candidate"]["candidate_id"])
        assert row.owner_visual_approval is True and row.method == "owner_submitted"
        assert row.technical_status == out["technical_status"] and row.cost_cad > 0.048


def test_binding_refuses_wrong_release_and_uncertified_and_unknown_without_release():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    assert CG.binding(db, "cloudline-baby-blanket", "1.2.0", "deadbeef0000")["status"] == "FAIL"
    assert CG.binding(db, "cloudline-baby-blanket", "9.9.9", RELEASE)["status"] == "FAIL"
    assert CG.binding(db, "cloudline-baby-blanket", "1.2.0", "")["status"] == "UNKNOWN"
    assert CG.binding(db, "cloudline-baby-blanket", "1.2.0", RELEASE[:12])["status"] == "PASS"


def test_image_quality_min_2000_no_transparency_no_webp():
    from brambleloop.visual import candidate_gates as CG

    assert CG.quality(png())["status"] == "PASS"
    assert CG.quality(png(1440, 1440))["status"] == "FAIL"
    assert CG.quality(png(mode="RGBA", alpha=200))["status"] == "FAIL"
    assert CG.quality(png(mode="RGBA", alpha=255))["status"] == "PASS"
    assert CG.quality(png(fmt="WEBP"))["status"] == "FAIL"
    assert CG.quality(b"not an image")["status"] == "FAIL"


def test_roles_generated_never_satisfies_photo_only_or_hero():
    from brambleloop.visual import candidate_gates as CG

    for r in ("proof", "fit", "hero", "whats_included", "materials", "nonsense"):
        assert CG.role(r)["status"] == "FAIL", r
    for r in ("lifestyle", "detail", "colour_context"):
        assert CG.role(r)["status"] == "PASS", r


def test_unknown_never_pass_and_publication_blocked_by_f852_and_etsy_policy():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    v = CG.evaluate(db, cand(role="detail"))     # real judges: fidelity/realism unread
    assert v["technical_status"] == "UNKNOWN" and not v["publishable"]
    joined = " ".join(v["publication"]["blockers"])
    assert "F-852" in joined and "Etsy" in joined
    # Even with every judge stubbed PASS, publication stays blocked (gate not lowered).
    v2 = CG.evaluate(db, cand(role="detail"), judges=StubJudges())
    assert v2["technical_status"] == "PASS" and v2["publishable"] is False
    assert any("F-852" in b for b in v2["publication"]["blockers"])


def test_same_gates_whatever_the_method():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    data = png()
    a = CG.evaluate(db, cand(data=data, role="detail",
                             provenance_kind="ai_generated_autonomous"), judges=StubJudges())
    b = CG.evaluate(db, cand(data=data, role="detail",
                             provenance_kind="ai_generated_owner_submitted"),
                    judges=StubJudges())
    assert {k: c["status"] for k, c in a["checks"].items()} == \
        {k: c["status"] for k, c in b["checks"].items()}
    assert a["publication"] == b["publication"]
    src = inspect.getsource(CG.evaluate).split('"""', 2)[2]
    assert "method" not in src


def test_lifestyle_from_pattern_derived_references_fails_product_truth():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    v = CG.evaluate(db, cand(references=[{"sha256": "c" * 64, "kind": "pattern_derived"}]))
    pt = v["checks"]["product_truth"]
    assert pt["status"] == "FAIL" and pt["lifestyle_evidence"]["status"] == "FAIL"


# ---- outfits -----------------------------------------------------------------------------

def test_laura_without_outfit_is_unknown_and_blocks():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    v = CG.evaluate(db, cand(laura_present=True), judges=StubJudges())
    assert v["checks"]["outfit"]["status"] == "UNKNOWN"
    assert v["technical_status"] == "UNKNOWN" and not v["publishable"]


def test_same_outfit_same_listing_allowed_other_listing_refused():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import outfits

    db = make_db()
    approved_outfit(db)
    one = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01"),
                      judges=StubJudges())
    two = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01",
                               role="colour_context"), judges=StubJudges())
    assert one["checks"]["outfit"]["status"] == "PASS"
    assert two["checks"]["outfit"]["status"] == "PASS"
    assert len(outfits.get(db, "sage-cardigan-01")["uses"]) == 2
    other = CG.evaluate(db, cand(slug="winter-village-graphghan", version="1.3.0",
                                 release=RELEASE_GV[:12], laura_present=True,
                                 outfit_id="sage-cardigan-01"), judges=StubJudges())
    assert other["checks"]["outfit"]["status"] == "FAIL"
    assert "outfit_duplication" in other["failure_categories"]


def test_outfit_never_alters_identity():
    from brambleloop.visual import canonical, outfits
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    g = GARMENTS["oat-jumper-02"]
    for bad in ({"identity_changes": {"hair": "bob"}, "garments": g},
                {"garments": {**g, "accessories": "a new haircut"}},
                {"garments": g, "reference_hashes": [canonical.FACE_SHA256]},
                {"garments": {"top_or_dress": "linen shirt", "shoes": "boots"}}):
        try:
            outfits.register(db, outfit_id="bad-outfit", **bad)
        except outfits.OutfitRefused:
            continue
        raise AssertionError(f"identity change accepted: {bad}")
    approved_outfit(db)
    # A registered outfit never rescues a drifted face, and the use is not recorded.
    v = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01"),
                    judges=StubJudges(identity="FAIL"))
    assert v["checks"]["identity"]["status"] == "FAIL" and v["technical_status"] == "FAIL"
    assert "identity_drift" in v["failure_categories"]
    assert outfits.get(db, "sage-cardigan-01")["uses"] == []
    assert [g["gate"] for g in v["laura_gates"]][0] == "canonical_identity"


def test_outfit_reservation_release_and_replace():
    from brambleloop.visual import outfits

    db = make_db()
    approved_outfit(db, "sage-cardigan-01")
    approved_outfit(db, "oat-jumper-02")
    assert outfits.reserve(db, "sage-cardigan-01", "cloudline-baby-blanket")["status"] == "PASS"
    assert outfits.reserve(db, "sage-cardigan-01", "hexagon-coaster-set")["status"] == "FAIL"
    assert outfits.release(db, "sage-cardigan-01", "cloudline-baby-blanket", why="run failed")[
        "released"]
    outfits.check_use(db, "sage-cardigan-01", listing="cloudline-baby-blanket",
                      product="cloudline-baby-blanket@1.2.0", image_sha256="d" * 64)
    assert not outfits.release(db, "sage-cardigan-01", "cloudline-baby-blanket",
                               why="x")["released"]
    rep = outfits.replace(db, "sage-cardigan-01", "oat-jumper-02", "cloudline-baby-blanket")
    assert rep["replaced"]
    old = outfits.get(db, "sage-cardigan-01")
    assert old["approval_state"] == "retired" and old["listing"] == "cloudline-baby-blanket"
    assert outfits.reserve(db, "sage-cardigan-01", "hexagon-coaster-set")["status"] == "FAIL"
    assert outfits.reserve(db, "unregistered-x", "hexagon-coaster-set")["status"] == "UNKNOWN"


def test_laura_gate_order_adds_outfit_and_identity_record_unchanged():
    from brambleloop.laura.core import identity as LI
    from brambleloop.visual import canonical

    g = canonical.LAURA_LISTING_GATES
    assert g[0] == "canonical_identity" and g[1] == "body_proportions"
    assert g.index("outfit_uniqueness") == g.index("product_truth_if_product_shown") + 1
    assert g.index("outfit_consistency") == g.index("outfit_uniqueness") + 1
    assert set(canonical.CUSTOMER_FACING_GATES) < set(g) and len(g) == 10
    assert LI.sha256_of(LI.record()) == LI.CURRENT_SHA256


# ---- release_gates role gap ---------------------------------------------------------------

def test_role_jobs_know_proof_and_lifestyle_without_lowering():
    from brambleloop.gates.asset_truth import AssetClass
    from brambleloop.publish import eligibility as el
    from brambleloop.publish import physical_upgrade
    from brambleloop.publish.release_gates import ROLE_JOBS

    assert ROLE_JOBS["proof"] == (el.PROOF, el.PHYSICAL_PROOF)
    assert ROLE_JOBS["lifestyle"] == (el.LIFESTYLE, el.CONVERSION_CREATIVE)
    el.Candidate(asset_id="p", medium=AssetClass.PHYSICAL_PRODUCT_PHOTO,
                 purpose=el.PHYSICAL_PROOF, job=el.PROOF, position=3)
    try:
        el.Candidate(asset_id="g", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=el.PHYSICAL_PROOF, job=el.PROOF, position=3)
        raise AssertionError("an AI image was allowed to claim physical proof")
    except el.EligibilityRefused:
        pass
    ai = el.Candidate(asset_id="g", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                      purpose=el.CONVERSION_CREATIVE, job=el.LIFESTYLE, position=2)
    passed = [el.GateResult(g, el.PASSED) for g in el.GATES]
    assert not el.may_export(ai, passed)["may_export"]          # F-852 kept
    photo = el.Candidate(asset_id="p", medium=AssetClass.PHYSICAL_PRODUCT_PHOTO,
                         purpose=el.CONVERSION_CREATIVE, job=el.LIFESTYLE, position=2)
    assert el.may_export(photo, passed)["may_export"]
    assert physical_upgrade.DECLARABLE_ROLES == ("proof", "lifestyle")
    try:
        physical_upgrade.plan_upgrade(make_db(), 1, role="hero")
        raise AssertionError("a photograph was declared into an unmapped role")
    except physical_upgrade.UpgradeRefused:
        pass


# ---- shot plans ---------------------------------------------------------------------------

def test_shot_plans_for_all_eight_and_wearable_template():
    from brambleloop.products import launch0
    from brambleloop.visual import shot_plans as SP

    plans = SP.all_plans()["plans"]
    assert len(plans) == 8 and set(plans) == set(launch0.LAUNCH0_SLUGS)
    for slug, p in plans.items():
        assert p["roles"] and p["roles"][0]["role"] == "hero", slug
        assert all(r["job"] and r["why"] for r in p["roles"]), slug
    cl = plans["cloudline-baby-blanket"]
    assert 7 <= cl["image_count_with_conditional"] <= 9 and cl["image_count"] == 7
    life = [r for r in cl["roles"] if r["role"] == "lifestyle"][0]
    assert life["laura"] and life["sources"][SP.DISCLOSED] == SP.NOT_DRAWABLE
    assert life["sources"][SP.GENERATED] == SP.BLOCKED_F852 and "F-030" in life["required_by"]
    assert "lifestyle" not in [r["role"] for r in plans["nordic-star-ornaments"]["roles"]]
    w = SP.wearable_template()
    roles = {r["role"]: r for r in w["roles"]}
    assert {"fit", "angle", "construction"} <= set(roles)
    assert roles["fit"]["sources"] == {SP.DISCLOSED: SP.NOT_DRAWABLE,
                                       SP.GENERATED: SP.PURPOSE_REFUSED, SP.PHOTO: SP.SATISFIES}


# ---- the autonomous workflow -------------------------------------------------------------

def drain(db, *, generator, judges, limit=60):
    """A worker loop over the real JobQueue: claim, run the stage, complete."""
    from brambleloop.queue.durable import DuplicateJob, JobQueue
    from brambleloop.visual import image_production as IP

    q = JobQueue(db)

    def follow(inputs, key):
        try:
            return q.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=key)
        except DuplicateJob:
            return None

    ran = 0
    while ran < limit:
        job = q.claim("test-worker", job_types=[IP.JOB_TYPE])
        if job is None:
            break
        out = IP.run_stage(db, dict(job.inputs), follow=follow, generator=generator,
                           judges=judges)
        q.complete(job.id, outputs={"run_key": out.get("run_key")}, worker="test-worker",
                   lease_token=job.lease_token)
        ran += 1
    return follow, ran


def test_unattended_end_to_end_shadow_stub_reaches_owner_card_without_owner_step():
    from brambleloop.app.command_center import notifications
    from brambleloop.visual import image_production as IP

    db = make_db()
    gen = StubGenerator()
    follow, _ = drain(db, generator=gen, judges=StubJudges())       # empty queue: no-op
    first = IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    again = IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    assert first["enqueued"] and not again["enqueued"]                 # one run per release
    _, ran = drain(db, generator=gen, judges=StubJudges())
    assert ran >= 10
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "ready_for_owner_review", run
    # Styling chose the outfit; anchor + lifestyle + scale + colour-context were generated.
    assert run["outfit_id"].startswith("auto-") and gen.calls == 4
    anchor = [kinds for role, kinds, _o in gen.seen if role == "product_anchor"][0]
    assert "laura_canonical" not in anchor                         # product-only: no Laura
    laura_calls = [(kinds, o) for role, kinds, o in gen.seen if role != "product_anchor"]
    assert len(laura_calls) == 3
    assert all(k.count("laura_canonical") == 3 for k, _o in laura_calls)
    assert {o["outfit_id"] for _k, o in laura_calls} == {run["outfit_id"]}
    assert run["card"]["campaign_consistency"]["status"] == "PASS"
    card = run["card"]
    assert card["owner_approval_is_not_technical_verification"]
    assert any("F-852" in b for b in card["publication_blockers"])
    board = {p["listing"]: p for p in IP.status_board(db)["products"]}
    assert board["cloudline-baby-blanket"]["state"] == "ready_for_owner_review"
    assert board["hexagon-coaster-set"]["state"] == "awaiting_certified_pattern"
    keys = [c["dedupe_key"] for c in IP.notification_candidates(db)]
    assert keys == [f"image_gallery:{run['run_key']}:ready_for_owner_review"]
    r1 = notifications.refresh(db)
    r2 = notifications.refresh(db)
    assert r1["created"] >= 1 and r2["created"] == 0               # deduplicated
    # The owner's approval re-checks the gates and cannot override F-852.
    dec = IP.approve(db, run["run_key"], decided_by="owner:test")
    assert dec["approved"] is False and any("F-852" in b for b in dec["blockers"])
    assert IP.get_run(db, run["run_key"])["state"] == "ready_for_owner_review"
    learn = IP.learning_summary(db, slug="cloudline-baby-blanket")
    assert learn["accepted"] >= 1 and learn["cost_per_accepted_cad"] == 0.0


def test_default_generator_is_flux3_and_refused_while_the_gate_is_closed():
    from brambleloop.visual import image_production as IP

    db = make_db()
    gen = IP.resolve_generator(db)
    assert gen is not None and gen.name == "flux3-image-stages" and gen.paid
    follow, _ = drain(db, generator=None, judges=StubJudges())
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    drain(db, generator=None, judges=StubJudges())
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked" and "image_generation gate closed" in run["blocked_reason"]
    assert run["spent_cad"] == 0.0 and run["generation_calls"] == 0
    assert not run["attempts_exhausted"] and IP.notification_candidates(db) == []


def test_real_judges_block_at_unverifiable_fidelity():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db = make_db()
    follow, _ = drain(db, generator=StubGenerator(), judges=CG.RealJudges(db))
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    drain(db, generator=StubGenerator(), judges=CG.RealJudges(db))
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked" and "fidelity cannot be verified" in run["blocked_reason"]
    assert IP.notification_candidates(db) == []


def test_repair_is_bounded_targeted_then_blocked_and_notified():
    from brambleloop.visual import image_production as IP

    class LifestyleFails(StubJudges):
        def product_truth(self, c, bind):
            if c.get("role") == "lifestyle":
                return {"status": "FAIL", "why": "border invented",
                        "codes": ["INVENTED_EDGING", "WRONG_CRAFT_TEXTURE"]}
            return {"status": "PASS", "why": "stub"}

    db = make_db()
    gen = StubGenerator()
    follow, _ = drain(db, generator=gen, judges=LifestyleFails())
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    drain(db, generator=gen, judges=LifestyleFails())
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked" and run["attempts_exhausted"]
    assert gen.calls == 1 + IP.MAX_ATTEMPTS_PER_ROLE + 2 <= IP.MAX_GENERATION_CALLS
    repairs = [r for r in gen.repairs if r]
    assert len(repairs) == IP.MAX_ATTEMPTS_PER_ROLE - 1
    kinds = {d["kind"] for d in repairs[0]["directives"]}
    assert kinds == {"prompt_negative", "reference_change"}
    assert "no edging" in " ".join(n for d in repairs[0]["directives"]
                                   for n in d.get("negatives", []))
    note = IP.notification_candidates(db)
    assert len(note) == 1 and note[0]["severity"] == "high"
    assert "recommended fix" in note[0]["consequence"]
    learn = IP.learning_summary(db, slug="cloudline-baby-blanket")
    assert learn["failure_categories"].get("INVENTED_EDGING") == IP.MAX_ATTEMPTS_PER_ROLE
    assert learn["failure_categories"].get("product_fidelity") == IP.MAX_ATTEMPTS_PER_ROLE


def test_unrouted_code_is_not_repaired_and_unverifiable_count_never_passes():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import repair_routes as RR

    class Unrouted(StubJudges):
        def product_truth(self, c, bind):
            if c.get("role") == "lifestyle":
                return {"status": "FAIL", "why": "x", "codes": ["SOMETHING_NEW"]}
            return {"status": "PASS", "why": "stub"}

    db = make_db()
    gen = StubGenerator()
    follow, _ = drain(db, generator=gen, judges=Unrouted())
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    drain(db, generator=gen, judges=Unrouted())
    assert gen.calls == 4 and not any(gen.repairs)               # no blind regeneration
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked"

    class CountHidden(StubJudges):
        def product_truth(self, c, bind):
            return {"status": "PASS", "why": "looks right", "codes": [RR.UNVERIFIABLE_COUNT]}

    v = CG.evaluate(db, cand(role="detail"), judges=CountHidden())
    assert v["checks"]["product_truth"]["status"] == "UNKNOWN"
    assert v["technical_status"] == "UNKNOWN" and not v["publishable"]
    assert RR.route([RR.UNVERIFIABLE_COUNT])["stays_unknown"] == [RR.UNVERIFIABLE_COUNT]


def test_wrap_experiment_is_the_seeded_learning_example():
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import repair_routes as RR

    shared = RR.shared_codes()
    assert set(shared["codes"]) == {"INVENTED_END_BAND_TREATMENT", "INVENTED_EDGING",
                                    "WRONG_CRAFT_TEXTURE", "UNVERIFIABLE_COUNT"}, shared
    assert set(shared["codes"]) <= set(RR.ROUTES)                  # every shared code routed
    db = make_db()
    first, again = RR.seed_experiment(db), RR.seed_experiment(db)
    assert first["seeded"] and not again["seeded"]
    assert shared["source"] == "creative.failure_codes.ALL_CODES"
    learn = IP.learning_summary(db, slug="reading-nook-cable-wrap")
    assert learn["candidates"] == 1 and learn["accepted"] == 0
    assert learn["cost_per_accepted_cad"] is None
    assert learn["failure_categories"]["WRONG_CRAFT_TEXTURE"] == 1
    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        row = s.get(ImageCandidate, first["candidate_id"])
        assert row.method == "owner_manual" and row.owner_visual_approval is True
        assert row.checks["identity"]["status"] == "UNKNOWN" and not row.publishable


def test_paid_generator_needs_the_image_generation_gate():
    from brambleloop.visual import image_production as IP

    class Paid(StubGenerator):
        paid = True

    db = make_db()
    follow, _ = drain(db, generator=Paid(), judges=StubJudges())
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    gen = Paid()
    drain(db, generator=gen, judges=StubJudges())
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked" and "image_generation gate closed" in run["blocked_reason"]
    assert gen.calls == 0


# ---- D-W4-LAURA-FLUX3 -------------------------------------------------------------------

def test_one_listing_keeps_one_outfit_across_its_campaign():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import outfits
    from brambleloop.visual import shot_plans as SP

    db = make_db()
    plan = SP.campaign_plan("cloudline-baby-blanket")
    assert plan["image_count"] == 7 and plan["one_outfit"] and plan["laura_in_campaign"]
    assert len({r["job"] for r in plan["roles"]}) == 7                # one job each, no filler
    follow, _ = drain(db, generator=StubGenerator(), judges=StubJudges())
    IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
    drain(db, generator=StubGenerator(), judges=StubJudges())
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    view = IP.readiness(db, "cloudline-baby-blanket", run_key_=run["run_key"])
    laura = [e["candidate"] for e in view["roles"] if e.get("laura") and e.get("candidate")]
    assert len(laura) == 3 and {c["outfit_id"] for c in laura} == {run["outfit_id"]}
    approved_outfit(db, "oat-jumper-02")
    assert outfits.reserve(db, "oat-jumper-02", "cloudline-baby-blanket")["status"] == "FAIL"
    v = CG.evaluate(db, cand(laura_present=True, outfit_id="oat-jumper-02", role="size"),
                    judges=StubJudges())
    assert v["checks"]["outfit"]["status"] == "FAIL" and not v["publishable"]


def test_a_different_listing_cannot_reuse_a_complete_outfit():
    from brambleloop.visual import outfits, styling

    db = make_db()
    approved_outfit(db)
    assert outfits.reserve(db, "sage-cardigan-01", "cloudline-baby-blanket")["status"] == "PASS"
    try:
        outfits.register(db, outfit_id="same-clothes-new-id",
                         garments=dict(GARMENTS["sage-cardigan-01"]))
        raise AssertionError("the same complete outfit was registered twice")
    except outfits.OutfitRefused:
        pass
    other = styling.select_for_listing(db, "winter-village-graphghan")
    assert outfits.signature(other["outfit"]["garments"]) != \
        outfits.signature(GARMENTS["sage-cardigan-01"])


def test_styling_is_chosen_automatically_deterministic_and_avoids_used():
    from brambleloop.visual import outfits, styling

    a = styling.select("cloudline-baby-blanket", category="baby", product_colours=["cream"])
    b = styling.select("cloudline-baby-blanket", category="baby", product_colours=["cream"])
    assert a == b and a["outfit"]["garments"]["top_or_dress"]
    assert "cream" not in a["outfit"]["garments"]["top_or_dress"]      # no clash with product
    assert a["concept"]["setting"] in styling.SETTINGS["baby"]
    c = styling.select("cloudline-baby-blanket", category="baby", product_colours=["cream"],
                       used_signatures={outfits.signature(a["outfit"]["garments"])},
                       used_settings={a["concept"]["setting"]})
    assert outfits.signature(c["outfit"]["garments"]) != outfits.signature(
        a["outfit"]["garments"])
    assert c["concept"]["setting"] != a["concept"]["setting"]
    assert "generic catalogue pose" in " ".join(a["concept"]["avoid"])


def test_product_truth_cannot_be_bypassed_and_no_publication_without_approvals():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    bad = CG.evaluate(db, cand(role="detail"), judges=StubJudges(product="FAIL"))
    assert bad["technical_status"] == "FAIL" and not bad["publishable"]
    assert not bad["publication"]["may_export"]
    approved_outfit(db)
    good = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01"),
                       judges=StubJudges())
    assert good["technical_status"] == "PASS" and not good["publishable"]
    joined = " ".join(good["publication"]["blockers"])
    assert "Laura publication gate" in joined and "F-852" in joined


def test_body_proportions_and_outfit_consistency_unknown_until_judged():
    from brambleloop.visual import candidate_gates as CG

    db = make_db()
    approved_outfit(db)
    v = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01"))
    assert v["checks"]["body_proportions"]["status"] == "UNKNOWN"
    assert v["checks"]["outfit_consistency"]["status"] == "UNKNOWN"

    class Drift(StubJudges):
        def body_proportions(self, c):
            return {"status": "FAIL", "why": "bust flattened against the torso reference"}

        def outfit_consistency(self, c, outfit):
            return {"status": "FAIL", "why": "cardigan changed to a coat"}

    d = CG.evaluate(db, cand(laura_present=True, outfit_id="sage-cardigan-01"), judges=Drift())
    assert {"body_proportion_drift", "outfit_consistency"} <= set(d["failure_categories"])


def test_incompatible_gallery_mix_is_refused():
    from brambleloop.visual import candidate_gates as CG

    row = {"listing": "cloudline-baby-blanket", "version": "1.2.0", "release": RELEASE,
           "cir_fingerprint": "f1", "laura_present": True, "outfit_id": "a"}
    assert CG.campaign_consistency([row, dict(row)])["status"] == "PASS"
    assert CG.campaign_consistency([row, {**row, "version": "1.3.0"}])["status"] == "FAIL"
    assert CG.campaign_consistency([row, {**row, "cir_fingerprint": "f2"}])["status"] == "FAIL"
    assert CG.campaign_consistency([row, {**row, "outfit_id": "b"}])["status"] == "FAIL"


def test_reduced_identity_conditioning_is_refused():
    from unittest.mock import patch

    from brambleloop.visual import canonical
    from brambleloop.visual import image_production as IP

    db = make_db()
    real = canonical.reference_file
    gen = StubGenerator()
    with patch.object(canonical, "reference_file",
                      lambda f: "" if f == "torso_fit_reference" else real(f)):
        follow, _ = drain(db, generator=gen, judges=StubJudges())
        IP.trigger(follow, slug="cloudline-baby-blanket", version="1.2.0", release=RELEASE)
        drain(db, generator=gen, judges=StubJudges())
    run = IP.get_run(db, IP.run_key("cloudline-baby-blanket", "1.2.0", RELEASE))
    assert run["state"] == "blocked" and "reduced identity conditioning" in run["blocked_reason"]
    assert [r for r, _k, _o in gen.seen] == ["product_anchor"]


def test_runtime_wiring():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority.classes import JOB_CLASS, ActionClass
    from brambleloop.runtime import release
    from brambleloop.runtime.worker import handlers

    assert "visual.image_production" in handlers.known()
    pub = [a for a in DEFAULT_AGENTS if a["name"] == "publishing"][0]
    assert "visual.image_production" in pub["allowed_job_types"]
    assert JOB_CLASS["visual.image_production"] is ActionClass.BUILD
    src = inspect.getsource(release.handle_assets_build)
    assert 'ctx.enqueue("publishing", "visual.image_production"' in src
    from brambleloop.app.command_center.api import make_router

    paths = {r.path for r in make_router(None).routes}
    assert {"/api/cc/images", "/api/cc/owner-images", "/api/cc/images/runs/approve",
            "/api/cc/images/plans"} <= paths
    view = ROOT / "src/brambleloop/app/command_center/static/js/views/images.js"
    assert "export async function render" in view.read_text()


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
