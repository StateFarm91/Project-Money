"""W4-FMEND (F-834): runtime evidence packets are emitted only for what a rehearsal recorded.

`scripts/emit_runtime_packets.py` turns a recorded `shadow_rehearsal.py` run into
`final_proof` packets: a packet only for a launch-critical row whose producer is the handler
of a job the rehearsal ran, carrying only the producer and live-root receipts, never an
independent review, and refusing a rehearsal from a dirty tree. Its packets stay BLOCKED.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_fmend_packets.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import final_proof  # noqa: E402

_spec = importlib.util.spec_from_file_location("emit_runtime_packets",
                                               ROOT / "scripts" / "emit_runtime_packets.py")
emitter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emitter)

HEAD = "c" * 40
REFS = {"gate.certify": "runtime/pipeline.py::handle_certify",
        "listing.seo": "runtime/release.py::handle_listing_seo",
        "store.publish": "runtime/pipeline.py::handle_store_publish"}


def _rehearsal(dirty=False):
    return {"head": HEAD, "head_short": HEAD[:7], "tree_dirty": dirty,
            "started_at": "2026-10-11T05:26:00+00:00",
            "steps": [{"step": "gate.certify", "outcome": "PASS",
                       "observed": {"job": 1, "status": "done"}},
                      {"step": "listing.seo", "outcome": "FAILED",
                       "observed": {"job": 2, "status": "dead"}},
                      {"step": "store.publish[shadow]", "outcome": "REFUSED_AS_EXPECTED",
                       "observed": {"job": 3, "status": "dead"}}]}


def _rows():
    return [{"uid": "F-1", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/pipeline.py::handle_certify",
             "protected_action_applicability": "unprotected"},
            {"uid": "F-2", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/release.py::handle_listing_seo",
             "protected_action_applicability": "unprotected"},
            {"uid": "F-3", "launch_class": "MATURE",
             "producer": "src/brambleloop/runtime/pipeline.py::handle_certify",
             "protected_action_applicability": "unprotected"},
            {"uid": "F-4", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/pipeline.py::handle_store_publish",
             "protected_action_applicability": "protected"},
            {"uid": "F-5", "launch_class": "LAUNCH-CRITICAL", "producer": "lib/x.py::f",
             "protected_action_applicability": "unprotected"}]


def test_only_rows_whose_producer_job_ran_get_a_packet():
    packets = emitter.emit(_rows(), _rehearsal(), "r.json", "0" * 64, REFS)
    # F-2's job FAILED, F-3 is not launch-critical, F-5 names no handler the rehearsal ran.
    assert sorted(p["uid"] for p in packets) == ["F-1", "F-4"], packets
    for p in packets:
        assert set(p["chain"]) == {"producer"}, "only the producer stage is claimed"
        assert "independent_review" not in p and "suite" not in p
        assert p["head"] == HEAD and p["run_id"].startswith("shadow_rehearsal:")


def test_a_dirty_rehearsal_is_refused():
    try:
        emitter.emit(_rows(), _rehearsal(dirty=True), "r.json", "0" * 64, REFS)
    except ValueError:
        return
    raise AssertionError("a dirty-tree rehearsal produced packets")


def test_emitted_packets_bind_the_artifact_and_stay_blocked():
    root = Path(tempfile.mkdtemp(prefix="fmend_packets_"))
    reh = root / "r.json"
    reh.write_text(json.dumps(_rehearsal()))
    digest = hashlib.sha256(reh.read_bytes()).hexdigest()
    rows = _rows()
    packets = emitter.emit(rows, _rehearsal(), "r.json", digest, REFS)
    report = final_proof.audit(rows, packets, head=HEAD, root=root)
    by = {r["uid"]: r for r in report["rows"]}
    assert report["certified"] is False
    assert all(r["verdict"] == "BLOCKED" for r in report["rows"])
    errs = by["F-1"]["errors"]
    assert "missing run identity" not in errs and "unbound receipt:producer" not in errs, errs
    assert not any(e.startswith("artifact digest mismatch") for e in errs), errs
    assert "worker self-review" in errs and "missing receipt:durable_state" in errs, errs
    # A tampered artifact unbinds every receipt.
    reh.write_text(json.dumps(_rehearsal()) + " ")
    errs = {r["uid"]: r for r in final_proof.audit(rows, packets, head=HEAD,
                                                    root=root)["rows"]}["F-1"]["errors"]
    assert "artifact digest mismatch:rehearsal" in errs, errs


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
