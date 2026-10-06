#!/usr/bin/env python3
"""F-848: one recorded shadow rehearsal of a Launch-0 product, end to end, on a fresh database.

What it does, in order, and what each step's outcome means:

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
    """The chain reached store.publish and it settled, or it stopped before it."""
    if _publish_settled(db, slug):
        return True
    rows = _jobs(db, CHAIN, slug)
    return bool(rows) and all(r["status"] in ("done", "dead", "cancelled") for r in rows) \
        and not any(r["status"] in ("pending", "running", "failed") for r in rows)


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


# ---- phase 2: past-shadow simulated publish ---------------------------------------------


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
        rec.step("owner_publication_grant", SKIPPED, expected="sealed grant recorded",
                 observed="no certified release reached store.publish in shadow")
        rec.step("store.publish[past-shadow]", SKIPPED, expected="one draft on fake Etsy",
                 observed="no certified release reached store.publish in shadow")
        return out
    env_keys = {"BRAMBLELOOP_PHASE": "limited_production",
                "BRAMBLELOOP_OPS_TOKEN": REHEARSAL_OPS_TOKEN,
                "BRAMBLELOOP_PUBLISH_AUTHORISED": "1"}
    saved_env = {k: os.environ.get(k) for k in
                 list(env_keys) + ["ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "ETSY_SHOP_ID",
                                   "ETSY_SHARED_SECRET", "ETSY_KEYSTRING",
                                   "ETSY_REFRESH_TOKEN"]}
    saved_base = etsy_mod.EtsyClient.BASE
    log: list = []
    with FakeEtsy() as fake:
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
            grant = None
            try:
                content = pa.snapshot(db, slug, version, release)
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
    for _ in range(10):
        if not w.run_once():
            break
    with db.session() as s:
        j = s.get(Job, job.id)
        return {"id": j.id, "status": j.status.value, "last_error": (j.last_error or "")[:600]}


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
    try:
        ctx = run_shadow_chain(rec, db, url, tmp, artifacts, cir, fast=fast)
        state = record_chain(rec, db, cir, ctx)
        if state.get("search_profile") and state["search_profile"].get("verdict") != "PASS":
            rec.defect("search_certificate_not_pass", "listing_search_profiles.verdict",
                       f"stored search verdict after listing.seo is "
                       f"{state['search_profile'].get('verdict')!r}; store.publish's "
                       f"search_certificate gate requires PASS")
        pub = run_past_shadow(rec, db, state)
        run_commerce(rec, db, state, pub.get("draft_listing_id"))
    except Exception as e:  # noqa: BLE001 - the rehearsal records its own breakage
        rec.step("rehearsal", FAILED, expected="every step runs to an outcome",
                 observed=f"{type(e).__name__}: {e}",
                 proof={"traceback": traceback.format_exc()[-3000:]})
    finished = _utc()
    required = ["boot", "cir.compile", "gate.certify", "assets.build", "listing.seo",
                "store.publish[shadow]", "owner_publication_grant",
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
            "owner publication grant recorded through approve() under a fixture ops credential",
            "receipt feed is a fixture via commerce.orders_ingest.reader_factory; receipts gate "
            "rows (etsy.probe ok, transactions_r scope) seeded as a simulated owner grant",
            "support case taken in through CustomerExperience.intake (no messaging integration "
            "exists)"],
        "steps": rec.steps,
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
