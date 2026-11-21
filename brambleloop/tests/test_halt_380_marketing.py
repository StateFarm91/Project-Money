"""eng/halt-380-marketing: why production's 102 marketing_asset rows never rebuilt or closed.

Production dc10a48d, readback 2026-11-21T10:35Z: 112 open stale-artefact incidents, of which
marketing_asset 102 (unversioned `slug:channel:digest` keys), 8 current-release core rows
(pricing, listing_copy, seo, release_bundle; 2 each) plus support_knowledge 1, and the
non-halting instrumentation backlog row (`stale-artefact:backlog`: the "unrecognised / no_row"
one). Moved upstreams: chain 111, cir 94, release 94. 12 products rebuild-incomplete.

What the real chain shows (the suite below, 12 products on cir.compile -> ... ->
marketing.schedule, the real ops.sentinel and chain.rebuild):

* The rebuild order is already core first. A targeted rebuild of a product whose core rows and
  marketing are both stale enqueues ONE stage (pricing.position), which rewrites pricing,
  listing_copy, seo and support_knowledge (listing.seo) and the release bundle (launch.plan)
  before launch.plan enqueues marketing.schedule. So marketing.schedule reads nothing
  non-marketing outstanding and is never refused on #172. The suite asserts the order from
  the job ids that wrote each row.
* Marketing rows of the CURRENT plan are rewritten by every rebuild that reaches
  marketing.schedule, whatever release they were recorded under.
* What never closed was the rest: pieces of an earlier plan. Before eng/halt-380-verify
  nothing superseded them. Since then only `drafted` pieces have been superseded, so a piece
  of an earlier plan in any other unpublished state ("held", "approved", "scheduled") read
  STALE for good. No stage rewrites a piece the plan no longer contains, and every attempt
  named it outstanding.
* Defect 2 (found by the production-shape run): once a rebuild superseded those pieces, their
  stale-artefact rows stay open until the next hourly sweep closes them "retired, not stale".
  Until then a marketing.schedule of the product (here a parity-escalation chain) was
  refused "halted (#173)". The rows only waived for the marketing rebuild were FRESH or still
  outstanding, and with nothing outstanding the exception also needed a pending
  rebuild-incomplete row.
* Defect 3: a superseded piece that came back into the plan stayed `superseded` while its row
  was rewritten. When it next went stale it would read RETIRED: real staleness hidden.

Fixes: marketing.schedule supersedes every piece its current plan no longer contains unless
it was PUBLISHED, recording the prior state and the reason. Published content is never
superseded or retired. It is listed (`published_out_of_plan`), its row stays STALE and it
keeps the product halted. A superseded piece back in the plan is restored to `drafted`.
`artefacts._vanished_lookup` never retires a superseded piece that carries any sign of
publication. For the marketing rebuild only, `release_gates.staleness` waives a sentinel row
whose artefact reads RETIRED, as it already waived FRESH. With nothing outstanding, it lets
the rebuild proceed when every halting row is one the sweep will close. Publication still
reads every row.

Run: cd brambleloop && python3 tests/test_halt_380_marketing.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_stale_rebuild_loop as base  # noqa: E402  (db factory, sentinel, drain)
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (ArtefactProvenance, AuditLog, ContentPiece,  # noqa: E402
                                     Incident, Job, JobStatus, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.runtime import release  # noqa: E402

CORE = ("pricing", "listing_copy", "seo", "release_bundle", "support_knowledge")
OLD_CIR = A.fingerprint("an earlier release's cir")[:16]       # the release the rows were
OLD_RELEASE = A.fingerprint("an earlier release")[:16]   # recorded under (cir, release moved)
# unpublished states of an earlier plan's pieces, as production's 102 rows carry them
ORPHAN_STATES = ("drafted", "held", "approved", "scheduled")
PUBLISHED_TITLE = "Our earliest pin, already live"


def _build_catalogue():
    """The real chain, once, for the twelve production slugs that have a builder (the drain
    also builds the rest of the Launch-0 catalogue). Returns (db, the twelve slugs)."""
    from brambleloop.products import builder
    from brambleloop.queue.durable import JobQueue

    db = base._sqlite_db()
    q = JobQueue(db)
    for n, slug in enumerate(base.LIVE):
        cir = builder.for_slug(slug)
        if cir is not None:
            q.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                      idempotency_key=f"h380m-compile-{n}")
    base._drain(db, "h380m-build", limit=3000)
    with db.session() as s:
        with_marketing = sorted({r.product_slug for r in s.scalars(
            select(ArtefactProvenance).where(
                ArtefactProvenance.artefact_class == "marketing_asset"))})
    preferred = [s_ for s_ in base.LIVE if s_ in with_marketing]
    slugs = (preferred + [s_ for s_ in with_marketing if s_ not in preferred])[:12]
    assert len(slugs) == 12, with_marketing
    return db, slugs


def _production_shape(db, slugs):
    """Production's shape, under the chain fingerprint BEFORE the move (as every row was):

    * every product's marketing rows recorded from an older release (cir and release moved);
    * an earlier plan's pieces left beside the current ones, one per product, cycling
      through the unpublished states; one more, PUBLISHED, on the first product;
    * the first two products' current-release core rows (pricing, listing_copy, seo,
      release_bundle, support_knowledge) under the old chain, like production's 9;
    * everything else (PDFs, charts, frames, certificates) already rebuilt under the new
      chain, so it reads fresh, as production's by_class shows.
    Returns {slug: {"orphans": {key: state}, "published": key|None}}."""
    new = A.chain_fingerprint()                 # called inside _MovedChain: the new chain
    core_stale = set(slugs[:2])
    plan = {}
    with db.session() as s:
        for n, slug in enumerate(slugs):
            plan[slug] = {"orphans": {}, "published": None}
            state = ORPHAN_STATES[n % len(ORPHAN_STATES)]
            title = f"An earlier plan's piece {n} ({state})"
            s.add(ContentPiece(product_slug=slug, channel="pinterest", title=title,
                               body="written for an earlier release", state=state))
            plan[slug]["orphans"][A.marketing_key(slug, "pinterest", title)] = state
            if n == 0:
                s.add(ContentPiece(product_slug=slug, channel="email", title=PUBLISHED_TITLE,
                                   body="sent to the list", state="published",
                                   detail={"published_at": "2026-11-01T12:00:00Z"}))
                plan[slug]["published"] = A.marketing_key(slug, "email", PUBLISHED_TITLE)
        s.flush()
        for r in s.scalars(select(ArtefactProvenance)):
            inputs = dict(r.inputs or {})
            if r.product_slug not in plan:
                # the rest of the catalogue is current: only the twelve are halted
                if "chain:release" in inputs:
                    inputs["chain:release"] = new
            elif r.artefact_class == "marketing_asset":
                inputs[f"cir:{r.product_slug}"] = OLD_CIR
                if f"release:{r.product_slug}" in inputs:
                    inputs[f"release:{r.product_slug}"] = OLD_RELEASE
            elif r.artefact_class in CORE and r.product_slug in core_stale:
                pass                                # stays under the old chain
            elif "chain:release" in inputs:
                inputs["chain:release"] = new
            r.inputs = inputs
        for slug, p in plan.items():
            design = {f"cir:{slug}": OLD_CIR, f"release:{slug}": OLD_RELEASE,
                      "chain:release": A.fingerprint(release.CHAIN_VERSION[:-len("-moved")])}
            for key in list(p["orphans"]) + ([p["published"]] if p["published"] else []):
                A.record(s, artefact_class="marketing_asset", artefact_key=key,
                         product_slug=slug, inputs=design)
    return plan


def _drain_attempt(db):
    for _ in range(6):                           # the stage chain, then each verify check
        base._drain(db, "h380m-drain", limit=3000)
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.run_after = utcnow()           # the 20-minute verify delay, elapsed


def test_production_shape_twelve_products_marketing_rebuilds_after_core_and_old_plans_retire():
    restore = base._no_policy()
    try:
        _run_production_shape()
    finally:
        restore()


def _run_production_shape():
    db, slugs = _build_catalogue()
    with base._MovedChain():
        plan = _production_shape(db, slugs)
        with db.session() as s:
            first_audit = s.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1))
            verdicts = [v for v in A.check(s, current=A.current_from_db(s))
                        if v.product_slug in slugs]
        stale = [v for v in verdicts if v.state == A.STALE]
        by_class = {}
        for v in stale:
            by_class[v.artefact_class] = by_class.get(v.artefact_class, 0) + 1
        # production's shape: marketing dominates (8-9 rows a product plus the earlier plan),
        # and the two products' core rows are the only non-marketing staleness
        assert set(by_class) == {"marketing_asset", *CORE}, by_class
        assert all(by_class[c] == 2 for c in CORE), by_class
        assert by_class["marketing_asset"] >= 12 * 8, by_class
        assert all(set(v.moved) >= {"chain:release", f"cir:{v.product_slug}"}
                   for v in stale if v.artefact_class == "marketing_asset"), stale[:3]

        out = base._sentinel(db, "h380m-1")
        assert out["rebuild_enqueued"], out
        with db.session() as s:
            ev = L.escalate_systemic(s)
        assert ev["systemic"] and "stale-artefact" in ev["widespread_families"], ev
        _drain_attempt(db)

        with db.session() as s:
            audits = list(s.scalars(select(AuditLog).where(AuditLog.id > first_audit)))
            verified = {}
            for a in audits:
                if a.action == "chain.rebuild_verified":
                    verified.setdefault(a.artifact.split("@")[0], []).append(a.detail)
            blocked = [(a.artifact, (a.detail or {}).get("reasons"))
                       for a in audits if a.action == "marketing.blocked"
                       and a.artifact.split("@")[0] in slugs]
            scheduled: dict[str, dict] = {}      # every marketing.scheduled of the attempt
            for a in audits:
                if a.action == "marketing.scheduled":
                    got = scheduled.setdefault(a.artifact.split("@")[0], {
                        "superseded_drafts": [], "published_out_of_plan": []})
                    for k in got:
                        got[k] += list((a.detail or {}).get(k) or [])
            pieces = {(p.product_slug, A.marketing_key(p.product_slug, p.channel, p.title)): p
                      for p in s.scalars(select(ContentPiece).where(
                          ContentPiece.product_slug.in_(slugs)))}
            rows = {(r.artefact_class, r.artefact_key): r for r in s.scalars(
                select(ArtefactProvenance).where(ArtefactProvenance.product_slug.in_(slugs)))}
            jobs = {j.id: j.job_type for j in s.scalars(select(Job))}
            after = {v.artefact_class + ":" + v.artefact_key: v
                     for v in A.check(s, current=A.current_from_db(s))
                     if v.product_slug in slugs}

        # marketing.schedule was never refused for any of the twelve (base: it ran, but the
        # earlier plan's non-draft pieces stayed outstanding on every check)
        assert blocked == [], blocked
        # what each product's last verify check left outstanding: only published content
        # (base: every product whose earlier-plan piece is not a draft keeps it outstanding)
        left_by_slug = {slug: (verified[slug][-1]["outstanding"] if slug in verified
                               else "never verified") for slug in slugs}
        want = {slug: ([f"marketing_asset:{plan[slug]['published']}"]
                       if plan[slug]["published"] else []) for slug in slugs}
        assert left_by_slug == want, {s_: (left_by_slug[s_], verified.get(s_, [{}])[-1].get(
            "outstanding_read")) for s_ in slugs if left_by_slug[s_] != want[s_]}
        for slug in slugs:
            expected_left = want[slug]
            # every unpublished piece of the earlier plan: superseded with its prior state,
            # its row retired with the check's reason
            assert plan[slug]["orphans"], slug
            for key, state in plan[slug]["orphans"].items():
                piece = pieces[(slug, key)]
                assert piece.state == A.CONTENT_SUPERSEDED, (slug, key, piece.state)
                by = piece.detail["superseded_by"]
                assert by["prior_state"] == state and by["reason"], by
                assert A.retired(after[f"marketing_asset:{key}"]), after[f"marketing_asset:{key}"]
                assert key in scheduled[slug]["superseded_drafts"], scheduled[slug]
            # nothing of the product reads STALE but published content
            left = [k for k, v in after.items() if v.product_slug == slug and v.state == A.STALE]
            assert left == expected_left, (slug, left)

        # core before marketing, on the real chain: for the two products with stale core
        # rows, the job that rewrote each core row ran before the marketing.schedule job that
        # rewrote the product's marketing rows
        for slug in slugs[:2]:
            core_jobs = [rows[(c, k)].job_id for (c, k) in rows
                         if c in CORE and rows[(c, k)].product_slug == slug]
            marketing_jobs = {rows[(c, k)].job_id for (c, k) in rows
                              if c == "marketing_asset" and rows[(c, k)].product_slug == slug
                              and after[f"{c}:{k}"].state == A.FRESH}
            assert core_jobs and marketing_jobs, (slug, core_jobs, marketing_jobs)
            assert {jobs[j] for j in marketing_jobs} == {"marketing.schedule"}, marketing_jobs
            assert max(core_jobs) < min(marketing_jobs), (slug, core_jobs, marketing_jobs)

        # published content is never retired: listed, still STALE, still halting its product
        owner = slugs[0]
        pub = plan[owner]["published"]
        assert pieces[(owner, pub)].state == "published", pieces[(owner, pub)].state
        assert pub in scheduled[owner]["published_out_of_plan"], scheduled[owner]
        assert after[f"marketing_asset:{pub}"].state == A.STALE, after[f"marketing_asset:{pub}"]

        second = base._sentinel(db, "h380m-2")
        with db.session() as s:
            ev = L.escalate_systemic(s)
        # only the published piece still reads stale (the estate-wide chain change may list
        # other products' rows again; they read fresh, so their attempt rebuilds nothing)
        assert second["stale"] == 1 and second["rebuild"] == [owner], second
        with db.session() as s:
            open_rows = {i.signature: i for i in s.scalars(select(Incident).where(
                Incident.resolved == False))}  # noqa: E712
            gate = G.publication_gate(s, slug=owner)
            closed = {i.signature: (i.detail or {}).get("resolution") for i in s.scalars(
                select(Incident).where(Incident.signature.like("stale-artefact:%"),
                                       Incident.resolved == True))}  # noqa: E712
        stale_open = sorted(k for k in open_rows if k.startswith("stale-artefact:")
                            and k != "stale-artefact:backlog")
        assert stale_open == [f"stale-artefact:marketing_asset:{pub}"], stale_open
        assert not [k for k in open_rows if k.startswith("rebuild-incomplete:")
                    and k.split(":", 1)[1] != owner], sorted(open_rows)
        for slug in slugs:
            assert plan[slug]["orphans"], slug
            for key in plan[slug]["orphans"]:
                assert str(closed.get(f"stale-artefact:marketing_asset:{key}", "")).startswith(
                    "retired, not stale"), (key, closed.get(f"stale-artefact:marketing_asset:{key}"))
        # one product held by its own public copy is not systemic: the company-wide halt is
        # resolved and the product stays halted
        assert not ev["systemic"] and ev["resolved"], ev
        assert f"marketing_asset:{pub}" in gate["outstanding"], gate


def test_out_of_plan_rule_publication_is_never_retired():
    """The rule's edges, without the chain: what counts as published, and that the check
    never retires a superseded piece carrying a sign of publication."""
    assert A.content_published("published") and A.content_published("Live")
    assert A.content_published("sent") and A.content_published("posted")
    assert A.content_published("drafted", {"published_at": "2026-11-01T00:00:00Z"})
    assert A.content_published("held", {"published_url": "https://example.invalid/p"})
    unpublished = ORPHAN_STATES + ("superseded", "", None)
    assert len(unpublished) == 7
    for state in unpublished:
        assert not A.content_published(state, {}), state

    from brambleloop.core.models import Product

    db = base._sqlite_db()
    with db.session() as s:
        s.add(Product(slug="p", title="p"))
        s.add(ContentPiece(product_slug="p", channel="email", title="was sent",
                           state=A.CONTENT_SUPERSEDED,
                           detail={"published_at": "2026-11-01T00:00:00Z"}))
        s.add(ContentPiece(product_slug="p", channel="pinterest", title="never sent",
                           state=A.CONTENT_SUPERSEDED, detail={}))
        s.flush()
        old = {"chain:release": "0" * 16}
        for ch, title in (("email", "was sent"), ("pinterest", "never sent")):
            A.record(s, artefact_class="marketing_asset",
                     artefact_key=A.marketing_key("p", ch, title), product_slug="p",
                     inputs=old)
        got = {v.artefact_key: v for v in A.check(s, current=A.current_from_db(s))}
    sent = got[A.marketing_key("p", "email", "was sent")]
    never = got[A.marketing_key("p", "pinterest", "never sent")]
    assert sent.state == A.STALE and not A.retired(sent), sent
    assert A.retired(never), never


def test_an_open_row_of_retired_content_does_not_refuse_the_marketing_rebuild():
    """Reproduced in the production-shape run: after an attempt superseded an earlier plan's
    piece, the piece's stale-artefact row stays open until the next hourly sweep closes it
    "retired, not stale". Until then it counted as a halt OTHER than the product's own
    staleness, so every marketing.schedule of the product (here a parity-escalation chain)
    was refused "halted (#173)". It is now waived for the marketing rebuild exactly like a
    row whose artefact reads FRESH. Guards: publication still reads it, and a genuinely STALE
    non-marketing row still refuses the marketing rebuild."""
    from brambleloop.core.models import Product
    from brambleloop.publish import release_gates

    db = base._sqlite_db()
    old = {"chain:release": "0" * 16}
    with db.session() as s:
        s.add(Product(slug="p", title="p"))
        s.add(ContentPiece(product_slug="p", channel="pinterest", title="earlier plan",
                           state=A.CONTENT_SUPERSEDED, detail={"superseded_by": {"job": 1}}))
        s.add(ContentPiece(product_slug="p", channel="pinterest", title="current plan",
                           state="drafted"))
        s.flush()
        gone = A.marketing_key("p", "pinterest", "earlier plan")
        live = A.marketing_key("p", "pinterest", "current plan")
        for key in (gone, live):
            A.record(s, artefact_class="marketing_asset", artefact_key=key, product_slug="p",
                     inputs=old)
            s.add(Incident(severity="P1", signature=f"stale-artefact:marketing_asset:{key}",
                           halts_publication=True, product_slug="p", summary="stale",
                           detail={}))
    got = release_gates.staleness(db, slug="p")
    assert f"marketing_asset:{gone}" in got["rebuild"]["retired"], got["rebuild"]
    assert got["rebuild"]["outstanding"] == [f"marketing_asset:{live}"], got["rebuild"]
    assert got["outstanding_only_marketing"] is True, got
    assert got["blocks"] and got["halted"], got                 # publication still halted

    # guard: a STALE non-marketing artefact of the product still refuses the rebuild
    with db.session() as s:
        A.record(s, artefact_class="pdf", artefact_key="p@1.0.0#pdf-us", product_slug="p",
                 inputs=old)
        s.add(Incident(severity="P1", signature="stale-artefact:pdf:p@1.0.0#pdf-us",
                       halts_publication=True, product_slug="p", summary="stale", detail={}))
    got = release_gates.staleness(db, slug="p")
    assert got["outstanding_only_marketing"] is False, got

    # after the rebuild delivered: nothing outstanding, only the retired piece's row open
    # (the parity-escalation chain of the production-shape run). It may proceed...
    db = base._sqlite_db()
    with db.session() as s:
        s.add(Product(slug="q", title="q"))
        s.add(ContentPiece(product_slug="q", channel="pinterest", title="earlier plan",
                           state=A.CONTENT_SUPERSEDED, detail={"superseded_by": {"job": 1}}))
        s.flush()
        gone = A.marketing_key("q", "pinterest", "earlier plan")
        A.record(s, artefact_class="marketing_asset", artefact_key=gone, product_slug="q",
                 inputs=old)
        s.add(Incident(severity="P1", signature=f"stale-artefact:marketing_asset:{gone}",
                       halts_publication=True, product_slug="q", summary="stale", detail={}))
    got = release_gates.staleness(db, slug="q")
    assert got["rebuild"]["outstanding"] == [] and got["halted"], got
    assert got["outstanding_only_marketing"] is True, got
    assert got["blocks"], got                                   # publication still halted
    # ...but never past a halt that is not the product's own staleness
    with db.session() as s:
        s.add(Incident(severity="P1", signature="terms-divergence:q", halts_publication=True,
                       product_slug="q", summary="terms diverge", detail={}))
    got = release_gates.staleness(db, slug="q")
    assert got["outstanding_only_marketing"] is False, got


def test_a_superseded_piece_back_in_the_plan_is_a_draft_again():
    """A piece an earlier plan superseded and the current plan contains again is restored to
    `drafted`, so its row is judged as live content when it next goes stale (left superseded,
    the check would read its staleness as RETIRED)."""
    from brambleloop.products import builder
    from brambleloop.queue.durable import JobQueue

    slug = "cloudline-baby-blanket"
    db = base._sqlite_db()
    JobQueue(db).enqueue("validator", "cir.compile",
                         {"cir": builder.for_slug(slug).to_dict()},
                         idempotency_key="h380m-restore-compile")
    base._drain(db, "h380m-restore", limit=3000)
    with db.session() as s:
        piece = s.scalar(select(ContentPiece).where(ContentPiece.product_slug == slug,
                                                    ContentPiece.channel == "pinterest"))
        piece.state = A.CONTENT_SUPERSEDED
        piece.detail = dict(piece.detail or {}, superseded_by={"job": 0})
        key = A.marketing_key(slug, piece.channel, piece.title)
    with base._MovedChain():
        base._sentinel(db, "h380m-restore-1")
        _drain_attempt(db)
        with db.session() as s:
            piece = s.scalar(select(ContentPiece).where(
                ContentPiece.product_slug == slug, ContentPiece.channel == "pinterest",
                ContentPiece.title == piece.title))
            v = {x.artefact_key: x for x in A.check(s, current=A.current_from_db(s))}[key]
    assert piece.state == "drafted", piece.state
    assert piece.detail.get("restored_by"), piece.detail
    assert v.state == A.FRESH, v
    # and once it is live content again, a later move reads it STALE, never retired
    with base._MovedChain("-moved-again"):
        with db.session() as s:
            v = {x.artefact_key: x for x in A.check(s, current=A.current_from_db(s))}[key]
    assert v.state == A.STALE and not A.retired(v), v


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)
             and (len(sys.argv) < 2 or any(a in n for a in sys.argv[1:]))]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
