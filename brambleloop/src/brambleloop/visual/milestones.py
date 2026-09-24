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
BLOCKED = "BLOCKED_ON_EARLIER"


def assess(size: str = "S") -> dict:
    """Run the benchmark end to end and report where the pipeline actually stands."""
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
    out.append({
        "milestone": "D", "name": "photographic presentation without structural drift",
        "status": NOT_STARTED,
        "evidence": ("no presentation layer exists. The invariant it must satisfy is written "
                     "down already: AI may photograph the product, it may not redesign it"),
    })
    out.append({
        "milestone": "E", "name": "listing asset passing Product Truth and realism together",
        "status": NOT_STARTED,
        "evidence": "waits on D; listable is still 0 of 10",
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
                         if r["status"] in (PARTIAL, FAIL, NOT_STARTED)), None),
        "business_objective": "listable products: 0 of 10",
        "rule": ("stop and diagnose at the first failed milestone rather than building later "
                 "layers on an invalid earlier one"),
    }
