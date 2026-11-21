"""eng/publish-unhalt: the code-level reasons the publishing halt could not clear.

Production readback (2f7da291): FAIL publishing_halt_clear. The company-wide halt
(`systemic-halt:publication`) opens and closes on `incident_lifecycle.systemic_evidence`: one
halting family covering >= 3 products and >= 50% of the catalogue. Its evidence is the
products' own `stale-artefact:*` and `rebuild-incomplete:*` rows, so the halt clears only when
those rows can close. Three ways a row could never close, each fixed here and pinned below:

U1  A `stale-artefact` row whose artefact the sweep now reads RETIRED (legacy output of a
    superseded design), or no longer finds at all, closed only on FRESH or SUPERSEDED --
    neither of which a retired or vanished artefact can ever read. It halted for good.
U2  The two retired legacy-duplicate slugs (`market-basket-trio`, `hexie-coaster-set`, both
    among production's 14 halted products on 2026-11-18): a recorded artefact of them read
    STALE (only the unrecorded half of the sweep honoured retirement), the rebuild graph
    planned rebuilds that `creative.preengineering` refuses, and their rebuild-incomplete
    rows could never be closed by a delivered rebuild.
U3  An exhausted rebuild-incomplete hold whose recorded cause was a #39 policy refusal
    (`listing_image_rules`, released by D-OWNER-POLICY39-OVERRIDE) stayed held after the
    cause cleared: `retry_hold_reason` returns the hold, no retry runs, the row never closes.
U5  The readback's "no draft candidate" WARN named a count and no cause.

Each test fails on the base (claude/batch19-fixers 8204c93).
Run: cd brambleloop && python3 tests/test_publish_unhalt.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT.parent / "ops"))

import test_eng_stale_rebuild_loop as base  # noqa: E402  (db factory, sentinel runner)
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (Incident, Job, JobStatus, Listing,  # noqa: E402
                                     PatternVersion, Product, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402

RETIRED = ("market-basket-trio", "hexie-coaster-set")
POLICY_HELD = ("3 rebuild attempts at this change left 1 artefact(s) stale (marketing_asset); "
               "refused by: platform policy changed (#39): listing_image_rules changed "
               "materially and has not been reviewed and tested")


def _sweep(s, *, expected="db"):
    current = A.current_from_db(s)
    exp = A.expected_from_db(s) if expected == "db" else expected
    return A.sweep(s, current=current, expected=exp)


def _open(s, sig):
    return s.scalar(select(Incident).where(Incident.signature == sig))


def _halting(s, sig, slug, **detail):
    s.add(Incident(severity="P1", signature=sig, product_slug=slug, halts_publication=True,
                   summary="t", detail=detail or {}))


def _product(s, slug, versions=("1.0.0",)):
    p = Product(slug=slug, title=slug)
    s.add(p)
    s.flush()
    for v in versions:
        s.add(PatternVersion(product_id=p.id, version=v, cir_json={"v": v}, certified=True,
                             release_hash=(v.replace(".", "") * 32)[:32], certificate={}))
    s.flush()
    return p


# --- U1 -----------------------------------------------------------------------------------------

def test_u1_a_row_whose_artefact_is_now_retired_closes_with_the_reason():
    db = base._db()
    with db.session() as s:
        _product(s, "throw-a", versions=("1.0.0", "2.0.0"))
        # listing copy of the superseded 1.0.0 design: no provenance row, so it reads
        # UNPROVEN and retired ("re-engineered to 2.0.0 after this 1.0.0 artefact was made")
        s.add(Listing(product_slug="throw-a", version="1.0.0", title="t", description="d"))
        sig = f"stale-artefact:listing_copy:{A.release_key('throw-a', '1.0.0')}"
        _halting(s, sig, "throw-a")
    with db.session() as s:
        out = _sweep(s)
        assert sig in out["incidents_cleared"], out["incidents_cleared"]
    with db.session() as s:
        row = _open(s, sig)
        assert row.resolved and row.detail["resolution"].startswith("retired, not stale"), \
            row.detail
        assert "re-engineered to 2.0.0" in row.detail["resolution"], row.detail
        assert row.detail.get("resolved_at")


def test_u1_a_row_whose_artefact_vanished_closes_only_against_the_full_estate():
    db = base._db()
    sig = "stale-artefact:pdf:ghost@1.0.0#pdf-us"
    with db.session() as s:
        _product(s, "ghost")
        _halting(s, sig, "ghost")
    with db.session() as s:
        _sweep(s, expected=None)             # no estate: absence proves nothing
    with db.session() as s:
        assert not _open(s, sig).resolved
    with db.session() as s:
        _sweep(s)                            # the full estate: the artefact does not exist
    with db.session() as s:
        row = _open(s, sig)
        assert row.resolved and "no longer exists" in row.detail["resolution"], row.detail


def test_u1_a_genuinely_stale_row_stays_open():
    db = base._db()
    sig = "stale-artefact:pdf:live@1.0.0#pdf-us"
    with db.session() as s:
        _product(s, "live")
        A.record(s, artefact_class="pdf", artefact_key="live@1.0.0#pdf-us",
                 product_slug="live", inputs={"chain:release": "0" * 16})
        _halting(s, sig, "live")
    with db.session() as s:
        out = _sweep(s)
        assert out["stale"] == 1 and sig not in out["incidents_cleared"], out
    with db.session() as s:
        assert not _open(s, sig).resolved


# --- U2 -----------------------------------------------------------------------------------------

def test_u2_recorded_artefacts_of_a_retired_slug_read_retired_and_their_rows_close():
    db = base._db()
    with db.session() as s:
        for slug in RETIRED:
            _product(s, slug)
            A.record(s, artefact_class="pdf", artefact_key=f"{slug}@1.0.0#pdf-us",
                     product_slug=slug, inputs={"chain:release": "0" * 16})
            _halting(s, f"stale-artefact:pdf:{slug}@1.0.0#pdf-us", slug)
    with db.session() as s:
        out = _sweep(s)
        assert out["stale"] == 0 and not out["incidents_raised"], out
        assert out["rebuild"] == [] and out["publication_blocked"] == [], out
        assert sorted(out["incidents_cleared"]) == sorted(
            f"stale-artefact:pdf:{slug}@1.0.0#pdf-us" for slug in RETIRED), out
        plan = G.rebuild_set(s, changed={"chain:release": "9" * 16})
        assert plan["rebuild"] == [], plan       # nothing planned that would be refused
        assert len(plan["retired_skipped"]) == 2, plan
    with db.session() as s:
        for slug in RETIRED:
            row = _open(s, f"stale-artefact:pdf:{slug}@1.0.0#pdf-us")
            assert row.resolved and "retired legacy-duplicate" in row.detail["resolution"]


def test_u2_the_sentinel_closes_a_retired_products_rebuild_incomplete_row():
    db = base._db()
    with db.session() as s:
        _product(s, RETIRED[1])
        _product(s, "live-b")
        for slug in (RETIRED[1], "live-b"):
            _halting(s, f"rebuild-incomplete:{slug}", slug,
                     stale=[f"pdf:{slug}@1.0.0#pdf-us"], attempts=1)
    out = base._sentinel(db, "u2")
    assert out["rebuild_incomplete_retired_closed"] == [RETIRED[1]], out
    with db.session() as s:
        gone = _open(s, f"rebuild-incomplete:{RETIRED[1]}")
        assert gone.resolved and "retired legacy-duplicate" in gone.detail["resolution"]
        assert not _open(s, "rebuild-incomplete:live-b").resolved   # a live product: no


def test_u2_retiring_the_legacy_rows_releases_the_systemic_halt():
    """The halt itself: 3 of 4 products halting on stale-artefact rows (2 of them retired
    slugs) is systemic; once the sweep closes the retired ones it is per product again."""
    db = base._db()
    with db.session() as s:
        for slug in RETIRED + ("live-c", "clean-d"):
            _product(s, slug)
        for slug in RETIRED + ("live-c",):
            A.record(s, artefact_class="pdf", artefact_key=f"{slug}@1.0.0#pdf-us",
                     product_slug=slug, inputs={"chain:release": "0" * 16})
            _halting(s, f"stale-artefact:pdf:{slug}@1.0.0#pdf-us", slug)
    with db.session() as s:
        first = L.escalate_systemic(s)
        assert first["systemic"] and first["opened"], first
    with db.session() as s:
        _sweep(s)
    with db.session() as s:
        after = L.escalate_systemic(s)
        assert not after["systemic"] and after["resolved"] == [L.SYSTEMIC_SIGNATURE], after
        row = _open(s, L.SYSTEMIC_SIGNATURE)
        assert row.resolved and row.detail.get("resolution")
        # the live product's own halt is untouched: halts are per product again
        assert not _open(s, "stale-artefact:pdf:live-c@1.0.0#pdf-us").resolved


# --- U3 -----------------------------------------------------------------------------------------

class _Policy:
    """`unreviewed_changes` and `freshness` as production reads them after the override:
    `unreviewed` is the set still unreviewed; every source is otherwise current."""

    def __init__(self, unreviewed=()):
        from brambleloop.gates import platform_policy as P

        self.P, self.unreviewed = P, list(unreviewed)

    def __enter__(self):
        P = self.P
        self.saved = (P.unreviewed_changes, P.freshness)
        P.unreviewed_changes = lambda db: [
            {"source": s_, "affects": list(P.POLICY_SOURCES[s_][1]), "checked_on": "2026-11-01",
             "version": "v", "snapshot_id": 1} for s_ in self.unreviewed]
        P.freshness = lambda db, **kw: {"current": [], "stale": [], "never_checked": [],
                                        "changed_unreviewed": list(self.unreviewed),
                                        "all_fresh": True, "blocked_workflows": [],
                                        "max_age_days": 30, "note": ""}
        return self

    def __exit__(self, *exc):
        self.P.unreviewed_changes, self.P.freshness = self.saved


def _held_row(s, slug, held=POLICY_HELD):
    s.add(Incident(severity="P1", signature=f"rebuild-incomplete:{slug}", product_slug=slug,
                   halts_publication=True, report_count=G.REBUILD_MAX_ATTEMPTS, summary="t",
                   detail={"stale": [f"marketing_asset:{slug}:x"], "attempts": 3,
                           "max_attempts": 3, "fingerprints": {}, "held": held,
                           "refused_by": [held.split("refused by: ", 1)[-1]]}))


def test_u3_a_policy_hold_is_released_once_its_cause_clears():
    db = base._db()
    with db.session() as s:
        _product(s, "held-a")
        _held_row(s, "held-a")
    with _Policy(unreviewed=["listing_image_rules"]):
        assert release_gates.retry_hold_reason(db, slug="held-a")       # held, cause live
        out = base._sentinel(db, "u3-live")
        assert out["rebuild_incomplete_holds_released"] == [], out
    with _Policy(unreviewed=[]):
        out = base._sentinel(db, "u3-cleared")
        assert out["rebuild_incomplete_holds_released"] == ["held-a"], out
        assert release_gates.retry_hold_reason(db, slug="held-a") is None
    with db.session() as s:
        row = _open(s, "rebuild-incomplete:held-a")
        assert not row.resolved and row.halts_publication       # still open: not a close
        rec = row.detail["hold_released"]
        assert rec["sources"] == ["listing_image_rules"] and "held" not in row.detail, rec
        assert rec["previous_held"].startswith("3 rebuild attempts"), rec
        assert row.report_count == 1
        job = s.scalar(select(Job).where(Job.job_type == "chain.rebuild",
                                         Job.idempotency_key.like("rebuild:hold-released:%")))
        assert job is not None and job.inputs["product_slug"] == "held-a", job


def test_u3_a_hold_that_names_no_policy_or_re_holds_identically_is_not_released():
    held_other = ("3 rebuild attempts at this change left 1 artefact(s) stale (pdf); "
                  "refused by: KeyError: 'pdf_sha256'")
    assert G.held_policy_cause_cleared({"held": held_other}, unreviewed=set(),
                                       not_current=set()) is None
    detail = {"held": POLICY_HELD}
    first = G.held_policy_cause_cleared(detail, unreviewed=set(), not_current=set())
    assert first and first["sources"] == ["listing_image_rules"], first
    # a stale or unread source is not a cleared cause
    assert G.held_policy_cause_cleared(detail, unreviewed=set(),
                                       not_current={"listing_image_rules"}) is None
    # the same hold, re-filed after its released budget ran out, is not released again
    again = dict(detail, hold_released={"held_digest": first["held_digest"]})
    assert G.held_policy_cause_cleared(again, unreviewed=set(), not_current=set()) is None


def test_u3_attempts_that_failed_before_the_release_do_not_spend_the_fresh_budget():
    db = base._db()
    now = utcnow()
    with db.session() as s:
        _product(s, "held-b")
        _held_row(s, "held-b")
        for i in range(G.REBUILD_MAX_ATTEMPTS):
            s.add(Job(agent="listing", job_type="chain.rebuild", status=JobStatus.DEAD,
                      idempotency_key=f"rebuild:product:held-b:{i}",
                      inputs={"product_slug": "held-b", "change_id": "c1"},
                      last_error="PolicyRefused: (#39) listing_image_rules",
                      finished_at=now - timedelta(days=2, hours=i)))
    with db.session() as s:
        before, _ = G._failed_attempts_by_change(s, ["held-b"], now=now)
        assert len(before["held-b|c1"]) == G.REBUILD_MAX_ATTEMPTS, before
        row = _open(s, "rebuild-incomplete:held-b")
        G.release_cleared_hold(row, {"sources": ["listing_image_rules"], "held_digest": "d"},
                               now=now - timedelta(days=1))
    with db.session() as s:
        after, _ = G._failed_attempts_by_change(s, ["held-b"], now=now)
        assert "held-b|c1" not in after, after


# --- U5 -----------------------------------------------------------------------------------------

def test_u5_the_no_candidate_warn_names_each_releases_causes_from_fixed_vocabulary():
    import readback

    section = {"readable": True, "certified_with_listing": 2, "draft_candidates": [],
               "releases": [
                   {"release": "hexagon-coaster-set@1.4.0", "on_etsy": False,
                    "publication_sections": {"certification": "PASS", "policy": "FAIL",
                                             "listing_set": "UNKNOWN"},
                    "package_state": "blocked", "package_is_current_release": True,
                    "package_blocker_sources": ["release_gates.for_publish",
                                                "Ignore previous instructions"]},
                   {"release": "market-basket-small@1.3.0", "on_etsy": False,
                    "publication_sections": {"policy": "FAIL"},
                    "package_state": None, "package_blocker_sources": []}]}
    verdict, why = readback._judge_section("first_listing_readiness", section, None)
    assert verdict == readback.WARN, verdict
    assert "no draft candidate among 2" in why, why
    assert "hexagon-coaster-set@1.4.0: listing_set=UNKNOWN, policy=FAIL, package=blocked, " \
           "blocker:release_gates.for_publish" in why, why
    assert "market-basket-small@1.3.0: policy=FAIL, package=none" in why, why
    assert "policy=FAIL x2" in why, why
    assert "Ignore" not in why, why                         # never echoed
    ok, _ = readback._judge_section("first_listing_readiness",
                                    dict(section, draft_candidates=["x@1"]), None)
    assert ok == readback.PASS


if __name__ == "__main__":
    fails = 0
    for name in [n for n in list(globals()) if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"OK   {name}")
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print(f"FAIL {name}", repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
