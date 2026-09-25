"""The Etsy surface registry, and the specific lies it is built to make impossible.

Every check here corresponds to a way this registry could look right and be wrong. Four of
them are proved against an injected defect: the naive implementation is written out, asserted
to reproduce the failure, and then the real code is asserted to refuse it. A test that only
ever sees the passing input does not establish that the rule is doing anything.

The defects proved here, in order of how easy they would be to write by accident:

1. A field missing from a snapshot read as a pass (`_naive_shop_check`).
2. An unread listing census read as "nothing has changed" (`_naive_census`).
3. An UNSUPPORTED verdict resting on nobody having looked, rather than on a counted absence.
4. A surface citing an Etsy endpoint that does not exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import pricing, shop_package  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402

DAY = 86400.0
NOW = 1_800_000_000.0


# ---- the registry holds ---------------------------------------------------


def test_the_registry_passes_its_own_invariants():
    assert es.check_registry() == []


def test_every_surface_the_brief_named_is_classified_exactly_once():
    """The brief listed the Shop Manager surfaces by name. None may be quietly dropped."""
    required = {
        "dashboard", "listings", "messages", "orders", "search_visibility", "stats",
        "marketplace_insights", "customer_service_stats", "policy_violations", "etsy_ads",
        "offsite_ads", "sales_and_discounts", "social_media", "share_and_save",
        "payment_account", "monthly_statements", "payment_settings", "legal_and_tax",
        "apps", "help", "your_shop", "info_and_appearance", "options", "shared_access",
        "delivery_settings", "policy_settings", "production_partners", "subscription",
        "sales_channels",
    }
    missing = required - set(es.SURFACES)
    assert not missing, f"surfaces named in the brief and not registered: {sorted(missing)}"
    keys = [s.key for s in es.surfaces()]
    assert len(keys) == len(set(keys))
    for s in es.surfaces():
        assert s.verdict in es.VERDICTS


def test_every_verdict_rests_on_at_least_one_document_this_build_read():
    """No surface may be classified entirely on hearsay or on our own opinion."""
    for s in es.surfaces():
        assert s.primary_evidence, (
            f"{s.key} is classified {s.verdict} with no primary evidence: every statement "
            f"behind it is secondary, inferred or a decision of ours")


def test_a_secondary_claim_names_a_source_this_environment_could_not_read():
    """Where the registry relies on help.etsy.com it must say the page refused us."""
    secondaries = [(s.key, e) for s in es.surfaces() for e in s.evidence
                   if e.kind == es.SECONDARY_CLAIM]
    assert secondaries, "the registry claims to have read everything, which is not true"
    for key, e in secondaries:
        source = es.SOURCES[e.source]
        assert not source.readable, (
            f"{key}: a SECONDARY claim citing {e.source}, which this build read successfully "
            f"-- if it was readable the claim is primary and should say so")


# ---- UNSUPPORTED and NOT_APPLICABLE are different claims ------------------


def test_unsupported_and_not_applicable_are_never_the_same_verdict():
    """The distinction the brief insisted on, asserted rather than described.

    UNSUPPORTED says Etsy offers nothing. NOT_APPLICABLE says the surface has nothing to do
    with a digital-pattern shop. Delivery Settings is the proof that they are different:
    Etsy ships a full shipping-profile CRUD and it is still irrelevant to us.
    """
    delivery = es.SURFACES["delivery_settings"]
    assert delivery.verdict == es.NOT_APPLICABLE
    assert delivery.operations, "delivery settings has endpoints; that is the whole point"
    assert "physical" in " ".join(e.statement for e in delivery.evidence)

    ads = es.SURFACES["etsy_ads"]
    assert ads.verdict == es.UNSUPPORTED
    assert ads.operations == ()

    for s in es.surfaces():
        if s.verdict == es.UNSUPPORTED:
            assert s.not_applicable_because is None
        if s.verdict == es.NOT_APPLICABLE:
            assert (s.not_applicable_because or "").strip()


def test_every_unsupported_verdict_names_a_counted_absence():
    for s in es.by_verdict(es.UNSUPPORTED):
        absences = [e for e in s.evidence if e.kind == es.OPENAPI_ABSENCE]
        assert absences, f"{s.key}: UNSUPPORTED with no counted absence"
        for e in absences:
            assert e.source == "openapi"


def test_injected_defect_an_unsupported_verdict_with_no_absence_probe_is_refused():
    """Defect 3: the verdict that says 'no API' because nobody looked for one."""
    bad = es.Surface(
        key="invented", name="Invented", where="nowhere", what="nothing",
        verdict=es.UNSUPPORTED,
        evidence=(es.Evidence(es.INFERRED, "we could not think of an endpoint", "openapi"),),
    )
    problems = es.check_registry([bad])
    assert any("no recorded absence probe" in p for p in problems), problems

    # ...and the same surface with a counted absence passes, so the rule is the probe and
    # not something incidental about the fixture.
    good = es.Surface(
        key="invented", name="Invented", where="nowhere", what="nothing",
        verdict=es.UNSUPPORTED,
        evidence=(es.Evidence(es.OPENAPI_ABSENCE, "'invented' 0", "openapi"),),
    )
    assert es.check_registry([good]) == []


def test_injected_defect_an_endpoint_that_does_not_exist_is_refused():
    """Defect 4: a plausible-looking operation name nobody could ever call."""
    bad = es.Surface(
        key="stats_but_real", name="Stats", where="Shop Manager > Stats", what="traffic",
        verdict=es.OBSERVE, operations=("getShopStats",),
        evidence=(es.Evidence(es.OPENAPI_SAYS, "surely", "openapi"),),
    )
    problems = es.check_registry([bad])
    assert any("an endpoint we invented" in p for p in problems), problems


def test_injected_defect_an_owner_only_surface_with_nothing_asked_of_the_owner():
    bad = es.Surface(
        key="shrug", name="Shrug", where="somewhere", what="something",
        verdict=es.OWNER_ONLY,
        evidence=(es.Evidence(es.INFERRED, "a person must do it", "openapi"),),
    )
    problems = es.check_registry([bad])
    assert any("OWNER_ONLY with no owner action" in p for p in problems), problems


def test_injected_defect_a_first_sale_blocker_filed_as_post_launch_work():
    bad = es.Surface(
        key="later", name="Later", where="somewhere", what="something",
        verdict=es.ACT, operations=("updateShop",),
        evidence=(es.Evidence(es.OPENAPI_SAYS, "it writes", "openapi"),),
        required_before_first_sale=True, requirement_basis=es.BY_ETSY,
        why_required="it is", work_class=es.CLASS_C,
    )
    problems = es.check_registry([bad])
    assert any("classed C" in p for p in problems), problems


# ---- reproducible absence -------------------------------------------------


def _synthetic_document() -> str:
    """A document whose term counts match the registry's recorded ones exactly."""
    parts = []
    for term, (count, _why) in sorted(es.ABSENCE_PROBES.items()):
        parts.extend([term] * count)
    return " | ".join(parts)


def test_the_absence_probes_reproduce_against_a_document_that_matches_them():
    assert es.verify_absence(_synthetic_document()) == []


def test_an_ads_api_appearing_is_reported_rather_than_aged_into_a_lie():
    """The registry's negative half has to be falsifiable by the next document."""
    doc = _synthetic_document() + (
        " Etsy Ads: create an advertising campaign with a daily budget and read its "
        "impression count")
    drift = es.verify_absence(doc)
    terms = {d["term"]: d for d in drift}
    for term in ("advertis", "campaign", "budget", "impression"):
        assert term in terms, f"{term} appeared and the registry did not notice"
        assert terms[term]["direction"] == "appeared"
        assert terms[term]["expected"] == 0


def test_a_capability_being_withdrawn_is_reported_too():
    doc = _synthetic_document().replace("keyword | ", "", 5)
    drift = {d["term"]: d for d in es.verify_absence(doc)}
    assert drift["keyword"]["direction"] == "vanished"
    assert drift["keyword"]["actual"] == 13


def test_the_document_the_registry_was_read_from_is_identified_by_hash():
    assert len(es.OPENAPI_SHA256) == 64
    assert es.document_fingerprint("") != es.OPENAPI_SHA256
    assert es.SOURCES["openapi"].sha256 == es.OPENAPI_SHA256
    assert es.SOURCES["openapi"].readable


# ---- scopes ---------------------------------------------------------------


def test_the_orders_surface_is_a_read_this_shop_is_not_authorised_to_make():
    """The finding that matters most for the first sale, asserted as arithmetic.

    Etsy offers the read. The grant this shop holds does not include it. Those are different
    facts, and a registry that reported only the first would say this system can see its own
    orders, which it cannot.
    """
    orders = es.SURFACES["orders"]
    assert orders.verdict == es.OBSERVE
    assert "getShopReceipts" in orders.operations
    assert orders.missing_scopes(es.GRANTED_SCOPES) == ("transactions_r",)
    assert orders.missing_scopes(es.GRANTED_SCOPES + ("transactions_r",)) == ()

    gaps = {g["surface"]: g for g in es.scope_gaps()}
    assert "orders" in gaps and "payment_account" in gaps
    assert gaps["orders"]["meanings"] == ["see all checkout/payment data"]


def test_no_surface_claims_a_scope_etsy_does_not_publish():
    for s in es.surfaces():
        for scope in s.scopes:
            assert scope in es.SCOPE_MEANINGS, f"{s.key}: invented scope {scope!r}"


def test_widening_the_grant_closes_the_gaps_and_nothing_else():
    widened = es.GRANTED_SCOPES + ("transactions_r",)
    assert es.scope_gaps(widened) == []


# ---- evidence state: emptiness is never a pass ----------------------------


def test_a_surface_with_no_collector_says_so_rather_than_saying_fine():
    ads = es.SURFACES["etsy_ads"]
    assert ads.collector is None
    assert es.evidence_state(ads, None, now=NOW) == es.NO_COLLECTOR


def test_a_collector_that_has_never_run_is_not_the_same_as_a_clean_run():
    shop = es.SURFACES["policy_settings"]
    assert shop.collector == "shop_snapshot"
    assert es.evidence_state(shop, None, now=NOW) == es.NO_EVIDENCE
    assert es.evidence_state(shop, {}, now=NOW) == es.NO_EVIDENCE
    assert es.evidence_state(shop, {"observed_at": NOW}, now=NOW) == es.FRESH
    assert es.evidence_state(shop, {"observed_at": NOW - 30 * DAY}, now=NOW) == es.STALE
    # A record from the future is a clock fault, and a clock fault is not freshness.
    assert es.evidence_state(shop, {"observed_at": NOW + DAY}, now=NOW) == es.STALE


# ---- collector 1: the shop snapshot ---------------------------------------


def _good_shop() -> dict:
    return {
        "icon_url_fullxfull": "https://i.etsystatic.com/icon.jpg",
        "image_url_760x100": "https://i.etsystatic.com/banner.jpg",
        "title": "Machine-checked crochet patterns",
        "announcement": "Every pattern is compiled and checked before release.",
        "digital_sale_message": "Your file is on your Purchases page. If anything is "
                                "wrong, reply to this message.",
        "policy_payment": "Etsy handles payment and tax at checkout.",
        "policy_shipping": "Nothing is posted; the file downloads immediately.",
        "policy_refunds": "Digital items cannot be returned. Here is what we do instead.",
        "policy_privacy": "Buying does not put you on a list.",
        "policy_additional": "Licence and AI disclosure.",
        "is_etsy_payments_onboarded": True,
        "is_vacation": False,
        "currency_code": "CAD",
        "digital_listing_count": 3,
    }


def _naive_shop_check(body: dict) -> bool:
    """The defect: a field that is not in the response defaults to 'fine'.

    This is not a strawman. `body.get(field, DEFAULT)` with any truthy default is the
    shortest way to write this function, and it turns a partial read into a clean bill of
    health -- which is the exact failure this repository keeps committing.
    """
    for key, field_name, kind, _expect, _why in es.SHOP_CHECKS:
        if kind == "nonblank" and not body.get(field_name, "assume it is set"):
            return False
    return True


def test_injected_defect_a_field_nobody_read_must_not_read_as_a_pass():
    """Defect 1, reproduced and then refused."""
    partial = _good_shop()
    for field_name in ("policy_payment", "policy_shipping", "policy_refunds",
                       "policy_privacy"):
        partial.pop(field_name)

    # The defect reproduces: the naive check sees no problem at all.
    assert _naive_shop_check(partial) is True

    # The real collector calls it what it is.
    status = es.assess_shop({"observed_at": NOW, "shop": partial}, now=NOW)
    unevidenced = {c.key for c in status.unevidenced}
    assert unevidenced == {"policy_payment_set", "policy_shipping_set",
                           "policy_refunds_set", "policy_privacy_set"}
    assert not status.failures
    assert status.green is False


def test_a_policy_etsy_returned_as_null_is_a_failure_not_an_unknown():
    body = _good_shop()
    body["policy_refunds"] = None
    status = es.assess_shop({"observed_at": NOW, "shop": body}, now=NOW)
    failed = {c.key for c in status.failures}
    assert failed == {"policy_refunds_set"}
    assert not status.unevidenced
    assert status.green is False


def test_an_empty_shop_body_is_no_evidence_on_every_check_and_never_green():
    status = es.assess_shop({"observed_at": NOW, "shop": {}}, now=NOW)
    assert status.evidence_state == es.FRESH
    assert len(status.unevidenced) == len(es.SHOP_CHECKS)
    assert status.green is False


def test_no_snapshot_at_all_is_no_evidence_and_says_which_kind_of_nothing():
    status = es.assess_shop(None, now=NOW)
    assert status.evidence_state == es.NO_EVIDENCE
    assert status.green is False
    assert "has ever been recorded" in status.note

    # A timestamp with no body is an empty observation, not an observation of an empty shop.
    status = es.assess_shop({"observed_at": NOW}, now=NOW)
    assert status.evidence_state == es.NO_EVIDENCE
    assert status.green is False


def test_a_correct_and_current_shop_is_the_only_thing_that_reads_green():
    status = es.assess_shop({"observed_at": NOW, "shop": _good_shop()}, now=NOW)
    assert status.evidence_state == es.FRESH
    assert not status.failures and not status.unevidenced
    assert status.green is True


def test_an_old_reading_describes_the_shop_as_it_was_and_is_not_green():
    status = es.assess_shop({"observed_at": NOW - 30 * DAY, "shop": _good_shop()}, now=NOW)
    assert status.evidence_state == es.STALE
    assert not status.failures
    assert status.green is False, "a clean reading from a month ago is not a clean shop"
    assert "days old" in status.note


def test_the_settings_that_silently_stop_every_sale_are_checked():
    on_holiday = _good_shop()
    on_holiday["is_vacation"] = True
    assert {c.key for c in
            es.assess_shop({"observed_at": NOW, "shop": on_holiday},
                           now=NOW).failures} == {"not_on_vacation"}

    wrong_currency = _good_shop()
    wrong_currency["currency_code"] = "USD"
    assert {c.key for c in
            es.assess_shop({"observed_at": NOW, "shop": wrong_currency},
                           now=NOW).failures} == {"currency_is_cad"}

    no_listings = _good_shop()
    no_listings["digital_listing_count"] = 0
    assert {c.key for c in
            es.assess_shop({"observed_at": NOW, "shop": no_listings},
                           now=NOW).failures} == {"has_a_digital_listing"}


def test_a_boolean_check_will_not_accept_something_merely_truthy():
    """`is_etsy_payments_onboarded: 1` is not the same fact as `true`, and payouts depend
    on it, so the check compares identity rather than truthiness."""
    body = _good_shop()
    body["is_etsy_payments_onboarded"] = 1
    status = es.assess_shop({"observed_at": NOW, "shop": body}, now=NOW)
    assert {c.key for c in status.failures} == {"etsy_payments_onboarded"}


def test_the_owner_actions_that_close_on_a_reading_actually_have_one():
    """Each manual action whose evidence is a getShop field must have that field checked."""
    checked_fields = {field for _k, field, _kind, _e, _w in es.SHOP_CHECKS}
    for key in ("info_and_appearance", "policy_settings", "payment_settings"):
        action = es.SURFACES[key].owner_action
        assert action is not None
        assert "getShop" in action.evidence_required
    assert "icon_url_fullxfull" in checked_fields
    assert "image_url_760x100" in checked_fields
    assert "is_etsy_payments_onboarded" in checked_fields


# ---- collector 2: the listing census --------------------------------------


def _naive_census(expected: dict, observed) -> list:
    """The defect: a fetch that returned nothing is read as a shop with nothing wrong."""
    if not observed:
        return []
    seen = {str(r["listing_id"]) for r in observed}
    return [k for k in expected if k not in seen]


def test_injected_defect_an_unread_census_must_not_read_as_no_drift():
    """Defect 2, reproduced and then refused."""
    expected = {"101": "active", "102": "active"}

    # The defect reproduces: nothing observed, nothing reported, everything looks fine.
    assert _naive_census(expected, None) == []

    status = es.listing_census_drift(expected, None)
    assert status.evidence_state == es.NO_EVIDENCE
    assert status.green is False
    assert "not the same as nothing being wrong" in status.note


def test_a_listing_that_has_vanished_raises_an_alarm_and_refuses_to_say_why():
    expected = {"101": "active", "102": "active"}
    observed = [{"listing_id": 101, "state": "active"}]
    status = es.listing_census_drift(expected, observed, observed_at=NOW, now=NOW)
    failures = {c.key: c.detail for c in status.failures}
    assert set(failures) == {"listing_102"}
    detail = failures["listing_102"]
    assert "Policy Violations" in detail
    assert "cannot tell a takedown from a deletion" in detail
    assert status.green is False


def test_a_listing_deactivated_behind_our_back_is_drift_too():
    status = es.listing_census_drift({"101": "active"},
                                     [{"listing_id": 101, "state": "inactive"}],
                                     observed_at=NOW, now=NOW)
    assert {c.key for c in status.failures} == {"listing_101"}


def test_a_listing_nobody_here_created_is_reported():
    status = es.listing_census_drift({"101": "active"},
                                     [{"listing_id": 101, "state": "active"},
                                      {"listing_id": 999, "state": "active"}],
                                     observed_at=NOW, now=NOW)
    assert {c.key for c in status.failures} == {"unexpected_999"}
    assert "did not create" in status.failures[0].detail


def test_holding_no_record_of_our_own_listings_is_not_a_clean_census():
    """An empty expectation compared against an empty shop looks perfect and means nothing."""
    status = es.listing_census_drift({}, [], observed_at=NOW, now=NOW)
    assert {c.key for c in status.unevidenced} == {"census_known"}
    assert status.green is False


def test_a_matching_current_census_is_green():
    status = es.listing_census_drift({"101": "active"},
                                     [{"listing_id": 101, "state": "active"}],
                                     observed_at=NOW, now=NOW)
    assert status.evidence_state == es.FRESH
    assert status.green is True


def test_an_old_census_is_not_a_current_one():
    status = es.listing_census_drift({"101": "active"},
                                     [{"listing_id": 101, "state": "active"}],
                                     observed_at=NOW - 5 * DAY, now=NOW)
    assert status.evidence_state == es.STALE
    assert status.green is False


# ---- the owner queue ------------------------------------------------------


def test_every_owner_action_is_actionable_and_closes_on_evidence():
    queue = es.owner_queue()
    assert queue, "a registry with ten OWNER_ONLY surfaces and no owner queue"
    keys = [a.key for a in queue]
    assert len(keys) == len(set(keys))
    for a in queue:
        assert a.minutes > 0
        assert a.action.strip() and a.why_software_cannot.strip()
        assert a.evidence_required.strip()
        assert a.risk.strip()
        assert a.surface in es.SURFACES


def test_the_first_sale_blockers_come_first_and_are_the_ones_that_block():
    queue = es.owner_queue()
    blockers = [a for a in queue if a.blocks_first_sale]
    assert [a.key for a in queue[:len(blockers)]] == [a.key for a in blockers]
    assert {a.key for a in blockers} == {
        "payment_settings_setup", "legal_and_tax_setup",
        "policy_settings_paste", "info_and_appearance_setup"}
    assert es.owner_queue(first_sale_only=True) == blockers


def test_no_owner_action_pretends_software_could_have_done_it():
    """Each entry has to say what stops automation, not that nobody got round to it."""
    for a in es.owner_queue():
        reason = a.why_software_cannot.lower()
        assert any(marker in reason for marker in
                   ("no ", "not ", "only", "browser", "portal", "identity")), a.key


def test_the_scope_re_authorisation_is_an_owner_action_rather_than_a_build_task():
    action = es.SURFACES["orders"].owner_action
    assert action is not None and action.key == "reauthorise_transactions_r"
    assert "transactions_r" in action.action
    assert "browser" in action.why_software_cannot
    assert not action.blocks_first_sale, (
        "a sale can complete without this; what it blocks is everything after the sale, and "
        "overstating it would put a non-blocker at the top of the owner's list")


# ---- A / B / C / D --------------------------------------------------------


def test_the_work_plan_uses_all_four_classes_and_keeps_a_for_real_blockers():
    plan = es.work_plan()
    for cls in (es.CLASS_A, es.CLASS_B, es.CLASS_C, es.CLASS_D):
        assert plan[cls], f"class {cls} is empty, so the classification is not doing work"
    for key in plan[es.CLASS_A]:
        assert es.SURFACES[key].required_before_first_sale, (
            f"{key} is class A without being a first-sale blocker; that is how every "
            f"improvement becomes a launch blocker")
    for key in plan[es.CLASS_D]:
        assert not es.SURFACES[key].required_before_first_sale


def test_the_first_sale_blockers_are_the_ones_a_shop_cannot_open_without():
    keys = {s.key for s in es.first_sale_blockers()}
    assert keys == {"listings", "messages", "orders", "payment_settings", "legal_and_tax",
                    "your_shop", "info_and_appearance", "options", "policy_settings",
                    "digital_files", "taxonomy_and_attributes"}
    for s in es.first_sale_blockers():
        assert s.requirement_basis in (es.BY_ETSY, es.BY_US, es.BY_LAW)
        assert s.why_required.strip()


def test_what_is_still_unknown_is_recorded_rather_than_filled_in():
    unknowns = es.coverage()["unknowns"]
    assert "taxonomy_and_attributes" in unknowns
    assert any("66" in u for u in unknowns["taxonomy_and_attributes"])
    assert "webhooks" in unknowns


# ---- consistency with the rest of the repository --------------------------


def test_every_manual_action_shop_package_lists_has_a_surface_that_owns_it():
    assert es.manual_only_consistency(shop_package.MANUAL_ONLY) == []


def test_injected_defect_a_manual_action_with_no_surface_is_reported():
    doctored = tuple(shop_package.MANUAL_ONLY) + (
        ("shop_video", "Shop Manager > Settings > Video"),)
    problems = es.manual_only_consistency(doctored)
    assert any("shop_video" in p for p in problems), problems


def test_a_manual_action_this_registry_still_maps_but_shop_package_dropped_is_reported():
    shortened = tuple(p for p in shop_package.MANUAL_ONLY if p[0] != "about_story")
    problems = es.manual_only_consistency(shortened)
    assert any("about_story" in p for p in problems), problems


# ---- the fee model this registry forced open ------------------------------


def test_a_take_rate_carries_the_fees_it_does_not_include():
    breakdown = pricing.fees(6.50)
    assert "offsite_ads" in breakdown.unmodelled
    payload = breakdown.to_dict()
    assert payload["take_rate_is_a_floor"] is True
    assert payload["unmodelled_fees"]


def test_the_unmodelled_fees_are_labelled_secondary_because_etsy_refuses_to_be_read():
    for key, _what, basis, rate, _when in pricing.UNMODELLED_FEES:
        assert basis.startswith("SECONDARY"), key
        assert 0 < rate < 1, key
    assert es.SOURCES["etsy_legal_fees"].http_status == 403


def test_the_worst_case_is_materially_worse_and_that_is_the_point():
    """If the gap were small the omission would not matter. It is not small."""
    price = 6.50
    modelled = pricing.fees(price)
    worst = pricing.worst_case_fees(price)
    assert worst["worst_case_take_rate"] > modelled.take_rate
    assert worst["worst_case_take_rate"] - modelled.take_rate > 0.15, (
        "the unmodelled fees move the take rate by less than fifteen points, which would "
        "mean this warning is noise -- check whether they have been folded in properly")
    assert worst["worst_case_net_cad"] < modelled.net_cad
    assert "Not a forecast" in worst["note"]


def test_a_price_decision_says_out_loud_that_its_take_rate_is_a_floor():
    decision = pricing.decide_price("cloudline-baby-blanket",
                                    category_band_cad=(4.0, 12.0), proposed_cad=6.50)
    joined = " ".join(decision.warnings)
    assert "offsite_ads" in joined
    assert "SECONDARY" in joined


def test_the_registry_and_the_fee_model_agree_about_why_this_is_unmodelled():
    """The reason the fee cannot simply be measured is a fact about Etsy's API."""
    offsite = es.SURFACES["offsite_ads"]
    assert offsite.verdict == es.UNSUPPORTED
    assert es.ABSENCE_PROBES["offsite"][0] == 0
    assert any("pricing" in e.statement for e in offsite.evidence)


def test_no_ad_spend_ceiling_can_be_enforced_in_code_and_the_registry_admits_it():
    """The Execution Directive requires ceilings in code. For this surface that is not
    available, and saying so is the only honest option."""
    ads = es.SURFACES["etsy_ads"]
    assert es.ABSENCE_PROBES["budget"][0] == 0
    assert any("ceiling" in e.statement for e in ads.evidence)
    assert ads.owner_action is not None


# ---- rendering ------------------------------------------------------------


def test_the_rendered_registry_reports_its_own_problems_rather_than_hiding_them():
    text = es.render()
    assert "Registry problems: 0" in text
    assert "OpenAPI 3.0.0" in text
    assert "transactions_r" in text
    assert "BLOCKER" in text


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
