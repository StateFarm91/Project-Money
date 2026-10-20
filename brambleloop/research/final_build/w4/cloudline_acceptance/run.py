#!/usr/bin/env python3
"""Cloudline acceptance: the first live acceptance test of autonomous image production, as one
command (W-VISNEXT2).

    Every image is an EXPERIMENT image and is never published.

The product is CERTIFIED (Cloudline Textured Baby Blanket 1.2.0), so no experiment mode is
needed for certification. The run goes through the production experiment command
(`experiments.controlled`, definition `exp-2026-10-21-cloudline-acceptance`), inside a
scratch SHADOW database:

1. **Certified pattern.** `gate.certify` and `assets.build` run through the real queue and
   handlers. The certificate must be GRANTED, and the certified PDFs must be hashed.
2. **References.** The four pattern references re-render to the frozen fingerprints.
3. **FLUX product-only.** The unfolded flat lay, at 2k.
4. **Fidelity.** `visual.fidelity` on the flat lay.
5. **Laura.** If the listing is eligible: the stage-A identity anchor in the reserved outfit
   (1k, intermediate), then lifestyle frames, with stage D editing the accepted frame.
6. **Gallery.** Assembly, the set check and campaign consistency.
7. **Approval card.** The gallery card: images, three separate decisions and the EXPERIMENT
   banner.

The owner's authorization is simulated in the scratch database exactly as the Command Center
records it (step-up). In production, the owner authorizes the definition in the Command
Center. Its CA$5 generation cap is shared with `exp-2026-10-20-wrap-7ref` and counted once.

Run it from `brambleloop/`:

    .venv/bin/python research/final_build/w4/cloudline_acceptance/run.py --dry-run
    BRAMBLELOOP_IMAGE_KEY_BFL=… ANTHROPIC_API_KEY=… .venv/bin/python research/final_build/w4/cloudline_acceptance/run.py --live

The dry run uses the stub provider and stub judges: no network, no key, no spend, and every
image and reading is marked STUB. `--live` reads both keys from the environment only. It
refuses before opening anything if either key is missing.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]                         # brambleloop/
sys.path.insert(0, str(ROOT / "src"))
DEFINITION = "exp-2026-10-21-cloudline-acceptance"
SLUG, VERSION = "cloudline-baby-blanket", "1.2.0"
KEY_VARS = ("BRAMBLELOOP_IMAGE_KEY_BFL", "ANTHROPIC_API_KEY")
WRAP_HARNESS = HERE.parent / "experiment_wrap" / "run.py"


class Refused(SystemExit):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wrap():
    """The WRAPTEST harness: its stub provider, stub judges and budgeted vision transport."""
    spec = importlib.util.spec_from_file_location("wraptest_run_cl", WRAP_HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_keys(live: bool) -> None:
    if live:
        missing = [k for k in KEY_VARS if not (os.environ.get(k) or "").strip()]
        if missing:
            raise Refused(f"REFUSED (no spend, nothing opened): missing {missing} in the "
                          f"environment")


def _drain(db, job_types, limit=50) -> int:
    from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    w, n = Worker(db, "cloudline-acceptance", job_types=job_types), 0
    while n < limit and w.run_once():
        n += 1
    return n


def run(*, live: bool, out: Path, generator=None, judges=None) -> dict:
    check_keys(live)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    from brambleloop.core import artifacts

    saved = artifacts.DEFAULT_DIR
    artifacts.DEFAULT_DIR = str(out / "artifacts")
    try:
        return _run(live=live, out=out, generator=generator, judges=judges)
    finally:
        artifacts.DEFAULT_DIR = saved


def _run(*, live: bool, out: Path, generator=None, judges=None) -> dict:
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Job, PatternVersion
    from brambleloop.experiments import controlled as C
    from brambleloop.queue.durable import DuplicateJob, JobQueue
    from brambleloop.runtime.pipeline import _certified_pdf_hashes
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.launch_imagery import _listing_parts

    timeline: list[dict] = []

    def step(n, name, **kw):
        timeline.append({"step": n, "name": name, "at": _now(), **kw})

    db = Database(f"sqlite:///{out / 'scratch_shadow.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    q = JobQueue(db)
    loaded = C.load(DEFINITION)
    defn = loaded["definition"]

    # 1. certified pattern: the real certify and assets.build handlers
    cir = _listing_parts(SLUG)[1][0]
    q.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
              idempotency_key=f"acceptance:certify:{cir.fingerprint}")
    _drain(db, ["gate.certify"])
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).where(PatternVersion.version == VERSION))
        certified, release = bool(pv and pv.certified), (pv.release_hash if pv else None)
    if not certified or release != defn["product"]["cir_hash"]:
        raise Refused(f"certification did not grant the frozen release ({str(release)[:12]})")
    q.enqueue("publishing", "assets.build", {"slug": SLUG, "version": VERSION,
                                             "release": release},
              idempotency_key=f"acceptance:assets:{release}")
    _drain(db, ["assets.build"])
    pdfs = _certified_pdf_hashes(db, SLUG, VERSION, release) or {}
    if set(pdfs) != {"US", "UK"}:
        raise Refused("assets.build recorded no certified US/UK PDF hashes")
    # The ordinary production run the chain just queued is left to its own gate: with
    # image_generation closed it stops before any call. It is not this test's run.
    _drain(db, [IP.JOB_TYPE], limit=5)
    ordinary = IP.get_run(db, IP.run_key(SLUG, VERSION, release))
    step(1, "certified pattern", granted=True, release=release, pdf_sha256=pdfs,
         ordinary_run=(ordinary or {}).get("status"))

    # 2. references: frozen fingerprints, checked before any spend
    v = C.verify(loaded, db)
    if not v["ok"]:
        raise Refused("definition drift: " + "; ".join(v["problems"]))
    step(2, "references verified", references=v["references"])

    # The owner's authorization, as the Command Center records it (step-up), then one run.
    auth = C.authorize(db, DEFINITION, by="owner:acceptance-harness", stepped_up=True)

    def enqueue(inputs, key):
        try:
            return q.enqueue(C.AGENT, C.JOB_TYPE, inputs, idempotency_key=key, max_attempts=1)
        except DuplicateJob as exc:
            return exc.existing_id

    sub = C.submit(db, DEFINITION, by="owner:acceptance-harness", enqueue=enqueue,
                   stepped_up=True)
    with db.session() as s:
        job = s.get(Job, sub["job_id"])
        inputs = dict(job.inputs)

    def ip_enqueue(inputs_, key):
        try:
            return q.enqueue("publishing", IP.JOB_TYPE, inputs_, idempotency_key=key)
        except DuplicateJob:
            return None

    started = C.run_job(db, inputs, job_id=sub["job_id"], enqueue=ip_enqueue)
    if not started.get("ran"):
        raise Refused(f"the controlled run did not start: {started.get('why')}")

    # 3-7: the orchestrator's stages, one durable job each, under the run's namespace
    W = _wrap()
    flux_log: list = []
    from brambleloop.visual.experiment import ExperimentBudget

    budget = ExperimentBudget(cap_cad=float(auth["generation_cap_cad"]))
    if generator is None:
        from brambleloop.creative import image_stages as S
        from brambleloop.creative.flux3_generator import Flux3Generator

        inner = S.flux3_renderer() if live else W.stub_renderer_class()()
        generator = Flux3Generator(db, renderer=inner, work_root=str(out / "work"),
                                   size="2048x2048")
        generator.paid = True if live else True       # the shared cap is exercised either way
    vision_log: list = []
    if judges is None:
        if live:
            from brambleloop.visual import candidate_gates as CG

            vb = ExperimentBudget(cap_cad=float(auth["vision_cap_cad"]))
            (out / "work").mkdir(exist_ok=True)
            vision = W.ExperimentVision(db, budget=vb, work=str(out / "work"), log=vision_log)
            judges = CG.RealJudges(db, vision=C.CappedVision(
                W.FidelityVisionJudge(vision), cap_cad=float(auth["vision_cap_cad"])))
        else:
            judges = W.StubJudges(db)
    n = 0
    while n < 80:
        job = q.claim("cloudline-acceptance", job_types=[IP.JOB_TYPE])
        if job is None:
            break
        res = IP.run_stage(db, dict(job.inputs), follow=ip_enqueue, generator=generator,
                           judges=judges)
        q.complete(job.id, outputs={"run_key": res.get("run_key"), "next": res.get("next")},
                   worker="cloudline-acceptance", lease_token=job.lease_token)
        n += 1
    ip_key = C.get_run(db, sub["run_id"])["receipt"].get("ip_run_key")
    ip = IP.get_run(db, ip_key)
    data = IP._stage_data(db, ip_key)
    step(3, "FLUX product-only", outputs=(data.get("product_generation") or {}).get("outputs"))
    step(4, "fidelity", evidence=(data.get("fidelity_gate") or {}).get("evidence"))
    step(5, "Laura (stage A identity anchor, lifestyle, stage D)",
         identity_anchor=(data.get("identity_anchor") or {}).get("outputs"),
         lifestyle=(data.get("lifestyle_generation") or {}).get("outputs"),
         remaining=(data.get("remaining_roles") or {}).get("outputs"))
    step(6, "gallery", outputs=(data.get("gallery_assembly") or {}).get("outputs"))
    card = C.card(db, sub["run_id"])
    step(7, "approval card", state=ip["state"], status=ip["status"],
         banner=(card or {}).get("banner"))
    controlled = C.get_run(db, sub["run_id"])
    summary = {"mode": "live" if live else "dry-run", "definition": DEFINITION,
               "definition_sha256": loaded["sha256"], "authorization": auth["auth_id"],
               "certified_release": release, "pdf_sha256": pdfs,
               "controlled_run": {k: controlled[k] for k in (
                   "run_id", "status", "generation_spent_cad", "vision_spent_cad",
                   "attempts")},
               "experiment_images": controlled["receipt"].get("images") or [],
               "orchestrator": {"run_key": ip_key, "state": ip["state"],
                                "status": ip["status"], "stages": ip["stages"],
                                "generation_calls": ip["generation_calls"]},
               "shared_cap_group": sorted(C.cap_group(DEFINITION)),
               "card_title_banner": (card or {}).get("banner"),
               "publication": ((card or {}).get("decisions") or {}).get(
                   "publication_authorization"),
               "stage_jobs": n, "timeline": timeline}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "card.json").write_text(json.dumps(card, indent=1, default=str))
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="stub provider (default)")
    g.add_argument("--live", action="store_true", help="real FLUX 3 + vision inside the caps")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else HERE / "out" / ("live" if a.live else "dry_run")
    try:
        s = run(live=bool(a.live), out=out)
    except Refused as exc:
        print(str(exc.code if hasattr(exc, "code") else exc))
        return 2
    print(json.dumps({k: v for k, v in s.items() if k != "timeline"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
