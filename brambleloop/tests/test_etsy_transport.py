"""The Etsy write path: image upload, draft update, OAuth refresh, encoding, read-back.

An audit on 2026-09-24 found that this system could create an Etsy draft and could not finish
one: `uploadListingImage` appeared nowhere in `src/`, `updateListing` appeared nowhere, and
the transport sent `application/json` to two endpoints for which Etsy lists
`application/x-www-form-urlencoded` as the only accepted media type. Etsy refuses to activate
a listing that has no image, so every draft the system could produce was permanently
unactivatable and the shop would have opened with zero live listings.

These tests run the whole sequence -- authenticated read, create draft, upload image, update
permitted fields, read back, verify, delete -- against `tests/fake_etsy.py`, a local HTTP
server built from Etsy's own published API description. **What that can and cannot prove is
the most important thing in this file.** It can prove that our bytes are parseable by a parser
that is not ours, that the client sends each endpoint's documented media type, that the image
binary is in a part named `image`, that read-back verification catches a write the server
ignored, and that the refusals refuse. It cannot prove that Etsy behaves this way: there are
no Etsy credentials in this environment and not one write has ever reached Etsy.

So these tests are written to fail in the two directions that matter:

- **A wrong encoding must fail.** The fake answers 415 to a JSON body on a form endpoint and
  400 to an image sent in a part named `file`, so the exact defects the audit found are now
  reproduced as failing requests rather than described in a document.
- **A silent success must fail.** The fake ignores a field Etsy's update schema does not
  carry, exactly as a form parser does, and returns 200. Only read-back catches that, so
  there is a test in which the write succeeds and the verification fails.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.resilience import PermanentError  # noqa: E402
from brambleloop.integrations import etsy_oauth, etsy_probe, etsy_verify  # noqa: E402
from brambleloop.integrations.etsy import (  # noqa: E402
    Authority, Credentials, EtsyClient, EtsyNotPermitted, EtsyRejected, FilePart,
    build_payload,
)
from brambleloop.integrations.http import UrllibTransport, form_body, multipart_body  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402


def _client(fake: FakeEtsy, *, phase: str = "shadow", owner: bool = False,
            shadow_writes: bool = True, token: str = "111.live-token",
            provider: object | None = None) -> EtsyClient:
    creds = Credentials(api_key=fake.keystring, shared_secret=fake.shared_secret,
                        access_token=token, shop_id=fake.shop_id, token_provider=provider)
    return EtsyClient(UrllibTransport(), credentials=creds, phase=phase,
                      owner_authorised=owner, shadow_writes_authorised=shadow_writes,
                      base=fake.base)


PAYLOAD = dict(title="Bramble Hollow Blanket crochet pattern",
               description="A worked example listing for the transport tests.",
               price_cad=9.99, tags=["crochet pattern", "blanket"], materials=["cotton yarn"])


# ---------------------------------------------------------------------------
# Encoding: what Etsy's document says each endpoint takes


def test_the_create_request_is_form_encoded_because_etsy_accepts_nothing_else():
    """Measures the media type the create request actually carries on the wire.

    Not what the client intends: what the server received in the Content-Type header, read
    back off the fake. Etsy lists `application/x-www-form-urlencoded` as the only media type
    for createDraftListing, and this client sent `application/json` until 2026-09-25.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        assert listing_id, "no listing id came back"
        create = [r for r in fake.requests if r["operation"] == "createDraftListing"]
        assert len(create) == 1, create
        assert create[0]["content_type"] == "application/x-www-form-urlencoded", create[0]


def test_a_json_body_on_a_form_endpoint_is_refused_which_is_the_defect_we_had():
    """Measures that the old transport's body would have been rejected, not tolerated.

    The previous transport serialised every body with `json.dumps`. If Etsy's form endpoints
    silently accepted JSON, the audit's finding would have been cosmetic. The fake answers 415
    because Etsy's document lists one media type, so this test is the reason the fix is a fix.
    """
    with FakeEtsy() as fake:
        transport = UrllibTransport()
        response = transport.request(
            "POST", f"{fake.base}/shops/{fake.shop_id}/listings",
            headers={"x-api-key": fake.api_key_header(),
                     "Authorization": "Bearer 111.live-token"},
            json={"quantity": 999, "title": "x", "description": "y", "price": 9.99,
                  "who_made": "i_did", "when_made": "made_to_order", "taxonomy_id": 66})
        assert response.status == 415, response
        assert "urlencoded" in str(response.body), response.body


def test_one_request_carries_one_body_so_the_content_type_cannot_lie():
    """Measures that the transport refuses two body channels at once.

    A request with both a JSON body and a form body has a Content-Type that describes one of
    them. That was the shape of the original defect -- a header that disagreed with the bytes
    -- so it is now unrepresentable rather than discouraged.
    """
    transport = UrllibTransport()
    try:
        transport.request("POST", "http://127.0.0.1:1/x", headers={}, json={"a": 1},
                          form={"b": 2})
    except ValueError as e:
        assert "one body" in str(e), e
    else:
        raise AssertionError("two bodies were accepted")


def test_form_and_multipart_encoders_produce_what_a_form_parser_reads_back():
    """Measures the encoders at the byte level, parsed by code that is not ours."""
    import email
    import urllib.parse

    body = form_body({"title": "Blanket & Throw", "is_supply": True, "quantity": 999,
                      "skip": None})
    parsed = dict(urllib.parse.parse_qsl(body.decode()))
    assert parsed == {"title": "Blanket & Throw", "is_supply": "true", "quantity": "999"}, \
        f"a form parser read something else: {parsed}"

    raw, content_type = multipart_body(
        FilePart(field="image", filename='odd"name.png', data=b"\x89PNG-bytes",
                 content_type="image/png"),
        {"rank": 1, "alt_text": "alt"})
    message = email.message_from_bytes(
        b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
    names, files = {}, {}
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = part.get_param("name", header="content-disposition")
        filename = part.get_param("filename", header="content-disposition")
        (files if filename else names)[name] = part.get_payload(decode=True)
    assert sorted(names) == ["alt_text", "rank"], names
    assert list(files) == ["image"], files
    assert files["image"] == b"\x89PNG-bytes", "the file's bytes did not survive encoding"


# ---------------------------------------------------------------------------
# The image upload: the gap that made every draft unactivatable


def test_a_listing_image_is_uploaded_and_etsy_holds_it():
    """Measures that an image upload results in an image on the listing, read back.

    The upload's own 201 is not the evidence. The evidence is `getListing?includes=Images`
    returning an image afterwards, because that is the state Etsy checks when it decides
    whether a draft may be activated.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        uploaded = client.upload_image(listing_id, filename="cover.png",
                                       data=etsy_probe.one_pixel_png(), rank=1,
                                       alt_text="cover")
        assert uploaded["listing_image_id"], uploaded
        remote = client.get_listing(listing_id)
        assert len(remote.get("images", [])) == 1, remote.get("images")
        upload = [r for r in fake.requests if r["operation"] == "uploadListingImage"][0]
        assert upload["content_type"] == "multipart/form-data", upload


def test_an_image_sent_in_a_part_named_file_is_refused():
    """Measures that the field name matters, which is why it is data and not a constant.

    Etsy reads a listing image from a part named `image`; the old transport hard-coded `file`
    for every upload. That request is well-formed, so the only thing that catches it is the
    server looking for a part that is not there.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        response = UrllibTransport().request(
            "POST", f"{fake.base}/shops/{fake.shop_id}/listings/{listing_id}/images",
            headers={"x-api-key": fake.api_key_header(),
                     "Authorization": "Bearer 111.live-token"},
            form={"rank": 1},
            multipart=FilePart(field="file", filename="cover.png",
                               data=etsy_probe.one_pixel_png(), content_type="image/png"))
        assert response.status == 400, response
        assert "image" in str(response.body), response.body


def test_an_image_that_does_not_exist_is_refused_as_a_launch_blocker():
    """Measures that empty bytes are refused before a request, with the consequence named."""
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        before = len(fake.requests)
        for filename, data, expect in (("cover.png", b"", "never be activated"),
                                       ("pattern.pdf", b"%PDF-1.7", "listing-image format")):
            try:
                client.upload_image(listing_id, filename=filename, data=data)
            except EtsyRejected as e:
                assert expect in str(e), e
            else:
                raise AssertionError(f"{filename} was accepted")
        assert len(fake.requests) == before, "a refused upload still sent a request"


# ---------------------------------------------------------------------------
# Draft update, and what updateListing will not take


def test_permitted_draft_fields_update_and_read_back_changed():
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        client.update_listing(listing_id, {"title": "Bramble Hollow Blanket pattern v2",
                                           "tags": ["crochet pattern", "throw"]})
        remote = client.get_listing(listing_id)
        assert remote["title"] == "Bramble Hollow Blanket pattern v2", remote["title"]
        assert remote["tags"] == ["crochet pattern", "throw"], remote["tags"]
        assert remote["state"] == "draft", "an update moved the listing out of draft"


def test_price_and_state_and_unknown_fields_are_refused_before_a_request_is_sent():
    """Measures three refusals that each prevent a different silent failure.

    `price` is not an updateListing field at all -- Etsy moves price to the inventory
    endpoint -- so sending it would change nothing and report success. `state` is the request
    that publishes a listing and charges a fee. An unknown field is ignored by a form parser,
    which means the listing keeps its old value under a 200.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        before = len(fake.requests)
        for fields, expect in (({"price": 12.0}, "inventory"),
                               ({"state": "active"}, "listing fee"),
                               ({"quantity": 5}, "no such field"),
                               ({}, "changes nothing")):
            try:
                client.update_listing(listing_id, fields)
            except (EtsyRejected, EtsyNotPermitted) as e:
                assert expect in str(e), f"{fields} -> {e}"
            else:
                raise AssertionError(f"{fields} was sent")
        assert len(fake.requests) == before, "a refused update still sent a request"


# ---------------------------------------------------------------------------
# Read-back verification: the only step that produces evidence


def test_read_back_verifies_every_field_including_the_ones_etsy_transforms():
    """Measures that verification passes only when it has compared every field it sent.

    Etsy returns `price` as a Money object and renames `type` to `listing_type`. A verifier
    that does not know both reports a mismatch on a correct write, which is how verification
    gets switched off.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        payload = build_payload(**PAYLOAD)
        sent = payload.to_dict()
        sent.pop("state", None)
        listing_id = client.create_draft(payload)
        result = etsy_verify.verify(sent, client.get_listing(listing_id),
                                   listing_id=listing_id, expect_state="draft",
                                   expect_images=0)
        assert result.verified, result.summary()
        assert result.mismatches == [], result.summary()
        assert result.unverifiable == [], result.summary()
        by_field = {v.field: v for v in result.verdicts}
        assert by_field["price"].remote == 9.99, by_field["price"]
        assert by_field["type"].note == "returned as listing_type", by_field["type"]


def test_a_write_the_server_ignored_returns_200_and_fails_read_back():
    """Measures the failure mode that only read-back can see.

    `quantity` is not in Etsy's updateListing schema. A form parser ignores an unknown field
    and the request succeeds, so the request log says the write worked and the listing still
    holds its old value. This test performs that write deliberately, past the client's own
    guard, and asserts that verification reports it.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        response = client._call(
            "PATCH", f"/shops/{fake.shop_id}/listings/{listing_id}",
            operation="updateListing",
            form={"title": "still a draft", "quantity": 5})
        assert response.status == 200, "the ignored field did not even look like a success"
        result = etsy_verify.verify({"title": "still a draft", "quantity": 5},
                                    client.get_listing(listing_id), listing_id=listing_id)
        assert not result.verified, "verification passed a write that did nothing"
        assert [v.field for v in result.mismatches] == ["quantity"], result.summary()
        assert result.mismatches[0].remote == 999.0, result.mismatches[0]


def test_a_field_etsy_never_returns_is_unverifiable_rather_than_verified():
    """Measures that "we could not check" is its own verdict and does not count as a pass."""
    result = etsy_verify.verify({"title": "t", "featured_rank": 1},
                                {"listing_id": 1, "title": "t", "state": "draft"},
                                listing_id="1")
    assert not result.verified, result.summary()
    assert [v.field for v in result.unverifiable] == ["featured_rank"], result.summary()
    assert [v.field for v in result.mismatches] == [], result.summary()


def test_read_back_reports_a_listing_that_is_no_longer_a_draft():
    """Measures the single most consequential read-back field: state.

    A listing that is not a draft is a listing a customer can reach. If that ever happens
    without a Launch-0 authorisation, it must be the loudest thing in the report.
    """
    result = etsy_verify.verify({"title": "t"},
                                {"listing_id": 1, "title": "t", "state": "active"},
                                listing_id="1", expect_state="draft", expect_images=1)
    assert not result.verified
    assert any("state on Etsy is 'active'" in p for p in result.problems), result.problems
    assert any("0 image" in p for p in result.problems), result.problems


# ---------------------------------------------------------------------------
# OAuth: PKCE, refresh, rotation, scope


def test_pkce_matches_the_published_rfc_7636_test_vector():
    """Measures the PKCE implementation against a value published outside this company.

    RFC 7636 appendix B gives a verifier and its challenge. Etsy requires PKCE on every
    authorization request, and a wrong challenge fails in the owner's browser rather than in
    any code path here, so an external check is worth more than a round trip through our own
    two functions.
    """
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert etsy_oauth.challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    generated = etsy_oauth.new_verifier()
    assert etsy_oauth.VERIFIER_MIN <= len(generated) <= etsy_oauth.VERIFIER_MAX, generated
    assert "=" not in generated, "a padded verifier is not URL-safe base64 per RFC 7636"


def test_an_expired_access_token_is_refreshed_and_the_new_refresh_token_is_handed_back():
    """Measures the failure that would have arrived on day two, not day one.

    Etsy's access token lives one hour and every refresh issues a **new** refresh token, the
    old one being spent. A client that refreshes and does not persist the new one works until
    it restarts and then needs the owner's browser, so the rotation is asserted as well as the
    refresh.
    """
    with FakeEtsy() as fake:
        app = etsy_oauth.OAuthApp(keystring=fake.keystring, redirect_uri="https://x/cb",
                                  shared_secret=fake.shared_secret,
                                  token_url=fake.token_url)
        persisted: list[etsy_oauth.TokenSet] = []
        provider = etsy_oauth.TokenProvider(
            app=app, transport=UrllibTransport(),
            tokens=etsy_oauth.TokenSet(access_token="111.dead-token",
                                       refresh_token="111.refresh-one",
                                       expires_at=time.time() - 1,
                                       scopes=fake.scopes),
            on_refresh=persisted.append)
        client = _client(fake, token="", provider=provider)

        listing_id = client.create_draft(build_payload(**PAYLOAD))

        assert listing_id, "the call did not complete after the refresh"
        assert fake.refreshes == 1, f"expected one refresh, saw {fake.refreshes}"
        assert provider.refreshes == 1
        assert persisted and persisted[0].refresh_token != "111.refresh-one", \
            "the rotated refresh token was not handed back for persistence"
        assert provider.history[0]["refresh_token_rotated"] is True
        assert fake.token_requests[0]["grant_type"] == "refresh_token"
        assert fake.token_requests[0]["client_id"] == fake.keystring


def test_a_spent_refresh_token_becomes_an_owner_action_rather_than_a_retry():
    """Measures that an unrecoverable auth failure says so and names the human step."""
    with FakeEtsy() as fake:
        app = etsy_oauth.OAuthApp(keystring=fake.keystring, redirect_uri="https://x/cb",
                                  token_url=fake.token_url)
        try:
            etsy_oauth.refresh(UrllibTransport(), app, "111.never-issued")
        except etsy_oauth.EtsyAuthNeedsOwner as e:
            assert "browser" in str(e), e
        else:
            raise AssertionError("a dead refresh token was treated as recoverable")


def test_a_token_without_the_write_scope_refuses_before_sending_anything():
    """Measures that a scope Etsy did not grant stops the call here, not at Etsy.

    Etsy's granted scope "may be a subset of the requested scopes", and a refresh cannot widen
    it. So a token missing `listings_w` is an owner action, and discovering that from a 403 on
    the first publish attempt is the expensive way to find out.
    """
    with FakeEtsy() as fake:
        app = etsy_oauth.OAuthApp(keystring=fake.keystring, redirect_uri="https://x/cb",
                                  token_url=fake.token_url)
        provider = etsy_oauth.TokenProvider(
            app=app, transport=UrllibTransport(),
            tokens=etsy_oauth.TokenSet(access_token="111.live-token",
                                       refresh_token="111.refresh-one",
                                       expires_at=time.time() + 3600,
                                       scopes=("listings_r", "shops_r")))
        client = _client(fake, token="", provider=provider)
        try:
            client.create_draft(build_payload(**PAYLOAD))
        except etsy_oauth.EtsyAuthNeedsOwner as e:
            assert "listings_w" in str(e), e
        else:
            raise AssertionError("a token without listings_w created a draft")
        assert fake.requests == [], "a scope refusal still reached the server"


def test_the_authorize_url_is_the_owner_action_and_carries_no_secret_in_the_report():
    """Measures that the one step only a human can take is stated exactly, and safely."""
    app = etsy_oauth.OAuthApp(keystring="keystring-value", redirect_uri="https://x/cb",
                              shared_secret="secret-value")
    action = etsy_oauth.owner_action(app)
    assert action["authorize_url"].startswith("https://www.etsy.com/oauth/connect?")
    assert "code_challenge_method=S256" in action["authorize_url"]
    assert "listings_w" in action["authorize_url"]
    assert action["maximum_cost"] == "CA$0"
    assert "secret-value" not in repr(app), "the shared secret is in the repr"
    assert "keystring-value" not in repr(app), "the keystring is in the repr"
    assert etsy_oauth.owner_action(None)["authorize_url"] is None, \
        "a URL was invented without an app to build it from"


def test_a_token_set_never_prints_itself():
    tokens = etsy_oauth.TokenSet(access_token="111.secret-access",
                                 refresh_token="111.secret-refresh",
                                 expires_at=time.time() + 60, scopes=("listings_w",))
    rendered = repr(tokens) + str(tokens.redacted())
    assert "secret-access" not in rendered and "secret-refresh" not in rendered, rendered
    creds = Credentials(api_key="k", access_token="111.secret-access", shop_id="9",
                        shared_secret="s")
    # The shop id stays in the repr on purpose: it is public on Etsy and it is what tells you
    # which account a failure came from. The token and the secret must not be there.
    assert "secret-access" not in repr(creds), repr(creds)
    assert "shop_id='9'" in repr(creds), repr(creds)


# ---------------------------------------------------------------------------
# Authority: drafts are free and invisible; activation is neither


def test_the_three_authorities_are_separate_gates():
    """Measures that a read, a draft write and an activation are not one permission.

    They were. `create_draft` and activation sat behind the same check, so an authority that
    allowed a draft allowed publishing, and the phase that forbade publishing also forbade
    the reads that would have exercised this code before launch day.
    """
    with FakeEtsy() as fake:
        held_back = _client(fake, shadow_writes=False)
        assert held_back.refusal_for(Authority.READ) is None, "a read was refused"
        assert "shadow_writes_authorised" in (
            held_back.refusal_for(Authority.DRAFT_WRITE) or ""), "a draft write was permitted"
        assert held_back.refusal_for(Authority.ACTIVATE) is not None

        drafting = _client(fake, shadow_writes=True)
        assert drafting.refusal_for(Authority.DRAFT_WRITE) is None
        activation = drafting.refusal_for(Authority.ACTIVATE) or ""
        assert "never activation" in activation or "does not permit publication" in activation, \
            activation

        # And the old publish gate is untouched: shadow still refuses to publish.
        assert drafting.refusal() is not None, "shadow permitted publication"


def test_activation_refuses_without_a_launch_authorisation_even_when_everything_else_is_true():
    """Measures the last gate, in the one configuration where only it is left.

    Phase production, owner authority granted, credentials present, image uploaded: this is
    the state in which a forgotten job would publish. The authorisation is an argument to the
    call, so a job configured once cannot have it.
    """
    with FakeEtsy() as fake:
        client = _client(fake, phase="production", owner=True, shadow_writes=False)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        client.upload_image(listing_id, filename="cover.png",
                            data=etsy_probe.one_pixel_png())
        before = len([r for r in fake.requests if r["operation"] == "updateListing"])
        try:
            client.activate(listing_id)
        except EtsyNotPermitted as e:
            assert "Launch-0" in str(e) and "listing fee" in str(e), e
        else:
            raise AssertionError("a listing was activated without authorisation")
        after = len([r for r in fake.requests if r["operation"] == "updateListing"])
        assert after == before, "the refused activation still sent an update"
        assert client.get_listing(listing_id)["state"] == "draft"


def test_activation_refuses_a_listing_with_no_image_before_spending_anything():
    """Measures Etsy's own activation rule, checked on our side so the failure is free.

    Etsy: "Setting a `draft` listing to `active` ... requires that the listing have an image
    set." A listing fee is charged on publication, so a request that Etsy would refuse is
    still worth not sending.
    """
    with FakeEtsy() as fake:
        client = _client(fake, phase="production", owner=True, shadow_writes=False)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        try:
            client.activate(listing_id, launch_authorisation="LAUNCH-0-TEST")
        except EtsyRejected as e:
            assert "no image" in str(e), e
        else:
            raise AssertionError("a listing with no image was activated")
        assert client.get_listing(listing_id)["state"] == "draft"
        assert not [r for r in fake.requests
                    if r["operation"] == "updateListing"], "an update was sent anyway"


def test_activation_works_when_it_is_authorised_which_is_why_the_gates_matter():
    """Measures that the capability exists, against a fake shop, and only there.

    Everything else in this file asserts that activation is refused. Something has to assert
    that the refusals are the only thing stopping it -- otherwise "activation is implemented"
    is a claim resting on code nothing has run. The fake shop has no customers, no money and
    no listing fee; the real one is not touched by any test.
    """
    with FakeEtsy() as fake:
        client = _client(fake, phase="production", owner=True, shadow_writes=False)
        listing_id = client.create_draft(build_payload(**PAYLOAD))
        client.upload_image(listing_id, filename="cover.png",
                            data=etsy_probe.one_pixel_png())
        client.attach_file(listing_id, filename="pattern.pdf", data=b"%PDF-1.7 bytes")
        client.activate(listing_id, launch_authorisation="LAUNCH-0-TEST")
        assert client.get_listing(listing_id)["state"] == "active"
        # And the safety on deletion holds: an active listing is not a draft.
        try:
            client.delete_listing(listing_id, expect_states=("draft",))
        except EtsyNotPermitted as e:
            assert "'active'" in str(e), e
        else:
            raise AssertionError("an active listing was deleted by a draft cleanup")


# ---------------------------------------------------------------------------
# The whole sequence, and the shape of the evidence it produces


def test_the_shadow_safe_exercise_runs_end_to_end_and_leaves_nothing_behind():
    """Measures the sequence the real shop would run: every step, in order, then cleanup.

    The assertion that matters most is the last one. A test artefact left in a real shop is
    indistinguishable from a product with a mistake in it, so the shop must hold nothing
    afterwards -- and the run must say so rather than leaving the caller to check.
    """
    with FakeEtsy() as fake:
        client = _client(fake)
        report = etsy_probe.run_exercise(client)

        assert report["verified"], report
        assert report["cleaned_up"] is True, report
        assert report["activation_attempted"] is False, report
        assert fake.listings == {}, f"the shop still holds {list(fake.listings)}"
        assert fake.images == {}, fake.images

        steps = {s["step"]: s for s in report["steps"]}
        assert all(steps[name]["ok"] for name in steps), report["steps"]
        for name in ("read_shop", "create_draft", "upload_image", "update_listing",
                     "refusals_hold", "read_back", "cleanup"):
            assert name in steps, f"{name} did not run"
        assert steps["create_draft"]["observed"]["encoding_sent"] == \
            "application/x-www-form-urlencoded"
        assert steps["upload_image"]["observed"]["encoding_sent"] == "multipart/form-data"
        assert steps["read_back"]["observed"]["images_on_etsy"] == 1
        assert steps["read_back"]["observed"]["state_on_etsy"] == "draft"

        # The operations Etsy saw, in order. A create with no state field, then the image.
        seen = [r["operation"] for r in fake.requests]
        assert seen.count("createDraftListing") == 1, seen
        assert seen.count("uploadListingImage") == 1, seen
        assert seen.count("deleteListing") == 1, seen


def test_the_exercise_report_carries_no_credential():
    """Measures that the evidence a run produces can be pasted into a document safely."""
    with FakeEtsy() as fake:
        client = _client(fake, token="111.live-token")
        report = etsy_probe.run_exercise(client)
        rendered = str(report)
        assert "live-token" not in rendered, "an access token is in the report"
        assert fake.shared_secret not in rendered, "the shared secret is in the report"
        assert fake.keystring not in rendered, "the keystring is in the report"


def test_a_test_draft_says_what_it_is_in_its_own_title():
    """Measures that a human who finds the artefact before cleanup knows what it is."""
    payload = etsy_probe.test_payload("abc123")
    assert payload.title.startswith("DO NOT BUY"), payload.title
    assert "not a product" in payload.description
    assert payload.state == "draft"


def test_the_probe_refuses_to_write_without_an_explicit_operator_grant():
    """Measures that running the probe with credentials present does not write by default.

    Credentials are absent from this environment, so this asserts the first branch: the probe
    reports that it was not exercised and returns the owner action rather than claiming
    anything. If credentials appear, `ETSY_SHADOW_WRITE=1` is still required before a single
    draft is created.
    """
    import io
    import json
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = etsy_probe.main([])
    report = json.loads(buffer.getvalue())
    assert code in (0, 2), code
    if code == 2:
        assert "NOT EXERCISED" in report["status"], report["status"]
        assert report["owner_action"]["minutes"] > 0
    else:
        assert "READ ONLY" in report["status"], report["status"]
    # Either way the ping was attempted against Etsy itself and reported honestly.
    assert report["ping"]["url"].startswith("https://openapi.etsy.com/"), report["ping"]


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
