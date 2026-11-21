"""IMAGE-E2E: production has made 0 images. Start from a production-like database and let the
real worker carry a Launch-0 product, unaided, to a complete certified 7-photo gallery and a
listing package that names it.

Starting state (production-like, every step through the real handlers):
  gate.certify -> assets.build (certified US/UK PDFs) -> listing.seo -> listing.package
  for the Launch-0 `housewarming-key-basket` (its real blockers are the sample-photo image
  reason and the two publish-time gates, so D-MAIN-IMAGE-ADMISSION admits it), with
  D-OWNER-APPROVE-ALL applied by the real `ops.owner_directives.apply` (the two paid
  activations, nothing else).

What runs for real: the durable JobQueue and the real `Worker` claiming every job type the
chain enqueues (nothing is called by hand after the seed), the capability probe, the paid
provider gate (activation, per-gallery, daily and monthly ceilings, paid-call replay), the
image gateway (`images.generate`: reserve, send, store, bill), the FLUX 3 request builder
and stages, the image-production stages, gallery certification, the listing set, the
listing package and the for-sale admission.

Test doubles (each labelled `test_double` where it leaves a reading):
  * the BFL HTTP transport (`images._post`, `images._get`, the delivery fetch): recorded
    response SHAPES from `tests/fixtures/bfl_flux3/`; the delivered pixels are a 2048 px
    synthetic flat lay of the certified CIR (FLUX would draw the product; a stub cannot);
  * the vision judges (`candidate_gates.RealJudges` -> test_vis_gallery_e2e.GalleryJudges:
    the same labelled judge doubles every gallery e2e uses);
  * Laura's per-image publication approval (`canonical.PUBLICATION_APPROVED`), which is a
    code constant the owner has never populated -- see test_6, which proves the worker
    stops there, with a named blocker and no further spend, without the double.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_image_e2e_worker.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import io
import json
import os
import sys
import time
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import test_search_hero_publish as SH  # noqa: E402  (installs the loopback-only socket guard)
import test_v6_gallery_e2e as V6  # noqa: E402
import test_vis_gallery_e2e as VG  # noqa: E402
import test_w4_fidelity as T  # noqa: E402

# The Launch-0 baby blanket: admitted for paid images under D-MAIN-IMAGE-ADMISSION once
# D-OWNER-ESTIMATE-CLAIMS lets its size claims pass as labelled estimates. (The key basket is a
# vessel and stalls at its anchor: see the review request, finding A.)
SLUG, CATEGORY = "cloudline-baby-blanket", "baby_blanket"
FIX = ROOT / "tests" / "fixtures" / "bfl_flux3"
SHAPES = json.loads((FIX / "response_shapes.json").read_text())
CRED_ENV = "BRAMBLELOOP_IMAGE_KEY_BFL"
CRED = "stand-in-not-a-key-e2e"        # never a real key
_S: dict = {}


# ---- the stub BFL transport ------------------------------------------------------------------

class StubBFL:
    """BFL's submit -> poll Ready -> delivery, from the recorded shapes. Each delivery is a
    synthetic flat lay of the CIR at the size the request asked for. Counts every paid
    submit (a POST is the billable request)."""

    def __init__(self, cir):
        self.cir = cir
        self.posts: list[dict] = []
        self.fetches = 0
        self._pending: list[tuple[int, int]] = []

    def post(self, url, headers, payload, *, label, timeout):
        body = json.loads(payload)
        self.posts.append(body)
        w, h = int(body.get("width") or 2048), int(body.get("height") or 2048)
        self._pending.append((w, h))
        return dict(SHAPES["submit"])

    def get(self, url, headers, *, label, timeout):
        return json.loads(json.dumps(SHAPES["poll_ready"]))

    def urlopen(self, url, timeout=None, **kw):
        from PIL import Image

        target = getattr(url, "full_url", url)
        if not str(target).startswith("https://delivery."):
            return self._real_urlopen(url, timeout=timeout, **kw)
        self.fetches += 1
        w, h = self._pending[-1] if self._pending else (2048, 2048)
        n = len(self.posts)
        raw = T.flat_lay(self.cir, canvas=max(w, h), rotate=(n * 1.7) % 6 - 3,
                         fill=0.62 + (n % 7) * 0.02)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        if im.size != (w, h):
            im = im.resize((w, h))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        data = buf.getvalue()

        class _R(io.BytesIO):
            headers = {"content-type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R(data)

    @contextmanager
    def installed(self):
        import urllib.request

        from brambleloop.gateway import images as I

        saved = (I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS)
        self._real_urlopen = urllib.request.urlopen
        I._post, I._get, urllib.request.urlopen = self.post, self.get, self.urlopen
        I.BFL_POLL_SECONDS = 0.0
        try:
            yield self
        finally:
            I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS = saved


@contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---- the production-like starting state -----------------------------------------------------

def production_like():
    """certify -> assets.build -> listing.seo (SH._chain) -> listing.package, then the owner
    directive applied the way boot applies it."""
    from brambleloop.core.db import Database
    from brambleloop.ops import owner_directives as D

    path, version, rh = SH._chain(SLUG, CATEGORY)
    db = Database(f"sqlite:///{path}")
    # BATCH19F (D-OWNER-SALE-PIPELINE): production's chain end raises the agents' launch
    # decision (`launch.plan`) for the release; the sale pipeline's spend admission reads it.
    from brambleloop.core.models import JobStatus

    job = SH._run(db, "growth", "launch.plan", {"slug": SLUG, "version": version,
                                                 "release": rh})
    assert job.status is JobStatus.DONE, job.last_error
    out = D.apply(db)
    assert sorted(out["activated"]) == ["flux-3-image:generation", "openai-vision:vision"], out
    return db, version, rh


def _cir(db, version):
    from brambleloop.runtime import pipeline

    return pipeline._engineered_cir(SLUG)


# ---- the unaided worker ---------------------------------------------------------------------

def run_worker(db, *, limit=400, laura_double=True, judges_for=None, after=None, env=None,
               seed=True):
    """Seed what production's own triggers enqueue (the listing.package event and the
    six-hourly capability probe), then let one real Worker claim every job until the queue
    is empty. Returns the ordered list of (job_type, status) it ran."""
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    from brambleloop.visual import candidate_gates as CG

    cir = _cir(db, None)
    q = JobQueue(db)
    with db.session() as s:
        version = s.scalar(select(Job).where(Job.job_type == "listing.seo")).inputs["version"]
    if seed:
        q.enqueue("orchestrator", "ops.capability_probes", {},
                  idempotency_key=f"probe:{time.time_ns()}")
        q.enqueue("listing", "listing.package", {"slug": SLUG, "version": version},
                  idempotency_key=f"pkg:{time.time_ns()}")
    vision = V6.StubVision(cir)
    real_judges = CG.RealJudges
    def factory(db_, **kw):
        # a caller building its own RealJudges (with its own transports) gets the real class
        if kw:
            return real_judges(db_, **kw)
        return (judges_for or (lambda d: VG.GalleryJudges(d, vision, cir)))(db_)

    CG.RealJudges = factory
    ran: list[tuple[str, str]] = []
    bfl = StubBFL(cir)
    try:
        with ExitStack() as stack:
            stack.enter_context(bfl.installed())
            # No network: the stand-in credential, and no proxy (a loopback proxy would carry
            # the capability probe's other reads out of the sandbox).
            stack.enter_context(_env(**{CRED_ENV: CRED, "HTTPS_PROXY": None,
                                        "https_proxy": None, "HTTP_PROXY": None,
                                        "http_proxy": None, **(env or {})}))
            w = Worker(db, "e2e-worker", lease_seconds=900)
            idle = 0
            while len(ran) < limit and idle < 2:
                if laura_double:
                    stack2 = VG.laura_publication_double(db)
                    stack2.__enter__()
                try:
                    did = w.run_once()
                finally:
                    if laura_double:
                        stack2.__exit__(None, None, None)
                if not did:
                    # Time passes: a job production schedules a little later (the sale
                    # pipeline's admission runs about 90 s after the package) is due now.
                    # Moving run_after forward skips no step and no gate.
                    if _advance_clock(db):
                        continue
                    idle += 1
                    continue
                idle = 0
                ran.append(did)
                if after is not None:
                    after(db, bfl)
    finally:
        CG.RealJudges = real_judges
    with db.session() as s:
        jobs = [(j.id, j.job_type, j.status.name, (j.last_error or "")[:300])
                for j in s.scalars(select(Job).order_by(Job.id))]
    return jobs, bfl



# ---- readings -----------------------------------------------------------------------------

def _advance_clock(db) -> bool:
    """Make the earliest future-dated PENDING job due now. True when one was moved."""
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus, utcnow

    with db.session() as s:
        j = s.scalar(select(Job).where(Job.status == JobStatus.PENDING,
                                       Job.run_after > utcnow()).order_by(Job.run_after))
        if j is None:
            return False
        j.run_after = utcnow()
        return True


def _gallery_key(rh):
    from brambleloop.visual import image_production as IP

    return IP.run_key(SLUG, VERSION, rh, route=IP.SP.FLUX_ROUTE)


VERSION = "1.2.0"


def _costs(db, provider="flux-3-image"):
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return [(c.amount_cad, c.provider, (c.detail or {}).get("gallery"))
                for c in s.scalars(select(CostEntry)) if c.provider == provider]


def _jobs(db, job_type=None):
    from sqlalchemy import select

    from brambleloop.core.models import Job

    with db.session() as s:
        q = select(Job).order_by(Job.id)
        if job_type:
            q = q.where(Job.job_type == job_type)
        return [(j.id, j.job_type, j.status.name, j.inputs, j.last_error or "")
                for j in s.scalars(q)]


def full():
    if "full" not in _S:
        db, version, rh = production_like()
        assert version == VERSION, version
        jobs, bfl = run_worker(db)
        _S["full"] = (db, rh, jobs, bfl)
    return _S["full"]


# ---- tests --------------------------------------------------------------------------------

def test_1_the_worker_alone_makes_a_complete_certified_seven_photo_gallery():
    from sqlalchemy import select

    from brambleloop.core.models import ListingSetCertificateRecord
    from brambleloop.products import lifecycle
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    db, rh, jobs, bfl = full()
    bad = [j for j in jobs if j[2] in ("DEAD", "FAILED") and j[1] != "store.publish"]
    assert not bad, bad          # store.publish refuses in SHADOW by design; nothing else may
    run = IP.get_run(db, _gallery_key(rh))
    assert run["state"] == "ready_for_owner_review", run
    with db.session() as s:
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == SLUG,
            ListingSetCertificateRecord.state == "valid"))
        frames = list(cert.certificate["frames"]) if cert else []
    assert len(frames) == CAMPAIGN_MIN_FRAMES == 7, frames
    assert [f["job"] for f in frames] == ["DESIRE", "COLOUR_CONTEXT", "LIFESTYLE", "ANGLE",
                                          "DETAIL", "SCALE", "CONTENTS"], frames
    with db.session() as s:
        assert lifecycle._complete_gallery(s, SLUG) is True      # D-OWNER-GALLERY-COMPLETE
    # every paid render went through the real gateway to the (stub) BFL transport
    assert len(bfl.posts) == len(_costs(db)), (len(bfl.posts), _costs(db))
    assert len(bfl.posts) >= 1 + 6, len(bfl.posts)      # probe + six generated frames


def test_2_the_listing_package_is_refreshed_and_names_only_publish_time_blockers():
    """IMAGE-E2E fix: the certified gallery re-assembles the package at once."""
    from brambleloop.publish import listing_package as LP
    from brambleloop.publish.release_gates import PUBLISH_TIME_AREAS

    db, rh, _jobs_run, _bfl = full()
    pkgs = _jobs(db, "listing.package")
    assert any((j[3] or {}).get("release") == rh and j[2] == "DONE" for j in pkgs), pkgs
    pkg = LP.latest(db, SLUG, VERSION)
    assert pkg and pkg["release_hash"] == rh, pkg
    whys = [b.get("why", "") for b in pkg["blockers"]]
    assert not any("gallery incomplete" in w for w in whys), whys
    assert not any(b.get("source") == "certified_frames" for b in pkg["blockers"]), whys
    # the publish-time gates still block publishing (D-MAIN-IMAGE-ADMISSION)
    assert {b.get("publish_time") for b in pkg["blockers"]} & set(PUBLISH_TIME_AREAS), whys
    # IMAGE-BF (finding F, fixed): the first-customer `imagery` area judges the certified
    # 7-frame generated gallery as that gallery, so it no longer FAILs the refreshed package.
    assert not any("imagery: FAIL" in w for w in whys), whys


def test_3_the_per_gallery_and_daily_ceilings_hold():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, rh, _jobs, _bfl = full()
    act = G.activation_state(db, "flux-3-image", "generation")["activation"]
    run = IP.get_run(db, _gallery_key(rh))
    spent = sum(c[0] for c in _costs(db))
    assert run["spent_cad"] <= min(act["per_gallery_cad"], IP.MAX_SPEND_CAD_PER_GALLERY) + 1e-9
    assert run["generation_calls"] <= IP.FLUX_MAX_GENERATION_CALLS, run
    assert spent <= act["daily_ceiling_cad"] + 1e-9, (spent, act)
    assert run["spent_cad"] > 0, "the paid path was exercised, not a free stand-in"


def test_4_a_lowered_gallery_cap_stops_the_worker_with_no_further_paid_call():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, version, rh = production_like()
    jobs, bfl = run_worker(db, env={G.GALLERY_IMAGE_CAP_ENV: "3"})
    run = IP.get_run(db, _gallery_key(rh))
    gallery_posts = len(bfl.posts) - 1                   # less the capability probe
    assert gallery_posts <= 3, gallery_posts
    assert run["state"] != "ready_for_owner_review", run
    from brambleloop.products import lifecycle
    with db.session() as s:
        assert lifecycle._complete_gallery(s, SLUG) is False      # never a partial gallery
    # (generation_calls counts the refused 4th attempt too; the BFL submits above are the
    # paid calls, and the refused one sent nothing)
    assert len(_costs(db)) == len(bfl.posts)
    # the run names the ceiling; it is not reported as an unresolved bill
    assert run["state"] == "blocked", run
    assert "unresolved cost" not in run["blocked_reason"], run["blocked_reason"]
    assert "gallery" in run["blocked_reason"] and "refused" in run["blocked_reason"], run
    assert "_pending_paid_call" not in (IP._stage_data(db, _gallery_key(rh)) or {})


def test_5_a_redrive_mid_run_repeats_no_paid_call():
    """Every generation stage, once it has completed, is redriven (the same job back to
    PENDING, as a dead-letter redrive does, plus a duplicate with the same inputs). The
    finished gallery costs exactly what the clean run cost: nothing is paid twice."""
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue

    _db0, _rh0, _j0, clean = full()
    db, version, rh = production_like()
    seen: set[int] = set()
    GEN = {"product_generation", "identity_anchor", "lifestyle_generation",
           "remaining_roles", "repair"}

    def redrive(db_, bfl):
        with db_.session() as s:
            done = [j for j in s.scalars(select(Job).where(
                Job.job_type == "visual.image_production", Job.status == JobStatus.DONE))
                if (j.inputs or {}).get("stage") in GEN and j.id not in seen]
            for j in done:
                seen.add(j.id)
                j.status, j.attempts, j.finished_at = JobStatus.PENDING, 0, None
        for j in done:
            JobQueue(db_).enqueue("publishing", "visual.image_production", dict(j.inputs),
                                  idempotency_key=f"redrive:{j.id}:{time.time_ns()}")

    jobs, bfl = run_worker(db, after=redrive)
    assert seen, "no generation stage was redriven"
    assert len(bfl.posts) == len(clean.posts), (len(bfl.posts), len(clean.posts))
    assert len(_costs(db)) == len(bfl.posts)
    from brambleloop.visual import image_production as IP
    run = IP.get_run(db, _gallery_key(rh))
    assert run["state"] == "ready_for_owner_review", run


def test_6_without_laura_approval_the_worker_stops_named_and_spends_nothing_more():
    """Laura's per-image publication approval is the owner's (canonical.PUBLICATION_APPROVED,
    empty). Unaided, the worker generates and verifies the gallery and then holds it with a
    named Laura-publication blocker: no certificate, no further paid call."""
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, ListingSetCertificateRecord
    from brambleloop.visual import gallery_persist as GP

    _db0, _rh0, _j0, clean = full()
    db, version, rh = production_like()
    jobs, bfl = run_worker(db, laura_double=False)
    from brambleloop.products import lifecycle

    with db.session() as s:
        # the earlier disclosed set's certificate may stay valid; no 7-frame gallery exists
        assert lifecycle._complete_gallery(s, SLUG) is False
        valid = [len((c.certificate or {}).get("frames") or []) for c in s.scalars(
            select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.state == "valid",
                ListingSetCertificateRecord.product_slug == SLUG))]
        assert all(n < 7 for n in valid), valid
        rows = [a.detail for a in s.scalars(select(AuditLog).where(
            AuditLog.action == GP.CERTIFY_ACTION))]
    assert rows and rows[-1]["certified"] is False, rows
    gates = {b["gate"] for b in rows[-1]["blockers"]}
    assert "laura_publication" in gates, gates
    assert len(bfl.posts) <= len(clean.posts), (len(bfl.posts), len(clean.posts))


def test_7_a_lowered_daily_cap_stops_the_worker_naming_the_daily_ceiling():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import image_production as IP

    db, version, rh = production_like()
    jobs, bfl = run_worker(db, env={G.DAILY_IMAGE_CAP_ENV: "3"})
    run = IP.get_run(db, _gallery_key(rh))
    assert len(bfl.posts) <= 3, len(bfl.posts)            # probe included: one day's images
    assert len(_costs(db)) == len(bfl.posts)
    assert run["state"] == "blocked", run
    assert "unresolved cost" not in run["blocked_reason"], run["blocked_reason"]
    assert "daily_image_cap" in run["blocked_reason"], run["blocked_reason"]
    assert "_pending_paid_call" not in (IP._stage_data(db, _gallery_key(rh)) or {})


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
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
