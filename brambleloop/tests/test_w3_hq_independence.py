"""Production never depends on an artefact that exists only on HQ (F-397). Wave 3, lane TOOLS.

The image is what the Dockerfile COPYs (src, release, tests, run_tests.sh, the requirements
files). A runtime module that climbs out of the package to the checkout root and reads anything
else -- research/, artifacts/, evidence/ -- works on a developer machine and silently degrades
in production. This is the promotion gate: every literal checkout-root path a module under src/
joins must be something the image contains, or be listed here with the reason it is safe and a
test that proves the fallback.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
sys.path.insert(0, str(ROOT / "src"))

# Anchors that resolve to the brambleloop/ checkout root (= /app in the image).
_ANCHOR = re.compile(
    r"(?:parents\[3\]|parent\.parent\.parent|_PACKAGE\.parent\.parent|\bREPO_ROOT|\bROOT)"
    r"\s*/\s*[\"']([A-Za-z0-9_.-]+)[\"']")
# Reviewed exceptions: (module, top-level name) -> why production does not depend on it.
ALLOWED = {
    ("build2/maturity.py", "research"): (
        "the F-125 disagreement check reads research/final_build/closure_matrix.json when it "
        "exists and otherwise the shipped projection build2/final_master_closure.json "
        "(test_the_maturity_check_falls_back_to_the_shipped_projection)"),
    ("seo/_testkit.py", "tests"): "a test kit; tests/ is in the image anyway",
    ("core/decision_index.py", "DECISION_LOG.md"): (
        "read only by the index generator (`main`) in the repository; at runtime `recorded()` "
        "reads the shipped core/decision_index.json (test_w3_decision_index keeps it in sync)"),
    ("laura/memory/provenance.py", "DECISION_LOG.md"): (
        "read when present (repository); in the image the OSError path falls back to the "
        "shipped core/decision_index.json (test_runtime_readers_fall_back_to_the_index...)"),
}


def image_contents() -> set[str]:
    """Top-level names the Dockerfile copies into /app."""
    out = set()
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        m = re.match(r"\s*COPY\s+(.+?)\s+(\S+)\s*$", line)
        if m:
            for src in m.group(1).split():
                out.add(src.rstrip("/").split("/")[0])
    return out


def checkout_root_reads() -> list[tuple[str, int, str]]:
    found = []
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).as_posix()
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for m in _ANCHOR.finditer(line):
                found.append((rel, n, m.group(1)))
    return found


def test_the_image_contents_are_read_from_the_dockerfile():
    got = image_contents()
    assert {"src", "release", "tests", "requirements.lock"} <= got, got
    assert "research" not in got and "artifacts" not in got


def test_no_runtime_module_reads_a_checkout_path_the_image_does_not_contain():
    image = image_contents()
    reads = checkout_root_reads()
    assert reads, "the scan found no checkout-root reads at all; the pattern is broken"
    bad = [(m, n, top) for m, n, top in reads
           if top not in image and (m, top) not in ALLOWED]
    assert not bad, ("runtime reads of HQ-only paths (promote the artefact into src/ or "
                     "release/, or record why it is safe): " + repr(bad))


def test_every_allowance_is_still_needed():
    reads = {(m, top) for m, _n, top in checkout_root_reads()}
    stale = [k for k in ALLOWED if k not in reads]
    assert not stale, stale


def test_the_maturity_check_falls_back_to_the_shipped_projection():
    from brambleloop.build2 import final_master, maturity

    saved = maturity._FINAL_MATRIX
    try:
        maturity._FINAL_MATRIX = Path("/nonexistent/closure_matrix.json")
        rows, source = maturity._final_matrix_rows()
    finally:
        maturity._FINAL_MATRIX = saved
    assert source == final_master.SNAPSHOT.name, source
    assert rows and all(r["maturity"] in maturity.INTEGRATED_OR_ABOVE for r in rows)
    assert any((r["producer"] or "").startswith("src/brambleloop/") for r in rows)
    # Same rows the research matrix gives, when it is present.
    full, _ = maturity._final_matrix_rows(maturity._FINAL_MATRIX)
    want = {r["uid"] for r in full if r.get("maturity") in maturity.INTEGRATED_OR_ABOVE}
    assert {r["uid"] for r in rows} == want


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
