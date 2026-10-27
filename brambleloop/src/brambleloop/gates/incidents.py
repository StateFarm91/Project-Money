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

    def publication_halted(self, product_slug: str, *, content_hash=None) -> bool:
        """Gate E: a P0/P1 incident stops the publication workflow for that product.

        `content_hash` is passed only by certification of a specific content, and only lifts
        a halt that is scoped to one *other* release content (`detail.release_scope`, e.g.
        a physical sample whose size disagreed, F-168). It may be a callable, evaluated only
        when such a halt exists. Every other halt, and every caller that does not name a
        content, is unchanged."""
        halting = [i for i in self.open_incidents(product_slug) if i.halts_publication]
        if not halting or content_hash is None:
            return bool(halting)
        scoped = [i for i in halting if release_scope(i)]
        if len(scoped) < len(halting):
            return True
        current = content_hash() if callable(content_hash) else content_hash
        if not current:
            return True
        return any(release_scope(i).get("content_hash") == current for i in scoped)

    def resolve_superseded_release_halts(self, product_slug: str, *, version: str,
                                         content_hash: str) -> list[int]:
        """Resolve release-scoped halts of this product whose content is no longer current.

        Called once a different content of the product is certified: the halted release is
        superseded, and the corrected one carries none of the halted release's evidence (it
        needs its own sample, F-078)."""
        resolved: list[int] = []
        for inc in self.open_incidents(product_slug):
            scope = release_scope(inc)
            if (not scope or inc.product_slug != product_slug
                    or not content_hash or scope.get("content_hash") == content_hash):
                continue
            self.resolve(inc.id, (f"superseded: {product_slug}@{version} (content "
                                  f"{content_hash[:12]}) is certified; it needs its own "
                                  f"physical sample"), new_version=version)
            resolved.append(inc.id)
        return resolved

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


def release_scope(incident) -> dict:
    """The one release content an incident halts, or {} for a product-wide incident."""
    scope = (getattr(incident, "detail", None) or {}).get("release_scope")
    return scope if isinstance(scope, dict) and scope.get("content_hash") else {}


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
