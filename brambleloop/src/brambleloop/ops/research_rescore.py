"""D-OWNER-RESEARCH-BAR (2026-11-22): re-score concepts refused only on the old research bar.

The owner ruled "Drop discount, bar 0.45": the #38 trend-evidence discount no longer multiplies
the opportunity score, and `PROMOTION_THRESHOLD` fell from 0.55 to 0.45. A concept whose newest
`radar.score` refused it on the score alone (or, under D-OWNER-NO-SAMPLE-SIZING, on "Class C
requires physical testing") is not re-judged until something re-scores it, so the Catalogue
kept showing products the owner wants as REJECTED.

Once per deployed commit this enqueues one ordinary `radar.score` per such concept. The handler
re-decides with today's rules through `promotion_verdict` (the pre-engineering gate included),
and a promoted concept is offered to `products.supply` -- the normal admission path and its WIP
limit. Nothing is promoted here and no admission is bypassed. A refusal by the pre-engineering
gate, an owner veto, or a concept that already has build work is never a candidate. No spend,
no model, no Etsy call.
"""
from __future__ import annotations

RULING = "D-OWNER-RESEARCH-BAR"
CAP = 80
# The refusal texts `promotion_verdict` writes for the two rules the owner changed.
_SCORE_REFUSAL = "below promotion threshold"
_CLASS_C_REFUSAL = "Class C requires physical testing"
_BUILD_TYPES = ("cir.draft", "cir.revise", "cir.reengineer", "cir.compile")


def is_research_only_refusal(outputs: dict | None) -> bool:
    """True when a `radar.score` output refused the concept only on a rule the owner changed."""
    out = outputs or {}
    if out.get("promoted") is not False or not out.get("slug"):
        return False
    if out.get("gate") or out.get("mode"):
        return False  # the pre-engineering gate refused it, or it was a coverage handoff
    reason = str(out.get("reason") or "")
    return _SCORE_REFUSAL in reason or reason.startswith(_CLASS_C_REFUSAL)


def candidates(session) -> list[str]:
    """Slugs whose NEWEST completed `radar.score` is a research-only refusal and that have no
    build work (a built concept is past research and is not re-scored here)."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    newest: dict[str, tuple[int, dict]] = {}
    for jid, outputs in session.execute(
            select(Job.id, Job.outputs).where(Job.job_type == "radar.score",
                                              Job.status == JobStatus.DONE)
            .order_by(Job.id)).all():
        slug = (outputs or {}).get("slug")
        if slug:
            newest[slug] = (jid, outputs or {})
    built: set[str] = set()
    for (inputs,) in session.execute(select(Job.inputs).where(Job.job_type.in_(_BUILD_TYPES))):
        if (inputs or {}).get("slug"):
            built.add(inputs["slug"])
    return sorted(slug for slug, (_jid, out) in newest.items()
                  if slug not in built and is_research_only_refusal(out))[:CAP]


def run(db, enqueue, *, commit: str, as_of: str | None = None) -> dict:
    """Enqueue one `radar.score` per candidate for this commit.

    `enqueue(agent, job_type, inputs, idempotency_key=...)` returns the job (None for a
    duplicate key) or raises; a duplicate is counted, never an error."""
    from ..runtime.pipeline import _seed_for
    from ..radar.opportunity import score_concept

    token = (commit or "dev")[:12]
    enqueued, skipped, duplicates = [], [], 0
    with db.session() as s:
        cands = candidates(s)
    for slug in cands:
        seed = _seed_for(slug, db)
        if seed is None:
            skipped.append({"slug": slug, "why": "not in the pool"})
            continue
        try:
            from datetime import date

            payload = score_concept(seed, date.fromisoformat(as_of) if as_of
                                    else date.today()).to_dict()
        except Exception as exc:  # noqa: BLE001 - one concept never stops the rest
            skipped.append({"slug": slug, "why": f"{type(exc).__name__}"})
            continue
        payload["rescore"] = {"ruling": RULING, "commit": token}
        try:
            job = enqueue("market_radar", "radar.score", payload,
                          idempotency_key=f"rescore-bar:{slug}:{token}")
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "DuplicateJob":
                duplicates += 1
            else:
                skipped.append({"slug": slug, "why": f"{type(exc).__name__}"})
            continue
        if job is None:
            duplicates += 1
        else:
            enqueued.append(slug)
    return {"ruling": RULING, "token": token, "candidates": len(cands), "enqueued": enqueued,
            "duplicates": duplicates, "skipped": skipped[:20]}
