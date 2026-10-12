"""Authorised delegation from a conversation (D-FB-16 item 7: "I don't like that banner. Have
Design make three more." -> authorised delegation + confirmation).

Laura parses an instruction of the form "have/ask/get/tell <department> [to] <task>" into a
*brief* and a proposal. Nothing happens until the owner confirms the proposal, and then the
existing follow-on boundary (`followon.create`) decides:

* a task that maps to a protected job type (publish, activate, update a live listing, price,
  ads, a customer message) becomes an owner action after step-up -- never a job;
* spending money, changing Laura's canonical identity, or replacing the owner's canonical
  logo/banner (D-FB-14, D-FB-17) is refused outright and routed to the owner: no job type
  exists for those, and none is invented;
* everything else becomes ONE internal GREEN mission for the named department through the COO
  orchestrator's single enqueue boundary (its `autonomy.department_review` job), carrying the
  brief in its inputs, audited as `laura`, on the company timeline and in her operational
  memory. The department reviews against the brief; any part of the brief that needs a gated
  capability (paid image generation, owner decisions) is listed in the brief as GATED, so the
  confirmation says exactly what will and will not happen.

Deterministic: regular expressions over the question; no model call.
"""
from __future__ import annotations

import re

# Spoken department names -> autonomy charter keys (autonomy.charters.BY_KEY).
DEPARTMENTS: dict[str, str] = {
    "design": "product_design", "product design": "product_design",
    "product & design": "product_design", "product and design": "product_design",
    "creative": "product_design", "product": "product_design",
    "visual": "visual", "visuals": "visual", "visual r&d": "visual", "imagery": "visual",
    "photography": "visual",
    "store": "store_commerce", "shop": "store_commerce", "commerce": "store_commerce",
    "seo": "store_commerce", "merchandising": "store_commerce",
    "finance": "finance", "accounting": "finance", "the books": "finance",
    "growth": "growth", "marketing": "growth",
    "learn": "learn", "improvement": "learn",
    "support": "support", "customer support": "support", "cx": "support",
    "intelligence": "intelligence", "research": "intelligence", "intel": "intelligence",
    "platform": "platform", "reliability": "platform", "ops": "platform",
    "operations": "platform",
    "product truth": "product_truth", "qa": "product_truth", "quality": "product_truth",
    "executive": "executive", "coo": "executive",
}

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "a couple of": 2, "a few": 3, "several": 3}

_DEPT_ALT = "|".join(sorted((re.escape(k) for k in DEPARTMENTS), key=len, reverse=True))
_VERB = r"(?:have|ask|get|tell|let|send|delegate(?:\s+(?:this|it))?\s+to)"
_PATTERN = re.compile(
    rf"(?:^|[.!?;,]\s*|\b(?:please|can you|could you|laura,?)\s+){_VERB}\s+(?:the\s+)?"
    rf"(?P<dept>{_DEPT_ALT})(?:\s+(?:team|department|dept))?\s+(?:to\s+)?(?P<task>[^.!?]+)",
    re.IGNORECASE)

# Task wording -> a protected job type and the department that owns it (charters).
_PROTECTED = (
    (re.compile(r"\b(publish|go live|put .* on etsy|list .* on etsy)\b", re.I),
     "store.publish", "store_commerce"),
    (re.compile(r"\b(activate|reactivate)\b", re.I), "store.activate", "store_commerce"),
    (re.compile(r"\b(update|edit|change) (the )?(live )?listing", re.I), "store.update",
     "store_commerce"),
    (re.compile(r"\b(price|prices|pricing|discount|sale)\b", re.I), "pricing.experiment",
     "store_commerce"),
    (re.compile(r"\b(ads?|campaign|advertis\w*)\b", re.I), "ads.campaign", "growth"),
    (re.compile(r"\b(reply|respond|message|email|write) (to )?(the |a |our )?(customer|buyer)s?",
                re.I), "support.reply", "support"),
)
# Requests no job type may carry: they are owner-only by the company constitution.
_REFUSED = (
    (re.compile(r"\b(spend|pay|buy|purchase|budget|top up|invoice)\b", re.I),
     "spending money is owner-only authority (company constitution; no consequential spend "
     "without owner approval)"),
    (re.compile(r"\b(replace|change|redo|remake|regenerate)\b.*\b(your|laura'?s?) "
                r"(face|look|identity|image|portrait)\b", re.I),
     "Laura's canonical identity (laura-r2-a42aeac7) changes only by a new owner decision "
     "(D-FB-11/D-FB-14)"),
    (re.compile(r"\b(replace|swap|change)\b.*\b(the |our )?(logo|banner)\b", re.I),
     "the owner's canonical logo and banner are preserved byte-for-byte; a replacement needs "
     "a new owner decision (D-FB-17 item 4) -- alternatives can be explored as candidates"),
)
# What each kind of deliverable needs that is not free today (stated, never hidden).
_GATED_NEEDS = (
    (re.compile(r"\b(banner|image|images|photo|photos|picture|pictures|hero|render|renders|"
                r"lifestyle|portrait)s?\b", re.I),
     "new imagery needs Visual's paid generation path, which waits on owner spend authority "
     "(visual.rnd paid_execution); until then the department works from existing assets"),
)


def _count(task: str) -> int | None:
    m = re.search(r"\b(\d{1,2})\b", task)
    if m:
        return int(m.group(1))
    low = task.lower()
    for w, n in sorted(_NUMBERS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(w)}\b", low):
            return n
    return None


_ANTECEDENT = re.compile(r"\b(?:that|this|the|those|these|our|my)\s+([a-z][a-z-]{2,30})\b",
                         re.IGNORECASE)
_DANGLING = re.compile(r"\b(?:more|another|others?|alternatives?|options?|versions?|variants?)"
                       r"(?:\s+(?:of\s+)?(?:them|those|these|it|one|ones))?\s*$", re.IGNORECASE)


def _resolve_object(task: str, before: str) -> str:
    """"I don't like that banner. Have Design make three more." -> "... three more banners".
    Only a dangling "more/another/alternatives" borrows the noun the owner just named."""
    if not _DANGLING.search(task):
        return task
    nouns = [m.group(1).lower() for m in _ANTECEDENT.finditer(before)]
    if not nouns:
        return task
    noun = nouns[-1]
    plural = noun if noun.endswith("s") else noun + "s"
    return re.sub(r"\s+(?:of\s+)?(?:them|those|these|it|one|ones)\s*$", "", task) + " " + plural


def parse(question: str) -> dict | None:
    """The delegation an instruction expresses, or None when it is not one."""
    q = " ".join(str(question or "").replace("’", "'").split())
    m = _PATTERN.search(q)
    if not m:
        return None
    spoken = m.group("dept").lower()
    task = m.group("task").strip().rstrip(",;")
    if not task or len(task) < 3:
        return None
    task = _resolve_object(task, q[:m.start()])
    return {"spoken_department": spoken, "department": DEPARTMENTS.get(spoken),
            "task": task[:240], "count": _count(task)}


def plan(d: dict) -> dict:
    """Classify a parsed delegation: refused / protected (owner action) / green mission."""
    task = d["task"]
    for rx, why in _REFUSED:
        if rx.search(task):
            return {**d, "route": "refused", "why": why, "job_type": None}
    for rx, jt, owner_dept in _PROTECTED:
        if rx.search(task):
            return {**d, "route": "owner_action", "job_type": jt,
                    "department": owner_dept,
                    "why": f"{jt} is protected: it becomes an owner decision after step-up; "
                           f"Laura cannot do it herself"}
    gated = [need for rx, need in _GATED_NEEDS if rx.search(task)]
    return {**d, "route": "mission", "job_type": "autonomy.department_review",
            "gated": gated,
            "why": "internal GREEN work through the COO orchestrator: no publishing, spending "
                   "or customer contact"}


def brief(p: dict, question: str) -> dict:
    """The durable brief a confirmed delegation carries into the department's job inputs."""
    constraints = ["Product Truth unchanged: nothing may misrepresent a pattern",
                   "the owner's canonical logo and banner stay the hero identity and art "
                   "target (D-FB-17); new work is a candidate for owner review, never a "
                   "replacement",
                   "any Laura imagery preserves laura-r2-a42aeac7 and passes every Visual gate; "
                   "nothing becomes publication-approved by this brief"]
    return {"requested_by": "owner via Laura (Command Center)", "instruction": question[:300],
            "task": p["task"], "count": p.get("count"), "department": p["department"],
            "constraints": constraints, "gated": list(p.get("gated") or []),
            "deliverable_state": ("GATED: " + "; ".join(p["gated"])) if p.get("gated")
            else "department review against this brief"}
