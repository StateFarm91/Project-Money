"""F-723: research spend above a threshold must name what it expects to learn, and the
realised learning is reported against the expectation.

ROI, stagnation throttling and the governor's marginal value already price *improvements*.
Research spend -- the gallery vision batch, SERP judging, any `research.*` purpose -- was
priced only against ceilings: a batch that fitted the budget ran whether or not it could
teach anything. Here a research reservation at or above `THRESHOLD_CAD` needs a declared
`Expected`:

* `question` -- what is being asked;
* `informs` -- the decision or consumer the answer changes (a question nobody reads is spend
  without a customer);
* `new_observations` -- how many new observations the spend can buy toward that question,
  computed by the caller from its own backlog (an already-drained backlog is zero, and zero
  is refused, which is the point);
* optional `risk_reduction` (0..1) and `capability` -- declared, never invented here.

`value_per_cad` = new_observations / amount. Below `MIN_OBSERVATIONS_PER_CAD` the spend is
refused. Every accepted expectation writes a `learning_value.expected` row; `realise` writes
the `learning_value.realised` row with what the spend actually obtained, and `report` puts
them side by side. Unrealised expectations are listed, never counted as realised.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

THRESHOLD_CAD = 0.25
MIN_OBSERVATIONS_PER_CAD = 4.0
RESEARCH_PURPOSES = frozenset({"gallery_observation", "serp_observation", "market_research",
                               "research_fetch"})
EXPECTED_ACTION = "learning_value.expected"
REALISED_ACTION = "learning_value.realised"
REFUSED_ACTION = "learning_value.refused"


class LearningValueRefused(ValueError):
    """Research spend above the threshold without a learning value that clears the floor."""


@dataclass(frozen=True)
class Expected:
    question: str
    informs: str
    new_observations: int
    risk_reduction: float | None = None
    capability: str = ""


def is_research(purpose: str) -> bool:
    p = (purpose or "").strip()
    return p in RESEARCH_PURPOSES or p.startswith("research.") or p.startswith("research_")


def _audit(db, action: str, artifact: str, detail: dict) -> int:
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor="learning_value", action=action, artifact=artifact, detail=detail)
        s.add(row)
        s.flush()
        return int(row.id)


def require(db, *, purpose: str, amount_cad: float, expected: Expected | None,
            job_id: int | None = None) -> dict:
    """Admit or refuse a research reservation. Returns the receipt; raises when refused."""
    amount = float(amount_cad or 0.0)
    if not is_research(purpose) or amount < THRESHOLD_CAD:
        return {"required": False, "receipt": None, "purpose": purpose, "amount_cad": amount}
    why = None
    if expected is None:
        why = "no expected learning value declared"
    elif not expected.question.strip() or not expected.informs.strip():
        why = "a learning value must name the question and the decision it informs"
    elif int(expected.new_observations) < 1:
        why = "the spend can buy no new observation toward the question"
    elif expected.risk_reduction is not None and not 0.0 <= expected.risk_reduction <= 1.0:
        why = f"risk_reduction {expected.risk_reduction} outside 0..1"
    per_cad = (int(expected.new_observations) / amount) if expected and amount else None
    if why is None and per_cad is not None and per_cad < MIN_OBSERVATIONS_PER_CAD:
        why = (f"{per_cad:.2f} new observations per CA$ is below the floor of "
               f"{MIN_OBSERVATIONS_PER_CAD}")
    detail = {"purpose": purpose, "amount_cad": round(amount, 4), "job_id": job_id,
              "expected": asdict(expected) if expected else None,
              "value_per_cad": round(per_cad, 4) if per_cad is not None else None}
    if why:
        _audit(db, REFUSED_ACTION, purpose, {**detail, "why": why})
        raise LearningValueRefused(f"{purpose}: CA${amount:.2f} research spend refused: {why}")
    receipt = _audit(db, EXPECTED_ACTION, purpose, detail)
    return {"required": True, "receipt": receipt, **detail}


def realise(db, receipt: int | None, *, observations: int, cost_cad: float,
            decision_changed: bool | None = None, note: str = "") -> int | None:
    """Record what the admitted spend obtained. `decision_changed` None means not yet known."""
    if receipt is None:
        return None
    return _audit(db, REALISED_ACTION, str(receipt),
                  {"receipt": int(receipt), "observations": int(observations),
                   "cost_cad": round(float(cost_cad or 0.0), 4),
                   "decision_changed": decision_changed, "note": note[:300]})


def report(db, *, limit: int = 200) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action.in_(
            (EXPECTED_ACTION, REALISED_ACTION, REFUSED_ACTION))).order_by(AuditLog.id.desc())
            .limit(limit)))
        rows = [(r.id, r.action, dict(r.detail or {})) for r in rows]
    realised = {d.get("receipt"): d for _i, a, d in rows if a == REALISED_ACTION}
    lines, unrealised, refused = [], [], []
    for rid, action, d in rows:
        if action == REFUSED_ACTION:
            refused.append({"row": rid, "purpose": d.get("purpose"), "why": d.get("why")})
        elif action == EXPECTED_ACTION:
            exp = d.get("expected") or {}
            r = realised.get(rid)
            if r is None:
                unrealised.append(rid)
            lines.append({
                "receipt": rid, "purpose": d.get("purpose"), "question": exp.get("question"),
                "expected_observations": exp.get("new_observations"),
                "realised_observations": r["observations"] if r else "UNREALISED",
                "realisation": (round(r["observations"] / exp["new_observations"], 3)
                                if r and exp.get("new_observations") else "UNREALISED"),
                "cost_cad": r["cost_cad"] if r else None,
                "decision_changed": r.get("decision_changed") if r else None})
    done = [x for x in lines if x["realisation"] != "UNREALISED"]
    return {"threshold_cad": THRESHOLD_CAD, "min_observations_per_cad": MIN_OBSERVATIONS_PER_CAD,
            "lines": lines, "unrealised": unrealised, "refused": refused[:20],
            "mean_realisation": (round(sum(x["realisation"] for x in done) / len(done), 3)
                                 if done else "UNMEASURED")}
