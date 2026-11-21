"""eng/halt-380-h3: rebuild-incomplete rows that name artefacts of a release the product has
moved past.

Production 7b250d61, systemic halt incident 380 OPEN: 12 halting products in one family
(`rebuild-incomplete`), including re-engineered products whose older releases are retired
(`cloudline-baby-blanket`, `winter-village-graphghan`). A `rebuild-incomplete:<slug>` row is
keyed per PRODUCT, but the artefacts it names (`detail.stale`) are per RELEASE. Once the
product is re-engineered, the old release's artefacts read SUPERSEDED, retired (never
recorded) or are gone, and nothing will ever rebuild them. The sentinel closed the row only
when every named artefact read FRESH or SUPERSEDED, so a row naming a retired or vanished old
release artefact could never close. It halted its product for good and counted toward
`incident_lifecycle.systemic_evidence`.

Fix: names of an obsolete release are set aside, and the row is judged on the CURRENT
release with the existing positive-evidence rule. A current release that is stale or unproven
still keeps the row open. The systemic thresholds are unchanged.

Run: cd brambleloop && python3 tests/test_halt_380_h3.py
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

from brambleloop.core.models import Listing  # noqa: E402
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402

OLD_NAMES = lambda slug: [f"listing_copy:{slug}@1.0.0",          # noqa: E731
                          f"pdf:{slug}@1.0.0#pdf-us"]


def _reengineered(s, slug, *, current_fresh=True, current_stale=False, legacy=False):
    """A product re-engineered 1.0.0 -> 2.0.0 whose rebuild-incomplete row still names the
    1.0.0 artefacts: a legacy listing copy (reads retired) and a PDF with no row at all."""
    U._product(s, slug, versions=("1.0.0", "2.0.0"))
    s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d"))
    cur = A.current_from_db(s)
    if current_fresh or current_stale:
        inputs = {"chain:release": cur["chain:release"], f"release:{slug}": cur[f"release:{slug}"]}
        if current_stale:
            inputs["chain:release"] = "0" * 16
        A.record(s, artefact_class="certificate", artefact_key=A.release_key(slug, "2.0.0"),
                 product_slug=slug, inputs=inputs)
    detail = {"stale": OLD_NAMES(slug)}
    if not legacy:
        detail["attempts"] = 1
    U._halting(s, f"rebuild-incomplete:{slug}", slug, **detail)


def test_obsolete_key_rule_is_narrow():
    latest = {"p": "2.0.0"}
    assert A.obsolete_release_key("pdf:p@1.0.0#pdf-us", "p", latest)
    assert A.obsolete_release_key("listing_copy:p@0.9.0", "p", latest)   # a release now gone
    assert A.obsolete_release_key("pdf:p@2.0.0#pdf-us", "p", latest) is None   # current
    assert A.obsolete_release_key("marketing_asset:p:etsy:abc", "p", latest) is None
    assert A.obsolete_release_key("pdf:p@collection#x", "p", latest) is None
    assert A.obsolete_release_key("pdf:q@1.0.0#pdf-us", "p", latest) is None  # other slug
    assert A.obsolete_release_key("pdf:p@1.0.0#pdf-us", "p", {}) is None   # newest unknown


def test_the_base_kept_an_old_release_row_open_forever_and_now_closes_it():
    db = base._db()
    with db.session() as s:
        _reengineered(s, "cloud")
    out = base._sentinel(db, "close")
    assert out["rebuild_incomplete_obsolete_release_closed"] == ["cloud"], out
    with db.session() as s:
        row = U._open(s, "rebuild-incomplete:cloud")
        assert row.resolved, row.detail
        assert "moved past" in row.detail["resolution"], row.detail
        assert set(row.detail["obsolete_release_names"]) == set(OLD_NAMES("cloud"))


def test_a_stale_current_release_still_holds_the_row():
    db = base._db()
    with db.session() as s:
        _reengineered(s, "cloud", current_fresh=False, current_stale=True)
    out = base._sentinel(db, "stale")
    assert out["rebuild_incomplete_obsolete_release_closed"] == [], out
    with db.session() as s:
        row = U._open(s, "rebuild-incomplete:cloud")
        assert not row.resolved and row.halts_publication
        assert row.detail["sentinel_read"]["verdicts"] == {"certificate:cloud@2.0.0": "stale"}


def test_an_unproven_current_release_is_not_evidence_and_holds_the_row():
    db = base._db()
    with db.session() as s:
        _reengineered(s, "cloud", current_fresh=False)
    base._sentinel(db, "unproven")
    with db.session() as s:
        assert not U._open(s, "rebuild-incomplete:cloud").resolved


def test_a_row_naming_a_stale_current_artefact_alongside_old_ones_stays_open():
    db = base._db()
    with db.session() as s:
        _reengineered(s, "cloud")
        row = U._open(s, "rebuild-incomplete:cloud")
        row.detail = dict(row.detail, stale=OLD_NAMES("cloud") + ["pdf:cloud@2.0.0#pdf-us"])
    base._sentinel(db, "mixed")
    with db.session() as s:
        row = U._open(s, "rebuild-incomplete:cloud")
        assert not row.resolved
        assert row.detail["sentinel_read"]["verdicts"] == {
            "pdf:cloud@2.0.0#pdf-us": "no provenance row"}, row.detail["sentinel_read"]


def test_production_shaped_systemic_halt_resolves_and_a_live_stale_product_keeps_its_own():
    """5 of 6 products halting in one family (systemic). 4 are re-engineered products whose
    rows name only their old release (one a legacy row with no attempt budget); 1 is a live
    product whose current release is genuinely stale; 1 is clean. After one sentinel pass the
    halt is per product again and only the live stale product halts."""
    db = base._db()
    reeng = ("cloudline-baby-blanket", "winter-village-graphghan", "throw-c", "throw-d")
    with db.session() as s:
        for i, slug in enumerate(reeng):
            _reengineered(s, slug, legacy=(i == 0))
        U._product(s, "live-e")
        A.record(s, artefact_class="pdf", artefact_key="live-e@1.0.0#pdf-us",
                 product_slug="live-e", inputs={"chain:release": "0" * 16})
        U._halting(s, "rebuild-incomplete:live-e", "live-e",
                   stale=["pdf:live-e@1.0.0#pdf-us"], attempts=1)
        U._product(s, "clean-f")
    with db.session() as s:
        first = L.escalate_systemic(s)
        assert first["systemic"] and first["opened"], first
        assert first["widespread_families"]["rebuild-incomplete"] == sorted(
            reeng + ("live-e",)), first
    out = base._sentinel(db, "prod")
    assert sorted(out["rebuild_incomplete_obsolete_release_closed"]) == sorted(reeng), out
    with db.session() as s:
        after = L.escalate_systemic(s)
        assert not after["systemic"] and after["resolved"] == [L.SYSTEMIC_SIGNATURE], after
        assert after["products"] == 6                 # the denominator is unchanged
        live = U._open(s, "rebuild-incomplete:live-e")
        assert not live.resolved and live.halts_publication


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
