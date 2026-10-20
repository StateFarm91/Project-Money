"""W4-FIRSTSALE follow-up: retention for durable_artifacts, the seo root cause, alt-text fit.

Retention (`commerce.deliverables.retention_plan` / `prune`):
* keeps every release that is listed (any non-withdrawn listing) or sold (an Order names it;
  an Order with no version keeps every release of that product), plus the newest N others;
* never prunes a hash any protected release names, even when another release kept it first;
* never prunes a hash a delivery record names (store.published / store.pdf_hash_verified);
* never prunes a row that was not kept as a certified customer deliverable;
* a dry run deletes nothing; unreadable state prunes nothing.

SEO cause (`launch.first_sale.seo_cause`): a refusal whose only failing checks are the
category and its attributes reads "category UNKNOWN (B2) only"; an independent failure is named.

Alt text (`publish.disclosed_listing.alt_text`): at most Etsy's advised 250 characters for the
Launch-0 heroes, the disclosure first, the size kept.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale_retention.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import deliverables as D  # noqa: E402

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _world():
    """Product A: 1.0 (listed), 1.1, 1.2, 1.3, 1.4 (newest). Product B: 2.0, 2.1, sold with
    no version. Every release has two kept PDFs; one frame is shared by A@1.1 and A@1.0."""
    from brambleloop.core.db import Database
    from brambleloop.core.models import (AuditLog, Customer, DurableArtifact, Listing,
                                         ListingAsset, Order, PatternVersion, Product)

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/r.sqlite")
    db.create_all()
    shas: dict[str, list[str]] = {}
    shared = b"frame shared by A@1.0 and A@1.1"
    with db.session() as s:
        for slug, versions in (("prod-a", ["1.0", "1.1", "1.2", "1.3", "1.4"]),
                               ("prod-b", ["2.0", "2.1"])):
            p = Product(slug=slug, title=slug)
            s.add(p)
            s.flush()
            for i, v in enumerate(versions):
                s.add(PatternVersion(product_id=p.id, version=v, cir_json={}, certified=True,
                                     created_at=T0 + timedelta(days=i)))
                pdfs = {t: f"{slug}@{v} {t} pdf".encode() for t in ("US", "UK")}
                s.add(AuditLog(actor="assets", action="assets.built", artifact=f"{slug}@{v}",
                               detail={"pdf_sha256_by_terminology":
                                       {t: _sha(b) for t, b in pdfs.items()}}))
                for t, b in pdfs.items():
                    s.add(DurableArtifact(sha256=_sha(b), payload=b, bytes_len=len(b),
                                          why_kept=D.keep_why(slug, v, f"pdf:{t}")))
                shas[f"{slug}@{v}"] = [_sha(b) for b in pdfs.values()]
        # the shared frame, kept first by A@1.1 (a release retention will drop)
        s.add(DurableArtifact(sha256=_sha(shared), payload=shared, bytes_len=len(shared),
                              why_kept=D.keep_why("prod-a", "1.1", "frame")))
        for v in ("1.0", "1.1"):
            s.add(ListingAsset(product_slug="prod-a", version=v, position=1,
                               asset_class="photo", role="hero", sha256=_sha(shared)))
        s.add(Listing(product_slug="prod-a", version="1.0", title="t", description="d",
                      tags=[], state="draft"))
        s.add(Listing(product_slug="prod-a", version="1.2", title="t", description="d",
                      tags=[], state="withdrawn"))
        c = Customer(customer_ref="cust-1")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="receipt-1", product_slug="prod-b",
                    version=""))
        # a delivery record naming one of A@1.1's PDFs
        s.add(AuditLog(actor="store", action="store.published", artifact="prod-a@1.1",
                       detail={"files": {"US": shas["prod-a@1.1"][0]}}))
        # a row kept for its own reasons (the canonical model's reference pack)
        pack = b"canonical model reference image"
        s.add(DurableArtifact(sha256=_sha(pack), payload=pack, bytes_len=len(pack),
                              why_kept="canonical model reference pack v15"))
    return db, shas, _sha(shared), _sha(pack)


def _held(db) -> set[str]:
    from sqlalchemy import select

    from brambleloop.core.models import DurableArtifact

    with db.session() as s:
        return set(s.scalars(select(DurableArtifact.sha256)))


def test_retention_keeps_listed_sold_recent_and_delivered_and_prunes_the_rest():
    db, shas, shared, pack = _world()
    plan = D.retention_plan(db, keep_previous=2)
    assert set(plan["protected_releases"]) == {
        "prod-a@1.0",                     # listed
        "prod-a@1.4", "prod-a@1.3",       # newest two others
        "prod-b@2.0", "prod-b@2.1"}       # sold with no version: every release
    pruned = {p["sha256"] for p in plan["prune"]}
    expected = set(shas["prod-a@1.2"]) | {shas["prod-a@1.1"][1]}
    assert pruned == expected, (sorted(pruned), sorted(expected))
    assert shared not in pruned, "a hash a protected release names is never pruned"
    assert shas["prod-a@1.1"][0] not in pruned, "a delivered file is never pruned"
    assert pack not in pruned, "a row kept for another reason is never pruned"

    before = _held(db)
    dry = D.prune(db, keep_previous=2, dry_run=True)
    assert dry["pruned"] == 0 and dry["candidates"] == 3 and _held(db) == before
    out = D.prune(db, keep_previous=2)
    assert out["pruned"] == 3 and _held(db) == before - expected
    # idempotent: nothing more to prune
    assert D.prune(db, keep_previous=2)["pruned"] == 0


def test_keep_previous_zero_still_protects_listed_and_sold():
    db, shas, shared, _ = _world()
    plan = D.retention_plan(db, keep_previous=0)
    assert set(plan["protected_releases"]) == {"prod-a@1.0", "prod-b@2.0", "prod-b@2.1"}
    pruned = {p["sha256"] for p in plan["prune"]}
    assert not (set(shas["prod-a@1.0"]) & pruned) and shared not in pruned
    assert set(shas["prod-a@1.4"]) <= pruned


def test_unreadable_state_prunes_nothing():
    db, *_ = _world()
    before = _held(db)
    real = D.retention_plan
    D.retention_plan = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("unreadable"))
    try:
        out = D.prune(db)
    finally:
        D.retention_plan = real
    assert out["pruned"] == 0 and "nothing pruned" in out["why"] and _held(db) == before


def test_readiness_runs_retention_after_securing():
    import inspect

    from brambleloop.runtime import release

    src = inspect.getsource(release.handle_launch_readiness)
    assert src.index("deliverables_mod.secure_release(") < src.index("deliverables_mod.prune(")


def test_seo_cause_separates_category_only_from_independent_failures():
    from brambleloop.launch import first_sale as FS

    ok = {"copy": True, "tags": True, "description": True, "hero": True}
    only = {"state": "FAIL", "category_status": "UNKNOWN",
            "checks": {**ok, "category": None, "attributes": False},
            "reasons": ["search certificate (F-005): category UNKNOWN -- no stored Etsy",
                        "search certificate (F-004) attributes: no category, so no schema"]}
    c = FS.seo_cause(only)
    assert c["category_only"] and not c["independent_failing"], c
    g = FS._seo_gate(only)
    assert g["state"] == "FAIL" and "category UNKNOWN (B2) only" in g["why"]
    assert g["blocker"] == "B2" and g["who_acts"] == "company"
    tags = dict(only, checks={**only["checks"], "tags": False},
                reasons=only["reasons"] + ["search certificate (F-004) tags: 2 duplicates"])
    c = FS.seo_cause(tags)
    assert not c["category_only"] and c["independent_failing"] == ["tags"], c
    assert "independent of the category" in FS._seo_gate(tags)["why"]
    stale = dict(only, reasons=only["reasons"] + ["search certificate (F-294): changed"])
    assert not FS.seo_cause(stale)["category_only"]
    unread = dict(only, checks={})
    assert not FS.seo_cause(unread)["category_only"], "unread checks prove nothing"
    chosen = dict(only, category_status="CHOSEN")
    assert not FS.seo_cause(chosen)["category_only"]


def test_launch0_hero_alt_texts_fit_etsys_advice_and_keep_the_disclosure():
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import disclosed_listing as DL
    from brambleloop.visual import disclosed_render as R

    checked = 0
    for slug in l0.LAUNCH0_SLUGS:
        for v in l0.candidate(slug).variants:
            cir = l0.cir_for(v.build)
            for rf in R.listing_set(cir):          # the exact frames the listing uploads
                man, view = rf.manifest, rf.manifest.get("view")
                alt = DL.alt_text(man, cir)
                checked += 1
                assert len(alt) <= DL.ALT_TEXT_ADVICE, (cir.slug, view, len(alt), alt)
                assert alt.startswith(DL.DISCLOSURE), alt
                if (man.get("finished_dimensions_cm") or {}).get("width"):
                    assert " cm" in alt, alt
    assert checked >= 20, checked


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc(limit=4)
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500], flush=True)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
