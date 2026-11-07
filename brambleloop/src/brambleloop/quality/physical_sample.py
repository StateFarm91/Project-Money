"""P0-PHYSICAL-TEST-REQUEST: one owner action per class-C release that has no bound full make.

`gate.certify` refuses a release whose effective risk class is C until a passed full physical
make of exactly that content is bound (`PHYSICAL_TEST_REQUIRED`). Before this module the only
owner request was `_request_physical_retest`, which fires when *earlier* evidence went stale.
A product that never had a sample raised nothing, and the one prepared kit
(`quality.tester_kit`) is fixed to `BUILD_KEY = "basket_small"`. So every new class-C design
waited silently.

This raises the request for that product:

* **Keyed** `physical.sample:<slug>@<version>`. One request per release, however many times
  certification re-runs. The key states the version, not the content: a material change
  under the same version is refused by PT-03, never re-requested here.
* **A sample kit built from the CIR itself.** Yarn, hook, gauge and the size the twin
  predicts come from the pattern, never from the basket kit. `kit_hash` is the SHA-256 of
  the canonical kit and binds to the certificate's `content_hash`, so the tester makes
  exactly what was examined (F-078).
* **The cost, minutes and consequence** come from `risk_matrix.owner_action_spec`. That is
  the one costing rule the retest path uses, so the two requests never disagree.
* **Closed only by evidence.** A `physical.record` intake for this slug@version, bound to the
  same content hash, closes the action as `satisfied`. A decision the owner has already made
  (any closed row for the key) is never reopened.

What this never does: create, infer or assume physical evidence; spend; contact a tester.
The action asks the owner to approve commissioning an independent tester (F-071).
"""
from __future__ import annotations

import hashlib
import json

KEY_PREFIX = "physical.sample:"
REQUESTED = "physical.sample_requested"
CLOSED = "physical.sample_closed"


def requirement_key(slug: str, version: str) -> str:
    return f"{KEY_PREFIX}{slug}@{version}"


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


def sample_kit(cir, cert) -> dict:
    """The exact sample a tester makes, from the CIR (never the fixed basket kit)."""
    g = cir.gauge
    twin = cert.twin_summary or {}
    size = {k: twin[k] for k in ("width_cm", "height_cm", "across_flats_cm", "shape")
            if twin.get(k) is not None}
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
        "gauge": None if g is None else {"stitches_per_10cm": g.stitches_per_10cm,
                                         "rows_per_10cm": g.rows_per_10cm,
                                         "stitch": g.stitch_type},
        "finished_size_note": cir.finished_size_note,
        "predicted_size": size,
        "yarn_metres_predicted": twin.get("yarn_metres") or {},
        "pieces": [c.name for c in cir.components],
    }


def request(ctx, cir, cert) -> dict | None:
    """Raise (or restate) the per-product sample request. Returns what was done, or None."""
    if not needs_request(cert):
        return None
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..gates import risk_matrix
    from ..ops import owner_queue

    status = ((cert.risk_matrix or {}).get("requirement") or {})
    required = status.get("required") or risk_matrix.FULL_PHYSICAL_MAKE
    twin = cert.twin_summary or {}
    try:
        from ..cir.compiler import compile_cir
        from ..seasonal.leadtime import estimate_for

        hours = estimate_for(cir, compile_cir(cir)).hours
    except Exception:  # noqa: BLE001 - no estimate: the spec's stated fallback hours apply
        hours = None
    spec = risk_matrix.owner_action_spec(
        slug=cir.slug, version=cir.version, content_hash=cert.content_hash,
        required=required, effective_class=(cert.risk_matrix or {}).get("effective", "C"),
        make_hours=hours, yarn_metres=sum((twin.get("yarn_metres") or {}).values()) or None)
    kit = sample_kit(cir, cert)
    digest = kit_hash(kit)
    key = requirement_key(cir.slug, cir.version)
    yarn = ", ".join(m["name"] for m in kit["yarn"]) or "the pattern's stated yarn"
    hook = f"{kit['hook_mm']} mm" if kit["hook_mm"] else "hook UNKNOWN (pattern states none)"
    action = (f"{spec['action']} Sample spec (kit {digest[:12]}): {yarn}; {hook}; "
              f"gauge {kit['gauge']}; pieces {kit['pieces']}.")
    with ctx.db.session() as s:
        prior = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)
                         .order_by(OwnerAction.id.desc()))
        if prior is not None and prior.done:
            state = "already_decided"
            row_id = prior.id
        else:
            row = owner_queue.ensure(
                s, key, action=action, reason=spec["reason"],
                max_cost_cad=spec["max_cost_cad"], minutes=spec["minutes"],
                consequence_of_delay=(f"{spec['consequence_of_delay']} The release stays "
                                      f"withheld until a passed full make is recorded."),
                blocks=spec["blocks"])
            state = "restated" if prior is not None else "queued"
            row_id = row.id
    ctx.audit(REQUESTED, artifact=f"{cir.slug}@{cir.version}",
              detail={"owner_action": state, "owner_action_id": row_id,
                      "requirement_key": key, "kit": kit, "kit_hash": digest,
                      "content_hash": cert.content_hash, "required": required,
                      "max_cost_cad": spec["max_cost_cad"], "cost_basis": spec["cost_basis"]})
    return {"state": state, "requirement_key": key, "kit_hash": digest,
            "owner_action_id": row_id}


def close_on_record(ctx, slug: str, version: str, content_hash: str | None,
                    row_id: int | None) -> dict | None:
    """A `physical.record` intake for this release closes its open sample request.

    Only a record bound to the content the request named closes it (`kit.content_hash`), and
    only an open row. Whether the sample *passed* is the certificate's question, asked by the
    next `gate.certify`; a recorded make answers this request either way."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction
    from ..ops import owner_queue

    key = requirement_key(slug, version)
    with ctx.db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == key, OwnerAction.done == False)  # noqa: E712
            .order_by(OwnerAction.id))
        if row is None:
            return None
        asked = s.scalar(select(AuditLog).where(
            AuditLog.action == REQUESTED, AuditLog.artifact == f"{slug}@{version}")
            .order_by(AuditLog.id.desc()))
        wanted = ((asked.detail or {}).get("content_hash") if asked is not None else None)
        if not content_hash or wanted != content_hash:
            outcome = {"closed": False, "why": "record bound to other content",
                       "requirement_key": key, "wanted": wanted, "got": content_hash}
        else:
            owner_queue.close(row, owner_queue.SATISFIED,
                              f"physical.record row {row_id} bound to {content_hash[:12]}")
            outcome = {"closed": True, "requirement_key": key, "physical_test": row_id}
    ctx.audit(CLOSED, artifact=f"{slug}@{version}", detail=outcome)
    return outcome
