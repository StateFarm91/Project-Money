"""Concept strength against the category, scored the same way on both sides (#125).

#125 makes the category's top decile the flagship target, and `standard.aspiration` already
computes a top decile from benchmark scores -- but nothing produced a benchmark score or a
concept score, so the pre-engineering check could only ever read UNMEASURED. This is the
scorer, and it is deterministic on purpose: a strength number that means something different
on each side of the comparison is not a comparison.

**What it measures.** "What would make this the most memorable result on the page?" is a
question about distinctiveness against the page. Every observed listing in a pod and every
concept are described as blinded cards in the same closed vocabulary (`creative.blinded`:
form, occasion, recipient, feeling). A card's strength is how far it stands from the rest of
the pod's cards -- the mean share of those fields on which it differs from each other card,
so a listing that is the fourth festive Christmas stocking scores low and one that is the only
tender new-baby stocking scores high. Benchmark listings are scored against the other
benchmark listings; a concept is scored against all of them.

**What it does not measure.** Photography, thumbnail readability and finished presentation
are judged downstream where the product exists (#75 parity, #126 grid). A title that does not
state enough to describe a card is not scored rather than defaulted, and fewer than
`standard.aspiration`'s five scores is reported, not estimated. A score a model jury judged is
always preferred when a brief carries one with its judge named.
"""
from __future__ import annotations

SOURCE = "deterministic:card_distinctiveness_v1"
_FIELDS = ("form", "occasion", "recipient", "feeling")


def _cards(db, pod: str) -> list:
    from . import blinded

    out = []
    for listing in blinded.benchmark_cards(db):
        if listing.get("pod") != pod:
            continue
        try:
            out.append(blinded.from_listing(listing))
        except (blinded.Unreadable, blinded.NotComparable):
            continue
    # Every observed seller, not just the anchor: the category is the page.
    return out


def _distinct(card, others: list) -> float | None:
    if not others:
        return None
    diffs = [sum(1 for f in _FIELDS if getattr(card, f) != getattr(o, f)) / len(_FIELDS)
             for o in others]
    return round(sum(diffs) / len(diffs), 4)


def benchmark_scores(db, pod: str) -> list[float]:
    cards = _cards(db, pod)
    return [s for i, c in enumerate(cards)
            if (s := _distinct(c, cards[:i] + cards[i + 1:])) is not None]


def concept_score(db, concept) -> dict:
    """The concept's distinctiveness against every observed card in its pod."""
    from . import blinded

    try:
        card = blinded.from_concept(concept)
    except blinded.NotComparable as exc:
        return {"score": None, "source": SOURCE, "why": str(exc)}
    cards = _cards(db, concept.pod)
    score = _distinct(card, cards)
    return {"score": score, "source": SOURCE, "against": len(cards),
            "why": "" if score is not None else
            f"no readable benchmark listing in {concept.pod!r} to stand apart from"}
