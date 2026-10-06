"""Talk to Laura (D-FB-13 / spec/07 item 9): the owner's business conversation with the
Founder/CEO, answered from durable evidence.

Pipeline, deterministic first:

  classify    keyword rules route the question to one of Laura's executive intents
  retrieve    `evidence` readers collect source-linked facts for that intent
  compose     a fixed template in Laura's business voice states those facts -- and only
              those facts -- and names every missing source as UNKNOWN with its reason
  propose     follow-on work grounded in the same evidence (`followon.proposal`): GREEN
              internal missions, or protected owner actions (step-up)
  phrase      optional: a gateway rephrasing that must preserve every number (`phrasing`)
  persist     the turn (question, answer, facts, sources, proposals) in `laura_cc_turns`

An intent with no evidence answers UNKNOWN; nothing is invented, and no money figure that is
UNKNOWN is ever rendered as CA$0.00. Questions outside Laura's intents fall back to the
existing Ask Company reader (`app.command_center.ask`), whose answers are equally grounded.

Business register only: this module neither reads nor writes any private/owner-relationship
memory or register (spec/07 owner correction; that layer is out of this lane's scope).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import evidence as ev
from . import delegation, followon, identity_view

METHOD = "deterministic retrieval over durable state + fixed templates (no model call)"
UNKNOWN = "UNKNOWN"
MAX_QUESTION = 500

SUGGESTED = (
    "What did your company do overnight?",
    "What are you working on?",
    "How does your store look?",
    "What's making money / losing money?",
    "What did your departments discover?",
    "What did you learn?",
    "What should we launch next?",
    "What genuinely needs me?",
)

# (intent, keywords) in priority order: the first intent with a matching keyword wins.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("needs_me", ("needs me", "need me", "needs my", "need my", "my attention", "my decision",
                  "approve", "approval", "waiting on me", "should i do", "do you need")),
    ("launch_next", ("launch next", "should we launch", "launch first", "next launch",
                     "next product", "what to launch", "launch")),
    ("money", ("making money", "losing money", "money", "profit", "revenue", "sales",
               "margin", "cash", "spend", "spent", "cost", "earn", "runway")),
    ("store", ("store", "shop", "storefront", "etsy", "listing", "banner", "look")),
    ("discoveries", ("discover", "found", "find", "insight", "research", "departments")),
    ("learned", ("learn", "lesson", "improv", "getting better")),
    ("visual", ("visual", "image", "photo", "render", "picture")),
    ("working_on", ("working on", "busy", "doing now", "right now", "focus", "priorit",
                    "current")),
    ("overnight", ("overnight", "last night", "while i", "since yesterday", "today",
                   "what happened", "what did you do", "company do", "what changed")),
    ("identity", ("who are you", "your role", "your job", "are you human", "are you real",
                  "what are you")),
)


def classify(question: str) -> str:
    """Keywords match at a word start ("learn" never matches "earn"). An instruction to a
    department ("have Design make three more banners") is a delegation, checked first."""
    from . import delegation

    if delegation.parse(question):
        return "delegate"
    low = " ".join(str(question or "").lower().replace("’", "'").split())
    for intent, words in _RULES:
        if any(re.search(r"(?<![a-z])" + re.escape(w), low) for w in words):
            return intent
    return "fallback"


# ---- intents: which evidence, what Laura says first ---------------------------------------


# Which of Laura's memory tiers (lane E) supplements each intent. Memory is supplementary:
# a memory section with no matching entry is left out rather than reported as UNKNOWN.
_MEMORY_TIERS = {"working_on": ("operational",), "store": ("brand",),
                 "learned": ("experience",), "discoveries": ("experience",),
                 "identity": ("canonical",)}


def _with_memory(db, intent: str, sections: list[dict], session_public_id: str) -> list[dict]:
    tiers = _MEMORY_TIERS.get(intent)
    if not tiers or not session_public_id:
        return sections
    m = ev.memory(db, session_public_id, None, tiers=tiers)
    return sections + [m] if m["facts"] else sections


def _sections(db, intent: str) -> list[dict]:
    if intent == "overnight":
        return [ev.overnight(db, 12), ev.departments(db)]
    if intent == "working_on":
        return [ev.executive(db), ev.working_on(db), ev.departments(db)]
    if intent == "store":
        return [ev.store(db), ev.products(db), ev.seo(db)]
    if intent == "money":
        return [ev.money(db)]
    if intent == "discoveries":
        return [ev.lessons(db, 72), ev.improvement(db), ev.seo(db), ev.ads(db),
                ev.visual_rnd(db)]
    if intent == "learned":
        return [ev.lessons(db), ev.improvement(db), ev.visual_rnd(db)]
    if intent == "launch_next":
        return [ev.products(db), ev.store(db), ev.owner_queue(db), ev.phase(db)]
    if intent == "needs_me":
        return [ev.owner_queue(db), _laura_owner_actions()]
    if intent == "visual":
        return [ev.visual_rnd(db)]
    return []


_OPENING = {
    "overnight": "Here is what my company did, straight from the records.",
    "working_on": "Here is what my company is working on right now.",
    "store": "Here is how the store stands today, read from Store Foundation.",
    "money": "On money, I'll only tell you what the books measure.",
    "discoveries": "Here is what my departments have turned up.",
    "learned": "Here is what we have learned, from recorded lessons and loops.",
    "launch_next": "Here is how I'd decide what to launch next, from the evidence.",
    "needs_me": "Here is what genuinely needs you -- only the decisions I can't make.",
    "visual": "Here is where Visual R&D stands.",
}


def _laura_owner_actions() -> dict:
    """Laura's own catalogue owner actions (not yet in the consolidated queue because their
    max cost is UNKNOWN, which that queue cannot represent without showing CA$0.00)."""
    from . import voice_selection

    a = voice_selection.OWNER_ACTION
    f = ev.fact(f"{a['action']} -- needs {'; '.join(a['needs'])}; max cost {a['max_cost']}; "
                f"about {a['minutes']} min; if it waits: {a['consequence_of_waiting']}",
                "laura.agency.voice_selection.OWNER_ACTION (D-FB-18 item 7)", basis="unknown")
    return ev.section("laura_owner_actions", "Laura's voice: your listening decision", [f])


def _fact_line(facts: list[dict], n: int) -> str:
    return "; ".join(f["statement"].rstrip(".") for f in facts[:n])


def _compose(intent: str, sections: list[dict]) -> tuple[str, str, list[dict]]:
    """(status, answer, unknowns). Every clause comes from a fact or a recorded reason."""
    known = [s for s in sections if s["facts"]]
    unknowns = [{"section": s["key"], "title": s["title"],
                 "reason": s.get("reason") or "no durable evidence recorded"}
                for s in sections if not s["facts"]]
    parts: list[str] = []

    if intent == "money":
        m = sections[0] if sections else None
        if m and m["facts"]:
            rev, prof = m.get("revenue_state"), m.get("profit_state")
            if rev != "MEASURED":
                parts.append("I can't yet tell you what is making or losing money: revenue is "
                             f"{rev or UNKNOWN} and profit is {prof or UNKNOWN}, and I won't "
                             "show either as CA$0.00.")
                unknowns.append({"section": "money.revenue", "title": "Measured revenue",
                                 "reason": f"revenue is {rev or UNKNOWN}; profit is "
                                           f"{prof or UNKNOWN}"})
            parts.append(f"{m['title']}: {_fact_line(m['facts'], 8)}.")
    elif intent == "needs_me":
        q = sections[0] if sections else None
        if q and q.get("nothing_open"):
            parts.append("Nothing in the company queue needs you: no owner decision is open and "
                         "no publication-halting or P0/P1 incident is recorded.")
        elif q and q["facts"]:
            parts.append(f"{len(q['facts'])} item(s) need you: {_fact_line(q['facts'], 6)}.")
        v = next((x for x in sections if x["key"] == "laura_owner_actions"), None)
        if v and v["facts"]:
            parts.append(f"And one of mine, when you're ready: {_fact_line(v['facts'], 1)}.")
    elif intent == "launch_next":
        p = next((s for s in sections if s["key"] == "products"), None)
        items = (p or {}).get("items") or []
        ready = [i for i in items if i.get("certified") and not i.get("on_etsy")]
        if ready:
            top = ready[0]
            parts.append(f"My pick is {top['slug']}: it has a certified release (v"
                         f"{top.get('version')}) and is not on Etsy yet. Publishing it is "
                         f"your decision, through its own grant.")
        elif items:
            parts.append(f"None of the {len(items)} recorded product(s) is both certified and "
                         f"off Etsy, so I have no launch candidate to recommend yet; "
                         f"certification comes first.")
        for s in known:
            parts.append(f"{s['title']}: {_fact_line(s['facts'], 4)}.")
    else:
        for s in known:
            parts.append(f"{s['title']}: {_fact_line(s['facts'], 5)}.")

    if not any(s["facts"] for s in sections):
        reasons = "; ".join(f"{u['title']}: {u['reason']}" for u in unknowns) or \
            "no evidence source answers this"
        return UNKNOWN, f"UNKNOWN: I don't have durable evidence to answer that yet ({reasons}).", \
            unknowns
    if unknowns:
        parts.append("Not known yet: " + "; ".join(
            f"{u['title']} ({u['reason']})" for u in unknowns) + ".")
    status = "ANSWERED" if not unknowns else "PARTIAL"
    return status, " ".join([_OPENING.get(intent, "")] + parts).strip(), unknowns


def _proposals(intent: str, sections: list[dict]) -> list[dict]:
    by = {s["key"]: s for s in sections}

    def srcs(*keys):
        return [x for k in keys for x in (by.get(k) or {}).get("sources", [])][:10]

    out: list[dict | None] = []
    if intent in ("overnight", "working_on"):
        out.append(followon.proposal(
            "executive", "autonomy.morning_handoff", "Write a fresh company brief",
            "re-read jobs, costs, incidents and owner actions into a new brief",
            srcs("overnight", "working_on", "departments")))
    if intent == "store":
        st = by.get("store") or {}
        if st.get("status") != "OK" or (by.get("seo") or {}).get("status") != "OK":
            out.append(followon.proposal(
                "store_commerce", "seo.cycle", "Run a store search (SEO) cycle",
                f"store is {st.get('status', UNKNOWN)}; search readiness is "
                f"{(by.get('seo') or {}).get('status', UNKNOWN)}", srcs("store", "seo")))
        out.append(followon.proposal(
            "store_commerce", "autonomy.department_review", "Have Store / Commerce review itself",
            "department self-review against its KPIs", srcs("store", "products")))
    if intent == "money":
        out.append(followon.proposal(
            "finance", "finance.accounting.cycle", "Refresh the books (accounting cycle)",
            "re-post and re-read the ledger so money figures are current", srcs("money")))
    if intent in ("discoveries", "learned"):
        out.append(followon.proposal(
            "learn", "improve.mine", "Mine recent failures for improvements",
            "turn incidents, refusals and dead letters into lessons",
            srcs("lessons", "improvement")))
    if intent == "discoveries":
        out.append(followon.proposal(
            "intelligence", "radar.score", "Score the next uncovered market arena",
            "coverage gap queue", srcs("seo", "ads")))
    if intent == "visual":
        out.append(followon.proposal(
            "visual", "visual.identity_drift", "Check my visual identity for drift",
            "reads audit rows; writes an identity-drift reading", srcs("visual_rnd")))
    if intent == "launch_next":
        items = (by.get("products") or {}).get("items") or []
        ready = [i for i in items if i.get("certified") and not i.get("on_etsy")]
        out.append(followon.proposal(
            "product_design", "seasonal.sentinel", "Recompute seasonal launch windows",
            "launch timing against today's date", srcs("products", "store")))
        if ready:
            top = ready[0]
            out.append(followon.proposal(
                "store_commerce", "store.publish", f"Decide whether to publish {top['slug']}",
                f"{top['slug']} has a certified release and is not on Etsy",
                [*top.get("sources", []), *srcs("store")], subject=top["slug"]))
    return [p for p in out if p is not None]


# ---- the conversation ----------------------------------------------------------------------


def _identity_answer(db, session_public_id: str) -> tuple[str, str, list[dict], list[dict]]:
    ident = identity_view.identity(db)
    src = (ident.get("sources") or [ident.get("source") or "visual.canonical"])[0]
    facts = [ev.fact(f"identity {ident['identity_id']}: {ident['name']}, {ident['role']}", src),
             ev.fact(ident["truthful_identity"][:380], src),
             ev.fact("model-independent: identity, memory and history live in Brambleloop's "
                     "durable state; a model provides cognition only", "DECISION_LOG D-FB-13")]
    answer = (f"I'm {ident['name']}, {ident['public_identity']} -- {ident['role']}. I'm an AI, "
              f"not a human; my history is the work my company has actually recorded. I run "
              f"Brambleloop through its departments within my authority, and Finance, Product "
              f"Truth and Security can challenge or block me.")
    ver = ident.get("verified") or {}
    if ver.get("status") and ver["status"] != "OK":
        facts.append(ev.fact(f"durable identity record {ver['status']}: {ver.get('reason')}",
                             "laura_identity_versions"))
        answer += f" (My durable identity record reads {ver['status']}; see evidence.)"
    mem = _with_memory(db, "identity", [], session_public_id)
    for m in mem:
        facts.extend(m["facts"][:4])
    return "ANSWERED", answer, facts, []


def _delegation_answer(db, question: str) -> tuple[str, str, list[dict], list[dict],
                                                   list[dict]]:
    """(status, answer, facts, unknowns, proposals) for an instruction to a department."""
    from ...autonomy import charters, memory

    d = delegation.parse(question) or {}
    if not d.get("department"):
        names = ", ".join(sorted({c.name for c in charters.BY_KEY.values()}))
        return (UNKNOWN, f"UNKNOWN: I don't have a department called "
                         f"\"{d.get('spoken_department')}\". My departments are: {names}.",
                [], [{"section": "delegation", "title": "Department",
                      "reason": f"no department {d.get('spoken_department')!r}"}], [])
    p = delegation.plan(d)
    ch = charters.BY_KEY.get(p["department"])
    if ch is None:
        return (UNKNOWN, f"UNKNOWN: department {p['department']} has no charter.", [],
                [{"section": "delegation", "title": "Department charter",
                  "reason": f"no charter for {p['department']}"}], [])
    facts = [ev.fact(f"{ch.name} holds GREEN authority for: "
                     f"{', '.join(sorted(ch.generatable))}", f"autonomy.charters:{ch.key}"),
             ev.fact("Protected work (publish, activate, live listing changes, pricing, ads, "
                     "customer messages) only ever becomes an owner decision",
                     "autonomy.charters.PROTECTED_JOB_TYPES")]
    if p["route"] == "refused":
        facts.append(ev.fact(f"Refused: {p['why']}", "DECISION_LOG (company constitution)"))
        return ("ANSWERED", f"I won't hand that to {ch.name}: {p['why']}. That decision is "
                            f"yours; nothing has been queued.", facts, [], [])
    block = memory.active_block(db, ch.key)
    if block:
        facts.append(ev.fact(f"{ch.name} is blocked by the owner: "
                             f"{(block.get('body') or {}).get('reason') or 'no reason given'}",
                             f"company_memory:{block.get('key') or 'block'}"))
    for need in p.get("gated") or []:
        facts.append(ev.fact(f"GATED: {need}", "visual.rnd.status (spend.paid_execution)",
                             basis="unknown"))
    if "banner" in p["task"].lower() or "logo" in p["task"].lower():
        facts.append(ev.fact("The owner's canonical banner and logo stay the art target; new "
                             "work is a candidate for your review, never a silent replacement",
                             "DECISION_LOG D-FB-17"))
    n = p.get("count")
    what = f"{p['task']}" + ("" if n is None else f" (count: {n})")
    title = f"Delegate to {ch.name}: {p['task']}"[:200]
    prop = followon.proposal(p["department"], p["job_type"], title, p["why"],
                             [f"autonomy.charters:{ch.key}", f"laura instruction: {question}"],
                             subject=("delegation:" + re.sub(r"[^a-z0-9]+", "-",
                                                             p["task"].lower()))[:80])
    if prop is None:
        return ("ANSWERED", f"{ch.name} has no authority I can delegate that under; nothing "
                            f"has been queued.", facts, [], [])
    prop = {**prop, "delegation": True, "brief": delegation.brief(p, question)}
    if p["route"] == "owner_action":
        answer = (f"That's protected ({p['job_type']}), so I can't just hand it to "
                  f"{ch.name}. Confirm with step-up and I'll record it as your decision in "
                  f"Approvals; the act itself still needs its own grant.")
    else:
        answer = (f"I'll give this to {ch.name}: {what}. Confirm and it goes on their queue as "
                  f"internal work -- no publishing, no spending, no customer contact.")
        if p.get("gated"):
            answer += " Honest limit: " + "; ".join(p["gated"]) + "."
        if block:
            answer += f" {ch.name} is currently blocked by you, so I won't route around it."
    return "ANSWERED", answer, facts, [], [prop]


def converse(db, question: str, *, session_public_id: str = "", gateway=None) -> dict:
    """Answer one business question as Laura, persist the turn, return it."""
    from ..private.firewall import reject_private
    from .models import REGISTER, LauraTurn, ensure_tables

    # PRIV: owner-private values never enter a business conversation (stdlib-only firewall;
    # raises PrivateInputRefused for anything tagged private, however nested).
    reject_private(question, context="laura.business")
    ensure_tables(db)
    question = " ".join(str(question or "").split())[:MAX_QUESTION]
    ident = identity_view.identity(db)
    intent = classify(question) if question else "empty"
    sections: list[dict] = []
    proposals: list[dict] = []
    method = METHOD
    if not question:
        status, answer, facts, unknowns = (UNKNOWN, "Ask me about the business -- for "
                                           "example: " + "; ".join(SUGGESTED[:4]), [], [])
    elif intent == "identity":
        status, answer, facts, unknowns = _identity_answer(db, session_public_id)
    elif intent == "delegate":
        status, answer, facts, unknowns, proposals = _delegation_answer(db, question)
        sections = [ev.section("delegation", "Delegation", facts,
                               status="OK" if facts else UNKNOWN)]
    elif intent == "fallback":
        from ...app.command_center import ask as ask_mod

        a = ask_mod.ask(db, question)
        facts = [ev.fact(f["statement"], f["source"], as_of=f.get("as_of"))
                 for f in a.get("facts") or [] if isinstance(f, dict)]
        status = "ANSWERED" if a.get("status") == "ANSWERED" and facts else UNKNOWN
        answer = a.get("answer") or "UNKNOWN"
        if status == UNKNOWN and not answer.startswith("UNKNOWN"):
            answer = "UNKNOWN: " + answer
        unknowns = [] if status != UNKNOWN else [{"section": "ask", "title": "Ask Company",
                                                  "reason": answer[:300]}]
        intent = f"ask:{a.get('intent') or 'unknown'}"
        method = f"{METHOD}; routed to Ask Company ({ask_mod.METHOD})"
        sections = [ev.section("ask", "Company records", facts,
                               status="OK" if facts else UNKNOWN,
                               reason=None if facts else answer[:300])]
    else:
        sections = _with_memory(db, intent, _sections(db, intent), session_public_id)
        status, answer, unknowns = _compose(intent, sections)
        facts = [f for s in sections for f in s["facts"]]
        proposals = _proposals(intent, sections)

    meta = {"phrased": False}
    if facts and status != UNKNOWN:
        from . import phrasing

        answer, meta = phrasing.phrase(
            db, answer, gateway=gateway,
            facts={f"f{i}": f["statement"] for i, f in enumerate(facts[:20])})
        if meta.get("phrased"):
            method = f"{METHOD}; {meta['method']}"
    sources = list(dict.fromkeys(f["source"] for f in facts))
    if status != UNKNOWN and not sources:
        status = UNKNOWN          # an answer with no source is not an answer
        answer = "UNKNOWN: " + answer
    with db.session() as s:
        row = LauraTurn(register=REGISTER, session_public_id=session_public_id[:40],
                        question=question, intent=intent[:40], status=status, answer=answer,
                        facts=facts, sources=sources, unknowns=unknowns, proposals=proposals,
                        method=method[:200], identity_id=ident["identity_id"])
        s.add(row)
        s.flush()
        turn_id, at = row.id, row.at
    return {"turn_id": turn_id, "at": _iso(at), "register": REGISTER, "question": question,
            "intent": intent, "status": status, "answer": answer, "facts": facts,
            "sources": sources, "unknowns": unknowns, "proposals": proposals,
            "sections": [{k: s_[k] for k in ("key", "title", "status", "reason")} | {
                "facts": len(s_["facts"])} for s_ in sections],
            "method": method, "phrasing": meta, "speaker": speaker(ident),
            "voice_findings": identity_view.voice_findings(answer)}


def _iso(v) -> str | None:
    if v is None:
        return None
    v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def speaker(ident: dict | None = None) -> dict:
    ident = ident or identity_view.identity()
    return {"name": ident["name"], "role": ident["role"], "identity_id": ident["identity_id"],
            "public_identity": ident["public_identity"],
            "portrait_path": "/api/cc/laura/portrait",
            "portrait_label": "Internal — canonical reference, not publication-approved",
            "identity_source": ident.get("source")}


def history(db, limit: int = 20) -> list[dict]:
    from sqlalchemy import select

    from .models import REGISTER, LauraTurn, ensure_tables

    ensure_tables(db)
    limit = max(1, min(int(limit or 20), 100))
    with db.session() as s:
        rows = list(s.scalars(select(LauraTurn).where(LauraTurn.register == REGISTER)
                              .order_by(LauraTurn.id.desc()).limit(limit)))
        return [{"turn_id": r.id, "at": _iso(r.at), "question": r.question,
                 "intent": r.intent, "status": r.status, "answer": r.answer,
                 "facts": r.facts or [], "sources": r.sources or [],
                 "unknowns": r.unknowns or [], "proposals": r.proposals or [],
                 "method": r.method} for r in rows]


def overview(db) -> dict:
    """The Laura view's header: who she is, what needs the owner, how the company runs."""
    ident = identity_view.identity(db)
    q = ev.owner_queue(db)
    d = ev.departments(db)
    ph = ev.phase(db)
    by_status: dict[str, int] = {}
    for f in d["facts"]:
        for st in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN"):
            if f": {st}" in f["statement"].split(",")[0]:
                by_status[st] = by_status.get(st, 0) + 1
    return {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "register": "business",
            "speaker": speaker(ident),
            "identity": {k: ident.get(k) for k in ("identity_id", "name", "role",
                                                   "public_identity", "truthful_identity",
                                                   "authority", "source", "sources",
                                                   "verified", "identity_disagreement")},
            "needs_you": {"status": q["status"], "count": len(q["facts"]),
                          "reason": q.get("reason"), "items": q["facts"][:5]},
            "departments": {"status": d["status"], "reason": d.get("reason"),
                            "by_status": by_status if d["facts"] else None},
            "phase": ph["facts"][0]["statement"] if ph["facts"] else UNKNOWN,
            "suggested": list(SUGGESTED),
            "recent_followons": followon.recent(db, 10),
            "method": METHOD}
