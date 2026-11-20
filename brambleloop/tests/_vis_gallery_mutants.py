"""ENG-VIS-GALLERY mutation run: each mutant weakens one new gate; the gate suite must fail.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/_vis_gallery_mutants.py
Each mutant is applied to a copy of the source tree in a temporary directory, never in place.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = "tests/test_vis_gallery_gates.py"
E = "src/brambleloop/publish/eligibility.py"
CG = "src/brambleloop/visual/candidate_gates.py"
GP = "src/brambleloop/visual/gallery_persist.py"
SP = "src/brambleloop/visual/shot_plans.py"
GB = "src/brambleloop/visual/gallery_budget.py"
IP = "src/brambleloop/visual/image_production.py"

MUTANTS = [
    ("unknown counts as pass", E, 'if st not in ("PASS",) and not', 'if st not in ("PASS", "UNKNOWN") and not'),
    ("label not checked", E, '        if str(ev.get(field_) or "") != label["label"] or not label["label"]:',
     '        if False:'),
    ("structural bytes not compared", E, 'or str(ev.get("structural_sha256") or "") != sha:', 'or False:'),
    ("provenance fields not required", E, '    missing = [k for k in EXCEPTION_PROVENANCE if not prov.get(k)]\n    refs = prov.get("references") or []\n    if refs and not all(isinstance(r, dict) and len(',
     '    missing = []\n    refs = prov.get("references") or []\n    if refs and not all(isinstance(r, dict) and len('),
    ("no CIR reference required", E, 'if not any(isinstance(r, dict) and r.get("kind") == "pattern_derived" for r in refs):', 'if False:'),
    ("release not exact", E, 'if not rel or not prov.get("release") or rel != str(prov["release"]):', 'if not rel:'),
    ("presented as photo allowed", E, 'if str(ev.get("presented_as") or "").lower() != "ai_generated":', 'if False:'),
    ("motif not required", E, 'GALLERY_CHECKS: tuple[str, ...] = ("structural_fidelity", "motif_fidelity",', 'GALLERY_CHECKS: tuple[str, ...] = ("structural_fidelity",'),
    ("route not dispatched", E, '    if evidence and evidence.get("route") == GALLERY_ROUTE:\n        return gallery_exception(candidate, evidence)\n', ''),
    ("etsy gate back", E, '"quality", "publication_gates")\nEXCEPTION_LAURA', '"quality", "etsy_policy", "publication_gates")\nEXCEPTION_LAURA'),
    ("fixture pass counts", GP, '        st = CG.gate_status(c)\n', '        st = c.get("status", CG.UNKNOWN)\n'),
    ("missing check passes", GP, '            seen.append((UNMEASURED, f"{n}: no reading"))', '            seen.append((PASS, f"{n}: no reading"))'),
    ("unknown reads pass in matrix", GP, '        st = {CG.UNKNOWN: UNMEASURED}.get(st, st)', '        st = {CG.UNKNOWN: PASS}.get(st, st)'),
    ("evidence drops structural sha", CG, '"structural_sha256": (checks.get("product_truth") or {}).get("sha256"),', '"structural_sha256": cand.get("sha256"),'),
    ("hero always allowed", CG, '    if job == el.HERO_JOB and route == el.GALLERY_ROUTE:', '    if job == el.HERO_JOB:'),
    ("campaign loses a slot", SP, '(el.DETAIL, "detail"), (el.SCALE, "size"),', '(el.SCALE, "size"),'),
    ("fit generated", SP, '(el.ANGLE, "angle"), (el.DETAIL, "detail")', '(el.FIT, "angle"), (el.DETAIL, "detail")'),
    ("owner cap can raise", GB, '        if amount > code_cap():', '        if False:'),
    ("non-owner sets cap", GB, '    if not str(by).startswith("owner"):', '    if False:'),
    ("cap ignores owner", GB, '    return code_cap() if own is None else min(code_cap(), own)', '    return code_cap()'),
    ("cir references not checked", GP, '    elif not cir_references or sent != list(cir_references):', '    elif False:'),
    ("stub readings count as independent", "src/brambleloop/ops/production_evidence.py", '        if c.get("test_double") or c.get("fixture_only"):\n            return False', '        if False:\n            return False'),
    ("fidelity double counts as independent", "src/brambleloop/ops/production_evidence.py", 'if isinstance(fid, dict) and (fid.get("test_double") or fid.get("fixture_only")):', 'if False:'),
    ("route call cap ignored", IP, '    calls = FLUX_MAX_GENERATION_CALLS if route_of_key(key) else MAX_GENERATION_CALLS', '    calls = MAX_GENERATION_CALLS'),
]


RG = "src/brambleloop/publish/release_gates.py"
GR = "src/brambleloop/visual/gallery_recovery.py"
PE = "src/brambleloop/ops/production_evidence.py"
E2E = "tests/test_vis_gallery_e2e.py"
# (name, file, old, new, tests to run): the chain-level mutants, ~3-5 min each
E2E_MUTANTS = [
    ("refused frame does not block the set", RG, "    if refused:\n        reasons.append(f\"generated frames:", "    if False:\n        reasons.append(f\"generated frames:", "test_8"),
    ("selected bytes not compared", RG, "if f is None or f.sha256 != sel.get(\"sha256\") or not is_gallery_route_frame(f):", "if f is None or not is_gallery_route_frame(f):", "test_8"),
    ("generated path not dispatched", RG, "    if selection is not None:\n        return generated_listing_set(", "    if False:\n        return generated_listing_set(", "test_2"),
    ("certify ignores blockers", GP, "    if not st[\"ok\"]:\n        with db.session() as s:", "    if False:\n        with db.session() as s:", "test_4"),
    ("laura publication passes unapproved", GP, "\"status\": PASS if ok else UNMEASURED, \"owner\": ID_AGENT,", "\"status\": PASS, \"owner\": ID_AGENT,", "test_5"),
    ("recovery ignores Laura", GR, "        if bool(r.laura_present) != bool(laura):\n            continue\n", "", "test_6"),
]


def _run(rel, old, new, suite, env_extra=None):
    with tempfile.TemporaryDirectory(prefix="visgal-mut-") as d:
        tree = Path(d) / "b"
        shutil.copytree(ROOT / "src", tree / "src")
        shutil.copytree(ROOT / "tests", tree / "tests",
                        ignore=shutil.ignore_patterns("__pycache__"))
        if suite == E2E:
            # the chain reads repository data beside src/ (registries, references, fixtures):
            # linked read-only, never copied or mutated
            for p in ROOT.iterdir():
                if p.name not in ("src", "tests") and not (tree / p.name).exists():
                    (tree / p.name).symlink_to(p)
            if (ROOT.parent / "ops").exists():
                (tree.parent / "ops").symlink_to(ROOT.parent / "ops")
        f = tree / rel
        text = f.read_text()
        if text.count(old) != 1:
            return None
        f.write_text(text.replace(old, new))
        env = {"PYTHONPATH": "src:tests", "PATH": "/usr/bin:/bin:/usr/local/bin",
               "HOME": str(tree), **(env_extra or {})}
        r = subprocess.run([sys.executable, suite], cwd=tree, capture_output=True, text=True,
                           env=env, timeout=2400)
        return r.returncode != 0


def main_e2e() -> int:
    from concurrent.futures import ThreadPoolExecutor

    def one(m):
        name, rel, old, new, only = m
        return name, _run(rel, old, new, E2E, {"VIS_E2E_ONLY": only})

    survived = []
    with ThreadPoolExecutor(4) as ex:
        for name, killed in ex.map(one, E2E_MUTANTS):
            print(("KILLED  " if killed else ("BAD     " if killed is None else "SURVIVED"))
                  + f" {name}", flush=True)
            if not killed:
                survived.append(name)
    print(f"{len(E2E_MUTANTS) - len(survived)} of {len(E2E_MUTANTS)} e2e mutants killed")
    return 1 if survived else 0


def main() -> int:
    if "--e2e" in sys.argv:
        return main_e2e()
    survived = []
    for name, rel, old, new in MUTANTS:
        with tempfile.TemporaryDirectory(prefix="visgal-mut-") as d:
            tree = Path(d) / "b"
            shutil.copytree(ROOT / "src", tree / "src")
            shutil.copytree(ROOT / "tests", tree / "tests",
                            ignore=shutil.ignore_patterns("__pycache__"))
            f = tree / rel
            text = f.read_text()
            if text.count(old) != 1:
                print(f"BAD  {name}: pattern found {text.count(old)} times")
                survived.append(name)
                continue
            f.write_text(text.replace(old, new))
            r = subprocess.run([sys.executable, SUITE], cwd=tree, capture_output=True,
                               text=True, env={"PYTHONPATH": "src:tests", "PATH": "/usr/bin:/bin"},
                               timeout=600)
            killed = r.returncode != 0
            print(("KILLED  " if killed else "SURVIVED") + f" {name}")
            if not killed:
                survived.append(name)
    print(f"{len(MUTANTS) - len(survived)} of {len(MUTANTS)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
