"""W4-FMBATCH1: F-010 Attribute Drift Monitor.

F-010 (Final Master, launch-critical): "Periodically re-check category/attribute schemas for
platform changes." The daily `listing.taxonomy_refresh` re-read the schema and stored a new
snapshot on change, and nothing consumed the change: a listing certified on a node Etsy
renamed, removed or re-required kept its category and property payload. These tests pin the
consumer (`integrations.taxonomy_drift`): the diff, which listings it touches, the halting
incident, the re-queued `listing.seo`, and the resolution once the profile is rebuilt on the
new snapshot. No network call is made; the taxonomy responses are recorded shapes.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_ART = tempfile.TemporaryDirectory()
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART.name)

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.integrations import etsy_taxonomy as T  # noqa: E402
from brambleloop.integrations import taxonomy_drift as D  # noqa: E402

_TMP = tempfile.mkdtemp()


# ---- the diff (pure) -----------------------------------------------------------------------

def _snap(tree=None, props_for=FX.properties_response):
    nodes = T.flatten(tree if tree is not None else FX.TREE)
    return {"nodes": nodes,
            "properties": {str(n["id"]): props_for(n["id"])["results"]
                           for n in T.pattern_subtree(nodes)}}


def _tree_with(fn):
    tree = copy.deepcopy(FX.TREE)
    fn(tree)
    return tree


def _find(tree, nid):
    for n in tree:
        if n["id"] == nid:
            return n
        got = _find(n.get("children") or [], nid)
        if got is not None:
            return got
    return None


def test_an_unchanged_schema_is_no_drift():
    d = D.diff(_snap(), _snap())
    assert d["material"] is False and d["changed_ids"] == [], d


def test_a_renamed_parent_moves_every_node_under_it():
    renamed = _tree_with(lambda t: _find(t, 2113).update(name="Home Décor & Living"))
    d = D.diff(_snap(), _snap(renamed))
    assert {2113, 2114, 2115} <= set(d["moved_or_renamed"]), d
    assert 2111 not in d["changed_ids"]          # a sibling is untouched


def test_a_removed_node_and_a_re_required_property_are_drift():
    def gone(t):
        home = _find(t, 2113)
        home["children"] = [c for c in home["children"] if c["id"] != 2114]

    def required(nid):
        body = FX.properties_response(nid)
        if nid == 2115:
            body = copy.deepcopy(body)
            next(p for p in body["results"] if p["property_id"] == 3002)["is_required"] = True
        return body

    d = D.diff(_snap(), _snap(_tree_with(gone), required))
    assert 2114 in d["removed"] and 2114 in d["changed_ids"]
    assert d["schema_changed"]["2115"]["changed"] == ["3002"], d["schema_changed"]
    assert 2115 in d["changed_ids"]


def test_a_new_child_flags_its_parent_because_a_deeper_category_may_exist():
    def child(t):
        node = _find(t, 2115)
        node["children"] = [FX._node(2117, "Market Baskets", 5, 2115)]
        node["child_ids"] = [2117]

    d = D.diff(_snap(), _snap(_tree_with(child)))
    assert 2117 in d["added"] and 2115 in d["gained_child"] and 2115 in d["changed_ids"], d


def test_a_first_snapshot_has_nothing_to_drift_from():
    d = D.diff(None, _snap())
    assert d["first_snapshot"] is True and d["changed_ids"] == [] and not d["material"]


def test_judge_halts_only_a_chosen_listing_on_a_changed_node():
    d = {"changed_ids": [2115], "removed": [], "moved_or_renamed": [2115],
         "schema_changed": {}, "gained_child": []}
    profiles = [
        {"slug": "basket", "version": "1", "snapshot_id": 1, "category_status": "CHOSEN",
         "taxonomy_id": 2115},
        {"slug": "coaster", "version": "1", "snapshot_id": 1, "category_status": "CHOSEN",
         "taxonomy_id": 2114},
        {"slug": "throw", "version": "1", "snapshot_id": None, "category_status": "UNKNOWN",
         "taxonomy_id": None},
        {"slug": "rebuilt", "version": "1", "snapshot_id": 2, "category_status": "CHOSEN",
         "taxonomy_id": 2115},
    ]
    got = {v["slug"]: v for v in D.judge(profiles, d, new_id=2)}
    assert got["basket"]["halts"] is True and "moved or was renamed" in got["basket"]["why"]
    assert "coaster" not in got                    # its node, path and schema are unchanged
    assert got["throw"]["halts"] is False          # re-chosen, no incident (already refused)
    assert "rebuilt" not in got                    # already built on the new snapshot


# ---- the runtime: refresh -> incident + re-queue -> listing.seo -> resolved ------------------

_CHAIN: dict = {}


def _db(name: str):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _drain(db, job_types, name):
    from brambleloop.core.models import Phase
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    w = Worker(db, name, phase=Phase.SHADOW, job_types=list(job_types))
    for _ in range(20):
        if not w.run_once():
            break


def _chain_db():
    """One certified product through the chain, then search-certified on snapshot A."""
    import sqlite3
    from datetime import datetime

    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, EtsyTaxonomySnapshot, Job, JobStatus

    if not _CHAIN:
        from brambleloop.products.vessels import build_hexagon_coaster
        from brambleloop.queue.durable import JobQueue
        from brambleloop.runtime import pipeline  # noqa: F401
        from brambleloop.runtime.worker import Worker

        db = _db("chain")
        JobQueue(db).enqueue("quality_director", "gate.certify",
                             {"cir": build_hexagon_coaster().to_dict()})
        w = Worker(db, "fmb1-chain")
        for _ in range(100):
            if not w.run_once():
                break
        snap = FX.snapshot()
        with db.session() as s:
            s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="fixture",
                           detail={"ok": True, "application_id": "fixture"}))
            s.add(EtsyTaxonomySnapshot(sha256=T.fingerprint(snap["nodes"], snap["properties"]),
                                       node_count=len(snap["nodes"]), nodes=snap["nodes"],
                                       properties=snap["properties"]))
            seo = s.scalar(select(Job).where(Job.job_type == "listing.seo",
                                             Job.status == JobStatus.DONE))
            inputs = dict(seo.inputs)
        JobQueue(db).enqueue("listing", "listing.seo", inputs, priority=0,
                             idempotency_key="fmb1-seo-on-snapshot-a")
        _drain(db, ["listing.seo"], "fmb1-seo-a")
        _CHAIN["path"] = f"{_TMP}/chain.sqlite"
    dst = f"{_TMP}/copy-{datetime.now().timestamp()}.sqlite"
    with sqlite3.connect(_CHAIN["path"]) as src, sqlite3.connect(dst) as out:
        src.backup(out)
    return Database(f"sqlite:///{dst}")


def _profile(db):
    from brambleloop.core.models import ListingSearchProfile

    with db.session() as s:
        rows = list(s.scalars(select(ListingSearchProfile)))
        assert len(rows) == 1, [r.product_slug for r in rows]
        s.expunge(rows[0])
        return rows[0]


class _Client(FX.RecordedTaxonomyClient):
    """The recorded responses with one change applied to one node's property schema."""

    def __init__(self, change=None, tree=None):
        super().__init__()
        self.change, self.tree = change, tree

    def _call(self, method, path, *, operation, authority=None, **_kw):
        if path == "/seller-taxonomy/nodes" and self.tree is not None:
            self.calls.append(operation)
            return FX.FakeResponse({"count": len(self.tree), "results": self.tree})
        got = super()._call(method, path, operation=operation, authority=authority)
        node = None if path == "/seller-taxonomy/nodes" else int(path.split("/")[3])
        if self.change and node is not None:
            body = copy.deepcopy(got.body)
            self.change(node, body)
            return FX.FakeResponse(body)
        return got


def _refresh(db, client, key):
    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue

    T.client_factory = lambda _db: client
    try:
        JobQueue(db).enqueue("listing", "listing.taxonomy_refresh", {}, priority=0,
                             idempotency_key=key)
        _drain(db, ["listing.taxonomy_refresh"], f"fmb1-{key}")
    finally:
        T.client_factory = None
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == key))
        return dict(job.outputs or {})


def _incident(db, slug):
    from brambleloop.core.models import Incident

    with db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == f"taxonomy-drift:{slug}"))
        if row is not None:
            s.expunge(row)
        return row


def _queued_seo(db):
    from brambleloop.core.models import Job

    with db.session() as s:
        return [j.idempotency_key for j in s.scalars(select(Job).where(
            Job.job_type == "listing.seo")) if ":tx" in (j.idempotency_key or "")]


def _re_require_skill_level(node, body):
    for p in body.get("results") or []:
        if p["property_id"] == 3002:
            p["is_required"] = True
            p["possible_values"].append({"value_id": 5999, "name": "Expert",
                                         "scale_id": None, "equal_to": []})


def test_a_changed_schema_halts_the_listing_requeues_seo_and_resolves_on_rebuild():
    from brambleloop.gates.incidents import IncidentTracker

    db = _chain_db()
    before = _profile(db)
    assert before.category_status == "CHOSEN" and before.snapshot_id is not None, before
    slug = before.product_slug

    out = _refresh(db, _Client(change=_re_require_skill_level), "fmb1-tax-drift")
    assert out["ran"] and out["new_snapshot"] is True, out
    new_id = out["snapshot_id"]
    assert new_id != before.snapshot_id
    drift = out["drift"]
    assert drift["state"] == "measured" and drift["incidents_opened"] == [slug], drift
    # The halting incident: publication (and Gate E) refuse the product while it is open.
    inc = _incident(db, slug)
    assert inc is not None and not inc.resolved and inc.halts_publication and inc.severity == "P1"
    assert inc.detail["snapshot_id"] == new_id and "property schema changed" in inc.summary
    assert IncidentTracker(db).publication_halted(slug) is True
    # listing.seo was re-queued once, keyed to the new snapshot, and ran on it.
    assert len(_queued_seo(db)) == 1 and f"tx{new_id}" in _queued_seo(db)[0], _queued_seo(db)
    _drain(db, ["listing.seo"], "fmb1-seo-b")
    after = _profile(db)
    assert after.snapshot_id == new_id, (after.snapshot_id, new_id)
    inc = _incident(db, slug)
    assert inc.resolved is True and str(new_id) in inc.detail["resolution"], inc.detail
    assert IncidentTracker(db).publication_halted(slug) is False

    # The next daily read of the same schema is a confirmation, not a drift: nothing re-runs.
    again = _refresh(db, _Client(change=_re_require_skill_level), "fmb1-tax-same")
    assert again["new_snapshot"] is False and "drift" not in again, again
    assert len(_queued_seo(db)) == 1


def test_a_change_elsewhere_in_the_tree_leaves_a_valid_listing_alone():
    db = _chain_db()
    before = _profile(db)
    chosen = before.taxonomy_id

    def unrelated(node, body):
        if node != chosen and node != 2120:
            for p in body.get("results") or []:
                if p["property_id"] == 3004:
                    p["name"] = "Subject matter"

    out = _refresh(db, _Client(change=unrelated), "fmb1-tax-elsewhere")
    assert out["new_snapshot"] is True, out
    assert out["drift"]["incidents_opened"] == [] and out["drift"]["requeued"] == [], out
    assert _incident(db, before.product_slug) is None
    assert _queued_seo(db) == []


def test_drift_with_nothing_to_rerun_is_reported_and_never_halts_certification():
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.gates.incidents import IncidentTracker

    db = _chain_db()
    slug = _profile(db).product_slug
    # No completed listing.seo to re-run (e.g. retention removed it): every one reads CANCELLED.
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "listing.seo")):
            j.status = JobStatus.CANCELLED
    out = _refresh(db, _Client(change=_re_require_skill_level), "fmb1-tax-norerun")
    drift = out["drift"]
    assert drift["requeued"] == [] and drift["not_requeued"][0]["slug"] == slug, drift
    inc = _incident(db, slug)
    assert inc is not None and not inc.resolved and inc.halts_publication is False
    assert "no listing.seo could be re-queued" in inc.summary
    assert IncidentTracker(db).publication_halted(slug) is False


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"\n  {passes} passing, {fails} failing")
    sys.exit(1 if fails else 0)
