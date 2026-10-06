"""Lesson swatches are compiled and reverse-compiled exactly like patterns (F-805).

Master v0.24 F-805: tutorial instructions are tested like patterns -- counts, stitch semantics,
hook/yarn assumptions and terminology must reconcile with the canonical lesson specification.
`validate_spec` already checks each single step against `cir.stitches`. A lesson that teaches
over several rows (a practice swatch) was not checked at all beyond that. This holds a swatch to
the pattern pipeline itself:

1. the swatch is a CIR (`cir.model.CIR.from_dict`), not prose;
2. every row declares its stitch total and `cir.compiler.compile_cir` must agree with every
   one -- a wrong row total is a refusal, the same COUNT_MISMATCH a pattern gets;
3. the customer-facing text is written by `cir.writer.write_pattern` in the lesson's
   terminology and must reverse-compile (`cir.reverse.compare`) back to the same CIR; a
   hand-supplied `text` is held to the same comparison, so an edited instruction is caught;
4. every stitch a step teaches is worked in the swatch, and the swatch's hook and yarn weight,
   where it states them, are the lesson's stated assumptions.

Nothing here approves a lesson: a clean swatch is necessary, never sufficient.
"""
from __future__ import annotations


def _walk_codes(nodes) -> set[str]:
    out: set[str] = set()
    for node in nodes or []:
        if isinstance(node, dict):
            if isinstance(node.get("stitch"), str):
                out.add(node["stitch"])
            out |= _walk_codes(node.get("ops"))
    return out


def problems(spec: dict) -> list[str]:
    """Refusal reasons for the spec's `swatch`, or [] when it is absent or reconciles."""
    swatch = spec.get("swatch")
    if swatch is None:
        return []
    if not isinstance(swatch, dict) or not isinstance(swatch.get("cir"), dict):
        return ["swatch must be an object carrying a CIR under 'cir'"]
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.reverse import compare
    from ..cir.writer import write_pattern

    terminology = spec.get("terminology", "US")
    try:
        cir = CIR.from_dict(swatch["cir"])
    except (KeyError, TypeError, ValueError) as exc:
        return [f"swatch is not a valid CIR: {type(exc).__name__}: {str(exc)[:160]}"]
    errors = []
    rows = [row for _comp, row in cir.iter_rows()]
    if len(rows) < 2:
        errors.append("a swatch is multi-row; a single row is taught as steps")
    if any(row.declared_count is None for row in rows):
        errors.append("every swatch row must declare its stitch total")
    result = compile_cir(cir)
    for finding in result.errors:
        errors.append(f"swatch {finding.code}: {finding.message}")
    if errors:
        return errors
    try:
        written = write_pattern(cir, result, terminology)
    except (KeyError, ValueError) as exc:
        return [f"swatch cannot be written in {terminology} terms: {exc}"]
    for finding in compare(cir, written, terminology):
        if finding.is_error:
            errors.append(f"swatch written text {finding.code}: {finding.message}")
    supplied = swatch.get("text")
    if supplied is not None:
        if not isinstance(supplied, str):
            errors.append("swatch text must be a string")
        else:
            for finding in compare(cir, supplied, terminology):
                if finding.is_error:
                    errors.append(f"swatch text disagrees with its CIR {finding.code}: "
                                  f"{finding.message}")
    worked = set()
    for comp in swatch["cir"].get("components") or []:
        for row in comp.get("rows") or []:
            worked |= _walk_codes(row.get("ops"))
    taught = {step.get("stitch") for step in spec.get("steps") or [] if isinstance(step, dict)}
    missing = sorted(t for t in taught if t and t not in worked)
    if missing:
        errors.append(f"swatch does not work the stitch(es) the steps teach: {missing}")
    assumptions = spec.get("assumptions") or {}
    if cir.gauge is not None and cir.gauge.hook_mm is not None and \
            float(cir.gauge.hook_mm) != float(assumptions.get("hook_mm") or 0):
        errors.append(f"swatch hook {cir.gauge.hook_mm} mm is not the lesson's stated "
                      f"{assumptions.get('hook_mm')} mm")
    weights = {m.yarn_weight for m in cir.materials if m.yarn_weight}
    if weights and weights != {assumptions.get("yarn_weight")}:
        errors.append(f"swatch yarn weight {sorted(weights)} is not the lesson's stated "
                      f"{assumptions.get('yarn_weight')!r}")
    return errors


def written(spec: dict) -> str | None:
    """The customer-facing swatch text, written from the CIR (never served hand-typed)."""
    swatch = spec.get("swatch")
    if not isinstance(swatch, dict) or problems(spec):
        return None
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.writer import write_pattern

    cir = CIR.from_dict(swatch["cir"])
    return write_pattern(cir, compile_cir(cir), spec.get("terminology", "US"))
