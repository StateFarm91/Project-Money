"""Pure parsing of frozen, closed-vocabulary knowledge references in a CIR."""
from __future__ import annotations

import re

PREFIX = "learning_rule:"
SUPPORTED = frozenset({"include_finishing_checklist", "include_checklist_and_end_check"})
_SHA = re.compile(r"^[0-9a-f]{64}$")


def markers(cir) -> list[dict]:
    """Parse frozen references; the caller must independently verify their authority."""
    provenance = getattr(cir, "provenance", None)
    primitives = tuple(getattr(provenance, "primitives_used", ()) or ())
    result, seen = [], set()
    for primitive in primitives:
        if not isinstance(primitive, str) or not primitive.startswith(PREFIX):
            continue
        fields = primitive.split(":")
        if (len(fields) != 6 or fields[1] not in SUPPORTED or not fields[2].isdigit()
                or not fields[3].isdigit() or str(int(fields[2])) != fields[2]
                or str(int(fields[3])) != fields[3] or int(fields[2]) <= 0 or int(fields[3]) <= 0
                or not _SHA.fullmatch(fields[4]) or not _SHA.fullmatch(fields[5])):
            raise ValueError("invalid frozen learning reference")
        pin = {"rule_id": int(fields[2]), "rule_version": int(fields[3]),
               "rule_digest": fields[4], "evaluation_digest": fields[5]}
        if pin["rule_id"] in seen:
            raise ValueError("duplicate frozen learning reference")
        seen.add(pin["rule_id"])
        result.append({"rule": fields[1], "pin": pin})
    return result


def marker(rule: str, pin: dict) -> str:
    """Encode a verified rule without copying its source evidence."""
    return (f"{PREFIX}{rule}:{pin['rule_id']}:{pin['rule_version']}:"
            f"{pin['rule_digest']}:{pin['evaluation_digest']}")
