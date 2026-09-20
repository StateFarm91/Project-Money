"""Which cultural domain a discovered topic belongs to, and what it may never conclude.

Requirement 133 names ten domains: films, television, memes, nostalgia eras, seasonal
traditions, viral aesthetics, music, sports culture, celebrity-driven aesthetics and internet
moments. Discovery produces article titles; this decides which domain each one is, and
refuses everything else.

**The vocabulary is closed on both sides.** An open answer produces "culture", and a closed
question with a tolerant parser produces "culture" one layer down. A topic the model cannot
place comes back `unplaced`, which is a state the radar can act on -- it is the interesting
half of a most-read list -- rather than a wrong domain that looks like knowledge.

**Placement is not permission.** Being classified says nothing about whether this company may
make anything from the topic. `culture.rights` decides that, separately and afterwards, and
nothing here is allowed to imply otherwise: a domain is a filing decision and rights are a
legal one, and collapsing them is how a protected character becomes a product because it was
filed under `film`.

**A topic is not a demand signal.** The most-read article on a given day is frequently a
death, a disaster or an election. `commercially_relevant` is a separate judgement with its
own refusals, so that "trending" never silently means "worth making".
"""
from __future__ import annotations

import json

from ..core.resilience import PermanentError, TransientError
from .radar import DOMAINS

UNPLACED = "unplaced"

# Topics that are trending and must never become products, whatever domain they file under.
# Not an exhaustive list of tragedy -- it cannot be -- but the categories that recur at the
# top of a most-read ranking, so the common case is refused by construction rather than by
# somebody noticing.
NEVER_A_PRODUCT: tuple[str, ...] = (
    "death", "died", "killed", "shooting", "attack", "disaster", "earthquake", "hurricane",
    "war", "invasion", "massacre", "crash", "outbreak", "verdict", "trial", "arrest",
    "indictment", "scandal", "obituary", "funeral", "memorial",
)

CLASSIFY_SYSTEM = (
    "You file cultural topics into a fixed set of domains for a craft company's demand "
    "radar. You are filing, not recommending: a topic being popular says nothing about "
    "whether anything should be made from it, and you never say what should be made."
)

MAX_TOPICS_PER_CALL = 40
CLASSIFY_MAX_TOKENS = 1500
# Routed rather than named. Cheap tier is correct here and the reason is the question rather
# than the price: filing against a closed vocabulary is extraction, and the answer would not
# improve on a stronger model -- the domains are disjoint and a topic either is a television
# series or is not. Stated because under a quality-first policy every cheap-tier choice has
# to survive being asked why.
TASK = "topic_filing"


class ClassificationRefused(ValueError):
    """An answer that is not a filing decision from the closed vocabulary."""


def prompt(topics: list[str]) -> str:
    return (
        "File each topic into exactly one domain, or `unplaced` if none fits.\n"
        "Domains: " + ", ".join(DOMAINS) + ", " + UNPLACED + "\n\n"
        "Reply with a single JSON object mapping each topic exactly as given to its domain, "
        "and nothing else.\n\nTopics:\n"
        + "\n".join(f"- {t}" for t in topics))


def sensitive(topic: str) -> bool:
    """Whether a topic is one of the recurring kinds that must never become a product."""
    words = set(topic.replace("_", " ").lower().replace("(", " ").replace(")", " ").split())
    return bool(words & set(NEVER_A_PRODUCT))


def parse(text: str, topics: list[str]) -> dict:
    """Read the filing, refusing anything outside the vocabulary or about another topic."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise ClassificationRefused(
            f"the model did not answer with JSON: {body[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise ClassificationRefused(f"expected one object, got {type(parsed).__name__}")

    allowed = set(DOMAINS) | {UNPLACED}
    asked = set(topics)
    out: dict[str, str] = {}
    for topic, domain in parsed.items():
        if topic not in asked:
            raise ClassificationRefused(
                f"{topic!r} was not asked about. A filing about a topic nobody raised is a "
                f"topic the model invented, and it would enter the radar as an observation")
        if domain not in allowed:
            raise ClassificationRefused(
                f"{domain!r} is not a domain. The vocabulary is closed because an open one "
                f"accepts 'culture', and a radar whose finding is 'culture' has found "
                f"nothing: {sorted(allowed)}")
        out[topic] = domain
    return out


def classify(topics: list[str], *, provider=None, db=None) -> dict:
    """File a batch of topics, and say plainly when nothing could be filed.

    Batched because filing is cheap per topic and a call per topic is forty calls. Unlike
    gallery analysis -- where a batch would invite an answer about the set -- each topic here
    is filed independently and named in the answer, so a batch cannot blur them.
    """
    from ..gateway import anthropic as gw

    topics = [t for t in topics if t][:MAX_TOPICS_PER_CALL]
    if not topics:
        return {"filed": {}, "sensitive": [], "reason": "no topics to file"}

    provider = provider or gw.provider_for(TASK)
    flagged = sorted(t for t in topics if sensitive(t))
    estimate = 0.0

    try:
        if db is not None:
            estimate = gw.check_budget(
                db, model=provider.model, input_tokens=len(prompt(topics)) // 4,
                max_tokens=CLASSIFY_MAX_TOKENS)["estimate_cad"]
        response = provider.complete(CLASSIFY_SYSTEM, prompt(topics),
                                     max_tokens=CLASSIFY_MAX_TOKENS)
    except (PermanentError, TransientError) as exc:
        return {"filed": {}, "sensitive": flagged, "reason": str(exc)[:300],
                "note": ("nothing was filed and the reason is above. An unfiled topic list "
                         "is not an empty culture")}

    if db is not None:
        from ..finance import spend_report

        spend_report.record(
            db, agent="market_radar",
            amount_cad=round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                             + response.output_tokens * provider.cost_per_1k_output_cad
                             / 1000, 8),
            estimated_cad=estimate, purpose=TASK, provider="anthropic",
            model=provider.model, department="culture",
            tokens_in=response.input_tokens, tokens_out=response.output_tokens,
            detail={"topics": len(topics), "price_basis": "assumed"})

    filed = parse(response.text, topics)
    placed = {t: d for t, d in filed.items() if d != UNPLACED}
    return {
        "filed": filed,
        "placed": placed,
        "unplaced": sorted(t for t, d in filed.items() if d == UNPLACED),
        "sensitive": flagged,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "note": ("filing is not permission. `culture.rights` decides whether anything may be "
                 "made from a topic, separately and afterwards, and a domain is a filing "
                 "decision rather than a legal one"),
        "sensitive_note": ("topics naming a death, a disaster or a trial are flagged and "
                           "never become products whatever domain they file under. The most-"
                           "read article on a given day is frequently one of those"),
    }
