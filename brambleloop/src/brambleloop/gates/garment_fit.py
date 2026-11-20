"""ENG-GARMENT: the garment gates, re-computed from each size's compiled rows and twin.

`gates.certificate.certify` certifies one CIR. A garment is a run of sizes sold as one
document, so these checks run over every size of a `products.garment_families` design and
look at what the per-size chain cannot see on its own. Every check recomputes from the
compiler and the twin; nothing is read from the design's own size table except to compare.

  GARMENT_STITCH_COUNT    every recorded step's stitch count is the compiler's count at that
                          step's last row, and every row declares its computed count.
  GARMENT_SHAPING         each shaping step changes the count by exactly what it says
                          (2 per event; 8 per raglan unit), within the rows it says.
  GARMENT_SEAM_MISMATCH   pieces sewn row to row have the same rows on both sides; edges sewn
                          by length agree within SEAM_TOLERANCE; a placed seam fits its edge.
  GARMENT_PICKUP_RATE     every picked-up band starts on exactly the stitches it says it picks
                          up, and those stitches at gauge are within MAX_PICKUP_DRIFT of the
                          edge's twin length (the pick-up rate the PDF prints).
  GARMENT_NECK_FIT        the neck opening sits on the shoulders: between NECK_MIN and
                          NECK_MAX of the body's cross-back (plus `cir.specification`'s yoke
                          plausibility for a raglan).
  GARMENT_ARMHOLE_FIT     the built armhole is at least the body's armhole depth and the
                          sleeve top at least the body's upper arm.
  GARMENT_FINISHED_OFF_TARGET  built chest within CHEST_TOLERANCE and length within
                          LENGTH_TOLERANCE of the target (body + ease).
  GARMENT_EASE_OUT_OF_BAND the built chest ease is inside the stated fit's band, at every size.
  GARMENT_YARDAGE_CLAIM   a size's stated metres, yards and balls are the twin's, recomputed.
  GARMENT_SIZE_CLAIM      every figure the size chart prints is the twin's, recomputed
                          (Product Truth for the size claims).
  GARMENT_STEPS_DIFFER    every size is the same steps in the same order (one design).
  GARMENT_SIZE_RUN        built chest rises strictly and yardage rises strictly size to size.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEAM_TOLERANCE = 0.06            # the assembler's own EDGE_TOLERANCE
CHEST_TOLERANCE = 0.05           # cir.graded.CHEST_TOLERANCE
LENGTH_TOLERANCE = 0.08          # whole rows on the shortest baby body move length ~5%
NECK_MIN, NECK_MAX = 0.55, 1.0   # neck width as a share of the body's cross-back
SAME_CM = 0.051


@dataclass
class GarmentFinding:
    code: str
    size: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} [{self.size}]: {self.message}"


@dataclass
class GarmentVerdict:
    findings: list[GarmentFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


def _f(out, code, size, msg):
    out.append(GarmentFinding(code, size, msg))


# ---- per size ----------------------------------------------------------------------------


def _counts(result) -> dict[tuple[str, int], int]:
    return {(r.component, r.index): r.stitch_count for r in result.rows}


def stitch_count_problems(cir, result, facts, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    counts = _counts(result)
    for comp in cir.components:
        for row in comp.rows:
            got = counts.get((comp.name, row.index))
            if row.declared_count is None or got != row.declared_count:
                _f(out, "GARMENT_STITCH_COUNT", size,
                   f"{comp.name} row {row.index} declares {row.declared_count}, the compiler "
                   f"counts {got}")
    for piece, steps in facts.pieces.items():
        for s in steps:
            if s.last < 1:
                continue
            got = counts.get((piece, s.last))
            if got != s.count:
                _f(out, "GARMENT_STITCH_COUNT", size,
                   f"{piece} {s.kind} ends on {s.count} sts at row {s.last}; the compiler "
                   f"counts {got}")
    return out


def shaping_problems(cir, result, facts, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    counts = _counts(result)
    for piece, steps in facts.pieces.items():
        before = steps[0].count
        for s in steps:
            if s.last < 1:
                before = s.count
                continue
            start = counts.get((piece, s.first - 1), before) if s.first > 1 else before
            rows = s.last - s.first + 1
            change = counts.get((piece, s.last), 0) - start
            if s.kind in ("inc", "dec"):
                times, every = s.get("times"), s.get("every")
                want = 2 * times * (1 if s.kind == "inc" else -1)
                if change != want or rows != (times - 1) * every + 1:
                    _f(out, "GARMENT_SHAPING", size,
                       f"{piece} rows {s.first}-{s.last}: {s.kind} {times} times every "
                       f"{every} rows should change the count by {want} over "
                       f"{(times - 1) * every + 1} rows; it changes by {change} over {rows}")
            elif s.kind == "raglan":
                units = s.get("singles") + 2 * s.get("doubles")
                if change != 8 * units:
                    _f(out, "GARMENT_SHAPING", size,
                       f"{piece} yoke: {units} raglan units should add {8 * units} sts; the "
                       f"rows add {change}")
            elif s.kind == "chain_on" and change != 2 * s.get("extra"):
                _f(out, "GARMENT_SHAPING", size, f"{piece}: chaining on {s.get('extra')} at "
                                                 f"each side adds {change}")
            elif s.kind == "leave" and change != -2 * s.get("leave"):
                _f(out, "GARMENT_SHAPING", size, f"{piece}: leaving {s.get('leave')} at each "
                                                 f"side removes {-change}")
            elif s.kind in ("even", "even_edge_rib", "neck_bridge", "buttonholes") and change:
                _f(out, "GARMENT_SHAPING", size, f"{piece} {s.kind} rows {s.first}-{s.last} "
                                                 f"change the count by {change}")
            before = s.count
    return out


def seam_problems(cir, result, twins, facts, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    for s in facts.seams:
        name = s["seam"]
        if "a_rows" in s:
            if s["a_rows"] != s["b_rows"]:
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"{name}: {s['a']} has {s['a_rows']} rows and {s['b']} {s['b_rows']}; "
                   f"sewn row to row they do not meet")
            if "a_edge_rows" in s and s["a_rows"] > min(s["a_edge_rows"], s["b_edge_rows"]):
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"{name}: {s['a_rows']} rows sewn on an edge of {s['a_edge_rows']}")
        if "a_sts" in s:
            if s["a_sts"] != s["b_sts"]:
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"{name}: {s['a_sts']} sts against {s['b_sts']}")
            if s["a_sts"] > min(s["a_edge_sts"], s["b_edge_sts"]) or s["a_sts"] < 1:
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"{name}: {s['a_sts']} sts sewn on an edge of {s['a_edge_sts']}")
        if "a_cm" in s:
            a, b = float(s["a_cm"]), float(s["b_cm"])
            drift = abs(a - b) / max(a, b, 1e-9)
            if drift > SEAM_TOLERANCE:
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"{name}: {s['a']} {a:.1f} cm against {s['b']} {b:.1f} cm "
                   f"({drift:.1%}, tolerance {SEAM_TOLERANCE:.0%})")
    # The generic assembler measures every join that names its edges, on the built pieces.
    from ..cir import assembly as _assembly

    geo = _assembly.assemble(cir, twins)
    for j in geo.mismatched_joins:
        _f(out, "GARMENT_SEAM_MISMATCH", size, j.why)
    # Pieces worked row-for-row against each other from their own compiled rows.
    if facts.construction in ("one_piece", "drop_shoulder"):
        rows = [r for r in result.rows if r.component == "body"]
        bridge = next((st for st in facts.pieces["body"] if st.kind == "neck_bridge"), None)
        if bridge is not None:
            front, back = bridge.first - 1, len(rows) - bridge.first
            if front != back:
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   f"side seam: the front half has {front} rows and the back half {back}")
            widths = [r.stitch_count for r in rows]
            if widths[:front] != list(reversed(widths[-back:])):
                _f(out, "GARMENT_SEAM_MISMATCH", size,
                   "the back half is not the front half row for row: the sleeves and sides "
                   "do not meet at the fold")
    return out


def pickup_problems(cir, result, twins, facts, g, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    counts = _counts(result)
    comps = {c.name: c for c in cir.components}
    st_cm = 10.0 / cir.gauge.stitches_per_10cm
    from ..products.garment_families import MAX_PICKUP_DRIFT

    for p in facts.pickups:
        comp = comps.get(p["piece"])
        if comp is None:
            _f(out, "GARMENT_PICKUP_RATE", size, f"{p['piece']} is not a piece")
            continue
        first = counts.get((comp.name, comp.rows[0].index))
        if comp.foundation != p["stitches"] or first != p["stitches"]:
            _f(out, "GARMENT_PICKUP_RATE", size,
               f"{comp.name} says it picks up {p['stitches']} sts; it starts on "
               f"{comp.foundation} and its first row counts {first}")
        # The edge, recomputed from the piece it is worked into.
        edge = _edge_cm(cir, twins, p, facts)
        if edge is None:
            _f(out, "GARMENT_PICKUP_RATE", size, f"{comp.name}: its edge has no length")
            continue
        made = p["stitches"] * st_cm
        drift = abs(made - edge) / edge
        if drift > MAX_PICKUP_DRIFT:
            _f(out, "GARMENT_PICKUP_RATE", size,
               f"{comp.name}: {p['stitches']} sts at gauge is {made:.1f} cm along a "
               f"{edge:.1f} cm edge ({drift:.1%}, at most {MAX_PICKUP_DRIFT:.0%}): the band "
               f"would ruffle or pull")
    return out


def _edge_cm(cir, twins, p, facts) -> float | None:
    into = twins.get(p["into"])
    if into is None:
        return None
    if facts.construction == "raglan":
        return into.height_cm                                   # hem to neck
    if p["piece"] == "cuff":
        return p["rows_along"] * into.height_cm / len(
            next(c for c in cir.components if c.name == p["into"]).rows)
    if p["piece"] == "neckband":
        from ..cir.assembly import openings_cm

        comp = next(c for c in cir.components if c.name == p["into"])
        ops = openings_cm(comp, cir.gauge)
        return 2 * ops[0] if ops else None
    return None


def neck_and_armhole_problems(cir, result, facts, g, measured, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    cross = g.body_cm("cross_back")
    if facts.construction in ("one_piece", "drop_shoulder", "side_to_side"):
        r = facts.neck_cm / cross
        if not NECK_MIN <= r <= NECK_MAX:
            _f(out, "GARMENT_NECK_FIT", size,
               f"the neck opening is {facts.neck_cm:.1f} cm, {r:.2f} of the {cross:g} cm "
               f"cross-back (between {NECK_MIN} and {NECK_MAX} sits on the shoulders)")
    else:
        from ..cir.specification import garment_implausibilities

        for why in garment_implausibilities(cir, cross_back_cm=cross):
            _f(out, "GARMENT_NECK_FIT", size, why)
    body_arm = g.body_cm("armhole_depth")
    if facts.armhole_cm + 1e-9 < body_arm:
        _f(out, "GARMENT_ARMHOLE_FIT", size,
           f"the armhole is {facts.armhole_cm:.1f} cm deep; the body's armhole depth is "
           f"{body_arm:g} cm")
    if facts.construction != "side_to_side":
        upper = measured.get("upper_arm")
        if upper is None or upper + 1e-9 < g.body_cm("upper_arm"):
            _f(out, "GARMENT_ARMHOLE_FIT", size,
               f"the sleeve is {upper} cm round at the top; the body's upper arm is "
               f"{g.body_cm('upper_arm'):g} cm")
    return out


def fit_problems(design, g, measured, size) -> list[GarmentFinding]:
    from ..cir.graded import FIT_EASE_BANDS_CM

    out: list[GarmentFinding] = []
    want = g.finished_cm("bust")
    chest = measured.get("chest")
    if chest is None or abs(chest - want) / want > CHEST_TOLERANCE:
        _f(out, "GARMENT_FINISHED_OFF_TARGET", size,
           f"built chest {chest} cm against the target {want:g} cm (body + ease), more than "
           f"{CHEST_TOLERANCE:.0%}")
    want_len = g.finished_cm("back_length")
    length = measured.get("length")
    if length is None or abs(length - want_len) / want_len > LENGTH_TOLERANCE:
        _f(out, "GARMENT_FINISHED_OFF_TARGET", size,
           f"built length {length} cm against the target {want_len:g} cm, more than "
           f"{LENGTH_TOLERANCE:.0%}")
    fit = design.fit.character
    if fit and chest is not None:
        lo, hi = FIT_EASE_BANDS_CM[fit]
        ease = chest - g.body_cm("bust")
        if not lo <= ease <= hi:
            _f(out, "GARMENT_EASE_OUT_OF_BAND", size,
               f"built chest ease {ease:.1f} cm is outside the {fit} band {lo:g}-{hi:g} cm")
    return out


# ---- the size chart and yardage claims (Product Truth for the sizes) --------------------


def size_claims(design, cirs: dict) -> list[dict]:
    """The figures the document prints per size, computed from each size's twin."""
    from ..cir.graded import measure_size
    from ..products.garment_families import balls_and_yards, built_measures

    rows = []
    for size, cir in cirs.items():
        g = design.graded_size(size)
        m = measure_size(cir, built_measures)
        built = m["built_cm"]
        rows.append({
            "size": size, "body_chest_cm": g.body_cm("bust"),
            "finished_chest_cm": built["chest"],
            "ease_cm": round(built["chest"] - g.body_cm("bust"), 1),
            "length_cm": built.get("length"), "upper_arm_cm": built.get("upper_arm"),
            **balls_and_yards(m["yarn_m"], cir.gauge.yarn_weight or "")})
    return rows


def claim_problems(design, cirs: dict, claims: list[dict]) -> list[GarmentFinding]:
    """Every printed figure, re-derived from the twin and compared (never trusted)."""
    out: list[GarmentFinding] = []
    truth = {r["size"]: r for r in size_claims(design, cirs)}
    if [c["size"] for c in claims] != list(truth):
        _f(out, "GARMENT_SIZE_CLAIM", "*", f"the chart lists {[c['size'] for c in claims]}; "
                                           f"the design builds {list(truth)}")
    for c in claims:
        t = truth.get(c["size"])
        if t is None:
            continue
        for k in ("body_chest_cm", "finished_chest_cm", "ease_cm", "length_cm",
                  "upper_arm_cm"):
            if (t.get(k) is None) != (c.get(k) is None) or (
                    t.get(k) is not None and abs(float(c[k]) - float(t[k])) > SAME_CM):
                _f(out, "GARMENT_SIZE_CLAIM", c["size"],
                   f"the chart prints {k} {c.get(k)}; the twin gives {t.get(k)}")
        for k in ("metres", "yards", "balls"):
            if c.get(k) != t.get(k):
                _f(out, "GARMENT_YARDAGE_CLAIM", c["size"],
                   f"the chart prints {c.get(k)} {k}; the twin's yarn is {t.get(k)} {k}")
    return out


# ---- the whole design --------------------------------------------------------------------


def evaluate(design, cirs: dict | None = None, *, claims: list[dict] | None = None,
             facts_by_size: dict | None = None) -> GarmentVerdict:
    """Every garment gate over every size. `cirs` defaults to building every sourced size;
    `claims` defaults to the computed chart (so only the per-size gates can fail)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..products.garment_families import built_measures, facts_of, step_signature

    v = GarmentVerdict()
    if cirs is None:
        cirs = {s: design.build(s) for s in design.sourced_sizes()}
    signatures = {}
    chests, yarns = [], []
    for size, cir in cirs.items():
        facts = (facts_by_size or {}).get(size) or facts_of(cir)
        if facts is None:
            _f(v.findings, "GARMENT_STEPS_DIFFER", size, "the size records no steps")
            continue
        result = compile_cir(cir)
        if not result.ok:
            _f(v.findings, "GARMENT_STITCH_COUNT", size,
               f"does not compile: {[str(e) for e in result.errors][:2]}")
            continue
        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        g = design.graded_size(size)
        measured = built_measures(cir)
        v.findings += stitch_count_problems(cir, result, facts, size)
        v.findings += shaping_problems(cir, result, facts, size)
        v.findings += seam_problems(cir, result, twins, facts, size)
        v.findings += pickup_problems(cir, result, twins, facts, g, size)
        v.findings += neck_and_armhole_problems(cir, result, facts, g, measured, size)
        v.findings += fit_problems(design, g, measured, size)
        signatures[size] = step_signature(cir)
        chests.append((size, measured.get("chest") or 0.0))
        yarns.append((size, sum(sum(t.yarn_metres_by_color.values()) * c.make
                                for c, t in ((c, twins[c.name]) for c in cir.components))))
    if len(set(signatures.values())) > 1:
        first = next(iter(signatures))
        odd = [s for s, sig in signatures.items() if sig != signatures[first]]
        _f(v.findings, "GARMENT_STEPS_DIFFER", ",".join(odd),
           f"sizes {odd} are worked in different steps from size {first}: several designs "
           f"sharing a name, which one document cannot write in parentheses")
    for (a, ca), (b, cb) in zip(chests, chests[1:]):
        if not cb > ca:
            _f(v.findings, "GARMENT_SIZE_RUN", b, f"built chest {ca:.1f} -> {cb:.1f} cm from "
                                                  f"{a} to {b} does not rise")
    for (a, ya), (b, yb) in zip(yarns, yarns[1:]):
        if not yb > ya:
            _f(v.findings, "GARMENT_SIZE_RUN", b, f"yarn {ya:.0f} -> {yb:.0f} m from {a} to "
                                                  f"{b} does not rise")
    if claims is not None:
        v.findings += claim_problems(design, cirs, claims)
    return v


# ---- the multi-size document, read back (its own grammar; shares nothing with the writer) --

import re as _re

_NUM = r"\d+(?:-\d+)?"
_VAL = rf"{_NUM}(?: \({_NUM}(?:, {_NUM})*\))?"


def _vals(text: str, n: int) -> list[str]:
    """`a` or `a (b, c, ...)` -> one value per size (n sizes)."""
    text = text.strip()
    m = _re.fullmatch(rf"({_NUM})(?: \(([^()]*)\))?", text)
    if not m:
        raise ValueError(f"not a size value: {text!r}")
    if m.group(2) is None:
        return [m.group(1)] * n
    out = [m.group(1)] + [x.strip() for x in m.group(2).split(",")]
    if len(out) != n:
        raise ValueError(f"{text!r} gives {len(out)} sizes, not {n}")
    return out


def _ints(text: str, n: int) -> list[int]:
    return [int(x) for x in _vals(text, n)]


def _span(text: str, n: int) -> list[tuple[int, int]]:
    out = []
    for v in _vals(text, n):
        a, _, b = v.partition("-")
        out.append((int(a), int(b or a)))
    return out


def _after(pattern: str, line: str, n: int) -> list[int]:
    m = _re.search(pattern.replace("V", f"({_VAL})"), line)
    if not m:
        raise ValueError(f"expected {pattern!r} in {line!r}")
    return _ints(m.group(1), n)


def read_line(line: str, n: int) -> dict:
    """One instruction line -> {"kind", per-size numbers, "rows", "counts"}."""
    out: dict = {"text": line}
    counts = _re.search(rf"\(({_VAL}) sts(?:, then ({_VAL}) sts)?\)$", line)
    if line.startswith("Set-up:"):
        out["kind"] = "setup"
        out["parts"] = [_ints(v, n) for v in _re.findall(
            rf"(?:sc|dc) ({_VAL}) \((?:front|sleeve|back)\)", line)]
        return out
    if _re.match(r"^Ch \d", line):
        out["kind"] = "chain"
        out["n"] = _after(r"^Ch V\.", line, n)
        return out
    if line.startswith("Pick up"):
        out["kind"] = "pick_up"
        out["n"] = _after(r"^Pick up V sts", line, n)
        return out
    if line.startswith("Rejoin"):
        out["kind"] = "resume"
        out["n"] = _after(r"the V held sts", line, n)
        return out
    m = _re.match(rf"^Rows? ({_VAL})", line)
    if not m or not counts:
        raise ValueError(f"an instruction with no rows or no stitch count: {line!r}")
    out["rows"] = _span(m.group(1), n)
    out["counts"] = _ints(counts.group(1), n)
    out["then"] = _ints(counts.group(2), n) if counts.group(2) else None
    if "raglan increase row" in line:
        out["kind"] = "raglan"
        out["doubles"] = (_after(r"work V double raglan", line, n)
                          if "double raglan" in line else [0] * n)
        out["every"] = _after(r"on every V row", line, n)
        out["times"] = _after(r"after it, V times in all", line, n)
    elif "1 st at each end" in line:
        out["kind"] = "inc" if "increase 1 st" in line else "dec"
        out["every"] = _after(r"of every V row", line, n)
        out["times"] = _after(r"after it, V times in all", line, n)
    elif "on the second row work" in line:
        out["kind"] = "chain_on"
        out["extra"] = _after(r"then ch V loosely", line, n)
    elif "leave them unworked" in line:
        out["kind"] = "leave"
        out["leave"] = _after(r"to the last V sts", line, n)
    elif "leave them on hold" in line:
        out["kind"] = "divide"
        out["front"] = _after(r"(?:sc|dc) V \(front\)", line, n)
        out["sleeve"] = _after(r"(?:sk|miss) V sleeve", line, n)
        out["back"] = _after(r"(?:sc|dc) V \(back\)", line, n)
    elif _re.search(r"\[ch 2, (?:sk|miss) 2 sts", line):
        out["kind"] = "buttonholes"
        out["first"] = _after(r"in the first V sts", line, n)
        out["between"] = _after(r"in the next V sts\]", line, n)
        out["holes"] = [h + 1 for h in _after(r"\] V times", line, n)]
        out["last"] = _after(r"in the last V sts", line, n)
    elif "loosely" in line and _re.search(r"(?:sk|miss) \d", line):
        out["kind"] = "bridge"
        sides = _re.findall(rf"(?:sc|dc) ({_VAL})", line)
        out["side"] = _ints(sides[0], n)
        out["neck"] = _after(r"ch V loosely", line, n)
    else:
        out["kind"] = "even"
    return out


def expand(parsed: list[dict], size: int) -> tuple[dict[int, int], list[str]]:
    """Per-row stitch counts for one size (index into the value lists), from text alone."""
    rows: dict[int, int] = {}
    problems: list[str] = []
    count = None
    expect = 1
    for p in parsed:
        k = p["kind"]
        if k in ("chain",):
            count = p["n"][size] - 1
            continue
        if k in ("pick_up", "resume"):
            count = p["n"][size]
            continue
        if k == "setup":
            continue
        a, b = p["rows"][size]
        if a != expect:
            problems.append(f"rows jump from {expect - 1} to {a} at {p['text'][:50]!r}")
        expect = b + 1
        printed = p["counts"][size]
        if count is None:
            problems.append(f"{p['text'][:40]!r} has no stitches to work into")
            count = printed
        if k == "even":
            for r in range(a, b + 1):
                rows[r] = count
        elif k in ("inc", "dec"):
            every, times = p["every"][size], p["times"][size]
            if b - a + 1 != (times - 1) * every + 1:
                problems.append(f"rows {a}-{b} do not hold {times} shapings every {every}")
            for r in range(a, b + 1):
                if (r - a) % every == 0 and (r - a) // every < times:
                    count += 2 if k == "inc" else -2
                rows[r] = count
        elif k == "raglan":
            d, every, times = p["doubles"][size], p["every"][size], p["times"][size]
            for i, r in enumerate(range(a, b + 1)):
                if i < d:
                    count += 16
                elif (i - d) % every == 0 and (i - d) // every < times:
                    count += 8
                rows[r] = count
        elif k == "chain_on":
            count += p["extra"][size]
            rows[a] = count
            count += p["extra"][size]
            rows[b] = count
            if p["then"] is None or p["then"][size] != count or printed != rows[a]:
                problems.append(f"chain-on counts printed {printed}/{p['then']} vs {rows[a]}"
                                f"/{count}")
            continue
        elif k == "leave":
            count -= p["leave"][size]
            rows[a] = count
            count -= p["leave"][size]
            rows[b] = count
            if p["then"] is None or p["then"][size] != count or printed != rows[a]:
                problems.append(f"leave counts printed {printed}/{p['then']} vs {rows[a]}"
                                f"/{count}")
            continue
        elif k == "divide":
            count = 2 * p["front"][size] + p["back"][size]
            rows[a] = count
        elif k == "bridge":
            if 2 * p["side"][size] + p["neck"][size] != count:
                problems.append(f"the shoulder row works {2 * p['side'][size]} + "
                                f"{p['neck'][size]} of {count} sts")
            rows[a] = count
        elif k == "buttonholes":
            h = p["holes"][size]
            made = (p["first"][size] + p["between"][size] * (h - 1) + p["last"][size]
                    + 2 * h)
            if made != count:
                problems.append(f"the buttonhole row makes {made} of {count} sts")
            rows[a] = count
        if rows[b] != printed:
            problems.append(f"{p['text'][:50]!r}: the rows end on {rows[b]} sts; the line "
                            f"prints {printed}")
    return rows, problems


def multi_size_problems(pieces_text: dict[str, list[str]], cirs: dict,
                        piece_of: dict[str, str]) -> list[GarmentFinding]:
    """Read the parenthesised document back per size and compare every row with the compiler.

    `pieces_text` is {piece heading: instruction lines} as printed; `piece_of` maps each
    heading to the component it instructs."""
    from ..cir.compiler import compile_cir

    out: list[GarmentFinding] = []
    sizes = list(cirs)
    n = len(sizes)
    results = {s: compile_cir(c) for s, c in cirs.items()}
    for heading, lines in pieces_text.items():
        comp = piece_of.get(heading)
        if comp is None:
            _f(out, "GARMENT_DOCUMENT", "*", f"heading {heading!r} names no piece")
            continue
        try:
            parsed = [read_line(line, n) for line in lines]
        except ValueError as exc:
            _f(out, "GARMENT_DOCUMENT", "*", f"{heading}: {exc}")
            continue
        for i, size in enumerate(sizes):
            rows, problems = expand(parsed, i)
            for p in problems:
                _f(out, "GARMENT_DOCUMENT", size, f"{heading}: {p}")
            built = {r.index: r.stitch_count for r in results[size].rows if r.component == comp}
            if set(rows) != set(built):
                _f(out, "GARMENT_DOCUMENT", size,
                   f"{heading}: the text covers rows {min(rows, default=0)}-"
                   f"{max(rows, default=0)}; the piece has rows 1-{max(built, default=0)}")
            for r, c in sorted(rows.items()):
                if built.get(r) != c:
                    _f(out, "GARMENT_DOCUMENT", size,
                       f"{heading} row {r}: the text gives {c} sts, the compiler {built.get(r)}")
                    break
            setup = next((p for p in parsed if p["kind"] == "setup"), None)
            if setup is not None and setup["parts"]:
                total = sum(v[i] for v in setup["parts"])
                if total != built.get(1):
                    _f(out, "GARMENT_DOCUMENT", size,
                       f"{heading}: the set-up markers divide {total} sts; row 1 has "
                       f"{built.get(1)}")
    return out
