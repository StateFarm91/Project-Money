"""The two credentials the owner approved, and the constraints they came with.

Etsy: current v3 authentication, secrets that stay in the hosting environment, and the
minimum access the read-only mission needs. Model provider: one integration, a hard CA$25 per
month enforced in code, routed by capability and cost, cached where content has not changed,
and never asked to write canonical pattern content.

Both approvals were conditional, so the conditions are what these tests are about.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402
from brambleloop.intel import etsy_public as ep  # noqa: E402

KEY = "keystring-abcdef123456"
SECRET = "shared-secret-should-never-leak"


@dataclass
class FakeResponse:
    status: int
    body: dict


class FakeTransport:
    """Records what was sent so the tests can assert on headers and URLs."""

    def __init__(self, pages: list[dict] | None = None, status: int = 200):
        self.pages = pages or [{}]
        self.status = status
        self.seen: list[tuple[str, dict]] = []

    def request(self, method: str, url: str, *, headers: dict, body: Any = None,
                timeout: float = 20.0) -> FakeResponse:
        self.seen.append((url, dict(headers)))
        page = self.pages[min(len(self.seen) - 1, len(self.pages) - 1)]
        return FakeResponse(self.status, page)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/models.sqlite")
    db.create_all()
    return db


# ---- Etsy: the owner's correction ----------------------------------------


def test_the_api_key_header_is_keystring_and_shared_secret():
    """The owner caught this, and it was wrong in two places.

    Etsy v3: "Every request to a v3 endpoint must include an x-api-key header containing your
    keystring and shared secret separated by a colon." A keystring-only header is accepted as
    a header and refused as a credential, so the first real call returns 401 and every
    explanation for a 401 is plausible — which costs a diagnosis round rather than failing in
    a way that names itself.
    """
    transport = FakeTransport()
    reader = ep.PublicReader(transport, env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    reader.get("ping")

    _, headers = transport.seen[0]
    assert headers["x-api-key"] == f"{KEY}:{SECRET}"

    # The publishing client had the same defect.
    from brambleloop.integrations.etsy import Credentials

    creds = Credentials.from_env({"ETSY_API_KEY": KEY, "ETSY_ACCESS_TOKEN": "t",
                                  "ETSY_SHOP_ID": "1", "ETSY_SHARED_SECRET": SECRET})
    assert creds.headers()["x-api-key"] == f"{KEY}:{SECRET}"


def test_a_missing_shared_secret_is_visible_rather_than_silently_dropped():
    """Falling back to the keystring alone produces an indistinguishable 401.

    The health report names the missing variable, and the failure message points at it, so
    the first thing anybody reads is the actual cause.
    """
    health = ep.health({ep.KEYSTRING_VAR: KEY})
    assert health["usable"] is False
    assert ep.SECRET_VAR in health["reason"]
    assert "keystring:shared_secret" in health["reason"]

    assert ep.health({})["reason"] == "neither variable is set"
    assert ep.health({ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})["usable"] is True

    # A 401 says what to check rather than leaving six equally plausible causes.
    reader = ep.PublicReader(FakeTransport(status=401),
                             env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: ""})
    try:
        reader.get("ping")
    except ep.ReadFailed as e:
        assert ep.SECRET_VAR in str(e)
    else:
        raise AssertionError("a 401 passed silently")


def test_the_mission_asks_for_no_scope_it_does_not_need():
    """"Do not request write/private scopes merely because we may eventually need them."

    An allowlist rather than a policy: "we only use the public endpoints" is a sentence, and a
    sentence does not stop the commit that adds one more. Every endpoint below is marked
    api_key-only in Etsy's own OpenAPI specification.
    """
    transport = FakeTransport()
    reader = ep.PublicReader(transport, env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})

    for forbidden in ("create_listing", "get_me", "shop_receipts", "update_listing",
                      "getShopPaymentAccountLedgerEntries"):
        try:
            reader.get(forbidden)
        except ep.EndpointRefused:
            pass
        else:
            raise AssertionError(f"{forbidden!r} was callable")
    assert transport.seen == [], "a refused endpoint still built a request"

    # And no code path can send an OAuth token: the header map has no Authorization key.
    reader.get("ping")
    _, headers = transport.seen[0]
    assert "Authorization" not in headers
    assert ep.capability_report({})["oauth_scopes_requested"] == []


def test_a_near_match_is_not_the_named_shop():
    """`findShops` is a search, so it answers with neighbours.

    Same hazard as following a redirect to a different seller (#206): the mandate names one
    shop, and a plausible near match silently re-points the whole mission at a stranger.
    """
    exact = {"results": [{"shop_name": "MJsOffTheHookDesignsCo", "shop_id": 1},
                         {"shop_name": "MJsOffTheHookDesigns", "shop_id": 2}]}
    reader = ep.PublicReader(FakeTransport([exact]),
                             env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    assert reader.resolve_shop("MJsOffTheHookDesigns")["shop_id"] == 2

    near = {"results": [{"shop_name": "MJsOffTheHookDesignsShop", "shop_id": 9}]}
    reader = ep.PublicReader(FakeTransport([near]),
                             env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    try:
        reader.resolve_shop("MJsOffTheHookDesigns")
    except ep.ReadFailed as e:
        assert "near match is a different seller" in str(e)
    else:
        raise AssertionError("a near match was accepted as the named benchmark")


def test_the_catalogue_is_enumerated_completely_rather_than_sampled():
    """#207 asks for the complete discoverable catalogue, not the top listings."""
    pages = [
        {"count": 5, "results": [{"listing_id": 1}, {"listing_id": 2}]},
        {"count": 5, "results": [{"listing_id": 3}, {"listing_id": 4}]},
        {"count": 5, "results": [{"listing_id": 5}]},
    ]
    transport = FakeTransport(pages)
    reader = ep.PublicReader(transport, env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    listings = reader.catalogue(2, limit=2)

    assert [x["listing_id"] for x in listings] == [1, 2, 3, 4, 5]
    assert "offset=2" in transport.seen[1][0]
    assert "offset=4" in transport.seen[2][0]


def test_the_credential_never_appears_in_the_evidence_trail():
    """Secrets stay Railway-side: not in GitHub, logs, BUILD_STATE or benchmark evidence."""
    transport = FakeTransport(status=500)
    reader = ep.PublicReader(transport, env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    try:
        reader.get("ping")
    except ep.ReadFailed as e:
        assert SECRET not in str(e) and KEY not in str(e)

    # The call trail records which endpoint, never which credential.
    assert all(SECRET not in call and KEY not in call for call in reader.calls)
    assert SECRET not in repr(reader.credential)
    assert SECRET not in str(ep.health({ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET}))
    assert SECRET not in str(ep.capability_report({ep.KEYSTRING_VAR: KEY,
                                                   ep.SECRET_VAR: SECRET}))


def test_the_capability_report_names_the_gap_rather_than_claiming_coverage():
    """#224: report the exact missing capability and a compliant alternative.

    The sanctioned API covers more of the mandate than expected. What it cannot do is the
    rendered page, and saying so is the requirement.
    """
    report = ep.capability_report({})
    assert "enumerate_full_catalogue" in report["covered_by_the_sanctioned_api"]
    assert "gallery_asset_inventory" in report["covered_by_the_sanctioned_api"]

    gaps = report["not_covered"]
    assert "rendered_page_presentation" in gaps
    assert "image_level_visual_judgement" in gaps
    for gap in gaps.values():
        assert gap["gap"] and gap["alternative"], "a gap with no proposed alternative"
    assert "unmet" in gaps["rendered_page_presentation"]["alternative"]


# ---- the model ceiling ----------------------------------------------------


def test_the_ceiling_is_checked_before_the_call_not_after():
    """A ceiling checked afterwards is a report about an overspend.

    The owner approved a maximum. So the refusal happens while the money is still unspent,
    and there is no override parameter — raising it is an owner decision.
    """
    db = _db()
    assert routing.budget(db).remaining_cad == 25.0
    routing.check(db, "benchmark_challenge")

    # Spend the month.
    for _ in range(200):
        routing.record(db, "benchmark_challenge", agent="quality_director",
                       tokens_in=6000, tokens_out=2500)

    state = routing.budget(db)
    assert state.spent_cad > 25.0 or state.remaining_cad == 0.0
    try:
        routing.check(db, "benchmark_challenge")
    except routing.CeilingReached as e:
        assert "owner decision" in str(e)
        assert "measured usage" in str(e)
    else:
        raise AssertionError("a call was permitted past the approved ceiling")


def test_a_model_may_never_be_asked_what_the_compiler_answers():
    """The rule that outranks the budget.

    Patterns are software releases. A model asked for stitch counts is being asked to guess
    at something the twin computes, and a cheap wrong answer is worse than an expensive one.
    """
    db = _db()
    for question in routing.PATTERN_TASKS_REFUSED:
        try:
            routing.route(question)
        except routing.TaskRefused as e:
            assert "deterministic" in str(e)
        else:
            raise AssertionError(f"a model was allowed to answer {question!r}")

    # An undeclared task is refused too: the ceiling can only be checked before a call whose
    # cost is known, and an unlisted task has no estimate.
    try:
        routing.route("have_a_guess")
    except routing.TaskRefused as e:
        assert "declared model task" in str(e)
    else:
        raise AssertionError("an undeclared task was routed")

    # Refusal does not depend on there being budget left.
    assert routing.budget(db).remaining_cad == 25.0


def test_work_is_routed_by_what_it_actually_needs():
    """"Start economically. Route tasks by capability/cost."

    Reading a title into a category and judging whether a photograph makes a garment look
    desirable are different questions. Paying the same rate for both is how CA$25 becomes
    CA$60.
    """
    _, cheap = routing.route("listing_classify")
    _, standard = routing.route("gallery_observation")
    _, deep = routing.route("benchmark_challenge")

    assert cheap.model == "claude-haiku-4-5"
    assert standard.model == "claude-sonnet-5"
    assert deep.model == "claude-opus-5"
    assert (routing.estimate_cad("listing_classify")
            < routing.estimate_cad("gallery_observation")
            < routing.estimate_cad("benchmark_challenge"))

    # The release-blocking judgement gets the best model, and it is still affordable -- the
    # ceiling buys dozens a month against a company that releases a handful of patterns.
    #
    # This number used to read "> 100" and it passed on a price that was a third of the real
    # one: routing restated the deep tier at USD 5/25 per million tokens while the provider
    # billed 15/75. The estimates are read from the billing table now, so CA$25 buys about 64
    # of these rather than the 192 this test used to believe. A budget assertion that passes
    # on the wrong price is worse than no budget assertion, because it is the number somebody
    # decides on.
    assert 25.0 / routing.estimate_cad("benchmark_challenge") > 50
    assert 25.0 / routing.estimate_cad("listing_classify") > 1000

    # Every declared task has a vision-capable tier, since gallery work is the whole mandate.
    for task in routing.TASKS.values():
        assert routing.TIERS[task.tier].vision is True


def test_unchanged_evidence_is_never_paid_for_twice():
    """#225, and the largest lever there is.

    Competitor evidence barely moves between runs. The key is the content itself, so a cache
    entry cannot go stale — a changed listing has a different fingerprint and simply misses.
    """
    db = _db()
    listing = {"listing_id": 1825269747, "title": "Cropped Cardigan", "price": 8.5}

    assert routing.cached_analysis(db, "listing_mechanisms", listing) is None
    routing.remember_analysis(db, "listing_mechanisms", listing,
                              {"mechanisms": ["colour_architecture"]})
    assert routing.cached_analysis(db, "listing_mechanisms", listing) == {
        "mechanisms": ["colour_architecture"]}

    changed = {**listing, "price": 9.5}
    assert routing.cached_analysis(db, "listing_mechanisms", changed) is None

    # A cached answer costs nothing, and the ledger says so rather than quietly recording
    # tokens nobody spent.
    before = routing.budget(db).spent_cad
    assert routing.record(db, "listing_mechanisms", agent="market_radar",
                          tokens_in=2000, tokens_out=800, cached=True) == 0.0
    assert routing.budget(db).spent_cad == before


def test_the_cache_key_changes_when_the_routing_does():
    """Otherwise a downgrade would silently keep serving the better model's answers.

    Which would make a routing change invisible in exactly the direction that flatters it.
    """
    payload = {"listing_id": 1}
    key = routing.cache_key("gallery_observation", payload)
    assert routing.TIERS[routing.STANDARD].model in key
    assert key != routing.cache_key("listing_mechanisms", payload)


def test_the_plan_states_the_ceiling_as_a_maximum_and_names_its_fx_assumption():
    """A CAD ceiling against a bill charged in USD has to say which rate it assumed."""
    db = _db()
    plan = routing.plan(db)

    assert plan["budget"]["ceiling_cad"] == 25.0
    assert "not a target" in plan["budget"]["note"]
    assert "USD" in plan["fx"] and "0.715" in plan["fx"]
    assert set(plan["tasks"]) == set(routing.TASKS)
    assert "pattern_instructions" in plan["refused"]
    assert "compiler" in plan["note"]


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
