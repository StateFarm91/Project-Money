"""ENG-CATALOGUE: the uncapped Mission Control catalogue (`/api/cc/catalogue`).

Owner-only, read-only (statement probe), paginated correctly over 300+ fixture products,
totals equal to SQL on the authoritative tables, and UNKNOWN never shown as 0.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_eng_catalogue.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="eng_catalogue_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cat.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "RAILWAY_GIT", "BRAMBLELOOP_COMMIT", "GIT_COMMIT", "SOURCE_COMMIT")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the catalogue harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, func, select  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center import catalogue as C  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import (Job, JobStatus, Listing, OwnerAction,  # noqa: E402
                                     PatternVersion, Product)
from brambleloop.products import production_inventory as PI  # noqa: E402
from brambleloop.radar.intake import RadarConcept  # noqa: E402

PASS = "owner passphrase for the catalogue harness"
os.environ[opsauth.TOKEN_VAR] = "c" * 40
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
DB = main.db
NOW = datetime.now(timezone.utc)
N = 320
KINDS = 5
_WORDS = ("amber", "birch", "cedar", "dune", "ember", "fern", "glade", "heath", "iris", "juniper")


def _word(i: int) -> str:
    """A number spelled in words (fixture titles carry no bare numbers: D-S1-FAIL-CLOSED)."""
    out = []
    while True:
        out.append(_WORDS[i % 10])
        i //= 10
        if not i:
            break
    return "-".join(reversed(out))


def _seed() -> None:
    with DB.session() as s:
        for i in range(N):
            w = _word(i)
            slug = f"cat-fixture-{w}"
            p = Product(slug=slug, title=f"Fixture Basket {w.replace('-', ' ').title()}")
            s.add(p)
            s.flush()
            kind = i % KINDS
            if kind in (1, 2, 3):
                cert = kind in (1, 2)
                s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                                     certified=cert, release_hash=("r" + w)[:60] if cert
                                     else None, certificate={"content_hash": "c" + w}
                                     if cert else None))
            if kind == 1:
                s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d",
                              state="active", release_hash=("r" + w)[:60],
                              etsy_listing_id=f"E{w}"[:30]))
            if kind == 2:
                from brambleloop.core import listing_state

                s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d",
                              state=listing_state.PUBLISHED, release_hash=("r" + w)[:60],
                              etsy_listing_id=f"D{w}"[:30]))
            if kind == 4:
                s.add(Job(agent="radar", job_type="radar.score", status=JobStatus.DONE,
                          inputs={"slug": slug}, outputs={"promoted": False,
                                                         "reason": "below the bar"},
                          finished_at=NOW))
            if i % 3 == 0:
                s.add(RadarConcept(slug=slug, state="proposed", source="fixture",
                                   source_ref=f"ref-{w}", fingerprint=f"fp-{w}",
                                   seed={"category": "basket" if i % 2 else "throw",
                                         "family": "nordic" if i % 2 else None}))
        # One open paid owner action naming one product: a paid-approval hold.
        s.add(OwnerAction(action=f"approve the yarn purchase for cat-fixture-{_word(5)} ",
                          requirement_key="fixture-paid", max_cost_cad=12.5))
        s.commit()


_seed()


def _view(**params):
    C.reset()
    return C.view(DB, params)


def _sql_counts() -> dict:
    from brambleloop.core import listing_state

    with DB.session() as s:
        return {
            "products": s.scalar(select(func.count()).select_from(Product)),
            "active": s.scalar(select(func.count()).select_from(Listing)
                               .where(Listing.state == "active")),
            "verified": s.scalar(select(func.count()).select_from(Listing)
                                 .where(Listing.state == listing_state.PUBLISHED)),
            "uncertified": s.scalar(select(func.count()).select_from(PatternVersion)
                                    .where(PatternVersion.certified.is_(False))),
            "rejected": s.scalar(select(func.count()).select_from(Job)
                                 .where(Job.job_type == "radar.score")),
        }


def test_pagination_covers_every_product_exactly_once_at_three_hundred_plus():
    v = _view(page_size=50)
    assert v["status"] == "OK", v.get("reason")
    assert v["matching"] == N and v["pages"] == -(-N // 50) and v["totals"]["products"] == N
    seen = []
    idx = C._index(DB)
    for page in range(1, v["pages"] + 1):
        got = C.query(idx, {"page_size": 50, "page": page})
        assert got["page"] == page
        seen += [(r["slug"], r["version"]) for r in got["items"]]
    assert len(seen) == N and len(set(seen)) == N, "a product was skipped or repeated"
    assert len(got["items"]) == N - 50 * (v["pages"] - 1)
    # Out-of-range and malformed paging is clamped, never empty-and-OK by accident.
    assert C.query(idx, {"page": 999, "page_size": 50})["page"] == v["pages"]
    assert C.query(idx, {"page": "x", "page_size": "y"})["page_size"] == C.PAGE_DEFAULT
    assert C.query(idx, {"page_size": 10_000})["page_size"] == C.PAGE_MAX
    # Above the P0 board's preview cap: the catalogue is not capped.
    from brambleloop.app.command_center import p0_board

    assert N > p0_board.ROW_LIMIT


def test_totals_match_sql_on_the_authoritative_tables():
    v = _view()
    sql = _sql_counts()
    t = v["totals"]
    assert t["products"] == sql["products"] == N
    assert sum(t["by_state"].values()) == N and sum(t["by_stage"].values()) == N
    assert t["by_stage"]["live_on_etsy"] == sql["active"]
    assert t["by_stage"]["etsy_draft_verified"] == sql["verified"]
    assert t["by_state"][PI.PUBLISHED] == sql["active"] + sql["verified"]
    assert t["by_stage"]["pattern_in_development"] == sql["uncertified"]
    assert t["by_stage"]["withdrawn_or_rejected"] == sql["rejected"]
    assert t["by_stage"]["research_candidate"] == N - sum(
        sql[k] for k in ("active", "verified", "uncertified", "rejected"))
    # Families: counted over every row, UNKNOWN where no concept names one.
    fam = t["by_category"]
    assert fam["basket"] == len([i for i in range(N) if i % 3 == 0 and i % 2])
    assert fam["throw"] == len([i for i in range(N) if i % 3 == 0 and not i % 2])
    assert fam[C.UNKNOWN] == N - fam["basket"] - fam["throw"]
    assert v["crosscheck"]["ok"] is True
    # A filtered count equals its total.
    idx = C._index(DB)
    for stage, n in t["by_stage"].items():
        assert C.query(idx, {"stage": stage})["matching"] == n, stage


def test_search_and_filters():
    idx = C._index(DB)
    one = C.query(idx, {"q": "AMBER-birch"})          # case-insensitive, slug substring
    assert one["matching"] >= 1 and all("amber-birch" in r["slug"] for r in one["items"])
    by_title = C.query(idx, {"q": "basket birch amber", "page_size": 200})  # title only
    assert by_title["matching"] >= 1 and all("basket birch amber" in r["title"].lower()
                                             for r in by_title["items"])
    assert C.query(idx, {"q": "%"})["matching"] == 0   # LIKE wildcards are literal
    assert C.query(idx, {"q": "_"})["matching"] == 0
    live = C.query(idx, {"state": PI.PUBLISHED, "page_size": 200})
    assert live["matching"] == _sql_counts()["active"] + _sql_counts()["verified"]
    assert all(r["state"] == PI.PUBLISHED for r in live["items"])
    basket = C.query(idx, {"category": "basket", "stage": "live_on_etsy"})
    assert all(r["category"] == "basket" and r["stage"] == "live_on_etsy"
               for r in basket["items"])
    assert C.query(idx, {"held": "none"})["matching"] + \
        C.query(idx, {"held": "any"})["matching"] == N
    owners = C.query(idx, {"owner": "product_truth"})
    assert owners["matching"] == _sql_counts()["uncertified"]
    assert all(r["next_action"]["job_type"] == "cir.compile" for r in owners["items"])


def test_evidence_links_and_next_action_per_product():
    idx = C._index(DB)
    live = C.query(idx, {"stage": "live_on_etsy"})["items"][0]
    ev = live["evidence"]
    assert ev["certificate"]["release_hash"] and ev["etsy"]["etsy_listing_id"]
    assert ev["etsy"]["read_back"] == "live"
    draft = C.query(idx, {"stage": "etsy_draft_verified"})["items"][0]
    assert draft["evidence"]["etsy"]["read_back"] == "verified"
    cand = C.query(idx, {"stage": "research_candidate"})["items"][0]
    assert cand["evidence"]["certificate"] is None and cand["evidence"]["etsy"] is None
    assert cand["next_action"] == {"action": C.NEXT_ACTION[PI.RESEARCH_CANDIDATE][0],
                                   "owner": "intelligence", "job_type": "radar.score"}
    # Sales unmeasured here: a live listing is never "sales monitoring" with zero sales.
    assert idx["sales_measured"] is False
    assert C.query(idx)["totals"]["by_stage"]["sales_monitoring"] == 0


def test_a_paid_hold_routes_the_next_action_to_the_owner():
    idx = C._index(DB)
    held = C.query(idx, {"held": "paid_approval"})
    assert held["matching"] == 1 == held["totals"]["by_held"]["paid_approval"]
    row = held["items"][0]
    assert row["slug"] == f"cat-fixture-{_word(5)}" and row["held"] == ["paid_approval"]
    assert row["next_action"]["owner"] == "owner" and row["next_action"]["job_type"] is None
    # The owner's queue is the paid hold plus every read-back-verified draft awaiting the
    # owner's activation (fix round 1: a verified draft is not live, so not finance's).
    assert C.query(idx, {"owner": "owner"})["matching"] == 1 + _sql_counts()["verified"]


def test_an_index_missing_a_product_row_fails_the_crosscheck():
    idx = C.build_index(DB)
    try:
        assert C.crosscheck(DB, idx["con"])["ok"] is True
        idx["con"].execute("DELETE FROM cat WHERE slug = ?", (f"cat-fixture-{_word(3)}",))
        got = C.crosscheck(DB, idx["con"])["checks"]["every_product_row_indexed"]
        assert got["ok"] is False and got["missing"] == [f"cat-fixture-{_word(3)}"]
    finally:
        idx["con"].close()


def test_an_underivable_row_is_unknown_never_revision_or_zero():
    real = PI.derive_row

    def flaky(db, rec, row, **kw):
        if row["slug"] == f"cat-fixture-{_word(7)}":
            raise RuntimeError("unreadable")
        return real(db, rec, row, **kw)

    with patch.object(PI, "derive_row", flaky):
        v = _view(q=_word(7))
    row = next(r for r in v["items"] if r["slug"] == f"cat-fixture-{_word(7)}")
    assert row["stage"] == C.UNKNOWN and row["state"] == C.UNKNOWN
    assert row["next_action"]["owner"] == C.UNKNOWN
    assert v["totals"]["unknown"] == 1 and v["totals"]["by_stage"][C.UNKNOWN] == 1
    assert v["totals"]["by_state"][PI.REVISION_REQUIRED] == 0
    assert v["crosscheck"]["ok"] is True and v["status"] == "OK"
    C.reset()


def test_an_unbuildable_catalogue_is_unknown_with_null_totals_never_zero():
    with patch.object(PI, "load_records", lambda db: (_ for _ in ()).throw(OSError("db"))):
        v = _view()
    assert v["status"] == C.UNKNOWN and "could not be built" in v["reason"]
    assert v["matching"] is None and all(x is None for x in v["totals"].values())
    C.reset()


def test_a_crosscheck_mismatch_makes_totals_unknown():
    real = C.crosscheck

    def drift(db, con):
        out = real(db, con)
        out["checks"]["every_product_row_indexed"]["ok"] = False
        out["ok"] = False
        return out

    with patch.object(C, "crosscheck", drift):
        v = _view()
    assert v["status"] == C.UNKNOWN and all(x is None for x in v["totals"].values())
    C.reset()
    idx = C._index(DB)
    assert C.query({**idx, "derived_total": N + 1})["status"] == C.UNKNOWN
    C.reset()


def test_a_mapping_that_loses_a_live_listing_is_caught_by_the_sql_crosscheck():
    real = C.stage18

    def lossy(item, listing, sold):
        got = real(item, listing, sold)
        return "research_candidate" if got == "live_on_etsy" and \
            item["slug"] == f"cat-fixture-{_word(1)}" else got

    with patch.object(C, "stage18", lossy):
        v = _view()
    chk = v["crosscheck"]["checks"]["published_listings_match"]
    assert chk["ok"] is False and chk["listings_table"] == chk["index"] + 1
    assert v["status"] == C.UNKNOWN and v["totals"]["products"] is None
    C.reset()


def test_pdf_gallery_and_listing_evidence_reach_the_row_end_to_end():
    """A certified release with its assets.build job, PDF hashes, verified listing images and
    a bound listing derives to Listing package completed, and the catalogue row links each
    piece of evidence. Seeded and removed here, so the other tests' counts are unchanged."""
    from brambleloop.core.models import AuditLog

    slug, rel = "cat-evidence-heath-iris", "f" * 64
    with DB.session() as s:
        p = Product(slug=slug, title="Fixture Evidence Basket")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             release_hash=rel, certificate={"content_hash": "cc"}))
        build = Job(agent="visual", job_type="assets.build", status=JobStatus.DONE,
                    inputs={"slug": slug, "version": "1.0.0", "release": rel},
                    outputs={"pdf_sha256_by_terminology": {"us": "a" * 64, "uk": "b" * 64}},
                    finished_at=NOW)
        s.add(build)
        s.flush()
        s.add_all([
            AuditLog(actor="t", action="assets.built", artifact=f"{slug}@1.0.0", job_id=build.id,
                     detail={"pdf_sha256_by_terminology": {"us": "a" * 64, "uk": "b" * 64}}),
            AuditLog(actor="t", action="assets.listing_images_built", artifact=f"{slug}@1.0.0",
                     job_id=build.id, detail={"frames": 6}),
            AuditLog(actor="t", action="listing.seo_drafted", artifact=f"{slug}@1.0.0",
                     detail={"search_share": 0.4}),
            Listing(product_slug=slug, version="1.0.0", title="t", description="d",
                    state="draft", release_hash=rel)])
        s.commit()
    try:
        row = _view(q=slug)["items"][0]
        assert row["slug"] == slug and row["state"] == PI.LISTING_COMPLETED, row["why"]
        assert row["stage"] in ("publication_gates_pending", "physical_sample_pending",
                                "physical_sample_passed")
        ev = row["evidence"]
        assert ev["certificate"]["release_hash"] == rel
        assert ev["pdf"]["sha256_by_terminology"] == {"us": "a" * 64, "uk": "b" * 64}
        assert ev["pdf"]["href"] == f"/api/cc/store/pdf/{slug}"
        assert ev["gallery"]["frames"] == 6 and ev["gallery"]["href"].endswith(slug)
        assert ev["listing_package"]["listing_id"] and ev["listing_package"]["audit_id"]
        assert ev["etsy"]["read_back"] == "no_remote_listing"
        assert row["next_action"]["owner"] in ("store_commerce", "owner")
    finally:
        with DB.session() as s:
            from sqlalchemy import delete

            s.execute(delete(AuditLog).where(AuditLog.artifact == f"{slug}@1.0.0"))
            s.execute(delete(Listing).where(Listing.product_slug == slug))
            s.execute(delete(Job).where(Job.job_type == "assets.build",
                                        Job.agent == "visual"))
            pid = s.scalar(select(Product.id).where(Product.slug == slug))
            s.execute(delete(PatternVersion).where(PatternVersion.product_id == pid))
            s.execute(delete(Product).where(Product.id == pid))
            s.commit()
        C.reset()
    assert _view()["totals"]["products"] == N


def test_the_route_is_owner_only_and_read_only():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/catalogue").status_code in (401, 403)
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200
    C.reset()
    writes = []

    def probe(conn, cursor, statement, params, context, executemany):
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        # The owner-session touch is the auth layer's bookkeeping, not the catalogue's.
        if head in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE") \
                and "cc_owner_sessions" not in statement:
            writes.append(statement[:120])

    event.listen(DB.engine, "before_cursor_execute", probe)
    try:
        r = c.get("/api/cc/catalogue?page_size=25&page=2&state=published&q=fixture")
    finally:
        event.remove(DB.engine, "before_cursor_execute", probe)
    assert r.status_code == 200, r.text
    data = r.json().get("data", r.json())
    assert data["tab"] == "CATALOGUE" and data["read_only"] is True and data["page"] == 2
    assert not writes, f"the catalogue wrote: {writes}"
    assert c.post("/api/cc/catalogue").status_code in (404, 405)


def test_every_inventory_state_maps_to_a_stage_and_unknown_is_never_inferred():
    for st in PI.PRIMARY_STATES:
        item = {"state": st, "evidence": {}, "physical_sample": {"status": "not_required"}}
        got = C.stage18(item, None, None)
        if st == PI.PUBLISHED:
            assert got == C.UNKNOWN       # published with no listing row: no evidence
        else:
            assert got in C.STAGE18_KEYS, (st, got)
    assert len(C.STAGES18) == 18 and len(set(C.STAGE18_KEYS)) == 18
    live = {"state": "active", "etsy_listing_id": "E"}
    pub = {"state": PI.PUBLISHED, "evidence": {}}
    assert C.stage18(pub, live, None) == "live_on_etsy"
    assert C.stage18(pub, live, False) == "live_on_etsy"
    assert C.stage18(pub, live, True) == "sales_monitoring"
    lc = {"state": PI.LISTING_COMPLETED, "evidence": {}}
    assert C.stage18({**lc, "physical_sample": {"status": "pending"}}, None, None) == \
        "physical_sample_pending"
    rv = {"state": PI.REVISION_REQUIRED, "evidence": {}}
    assert C.stage18(rv, {"state": "withdrawn"}, None) == "withdrawn_or_rejected"
    assert C.stage18(rv, None, None) == "revision_required"


if __name__ == "__main__":
    failed = passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
