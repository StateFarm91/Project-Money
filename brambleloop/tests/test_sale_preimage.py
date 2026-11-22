"""SALE-PREIMAGE: the sale pipeline's pre-image readiness and image admission defects seen in
production evidence 2026-11-22T00:00Z (`awaiting_pre_image_by_reason`: child_family 15,
copy_seo 6, pdf_structure 7; three eligible releases with gallery_done 0 and nine image runs
in `waiting_for_sale_admission`).

Each test reproduces one defect (it fails on the code before SALE-PREIMAGE) and proves the
fix, plus the guards that must NOT move: child safety still FAILs every release with a
children's signal and no explicit decision, a changed reading is never reused, and an image
run is re-entered only through both spend admissions.

The scratch database is `test_w4_ownerimg.make_db`. Nothing here calls a network or spends.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_sale_preimage.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402

from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.core.models import Job, JobStatus, Listing  # noqa: E402
from brambleloop.publish import sale_pipeline as SPL  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

SLUG, VERSION = "cloudline-baby-blanket", "1.2.0"
PLAIN = "test-plain-throw"


def _db():
    db = O.make_db()
    SPL.ensure_tables(db)
    return db


class _Patch:
    """Minimal monkeypatch: restores every attribute it set."""

    def __init__(self):
        self.saved = []

    def set(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)


def _plain_cir(**changes):
    """An adult, flat, unstuffed throw that no catalogue entry names (undecided)."""
    d = O._cir("winter-village-graphghan").to_dict()
    d.update({"slug": PLAIN, "title": "Plain Ridge Throw", **changes})
    return CIR.from_dict(d)


def _readiness(db, cir, *, listing=None, cached=None, structure=None):
    """`pre_image_readiness` on `cir`, with the base PDFs stubbed (their reading is not under
    test here unless `structure` is given)."""
    p = _Patch()
    pv = {"certified": True, "release_hash": "r" * 64, "created": None}
    p.set(SPL, "_cir", lambda db_, slug, version: (cir, pv))
    p.set(SPL, "base_pdf_hashes", lambda *a, **k: {"US": "a" * 64, "UK": "b" * 64})
    calls = []

    def fake_structure(*a, **k):
        calls.append(1)
        return structure() if structure else {"status": SPL.PASS, "why": "",
                                              "hashes": {"US": "a" * 64, "UK": "b" * 64},
                                              "checker": SPL.structure_checker()}
    p.set(SPL, "_structure", fake_structure)
    if listing is not None:
        with db.session() as s:
            s.add(Listing(product_slug=cir.slug, version=cir.version, release_hash="r" * 64,
                          price_cad=8.0, **listing))
    try:
        return SPL.pre_image_readiness(db, cir.slug, cir.version, "r" * 64,
                                       cached=cached), calls
    finally:
        p.undo()


# ---- child_family -----------------------------------------------------------------------

def test_child_family_a_product_with_no_childrens_signal_is_outside_the_question():
    """Defect: every product no catalogue entry names read `undecided` and FAILed, although
    the renderer and the listing package (the publication gates) treat a product with no
    children's signal as outside the question. 15 releases waited for good."""
    db = _db()
    cir = _plain_cir()
    from brambleloop.products import launch0

    assert launch0.childrens_decision_for(cir)[0] == launch0.UNDECIDED
    got, _ = _readiness(db, cir, listing={"title": "Plain Ridge Throw crochet pattern",
                                          "description": "A textured throw.",
                                          "tags": ["throw blanket", "texture"]})
    cf = got["gates"]["child_family"]
    assert cf["status"] == SPL.PASS and cf["decision"] == "not_applicable", cf
    assert cf["screen"] == {"applies": False, "signals": []}


def test_child_family_undecided_with_any_signal_still_fails():
    """Child safety is not weakened: any children's signal with no explicit decision FAILs and
    names the owner decision required."""
    db = _db()
    for cir, listing, signal in (
            (_plain_cir(title="Plain Ridge Baby Throw"), None, "child words"),
            (_plain_cir(), {"title": "Throw pattern", "description": "Perfect for a toddler.",
                            "tags": ["throw"]}, "listing copy"),
            (_plain_cir(), {"title": "Throw pattern", "description": "Sized 0-3m.",
                            "tags": ["throw"]}, "listing copy")):
        db = _db()
        got, _ = _readiness(db, cir, listing=listing)
        cf = got["gates"]["child_family"]
        assert cf["status"] == SPL.FAIL, (signal, cf)
        assert cf["screen"]["applies"] and any(signal in s for s in cf["screen"]["signals"]), cf


def test_child_family_a_closed_stuffed_form_is_always_a_signal():
    cir = _plain_cir()
    d = cir.to_dict()
    d["materials"] = list(d.get("materials") or []) + [{"name": "polyester fiberfill"}]
    stuffed = CIR.from_dict(d)
    screen = SPL.child_audience_screen(stuffed)
    assert screen["applies"] and any("stuffed" in s for s in screen["signals"]), screen
    got, _ = _readiness(_db(), stuffed)
    assert got["gates"]["child_family"]["status"] == SPL.FAIL


def test_child_family_unreadable_pattern_or_copy_is_a_signal():
    class Broken:
        slug, title = PLAIN, "x"

        @property
        def components(self):
            raise RuntimeError("unreadable")
    screen = SPL.child_audience_screen(Broken())
    assert screen["applies"], screen
    screen = SPL.child_audience_screen(_plain_cir(), {"title": "t", "tags": [3]})
    assert screen["applies"] and any("unreadable" in s for s in screen["signals"]), screen


def test_child_family_an_assigned_product_is_unchanged():
    db = _db()
    cir = O._cir(SLUG)
    got, _ = _readiness(db, cir)
    cf = got["gates"]["child_family"]
    assert cf["status"] == SPL.PASS and cf["decision"] == "assigned", cf


# ---- copy_seo ---------------------------------------------------------------------------

def _seo_job(s, slug, version, release, *, ok=True, key=None):
    s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.DONE,
              inputs={"slug": slug, "version": version, "release": release},
              outputs={"ok": ok}, idempotency_key=key))


def test_copy_seo_the_releases_own_seo_job_is_found_behind_newer_rebuilds():
    """Defect: `_latest_job` read only the newest 500 DONE listing.seo jobs company-wide, so
    after fix-only rebuilds of other products a release's own SEO job fell out of the window
    and copy_seo FAILed for good ('no listing copy and SEO drafted')."""
    from brambleloop.runtime.release import chain_key

    db = _db()
    rel = "e" * 64
    with db.session() as s:
        _seo_job(s, SLUG, VERSION, rel, key=chain_key("seo", SLUG, VERSION, rel))
        for n in range(SPL._LATEST_JOB_SCAN + 5):
            _seo_job(s, f"other-{n}", "1.0.0", "f" * 64,
                     key=chain_key("seo", f"other-{n}", "1.0.0", "f" * 64, f"fix{n}"))
    got = SPL._latest_job(db, "listing.seo", SLUG, VERSION, rel)
    assert got is not None and got["outputs"]["ok"] is True, got


def test_copy_seo_exact_inputs_still_decide_and_newest_wins():
    from brambleloop.runtime.release import chain_key

    db = _db()
    rel = "e" * 64
    other = "e" * 12 + "0" * 52            # same 12-char key prefix, a different release
    with db.session() as s:
        _seo_job(s, SLUG, VERSION, rel, ok=True, key=chain_key("seo", SLUG, VERSION, rel))
        _seo_job(s, SLUG, VERSION, other, ok=True,
                 key=chain_key("seo", SLUG, VERSION, other, "rb2"))
        _seo_job(s, SLUG, VERSION, rel, ok=False, key=chain_key("seo", SLUG, VERSION, rel, "rb1"))
    got = SPL._latest_job(db, "listing.seo", SLUG, VERSION, rel)
    assert got["inputs"]["release"] == rel and got["outputs"]["ok"] is False, got
    assert SPL._latest_job(db, "listing.seo", SLUG, VERSION, "9" * 64) is None
    with db.session() as s:                  # an unkeyed job is still found by the scan
        _seo_job(s, "unkeyed", "1.0.0", rel, ok=True, key=None)
    assert SPL._latest_job(db, "listing.seo", "unkeyed", "1.0.0", rel) is not None


# ---- pdf_structure ----------------------------------------------------------------------

def test_pdf_structure_a_reading_from_another_checker_is_not_reused():
    """Defect: the cached structure reading was reused whenever the base PDF hashes matched,
    so a FAIL issued by an older checker stood for good. It is reused only from the same
    checker; a reading without a checker identity is re-read."""
    db = _db()
    cir = _plain_cir()
    hashes = {"US": "a" * 64, "UK": "b" * 64}
    stale = {"status": SPL.FAIL, "why": "old checker", "hashes": hashes}
    got, calls = _readiness(db, cir, cached={"pdf_structure": stale})
    assert calls == [1] and got["gates"]["pdf_structure"]["status"] == SPL.PASS, got
    other = {**stale, "checker": "pdf_standard/1|x|y"}
    got, calls = _readiness(_db(), cir, cached={"pdf_structure": other})
    assert calls == [1], calls


def test_pdf_structure_the_same_checker_and_pdfs_reuse_the_reading():
    hashes = {"US": "a" * 64, "UK": "b" * 64}
    same = {"status": SPL.FAIL, "why": "real defect", "hashes": hashes,
            "checker": SPL.structure_checker()}
    assert same["checker"] and SPL.structure_checker() == same["checker"]
    got, calls = _readiness(_db(), _plain_cir(), cached={"pdf_structure": same})
    assert calls == [] and got["gates"]["pdf_structure"]["status"] == SPL.FAIL, got
    changed = {**same, "hashes": {"US": "c" * 64, "UK": "b" * 64}}
    got, calls = _readiness(_db(), _plain_cir(), cached={"pdf_structure": changed})
    assert calls == [1], calls


def test_pdf_structure_records_its_checker():
    got = SPL._structure.__code__.co_names
    assert "structure_checker" in got


# ---- image admission ------------------------------------------------------------------------

def _row(db, slug, release, **kw):
    with db.session() as s:
        r = SPL._row(s, SPL.run_key(slug, VERSION, release), lock=True)
        if r is None:
            r = SPL.SalePipelineRun(run_key=SPL.run_key(slug, VERSION, release), slug=slug,
                                    version=VERSION, release=release, evidence={})
            s.add(r)
        for k, v in kw.items():
            setattr(r, k, v)


def _parked_flux_run(db, why="1 non-image listing gate(s) not PASS: halted (#173)"):
    key = IP.run_key(SLUG, VERSION, O.RELEASE, route=IP.SP.FLUX_ROUTE)
    IP._ensure_run(db, SLUG, VERSION, O.RELEASE, "", IP.SP.FLUX_ROUTE)
    IP._park_for_sale(db, key, "retrieve_release", {"admitted": False, "why": why})
    assert IP.get_run(db, key)["state"] == IP.SALE_WAITING
    return key


class _Ctx:
    def __init__(self, db):
        self.db, self.sent = db, []

    def enqueue(self, agent, job_type, inputs, idempotency_key=None, **kw):
        self.sent.append((job_type, inputs, idempotency_key))
        return object()


def test_an_admitted_releases_parked_flux_run_is_reentered_through_sale_admission():
    """Defect: `start_images` read a FLUX run parked in waiting_for_sale_admission as
    'in_progress' and enqueued nothing, so an admitted release (reservation held) never
    started its gallery. It now goes through `admit_for_sale`, which re-checks the
    vis-gallery admission and re-enters once per wait."""
    from brambleloop.runtime import sale_pipeline_ops as OPS

    db = _db()
    key = _parked_flux_run(db)
    ctx = _Ctx(db)
    p = _Patch()
    p.set(IP, "sale_admission", lambda *a, **k: {"admitted": True, "why": "every gate PASS"})
    try:
        out = OPS.start_images(ctx)(SLUG, VERSION, O.RELEASE)
        again = OPS.start_images(ctx)(SLUG, VERSION, O.RELEASE)
    finally:
        p.undo()
    assert out["started"] == "sale_readmission" and out["enqueued"], out
    flux = [x for x in ctx.sent if x[0] == IP.JOB_TYPE and x[1].get("route") == IP.SP.FLUX_ROUTE]
    assert flux and all(x[1]["stage"] == IP.STAGES[0][0] for x in flux), ctx.sent
    # once per wait: the second call reuses the same idempotency key (the durable queue
    # deduplicates on it), never a second gallery
    assert again["started"] in ("sale_readmission", "still_waiting"), again
    keys = [x[2] for x in ctx.sent if x[0] == IP.JOB_TYPE and x[1].get("route")]
    assert len(set(keys)) == 1, keys
    assert IP.get_run(db, key)["state"] == IP.SALE_WAITING  # the stage itself re-checks


def test_a_parked_run_whose_vis_gallery_admission_still_refuses_stays_parked():
    from brambleloop.runtime import sale_pipeline_ops as OPS

    db = _db()
    key = _parked_flux_run(db)
    ctx = _Ctx(db)
    p = _Patch()
    p.set(IP, "sale_admission", lambda *a, **k: {"admitted": False, "why": "halted (#173)"})
    try:
        out = OPS.start_images(ctx)(SLUG, VERSION, O.RELEASE)
    finally:
        p.undo()
    assert out["started"] == "still_waiting" and not out["enqueued"], out
    assert [x for x in ctx.sent if x[0] == IP.JOB_TYPE] == []
    assert IP.get_run(db, key)["state"] == IP.SALE_WAITING


def test_the_gallery_stage_names_the_wait_reason_and_reenters_the_parked_run():
    """Defect: the gallery stage of an admitted release whose image run was parked said only
    'gallery_in_production' and never re-entered it. It now names the wait's own reason and
    asks `start_images` to re-enter the run (only while the reservation is held)."""
    db = _db()
    _row(db, SLUG, O.RELEASE, state=SPL.GALLERY, reservation="held", reserved_cad=2.0)
    _parked_flux_run(db, why="1 non-image listing gate(s) not PASS: halted (#173): x")
    asked = []

    def start_images(slug, version, release):
        asked.append((slug, version, release))
        return {"started": "still_waiting"}
    out = SPL.run_stage(db, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                             "stage": "gallery"}, follow=lambda *a: None,
                        start_images=start_images)
    assert out["blocker"] == "image_sale_admission", out
    assert "halted (#173)" in out["why"] and "waiting_for_sale_admission" in out["why"], out
    assert asked == [(SLUG, VERSION, O.RELEASE)]
    # no reservation held: nothing is re-entered (no spend can start)
    db2 = _db()
    _row(db2, SLUG, O.RELEASE, state=SPL.GALLERY, reservation="released", reserved_cad=0.0)
    _parked_flux_run(db2)
    asked.clear()
    out = SPL.run_stage(db2, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                              "stage": "gallery"}, follow=lambda *a: None,
                        start_images=start_images)
    assert out["blocker"] == "image_sale_admission" and asked == [], out


def test_a_reentered_run_still_spends_nothing_without_both_admissions():
    """The fix opens no spend path: a re-entered FLUX stage with a paid generator and no sale
    pipeline reservation waits (AWAITING_PRE_IMAGE), and makes no generator call."""
    class Paid(O.StubGenerator):
        paid = True
        calls = 0

        def prepare_references(self, **kw):
            Paid.calls += 1
            return []
    db = _db()
    key = _parked_flux_run(db)
    _row(db, SLUG, O.RELEASE, state=SPL.AWAITING_PRE_IMAGE, reservation="none")
    out = IP._run_stage(db, {"slug": SLUG, "version": VERSION, "release": O.RELEASE,
                             "stage": "prepare_references", "route": IP.SP.FLUX_ROUTE,
                             "round": 0}, follow=lambda *a: None, generator=Paid())
    assert Paid.calls == 0, out
    assert IP.get_run(db, key)["state"] in (IP.AWAITING_PRE_IMAGE, IP.SALE_WAITING), out


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
