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

from . import executor, maturity, reachability, requirements as reg

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
    # C-64: reading receipts needs a scope only the owner can grant in a browser.
    "transactions_r",
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
    # C-65: a runtime root (runtime/release.py, app/main.py ...) is reached by definition, so
    # naming one beside a library proved nothing about the library. The roots count only for
    # a row whose machinery *is* a root; otherwise a named library must itself be live.
    libs = {m: v for m, v in reach.items() if m not in reachability.ROOTS}
    reached = [m for m, v in (libs or reach).items() if v["reached"]]
    return {"modules": modules, "existing": existing, "tested": tested, "tests": tests,
            "reached": reached,
            "unreached": {m: v["why"] for m, v in reach.items() if not v["reached"]},
            "proven": bool(existing) and (bool(tested) or bool(tests)) and bool(reached)}


def classify(requirement: reg.Requirement, *, gate_open: dict[str, bool] | None = None) -> dict:
    """One requirement -> one state, with the reason written beside it.

    `gate_open=None` means nobody checked the gates (no database): a parked row then says so
    in its `why` rather than reading as a gate verified closed (C-65)."""
    gate_checked = gate_open is not None
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
    # C-65 (Codex P01): only an EXPLICIT park -- `parked_on` written by whoever last audited
    # the row -- parks it. The executor's gate table lists whole requirements a gate once
    # stood in front of; when an audit reopens a row it clears `parked_on`, and the table
    # must not quietly re-park it. Twenty reopened rows read as gated that way at 9434c53.
    # A row registered owner_gated is parked whole, and the registry forbids `parked_on` on
    # it, so its gate is the table's. A PARTIAL row is parked only by its own `parked_on`.
    table_gate = executor.gate_for(requirement.id)
    row["gate_table"] = table_gate
    if requirement.status == reg.OWNER_GATED:
        gate = table_gate
        if gate is None:
            row["state"] = OPEN
            row["why"] = "owner_gated with no checkable gate -- nobody can say what would open it"
            return row
    else:
        gate = (requirement.parked_on or "").strip() or None
    if gate is None:
        row["state"] = OPEN
        row["why"] = ("executable work Build 2 still owes"
                      + (f" (reopened: no explicit park; the gate table's {table_gate} does "
                         "not park a row by itself)" if table_gate else ""))
        return row
    if gate not in _known_gates() | set(EXTERNAL_GATES) | DATA_GATES | OWNER_GATES:
        raise ClosureRefused(f"requirement {requirement.id} is parked on {gate!r}, which is "
                             f"not a gate the executor can check")
    row["gate"] = gate
    # C-59: a partly built row parked on a gate must have its built half running. When the
    # note or `proof` names machinery that exists, at least one module of it must be reached.
    # C-65: that includes rows registered owner_gated. "Waiting on the owner" excuses the
    # owner's half only; a row whose built half names machinery nothing runs would otherwise
    # sit parked on a gate while the thing that should read the gate's input does not exist
    # in the running system either.
    proof = proof_of(requirement)
    row["proof"] = proof
    if proof["existing"] and not proof["reached"]:
        row["state"] = OPEN
        row["why"] = (f"parked on {gate}, but the machinery it names is not reached from "
                      f"the running system: "
                      + "; ".join(f"{m}: {w}" for m, w in proof["unreached"].items())[:300])
        return row
    kind = kind_of(gate)
    is_open = gate_open.get(gate) if gate_checked else None
    row["gate_open"] = is_open
    row["gate_checked"] = gate_checked
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
    if not gate_checked:
        row["why"] += (" (gate state NOT checked live: no database was given, so this is the "
                       "registry's parking, not a verified-closed gate)")
    return row


@reachability._graph_boundary
@maturity._with_test_import_snapshot
def matrix(db=None, *, env=None) -> dict:
    """The whole registry classified; `open` is the closeout remainder."""
    unknown = sorted({g for g in (executor.gate_for(r.id) for r in reg.load()) if g}
                     - _known_gates() - set(EXTERNAL_GATES) - DATA_GATES - OWNER_GATES)
    if unknown:
        raise ClosureRefused(f"requirements parked on gates the executor cannot check: {unknown}")
    gate_open: dict[str, bool] | None = None
    gate_error = None
    if db is not None:
        try:
            gate_open = {k: bool(v.get("open"))
                         for k, v in executor.gate_states(db, env).items()}
        except Exception as exc:  # noqa: BLE001 - an unreadable gate is unchecked, not closed
            gate_error = f"{type(exc).__name__}: {exc}"[:300]
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
        # C-65 (Codex P03): closed out means zero OPEN *with every gate read live*. With no
        # database the gate half of the classification is the registry's word, so the bar
        # is indeterminate, not met.
        "closed_out": counts[OPEN] == 0 and gate_open is not None,
        "closeout_indeterminate": gate_open is None,
        "gates_checked_live": gate_open is not None,
        # C-65: explicit when the gates were not read, and which parked rows that leaves
        # resting on the registry's word rather than on a live check.
        "gates_unchecked": (None if gate_open is not None else {
            "why": gate_error or "no database given; pass one to check every gate live",
            "rows": sorted(r["id"] for r in rows if r.get("gate") and r["state"] != OPEN)}),
        "external_blockers": {k: v for k, v in EXTERNAL_GATES.items()},
        "by_section": by_section,
        "open": open_rows,
        "rows": rows,
    }


# ---------------------------------------------------------------------------------------------
# W4-B2: the dashboard's Build 2 figures and the per-row ledger, both from this matrix.
#
# The owner's dashboard read "Build 2: 227/320 complete (70.9%), executable remaining 45,
# owner-gated 28, data-gated 20" on 2026-10-07. That is `requirements.coverage()` served by
# production at fcb982d -- the registry of 2026-09-22 -- and it is wrong twice over: stale (the
# 2026-09-27/28 certification reopened and re-parked rows the deployed registry still calls
# covered or owner_gated), and miscounted in meaning (`executable_remaining` is partial+missing,
# so a partial row parked on an owner, data or external gate is reported as executable work, and
# "complete" is the registry's claim rather than a proof). The figures below are the closure's:
# computed from evidence, with gated work split by the kind of its gate and OPEN being the only
# executable remainder.

LEDGER_STATES = ("PROVEN", "OWNER-GATED", "DATA-GATED", "EXTERNAL-GATED", "NOT-APPLICABLE",
                 "OPEN-DEFECT")
_LEDGER_OF = {COMPLETE_PROVEN: "PROVEN", OWNER_GATED: "OWNER-GATED", DATA_GATED: "DATA-GATED",
              EXTERNAL_BLOCKED: "EXTERNAL-GATED", OPEN: "OPEN-DEFECT"}


def ledger_state(row: dict) -> str:
    """The ledger's vocabulary for one classified row.

    A process directive to the auditor (merge order, canonical reconciliation) is closed as
    followed by the matrix; the ledger calls it NOT-APPLICABLE because nothing was built, so the
    PROVEN count is only rows whose machinery exists, is tested and is reached."""
    if row["state"] == COMPLETE_PROVEN and (row.get("proof") or {}).get("directive"):
        return "NOT-APPLICABLE"
    return _LEDGER_OF[row["state"]]


def dashboard(db=None, *, env=None, m: dict | None = None) -> dict:
    """The Build 2 headline the owner's dashboard should show, from the closure matrix.

    `executable_remaining` here is OPEN only -- executable work nothing is waiting for. Rows
    parked on a gate are counted under the kind of that gate, never as executable work."""
    m = m if m is not None else matrix(db, env=env)
    c = m["counts"]
    na = sum(1 for r in m["rows"] if ledger_state(r) == "NOT-APPLICABLE")
    proven = c[COMPLETE_PROVEN] - na
    return {
        "basis": "build2.closure.matrix (evidence: module exists, is tested and is reached; "
                 "gated rows by the kind of their gate) -- not the registry's own status",
        "total": m["total"],
        "proven": proven,
        "not_applicable": na,
        "complete": c[COMPLETE_PROVEN],
        "percent_complete": round(100.0 * c[COMPLETE_PROVEN] / m["total"], 1),
        "owner_gated": c[OWNER_GATED],
        "data_gated": c[DATA_GATED],
        "external_gated": c[EXTERNAL_BLOCKED],
        "open_defects": c[OPEN],
        "executable_remaining": c[OPEN],
        "gates_checked_live": m["gates_checked_live"],
        "closed_out": m["closed_out"],
        "as_of": m["as_of"],
    }


def _runtime_path(proof: dict) -> list[dict]:
    """The live consumer path of each reached module, as reachability states it."""
    from . import reachability

    out = []
    for mod in (proof or {}).get("reached", [])[:3]:
        v = reachability.reached(mod)
        out.append({"module": mod, "why": v.get("why"), "live": v.get("live", [])[:4]})
    return out


@reachability._graph_boundary
@maturity._with_test_import_snapshot
def ledger(db=None, *, env=None, gate_open: dict[str, bool] | None = None,
           gate_source: str = "") -> dict:
    """Every requirement -> one ledger state with its evidence and, when gated, its exact gate.

    `gate_open` lets a caller supply gate readings taken elsewhere (for example production's
    `/api/build` read-only) when no database is at hand; `gate_source` says where they came
    from. A gate absent from the readings is unchecked, never assumed open."""
    if db is not None and gate_open is None:
        gate_open = {k: bool(v.get("open")) for k, v in executor.gate_states(db, env).items()}
        gate_source = gate_source or "executor.gate_states(db)"
    rows = [classify(r, gate_open=gate_open) for r in reg.load()]
    by_req = {r.id: r for r in reg.load()}
    out = []
    for row in rows:
        state = ledger_state(row)
        proof = row.get("proof") or {}
        entry = {"id": row["id"], "title": row["title"], "section": row["section"],
                 "registry_status": row["status"], "state": state,
                 "closure_state": row["state"], "why": row["why"],
                 "evidence": {"tests": sorted(set(proof.get("tests", []))),
                              "tested_modules": proof.get("tested", []),
                              "artefacts": proof.get("existing", []),
                              "runtime_consumers": _runtime_path(proof)}}
        if proof.get("directive"):
            entry["evidence"]["directive"] = proof["directive"]
        gate = row.get("gate")
        if gate and state in ("OWNER-GATED", "DATA-GATED", "EXTERNAL-GATED"):
            g = executor.GATE_BY_KEY.get(gate)
            entry["gate"] = {
                "key": gate, "kind": kind_of(gate),
                "what": g.what if g else None,
                "opens_when": g.how if g else None,
                "external_evidence": EXTERNAL_GATES.get(gate),
                "state": ("open" if (gate_open or {}).get(gate) else
                          "closed" if gate_open is not None and gate in gate_open else
                          "unchecked"),
                "state_source": gate_source if gate_open is not None and gate in gate_open
                                else "not readable: no live reading of this gate was given",
                "remaining_note": by_req[row["id"]].note[-400:],
            }
        out.append(entry)
    counts = {s: sum(1 for e in out if e["state"] == s) for s in LEDGER_STATES}
    return {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "spec": "spec/08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf",
            "total": len(out), "counts": counts, "gate_source": gate_source or None,
            "rows": out}
