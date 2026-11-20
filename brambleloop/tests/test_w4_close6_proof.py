"""W4-CLOSE6: F-834 Consumption Required -- consumer receipts in the runtime evidence packets.

  F-834  "Producing a reading is insufficient when the requirement exists to influence a
          downstream decision/action; prove the consumer."

`build2/final_proof.py` already refused a row without a receipt for each stage, producer ->
durable_state -> consumer -> decision -> effect -> result, bound to one run. But the only
recorded run, `scripts/shadow_rehearsal.py`, recorded job outcomes and nothing else. So
`scripts/emit_runtime_packets.py` could claim the producer and nothing past it, and every row
stayed BLOCKED on the consumer.

The rehearsal now records the edges (`record_edges`):
- the row each producer job wrote;
- that the `store.publish` job read that state: its gates name the same version, and its key
  names the same certified release;
- what it decided, the effect row it wrote, and the result.

The emitter turns a recorded edge into receipts only for a row whose producer AND named
consumer are the handlers on that edge. The independent review stays the reviewer's: the
emitter never writes one, so packets remain BLOCKED on review, production-producer and
failure-test receipts. They are no longer blocked on the consumer chain.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_proof.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import final_proof  # noqa: E402

_spec = importlib.util.spec_from_file_location("emit_runtime_packets_c6",
                                               ROOT / "scripts" / "emit_runtime_packets.py")
emitter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emitter)

HEAD = "d" * 40
REL = "7c63dbdd501fa6b1ec89a12b29ad50ad26f52091884b5d60893fafa4a27d9684"
REFS = {"gate.certify": "runtime/pipeline.py::handle_certify",
        "listing.seo": "runtime/release.py::handle_listing_seo",
        "store.publish": "runtime/pipeline.py::handle_store_publish"}
CONSUMER = "src/brambleloop/runtime/pipeline.py::handle_store_publish"
STAGE_ERRORS = ("missing receipt:durable_state", "missing receipt:consumer",
                "missing receipt:decision", "missing receipt:effect", "missing receipt:result",
                "broken evidence edge", "consumer receipt does not bind")


def _edges(release_in_key=True):
    key = f"publish:cloudline-baby-blanket:1.2.0:{REL[:12] if release_in_key else 'other'}:c9"
    return {
        "durable": {
            "gate.certify": {"identity": f"pattern_versions:1#certified:{REL}", "job": 2,
                             "audit": "audit_log:3", "release_hash": REL},
            "listing.seo": {"identity": "listings:1", "job": 7, "audit": "audit_log:24",
                            "release_hash": REL}},
        "consumers": {"store.publish": {
            "job": 10, "status": "dead",
            "reads": {"audit": "audit_log:40", "slug": "cloudline-baby-blanket",
                      "version": "1.2.0", "same_version": True, "idempotency_key": key,
                      "same_release": release_in_key, "listing_same_release": True},
            "decision": {"refused": True, "reason": "shadow mode: no live publication",
                         "release_gates_would_block": True},
            "effect": {"audit": "audit_log:41", "action": "store.publish_refused"},
            "result": {"store_published_rows": 0, "listing": 1, "etsy_listing_id": ""}}}}


def _rehearsal(edges):
    return {"head": HEAD, "head_short": HEAD[:7], "tree_dirty": False,
            "started_at": "2026-10-20T12:00:00+00:00", "chain_edges": edges,
            "steps": [{"step": "gate.certify", "outcome": "PASS", "observed": {"job": 2}},
                      {"step": "listing.seo", "outcome": "PASS", "observed": {"job": 7}},
                      {"step": "store.publish[shadow]", "outcome": "REFUSED_AS_EXPECTED",
                       "observed": {"job": 10}}]}


def _rows(consumer=CONSUMER):
    return [{"uid": "F-477", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/pipeline.py::handle_certify",
             "consumer": consumer, "protected_action_applicability": "unprotected"},
            {"uid": "F-048", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/release.py::handle_listing_seo",
             "consumer": consumer, "protected_action_applicability": "unprotected"},
            {"uid": "F-900", "launch_class": "LAUNCH-CRITICAL",
             "producer": "src/brambleloop/runtime/pipeline.py::handle_certify",
             "consumer": "a listing description", "protected_action_applicability": "unprotected"}]


def _validate(rows, packets):
    root = Path(tempfile.mkdtemp())
    (root / "r.json").write_text("{}")
    sha = hashlib.sha256((root / "r.json").read_bytes()).hexdigest()
    for p in packets:
        p["artifacts"]["rehearsal"]["sha256"] = sha
    by = {p["uid"]: p for p in packets}
    return {r["uid"]: final_proof.validate(r, by.get(r["uid"], {}), head=HEAD, root=root)
            for r in rows}


def test_a_recorded_edge_gives_every_chain_stage_a_bound_receipt():
    rows = _rows()
    packets = emitter.emit(rows, _rehearsal(_edges()), "r.json", "0" * 64, REFS)
    by = {p["uid"]: p for p in packets}
    for uid in ("F-477", "F-048"):
        assert set(by[uid]["chain"]) == set(final_proof.STAGES), by[uid]["chain"]
        assert by[uid]["chain"]["consumer"]["identity"] == CONSUMER
        assert by[uid]["chain"]["consumer"]["job"] == 10
        assert by[uid]["not_observed"] == {}, by[uid]["not_observed"]
    assert by["F-477"]["chain"]["durable_state"]["identity"].endswith(REL)
    assert by["F-048"]["chain"]["durable_state"]["identity"] == "listings:1"
    assert set(by["F-900"]["chain"]) == {"producer"}, "its consumer is not the recorded one"
    out = _validate(rows, packets)
    for uid in ("F-477", "F-048"):
        errs = out[uid]["errors"]
        assert not [e for e in errs if e.startswith(STAGE_ERRORS)], errs
        assert out[uid]["verdict"] == "BLOCKED", "review is still the reviewer's"
        assert "worker self-review" in errs or any("independent_review" in e for e in errs)
    assert any(e.startswith("missing receipt:durable_state") for e in out["F-900"]["errors"])


def test_an_unbound_read_claims_nothing_past_the_producer():
    rows = _rows()
    for edges in (_edges(release_in_key=False),
                  {"durable": _edges()["durable"], "consumers": {}}, {}):
        packets = emitter.emit(rows, _rehearsal(edges), "r.json", "0" * 64, REFS)
        assert all(set(p["chain"]) == {"producer"} for p in packets), packets
    other = copy.deepcopy(_rows(consumer="src/brambleloop/runtime/pipeline.py::handle_x"))
    packets = emitter.emit(other, _rehearsal(_edges()), "r.json", "0" * 64, REFS)
    assert all(set(p["chain"]) == {"producer"} for p in packets)


def test_the_recorded_rehearsal_binds_the_edge_on_this_head():
    ev = sorted((ROOT / "research/final_build/w4/evidence_CLOSE6").glob("shadow_rehearsal_*.json"))
    assert ev, "the rehearsal evidence for this branch is committed"
    reh = json.loads(ev[-1].read_text())
    e = reh["chain_edges"]
    pub = e["consumers"]["store.publish"]
    assert pub["reads"]["same_version"] and pub["reads"]["same_release"], pub["reads"]
    assert pub["reads"]["listing_same_release"]
    assert pub["decision"]["refused"] and pub["result"]["store_published_rows"] == 0
    assert {"cir.compile", "gate.certify", "listing.seo"} <= set(e["durable"])
    report = json.loads(next((ROOT / "research/final_build/w4/evidence_CLOSE6")
                             .glob("final_proof_*.json")).read_text())
    chained = [r for r in report["rows"]
               if r["errors"] and not [x for x in r["errors"] if x.startswith(STAGE_ERRORS)]
               and r["uid"] in ("F-477", "F-048")]
    assert {r["uid"] for r in chained} == {"F-477", "F-048"}, \
        [(r["uid"], r["errors"][:4]) for r in report["rows"] if r["uid"] in ("F-477", "F-048")]
    assert all(r["verdict"] == "BLOCKED" for r in report["rows"]), "nothing self-certifies"


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
