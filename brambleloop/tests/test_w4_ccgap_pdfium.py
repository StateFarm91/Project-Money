"""W4-CCGAP: PDFium is never entered by two threads at once (the web process must not crash).

Found while exercising the Command Center at c131f07: the web process died with
`bad_variant_access was thrown in -fno-exceptions mode` / SIGSEGV in libpdfium. PDFium is not
thread-safe, and the CONTENTS gallery frame (`visual.contents_frame`) rasterises the certified
pattern PDF through it. The CC's launch-packet background thread, request threads (the Store
and readiness reads verify CONTENTS frames) and worker threads can all reach it together.

* test_concurrent_contents_frames_do_not_crash_and_stay_identical: eight threads render and
  count the same certified PDF in a child process; the child must exit 0 (before the fix it
  aborted with SIGSEGV/SIGABRT) and every thread's PNG must be byte-identical.
* test_every_pdfium_use_is_under_the_lock: a static scan: any source file that imports
  pypdfium2 must route it through `contents_frame.PDFIUM_LOCK`.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_ccgap_pdfium.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
_TMP = tempfile.mkdtemp(prefix="w4_ccgap_pdfium_")

_CHILD = r"""
import hashlib, sys, threading
sys.path.insert(0, sys.argv[1])
from brambleloop.visual import contents_frame as CF
pdf = open(sys.argv[2], "rb").read()
shas, errs = set(), []
def run():
    try:
        for _ in range(6):
            fr = CF.render(pdf, slug="hexagon-coaster-set", version="1.2.0", title="t",
                           editions=["UK", "US"])
            shas.add(hashlib.sha256(fr.png).hexdigest())
    except Exception as exc:
        errs.append(repr(exc))
ts = [threading.Thread(target=run) for _ in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
print("SHAS", len(shas), "ERRS", errs[:2])
sys.exit(0 if not errs and len(shas) == 1 else 3)
"""


def _pdf_path() -> str:
    from datetime import date

    from brambleloop.publish.pdf import build_pattern_pdf
    from brambleloop.runtime import pipeline

    cir = pipeline._engineered_cir("hexagon-coaster-set")
    pdf = build_pattern_pdf(cir, terminology="US", released_on=date(2026, 10, 7)).pdf_bytes
    path = os.path.join(_TMP, "pattern-US.pdf")
    Path(path).write_bytes(pdf)
    return path


def test_concurrent_contents_frames_do_not_crash_and_stay_identical():
    pdf = _pdf_path()
    child = os.path.join(_TMP, "child.py")
    Path(child).write_text(_CHILD)
    # Twice: the unguarded crash was intermittent on one run, every run on several.
    for _ in range(2):
        p = subprocess.run([sys.executable, "-I", child, str(SRC), pdf], capture_output=True,
                           text=True, timeout=600, cwd=_TMP)
        assert p.returncode == 0, (p.returncode, p.stdout[-400:], p.stderr[-400:])
        assert "SHAS 1 ERRS []" in p.stdout, p.stdout


def test_every_pdfium_use_is_under_the_lock():
    from brambleloop.visual import contents_frame as CF

    assert hasattr(CF, "PDFIUM_LOCK")
    users = [p for p in (SRC / "brambleloop").rglob("*.py")
             if re.search(r"^\s*(import pypdfium2|from pypdfium2)", p.read_text(), re.M)]
    assert users, "expected at least contents_frame to use pypdfium2"
    for p in users:
        text = p.read_text()
        assert "PDFIUM_LOCK" in text, f"{p.relative_to(SRC)} uses pypdfium2 without PDFIUM_LOCK"
        # every PdfDocument open sits inside a `with PDFIUM_LOCK:` block and is closed there
        for m in re.finditer(r"pdfium\.PdfDocument\(", text):
            before = text[:m.start()].splitlines()
            indent = len(before[-1]) - len(before[-1].lstrip())
            guarded = False
            for line in reversed(before[:-1]):
                stripped = line.strip()
                if not stripped:
                    continue
                ind = len(line) - len(line.lstrip())
                if ind < indent:
                    guarded = stripped.startswith("with PDFIUM_LOCK")
                    break
            assert guarded, f"{p.relative_to(SRC)}: PdfDocument opened outside PDFIUM_LOCK"
        assert text.count("pdfium.PdfDocument(") <= text.count("doc.close()"), p


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
