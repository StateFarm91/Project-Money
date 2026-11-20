"""The rapid-response cell, and the one sentence that makes it safe.

Requirement 141. A cell for time-sensitive cultural opportunities is obviously useful and
obviously dangerous, and the spec resolves it in a single line worth quoting exactly: *speed
comes from prioritization and parallelism, not lower standards.*

That line is the whole module. Everything a rapid cell is allowed to accelerate is work that
can be done sooner or in parallel — research, the concept tournament, feasibility, creative
prototyping. Everything it may not touch is a gate: CIR validation, Product Truth, Creative
Parity, policy, spend and release. The distinction is not a matter of degree, and it is stated
as two closed lists rather than a principle, because a principle under deadline pressure
becomes a conversation about what counts as lowering a standard.

The pressure is real and it is exactly backwards from where it feels: the cell exists because
a window is closing, so the argument for skipping a gate is strongest precisely when the
consequence of skipping it is worst. A product rushed into a closing window is the one with
the least time for a correction round afterwards.
"""
from __future__ import annotations

from ..improve.governance import PROTECTED_GATES

# What speed is allowed to come from.
MAY_ACCELERATE: dict[str, str] = {
    "research": "start it now instead of at the next planning cycle",
    "concept_tournament": "run more concepts in parallel rather than fewer rounds",
    "feasibility": "compile the twin for several candidates at once",
    "creative_prototyping": "prototype in parallel instead of sequentially",
    "asset_drafting": "draft assets while the pattern is still certifying",
    "listing_copy": "write it early; it still passes every claim gate before it is used",
}

# What it may never touch. Named individually so a refusal says which gate and why.
MAY_NEVER_BYPASS: dict[str, str] = {
    "cir_validation": "a pattern that was not validated is not a pattern, it is a document",
    "product_truth": "a claim nobody checked is a claim, and a customer will check it",
    "creative_parity": "the visual standard does not drop because the window is closing",
    "policy_gate": "the rights router is the reason this cell is allowed near culture at all",
    "spend_ceilings": "a closing window is the most persuasive possible argument for an "
                      "unbudgeted spend, which is why the ceiling is in code",
    "release_gates": "the certificate is what a release is; issuing it early issues nothing",
    "reverse_compilation": "the document and the design must still agree",
    "shadow_mode": "a cultural window does not graduate a phase",
}


class RapidRefused(Exception):
    """An attempt to buy speed with a standard."""


def check(action: str, *, accelerates: str = "", bypasses: tuple[str, ...] = ()) -> dict:
    """Whether the rapid cell may do this.

    Refuses on the bypass list first: an action that both accelerates something legitimate
    and skips a gate is the shape this refusal exists for, and reporting the legitimate half
    would be reporting the cover story.
    """
    attempted = [g for g in bypasses if g in MAY_NEVER_BYPASS]
    if attempted:
        gate = attempted[0]
        raise RapidRefused(
            f"{action!r} bypasses {gate}: {MAY_NEVER_BYPASS[gate]}. Speed comes from "
            f"prioritization and parallelism, not lower standards (#141) — and the argument "
            f"for skipping a gate is strongest exactly when the consequence is worst, "
            f"because a product rushed into a closing window has the least time left for a "
            f"correction round")
    unknown_bypass = [g for g in bypasses if g not in MAY_NEVER_BYPASS]
    if unknown_bypass:
        # Named gates only. An unnamed one is either not a gate, in which case say what it
        # accelerates, or a gate nobody listed, which is worse than either.
        raise RapidRefused(
            f"{sorted(unknown_bypass)} are not named gates: {sorted(MAY_NEVER_BYPASS)}. "
            f"A gate this cell can skip without the skip being named is a gate that is "
            f"already gone")
    if accelerates not in MAY_ACCELERATE:
        raise RapidRefused(
            f"{accelerates!r} is not something this cell may accelerate: "
            f"{sorted(MAY_ACCELERATE)}. Everything on that list can be done sooner or in "
            f"parallel; everything off it is a gate or an invention")
    return {"action": action, "accelerates": accelerates,
            "how": MAY_ACCELERATE[accelerates],
            "permitted": True,
            "gates_unchanged": sorted(MAY_NEVER_BYPASS)}


def describe() -> dict:
    return {
        "may_accelerate": MAY_ACCELERATE,
        "may_never_bypass": MAY_NEVER_BYPASS,
        # The cell's forbidden list is a superset of the department-wide protected gates, so
        # a rapid cell can never be a route around the Improvement Department's boundary.
        "covers_protected_gates": sorted(set(PROTECTED_GATES) & set(MAY_NEVER_BYPASS)),
        "rule": "speed comes from prioritization and parallelism, not lower standards (#141)",
    }
