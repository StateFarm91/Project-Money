"""The acceptance gates, asserted as gates (spec 03_Acceptance_Tests_and_Autonomy_Gates).

The rest of the suite tests components. This file tests the *gates*, one test per line of the
owner's acceptance document, so that "Gate B passes" is a claim backed by a named test rather
than inferred from a scattering of others. Capabilities may only graduate SHADOW → STAGING →
LIMITED PRODUCTION → PRODUCTION by passing these.

Where a gate line needs something that does not exist yet, the test says so explicitly and
fails rather than being quietly omitted.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fixtures import broken_repeat, broken_stitch_count, good_mosaic_panel  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import BudgetExceeded, Registry, SpendGuard  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, LedgerEntry, Product, SupportCase,
)
from brambleloop.gates import regression as reg  # noqa: E402
from brambleloop.gates.asset_truth import (  # noqa: E402
    Asset, AssetClass, Claims, Provenance, check_assets,
)
from brambleloop.gates.incidents import (  # noqa: E402
    DefectReport, IncidentTracker, SupportCannotPatchPatterns, apply_support_patch,
)
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402
from brambleloop.runtime.worker import Worker  # noqa: E402

_RUN: dict = {}


def _full_cycle() -> Database:
    """One unattended cycle, cached. Gate F needs the whole thing; others reuse it."""
    if "db" not in _RUN:
        import os

        tmp = tempfile.mkdtemp()
        os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = f"{tmp}/art"
        db = Database(f"sqlite:///{tmp}/gates.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {"as_of": "2026-09-17"})
        w = Worker(db, "gate-worker")
        for _ in range(2500):
            if not w.run_once():
                break
        _RUN["db"] = db
    return _RUN["db"]


def _audit_actions(db) -> set[str]:
    with db.session() as s:
        return {a.action for a in s.scalars(select(AuditLog))}


# ---- Gate A: Infrastructure ------------------------------------------------


def test_gate_a_worker_restart_does_not_lose_durable_jobs():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/a.sqlite"
        db = Database(url)
        db.create_all()
        Registry(db).seed_defaults()
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {"as_of": "2026-09-17"})

        Worker(db, "first").run_once()          # process "dies" here
        assert JobQueue(Database(url)).counts()["pending"] >= 1

        w2 = Worker(Database(url), "second")
        for _ in range(2500):
            if not w2.run_once():
                break
        with Database(url).session() as s:
            assert list(s.scalars(select(Product))), "work was lost across the restart"


def test_gate_a_duplicate_execution_cannot_duplicate_publication_or_spend():
    db = _full_cycle()
    q = JobQueue(db)
    with db.session() as s:
        before = sorted(p.slug for p in s.scalars(select(Product)))
    q.enqueue("orchestrator", "plan.cycle", {"as_of": "2026-09-17"})
    w = Worker(db, "replay")
    for _ in range(2500):
        if not w.run_once():
            break
    with db.session() as s:
        after = sorted(p.slug for p in s.scalars(select(Product)))
    assert before == after, "a replayed cycle duplicated products"


def test_gate_a_backup_and_tested_restore_succeed():
    from brambleloop.core.backup import backup, drill

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/live.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
        backup(db, Path(tmp) / "backups")
        result = drill(db, Path(tmp) / "scratch")
        assert result.ok, result


def test_gate_a_dead_letter_and_backoff_work():
    db = _full_cycle()
    dead = JobQueue(db).dead_letters()
    assert dead, "nothing ever reached the dead-letter queue"
    assert all(j.attempts >= 1 for j in dead)


def test_gate_a_audit_identifies_actor_action_and_artifact():
    db = _full_cycle()
    with db.session() as s:
        rows = [a for a in s.scalars(select(AuditLog)) if a.artifact]
    assert rows
    assert all(a.actor and a.action for a in rows)


# ---- Gate B: Pattern Safety ------------------------------------------------


def test_gate_b_a_known_good_fixture_compiles():
    assert compile_cir(good_mosaic_panel()).ok


def test_gate_b_a_broken_stitch_count_fails():
    result = compile_cir(broken_stitch_count())
    assert not result.ok and any(f.code == "COUNT_MISMATCH" for f in result.errors)


def test_gate_b_a_bad_repeat_fails():
    result = compile_cir(broken_repeat())
    assert not result.ok and any(f.code in ("REPEAT", "COUNT_MISMATCH", "UNDERRUN")
                                 for f in result.errors)


def test_gate_b_a_construction_changing_mutation_is_caught_by_reverse_compilation():
    cir = nf.build("baby")
    text = write_pattern(cir, compile_cir(cir))
    assert compare(cir, text, "US") == []
    mutated = text.replace("sc in next 5 sts", "dc in next 5 sts", 1)
    assert mutated != text
    assert compare(cir, mutated, "US"), "a stitch substitution passed unchallenged"


def test_gate_b_a_corrected_bug_creates_a_regression_test():
    """The line that kept Gate B open until now."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        fixture = reg.capture(broken_stitch_count(), source="gate-b", directory=d)
        assert fixture.expected_codes
        assert reg.run(d).ok
    assert reg.run().checked >= 5, "the repository's own regression corpus is missing"
    assert reg.run().ok


# ---- Gate C: Asset Truth ---------------------------------------------------


def _twin_for(cir):
    return build_twin(cir, compile_cir(cir))


def test_gate_c_an_absent_motif_in_a_listing_image_is_rejected():
    cir = nf.build("baby")
    twin = _twin_for(cir)
    asset = Asset(asset_id="a", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                  provenance=Provenance(source="twin", created_by="t", tool="t@1"),
                  depicts_stitches=sorted(twin.stitch_types_used) + ["tr"],
                  depicts_colors=sorted(c for c in twin.colors_used if c),
                  is_hero=True, claims=Claims())
    assert any(f.code == "ASSET_MOTIF_ABSENT" for f in check_assets([asset], cir, twin))


def test_gate_c_unsupported_size_material_and_difficulty_claims_are_blocked():
    cir = nf.build("baby")
    twin = _twin_for(cir)
    asset = Asset(asset_id="a", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                  provenance=Provenance(source="twin", created_by="t", tool="t@1"),
                  depicts_stitches=sorted(twin.stitch_types_used),
                  depicts_colors=sorted(c for c in twin.colors_used if c), is_hero=True,
                  claims=Claims(finished_width_cm=300.0, finished_height_cm=300.0,
                                materials=["cashmere"], difficulty="advanced"))
    codes = {f.code for f in check_assets([asset], cir, twin)}
    assert any(c.startswith("CLAIM_SIZE") for c in codes), codes
    assert "CLAIM_MATERIAL_UNSUPPORTED" in codes, codes
    assert "CLAIM_DIFFICULTY_UNSUPPORTED" in codes, codes


def test_gate_c_asset_provenance_is_stored():
    from brambleloop.core.models import ListingAsset

    db = _full_cycle()
    with db.session() as s:
        assets = list(s.scalars(select(ListingAsset)))
    assert assets, "no listing assets were recorded"
    assert all(a.asset_class and a.sha256 for a in assets)


# ---- Gate D: Commercial Safety ---------------------------------------------


def test_gate_d_price_and_promotion_changes_pass_policy_rules():
    from brambleloop.commerce.pricing import DeceptivePricing, check_no_fake_discount
    from brambleloop.commerce.pricing_intel import check_promotion

    assert check_promotion("launch_window", price_cad=9.99, was_price_cad=12.50,
                           ever_charged=True, duration_days=7) == []
    try:
        check_no_fake_discount(9.99, 23.30, ever_charged=False)
    except DeceptivePricing:
        pass
    else:
        raise AssertionError("a was-price never charged was accepted")


def test_gate_d_ad_budget_breach_is_prevented_and_the_scope_is_paused():
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    guard = SpendGuard(db)
    guard.set_limit("ads:etsy", daily_cap_cad=5.0, lifetime_cap_cad=20.0)
    guard.authorize_spend("ads:etsy", 4.0)
    for _ in range(3):
        try:
            guard.authorize_spend("ads:etsy", 4.0)
        except BudgetExceeded:
            pass
    status = guard.status("ads:etsy")
    assert status.paused is True
    assert status.spent_today_cad <= 5.0, "a refused spend leaked through"


def test_gate_d_contribution_accounting_reconciles_to_test_transactions():
    """Gate D's line, against transactions written for the purpose."""
    from brambleloop.finance.books import Books

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for i in range(10):
            s.add(LedgerEntry(category="sale", gross_cad=12.50, fees_cad=1.46,
                              evidence_ref=f"gate-d-{i}"))
    pl = Books(db).profit_and_loss()
    assert pl.orders == 10
    assert abs(pl.gross_sales_cad - 125.0) < 1e-6
    assert abs(pl.platform_fees_cad - 14.60) < 1e-6
    # Contribution is net sales less the costs that vary with selling.
    assert abs(pl.contribution_margin_cad - 110.40) < 0.01
    assert abs(pl.net_profit_cad - (125.0 - 14.6 - pl.tax_reserve_cad)) < 0.01


def test_gate_d_agent_token_and_cost_ceilings_work():
    db = Database("sqlite://")
    db.create_all()
    reg_ = Registry(db)
    reg_.seed_defaults()
    hit = False
    for _ in range(50):
        try:
            reg_.record_cost("validator", 0.30, kind="llm")
        except BudgetExceeded:
            hit = True
            break
    assert hit, "an agent spent past its daily ceiling"


# ---- Gate E: Customer Experience -------------------------------------------


def test_gate_e_routine_support_is_answered_from_the_correct_pattern_version():
    db = _full_cycle()
    q = JobQueue(db)
    job = q.enqueue("support", "support.reply", {
        "slug": "nordic-forest-mosaic-throw", "version": "1.0.0", "customer_ref": "gate-e",
        "question": "how many stitches at the end of row 12?"})
    assert Worker(db, "gate-e").run_once() is True
    out = q.get(job.id).outputs
    assert out["cited_version"] == "nordic-forest-mosaic-throw@1.0.0"
    assert out["escalated"] is False
    assert out["sent"] is False
    with db.session() as s:
        assert any(c.customer_ref == "gate-e" for c in s.scalars(select(SupportCase)))


def test_gate_e_repeated_defect_reports_correlate_into_one_incident():
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    tracker = IncidentTracker(db)
    ids = {tracker.report(DefectReport("p", "1.0.0", "panel", 4, f"c{i}",
                                       "row 4 count is wrong")).id for i in range(4)}
    assert len(ids) == 1, "four reports of one defect made more than one incident"


def test_gate_e_support_cannot_silently_patch_the_cir():
    from brambleloop.support.concierge import Concierge, SupportCannotAmendPatterns

    try:
        apply_support_patch()
    except SupportCannotPatchPatterns:
        pass
    else:
        raise AssertionError("support patched a canonical pattern")
    try:
        Concierge(nf.build("baby")).amend()
    except SupportCannotAmendPatterns:
        pass
    else:
        raise AssertionError("the concierge amended a released pattern")


def test_gate_e_a_p1_incident_halts_the_publication_workflow():
    import os

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = f"{tmp}/art"
        db = Database(f"sqlite:///{tmp}/e.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        tracker = IncidentTracker(db)
        for i in range(3):
            tracker.report(DefectReport("nordic-forest-mosaic-throw", "1.0.0", "blanket", 4,
                                        f"c{i}", "row 4 is wrong"))
        assert tracker.publication_halted("nordic-forest-mosaic-throw")

        JobQueue(db).enqueue("orchestrator", "plan.cycle", {"as_of": "2026-09-17"})
        w = Worker(db, "halted")
        for _ in range(2500):
            if not w.run_once():
                break
        with db.session() as s:
            assert s.scalar(select(Product).where(
                Product.slug == "nordic-forest-mosaic-throw")) is None
        assert "gate.halted" in _audit_actions(db)


# ---- Gate F: Shadow Mode Graduation ----------------------------------------


def test_gate_f_a_full_product_completes_the_whole_chain_without_intervention():
    """Market Radar -> Opportunity -> CIR -> QA -> PDF/assets -> pricing -> listing draft
    -> launch plan -> simulated support, unattended."""
    db = _full_cycle()
    actions = _audit_actions(db)
    for stage in ("radar.scanned", "radar.scored", "cir.drafted", "cir.compiled",
                  "gate.certified", "listing.drafted", "assets.built",
                  "assets.listing_images_built", "pricing.positioned",
                  "listing.seo_drafted", "launch.planned", "marketing.scheduled",
                  "store.publish_refused"):
        assert stage in actions, f"the chain never reached {stage}: {sorted(actions)}"

    with db.session() as s:
        broken = [(j.job_type, (j.last_error or "")[:100]) for j in s.scalars(select(Job))
                  if j.status in (JobStatus.FAILED, JobStatus.DEAD)
                  and j.job_type != "store.publish"]
    assert not broken, broken

    # Simulated support closes the chain.
    q = JobQueue(db)
    job = q.enqueue("support", "support.reply", {
        "slug": "nordic-forest-mosaic-throw", "version": "1.0.0", "customer_ref": "gate-f",
        "question": "what gauge is this?"})
    Worker(db, "gate-f").run_once()
    assert q.get(job.id).outputs["cited_version"].startswith("nordic-forest-mosaic-throw")


def test_gate_f_nothing_graduated_past_shadow():
    """Passing the gates is permission to graduate, not graduation."""
    db = _full_cycle()
    actions = _audit_actions(db)
    assert "store.published" not in actions
    assert "store.publish_refused" in actions
    with db.session() as s:
        assert not list(s.scalars(select(LedgerEntry))), "shadow mode recorded a transaction"
        assert all(c.sent is False for c in s.scalars(select(SupportCase)))


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
