"""Read-only reconstruction of committed Visual evidence. No providers or credentials.

Writes only visual_v2/out. Historical images may be inspected as evidence, but are
never inputs to build_probe.py or render_probe.py. Costs are recorded estimates,
not independently reconciled invoices. Run from any directory with Python 3.12.
"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESEARCH = HERE.parent
OUT = HERE / "out"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    result = {"snapshot": "0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56", "experiments": {}}
    for exp in ("bench1", "bench2", "v1grad"):
        directory = RESEARCH / exp / "out"
        m = read(directory / f"{exp}_manifest.json")
        g = read(directory / f"{exp}_gate.json")
        rows = {}
        for name, row in g.items():
            rows[name] = {k: row.get(k) for k in (
                "reference_version", "prompt_version", "output_sha256", "usd_generation",
                "deterministic", "properties", "judge", "verdict")}
        result["experiments"][exp] = {
            "attempts": len(m["runs"]), "successful_draws": sum(bool(r.get("ok")) for r in m["runs"]),
            "gate_records": len(g), "verdicts": dict(collections.Counter(r["verdict"]["status"] for r in g.values())),
            "material_failures": dict(collections.Counter(k for r in g.values() for k in r["verdict"]["material_failures"])),
            "all_seven_realism_pass": sum(len(r.get("judge") or {}) == 7 and all(x == "PASS" for x in r["judge"].values()) for r in g.values()),
            "recorded_spent_usd": m["spent_usd"], "rows": rows,
        }
    e5 = read(RESEARCH / "e5/out/e5_validation.json")
    result["experiments"]["e5"] = {
        "draws": len(e5["results"]), "yield_per_mode": e5["yield_per_mode"],
        "judge_pass_sum": sum(r["judge_pass"] for r in e5["yield_per_mode"].values()),
        "spend": e5["spend_usd"],
        "judge_record_cost_sum": round(sum(sum(v.get("cost_usd", 0) for v in read(p).get("views", [])) for p in (RESEARCH / "e5/out").glob("judge_*.json")), 6),
    }
    result["experiments"]["e4"] = {}
    for tag in ("e4", "e4r2", "e4r3", "e4y"):
        m = read(RESEARCH / f"e4/out/{tag}_manifest.json")
        v = read(RESEARCH / f"e4/out/{tag}_validation.json")
        result["experiments"]["e4"][tag] = {"attempts": len(m["runs"]), "usd_list": m["spent_usd_list_price"], "runs": m["runs"], "validation": v}
    result["experiments"]["e3"] = {}
    for suffix in ("", "_pkg"):
        m = read(RESEARCH / f"e3/out/e3_manifest{suffix}.json")
        c = read(RESEARCH / f"e3/out/e3_correspondence{suffix}.json")
        result["experiments"]["e3"][suffix or "rgb"] = {"manifest": m, "correspondence": c}
    result["experiments"]["e2"] = {str(p.relative_to(RESEARCH)): read(p) for p in (RESEARCH / "e2/out").rglob("e2_manifest.json")}
    result["experiments"]["e1"] = {"manifest": read(RESEARCH / "e1/out/e1_manifest.json"), "measurements": read(RESEARCH / "e1/out/e1_measurements.json")}
    result["experiments"]["d"] = {}
    for kind in ("sc", "hdc"):
        d = read(RESEARCH / f"d/out/milestone_d_{kind}_final.json")
        result["experiments"]["d"][kind] = {k: d[k] for k in ("status", "geometry_sha256", "failed", "unknown", "items", "seconds")}
    previews = {}
    for exp in ("v1grad", "bench2"):
        d = RESEARCH / exp / "out/gen_preview"
        index = read(d / "INDEX.json")
        entries = index.get("draws", {})
        previews[exp] = {"note": index.get("note"), "records": {name: {"matches_preview_hash": sha(d / name) == r["preview_sha256"], "full_sha256": r["full_sha256"]} for name, r in entries.items()}}
    result["preview_integrity"] = previews
    (OUT / "evidence_reconstruction.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    inventory = []
    roots = [RESEARCH / name for name in ("d", "e1", "e2", "e3", "e4", "e5", "bench1", "bench2", "v1grad")]
    roots += [ROOT / "src/brambleloop/visual", ROOT / "src/brambleloop/cir", ROOT / "src/brambleloop/gateway"]
    paths = {p for root in roots for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    paths |= set(RESEARCH.glob("VISUAL*.md"))
    paths |= {ROOT / "BUILD_STATE.md", ROOT / "DECISION_LOG.md", ROOT / "src/brambleloop/products/texture.py"}
    paths |= {p for p in (ROOT / "tests").glob("test_*.py") if any(x in p.name for x in ("visual", "stitch", "drape", "render", "milestone", "fabric", "topology", "gateway", "model_freeze"))}
    for p in sorted(paths):
        inventory.append({"path": str(p.relative_to(ROOT)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha(p)})
    (OUT / "source_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(json.dumps({exp: {k:v for k,v in data.items() if k in ("attempts", "successful_draws", "verdicts", "material_failures", "recorded_spent_usd", "all_seven_realism_pass", "judge_pass_sum", "spend", "judge_record_cost_sum")} for exp, data in result["experiments"].items()}, indent=2))


if __name__ == "__main__":
    main()
