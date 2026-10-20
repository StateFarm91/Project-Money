"""Ask Company (F-928) without hallucinated answers (F-929).

Deterministic retrieval over durable state. A question is classified into an intent by
keyword rules; each intent has a reader that collects *facts*, each fact carrying the row it
came from (`table:id` or the reader's module path). The answer is assembled only from those
facts. When the readers find no supporting evidence the status is UNKNOWN and the answer says
what is missing -- it never guesses.

No model is called. (A model-written paraphrase could be added later through
`gateway.model_gateway` with spend recording, but it could only rephrase these facts; v1.1
lane C adds no paid API calls.)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

METHOD = "deterministic retrieval over durable state (no model call)"
SUPPORTED = ("why is <product> blocked?", "what is blocking launch?",
             "what did Brambleloop do overnight?", "why did profit fall? / how much revenue?",
             "why does <thing> need my approval?", "what incidents are open?",
             # W4-CLOSE6 (F-664): the three the master plan names that had no reader.
             "what are the agents doing?", "what did we spend?", "what opportunities are open?")


def _fact(statement: str, source: str, as_of: str | None = None) -> dict:
    return {"statement": statement, "source": source,
            "as_of": as_of or datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


def _result(question, intent, facts, answer, *, status=None, next_action=None) -> dict:
    status = status or ("ANSWERED" if facts else "UNKNOWN")
    if status == "UNKNOWN" and not answer.startswith("UNKNOWN"):
        answer = "UNKNOWN: " + answer
    return {"question": question, "intent": intent, "status": status, "answer": answer,
            "facts": facts, "next_action": next_action,
            "sources": sorted({f["source"] for f in facts}), "method": METHOD,
            # W4-CCGAP: when this answer was read from durable state.
            "answered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


# ---- intent classification -------------------------------------------------------

_PRODUCT_PATTERNS = (
    re.compile(r"why\s+(?:is|are|isn'?t)\s+(?:the\s+)?(?:product\s+)?['\"]?(?P<x>[\w][\w\s\-.]*?)"
               r"['\"]?\s+(?:blocked|not\s+(?:published|live|listed|launched|ready)|stuck|"
               r"held|parked)", re.I),
    re.compile(r"what(?:'s|\s+is)\s+blocking\s+(?:the\s+)?product\s+['\"]?(?P<x>[\w][\w\-.]*)", re.I),
    re.compile(r"(?:status|blockers?)\s+(?:of|for)\s+(?:the\s+)?product\s+['\"]?"
               r"(?P<x>[\w][\w\-.]*)", re.I),
)


def classify(question: str) -> tuple[str, str | None]:
    q = (question or "").strip()
    low = q.lower()
    for pat in _PRODUCT_PATTERNS:
        m = pat.search(q)
        if m and m.group("x").strip().lower() not in ("launch", "the launch", "store", "shop"):
            return "product_blocked", m.group("x").strip()
    if "approval" in low or "approve" in low:
        return "approval_reason", q
    if "launch" in low and any(w in low for w in ("block", "stop", "wait", "need", "ready")):
        return "launch_blocked", None
    if any(w in low for w in ("overnight", "last night", "while i", "since yesterday",
                              "today", "did brambleloop do", "what happened")):
        return "overnight", None
    # W4-CLOSE6 (F-664): spend, agents and opportunities. Spend is checked before profit
    # ("money" alone stays a profit question; "spend"/"cost" are not).
    if any(w in low for w in ("spend", "spent", "cost", "burn", "bill")):
        return "spend", None
    if any(w in low for w in ("agent", "department", "working on", "who is doing", "busy",
                              "idle")):
        return "agents", None
    if any(w in low for w in ("opportunit", "idea", "what should we make", "gap")):
        return "opportunities", None
    if any(w in low for w in ("profit", "revenue", "sales", "money", "margin", "earn")):
        return "profit", None
    if any(w in low for w in ("incident", "broken", "wrong", "failing", "outage")):
        return "incidents", None
    return "unknown", None


# ---- readers ------------------------------------------------------------------------


def _find_product(db, needle: str):
    from ...core.models import Product

    n = needle.strip().strip("?.!").lower()
    slugish = re.sub(r"[\s_]+", "-", n)
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == slugish))
        if p is None:
            p = s.scalar(select(Product).where(or_(Product.slug.ilike(f"%{slugish}%"),
                                                   Product.title.ilike(f"%{n}%")))
                         .order_by(Product.id).limit(1))
        if p is not None:
            s.expunge(p)
        return p


def product_blocked(db, question: str, needle: str) -> dict:
    from ...core.models import AuditLog, Incident, Listing, PatternVersion
    from ...ops import publication_authority as pa

    p = _find_product(db, needle)
    if p is None:
        return _result(question, "product_blocked", [],
                       f"no product matching {needle!r} is recorded, so there is no evidence "
                       f"about why it would be blocked")
    facts = [_fact(f"product {p.slug} ({p.title}) has status {p.status!r}",
                   f"products:{p.id}")]
    blockers: list[str] = []
    next_action = None
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == p.id)
                      .order_by(PatternVersion.id.desc()).limit(1))
        listing = None if pv is None else s.scalar(
            select(Listing).where(Listing.product_slug == p.slug,
                                  Listing.version == pv.version)
            .order_by(Listing.id.desc()).limit(1))
        incidents = list(s.scalars(select(Incident).where(
            Incident.product_slug == p.slug, Incident.resolved == False)))  # noqa: E712
        audits = list(s.scalars(select(AuditLog).where(
            AuditLog.artifact.ilike(f"%{p.slug}%")).order_by(AuditLog.id.desc()).limit(5)))
        pv_view = None if pv is None else {
            "id": pv.id, "version": pv.version, "certified": bool(pv.certified),
            "release": pv.release_hash or "",
            "findings": [f for f in ((pv.certificate or {}).get("findings") or [])
                         if isinstance(f, dict)]}
        listing_view = None if listing is None else {"id": listing.id, "state": listing.state}
    if pv_view is None:
        blockers.append("no pattern version (CIR release) is stored")
        facts.append(_fact("no PatternVersion row exists for this product", "pattern_versions"))
        next_action = "author and certify a CIR release (Product Truth chain)"
    else:
        src = f"pattern_versions:{pv_view['id']}"
        if not pv_view["certified"]:
            errs = sorted({str(f.get("code")) for f in pv_view["findings"]
                           if str(f.get("severity", "")).lower() == "error"})
            blockers.append("release v{} is not certified{}".format(
                pv_view["version"], f" (blocking findings: {', '.join(errs)})" if errs else ""))
            facts.append(_fact(f"v{pv_view['version']} certified=False"
                               + (f"; error findings {errs}" if errs else ""), src))
            next_action = "fix the blocking findings and re-run certification"
        else:
            facts.append(_fact(f"v{pv_view['version']} is certified "
                               f"(release {pv_view['release'][:12]})", src))
        try:
            ev = pa.evidence(db, p.slug, pv_view["version"], pv_view["release"])
            for row in pa.display(ev):
                if row["section"] == "economics":
                    continue
                if row["state"] != "PASS":
                    blockers.append(f"{row['section']} gate {row['state']}: {row['why'][:160]}")
                facts.append(_fact(f"{row['section']} gate: {row['state']}"
                                   + (f" ({row['why'][:200]})" if row["why"] else ""),
                                   f"ops.publication_authority.evidence[{row['section']}]"
                                   f"@{src}"))
            if next_action is None and ev["summary"]["not_passing"]:
                next_action = (f"resolve the {ev['summary']['not_passing'][0]} gate first "
                               f"(Product Truth before publication)")
        except Exception as exc:  # noqa: BLE001
            facts.append(_fact(f"gate evidence unreadable ({type(exc).__name__}); treated as "
                               f"UNKNOWN, not passing", "ops.publication_authority.evidence"))
            blockers.append("gate evidence UNKNOWN")
    if listing_view is not None:
        facts.append(_fact(f"listing state {listing_view['state']!r}",
                           f"listings:{listing_view['id']}"))
    for inc in incidents:
        blockers.append(f"open {inc.severity} incident #{inc.id}"
                        + (" (halts publication)" if inc.halts_publication else "")
                        + f": {inc.summary[:120]}")
        facts.append(_fact(f"open {inc.severity} incident: {inc.summary[:200]}",
                           f"incidents:{inc.id}"))
        if inc.halts_publication and next_action is None:
            next_action = f"resolve incident #{inc.id}"
    for a in audits:
        facts.append(_fact(f"recent event {a.action} on {a.artifact}", f"audit_log:{a.id}"))
    if blockers:
        answer = f"{p.slug} is blocked by: " + "; ".join(blockers) + "."
    else:
        answer = (f"No recorded gate blocks {p.slug}: it is certified, every gated section "
                  f"passes and no incident is open. Publishing still needs an owner grant.")
        next_action = next_action or "review the publication card in Approvals"
    return _result(question, "product_blocked", facts, answer, next_action=next_action)


def launch_blocked(db, question: str) -> dict:
    from . import approvals, readers

    facts = []
    parts = []
    try:
        from ...core import phase as phase_mod

        ph = phase_mod.resolve(db)
        facts.append(_fact(f"effective phase {ph['phase']} ({ph['why'][:160]})",
                           "core.phase.resolve (audit_log owner.phase.transition)"))
        if ph["phase"] == "shadow":
            parts.append("the company runs in SHADOW (no live publication)")
    except Exception:  # noqa: BLE001
        pass
    box = approvals.inbox(db)
    for c in box["cards"][:8]:
        facts.append(_fact(f"owner decision open: {c['title']}", c["sources"][-1]
                           if c["sources"] else "build2.executor.approval_inbox"))
    if box["cards"]:
        parts.append(f"{len(box['cards'])} owner decision(s) open (top: {box['cards'][0]['title']})")
    inc = readers.incidents(db)
    halting = [i for i in inc.get("items", []) if i.get("halts_publication")]
    for i in halting:
        facts.append(_fact(f"incident halts publication: {i['summary'][:160]}", i["source"]))
    if halting:
        parts.append(f"{len(halting)} incident(s) halt publication")
    prods = readers.products(db)
    if prods["status"] == "OK":
        facts.append(_fact(f"{prods.get('certified', 0)} of {len(prods['items'])} products "
                           f"have a certified release; {prods.get('on_etsy', 0)} are on Etsy",
                           "products+pattern_versions+listings"))
    if not facts:
        return _result(question, "launch_blocked", [],
                       "no launch readiness evidence is recorded")
    answer = ("Launch is blocked by: " + "; ".join(parts) + ".") if parts else (
        "No recorded blocker found in the owner queue, incidents or phase record.")
    return _result(question, "launch_blocked", facts, answer,
                   next_action=(box["cards"][0]["proposed_action"] if box["cards"] else None))


def overnight(db, question: str, hours: float = 12) -> dict:
    from . import readers

    jw = readers.jobs_window(db, hours)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = readers.audit_events(db, since=since, limit=15)
    facts = []
    if jw.get("status") == "OK" and jw.get("completed"):
        facts.append(_fact(f"{jw['completed']} jobs completed, {jw['failed']} failed, "
                           f"{jw['created']} created in the last {hours:g} h", "jobs"))
        for it in jw["items"][:8]:
            facts.append(_fact(f"{it['agent']} completed {it['completed']} job(s)", "jobs"))
    for e in events:
        facts.append(_fact(f"{e['at']}: {e['actor']} {e['action']} {e['artifact'] or ''}"
                           .strip(), e["source"], e["at"]))
    if not facts:
        return _result(question, "overnight", [],
                       f"no completed job or audit event is recorded in the last {hours:g} h")
    return _result(question, "overnight", facts,
                   f"In the last {hours:g} h: {jw.get('completed', 0)} jobs completed and "
                   f"{len(events)} significant events were recorded (see facts).")


def profit(db, question: str) -> dict:
    from . import providers, readers

    acct = providers.call("accounting", db)
    facts = []
    if acct["status"] != "UNKNOWN":
        for it in acct["items"][:10]:
            if isinstance(it, dict):
                facts.append(_fact(str(it.get("label") or it.get("metric") or it)[:200]
                                   + (f": {it.get('display') or it.get('value')}"
                                      if (it.get("display") or it.get("value") is not None)
                                      else ""),
                                   (acct["sources"] or [acct["provider"]])[0]))
    rev = readers.revenue(db)
    if rev["state"] == "MEASURED":
        facts.append(_fact(f"reconciled revenue {rev['display']}", rev["sources"][0]))
        return _result(question, "profit", facts,
                       f"Measured, reconciled revenue is {rev['display']}. Profit needs the "
                       f"accountant's cost attribution"
                       + ("" if acct["status"] != "UNKNOWN" else
                          f" (accountant view UNKNOWN: {acct.get('reason')})") + ".")
    why = rev.get("why") or "order source not measured"
    return _result(question, "profit", facts,
                   f"revenue is UNMEASURED ({why}); profit cannot be stated and is not shown "
                   f"as CA$0.00" + (f"; accountant view: {acct.get('reason')}"
                                    if acct["status"] == "UNKNOWN" else ""),
                   status="UNKNOWN")


def approval_reason(db, question: str) -> dict:
    from . import approvals

    box = approvals.inbox(db)
    words = {w for w in re.findall(r"[a-z0-9_\-]{4,}", question.lower())
             if w not in ("does", "need", "needs", "approval", "approve", "why", "this", "what",
                          "brambleloop", "owner", "my")}
    best, score = None, 0
    for c in box["cards"]:
        hay = f"{c['card_id']} {c['title']} {c.get('proposed_action') or ''}".lower()
        sc = sum(1 for w in words if w in hay)
        if sc > score:
            best, score = c, sc
    if best is None:
        if not box["cards"]:
            return _result(question, "approval_reason", [],
                           "no owner approval is open, so nothing needs your approval now")
        facts = [_fact(f"open: {c['title']}", (c["sources"] or ["owner_actions"])[-1])
                 for c in box["cards"][:8]]
        return _result(question, "approval_reason", facts,
                       "Could not tell which approval you mean; open approvals are listed in "
                       "facts.", status="UNKNOWN")
    facts = [_fact(f"{e['label']}: {e['state']} {e['why'][:160]}", e["source"])
             for e in best["evidence"]]
    facts += [_fact(f"card source {s_}", s_) for s_ in best["sources"]]
    return _result(question, "approval_reason", facts,
                   f"{best['title']} needs you because only the owner holds this authority. "
                   f"{best['recommendation']}. If nothing is done: "
                   f"{best['consequence_of_no_action']}.",
                   next_action=best.get("proposed_action"))


def incidents_q(db, question: str) -> dict:
    from . import readers

    inc = readers.incidents(db)
    if inc["status"] == "UNKNOWN":
        return _result(question, "incidents", [], inc.get("reason") or "incidents unreadable")
    facts = [_fact(f"{i['severity']}: {i['summary'][:200]}", i["source"], i["at"])
             for i in inc["items"]]
    if not facts:
        return _result(question, "incidents",
                       [_fact("no unresolved incident is recorded", "incidents")],
                       "No incident is open.")
    return _result(question, "incidents", facts, f"{len(facts)} open incident(s); "
                   f"most severe: {inc['items'][0]['summary'][:160]}.")


def spend_q(db, question: str) -> dict:
    """This month's recorded spend, by purpose and agent, each line citing cost_entries."""
    from ...finance import spend_report

    try:
        w = spend_report.what_it_bought(db)
    except Exception as exc:  # noqa: BLE001
        return _result(question, "spend", [], f"spend unreadable: {type(exc).__name__}")
    if not w.get("calls"):
        return _result(question, "spend",
                       [_fact(f"no cost row is recorded for {w['month']}", "cost_entries")],
                       f"Nothing is recorded as spent this month ({w['month']}).")
    facts = [_fact(f"{k}: CA${v['cad']:.2f} over {v['calls']} call(s)",
                   "cost_entries (finance.spend_report.what_it_bought by_purpose)")
             for k, v in list(w["by_purpose"].items())[:6]]
    facts += [_fact(f"agent {k}: CA${v['cad']:.2f}",
                    "cost_entries (finance.spend_report.what_it_bought by_agent)")
              for k, v in list(w["by_agent"].items())[:4]]
    top = next(iter(w["by_purpose"].items()))
    return _result(question, "spend", facts,
                   f"Recorded spend this month ({w['month']}) is CA${w['spent_cad']:.2f} over "
                   f"{w['calls']} calls; the largest purpose is {top[0]} at "
                   f"CA${top[1]['cad']:.2f}. This is recorded exposure, not a reconciled bill; "
                   f"the linear projection to month end is "
                   f"CA${w['projected_month_end_cad']:.2f}.")


def agents_q(db, question: str) -> dict:
    """What each agent is doing now: running job, ready backlog, parked types, idle."""
    from ...swarm import metrics

    try:
        view = metrics.agents_view(db)
    except Exception as exc:  # noqa: BLE001
        return _result(question, "agents", [], f"agents unreadable: {type(exc).__name__}")
    rows = view.get("agents") or []
    if not rows:
        return _result(question, "agents", [], "no agent is registered")
    busy = [r for r in rows if r.get("running_job")]
    facts = [_fact(f"{r['agent']} is running {r['running_job']['job_type']}",
                   r["running_job"]["job"]) for r in busy[:8]]
    facts += [_fact(f"{r['agent']} has {r['pending_ready']} ready job(s) waiting", "jobs")
              for r in rows if not r.get("running_job") and r.get("pending_ready")][:6]
    facts += [_fact(f"{r['agent']} parked: {t} ({why})", "swarm.orchestrate")
              for r in rows for t, why in (r.get("parked_job_types") or {}).items()][:6]
    idle = [r["agent"] for r in rows if r.get("idle")]
    if not facts:
        facts = [_fact(f"{len(idle)} enabled agent(s) idle with no ready work", "jobs")]
    return _result(question, "agents", facts,
                   f"{len(busy)} agent(s) are running a job now; {len(idle)} enabled agent(s) "
                   f"are idle with nothing ready (see facts for who and what).")


def opportunities_q(db, question: str) -> dict:
    """Open opportunities from durable rows: MJs-derived marketplace openings the mission
    entered, and improvement proposals not yet decided. Never invented."""
    from ...core.models import Improvement, MjsMissionEvent

    facts = []
    with db.session() as s:
        for ev in s.scalars(select(MjsMissionEvent).where(
                MjsMissionEvent.entered == True)  # noqa: E712
                .order_by(MjsMissionEvent.id.desc()).limit(6)):
            tgt = (ev.seasonal or {}).get("target") or {}
            facts.append(_fact(
                f"marketplace opening: {ev.pod or '?'} / {ev.arena or '?'}"
                + (f" for {tgt['event']}" if tgt.get("event") else "")
                + (f" ({ev.decision})" if ev.decision else ""),
                f"mjs_mission_events:{ev.id}", _iso_or_none(ev.at)))
        for imp in s.scalars(select(Improvement).where(
                Improvement.state.in_(("proposed", "PROPOSED", "testing", "TESTING")))
                .order_by(Improvement.id.desc()).limit(4)):
            facts.append(_fact(f"improvement proposal ({imp.cell}): {imp.hypothesis[:160]}",
                               f"improvements:{imp.id}", _iso_or_none(imp.at)))
    if not facts:
        return _result(question, "opportunities", [],
                       "no entered marketplace opening and no open improvement proposal is "
                       "recorded")
    return _result(question, "opportunities", facts,
                   f"{len(facts)} open opportunit{'y' if len(facts) == 1 else 'ies'} on record "
                   f"(marketplace openings the mission entered, then undecided improvement "
                   f"proposals); each cites its row.")


def _iso_or_none(v):
    try:
        return v.isoformat() if v is not None else None
    except AttributeError:
        return None


def ask(db, question: str) -> dict:
    question = str(question or "").strip()[:500]
    if not question:
        return _result(question, "unknown", [], "ask a question")
    intent, arg = classify(question)
    if intent == "product_blocked":
        return product_blocked(db, question, arg or "")
    if intent == "launch_blocked":
        return launch_blocked(db, question)
    if intent == "overnight":
        return overnight(db, question)
    if intent == "profit":
        return profit(db, question)
    if intent == "approval_reason":
        return approval_reason(db, question)
    if intent == "incidents":
        return incidents_q(db, question)
    if intent == "spend":
        return spend_q(db, question)
    if intent == "agents":
        return agents_q(db, question)
    if intent == "opportunities":
        return opportunities_q(db, question)
    return _result(question, "unknown", [],
                   "this question is not one the company can answer from recorded evidence "
                   "yet. Supported: " + "; ".join(SUPPORTED))
