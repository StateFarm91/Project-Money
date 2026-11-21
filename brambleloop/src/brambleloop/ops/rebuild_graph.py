"""The rebuild set, and the part of the estate the graph cannot see.

Requirement 172. An explicit dependency graph per product; when a node changes, compute the
exact downstream rebuild set, enqueue it idempotently, and block publication until every
required descendant has been rebuilt and re-certified -- storing old and new fingerprints,
the reason, the time, and the evidence that it completed.

The graph is not invented here. `ops.artefacts` already records what every artefact was made
from, and this reads those edges rather than maintaining a second opinion about them: a
dependency graph kept beside the provenance would be a second answer to "what does this
depend on", and the two would agree until the day it mattered.

What this adds is direction and closure. Provenance answers *what was this made from*; a
rebuild needs *what must now be remade*, which is the same edges followed the other way, and
transitively -- a listing built from a PDF built from a design is two hops from the design
and nobody rebuilds it by hand. And it needs an order: rebuilding the listing before the PDF
regenerates it from the stale one, which is worse than not rebuilding it, because afterwards
everything claims to be current.

**The number that matters is the one the graph cannot see.** Today the production estate
holds 275 derived artefacts and not one carries a provenance row, so a propagation over the
recorded graph would touch nothing and report that no rebuild is needed. That is a true
statement about the graph and a false one about the shop. So every plan reports its coverage,
and a plan that covers a small share of the estate says so on the same line as its rebuild
set -- because the rebuild set is the part people read.

**A cycle is refused rather than traversed.** A rebuild graph with a cycle is a rebuild that
does not terminate, and the shape it takes in practice is two artefacts each recorded as an
input to the other by a caller who meant "these go together".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .artefacts import ARTEFACT_CLASSES, UNPROVEN, check


class GraphRefused(ValueError):
    """A cycle, or a node nobody recorded."""


@dataclass
class Node:
    """One artefact in the graph, with the refs it was built from."""

    key: str                       # "class:artefact_key"
    artefact_class: str
    artefact_key: str
    product_slug: str
    inputs: dict[str, str] = field(default_factory=dict)


def _node_key(artefact_class: str, artefact_key: str) -> str:
    return f"{artefact_class}:{artefact_key}"


def load_graph(db) -> dict:
    """Read the edges from the provenance rows rather than keeping a second copy."""
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    nodes: dict[str, Node] = {}
    for row in db.scalars(select(ArtefactProvenance)):
        key = _node_key(row.artefact_class, row.artefact_key)
        nodes[key] = Node(key=key, artefact_class=row.artefact_class,
                          artefact_key=row.artefact_key, product_slug=row.product_slug,
                          inputs=dict(row.inputs or {}))

    # An artefact may be an input to another one: "asset:hex-coaster.pdf" refers to a node if
    # something recorded that artefact. Edges to refs nobody recorded are upstreams outside
    # the graph -- a design, a policy snapshot -- and are kept as such rather than dropped.
    by_ref: dict[str, str] = {}
    for key, node in nodes.items():
        by_ref[f"asset:{node.artefact_key}"] = key

    children: dict[str, set[str]] = {k: set() for k in nodes}
    external: set[str] = set()
    for key, node in nodes.items():
        for ref in node.inputs:
            parent = by_ref.get(ref)
            if parent is None:
                external.add(ref)
            elif parent != key:
                children[parent].add(key)

    _refuse_cycles(children)
    return {"nodes": nodes, "children": children, "external_refs": sorted(external)}


def _refuse_cycles(children: dict[str, set[str]]) -> None:
    colour: dict[str, int] = {}

    def visit(key: str, path: list[str]) -> None:
        state = colour.get(key, 0)
        if state == 1:
            cycle = path[path.index(key):] + [key]
            raise GraphRefused(
                f"a cycle: {' -> '.join(cycle)}. A rebuild graph with a cycle is a rebuild "
                f"that does not terminate, and in practice it is two artefacts each recorded "
                f"as an input to the other by somebody who meant 'these go together'")
        if state == 2:
            return
        colour[key] = 1
        for child in sorted(children.get(key, ())):
            visit(child, path + [key])
        colour[key] = 2

    for key in sorted(children):
        visit(key, [])


def rebuild_set(db, *, changed: dict[str, str],
                expected: list[tuple[str, str, str]] | None = None) -> dict:
    """Everything that must be remade because these refs moved, in the order to remake it.

    `changed` maps an upstream reference to its new fingerprint. The order is topological:
    rebuilding a listing before the PDF it quotes regenerates it from the stale one, which is
    worse than not rebuilding it, because afterwards everything claims to be current.
    """
    graph = load_graph(db)
    nodes, children = graph["nodes"], graph["children"]

    seeds = {key for key, node in nodes.items()
             if any(ref in changed for ref in node.inputs)}

    affected: set[str] = set()
    frontier = list(seeds)
    while frontier:
        key = frontier.pop()
        if key in affected:
            continue
        affected.add(key)
        frontier.extend(children.get(key, ()))

    # eng/publish-unhalt U2: a retired legacy-duplicate slug is never rebuilt
    # (`creative.preengineering` refuses it), so planning its artefacts enqueued a
    # chain.rebuild that could only be refused, spent the bounded budget and filed a
    # rebuild-incomplete hold for a product that no longer exists. Its artefacts read
    # retired in `artefacts.check`; they are listed apart here, never planned.
    from .artefacts import _retired_slugs

    retired_slugs = _retired_slugs()
    retired_skipped = sorted(k for k in affected if nodes[k].product_slug in retired_slugs)
    affected -= set(retired_skipped)
    order = _topological(affected, children)

    # Coverage: the rebuild set is the part people read, so what the graph cannot see is
    # reported on the same line rather than in a separate report nobody opens.
    unseen = 0
    if expected is not None:
        unseen = sum(1 for v in check(db, current={}, expected=expected)
                     if v.state == UNPROVEN)
    total = len(nodes) + unseen

    return {
        "changed": sorted(changed),
        "rebuild": [{"key": k, "artefact_class": nodes[k].artefact_class,
                     "artefact_key": nodes[k].artefact_key,
                     "product_slug": nodes[k].product_slug,
                     # the moved refs this node itself records (eng/stale-rebuild-loop)
                     "refs": sorted(r for r in nodes[k].inputs if r in changed)}
                    for k in order],
        "count": len(order),
        "retired_skipped": retired_skipped,
        "seeds": sorted(seeds),
        "coverage": {
            "in_graph": len(nodes),
            "not_in_graph": unseen,
            "share": round(len(nodes) / total, 3) if total else None,
        },
        "why": (f"{len(order)} artefact(s) descend from {sorted(changed)}"
                + (f", out of an estate where {unseen} artefact(s) carry no provenance at "
                   f"all -- a propagation over the recorded graph cannot reach them, and "
                   f"reports that no rebuild is needed, which is true of the graph and false "
                   f"of the shop" if unseen else "")),
        "order_note": ("topological: a listing rebuilt before the PDF it quotes is "
                       "regenerated from the stale one, and afterwards everything claims to "
                       "be current"),
    }


def _topological(keys: set[str], children: dict[str, set[str]]) -> list[str]:
    """Parents before children, deterministically."""
    inside = set(keys)
    indegree = {k: 0 for k in inside}
    for key in inside:
        for child in children.get(key, ()):
            if child in inside:
                indegree[child] += 1
    ready = sorted(k for k, n in indegree.items() if n == 0)
    order: list[str] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for child in sorted(children.get(key, ())):
            if child not in inside:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    return order


# `jobs.idempotency_key` is VARCHAR(200) (core/models.py). A key built from every moved ref
# outgrows it as soon as a deploy moves many code fingerprints at once: on Postgres the insert
# then fails with StringDataRightTruncation and the sentinel dead-letters every hour
# (production 0417f35, 2026-10-11, W4-FMGATE). SQLite does not enforce the length, so only
# Postgres ever saw it.
IDEMPOTENCY_KEY_MAX = 200


def job_key(prefix: str, stamp: str) -> str:
    """`prefix:stamp`, or -- when that would not fit the column -- `prefix:sha256=<digest of
    stamp>`. Deterministic in the change, so the idempotency property is unchanged: the same
    change still enqueues once and a different change enqueues again."""
    key = f"{prefix}:{stamp}"
    if len(key) <= IDEMPOTENCY_KEY_MAX:
        return key
    digest = hashlib.sha256(stamp.encode()).hexdigest()
    key = f"{prefix}:sha256={digest}"
    if len(key) <= IDEMPOTENCY_KEY_MAX:
        return key
    return "rebuild:sha256=" + hashlib.sha256(f"{prefix}\0{stamp}".encode()).hexdigest()


def _bounded_key(prefix: str, stamp: str) -> str:
    """W4-FINHEALTH's spelling of the same fix (prefix carries its trailing ':'); one
    implementation, `job_key`, so both lanes' regression tests hold the same keys."""
    return job_key(prefix[:-1] if prefix.endswith(":") else prefix, stamp)


# How long after the last terminal attempt for a product the same change may be asked for
# again. Long enough that a verify cycle (3 x 20 min) has finished; one retry per UTC day.
RETRY_AFTER = timedelta(hours=12)


def _recent_rebuild_slugs(db, now: datetime) -> set[str]:
    """Products with a chain.rebuild in flight, or one that ended inside RETRY_AFTER.

    Review F6: one bounded query per sentinel run (in-flight rows plus rows touched inside the
    window), never every chain.rebuild ever written once per product."""
    from sqlalchemy import or_, select

    from ..core.models import Job, JobStatus

    since = now - RETRY_AFTER
    rows = db.execute(select(Job.inputs).where(
        Job.job_type == "chain.rebuild",
        or_(Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)),
            Job.finished_at >= since,
            Job.finished_at.is_(None) & (Job.created_at >= since))))
    return {str((inputs or {}).get("product_slug") or "") for (inputs,) in rows}


# eng/stale-rebuild-loop: a rebuild that cannot complete must not loop silently. After this
# many attempts at the same change ended `rebuild-incomplete`, the daily retry stops and the
# product is held with the named reason on that incident (`release_gates.retry_hold_reason`).
REBUILD_INCOMPLETE_SIGNATURE = "rebuild-incomplete"
REBUILD_MAX_ATTEMPTS = 3
# Review LOW of 0d2e6cbc: failed attempts are read inside this window only (and only for the
# products in the plan), not every chain.rebuild ever written. Three daily attempts take
# ~3 days; once a change is held the durable rebuild-incomplete row keeps holding it
# (`release_gates.retry_hold_reason`), so failures ageing out of the window do not unhold it.
REBUILD_FAILURE_WINDOW = timedelta(days=30)
LEGACY_RESET_WHY = (
    "row written before eng/stale-rebuild-loop: its report_count counted every failed daily "
    "attempt, including attempts that failed only because of the bugs that branch fixed, so "
    "it is not an attempt budget. The new code gives it a fresh budget of "
    f"{REBUILD_MAX_ATTEMPTS} attempts; the legacy count and detail are kept here.")


def legacy_incomplete(detail) -> bool:
    """Review M-E of 0d2e6cbc: a `rebuild-incomplete` row written by the pre-branch code -- no
    `attempts` (every write since this branch records it) and no budget reset recorded yet.
    Its report_count is a count of loop iterations, not of attempts under the bounded retry."""
    d = detail or {}
    return "attempts" not in d and "budget_reset" not in d


def incomplete_exhausted(report_count, detail) -> bool:
    """One definition of 'this rebuild-incomplete row has used up its attempts' (the retry
    hold, the publish gate and production evidence all read it). A legacy row is never
    exhausted by its count: it is retried and gets a fresh, recorded budget on its first
    restate (`reset_legacy_budget`); after that budget the named hold applies as designed."""
    d = detail or {}
    if d.get("held"):
        return True
    if legacy_incomplete(d):
        return False
    return int(report_count or 1) >= REBUILD_MAX_ATTEMPTS


def reset_legacy_budget(inc, *, now: datetime | None = None) -> dict | None:
    """If `inc` is a legacy row, the record of its budget reset (the legacy count, the legacy
    detail as it stood, when and why) -- to be stored in its detail as `budget_reset` by the
    caller, which also sets the new count. None for a row already under the new budget."""
    detail = dict(inc.detail or {})
    if not legacy_incomplete(detail):
        return None
    legacy = {k: v for k, v in detail.items() if k != "stale"}
    legacy["stale"] = list(detail.get("stale") or [])[:50]
    return {"legacy_report_count": int(inc.report_count or 1),
            "legacy_severity": inc.severity, "legacy_summary": str(inc.summary or "")[:500],
            "legacy_opened_at": inc.at.isoformat() if getattr(inc, "at", None) else None,
            "legacy_detail": legacy,
            "at": (now or datetime.now(timezone.utc)).isoformat(),
            "why": LEGACY_RESET_WHY}


HOLD_RELEASE_KEY = "hold_released"


def _hold_text(detail) -> str:
    d = detail or {}
    parts = [str(d.get("held") or "")]
    parts += [str(x) for x in (d.get("refused_by") or [])]
    parts += [str((f or {}).get("why") or "") for f in (d.get("failed_attempts") or [])
              if isinstance(f, dict)]
    return " | ".join(p for p in parts if p)


def held_policy_cause_cleared(detail, *, unreviewed: set[str], not_current: set[str]):
    """eng/publish-unhalt U3: the policy sources an exhausted hold names as its cause, when
    every one of them has since cleared -- or None.

    A hold filed while a #39 refusal (an unreviewed material change, e.g. the
    `listing_image_rules` change the owner later released by D-OWNER-POLICY39-OVERRIDE)
    refused every attempt records that refusal in `held` / `refused_by` / `failed_attempts`.
    Nothing re-read it: the hold outlived its cause, no retry ran, the row could never close
    and the company-wide halt it fed stayed open. The cause is read deterministically: the
    watched source keys (`platform_policy.POLICY_SOURCES`) named in the recorded refusal
    text. Cleared means none of them is unreviewed (owner overrides honoured, as everywhere)
    and none is stale or unread. A hold naming no policy source, or one that is still
    refused, returns None and stays held. One release per distinct hold
    (`hold_released.held_digest`), so a cause that re-holds is not looped."""
    from ..gates.platform_policy import POLICY_SOURCES

    d = detail or {}
    if not d.get("held"):
        return None
    text = _hold_text(d)
    if "#39" not in text and "policy" not in text.lower():
        return None
    named = sorted(src for src in POLICY_SOURCES if src in text)
    if not named:
        return None
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    if (d.get(HOLD_RELEASE_KEY) or {}).get("held_digest") == digest:
        return None
    if any(src in unreviewed or src in not_current for src in named):
        return None
    return {"sources": named, "held_digest": digest}


def held_without_own_stage(db, slug: str, detail, *, final_check: int,
                           now: datetime | None = None):
    """eng/halt-380: an exhausted `_rebuild_incomplete` hold whose counted attempts did not
    each run a stage job of their own -- or None.

    Before this branch a second attempt at the same change (minted by another product's ref
    moving the estate-wide key) deduplicated onto the first attempt's stage job and rebuilt
    nothing; its verify passes ran out and counted a failed attempt. Three such no-op attempts
    held the product with "the stage ran and did not rewrite them", which was not true, and
    nothing re-read it: the product never rebuilt and the systemic halt it fed stayed open.

    Read deterministically from the product's final verify passes at the hold's own change
    (same fingerprints) inside REBUILD_FAILURE_WINDOW: each carries the `stage_job` its
    attempt enqueued, or none. Released only when fewer than REBUILD_MAX_ATTEMPTS of them ran
    a stage of their own and at least one did not. A hold of the DEAD/refused kind
    (`failed_attempts`) is a different cause and is never released here; one release per
    distinct hold text (`hold_released.held_digest`)."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    d = detail or {}
    if not d.get("held") or d.get("failed_attempts"):
        return None
    fps = d.get("fingerprints") or {}
    now = now or datetime.now(timezone.utc)
    ran = without = 0
    for inputs, outputs in db.execute(select(Job.inputs, Job.outputs).where(
            Job.job_type == "chain.rebuild", Job.status == JobStatus.DONE,
            Job.finished_at >= now - REBUILD_FAILURE_WINDOW,
            Job.idempotency_key.like(f"rebuild-verify:{slug}:%"))):
        inputs, outputs = dict(inputs or {}), dict(outputs or {})
        if (str(inputs.get("product_slug") or "") != slug
                or int(inputs.get("verify") or 0) != int(final_check)
                or (inputs.get("fingerprints") or {}) != fps
                or not outputs.get("outstanding")):
            continue
        if inputs.get("stage_job"):
            ran += 1
        else:
            without += 1
    if without == 0 or ran >= REBUILD_MAX_ATTEMPTS:
        return None
    digest = hashlib.sha256(_hold_text(d).encode()).hexdigest()[:16]
    if (d.get(HOLD_RELEASE_KEY) or {}).get("held_digest") == digest:
        return None
    return {"sources": [], "held_digest": digest, "attempts_with_own_stage": ran,
            "attempts_without_own_stage": without,
            "why": (f"{without} of the attempts this hold counted ran no stage job of their "
                    f"own (their stage key was already taken by an earlier attempt, so they "
                    f"rebuilt nothing); {ran} ran one. One fresh budget of "
                    f"{REBUILD_MAX_ATTEMPTS} attempts (eng/halt-380)")}


def release_cleared_hold(inc, cleared: dict, *, now: datetime | None = None) -> dict:
    """Give a hold whose cause cleared one fresh, recorded budget (the row stays OPEN and
    halting; only a verified rebuild or the sentinel's positive evidence closes it)."""
    detail = dict(inc.detail or {})
    record = {"at": (now or datetime.now(timezone.utc)).isoformat(),
              "sources": cleared["sources"], "held_digest": cleared["held_digest"],
              "previous_held": str(detail.get("held") or "")[:500],
              "previous_report_count": int(inc.report_count or 1),
              "why": cleared.get("why") or (
                  "the policy refusal this hold recorded has cleared (no named source is "
                  "unreviewed, stale or unread now); one fresh budget of "
                  f"{REBUILD_MAX_ATTEMPTS} attempts")}
    for k in ("attempts_with_own_stage", "attempts_without_own_stage"):
        if k in cleared:
            record[k] = cleared[k]
    detail.pop("held", None)
    detail["attempts"] = 0
    detail[HOLD_RELEASE_KEY] = record
    inc.detail = detail
    inc.report_count = 1
    return record


def _released_at(db, slugs) -> dict[str, datetime]:
    """When each product's rebuild-incomplete hold was last released (U3), so attempts that
    failed under the cleared cause do not spend the fresh budget."""
    from sqlalchemy import select

    from ..core.models import Incident

    out: dict[str, datetime] = {}
    sigs = [f"{REBUILD_INCOMPLETE_SIGNATURE}:{s}" for s in slugs]
    if not sigs:
        return out
    for sig, detail in db.execute(select(Incident.signature, Incident.detail).where(
            Incident.signature.in_(sigs), Incident.resolved.is_(False))):
        at = ((detail or {}).get(HOLD_RELEASE_KEY) or {}).get("at")
        if not at:
            continue
        try:
            t = datetime.fromisoformat(str(at))
        except ValueError:
            continue
        out[sig.split(":", 1)[1]] = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return out


def change_id(changed: dict[str, str], own_refs: set[str]) -> str:
    """Review LOW of 0d2e6cbc: the change *this product* is asked to absorb -- only the refs
    its artefacts record, with their new fingerprints. The job key carries the estate-wide
    change set (unchanged, for idempotency), so another product's ref moving gave this product
    a new key and restarted its failure bound; the bound is keyed on this instead."""
    own = {ref: fp for ref, fp in sorted(changed.items()) if ref in own_refs}
    return hashlib.sha256(json.dumps(own, sort_keys=True).encode()).hexdigest()[:16]


def _failed_attempts_by_change(db, slugs, *, now: datetime) -> tuple[dict, dict]:
    """Review M-B of 4b683993: attempts that ended without ever reaching a verify pass --
    the job went DEAD (raised until its retries ran out) or the rebuild refused (no stored
    release, a withheld release) -- keyed `slug|change_id` (the product's own change, carried
    in the payload by every attempt and retry since round 3). Verify passes are not attempts;
    their outcome is counted on the rebuild-incomplete row. One query per call.

    Round 3 (review of 0d2e6cbc): bounded to `slugs` and REBUILD_FAILURE_WINDOW, and a
    pre-branch attempt (no `change_id` in its payload: it failed under the bugs this branch
    fixes) spends none of the new budget -- it is counted per product in the second return
    value so the hold can say how many were not counted."""
    from sqlalchemy import or_, select

    from ..core.models import Job, JobStatus

    slugs = sorted({s for s in slugs if s})
    out: dict[str, list[dict]] = {}
    legacy: dict[str, int] = {}
    if not slugs:
        return out, legacy
    released: dict[str, datetime] | None = None
    like = [Job.idempotency_key.like(f"rebuild:product:{s}:%") for s in slugs]
    for key, status, inputs, outputs, err, finished in db.execute(select(
            Job.idempotency_key, Job.status, Job.inputs, Job.outputs, Job.last_error,
            Job.finished_at).where(
            Job.job_type == "chain.rebuild",
            Job.status.in_((JobStatus.DEAD, JobStatus.DONE)),
            Job.finished_at >= now - REBUILD_FAILURE_WINDOW,
            # a key too long for the column is hashed whole (`job_key`): keep those too
            or_(*like, Job.idempotency_key.like("rebuild:sha256=%"))).order_by(Job.id)):
        inputs, outputs = dict(inputs or {}), dict(outputs or {})
        slug = str(inputs.get("product_slug") or "")
        if inputs.get("verify") or slug not in slugs:
            continue
        if status == JobStatus.DEAD:
            text = str(err or "").strip()
            why = (f"chain.rebuild went dead: {text.split(':', 1)[0][:80] or 'unknown error'}"
                   + (f" ({text[:160]})" if text else ""))
        elif outputs.get("refused") or outputs.get("withheld"):
            why = ("chain.rebuild refused: "
                   + (str(outputs.get("refused")) if outputs.get("refused")
                      else "release withheld (#163/#228)"))
        else:
            continue
        if not inputs.get("change_id"):
            legacy[slug] = legacy.get(slug, 0) + 1
            continue
        if released is None:
            released = _released_at(db, slugs)
        if slug in released and finished is not None:
            f_at = finished if finished.tzinfo else finished.replace(tzinfo=timezone.utc)
            if f_at <= released[slug]:
                continue        # U3: failed under a cause that has since cleared
        out.setdefault(f"{slug}|{inputs['change_id']}", []).append(
            {"why": why, "finished_at": str(finished), "job_key": key,
             "status": getattr(status, "value", str(status))})
    return out, legacy


def _hold_failed_change(db, slug: str, key: str, failures: list[dict], *,
                        artefacts: list[str], fingerprints: dict, change: str = "",
                        legacy_failures: int = 0, now: datetime | None = None) -> str:
    """File the named, durable hold for a change whose attempts all died or were refused:
    `rebuild-incomplete:<slug>` (the family production_evidence, retry_hold_reason and the
    publish gate already read), exhausted, with the last failure's class as the reason. It
    closes like any rebuild-incomplete row: on a verified rebuild, or when the sentinel reads
    every artefact it names fresh."""
    from sqlalchemy import select

    from ..core.models import Incident

    last = failures[-1]["why"]
    held = (f"{len(failures)} rebuild attempts at this change ended without a verify pass; "
            f"last: {last}")
    sig = f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}"
    inc = db.scalar(select(Incident).where(Incident.signature == sig,
                                           Incident.resolved.is_(False)))
    detail = {"stale": list(artefacts)[:50], "fingerprints": fingerprints, "change": key,
              "change_id": change, "attempts": len(failures),
              "max_attempts": REBUILD_MAX_ATTEMPTS,
              "failed_attempts": failures[-REBUILD_MAX_ATTEMPTS:], "held": held,
              "legacy_failed_attempts_not_counted": int(legacy_failures),
              "reason": "attempts died or were refused before any verify pass"}
    summary = (f"rebuild of {slug} held: {len(failures)} attempts at one change ended "
               f"without a verify pass ({last[:120]})")
    if inc is None:
        db.add(Incident(severity="P1", signature=sig, halts_publication=True,
                        product_slug=slug, summary=summary[:500],
                        report_count=len(failures), detail=detail))
    else:
        inc.product_slug, inc.severity, inc.halts_publication = slug, "P1", True
        reset = reset_legacy_budget(inc, now=now)       # review M-E: keep, do not erase
        if reset is not None:
            detail["budget_reset"] = reset
            inc.report_count = len(failures)
        else:
            inc.report_count = max(int(inc.report_count or 1), len(failures))
        inc.summary = summary[:500]
        inc.detail = dict(inc.detail or {}, **detail)
    db.flush()
    return held


def _inflight_slugs(db) -> set[str]:
    """Products with a chain.rebuild in flight (pending, running, or failed-and-retrying) --
    the first attempt, its daily retry or one of its verify passes. A key held by a finished
    job is not a queued rebuild."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    rows = db.execute(select(Job.inputs).where(
        Job.job_type == "chain.rebuild",
        Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED))))
    return {str((inputs or {}).get("product_slug") or "") for (inputs,) in rows}


def _prior_attempt_keys(db, by_product, *, now: datetime) -> dict[str, str]:
    """eng/halt-380: `slug|change_id` -> the key of the newest first attempt (not a retry,
    not a verify pass) at that product's own change, inside REBUILD_FAILURE_WINDOW, whatever
    its status. One bounded query per sentinel run. Attempts written before round 3 carry no
    `change_id` and are not matched (they keep their own keys, as before)."""
    from sqlalchemy import or_, select

    from ..core.models import Job

    slugs = sorted({s for s in by_product if s})
    out: dict[str, str] = {}
    if not slugs:
        return out
    like = [Job.idempotency_key.like(f"rebuild:product:{s}:%") for s in slugs]
    for key, inputs in db.execute(select(Job.idempotency_key, Job.inputs).where(
            Job.job_type == "chain.rebuild",
            Job.created_at >= now - REBUILD_FAILURE_WINDOW,
            or_(*like, Job.idempotency_key.like("rebuild:sha256=%"))).order_by(Job.id)):
        inputs = dict(inputs or {})
        slug, change = str(inputs.get("product_slug") or ""), inputs.get("change_id")
        if (slug not in slugs or not change or inputs.get("verify")
                or inputs.get("retry_of_key")):
            continue
        out[f"{slug}|{change}"] = key
    return out


def _retry_key(db, slug: str, key: str, *, now: datetime | None = None,
               recent: set[str] | None = None) -> str | None:
    """A fresh daily key when no chain.rebuild for `slug` is in flight and none ended inside
    RETRY_AFTER; otherwise None (the existing attempt stands)."""
    now = now or datetime.now(timezone.utc)
    if recent is None:
        recent = _recent_rebuild_slugs(db, now)
    if slug in recent:
        return None
    return job_key(f"{key}:retry", now.date().isoformat())


def enqueue(db, queue, *, changed: dict[str, str], reason: str,
            expected: list[tuple[str, str, str]] | None = None,
            per: str = "artefact", previous: dict[str, str] | None = None,
            now: datetime | None = None, hold=None) -> dict:
    """Enqueue the rebuild set idempotently, keyed on what moved.

    The key carries the new fingerprint, so the same change enqueues once however many times
    this is called, and a *different* change enqueues again -- which is the distinction a
    key on the slug alone loses, and the reason a re-engineered product could once never
    re-enter the chain.
    """
    from ..queue.durable import DuplicateJob

    plan = rebuild_set(db, changed=changed, expected=expected)
    stamp = "-".join(f"{ref}={fp[:8]}" for ref, fp in sorted(changed.items()))

    enqueued, already = [], []
    if per == "product":
        # One job per product carrying that product's exact descendants in order. The chain
        # stage it drives rebuilds a whole product, so a job per artefact would run that
        # stage once per artefact for one change -- same result, many times the work. The
        # key still carries the new fingerprints, so the idempotency property is unchanged.
        by_product: dict[str, list[dict]] = {}
        for row in plan["rebuild"]:
            by_product.setdefault(row["product_slug"], []).append(row)
        retried: list[str] = []
        held: dict[str, str] = {}
        waiting: list[str] = []
        recent: set[str] | None = None
        inflight: set[str] | None = None
        failed: dict[str, list[dict]] | None = None
        legacy_failed: dict[str, int] = {}
        priors: dict[str, str] | None = None
        for slug, rows in sorted(by_product.items()):
            key = job_key(f"rebuild:product:{slug}", stamp)
            # eng/stale-rebuild-loop: only the refs this product's artefacts record. The
            # verify pass requires every named ref to read its new fingerprint on the row, so
            # naming another product's design here made a correctly rebuilt row unbound.
            own_refs = {ref for r in rows for ref in (r.get("refs") or [])} or set(changed)
            change = change_id(changed, own_refs)
            payload = {"product_slug": slug, "change_id": change,
                       "artefacts": [r["key"] for r in rows],
                       "reason": reason, "changed": plan["changed"],
                       "fingerprints": {
                           ref: {"old": (previous or {}).get(ref), "new": fp}
                           for ref, fp in sorted(changed.items()) if ref in own_refs}}
            # Review M-B of 4b683993, keyed per product (LOW of 0d2e6cbc): a change of this
            # product's whose attempts all died or were refused (never reaching verify) is
            # held, named and filed after REBUILD_MAX_ATTEMPTS -- whether it arrives as a
            # retry or under a new estate-wide key because another product's ref moved.
            if failed is None:
                failed, legacy_failed = _failed_attempts_by_change(
                    db, by_product, now=now or datetime.now(timezone.utc))
            fails = failed.get(f"{slug}|{change}") or []
            if len(fails) >= REBUILD_MAX_ATTEMPTS:
                held[slug] = "held: " + _hold_failed_change(
                    db, slug, key, fails, artefacts=payload["artefacts"],
                    fingerprints=payload["fingerprints"], change=change,
                    legacy_failures=legacy_failed.get(slug, 0), now=now)
                continue
            # eng/halt-380: the key carries the estate-wide change set, so any *other*
            # product's ref moving (a re-engineered design, a new release) minted a new key
            # for this product while its change was unchanged. That new key skipped the
            # in-flight check, RETRY_AFTER and the hold below, and -- carrying the same stage
            # token -- deduplicated onto the first attempt's stage job, so nothing was ever
            # rebuilt again and the verify passes never bound (production 7b250d61: 12
            # products stale and rebuild-incomplete, a fresh pending rebuild every hour, no
            # verified rebuild since the chain moved). An earlier attempt at this product's
            # own change routes through the existing attempt's key instead.
            if priors is None:
                priors = _prior_attempt_keys(db, by_product, now=now or datetime.now(
                    timezone.utc))
            prior = priors.get(f"{slug}|{change}")
            if prior is not None:
                key = prior
            try:
                if prior is not None:
                    raise DuplicateJob(key, -1)     # that attempt stands: retry rules below
                queue.enqueue("listing", "chain.rebuild", payload, idempotency_key=key)
                enqueued.extend(r["key"] for r in rows)
            except DuplicateJob:
                # W4-PRODFIX: the key names the change, so an attempt that ended without
                # delivering it (refused downstream, rebuild-incomplete) held the key for
                # good and the artefacts were never asked for again -- production 051dbee2
                # had 299 stale artefacts and no rebuild for days. Once the last attempt
                # for this product is terminal and old enough, ask again, once a day.
                if recent is None:
                    recent = _recent_rebuild_slugs(db, now or datetime.now(timezone.utc))
                again = _retry_key(db, slug, key, now=now, recent=recent)
                # INTEG7 (review S-2): no daily retry while an owner- or policy-gated reason
                # refuses this product's rebuild; it resumes when the gate clears.
                held_why = hold(slug) if (again and hold is not None) else None
                if held_why:
                    # held is held, not queued: the product has no job in flight
                    held[slug] = held_why
                    continue
                if again:
                    try:
                        queue.enqueue("listing", "chain.rebuild",
                                      {**payload, "retry_of_key": key, "retry": again},
                                      idempotency_key=again)
                        enqueued.extend(r["key"] for r in rows)
                        retried.append(slug)
                        continue
                    except DuplicateJob:
                        pass
                # eng/stale-rebuild-loop (production ea3aacc7: 50 "already queued", zero
                # unfinished jobs): "already queued" means a job for this change is in
                # flight. An attempt that ended and is waiting out RETRY_AFTER, or whose
                # retry for today has run, is reported as waiting -- not as queued work.
                if inflight is None:
                    inflight = _inflight_slugs(db)
                if slug in inflight:
                    already.extend(r["key"] for r in rows)
                else:
                    waiting.append(slug)
        return {"enqueued": enqueued, "already_queued": already, "retried": retried,
                "retry_held": held, "retry_waiting": waiting,
                "plan": plan, "reason": reason, "per": per,
                "idempotency": ("keyed on the product and the new fingerprint, so the same "
                                "change enqueues once and a different change enqueues again")}

    for row in plan["rebuild"]:
        key = job_key(f"rebuild:{row['key']}", stamp)
        try:
            queue.enqueue("listing", "chain.rebuild",
                          {"product_slug": row["product_slug"],
                           "artefact_class": row["artefact_class"],
                           "artefact_key": row["artefact_key"],
                           "reason": reason, "changed": plan["changed"]},
                          idempotency_key=key)
            enqueued.append(row["key"])
        except DuplicateJob:
            already.append(row["key"])

    return {"enqueued": enqueued, "already_queued": already,
            "plan": plan, "reason": reason,
            "idempotency": ("keyed on the new fingerprint, so the same change enqueues once "
                            "and a different change enqueues again")}


def blocks_publication(db, *, changed: dict[str, str], rebuilt: set[str]) -> dict:
    """Whether publication may proceed, which it may not until every descendant is remade."""
    plan = rebuild_set(db, changed=changed)
    outstanding = [row["key"] for row in plan["rebuild"] if row["key"] not in rebuilt]
    return {
        "may_publish": not outstanding,
        "outstanding": outstanding,
        "why": ("every descendant has been rebuilt" if not outstanding else
                f"{len(outstanding)} descendant(s) still carry the old input. Publishing now "
                f"ships a set that is partly current, which is harder to find than one that "
                f"is wholly stale"),
    }


def publication_gate(db, *, slug: str, current: dict[str, str] | None = None) -> dict:
    """#172 at the publish path: may this product publish, given what has moved upstream?

    `changed` is every upstream reference a recorded artefact of this product was built from
    that has since moved (old and new fingerprint kept); `rebuilt` is every node whose
    upstreams all match now, which is the completion evidence -- a descendant is rebuilt
    when its provenance row says it was made from the current input, not when a job said so.
    """
    from .artefacts import FRESH, STALE, current_from_db

    current = current if current is not None else current_from_db(db)
    verdicts = check(db, current=current)
    changed: dict[str, str] = {}
    previous: dict[str, str] = {}
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    recorded = {(r.artefact_class, r.artefact_key): (r.inputs or {}, r.built_at)
                for r in db.scalars(select(ArtefactProvenance)
                                    .where(ArtefactProvenance.product_slug == slug))}
    for v in verdicts:
        if v.product_slug != slug or v.state != STALE:
            continue
        inputs = recorded.get((v.artefact_class, v.artefact_key), ({}, None))[0]
        for ref in v.moved:
            if ref in current:
                changed[ref] = current[ref]
                previous[ref] = inputs.get(ref)
    rebuilt = {_node_key(v.artefact_class, v.artefact_key) for v in verdicts
               if v.state == FRESH}
    unprovable = sorted(_node_key(v.artefact_class, v.artefact_key) for v in verdicts
                        if v.product_slug == slug and v.state == STALE and v.unknown
                        and not v.moved)
    verdict = (blocks_publication(db, changed=changed, rebuilt=rebuilt) if changed
               else {"may_publish": True, "outstanding": [], "why": "nothing upstream moved"})
    nodes = load_graph(db)["nodes"]
    # eng/halt-380-verify: a node the check reads RETIRED (its frame row dropped, its draft
    # superseded, its slug retired) is no descendant to remake: nothing exists to ship stale.
    # Counted, it kept `may_publish` false for good and -- being non-marketing -- refused the
    # product's marketing rebuild on every attempt.
    from .artefacts import retired as _retired

    gone = {_node_key(v.artefact_class, v.artefact_key) for v in verdicts if _retired(v)}
    outstanding = [k for k in verdict["outstanding"]
                   if k in nodes and nodes[k].product_slug == slug and k not in gone]
    evidence = [{"key": _node_key(c, k), "built_at": str(built)}
                for (c, k), (_, built) in sorted(recorded.items())
                if _node_key(c, k) in rebuilt]
    fresh = sorted(_node_key(v.artefact_class, v.artefact_key) for v in verdicts
                   if v.product_slug == slug and v.state == FRESH)
    return {
        "slug": slug, "may_publish": not outstanding, "outstanding": outstanding,
        # eng/stale-rebuild-loop: every artefact of this product that reads FRESH now, so a
        # gate can tell a sentinel row awaiting its next sweep from a live staleness.
        "fresh": fresh,
        # eng/halt-380-marketing: every artefact of this product the check reads RETIRED now
        # (a superseded draft, a dropped frame). Its sentinel row, if one is open, awaits the
        # next sweep's "retired, not stale" close exactly as a FRESH one awaits "rebuilt".
        "retired": sorted(_node_key(v.artefact_class, v.artefact_key) for v in verdicts
                          if v.product_slug == slug and _retired(v)),
        "changed": {ref: {"old": previous.get(ref), "new": fp}
                    for ref, fp in sorted(changed.items())},
        "rebuilt_evidence": evidence[:40],
        # Reported, not blocking here: an upstream with no current fingerprint is the
        # sentinel's to raise (it halts through the incident flag the publish path reads).
        "unprovable": unprovable,
        "why": (f"{len(outstanding)} descendant(s) of this product still carry the old "
                f"input: {outstanding[:5]}" if outstanding
                else "every descendant has been rebuilt or no longer exists"
                if verdict["outstanding"] else verdict["why"]),
    }


def state() -> dict:
    """Where the edges come from, and what the graph does not cover."""
    return {
        "edges_from": ("ops.artefacts' provenance rows. A dependency graph kept beside them "
                       "would be a second answer to what an artefact depends on, and the two "
                       "would agree until the day it mattered"),
        "artefact_classes": sorted(ARTEFACT_CLASSES),
        "order": "topological, parents before children",
        "refuses": ["a cycle, which is a rebuild that does not terminate"],
        "note": ("The number that matters is the one the graph cannot see: an estate whose "
                 "artefacts carry no provenance produces a propagation that touches nothing "
                 "and reports that no rebuild is needed -- true of the graph, false of the "
                 "shop (#172)."),
    }
