"""F-828: cross-department ownership of a Learn gap.

The Master assigns each department its part of the educational product: Research finds gaps,
Pattern supplies technical truth, Visual supplies truthful instructional assets,
Marketing/SEO packages discovery, CX supplies confusion signals, Finance measures economics
and Learn coordinates. Until this module every `LearnGap.owner` was "learn", so a gap that
was waiting on Pattern or Visual looked like Learn's own backlog.

`route(...)` reads what each department has already supplied for a topic and returns:

* `contributions`: per department, `supplied` / `needed` / `not_needed` / `UNMEASURED`,
  each with the evidence it was decided from;
* `owner`: the department whose contribution is the next one missing, in the order the
  work depends on -- technical truth before an instructional diagram, both before Learn
  writes the lesson. Learn owns the gap once its inputs are in.

Nothing is guessed: a topic only a support case raised has no technical truth until Pattern
supplies it (a CIR that teaches it), and a measure with no source is UNMEASURED, never 0.
"""
from __future__ import annotations

# Topic kinds that teach a hand movement: an instructional diagram is part of the lesson.
DIAGRAM_KINDS = ("stitch", "technique", "finishing")
ORDER = ("pattern", "visual", "learn")


def _kind(topic: str) -> str:
    return topic.split(":", 1)[0]


def route(topic: str, evidence: list[dict], *, diagram_lessons: set[str],
          search_demand: dict[str, int] | None, cost_cad: float | None) -> dict:
    pattern_ev = [e for e in evidence if e.get("pattern_version_id")]
    support_ev = [e for e in evidence if e.get("support_case_id")]
    needs_diagram = _kind(topic) in DIAGRAM_KINDS
    c = {
        "research": {"state": "supplied", "evidence": f"{len(evidence)} source(s) raised it"},
        "pattern": ({"state": "supplied",
                     "evidence": f"{len(pattern_ev)} certified-pattern CIR(s) teach it"}
                    if pattern_ev else
                    {"state": "needed", "evidence": "raised by support only; no CIR in "
                                                     "the catalogue teaches it yet"}),
        "visual": ({"state": "not_needed", "evidence": f"{_kind(topic)} topics carry no "
                                                       f"technique diagram"}
                   if not needs_diagram else
                   {"state": "supplied", "evidence": "a lesson carries a verified "
                                                     "technique_diagram for it"}
                   if topic in diagram_lessons else
                   {"state": "needed", "evidence": "a technique diagram is required "
                                                   "(F-806) and none exists"}),
        "customer_experience": {"state": "supplied" if support_ev else "UNMEASURED",
                                "evidence": f"{len(support_ev)} support case(s)"
                                if support_ev else "no support case mentions it yet"},
        "marketing_seo": ({"state": "UNMEASURED",
                           "evidence": "no search-demand reading for this topic"}
                          if search_demand is None or topic not in search_demand else
                          {"state": "supplied",
                           "evidence": f"search demand {search_demand[topic]}"}),
        "finance": ({"state": "UNMEASURED", "evidence": "no Learn cost is recorded yet"}
                    if cost_cad is None else
                    {"state": "supplied", "evidence": f"Learn spend CA${cost_cad:.2f} "
                                                      f"recorded to date"}),
    }
    owner = next((d for d in ORDER[:-1] if c[d]["state"] == "needed"), "learn")
    return {"topic": topic, "owner": owner, "contributions": c,
            "coordinator": "learn"}


def learn_cost_cad(db) -> float | None:
    """Recorded spend whose purpose is Learn's work; None (UNMEASURED) when there is none."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    try:
        with db.session() as s:
            rows = [float(c.amount_cad or 0.0) for c in s.scalars(select(CostEntry))
                    if str(getattr(c, "purpose", "") or "").startswith("learn")]
    except Exception:  # noqa: BLE001 - an unreadable ledger is UNMEASURED
        return None
    return round(sum(rows), 4) if rows else None
