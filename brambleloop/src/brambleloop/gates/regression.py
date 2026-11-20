"""Incident to regression fixture (acceptance Gate B).

Gate B requires that a corrected bug creates a regression test. This is the automation that
closes it, and it is the difference between a system that fixes bugs and one that stops making
them.

The mechanism is small. When a defect is confirmed against a pattern, the *defective CIR* is
captured as a permanent fixture with the specific finding it must provoke. The suite then runs
every captured fixture and asserts the compiler still catches each one. A future change that
quietly loosens a check fails here rather than in a customer's hands at row 94.

Two things this deliberately does not do. It does not capture a fixture from an unconfirmed
customer report -- a report is evidence that something is wrong, and the compiler decides what.
And it does not store a fix; it stores the *failure*. A regression suite made of fixed patterns
proves only that the fixed patterns are still fixed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..cir.compiler import compile_cir
from ..cir.model import CIR

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "regressions"


class NotAReproducibleDefect(ValueError):
    """A fixture was offered for a CIR that compiles clean."""


@dataclass
class RegressionFixture:
    slug: str
    captured_at: str
    source: str                     # incident id, or a description of where it came from
    expected_codes: list[str]
    cir: dict
    note: str = ""

    def to_dict(self) -> dict:
        return {"slug": self.slug, "captured_at": self.captured_at, "source": self.source,
                "expected_codes": list(self.expected_codes), "cir": self.cir,
                "note": self.note}

    @classmethod
    def from_dict(cls, data: dict) -> "RegressionFixture":
        return cls(slug=data["slug"], captured_at=data["captured_at"],
                   source=data["source"], expected_codes=list(data["expected_codes"]),
                   cir=data["cir"], note=data.get("note", ""))


def capture(cir: CIR, *, source: str, note: str = "",
            directory: Path | None = None) -> RegressionFixture:
    """Freeze a defective pattern as a permanent regression fixture.

    Refuses a CIR that compiles clean. A fixture that provokes no finding asserts nothing, and
    a suite full of those is worse than no suite because it reports green.
    """
    result = compile_cir(cir)
    if result.ok:
        raise NotAReproducibleDefect(
            f"{cir.slug} compiles clean, so there is nothing for a regression test to catch. "
            f"A defect is only reproducible once the deterministic checks can see it; if a "
            f"customer is reporting a real problem the compiler cannot see, the missing check "
            f"is the bug.")

    codes = sorted({f.code for f in result.errors})
    directory = directory or FIXTURE_DIR
    directory.mkdir(parents=True, exist_ok=True)

    fixture = RegressionFixture(
        slug=cir.slug,
        captured_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        expected_codes=codes,
        cir=cir.to_dict(),
        note=note or f"captured from {source}; must always produce {codes}",
    )
    path = directory / f"{_safe(cir.slug)}-{_safe(source)}.json"
    path.write_text(json.dumps(fixture.to_dict(), indent=2, sort_keys=True))
    return fixture


def _safe(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text)[:60]


def load_all(directory: Path | None = None) -> list[RegressionFixture]:
    directory = directory or FIXTURE_DIR
    if not directory.exists():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        out.append(RegressionFixture.from_dict(json.loads(path.read_text())))
    return out


@dataclass
class RegressionRun:
    checked: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {"checked": self.checked, "ok": self.ok, "failures": list(self.failures)}


def run(directory: Path | None = None) -> RegressionRun:
    """Re-run every captured defect. Every one must still be caught."""
    out = RegressionRun()
    for fixture in load_all(directory):
        out.checked += 1
        result = compile_cir(CIR.from_dict(fixture.cir))
        if result.ok:
            out.failures.append({
                "slug": fixture.slug, "source": fixture.source,
                "problem": "a pattern that was defective now compiles clean — a check has "
                           "been loosened or removed",
                "expected_codes": fixture.expected_codes})
            continue
        codes = {f.code for f in result.errors}
        missing = [c for c in fixture.expected_codes if c not in codes]
        if missing:
            out.failures.append({
                "slug": fixture.slug, "source": fixture.source,
                "problem": f"no longer produces {missing}",
                "now_produces": sorted(codes)})
    return out


def capture_from_incident(db, incident_id: int, cir: CIR, *,
                          directory: Path | None = None) -> RegressionFixture | None:
    """Capture a fixture for a confirmed incident, once.

    Returns None when the pattern compiles clean, which is the common and important case: most
    customer reports are not compiler-visible defects, and turning every one into a fixture
    would fill the suite with patterns that assert nothing.
    """
    from ..core.models import Incident

    with db.session() as s:
        incident = s.get(Incident, incident_id)
        if incident is None:
            raise KeyError(f"no incident {incident_id}")
        already = (incident.detail or {}).get("regression_fixture")
        if already:
            return None
        source = f"incident-{incident_id}"
        summary = incident.summary

    try:
        fixture = capture(cir, source=source, note=summary, directory=directory)
    except NotAReproducibleDefect:
        with db.session() as s:
            incident = s.get(Incident, incident_id)
            detail = dict(incident.detail or {})
            detail["regression_fixture"] = None
            detail["not_reproducible"] = (
                "the pattern compiles clean, so this is not a compiler-visible defect. If the "
                "report is real, the missing check is the bug.")
            incident.detail = detail
        return None

    with db.session() as s:
        incident = s.get(Incident, incident_id)
        detail = dict(incident.detail or {})
        detail["regression_fixture"] = fixture.slug
        detail["expected_codes"] = fixture.expected_codes
        incident.detail = detail
    return fixture
