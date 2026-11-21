"""eng/halt-380-h5: does the targeted rebuild agree with the sentinel about what is stale?

Production 1bb7c4f5 at 2026-11-21T08:20Z: `sentinel_stale_artefacts` 111 of 600 checked;
`open_stale_artefact_incidents` 112 across 12 products, the oldest 1487 h old;
`rebuilds_already_fresh_7d` 874 against `rebuilds_verified_7d` 8.

Main's hypothesis H5: the sentinel (`ops/artefacts.sweep`) judges against the full estate
(`check(..., expected=expected_from_db)`), so an expected artefact with no provenance row reads
UNPROVEN and, in a graduated class, blocks. `_targeted_rebuild` called `check(s, current=...)`
with no `expected`, so it judged a different set, and a stage that never writes the exact
class:key cannot cure the incident.

What these tests establish (each one says whether it fails on the base 1bb7c4f5):

* H5 as stated -- an UNPROVEN graduated key whose rebuild "never reads fresh" -- is REFUTED
  for a stage that writes the expected key: the rebuild requests it, the stage writes the exact
  key, verify binds it and the incident closes (`test_h5_literal_...`, passes on base). The real
  gap on that path is different: the sentinel never REQUESTS a rebuild for a blocking UNPROVEN
  key (its propagation is driven only by STALE moved refs), so such an incident waited for a
  rebuild nobody asked for (`test_h5_unproven_blocking_key_gets_a_rebuild`, fails on base).
* The `already_fresh` keys are NOT incidents the sweep fails to close: the sweep reads the same
  row the same way and closes it on the next pass (`test_already_fresh_...`, passes on base).
* The disagreement that does exist, and that matches the production shape (111 STALE verdicts
  behind 112 open incidents), is an ORPHAN row: the gallery rebuild deletes ListingAsset rows
  beyond the rebuilt set (`runtime/release.py`, review 6817652112 N2) but their
  `visual_truth:<slug>@<v>#<id>` provenance rows stay. After a chain move they read STALE for
  good; no stage ever rewrites a key whose frame no longer exists, so the incident halts its
  product forever and the rebuild re-requests it every day (`test_orphan_...`, fails on base).

The fix is one shared verdict (`artefacts.standing`) used by the sentinel and by the rebuild;
an orphan row of a fully enumerated class is retired WITH its reason, never silently; a key the
sweep retires is set aside by the rebuild and by the rebuild-incomplete judge. Absence of a row
for an artefact that exists is still UNPROVEN and still blocks in a graduated class.

Run: cd brambleloop && python3 tests/test_halt_380_h5.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT.parent / "ops"))

import test_eng_stale_rebuild_loop as base  # noqa: E402
import test_publish_unhalt as U  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (ArtefactProvenance, AuditLog, Incident, Job,  # noqa: E402
                                     JobStatus, ListingAsset, Phase, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime import worker as W  # noqa: E402

SLUG = "cloudline-baby-blanket"
V = "1.0.0"
STAGES = ("gate.certify", "assets.build", "pricing.position")


# --- estate ------------------------------------------------------------------------------------

def _frames(s, slug, n, *, start=1):
    out = []
    for pos in range(start, start + n):
        a = ListingAsset(product_slug=slug, version=V, position=pos, asset_class="RENDER",
                         role=f"r{pos}", sha256="a" * 64, approved=True)
        s.add(a)
        s.flush()
        out.append(a)
    return out


def _vkey(a):
    return A.visual_key(a.product_slug, a.version, a.id)


def _graduate(s, cls):
    s.add(AuditLog(actor="test", action=A.GRADUATION_ACTION, artifact=f"artefact_class:{cls}",
                   detail={"test": True}))
    s.flush()


def _estate(db, slug=SLUG, frames=3):
    """A certified release with `frames` gallery frames, each recorded under today's chain."""
    with db.session() as s:
        U._product(s, slug)
        assets = _frames(s, slug, frames)
        for a in assets:
            A.record(s, artefact_class="visual_truth", artefact_key=_vkey(a), product_slug=slug,
                     inputs=A.design_inputs(s, slug, V))
        return [_vkey(a) for a in assets], [a.id for a in assets]


def _drop_frame(db, asset_id):
    """What the gallery rebuild does to a frame beyond the rebuilt set: the row is deleted,
    its provenance row is not."""
    with db.session() as s:
        s.delete(s.get(ListingAsset, asset_id))


class _FaithfulStage:
    """The stage a targeted rebuild enqueues, writing what the REAL stage writes: one row per
    frame that EXISTS for the newest release (never a row for a frame that is gone), with the
    design inputs of that release, bound to the stage job. (`test_halt380_h4`'s stub instead
    rewrites every existing provenance row, orphans included -- which no real stage does.)"""

    def __init__(self, writes=True):
        self.writes, self.ran = writes, []

    def _stage(self, ctx):
        i = dict(ctx.job.inputs)
        slug = i.get("slug") or (i.get("cir") or {}).get("slug") or i.get("product_slug") or ""
        if self.writes:
            with ctx.db.session() as s:
                for a in s.scalars(select(ListingAsset).where(
                        ListingAsset.product_slug == slug, ListingAsset.version == V)):
                    A.record(s, artefact_class="visual_truth", artefact_key=_vkey(a),
                             product_slug=slug, inputs=A.design_inputs(s, slug, V))
                    row = s.scalar(select(ArtefactProvenance).where(
                        ArtefactProvenance.artefact_class == "visual_truth",
                        ArtefactProvenance.artefact_key == _vkey(a)))
                    row.job_id = ctx.job.id
        self.ran.append((ctx.job.job_type, slug))
        return {"stub_stage": True, "slug": slug}

    def __enter__(self):
        self.saved = {t: W.handlers.get(t) for t in STAGES}
        for t in STAGES:
            W.handlers._handlers[t] = self._stage
        return self

    def __exit__(self, *exc):
        for t, fn in self.saved.items():
            if fn is None:
                W.handlers._handlers.pop(t, None)
            else:
                W.handlers._handlers[t] = fn


def _drain(db, rounds=6):
    """Run every rebuild, stage and verify pass; the verify delay elapses between rounds."""
    w = W.Worker(db, "h5", phase=Phase.SHADOW, lease_seconds=900,
                 job_types=["chain.rebuild", *STAGES])
    for _ in range(rounds):
        for _ in range(200):
            if not w.run_once():
                break
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.run_after = utcnow()


def _incident(db, sig):
    with db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == sig)
                       .order_by(Incident.id.desc()))
        if row is not None:
            s.expunge(row)
        return row


def _rebuild(db, keys, tag, slug=SLUG, **extra):
    return base._run_job(db, "listing", "chain.rebuild",
                         {"product_slug": slug, "artefacts": keys, "fingerprints": {},
                          "reason": f"h5 {tag}", **extra}, f"h5-rebuild-{tag}")


# --- H5 as stated: an UNPROVEN graduated key -----------------------------------------------------

def test_h5_literal_unproven_graduated_key_is_cured_when_the_stage_writes_the_exact_key():
    """A graduated class, an expected artefact with NO row: the sentinel blocks on it. The
    rebuild judges it not-fresh too (absent from its verdicts), enqueues the stage, the stage
    writes that exact key, and the verify pass binds it and closes the incident. Passes on base:
    with a stage that writes the expected key, H5's 'never reads fresh' does not happen."""
    db = base._db()
    restore = base._no_policy()
    try:
        _keys, _ids = _estate(db, frames=2)
        with db.session() as s:
            _graduate(s, "visual_truth")
            fresh_frame = _frames(s, SLUG, 1, start=3)[0]      # exists, no provenance row
            key = f"visual_truth:{_vkey(fresh_frame)}"
        base._sentinel(db, "lit-1")
        inc = _incident(db, f"stale-artefact:{key}")
        assert inc is not None and not inc.resolved and inc.halts_publication, inc
        with _FaithfulStage():
            first = _rebuild(db, [key], "lit")
            assert first.outputs["requested"] == [key], first.outputs
            _drain(db)
        assert _incident(db, f"stale-artefact:{key}").resolved, "verified rebuild closes it"
        with db.session() as s:
            done = [a.artifact for a in s.scalars(select(AuditLog).where(
                AuditLog.action == "chain.rebuild_completed"))
                if not (a.detail or {}).get("already_fresh")]
        assert key in done, done
    finally:
        restore()


def test_h5_a_stage_that_never_writes_the_key_leaves_it_blocking_and_bounded():
    """The other half of H5: if the stage does NOT write the exact key, the graduated absence
    stays UNPROVEN, keeps blocking, and the attempt ends in a bounded rebuild-incomplete row
    (never a silent pass). Same on base and branch -- the gate's intent is kept."""
    db = base._db()
    restore = base._no_policy()
    try:
        _estate(db, frames=1)
        with db.session() as s:
            _graduate(s, "visual_truth")
            key = f"visual_truth:{_vkey(_frames(s, SLUG, 1, start=2)[0])}"
        base._sentinel(db, "nw-1")
        with _FaithfulStage(writes=False):
            _rebuild(db, [key], "nw")
            _drain(db)
        assert not _incident(db, f"stale-artefact:{key}").resolved
        assert _incident(db, f"stale-artefact:{key}").halts_publication
        ri = _incident(db, f"rebuild-incomplete:{SLUG}")
        assert ri is not None and not ri.resolved and key in ri.detail["stale"], ri
        base._sentinel(db, "nw-2")
        assert not _incident(db, f"stale-artefact:{key}").resolved     # absence never passes
    finally:
        restore()


def test_h5_unproven_blocking_key_gets_a_rebuild():
    """The gap on H5's path: the sentinel's propagation is driven only by STALE moved refs, so
    a blocking UNPROVEN key (graduated class, nothing stale) got NO rebuild request -- the
    incident waited for good. FAILS ON BASE (nothing is enqueued). Now one targeted rebuild per
    product per day is requested for exactly its blocking UNPROVEN keys, and it cures them."""
    db = base._db()
    restore = base._no_policy()
    try:
        _estate(db, frames=1)
        with db.session() as s:
            _graduate(s, "visual_truth")
            key = f"visual_truth:{_vkey(_frames(s, SLUG, 1, start=2)[0])}"
        out = base._sentinel(db, "req-1")
        with db.session() as s:
            asked = [j.inputs for j in s.scalars(select(Job).where(
                Job.job_type == "chain.rebuild"))]
        assert any(key in (i.get("artefacts") or []) for i in asked), (out, asked)
        assert out.get("rebuild_unproven_requested") == [SLUG], out
        again = base._sentinel(db, "req-2")                     # once per product per day
        assert again.get("rebuild_unproven_requested") == [], again
        with _FaithfulStage():
            _drain(db)
        base._sentinel(db, "req-3")
        assert _incident(db, f"stale-artefact:{key}").resolved
    finally:
        restore()


# --- task 2: already_fresh keys and the sweep's close condition ---------------------------------

def test_already_fresh_keys_close_on_the_next_sweep():
    """A key the rebuild reports already_fresh is a key whose row reads FRESH. The sweep reads
    the same row against the same current fingerprints, so its stale-artefact incident closes
    on the next pass. Passes on base: the already_fresh count is noise (the per-product rebuild
    set names every artefact of the product), not an incident the sweep fails to close."""
    db = base._db()
    restore = base._no_policy()
    try:
        keys, _ids = _estate(db, frames=2)
        with base._MovedChain():
            base._sentinel(db, "af-1")
            for k in keys:
                assert not _incident(db, f"stale-artefact:visual_truth:{k}").resolved
            with db.session() as s:                    # rewritten outside this attempt
                for k in keys:
                    A.record(s, artefact_class="visual_truth", artefact_key=k,
                             product_slug=SLUG, inputs=A.design_inputs(s, SLUG, V))
            first = _rebuild(db, [f"visual_truth:{k}" for k in keys], "af")
            assert sorted(first.outputs["already_fresh"]) == sorted(
                f"visual_truth:{k}" for k in keys), first.outputs
            base._sentinel(db, "af-2")
            for k in keys:
                inc = _incident(db, f"stale-artefact:visual_truth:{k}")
                assert inc.resolved and "match again" in inc.detail["resolution"], inc.detail
    finally:
        restore()


# --- the disagreement that exists: an orphan row --------------------------------------------------

def test_orphan_row_of_a_deleted_frame_is_retired_with_its_reason_and_the_halt_clears():
    """Production shape: frames recorded, the chain moves, the gallery rebuild drops a frame
    (row deleted, provenance row kept). On base the orphan reads STALE forever: its incident
    halts the product, every rebuild re-requests it, the stage never rewrites it, and the
    attempt ends in a held rebuild-incomplete row. FAILS ON BASE. Now the shared verdict retires
    the orphan with the reason, the sweep closes its incident with that reason, the rebuild sets
    it aside, and the surviving frames are rebuilt, verified and closed."""
    db = base._db()
    restore = base._no_policy()
    try:
        keys, ids = _estate(db, frames=3)
        orphan = f"visual_truth:{keys[2]}"
        with base._MovedChain():
            base._sentinel(db, "orph-1")
            assert _incident(db, f"stale-artefact:{orphan}").halts_publication
            _drop_frame(db, ids[2])
            with _FaithfulStage():
                for n in range(2):
                    out = base._sentinel(db, f"orph-run-{n}")
                    _drain(db)
            out = base._sentinel(db, "orph-final")
            inc = _incident(db, f"stale-artefact:{orphan}")
            assert inc.resolved, (inc.detail, out)
            assert "no longer exists" in inc.detail["resolution"], inc.detail
            survivors = keys[:2]
            assert len(survivors) == 2
            for k in survivors:
                assert _incident(db, f"stale-artefact:visual_truth:{k}").resolved
            ri = _incident(db, f"rebuild-incomplete:{SLUG}")
            assert ri is None or ri.resolved, ri.detail
            assert out["stale"] == 0 and out["publication_blocked"] == [], out
            from brambleloop.ops import rebuild_graph as G

            with db.session() as s:                       # the publish path agrees too
                gate = G.publication_gate(s, slug=SLUG)
            assert gate["may_publish"], gate
            with db.session() as s:
                retired_audit = [a for a in s.scalars(select(AuditLog).where(
                    AuditLog.action == "chain.rebuild_retired"))]
            assert retired_audit and orphan in retired_audit[0].detail["retired"], \
                "the rebuild records what it set aside and why, never silently"
            ev = PE.stale_rebuilds(db, now=utcnow())
            # only the non-halting backlog counter (this fixture's certificate, ungraduated)
            assert ev["open_stale_artefact_incidents"] == 1, ev
            assert _incident(db, "stale-artefact:backlog").halts_publication is False
    finally:
        restore()


def test_a_held_rebuild_incomplete_row_naming_an_orphan_closes():
    """The incident state production already holds: a rebuild-incomplete row (held) naming an
    orphan plus surviving frames that have since been rebuilt fresh. On base the orphan reads
    'stale' in sentinel_read and the row never closes. FAILS ON BASE."""
    db = base._db()
    restore = base._no_policy()
    try:
        keys, ids = _estate(db, frames=2)
        orphan = f"visual_truth:{keys[1]}"
        with db.session() as s:
            row = s.scalar(select(ArtefactProvenance).where(
                ArtefactProvenance.artefact_key == keys[1]))
            row.inputs = dict(row.inputs, **{"chain:release": "0" * 16})
            U._halting(s, f"rebuild-incomplete:{SLUG}", SLUG,
                       stale=[f"visual_truth:{k}" for k in keys], attempts=3, held="3 attempts")
        _drop_frame(db, ids[1])
        out = base._sentinel(db, "held")
        ri = _incident(db, f"rebuild-incomplete:{SLUG}")
        assert ri.resolved, (ri.detail, out.get("rebuild_incomplete_open"))
        assert orphan in ri.detail["retired_names"], ri.detail
    finally:
        restore()


def test_guard_a_stale_row_of_an_existing_frame_still_blocks():
    db = base._db()
    restore = base._no_policy()
    try:
        keys, ids = _estate(db, frames=2)
        _drop_frame(db, ids[1])
        with base._MovedChain():
            out = base._sentinel(db, "guard")
            live = _incident(db, f"stale-artefact:visual_truth:{keys[0]}")
            assert live is not None and not live.resolved and live.halts_publication
            assert out["publication_blocked"] == [SLUG], out
            assert out["stale"] == 1, out                  # the orphan is not counted stale
            from brambleloop.ops import rebuild_graph as G

            with db.session() as s:
                gate = G.publication_gate(s, slug=SLUG)
            assert not gate["may_publish"], gate
            assert f"visual_truth:{keys[0]}" in gate["outstanding"], gate
            assert f"visual_truth:{keys[1]}" not in gate["outstanding"], gate
    finally:
        restore()


def test_guard_orphan_rule_is_narrow():
    """Retirement needs the full estate and a fully enumerated class with a frame-id key: a
    check without `expected`, a non-enumerated class (a marketing video row), or a key that is
    not a frame id never retires a row as an orphan."""
    db = base._db()
    keys, ids = _estate(db, frames=1)
    _drop_frame(db, ids[0])
    with db.session() as s:
        A.record(s, artefact_class="marketing_asset", artefact_key=f"video:{SLUG}:clip:tiktok",
                 product_slug=SLUG, inputs={"chain:release": "0" * 16})
        A.record(s, artefact_class="visual_truth", artefact_key=f"{SLUG}@{V}#hero",
                 product_slug=SLUG, inputs={"chain:release": "0" * 16})
        bare = {f"{v.artefact_class}:{v.artefact_key}": v
                for v in A.check(s, current=A.current_from_db(s))}
        assert not bare[f"visual_truth:{keys[0]}"].retired      # no estate: proves nothing
        st = {f"{v.artefact_class}:{v.artefact_key}": v for v in A.standing(s).verdicts}
        assert st[f"visual_truth:{keys[0]}"].retired
        assert "no longer exists" in st[f"visual_truth:{keys[0]}"].retired
        assert st[f"marketing_asset:video:{SLUG}:clip:tiktok"].state == A.STALE
        assert st[f"visual_truth:{SLUG}@{V}#hero"].state == A.STALE


def test_the_rebuild_and_the_sentinel_read_one_verdict():
    """Agreement: on a mixed estate (fresh, stale, orphan, graduated absence), the states the
    rebuild acts on are exactly the sentinel's. FAILS ON BASE (the rebuild requested the orphan
    the sentinel no longer counts, and read the absence from a different verdict set)."""
    db = base._db()
    restore = base._no_policy()
    try:
        keys, ids = _estate(db, frames=3)
        with db.session() as s:
            _graduate(s, "visual_truth")
            absent = f"visual_truth:{_vkey(_frames(s, SLUG, 1, start=4)[0])}"
            row = s.scalar(select(ArtefactProvenance).where(
                ArtefactProvenance.artefact_key == keys[1]))
            row.inputs = dict(row.inputs, **{"chain:release": "0" * 16})
            row = s.scalar(select(ArtefactProvenance).where(
                ArtefactProvenance.artefact_key == keys[2]))
            row.inputs = dict(row.inputs, **{"chain:release": "0" * 16})
        _drop_frame(db, ids[2])
        named = [f"visual_truth:{k}" for k in keys] + [absent]
        out = base._sentinel(db, "agree")
        with db.session() as s:
            st = {f"{v.artefact_class}:{v.artefact_key}": v for v in A.standing(s).verdicts}
        bad = {k for k in named if k in st and st[k].state in (A.STALE, A.UNPROVEN)
               and not st[k].retired}
        job = _rebuild(db, named, "agree")
        assert set(job.outputs["requested"]) == bad, (job.outputs, bad)
        assert set(job.outputs["already_fresh"]) == {f"visual_truth:{keys[0]}"}
        assert set(job.outputs["retired"]) == {f"visual_truth:{keys[2]}"}, job.outputs
        assert out["stale"] == 1, out                       # keys[1]; the orphan is retired
    finally:
        restore()


if __name__ == "__main__":
    import traceback

    names = [n for n in list(globals()) if n.startswith("test_")]
    fails = 0
    for name in names:
        try:
            globals()[name]()
            print(f"OK   {name}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            fails += 1
            print(f"FAIL {name}", repr(e)[:300])
    print(f"{len(names) - fails}/{len(names)} passed")
    sys.exit(1 if fails else 0)
