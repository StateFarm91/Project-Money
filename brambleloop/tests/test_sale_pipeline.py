"""ENG-SALE-PIPELINE: spend order, admission, stalls, certificates and the ready rule
(`publish.sale_pipeline`; D-OWNER-SPEND-ORDER, D-OWNER-SALE-PIPELINE).

The scratch database is `test_w4_ownerimg.make_db` (two certified releases). Generators are
the ownerimg test doubles; a `paid = True` double stands in for a paid provider. Nothing
here calls a network or spends.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_sale_pipeline.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402

from brambleloop.publish import sale_pipeline as SPL  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

SLUG, VERSION = "cloudline-baby-blanket", "1.2.0"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


class PaidDouble(O.StubGenerator):
    """test_double: a paid provider. Any call is counted."""
    paid = True


def _db():
    db = O.make_db()
    SPL.ensure_tables(db)
    return db


def _row(db, slug, release, **kw):
    with db.session() as s:
        r = SPL._row(s, SPL.run_key(slug, VERSION, release), lock=True)
        if r is None:
            r = SPL.SalePipelineRun(run_key=SPL.run_key(slug, VERSION, release), slug=slug,
                                    version=VERSION, release=release, evidence={})
            s.add(r)
        for k, v in kw.items():
            setattr(r, k, v)


def _collect():
    sent = []

    def follow(inputs, key):
        sent.append((inputs, key))
        return object()
    return follow, sent


# ---- D-OWNER-SPEND-ORDER --------------------------------------------------------------------

def test_a_release_not_selected_for_sale_waits_before_images_and_spends_nothing():
    db = _db()
    follow, sent = _collect()
    out = SPL.run_stage(db, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                             "stage": "admission"}, follow=follow,
                        start_images=lambda *a: {"started": "never"})
    assert out["state"] == SPL.AWAITING_PRE_IMAGE, out
    assert out["blocker"] == "pre_image:selected_for_sale", out
    assert not SPL.spend_admitted(db, SLUG, VERSION, O.RELEASE)
    assert sent == []                                   # nothing enqueued, nothing started
    gen = PaidDouble()
    f, _ = O.drain(db, generator=gen, judges=O.StubJudges())
    IP.trigger(f, slug=SLUG, version=VERSION, release=O.RELEASE)
    O.drain(db, generator=gen, judges=O.StubJudges())
    run = IP.get_run(db, IP.run_key(SLUG, VERSION, O.RELEASE))
    assert run["state"] == IP.AWAITING_PRE_IMAGE, run
    assert gen.calls == 0 and run["spent_cad"] == 0.0 and run["generation_calls"] == 0
    assert IP.AWAITING_PRE_IMAGE in IP.STATES


def test_an_admitted_release_still_meets_every_image_gate():
    db = _db()
    _row(db, SLUG, O.RELEASE, state=SPL.GALLERY, reservation="held", reserved_cad=2.0)
    assert SPL.spend_admitted(db, SLUG, VERSION, O.RELEASE)
    gen = PaidDouble()
    f, _ = O.drain(db, generator=gen, judges=O.StubJudges())
    IP.trigger(f, slug=SLUG, version=VERSION, release=O.RELEASE)
    O.drain(db, generator=gen, judges=O.StubJudges())
    run = IP.get_run(db, IP.run_key(SLUG, VERSION, O.RELEASE))
    # admission never opens the image_generation gate: the paid call is still refused
    assert run["state"] == "blocked" and "image_generation gate closed" in run["blocked_reason"]
    assert gen.calls == 0


def test_a_queued_spending_continuation_waits_when_admission_is_withdrawn():
    db = _db()
    out = IP.run_stage(db, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                            "stage": "product_generation", "round": 0},
                       follow=lambda *a: None, generator=PaidDouble(), judges=O.StubJudges())
    assert out["state"] == IP.AWAITING_PRE_IMAGE, out


def test_a_free_generator_and_an_experiment_are_not_held():
    assert IP._spend_admitted(None, O.StubGenerator(), None, None, SLUG, VERSION, "r")
    assert IP._spend_admitted(None, PaidDouble(), object(), None, SLUG, VERSION, "r")
    assert IP._spend_admitted(None, PaidDouble(), None, 7, SLUG, VERSION, "r")
    assert not IP._spend_admitted(None, None, None, None, SLUG, VERSION, "r")  # unreadable: no


def test_admission_is_in_value_order_core_first_and_bounded_by_the_ceiling():
    db = _db()
    cap = SPL._per_listing_cap()
    _row(db, "other-high", "r1", state=SPL.AWAITING_ADMISSION, core=False, ev_score=50.0)
    _row(db, "core-low", "r2", state=SPL.AWAITING_ADMISSION, core=True, ev_score=5.0)
    _row(db, "core-high", "r3", state=SPL.AWAITING_ADMISSION, core=True, ev_score=9.0)
    real = SPL._month_budget
    SPL._month_budget = lambda _db: (100.0 - 2 * cap, 100.0, "")
    try:
        k = lambda slug, rel: SPL.run_key(slug, VERSION, rel)  # noqa: E731
        q = [r["slug"] for r in SPL.admission_queue(db)]
        assert q == ["core-high", "core-low", "other-high"], q
        got = SPL.try_admit(db, k("other-high", "r1"))
        assert not got["admitted"] and got["blocker"] == "admission_queue", got
        assert SPL.try_admit(db, k("core-low", "r2"))["admitted"]
        assert SPL.try_admit(db, k("core-high", "r3"))["admitted"]
        got = SPL.try_admit(db, k("other-high", "r1"))
        assert not got["admitted"] and got["blocker"] == "budget_ceiling", got
        with db.session() as s:
            held = SPL._held_reservations(s)
        assert held == 2 * cap and 100.0 - 2 * cap + held <= 100.0
        # a parked product gives its reservation back, and the next in line is admitted
        assert SPL.park(db, "core-low", VERSION, "r2", why="parked by the agents")["released"]
        assert SPL.try_admit(db, k("other-high", "r1"))["admitted"]
        assert not SPL.spend_admitted(db, "core-low", VERSION, "r2")
    finally:
        SPL._month_budget = real


def test_an_unreadable_ledger_admits_nothing():
    db = _db()
    _row(db, "core-a", "r9", state=SPL.AWAITING_ADMISSION, core=True, ev_score=9.0)
    real = SPL._month_budget
    SPL._month_budget = lambda _db: (None, 100.0, "CeilingReached: invalid ledger")
    try:
        got = SPL.try_admit(db, SPL.run_key("core-a", VERSION, "r9"))
        assert not got["admitted"] and got["blocker"] == "budget_ledger_unreadable"
    finally:
        SPL._month_budget = real


def test_core_families_classify_first():
    db = _db()
    assert SPL.classify(db, "cloudline-baby-blanket") == ("baby", True)
    assert SPL.classify(db, "cosy-cushion-cover") == ("pillow", True)
    assert SPL.classify(db, "bunny-amigurumi") == ("amigurumi", True)
    assert SPL.classify(db, "hexagon-coaster-set")[1] is False


# ---- no silent stalls -----------------------------------------------------------------------

def test_a_stalled_eligible_release_is_a_named_incident_with_bounded_redrives():
    db = _db()
    _row(db, SLUG, O.RELEASE, state=SPL.GALLERY, reservation="held", reserved_cad=2.0,
         blocker="provider_key_missing", blocker_detail="no image generator is wired",
         progressed_at=NOW - timedelta(hours=13))
    seen = []
    follow, sent = _collect()
    for i in range(SPL.MAX_REDRIVES + 2):
        out = SPL.sweep(db, follow=follow, now=NOW + timedelta(hours=i),
                        incident=lambda sig, summary, detail: seen.append((sig, detail)))
        assert out["stalled"] == 1
    assert {s for s, _ in seen} == {f"{SPL.INCIDENT_PREFIX}{SLUG}@{VERSION}"}
    assert seen[0][1]["blocker"] == "provider_key_missing"
    redrives = [k for i, k in sent if i["stage"] == "gallery"]
    assert len(redrives) == SPL.MAX_REDRIVES, redrives          # bounded
    assert len(set(redrives)) == SPL.MAX_REDRIVES                # each a new key
    b = SPL.board(db, now=NOW)
    assert b["eligible"] == 1 and b["stalled"] == 1
    assert b["blocked_by_reason"] == {"provider_key_missing": 1}


def test_the_gallery_stage_names_the_image_runs_blocker():
    db = _db()
    _row(db, SLUG, O.RELEASE, state=SPL.GALLERY, reservation="held", reserved_cad=2.0)
    IP._ensure_run(db, SLUG, VERSION, O.RELEASE)
    IP._update(db, IP.run_key(SLUG, VERSION, O.RELEASE), stage="prepare_references",
               blocked="no image generator is wired: W-FLUXAPI's stage functions")
    follow, sent = _collect()
    out = SPL.run_stage(db, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                             "stage": "gallery"}, follow=follow)
    assert out["blocker"] == "provider_key_missing" and out["next"] is None, out
    assert sent == []
    assert SPL.name_blocker("identity HOLD: not production qualified") == "identity_not_qualified"
    assert SPL.name_blocker("spend plan refused: budget") == "budget_ceiling"


def test_the_sweep_asks_admission_for_every_certified_listed_release_hourly():
    from brambleloop.core.models import Listing

    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title="t", description="d",
                      tags=["x"], price_cad=7.5, state="draft", release_hash=O.RELEASE))
    follow, sent = _collect()
    SPL.sweep(db, follow=follow, now=NOW)
    SPL.sweep(db, follow=follow, now=NOW + timedelta(minutes=10))
    keys = [k for i, k in sent if i["stage"] == "admission"]
    assert len(keys) == 2 and len(set(keys)) == 1               # one per release per hour


# ---- certificates and the ready rule ----------------------------------------------------------

def _certified(db, base=("a" * 64, "b" * 64)):
    _row(db, SLUG, O.RELEASE, state=SPL.PDFS_CERTIFIED, reservation="consumed",
         evidence={"premium_pdfs": {"US": {"sha256": "c" * 64}, "UK": {"sha256": "d" * 64}}})
    for t, sha, b in (("US", "c" * 64, base[0]), ("UK", "d" * 64, base[1])):
        SPL._record_certificate(db, slug=SLUG, version=VERSION, release=O.RELEASE,
                                terminology=t, pdf_sha256=sha, verdict="PASS", checks=[],
                                expected={}, gallery_record_id=1, base_pdf_sha256=b,
                                standard_sha256="s")


def test_pdf_certificates_bind_to_this_releases_pdfs():
    db = _db()
    assert SPL.pdf_certificates(db, SLUG, VERSION, O.RELEASE)["both_pass"] is False
    _certified(db)
    assert SPL.pdf_certificates(db, SLUG, VERSION, O.RELEASE)["both_pass"] is True
    assert SPL.pdf_certificates(db, SLUG, VERSION, "other-release")["both_pass"] is False
    # a certificate for a superseded text PDF no longer binds
    from brambleloop.core.models import AuditLog, Job

    with db.session() as s:
        j = Job(agent="synthetic", job_type="assets.build", inputs={"release": O.RELEASE})
        s.add(j)
        s.flush()
        s.add(AuditLog(actor="synthetic", action="assets.built", artifact=f"{SLUG}@{VERSION}",
                       job_id=j.id, detail={"pdf_sha256_by_terminology": {"US": "e" * 64,
                                                                          "UK": "b" * 64}}))
    got = SPL.pdf_certificates(db, SLUG, VERSION, O.RELEASE)
    assert got["both_pass"] is False and not got["editions"]["US"]["bound_to_release_pdfs"]


def test_a_failing_or_unknown_edition_never_certifies():
    db = _db()
    _certified(db)
    SPL._record_certificate(db, slug=SLUG, version=VERSION, release=O.RELEASE, terminology="UK",
                            pdf_sha256="d" * 64, verdict="UNKNOWN", checks=[], expected={},
                            gallery_record_id=1, base_pdf_sha256="b" * 64, standard_sha256="s")
    assert SPL.pdf_certificates(db, SLUG, VERSION, O.RELEASE)["both_pass"] is False


def test_the_listing_package_blocks_without_both_pdf_certificates():
    from brambleloop.publish import listing_package as LP

    db = _db()
    pkg = LP.assemble(db, SLUG, VERSION)
    src = [b for b in pkg["blockers"] if b["source"] == "pdf_standard"]
    assert pkg["state"] == LP.BLOCKED and src, pkg["blockers"]
    assert "D-OWNER-PDF-STANDARD" in src[0]["why"]
    _certified(db)
    pkg = LP.assemble(db, SLUG, VERSION)
    assert not [b for b in pkg["blockers"] if b["source"] == "pdf_standard"], pkg["blockers"]
    assert pkg["files"]["premium_pdfs"]["US"]["verdict"] == "PASS"


def test_ready_for_sale_needs_everything():
    db = _db()
    got = SPL.ready_for_sale(db, SLUG, VERSION)
    assert got["ready"] is False
    assert any("gallery" in r for r in got["reasons"])
    assert any("premium PDFs" in r for r in got["reasons"])
    assert any("listing gates" in r for r in got["reasons"])
    assert SPL.ready_for_sale(db, "no-such", VERSION)["ready"] is False


def test_lifecycle_listing_ready_requires_ready_for_sale():
    from brambleloop.products import lifecycle

    real_g, real_r = lifecycle._complete_gallery, lifecycle._ready_for_sale
    from brambleloop.core.models import Listing, ListingAsset

    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title="t", description="d",
                      tags=["x"], price_cad=7.5, state="draft", release_hash=O.RELEASE))
        s.add(ListingAsset(product_slug=SLUG, version=VERSION, position=1, asset_class="x",
                           role="hero", sha256="f" * 64, claims={}))
    try:
        lifecycle._complete_gallery = lambda s, slug: True
        lifecycle._ready_for_sale = lambda db, slug, v: {"ready": False, "reasons": ["pdf"]}
        assert lifecycle.derive(db, SLUG)["stage"] == "VISUAL"
        lifecycle._ready_for_sale = lambda db, slug, v: {"ready": True, "reasons": []}
        assert lifecycle.derive(db, SLUG)["stage"] == "LISTING_READY"
    finally:
        lifecycle._complete_gallery, lifecycle._ready_for_sale = real_g, real_r


def test_image_production_hands_on_to_the_gallery_stage():
    from brambleloop.runtime import release

    db = _db()
    IP._ensure_run(db, SLUG, VERSION, O.RELEASE)
    key = IP.run_key(SLUG, VERSION, O.RELEASE)
    IP._update(db, key, stage="owner_card", status="ready_for_owner_review")
    sent = []

    class Ctx:
        def __init__(self, inputs):
            self.db = db
            self.job = type("J", (), {"inputs": inputs, "id": 1})()

        def enqueue(self, agent, job_type, inputs, **kw):
            sent.append((agent, job_type, inputs, kw["idempotency_key"]))
            return object()

        def audit(self, *a, **k):
            raise AssertionError(f"hand-off failed: {k}")

    release._hand_on_to_sale_pipeline(Ctx({"slug": SLUG}), {"run_key": key})
    assert sent and sent[0][:2] == ("listing", "sale.pipeline") and \
        sent[0][2]["stage"] == "gallery", sent
    sent.clear()
    release._hand_on_to_sale_pipeline(Ctx({"slug": SLUG, "experiment": True}), {"run_key": key})
    assert sent == []                                   # experiments never hand on


def test_wiring_is_registered_and_scheduled():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.runtime import worker
    from brambleloop.runtime.worker import handlers
    from brambleloop.ops import production_evidence as pe

    import brambleloop.runtime.pipeline  # noqa: F401  (registers handlers)

    assert "sale.pipeline" in handlers._handlers and "sale.pipeline_sweep" in handlers._handlers
    assert any(c[2] == "sale.pipeline_sweep" and c[3] == 3600 for c in worker.CADENCES)
    listing = next(a for a in DEFAULT_AGENTS if a["name"] == "listing")
    assert {"sale.pipeline", "sale.pipeline_sweep"} <= set(listing["allowed_job_types"])
    assert "awaiting_pre_image_readiness" in pe._RUN_STATES
    assert "sale_pipeline" in pe.SECTIONS


if __name__ == "__main__":
    import traceback

    failed = 0
    for name, fn in sorted((n, f) for n, f in dict(globals()).items() if n.startswith("test_")):
        try:
            fn()
            print("OK  ", name)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
