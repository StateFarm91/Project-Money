"""Pre-sale internal outcomes: what the company can measure about itself before any customer.

W4-LEARN. The capability cells that need a sale (pricing, customer experience, portfolio,
finance, growth) stay data-gated until there is one, and that is right. But a large part of
whether the company is getting better happens before a sale and is already in the database:
how often a pattern passes the certificate chain first time, how often Product Truth refuses
listing copy, how many rendered assets the visual gate blocks, how often the search
certificate passes, how often the release gates would let a product out, how long the chain
takes from compile to a publish request, and what a release-ready product actually cost.

Each reading here is a deterministic query over rows the runtime already writes. Rules:

* **Internal, never customer.** Every reading carries `kind: "internal pre-sale outcome"` and
  `customer_outcome: False`. None of these is a proxy for demand and none is labelled one.
* **UNKNOWN is never 0.** An empty source gives `value: None, reading: "UNMEASURED"` with the
  table that has to fill; a measured zero is only written over a non-empty sample.
* **Estimated is not actual.** Cost reads `CostEntry` rows only (actual spend); with none, the
  cost reading is UNMEASURED, not CA$0.
* **Movement is computed, not asserted.** `record` appends one audit row (`improve.presale`)
  when the readings change, and `movement` compares the newest two recordings per metric, in
  the metric's own direction.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

ACTION = "improve.presale"
KIND = "internal pre-sale outcome"

# metric -> (higher_is_better, what it reads)
METRICS: dict[str, tuple[bool, str]] = {
    "gate_first_pass_rate": (True, "first gate.certified/gate.blocked audit per slug@version"),
    "product_truth_refusal_rate": (False, "gate.listing_copy_refused audits per certified-or-"
                                          "blocked slug@version"),
    "creative_survival_rate": (True, "creative.tournament audits: survivors / generated"),
    "catalogue_creative_survival_rate": (True, "creative.audit.audit_catalogue: legacy builder "
                                               "catalogue concepts the deterministic jury "
                                               "passes (cohort-labelled, F-188)"),
    "render_qa_block_rate": (False, "decided ListingAsset rows blocked by the visual gate"),
    "seo_certificate_pass_rate": (True, "ListingSearchProfile verdict PASS, newest per slug"),
    "release_gate_pass_rate": (True, "newest store.release_gates audit per slug not blocking"),
    "time_to_publish_request_hours": (False, "first compile/certify job for a slug to its "
                                             "first store.publish job (median)"),
    "cost_per_release_ready_cad": (False, "actual CostEntry amount_cad per release-ready slug"),
}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _measured(metric: str, value: float, sample: int, **detail) -> dict:
    higher, reads = METRICS[metric]
    return {"metric": metric, "value": round(float(value), 4), "sample": int(sample),
            "reading": "MEASURED", "kind": KIND, "customer_outcome": False,
            "higher_is_better": higher, "reads": reads, "detail": detail}


def _unmeasured(metric: str, why: str) -> dict:
    higher, reads = METRICS[metric]
    return {"metric": metric, "value": None, "sample": 0, "reading": "UNMEASURED",
            "kind": KIND, "customer_outcome": False, "higher_is_better": higher,
            "reads": reads, "why": why}


def _slug(artifact: str) -> str:
    return (artifact or "").split("@", 1)[0]


def _audits(s, actions) -> list:
    from sqlalchemy import select

    from ..core.models import AuditLog

    return list(s.scalars(select(AuditLog).where(AuditLog.action.in_(tuple(actions)))
                          .order_by(AuditLog.id)))


def gate_first_pass(s) -> dict:
    first: dict[str, bool] = {}
    for a in _audits(s, ("gate.certified", "gate.blocked")):
        first.setdefault(a.artifact or "", a.action == "gate.certified")
    first.pop("", None)
    if not first:
        return _unmeasured("gate_first_pass_rate", "no gate.certified/gate.blocked audit yet")
    passed = sum(first.values())
    return _measured("gate_first_pass_rate", passed / len(first), len(first),
                     passed=passed, artifacts=len(first))


def product_truth(s) -> dict:
    attempts = {a.artifact for a in _audits(s, ("gate.certified", "gate.blocked"))
                if a.artifact}
    if not attempts:
        return _unmeasured("product_truth_refusal_rate",
                           "no certification attempt yet, so no listing copy was examined")
    refused = {a.artifact for a in _audits(s, ("gate.listing_copy_refused",)) if a.artifact}
    hit = refused & attempts
    return _measured("product_truth_refusal_rate", len(hit) / len(attempts), len(attempts),
                     refused=sorted(hit)[:20])


def creative_survival(s) -> dict:
    generated = survived = runs = 0
    for a in _audits(s, ("creative.tournament",)):
        d = a.detail or {}
        g = int(((d.get("field") or {}).get("generated")) or 0)
        if g <= 0:
            continue
        runs += 1
        generated += g
        survived += len(d.get("survivors") or []) if isinstance(d.get("survivors"), list) else 0
    if not generated:
        return _unmeasured("creative_survival_rate",
                           "no creative.tournament audit has generated a field yet")
    return _measured("creative_survival_rate", survived / generated, generated,
                     survivors=survived, runs=runs)


def catalogue_creative_survival(s) -> dict:
    """The legacy catalogue cohort, judged by the same deterministic jury the dashboard reads.

    A separate metric from the tournament rate, so the two cohorts never share a series
    (F-188): the first tournament must not read as a jump in the catalogue's survival.
    """
    from ..creative.audit import audit_catalogue

    report = audit_catalogue()
    audited = int(report.get("products_audited") or 0)
    if audited <= 0:
        return _unmeasured("catalogue_creative_survival_rate",
                           "the legacy catalogue has no concept to judge")
    survivors = [str(x) for x in report.get("survivors") or []]
    cohort = report.get("cohort") or {}
    return _measured("catalogue_creative_survival_rate", len(survivors) / audited, audited,
                     survivors=len(survivors), cohort=cohort.get("name"),
                     generator_version=cohort.get("generator_version"),
                     dominant_failure=(report.get("autopsy") or {}).get("dominant_cause"))


def render_qa(s) -> dict:
    from sqlalchemy import select

    from ..core.models import ListingAsset

    decided = [a for a in s.scalars(select(ListingAsset)) if a.approved or a.blocked_reasons]
    if not decided:
        return _unmeasured("render_qa_block_rate", "no ListingAsset decided by the gate yet")
    blocked = [a for a in decided if a.blocked_reasons]
    groups: dict[str, int] = {}
    for a in blocked:
        key = f"{a.asset_class}/{a.role}"
        groups[key] = groups.get(key, 0) + 1
    return _measured("render_qa_block_rate", len(blocked) / len(decided), len(decided),
                     blocked=len(blocked), blocked_by_group=groups)


def seo_certificate(s) -> dict:
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    newest: dict[str, object] = {}
    for p in s.scalars(select(ListingSearchProfile).order_by(ListingSearchProfile.id)):
        newest[p.product_slug] = p
    if not newest:
        return _unmeasured("seo_certificate_pass_rate", "no ListingSearchProfile yet "
                                                        "(listing.seo has not run)")
    passed = [k for k, p in newest.items() if p.verdict == "PASS"]
    status: dict[str, int] = {}
    for p in newest.values():
        status[p.category_status] = status.get(p.category_status, 0) + 1
    return _measured("seo_certificate_pass_rate", len(passed) / len(newest), len(newest),
                     passed=sorted(passed), category_status=status)


def _release_gates(s) -> dict[str, dict]:
    newest: dict[str, dict] = {}
    for a in _audits(s, ("store.release_gates",)):
        d = a.detail or {}
        slug = d.get("slug") or _slug(a.artifact or "")
        if slug:
            newest[slug] = d
    return newest


def release_gates(s) -> dict:
    newest = _release_gates(s)
    if not newest:
        return _unmeasured("release_gate_pass_rate",
                           "no store.release_gates audit yet (no publish attempt)")
    clear = sorted(k for k, d in newest.items() if not d.get("blocks_release"))
    reasons: dict[str, int] = {}
    for d in newest.values():
        for r in (d.get("reasons") or [])[:10]:
            head = str(r).split(":", 1)[0][:60]
            reasons[head] = reasons.get(head, 0) + 1
    return _measured("release_gate_pass_rate", len(clear) / len(newest), len(newest),
                     release_ready=clear,
                     blocking_reasons=dict(sorted(reasons.items(), key=lambda kv: -kv[1])))


def time_to_publish_request(s) -> dict:
    from sqlalchemy import select

    from ..core.models import Job

    start: dict[str, datetime] = {}
    request: dict[str, datetime] = {}
    for j in s.scalars(select(Job).order_by(Job.id)):
        inputs = j.inputs or {}
        if j.job_type in ("cir.compile", "gate.certify"):
            slug = (inputs.get("cir") or {}).get("slug") if isinstance(inputs.get("cir"),
                                                                       dict) else None
            if slug and slug not in start:
                start[slug] = _aware(j.created_at)
        elif j.job_type == "store.publish" and inputs.get("slug"):
            request.setdefault(inputs["slug"], _aware(j.created_at))
    spans = [(request[k] - start[k]).total_seconds() / 3600.0
             for k in request if k in start and request[k] >= start[k]]
    if not spans:
        return _unmeasured("time_to_publish_request_hours",
                           "no slug has both a compile/certify job and a store.publish job")
    return _measured("time_to_publish_request_hours", statistics.median(spans), len(spans),
                     max_hours=round(max(spans), 4))


def cost_per_ready(s) -> dict:
    from sqlalchemy import select

    from ..core.models import CostEntry

    ready = [k for k, d in _release_gates(s).items() if not d.get("blocks_release")]
    if not ready:
        return _unmeasured("cost_per_release_ready_cad",
                           "no release-ready product yet (every newest store.release_gates "
                           "audit blocks release)")
    entries = [c for c in s.scalars(select(CostEntry)) if c.product_slug in ready]
    if not entries:
        return _unmeasured("cost_per_release_ready_cad",
                           "no actual CostEntry row for a release-ready product; the cost is "
                           "unknown, not CA$0")
    total = sum(float(c.amount_cad or 0.0) for c in entries)
    return _measured("cost_per_release_ready_cad", total / len(ready), len(entries),
                     products=len(ready), total_cad=round(total, 2), basis="actual")


READERS = (gate_first_pass, product_truth, creative_survival, catalogue_creative_survival,
           render_qa, seo_certificate,
           release_gates, time_to_publish_request, cost_per_ready)
assert len(READERS) == len(METRICS)


def readings(db) -> dict[str, dict]:
    """Every pre-sale reading, now. Read-only; one reader's failure is reported, not hidden."""
    out: dict[str, dict] = {}
    with db.session() as s:
        for reader, metric in zip(READERS, METRICS):
            try:
                out[metric] = reader(s)
            except Exception as exc:  # noqa: BLE001 - reported as unmeasured with the reason
                out[metric] = _unmeasured(metric, f"reader failed: {type(exc).__name__}: "
                                                  f"{str(exc)[:160]}")
    return out


def _fingerprint(values: dict) -> dict:
    return {k: (v["value"], v["sample"]) for k, v in values.items()}


def history(db, *, limit: int = 30) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                              .order_by(desc(AuditLog.id)).limit(limit)))
    return [{"id": r.id, "at": _aware(r.at).isoformat() if r.at else None,
             "readings": (r.detail or {}).get("readings") or {}} for r in reversed(rows)]


def record(db) -> dict:
    """Append the readings when they changed since the last recording. Idempotent."""
    from ..core.models import AuditLog

    now = readings(db)
    last = history(db, limit=1)
    compact = {k: {"value": v["value"], "sample": v["sample"], "reading": v["reading"]}
               for k, v in now.items()}
    if last and _fingerprint(last[-1]["readings"]) == _fingerprint(compact):
        return {"recorded": False, "readings": now,
                "measured": sorted(k for k, v in now.items() if v["reading"] == "MEASURED")}
    with db.session() as s:
        row = AuditLog(actor="improvement", action=ACTION,
                       detail={"readings": compact, "kind": KIND, "customer_outcome": False})
        s.add(row)
        s.flush()
        rid = row.id
    return {"recorded": True, "audit_id": rid, "readings": now,
            "measured": sorted(k for k, v in now.items() if v["reading"] == "MEASURED")}


def movement(db) -> dict[str, dict]:
    """Per metric, the newest two measured recordings and the direction between them."""
    series: dict[str, list[float]] = {}
    for h in history(db, limit=60):
        for k, v in h["readings"].items():
            if v.get("value") is not None:
                series.setdefault(k, []).append(float(v["value"]))
    out = {}
    for k, values in series.items():
        if k not in METRICS:
            continue
        if len(values) < 2:
            out[k] = {"direction": "baseline", "to": values[-1]}
            continue
        a, b = values[-2], values[-1]
        higher = METRICS[k][0]
        out[k] = {"from": a, "to": b,
                  "direction": "flat" if a == b else
                  ("improved" if (b > a) == higher else "regressed")}
    return out


def summary(db) -> dict:
    """Provider section. Never raises."""
    try:
        now = readings(db)
        measured = [k for k, v in now.items() if v["reading"] == "MEASURED"]
        return {"kind": KIND, "customer_outcome": False,
                "measured": len(measured), "of": len(METRICS),
                "readings": now, "movement": movement(db),
                "note": ("internal outcomes before any sale; none is a customer, demand or "
                         "revenue measurement and none is a proxy for one")}
    except Exception as exc:  # noqa: BLE001
        return {"kind": KIND, "measured": None, "of": len(METRICS),
                "reason": f"unreadable: {type(exc).__name__}: {str(exc)[:200]}"}
