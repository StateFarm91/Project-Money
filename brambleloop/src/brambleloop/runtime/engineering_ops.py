"""Product Development: `cir.revise` (crochet_engineer) -- W4-AGENTS department batch 3.

Before this, a CIR that failed `cir.compile` simply died there ("the concept dies here") and
`cir.revise` was a permission with no handler. Now a failed compile is handed back to the
Crochet Engineer once, with the compiler's findings, and the engineer applies only repair
rules that change *declared geometry parameters* and never the design's idea -- then the
revised CIR goes back through `cir.compile` -> `gate.certify` exactly like a new draft.
Deterministic validation still decides: a revision is a candidate, nothing more.

Like `cir.draft`, this is deterministic (the draft path calls no model; Master Plan s2 forbids
asking a model to supply instructions). No model, no network, CA$0 -- well inside the
crochet_engineer CA$4.00 daily ceiling, which stays the bound if a model rule is ever added.

Rules (each one names the finding it answers):

* `REPEAT_DIVISIBILITY` -- answers compiler `REPEAT`/`COUNT_MISMATCH` on a uniform-width flat
  panel (the `concept_to_cir` shape: plain rows of W stitches alternating with a to-end
  repeat of unit u). W becomes the nearest multiple of u (ties upward, at least u); every
  plain row, declared count and the foundation move together. The width change is recorded.

Anything else is recorded as UNREPAIRABLE with its finding codes -- honest, and a lesson for
`improve.mine` -- rather than guessed at.
"""
from __future__ import annotations

import copy

from .worker import JobContext, handlers

MAX_REVISIONS = 1


def _unit(node) -> int | None:
    from ..cir.model import Op, Repeat

    if isinstance(node, Repeat) and node.times is None and all(isinstance(o, Op)
                                                               for o in node.ops):
        return sum(int(o.count) for o in node.ops)
    return None


def repair_repeat_divisibility(cir) -> tuple[object | None, dict]:
    """The REPEAT_DIVISIBILITY rule. (revised CIR or None, what it did / why not)."""
    from ..cir.model import Op

    if len(cir.components) != 1:
        return None, {"why": "rule covers single-panel CIRs only"}
    comp = cir.components[0]
    if comp.construction != "flat_rows" or not comp.rows:
        return None, {"why": "rule covers flat-row panels only"}
    widths, units = set(), set()
    for row in comp.rows:
        if len(row.ops) != 1:
            return None, {"why": f"row {row.index} is not a single plain op or repeat"}
        node = row.ops[0]
        if isinstance(node, Op):
            widths.add(int(node.count))
        else:
            u = _unit(node)
            if u is None:
                return None, {"why": f"row {row.index} repeat is not a plain to-end repeat"}
            units.add(u)
        if row.declared_count is not None:
            widths.add(int(row.declared_count))
    if comp.foundation:
        widths.add(int(comp.foundation))
    if len(widths) != 1 or len(units) != 1:
        return None, {"why": f"not a uniform panel (widths {sorted(widths)}, units "
                             f"{sorted(units)})"}
    (w,), (u,) = widths, units
    if w % u == 0:
        return None, {"why": f"width {w} already divides by the repeat unit {u}"}
    lower, upper = (w // u) * u, (w // u + 1) * u
    new_w = upper if (upper - w) <= (w - lower) or lower < u else lower
    revised = copy.deepcopy(cir)
    rc = revised.components[0]
    for row in rc.rows:
        node = row.ops[0]
        if isinstance(node, Op):
            node.count = new_w
        if row.declared_count is not None:
            row.declared_count = new_w
    if rc.foundation:
        rc.foundation = new_w
    return revised, {"rule": "REPEAT_DIVISIBILITY", "width_from": w, "width_to": new_w,
                     "unit": u, "rows_changed": len(rc.rows),
                     "note": "finished width changes accordingly; certification re-derives "
                             "size and yardage from the revised CIR"}


RULES = (("REPEAT_DIVISIBILITY", ("REPEAT", "COUNT_MISMATCH", "UNDERRUN", "OVERRUN"),
          repair_repeat_divisibility),)


@handlers.register("cir.revise")
def handle_cir_revise(ctx: JobContext) -> dict:
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR

    i = dict(ctx.job.inputs or {})
    if not isinstance(i.get("cir"), dict):
        return {"ran": False, "why": "cir.revise needs the failed CIR"}
    cir = CIR.from_dict(i["cir"])
    revision = int(i.get("revision") or 0) + 1
    if revision > MAX_REVISIONS:
        return {"ran": False, "why": f"revision limit {MAX_REVISIONS} reached; the concept "
                                     f"stops here"}
    result = compile_cir(cir)
    if result.ok:
        return {"ran": False, "why": "the CIR compiles; nothing to revise"}
    codes = sorted({f.code for f in result.errors})
    artifact = f"{cir.slug}@{cir.version}"
    for name, answers, rule in RULES:
        if not set(codes) & set(answers):
            continue
        revised, what = rule(cir)
        if revised is None:
            continue
        check = compile_cir(revised)
        ctx.audit("cir.revised", artifact=artifact,
                  detail={"rule": name, "codes": codes, **what, "compiles": check.ok,
                          "from_fingerprint": cir.fingerprint,
                          "to_fingerprint": revised.fingerprint, "revision": revision})
        if not check.ok:
            continue
        # Back through the ordinary chain: compile, then certify. Literal job type so the
        # autonomy map sees the edge.
        ctx.enqueue("validator", "cir.compile",
                    {"cir": revised.to_dict(), "revision": revision,
                     "revision_of": cir.fingerprint},
                    idempotency_key=f"compile:{revised.slug}:{revised.version}:"
                                    f"{revised.fingerprint}")
        return {"artifact": artifact, "revised": True, "rule": name, "codes": codes,
                "detail": what, "work_done": 1}
    ctx.audit("cir.revise_unrepairable", artifact=artifact,
              detail={"codes": codes, "errors": [str(f)[:160] for f in result.errors][:10],
                      "rules_tried": [n for n, _, _ in RULES], "revision": revision})
    return {"artifact": artifact, "revised": False, "unrepairable": True, "codes": codes,
            "work_done": 1}


@handlers.register("creative.family_engine")
def handle_family_engine(ctx: JobContext) -> dict:
    """Product Family Engine (creative_director): the certified catalogue's families, bundle
    readiness, recolour duplicates, next members and evidence-gated amplification. Reads our
    own rows only; one reading a day; creates no product. Deterministic, CA$0."""
    from ..creative.family_engine import family_report
    from .etsy_ops import store_reading

    rep = family_report(ctx.db)
    if not rep["certified"]:
        return {"ran": False, "why": "no certified release to group into families"}
    store_reading(ctx.db, "creative.family_engine", rep)
    ctx.audit("creative.family_engine", detail={
        "families": len(rep["families"]), "singles": len(rep["single_products"]),
        "bundle_ready": rep["portfolio_has_bundle_ready_family"],
        "recolour_duplicates": rep["recolour_duplicates"][:5]})
    return {"families": len(rep["families"]), "single_products": len(rep["single_products"]),
            "portfolio_has_bundle_ready_family": rep["portfolio_has_bundle_ready_family"],
            "recolour_duplicates": len(rep["recolour_duplicates"]),
            "work_done": len(rep["families"]) + len(rep["single_products"])}
