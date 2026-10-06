"""Final Build wave fb4-LAUNCH: the owner approval packet's evidence (F-704), the recorded
controlled phase transition (F-299) and the generated Launch-0 owner launch packet (F-878).

Hermetic: no network, no model, no secret (a synthetic ops credential only), no live Etsy.
Failing checks are findings; do not weaken them. UNKNOWN is never PASS.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import atexit
import copy
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]
_TMP = tempfile.mkdtemp(prefix="fb4launch_")
atexit.register(shutil.rmtree, _TMP, True)
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import phase as P  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Job, Listing, Phase,  # noqa: E402
                                     PatternVersion, Product)
from brambleloop.launch import packet as LP  # noqa: E402
from brambleloop.ops import publication_authority as pa  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402
from brambleloop.runtime.worker import JobContext  # noqa: E402

TOKEN = "fb4-launch-synthetic-operator-token-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class _Env:
    """Set environment variables for a block and restore them afterwards."""

    def __init__(self, **values):
        self.values, self.prior = values, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.prior[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _db() -> Database:
    db = Database("sqlite:///" + tempfile.mkdtemp(prefix="db_", dir=_TMP) + "/t.sqlite",
                  scratch=True)
    db.create_all()
    return db


def _certify_launch0(db) -> list[tuple[str, str, str]]:
    """Launch-0 certified through the real gate.certify handler, in shadow."""
    out = []
    for rel in LP.launch0_releases():
        cir = l0.cir_for(next(v.build for v in l0.candidate(rel["candidate"]).variants
                              if l0.cir_for(v.build).slug == rel["slug"]))
        job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                                   idempotency_key=f"t:certify:{cir.slug}")
        with db.session() as s:
            row = s.get(Job, job.id)
            s.expunge(row)
        ctx = JobContext(job=row, db=db, queue=JobQueue(db), registry=Registry(db),
                         phase=Phase.SHADOW)
        got = pipeline.handle_certify(ctx)
        assert got.get("granted") is True, (cir.slug, got)
        with db.session() as s:
            pv = s.scalar(select(PatternVersion).join(Product).where(
                Product.slug == cir.slug, PatternVersion.version == cir.version))
            out.append((cir.slug, cir.version, pv.release_hash))
    return out


def _drafted(db, slug, version, release, *, price=9.5,
             description="A crochet pattern PDF.") -> None:
    with db.session() as s:
        s.add(Listing(product_slug=slug, version=version, title=f"{slug} crochet pattern",
                      description=description, release_hash=release, price_cad=price))


class _Payload:
    def __init__(self, title):
        self.title = title


def _fixed_payload():
    return patch.object(etsy_ops, "sent_fields", side_effect=lambda p: {"title": "fixed"})


def _api(db, router_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router_module.make_router(db))
    return TestClient(app)


# ---- F-704: the approval packet carries the evidence, and binds it ------------------------

def test_preview_carries_every_evidence_section_and_unknown_never_displays_as_passing():
    db = _db()
    slug, version, release = _certify_launch0(db)[0]
    _drafted(db, slug, version, release)
    from brambleloop.app import publication_authority_api as api_mod

    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN), \
            patch.object(etsy_ops, "certified_payload", return_value=_Payload("t")), \
            _fixed_payload():
        api = _api(db, api_mod)
        body = {"slug": slug, "version": version, "release": release}
        assert api.post("/api/owner/publication/preview", json=body).status_code == 403
        r = api.post("/api/owner/publication/preview", json=body, headers=AUTH)
        assert r.status_code == 200, r.text
        got = r.json()
    ev = got["content"]["evidence"]
    for key in ("certification", "parity", "listing_set", "disclosure", "policy", "search",
                "economics", "rollback"):
        assert key in ev and "state" in ev[key] and ev[key].get("why"), (key, ev.get(key))
    # certified through the real gate: the certificate verdict is read, not assumed
    assert ev["certification"]["state"] == "PASS", ev["certification"]
    assert ev["certification"]["certificate_granted"] is True
    assert ev["certification"]["physical_proof"] in ("not_required", "passed",
                                                     "required_not_passed", "UNKNOWN")
    # parity per dimension, with the unjudged ones named
    from brambleloop.visual import parity

    par = ev["parity"]
    assert par["state"] != "PASS"
    assert set(par.get("dimensions") or {}) == set(parity.DIMENSIONS) or par["state"] == "UNKNOWN"
    if par.get("dimensions"):
        assert par["unjudged"], "an empty frame set judged every dimension"
    # policy never read: UNKNOWN, not fresh
    assert ev["policy"]["state"] == "UNKNOWN" and ev["policy"]["never_checked"]
    # economics carries its basis and is never PASS
    assert ev["economics"]["state"] == "MODELLED", ev["economics"]
    assert ev["economics"]["fees_basis"] == "modelled"
    assert ev["economics"]["sales_volume_basis"] == "unknown"
    # rollback path is described, and the rehearsal is UNKNOWN until one is on file
    assert ev["rollback"]["state"] == "UNKNOWN" and "buyers" in ev["rollback"]["path"]
    assert "delete_listing" in ev["rollback"]["path"]["remove_draft"]
    # display: only PASS is passing; the summary names what is not passing
    for row in got["display"]:
        assert row["passing"] == (row["state"] == "PASS"), row
    assert got["evidence_summary"]["all_gated_sections_pass"] is False
    assert "policy" in got["evidence_summary"]["unknown"]
    assert got["digest"] == pa.digest(got["content"])


def test_an_unreadable_or_malformed_section_is_unknown_not_pass():
    def boom():
        raise RuntimeError("store unavailable")

    assert pa._guard(boom)["state"] == "UNKNOWN"
    assert pa._guard(lambda: {"ok": True})["state"] == "UNKNOWN"
    assert pa._guard(lambda: {"state": "GREEN"})["state"] == "UNKNOWN"
    rows = pa.display({"policy": {"state": "UNKNOWN", "why": "x"}})
    assert all(not r["passing"] for r in rows)
    assert {r["section"] for r in rows} >= set(pa.GATED_SECTIONS)


def _grant(db, slug, version, release):
    content = pa.snapshot(db, slug, version, release)
    return pa.approve(db, authorization=TOKEN, slug=slug, version=version, release=release,
                      expected_digest=pa.digest(content), reason="owner reviewed the evidence"
                      )["approval_id"]


def test_a_change_in_any_bound_evidence_element_voids_the_grant():
    db = _db()
    slug, version, release = _certify_launch0(db)[0]
    _drafted(db, slug, version, release)
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PUBLISH_AUTHORISED="1"), \
            patch.object(etsy_ops, "certified_payload", return_value=_Payload("t")), \
            _fixed_payload():
        gid = _grant(db, slug, version, release)
        assert pa.validate(db, gid, slug=slug, version=version, release=release) is None
        # every section reader, changed in turn, voids the grant
        readers = {"certification": "_certification", "parity": "_parity",
                   "disclosure": "_disclosure", "search": "_search",
                   "economics": "_economics", "rollback": "_rollback"}
        assert len(readers) == 6
        for section, fn in readers.items():
            changed = {"state": "PASS", "why": f"changed {section}"}
            with patch.object(pa, fn, return_value=changed):
                why = pa.validate(db, gid, slug=slug, version=version, release=release)
                assert why and "does not match current content" in why, (section, why)
            assert pa.validate(db, gid, slug=slug, version=version, release=release) is None
        with patch.object(pa, "_listing_set",
                          return_value=({"state": "PASS", "why": "changed"}, {"frames": []})):
            assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                                   release=release)
        with patch.object(pa, "_policy", return_value={"state": "PASS", "why": "changed"}):
            assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                                   release=release)
        assert pa.validate(db, gid, slug=slug, version=version, release=release) is None

        # and real state changes, not only patched readers
        from brambleloop.gates.platform_policy import record_snapshot

        record_snapshot(db, "seller_policy", text="a reading", version="v1",
                        checked_on=__import__("datetime").date.today().isoformat())
        assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                               release=release)
        gid = _grant(db, slug, version, release)
        with db.session() as s:
            row = s.scalar(select(Listing).where(Listing.product_slug == slug))
            row.price_cad = 12.0
        assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                               release=release)
        gid = _grant(db, slug, version, release)
        from brambleloop.publish import withholding

        withholding.record(db, slug, version, kind=withholding.KINDS[0], reason="held")
        assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                               release=release)
        withholding.record(db, slug, version, kind=withholding.KINDS[0], reason=None)
        gid = _grant(db, slug, version, release)
        from brambleloop.launch import rollback

        rollback.rehearse(db, slug=slug, version=version)
        assert "does not match" in pa.validate(db, gid, slug=slug, version=version,
                                               release=release)


# ---- F-299: the phase has a durable, owner-recorded transition ----------------------------

def test_env_alone_saying_limited_production_runs_as_shadow_with_an_incident():
    db = _db()
    env = {P.ENV_VAR: "limited_production"}
    r = P.resolve(db, env)
    assert r["phase"] == "shadow" and r["mismatch"] and r["recorded_phase"] == "shadow", r
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PHASE="limited_production"):
        assert P.effective_phase(db) is Phase.SHADOW
        assert P.effective_phase(db) is Phase.SHADOW  # restated, not re-opened
    with db.session() as s:
        open_ = list(s.scalars(select(Incident).where(
            Incident.signature == P.INCIDENT_SIGNATURE, Incident.resolved.is_(False))))
        audits = list(s.scalars(select(AuditLog).where(AuditLog.action == P.MISMATCH)))
    assert len(open_) == 1 and open_[0].report_count == 2 and len(audits) == 1
    # the default stays shadow, with nothing to reconcile
    assert P.resolve(_db(), {})["phase"] == "shadow"
    assert P.resolve(_db(), {})["agree"] is True
    # an unparseable env value is not a phase
    assert P.resolve(_db(), {P.ENV_VAR: "prod"})["phase"] == "shadow"


def test_recorded_transitions_and_env_agree_then_that_phase_applies_and_rows_are_audited():
    db = _db()
    from brambleloop.app import phase_api

    from phase_fixture import synthetic_readiness

    # K4 / F-300: the route evaluates live readiness at transition time; a hermetic database
    # cannot be launch-ready, so this route test substitutes the synthetic verdict (the real
    # refusal is tested in test_w3_k4_launch_verdict.py).
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PHASE="limited_production"), \
            patch.object(P, "live_readiness", synthetic_readiness):
        P.effective(db)  # mismatch incident opened first
        api = _api(db, phase_api)
        # rc1-AUTH D4: refs must resolve to real recorded evidence rows; free text does not.
        invented = {"to": "staging", "reason": "readiness reviewed",
                    "evidence_refs": {"readiness": "readiness-run-1",
                                      "rollback": "launch.rollback_rehearsed:7"}}
        assert api.post("/api/owner/phase/transition", json=invented,
                        headers=AUTH).status_code == 409
        from phase_fixture import synthetic_evidence

        refs = synthetic_evidence(db)
        body = {"to": "staging", "reason": "readiness reviewed", "evidence_refs": refs}
        assert api.post("/api/owner/phase/transition", json=body).status_code == 403
        assert api.get("/api/owner/phase").status_code == 403
        # one step at a time, and upward moves cite readiness and rollback
        skip = {**body, "to": "limited_production"}
        assert api.post("/api/owner/phase/transition", json=skip, headers=AUTH).status_code == 409
        bare = {**body, "evidence_refs": {}}
        assert api.post("/api/owner/phase/transition", json=bare, headers=AUTH).status_code == 409
        noreason = {**body, "reason": " "}
        assert api.post("/api/owner/phase/transition", json=noreason,
                        headers=AUTH).status_code == 409
        r = api.post("/api/owner/phase/transition", json=body, headers=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["from"] == "shadow" and r.json()["to"] == "staging"
        assert r.json()["effective_now"] == "staging"  # env limited_production > staging
        r = api.post("/api/owner/phase/transition",
                     json={**body, "to": "limited_production"}, headers=AUTH)
        assert r.status_code == 200, r.text
        assert P.effective_phase(db) is Phase.LIMITED_PRODUCTION
        state = api.get("/api/owner/phase", headers=AUTH).json()
        assert state["phase"] == "limited_production" and state["agree"] is True
        assert [h["to"] for h in state["history"]] == ["limited_production", "staging"]
        # env says production, record says limited_production: the more restrictive applies
        assert P.resolve(db, {P.ENV_VAR: "production"})["phase"] == "limited_production"
        # env lowered without a record: the more restrictive (env) applies
        assert P.resolve(db, {P.ENV_VAR: "shadow"})["phase"] == "shadow"
        # rollback: any downward move with a reason, no refs needed
        r = api.post("/api/owner/phase/transition",
                     json={"to": "shadow", "reason": "rollback drill"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["direction"] == "down", r.text
        assert P.effective_phase(db) is Phase.SHADOW
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                              .order_by(AuditLog.id)))
        inc = s.scalar(select(Incident).where(Incident.signature == P.INCIDENT_SIGNATURE))
        assert inc is not None
    assert [(r.detail["from"], r.detail["to"]) for r in rows] == [
        ("shadow", "staging"), ("staging", "limited_production"),
        ("limited_production", "shadow")]
    for r in rows:
        assert r.actor == P.PRINCIPAL and r.detail["principal"] == P.PRINCIPAL
        assert r.detail["reason"] and r.detail["at"] and r.detail["seal"]
        assert "token" not in json.dumps(r.detail).lower() or TOKEN not in json.dumps(r.detail)
    assert rows[0].detail["evidence_refs"] == refs
    # D4: the sealed row records what each ref resolved to; D1: rows are chained.
    assert rows[0].detail["evidence"]["readiness"]["id"] == int(refs["readiness"])
    assert [r.detail["seq"] for r in rows] == [1, 2, 3]
    assert rows[1].detail["prev_id"] == rows[0].id


def test_a_forged_or_edited_transition_row_is_not_authority():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor=P.PRINCIPAL, action=P.TRANSITION, artifact="phase:shadow->production",
                       detail={"principal": P.PRINCIPAL, "from": "shadow", "to": "production",
                               "reason": "forged", "evidence_refs": {}, "at": "2026-10-01",
                               "seal": "0" * 64}))
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN):
        r = P.resolve(db, {P.ENV_VAR: "production"})
        assert r["phase"] == "shadow" and r["mismatch"], r
        # only a recorded rollback to shadow clears an unverifiable newest row
        try:
            P.record_transition(db, authorization=TOKEN, to="staging", reason="x",
                                evidence_refs={"readiness": "a", "rollback": "b"})
            raise AssertionError("moved up past an unverifiable record")
        except ValueError:
            pass
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="clear forged row")
        assert P.resolve(db, {P.ENV_VAR: "shadow"})["agree"] is True
        # a genuine row edited afterwards stops verifying
        from phase_fixture import record_phase_path

        record_phase_path(db, TOKEN, "staging")
        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                           .order_by(AuditLog.id.desc()).limit(1))
            d = dict(row.detail)
            d["to"] = "production"
            row.detail = d
        assert P.resolve(db, {P.ENV_VAR: "production"})["phase"] == "shadow"
    # without the owner credential nothing verifies and nothing can be recorded
    with _Env(BRAMBLELOOP_OPS_TOKEN=None):
        assert P.resolve(db, {P.ENV_VAR: "staging"})["phase"] == "shadow"


def test_store_publish_refuses_when_env_says_production_but_nothing_is_recorded():
    from test_draft_creation_durability import args, ctx, setup

    from brambleloop.core.resilience import PermanentError

    tmp = tempfile.mkdtemp(prefix="pub_", dir=_TMP)
    db = setup(Path(tmp) / "state.db")
    kw = args()
    with db.session() as s:
        p = Product(slug="original", title="Synthetic")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={"synthetic": True},
                             certified=True, release_hash="release-a"))
    with _Env(BRAMBLELOOP_OPS_TOKEN=TOKEN, BRAMBLELOOP_PUBLISH_AUTHORISED="1",
              BRAMBLELOOP_PHASE="production"), \
            patch.object(pipeline, "_listing_parity", return_value={"blocks_release": False}), \
            patch.object(pipeline, "_release_gates", return_value={"blocks_release": False}), \
            patch.object(etsy_ops, "certified_payload",
                         return_value=copy.deepcopy(kw["payload"])), \
            patch.object(etsy_ops, "certified_images",
                         return_value={**copy.deepcopy(kw["listing_images"]), "problems": []}):
        _grant(db, "original", "1", "release-a")
        try:
            pipeline._revalidate_publish_effect(ctx(db), **{k: kw[k] for k in (
                "slug", "version", "release", "payload", "docs", "listing_images")})
            raise AssertionError("published on the environment flag alone")
        except PermanentError as exc:
            assert "phase" in str(exc), exc


# ---- F-878: the generated owner launch packet ------------------------------------------------

def test_launch_packet_on_a_fresh_shadow_db_with_launch0_certified_is_honest():
    db = _db()
    certified = _certify_launch0(db)
    out_dir = Path(tempfile.mkdtemp(prefix="packet_", dir=_TMP))
    with _Env(BRAMBLELOOP_PHASE="shadow"):
        p = LP.build(db, sha="f" * 40, repo_root=ROOT)
    assert p["candidate_sha"] == "f" * 40
    assert p["verdict"] in ("UNKNOWN", "BLOCKED") and p["verdict"] != "READY", p["verdict"]
    assert p["phase"]["phase"] == "shadow" and p["phase"]["agree"] is True
    slugs = {(pr["slug"], pr["version"]) for pr in p["products"]}
    assert slugs == {(s, v) for s, v, _r in certified}
    for pr in p["products"]:
        assert pr["certified"] is True and pr["release"]
        assert pr["sections"]["certification"]["state"] == "PASS", pr["sections"]["certification"]
        for key in ("parity", "listing_set", "disclosure", "policy", "search", "rollback"):
            assert pr["sections"][key]["state"] != "PASS", (pr["slug"], key, pr["sections"][key])
        assert pr["sections"]["economics"]["state"] == "UNKNOWN"  # no price drafted
        assert pr["listing"] is None and pr["publishable_now"] is False
        assert "policy" in pr["unknown"]
        assert pr["physical_proof"] in ("not_required", "passed", "required_not_passed",
                                        "UNKNOWN")
        for row in pr["display"]:
            assert row["passing"] == (row["state"] == "PASS")
        assert {g["section"] for g in pr["open_gates"]} == set(pr["not_passing"])
        assert pr["launch_wide_owner_actions"] == [o["key"] for o in
                                                   p["owner_queue"]["owner_actions"]]
    # the owner queue comes from launch readiness, each with action, cost, minutes, consequence
    q = p["owner_queue"]
    assert q["ready"] is False and q["owner_actions"], q
    for o in q["owner_actions"]:
        assert o["action"] and isinstance(o["max_cost_cad"], (int, float))
        assert isinstance(o["minutes"], int) and o["consequence_of_delay"]
    assert "buyers" in p["rollback_path"] and p["activation_steps"]
    j, m = LP.write(p, out_dir)
    assert j.name.startswith("launch_packet_ffffffffffff_") and j.suffix == ".json"
    assert json.loads(j.read_text())["verdict"] == p["verdict"]
    md = m.read_text()
    assert "Verdict: READY" not in md and "UNKNOWN" in md and "Open owner gates" in md

    # it reads state: fresh policy readings flip the policy section, nothing hard-coded
    from datetime import date

    from brambleloop.gates.platform_policy import POLICY_SOURCES, record_snapshot

    for source in POLICY_SOURCES:
        record_snapshot(db, source, text=f"reading of {source}", version="v1",
                        checked_on=date.today().isoformat())
    p2 = LP.build(db, sha="f" * 40, repo_root=ROOT)
    assert all(pr["sections"]["policy"]["state"] == "PASS" for pr in p2["products"])
    assert p2["verdict"] != "READY"
    # an env-only phase change shows as a mismatch, run as shadow
    with _Env(BRAMBLELOOP_PHASE="limited_production"):
        p3 = LP.build(db, sha="f" * 40)
    assert p3["phase"]["phase"] == "shadow" and p3["phase"]["agree"] is False
    assert p3["recorded_suite"]["state"] == "UNKNOWN"


def test_launch_packet_script_writes_json_and_markdown():
    db = _db()
    _certify_launch0(db)
    url = str(db.engine.url)
    out_dir = Path(tempfile.mkdtemp(prefix="script_", dir=_TMP))
    import importlib.util

    spec = importlib.util.spec_from_file_location("launch_packet_script",
                                                  ROOT / "scripts" / "launch_packet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with _Env(BRAMBLELOOP_PHASE="shadow"):
        assert mod.main(["--db", url, "--sha", "a" * 40, "--out", str(out_dir)]) == 0
    files = sorted(out_dir.iterdir())
    assert [f.suffix for f in files] == [".json", ".md"], files
    assert files[0].stem == files[1].stem and files[0].stem.startswith("launch_packet_aaaaaaaaaaaa_")
    assert json.loads(files[0].read_text())["verdict"] != "READY"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}  -- {type(exc).__name__}: {str(exc)[:600]}")
            if os.environ.get("CERT_TRACE"):
                traceback.print_exc()
    print(f"\n  {len(tests) - failed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
