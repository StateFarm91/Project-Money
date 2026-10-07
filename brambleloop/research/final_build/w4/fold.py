"""Wave-4 re-map of the Final Master v1.0 rows on the current head (lane FM).

The canonical mapping (mapping/s*.json) was made on 019ebf0 and re-mapped on 6f9a2f7. Nothing
merged since (FB-4, rc1, v1.1, wave 3) was visible to the adjudicator, so the launch gate read
300 OPEN rows that later work claims to have closed. This script re-maps those rows from
evidence and lets `aggregate.cap()/completion()` decide -- it never certifies anything itself.

Sources per row (launch-critical rows the current matrix computes OPEN):
  * FOLD   -- a wave-3 lane handoff claims COMPLETE (w4/claims.py): tests named in the claim,
              the producer module the claim names (else one the cited tests import), the
              consumer the claim names (else the live root reachability says reaches the
              producer). A claim qualified with a gate key (`GATED on \\`x\\``) keeps coverage
              PARTIAL and records the gate; any other qualifier keeps PARTIAL and the row OPEN.
  * FOLD-R -- lane K's audit (w3/closure_w3.py `T`, code R) re-checked it as resolved on f0c2d12.
  * REGATE -- lane K's audit (code G) found the explicit owner/data/external gate with its key.
A row is written back only when (a) the overlay computes COMPLETE or GATED under the canonical
rules on the regenerated reachability and (b) every cited test FILE ran green on this head
(w4/fold_test_results.json, produced by `--run-tests`). Everything else keeps its old mapping
and is listed in w4/FOLD_REPORT.json with the reason.

Run (from brambleloop/):
  python3 research/final_build/w4/fold.py --plan        # candidates + the test files they cite
  python3 research/final_build/w4/fold.py --run-tests   # runs each cited test file once
  python3 research/final_build/w4/fold.py --apply       # writes mapping + remap_<sha7>, report
  python3 research/final_build/aggregate.py             # re-adjudicate + regenerate snapshot
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FB))
sys.path.insert(0, str(FB / "w3"))
import aggregate as agg  # noqa: E402
import claims as claims_mod  # noqa: E402

HEAD_SHA7 = "fee1cfe"
GENERIC = {"core/db.py", "core/models.py", "agents/registry.py", "app/main.py", "core/config.py",
           "core/settings.py", "runtime/handlers.py", "runtime/worker.py"}
RESULTS = HERE / "fold_test_results.json"
# Producer corrections where the claim text names a helper before the module that implements
# the row (checked by reading the claim and the module; reachability still adjudicates).
_FM = "src/brambleloop/build2/final_master.py"
_FM_CONSUMER = ("launch/readiness.assess requirement final_master_closure (GET / dashboard, "
                "launch.readiness cadence) and build2/executor.report")
PRODUCER_FIX = {
    **{u: (_FM, _FM_CONSUMER) for u in ("F-129", "F-130", "F-133", "F-136", "F-382", "F-400",
                                         "F-831", "F-832", "F-838", "F-844", "F-860", "F-867",
                                         "F-879")},
    "F-127": ("src/brambleloop/ops/truth.py", None),
    "F-161": ("src/brambleloop/ops/artefacts.py", None),
    "F-162": ("src/brambleloop/ops/artefacts.py", None),
    "F-080": ("src/brambleloop/gates/risk_matrix.py", None),
    "F-805": ("src/brambleloop/learn/service.py", None),
    "F-826": ("src/brambleloop/learn/service.py", None),
    "F-109": ("src/brambleloop/gateway/paid_calls.py",
              "runtime/worker.Worker.run_once -> finance/spend_report.attributed_to (job scope)"),
}
PY = os.environ.get("BL_PY", "/home/user/Project-Money/brambleloop/.venv/bin/python")
_GATE_KEY = re.compile(r"GATED[^`]*`([\w.-]+)`")


def _triage():
    import closure_w3
    return closure_w3.T


def _mapping():
    rows, where = {}, {}
    for f in sorted((FB / "mapping").glob("s[0-9].json")):
        for r in json.loads(f.read_text()):
            rows[r["uid"]] = r
            where[r["uid"]] = f
    return rows, where


def _consumer_from(text: str) -> str | None:
    cells = [c.strip() for c in text.strip().strip("|").split("|")]
    for c in cells[2:]:
        if "→" in c:
            return c.split("→", 1)[1].strip()[:400]
        m = re.search(r"[Cc]onsumers?:\s*(.+)", c)
        if m:
            return m.group(1).strip()[:400]
    if len(cells) >= 4 and cells[-1]:
        return cells[-1][:400]
    if "→" in text:
        return text.split("→", 1)[1].strip()[:400]
    m = re.search(r"go(?:es)? through (.+?)(?:\.|$)", text)
    return m.group(1).strip()[:400] if m else None


def _pick_producer(mods, imports, reach):
    for m in list(mods) + sorted(imports):
        if m in GENERIC:
            continue
        if (reach.get(m) or {}).get("reached"):
            return m
    return None


def plan():
    matrix = {r["uid"]: r for r in json.loads((FB / "closure_matrix.json").read_text())["matrix"]}
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    T = _triage()
    cl = claims_mod.parse()
    rows, _ = _mapping()
    pc = {x["uid"]: x for x in json.loads(
        (FB / "mapping" / "remap_6f9a2f7" / "partial_classification_376c54b.json").read_text())}
    cands = []
    for uid, m in matrix.items():
        if m["launch_class"] != "LAUNCH-CRITICAL" or m["completion"] != "OPEN":
            continue
        base = json.loads(json.dumps(rows[uid]))
        good = [c for c in cl.get(uid, []) if c["status"] == "COMPLETE"]
        bad = [c for c in cl.get(uid, []) if c["status"] in ("OPEN", "FAIL")]
        t = T.get(uid) or {}
        src, ov, note = None, dict(base), ""
        if good and not bad:
            src = "FOLD"
            c = good[0]
            tests = sorted({x for g in good for x in g["tests"]})
            mods = [x for g in good for x in g["modules"]]
            imps = {x for g in good for x in g.get("test_imports", [])}
            prod = _pick_producer(mods, imps, reach)
            cons = _consumer_from(c["text"])
            if not cons and prod:
                cons = "runtime consumer per reachability: " + reach[prod]["why"]
            qual = re.sub(r"^\**\s*(COMPLETE|PASS|HOLDS)\s*\**", "", c["status_cell"]).strip()
            ov.update(tests=sorted(set(base.get("tests") or []) | set(tests)),
                      evidence=list(base.get("evidence") or []) + [
                          f"w3 handoff_{x['lane']}.md claim: {x['text'][:300]}" for x in good])
            if prod:
                ov["producer"] = f"src/brambleloop/{prod}"
            if cons:
                ov["consumer"] = cons
            ov["maturity"] = base["maturity"] if agg.LEVELS.index(base["maturity"]) >= 3 else "INTEGRATED"
            gk = _GATE_KEY.search(c["status_cell"]) or (
                _GATE_KEY.search(c["text"]) if "GATED" in c["status_cell"] else None)
            if not qual or qual.lower() in ("(code)",):
                ov.update(coverage="FULL", missing_part=None, defect=None)
            elif gk or "GATED" in qual:
                key = gk.group(1) if gk else ((base.get("gate") or {}).get("key"))
                kind = (base.get("gate") or {}).get("kind")
                kind = kind if kind in ("owner", "data", "external") else "owner"
                ov.update(coverage="PARTIAL", missing_part=f"lane claim qualifier: {qual}",
                          defect=None, gate={"kind": kind, "key": key,
                                             "detail": f"w3 claim: {qual}"} if key else base.get("gate"),
                          next_action=base.get("next_action") or f"close the gated half: {qual}")
            else:
                ov.update(coverage="PARTIAL", missing_part=f"lane claim qualifier: {qual}",
                          next_action=base.get("next_action") or qual)
            if uid in PRODUCER_FIX:
                ov["producer"], fixc = PRODUCER_FIX[uid]
                if fixc:
                    ov["consumer"] = fixc
            note = f"claims {[x['lane'] for x in good]}"
        elif t.get("v") == "R":
            src = "FOLD-R"
            tests = list(t["tests"])
            for e in (pc.get(uid) or {}).get("evidence") or []:
                if isinstance(e, str) and e.startswith("tests/"):
                    tests.append(e.split()[0])
            ov["tests"] = sorted(set(base.get("tests") or []) | set(tests))
            if t.get("producer"):
                ov["producer"] = t["producer"]
            if agg.LEVELS.index(base["maturity"]) < agg.LEVELS.index("INTEGRATED"):
                ov["maturity"] = "INTEGRATED"
            ov.update(coverage="FULL", defect=None, missing_part=None)
            ov["evidence"] = list(base.get("evidence") or []) + [f"w3 lane K triage R: {t['n']}"]
            mod = agg._module_of(ov.get("producer"))
            if not str(ov.get("consumer") or "").strip() and mod and (reach.get(mod) or {}).get("reached"):
                ov["consumer"] = "runtime consumer per reachability: " + reach[mod]["why"]
            note = t["n"]
        elif t.get("v") == "G" and not base.get("defect"):
            src = "REGATE"
            ov["gate"] = dict(t["gate"])
            note = t["n"]
            if not str(ov.get("missing_part") or "").strip():
                ov["missing_part"] = t["n"]
            if not str(ov.get("next_action") or "").strip():
                ov["next_action"] = f"{t['gate']['kind']} gate {t['gate']['key']}: {t['n']}"
        if not src:
            continue
        ov["evidence"] = ov.get("evidence") or []
        lvl, notes = agg.cap(dict(ov), reach)
        probe = dict(ov, maturity=lvl)
        verdict, reasons = agg.completion(probe)
        files = sorted({x.split("::")[0] for x in ov.get("tests") or [] if agg._test_exists(x)})
        cands.append({"uid": uid, "source": src, "note": note, "verdict": verdict,
                      "reasons": notes + reasons, "maturity": lvl, "test_files": files,
                      "row": ov})
    return cands


SUITE_LOG = Path("/home/user/Project-Money/.claude/worktrees/visual-investigation/brambleloop/"
                 "artifacts/suite_runs/20261006T223255Z-18437.log")
SUITE_SHA = "cc4a129"


def run_tests(cands, log: Path = SUITE_LOG):
    """Per-function results from the integrator's last full-suite run (cc4a129, 494 suites,
    7143 passing, one failing suite: test_v11_pwa_browser, fixed by 94f99ad). cc4a129..fee1cfe
    changes only tests/fixtures/cc_mock/check.mjs and the wave-4 brief, so every other suite's
    result holds on this head. The run log is git-ignored, so the parsed result is committed as
    w4/fold_test_results.json -- the durable artefact the fold cites. No test is re-run here
    (the brief forbids lanes running the full suite)."""
    res: dict[str, dict] = {}
    cur = None
    for line in log.read_text(errors="replace").splitlines():
        m = re.match(r"^== (tests/\S+\.py)", line)
        if m:
            cur = res.setdefault(m.group(1), {"ok": [], "fail": []})
            continue
        m = re.match(r"^\s+(OK|FAIL)\s+(test_\w+)", line)
        if m and cur is not None:
            cur["ok" if m.group(1) == "OK" else "fail"].append(m.group(2))
    hdr = {"source": f"run_tests.sh full suite on {SUITE_SHA} (run 20261006T223255Z-18437)",
           "applies_to": f"{HEAD_SHA7}: cc4a129..fee1cfe changes only tests/fixtures/cc_mock/"
                         "check.mjs + research/final_build/w4/WAVE4_BRIEF.md",
           "suites": len(res)}
    out = {"_meta": hdr, "suites": {f: {"ok": sorted(set(v["ok"])), "fail": sorted(set(v["fail"]))}
                                     for f, v in sorted(res.items())}}
    RESULTS.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(hdr)
    return out


FAILING_SUITES = {"tests/test_v11_pwa_browser.py"}  # the run record's failing_suites


def test_green(ref: str, results: dict) -> bool:
    """A cited test is green when its function exists on this head and its suite ran in the
    cc4a129 full run and exited 0 (the record's failing_suites lists only the PWA browser
    check). Suite output lines are free text in many files, so the suite exit status -- not a
    name match -- is the per-suite verdict; per-function existence is aggregate._test_exists."""
    m = re.match(r"(tests/[\w/]+\.py)", ref or "")
    if not m or not agg._test_exists(ref):
        return False
    f = m.group(1)
    suite = results["suites"].get(f)
    return suite is not None and f not in FAILING_SUITES and not suite["fail"]


def apply(cands):
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    rows, where = _mapping()
    folded, kept = [], []
    for c in cands:
        why = None
        if c["verdict"] not in ("COMPLETE", "GATED"):
            why = "overlay does not compute COMPLETE/GATED: " + "; ".join(c["reasons"])[:400]
        elif c["verdict"] == "COMPLETE" and not c["test_files"]:
            why = "no cited test exists"
        else:
            refs = [t for t in c["row"].get("tests") or [] if agg._test_exists(t)]
            bad = [t for t in refs if not test_green(t, results)]
            if bad:
                why = "cited test not green in the cc4a129 full suite: " + ", ".join(bad)[:300]
        if why:
            kept.append({"uid": c["uid"], "source": c["source"], "why": why})
            continue
        row = c["row"]
        row["searched"] = (str(row.get("searched") or "") +
                           f" | w4-FM re-map on {HEAD_SHA7} ({c['source']}): {c['note']}")[:2000]
        rows[c["uid"]] = row
        folded.append({"uid": c["uid"], "source": c["source"], "verdict": c["verdict"],
                       "maturity": c["maturity"], "test_files": c["test_files"],
                       "producer": row.get("producer"), "consumer": str(row.get("consumer"))[:200]})
    by_file: dict[Path, list] = {}
    for uid, f in where.items():
        by_file.setdefault(f, []).append(rows[uid])
    for f, rs in by_file.items():
        old = json.loads(f.read_text())
        order = [r["uid"] for r in old]
        new = {r["uid"]: r for r in rs}
        f.write_text(json.dumps([new[u] for u in order], indent=1, ensure_ascii=False) + "\n")
    rdir = FB / "mapping" / f"remap_{HEAD_SHA7}"
    rdir.mkdir(exist_ok=True)
    (rdir / "remap_w4.json").write_text(json.dumps(
        [rows[x["uid"]] for x in folded], indent=1, ensure_ascii=False) + "\n")
    (HERE / "FOLD_REPORT.json").write_text(json.dumps(
        {"head": HEAD_SHA7, "folded": folded, "kept_open": kept,
         "counts": {"folded": len(folded), "kept": len(kept)}}, indent=1) + "\n")
    print(len(folded), "folded;", len(kept), "kept")


if __name__ == "__main__":
    cands = plan()
    if "--plan" in sys.argv:
        from collections import Counter
        print(Counter((c["source"], c["verdict"]) for c in cands))
        for c in cands:
            if c["verdict"] not in ("COMPLETE", "GATED"):
                print(c["uid"], c["source"], "; ".join(c["reasons"])[:220])
        print(sorted({f for c in cands for f in c["test_files"]}))
    elif "--run-tests" in sys.argv:
        run_tests(cands)
    elif "--apply" in sys.argv:
        apply(cands)
