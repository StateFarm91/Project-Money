"""Independent instruction draft: the spec is frozen before the writer runs (F-792).

A competitor-informed design (`Provenance.benchmarks_consulted`) may have been shaped by
research on somebody else's pattern. The publishable instructions must come from
Brambleloop's own CIR and design record, never from that pattern's prose, and the competitor
file must be out of the instruction-writing context once the specification is frozen.

Two deterministic halves:

* **The freeze.** Immediately before the writer runs on a competitor-informed release, the
  CIR's fingerprint is recorded in the append-only audit log (`FREEZE_ACTION`) with the
  writer's inputs and the benchmark references excluded from them. The first freeze of a
  slug@version is the spec; a later certification of the same slug@version whose CIR no
  longer matches it is `SPEC_CHANGED_AFTER_FREEZE` -- the design moved after its
  instructions were drafted, which is how a "small fix" copied in from the benchmark would
  arrive.
* **The writer's context.** `cir.writer.write_pattern` takes the CIR, its compile result and
  layout numbers, and nothing else; its module imports nothing that can reach the benchmark
  library, teardown readings or market intelligence. `writer_context_problems` checks both
  from the source, so a later edit that hands the writer a benchmark is a refused release
  rather than a convention somebody forgot.
"""
from __future__ import annotations

import ast
import functools
import inspect

from ..cir.compiler import ERROR, Finding

FREEZE_ACTION = "originality.spec_freeze"
# What the writer may be given. Anything else is a new input someone has to justify here.
WRITER_PARAMETERS: tuple[str, ...] = ("cir", "result", "terminology", "width_cm", "height_cm")
# Packages whose contents can carry a competitor's pattern or its readings.
FORBIDDEN_WRITER_IMPORTS: tuple[str, ...] = ("teardown", "intel", "research", "benchmark",
                                             "gateway", "radar")


def consulted(cir) -> tuple[str, ...]:
    prov = getattr(cir, "provenance", None)
    return tuple(getattr(prov, "benchmarks_consulted", ()) or ())


@functools.lru_cache(maxsize=1)
def writer_context_problems() -> tuple[str, ...]:
    """Why the instruction writer's context could include benchmark material. Empty is clean."""
    from ..cir import writer

    problems: list[str] = []
    params = tuple(inspect.signature(writer.write_pattern).parameters)
    extra = [p for p in params if p not in WRITER_PARAMETERS]
    if extra:
        problems.append(f"write_pattern takes {extra}, beyond the CIR and its compile result")
    tree = ast.parse(inspect.getsource(writer))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom):
            names = [node.module or ""] + [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            if any(part in FORBIDDEN_WRITER_IMPORTS for part in name.lower().split(".")):
                problems.append(f"cir/writer.py imports {name!r}, which can reach benchmark "
                                f"material")
    return tuple(problems)


def _artifact(cir) -> str:
    return f"{cir.slug}@{cir.version}"


def frozen(db, cir) -> list[dict]:
    """Every freeze of this slug@version, oldest first."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == FREEZE_ACTION, AuditLog.artifact == _artifact(cir))
            .order_by(AuditLog.at, AuditLog.id)))
        return [{"at": r.at.isoformat() if r.at else None, **(r.detail or {})} for r in rows]


def freeze(db, cir, *, actor: str = "release_chain") -> dict:
    """Record the spec the instructions are about to be written from (idempotent per CIR)."""
    from ..core.models import AuditLog

    fp = cir.fingerprint
    for f in frozen(db, cir):
        if f.get("fingerprint") == fp:
            return f
    detail = {"fingerprint": fp, "writer_inputs": list(WRITER_PARAMETERS),
              "excluded_from_writer": list(consulted(cir)),
              "writer_context_problems": list(writer_context_problems())}
    with db.session() as s:
        s.add(AuditLog(actor=actor, action=FREEZE_ACTION, artifact=_artifact(cir),
                       detail=detail))
    return detail


def findings(cir, db=None) -> list[Finding]:
    """F-792 for one release. Only competitor-informed designs carry the obligation."""
    if getattr(cir, "authored", "brambleloop") != "brambleloop" or not consulted(cir):
        return []
    out = [Finding(ERROR, "WRITER_CONTEXT_NOT_INDEPENDENT", f"{p} (F-792)")
           for p in writer_context_problems()]
    if db is None:
        return out          # release_findings already refuses a consulted design without db
    history = frozen(db, cir)
    if not history:
        out.append(Finding(ERROR, "SPEC_NOT_FROZEN",
                           f"{_artifact(cir)} is competitor-informed and no specification "
                           f"freeze precedes its instructions (F-792)"))
    elif history[0].get("fingerprint") != cir.fingerprint:
        out.append(Finding(ERROR, "SPEC_CHANGED_AFTER_FREEZE",
                           f"{_artifact(cir)} was frozen at {history[0].get('at')} as "
                           f"{str(history[0].get('fingerprint'))[:12]} and is now "
                           f"{cir.fingerprint[:12]}: the design changed after its "
                           f"instructions were drafted; bump the version (F-792)"))
    return out
