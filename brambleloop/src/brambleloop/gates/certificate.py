"""Quality Release Certificate (Master Plan sections 2, 17, 36).

The release chain, in one place, with a single honest verdict at the end:

    CIR -> Compiler -> Digital Twin -> Written Pattern -> Reverse Compiler
        -> Asset Truth -> Policy -> Certificate

Any unresolved arithmetic error, invalid repeat, reverse-compile mismatch, unsupported claim,
asset misrepresentation, IP concern or policy failure blocks the release. The certificate is
not a summary of how it went; it is the thing that either exists or does not.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..cir.compiler import ERROR, Finding, compile_cir
from ..cir.model import CIR
from ..cir.reverse import compare as reverse_compare
from ..cir.twin import TwinModel, build_twin
from ..cir.writer import write_pattern
from .asset_truth import Asset, check_assets
from .policy import POLICY_VERSION, ListingDraft, check_listing


@dataclass
class ReleaseCertificate:
    slug: str
    version: str
    granted: bool
    release_hash: str | None
    findings: list[Finding] = field(default_factory=list)
    stages_run: list[str] = field(default_factory=list)
    pattern_text: str | None = None
    twin_summary: dict | None = None
    policy_version: str = POLICY_VERSION
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    physical_test_required: bool = False
    physical_test_passed: bool = False

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def blocking_reasons(self) -> list[str]:
        return [str(f) for f in self.errors]

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "version": self.version,
            "granted": self.granted,
            "release_hash": self.release_hash,
            "stages_run": self.stages_run,
            "policy_version": self.policy_version,
            "issued_at": self.issued_at.isoformat(),
            "physical_test_required": self.physical_test_required,
            "physical_test_passed": self.physical_test_passed,
            "findings": [
                {"severity": f.severity, "code": f.code, "message": f.message,
                 "component": f.component, "row": f.row}
                for f in self.findings
            ],
            "twin": self.twin_summary,
        }

    def __str__(self) -> str:
        if self.granted:
            return f"CERTIFIED {self.slug}@{self.version} ({self.release_hash[:12]})"
        return (f"BLOCKED {self.slug}@{self.version}: "
                + "; ".join(self.blocking_reasons[:5]))


def _release_hash(cir: CIR, pattern_text: str) -> str:
    payload = json.dumps(
        {"cir": cir.to_dict(), "text": pattern_text}, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def certify(
    cir: CIR,
    *,
    assets: list[Asset] | None = None,
    listing: ListingDraft | None = None,
    physical_test_passed: bool = False,
    terminology: str = "US",
) -> ReleaseCertificate:
    """Run the full release chain and issue -- or refuse -- a certificate."""
    findings: list[Finding] = []
    stages: list[str] = []

    # 1. Deterministic compile.
    result = compile_cir(cir)
    stages.append("compile")
    findings.extend(result.findings)
    if not result.ok:
        return ReleaseCertificate(cir.slug, cir.version, False, None, findings, stages)

    # 2. Digital twin.
    twin: TwinModel = build_twin(cir, result)
    stages.append("twin")

    # 3. Written pattern, then an independent reverse compile of that exact text.
    pattern_text = write_pattern(cir, result, terminology)
    stages.append("write")
    findings.extend(reverse_compare(cir, pattern_text, terminology))
    stages.append("reverse")

    # 4. Asset truth.
    if assets:
        findings.extend(check_assets(assets, cir, twin))
        stages.append("asset_truth")

    # 5. Policy.
    if listing is not None:
        findings.extend(check_listing(listing, cir))
        stages.append("policy")

    # 6. Physical testing. Class C (fitted garments, complex structures) does not ship on
    #    computation alone -- section 3 is explicit that it normally requires a real sample.
    physical_required = cir.risk_class == "C"
    if physical_required and not physical_test_passed:
        findings.append(Finding(
            ERROR, "PHYSICAL_TEST_REQUIRED",
            f"risk class {cir.risk_class} requires a physical test before release; "
            "computation alone cannot confirm fit and drape"))
    stages.append("physical_test")

    granted = not any(f.severity == ERROR for f in findings)
    rhash = _release_hash(cir, pattern_text) if granted else None

    return ReleaseCertificate(
        slug=cir.slug,
        version=cir.version,
        granted=granted,
        release_hash=rhash,
        findings=findings,
        stages_run=stages,
        pattern_text=pattern_text if granted else None,
        twin_summary={
            "stitch_total": twin.stitch_total,
            "width_cm": twin.width_cm,
            "height_cm": twin.height_cm,
            "colors": sorted(twin.colors_used),
            "stitches": sorted(twin.stitch_types_used),
            "yarn_metres": twin.yarn_metres_by_color,
            "yardage_tolerance": twin.yardage_tolerance,
        },
        physical_test_required=physical_required,
        physical_test_passed=physical_test_passed,
    )
