"""ENG-DAILY: the daily production ledger and the zero-output diagnosis.

The owner's P0: Mission Control shows, per UTC day, what the company actually produced, and
when a stage produced nothing the system says why and fixes what it safely can.

**Counts come from persisted rows only** (audit rows, job rows and model rows), bucketed by
the UTC day of the row's own event timestamp, for the last `DAYS` days. Each metric names its
source. A day is UNKNOWN, never 0, when:

* the source could not be read (the error class is kept, never the text);
* the day ends before the company's first recorded job (nothing was observing);
* the day starts before the source's retention horizon (`ops.retention`), so rows may be gone;
* the per-shop source is not registered for that shop.

Where the system keeps no per-event timestamp (a lifecycle stage move, the moment an Etsy id
is set) the metric counts the nearest timestamped row and says so in `basis`.

**Diagnosis.** For each stage that produced 0 today, or 0 over 24 hours where its 13-day rate
is above 0, `diagnose` records why, from the same rows: its producer job types are suspended
(with the breaker's reason), its upstream queue is empty, a gate is refusing (top reasons),
the budget refused, or a hold is in place (an unreviewed policy change, an owner veto or a
withheld release). It never changes a gate, a ceiling or an owner exception. Safe actions:

* `rearm` -- a suspended loop that `swarm.orchestrate.rearm_probe` already releases (free
  only, one probe per release) gets its one cadence job now, under the cadence's own key, so
  the scheduler cannot enqueue it twice;
* `reoffer` -- supply offers wait while admission reports open slots and no refusal (capacity,
  backlog and cost all clear) and no admission pass is due: one `supply.admit` pass.

A cause only code can fix (a loop the breaker holds with no release change, or a zero with no
cause found) files an `EngineeringChangeRequest` through `improve.ecr` when that module is
present, else records the request as `ops.ecr_pending` for ENG-IMPROVE to take.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

DAYS = 14
UNKNOWN = "UNKNOWN"
LEDGER_KIND = "ops.daily_ledger"
DIAG_KIND = "ops.zero_output"
ECR_PENDING = "ops.ecr_pending"
REARM_PREFIX = "daily-rearm"
REOFFER_PREFIX = "daily-reoffer"
TOP_REASONS = 5
_TOKEN = re.compile(r"[^a-z0-9_.:-]+")

# Audit actions read here (all windowed to DAYS, or 24 h for refusals).
A_SCAN_WATCH = "intel.watchlist_scan"
A_ADMITTED = "supply.admitted"
A_DRAFTED = "cir.drafted"
A_CERTIFIED = "gate.certified"
A_BUILT = "assets.built"
A_GALLERY = "assets.listing_images_built"
A_PACKAGE = "listing.package"
A_ETSY_DRAFT = ("store.published", "store.publish_incomplete")
A_ACTIVATED = "store.activated"
A_REPLAYED = "paid_call.replayed"
A_SPEND_REFUSED = ("spend.refused", "job.budget_exceeded")
A_WITHHELD = "gate.release_withheld"
IMAGE_JOB_PREFIXES = ("visual.", "assets.")


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _day(v) -> str | None:
    v = _aware(v)
    return v.astimezone(timezone.utc).date().isoformat() if isinstance(v, datetime) else None


def _days(now: datetime, n: int = DAYS) -> list[str]:
    today = now.astimezone(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _token(v) -> str:
    return _TOKEN.sub("_", str(v or "").strip().lower())[:60] or "unstated"


def _status(v) -> str:
    return getattr(v, "value", str(v))


# ---- sources ----------------------------------------------------------------------------

class _Src:
    """One metric's raw per-day tally and the retention horizon of the rows it reads."""

    def __init__(self, basis: str, pruned_after_days: int | None):
        self.basis, self.pruned_after_days = basis, pruned_after_days
        self.counts: dict[str, float] = {}
        self.ids: dict[str, list[str]] = {}
        # Days the source actually measured; None means every observed day was measured.
        # A day outside it is UNKNOWN (with `unmeasured_why`), never a 0.
        self.measured_days: set[str] | None = None
        self.unmeasured_why: str = "the source did not measure this day"

    def add(self, at, n: float = 1, ident: str | None = None):
        d = _day(at)
        if d is None or not n:
            return
        self.counts[d] = self.counts.get(d, 0) + n
        if ident:
            self.ids.setdefault(d, [])
            if ident not in self.ids[d] and len(self.ids[d]) < 25:
                self.ids[d].append(ident)


def _audit_days():
    from .retention import AUDIT_RETENTION_DAYS
    return AUDIT_RETENTION_DAYS


def _job_days():
    from .retention import JOB_RETENTION_DAYS
    return JOB_RETENTION_DAYS


def _audits(s, actions, since):
    from sqlalchemy import select

    from ..core.models import AuditLog

    return list(s.execute(select(AuditLog.action, AuditLog.at, AuditLog.artifact,
                                 AuditLog.detail, AuditLog.job_id)
                          .where(AuditLog.action.in_(tuple(actions)), AuditLog.at >= since)))


def _audit_src(s, actions, since, basis, weight=None, ident=None) -> _Src:
    src = _Src(basis, _audit_days())
    for r in _audits(s, actions, since):
        d = r.detail if isinstance(r.detail, dict) else {}
        src.add(r.at, weight(d) if weight else 1, ident(r, d) if ident else None)
    return src


def _pdfs(term):
    def w(d):
        pdfs = d.get("pdfs")
        return 1 if isinstance(pdfs, dict) and pdfs.get(term) else 0
    return w


def _ready_packages(d):
    return sum(1 for r in d.get("results") or [] if isinstance(r, dict)
               and r.get("state") == "ready_for_owner_review")


def _etsy_id(r, d):
    v = d.get("etsy_listing_id")
    return str(v)[:32] if v else None


def _metrics(db, since, now) -> dict[str, _Src]:
    """Every metric's tally. Each reader has its own session, so one failed read (which
    aborts a PostgreSQL transaction) is that metric's UNKNOWN, never its neighbours'."""
    from sqlalchemy import select

    from ..core.models import CostEntry, Job, JobStatus, Lesson

    out: dict[str, _Src | Exception] = {}
    s = None

    def call(fn, keys):
        nonlocal s
        try:
            with db.session() as sess:
                s = sess
                got = fn()
            got = got if isinstance(got, tuple) else (got,)
            out.update(dict(zip(keys, got)))
        except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never 0
            out.update({k: exc for k in keys})

    def run(key, fn):
        call(fn, (key,))

    def concepts():
        from sqlalchemy import inspect

        from ..radar.intake import RadarConcept

        made = _Src("radar_concepts rows by `at`", None)
        ok = _Src("radar_concepts approved, by `decided_at`", None)
        no = _Src("radar_concepts refused, by `decided_at`", None)
        if not inspect(s.get_bind()).has_table(RadarConcept.__tablename__):
            return made, ok, no      # created with the first proposal: none was ever made
        for at, dec, st in s.execute(select(RadarConcept.at, RadarConcept.decided_at,
                                            RadarConcept.state)):
            if _aware(at) and _aware(at) >= since:
                made.add(at)
            if dec is not None and _aware(dec) >= since:
                (ok if st == "approved" else no if st == "refused" else _Src("", None)).add(dec)
        return made, ok, no

    def held():
        from ..core.models import OperatingReading
        from .flow_health import SUPPLY_STALL_KIND

        # A stall reading is written only when a scan found a stall, so a day with no
        # completed radar.scan has no reading either way: it is UNKNOWN, never 0 held
        # (review of a795be17, Unit B finding 3). The scan days come from Job rows, so the
        # horizon is the job retention horizon.
        src = _Src("radar.supply_stall readings: concepts held, by reading time; 0 when a "
                   "completed radar.scan found supply, UNKNOWN when no radar.scan completed",
                   _job_days())
        src.measured_days = {d for (f,) in s.execute(select(Job.finished_at).where(
            Job.job_type == "radar.scan", Job.status == JobStatus.DONE,
            Job.finished_at >= since)) if (d := _day(f))}
        src.unmeasured_why = "no radar.scan completed this day"
        for at, p in s.execute(select(OperatingReading.at, OperatingReading.payload).where(
                OperatingReading.kind == SUPPLY_STALL_KIND, OperatingReading.at >= since)):
            src.add(at, len((p or {}).get("held") or {}))
            if (d := _day(at)):
                src.measured_days.add(d)     # a stall reading is itself a measurement
        return src

    call(concepts, ("concepts_created", "concepts_approved", "concepts_refused"))
    run("concepts_held", held)
    run("concepts_admitted", lambda: _audit_src(
        s, (A_ADMITTED,), since, "supply.admitted audit rows (admitted to engineering)"))
    run("products_started", lambda: _audit_src(
        s, (A_DRAFTED,), since, "cir.drafted audit rows (a CIR draft written)",
        ident=lambda r, d: r.artifact))
    run("certifications", lambda: _audit_src(
        s, (A_CERTIFIED,), since, "gate.certified audit rows", ident=lambda r, d: r.artifact))
    run("pdfs_us", lambda: _audit_src(s, (A_BUILT,), since,
                                      "assets.built rows carrying a US PDF", _pdfs("US")))
    run("pdfs_uk", lambda: _audit_src(s, (A_BUILT,), since,
                                      "assets.built rows carrying a UK PDF", _pdfs("UK")))

    def images():
        from ..visual.image_records import ImageCandidate

        gen = _Src("image_candidates rows by `created_at`, provider errors excluded", None)
        ver = _Src("image_candidates accepted (verified), by `created_at`: no verify time "
                   "is stored", None)
        for at, outcome in s.execute(select(ImageCandidate.created_at, ImageCandidate.outcome)
                                     .where(ImageCandidate.created_at >= since)):
            if outcome != "provider_error":
                gen.add(at)
            if outcome == "accepted":
                ver.add(at)
        return gen, ver

    call(images, ("images_generated", "images_verified"))

    def recovered():
        src = _Src("paid_call.replayed rows on visual./assets. jobs (a paid image result "
                   "replayed, not re-bought)", _audit_days())
        rows = _audits(s, (A_REPLAYED,), since)
        ids = {r.job_id for r in rows if r.job_id}
        types = dict(s.execute(select(Job.id, Job.job_type).where(Job.id.in_(ids)))) if ids \
            else {}
        for r in rows:
            if str(types.get(r.job_id, "")).startswith(IMAGE_JOB_PREFIXES):
                src.add(r.at)
        return src

    run("images_recovered", recovered)
    run("galleries_completed", lambda: _audit_src(
        s, (A_GALLERY,), since, "assets.listing_images_built audit rows",
        ident=lambda r, d: r.artifact))
    run("listing_packages", lambda: _audit_src(
        s, (A_PACKAGE,), since, "listing.package results ready_for_owner_review",
        _ready_packages))
    run("etsy_drafts", lambda: _audit_src(
        s, A_ETSY_DRAFT, since, "store.published / store.publish_incomplete rows (the remote "
        "draft was created; Listing has no time for when its id was set)", ident=_etsy_id))
    run("etsy_live", lambda: _audit_src(s, (A_ACTIVATED,), since,
                                        "store.activated rows", ident=_etsy_id))

    def lessons():
        made = _Src("lessons rows by `at`", None)
        used = _Src("lessons.acted_on_by entries by their `at`", None)
        for at, acted in s.execute(select(Lesson.at, Lesson.acted_on_by)):
            if _aware(at) and _aware(at) >= since:
                made.add(at)
            for e in acted or []:
                when = _parse(e.get("at")) if isinstance(e, dict) else None
                if when and when >= since:
                    used.add(when)
        return made, used

    call(lessons, ("lessons_learned", "lessons_applied"))

    def dead():
        from ..queue.durable import DEFECT, classify_dead_letter

        dl = _Src("jobs DEAD, by `finished_at`", _job_days())
        fail = _Src("jobs DEAD classified as a defect (not a refusal or stand-aside)",
                    _job_days())
        for jt, err, at in s.execute(select(Job.job_type, Job.last_error, Job.finished_at)
                                     .where(Job.status == JobStatus.DEAD,
                                            Job.finished_at >= since)):
            dl.add(at)
            if classify_dead_letter(jt, err or "") == DEFECT:
                fail.add(at)
        return dl, fail

    call(dead, ("dead_letters", "failures"))

    def spend():
        src = _Src("cost_entries amount_cad by `at` (never pruned)", None)
        for at, amt in s.execute(select(CostEntry.at, CostEntry.amount_cad)
                                 .where(CostEntry.at >= since)):
            src.add(at, float(amt or 0.0))
        return src

    run("spend_cad", spend)

    def advanced():
        from ..autonomy.kpis import did_no_work
        from ..products.lifecycle import PIPELINE_JOBS

        per = {jt: _Src(f"{jt} jobs DONE with useful work, by `finished_at` (stage moves "
                        "carry no time of their own)", _job_days()) for jt in PIPELINE_JOBS}
        for jt, outputs, at in s.execute(select(Job.job_type, Job.outputs, Job.finished_at)
                                         .where(Job.job_type.in_(PIPELINE_JOBS),
                                                Job.status == JobStatus.DONE,
                                                Job.finished_at >= since)):
            if not did_no_work(outputs or {}, jt):
                per[jt].add(at)
        return per

    from ..products.lifecycle import PIPELINE_JOBS

    call(lambda: tuple(advanced()[jt] for jt in PIPELINE_JOBS),
         tuple(f"advanced:{jt}" for jt in PIPELINE_JOBS))
    return out


def _parse(v):
    if isinstance(v, datetime):
        return _aware(v)
    try:
        return _aware(datetime.fromisoformat(str(v)))
    except (TypeError, ValueError):
        return None


def _shop_scans(s, since) -> list[dict]:
    """Per owner shop, attempted and successful scans per day. The anchor's evidence is its
    `mjs.scan` jobs; the watchlist shops' is each `intel.watchlist_scan` row's shop list."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..intel import watchlist
    from ..intel.scan_evidence import OWNER_SHOPS
    from ..runtime.intel_ops import benchmark_alias

    by_name = {m.shop_name.lower(): m for m in watchlist.WATCHLIST}
    watch_rows = None
    out = []
    for order, (name, _url, role) in enumerate(OWNER_SHOPS, start=1):
        tried, ok = _Src("", _job_days()), _Src("", _job_days())
        entry = {"owner_order": order, "role": role}
        try:
            if role == "anchor":
                entry["alias"] = "anchor"
                entry["basis"] = "mjs.scan jobs DONE that ran (deferred runs are not attempts)"
                for outputs, at in s.execute(select(Job.outputs, Job.finished_at).where(
                        Job.job_type == "mjs.scan", Job.status == JobStatus.DONE,
                        Job.finished_at >= since)):
                    o = outputs or {}
                    if o.get("deferred") or not o.get("ran"):
                        continue
                    tried.add(at)
                    if not o.get("credential_refused"):
                        ok.add(at)
            else:
                m = by_name.get(name.lower())
                if m is None:
                    out.append({**entry, "alias": None, "registered": False,
                                "why": "not registered on the watchlist"})
                    continue
                alias = benchmark_alias(m.key)
                entry["alias"] = alias
                entry["basis"] = "intel.watchlist_scan rows, this shop's entry (not deferred)"
                tried.pruned_after_days = ok.pruned_after_days = _audit_days()
                if watch_rows is None:
                    watch_rows = _audits(s, (A_SCAN_WATCH,), since)
                for r in watch_rows:
                    for sh in (r.detail or {}).get("shops") or []:
                        if not isinstance(sh, dict) or sh.get("alias") != alias \
                                or sh.get("deferred"):
                            continue
                        tried.add(r.at)
                        if sh.get("ran") and sh.get("state") == "ok":
                            ok.add(r.at)
            out.append({**entry, "registered": True, "attempted": tried, "succeeded": ok})
        except Exception as exc:  # noqa: BLE001
            out.append({**entry, "registered": True, "attempted": exc, "succeeded": exc})
    return out


# ---- finalising: counts with UNKNOWN ----------------------------------------------------

def _series(src, days: list[str], observed_from: date | None, now: datetime) -> dict:
    if isinstance(src, Exception):
        return {"days": {d: UNKNOWN for d in days}, "basis": None,
                "error_class": type(src).__name__}
    horizon = None
    if src.pruned_after_days is not None:
        horizon = (now - timedelta(days=src.pruned_after_days)).date()
    vals, why = {}, {}
    for d in days:
        dd = date.fromisoformat(d)
        if observed_from is None or dd < observed_from:
            vals[d], why[d] = UNKNOWN, "before the first recorded job"
        elif horizon is not None and dd <= horizon:
            # The horizon day itself is partly pruned, so it is UNKNOWN too (finding 5).
            vals[d], why[d] = UNKNOWN, "older than the source's retention horizon"
        elif src.measured_days is not None and d not in src.measured_days:
            vals[d], why[d] = UNKNOWN, src.unmeasured_why
        else:
            v = src.counts.get(d, 0)
            vals[d] = round(v, 2) if isinstance(v, float) else v
    out = {"days": vals, "basis": src.basis}
    if why:
        out["unknown_why"] = why
    if src.ids:
        out["ids"] = {d: src.ids[d] for d in days if d in src.ids}
    return out


def _observed_from(s) -> date | None:
    from sqlalchemy import func, select

    from ..core.models import Job

    first = _aware(s.scalar(select(func.min(Job.created_at))))
    return first.date() if first else None


def _reasons(db, since) -> dict:
    """Why concepts were held or refused, counted over the window (reason tokens only)."""
    from sqlalchemy import select

    from ..core.models import OperatingReading
    from .flow_health import SUPPLY_STALL_KIND

    held: dict[str, int] = {}
    refused: dict[str, int] = {}
    try:
        with db.session() as s:
            rows = list(s.execute(select(OperatingReading.payload).where(
                OperatingReading.kind == SUPPLY_STALL_KIND, OperatingReading.at >= since)))
        for (p,) in rows:
            for why in ((p or {}).get("held") or {}).values():
                k = _token(why if isinstance(why, str) else (why or {}).get("reason"))
                held[k] = held.get(k, 0) + 1
    except Exception:  # noqa: BLE001
        held = None
    try:
        from ..radar.intake import RadarConcept

        with db.session() as s:
            rows = list(s.execute(select(RadarConcept.reasons).where(
                RadarConcept.state == "refused", RadarConcept.decided_at >= since)))
        for (rs,) in rows:
            for why in (rs or [])[:3]:
                k = _token(str(why).split(":")[0])
                refused[k] = refused.get(k, 0) + 1
    except Exception:  # noqa: BLE001
        refused = None

    def top(d):
        return None if d is None else dict(sorted(d.items(), key=lambda kv: -kv[1])
                                           [:TOP_REASONS])
    return {"held": top(held), "refused": top(refused)}


def ledger(db, *, now: datetime | None = None, days: int = DAYS) -> dict:
    """Per-UTC-day counts for the last `days` days, from persisted rows. Writes nothing."""
    now = _aware(now) or datetime.now(timezone.utc)
    day_list = _days(now, days)
    since = datetime.combine(date.fromisoformat(day_list[0]), datetime.min.time(),
                             tzinfo=timezone.utc)
    try:
        with db.session() as s:
            observed = _observed_from(s)
    except Exception:  # noqa: BLE001 - no observation start: every day is UNKNOWN
        observed = None
    raw = _metrics(db, since, now)
    try:
        with db.session() as s:
            shops = _shop_scans(s, since)
    except Exception as exc:  # noqa: BLE001
        shops = exc
    reasons = _reasons(db, since)
    metrics = {k: _series(v, day_list, observed, now) for k, v in raw.items()}
    if isinstance(shops, Exception):
        shop_rows = {"error_class": type(shops).__name__}
    else:
        shop_rows = []
        for r in shops:
            row = {k: r.get(k) for k in ("owner_order", "role", "alias", "registered",
                                         "basis", "why")}
            if r.get("registered"):
                row["attempted"] = _series(r["attempted"], day_list, observed, now)["days"]
                row["succeeded"] = _series(r["succeeded"], day_list, observed, now)["days"]
            else:
                row["attempted"] = row["succeeded"] = {d: UNKNOWN for d in day_list}
            shop_rows.append(row)
        metrics["scans_succeeded"] = {"days": _sum_days(
            [r["succeeded"] for r in shop_rows], day_list),
            "basis": "sum over the owner's shops; UNKNOWN if any shop is UNKNOWN"}
    return {"as_of": now.isoformat(), "days": day_list, "today": day_list[-1],
            "today_partial": True, "observed_from": observed.isoformat() if observed else None,
            "unknown_rule": "UNKNOWN is never 0: unreadable source, before the first "
                            "recorded job, past the retention horizon or not registered",
            "metrics": metrics, "shops": shop_rows, "reasons": reasons}


def _sum_days(series: list[dict], days: list[str]) -> dict:
    out = {}
    for d in days:
        vals = [x.get(d) for x in series]
        out[d] = UNKNOWN if not vals or any(v == UNKNOWN or v is None for v in vals) \
            else sum(vals)
    return out


# ---- zero-output diagnosis --------------------------------------------------------------

# (stage, ledger metric, producer job types, upstream metric, refusal actions, holds apply)
STAGES: tuple[tuple[str, str, tuple[str, ...], str | None, tuple[str, ...], str], ...] = (
    ("scans", "scans_succeeded", ("mjs.scan", "intel.watchlist_scan"), None,
     ("mjs.scan_blocked",), ""),
    ("concepts", "concepts_created", ("radar.concept_intake", "radar.scan"), None,
     ("concept.intake_refused",), ""),
    ("products_started", "products_started", ("cir.draft", "supply.admit"),
     "concepts_admitted", ("cir.draft_refused",), "manufacturing"),
    ("certifications", "certifications", ("gate.certify",), "products_started",
     ("gate.blocked", "gate.halted"), "manufacturing"),
    ("pdfs", "pdfs_us", ("assets.build",), "certifications",
     ("assets.deliverable_problems",), "manufacturing"),
    ("galleries", "galleries_completed", ("assets.build",), "certifications",
     ("assets.listing_images_blocked",), "manufacturing"),
    ("listing_packages", "listing_packages", ("listing.package",), "galleries_completed",
     ("listing.package_release_failed",), "publication"),
    ("etsy_drafts", "etsy_drafts", ("store.publish",), "listing_packages",
     ("store.publish_refused", "store.publish_blocked"), "publication"),
    ("lessons", "lessons_learned", ("learn.scan", "improve.mine", "improve.retrospective"),
     None, (), ""),
)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# A stage is zero-output only when, by this hour of the UTC day, its historical rate
# expects clearly more than nothing and what it made is far below that (review of
# a795be17, Unit B finding 2). Before that it is "not yet due": a reading, never DEGRADED.
EXPECTED_MIN = 1.0          # expected count by now must be at least this
FAR_BELOW = 0.2             # observed <= FAR_BELOW * expected counts as far below
MIN_HOURS_INTO_DAY = 6      # the first six-hourly run of a UTC day never diagnoses
NOT_YET_DUE = "not_yet_due"
ZERO_OUTPUT = "zero_output"
PRODUCING = "producing"


def _day_fraction(led: dict, now: datetime) -> float:
    start = datetime.combine(date.fromisoformat(led["days"][-1]), datetime.min.time(),
                             tzinfo=timezone.utc)
    return min(1.0, max(0.0, (now - start).total_seconds() / 86400))


def stage_readings(led: dict, *, now: datetime) -> list[dict]:
    """Every stage's reading today: zero_output, not_yet_due, producing or UNKNOWN."""
    days = led["days"]
    today, yesterday = days[-1], days[-2] if len(days) > 1 else None
    frac = _day_fraction(led, now)
    out = []
    for stage, metric, *_rest in STAGES:
        series = (led["metrics"].get(metric) or {}).get("days") or {}
        t = series.get(today, UNKNOWN)
        if t == UNKNOWN or _num(t) is None:
            out.append({"stage": stage, "metric": metric, "today": UNKNOWN,
                        "status": UNKNOWN, "unknown": True})
            continue
        prior = [_num(series.get(d)) for d in days[:-1]]
        known = [p for p in prior if p is not None]
        rate = (sum(known) / len(known)) if known else None
        expected = None if rate is None else rate * frac
        y = _num(series.get(yesterday)) if yesterday else None
        # The last 24 h: today, plus yesterday's share by the hour (an estimate, labelled).
        last24 = None if y is None else t + y * max(0.0, 1 - frac)
        row = {"stage": stage, "metric": metric, "today": t,
               "last_24h_estimate": None if last24 is None else round(last24, 2),
               "expected_per_day": None if rate is None else round(rate, 2),
               "expected_by_now": None if expected is None else round(expected, 2),
               "hours_into_day": round(frac * 24, 2)}
        if (frac * 24 >= MIN_HOURS_INTO_DAY and expected is not None
                and expected >= EXPECTED_MIN and t <= FAR_BELOW * expected):
            row["status"] = ZERO_OUTPUT
        elif t > 0:
            row["status"] = PRODUCING
        else:
            row["status"] = NOT_YET_DUE
            row["why"] = ("no history to expect output from" if rate is None else
                          f"{round(expected, 2)} expected by now, under {EXPECTED_MIN}"
                          if expected < EXPECTED_MIN else
                          f"under {MIN_HOURS_INTO_DAY} h into the UTC day")
        out.append(row)
    return out


def zero_stages(led: dict, *, now: datetime) -> list[dict]:
    """The stages to diagnose: zero-output ones, and UNKNOWN ones listed apart."""
    return [r for r in stage_readings(led, now=now) if r["status"] in (ZERO_OUTPUT, UNKNOWN)]


def _top(rows) -> list[dict]:
    seen: dict[str, int] = {}
    for d in rows:
        d = d if isinstance(d, dict) else {}
        rs = d.get("reasons") or ([d["reason"]] if d.get("reason") else [])
        if isinstance(rs, dict):
            rs = list(rs.values())
        for r in (rs or ["unstated"])[:3]:
            k = _token(str(r).split(":")[0])
            seen[k] = seen.get(k, 0) + 1
    return [{"reason": k, "count": n} for k, n in
            sorted(seen.items(), key=lambda kv: -kv[1])[:TOP_REASONS]]


def _causes(db, s, stage_def, led, *, now, suspended) -> list[dict]:
    from sqlalchemy import func, select

    from ..core.models import AuditLog, Job, JobStatus, OwnerVeto

    stage, metric, producers, upstream, refusals, holds = stage_def
    since = now - timedelta(hours=24)
    causes = []
    for jt in producers:
        if jt in suspended:
            sus = suspended[jt]
            causes.append({"kind": "suspended", "job_type": jt,
                           "suspension": sus.get("kind"), "incident": sus.get("incident"),
                           "why": sus.get("why") or (f"backed off until {sus.get('until')}"
                                                     if sus.get("until") else None)})
    live = s.scalar(select(func.count()).select_from(Job).where(
        Job.job_type.in_(producers), Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING))))
    recent = s.scalar(select(func.count()).select_from(Job).where(
        Job.job_type.in_(producers), Job.created_at >= since))
    if upstream:
        up = (led["metrics"].get(upstream) or {}).get("days") or {}
        last2 = [up.get(d) for d in led["days"][-2:]]
        if all(v == 0 for v in last2) and not live:
            causes.append({"kind": "queue_empty_upstream", "upstream": upstream,
                           "producer_jobs_open": live, "producer_jobs_24h": recent})
    elif not live and not recent and not any(c["kind"] == "suspended" for c in causes):
        causes.append({"kind": "queue_empty_upstream", "upstream": None,
                       "producer_jobs_open": 0, "producer_jobs_24h": 0})
    if refusals:
        rows = [d for (d,) in s.execute(select(AuditLog.detail).where(
            AuditLog.action.in_(refusals), AuditLog.at >= since))]
        if rows:
            causes.append({"kind": "gate_refusing", "refusals_24h": len(rows),
                           "actions": list(refusals), "top_reasons": _top(rows)})
    budget = s.scalar(select(func.count()).select_from(Job).where(
        Job.job_type.in_(producers), Job.finished_at >= since,
        Job.last_error.like("budget exceeded%")))
    spend_refused = s.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action.in_(A_SPEND_REFUSED), AuditLog.at >= since))
    if budget or spend_refused:
        causes.append({"kind": "budget_refused", "producer_jobs_refused_24h": budget,
                       "spend_refusals_24h": spend_refused})
    if holds:
        try:
            from ..gates.platform_policy import unreviewed_changes
            from ..publish.release_gates import policy_holds_manufacturing

            changes = unreviewed_changes(db)
            held = (policy_holds_manufacturing(changes) if holds == "manufacturing" else
                    sorted({str(c.get("source")) for c in changes
                            if "publishing" in (c.get("affects") or ())}))
            if held:
                causes.append({"kind": "hold", "hold": "policy",
                               "sources": [_token(x) for x in held][:5]})
        except Exception as exc:  # noqa: BLE001 - an unreadable hold is named, never "none"
            causes.append({"kind": "hold", "hold": "policy", "unknown": type(exc).__name__})
        vetoes = s.scalar(select(func.count()).select_from(OwnerVeto).where(
            OwnerVeto.owner_vetoed.is_(True), OwnerVeto.at >= now - timedelta(days=DAYS)))
        withheld = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == A_WITHHELD, AuditLog.at >= since))
        if vetoes or withheld:
            causes.append({"kind": "hold", "hold": "owner", "owner_vetoes_14d": vetoes,
                           "releases_withheld_24h": withheld})
    return causes


def _fingerprint(defect_class: str, department: str, module: str) -> str:
    """ENG-IMPROVE's fingerprint when present, else the same formula (so the two agree)."""
    try:
        from ..improve.ecr import fingerprint
    except ImportError:
        import hashlib

        def fingerprint(c, d, m):
            raw = f"{c.strip().lower()}|{d.strip().lower()}|{m.strip().lower()}"
            return hashlib.sha256(raw.encode()).hexdigest()[:32]
    return fingerprint(defect_class, department, module)


def _pending_exists(db, artifact: str, fp: str, day: str) -> bool:
    """A fallback `ops.ecr_pending` row for this fingerprint already filed on this UTC day."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    start = datetime.combine(date.fromisoformat(day), datetime.min.time(), tzinfo=timezone.utc)
    with db.session() as s:
        for (d,) in s.execute(select(AuditLog.detail).where(
                AuditLog.action == ECR_PENDING, AuditLog.artifact == artifact,
                AuditLog.at >= start, AuditLog.at < start + timedelta(days=1))):
            if (d or {}).get("fingerprint") in (None, fp):
                return True
    return False


def _file_ecr(db, *, day: str, now: datetime, filed: set[str] | None = None, **kw) -> dict:
    """File through ENG-IMPROVE's `improve.ecr.file`; else a pending request row.

    Deduplicated by fingerprint per stage per UTC day (review of a795be17, Unit B finding 2):
    `filed` holds the fingerprints today's diagnosis row for this stage already filed, and
    the fallback also checks for a pending row of the same fingerprint today, so a repeated
    run neither adds a pending row nor inflates an open request's `occurrences`."""
    fp = _fingerprint(kw["defect_class"], kw["department"], kw["module"])
    if filed is not None and fp in filed:
        return {"filed": False, "deduped": True, "fingerprint": fp}
    try:
        from ..improve import ecr
    except ImportError:
        ecr = None
    if ecr is not None and hasattr(ecr, "file"):
        try:
            got = ecr.file(db, filed_by="ops.daily_ledger", **kw)
            return {"filed": True, "id": got.get("id"), "created": got.get("created"),
                    "fingerprint": fp}
        except Exception as exc:  # noqa: BLE001 - recorded, the diagnosis still stands
            return {"filed": False, "error_class": type(exc).__name__, "fingerprint": fp}
    from ..core.models import AuditLog

    artifact = f"ecr:{kw['defect_class']}:{kw['module']}"[:200]
    if _pending_exists(db, artifact, fp, day):
        return {"filed": False, "deduped": True, "pending": True, "fingerprint": fp}
    with db.session() as s:
        s.add(AuditLog(actor="ops.daily_ledger", action=ECR_PENDING, artifact=artifact, at=now,
                       detail={"request": kw, "for": "improve.ecr.file", "fingerprint": fp,
                               "day": day}))
    return {"filed": False, "pending": True, "fingerprint": fp}


def _cadence_for(job_type: str):
    from ..runtime.worker import CADENCES

    return next(((n, a, jt, p) for n, a, jt, p in CADENCES if jt == job_type), None)


def _rearm(db, queue, jt: str, *, now) -> dict | None:
    """Enqueue the one probe `rearm_probe` grants (free loops only), under the cadence key."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..runtime.worker import cadence_key
    from ..swarm import orchestrate as orc

    cad = _cadence_for(jt)
    if cad is None:
        return None
    with db.session() as s:
        if orc.spending_job_type(s, jt):
            return None
        hit = None
        for inc in s.scalars(select(Incident).where(
                Incident.resolved.is_(False),
                Incident.signature.like(f"{orc.THRASH_SIGNATURE_PREFIX}%"))):
            sus = (inc.detail or {}).get("suspension") or {}
            if sus.get("job_type") == jt and sus.get("kind") in (orc.BACKOFF, orc.SUSPENDED):
                hit = orc.rearm_probe(s, jt, sus)
                if hit:
                    break
    if not hit:
        return None
    name, agent, _jt, period = cad
    key = cadence_key(name, period, now)
    try:
        job = queue.enqueue(agent, jt, {"cadence": name, "rearm": hit["release"]},
                            idempotency_key=key, priority=orc.priority_for(jt))
    except Exception:  # noqa: BLE001 - the key exists: the scheduler already enqueued it
        return {"action": "rearm", "job_type": jt, "enqueued": False, "key": key,
                "why": "the probe for this window is already queued"}
    return {"action": "rearm", "job_type": jt, "enqueued": True, "job": job.id, "key": key,
            "release": hit["release"]}


def _reoffer(db, queue, *, now) -> dict | None:
    """One admission pass when offers wait, admission is clear and no pass is due."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..products import supply

    waiting = supply.offers(db)
    if not waiting:
        return None
    cap = supply.assess(db, now=now)
    if cap.get("refusals") or not cap.get("slots"):
        return {"action": "reoffer", "enqueued": False, "offers_waiting": len(waiting),
                "why": "admission refuses: " + "; ".join(cap.get("refusals") or
                                                         ["no open slot"])[:200]}
    with db.session() as s:
        due = s.scalar(select(Job.id).where(Job.job_type == "supply.admit",
                                            Job.status.in_((JobStatus.PENDING,
                                                            JobStatus.RUNNING))).limit(1))
    if due is not None:
        return {"action": "reoffer", "enqueued": False, "offers_waiting": len(waiting),
                "why": "an admission pass is already queued"}
    key = f"{REOFFER_PREFIX}:{now.date().isoformat()}"
    try:
        job = queue.enqueue("orchestrator", "supply.admit", {"reoffer": True},
                            idempotency_key=key)
    except Exception:  # noqa: BLE001 - today's re-offer already ran
        return {"action": "reoffer", "enqueued": False, "key": key,
                "why": "today's re-offer pass already exists"}
    return {"action": "reoffer", "enqueued": True, "job": job.id, "key": key,
            "offers_waiting": len(waiting)}


def _department(jt: str) -> str:
    try:
        from ..autonomy.charters import department_of

        return department_of(jt) or "engineering"
    except Exception:  # noqa: BLE001
        return "engineering"


def diagnose(db, queue=None, *, now: datetime | None = None, act: bool = True,
             led: dict | None = None) -> dict:
    """Diagnose every zero stage and record one row per (day, stage). `act=False` reads only."""
    from ..core.models import OperatingReading
    from ..swarm.orchestrate import suspended_job_types

    now = _aware(now) or datetime.now(timezone.utc)
    led = led or ledger(db, now=now)
    try:
        suspended = suspended_job_types(db, now=now)
    except Exception:  # noqa: BLE001
        suspended = {}
    defs = {d[0]: d for d in STAGES}
    rows = []
    for z in zero_stages(led, now=now):
        d = defs[z["stage"]]
        key = f"{led['today']}:{z['stage']}"
        prior_payload = {}
        if act:
            from sqlalchemy import select

            with db.session() as s:
                prior_payload = dict(s.scalar(select(OperatingReading.payload).where(
                    OperatingReading.kind == DIAG_KIND,
                    OperatingReading.period_key == key)) or {})
        prior_ecrs = [e for e in prior_payload.get("ecrs") or [] if isinstance(e, dict)]
        filed_today = {e["fingerprint"] for e in prior_ecrs if e.get("fingerprint")
                       and (e.get("filed") or e.get("pending"))}
        # A change request needs the whole 24-hour window at zero, not the partial day.
        window_zero = z.get("last_24h_estimate") == 0
        if z.get("unknown"):
            m = led["metrics"].get(z["metric"]) or {}
            causes = [{"kind": "unknown", "error_class": m.get("error_class"),
                       "why": (m.get("unknown_why") or {}).get(led["today"])
                       or "today's count could not be read"}]
        else:
            try:
                with db.session() as s:
                    causes = _causes(db, s, d, led, now=now, suspended=suspended)
            except Exception as exc:  # noqa: BLE001
                causes = [{"kind": "unknown", "error_class": type(exc).__name__}]
        if not causes:
            causes = [{"kind": "undiagnosed", "why": "no recorded cause explains the zero"}]
        actions, ecrs = [], []
        if act and queue is not None:
            for c in causes:
                if c["kind"] == "suspended":
                    got = _rearm(db, queue, c["job_type"], now=now)
                    if got:
                        actions.append(got)
                    elif window_zero:
                        ecrs.append(_file_ecr(
                            db, day=led["today"], now=now, filed=filed_today,
                            defect_class="failing_loop",
                            department=_department(c["job_type"]), module=c["job_type"],
                            title=f"{c['job_type']} suspended while {z['stage']} produced 0",
                            problem=f"The thrash breaker holds {c['job_type']} "
                                    f"({c.get('suspension')}) and no release change re-arms "
                                    "it; the stage it feeds produced nothing.",
                            evidence={"stage": z["stage"], "day": led["today"],
                                      "incident": c.get("incident"),
                                      "examples": [c.get("incident")]},
                            proposed_change="Fix the cause the breaker recorded and "
                                            "release, so rearm_probe grants its probe.",
                            acceptance_criteria=[f"{z['metric']} above 0 within 24 h of "
                                                 "the deploy"],
                            priority="P1"))
                elif c["kind"] == "queue_empty_upstream" and z["stage"] == "products_started":
                    got = _reoffer(db, queue, now=now)
                    if got:
                        actions.append(got)
                elif c["kind"] == "undiagnosed" and window_zero:
                    ecrs.append(_file_ecr(
                        db, day=led["today"], now=now, filed=filed_today,
                        defect_class="missing_capability", department="engineering",
                        module=f"ops.daily_ledger:{z['stage']}",
                        title=f"{z['stage']} produced 0 with no recorded cause",
                        problem="The daily ledger reads 0 and no suspension, empty queue, "
                                "gate refusal, budget refusal or hold explains it.",
                        evidence={"stage": z["stage"], "day": led["today"],
                                  "expected_per_day": z.get("expected_per_day"),
                                  "examples": [led["today"]]},
                        proposed_change="Instrument or repair the producer so its zero is "
                                        "explained by a row.",
                        acceptance_criteria=["the stage's zero names a cause, or the "
                                             "stage produces"], priority="P2"))
        payload = {**z, "day": led["today"], "causes": causes, "actions": actions,
                   "ecrs": ecrs, "at": now.isoformat()}
        if act:
            from sqlalchemy import select

            with db.session() as s:
                row = s.scalar(select(OperatingReading).where(
                    OperatingReading.kind == DIAG_KIND, OperatingReading.period_key == key))
                if row is None:
                    s.add(OperatingReading(kind=DIAG_KIND, period_key=key, payload=payload,
                                           at=now))
                else:
                    prior = list((row.payload or {}).get("actions") or [])
                    kept = [e for e in prior_ecrs if e.get("filed") or e.get("pending")]
                    fresh = [e for e in ecrs if not e.get("deduped")]
                    row.payload = {**payload, "actions": prior + actions,
                                   "ecrs": kept + fresh}
        rows.append(payload)
    return {"day": led["today"], "diagnosed": rows,
            "zero_stages": [r["stage"] for r in rows],
            "actions_taken": sum(1 for r in rows for a in r["actions"] if a.get("enqueued"))}


def recorded_diagnoses(db, day: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        return [dict(p or {}) for (p,) in s.execute(
            select(OperatingReading.payload).where(
                OperatingReading.kind == DIAG_KIND,
                OperatingReading.period_key.like(f"{day}:%"))
            .order_by(OperatingReading.id))]


def run(ctx) -> dict:
    """The `ops.daily_ledger` job: compute, record the ledger row, diagnose and act."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    now = datetime.now(timezone.utc)
    led = ledger(ctx.db, now=now)
    with ctx.db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == LEDGER_KIND, OperatingReading.period_key == led["today"]))
        if row is None:
            s.add(OperatingReading(kind=LEDGER_KIND, period_key=led["today"], payload=led,
                                   at=now))
        else:
            row.payload = led
    diag = diagnose(ctx.db, ctx.queue, now=now, led=led)
    return {"recorded": led["today"], "zero_stages": diag["zero_stages"],
            "diagnosed": len(diag["diagnosed"]), "actions_taken": diag["actions_taken"],
            "ecrs": sum(1 for r in diag["diagnosed"] for e in r["ecrs"] if not e.get("deduped")),
            "ecrs_deduped": sum(1 for r in diag["diagnosed"] for e in r["ecrs"]
                                if e.get("deduped"))}


# ---- projections ------------------------------------------------------------------------

# The Daily panel's rows: (metric, label, pill mode). "invert": bad when high; "neutral":
# neither good nor bad (spend). Served with the panel so the shell bundle stays small.
PANEL_ROWS = (
    ("scans_succeeded", "Competitor scans", None), ("concepts_created", "Concepts created", None),
    ("concepts_approved", "Concepts admitted by intake", None),
    ("concepts_admitted", "Concepts admitted to engineering", None),
    ("concepts_held", "Concepts held", None), ("products_started", "Products started", None),
    ("certifications", "Certified", None), ("pdfs_us", "US PDFs", None),
    ("pdfs_uk", "UK PDFs", None), ("images_generated", "Images generated", None),
    ("images_recovered", "Images recovered", None), ("images_verified", "Images verified", None),
    ("galleries_completed", "Galleries completed", None),
    ("listing_packages", "Listing packages", None), ("etsy_drafts", "Etsy drafts", None),
    ("etsy_live", "Live on Etsy", None), ("lessons_learned", "Lessons learned", None),
    ("lessons_applied", "Lessons applied", None), ("failures", "Failures", "invert"),
    ("dead_letters", "Dead letters", "invert"), ("spend_cad", "Spend (CA$)", "neutral"),
)


def panel(db, *, now: datetime | None = None) -> dict:
    """The owner's Daily panel: the live ledger and today's recorded diagnoses. Read-only."""
    now = _aware(now) or datetime.now(timezone.utc)
    led = ledger(db, now=now)
    try:
        diag = recorded_diagnoses(db, led["today"])
    except Exception as exc:  # noqa: BLE001
        diag = {"error_class": type(exc).__name__}
    preview = diagnose(db, None, now=now, act=False, led=led)["diagnosed"]
    return {"tab": "DAILY", "read_only": True, "ledger": led, "diagnoses": diag,
            "live_zero_stages": preview, "stage_readings": stage_readings(led, now=now),
            "rows": [list(r) for r in PANEL_ROWS],
            "rule": {"expected_min": EXPECTED_MIN, "far_below": FAR_BELOW,
                     "min_hours_into_day": MIN_HOURS_INTO_DAY}}


def readback(db, *, now: datetime) -> dict:
    """The readback section: counts only. Spend amounts, ids and reason text are withheld."""
    led = ledger(db, now=now)
    metrics = {}
    for k, m in led["metrics"].items():
        if k == "spend_cad":
            metrics["spend_recorded"] = {"days": {d: (v if v == UNKNOWN else bool(v))
                                                  for d, v in m["days"].items()}}
            continue
        metrics[k] = {"days": m["days"], **({"error_class": m["error_class"]}
                                           if m.get("error_class") else {})}
    shops = led["shops"]
    if isinstance(shops, list):
        shops = [{k: r.get(k) for k in ("owner_order", "role", "alias", "registered",
                                        "attempted", "succeeded")} for r in shops]
    return {"readable": True, "days": led["days"], "observed_from": led["observed_from"],
            "metrics": metrics, "shops": shops,
            "zero_stages_today": [z["stage"] for z in zero_stages(led, now=now)],
            "stage_status_today": {r["stage"]: r["status"]
                                   for r in stage_readings(led, now=now)}}
