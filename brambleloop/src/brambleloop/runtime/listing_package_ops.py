"""`listing.package` (listing): the owner-review listing package for every certified release.

Every six hours (the safety net), and at once for one release when `launch.plan` finishes
its chain (W5-A9, the event path; inputs `slug`, `version`). Assembles each certified
release's package from the chain's own stored outputs (`publish.listing_package`), records
it durably, and raises one owner review request for a package with no blocker. Internal writes only (class B, review OPUS2F A-6): no Etsy call,
model, network or spend, and nothing is published. Integrator item INTEG-LISTING-JOB, claimed as OPUS2-LISTING-PACKAGE-JOB.
"""
from __future__ import annotations

import re
from collections import Counter

from .worker import JobContext, handlers

JOB_TYPE = "listing.package"
RELEASE_FAILED = "listing.package_release_failed"
_CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]{1,63}$")


class ListingPackageNotRecorded(RuntimeError):
    """Releases of a listing-package run were not recorded. The worker writes `last_error` as
    `<class name>: <message>`; the class raised is a subclass NAMED after the releases' real
    (most common) error class, so a dead letter reads e.g. `StringDataRightTruncation: ...`
    and `ops.production_evidence.error_class` reports that class, not a generic wrapper.
    Only the class name travels; the message holds release keys and class names only."""


_NAMED: dict[str, type] = {}


def _not_recorded(failed: list[dict], single: bool, *, degraded: bool = False):
    """(exception class, message) for releases that were not recorded."""
    named = ", ".join(f"{f['key']} ({f['error_class']})" for f in failed[:10])
    more = f" and {len(failed) - 10} more" if len(failed) > 10 else ""
    what = f"listing package {'event' if single else 'sweep'}"
    tail = ("completed degraded; the next sweep retries them" if degraded else "retry the job")
    message = f"{what}: {len(failed)} release(s) not recorded: {named}{more}; {tail}"
    top = Counter(f["error_class"] for f in failed).most_common(1)[0][0]
    if not (isinstance(top, str) and _CLASS_NAME.match(top)):
        return ListingPackageNotRecorded, message
    cls = _NAMED.get(top)
    if cls is None:
        cls = _NAMED[top] = type(top, (ListingPackageNotRecorded,), {"__module__": __name__})
    return cls, message


def _replace_last_error(ctx: JobContext, text: str | None) -> None:
    """Review of a9feb805 (LOW): a DONE job must not keep an earlier attempt's `last_error`.
    Written under this run's lease (fenced on the lease token), before `complete`."""
    job_id = getattr(ctx.job, "id", None)
    if job_id is None:
        return
    from sqlalchemy import update

    from ..core.models import Job

    with ctx.db.session() as s:
        s.execute(update(Job).where(Job.id == job_id,
                                    Job.lease_token == getattr(ctx.job, "lease_token", None))
                  .values(last_error=text))


def _admit_for_sale(ctx: JobContext, results: list[dict]) -> list[dict]:
    """b17-c A3 (D-OWNER-SPEND-ORDER): the for-sale admission point. After a release's package
    is recorded, the paid FLUX gallery route is enqueued only when every non-image listing gate
    is PASS (`image_production.admit_for_sale`); otherwise an existing run is parked without
    spend. The package job itself still spends nothing: this only enqueues."""
    from ..publish import listing_package as LP
    from ..visual import image_production as IP

    done = []
    for r in results:
        key = r.get("key")
        if r.get("retry") or not isinstance(key, str) or "@" not in key:
            continue
        slug, version = key.rsplit("@", 1)
        try:
            pkg = LP.latest(ctx.db, slug, version) or {}
            release = str(pkg.get("release_hash") or "")
            if not release:
                continue
            got = IP.admit_for_sale(
                ctx.db, lambda inputs, k: ctx.enqueue("publishing", IP.JOB_TYPE, inputs,
                                                      idempotency_key=k),
                slug=slug, version=version, release=release)
            done.append({"key": key, "admitted": got["admission"]["admitted"],
                         "enqueued": bool(got.get("enqueued"))})
        except Exception as exc:  # noqa: BLE001 - admission never fails the package
            ctx.audit("visual.sale_admission_failed", artifact=key,
                      detail={"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return done


@handlers.register(JOB_TYPE)
def handle_listing_package(ctx: JobContext) -> dict:
    from ..publish import listing_package as LP

    raw = ctx.job.inputs
    i = dict(raw) if isinstance(raw, dict) else None
    # W5-A9 (P0-PACKAGE-EVENT): a job naming one release is the event `launch.plan` raises
    # when that release's chain completes; one with no release is the six-hourly sweep, kept
    # as the safety net. Both run the same per-release step, so neither duplicates the other.
    scoped = i is not None and ("slug" in i or "version" in i)
    valid_event = bool(scoped and all(
        isinstance(i.get(key), str) and i[key].strip() and i[key] == i[key].strip()
        for key in ("slug", "version")) and ("release" not in i or isinstance(i["release"], str)))
    # The scheduler and its post-deploy retry use these exact forms. A typo or
    # incomplete event must not accidentally authorize a company-wide sweep.
    valid_sweep = bool(i is not None and (not i or (
        i.get("cadence") == "listing_package" and set(i) <= {"cadence", "retry_for_commit"}
        and ("retry_for_commit" not in i or (
            isinstance(i["retry_for_commit"], str) and bool(i["retry_for_commit"].strip()))))))
    if not valid_event and not valid_sweep:
        # An incomplete per-release event is not the scheduler's deliberate
        # unscoped sweep. Refuse it without touching other releases.
        ctx.audit("listing.package_invalid_scope", detail={
            "why": "expected a complete release event or recognized listing-package sweep"})
        return {"eligible": False, "releases": 0, "ready": 0, "changed": 0,
                "publishes": False, "work_done": False, "refused": "invalid_release_scope"}
    single = valid_event
    out = (LP.for_release(ctx.db, i["slug"], i["version"], expected_release=i.get("release", ""))
           if single else LP.sweep(ctx.db))
    failed = [{"key": r.get("key"), "error_class": r.get("error_class") or "UnknownError"}
              for r in out["results"] if r.get("retry")]
    admitted = _admit_for_sale(ctx, out["results"])
    # Review of 56f92eb9 M4: the run's audit row is written whatever happened -- before any
    # retry is requested -- with every release's outcome, so the releases that WERE recorded
    # and the ones that failed (by error class) are both on file.
    ctx.audit(JOB_TYPE, artifact=(f"{i['slug']}@{i['version']}" if single else None),
              detail={"trigger": "event" if single else "sweep",
                      "eligible": out.get("eligible", True),
                      "releases": out["releases"], "ready": out["ready"],
                      "changed": out["changed"], "failed": failed[:30],
                      "attempt": int(getattr(ctx.job, "attempts", 0) or 0),
                      "sale_admission": admitted[:30],
                      "results": [{k: r.get(k) for k in ("key", "state", "blockers",
                                                         "review_requested", "error_class",
                                                         "refused")}
                                  for r in out["results"][:30]]})
    attempts = int(getattr(ctx.job, "attempts", 0) or 0)
    max_attempts = int(getattr(ctx.job, "max_attempts", 0) or 0)
    # Review of a9feb805 (LOW): with max_attempts <= 0 the queue dead-letters the first
    # failure (`attempts >= max_attempts`), so every attempt IS the last one; say so
    # explicitly rather than by the accident of `0 >= 0`.
    final_attempt = max_attempts <= 0 or attempts >= max_attempts
    for f in failed:
        # Each failing release is named durably, with its real error class.
        ctx.audit(RELEASE_FAILED, artifact=str(f["key"]), detail={
            **f, "trigger": "event" if single else "sweep",
            "attempt": attempts, "final_attempt": final_attempt})
    # Review of a9feb805 (MEDIUM): a sweep in which NOTHING was recorded is a failed sweep,
    # on the final attempt too -- it dead-letters, with the real error class and the failing
    # releases, where every DEAD-reading check sees it (the PostgreSQL period_key truncation
    # failed every release's record; that must never pass as DONE every six hours).
    recorded = [r for r in out["results"] if not r.get("retry")]
    if failed and (single or not final_attempt or not recorded):
        # Let the durable worker retry (or dead-letter on the last attempt); do not report an
        # unrecorded snapshot as done. A ValueError is not "changed repeatedly".
        cls, message = _not_recorded(failed, single)
        raise cls(message)
    degraded = bool(failed)
    refused = next((r["refused"] for r in out["results"] if r.get("refused")), None)
    if degraded:
        # Some releases recorded, some not, on the last attempt: the sweep completes so one
        # bad release does not dead-letter the rest, but DEGRADED and visibly so -- the
        # failing releases are named above (`listing.package_release_failed`, final_attempt)
        # and `ops.production_evidence.listing_package_releases` reports them; last_error is
        # replaced with what actually happened on this attempt.
        cls, message = _not_recorded(failed, single, degraded=True)
        _replace_last_error(ctx, f"{cls.__name__}: {message}")
        return {"ran": True, "trigger": "sweep", "eligible": out.get("eligible", True),
                "releases": out["releases"], "ready": out["ready"],
                "changed": out["changed"], "publishes": False,
                "work_done": bool(out["changed"]), "degraded": True,
                "recorded": len(recorded), "failed_releases": failed[:30]}
    return {"ran": True, "trigger": "event" if single else "sweep",
            "eligible": out.get("eligible", True), "releases": out["releases"],
            "ready": out["ready"], "changed": out["changed"], "publishes": False,
            "work_done": bool(out["changed"]), **({"refused": refused} if refused else {})}
