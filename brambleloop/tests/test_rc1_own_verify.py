"""A3-10: /api/verify's publication checks are phase-aware and see draft writes."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

SHADOW_NAMES = ["phase_is_shadow", "nothing_published", "no_revenue_claimed"]
LIVE_NAMES = ["phase_is_recorded_and_agrees",
              "everything_published_is_certified_granted_and_read_back",
              "revenue_only_with_order_evidence"]


def _db():
    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp(prefix="rc1own-verify-")
    db = Database(f"sqlite:///{tmp}/v.db")
    db.create_all()
    return tmp, db


def _phase(effective, agree=True):
    def fake(db, env):
        return {"phase": effective, "env": effective, "env_phase": effective,
                "recorded_phase": effective if agree else "shadow", "agree": agree,
                "why": "test"}
    return fake


def _run(db, effective, agree=True):
    from brambleloop.app import verify_checks as vc

    orig = vc._phase
    vc._phase = _phase(effective, agree)
    try:
        out = vc.publication_checks(db)
    finally:
        vc._phase = orig
    return [out["phase"], out["published"], out["revenue"]]


def _audit(db, action, artifact="", detail=None):
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail or {}))


def _released_listing(db, slug="hat", version="1.0.0", certified=True, etsy_id="999"):
    from brambleloop.core.models import Listing, PatternVersion, Product

    with db.session() as s:
        p = Product(slug=slug, title=slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={},
                             certified=certified))
        s.add(Listing(product_slug=slug, version=version, title="t", description="d",
                      etsy_listing_id=etsy_id, state="published"))


def test_shadow_names_unchanged_and_green_when_nothing_written():
    tmp, db = _db()
    try:
        checks = _run(db, "shadow")
        assert [c["check"] for c in checks] == SHADOW_NAMES
        assert all(c["ok"] for c in checks), checks
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_shadow_sees_draft_writes():
    for write in ("incomplete", "exercise", "intent", "listing"):
        tmp, db = _db()
        try:
            if write == "incomplete":
                _audit(db, "store.publish_incomplete", "hat@1.0.0", {"etsy_listing_id": "5"})
            elif write == "exercise":
                _audit(db, "etsy.exercise_draft_created", "", {"listing_id": "123"})
            elif write == "intent":
                from brambleloop.publish.draft_intent import DraftIntent

                with db.session() as s:
                    s.add(DraftIntent(key="k" * 64, slug="hat", version="1.0.0", release="r",
                                      content_digest="d", token="t", state="CREATING",
                                      detail={}))
            else:
                _released_listing(db)
            checks = _run(db, "shadow")
            pub = checks[1]
            assert pub["check"] == "nothing_published"
            assert pub["ok"] is False, (write, pub)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # A matched exercise round trip (created and removed) left nothing on Etsy.
    tmp, db = _db()
    try:
        _audit(db, "etsy.exercise_draft_created", "", {"listing_id": "7"})
        _audit(db, "etsy.exercise_draft_removed", "", {"listing_id": "7"})
        assert _run(db, "shadow")[1]["ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live_phase_is_not_permanently_red_and_checks_proof():
    tmp, db = _db()
    try:
        _released_listing(db)
        _audit(db, "store.execution_revalidated", "hat@1.0.0",
               {"owner_publication_grant": "g-1"})
        _audit(db, "store.published", "hat@1.0.0",
               {"etsy_listing_id": "999", "read_back": {"verified": True}})
        from brambleloop.core.models import LedgerEntry

        with db.session() as s:
            s.add(LedgerEntry(category="sale", gross_cad=12.0, evidence_ref="etsy:receipt:1"))
        for phase in ("limited_production", "production"):
            checks = _run(db, phase)
            assert [c["check"] for c in checks] == LIVE_NAMES
            assert all(c["ok"] for c in checks), checks
        # Same rows under shadow are (correctly) red: something is on Etsy.
        assert _run(db, "shadow")[1]["ok"] is False
        # env/record disagreement is red in a live phase
        assert _run(db, "limited_production", agree=False)[0]["ok"] is False
        # revenue without its order evidence is red
        with db.session() as s:
            s.add(LedgerEntry(category="sale", gross_cad=5.0, evidence_ref=""))
        assert _run(db, "production")[2]["ok"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live_phase_red_without_grant_readback_or_certificate_or_with_stranded_draft():
    cases = {
        "no_grant": dict(grant=False, readback=True, certified=True, stranded=False),
        "no_readback": dict(grant=True, readback=False, certified=True, stranded=False),
        "uncertified": dict(grant=True, readback=True, certified=False, stranded=False),
        "stranded": dict(grant=True, readback=True, certified=True, stranded=True),
    }
    assert len(cases) == 4
    for name, c in cases.items():
        tmp, db = _db()
        try:
            _released_listing(db, certified=c["certified"])
            if c["grant"]:
                _audit(db, "store.execution_revalidated", "hat@1.0.0",
                       {"owner_publication_grant": "g-1"})
            _audit(db, "store.published", "hat@1.0.0",
                   {"read_back": {"verified": c["readback"]}})
            if c["stranded"]:
                _audit(db, "etsy.exercise_draft_created", "", {"listing_id": "55"})
            pub = _run(db, "limited_production")[1]
            assert pub["ok"] is False, (name, pub)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def test_verify_endpoint_uses_the_effective_phase_module():
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "brambleloop", "app",
                            "main.py")).read()
    body = src[src.index("def api_verify"):src.index("def api_verify") + 3000]
    assert 'os.environ.get("BRAMBLELOOP_PHASE", "shadow")' not in body
    assert "verify_checks.publication_checks(db)" in body


if __name__ == "__main__":
    # One `OK  <name>` / `FAIL <name>` line per test, in definition order, and a nonzero exit
    # on any failure: run_tests.sh counts ^OK lines, so a bare trailing "suite: OK" line would
    # leave every pass here out of the total.
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
