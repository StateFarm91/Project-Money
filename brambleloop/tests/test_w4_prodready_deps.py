"""W4-PRODREADY: every third-party module production code imports is in requirements.lock.

The production image installs ONLY requirements.lock (Dockerfile: `--require-hashes
--no-deps`). On 2026-10-19 scipy was imported unguarded by the disclosed-render verifier
(visual/render_verification.py) and the listing export check (publish/disclosed_listing.py)
but declared in neither requirements.txt nor the lock. The developer venv had scipy, so the
suite passed and hid it, while the deployed build could not render or verify listing images.

This parses every `import` under src/ (AST, so function-level imports count), drops the
standard library and the package itself, maps each module to the distribution that provides
it, and requires that distribution to be pinned in requirements.lock and named in
requirements.txt's closure. The only exceptions are listed below with the reason, and each
must stay a lazy (function-level) import, so importing its module can never fail at startup.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_prodready_deps.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOCK = ROOT / "requirements.lock"
REQS = ROOT / "requirements.txt"

# Not runtime dependencies, deliberately absent from the image. Each is imported only inside
# a function, on a path the deployed service never takes.
NOT_RUNTIME = {
    "fontTools": "brand/fontbuild.py is a build-time tool run by hand when the typography "
                 "changes; its output (data/glyphs.json) is what ships",
    "mitsuba": "visual/pbr_scene.py: the ~200MB physically based renderer for a hand-run "
               "feasibility spike; guarded, raises a stated RuntimeError when absent",
    "pdfplumber": "teardown/reader.py: fallback only if pypdf is ever dropped; pypdf is "
                  "locked and `available()` picks it first",
}
# Import name -> distribution, for an import whose distribution is not installed here.
_KNOWN = {"PIL": "pillow", "yaml": "pyyaml"}


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _imports() -> dict[str, list[tuple[str, int, bool]]]:
    """{top-level module: [(file, line, at_module_level)]} for every non-stdlib import."""
    out: dict[str, list[tuple[str, int, bool]]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level = {id(n) for n in tree.body}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in sys.stdlib_module_names or top in ("brambleloop", "__future__"):
                    continue
                out.setdefault(top, []).append(
                    (str(path.relative_to(ROOT)), node.lineno, id(node) in top_level))
    return out


def _locked() -> set[str]:
    names = set()
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==\S+", line.strip())
        if m:
            names.add(_canon(m.group(1)))
    return names


def test_every_third_party_import_under_src_is_locked():
    imports = _imports()
    assert len(imports) >= 8, sorted(imports)       # the walk found the real dependencies
    provider = metadata.packages_distributions()
    locked = _locked()
    assert "numpy" in locked and "sqlalchemy" in locked, sorted(locked)[:10]
    missing = []
    checked = 0
    for module, sites in sorted(imports.items()):
        if module in NOT_RUNTIME:
            continue
        dists = provider.get(module) or ([_KNOWN[module]] if module in _KNOWN else [])
        if not dists:
            missing.append(f"{module}: no installed distribution provides it ({sites[0]})")
            continue
        checked += 1
        if not any(_canon(d) in locked for d in dists):
            missing.append(f"{module} (distribution {dists}) is imported at {sites[0][0]}:"
                           f"{sites[0][1]} but is not pinned in requirements.lock")
    assert checked >= 8, checked
    assert not missing, "\n".join(missing)


def test_scipy_is_declared_and_locked_with_hashes():
    reqs = [ln.split("#")[0].strip() for ln in REQS.read_text().splitlines()]
    assert any(re.match(r"^scipy\b", r) for r in reqs), "scipy is not in requirements.txt"
    text = LOCK.read_text()
    m = re.search(r"^scipy==(\S+) \\\n((?:    --hash=sha256:[0-9a-f]{64}.*\n)+)", text, re.M)
    assert m, "scipy is not pinned with hashes in requirements.lock"
    assert m.group(2).count("--hash=sha256:") >= 10, m.group(2)[:200]
    numpy = re.search(r"^numpy==(\d+)\.(\d+)", text, re.M)
    assert numpy and (int(numpy.group(1)), int(numpy.group(2))) < (2, 7), numpy
    # the production importers really do import it
    sites = {s[0] for s in _imports()["scipy"]}
    assert {"src/brambleloop/visual/render_verification.py",
            "src/brambleloop/publish/disclosed_listing.py"} <= sites, sites


def test_the_not_runtime_exceptions_stay_lazy_and_absent():
    imports = _imports()
    locked = _locked()
    for module, why in NOT_RUNTIME.items():
        assert why
        sites = imports.get(module) or []
        assert sites, f"{module} is no longer imported: remove its exception"
        top = [s for s in sites if s[2]]
        assert not top, f"{module} imported at module level {top}: it would fail at startup"
        assert _canon(module) not in locked, f"{module} is locked: drop its exception"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:2000])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
