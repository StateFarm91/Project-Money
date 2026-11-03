"""A6 x I-A6-FROZEN-KNOWLEDGE-CONTRACT: approved design knowledge enters a design only frozen,
and every boundary that accepts the design re-verifies it (opus2; Codex owns the store).

Codex's `improve.design_knowledge` is the ONE approval authority for design rules: an
independently reviewed, held-out-evaluated DesignRule, pinned as {rule_id, rule_version,
rule_digest, evaluation_digest}. This module is Pattern Engineering's side of that contract.

* `freeze_applicable(db, cir)` -- at drafting: the approved records for the writer sections
  this drafter can honour are frozen into the CIR's provenance (`design_knowledge.freeze_pins`,
  `learning_rule:...` markers). No approved record: the CIR is returned unchanged, so a
  design with no knowledge is byte-identical to before. A store failure freezes nothing.
* `refusal(db, cir)` -- at certification, re-verification, the PDF and release: None for a
  CIR that carries no pins; otherwise `design_knowledge.verify_cir_pins`, and ANY failure --
  forged, stale, revoked, unevaluated, unreadable store -- is a named refusal. A pinned
  design is never silently rendered without the knowledge it was certified with.
"""
from __future__ import annotations

FROZEN = "design_knowledge.frozen"
REFUSED = "design_knowledge.pins_refused"


def has_pins(cir) -> bool:
    from ..cir import knowledge

    prov = getattr(cir, "provenance", None)
    return bool(prov is not None and any(
        isinstance(p, str) and p.startswith(knowledge.PREFIX)
        for p in (getattr(prov, "primitives_used", None) or ())))


def freeze_applicable(db, cir):
    """(cir, records): the CIR with every applicable approved record frozen into it."""
    from . import design_knowledge as dk

    if getattr(cir, "provenance", None) is None:
        return cir, []                 # nothing to freeze into; the writer stays baseline
    try:
        records = list(dk.applicable_to_cir(db, cir))
    except Exception:  # noqa: BLE001 - an unreadable store freezes nothing
        return cir, []
    if not records:
        return cir, []
    try:
        return dk.freeze_pins(db, cir, [r["pin"] for r in records]), records
    except dk.DesignKnowledgeRefused:
        return cir, []


def refusal(db, cir) -> str | None:
    if not has_pins(cir):
        return None
    from . import design_knowledge as dk

    try:
        dk.verify_cir_pins(db, cir)
        return None
    except Exception as exc:  # noqa: BLE001 - any unverifiable pin refuses (fail closed)
        return (f"frozen design knowledge does not verify ({type(exc).__name__}: "
                f"{str(exc)[:240]}); a pinned design is never accepted or rendered without it")
