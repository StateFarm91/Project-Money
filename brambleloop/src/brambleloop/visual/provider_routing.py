"""F-739 Cross-Provider Identity Benchmark: route on-model work by demonstrated evidence (W4-C08).

"Continuously benchmark available image providers/modes for canonical-model identity
retention, Product Truth retention, realism, yield, latency and cost. Route on-model work to
the best demonstrated configuration rather than permanently hard-coding one provider."

No new paid call is made here. The benchmark is a reading of evidence the system already
records every time it renders Laura:
* `image_candidates` (`visual.image_records`) -- every on-model candidate (`laura_present`)
  with provider, model, its identity / product_truth / realism checks, outcome, cost, latency;
* the F-744 model evidence ledger (`visual.model_ledger`) -- provider trials, model
  photography, benchmark trials, with identity, Product Truth and realism verdicts and cost.
Paid challenger renders are still only made through the existing, gated paths
(`visual.provider_trial` under `finance.spend_policy`, `experiments.controlled` behind owner
authorization and step-up); their results land in those two tables and so in this scoreboard.

`scoreboard(db)` groups the evidence per configuration (provider, model). `route(db, ...)`
picks the best demonstrated configuration among the AVAILABLE ones: it must have at least
`MIN_EVIDENCE` judged frames on identity and on Product Truth, and clear the identity and
Product Truth floors; it is then ranked identity retention > Product Truth > realism > yield >
cost per accepted image > latency. With no configuration demonstrated, the caller's default
is returned with that reason -- the default is a fallback, never a permanent choice.
`image_production.resolve_generator` consults `route` whenever more than one generator is
registered. Deterministic, read-only, CA$0.
"""
from __future__ import annotations

KIND = "visual.provider_route"
MIN_EVIDENCE = 5
IDENTITY_FLOOR = 0.8
PRODUCT_TRUTH_FLOOR = 0.8
_PASS = {"PASS", "MATCH", "pass", "match"}
_FAIL = {"FAIL", "DRIFT", "fail", "drift", "mismatch", "MISMATCH"}


def _v(x) -> str | None:
    if isinstance(x, dict):
        x = x.get("status") or x.get("verdict")
    if x in _PASS:
        return "PASS"
    if x in _FAIL:
        return "FAIL"
    return None


def observations(db) -> list[dict]:
    """One uniform observation per on-model frame, from both evidence sources."""
    from sqlalchemy import select

    from . import model_ledger
    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    out: list[dict] = []
    with db.session() as s:
        for r in s.scalars(select(ImageCandidate).where(ImageCandidate.laura_present == True)):  # noqa: E712
            c = r.checks or {}
            out.append({"source": "image_candidate", "provider": r.provider or "UNKNOWN",
                        "model": r.model or "UNKNOWN",
                        "identity": _v(c.get("identity")),
                        "product_truth": _v(c.get("product_truth")),
                        "realism": _v(c.get("realism")),
                        "accepted": r.outcome == "accepted",
                        "cost_cad": r.cost_cad, "latency_s": r.latency_s})
    for e in model_ledger.ledger(db, limit=100000):
        out.append({"source": f"ledger:{e.get('kind')}", "provider": str(e.get("provider")),
                    "model": str(e.get("model")),
                    "identity": _v((e.get("identity") or {}).get("verdict")),
                    "product_truth": _v(e.get("product_truth")),
                    "realism": _v(e.get("realism")),
                    "accepted": e.get("accepted") is True,
                    "cost_cad": (e.get("cost_cad") if isinstance(e.get("cost_cad"), (int, float))
                                 else None),
                    "latency_s": None})
    return out


def _share(obs: list[dict], key: str) -> tuple[float | None, int]:
    judged = [o[key] for o in obs if o[key] is not None]
    return ((sum(1 for v in judged if v == "PASS") / len(judged)) if judged else None,
            len(judged))


def scoreboard(db=None, *, obs: list[dict] | None = None) -> list[dict]:
    obs = obs if obs is not None else observations(db)
    groups: dict[tuple, list] = {}
    for o in obs:
        groups.setdefault((o["provider"], o["model"]), []).append(o)
    rows = []
    for (provider, model), g in sorted(groups.items()):
        idr, idn = _share(g, "identity")
        ptr, ptn = _share(g, "product_truth")
        rlr, rln = _share(g, "realism")
        acc = sum(1 for o in g if o["accepted"])
        costs = [o["cost_cad"] for o in g if o["cost_cad"] is not None]
        lat = [o["latency_s"] for o in g if o["latency_s"] is not None]
        rows.append({
            "provider": provider, "model": model, "frames": len(g),
            "identity_retention": idr, "identity_judged": idn,
            "product_truth_retention": ptr, "product_truth_judged": ptn,
            "realism": rlr, "realism_judged": rln,
            "yield": acc / len(g), "accepted": acc,
            "spent_cad": round(sum(costs), 4),
            "cost_per_accepted_cad": (round(sum(costs) / acc, 4)
                                      if acc and len(costs) == len(g) else None),
            "latency_s_mean": round(sum(lat) / len(lat), 2) if lat else None,
            "sources": sorted({o["source"] for o in g}),
        })
    return rows


def _eligible(row: dict) -> str | None:
    if min(row["identity_judged"], row["product_truth_judged"]) < MIN_EVIDENCE:
        return f"fewer than {MIN_EVIDENCE} judged frames on identity or Product Truth"
    if row["identity_retention"] < IDENTITY_FLOOR:
        return f"identity retention {row['identity_retention']:.0%} < {IDENTITY_FLOOR:.0%}"
    if row["product_truth_retention"] < PRODUCT_TRUTH_FLOOR:
        return (f"Product Truth retention {row['product_truth_retention']:.0%} < "
                f"{PRODUCT_TRUTH_FLOOR:.0%}")
    return None


def _rank(row: dict) -> tuple:
    big = float("inf")
    return (-row["identity_retention"], -row["product_truth_retention"],
            -(row["realism"] or 0.0), -row["yield"],
            row["cost_per_accepted_cad"] if row["cost_per_accepted_cad"] is not None else big,
            row["latency_s_mean"] if row["latency_s_mean"] is not None else big)


def route(db=None, *, available: list[str] | None = None, default: str | None = None,
          board: list[dict] | None = None) -> dict:
    """The best demonstrated configuration among `available` providers (None: any)."""
    board = board if board is not None else scoreboard(db)
    considered, refused = [], {}
    for row in board:
        if available is not None and row["provider"] not in available:
            continue
        why = _eligible(row)
        if why:
            refused[f"{row['provider']}/{row['model']}"] = why
        else:
            considered.append(row)
    if considered:
        best = sorted(considered, key=_rank)[0]
        return {"provider": best["provider"], "model": best["model"], "basis": "demonstrated",
                "evidence": best, "refused": refused,
                "rule": "identity > Product Truth > realism > yield > cost/accepted > latency"}
    return {"provider": default, "model": None, "basis": "default",
            "why": "no available configuration has demonstrated the identity and Product Truth "
                   "floors on enough judged frames; the default is a fallback, not a choice",
            "refused": refused}


def record(db) -> dict:
    """Persist this reading (one per day) so the benchmark has a history."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import OperatingReading

    board = scoreboard(db)
    chosen = route(board=board)
    key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                      OperatingReading.period_key == key))
        payload = {"scoreboard": board, "route": {k: chosen.get(k) for k in
                                                  ("provider", "model", "basis", "why")}}
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=key, payload=payload))
        else:
            row.payload = payload
    return {"configurations": len(board), "route": payload["route"]}
