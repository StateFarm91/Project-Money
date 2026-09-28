"""Final Build: the Final Master v1.0 registry is a faithful, complete parse of the source.

The registry is the requirement side of the Final Build closure matrix (F-843). If it silently
drops, merges or truncates a requirement, every downstream mapping inherits the loss, so the
ID-space accounting is pinned here and the committed JSON must equal a fresh parse.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "research" / "final_build"


def _parser():
    spec = importlib.util.spec_from_file_location("parse_master", FB / "parse_master.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_registry_is_exactly_a_fresh_parse():
    fresh = _parser().parse()
    committed = json.loads((FB / "master_registry.json").read_text())
    assert fresh == committed


def test_every_declared_id_is_accounted_for_as_present_or_absent():
    reg = _parser().parse()
    present = {r["num"] for r in reg["requirements"]}
    absent = {int(a[2:]) for a in reg["id_space"]["absent_ids"]}
    assert present | absent == set(range(1, 880)) and not present & absent
    # The only hole in F-001..F-879 is the v0.18 -> v0.19 numbering jump.
    assert sorted(absent) == list(range(631, 651))


def test_the_v015_v016_id_collision_keeps_both_requirements():
    reg = _parser().parse()
    assert sorted(reg["id_space"]["collisions"]) == [f"F-{n}" for n in range(514, 521)]
    uids = [r["uid"] for r in reg["requirements"]]
    assert len(uids) == len(set(uids)) == 866
    by = {r["uid"]: r for r in reg["requirements"]}
    assert by["F-514@v0.15"]["title"] == "Outcome-Based Improvement"
    assert by["F-514@v0.16"]["title"] == "Etsy Surface Inventory"


def test_no_requirement_swallows_a_section_heading_or_version_note():
    import re
    for r in _parser().parse()["requirements"]:
        assert r["title"] and r["text"], r["uid"]
        assert not re.search(r"\b\d{1,2}\. [A-Z0-9/]{3,} [A-Z]|Version note|appends F-",
                             r["full_text"]), r["uid"]


def test_supersessions_and_source_priorities_are_carried():
    reg = _parser().parse()
    by = {r["uid"]: r for r in reg["requirements"]}
    assert "F-789" in by["F-781"]["superseded_where_conflicting_by"]
    assert by["F-001"]["master_priority"] == "P0-before-launch"
    assert by["F-032"]["master_priority"] == "P1-after-real-traffic"
    assert by["F-300"]["master_priority"] == "addendum-P0-launch-critical"
    assert by["F-879"]["version"] == "v1.0" and by["F-831"]["title"] == "Capability Proof Chain"


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
