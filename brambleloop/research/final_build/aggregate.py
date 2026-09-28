"""Aggregate worker mapping slices into the Final Build closure matrix (integrator step).

Workers propose; this script adjudicates mechanically what can be checked from evidence:
  * every registry uid appears exactly once, every row has the schema keys;
  * a claimed maturity is capped by what the cited evidence can support:
      - INTEGRATED+ needs a producer module that module_reachability.json marks reached;
      - DEPLOYED+ additionally needs that module in the production tree fcb982d;
      - TESTED+ needs at least one named test that exists in tests/ (function present);
      - COMMERCIALLY-EVIDENCED is refused outright (no customer/revenue evidence exists);
  * every downgrade is recorded in the row's `adjudication` with the reason.
Human/integrator adjudications that cannot be computed live in `overrides.json`
({uid: {field: value, "reason": ...}}) and are applied last, with the reason kept.

Run: python3 research/final_build/aggregate.py
"""
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LEVELS = ["MISSING", "IMPLEMENTED", "TESTED", "INTEGRATED", "DEPLOYED", "EXERCISED",
          "PRODUCTION-OBSERVED", "COMMERCIALLY-EVIDENCED"]
KEYS = ["uid", "launch_class", "launch_class_reason", "maturity", "coverage", "missing_part",
        "producer", "durable_state", "consumer", "protected_effect", "tests", "evidence",
        "build2_rows", "gate", "defect", "next_action", "confidence", "searched"]
CLASSES = {"LAUNCH-CRITICAL", "MATURE", "NA"}


def _module_of(ref):
    if not ref:
        return None
    m = re.search(r"(?:src/brambleloop/)?([\w/]+\.py)", ref)
    if not m:
        return None
    p = m.group(1)
    return p[len("src/brambleloop/"):] if p.startswith("src/brambleloop/") else p


_TEST_CACHE = {}


def _test_exists(ref):
    m = re.match(r"(tests/[\w/]+\.py)(?:::(\w+))?", ref or "")
    if not m:
        return False
    path = ROOT / m.group(1)
    if not path.exists():
        return False
    if not m.group(2):
        return True
    src = _TEST_CACHE.setdefault(path, path.read_text(errors="replace"))
    return re.search(rf"def {re.escape(m.group(2))}\b", src) is not None


def cap(row, reach):
    notes = []
    lvl = row["maturity"]
    if lvl not in LEVELS:
        notes.append(f"unknown maturity {lvl!r} -> MISSING")
        lvl = "MISSING"
    i = LEVELS.index(lvl)
    if i >= LEVELS.index("COMMERCIALLY-EVIDENCED"):
        notes.append("no customer/revenue evidence exists -> capped at PRODUCTION-OBSERVED")
        i = LEVELS.index("PRODUCTION-OBSERVED")
    if i >= LEVELS.index("TESTED"):
        real = [t for t in row.get("tests") or [] if _test_exists(t)]
        if not real:
            notes.append("no cited test exists in tests/ -> capped at IMPLEMENTED")
            i = LEVELS.index("IMPLEMENTED")
    if i >= LEVELS.index("INTEGRATED"):
        mod = _module_of(row.get("producer"))
        info = reach.get(mod) if mod else None
        if not info or not info["reached"]:
            notes.append(f"producer module {mod!r} not reached from a live root -> capped at TESTED")
            i = LEVELS.index("TESTED")
        elif i >= LEVELS.index("DEPLOYED") and not info["in_production_fcb982d"]:
            notes.append(f"producer module {mod!r} absent from production fcb982d -> capped at INTEGRATED")
            i = LEVELS.index("INTEGRATED")
    return LEVELS[i], notes


def main():
    reg = json.loads((HERE / "master_registry.json").read_text())
    reqs = {r["uid"]: r for r in reg["requirements"]}
    reach = json.loads((HERE / "module_reachability.json").read_text())["modules"]
    overrides_p = HERE / "overrides.json"
    overrides = json.loads(overrides_p.read_text()) if overrides_p.exists() else {}
    rows, problems = {}, []
    for f in sorted((HERE / "mapping").glob("s[0-9].json")):
        for row in json.loads(f.read_text()):
            uid = row.get("uid")
            if uid not in reqs:
                problems.append(f"{f.name}: unknown uid {uid}")
                continue
            if uid in rows:
                problems.append(f"{f.name}: duplicate uid {uid}")
            missing = [k for k in KEYS if k not in row]
            if missing:
                problems.append(f"{uid}: missing keys {missing}")
            row.setdefault("tests", [])
            row["slice"] = f.stem
            rows[uid] = row
    absent = [u for u in reqs if u not in rows]
    matrix = []
    for uid, req in reqs.items():
        row = rows.get(uid)
        if row is None:
            continue
        claimed = row["maturity"]
        final, notes = cap(row, reach)
        row["maturity_claimed"], row["maturity"] = claimed, final
        if row.get("launch_class") not in CLASSES:
            notes.append(f"launch_class {row.get('launch_class')!r} invalid -> LAUNCH-CRITICAL (fail safe)")
            row["launch_class"] = "LAUNCH-CRITICAL"
        if uid in overrides:
            ov = dict(overrides[uid])
            reason = ov.pop("reason", "integrator override")
            for k, v in ov.items():
                notes.append(f"override {k}: {row.get(k)!r} -> {v!r} ({reason})")
                row[k] = v
        row["adjudication"] = notes
        row.update({"id": req["id"], "title": req["title"], "version": req["version"],
                    "master_priority": req.get("master_priority")})
        matrix.append(row)
    lc = [r for r in matrix if r["launch_class"] == "LAUNCH-CRITICAL"]
    summary = {
        "rows": len(matrix), "unmapped": absent, "problems": problems,
        "maturity": dict(Counter(r["maturity"] for r in matrix)),
        "maturity_claimed": dict(Counter(r["maturity_claimed"] for r in matrix)),
        "launch_class": dict(Counter(r["launch_class"] for r in matrix)),
        "launch_critical_maturity": dict(Counter(r["maturity"] for r in lc)),
        "gate_kind": dict(Counter((r.get("gate") or {}).get("kind", "none") for r in matrix)),
        "launch_critical_gate_kind": dict(Counter((r.get("gate") or {}).get("kind", "none") for r in lc)),
        "coverage": dict(Counter(r.get("coverage") for r in matrix)),
        "downgraded": sum(1 for r in matrix if r["maturity"] != r["maturity_claimed"]),
        "defects": sum(1 for r in matrix if r.get("defect")),
    }
    out = {"basis": {"engineering": "019ebf0 (+ Final Build registry commits)",
                     "production": "fcb982d", "registry": "master_registry.json"},
           "levels": LEVELS, "summary": summary, "matrix": matrix}
    (HERE / "closure_matrix.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1)[:4000])


if __name__ == "__main__":
    main()
