"""GALLERY-START: the Patterns & Blueprints "Self-published" property is decided, and a search
certificate refused only on attributes is re-certified once per deployed commit.

Production 2026-11-22 06:55Z: every Launch-0 release on node 6343 held a certificate REFUSED
on `attributes` (the node's "Self-published" property had no rule and read UNDECIDED), so
`certified_payload` raised, the listing package carried a non-image blocker, and all 14 FLUX
gallery runs waited at `waiting_for_sale_admission`.

Run: cd brambleloop && python3 tests/test_gallery_start.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.commerce import category as C  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, ListingSearchProfile  # noqa: E402
from brambleloop.ops import search_recertify as R  # noqa: E402

SELF_PUB_ID = 102868018029


def _snapshot(values):
    snap = FX.snapshot()
    snap["properties"] = {k: list(v) + [FX.prop(SELF_PUB_ID, "Self-published", values)]
                          for k, v in snap["properties"].items()}
    return snap


def _facts(category):
    return C.Facts(category=category, difficulty="confident beginner",
                   colors=[("cream", "#FAF6EB"), ("wine", "#6E1F2A")],
                   width_cm=76.0, height_cm=91.0)


def test_self_published_is_set_yes_and_completes_properties():
    snap = _snapshot(("Yes", "No"))
    for category in ("coaster", "basket", "placemat"):
        choice = C.choose(snap, category)
        assert choice.status == C.CHOSEN, (category, choice.why)
        props = C.properties_for(snap, choice, _facts(category))
        by_name = {d["name"]: d for d in props["decisions"]}
        d = by_name["Self-published"]
        assert d["status"] == C.SET and d["values"] == ["Yes"], d
        assert not any("Self-published" in g for g in props.get("gaps") or []), props["gaps"]


def test_self_published_without_a_yes_value_stays_missing():
    snap = _snapshot(("Publisher", "Other"))
    choice = C.choose(snap, "coaster")
    props = C.properties_for(snap, choice, _facts("coaster"))
    d = {x["name"]: x for x in props["decisions"]}["Self-published"]
    assert d["status"] == C.MISSING, d          # not guessed
    assert props["complete"] is False


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/g.db")
    db.create_all()
    return db


def _profile(s, slug, verdict, failed):
    s.add(ListingSearchProfile(product_slug=slug, version="1.0.0", verdict=verdict,
                               certificate={"verdict": verdict, "failed": failed}))


def _seo_job(s, slug):
    s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.DONE,
              inputs={"slug": slug, "version": "1.0.0", "release": "r" * 64}))


def test_recertify_enqueues_only_attribute_refusals_once_per_commit():
    db = _db()
    with db.session() as s:
        _profile(s, "coaster", "REFUSED", ["attributes", "hero"])   # eligible
        _profile(s, "basket", "REFUSED", ["attributes"])            # eligible
        _profile(s, "placemat", "REFUSED", ["attributes", "tags"])  # a real copy problem
        _profile(s, "throw", "PASS", [])                            # fine
        _profile(s, "runner", "REFUSED", ["attributes"])            # no seo job to re-run
        for slug in ("coaster", "basket", "placemat", "throw"):
            _seo_job(s, slug)
    calls, seen = [], set()

    class DuplicateJob(Exception):
        pass

    def enqueue(agent, job_type, inputs, idempotency_key):
        if idempotency_key in seen:
            raise DuplicateJob(idempotency_key)
        seen.add(idempotency_key)
        calls.append((agent, job_type, inputs, idempotency_key))

    out = R.run(db, enqueue, commit="abcdef0123456789")
    assert sorted(out["enqueued"]) == ["basket@1.0.0", "coaster@1.0.0"], out
    assert out["candidates"] == 3 and len(out["skipped"]) == 1, out
    for agent, job_type, inputs, key in calls:
        assert (agent, job_type) == ("listing", "listing.seo")
        assert inputs["rebuild"] == "recert-abcdef012345" and "fix_only" not in inputs
        assert key.startswith("seo:")
    again = R.run(db, enqueue, commit="abcdef0123456789")
    assert again["enqueued"] == [] and again["duplicates"] == 2, again
    nxt = R.run(db, enqueue, commit="fedcba9876543210")
    assert len(nxt["enqueued"]) == 2, nxt                     # a new deploy re-asks


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("OK")
