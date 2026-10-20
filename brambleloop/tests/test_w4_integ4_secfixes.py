"""W4-INTEG4: fixes for the independent security review of 7f6dbe8 (B1 BLOCKER, L1-L4 LOW).

B1  the public `/api/model-tournament/image/{sha}` served ANY stored artifact by digest, and the
    public `/api/audit` handed out the digests of the certified pattern PDFs, which this
    release keeps durably in Postgres. Now the image route is an allowlist (reference-pack
    keep rows and digests a recorded tournament / reference-pack package names, image bytes
    only) and the public audit view shortens every 64-hex digest.
L1  `/api/cc/images/runs/restart` requires step-up.
L2  the experiment's in-code price is the gateway's own reservation price.
L3  the Etsy upload path checks every certified frame for an experiment output, and the image
    check fails closed when the run table cannot be read.
L4  retention re-reads protection just before it deletes.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_integ4_secfixes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import inspect
import io
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w4_integ4_sec_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.models import AuditLog, DurableArtifact  # noqa: E402

OPS = "z" * 40
PASS = "owner passphrase for the integ4 security harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
PDF = b"%PDF-1.7\n" + b"certified paid pattern " * 40


def _png(colour=(36, 74, 58)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), colour).save(buf, format="PNG")
    return buf.getvalue()


def _client():
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def _audit(action, detail, artifact=None):
    with DB.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail))


def _image(c, sha):
    return c.get(f"/api/model-tournament/image/{sha}")


# ---- B1 ----------------------------------------------------------------------------------

def test_b1_a_kept_customer_pdf_is_never_served_even_after_a_redeploy():
    from brambleloop.commerce import deliverables

    stored = ArtifactStore().put("pdf/US.pdf", PDF, "application/pdf", db=DB,
                                 keep=deliverables.keep_why("wrap", "1.0.0", "pdf:US"))
    assert stored.durable
    _audit("assets.built", {"pdfs": {"US": {"sha256": stored.sha256}}}, "wrap@1.0.0")
    c = _client()
    r = _image(c, stored.sha256)
    assert r.status_code == 404 and b"%PDF" not in r.content, r.status_code
    # After a simulated redeploy (disk gone) it is still refused: Postgres is not a back door.
    Path(stored.path).unlink()
    r = _image(c, stored.sha256)
    assert r.status_code == 404 and b"%PDF" not in r.content
    # And the public audit trail no longer carries the address.
    rows = c.get("/api/audit?action=assets.built").json()["audit"]
    assert rows, "the row is there"
    blob = str(rows)
    assert stored.sha256 not in blob and stored.sha256[:12] + "…" in blob


def test_b1_a_pdf_named_by_a_tournament_package_is_still_not_served():
    stored = ArtifactStore().put("tournament/x.png", PDF + b"x", "image/png")
    from brambleloop.visual import tournament

    _audit(tournament.TOURNAMENT_ACTION, {"finalists": [{"image": {"sha256": stored.sha256}}]})
    r = _image(_client(), stored.sha256)
    assert r.status_code == 404 and b"%PDF" not in r.content, "bytes must be an image"


def test_b1_a_tournament_render_and_the_reference_pack_are_still_served():
    from brambleloop.visual import reference_pack, tournament

    tmp = Path(tempfile.mkdtemp()) / "finalist.png"
    tmp.write_bytes(_png((200, 10, 10)))
    kept = tournament._keep(str(tmp))
    _audit(tournament.TOURNAMENT_ACTION, {"brief_fingerprint": "t",
                                          "finalists": [{"image": kept}]})
    c = _client()
    r = _image(c, kept["sha256"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert "public" not in r.headers["cache-control"]
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.content == tmp.read_bytes()

    ref = Path(tempfile.mkdtemp()) / "ref.png"
    ref.write_bytes(_png((10, 200, 10)))
    pack = tournament._keep(str(ref), db=DB, why=reference_pack.KEEP_REASON)
    Path(ArtifactStore().root / pack["sha256"][:2] / pack["sha256"]).unlink()  # redeploy
    r = _image(c, pack["sha256"])
    assert r.status_code == 200 and r.content == ref.read_bytes(), r.status_code


def test_b1_an_image_no_package_names_or_kept_for_another_purpose_is_refused():
    from brambleloop.visual import experiment as XP

    c = _client()
    loose = ArtifactStore().put("chart/c.png", _png((1, 2, 3)), "image/png")
    assert _image(c, loose.sha256).status_code == 404, "a chart/frame on disk is not served"
    exp = ArtifactStore().put("exp/e.png", _png((4, 5, 6)), "image/png", db=DB,
                              keep=f"{XP.LABEL}; exp-x")
    # Even a package naming it does not override a keep row for another purpose.
    from brambleloop.visual import tournament

    _audit(tournament.TOURNAMENT_ACTION, {"finalists": [{"image": {"sha256": exp.sha256}}]})
    assert _image(c, exp.sha256).status_code == 404
    assert _image(c, "G" * 64).status_code == 400
    assert _image(c, "a" * 63).status_code == 400


def test_b1_the_route_fails_closed_when_state_cannot_be_read():
    real = main.db.session

    def broken():
        raise RuntimeError("database unavailable")

    main.db.session = broken
    try:
        assert main.tournament_image_refusal("a" * 64) is not None
    finally:
        main.db.session = real


def test_b1_the_operator_reads_the_audit_digests_unchanged():
    sha = hashlib.sha256(b"operator-visible").hexdigest()
    _audit("integ4.digest_probe", {"sha256": sha, "text": f"made {sha} today"})
    c = _client()
    pub = c.get("/api/audit?action=integ4.digest_probe").json()["audit"][0]["detail"]
    assert pub == {"sha256": sha[:12] + "…", "text": f"made {sha[:12]}… today"}, pub
    op = c.get("/api/audit?action=integ4.digest_probe",
               headers={"Authorization": f"Bearer {OPS}"}).json()["audit"][0]["detail"]
    assert op == {"sha256": sha, "text": f"made {sha} today"}
    # Shorter hex (a 12-char prefix, a 40-char git sha) is left alone.
    assert main._shorten_digests("b931d17a738d6a5bcd96580f620069b669ca5f57") == \
        "b931d17a738d6a5bcd96580f620069b669ca5f57"


def test_i7_the_public_audit_shortens_glued_digests_and_the_artifact_column():
    a, b = hashlib.sha256(b"one").hexdigest(), hashlib.sha256(b"two").hexdigest()
    _audit("integ4.glued_probe", {"blob": f"ab{a}{b}", "upper": a.upper()}, artifact=a)
    row = _client().get("/api/audit?action=integ4.glued_probe").json()["audit"][0]
    text = str(row)
    for d in (a, b, a.upper()):
        assert d not in text, d
    assert row["artifact"] == a[:12] + "…"


def test_i8_the_owner_fingerprint_is_domain_separated():
    from brambleloop.gateway import credentials as CR

    key = "bfl-sk-" + "x" * 30
    fp = CR.fingerprint(key)
    assert fp["last4"] == "xxxx" and len(fp["sha256_prefix"]) == 12
    assert fp["sha256_prefix"] != hashlib.sha256(key.encode()).hexdigest()[:12]
    assert key not in str(fp)


# ---- L1 ----------------------------------------------------------------------------------

def _session(c):
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _post(c, csrf, path, body=None):
    return c.post(path, json=body or {}, headers={
        "X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
        "X-CC-Timestamp": str(int(time.time()))})


def test_l1_restart_requires_step_up():
    from datetime import timedelta

    from sqlalchemy import select

    from brambleloop.app.command_center.models import OwnerSession

    c = _client()
    csrf = _session(c)                      # a fresh login carries a step-up window ...
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:                 # ... which is expired here
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))
    r = _post(c, csrf, "/api/cc/images/runs/restart", {"run_key": "no-such-run"})
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, (r.status_code, r.text)
    assert _post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = _post(c, csrf, "/api/cc/images/runs/restart", {"run_key": "no-such-run"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert not r.json().get("data", r.json()).get("restarted"), "an unknown run is refused"


# ---- L2 ----------------------------------------------------------------------------------

def test_l2_the_experiment_reserves_the_gateway_price_never_below_the_table():
    from brambleloop.experiments import controlled as C
    from brambleloop.gateway import images as I

    for model, size in (("flux-2-pro", "2048x2048"), ("flux-2-pro", "1024x1024"),
                        ("flux-3-image", "2048x2048")):
        p = I.BY_KEY[model]
        gw = round(I.render_estimate_usd(p, size, [])["usd"] * I.USD_TO_CAD, 6)
        got = C._price_cad(model, size, [])
        assert got >= p.cad_per_image and abs(got - max(gw, p.cad_per_image)) < 1e-6, \
            (model, size, got, gw)
    # 4 MP FLUX.2 costs more than its 1 MP table price: the old check under-reserved here.
    assert C._price_cad("flux-2-pro", "2048x2048") > I.BY_KEY["flux-2-pro"].cad_per_image
    assert "_price_cad(model, size, refs)" in inspect.getsource(C)


# ---- L3 ----------------------------------------------------------------------------------

def test_l3_the_upload_path_checks_every_frame_and_the_check_fails_closed():
    from brambleloop.runtime import etsy_ops
    from brambleloop.visual import experiment as XP

    src = inspect.getsource(etsy_ops.certified_images)
    assert "refuse_if_experiment_image(" in src and 'cert["frames"]' in src

    class Broken:
        def session(self):
            raise RuntimeError("run table unreadable")

    try:
        XP.refuse_if_experiment_image(Broken(), ["a" * 64], action="listing image upload")
        raise AssertionError("an unreadable run table must refuse publication")
    except XP.ExperimentRefused as exc:
        assert "unreadable" in str(exc)
    XP.refuse_if_experiment_image(Broken(), [], action="listing image upload")  # nothing to do
    XP.refuse_if_experiment_image(DB, ["b" * 64], action="listing image upload")  # readable


# ---- L4 ----------------------------------------------------------------------------------

def test_l4_prune_rereads_protection_before_it_deletes():
    from brambleloop.commerce import deliverables as D

    a, b = "1" * 64, "2" * 64
    with DB.session() as s:
        for sha in (a, b):
            s.add(DurableArtifact(sha256=sha, content_type="application/pdf", bytes_len=3,
                                  payload=b"abc", why_kept=D.KEEP_PREFIX + "x"))
    plans = iter([
        {"prune": [{"sha256": a, "bytes": 3, "why_kept": D.KEEP_PREFIX},
                   {"sha256": b, "bytes": 3, "why_kept": D.KEEP_PREFIX}],
         "prune_bytes": 6, "kept_rows": 2, "protected_releases": [], "keep_previous": 2},
        # Between the two readings, b's release was listed: it is now protected.
        {"prune": [{"sha256": a, "bytes": 3, "why_kept": D.KEEP_PREFIX}],
         "prune_bytes": 3, "kept_rows": 2, "protected_releases": ["x@1"], "keep_previous": 2},
    ])
    real = D.retention_plan
    D.retention_plan = lambda db, keep_previous=D.KEEP_PREVIOUS: next(plans)
    try:
        out = D.prune(DB)
    finally:
        D.retention_plan = real
    assert out["pruned"] == 1 and out["bytes"] == 3, out
    with DB.session() as s:
        assert s.get(DurableArtifact, a) is None
        assert s.get(DurableArtifact, b) is not None, "protected since the first reading"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
            traceback.print_exc(limit=5)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
