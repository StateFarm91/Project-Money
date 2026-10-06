"""The Visual R&D department loop (owner directive §9-§12): permanent, self-improving.

    GENERATE -> PRODUCT TRUTH -> STRUCTURAL/IDENTITY VALIDATION -> PHOTOREALISM ->
    COMMERCIAL/BLIND BENCHMARK JUDGMENT -> FAILURE DIAGNOSIS -> CHALLENGER -> CONTROLLED TEST ->
    PROMOTE/REJECT -> MONITOR -> ROLLBACK IF WORSE -> PERSIST LESSON -> AFFECT FUTURE
    GENERATION -> REPEAT

Where each step lives:

* GENERATE / the gates: `gates.produce` + `gates.judge_frame` (existing independent gates).
* FAILURE DIAGNOSIS: `diagnose` -- failure taxonomy, accepted-image yield, hero prominence.
* CHALLENGER: `propose` -- the next untried value of a declared tunable, ordered by diagnosis,
  skipping what a persisted lesson rules out and parameters the marketplace overturned.
* CONTROLLED TEST: `experiment` -- incumbent and challenger on the same fixed task set (every
  product of the class), judged by the same gates; `compare` uses the league's margins
  (`improve.league`), and no gain is allowed to buy a gate failure or a yield drop.
* PROMOTE/REJECT: `pipeline.promote` / candidate `rejected`, both with a lesson.
* MONITOR / ROLLBACK IF WORSE: `monitor` -- production judgements after a promotion against
  the reading of the version it replaced; worse rolls back to that version.
* SLOW LOOP: `record_market` + `calibrate` -- impressions, clicks, favourites, carts,
  purchases, refunds per version. A significantly worse marketplace reading OVERTURNS an
  internal promotion: rollback, a lesson, and the parameter is struck from the class's
  internal search until the marketplace says otherwise -- internal judges accelerate R&D and
  never substitute for commercial evidence.
* AFFECT FUTURE GENERATION: `generate` reads the incumbent version; every image row carries the
  version id that made it.

Two speeds, one rule for money: deterministic challengers run locally for free; any challenger
that varies a paid stage (provider/model, lighting, camera, composition, crop, control, Laura
reproduction) is *planned and queued* as `GATED_SPEND` with an estimated cost and is never
executed here -- `paid_execution_gate()` is closed (no owner spend authority; shadow phase).
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import gates as G
from . import models as M
from . import pipeline as P

# Experiment states.
PROMOTED, REJECTED, REFUSED, MEMORY_SKIPPED = "PROMOTED", "REJECTED", "REFUSED", "MEMORY_SKIPPED"
GATED_SPEND, ROLLED_BACK, OVERTURNED = "GATED_SPEND", "ROLLED_BACK", "OVERTURNED"
EXPERIMENT_STATES = (PROMOTED, REJECTED, REFUSED, MEMORY_SKIPPED, GATED_SPEND, ROLLED_BACK,
                     OVERTURNED)

# How far production may fall below the reading of the version a promotion replaced before
# the promotion is rolled back (yield and task score, absolute).
REGRESSION_TOLERANCE = 0.05
# Slow loop: per-version impressions before CTR is compared at all, clicks before conversion,
# purchases before refund rate, and the two-proportion z beyond which a difference counts.
MARKET_MIN_IMPRESSIONS = 200
MARKET_MIN_CLICKS = 100
MARKET_MIN_PURCHASES = 20
MARKET_Z = 1.96
# Wall-clock latency on a shared machine jitters by seconds (cold imports, other workers), so
# the league's latency ratio only blocks when the extra time per task also exceeds this.
LATENCY_NOISE_FLOOR_S = 5.0
# A challenger must cut bytes this much (at equal quality and yield) to win on efficiency.
BYTES_EFFICIENCY = 0.9
LESSON_MEMORY_DAYS = 30
OVERTURN_MEMORY_DAYS = 180
# Images a paid experiment would generate per arm (for its cost estimate only).
PLANNED_PAID_IMAGES = 6
DETERMINISTIC_COST_BASIS = "measured: deterministic local render, no provider call"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------- catalogue

def catalogue(builds=None) -> dict[str, list]:
    """Certified CIRs by product class (Launch-0 builders; `builds` narrows it)."""
    from ...products import launch0

    keys = list(builds) if builds else sorted(launch0.BUILDERS)
    out: dict[str, list] = {}
    for b in keys:
        cir = launch0.cir_for(b)
        out.setdefault(P.classify(cir), []).append(cir)
    return out


def catalogue_fp(cirs) -> str:
    return hashlib.sha256("|".join(sorted(c.fingerprint for c in cirs)).encode()).hexdigest()


# ---------------------------------------------------------------------------- judgements

def _record(db, **row) -> int:
    with M.session(db) as s:
        r = M.VisualJudgement(**row)
        s.add(r)
        s.flush()
        return r.id


def run_arm(db, product_class: str, version: dict, cirs, *, experiment_id=None,
            arm: str = "production") -> dict:
    """Make and judge every product's gallery with one version; persist every judgement."""
    M.ensure_tables(db)
    fp = catalogue_fp(cirs)
    tasks, failures = {}, Counter()
    frames_n = accepted_n = bytes_n = 0
    latency = 0.0
    galleries = []
    for cir in cirs:
        frames = G.produce(cir, version["params"])
        judged = []
        for i, f in enumerate(frames):
            j = G.judge_frame(cir, f, i + 1, product_class)
            judged.append(j)
            frames_n += 1
            accepted_n += int(j["accepted"])
            bytes_n += f["bytes"]
            latency += f["latency_s"]
            failures.update(j["failures"])
            _record(db, pipeline_id=version["id"], experiment_id=experiment_id, arm=arm,
                    product_class=product_class, subject=f"{cir.slug}@{cir.version}:{f['view']}",
                    image_sha256=f["sha256"], gates=j["gates"], accepted=j["accepted"],
                    failures=j["failures"], metrics=j["metrics"], latency_s=f["latency_s"],
                    cost_cad=0.0, cost_basis=DETERMINISTIC_COST_BASIS,
                    source="deterministic_disclosed_render")
        gc = G.gallery_contract(frames)
        ok = all(j["accepted"] for j in judged) and gc["status"] == G.PASS
        sc = G.score(ok, judged[0]["metrics"].get("mobile_ink_share"))
        g_fail = sorted({x for j in judged for x in j["failures"]}
                        | ({f"GALLERY_CONTRACT:{gc['status']}"} if gc["status"] != G.PASS
                           else set()))
        subject = f"{cir.slug}@{cir.version}"
        _record(db, pipeline_id=version["id"], experiment_id=experiment_id, arm=arm,
                product_class=product_class, subject=f"{subject}:gallery",
                image_sha256=frames[0]["sha256"], gates={"gallery_contract": gc},
                accepted=ok, failures=g_fail, score=sc,
                metrics={"hero_mobile_ink_share": judged[0]["metrics"].get("mobile_ink_share"),
                         "frames": len(frames), "catalogue_fp": fp,
                         "frame_sha256": [f["sha256"] for f in frames]},
                latency_s=round(sum(f["latency_s"] for f in frames), 4), cost_cad=0.0,
                cost_basis=DETERMINISTIC_COST_BASIS, source="deterministic_disclosed_render")
        tasks[subject] = sc
        galleries.append({"subject": subject, "accepted": ok, "score": sc,
                          "failures": g_fail,
                          "frames": [{"view": f["view"], "sha256": f["sha256"],
                                      "accepted": j["accepted"]}
                                     for f, j in zip(frames, judged)]})
    return {"version_id": version["id"], "label": version["label"], "tasks": tasks,
            "quality": round(sum(tasks.values()) / len(tasks), 4) if tasks else None,
            "frames": frames_n, "accepted_frames": accepted_n,
            "yield": round(accepted_n / frames_n, 4) if frames_n else None,
            "bytes": bytes_n, "latency_s": round(latency, 4), "cost_cad": 0.0,
            "failures": dict(failures), "galleries": galleries, "catalogue_fp": fp}


def record_judgement(db, product_class: str, *, subject: str, gates: dict,
                     pipeline_id: int | None = None, identity_scored: dict | None = None,
                     score: float | None = None, latency_s: float | None = None,
                     cost_cad: float | None = None, cost_basis: str = "unknown",
                     source: str, arm: str = "production", experiment_id=None,
                     image_sha256: str = "", metrics: dict | None = None,
                     identity_evidence: dict | None = None,
                     product_evidence: dict | None = None) -> dict:
    """Record an image judged outside the deterministic path (a paid generation once
    authorised, a vision judge, an owner review). Gates not supplied are UNKNOWN, which
    blocks. For model-bearing classes the Laura identity gate is computed here -- a caller
    cannot hand in a PASS for it -- by `visual.identity_gate.assess` (K12: F-213 trial
    validity, F-219 review band, F-732 exact identity) on `identity_evidence`, or on the
    single per-dimension reading `identity_scored` (one judge: never a pass). A REVIEW-band
    result opens a human identity review. Product truth and structure for model-bearing
    images are computed by `visual.final_image_gate.evaluate` on `product_evidence`
    (F-677): deterministic evidence only; a caller-supplied PASS is overridden."""
    if not (source or "").strip():
        raise ValueError("a judgement names where it came from")
    M.ensure_tables(db)
    version = (P.get(db, pipeline_id) if pipeline_id else P.ensure_incumbent(db, product_class))
    g = {k: dict(v) for k, v in (gates or {}).items()}
    ident = None
    if product_class in P.MODEL_BEARING_CLASSES:
        from .. import final_image_gate, identity_gate

        ident = identity_gate.assess(identity_evidence if identity_evidence is not None
                                     else identity_gate.single_reading(identity_scored))
        g["laura_identity"] = {"status": ident["status"], "why": ident["why"],
                               "band": ident["band"], "failed": ident["failed"],
                               "validity": ident["validity"]["validity"]}
        truth = final_image_gate.evaluate(product_evidence)
        for name in ("product_truth", "structure"):
            g[name] = {"status": truth["status"], "why": truth["why"],
                       "attributes": truth["attributes"],
                       "failed": [a for a, v in truth["attributes"].items() if v == "FAIL"]}
    else:
        g.setdefault("laura_identity", {"status": G.NA, "why": "product-only class"})
        g.setdefault("anatomy", {"status": G.NA, "why": "product-only class"})
    if subject.endswith(":gallery"):
        g = {"gallery_contract": g.get("gallery_contract") or {"status": G.UNKNOWN}}
        failures = [] if g["gallery_contract"]["status"] == G.PASS else [
            f"GALLERY_CONTRACT:{g['gallery_contract']['status']}"]
        failures += list((metrics or {}).get("frame_failures") or [])
        out = {"gates": g, "accepted": not failures, "failures": failures,
               "metrics": dict(metrics or {})}
    else:
        out = G.finish(g, metrics=metrics)
    sc = (float(score) if score is not None and out["accepted"] else
          (0.0 if subject.endswith(":gallery") else None))
    rid = _record(db, pipeline_id=version["id"], experiment_id=experiment_id, arm=arm,
                  product_class=product_class, subject=subject, image_sha256=image_sha256,
                  gates=out["gates"], accepted=out["accepted"], failures=out["failures"],
                  score=sc, metrics=out["metrics"], latency_s=latency_s, cost_cad=cost_cad,
                  cost_basis=cost_basis, source=source.strip())
    review = None
    if ident is not None and ident.get("review_required"):
        from .. import identity_gate
        review = identity_gate.open_review(db, product_class=product_class, subject=subject,
                                           gate=ident, image_sha256=image_sha256,
                                           judgement_id=rid)
    return {"id": rid, "pipeline_id": version["id"], **out, "score": sc,
            "identity_review": review}


# ---------------------------------------------------------------------------- lessons

def _lesson(db, product_class: str, kind: str, params: dict, statement: str, ref: str) -> None:
    with M.session(db) as s:
        s.add(M.VisualLesson(product_class=product_class, kind=kind, params=params,
                             statement=statement[:4000], ref=ref[:160]))


def lessons(db, product_class: str | None = None, *, limit: int = 50) -> list[dict]:
    from sqlalchemy import select

    if not M.tables_exist(db):
        return []
    with M.session(db) as s:
        q = select(M.VisualLesson).order_by(M.VisualLesson.id.desc()).limit(limit)
        if product_class:
            q = q.where(M.VisualLesson.product_class == product_class)
        return [{"id": r.id, "at": _aware(r.at).isoformat(), "product_class": r.product_class,
                 "kind": r.kind, "params": r.params, "statement": r.statement, "ref": r.ref}
                for r in s.scalars(q)]


def _canon(changes: dict) -> dict:
    from ...improve import invariants
    return {invariants.canonical_key(k): v for k, v in (changes or {}).items()}


def remembered(db, product_class: str, changes: dict, *, catalogue: str = "",
               now: datetime | None = None) -> dict | None:
    """A lesson that says not to try this again (same change; same catalogue unless the
    marketplace overturned it, which holds for every catalogue)."""
    now = now or _now()
    want = _canon(changes)
    for les in lessons(db, product_class, limit=500):
        if les["kind"] not in (REJECTED.lower(), REFUSED.lower(), "rolled_back", "overturned"):
            continue
        days = OVERTURN_MEMORY_DAYS if les["kind"] == "overturned" else LESSON_MEMORY_DAYS
        if now - datetime.fromisoformat(les["at"]) > timedelta(days=days):
            continue
        if (les["params"] or {}).get("changes") != want:
            continue
        if les["kind"] in ("overturned", REFUSED.lower()) or \
                (les["params"] or {}).get("catalogue") in ("", catalogue):
            return les
    return None


def overturned_params(db, product_class: str, *, now: datetime | None = None) -> set[str]:
    """Parameters the marketplace overturned for this class: the internal judge is not
    trusted on them, so the internal search stops proposing them."""
    now = now or _now()
    out = set()
    for les in lessons(db, product_class, limit=500):
        if les["kind"] == "overturned" and \
                now - datetime.fromisoformat(les["at"]) <= timedelta(days=OVERTURN_MEMORY_DAYS):
            out.update((les["params"] or {}).get("changes", {}).keys())
    return out


# ---------------------------------------------------------------------------- diagnosis

def _production(db, version_id: int, *, after=None, arms=("production",)) -> list:
    from sqlalchemy import select

    with M.session(db) as s:
        q = select(M.VisualJudgement).where(M.VisualJudgement.pipeline_id == version_id,
                                            M.VisualJudgement.arm.in_(arms))
        rows = list(s.scalars(q.order_by(M.VisualJudgement.id)))
        if after is not None:
            rows = [r for r in rows if _aware(r.at) >= _aware(after)]
        return [{"id": r.id, "subject": r.subject, "accepted": r.accepted, "failures": list(r.failures or []),
                 "score": r.score, "metrics": dict(r.metrics or {}), "at": _aware(r.at),
                 "gates": dict(r.gates or {})} for r in rows]


def _readings(rows: list[dict]) -> dict:
    frames = [r for r in rows if not r["subject"].endswith(":gallery")]
    galleries = [r for r in rows if r["subject"].endswith(":gallery")]
    return {"frames": len(frames), "galleries": len(galleries),
            "yield": (round(sum(r["accepted"] for r in frames) / len(frames), 4)
                      if frames else None),
            "quality": (round(sum(r["score"] or 0.0 for r in galleries) / len(galleries), 4)
                        if galleries else None),
            "failures": dict(Counter(f for r in frames for f in r["failures"]))}


def diagnose(db, product_class: str) -> dict:
    """FAILURE DIAGNOSIS: what is wrong with the class's current images, and where to look."""
    inc = P.ensure_incumbent(db, product_class)
    rd = _readings(_production(db, inc["id"]))
    findings, stages = [], []
    if rd["frames"] == 0:
        findings.append("no production judgement yet for the incumbent")
    fail = rd["failures"]
    structural = {k: v for k, v in fail.items() if k.startswith(("STRUCTURE", "PRODUCT_TRUTH"))}
    if structural:
        findings.append(f"structural/product-truth rejections {structural}")
        stages += ["post_processing", "encode", "renderer_layout"]
    if any(k.startswith(("COMPOSITION", "MOBILE_THUMBNAIL")) for k in fail):
        findings.append("composition / thumbnail failures")
        stages += ["renderer_layout", "crop_thumbnail", "composition"]
    if rd["quality"] is not None and rd["quality"] < 1.0:
        findings.append(f"hero thumbnail prominence score {rd['quality']} < 1.0")
        stages += ["renderer_layout", "crop_thumbnail"]
    if product_class in P.MODEL_BEARING_CLASSES or product_class not in P.DISCLOSED_CLASSES:
        findings.append("no free deterministic producer for this class; the generated "
                        "path's photorealism/identity readings are unjudged (paid, gated)")
        stages += ["laura_reproduction", "provider_model", "control_method", "lighting"]
    stages += ["encode", "post_processing", "renderer_layout", "provider_model", "lighting",
               "camera", "composition", "crop_thumbnail", "control", "laura_reproduction"]
    ordered = list(dict.fromkeys(stages))
    return {"product_class": product_class, "incumbent": inc["label"], "readings": rd,
            "findings": findings, "stage_order": ordered,
            "overturned_params": sorted(overturned_params(db, product_class))}


def propose(db, product_class: str, diagnosis: dict, *, catalogue: str = "",
            execution: str = P.DETERMINISTIC) -> dict | None:
    """CHALLENGER: the next untried value, by diagnosed stage, minus what lessons rule out."""
    inc = P.ensure_incumbent(db, product_class)
    banned = set(diagnosis.get("overturned_params") or [])
    for stage in diagnosis["stage_order"]:
        for t in P.applicable(product_class, execution=execution):
            if t.stage != stage or t.name in banned:
                continue
            values = list(t.trials) or [c for c in t.choices if c != t.default]
            for v in values:
                if inc["params"].get(t.name) == v:
                    continue
                change = {t.name: v}
                if remembered(db, product_class, change, catalogue=catalogue):
                    continue
                return change
    return None


# ---------------------------------------------------------------------------- controlled test

def compare(inc: dict, ch: dict, *, census: bool) -> dict:
    """PROMOTE/REJECT on the shared task set, with the league's margins (#95, #180).

    Truth first: any gate failure the incumbent did not have, or any accepted-yield drop,
    rejects whatever else improved. Quality must then beat `improve.league.required_margin`
    for the task count; when the arms are deterministic and the task set is the class's whole
    current catalogue (a census, not a sample) the flat `QUALITY_MARGIN` applies, because
    re-measurement is exact and there is no unsampled current product -- future products are
    covered by MONITOR. Latency uses the league's tolerance; bytes stand in for storage cost.
    """
    from ...improve import league

    shared = sorted(inc["tasks"])
    if sorted(ch["tasks"]) != shared:
        return {"promote": False, "reason": "incomplete", "blockers": [
            "the challenger was not judged on exactly the incumbent's task set"]}
    blockers = []
    new_fail = sorted(set(ch["failures"]) - set(inc["failures"]))
    if new_fail:
        blockers.append(f"gate failures the incumbent does not have: {new_fail}")
    if (ch["yield"] or 0) < (inc["yield"] or 0):
        blockers.append(f"accepted-image yield fell {inc['yield']} -> {ch['yield']}")
    gain = round((ch["quality"] or 0) - (inc["quality"] or 0), 4)
    margin = league.QUALITY_MARGIN if census else league.required_margin(len(shared))
    lat_ratio = (ch["latency_s"] / inc["latency_s"]) if inc["latency_s"] else 1.0
    bytes_ratio = (ch["bytes"] / inc["bytes"]) if inc["bytes"] else 1.0
    efficiency = abs(gain) < 1e-9 and bytes_ratio <= BYTES_EFFICIENCY
    if not blockers and gain <= margin and not efficiency:
        blockers.append(f"quality gain {gain:+.4f} does not exceed the {margin:.4f} margin for "
                        f"{len(shared)} task(s) and bytes ratio {bytes_ratio:.3f} is no "
                        f"efficiency win")
    lat_extra = (ch["latency_s"] - inc["latency_s"]) / max(1, len(shared))
    if not blockers and lat_ratio > league.LATENCY_TOLERANCE and \
            lat_extra > LATENCY_NOISE_FLOOR_S:
        need = margin * 2 * (lat_ratio / league.LATENCY_TOLERANCE)
        if gain <= need:
            blockers.append(f"{lat_ratio:.2f}x the incumbent's latency for {gain:+.4f}, "
                            f"where {need:.4f} would be needed")
    return {"promote": not blockers, "blockers": blockers, "quality_gain": gain,
            "required_margin": round(margin, 4), "census": census,
            "tasks_compared": len(shared), "latency_ratio": round(lat_ratio, 3),
            "latency_extra_s_per_task": round(lat_extra, 3),
            "bytes_ratio": round(bytes_ratio, 3), "efficiency_win": efficiency and not blockers,
            "incumbent": {k: inc[k] for k in ("version_id", "quality", "yield", "latency_s",
                                               "bytes", "failures")},
            "challenger": {k: ch[k] for k in ("version_id", "quality", "yield", "latency_s",
                                               "bytes", "failures")}}


def _experiment_row(db, **kw) -> int:
    with M.session(db) as s:
        r = M.VisualExperiment(**kw)
        s.add(r)
        s.flush()
        return r.id


def _set_experiment(db, eid: int, **kw) -> None:
    with M.session(db) as s:
        r = s.get(M.VisualExperiment, eid)
        for k, v in kw.items():
            setattr(r, k, v)


def paid_execution_gate() -> dict:
    """Closed. No owner spend authority for Visual R&D generation exists in this build."""
    import os

    return {"allowed": False,
            "phase": os.environ.get("BRAMBLELOOP_PHASE", "shadow"),
            "why": ("paid image generation needs a recorded owner spend authority for Visual "
                    "R&D (amount, provider, ceiling); none exists, and CA$ spend is forbidden "
                    "without owner approval. The experiment stays queued as GATED_SPEND")}


def _estimate_cost(changes: dict) -> tuple[float | None, str]:
    try:
        from ...gateway import images
    except Exception:  # noqa: BLE001
        return None, "unknown: image gateway unavailable"
    key = changes.get("provider_model")
    provider = images.BY_KEY.get(key) if key else None
    if provider is None:
        priced = [p for p in images.PROVIDERS if getattr(p, "usd_per_image", None)]
        if not priced:
            return None, "unknown: no listed price"
        provider = min(priced, key=lambda p: p.usd_per_image)
    cad = float(provider.usd_per_image) * float(images.USD_TO_CAD) * PLANNED_PAID_IMAGES * 2
    return round(cad, 4), (f"estimated: list price of {provider.key} x {PLANNED_PAID_IMAGES} "
                           f"images x 2 arms; not a measurement")


PAID_PASS_CRITERIA: tuple[str, ...] = (
    "every applicable non-advisory gate PASS on every challenger image (UNKNOWN blocks)",
    "accepted-image yield not below the incumbent's on the same task set",
    "quality gain exceeds improve.league.required_margin for the task count",
    "model-bearing frames: identity_gate PASS (proven current reference, judge pair, "
    "biometric floor) and final_image_gate PASS",
)
PAID_FAIL_CRITERIA: tuple[str, ...] = (
    "any gate failure the incumbent does not have",
    "any Laura identity drift (a similar woman is not Laura)",
    "any Product Truth change found by the final image gate",
    "spend would exceed max_spend_cad or calls would exceed call_count (stop, not fail open)",
)


def paid_plan(product_class: str, changes: dict, hypothesis: str) -> dict:
    """The F-877 plan for one paid visual challenger (`visual.spend_plan`)."""
    from .. import spend_plan

    est, basis = _estimate_cost(changes)
    provider = changes.get("provider_model") or ""
    if not provider:
        try:
            from ...gateway import images
            priced = [p for p in images.PROVIDERS if getattr(p, "usd_per_image", None)]
            provider = min(priced, key=lambda p: p.usd_per_image).key if priced else ""
        except Exception:  # noqa: BLE001 - no gateway: the plan says provider missing
            provider = ""
    calls = PLANNED_PAID_IMAGES * 2
    return spend_plan.build(
        hypothesis=hypothesis or f"{changes} beats the {product_class} incumbent",
        provider_model=provider, call_count=calls, max_spend_cad=est,
        price_cad_per_call=(round(est / calls, 6) if est else None),
        pass_criteria=PAID_PASS_CRITERIA, fail_criteria=PAID_FAIL_CRITERIA, basis=basis)


def experiment(db, product_class: str, changes: dict, *, hypothesis: str = "",
               diagnosis: dict | None = None, proposed_by: str = "visual.rnd",
               cirs=None, now: datetime | None = None) -> dict:
    """CHALLENGER -> guard -> CONTROLLED TEST -> PROMOTE/REJECT -> PERSIST LESSON."""
    M.ensure_tables(db)
    now = now or _now()
    inc = P.ensure_incumbent(db, product_class)
    canon = _canon(changes)
    stage = ",".join(sorted({P.TUNABLES[k].stage for k in canon if k in P.TUNABLES})) or "?"
    base = dict(product_class=product_class, incumbent_id=inc["id"], varied=canon,
                hypothesis=(hypothesis or f"{canon} beats {inc['label']}")[:2000],
                diagnosis=diagnosis or {}, stage=stage)
    refusals = P.check_change(product_class, changes)
    if refusals:
        eid = _experiment_row(db, **base, execution="none", state=REFUSED, decided_at=now,
                              result={"refusals": [r.to_dict() for r in refusals],
                                      "proposed_by": proposed_by})
        _lesson(db, product_class, REFUSED.lower(), {"changes": canon},
                f"refused {canon}: " + "; ".join(r.reason for r in refusals), f"experiment:{eid}")
        return {"experiment": eid, "state": REFUSED,
                "refusals": [r.to_dict() for r in refusals]}
    paid = sorted(k for k in canon if P.TUNABLES[k].execution == P.PAID)
    if cirs is None:
        cirs = catalogue().get(product_class, [])
    fp = catalogue_fp(cirs) if cirs else ""
    mem = remembered(db, product_class, canon, catalogue=fp, now=now)
    if mem is not None:
        eid = _experiment_row(db, **base, execution="none", state=MEMORY_SKIPPED,
                              decided_at=now, result={"lesson": mem})
        return {"experiment": eid, "state": MEMORY_SKIPPED, "lesson": mem}
    if paid:
        est, basis = _estimate_cost(canon)
        cand = P.new_candidate(db, product_class, inc, canon,
                               f"paid challenger (planned): {canon}")
        from .. import spend_plan
        plan = paid_plan(product_class, canon, base["hypothesis"])
        eid = _experiment_row(db, **base, challenger_id=cand["id"], execution=P.PAID,
                              state=GATED_SPEND, estimated_cost_cad=est,
                              result={"paid_stages": paid, "cost_basis": basis,
                                      "paid_plan": plan,
                                      "plan_problems": spend_plan.problems(plan),
                                      "gate": paid_execution_gate()})
        return {"experiment": eid, "state": GATED_SPEND, "estimated_cost_cad": est,
                "cost_basis": basis, "candidate": cand, "paid_plan": plan,
                "plan_problems": spend_plan.problems(plan)}
    if not cirs:
        return {"experiment": None, "state": "NO_PRODUCTS",
                "why": f"no certified product in {product_class} to test on"}
    cand = P.new_candidate(db, product_class, inc, canon, hypothesis or f"challenger {canon}")
    eid = _experiment_row(db, **base, challenger_id=cand["id"], execution=P.DETERMINISTIC,
                          state="RUNNING")
    a = run_arm(db, product_class, inc, cirs, experiment_id=eid, arm="incumbent")
    b = run_arm(db, product_class, cand, cirs, experiment_id=eid, arm="challenger")
    verdict = compare(a, b, census=True)
    slim = {k: v for k, v in verdict.items()}
    if verdict["promote"]:
        P.promote(db, cand["id"], promoted_on={
            "experiment": eid, "incumbent": verdict["incumbent"],
            "challenger": verdict["challenger"], "catalogue_fp": fp,
            "replaced_id": inc["id"]})
        _set_experiment(db, eid, state=PROMOTED, result=slim, decided_at=now)
        _lesson(db, product_class, "promoted", {"changes": canon, "catalogue": fp},
                f"{canon} promoted over {inc['label']}: quality {verdict['quality_gain']:+.4f} "
                f"(margin {verdict['required_margin']}), yield "
                f"{verdict['incumbent']['yield']} -> {verdict['challenger']['yield']}",
                f"experiment:{eid}")
        state = PROMOTED
    else:
        P.set_state(db, cand["id"], P.REJECTED)
        _set_experiment(db, eid, state=REJECTED, result=slim, decided_at=now)
        _lesson(db, product_class, REJECTED.lower(), {"changes": canon, "catalogue": fp},
                f"{canon} rejected against {inc['label']}: " + "; ".join(verdict["blockers"]),
                f"experiment:{eid}")
        state = REJECTED
    return {"experiment": eid, "state": state, "verdict": verdict, "candidate": cand["id"]}


# ---------------------------------------------------------------------------- generation

def generate(db, product_class: str, *, cirs=None) -> dict:
    """AFFECT FUTURE GENERATION: production images are made with the incumbent version."""
    inc = P.ensure_incumbent(db, product_class)
    if cirs is None:
        cirs = catalogue().get(product_class, [])
    if not cirs:
        return {"pipeline": inc, "galleries": [], "why": "no certified product in class"}
    res = run_arm(db, product_class, inc, cirs, arm="production")
    return {"pipeline": inc, **res}


# ---------------------------------------------------------------------------- monitor

def _experiment_for(db, challenger_id: int):
    from sqlalchemy import select

    with M.session(db) as s:
        r = s.scalar(select(M.VisualExperiment).where(
            M.VisualExperiment.challenger_id == challenger_id).order_by(
                M.VisualExperiment.id.desc()))
        return r.id if r is not None else None


def _watermark(db, eid: int, through) -> None:
    with M.session(db) as s:
        r = s.get(M.VisualExperiment, eid)
        r.result = {**dict(r.result or {}), "monitored_through": through}


def monitor(db, product_class: str, *, now: datetime | None = None) -> dict:
    """MONITOR -> ROLLBACK IF WORSE: production since promotion vs what it replaced."""
    now = now or _now()
    inc = P.ensure_incumbent(db, product_class)
    po = inc.get("promoted_on") or {}
    if not po or inc["parent_id"] is None:
        return {"product_class": product_class, "action": "none",
                "why": "the incumbent is a first version or was not promoted by a test"}
    after = datetime.fromisoformat(inc["promoted_at"]) if inc["promoted_at"] else None
    rd = _readings(_production(db, inc["id"], after=after))
    if rd["frames"] == 0 and rd["galleries"] == 0:
        return {"product_class": product_class, "action": "waiting",
                "why": "no production judgement since promotion"}
    replaced = po.get("incumbent") or {}
    worse = []
    if rd["yield"] is not None and replaced.get("yield") is not None and \
            rd["yield"] < replaced["yield"] - REGRESSION_TOLERANCE:
        worse.append(f"accepted-image yield {rd['yield']} < replaced {replaced['yield']} - "
                     f"{REGRESSION_TOLERANCE}")
    if rd["quality"] is not None and replaced.get("quality") is not None and \
            rd["quality"] < replaced["quality"] - REGRESSION_TOLERANCE:
        worse.append(f"task score {rd['quality']} < replaced {replaced['quality']} - "
                     f"{REGRESSION_TOLERANCE}")
    eid = _experiment_for(db, inc["id"])
    rows = _production(db, inc["id"], after=after)
    through = max(r["id"] for r in rows) if rows else None
    if eid:
        _watermark(db, eid, through)
    if not worse:
        return {"product_class": product_class, "action": "retain", "readings": rd,
                "monitored_through": through}
    why = "production regressed after promotion: " + "; ".join(worse)
    rb = P.rollback(db, product_class, why=why)
    if eid:
        _set_experiment(db, eid, state=ROLLED_BACK, decided_at=now)
    changes = {k: v for k, v in inc["params"].items()
               if (rb.get("to") or {}).get("params", {}).get(k) != v}
    _lesson(db, product_class, "rolled_back", {"changes": changes,
                                               "catalogue": po.get("catalogue_fp", "")},
            f"{inc['label']} rolled back to {(rb.get('to') or {}).get('label')}: {why}",
            f"experiment:{eid}")
    return {"product_class": product_class, "action": "rolled_back", "readings": rd,
            "rollback": rb, "why": why}


# ---------------------------------------------------------------------------- slow loop

def record_market(db, *, pipeline_id: int, source_ref: str, subject: str = "",
                  impressions: int | None = None, clicks: int | None = None,
                  favourites: int | None = None, carts: int | None = None,
                  purchases: int | None = None, refunds: int | None = None,
                  support_flags: int | None = None) -> int:
    """A marketplace reading for listings imaged by `pipeline_id`. Provenance required."""
    if not (source_ref or "").strip():
        raise ValueError("a marketplace reading names its source (export id, stats page)")
    counts = dict(impressions=impressions, clicks=clicks, favourites=favourites, carts=carts,
                  purchases=purchases, refunds=refunds, support_flags=support_flags)
    for k, v in counts.items():
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise ValueError(f"{k} must be a non-negative whole count or absent")
    if impressions is not None and clicks is not None and clicks > impressions:
        raise ValueError("more clicks than impressions")
    version = P.get(db, pipeline_id)
    if version is None:
        raise ValueError(f"no pipeline version {pipeline_id}")
    with M.session(db) as s:
        r = M.VisualMarketEvidence(pipeline_id=pipeline_id,
                                   product_class=version["product_class"], subject=subject,
                                   source_ref=source_ref.strip(), **counts)
        s.add(r)
        s.flush()
        return r.id


def market_totals(db, pipeline_id: int) -> dict:
    from sqlalchemy import select

    keys = ("impressions", "clicks", "favourites", "carts", "purchases", "refunds",
            "support_flags")
    with M.session(db) as s:
        rows = list(s.scalars(select(M.VisualMarketEvidence).where(
            M.VisualMarketEvidence.pipeline_id == pipeline_id)))
    out = {k: (sum(getattr(r, k) for r in rows if getattr(r, k) is not None)
               if any(getattr(r, k) is not None for r in rows) else None) for k in keys}
    out["readings"] = len(rows)
    out["ctr"] = (out["clicks"] / out["impressions"]
                  if out["impressions"] and out["clicks"] is not None else None)
    out["conversion"] = (out["purchases"] / out["clicks"]
                         if out["clicks"] and out["purchases"] is not None else None)
    out["refund_rate"] = (out["refunds"] / out["purchases"]
                          if out["purchases"] and out["refunds"] is not None else None)
    return out


def _z(x1, n1, x2, n2) -> float | None:
    if not n1 or not n2:
        return None
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0.0
    return None if se == 0 else ((x1 / n1) - (x2 / n2)) / se


def calibrate(db, product_class: str, *, now: datetime | None = None) -> dict:
    """SLOW LOOP: does marketplace evidence confirm or overturn the internal promotion?

    Sequential before/after per version (Etsy offers no image A/B test), so a difference must
    clear both a volume floor and a two-proportion z of `MARKET_Z`. Overturn = rollback to the
    replaced version + a lesson that strikes the parameter from the internal search.
    """
    now = now or _now()
    inc = P.ensure_incumbent(db, product_class)
    if inc["parent_id"] is None:
        return {"product_class": product_class, "verdict": "no_comparison",
                "why": "first version: nothing to compare against"}
    parent = P.get(db, inc["parent_id"])
    a, b = market_totals(db, parent["id"]), market_totals(db, inc["id"])
    checks, worse, better = [], [], []
    if (a["impressions"] or 0) >= MARKET_MIN_IMPRESSIONS and \
            (b["impressions"] or 0) >= MARKET_MIN_IMPRESSIONS and \
            a["clicks"] is not None and b["clicks"] is not None:
        z = _z(b["clicks"], b["impressions"], a["clicks"], a["impressions"])
        checks.append({"metric": "ctr", "replaced": a["ctr"], "incumbent": b["ctr"], "z": z})
        if z is not None and z <= -MARKET_Z:
            worse.append(f"hero CTR {b['ctr']:.4f} vs {a['ctr']:.4f} (z={z:.2f})")
        elif z is not None and z >= MARKET_Z:
            better.append("ctr")
    if (a["clicks"] or 0) >= MARKET_MIN_CLICKS and (b["clicks"] or 0) >= MARKET_MIN_CLICKS \
            and a["purchases"] is not None and b["purchases"] is not None:
        z = _z(b["purchases"], b["clicks"], a["purchases"], a["clicks"])
        checks.append({"metric": "conversion", "replaced": a["conversion"],
                       "incumbent": b["conversion"], "z": z})
        if z is not None and z <= -MARKET_Z:
            worse.append(f"listing conversion {b['conversion']:.4f} vs {a['conversion']:.4f}")
    if (a["purchases"] or 0) >= MARKET_MIN_PURCHASES and \
            (b["purchases"] or 0) >= MARKET_MIN_PURCHASES and \
            a["refunds"] is not None and b["refunds"] is not None:
        z = _z(b["refunds"], b["purchases"], a["refunds"], a["purchases"])
        checks.append({"metric": "refund_rate", "replaced": a["refund_rate"],
                       "incumbent": b["refund_rate"], "z": z})
        if z is not None and z >= MARKET_Z:
            worse.append(f"refund rate {b['refund_rate']:.4f} vs {a['refund_rate']:.4f}")
    if not checks:
        return {"product_class": product_class, "verdict": "insufficient_evidence",
                "replaced": a, "incumbent": b,
                "why": f"needs >= {MARKET_MIN_IMPRESSIONS} impressions on both versions"}
    if not worse:
        return {"product_class": product_class,
                "verdict": "confirmed" if better else "inconclusive", "checks": checks}
    changes = {k: v for k, v in inc["params"].items() if parent["params"].get(k) != v}
    why = ("marketplace evidence overturned the internal promotion: " + "; ".join(worse) +
           ". Basis: sequential before/after per version, not a randomised test")
    rb = P.rollback(db, product_class, why=why, to_id=parent["id"])
    eid = _experiment_for(db, inc["id"])
    if eid:
        _set_experiment(db, eid, state=OVERTURNED, decided_at=now)
    _lesson(db, product_class, "overturned", {"changes": changes, "checks": checks},
            f"{inc['label']} overturned by the marketplace and rolled back to "
            f"{parent['label']}: {'; '.join(worse)}. The internal judge "
            f"({G.JUDGE_VERSION}) is not trusted on {sorted(changes)} for {product_class} "
            f"for {OVERTURN_MEMORY_DAYS} days", f"experiment:{eid}")
    return {"product_class": product_class, "verdict": "overturned", "checks": checks,
            "rollback": rb, "why": why}


# ---------------------------------------------------------------------------- paid planning

def _open_paid(db, product_class: str) -> int | None:
    from sqlalchemy import select

    with M.session(db) as s:
        r = s.scalar(select(M.VisualExperiment).where(
            M.VisualExperiment.product_class == product_class,
            M.VisualExperiment.state == GATED_SPEND))
        return r.id if r is not None else None


def plan_paid(db, product_class: str, diagnosis: dict | None = None) -> dict:
    """Queue one paid challenger per class (idempotent). Never executed here."""
    existing = _open_paid(db, product_class)
    if existing:
        return {"experiment": existing, "state": GATED_SPEND, "new": False}
    diagnosis = diagnosis or diagnose(db, product_class)
    change = propose(db, product_class, diagnosis, execution=P.PAID)
    if change is None:
        return {"experiment": None, "state": "NO_CANDIDATE"}
    out = experiment(db, product_class, change, diagnosis=diagnosis,
                     hypothesis=(f"generated-path challenger {change} for {product_class}: "
                                 f"{'; '.join(diagnosis['findings']) or 'explore'}"))
    return {**out, "new": True}


def execute_paid(db, experiment_id: int) -> dict:
    """The paid executor's door. Closed: returns the refusal, makes no call.

    A paid experiment without a complete F-877 plan (hypothesis, provider/model, call count,
    max spend, pass/fail criteria) is refused before the gate is even consulted, so opening
    the gate later can never run an unbounded experiment."""
    from .. import spend_plan

    plan = None
    with M.session(db) as s:
        row = s.get(M.VisualExperiment, experiment_id)
        if row is not None:
            plan = (row.result or {}).get("paid_plan")
    found = spend_plan.problems(plan)
    if found:
        return {"experiment": experiment_id, "executed": False, "allowed": False,
                "why": "incomplete paid plan (F-877): " + "; ".join(found),
                "plan_problems": found}
    gate = paid_execution_gate()
    return {"experiment": experiment_id, "executed": False, **gate, "paid_plan": plan}


# ---------------------------------------------------------------------------- the cycle

def cycle(db, *, builds=None, classes=None, now: datetime | None = None,
          experiments_per_class: int = 1, hero: bool = True) -> dict:
    """One REPEAT of the loop for every class. Deterministic work runs; paid work is queued."""
    M.ensure_tables(db)
    now = now or _now()
    cat = catalogue(builds)
    report = {"at": now.isoformat(), "classes": {}}
    for cls in (classes or list(P.PRODUCT_CLASSES)):
        entry: dict = {}
        cirs = cat.get(cls, [])
        inc = P.ensure_incumbent(db, cls)
        if cirs:
            fp = catalogue_fp(cirs)
            seen = [r for r in _production(db, inc["id"])
                    if r["subject"].endswith(":gallery") and r["metrics"].get("catalogue_fp") == fp]
            if not seen:
                entry["generated"] = {k: v for k, v in generate(db, cls, cirs=cirs).items()
                                      if k in ("quality", "yield", "frames", "failures")}
            entry["monitor"] = monitor(db, cls, now=now)
        entry["calibration"] = calibrate(db, cls, now=now)
        diag = diagnose(db, cls)
        entry["diagnosis"] = {k: diag[k] for k in ("findings", "readings")}
        runs = []
        if cirs:
            for _ in range(experiments_per_class):
                change = propose(db, cls, diag, catalogue=catalogue_fp(cirs))
                if change is None:
                    break
                res = experiment(db, cls, change, diagnosis=diag, cirs=cirs, now=now)
                runs.append({k: res.get(k) for k in ("experiment", "state")} |
                            {"changes": change})
                diag = diagnose(db, cls)
        entry["experiments"] = runs
        entry["paid"] = {k: v for k, v in plan_paid(db, cls, diag).items()
                         if k in ("experiment", "state", "new", "estimated_cost_cad")}
        entry["incumbent"] = P.ensure_incumbent(db, cls)["label"]
        if hero:
            # Commercial merchandising R&D (D-FB-16): slow loop first (it can overturn), then
            # free hero challengers on the (possibly new) incumbent pipeline.
            from . import hero as H
            entry["hero_calibration"] = H.calibrate(db, cls, now=now)
            ch = H.challenge(db, cls, cirs=cirs, now=now)
            entry["hero"] = {k: ch[k] for k in ("evaluated", "queued", "unavailable",
                                                "refused")} | {
                "promoted": bool((ch["promotion"] or {}).get("promoted"))}
        report["classes"][cls] = entry
    return report
