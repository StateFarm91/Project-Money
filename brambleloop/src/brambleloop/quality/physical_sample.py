"""P0-PHYSICAL-TEST-REQUEST: one tester work item per class-C release with no bound full make.

`gate.certify` refuses a release whose effective risk class is C until a passed full physical
make of exactly that content is bound (`PHYSICAL_TEST_REQUIRED`). Before this module nothing
said *what* to make for a product that never had a sample: the one prepared kit
(`quality.tester_kit`) is fixed to `BUILD_KEY = "basket_small"`.

**This is tester work, not an owner card (DECISION_LOG B-532; review PHYSICAL e8b458b5
MED-3).** The owner has withdrawn the physical sample from the owner queue; the route is an
independent pattern tester (`tester_roster`), and the one owner card for that route is the
existing `tester_outreach` decision. So this module writes no OwnerAction. It records a work
item, `physical.sample_requested`, that `quality.testers.plan` attaches to the release's
testing demand, so whoever tests the product is handed the exact kit.

* **Bound to the content hash** (review MED-1). One open item per slug@version@content: a
  re-certify of the same content writes nothing new; changed content under the same version
  opens a new item.
* **The kit comes from the CIR and its twin** (MED-2): yarn, hook, gauge (UNKNOWN when the
  pattern states none), the pieces, the predicted size, and the predicted metres of every
  yarn colour, keyed as the physical validator keys them (the twin's `yarn_metres_by_color`),
  with the +-20% calibration tolerance stated.
* **Satisfied only by evidence that would clear the gate** (HIGH-1): a stored
  `physical.record` that is a passed, non-owner-made full physical make bound to the same
  content hash. Any other record (swatch, component, owner-made, failed, a colour
  unmeasured, other content) leaves the item open and says why.
* **Says only what is true** (HIGH-2): a record that leaves a sampled colour unmeasured is
  stored as not passed (`SAMPLE_COLOUR_UNMEASURED` is an assessment finding, not a refusal),
  so it does not satisfy the item.

What this never does: create, infer or assume physical evidence; spend; contact a tester;
raise an owner card.
"""
from __future__ import annotations

import hashlib
import json

REQUESTED = "physical.sample_requested"
CLOSED = "physical.sample_closed"
TOLERANCE = 0.20                 # the uncalibrated yardage estimate (B-532: +-20%)


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def kit_hash(kit: dict) -> str:
    return hashlib.sha256(_canonical(kit).encode()).hexdigest()


def needs_request(cert) -> bool:
    """Class C, refused only for want of a bound full make, and not a stale-evidence retest
    (that request is `_request_physical_retest`'s, keyed on the new content)."""
    if not getattr(cert, "physical_test_required", False):
        return False
    if getattr(cert, "physical_test_passed", False):
        return False
    status = ((cert.risk_matrix or {}).get("requirement") or {})
    if status.get("retest_required"):
        return False
    return bool(cert.content_hash)


def _metres_by_colour(cir, cert) -> dict:
    """The twin's predicted metres per colour id: the keys the physical validator reads."""
    twin = cert.twin_summary or {}
    got = twin.get("yarn_metres_by_color") or {}
    if not got:
        try:
            from ..cir.compiler import compile_cir
            from ..cir.twin import build_twin

            got = dict(build_twin(cir, compile_cir(cir)).yarn_metres_by_color or {})
        except Exception:  # noqa: BLE001 - no twin: the colours stay UNKNOWN by name
            got = {}
    return {str(k): round(float(v), 1) for k, v in sorted(got.items()) if v is not None}


def sample_kit(cir, cert) -> dict:
    """The exact sample a tester makes, from the CIR (never the fixed basket kit)."""
    g = cir.gauge
    twin = cert.twin_summary or {}
    size = {k: twin[k] for k in ("width_cm", "height_cm", "across_flats_cm", "shape")
            if twin.get(k) is not None}
    gauge = "UNKNOWN (the pattern states no gauge)"
    if g is not None and (g.stitches_per_10cm or g.rows_per_10cm):
        gauge = {"stitches_per_10cm": g.stitches_per_10cm, "rows_per_10cm": g.rows_per_10cm,
                 "stitch": g.stitch_type}
    metres = _metres_by_colour(cir, cert)
    return {
        "slug": cir.slug, "version": cir.version, "title": cir.title,
        "content_hash": cert.content_hash,
        "risk_class": (cert.risk_matrix or {}).get("effective", "C"),
        "scope": "full_make",
        "yarn": [{"name": m.name, "yarn_weight": m.yarn_weight,
                  "metres_estimate": m.metres_estimate, "color_id": m.color_id}
                 for m in cir.materials],
        "yarn_weight": getattr(g, "yarn_weight", None),
        "hook_mm": getattr(g, "hook_mm", None),
        "gauge": gauge,
        "finished_size_note": cir.finished_size_note,
        "predicted_size": size,
        "colours_to_weigh": sorted(metres),
        "yarn_metres_predicted": metres,
        "yarn_tolerance": TOLERANCE,
        "pieces": [c.name for c in cir.components],
    }


def brief(kit: dict) -> str:
    """What the tester is told to make and to record, from the kit alone."""
    yarn = ", ".join(m["name"] for m in kit["yarn"]) or "the pattern's stated yarn"
    hook = f"{kit['hook_mm']} mm" if kit["hook_mm"] else "hook UNKNOWN (pattern states none)"
    colours = "; ".join(f"{c}: about {m} m (+-{int(kit['yarn_tolerance'] * 100)}%)"
                        for c, m in kit["yarn_metres_predicted"].items()) or (
        "UNKNOWN (no per-colour prediction)")
    return (f"Make the whole {kit['title']} ({kit['slug']}@{kit['version']}), as written: "
            f"{yarn}; {hook}; gauge {kit['gauge']}; pieces {kit['pieces']}. Record the "
            f"finished measurements and the grams used of every colour ({colours}). A record "
            f"that leaves a colour unweighed is stored as not passed "
            f"(SAMPLE_COLOUR_UNMEASURED) and does not satisfy this request.")


def _rows(db, artifact: str | None = None) -> list[tuple]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    q = select(AuditLog).where(AuditLog.action.in_((REQUESTED, CLOSED)))
    if artifact is not None:
        q = q.where(AuditLog.artifact == artifact)
    with db.session() as s:
        return [(r.action, r.artifact, dict(r.detail or {}))
                for r in s.scalars(q.order_by(AuditLog.id))]


def state(db, slug: str, version: str, content_hash: str | None) -> dict:
    """The work item for this exact content: none, open, or satisfied (by which record)."""
    rows = _rows(db, f"{slug}@{version}")
    asked = [d for a, _x, d in rows if a == REQUESTED and d.get("content_hash") == content_hash]
    done = [d for a, _x, d in rows if a == CLOSED and d.get("satisfied")
            and d.get("content_hash") == content_hash]
    if done:
        return {"state": "satisfied", "physical_test": done[-1].get("physical_test")}
    if asked:
        return {"state": "open", "kit_hash": asked[-1].get("kit_hash")}
    return {"state": "none"}


def request(ctx, cir, cert) -> dict | None:
    """Open the tester work item for this release's content, once. Returns what was done."""
    if not needs_request(cert):
        return None
    now = state(ctx.db, cir.slug, cir.version, cert.content_hash)
    if now["state"] != "none":
        return {"state": "already_" + now["state"], "content_hash": cert.content_hash,
                "kit_hash": now.get("kit_hash")}
    kit = sample_kit(cir, cert)
    digest = kit_hash(kit)
    ctx.audit(REQUESTED, artifact=f"{cir.slug}@{cir.version}",
              detail={"route": "tester_roster", "owner_card": None, "kit": kit,
                      "kit_hash": digest, "content_hash": cert.content_hash,
                      "brief": brief(kit)})
    return {"state": "requested", "content_hash": cert.content_hash, "kit_hash": digest}


def open_requests(db) -> dict:
    """slug -> its newest open work item (kit hash, content hash, brief), for testing demand."""
    rows = _rows(db)
    satisfied = {(art, d.get("content_hash")) for a, art, d in rows
                 if a == CLOSED and d.get("satisfied")}
    latest: dict = {}
    for a, art, d in rows:
        if a == REQUESTED and (art, d.get("content_hash")) not in satisfied:
            latest[art.split("@", 1)[0]] = {"artifact": art, "kit_hash": d.get("kit_hash"),
                                            "content_hash": d.get("content_hash"),
                                            "brief": d.get("brief")}
    return latest


def close_on_record(ctx, slug: str, version: str, content_hash: str | None,
                    row_id: int | None, *, passed: bool, evidence_class: str | None,
                    owner_made: bool) -> dict | None:
    """A stored `physical.record` satisfies the open work item only when it is the evidence
    the gate accepts: a passed, non-owner-made full physical make of the same content."""
    from ..gates.risk_matrix import FULL_PHYSICAL_MAKE

    if state(ctx.db, slug, version, content_hash)["state"] != "open":
        return None
    why = []
    if not passed:
        why.append("the make did not pass (a failed check, a deviation or a colour "
                   "unmeasured)")
    if evidence_class != FULL_PHYSICAL_MAKE:
        why.append(f"it is {evidence_class or 'unclassified'}, not a full physical make")
    if owner_made:
        why.append("it is owner-made; the route is an independent tester (B-532)")
    outcome = {"satisfied": not why, "content_hash": content_hash, "physical_test": row_id,
               "why": "; ".join(why) or "a passed full make of this content is bound"}
    ctx.audit(CLOSED, artifact=f"{slug}@{version}", detail=outcome)
    return outcome
