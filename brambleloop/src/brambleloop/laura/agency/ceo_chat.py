"""Business Laura's real conversation in the Command Center (W4-LAURACEO; ADD-LCEO-01/02/03/05/06).

Before this module, `POST /api/cc/laura/ask` answered with `talk.converse`: keyword rules picked
an intent and a fixed template stated the retrieved facts. A greeting matched no rule, fell
through to Ask Company, matched no rule there either, and came back as "UNKNOWN: this
question is not one the company can answer from recorded evidence yet" (and "how are you
today?" matched the keyword `today` and came back as the overnight-jobs template).

Here the model writes the reply and the deterministic machinery becomes its tools:

  RETRIEVE   `talk.converse(persist=False)` -- the same classification, evidence readers, Ask
             Company fallback, delegation parser and authority-checked follow-on proposals --
             plus a headline pack (owner queue, phase, Laura's executive state) so even a
             greeting is grounded; a multi-part briefing request reads the briefing's own
             evidence pack instead (no second model call). The template answer is discarded.
  REMEMBER   the last turns of this owner session (`laura_cc_turns`) and Laura's scoped
             business memory (`laura.memory` relationship tier, `context/conversation/*`)
  ROUTE      cheap tier (`laura.converse`) for conversation; standard tier
             (`laura.executive`) for executive reasoning (priorities, recommendations,
             strategy, delegation, briefings)
  CALL       `gateway.laura_converse.call`: Laura's own CA$0.50/day permission, the purpose
             allocation stop, the month ceiling, an atomic reservation before the request
  VALIDATE   deterministic, and it wins: citations must name offered records; every figure
             in the reply must appear in the evidence, the owner's words, the conversation or
             memory; no claim to be human. A reply that fails is withheld, with the reason.
  PERSIST    the turn (reply, cited facts, unknowns, proposals, method, model) in
             `laura_cc_turns`; its cost in `laura_cost_events`; an optional owner-stated
             preference in her business memory, citing the turn

When the model cannot be called (no key, no permission, allocation spent, parked, provider
error) the owner is told exactly that. No template is ever returned as Laura's reply.

Business register only: `firewall.reject_private` refuses private input, and nothing here
reads or writes the private store (W-VENICE owns Private Laura).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from . import evidence as ev

CHAT = "laura.converse"
EXECUTIVE = "laura.executive"
MAX_QUESTION = 500
HISTORY_TURNS = 6
MAX_EVIDENCE = 60
MAX_REPLY = 2400
MEMORY_PREFIX = "context/conversation/"

UNAVAILABLE = "UNAVAILABLE"
WITHHELD = "WITHHELD"

# Executive reasoning: the question asks for judgement, not a reading of the records.
_EXEC_INTENTS = {"briefing", "briefing_followup", "launch_next", "needs_me", "delegate",
                 "working_on", "money"}
_EXEC_WORDS = re.compile(
    r"\b(should|recommend|priorit|strategy|strategic|plan|focus|decide|decision|trade-?off|"
    r"why|what would you|what do you think|next step|opportunit|risk|delegate|assign|"
    r"improve|fix|budget)\w*", re.I)
_GREETING = re.compile(
    r"^\s*(hi|hello|hey|hiya|good (morning|afternoon|evening)|morning|evening|thanks|"
    r"thank you|cheers|how are you|how's it going|yo)\b", re.I)
_NUM = re.compile(r"\d+(?:[.,:]\d+)*")
_LIST_MARK = re.compile(r"(?m)^\s*\(?\d{1,2}[.)]\s")
_HUMAN = re.compile(r"\bI(?:'m|’m| am) (?:a |an )?(?:human|real person|biological)\b", re.I)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def route(question: str, intent: str) -> str:
    """Which task (and so which tier) answers this turn."""
    q = question or ""
    if _GREETING.match(q) and len(q) < 80 and not _EXEC_WORDS.search(q):
        return CHAT
    if intent in _EXEC_INTENTS or _EXEC_WORDS.search(q) or len(q) > 240:
        return EXECUTIVE
    return CHAT


# ---- tools: deterministic retrieval --------------------------------------------------------


def _headline(db) -> list[dict]:
    """A small always-on pack: what needs the owner, the phase, Laura's own executive state."""
    out: list[dict] = []
    for fn in (ev.owner_queue, ev.phase, ev.executive):
        try:
            sec = fn(db)
        except Exception:  # noqa: BLE001 - a reader never stops the conversation
            continue
        out.extend(sec.get("facts") or [])
    return out[:12]


def _briefing_tool(db, question: str) -> dict:
    from . import briefing

    parsed = briefing.parse(question)
    pack = briefing.evidence_pack(db, window_hours=parsed["window_hours"],
                                  decisions_n=parsed["decisions_n"])
    facts = [{"statement": i["statement"], "source": i["source"], "as_of": i.get("as_of"),
              "link": i.get("link"), "basis": i.get("basis")}
             for i in pack["items"] if i.get("status") != "UNKNOWN"]
    unknowns = [{"section": i.get("section"), "title": i["statement"][:80],
                 "reason": i["statement"][:300]}
                for i in pack["items"] if i.get("status") == "UNKNOWN"]
    return {"intent": "briefing", "status": "ANSWERED" if facts else "UNKNOWN",
            "facts": facts, "unknowns": unknowns,
            "proposals": briefing.proposals(pack)}


def retrieve(db, question: str, session_public_id: str) -> dict:
    """The evidence tools. Their template answers are never the reply."""
    from . import talk

    if talk.classify(question) == "briefing":
        tool = _briefing_tool(db, question)
    else:
        tool = talk.converse(db, question, session_public_id=session_public_id,
                             persist=False)
    facts = list(tool.get("facts") or [])
    seen = {(f.get("statement"), f.get("source")) for f in facts}
    for f in _headline(db):
        if (f.get("statement"), f.get("source")) not in seen:
            facts.append(f)
            seen.add((f.get("statement"), f.get("source")))
    return {"intent": tool.get("intent") or "unknown", "tool_status": tool.get("status"),
            "tool_method": tool.get("method"), "facts": facts[:MAX_EVIDENCE],
            "unknowns": list(tool.get("unknowns") or [])[:12],
            "proposals": [p for p in tool.get("proposals") or [] if isinstance(p, dict)][:8]}


def history(db, session_public_id: str, n: int = HISTORY_TURNS) -> list[dict]:
    from sqlalchemy import select

    from .models import REGISTER, LauraTurn, ensure_tables

    if not session_public_id:
        return []
    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(LauraTurn).where(
            LauraTurn.register == REGISTER,
            LauraTurn.session_public_id == session_public_id[:40])
            .order_by(LauraTurn.id.desc()).limit(n)))
        return [{"q": r.question, "a": r.answer, "id": r.id} for r in reversed(rows)]


def memory(db) -> list[dict]:
    """Laura's scoped business conversation memory (relationship tier, context/conversation/)."""
    try:
        from .. import memory as lm

        rows = lm.read(db, "relationship", MEMORY_PREFIX + "*", lm.Principal.laura(),
                       limit=12)
    except Exception:  # noqa: BLE001 - memory is supplementary
        return []
    out = []
    for e in rows:
        v = e.get("value")
        note = v.get("note") if isinstance(v, dict) else v
        if note:
            out.append({"key": e.get("key"), "note": str(note)[:240],
                        "source": (e.get("sources") or [""])[0]})
    return out


# ---- the prompt values ---------------------------------------------------------------------


def values(question: str, *, ident: dict, hist: list[dict], mem: list[dict], facts: list[dict],
           unknowns: list[dict], proposals: list[dict]) -> dict:
    from ...gateway import laura_converse as lc

    ev_lines = [f"E{i} | {f.get('as_of') or 'UNKNOWN'} | {lc.data(f.get('source'))} | "
                f"{lc.data(str(f.get('statement'))[:260])}" for i, f in enumerate(facts, 1)]
    un_lines = [f"U{i} | {lc.data(u.get('title'))} | {lc.data(str(u.get('reason'))[:200])}"
                for i, u in enumerate(unknowns, 1)]
    pr_lines = [f"P{i} | {p.get('kind')} | {p.get('department')} | {p.get('job_type')} | "
                f"{lc.data(p.get('title'))}" for i, p in enumerate(proposals, 1)]
    hi_lines = []
    for h in hist:
        hi_lines.append(f"Owner: {lc.data(h['q'])[:300]}")
        hi_lines.append(f"Laura: {lc.data(h['a'])[:400]}")
    me_lines = [f"M{i} | {lc.data(m['note'])} | {lc.data(m['source'])}"
                for i, m in enumerate(mem, 1)]
    return {"today": _now().strftime("%Y-%m-%d"),
            "identity": lc.data(f"{ident.get('name')}, {ident.get('role')} "
                                f"(identity {ident.get('identity_id')}); "
                                f"{ident.get('truthful_identity', '')}")[:500],
            "history": lc.block(hi_lines, "(this is the start of the conversation)"),
            "memory": lc.block(me_lines, "(nothing remembered yet)"),
            "evidence": lc.block(ev_lines, "(no records were retrieved)"),
            "unknowns": lc.block(un_lines, "(none)"),
            "proposals": lc.block(pr_lines, "(none)"),
            "question": lc.block([lc.data(question)], "")}


# ---- deterministic validation (wins over the model) ----------------------------------------


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(str(text or ""))}


def validate(data: dict | None, *, question: str, vals: dict, n_facts: int,
             n_props: int) -> tuple[dict | None, str]:
    """(accepted, why_rejected). Every figure must be traceable; citations must exist."""
    if not isinstance(data, dict):
        return None, "the model reply was not a JSON object"
    reply = str(data.get("reply") or "").strip()
    if not reply:
        return None, "the model returned an empty reply"
    if len(reply) > MAX_REPLY:
        return None, f"the reply exceeded {MAX_REPLY} characters"
    if _HUMAN.search(reply):
        return None, "the reply claimed Laura is human (D-FB-12)"
    allowed = set()
    for k in ("evidence", "unknowns", "memory", "history", "proposals", "today", "identity"):
        allowed |= _numbers(vals.get(k, ""))
    allowed |= _numbers(question)
    stated = _numbers(_LIST_MARK.sub(" ", reply))
    extra = sorted(n for n in stated if n not in allowed)
    if extra:
        return None, ("the reply stated figures not found in the records or the conversation: "
                      + ", ".join(extra[:8]))

    def ids(key: str, prefix: str, n: int) -> list[int]:
        out = []
        raw = data.get(key) or []
        for x in raw if isinstance(raw, list) else []:
            m = re.fullmatch(rf"{prefix}(\d+)", str(x).strip())
            if m and 1 <= int(m.group(1)) <= n and int(m.group(1)) not in out:
                out.append(int(m.group(1)))
        return out

    remember = str(data.get("remember") or "").strip()[:240]
    return {"reply": reply, "citations": ids("citations", "E", n_facts),
            "offer": ids("offer", "P", n_props), "remember": remember}, ""


# ---- the turn ------------------------------------------------------------------------------


def _remember(db, turn_id: int, note: str) -> dict:
    from ..private.firewall import reject_private

    try:
        reject_private(note, context="laura.business.memory")
        from .. import memory as lm

        key = MEMORY_PREFIX + hashlib.sha256(note.lower().encode()).hexdigest()[:16]
        e = lm.write(db, "relationship", key, {"note": note, "turn": int(turn_id)},
                     source=[f"laura_cc_turns:{turn_id}"], actor=lm.Principal.laura(),
                     subject=f"Owner-stated business context: {note}"[:200])
        return {"memory_ref": e.get("ref") or f"laura_memory:relationship:{key}"}
    except Exception as exc:  # noqa: BLE001 - memory refusal never undoes the turn
        return {"memory": f"not recorded: {type(exc).__name__}: {str(exc)[:160]}"}


def converse(db, question: str, *, session_public_id: str = "",
             provider_factory=None) -> dict:
    """One owner turn with Business Laura. Persists the turn and its cost; never raises for
    money or provider failure; never returns a template as the reply."""
    from ...gateway import laura_converse as lc
    from ..private.firewall import reject_private
    from . import costs, identity_view
    from .models import REGISTER, LauraTurn, ensure_tables
    from .talk import _iso, speaker

    reject_private(question, context="laura.business")
    ensure_tables(db)
    question = " ".join(str(question or "").split())[:MAX_QUESTION]
    ident = identity_view.identity(db)
    if not question:
        tool = {"intent": "empty", "facts": _headline(db), "unknowns": [], "proposals": []}
    else:
        tool = retrieve(db, question, session_public_id)
    facts, unknowns, proposals = tool["facts"], tool["unknowns"], tool["proposals"]
    task = route(question, tool["intent"])
    hist = history(db, session_public_id)
    mem = memory(db)
    vals = values(question or "(the owner opened the conversation without a message)",
                  ident=ident, hist=hist, mem=mem, facts=facts, unknowns=unknowns,
                  proposals=proposals)
    out = lc.call(db, task, values=vals, provider_factory=provider_factory)
    cited: list[dict] = []
    offered: list[dict] = []
    remember = ""
    model = out.get("model") or ""
    if out["source"] != "model":
        status = UNAVAILABLE
        answer = (f"I can't give you a considered reply right now: {out['reason']}. I won't "
                  "hand you a canned answer in place of one. The records I retrieved for "
                  "your question are attached below as evidence, not as my reply.")
        method = (f"model unavailable ({task}); no reply generated; evidence: deterministic "
                  f"retrieval ({len(facts)} records)")
        cited = facts
    else:
        acc, why = validate(out["data"], question=question, vals=vals, n_facts=len(facts),
                            n_props=len(proposals))
        if acc is None:
            status = WITHHELD
            answer = (f"I drafted a reply but withheld it because {why}. Deterministic "
                      "validation wins over my draft; the records I retrieved are attached "
                      "below. Ask me again or narrow the question.")
            method = f"model {model} via {out['prompt']}; reply withheld by validation"
            cited = facts
        else:
            answer = acc["reply"]
            cited = [facts[i - 1] for i in acc["citations"]]
            offered = [proposals[i - 1] for i in acc["offer"]]
            remember = acc["remember"]
            status = "ANSWERED" if not unknowns else "PARTIAL"
            method = (f"model {model} via {out['prompt']}; grounded in deterministic "
                      f"retrieval ({len(facts)} records offered, {len(cited)} cited)")
    # Authority-checked proposals stay attached whatever the model offered: each still needs
    # the owner's confirmation (and step-up when protected) through `followon.create`.
    stored_props = offered + [p for p in proposals if p not in offered]
    sources = list(dict.fromkeys(str(f.get("source")) for f in cited if f.get("source")))
    with db.session() as s:
        row = LauraTurn(register=REGISTER, session_public_id=session_public_id[:40],
                        question=question, intent=f"ceo:{tool['intent']}"[:40], status=status,
                        answer=answer, facts=cited, sources=sources, unknowns=unknowns,
                        proposals=stored_props, method=method[:200],
                        identity_id=ident["identity_id"])
        s.add(row)
        s.flush()
        turn_id, at = row.id, row.at
    billed = out.get("billed_total_cad", out.get("cost_cad"))
    cost = costs.record(db, "conversation", f"laura_cc_turns:{turn_id}",
                        cost_cad=float(billed or 0.0),
                        basis=("gateway bill (cost_entries)" if out["source"] == "model"
                               or billed else "not_called: no model call was made"),
                        model=model, purpose=out.get("prompt") or "",
                        outcome=status.lower(), detail={"task": task})
    mem_out = _remember(db, turn_id, remember) if remember and status in (
        "ANSWERED", "PARTIAL") else {}
    return {"turn_id": turn_id, "at": _iso(at), "register": REGISTER, "question": question,
            "intent": f"ceo:{tool['intent']}", "status": status, "answer": answer,
            "facts": cited, "sources": sources, "unknowns": unknowns,
            "proposals": stored_props, "method": method,
            "model": {"task": task, "source": out["source"], "model": model or None,
                      "reason": out.get("reason"), "prompt": out.get("prompt")},
            "cost": cost, "memory": mem_out,
            "evidence_offered": len(facts), "speaker": speaker(ident),
            "voice_findings": identity_view.voice_findings(answer)}
