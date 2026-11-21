"""Research M2 (review 6954809399): a watchlist gap's research question answered from evidence
this system already recorded, so gap -> research -> fact -> proposal -> concept_intake runs
unattended.

The question `watchlist._research_question` opens is "is buyer demand in this arena durable
across the watchlist shops, or a passing trend?". Nothing answered it: the Research Agent
writes only `unresolved` findings and, with no internal hit for a pod name, stops the task;
no fetch covers Etsy. The evidence that bears on it is the daily structured comparison
(`intel.watchlist_compare` readings), which records, per day, the arenas that at least
`MIN_SHOPS_FOR_ARENA` uncovered watchlist shops each stock with at least
`MIN_LISTINGS_FOR_ARENA` listings.

Review H1/H2 (eng/r5-research-2): the comparison counts only shops with a FRESH successful
read and only listings that are not withdrawn; each validated arena carries, per shop, the
read's timestamp and the listing ids it rests on. Durability is the number of distinct
observation dates per shop (re-reading the same stored rows on a day with no scan adds
nothing). Until at least `MIN_SHOPS_FOR_ARENA` shops each reach `DURABLE_DAYS` dates the task
stays OPEN, refreshed in place with its progress -- no `low` answer is written for concept
intake to refuse. An arena the latest comparison grades UNKNOWN (a stale/withdrawn majority)
is never a fact.

What an answer writes, and nothing more:

* two `internal` sources read on the latest day: that day's comparison (citing each shop's
  observation time) and the run of readings in the window (citing each shop's dates);
* a `fact`: N uncovered watchlist shops each had at least `MIN_LISTINGS_FOR_ARENA` live
  listings in the arena in fresh reads -- per shop, the read's timestamp and listing ids;
* a `fact`: at least `MIN_SHOPS_FOR_ARENA` shops each corroborated it on K distinct
  observation dates in the last `DURABILITY_WINDOW_DAYS` days, naming the dates;
* an `unresolved` finding for what the readings cannot show: whether the listings sell
  (no per-listing sales are recorded), so demand at the sales level stays UNKNOWN;
* the answer, with confidence `medium` (it clears concept intake's evidence floor).

Listing ids are identifiers; no competitor title, URL, tag or listing text is read or
written: only the comparison's own pod names, shop aliases, counts, ids and dates. A task that is not OPEN is never touched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DURABILITY_WINDOW_DAYS = 14
DURABLE_DAYS = 3
ACTION = "research.answered_from_watchlist"
# Review LOW (eng/r5-research-2): the daily comparison refreshes this task in place. While it
# does (progress noted within REFRESHED_WITHIN), the Research Agent's sweep leaves it alone --
# it would otherwise find no internal record naming the pod and stop the question the
# comparison is still answering, so a new task would open the next day.
ANSWERED_BY = "intel.watchlist_compare"
REFRESHED_WITHIN = timedelta(hours=48)


def refreshed_by_comparison(detail: dict, now: datetime) -> bool:
    if (detail or {}).get("answered_by") != ANSWERED_BY:
        return False
    try:
        at = datetime.fromisoformat(str(((detail or {}).get("watchlist_progress") or {})
                                        .get("at")))
    except ValueError:
        return False
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return now - at <= REFRESHED_WITHIN


def _readings(db, kind: str, *, until: date) -> list[tuple[str, dict]]:
    """(day, payload) of every reading of `kind` in the window ending `until`, newest first."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    since = (until - timedelta(days=DURABILITY_WINDOW_DAYS - 1)).isoformat()
    with db.session() as s:
        rows = list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == kind, OperatingReading.period_key >= since,
            OperatingReading.period_key <= until.isoformat()).order_by(
            OperatingReading.period_key.desc())))
        return [(r.period_key, dict(r.payload or {})) for r in rows]


def _entry(payload: dict, pod: str) -> dict | None:
    # ENG-SUPPLY-FEED: an arena we already sell in is corroborated by the same rules and
    # recorded under `demand_arenas`; it is the same kind of observation evidence.
    for a in (payload.get("validated_arenas") or []) + (payload.get("demand_arenas") or []):
        if a.get("pod") == pod:
            return a
    return None


def _unknown(payload: dict, pod: str) -> dict | None:
    for a in ((payload.get("unknown_arenas") or [])
              + (payload.get("demand_unknown_arenas") or [])):
        if a.get("pod") == pod:
            return a
    return None


def _fresh_observations(entry: dict, now: datetime) -> list[dict]:
    """The entry's per-shop observations that are fresh at `now` and name their listings.
    A reading written before review H2 carries none: it is not evidence of anything."""
    from .watchlist import MIN_LISTINGS_FOR_ARENA, STALE_AFTER

    out = []
    for o in entry.get("observations") or []:
        try:
            at = datetime.fromisoformat(str(o.get("observed_at")))
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        ids = [str(x) for x in o.get("listing_ids") or []]
        if now - at <= STALE_AFTER and len(ids) >= MIN_LISTINGS_FOR_ARENA:
            out.append({"alias": str(o.get("alias")), "observed_at": at.isoformat(),
                        "listing_ids": ids, "live_listings": int(o.get("live_listings")
                                                                 or len(ids))})
    return sorted(out, key=lambda o: o["alias"])


def durability(readings: list[tuple[str, dict]], pod: str) -> tuple[int, dict[str, list[str]]]:
    """Review H2: durability is independent observations, not comparison runs. Per shop, the
    distinct dates of the successful reads that corroborated the arena; the arena's durable
    days are what at least MIN_SHOPS_FOR_ARENA shops each reached. Re-reading the same stored
    rows on a day with no new scan adds nothing."""
    from .watchlist import MIN_SHOPS_FOR_ARENA

    by_shop: dict[str, set[str]] = {}
    for _day, payload in readings:
        if _unknown(payload, pod):
            continue
        e = _entry(payload, pod)
        for o in (e or {}).get("observations") or []:
            if o.get("observed_at") and o.get("listing_ids"):
                by_shop.setdefault(str(o["alias"]), set()).add(str(o["observed_at"])[:10])
    counts = sorted((len(v) for v in by_shop.values()), reverse=True)
    days = counts[MIN_SHOPS_FOR_ARENA - 1] if len(counts) >= MIN_SHOPS_FOR_ARENA else 0
    return days, {k: sorted(v) for k, v in sorted(by_shop.items())}


def _ids(ids: list[str], n: int = 10) -> str:
    return ", ".join(ids[:n]) + (f" (+{len(ids) - n} more)" if len(ids) > n else "")


def _note_progress(db, task_id: int, progress: dict) -> None:
    """The task stays OPEN and is refreshed in place: the latest evidence count is kept on it,
    so one open question per gap carries the running tally (no new task, no low answer)."""
    from sqlalchemy.orm.attributes import flag_modified

    from . import research

    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        d = dict(t.detail or {})
        d["watchlist_progress"] = progress
        d["answered_by"] = ANSWERED_BY
        t.detail = d
        flag_modified(t, "detail")


def answer(db, *, gap_id: int, task_id: int, pod: str, now: datetime | None = None,
           audit=None) -> dict:
    """Answer the gap's OPEN research task from the recorded comparisons, or say why not.

    Review H1/H2 (eng/r5-research-2): the task is answered only when the evidence is durable
    (confidence `medium`, which clears concept intake's own evidence floor). Until then it
    stays OPEN with its progress noted -- never a `low` answer that a proposal could be
    refused on and that expires into a new task the next day."""
    from . import research
    from .watchlist import COMPARE_READING, MIN_LISTINGS_FOR_ARENA, MIN_SHOPS_FOR_ARENA

    now = now or datetime.now(timezone.utc)
    research._ensure(db)
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        state = t.state if t is not None else None
    if state != research.OPEN:
        return {"answered": False, "task": task_id, "why": f"task is {state}, not open"}

    def not_yet(why: str, **extra) -> dict:
        _note_progress(db, task_id, {"at": now.isoformat(), "why": why, **extra})
        return {"answered": False, "task": task_id, "why": why, **extra}

    readings = _readings(db, COMPARE_READING, until=now.date())
    if not readings:
        return not_yet(f"no recorded comparison in the last {DURABILITY_WINDOW_DAYS} days")
    latest_day, latest = readings[0]
    unknown = _unknown(latest, pod)
    if unknown:
        return not_yet(f"the {pod} arena is UNKNOWN in the {latest_day} comparison: "
                       f"{unknown.get('why')}")
    entry = _entry(latest, pod)
    if entry is None:
        return not_yet(f"the {latest_day} comparison does not corroborate the {pod} arena")
    obs = _fresh_observations(entry, now)
    if len(obs) < MIN_SHOPS_FOR_ARENA:
        return not_yet(f"the {latest_day} comparison holds {len(obs)} fresh per-shop "
                       f"observation(s) with listing ids for the {pod} arena; "
                       f"{MIN_SHOPS_FOR_ARENA} are needed")
    days, dates = durability(readings, pod)
    if days < DURABLE_DAYS:
        return not_yet(f"not yet durable: {days} of {DURABLE_DAYS} distinct observation "
                       f"days per shop", days=days, observation_dates=dates)

    read_on = date.fromisoformat(latest_day)
    per_shop = "; ".join(f"{o['alias']} observed {o['observed_at']} (listing ids "
                         f"{_ids(o['listing_ids'])})" for o in obs)
    s_latest = "S%d" % research.add_source(
        db, task_id, source=COMPARE_READING,
        citation=(f"operating_reading:{COMPARE_READING}:{latest_day}#validated_arenas/{pod} "
                  f"[{'; '.join(o['alias'] + '@' + o['observed_at'] for o in obs)}]"),
        retrieval="internal", read_on=read_on)
    first_day = readings[-1][0]
    s_series = "S%d" % research.add_source(
        db, task_id, source=COMPARE_READING,
        citation=(f"operating_reading:{COMPARE_READING}:{first_day}..{latest_day}"
                  f"#validated_arenas/{pod}/observations (observation dates: "
                  f"{'; '.join(a + ': ' + ', '.join(d) for a, d in dates.items())})"),
        retrieval="internal", read_on=read_on)
    # ENG-SUPPLY-FEED: an arena we already sell in says so; it is never called uncovered.
    shops_word = "watchlist shops" if entry.get("covered") else "uncovered watchlist shops"
    where = (f"the {pod} arena (one we already sell in)" if entry.get("covered")
             else f"the {pod} arena")
    f_now = research.add_finding(
        db, task_id, claim_class="fact", rests_on=[s_latest], confidence="high",
        statement=(f"In fresh official-API observations, {len(obs)} {shops_word} "
                   f"each had at least {MIN_LISTINGS_FOR_ARENA} live (not withdrawn) listings "
                   f"in {where}: {per_shop}."))
    f_durable = research.add_finding(
        db, task_id, claim_class="fact", rests_on=[s_series], confidence="high",
        statement=(f"At least {MIN_SHOPS_FOR_ARENA} {shops_word} each "
                   f"corroborated the {pod} arena on {days} or more distinct observation dates "
                   f"in the last {DURABILITY_WINDOW_DAYS} days: "
                   f"{'; '.join(a + ': ' + ', '.join(d) for a, d in dates.items())}."))
    f_unknown = research.add_finding(
        db, task_id, claim_class="unresolved",
        statement=(f"Whether the {pod} listings sell is UNKNOWN: the comparison records "
                   f"listing counts and dates, not per-listing sales."))
    confidence = "medium"
    out = research.answer(
        db, task_id, outcome="durable", confidence=confidence, now=now,
        effect={"kind": "constraint_established",
                "statement": (f"{pod}: corroborated on {days} distinct observation dates by "
                              f"{MIN_SHOPS_FOR_ARENA}+ shops ({f_now}, {f_durable})")},
        conclusion={"alternatives": [], "constraints": [
                        f"corroborated by {len(obs)} {shops_word} in fresh "
                        f"observations read {latest_day}",
                        f"corroborated on {days} distinct observation dates"],
                    "unresolved": [f_unknown], "next_test": {},
                    "applicability": {"pod": pod, "gap": gap_id}})
    _note_progress(db, task_id, {"at": now.isoformat(), "answered": True, "days": days,
                                 "observation_dates": dates, "observations": obs})
    detail = {"gap": gap_id, "task": task_id, "pod": pod, "days": days,
              "reading_day": latest_day,
              "confidence": confidence, "findings": [f_now, f_durable, f_unknown],
              "observations": [{k: o[k] for k in ("alias", "observed_at", "live_listings")}
                               for o in obs]}
    if audit is not None:
        audit(ACTION, artifact=f"research_task:{task_id}", detail=detail)
    return {"answered": True, **detail, "result": out}


# ---- Review H3 (eng/r5-research-3): an approved concept's support is renewed, not lapsed --
RENEWED = "research.support_renewed"


def fact_refs(findings: list[dict]) -> list[str]:
    """The fact-grade findings of a task and the sources they rest on -- what a proposal (or
    a renewal of its support) cites, so `intake.research_evidence` resolves every ref."""
    facts = [f for f in findings or [] if f.get("claim_class") == "fact" and f.get("ref")]
    refs = [f["ref"] for f in facts]
    for f in facts:
        refs += [r for r in f.get("rests_on") or [] if r not in refs]
    return refs


RENEW_AHEAD = timedelta(hours=12)
RENEWAL_KEEP = 2
CLOSED_WITH_WITHDRAWAL = "research.renewal_closed"


def _retire(row, by: int, now: datetime) -> None:
    """A superseded renewal answer: EXPIRED (it no longer supports anything), so
    `research.expire_due` does not later re-open its question as a new OPEN task."""
    from sqlalchemy.orm.attributes import flag_modified

    from . import research

    if row is None or row.state != research.ANSWERED:
        return
    row.state = research.EXPIRED
    row.detail = {**(row.detail or {}), "superseded_by": by,
                  "superseded_at": now.isoformat()}
    flag_modified(row, "detail")


def _gap_of(row) -> int | None:
    trigger = str(getattr(row, "trigger", "") or "")
    if not trigger.startswith("watchlist_gap:"):
        return None
    head = trigger.split(":", 1)[1].split("#", 1)[0]
    return int(head) if head.isdigit() else None


def close_renewals(db, *, concept_task_id: int, why: str, now: datetime | None = None,
                   keep_for: set[int] | frozenset = frozenset(), audit=None) -> list[int]:
    """Review LOW (eng/r5-research-2): when a watchlist concept is withdrawn, the OPEN tasks
    that were renewing its support (`watchlist_gap:<gap>#renew:...`, or the gap question
    re-opened by `research.expire_due`, `watchlist_gap:<gap>#after:...`) are closed with it:
    EXPIRED, with the withdrawal recorded on the task. Not while another approved concept
    (`keep_for`: its concept task ids) rests on the same gap. Fresh evidence later opens a
    new question (`watchlist._research_question`), so nothing is lost."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from . import research

    research._ensure(db)
    now = now or datetime.now(timezone.utc)
    closed: list[int] = []
    with db.session() as s:
        gid = _gap_of(s.get(research.ResearchTask, int(concept_task_id)))
        if gid is None:
            return []
        if any(_gap_of(s.get(research.ResearchTask, int(k))) == gid
               for k in keep_for if int(k) != int(concept_task_id)):
            return []
        prefix = f"watchlist_gap:{gid}#"
        for row in s.scalars(select(research.ResearchTask).where(
                research.ResearchTask.state == research.OPEN,
                research.ResearchTask.trigger.startswith(prefix))):
            row.state = research.EXPIRED
            row.detail = {**(row.detail or {}), "closed": {
                "why": why, "at": now.isoformat(), "concept_task": int(concept_task_id)}}
            flag_modified(row, "detail")
            closed.append(row.id)
    if closed and audit is not None:
        audit(CLOSED_WITH_WITHDRAWAL, artifact=f"research_task:{concept_task_id}",
              detail={"gap": gid, "closed": closed, "why": why})
    return closed


def renew_support(db, *, gap_id: int, concept_task_id: int, pod: str, now: datetime,
                  open_task, audit=None, expiring_within: timedelta | None = None) -> dict:
    """Renew the research behind an APPROVED concept from today's observations.

    A `market_radar` answer is fresh for one day, so the answer a concept was approved on
    expires the next day and intake would withdraw the concept although the evidence is
    still there. Each daily comparison therefore re-asks the gap's question (a new task,
    reopened for new evidence) and answers it with `answer` -- the same rules: fresh per-shop
    observations in the latest reading and durability. Only when that new answer is written
    is it recorded on the concept's task (`detail.renewed_support`: the task and the refs it
    cites), which intake then judges as the concept's support. When today's evidence is
    stale, withdrawn or not durable, nothing is renewed: the old answer expires and intake
    withdraws the concept. Nothing here keeps a concept alive on old evidence.

    Two callers: the daily comparison (renews unless the support already rests on today's
    reading) and the 6-hourly concept-intake job with `expiring_within` (renews only when the
    support expires within that window), so a late comparison cannot let the support lapse
    between two intake passes."""
    from sqlalchemy.orm.attributes import flag_modified

    from . import research

    research._ensure(db)
    with db.session() as s:
        c = s.get(research.ResearchTask, int(concept_task_id))
        renewed = dict((c.detail or {}).get("renewed_support") or {})
        head_id = int(renewed.get("task") or concept_task_id)
        head = s.get(research.ResearchTask, head_id)
        head_live = head is not None and head.state == research.ANSWERED
        head_expires = research._aware(head.expires_on) if head_live else None
        head_answered = research._aware(head.answered_at) if head_live else None
        head_day = str(renewed.get("reading_day") or "") if renewed else (
            head_answered.date().isoformat() if head_answered else "")
    if expiring_within is not None:
        if head_live and (head_expires is None or head_expires - now > expiring_within):
            return {"answered": False, "task": head_id, "renewed": False,
                    "why": "the support does not expire within "
                           f"{int(expiring_within.total_seconds() // 3600)} h"}
    elif head_live and head_day >= now.date().isoformat():
        return {"answered": False, "task": head_id, "renewed": False,
                "why": f"the support already rests on the {head_day} reading"}
    task = open_task(f"watchlist_gap:{gap_id}#renew:{head_id}",
                     f"the {now.date().isoformat()} watchlist comparison re-observes the "
                     f"{pod} arena; renews the support of the concept approved on research "
                     f"task {concept_task_id}")
    if task is None:
        return {"answered": False, "task": None, "renewed": False,
                "why": "no research task could be opened to renew the support"}
    out = answer(db, gap_id=gap_id, task_id=int(task), pod=pod, now=now, audit=audit)
    if not out.get("answered"):
        return {**out, "renewed": False}
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task))
        refs = fact_refs(list(t.findings or []))
        c = s.get(research.ResearchTask, int(concept_task_id))
        d = dict(c.detail or {})
        chain = list((d.get("renewed_support") or {}).get("chain") or []) + [int(task)]
        # Review LOW (eng/r5-research-2): a renewal supersedes the one before it. Only the
        # last RENEWAL_KEEP renewals are kept (the head that supports the concept and the one
        # it replaced, for traceability); older ones are deleted, so a concept approved for a
        # year holds two renewal tasks, not 365. Every renewal stays in the audit log
        # (`research.support_renewed`: the task, its refs and the one it replaced).
        kept, pruned = chain[-RENEWAL_KEEP:], chain[:-RENEWAL_KEEP]
        d["renewed_support"] = {"task": int(task), "refs": refs, "at": now.isoformat(),
                                "reading_day": out.get("reading_day"), "chain": kept,
                                "pruned": int((d.get("renewed_support") or {})
                                              .get("pruned") or 0) + len(pruned)}
        c.detail = d
        flag_modified(c, "detail")
        for old_id in kept[:-1]:
            _retire(s.get(research.ResearchTask, old_id), int(task), now)
        for old_id in pruned:
            old = s.get(research.ResearchTask, old_id)
            if old is not None and old.id not in (int(concept_task_id), int(task)):
                s.delete(old)
    if audit is not None:
        audit(RENEWED, artifact=f"research_task:{concept_task_id}",
              detail={"gap": gap_id, "pod": pod, "renewed_by": int(task), "refs": refs,
                      "previous": head_id})
    return {**out, "renewed": True, "concept_task": int(concept_task_id)}
