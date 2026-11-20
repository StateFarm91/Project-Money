"""ENG-APPROVALS: the owner's standing authority D-OWNER-STANDING-INTERNAL in code.

* routine internal kinds proceed (are superseded by the directive) with an audit citation;
* genuine exceptions stay with the owner, whatever their class, and so does any unknown kind;
* the opening-catalogue Etsy listing-fee budget caps at CA$6 cumulatively and refuses beyond;
* a publication hold (an unreviewed listing-side policy change, an open hold card) does not
  stop internal job types from dispatching, and still refuses publication;
* the consolidation sweep is idempotent and never closes a genuine exception;
* nothing here ever signs, seals or records an owner grant;
* the guards are mutation-killing (boundaries and fail-closed defaults are pinned).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import BudgetExceeded  # noqa: E402
from brambleloop.authority import classes  # noqa: E402
from brambleloop.authority import standing_internal as SI  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, OwnerAction  # noqa: E402
from brambleloop.finance import listing_costs as LC  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.ops import owner_queue_consolidate as OQC  # noqa: E402
# D-OWNER-POLICY39-OVERRIDE releases production's pending listing_image_rules change; this
# suite tests the #39 hold mechanism itself on fixture changes, so the override is off here.
from brambleloop.gates import platform_policy as _pp_override  # noqa: E402
_pp_override.OWNER_DIRECTED_OVERRIDES.clear()

NOW = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)

ROUTINE_KEYS = ("store:etsy.openapi_review", "store:etsy.ui_drift_review",
                "creative.reengineer:owner_choice", "chain-deadend:pricing:demo-mat@v",
                "taxonomy_drift:seven", "portfolio.rework:demo-mat",
                "improve.stop_list:weekly", "improve.retirement:weekly_review",
                "laura:growth:seo.cycle", "model.routes_invalid")
# One genuine kind per exception class, plus an unknown kind (fail closed).
GENUINE_KEYS = {
    SI.GRANT_SIGNATURE: "storefront:write_authority",
    SI.PUBLICATION: "standing_policy.hold:demo-mat@v:abcdefabcdef",
    SI.POLICY_ATTESTATION: "etsy_surface:apps_none_installed",
    SI.PHYSICAL_EVIDENCE: "physical_review:demo-mat@v:three",
    SI.SPEND_BEYOND_BUDGET: "benchmark_challenge",
    SI.PAID_ADS_SUBSCRIPTIONS: "ads.scale:demo-mat",
    SI.KYC_LEGAL_BANKING: "payout",
    SI.CERT_SAFETY_AUTHORITY: "childrens-decision:demo-mat",
    SI.UNCLASSIFIED: "something.nobody.named",
}
# Every kind the producer inventory found (owner_queue_classification.md), placeholders filled.
INVENTORY = (
    "etsy.auth:reauthorise", "reauthorise_transactions_r", "store:etsy.openapi_review",
    "etsy_surface:messages_watch", "etsy_surface:policy_violations_check",
    "etsy_surface:etsy_ads_off", "etsy_surface:offsite_ads_fee_readout",
    "etsy_surface:first_monthly_statement", "etsy_surface:payment_settings_setup",
    "etsy_surface:legal_and_tax_setup", "etsy_surface:apps_none_installed",
    "etsy_surface:info_and_appearance_setup", "etsy_surface:shared_access_empty",
    "etsy_surface:policy_settings_paste", "etsy_surface:subscription_none",
    "etsy_surface:webhook_order_paid", "etsy_surface:developer_portal_quota",
    "search_visibility:launch_week", "storefront:write_authority",
    "storefront.asset:ICON_MISSING:shop", "store:OA-OBS", "store:OA-B", "store:OA-BANNER",
    "store:OA-C", "store:OA-D1", "store:OA-E", "store:OA-F", "store:OA-G1", "store:OA-G2",
    "store:OA-LIVE-title", "store:etsy.ui_drift_review", "etsy_shop", "payout",
    "listing_fees", "physical_calibration", "model_credits", "benchmark_challenge",
    "brand_clearance", "artifact_storage", "phase", "benchmark_observation", "model_provider",
    "credential_rotation:ANTHROPIC_API_KEY", "image_benchmark_budget",
    "canonical_model_selection", "canonical_model_approval", "model_provider_balance",
    "model_provider_balance:bfl", "model.vendor_switch_routed_only", "model.routes_invalid",
    "laura.voice.listen_shortlist", "creative.reengineer:owner_choice",
    "childrens-decision:demo-mat", "listing.live_update:demo-mat@v",
    "physical_size_conflict:demo-mat@v:row", "physical_review:demo-mat@v:row",
    "physical_evidence:demo-mat@v:abcdefabcdef", "chain-deadend:pricing:demo-mat@v",
    "standing_policy.hold:demo-mat@v:abcdefabcdef",
    "standing_policy.withdrawal_unconfirmed:listing", "autonomy:store_commerce:publication_review",
    "listing_package:demo-mat@v:abcdef", "draft_reconcile:abcdef",
    "etsy.exercise.stranded_draft.listing", "taxonomy_drift:snap", "portfolio.retire:demo-mat",
    "portfolio.rework:demo-mat", "ads.scale:demo-mat", "ads.proposal:abcdef",
    "etsy_ads_eligibility_evidence", "creators.graduate:tester", "club:launch_decision",
    "spend.ceiling.2026-11", "reinvestment:2026-11", "knowledge_gap:line",
    "benchmark_refresh:trigger:subject", "etsy.dashboard:order:ref",
    "etsy.dashboard:renewal:listing", "correction_notice:demo-mat@v",
    "legal_review:etsy.policy_violation:item", "policy_violation_overdue:etsy.policy_violation:item",
    "support.first_response:case:one", "support_defect_decision:support.defect:sig",
    "improve.retirement:weekly_review", "improve.architecture:add",
    "improve.architecture:revise_metric", "improve.stop_list:weekly", "improve.upgrade:one",
    "improve.league:one", "improve.challenger_run:one", "laura:growth:seo.cycle",
    "laura:store.publish:demo-mat", "decision.api_vision_equivalence",
    "etsy.oauth.reauthorise",
)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/approvals.sqlite", scratch=True)
    db.create_all()
    return db


def _add(db, key, *, at=NOW, parked=False) -> int:
    with db.session() as s:
        row = OwnerAction(requirement_key=key, action=f"do {key}", reason="r", at=at)
        s.add(row)
        s.flush()
        if parked:
            owner_queue.transition(s, row, owner_queue.PARKED, "parked by the owner", now=at)
        return row.id


def _rows(db):
    with db.session() as s:
        return {r.requirement_key: (owner_queue.effective_state(r), r.state_reason or "")
                for r in s.scalars(select(OwnerAction))}


def _audits(db, action=SI.AUDIT_ACTION):
    with db.session() as s:
        return [(r.actor, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


# ---- classification ----------------------------------------------------------------------

def test_covered_classes_are_exactly_the_autonomous_ones():
    assert SI.COVERED_CLASSES == classes.AUTONOMOUS
    assert not SI.COVERED_CLASSES & classes.GATED
    for jt in ("chain.rebuild", "gate.certify", "assets.build", "listing.package",
               "listing.seo", "cir.compile", "radar.scan", "ops.owner_queue_consolidate"):
        assert SI.covers_job_type(jt), jt
    for jt in ("store.publish", "store.activate", "store.update", "ads.campaign",
               "support.reply", "pricing.experiment", "an.unknown.type", "", "deploy_now"):
        assert not SI.covers_job_type(jt), jt


def test_every_inventoried_kind_is_classified_and_none_falls_to_the_default():
    unclassified = [k for k in INVENTORY if SI.classify(k)["class"] == SI.UNCLASSIFIED]
    assert unclassified == [], unclassified
    for k in INVENTORY:
        v = SI.classify(k)
        assert v["disposition"] in SI.DISPOSITIONS and v["directive"] == SI.DIRECTIVE_ID
        if v["disposition"] == SI.GENUINE_EXCEPTION:
            assert v["class"] in SI.EXCEPTION_CLASSES, (k, v)


def test_unknown_and_empty_kinds_fail_closed_to_the_owner():
    for k in ("something.nobody.named", "", None, "dag:no-job-type-here",
              "laura:growth:not.a.known.job"):
        v = SI.classify(k)
        assert v["disposition"] == SI.GENUINE_EXCEPTION and v["class"] == SI.UNCLASSIFIED, k


def test_job_type_requests_follow_the_declared_action_class():
    assert SI.classify("laura:growth:seo.cycle")["disposition"] == SI.ROUTINE_INTERNAL
    pub = SI.classify("laura:store_commerce:store.publish")
    assert pub["disposition"] == SI.GENUINE_EXCEPTION and pub["class"] == SI.PUBLICATION
    # One gated job type among routine ones keeps the whole request with the owner.
    mixed = SI.classify("dag:seo.cycle:ads.campaign")
    assert mixed["disposition"] == SI.GENUINE_EXCEPTION
    assert mixed["class"] == SI.SPEND_BEYOND_BUDGET
    assert SI.classify("dag:x:support.reply")["class"] == SI.PUBLICATION


def test_the_specific_genuine_rules_win_over_broader_prefixes():
    assert SI.classify("etsy_surface:apps_none_installed")["class"] == SI.POLICY_ATTESTATION
    assert SI.classify("etsy_surface:legal_and_tax_setup")["class"] == SI.KYC_LEGAL_BANKING
    assert SI.classify("etsy_surface:anything_new")["class"] == SI.PUBLICATION
    assert SI.classify("store:OA-B")["class"] == SI.GRANT_SIGNATURE
    assert SI.classify("store:OA-anything")["disposition"] == SI.GENUINE_EXCEPTION
    assert SI.classify("store:etsy.openapi_review")["disposition"] == SI.ROUTINE_INTERNAL


def test_no_routine_or_auto_close_rule_names_an_executor_gate():
    from brambleloop.build2 import executor

    gate_keys = set(executor.GATE_BY_KEY) | set(executor.OWNER_ACTION_GATE_ALIASES)
    assert len(gate_keys) > 20, gate_keys
    for k in sorted(gate_keys):
        v = SI.classify(k)
        assert v["disposition"] == SI.GENUINE_EXCEPTION, (k, v)


# ---- the sweep ---------------------------------------------------------------------------

def test_routine_kinds_proceed_with_an_audit_row_citing_the_directive():
    db = _db()
    for k in ROUTINE_KEYS:
        _add(db, k)
    _add(db, "improve.architecture:add", parked=True)
    out = OQC.sweep(db, now=NOW)
    rows = _rows(db)
    for k in ROUTINE_KEYS + ("improve.architecture:add",):
        state, why = rows[k]
        assert state == owner_queue.SUPERSEDED, (k, state)
        assert SI.DIRECTIVE_ID in why, why
    assert len(out["routine_superseded"]) == len(ROUTINE_KEYS) + 1 and out["auto_closed"] == []
    audits = _audits(db)
    assert len(audits) == len(ROUTINE_KEYS) + 1
    for actor, d in audits:
        assert actor == SI.ACTOR and d["directive"] == SI.DIRECTIVE_ID
        assert d["disposition"] == SI.ROUTINE_INTERNAL and d["to"] == owner_queue.SUPERSEDED
    # The lifecycle trail is written too, and nothing is deleted.
    assert len(_audits(db, "owner_action.lifecycle")) >= len(ROUTINE_KEYS)
    with db.session() as s:
        assert s.scalar(select(func.count(OwnerAction.id))) == len(ROUTINE_KEYS) + 1


def test_genuine_exceptions_still_require_the_owner():
    db = _db()
    for k in GENUINE_KEYS.values():
        _add(db, k, at=NOW - timedelta(days=400))      # old: never "stale" for a genuine kind
    _add(db, "payout_extra_never_named", parked=True)
    out = OQC.sweep(db, now=NOW)
    assert out["closed"] == 0 and _audits(db) == []
    for k, (state, _why) in _rows(db).items():
        assert state in (owner_queue.OPEN, owner_queue.PARKED), (k, state)
    assert set(out["unclassified_open"]) == {"something.nobody.named",
                                            "payout_extra_never_named"}


def test_auto_close_kinds_close_with_their_reason():
    db = _db()
    _add(db, "autonomy:store_commerce:publication_review")
    _add(db, "listing_package:demo-mat@v:abcdef")
    _add(db, "etsy.oauth.reauthorise")
    OQC.sweep(db, now=NOW)
    rows = _rows(db)
    assert rows["autonomy:store_commerce:publication_review"][0] == owner_queue.SUPERSEDED
    assert rows["etsy.oauth.reauthorise"][0] == owner_queue.SUPERSEDED
    # Withdrawn: the package job treats it as answered for that content (no hourly churn).
    assert rows["listing_package:demo-mat@v:abcdef"][0] == owner_queue.WITHDRAWN
    assert {d["disposition"] for _a, d in _audits(db)} == {SI.AUTO_CLOSE}


def test_the_sweep_is_idempotent_and_a_reraised_card_is_closed_again():
    db = _db()
    for k in ROUTINE_KEYS[:3] + tuple(GENUINE_KEYS.values()):
        _add(db, k)
    first = OQC.sweep(db, now=NOW)
    n = len(_audits(db))
    snap = _rows(db)
    second = OQC.sweep(db, now=NOW + timedelta(hours=1))
    assert first["closed"] == 3 and second["closed"] == 0
    assert len(_audits(db)) == n and _rows(db) == snap
    # A producer raising the same routine kind again gets one new row; it is closed once.
    _add(db, ROUTINE_KEYS[0], at=NOW + timedelta(hours=2))
    third = OQC.sweep(db, now=NOW + timedelta(hours=3))
    assert third["closed"] == 1 and len(_audits(db)) == n + 1


def test_stale_rule_waits_for_the_window_and_never_applies_to_a_genuine_kind():
    class _Row:
        at = NOW - SI.STALE_AFTER + timedelta(minutes=1)
        state_at = None
    stale = {"disposition": SI.AUTO_CLOSE, "class": OQC.STALE_RULE, "why": "w"}
    assert OQC.decide(_Row, stale, now=NOW) is None
    _Row.at = NOW - SI.STALE_AFTER
    assert OQC.decide(_Row, stale, now=NOW)[0] == owner_queue.EXPIRED
    genuine = {"disposition": SI.GENUINE_EXCEPTION, "class": OQC.STALE_RULE, "why": "w"}
    assert OQC.decide(_Row, genuine, now=NOW) is None
    unknown_rule = {"disposition": SI.AUTO_CLOSE, "class": "no_such_rule", "why": "w"}
    assert OQC.decide(_Row, unknown_rule, now=NOW) is None


def test_counts_for_the_p0_board():
    db = _db()
    for k in ROUTINE_KEYS[:2]:
        _add(db, k)
    _add(db, "autonomy:store_commerce:publication_review")
    for k in list(GENUINE_KEYS.values())[:4]:
        _add(db, k)
    _add(db, "taxonomy_drift:awaiting")
    before = OQC.counts(db, now=NOW)
    assert before["owner_exceptions_open"] == 4 and before["awaiting_sweep"] == 4
    OQC.sweep(db, now=NOW)
    c = OQC.counts(db, now=NOW + timedelta(minutes=5))
    assert c["owner_exceptions_open"] == 4 and c["awaiting_sweep"] == 0
    assert c["routine_auto_approved_24h"] == 2 and c["closed_automatically_24h"] == 1
    assert c["routine_superseded_nothing_approved_24h"] == 1
    later = OQC.counts(db, now=NOW + timedelta(hours=25))
    assert later["routine_auto_approved_24h"] == 0 and later["closed_automatically_24h"] == 0


def test_the_p0_board_carries_the_owner_queue_section():
    from brambleloop.app.command_center import p0_board

    assert "owner_queue" in dict(p0_board.SECTIONS)
    db = _db()
    _add(db, "payout")
    _add(db, "store:etsy.openapi_review")
    OQC.sweep(db, now=NOW)
    sec = p0_board.view(db, now=NOW + timedelta(minutes=1))["sections"]["owner_queue"]
    assert sec["owner_exceptions_open"] == 1 and sec["routine_auto_approved_24h"] == 1
    assert sec["state"] == "OPEN"


# ---- the one owner batch ------------------------------------------------------------------

def test_the_batch_shows_only_genuine_exceptions_grouped_by_class():
    cards = [
        {"card_id": "publication:demo-mat@v", "kind": "PUBLICATION", "executable": False},
        {"card_id": "publication:demo-rug@v", "kind": "PUBLICATION", "executable": True,
         "title": "t", "actions": [{"action": "publication.preview"}]},
        {"card_id": "policy:listing_image_rules", "kind": "policy_review", "executable": True},
        {"card_id": "owner_action:9", "kind": "OWNER-DECISION",
         "requirement_key": "store:etsy.openapi_review"},
        {"card_id": "owner_action:10", "kind": "OWNER-DECISION",
         "requirement_key": "childrens-decision:demo-mat"},
        {"card_id": "gate:etsy_shop", "kind": "GATE", "requirement_key": "etsy_shop"},
        {"card_id": "owner_action:11", "kind": "OWNER-DECISION",
         "requirement_key": "brand.new.kind"},
    ]
    b = OQC.exception_batch(cards)
    got = {s["class"]: [i["card_id"] for i in s["items"]] for s in b["sections"]}
    assert got == {SI.PUBLICATION: ["publication:demo-rug@v"],
                   SI.POLICY_ATTESTATION: ["policy:listing_image_rules"],
                   SI.KYC_LEGAL_BANKING: ["gate:etsy_shop"],
                   SI.CERT_SAFETY_AUTHORITY: ["owner_action:10"],
                   SI.UNCLASSIFIED: ["owner_action:11"]}, got
    assert b["exceptions"] == 5 and b["covered_by_standing_authority"] == 2
    assert b["covered_by_class"] == {"engineering": 1, SI.PUBLICATION: 1}
    assert b["not_ready_publication"] == 1
    assert [s["class"] for s in b["sections"]][-1] == SI.UNCLASSIFIED


def test_every_gate_class_is_a_directive_exception_class():
    assert set(OQC.GATE_EXCEPTION_CLASS.values()) <= set(SI.EXCEPTION_CLASSES)
    assert set(OQC.CARD_KIND_CLASS.values()) <= set(SI.EXCEPTION_CLASSES)


# ---- the opening-catalogue listing-fee budget ---------------------------------------------

def _reserve(db, n, amount=0.28, ceiling=100.0):
    return LC.reserve(db, listing_id=f"L{n}", amount=amount, agent="store_operator",
                      ceiling=ceiling)


def test_fee_budget_caps_at_six_dollars_cumulatively():
    db = _db()
    assert LC.OPENING_CATALOGUE_FEE_BUDGET_CAD == SI.OPENING_LISTING_FEE_BUDGET_CAD == 6.00
    for n in range(21):                          # 21 x 0.28 = 5.88
        _reserve(db, n)
    assert LC.opening_budget(db)["used_cad"] == 5.88
    assert LC.opening_budget_refusal(db, "L-new", 0.28) is not None
    try:
        _reserve(db, 99)
        raise AssertionError("the 22nd listing fee must be refused")
    except BudgetExceeded as exc:
        assert "CA$6.00" in str(exc)
    # The same listing again costs nothing more (once per listing), and is not refused.
    assert LC.opening_budget_refusal(db, "L3", 0.28) is None
    _reserve(db, 3)
    with db.session() as s:
        assert s.scalar(select(func.count(CostEntry.id))) == 21
    assert LC.opening_budget(db)["remaining_cad"] == 0.12


def test_fee_budget_boundary_and_actual_fees_count():
    db = _db()
    # ENG-ETSY-PUBLISH: one reservation is at most one listing fee (US$0.20 at the assumed
    # rate), so the cumulative CA$6 boundary is reached one fee at a time.
    assert "per-listing cap" in (LC.opening_budget_refusal(db, "A", 6.00) or "")
    assert LC.opening_budget_refusal(db, "A", 0.28) is None
    assert LC.opening_budget_refusal(db, "A", -1.0) is not None
    for n in range(20):
        _reserve(db, n)                                   # 20 x 0.28 = CA$5.60
    assert LC.opening_budget_refusal(db, "B", 0.28) is None
    # An observed fee for a listing never reserved counts; one for a reserved listing does not.
    with db.session() as s:
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee_actual",
                        amount_cad=0.30, detail={"listing_id": "L1"}))
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee_actual",
                        amount_cad=0.25, detail={"listing_id": "renewed-elsewhere"}))
    assert LC.opening_budget(db)["used_cad"] == 5.85
    assert LC.opening_budget_refusal(db, "C", 0.15) is None          # exactly CA$6.00
    assert "CA$6.00" in (LC.opening_budget_refusal(db, "C", 0.16) or "")


def test_the_daily_ceiling_is_unchanged_and_checked_first():
    db = _db()
    try:
        _reserve(db, 1, amount=0.28, ceiling=0.20)
        raise AssertionError("the store_operator daily ceiling still applies")
    except BudgetExceeded as exc:
        assert "daily ceiling" in str(exc)
    from brambleloop.agents.registry import DEFAULT_AGENTS

    op = next(a for a in DEFAULT_AGENTS if a["name"] == "store_operator")
    assert op["daily_cost_ceiling_cad"] == 1.0              # not raised by the budget


# ---- publication holds never stop internal manufacturing --------------------------------

def test_a_publication_hold_does_not_block_internal_jobs_and_still_holds_publication():
    from brambleloop.authority import policy
    from brambleloop.gates import platform_policy as pp

    db = _db()
    pp.record_snapshot(db, "listing_image_rules", text="rules one", checked_on="2026-11-01",
                       read_by="tester", basis="page")
    pp.record_snapshot(db, "listing_image_rules", text="rules two changed",
                       checked_on="2026-11-02", read_by="tester", basis="page")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == ["listing_image_rules"]
    _add(db, "standing_policy.hold:demo-mat@v:abcdefabcdef")
    _add(db, "autonomy:store_commerce:publication_review")
    from brambleloop.agents.registry import DEFAULT_AGENTS

    internal = ("chain.rebuild", "gate.certify", "assets.build", "assets.render",
                "listing.package", "listing.seo", "seo.cycle", "cir.compile", "cir.twin")
    assert internal
    for jt in internal:
        owner = next((a["name"] for a in DEFAULT_AGENTS if jt in a["allowed_job_types"]),
                     "orchestrator")
        assert policy.check_dispatch(db, owner, jt) is None, jt
        assert SI.covers_job_type(jt), jt
    # ...while a gated type is still examined (and refused for an agent without authority).
    assert policy.check_dispatch(db, "orchestrator", "store.publish") is not None
    OQC.sweep(db, now=NOW)
    rows = _rows(db)
    assert rows["standing_policy.hold:demo-mat@v:abcdefabcdef"][0] == owner_queue.OPEN
    # Publication stays held by the unreviewed change.
    from brambleloop.publish import release_gates as rg

    assert any("platform policy changed" in r
               for r in rg.staleness(db, slug="demo-mat")["reasons"])


# ---- nothing is ever signed --------------------------------------------------------------

def test_no_grant_is_ever_signed_automatically():
    db = _db()
    for k in INVENTORY:
        _add(db, k)
    OQC.sweep(db, now=NOW)
    with db.session() as s:
        actions = {a for (a,) in s.execute(select(AuditLog.action))}
        actors = {a for (a,) in s.execute(select(AuditLog.actor))}
    assert actions <= {SI.AUDIT_ACTION, "owner_action.lifecycle"}, actions
    assert not any(a.startswith("owner") for a in actors), actors
    # Every owner-grant family stays empty.
    from brambleloop.ops import activation_authority as aa
    from brambleloop.ops import launch_decisions as ld
    from brambleloop.ops import publication_authority as pa
    from brambleloop.ops import standing_policy as sp

    for fam in (pa.APPROVED, aa.APPROVED, ld.APPROVED, sp.APPROVED):
        assert fam not in actions
    # The modules import no signer or grant writer and call no owner door.
    import ast

    forbidden = {"publication_authority", "activation_authority", "launch_decisions",
                 "standing_policy", "standing_issuer", "sealed_chain", "owner_grant_keys",
                 "storefront_authority", "opsauth"}
    for mod in (SI, OQC):
        tree = ast.parse(open(mod.__file__).read())
        assert tree.body
        for node in ast.walk(tree):  # vacuity-ok: a non-empty module, asserted above
            if isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[-1]} | {a.name for a in node.names}
            elif isinstance(node, ast.Import):
                names = {a.name.split(".")[-1] for a in node.names}
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                names = {node.func.attr}
            else:
                continue
            bad = names & (forbidden | {"approve", "record_owner_approval", "review_change",
                                        "set_limit", "record", "sign"})
            assert not bad, (mod.__name__, bad)



# ---- M1-M3 (independent review) ----------------------------------------------------------

#: Every rule in KIND_RULES, pinned as (disposition, class). Any reclassification fails.
D_G, D_R, D_A = SI.GENUINE_EXCEPTION, SI.ROUTINE_INTERNAL, SI.AUTO_CLOSE
PINNED_RULES = {
    'prefix:childrens-decision:': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'prefix:physical_size_conflict:': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'exact:decision.api_vision_equivalence': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'prefix:support_defect_decision:': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'prefix:improve.upgrade:': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'prefix:improve.league:': (D_G, SI.GRANT_SIGNATURE),
    'exact:storefront:write_authority': (D_G, SI.GRANT_SIGNATURE),
    'exact:canonical_model_selection': (D_G, SI.GRANT_SIGNATURE),
    'exact:canonical_model_approval': (D_G, SI.GRANT_SIGNATURE),
    'exact:etsy.auth:reauthorise': (D_G, SI.GRANT_SIGNATURE),
    'exact:reauthorise_transactions_r': (D_G, SI.GRANT_SIGNATURE),
    'exact:benchmark_observation': (D_G, SI.GRANT_SIGNATURE),
    'exact:model_provider': (D_G, SI.GRANT_SIGNATURE),
    'prefix:credential_rotation:': (D_G, SI.GRANT_SIGNATURE),
    'exact:etsy_surface:webhook_order_paid': (D_G, SI.GRANT_SIGNATURE),
    'exact:store:OA-B': (D_G, SI.GRANT_SIGNATURE),
    'exact:etsy_shop': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:payout': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:brand_clearance': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:etsy_surface:payment_settings_setup': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:etsy_surface:legal_and_tax_setup': (D_G, SI.KYC_LEGAL_BANKING),
    'prefix:legal_review:': (D_G, SI.KYC_LEGAL_BANKING),
    'prefix:creators.graduate:': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:model_credits': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:model_provider_balance': (D_G, SI.KYC_LEGAL_BANKING),
    'prefix:model_provider_balance:': (D_G, SI.KYC_LEGAL_BANKING),
    'exact:listing_fees': (D_G, SI.SPEND_BEYOND_BUDGET),
    'exact:benchmark_challenge': (D_G, SI.SPEND_BEYOND_BUDGET),
    'exact:image_benchmark_budget': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:spend.ceiling.': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:reinvestment:': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:knowledge_gap:': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:benchmark_refresh:': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:etsy.dashboard:renewal:': (D_G, SI.SPEND_BEYOND_BUDGET),
    'prefix:ads.': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:etsy_ads_eligibility_evidence': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:etsy_surface:etsy_ads_off': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:store:OA-G2': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:etsy_surface:subscription_none': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:artifact_storage': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'exact:laura.voice.listen_shortlist': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'prefix:physical_evidence:': (D_G, SI.PHYSICAL_EVIDENCE),
    'prefix:physical_review:': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:physical_calibration': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:search_visibility:launch_week': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:store:OA-BANNER': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:etsy_surface:offsite_ads_fee_readout': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:etsy_surface:first_monthly_statement': (D_G, SI.PHYSICAL_EVIDENCE),
    'exact:etsy_surface:developer_portal_quota': (D_G, SI.PHYSICAL_EVIDENCE),
    'prefix:policy_violation_overdue:': (D_G, SI.POLICY_ATTESTATION),
    'exact:etsy_surface:messages_watch': (D_G, SI.POLICY_ATTESTATION),
    'exact:etsy_surface:policy_violations_check': (D_G, SI.POLICY_ATTESTATION),
    'exact:etsy_surface:apps_none_installed': (D_G, SI.POLICY_ATTESTATION),
    'exact:etsy_surface:shared_access_empty': (D_G, SI.POLICY_ATTESTATION),
    'exact:store:OA-OBS': (D_G, SI.POLICY_ATTESTATION),
    'exact:store:OA-G1': (D_G, SI.POLICY_ATTESTATION),
    'exact:phase': (D_G, SI.PUBLICATION),
    'prefix:first_public_listing:': (D_G, SI.PUBLICATION),
    'prefix:standing_policy.hold:': (D_G, SI.PUBLICATION),
    'prefix:standing_policy.withdrawal_unconfirmed:': (D_G, SI.PUBLICATION),
    'prefix:listing.live_update:': (D_G, SI.PUBLICATION),
    'prefix:portfolio.retire:': (D_G, SI.PUBLICATION),
    'prefix:draft_reconcile:': (D_G, SI.PUBLICATION),
    'prefix:etsy.exercise.stranded_draft.': (D_G, SI.PUBLICATION),
    'prefix:correction_notice:': (D_G, SI.PUBLICATION),
    'prefix:support.first_response:': (D_G, SI.PUBLICATION),
    'prefix:etsy.dashboard:order:': (D_G, SI.PUBLICATION),
    'exact:club:launch_decision': (D_G, SI.PUBLICATION),
    'prefix:storefront.asset:': (D_G, SI.PUBLICATION),
    'prefix:etsy_surface:': (D_G, SI.PUBLICATION),
    'prefix:store:OA-': (D_G, SI.PUBLICATION),
    'exact:autonomy:store_commerce:publication_review': (D_A, 'redundant'),
    'exact:etsy.oauth.reauthorise': (D_A, 'redundant'),
    'prefix:listing_package:': (D_A, 'redundant_withdrawn'),
    'exact:store:etsy.openapi_review': (D_R, 'engineering'),
    'exact:store:etsy.ui_drift_review': (D_R, 'engineering'),
    'exact:model.vendor_switch_routed_only': (D_R, 'engineering'),
    'exact:model.routes_invalid': (D_R, 'engineering'),
    'exact:creative.reengineer:owner_choice': (D_R, 'product_development'),
    'prefix:chain-deadend:pricing:': (D_R, 'product_development'),
    'prefix:taxonomy_drift:': (D_R, 'recovery'),
    'prefix:portfolio.rework:': (D_R, 'product_development'),
    'exact:improve.retirement:weekly_review': (D_R, 'agent_coordination'),
    'exact:improve.architecture:add': (D_R, 'agent_coordination'),
    'exact:improve.architecture:revise_metric': (D_R, 'agent_coordination'),
    'exact:improve.stop_list:weekly': (D_R, 'scheduling'),
    'prefix:improve.challenger_run:': (D_R, 'learning'),
}

#: Every inventoried kind and the job-type families, pinned the same way.
EXPECTED_RULE_TALLY = {D_G: 71, D_R: 13, D_A: 3}

PINNED_KINDS = {
    'etsy.auth:reauthorise': (D_G, SI.GRANT_SIGNATURE),
    'reauthorise_transactions_r': (D_G, SI.GRANT_SIGNATURE),
    'store:etsy.openapi_review': (D_R, 'engineering'),
    'etsy_surface:messages_watch': (D_G, SI.POLICY_ATTESTATION),
    'etsy_surface:policy_violations_check': (D_G, SI.POLICY_ATTESTATION),
    'etsy_surface:etsy_ads_off': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'etsy_surface:offsite_ads_fee_readout': (D_G, SI.PHYSICAL_EVIDENCE),
    'etsy_surface:first_monthly_statement': (D_G, SI.PHYSICAL_EVIDENCE),
    'etsy_surface:payment_settings_setup': (D_G, SI.KYC_LEGAL_BANKING),
    'etsy_surface:legal_and_tax_setup': (D_G, SI.KYC_LEGAL_BANKING),
    'etsy_surface:apps_none_installed': (D_G, SI.POLICY_ATTESTATION),
    'etsy_surface:info_and_appearance_setup': (D_G, SI.PUBLICATION),
    'etsy_surface:shared_access_empty': (D_G, SI.POLICY_ATTESTATION),
    'etsy_surface:policy_settings_paste': (D_G, SI.PUBLICATION),
    'etsy_surface:subscription_none': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'etsy_surface:webhook_order_paid': (D_G, SI.GRANT_SIGNATURE),
    'etsy_surface:developer_portal_quota': (D_G, SI.PHYSICAL_EVIDENCE),
    'search_visibility:launch_week': (D_G, SI.PHYSICAL_EVIDENCE),
    'storefront:write_authority': (D_G, SI.GRANT_SIGNATURE),
    'storefront.asset:ICON_MISSING:shop': (D_G, SI.PUBLICATION),
    'store:OA-OBS': (D_G, SI.POLICY_ATTESTATION),
    'store:OA-B': (D_G, SI.GRANT_SIGNATURE),
    'store:OA-BANNER': (D_G, SI.PHYSICAL_EVIDENCE),
    'store:OA-C': (D_G, SI.PUBLICATION),
    'store:OA-D1': (D_G, SI.PUBLICATION),
    'store:OA-E': (D_G, SI.PUBLICATION),
    'store:OA-F': (D_G, SI.PUBLICATION),
    'store:OA-G1': (D_G, SI.POLICY_ATTESTATION),
    'store:OA-G2': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'store:OA-LIVE-title': (D_G, SI.PUBLICATION),
    'store:etsy.ui_drift_review': (D_R, 'engineering'),
    'etsy_shop': (D_G, SI.KYC_LEGAL_BANKING),
    'payout': (D_G, SI.KYC_LEGAL_BANKING),
    'listing_fees': (D_G, SI.SPEND_BEYOND_BUDGET),
    'physical_calibration': (D_G, SI.PHYSICAL_EVIDENCE),
    'model_credits': (D_G, SI.KYC_LEGAL_BANKING),
    'benchmark_challenge': (D_G, SI.SPEND_BEYOND_BUDGET),
    'brand_clearance': (D_G, SI.KYC_LEGAL_BANKING),
    'artifact_storage': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'phase': (D_G, SI.PUBLICATION),
    'benchmark_observation': (D_G, SI.GRANT_SIGNATURE),
    'model_provider': (D_G, SI.GRANT_SIGNATURE),
    'credential_rotation:ANTHROPIC_API_KEY': (D_G, SI.GRANT_SIGNATURE),
    'image_benchmark_budget': (D_G, SI.SPEND_BEYOND_BUDGET),
    'canonical_model_selection': (D_G, SI.GRANT_SIGNATURE),
    'canonical_model_approval': (D_G, SI.GRANT_SIGNATURE),
    'model_provider_balance': (D_G, SI.KYC_LEGAL_BANKING),
    'model_provider_balance:bfl': (D_G, SI.KYC_LEGAL_BANKING),
    'model.vendor_switch_routed_only': (D_R, 'engineering'),
    'model.routes_invalid': (D_R, 'engineering'),
    'laura.voice.listen_shortlist': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'creative.reengineer:owner_choice': (D_R, 'product_development'),
    'childrens-decision:demo-mat': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'listing.live_update:demo-mat@v': (D_G, SI.PUBLICATION),
    'physical_size_conflict:demo-mat@v:row': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'physical_review:demo-mat@v:row': (D_G, SI.PHYSICAL_EVIDENCE),
    'physical_evidence:demo-mat@v:abcdefabcdef': (D_G, SI.PHYSICAL_EVIDENCE),
    'chain-deadend:pricing:demo-mat@v': (D_R, 'product_development'),
    'standing_policy.hold:demo-mat@v:abcdefabcdef': (D_G, SI.PUBLICATION),
    'standing_policy.withdrawal_unconfirmed:listing': (D_G, SI.PUBLICATION),
    'autonomy:store_commerce:publication_review': (D_A, 'redundant'),
    'listing_package:demo-mat@v:abcdef': (D_A, 'redundant_withdrawn'),
    'draft_reconcile:abcdef': (D_G, SI.PUBLICATION),
    'etsy.exercise.stranded_draft.listing': (D_G, SI.PUBLICATION),
    'taxonomy_drift:snap': (D_R, 'recovery'),
    'portfolio.retire:demo-mat': (D_G, SI.PUBLICATION),
    'portfolio.rework:demo-mat': (D_R, 'product_development'),
    'ads.scale:demo-mat': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'ads.proposal:abcdef': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'etsy_ads_eligibility_evidence': (D_G, SI.PAID_ADS_SUBSCRIPTIONS),
    'creators.graduate:tester': (D_G, SI.KYC_LEGAL_BANKING),
    'club:launch_decision': (D_G, SI.PUBLICATION),
    'spend.ceiling.2026-11': (D_G, SI.SPEND_BEYOND_BUDGET),
    'reinvestment:2026-11': (D_G, SI.SPEND_BEYOND_BUDGET),
    'knowledge_gap:line': (D_G, SI.SPEND_BEYOND_BUDGET),
    'benchmark_refresh:trigger:subject': (D_G, SI.SPEND_BEYOND_BUDGET),
    'etsy.dashboard:order:ref': (D_G, SI.PUBLICATION),
    'etsy.dashboard:renewal:listing': (D_G, SI.SPEND_BEYOND_BUDGET),
    'correction_notice:demo-mat@v': (D_G, SI.PUBLICATION),
    'legal_review:etsy.policy_violation:item': (D_G, SI.KYC_LEGAL_BANKING),
    'policy_violation_overdue:etsy.policy_violation:item': (D_G, SI.POLICY_ATTESTATION),
    'support.first_response:case:one': (D_G, SI.PUBLICATION),
    'support_defect_decision:support.defect:sig': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'improve.retirement:weekly_review': (D_R, 'agent_coordination'),
    'improve.architecture:add': (D_R, 'agent_coordination'),
    'improve.architecture:revise_metric': (D_R, 'agent_coordination'),
    'improve.stop_list:weekly': (D_R, 'scheduling'),
    'improve.upgrade:one': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'improve.league:one': (D_G, SI.GRANT_SIGNATURE),
    'improve.challenger_run:one': (D_R, 'learning'),
    'laura:growth:seo.cycle': (D_R, 'autonomous_class'),
    'laura:store.publish:demo-mat': (D_G, SI.PUBLICATION),
    'decision.api_vision_equivalence': (D_G, SI.CERT_SAFETY_AUTHORITY),
    'etsy.oauth.reauthorise': (D_A, 'redundant'),
    'dag:x:ads.campaign': (D_G, SI.SPEND_BEYOND_BUDGET),
    'something.nobody.named': (D_G, SI.UNCLASSIFIED),
    '': (D_G, SI.UNCLASSIFIED),
}



def test_every_owner_action_kind_is_pinned_to_its_expected_class():
    # M3 (review): classification mutants survived because only "is it classified" was tested.
    # Every rule, and every inventoried kind, is pinned to (disposition, class); a rule added,
    # removed or reclassified fails here until this table is changed on purpose.
    actual_rules = {f"{r['match']}:{r['pattern']}": (r["disposition"], r["class"])
                    for r in SI.KIND_RULES}
    assert len(actual_rules) == len(SI.KIND_RULES)           # no duplicate rule
    assert actual_rules == PINNED_RULES
    assert len(PINNED_RULES) >= 80 and len(PINNED_KINDS) >= 90          # vacuity guard
    for k, (disp, klass) in PINNED_KINDS.items():
        v = SI.classify(k)
        assert (v["disposition"], v["class"]) == (disp, klass), (k, v["disposition"], v["class"])
    # Every inventoried kind is pinned, and each genuine one names a directive class or the
    # fail-closed default, never a routine label.
    assert set(INVENTORY) <= set(PINNED_KINDS)
    for k, (disp, klass) in PINNED_KINDS.items():
        if disp == SI.GENUINE_EXCEPTION:
            assert klass in SI.EXCEPTION_CLASSES + (SI.UNCLASSIFIED,), (k, klass)
    # The counts by disposition: a mover between buckets shifts one of these.
    tally: dict = {}
    for disp, _k in PINNED_RULES.values():
        tally[disp] = tally.get(disp, 0) + 1
    assert tally == EXPECTED_RULE_TALLY, tally


def test_a_support_defect_decision_is_a_genuine_certification_authority_card():
    # M1 (review): a not_a_defect ruling releases a publication withholding, and the incident
    # says "owner decision only". The sweep must never supersede it, at any age or state.
    key = "support_defect_decision:support.defect:sig"
    v = SI.classify(key)
    assert v["disposition"] == SI.GENUINE_EXCEPTION and v["class"] == SI.CERT_SAFETY_AUTHORITY
    assert SI.is_genuine(key)
    db = _db()
    open_id = _add(db, key, at=NOW - timedelta(days=400))
    parked_id = _add(db, key + "2", parked=True)
    out = OQC.sweep(db, now=NOW)
    out2 = OQC.sweep(db, now=NOW + timedelta(days=60))
    assert out["closed"] == 0 and out2["closed"] == 0 and _audits(db) == []
    assert {open_id, parked_id} <= set(out["genuine_open"])
    rows = _rows(db)
    assert rows[key][0] == owner_queue.OPEN and rows[key + "2"][0] == owner_queue.PARKED
    sec = OQC.counts(db, now=NOW)
    assert sec["owner_exceptions_by_class"].get(SI.CERT_SAFETY_AUTHORITY) == 1
    assert SI.CERT_SAFETY_AUTHORITY == SI.classify("childrens-decision:x")["class"]
    # The batch groups it as an exception, never as covered.
    b = OQC.card_verdict({"card_id": "x", "requirement_key": key})
    assert b["disposition"] == SI.GENUINE_EXCEPTION and b["class"] == SI.CERT_SAFETY_AUTHORITY


# ---- M2: a closure in force is not re-raised every tick ------------------------------------

def _hours(n):
    return [NOW + timedelta(hours=h) for h in range(n)]


def _count(db, model, *where):
    with db.session() as s:
        return s.scalar(select(func.count(model.id)).where(*where))


def _assert_one_row_one_audit(db, key, hours):
    rows = _count(db, OwnerAction, OwnerAction.requirement_key == key)
    audits = [d for _a, d in _audits(db) if d.get("requirement_key") == key and d.get("to")]
    lifecycle = [d for _a, d in _audits(db, "owner_action.lifecycle")
                 if d.get("requirement_key") == key]
    assert rows == 1, f"{key}: {rows} owner_actions rows after {hours} ticks"
    assert len(audits) == 1, f"{key}: {len(audits)} standing_authority rows"
    assert len(lifecycle) == 1, f"{key}: {len(lifecycle)} lifecycle rows"
    return audits[0]


def _candidate():
    from brambleloop.autonomy import generators

    return generators.Candidate(
        department="store_commerce", job_type="store.publish", value=0, source="approval",
        protected=True, reason="drafts prepared", fingerprint="approval:store.publish:1:1",
        evidence=["listings:1"],
        approval={"requirement_key": "autonomy:store_commerce:publication_review",
                  "action": "Review 1 prepared listing draft(s)", "reason": "protected",
                  "max_cost_cad": 0.0, "minutes": 10, "consequence": "stay drafts",
                  "blocks": "store_commerce publication"})


def test_publication_review_is_not_reraised_while_its_closure_is_in_force():
    from brambleloop.autonomy import charters, orchestrator

    db = _db()
    charter = next(c for c in charters.CHARTERS if c.key == "store_commerce")
    cand = _candidate()
    key = cand.approval["requirement_key"]
    raised = []
    for t in _hours(8):                      # eight simulated hours: producer, then the sweep
        out = orchestrator._raise_approval(db, charter, cand, t)
        raised.append(out["created"])
        OQC.sweep(db, now=t)
    assert raised == [True] + [False] * 7, raised
    detail = _assert_one_row_one_audit(db, key, 8)
    assert detail["disposition"] == SI.AUTO_CLOSE
    sec = OQC.counts(db, now=NOW + timedelta(hours=8))
    assert sec["closed_automatically_24h"] == 1, sec            # not ~24 for one card
    assert sec["owner_exceptions_open"] == 0
    # Nothing was deleted: the closed row is still there, closed.
    assert _rows(db)[key][0] == owner_queue.SUPERSEDED


def test_dag_recompute_does_not_reraise_a_closed_routine_approval():
    from brambleloop.authority import dag

    db = _db()
    key = "autonomy:store_commerce:publication_review"
    dag.ensure_tables(db)
    dag.submit(db, key="approval:" + key, department="store_commerce", job_type="store.publish",
               submitted_by="coo", requires_approval=True,
               inputs={"requirement_key": key}, title="Review drafts", now=NOW)
    for t in _hours(8):
        dag.recompute(db, now=t)
        OQC.sweep(db, now=t)
    _assert_one_row_one_audit(db, key, 8)
    with db.session() as s:
        from brambleloop.authority.models import WorkItem

        w = s.scalar(select(WorkItem).where(WorkItem.key == "approval:" + key))
        assert w.state == "awaiting_approval"      # still waiting for the owner's real approval


def test_provider_cards_are_not_reraised_while_their_closure_is_in_force():
    from brambleloop.gateway import providers

    db = _db()
    env = {providers.VENDOR_VAR: sorted(providers.ROUTED_ONLY)[0],
           providers.ROUTES_VAR: "no_such_task=openai"}
    states = []
    for t in _hours(8):
        states.append((providers.vendor_switch_card(db, env=env)["state"],
                       providers.routes_card(db, env=env)["state"]))
        OQC.sweep(db, now=t)
    assert states[0] == ("raised", "raised") and set(states[1:]) == {("covered", "covered")}
    for key in (providers.VENDOR_CARD_KEY, providers.ROUTES_CARD_KEY):
        _assert_one_row_one_audit(db, key, 8)
    sec = OQC.counts(db, now=NOW + timedelta(hours=8))
    assert sec["routine_auto_approved_24h"] == 2, sec
    # The condition clears: the marker is lifted with one audit row, and costs nothing after.
    ok = {providers.VENDOR_VAR: "", providers.ROUTES_VAR: ""}
    n = len(_audits(db))
    for _ in range(3):
        assert providers.vendor_switch_card(db, env=ok)["state"] == "clear"
        assert providers.routes_card(db, env=ok)["state"] == "clear"
    assert len(_audits(db)) == n + 2
    # It comes back (a genuinely new episode): raised again once, then covered again.
    assert providers.vendor_switch_card(db, env=env)["state"] == "raised"
    OQC.sweep(db, now=NOW + timedelta(hours=20))
    assert providers.vendor_switch_card(db, env=env)["state"] == "covered"
    assert _count(db, OwnerAction, OwnerAction.requirement_key == providers.VENDOR_CARD_KEY) == 2


def test_a_changed_condition_or_an_owner_closed_card_is_not_covered():
    from brambleloop.gateway import providers

    db = _db()
    routed = sorted(providers.ROUTED_ONLY)
    first = {providers.VENDOR_VAR: routed[0]}
    assert providers.vendor_switch_card(db, env=first)["state"] == "raised"
    OQC.sweep(db, now=NOW)
    assert providers.vendor_switch_card(db, env=first)["state"] == "covered"
    if len(routed) > 1:                          # another vendor named: a new condition
        second = {providers.VENDOR_VAR: routed[1]}
        assert providers.vendor_switch_card(db, env=second)["state"] == "raised"
    # The same key with a different condition (another invalid route entry) is a new card.
    one = {providers.ROUTES_VAR: "no_such_task=openai"}
    two = {providers.ROUTES_VAR: "another_bad_task=openai"}
    assert providers.routes_card(db, env=one)["state"] == "raised"
    OQC.sweep(db, now=NOW)
    assert providers.routes_card(db, env=one)["state"] == "covered"
    assert providers.routes_card(db, env=two)["state"] == "raised"
    # A genuine kind is never covered, whatever closed it.
    with db.session() as s:
        row = OwnerAction(requirement_key="payout", action="a", done=True, state="withdrawn")
        s.add(row)
        s.flush()
        s.add(AuditLog(actor=SI.ACTOR, action=SI.AUDIT_ACTION, artifact=f"owner_action:{row.id}",
                       detail={"to": "superseded"}))
        s.flush()
        assert not SI.closure_in_force(s, "payout")
        assert not SI.closure_in_force(s, "")
        assert not SI.closure_in_force(s, "no.such.key")


def test_the_sweep_still_closes_a_card_a_producer_raises_when_not_covered():
    # The marker only suppresses producers; a stray routine row is still closed by the sweep.
    db = _db()
    _add(db, "model.routes_invalid")
    assert OQC.sweep(db, now=NOW)["closed"] == 1


# ---- FIX2: owner-closed vs standing-authority-closed, labels, counts, no wall-clock ---------

def _closed_row(db, key, state, actor, *, max_cost=None):
    """A done card closed to `state` by `actor` (the lifecycle audit says who)."""
    with db.session() as s:
        row = OwnerAction(requirement_key=key, action=f"do {key}", reason="r", at=NOW,
                          max_cost_cad=max_cost or 0.0)
        s.add(row)
        s.flush()
        owner_queue.transition(s, row, state, "closed for the test", actor=actor, now=NOW)
        if actor == SI.ACTOR:
            s.add(AuditLog(actor=SI.ACTOR, action=SI.AUDIT_ACTION, at=NOW,
                           artifact=f"owner_action:{row.id}", detail={"to": state}))
        return row.id


def _owner_closed(db, rid, states=None):
    with db.session() as s:
        return SI.owner_closed(s, s.get(OwnerAction, rid), states)


def test_owner_closed_excludes_standing_authority_and_non_decisions():
    db = _db()
    owner = _closed_row(db, "k1", owner_queue.SATISFIED, "owner")
    standing = _closed_row(db, "k2", owner_queue.SATISFIED, SI.ACTOR)
    withdrawn_owner = _closed_row(db, "k3", owner_queue.WITHDRAWN, "owner")
    withdrawn_standing = _closed_row(db, "k4", owner_queue.WITHDRAWN, SI.ACTOR)
    superseded = _closed_row(db, "k5", owner_queue.SUPERSEDED, "owner")
    assert _owner_closed(db, owner) and not _owner_closed(db, standing)
    assert not _owner_closed(db, withdrawn_owner) and not _owner_closed(db, superseded)
    both = (owner_queue.SATISFIED, owner_queue.WITHDRAWN)
    assert _owner_closed(db, withdrawn_owner, both)
    assert not _owner_closed(db, withdrawn_standing, both)
    with db.session() as s:
        assert not SI.owner_closed(s, None)
        assert not SI.owner_closed(s, OwnerAction(requirement_key="x", action="a"))
    # Closed by the standing authority, reopened, then closed by the owner: the owner's.
    with db.session() as s:
        row = s.get(OwnerAction, standing)
        owner_queue.transition(s, row, owner_queue.OPEN, "reopened", actor="owner", now=NOW)
        owner_queue.transition(s, row, owner_queue.SATISFIED, "owner did it", actor="owner",
                               now=NOW)
    assert _owner_closed(db, standing)
    # Mutation: a helper that forgets the standing check lets that closure through.
    orig = SI.closed_by_standing_authority
    SI.closed_by_standing_authority = lambda s, r: False
    try:
        assert _owner_closed(db, _closed_row(db, "k6", owner_queue.SATISFIED, SI.ACTOR))
    finally:
        SI.closed_by_standing_authority = orig
    assert not _owner_closed(db, _closed_row(db, "k7", owner_queue.SATISFIED, SI.ACTOR))


def test_finance_spend_authority_needs_an_owner_closure():
    from brambleloop.finance.accounting import policy

    db = _db()
    ok = _closed_row(db, "spend:ok", owner_queue.SATISFIED, "owner", max_cost=10.0)
    bad = _closed_row(db, "spend:bad", owner_queue.SATISFIED, SI.ACTOR, max_cost=10.0)
    wd = _closed_row(db, "spend:wd", owner_queue.WITHDRAWN, "owner", max_cost=10.0)

    def run(key):
        with db.session() as s:
            return policy._authority(s, {"authority": {"type": "owner_action", "ref": key},
                                         "amount_cad": 1.0})[0]

    assert run("spend:ok") is True
    assert run("spend:bad") is False and run("spend:wd") is False
    orig = SI.owner_closed
    SI.owner_closed = lambda s, r, states=None: bool(r.done)       # mutation: the old check
    try:
        assert run("spend:bad") is True and run("spend:wd") is True
    finally:
        SI.owner_closed = orig
    assert ok and bad and wd


def test_reengineer_job_ignores_a_standing_authority_closure():
    from brambleloop.runtime import engineering_ops as E

    db = _db()
    ok = _closed_row(db, E.REENGINEER_CARD, owner_queue.SATISFIED, "owner")

    class _Job:
        def __init__(self, aid):
            self.inputs = {"owner_action_id": aid, "slugs": []}

    class _Ctx:
        def __init__(self, aid):
            self.db, self.job = db, _Job(aid)

    def ran(aid):
        return E.handle_cir_reengineer(_Ctx(aid)).get("ran") is not False

    assert ran(ok)
    with db.session() as s:
        s.get(OwnerAction, ok).requirement_key = "other"       # one card per key at a time
    standing = _closed_row(db, E.REENGINEER_CARD, owner_queue.SATISFIED, SI.ACTOR)
    assert not ran(standing)
    orig = SI.owner_closed
    SI.owner_closed = lambda s, r, states=None: bool(r.done)       # mutation: card.done
    try:
        assert ran(standing)
    finally:
        SI.owner_closed = orig


def test_listing_package_does_not_read_a_standing_withdrawal_as_the_owners():
    from brambleloop.publish import listing_package as LP

    db = _db()
    owner = _closed_row(db, "listing_package:a@1:x", owner_queue.WITHDRAWN, "owner")
    standing = _closed_row(db, "listing_package:b@1:x", owner_queue.WITHDRAWN, SI.ACTOR)
    states = LP._owner_closed()
    assert _owner_closed(db, owner, states) and not _owner_closed(db, standing, states)
    src = open(LP.__file__).read()
    assert "_si.owner_closed(s, r, _OWNER_CLOSED)" in src          # mutation: the old state test
    assert "r.state in _OWNER_CLOSED" not in src


def test_not_ready_publication_is_labelled_by_its_true_class():
    v = OQC.card_verdict({"card_id": "publication:x", "kind": "PUBLICATION",
                          "executable": False})
    assert v["class"] == SI.PUBLICATION and v["disposition"] == SI.ROUTINE_INTERNAL
    assert v["not_ready"] is True
    ready = OQC.card_verdict({"card_id": "publication:x", "kind": "PUBLICATION",
                              "executable": True})
    assert ready["disposition"] == SI.GENUINE_EXCEPTION and not ready.get("not_ready")
    b = OQC.exception_batch([{"card_id": "p", "kind": "PUBLICATION", "executable": False}])
    assert b["covered_by_class"] == {SI.PUBLICATION: 1} and b["not_ready_publication"] == 1
    assert "publication_not_ready" not in b["covered_by_class"]


def test_supersedes_that_approve_nothing_are_counted_apart():
    db = _db()
    _add(db, "improve.challenger_run:7")
    _add(db, "taxonomy_drift:seven")
    _add(db, "store:etsy.openapi_review")
    _add(db, "model.routes_invalid")
    OQC.sweep(db, now=NOW)
    c = OQC.counts(db, now=NOW + timedelta(minutes=5))
    assert c["routine_auto_approved_24h"] == 2
    assert c["routine_superseded_nothing_approved_24h"] == 2
    orig = SI.NO_APPROVAL_PREFIXES
    SI.NO_APPROVAL_PREFIXES = ()                                   # mutation: lump them in
    try:
        assert OQC.counts(db, now=NOW + timedelta(minutes=5))["routine_auto_approved_24h"] == 4
    finally:
        SI.NO_APPROVAL_PREFIXES = orig


def test_audit_rows_carry_the_injected_clock_not_the_wall_clock():
    db = _db()
    _add(db, "model.routes_invalid")
    OQC.sweep(db, now=NOW)
    with db.session() as s:
        ats = [r.at.replace(tzinfo=timezone.utc) if r.at.tzinfo is None else r.at
               for r in s.scalars(select(AuditLog))]
    assert ats and all(a == NOW for a in ats), ats


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
