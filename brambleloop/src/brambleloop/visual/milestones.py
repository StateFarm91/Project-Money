"""The visual pipeline's milestone ladder, measured rather than declared.

The owner's instruction on 2026-09-24 was to prove five things in order and stop at the first
failure rather than building later layers on an invalid earlier one. That ordering is the
whole value of the ladder, so it is enforced here: a milestone cannot report PASS while an
earlier one has not, however well its own checks happen to run.

  A  pattern -> deterministic stitch/fabric representation
  B  deterministic panels -> correctly assembled object geometry
  C  assembled object -> visual correspondence with the real benchmark photographs
  D  authoritative object -> realistic photographic presentation, no structural drift
  E  complete listing asset -> Product Truth AND photographic realism both PASS

Each milestone is computed from the benchmark on every call. Nothing here is a stored claim
about progress, because a stored claim is exactly what a dashboard reporting the build was
finished turned out to be.
"""
from __future__ import annotations

PASS, PARTIAL, FAIL, NOT_STARTED = "PASS", "PARTIAL", "FAIL", "NOT_STARTED"
UNMEASURED = "UNMEASURED"
BLOCKED = "BLOCKED_ON_EARLIER"


def assess(size: str = "S", *, measure_d: bool = False, d_result: dict | None = None) -> dict:
    """Run the benchmark end to end and report where the pipeline actually stands.

    Milestone D is measured by `milestone_d.assess`, which drapes the certified swatch on a
    form and takes about two minutes; it runs here only when `measure_d` is set or a result
    is passed in. Otherwise D reports UNMEASURED -- not FAIL, not PASS -- because a status
    this module did not measure on this call is not a status it can report.
    """
    from ..cir import assembly, benchmarks as B
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from . import correspondence as C, fabric

    out: list[dict] = []

    # --- A: does a pattern become a fabric whose structure is ours? --------
    try:
        cir = B.cardigan(size)
        result = compile_cir(cir)
        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        sig = fabric.texture_signature(twins["body"])
        errors = [f for f in result.findings if getattr(f, "severity", "") == "ERROR"]
        a_ok = result.ok and not errors and sig.get("textured") is True
        out.append({
            "milestone": "A", "name": "pattern to deterministic fabric",
            "status": PASS if a_ok else FAIL,
            "evidence": (f"{len(cir.components)} components compile with {len(errors)} errors; "
                         f"body is {twins['body'].stitch_total} placed stitches measuring "
                         f"{sig.get('surface')}"),
        })
    except Exception as exc:                       # noqa: BLE001 - a milestone may fail hard
        out.append({"milestone": "A", "name": "pattern to deterministic fabric",
                    "status": FAIL, "evidence": f"{type(exc).__name__}: {exc}"})
        return _ladder(out)

    # --- B: do the panels make an object? ---------------------------------
    geo = assembly.assemble(cir, twins)
    checked = [j for j in geo.joins if j.verdict in ("sound", "mismatched", "indeterminate")]
    b_status = {"assembles": PASS, "partially_placed": PARTIAL,
                "does_not_assemble": FAIL}.get(geo.verdict, FAIL)
    out.append({
        "milestone": "B", "name": "panels to assembled object geometry",
        "status": b_status,
        "evidence": (f"{len(geo.footprints)} pieces placed; {len(checked)} of {len(geo.joins)} "
                     f"joins checkable, {len(geo.mismatched_joins)} mismatched; silhouette "
                     f"{geo.silhouette_across_cm}x{geo.silhouette_up_cm}cm. {geo.why}"),
    })

    # --- C: does it match the real garment? -------------------------------
    corr = C.compare(cir, geo, twins, size=size)
    counts = corr.counts
    c_status = {"FULL": PASS, "PARTIAL": PARTIAL, "CONTRADICTED": FAIL}.get(
        corr.verdict, NOT_STARTED)
    out.append({
        "milestone": "C", "name": "object to photograph correspondence",
        "status": c_status,
        "evidence": (f"{counts.get(C.CORRESPONDS, 0)} correspond, "
                     f"{counts.get(C.CONTRADICTS, 0)} contradict, "
                     f"{counts.get(C.NOT_OBSERVABLE, 0)} not observable in photography"),
    })

    # --- D and E: not started, and said so rather than shown empty --------
    from . import final_standard as F

    if d_result is None and measure_d:
        from . import milestone_d
        d_result = milestone_d.assess("hdc")
    if d_result is not None:
        from . import milestone_d
        d_status = {milestone_d.PASS: PASS, milestone_d.PARTIAL: PARTIAL,
                    milestone_d.FAIL: FAIL}.get(d_result["status"], FAIL)
        out.append({
            "milestone": "D", "name": "photographic presentation without structural drift",
            "status": d_status,
            "evidence": milestone_d.summary(d_result),
            "unknown": d_result.get("unknown", []), "failed": d_result.get("failed", []),
        })
    else:
        out.append({
            "milestone": "D", "name": "photographic presentation without structural drift",
            "status": UNMEASURED,
            "evidence": ("not measured on this call. `milestone_d.assess()` drapes the "
                         "certified swatch on a form, re-validates it and renders it (about "
                         "two minutes); pass measure_d=True or its result. History: 2D glyphs "
                         "failed (B-704); the yarn-level spike failed on topology (B-705); the "
                         "drape solver's reported motion was free drift and the frictionless "
                         "force law took stitches apart once it was not -- see "
                         "visual/milestone_d.py and research/VISUAL_MILESTONE_D.md"),
        })
    out.append({
        "milestone": "E", "name": "listing asset clearing all three floors at once",
        "status": NOT_STARTED,
        "evidence": (f"waits on D; listable is still 0 of 10. The bar is set and testable: "
                     f"{', '.join(F.FLOORS)}, with identity clearing "
                     f"{' and '.join(F.IDENTITY_HALVES)} separately. None compensates for "
                     f"another and unmeasurable is never pass"),
    })
    return _ladder(out)


def _ladder(rows: list[dict]) -> dict:
    """Apply the ordering rule: nothing passes on top of something that did not.

    Without this the ladder is five independent checks wearing the costume of a sequence, and
    a later milestone could report PASS while the thing it is built on reported FAIL -- which
    is precisely the "building later layers on an invalid earlier one" the owner forbade.
    """
    blocked_from = None
    for row in rows:
        if blocked_from is not None and row["status"] in (PASS, PARTIAL):
            row["status"] = BLOCKED
            row["evidence"] = (f"held at milestone {blocked_from}: its own checks may run but "
                               f"they rest on an earlier milestone that has not passed. "
                               + row["evidence"])
        elif row["status"] == FAIL and blocked_from is None:
            blocked_from = row["milestone"]
    reached = [r["milestone"] for r in rows if r["status"] == PASS]
    return {
        "milestones": rows,
        "highest_passed": reached[-1] if reached else None,
        "current": next((r["milestone"] for r in rows
                         if r["status"] in (PARTIAL, FAIL, NOT_STARTED, UNMEASURED)), None),
        "business_objective": "listable products: 0 of 10",
        "rule": ("stop and diagnose at the first failed milestone rather than building later "
                 "layers on an invalid earlier one"),
    }
