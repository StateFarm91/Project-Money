"""W4-CLOSE5: criterion-level tests for the Final Master rows this lane closes.

Each test names the row and quotes the clause it asserts. They test code that is already in
the deployed tree (b931d17), so they are also run, unchanged, on a clean worktree of that commit
(research/final_build/w4/evidence_CLOSE5/deployed_tree_tests_b931d17.json).

  F-152  Scratch Non-Authority   "Recovery/audit evidence cannot exist only in ephemeral scratch."
  F-299  Controlled Phase Change "Shadow -> staging -> live publication/ads is explicit
                                  owner-approved transition with rollback."  (the ads half)
  F-718  No Chat as Source of Truth  "No critical state may exist only in a Claude, GPT or
                                  Fable conversation." (runtime never reads dev-lane state)

Local, deterministic; no network, no provider, no spend.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

TOKEN = "close5-owner-token-0123456789abcdef0123"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase, SpendLimit  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402


def _db(name: str = "close5.sqlite") -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/{name}")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class _Env:
    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# =============================================================================================
# F-152 Scratch Non-Authority: "Recovery/audit evidence cannot exist only in ephemeral scratch."
# =============================================================================================

def _scratch_sites() -> set[str]:
    """Every function in src/ that creates a scratch directory: core.workspace.work_dir,
    tempfile.TemporaryDirectory or tempfile.mkdtemp. As "relative/module.py::function"."""
    out = set()
    for p in sorted(SRC.rglob("*.py")):
        text = p.read_text()
        if not any(k in text for k in ("work_dir(", "TemporaryDirectory", "mkdtemp")):
            continue
        tree = ast.parse(text)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name == "work_dir":
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = getattr(f, "attr", None) or getattr(f, "id", None)
                    if name in ("work_dir", "TemporaryDirectory", "mkdtemp"):
                        out.add(f"{p.relative_to(SRC).as_posix()}::{fn.name}")
    return out


# Every scratch site, and where whatever evidence it produces is made durable. Kinds:
#   durable   the named function writes the record to the database (audit row, session row,
#             continuity archive) -- `markers` must appear in that function's source;
#   caller    the site returns its result to the named function, which records it durably;
#   copy      the scratch holds a copy of evidence that already lives in the database;
#   cli       operator proof tooling: scratch holds only a throwaway database, and the evidence
#             is written to an operator-chosen output path outside the scratch directory;
#   reading   a measurement recomputed on each read and never stored, so a lost scratch dir
#             loses nothing that was evidence.
# A new scratch site fails `test_f152_every_scratch_site_is_classified` until it is added here.
SCRATCH = {
    "app/main.py::api_continuity_export": ("copy", "app/main.py::api_continuity_export",
                                           ("continuity.export(", ".audit(")),
    "autonomy/proof.py::main": ("cli", "autonomy/proof.py::main", ("--out",)),
    "laura/executive/proof.py::main": ("cli", "laura/executive/proof.py::main", ("--out",)),
    "finance/accounting/shadow_dataset.py::runtime_proof": (
        "cli", "finance/accounting/shadow_dataset.py::runtime_proof", ("out_dir",)),
    "brand/moat.py::measure_recognisability": ("reading", "brand/moat.py::evidence", ()),
    "core/offsite.py::archive": ("durable", "core/offsite.py::archive", ("AuditLog(",)),
    "gateway/image_bench.py::run": ("caller", "runtime/release.py::handle_image_benchmark",
                                    ("ctx.audit(",)),
    "gateway/images.py::reference_probe": ("durable", "gateway/images.py::reference_probe",
                                           ("audit",)),
    "gateway/images.py::probe": ("durable", "gateway/images.py::probe", ("AuditLog(",)),
    "publish/model_photography.py::make": ("caller",
                                           "runtime/release.py::handle_model_photography",
                                           ("ctx.audit(",)),
    "publish/model_photography.py::sequence": (
        "caller", "runtime/release.py::handle_model_photography", ("ctx.audit(",)),
    "publish/motif_fidelity.py::check": ("caller", "publish/owned_photography.py::make",
                                         ("motif_fidelity.check(",)),
    "publish/owned_photography.py::make": ("caller",
                                           "runtime/release.py::handle_owned_photography",
                                           ("ctx.audit(",)),
    "runtime/release.py::handle_continuity": ("durable", "runtime/release.py::handle_continuity",
                                              ("ctx.audit(", "continuity.retain(")),
    "runtime/release.py::handle_model_photography": (
        "durable", "runtime/release.py::handle_model_photography", ("ctx.audit(",)),
    "runtime/release.py::handle_seasonal_cycle_proof": (
        "durable", "runtime/release.py::handle_seasonal_cycle_proof", ("ctx.audit(",)),
    "runtime/release.py::handle_grid_tournament": (
        "caller", "runtime/release.py::_grid_tournament_in", ("ctx.audit(",)),
    "runtime/release.py::handle_offsite_archive": (
        "durable", "runtime/release.py::handle_offsite_archive", ("ctx.audit(",)),
    "runtime/release.py::handle_model_tournament": (
        "durable", "runtime/release.py::handle_model_tournament", ("ctx.audit(",)),
    "runtime/release.py::handle_portrait_repair": (
        "durable", "runtime/release.py::handle_portrait_repair", ("ctx.audit(",)),
    "runtime/release.py::handle_provider_trial": (
        "durable", "runtime/release.py::handle_provider_trial", ("ctx.audit(",)),
    "runtime/release.py::handle_owned_photography": (
        "durable", "runtime/release.py::handle_owned_photography", ("ctx.audit(",)),
    "runtime/release.py::_owned_photography_rung": (
        "durable", "runtime/release.py::_owned_photography_rung", ("audit",)),
    "runtime/release.py::handle_model_reference_pack": (
        "durable", "runtime/release.py::handle_model_reference_pack", ("ctx.audit(",)),
    "teardown/proof_run.py::_run": ("reading", "teardown/readiness.py::check", ()),
    "teardown/reader.py::self_test": ("reading", "teardown/readiness.py::check", ()),
    "visual/exported_review.py::review": ("durable", "visual/exported_review.py::review",
                                          ("AuditLog(",)),
    "visual/hero_review.py::review_disclosed_hero": (
        "durable", "visual/hero_review.py::review_disclosed_hero", ("AuditLog(",)),
    "visual/inspect.py::identify_at_grid": ("caller", "visual/hero_review.py::review_disclosed_hero",
                                            ("identify_at_grid(",)),
    # INTEG4 (VISNEXT merged with CLOSE5): the generator's scratch holds the render only until
    # its bytes are returned; image_production._generate keeps them (`store_bytes`, durable
    # artifact row) and records the candidate row.
    "creative/flux3_generator.py::_scratch": ("caller", "visual/image_production.py::_generate",
                                              ("gen.generate(", "store_bytes(",
                                               "record_candidate(")),
    # The experiment's scratch holds the provider download; run_job keeps the image as a
    # durable artifact and the handler writes the audit row (the run row is written by
    # controlled._update throughout).
    "experiments/controlled.py::run_job": ("caller",
                                           "runtime/release.py::handle_controlled_experiment",
                                           ("controlled.run_job(", "ctx.audit(")),
    # The fidelity judge's scratch holds copies of the image bytes it was handed, for the
    # provider call; its reading is returned to the gates that record it.
    "visual/fidelity.py::read": ("caller", "visual/fidelity.py::craft_texture",
                                 ("judge.read(",)),
    "visual/milestone_d.py::assess": ("reading", "visual/milestones.py::assess", ()),
    "visual/pbr_scene.py::render": ("reading", "visual/pbr_scene.py::render", ()),
}


def _function_source(ref: str) -> str:
    rel, fn = ref.split("::")
    text = (SRC / rel).read_text()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{ref} does not exist")


def test_f152_every_scratch_site_is_classified():
    found = _scratch_sites()
    unclassified = sorted(found - set(SCRATCH))
    assert not unclassified, (
        f"scratch directories created with no recorded durable home for their evidence: "
        f"{unclassified}. Add each to SCRATCH with where its evidence is made durable")
    stale = sorted(set(SCRATCH) - found)
    assert not stale, f"SCRATCH names sites that no longer create scratch: {stale}"
    assert len(found) >= 25, found  # the scan is not vacuous


def test_f152_each_classified_home_really_writes_or_hands_over_the_evidence():
    checked = 0
    for site, (kind, home, markers) in SCRATCH.items():
        src = _function_source(home)
        for m in markers:
            assert m in src, f"{site}: {home} lacks {m!r} ({kind})"
        if kind == "durable":
            assert re.search(r"\baudit\w*\(|\.add\(|AuditLog\(|\.retain\(", src), (site, home)
        if kind == "caller":
            callee = site.split("::")[1]
            assert callee in src or any(m in src for m in markers), (site, home)
        if kind == "cli":
            # the proof's output path is resolved before the scratch dir exists, so it is not
            # inside it
            body = _function_source(site)
            out_at = min(body.find(m) for m in markers)
            tmp_at = body.find("TemporaryDirectory")
            assert 0 <= out_at < tmp_at, (site, out_at, tmp_at)
        checked += 1
    assert checked == len(SCRATCH) and checked >= 25


def test_f152_continuity_evidence_outlives_its_scratch_directory():
    """The daily restore proof: when the scratch directory is gone, the proof and the archive
    are still answerable from the database alone."""
    from brambleloop.core import continuity
    from brambleloop.runtime import release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import JobContext, handlers

    db = _db("source.sqlite")
    q = JobQueue(db)
    for i in range(3):
        q.enqueue("orchestrator", "ops.heartbeat", {"n": i}, idempotency_key=f"c5-{i}")
    scratch = tempfile.mkdtemp(prefix="continuity-")
    job = q.enqueue("orchestrator", "ops.continuity", {"work_dir": scratch},
                    idempotency_key="c5-continuity")
    ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)
    handlers.get("ops.continuity")(ctx)
    shutil.rmtree(scratch)
    assert not Path(scratch).exists()

    with db.session() as s:
        proof = s.scalar(select(AuditLog).where(AuditLog.action == "continuity.verified"))
        retained_row = s.scalar(select(AuditLog).where(AuditLog.action == "continuity.retained"))
    assert proof is not None and proof.detail.get("work_dir_is_durable") is False
    assert retained_row is not None
    held = continuity.retained(db)
    assert held, "no archive survived in the database"
    # the archive restores from the database bytes, with the scratch directory gone
    out = Path(tempfile.mkdtemp())
    target = Database(f"sqlite:///{out}/recovered.sqlite")
    counts = continuity.restore_retained(db, held[0]["archive_id"], target, out / "recovery")
    assert counts["jobs"] >= 4 and counts["agents"] >= 1, counts


def test_f152_offsite_evidence_outlives_its_scratch_directory():
    from brambleloop.core import offsite
    from brambleloop.core.models import Product

    env = {offsite.ENDPOINT_VAR: "https://s3.us-west-004.backblazeb2.com",
           offsite.BUCKET_VAR: "brambleloop-archive",
           offsite.KEY_ID_VAR: "004aabbccddeeff0000000001",
           offsite.SECRET_VAR: "K004xxxxxxxxxxxxxxxxxxxxxxxxxxx",
           offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to be stretched into a key",
           offsite.REGION_VAR: "us-west-004"}
    objects: dict[str, bytes] = {}

    def put(key, payload, *, env=None):
        objects[key] = payload
        return {"key": key, "bytes": len(payload), "bucket": "test", "host": "test"}

    def get(key, *, env=None):
        return objects[key]

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(Product(slug="c5-throw", title="C5 throw"))
    scratch = tempfile.mkdtemp(prefix="offsite-")
    record = offsite.archive(db, env=env, transport=(put, get), work_dir=scratch)
    assert record["ok"] is True, record.get("reason")
    shutil.rmtree(scratch)
    # the proof is the database row and the remote object, not anything in scratch
    assert offsite.usable(db) is True
    last = offsite.last_archive(db)
    assert last["ok"] and last["key"] in objects
    assert scratch not in repr(last), "the recorded evidence points into scratch"
    assert offsite.state(db, env=env)["usable"] is True


# =============================================================================================
# F-299 Controlled Phase Change -- the ads half: "Shadow -> staging -> live publication/ads is
# explicit owner-approved transition with rollback." Publication is already asserted by
# tests/test_fb4_launch.py::test_store_publish_refuses_when_env_says_production_but_nothing_is_recorded.
# =============================================================================================

def _run_campaign(db, phase: Phase) -> Job:
    from brambleloop.runtime import growth_ops  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    job = JobQueue(db).enqueue("ads", "ads.campaign",
                               {"slug": "c5-throw", "daily_budget_cad": 3.0, "max_cac_cad": 4.0},
                               idempotency_key=f"c5-ads-{datetime.now().timestamp()}")
    assert Worker(db, "t", phase=phase, job_types=["ads.campaign"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def test_f299_ad_spend_follows_the_recorded_owner_transition_not_the_environment():
    from brambleloop.core import phase as P

    from phase_fixture import record_phase_path

    db = _db()
    with db.session() as s:
        s.add(SpendLimit(scope="ads", daily_cap_cad=5.0, lifetime_cap_cad=100.0))
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PHASE="production"):
        # 1. the environment alone says production; nothing is recorded: spend runs as shadow
        planned = _run_campaign(db, Phase.PRODUCTION)
        assert planned.status == JobStatus.DONE, planned.last_error
        assert planned.outputs["phase"] == "shadow" and planned.outputs["spent_cad"] == 0.0
        assert "production" in planned.outputs["refused_by"]
        # 2. the owner records shadow -> staging -> limited_production -> production, one step
        #    at a time with readiness and rollback evidence: the phase gate now passes, and the
        #    job stops only because no ad integration exists to spend through
        record_phase_path(db, TOKEN, "production")
        assert P.effective(db) == "production"
        passed = _run_campaign(db, Phase.PRODUCTION)
        assert passed.status in (JobStatus.DEAD, JobStatus.FAILED), passed.status
        assert "no ad integration" in (passed.last_error or ""), passed.last_error
        # 3. the owner's rollback (down, reason only) stops spend at the next job
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="owner rollback drill")
        rolled = _run_campaign(db, Phase.PRODUCTION)
        assert rolled.status == JobStatus.DONE and rolled.outputs["phase"] == "shadow"
    with db.session() as s:
        steps = [(r.detail["from"], r.detail["to"]) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == P.TRANSITION).order_by(AuditLog.id))]
        limit = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
    assert steps == [("shadow", "staging"), ("staging", "limited_production"),
                     ("limited_production", "production"), ("production", "shadow")], steps
    assert limit.spent_today_cad == 0.0 and limit.spent_lifetime_cad == 0.0


def test_f299_the_staging_step_cannot_be_skipped_and_needs_the_owner():
    from brambleloop.core import opsauth
    from brambleloop.core import phase as P

    from phase_fixture import synthetic_evidence, synthetic_readiness

    db = _db()
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PHASE="production"):
        refs = synthetic_evidence(db)
        for to in ("limited_production", "production"):
            try:
                P.record_transition(db, authorization=TOKEN, to=to, reason="skip staging",
                                    evidence_refs=refs, env={P.ENV_VAR: to},
                                    readiness_verdict=synthetic_readiness)
            except ValueError:
                pass
            else:
                raise AssertionError(f"shadow -> {to} skipped staging")
        try:
            P.record_transition(db, authorization="not-the-owner", to="staging", reason="x",
                                evidence_refs=refs, env={P.ENV_VAR: "staging"},
                                readiness_verdict=synthetic_readiness)
        except opsauth.OpsAuthRefused:
            pass
        else:
            raise AssertionError("a transition was recorded without the owner credential")
        assert P.resolve(db)["phase"] == "shadow"


# =============================================================================================
# F-718 No Chat as Source of Truth: the company runtime never reads development-lane state
# (ops/JOBS.json, the machine-local job registry of build sessions); its own state is the
# database and the repository, and the canonical-model approval is a repository object.
# =============================================================================================

def test_f718_the_runtime_reads_no_dev_lane_or_session_state():
    """No runtime module imports the dev-lane registry (ops/registry.py), opens its file
    (ops/JOBS.json) or reads its variable. A note *naming* it (swarm/metrics.py says merge
    delay is measured there, outside the deployed tree) is not a read."""
    read_markers = ("JOBS.json", "BRAMBLELOOP_JOB_REGISTRY", "claude_session",
                    "conversation_log", ".claude/")
    hits = []
    scanned = 0
    for p in sorted(SRC.rglob("*.py")):
        text = p.read_text()
        tree = ast.parse(text)
        scanned += 1
        docs = _docstring_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs \
                    and any(m in node.value for m in read_markers):
                hits.append(f"{p.relative_to(SRC)}: {node.value[:60]!r}")
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [a.name for a in node.names]
                if mod == "ops.registry" or (mod == "ops" and "registry" in names) or \
                        (node.level == 0 and mod.startswith("ops.")):
                    hits.append(f"{p.relative_to(SRC)}: from {mod} import {names}")
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "ops" or a.name.startswith("ops."):
                        hits.append(f"{p.relative_to(SRC)}: import {a.name}")
    assert scanned > 300, scanned
    assert not hits, hits


def _docstring_ids(tree) -> set[int]:
    """ids of the docstring constants (module, class, function) in one parsed file."""
    out = set()
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant):
            out.add(id(body[0].value))
    return out


def test_f718_the_owner_approval_is_a_repository_object_matching_the_database():
    from brambleloop.visual import approval_record

    rec = approval_record.load()
    assert rec["source"]["action"] == "model.frozen" and rec["source"]["audit_id"] == 5693
    pinned = {k: rec["freeze"][k] for k in approval_record.PINNED}
    db = _db()
    assert approval_record.compare(db)["state"] == "NO_ROW"  # never MATCH by default
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="model.frozen",
                       detail={"freeze": dict(pinned)}))
    assert approval_record.compare(db)["state"] == "MATCH"
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="model.frozen",
                       detail={"freeze": {**pinned, "candidate_fingerprint": "0" * 16}}))
    got = approval_record.compare(db)
    assert got["state"] == "MISMATCH" and got["mismatched_fields"] == ["candidate_fingerprint"]


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 8, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
