"""The flagship product, end to end, and then deliberately attacked.

Two halves. The first runs one real product from a market scan to a finished PDF, a price, a
listing and a launch plan, unattended, and checks the artefacts rather than the job statuses:
a green pipeline that produced a 26 cm "throw" is a green pipeline that failed.

The second half is the part that matters more. A release chain nobody has attacked is a
release chain nobody has tested. Each attack below is something a real system does to itself
eventually -- a transcription slip in a motif, a stale chart, a listing claim that drifted
from the pattern, a support agent trying to be helpful -- and each one must be rejected by
construction rather than by a reviewer noticing.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_ART = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import PermissionDenied, Registry  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Op, Row  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.commerce import pricing as pricing_mod  # noqa: E402
from brambleloop.commerce import seo as seo_mod  # noqa: E402
from brambleloop.core.artifacts import ArtifactMissing, ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Product  # noqa: E402
from brambleloop.gates.asset_truth import (  # noqa: E402
    Asset, AssetClass, Claims, Provenance, check_assets,
)
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.support.concierge import (  # noqa: E402
    Concierge, SupportCannotAmendPatterns,
)

FLAGSHIP = "nordic-forest-mosaic-throw"
TODAY = date(2026, 9, 17)

_RUN: dict = {}


def _run_once() -> dict:
    """One full unattended cycle, cached so the suite is not twelve identical pipelines."""
    if _RUN:
        return _RUN
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/run.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {"as_of": TODAY.isoformat()})
    w = Worker(db, "run-worker")
    for _ in range(900):
        if not w.run_once():
            break
    _RUN["db"] = db
    return _RUN


def _outputs(db: Database, job_type: str) -> list[dict]:
    with db.session() as s:
        return [j.outputs for j in s.scalars(select(Job))
                if j.job_type == job_type and j.status == JobStatus.DONE and j.outputs]


def _flagship(db: Database, job_type: str) -> dict:
    rows = [o for o in _outputs(db, job_type) if o.get("slug") == FLAGSHIP]
    assert rows, f"no completed {job_type} for {FLAGSHIP}"
    return rows[0]


# ---- the full run ---------------------------------------------------------


def test_the_whole_chain_runs_unattended_with_no_unexpected_failures():
    db = _run_once()["db"]
    with db.session() as s:
        broken = [(j.job_type, (j.last_error or "")[:120]) for j in s.scalars(select(Job))
                  if j.status in (JobStatus.FAILED, JobStatus.DEAD)
                  and j.job_type != "store.publish"]
    assert not broken, broken
    # Every publish attempt is refused, and refusal is the designed outcome in shadow mode.
    with db.session() as s:
        refused = [j for j in s.scalars(select(Job))
                   if j.job_type == "store.publish" and j.status == JobStatus.DEAD]
    assert refused, "nothing even tried to publish, so the refusal proved nothing"


def test_the_flagship_uses_the_engineered_design_not_the_template():
    db = _run_once()["db"]
    with db.session() as s:
        drafted = [a for a in s.scalars(select(AuditLog))
                   if a.action == "cir.drafted" and a.artifact
                   and a.artifact.startswith(FLAGSHIP)]
    assert drafted, "the flagship was never drafted"
    assert any(a.detail.get("source") == "engineered design" for a in drafted), \
        "the flagship shipped the generic striped-panel template"


def test_the_flagship_is_a_plausible_physical_object():
    """The arithmetic can be internally consistent and still describe something absurd."""
    db = _run_once()["db"]
    assets = _flagship(db, "assets.build")
    w, h = assets["finished_size_cm"]
    assert 70 <= w <= 140, f"a throw {w} cm wide is not a throw"
    assert 100 <= h <= 200, f"a throw {h} cm long is not a throw"
    total_m = sum(assets["yardage"].values())
    assert 500 <= total_m <= 2500, f"{total_m:.0f} m of yarn for a throw is not credible"
    assert assets["calibrated"] is False, "nothing has been physically tested yet"
    assert assets["tolerance"] >= 0.2, "an uncalibrated estimate needs a stated tolerance"


def test_the_pdf_is_real_and_hashed():
    db = _run_once()["db"]
    assets = _flagship(db, "assets.build")
    assert assets["pages"] >= 5
    assert len(assets["pdf_sha256"]) == 64
    store = ArtifactStore()
    data = store.get(assets["pdf_sha256"])
    assert data.startswith(b"%PDF"), "the stored artifact is not a PDF"
    assert len(data) > 10_000


def test_storage_is_honest_that_it_is_not_durable():
    """No object storage is provisioned. The system must say so, not imply otherwise."""
    db = _run_once()["db"]
    with db.session() as s:
        warned = [a for a in s.scalars(select(AuditLog))
                  if a.action == "assets.storage_not_durable"]
    assert warned, "an ephemeral artifact store must announce itself"
    assert _flagship(db, "assets.build")["pdf_sha256"], "the hash is the durable part"


def test_pricing_survives_etsy_fees_and_carries_no_fake_discount():
    db = _run_once()["db"]
    price = [o for o in _outputs(db, "pricing.position") if o.get("slug") == FLAGSHIP][0]
    assert 8.5 <= price["price_cad"] <= 14.0, price
    assert price["net_cad"] < price["price_cad"], "fees were not deducted at all"
    assert price["take_rate"] > 0.09, "Etsy's take is roughly 10%; this understates it"
    assert price["net_cad"] > 9.0


def test_the_listing_only_claims_what_the_pattern_can_support():
    db = _run_once()["db"]
    listing = _flagship(db, "listing.seo")["listing"]
    assets = _flagship(db, "assets.build")

    assert listing["title"].lower().count("pattern") >= 1
    assert len(listing["title"]) <= seo_mod.TITLE_MAX
    assert len(listing["tags"]) <= seo_mod.TAG_MAX_COUNT
    assert all(len(t) <= seo_mod.TAG_MAX_CHARS for t in listing["tags"])
    assert all(len(t.split(" ")) >= 2 for t in listing["tags"]), \
        f"single-word tags cannot rank for a new shop: {listing['tags']}"

    body = listing["description"]
    assert assets["size_label"] in body, "the listing must quote the computed finished size"
    assert "estimates" in body and "range" in body, "yardage must be framed as an estimate"
    assert "not a finished item" in body, "a pattern listing must say it is a pattern"
    assert "AI assistance" in body, "AI involvement is disclosed, not buried"


def test_the_launch_plan_is_anchored_on_the_buying_window_not_the_holiday():
    db = _run_once()["db"]
    plan = [o for o in _outputs(db, "launch.plan") if o.get("slug") == FLAGSHIP][0]
    assert plan["window_opens"] < "2026-10-01", plan
    assert plan["window_closes"] < "2026-12-01", "the window must close before Christmas"
    assert plan["launch_on"] <= plan["window_closes"]
    assert plan["compressed"] is True
    assert any("window opened" in w for w in plan["warnings"]), plan["warnings"]


def test_support_answers_from_the_released_version():
    db = _run_once()["db"]
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == FLAGSHIP))
        assert product is not None
    q = JobQueue(db)
    job = q.enqueue("support", "support.reply", {
        "slug": FLAGSHIP, "version": "1.0.0",
        "question": "how many stitches should I have at the end of row 12?"})
    assert Worker(db, "support-worker").run_once() is True
    out = q.get(job.id).outputs
    assert out["cited_version"] == f"{FLAGSHIP}@1.0.0"
    assert out["cited_rows"] == [12]
    assert "144 stitches" in out["body"], out["body"]
    assert out["sent"] is False, "shadow mode drafted a reply and marked it sent"


# ---- attacks --------------------------------------------------------------


def test_attack_a_single_wrong_stitch_in_the_motif_is_caught():
    """One transcription slip in one row. This is the realistic failure, not a total fiction."""
    cir = nf.build("throw")
    victim = cir.components[0].rows[40]
    # Rows are a repeat of the motif's runs, so the slip goes inside the repeat -- which is
    # exactly where a real transcription error lands, and where it is multiplied twelve times.
    unit = victim.ops[0].ops
    idx = next(i for i, op in enumerate(unit) if op.count >= 2)
    unit[idx] = Op(unit[idx].stitch, unit[idx].count - 1)

    result = compile_cir(cir)
    assert not result.ok, "a row that is one stitch short compiled clean"
    codes = {f.code for f in result.errors}
    assert codes & {"COUNT_MISMATCH", "UNDERRUN"}, codes


def test_attack_a_wrong_pattern_cannot_become_a_pdf():
    cir = nf.build("baby")
    cir.components[0].rows[5].declared_count = 999
    try:
        build_pattern_pdf(cir)
    except ValueError as e:
        assert "fails compilation" in str(e)
    else:
        raise AssertionError("a PDF was rendered for a pattern that does not compile")


def test_attack_customer_text_that_drifts_from_the_pattern_is_caught():
    """The written instructions are what the customer follows; they must match the source."""
    cir = nf.build("baby")
    result = compile_cir(cir)
    text = write_pattern(cir, result)
    assert compare(cir, text, "US") == [], "the honest text already disagreed"

    # A plausible edit: someone "tidies" a row and changes what it says.
    tampered = text.replace("sc in next 5 sts", "sc in next 6 sts", 1)
    assert tampered != text, "the tamper did not apply; the test proves nothing"
    findings = compare(cir, tampered, "US")
    assert findings, "edited customer text passed reverse compilation unchallenged"


def test_attack_a_chart_from_a_different_size_cannot_pass_as_this_one():
    """A stale asset is the easiest mistake to make and the hardest to see."""
    baby = nf.build("baby")
    large = nf.build("large")
    baby_twin = build_twin(baby, compile_cir(baby))
    large_twin = build_twin(large, compile_cir(large))
    assert baby_twin.chart_grid() != large_twin.chart_grid()
    assert baby_twin.width_cm != large_twin.width_cm

    store = ArtifactStore()
    import io

    from brambleloop.publish.charts import render_chart

    buf = io.BytesIO()
    render_chart(large, large_twin).save(buf, format="PNG")
    stored = store.put("k", buf.getvalue(), "image/png")
    # The hash recorded for the large chart cannot vouch for the baby chart's bytes.
    buf2 = io.BytesIO()
    render_chart(baby, baby_twin).save(buf2, format="PNG")
    other = store.put("k", buf2.getvalue(), "image/png")
    assert stored.sha256 != other.sha256


def test_attack_a_size_claim_the_pattern_does_not_support_is_blocked():
    cir = nf.build("baby")
    twin = build_twin(cir, compile_cir(cir))
    lying = Asset(
        asset_id="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="asset_truth", tool="twin@1"),
        depicts_stitches=sorted(twin.stitch_types_used),
        depicts_colors=sorted(c for c in twin.colors_used if c), is_hero=True,
        claims=Claims(finished_width_cm=220.0, finished_height_cm=240.0),
    )
    findings = check_assets([lying], cir, twin)
    assert any(f.code.startswith("CLAIM_SIZE") for f in findings), findings


def test_attack_a_motif_the_pattern_does_not_contain_is_blocked():
    cir = nf.build("baby")
    twin = build_twin(cir, compile_cir(cir))
    invented = Asset(
        asset_id="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="asset_truth", tool="twin@1"),
        depicts_stitches=sorted(twin.stitch_types_used) + ["tr"],
        depicts_colors=sorted(c for c in twin.colors_used if c) + ["gold"],
        is_hero=True, claims=Claims(),
    )
    findings = check_assets([invented], cir, twin)
    codes = {f.code for f in findings}
    assert codes & {"ASSET_MOTIF_ABSENT", "ASSET_COLOR_ABSENT"}, codes


def test_the_chart_is_published_as_a_readable_repeat_not_a_pixel_field():
    """A 144 x 120 chart on one page gives each stitch about a pixel. That is not a chart."""
    from brambleloop.publish.charts import crop_grids, detect_repeat, render_chart

    cir = nf.build("throw")
    twin = build_twin(cir, compile_cir(cir))
    grid, colour_grid = twin.chart_grid(), twin.color_grid()
    cols, rows = detect_repeat(grid, colour_grid)
    assert (cols, rows) == (nf.MOTIF_WIDTH, len(nf.MOTIF)), (cols, rows)

    grids = crop_grids(grid, colour_grid, cols, rows)
    img = render_chart(cir, twin, grids=grids, caption="one repeat")
    # Every cell must be big enough to carry a legible glyph.
    assert img.width / cols >= 16, f"{img.width / cols:.1f} px per stitch is unreadable"


def test_the_detected_repeat_is_the_real_one_not_a_convenient_one():
    """Claiming a repeat the fabric does not have would mislabel the whole chart."""
    from brambleloop.publish.charts import detect_repeat

    cir = nf.build("baby")
    twin = build_twin(cir, compile_cir(cir))
    grid, colour_grid = twin.chart_grid(), twin.color_grid()
    cols, rows = detect_repeat(grid, colour_grid)
    for i, row in enumerate(grid):
        for j, cell in enumerate(row):
            assert cell == grid[i % rows][j % cols], f"repeat lies at row {i}, column {j}"
            assert colour_grid[i][j] == colour_grid[i % rows][j % cols]


def test_a_pipeline_upgrade_reaches_products_that_already_shipped():
    """Found in production, not in a test.

    Fifteen products were certified before listing imagery, search coverage and the content
    ecosystem existed. The next cycle ran, reported success, and produced nothing: the
    downstream idempotency keys were already taken, so every stage after certification
    collapsed silently. Certification is correctly once-per-version; everything after it has
    to be reachable again when the code that does it changes.
    """
    import tempfile as _tempfile

    from sqlalchemy import select as _select

    from brambleloop.agents.registry import Registry as _Registry
    from brambleloop.core.db import Database as _Database
    from brambleloop.core.models import Collection, ContentPiece, Listing, ListingAsset
    from brambleloop.queue.durable import JobQueue as _JobQueue
    from brambleloop.runtime.release import CHAIN_VERSION, chain_key
    from brambleloop.runtime.worker import Worker as _Worker

    assert chain_key("assets", "s", "1.0.0").endswith(f":c{CHAIN_VERSION}")

    tmp = _tempfile.mkdtemp()
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = f"{tmp}/art"
    db = _Database(f"sqlite:///{tmp}/upgrade.sqlite")
    db.create_all()
    _Registry(db).seed_defaults()
    q = _JobQueue(db)
    q.enqueue("orchestrator", "plan.cycle", {"as_of": TODAY.isoformat()})
    w = _Worker(db, "upgrade")
    for _ in range(2500):
        if not w.run_once():
            break

    # Reproduce "certified under an older chain": keep the certificates, remove everything the
    # current chain produces, and strip the current chain's keys.
    with db.session() as s:
        for table in (Listing, ListingAsset, ContentPiece, Collection):
            for row in list(s.scalars(_select(table))):
                s.delete(row)
        for job in s.scalars(_select(Job)):
            if job.idempotency_key and f":c{CHAIN_VERSION}" in job.idempotency_key:
                job.idempotency_key = job.idempotency_key.replace(f":c{CHAIN_VERSION}", "")

    q.enqueue("listing", "chain.rebuild", {})
    for _ in range(3000):
        if not w.run_once():
            break

    with db.session() as s:
        listings = list(s.scalars(_select(Listing)))
        images = list(s.scalars(_select(ListingAsset)))
        content = list(s.scalars(_select(ContentPiece)))
        collections = list(s.scalars(_select(Collection)))
        broken = [(j.job_type, (j.last_error or "")[:80]) for j in s.scalars(_select(Job))
                  if j.status in (JobStatus.DEAD, JobStatus.FAILED)
                  and j.job_type != "store.publish"]
    assert not broken, broken
    assert len(listings) >= 10, f"the rebuild reached only {len(listings)} listings"
    assert images and content and collections
    assert {l.chain_version for l in listings} == {CHAIN_VERSION}


def test_a_stale_listing_is_rebuilt_not_only_a_missing_one():
    """The first rebuild looked only for *missing* listings.

    So a copy fix reached nothing: every shipped product kept its old listing through two
    deploys, because a stale listing is present and the check only asked whether one existed.
    """
    import tempfile as _tempfile

    from sqlalchemy import select as _select

    from brambleloop.agents.registry import Registry as _Registry
    from brambleloop.core.db import Database as _Database
    from brambleloop.core.models import Listing
    from brambleloop.queue.durable import JobQueue as _JobQueue
    from brambleloop.runtime.release import CHAIN_VERSION
    from brambleloop.runtime.worker import Worker as _Worker

    tmp = _tempfile.mkdtemp()
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = f"{tmp}/art"
    db = _Database(f"sqlite:///{tmp}/stale.sqlite")
    db.create_all()
    _Registry(db).seed_defaults()
    q = _JobQueue(db)
    q.enqueue("orchestrator", "plan.cycle", {"as_of": TODAY.isoformat()})
    w = _Worker(db, "stale")
    for _ in range(2500):
        if not w.run_once():
            break

    with db.session() as s:
        listings = list(s.scalars(_select(Listing)))
        assert listings and all(l.chain_version == CHAIN_VERSION for l in listings)
        # Age every listing, and free the keys the way a chain bump would.
        for l in listings:
            l.chain_version = "0"
        for job in s.scalars(_select(Job)):
            if job.idempotency_key and f":c{CHAIN_VERSION}" in job.idempotency_key:
                job.idempotency_key = job.idempotency_key.replace(f":c{CHAIN_VERSION}", ":c0")

    q.enqueue("listing", "chain.rebuild", {})
    for _ in range(3000):
        if not w.run_once():
            break

    with db.session() as s:
        after = list(s.scalars(_select(Listing)))
        broken = [(j.job_type, (j.last_error or "")[:80]) for j in s.scalars(_select(Job))
                  if j.status in (JobStatus.DEAD, JobStatus.FAILED)
                  and j.job_type != "store.publish"]
    assert not broken, broken
    assert after and all(l.chain_version == CHAIN_VERSION for l in after), \
        sorted({l.chain_version for l in after})


def test_attack_a_fake_was_price_is_refused():
    """The whole category runs a permanent fake sale. It is still not available to us."""
    try:
        pricing_mod.check_no_fake_discount(11.65, 23.30, ever_charged=False)
    except pricing_mod.DeceptivePricing as e:
        assert "never been sold" in str(e)
    else:
        raise AssertionError("a was-price we never charged was accepted")


def test_attack_a_bundle_that_is_not_actually_cheaper_is_refused():
    try:
        pricing_mod.decide_price("b", category_band_cad=(8.0, 26.0), proposed_cad=26.0,
                                 is_bundle=True, bundle_members_cad=[12.5, 5.5, 7.5])
    except pricing_mod.DeceptivePricing as e:
        assert "not cheaper" in str(e)
    else:
        raise AssertionError("a bundle priced above its members was accepted")


def test_attack_an_unsupportable_listing_claim_is_blocked():
    copy = seo_mod.ListingCopy(
        title="Guaranteed Easiest Crochet Pattern",
        tags=["a b", "c d"],
        description="x" * 400,
        materials=["worsted acrylic"], price_cad=12.5)
    problems = seo_mod.check_listing_limits(copy)
    assert any(p.startswith("LISTING_UNSUPPORTABLE_CLAIM") for p in problems), problems


def test_attack_a_listing_that_hides_it_is_a_pattern_is_blocked():
    copy = seo_mod.ListingCopy(title="Nordic Forest Throw Blanket", tags=["a b"],
                               description="x" * 400, materials=[], price_cad=12.5)
    problems = seo_mod.check_listing_limits(copy)
    assert any(p.startswith("LISTING_AMBIGUOUS_PRODUCT") for p in problems), problems


def test_attack_support_cannot_edit_the_pattern():
    c = Concierge(nf.build("baby"))
    try:
        c.amend(row=4, count=41)
    except SupportCannotAmendPatterns as e:
        assert "incident" in str(e)
    else:
        raise AssertionError("support amended a released pattern")


def test_attack_support_will_not_guess_when_it_does_not_know():
    c = Concierge(nf.build("baby"))
    answer = c.answer("can I use this as a car seat cover for a newborn?")
    assert answer.escalated and not answer.confident
    assert "human" in answer.answer


def test_attack_an_agent_cannot_reach_outside_its_permissions():
    db = Database("sqlite://")
    db.create_all()
    reg = Registry(db)
    reg.seed_defaults()
    for agent, job_type in (("support", "cir.draft"), ("publishing", "store.publish"),
                            ("growth", "gate.certify"), ("listing", "ads.campaign"),
                            ("pricing", "gate.policy")):
        try:
            reg.authorize(agent, job_type)
        except PermissionDenied:
            continue
        raise AssertionError(f"{agent} was allowed to run {job_type}")


def test_attack_a_missing_artifact_is_reported_not_silently_substituted():
    store = ArtifactStore(tempfile.mkdtemp())
    stored = store.put("k", b"%PDF-1.4 real", "application/pdf")
    Path(stored.path).unlink()
    try:
        store.get(stored.sha256)
    except ArtifactMissing as e:
        assert "not on disk" in str(e)
    else:
        raise AssertionError("a deleted artifact was served as if present")


def test_attack_a_corrupted_artifact_is_detected():
    store = ArtifactStore(tempfile.mkdtemp())
    stored = store.put("k", b"%PDF-1.4 real", "application/pdf")
    Path(stored.path).write_bytes(b"%PDF-1.4 tampered")
    try:
        store.get(stored.sha256)
    except ArtifactMissing as e:
        assert "corrupt" in str(e)
    else:
        raise AssertionError("a tampered artifact passed its integrity check")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
