"""The benchmark pattern as a recurring end-to-end test (F-678) -- W4-C07.

"The purchased benchmark pattern plus its real listing photographs become the recurring
end-to-end test: pattern -> CIR -> full-product 3D -> AI ad image -> Product Truth/real-outcome
comparison."

Benchmark 2 (the purchased Mini Star Stitch Cardigan) was a one-off research run
(`research/bench2`), frozen in `out/bench2_manifest.json`: the Product Truth digest, the CIR
fingerprint, the deterministic reference's sha256 and every gated generation. `run(bench_dir)`
replays the chain against that freeze, so any change anywhere in the pipeline that moves the
benchmark shows up as a regression rather than going unnoticed:

1. **pattern** -- the stored Product Truth facts (counts, gauge, measurements, cited to pages;
   the designer's prose and photographs are never in the repository) and their own arithmetic
   checks;
2. **cir** -- the CIR rebuilt from those facts (`research/bench2/product_truth.build_cir`) must
   compile, and its fingerprint must equal the frozen one;
3. **reference** -- the deterministic full-product flat-lay reference rebuilt from Product
   Truth must be byte-identical to the frozen reference;
4. **ad_image** -- the AI generations already gated against that reference are read back; a
   NEW generation is a paid call and is never made here (SKIPPED_NEEDS_BUDGET), so this stage
   reports the stored verdicts only;
5. **comparison** -- the private comparison of certified heroes with the designer's photographs:
   UNKNOWN while no hero has been certified.

A deterministic stage that differs from the freeze is REGRESSION; a stage that cannot run
(the research directory is not shipped in the production image) is UNKNOWN, never PASS.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "research" / "bench2"
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def _load(bench: Path, name: str):
    if str(bench) not in sys.path:
        sys.path.insert(0, str(bench))
    spec = importlib.util.spec_from_file_location(f"bench2_{name}", bench / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(bench_dir: Path | str | None = None, *, size: str = "2-3T",
        build_reference: bool = True) -> dict:
    bench = Path(bench_dir or DEFAULT_DIR)
    out = bench / "out"
    stages: dict[str, dict] = {}
    if not (out / "product_truth.json").exists() or not (out / "bench2_manifest.json").exists():
        return {"state": UNKNOWN, "stages": {},
                "why": f"benchmark freeze not present at {bench} (not shipped in the image)"}
    pt = json.loads((out / "product_truth.json").read_text())
    manifest = json.loads((out / "bench2_manifest.json").read_text())
    checks = pt["derived"].get("checks") or []
    bad = [c["check"] for c in checks if c.get("status") != "PASS"]
    stages["pattern"] = {"status": PASS if checks and not bad else FAIL,
                         "checks": len(checks), "failed": bad,
                         "basis": "stored Product Truth facts, page-cited; no designer prose"}

    from ..cir import compiler

    P = _load(bench, "product_truth")
    facts = dict(pt["facts"])
    facts["_derived_after"] = [p["sleeve_rows_after_neck_derived"]
                               for p in pt["derived"]["per_size"]]
    cir = P.build_cir(facts, size)
    res = compiler.compile_cir(cir)
    frozen = manifest.get("cir_fingerprint")
    stages["cir"] = {"status": PASS if res.ok and cir.fingerprint == frozen else FAIL,
                     "compiles": res.ok, "fingerprint": cir.fingerprint, "frozen": frozen,
                     "errors": [str(e) for e in res.errors][:5]}

    if build_reference:
        R = _load(bench, "reference")
        want = (manifest.get("references") or {}).get("ref") or {}
        with tempfile.TemporaryDirectory(prefix="bench2ref_") as tmp:
            R.build(Path(tmp), prefix="ref")
            got = {k: _sha(Path(tmp) / f"ref_{f}.png")
                   for k, f in (("rgb", "flatlay"), ("mask", "mask"), ("normal", "normal"))}
        drift = sorted(k for k in want if got.get(k) != want[k])
        stages["reference"] = {"status": PASS if want and not drift else FAIL,
                               "drifted": drift, "frozen": want, "rebuilt": got}
    else:
        stages["reference"] = {"status": UNKNOWN, "why": "not rebuilt in this run"}

    gate_path = out / "bench2_gate.json"
    gated = json.loads(gate_path.read_text()) if gate_path.exists() else {}
    verdicts = {k: (v.get("deterministic") or {}).get("status", UNKNOWN)
                for k, v in gated.items()}
    stages["ad_image"] = {"status": "STORED" if verdicts else UNKNOWN,
                          "stored_verdicts": verdicts,
                          "any_pass": any(v == PASS for v in verdicts.values()),
                          "new_generation": "SKIPPED_NEEDS_BUDGET",
                          "why": "a new generation is a paid call; only an owner-approved "
                                 "budget runs one"}
    cmp_path = out / "private_comparison.json"
    certified = (json.loads(cmp_path.read_text()).get("certified") if cmp_path.exists()
                 else None)
    stages["comparison"] = {"status": PASS if certified else UNKNOWN,
                            "why": ("certified heroes compared" if certified else
                                    "no certified hero exists to compare with the designer's "
                                    "photographs")}
    deterministic = ("pattern", "cir", "reference")
    regress = [s for s in deterministic if stages[s]["status"] == FAIL]
    return {"state": "REGRESSION" if regress else "HOLDS", "regressed": regress,
            "stages": stages, "size": size,
            "frozen_utc": manifest.get("frozen_utc")}
