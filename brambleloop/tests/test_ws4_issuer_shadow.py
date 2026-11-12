"""WS4-5: the standing-policy issuer in SHADOW (design §3.3, §9 M6 increment 5).

The shadow issuer evaluates certified releases against the owner's approved policy and
records what it WOULD do. It never signs and never issues. Readers the next increment builds
read UNKNOWN, so today every decision is HOLD with those reasons named.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core import owner_grant_keys  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, PatternVersion, Product  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_policy_object import NOW, _approve, _db, _restore, content  # noqa: E402

SLUG, VERSION = "shadow-coaster", "1.0.0"


def _release(db, *, slug=SLUG, release="a" * 64, on_etsy=""):
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == slug))
        if p is None:
            p = Product(slug=slug, title="Shadow Coaster")
            s.add(p)
            s.flush()
        s.add(PatternVersion(product_id=p.id, version=VERSION, cir_json={}, certified=True,
                             release_hash=release, certificate={"granted": True}))
        s.add(Listing(product_slug=slug, version=VERSION, title="Shadow Coaster",
                      description="plain", tags=["coaster"], price_cad=8.0,
                      release_hash=release, etsy_listing_id=on_etsy))


def _rows(db):
    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
            AuditLog.action == sp.SHADOW_DECISION).order_by(AuditLog.id))]


def test_with_no_approved_policy_nothing_is_recorded():
    try:
        db = _db()
        _release(db)
        out = SI.shadow_run(db, now=NOW)
        assert out["policy"] is None and out["recorded"] == 0 and _rows(db) == [], out
    finally:
        _restore()


def test_an_approved_policy_is_shadowed_and_every_decision_holds_today():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _release(db)
        out = SI.shadow_run(db, now=NOW)
        assert out["policy"] == c["policy_id"] and out["approval_id"] == a, out
        assert out["evaluated"] == 1 and out["recorded"] == 1 and out["would_issue"] == 0
        assert out["signed"] == 0 and out["issued"] == 0
        rows = _rows(db)
        assert len(rows) == 1
        row = rows[0]
        assert row["decision"] == "HOLD" and row["signed"] is False and row["shadow"] is True
        assert row["slug"] == SLUG and row["release"] == "a" * 64 and row["approval_id"] == a
        assert sorted(row["assumed"]) == sorted(SI.ASSUMED_IN_SHADOW)
        for name in SI.NOT_BUILT_YET:
            assert any(r.startswith(f"{name}: UNKNOWN") for r in row["reasons"]), name
        # The activation precondition that needs a shadow decision is now satisfied.
        why = sp.activation_refusals(db, a, now=NOW + timedelta(days=30))
        assert not any("shadow decision" in w for w in why), why
    finally:
        _restore()


def test_the_shadow_run_never_signs_or_issues():
    """Signing raises if attempted: the run completes and only decision rows appear."""
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db)
        with db.session() as s:
            before = s.scalar(select(func.count()).select_from(AuditLog))

        def no_signing(*_a, **_k):
            raise AssertionError("the shadow issuer tried to sign")

        with patch.object(sp, "_sign", no_signing), \
                patch.object(owner_grant_keys, "sign", no_signing):
            out = SI.shadow_run(db, now=NOW)
        with db.session() as s:
            new = list(s.scalars(select(AuditLog.action).where(AuditLog.id > before)))
        assert out["recorded"] == 1 and set(new) <= {sp.SHADOW_DECISION, "experiment.refused"}, \
            new
    finally:
        _restore()


def test_decisions_are_deduplicated_per_day_and_a_new_release_is_new():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db)
        assert SI.shadow_run(db, now=NOW)["recorded"] == 1
        assert SI.shadow_run(db, now=NOW + timedelta(hours=6))["recorded"] == 0
        _release(db, slug="shadow-placemat", release="b" * 64)
        assert SI.shadow_run(db, now=NOW + timedelta(hours=7))["recorded"] == 1
        assert len(_rows(db)) == 2
        # After the window the same decision is recorded again (one row per day).
        assert SI.shadow_run(db, now=NOW + timedelta(hours=25))["recorded"] == 1
    finally:
        _restore()


def test_a_listing_already_on_etsy_is_not_a_candidate():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db, on_etsy="1234567")
        assert SI.candidates(db) == []
        assert SI.shadow_run(db, now=NOW)["evaluated"] == 0
    finally:
        _restore()


def test_a_revoked_or_expired_policy_is_not_shadowed():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _release(db)
        assert SI.shadow_policy(db, now=NOW)["approval_id"] == a
        assert SI.shadow_policy(db, now=NOW + timedelta(days=400)) is None     # expired
        sp.revoke(db, a)
        assert SI.shadow_policy(db, now=NOW) is None
        assert SI.shadow_run(db, now=NOW)["recorded"] == 0
    finally:
        _restore()


def test_a_reader_that_raises_reads_unknown_and_holds():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db)
        with patch.object(SI, "_category", side_effect=RuntimeError("boom")):
            SI.shadow_run(db, now=NOW)
        row = _rows(db)[0]
        assert row["decision"] == "HOLD" and row["fact_states"]["category"] == SB.UNKNOWN
        assert any("category: UNKNOWN" in r and "RuntimeError" in r for r in row["reasons"])
    finally:
        _restore()


def test_with_every_fact_passing_the_shadow_decision_is_would_issue_and_still_unsigned():
    """The pipeline end to end: when every fact reads PASS (the next increment's readers
    stubbed here), the shadow decision is ISSUE -- recorded, never signed or issued."""
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db)

        def all_pass(db_, slug, version, release, content_, *, shadow=True):
            from test_ws4_boundary import facts

            return facts(slug=slug)

        with patch.object(SI, "read_facts", all_pass):
            out = SI.shadow_run(db, now=NOW)
        assert out["would_issue"] == 1 and out["signed"] == 0 and out["issued"] == 0, out
        row = _rows(db)[0]
        assert row["decision"] == "ISSUE" and row["class_id"] == "flat-colourwork-A"
        assert row["signed"] is False
    finally:
        _restore()


def test_the_job_is_registered_as_an_observe_cadence():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority.classes import JOB_CLASS, ActionClass
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import CADENCES, handlers

    assert JOB_CLASS["policy.issuer_shadow"] == ActionClass.OBSERVE
    assert any(job == "policy.issuer_shadow" for _c, _a, job, _p in CADENCES)
    assert handlers.get("policy.issuer_shadow") is not None
    publishing = next(a for a in DEFAULT_AGENTS if a["name"] == "publishing")
    assert "policy.issuer_shadow" in publishing["allowed_job_types"]


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
