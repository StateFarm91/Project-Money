"""Audit F-05 (2026-11-22): BUILD_STATE.md must open with a current PRODUCTION NOW block.

BUILD_STATE.md is the "read first every session" record. It drifted: it named no production SHA
and its newest entries still said "NOT deployed" for branches that were deployed. This suite keeps
the top of the file tied to two facts git can check:

1. The block's `- production-sha: <40 hex>` line names a SHA in release/DEPLOYED_HISTORY.json that
   is the NEWEST entry or the one immediately before it.

   Tolerance (why one entry of slack): ops/deploy.sh deploys a candidate whose tree still has the
   previous production as the newest history entry, and only afterwards is a record-only commit
   ("DEPLOYED_HISTORY: Batch X <sha>") appended on top (f9011cf9 is one). On that tree the block
   honestly names the previous production, which is now one behind. Requiring "newest only" would
   turn that automated record-only commit red; this slack does not touch the deploy guard, the
   rehearsed rollback or the suite records, so the deploy tooling cannot deadlock. Two deploys
   without updating the block is drift, and fails here.

2. The block's `- release-record: NONE|PRESENT` line agrees with
   `release_record.verify_build` for the checked-out tree (the same check the Railway boot guard
   runs). BUILD_STATE.md is not deployable (only src/ and requirements.lock are digested), so the
   operator can update this line in the same commit that adds a release record written by
   `ops/deploy_guard.py record` (which never commits by itself): no deadlock there either.

Run: cd brambleloop && python3 tests/test_audit_build_state_current.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import release_record  # noqa: E402

BUILD_STATE = ROOT / "BUILD_STATE.md"
HISTORY = ROOT / "release" / "DEPLOYED_HISTORY.json"
HEADING = re.compile(r"^## PRODUCTION NOW \(verified \d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z\)$")
SHA_LINE = re.compile(r"^- production-sha: ([0-9a-f]{40})\s*$", re.M)
RECORD_LINE = re.compile(r"^- release-record: (NONE|PRESENT)\b", re.M)
NONE_PHRASE = "No committed release record names this tree"


def block_of(text: str) -> str:
    """The PRODUCTION NOW block: from the first line to the first `---` rule."""
    lines = text.lstrip("\n").split("\n")
    if not lines or not HEADING.match(lines[0].strip()):
        raise AssertionError(f"BUILD_STATE.md must open with '## PRODUCTION NOW (verified "
                             f"<UTC>)'; it opens with {lines[0][:80]!r}")
    out = []
    for line in lines:
        if line.strip() == "---":
            return "\n".join(out)
        out.append(line)
    raise AssertionError("the PRODUCTION NOW block has no closing '---' rule")


def problems(text: str, history: list[str], record_ok: bool) -> list[str]:
    """Every way the block disagrees with git; [] when it is current."""
    try:
        block = block_of(text)
    except AssertionError as exc:
        return [str(exc)]
    out = []
    shas = SHA_LINE.findall(block)
    if len(shas) != 1:
        out.append(f"the block must have exactly one '- production-sha:' line, found {len(shas)}")
    else:
        sha = shas[0]
        if sha not in history:
            out.append(f"production-sha {sha[:12]} is not in DEPLOYED_HISTORY.json")
        elif history.index(sha) < len(history) - 2:
            behind = len(history) - 1 - history.index(sha)
            out.append(f"production-sha {sha[:12]} is {behind} deploys behind the newest "
                       f"DEPLOYED_HISTORY entry {history[-1][:12]}; update the block")
    recs = RECORD_LINE.findall(block)
    if len(recs) != 1:
        out.append(f"the block must have exactly one '- release-record:' line, found {len(recs)}")
    else:
        want = "PRESENT" if record_ok else "NONE"
        if recs[0] != want:
            out.append(f"block says release-record {recs[0]} but verify_build ok={record_ok}")
        if record_ok and NONE_PHRASE in block:
            out.append("a release record names this tree, yet the block says none exists")
    return out


def _history() -> list[str]:
    return [e["sha"] for e in json.loads(HISTORY.read_text())["deployed"]]


def _record_ok() -> bool:
    return bool(release_record.verify_build(env={"RAILWAY_ENVIRONMENT": "production"})["ok"])


# ---- the real file -------------------------------------------------------------------------

def test_build_state_production_block_is_current():
    found = problems(BUILD_STATE.read_text(), _history(), _record_ok())
    assert not found, found


# ---- the checker itself (so the tolerance is pinned, not just the file) -------------------

A, B, C = "a" * 40, "b" * 40, "c" * 40


def _doc(sha: str, record: str = "NONE", extra: str = "") -> str:
    return (f"## PRODUCTION NOW (verified 2026-11-22T05:29Z)\n\n- production-sha: {sha}\n"
            f"- release-record: {record}. {extra}\n\n---\n\n> **2026-11-22 — entry**\n")


def test_newest_and_one_behind_pass_two_behind_fails():
    assert problems(_doc(C), [A, B, C], False) == []
    assert problems(_doc(B), [A, B, C], False) == []   # record-only history commit on top
    assert any("2 deploys behind" in p for p in problems(_doc(A), [A, B, C], False))


def test_unknown_sha_and_missing_block_fail():
    assert any("not in DEPLOYED_HISTORY" in p for p in problems(_doc("d" * 40), [A, B, C], False))
    assert any("must open with" in p for p in problems("> **2026-11-22 — entry**\n", [A], False))
    assert any("closing" in p for p in problems(_doc(A).replace("---", ""), [A], False))


def test_release_record_line_must_match_verify_build():
    assert problems(_doc(A, "PRESENT"), [A], True) == []
    assert any("verify_build ok=False" in p for p in problems(_doc(A, "PRESENT"), [A], False))
    assert any("verify_build ok=True" in p for p in problems(_doc(A, "NONE"), [A], True))
    assert any("says none exists" in p
               for p in problems(_doc(A, "PRESENT", NONE_PHRASE), [A], True))


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
