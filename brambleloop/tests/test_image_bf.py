"""IMAGE-BF: findings B and F of IMAGE-E2E, end to end on the real worker's gallery.

B. Laura's publication approval has a production path (`visual.laura_approval`):
   * a generated gallery verified in every respect but Laura raises ONE owner card;
   * the owner decides through the existing step-up (passphrase + TOTP) on the real
     `/api/cc/*` routes, or with "Approve all eligible" (which shows the frames);
   * the approval is recorded per gallery and frame hash and covers exactly those hashes;
   * every decision is audited; nothing is inferred; a mutation that skips the step-up fails.
F. The first-customer `imagery` area judges a certified generated gallery as that gallery:
   a complete 7-frame certificate passes, a 6-frame one fails, and the disclosure and
   re-judging checks still bite.

Starting state: the IMAGE-E2E production-like DB and the real `Worker`, unaided, WITHOUT the
Laura publication double (`test_image_e2e_worker.run_worker(laura_double=False)`). Doubles are
the same labelled ones IMAGE-E2E uses (BFL transport, judge doubles). Laura
(laura-r2-a42aeac7) is locked: nothing here modifies, regenerates or substitutes her.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_image_bf.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import base64
import os
import shutil
import sys
import time
import traceback
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import test_image_e2e_worker as E  # noqa: E402  (installs the loopback-only socket guard)

PASS = "owner passphrase for image bf approvals"
TOTP = base64.b32encode(b"image-bf-laura-totp-key!").decode().rstrip("=")
_S: dict = {}


# ---- the gallery, once: verified, held only on Laura ------------------------------------------

def _copy(src: str, dst: str) -> None:
    """A SQLite database with its WAL side files (the engine is disposed first)."""
    for ext in ("-wal", "-shm"):
        if os.path.exists(dst + ext):
            os.remove(dst + ext)
    shutil.copy(src, dst)
    for ext in ("-wal", "-shm"):
        if os.path.exists(src + ext):
            shutil.copy(src + ext, dst + ext)


def gallery():
    if "g" not in _S:
        db, version, rh = E.production_like()
        assert version == E.VERSION, version
        jobs, bfl = E.run_worker(db, laura_double=False)
        path = db.engine.url.database
        db.engine.dispose()
        snap = path + ".before-decision"
        _copy(path, snap)
        _S["g"] = {"path": path, "snap": snap, "rh": rh, "key": E._gallery_key(rh),
                   "posts": len(bfl.posts)}
    return _S["g"]


def app():
    """The real app on the gallery's database, with a real owner passphrase + TOTP."""
    if "app" not in _S:
        g = gallery()
        from brambleloop.core import opsauth

        os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{g['path']}"
        os.environ.pop("DATABASE_URL", None)
        os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
        os.environ["BRAMBLELOOP_PHASE"] = "shadow"
        os.environ[opsauth.TOKEN_VAR] = "b" * 40
        from brambleloop.app.command_center import auth

        os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
        os.environ[auth.TOTP_VAR] = TOTP
        from brambleloop.app import main

        main.db.create_all()
        _S["app"] = main
    return _S["app"]


def db():
    return app().db


def restore():
    """Back to the moment the worker finished (card raised, nothing decided)."""
    g = gallery()
    d = db()
    d.engine.dispose()
    _copy(g["snap"], g["path"])
    d.engine.dispose()


def _code() -> str:
    from sqlalchemy import delete

    from brambleloop.app.command_center import auth
    from brambleloop.app.command_center.models import RequestNonce

    auth.ensure_tables(db())
    with db().session() as s:
        s.execute(delete(RequestNonce).where(
            RequestNonce.session_public_id == auth.TOTP_OWNER_KEY))
    return auth.totp_code(TOTP)


def session():
    from fastapi.testclient import TestClient

    c = TestClient(app().app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS, "totp": _code()})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def post(c, csrf, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
                                            "X-CC-Timestamp": str(int(time.time()))})


def expire_stepup(c):
    from sqlalchemy import select

    from brambleloop.app.command_center import auth
    from brambleloop.app.command_center.models import OwnerSession

    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with db().session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def cards():
    from sqlalchemy import select

    from brambleloop.core.models import OwnerAction
    from brambleloop.ops import owner_queue
    from brambleloop.visual import laura_approval as LA

    with db().session() as s:
        return [(r.id, r.requirement_key, owner_queue.effective_state(r))
                for r in s.scalars(select(OwnerAction).order_by(OwnerAction.id))
                if LA.is_card(r.requirement_key)]


def approvals():
    from sqlalchemy import select

    from brambleloop.visual.image_records import LauraGalleryApproval, ensure_tables

    ensure_tables(db())
    with db().session() as s:
        return [(r.run_key, r.frame_sha256, r.decision, r.step_up, r.via, r.decided_by)
                for r in s.scalars(select(LauraGalleryApproval).order_by(LauraGalleryApproval.id))]


def audits(action):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db().session() as s:
        return [(a.actor, dict(a.detail or {})) for a in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def laura_shas():
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import laura_approval as LA

    return {f["sha256"] for f in LA.laura_frames(GP.gallery_status(db(), gallery()["key"]))}


def valid_certs():
    from sqlalchemy import select

    from brambleloop.core.models import ListingSetCertificateRecord

    with db().session() as s:
        return [(c.id, len((c.certificate or {}).get("frames") or [])) for c in s.scalars(
            select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.product_slug == E.SLUG,
                ListingSetCertificateRecord.state == "valid"))]


# ---- B: the card ------------------------------------------------------------------------------

def test_1_a_verified_laura_gallery_raises_exactly_one_card_showing_its_frames():
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import laura_approval as LA

    restore()
    key = gallery()["key"]
    got = cards()
    assert len(got) == 1 and got[0][2] == "open", got
    raised = audits(LA.AUDIT_RAISED)
    assert len(raised) == 1, raised
    d = raised[0][1]
    shas = laura_shas()
    assert shas and {f["sha256"] for f in d["frames"]} == shas, (d["frames"], shas)
    roles = {f["role"] for f in d["frames"]}
    assert roles == {"lifestyle", "size"}, roles
    assert all(f["image_url"].startswith("/api/cc/images/candidates/") for f in d["frames"])
    # The real status is held on Laura only; nothing is certified and nothing is approved.
    st = GP.gallery_status(db(), key)
    assert not st["ok"] and LA.verified_but_for_laura(db(), key, st)
    assert {b["gate"] for b in st["blockers"]} <= {"laura_publication", "exception_route"}
    assert not approvals()
    assert all(n < 7 for _i, n in valid_certs()), valid_certs()
    # Once per gallery: re-certifying, re-raising and re-running the card stage add nothing.
    again = LA.raise_card(db(), key)
    assert again["raised"] is False and again["card_id"] == got[0][0], again
    IP._certify_route(db(), key, IP.SP.FLUX_ROUTE, {})
    GP.certify_gallery(db(), key)
    assert cards() == got and len(audits(LA.AUDIT_RAISED)) == 1
    # The card is visible to the owner and readable with its frames.
    c, _csrf = session()
    r = c.get("/api/cc/laura-gallery/card", params={"key": got[0][1]})
    assert r.status_code == 200 and {f["sha256"] for f in r.json()["frames"]} == shas, \
        r.text


def test_2_a_gallery_that_fails_a_real_gate_raises_no_card():
    from brambleloop.visual import laura_approval as LA

    st = {"ok": False, "frames": [{"position": 3, "role": "lifestyle", "laura_present": True,
                                   "sha256": "a" * 64, "candidate_id": 1}],
          "blockers": [{"gate": "identity", "status": "FAIL"}]}
    with patch("brambleloop.visual.gallery_persist.gallery_status",
               lambda *_a, **_k: {**st, "ok": False}):
        assert LA.verified_but_for_laura(db(), "k", st) is False
        assert LA.raise_card(db(), "k", st=st)["raised"] is False


# ---- B: the step-up --------------------------------------------------------------------------

def _no_stepup_is_refused():
    """The decision refuses without a fresh step-up, on both doors, and moves nothing."""
    from brambleloop.app.command_center import approve_all as AA

    restore()
    before = (cards(), approvals())
    key = before[0][0][1]
    c, csrf = session()
    expire_stepup(c)
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "approved"})
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, (r.status_code, r.text)
    pv = c.get("/api/cc/approve-all").json()
    assert any(e["requirement_key"] == key for e in pv["eligible"]), pv["eligible"]
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, (r.status_code, r.text)
    # a wrong TOTP is no step-up
    r = post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS, "totp": "000000"})
    assert r.status_code != 200, r.text
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "approved"})
    assert r.status_code == 403, r.text
    assert (cards(), approvals()) == before, "a refused decision moved something"
    assert not audits("laura_gallery.decision")
    # the module refuses a caller that does not assert the step-up, or is not the owner
    from brambleloop.visual import laura_approval as LA

    for kw in ({"actor": "owner:cc:x", "step_up": False}, {"actor": "system", "step_up": True}):
        try:
            LA.decide(db(), key, decision="approved", **kw)
        except LA.Refused:
            pass
        else:
            raise AssertionError(f"decide accepted {kw}")
    assert AA.judge(key)["eligible"] is True
    assert (cards(), approvals()) == before


def test_3_the_step_up_is_required():
    _no_stepup_is_refused()


def test_4_a_mutation_that_skips_the_step_up_fails_the_step_up_test():
    from brambleloop.app.command_center import auth

    real = auth.require_stepup
    try:
        auth.require_stepup = lambda *_a, **_k: None        # the mutant: no step-up asked
        try:
            _no_stepup_is_refused()
        except AssertionError:
            pass
        else:
            raise AssertionError("skipping the step-up was not detected")
    finally:
        auth.require_stepup = real
        restore()
    # the module-level guard alone also kills a mutant that hands step_up=True blindly
    from brambleloop.visual import laura_approval as LA

    src = Path(LA.__file__).read_text()
    assert 'if step_up is not True:' in src


# ---- B: the approval covers exactly the approved hashes --------------------------------------

def test_5_approval_through_the_route_covers_exactly_the_approved_hashes():
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import laura_approval as LA
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    restore()
    g = gallery()
    key = cards()[0][1]
    shas = laura_shas()
    c, csrf = session()                     # login is a fresh passphrase + TOTP step-up
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "approved", "note": "looked at both"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["decided"] and set(out["frames"]) == shas, out
    rows = approvals()
    assert {(rk, sha) for rk, sha, *_ in rows} == {(g["key"], s) for s in shas}, rows
    assert all(d == "approved" and su is True and via == "route" and by.startswith("owner:cc:")
               for _rk, _sha, d, su, via, by in rows), rows
    # PASS for exactly those hashes in exactly this gallery; UNMEASURED for anything else
    for sha in shas:
        assert LA.approved(db(), g["key"], sha)
        assert not LA.approved(db(), g["key"] + ":other", sha)
    assert not LA.approved(db(), g["key"], "f" * 64)
    st = GP.gallery_status(db(), g["key"])
    pubs = [f["gates"]["laura_publication"]["status"] for f in st["frames"]
            if f.get("laura_present")]
    assert pubs and set(pubs) == {"PASS"}, pubs
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db().session() as s:
        others = [r for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.laura_present.is_(True), ImageCandidate.run_key == g["key"]))
            if r.sha256 and r.sha256 not in shas]
        for r in others:
            s.expunge(r)
    for row in others:                       # an earlier attempt's Laura bytes: not approved
        m = GP.frame_matrix(db(), row, job="LIFESTYLE", laura_expected=True)
        assert m["gates"]["laura_publication"]["status"] == "UNMEASURED", m["gates"]
    # The approval re-judged the gallery: certified, complete, no extra paid call.
    assert out["recertified"]["certified"] is True, out
    assert any(n == CAMPAIGN_MIN_FRAMES for _i, n in valid_certs()), valid_certs()
    # Audited: the decision, the card's lifecycle, the route's action record.
    dec = audits(LA.AUDIT_DECIDED)
    assert len(dec) == 1 and dec[0][1]["step_up"] is True and dec[0][1]["via"] == "route"
    assert dec[0][0].startswith("owner:cc:") and set(
        f["sha256"] for f in dec[0][1]["frames"]) == shas
    life = [d for _a, d in audits("owner_action.lifecycle") if d.get("requirement_key") == key]
    assert life and life[-1]["to"] == "satisfied", life
    assert cards()[0][2] == "satisfied"
    # Answered: a second decision is refused, and no second card is raised.
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "rejected"})
    assert r.status_code == 409, r.text
    assert LA.raise_card(db(), g["key"])["raised"] is False and len(cards()) == 1


# ---- F: the first-customer imagery area ------------------------------------------------------

def _clone_cert(drop: int | None = None, mutate=None) -> int:
    """A new valid certificate record copied from the 7-frame one (a test-only tamper)."""
    from sqlalchemy import desc, select

    from brambleloop.core.models import ListingSetCertificateRecord

    with db().session() as s:
        src = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == E.SLUG,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        cert = dict(src.certificate)
        frames = [dict(f) for f in cert["frames"]]
        if drop is not None:
            frames = [f for f in frames if int(f["position"]) != drop]
        if mutate is not None:
            mutate(frames)
        cert["frames"] = frames
        cols = {c.name: getattr(src, c.name) for c in src.__table__.columns
                if c.name not in ("id",)}
        cols["certificate"] = cert
        row = ListingSetCertificateRecord(**cols)
        s.add(row)
        s.flush()
        return row.id


def test_6_a_certified_seven_frame_gallery_passes_imagery_and_six_frames_fail():
    from brambleloop.gates import first_customer as FC

    restore()
    key = cards()[0][1]
    c, csrf = session()
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "approved"})
    assert r.status_code == 200 and r.json()["recertified"]["certified"], r.text
    got = FC.disclosed_imagery(db(), E.SLUG, E.VERSION)
    assert got["state"] == FC.PASS, got
    assert "7 frames" in got["detail"] and "generated" in got["detail"], got
    check = FC.check_imagery(None, None, None, got)
    assert check.state == FC.PASS, check
    # 6 frames: gallery incomplete
    _clone_cert(drop=4)
    got6 = FC.disclosed_imagery(db(), E.SLUG, E.VERSION)
    assert got6["state"] == FC.FAIL and "gallery incomplete" in got6["detail"], got6
    restore()


def test_7_imagery_keeps_its_truth_and_disclosure_checks_on_the_generated_gallery():
    from brambleloop.gates import first_customer as FC
    from brambleloop.publish import release_gates as RG

    restore()
    key = cards()[0][1]
    c, csrf = session()
    assert post(c, csrf, "/api/cc/laura-gallery/decide",
                {"requirement_key": key, "decision": "approved"}).status_code == 200
    assert FC.disclosed_imagery(db(), E.SLUG, E.VERSION)["state"] == FC.PASS

    def strip_label(frames):
        for f in frames:
            if f.get("kind") == RG.GENERATED_RENDER_KIND:
                f["honesty_label"] = ""
                break
    _clone_cert(mutate=strip_label)
    got = FC.disclosed_imagery(db(), E.SLUG, E.VERSION)
    assert got["state"] == FC.FAIL and "disclosure" in got["detail"], got
    restore()
    # Without the owner's Laura approval the gallery is not certified, so imagery is still
    # judged as the disclosed set (and FAILs on the complete-gallery standard downstream).
    assert FC.generated_gallery_imagery(db(), E.SLUG, E.VERSION) is None
    # A frame that no longer re-judges as exportable (approval withdrawn: Laura's bytes no
    # longer approved for this run) FAILs a generated certificate.
    assert post(*session(), "/api/cc/laura-gallery/decide",
                {"requirement_key": key, "decision": "approved"}).status_code == 200
    with patch("brambleloop.visual.laura_approval.approved", lambda *_a, **_k: False):
        got = FC.disclosed_imagery(db(), E.SLUG, E.VERSION)
    assert got["state"] == FC.FAIL and "exportable" in got["detail"], got
    restore()


# ---- B: approve all, and rejection -----------------------------------------------------------

def test_8_approve_all_shows_the_frames_and_approves_them_with_its_step_up():
    from brambleloop.visual import laura_approval as LA

    restore()
    key = cards()[0][1]
    shas = laura_shas()
    c, csrf = session()
    pv = c.get("/api/cc/approve-all").json()
    item = next(e for e in pv["eligible"] if e["requirement_key"] == key)
    assert {f["sha256"] for f in item["frames"]} == shas and all(
        f["image_url"] for f in item["frames"]), item
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert any(a["requirement_key"] == key for a in out["approved"]), out
    assert out["laura_galleries"][gallery()["key"]]["certified"] is True, out
    rows = approvals()
    assert {sha for _rk, sha, *_ in rows} == shas and all(
        via == "approve_all" and su is True for *_x, su, via, _by in rows), rows
    assert [d["via"] for _a, d in audits(LA.AUDIT_DECIDED)] == ["approve_all"]
    row_audits = [d for _a, d in audits("owner_action.approve_all")
                  if d.get("requirement_key") == key]
    assert len(row_audits) == 1 and row_audits[0]["step_up"] is True, row_audits
    restore()


def test_9_a_rejection_is_recorded_and_leaves_laura_unmeasured():
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import laura_approval as LA

    restore()
    key = cards()[0][1]
    c, csrf = session()
    r = post(c, csrf, "/api/cc/laura-gallery/decide",
             {"requirement_key": key, "decision": "rejected"})
    assert r.status_code == 200, r.text
    assert {d for _rk, _sha, d, *_ in approvals()} == {"rejected"}
    st = GP.gallery_status(db(), gallery()["key"])
    assert {f["gates"]["laura_publication"]["status"] for f in st["frames"]
            if f.get("laura_present")} == {"UNMEASURED"}
    assert all(n < 7 for _i, n in valid_certs())
    assert LA.raise_card(db(), gallery()["key"])["raised"] is False and len(cards()) == 1
    restore()


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
