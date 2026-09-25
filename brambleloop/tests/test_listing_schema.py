"""Etsy's own contract for a digital-download listing, and the parts of it nothing checked.

The Etsy client was already tested against a fake transport, and every one of those tests
passed while the payload it produced could not be published. That is the shape of the failure
this suite is for: the limits the system enforces are its own reading of Etsy's limits, and
the ones it never read are enforced by Etsy, at the moment of the first real request, on the
day the phase moves.

What these tests defend:

- **A sourced clause keeps the sentence it came from.** A clause labelled sourced with
  nothing quoted is an assumption that has stopped being arguable, and it is refused at
  construction rather than reviewed later.
- **A draft is not a listing.** Etsy will not activate a listing with no image set, and
  nothing in this system uploads a listing image. The check says so in those words, because
  "not ready" would be read as a formality.
- **The character sets are narrower than a string.** Materials allow letters, digits and
  whitespace only, which means "100% cotton" is refused by Etsy and reads as unremarkable to
  everybody here. Titles allow %, :, & and + once each, which a template violates without
  anybody noticing.
- **The export the system actually produces is checked**, not a fixture written to pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.integrations.etsy import EtsyRejected, build_payload  # noqa: E402
from brambleloop.publish import listing_schema as S  # noqa: E402


GOOD = dict(title="Crochet Storage Basket | Crochet Pattern PDF | Written and Chart",
            description="A basket worked in the round from the centre of the base.",
            price_cad=6.50, tags=["crochet basket", "basket pattern"],
            materials=["worsted cotton"])


# ---- the evidence ----------------------------------------------------------


def test_a_sourced_clause_that_quotes_nothing_is_refused():
    """The label is the claim. Without a sentence behind it, it is a confident guess."""
    try:
        S.Clause("invented", "Etsy requires a haiku", S.SOURCED)
    except S.SchemaRefused as e:
        assert "quotes nothing" in str(e)
    else:
        raise AssertionError("a sourced clause was accepted with no sentence behind it")

    # And the inferred label is available for exactly this case, with no quote required.
    reasoned = S.Clause("reasoned", "a file has no meaningful stock level", S.INFERRED)
    assert reasoned.basis == S.INFERRED and reasoned.quote == ""


def test_every_clause_names_where_it_came_from_and_when():
    """A rule with no reading date is a claim about the past wearing the present tense."""
    assert S.CLAUSES, "the contract is empty"
    for clause in S.CLAUSES:
        record = clause.to_dict()
        assert record["read_from"] == S.ETSY_OPENAPI_URL
        assert record["read_on"] == S.READ_ON
        if clause.basis == S.SOURCED:
            assert clause.quote.strip(), clause.key
    sourced = [c for c in S.CLAUSES if c.basis == S.SOURCED]
    assert len(sourced) >= 10, "most of this contract should be quotable, not reasoned"


def test_the_required_fields_are_etsys_list_and_not_a_convenient_subset():
    assert S.REQUIRED_TO_CREATE == ("quantity", "title", "description", "price",
                                    "who_made", "when_made", "taxonomy_id")
    missing = S.check_payload({"title": "t", "description": "d", "type": S.DIGITAL_TYPE})
    assert any("LISTING_MISSING_REQUIRED" in p for p in missing), missing


def test_a_physical_listings_obligations_are_not_a_digital_listings():
    """Named rather than omitted: 'we did not send it' and 'it is not required' differ."""
    for field in ("shipping_profile_id", "return_policy_id", "readiness_state_id"):
        assert field in S.NOT_REQUIRED_FOR_DIGITAL
        assert field not in S.REQUIRED_TO_CREATE
    assert "physical" in S.CLAUSES_BY_KEY["return_policy_physical_only"].quote


# ---- the gap that closes the shop -----------------------------------------


def test_a_draft_with_no_image_cannot_be_activated():
    """Etsy's sentence, enforced here, because a catalogue of drafts is not a shop."""
    payload = build_payload(**GOOD).to_dict()
    assert S.check_payload(payload, images=0, intended_state="draft") == [], \
        "creating the draft is fine; it is activation that needs an image"

    blocked = S.check_payload(payload, images=0, intended_state="active")
    assert any("LISTING_CANNOT_BE_ACTIVATED" in p for p in blocked), blocked
    assert any("different endpoint" in p for p in blocked), (
        "the message has to say the pattern file is not a listing image, because that is "
        "the confusion that makes this look already solved")

    assert S.check_payload(payload, images=1, intended_state="active") == []
    too_many = S.check_payload(payload, images=S.MAX_IMAGES + 1, intended_state="active")
    assert any("LISTING_TOO_MANY_IMAGES" in p for p in too_many), too_many


def test_the_image_gap_is_recorded_as_a_launch_blocker():
    """The image and encoding gaps stay launch blockers after being closed in code.

    Both were "this system does not do it" on 2026-09-24 and are "Etsy has never confirmed
    that this system does it correctly" on 2026-09-25. The second is a smaller gap and it
    fails exactly as hard on launch day, so downgrading it when the code was written would
    have turned a build task into a silent assumption.
    """
    blockers = [g for g in S.gaps() if g["blocks_launch"]]
    assert any("image" in g["gap"] for g in blockers), blockers
    assert any("form-encoded" in g["gap"] for g in blockers), blockers
    assert any("authenticated against Etsy" in g["gap"] for g in blockers), blockers
    # A launch blocker here is now about unconfirmed behaviour rather than missing code, and
    # the check for that is the verification state rather than the wording: not one blocker
    # may be VERIFIED_AGAINST_ETSY, because a blocker Etsy has confirmed is not a blocker.
    assert all(g["verification"] in (S.IMPLEMENTED, S.LOCALLY_TESTED) for g in blockers), \
        [(g["gap"], g["verification"]) for g in blockers]
    for gap in S.gaps():
        assert gap["clause"] in S.CLAUSES_BY_KEY, (
            f"{gap['clause']} is not a clause; a gap that rests on nothing cannot stop "
            f"being true when Etsy changes its document")


# ---- the character sets ----------------------------------------------------


def test_a_material_may_not_carry_a_percentage_and_yarn_usually_does():
    problems = S.material_problems(["100% cotton"])
    assert any("MATERIAL_CHARACTERS" in p for p in problems), problems
    assert "'%'" in problems[0], "the refusal names the character rather than the string"
    assert S.material_problems(["worsted cotton", "dk acrylic"]) == []
    # A hyphen is fine in a tag and not in a material. The sets genuinely differ.
    assert S.tag_problems(["hand-dyed yarn"]) == []
    assert S.material_problems(["hand-dyed yarn"]) != []


def test_a_title_may_use_an_ampersand_once_and_a_template_uses_it_twice():
    assert S.title_problems("Crochet Pattern | Chart & Written Instructions") == []
    twice = S.title_problems("Pattern & Chart & Written")
    assert any("TITLE_REPEATED_SYMBOL" in p for p in twice), twice
    for char in S.TITLE_ONCE_ONLY:
        assert S.title_problems(f"a {char} b {char} c"), char


def test_a_tag_with_a_comma_is_caught_because_the_body_is_comma_separated():
    problems = S.tag_problems(["chart, written"])
    assert any("TAG_CHARACTERS" in p for p in problems), problems
    assert S.form_encoded({"tags": ["a b", "c d"]})["tags"] == "a b,c d"


def test_the_request_body_is_form_encoded_rather_than_json():
    """Etsy's document lists one media type for this endpoint and it is not JSON."""
    assert S.REQUEST_ENCODING == "application/x-www-form-urlencoded"
    body = S.form_encoded(build_payload(**GOOD).to_dict())
    assert all(isinstance(v, str) for v in body.values()), body
    assert body["is_supply"] == "true", "a form body has no booleans"
    assert body["materials"] == "worsted cotton"
    assert body["type"] == S.DIGITAL_TYPE


# ---- what the system actually produces ------------------------------------


def test_the_real_export_passes_the_contract_it_can_pass():
    payload = build_payload(**GOOD).to_dict()
    assert S.check_payload(payload) == [], "the drafted export must be creatable"
    assert payload["type"] == S.DIGITAL_TYPE
    assert payload["who_made"] in S.WHO_MADE_VALUES


def test_a_duplicated_material_is_collapsed_rather_than_spending_a_slot():
    """A CIR carries one material per colour, so this arrives from truth, not from a typo."""
    payload = build_payload(**dict(GOOD, materials=["worsted cotton"] * 6))
    assert payload.materials == ["worsted cotton"]
    assert S.material_problems(["worsted cotton"] * 6) != [], (
        "the checker still reports duplicates; the builder is what collapses them")


def test_the_builder_refuses_a_listing_etsy_would_refuse():
    for bad, needle in ((dict(GOOD, materials=["100% cotton"]), "MATERIAL_CHARACTERS"),
                        (dict(GOOD, tags=["chart, written"]), "TAG_CHARACTERS"),
                        (dict(GOOD, title="Pattern & Chart & Written"),
                         "TITLE_REPEATED_SYMBOL")):
        try:
            build_payload(**bad)
        except EtsyRejected as e:
            assert needle in str(e), (needle, str(e))
        else:
            raise AssertionError(f"a listing Etsy would refuse was mapped: {needle}")


def test_describe_carries_the_whole_contract_for_the_readiness_report():
    out = S.describe()
    assert out["source"] == S.ETSY_OPENAPI_URL and out["read_on"] == S.READ_ON
    assert out["request_encoding"] == S.REQUEST_ENCODING
    assert out["write_scope"] == "listings_w"
    assert len(out["clauses"]) == len(S.CLAUSES)
    assert out["gaps"], "a contract with no gaps has not been compared to anything"
    assert out["verification_states"] == list(S.VERIFICATION_STATES)
    assert out["verification_matrix"], "the readiness report needs the three states"
    assert sum(out["verification_summary"].values()) == len(out["verification_matrix"])


# ---- the three states ------------------------------------------------------


def test_the_three_states_are_three_and_every_claim_is_in_exactly_one():
    """Measures that IMPLEMENTED, LOCALLY_TESTED and VERIFIED_AGAINST_ETSY stay apart.

    Two states -- done and not done -- is what makes a large build dishonest here, because
    "the code exists", "our own server accepts it" and "Etsy accepts it" are three different
    amounts of evidence and only the third is worth anything on launch day.
    """
    assert S.VERIFICATION_STATES == (S.IMPLEMENTED, S.LOCALLY_TESTED,
                                     S.VERIFIED_AGAINST_ETSY)
    rows = S.verification_matrix()
    claims = [r["claim"] for r in rows]
    assert len(claims) == len(set(claims)), "a claim appears twice and could be in two states"
    for row in rows:
        assert row["state"] in S.VERIFICATION_STATES, row
        assert row["what"].strip() and row["graduates_by"].strip(), row
        assert row["evidence"].strip(), row
    # All three are actually in use. A matrix where everything is IMPLEMENTED has not made
    # the distinction, it has just renamed one state.
    assert len(set(r["state"] for r in rows)) == 3, S.verification_summary()


def test_only_the_four_unauthenticated_pings_are_verified_against_etsy():
    """Measures that the green column is exactly what Etsy has actually said, and no more.

    Four facts, all from the three unauthenticated requests of 2026-09-25: that Etsy is
    reachable through our own transport, the keystring:shared_secret header format, 403
    rather than 401, and that Etsy refuses on the API key before reading a body. Nothing
    about encodings, images, taxonomy or deletion is in there, because no authenticated
    request has ever been made.
    """
    verified = [r for r in S.verification_matrix()
                if r["state"] == S.VERIFIED_AGAINST_ETSY]
    assert len(verified) == 4, [r["claim"] for r in verified]
    for row in verified:
        assert row["observed_on"] == "2026-09-25", row
        assert row["evidence"] != "none; the code exists and has not run", row
    # And none of them is about a write. Every write claim is at most LOCALLY_TESTED.
    for claim in ("form_encoded_create", "multipart_image_upload", "array_encoding_tags",
                  "delete_removes_draft", "taxonomy_patterns_id"):
        row = [r for r in S.verification_matrix() if r["claim"] == claim][0]
        assert row["state"] != S.VERIFIED_AGAINST_ETSY, row


def test_a_claim_cannot_be_promoted_by_being_believed():
    """Measures the enforcement: VERIFIED_AGAINST_ETSY needs a recorded observation.

    The failure mode this prevents is the cheap one -- somebody edits a state to green
    because the tests pass. The state and the observation live in two places and the matrix
    refuses to emit one without the other.
    """
    original = S._MATRIX
    try:
        S._MATRIX = original + ({"claim": "invented_claim",
                                 "state": S.VERIFIED_AGAINST_ETSY,
                                 "blocks_launch": False, "what": "x", "graduates_by": "y"},)
        try:
            S.verification_matrix()
        except S.SchemaRefused as e:
            assert "ETSY_VERIFIED_FACTS" in str(e), e
        else:
            raise AssertionError("a claim promoted itself to VERIFIED_AGAINST_ETSY")

        # A state that is not one of the three is refused for the same reason.
        S._MATRIX = original + ({"claim": "invented_claim", "state": "PROBABLY_FINE",
                                 "blocks_launch": False, "what": "x", "graduates_by": "y"},)
        try:
            S.verification_matrix()
        except S.SchemaRefused as e:
            assert "PROBABLY_FINE" in str(e), e
        else:
            raise AssertionError("an invented state was accepted")
    finally:
        S._MATRIX = original


def test_every_gap_states_its_evidential_status_and_cannot_invent_a_claim():
    """Measures that the gap list and the matrix cannot describe different worlds."""
    states = {r["claim"]: r["state"] for r in S.verification_matrix()}
    for gap in S.gaps():
        assert gap["verification"] in S.VERIFICATION_STATES, gap
        if gap.get("claim"):
            assert gap["verification"] == states[gap["claim"]], gap

    original = S._MATRIX
    try:
        # A gap naming a claim nobody tracks is refused rather than quietly stamped.
        S._MATRIX = tuple(r for r in original if r["claim"] != "delete_removes_draft")
        try:
            S.gaps()
        except S.SchemaRefused as e:
            assert "delete_removes_draft" in str(e), e
        else:
            raise AssertionError("a gap rested on a claim with no evidential status")
    finally:
        S._MATRIX = original


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
