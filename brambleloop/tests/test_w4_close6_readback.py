"""W4-CLOSE6: F-144 Production Readback Gate.

  F-144  "Major operational features require deployed readback/verification after local
          tests."

W4-SMOKE built the gate: `ops/readback.py` has a per-feature manifest of endpoint, field and
predicate, `ops/deploy.sh` exits 5 when a feature does not read back, and
`ops/smoke.py` / GET /api/verify/smoke covers it. Two gaps remained:

1. The manifest missed features that then failed in production. GET /api/departments
   answered 500 on b931d17 while every listed feature read PASS. The departments, swarm
   runtime, funding packet, off-site archive, continuity proof and Etsy credential features
   are now read back.
2. A failed readback stopped the deploy script but did not stop anything from being counted
   done. The mapping's "not refused 'done' until its deployed readback passes" was unmet. Now
   `deploy.sh` writes the readback as evidence. `completion_board_final.apply_readback` keeps
   a Final Master row named by a feature out of verified_complete unless the readback of the
   DEPLOYED commit passed for every feature naming it. With no readback on file the row stays
   out too (UNKNOWN is never a pass).

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_readback.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "ops"))
sys.path.insert(0, str(ROOT / "tests"))

import readback  # noqa: E402

SHA = "a" * 40


def _board():
    path = ROOT / "research/final_build/w4/completion_board_final.py"
    spec = importlib.util.spec_from_file_location("cbf_close6", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_manifest_reads_back_the_features_that_failed_unseen():
    by = readback.rows_by_feature()
    assert len(by) >= 18, sorted(by)
    eps = {e for _f, _r, e, *_ in readback.MANIFEST}
    for ep in ("/api/departments", "/api/swarm/runtime", "/api/funding/packets",
               "/api/offsite", "/api/continuity", "/api/etsy"):
        assert ep in eps, ep
    import test_w4_smoke as smoke_t

    out = readback.run(SHA, url="https://prod.invalid",
                       fetch=smoke_t._fetcher(smoke_t._prod_bodies(
                           sha=SHA, **{"/api/departments": (500, None)})),
                       token=smoke_t.OPS_TOKEN)
    assert out["verdict"] == "FAIL" and out["not_done"] == ["department health served"], out
    assert out["read_at"].endswith("Z")


def _rows(*ids):
    return [{"source": "final_master", "id": i, "cls": "verified_complete", "root": None}
            for i in ids]


def _write(ev: Path, sha: str, features: dict):
    (ev / f"prod_readback_{sha[:12]}_20261020T1200Z.json").write_text(json.dumps(
        {"sha": sha, "verdict": "PASS" if all(v == "PASS" for v in features.values())
         else "FAIL", "features": [{"feature": f, "verdict": v} for f, v in features.items()],
         "not_done": [f for f, v in features.items() if v != "PASS"]}))


def test_a_row_is_not_complete_unless_its_deployed_readback_passed():
    cbf = _board()
    ev = Path(tempfile.mkdtemp())
    cbf.EV = ev
    prod = {"commit": SHA}
    all_pass = {f: "PASS" for f in readback.rows_by_feature()}
    # no readback of the deployed commit on file: UNKNOWN, never a pass
    rows = _rows("F-487", "F-878", "F-999")
    out = cbf.apply_readback(rows, prod)
    assert out["status"] == "UNKNOWN"
    assert [r["cls"] for r in rows] == ["implemented_unverified", "implemented_unverified",
                                       "verified_complete"], rows
    assert rows[0]["root"] == "deployed_readback_missing"
    # a readback of ANOTHER commit does not count
    _write(ev, "b" * 40, all_pass)
    rows = _rows("F-487")
    cbf.apply_readback(rows, prod)
    assert rows[0]["cls"] == "implemented_unverified"
    # the deployed commit read back with departments failing: only its rows are held
    _write(ev, SHA, {**all_pass, "department health served": "FAIL"})
    rows = _rows("F-487", "F-878")
    out = cbf.apply_readback(rows, prod)
    assert out["status"] == "FAIL" and out["not_done"] == ["department health served"]
    assert rows[0]["cls"] == "implemented_unverified"
    assert rows[0]["root"] == "deployed_readback_failed"
    assert "department health served" in rows[0]["missing_evidence"]
    assert rows[1]["cls"] == "verified_complete", "a passing feature keeps its row"
    # downgrade only, never upgrade
    rows = [{"source": "final_master", "id": "F-487", "cls": "blocked_owner", "root": "x"}]
    _write(ev, SHA, all_pass)
    cbf.apply_readback(rows, prod)
    assert rows[0]["cls"] == "blocked_owner"


def test_deploy_writes_the_readback_where_the_board_reads_it():
    sh = (REPO / "ops/deploy.sh").read_text()
    assert '--json "$rb_json"' in sh and "evidence_BOARD/prod_readback_" in sh
    assert 'mkdir -p "$(dirname "$rb_json")"' in sh
    assert Path(readback.evidence_path(SHA, "X")).parent == \
        (ROOT / "research/final_build/w4/evidence_BOARD").resolve()
    board = (ROOT / "research/final_build/w4/completion_board_final.py").read_text()
    assert "readback = apply_readback(fm, prod)" in board


def test_the_committed_board_applies_the_deployed_readback():
    board = json.loads((ROOT / "research/final_build/w4/COMPLETION_BOARD_FINAL.json")
                       .read_text())
    def find(x):
        if isinstance(x, dict):
            if "deployed_readback" in x:
                return x["deployed_readback"]
            for v in x.values():
                r = find(v)
                if r is not None:
                    return r
        return None

    rb = find(board)
    assert rb and rb["file"] and rb["status"] in ("PASS", "FAIL", "UNKNOWN"), rb
    held = [x for x in board["rows"]["final_master"]
            if (x.get("readback") or {}).get("not_passing") and x["cls"] == "verified_complete"]
    assert held == [], held


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
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
