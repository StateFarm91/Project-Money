"""The running half of pre-production demand validation (#4): `growth.preproduction`.

`commerce.preproduction` prepares a concept post and refuses the ways it can go wrong, and
nothing in the running system called it -- the refusals were tested and never exercised. This
module is the caller. Daily, from the database, it:

1. **finds the concepts worth asking about** -- winners held at intake before engineering
   (`creative.winner_intake` rows whose decision is `waiting`) and the newest tournament's
   research survivors. Both are concepts *before* expensive engineering, which is the whole
   point of the stage;
2. **prepares one concept post per channel** through `preproduction.prepare`, so every post
   passes `check_post` or is refused by name, and records each durably
   (`preproduction.concept_post` / `preproduction.post_refused`), once per concept and
   channel;
3. **asks whether it may publish** -- the `owned_surfaces` gate, read the way the closure
   reads it (the latest `owned_surface.probe` row records `ok: true`). Closed, nothing is
   posted and the refusal is recorded (`preproduction.publish_refused`). Open, there is still
   no publisher in this codebase, and that is recorded rather than papered over;
4. **reads interest** from the only place it may come from: a `preproduction.interest_observed`
   row a platform ingest wrote, naming its source. None exists today, so interest is recorded
   `UNMEASURED` by name through `preproduction.record_interest`, which has no path that can
   author a number;
5. **acts on a measured result**: a concept whose interest a platform reported is recorded as
   `preproduction.validated` with the observation, and `creative.ideation` reads those rows
   into the next tournament's brief -- the field is steered toward what buyers were seen
   responding to, with the receipt row named in the constraint.

Nothing here posts, spends or fetches. The one number this module ever writes about interest
is the count of rows it read.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from . import preproduction

JOB_TYPE = "growth.preproduction"
CHANNELS: tuple[str, ...] = ("pinterest", "owned_site")
GATE = "owned_surfaces"

CYCLE_ACTION = "preproduction.cycle"
POST_ACTION = "preproduction.concept_post"
REFUSED_ACTION = "preproduction.post_refused"
PUBLISH_REFUSED_ACTION = "preproduction.publish_refused"
INTEREST_ACTION = "preproduction.interest"
OBSERVED_ACTION = "preproduction.interest_observed"     # written only by a platform ingest
VALIDATED_ACTION = "preproduction.validated"

UNMEASURED = "UNMEASURED"
MAX_CONCEPTS = 12
BRIEF_ROWS = 5


def _concept_from(entry: dict):
    """The concept a post is about, from a recorded dict (an intake row's `concept` or a
    survivor entry). A post needs the concept's key and its premise -- `preproduction`
    reads nothing else -- so nothing is invented for fields a survivor entry does not carry."""
    from types import SimpleNamespace

    raw = dict(entry.get("concept") or entry)
    key, premise = str(raw.get("key") or ""), str(raw.get("premise") or "")
    if not key or len(premise.split()) < 6:
        return None
    return SimpleNamespace(key=key, premise=premise, title=str(raw.get("title") or key),
                           pod=str(raw.get("pod") or ""), form=str(raw.get("form") or ""))


def candidates(db, *, limit: int = MAX_CONCEPTS) -> list[dict]:
    """Concepts before engineering: held winners first, then the newest field's survivors."""
    from ..creative import intake
    from ..creative.ideation import _rows as ideation_rows

    out: list[dict] = []
    seen: set[str] = set()
    for _id, slug, detail in intake.intake_rows(db, limit=60):
        if detail.get("decision") != intake.WAITING or slug in seen:
            continue
        concept = _concept_from(detail)
        if concept is None:
            continue
        seen.add(slug)
        out.append({"concept": concept, "from": f"{intake.INTAKE_ACTION} row {_id}",
                    "stage": "held_winner"})
    for _id, _action, _artifact, detail in ideation_rows(db, ("creative.tournament",),
                                                          limit=1):
        for entry in detail.get("research_survivors") or []:
            key = str(entry.get("key") or "")
            if not key or key in seen or not isinstance(entry, dict):
                continue
            concept = _concept_from(entry)
            if concept is None:
                continue
            seen.add(key)
            out.append({"concept": concept, "from": f"creative.tournament row {_id}",
                        "stage": "research_survivor"})
    return out[:limit]


def _rows(db, action: str, *, artifact: str | None = None) -> list[tuple[int, str, dict]]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    q = select(AuditLog).where(AuditLog.action == action)
    if artifact is not None:
        q = q.where(AuditLog.artifact == artifact)
    with db.session() as s:
        return [(r.id, r.artifact or "", dict(r.detail or {}))
                for r in s.scalars(q.order_by(AuditLog.id))]


def gate_open(db) -> dict:
    """The `owned_surfaces` gate, read exactly as the Build 2 closure reads it."""
    from ..build2.executor import GATES

    gate = next((g for g in GATES if g.key == GATE), None)
    if gate is None:  # pragma: no cover - the gate table is validated at import
        return {"gate": GATE, "open": False, "how": "gate not found"}
    return {"gate": GATE, "open": gate.open(db, None), "how": gate.how}


def observed_interest(db, key: str) -> dict | None:
    """The newest platform-reported observation for a concept, or None. Never authored here."""
    rows = _rows(db, OBSERVED_ACTION, artifact=key)
    if not rows:
        return None
    row_id, _artifact, detail = rows[-1]
    return {"row": row_id, "source": str(detail.get("source") or ""),
            "observed": dict(detail.get("observed") or {}),
            "channel": str(detail.get("channel") or "")}


def brief(db, *, limit: int = BRIEF_ROWS) -> dict:
    """What ideation reads: the concepts whose interest a platform measured (#4)."""
    rows = _rows(db, VALIDATED_ACTION)
    if not rows:
        return {"measured": [], "source": None,
                "reason": ("no concept post has a platform-reported interest reading; "
                           "posting waits on owned_surfaces and interest is UNMEASURED")}
    latest: dict[str, tuple[int, dict]] = {}
    for row_id, artifact, detail in rows:
        latest[artifact] = (row_id, detail)
    measured = []
    for artifact, (row_id, detail) in sorted(latest.items(), key=lambda kv: -kv[1][0])[:limit]:
        measured.append({"concept": artifact, "premise": str(detail.get("premise") or "")[:160],
                         "source": detail.get("source"), "observed": detail.get("observed"),
                         "receipt": f"{VALIDATED_ACTION} row {row_id}"})
    return {"measured": measured, "source": f"{VALIDATED_ACTION} rows",
            "reason": f"{len(measured)} concept(s) with platform-reported interest"}


def brief_lines(b: dict) -> list[str]:
    """The constraint lines a measured result adds to a generator brief."""
    lines = []
    for m in b.get("measured") or []:
        numbers = ", ".join(f"{k} {v}" for k, v in sorted((m.get("observed") or {}).items()))
        lines.append(f"- pre-production interest ({m['receipt']}, reported by {m['source']}): "
                     f"the concept {m['concept']!r} -- {m['premise']} -- drew {numbers}; a "
                     f"concept developing that direction is preferred, never a copy of it")
    return lines


def run(ctx, *, today: date | None = None) -> dict:
    """One cycle: prepare, refuse-to-post, read interest, act on what was measured."""
    db = ctx.db
    today = today or datetime.now(timezone.utc).date()
    found = candidates(db)
    existing_posts = {(a, d.get("channel")) for _i, a, d in _rows(db, POST_ACTION)}
    existing_refusals = {(a, d.get("channel")) for _i, a, d in _rows(db, REFUSED_ACTION)}
    last_interest = {a: d for _i, a, d in _rows(db, INTEREST_ACTION)}
    validated_rows = {a: d.get("observed_row") for _i, a, d in _rows(db, VALIDATED_ACTION)}

    prepared, refused, held_for_gate, acted = [], [], [], []
    interest: dict[str, str] = {}
    posts_by_key: dict[str, preproduction.ConceptPost] = {}
    premise_of: dict[str, str] = {}

    for item in found:
        concept = item["concept"]
        for channel in CHANNELS:
            body = preproduction._body_for(concept)
            try:
                post = preproduction.prepare(concept, channel=channel, body=body, today=today)
            except preproduction.PreProductionRefused as exc:
                if (concept.key, channel) not in existing_refusals:
                    ctx.audit(REFUSED_ACTION, artifact=concept.key,
                              detail={"channel": channel, "why": str(exc)[:400],
                                      "from": item["from"]})
                refused.append({"concept": concept.key, "channel": channel,
                                "why": str(exc)[:200]})
                continue
            posts_by_key.setdefault(concept.key, post)
            premise_of[concept.key] = concept.premise
            if (concept.key, channel) not in existing_posts:
                ctx.audit(POST_ACTION, artifact=concept.key,
                          detail={**post.to_dict(), "from": item["from"],
                                  "stage": item["stage"], "check": "passed",
                                  "posted": False})
                prepared.append({"concept": concept.key, "channel": channel})
            held_for_gate.append({"concept": concept.key, "channel": channel})

    gate = gate_open(db)
    publish = {"gate": GATE, "open": gate["open"], "posted": 0}
    if held_for_gate and not gate["open"]:
        publish["state"] = "refused"
        publish["why"] = (f"the {GATE} gate is closed: {gate['how']}. Nothing is posted; the "
                          f"prepared posts wait, checked, for the day a surface exists")
        ctx.audit(PUBLISH_REFUSED_ACTION, detail={
            "gate": GATE, "held": len(held_for_gate),
            "concepts": sorted({h["concept"] for h in held_for_gate}), "why": publish["why"]})
    elif held_for_gate:
        publish["state"] = "no_publisher"
        publish["why"] = (f"the {GATE} gate is open but this codebase has no publisher for a "
                          f"concept post yet; nothing is posted and that is recorded rather "
                          f"than a post being counted")
    else:
        publish["state"] = "nothing_to_post"
        publish["why"] = "no concept before engineering was found in the rows"

    for key, post in posts_by_key.items():
        seen = observed_interest(db, key)
        if seen is None:
            reading = preproduction.record_interest(post, observed=None, source="")
            verdict = UNMEASURED
        else:
            try:
                reading = preproduction.record_interest(post, observed=seen["observed"],
                                                        source=seen["source"])
            except preproduction.PreProductionRefused as exc:
                reading = {"concept": key, "measurable": False, "source": seen["source"],
                           "why": str(exc)[:300], "observed_row": seen["row"]}
            verdict = "measured" if reading["measurable"] else UNMEASURED
        record = {**reading, "reading": verdict,
                  "observed_row": (seen or {}).get("row")}
        previous = last_interest.get(key)
        if previous is None or {k: previous.get(k) for k in ("reading", "observed_row")} != \
                {k: record.get(k) for k in ("reading", "observed_row")}:
            ctx.audit(INTEREST_ACTION, artifact=key, detail=record)
        interest[key] = verdict
        if verdict == "measured" and validated_rows.get(key) != seen["row"]:
            # The act: a measured result becomes a brief input the next field is generated
            # under (`creative.ideation.preproduction_interest`), with its receipt.
            ctx.audit(VALIDATED_ACTION, artifact=key, detail={
                "premise": premise_of.get(key, "")[:300],
                "source": seen["source"], "observed": seen["observed"],
                "observed_row": seen["row"], "channel": seen["channel"],
                "feeds": "creative.ideation.plan()['preproduction'] -> constraints_text",
                "why": ("interest a platform measured on a concept post before engineering "
                        "is the one signal this stage exists to produce; it steers the next "
                        "field toward the direction buyers responded to")})
            acted.append({"concept": key, "source": seen["source"],
                          "observed": seen["observed"]})

    return {
        "ran": True,
        "concepts": len(found),
        "prepared": prepared, "refused": refused,
        "held_for_gate": len(held_for_gate),
        "publish": publish,
        "interest": interest,
        "unmeasured": sorted(k for k, v in interest.items() if v == UNMEASURED),
        "acted_on": acted,
        "brief": brief(db),
        "never": preproduction.NEVER_FABRICATED,
    }
