"""Beginner failure simulation (F-823) -- W4-C11.

"For foundational lessons, adversarial QA checks likely beginner mistakes: wrong loop, wrong
stitch count, skipped turning chain, excessive tension, wrong hook, twisted foundation, missed
gauge, reversed RS/WS and similar errors."

For each mistake the question is the same: if a beginner makes it while following this lesson,
does the lesson give them something that shows it? A mistake is

* DETECTED -- the lesson carries the check that exposes it, shown by simulation where the
  mistake can be worked: the mistake is applied to the lesson's practice swatch (a CIR) and the
  compiler, the twin or the written instruction differs from the lesson's;
* UNGUARDED -- nothing in the lesson would show it;
* NOT_APPLICABLE -- the lesson cannot produce it (no turning chain in a lesson worked in the
  round; no RS/WS in a plain fabric).

Simulations: wrong stitch count -> one stitch dropped in row 2, and the compiler's count must
disagree with the row total the lesson states; skipped turning chain -> row 2's turning chain
removed, and the written text must change (the instruction states the chain); excessive
tension / missed gauge -> stitch gauge 15 % tighter, and the swatch's measured size must move
beyond the 2 % gauge tolerance (the lesson states a gauge to measure against); wrong loop -> the
taught loop switched, and the lesson must name the loop or carry its technique diagram.

Only foundational lessons (`curriculum.track_of` = foundations for any topic) are required to
leave nothing UNGUARDED; others are reported but NOT_REQUIRED.
"""
from __future__ import annotations

import copy
import re

MISTAKES = ("wrong_loop", "wrong_stitch_count", "skipped_turning_chain", "excessive_tension",
            "wrong_hook", "twisted_foundation", "missed_gauge", "reversed_rs_ws")
GAUGE_TOLERANCE = 0.02


def _text(spec) -> str:
    return " ".join([str(spec.get("learner_problem") or "")] +
                    [str(s.get("instruction") or "") for s in spec.get("steps") or []])


def _compile(cir_dict):
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR

    cir = CIR.from_dict(cir_dict)
    return cir, compile_cir(cir)


def _written(cir_dict, terminology):
    from ..cir.writer import write_pattern

    cir, result = _compile(cir_dict)
    return write_pattern(cir, result, terminology)


def _width(cir_dict):
    from ..cir.twin import build_twin

    cir, result = _compile(cir_dict)
    return build_twin(cir, result).width_cm


def _rows(cir_dict):
    return [r for comp in cir_dict.get("components") or [] for r in comp.get("rows") or []]


def simulate(spec: dict) -> dict:
    text = _text(spec)
    t = spec.get("terminology", "US")
    sw = (spec.get("swatch") or {}).get("cir")
    flat = bool(sw) and all(str(c.get("construction", "")).endswith("rows")
                            for c in sw.get("components") or [])
    loops = {s.get("loop", "both") for s in spec.get("steps") or []}
    textured = loops - {"both"} or any(s.get("stitch") in ("fpdc", "bpdc")
                                       for s in spec.get("steps") or [])
    diagrams = {(a.get("stitch"), a.get("loop", "both")) for a in spec.get("assets") or []
                if a.get("kind") == "technique_diagram"}
    out: dict[str, dict] = {}

    def put(m, state, why):
        out[m] = {"state": state, "why": why}

    # wrong loop
    named = re.search(r"\b(both loops|front loop|back loop|blo|flo)\b", text, re.I)
    drawn = all((s.get("stitch"), s.get("loop", "both")) in diagrams
                for s in spec.get("steps") or [])
    put("wrong_loop", "DETECTED" if named or drawn else "UNGUARDED",
        "the lesson names the loop" if named else
        "every step carries its technique diagram" if drawn else
        "no step names the loop and no diagram shows it")

    # wrong stitch count
    if sw and len(_rows(sw)) >= 2:
        bad = copy.deepcopy(sw)
        op = _rows(bad)[1]["ops"][0]
        op["count"] = int(op.get("count", 1)) - 1
        caught = bool(_compile(bad)[1].errors)
        put("wrong_stitch_count", "DETECTED" if caught else "UNGUARDED",
            "a dropped stitch in row 2 disagrees with the row total the lesson states" if caught
            else "a dropped stitch compiles cleanly: no row total exposes it")
    else:
        counted = re.search(r"\(\d+\)|\b\d+ (sts|stitches)\b", text)
        put("wrong_stitch_count", "DETECTED" if counted else "UNGUARDED",
            "the instructions state a stitch count" if counted else
            "no swatch row total and no stated count")

    # skipped turning chain
    if not flat:
        put("skipped_turning_chain", "NOT_APPLICABLE", "no flat rows: nothing turns")
    else:
        bad = copy.deepcopy(sw)
        _rows(bad)[1]["turning_chain"] = 0
        try:
            changed = _written(bad, t) != _written(sw, t)
        except (KeyError, ValueError):
            changed = True
        put("skipped_turning_chain", "DETECTED" if changed else "UNGUARDED",
            "the written rows state the turning chain" if changed else
            "the written rows read the same without it")

    # tension and gauge
    g = (sw or {}).get("gauge")
    if sw and g:
        bad = copy.deepcopy(sw)
        bad["gauge"]["stitches_per_10cm"] = float(g["stitches_per_10cm"]) * 1.15
        w0, w1 = _width(sw), _width(bad)
        moved = w0 and w1 and abs(w1 - w0) / w0 > GAUGE_TOLERANCE
        for m in ("excessive_tension", "missed_gauge"):
            put(m, "DETECTED" if moved else "UNGUARDED",
                f"15 % tighter tension changes the swatch width {w0:.1f} -> {w1:.1f} cm "
                f"against a stated gauge" if moved else "the stated gauge does not show it")
    else:
        said = re.search(r"\b(gauge|tension|swatch)\b", text, re.I)
        for m in ("excessive_tension", "missed_gauge"):
            put(m, "DETECTED" if said else "UNGUARDED",
                "the lesson tells the learner to check gauge" if said else
                "no gauge is stated to measure against")

    # wrong hook
    hook = (spec.get("assumptions") or {}).get("hook_mm")
    put("wrong_hook", "DETECTED" if hook and (not g or g.get("hook_mm") == hook) else
        "UNGUARDED", f"the lesson states a {hook} mm hook" if hook else "no hook stated")

    # twisted foundation
    if not flat:
        put("twisted_foundation", "NOT_APPLICABLE", "no foundation chain worked flat")
    else:
        warned = re.search(r"\b(twist\w*|untwisted|flat chain|chain lies flat)\b", text, re.I)
        put("twisted_foundation", "DETECTED" if warned else "UNGUARDED",
            "the lesson warns about a twisted chain" if warned else
            "nothing warns that the foundation chain must not twist")

    # reversed RS/WS
    if not textured:
        put("reversed_rs_ws", "NOT_APPLICABLE", "a plain fabric has no right or wrong side")
    else:
        sided = re.search(r"\b(right side|wrong side|RS|WS)\b", text)
        put("reversed_rs_ws", "DETECTED" if sided else "UNGUARDED",
            "the lesson marks the right side" if sided else
            "a textured fabric with no right side marked")
    return out


def check(db, slug: str) -> dict:
    from .curriculum import track_of
    from .models import Lesson

    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None:
            raise LookupError(slug)
        spec = dict(row.spec)
    foundational = any(track_of(db, t) == "foundations" for t in spec.get("topics") or [])
    sim = simulate(spec)
    unguarded = sorted(m for m, r in sim.items() if r["state"] == "UNGUARDED")
    verdict = ("NOT_REQUIRED" if not foundational else "FAIL" if unguarded else "PASS")
    return {"slug": slug, "foundational": foundational, "verdict": verdict,
            "unguarded": unguarded, "mistakes": sim}
