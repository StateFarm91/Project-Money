"""ENG-PLUSH mutation run: every new gate rule is weakened in a scratch copy of the tree, one at
a time, and `tests/test_eng_plush.py` must fail (kill it).

Never edits the working tree: the tree is copied to a temporary directory, each mutant is
applied to the copy, the suite runs there, and the file is restored before the next mutant.

Run: cd brambleloop && python3 scripts/mutate_plush.py [suite ...]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CS = "src/brambleloop/gates/child_safety.py"
CF = "src/brambleloop/cir/closed_forms.py"

# (name, file, old, new) -- `old` must occur exactly once.
MUTANTS: list[tuple[str, str, str, str]] = [
    ("features: hard parts unread", CS, "    hit = _HARD_PARTS.search(texts)\n",
     "    hit = None\n"),
    ("features: a face need not be embroidered", CS,
     '    if "face" in profile and not re.search(r"\\bembroider", texts):', "    if False:"),
    ("joins: unplaced accepted", CS, "    if unplaced:\n", "    if False:\n"),
    ("joins: mismatched accepted", CS,
     '    if assembly_errors or geo.verdict == "does_not_assemble":', "    if assembly_errors:"),
    ("joins: workmanship unread", CS, '    if not (re.search(r"both loops", notes)',
     '    if False and not (re.search(r"both loops", notes)'),
    ("joins: a threaded cord is a join", CS,
     "    bad = [f\"{s.piece_a}->{s.piece_b} by {s.method}\" for s in sewn\n"
     "           if s.method not in (\"whipstitch\", \"sew\", \"mattress\", \"slst\")]",
     "    bad = []"),
    ("cords: thread accepted", CS, '    if any(s.method == "thread" for s in cir.assembly):',
     "    if False:"),
    ("cords: chain loops unread", CS, "            if longest > MAX_CHAIN_RUN:",
     "            if longest > 999:"),
    ("cords: cord words unread", CS, "    hit = _CORD_WORDS.search(", "    hit = None and _CORD_WORDS.search("),
    ("stuffing: material unread", CS, "    if not _STUFFING_OK.search(materials):", "    if False:"),
    ("stuffing: point unread", CS,
     "    missing = [c.name for c in closed if c.stuff_at_round is None or not c.closes]",
     "    missing = []"),
    ("small parts: blocks ignored", CS,
     "    blocks = small_parts.blocking(cir)\n    if blocks:",
     "    blocks = small_parts.blocking(cir)\n    if False:"),
    ("physical: evidence passes", CS, '    return Check("PHYSICAL_EVIDENCE", UNKNOWN,',
     '    return Check("PHYSICAL_EVIDENCE", PASS,'),
    ("verdict: UNKNOWN reads as PASS", CS,
     "        if UNKNOWN in states:\n            return VERDICT_HELD",
     "        if UNKNOWN in states:\n            return VERDICT_PASS"),
    ("text: missing statement passes", CS,
     '    out.append(Check("SAFETY_SECTION", FAIL if missing else PASS,',
     '    out.append(Check("SAFETY_SECTION", PASS if missing else PASS,'),
    ("text: access date unread", CS, '    if f"accessed {ACCESSED}" not in folded:', "    if False:"),
    ("text: claims unread", CS, "    claim = _CLAIMS.search(folded)", "    claim = None"),
    ("text: hard parts in instructions unread", CS, "    hard = _HARD_PARTS.search(outside)",
     "    hard = None"),
    ("closed: open closure accepted", CF,
     "        if comp.closes and last.stitch_count > geometry.CLOSEABLE_STITCHES:",
     "        if False:"),
    ("closed: unstuffed closure accepted", CF,
     "        if comp.closes and comp.stuff_at_round is None:", "        if False:"),
    ("closed: early stuffing accepted", CF, "                if at < widest_index:",
     "                if False:"),
    ("closed: small opening accepted", CF,
     "                if counts[at] < STUFF_OPENING_MIN_STS:", "                if False:"),
    ("closed: unknown round accepted", CF, "            if at not in counts:",
     "            if False:"),
    ("closed: stuffing after close accepted", CF,
     "                if comp.closes and at == last.index:", "                if False:"),
    ("closed: flat closure accepted", CF, '        if comp.construction == "flat_rows":\n'
     '            findings.append(_finding("CLOSED_FORM_NOT_ROUNDS",',
     '        if False:\n            findings.append(_finding("CLOSED_FORM_NOT_ROUNDS",'),
    ("reverse: closed form unread", "src/brambleloop/cir/reverse.py",
     "    if printed_closed != expected_closed:", "    if False:"),
    ("pdf: content gate not run", "src/brambleloop/publish/pdf.py",
     "    _refuse_a_child_safety_content_failure(cir, result, pdf_bytes, childrens, terminology,\n"
     "                                           instructions=text)", "    pass"),
    ("pdf: safety section not rendered", "src/brambleloop/publish/pdf.py",
     "    if _child_safety.applies(cir, childrens):\n        profile =",
     "    if False:\n        profile ="),
    ("pdf: part diagram not drawn", "src/brambleloop/publish/pdf.py",
     "    if part_png is not None:", "    if False:"),
    ("certify: held evidence dropped", "src/brambleloop/gates/certificate.py",
     "        for check in safety.unknown():", "        for check in []:"),
    ("certify: failures dropped", "src/brambleloop/gates/certificate.py",
     "        for check in safety.failing():", "        for check in []:"),
    ("route: texture admitted", "src/brambleloop/creative/fallback_constructions.py",
     "    if texture:\n        return {\"family\": REFUSED,\n                \"needs\": (",
     "    if False:\n        return {\"family\": REFUSED,\n                \"needs\": ("),
    ("engine: small ears drafted", "src/brambleloop/creative/fallback_constructions.py",
     "    small = small_parts.blocking(cir)\n    if small:",
     "    small = small_parts.blocking(cir)\n    if False:"),
    ("asset truth: first piece only", "src/brambleloop/gates/asset_truth.py",
     "    real_colors = (set(twin.colors_used) | _colours_worked(cir)) or set(cir.colors)",
     "    real_colors = twin.colors_used or set(cir.colors)"),
    # ---- slices 2 and 3 ----
    ("surface: off the side accepted", "src/brambleloop/cir/assembly.py",
     "    if left < margin or right > fb.across_cm - margin:", "    if False:"),
    ("surface: off the top/bottom accepted", "src/brambleloop/cir/assembly.py",
     "    if bottom < margin or top > fb.up_cm - margin:", "    if False:"),
    ("surface: mirrored overlap accepted", "src/brambleloop/cir/assembly.py",
     "    if seam.mirrored and seam.stitches_from_centre * st < across / 2.0:", "    if False:"),
    ("surface: placement unmeasured", "src/brambleloop/cir/assembly.py",
     '        elif seam.edge_b == "surface":\n            _surface_join(',
     '        elif False:\n            _surface_join('),
    ("reverse: surface placement unread", "src/brambleloop/cir/reverse.py",
     "        if surface:\n            at_round, spans =",
     "        if False:\n            at_round, spans ="),
    ("cushion: texture admitted", "src/brambleloop/creative/fallback_constructions.py",
     "            if texture:\n                return {\"family\": REFUSED,\n"
     "                        \"needs\": \"an engine-modelled texture (loop",
     "            if False:\n                return {\"family\": REFUSED,\n"
     "                        \"needs\": \"an engine-modelled texture (loop"),
    ("cushion: unworked colour listed", "src/brambleloop/creative/cushions.py",
     "    if len(palette) > wanted:", "    if False:"),
    ("gate: an uninstructed face passes", CS,
     '    if instructions is not None and ("face" in profile) \\\n', '    if False and (instructions is not None) \\\n'),
    ("gate: sleep profile dropped", CS,
     "    if (childrens and childrens[0] in SLEEP_SUBCATEGORIES) or _SLEEP_WORDS.search(title):",
     "    if False:"),
    ("gate: a closed piece in rounds is not a toy", CS,
     "    if any(c.closes or c.stuff_at_round is not None for c in cir.components):\n"
     "        return True",
     "    if any(c.closes or c.stuff_at_round is not None for c in cir.components):\n"
     "        return False"),
]


def main(suites: list[str]) -> int:
    suites = suites or ["tests/test_eng_plush.py"]
    work = Path(tempfile.mkdtemp(prefix="plushmut_"))
    tree = work / "brambleloop"
    shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    survived = []
    try:
        for name, rel, old, new in MUTANTS:
            path = tree / rel
            original = path.read_text()
            if original.count(old) != 1:
                print(f"BAD  {name}: pattern occurs {original.count(old)} times")
                survived.append(name)
                continue
            path.write_text(original.replace(old, new))
            try:
                killed = any(subprocess.run([sys.executable, s], cwd=tree,
                                            capture_output=True, timeout=1800).returncode != 0
                             for s in suites)
            finally:
                path.write_text(original)
            print(f"{'KILLED ' if killed else 'SURVIVED'} {name}", flush=True)
            if not killed:
                survived.append(name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"{len(MUTANTS) - len(survived)} of {len(MUTANTS)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
