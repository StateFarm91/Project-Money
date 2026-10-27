"""F-737 Canonical Model Improvement Loop + F-745 Autonomous Model R&D (W4-C08), with the
F-738 rollback trigger acted on.

F-737: "Visual/Brand agents continuously improve the canonical model system: realism,
skin/hair detail, lighting response, pose range, expression consistency, anatomy, garment
interaction, camera realism, cross-view consistency and provider conditioning. Improvements
must make the same model more convincing - not evolve her into a different person."

F-745: "When safe capacity exists, Visual/Brand agents continuously search for measurable ways
to make the canonical model more realistic and more consistent. They may run bounded
experiments under spend/governance policy without waiting for an owner prompt, while
customer-facing promotion remains gated by evidence and authority."

The cell runs inside the existing 6-hourly Visual R&D cycle (`visual.rnd.loop.cycle`, job
`visual.rnd.cycle`), so it needs no new cadence, and it reuses rather than rebuilds:
* evidence -- the F-744 ledger (`model_ledger`) and `image_candidates`;
* the identity anchor -- `canonical_registry.require_current` (F-733): every proposal is bound
  to the verified current identity id, never a remembered one;
* promotion -- `model_promotion.compare` (equal-or-better identity AND better realism, owner
  decision required); the identity change itself stays `model_registry.replace_canonical`;
* paid work -- only `experiments.controlled` (frozen definition, owner authorization and
  step-up, its caps plus every gateway reservation and ceiling). This module never calls a
  provider and never reserves: a paid arm is a recorded proposal that waits for that door.

One cycle (`cycle(db)`):
1. **capacity** -- refuses to start new work while the publishing agent's queue is backed up
   (`MAX_BACKLOG`) or a visual-identity incident is open: safe capacity first;
2. **diagnose** -- a pass rate per improvement axis from recorded checks; an axis nobody
   measures is UNMEASURED and its proposal is a CA$0 instrumentation task;
3. **propose** -- one bounded experiment for the weakest axis (idempotent per axis and
   identity), refused outright if it would touch a locked identity field (face, hair, eyes,
   age, facial structure...): improvements make her more convincing, never different;
4. **CA$0 experiments run now** (re-reading recorded evidence: no spend, no owner prompt);
   paid arms are recorded `awaiting_controlled_experiment`;
5. **rollback watch** (F-738) -- the newest canonical version against its predecessor; a loss
   of identity retention or realism opens one incident naming the retired predecessor to
   restore (by owner decision), and the incident resolves when it holds again.
"""
from __future__ import annotations

from datetime import datetime, timezone

KIND_PROPOSAL = "visual.model_rnd"
REGRESSION_SIGNATURE = "visual.canonical_regression:"
MAX_BACKLOG = 25
AXES: tuple[str, ...] = (
    "realism", "skin_hair_detail", "lighting_response", "pose_range",
    "expression_consistency", "anatomy", "garment_interaction", "camera_realism",
    "cross_view_consistency", "provider_conditioning")
# axis -> the recorded candidate checks (visual.candidate_gates.CHECKS) that measure it, plus
# the failure-reason words that attribute a realism failure to a finer axis.
AXIS_CHECKS: dict[str, tuple[str, ...]] = {
    "realism": ("realism",), "anatomy": ("anatomy",),
    "garment_interaction": ("product_truth", "outfit"),
    "cross_view_consistency": ("identity", "body_proportions"),
}
AXIS_WORDS: dict[str, tuple[str, ...]] = {
    "skin_hair_detail": ("skin", "hair", "pore", "smooth"),
    "lighting_response": ("light", "shadow", "exposure"),
    "camera_realism": ("lens", "depth of field", "bokeh", "camera", "focus"),
    "expression_consistency": ("expression", "smile"),
    "pose_range": ("pose", "copy-paste", "sameness"),
}
# Changes a proposal may make: how she is rendered, never who she is.
ALLOWED_CHANGES = frozenset({"prompt_version", "conditioning_order", "reference_crop",
                             "lighting_brief", "camera_brief", "pose_brief",
                             "expression_brief", "provider", "mode", "post_processing",
                             "judge_rubric"})


class ProposalRefused(ValueError):
    """A proposal that would change her identity, or one without a verified identity."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def refuse_identity_change(changes: dict) -> None:
    from . import canonical

    locked = {str(x).lower() for x in canonical.LOCKED}
    bad = sorted(k for k in changes if k.lower() in locked or k not in ALLOWED_CHANGES)
    if bad:
        raise ProposalRefused(f"changes {bad} are not rendering changes; an improvement must "
                              f"make the same Laura more convincing, never a different person")


def capacity(db) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Incident, Job, JobStatus

    with db.session() as s:
        backlog = int(s.scalar(select(func.count()).select_from(Job).where(
            Job.agent == "publishing",
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))) or 0)
        open_identity = [i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved == False))  # noqa: E712
            if str(i.signature).startswith(("visual.identity_drift", REGRESSION_SIGNATURE))]
    ok = backlog <= MAX_BACKLOG and not open_identity
    return {"safe": ok, "publishing_backlog": backlog, "open_identity_incidents": open_identity,
            "why": ("capacity available" if ok else
                    "customer work or an identity incident comes first")}


def diagnose(db) -> dict:
    from sqlalchemy import select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    tally = {a: [0, 0] for a in AXES}        # [judged, passed]
    with db.session() as s:
        rows = [(r.checks or {}) for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.laura_present == True))]  # noqa: E712
    for checks in rows:
        for axis, keys in AXIS_CHECKS.items():
            st = [str((checks.get(k) or {}).get("status")) for k in keys]
            st = [x for x in st if x in ("PASS", "FAIL")]
            if st:
                tally[axis][0] += 1
                tally[axis][1] += int(all(x == "PASS" for x in st))
        realism = checks.get("realism") or {}
        if str(realism.get("status")) in ("PASS", "FAIL"):
            why = str(realism.get("why") or "").lower()
            for axis, words in AXIS_WORDS.items():
                if realism["status"] == "PASS":
                    tally[axis][0] += 1
                    tally[axis][1] += 1
                elif any(w in why for w in words):
                    tally[axis][0] += 1
        ev = (checks.get("_identity_evidence") or {}).get("request") or {}
        if "conditioning_proven" in ev:
            tally["provider_conditioning"][0] += 1
            tally["provider_conditioning"][1] += int(bool(ev["conditioning_proven"]))
    axes = {a: ({"judged": n, "pass_rate": round(p / n, 4)} if n else
                {"judged": 0, "pass_rate": None, "state": "UNMEASURED"})
            for a, (n, p) in tally.items()}
    measured = sorted((a for a in AXES if axes[a]["pass_rate"] is not None),
                      key=lambda a: (axes[a]["pass_rate"], AXES.index(a)))
    return {"axes": axes, "weakest": measured[:3],
            "unmeasured": [a for a in AXES if axes[a]["pass_rate"] is None]}


def _proposal_for(axis: str, diag: dict, identity_id: str) -> dict:
    a = diag["axes"][axis]
    if a["pass_rate"] is None:
        return {"axis": axis, "identity_id": identity_id, "kind": "instrumentation",
                "cost_class": "free", "estimated_cost_cad": 0.0, "changes": {},
                "hypothesis": f"{axis} is never measured; add it to the recorded checks "
                              f"before any spend is spent improving it"}
    change = {"realism": {"post_processing": "none"},
              "skin_hair_detail": {"prompt_version": "skin-texture-explicit"},
              "lighting_response": {"lighting_brief": "window light, one source"},
              "pose_range": {"pose_brief": "rotate seated/standing/walking"},
              "expression_consistency": {"expression_brief": "relaxed, mouth closed"},
              "anatomy": {"judge_rubric": "hands-and-fingers explicit"},
              "garment_interaction": {"reference_crop": "garment-first"},
              "camera_realism": {"camera_brief": "50mm, f/2.8, natural depth"},
              "cross_view_consistency": {"conditioning_order": "face,torso,full"},
              "provider_conditioning": {"conditioning_order": "face,torso,full"}}[axis]
    return {"axis": axis, "identity_id": identity_id, "kind": "controlled_render_comparison",
            "cost_class": "paid", "changes": change,
            "hypothesis": (f"{axis} passes {a['pass_rate']:.0%} of {a['judged']} judged "
                           f"frames; {change} should raise it with identity held"),
            "arms": ["incumbent canonical rendering", f"incumbent + {change}"],
            "success": "model_promotion.compare == PROMOTE (identity >=, realism >)",
            "door": "experiments.controlled (frozen definition, owner authorization, step-up)"}


def _replay(db, proposal: dict) -> dict:
    """The CA$0 experiment: re-read the recorded evidence for the axis under the proposal."""
    from . import model_ledger

    harvested = model_ledger.harvest(db)
    return {"ran": True, "spent_cad": 0.0, "harvested": harvested["harvested"],
            "reading": diagnose(db)["axes"].get(proposal["axis"])}


def regression_watch(db, *, records: list[dict] | None = None) -> dict:
    """F-738: a newest canonical version that lost identity or realism triggers rollback."""
    from ..ops import incident_lifecycle as lifecycle
    from . import model_ledger, model_promotion as MP

    recs = records if records is not None else model_ledger.ledger(db, limit=100000)
    first_seen: dict[str, str] = {}
    for r in recs:
        v = str(r.get("canonical_version"))
        if v in ("UNKNOWN", "None"):
            continue
        at = str(r.get("at") or "")
        if v not in first_seen or at < first_seen[v]:
            first_seen[v] = at
    versions = sorted(first_seen, key=lambda v: first_seen[v])
    summaries = [MP.summarise(recs, v) for v in versions]
    ready = [s for s in summaries if min(s["identity_judged"], s["realism_judged"])
             >= MP.MIN_FRAMES]
    if len(ready) < 2:
        out = {"verdict": "UNKNOWN", "rollback": False, "versions": versions,
               "why": "fewer than two canonical versions with enough judged frames"}
    else:
        before, after = ready[-2], ready[-1]
        out = {**MP.regression(after, before), "candidate": after["version"],
               "restore": before["version"], "versions": versions}
    sig = REGRESSION_SIGNATURE + str(out.get("candidate", ""))
    with db.session() as s:
        life = lifecycle.reconcile(
            s, REGRESSION_SIGNATURE,
            lambda inc: out.get("rollback") and inc.signature == sig,
            resolution="the newest canonical version holds identity and realism again")
        opened = False
        if out.get("rollback"):
            _r, opened = lifecycle.open_or_restate(
                s, signature=sig, severity="P2", halts_publication=False,
                summary=(f"canonical version {out['candidate']} regressed on "
                         f"{', '.join(out['lost'])} against {out['restore']}: roll back by "
                         f"restoring the retired predecessor (owner decision; "
                         f"model_registry retires, never deletes)"),
                detail={k: out.get(k) for k in ("candidate", "restore", "lost")})
    return {**out, "incident_opened": opened, "incidents_resolved": life["resolved"]}


def cycle(db, *, now: datetime | None = None) -> dict:
    """One pass of the improvement loop. Never spends; never promotes."""
    from sqlalchemy import select

    from ..core.models import OperatingReading
    from . import canonical_registry

    now = now or _now()
    watch = regression_watch(db)
    cap = capacity(db)
    if not cap["safe"]:
        return {"ran": False, "capacity": cap, "regression": watch, "spent_cad": 0.0}
    try:
        identity_id = canonical_registry.current_identity_id(db)
    except Exception as exc:  # noqa: BLE001 - no verified identity, no improvement work
        return {"ran": False, "why": f"canonical registry refused: {exc}"[:300],
                "regression": watch, "spent_cad": 0.0}
    diag = diagnose(db)
    order = diag["weakest"] + diag["unmeasured"]
    made = []
    with db.session() as s:
        held = {k for (k,) in s.execute(select(OperatingReading.period_key).where(
            OperatingReading.kind == KIND_PROPOSAL)).all()}
    for axis in order:
        key = f"{axis[:11]}:{identity_id[-8:]}"
        if key in held:
            continue
        prop = _proposal_for(axis, diag, identity_id)
        refuse_identity_change(prop["changes"])
        if prop["cost_class"] == "free":
            prop["state"], prop["result"] = "ran", _replay(db, prop)
        else:
            prop["state"] = "awaiting_controlled_experiment"
        prop["at"] = now.isoformat()
        with db.session() as s:
            s.add(OperatingReading(kind=KIND_PROPOSAL, period_key=key, payload=prop))
        made.append({k: prop[k] for k in ("axis", "kind", "state", "cost_class")})
        break                                  # one bounded proposal per cycle
    return {"ran": True, "capacity": cap, "identity_id": identity_id,
            "diagnosis": diag, "proposed": made, "regression": watch, "spent_cad": 0.0,
            "promotion": "owner decision via model_promotion.compare; never here"}


def active(db) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        return [dict(r.payload or {}) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == KIND_PROPOSAL)
            .order_by(desc(OperatingReading.id)).limit(50))]
