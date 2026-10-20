"""W4-CREDHEALTH: provider credential health, owner cards, key secrecy, experiment robustness.

Railway is the only secret store; every check here runs on a MOCK transport with stand-in key
strings that the tests then hunt for everywhere they must never appear. No network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_credhealth.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_controlled_experiments as CE  # noqa: E402 - sets up the app, DB, BFL stand-in

from sqlalchemy import select  # noqa: E402

from brambleloop.app.command_center import notifications as N  # noqa: E402
from brambleloop.app.command_center.models import Notification  # noqa: E402
from brambleloop.core.models import AuditLog, Job  # noqa: E402
from brambleloop.experiments import controlled as C  # noqa: E402
from brambleloop.gateway import credentials as CR  # noqa: E402
from brambleloop.gateway import paid_calls as PC  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

DB = CE.DB
BFL_KEY = CE.SECRET
ANT_KEY = "sk-ant-STANDIN-" + uuid.uuid4().hex
ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": BFL_KEY, "ANTHROPIC_API_KEY": ANT_KEY}


class Http:
    """Scripted provider answers, by provider; records every request."""

    def __init__(self, bfl=(200, '{"credits": 500}'), ant=(200, '{"input_tokens": 12}')):
        self.bfl, self.ant, self.calls = bfl, ant, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "body": json.loads(body) if body else None})
        return self.bfl if "bfl.ai" in url else self.ant


def _clear_credential_rows():
    with DB.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == CR.ACTION)):
            s.delete(a)                       # test isolation only; production never deletes
        for n in s.scalars(select(Notification).where(
                Notification.dedupe_key.like("credential:%"))):
            s.delete(n)


def _cred_cards():
    N.refresh(DB)
    with DB.session() as s:
        return [(n.dedupe_key, n.title, n.body, n.resolved_at) for n in s.scalars(
            select(Notification).where(Notification.dedupe_key.like("credential:%"))
            .order_by(Notification.id))]


# ---- classification ---------------------------------------------------------------------

def test_status_classes():
    cases = [((200, "{}"), CR.OK), ((401, "invalid x-api-key"), CR.REJECTED),
             ((403, "Forbidden"), CR.REJECTED),
             ((403, "your key does not have permission to use this model"), CR.PERMISSION),
             ((404, '{"type":"not_found_error","message":"model: x"}'), CR.PERMISSION),
             ((402, ""), CR.INSUFFICIENT_CREDIT),
             ((400, "Your credit balance is too low to access the Anthropic API"),
              CR.INSUFFICIENT_CREDIT),
             ((429, "slow down"), CR.RATE_LIMITED), ((500, ""), CR.OUTAGE),
             ((529, "overloaded"), CR.OUTAGE), ((0, "unreachable: TimeoutError"), CR.OUTAGE),
             ((418, "teapot"), CR.UNKNOWN), ((400, "bad request"), CR.UNKNOWN)]
    assert len(cases) == 13
    for (st, text), want in cases:
        assert CR.classify(st, text) == want, (st, text, CR.classify(st, text))
    assert set(CR.STATUSES) == {"OK", "MISSING", "REJECTED", "INSUFFICIENT_CREDIT",
                                "PERMISSION", "OUTAGE", "RATE_LIMITED", "UNKNOWN"}


def test_bfl_uses_the_free_credits_endpoint_and_reads_the_balance():
    h = Http()
    got = CR.check_bfl(ENV, h)
    assert got["status"] == CR.OK and got["credits"] == 500.0, got
    assert len(h.calls) == 1
    call = h.calls[0]
    assert call["method"] == "GET" and call["url"] == "https://api.bfl.ai/v1/credits"
    assert call["headers"]["x-key"] == BFL_KEY and call["body"] is None
    low = CR.check_bfl(ENV, Http(bfl=(200, '{"credits": 5}')))
    assert low["status"] == CR.INSUFFICIENT_CREDIT and "less than one 2k" in low["why"]
    assert CR.check_bfl({}, Http())["status"] == CR.MISSING
    assert CR.check_bfl(ENV, Http(bfl=(200, "not json")))["status"] == CR.UNKNOWN
    for st, want in ((401, CR.REJECTED), (402, CR.INSUFFICIENT_CREDIT), (429, CR.RATE_LIMITED),
                     (503, CR.OUTAGE), (0, CR.OUTAGE)):
        assert CR.check_bfl(ENV, Http(bfl=(st, "x")))["status"] == want, st


def test_anthropic_uses_count_tokens_with_an_image_block():
    h = Http()
    got = CR.check_anthropic(ENV, h, db=None)
    assert got["status"] == CR.OK and got["image_input"] is True, got
    assert got["credit"]["status"] == CR.UNKNOWN          # credit is not assumed
    call = h.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.anthropic.com/v1/messages/count_tokens"
    assert call["headers"]["x-api-key"] == ANT_KEY
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    kinds = [b["type"] for b in call["body"]["messages"][0]["content"]]
    assert kinds == ["image", "text"] and "max_tokens" not in call["body"]
    assert CR.check_anthropic({}, h)["status"] == CR.MISSING
    perm = CR.check_anthropic(ENV, Http(ant=(403, "permission_error: not enabled")))
    assert perm["status"] == CR.PERMISSION


def test_anthropic_credit_is_read_from_the_last_real_call():
    _clear_credential_rows()
    with DB.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe", artifact="m",
                       detail={"at": "2030-01-01T00:00:00+00:00", "ok": False,
                               "reason": "Your credit balance is too low to access the "
                                         "Anthropic API"}))
    got = CR.check_anthropic(ENV, Http(), db=DB)
    assert got["status"] == CR.INSUFFICIENT_CREDIT, got
    with DB.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe", artifact="m",
                       detail={"at": "2030-01-02T00:00:00+00:00", "ok": True, "reason": ""}))
    got = CR.check_anthropic(ENV, Http(), db=DB)
    assert got["status"] == CR.OK and got["credit"]["status"] == CR.OK, got


# ---- owner cards ------------------------------------------------------------------------

def test_cards_dedupe_alert_owner_states_and_recover():
    _clear_credential_rows()
    CR.check_all(DB, env=ENV, http=Http())
    assert _cred_cards() == []                                     # healthy: nothing
    CR.check_all(DB, env=ENV, http=Http(bfl=(401, "unauthorized")))
    CR.check_all(DB, env=ENV, http=Http(bfl=(401, "unauthorized")))
    cards = _cred_cards()
    open_ = [c for c in cards if c[3] is None]
    assert len(open_) == 1, cards                                   # one card, deduplicated
    key, title, body, _ = open_[0]
    assert key.startswith("credential:bfl:REJECTED:") and "rejected" in title
    assert "Railway → Variables → BRAMBLELOOP_IMAGE_KEY_BFL" in body, body
    assert "delete the old key" in body
    # recovery card, and the REJECTED card resolves
    CR.check_all(DB, env=ENV, http=Http())
    cards = _cred_cards()
    rec = [c for c in cards if ":recovered:" in c[0] and c[3] is None]
    assert len(rec) == 1 and "healthy again" in rec[0][1], cards
    assert all(c[3] is not None for c in cards if ":REJECTED:" in c[0])


def test_outage_alerts_only_after_consecutive_failures():
    _clear_credential_rows()
    CR.check_all(DB, env=ENV, http=Http())
    for i in range(1, CR.ALERT_AFTER_CONSECUTIVE):
        recs = CR.check_all(DB, env=ENV, http=Http(ant=(503, "overloaded")))
        assert recs[1]["consecutive_failures"] == i
        assert [c for c in _cred_cards() if c[3] is None] == [], i     # no spam
    CR.check_all(DB, env=ENV, http=Http(ant=(503, "overloaded")))
    open_ = [c for c in _cred_cards() if c[3] is None]
    assert len(open_) == 1 and open_[0][0] == "credential:anthropic:OUTAGE:streak", open_
    for status, var in (("MISSING", "ANTHROPIC_API_KEY"),
                        ("INSUFFICIENT_CREDIT", None), ("PERMISSION", "ANTHROPIC_API_KEY")):
        text = CR.owner_action("anthropic", status)
        assert text and (var is None or var in text), (status, text)


# ---- the job, the on-demand route and secrecy --------------------------------------------

def test_wiring_cadence_authority_liveness_and_routes():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.app.command_center.api import make_router
    from brambleloop.authority import classes
    from brambleloop.ops import on_demand
    from brambleloop.runtime.pipeline import WORK_KEYS
    from brambleloop.runtime.worker import CADENCES
    from brambleloop.swarm.orchestrate import LIVENESS_JOB_TYPES

    assert ("provider_credentials", "orchestrator", CR.JOB_TYPE, 86400) in CADENCES
    orch = next(a for a in DEFAULT_AGENTS if a["name"] == "orchestrator")
    assert CR.JOB_TYPE in orch["allowed_job_types"]
    assert classes.classify(CR.JOB_TYPE) == classes.ActionClass.OBSERVE
    assert not classes.is_gated(CR.JOB_TYPE)
    assert CR.JOB_TYPE in WORK_KEYS and CR.JOB_TYPE in LIVENESS_JOB_TYPES
    assert on_demand.CHECKS["credentials"].cadences == ("provider_credentials",)
    paths = {r.path for r in make_router(None).routes}
    assert "/api/cc/credentials" in paths
    amap = json.loads((ROOT / "src/brambleloop/autonomy/autonomy_map.json").read_text())
    assert CR.JOB_TYPE in json.dumps(amap)


def test_on_demand_check_runs_the_job_and_no_key_leaks_anywhere():
    _clear_credential_rows()
    leaky = Http(bfl=(401, f'{{"detail": "invalid key {BFL_KEY}"}}'),
                 ant=(401, f"invalid x-api-key {ANT_KEY}"))
    saved_http = CR._http
    os.environ["ANTHROPIC_API_KEY"] = ANT_KEY
    try:
        CR._http = leaky
        anon = CE.TestClient(CE.main.app, base_url="https://testserver",
                             raise_server_exceptions=False)
        assert anon.get("/api/cc/credentials").status_code == 401
        c, csrf = CE.session()
        CE.stepup(c, csrf)
        r = CE.post(c, csrf, "/api/cc/checks/credentials/run")
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["job_type"] == CR.JOB_TYPE
        from brambleloop.runtime import release  # noqa: F401 - registers handlers
        from brambleloop.runtime.worker import Worker

        w = Worker(DB, "cred-test", job_types=[CR.JOB_TYPE])
        assert w.run_once()
        assert len(leaky.calls) == 2
        state = c.get("/api/cc/credentials")
        assert state.status_code == 200
        provs = {p["provider"]: p for p in state.json()["providers"]}
        assert provs["bfl"]["status"] == CR.REJECTED and \
            provs["anthropic"]["status"] == CR.REJECTED
        assert provs["bfl"]["latest"]["trigger"] == "on_demand"
        fp_b, fp_a = CR.fingerprint(BFL_KEY), CR.fingerprint(ANT_KEY)
        assert provs["bfl"]["fingerprint"] == fp_b and provs["anthropic"]["fingerprint"] == fp_a
        N.refresh(DB)
        notes = c.get("/api/cc/notifications").text
        # every surface: logs, audit, job rows, API, notifications
        blobs = {"log": CE.LOG.getvalue(), "api_state": state.text, "api_notes": notes}
        with DB.session() as s:
            blobs["jobs"] = json.dumps([[j.inputs, j.outputs, getattr(j, "last_error", "")]
                                        for j in s.scalars(select(Job))], default=str)
            blobs["audit"] = json.dumps([a.detail for a in s.scalars(select(AuditLog))],
                                        default=str)
            blobs["notifications"] = json.dumps(
                [[n.title, n.body, n.dedupe_key] for n in s.scalars(select(Notification))],
                default=str)
        assert "invalid key [redacted]" in blobs["audit"]          # the evidence, scrubbed
        for name, blob in blobs.items():
            assert BFL_KEY not in blob and ANT_KEY not in blob, f"key leaked in {name}"
        # the fingerprint is the owner view's alone
        for name in ("jobs", "audit", "notifications", "api_notes", "log"):
            for fp in (fp_b, fp_a):
                assert fp["sha256_prefix"] not in blobs[name], f"fingerprint in {name}"
    finally:
        CR._http = saved_http
        os.environ.pop("ANTHROPIC_API_KEY", None)


# ---- experiment robustness -------------------------------------------------------------

def _claimed_run():
    CE._settle_active()
    CE._authorize()
    q = JobQueue(DB)
    out = C.submit(DB, CE.EXP, by="owner:test", stepped_up=True,
                   enqueue=lambda i, k: q.enqueue(C.AGENT, C.JOB_TYPE, i, idempotency_key=k,
                                                  max_attempts=2).id)
    job = q.claim("worker-1", job_types=[C.JOB_TYPE])
    assert job is not None and job.id == out["job_id"]
    with DB.session() as s:
        inputs = dict(s.get(Job, job.id).inputs)
    return out, job, inputs


def test_restart_after_the_image_was_stored_resumes_without_a_second_paid_call():
    out, job, inputs = _claimed_run()
    saved = C._finish

    def die(*a, **k):
        raise KeyboardInterrupt("worker killed after the image was stored")

    t = CE.Transport()
    try:
        C._finish = die
        with t, PC.job_scope(DB, job):
            try:
                C.run_job(DB, inputs, job_id=job.id)
                raise AssertionError("the simulated kill did not happen")
            except KeyboardInterrupt:
                pass
    finally:
        C._finish = saved
    mid = C.get_run(DB, out["run_id"])
    assert mid["status"] == "running" and mid["image_sha256"], mid       # receipts persisted
    assert mid["receipt"] and mid["generation_spent_cad"] > 0
    spent = mid["generation_spent_cad"]
    # a redeploy: the local artifact directory is gone; the durable copy is in the database
    shutil.rmtree(os.environ["BRAMBLELOOP_ARTIFACT_DIR"], ignore_errors=True)
    with t, PC.job_scope(DB, job):
        got = C.run_job(DB, inputs, job_id=job.id)
    assert len(t.posts) == 1, "a resumed run paid again"
    assert got["resumed"] and got["image"] and got["image_sha256"] == mid["image_sha256"]
    run = C.get_run(DB, out["run_id"])
    assert run["status"] == "completed" and run["generation_spent_cad"] == spent
    assert run["verification"].get("summary") in ("UNKNOWN", "FAIL")       # never PASS here
    # a re-run of the completed run does nothing
    again = C.run_job(DB, inputs, job_id=job.id)
    assert again["ran"] is False and "completed" in again["why"]
    CE._settle_active()


def test_restart_during_the_paid_call_is_never_resent():
    out, job, inputs = _claimed_run()

    class Dies(CE.Transport):
        def post(self, *a, **k):
            super().post(*a, **k)
            raise KeyboardInterrupt("worker killed while the provider had the request")

    t = Dies()
    with t, PC.job_scope(DB, job):
        try:
            C.run_job(DB, inputs, job_id=job.id)
            raise AssertionError("the simulated kill did not happen")
        except KeyboardInterrupt:
            pass
    assert len(t.posts) == 1                               # the provider had the request
    assert [r["outcome"] for r in PC.rows(DB, job_id=job.id)] == [PC.UNCERTAIN]
    mid = C.get_run(DB, out["run_id"])
    assert mid["status"] == "running" and not mid["image_sha256"]
    reserved = mid["generation_spent_cad"]
    assert reserved > 0                                    # billing unknown is never zero
    t2 = CE.Transport()
    with t2, PC.job_scope(DB, job):
        got = C.run_job(DB, inputs, job_id=job.id)
    assert t2.posts == [], "a billing-unknown call was resent"
    run = C.get_run(DB, out["run_id"])
    assert run["status"] == "failed" and got["image"] is False, run
    assert run["generation_spent_cad"] == reserved          # counted once, not twice, not 0
    assert "Unresolved" in json.dumps(run["attempt_log"]) or "F-339" in run["why"], run
    CE._settle_active()


def test_restart_without_a_job_scope_settles_billing_unknown():
    out, job, inputs = _claimed_run()
    C._update(DB, out["run_id"], status="running", job_id=job.id, attempts=1,
              generation_spent_cad=0.14)
    t = CE.Transport()
    with t:
        got = C.run_job(DB, inputs, job_id=job.id)
    assert t.posts == [] and got["settled"] == "billing_unknown"
    run = C.get_run(DB, out["run_id"])
    assert run["status"] == "failed" and run["generation_spent_cad"] == 0.14
    # a different job never touches a running run
    out2, job2, inputs2 = _claimed_run()
    C._update(DB, out2["run_id"], status="running", job_id=job2.id)
    assert "running under" in C.run_job(DB, inputs2, job_id=job2.id + 999)["why"]
    # a run whose job dead-lettered is settled by the board
    from brambleloop.core.models import JobStatus

    with DB.session() as s:
        s.get(Job, job2.id).status = JobStatus.DEAD
    assert C.settle_dead(DB) == 1
    assert C.get_run(DB, out2["run_id"])["status"] == "failed"
    CE._settle_active()


def test_the_cc_enqueues_a_reclaimable_job_and_publication_stays_impossible():
    import inspect

    from brambleloop.app.command_center import api

    src = inspect.getsource(api.make_router)
    i = src.index("/experiments/{definition_id}/run")
    assert "max_attempts=2" in src[i:i + 1200]
    CE.test_publication_is_refused_everywhere_for_the_experiment()


def test_the_rotation_doc_and_the_acceptance_runbook_exist():
    doc = (ROOT / "research/final_build/w4/KEY_ROTATION.md").read_text()
    for needle in ("BRAMBLELOOP_IMAGE_KEY_BFL", "ANTHROPIC_API_KEY", "Variables",
                   "fingerprint", "Delete the old key", "Check now"):
        assert needle in doc, needle
    ex = (ROOT / "research/final_build/w4/EXPERIMENTS.md").read_text()
    i = ex.index("Production acceptance runbook")
    for step in ("A.", "B.", "C.", "D.", "E.", "F.", "G.", "2048", "CA$5", "CA$1"):
        assert step in ex[i:], step


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
