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
    assert c["routine_auto_approved_24h"] == 3 and c["closed_automatically_24h"] == 1
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
    assert b["covered_by_class"] == {"engineering": 1, "publication_not_ready": 1}
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
    assert LC.opening_budget_refusal(db, "A", 6.00) is None
    assert LC.opening_budget_refusal(db, "A", 6.01) is not None
    assert LC.opening_budget_refusal(db, "A", -1.0) is not None
    _reserve(db, 1, amount=5.00)
    assert LC.opening_budget_refusal(db, "B", 1.00) is None
    assert LC.opening_budget_refusal(db, "B", 1.01) is not None
    # An observed fee for a listing never reserved counts; one for a reserved listing does not.
    with db.session() as s:
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee_actual",
                        amount_cad=0.30, detail={"listing_id": "L1"}))
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee_actual",
                        amount_cad=0.50, detail={"listing_id": "renewed-elsewhere"}))
    assert LC.opening_budget(db)["used_cad"] == 5.50
    assert LC.opening_budget_refusal(db, "C", 0.51) is not None


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
        for node in ast.walk(tree):
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


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
