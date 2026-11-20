"""F-624: the quarterly company/Etsy capability audit, written as decision records.

The daily executive brief is `autonomy.morning_handoff` and the weekly retrospective is
`improve.cells`; what did not exist was the quarterly look at *what the company can do*:
which Etsy surfaces have a collector and evidence, which first-sale blockers remain, and
where the Build 2 closure stands -- compared with the previous quarter, with a decision for
each gap. It runs from the morning handoff (no new cadence or permission), once per quarter,
keyed `capability_audit:<YYYY>Q<n>`; a second run in the same quarter writes nothing.

Decisions are recorded, not executed: each names the gap, the evidence and the next step,
and lands in company memory (`kind="capability_audit"`) with a `decision.recorded` event.
"""
from __future__ import annotations

from datetime import datetime, timezone

KIND = "capability_audit"


def quarter(now: datetime) -> str:
    return f"{now.year}Q{(now.month - 1) // 3 + 1}"


def _readings(db) -> dict:
    out: dict = {}
    try:
        from ..intel import etsy_surfaces

        cov = etsy_surfaces.coverage()
        out["etsy"] = {"surfaces": cov["surfaces"], "verdicts": cov["verdicts"],
                       "without_collector": cov["without_collector"],
                       "required_before_first_sale": cov["required_before_first_sale"],
                       "owner_actions": cov["owner_actions"],
                       "scope_gaps": len(cov["scope_gaps"]), "problems": cov["problems"]}
    except Exception as exc:  # noqa: BLE001 - an unreadable source is UNKNOWN, by name
        out["etsy"] = {"state": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        from ..build2 import closure

        d = closure.dashboard(db)
        out["closure"] = {k: d[k] for k in ("total", "proven", "percent_complete",
                                            "owner_gated", "data_gated", "external_gated",
                                            "open_defects")}
    except Exception as exc:  # noqa: BLE001
        out["closure"] = {"state": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out


def decisions(now_r: dict, prev_r: dict | None) -> list[dict]:
    out: list[dict] = []
    etsy, prev_etsy = now_r.get("etsy") or {}, (prev_r or {}).get("etsy") or {}
    clo, prev_clo = now_r.get("closure") or {}, (prev_r or {}).get("closure") or {}
    for src, r in (("etsy_surfaces", etsy), ("build2_closure", clo)):
        if r.get("state") == "UNKNOWN":
            out.append({"gap": f"{src} unreadable", "evidence": r["why"],
                        "decision": "repair the reader before the next audit; no capability "
                                    "claim is made from an unreadable source"})
    blockers = [k for k in etsy.get("required_before_first_sale") or []
                if k in set(etsy.get("without_collector") or [])]
    if blockers:
        out.append({"gap": "first-sale surfaces with no collector", "evidence": blockers,
                    "decision": "build a collector or record each as owner-manual this quarter"})
    if etsy.get("problems"):
        out.append({"gap": "Etsy surface registry problems", "evidence": etsy["problems"][:10],
                    "decision": "fix the registry entries before relying on coverage"})
    if isinstance(clo.get("open_defects"), int) and clo["open_defects"] > 0:
        grew = (isinstance(prev_clo.get("open_defects"), int)
                and clo["open_defects"] > prev_clo["open_defects"])
        out.append({"gap": "Build 2 executable rows open",
                    "evidence": {"open": clo["open_defects"],
                                 "previous": prev_clo.get("open_defects", "NO_PRIOR_AUDIT")},
                    "decision": ("open work grew since last quarter: prioritise closure over "
                                 "new capability" if grew else
                                 "continue closing executable rows in value order")})
    if (isinstance(clo.get("percent_complete"), (int, float))
            and isinstance(prev_clo.get("percent_complete"), (int, float))
            and clo["percent_complete"] <= prev_clo["percent_complete"]):
        out.append({"gap": "no closure progress quarter on quarter",
                    "evidence": {"now": clo["percent_complete"],
                                 "previous": prev_clo["percent_complete"]},
                    "decision": "review what parked the work; raise owner-gated items in one batch"})
    return out


def run(db, *, now: datetime | None = None) -> dict:
    from . import memory

    now = now or datetime.now(timezone.utc)
    q = quarter(now)
    key = f"{KIND}:{q}"
    if memory.get(db, key) is not None:
        return {"ran": False, "quarter": q, "reason": "already audited this quarter"}
    prior = memory.recall(db, kind=KIND, limit=1)
    prev = prior[0]["body"].get("readings") if prior else None
    readings = _readings(db)
    made = decisions(readings, prev)
    body = {"quarter": q, "readings": readings, "decisions": made,
            "previous_quarter": prior[0]["body"].get("quarter") if prior else None}
    memory.remember(db, key, kind=KIND, department="executive", state="decided",
                    subject=f"Capability audit {q}", body=body,
                    sources=["intel.etsy_surfaces.coverage", "build2.closure.dashboard"],
                    now=now)
    memory.record_event(db, key, kind="decision.recorded", department="executive",
                        summary=f"Capability audit {q}: {len(made)} decision(s)",
                        refs=[f"company_memory:{key}"], at=now)
    return {"ran": True, "quarter": q, "decisions": len(made), "key": key}
