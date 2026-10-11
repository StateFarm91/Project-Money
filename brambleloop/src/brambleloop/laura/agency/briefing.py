"""Laura's CEO briefing (W4-LAURA1): a multi-part owner question, answered part by part.

Production defect fixed here (owner report against 0417f35): the owner asked for a CEO
briefing in six parts and `talk.classify` -- one keyword intent per question -- routed the
whole thing to `needs_me` ("...you need me to decide"), which answers with the owner queue
and nothing else. The other five parts were silently dropped, and no model was involved.

Pipeline, deterministic first:

  parse        which components the question asks for, in the order asked: time window,
               per-department work, first-sale blockers, N owner decisions, verified vs
               unknown, what Laura handles on her own (`parse`)
  evidence     one pack from durable state through the existing readers (`talk`'s `evidence`
               module, the approvals inbox, incidents, products, store, money, spend, phase):
               every item has an id (E#), source, timestamp and a status -- VERIFIED,
               ESTIMATE or UNKNOWN. UNKNOWN is never rendered as 0 (`evidence_pack`)
  decisions    the owner queue's own ranking (`build2.executor.approval_inbox` -> card rank),
               top N, never re-ranked by a model
  proposals    follow-on work only through `followon.proposal` (GREEN missions inside the
               department's charter, or protected work as an owner decision -- never an act)
  synthesis    the model only SELECTS and ORDERS evidence ids per section (plus one
               closed-vocabulary note) through `gateway.laura_briefing` (Laura's own daily
               permission, month ceiling, check-and-reserve); code renders every factual line
               from the records' own statements, and any deviation sends that section back to
               the deterministic text (`validate`, `model_lines`)
  fallback     when the model is unavailable or refused, `compose` answers every requested
               component from the same pack and says plainly that it is the fallback and why
  follow-ups   "expand decision 2" resolves against the stored briefing turn (`followup`)

Business register only: no private/owner-relationship memory is read; any pack item whose
source names a private register is dropped before composition.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import evidence as ev

UNKNOWN = "UNKNOWN"
VERIFIED = "VERIFIED"
ESTIMATE = "ESTIMATE"

COMPONENTS = ("last_window", "departments", "blockers", "decisions", "facts_unknowns",
              "autonomous")
MAX_ITEMS = 5
MAX_LINE = 170
MAX_ANSWER_CHARS = 4500
METHOD_FALLBACK = "deterministic briefing composer over the evidence pack (fallback)"
METHOD_MODEL = "model synthesis via gateway {ref} ({model}) over the evidence pack, validated"

_BRIEFING_WORDS = re.compile(
    r"\b(ceo )?(briefing|brief me|debrief|sitrep|status report|state of the (company|business)"
    r"|executive summary|rundown)\b")
_PATTERNS: dict[str, re.Pattern] = {
    "last_window": re.compile(
        r"last \d+ ?(h\b|hours?|days?)|last (twenty[- ]four|twenty four) hours|last day|"
        r"past (day|\d+ hours)|overnight|accomplish|what happened|since yesterday|"
        r"what (did )?(we|you|the company|brambleloop) (do|did|get done)"),
    "departments": re.compile(r"department|each team|every team|the teams|"
                              r"(are|is) (you |they |everyone )?working on|busy with"),
    "blockers": re.compile(r"block|prevent|stopping (us|our)|in the way|obstacle|"
                           r"first (etsy )?sale|holding (us|it) back|"
                           r"(not|n't|never) (yet )?sell|no sales|(not|n't) (making|getting) "
                           r"(any )?(sales|money)"),
    "decisions": re.compile(r"decision|\bdecide|needs? me\b|needs? my|approv|sign[- ]off"),
    "facts_unknowns": re.compile(r"verified|unknowns?\b|facts? (vs|versus|from|and)|"
                                 r"what you (know|don't know)|separate"),
    "autonomous": re.compile(r"without (my|me)\b|on your own|handle (it |that )?(yourself|"
                             r"alone)|you can handle|next steps?|you will do next|"
                             r"autonom|by yourself"),
}
_TOPICAL = re.compile(r"\b(of|on|about|for) (the |our |my |your )?(store|shop|storefront|"
                      r"revenue|money|sales|seo|search|products?|visual|ads|finance|books|"
                      r"listings?|banner|brand)\b")
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "top": 0}
_N_DECISIONS = re.compile(
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s+[a-z'-]+){0,3}?"
    r"\s+(decisions?|things|items|priorities|choices|calls)\b")

TITLES = {
    "last_window": "What we accomplished in the last {h} hours",
    "departments": "What each department is working on",
    "blockers": "What is preventing our first Etsy sale",
    "decisions": "The {n} decisions I need from you, ranked",
    "facts_unknowns": "Verified facts vs unknowns",
    "autonomous": "What I can handle without you",
}


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().replace("’", "'").split())


def parse(question: str) -> dict:
    """{is_briefing, components (in the order asked), window_hours, decisions_n, concise}."""
    q = _norm(question)
    found: list[tuple[int, str]] = []
    for comp, rx in _PATTERNS.items():
        m = rx.search(q)
        if m:
            found.append((m.start(), comp))
    comps = [c for _, c in sorted(found)]
    named = bool(_BRIEFING_WORDS.search(q))
    # Review LOW-1: "a rundown of the store" / "status report on revenue" is a topical
    # question, not a six-part briefing; the topical intent answers it. Round 2: a topic plus
    # any asked-for part ("a CEO briefing on the store and the decisions you need") is a
    # briefing on both -- the store/money topic is answered by the section that holds it.
    t = _TOPICAL.search(q)
    if named and t and comps:
        topic_comp = ("facts_unknowns" if re.search(r"revenue|money|sales|finance|books",
                                                    t.group(0)) else "blockers")
        if topic_comp not in comps:
            found.append((t.start(), topic_comp))
            comps = [c for _, c in sorted(found)]
    topical = bool(t) and len(comps) < 2
    # Review MEDIUM-2: two or more asked-for parts are answered part by part (never collapsed
    # onto one single-keyword intent); a briefing word with fewer parts means the full briefing.
    is_briefing = ((named and bool(q)) and not topical) or len(comps) >= 2
    if named and not topical and len(comps) < 2:
        comps = list(COMPONENTS)
    window = 24
    m = re.search(r"last (\d{1,3}) ?(h\b|hours?)", q)
    if m:
        window = max(1, min(int(m.group(1)), 168))
    elif re.search(r"last (\d{1,2}) days?", q):
        window = max(1, min(int(re.search(r"last (\d{1,2}) days?", q).group(1)), 7)) * 24
    elif re.search(r"this week|past week|last week", q):
        window = 168
    n = 5
    m = _N_DECISIONS.search(q)
    if m and "decisions" in comps:
        n = int(m.group(1)) if m.group(1).isdigit() else _WORDS.get(m.group(1), 5) or 5
    return {"is_briefing": is_briefing, "components": comps, "window_hours": window,
            "decisions_n": max(1, min(n, 10)), "concise": "concise" in q or "brief" in q}


# ---- the evidence pack ------------------------------------------------------------------

# Any source or section naming a private register (or spouse context) is dropped: the
# briefing reads business state only, and this is the belt to that brace.
_PRIVATE_MARKERS = ("private", "spouse", "spousal")


def _is_private(item: dict) -> bool:
    blob = f"{item.get('source', '')} {item.get('section', '')}".lower()
    return any(m in blob for m in _PRIVATE_MARKERS)


def _status(f: dict) -> str:
    basis = str(f.get("basis") or "unknown")
    if UNKNOWN in str(f.get("statement") or "") or basis == "unknown":
        return UNKNOWN
    if basis in ("modelled", "estimated"):
        return ESTIMATE
    return VERIFIED


class _Pack:
    def __init__(self):
        self.items: list[dict] = []
        self.sections: dict[str, dict] = {}

    def add(self, statement: str, source: str, components, *, section: str, as_of=None,
            status: str | None = None, basis: str = "measured", **extra) -> dict:
        f = ev.fact(statement, source, as_of=as_of, basis=basis)
        item = {"id": f"E{len(self.items) + 1}", "components": list(components),
                "section": section, "statement": f["statement"], "source": f["source"],
                "as_of": f["as_of"], "link": f["link"], "basis": f["basis"],
                "status": status or _status(f), **extra}
        if _is_private(item):
            return {}
        self.items.append(item)
        return item

    def section(self, sec: dict, components, *, limit: int = 8, keep=None) -> list[dict]:
        """Add a reader section's facts (or one UNKNOWN item naming why it has none)."""
        self.sections[sec["key"]] = sec
        out = []
        facts = [f for f in sec.get("facts") or [] if keep is None or keep(f)]
        for f in facts[:limit]:
            it = self.add(f["statement"], f["source"], components, section=sec["key"],
                          as_of=f.get("as_of"), basis=f.get("basis") or "measured")
            if it:
                out.append(it)
        if not sec.get("facts"):
            src = (sec.get("sources") or [sec["key"]])[0]
            it = self.add(f"{sec['title']}: UNKNOWN -- {sec.get('reason') or 'no evidence'}",
                          src, components, section=sec["key"], status=UNKNOWN,
                          basis="unknown")
            if it:
                out.append(it)
        return out

    def by_id(self) -> dict[str, dict]:
        return {i["id"]: i for i in self.items}


def _cost_text(v) -> str:
    return f"max cost CA${float(v):.2f}" if isinstance(v, (int, float)) else \
        "max cost UNKNOWN"


def _decision_candidates(db) -> tuple[list[dict], str | None]:
    """The owner queue's own ranking: approvals inbox cards by `rank`, then Laura's own
    catalogue owner action (whose cost is UNKNOWN). Returns (cards, unreadable_reason)."""
    from ...app.command_center import approvals

    try:
        box = approvals.inbox(db)
    except Exception as exc:  # noqa: BLE001
        return [], f"owner queue unreadable: {type(exc).__name__}"
    cards = list(box.get("cards") or [])
    indexed = list(enumerate(cards))
    indexed.sort(key=lambda ic: (ic[1].get("rank") is None,
                                 ic[1].get("rank") if isinstance(ic[1].get("rank"), int)
                                 else 0, ic[0]))
    out = [c for _, c in indexed]
    try:
        from . import voice_selection

        a = voice_selection.OWNER_ACTION
        out.append({"card_id": "laura:voice_selection", "title": a["action"],
                    "max_spend_cad": None, "minutes": a.get("minutes"),
                    "consequence_of_no_action": a.get("consequence_of_waiting"),
                    "sources": ["laura.agency.voice_selection.OWNER_ACTION"]})
    except Exception:  # noqa: BLE001
        pass
    return out, (box.get("reason") if box.get("status") == UNKNOWN else None)


# Review LOW-2: refusals, access reads and security bookkeeping are audit noise, not company
# accomplishments (and can carry session ids); they never enter the "accomplished" section.
_AUDIT_NOISE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*\.(refused|denied|read|viewed|accessed|"
                          r"rejected|refusal|login|logout|session\w*|step_?up)\b|"
                          r"PermissionRefused|Refused\b|owner:p\w*|\bsession\b|security",
                          re.I)


_ETSY_WORDS = re.compile(r"etsy|listing|publication|publish|transactions_r|shop|marketplace|"
                         r"order|receipt", re.I)


def evidence_pack(db, *, window_hours: int = 24, decisions_n: int = 5) -> dict:
    """Every item the briefing may say, with id, source, timestamp and status."""
    from ...app.command_center import readers

    p = _Pack()
    # 1. last window
    p.section(ev.overnight(db, window_hours), ["last_window"], limit=8,
              keep=lambda f: not _AUDIT_NOISE.search(f["statement"]))
    # 2. departments: status + queued missions/open jobs + Laura's own priorities
    dep = ev.departments(db)
    dep_items = p.section(dep, ["departments"], limit=12)
    p.section(ev.working_on(db), ["departments", "autonomous"], limit=8)
    p.section(ev.executive(db), ["departments", "autonomous"], limit=5)
    # 3. first-sale blockers
    prod = ev.products(db)
    p.section(prod, ["blockers"], limit=4)
    p.section(ev.phase(db), ["blockers"], limit=1)
    store = ev.store(db)
    p.section(store, ["blockers"], limit=6,
              keep=lambda f: not re.search(r": (READY|OK|PASS)\b", f["statement"]))
    try:
        inc = readers.incidents(db, limit=10)
        for i in inc.get("items") or []:
            if i.get("halts_publication") or i.get("severity") in ("P0", "P1"):
                p.add(f"open {i['severity']} incident"
                      + (" (halts publication)" if i.get("halts_publication") else "")
                      + f": {i['summary'][:160]}", i["source"], ["blockers"],
                      section="incidents", as_of=i.get("at"))
    except Exception as exc:  # noqa: BLE001
        p.add(f"Incidents: UNKNOWN -- unreadable ({type(exc).__name__})", "incidents",
              ["blockers"], section="incidents", status=UNKNOWN, basis="unknown")
    for it in dep_items:
        if "blocked by" in it["statement"] and re.search(r"store|commerce|finance|support",
                                                          it["statement"], re.I):
            it["components"].append("blockers")
    # money: revenue/profit (UNKNOWN until measured) + recorded spend
    money = ev.money(db)
    p.section(money, ["blockers", "facts_unknowns"], limit=6,
              keep=lambda f: re.match(r"(Revenue|Net sales|Profit|reconciled revenue|profit|"
                                      r"recorded spend|Operating spend)", f["statement"])
              is not None)
    try:
        from ...gateway import laura_briefing, routing

        b = routing.budget(db)
        p.add(f"model/image spend this month: CA${b.spent_cad:.2f} of the CA${b.ceiling_cad:.2f}"
              f" monthly ceiling", "cost_entries (gateway.routing.budget)",
              ["facts_unknowns"], section="spend")
        perm = laura_briefing.laura_daily_permission(db)
        p.add(f"Laura's authorised daily model budget: CA${perm:.2f}"
              + (" (none authorised: model synthesis is off)" if perm <= 0 else ""),
              "agents.registry:laura (daily_cost_ceiling_cad)", ["facts_unknowns"],
              section="spend")
    except Exception as exc:  # noqa: BLE001
        p.add(f"Spend: UNKNOWN -- unreadable ({type(exc).__name__})", "cost_entries",
              ["facts_unknowns"], section="spend", status=UNKNOWN, basis="unknown")
    # 4. decisions -- the queue's own ranking, top N
    cards, why = _decision_candidates(db)
    decisions: list[dict] = []
    for c in cards[:decisions_n]:
        mins = c.get("minutes")
        stmt = (f"{c.get('title') or 'an owner decision'} -- {_cost_text(c.get('max_spend_cad'))}"
                f"; about {mins if isinstance(mins, int) and mins > 0 else UNKNOWN} min; if it "
                f"waits: {c.get('consequence_of_no_action') or 'not stated'}")
        it = p.add(stmt, (c.get("sources") or ["owner_actions"])[-1], ["decisions"],
                   section="owner_queue", basis="measured",
                   card_id=c.get("card_id"), decision_rank=len(decisions) + 1)
        if it:
            it["status"] = VERIFIED      # the card exists; its own UNKNOWN cost stays in text
            decisions.append({"rank": it["decision_rank"], "evidence_id": it["id"],
                              "card_id": c.get("card_id"), "statement": stmt,
                              "etsy": bool(_ETSY_WORDS.search(stmt))})
            if _ETSY_WORDS.search(str(c.get("title") or "")):
                it["components"].append("blockers")
    if why:
        p.add(f"Owner queue: UNKNOWN -- {why}", "build2.executor.approval_inbox",
              ["decisions"], section="owner_queue", status=UNKNOWN, basis="unknown")
    return {"items": p.items, "decisions": decisions, "open_decisions": len(cards),
            "sections": p.sections, "window_hours": window_hours,
            "products": (prod.get("items") or []), "store_status": store.get("status"),
            "as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


# ---- follow-on work within authority ----------------------------------------------------


def proposals(pack: dict) -> list[dict]:
    """GREEN missions Laura may start on confirmation, and protected work as owner decisions.
    Every proposal is built by `followon.proposal`, which refuses anything outside authority."""
    from . import followon

    items = pack["items"]

    def srcs(*sections):
        return [i["source"] for i in items if i["section"] in sections][:8]

    cands = [
        ("executive", "autonomy.morning_handoff", "Write a fresh company brief",
         "re-read jobs, costs, incidents and owner actions into tomorrow's brief",
         ("overnight", "departments")),
        ("store_commerce", "autonomy.department_review", "Have Store / Commerce review itself",
         f"store reads {pack.get('store_status') or UNKNOWN}; review it against its KPIs",
         ("store", "products")),
        ("store_commerce", "seo.cycle", "Run a store search (SEO) cycle",
         "keep the listing plans search-ready for the first sale", ("store",)),
        ("finance", "finance.accounting.cycle", "Refresh the books (accounting cycle)",
         "re-post and re-read the ledger so money figures are current", ("money", "spend")),
        ("learn", "improve.mine", "Mine recent failures for improvements",
         "turn incidents, refusals and dead letters into lessons", ("incidents", "overnight")),
    ]
    out = []
    for dept, jt, title, why, secs in cands:
        prop = followon.proposal(dept, jt, title, why, srcs(*secs) or [f"autonomy.charters:{dept}"])
        if prop is not None:
            out.append(prop)
    for it in pack.get("products") or []:
        if it.get("certified") and not it.get("on_etsy"):
            prop = followon.proposal("store_commerce", "store.publish",
                                     f"Decide whether to publish {it['slug']}",
                                     f"{it['slug']} has a certified release and is not on Etsy",
                                     list(it.get("sources") or [])[:5] or ["products"],
                                     subject=it["slug"])
            if prop is not None:
                out.append(prop)
            break
    for i, prop in enumerate(out, 1):
        prop["pid"] = f"P{i}"
    return out


# ---- deterministic composer -------------------------------------------------------------


def _clip(text: str, n: int = MAX_LINE) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _line(text: str, refs: list[str]) -> str:
    return f"- {_clip(text)} [{', '.join(refs)}]"


def _for(pack: dict, comp: str) -> list[dict]:
    return [i for i in pack["items"] if comp in i["components"]]


_BLOCKER_ORDER = (r"incident", r"0 are on Etsy|on Etsy", r"not certified", r"SHADOW",
                  r"NEEDS_OWNER|FAIL|GATED", r"blocked by", r"Revenue|revenue|sales")


def blockers(pack: dict) -> list[dict]:
    """Blocker evidence, most fundamental first, at most five."""
    items = [i for i in _for(pack, "blockers") if i["section"] != "owner_queue"
             and not re.match(r"(recorded spend|Operating spend|Profit|profit)",
                              i["statement"])]

    def key(i):
        for n, rx in enumerate(_BLOCKER_ORDER):
            if re.search(rx, i["statement"]):
                return n
        return len(_BLOCKER_ORDER)

    items.sort(key=key)
    out, seen = [], set()
    for i in items:
        k = i["statement"][:60]
        if k in seen or re.search(r"store surfaces: ", i["statement"]) and len(out) >= 4:
            continue
        seen.add(k)
        out.append(i)
        if len(out) >= MAX_ITEMS:
            break
    return out


_VERIFIED_ORDER = ("overnight", "products", "phase", "money", "spend", "owner_queue",
                   "departments")
_UNKNOWN_ORDER = ("money", "spend", "owner_queue", "incidents", "overnight", "working_on",
                  "executive", "store", "products", "departments")


def _deterministic_lines(pack: dict, comp: str, props: list[dict], n: int) -> list[str]:
    if comp == "last_window":
        items = _for(pack, "last_window")
        return [_line(i["statement"] if i["status"] != UNKNOWN else
                      i["statement"], [i["id"]]) for i in items[:MAX_ITEMS]]
    if comp == "departments":
        items = _for(pack, "departments")
        busy = [i for i in items if not re.search(r": UNKNOWN, 0 job", i["statement"])]
        idle = [i for i in items if i not in busy]
        lines = [_line(i["statement"], [i["id"]]) for i in busy[:6]]
        if idle:
            names = [re.split(r":", i["statement"])[0] for i in idle]
            lines.append(_line(f"No recorded activity in the window (status UNKNOWN): "
                               f"{', '.join(names)}", [i["id"] for i in idle][:8]))
        return lines
    if comp == "blockers":
        b = blockers(pack)
        etsy_dec = [d for d in pack["decisions"] if d["etsy"]]
        lines = [_line(i["statement"], [i["id"]]) for i in b]
        if etsy_dec:
            lines.append(_line("Also waiting on you (see decisions): " + "; ".join(
                f"#{d['rank']}" for d in etsy_dec), [d["evidence_id"] for d in etsy_dec]))
        return lines or ["- UNKNOWN: no blocker evidence could be read"]
    if comp == "decisions":
        decs = pack["decisions"][:n]
        lines = [f"{d['rank']}. {_clip(d['statement'])} [{d['evidence_id']}]" for d in decs]
        if len(decs) < n:
            lines.append(f"- Only {len(decs)} owner decision(s) are open in the queue; I won't "
                         f"invent the rest.")
        return lines
    if comp == "facts_unknowns":
        ver_all = [i for i in pack["items"] if i["status"] == VERIFIED]
        unk = [i for i in pack["items"] if i["status"] == UNKNOWN]
        est = [i for i in pack["items"] if i["status"] == ESTIMATE]
        ver, seen = [], set()
        for sec in _VERIFIED_ORDER:            # one most-material verified fact per source
            hit = next((i for i in ver_all if i["section"] == sec), None)
            if hit and sec not in seen:
                seen.add(sec)
                ver.append(hit)
        unk.sort(key=lambda i: (_UNKNOWN_ORDER.index(i["section"])
                                if i["section"] in _UNKNOWN_ORDER else len(_UNKNOWN_ORDER)))
        lines = [f"Verified ({len(ver_all)} records, each with a source and timestamp); "
                 f"the most material:"]
        lines += [_line(_clip(i["statement"], 140), [i["id"]]) for i in ver[:4]]
        lines.append(f"Unknown ({len(unk)} records; UNKNOWN is never shown as zero); "
                     f"the most material:")
        lines += [_line(_clip(i["statement"] if UNKNOWN in i["statement"] else
                              f"UNKNOWN: {i['statement']}", 140), [i["id"]]) for i in unk[:4]]
        if est:
            lines.append(_line(f"{len(est)} record(s) are estimates or models, not "
                               f"measurements", [i["id"] for i in est][:5]))
        return lines
    if comp == "autonomous":
        lines = []
        for prop in [x for x in props if x["kind"] == "mission"][:4]:
            lines.append(_line(f"{prop['title']} ({prop['department']}): {prop['why']}",
                               [prop["pid"]]))
        wip = [i for i in _for(pack, "autonomous") if i["status"] != UNKNOWN]
        if wip:
            lines.append(_line("Already running without you: " + "; ".join(
                i["statement"] for i in wip[:3]), [i["id"] for i in wip[:3]]))
        if lines:
            lines.append("  All internal GREEN work inside each department's charter: confirm "
                         "a step and it is queued. No publishing, spending, pricing or customer "
                         "contact.")
        prot = [x for x in props if x["kind"] != "mission"]
        for prop in prot[:2]:
            lines.append(_line(f"Not mine to do: {prop['title']} is protected "
                               f"({prop['job_type']}), so it stays your decision",
                               [prop["pid"]]))
        return lines or ["- UNKNOWN: no follow-on work is within my authority right now"]
    return []


def _header(window: int, as_of: str) -> str:
    return f"Here's where Brambleloop stands (last {window} h, as of {as_of})."


def compose(pack: dict, parsed: dict, props: list[dict], *, mode_line: str,
            lines_by_comp: dict[str, list[str]] | None = None) -> str:
    """The sectioned briefing, in the order asked. `lines_by_comp` (validated model lines)
    overrides the deterministic lines component by component."""
    n, window = parsed["decisions_n"], parsed["window_hours"]
    parts = [_header(window, pack["as_of"]), mode_line]
    for k, comp in enumerate(parsed["components"], 1):
        title = TITLES[comp].format(h=window, n=n)
        lines = (lines_by_comp or {}).get(comp) or _deterministic_lines(pack, comp, props, n)
        parts.append(f"\n{k}. {title}\n" + "\n".join(lines))
    parts.append("\nAsk \"expand decision 2\" (or blocker / step N) for the detail behind any "
                 "line; every [E#] is a record you can open.")
    text = "\n".join(parts)
    if len(text) > MAX_ANSWER_CHARS:
        text = text[: MAX_ANSWER_CHARS - 40].rstrip() + "\n… (trimmed for length)"
    return text


# ---- the model's contract: select and order, never assert ---------------------------------
#
# Round-2 review (INDEPENDENT_REVIEW_LAURA1.md, 5dcb6c0): validating free prose with keyword
# rules keeps losing to rephrasing. So the model no longer writes claims at all. Per section it
# may only
#   * SELECT and ORDER evidence ids (E#, or P# for the autonomy section) that belong to that
#     section, and
#   * add ONE short note built only from `NOTE_VOCABULARY` -- a closed list of connective and
#     framing words with no numbers, no events (sale, listing, launch, order...) and no action
#     verbs (publish, price, spend, contact...).
# Every factual line the owner sees is rendered by code from the selected record's own
# statement text. The decision section is always the owner queue's cards, verbatim, in queue
# order; the VERIFIED / UNKNOWN listing and the authority boundary are always code-rendered.
# Anything else in a section -- an unknown or foreign id, free text, a word outside the
# vocabulary, a digit -- and that whole section falls back to the deterministic text.

NOTE_MAX_WORDS = 20
NOTE_MAX_CHARS = 140
NOTE_VOCABULARY = frozenset("""
a all also an and are as at below briefly by each first focus for from have here i in is it
its key line lines main matter matters most my next note of on order our overall picture
plainly point points priority read record records remain remains short so source sources
stand stands start still summary that the then these this those to top unknown unknowns
verified view what where worth yet your attention open known not ranked listed importance
""".split())


def note_problem(note) -> str | None:
    """Why a model note is not allowed, or None. Closed vocabulary; no digits."""
    if note is None or note == "":
        return None
    if not isinstance(note, str):
        return "note is not text"
    if len(note) > NOTE_MAX_CHARS:
        return f"note longer than {NOTE_MAX_CHARS} characters"
    if re.search(r"\d", note):
        return "note contains a number"
    if re.search(r"[^A-Za-z ,.;:'\-]", note):
        return "note contains characters outside plain words"
    words = re.findall(r"[a-z']+", note.lower())
    if len(words) > NOTE_MAX_WORDS:
        return f"note longer than {NOTE_MAX_WORDS} words"
    outside = sorted({w for w in words if w not in NOTE_VOCABULARY})
    if outside:
        return f"note uses words outside the closed vocabulary: {outside[:5]}"
    return None


def _allowed_ids(comp: str, pack: dict, props: list[dict], n: int) -> set[str]:
    if comp == "decisions":
        return {d["evidence_id"] for d in pack["decisions"][:n]}
    if comp == "autonomous":
        return ({p["pid"] for p in props if p["kind"] == "mission"}
                | {i["id"] for i in _for(pack, "autonomous") if i["status"] != UNKNOWN})
    return {i["id"] for i in _for(pack, comp)}


def validate(data, pack: dict, parsed: dict, props: list[dict]
             ) -> tuple[dict[str, dict], list[dict]]:
    """({component: {"ids": [...], "note": str}}, rejected [{component, reason}]).

    Section-level and deterministic: a section is accepted only if it is exactly
    {component, evidence: [ids allowed for that section], note: closed-vocabulary text}."""
    accepted: dict[str, dict] = {}
    rejected: list[dict] = []
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list):
        return {}, [{"component": "*", "reason": "no sections list"}]
    n = parsed["decisions_n"]
    for sec in sections:
        comp = sec.get("component") if isinstance(sec, dict) else None
        if comp not in parsed["components"]:
            rejected.append({"component": str(comp), "reason": "component not requested"})
            continue
        if comp in accepted:
            rejected.append({"component": comp, "reason": "component given twice"})
            accepted.pop(comp)
            continue
        extra = sorted(set(sec) - {"component", "evidence", "note"})
        if extra:
            rejected.append({"component": comp,
                             "reason": f"fields outside the contract: {extra} (the model may "
                                       f"only select evidence ids and add one note)"})
            continue
        ids = sec.get("evidence")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            rejected.append({"component": comp, "reason": "no evidence ids selected"})
            continue
        ids = [i.strip() for i in ids]
        allowed = _allowed_ids(comp, pack, props, n)
        bad = [i for i in ids if i not in allowed]
        if bad:
            rejected.append({"component": comp,
                             "reason": f"ids not in this section's evidence: {bad[:4]}"})
            continue
        if len(set(ids)) != len(ids):
            rejected.append({"component": comp, "reason": "an id is selected twice"})
            continue
        why = note_problem(sec.get("note"))
        if why:
            rejected.append({"component": comp, "reason": why})
            continue
        accepted[comp] = {"ids": ids[:MAX_ITEMS + 3], "note": (sec.get("note") or "").strip()}
    return accepted, rejected


def model_lines(accepted: dict[str, dict], pack: dict, parsed: dict,
                props: list[dict] | None = None) -> dict:
    """Render accepted selections. Every factual line is a record's own statement."""
    props = props or []
    by_id = {i["id"]: i for i in pack["items"]}
    pmap = {p["pid"]: p for p in props}
    n = parsed["decisions_n"]
    out: dict[str, list[str]] = {}
    for comp, sel in accepted.items():
        note = [f"  {sel['note']}"] if sel["note"] else []
        if comp in ("decisions", "facts_unknowns"):
            # queue order / record status are never the model's: note only
            out[comp] = note + _deterministic_lines(pack, comp, props, n)
            continue
        lines = []
        for i in sel["ids"][:MAX_ITEMS + (1 if comp == "departments" else 0)]:
            if i in pmap:
                p = pmap[i]
                lines.append(_line(f"{p['title']} ({p['department']}): {p['why']}", [i]))
            else:
                lines.append(_line(by_id[i]["statement"], [i]))
        if comp == "autonomous":
            lines += [x for x in _deterministic_lines(pack, comp, props, n)
                      if "All internal GREEN" in x or "Not mine to do" in x]
        out[comp] = note + lines
    return out


# ---- the answer -------------------------------------------------------------------------


def answer(db, question: str, parsed: dict | None = None, *, provider_factory=None) -> dict:
    """{status, answer, facts, unknowns, proposals, sections, method, synthesis}."""
    from ...gateway import laura_briefing

    parsed = parsed or parse(question)
    pack = evidence_pack(db, window_hours=parsed["window_hours"],
                         decisions_n=parsed["decisions_n"])
    props = proposals(pack)
    values = laura_briefing.render_values(
        question=question, components=parsed["components"],
        window_hours=parsed["window_hours"], decisions_n=parsed["decisions_n"],
        pack=pack["items"], decisions=pack["decisions"][:parsed["decisions_n"]],
        proposals=props)
    out = laura_briefing.synthesize(db, values=values, provider_factory=provider_factory)
    rejected: list[dict] = []
    lines = None
    if out["source"] == "model":
        accepted, rejected = validate(out["data"], pack, parsed, props)
        lines = model_lines(accepted, pack, parsed, props)
        filled = [c for c in parsed["components"] if not lines.get(c)]
        mode = ("Written with model synthesis: the model chose and ordered the evidence; "
                "every factual line is the record's own text"
                + (f"; {len(filled)} section(s) fell back to my deterministic text"
                   f" ({', '.join(filled)})" if filled else "") + ".")
        method = METHOD_MODEL.format(ref=laura_briefing.PROMPT.ref, model=out["model"])
    else:
        mode = (f"Model synthesis unavailable: {out['reason']}. This is my deterministic "
                f"fallback briefing, built only from the evidence records cited below.")
        method = f"{METHOD_FALLBACK}; model synthesis unavailable: {out['reason']}"
    text = compose(pack, parsed, props, mode_line=mode, lines_by_comp=lines)
    unknowns = [{"section": i["section"], "title": i["id"], "reason": i["statement"][:300]}
                for i in pack["items"] if i["status"] == UNKNOWN]
    facts = [{k: i[k] for k in ("id", "statement", "source", "as_of", "link", "basis",
                                "status", "components", "section")}
             | ({"card_id": i["card_id"], "decision_rank": i["decision_rank"]}
                if "decision_rank" in i else {}) for i in pack["items"]]
    blk = blockers(pack)
    for f in facts:
        for r, b in enumerate(blk, 1):
            if f["id"] == b["id"]:
                f["blocker_rank"] = r
    return {"status": "ANSWERED" if not unknowns else "PARTIAL", "answer": text,
            "facts": facts, "unknowns": unknowns, "proposals": props,
            "sections": [{"key": c, "title": TITLES[c].format(h=parsed["window_hours"],
                                                              n=parsed["decisions_n"]),
                          "status": "OK", "reason": None,
                          "facts": len(_for(pack, c))} for c in parsed["components"]],
            "method": method[:200],
            "synthesis": {"source": out["source"], "reason": out["reason"],
                          "model": out.get("model"), "cost_cad": out.get("cost_cad", 0.0),
                          "rejected": rejected, "components": parsed["components"],
                          "window_hours": parsed["window_hours"],
                          "decisions_n": parsed["decisions_n"]}}


# ---- follow-ups against the stored briefing ---------------------------------------------

# Review LOW-3: anchored at the start of a short message, so an ordinary question that
# merely mentions "step 2" is not hijacked as a follow-up.
_FOLLOW = re.compile(
    r"^(laura[,:]?\s+)?(please\s+)?(can you\s+|could you\s+)?(expand( on)?|more on|"
    r"more about|tell me more( about)?|explain|elaborate( on)?|unpack|go deeper( on)?|"
    r"what about|why)\s+(on\s+)?(the\s+|your\s+)?(?P<kind>decision|blocker|step|proposal)s?"
    r"\s*(?:#|no\.?|number)?\s*(?P<n>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|"
    r"ten)\b[\s?.!]*$")


def parse_followup(question: str) -> tuple[str, int] | None:
    m = _FOLLOW.search(_norm(question))
    if not m:
        return None
    num = m.group("n")
    n = int(num) if num.isdigit() else _WORDS.get(num, 0)
    kind = "step" if m.group("kind") == "proposal" else m.group("kind")
    return (kind, n) if n > 0 else None


def last_briefing(db, session_public_id: str):
    from sqlalchemy import select

    from .models import REGISTER, LauraTurn, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = s.scalar(select(LauraTurn).where(
            LauraTurn.register == REGISTER, LauraTurn.intent == "briefing",
            LauraTurn.session_public_id == (session_public_id or "")[:40])
            .order_by(LauraTurn.id.desc()).limit(1))
        if row is None:
            return None
        return {"turn_id": row.id, "at": row.at, "facts": list(row.facts or []),
                "proposals": list(row.proposals or [])}


def followup(db, question: str, session_public_id: str) -> dict | None:
    """Resolve "expand decision 2" (blocker N, step N) against the previous briefing turn in
    this session. None when the question is not such a follow-up or no briefing exists."""
    ref = parse_followup(question)
    if ref is None:
        return None
    prev = last_briefing(db, session_public_id)
    if prev is None:
        return None
    kind, n = ref
    at = ev._iso(prev["at"]) if prev["at"] else UNKNOWN
    facts = prev["facts"]
    if kind == "decision":
        item = next((f for f in facts if f.get("decision_rank") == n), None)
        if item is None:
            k = sum(1 for f in facts if f.get("decision_rank"))
            return _fu(prev, f"UNKNOWN: my briefing (turn {prev['turn_id']}) ranked {k} "
                             f"decision(s); there is no decision {n}.", [], UNKNOWN)
        detail = _card_detail(db, item.get("card_id"))
        lines = [f"Decision {n} from my briefing at {at} (turn {prev['turn_id']}): "
                 f"{item['statement']} [{item['id']}]"]
        if detail is None:
            lines.append("It is no longer open in the owner queue, so it may already be "
                         "settled; nothing else is known about it here.")
        else:
            for label, key in (("Why it is yours", "why_software_cannot"),
                               ("Recommendation", "recommendation"),
                               ("What you'd do", "proposed_action"),
                               ("Reversible?", "reversibility"),
                               ("If it waits", "consequence_of_no_action"),
                               ("Uncertainty", "uncertainty")):
                v = detail.get(key)
                if v:
                    lines.append(f"- {label}: {_clip(v, 300)}")
            if detail.get("unblocks"):
                lines.append(f"- It un-parks {len(detail['unblocks'])} requirement(s).")
            lines.append("- You decide it in Approvals; I can't act on it myself.")
        cited = [item] + ([] if detail is None else [ev.fact(
            f"owner queue card {item.get('card_id')}", "build2.executor.approval_inbox")])
        return _fu(prev, "\n".join(lines), cited, "ANSWERED")
    if kind == "blocker":
        item = next((f for f in facts if f.get("blocker_rank") == n), None)
        if item is None:
            return _fu(prev, f"UNKNOWN: my briefing (turn {prev['turn_id']}) has no blocker "
                             f"{n}.", [], UNKNOWN)
        related = [f for f in facts if f.get("section") == item.get("section")
                   and f["id"] != item["id"]][:4]
        lines = [f"Blocker {n} from my briefing at {at}: {item['statement']} [{item['id']}] "
                 f"(source {item['source']}, as of {item.get('as_of') or UNKNOWN}; "
                 f"{item.get('status')})."]
        for f in related:
            lines.append(f"- Related: {_clip(f['statement'])} [{f['id']}]")
        return _fu(prev, "\n".join(lines), [item] + related, "ANSWERED")
    props = prev["proposals"]
    prop = next((p for p in props if p.get("pid") == f"P{n}"), None) or (
        props[n - 1] if 0 < n <= len(props) else None)
    if prop is None:
        return _fu(prev, f"UNKNOWN: my briefing (turn {prev['turn_id']}) has no step {n}.", [],
                   UNKNOWN)
    if prop.get("kind") == "mission":
        text = (f"Step {n}: {prop['title']} -- {prop['why']}. It is internal GREEN work for "
                f"{prop['department']} ({prop['job_type']}); confirm it as a follow-on on turn "
                f"{prev['turn_id']} and it goes on their queue. No publishing, spending or "
                f"customer contact.")
    else:
        text = (f"Step {n}: {prop['title']} is protected ({prop['job_type']}); I can only "
                f"record it as your decision after step-up, and the act itself needs its own "
                f"grant.")
    cited = [ev.fact(f"proposal {prop.get('key')}", s) for s in (prop.get("evidence") or [])[:3]]
    return _fu(prev, text, cited, "ANSWERED", proposals=[prop])


def _card_detail(db, card_id) -> dict | None:
    if not card_id:
        return None
    if card_id == "laura:voice_selection":
        from . import voice_selection

        a = voice_selection.OWNER_ACTION
        return {"proposed_action": a["action"], "why_software_cannot": "; ".join(a["needs"]),
                "consequence_of_no_action": a["consequence_of_waiting"]}
    from ...app.command_center import approvals

    try:
        for c in approvals.inbox(db).get("cards") or []:
            if c.get("card_id") == card_id:
                return c
    except Exception:  # noqa: BLE001
        return None
    return None


def _fu(prev: dict, text: str, cited: list[dict], status: str, *, proposals=None) -> dict:
    facts = [{k: f.get(k) for k in ("id", "statement", "source", "as_of", "link", "basis",
                                    "status") if k in f} for f in cited]
    return {"status": status, "answer": text, "facts": facts,
            "unknowns": [] if status != UNKNOWN else [
                {"section": "briefing_followup", "title": "Follow-up", "reason": text[:300]}],
            "proposals": list(proposals or []),
            "sections": [{"key": "briefing_followup", "title": "Follow-up on my briefing",
                          "status": "OK" if status != UNKNOWN else UNKNOWN,
                          "reason": None, "facts": len(facts)}],
            "method": f"deterministic follow-up resolved against briefing turn {prev['turn_id']}",
            "resolved_turn": prev["turn_id"]}
