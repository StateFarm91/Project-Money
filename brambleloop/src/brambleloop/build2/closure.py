"""The Build 2 closure matrix: every one of the 320 requirements in exactly one final state.

The registry's five statuses describe *work*: covered, partial, missing, owner-gated,
data-gated. A closeout needs a different vocabulary, one that describes *why nothing more can
be done here* -- and it has to be computed from evidence, not copied from the status, because
the status is the claim under test. The owner set the vocabulary on 2026-09-26 and it has four
values only:

    COMPLETE+PROVEN    the note or `proof` names a module that exists in the package and a
                       test file that exercises it. "covered" alone is not enough: sixty-seven
                       covered rows named no module when this matrix was first computed.
    OWNER-GATED        the remaining work waits on something only the owner can do -- a
                       credential, a purchase, a surface, an approval -- and the gate it waits
                       on is checkable (`executor.GATES`) and closed.
    DATA-GATED         the remaining work needs customers, orders or traffic that cannot exist
                       before launch. Parked on the `customers` gate or registered data_gated.
    EXTERNAL-BLOCKED   a third party refuses the capability and no honest route exists: Etsy
                       returns HTTP 403 to every automated reader of its policy and search
                       pages (B-268, B-500), and no image provider has produced a
                       stitch-faithful photograph of a certified structure (VISUAL_V1_GRADUATION,
                       0 of 16; VISUAL_BENCH2, 0 of 7). Those are not owner actions and not
                       data; they are the world saying no, and the matrix says so in those words.

Anything else is OPEN: executable work Build 2 still owes, or a covered row whose proof
cannot be found. The closeout bar is `open == 0`. A gate that has *opened* (checked live
against the database) returns its requirements to OPEN rather than leaving them parked on a
reason that no longer holds -- a closure that could not reopen would be a filing cabinet.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import executor, maturity, requirements as reg

COMPLETE_PROVEN = "COMPLETE+PROVEN"
OWNER_GATED = "OWNER-GATED"
DATA_GATED = "DATA-GATED"
EXTERNAL_BLOCKED = "EXTERNAL-BLOCKED"
OPEN = "OPEN"
FINAL_STATES = (COMPLETE_PROVEN, OWNER_GATED, DATA_GATED, EXTERNAL_BLOCKED)

# Each executor gate is one of the three parked kinds. A gate missing from this table is a
# refusal, not a default: a new gate must say what kind of waiting it is.
DATA_GATES = frozenset({"customers"})
EXTERNAL_GATES = {
    "rendered_pages": (
        "etsy.com/legal, help.etsy.com and Etsy search pages return HTTP 403 to every honest "
        "automated reader (DECISION_LOG B-268, B-500; re-proven 2026-09-26 with two "
        "independent fetchers). Spoofing a browser is refused. A person can read the page and "
        "record it (POST /api/policy/snapshot)."),
    "model_bearing_render": (
        "no image provider has rendered a certified crochet structure faithfully enough to "
        "pass the deterministic stitch instrument: 0 of 16 gpt-image-1.5 draws "
        "(research/VISUAL_V1_GRADUATION.md, 4cf6959) and 0 of 7 gemini draws "
        "(research/VISUAL_BENCH2.md, ad81e30). The blind deterministic chain passed; the "
        "provider is the ceiling. Frozen as an external blocker; no further paid draws."),
}
OWNER_GATES = frozenset({
    "benchmark_observation", "model_provider", "etsy_shop", "etsy_api", "tester_roster",
    "image_generation", "canonical_model", "benchmark_purchases", "offsite_storage",
    "owned_surfaces", "live_listings", "physical_proof", "second_market_benchmark",
    "culture_feed", "ad_authority", "image_vision",
    # Certification C-40: the owner pastes Shop Manager Insights readings; the owner rules on
    # the browser/vision acceptance wording. Both need a person, so both are owner gates.
    "insights_access", "acceptance_ruling",
    # #195: deploying Build 2 for an unattended production window is the owner's call.
    "production_window",
})


class ClosureRefused(Exception):
    pass


def kind_of(gate_key: str) -> str:
    if gate_key in DATA_GATES:
        return DATA_GATED
    if gate_key in EXTERNAL_GATES:
        return EXTERNAL_BLOCKED
    if gate_key in OWNER_GATES:
        return OWNER_GATED
    raise ClosureRefused(
        f"gate {gate_key!r} is not classified as owner, data or external waiting; a gate "
        f"whose kind nobody stated would be filed wherever flattered the count")


def _known_gates() -> frozenset[str]:
    return frozenset(g.key for g in executor.GATES)


def proof_of(requirement: reg.Requirement) -> dict:
    """The evidence a covered row rests on: modules that exist and tests that name them."""
    modules = maturity.modules_named(requirement.note + " " + requirement.proof)
    tests = sorted({tok for tok in requirement.proof.split()
                    if tok.startswith("tests/") and tok.endswith(".py")})
    existing = [m for m in modules if maturity._importable(m)]
    tested = [m for m in existing if maturity._tested(m)]
    # Certification (C-41/C-43/C-59): existing and tested is not enough. At least one named
    # module must be reached from a runtime root -- imported by the handlers, worker or API
    # and referenced by something there -- or the claim is the 63f2493 failure again.
    from . import reachability

    reach = {m: reachability.reached(m) for m in existing if m.endswith(".py")}
    reached = [m for m, v in reach.items() if v["reached"]]
    return {"modules": modules, "existing": existing, "tested": tested, "tests": tests,
            "reached": reached,
            "unreached": {m: v["why"] for m, v in reach.items() if not v["reached"]},
            "proven": bool(existing) and (bool(tested) or bool(tests)) and bool(reached)}


def classify(requirement: reg.Requirement, *, gate_open: dict[str, bool] | None = None) -> dict:
    """One requirement -> one state, with the reason written beside it."""
    gate_open = gate_open or {}
    row = {"id": requirement.id, "title": requirement.title, "section": requirement.section,
           "status": requirement.status, "gate": None, "gate_open": None, "why": ""}
    if requirement.status == reg.COVERED and requirement.proof.startswith("directive:"):
        # Three rows of v1.4.3 instruct the auditor (merge order, canonical reconciliation);
        # there is nothing to build and a module would be a fiction. They close as followed,
        # with the evidence written in `proof`, rather than inflating either count.
        row["state"] = COMPLETE_PROVEN
        row["proof"] = {"modules": [], "existing": [], "tested": [], "tests": [], "proven": True,
                        "directive": requirement.proof}
        row["why"] = "process directive to the auditor, followed: " + requirement.proof[len("directive:"):].strip()
        return row
    if requirement.status == reg.COVERED:
        proof = proof_of(requirement)
        row["proof"] = proof
        if proof["proven"]:
            row["state"] = COMPLETE_PROVEN
            row["why"] = f"module {proof['existing'][0]} exists and is tested"
        else:
            row["state"] = OPEN
            row["why"] = ("covered, but no module the note or `proof` names exists, is "
                          "tested and is reached from the running system; the claim is "
                          "unverified until one is")
        return row
    if requirement.status == reg.DATA_GATED:
        # Only the data may be the gate: the machinery that will read the data must already
        # exist. A data-gated row naming no module that exists was a requirement nobody had
        # built, filed where the missing data excused it (certification defect C-39).
        proof = proof_of(requirement)
        row["proof"] = proof
        if not proof["existing"]:
            row["state"] = OPEN
            row["why"] = ("data_gated, but no module the note or `proof` names exists: the "
                          "machinery that will use the data is owed now")
            return row
        if not proof["reached"]:
            # C-59: machinery nothing runs reads nothing on the day the data arrives.
            row["state"] = OPEN
            row["why"] = ("data_gated, but the machinery it names is not reached from the "
                          "running system: " + "; ".join(f"{m}: {w}" for m, w in
                                                         proof["unreached"].items())[:300])
            return row
        row["state"] = DATA_GATED
        row["why"] = (f"machinery exists ({proof['existing'][0]}); needs customers, orders or "
                      f"traffic that cannot exist before launch")
        return row
    gate = executor.gate_for(requirement.id)
    if requirement.status == reg.OWNER_GATED and gate is None:
        row["state"] = OPEN
        row["why"] = "owner_gated with no checkable gate -- nobody can say what would open it"
        return row
    if gate is None:
        row["state"] = OPEN
        row["why"] = "executable work Build 2 still owes"
        return row
    row["gate"] = gate
    # C-59: a partly built row parked on a gate must have its built half running. When the
    # note or `proof` names machinery that exists, at least one module of it must be reached.
    if requirement.status != reg.OWNER_GATED:
        proof = proof_of(requirement)
        row["proof"] = proof
        if proof["existing"] and not proof["reached"]:
            row["state"] = OPEN
            row["why"] = (f"parked on {gate}, but the machinery it names is not reached from "
                          f"the running system: "
                          + "; ".join(f"{m}: {w}" for m, w in proof["unreached"].items())[:300])
            return row
    kind = kind_of(gate)
    is_open = gate_open.get(gate)
    row["gate_open"] = is_open
    if is_open:
        row["state"] = OPEN
        row["why"] = f"gate {gate} has opened; the remaining work is no longer parked"
        return row
    row["state"] = kind
    if kind == EXTERNAL_BLOCKED:
        row["why"] = EXTERNAL_GATES[gate]
    elif kind == DATA_GATED:
        row["why"] = f"parked on {gate}: needs real customers"
    else:
        row["why"] = f"parked on owner gate {gate}"
    return row


def matrix(db=None, *, env=None) -> dict:
    """The whole registry classified; `open` is the closeout remainder."""
    unknown = sorted({g for g in (executor.gate_for(r.id) for r in reg.load()) if g}
                     - _known_gates() - set(EXTERNAL_GATES) - DATA_GATES - OWNER_GATES)
    if unknown:
        raise ClosureRefused(f"requirements parked on gates the executor cannot check: {unknown}")
    gate_open: dict[str, bool] = {}
    if db is not None:
        gate_open = {k: bool(v.get("open")) for k, v in executor.gate_states(db, env).items()}
    rows = [classify(r, gate_open=gate_open) for r in reg.load()]
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in FINAL_STATES + (OPEN,)}
    by_section: dict[str, dict] = {}
    for r in rows:
        sec = by_section.setdefault(r["section"], {s: 0 for s in FINAL_STATES + (OPEN,)})
        sec[r["state"]] += 1
    open_rows = [r for r in rows if r["state"] == OPEN]
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(rows),
        "counts": counts,
        "closed_out": counts[OPEN] == 0,
        "gates_checked_live": db is not None,
        "external_blockers": {k: v for k, v in EXTERNAL_GATES.items()},
        "by_section": by_section,
        "open": open_rows,
        "rows": rows,
    }
