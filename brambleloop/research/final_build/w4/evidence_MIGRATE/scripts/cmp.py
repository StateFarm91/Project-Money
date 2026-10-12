"""Compare two snapshots. usage: cmp.py <before.json> <after.json>  (prints JSON verdict)"""
import json
import sys

a, b = (json.load(open(p)) for p in sys.argv[1:3])
out = {"dropped_tables": [], "dropped_columns": [], "retyped_columns": [],
       "nullability_tightened": [], "row_count_changes": {}, "content_changes": [],
       "added_tables": [], "added_columns": [], "dropped_indexes": [], "added_indexes": [],
       "dropped_constraints": [], "added_constraints": []}
for t, cols in a["columns"].items():
    if t not in b["columns"]:
        out["dropped_tables"].append(t)
        continue
    for col, spec in cols.items():
        nb = b["columns"][t].get(col)
        if nb is None:
            out["dropped_columns"].append(f"{t}.{col}")
        elif nb[:2] != spec[:2]:
            out["retyped_columns"].append(f"{t}.{col} {spec[:2]} -> {nb[:2]}")
        elif spec[2] == "YES" and nb[2] == "NO":
            out["nullability_tightened"].append(f"{t}.{col}")
    for col in b["columns"][t]:
        if col not in cols:
            out["added_columns"].append(f"{t}.{col} {b['columns'][t][col][0]} "
                                        f"nullable={b['columns'][t][col][2]}")
    da, db_ = a["data"][t], b["data"].get(t, {})
    if da["rows"] != db_.get("rows"):
        out["row_count_changes"][t] = [da["rows"], db_.get("rows")]
    elif da["md5"] != db_.get("md5"):
        out["content_changes"].append(t)
out["added_tables"] = sorted(set(b["columns"]) - set(a["columns"]))
out["dropped_indexes"] = sorted(set(a["indexes"]) - set(b["indexes"]))
out["added_indexes"] = sorted(set(b["indexes"]) - set(a["indexes"]))
out["dropped_constraints"] = sorted(set(a["constraints"]) - set(b["constraints"]))
out["added_constraints"] = sorted(set(b["constraints"]) - set(a["constraints"]))
out["summary"] = {k: len(v) for k, v in out.items() if k != "summary"}
print(json.dumps(out, indent=1))
