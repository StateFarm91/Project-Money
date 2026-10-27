"""W5-INVENTORY: the product inventory state machine, flow health, department activity, the
Command Center Production view and the readback projection.

* every state is derived from seeded records (jobs, PatternVersion, Listing, audits, tests);
* "Ready for publication" is refused whenever any gate is open (each gate opened in turn);
* the physical sample is an attribute: PDF / visual / listing package are reachable without a
  sample, and a product awaiting its sample never counts toward Ready (owner clarification);
* stall and loop detection; the useful vs no-op split (the one judge);
* GET /api/cc/production needs an owner session and writes nothing;
* the readback projection carries no private data.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w5_inventory.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w5_inventory_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'inv.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*_a, **_k):
    raise OSError("network refused by the W5-INVENTORY harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, production  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Job, JobStatus, Listing,  # noqa: E402
                                     OwnerAction, OwnerVeto, PatternVersion, PhysicalTest,
                                     Product)
from brambleloop.ops import flow_health  # noqa: E402
from brambleloop.products import production_inventory as pi  # noqa: E402

OPS = "i" * 40
PASS = "owner passphrase for the W5-INVENTORY harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
NOW = datetime.now(timezone.utc)
T_JOB = NOW - timedelta(hours=3)
T_AUDIT = NOW - timedelta(hours=1)
PDF = {"US": {"sha256": "a" * 64}, "UK": {"sha256": "b" * 64}}


# ---- seeding ------------------------------------------------------------------------------------

def job(db, job_type, status="done", inputs=None, outputs=None, agent="listing", at=T_JOB,
        run_after=None, started=None, last_error=None):
    with db.session() as s:
        j = Job(agent=agent, job_type=job_type, inputs=inputs or {}, outputs=outputs,
                status=JobStatus(status), created_at=at, run_after=run_after or at,
                started_at=started or (at if status != "pending" else None),
                finished_at=at if status in ("done", "dead") else None, last_error=last_error)
        s.add(j)
        s.flush()
        return j.id


def audit(db, action, artifact, detail, job_id=None, at=T_AUDIT):
    with db.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail,
                       job_id=job_id, at=at))


def release(db, slug, version="1.0.0", *, certified=True, physical=False):
    rh = ("r" + slug)[:64]
    with db.session() as s:
        p = Product(slug=slug, title=f"Title {slug}")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={"slug": slug},
                             certified=certified, release_hash=rh if certified else None,
                             certificate={"granted": certified, "content_hash": "c" * 16,
                                          "physical_test_required": physical}))
    return rh


def up_to(db, slug, stage, *, physical=False, gates=True, gates_stale=False, parity=True,
          blocks=False, parity_blocks=False):
    """Seed one product through the chain up to `stage`."""
    v = "1.0.0"
    job(db, "radar.score", inputs={"slug": slug}, outputs={"slug": slug, "promoted": True,
                                                          "score": 0.8}, agent="market_radar")
    job(db, "cir.draft", inputs={"slug": slug}, outputs={"artifact": f"{slug}@{v}",
                                                        "drafted": True})
    job(db, "cir.compile", inputs={"cir": {"slug": slug, "version": v}},
        outputs={"artifact": f"{slug}@{v}", "compiled": True}, agent="validator")
    if stage == "validated":
        return None
    rh = release(db, slug, physical=physical)
    job(db, "gate.certify", inputs={"cir": {"slug": slug, "version": v}},
        outputs={"artifact": f"{slug}@{v}", "granted": True, "release_hash": rh},
        agent="quality_director")
    job(db, "listing.draft", inputs={"slug": slug, "version": v, "release": rh},
        outputs={"artifact": slug, "drafted": True})
    if stage == "review":
        job(db, "assets.build", "pending", inputs={"slug": slug, "version": v, "release": rh})
        return rh
    b = job(db, "assets.build", inputs={"slug": slug, "version": v, "release": rh},
            outputs={"slug": slug, "pdf_sha256": "a" * 64}, agent="publishing")
    audit(db, "assets.built", f"{slug}@{v}", {"pdfs": PDF, "pdf": PDF["US"]}, job_id=b)
    if stage == "pdf":
        return rh
    audit(db, "assets.listing_images_built", f"{slug}@{v}", {"frames": 5}, job_id=b)
    job(db, "pricing.position", inputs={"slug": slug, "version": v, "release": rh},
        outputs={"slug": slug, "price_cad": 6.5}, agent="pricing")
    if stage == "visual":
        return rh
    s_job = job(db, "listing.seo", inputs={"slug": slug, "version": v, "release": rh},
                outputs={"slug": slug, "ok": True, "listing": {"title": "t"}})
    audit(db, "listing.seo_drafted", f"{slug}@{v}", {"search_share": 0.7}, job_id=s_job)
    with db.session() as s:
        s.add(Listing(product_slug=slug, version=v, title="t", description="d", tags=[],
                      price_cad=6.5, release_hash=rh, seo_score=0.8))
    job(db, "launch.plan", inputs={"slug": slug, "version": v, "release": rh},
        outputs={"launch_on": "2026-11-01"}, agent="growth")
    # as in shadow: launch.plan queued store.publish, which refused (a closed gate)
    job(db, "store.publish", "dead", inputs={"slug": slug, "version": v},
        agent="store_operator", last_error="capability not enabled: shadow mode")
    if stage == "listing":
        return rh
    at = T_JOB - timedelta(hours=1) if gates_stale else T_AUDIT
    if gates:
        audit(db, "store.release_gates", slug, {"slug": slug, "version": v,
                                                "blocks_release": blocks,
                                                "reasons": ["search certificate"] if blocks
                                                else []}, at=at)
    if parity:
        audit(db, "listing.parity", slug, {"verdict": "PASS" if not parity_blocks else "FAIL",
                                           "blocks_release": parity_blocks,
                                           "why": "frame 2 fails"}, at=at)
    return rh


def item(inv, slug):
    found = [i for i in inv["items"] if i["slug"] == slug]
    assert len(found) == 1, (slug, found)
    return found[0]


class _Patch:
    """Open the two owner gates (phase, grant) for the duration of a block."""

    def __enter__(self):
        self.saved = (pi._phase_refusal, pi._grant_refusal)
        pi._phase_refusal = lambda db: None
        pi._grant_refusal = lambda db, slug, version, release: None

    def __exit__(self, *a):
        pi._phase_refusal, pi._grant_refusal = self.saved


# ---- seed the shared catalogue ------------------------------------------------------------------

job(DB, "radar.score", "pending", inputs={"slug": "s-candidate"}, agent="market_radar")
job(DB, "radar.score", inputs={"slug": "s-approved"}, outputs={"slug": "s-approved",
                                                              "promoted": True, "score": 0.9},
    agent="market_radar")
job(DB, "radar.score", inputs={"slug": "s-dev"}, outputs={"promoted": True, "score": 0.7},
    agent="market_radar")
job(DB, "cir.draft", inputs={"slug": "s-dev"}, outputs={"artifact": "s-dev@1.0.0",
                                                       "drafted": True})
job(DB, "cir.compile", "pending", inputs={"cir": {"slug": "s-dev", "version": "1.0.0"}},
    agent="validator")
up_to(DB, "s-valid", "validated")
up_to(DB, "s-review", "review")
up_to(DB, "s-pdf", "pdf")
up_to(DB, "s-visual", "visual")
up_to(DB, "s-listing", "listing")
up_to(DB, "s-owner", "gates")
up_to(DB, "s-ready", "gates")
up_to(DB, "s-sample", "gates", physical=True)
up_to(DB, "s-sample-passed", "gates", physical=True)
with DB.session() as _s:
    _s.add(PhysicalTest(product_slug="s-sample-passed", version="1.0.0", tester_ref="t1",
                        passed=True, completed_at=NOW))
up_to(DB, "s-published", "listing")
with DB.session() as _s:
    _row = _s.query(Listing).filter_by(product_slug="s-published").one()
    _row.state, _row.etsy_listing_id = "published_manually", "12345"
job(DB, "radar.score", inputs={"slug": "s-revise"}, outputs={"promoted": True, "score": 0.6},
    agent="market_radar")
job(DB, "cir.compile", inputs={"cir": {"slug": "s-revise", "version": "1.0.0"}},
    outputs={"artifact": "s-revise@1.0.0", "compiled": False, "errors": ["row 3 count"]},
    agent="validator")
job(DB, "radar.score", inputs={"slug": "s-rejected"},
    outputs={"promoted": False, "score": 0.9, "gate": {"decision": "refused",
                                                       "reasons": ["#88 novelty: parity"]}},
    agent="market_radar")
up_to(DB, "s-vetoed", "listing")
with DB.session() as _s:
    _s.add(OwnerVeto(subject_ref="s-vetoed", scope="product", reason="off-brand"))
# gate-open variants of the ready product
up_to(DB, "g-blocks", "gates", blocks=True)
up_to(DB, "g-parity", "gates", parity_blocks=True)
up_to(DB, "g-stale", "gates", gates_stale=True)
up_to(DB, "g-noparity", "gates", parity=False)
up_to(DB, "g-norun", "listing")
up_to(DB, "g-intent", "gates")
try:
    from brambleloop.publish.draft_intent import DraftIntent

    with DB.session() as _s:
        _s.add(DraftIntent(key="k" * 64, slug="g-intent", version="1.0.0", release="rg-intent",
                           content_digest="d" * 64, token="t" * 32, state="RECONCILE_REQUIRED"))
except Exception as exc:  # pragma: no cover
    raise AssertionError(f"draft intent seed failed: {exc}")
# stall + loop fixtures
job(DB, "cir.draft", "pending", inputs={"slug": "s-waiting"}, at=NOW - timedelta(hours=10))
for n in range(3):
    job(DB, "listing.seo", inputs={"slug": "s-loop", "version": "1.0.0", "rebuild": f"tok{n}"},
        outputs={"slug": "s-loop", "ok": False}, at=NOW - timedelta(hours=n + 1))
for n in range(2):
    job(DB, "listing.seo", inputs={"slug": "s-twice", "version": "1.0.0", "rebuild": f"t{n}"},
        outputs={"ok": False}, at=NOW - timedelta(hours=n + 1))


# ---- states -------------------------------------------------------------------------------------

EXPECTED = {
    "s-candidate": pi.RESEARCH_CANDIDATE, "s-approved": pi.RESEARCH_APPROVED,
    "s-dev": pi.PATTERN_IN_DEVELOPMENT, "s-valid": pi.PATTERN_VALIDATED,
    "s-review": pi.REVIEW_PASSED, "s-pdf": pi.PDF_COMPLETED, "s-visual": pi.VISUAL_COMPLETED,
    "s-listing": pi.LISTING_COMPLETED, "s-owner": pi.OWNER_APPROVAL_PENDING,
    "s-published": pi.PUBLISHED, "s-revise": pi.REVISION_REQUIRED,
    "s-rejected": pi.REJECTED, "s-vetoed": pi.REJECTED,
}


def test_each_state_is_derived_from_seeded_records():
    inv = pi.derive(DB)
    for slug, want in EXPECTED.items():
        it = item(inv, slug)
        assert it["state"] == want, (slug, it["state"], it["why"])
        assert it["label"] == pi.LABEL[want]
        assert it["evidence"]["job_ids"] or want == pi.PUBLISHED, slug
    assert sum(inv["counts"].values()) == inv["total"]
    assert set(inv["counts"]) == set(pi.PRIMARY_STATES)
    # evidence: job ids, digests, versions, cost and quality scores
    pdf = item(inv, "s-pdf")
    stage = next(s for s in pdf["evidence"]["stages"] if s["stage"] == "premium_pdf_completed")
    assert stage["digests"]["pdf"] == {"US": "a" * 64, "UK": "b" * 64}
    assert pdf["version"] == "1.0.0" and pdf["release_hash"]
    assert item(inv, "s-listing")["evidence"]["quality_scores"]["seo_score"] == 0.8
    assert "cost_to_date_cad" in pdf["evidence"]
    # the owner state is real: shadow phase and no grant keep it owner-held, never Ready
    owner = item(inv, "s-owner")
    assert any(h["kind"] == pi.HOLD_OWNER for h in owner["holds"]), owner["holds"]
    with _Patch():
        assert item(pi.derive(DB), "s-ready")["state"] == pi.READY
        assert item(pi.derive(DB), "s-ready")["tiers"]["public"]["ready"] is True


def test_published_manually_is_published():
    it = item(pi.derive(DB), "s-published")
    assert it["state"] == pi.PUBLISHED and "published_manually" in it["why"]


def test_ready_is_refused_whenever_any_gate_is_open():
    with _Patch():
        inv = pi.derive(DB)
        assert item(inv, "s-ready")["state"] == pi.READY
        for slug in ("g-blocks", "g-parity", "g-stale", "g-noparity", "g-norun", "g-intent"):
            it = item(inv, slug)
            assert it["state"] != pi.READY, (slug, it["why"])
            assert it["state"] == pi.LISTING_COMPLETED, (slug, it["state"])
            assert any(h["kind"] == pi.HOLD_POLICY for h in it["holds"]), slug
            assert it["tiers"]["private_draft"]["ready"] is False
            assert it["tiers"]["public"]["ready"] is False
        assert "UNKNOWN" == item(inv, "g-stale")["evidence"]["product_gates"]["state"]
    # each owner gate, alone, refuses Ready
    for which in ("_phase_refusal", "_grant_refusal"):
        with _Patch():
            setattr(pi, which, lambda *a, **k: "closed for the test")
            it = item(pi.derive(DB), "s-ready")
            assert it["state"] == pi.OWNER_APPROVAL_PENDING, (which, it["state"])
    # a gate reader that crashes is a closed gate
    with _Patch():
        def boom(*a, **k):
            raise RuntimeError("unreadable")
        pi._grant_refusal = boom
        assert item(pi.derive(DB), "s-ready")["state"] == pi.OWNER_APPROVAL_PENDING


def test_physical_sample_is_an_attribute_never_an_internal_step():
    with _Patch():
        inv = pi.derive(DB)
        sample = item(inv, "s-sample")
        # every gate passes and the owner gates are open -- only the sample is missing
        assert sample["state"] == pi.LISTING_COMPLETED, sample["state"]
        assert sample["physical_sample"]["status"] == "pending"
        assert any(h["kind"] == pi.HOLD_PHYSICAL for h in sample["holds"])
        assert sample["tiers"]["internal"]["complete"] is True
        assert sample["tiers"]["private_draft"]["ready"] is True
        assert sample["tiers"]["public"]["ready"] is False
        assert sample["state"] not in (pi.READY, pi.OWNER_APPROVAL_PENDING)
        passed = item(inv, "s-sample-passed")
        assert passed["state"] == pi.READY and passed["physical_sample"]["status"] == "passed"
        assert inv["counts"][pi.READY] == 2  # s-ready and s-sample-passed, never s-sample
        assert inv["public_ready"] == 2
        assert inv["attribute_counts"][pi.PHYSICAL_PENDING] == 1
        assert inv["attribute_counts"][pi.PHYSICAL_PASSED] == 1
    # PDF, visual and listing packages are reachable with no sample on record at all
    db2 = _fresh_db("phys")
    for slug, stage in (("p-pdf", "pdf"), ("p-vis", "visual"), ("p-list", "listing")):
        up_to(db2, slug, stage, physical=True)
    inv2 = pi.derive(db2)
    assert item(inv2, "p-pdf")["state"] == pi.PDF_COMPLETED
    assert item(inv2, "p-vis")["state"] == pi.VISUAL_COMPLETED
    assert item(inv2, "p-list")["state"] == pi.LISTING_COMPLETED
    for slug in ("p-pdf", "p-vis", "p-list"):
        assert item(inv2, slug)["physical_sample"]["status"] == "pending"
    # a sample that was made and failed is a revision
    with db2.session() as s:
        s.add(PhysicalTest(product_slug="p-list", version="1.0.0", tester_ref="t",
                           passed=False, completed_at=NOW))
    assert item(pi.derive(db2), "p-list")["state"] == pi.REVISION_REQUIRED


def test_dashboard_shows_physical_beside_state():
    production.reset()
    with _Patch():
        data = production.build(DB)
    inv = data["sections"]["inventory"]
    rows = {r["key"]: r for r in inv["items"]}
    assert len(rows) == 15, sorted(rows)
    assert rows[pi.PHYSICAL_PENDING]["kind"].startswith("attribute")
    assert "s-sample@1.0.0" in rows[pi.PHYSICAL_PENDING]["products"]
    assert "s-sample@1.0.0" in rows[pi.LISTING_COMPLETED]["products"]
    assert "s-sample@1.0.0" not in rows[pi.READY]["products"]
    tiers = {t["title"]: t["count"] for t in data["sections"]["tiers"]["items"]}
    assert tiers["Awaiting physical sample"] == 1 and tiers["Public publication ready"] == 2
    prod = {p["title"]: p for p in data["sections"]["products"]["items"]}
    assert prod["s-sample@1.0.0"]["physical_sample"] == "pending"
    assert "physical" in prod["s-sample@1.0.0"]["held"]


def test_stall_and_loop_detection():
    fl = flow_health.flow(DB, now=NOW)
    rows = {(r["slug"], r["version"]): r for r in fl["rows"]}
    approved = rows[("s-approved", None)]
    assert approved["stalled"] and approved["stalls"][0]["kind"] == "no_successor", approved
    assert approved["stalls"][0]["job_type"] == "radar.score"
    waiting = rows[("s-waiting", None)]
    assert any(s["kind"] == "waiting_too_long" for s in waiting["stalls"]), waiting
    loop = rows[("s-loop", "1.0.0")]
    assert loop["looping"] and loop["loops"][0]["runs"] == 3, loop
    assert loop["loops"][0]["outputs_unchanged"] is True
    assert not rows[("s-twice", "1.0.0")]["looping"]
    # healthy rows are not stalled: successor present, or the row moved past it
    for slug in ("s-dev", "s-review", "s-listing", "s-owner"):
        assert not rows[(slug, "1.0.0")]["stalled"], (slug, rows[(slug, "1.0.0")]["stalls"])
    # a stage that succeeded with nothing queued after it is a stall wherever it happens
    assert rows[("s-valid", "1.0.0")]["stalled"]   # compiled, no gate.certify
    assert rows[("s-pdf", "1.0.0")]["stalled"]     # PDF built, no pricing.position
    # the shadow refusal of store.publish is a HOLD (owner), not a stall
    owner = rows[("s-owner", "1.0.0")]
    assert not owner["stalled"] and "owner" in owner["held_reasons"], owner
    assert fl["stalled_count"] >= 2 and fl["looping_count"] == 1


def _fresh_db(tag):
    d = tempfile.mkdtemp(prefix=f"w5inv_{tag}_")
    db = Database(f"sqlite:///{os.path.join(d, 'x.db')}")
    db.create_all()
    return db


def test_useful_vs_noop_split_uses_the_handlers_outcome_labels():
    db = _fresh_db("split")
    recent = NOW - timedelta(hours=2)
    job(db, "cir.compile", outputs={"compiled": True}, agent="validator", at=recent)
    job(db, "listing.draft", outputs={"drafted": True}, agent="listing", at=recent)
    job(db, "cir.compile", outputs={"compiled": False}, agent="validator", at=recent)  # no-op
    job(db, "ops.heartbeat", outputs={"queue": {"pending": 3}}, agent="ops", at=recent)
    job(db, "support.triage", outputs={"cases": 0}, agent="support", at=recent)
    job(db, "listing.draft", outputs={"drafted": True}, agent="listing",
        at=NOW - timedelta(days=3))
    job(db, "assets.build", "dead", agent="publishing", at=recent, last_error="KeyError: x")
    job(db, "store.publish", "dead", agent="store_operator", at=recent,
        last_error="capability not enabled: shadow mode")
    with db.session() as s:
        s.add(CostEntry(agent="validator", amount_cad=0.25, at=recent))
    split = flow_health.useful_split(db, now=NOW)
    assert split["24h"]["useful"] == 2 and split["24h"]["no_op"] == 3, split
    assert split["7d"]["useful"] == 3 and split["7d"]["no_op"] == 3, split
    assert split["24h"]["dead_defect"] == 1 and split["24h"]["dead_refused"] == 1
    act = flow_health.activity(db, now=NOW)
    agents = {a["agent"]: a for a in act["windows"]["24h"]["agents"]}
    v = agents["validator"]
    assert (v["completed"], v["useful"], v["no_op"], v["cost_cad"]) == (2, 1, 1, 0.25), v
    assert agents["publishing"]["dead_defect"] == 1
    assert v["idle_s"] <= 24 * 3600 and "next_cadence" in v
    depts = {d["department"] for d in act["windows"]["7d"]["departments"]}
    assert depts, act


def _rows() -> dict:
    skip = {"cc_owner_sessions", "cc_security_events", "cc_nonces"}
    names = [n for n in inspect(DB.engine).get_table_names() if n not in skip]
    with DB.engine.connect() as conn:
        return {n: conn.execute(text(f'SELECT COUNT(*) FROM "{n}"')).scalar() for n in names}


def test_cc_production_requires_owner_session_and_is_read_only():
    production.reset()
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.get("/api/cc/production").status_code == 401
    r = c.get("/api/cc/production", headers={"Authorization": f"Bearer {OPS}"})
    assert r.status_code == 401 and "s-ready" not in r.text, "operator token is not an owner"
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    before = _rows()
    r = c.get("/api/cc/production")
    assert r.status_code == 200, r.text[:400]
    assert r.headers.get("cache-control") == "no-store"
    assert _rows() == before, "reading the production view wrote a row"
    data = r.json()
    assert data["tab"] == "PRODUCTION" and data["read_only"] is True
    for name in ("inventory", "tiers", "products", "agents_working", "recent_outputs",
                 "stalls_loops", "costs_failures", "next_work"):
        assert data["sections"][name]["status"] in ("OK", "DEGRADED", "BLOCKED"), (
            name, data["sections"][name])
    assert c.post("/api/cc/production", json={}).status_code in (403, 404, 405)


def test_pwa_has_the_production_view():
    static = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
    view = (static / "js" / "views" / "production.js").read_text()
    assert "export async function render" in view and "api.production()" in view
    assert "innerHTML" not in view and "localStorage" not in view
    assert '"js/views/production.js"' in (static / "sw.js").read_text()
    assert 'id: "production"' in (static / "js" / "routes.js").read_text()
    assert "/production`" in (static / "js" / "api.js").read_text()


def test_readback_projection_carries_no_private_data():
    with DB.session() as s:
        s.add(Product(slug="secret-unreleased", title="Unreleased Design"))
        s.add(CostEntry(agent="market_radar", amount_cad=3.21, product_slug="secret-unreleased"))
        s.add(OwnerAction(action="approve tester spend for secret-unreleased",
                          max_cost_cad=40.0, requirement_key="secret-unreleased"))
    job(DB, "assets.build", "dead", inputs={"slug": "secret-unreleased"},
        last_error="ValueError: customer jane@example.com token sk-live-xyz")
    out = pi.production_summary(DB, now=NOW)
    blob = json.dumps(out)
    for leak in ("secret-unreleased", "Unreleased Design", "3.21", "jane@example.com",
                 "sk-live", "s-ready", "Title ", "customer", "cost_cad", "release_hash"):
        assert leak not in blob, leak
    assert set(out) == {"readable", "as_of", "gate_mode", "products", "by_state",
                        "physical_sample", "ready_for_publication", "private_draft_ready",
                        "stalled", "looping", "held_by_reason", "useful_vs_noop"}, set(out)
    assert out["readable"] is True and out["by_state"][pi.REJECTED] >= 2
    assert out["stalled"] >= 2 and out["looping"] == 1
    assert out["held_by_reason"]["paid_approval"] >= 1
    for w in ("24h", "7d"):
        assert set(out["useful_vs_noop"][w]) == {"useful", "no_op"}


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name}: {exc}")
    print(f"{'OK' if not failed else 'FAILED'}: {failed} failed")
    sys.exit(1 if failed else 0)
