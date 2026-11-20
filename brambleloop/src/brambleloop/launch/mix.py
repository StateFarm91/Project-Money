"""Launch-mix evaluation (F-366) and autonomous category rebalancing (F-370) -- W4-INTELREC C06.

F-366: "the launch-catalogue optimizer must explicitly consider baby/children's products
alongside adult garments, home/decor, seasonal and accessories rather than treating kids as a
later afterthought." The optimizer is `radar.opportunity.select_portfolio` (section 33's
structural constraints, greedy by score then repaired). It knew categories, not these five
segments. `optimize` runs it, measures the result by segment
(`creative.children.segment`), and repairs it the same way the radar repairs its own
constraints: at least one children's product when an eligible one exists, and no segment above
`MAX_SEGMENT_SHARE` of the mix -- each swap evicting only a pick whose removal breaks none of
section 33's constraints, and each recorded.

F-370: "after sufficient live evidence exists, Brambleloop may increase or reduce the share of
baby/children's products based on measured performance, while preserving owner-set brand and
quality constraints." `rebalance` takes measured per-segment outcomes (visits and orders) and
proposes bounded share changes: nothing below `MIN_VISITS_PER_SEGMENT` measured visits per
segment (UNMEASURED, no change); at most `MAX_STEP` points per review; never outside the
owner's minimum/maximum share for a segment. It recommends; nothing here changes the catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..creative.children import PRIORITY_FAMILY, SEGMENTS, segment

MAX_SEGMENT_SHARE = 0.5
MIN_PER_SEGMENT = {PRIORITY_FAMILY: 1}
MIN_VISITS_PER_SEGMENT = 500
MAX_STEP = 0.10
UNMEASURED = "UNMEASURED"


def segment_of(seed) -> str:
    return segment(category=seed.category, title=seed.title, season=seed.season)


def evaluate(selected) -> dict:
    """The mix by segment: counts, shares and what is absent."""
    n = len(selected) or 1
    counts = {s: 0 for s in SEGMENTS}
    for c in selected:
        counts[segment_of(c.seed)] = counts.get(segment_of(c.seed), 0) + 1
    return {"counts": counts, "shares": {s: round(v / n, 3) for s, v in counts.items()},
            "absent": [s for s in SEGMENTS if counts[s] == 0],
            "children_considered": True,
            "children_in_mix": counts[PRIORITY_FAMILY]}


def optimize(*, target: int = 10, today=None, scored=None) -> dict:
    """`select_portfolio`, then repaired so every segment is weighed (F-366)."""
    from ..radar import opportunity as O

    port = O.select_portfolio(scored, target=target, today=today)
    selected = list(port.selected)
    before = evaluate(selected)
    pool = sorted(port.rejected, key=lambda c: (-c.score, c.seed.slug))
    reasons: list[str] = []

    def eligible(c) -> bool:
        return not c.seed.is_bundle and c.seed.risk_class in ("A", "B")

    def swap_in(candidate, *, why: str, protect: str | None = None) -> bool:
        held = O._check(selected)
        for victim in sorted(selected, key=lambda c: c.score):
            if victim.seed.is_bundle or segment_of(victim.seed) == protect:
                continue
            trial = [c for c in selected if c is not victim] + [candidate]
            after = O._check(trial)
            if all(after[k] or not held[k] for k in held):
                selected.remove(victim)
                selected.append(candidate)
                reasons.append(f"swapped {victim.slug} (score {victim.score}) for "
                               f"{candidate.slug} (score {candidate.score}): {why}")
                return True
        reasons.append(f"could not add {candidate.slug} ({why}) without breaking a section-33 "
                       f"constraint")
        return False

    for seg, minimum in MIN_PER_SEGMENT.items():
        have = sum(1 for c in selected if segment_of(c.seed) == seg)
        for cand in [c for c in pool if eligible(c) and segment_of(c.seed) == seg]:
            if have >= minimum:
                break
            if swap_in(cand, why=f"the {seg} segment had {have} of a minimum {minimum}",
                       protect=seg):
                have += 1
                pool.remove(cand)
        if have < minimum:
            reasons.append(f"{seg}: no eligible candidate reached the mix (minimum {minimum})")

    cap = max(1, int(MAX_SEGMENT_SHARE * max(len(selected), 1)))
    for seg in SEGMENTS:
        over = [c for c in selected if segment_of(c.seed) == seg]
        while len(over) > cap:
            others = [c for c in pool if eligible(c) and segment_of(c.seed) != seg]
            if not others:
                reasons.append(f"{seg} holds {len(over)} of {len(selected)} with no other "
                               f"segment's candidate to swap in")
                break
            cand = others[0]
            pool.remove(cand)
            weakest = min(over, key=lambda c: c.score)
            trial = [c for c in selected if c is not weakest] + [cand]
            held, after = O._check(selected), O._check(trial)
            if all(after[k] or not held[k] for k in held):
                selected.remove(weakest)
                selected.append(cand)
                reasons.append(f"swapped {weakest.slug} for {cand.slug}: {seg} was above "
                               f"{MAX_SEGMENT_SHARE:.0%} of the mix")
                over.remove(weakest)
            else:
                continue
    after = evaluate(selected)
    return {"before": before, "after": after, "reasons": reasons,
            "selected": [c.slug for c in sorted(selected, key=lambda c: (-c.score, c.slug))],
            "constraints_met": O._check(selected),
            "basis": "radar.opportunity.select_portfolio + segment repair (F-366)"}


@dataclass(frozen=True)
class OwnerConstraints:
    """Owner-set bounds the rebalancer may never cross (F-370)."""

    min_share: dict = field(default_factory=lambda: {PRIORITY_FAMILY: 0.10})
    max_share: dict = field(default_factory=lambda: {PRIORITY_FAMILY: 0.40})


def rebalance(current_shares: dict, outcomes: dict, *,
              owner: OwnerConstraints | None = None) -> dict:
    """Proposed shares from measured per-segment conversion, bounded (F-370).

    `outcomes`: segment -> {"visits": int, "orders": int} measured from live listings."""
    owner = owner or OwnerConstraints()
    measured = {s: o for s, o in (outcomes or {}).items()
                if (o.get("visits") or 0) >= MIN_VISITS_PER_SEGMENT and o.get("orders") is not None}
    if len(measured) < 2:
        return {"status": UNMEASURED, "proposed": dict(current_shares), "changes": {},
                "why": (f"{len(measured)} segment(s) carry {MIN_VISITS_PER_SEGMENT}+ measured "
                        f"visits; rebalancing needs at least two to compare")}
    conv = {s: o["orders"] / o["visits"] for s, o in measured.items()}
    mean = sum(conv.values()) / len(conv)
    proposed = dict(current_shares)
    changes = {}
    for s, c in conv.items():
        cur = float(current_shares.get(s, 0.0))
        rel = (c - mean) / mean if mean else 0.0
        step = max(-MAX_STEP, min(MAX_STEP, round(rel * MAX_STEP, 3)))
        new = cur + step
        lo, hi = owner.min_share.get(s, 0.0), owner.max_share.get(s, 1.0)
        new = round(max(lo, min(hi, new)), 3)
        if new != cur:
            changes[s] = {"from": cur, "to": new, "conversion": round(c, 4),
                          "bounded_by_owner": new in (lo, hi) and new != round(cur + step, 3)}
        proposed[s] = new
    # Not renormalised: a rescale could push a segment back across an owner bound. The total
    # is reported; the catalogue plan fills the remainder (or trims) from the unmeasured rest.
    return {"status": "PROPOSED", "proposed": proposed,
            "total_share": round(sum(proposed.values()), 3), "changes": changes,
            "owner_constraints": {
                "min_share": dict(owner.min_share), "max_share": dict(owner.max_share)},
            "note": "a recommendation: nothing here adds, removes or reprices a product"}
