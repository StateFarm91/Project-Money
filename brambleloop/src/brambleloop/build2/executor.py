"""The build loop, in the database rather than in a conversation.

The master intent asks for an autonomous build executor that never idles: owner-blocked work
is parked, the highest-value unblocked requirement continues, and losing a session is not
losing the build. This module is the machinery for that, and it exists because the previous
arrangement worked for the wrong reason.

Build 2 did route around the missing Etsy credential — eight milestones landed while it was
unavailable, and no requirement waited on it. But the thing that routed around it was a
session. The dependency graph was prose in BUILD_STATE, the priority queue was judgement, and
the parking decision was made once and remembered by whoever was in the conversation. All of
that evaporates when the session does. Autonomy that depends on a particular process staying
alive is not autonomy; it is a person with extra steps, and the failure is invisible right up
until the moment it matters.

So four things move into Postgres, where the deployed worker can read them:

**The graph.** Every requirement is a row with its dependencies and a derived state. `ready`
means nothing is stopping it. `blocked` means a requirement it needs is unfinished. `parked`
means the owner has to do something first — and parking is the interesting one.

**Parking is checkable or it is refused.** A task may only be parked on a *capability* whose
availability the code can test, and the capability is the one the access registry already
defines. "Waiting on the owner" as free text would make parking a place to put anything hard,
and a queue that can absorb its own difficulties never reports being blocked and never
finishes. Unparking is automatic: the capability becomes available, the task becomes ready,
and nothing has to remember.

**Never-idle is measured in requirements, not in ticks.** A loop that always has something to
do is trivially satisfiable by inventing work, which is the failure `swarm.next_work` already
names for agents and which applies with more force here. The watchdog therefore asks a harder
question than "is the loop running": it asks whether anything has been *completed* recently,
and it distinguishes idle-because-blocked from idle-because-nobody-looked. Those need
opposite responses and they look identical from outside.

**An owner action never stops the queue.** It becomes a row with a capability attached, the
requirements that wait on it are parked, and the loop moves to the next ready thing. The
owner's queue and the build queue are separate objects with one link between them, so the
build cannot be held up by a decision nobody has made yet.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import requirements as reg

READY = "ready"
BLOCKED = "blocked"
PARKED = "parked"
IN_PROGRESS = "in_progress"
DONE = "done"

STATES: tuple[str, ...] = (READY, BLOCKED, PARKED, IN_PROGRESS, DONE)

# Which registry statuses produce a schedulable task at all. `data_gated` requirements are
# not parked on a capability -- no credential makes a customer exist -- so they are held
# separately and never counted as executable.
SCHEDULABLE = (reg.PARTIAL, reg.MISSING)

# Sections ordered by how much of the business depends on them. A priority that is only the
# requirement number builds the document in order, which is the order it was written rather
# than the order it is needed.
SECTION_WEIGHT: dict[str, float] = {
    "MJsOffTheHookDesigns priority mission": 5.0,
    "Adversarial commercial + policy audit": 12.0,
    "Creativity engine + continuous improvement": 15.0,
    "Deep seasonal creativity audit": 18.0,
    "Proven-trend seasonal capture & lead-time engine": 20.0,
    "Core commercial upgrades": 25.0,
    "CA$5K/month scale architecture": 30.0,
    "24/7 cloud autonomy, agent swarms, continuous learning": 32.0,
    "Culture & nostalgia opportunity engine": 40.0,
    "Competitive product teardown laboratory": 45.0,
    "Visual asset production audit": 50.0,
    "Voice session reconciliation (model + MJs)": 60.0,
}
DEFAULT_SECTION_WEIGHT = 55.0

# A partial requirement is cheaper to finish than a missing one and is worth doing first: it
# already has a shape, and the gap is usually named in its note.
STATUS_BONUS: dict[str, float] = {reg.PARTIAL: -6.0, reg.MISSING: 0.0}

# How long a claim survives without progress before another worker may take it. A session
# that dies mid-requirement must not hold the task forever, which is the same lease logic the
# job queue already uses and for the same reason.
CLAIM_LEASE_MINUTES = 90

# No completion in this long, with ready work available, is the watchdog's alarm.
IDLE_ALARM_HOURS = 6


class ExecutorRefused(ValueError):
    """A park with no checkable condition, a cycle, or a completion with no evidence."""


# ---------------------------------------------------------------------------
# Dependencies
#
# Deliberately sparse. A dense graph invented up front would block most of the build on
# guesses about what needs what; these are the edges where building the second thing first
# genuinely produces something that has to be redone.

DEPENDENCIES: dict[int, tuple[int, ...]] = {
    # The pre-launch benchmark challenge cannot run before the teardown scorecard exists.
    168: (161, 162),
    # Improvement pipeline needs the findings it consumes.
    164: (161,),
    # The confidence gate reads the ladder.
    27: (274,),
    # Cannibalisation needs the contribution figures pricing produces.
    45: (24,),
    # The trajectory simulator reads the run-rate decomposition.
    26: (25,),
    # Culture radar's improvement wiring needs the improvement bus.
    147: (97,),
    # Seasonal collection calendar needs the lead-time engine's arithmetic.
    123: (283,),
    # Storefront takeovers need the collection architecture they would present.
    131: (143,),
}


# ---------------------------------------------------------------------------
# Owner gates
#
# Every owner-gated requirement is parked on one of these, and every gate has a condition the
# code can *test*. That is the load-bearing constraint: free text would make parking a place
# to put anything difficult, and a queue that can absorb its own difficulties never reports
# being blocked and never finishes. `sync()` refuses an owner-gated requirement with no gate
# rather than letting it drift into the ready list, where it would be work nobody can do.
#
# Two of these check database rows rather than environment variables, which is the point:
# the mechanism is "is this true yet", not "is there a credential".

def _env_gate(*names: str):
    def check(db, env) -> bool:
        import os

        e = env if env is not None else os.environ
        return all((e.get(n) or "").strip() for n in names)
    return check


def _has_customers(db, env) -> bool:
    """At least one real money event is recorded. Counted, not asked about.

    The one gate in this table the owner cannot grant. Every other capability here is a key
    somebody pastes; this one opens when a stranger buys something, and it exists because a
    requirement whose remainder needs orders has nowhere else to wait. Before this, #18 sat
    at the top of the ready queue advertising a measurement -- whether fast support reduces
    refunds -- that cannot be taken until refunds exist.

    Rows rather than a variable, for the same reason every other gate here counts something:
    a phase flag saying "we are selling now" is a claim, and a ledger entry is an event.
    """
    from sqlalchemy import func, select

    from ..core.models import LedgerEntry

    # Revenue with evidence, not any row (C-38). An expense is a LedgerEntry too, and the
    # first thing this company records is money going out -- counting every row opened the
    # gate on a hosting bill. A customer is money coming in, with the order it came from.
    with db.session() as s:
        return bool(s.scalar(select(func.count(LedgerEntry.id)).where(
            LedgerEntry.gross_cad > 0, LedgerEntry.evidence_ref.is_not(None),
            func.trim(LedgerEntry.evidence_ref) != "")))


def _has_live_listing(db, env) -> bool:
    """At least one listing exists on the marketplace. Counted from its own identifier.

    The second gate in this table nobody can grant by pasting a key, and unlike `customers`
    it is not waiting on a stranger -- it is waiting on the owner deciding to leave shadow
    mode. Impressions, click-through and favourites are all facts about a listing somebody
    can see, and no credential produces them for a listing that was never published.

    Counted rather than read from the phase flag, for the reason every other gate counts
    something: `BRAMBLELOOP_PHASE=production` is a statement of intent, and an Etsy listing
    id is a listing.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        return bool(s.scalar(
            select(Listing.id).where(Listing.etsy_listing_id != "").limit(1)))


def _benchmarks_purchased(db, env) -> bool:
    """The owner's ten benchmark patterns, counted rather than asked about."""
    from sqlalchemy import func, select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        return bool(s.scalar(select(func.count()).select_from(BenchmarkProduct)))


def _model_usable(db, env) -> bool:
    """A key is not a capability.

    The owner supplied an Anthropic key on 2026-09-19 and the first call it made returned
    "Your credit balance is too low to access the Anthropic API." The key authenticates; the
    account cannot serve a request. An environment-variable check would have opened this gate
    and un-parked four requirements onto work that cannot run, which is the queue advertising
    work nobody can start -- the exact failure this module exists to prevent. So the
    condition is a recorded successful call, and it opens by itself when one happens.
    """
    from ..gateway.anthropic import usable

    return usable(db)


def _etsy_usable(db, env) -> bool:
    """A credential is not a capability, for the same reason a key was not one.

    Etsy v3 refuses the keystring alone with "Shared secret is required in x-api-key
    header", so a half-configured credential is indistinguishable from a working one until
    something actually asks. The condition is therefore a recorded successful read, and it
    opens by itself when one happens.
    """
    from ..intel.etsy_public import usable

    return usable(db)


def _physical_proof_available(db, env) -> bool:
    """Whether any completed physical test exists to photograph a finished object from.

    #64's upgrade path triggers on tester or customer photography becoming available, and
    nobody has crocheted a Brambleloop sample. Counted from completed tests rather than from
    a flag saying testing is set up: the intake being built is not the same as a finished
    object existing, and the second is what a photograph needs.
    """
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest).limit(50)))
    return any(row.completed_at is not None for row in rows)


def _vision_usable(db, env) -> bool:
    """Whether a real image has actually been looked at, not whether a key is set.

    The same rule as `_model_usable`, applied to the capability that was hiding behind an
    environment-variable check. A text call succeeding proves the account serves requests
    and proves nothing about whether an image can be put in front of the model: a URL the
    provider cannot fetch, a format it refuses and a payload shape that is subtly wrong all
    fail here and nowhere else.
    """
    from ..gateway.anthropic import vision_usable

    return vision_usable(db)


def _rendered_pages_usable(db, env) -> bool:
    """Whether a rendered page has actually been fetched, not whether a URL is configured.

    `browser_vision` checked `BRAMBLELOOP_BROWSER_URL`, which is the one gate in this table
    that could be opened by typing -- and it stood in front of twenty-eight requirements.
    Setting a variable to a worker that is misconfigured, unreachable or refused by Etsy's
    bot protection would have released every one of them into the ready queue, which is the
    single failure this module exists to prevent, at the largest scale available in it.

    W4-B2CLOSE, 2026-10-10 (BUILD2_VERIFY finding 2): the gate now carries only #35 and #39,
    and what both need is a current reading of the etsy.com/legal policy pages -- which
    answer every automated reader 403 (closure.EXTERNAL_GATES), so no honest browser.probe
    can ever supply it. The closure's own remedy is a person reading the pages and recording
    them (POST /api/policy/snapshot). So the gate opens on either path: a recorded
    browser.probe, or `platform_policy.page_readings_status` -- every etsy.com/legal source
    read by a named person through the authenticated intake within MAX_AGE_DAYS, with no
    unreviewed material change. A stale, absent, anonymous or un-audited reading opens
    nothing, and the reading goes stale by itself after 30 days, closing the gate again.
    """
    from ..gates.platform_policy import page_readings_status
    from ..intel.browser import usable

    if usable(db):
        return True
    return bool(page_readings_status(db)["open"])


def _tester_recruited(db, env) -> bool:
    """Whether anybody has actually joined the tester or creator roster.

    #9 and #250 sat on `browser_vision`, and neither needs a browser: what they wait on is a
    person agreeing to test a pattern. The note on #250 said so in plain words -- "no tester
    has been recruited, so nobody has graduated" -- while the gate beside it named a cloud
    worker pool, so the queue would have released both the day a browser arrived.
    """
    from sqlalchemy import select

    from ..core.models import CreatorProfile

    # Somebody who *agreed*, not anybody on file (C-38). A CreatorProfile is written for a
    # prospect the moment they are observed, so counting rows opened this gate on a list of
    # people nobody has spoken to. Agreement is evidenced by a delivery or a recorded
    # permission.
    with db.session() as s:
        rows = s.execute(select(CreatorProfile.delivered, CreatorProfile.permissions)).all()
    return any((delivered or 0) > 0 or bool(permissions) for delivered, permissions in rows)


def _owned_surface_probed(db, env) -> bool:
    """Whether publishing to an owned surface has actually been shown to work (C-38).

    This opened on `BRAMBLELOOP_SITE_URL` or `PINTEREST_ACCESS_TOKEN` being set -- a gate
    reading configuration instead of demonstrated capability, the discipline `etsy.probe`
    and `model.probe` already hold. The condition is the most recent `owned_surface.probe`
    audit row recording `ok: true`; a variable alone opens nothing.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "owned_surface.probe")
                       .order_by(desc(AuditLog.id)).limit(1))
        return bool(row is not None and (row.detail or {}).get("ok") is True)


def _transactions_readable(db, env) -> bool:
    """The order source may read: the ingest's own gate (scope granted + probe recorded)."""
    try:
        from ..commerce import orders_ingest
    except ImportError:
        return False
    try:
        return bool(orders_ingest.gate(db)["open"])
    except Exception:  # noqa: BLE001 - an unreadable gate is a closed gate, said so
        return False


def _insights_recorded(db, env) -> bool:
    """At least one owner-recorded Marketplace Insights reading exists.

    Read lazily: the table is new, and a database or build without it has no readings.
    """
    try:
        from sqlalchemy import select

        from ..core.models import InsightsSnapshot
    except ImportError:
        return False
    try:
        with db.session() as s:
            return s.scalar(select(InsightsSnapshot.id).limit(1)) is not None
    except Exception:  # noqa: BLE001 - a missing table is "no readings", not a crash
        return False


ACCEPTANCE_RULING_KEY = "decision.api_vision_equivalence"


def _acceptance_ruled(db, env) -> bool:
    """The owner has ruled whether an API+vision traversal satisfies the browser/vision
    wording of #189/#221/#222/#320 -- a decision, recorded as a done OwnerAction."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    with db.session() as s:
        return s.scalar(select(OwnerAction.id).where(
            OwnerAction.requirement_key == ACCEPTANCE_RULING_KEY,
            OwnerAction.done.is_(True)).limit(1)) is not None


def _image_generation_usable(db, env) -> bool:
    """Whether an image has actually been generated, not whether a key is set.

    Four states and one string: a key that is set, a key for a provider with no price on
    file, an account with no credit, and a provider that refuses this company's brief on
    content grounds. The last is a live possibility for #198's brief -- an attractive adult
    model in editorial styling -- and it must surface as a refusal in the provider's own
    words rather than as a gallery that stayed empty for reasons nobody wrote down.
    """
    from ..gateway.images import usable

    return usable(db)


def _canonical_model_approved(db, env) -> bool:
    """Whether the owner has actually approved a canonical model, not whether one rendered.

    Nine requirements said it in prose and no gate said it in code. Their notes all read
    "needs an image generation capability *and owner identity selection*", and only the
    first half was checkable -- so the moment image generation started working, nine
    owner-gated requirements un-parked into the ready queue, which is the queue advertising
    work nobody can start. That is the single number this module exists to get right, and
    it had been wrong since the image gate opened.

    `canonical_pack` reads the one slot nothing can write without the owner: `select`
    refuses to promote a candidate without an approval timestamp, so this cannot be made
    true by rendering a better picture.
    """
    from ..visual import model_registry

    return model_registry.canonical_pack(db) is not None


def _production_window_proven(db, env) -> bool:
    """#195: a full unattended production window, read from the rows it left, has passed."""
    from . import autonomy

    try:
        return autonomy.launch_item(db)["status"] == autonomy.PROVEN
    except Exception:  # noqa: BLE001 - an uncomputable proof is not a proven one
        return False


def _offsite_archive_written(db, env) -> bool:
    """Whether a continuity archive has actually made the whole round trip.

    BRAMBLELOOP_ARCHIVE_URL being set says a person typed a bucket's address. #51 is about
    surviving the loss of this provider, and a bucket address that is wrong, whose
    credentials are wrong, or that nothing has ever successfully written to survives nothing.

    Stronger than a successful write, since 2026-09-20: the recorded condition is export,
    encrypt, upload, read back, decrypt, verify the digest and restore into a scratch
    database. An upload that succeeded and a restore proven separately are two facts about
    two different objects, and a backup nobody has restored is a hope.
    """
    from ..core.offsite import usable

    return usable(db)


def _second_market_observed(db, env) -> bool:
    """Whether any benchmark outside the United States has actually been observed.

    #268 was parked on `benchmark_observation` -- "read-only Etsy API credentials that can
    actually serve a request" -- and those have existed and been proven since 2026-09-19:
    the credential read 438 listings from the anchor shop. The gate was open and the
    requirement sat behind it, which is the mirror image of the failure this module usually
    catches: not work advertised that nobody can start, but work hidden that anybody could.

    What #268 actually needs is a second market to compare against. One shop's term
    frequencies are one market's language however many listings they came from, so the
    condition counts *distinct stated markets with observed listings*, not listings and not
    credentials. No capability opens it and no spend does; somebody chooses a shop.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    with db.session() as s:
        keys = {k for (k,) in s.execute(
            select(BenchmarkListing.benchmark_key).distinct())}

    # A discovered panel member (#219) carries its market on its row, read from the shop's
    # own Etsy location; `market_of` reads the spec first and that row second.
    markets = {m for key in keys if (m := benchmarks.market_of(db, key))}
    return len(markets) > 1


def _culture_feed_connected(db, env) -> bool:
    """Whether any cultural signal has actually been observed from a source.

    Counted rather than configured, like every other gate here. A culture radar with no feed
    and a culture radar with a feed and a quiet week produce the identical empty trend list,
    and the second reading is the one an absent owner takes from a dashboard -- which is why
    `culture.radar.sweep` refuses to return one. The gate opens on the first observation that
    names where it came from, because an observation with no source is the same unverifiable
    thing as no observation at all.
    """
    from sqlalchemy import select

    from ..core.models import CultureObservation

    with db.session() as s:
        rows = list(s.scalars(select(CultureObservation).limit(50)))
    return any((row.source or "").strip() for row in rows)


def _model_bearing_render_proven(db, env) -> bool:
    """Whether a frame with the canonical model in it has actually cleared every floor.

    Read from the `assets.model_photography` audit rows -- the record
    `publish.model_photography.sequence()` returns and the daily handler files -- and from
    nothing else. The condition is a filed record that is `made`, `carries_model`, is
    `usable_as_listing_asset`, and whose `floors` say `pass` for all six of
    `model_photography.FLOORS`: face identity, whole-person morphology, product truth,
    photographic realism (the photoreal floor), asset truth and styling. Any one of them
    missing is not a pass, so a record written by an earlier method with fewer floors
    cannot open this.

    `assets.owned_photography` rows are deliberately not read: those are product-first
    frames with nobody in them, and a product-first frame passing proves nothing about a
    model-bearing one. Neither is `visual.parity`'s verdict, because parity reads these
    same frames and would be a second opinion about one record.

    Why a gate at all: the render path exists, and every attempt so far has failed the
    product-truth floor on the provider's side (DECISION_LOG and `closure.EXTERNAL_GATES`).
    #72, #130 and #202 are the requirements that need a model-bearing frame to exist, and
    they are waiting on a provider rather than on any work this build can do next.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..publish import model_photography

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog.detail).where(
            AuditLog.action == model_photography.ACTION)
            .order_by(desc(AuditLog.id)).limit(200)))
    for detail in rows:
        detail = detail or {}
        floors = detail.get("floors") or {}
        if (detail.get("made") and detail.get("carries_model")
                and detail.get("usable_as_listing_asset") is True
                and all(floors.get(name) == "pass" for name in model_photography.FLOORS)):
            return True
    return False


def _ads_authorised(db, env) -> bool:
    """Advertising authority is a spend limit the owner set, not a sentence in a chat."""
    from sqlalchemy import select

    from ..core.models import SpendLimit

    with db.session() as s:
        limit = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        return bool(limit and limit.daily_cap_cad > 0 and not limit.paused)


class Gate:
    """One owner-granted thing, its checkable condition, and what waits on it."""

    def __init__(self, key: str, what: str, check, requirement_ids: tuple[int, ...],
                 how: str):
        self.key = key
        self.what = what
        self.check = check
        self.requirement_ids = requirement_ids
        self.how = how

    def open(self, db, env=None) -> bool:
        return bool(self.check(db, env))

    def to_dict(self, db=None, env=None) -> dict:
        waiting = sorted({rid for rid, key in gated_requirements().items()
                          if key == self.key})
        out = {"key": self.key, "what": self.what, "how_it_is_checked": self.how,
               "requirement_ids": waiting}
        if db is not None:
            out["open"] = self.open(db, env)
        return out


GATES: tuple[Gate, ...] = (
    Gate("benchmark_observation",
         "read-only Etsy API credentials that can actually serve a request",
         _etsy_usable,
         (),
         "a recorded etsy.probe succeeded -- a real sanctioned read, not a variable being set"),
    Gate("model_provider", "a model provider that can actually serve a request",
         _model_usable,
         (94, 277, 281),
         "a recorded model.probe succeeded -- a real call, not a variable being set"),
    # Satisfied 2026-09-19: BrambleloopStudio exists, empty, zero sales. Kept rather than
    # deleted, and carrying no requirements rather than the four it used to. Those four --
    # Marketplace Insights and seller-side offers -- were never blocked by the shop existing;
    # they are blocked by *automated access to it*, which is the developer credential. Parking
    # them here was imprecise, and unparking them on the shop's existence would have put work
    # in the ready queue that nobody can start, which is the one thing this module exists to
    # prevent. A gate that has opened is evidence and is worth keeping.
    Gate("etsy_shop", "a live Etsy shop, which only the account holder can open",
         # The identifier AND a sanctioned read that worked.
         #
         # This opened on `ETSY_SHOP_NAME` alone -- a gate reading configuration instead of
         # demonstrated capability, which is exactly what the `etsy_api` gate directly
         # below states the rule against: "a real sanctioned read, not a variable being
         # set". So it reported OPEN while `/api/launch` reported the shop blocked on the
         # owner with `ever_called: false`, and the executor would have offered
         # shop-dependent work as ready that nobody could do.
         #
         # A variable can be set by anyone at any time; a shop cannot. Requiring both means
         # the gate cannot open ahead of the thing it stands for.
         lambda db, env: bool(_env_gate("ETSY_SHOP_NAME")(db, env)
                              or _env_gate("ETSY_SHOP_ID")(db, env)) and _etsy_usable(db, env),
         (),
         "the shop's public identifier is set AND a recorded etsy.probe succeeded -- the "
         "identifier alone is a variable, which is not a shop"),
    Gate("etsy_api",
         "Etsy API credentials, which are what lets this system read the shop's own seller "
         "data rather than a person reading it on a screen",
         _etsy_usable,
         (),
         "a recorded etsy.probe succeeded -- a real sanctioned read, not a variable being set"),
    # `browser_vision` was split on 2026-09-20, and the split is the finding rather than a
    # tidy-up. One gate named two capabilities -- "rendered-page and image evidence" -- and
    # held twenty-eight requirements behind the more expensive of them. The image half never
    # needed a browser: the sanctioned Etsy endpoint `listing_images` has been returning
    # every gallery image's URL since the credential was proven by use on 2026-09-19, and the
    # model provider that can look at those URLs was credentialed the same day. What stood
    # between this company and image-level competitive evidence was that nobody had written
    # the call, which is not a capability anybody had to buy, and for a day it was
    # indistinguishable from one because both lived under one name.
    #
    # Both halves are now probes rather than variables, which the old gate was not. It read
    # BRAMBLELOOP_BROWSER_URL -- the only gate in this table openable by typing -- standing
    # in front of twenty-eight requirements.
    Gate("image_vision",
         "a model that can actually look at a picture, over the gallery URLs the sanctioned "
         "Etsy endpoint already returns",
         _vision_usable,
         # C-60/C-71: #208 #210 #211 were built without a vision model (API evidence, pod
         # maps, photography coverage) and left the gate; the registry's explicit parks
         # (#15 #86 #116 #304) are the live half.
         (61, 116, 304),
         "a recorded vision.probe judged a real observed image -- and a reply that describes "
         "no image is recorded as a failure, because a 200 carrying an apology is the shape "
         "a broken vision path takes"),
    Gate("rendered_pages",
         "a browser worker that can fetch an Etsy page as a buyer sees it: Marketplace "
         "Insights, search results and policy pages have no endpoint among the nine this "
         "application is authorised for",
         _rendered_pages_usable,
         # Narrowed 2026-09-27 (C-38). Marketplace Insights (1, 37, 236) waits on owner-recorded
         # readings (`insights_access`); the browser/vision wording of 189/221/222/320 waits
         # on the owner's ruling (`acceptance_ruling`); 277 and 281 wait on a model that can
         # serve a request (`model_provider`); 67, 71, 76, 86, 126, 218 and 315 were closed
         # or re-parked by their own audits and no longer wait here.
         # 2 and 15 left too (C-40): the API search index (findAllListingsActive, api_key
         # only) now supplies density and a labelled ranking proxy. Only the policy pages
         # still need a rendered page: #39 (policy freshness) and #35, whose class enablement
         # reads the same current policy pages (parked here in ca38f44; C-73).
         (35, 39),
         "a recorded browser.probe fetched a real rendered page -- a configured worker URL "
         "is a string, and Etsy answers 403 to a great many of them -- OR every "
         "etsy.com/legal policy source has a page reading by a named person, recorded "
         "through POST /api/policy/snapshot within 30 days, with no unreviewed material "
         "change (platform_policy.page_readings_status)"),
    Gate("transactions_r",
         "the owner has re-authorised the Etsy app with the transactions_r scope, so receipts "
         "can be read (C-64: the order source)",
         _transactions_readable,
         (11, 12),
         "the stored Etsy grant lists transactions_r AND a successful etsy.probe is recorded; "
         "the scope is added only by the owner in a browser (owner action "
         "reauthorise_transactions_r), and the ingest makes no network call while closed"),
    Gate("insights_access",
         "owner-recorded Marketplace Insights readings exist",
         _insights_recorded,
         (1, 37, 236),
         "at least one InsightsSnapshot row exists -- a reading somebody recorded from Shop "
         "Manager, counted, because there is no sanctioned endpoint that returns it"),
    Gate("acceptance_ruling",
         "the owner has ruled whether an API+vision traversal satisfies the browser/vision "
         "wording of #189/#221/#222/#320",
         _acceptance_ruled,
         (189, 221, 222, 320),
         f"an OwnerAction with requirement_key {ACCEPTANCE_RULING_KEY!r} is done -- a "
         "decision only the owner can make, recorded rather than assumed"),
    Gate("tester_roster",
         "one person who has agreed to test a Brambleloop pattern, which needs outreach to "
         "real people and therefore an exit from shadow mode",
         _tester_recruited,
         (9, 250),
         "at least one CreatorProfile has agreed -- delivered > 0 or a recorded permission. "
         "A prospect on file is not a tester"),
    Gate("image_generation",
         "an image-generation provider that conditions on reference images, because an "
         "identity lock is reference conditioning rather than a better prompt",
         _image_generation_usable,
         # Carries no owner-gated requirement of its own any more, and is kept for the
         # reason `etsy_shop` is kept: a gate that has opened is evidence. #199 moved to
         # `canonical_model` because its body ends "Owner selects the final identity" --
         # the tournament half ran and was presented, and the selection half is a decision.
         (),
         "a recorded image.probe generated a real image -- and a provider that refuses this "
         "brief on content grounds is a refusal in its own words, never an empty gallery"),
    # The half of the model gate that was written in prose and never in code. Every one of
    # these requirements' notes said "needs an image generation capability *and owner
    # identity selection*"; only the first half was checkable, so all nine un-parked into
    # the ready queue the moment images started working. The tournament and the aesthetic
    # direction stay on `image_generation` above, because rendering a field is exactly what
    # they needed and both have happened.
    Gate("canonical_model",
         "the owner's approval of a canonical model identity, which is a decision rather "
         "than a capability -- no amount of rendering produces it",
         _canonical_model_approved,
         # Opened 2026-09-22T03:52:53Z when the owner approved and froze the identity, and
         # now carries nothing, for the reason `etsy_shop` and `image_generation` are also
         # kept empty: a gate that has opened is evidence and worth keeping, and leaving
         # the nine requirements attached would keep claiming they wait on a decision that
         # has been made. Three of them are covered and six have remaining work that is
         # ours, which is a different thing from being gated (B-622).
         (),
         "a ModelIdentity row is canonical with an owner approval timestamp. `select` "
         "refuses to promote a candidate without one, so a better picture cannot make "
         "this true"),
    # W4-GATESB: the owner's approved set is thirteen (B-501/B-512, teardown.intake SET_SIZE,
    # CA$300 ceiling), not "roughly ten"; the exact list is gate_clearance.benchmark_purchase_list.
    Gate("benchmark_purchases",
         "the approved 13-pattern MJs benchmark set (CA$300 ceiling), bought by the owner and "
         "uploaded at /ops/teardown",
         _benchmarks_purchased,
         (165, 168, 317),
         "at least one BenchmarkProduct row exists -- counted, not asked about"),
    # Certification (#195): the off-device proof is computed and launch-blocking, and its
    # pass can only come from a production window running this build unattended. Deploying
    # Build 2 is the owner's decision, so this is an owner gate that opens on the evidence.
    Gate("production_window",
         "the owner's authorisation to run this build in production for a full unattended "
         "window, so the off-device proof can be read from real rows",
         _production_window_proven,
         (195,),
         "autonomy.launch_item reads PROVEN from the rows a full production window left"),
    Gate("offsite_storage",
         "an object-storage bucket and credential outside this provider, so a copy of the "
         "continuity archive survives losing the provider itself",
         _offsite_archive_written,
         (51,),
         "a continuity archive has actually been written offsite. A typed bucket address "
         "that is wrong, or whose credentials are, survives losing this provider exactly as "
         "well as no bucket at all"),
    # Added 2026-09-20. Several requirements were parked on browser_vision or live_listings
    # because those were the nearest existing keys, and neither is what they actually wait
    # for: a concept post and a free article wait on somewhere of this company's own to
    # publish them. A gate that is nearly right is worse than a new one, because it opens on
    # the wrong day and puts work in the ready queue that still cannot start.
    # W4-GATESB: the Etsy shop exists and is recognised (gate etsy_shop) as the paid
    # destination; it is not a surface the company can publish free content, pins, video or
    # email to. gate_clearance.owned_surfaces_inventory names each missing surface and why.
    Gate("owned_surfaces",
         "an owned publishing surface beyond the Etsy shop (which exists and is the paid "
         "destination): a site and/or Pinterest account, opened by the owner",
         _owned_surface_probed,
         (),
         "the latest owned_surface.probe audit row records ok: true -- a real publish-path "
         "check, not a site URL or token variable being set"),
    Gate("live_listings",
         "a listing that exists on the marketplace: company work first (a product clears the "
         "final publication gate), then the owner's per-listing publication grant",
         _has_live_listing,
         (),
         "at least one Listing row carries an Etsy listing id -- counted, not read from the "
         "phase flag, because a phase is a statement of intent and a listing id is a listing"),
    Gate("customers",
         "real orders, which only a buyer can create -- DATA/EXTERNAL-gated, never an owner "
         "action (closure.DATA_GATES; listed under waiting_on_data, never as an owner card)",
         _has_customers,
         (),
         "at least one LedgerEntry has gross_cad > 0 and an evidence_ref -- revenue with "
         "its order, not an expense and not a phase flag saying the company is selling"),
    # Added 2026-09-20. #133, #140 and #147 sat in the ready queue while the thing they wait
    # for -- a connected cultural signal source -- does not exist, and each of their registry
    # notes already said so in prose. Prose in a note does not park anything: the queue went
    # on reporting three requirements as ready work somebody could start, which is the one
    # number the executor exists to keep honest. No existing gate is right for it either;
    # `benchmark_observation` is about competitor listings and a search-interest feed is not
    # that, and a gate that is nearly right opens on the wrong day.
    # Added 2026-09-20 alongside culture_feed, and for the same reason: #64's only remaining
    # work is the trigger, and the trigger is a photograph of an object nobody has made.
    # Reworded 2026-09-20. The old text read "needs somebody to crochet a Brambleloop sample
    # and photograph it", which put the owner's own hands in a gate description and so made
    # the owner action list ask for something no owner action list should ask for. The
    # condition is unchanged and stays unchanged: a completed physical test. Who completes it
    # -- a paid tester, a customer, an independent maker under the revised risk-based
    # protocol the owner has said is coming in the Final Master -- is a question about the
    # protocol, and a gate that names one answer forecloses the others.
    Gate("physical_proof",
         "a completed physical test of a Brambleloop pattern by whoever the testing protocol "
         "says performs one",
         _physical_proof_available,
         (64,),
         "at least one PhysicalTest row has a completion date -- the intake being built is "
         "not the same as a finished object existing, and nothing here says whose hands "
         "finished it"),
    # #268 moved here from `benchmark_observation` on 2026-09-20. That gate names the Etsy
    # credential, the credential has been proven by use since 2026-09-19, and the gate was
    # therefore open -- so the requirement was parked on a condition that was already true,
    # which is a park that never expires by itself. What it waits on is a second market,
    # and nothing in this system could have told the difference while the two were conflated.
    # Carries nothing since 2026-09-20, and is kept for the same reason `etsy_shop` is: the
    # condition is worth having in code. #268 moved to `data_gated` on the owner's decision
    # -- what it waits on is a second market's listings, which is evidence this company does
    # not hold rather than work it can start, and `parked_on` states what remaining work
    # needs. A data-gated requirement has left the queue rather than waiting in it, so this
    # gate's job is to say what would bring it back.
    Gate("second_market_benchmark",
         "a benchmark shop outside the United States, which is a choice of shop rather than "
         "a credential or a capability",
         _second_market_observed,
         (),
         "observed listings exist for two or more distinct stated markets -- one shop's term "
         "frequencies are one market's language however many listings they came from"),
    Gate("culture_feed",
         "a connected source of cultural signal -- search interest, social or trend data -- "
         "which this company has never had",
         _culture_feed_connected,
         (140, 147),
         "at least one CultureObservation row names the source it came from. An observation "
         "with no source is the same unverifiable thing as no observation"),
    # Added 2026-09-26. #72, #130 and #202 each said in prose "waits on the model-bearing
    # render path", and nothing parked them, so they sat in the ready queue as work somebody
    # could start. The path is built; what it has never produced is a frame that clears all
    # six floors, and the floor it fails is the provider's rendering of a certified
    # structure. `closure.EXTERNAL_GATES` names this key and says why it is external.
    Gate("model_bearing_render",
         "a model-bearing listing frame that clears every floor -- identity, morphology, "
         "product truth, photographic realism, asset truth and styling -- which no image "
         "provider has yet rendered",
         _model_bearing_render_proven,
         (),
         "an assets.model_photography audit row that is made, carries the model, is usable "
         "as a listing asset and reads `pass` on all six model_photography.FLOORS. "
         "`unverifiable` is not a pass, and a product-first frame does not count"),
    # W4-GATESB (W4-OWNER finding): #242-245 are computed daily by ads.adjust whatever the
    # authority and wait on order data, so they park on `customers` (registry parked_on).
    # Only the paid scaling rows wait on a budget.
    Gate("ad_authority",
         "an approved advertising budget -- recommended only once a listing is ready to sell "
         "(gate_clearance.ad_readiness)",
         _ads_authorised,
         (294, 295),
         "a SpendLimit row for 'ads' exists with a positive, unpaused daily cap"),
)

GATE_BY_KEY: dict[str, Gate] = {g.key: g for g in GATES}
_GATE_FOR_REQUIREMENT: dict[int, str] = {
    rid: g.key for g in GATES for rid in g.requirement_ids}


def _registry_gates() -> dict[int, str]:
    """Gates the registry declares on itself, via each requirement's `parked_on`.

    The audit is where somebody writes "remaining: waits on image generation", so it is also
    where that sentence should be machine-readable. Keeping the claim and the parking in one
    edit is the only arrangement under which they cannot disagree.
    """
    return {r.id: r.parked_on for r in reg.load() if r.parked_on}


def gate_for(requirement_id: int) -> str | None:
    """Which owner gate this requirement waits on, if any.

    The registry wins over the table above. The table is the older half and is keyed by whole
    requirements; `parked_on` is written by whoever last audited the requirement and knows
    what is actually left of it.
    """
    declared = _registry_gates().get(requirement_id)
    if declared:
        return declared
    return _GATE_FOR_REQUIREMENT.get(requirement_id)


def gated_requirements() -> dict[int, str]:
    """Every requirement parked on a gate, from both halves. Registry wins on a conflict."""
    return {**_GATE_FOR_REQUIREMENT, **_registry_gates()}


def gate_states(db, env=None) -> dict:
    """Every gate and whether it is open, checked rather than remembered."""
    return {g.key: g.to_dict(db, env) for g in GATES}


def _validate_graph() -> None:
    known = {r.id for r in reg.load()}
    for node, edges in DEPENDENCIES.items():
        if node not in known:
            raise ExecutorRefused(f"dependency declared for unknown requirement {node}")
        for edge in edges:
            if edge not in known:
                raise ExecutorRefused(f"requirement {node} depends on unknown {edge}")
    # Depth-first cycle check. A cycle makes every task in it permanently blocked, and the
    # queue would report "nothing ready" while looking entirely healthy.
    colour: dict[int, int] = {}

    def visit(node: int, path: tuple[int, ...]) -> None:
        state = colour.get(node, 0)
        if state == 1:
            raise ExecutorRefused(
                f"dependency cycle: {' -> '.join(str(p) for p in path + (node,))}. Every "
                f"task in a cycle is permanently blocked, and the queue would report "
                f"nothing ready while looking healthy")
        if state == 2:
            return
        colour[node] = 1
        for edge in DEPENDENCIES.get(node, ()):
            visit(edge, path + (node,))
        colour[node] = 2

    for node in DEPENDENCIES:
        visit(node, ())


def _validate_gates() -> None:
    """Every owner-gated requirement must be parked on a gate somebody can test.

    Without this the registry's `owner_gated` status and the executor's parking drift apart
    silently, and the drift always goes the same way: an owner-gated requirement with no gate
    falls through into the ready list, where it is work nobody can actually do. The queue
    then reports more ready work than exists, which is the one number this whole module is
    for.
    """
    ungated = [r.id for r in reg.by_status(reg.OWNER_GATED)
               if gate_for(r.id) is None]
    if ungated:
        raise ExecutorRefused(
            f"owner-gated requirements with no gate: {ungated}. Each needs a gate with a "
            f"condition the code can test, or it falls into the ready list as work nobody "
            f"can do and the queue overstates itself")
    known = {r.id for r in reg.load()}
    stray = [rid for rid in gated_requirements() if rid not in known]
    if stray:
        raise ExecutorRefused(f"gates declared for unknown requirements: {stray}")
    # A registry that names a gate this module does not define would park the requirement on
    # a key nothing ever checks, so it could never un-park. That is worse than not parking
    # it: the work would leave the queue and never come back, and the loop would look
    # finished by losing a requirement rather than by finishing it.
    unknown = sorted({(rid, key) for rid, key in _registry_gates().items()
                      if key not in GATE_BY_KEY})
    if unknown:
        raise ExecutorRefused(
            f"registry parks requirements on gates that do not exist: {unknown}. A gate key "
            f"nothing checks never opens, so the requirement would leave the queue "
            f"permanently rather than wait in it")


def priority_of(requirement) -> float:
    """Lower is sooner. Section first, then how nearly finished it already is."""
    weight = SECTION_WEIGHT.get(requirement.section, DEFAULT_SECTION_WEIGHT)
    return weight + STATUS_BONUS.get(requirement.status, 0.0) + requirement.id / 1000.0


# ---------------------------------------------------------------------------
# Sync


def sync(db, *, env: dict[str, str] | None = None) -> dict:
    """Reconcile the task table with the registry and the current capabilities.

    Idempotent and safe to run on every tick. Registry status is the source of truth for
    *what* a requirement is; this table owns *where it stands*, and a requirement whose
    registry status moved to covered is completed here rather than silently diverging.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    _validate_graph()
    _validate_gates()
    now = datetime.now(timezone.utc)

    open_gates: dict[str, bool] = {g.key: g.open(db, env) for g in GATES}

    created, updated, unparked, completed, retired = 0, 0, [], [], []
    with db.session() as s:
        existing = {t.requirement_id: t for t in s.scalars(select(BuildTask))}
        done_ids = {r.id for r in reg.load() if r.status == reg.COVERED}

        for requirement in reg.load():
            if requirement.status not in SCHEDULABLE and requirement.status != reg.OWNER_GATED:
                # Covered and data-gated requirements are not schedulable work. Covered ones
                # still get a row so completion is visible; data-gated ones do not, because
                # no credential makes a customer exist and a task that can never be ready is
                # a permanent blocker wearing a queue entry.
                if requirement.status != reg.COVERED:
                    stale = existing.get(requirement.id)
                    if stale is not None:
                        # A requirement re-audited as data-gated must leave the queue, not
                        # sit in it forever because the row already existed. The first
                        # version of this skipped straight past an existing task, so five
                        # requirements reclassified as gated kept reporting themselves ready
                        # -- the queue advertising work nobody can start, which is the exact
                        # failure this module was written to prevent.
                        s.delete(stale)
                        retired.append(requirement.id)
                    continue

            task = existing.get(requirement.id)
            first_sight = task is None
            if first_sight:
                task = BuildTask(requirement_id=requirement.id)
                s.add(task)
                created += 1
            else:
                updated += 1

            task.title = requirement.title
            task.section = requirement.section
            task.status = requirement.status
            task.note = requirement.note
            task.depends_on = list(DEPENDENCIES.get(requirement.id, ()))
            task.priority = priority_of(requirement)
            task.updated_at = now

            if requirement.status == reg.COVERED:
                if task.state != DONE:
                    task.state = DONE
                    task.completed_at = task.completed_at or now
                    # A completion is a transition this system *observed*, not a status it
                    # found on first sight. Counting the already-covered backlog as
                    # completions would make the first sync look like 140 requirements
                    # finishing at once, and the watchdog would report a moving loop from a
                    # table that had just been created.
                    if not first_sight:
                        completed.append(requirement.id)
                continue

            gate_key = gate_for(requirement.id)
            if gate_key and not open_gates.get(gate_key, False):
                # Re-park when the *gate* changed, not only when the state did. The test was
                # `task.state != PARKED`, so a task already parked kept whatever key it was
                # parked on the day it was parked -- and when `browser_vision` was split into
                # `image_vision` and `rendered_pages` on 2026-09-20, twenty-two live rows in
                # production went on naming a gate nothing checks. They would still have
                # un-parked correctly, because the un-park test reads `gate_for` rather than
                # the stored label, so this was a reporting fault rather than a stuck queue:
                # `parked_by_capability` groups by the stored key, so the console showed a
                # capability that no longer exists and none of the one that does. A label
                # that is only ever written once is a label that goes stale silently.
                if task.state != PARKED or task.parked_on != gate_key:
                    gate = GATE_BY_KEY[gate_key]
                    was = task.parked_on
                    task.state = PARKED
                    task.parked_on = gate_key
                    task.parked_at = task.parked_at if was == gate_key else now
                    task.parked_reason = (
                        f"waiting on {gate.what}. Checked by: {gate.how}. Parked rather "
                        f"than blocking -- every other requirement continues, and this "
                        f"un-parks automatically when the condition becomes true, with "
                        f"nobody having to remember"
                        + (f" (moved from {was})" if was and was != gate_key else ""))
                continue

            if task.state == PARKED:
                # The gate opened. Nothing had to remember.
                task.state = READY
                task.parked_on = None
                task.parked_reason = ""
                task.parked_at = None
                unparked.append(requirement.id)

            unmet = [d for d in task.depends_on if d not in done_ids]
            if unmet:
                task.state = BLOCKED
                continue

            if task.state in (BLOCKED,) or task.state not in (IN_PROGRESS, DONE):
                task.state = READY

    result = {"created": created, "updated": updated, "unparked": unparked,
              "completed": completed, "retired": retired, "gates_open": open_gates}

    # A completion the watchdog cannot see is a completion that did not happen, as far as the
    # only thing watching is concerned. Most completions arrive this way -- a session finishes
    # the work and moves the registry status -- and recording them only as a "sync" event made
    # the watchdog report a stalled loop while six requirements had just closed. A false alarm
    # in the channel that exists to catch a real one is worse than no channel.
    for requirement_id in completed:
        record(db, kind="complete", requirement_id=requirement_id, actor="registry_sync",
               summary=f"completed {requirement_id} by registry status",
               detail={"source": "registry_sync"})
    if unparked:
        record(db, kind="unpark", summary=(
            f"{len(unparked)} requirements un-parked because their gate opened"),
            detail={"requirement_ids": unparked, "gates_open": open_gates})
    return result


def record(db, *, kind: str, summary: str, requirement_id: int | None = None,
           actor: str = "executor", detail: dict | None = None) -> int:
    from ..core.models import BuildEvent

    with db.session() as s:
        row = BuildEvent(kind=kind, requirement_id=requirement_id, actor=actor,
                         summary=summary, detail=detail or {})
        s.add(row)
        s.flush()
        return row.id


# ---------------------------------------------------------------------------
# The queue


def reconciliation(db) -> dict:
    """The invariant tying the registry to the queue, stated as what is actually true.

    `executable` (partial or missing) means this build still owes the requirement.
    `ready` means nothing is stopping it right now. Those were the same number while every
    gated requirement was also `owner_gated` -- and they stopped being the same the moment a
    requirement was half-built with its remainder behind a credential, which is the ordinary
    case rather than the exception. Asserting equality would have forced a choice between
    two lies: calling a half-built requirement owner-gated, or calling gated work ready.

    So: every executable requirement is either ready or parked, nothing owner-gated is ever
    ready, and the parked ones name their gate.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        tasks = [(t.requirement_id, t.status, t.state, t.parked_on)
                 for t in s.scalars(select(BuildTask))]

    executable = {r.id for r in reg.executable()}
    ready = {rid for rid, _, state, _ in tasks if state == READY}
    parked = {rid: gate for rid, _, state, gate in tasks if state == PARKED}
    blocked = {rid for rid, _, state, _ in tasks if state == BLOCKED}

    owner_gated_ready = sorted(
        rid for rid in ready
        if reg.get(rid).status == reg.OWNER_GATED)
    unaccounted = sorted(executable - ready - set(parked) - blocked)

    return {
        "executable": len(executable),
        "ready": len(ready),
        "executable_parked": sorted(executable & set(parked)),
        "blocked": len(blocked),
        "balances": not unaccounted and not owner_gated_ready,
        "unaccounted": unaccounted,
        "owner_gated_but_ready": owner_gated_ready,
        "note": ("Executable means this build owes it; ready means nothing is stopping it "
                 "now. A half-built requirement whose remainder waits on a credential is "
                 "both owed and parked, which is why these are two numbers rather than one."),
    }


def queue(db, *, limit: int = 25) -> dict:
    """What is ready, what is parked, what is blocked — and why, for each.

    The three are reported together on purpose. A queue that showed only ready work would
    look identical whether twelve requirements were parked on a credential or none were.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        tasks = list(s.scalars(select(BuildTask)))
        rows = [{"requirement_id": t.requirement_id, "title": t.title,
                 "section": t.section, "status": t.status, "state": t.state,
                 "priority": t.priority, "depends_on": list(t.depends_on or []),
                 "parked_on": t.parked_on, "parked_reason": t.parked_reason,
                 "claimed_by": t.claimed_by}
                for t in tasks]

    ready = sorted([r for r in rows if r["state"] == READY], key=lambda r: r["priority"])
    parked = [r for r in rows if r["state"] == PARKED]
    blocked = [r for r in rows if r["state"] == BLOCKED]
    in_progress = [r for r in rows if r["state"] == IN_PROGRESS]

    by_capability: dict[str, list[int]] = {}
    for r in parked:
        by_capability.setdefault(r["parked_on"] or "unknown", []).append(r["requirement_id"])
    # F-130: parked work split by what kind of waiting it is -- owner, data or external -- so
    # "parked" never hides which of the three is holding it. A gate nobody classified is
    # reported as such rather than filed wherever flatters the count.
    from . import closure

    by_kind: dict[str, list[int]] = {"owner_gated": [], "data_gated": [],
                                     "external_blocked": [], "unclassified": []}
    kind_key = {closure.OWNER_GATED: "owner_gated", closure.DATA_GATED: "data_gated",
                closure.EXTERNAL_BLOCKED: "external_blocked"}
    for r in parked:
        try:
            k = kind_key.get(closure.kind_of(r["parked_on"] or ""), "unclassified")
        except closure.ClosureRefused:
            k = "unclassified"
        by_kind[k].append(r["requirement_id"])

    return {
        "ready": ready[:limit],
        "ready_total": len(ready),
        "parked_total": len(parked),
        "parked_by_capability": by_capability,
        "parked_by_kind": {k: sorted(v) for k, v in by_kind.items()},
        "executable_remaining": len(ready) + len(blocked) + len(in_progress),
        "running_total": len(in_progress),
        "dependency_waiting_total": len(blocked),
        "blocked_total": len(blocked),
        "blocked": blocked[:limit],
        "in_progress": in_progress,
        "done_total": sum(1 for r in rows if r["state"] == DONE),
        "next": ready[0] if ready else None,
        "note": ("Ready, parked and blocked are reported together: a queue showing only "
                 "ready work looks identical whether twelve requirements are parked on a "
                 "credential or none are."),
    }


def next_ready(db) -> dict | None:
    """The highest-value requirement nothing is stopping."""
    return queue(db, limit=1)["next"]


def claim(db, requirement_id: int, *, worker: str) -> dict:
    """Take a requirement, with a lease so a dead session does not hold it forever."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=CLAIM_LEASE_MINUTES)
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        if task.state == DONE:
            raise ExecutorRefused(f"requirement {requirement_id} is already done")
        if task.state == PARKED:
            raise ExecutorRefused(
                f"requirement {requirement_id} is parked on {task.parked_on!r}; claiming it "
                f"would be starting work that cannot finish")
        if task.state == BLOCKED:
            raise ExecutorRefused(
                f"requirement {requirement_id} depends on {task.depends_on}, which are not "
                f"done. Building it first produces something that has to be redone")
        if task.state == IN_PROGRESS and task.claimed_by != worker:
            claimed_at = task.claimed_at
            if claimed_at is not None and claimed_at.tzinfo is None:
                claimed_at = claimed_at.replace(tzinfo=timezone.utc)
            if claimed_at is not None and claimed_at > cutoff:
                raise ExecutorRefused(
                    f"requirement {requirement_id} is claimed by {task.claimed_by!r} and the "
                    f"lease has not expired")
        task.state = IN_PROGRESS
        task.claimed_by = worker
        task.claimed_at = now
        task.updated_at = now
        out = {"requirement_id": requirement_id, "title": task.title,
               "section": task.section, "worker": worker,
               "lease_expires_in_minutes": CLAIM_LEASE_MINUTES}

    record(db, kind="claim", requirement_id=requirement_id, actor=worker,
           summary=f"claimed {requirement_id}: {out['title']}")
    return out


def _not_held_by(task, worker: str, what: str) -> str | None:
    """Why `worker` may not complete/release this task, or None when it may (C-16).

    Only the claimant of an IN_PROGRESS task finishes or releases it. A PARKED, BLOCKED or
    READY task was never claimed, so completing it skips the claim (and, for PARKED, the gate
    the task is waiting on); a task another worker holds is that worker's to finish.
    """
    if task.state != IN_PROGRESS:
        return (f"requirement {task.requirement_id} is {task.state!r}, not in progress; "
                f"only a claimed task can be {what}d -- claim it first"
                + (f" (it is parked on {task.parked_on!r})" if task.state == PARKED else ""))
    if task.claimed_by != worker:
        return (f"requirement {task.requirement_id} is claimed by {task.claimed_by!r}, not "
                f"{worker!r}; its outcome belongs to the claimant")
    return None


def _refuse(db, requirement_id: int, worker: str, what: str, why: str):
    """Audit a refused completion or release, then raise."""
    record(db, kind="refused", requirement_id=requirement_id, actor=worker,
           summary=f"refused {what} of {requirement_id} by {worker}: {why}"[:500],
           detail={"attempted": what, "why": why})
    raise ExecutorRefused(why)


def complete(db, requirement_id: int, *, worker: str, evidence: dict) -> dict:
    """Finish a requirement, with evidence. A completion with no evidence is a checkbox."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    if not evidence or not any(str(v).strip() for v in evidence.values()):
        raise ExecutorRefused(
            "a completion records what proved it -- a suite, a test count, a commit. Without "
            "that the build loop's own progress is the one number in this company nobody "
            "has to evidence")

    now = datetime.now(timezone.utc)
    refusal = None
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        refusal = _not_held_by(task, worker, "complete")
        if refusal is None:
            task.state = DONE
            task.completed_at = now
            task.updated_at = now
            task.evidence = dict(evidence)
            task.claimed_by = None
        title = task.title

    if refusal is not None:
        _refuse(db, requirement_id, worker, "complete", refusal)
    record(db, kind="complete", requirement_id=requirement_id, actor=worker,
           summary=f"completed {requirement_id}: {title}", detail=dict(evidence))
    return {"requirement_id": requirement_id, "state": DONE, "evidence": dict(evidence)}


def release(db, requirement_id: int, *, worker: str, why: str) -> dict:
    """Put a claimed requirement back, without pretending it was finished."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        refusal = _not_held_by(task, worker, "release")
        if refusal is None:
            task.state = READY
            task.claimed_by = None
            task.claimed_at = None
            task.updated_at = datetime.now(timezone.utc)

    if refusal is not None:
        _refuse(db, requirement_id, worker, "release", refusal)
    record(db, kind="release", requirement_id=requirement_id, actor=worker,
           summary=f"released {requirement_id}: {why}")
    return {"requirement_id": requirement_id, "state": READY, "why": why}


# ---------------------------------------------------------------------------
# The watchdog


AWAITING_BUILD_SESSION = "awaiting_build_session"
STALLED = "stalled"


def watchdog(db, *, now: datetime | None = None,
             idle_alarm_hours: int = IDLE_ALARM_HOURS) -> dict:
    """Is the build actually moving, and if not, is that legitimate?

    Three idle states, and they need three different responses.

    **Everything parked** is the system working correctly and waiting on a person. Raising
    an incident for it would train everybody to ignore the channel.

    **Ready work, and nobody has claimed any** is `awaiting_build_session`. The deployed
    worker never writes code: `build.tick` syncs, queues and watches, and a requirement
    completes when a session does the work and moves the registry. So "nothing completed in
    six hours" with no claim in the window measures how often a session has been opened, not
    whether the loop is broken -- and an incident for it is an alarm about the calendar. It
    is reported with the top ready requirement named, so the next session knows where to
    start, and it does not alarm.

    **Ready work that somebody claimed and did not finish** is `stalled`, and that is the
    incident: a claim is a promise to make progress, and a claim with no completion in the
    window is a worker that took the task and stopped.
    """
    from sqlalchemy import func, select

    from ..core.models import BuildEvent, BuildTask

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=idle_alarm_hours)

    def _aware(value):
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        recent = int(s.scalar(select(func.count(BuildEvent.id)).where(
            BuildEvent.kind == "complete", BuildEvent.at >= cutoff)) or 0)
        last = _aware(s.scalar(select(func.max(BuildEvent.at)).where(
            BuildEvent.kind == "complete")))
        claims = int(s.scalar(select(func.count(BuildEvent.id)).where(
            BuildEvent.kind == "claim", BuildEvent.at >= cutoff)) or 0)
        held = [(t.requirement_id, t.claimed_by) for t in s.scalars(
            select(BuildTask).where(BuildTask.state == IN_PROGRESS))]

    snapshot = queue(db)

    if recent:
        return {"moving": True, "completions_in_window": recent,
                "window_hours": idle_alarm_hours,
                "last_completion": last.isoformat() if last else None,
                "ready_total": snapshot["ready_total"],
                "verdict": "moving", "alarm": False}

    if snapshot["ready_total"] == 0 and not held:
        return {
            "moving": False,
            "completions_in_window": 0,
            "window_hours": idle_alarm_hours,
            "last_completion": last.isoformat() if last else None,
            "ready_total": 0,
            "parked_total": snapshot["parked_total"],
            "parked_by_capability": snapshot["parked_by_capability"],
            "verdict": "waiting_on_owner" if snapshot["parked_total"] else "finished",
            "alarm": False,
            "note": ("Nothing is ready and nothing has completed, which is the system "
                     "working correctly rather than a stall. Raising an incident here would "
                     "train everybody to ignore the channel."),
        }

    # A stall is a task somebody *holds* without finishing it. Claim events in the window
    # without anything held mean the claim was honestly released (or completed and then a
    # new one released), which is not a worker that took the task and stopped (C-16).
    if not held:
        top = snapshot["next"] or {}
        return {
            "moving": False,
            "completions_in_window": 0,
            "claims_in_window": claims,
            "window_hours": idle_alarm_hours,
            "last_completion": last.isoformat() if last else None,
            "ready_total": snapshot["ready_total"],
            "next": snapshot["next"],
            "verdict": AWAITING_BUILD_SESSION,
            "alarm": False,
            "note": (f"{snapshot['ready_total']} requirements are ready and none is held "
                     f"({claims} claim(s) in {idle_alarm_hours} hours, all released or "
                     f"finished). The deployed worker does not "
                     f"write code, so this is waiting for a build session rather than a "
                     f"broken loop. Start with #{top.get('requirement_id')}: "
                     f"{top.get('title') or ''}".rstrip(": ")),
        }

    return {
        "moving": False,
        "completions_in_window": 0,
        "claims_in_window": claims,
        "in_progress": [{"requirement_id": rid, "claimed_by": who} for rid, who in held],
        "window_hours": idle_alarm_hours,
        "last_completion": last.isoformat() if last else None,
        "ready_total": snapshot["ready_total"],
        "next": snapshot["next"],
        "verdict": STALLED,
        "alarm": True,
        "note": (f"work was claimed ({claims} claim(s) in the window, {len(held)} task(s) "
                 f"in progress) and nothing has been completed in {idle_alarm_hours} hours. "
                 f"A claim is a promise to make progress; a claim with no completion is a "
                 f"worker that took the task and stopped."),
    }


def _final_master_brief() -> dict:
    from . import final_master

    fm = final_master.summary()
    return {k: fm.get(k) for k in ("status", "launch_ready", "launch_critical",
                                   "gated_by_kind", "post_launch_excluded",
                                   "integrity_violations", "reason", "rule")}


def report(db, *, env: dict[str, str] | None = None) -> dict:
    """Everything an absent owner needs to see about the build loop itself."""
    from ..launch import access

    snapshot = queue(db)
    return {
        "queue": snapshot,
        # `reconciliation` was written, tested and then called by nothing -- the build's own
        # most familiar failure, committed by the module whose docstring names it. It states
        # the invariant that nothing owner-gated is ever ready, and while nobody read it,
        # nine owner-gated requirements sat in the ready list in production for a day.
        "reconciliation": reconciliation(db),
        "watchdog": watchdog(db),
        "gates": gate_states(db, env),
        "capabilities": access.statuses(env),
        "dependencies": {str(k): list(v) for k, v in DEPENDENCIES.items()},
        "claim_lease_minutes": CLAIM_LEASE_MINUTES,
        # F-129 / F-136: the Final Master registry's live re-audit beside Build 2's.
        "final_master": _final_master_brief(),
        "note": ("The graph, the queue and the parking state live in Postgres, so losing a "
                 "session loses a worker rather than the build. An owner action parks the "
                 "requirements that need it and never holds the queue."),
    }


# ---------------------------------------------------------------------------
# The owner approval inbox (#196)
#
# The requirement is that an owner action collapses into a card, non-urgent ones batch, and
# *everything else continues*. The last clause is the one that matters and it is the one a
# card UI would quietly drop: an inbox is only asynchronous if the queue behind it does not
# wait, and that property lives in `sync()` rather than here. What lives here is making the
# ask small enough to answer from a phone.

# How the cards sort. Free and quick first, because an owner reading on a phone answers the
# top one, and the top one should be the one that unblocks most for least.
def _urgency(card: dict) -> tuple:
    # W3-WIRE4: an UNKNOWN cost (None) is never ranked as free; it sorts after every stated
    # cost, because nobody can say yet what answering it would spend.
    cost = card["max_cost_cad"]
    minutes = card.get("minutes")
    return (cost is None, cost if cost is not None else 0.0, minutes is None, minutes or 0,
            -card["unblocks_count"])


# F-179 / F-663: the legacy OwnerAction table and the gate cards are ONE queue.
#
# Production rendered two owner surfaces -- "Owner action required" from OwnerAction rows and
# "Waiting on the owner" from these gate cards -- and nothing reconciled them, so the owner
# was asked twice for one decision (actions 19/20) and, worse, asked for things already done.
# An OwnerAction row is bound to the gate it would open through its `requirement_key`: either
# the key *is* a gate key, or it is one of the aliases below (the readiness and access
# assessments name the same decision differently). A bound row is merged into its gate's card
# rather than listed beside it; a row whose gate is already open is not presented at all and
# is reported under `satisfied_but_open`, which `/api/verify` fails on (F-182). A row bound to
# nothing is a genuine standalone decision (a budget, a retirement review) and is presented as
# its own card, keyed on its requirement.
OWNER_ACTION_GATE_ALIASES: dict[str, str] = {
    "model_credits": "model_provider",
    "reauthorise_transactions_r": "transactions_r",
    "canonical_model_selection": "canonical_model",
    "canonical_model_approval": "canonical_model",
    ACCEPTANCE_RULING_KEY: "acceptance_ruling",
}


def _table_cost(gate_key: str):
    """W4-OWNER: the decision table's ceiling for a gate, or None (UNKNOWN)."""
    from ..ops import owner_queue

    d = owner_queue.DECISION_BY_GATE.get(gate_key)
    return d["max_cost_cad"] if d else None


def _table_minutes(gate_key: str):
    from ..ops import owner_queue

    d = owner_queue.DECISION_BY_GATE.get(gate_key)
    return d["minutes"] if d else None


def gate_for_owner_action(requirement_key: str | None) -> str | None:
    """The executor gate an OwnerAction row would open, or None for a standalone decision."""
    key = (requirement_key or "").strip()
    if key in GATE_BY_KEY:
        return key
    return OWNER_ACTION_GATE_ALIASES.get(key)


def approval_inbox(db, *, env: dict[str, str] | None = None) -> dict:
    """The one owner queue: every genuine owner decision as a card, ranked (#196, F-663).

    Each card carries the seven things #196 asks for -- what, why, capability, maximum spend,
    risk, rollback, consequence of waiting -- plus the requirements it would un-park, the
    evidence that will show it done (`evidence`) and the exact step (`steps`).

    What is *not* a card, and why (F-181, F-196):
    - a gate that is open (satisfied work is never asked for again);
    - a gate whose kind is external (`closure.EXTERNAL_GATES`): no owner action opens it, so
      it is listed under `external_capability_unavailable`, never as an owner request -- the
      owner must not be asked to buy a browser Etsy will answer 403;
    - a data gate (`customers`): only a buyer opens it, listed under `waiting_on_data`;
    - an owner gate that un-parks nothing: listed under `suppressed_unblocks_nothing`,
      because an action that no longer unblocks anything is not active.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..launch import access
    from ..ops import owner_queue
    from . import closure

    requests = {r.key: r for r in access.pending_requests(env)}
    parked_by_gate: dict[str, list[int]] = {}
    for rid, key in gated_requirements().items():
        parked_by_gate.setdefault(key, []).append(rid)

    with db.session() as s:
        rows = [{"id": a.id, "requirement_key": a.requirement_key or "", "action": a.action,
                 # W3-WIRE4: None when the row's cost basis is UNKNOWN (never CA$0.00).
                 "reason": a.reason or "", "max_cost_cad": a.max_cost_known,
                 "minutes": int(a.minutes or 0),
                 "consequence_of_delay": a.consequence_of_delay or "",
                 "blocks": a.blocks or "", "at": a.at.isoformat() if a.at else None,
                 # F-180 / F-870 (K7): lifecycle state and why software cannot do it.
                 "state": owner_queue.effective_state(a),
                 "why_software_cannot": getattr(a, "why_software_cannot", "") or ""}
                for a in s.scalars(select(OwnerAction).where(
                    OwnerAction.done == False))]  # noqa: E712
    # F-180: a parked action is not active. It is listed, never presented as a card.
    parked_actions = [r for r in rows if r["state"] == owner_queue.PARKED]
    rows = [r for r in rows if r["state"] != owner_queue.PARKED]
    rows_by_gate: dict[str, list[dict]] = {}
    standalone: list[dict] = []
    for row in rows:
        g = gate_for_owner_action(row["requirement_key"])
        if g is None:
            standalone.append(row)
        else:
            rows_by_gate.setdefault(g, []).append(row)

    cards: list[dict] = []
    external: list[dict] = []
    data_wait: list[dict] = []
    suppressed: list[dict] = []
    satisfied_but_open: list[dict] = []
    company_opened: list[dict] = []
    not_yet_askable: list[dict] = []
    gate_open: dict[str, bool] = {}
    for gate in GATES:
        is_open = gate.open(db, env)
        gate_open[gate.key] = is_open
        bound = rows_by_gate.get(gate.key, [])
        if is_open:
            satisfied_but_open += [{"owner_action_id": r["id"], "gate": gate.key,
                                    "requirement_key": r["requirement_key"],
                                    "action": r["action"]} for r in bound]
            continue
        parked = sorted(parked_by_gate.get(gate.key, []))
        kind = closure.kind_of(gate.key)
        if kind == closure.EXTERNAL_BLOCKED:
            external.append({
                "gate": gate.key, "what": gate.what, "kind": kind,
                "label": "external capability unavailable",
                "why": closure.EXTERNAL_GATES.get(gate.key, ""),
                "unblocks": parked, "unblocks_count": len(parked),
                "owner_action_ids": [r["id"] for r in bound],
                "how_it_is_checked": gate.how})
            continue
        if kind == closure.DATA_GATED:
            data_wait.append({"gate": gate.key, "what": gate.what, "kind": kind,
                              "unblocks": parked, "how_it_is_checked": gate.how})
            continue
        if gate.key in owner_queue.COMPANY_OPENED_GATES:
            # W4-OWNER: the company's own cadence opens this gate; never an owner ask.
            company_opened.append({"gate": gate.key, "what": gate.what, "unblocks": parked,
                                   "owner_action_ids": [r["id"] for r in bound],
                                   "why": owner_queue.COMPANY_OPENED_GATES[gate.key],
                                   "how_it_is_checked": gate.how})
            continue
        if not parked:
            suppressed.append({"gate": gate.key, "what": gate.what,
                               "owner_action_ids": [r["id"] for r in bound],
                               "why": "closed, but no requirement is parked on it, so "
                                      "opening it unblocks nothing"})
            continue
        # W4-GATESB: a card the owner cannot usefully answer yet (company work or another
        # gate must land first) is listed with its precondition, never asked.
        from . import gate_clearance

        precondition = gate_clearance.prerequisite(db, gate.key, env)
        if precondition:
            not_yet_askable.append({"gate": gate.key, "what": gate.what, "kind": kind,
                                    "unblocks": parked, "precondition": precondition,
                                    "owner_action_ids": [r["id"] for r in bound],
                                    "how_it_is_checked": gate.how})
            continue
        request = requests.get(gate.key)
        row = bound[0] if bound else None
        cards.append({
            "gate": gate.key,
            "kind": kind,
            "requirement_key": row["requirement_key"] if row else gate.key,
            "owner_action_id": row["id"] if row else None,
            "merged_owner_action_ids": [r["id"] for r in bound],
            "what": gate.what,
            "action": (row["action"] if row else request.action if request else
                       f"grant {gate.what}"),
            "why": (row["reason"] if row and row["reason"] else
                    request.purpose if request else
                    f"{len(parked)} requirements are parked on it"),
            "capability_unlocked": (request.unlocks if request else gate.what),
            # W4-OWNER: no row and no access request means the cost is UNKNOWN (None),
            # never CA$0; minutes come from the decision table, never an invented 10.
            "max_spend_cad": (row["max_cost_cad"] if row else
                              request.max_cost_cad if request else
                              _table_cost(gate.key)),
            "monthly_ceiling_cad": request.monthly_ceiling_cad if request else None,
            "minutes": (row["minutes"] if row and row["minutes"] else
                        request.minutes if request else _table_minutes(gate.key)),
            "risk": (request.security_scope if request else
                     "scope not yet described in the access registry"),
            "rollback": ("revocable at the source at any time; the gate closes again and "
                         "its requirements re-park automatically"),
            "consequence_of_waiting": (row["consequence_of_delay"] if row and
                                       row["consequence_of_delay"] else
                                       request.consequence_of_declining if request else
                                       f"requirements {parked} stay parked"),
            "continues_regardless": (request.continues_without if request else
                                     "every requirement not parked on this gate"),
            "unblocks": parked,
            "unblocks_count": len(parked),
            "how_it_is_checked": gate.how,
            "evidence": f"gate {gate.key!r} opens when: {gate.how}",
            "steps": (row["action"] if row else request.action if request else
                      f"grant {gate.what}"),
            "max_cost_cad": (row["max_cost_cad"] if row else
                             request.max_cost_cad if request else
                             _table_cost(gate.key)),
            # W4-B2CLOSE: a figure taken from the decision table is not a producer's
            # statement; owner_queue.decision_fields then shows the table's own basis.
            "cost_from_table": not row and not request,
        })
    for row in standalone:
        cards.append({
            "gate": None,
            "kind": "OWNER-DECISION",
            "requirement_key": row["requirement_key"],
            "owner_action_id": row["id"],
            "merged_owner_action_ids": [row["id"]],
            "what": row["action"],
            "action": row["action"],
            "why": row["reason"] or "a decision only the owner can make",
            "capability_unlocked": row["blocks"] or row["requirement_key"],
            "max_spend_cad": row["max_cost_cad"],
            "monthly_ceiling_cad": None,
            "minutes": row["minutes"],
            "risk": "stated in the action" if row["reason"] else "not described",
            "rollback": "the decision is recorded and can be reversed by a later decision",
            "consequence_of_waiting": row["consequence_of_delay"] or "not stated",
            "continues_regardless": "every requirement not waiting on this decision",
            "unblocks": [row["blocks"] or row["requirement_key"]],
            "unblocks_count": 1,
            "how_it_is_checked": (f"OwnerAction #{row['id']} "
                                  f"({row['requirement_key'] or 'no key'}) is marked done"),
            "evidence": (f"OwnerAction #{row['id']} raised {row['at'] or 'at an unknown time'}"
                         f" for {row['requirement_key'] or 'an unkeyed decision'}"),
            "steps": row["action"],
            "max_cost_cad": row["max_cost_cad"],
        })

    cards.sort(key=_urgency)
    # F-870 / F-623 / F-197 (K7): packet fields, explicit rank and urgency, the tester route.
    owner_queue.enrich_cards(db, cards, why_by_action_id={
        r["id"]: r["why_software_cannot"] for r in rows if r["why_software_cannot"]})
    # F-204: the gates above were read live on this call; the guard also needs a fresh
    # readiness assessment before an empty queue is called proven.
    empty_state = owner_queue.empty_guard(db, cards, gates_read_live=True)
    snapshot = queue(db)
    free_and_quick = [c for c in cards if c["max_cost_cad"] == 0.0
                      and c.get("max_cost_basis") != "UNKNOWN"]
    return {
        "cards": cards,
        "open_actions": len(cards),
        "batched_free_and_quick": [c["gate"] or c["requirement_key"] for c in free_and_quick],
        "external_capability_unavailable": external,
        "waiting_on_data": data_wait,
        "not_yet_askable": not_yet_askable,
        "suppressed_unblocks_nothing": suppressed,
        "satisfied_but_open": satisfied_but_open,
        # W4-OWNER: gates the company opens itself, never presented as owner asks.
        "company_opened_not_owner": company_opened,
        # W4-OWNER: the owner's decision packet -- cards merged into decisions, batched.
        "batches": owner_queue.batch_cards(cards),
        "parked_owner_actions": [{"owner_action_id": r["id"],
                                  "requirement_key": r["requirement_key"],
                                  "action": r["action"]} for r in parked_actions],
        "empty_state": empty_state,
        "gate_open": gate_open,
        "source": ("one queue: executor gate state merged with OwnerAction rows by "
                   "requirement_key (build2.executor.approval_inbox)"),
        "total_parked": snapshot["parked_total"],
        "ready_regardless": snapshot["ready_total"],
        "blocking_the_build": False,
        "note": ("An inbox is only asynchronous if the queue behind it does not wait. "
                 f"{snapshot['ready_total']} requirements are ready right now and none of "
                 f"them needs any of these answers; answering them un-parks "
                 f"{snapshot['parked_total']} more (#196)."),
    }
