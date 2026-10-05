"""Aggregate worker mapping slices into the Final Build closure matrix (integrator step).

Workers propose; this script adjudicates mechanically what can be checked from evidence:
  * every registry uid appears exactly once, every row has the schema keys;
  * a claimed maturity is capped by what the cited evidence can support:
      - INTEGRATED+ needs a producer module that module_reachability.json marks reached;
      - DEPLOYED+ additionally needs that module in the production tree fcb982d;
      - TESTED+ needs at least one named test that exists in tests/ (function present);
      - INTEGRATED+ needs every database table its `durable_state` cites to have a writer
        outside tests/ in a module module_reachability.json marks reached (F-836): a fact
        only a fixture writes is not runtime state;
      - INTEGRATED+ is refused when every cited evidence item is flagged proxy (F-837); an
        item is proxy when it is {"ref": ..., "proxy": true} or a string starting "[proxy]";
      - COMMERCIALLY-EVIDENCED is refused outright (no customer/revenue evidence exists);
  * every downgrade is recorded in the row's `adjudication` with the reason.
It also derives, per row, `protected_action_applicability` (what build2/final_proof.py needs
to decide whether an execution-gate receipt is required), `mapped_on` (the SHA the row's
mapping was made against), and a completion verdict (F-178/F-843):
  * LAUNCH-CRITICAL rows: COMPLETE iff maturity >= INTEGRATED, coverage FULL and no recorded
    defect; GATED iff not complete, no recorded defect, and the remaining step carries a
    recorded owner/data/external gate with a key; otherwise OPEN (with the reasons);
  * MATURE rows: POST-LAUNCH; NA rows: NOT-APPLICABLE.
The summary carries the counts, including `launch_critical_open`. It is computed, not pinned
to zero: release requires it to reach 0 (or every open row to be reclassified with a reason).
Human/integrator adjudications that cannot be computed live in `overrides.json`
({uid: {field: value, "reason": ...}}) and are applied last, with the reason kept.

Run: python3 research/final_build/aggregate.py
"""
import ast
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
SRC = ROOT / "src" / "brambleloop"
# The SHAs the mapping rows were made against (MAPPING_BRIEF.md: 019ebf0; the re-map wave under
# mapping/remap_<sha7>/ against that SHA). Full SHAs so the basis names a commit, not a prefix.
MAPPING_BASE = "019ebf0eeb36789aa62ddf7be9bfb6ba3995853a"
REMAP_SHAS = {"6f9a2f7": "6f9a2f7a1405f5c9638a78552934445bc590c63f"}
PRODUCTION = "fcb982d57e291c88d9f78eaa091e90904b6c2cc9"
# Completion target per launch class (F-178). Only launch-critical rows have a launch target.
TARGET = {"LAUNCH-CRITICAL": "INTEGRATED", "MATURE": None, "NA": None}
# Words in a row's protected effect / producer / title that name a protected (externally
# visible, spending, customer-facing or authority-bearing) action. A row matching none, with no
# protected_effect, is "unprotected"; anything else is "protected" (fail safe: final_proof then
# requires an execution-gate receipt).
PROTECTED_WORDS = re.compile(
    r"\b(?:publish|activat|etsy|listing\b|spend|budget|refund|payment|pric|send|email|"
    r"customer|order|delet|deploy|grant|authori[sz]|owner|ads?\b|campaign|credential)",
    re.I)


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


def _model_tables():
    """{table: {class names}} and {class name: {tables}} from every ORM model under src/."""
    tables, classes = {}, {}
    for path in SRC.rglob("*.py"):
        text = path.read_text(errors="replace")
        if "__tablename__" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.ClassDef):
                continue
            for st in node.body:
                if (isinstance(st, ast.Assign) and any(getattr(t, "id", "") == "__tablename__"
                                                       for t in st.targets)
                        and isinstance(st.value, ast.Constant)):
                    tables.setdefault(st.value.value, set()).add(node.name)
                    classes.setdefault(node.name, set()).add(st.value.value)
    return tables, classes


_INDEX = {}


def writer_index():
    """{table: sorted modules (relative to src/brambleloop) that write it, outside tests/}.

    A writer constructs the mapped class (`Cls(...)`), names it in `insert(Cls)` /
    `update(Cls)` / `delete(Cls)`, or issues SQL text `INSERT INTO t` / `UPDATE t SET`. A class
    name defined for two tables counts as a writer of both (over-approximates; a writer that
    is only ever reached from tests is still caught by reachability).
    """
    if _INDEX:
        return _INDEX
    tables, classes = _model_tables()
    writers = {t: set() for t in tables}
    sql = re.compile(r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE)\s+[\"`]?(\w+)", re.I)
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        text = path.read_text(errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else (
                    fn.attr if isinstance(fn, ast.Attribute) else None)
                if name in classes:
                    for t in classes[name]:
                        writers[t].add(rel)
                elif name in ("insert", "update", "delete") and node.args:
                    a = node.args[0]
                    cls = a.id if isinstance(a, ast.Name) else (
                        a.attr if isinstance(a, ast.Attribute) else None)
                    for t in classes.get(cls, ()):
                        writers[t].add(rel)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in sql.finditer(node.value):
                    if m.group(1) in writers:
                        writers[m.group(1)].add(rel)
    _INDEX.update(tables=tables, classes=classes,
                  writers={t: sorted(w) for t, w in writers.items()})
    return _INDEX


def cited_tables(durable_state):
    """Database tables a row's `durable_state` names (table names, or unambiguous class names)."""
    if not durable_state:
        return []
    idx = writer_index()
    text = str(durable_state)
    found = []
    for t in idx["tables"]:
        if re.search(rf"(?<![\w/.]){re.escape(t)}(?![\w/])", text):
            found.append(t)
    for cls, ts in idx["classes"].items():
        if len(ts) == 1 and re.search(rf"\b{re.escape(cls)}\b", text):
            found.extend(ts)
    return sorted(set(found))


def unwritten_tables(row, reach):
    """Cited tables with no non-test writer in a reached module: [(table, writers)]."""
    idx = writer_index()
    out = []
    for t in cited_tables(row.get("durable_state")):
        live = [m for m in idx["writers"].get(t, []) if (reach.get(m) or {}).get("reached")]
        if not live:
            out.append((t, idx["writers"].get(t, [])))
    return out


def _is_proxy(item):
    if isinstance(item, dict):
        return item.get("proxy") is True
    return isinstance(item, str) and item.strip().lower().startswith("[proxy]")


def all_evidence_proxy(row):
    ev = row.get("evidence") or []
    return bool(ev) and all(_is_proxy(e) for e in ev)


def protected_action_applicability(row):
    if row.get("protected_effect"):
        return "protected", "row names a protected_effect"
    text = " ".join(str(row.get(k) or "") for k in ("title", "producer", "consumer"))
    m = PROTECTED_WORDS.search(text)
    if m:
        return "protected", f"title/producer/consumer names {m.group(0)!r}"
    return "unprotected", "no protected_effect and no protected action named"


def completion(row):
    """(verdict, reasons) for one adjudicated row (F-178)."""
    cls = row.get("launch_class")
    if cls == "NA":
        return "NOT-APPLICABLE", []
    if cls != "LAUNCH-CRITICAL":
        return "POST-LAUNCH", []
    reasons = []
    if LEVELS.index(row["maturity"]) < LEVELS.index(TARGET[cls]):
        reasons.append(f"maturity {row['maturity']} below target {TARGET[cls]}")
    if row.get("coverage") != "FULL":
        reasons.append("coverage PARTIAL: " + str(row.get("missing_part") or "")[:160])
    if row.get("defect"):
        reasons.append("defect recorded: " + str(row["defect"])[:160])
    if not reasons:
        return "COMPLETE", []
    gate = row.get("gate") or {}
    if (not row.get("defect") and gate.get("kind") in ("owner", "data", "external")
            and gate.get("key")):
        return "GATED", [f"{gate['kind']} gate {gate['key']!r}"] + reasons
    return "OPEN", reasons


SCOPE_OF = {"LAUNCH-CRITICAL": "launch-critical", "MATURE": "post-launch", "NA": "rejected"}


def launch_scope(matrix, remapped_classes, overrides, basis):
    """F-847 / D-FB-5: every requirement classified launch-critical / post-launch / rejected.

    Generated from the adjudicated matrix, never edited by hand. A row counts as a
    *reclassification* out of launch scope when it is post-launch although (a) its source
    priority says P0 / launch-critical, (b) the launch-critical re-map wave moved it out
    (remap rows are only drawn from launch-critical rows), or (c) an integrator override set
    its class; each such row must carry its reason (tests/test_final_closure_matrix.py).
    """
    entries = []
    for r in matrix:
        scope = SCOPE_OF[r["launch_class"]]
        why_moved = []
        if scope != "launch-critical":
            if "P0" in str(r.get("master_priority") or ""):
                why_moved.append(f"source priority {r['master_priority']}")
            if remapped_classes.get(r["uid"]) not in (None, "LAUNCH-CRITICAL"):
                why_moved.append("moved out by the launch-critical re-map wave")
            if "launch_class" in (overrides.get(r["uid"]) or {}):
                why_moved.append("integrator override")
        entries.append({
            "uid": r["uid"], "id": r["id"], "title": r["title"][:120], "scope": scope,
            "reason": r.get("launch_class_reason") or "",
            "reclassified": bool(why_moved), "reclassified_against": why_moved,
            "completion": r["completion"]})
    return {
        "rule": "D-FB-5 / F-847: launch-critical ships before launch; post-launch is scheduled "
                "after first sale; rejected is not applicable to Brambleloop. New ideas enter "
                "as registry rows or overrides.json entries and are classified here.",
        "generated_by": "research/final_build/aggregate.py (do not edit by hand)",
        "basis": basis,
        "counts": dict(Counter(e["scope"] for e in entries)),
        "reclassified_out_of_launch": sorted(e["uid"] for e in entries if e["reclassified"]),
        "entries": entries}


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
    if i >= LEVELS.index("EXERCISED"):
        # EXERCISED means the real runtime ran it and a durable production artefact says so.
        # BUILD_STATE prose describing production is a secondary record, not the artefact.
        ev = " ".join(map(str, row.get("evidence") or []))
        if not re.search(r"research/b2_resume/evidence/prod_|prod_api_verify_\d", ev):
            notes.append("exercise evidence is not a committed production artefact "
                         "(status prose is secondary) -> capped at DEPLOYED")
            i = LEVELS.index("DEPLOYED")
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
    if i >= LEVELS.index("INTEGRATED"):
        bad = unwritten_tables(row, reach)
        if bad:
            notes.append("durable_state table(s) with no non-test writer in a reached module: "
                         + "; ".join(f"{t} (writers: {w or 'none'})" for t, w in bad)
                         + " -> capped at TESTED (F-836)")
            i = LEVELS.index("TESTED")
    if i >= LEVELS.index("INTEGRATED") and all_evidence_proxy(row):
        notes.append("every cited evidence item is flagged proxy -> capped at TESTED (F-837)")
        i = LEVELS.index("TESTED")
    return LEVELS[i], notes


def main():
    reg = json.loads((HERE / "master_registry.json").read_text())
    reqs = {r["uid"]: r for r in reg["requirements"]}
    reach = json.loads((HERE / "module_reachability.json").read_text())["modules"]
    overrides_p = HERE / "overrides.json"
    overrides = json.loads(overrides_p.read_text()) if overrides_p.exists() else {}
    remapped, remapped_classes = {}, {}
    for sha7, full in REMAP_SHAS.items():
        for f in sorted((HERE / "mapping" / f"remap_{sha7}").glob("*.json")):
            for r in json.loads(f.read_text()):
                remapped[r.get("uid")] = full
                remapped_classes[r.get("uid")] = r.get("launch_class")
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
        row["mapped_on"] = remapped.get(uid, MAPPING_BASE)
        if row.get("protected_action_applicability") not in ("protected", "unprotected"):
            row["protected_action_applicability"], row["protected_action_basis"] = \
                protected_action_applicability(row)
        row["completion"], row["completion_reasons"] = completion(row)
        matrix.append(row)
    # Wave overlay: what integrated implementation clusters report for each row. It is kept
    # beside `maturity`, never folded into it: a worker's DONE is a claim that the next
    # re-mapping of that row must verify against code before maturity may rise (F-867).
    integrated = json.loads((HERE / "waves" / "INTEGRATED.json").read_text()) \
        if (HERE / "waves" / "INTEGRATED.json").exists() else {}
    by_uid = {r["uid"]: r for r in matrix}
    for cluster, meta in integrated.items():
        rep = HERE / "waves" / f"fb1_{cluster}.json"
        if not rep.exists():
            continue
        for item in json.loads(rep.read_text())["requirements"]:
            row = by_uid.get(item["uid"])
            if row is not None:
                row.setdefault("wave", []).append({
                    "cluster": cluster, "merge": meta["merge"], "status": item["status"],
                    "remaining": item.get("remaining"),
                    "note": "worker-reported; integrator ran targeted suites; maturity not "
                            "re-mapped yet"})
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
        "wave_reported": dict(Counter(w["status"] for r in matrix for w in r.get("wave", []))),
        "completion": dict(Counter(r["completion"] for r in matrix)),
        "launch_critical_completion": dict(Counter(r["completion"] for r in lc)),
        "launch_critical_open": sum(1 for r in lc if r["completion"] == "OPEN"),
        "launch_critical_open_reasons": dict(Counter(
            reason.split(":")[0].split(" below")[0] for r in lc if r["completion"] == "OPEN"
            for reason in r["completion_reasons"])),
        "protected_action_applicability": dict(Counter(
            r["protected_action_applicability"] for r in matrix)),
        "capped_by_unwritten_state": sum(1 for r in matrix if any(
            "F-836" in n for n in r["adjudication"])),
        "capped_by_proxy_evidence": sum(1 for r in matrix if any(
            "F-837" in n for n in r["adjudication"])),
        "mapped_on": dict(Counter(r["mapped_on"][:7] for r in matrix)),
    }
    reach_basis = json.loads((HERE / "module_reachability.json").read_text()).get("basis")
    out = {"basis": {"mapping": {"base": MAPPING_BASE,
                                 "remaps": {sha7: {"sha": full, "rows": sum(
                                     1 for r in matrix if r["mapped_on"] == full)}
                                            for sha7, full in REMAP_SHAS.items()},
                                 "rows_on_base": sum(1 for r in matrix
                                                     if r["mapped_on"] == MAPPING_BASE),
                                 "per_row": "matrix[].mapped_on"},
                     "reachability": reach_basis,
                     "production": PRODUCTION, "registry": "master_registry.json"},
           "levels": LEVELS, "summary": summary, "matrix": matrix}
    (HERE / "closure_matrix.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    scope = launch_scope(matrix, remapped_classes, overrides, out["basis"])
    (HERE / "LAUNCH_SCOPE.json").write_text(json.dumps(scope, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1)[:4000])


if __name__ == "__main__":
    main()
