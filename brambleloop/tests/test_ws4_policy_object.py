"""WS4-2: the standing publication policy object and its chain (design §7.1 T-PO, T-CH).

Every key used here is generated in this process for this test only: no deployment secret is
read, and nothing is written outside the scratch database.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import owner_grant_keys  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
_SAVED = {}


def _keys():
    """Fresh, distinct keys for this process; restored by `_restore`."""
    pairs = sp.generate_keypairs()
    env = {sp.SIGNING_KEY_VAR: pairs[sp.SIGNING_KEY_VAR],
           sp.VERIFY_KEY_VAR: pairs[sp.VERIFY_KEY_VAR],
           sp.EMBEDDED_VAR: "0",
           "BRAMBLELOOP_OPS_TOKEN": "ws4-2-fixture-ops-token-" + uuid.uuid4().hex}
    for k, v in env.items():
        _SAVED.setdefault(k, os.environ.get(k))
        os.environ[k] = v
    sp._JOB_PROCESS["is"] = False
    return env


def _restore():
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    sp._JOB_PROCESS["is"] = False


def _db() -> Database:
    _keys()
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/sp.sqlite", scratch=True)
    db.create_all()
    return db


def content(**over) -> dict:
    c = {
        "schema": sp.SCHEMA, "policy_id": f"sp-{uuid.UUID(int=7, version=4)}", "version": 1,
        "supersedes": None, "actions": ["store.publish"],
        "etsy": {"shop_id": "12345678", "shop_name": "BrambleloopStudio"},
        "product_classes": [{
            "class_id": "flat-colourwork-A", "categories": ["coaster", "placemat"],
            "max_effective_risk_class": "A", "physical_required": "partial_physical",
            "price_band_cad": [4.00, 12.00], "max_sizes": 1, "colourwork_allowed": True,
            "wearable_allowed": False}],
        "exclusions": {"launch0_slugs": "ALWAYS", "slugs": [],
                       "categories": ["garment", "amigurumi"]},
        "required_certifications": sorted(sp.REQUIRED_CERTIFICATIONS_FLOOR),
        "evidence": {"rollback_rehearsal_max_age_days": 14, "policy_reading_max_age_days": 7,
                     "vision_reviewer_must_differ_from_generator": True,
                     "min_shadow_days_before_activation": 7},
        "frequency": {"max_per_day": 2, "max_per_7d": 6, "min_spacing_minutes": 180,
                      "max_outstanding_unconsumed_grants": 1},
        "spend": {"max_listing_fees_cad_per_30d": 0.00, "ads": "NONE"},
        "stop_conditions": {"open_defect_incident_on_policy_product": 1,
                            "refunds_7d_count": 2, "refund_rate_30d_pct": 10.0,
                            "etsy_policy_notice_any": True, "dead_letters_60m": 5,
                            "open_p0_any": True, "authority_tamper_any": True,
                            "publish_incomplete_any": True,
                            "census_drift_on_policy_listing": True,
                            "stop_watch_max_silence_minutes": 30},
        "validity": {"not_before": "2026-11-20T00:00:00+00:00",
                     "review_by": "2027-01-18T00:00:00+00:00",
                     "expires_at": "2027-02-17T00:00:00+00:00"},
        "owner_statement_digest": "0" * 64, "code_ceilings_version": sp.CEILINGS_VERSION}
    for k, v in over.items():
        c[k] = v
    c["owner_statement_digest"] = sp.statement_digest(c)
    return c


def _approve(db, c, *, now=NOW, **over):
    kw = dict(digest=sp.statement_digest(c), typed_confirmation=sp.confirmation_phrase(c),
              stepped_up=True, owner_session="sess-1", actor="owner", reason="test policy",
              now=now)
    kw.update(over)
    with owner_grant_keys.owner_request("sess-1"):
        return sp.approve(db, c, **kw)


def _refused(fn, *a, contains=None, **k):
    try:
        fn(*a, **k)
    except ValueError as exc:
        assert contains is None or contains in str(exc), (contains, str(exc))
        return str(exc)
    raise AssertionError(f"{getattr(fn, '__name__', fn)} was not refused")


def _activate_raw(db, approval_id, c):
    """Write an activation row directly (Mode T does not exist yet, so `activate` always
    refuses); used only to exercise `effective()` and the chain."""
    with owner_grant_keys.owner_request("sess-1"):
        return sp.LEDGER.append(db, action=sp.ACTIVATED, artifact=c["policy_id"], detail={
            "principal": sp.PRINCIPAL, "actor": "owner", "owner_session": "sess-1",
            "stepped_up": True, "approval_id": approval_id, "policy_id": c["policy_id"],
            "version": c["version"], "activated_at": NOW.isoformat()})


class _ModeT:
    def __enter__(self):
        self.orig = sp.deployment_mode
        sp.deployment_mode = lambda: "T"

    def __exit__(self, *a):
        sp.deployment_mode = self.orig


# ------------------------------------------------------------------------------- T-PO-1

def test_t_po_1_approve_refuses_without_owner_request_stepup_confirmation_or_digest():
    try:
        db, c = _db(), content()
        kw = dict(digest=sp.statement_digest(c), typed_confirmation=sp.confirmation_phrase(c),
                  stepped_up=True, owner_session="s", actor="owner", reason="r", now=NOW)
        _refused(sp.approve, db, c, **kw, contains="Command Center request")   # no request
        with owner_grant_keys.owner_request("s"):
            _refused(sp.approve, db, c, **{**kw, "stepped_up": False}, contains="step-up")
            _refused(sp.approve, db, c, **{**kw, "typed_confirmation": "AUTHORISE"},
                     contains="type exactly")
            _refused(sp.approve, db, c, **{**kw, "digest": "f" * 64},
                     contains="digest mismatch")
            stale = {**c, "owner_statement_digest": "e" * 64}
            _refused(sp.approve, db, stale, **kw, contains="digest mismatch")
            _refused(sp.approve, db, c, **{**kw, "reason": " "}, contains="reason")
        with db.session() as s:
            assert s.scalar(select(AuditLog.id).where(AuditLog.action == sp.APPROVED)) is None
        ident = _approve(db, c)
        assert ident and sp.LEDGER.refusal(db, ident) is None
    finally:
        _restore()


def test_t_po_1_the_signer_itself_refuses_outside_the_owner_request():
    """Mutant M16: even a direct LEDGER.append of an approval is refused outside the request."""
    try:
        db, c = _db(), content()
        _refused(sp.LEDGER.append, db, action=sp.APPROVED, artifact=c["policy_id"],
                 detail={"content": c}, contains="Command Center request")
        for action in (sp.ACTIVATED, sp.RESUMED):
            _refused(sp.LEDGER.append, db, action=action, artifact=c["policy_id"],
                     detail={"policy_id": c["policy_id"]}, contains="Command Center request")
        _refused(sp.LEDGER.rebase, db, "no request", contains="Command Center request")
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-PO-2

def _ceiling_cases():
    """(name, mutate) pairs: each exceeds exactly one code ceiling by the smallest step."""
    def cls(**kw):
        def f(c):
            c["product_classes"][0].update(kw)
        return f

    def sub(section, key, value):
        def f(c):
            c[section][key] = value
        return f

    return [
        ("max_per_day 4", sub("frequency", "max_per_day", sp.MAX_PER_DAY + 1)),
        ("max_per_7d 11", sub("frequency", "max_per_7d", sp.MAX_PER_7D + 1)),
        ("outstanding 3", sub("frequency", "max_outstanding_unconsumed_grants",
                              sp.MAX_OUTSTANDING + 1)),
        ("risk C", cls(max_effective_risk_class="C")),
        ("price floor", cls(price_band_cad=[0.99, 12.00])),
        ("price ceiling", cls(price_band_cad=[4.00, 40.01])),
        ("ads", sub("spend", "ads", "META")),
        ("fees", sub("spend", "max_listing_fees_cad_per_30d", 0.01)),
        ("actions", lambda c: c.__setitem__("actions", ["store.publish", "store.activate"])),
        ("launch0", sub("exclusions", "launch0_slugs", "NEVER")),
        ("shadow 6 days", sub("evidence", "min_shadow_days_before_activation",
                              sp.MIN_SHADOW_DAYS - 1)),
        ("rollback age", sub("evidence", "rollback_rehearsal_max_age_days",
                             sp.MAX_ROLLBACK_REHEARSAL_AGE_DAYS + 1)),
        ("reading age", sub("evidence", "policy_reading_max_age_days",
                            sp.MAX_POLICY_READING_AGE_DAYS + 1)),
        ("vision", sub("evidence", "vision_reviewer_must_differ_from_generator", False)),
        ("review window", sub("validity", "review_by", "2027-02-18T00:00:01+00:00")),
        ("expiry window", sub("validity", "expires_at", "2027-02-17T00:00:01+00:00")),
        ("dropped certification", lambda c: c["required_certifications"].remove("rollback")),
        ("stop silence", sub("stop_conditions", "stop_watch_max_silence_minutes", 31)),
        ("stop refunds", sub("stop_conditions", "refunds_7d_count", 3)),
        ("stop boolean off", sub("stop_conditions", "open_p0_any", False)),
        ("unknown field", lambda c: c.__setitem__("extra", 1)),
        ("naive time", sub("validity", "not_before", "2026-11-20T00:00:00")),
    ]


def test_t_po_2_every_code_ceiling_exceeded_by_one_step_is_refused():
    try:
        db = _db()
        base = content()
        assert sp.ceiling_refusals(base) == [], sp.ceiling_refusals(base)
        # The boundary values themselves are accepted (the ceilings are inclusive).
        edge = content(frequency={"max_per_day": sp.MAX_PER_DAY, "max_per_7d": sp.MAX_PER_7D,
                                  "min_spacing_minutes": 0,
                                  "max_outstanding_unconsumed_grants": sp.MAX_OUTSTANDING})
        edge["product_classes"][0].update(max_effective_risk_class="B",
                                          price_band_cad=[1.00, 40.00])
        edge["validity"] = {"not_before": "2026-11-20T00:00:00+00:00",
                            "review_by": "2027-02-18T00:00:00+00:00",
                            "expires_at": "2027-03-20T00:00:00+00:00"}
        edge["owner_statement_digest"] = sp.statement_digest(edge)
        assert sp.ceiling_refusals(edge) == [], sp.ceiling_refusals(edge)
        for name, mutate in _ceiling_cases():
            c = copy.deepcopy(base)
            mutate(c)
            if "extra" not in c:
                c["owner_statement_digest"] = sp.statement_digest(c) if not sp.ceiling_refusals(
                    {**c, "owner_statement_digest": "0" * 64}) else "0" * 64
            assert sp.ceiling_refusals(c), name
            _refused(_approve, db, c, digest=("0" * 64), contains="code ceilings")
        with db.session() as s:
            assert s.scalar(select(AuditLog.id).where(AuditLog.action == sp.APPROVED)) is None
    finally:
        _restore()


def test_physical_vocabulary_is_the_risk_matrix_evidence_classes():
    from brambleloop.gates import risk_matrix

    for level in sp.PHYSICAL_ORDER[1:]:
        assert level in risk_matrix.CLASS_BY_KEY, level
    assert sp.PHYSICAL_ORDER[1:] == (risk_matrix.PARTIAL_PHYSICAL, risk_matrix.FULL_PHYSICAL_MAKE)


def test_seg_ttl_constant_is_within_its_ceiling():
    """Mutant M3 (TTL part): the SEG TTL constant may not exceed its ceiling."""
    assert 0 < sp.SEG_TTL_MINUTES <= sp.SEG_TTL_CEILING_MINUTES <= 30


def test_code_ceilings_are_the_values_main_approved():
    """Design §9 M5 approved these as drafted; a change is a reviewed code change, and this
    test is the review tripwire (it cannot be satisfied by moving a constant)."""
    assert (sp.MAX_PER_DAY, sp.MAX_PER_7D, sp.MAX_OUTSTANDING) == (3, 10, 2)
    assert (sp.SEG_TTL_MINUTES, sp.SEG_TTL_CEILING_MINUTES) == (15, 30)
    assert (sp.MAX_REVIEW_WINDOW_DAYS, sp.MAX_EXPIRY_AFTER_REVIEW_DAYS) == (90, 30)
    assert sp.MAX_RISK_CLASS == "B" and sp.ALLOWED_ACTIONS == frozenset({"store.publish"})
    assert (sp.PRICE_FLOOR_CAD, sp.PRICE_CEILING_CAD) == (1.00, 40.00)
    assert sp.MIN_SHADOW_DAYS == 7 and sp.MAX_LISTING_FEES_CAD_PER_30D == 0.00
    assert sp.MAX_STOP_WATCH_SILENCE_MINUTES == 30
    assert len(sp.REQUIRED_CERTIFICATIONS_FLOOR) == 14


def test_stored_content_is_rechecked_against_the_ceilings_at_every_read():
    """A row that reached the chain with over-ceiling content (an older code version, or a
    signer bypassing `approve`) is never effective."""
    try:
        db = _db()
        c = content(frequency={"max_per_day": 5, "max_per_7d": 6, "min_spacing_minutes": 0,
                               "max_outstanding_unconsumed_grants": 1})
        assert sp.ceiling_refusals(c)
        with owner_grant_keys.owner_request("s"):
            a = sp.LEDGER.append(db, action=sp.APPROVED, artifact=c["policy_id"], detail={
                "principal": sp.PRINCIPAL, "content": c, "digest": sp.statement_digest(c),
                "approved_at": NOW.isoformat()})
        _activate_raw(db, a, c)
        with _ModeT():
            e = sp.effective(db, now=NOW)
        assert e["state"] == sp.BROKEN and "code ceilings" in e["why"], e
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-PO-3

def test_t_po_3_version_gap_wrong_supersedes_and_only_newest_activation_is_effective():
    try:
        db, c1 = _db(), content()
        a1 = _approve(db, c1)
        with db.session() as s:
            seal1 = s.get(AuditLog, a1).detail["seal"]
        _refused(_approve, db, content(version=3, supersedes={"row_id": a1, "seal": seal1}),
                 contains="version must be 2")
        _refused(_approve, db, content(version=2, supersedes={"row_id": a1, "seal": "0" * 128}),
                 contains="supersedes must name")
        _refused(_approve, db, content(version=2, supersedes=None),
                 contains="supersedes must name")
        _refused(_approve, db, content(version=1), contains="version must be 2")
        other = content(policy_id=f"sp-{uuid.UUID(int=9, version=4)}", version=2)
        _refused(_approve, db, other, contains="version 1")
        c2 = content(version=2, supersedes={"row_id": a1, "seal": seal1})
        a2 = _approve(db, c2)
        _activate_raw(db, a1, c1)
        _activate_raw(db, a2, c2)
        with _ModeT():
            e = sp.effective(db, now=NOW + timedelta(days=1))
            assert e["state"] == sp.EFFECTIVE and e["approval_id"] == a2, e
            _activate_raw(db, a1, c1)          # re-activating v1 makes v1 the effective one
            e = sp.effective(db, now=NOW + timedelta(days=1))
            assert e["state"] == sp.EFFECTIVE and e["approval_id"] == a1, e
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-PO-4

def test_t_po_4_statement_is_deterministic_and_every_field_changes_the_digest():
    base = content()
    assert sp.render_statement(base) == sp.render_statement(copy.deepcopy(base))
    d0 = sp.statement_digest(base)
    changes = {
        "policy_id": f"sp-{uuid.UUID(int=8, version=4)}", "version": 2,
        "supersedes": {"row_id": 1, "seal": "a" * 128}, "etsy.shop_id": "87654321",
        "etsy.shop_name": "Other", "classes.class_id": "x", "classes.categories": ["placemat"],
        "classes.risk": "B", "classes.physical": "full_physical_make", "classes.lo": 4.01,
        "classes.hi": 11.99, "classes.max_sizes": 2, "classes.colourwork": False,
        "classes.wearable": True, "exclusions.slugs": ["s"], "exclusions.categories": [],
        "certs": sorted(sp.REQUIRED_CERTIFICATIONS_FLOOR) + ["extra_check"],
        "evidence.rollback": 13, "evidence.reading": 6, "evidence.shadow": 8,
        "frequency.day": 1, "frequency.7d": 5, "frequency.spacing": 181,
        "frequency.outstanding": 2, "stop.refunds": 1, "stop.silence": 29,
        "validity.not_before": "2026-11-21T00:00:00+00:00",
        "validity.review_by": "2027-01-17T00:00:00+00:00",
        "validity.expires_at": "2027-02-16T00:00:00+00:00",
    }
    for name, value in changes.items():
        c = copy.deepcopy(base)
        pc = c["product_classes"][0]
        if name in ("policy_id", "version", "supersedes"):
            c[name] = value
        elif name.startswith("etsy."):
            c["etsy"][name[5:]] = value
        elif name.startswith("classes."):
            key = {"class_id": "class_id", "categories": "categories",
                   "risk": "max_effective_risk_class", "physical": "physical_required",
                   "max_sizes": "max_sizes", "colourwork": "colourwork_allowed",
                   "wearable": "wearable_allowed"}.get(name[8:])
            if name.endswith(".lo"):
                pc["price_band_cad"] = [value, pc["price_band_cad"][1]]
            elif name.endswith(".hi"):
                pc["price_band_cad"] = [pc["price_band_cad"][0], value]
            else:
                pc[key] = value
        elif name.startswith("exclusions."):
            c["exclusions"][name[11:]] = value
        elif name == "certs":
            c["required_certifications"] = value
        elif name.startswith("evidence."):
            c["evidence"][{"rollback": "rollback_rehearsal_max_age_days",
                           "reading": "policy_reading_max_age_days",
                           "shadow": "min_shadow_days_before_activation"}[name[9:]]] = value
        elif name.startswith("frequency."):
            c["frequency"][{"day": "max_per_day", "7d": "max_per_7d",
                            "spacing": "min_spacing_minutes",
                            "outstanding": "max_outstanding_unconsumed_grants"}[name[10:]]] = value
        elif name.startswith("stop."):
            c["stop_conditions"][{"refunds": "refunds_7d_count",
                                  "silence": "stop_watch_max_silence_minutes"}[name[5:]]] = value
        elif name.startswith("validity."):
            c["validity"][name[9:]] = value
        assert sp.statement_digest(c) != d0, name
    phrase = sp.confirmation_phrase(base)
    assert phrase == f"AUTHORISE {base['policy_id']} v1 {d0[:8]}"


# ------------------------------------------------------------------------------- T-PO-5

def test_t_po_5_signing_refuses_with_the_embedded_worker_on_or_in_a_job_process():
    try:
        db, c = _db(), content()
        os.environ[sp.EMBEDDED_VAR] = "1"
        _refused(_approve, db, c, contains="EMBEDDED_WORKER")
        os.environ.pop(sp.EMBEDDED_VAR)      # unset means on (the default deployment)
        _refused(_approve, db, c, contains="EMBEDDED_WORKER")
        os.environ[sp.EMBEDDED_VAR] = "0"
        assert sp.mark_job_process() is True and sp.SIGNING_KEY_VAR not in os.environ
        _refused(_approve, db, c, contains="runs jobs")
        sp._JOB_PROCESS["is"] = False
        _refused(_approve, db, c, contains="signing key unavailable")   # scrubbed
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-PO-6

def test_t_po_6_a_key_shared_with_another_authority_is_not_configured():
    from brambleloop.ops import storefront_authority as sf

    try:
        env = _keys()
        assert sp.key_health()["configured"] is True, sp.key_health()
        other = sp.generate_keypairs()
        shared_cases = {
            "storefront signing": {sf.SIGNING_KEY_VAR: env[sp.SIGNING_KEY_VAR]},
            "storefront verify": {sf.VERIFY_KEY_VAR: env[sp.VERIFY_KEY_VAR]},
            "owner grant": {owner_grant_keys.SIGNING_KEY_VAR: env[sp.SIGNING_KEY_VAR]},
            "issuer": {sp.ISSUER_KEY_VAR: env[sp.SIGNING_KEY_VAR]},
            "issuer verify": {sp.ISSUER_VERIFY_KEY_VAR: env[sp.VERIFY_KEY_VAR]},
            "ops token": {"BRAMBLELOOP_OPS_TOKEN": env[sp.SIGNING_KEY_VAR]},
        }
        for name, extra in shared_cases.items():
            h = sp.key_health({**os.environ, **extra})
            assert h["configured"] is False and h["problems"], (name, h)
        mismatched = {**os.environ, sp.VERIFY_KEY_VAR: other[sp.VERIFY_KEY_VAR]}
        assert sp.key_health(mismatched)["configured"] is False
        missing = {k: v for k, v in os.environ.items() if k != sp.VERIFY_KEY_VAR}
        assert sp.key_health(missing)["configured"] is False
        distinct = {**os.environ, sp.ISSUER_KEY_VAR: other[sp.ISSUER_KEY_VAR],
                    sf.SIGNING_KEY_VAR: other[sp.SIGNING_KEY_VAR]}
        assert sp.key_health(distinct)["configured"] is True
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-PO-7

def test_t_po_7_review_by_pauses_expiry_kills_and_a_dead_policy_is_not_renewed_by_editing():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        with _ModeT():
            before = datetime(2026, 11, 19, tzinfo=timezone.utc)
            assert sp.effective(db, now=before)["state"] == sp.NOT_YET
            assert sp.effective(db, now=NOW)["state"] == sp.EFFECTIVE
            rb = datetime(2027, 1, 18, tzinfo=timezone.utc)
            assert sp.effective(db, now=rb - timedelta(seconds=1))["state"] == sp.EFFECTIVE
            assert sp.effective(db, now=rb)["state"] == sp.ISSUE_PAUSED
            ex = datetime(2027, 2, 17, tzinfo=timezone.utc)
            assert sp.effective(db, now=ex - timedelta(seconds=1))["state"] == sp.ISSUE_PAUSED
            assert sp.effective(db, now=ex)["state"] == sp.DEAD
            # Editing the stored validity breaks the seal: the chain refuses everything.
            with db.session() as s:
                row = s.get(AuditLog, a)
                d = copy.deepcopy(row.detail)
                d["content"]["validity"]["expires_at"] = "2027-03-01T00:00:00+00:00"
                row.detail = d
            e = sp.effective(db, now=ex)
            assert e["state"] == sp.BROKEN, e
    finally:
        _restore()


def test_without_mode_t_nothing_is_effective_and_activation_is_refused():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        e = sp.effective(db, now=NOW)
        assert e["state"] == sp.NONE and "Mode T" in e["why"], e
        with owner_grant_keys.owner_request("s"):
            why = _refused(sp.activate, db, a, stepped_up=True, owner_session="s",
                           actor="owner", now=NOW + timedelta(days=30))
        assert "Mode T" in why and "shadow decision" in why, why
    finally:
        _restore()


def test_activation_preconditions_each_refuse():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        with _ModeT():
            why = sp.activation_refusals(db, a, now=NOW)
            for needle in ("STANDING_POLICY_ENABLED", "effective phase", "shadow period",
                           "separate day", "shadow decision"):
                assert any(needle in w for w in why), (needle, why)
            assert not any("Mode T" in w for w in why)
            with owner_grant_keys.owner_request("s"):
                _refused(sp.activate, db, a, stepped_up=False, owner_session="s",
                         actor="owner", now=NOW, contains="step-up")
            _refused(sp.activate, db, a, stepped_up=True, owner_session="s", actor="owner",
                     now=NOW, contains="Command Center request")
    finally:
        _restore()


# ------------------------------------------------------------------------------- T-CH

def test_t_ch_1_a_deleted_mid_chain_revocation_refuses_all_and_opens_a_p1():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        r = sp.revoke(db, a)
        _activate_raw(db, a, c)
        with db.session() as s:
            s.delete(s.get(AuditLog, r))
        with _ModeT():
            e = sp.effective(db, now=NOW)
        assert e["state"] == sp.BROKEN, e
        assert sp.LEDGER.refusal(db, a)
        with db.session() as s:
            inc = s.scalar(select(Incident).where(Incident.signature == sp.SIGNATURE))
            assert inc is not None and inc.severity == "P1"
    finally:
        _restore()


def test_t_ch_2_a_copied_old_approval_row_breaks_the_link():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        with db.session() as s:
            orig = s.get(AuditLog, a)
            s.add(AuditLog(actor=orig.actor, action=orig.action, artifact=orig.artifact,
                           detail=dict(orig.detail)))
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] == sp.BROKEN
    finally:
        _restore()


def test_t_ch_3_an_unsealed_suspension_still_suspends_and_is_reported_as_tamper():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        # A process that can neither sign nor hold the ops token still suspends.
        os.environ[sp.EMBEDDED_VAR] = "1"
        os.environ.pop("BRAMBLELOOP_OPS_TOKEN")
        sid = sp.suspend(db, c["policy_id"], reason="stop: dead letters", by="worker")
        with db.session() as s:
            assert s.get(AuditLog, sid).detail.get("unsealed") is True
        with _ModeT():
            e = sp.effective(db, now=NOW)
        assert e["state"] in (sp.BROKEN, sp.SUSPENDED_STATE) and e["state"] != sp.EFFECTIVE, e
        with db.session() as s:
            assert s.scalar(select(Incident).where(Incident.signature == sp.SIGNATURE))
    finally:
        _restore()


def test_t_ch_3_a_worker_with_only_the_ops_token_suspends_but_cannot_grant():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        os.environ[sp.EMBEDDED_VAR] = "1"           # cannot sign with the policy key
        sid = sp.suspend(db, c["policy_id"], reason="stop: refund rate", by="stop_watch")
        with db.session() as s:
            d = s.get(AuditLog, sid).detail
        assert d["seal"].startswith("h:") and not d.get("unsealed"), d
        with _ModeT():
            e = sp.effective(db, now=NOW)
        assert e["state"] == sp.SUSPENDED_STATE and "refund rate" in e["why"], e
        # The same HMAC cannot seal anything that grants: an approval sealed with it fails.
        forged = {"principal": sp.PRINCIPAL, "policy_id": c["policy_id"], "reason": "x",
                  "by": "x", "suspended_at": NOW.isoformat(), "event": sp.ACTIVATED,
                  "seq": 9, "prev_id": sid, "prev_seal": d["seal"]}
        assert sp._verify(forged, sp._suspension_hmac(
            {**forged, "event": sp.SUSPENDED})) is False
        assert sp._verify({"content": c, "event": sp.APPROVED},
                          sp._suspension_hmac({**forged, "event": sp.SUSPENDED})) is False
    finally:
        _restore()


def test_the_suspension_hmac_never_verifies_a_granting_row():
    """The ops-token HMAC is deny-only: an approval, activation or resume sealed with it does
    not verify, even when the HMAC is computed over that exact body."""
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        bodies = [
            {"principal": sp.PRINCIPAL, "content": c, "event": sp.APPROVED, "seq": 2,
             "prev_id": a, "prev_seal": "x"},
            {"principal": sp.PRINCIPAL, "approval_id": a, "policy_id": c["policy_id"],
             "event": sp.ACTIVATED, "seq": 2, "prev_id": a, "prev_seal": "x"},
            {"principal": sp.PRINCIPAL, "policy_id": c["policy_id"], "reason": "x", "by": "x",
             "suspended_at": NOW.isoformat(), "event": sp.RESUMED, "seq": 2, "prev_id": a,
             "prev_seal": "x"},
        ]
        for body in bodies:
            assert sp._verify(body, sp._suspension_hmac(body)) is False, body["event"]
        # On the chain: a worker that forges an activation with the HMAC breaks the chain.
        with db.session() as s:
            prev = s.get(AuditLog, a).detail["seal"]
            body = {"principal": sp.PRINCIPAL, "approval_id": a, "policy_id": c["policy_id"],
                    "event": sp.ACTIVATED, "seq": 2, "prev_id": a, "prev_seal": prev}
            s.add(AuditLog(actor=sp.PRINCIPAL, action=sp.ACTIVATED, artifact=c["policy_id"],
                           detail={**body, "seal": sp._suspension_hmac(body)}))
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] == sp.BROKEN
    finally:
        _restore()


def test_suspension_is_sticky_and_resume_refuses_while_conditions_are_unknown():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        sp.suspend(db, c["policy_id"], reason="owner pause", by="owner")
        with _ModeT():
            assert sp.effective(db, now=NOW + timedelta(days=5))["state"] == sp.SUSPENDED_STATE
        with owner_grant_keys.owner_request("s"):
            _refused(sp.resume, db, c["policy_id"], stepped_up=True, owner_session="s",
                     actor="owner", contains="UNKNOWN")
            _refused(sp.resume, db, c["policy_id"], stepped_up=True, owner_session="s",
                     actor="owner", stop_conditions_holding=lambda *_: ["refunds 3"],
                     contains="refunds 3")
            sp.resume(db, c["policy_id"], stepped_up=True, owner_session="s", actor="owner",
                      stop_conditions_holding=lambda *_: [])
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] == sp.EFFECTIVE
    finally:
        _restore()


def test_t_ch_4_a_deleted_suspended_or_activated_row_is_detected():
    for target in ("suspended", "activated"):
        try:
            db, c = _db(), content()
            a = _approve(db, c)
            act = _activate_raw(db, a, c)
            sid = sp.suspend(db, c["policy_id"], reason="stop", by="stop_watch")
            _approve(db, content(version=2, supersedes={
                "row_id": a, "seal": _seal_of(db, a)}))
            with db.session() as s:
                s.delete(s.get(AuditLog, sid if target == "suspended" else act))
            with _ModeT():
                e = sp.effective(db, now=NOW)
            assert e["state"] == sp.BROKEN, (target, e)
        finally:
            _restore()


def _seal_of(db, ident):
    with db.session() as s:
        return s.get(AuditLog, ident).detail["seal"]


def test_revocation_without_a_signing_process_is_still_written_and_revokes():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        os.environ[sp.EMBEDDED_VAR] = "1"
        rid = sp.revoke(db, a)
        with db.session() as s:
            assert s.get(AuditLog, rid).detail.get("unsealed") is True
        assert sp.LEDGER.refusal(db, a)
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] != sp.EFFECTIVE
    finally:
        _restore()


def test_a_sealed_revocation_ends_the_policy():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        sp.revoke(db, a)
        with _ModeT():
            e = sp.effective(db, now=NOW)
        assert e["state"] == sp.NONE and "revoked" in e["why"], e
    finally:
        _restore()


def test_rebase_needs_the_owner_and_voids_earlier_policies():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        _refused(sp.rebase, db, "x", stepped_up=True, contains="Command Center request")
        with owner_grant_keys.owner_request("s"):
            _refused(sp.rebase, db, "x", stepped_up=False, contains="step-up")
            sp.rebase(db, "owner re-anchors", stepped_up=True)
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] == sp.NONE
    finally:
        _restore()


def test_no_verify_key_means_no_policy():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        os.environ.pop(sp.VERIFY_KEY_VAR)
        with _ModeT():
            assert sp.effective(db, now=NOW)["state"] == sp.BROKEN
    finally:
        _restore()


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
