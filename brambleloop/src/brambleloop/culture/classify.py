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


def _outcome_unknown(exc: BaseException) -> bool:
    """Whether this failed call's billing is UNKNOWN (OPUS2I C-4).

    In a job scope: the guard's own record for the call is UNCERTAIN. Outside one (a probe, a
    test): the exception is one `gateway.anthropic._classify_failure` calls UNCERTAIN."""
    from ..gateway import paid_calls
    from ..gateway import providers as gw   # F-091: the vendor-neutral boundary

    scope = paid_calls._SCOPE.get()
    if scope is not None:
        key = (scope.last_call or {}).get("paid_call_key")
        if not key:
            return False                          # the guard never reached the provider
        with scope.db.session() as s:
            row = s.get(paid_calls.PaidCallRecord, key)
            return row is not None and row.outcome == paid_calls.UNCERTAIN
    return gw.classify_failure(exc) == paid_calls.UNCERTAIN


def classify(topics: list[str], *, provider=None, db=None) -> dict:
    """File a batch of topics, and say plainly when nothing could be filed.

    Batched because filing is cheap per topic and a call per topic is forty calls. Unlike
    gallery analysis -- where a batch would invite an answer about the set -- each topic here
    is filed independently and named in the answer, so a batch cannot blur them.
    """
    from ..gateway import providers as gw          # F-091: the vendor-neutral boundary

    topics = [t for t in topics if t][:MAX_TOPICS_PER_CALL]
    if not topics:
        return {"filed": {}, "sensitive": [], "reason": "no topics to file"}

    provider = provider or gw.for_task(TASK)
    flagged = sorted(t for t in topics if sensitive(t))
    estimate = 0.0
    # The reservation this call holds while it runs, released below whatever happens. The
    # `agent` is what makes the daily ceiling bind: this spends as `market_radar`, and until
    # 2026-09-25 that agent's CA$4.00/day was checked by nothing on this path.
    reservation = None

    sent = False
    try:
        user = prompt(topics)           # built before the call: a bug here is never "sent"
        if db is not None:
            budget = gw.check_budget(
                db, model=provider.model, input_tokens=len(user) // 4,
                max_tokens=CLASSIFY_MAX_TOKENS, agent="market_radar", purpose=TASK)
            estimate = budget["estimate_cad"]
            reservation = budget["reservation_id"]
        sent = True                     # from here on the request may have reached the provider
        response = provider.complete(CLASSIFY_SYSTEM, user, max_tokens=CLASSIFY_MAX_TOKENS)
    except (PermanentError, TransientError) as exc:
        if db is not None:
            gw.release_reservation(db, reservation)
        return {"filed": {}, "sensitive": flagged, "reason": str(exc)[:300],
                "note": ("nothing was filed and the reason is above. An unfiled topic list "
                         "is not an empty culture")}
    except Exception as exc:  # noqa: BLE001 - classified by outcome below, never swallowed blind
        # P1-CULTURE-SWEEP-TIMEOUT, widened by review OPUS2G C-2: once the request was sent, a
        # failure that is not a provider refusal (handled above) is UNCERTAIN -- a timeout, an
        # unreadable 200 (ValueError), a reset or incomplete read -- exactly the set
        # `gateway.anthropic._classify_failure` calls UNCERTAIN. Whether it billed is UNKNOWN,
        # and UNKNOWN is never zero: it is counted once at the reservation's estimate, as
        # `ModelGateway._billing` counts it. The paid-call intent stays UNCERTAIN (F-307/F-339)
        # so nothing is re-sent; the attempt files nothing and the sweep goes on. A failure
        # before anything was sent (the budget check, a bug) is not billed and is re-raised.
        # Review OPUS2I C-4: "sent" alone is not proof. Inside a job the paid-call guard is the
        # authority -- it writes UNCERTAIN only for a call it actually made -- so the spend is
        # billed only when that record says so; a write-ahead DB error or a provider-side bug
        # before the send has no UNCERTAIN record and is re-raised, visible, unbilled.
        if not sent or not _outcome_unknown(exc):
            if db is not None:
                gw.release_reservation(db, reservation)
            raise
        if db is not None:
            from ..finance import spend_report
            from ..gateway import paid_calls

            gw.release_reservation(db, reservation, actual_cad=estimate)
            spend_report.record(
                db, agent="market_radar", amount_cad=estimate, estimated_cad=estimate,
                purpose=TASK, provider="anthropic", model=provider.model,
                department="culture",
                detail={"topics": len(topics), "price_basis": "assumed",
                        "billing": "unknown_counted_at_estimate",
                        "cost_basis_note": ("the classifier call failed after it was sent "
                                            f"({type(exc).__name__}); whether it billed is "
                                            "UNKNOWN and counted at the reservation "
                                            "estimate, never as zero"),
                        **paid_calls.ledger_note()})
        return {"filed": {}, "sensitive": flagged, "unresolved": True,
                "reason": f"classifier call outcome unknown ({type(exc).__name__}): {exc}"[:300],
                "note": ("nothing was filed: the call's outcome is unknown, so it is counted "
                         "at its estimate and not re-sent. An unfiled topic list is not an "
                         "empty culture")}

    if db is not None:
        from ..finance import spend_report

        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        gw.release_reservation(db, reservation, actual_cad=cost)
        spend_report.record(
            db, agent="market_radar", amount_cad=cost,
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
