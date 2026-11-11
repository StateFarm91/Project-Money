"""F-848 (review 6773190553 #4/#5): readiness is explained item by item, and can be judged
read-only on a restored production export.

* `explain_readiness` names, for every outstanding requirement, who can clear it (its own
  `blocked_by`) and why it fails, so a BLOCKED owner transition is never a bare list.
* `readiness_from_export` restores a portable continuity export into a throwaway database and
  reports the transition verdict there. The export here is made from a scratch database (no
  production data, no credential); the operator produces the real one.

Run: cd brambleloop && $PY tests/test_readiness_from_export.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _db_with_open_p1(tmp: Path):
    from brambleloop.core.db import Database
    from brambleloop.core.models import Incident

    db = Database(f"sqlite:///{tmp}/src.sqlite")
    db.create_all()
    with db.session() as s:
        s.add(Incident(severity="P1", signature="rehearsal-probe:p1", summary="probe",
                       halts_publication=True))
        s.add(Incident(severity="P3", signature="rehearsal-probe:p3", summary="harmless"))
    return db


def test_explain_readiness_names_who_clears_each_item_and_why():
    rehearsal = _load("shadow_rehearsal")
    with tempfile.TemporaryDirectory() as t:
        db = _db_with_open_p1(Path(t))
        explained = rehearsal.explain_readiness(db, to="staging")
    keys = {e["key"]: e for e in explained}
    inc = keys["no_open_incidents"]
    assert inc["blocked_by"] == "build" and inc["cleared_by"] == "ours (build)", inc
    assert "P1" in inc["why"], inc            # readiness's own evidence: every open severity
    assert explained, explained
    for e in explained:
        assert isinstance(e["why"], str) and e["why"].strip(), e     # MED-2: never empty
        assert e["cleared_by"] != "unclassified" or e["blocked_by"] is None, e
        assert e["key"] and "evidence" in e, e
    owner = [e["key"] for e in explained if e["blocked_by"] == "owner"]
    assert owner, explained                                 # a fresh shop has owner gates


def test_readiness_from_export_restores_and_judges_read_only():
    from brambleloop.core import continuity

    script = _load("readiness_from_export")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        db = _db_with_open_p1(tmp)
        export = tmp / "export.jsonl"
        continuity.export(db, export)
        before = export.read_bytes()
        beside = sorted(p.name for p in tmp.iterdir())
        temp_root = Path(tempfile.gettempdir())
        temp_before = {p.name for p in temp_root.iterdir()}
        report = script.readiness_from_export(export, to="staging")
        assert export.read_bytes() == before                # the export is only read
        # review 6776323331 MED-1: the restored copy of production data does not survive --
        # nothing new beside the export, and nothing left in the temp root
        assert sorted(p.name for p in tmp.iterdir()) == beside, list(tmp.iterdir())
        left = {p.name for p in temp_root.iterdir()} - temp_before
        assert not left, left
    assert report["restored_rows"] >= 2 and report["ready"] is False, report
    assert "shop_trustworthy:no_open_incidents" in report["failing"], report["failing"]
    explained = {e["key"]: e for e in report["explained"]}
    assert "P1" in explained["no_open_incidents"]["why"], explained["no_open_incidents"]
    assert "no_open_incidents" in report["by_clearer"]["ours (build)"], report["by_clearer"]


def test_the_restored_copy_is_deleted_even_when_the_verdict_raises():
    """MED-1: a failure after the restore must not leave the copy on disk."""
    from brambleloop.core import continuity
    from brambleloop.launch import readiness as R

    script = _load("readiness_from_export")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        export = tmp / "export.jsonl"
        continuity.export(_db_with_open_p1(tmp), export)
        temp_root = Path(tempfile.gettempdir())
        temp_before = {p.name for p in temp_root.iterdir()}
        saved = R.transition_verdict

        def boom(*a, **k):
            raise RuntimeError("verdict failed")
        R.transition_verdict = boom
        try:
            script.readiness_from_export(export)
        except RuntimeError:
            pass
        else:
            raise AssertionError("the failure was swallowed")
        finally:
            R.transition_verdict = saved
        left = {p.name for p in temp_root.iterdir()} - temp_before
        assert not left, left


def test_shortfall_keys_match_whole_tokens_only():
    """Review 6781897314 LOW: `units` / `total_units` are not shortfalls; `unpriced` is."""
    rehearsal = _load("shadow_rehearsal")
    plain = rehearsal.why_unmet("every listing has a price", {"total_units": 3, "units": 1})
    assert plain.startswith("not met: every listing has a price"), plain
    named = rehearsal.why_unmet("every listing has a price", {"unpriced": ["a@1"], "units": 2})
    assert named.startswith("unpriced:") and "units" not in named, named
    for key in ("listings_short_of_frames", "releases_without_search_baseline", "not_checked",
                "with_only_unusable_assets", "rehearsal_failed"):
        assert rehearsal._names_a_shortfall(key), key
    for key in ("units", "total_units", "unique_tags", "funnel", "underlay"):
        assert not rehearsal._names_a_shortfall(key), key


def test_the_engine_is_disposed_on_success_and_on_failure():
    """Review 6781897314 LOW: the restored database's engine is closed before its directory
    is removed, whether or not the verdict raises."""
    from brambleloop.core import continuity
    from brambleloop.core import db as db_mod
    from brambleloop.launch import readiness as R

    script = _load("readiness_from_export")
    disposed = []
    real_init = db_mod.Database.__init__

    def tracking_init(self, *a, **k):
        real_init(self, *a, **k)
        real_dispose = self.engine.dispose
        self.engine.dispose = lambda *x, **y: (disposed.append(True), real_dispose(*x, **y))
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        export = tmp / "export.jsonl"
        continuity.export(_db_with_open_p1(tmp), export)
        db_mod.Database.__init__ = tracking_init
        saved = R.transition_verdict
        try:
            script.readiness_from_export(export)
            assert disposed == [True], disposed
            R.transition_verdict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
            try:
                script.readiness_from_export(export)
            except RuntimeError:
                pass
            assert disposed == [True, True], disposed
        finally:
            db_mod.Database.__init__ = real_init
            R.transition_verdict = saved


def test_a_truncated_export_is_refused_not_judged():
    from brambleloop.core import continuity

    script = _load("readiness_from_export")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        db = _db_with_open_p1(tmp)
        export = tmp / "export.jsonl"
        continuity.export(db, export)
        lines = export.read_text().splitlines(keepends=True)
        export.write_text("".join(lines[:-1]))               # drop the closing record
        try:
            script.readiness_from_export(export)
        except Exception as exc:  # noqa: BLE001 - any refusal is the point
            assert "trunc" in str(exc).lower() or "incomplete" in str(exc).lower() \
                or "finish" in str(exc).lower(), exc
        else:
            raise AssertionError("a truncated export was judged")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
