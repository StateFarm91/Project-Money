"""ENG-FIRSTLIST: the owner's grant reaches the job that uses it, end to end, on a fake Etsy.

Found tracing the first real Etsy draft on the Batch 9 code (base 6e47d9bb):

* G1: a valid owner publication grant caused nothing. The only store.publish is the one
  `launch.plan` enqueues; in SHADOW it is refused and dead-lettered, and `store.publish` is a
  DELIBERATE_REFUSAL_TYPE that `requeue_dead` never re-drives. No route enqueued another.
* G2: no code put `owner_activation_approval_id` on a store.activate job, so
  `activation_authority.validate` refused every activation, and no inbox card offered
  `activation.approve` at all.
* G3: the Approvals card sent `expected_digest: "<from publication.preview>"` verbatim, so the
  server refused every approval made from that button.
* G4: `/api/readback/evidence` could not say which release is a first-draft candidate.

The flow below uses the real certified release fixture (tests/test_search_hero_publish.py:
certify -> assets.build -> listing.seo through the real handlers) and the rehearsal's own
helpers. Held, exactly as test_rehearsal_past_shadow_success holds them: the readiness
verdict (a fixture shop is honestly not ready), creative parity (#75), the search-grid
tournament (#126) and the Launch-0 scope gate. Everything else is real: the phase transition,
the sealed grants, the Command Center action dispatch, store.publish, the read-back,
store.activate, the listing-fee reservation and the fake Etsy's HTTP contract.

Run: cd brambleloop && python3 tests/test_first_listing_doors.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import json
import os
import re
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT.parent / "ops"))

import test_search_hero_publish as SH  # noqa: E402  (sets its env and loopback-only sockets)
import test_rehearsal_past_shadow_success as RP  # noqa: E402
import ready_release_fixture as RF  # noqa: E402  (a READY release, real sale pipeline)

_spec = importlib.util.spec_from_file_location("shadow_rehearsal_fl",
                                               ROOT / "scripts" / "shadow_rehearsal.py")
reh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reh)

from sqlalchemy import select  # noqa: E402

from brambleloop.app.command_center import approvals  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, Listing, Phase  # noqa: E402
from brambleloop.ops import owner_execution as oe  # noqa: E402

STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"


def _run_all(db, job_types, worker_phase=Phase.LIMITED_PRODUCTION, limit=20):
    from brambleloop.runtime.worker import Worker

    w = Worker(db, "first-listing-test", phase=worker_phase, job_types=list(job_types),
               lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def _job(db, job_id):
    with db.session() as s:
        j = s.get(Job, job_id)
        return {"status": j.status.value, "inputs": dict(j.inputs or {}),
                "outputs": dict(j.outputs or {}), "error": (j.last_error or "")[:600]}


def _audits(db, action):
    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _fees(db):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return [{"kind": c.kind, "amount_cad": float(c.amount_cad), "agent": c.agent}
                for c in s.scalars(select(CostEntry).where(
                    CostEntry.kind == "etsy_listing_fee"))]


def _exec(db, action, **body):
    return approvals.execute(db, action, {"reason": "ENG-FIRSTLIST test owner", **body},
                             actor="owner-test")


def test_the_grant_reaches_a_draft_and_then_a_public_listing_through_the_owner_doors():
    from tests.fake_etsy import FakeEtsy

    from brambleloop.core import owner_grant_keys as ogk
    from brambleloop.integrations import etsy as etsy_mod
    from brambleloop.ops import activation_authority as aa
    from brambleloop.ops import production_evidence as pe
    from brambleloop.ops import publication_authority as pa

    # A release READY for sale (D-OWNER-SALE-PIPELINE): the seven-frame certified gallery, both
    # premium PDFs certified, the package READY -- built through the real sale chain on fake
    # image / vision providers only (tests/ready_release_fixture.py, READY-FIXTURE.md).
    path, version, rh = RF.ready_chain("doors")
    copy = path + ".doors.sqlite"
    shutil.copyfile(path, copy)
    db = Database(f"sqlite:///{copy}")
    slug = SH.SLUG
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                       artifact=f"{slug}@{version}", detail={"ok": True}))
    env_keys = {"BRAMBLELOOP_OPS_TOKEN": reh.REHEARSAL_OPS_TOKEN,
                "BRAMBLELOOP_PUBLISH_AUTHORISED": "1", **ogk.generate_keypair()}
    saved_env = {k: os.environ.get(k) for k in
                 list(env_keys) + ["BRAMBLELOOP_PHASE", "ETSY_API_KEY", "ETSY_ACCESS_TOKEN",
                                   "ETSY_SHOP_ID", "ETSY_SHARED_SECRET", "ETSY_KEYSTRING",
                                   "ETSY_REFRESH_TOKEN"]}
    saved_base = etsy_mod.EtsyClient.BASE
    restore_gates = RP._held_gates()
    sim_tree, sim_craft = reh.simulated_taxonomy()
    log: list = []
    try:
        with FakeEtsy(taxonomy_nodes=sim_tree, required_property=sim_craft,
                      create_refuses_required_property=False) as fake:
            restore_net = reh._guard_narrowed(fake.port, log)
            try:
                os.environ.update(env_keys)
                os.environ["BRAMBLELOOP_PHASE"] = "shadow"
                for k in ("ETSY_KEYSTRING", "ETSY_REFRESH_TOKEN"):
                    os.environ.pop(k, None)
                os.environ.update({"ETSY_API_KEY": fake.keystring,
                                   "ETSY_ACCESS_TOKEN": "111.live-token",
                                   "ETSY_SHOP_ID": fake.shop_id,
                                   "ETSY_SHARED_SECRET": fake.shared_secret})
                etsy_mod.EtsyClient.BASE = fake.base
                rec = reh.Recorder()
                state = {"slug": slug, "version": version, "release": rh}
                # The simulated seller taxonomy and the release's listing.seo were recorded by
                # the READY fixture in production order, before the gallery
                # (ready_release_fixture._simulated_taxonomy, the same
                # reh.record_simulated_taxonomy step); read back here. Re-running listing.seo
                # after a certified generated gallery is refused (READY-FIXTURE.md, F1).
                RF.assert_taxonomy_recorded(db, slug, version)

                # G4: the readback names this release and what still blocks it.
                rb = pe.first_listing_readiness(db, now=pe.datetime.now(pe.timezone.utc))
                mine = [r for r in rb["releases"] if r["release"] == f"{slug}@{version}"]
                assert rb["readable"] and len(mine) == 1, rb
                assert set(mine[0]["publication_sections"]) == set(pa.GATED_SECTIONS), mine
                assert mine[0]["on_etsy"] is False, mine
                assert mine[0]["release_hash_prefix"] == rh[:12], mine

                # The owner's publication grant, recorded in SHADOW (approve never needs a
                # phase; it binds content).
                content = pa.snapshot(db, slug, version, rh)
                with ogk.owner_request("first-listing-test-owner"):
                    grant = pa.approve(db, authorization=reh.REHEARSAL_OPS_TOKEN, slug=slug,
                                       version=version, release=rh,
                                       expected_digest=pa.digest(content),
                                       reason="ENG-FIRSTLIST test: simulated owner review")
                gid = grant["approval_id"]

                # G1 guard: in SHADOW the door refuses and queues nothing, because a
                # store.publish refused there is never re-driven and its key stays taken.
                try:
                    _exec(db, "publication.execute", slug=slug, version=version, release=rh,
                          approval_id=gid)
                    raise AssertionError("publication.execute queued a job in SHADOW")
                except approvals.ActionRefused as exc:
                    assert "phase" in str(exc), exc
                with db.session() as s:
                    assert not s.scalars(select(Job).where(
                        Job.job_type == "store.publish",
                        Job.idempotency_key.like("owner-publish:%"))).first()
                # A reason is required, as for approve.
                try:
                    approvals.execute(db, "publication.execute",
                                      {"slug": slug, "version": version, "release": rh,
                                       "approval_id": gid}, actor="owner-test")
                    raise AssertionError("no reason accepted")
                except approvals.ActionRefused as exc:
                    assert "reason" in str(exc), exc

                # The owner's phase, recorded through record_transition (readiness held).
                os.environ["BRAMBLELOOP_PHASE"] = "limited_production"

                def run_job(db_, agent, job_type, inputs, phase):
                    if job_type == "launch.readiness":
                        with db_.session() as s:
                            s.add(AuditLog(actor="orchestrator", action="launch.assessed",
                                           artifact="launch", detail={"ready": True}))
                        return {"id": None, "status": "not run (test)", "last_error": ""}
                    return real_run_job(db_, agent, job_type, inputs, phase)
                real_run_job = reh._run_job
                reh._run_job = run_job
                try:
                    reh.record_owner_phase(rec, db, readiness_verdict=RP._ready)
                finally:
                    reh._run_job = real_run_job
                from brambleloop.core import phase as phase_mod
                assert phase_mod.effective(db, record_incident=False) == "limited_production"

                # The kill-switch still denies through the door.
                os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "0"
                try:
                    _exec(db, "publication.execute", slug=slug, version=version, release=rh,
                          approval_id=gid)
                    raise AssertionError("queued with the kill-switch off")
                except approvals.ActionRefused as exc:
                    assert "BRAMBLELOOP_PUBLISH_AUTHORISED" in str(exc) or "kill" in str(exc), exc
                os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"

                # The inbox card now offers the execute button with the live grant.
                cards = {c["card_id"]: c for c in approvals.inbox(db).get("cards") or []
                         if isinstance(c, dict) and c.get("card_id")}
                pub_card = cards.get(f"publication:{slug}@{version}")
                if pub_card is not None and pub_card.get("executable"):
                    acts = {a["action"]: a for a in pub_card["actions"]}
                    assert acts["publication.execute"]["params"]["approval_id"] == gid, acts

                # G1: the door queues exactly one store.publish carrying the grant id.
                out = _exec(db, "publication.execute", slug=slug, version=version,
                            release=rh, approval_id=gid)["result"]
                assert out["queued"] is True and out["approval_id"] == gid, out
                again = _exec(db, "publication.execute", slug=slug, version=version,
                              release=rh, approval_id=gid)["result"]
                assert again["queued"] is False and again["job_id"] == out["job_id"], again
                j = _job(db, out["job_id"])
                assert j["inputs"]["owner_publication_approval_id"] == gid, j

                _run_all(db, ["store.publish"])
                j = _job(db, out["job_id"])
                assert j["status"] == "done" and j["outputs"].get("published") is True, j
                assert j["outputs"].get("read_back_verified") is True, j
                assert len(fake.listings) == 1, fake.listings
                listing_id = j["outputs"]["etsy_listing_id"]
                remote = fake.listings[int(listing_id)] if int(listing_id) in fake.listings \
                    else fake.listings[str(listing_id)]
                assert remote.get("state") == "draft", remote
                with db.session() as s:
                    row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                         Listing.version == version))
                    assert row.state == "published" and str(row.etsy_listing_id) == \
                        str(listing_id), (row.state, row.etsy_listing_id)
                assert _audits(db, "store.published"), "no store.published row"
                assert _fees(db) == [], "a draft must reserve no listing fee"

                # The publication door is closed once the draft exists (grant covers draft
                # creation only), and the readback says it is on Etsy.
                try:
                    _exec(db, "publication.execute", slug=slug, version=version, release=rh,
                          approval_id=gid)
                    raise AssertionError("a second draft door opened")
                except approvals.ActionRefused:
                    pass
                rb = pe.first_listing_readiness(db, now=pe.datetime.now(pe.timezone.utc))
                mine = [r for r in rb["releases"] if r["release"] == f"{slug}@{version}"][0]
                assert mine["on_etsy"] is True and mine["draft_candidate"] is False, mine

                # G2 (before the fix): the automatic store.activate carries no approval id
                # and refuses. It still reads the draft back (store.activation_verified).
                _run_all(db, ["store.activate"])
                with db.session() as s:
                    auto = s.scalars(select(Job).where(Job.job_type == "store.activate")
                                     .order_by(Job.id)).all()
                    assert len(auto) == 1, [a.inputs for a in auto]
                    assert "owner_activation_approval_id" not in (auto[0].inputs or {})
                    assert (auto[0].outputs or {}).get("activated") is False, auto[0].outputs
                # It still reads the draft back: every field, image and file matched, and the
                # one reason is the release gate a buyer-facing listing needs.
                verified = _audits(db, "store.activation_verified")[-1]
                assert verified["fields"]["verified"] and verified["files"]["verified"], verified
                assert [r.split(":")[0] for r in verified["reasons"]] == \
                    ["release gate"] and "SAMPLE_PHOTO_REQUIRED" in verified["reasons"][0], \
                    verified["reasons"]

                # The activation card exists and offers preview/approve.
                cards = {c["card_id"]: c for c in approvals.inbox(db).get("cards") or []
                         if isinstance(c, dict) and c.get("card_id")}
                act_card = cards[f"activation:{slug}@{version}"]
                assert [a["action"] for a in act_card["actions"]] == \
                    ["activation.preview", "activation.approve"], act_card["actions"]

                # The owner's activation grant, then the door.
                prev = _exec(db, "activation.preview", slug=slug, version=version,
                             release=rh)["result"]
                with ogk.owner_request("first-listing-test-owner"):
                    agrant = aa.approve(db, authorization=reh.REHEARSAL_OPS_TOKEN, slug=slug,
                                        version=version, release=rh,
                                        expected_digest=prev["digest"],
                                        reason="ENG-FIRSTLIST test: simulated owner review")
                aid = agrant["approval_id"]
                cards = {c["card_id"]: c for c in approvals.inbox(db).get("cards") or []
                         if isinstance(c, dict) and c.get("card_id")}
                acts = {a["action"]: a for a in cards[f"activation:{slug}@{version}"]["actions"]}
                assert acts["activation.execute"]["params"]["approval_id"] == aid, acts

                out = _exec(db, "activation.execute", slug=slug, version=version, release=rh,
                            approval_id=aid)["result"]
                assert out["queued"] is True and str(out["etsy_listing_id"]) == str(listing_id)
                again = _exec(db, "activation.execute", slug=slug, version=version,
                              release=rh, approval_id=aid)["result"]
                assert again["queued"] is False and again["job_id"] == out["job_id"], again
                # The door does not weaken the gate: with no sample photograph on file the
                # owner-granted activation is still refused, nothing is activated and no fee is
                # reserved.
                _run_all(db, ["store.activate"])
                j = _job(db, out["job_id"])
                assert j["status"] == "done" and j["outputs"].get("activated") is False, j
                assert any("SAMPLE_PHOTO_REQUIRED" in r for r in j["outputs"]["reasons"]), j
                assert remote.get("state") == "draft" and _fees(db) == [], remote
                # One job per grant: the refused grant does not queue again.
                again = _exec(db, "activation.execute", slug=slug, version=version,
                              release=rh, approval_id=aid)["result"]
                assert again["queued"] is False and again["job_status"] == "done", again

                # Held from here, as the other gates are (sample_photo has its own tests in
                # test_w4_launchfix): an owner-attested unedited sample photo through the
                # physical intake is the owner's physical action, not something to forge.
                from brambleloop.publish import sample_photo
                real_requirement = sample_photo.requirement
                sample_photo.requirement = lambda *a, **k: {
                    "satisfied": False, "reasons": [], "qualifying": [], "rejected": [],
                    "first_frame": None, "held": "SAMPLE_PHOTO_REQUIRED has its own tests"}
                try:
                    prev = _exec(db, "activation.preview", slug=slug, version=version,
                                 release=rh)["result"]
                    with ogk.owner_request("first-listing-test-owner"):
                        aid = aa.approve(db, authorization=reh.REHEARSAL_OPS_TOKEN,
                                         slug=slug, version=version, release=rh,
                                         expected_digest=prev["digest"],
                                         reason="ENG-FIRSTLIST test: second review")[
                                             "approval_id"]
                    out = _exec(db, "activation.execute", slug=slug, version=version,
                                release=rh, approval_id=aid)["result"]
                    assert out["queued"] is True, out
                    _run_all(db, ["store.activate"])
                finally:
                    sample_photo.requirement = real_requirement
                j = _job(db, out["job_id"])
                assert j["status"] == "done" and j["outputs"].get("activated") is True, j
                assert j["outputs"].get("state_on_etsy") == "active", j
                assert remote.get("state") == "active", remote
                with db.session() as s:
                    row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                         Listing.version == version))
                    assert row.state == "active", row.state
                assert _audits(db, "store.activated"), "no store.activated row"
                fees = _fees(db)
                assert len(fees) == 1 and fees[0]["kind"] == "etsy_listing_fee", fees
                assert 0.27 <= fees[0]["amount_cad"] <= 0.29, fees  # US$0.20 at 1.4154
                used = _audits(db, "store.activation_authority_used")
                assert used and used[-1]["approval_id"] == aid, used
                # Once active, the activation door refuses.
                try:
                    _exec(db, "activation.execute", slug=slug, version=version, release=rh,
                          approval_id=aid)
                    raise AssertionError("activation door open on an active listing")
                except approvals.ActionRefused as exc:
                    assert "active" in str(exc), exc
                assert not log, log[:5]      # nothing but the fake's loopback port was reached
            finally:
                restore_net()
    finally:
        restore_gates()
        etsy_mod.EtsyClient.BASE = saved_base
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        db.engine.dispose()


def test_the_doors_are_step_up_owner_actions_that_never_sign():
    for a in ("publication.execute", "activation.execute"):
        assert approvals.ACTIONS[a][0] is True, a
    api = (ROOT / "src/brambleloop/app/command_center/api.py").read_text()
    seg = api[api.index("OWNER_GRANT_SIGNING_ACTIONS = ("):]
    seg = seg[:seg.index(")")]
    assert "execute" not in seg, "an execute door must never enter the signing context"
    src = (ROOT / "src/brambleloop/ops/owner_execution.py").read_text()
    assert "owner_grant_keys" not in src and "UrllibTransport" not in src
    assert "record_transition" not in src


def test_the_approve_button_sends_the_previewed_digest_not_the_placeholder():
    js = (STATIC / "js/views/approvals.js").read_text()
    funcs = {}
    for name in ("previewKey", "isPreviewVerb", "fillPreviewParams"):
        m = re.search(r"export function " + name + r"\(.*?\n\}\n", js, re.S)
        assert m, f"{name} is missing"
        funcs[name] = m.group(0).replace("export function", "function")
    assert "fillPreviewParams(a.params, digests, previewParams) === null" in js
    assert "params: fillPreviewParams(a.params, digests, previewParams)" in js
    # Assign 7012067586 L2: the entry is cleared when a preview starts.
    assert "delete digests[key];" in js
    import re as _re
    _v = _re.search(r'const VERSION = "cc-shell-v(\d+)";', (STATIC / "sw.js").read_text())
    assert _v and int(_v.group(1)) >= 33, _v  # digests keyed by action+params (v33)
    node = shutil.which("node")
    if node is None:
        print("   (node not installed: the pure-function run is skipped)")
        return
    prog = "".join(funcs.values()) + """
const ph = {slug: "s", version: "1", release: "r", expected_digest: "<from publication.preview>"};
const pp = {"publication.preview": {slug: "s", version: "1", release: "r"}};
const k = previewKey("publication.preview", pp["publication.preview"]);
const kOther = previewKey("publication.preview", {slug: "other", version: "1", release: "r"});
const out = {
  none: fillPreviewParams(ph, {}, pp),
  wrong: fillPreviewParams(ph, {[previewKey("activation.preview", {})]: "d1"}, pp),
  other_params: fillPreviewParams(ph, {[kOther]: "zzz"}, pp),
  name_only: fillPreviewParams(ph, {"publication.preview": "abc123"}, pp),
  no_preview_on_card: fillPreviewParams(ph, {[k]: "abc123"}, {}),
  got: fillPreviewParams(ph, {[k]: "abc123"}, pp),
  key_order: previewKey("x.preview", {b: 1, a: 2}) === previewKey("x.preview", {a: 2, b: 1}),
  plain: fillPreviewParams({slug: "s", approval_id: 7}, {}, {}),
  untouched: ph.expected_digest,
  verbs: ["preview", "review_preview", "approve", "revoke"].map(isPreviewVerb),
};
console.log(JSON.stringify(out));
"""
    r = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["none"] is None and out["wrong"] is None, out
    assert out["other_params"] is None and out["name_only"] is None, out      # L2
    assert out["no_preview_on_card"] is None, out
    assert out["got"] == {"slug": "s", "version": "1", "release": "r",
                          "expected_digest": "abc123"}, out
    assert out["key_order"] is True, out
    assert out["plain"] == {"slug": "s", "approval_id": 7}, out
    assert out["untouched"] == "<from publication.preview>", out
    assert out["verbs"] == [True, True, False, False], out                     # L3
    # L3: the review_preview digest field is captured.
    assert "res.review_digest" in js


def test_the_policy_review_card_names_a_preview_its_digest_comes_from():
    """Assign 7012067586 L3: the policy.review card's placeholder names a preview action that
    is on the same card and is a preview verb, and that preview returns `review_digest`."""
    import inspect

    src = inspect.getsource(approvals)
    assert '"expected_digest": "<from policy.review_preview>"' in src
    assert '{"action": "policy.review_preview"' in src
    assert 'shown["review_digest"]' in src

def test_the_readback_cli_judges_the_new_section_as_advisory():
    import readback

    from brambleloop.ops import production_evidence as pe

    assert "first_listing_readiness" in pe.SECTIONS
    items = {s for _i, s, _k in readback.EVIDENCE_ITEMS}
    assert "first_listing_readiness" in items
    j = readback._judge_section
    assert j("first_listing_readiness", None, None)[0] == readback.WARN
    assert j("first_listing_readiness", {"readable": True, "draft_candidates": [],
                                         "certified_with_listing": 2}, None)[0] == readback.WARN
    assert j("first_listing_readiness", {"readable": True,
                                         "draft_candidates": ["a@1.0.0"]}, None)[0] \
        == readback.PASS


def test_a_handler_refused_publication_is_not_re_pressed_with_the_same_grant():
    """Assign 7012067586 L4: the handler refused the store.publish this grant queued (kill
    switch, gate, credential: it dead-letters, and store.publish is never re-driven). A second
    press with the SAME grant returns that refused job, says a new grant is needed, and queues
    nothing; a NEW grant queues a fresh job."""
    import tempfile
    from unittest.mock import patch

    from brambleloop.core.models import JobStatus
    from brambleloop.ops import owner_execution as oe
    from brambleloop.ops import publication_authority as pa

    tmp = tempfile.mkdtemp(prefix="flr_l4_")
    db = Database(f"sqlite:///{os.path.join(tmp, 'l4.db')}")
    db.create_all()
    slug, version, rel = "l4-coaster", "1.0.0", "f" * 64
    grants = {"current": 501}
    with patch.object(pa, "resolve", lambda db_, **k: (None, grants["current"])), \
            patch.object(oe, "_phase_refusal", lambda db_: None), \
            patch.object(oe, "_kill_switch_refusal", lambda: None):
        first = oe.queue_publication(db, slug=slug, version=version, release=rel,
                                     approval_id=501)
        assert first["queued"] is True, first
        with db.session() as s:                    # what the handler leaves on a refusal
            j = s.get(Job, first["job_id"])
            j.status = JobStatus.DEAD
            j.last_error = "store.publish refused: BRAMBLELOOP_PUBLISH_AUTHORISED is off"
        again = oe.queue_publication(db, slug=slug, version=version, release=rel,
                                     approval_id=501)
        assert again["queued"] is False and again["job_id"] == first["job_id"], again
        assert again["job_status"] == "dead" and "new grant" in again["why"], again
        with db.session() as s:
            jobs = list(s.scalars(select(Job).where(Job.job_type == oe.PUBLISH_JOB)))
        assert len(jobs) == 1, [j.id for j in jobs]
        grants["current"] = 502                     # the owner re-approves: a new grant
        fresh = oe.queue_publication(db, slug=slug, version=version, release=rel,
                                     approval_id=502)
        assert fresh["queued"] is True and fresh["job_id"] != first["job_id"], fresh
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
