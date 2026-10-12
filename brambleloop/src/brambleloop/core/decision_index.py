"""Owner decision ids, shipped inside the image.

DECISION_LOG.md is the authority, but the deploy image does not carry it: the log mentions the
operator's build sessions, and the image must carry no Claude session state
(tests/test_cert_claude_independence.py). Runtime checks that an owner decision id exists
(Laura's memory provenance, her identity amendments, voice selection) therefore read this
index -- the log's heading ids and their levels, nothing else -- when the log is absent.
`tests/test_w3_decision_index.py` fails when the index and the log disagree; regenerate with
`python -m brambleloop.core.decision_index` after recording a decision.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

INDEX = Path(__file__).resolve().with_name("decision_index.json")
LOG = Path(__file__).resolve().parents[3] / "DECISION_LOG.md"
_HEADING = re.compile(r"^(#+)\s+([A-Za-z0-9][A-Za-z0-9._-]{0,63})(?=\s|\(|$)", re.M)


def build(text: str) -> dict[str, int]:
    """Heading id -> the shallowest heading level it appears at."""
    out: dict[str, int] = {}
    for hashes, ident in _HEADING.findall(text):
        out[ident] = min(len(hashes), out.get(ident, 99))
    return dict(sorted(out.items()))


def load() -> dict[str, int]:
    try:
        return {str(k): int(v) for k, v in json.loads(INDEX.read_text())["ids"].items()}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def recorded(decision_id: str, *, level: int | None = None) -> bool:
    """`decision_id` is a heading in the shipped index (at exactly `level` hashes if given)."""
    got = load().get(decision_id)
    return got is not None and (level is None or got == level)


def main(argv: list[str]) -> int:
    ids = build(LOG.read_text(encoding="utf-8"))
    INDEX.write_text(json.dumps({"source": "DECISION_LOG.md headings", "ids": ids},
                                indent=1, sort_keys=True) + "\n")
    print(f"wrote {INDEX.name}: {len(ids)} ids")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
