"""The Build-2 requirement registry, and the honesty rules that make it worth having.

A 320-requirement build is exactly where a progress number becomes a lie: drop a few
requirements and the percentage improves, file the hard ones under "blocked" and the
remaining work shrinks. These tests exist to make both of those fail loudly.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import requirements as R  # noqa: E402


def test_the_registry_is_a_complete_unbroken_spine_of_all_320():
    """v1.4.3 numbers 1..320 with no gaps, so the registry must too.

    A registry that silently loses a requirement still reports a plausible percentage, which
    is the failure mode that matters: nobody notices 317 where 320 was expected.
    """
    reqs = R.load()
    assert len(reqs) == 320
    assert sorted(r.id for r in reqs) == list(range(1, 321))
    assert R.coverage()["total"] == 320


def test_every_requirement_carries_its_spec_text_and_a_reason():
    """The audit has to be checkable against the document it audits.

    A status with no note is an opinion. Each entry keeps the requirement's own words so a
    future session can re-judge the classification without reopening the PDF.
    """
    for r in R.load():
        assert r.title.strip(), r.id
        assert r.body.strip(), r.id
        assert r.note.strip(), r.id
        assert r.version.startswith("v1."), (r.id, r.version)
        assert r.status in R.STATUSES, (r.id, r.status)


def test_remaining_work_excludes_nothing_that_claude_can_actually_build():
    """`executable` is the number that must not be gameable.

    Owner-gated and data-gated are real categories -- an Etsy shop cannot be written into
    existence -- but they are also the obvious place to hide work one does not want to do.
    So the remaining count is defined as partial + missing only, and this asserts that
    definition rather than trusting it.
    """
    c = R.coverage()
    assert c["executable_remaining"] == c["by_status"]["partial"] + c["by_status"]["missing"]
    assert c["executable_remaining"] == len(R.executable())
    for r in R.executable():
        assert r.status in (R.PARTIAL, R.MISSING), (r.id, r.status)
    # Gated requirements are excluded from the remaining count, never from the registry.
    total = sum(c["by_status"].values())
    assert total == 320, c["by_status"]


def test_the_mandatory_mjs_mission_is_present_and_not_quietly_generalised():
    """The owner's single loudest instruction: do not turn this into 'watch competitors'.

    301-320 are the named MJs mission. They must be in the registry as themselves, and the
    named shop must survive as a literal string rather than being softened into a category.
    """
    mjs = [r for r in R.load() if 301 <= r.id <= 320]
    assert len(mjs) == 20
    assert all(r.version == "v1.4.3" for r in mjs)

    named = R.get(301)
    assert "MJsOffTheHookDesigns" in named.title or "MJsOffTheHookDesigns" in named.body
    assert "MJsOffTheHookDesigns" in named.body

    # 320 is the release-blocking acceptance test and must be tracked as blocked, not done.
    assert R.get(320).status != R.COVERED


def test_business_continuity_is_registered_as_the_owner_flagged_it():
    """51 is the gap Build 1 found and the owner told Build 2 to close early."""
    r = R.get(51)
    assert "continuity" in r.title.lower() or "export" in r.title.lower()
    assert r.status in (R.MISSING, R.PARTIAL, R.COVERED, R.OWNER_GATED)
    if r.status == R.OWNER_GATED:
        # The export, the restore, the proof and the retained archive are all built. What is
        # left is a copy outside this provider, and an owner gate is only honest if it names
        # a condition code can check rather than a reason nobody revisits.
        from brambleloop.build2 import executor as E

        gate = E.gate_for(51)
        assert gate is not None, "51 was parked without naming what it is waiting for"
        assert gate == "offsite_storage"
        assert E.GATE_BY_KEY[gate].how.strip(), "a gate with no checkable condition"
        assert "retained" in r.note and "provider" in r.note


def test_sections_account_for_every_requirement_exactly_once():
    """The per-version rollup is what a reader actually navigates by."""
    sections = R.sections()
    assert sum(s["total"] for s in sections) == 320
    counted = sum(s[status] for s in sections for status in R.STATUSES)
    assert counted == 320
    versions = [s["version"] for s in sections]
    assert len(versions) == len(set(versions))
    assert "v1.4.3" in versions


def test_a_registry_that_lost_a_requirement_is_refused():
    """The validator is the thing standing between a dropped requirement and a nice number,
    so it gets exercised rather than trusted."""
    import json
    import tempfile

    from brambleloop.build2 import requirements as mod

    raw = json.loads(mod.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert len(raw) == 320

    original = mod.REGISTRY_PATH
    try:
        for mutation, why in (
            (raw[:-1], "a dropped requirement"),
            (raw + [dict(raw[0])], "a duplicated requirement"),
            ([{**r, "status": "nearly"} if r["id"] == 5 else r for r in raw], "a bad status"),
            ([{**r, "note": "  "} if r["id"] == 5 else r for r in raw], "an empty note"),
        ):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(mutation, fh)
                path = Path(fh.name)
            mod.REGISTRY_PATH = path
            mod.load.cache_clear()
            try:
                mod.load()
            except ValueError:
                pass
            else:
                raise AssertionError(f"the validator accepted {why}")
    finally:
        mod.REGISTRY_PATH = original
        mod.load.cache_clear()
    assert len(mod.load()) == 320


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
