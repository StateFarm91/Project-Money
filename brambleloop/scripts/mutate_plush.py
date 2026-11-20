"""ENG-PLUSH mutation run: every new gate rule is weakened in a scratch copy of the tree, one at
a time, and `tests/test_eng_plush.py` must fail (kill it).

Never edits the working tree: the tree is copied to a temporary directory, each mutant is
applied to the copy, the suite runs there, and the file is restored before the next mutant.

ENG-PLUSH-FIX (review L1 / H3): a suite that cannot even import is not a kill. The unmutated
copy must pass every suite first (else the run is refused, exit 2), and each mutant run is
classified: KILLED only when a suite ran and a test failed; ERROR when a suite died at import
or on its environment (ModuleNotFoundError, ImportError, SyntaxError, a timeout) -- an ERROR is
never counted as killed, and any ERROR fails the run.

Run: cd brambleloop && python3 scripts/mutate_plush.py [suite ...]
"""
from __future__ import annotations

import re
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
    ("cords: cord words unread", CS, "    hit = _cord_word(", "    hit = None and _cord_word("),
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
     "    real_colors = (set(twin.colors_used) | _colours_worked(cir, depicted)) or set(cir.colors)",
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
    # ---- ENG-PLUSH-FIX: the review's findings, each rule weakened once ----
    ("fix M1: unembroidered feature accepted", CS,
     "        clause = _unembroidered_feature(piece)\n        if clause:",
     "        clause = _unembroidered_feature(piece)\n        if False:"),
    ("fix M1: mounted feature accepted", CS,
     "        if mounted:\n            return mounted.group(0).strip()",
     "        if False:\n            return mounted.group(0).strip()"),
    ("fix M1: material allow-list off", CS, "    if unknown:\n        return Check(\"MATERIALS_KNOWN\", UNKNOWN,",
     "    if False:\n        return Check(\"MATERIALS_KNOWN\", UNKNOWN,"),
    ("fix M1: instructions feature rule off", CS,
     "    named = hard.group(0) if hard else _unembroidered_feature(outside)",
     "    named = hard.group(0) if hard else None"),
    ("fix M2: chain runs not summed", CS, "            if is_ch:\n                run += count",
     "            if is_ch:\n                run = count"),
    ("fix M2: repeats not expanded", CS, "                for _ in range(min(times, 64)):",
     "                for _ in range(min(times, 1)):"),
    ("fix M2: stitch-loop exemption swallows every loop", CS,
     "    folded = _LACE_TERMS.sub(\" \", _STITCH_LOOP_TERMS.sub(\" \", _fold(text)))",
     "    folded = re.sub(r\"\\bloops?\\b\", \" \", _fold(text))"),
    ("fix M3: certify ignores the assignment", "src/brambleloop/gates/certificate.py",
     "                                    childrens=_launch0.childrens_assignment(cir.slug))",
     "                                    childrens=None)"),
    ("fix M4: age band unread", CS, "    if band not in _ch.AGE_BANDS:", "    if False:"),
    ("fix M4: under-3 small parts unread", CS,
     "    if band == _ch.UNDER_3 and \"sewn\" in profile and small.state != PASS:",
     "    if False:"),
    ("fix M4: age text always claims", CS,
     "    if small_parts_clear is True:\n        return STATEMENTS",
     "    if True:\n        return STATEMENTS"),
    ("fix L3: uncompiled closure skipped", CF,
     "            findings.append(_finding(\"CLOSED_FORM_UNMEASURED\",",
     "            None and findings.append(_finding(\"CLOSED_FORM_UNMEASURED\","),
    ("fix L2: unread quotes pass", CS, "    unread = [k for k in sources if not SOURCES[k].verified]",
     "    unread = []"),
    ("fix L4: depicted pieces unread", "src/brambleloop/gates/asset_truth.py",
     "    depicted = set(asset.depicts_components) or None", "    depicted = None"),
    # ENG-PLUSH-FIX round 2: the attachment allow-list and the eye-options reading.
    ("fix round 2: attachment allow-list off", CS,
     "    if unknown:\n        return Check(\"ATTACHMENTS_KNOWN\", UNKNOWN,",
     "    if False:\n        return Check(\"ATTACHMENTS_KNOWN\", UNKNOWN,"),
    ("fix round 2: any attach verb is known", CS,
     "            if _KNOWN_ATTACHED.search(clause) or words & names:",
     "            if True:"),
    ("fix round 2: attachments not evaluated", CS,
     "    v.checks += [_features(cir, profile), _materials(cir), _attachments(cir),",
     "    v.checks += [_features(cir, profile), _materials(cir),"),
    ("fix round 2: eye options not required", CS,
     '        keys.append("eye_options")\n', ""),
    ("fix round 2: young reads as older", CS,
     '    young = band == _ch.UNDER_3 or "sleep" in profile or not known',
     "    young = band == _ch.UNDER_3"),
    ("fix round 2: age guidance unchecked", CS,
     "        guided = _fold(AGE_GUIDANCE_MARKER) in folded", "        guided = True"),
    ("fix round 2: pdf ignores the age band", "src/brambleloop/publish/pdf.py",
     "                age_band=childrens[1] if childrens else None):",
     "                age_band=None):"),
]


KILLED, SURVIVED, ERROR = "KILLED", "SURVIVED", "ERROR"
_ENV_ERROR = re.compile(rb"ModuleNotFoundError|ImportError|SyntaxError|IndentationError|"
                        rb"No module named|cannot import name")
_TEST_FAILED = re.compile(rb"^FAIL |^FAILED |AssertionError|[1-9]\d* failed", re.M)


def classify(proc) -> str:
    """One suite run -> KILLED (a test failed), SURVIVED (it passed) or ERROR (it never ran)."""
    if proc.returncode == 0:
        return SURVIVED
    out = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
    if _ENV_ERROR.search(out) and not _TEST_FAILED.search(proc.stdout or b""):
        return ERROR
    if _TEST_FAILED.search(out):
        return KILLED
    return ERROR                       # a non-zero exit with no failing test is not a kill


def _run(tree: Path, suite: str) -> str:
    try:
        proc = subprocess.run([sys.executable, suite], cwd=tree, capture_output=True,
                              timeout=1800)
    except subprocess.TimeoutExpired:
        return ERROR
    return classify(proc)


def _outcome(states: list[str]) -> str:
    if KILLED in states:
        return KILLED
    if ERROR in states:
        return ERROR
    return SURVIVED


def _mutant(tree: Path, suites: list[str], mutant) -> tuple[str, str]:
    name, rel, old, new = mutant
    path = tree / rel
    original = path.read_text()
    if original.count(old) != 1:
        return name, f"BAD: pattern occurs {original.count(old)} times"
    path.write_text(original.replace(old, new))
    try:
        states = []
        for s in suites:
            states.append(_run(tree, s))
            if states[-1] == KILLED:
                break
    finally:
        path.write_text(original)
    return name, _outcome(states)


def main(suites: list[str]) -> int:
    """MUTATE_JOBS=n runs n mutants at once, each in its own copy of the tree."""
    import os
    import queue
    import threading

    suites = suites or ["tests/test_eng_plush.py"]
    jobs = max(1, int(os.environ.get("MUTATE_JOBS", "1")))
    work = Path(tempfile.mkdtemp(prefix="plushmut_"))
    trees = []
    for i in range(jobs):
        tree = work / f"t{i}" / "brambleloop"
        shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                                  "*.pyc"))
        trees.append(tree)
    results: dict[str, str] = {}
    try:
        baseline = {s: _run(trees[0], s) for s in suites}
        bad = {s: st for s, st in baseline.items() if st != SURVIVED}
        if bad:
            print(f"BASELINE NOT GREEN, no mutant run: {bad}")
            return 2
        print(f"BASELINE green: {sorted(baseline)}", flush=True)
        todo: queue.Queue = queue.Queue()
        for m in MUTANTS:
            todo.put(m)
        lock = threading.Lock()

        def worker(tree: Path) -> None:
            while True:
                try:
                    m = todo.get_nowait()
                except queue.Empty:
                    return
                name, outcome = _mutant(tree, suites, m)
                with lock:
                    results[name] = outcome
                    print(f"{outcome:<8} {name}", flush=True)

        threads = [threading.Thread(target=worker, args=(t,)) for t in trees]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    survived = [n for n, o in results.items() if o == SURVIVED]
    errored = [n for n, o in results.items() if o != SURVIVED and o != KILLED]
    killed = sum(1 for o in results.values() if o == KILLED)
    print(f"{killed} of {len(MUTANTS)} mutants killed; {len(survived)} survived; "
          f"{len(errored)} errored")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
