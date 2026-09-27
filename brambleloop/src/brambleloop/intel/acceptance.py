"""The benchmark acceptance test, run offline over the sanctioned API + vision path (#222, #320).

#222 asks for proof that each step of an end-to-end observation actually occurred: resolve
the shop, enumerate the catalogue, open multiple listings, traverse their galleries, produce
image-level observations, classify into pods, persist the evidence, detect a change and
trigger a re-audit. #320 asks the same of the named MJs mission and adds that access
limitations are reported honestly rather than silently downgraded.

This runner does not observe anything. It reads what the scans (`intel.observe`) and the
gallery analysis (`intel.vision`) already stored, and proves or fails each step from those
rows. That is deliberate: an acceptance test that fetched its own evidence would be testing
itself. Nothing here touches the network, spends money or writes anywhere but its own
observation rows.

**Evidence kind.** Every step is filed as a mission report of kind `api_gallery_traversal`
through `mission.record`, so it is graded by `launch.access` like every other piece of
benchmark evidence and cannot promote itself (B-105). A step additionally refuses to count
underlying rows that were themselves recorded below the mandated grade, so a fixture or a
scan run without the credential cannot pass a step by being present.

**What this does not settle.** #222 and #320 are worded "browser/vision". This path is the
official API plus the vision model, not a browser. Whether that satisfies the requirement is
an owner decision that the decision log has not recorded (B-105 grades evidence by
capability; it does not say an API traversal is a browser traversal). Until it is recorded,
every step and the run itself carry `grade_provisional` and name the missing decision,
and a PASS here is a PASS of the API+vision path, not of the browser wording.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import benchmarks, market_map, mission, pods

EVIDENCE_KIND = "api_gallery_traversal"
METHOD_VERSION = "acceptance-2026-09-26"

# "Open multiple listings": two is the smallest number that is multiple. Not a quality
# threshold, and not lowered to one because a single listing proves no enumeration.
MIN_LISTINGS = 2
# Image-level observations across at least this many distinct images.
MIN_IMAGES_OBSERVED = 2

PROVISIONAL_NOTE = (
    "graded as an API+vision traversal. #222/#320 are worded 'browser/vision'; whether this "
    "sanctioned path satisfies them needs a recorded owner decision (B-105 grades evidence by "
    "capability and does not decide that). Until then this grade is provisional.")

STEPS: tuple[str, ...] = (
    "resolve", "observed_listings", "deep_audit", "gallery_urls", "observations", "pods",
    "persist", "staleness_change", "re_audit",
    # #320's four further links: from the evidence to an action.
    "seasonal_adaptation", "launch_timing", "concept_responses", "coverage_matrix",
)

# "Multiple Brambleloop concept responses" (#320): more than one, the same floor as listings.
MIN_CONCEPT_RESPONSES = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Step:
    name: str
    passed: bool
    why: str
    evidence: dict = field(default_factory=dict)
    listings: list[str] = field(default_factory=list)
    images: int = 0
    pods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"step": self.name, "passed": self.passed, "why": self.why,
                "evidence": self.evidence, "listings": list(self.listings),
                "images": self.images, "pods": list(self.pods)}


def _load(db, benchmark_key: str) -> dict:
    from sqlalchemy import select

    from ..core.models import Benchmark, BenchmarkListing, BenchmarkObservation

    with db.session() as s:
        bench = s.scalar(select(Benchmark).where(Benchmark.key == benchmark_key))
        listings = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)
            .order_by(BenchmarkListing.listing_ref)))
        observations = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind.in_(("official_api_read", "gallery_image_observation")))
            .order_by(BenchmarkObservation.id)))
        s.expunge_all()
    return {"bench": bench, "listings": listings, "observations": observations}


def _scan_reports(observations) -> list:
    """Mandated scan reports only: the API read performed with the granted credential."""
    return [o for o in observations if o.kind == "official_api_read" and o.satisfies_mandate
            and isinstance(o.detail, dict) and "catalogue_coverage" in o.detail]


def _vision(observations) -> list:
    return [o for o in observations
            if o.kind == "gallery_image_observation" and o.satisfies_mandate]


def evaluate(db, *, benchmark_key: str = benchmarks.MJS_KEY,
             now: datetime | None = None) -> list[Step]:
    """Prove or fail every step from stored rows. Read-only."""
    now = now or _utcnow()
    data = _load(db, benchmark_key)
    bench, listings, observations = data["bench"], data["listings"], data["observations"]
    scans = _scan_reports(observations)
    vision_rows = _vision(observations)
    live = [r for r in listings if r.audit_state != "withdrawn"]
    audited = [r for r in live if r.audit_state == "audited"
               and (r.detail or {}).get("gallery_audited")]
    steps: list[Step] = []

    # 1. resolve: the named shop, by the owner's URL, through a mandated API read.
    named = [o for o in scans
             if benchmarks.MJS_SHOP.lower() in str(o.detail.get("benchmark", "")).lower()]
    owner_url = bench.owner_supplied_url if bench else ""
    ok = bool(bench) and owner_url == benchmarks.MJS_OWNER_SUPPLIED_URL and bool(named)
    steps.append(Step(
        "resolve", ok,
        (f"{len(named)} mandated API scan report(s) name {benchmarks.MJS_SHOP}; the registry "
         f"carries the owner-supplied URL verbatim" if ok else
         "no mandated API scan report names the benchmark shop" if bench else
         "the benchmark is not in the registry"),
        {"observation_ids": [o.id for o in named][-5:], "owner_supplied_url": owner_url,
         "canonical_url": bench.canonical_url if bench else ""}))

    # 2. observed_listings: the catalogue was enumerated, not sampled from one page.
    enumerated = [r for r in live if r.title and r.url]
    ok = len(enumerated) >= MIN_LISTINGS and bool(scans)
    steps.append(Step(
        "observed_listings", ok,
        (f"{len(enumerated)} listings enumerated with title and URL" if ok else
         f"{len(enumerated)} enumerated listing(s) against a floor of {MIN_LISTINGS}, "
         f"{'with' if scans else 'without'} a mandated scan behind them"),
        {"listings_known": len(listings), "live": len(live),
         "enumerated": len(enumerated)},
        listings=[r.listing_ref for r in enumerated[:10]]))

    # 3. deep_audit: individual listings opened, commerce metadata captured.
    with_meta = [r for r in audited if r.price_cad > 0 and "tags" in (r.detail or {})]
    ok = len(with_meta) >= MIN_LISTINGS
    steps.append(Step(
        "deep_audit", ok,
        (f"{len(with_meta)} listings opened with price and tags captured" if ok else
         f"{len(with_meta)} deep-audited listing(s) carrying price and tags, against "
         f"{MIN_LISTINGS}"),
        {"audited": len(audited), "with_commerce_metadata": len(with_meta)},
        listings=[r.listing_ref for r in with_meta[:10]]))

    # 4. gallery_urls: galleries traversed, image URLs stored per listing.
    galleried = [r for r in audited if [u for u in (r.detail or {}).get("image_urls") or []
                                        if u]]
    image_count = sum(len([u for u in (r.detail or {}).get("image_urls") or [] if u])
                      for r in galleried)
    ok = len(galleried) >= MIN_LISTINGS
    steps.append(Step(
        "gallery_urls", ok,
        (f"{image_count} gallery images inventoried across {len(galleried)} listings" if ok
         else f"{len(galleried)} listing(s) with a traversed gallery, against {MIN_LISTINGS}"),
        {"listings_with_gallery": len(galleried), "image_urls": image_count},
        listings=[r.listing_ref for r in galleried[:10]], images=image_count))

    # 5. observations: image-level judgements, by the vision model, at the mandated grade.
    judged_images = {(o.listing_ref, ((o.detail or {}).get("image") or {}).get("rank"))
                     for o in vision_rows}
    judged_listings = sorted({o.listing_ref for o in vision_rows})
    ok = len(judged_images) >= MIN_IMAGES_OBSERVED
    steps.append(Step(
        "observations", ok,
        (f"{len(judged_images)} images judged across {len(judged_listings)} listings" if ok
         else f"{len(judged_images)} mandated image observation(s), against "
              f"{MIN_IMAGES_OBSERVED}. Observations recorded without the capability do not "
              f"count"),
        {"observation_ids": [o.id for o in vision_rows][-10:],
         "images_judged": len(judged_images)},
        listings=judged_listings[:10], images=len(judged_images)))

    # 6. pods: the evidence was routed to specialist pods, not left unclassified.
    routed = [r for r in audited if r.pod and r.pod in pods.POD_KEYS
              and r.pod != pods.UNCLASSIFIED]
    pod_keys = sorted({r.pod for r in routed})
    ok = len(routed) >= MIN_LISTINGS
    steps.append(Step(
        "pods", ok,
        (f"{len(routed)} audited listings routed to {len(pod_keys)} pod(s)" if ok else
         f"{len(routed)} audited listing(s) routed to a specialist pod, against "
         f"{MIN_LISTINGS}"),
        {"routed": len(routed),
         "unclassified": sum(1 for r in audited if (r.pod or pods.UNCLASSIFIED)
                             == pods.UNCLASSIFIED)},
        listings=[r.listing_ref for r in routed[:10]], pods=pod_keys))

    # 7. persist: dated rows exist and the registry records when it last scanned.
    dated = [o for o in scans + vision_rows if o.at is not None]
    ok = bool(dated) and bool(bench and bench.last_scan_at)
    steps.append(Step(
        "persist", ok,
        (f"{len(dated)} dated mandated evidence rows; last scan "
         f"{_aware(bench.last_scan_at).isoformat()}" if ok else
         "no dated mandated evidence, or the registry has never recorded a scan"),
        {"dated_rows": len(dated),
         "last_scan_at": (_aware(bench.last_scan_at).isoformat()
                          if bench and bench.last_scan_at else None),
         "last_baseline_at": (_aware(bench.last_baseline_at).isoformat()
                              if bench and bench.last_baseline_at else None)}))

    # 8. staleness_change: coverage is fresh, and a change after the baseline was detected.
    last_scan = _aware(bench.last_scan_at) if bench else None
    fresh = bool(last_scan) and now - last_scan <= timedelta(
        hours=market_map.STALE_AFTER_HOURS)
    changed = [o for o in scans if not o.detail.get("baseline")
               and o.detail.get("changes")]
    ok = fresh and bool(changed)
    steps.append(Step(
        "staleness_change", ok,
        ("coverage is inside the staleness window and a post-baseline scan detected "
         f"{sum(len(o.detail['changes']) for o in changed)} change(s)" if ok else
         "; ".join(x for x in (
             "" if fresh else (f"last scan is older than {market_map.STALE_AFTER_HOURS}h"
                               if last_scan else "never scanned"),
             "" if changed else "no post-baseline scan has detected a change yet") if x)),
        {"fresh": fresh, "stale_after_hours": market_map.STALE_AFTER_HOURS,
         "change_reports": [o.id for o in changed][-5:]}))

    # 9. re_audit: a detected change led to that listing's gallery being read again.
    re_audited: list[str] = []
    for o in changed:
        moved = {c.get("listing_ref") for c in o.detail["changes"]
                 if c.get("what") in ("new listing", "materially changed")}
        re_audited += sorted(moved & set(o.detail.get("listings_inspected") or []))
    ok = bool(re_audited)
    steps.append(Step(
        "re_audit", ok,
        (f"{len(set(re_audited))} changed listing(s) were deep-audited in the scan that "
         f"detected them" if ok else
         "no detected change has a matching deep audit on record"),
        {"re_audited": sorted(set(re_audited))[:10]},
        listings=sorted(set(re_audited))[:10]))

    steps += _action_steps(db, benchmark_key)
    return steps


def _latest_cycle(db) -> tuple[int | None, dict]:
    """The most recent seasonal cycle proof run as a job, or none.

    The cycle is the one path that takes a benchmark signal to an event, a launch date and
    concepts; it is recorded by `seasonal.cycle_proof` as an audit row. A cycle computed on
    a GET leaves no row and proves nothing here, deliberately.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "seasonal.cycle_proof")
                       .order_by(desc(AuditLog.id)).limit(1))
        return (row.id, dict(row.detail or {})) if row is not None else (None, {})


def _action_steps(db, benchmark_key: str) -> list[Step]:
    """#320's last four links, proved from the cycle proof and the coverage matrix."""
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from . import coverage

    audit_id, cycle = _latest_cycle(db)
    links = {st.get("step"): st for st in cycle.get("steps") or []}
    out: list[Step] = []

    def link_step(name: str, key: str, what: str) -> Step:
        got = links.get(key) or {}
        ok = got.get("state") == "ran" and bool(got.get("evidence"))
        why = (f"the recorded cycle proof ran '{key}' with evidence: {what}" if ok else
               "no seasonal cycle proof has been recorded as a job" if audit_id is None else
               f"the latest cycle proof's '{key}' link is {got.get('state') or 'absent'}"
               + (f" (gated on {got['gated_on']})" if got.get("gated_on") else ""))
        return Step(name, ok, why, {"cycle_proof_audit_id": audit_id, "link": key,
                                    "link_state": got.get("state"),
                                    "link_evidence": got.get("evidence") or {}})

    out.append(link_step("seasonal_adaptation", "choose_event",
                         "an upcoming event with runway left was chosen"))
    out.append(link_step("launch_timing", "launch_date",
                         "the maker's lead time was chained back to a launch date"))

    gen = links.get("generate") or {}
    evidence = gen.get("evidence") or {}
    concepts = evidence.get("concepts") or evidence.get("responses") or []
    count = len(concepts) if isinstance(concepts, list) else int(evidence.get("count") or 0)
    ok = gen.get("state") == "ran" and count >= MIN_CONCEPT_RESPONSES
    out.append(Step(
        "concept_responses", ok,
        (f"{count} original concept responses recorded by the cycle proof" if ok else
         "no seasonal cycle proof has been recorded as a job" if audit_id is None else
         f"the cycle proof's generate link is {gen.get('state') or 'absent'} with {count} "
         f"concept(s), against {MIN_CONCEPT_RESPONSES}"),
        {"cycle_proof_audit_id": audit_id, "concepts": count,
         "gated_on": gen.get("gated_on") or ""}))

    with db.session() as s:
        gaps = list(s.scalars(select(CoverageGap).where(
            CoverageGap.benchmark_key == benchmark_key)))
        acted = [g for g in gaps if g.state != coverage.UNCOVERED
                 and (g.state != coverage.NOT_PURSUING or (g.reason or "").strip())]
        rows = [{"arena": g.arena, "pod": g.pod, "state": g.state,
                 "product_slug": g.product_slug} for g in acted[:10]]
    ok = bool(acted)
    out.append(Step(
        "coverage_matrix", ok,
        (f"{len(acted)} arena(s) in the coverage matrix carry a recorded action" if ok else
         f"{len(gaps)} arena(s) in the matrix and none has moved past uncovered with a "
         f"recorded action"),
        {"arenas": len(gaps), "acted_on": rows}))
    return out


def _report_for(step: Step, *, listings_known: int, run_at: str) -> dict:
    """One step as a #319-shaped mission report, checked before it is filed."""
    report = {
        "benchmark": benchmarks.MJS_SHOP,
        "observed_at": run_at,
        "catalogue_coverage": {"listings_known": listings_known,
                               "listings_inspected": len(step.listings)},
        "changes": [],
        "listings_inspected": list(step.listings),
        "images_inspected": step.images,
        "pods_notified": list(step.pods),
        "actions": [f"acceptance step {step.name}: {'PASS' if step.passed else 'FAIL'}"],
        "summary": f"acceptance step {step.name}: {step.why}",
        "acceptance_step": step.name,
        "passed": step.passed,
        "evidence": step.evidence,
        "method_version": METHOD_VERSION,
        "grade_provisional": True,
        "provisional_note": PROVISIONAL_NOTE,
    }
    mission.check_report(report)
    return report


def run(db, job_id: int | None = None, *, benchmark_key: str = benchmarks.MJS_KEY,
        env: dict[str, str] | None = None, now: datetime | None = None) -> dict:
    """Evaluate every step and file one graded mission report per step."""
    now = now or _utcnow()
    steps = evaluate(db, benchmark_key=benchmark_key, now=now)
    data = _load(db, benchmark_key)
    run_at = now.isoformat()
    grades = []
    filed = []
    for step in steps:
        report = _report_for(step, listings_known=len(data["listings"]), run_at=run_at)
        report["job_id"] = job_id
        got = mission.record(db, benchmark_key=benchmark_key, kind=EVIDENCE_KIND,
                             detail=report, listing_ref="",
                             pods_notified=tuple(p for p in step.pods if p in pods.POD_KEYS),
                             actions=tuple(report["actions"]), env=env)
        grades.append(got.grade)
        filed.append(got.observation_id)
    failed = [s.name for s in steps if not s.passed]
    passed = len(steps) - len(failed)
    mandated = all(g == "mandated" for g in grades)
    return {
        "verdict": "PASS" if not failed else "FAIL",
        "passed": passed, "of": len(steps), "failed_steps": failed,
        "grade": ("mandated (provisional: B-105 decision pending)" if mandated and not failed
                  else "supporting"),
        "grade_provisional": True, "provisional_note": PROVISIONAL_NOTE,
        "evidence_kind": EVIDENCE_KIND, "method_version": METHOD_VERSION,
        "steps": [s.to_dict() for s in steps], "observation_ids": filed,
        "run_at": run_at, "job_id": job_id,
    }


def latest(db, *, benchmark_key: str = benchmarks.MJS_KEY) -> dict:
    """The most recent filed run, read back from its step reports, or UNMEASURED."""
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkObservation

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind == EVIDENCE_KIND)
            .order_by(desc(BenchmarkObservation.id)).limit(len(STEPS) * 4)))
        s.expunge_all()
    if not rows:
        return {"status": "UNMEASURED",
                "why": "the acceptance runner has not filed a run yet"}
    run_at = (rows[0].detail or {}).get("observed_at")
    same = [r for r in rows if (r.detail or {}).get("observed_at") == run_at]
    steps = {(r.detail or {}).get("acceptance_step"): r for r in same}
    failed = [n for n in STEPS if n not in steps or not steps[n].detail.get("passed")]
    return {
        "status": "measured", "run_at": run_at,
        "verdict": "PASS" if not failed else "FAIL",
        "passed": len(STEPS) - len(failed), "of": len(STEPS), "failed_steps": failed,
        "grades": {n: steps[n].grade for n in STEPS if n in steps},
        "grade_provisional": True, "provisional_note": PROVISIONAL_NOTE,
    }


def describe(db, *, benchmark_key: str = benchmarks.MJS_KEY) -> dict:
    """What GET /api/acceptance shows: the live evaluation beside the last filed run."""
    steps = evaluate(db, benchmark_key=benchmark_key)
    failed = [s.name for s in steps if not s.passed]
    return {
        "requirements": [222, 320],
        "evidence_kind": EVIDENCE_KIND,
        "current": {"verdict": "PASS" if not failed else "FAIL",
                    "passed": len(steps) - len(failed), "of": len(steps),
                    "failed_steps": failed, "steps": [s.to_dict() for s in steps]},
        "last_run": latest(db, benchmark_key=benchmark_key),
        "provisional_note": PROVISIONAL_NOTE,
        "note": ("evaluated offline from stored scan and vision rows; this endpoint fetches "
                 "nothing and files nothing. The intel.acceptance job files the run"),
    }
