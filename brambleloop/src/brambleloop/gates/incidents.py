"""Incident correlation (Master Plan section 10, acceptance Gate E).

One customer confused at round 14 is a support case. Three customers confused at round 14 is a
defect, and the pattern -- not the customer -- is wrong. Correlation is what turns the second
situation into a halt instead of three cheerful individual replies.

Support can raise incidents and answer from the canonical pattern. Support cannot edit the
canonical pattern; only a re-validated CIR release can do that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select

from ..core.db import Database
from ..core.models import Incident, utcnow

# How many independent reports of the same signature before it stops being a coincidence.
DEFECT_THRESHOLD = 3
# The company-wide escalation row (`ops.incident_lifecycle.SYSTEMIC_SIGNATURE` family).
SYSTEMIC_PREFIX = "systemic-halt:"


class SupportCannotPatchPatterns(PermissionError):
    """Raised if support code attempts to mutate a canonical pattern version."""


@dataclass
class DefectReport:
    product_slug: str
    pattern_version: str
    component: str | None
    row: int | None
    customer_ref: str
    text: str


def signature(report: DefectReport) -> str:
    """Group reports that are plausibly the same underlying defect."""
    if report.row is not None:
        return f"{report.product_slug}@{report.pattern_version}:{report.component or '-'}:row{report.row}"
    key = re.sub(r"[^a-z ]", "", report.text.lower())
    key = " ".join(sorted(set(key.split()) - {"the", "a", "is", "i", "to", "of", "on", "at"}))[:60]
    return f"{report.product_slug}@{report.pattern_version}:text:{key}"


class IncidentTracker:
    def __init__(self, db: Database, threshold: int = DEFECT_THRESHOLD):
        self.db = db
        self.threshold = threshold

    def report(self, report: DefectReport) -> Incident:
        """File a defect report; correlate it into an existing incident when it matches."""
        sig = signature(report)
        with self.db.session() as s:
            inc = s.scalar(
                select(Incident).where(Incident.signature == sig, Incident.resolved == False)  # noqa: E712
            )
            if inc is None:
                inc = Incident(
                    signature=sig,
                    product_slug=report.product_slug,
                    summary=report.text[:500],
                    severity="P2",
                    report_count=1,
                    detail={"reports": [report.customer_ref],
                            "row": report.row, "component": report.component,
                            "pattern_version": report.pattern_version},
                )
                s.add(inc)
            else:
                inc.report_count += 1
                detail = dict(inc.detail or {})
                refs = list(detail.get("reports", []))
                if report.customer_ref not in refs:
                    refs.append(report.customer_ref)
                detail["reports"] = refs
                inc.detail = detail

            # Escalate once the same complaint recurs: this is a pattern bug, not confusion.
            if inc.report_count >= self.threshold:
                inc.severity = "P1"
                inc.halts_publication = True
                inc.summary = (
                    f"{inc.report_count} independent reports at the same place "
                    f"({sig}); treating as a pattern defect"
                )
            s.flush()
            s.expunge(inc)
            return inc

    def open_incidents(self, product_slug: str | None = None) -> list[Incident]:
        with self.db.session() as s:
            q = select(Incident).where(Incident.resolved == False)  # noqa: E712
            if product_slug:
                # F-168 (K7): a halt is scoped to its product unless the systemic escalation
                # (`ops.incident_lifecycle.escalate_systemic`) has opened the company-wide
                # row, which then applies to every product.
                q = q.where((Incident.product_slug == product_slug) | (
                    Incident.signature.like("systemic-halt:%")
                    & Incident.halts_publication.is_(True)))
            rows = list(s.scalars(q))
            for r in rows:
                s.expunge(r)
            return rows

    def publication_halted(self, product_slug: str) -> bool:
        """Gate E: a P0/P1 incident stops the publication workflow for that product.

        PHYSFIX integrator decision (SECREVIEW 8da830d R28): every halt is product-wide. No
        design digest, content hash or release identity is read here -- a size halt was once
        scoped to one design digest (F-168), and six review rounds each found a restatement
        of the same object that moved the digest and so escaped the halt. A size halt is
        lifted only by the owner (`runtime.release.lift_size_halt`)."""
        return any(i.halts_publication for i in self.open_incidents(product_slug))

    def certification_halts(self, product_slug: str) -> list[Incident]:
        """The open incidents that stop `gate.certify` for this product.

        ENG-SUPPLY-LANE (owner P0: "Publication holds MUST NOT stop permitted research, QA,
        PDFs or internal listings"). Certification is QA: it publishes nothing, and every
        publication gate still reads `publication_halted`, the company-wide row included.
        So every halt naming this product stops its certification exactly as before. The
        company-wide `systemic-halt:publication` row is waived here only on the rule the
        publication gates already use for rebuilds (`release_gates._staleness_only`): its
        live evidence is widespread artefact STALENESS and no integrity failure. A tampered
        authority chain, any other widespread family, or evidence that cannot be read keeps
        it halting (fail closed). Evidence and rows are read in one session."""
        from ..ops.incident_lifecycle import SYSTEMIC_SIGNATURE, systemic_evidence
        from ..publish.release_gates import _staleness_only

        with self.db.session() as s:
            try:
                staleness_only = _staleness_only(systemic_evidence(s))
            except Exception:  # noqa: BLE001 - unreadable evidence never waives a halt
                staleness_only = False
            rows = list(s.scalars(select(Incident).where(
                Incident.resolved == False,  # noqa: E712
                Incident.halts_publication.is_(True),
                (Incident.product_slug == product_slug) | (
                    Incident.signature.like(f"{SYSTEMIC_PREFIX}%")))))
            for r in rows:
                s.expunge(r)
        return [r for r in rows
                if not (staleness_only and r.product_slug is None
                        and r.signature == SYSTEMIC_SIGNATURE)]

    def resolve(self, incident_id: int, resolution: str, new_version: str | None = None) -> None:
        with self.db.session() as s:
            inc = s.get(Incident, incident_id)
            if inc is None:
                raise KeyError(incident_id)
            inc.resolved = True
            detail = dict(inc.detail or {})
            detail["resolution"] = resolution
            detail["resolved_at"] = utcnow().isoformat()
            if new_version:
                detail["fixed_in_version"] = new_version
            inc.detail = detail


def apply_support_patch(*_args, **_kwargs):
    """Support has no path to the canonical pattern. Calling this is always a bug.

    Kept as an explicit, importable refusal so an agent reaching for it fails loudly instead
    of discovering some other way in (section 14: "Support cannot silently patch canonical
    patterns").
    """
    raise SupportCannotPatchPatterns(
        "support cannot modify a canonical pattern; file an incident and let the engineering "
        "chain produce a re-validated release"
    )
