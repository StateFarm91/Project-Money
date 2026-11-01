"""Tester recruitment, prepared and never sent (#9, #43, #250; gate `tester_roster`).

Owner authorisation 2026-10-07: prepare the allowed recruitment process; contacting a real
person is an external action, so the exact outreach and its channel are brought to the owner
as a confirmation item and nothing here sends anything.

**Why a public call and not direct messages.** A direct message to a maker's address is a
commercial electronic message under CASL and needs a basis (`growth.owned`). A call for
testers posted where makers go looking for test calls is not addressed to anybody; a maker
who answers it contacts us, and gives *express* consent on the intake form before we ever
write to them. That keeps the very first contact on the right side of CASL by construction.

**What a tester is offered is work, not an opinion.** The deliverables are the closed
vocabulary of `growth.creators` (a tested sample, a finished photograph); a review is not
askable there and is not asked for here. Compensation never depends on what the tester
thinks (#250 separates testing compensation from public review incentives).

`record_agreement` is the one intake: it writes the CreatorProfile that opens the gate only
when the intake carries express consent and an agreed brief that `creators.check_brief`
passes. A prospect on file is not a tester (C-38).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

CONSENT_VERSION = "tester-consent-v1-2026-10-07"

CHANNEL = {
    "primary": ("Ravelry group 'The Testing Pool' -- a public tester-call post from the "
                "Brambleloop Ravelry account (makers browse it to find tests)"),
    "secondary": ("a public post on the Brambleloop Etsy shop announcement or an owned "
                  "channel once one exists; never direct messages to individuals"),
    "why_this_channel": ("a public call is addressed to nobody, so it is not a commercial "
                         "electronic message to an address; respondents contact us and give "
                         "express consent on the intake form before we write to them"),
    "account_needed": "a Ravelry account in the owner's name (free; person-only signup)",
}

OFFER = {
    "deliverables": ("tested_sample", "finished_photograph"),
    "gets": [
        "the final pattern PDF free, and the next Brambleloop pattern of their choice free",
        "a test fee for the make (approved per make by the owner; default ceiling from "
        "gates.risk_matrix: CA$20/hour of estimated make time, yarn reimbursed at cost up to "
        "the stated ceiling)",
        "credit by name or handle in the pattern's acknowledgements, only if they want it",
    ],
    "never": ["a review, rating, favourite or testimonial (not askable: growth.creators)",
              "any condition on liking the pattern -- defects are the point of a test"],
}

CONSENT_TEXT = (
    "I agree that Brambleloop Studio may email me about this pattern test (instructions, "
    "questions about my results, and the test fee). This is express consent under Canada's "
    "Anti-Spam Legislation, recorded with today's date; I can withdraw it at any time by "
    "replying 'unsubscribe' or using the link in any message, and it is actioned within 10 "
    "business days. Separately, I choose whether Brambleloop may show my photos of the "
    "finished object (on its Etsy listings / its own site / its emails / ads), and I can "
    "withdraw that permission for future use at any time. I am 18 or older. I understand no "
    "review, rating or favourite is requested, and my fee does not depend on my opinion.")

INTAKE_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("handle", "name or handle to call you by (stored as a reference, not a contact list)", True),
    ("email", "email for this test only (kept with the consent record, not on the roster)", True),
    ("country_region", "country and province/state (for terminology and shipping-free kits)", True),
    ("experience", "crochet experience: beginner / intermediate / advanced", True),
    ("specialties", "what you usually make (departments)", True),
    ("can_weigh_grams", "do you have a kitchen scale reading to 1 g? (yes/no)", True),
    ("terms_preference", "US or UK crochet terms", True),
    # Tester terms (owner directive, construction-review round): independence is declared,
    # and qualification is shown, not asserted.
    ("relationship", "any relationship to Brambleloop or its owner -- household, family, "
                     "work or financial? describe it, or write 'none'", True),
    ("qualification", "a photo of, or link to, a finished piece you crocheted in joined "
                      "rounds", True),
    ("express_consent", "tick: " + CONSENT_TEXT[:80] + "...", True),
    ("photo_permission_scopes", "optional: brambleloop_listing / brambleloop_site / "
                                "brambleloop_email / advertising", False),
    ("credit_preference", "optional: credit by name / by handle / no credit", False),
)

OUTREACH_POST = {
    "title": "[Tester call] Crochet Hexagonal Bread Basket -- worsted cotton, ~3 hrs, paid",
    "body": (
        "Hello! Brambleloop Studio (a small Canadian crochet pattern studio, Etsy shop "
        "BrambleloopStudio) is looking for ONE tester for a small hexagonal bread basket "
        "worked in single crochet: base about 16 cm across the points, walls about 9 cm "
        "tall, worsted-weight cotton in two colours (about 40 m + 12 m), 5.0 mm hook.\n\n"
        "Who can apply: an adult who is not the shop's owner, not a member of the owner's "
        "household or family, and has no financial interest in Brambleloop. Please tell us "
        "about any relationship you have with Brambleloop or its owner, and include a photo "
        "of, or a link to, a finished piece you crocheted in joined rounds.\n\n"
        "What we ask: make the basket from the test PDF within 14 days, follow it exactly, "
        "and fill in the record sheet -- grams used per colour, the ball band (grams and "
        "metres), your hook, the finished measurements, whether it sits flat and holds its "
        "shape, hours, whether you followed it exactly, and anything that was unclear or "
        "wrong. Mistakes you find are the most useful thing you can send.\n\n"
        "What you get: CA$65.90 in total, paid to you in full -- a CA$55.90 test fee plus "
        "CA$10.00 towards two balls of yarn -- by a fee-free transfer (any payment-processing "
        "fee is ours and is never deducted from you); the final pattern free, another "
        "Brambleloop pattern of your choice, and credit if you want it. We never ask for "
        "reviews, ratings or favourites, and nothing depends on whether you like it.\n\n"
        "To apply, reply in this thread or message the Brambleloop Ravelry account; we will "
        "send the intake form (it records your consent to be emailed about this test, which "
        "you can withdraw any time). Brambleloop Studio, Canada."),
    "identification": "Brambleloop Studio, Canada; Etsy shop BrambleloopStudio",
    "sends_to_individuals": False,
}

def outreach_markdown(post: dict | None = None) -> str:
    """The tester-call file, one format for every kit (built by `quality.tester_kit.build`)."""
    post = post or OUTREACH_POST
    return ("# Tester call -- prepared, NOT SENT (owner confirmation required)\n\n"
            f"Channel: {CHANNEL['primary']}\n\n"
            f"**{post['title']}**\n\n"
            f"{post['body']}\n\n## Consent text\n\n"
            f"{CONSENT_TEXT}\n")


OWNER_STEPS = ("1) sign in to (or create) the Brambleloop Ravelry account; 2) post "
               "OUTREACH.md's title and body as a new thread in the group 'The Testing Pool' "
               "(tester-call board); 3) forward replies to the operator, who sends the "
               "intake form and records each agreement (quality.tester_programme."
               "record_agreement). Nothing is posted until you confirm")
OWNER_MINUTES = 20
MAX_COST_CAD = 0.0   # the post is free; each make's fee is the physical_proof decision


class TesterRefused(ValueError):
    pass


# SECREVIEW R6 (89eef1e): independence is an ALLOW-LIST, not a keyword denylist. A tester
# declares exactly one of these, normalised (case and punctuation ignored). Anything else --
# family of any degree, a partner, someone in the owner's household, an employee or
# contractor, anyone with a financial interest, or any free-text description -- is refused,
# and the operator brings it to the owner instead.
ALLOWED_RELATIONSHIPS = {"none": "none", "acquaintancedeclared": "acquaintance (declared)"}


def _norm_relationship(text: str | None) -> str:
    import re

    return re.sub(r"[^a-z]", "", (text or "").lower())


def independence_problems(relationship: str | None) -> list[str]:
    """Why a relationship declaration disqualifies a tester; [] for an allowed one."""
    if relationship is None or not str(relationship).strip():
        return ["no relationship declaration: a tester declares 'none' or "
                "'acquaintance (declared)'"]
    if _norm_relationship(relationship) in ALLOWED_RELATIONSHIPS:
        return []
    return [f"declared relationship {relationship!r} is not on the independence allow-list "
            f"({sorted(ALLOWED_RELATIONSHIPS.values())}). Family of any degree, a partner, "
            f"the owner's household, an employee or contractor and any financial interest "
            f"are refused; bring any other declaration to the owner"]


def qualification_problems(qualification) -> list[str]:
    """SECREVIEW R16: qualification evidence of substance -- a web link (http/https with a
    host) or a stored photo reference (`photo:<sha256>`, or a bare SHA-256). "." is not."""
    import re

    text = str(qualification or "").strip()
    if re.fullmatch(r"https?://[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:\d+)?(/\S*)?", text):
        return []
    if re.fullmatch(r"(photo:)?[0-9a-f]{64}", text.lower()):
        return []
    return [f"qualification {text[:60]!r} is not evidence: give a link (https://...) to, or a "
            f"stored photo (photo:<sha256>) of, a finished piece worked in joined rounds"]


def independent_agreement(db, tester_ref: str | None) -> dict | None:
    """SECREVIEW R12: the recorded tester agreement that makes `tester_ref` an independent,
    qualified tester, or None. Only a permission written by `record_agreement` through the
    allow-list counts; an agreement recorded before the allow-list (no `independence` block),
    the owner, and an unknown reference are None."""
    from sqlalchemy import select

    from ..core.models import CreatorProfile

    ref = str(tester_ref or "").strip()
    if not ref or ref.lower() == "owner":
        return None
    with db.session() as s:
        row = s.scalar(select(CreatorProfile).where(CreatorProfile.ref == ref))
        perms = list(row.permissions or []) if row is not None else []
    for p in reversed(perms):
        ind = (p or {}).get("independence") or {}
        if ((p or {}).get("kind") == "tester_agreement"
                and ind.get("relationship") in ALLOWED_RELATIONSHIPS.values()
                and not qualification_problems(ind.get("qualification"))):
            return dict(p)
    return None


def record_agreement(db, *, handle_ref: str, specialties: list[str], express_consent: bool,
                     consent_source: str, photo_scopes: list[str] | None = None,
                     agreed_on: date | None = None, relationship: str | None = None,
                     qualification: str | None = None) -> dict:
    """Record one tester who agreed. Refuses without express consent or with a dishonest brief.

    Writes a CreatorProfile with a recorded permission (consent reference + version), which
    is what the `tester_roster` gate counts. The email lives where consent lives, not here.
    """
    from sqlalchemy import select

    from ..core.models import CreatorProfile
    from ..growth import creators, owned

    # SECREVIEW R6: the tester terms are mandatory for every new agreement -- an allowed
    # relationship declaration and qualification evidence. Absent is refused, never skipped.
    problems = independence_problems(relationship) + qualification_problems(qualification)
    if problems:
        raise TesterRefused("; ".join(problems))
    if not express_consent:
        raise TesterRefused("no express consent recorded: a tester is somebody who agreed, "
                            "and CASL needs the agreement before we write to them")
    if not (consent_source or "").strip():
        raise TesterRefused("a consent with no source is an assertion; name where it is kept")
    ref = (handle_ref or "").strip()[:80]
    if not ref:
        raise TesterRefused("a tester needs a reference")
    on = agreed_on or datetime.now(timezone.utc).date()
    consent = owned.Consent(address_ref=f"tester:{ref}", basis=owned.EXPRESS, obtained_on=on,
                            source=consent_source)
    pod = (specialties or ["home_decor"])[0]
    brief = creators.check_brief(creators.Brief(
        creator_ref=ref, pod=pod, deliverables=OFFER["deliverables"], fee_cad=0.0,
        terms="make from the test PDF and report what happened, including what did not work"))
    if not brief["ok"]:
        raise TesterRefused("; ".join(brief["reasons"]))
    for scope in photo_scopes or []:
        if scope not in creators.SCOPES:
            raise TesterRefused(f"{scope!r} is not a permission scope: {creators.SCOPES}")
    permission = {"kind": "tester_agreement", "consent_version": CONSENT_VERSION,
                  "consent_basis": consent.basis, "consent_source": consent.source,
                  "agreed_on": on.isoformat(), "photo_scopes": list(photo_scopes or []),
                  "independence": {
                      "relationship": ALLOWED_RELATIONSHIPS[_norm_relationship(relationship)],
                      "qualification": str(qualification).strip()[:300]}}
    with db.session() as s:
        row = s.scalar(select(CreatorProfile).where(CreatorProfile.ref == ref))
        if row is None:
            row = CreatorProfile(ref=ref, specialties=list(specialties or [pod]),
                                 invited=1, delivered=0, permissions=[permission])
            s.add(row)
        else:
            row.permissions = list(row.permissions or []) + [permission]
            row.invited = int(row.invited or 0) + 1
    return {"recorded": True, "ref": ref, "permission": permission, "brief": brief}


def packet() -> dict:
    """Everything the owner confirmation item and the report carry."""
    return {"channel": CHANNEL, "offer": OFFER, "consent_text": CONSENT_TEXT,
            "consent_version": CONSENT_VERSION,
            "intake_fields": [{"field": f, "label": l, "required": r}
                              for f, l, r in INTAKE_FIELDS],
            "outreach": OUTREACH_POST, "owner_steps": OWNER_STEPS,
            "owner_minutes": OWNER_MINUTES, "max_cost_cad": MAX_COST_CAD,
            "sent": False}
