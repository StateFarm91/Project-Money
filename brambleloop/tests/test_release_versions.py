"""Patterns are software releases: a content change cannot keep a released version.

FB3-G (a8ed44f) re-derived the gauge and every stitch and row count of the Nordic Forest
sizes, the cable throw, the bobble pillow and the Harbour pullover, and left them at 1.0.0 --
so a buyer holding "1.0.0" and a buyer downloading "1.0.0" had two different patterns, and
nothing in the suite noticed. This file is the thing that notices.

`tests/data/release_fingerprints.tsv` pins, for every catalogue builder's default output,
(slug, version, content fingerprint). The fingerprint is `CIR.fingerprint` -- the design
content hash the release chain keys redrafts and the certificate's content hash on (both hash
`CIR.to_dict()`) -- taken with the version blanked, so it measures content alone.

The test fails when:
  * a design's content fingerprint changed but its version did not (bump the version), or
  * its version changed but the pinned row was not updated (update the row with it), or
  * a catalogue builder appears or disappears without its row.

Run `python tests/test_release_versions.py --print` to print the current rows.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.model import CIR, Op  # noqa: E402
from brambleloop.products import builder, garments, nordic_forest, texture, vessels  # noqa: E402

TABLE = ROOT / "tests" / "data" / "release_fingerprints.tsv"


def catalogue() -> dict[str, CIR]:
    """Every catalogue builder's default release, keyed by slug."""
    out: dict[str, CIR] = {}

    def add(cir: CIR) -> None:
        assert cir.slug not in out, f"two catalogue builders release {cir.slug}"
        out[cir.slug] = cir

    for slug in builder.CATALOGUE:
        add(builder.for_slug(slug))
    for cir in nordic_forest.all_sizes().values():
        add(cir)
    for make in (texture.build_ribbed_scarf, texture.build_bobble_pillow,
                 texture.build_cable_throw):
        add(make())
    for spec in vessels.BASKET_SIZES:
        add(vessels.build_basket(spec.key))
    add(vessels.build_hexagon_coaster())
    for cir in garments.every_graded_cir().values():
        add(cir)
    return out


def content_fingerprint(cir: CIR) -> str:
    """The design content hash with the version taken out, so it measures content alone."""
    return dataclasses.replace(cir, version="").fingerprint


def pinned() -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in TABLE.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        slug, version, fp = line.split("\t")
        assert slug not in rows, f"{slug} pinned twice"
        rows[slug] = (version, fp)
    return rows


def release_violations(built: dict[str, CIR], table: dict[str, tuple[str, str]]) -> list[str]:
    out: list[str] = []
    for slug in sorted(set(built) - set(table)):
        out.append(f"{slug}: a catalogue release with no pinned row; add it")
    for slug in sorted(set(table) - set(built)):
        out.append(f"{slug}: pinned but no catalogue builder releases it; remove the row")
    for slug in sorted(set(built) & set(table)):
        version, fp = table[slug]
        cir = built[slug]
        now = content_fingerprint(cir)
        if now != fp and cir.version == version:
            out.append(f"{slug}@{version}: content changed ({fp} -> {now}) but the version "
                       f"did not -- a released version cannot change content; bump it")
        elif cir.version != version:
            out.append(f"{slug}: version {version} -> {cir.version} but the pinned row was "
                       f"not updated; update version and fingerprint together")
    return out


def test_no_content_change_keeps_a_released_version():
    problems = release_violations(catalogue(), pinned())
    assert not problems, "\n".join(problems)


def test_the_check_catches_a_content_change_under_the_same_version():
    """The guard itself: alter one row of a pinned design and keep its version."""
    built = catalogue()
    table = pinned()
    slug = "chunky-ribbed-scarf"
    cir = built[slug]
    altered = CIR.from_dict(cir.to_dict())
    first = altered.components[0].rows[0]
    first.ops = list(first.ops) + [Op("sc", 1)]
    first.declared_count = (first.declared_count or 0) + 1
    problems = release_violations({**built, slug: altered}, table)
    assert any(p.startswith(f"{slug}@") and "bump it" in p for p in problems), problems
    # ...and the same change carried under a new version is a release, asking only for the row.
    bumped = dataclasses.replace(altered, version="1.1.0")
    problems = release_violations({**built, slug: bumped}, table)
    assert problems == [f"{slug}: version 1.0.0 -> 1.1.0 but the pinned row was not updated; "
                        f"update version and fingerprint together"], problems


def test_the_d_fb_6_redesigns_carry_a_new_version():
    """a8ed44f changed these designs' content; the unchanged ones keep theirs."""
    built = catalogue()
    for size in nordic_forest.SIZES:
        assert built[f"nordic-forest-mosaic-throw-{size}"].version == "1.1.0"
    assert built["heirloom-cable-blanket"].version == "1.1.0"
    assert built["bobble-floor-pillow"].version == "1.1.0"
    assert built["chunky-ribbed-scarf"].version == "1.0.0"
    assert built["autumn-oak-mosaic-throw"].version == "1.0.0"     # LEGACY_HELD
    for slug, cir in built.items():
        if slug.startswith("harbour-drop-shoulder-pullover-"):
            assert cir.version == "1.1.0", slug
        if slug.startswith("pebble-raglan-cardigan-"):
            assert cir.version == "1.0.0", slug


if __name__ == "__main__":
    if "--print" in sys.argv:
        for slug, cir in sorted(catalogue().items()):
            print(f"{slug}\t{cir.version}\t{content_fingerprint(cir)}")
        sys.exit(0)
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
