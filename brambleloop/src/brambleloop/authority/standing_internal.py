"""The owner's standing authorisation for routine internal operations (D-OWNER-STANDING-INTERNAL).

ENG-APPROVALS (owner directive, 2026-11-19). The owner queue had grown to ~106 cards, most of
them asking the owner to approve work the company is already authorised to do. The owner
replaced the per-item asks with one standing decision, recorded verbatim in DECISION_LOG
(`D-OWNER-STANDING-INTERNAL`) and in `DIRECTIVE_TEXT` below.

This module is that decision in code. It is not a second authority framework: it *reads* the
existing ones --

* `authority.classes`: the action classes the directive covers are exactly the five autonomous
  classes (OBSERVE, RESEARCH, BUILD, TEST, DRAFT). The gated classes (PUBLISH, SPEND, DEPLOY,
  LEGAL-TAX, CUSTOMER-REMEDY, CREDENTIALS) are never covered; `covers_job_type` says so and a
  test pins that the two sets agree with `classes.AUTONOMOUS`.
* `ops.owner_queue`: the OwnerAction lifecycle. Covered or redundant cards are moved with
  `owner_queue.transition` (history kept, nothing deleted), and every automatic move writes
  one `owner_action.standing_authority` audit row citing the directive.
* `build2.executor` gates and `ops.owner_queue.DECISIONS`: the gate-bound decisions.

Classification (`classify`) is a table of OwnerAction requirement keys (exact keys and
prefixes) to one of three dispositions:

ROUTINE_INTERNAL   covered by the standing authority. The card is superseded by the directive;
                   the work it asked about proceeds inside every existing gate and ceiling.
AUTO_CLOSE         redundant, stale or already satisfied (the reason is the rule's). Closed.
GENUINE_EXCEPTION  stays with the owner. Only the directive's eight exception classes qualify
                   (`EXCEPTION_CLASSES`).

It fails closed: a key nothing in the table names is a GENUINE_EXCEPTION
(`unclassified_fail_closed`) -- left with the owner, never auto-approved -- and the P0 board
counts them so the table is extended rather than guessed.

What this module never does: sign, seal or record any owner grant, launch decision or policy
review; publish, activate, spend, deploy, change the phase or `STAGE_A_ENABLED`; delete a row.
The owner's words: "Do not interpret this as me attesting that I've personally reviewed
external policies, supplied physical evidence, signed specific cryptographic grants or
authorized publication that hasn't passed its requirements."
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import classes

DIRECTIVE_ID = "D-OWNER-STANDING-INTERNAL"
DIRECTIVE_AT = "2026-11-19"
DIRECTIVE_TEXT = (
    "I authorize all routine internal Brambleloop operations within our existing budgets, "
    "permissions and safety requirements. Research, product development, engineering, testing, "
    "PDF creation, image generation, SEO, listing preparation, learning, recovery, scheduling "
    "and agent coordination should happen AUTOMATICALLY. I approve the opening catalogue's Etsy "
    "listing fees up to CA$6 and the existing CA$100/month model-spending ceiling. This is not "
    "permission for paid ads, additional subscriptions, or higher spending. Replace the 106-card "
    "owner queue with consolidated decisions, standing authorizations and automatic closure of "
    "redundant, stale or already-satisfied requests. Preserve the audit trail. Do not interpret "
    "this as me attesting that I've personally reviewed external policies, supplied physical "
    "evidence, signed specific cryptographic grants or authorized publication that hasn't "
    "passed its requirements. Bring me only those genuinely necessary exceptions in one concise "
    "batch. Do not let unresolved publication approvals stop safe internal manufacturing.")

#: The audit action every automatic decision under the directive writes (retention: lifetime).
AUDIT_ACTION = "owner_action.standing_authority"
#: The actor of those rows (an automatic decision is never written as the owner).
ACTOR = "standing_authority"

ROUTINE_INTERNAL = "ROUTINE_INTERNAL"
#: ROUTINE_INTERNAL keys whose supersede approves nothing (no work is authorised by it).
NO_APPROVAL_PREFIXES: tuple[str, ...] = ("improve.challenger_run:", "taxonomy_drift:")
AUTO_CLOSE = "AUTO_CLOSE"
GENUINE_EXCEPTION = "GENUINE_EXCEPTION"
DISPOSITIONS = (ROUTINE_INTERNAL, AUTO_CLOSE, GENUINE_EXCEPTION)

# The directive's exception classes, and nothing else (plus the fail-closed default).
GRANT_SIGNATURE = "grant_signature_or_step_up"
PUBLICATION = "publication_or_activation"
POLICY_ATTESTATION = "external_policy_attestation"
PHYSICAL_EVIDENCE = "physical_evidence"
SPEND_BEYOND_BUDGET = "spend_beyond_approved_budgets"
PAID_ADS_SUBSCRIPTIONS = "paid_ads_or_subscriptions"
KYC_LEGAL_BANKING = "kyc_legal_banking"
CERT_SAFETY_AUTHORITY = "certification_construction_safety_authority"
UNCLASSIFIED = "unclassified_fail_closed"
EXCEPTION_CLASSES: tuple[str, ...] = (
    GRANT_SIGNATURE, PUBLICATION, POLICY_ATTESTATION, PHYSICAL_EVIDENCE, SPEND_BEYOND_BUDGET,
    PAID_ADS_SUBSCRIPTIONS, KYC_LEGAL_BANKING, CERT_SAFETY_AUTHORITY)

#: The work the directive names, for the record and the batch view.
COVERED_WORK: tuple[str, ...] = (
    "research", "product development", "engineering", "testing", "PDF creation",
    "image generation", "SEO", "listing preparation", "learning", "recovery", "scheduling",
    "agent coordination")

#: The action classes the directive covers: the autonomous classes, never a gated one.
COVERED_CLASSES: frozenset = frozenset(classes.AUTONOMOUS)

#: Budgets the directive approves, as figures. Neither raises any other ceiling.
OPENING_LISTING_FEE_BUDGET_CAD = 6.00
MODEL_MONTHLY_CEILING_CAD = 100.00

#: An open card with no restatement for this long, whose kind is not a genuine exception,
#: is stale.
STALE_AFTER = timedelta(days=21)


def covers_job_type(job_type: str) -> bool:
    """True when the directive covers this job type: its declared class is autonomous.

    A gated class (publish, spend, deploy, legal/tax, customer remedy, credentials) and an
    unclassified type are never covered."""
    cls = classes.classify(job_type)
    return isinstance(cls, classes.ActionClass) and cls in COVERED_CLASSES


# ---- the kind table --------------------------------------------------------------------------
#
# (match, pattern, disposition, class-or-rule, why). `match` is "exact", "prefix" or "regex".
# Order matters: the first matching rule wins, so the specific genuine rules come first. Each
# row cites the producer the inventory found it in
# (research/final_build/w6/owner_queue_classification.md).

def _r(match, pattern, disposition, klass, why):
    return {"match": match, "pattern": pattern, "disposition": disposition, "class": klass,
            "why": why}


R, A, G = ROUTINE_INTERNAL, AUTO_CLOSE, GENUINE_EXCEPTION

_GS, _PUB, _POL, _PHY = GRANT_SIGNATURE, PUBLICATION, POLICY_ATTESTATION, PHYSICAL_EVIDENCE
_SPEND, _ADS, _KYC, _CERT = (SPEND_BEYOND_BUDGET, PAID_ADS_SUBSCRIPTIONS, KYC_LEGAL_BANKING,
                             CERT_SAFETY_AUTHORITY)
_COVERED = f"covered by {DIRECTIVE_ID}"

KIND_RULES: tuple[dict, ...] = (
    # ---- GENUINE: certification, construction and safety authority (independent approval) --
    _r("prefix", "childrens-decision:", G, _CERT, "children's-safety decision (A1-R)"),
    _r("prefix", "physical_size_conflict:", G, _CERT, "lifting a physical size halt"),
    _r("exact", "decision.api_vision_equivalence", G, _CERT, "the acceptance-wording ruling"),
    # A ruling of not_a_defect releases a publication withholding, and the incident's `clears`
    # field says "owner decision only" (support/defects.py): never superseded.
    _r("prefix", "support_defect_decision:", G, _CERT,
       "a reader-reported pattern defect: only the owner's ruling releases the withholding"),
    _r("prefix", "improve.upgrade:", G, _CERT, "a gate-tier improvement (cells approval)"),
    # ---- GENUINE: grant signatures and step-up acts --------------------------------------
    _r("prefix", "improve.league:", G, _GS, "promoting a challenger is a step-up owner act"),
    _r("exact", "storefront:write_authority", G, _GS, "signed storefront grants"),
    _r("exact", "canonical_model_selection", G, _GS, "an owner approval record (never forged)"),
    _r("exact", "canonical_model_approval", G, _GS, "an owner approval record (never forged)"),
    _r("exact", "etsy.auth:reauthorise", G, _GS, "OAuth consent by the account holder"),
    _r("exact", "reauthorise_transactions_r", G, _GS, "OAuth consent by the account holder"),
    _r("exact", "benchmark_observation", G, _GS, "developer credentials of the account holder"),
    _r("exact", "model_provider", G, _GS, "a provider key set in the host by the owner"),
    _r("prefix", "credential_rotation:", G, _GS, "rotating an exposed credential"),
    _r("exact", "etsy_surface:webhook_order_paid", G, _GS, "a webhook signing secret"),
    _r("exact", "store:OA-B", G, _GS, "account settings and 2FA"),
    # ---- GENUINE: KYC, legal, banking ------------------------------------------------------
    _r("exact", "etsy_shop", G, _KYC, "identity verification and seller terms"),
    _r("exact", "payout", G, _KYC, "payout bank account and tax details"),
    _r("exact", "brand_clearance", G, _KYC, "legal risk acceptance / trademark"),
    _r("exact", "etsy_surface:payment_settings_setup", G, _KYC, "Etsy Payments onboarding"),
    _r("exact", "etsy_surface:legal_and_tax_setup", G, _KYC, "identity, legal and tax"),
    _r("prefix", "legal_review:", G, _KYC, "an IP/account notice; legal advice"),
    _r("prefix", "creators.graduate:", G, _KYC, "an agreement with a real person"),
    _r("exact", "model_credits", G, _KYC, "a payment by the account holder"),
    _r("exact", "model_provider_balance", G, _KYC, "a payment by the account holder"),
    _r("prefix", "model_provider_balance:", G, _KYC, "a payment by the account holder"),
    # ---- GENUINE: spend beyond the approved budgets ---------------------------------------
    # listing_fees: the opening-catalogue fee is approved up to CA$6 (enforced in
    # finance.listing_costs); the readiness card itself stays until its producer clears it.
    _r("exact", "listing_fees", G, _SPEND, "fees beyond the CA$6 opening budget need the owner"),
    _r("exact", "benchmark_challenge", G, _SPEND, "buying benchmark patterns (CA$300)"),
    _r("exact", "image_benchmark_budget", G, _SPEND, "raising a provider budget"),
    _r("prefix", "spend.ceiling.", G, _SPEND, "raising a monthly spend ceiling"),
    _r("prefix", "reinvestment:", G, _SPEND, "reinvesting revenue"),
    _r("prefix", "knowledge_gap:", G, _SPEND, "buying a reference pattern"),
    _r("prefix", "benchmark_refresh:", G, _SPEND, "buying a benchmark pattern"),
    _r("prefix", "etsy.dashboard:renewal:", G, _SPEND, "a renewal fee outside the opening budget"),
    # ---- GENUINE: paid ads and subscriptions ----------------------------------------------
    _r("prefix", "ads.", G, _ADS, "paid advertising"),
    _r("exact", "etsy_ads_eligibility_evidence", G, _ADS, "an Etsy Ads reading (no activation)"),
    _r("exact", "etsy_surface:etsy_ads_off", G, _ADS, "Etsy Ads stay off unless the owner says"),
    _r("exact", "store:OA-G2", G, _ADS, "Offsite Ads enrolment (15% fee)"),
    _r("exact", "etsy_surface:subscription_none", G, _ADS, "no paid Etsy subscription"),
    _r("exact", "artifact_storage", G, _ADS, "an object-storage subscription"),
    _r("exact", "laura.voice.listen_shortlist", G, _ADS, "a voice provider account / paid trial"),
    # ---- GENUINE: physical evidence and readings only a person can take -------------------
    _r("prefix", "physical_evidence:", G, _PHY, "an independent tester make / swatch"),
    _r("prefix", "physical_review:", G, _PHY, "a partial physical sample"),
    _r("exact", "physical_calibration", G, _PHY, "a physical sample"),
    _r("exact", "search_visibility:launch_week", G, _PHY, "a Shop Manager reading"),
    _r("exact", "store:OA-BANNER", G, _PHY, "a phone screenshot of the banner crop"),
    _r("exact", "etsy_surface:offsite_ads_fee_readout", G, _PHY, "a Finances reading"),
    _r("exact", "etsy_surface:first_monthly_statement", G, _PHY, "the monthly statement file"),
    _r("exact", "etsy_surface:developer_portal_quota", G, _PHY, "a Developer Portal reading"),
    # ---- GENUINE: external policy attestation ---------------------------------------------
    _r("prefix", "policy_violation_overdue:", G, _POL, "an Etsy policy-violation item"),
    _r("exact", "etsy_surface:messages_watch", G, _POL, "the owner's message-watch attestation"),
    _r("exact", "etsy_surface:policy_violations_check", G, _POL, "a Policy Violations check"),
    _r("exact", "etsy_surface:apps_none_installed", G, _POL, "no third-party app attestation"),
    _r("exact", "etsy_surface:shared_access_empty", G, _POL, "Shared Access attestation"),
    _r("exact", "store:OA-OBS", G, _POL, "what the live shop shows, observed by the owner"),
    _r("exact", "store:OA-G1", G, _POL, "an Etsy shop-option attestation"),
    # ---- GENUINE: publication, activation, customer-facing acts ---------------------------
    _r("exact", "phase", G, _PUB, "a phase move out of shadow"),
    _r("prefix", "first_public_listing:", G, _PUB,
       "the first public listing and its fee (step-up)"),
    _r("prefix", "standing_policy.hold:", G, _PUB, "a release outside the standing policy"),
    _r("prefix", "standing_policy.withdrawal_unconfirmed:", G, _PUB, "deactivation on Etsy"),
    _r("prefix", "listing.live_update:", G, _PUB, "changing a live listing"),
    _r("prefix", "portfolio.retire:", G, _PUB, "deactivating a live listing"),
    _r("prefix", "draft_reconcile:", G, _PUB, "binding an Etsy draft to a release"),
    _r("prefix", "etsy.exercise.stranded_draft.", G, _PUB, "deleting a draft in Shop Manager"),
    _r("prefix", "correction_notice:", G, _PUB, "a message to buyers"),
    _r("prefix", "support.first_response:", G, _PUB, "a reply to a buyer"),
    _r("prefix", "etsy.dashboard:order:", G, _PUB, "contact with a buyer"),
    _r("exact", "club:launch_decision", G, _PUB, "launching a buyer-facing club"),
    _r("prefix", "storefront.asset:", G, _PUB, "an upload in Etsy Info & Appearance"),
    _r("prefix", "etsy_surface:", G, _PUB, "a change in the live Etsy shop"),
    _r("prefix", "store:OA-", G, _PUB, "a change in the live Etsy shop settings"),
    # ---- AUTO_CLOSE: redundant / superseded ------------------------------------------------
    _r("exact", "autonomy:store_commerce:publication_review", A, "redundant",
       "each certified release has its own publication card carrying this decision"),
    _r("exact", "etsy.oauth.reauthorise", A, "redundant",
       "legacy key superseded by etsy.auth:reauthorise (no producer raises it)"),
    # Withdrawn, not superseded: the package job re-asks after a supersede it did not make
    # itself (listing_package EF2-4) but treats a withdrawn request for the same content as
    # answered, so this closes once per content fingerprint instead of churning hourly.
    _r("prefix", "listing_package:", A, "redundant_withdrawn",
       "the publication grant previews and binds the same listing content; nothing reads a "
       "closed package card as approval"),
    # ---- ROUTINE_INTERNAL: covered by the standing authority -------------------------------
    _r("exact", "store:etsy.openapi_review", R, "engineering",
       f"{_COVERED}: research/engineering -- the weekly re-verification is company work"),
    _r("exact", "store:etsy.ui_drift_review", R, "engineering",
       f"{_COVERED}: research/engineering -- the surface inventory is company work"),
    _r("exact", "model.vendor_switch_routed_only", R, "engineering",
       f"{_COVERED}: engineering -- routed to Main (configuration), not an owner decision"),
    _r("exact", "model.routes_invalid", R, "engineering",
       f"{_COVERED}: engineering -- routed to Main (configuration), not an owner decision"),
    _r("exact", "creative.reengineer:owner_choice", R, "product_development",
       f"{_COVERED}: product development -- which legacy products to re-engineer"),
    _r("prefix", "chain-deadend:pricing:", R, "product_development",
       f"{_COVERED}: pricing / product development before publication"),
    _r("prefix", "taxonomy_drift:", R, "recovery",
       f"{_COVERED}: recovery -- re-certifying drifted listings is internal work"),
    _r("prefix", "portfolio.rework:", R, "product_development",
       f"{_COVERED}: product development -- a new design version"),
    _r("exact", "improve.retirement:weekly_review", R, "agent_coordination",
       f"{_COVERED}: agent coordination -- the weekly retire/merge review"),
    _r("exact", "improve.architecture:add", R, "agent_coordination",
       f"{_COVERED}: agent coordination -- specialist agents"),
    _r("exact", "improve.architecture:revise_metric", R, "agent_coordination",
       f"{_COVERED}: agent coordination -- department metrics"),
    _r("exact", "improve.stop_list:weekly", R, "scheduling",
       f"{_COVERED}: scheduling -- the weekly STOP list"),
    _r("prefix", "improve.challenger_run:", R, "learning",
       f"{_COVERED}: learning -- one league run (<= CA$2) inside the approved CA$100/month "
       f"model ceiling, which SpendGuard still enforces"),
    # laura:/dag: requests name a job type; decided by its declared action class below.
)

#: Keys that ask for authority over a named job type; decided by `authority.classes`.
JOB_TYPE_PREFIXES = ("laura:", "dag:")
_CLASS_EXCEPTION = {"PUBLISH": PUBLICATION, "SPEND": SPEND_BEYOND_BUDGET,
                    "DEPLOY": PUBLICATION, "LEGAL-TAX": KYC_LEGAL_BANKING,
                    "CUSTOMER-REMEDY": PUBLICATION, "CREDENTIALS": GRANT_SIGNATURE}


def _job_type_verdict(key: str) -> dict | None:
    """laura:/dag: keys: covered when every job type the key names is autonomous; the
    exception class of the first gated one otherwise; None when it names no job type."""
    if not key.startswith(JOB_TYPE_PREFIXES):
        return None
    parts = [p for p in key.split(":")[1:] if "." in p]
    named = [p for p in parts if p in classes.JOB_CLASS]
    if not named:
        return None
    gated = [p for p in named if not covers_job_type(p)]
    if gated:
        cls = classes.class_value(gated[0])
        return {"disposition": GENUINE_EXCEPTION,
                "class": _CLASS_EXCEPTION.get(cls, UNCLASSIFIED),
                "rule": f"job_type:{gated[0]}",
                "why": f"{gated[0]} is {cls}, a gated class the directive does not cover"}
    return {"disposition": ROUTINE_INTERNAL, "class": "autonomous_class",
            "rule": f"job_type:{named[0]}",
            "why": (f"{_COVERED}: {', '.join(named)} "
                    f"({', '.join(classes.class_value(n) for n in named)}) is autonomous work")}


def _matches(rule: dict, key: str) -> bool:
    m, p = rule["match"], rule["pattern"]
    if m == "exact":
        return key == p
    if m == "prefix":
        return key.startswith(p)
    return re.fullmatch(p, key) is not None


def classify(requirement_key: str | None) -> dict:
    """The disposition of an OwnerAction kind. Fails closed to GENUINE_EXCEPTION."""
    key = (requirement_key or "").strip()
    jt = _job_type_verdict(key) if key else None
    if jt is not None:
        return {"key": key, "directive": DIRECTIVE_ID, **jt}
    for rule in KIND_RULES:
        if key and _matches(rule, key):
            return {"key": key, "disposition": rule["disposition"], "class": rule["class"],
                    "rule": f"{rule['match']}:{rule['pattern']}", "why": rule["why"],
                    "directive": DIRECTIVE_ID}
    return {"key": key, "disposition": GENUINE_EXCEPTION, "class": UNCLASSIFIED,
            "rule": "default", "directive": DIRECTIVE_ID,
            "why": ("no rule names this kind: it stays with the owner (fail closed) until the "
                    "classification table is extended")}


def is_genuine(requirement_key: str | None) -> bool:
    return classify(requirement_key)["disposition"] == GENUINE_EXCEPTION


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---- the covered marker: producers must not re-raise a closure that is in force ---------------

#: Audit rows written when a producer sees its condition clear while a closure is in force.
CLEARED_ARTIFACT_PREFIX = "owner_action_key:"


def closure_in_force(session, requirement_key: str, action: str | None = None) -> bool:
    """True while an automatic (standing-authority) closure covers this key and condition.

    The sweep closes a routine or redundant card; a producer that still sees its condition would
    raise the same card again on the next tick, and the sweep would close it again -- one more
    owner_actions row, lifecycle row and audit row per hour, for ever. A producer asks this
    first and, when it is True, raises nothing.

    In force means all of:
      * the kind is not a genuine exception (a genuine one is never covered);
      * the most recent closed row for the key was closed by the standing authority, i.e. an
        `owner_action.standing_authority` audit row names it (a card the owner closed, or one the
        producer closed itself because its condition cleared, is not covered);
      * no later audit row says the producer saw the condition clear
        (`note_condition_cleared`);
      * when `action` is given, it is the text the closed card carried: a changed condition
        (another vendor named, another invalid route) is a new card.
    Nothing is deleted or rewritten; the closed row and its audit trail stay as they are."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction

    key = (requirement_key or "").strip()
    if not key or is_genuine(key):
        return False
    with session.no_autoflush:
        last = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == key, OwnerAction.done == True)  # noqa: E712
            .order_by(OwnerAction.id.desc()).limit(1))
        if last is None:
            return False
        if action is not None and (last.action or "") != action:
            return False
        marks = list(session.scalars(select(AuditLog).where(
            AuditLog.action == AUDIT_ACTION,
            AuditLog.artifact.in_([f"owner_action:{last.id}",
                                   CLEARED_ARTIFACT_PREFIX + key[:150]]))
            .order_by(AuditLog.id.desc()).limit(1)))
    return bool(marks) and marks[0].artifact == f"owner_action:{last.id}"


def closed_by_standing_authority(session, row) -> bool:
    """True when the standing authority (not the owner) made the latest closure of `row`.

    The latest lifecycle or standing audit row naming the card decides, so a card the standing
    authority superseded and the owner later reopened and closed is the owner's."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    rid = getattr(row, "id", None)
    if rid is None:
        return False
    with session.no_autoflush:
        last = session.scalar(select(AuditLog).where(
            AuditLog.action.in_([AUDIT_ACTION, "owner_action.lifecycle"]),
            AuditLog.artifact == f"owner_action:{rid}")
            .order_by(AuditLog.id.desc()).limit(1))
    return bool(last is not None and (last.action == AUDIT_ACTION or last.actor == ACTOR))


def owner_closed(session, row, states=None) -> bool:
    """The OWNER closed `row`: it is done, in one of `states` (default satisfied or the legacy
    closed_unclassified), and the standing authority did not close it. A withdrawn, superseded
    or expired card is not an owner decision unless a caller names that state in `states`."""
    from ..ops import owner_queue

    if row is None or not row.done:
        return False
    allowed = frozenset(states) if states is not None else frozenset(
        {owner_queue.SATISFIED, owner_queue.CLOSED_UNCLASSIFIED})
    if owner_queue.effective_state(row) not in allowed:
        return False
    return not closed_by_standing_authority(session, row)


def note_condition_cleared(session, requirement_key: str) -> bool:
    """A producer saw its condition clear: end any closure in force, with one audit row.

    Writes nothing when no closure is in force, so a clear condition costs no rows."""
    from ..core.models import AuditLog

    key = (requirement_key or "").strip()
    if not closure_in_force(session, key):
        return False
    session.add(AuditLog(actor=ACTOR, action=AUDIT_ACTION,
                         artifact=CLEARED_ARTIFACT_PREFIX + key[:150],
                         detail={"directive": DIRECTIVE_ID, "event": "condition_cleared",
                                 "requirement_key": key}))
    return True
