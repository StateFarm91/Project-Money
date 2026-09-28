"""Which credentials have been exposed, and whether each has been replaced since (F-160).

A credential that travelled through a chat transcript, a screenshot or a manual handoff is
compromised in the only sense that matters operationally: somebody other than the secret store
has held it, and nobody can enumerate who. It stays ROTATION REQUIRED until it is replaced at
the source, however long ago the exposure was and however carefully it has been stored since.

Until this file existed that fact lived in one paragraph of BUILD_STATE ("a key that has
travelled through a chat transcript should be rotated once the build no longer needs this
one"). Prose is not a queue: nothing re-raised it, nothing could say whether it had happened,
and the next exposure would have been another paragraph somewhere else.

THREE PROPERTIES

**Never a value.** A register of secrets that stored the secrets would be the most valuable
file in the repository. `Exposure` has no field that could hold one, `validate()` refuses an
entry any of whose text is shaped like a credential (the same patterns as the release secret
scan), and `tests/test_secret_scan.py` reads this file on every run.

**Held in code, like `provider_accounts.REPORTED_FACTS`.** Each entry is a statement about an
event -- this credential was exposed here, on this date; it was replaced on that one -- and a
statement that arrives by conversation should be visible in the diff that recorded it. The
register is short and auditable; a table would hide who wrote which row.

**Rotated is a date, not a belief.** `rotated_at` is set only when the replacement is known to
be in service (for a key: the new one authenticated in production). Until then the entry is
surfaced as an owner card in the Execution Directive's format and it does not age out.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..launch.readiness import OwnerRequest

KEY_PREFIX = "credential_rotation:"
ROTATION_REQUIRED = "rotation_required"
ROTATED = "rotated"


@dataclass(frozen=True)
class Exposure:
    """One credential, where it is held, and the event that made it rotation-required."""

    name: str            # the variable / credential name, never its value
    provider: str        # whose credential it is (where it is rotated)
    held_in: str         # where the live copy is held today
    exposed_at: str      # ISO date of the exposure event
    exposure: str        # what happened, in words
    rotate_how: str      # the exact rotation action
    rotated_at: str = ""  # ISO date the replacement was confirmed in service; "" = not yet
    rotation_evidence: str = ""

    @property
    def status(self) -> str:
        return ROTATED if self.rotated_at else ROTATION_REQUIRED

    def to_dict(self) -> dict:
        return {**asdict(self), "status": self.status}


REGISTER: tuple[Exposure, ...] = (
    Exposure(
        name="ANTHROPIC_API_KEY",
        provider="anthropic",
        held_in="Railway service variable (production); nowhere in this repository",
        exposed_at="2026-09-19",
        exposure=("pasted into a Claude Code session in plaintext and in a screenshot during "
                  "Build 2 provider set-up (BUILD_STATE, owner-actions section, commit 3301d67)"),
        rotate_how=("create a new key in the Anthropic console, set it as ANTHROPIC_API_KEY on "
                    "the Railway service, confirm one real model call succeeds, then revoke "
                    "the old key in the console"),
    ),
)

# The release secret scan's patterns, restated narrowly so this module does not import tests.
_VALUE_SHAPES = re.compile(
    r"sk-[A-Za-z0-9_\-]{20,}|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|PRIVATE KEY-----|"
    r"\b\d{5,12}\.[A-Za-z0-9_\-]{50,}|\bgh[pousr]_[A-Za-z0-9]{36}\b|"
    r"(?i:\bbearer\s+[A-Za-z0-9._~+/\-]{24,})")


def validate(register: tuple[Exposure, ...] = REGISTER) -> list[str]:
    """Problems with the register; empty when it is sound. Never returns a matched value."""
    problems = []
    seen = set()
    for e in register:
        if e.name in seen:
            problems.append(f"{e.name}: listed twice")
        seen.add(e.name)
        for field_name, text in asdict(e).items():
            if _VALUE_SHAPES.search(str(text)):
                problems.append(f"{e.name}.{field_name}: text is shaped like a credential")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.exposed_at):
            problems.append(f"{e.name}: exposed_at is not an ISO date")
        if e.rotated_at:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.rotated_at):
                problems.append(f"{e.name}: rotated_at is not an ISO date")
            elif e.rotated_at < e.exposed_at:
                problems.append(f"{e.name}: rotated before it was exposed")
            if not e.rotation_evidence:
                problems.append(f"{e.name}: rotated_at without rotation_evidence")
    return problems


def pending(register: tuple[Exposure, ...] = REGISTER) -> list[Exposure]:
    return [e for e in register if e.status == ROTATION_REQUIRED]


def owner_requests(register: tuple[Exposure, ...] = REGISTER) -> list[OwnerRequest]:
    """One owner card per unrotated credential, keyed so the owner queue de-duplicates it.

    The key is stable per credential name, so the queue restates rather than duplicates, and
    the card stops being generated -- and is closed by the queue -- the day `rotated_at` is set.
    """
    return [OwnerRequest(
        key=KEY_PREFIX + e.name,
        action=f"Rotate {e.name} ({e.provider}): {e.rotate_how}.",
        reason=(f"Exposed {e.exposed_at}: {e.exposure}. A credential that has been outside "
                f"the secret store stays rotation-required until replaced (F-160)."),
        max_cost_cad=0.0,
        minutes=10,
        consequence_of_delay=("the exposed credential stays valid; anyone holding the "
                              "transcript or screenshot can spend on or act as this account"),
        blocks="nothing in the build; this is a security exposure, not a capability gate",
    ) for e in pending(register)]


def report(register: tuple[Exposure, ...] = REGISTER) -> dict:
    """The register as data: every entry, what is still pending, and whether it is sound."""
    return {
        "entries": [e.to_dict() for e in register],
        "rotation_required": [e.name for e in pending(register)],
        "problems": validate(register),
        "note": "names and events only; no credential value is ever held here (F-160)",
    }


if __name__ == "__main__":
    import json
    import sys

    out = report()
    print(json.dumps(out, indent=2))
    sys.exit(1 if out["rotation_required"] or out["problems"] else 0)
