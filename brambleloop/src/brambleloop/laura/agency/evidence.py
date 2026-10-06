"""Evidence readers for Talk to Laura: durable company state -> source-linked facts.

Every reader returns a *section*: `{"key", "title", "status", "facts", "reason", "sources"}`.
A fact is `{"statement", "source", "as_of", "link", "basis"}`; `source` is the table row or
provider the statement was read from, `link` the Command Center route that shows it. Readers
never invent: a provider that is absent, failing or empty gives an UNKNOWN section with the
reason, and an UNKNOWN money figure is reported as UNKNOWN, never as CA$0.00 (F-898).

Sources read (all through existing interfaces, tolerating absence):
  autonomy.status.summary / timeline (departments, overnight missions)  -- lane D base
  autonomy.memory missions (what the departments are working on)
  brambleloop.laura.executive (Laura's priorities/history)              -- lane D, optional
  finance.accounting.dashboard via command_center.tabs.money_section    -- accountant
  learn.improvement_status, lessons, improvements, experiments          -- Learn
  seo.status, growth.ads_readiness, store_foundation.preview            -- store/growth
  brambleloop.visual.rnd.status.summary                                 -- lane H, optional
  approvals inbox, incidents, products                                  -- owner queue
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

UNKNOWN = "UNKNOWN"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).replace(
            microsecond=0).isoformat()
    return str(v)


# Where in the Command Center a source can be seen. Row refs with a drill view go to it.
_DRILL = ("jobs:", "incidents:", "audit_log:", "agents:")
_LINKS = (
    (("owner_actions", "approval", "build2.executor", "ops.publication_authority"),
     "#/approvals"),
    (("finance", "ledger", "cost_entries", "revenue", "orders", "accounting"), "#/money"),
    (("store_foundation", "products", "pattern_versions", "listings", "seo"), "#/store"),
    (("lessons", "improvement", "experiments", "learn", "visual.rnd", "company_memory",
      "autonomy.status", "laura.executive"), "#/learn"),
    (("growth", "ads"), "#/insights"),
    (("company_timeline", "timeline"), "#/timeline"),
)


def link_for(source: str) -> str:
    s = str(source or "")
    if s.startswith(_DRILL):
        return f"#/drill/{s}"
    low = s.lower()
    for keys, route in _LINKS:
        if any(k in low for k in keys):
            return route
    return f"#/drill/{s}"


def fact(statement: str, source: str, *, as_of=None, basis: str = "measured") -> dict:
    return {"statement": str(statement)[:400], "source": str(source)[:200],
            "as_of": _iso(as_of) or _iso(_now()), "link": link_for(source), "basis": basis}


def section(key: str, title: str, facts: list[dict], *, status: str | None = None,
            reason: str | None = None, sources: list | None = None, **extra) -> dict:
    st = status or ("OK" if facts else UNKNOWN)
    if st == UNKNOWN and not reason:
        reason = "no durable evidence recorded"
    srcs = list(dict.fromkeys([f["source"] for f in facts] + list(sources or [])))
    return {"key": key, "title": title, "status": st, "facts": facts, "reason": reason,
            "sources": srcs, **extra}


def unknown_section(key: str, title: str, reason: str, sources: list | None = None) -> dict:
    return section(key, title, [], status=UNKNOWN, reason=reason, sources=sources)


def _guard(key: str, title: str, fn) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - an unreadable source is UNKNOWN, not a crash
        return unknown_section(key, title, f"could not be read: {type(exc).__name__}")


def _provider(key: str, db) -> dict:
    from ...app.command_center import providers

    return providers.call(key, db)


def _optional(module: str, fn_name: str, db, *args, **kwargs):
    """(value, why) from a peer lane's optional provider; ImportError -> 'not built'."""
    from ...app.command_center import providers

    try:
        mod = importlib.import_module(module)
    except ImportError:
        return None, "not built"
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        return None, "not built"
    try:
        return providers._invoke(fn, db, *args, **kwargs), None
    except Exception as exc:  # noqa: BLE001
        return None, f"provider failed: {type(exc).__name__}"


# ---- the company: departments, overnight work, current work ----------------------------


def departments(db) -> dict:
    title = "Departments (autonomy status)"

    def read():
        a = _provider("autonomy", db)
        src = a.get("provider") or "brambleloop.autonomy.status.summary"
        if a["status"] == UNKNOWN:
            return unknown_section("departments", title, a.get("reason") or "unknown", [src])
        facts = []
        orch = a.get("orchestrator") or {}
        if orch.get("last_tick"):
            facts.append(fact(f"the COO orchestrator last ran at {orch['last_tick']}"
                              + (" and is STALE" if orch.get("stale") else ""), src,
                              as_of=orch["last_tick"]))
        for d in a["items"]:
            if not isinstance(d, dict) or not d.get("department"):
                continue
            bits = [f"{d.get('name') or d['department']}: {d.get('status', UNKNOWN)}"]
            if d.get("completed_24h") is not None:
                bits.append(f"{d['completed_24h']} job(s) completed in 24 h "
                            f"({d.get('useful_24h', 0)} useful)")
            if d.get("open_jobs"):
                bits.append(f"{d['open_jobs']} open")
            bl = [b for b in d.get("blockers") or [] if isinstance(b, dict)]
            if bl:
                bits.append("blocked by " + "; ".join(
                    str(b.get("reason") or b.get("what") or b.get("gate") or b.get("kind"))[:80]
                    for b in bl[:2]))
            facts.append(fact(", ".join(bits), f"{src}[{d['department']}]",
                              as_of=a.get("as_of")))
        return section("departments", title, facts, status=a["status"],
                       reason=a.get("reason"), sources=a.get("sources"),
                       overnight=a.get("overnight"))

    return _guard("departments", title, read)


def overnight(db, hours: float = 12) -> dict:
    title = f"What the company did (last {hours:g} h)"

    def read():
        from ...app.command_center import readers

        since = _now() - timedelta(hours=hours)
        facts = []
        jw = readers.jobs_window(db, hours)
        if jw.get("status") == "OK" and (jw.get("completed") or jw.get("failed")):
            facts.append(fact(f"{jw.get('completed', 0)} job(s) completed and "
                              f"{jw.get('failed', 0)} failed in the last {hours:g} h", "jobs"))
            for it in (jw.get("items") or [])[:6]:
                facts.append(fact(f"{it['agent']} completed {it['completed']} job(s)", "jobs"))
        try:
            from ...autonomy import memory

            missions = memory.recall(db, kind="mission", since=since, limit=200)
        except Exception:  # noqa: BLE001
            missions = []
        if missions:
            by: dict[str, int] = {}
            for m in missions:
                by[m.get("state") or "?"] = by.get(m.get("state") or "?", 0) + 1
            facts.append(fact(f"{len(missions)} department mission(s) touched: "
                              + ", ".join(f"{v} {k}" for k, v in sorted(by.items())),
                              "company_memory (kind=mission)"))
            for m in [m for m in missions if m.get("state") == "useful"][:5]:
                facts.append(fact(f"{m.get('department')}: {m.get('subject')} (useful)",
                                  f"company_memory:{m.get('key')}", as_of=m.get("updated_at")))
        tl = _provider_raw_timeline(db, since)
        for e in tl[:8]:
            facts.append(fact(f"{e.get('kind')}: {e.get('summary')}",
                              (e.get("refs") or [e.get("source") or "company_timeline"])[0],
                              as_of=e.get("at")))
        return section("overnight", title, facts,
                       reason=None if facts else
                       f"no completed job, mission or timeline event in the last {hours:g} h")

    return _guard("overnight", title, read)


def _provider_raw_timeline(db, since: datetime) -> list[dict]:
    from ...app.command_center import providers

    val, _why = providers.call_raw("timeline", db, limit=40)
    items = val.get("items") if isinstance(val, dict) else val
    out = []
    for e in items or []:
        if not isinstance(e, dict):
            continue
        try:
            at = datetime.fromisoformat(str(e.get("at")))
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        if at >= since:
            out.append(e)
    return out


def working_on(db) -> dict:
    title = "Work in progress"

    def read():
        from ...autonomy import memory

        facts = []
        for m in memory.recall(db, kind="mission", state="queued", limit=15):
            facts.append(fact(f"{m.get('department')}: {m.get('subject')}",
                              f"company_memory:{m.get('key')}", as_of=m.get("updated_at")))
        for a in memory.recall(db, kind="approval", state="awaiting_owner", limit=5):
            facts.append(fact(f"waiting on you ({a.get('department')}): {a.get('subject')}",
                              f"company_memory:{a.get('key')}", as_of=a.get("updated_at")))
        from sqlalchemy import func, select

        from ...core.models import Job, JobStatus

        with db.session() as s:
            rows = list(s.execute(select(Job.job_type, Job.status, func.count()).where(
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
                .group_by(Job.job_type, Job.status).order_by(func.count().desc()).limit(8)))
        for jt, st, n in rows:
            facts.append(fact(f"{getattr(st, 'value', st)}: {jt} x{int(n)}", "jobs"))
        return section("working_on", title, facts,
                       reason=None if facts else "no queued mission or open job is recorded")

    return _guard("working_on", title, read)


def executive(db) -> dict:
    """Laura's own executive priorities and history (lane D `laura.executive`), if merged."""
    title = "My executive priorities"

    def read():
        facts = []
        why_all = []
        for fn, label in (("priorities", "priority"), ("summary", "summary"),
                          ("history", "history")):
            val, why = _optional("brambleloop.laura.executive", fn, db)
            if why:
                why_all.append(f"{fn}: {why}")
                continue
            items = val.get("items") if isinstance(val, dict) else val
            for it in (items or [])[:8]:
                if isinstance(it, dict):
                    text = (it.get("statement") or it.get("title") or it.get("summary")
                            or it.get("subject") or it.get("priority") or it.get("what"))
                    if not text:
                        continue
                    src = (it.get("source") or (it.get("sources") or [None])[0]
                           or f"laura.executive.{fn}")
                    facts.append(fact(f"{label}: {text}", str(src),
                                      as_of=it.get("at") or it.get("as_of")))
                elif isinstance(it, str):
                    facts.append(fact(f"{label}: {it}", f"laura.executive.{fn}"))
            if facts:
                break
        return section("executive", title, facts,
                       reason=None if facts else ("laura.executive " +
                                                  ("; ".join(why_all) or "returned nothing")))

    return _guard("executive", title, read)


# ---- money -----------------------------------------------------------------------------


def money(db) -> dict:
    title = "Money (Accountant)"

    def read():
        from ...app.command_center import tabs

        m = tabs.money_section(db)
        acct = m.get("accounting") or {}
        facts = []
        src = acct.get("provider") or "brambleloop.finance.accounting.dashboard.summary"
        for it in acct.get("items") or []:
            if not isinstance(it, dict) or "label" not in it:
                continue
            disp = it.get("display") or it.get("state") or UNKNOWN
            basis = it.get("basis") or "unknown"
            facts.append(fact(f"{it['label']}: {disp}", (it.get("sources") or [src])[0],
                              basis=basis if basis in ("measured", "estimated", "modelled",
                                                       "derived") else "unknown"))
        rev = m.get("revenue") or {}
        facts.append(fact(f"reconciled revenue: {rev.get('display') or UNKNOWN}"
                          + (f" ({rev.get('why')})" if rev.get("why") and
                             rev.get("state") != "MEASURED" else ""),
                          (rev.get("sources") or ["orders"])[0],
                          basis="measured" if rev.get("state") == "MEASURED" else "unknown"))
        prof = m.get("profit") or {}
        facts.append(fact(f"profit: {prof.get('display') or UNKNOWN}"
                          + (f" ({prof.get('why')})" if prof.get("why") and
                             prof.get("state") not in ("MEASURED",) else ""),
                          (prof.get("sources") or [src])[0],
                          basis=str(prof.get("basis") or "unknown")))
        spent = m.get("recorded_spend") or {}
        if spent.get("display"):
            facts.append(fact(f"recorded spend: {spent['display']}",
                              (spent.get("sources") or ["cost_entries"])[0],
                              basis=str(spent.get("basis") or "measured")))
        warn = (m.get("source_health") or {}).get("warning")
        if warn:
            facts.append(fact(warn, "finance.accounting.health", basis="measured"))
        measured = [f for f in facts if f["basis"] == "measured" and UNKNOWN not in
                    f["statement"]]
        status = "OK" if measured else UNKNOWN
        return section("money", title, facts, status=status if facts else UNKNOWN,
                       reason=None if measured else (m.get("reason") or
                                                     "no measured money figure: revenue "
                                                     "and profit are UNKNOWN, not CA$0.00"),
                       revenue_state=rev.get("state"), profit_state=prof.get("state"))

    return _guard("money", title, read)


# ---- store -----------------------------------------------------------------------------


def store(db) -> dict:
    title = "The store (Store Foundation)"

    def read():
        sf = _provider("store_foundation", db)
        src = sf.get("provider") or "brambleloop.store_foundation.preview.summary"
        if sf["status"] == UNKNOWN and not sf.get("items"):
            return unknown_section("store", title, sf.get("reason") or "unknown", [src])
        facts = []
        counts = sf.get("counts")
        if isinstance(counts, dict) and counts:
            facts.append(fact("store surfaces: " + ", ".join(
                f"{v} {k}" for k, v in sorted(counts.items())), src, as_of=sf.get("as_of")))
        for it in sf.get("items") or []:
            if not isinstance(it, dict) or not it.get("label"):
                continue
            st = it.get("status") or UNKNOWN
            line = f"{it['label']}: {st}"
            top = [t for t in it.get("top_findings") or [] if t][:1]
            if top and st not in ("READY", "OK", "PASS"):
                line += f" ({str(top[0])[:120]})"
            facts.append(fact(line, str(it.get("source") or src), as_of=sf.get("as_of"),
                              basis=it.get("basis") or "measured"))
        if sf.get("preview_path"):
            facts.append(fact(f"owner store preview: {sf['preview_path']}"
                              + (f" (variants: {', '.join(sf.get('preview_variants') or [])})"
                                 if sf.get("preview_variants") else ""), src))
        return section("store", title, facts, status=sf["status"], reason=sf.get("reason"),
                       sources=sf.get("sources"), preview_path=sf.get("preview_path"))

    return _guard("store", title, read)


def seo(db) -> dict:
    title = "Search (SEO)"

    def read():
        e = _provider("seo", db)
        src = e.get("provider") or "brambleloop.seo.status.summary"
        if e["status"] == UNKNOWN and not e.get("items"):
            return unknown_section("seo", title, e.get("reason") or "unknown", [src])
        facts = []
        for it in (e.get("items") or [])[:6]:
            if isinstance(it, dict) and (it.get("title") or it.get("slug")):
                facts.append(fact(f"{it.get('slug') or ''} {it.get('title') or ''}: "
                                  f"{'ok' if it.get('ok') else 'needs work'}".strip(), src,
                                  as_of=e.get("as_of")))
        if not facts:
            facts.append(fact(f"SEO status {e['status']}"
                              + (f" ({e.get('reason')})" if e.get("reason") else ""), src,
                              as_of=e.get("as_of")))
        return section("seo", title, facts, status=e["status"], reason=e.get("reason"),
                       sources=e.get("sources"))

    return _guard("seo", title, read)


def products(db) -> dict:
    title = "Products"

    def read():
        from ...app.command_center import readers

        p = readers.products(db)
        if p["status"] != "OK":
            return unknown_section("products", title, p.get("reason") or "unknown",
                                   ["products"])
        facts = [fact(f"{p.get('certified', 0)} of {len(p['items'])} product(s) have a "
                      f"certified release; {p.get('on_etsy', 0)} are on Etsy",
                      "products+pattern_versions+listings")]
        for it in p["items"][:12]:
            facts.append(fact(f"{it['slug']}: status {it['status']}, "
                              f"{'certified' if it['certified'] else 'not certified'}"
                              f"{', listing ' + str(it['listing_state']) if it['listing_state'] else ''}",
                              it["sources"][-1] if it.get("sources") else "products"))
        return section("products", title, facts, items=p["items"])

    return _guard("products", title, read)


# ---- discoveries / learning / visual ---------------------------------------------------


def lessons(db, hours: float | None = None) -> dict:
    title = "Lessons"

    def read():
        from sqlalchemy import select

        from ...core.models import Lesson

        q = select(Lesson).order_by(Lesson.id.desc()).limit(10)
        if hours:
            q = q.where(Lesson.at >= _now() - timedelta(hours=hours))
        with db.session() as s:
            rows = [(r.id, r.at, r.subject, r.statement, r.confidence) for r in s.scalars(q)]
        facts = [fact(f"{subj}: {stmt[:240]} ({conf})", f"lessons:{i}", as_of=at)
                 for i, at, subj, stmt, conf in rows]
        return section("lessons", title, facts,
                       reason=None if facts else "no lesson is recorded"
                       + (f" in the last {hours:g} h" if hours else ""))

    return _guard("lessons", title, read)


def improvement(db) -> dict:
    title = "Improvement loops (Learn)"

    def read():
        e = _provider("improvement", db)
        src = e.get("provider") or "brambleloop.learn.improvement_status.summary"
        if e["status"] == UNKNOWN and not e.get("items"):
            return unknown_section("improvement", title, e.get("reason") or "unknown", [src])
        facts = []
        for it in (e.get("items") or [])[:8]:
            if not isinstance(it, dict):
                continue
            text = it.get("title") or it.get("loop") or it.get("why") or it.get("key")
            if text:
                st = it.get("state") or it.get("status")
                facts.append(fact(f"{text}" + (f" ({st})" if st else ""), src,
                                  as_of=e.get("as_of")))
        return section("improvement", title, facts, status=e["status"] if facts else UNKNOWN,
                       reason=e.get("reason") or (None if facts else "no loop reported"),
                       sources=e.get("sources"))

    return _guard("improvement", title, read)


def ads(db) -> dict:
    title = "Growth / ads readiness"

    def read():
        e = _provider("ads", db)
        src = e.get("provider") or "brambleloop.growth.ads_readiness.summary"
        if e["status"] == UNKNOWN and not e.get("items"):
            return unknown_section("ads", title, e.get("reason") or "unknown", [src])
        facts = [fact(f"ads readiness {e['status']}"
                      + (f": {e.get('reason')}" if e.get("reason") else ""), src,
                      as_of=e.get("as_of"))]
        return section("ads", title, facts, status=e["status"], reason=e.get("reason"),
                       sources=e.get("sources"))

    return _guard("ads", title, read)


def visual_rnd(db) -> dict:
    """Lane H's Visual R&D provider (`visual.rnd.status.summary`), if merged."""
    title = "Visual R&D"

    def read():
        from ...app.command_center import providers

        val, why = _optional("brambleloop.visual.rnd.status", "summary", db)
        if why:
            return unknown_section("visual_rnd", title, f"visual.rnd.status {why}",
                                   ["brambleloop.visual.rnd.status.summary"])
        e = providers.validate(val, "brambleloop.visual.rnd.status.summary")
        src = e["provider"]
        if e["status"] == UNKNOWN and not e["items"]:
            return unknown_section("visual_rnd", title, e.get("reason") or "unknown", [src])
        facts = []
        for it in e["items"][:8]:
            if isinstance(it, dict):
                text = (it.get("statement") or it.get("title") or it.get("label")
                        or it.get("summary") or it.get("key"))
                if text:
                    st = it.get("status") or it.get("state")
                    facts.append(fact(f"{text}" + (f" ({st})" if st else ""),
                                      str(it.get("source") or src), as_of=e.get("as_of")))
        if not facts:
            facts.append(fact(f"Visual R&D status {e['status']}"
                              + (f" ({e.get('reason')})" if e.get("reason") else ""), src))
        return section("visual_rnd", title, facts, status=e["status"], reason=e.get("reason"),
                       sources=e.get("sources"))

    return _guard("visual_rnd", title, read)


# ---- what needs the owner --------------------------------------------------------------


def owner_queue(db) -> dict:
    title = "Decisions only you can make"

    def read():
        from ...app.command_center import approvals, readers

        box = approvals.inbox(db)
        facts = []
        for c in box["cards"][:10]:
            facts.append(fact(f"{c['title']}"
                              + (f" -- {c.get('recommendation')}" if c.get("recommendation")
                                 else ""),
                              (c.get("sources") or ["owner_actions"])[-1]))
        inc = readers.incidents(db, limit=10)
        for i in inc.get("items") or []:
            if i.get("halts_publication") or i.get("severity") in ("P0", "P1"):
                facts.append(fact(f"open {i['severity']} incident: {i['summary'][:160]}",
                                  i["source"], as_of=i.get("at")))
        if box["status"] == UNKNOWN and not facts:
            return unknown_section("owner_queue", title, box.get("reason") or "unreadable",
                                   box.get("sources"))
        nothing = not facts
        if nothing:
            facts.append(fact("no owner decision is open and no publication-halting or P0/P1 "
                              "incident is recorded", "build2.executor.approval_inbox"))
        return section("owner_queue", title, facts, status="OK", nothing_open=nothing,
                       reason=None, sources=box.get("sources"), open=box["open"],
                       cards=[{"card_id": c["card_id"], "title": c["title"]}
                              for c in box["cards"][:10]])

    return _guard("owner_queue", title, read)


def phase(db) -> dict:
    title = "Company phase"

    def read():
        from ...core import phase as phase_mod

        ph = phase_mod.resolve(db)
        return section("phase", title, [fact(
            f"the company runs in {str(ph['phase']).upper()}"
            + (" -- nothing is published or spent live" if ph["phase"] == "shadow" else ""),
            "core.phase.resolve (audit_log owner.phase.transition)")])

    return _guard("phase", title, read)
