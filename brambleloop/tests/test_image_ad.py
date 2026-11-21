"""IMAGE-AD: the two open findings of IMAGE-E2E, closed.

A. A vessel (a Launch-0 basket) reaches a certified FLUX anchor. Its anchor is a pair: the
   top-down view and a side view standing, the side rendered by
   `image_stages.product_only(view="side")` as its own paid call. The side render is counted
   by the run cap, the per-gallery cap and the daily cap; its bytes ride through recovery and
   re-verification; a redrive buys nothing twice.
D. The template layout (D-OWNER-PDF-TEMPLATE) is the production PDF layout. Once the gallery
   is certified both editions are rebuilt with those frames embedded and re-certified
   (PremiumStandard and the sale checker); the build record binds to the gallery
   certificate; until then the engine PDF is the interim deliverable and never makes the
   listing package READY (D-OWNER-PDF-STANDARD).

Test doubles (labelled): the BFL HTTP transport (`test_image_e2e_worker.StubBFL`), whose
pixels are synthetic -- for a vessel request, the top-down or side render of the certified
CIR's own wall model (`test_v2_vessel_fidelity`), chosen from the request's own scene
text; the vision judges (`test_vis_gallery_e2e.GalleryJudges`); Laura's per-image
publication approval. Nothing reaches BFL, OpenAI or Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_image_ad.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import json
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import test_image_e2e_worker as E  # noqa: E402
import test_v2_vessel_fidelity as VF  # noqa: E402

BASKET, BASKET_CATEGORY = "market-basket-small", "basket"   # the Hexagonal Bread Basket
_S: dict = {}


@contextmanager
def product(slug, category):
    saved = (E.SLUG, E.CATEGORY)
    E.SLUG, E.CATEGORY = slug, category
    try:
        yield
    finally:
        E.SLUG, E.CATEGORY = saved


class VesselBFL(E.StubBFL):
    """StubBFL whose vessel requests are answered with the CIR's own vessel views: the side
    render for a request whose scene asks for the side, the top-down render for one that asks
    for the view from above. Every other request gets the flat lay, as before."""

    def __init__(self, cir):
        super().__init__(cir)
        from brambleloop.visual import vessel as V

        self.model = V.vessel_models(cir)[0]
        self.views: list[str] = []

    def urlopen(self, url, timeout=None, **kw):
        from PIL import Image

        target = getattr(url, "full_url", url)
        if not str(target).startswith("https://delivery."):
            return self._real_urlopen(url, timeout=timeout, **kw)
        text = json.dumps(self.posts[-1]) if self.posts else ""
        view = ("side" if "seen from the side" in text else
                "top" if "seen from directly above" in text else None)
        self.views.append(view or "flat")
        if view is None:
            return super().urlopen(url, timeout=timeout, **kw)
        self.fetches += 1
        w, h = self._pending[-1] if self._pending else (2048, 2048)
        raw = (VF.side_view(model=self.model, size=(w, h)) if view == "side"
               else VF.top_view(model=self.model, size=max(w, h)))
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        if im.size != (w, h):
            im = im.resize((w, h))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)

        class _R(io.BytesIO):
            headers = {"content-type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R(buf.getvalue())


class VesselVision(E.V6.StubVision):
    """The vision double, answering the craft question for the basket the way
    test_w4_fidelity's PASSING_JUDGE describes a plain crocheted piece: no edging, no
    ribbing (the bread basket's rim is a plain cream wall row). The blanket's double
    (PASSING_BANDS_JUDGE) describes an edging at the ends, which the basket does not have."""

    def read(self, prompt, images, **kw):
        if not prompt.startswith("Task: "):
            self.tasks.append("craft_texture")
            return E.T.PASSING_JUDGE.read(prompt, images, **kw)
        return super().read(prompt, images, **kw)


def vessel_judges(db):
    with product(BASKET, BASKET_CATEGORY):
        cir = E._cir(db, None)
    return E.VG.GalleryJudges(db, VesselVision(cir), cir)


def basket_run(**kw):
    kw.setdefault("judges_for", vessel_judges)
    with product(BASKET, BASKET_CATEGORY):
        db, version, rh = E.production_like()
        saved = E.StubBFL
        E.StubBFL = VesselBFL
        try:
            jobs, bfl = E.run_worker(db, **kw)
            # The basket's chain re-drafts its listing after the first package (re-price ->
            # listing.seo), which the package fence reads as "changed after package review",
            # so the gallery run parks waiting for sale admission. Production's six-hourly
            # listing.package sweep is the safety net; it is run here the same way (no new
            # probe, nothing called by hand), at most twice.
            from brambleloop.queue.durable import JobQueue
            from brambleloop.visual import image_production as IP

            for _ in range(2):
                if (IP.get_run(db, _key(version, rh)) or {}).get("state") != \
                        "waiting_for_sale_admission":
                    break
                JobQueue(db).enqueue("listing", "listing.package",
                                     {"cadence": "listing_package"},
                                     idempotency_key=f"sweep:{time.time_ns()}")
                more, bfl2 = E.run_worker(db, seed=False, **kw)
                jobs = more
                bfl.posts += bfl2.posts
                bfl.views += bfl2.views
                bfl.fetches += bfl2.fetches
        finally:
            E.StubBFL = saved
    return db, version, rh, jobs, bfl


def _key(version, rh):
    from brambleloop.visual import image_production as IP

    return IP.run_key(BASKET, version, rh, route=IP.SP.FLUX_ROUTE)


def _rows(db, key, role):
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        return [{"id": r.id, "sha256": r.sha256, "status": r.technical_status,
                 "checks": dict(r.checks or {}), "cost": r.cost_cad, "attempt": r.attempt}
                for r in s.scalars(select(ImageCandidate).where(
                    ImageCandidate.run_key == key, ImageCandidate.role == role)
                    .order_by(ImageCandidate.id))]


def _paid_by_run(db):
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    out: dict[str, int] = {}
    with db.session() as s:
        for r in s.scalars(select(ImageCandidate)):
            # image-production runs only (the fixture DB carries seeded learning rows)
            if r.sha256 and (r.cost_cad or 0) > 0 and r.run_key.startswith("imgprod:"):
                out[r.run_key] = out.get(r.run_key, 0) + 1
    return out


def clean():
    if "clean" not in _S:
        _S["clean"] = basket_run()
    return _S["clean"]


# ---- A: the vessel anchor -------------------------------------------------------------

def test_a1_a_basket_reaches_a_certified_vessel_anchor_from_its_side_and_top_views():
    from brambleloop.visual import image_production as IP

    db, version, rh, jobs, bfl = clean()
    key = _key(version, rh)
    sides, tops = _rows(db, key, IP.ANCHOR_SIDE_ROLE), _rows(db, key, IP.ANCHOR_ROLE)
    assert sides and tops, (sides, tops, IP.get_run(db, key))
    best = IP._best(db, listing=IP.get_run(db, key)["listing"], role=IP.ANCHOR_ROLE, run=key)
    assert best["technical_status"] == "PASS", (best, IP.get_run(db, key))
    top = next(r for r in tops if r["id"] == best["candidate_id"])
    fid = (top["checks"]["product_truth"].get("fidelity") or top["checks"]["product_truth"])
    assert fid.get("kind") == "vessel_anchor", fid
    # the pair: the anchor names the side view it was judged with, and it is that row
    pair = top["checks"]["_anchor_side"]
    assert pair["sha256"] in {r["sha256"] for r in sides}, (pair, sides)
    # the side request asked for the side; the anchor for the view from above
    assert "side" in bfl.views and "top" in bfl.views, bfl.views
    # the run got past the fidelity gate (finding A: it used to block here on vessel_views)
    run = IP.get_run(db, key)
    assert "vessel_views" not in (run.get("blocked_reason") or ""), run
    stages = IP._stage_data(db, key)
    assert stages.get("fidelity_gate", {}).get("status") is not None or \
        run["stage"] not in ("product_generation", "fidelity_gate"), (run, list(stages))


def test_a2_the_side_render_is_paid_once_and_counted_in_the_run_and_money_caps():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, version, rh, _jobs, bfl = clean()
    key = _key(version, rh)
    run = IP.get_run(db, key)
    sides = _rows(db, key, IP.ANCHOR_SIDE_ROLE)
    # every BFL submit has exactly one cost entry; each side view was a real (stub) submit
    assert len(E._costs(db)) == len(bfl.posts), (len(E._costs(db)), len(bfl.posts))
    # (later frames reuse the vessel scene text, so the stub's view tally is an upper bound)
    assert 1 <= len(sides) <= bfl.views.count("side"), (bfl.views, sides)
    assert all((r["cost"] or 0) > 0 for r in sides), sides
    # one side view per anchor attempt, never two for one attempt
    assert len({r["attempt"] for r in sides}) == len(sides), sides
    act = G.activation_state(db, "flux-3-image", "generation")["activation"]
    assert run["generation_calls"] <= IP.FLUX_MAX_GENERATION_CALLS, run
    assert run["spent_cad"] <= min(act["per_gallery_cad"], IP.MAX_SPEND_CAD_PER_GALLERY) + 1e-9
    assert sum(c[0] for c in E._costs(db)) <= act["daily_ceiling_cad"] + 1e-9


def test_a3_a_gallery_cap_of_one_buys_the_side_view_and_refuses_the_anchor_by_name():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, version, rh, _jobs, bfl = basket_run(env={G.GALLERY_IMAGE_CAP_ENV: "1"})
    key = _key(version, rh)
    run = IP.get_run(db, key)
    # the cap is per gallery: every image run (the FLUX gallery and the readmitted campaign
    # route each have their own) made at most one paid render, and no top anchor was bought
    paid = _paid_by_run(db)
    assert paid and all(n <= 1 for n in paid.values()), paid
    assert len(bfl.posts) - 1 == sum(paid.values()), (bfl.views, paid)   # less the probe
    assert bfl.views.count("top") == 0, bfl.views
    assert [r["status"] for r in _rows(db, key, IP.ANCHOR_SIDE_ROLE)] and \
        not _rows(db, key, IP.ANCHOR_ROLE), paid
    assert run["state"] == "blocked", run
    assert "gallery" in run["blocked_reason"] and "refused" in run["blocked_reason"], run
    assert "unresolved cost" not in run["blocked_reason"], run
    assert "_pending_paid_call" not in (IP._stage_data(db, key) or {})
    assert len(E._costs(db)) == len(bfl.posts)


def test_a4_a_daily_cap_counts_the_side_view():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, version, rh, _jobs, bfl = basket_run(env={G.DAILY_IMAGE_CAP_ENV: "2"})
    key = _key(version, rh)
    run = IP.get_run(db, key)
    assert len(bfl.posts) <= 2, bfl.views                     # probe + the side view
    assert bfl.views.count("top") == 0, bfl.views
    assert run["state"] == "blocked", run
    assert "daily_image_cap" in run["blocked_reason"], run["blocked_reason"]
    assert "_pending_paid_call" not in (IP._stage_data(db, key) or {})


def test_a5_a_redrive_of_the_anchor_stage_repeats_no_paid_call():
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.visual import image_production as IP

    _db, _v, _rh, _j, clean_bfl = clean()
    seen: set[int] = set()

    def redrive(db_, bfl):
        with db_.session() as s:
            done = [j for j in s.scalars(select(Job).where(
                Job.job_type == "visual.image_production", Job.status == JobStatus.DONE))
                if (j.inputs or {}).get("stage") in ("product_generation", "fidelity_gate")
                and j.id not in seen]
            for j in done:
                seen.add(j.id)
                j.status, j.attempts, j.finished_at = JobStatus.PENDING, 0, None
        for j in done:
            JobQueue(db_).enqueue("publishing", "visual.image_production", dict(j.inputs),
                                  idempotency_key=f"redrive:{j.id}:{time.time_ns()}")

    db, version, rh, _jobs, bfl = basket_run(after=redrive)
    assert seen, "the anchor stage was never redriven"
    assert bfl.views.count("side") == clean_bfl.views.count("side"), (bfl.views,
                                                                      clean_bfl.views)
    assert len(bfl.posts) == len(clean_bfl.posts), (len(bfl.posts), len(clean_bfl.posts))
    assert len(E._costs(db)) == len(bfl.posts)
    key = _key(version, rh)
    best = IP._best(db, listing=IP.get_run(db, key)["listing"], role=IP.ANCHOR_ROLE, run=key)
    assert best["technical_status"] == "PASS", best


def test_a6_reverify_judges_the_stored_pair_again_and_still_passes():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db, version, rh, _jobs, _bfl = clean()
    key = _key(version, rh)
    best = IP._best(db, listing=IP.get_run(db, key)["listing"], role=IP.ANCHOR_ROLE, run=key)
    judges = vessel_judges(db)
    out = IP.reverify(db, best["candidate_id"], judges=judges)
    assert out["reverified"] and out["technical_status"] == "PASS", out
    top = next(r for r in _rows(db, key, IP.ANCHOR_ROLE) if r["id"] == best["candidate_id"])
    assert top["checks"].get("_anchor_side"), "the pair was dropped on reverify"
    # without its side view the same anchor is UNKNOWN by name (the old defect)
    with db.session() as s:
        from brambleloop.visual.image_records import ImageCandidate

        row = s.get(ImageCandidate, best["candidate_id"])
        from brambleloop.core.artifacts import ArtifactStore

        data = ArtifactStore().get(row.sha256, db=db)
    bare = CG.fidelity_reading(db, {"role": IP.ANCHOR_ROLE, "slug": BASKET, "version": version,
                                    "data": data}, {"release_hash": rh})
    assert bare["status"] == "UNKNOWN", bare


# ---- D: the illustrated PDF -----------------------------------------------------------

def _blanket():
    if "blanket" not in _S:
        _S["blanket"] = E.full()
    return _S["blanket"]


def _built_rows(db, slug, version):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, Job

    with db.session() as s:
        return [(a.id, dict(a.detail or {}), dict((s.get(Job, a.job_id).inputs or {})
                                                  if a.job_id else {}))
                for a in s.scalars(select(AuditLog).where(
                    AuditLog.action == "assets.built",
                    AuditLog.artifact == f"{slug}@{version}").order_by(AuditLog.id))]


def test_d1_before_the_gallery_the_engine_pdf_is_interim_and_never_ready():
    from brambleloop.publish import listing_package as LP

    db, version, rh = E.production_like()
    rows = _built_rows(db, E.SLUG, version)
    assert rows, "no assets.built"
    detail = rows[-1][1]
    assert {v["layout"] for v in detail["pdf_layout"].values()} == {"engine_interim"}, detail
    assert all("awaiting gallery" in v["why"] for v in detail["pdf_layout"].values()), detail
    assert detail["illustrated"] is None
    pkg = LP.assemble(db, E.SLUG, version)
    whys = [b for b in pkg["blockers"] if b["source"] == "pdf_illustration"]
    assert whys and whys[0]["image"] is True, pkg["blockers"]
    assert "PDF_NOT_ILLUSTRATED" in whys[0]["why"], whys
    assert pkg["state"] != LP.READY


def _refusal(db):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        rows = [dict(a.detail or {}) for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "assets.illustration_refused",
            AuditLog.artifact == f"{E.SLUG}@{E.VERSION}").order_by(AuditLog.id))]
    return rows


def test_d2_the_certified_gallery_triggers_the_rebuild_which_binds_and_rechecks_the_pdfs():
    """The certified 7-frame gallery enqueues assets.build{illustrate: record}. Both editions
    are built in the template with the certificate's frames embedded, in order, and pass
    PremiumStandard and the sale checker (inside build_customer_pdf_with_layout). Before
    storing, the gallery's CONTENTS frame (a preview of the PDF) is re-checked against the
    new PDF; it previews the interim PDF, so the rebuild is refused BY NAME and the interim
    PDF stays the certified file (IMAGE-AD finding G: the CONTENTS <-> PDF cycle)."""
    from sqlalchemy import select

    from brambleloop.core.models import ListingSetCertificateRecord

    db, rh, jobs, _bfl = _blanket()
    illus = [j for j in E._jobs(db, "assets.build") if (j[3] or {}).get("illustrate")]
    assert illus and illus[-1][2] == "DONE", (illus, [j for j in jobs if j[1] == "assets.build"])
    with db.session() as s:
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == E.SLUG,
            ListingSetCertificateRecord.state == "valid"))
        cert_id, frames = cert.id, [f["sha256"] for f in cert.certificate["frames"]]
    assert illus[-1][3]["illustrate"] == cert_id and illus[-1][3]["release"] == rh
    refused = _refusal(db)
    assert refused, "no illustration outcome recorded"
    r = refused[-1]
    assert r["certificate_record"] == cert_id, r
    # the template build itself passed PremiumStandard and the sale checker; the layout
    # decision then found the CONTENTS frame previewing the interim PDF (finding G)
    assert "CONTENTS_PREVIEW_STALE" in str(r["why"]), r["why"]
    assert set(r["why"]) == {"US", "UK"}, r["why"]
    # nothing was stored as certified: the newest build is still the interim one
    from brambleloop.runtime import pipeline

    _id, detail, _inputs = _built_rows(db, E.SLUG, E.VERSION)[-1]
    assert {v["layout"] for v in detail["pdf_layout"].values()} == {"engine_interim"}, detail
    assert pipeline._certified_pdf_hashes(db, E.SLUG, E.VERSION, rh)


def test_d3_the_interim_state_is_consistent_and_never_ready():
    from brambleloop.commerce import deliverables
    from brambleloop.publish import listing_package as LP
    from brambleloop.runtime import pipeline

    db, rh, _jobs, _bfl = _blanket()
    pkg = LP.latest(db, E.SLUG, E.VERSION)
    ill = [b for b in pkg["blockers"] if b["source"] == "pdf_illustration"]
    assert ill and ill[0]["image"] is True and "PDF_NOT_ILLUSTRATED" in ill[0]["why"], \
        pkg["blockers"]
    assert pkg["state"] != LP.READY
    # the certified (interim) PDFs and every re-render agree: no PDF_HASH_DRIFT, with or
    # without the Laura double the worker ran under
    with E.VG.laura_publication_double(db):
        assert pipeline.check_pdf_hashes(db, slug=E.SLUG, version=E.VERSION, release=rh,
                                         rendered=deliverables.render_certified_pdfs(
                                             db, E.SLUG, E.VERSION))
    assert pipeline.check_pdf_hashes(db, slug=E.SLUG, version=E.VERSION, release=rh,
                                     rendered=_rerender(db))


def _rerender(db):
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.learn.service import pdf_help_links
    from brambleloop.publish.pdf import TERMINOLOGIES
    from brambleloop.publish.pdf_template import build_customer_pdf
    from brambleloop.quality.physical import calibration_from_db
    from brambleloop.runtime import release as R

    with product(E.SLUG, E.CATEGORY):
        cir = E._cir(db, E.VERSION)

    class _Ctx:
        def __init__(self, db_):
            self.db = db_
    released_on = R._released_on(_Ctx(db), E.SLUG, E.VERSION)
    twin = build_twin(cir, compile_cir(cir), calibration=calibration_from_db(db, cir))
    links = pdf_help_links(db, cir.to_dict())
    return {t: build_customer_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                  lesson_links=links, db=db).pdf_bytes for t in TERMINOLOGIES}


def test_d4_the_ready_rule_binds_the_illustrated_build_to_the_gallery_frames():
    """With an illustrated build on record (the refused build's own binding, filed as an
    `assets.built` row of the illustrate job), the READY rule accepts it only for the valid
    certificate's frames, in order; a re-issued record with the same frames stays bound."""
    from brambleloop.core.models import AuditLog
    from brambleloop.publish import listing_package as LP
    from brambleloop.runtime import etsy_ops

    db, rh, _jobs, _bfl = _blanket()
    framed0 = etsy_ops.certified_frames(db, E.SLUG, E.VERSION, release=rh)
    frames = [f.get("sha256") for f in framed0["frames"]]
    r = {"binding": {"certificate_record": framed0["record_id"], "frames": frames,
                     "embedded_frames": {"US": frames, "UK": frames}},
         "built_sha256_by_terminology": {"US": "0" * 64, "UK": "1" * 64}}
    illus = [j for j in E._jobs(db, "assets.build") if (j[3] or {}).get("illustrate")][-1]
    with db.session() as s:
        s.add(AuditLog(actor="test", action="assets.built", job_id=illus[0],
                       artifact=f"{E.SLUG}@{E.VERSION}",
                       detail={"pdf_layout": {t: {"layout": "template"} for t in ("US", "UK")},
                               "illustrated": r["binding"],
                               "pdf_sha256_by_terminology": r["built_sha256_by_terminology"]}))
    framed = etsy_ops.certified_frames(db, E.SLUG, E.VERSION, release=rh)
    assert LP.pdf_illustration_blockers(db, E.SLUG, E.VERSION, rh, framed) == []
    moved = {**framed, "record_id": framed["record_id"] + 1000}
    assert LP.pdf_illustration_blockers(db, E.SLUG, E.VERSION, rh, moved) == []
    reordered = {**framed, "frames": list(reversed(framed["frames"]))}
    stale = LP.pdf_illustration_blockers(db, E.SLUG, E.VERSION, rh, reordered)
    assert stale and "PDF_GALLERY_STALE" in stale[0], stale
    assert LP.pdf_illustration_blockers(db, E.SLUG, E.VERSION, rh, None)


if __name__ == "__main__":
    only = sys.argv[1:]
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and (not only or any(o in name
                                                                          for o in only)):
            t0 = time.time()
            try:
                fn()
                print("OK  ", name, f"{time.time() - t0:.0f}s", flush=True)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc)[:2000], flush=True)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
