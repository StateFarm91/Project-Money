"""A4B-2: the production producer that answers open enrichment requests (Main verdict on A4b).

Before this, `enrichment_requests.answer` had no caller in `src/`. The hourly sweep wrote
request rows and nothing ever answered them, so a refused draft never came back as a new
draft in production.

What this answers with, and why that is the honest limit today
--------------------------------------------------------------
The answer contract (`enrichment_requests._authoritative_input`) admits exactly one payload
for a radar request: the current authoritative radar seed and its deterministic geometry.
It holds three cases:

* registry briefs;
* dynamic (intake-approved) seeds;
* any payload that changes what the product *is*: its object, title, slug, category,
  rationale or geometry.

So the only evidence an answer may rest on is the authoritative seed itself. This producer
therefore invents nothing. For each open radar request, every sweep:

1. builds the authoritative payload from the current seed (never from the request or
   from any model);
2. runs the contract check; a held request stays held, with the contract's reason;
3. re-runs the construction recheck that refused the draft (`_recheck`, which uses the
   same pure builders as `cir.draft`). While it still refuses, nothing is answered and
   no round is spent;
4. once the recheck passes, queues one `research.enrichment_answer` job. That happens
   because a construction the fallback lacked has since been built, or because the
   code-owned seed itself was corrected.

The job key is `enrich-answer:<slug>:<request row>:<seed binding>`, so a sweep repeated
on the same request and seed queues nothing new. The answer handler then does everything
else, serialized under its lock: bounded rounds, `draft:<slug>:enrich:<round>`, exhaustion
at MAX_ROUNDS, and holds on approval changes.

What this does not do: substantive enrichment (new design facts from research). That needs
the reviewed, evidence-bound authority contract the answer path names. Until that exists,
this producer is the request side plus "re-draft when capability catches up", and it says so
in every reading it returns.

CA$0, deterministic, no model or network call, no publish.
"""
from __future__ import annotations

import dataclasses

from . import enrichment_requests as E

ANSWER_JOB = "research.enrichment_answer"
ANSWER_AGENT = "crochet_engineer"
SCOPE = ("re-draft when the authoritative seed now passes the construction that refused it; "
         "substantive enrichment awaits an evidence-bound authority contract")


def authoritative_payload(seed) -> dict:
    """The only payload the answer contract admits: the seed's fields plus its geometry."""
    from ..runtime.pipeline import concept_geometry

    out = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    out.update(concept_geometry(seed))
    return out


def answer_key(slug: str, requested_row, binding: str) -> str:
    return f"enrich-answer:{slug}:{requested_row}:{binding[:16]}"


def plan(db) -> dict:
    """For each open request: one answer to queue, or the named reason it waits.

    Read-only.
    """
    from ..runtime.pipeline import _seed_for

    ready: list[dict] = []
    waiting: list[dict] = []
    for req in sorted(E.open_requests(db), key=lambda r: r["slug"]):
        slug = req["slug"]
        context = req.get("context") or {}
        if context.get("kind") != "radar":
            waiting.append({"slug": slug, "why": "no approved authority contract for this "
                                                 "enrichment"})
            continue
        seed = _seed_for(slug, db)
        if seed is None:
            waiting.append({"slug": slug, "why": "no current approved concept"})
            continue
        payload = authoritative_payload(seed)
        held = E._authoritative_input(db, slug, context, payload, None)
        if held:
            waiting.append({"slug": slug, "why": held})
            continue
        still = E._recheck(context, payload, None)
        if still:
            waiting.append({"slug": slug, "why": "construction still refuses the "
                                                 "authoritative seed", "still_missing": still})
            continue
        binding = E._approved_binding(db, slug)
        if binding is None:
            waiting.append({"slug": slug, "why": "current concept approval is unavailable"})
            continue
        ready.append({"slug": slug, "payload": payload,
                      "key": answer_key(slug, req.get("requested_row"), binding)})
    return {"ready": ready, "waiting": waiting, "scope": SCOPE}


def produce(db, *, enqueue) -> dict:
    """Queue one answer job per ready request. `enqueue` returns None on a duplicate key."""
    reading = plan(db)
    queued, already = [], []
    for item in reading["ready"]:
        job = enqueue(ANSWER_AGENT, ANSWER_JOB, {"slug": item["slug"],
                                                 "payload": item["payload"]},
                      idempotency_key=item["key"])
        (queued if job is not None else already).append(item["slug"])
    return {"answers_queued": queued, "answers_already_queued": already,
            "waiting": reading["waiting"], "scope": reading["scope"]}
