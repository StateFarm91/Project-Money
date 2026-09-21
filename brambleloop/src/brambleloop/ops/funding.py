"""When the account runs out of money, say so to the one person who can fix it.

Found live on 2026-09-21: the reference-pack build rendered its images, spent CA$0.08, and
died at the first vision call with *"Your credit balance is too low to access the Anthropic
API"*. Every part of the system behaved correctly. The gateway classified it as permanent
rather than retrying it, the handler recorded the reason, the job completed with an honest
`built: false`, and the endpoint reported the attempt and its stage.

And nobody was told. The only person who can buy credit is the owner, the owner's queue is
the one place this build puts things that need them, and a funding failure went to a JSON
field instead. A capability that cannot be routed around and cannot be fixed from inside is
the definition of an owner action.

Two distinctions this makes, because both were live at the time:

**Out of money is not over budget.** The monthly ceiling is a policy this system enforces on
itself and was nowhere near breached -- CA$45 of CA$100. The account balance is money that
exists or does not. Reporting the first when the second is true sends somebody to the wrong
screen.

**Out of money is per provider.** Image generation is prepaid at OpenAI and Black Forest
Labs and kept working; the judging and vision calls are Anthropic and stopped. Saying "the
model provider is down" would be wrong twice: it is not down and it is not all of them.
"""
from __future__ import annotations

ACTION = "ops.funding_exhausted"

REQUIREMENT_KEY = "model_provider_balance"

# What a spent balance says, as each provider says it. Matched case-insensitively against
# whatever the failure text was, because these arrive as a provider's prose inside an HTTP
# body and nothing about them is structured.
MARKERS: tuple[str, ...] = (
    "credit balance is too low",
    "insufficient credit",
    "insufficient_quota",
    "billing_hard_limit_reached",
    "exceeded your current quota",
    "payment required",
)

# Which provider a message is about, where it can be told. A funding failure names the
# account to top up, and "a provider" is not an actionable sentence.
PROVIDERS: tuple[tuple[str, str], ...] = (
    ("anthropic", "Anthropic (judging, vision, all text calls)"),
    ("openai", "OpenAI (image generation)"),
    ("bfl", "Black Forest Labs (image generation)"),
    ("x-key", "Black Forest Labs (image generation)"),
)


def detect(text: str) -> bool:
    """Whether this failure is a spent balance rather than an outage or a bug."""
    low = (text or "").lower()
    return any(marker in low for marker in MARKERS)


def provider_in(text: str) -> str:
    low = (text or "").lower()
    for needle, name in PROVIDERS:
        if needle in low:
            return name
    return "a model provider named in the error"


def note(db, text: str) -> dict:
    """Raise the owner action, once, and record that the balance is the blocker.

    Idempotent on the requirement key: a spent balance fails every call that follows it, and
    an owner queue with forty copies of one action is a queue nobody reads.
    """
    if db is None or not detect(text):
        return {"raised": False}

    from sqlalchemy import select

    from ..core.models import OwnerAction

    provider = provider_in(text)
    with db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == REQUIREMENT_KEY,
            OwnerAction.done == False))  # noqa: E712
        if open_row is not None:
            return {"raised": False, "reason": "already open", "provider": provider}
        s.add(OwnerAction(
            requirement_key=REQUIREMENT_KEY,
            action=(f"Add credit to the {provider} account. Anthropic: console.anthropic.com "
                    f"-> Plans & Billing. OpenAI: platform.openai.com -> Billing. Black "
                    f"Forest Labs: the dashboard the key was issued from."),
            reason=(f"{provider} refused a call because the account balance is spent. This "
                    f"is not the monthly ceiling -- that is a policy this system enforces on "
                    f"itself and it is not breached. It is money in the account, which only "
                    f"you can add."),
            max_cost_cad=25.0,
            minutes=5,
            consequence_of_delay=(
                "Every call to that provider fails until it is topped up. For Anthropic "
                "that is all judging and vision: the canonical-model identity measurements, "
                "the asset-truth checks on generated imagery, and the MJs gallery "
                "analysis. Image rendering is prepaid elsewhere and continues, which is why "
                "renders succeed and the checks on them do not."),
            blocks="all model judgement: identity measurement, asset truth, gallery analysis"))

    return {"raised": True, "provider": provider, "requirement_key": REQUIREMENT_KEY}
