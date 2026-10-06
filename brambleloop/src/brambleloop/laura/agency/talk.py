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
from . import followon, identity_view

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
    """Keywords match at a word start ("learn" never matches "earn")."""
    low = " ".join(str(question or "").lower().replace("’", "'").split())
    for intent, words in _RULES:
        if any(re.search(r"(?<![a-z])" + re.escape(w), low) for w in words):
            return intent
    return "fallback"


# ---- intents: which evidence, what Laura says first ---------------------------------------


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
        return [ev.owner_queue(db)]
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
            parts.append("Nothing needs you right now: no owner decision is open and no "
                         "publication-halting or P0/P1 incident is recorded.")
        elif q and q["facts"]:
            parts.append(f"{len(q['facts'])} item(s) need you: {_fact_line(q['facts'], 6)}.")
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


def _identity_answer() -> tuple[str, str, list[dict], list[dict]]:
    ident = identity_view.identity()
    src = ident.get("source") or "brambleloop.visual.canonical"
    facts = [ev.fact(f"identity {ident['identity_id']}: {ident['name']}, {ident['role']}", src),
             ev.fact(ident["truthful_identity"][:380], src),
             ev.fact("model-independent: identity, memory and history live in Brambleloop's "
                     "durable state; a model provides cognition only", "DECISION_LOG D-FB-13")]
    answer = (f"I'm {ident['name']}, {ident['public_identity']} -- {ident['role']}. I'm an AI, "
              f"not a human; my history is the work my company has actually recorded. I run "
              f"Brambleloop through its departments within my authority, and Finance, Product "
              f"Truth and Security can challenge or block me.")
    return "ANSWERED", answer, facts, []


def converse(db, question: str, *, session_public_id: str = "", gateway=None) -> dict:
    """Answer one business question as Laura, persist the turn, return it."""
    from .models import REGISTER, LauraTurn, ensure_tables

    ensure_tables(db)
    question = " ".join(str(question or "").split())[:MAX_QUESTION]
    ident = identity_view.identity()
    intent = classify(question) if question else "empty"
    sections: list[dict] = []
    proposals: list[dict] = []
    method = METHOD
    if not question:
        status, answer, facts, unknowns = (UNKNOWN, "Ask me about the business -- for "
                                           "example: " + "; ".join(SUGGESTED[:4]), [], [])
    elif intent == "identity":
        status, answer, facts, unknowns = _identity_answer()
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
        sections = _sections(db, intent)
        status, answer, unknowns = _compose(intent, sections)
        facts = [f for s in sections for f in s["facts"]]
        proposals = _proposals(intent, sections)

    meta = {"phrased": False}
    if facts and status != UNKNOWN:
        from . import phrasing

        answer, meta = phrasing.phrase(db, answer, gateway=gateway)
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
            "method": method, "phrasing": meta, "speaker": speaker(ident)}


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
    ident = identity_view.identity()
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
                                                   "authority", "source",
                                                   "identity_disagreement")},
            "needs_you": {"status": q["status"], "count": len(q["facts"]),
                          "reason": q.get("reason"), "items": q["facts"][:5]},
            "departments": {"status": d["status"], "reason": d.get("reason"),
                            "by_status": by_status if d["facts"] else None},
            "phase": ph["facts"][0]["statement"] if ph["facts"] else UNKNOWN,
            "suggested": list(SUGGESTED),
            "recent_followons": followon.recent(db, 10),
            "method": METHOD}
