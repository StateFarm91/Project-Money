"""F-744 Model Evidence Ledger (W4-AGENTS cluster C2).

"Persist every material model experiment: canonical version, provider/model/mode, references,
prompts/settings, output hashes, identity score/evidence, Product Truth result, realism result,
cost, acceptance/rejection and reason. Failed identity approaches remain institutional
knowledge."

The experiments were recorded as audit rows of different shapes, and `ops.retention` prunes
`assets.model_photography` after its 60-day window -- so a failed approach older than that was
lost. `harvest(db)` normalises every experiment row into ONE record shape and persists it as an
`operating_readings` row (kind `visual.model_experiment`, keyed by the source audit id), which
retention does not prune. Fields a source row never recorded are UNKNOWN, never guessed.
Read-only against everything else; deterministic; CA$0.
"""
from __future__ import annotations

KIND = "visual.model_experiment"
UNKNOWN = "UNKNOWN"
#: audit action -> experiment kind
SOURCES: dict[str, str] = {
    "assets.model_photography": "model_photography",
    "visual.provider_trial": "provider_trial",
    "image.benchmark_trial": "image_benchmark_trial",
    "image.benchmark_candidate": "image_benchmark_candidate",
    "model.reference_pack": "reference_pack",
    "visual.portrait_repair": "portrait_repair",
}


def _get(d: dict, *path, default=UNKNOWN):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur or cur[p] in (None, ""):
            return default
        cur = cur[p]
    return cur


def normalise(audit_id: int, action: str, at, detail: dict) -> dict:
    d = dict(detail or {})
    cond = d.get("conditioned_on") or {}
    refs = [r for r in (cond.get("reference_image"), cond.get("body_reference_image"),
                        cond.get("chart_reference")) if r] or d.get("references") or UNKNOWN
    accepted = (d.get("usable_as_listing_asset") if "usable_as_listing_asset" in d
                else d.get("accepted") if "accepted" in d else d.get("made", UNKNOWN))
    return {
        "source_audit_id": int(audit_id), "kind": SOURCES.get(action, action),
        "at": at.isoformat() if hasattr(at, "isoformat") else str(at or UNKNOWN),
        "canonical_version": _get(cond, "pack_version", default=_get(d, "pack_version")),
        "provider": _get(d, "provider"), "model": _get(d, "model"),
        "mode": _get(d, "mode", default=_get(d, "method_version")),
        "references": refs,
        "prompt": _get(d, "prompt_sha256", default=_get(d, "prompt")),
        "settings": _get(d, "settings"),
        "output_hashes": _get(d, "image_sha256", default=_get(d, "image_ref")),
        "identity": {"verdict": _get(d, "identity", "verdict"),
                     "face": _get(d, "identity", "face", "verdict"),
                     "morphology": _get(d, "identity", "morphology", "verdict")},
        "product_truth": _get(d, "motif", "verdict", default=_get(d, "product_truth")),
        "realism": _get(d, "photographic_realism", "verdict",
                        default=_get(d, "photographic_realism")),
        "cost_cad": d.get("spent_cad", UNKNOWN),
        "accepted": accepted,
        "reason": str(d.get("why") or d.get("reason") or UNKNOWN)[:400],
    }


def harvest(db) -> dict:
    """Persist every not-yet-harvested experiment row. Idempotent per source audit id."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OperatingReading

    with db.session() as s:
        done = {k for (k,) in s.execute(select(OperatingReading.period_key).where(
            OperatingReading.kind == KIND)).all()}
        rows = s.execute(select(AuditLog.id, AuditLog.action, AuditLog.at, AuditLog.detail)
                         .where(AuditLog.action.in_(list(SOURCES)))).all()
        added = 0
        for rid, action, at, detail in rows:
            if str(rid) in done:
                continue
            s.add(OperatingReading(kind=KIND, period_key=str(rid),
                                   payload=normalise(rid, action, at, detail or {})))
            added += 1
    return {"harvested": added, "already": len(done), "sources": sorted(SOURCES)}


def ledger(db, *, limit: int = 500) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        return [dict(r.payload or {}) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == KIND)
            .order_by(desc(OperatingReading.id)).limit(limit))]


def failed_approaches(db) -> list[dict]:
    """Rejected experiments grouped by approach -- the institutional knowledge the row keeps."""
    groups: dict[tuple, dict] = {}
    for r in ledger(db, limit=100000):
        if r.get("accepted") is not False:
            continue
        key = (r["kind"], str(r["provider"]), str(r["mode"]))
        g = groups.setdefault(key, {"kind": key[0], "provider": key[1], "mode": key[2],
                                    "rejections": 0, "reasons": []})
        g["rejections"] += 1
        if r["reason"] not in g["reasons"]:
            g["reasons"].append(r["reason"])
    return sorted(groups.values(), key=lambda g: -g["rejections"])
