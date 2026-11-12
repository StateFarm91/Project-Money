#!/usr/bin/env python3
"""F-848: one recorded shadow rehearsal of a Launch-0 product, end to end, on a fresh database.

What it does, in order, and what each step's outcome means:

0. **Opportunity and design** (W4-C07): the product's radar seed in `radar.opportunity.POOL`
   (and whether today's portfolio still selects it), then every `launch0.product_truth` design
   gate on the candidate's CIR -- recorded before the pattern enters the chain.
1. **Boot.** The production start command (`railway.json`: uvicorn `brambleloop.app.main:app`,
   whose startup hook starts the embedded worker and scheduler) is launched as a subprocess
   with a scrubbed environment in SHADOW phase on a fresh file-backed SQLite database. The
   network is refused inside that process by `tests/network_guard.py`, installed through a
   `sitecustomize` on its PYTHONPATH; every refused attempt is logged. The only allowance is
   resolving the numeric literal `127.0.0.1` so uvicorn can bind its own listening socket
   (`AI_NUMERICHOST`: no resolver is consulted). `--fast` runs the same handlers through an
   in-process `Worker` instead of the subprocess (for the test suite); the evidence says so.
2. **Shadow chain.** The Launch-0 product's CIR is enqueued at `cir.compile`; the running
   system itself carries it through `gate.certify` -> `listing.draft` -> `assets.build` ->
   `pricing.position` -> `listing.seo` -> `launch.plan` -> `store.publish`, and in SHADOW the
   last one must be refused. Every step's outcome is read back from the database.
3. **Past-shadow (simulated).** The server is stopped. In this process, with the phase set to
   `limited_production`, the network narrowed to one loopback port served by
   `tests/fake_etsy.py` (never Etsy), fixture Etsy credentials for that fake, and the owner's
   publication grant recorded through the real `ops.publication_authority.approve` path,
   `store.publish` is run once more through the worker. A draft created on the fake is the
   PASS; a refusal is recorded with its reason, never worked around.
4. **Orders, support, ledger.** A fake receipt (Etsy ShopReceipt shape, never Etsy) for the
   product is fed through `commerce.orders_ingest` via its `reader_factory` seam with the
   receipts gate rows seeded as a simulated owner OAuth grant; a support case is taken in
   through `CustomerExperience.intake` and triaged/drafted by `support.triage` /
   `support.reply`; the ledger rows the ingest wrote and a `finance.reconcile` run are read.

Evidence is written to `research/final_build/evidence/shadow_rehearsal_<sha7>_<utc>.json`
(or `--out`), with every step's outcome, the expected outcome, and the database rows read as
proof. Outcomes: PASS, REFUSED_AS_EXPECTED, BLOCKED (a gate or defect stopped it; reason
recorded), FAILED (the rehearsal itself broke), SKIPPED (an earlier step made it impossible).

    cd brambleloop && .venv/bin/python scripts/shadow_rehearsal.py [--product SLUG] [--fast]

No model call, no secret, no real network, no live Etsy, no spend.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import shutil
import sys
import tempfile
import time
import traceback
import types
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO = ROOT.parent
EVIDENCE_DIR = ROOT / "research" / "final_build" / "evidence"
LAUNCH0_DEFAULT = "cloudline-baby-blanket"
# A fixture credential for the ops-token HMAC that seals the simulated owner grant. It is not a
# secret: it exists only inside this rehearsal's process and its throwaway database.
REHEARSAL_OPS_TOKEN = "rehearsal-fixture-owner-credential-not-a-secret-0001"
RUN_JOB_PATIENCE_S = 60.0   # how long an in-process step job may stay unclaimed (see _run_job)
CHAIN = ("cir.compile", "gate.certify", "listing.draft", "assets.build", "pricing.position",
         "listing.seo", "launch.plan", "store.publish")

PASS, REFUSED, BLOCKED, FAILED, SKIPPED = ("PASS", "REFUSED_AS_EXPECTED", "BLOCKED", "FAILED",
                                           "SKIPPED")
GOOD = {PASS, REFUSED}

_SITECUSTOMIZE = '''
import os, socket, sys, json
sys.path.insert(0, {root!r})
from tests import network_guard
_log = {log!r}
_orig_gai = socket.getaddrinfo
network_guard.install()
def _note(kind, args):
    with open(_log, "a") as f:
        f.write(json.dumps({{"pid": os.getpid(), "kind": kind, "args": repr(args)[:200]}}) + "\\n")
def _wrap(kind, fn):
    def inner(*a, **k):
        _note(kind, a)
        return fn(*a, **k)
    return inner
socket.socket.connect = _wrap("connect", socket.socket.connect)
socket.socket.connect_ex = _wrap("connect_ex", socket.socket.connect_ex)
socket.create_connection = _wrap("create_connection", socket.create_connection)
_refuse_gai = socket.getaddrinfo
def _gai(host, port, family=0, type=0, proto=0, flags=0):
    if host in ("127.0.0.1", b"127.0.0.1"):
        return _orig_gai(host, port, family, type, proto, flags | socket.AI_NUMERICHOST)
    _note("getaddrinfo", (host, port))
    return _refuse_gai(host, port, family, type, proto, flags)
socket.getaddrinfo = _gai
with open({marker!r}, "a") as f:
    f.write(str(os.getpid()) + "\\n")
'''


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout.strip()


class Recorder:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.defects: list[dict] = []

    def step(self, name: str, outcome: str, *, expected: str, observed, proof=None) -> dict:
        row = {"step": name, "outcome": outcome, "expected": expected,
               "observed": observed, "db_proof": proof or {}, "at": _utc().isoformat()}
        self.steps.append(row)
        print(f"[{outcome:>19}] {name}: {str(observed)[:160]}", flush=True)
        return row

    def defect(self, key: str, where: str, detail: str) -> None:
        self.defects.append({"key": key, "where": where, "detail": detail[:1200]})


# ---- network guards ----------------------------------------------------------------------


def _guard_narrowed(allow_port: int | None, log: list):
    """tests/network_guard.py, then one loopback port re-opened for the fake Etsy server."""
    sys.path.insert(0, str(ROOT))
    from tests import network_guard

    orig = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)
    restore = network_guard.install()
    refused = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)

    def allowed(host, port):
        return allow_port is not None and host in ("127.0.0.1", "localhost") and \
            int(port) == allow_port

    def connect(self, address):
        if isinstance(address, tuple) and len(address) >= 2 and allowed(*address[:2]):
            return orig[0](self, address)
        log.append({"kind": "connect", "address": repr(address)[:120]})
        return refused[0](self, address)

    def create_connection(address, *a, **k):
        if allowed(*address[:2]):
            return orig[1](address, *a, **k)
        log.append({"kind": "create_connection", "address": repr(address)[:120]})
        return refused[1](address, *a, **k)

    def getaddrinfo(host, port, *a, **k):
        if port is not None and allowed(host, port):
            return orig[2](host, port, *a, **k)
        log.append({"kind": "getaddrinfo", "address": repr((host, port))[:120]})
        return refused[2](host, port, *a, **k)

    socket.socket.connect = connect
    socket.create_connection = create_connection
    socket.getaddrinfo = getaddrinfo
    return restore


# ---- database reads ----------------------------------------------------------------------


def _jobs(db, types_=None, slug=None) -> list[dict]:
    from sqlalchemy import select

    from brambleloop.core.models import Job

    out = []
    with db.session() as s:
        for j in s.scalars(select(Job).order_by(Job.id)):
            if types_ and j.job_type not in types_:
                continue
            ins = dict(j.inputs or {})
            if slug and ins.get("slug") != slug and \
                    (ins.get("cir") or {}).get("slug") != slug:
                continue
            out.append({"id": j.id, "job_type": j.job_type, "status": j.status.value,
                        "last_error": (j.last_error or "")[:600], "inputs_keys": sorted(ins),
                        "idempotency_key": j.idempotency_key})
    return out


def _audits(db, action: str, artifact_prefix: str | None = None) -> list[dict]:
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == action)
                              .order_by(AuditLog.id)))
        return [{"id": a.id, "job_id": a.job_id, "actor": a.actor, "artifact": a.artifact,
                 "detail": dict(a.detail or {})} for a in rows
                if artifact_prefix is None or (a.artifact or "").startswith(artifact_prefix)]


def _trim(value, n=600):
    text = json.dumps(value, default=str, sort_keys=True)
    return value if len(text) <= n else text[:n] + "...(truncated)"


# ---- phase 1: boot + shadow chain ----------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _python() -> str:
    for cand in (ROOT / ".venv" / "bin" / "python",
                 Path("/home/user/Project-Money/brambleloop/.venv/bin/python")):
        if cand.exists():
            return str(cand)
    return sys.executable


def _boot_server(url: str, tmp: Path, artifacts: str):
    start = json.loads((ROOT / "railway.json").read_text())["deploy"]["startCommand"]
    if not start.startswith("uvicorn brambleloop.app.main:app"):
        raise RuntimeError(f"production start command changed: {start!r}")
    guard_dir = tmp / "guard"
    guard_dir.mkdir()
    log, marker = tmp / "net_refused.jsonl", tmp / "guard_installed"
    (guard_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE.format(
        root=str(ROOT), log=str(log), marker=str(marker)))
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(tmp), "LANG": "C.UTF-8",
           "PYTHONPATH": f"{guard_dir}{os.pathsep}{SRC}", "BRAMBLELOOP_DATABASE_URL": url,
           "BRAMBLELOOP_PHASE": "shadow", "BRAMBLELOOP_LOG_LEVEL": "WARNING",
           "BRAMBLELOOP_ARTIFACT_DIR": artifacts, "PYTHONDONTWRITEBYTECODE": "1",
           "BRAMBLELOOP_RUNNER_START_DELAY": "0", "BRAMBLELOOP_SCHEDULER_INTERVAL": "2",
           "BRAMBLELOOP_IDLE_SLEEP": "0.2"}
    port = _free_port()
    cmd = [_python(), "-m", "uvicorn", "brambleloop.app.main:app", "--host", "127.0.0.1",
           "--port", str(port), "--workers", "1"]
    proc = subprocess.Popen(cmd, cwd=str(tmp), env=env, stdout=subprocess.DEVNULL,
                            stderr=open(tmp / "server.stderr", "wb"))
    return proc, port, {"start_command": start, "argv": cmd[1:], "log": log, "marker": marker,
                        "env_keys": sorted(env)}


def _health(port: int, timeout: float = 120.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.5)
    return False


def _stop(proc) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)


def _publish_settled(db, slug) -> bool:
    rows = _jobs(db, ("store.publish",), slug)
    return any(r["status"] in ("dead", "done", "cancelled") for r in rows)


def _chain_terminal(db, slug) -> bool:
    """The chain reached store.publish and it settled, or it stopped before it -- and in
    either case NO chain job of this product is still waiting, running or retrying.

    A settled store.publish alone is not the end: the chain can re-enqueue a stage after it
    (a late `listing.seo` re-run after a re-price), and stopping the wait then recorded that
    still-pending job as the stage's FAILED outcome (the production-mode `listing.seo`
    FAILED seen on 4ea4c1cb and 9958d72 with nothing wrong in the chain)."""
    rows = _jobs(db, CHAIN, slug)
    if any(r["status"] in ("pending", "running", "failed") for r in rows):
        return False
    if _publish_settled(db, slug):
        return True
    return bool(rows) and all(r["status"] in ("done", "dead", "cancelled") for r in rows)


STALL_SECONDS = 300      # no progress anywhere in the queue for this long = stalled
CHAIN_CAP_SECONDS = 1800  # absolute bound on the shadow chain, progress or not


def _progress_mark(db, slug) -> tuple:
    """What counts as progress while waiting for the rehearsed chain to settle.

    The rehearsed product's chain shares one pool worker with everything the runtime
    schedules itself -- notably `chain.rebuild`, which fans out the other Launch-0 products'
    release chains at the same band. Under load the product's `store.publish` legitimately
    waits FIFO behind several minute-long `assets.build` jobs of other products (INT3 root
    cause of the b9f9243 `store.publish[shadow]` FAILED). Watching only this product's chain
    jobs read that busy worker as a stall. Progress is therefore: this chain changed, OR any
    job anywhere reached a terminal state or was claimed, OR a running job renewed its lease
    (a handler heartbeating between steps). A wedged runtime -- nothing finishes, nothing is
    claimed, no lease is renewed -- still produces an unchanged mark and is stopped."""
    from sqlalchemy import func, select

    from brambleloop.core.models import Job, JobStatus

    chain = tuple((r["id"], r["job_type"], r["status"]) for r in _jobs(db, CHAIN, slug))
    with db.session() as s:
        settled = s.scalar(select(func.count(Job.id)).where(Job.status.in_(
            [JobStatus.DONE, JobStatus.DEAD, JobStatus.CANCELLED]))) or 0
        running = tuple(sorted((j.id, str(j.lease_expires_at), int(j.attempts or 0))
                               for j in s.scalars(select(Job).where(
                                   Job.status == JobStatus.RUNNING))))
    return chain, settled, running


def _queue_ahead(db, slug) -> dict:
    """Evidence for a chain that did not settle: what the worker was doing and what was
    queued, so a busy worker is distinguishable from a stuck one in the report."""
    from sqlalchemy import select

    from brambleloop.core.models import Job, JobStatus

    with db.session() as s:
        running = [(j.id, j.job_type, (j.inputs or {}).get("slug"))
                   for j in s.scalars(select(Job).where(Job.status == JobStatus.RUNNING))]
        pending = [(j.id, j.job_type, j.priority, (j.inputs or {}).get("slug"))
                   for j in s.scalars(select(Job).where(
                       Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]))
                       .order_by(Job.priority, Job.run_after, Job.id).limit(40))]
    return {"running": running, "pending_by_priority": pending}


def _wait_for_chain(db, slug, *, stall: float = STALL_SECONDS, cap: float = CHAIN_CAP_SECONDS,
                    clock=time.time, sleep=time.sleep, poll: float = 2.0) -> dict:
    """Wait until the chain is terminal; return why the wait ended and for how long."""
    start = last = clock()
    seen = None
    reason = "cap"
    while clock() - start < cap:
        if _chain_terminal(db, slug):
            reason = "settled"
            break
        mark = _progress_mark(db, slug)
        if mark != seen:
            seen, last = mark, clock()
        elif clock() - last > stall:
            reason = "stalled"
            break
        sleep(poll)
    out = {"reason": reason, "waited_s": round(clock() - start, 1),
           "stall_s": stall, "cap_s": cap}
    if reason != "settled":
        out["queue"] = _queue_ahead(db, slug)
    return out


def run_shadow_chain(rec: Recorder, db, url: str, tmp: Path, artifacts: str, cir, *,
                     fast: bool) -> dict:
    from brambleloop.core.models import Phase
    from brambleloop.queue.durable import JobQueue

    slug = cir.slug
    ctx = {"mode": "in-process Worker (fast)" if fast else "production start command"}
    if fast:
        from brambleloop.runtime import pipeline  # noqa: F401 - registers every handler
        from brambleloop.runtime.worker import Worker

        log: list = []
        restore = _guard_narrowed(None, log)
        try:
            JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                                 priority=0, idempotency_key=f"rehearsal:compile:{slug}")
            w = Worker(db, "rehearsal-shadow", phase=Phase.SHADOW, lease_seconds=900)
            for _ in range(400):
                if not w.run_once():
                    break
        finally:
            restore()
        rec.step("boot", PASS, expected="runtime handlers run in SHADOW with network refused",
                 observed={"mode": ctx["mode"], "phase": "shadow",
                           "note": "fast mode: the production start command was NOT booted"},
                 proof={"network_refused_attempts": log})
        ctx["net_refused"] = log
        ctx["guard_installed"] = True
    else:
        proc, port, info = _boot_server(url, tmp, artifacts)
        try:
            healthy = _health(port)
            boots = _audits(db, "runtime.started")
            installed = info["marker"].read_text().split() if info["marker"].exists() else []
            ok = healthy and bool(boots) and str(proc.pid) in installed
            rec.step("boot", PASS if ok else FAILED,
                     expected="production start command serves /health in SHADOW with the "
                              "network guard installed in its process",
                     observed={"health_200": healthy, "pid": proc.pid,
                               "guard_installed_in_pids": installed,
                               "start_command": info["start_command"], "argv": info["argv"],
                               "env_keys": info["env_keys"]},
                     proof={"runtime.started": [_trim(b, 300) for b in boots]})
            ctx["guard_installed"] = str(proc.pid) in installed
            if not ok:
                raise RuntimeError("server did not boot: "
                                   + (tmp / "server.stderr").read_text()[-1500:])
            JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                                 priority=0, idempotency_key=f"rehearsal:compile:{slug}")
            ctx["wait"] = _wait_for_chain(db, slug)
        finally:
            _stop(proc)
        log_path = info["log"]
        ctx["net_refused"] = ([json.loads(x) for x in log_path.read_text().splitlines()]
                              if log_path.exists() else [])
    return ctx


def record_chain(rec: Recorder, db, cir, ctx: dict) -> dict:
    from sqlalchemy import select

    from brambleloop.core.models import Listing, ListingSearchProfile, PatternVersion, Product

    slug, version = cir.slug, cir.version
    all_jobs = _jobs(db, CHAIN, slug)
    jobs = {j["job_type"]: j for j in all_jobs}       # the latest of each type for this slug
    state: dict = {"slug": slug, "version": version}
    rec.step("chain.jobs", PASS if all_jobs else FAILED,
             expected="the release chain for this product ran inside the runtime",
             observed={"jobs": len(all_jobs), "wait": ctx.get("wait")},
             proof={"jobs": [(j["id"], j["job_type"], j["status"]) for j in all_jobs]})

    def job_step(name, expected, ok_pred, proof, *, refused=False, job_type=None):
        j = jobs.get(job_type or name)
        if j is None:
            return rec.step(name, SKIPPED, expected=expected,
                            observed="job never enqueued: the chain stopped earlier",
                            proof=proof)
        if refused:
            outcome = REFUSED if ok_pred(j) else (BLOCKED if j["status"] == "dead" else FAILED)
        else:
            outcome = PASS if ok_pred(j) else (BLOCKED if j["status"] == "dead" else FAILED)
        return rec.step(name, outcome, expected=expected,
                        observed={"job": j["id"], "status": j["status"],
                                  "last_error": j["last_error"]}, proof=proof)

    job_step("cir.compile", "compiles clean and enqueues gate.certify",
             lambda j: j["status"] == "done",
             {"cir.compiled": [_trim(a["detail"]) for a in _audits(db, "cir.compiled", slug)]})
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product else None)
        pv_proof = ({"certified": pv.certified, "release_hash": pv.release_hash,
                     "granted": (pv.certificate or {}).get("granted"),
                     "stages_run": (pv.certificate or {}).get("stages_run")}
                    if pv else None)
        state["release"] = pv.release_hash if pv else None
    job_step("gate.certify", "certificate granted and PatternVersion certified",
             lambda j: j["status"] == "done" and bool(pv_proof and pv_proof["certified"]),
             {"pattern_versions": pv_proof,
              "gate.certified": [_trim(a["detail"], 400)
                                 for a in _audits(db, "gate.certified", slug)]})
    built = _audits(db, "assets.built", slug)
    job_step("assets.build", "PDFs (US/UK) and listing images built and hashed",
             lambda j: j["status"] == "done" and bool(built),
             {"assets.built": [{"artifact": a["artifact"],
                                "pdfs": {t: (p or {}).get("sha256") for t, p in
                                         (a["detail"].get("pdfs") or {}).items()}}
                               for a in built],
              "assets.listing_images_built": [_trim(a["detail"], 400) for a in
                                              _audits(db, "assets.listing_images_built", slug)]})
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        profile = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))
        l_proof = ({"id": listing.id, "title": listing.title, "price_cad": listing.price_cad,
                    "tags": list(listing.tags or []), "release_hash": listing.release_hash,
                    "etsy_listing_id": listing.etsy_listing_id} if listing else None)
        p_proof = ({"verdict": profile.verdict, "category_status": profile.category_status,
                    "taxonomy_id": profile.taxonomy_id} if profile else None)
    state["search_profile"] = p_proof
    job_step("listing.seo", "Listing row written from the certified release",
             lambda j: j["status"] == "done" and bool(l_proof),
             {"listings": l_proof, "listing_search_profiles": p_proof,
              "listing.seo_drafted": len(_audits(db, "listing.seo_drafted", slug)),
              "listing.seo_blocked": [_trim(a["detail"], 400)
                                      for a in _audits(db, "listing.seo_blocked", slug)]})
    refused = _audits(db, "store.publish_refused", slug)
    published = _audits(db, "store.published")
    gates = _audits(db, "store.release_gates", slug)
    job_step("store.publish[shadow]",
             "refused in SHADOW by the capability layer; no store.published row",
             lambda j: j["status"] == "dead" and "capability not enabled" in j["last_error"]
             and bool(refused) and not published,
             {"store.publish_refused": [_trim(a["detail"], 900) for a in refused],
              "store.published": len(published),
              "store.release_gates": [_trim(a["detail"], 900) for a in gates]},
             refused=True, job_type="store.publish") if "store.publish" in jobs else rec.step(
        "store.publish[shadow]", BLOCKED, expected="refused in SHADOW",
        observed="the chain stopped before store.publish",
        proof={"chain": [(j["job_type"], j["status"], j["last_error"][:200])
                         for j in _jobs(db, None, slug)]})
    if gates:
        state["release_gate_reasons"] = gates[-1]["detail"].get("reasons")
        state["release_gates_block"] = gates[-1]["detail"].get("blocks_release")
    rec.step("network[shadow]", PASS if ctx.get("guard_installed") else FAILED,
             expected="tests/network_guard.py installed in the process that ran the chain; "
                      "every connection attempt refused and logged",
             observed={"guard_installed": bool(ctx.get("guard_installed")),
                       "refused_attempts": len(ctx["net_refused"])},
             proof={"refused": ctx["net_refused"][:25]})
    state["publish_inputs"] = None
    with db.session() as s:
        from brambleloop.core.models import Job

        for j in s.scalars(select(Job).where(Job.job_type == "store.publish")
                           .order_by(Job.id.desc())):
            if (j.inputs or {}).get("slug") == slug and \
                    (j.inputs or {}).get("version") == version:
                state["publish_inputs"] = dict(j.inputs)
                break
    return state


def record_listing_package(rec: Recorder, db, state: dict) -> dict | None:
    """F-848 (owner goal L3): the certified release reaches a LISTING PACKAGE in the rehearsal.

    `listing.package` is a six-hourly cadence sweep (runtime.worker CADENCES), so a rehearsal
    that only waits for the release chain never reaches it. This runs the real job through the
    real Worker on the rehearsal's own database and reads back the durable package
    (`publish.listing_package.latest`, an OperatingReading) for exactly this release.

    Review L3 MED: this runs after the settled chain, so after the in-chain
    `store.publish[shadow]` refusal; store.publish does not read the package. The package is
    the owner-review artefact the settled chain yields, recorded beside the refusal, not a
    precondition of it.

    PASS means the package exists, is bound to the certified release hash, publishes nothing,
    and is honest about its state: ready_for_owner_review, or blocked with every blocker named
    (source and why). The package's own state is recorded as observed, never upgraded: a
    package blocked by a real gate (e.g. no attested sample photo) is the true state of the
    product, and the evidence says so."""
    from brambleloop.core.models import Phase
    from brambleloop.publish import listing_package as LP
    from brambleloop.runtime import listing_package_ops  # noqa: F401 - registers the handler

    slug, version, release = state.get("slug"), state.get("version"), state.get("release")
    expected = ("the real listing.package job records this certified release's package, bound "
                "to its release hash: ready_for_owner_review, or blocked with every blocker "
                "named; nothing published")
    if not release:
        rec.step("listing.package", SKIPPED, expected=expected,
                 observed="no certified release: the chain stopped before certification",
                 proof={"state": {k: state.get(k) for k in ("slug", "version", "release")}})
        return None
    job = _run_job(db, "listing", listing_package_ops.JOB_TYPE, {}, Phase.SHADOW)
    # Review L3 LOW: the verdict is THIS job's. Its own audit must name this release's
    # package, in the same state as the stored record; a package another sweep wrote proves
    # nothing about this run.
    mine = [a for a in _audits(db, "listing.package") if a.get("job_id") == job["id"]]
    key = f"{slug}@{version}"
    named = [r for a in mine for r in (a["detail"].get("results") or [])
             if r.get("key") == key]
    pkg = LP.latest(db, slug, version) if named else None
    if pkg is not None and named[-1].get("state") != pkg.get("state"):
        pkg = None
    every_named = bool(pkg) and all(b.get("source") and str(b.get("why") or "").strip()
                                    for b in pkg.get("blockers") or [])
    honest = bool(pkg) and (
        (pkg.get("state") == LP.READY and not pkg.get("blockers"))
        or (pkg.get("state") == LP.BLOCKED and bool(pkg.get("blockers")) and every_named))
    ok = (job["status"] == "done" and bool(pkg) and pkg.get("release_hash") == release
          and pkg.get("publishes") is False and honest)
    rec.step("listing.package", PASS if ok else (BLOCKED if job["status"] == "dead" else FAILED),
             expected=expected,
             observed={"job": job, "package_state": (pkg or {}).get("state"),
                       "blockers": len((pkg or {}).get("blockers") or []),
                       "bound_to_release": bool(pkg) and pkg.get("release_hash") == release},
             proof={"operating_readings.listing_package": None if not pkg else {
                 "key": f"{slug}@{version}", "state": pkg.get("state"),
                 "release_hash": pkg.get("release_hash"),
                 "fingerprint": pkg.get("fingerprint"),
                 "publishes": pkg.get("publishes"),
                 "gallery": len(pkg.get("gallery") or []),
                 "files": sorted((pkg.get("files") or {}).get("pdf_sha256_by_terminology")
                                 or {}),
                 "blockers": [{"source": b.get("source"), "why": _trim(b.get("why"), 300)}
                              for b in pkg.get("blockers") or []]},
                 "listing.package audits (this job)": [_trim(a["detail"], 600)
                                                       for a in mine]})
    if pkg:
        state["listing_package"] = {"state": pkg.get("state"),
                                    "blockers": [b.get("source") for b in
                                                 pkg.get("blockers") or []]}
    return pkg

def seed_catalogue(rec: Recorder, db, primary_slug: str, *, max_steps: int = 4000) -> dict:
    """F-848 next_action (review L3 item 1): readiness judged on a PRODUCTION-SHAPED state.

    A fresh database holding one product can never pass catalogue depth, the storefront
    preview or the economics, whatever the owner does. Production's own data (its live
    `launch.assessed`, a continuity export) is not read here: that needs the operator
    credential and production access. Instead every other Launch-0 release is driven through
    the SAME real chain handlers (compile, certify, assets, pricing, SEO, launch plan, the
    store.publish refusal) in-process, in SHADOW, on the rehearsal's own database, so the
    readiness verdict the owner phase transition cites is read from a real catalogue the
    company built, not from a stub. Nothing is assumed: products that do not certify or list
    are counted as such, and readiness reports whatever it reads."""
    from sqlalchemy import select

    from brambleloop.core.models import Listing, PatternVersion, Phase, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers every handler
    from brambleloop.runtime.release_recovery import launch0_releases
    from brambleloop.runtime.worker import Worker

    others = [c for c in launch0_releases() if c.slug != primary_slug]
    log: list = []
    restore = _guard_narrowed(None, log)
    steps = 0
    try:
        for cir in others:
            JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                                 priority=0,
                                 idempotency_key=f"rehearsal:catalogue:{cir.slug}:{cir.version}")
        w = Worker(db, "rehearsal-catalogue", phase=Phase.SHADOW, lease_seconds=900)
        while steps < max_steps and w.run_once():
            steps += 1
    finally:
        restore()
    with db.session() as s:
        certified = sorted({f"{p.slug}@{v.version}" for p, v in s.execute(
            select(Product, PatternVersion).join(
                PatternVersion, PatternVersion.product_id == Product.id).where(
                PatternVersion.certified == True))})  # noqa: E712
        listed = sorted({f"{l.product_slug}@{l.version}" for l in s.scalars(select(Listing))})
    wanted = sorted(f"{c.slug}@{c.version}" for c in others)
    settled = steps < max_steps
    rec.step("catalogue[production-shaped]", PASS if settled else FAILED,
             expected=("every other Launch-0 release driven through the real chain handlers "
                       "in SHADOW on this database, so readiness reads a real catalogue"),
             observed={"releases": len(wanted), "worker_steps": steps, "settled": settled,
                       "certified": len(certified), "listed": len(listed),
                       "network_refused_attempts": len(log)},
             proof={"wanted": wanted, "pattern_versions.certified": certified,
                    "listings": listed,
                    "simulation": "in-process Worker over the real handlers; production data "
                                  "is not read (it needs the operator credential)"})
    return {"certified": certified, "listed": listed}


def simulated_taxonomy():
    """The SIMULATED Etsy seller taxonomy the past-shadow fake serves (review L3 item 2).

    Etsy's own NAMES as production's 2026-10-21 refresh recorded them
    (research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_*.json;
    LAUNCHFIX.md section 4): crochet is never a pattern node; the pattern node is
    "Patterns & How To > Patterns & Blueprints", and crochet can only be confirmed by a
    "Crochet" value in that node's property schema. The ids are ILLUSTRATIVE (production
    recorded names only), and the "Crochet" value is an ASSUMPTION: whether Etsy's schema
    offers it is UNKNOWN until production's refresh records `category_choices`
    (LAUNCHFIX section 4). The evidence states both; nothing here is Etsy's data."""
    sys.path.insert(0, str(ROOT / "tests"))
    import fixtures_etsy_taxonomy as FX

    N = FX._node
    kids = ["Books & Magazines", "Craft Machine Files", "Critiques & Shop Tutorials", "Kits",
            "Patterns & Blueprints", "Recipes", "Tutorials"]
    tree = (
        N(1, "Art & Collectibles", 0, None, [N(2, "Fiber Arts", 1, 1, [N(3, "Crochet", 2, 2)])]),
        N(10, "Craft Supplies & Tools", 0, None, [
            N(11, "Patterns & How To", 1, 10, [N(20 + i, k, 2, 11) for i, k in enumerate(kids)]),
            N(40, "Tools & Equipment", 1, 10, [N(41, "Tools", 2, 40, [
                N(42, "Hooking", 3, 41, [N(43, "Crochet Hooks", 4, 42)])])])]))
    craft = FX.prop(9001, "Craft type", ("Crochet", "Knitting"))
    return tree, craft


SIMULATED_TAXONOMY_LABEL = (
    "SIMULATED taxonomy: Etsy's own node names from production's 2026-10-21 refresh, "
    "ILLUSTRATIVE ids, and an ASSUMED 'Crochet' value in the Patterns & Blueprints schema "
    "(UNKNOWN in production until its refresh records category_choices; LAUNCHFIX section 4)")

def record_simulated_taxonomy(rec: Recorder, db, state: dict, *, fake_base: str) -> None:
    """Review L3 item 2: approval -> simulated publish needs a category. In production the
    taxonomy is read by `listing.taxonomy_refresh` behind the owner's etsy_api gate. Here the
    REAL refresh job reads tests/fake_etsy.py's seller-taxonomy tree (the simulated Etsy the
    past-shadow phase already uses), then the release's own `listing.seo` re-runs so category
    selection reads that snapshot. Labelled SIMULATED in the evidence; nothing leaves the
    rehearsal's database. Whatever the gate or the selector says is recorded as it is."""
    from sqlalchemy import select

    from brambleloop.commerce import category
    from brambleloop.core.models import Job, Phase

    from brambleloop.integrations import etsy_taxonomy

    slug, version = state["slug"], state["version"]
    # The API-key taxonomy client carries its own base URL (etsy_taxonomy.ApiKeyTaxonomyClient);
    # like EtsyClient.BASE in this phase, it is pointed at the local fake only for this call.
    saved_base = etsy_taxonomy.ApiKeyTaxonomyClient.BASE
    etsy_taxonomy.ApiKeyTaxonomyClient.BASE = fake_base
    try:
        refresh = _run_job(db, "listing", "listing.taxonomy_refresh", {},
                           Phase.LIMITED_PRODUCTION)
    finally:
        etsy_taxonomy.ApiKeyTaxonomyClient.BASE = saved_base
    seo_inputs = None
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "listing.seo")
                           .order_by(Job.id.desc())):
            if (j.inputs or {}).get("slug") == slug and \
                    (j.inputs or {}).get("version") == version:
                seo_inputs = dict(j.inputs)
                break
    seo = (_run_job(db, "listing", "listing.seo", seo_inputs, Phase.LIMITED_PRODUCTION)
           if seo_inputs is not None else None)
    try:
        chosen = category.publish_inputs(db, slug=slug, version=version)
    except Exception as e:  # noqa: BLE001 - recorded as it is
        chosen = {"status": "ERROR", "why": f"{type(e).__name__}: {e}"[:300]}
    refreshed = [a for a in _audits(db, "etsy.taxonomy_refreshed")
                 if a.get("job_id") == refresh["id"]]
    unmeasured = [a for a in _audits(db, "etsy.taxonomy_unmeasured")
                  if a.get("job_id") == refresh["id"]]
    ok = (refresh["status"] == "done" and bool(refreshed)
          and chosen.get("status") == category.CHOSEN and bool(chosen.get("taxonomy_id")))
    rec.step("taxonomy[simulated]", PASS if ok else BLOCKED,
             expected=("the real listing.taxonomy_refresh reads the SIMULATED Etsy taxonomy "
                       "(tests/fake_etsy.py) and the release's listing.seo selects a category "
                       "from that snapshot"),
             observed={"refresh_job": refresh, "seo_job": seo,
                       "category": {k: chosen.get(k) for k in
                                    ("status", "taxonomy_id", "certified", "why")}},
             proof={"etsy.taxonomy_refreshed": [_trim(a["detail"], 600) for a in refreshed],
                    "etsy.taxonomy_unmeasured": [_trim(a["detail"], 600) for a in unmeasured],
                    "simulation": SIMULATED_TAXONOMY_LABEL})
    if not ok:
        rec.defect("simulated_taxonomy_not_chosen", "commerce/category.publish_inputs",
                   json.dumps({"refresh": refresh, "category": chosen}, default=str)[:600])

def _stored_search_verdict(db, slug: str, version: str):
    """The search certificate verdict as stored now, or None when no profile exists."""
    from sqlalchemy import select

    from brambleloop.core.models import ListingSearchProfile

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))
        return row.verdict if row else None


def record_edges(db, slug: str, version: str) -> dict:
    """F-834 (W4-CLOSE6): the evidence edges producer -> durable state -> consumer -> decision ->
    effect -> result, read from the rows this run wrote, so a packet can carry a receipt for
    each stage instead of the producer alone.

    `durable` names, per producer job type, the row it wrote and the job that wrote it (the
    audit row the producer emitted carries the job id). `consumers["store.publish"]` records
    that the publish job READ that state: its `store.release_gates` audit -- written by that
    job -- names the same slug, version and release hash. It also records what the job decided
    (refused in SHADOW, and whether the release gates would block), the effect it wrote (the
    `store.publish_refused` audit row) and the result (no `store.published` row; the listing
    has no Etsy id). Nothing is inferred: an edge whose rows are absent is not recorded.
    """
    from sqlalchemy import select

    from brambleloop.core.models import Job, Listing, PatternVersion, Product

    jobs = {j["job_type"]: j for j in _jobs(db, CHAIN, slug)}
    durable: dict = {}
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product else None)
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        pv_d = ({"id": pv.id, "certified": bool(pv.certified), "release_hash": pv.release_hash}
                if pv else None)
        l_d = ({"id": listing.id, "release_hash": listing.release_hash,
                "etsy_listing_id": listing.etsy_listing_id} if listing else None)

    every = _jobs(db, CHAIN, slug)

    def by_job(action, job_type):
        """The newest audit row of `action` written by a job of `job_type` for this product,
        and that job (a later re-run of the same type that has not finished yet does not
        hide the run that wrote the row)."""
        ids = {j["id"]: j for j in every if j["job_type"] == job_type}
        rows = [a for a in _audits(db, action, slug) if a["job_id"] in ids]
        return (ids[rows[-1]["job_id"]], rows[-1]) if rows else (None, None)

    j, a = by_job("cir.compiled", "cir.compile")
    if j and a and pv_d:
        durable["cir.compile"] = {"identity": f"pattern_versions:{pv_d['id']}",
                                  "job": j["id"], "audit": f"audit_log:{a['id']}"}
    j, a = by_job("gate.certified", "gate.certify")
    if j and a and pv_d and pv_d["certified"]:
        durable["gate.certify"] = {
            "identity": f"pattern_versions:{pv_d['id']}#certified:{pv_d['release_hash']}",
            "job": j["id"], "audit": f"audit_log:{a['id']}",
            "release_hash": pv_d["release_hash"]}
    j, a = by_job("listing.seo_drafted", "listing.seo")
    if j and a and l_d:
        durable["listing.seo"] = {"identity": f"listings:{l_d['id']}", "job": j["id"],
                                  "audit": f"audit_log:{a['id']}",
                                  "release_hash": l_d["release_hash"]}
    consumers: dict = {}
    pub = jobs.get("store.publish")
    if pub:
        gates = [g for g in _audits(db, "store.release_gates", slug) if g["job_id"] == pub["id"]]
        refused = [r for r in _audits(db, "store.publish_refused", slug)
                   if r["job_id"] == pub["id"]]
        published = _audits(db, "store.published")
        if gates and refused:
            g = gates[-1]["detail"]
            rel = pv_d["release_hash"] if pv_d else None
            consumers["store.publish"] = {
                "job": pub["id"], "status": pub["status"],
                # The publish job is keyed to the certified release it was enqueued for
                # (runtime.release.chain_key("publish", slug, version, release, ...)), and the
                # gates it computed name the same slug and version.
                "reads": {"audit": f"audit_log:{gates[-1]['id']}",
                          "slug": g.get("slug"), "version": g.get("version"),
                          "same_version": g.get("version") == version,
                          "idempotency_key": pub["idempotency_key"],
                          "same_release": bool(rel) and f":{rel[:12]}:" in (pub["idempotency_key"]
                                                                      or ""),
                          "listing_same_release": bool(l_d and rel
                                                       and l_d["release_hash"] == rel)},
                "decision": {"refused": "capability not enabled" in pub["last_error"],
                             "reason": refused[-1]["detail"].get("reason"),
                             "release_gates_would_block": g.get("blocks_release")},
                "effect": {"audit": f"audit_log:{refused[-1]['id']}",
                           "action": "store.publish_refused"},
                "result": {"store_published_rows": len(published),
                           "listing": l_d["id"] if l_d else None,
                           "etsy_listing_id": l_d["etsy_listing_id"] if l_d else None}}
    return {"durable": durable, "consumers": consumers}


# ---- phase 2: past-shadow simulated publish ---------------------------------------------

PAST_SHADOW_PATH = ("staging", "limited_production")


# Review 6773190553 #4 (L3 F2): who can clear each failing readiness requirement, by the
# requirement's own `blocked_by`. A requirement with blocked_by "build" is ours, and is the one
# kind a rehearsal must explain rather than merely list.
_CLEARED_BY = {"owner": "owner gate", "integration": "integration (a key or paid service)",
               "tester": "physical evidence (a sample make / tester)", "build": "ours (build)"}


def _digest(value, limit: int = 400):
    import json as _json

    text = _json.dumps(value, default=str, sort_keys=True)
    return value if len(text) <= limit else text[:limit] + "..."


def explain_readiness(db, *, to: str) -> list[dict]:
    """Every requirement the launch assessment at `to` finds outstanding, with who can clear
    it (its own `blocked_by`) and the evidence it gave, so a BLOCKED transition says WHY each
    item fails instead of only naming it. Read-only; unreadable evidence is reported as such."""
    from brambleloop.launch import readiness as R

    a = R.launch_assessment(db, phase=to)
    out = []
    for r in a.readiness.outstanding:
        ev = r.evidence or {}
        out.append({"key": r.key, "blocked_by": r.blocked_by,
                    "cleared_by": _CLEARED_BY.get(r.blocked_by or "", "unclassified"),
                    "why": why_unmet(r.description, ev),
                    "evidence": _digest(ev, 1200)})
    return out


# Review 6776323331 MED-2: the evidence keys a requirement uses to say what is wrong. Explicit
# reasons first, then the keys that NAME a shortfall (`unpriced`, `without`, `not_checked`,
# `listings_short_of_frames`, ...), by the naming convention readiness evidence follows.
_REASON_KEYS = ("why", "reason", "problems", "missing", "unmet", "blocked", "open",
                "knockout_problems", "method_blocked_on", "last_probe_reason", "owner_decision",
                "undetermined", "coverage_gaps", "launch_critical_open", "status", "note")
_SHORTFALL_MARKS = ("un", "not_", "without", "missing", "with_no", "with_only", "blocked",
                    "failing", "short", "rehearsal_failed", "releases_without")


def _present(value) -> bool:
    return value not in (None, "", [], {}, ())


def why_unmet(description: str, evidence: dict) -> str:
    """Why one outstanding requirement is unmet, read from its own evidence; never empty.

    The first present explicit reason key; else every present key whose name marks a
    shortfall; else the requirement's description with a digest of its evidence."""
    for key in _REASON_KEYS:
        if _present(evidence.get(key)):
            return f"{key}: {_digest(evidence[key], 300)}"
    shortfalls = {k: v for k, v in evidence.items()
                  if any(k.startswith(m) or f"_{m}" in k for m in _SHORTFALL_MARKS)
                  and _present(v)}
    if shortfalls:
        return "; ".join(f"{k}: {_digest(v, 160)}" for k, v in sorted(shortfalls.items()))[:500]
    facts = _digest(evidence, 300) if evidence else "no evidence recorded"
    return f"not met: {description[:200]} (evidence: {facts})"


def record_owner_phase(rec: Recorder, db, *, authorization: str = REHEARSAL_OPS_TOKEN,
                       readiness_verdict=None) -> dict:
    """W4-FMEND: record the owner's phase transition shadow -> staging -> limited_production
    in the rehearsal's scratch database, through the path the runtime uses.

    `store.publish` runs under `protected_phase`: the more restrictive of the worker's phase,
    the environment and the owner's *recorded*, sealed transition (`core.phase.effective`).
    Setting only BRAMBLELOOP_PHASE therefore left the simulated past-shadow publish refused as
    SHADOW whatever else held. The fix does not touch that rule. It runs:

    * the real `launch.readiness` job (writes `launch.assessed` and, per listed release, the
      `launch.rollback_rehearsed` rows the transition must cite);
    * `core.phase.record_transition` (the function behind POST /api/owner/phase/transition)
      under the rehearsal's fixture ops credential, citing those rows, one step at a time.

    record_transition still checks the credential, the cited evidence (passing from
    limited_production up) and the launch readiness verdict evaluated now. Any refusal is
    recorded as BLOCKED with its reason and the phase stays where it is. Nothing is forced, and
    `readiness_verdict` is None (the live verdict) in every rehearsal run; tests use it only to
    reach the success path.
    """
    from brambleloop.core import phase as phase_mod
    from brambleloop.core.models import Phase
    from brambleloop.runtime import pipeline, release  # noqa: F401 - registers launch.readiness

    expected = ("owner transition shadow -> staging -> limited_production recorded via "
                "core.phase.record_transition, citing launch.readiness evidence")
    job = _run_job(db, "orchestrator", "launch.readiness", {}, Phase.SHADOW)
    assessed = _audits(db, "launch.assessed")
    rehearsed = _audits(db, "launch.rollback_rehearsed")
    refs = {}
    if assessed:
        refs["readiness"] = str(assessed[-1]["id"])
    if rehearsed:
        refs["rollback"] = str(rehearsed[-1]["id"])
    proof = {"launch.readiness_job": job,
             "launch.assessed": {"id": assessed[-1]["id"],
                                 "ready": assessed[-1]["detail"].get("ready"),
                                 "blocked_on_owner": assessed[-1]["detail"].get(
                                     "blocked_on_owner"),
                                 "blocked_on_integration": assessed[-1]["detail"].get(
                                     "blocked_on_integration")} if assessed else None,
             "launch.rollback_rehearsed": [{"id": a["id"], "artifact": a["artifact"],
                                            "ok": a["detail"].get("ok")}
                                           for a in rehearsed[-8:]],
             "evidence_refs": refs}
    recorded = []
    try:
        for to in PAST_SHADOW_PATH:
            t = phase_mod.record_transition(
                db, authorization=authorization, to=to,
                reason="shadow rehearsal: simulated owner phase decision (F-848), scratch DB",
                evidence_refs=refs, readiness_verdict=readiness_verdict)
            recorded.append({"to": to, "transition_id": t["transition_id"],
                             "effective_now": t["effective_now"]})
    except Exception as e:  # noqa: BLE001 - a refused transition is the blocker, recorded
        why = f"{type(e).__name__}: {str(e)[:700]}"
        proof["transitions_recorded"] = recorded
        proof["phase_effective"] = phase_mod.effective(db, record_incident=False)
        try:
            proof["readiness_explained"] = explain_readiness(
                db, to=PAST_SHADOW_PATH[len(recorded)])
        except Exception as exc:  # noqa: BLE001 - the explanation never changes the verdict
            proof["readiness_explained"] = {"unreadable": f"{type(exc).__name__}: {exc}"[:300]}
        rec.step("owner_phase_transition", BLOCKED, expected=expected,
                 observed={"refused_at": PAST_SHADOW_PATH[len(recorded)], "why": why,
                           "recorded": recorded}, proof=proof)
        rec.defect("owner_phase_transition_refused", "core/phase.py::record_transition", why)
        return {"ok": False, "why": why, "recorded": recorded}
    proof["transitions_recorded"] = recorded
    proof["phase_effective"] = phase_mod.effective(db, record_incident=False)
    ok = proof["phase_effective"] == "limited_production"
    rec.step("owner_phase_transition", PASS if ok else BLOCKED, expected=expected,
             observed={"recorded": recorded, "phase_effective": proof["phase_effective"]},
             proof=proof)
    if not ok:
        rec.defect("owner_phase_transition_refused", "core/phase.py::effective",
                   f"transitions recorded but effective phase is {proof['phase_effective']!r}")
    return {"ok": ok, "recorded": recorded}


def run_past_shadow(rec: Recorder, db, state: dict) -> dict:
    from sqlalchemy import select

    sys.path.insert(0, str(ROOT))
    from tests.fake_etsy import FakeEtsy

    from brambleloop.core.models import Job, Listing, Phase
    from brambleloop.integrations import etsy as etsy_mod
    from brambleloop.ops import publication_authority as pa
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker

    slug, version, release = state["slug"], state["version"], state.get("release")
    out = {"draft_listing_id": None}
    if not release or not state.get("publish_inputs"):
        rec.step("owner_phase_transition", SKIPPED, expected="owner transition recorded",
                 observed="no certified release reached store.publish in shadow")
        rec.step("owner_publication_grant", SKIPPED, expected="sealed grant recorded",
                 observed="no certified release reached store.publish in shadow")
        rec.step("store.publish[past-shadow]", SKIPPED, expected="one draft on fake Etsy",
                 observed="no certified release reached store.publish in shadow")
        return out
    env_keys = {"BRAMBLELOOP_PHASE": "limited_production",
                "BRAMBLELOOP_OPS_TOKEN": REHEARSAL_OPS_TOKEN,
                "BRAMBLELOOP_PUBLISH_AUTHORISED": "1"}
    # WS4-0 (cert 20261112T090404Z-20841): owner grants are Ed25519-signed only inside the
    # owner's Command Center request. The simulated owner gets its own throwaway key pair for
    # this phase -- the same treatment as REHEARSAL_OPS_TOKEN -- and is never handed the
    # deployment's signing key; saved_env below restores whatever was set before.
    from brambleloop.core import owner_grant_keys as _rehearsal_ogk
    env_keys.update(_rehearsal_ogk.generate_keypair())
    saved_env = {k: os.environ.get(k) for k in
                 list(env_keys) + ["ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "ETSY_SHOP_ID",
                                   "ETSY_SHARED_SECRET", "ETSY_KEYSTRING",
                                   "ETSY_REFRESH_TOKEN"]}
    saved_base = etsy_mod.EtsyClient.BASE
    log: list = []
    sim_tree, sim_craft = simulated_taxonomy()
    # Review 6775786220 F1: the simulated schema names "Craft type" as a required property,
    # and the draft is created first with the property written afterwards -- the flow the
    # production publish handler implements. The fake's default reading (every create
    # refused) would make this PASS branch unreachable by construction, whatever the release.
    with FakeEtsy(taxonomy_nodes=sim_tree, required_property=sim_craft,
                  create_refuses_required_property=False) as fake:
        restore = _guard_narrowed(fake.port, log)
        try:
            os.environ.update(env_keys)
            for k in ("ETSY_KEYSTRING", "ETSY_REFRESH_TOKEN"):
                os.environ.pop(k, None)
            os.environ.update({"ETSY_API_KEY": fake.keystring, "ETSY_ACCESS_TOKEN":
                               "111.live-token", "ETSY_SHOP_ID": fake.shop_id,
                               "ETSY_SHARED_SECRET": fake.shared_secret})
            # The production client is pointed at the local fake for this simulated phase only.
            etsy_mod.EtsyClient.BASE = fake.base
            # Review L3 item 2: the category the grant needs, read from the simulated Etsy.
            record_simulated_taxonomy(rec, db, state, fake_base=fake.base)
            # W4-FMEND: the owner's recorded phase, through record_transition (never forced).
            record_owner_phase(rec, db)
            grant = None
            try:
                content = pa.snapshot(db, slug, version, release)
                # The simulated owner's review, inside an explicitly labelled owner request
                # (the rehearsal plays the owner here; production enters it only from the
                # Command Center route after session, CSRF/nonce and step-up).
                with _rehearsal_ogk.owner_request("shadow-rehearsal-simulated-owner"):
                    grant = pa.approve(db, authorization=REHEARSAL_OPS_TOKEN, slug=slug,
                                       version=version, release=release,
                                       expected_digest=pa.digest(content),
                                       reason="shadow rehearsal: simulated owner review (F-848)")
                rec.step("owner_publication_grant", PASS,
                         expected="sealed, content-bound grant recorded via approve()",
                         observed={"approval_id": grant["approval_id"],
                                   "expires_at": grant["expires_at"]},
                         proof={"audit_log": [_trim(a["detail"], 500) for a in
                                              _audits(db, pa.APPROVED, slug)]})
            except Exception as e:  # noqa: BLE001 - recorded, not hidden
                rec.step("owner_publication_grant", BLOCKED,
                         expected="sealed, content-bound grant recorded via approve()",
                         observed=f"{type(e).__name__}: {str(e)[:500]}")
                rec.defect("grant_snapshot_refused", "ops/publication_authority.snapshot",
                           f"{type(e).__name__}: {e}")
            inputs = dict(state["publish_inputs"])
            inputs.pop("as_of", None)
            if grant:
                inputs["owner_publication_approval_id"] = grant["approval_id"]
            job = JobQueue(db).enqueue("store_operator", "store.publish", inputs, priority=0,
                                       idempotency_key=f"rehearsal:past-shadow:{slug}:{time.time_ns()}")
            w = Worker(db, "rehearsal-limited", phase=Phase.LIMITED_PRODUCTION,
                       job_types=["store.publish"], lease_seconds=900)
            for _ in range(20):
                with db.session() as s:
                    if s.get(Job, job.id).status.value not in ("pending", "running"):
                        break
                if not w.run_once():
                    break
            with db.session() as s:
                j = s.get(Job, job.id)
                status, err = j.status.value, (j.last_error or "")[:900]
                listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                         Listing.version == version))
                etsy_id = listing.etsy_listing_id if listing else None
            refusals = [a for a in _audits(db, "store.publish_refused", slug)
                        if a["job_id"] == job.id]
            published = [a for a in _audits(db, "store.published") if a["job_id"] == job.id]
            created = [r for r in fake.requests if r.get("operation") == "createDraftListing"]
            drafts = {k: {"state": v.get("state"), "title": v.get("title")}
                      for k, v in fake.listings.items()}
            ok = bool(etsy_id) and len(fake.listings) == 1 and status == "done"
            outcome = PASS if ok else (BLOCKED if status in ("dead", "failed") or refusals
                                       else FAILED)
            rec.step("store.publish[past-shadow]", outcome,
                     expected="exactly one draft created on fake Etsy under the owner grant",
                     observed={"job": job.id, "status": status, "last_error": err,
                               "fake_listings": drafts, "create_requests": len(created)},
                     proof={"listings.etsy_listing_id": etsy_id,
                            "store.publish_refused": [_trim(a["detail"], 1500)
                                                      for a in refusals],
                            "store.published": [_trim(a["detail"], 600) for a in published],
                            "store.execution_revalidated": [
                                _trim(a["detail"], 600) for a in
                                _audits(db, "store.execution_revalidated")
                                if a["job_id"] == job.id]})
            if not ok:
                why = err or json.dumps([a["detail"] for a in refusals], default=str)[:900]
                key = ("search_certificate_never_pass"
                       if "search" in why.lower() and "certificate" in why.lower()
                       else "past_shadow_publish_blocked")
                rec.defect(key, "runtime/pipeline.py::handle_store_publish", why)
            out["draft_listing_id"] = etsy_id
            rec.step("network[past-shadow]", PASS,
                     expected="only the fake Etsy loopback port was reachable",
                     observed={"refused_attempts": len(log),
                               "fake_requests": len(fake.requests)},
                     proof={"refused": log[:25],
                            "fake_operations": [r.get("operation") for r in
                                                    fake.requests][:40]})
        finally:
            restore()
            etsy_mod.EtsyClient.BASE = saved_base
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return out


# ---- phase 3: orders, support, ledger ------------------------------------------------------


def _run_job(db, agent, job_type, inputs, phase):
    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0,
                               idempotency_key=f"rehearsal:{job_type}:{time.time_ns()}")
    w = Worker(db, f"rehearsal-{job_type}", phase=phase, job_types=[job_type],
               lease_seconds=900)
    deadline = time.time() + RUN_JOB_PATIENCE_S
    while True:
        for _ in range(10):
            if not w.run_once():
                break
        with db.session() as s:
            j = s.get(Job, job.id)
            out = {"id": j.id, "status": j.status.value,
                   "last_error": (j.last_error or "")[:600]}
            if j.status.value != "pending" or time.time() >= deadline:
                break
        # Production mode only: after the booted server has shared the database file, a
        # fresh job has intermittently been left unclaimed by an in-process worker
        # (e532a4d under load, 9958d72, 44f1b36). Retry briefly instead of recording an
        # untried step; if it is still pending, the evidence carries why (below).
        time.sleep(2.0)
    if out["status"] == "pending":
        from datetime import datetime, timezone

        with db.session() as s:
            j = s.get(Job, job.id)
            out["unclaimed"] = {
                "run_after": str(j.run_after), "now": datetime.now(timezone.utc).isoformat(),
                "attempts": j.attempts, "lease_expires_at": str(j.lease_expires_at),
                "leased_by": getattr(j, "leased_by", None),
                "waited_s": RUN_JOB_PATIENCE_S}
    return out


def run_commerce(rec: Recorder, db, state: dict, draft_id) -> None:
    from sqlalchemy import select

    from brambleloop.commerce import orders_ingest
    from brambleloop.core.models import (AuditLog, LedgerEntry, OAuthCredential, Order,
                                         OrderVersion, Phase, SupportCase)
    from brambleloop.runtime import pipeline  # noqa: F401

    slug, version = state["slug"], state["version"]
    listing_id = str(draft_id) if draft_id else "rehearsal-unpublished-listing"
    now = _utc()
    receipt = {"receipt_id": 9100001, "buyer_user_id": 9200001,
               "buyer_email": "never@stored.example", "name": "Never Stored",
               "status": "paid", "is_paid": True, "is_shipped": False, "refunds": [],
               "create_timestamp": int((now - timedelta(hours=1)).timestamp()),
               "update_timestamp": int((now - timedelta(hours=1)).timestamp()),
               "transactions": [{"transaction_id": 91000010, "listing_id": listing_id,
                                 "quantity": 1, "price": {"amount": 1299, "divisor": 100,
                                                          "currency_code": "CAD"}}]}

    class FakeFeed:
        calls = 0

        def receipts(self, *, since):
            FakeFeed.calls += 1
            return [receipt]

    with db.session() as s:
        # Simulated owner OAuth grant with the receipts scope and a recorded working probe:
        # the two rows the receipts gate reads. Labelled; never a real credential.
        s.add(AuditLog(actor="rehearsal", action="etsy.probe",
                       detail={"ok": True, "simulated": "shadow rehearsal fixture"}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="rehearsal-sealed",
                              token_fingerprint="rehearsal",
                              scopes="listings_r listings_w shops_r transactions_r"))
    log: list = []
    restore = _guard_narrowed(None, log)
    orders_ingest.reader_factory = lambda _db: FakeFeed()
    try:
        j = _run_job(db, "cfo", "commerce.orders_ingest", {}, Phase.LIMITED_PRODUCTION)
    finally:
        orders_ingest.reader_factory = None
        restore()
    with db.session() as s:
        orders = [{"external_ref": o.external_ref, "price_cad": o.price_cad,
                   "revenue_cad": o.revenue_cad, "source": o.source}
                  for o in s.scalars(select(Order))]
        versions = [{"product_slug": v.product_slug, "version": v.version}
                    for v in s.scalars(select(OrderVersion))]
        ledger = [{"category": e.category, "gross_cad": e.gross_cad, "fees_cad": e.fees_cad,
                   "evidence_ref": e.evidence_ref} for e in s.scalars(select(LedgerEntry))]
    ingested = _audits(db, "commerce.orders_ingested")
    # Exactly once: in production mode the scheduler's own ingest job may also read the same
    # fixture feed (it is the same seam); a second read must add nothing.
    ok = j["status"] == "done" and len(orders) == 1 and FakeFeed.calls >= 1 and \
        sum(1 for e in ledger if e["category"] == "sale") == 1
    rec.step("orders.ingest", PASS if ok else FAILED,
             expected="one fake receipt becomes one order, a version mapping and a ledger "
                      "sale entry (fixture feed via reader_factory; never Etsy)",
             observed={"job": j, "orders": len(orders), "feed_calls": FakeFeed.calls,
                       "receipt_listing_id": listing_id,
                       "version_mapped": any(v["product_slug"] == slug for v in versions)},
             proof={"orders": orders, "order_versions": versions,
                    "commerce.orders_ingested": [_trim(a["detail"], 900) for a in ingested]})
    if ok and not any(v["product_slug"] == slug for v in versions):
        rec.defect("order_version_unmapped", "commerce/orders_ingest.py",
                   f"the receipt's listing {listing_id} did not map to {slug}@{version}"
                   + ("" if draft_id else " (no draft listing id existed to sell)"))

    from brambleloop.support.department import CustomerExperience

    case_id = CustomerExperience(db).intake(
        customer_ref="rehearsal-buyer-9200001",
        message="Hi, in row 3 of the border I end with one stitch fewer than the count. "
                "What should the stitch count be?", product_slug=slug, version=version,
        source="rehearsal")
    t = _run_job(db, "support", "support.triage", {}, Phase.SHADOW)
    r_jobs = _jobs(db, ("support.reply",))
    worker_out = None
    if r_jobs:
        from brambleloop.core.models import Phase as _P
        from brambleloop.runtime.worker import Worker

        w = Worker(db, "rehearsal-support", phase=_P.SHADOW, job_types=["support.reply"],
                   lease_seconds=900)
        for _ in range(10):
            if not w.run_once():
                break
        worker_out = _jobs(db, ("support.reply",))
    with db.session() as s:
        case = s.get(SupportCase, case_id)
        c_proof = {"id": case.id, "specialist": case.specialist, "answer_len": len(case.answer or ""),
                   "sent": case.sent, "escalated": case.escalated, "version": case.version,
                   "detail_keys": sorted((case.detail or {}).keys())}
    ok = t["status"] == "done" and c_proof["answer_len"] > 0 and c_proof["sent"] is False
    rec.step("support.case", PASS if ok else (BLOCKED if t["status"] != "done" else FAILED),
             expected="case taken in, triaged, a reply drafted from the sold version, "
                      "nothing sent",
             observed={"triage_job": t, "reply_jobs": worker_out}, proof={"support_cases": c_proof})

    f = _run_job(db, "cfo", "finance.reconcile", {}, Phase.SHADOW)
    sale = [e for e in ledger if e["category"] == "sale"]
    ok = bool(sale) and f["status"] == "done"
    rec.step("ledger", PASS if ok else (BLOCKED if sale else FAILED),
             expected="the sale is in the ledger with its evidence ref and finance.reconcile "
                      "runs over it",
             observed={"sale_entries": len(sale), "reconcile_job": f},
             proof={"ledger": ledger,
                    "finance.reconciled": [_trim(a["detail"], 600)
                                           for a in _audits(db, "finance.reconciled")]})


# ---- driver --------------------------------------------------------------------------------


def record_upstream(rec: Recorder, cand, cir) -> None:
    """W4-C07 (F-848): the two stages before the pattern, through the real code paths.

    * **opportunity** -- the radar seed this product was promoted on
      (`launch0.radar_concept_for`, else its own slug) in `radar.opportunity.POOL`, and whether
      today's `select_portfolio` still selects it. Found is PASS (selection is reported, not
      required: Launch-0's scope is an owner decision already made); no seed is BLOCKED.
    * **design** -- `launch0.product_truth` on the candidate: every design gate (title, assembly,
      fabric and motif promises backed by the CIR, every variant compiling). Any gate false is
      BLOCKED with the gates named; the CIR fingerprint is the design's identity.
    """
    from brambleloop.products import launch0
    from brambleloop.radar.opportunity import POOL, select_portfolio

    key = launch0.radar_concept_for(cir.slug) or cand.slug
    seed = next((p for p in POOL if p.slug in (key, cand.slug, cir.slug)), None)
    if seed is None:
        rec.step("opportunity", BLOCKED, expected="the product's radar opportunity is on record",
                 observed=f"no radar seed for {key!r}", proof={"key": key})
    else:
        try:
            selected = seed.slug in {c.seed.slug for c in select_portfolio().selected}
        except Exception as e:  # noqa: BLE001 - unreadable selection is UNKNOWN, recorded
            selected = f"UNKNOWN ({type(e).__name__})"
        rec.step("opportunity", PASS, expected="the product's radar opportunity is on record",
                 observed=f"seed {seed.slug} ({seed.category}); selected today: {selected}",
                 proof={"seed": seed.slug, "selected_today": selected})
    truth = launch0.product_truth(cand)
    failed = sorted(k for k, v in (truth.get("gates") or {}).items() if not v)
    rec.step("design", PASS if truth.get("passes_gates") else BLOCKED,
             expected="every design gate passes on the candidate's CIR",
             observed=("all design gates pass" if truth.get("passes_gates") else
                       f"failed gates: {failed}"),
             proof={"cir_fingerprint": cir.fingerprint, "failed_gates": failed})


def rehearse(product: str = LAUNCH0_DEFAULT, *, fast: bool = False,
             out: Path | None = None) -> dict:
    """Run the rehearsal in a scratch directory that is removed afterwards.

    The evidence has always said "fresh sqlite file (discarded after the run)"; until W3-HYG
    (2026-10-06) it was not -- `mkdtemp` left the database, the rendered assets and the server
    log behind on every run. The directory is now removed on success and on exception.
    """
    tmp = Path(tempfile.mkdtemp(prefix="shadow_rehearsal_"))
    try:
        return _rehearse(tmp, product, fast=fast, out=out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _rehearse(tmp: Path, product: str, *, fast: bool, out: Path | None) -> dict:
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(ROOT))
    started = _utc()
    head = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    artifacts = str(tmp / "artifacts")
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = artifacts
    os.environ["BRAMBLELOOP_PHASE"] = "shadow"
    for k in list(os.environ):
        if k.startswith(("ETSY", "BRAMBLELOOP_PUBLISH_AUTHORISED", "BRAMBLELOOP_OPS_TOKEN")):
            os.environ.pop(k)
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.products import launch0

    if product not in launch0.LAUNCH0_SLUGS:
        raise SystemExit(f"{product!r} is not a Launch-0 product: {launch0.LAUNCH0_SLUGS}")
    cand = launch0.candidate(product)
    cir = launch0.cir_for(cand.variants[0].build)
    url = f"sqlite:///{tmp}/company.sqlite"
    db = Database(url)
    db.create_all()
    if fast:
        Registry(db).seed_defaults()
    rec = Recorder()
    state: dict = {"slug": cir.slug, "version": cir.version}
    edges: dict = {"durable": {}, "consumers": {}}
    try:
        record_upstream(rec, cand, cir)
        ctx = run_shadow_chain(rec, db, url, tmp, artifacts, cir, fast=fast)
        state = record_chain(rec, db, cir, ctx)
        record_listing_package(rec, db, state)
        seed_catalogue(rec, db, cir.slug)
        edges = record_edges(db, cir.slug, cir.version)
        pub = run_past_shadow(rec, db, state)
        # Review 6775786220 F3: judged on the STORED verdict after the last listing.seo (the
        # simulated taxonomy re-runs it), not on the one read before that re-run -- a stale
        # REFUSED would misstate to freeze_candidate what blocks.
        if state.get("search_profile"):
            final = _stored_search_verdict(db, cir.slug, cir.version)
            if final != "PASS":
                rec.defect("search_certificate_not_pass", "listing_search_profiles.verdict",
                           f"stored search verdict after the last listing.seo is {final!r} "
                           f"(after the shadow chain it was "
                           f"{state['search_profile'].get('verdict')!r}); store.publish's "
                           f"search_certificate gate requires PASS")
        run_commerce(rec, db, state, pub.get("draft_listing_id"))
    except Exception as e:  # noqa: BLE001 - the rehearsal records its own breakage
        rec.step("rehearsal", FAILED, expected="every step runs to an outcome",
                 observed=f"{type(e).__name__}: {e}",
                 proof={"traceback": traceback.format_exc()[-3000:]})
    finished = _utc()
    required = ["opportunity", "design", "boot", "cir.compile", "gate.certify", "assets.build", "listing.seo",
                "listing.package", "catalogue[production-shaped]", "store.publish[shadow]",
                "taxonomy[simulated]", "owner_phase_transition", "owner_publication_grant",
                "store.publish[past-shadow]", "orders.ingest", "support.case", "ledger"]
    by = {s["step"]: s["outcome"] for s in rec.steps}
    evidence = {
        "kind": "shadow_rehearsal", "requirement": "F-848",
        "head": head, "head_short": head[:7], "tree_dirty": dirty,
        "product": cir.slug, "version": cir.version, "mode": "fast" if fast else "production",
        "started_at": started.isoformat(), "finished_at": finished.isoformat(),
        "seconds": round((finished - started).total_seconds(), 1),
        "database": "fresh sqlite file (discarded after the run)",
        "simulations": [
            "past-shadow phase is simulated in-process (BRAMBLELOOP_PHASE=limited_production); "
            "production stays SHADOW",
            "Etsy is tests/fake_etsy.py on loopback; EtsyClient.BASE pointed at it for the "
            "simulated phase only",
            "owner phase transition shadow -> staging -> limited_production attempted through "
            "core.phase.record_transition under a fixture ops credential, citing the real "
            "launch.readiness evidence and the live readiness verdict (refused = BLOCKED)",
            "owner publication grant recorded through approve() under a fixture ops credential",
            SIMULATED_TAXONOMY_LABEL + "; read by the real listing.taxonomy_refresh from "
            "tests/fake_etsy.py on loopback",
            "catalogue: every other Launch-0 release driven through the real chain handlers "
            "in-process in SHADOW on the rehearsal database (production data is not read)",
            "receipt feed is a fixture via commerce.orders_ingest.reader_factory; receipts gate "
            "rows (etsy.probe ok, transactions_r scope) seeded as a simulated owner grant",
            "support case taken in through CustomerExperience.intake (no messaging integration "
            "exists)"],
        "steps": rec.steps,
        "chain_edges": edges,
        "required": required,
        "outcomes": by,
        "blocking_defects": rec.defects,
        "complete": all(by.get(k) in GOOD for k in required),
        "not_complete_because": [k for k in required if by.get(k) not in GOOD],
    }
    target = out
    if target is None:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        target = EVIDENCE_DIR / (f"shadow_rehearsal_{head[:7]}_"
                                 f"{started.strftime('%Y-%m-%dT%H%MZ')}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=1, default=str, ensure_ascii=False) + "\n")
    evidence["path"] = str(target)
    return evidence


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--product", default=LAUNCH0_DEFAULT)
    p.add_argument("--fast", action="store_true",
                   help="drive the handlers with an in-process Worker instead of booting the "
                        "production start command")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    ev = rehearse(a.product, fast=a.fast, out=a.out)
    print(json.dumps({"path": ev["path"], "complete": ev["complete"],
                      "outcomes": ev["outcomes"],
                      "blocking_defects": [d["key"] for d in ev["blocking_defects"]]}, indent=1))
    return 0 if ev["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
