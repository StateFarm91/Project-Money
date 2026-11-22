"""A genuinely READY release (D-OWNER-SALE-PIPELINE) for the draft / rollback / adoption /
activation suites, built through the REAL sale-pipeline code paths.

Since batch 19f no fixture reached an Etsy draft: store.publish publishes only a release that
is READY for sale -- a complete certified seven-frame gallery (D-OWNER-GALLERY-COMPLETE), both
premium PDFs certified for the release (D-OWNER-PDF-STANDARD) and a READY listing package.
`ready_chain()` builds one and returns `(db_path, version, release)`, exactly the shape of
`test_search_hero_publish._chain()`, so a suite swaps one call.

Faked, at their provider seams only (each is a labelled `test_double` in the readings it makes):

* **Image provider (BFL / FLUX 3).** `test_vis_gallery_e2e.GalleryGenerator`: the real
  `creative.flux3_generator` request builder on its `StubRenderer` (no network, no spend),
  injected through `image_production.run_stage(generator=...)` -- the same seam the worker
  fills from `image_production.resolve_generator`. Its pixels are a deterministic
  listing-size synthetic flat lay of the certified CIR.
* **Vision provider (OpenAI).** `test_v6_gallery_e2e.StubVision` (the `image_vision`
  transport: a fixed blind reading per task, consistent with the CIR) and the person judges
  `test_w4_ownerimg.StubJudges` (identity / anatomy / realism / body / outfit), injected
  through `image_production.run_stage(judges=...)`. The real deterministic gate code runs on
  those readings: `visual.fidelity.verify_anchor` / `verify_lifestyle`,
  `candidate_gates.evaluate`, `publish.motif_fidelity.judge`, campaign consistency,
  naturalism, the quality floor, `gallery_persist.certify_gallery` and
  `release_gates.generated_listing_set`.
* **Etsy HTTP.** Not touched here; the suites use `tests/fake_etsy.FakeEtsy` (loopback).

One gate RULE is still doubled inside the vision double, inherited unchanged from
`test_vis_gallery_e2e.GalleryJudges.product_truth` and disclosed in READY-FIXTURE.md: V1's
end-band rule keeps `craft_texture` UNKNOWN on every in-scene frame of a banded blanket (the
anchor's band measurement is never promoted into a scene), so with nothing else UNKNOWN or
FAILED that single dimension reads PASS. Every other dimension of that verdict is real.

Real (nothing below is replaced):

* `gate.certify` -> `assets.build` -> `listing.seo` (`test_search_hero_publish._chain`);
* `listing.package` through its handler, before and after the gallery;
* the for-sale admission in image production (`image_production.sale_admission`) -- NOT
  doubled here, unlike `test_vis_gallery_e2e.run_gallery`; it reads the recorded package;
* every `image_production` stage on the generated-gallery route on the durable JobQueue;
* Laura's per-gallery publication approval through the owner's real record path
  (`laura_approval.raise_card` + `decide`, owner actor, step-up asserted -- the same
  function the Command Center route calls after `auth.require_stepup`), which re-certifies
  the gallery through `gallery_persist.certify_gallery`. Not the global
  `canonical.PUBLICATION_APPROVED` override `test_vis_gallery_e2e` uses;
* `launch.plan` and every `sale.pipeline` stage (admission -> gallery -> pdf_build ->
  pdf_certify -> attach -> ready): the premium US/UK editions rendered in the owner's master
  template with the certified frames, certified by `publish.pdf_standard.check` on the stored
  bytes, the listing package re-assembled by the real packager, `ready_for_sale` re-checked.

Held, exactly as the suites already held them before 19f and as
`test_rehearsal_past_shadow_success._held_gates` holds them (each has its own tests; none is
a sale-pipeline gate): #75 listing parity (`pipeline._listing_parity`), the #126 search-grid
tournament and the Launch-0 first-customer scope gate. They are held only while the fixture
packages and drives the chain, and restored before it returns.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import test_search_hero_publish as SH
import test_rehearsal_past_shadow_success as RP

_BUILT: dict = {}
OWNER_ACTOR = "owner:cc:ready-fixture"
TAXONOMY_STEP = "taxonomy[simulated]"


def _rehearsal():
    """scripts/shadow_rehearsal.py, loaded as the suites load it."""
    import importlib.util
    import sys

    name = "shadow_rehearsal_ready_fixture"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, Path(__file__).resolve().parents[1] / "scripts" / "shadow_rehearsal.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[name] = mod
    return sys.modules[name]


def _simulated_taxonomy(db, version: str, rh: str) -> dict:
    """The rehearsal's simulated taxonomy step (the REAL listing.taxonomy_refresh on
    FakeEtsy's seller taxonomy, then the release's own listing.seo), run in production order:
    BEFORE the gallery. See READY-FIXTURE.md, finding F1: a listing.seo re-run after a
    generated gallery is certified is refused (POLICY_CLASSIFICATION), so the suites assert
    this recorded step instead of re-running it after the fixture."""
    from unittest.mock import patch

    from fake_etsy import FakeEtsy

    reh = _rehearsal()
    sim_tree, sim_craft = reh.simulated_taxonomy()
    rec = reh.Recorder()
    with FakeEtsy(taxonomy_nodes=sim_tree, required_property=sim_craft,
                  create_refuses_required_property=False) as fake:
        env = {"ETSY_API_KEY": fake.keystring, "ETSY_ACCESS_TOKEN": "111.live-token",
               "ETSY_SHOP_ID": fake.shop_id, "ETSY_SHARED_SECRET": fake.shared_secret}
        with patch.dict(os.environ, env):
            for k in ("ETSY_KEYSTRING", "ETSY_REFRESH_TOKEN"):
                os.environ.pop(k, None)
            reh.record_simulated_taxonomy(rec, db, {"slug": SH.SLUG, "version": version,
                                                    "release": rh}, fake_base=fake.base)
        assert not [r for r in fake.requests if r.get("operation") == "createDraftListing"]
    step = {s["step"]: s for s in rec.steps}[TAXONOMY_STEP]
    assert step["outcome"] == reh.PASS, step
    return step


def assert_taxonomy_recorded(db, slug: str, version: str) -> dict:
    """What `record_simulated_taxonomy` establishes, read back from the READY database: the
    simulated seller taxonomy is the snapshot on file and the release's category is CHOSEN
    from it, and the search certificate is PASS on the certified gallery."""
    from brambleloop.commerce import category

    chosen = category.publish_inputs(db, slug=slug, version=version)
    assert chosen.get("status") == category.CHOSEN and chosen.get("taxonomy_id"), chosen
    row = SH._profile(db, slug)
    assert row.verdict == "PASS", (row.verdict, (row.certificate or {}).get("reasons"))
    return chosen


def _gallery(db, version: str, rh: str) -> dict:
    """The generated-gallery route, real stages and real admission, fake providers only."""
    import test_v6_gallery_e2e as V6
    import test_vis_gallery_e2e as VG
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import laura_home as H
    from brambleloop.visual import room_references as RR
    from brambleloop.visual.launch_imagery import _listing_parts

    cir = _listing_parts(V6.CLOUD)[1][0]
    assert cir.slug == SH.SLUG and cir.version == version, (cir.slug, cir.version, version)
    adm = IP.sale_admission(db, cir.slug, cir.version, rh)
    assert adm["admitted"] is True, adm            # the REAL for-sale admission
    room = H.scene_for(cir.slug)["room"]
    manifest, _entry, _rb = V6._room_manifest(room)
    real_manifest = RR.MANIFEST
    RR.MANIFEST = manifest      # the approved room reference set, as V6 / VG install it
    try:
        vision = V6.StubVision(cir)                               # test_double: OpenAI vision
        judges = VG.GalleryJudges(db, vision, cir)                # test_double: person judges
        gen = VG.GalleryGenerator(db, cir)                        # test_double: BFL pixels
        follow, _ = O.drain(db, generator=gen, judges=judges)
        first = IP.trigger(follow, slug=cir.slug, version=cir.version, release=rh,
                           route="generated_gallery")
        _, ran = O.drain(db, generator=gen, judges=judges, limit=160)
    finally:
        RR.MANIFEST = real_manifest
    assert gen.requests, "the fake image provider was never asked"
    return {"key": first["run_key"], "ran": ran, "gen": gen, "judges": judges}


def _approve_laura(db, key: str) -> dict:
    """The owner approves this gallery's Laura frames on the real record path."""
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import laura_approval as LA

    st = GP.gallery_status(db, key)
    if st.get("ok"):
        return {"needed": False}
    assert LA.verified_but_for_laura(db, key, st), [
        (b.get("role"), b["gate"], b["status"], str(b.get("why"))[:160])
        for b in st["blockers"]]
    raised = LA.raise_card(db, key, st=st)
    req = raised.get("requirement_key") or LA.requirement_key(
        key, LA.digest(LA.laura_frames(st)))
    out = LA.decide(db, req, decision=LA.APPROVED, actor=OWNER_ACTOR, step_up=True,
                    via="ready_fixture", note="fixture owner reviewed the Laura frames")
    assert (out.get("recertified") or {}).get("certified") is True, out
    return {"needed": True, "requirement_key": req, "decision": out}


def _run_pending_publish_in_shadow(db) -> list[dict]:
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus, Phase
    from brambleloop.runtime.worker import Worker

    w = Worker(db, "ready-fixture-shadow", phase=Phase.SHADOW, job_types=["store.publish"],
               lease_seconds=900)
    for _ in range(5):
        if not w.run_once():
            break
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.job_type == "store.publish")))
        out = [{"id": r.id, "status": r.status.value,
                "published": (r.outputs or {}).get("published")} for r in rows]
    assert all(r["status"] not in (JobStatus.PENDING.value, JobStatus.RUNNING.value)
               and r["published"] is not True for r in out), out
    return out


def _build() -> tuple[str, str, str, dict]:
    import test_vis_gallery_e2e as VG
    from sqlalchemy import select

    from brambleloop.core.db import Database
    from brambleloop.core.models import JobStatus, ListingSetCertificateRecord
    from brambleloop.publish import listing_package as LP
    from brambleloop.publish import sale_pipeline as SPL
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    path, version, rh = SH._chain()
    slug = SH.SLUG
    db = Database(f"sqlite:///{path}")
    restore = RP._held_gates()
    try:
        # 0. The simulated seller taxonomy and the release's listing.seo, before the gallery.
        taxonomy = _simulated_taxonomy(db, version, rh)
        # 1. The listing package for the release, so the for-sale admission has a reading.
        job = SH._run(db, "listing", "listing.package", {"slug": slug, "version": version})
        assert job.status is JobStatus.DONE, job.last_error
        # 2. The seven-frame generated campaign, on fake providers, through the real route.
        g = _gallery(db, version, rh)
        # 3. Laura's publication approval, recorded by the owner path; re-certifies.
        laura = _approve_laura(db, g["key"])
        with db.session() as s:
            rec = s.scalar(select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.state == "valid"))
            assert rec is not None and rec.release_hash == rh, rec
            assert len(rec.certificate["frames"]) >= CAMPAIGN_MIN_FRAMES == 7, \
                rec.certificate["frames"]
        # 4. The package with the certified gallery, then the real sale chain to READY.
        job = SH._run(db, "listing", "listing.package", {"slug": slug, "version": version})
        assert job.status is JobStatus.DONE, job.last_error
        premium = VG._drive_sale_pipeline(db, slug, version, rh)
        run = SPL.get(db, slug, version, rh) or {}
        assert run.get("state") == SPL.READY, (run, premium["ran"])
        ready = SPL.ready_for_sale(db, slug, version, rh)
        assert ready["ready"] is True, ready
        pkg = LP.latest(db, slug, version) or {}
        assert SPL.package_ready_for_sale(pkg, rh), pkg.get("blockers")
        # 5. launch.plan enqueued its own store.publish (G1 in test_first_listing_doors). In
        #    production the worker runs it in SHADOW, where it is refused and dead-lettered;
        #    the fixture does exactly that, so no Etsy request is possible and nothing is
        #    left pending for a door to collide with.
        shadow_publish = _run_pending_publish_in_shadow(db)
    finally:
        restore()
        db.engine.dispose()
    info = {"shadow_publish": shadow_publish, "taxonomy": taxonomy, "premium": premium, "ready": ready, "laura": laura, "gallery_run": g["key"],
            "frames": len(rec.certificate["frames"])}
    return path, version, rh, info


def ready_chain(tag: str = "ready") -> tuple[str, str, str]:
    """A fresh copy of the READY release database: (path, version, release)."""
    if "base" not in _BUILT:
        _BUILT["base"] = _build()
    path, version, rh, _info = _BUILT["base"]
    copy = f"{path}.{tag}-{time.time_ns()}.sqlite"
    shutil.copyfile(path, copy)
    return copy, version, rh


def info() -> dict:
    """What the build produced (premium PDF hashes, the READY verdict, the Laura record)."""
    if "base" not in _BUILT:
        _BUILT["base"] = _build()
    return dict(_BUILT["base"][3])


__all__ = ["ready_chain", "info", "assert_taxonomy_recorded", "OWNER_ACTOR"]
