"""F-748 Studio Visibility + F-680 Visual Evidence Panel: two consolidated read models (W4-C08).

F-748: "Brambleloop Studio exposes canonical model version, current best provider/mode,
recent identity/realism yield, rejected drift examples, active improvement experiments and
whether each listing image passed both Model Identity and Product Truth."

F-680: "show real benchmark reference, Brambleloop 3D, conditioning passes, generated
candidates, rejected candidates/reasons and final approved asset together."

The pieces were separate endpoints. `canonical_model(db)` and `evidence_panel(db, slug)` join
them from their single sources -- nothing is recomputed differently here:
* version -- `canonical_registry.resolve` (F-733);
* best provider/mode -- `provider_routing.route` (F-739);
* yield, drift examples, per-image verdicts -- `image_candidates` checks;
* active experiments -- `model_rnd.active` (F-737/F-745) and `experiments.controlled.board`;
* 3D -- `launch_imagery.last` (the registered disclosed set and gallery frames);
* conditioning passes -- each candidate's recorded references and conditioning receipt, and
  the F-679 trial matrix.
A part that has no record is ABSENT with the reason, never an empty success. Read-only, CA$0.
"""
from __future__ import annotations

ABSENT = "ABSENT"
RECENT = 50


def _st(checks: dict, key: str) -> str:
    return str((checks.get(key) or {}).get("status") or "UNKNOWN")


def _image_rows(db, *, slug: str | None = None, laura_only: bool = False) -> list:
    from sqlalchemy import desc, select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        q = select(ImageCandidate)
        if slug:
            q = q.where(ImageCandidate.slug == slug)
        if laura_only:
            q = q.where(ImageCandidate.laura_present == True)  # noqa: E712
        return list(s.scalars(q.order_by(desc(ImageCandidate.id))))


def listing_image_verdicts(db, *, slug: str | None = None) -> list[dict]:
    """Per listing image: did it pass BOTH Model Identity and Product Truth?"""
    out = []
    for r in _image_rows(db, slug=slug):
        c = r.checks or {}
        ident = _st(c, "identity") if r.laura_present else "NOT_APPLICABLE"
        truth = _st(c, "product_truth")
        out.append({"listing": r.listing, "slug": r.slug, "role": r.role, "sha256": r.sha256,
                    "laura_present": bool(r.laura_present), "model_identity": ident,
                    "product_truth": truth,
                    "passed_both": truth == "PASS" and ident in ("PASS", "NOT_APPLICABLE"),
                    "publishable": bool(r.publishable)})
    return out


def canonical_model(db) -> dict:
    from . import canonical_registry, model_rnd, provider_routing

    reg = canonical_registry.resolve(db)
    rows = _image_rows(db, laura_only=True)[:RECENT]

    def _yield(key):
        judged = [_st(r.checks or {}, key) for r in rows]
        judged = [x for x in judged if x in ("PASS", "FAIL")]
        return ({"pass": sum(x == "PASS" for x in judged), "judged": len(judged),
                 "rate": round(sum(x == "PASS" for x in judged) / len(judged), 4)}
                if judged else {"state": ABSENT, "why": "no judged on-model frame yet"})

    drift = [{"sha256": r.sha256, "listing": r.listing, "provider": r.provider,
              "why": str(((r.checks or {}).get("identity") or {}).get("why") or "")[:300]}
             for r in rows if _st(r.checks or {}, "identity") == "FAIL"
             or _st(r.checks or {}, "body_proportions") == "FAIL"][:10]
    try:
        from ..experiments import controlled

        controlled_board = controlled.board(db)
    except Exception as exc:  # noqa: BLE001 - shown as absent, not as zero experiments
        controlled_board = {"state": ABSENT, "why": f"{type(exc).__name__}"}
    route = provider_routing.route(db)
    images = listing_image_verdicts(db)
    return {
        "canonical": {"identity_id": reg.get("identity_id"), "revision": reg.get("revision"),
                      "verified": reg["ok"], "problems": reg["problems"]},
        "best_provider_mode": {k: route.get(k) for k in ("provider", "model", "basis", "why")},
        "recent_yield": {"window": len(rows), "identity": _yield("identity"),
                         "realism": _yield("realism")},
        "rejected_drift_examples": drift or {"state": ABSENT,
                                             "why": "no on-model frame failed identity"},
        "active_improvement_experiments": {
            "proposals": [p for p in model_rnd.active(db)
                          if p.get("state") in ("awaiting_controlled_experiment", "ran")],
            "controlled_runs": controlled_board},
        "listing_images": images,
        "listing_images_passing_both": sum(1 for i in images if i["passed_both"]),
    }


def evidence_panel(db, slug: str) -> dict:
    from . import conditioning_matrix, launch_imagery
    from .image_records import ImageProductionRun, ensure_tables

    rows = _image_rows(db, slug=slug)
    refs: dict[str, list] = {}
    receipts = []
    for r in rows:
        for ref in r.references or []:
            kind = str(ref.get("kind") or "other")
            if ref.get("sha256") and ref["sha256"] not in refs.setdefault(kind, []):
                refs[kind].append(ref["sha256"])
        ev = (r.checks or {}).get("_identity_evidence") or {}
        if ev.get("conditioning"):
            receipts.append({"candidate_sha256": r.sha256, "conditioning": ev["conditioning"]})
    imagery = launch_imagery.last(db, slug)
    three_d = ({"version": imagery.get("version"),
                "disclosed": {s: [f.get("sha256") for f in (d.get("frames") or [])]
                              for s, d in (imagery.get("disclosed") or {}).items()},
                "gallery_frames": [{"job": f.get("job"), "sha256": f.get("sha256"),
                                    "verification": f.get("verification")}
                                   for f in imagery.get("gallery_frames") or []]}
               if imagery else {"state": ABSENT, "why": "no registered 3D imagery set"})
    generated, rejected = [], []
    for r in rows:
        c = r.checks or {}
        item = {"sha256": r.sha256, "role": r.role, "provider": r.provider,
                "attempt": r.attempt, "outcome": r.outcome,
                "technical_status": r.technical_status}
        generated.append(item)
        if r.outcome == "rejected" or r.technical_status == "FAIL":
            rejected.append({**item, "failure_categories": list(r.failure_categories or []),
                             "reasons": {k: str(v.get("why") or "")[:200] for k, v in c.items()
                                         if isinstance(v, dict) and v.get("status") == "FAIL"}})
    ensure_tables(db)
    from sqlalchemy import desc, select

    with db.session() as s:
        run = s.scalar(select(ImageProductionRun).where(ImageProductionRun.slug == slug)
                       .order_by(desc(ImageProductionRun.id)).limit(1))
        run_state = ({"run_key": run.run_key, "status": run.status,
                      "owner_decision": dict(run.owner_decision or {})} if run else None)
    approved = [{"sha256": r.sha256, "role": r.role} for r in rows
                if r.publishable and (run_state or {}).get("status") ==
                "approved_for_publication"]
    trials = [t for t in conditioning_matrix.matrix(db) if t["trials"]]
    return {
        "slug": slug,
        "real_benchmark_reference": refs.get("physical_product_photo") or {
            "state": ABSENT, "why": "no physical product photograph was used as a reference"},
        "brambleloop_3d": three_d,
        "conditioning_passes": {"references_by_kind": refs, "receipts": receipts,
                                "matrix_trials": trials} if (refs or receipts or trials) else
        {"state": ABSENT, "why": "no candidate recorded its conditioning"},
        "generated_candidates": generated or {"state": ABSENT, "why": "nothing generated"},
        "rejected_candidates": rejected,
        "final_approved_asset": approved or {
            "state": ABSENT, "why": ("no gallery approved for publication"
                                     + (f" (run {run_state['status']})" if run_state else ""))},
        "run": run_state,
    }
