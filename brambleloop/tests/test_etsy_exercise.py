"""The operator trigger that runs the prepared Etsy exercise inside production.

`etsy_probe.run_exercise` was written, tested and then had no caller but a CLI `main()`. This
suite is about the thing that now calls it: an `opsauth`-guarded endpoint, a client that
cannot activate, a durable record of any draft it creates, and a refresh-token rotation proof.

**What these tests can and cannot prove is the most important line in this file.** They run
against `tests/fake_etsy.py`, a local server built from Etsy's own document by the same hand
that read that document to write the client. A green run here establishes that our side of
the wire is correct against our reading of Etsy; it establishes nothing about Etsy, and
`test_a_green_run_against_the_fake_promotes_nothing` asserts that the code agrees.

Written to fail in the directions that matter:

* **Activation must be unreachable, not merely unrequested.** One test drives a whole run
  through a recording transport and asserts that no request anywhere in it carried a `state`
  field; another pins `EtsyClient.activate`'s source byte for byte; a third makes
  `refusal_for` lie and asserts the run refuses to start rather than running.
* **A stranded draft must be visible without a re-run.** One test breaks the fake's delete,
  asserts the listing id and title reach the owner queue and the durable ledger, then repairs
  the fake and asserts the next run's step-0 sweep removes it.
* **The rotation proof must fail under the defect it closed.** One test reinstates the old
  `TokenProvider` with no `on_refresh` and asserts that round B is refused by the fake with
  `invalid_grant` -- the failure that looks exactly like a revoked app.

Nothing here touches Etsy, creates a real listing, activates anything or costs a cent.
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/exercise.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"

OPS_TOKEN = "operator-token-for-tests-0123456789"
SEAL_KEY = "a-test-sealing-key-of-quite-sufficient-length-0123456789"
SCOPES = ("listings_r", "listings_w", "listings_d", "shops_r", "shops_w")
FIRST_REFRESH_TOKEN = "111.refresh-one"

os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN
os.environ["BRAMBLELOOP_SECRET_KEY"] = SEAL_KEY
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ["ETSY_KEYSTRING"] = "fakekeystring"
os.environ["ETSY_SHARED_SECRET"] = "fakesharedsecret"
os.environ["ETSY_SHOP_ID"] = "12345"
os.environ["ETSY_REDIRECT_URI"] = "https://brambleloop.example/api/etsy/oauth/callback"
os.environ.pop("ETSY_REFRESH_TOKEN", None)
os.environ.pop("ETSY_ACCESS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from brambleloop.app import main as app_main  # noqa: E402
from brambleloop.core import oauth_store  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, OAuthCredential, OwnerAction,
)
from brambleloop.integrations import etsy as etsy_module  # noqa: E402
from brambleloop.integrations import etsy_exercise, etsy_oauth, etsy_probe  # noqa: E402
from brambleloop.integrations import http as etsy_http  # noqa: E402
from brambleloop.integrations.etsy import Authority, EtsyClient  # noqa: E402
from brambleloop.integrations.http import UrllibTransport  # noqa: E402

from tests.fake_etsy import FakeEtsy  # noqa: E402

DB = app_main.db
DB.create_all()


# ---------------------------------------------------------------------------
# Harness


class Recording(UrllibTransport):
    """The real transport, with a note of every request made through it.

    Used rather than a stub so the bytes on the wire are still the bytes the client produces.
    What is recorded is the form dictionary, which is what makes "no request anywhere in this
    run carried a `state` field" an assertion about the wire rather than about intent.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict] = []

    def request(self, method, url, *, headers, json=None, form=None, multipart=None):
        self.sent.append({"method": method, "url": url, "form": dict(form or {}),
                          "json": dict(json or {}),
                          "multipart": getattr(multipart, "field", None)})
        return super().request(method, url, headers=headers, json=json, form=form,
                               multipart=multipart)


@contextlib.contextmanager
def pointed_at(fake: FakeEtsy):
    """Point the client class and the OAuth token host at the local fake.

    Patched at the class and at the module global rather than through a constructor argument,
    because `src/` deliberately offers no way to redirect a production client: `EtsyClient`'s
    `base` is documented as test-only and nothing in `src/` sets it. A test may reach in; the
    application may not.
    """
    base, token_url, alternate, ping = (EtsyClient.BASE, etsy_oauth.TOKEN_URL,
                                        etsy_oauth.TOKEN_URL_ALTERNATE, etsy_http.PING_URL)
    EtsyClient.BASE = fake.base
    etsy_oauth.TOKEN_URL = fake.token_url
    etsy_oauth.TOKEN_URL_ALTERNATE = fake.token_url
    # The ping is a real request to a real host. Redirected too, so that no test in this
    # suite ever leaves the loopback interface.
    etsy_http.PING_URL = f"{fake.base}/openapi-ping"
    try:
        yield
    finally:
        EtsyClient.BASE = base
        etsy_oauth.TOKEN_URL = token_url
        etsy_oauth.TOKEN_URL_ALTERNATE = alternate
        etsy_http.PING_URL = ping


def reset(*, credential: str | None = FIRST_REFRESH_TOKEN) -> None:
    """Empty every row this module reads or writes, then seal one credential."""
    with DB.session() as s:
        s.execute(delete(OAuthCredential))
        s.execute(delete(OwnerAction))
        s.execute(delete(AuditLog).where(AuditLog.action.in_(
            [etsy_exercise.DRAFT_CREATED, etsy_exercise.DRAFT_REMOVED,
             etsy_exercise.RUN_STARTED, etsy_exercise.RUN_FINISHED, "etsy.exercise"])))
    if credential:
        oauth_store.save_refresh_token(DB, credential, scopes=" ".join(SCOPES),
                                       source="test", new_grant=True)


def green_verify() -> dict:
    """A twelve-of-twelve `/api/verify`, so a run's verdict is not hostage to fixture data.

    The real handler is exercised separately, in
    `test_the_real_api_verify_handler_is_what_the_endpoint_passes_in`.
    """
    return {"ok": True, "checks": [{"check": f"check_{i}", "ok": True} for i in range(12)]}


def run_full(fake: FakeEtsy, *, transport=None, verify=green_verify, mode="full") -> dict:
    transport = transport if transport is not None else Recording()
    with pointed_at(fake):
        return etsy_exercise.run(DB, transport=transport, mode=mode, verify=verify)


def secrets_in_play(fake: FakeEtsy) -> list[str]:
    values = [fake.shared_secret, OPS_TOKEN, SEAL_KEY, FIRST_REFRESH_TOKEN]
    values += list(fake.refresh_tokens) + list(fake.tokens)
    values += list(fake.authorization_codes)
    return [v for v in values if v and len(v) >= 8]


# ---------------------------------------------------------------------------
# The guard: exactly what `opsauth` does everywhere else


def test_the_trigger_refuses_everybody_when_no_operator_token_is_configured():
    """503, not 200. Unconfigured means closed.

    The opposite default is how an endpoint that writes to a real shop ends up open to the
    internet during the window between a deploy and remembering to set a variable.
    """
    previous = os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
    try:
        with TestClient(app_main.app) as client:
            response = client.post("/api/etsy/exercise",
                                   headers={"Authorization": f"Bearer {OPS_TOKEN}"})
        assert response.status_code == 503, response.text
        assert "BRAMBLELOOP_OPS_TOKEN" in response.json()["error"]
        assert OPS_TOKEN not in response.text
    finally:
        if previous is not None:
            os.environ["BRAMBLELOOP_OPS_TOKEN"] = previous


def test_the_trigger_is_401_for_a_wrong_credential_and_for_none_at_all():
    with TestClient(app_main.app) as client:
        for headers in ({}, {"Authorization": "Bearer not-the-operator-token-but-long"},
                        {"Authorization": f"Bearer {OPS_TOKEN}x"},
                        {"Authorization": OPS_TOKEN[:-1]}):
            response = client.post("/api/etsy/exercise", headers=headers)
            assert response.status_code == 401, (headers, response.text)
            assert response.json() == {"error": "operator credential required"}


def test_a_refused_call_sends_not_one_byte_to_etsy():
    """The guard has to run before anything reaches the network, not after.

    Every outbound request is made to raise, so a single one is an assertion failure with a
    name rather than a mysterious pass.
    """
    calls: list[str] = []

    def explode(self, method, url, **kw):
        calls.append(url)
        raise AssertionError(f"a refused call reached the network: {method} {url}")

    original = UrllibTransport.request
    UrllibTransport.request = explode          # type: ignore[assignment]
    try:
        with TestClient(app_main.app) as client:
            assert client.post("/api/etsy/exercise").status_code == 401
            assert client.post("/api/etsy/exercise",
                               headers={"Authorization": "Bearer wrong-but-long-enough-xx"}
                               ).status_code == 401
    finally:
        UrllibTransport.request = original     # type: ignore[assignment]
    assert calls == [], calls


# ---------------------------------------------------------------------------
# Activation: unreachable, and pinned


ACTIVATE_SOURCE_SHA256 = "1c176679c097260b356ba212d5f1b5868ed3c852f7379a3559dc1ae111975b29"


def test_activate_keeps_its_three_gates_byte_for_byte():
    """A deliberate tripwire over `EtsyClient.activate`.

    The lane that added the trigger was required to leave activation's gates unchanged, and
    "unchanged" is a property of bytes rather than of intent. If this fails, the question is
    not how to update the constant: it is whether the change was meant, reviewed and still
    leaves all three gates -- phase, owner authority, and a Launch-0 string on the call
    itself -- in that order. Update the hash only after answering that.
    """
    source = inspect.getsource(EtsyClient.activate)
    assert hashlib.sha256(source.encode()).hexdigest() == ACTIVATE_SOURCE_SHA256, (
        "EtsyClient.activate has changed. See this test's docstring before touching the hash.")
    assert "self._require(Authority.ACTIVATE)" in source
    assert "if not launch_authorisation.strip():" in source
    assert 'form={"state": "active"}' in source


def test_the_exercise_client_can_never_activate_whatever_the_phase_says():
    """The phase is not what stops this, which is the point.

    `BRAMBLELOOP_PHASE` is an environment variable and environment variables change. The
    client is built with `owner_authorised=False`, which `refusal()` checks second and which
    nothing in this module exposes, so even a deployment that has graduated to production
    gets a refusal here.
    """
    reset()
    with FakeEtsy() as fake, pointed_at(fake):
        for phase in ("shadow", "staging", "limited_production", "production"):
            env = dict(os.environ, BRAMBLELOOP_PHASE=phase)
            client = etsy_exercise._client(DB, env, UrllibTransport(), breadcrumbs=False)
            refusal = client.refusal_for(Authority.ACTIVATE)
            assert refusal, f"phase={phase} produced an activation authority"
            assert client.owner_authorised is False
            # And the narrower grant it does hold is the draft one, which is the whole design.
            assert client.refusal_for(Authority.DRAFT_WRITE) is None


def test_the_run_refuses_to_start_if_its_client_ever_reports_an_activation_authority():
    """The assertion in `_client` is load-bearing, so it is made to fire.

    `refusal_for` is replaced with one that permits everything -- the shape a future
    loosening of the gates would have -- and the run must refuse rather than proceed with a
    client that could publish.
    """
    reset()
    original = EtsyClient.refusal_for
    EtsyClient.refusal_for = lambda self, authority: None   # type: ignore[assignment]
    try:
        with FakeEtsy() as fake, pointed_at(fake):
            try:
                etsy_exercise.run(DB, transport=Recording(), verify=green_verify)
            except etsy_exercise.ExerciseRefused as e:
                assert "REFUSING TO RUN" in str(e)
                assert "activate" in str(e).lower()
            else:
                raise AssertionError("the run started with a client that could activate")
    finally:
        EtsyClient.refusal_for = original       # type: ignore[assignment]


def test_no_request_in_a_whole_run_ever_carries_a_listing_state():
    """Measured on the wire, not in the code.

    Activation is one field on one PATCH: `state=active`. This asserts that no request the
    run made -- create, image, update, the deliberate refusal probes, delete -- carried a
    `state` field at all, and that the listing Etsy held was a draft every time it was read.
    """
    reset()
    transport = Recording()
    with FakeEtsy() as fake:
        report = run_full(fake, transport=transport)
        with_state = [r for r in transport.sent
                      if "state" in r["form"] or "state" in r["json"]]
        assert with_state == [], with_state
        assert not any(listing.get("state") == "active"
                       for listing in fake.listings.values()), fake.listings

    exercise = report["exercise"]
    assert exercise["activation_attempted"] is False
    assert report["activation"]["attempted"] is False
    assert report["activation"]["activate"], "no refusal reason was recorded"
    refusals = [s for s in exercise["steps"] if s["step"] == "refusals_hold"][0]
    assert refusals["ok"] is True
    assert "NOT REFUSED" not in str(refusals["observed"])
    # The state Etsy reported while the draft existed.
    read_back = [s for s in exercise["steps"] if s["step"] == "verify_contract"][0]
    assert read_back["observed"]["state_on_etsy"] == "draft"


# ---------------------------------------------------------------------------
# The run itself


def test_a_full_run_walks_every_step_and_leaves_the_shop_clean():
    reset()
    with FakeEtsy() as fake:
        report = run_full(fake)
        assert fake.listings == {}, "the fake shop still holds a listing"

    steps = [s["step"] for s in report["exercise"]["steps"]]
    assert steps == ["sweep", "identity", "create_draft", "upload_image", "update_listing",
                     "refusals_hold", "read_back", "verify_contract", "cleanup",
                     "verify_cleanup"], steps
    assert report["exercise"]["verified"] is True
    assert report["exercise"]["cleaned_up"] is True
    assert report["exercise"]["cleanup_verified"] is True
    assert report["exercise"]["left_behind"] == []
    assert report["shop_is_clean"] is True
    assert report["owner_actions"] == []
    assert report["ok"] is True
    assert "CA$0" in report["costs"]
    # Step 0's first half: measured, not assumed. The taxonomy uses it to decide whether a
    # later refusal is the network rather than our bytes.
    assert report["ping"]["reachable"] is True, report["ping"]
    assert report["ping"]["sent_api_key_header"] is True


def test_the_draft_is_labelled_so_a_human_who_finds_it_knows_not_to_buy_it():
    reset()
    seen: list[str] = []
    with FakeEtsy() as fake:
        original = FakeEtsy._new_listing

        def watch(self, fields, repeated=()):
            record = original(self, fields, repeated)
            seen.append(record["title"])
            return record

        FakeEtsy._new_listing = watch          # type: ignore[assignment]
        try:
            report = run_full(fake)
        finally:
            FakeEtsy._new_listing = original   # type: ignore[assignment]

    assert len(seen) == 1, f"the run created {len(seen)} listings; it must create exactly one"
    assert seen[0].startswith("DO NOT BUY - Brambleloop transport test"), seen
    assert report["exercise"]["listing_title"].startswith("DO NOT BUY")


def test_a_green_run_against_the_fake_promotes_nothing():
    """The fake is our reading of Etsy's document, so no run against it is evidence of Etsy."""
    reset()
    with FakeEtsy() as fake:
        report = run_full(fake)
    assert report["against_etsy"] is False
    assert "LOCAL MODEL OF ETSY, NOT ETSY" in report["status"]
    promoted = [c for c in report["exercise"]["claims"]
                if c["state_after"] == "VERIFIED_AGAINST_ETSY"
                and c["state_before"] != "VERIFIED_AGAINST_ETSY"]
    assert promoted == [], promoted


def test_running_twice_leaves_one_shop_not_two():
    reset()
    with FakeEtsy() as fake:
        first = run_full(fake)
        second = run_full(fake)
        assert fake.listings == {}
    for report in (first, second):
        assert report["ok"] is True
        assert report["shop_read_back"]["test_drafts_remaining"] == []
    # The second run's sweep found nothing, because the first cleaned up after itself.
    sweep = [s for s in second["exercise"]["steps"] if s["step"] == "sweep"][0]
    assert sweep["observed"]["stale_drafts_found"] == 0, sweep


def test_a_draft_left_by_a_previous_attempt_is_swept_before_this_one_starts():
    """The property that makes the trigger safe to run twice, exercised end to end.

    The first run's delete is broken, so it strands a draft in a real shop -- the exact
    failure this design is against. The delete is then repaired and the run repeated against
    the same shop: step 0 must remove the stranded listing, and the ledger must be left with
    nothing outstanding.
    """
    reset()
    with FakeEtsy(delete_failure=(403, "You do not have permission to delete this "
                                       "listing.")) as fake:
        stranded = run_full(fake)
        stuck = list(fake.listings)
        assert len(stuck) == 1, fake.listings
        listing_id = stuck[0]

        assert stranded["ok"] is False
        assert stranded["shop_is_clean"] is False
        named = str(stranded["owner_actions"])
        assert listing_id in named, named
        assert "DO NOT BUY" in named
        assert "Shop Manager" in named

        # The durable ledger, which is what a killed container leaves behind.
        open_rows = etsy_exercise.outstanding_drafts(DB)
        assert [row["listing_id"] for row in open_rows] == [listing_id], open_rows

        # The same shop, with the delete working again.
        fake.delete_failure = None
        recovered = run_full(fake)
        assert fake.listings == {}, "the sweep did not remove the stale draft"

    sweep = [s for s in recovered["exercise"]["steps"] if s["step"] == "sweep"][0]
    assert sweep["observed"]["stale_drafts_found"] == 1, sweep
    assert [row["listing_id"] for row in sweep["observed"]["removed"]] == [listing_id]
    assert recovered["shop_is_clean"] is True
    assert etsy_exercise.outstanding_drafts(DB) == []


def test_the_draft_is_written_down_durably_before_the_run_can_lose_it():
    """A row in the audit ledger, not a list in memory.

    `run_exercise` keeps `left_behind` in a Python list, which is right for a function and
    worth nothing if the process dies. The breadcrumb is what a different container can read
    afterwards, so this asserts the row exists with the listing id and the title on it.
    """
    reset()
    with FakeEtsy(delete_failure=(500, "Internal Server Error")) as fake:
        report = run_full(fake)
        listing_id = list(fake.listings)[0]

    with DB.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == etsy_exercise.DRAFT_CREATED)))
    assert len(rows) == 1, rows
    detail = rows[0].detail
    assert detail["listing_id"] == listing_id
    assert detail["title"].startswith("DO NOT BUY")
    assert report["breadcrumbs"]["still_on_etsy"][0]["listing_id"] == listing_id


def test_a_stranded_draft_raises_one_owner_action_however_often_the_run_repeats():
    """One row per artefact, not one per attempt.

    The repeats are `mode=rotation` runs, which create no draft of their own: what is being
    measured is that re-reconciling the *same* stuck listing does not fill the owner queue
    with duplicates of one two-minute job.
    """
    reset()
    with FakeEtsy(delete_failure=(403, "no")) as fake:
        run_full(fake)
        listing_id = list(fake.listings)[0]
        run_full(fake, mode="rotation")
        run_full(fake, mode="rotation")
    with DB.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.done == False)))  # noqa: E712
    keys = [r.requirement_key for r in rows]
    assert keys == [f"{etsy_exercise.STRANDED_KEY}.{listing_id}"], keys
    assert rows[0].max_cost_cad == 0.0
    assert listing_id in rows[0].action and "DO NOT BUY" in rows[0].action


def test_the_shop_is_read_back_from_etsy_rather_than_from_the_runs_own_bookkeeping():
    """`shop_is_clean` must come from Etsy, not from the list the run kept while it worked.

    A marker-titled draft is put into the shop *after* the run has finished and reported a
    clean shop. The run's own record still says clean; the read of Etsy must not.
    """
    reset()
    with FakeEtsy() as fake, pointed_at(fake):
        report = run_full(fake)
        assert report["shop_is_clean"] is True

        fake.listings["999"] = {
            "listing_id": 999, "shop_id": int(fake.shop_id), "state": "draft",
            "title": f"{etsy_probe.TEST_TITLE_PREFIX} left-by-a-killed-container",
            "tags": [], "materials": [], "description": "", "quantity": 1,
            "price": {"amount": 999, "divisor": 100, "currency_code": "CAD"},
            "taxonomy_id": 66, "listing_type": "download", "who_made": "i_did",
            "when_made": "made_to_order", "is_supply": True, "file_data": "", "url": ""}
        fake.images["999"] = []
        client = etsy_exercise._client(DB, dict(os.environ), UrllibTransport(),
                                       breadcrumbs=False)
        seen = etsy_exercise.shop_read_back(client)

    assert seen["ok"] is False
    assert [row["listing_id"] for row in seen["test_drafts_remaining"]] == ["999"]
    assert "read of Etsy" in seen["measured_by"]


def test_only_one_exercise_may_run_at_a_time():
    """A second call is refused rather than allowed to sweep the first run's draft."""
    reset()
    assert etsy_exercise._IN_PROCESS.acquire(blocking=False)
    try:
        with TestClient(app_main.app) as client:
            response = client.post("/api/etsy/exercise",
                                   headers={"Authorization": f"Bearer {OPS_TOKEN}"})
        assert response.status_code == 409, response.text
        assert "Only one may run at a time" in response.json()["error"]
    finally:
        etsy_exercise._IN_PROCESS.release()


def test_the_run_states_which_single_flight_guarantee_was_actually_in_force():
    """On SQLite there is no advisory lock, and the report must not imply there was one."""
    reset()
    with FakeEtsy() as fake:
        report = run_full(fake)
    assert report["single_flight"]["held"] is True
    assert "this process only" in report["single_flight"]["scope"]


def test_the_report_carries_the_credential_and_the_verify_verdict_after_cleanup():
    reset()
    with FakeEtsy() as fake:
        report = run_full(fake)
    after = report["after"]
    assert after["oauth"]["openable"] is True
    assert after["oauth"]["stored"] is True
    assert after["verify"] == {"ok": True, "passed": 12, "total": 12, "failed": []}


def test_the_real_api_verify_handler_is_what_the_endpoint_passes_in():
    """Wiring, not a stub: the endpoint must hand the exercise `/api/verify`'s own answer."""
    snapshot = app_main._verify_snapshot()
    assert "checks" in snapshot and snapshot["checks"], snapshot
    assert all("check" in row and "ok" in row for row in snapshot["checks"])
    source = inspect.getsource(app_main.api_etsy_exercise)
    assert "verify=_verify_snapshot" in source


def test_a_run_whose_verify_is_red_is_not_reported_as_ok():
    reset()

    def red() -> dict:
        return {"ok": False, "checks": [{"check": "phase_is_shadow", "ok": False}]}

    with FakeEtsy() as fake:
        report = run_full(fake, verify=red)
    assert report["after"]["verify"] == {"ok": False, "passed": 0, "total": 1,
                                         "failed": ["phase_is_shadow"]}
    assert report["ok"] is False


def test_the_endpoint_refuses_with_409_when_there_is_no_credential_to_run_with():
    reset(credential=None)
    with TestClient(app_main.app) as client:
        response = client.post("/api/etsy/exercise",
                               headers={"Authorization": f"Bearer {OPS_TOKEN}"})
    assert response.status_code == 409, response.text
    body = response.json()
    assert "oauth" in body["error"].lower() or "credential" in body["error"].lower()
    assert body["credential"]["stored"] is False
    assert OPS_TOKEN not in response.text and SEAL_KEY not in response.text


# ---------------------------------------------------------------------------
# The rotation proof


def test_the_rotation_proof_rotates_twice_and_seals_each_one():
    """Two rounds, three distinct fingerprints, and the row rises by exactly two.

    Round A proves Etsy issued a *different* refresh token and that the new one was sealed.
    Round B proves a credential whose refresh token could only have come from that sealed row
    is accepted -- the boundary the defect crossed.
    """
    reset()
    before = oauth_store.credential_health(DB)
    with FakeEtsy() as fake, pointed_at(fake):
        proof = etsy_exercise.rotation_proof(DB, env=dict(os.environ),
                                             transport=UrllibTransport())
    assert proof["ok"] is True, proof
    assert [r["round"] for r in proof["rounds"]] == ["A", "B"]
    for entry in proof["rounds"]:
        assert entry["ok"] is True, entry
        assert entry["etsy_issued_a_different_refresh_token"] is True
        assert entry["carried_the_stored_token"] is True, entry
        assert entry["stored_value_is_the_live_one"] is True, entry
        assert entry["after"]["openable"] is True
    assert proof["rotations"] == {"before": before["rotations"],
                                  "after": before["rotations"] + 2}
    assert proof["distinct_fingerprints"] == 3, proof["fingerprint_chain"]
    assert "does_not_establish" in proof and "operating-system process" in \
        proof["does_not_establish"]
    assert "/api/etsy/oauth/status" in proof["how_that_closes_for_free"]


def test_a_full_run_takes_the_rotation_counter_from_zero_to_three():
    """Three, not two, and the third is the interesting one.

    The exercise's *own* first authenticated call already forces a refresh: a credential
    built from the sealed store carries no live access token, so `Credentials.from_env`
    gives it `expires_at = 0.0` and `TokenProvider` refreshes before the first request. The
    proof then adds its two rounds. That first rotation is the one that would have happened
    unobserved in production, and it is why `rotations: 0` was never going to stay 0 by
    accident -- it stayed 0 because nothing had ever made an authenticated Etsy call.
    """
    reset()
    assert oauth_store.credential_health(DB)["rotations"] == 0
    with FakeEtsy() as fake:
        report = run_full(fake)
    assert report["after"]["oauth"]["rotations"] == 3, report["after"]["oauth"]
    assert report["rotation"]["rotations"] == {"before": 1, "after": 3}
    assert report["after"]["oauth"]["openable"] is True


def test_round_b_builds_its_credential_only_from_the_sealed_row():
    """The fingerprint it carries is the one the database holds, and no other.

    If round B were quietly reusing an object round A left behind, this equality would hold
    against round A's *live* token rather than the stored one, and the defect would pass the
    test it exists to fail.
    """
    reset()
    with FakeEtsy() as fake, pointed_at(fake):
        proof = etsy_exercise.rotation_proof(DB, env=dict(os.environ),
                                             transport=UrllibTransport())
    a, b = proof["rounds"]
    assert b["before"]["fingerprint"] == a["after"]["fingerprint"], (a, b)
    assert b["carried_the_stored_token"] is True
    assert "sealed oauth_credentials row" in b["credential_was_built_from"]


def test_with_the_defect_reinstated_round_b_is_refused_by_etsy():
    """The injected defect: a `TokenProvider` with no `on_refresh`.

    This is the bug that was found and closed. With it back, round A still succeeds -- which
    is exactly why it went unnoticed -- and round B presents a refresh token Etsy has already
    spent. The fake forgets a spent token, so the answer is `invalid_grant`: the failure that
    looks exactly like a revoked app, arriving on day two with nobody watching.
    """
    reset()
    original = etsy_module._persisting_on_refresh
    etsy_module._persisting_on_refresh = lambda db, env, current_token=None: None
    try:
        with FakeEtsy() as fake, pointed_at(fake):
            proof = etsy_exercise.rotation_proof(DB, env=dict(os.environ),
                                                 transport=UrllibTransport())
    finally:
        etsy_module._persisting_on_refresh = original

    assert proof["ok"] is False, proof
    first = proof["rounds"][0]
    # Round A refreshed against Etsy and the store did not move: the whole defect in one row.
    assert first["ok"] is False
    assert first["after"]["rotations"] == first["before"]["rotations"]
    assert "spent" in first.get("danger", ""), first
    assert proof["stopped_after"] == "A"
    assert proof["owner_action"]["maximum_cost"] == "CA$0"


def test_the_defect_is_reproduced_all_the_way_to_invalid_grant():
    """Not only that the store did not move -- that the next process is locked out.

    The proof stops after round A by design, so this drives the second half directly: a
    credential rebuilt from the untouched store presents the pre-refresh token, and the fake
    answers with the error Etsy answers.
    """
    reset()
    original = etsy_module._persisting_on_refresh
    etsy_module._persisting_on_refresh = lambda db, env, current_token=None: None
    try:
        with FakeEtsy() as fake, pointed_at(fake):
            env = dict(os.environ)
            first = etsy_module.Credentials.from_env(env, transport=UrllibTransport(), db=DB)
            EtsyClient(UrllibTransport(), credentials=first, phase="shadow").get_shop()
            # A new container: everything above is gone, the store is all that is left.
            second = etsy_module.Credentials.from_env(env, transport=UrllibTransport(), db=DB)
            try:
                EtsyClient(UrllibTransport(), credentials=second, phase="shadow").get_shop()
            except etsy_oauth.EtsyAuthNeedsOwner as e:
                assert "400" in str(e), e
                assert "spent" in str(e) or "refresh token" in str(e)
            else:
                raise AssertionError(
                    "the spent refresh token was accepted, so this fake is not modelling "
                    "Etsy's rotation and the defect cannot be reproduced")
    finally:
        etsy_module._persisting_on_refresh = original


def test_the_proof_refuses_when_there_is_nothing_it_could_rotate():
    reset(credential=None)
    proof = etsy_exercise.rotation_proof(DB, env=dict(os.environ),
                                         transport=UrllibTransport())
    assert proof["ok"] is False
    assert "nothing to rotate" in proof["refused"]
    assert proof["rounds"] == []


def test_rotation_mode_creates_no_draft_at_all():
    """The safest form of the evidence: two shop reads and nothing else."""
    reset()
    transport = Recording()
    with FakeEtsy() as fake:
        report = run_full(fake, transport=transport, mode="rotation")
        assert fake.listings == {}
    assert report["exercise"]["skipped"].startswith("mode=rotation")
    assert report["rotation"]["ok"] is True
    assert report["shop_is_clean"] is True
    writes = [r for r in transport.sent if r["method"] in ("POST", "PATCH", "DELETE")
              and "/oauth/token" not in r["url"]]
    assert writes == [], writes
    assert etsy_exercise.outstanding_drafts(DB) == []


# ---------------------------------------------------------------------------
# Secrets


def test_no_credential_value_reaches_the_report_the_ledger_or_the_owner_queue():
    """One sweep over everything this run wrote, for every secret it handled.

    Checking only for the token a test happened to think of is how a verifier leaks: the
    fake's whole token store is swept, including the ones it minted during the run.
    """
    reset()
    with FakeEtsy() as fake:
        report = run_full(fake)
        proof_secrets = secrets_in_play(fake)

    with DB.session() as s:
        ledger = repr([(r.action, r.detail) for r in s.scalars(select(AuditLog))])
        queue = repr([(r.requirement_key, r.action, r.reason)
                      for r in s.scalars(select(OwnerAction))])
    blob = repr(report) + ledger + queue
    for secret in proof_secrets:
        assert secret not in blob, f"a secret reached a report, a log row or the owner queue"
    # And the credential is still identified, by fingerprint, so the report is still useful.
    assert "***" in repr(report["after"]["oauth"]["token_fingerprint"])


def test_the_rotation_proof_reports_fingerprints_and_never_a_token():
    reset()
    with FakeEtsy() as fake, pointed_at(fake):
        proof = etsy_exercise.rotation_proof(DB, env=dict(os.environ),
                                             transport=UrllibTransport())
        leaked = [s for s in secrets_in_play(fake) if s in repr(proof)]
    assert leaked == [], leaked
    for fingerprint in proof["fingerprint_chain"]:
        assert fingerprint.startswith("***") and len(fingerprint) == 11, fingerprint


def test_the_module_never_writes_a_secret_to_the_repository_or_reads_one_from_it():
    source = (ROOT / "src/brambleloop/integrations/etsy_exercise.py").read_text()
    assert "ETSY_REFRESH_TOKEN =" not in source
    for forbidden in ("open(", "write_text", "Path("):
        assert forbidden not in source, (
            f"{forbidden!r} appears in etsy_exercise.py: this module must not touch the "
            f"filesystem, because the only thing it holds is a credential")


if __name__ == "__main__":
    import traceback

    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            passed += 1
            # `OK` at column zero, because that is what run_tests.sh counts
            # (`grep -c '^OK'`). Printed as "  ok  ", every one of these checks passed
            # and none of them reached the total -- the suite ran, exited clean, and was
            # invisible to the thing that reports whether the suite ran.
            print(f"OK   {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
