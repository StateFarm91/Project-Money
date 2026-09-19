"""What has to be true before a new shop spends money on traffic.

Requirement 17. The instruction is a sequence, and the sequence is the content: complete the
shop, then accumulate legitimate proof, then scale. Reversing it is the most expensive
ordinary mistake in this category -- paid traffic arriving at a shop with no About page, one
photograph and no reviews converts at a fraction of the same traffic a month later, and the
money is spent either way. Nobody reverses it on purpose. It happens because the ads are the
exciting part and the About page is not.

So this is a gate rather than a checklist, and it reads rows rather than intentions.

**Every rung reports passed, failed or unmeasured, and unmeasured is not passed.** A thumbnail
coherence check nobody can run yet is not a rung this shop has cleared; it is a rung nobody
has looked at, and the two are opposite situations wearing the same colour.

**Proof has an origin or it is not proof.** A tester example points at a physical test row; a
customer example points at an order. A testimonial somebody typed is refused at the door,
which is the mechanical form of the standing rule against manufactured reviews -- a rule that
survives on good intentions right up until a quiet week.
"""
from __future__ import annotations

from dataclasses import dataclass

PASSED, FAILED, UNMEASURED = "passed", "failed", "unmeasured"

# Proof origins that can be checked against a row in this database. Anything else is somebody
# saying a nice thing happened.
TESTER_PROOF = "physical_test"
CUSTOMER_PROOF = "sale"
PROOF_ORIGINS: tuple[str, ...] = (TESTER_PROOF, CUSTOMER_PROOF)

# How much legitimate proof a new shop needs before paid traffic is worth buying. Deliberately
# small: the point is not a high bar, it is that the number is above zero and counted.
PROOF_FLOOR = 3


class TrustRefused(ValueError):
    """Proof with no verifiable origin, or a scale decision taken before the sequence."""


@dataclass(frozen=True)
class Rung:
    key: str
    what: str
    why: str


RUNGS: tuple[Rung, ...] = (
    Rung("shop_complete", "icon, banner, About, policies and sections",
         "an empty About page is the first thing a cautious buyer notices, and paid traffic "
         "is the most expensive way to show it to people"),
    Rung("download_expectations", "the digital-not-finished disclosure where it is read",
         "a buyer who thinks they are purchasing a blanket refunds, and that refund is the "
         "most preventable one in the category"),
    Rung("truthful_information", "size, material and difficulty claims that survive the gate",
         "an unsupported claim converts once and is a dispute afterwards"),
    Rung("thumbnail_coherence", "a thumbnail set that reads as one shop",
         "the shop front is the grid of thumbnails; a set that does not cohere reads as a "
         "reseller whatever the About page says"),
    Rung("rapid_support", "a response target that is met rather than published",
         "the fastest trust signal a new shop has, and the only one that costs nothing"),
    Rung("legitimate_proof", "tester and customer examples with a row behind each",
         "the one rung that cannot be built in an afternoon, which is exactly why it is the "
         "one people manufacture"),
)

RUNG_BY_KEY: dict[str, Rung] = {r.key: r for r in RUNGS}


def proof_count(db) -> dict:
    """Legitimate proof, counted from rows rather than from a claim about proof."""
    from sqlalchemy import func, select

    from ..core.models import LedgerEntry, PhysicalTest

    with db.session() as s:
        testers = int(s.scalar(select(func.count()).select_from(PhysicalTest).where(
            PhysicalTest.passed == True)) or 0)  # noqa: E712
        # A sale is a ledger row with money in it. There is no orders table, and inventing
        # one so this function could count something would be the wrong kind of tidy.
        customers = int(s.scalar(select(func.count()).select_from(LedgerEntry).where(
            LedgerEntry.category == "sale")) or 0)
    return {"physical_test": testers, "sale": customers, "total": testers + customers}


def record_proof(db, *, origin: str, row_id: int, summary: str) -> dict:
    """Attach a proof example to the row it came from, refusing anything free-standing.

    This is the standing rule against manufactured reviews in its mechanical form. A rule
    that lives only in a document survives every quiet week except the one that matters.
    """
    from ..core.models import AuditLog, LedgerEntry, PhysicalTest

    if origin not in PROOF_ORIGINS:
        raise TrustRefused(
            f"{origin!r} is not a verifiable proof origin: {list(PROOF_ORIGINS)}. A "
            f"testimonial with no row behind it is somebody saying a nice thing happened")
    model = {TESTER_PROOF: PhysicalTest, CUSTOMER_PROOF: LedgerEntry}[origin]
    with db.session() as s:
        row = s.get(model, row_id)
        if row is None:
            raise TrustRefused(
                f"no {origin} row {row_id}. Proof points at something that happened, and "
                f"this points at nothing")
        entry = AuditLog(actor="brand", action="trust.proof", artifact=f"{origin}:{row_id}",
                         detail={"origin": origin, "row_id": row_id, "summary": summary})
        s.add(entry)
        s.flush()
        return {"origin": origin, "row_id": row_id, "record_id": entry.id}


def accelerator(db, *, storefront_problems: list[str] | None = None,
                disclosure_ok: bool | None = None,
                claims_ok: bool | None = None,
                thumbnails_coherent: bool | None = None,
                support_meets_target: bool | None = None) -> dict:
    """Every rung, with what it is measured from and whether anybody has measured it.

    The unmeasured verdict is load-bearing. A rung nobody can check yet is not a rung this
    shop has cleared, and reporting it as green is how a sequence becomes a formality.
    """
    from ..brand.storefront import build_storefront

    problems = (storefront_problems if storefront_problems is not None
                else build_storefront().problems)
    proof = proof_count(db)

    def verdict(value: bool | None) -> str:
        return UNMEASURED if value is None else (PASSED if value else FAILED)

    rungs = [
        {"rung": "shop_complete", "verdict": PASSED if not problems else FAILED,
         "evidence": {"storefront_problems": list(problems)}},
        {"rung": "download_expectations", "verdict": verdict(disclosure_ok),
         "evidence": {"checked": disclosure_ok is not None}},
        {"rung": "truthful_information", "verdict": verdict(claims_ok),
         "evidence": {"checked": claims_ok is not None}},
        {"rung": "thumbnail_coherence", "verdict": verdict(thumbnails_coherent),
         "evidence": {"checked": thumbnails_coherent is not None}},
        {"rung": "rapid_support", "verdict": verdict(support_meets_target),
         "evidence": {"checked": support_meets_target is not None}},
        {"rung": "legitimate_proof",
         "verdict": PASSED if proof["total"] >= PROOF_FLOOR else FAILED,
         "evidence": {**proof, "floor": PROOF_FLOOR}},
    ]
    for row in rungs:
        spec = RUNG_BY_KEY[row["rung"]]
        row["what"], row["why"] = spec.what, spec.why

    failed = [r["rung"] for r in rungs if r["verdict"] == FAILED]
    unmeasured = [r["rung"] for r in rungs if r["verdict"] == UNMEASURED]
    return {
        "rungs": rungs,
        "failed": failed,
        "unmeasured": unmeasured,
        "cleared": not failed and not unmeasured,
        "proof": proof,
        "note": ("the sequence is complete: the shop is finished and the proof is counted"
                 if not failed and not unmeasured else
                 f"{len(failed)} rung(s) failed and {len(unmeasured)} have not been "
                 f"measured. Unmeasured is not passed: a rung nobody has looked at and a "
                 f"rung this shop has cleared are opposite situations"),
    }


def may_scale_ads(db, **checks) -> dict:
    """Whether paid traffic is worth buying yet, and exactly what is in the way.

    Returns rather than raises, because the answer is normally no for months and a refusal
    that reads as an error trains a reader to route around it.
    """
    state = accelerator(db, **checks)
    blocking = state["failed"] + state["unmeasured"]
    return {
        "may_scale": state["cleared"],
        "blocking": blocking,
        "detail": state,
        "note": ("nothing is in the way of paid traffic on trust grounds; the spend decision "
                 "itself is a separate owner approval"
                 if state["cleared"] else
                 f"paid traffic would arrive at a shop that is not finished: {blocking}. "
                 f"The same traffic a month later converts better and costs the same, which "
                 f"is the whole of #17"),
    }
