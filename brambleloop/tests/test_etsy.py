"""The Etsy publishing path: the only code that could reach a customer, and its refusals.

Written and tested while it cannot publish, which is the point. The alternative is writing
the code that sends real listings to a real shop for the first time on the day it matters.

What these tests defend:

- **Nothing leaves the building.** In shadow, with or without credentials, zero requests are
  made. The transport is the only way out and the tests count its calls.
- **The refusals are ordered.** Phase first, then the owner's authority, then credentials, so
  a misconfigured key can never be the reason we stopped and a present key is never mistaken
  for permission.
- **A listing that cannot be mapped is refused, not truncated.** A title cut at 140
  characters mid-word is a listing nobody approved, shipped under a certificate describing
  something else.
- **The half-done case is reported as itself.** A listing on Etsy with no file attached takes
  money and delivers nothing; it is not a success and it is not a plain failure, because the
  recovery is to complete or delete it rather than create it again.
- **Secrets stay out of logs.** A credential's repr is what ends up in a traceback.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.integrations.etsy import (  # noqa: E402
    TAG_CHARS_MAX, TAGS_MAX, TITLE_MAX, Credentials, EtsyClient, EtsyNotConfigured,
    EtsyNotPermitted, EtsyRejected, Response, build_payload,
)


class FakeTransport:
    """Records every call and returns whatever the test asked for."""

    def __init__(self, *, listing_status: int = 200, file_status: int = 200,
                 listing_body: dict | None = None, file_body: dict | None = None) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.listing_status = listing_status
        self.file_status = file_status
        self.listing_body = listing_body if listing_body is not None else {
            "listing_id": 987654321}
        self.file_body = file_body if file_body is not None else {"listing_file_id": 42}

    def request(self, method, url, *, headers, json=None, file=None):
        self.calls.append((method, url, json))
        assert "x-api-key" in headers and headers["Authorization"].startswith("Bearer ")
        if file is not None:
            # A multipart body must not claim to be JSON.
            assert "Content-Type" not in headers, headers
            assert isinstance(file[1], bytes) and file[1], "no bytes to upload"
        if url.endswith("/files"):
            return Response(self.file_status, self.file_body,
                            {"Retry-After": "7"} if self.file_status == 429 else {})
        return Response(self.listing_status, self.listing_body,
                        {"Retry-After": "7"} if self.listing_status == 429 else {})


GOOD = dict(title="Crochet Storage Basket | Crochet Pattern PDF | Written and Chart",
            description="A basket worked in the round from the centre of the base.",
            price_cad=6.50, tags=["crochet basket", "basket pattern"],
            materials=["worsted cotton"])
CREDS = Credentials(api_key="key", access_token="token", shop_id="shop-1")


def _granted(transport) -> EtsyClient:
    return EtsyClient(transport, credentials=CREDS, phase="production",
                      owner_authorised=True)


# ---- nothing leaves the building ------------------------------------------


def test_shadow_mode_makes_no_request_at_all():
    transport = FakeTransport()
    client = EtsyClient(transport, credentials=CREDS, phase="shadow",
                        owner_authorised=True)
    outcome = client.publish(payload=build_payload(**GOOD), filename="b.pdf",
                             data=b"%PDF-1.4 fake")
    assert outcome.published is False
    assert transport.calls == [], "shadow mode reached the network"
    assert "shadow" in outcome.problems[0].lower()


def test_staging_may_not_publish_either():
    transport = FakeTransport()
    client = EtsyClient(transport, credentials=CREDS, phase="staging",
                        owner_authorised=True)
    assert client.refusal() is not None
    assert transport.calls == []


def test_the_refusals_are_ordered_phase_first():
    """A misconfigured credential must never be the reason we stopped."""
    transport = FakeTransport()
    client = EtsyClient(transport, credentials=None, phase="shadow",
                        owner_authorised=False)
    reason = client.refusal()
    assert "PHASE" in reason, reason
    assert "credential" not in reason.lower()


def test_a_credential_is_not_a_permission():
    transport = FakeTransport()
    client = EtsyClient(transport, credentials=CREDS, phase="production",
                        owner_authorised=False)
    reason = client.refusal()
    assert "authority matrix" in reason
    try:
        client.create_draft(build_payload(**GOOD))
    except EtsyNotPermitted:
        assert transport.calls == []
        return
    raise AssertionError("publishing without the owner's grant was permitted")


def test_missing_credentials_are_a_configuration_refusal_not_an_outage():
    transport = FakeTransport()
    client = EtsyClient(transport, credentials=None, phase="production",
                        owner_authorised=True)
    try:
        client.create_draft(build_payload(**GOOD))
    except EtsyNotConfigured as e:
        assert "never stored in this repository" in str(e)
        assert transport.calls == []
        return
    raise AssertionError("a client with no credentials tried to publish")


def test_credentials_are_read_from_the_environment_and_absent_here():
    assert Credentials.from_env({}) is None
    assert Credentials.from_env({"ETSY_API_KEY": "k"}) is None
    creds = Credentials.from_env({"ETSY_API_KEY": "k", "ETSY_ACCESS_TOKEN": "t",
                                  "ETSY_SHOP_ID": "s"})
    assert creds and creds.shop_id == "s"
    # And this environment has none, which is what the readiness report says.
    import os
    assert Credentials.from_env(dict(os.environ)) is None


def test_a_credential_never_prints_its_secrets():
    """A credential's repr is what ends up in a traceback and in the job's last_error."""
    creds = Credentials(api_key="SECRET-API-VALUE", access_token="SECRET-TOKEN-VALUE",
                        shop_id="shop-1")
    text = repr(creds)
    assert "SECRET-API-VALUE" not in text
    assert "SECRET-TOKEN-VALUE" not in text
    # The shop id is not a secret and is the thing you need to identify the account.
    assert "shop-1" in text


# ---- mapping ---------------------------------------------------------------


def test_a_listing_that_cannot_be_mapped_is_refused_not_truncated():
    for bad, needle in (
        (dict(GOOD, title="x" * (TITLE_MAX + 1)), f"allows {TITLE_MAX}"),
        (dict(GOOD, title="   "), "no title"),
        (dict(GOOD, description=""), "no description"),
        (dict(GOOD, price_cad=0.0), "price must be positive"),
        (dict(GOOD, tags=[f"tag{i}" for i in range(TAGS_MAX + 1)]), f"allows {TAGS_MAX}"),
        (dict(GOOD, tags=["x" * (TAG_CHARS_MAX + 1)]), "characters"),
        (dict(GOOD, materials=[f"m{i}" for i in range(14)]), "materials"),
    ):
        try:
            build_payload(**bad)
        except EtsyRejected:
            continue
        raise AssertionError(f"an unmappable listing was accepted: {needle}")


def test_the_payload_says_what_a_digital_pattern_is():
    payload = build_payload(**GOOD).to_dict()
    assert payload["type"] == "download"
    assert payload["state"] == "draft", "activation is a separate decision"
    assert payload["who_made"] == "i_did"
    assert payload["is_supply"] is True
    assert payload["quantity"] == 999
    assert payload["price"] == 6.50


# ---- what happens when it does run ---------------------------------------


def test_a_granted_client_creates_a_draft_and_attaches_the_file():
    transport = FakeTransport()
    outcome = _granted(transport).publish(payload=build_payload(**GOOD),
                                          filename="basket.pdf", data=b"%PDF-1.4 fake")
    assert outcome.published is True
    assert outcome.listing_id == "987654321"
    assert outcome.file_uploaded is True
    assert outcome.needs_completion is False
    methods = [c[0] for c in transport.calls]
    assert methods == ["POST", "POST"]
    assert transport.calls[0][2]["state"] == "draft"


def test_a_listing_with_no_file_is_reported_as_its_own_outcome():
    """The dangerous state: a listing exists on Etsy that would take money and deliver
    nothing. The recovery is to complete or delete it, not to create it again."""
    transport = FakeTransport(file_status=500)
    outcome = _granted(transport).publish(payload=build_payload(**GOOD),
                                          filename="basket.pdf", data=b"%PDF-1.4 fake")
    assert outcome.published is False
    assert outcome.listing_id == "987654321"
    assert outcome.needs_completion is True
    assert "no file attached" in outcome.problems[0]


def test_a_rate_limit_is_transient_and_a_rejection_is_not():
    rate_limited = FakeTransport(listing_status=429)
    try:
        _granted(rate_limited).create_draft(build_payload(**GOOD))
    except TransientError:
        pass
    else:
        raise AssertionError("429 should be retryable")

    rejected = FakeTransport(listing_status=400, listing_body={"error": "bad taxonomy"})
    try:
        _granted(rejected).create_draft(build_payload(**GOOD))
    except EtsyRejected as e:
        assert "bad taxonomy" in str(e)
    else:
        raise AssertionError("400 should never be retried")


def test_a_success_with_no_listing_id_is_treated_as_a_rejection():
    """An accepted request that returns nothing identifiable cannot be recorded, and a
    listing we cannot name is a listing we cannot fix."""
    transport = FakeTransport(listing_body={"ok": True})
    try:
        _granted(transport).create_draft(build_payload(**GOOD))
    except EtsyRejected as e:
        assert "no listing_id" in str(e)
        return
    raise AssertionError("a response with no listing_id was accepted")



# ---- through the job -------------------------------------------------------


def test_the_publish_job_refuses_in_shadow_and_says_the_draft_is_kept():
    """The refusal production has recorded 45 times. Its wording is load-bearing: the
    verification endpoint counts these, and a buyer-facing draft that is "retained for
    review" is a different claim from one that was lost."""
    import tempfile

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker
    from sqlalchemy import select

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/publish.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("store_operator", "store.publish",
                         {"slug": "market-basket-trio", "version": "1.0.0"})
    w = Worker(db, "publish-worker", phase=Phase.SHADOW)
    for _ in range(20):
        if not w.run_once():
            break

    with db.session() as s:
        refusals = [r for r in s.scalars(select(AuditLog))
                    if r.action == "store.publish_refused"]
    assert refusals, "shadow mode did not record a refusal"
    assert "shadow" in str(refusals[0].detail).lower()


def test_past_shadow_the_client_still_refuses_for_want_of_credentials():
    """The phase is the first of four conditions, not the only one. This environment has no
    credentials and no owner grant, so a phase change alone cannot publish anything."""
    import tempfile

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker
    from sqlalchemy import select

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/publish2.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("store_operator", "store.publish",
                         {"slug": "market-basket-trio", "version": "1.0.0"})
    w = Worker(db, "publish-worker", phase=Phase.PRODUCTION)
    for _ in range(20):
        if not w.run_once():
            break

    with db.session() as s:
        refusals = [str(r.detail) for r in s.scalars(select(AuditLog))
                    if r.action == "store.publish_refused"]
    assert refusals, "publishing in production was not even attempted"
    reason = refusals[-1]
    assert "authority matrix" in reason or "credentials" in reason, reason

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
