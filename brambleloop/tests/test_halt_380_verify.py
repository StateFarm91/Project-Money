"""eng/halt-380-verify: why a chain.rebuild that runs ends without verifying.

Production 1bb7c4f5 (H1, H3, H4 deployed), readback 2026-11-21T08:20Z: systemic halt #380
open; 112 open stale-artefact incidents, 12 rebuild-incomplete; chain.rebuild 7 d done 199,
unfinished 0; rebuilds_verified_24h 8 with the newest at 2026-11-20T13:12Z, so no recent
attempt completed a single artefact; 14 products waiting out RETRY_AFTER.

Cause, reproduced below on the real chain (cir.compile -> ... -> marketing.schedule, the
real ops.sentinel and chain.rebuild handlers): a provenance row whose artefact NO LONGER
EXISTS reads STALE for good, and no stage can rewrite it.

* `_persist_frames` deletes the gallery rows a rebuild did not place (review 6817652112 N2)
  and leaves their `visual_truth` rows behind, keyed by the deleted row id.
* `marketing.schedule` drafts the current content plan; a draft from an earlier plan (an
  earlier title, estimate, collection or positioning) keeps its row under its old title.

The first attempt after a chain move remakes everything that exists and verifies it (the 8),
and names the orphans outstanding. Worse, an orphan that is not marketing content made
`release_gates.staleness` refuse `only_own_marketing_stale`, so marketing.schedule refused
the product's REAL marketing rebuild on "rebuild outstanding (#172)". Every later attempt's
outstanding set is then the orphans plus that refused marketing: it completes nothing, opens
`rebuild-incomplete` (refused_by: the product's own staleness), waits RETRY_AFTER and repeats.

Fixes: `artefacts.check` reads such a row RETIRED (its exact key shape, its row gone or its
draft superseded; anything else fails closed), marketing.schedule supersedes drafts its plan
no longer contains (drafts only), and the verify pass, the sentinel's rebuild-incomplete
judgement and `rebuild_graph.publication_gate` set retired names aside.

Second defect: a rebuild refused by a REAL gate of its own chain (certification, a withheld
release, image/listing/pricing gates, a missed launch window, a child-safety decision) was
recorded only as "the stage ran and did not rewrite them" and counted toward the company-wide
staleness halt. It now parks the product on that gate with its reason; the product stays
halted, and `systemic_evidence` does not count a parked product toward the staleness
families. The product's own staleness is never mistaken for a gate.

Run: cd brambleloop && python3 tests/test_halt_380_verify.py
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
                                     Incident, Job, JobStatus, ListingAsset, PatternVersion,
                                     Product, utcnow)
from brambleloop.gates.incidents import IncidentTracker  # noqa: E402
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.runtime import release  # noqa: E402

SLUG = "cloudline-baby-blanket"    # one of production's twelve; evergreen, so no launch window
OLD_TITLE = "About 3–5 hours"       # a pin of an earlier plan (an earlier estimate)


# --- the production shape on the real chain -------------------------------------------------

def _built_with_orphans():
    """A real chain build of SLUG, then the two orphans production carries, recorded under
    the chain fingerprint BEFORE the move (as every row there was)."""
    from brambleloop.products import builder
    from brambleloop.queue.durable import JobQueue

    db = base._sqlite_db()
    cir = builder.for_slug(SLUG)
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="h380v-compile")
    base._drain(db, "h380v-build")
    with db.session() as s:
        pid = s.scalar(select(Product.id).where(Product.slug == SLUG))
        version = A.newest_release(s, pid).version
        design = A.design_inputs(s, SLUG, version)
        frame_ids = [i for (i,) in s.execute(select(ListingAsset.id).where(
            ListingAsset.product_slug == SLUG))]
        assert frame_ids, "the chain placed no gallery frame"
        dropped = max(frame_ids) + 1000          # a frame a later gallery rebuild dropped
        s.add(ContentPiece(product_slug=SLUG, channel="pinterest", title=OLD_TITLE,
                           body="an earlier plan's pin", state="drafted"))
        A.record(s, artefact_class="marketing_asset",
                 artefact_key=A.marketing_key(SLUG, "pinterest", OLD_TITLE),
                 product_slug=SLUG, inputs=design)
        A.record(s, artefact_class="visual_truth",
                 artefact_key=A.visual_key(SLUG, version, dropped),
                 product_slug=SLUG, inputs=design)
    orphans = {f"marketing_asset:{A.marketing_key(SLUG, 'pinterest', OLD_TITLE)}",
               f"visual_truth:{A.visual_key(SLUG, version, dropped)}"}
    return db, version, orphans


def _drain_attempt(db):
    for _ in range(6):                           # the stage chain, then each verify check
        base._drain(db, "h380v-drain")
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.run_after = utcnow()           # the 20-minute delay, elapsed


def test_production_shape_a_rebuild_with_orphans_verifies_and_the_orphans_retire():
    db, version, orphans = _built_with_orphans()
    with db.session() as s:
        marketing = {f"marketing_asset:{r.artefact_key}" for r in s.scalars(
            select(ArtefactProvenance).where(
                ArtefactProvenance.product_slug == SLUG,
                ArtefactProvenance.artefact_class == "marketing_asset"))} - orphans
        first_audit = s.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1))
    assert marketing
    with base._MovedChain():
        out = base._sentinel(db, "h380v-1")
        assert out["rebuild_enqueued"], out
        _drain_attempt(db)
        with db.session() as s:
            verified = [a.detail for a in s.scalars(select(AuditLog).where(
                AuditLog.id > first_audit, AuditLog.action == "chain.rebuild_verified"))]
            completed = {a.artifact for a in s.scalars(select(AuditLog).where(
                AuditLog.id > first_audit, AuditLog.action == "chain.rebuild_completed"))
                if not (a.detail or {}).get("already_fresh")}
            refused = [a.detail for a in s.scalars(select(AuditLog).where(
                AuditLog.id > first_audit, AuditLog.action == "marketing.blocked"))]
            open_ = {i.signature: i.detail for i in s.scalars(select(Incident).where(
                Incident.resolved == False))}  # noqa: E712
            jobs = list(s.scalars(select(Job).where(Job.job_type == "chain.rebuild")))
            for j in jobs:
                s.expunge(j)
            old = s.scalar(select(ContentPiece).where(ContentPiece.product_slug == SLUG,
                                                      ContentPiece.title == OLD_TITLE))
            verdicts = {f"{v.artefact_class}:{v.artefact_key}": v
                        for v in A.check(s, current=A.current_from_db(s))}
        # On the base: check 1 completes 15 and leaves 10 outstanding (the 2 orphans plus all
        # 8 real marketing pieces, refused on "rebuild outstanding (#172)"), checks 2-3 and
        # every retry complete 0, and rebuild-incomplete opens.
        assert verified and verified[0]["outstanding"] == [], verified
        # the dropped frame is set aside by the first pass (it never existed to rebuild); the
        # earlier-plan draft once marketing.schedule superseded it, by the verify pass
        first_pass = [j.outputs or {} for j in jobs if not (j.inputs or {}).get("verify")]
        set_aside = {k for o in first_pass for k in o.get("retired") or []}
        set_aside |= set(verified[0]["retired"])
        assert set_aside == orphans, (set_aside, orphans)
        assert len(verified) == 1, verified              # verified on the first check
        assert marketing <= completed, sorted(marketing - completed)
        assert refused == [], refused
        assert not [k for k in open_ if k.startswith("rebuild-incomplete:")], sorted(open_)
        # what this attempt remade is closed by its verified evidence; what is left open is
        # only the superseded draft's row, which the sentinel's next sweep closes as retired
        assert {k for k in open_ if k.startswith("stale-artefact:")} <= {
            f"stale-artefact:{k}" for k in orphans}, sorted(open_)
        for k in orphans:
            assert A.retired(verdicts[k]), (k, verdicts[k])
        assert old.state == A.CONTENT_SUPERSEDED and old.detail.get("superseded_by"), old.state
        # every artefact that exists is fresh again; nothing of the product reads stale
        assert not [k for k, v in verdicts.items()
                    if v.product_slug == SLUG and v.state == A.STALE], verdicts
        second = base._sentinel(db, "h380v-2")
        assert second["stale"] == 0 and not second.get("rebuild_enqueued"), second
        with db.session() as s:
            rows = {i.signature: i for i in s.scalars(select(Incident).where(
                Incident.signature.like("stale-artefact:%")))}
        assert not [k for k, i in rows.items() if not i.resolved], sorted(rows)
        draft = next(f"stale-artefact:{k}" for k in orphans if k.startswith("marketing_asset:"))
        assert rows[draft].detail["resolution"].startswith("retired, not stale"), \
            rows[draft].detail
        with db.session() as s:
            gate = G.publication_gate(s, slug=SLUG)
        assert gate["outstanding"] == [], gate


def test_vanished_rule_is_narrow_and_fails_closed():
    """Only the exact key shapes, only when the artefact is really gone. A frame that exists,
    a draft still in the plan, content handed on (any non-draft state), a title no piece
    carries (pieces are never deleted, so absence proves nothing), another slug's key and
    every other shape stay STALE."""
    db = base._sqlite_db()
    old = A.chain_fingerprint()
    with db.session() as s:
        s.add(Product(slug="p", title="p"))
        s.flush()
        frame = ListingAsset(product_slug="p", version="1.0.0", position=1,
                             asset_class="DIGITAL_TWIN_RENDER", role="hero", sha256="a" * 64)
        s.add(frame)
        s.add(ContentPiece(product_slug="p", channel="pinterest", title="kept",
                           state="drafted"))
        s.add(ContentPiece(product_slug="p", channel="email", title="sent",
                           state="published"))
        s.add(ContentPiece(product_slug="p", channel="article", title="replaced",
                           state=A.CONTENT_SUPERSEDED))
        s.flush()
        rows = {
            "kept_frame": ("visual_truth", A.visual_key("p", "1.0.0", frame.id)),
            "gone_frame": ("visual_truth", A.visual_key("p", "1.0.0", frame.id + 50)),
            "other_version": ("visual_truth", A.visual_key("p", "2.0.0", frame.id)),
            "kept_draft": ("marketing_asset", A.marketing_key("p", "pinterest", "kept")),
            "published": ("marketing_asset", A.marketing_key("p", "email", "sent")),
            "superseded": ("marketing_asset", A.marketing_key("p", "article", "replaced")),
            "no_piece": ("marketing_asset", A.marketing_key("p", "teaser", "never")),
            "video": ("marketing_asset", "video:p:canonical:youtube"),
            "foreign": ("marketing_asset", A.marketing_key("q", "teaser", "never")),
            "pdf": ("pdf", A.pdf_key("p", "1.0.0", "US")),
        }
        for cls, key in rows.values():
            A.record(s, artefact_class=cls, artefact_key=key, product_slug="p",
                     inputs={"chain:release": old})
    with base._MovedChain():
        with db.session() as s:
            v = {f"{x.artefact_class}:{x.artefact_key}": x
                 for x in A.check(s, current=A.current_from_db(s))}
    state = {name: ("retired" if A.retired(v[f"{c}:{k}"]) else v[f"{c}:{k}"].state)
             for name, (c, k) in rows.items()}
    assert state == {"kept_frame": A.STALE, "gone_frame": "retired",
                     "other_version": "retired", "kept_draft": A.STALE,
                     "published": A.STALE, "superseded": "retired", "no_piece": A.STALE,
                     "video": A.STALE, "foreign": A.STALE, "pdf": A.STALE}, state
    # a fresh row is never retired, even when its artefact is gone (it harms nothing)
    with db.session() as s:
        v = {f"{x.artefact_class}:{x.artefact_key}": x
             for x in A.check(s, current=A.current_from_db(s))}
    assert v["visual_truth:" + rows["gone_frame"][1]].state == A.FRESH


# --- a real gate's refusal parks the product; its own staleness never does -------------------

class _Ctx:
    class _J:
        id = 10_000

    def __init__(self, db, requested_by):
        self.db, self.job = db, self._J()
        self.job.inputs = {"requested_by": requested_by, "stage_job": requested_by + 1}


def _estate(db, n):
    with db.session() as s:
        for k in range(n):
            p = Product(slug=f"p{k}", title="p")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"k": k},
                                 certified=True, release_hash="ab" * 16, certificate={}))
            s.add(Incident(severity="P2", signature=f"stale-artefact:pdf:p{k}@1.0.0#pdf-us",
                           halts_publication=True, product_slug=f"p{k}", summary="stale",
                           detail={}))
        for _ in range(2):          # an older attempt's job, then this attempt's first pass
            s.add(Job(agent="listing", job_type="chain.rebuild", inputs={},
                      status=JobStatus.DONE))
    with db.session() as s:
        return s.scalar(select(Job.id).order_by(Job.id.desc()).limit(1))


def _audit(db, action, slug, job_id, detail):
    with db.session() as s:
        s.add(Job(agent="x", job_type="stage", inputs={}, status=JobStatus.DONE))
        s.flush()
        jid = job_id if job_id is not None else s.scalar(
            select(Job.id).order_by(Job.id.desc()).limit(1))
        s.add(AuditLog(actor="x", action=action, artifact=f"{slug}@1.0.0", job_id=jid,
                       detail=detail))


def test_a_real_gate_refusal_parks_the_product_and_leaves_the_systemic_halt():
    db = base._sqlite_db()
    restore = base._no_policy()
    try:
        first = _estate(db, 4)
        fp = {"chain:release": {"old": "0" * 16, "new": "1" * 16}}
        # p0, p1, p2: this attempt's own chain refused at a real gate.
        _audit(db, "assets.listing_images_blocked", "p0", None,
               {"blocking": ["CREATIVE_INVENTED: frame 3 depicts a motif the truth lacks"]})
        _audit(db, "launch.held", "p1", None, {"action": "hold", "why": "window missed"})
        _audit(db, "childrens.decision_required", "p2", None,
               {"why": "a children's item needs the owner's decision"})
        # p3: refused only on its own staleness -- the deadlock, never a gate.
        _audit(db, "marketing.blocked", "p3", None,
               {"reasons": ["halted (#173): 1 open publication-halting incident(s)",
                            "rebuild outstanding (#172): 1 descendant(s)"]})
        # an older attempt's refusal for p3 does not belong to this attempt
        _audit(db, "pricing.refused", "p3", first - 1,
               {"reasons": ["older attempt"]})
        ctx = _Ctx(db, first)
        details = {f"p{k}": release._rebuild_incomplete(
            ctx, f"p{k}", "1.0.0", stale=[f"pdf:p{k}@1.0.0#pdf-us"], reason="t",
            fingerprints=fp, checks=3) for k in range(4)}
        assert details["p0"]["parked"]["gate"] == "assets.listing_images_blocked"
        assert "CREATIVE_INVENTED" in details["p0"]["parked"]["reasons"][0]
        assert details["p1"]["parked"]["gate"] == "launch.held"
        assert details["p2"]["parked"]["gate"] == "childrens.decision_required"
        assert "parked" not in details["p3"], details["p3"]
        with db.session() as s:
            ev = L.systemic_evidence(s)
        # 1 of 4 products in each staleness family: not widespread; the 3 parked are named
        assert not ev["systemic"], ev
        assert set(ev["parked_on_a_gate"]) == {"p0", "p1", "p2"}, ev
        # every gate kept: each parked product is still halted, its rows open
        tracker = IncidentTracker(db)
        for k in range(4):
            assert tracker.publication_halted(f"p{k}"), k
            assert release_gates.staleness(db, slug=f"p{k}")["halted"], k
        # an integrity failure is still systemic whatever is parked
        with db.session() as s:
            s.add(Incident(severity="P0", signature="authority_chain_tamper:x",
                           halts_publication=True, summary="t", detail={}))
        with db.session() as s:
            assert L.systemic_evidence(s)["systemic"]
        # a later attempt refused by no gate un-parks the product
        ctx2 = _Ctx(db, first + 1000)
        d = release._rebuild_incomplete(ctx2, "p0", "1.0.0", stale=["pdf:p0@1.0.0#pdf-us"],
                                        reason="t", fingerprints=fp, checks=3)
        assert "parked" not in d
        with db.session() as s:
            row = s.scalar(select(Incident).where(Incident.signature == "rebuild-incomplete:p0"))
            assert "parked" not in (row.detail or {}), row.detail
    finally:
        restore()


def test_a_pivoted_launch_hold_and_an_attempt_without_identity_never_park():
    db = base._sqlite_db()
    restore = base._no_policy()
    try:
        first = _estate(db, 1)
        _audit(db, "launch.held", "p0", None, {"why": "window missed"})
        _audit(db, "launch.pivot_queued", "p0", None, {"why": "evergreen pivot"})
        fp = {"chain:release": {"new": "1" * 16}}
        d = release._rebuild_incomplete(_Ctx(db, first), "p0", "1.0.0", stale=["pdf:x"],
                                        reason="t", fingerprints=fp, checks=3)
        assert "parked" not in d, d
        legacy = _Ctx(db, first)
        legacy.job.inputs = {}
        d = release._rebuild_incomplete(legacy, "p0", "1.0.0", stale=["pdf:x"], reason="t",
                                        fingerprints=fp, checks=3)
        assert "parked" not in d, d
    finally:
        restore()


TESTS = [test_vanished_rule_is_narrow_and_fails_closed,
         test_a_real_gate_refusal_parks_the_product_and_leaves_the_systemic_halt,
         test_a_pivoted_launch_hold_and_an_attempt_without_identity_never_park,
         test_production_shape_a_rebuild_with_orphans_verifies_and_the_orphans_retire]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
