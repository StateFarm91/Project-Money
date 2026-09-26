"""`CIR.from_dict(CIR.to_dict(x))` must be `x`, for every design this repository can build.

Every pipeline hop serialises: the draft job enqueues `cir.to_dict()`, the compile job reads
`CIR.from_dict`, the release row stores the dict and the reader loads it back. Until
2026-09-26 `from_dict` silently dropped `Op.loop`, `Op.spans`, `Row.skips`,
`Component.holds/resumes/grain` and `CIR.authored`. The benchmark cardigan came back as a
CIR that failed to compile (its armhole rows lost their `skips` and read as underruns), was
relabelled as Brambleloop's own work, stood its side-to-side grain upright and flattened every
back-loop stitch to plain fabric. Every one of those is a fact the compiler, the specification
gate or the texture instrument depends on, and every one was being lost between two stages
that both believed they were looking at the same design.

The rule this file pins is structural rather than a list: the set of keys `to_dict` writes is
the set `from_dict` reads, checked by round-tripping and comparing the dicts, so a field added
to the schema tomorrow without a `from_dict` line fails here rather than in production.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import benchmarks as B  # noqa: E402  (read-only fixture use)
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import (  # noqa: E402
    CIR, Component, Gauge, Hold, Op, Provenance, Repeat, Row, Seam,
)
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.products import texture, vessels  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402
from tests import fixtures  # noqa: E402
from tests.test_division import yoke  # noqa: E402


def every_design() -> list[tuple[str, CIR]]:
    """Every builder in `products/*`, every benchmark size, and the division fixtures."""
    out: list[tuple[str, CIR]] = []
    for size in ("throw", "baby", "large"):
        out.append((f"nordic-{size}", nf.build(size)))
    out += [(slug, build(d)) for slug, d in sorted(CATALOGUE.items())]
    out += [("cable-throw", texture.build_cable_throw()),
            ("bobble-pillow", texture.build_bobble_pillow()),
            ("ribbed-scarf", texture.build_ribbed_scarf()),
            ("basket-trio", vessels.build()),
            ("hexagon-coaster", vessels.build_hexagon_coaster())]
    out += [(f"basket-{s}", vessels.build_basket(s)) for s in ("small", "medium", "large")]
    out += [(f"benchmark-cardigan-{s}", B.cardigan(s)) for s in B.SIZES]
    out += [("division-yoke", yoke()),
            ("fixture-sphere", fixtures.good_sphere()),
            ("fixture-mosaic", fixtures.good_mosaic_panel())]
    try:
        from brambleloop.products import garments
        out += [(f"garment-{k}", c) for k, c in garments.every_graded_cir().items()]
    except ImportError:  # the garment capability is built in the same change; tolerate absence
        pass
    return out


def _codes(cir: CIR) -> list[str]:
    return sorted(str(f) for f in compile_cir(cir).findings)


def test_to_dict_from_dict_is_the_identity_for_every_design():
    broken = []
    for name, cir in every_design():
        before = cir.to_dict()
        after = CIR.from_dict(before).to_dict()
        if after != before:
            lost = _first_difference(before, after)
            broken.append((name, lost))
    assert not broken, broken


def test_the_round_trip_survives_json_too():
    """The pipeline stores JSON, so lists-for-tuples must normalise back to the same dict."""
    broken = []
    for name, cir in every_design():
        before = cir.to_dict()
        after = CIR.from_json(cir.to_json()).to_dict()
        if json.dumps(after, sort_keys=True, default=str) != json.dumps(
                before, sort_keys=True, default=str):
            broken.append((name, _first_difference(before, after)))
    assert not broken, broken


def test_a_round_tripped_design_compiles_to_the_same_findings():
    """The symptom the drop produced: the cardigan came back with UNDERRUN at its armholes."""
    broken = []
    for name, cir in every_design():
        if _codes(cir) != _codes(CIR.from_dict(cir.to_dict())):
            broken.append(name)
    assert not broken, broken


def test_the_fields_the_old_reader_dropped_are_read_back():
    cardigan = B.cardigan("M")
    back = CIR.from_dict(cardigan.to_dict())
    assert back.authored == "benchmark"
    body = next(c for c in back.components if c.name == "body")
    assert body.grain == "across"
    armhole = next(r for r in body.rows if r.skips)
    assert armhole.skips == armhole.ops[-1].spans == armhole.ops[-1].count - 1
    loops = {op.loop for c in back.components for r in c.rows for op in r.ops
             if isinstance(op, Op)}
    assert "back" in loops, "the back-loop rib was flattened to plain fabric"

    divided = CIR.from_dict(yoke().to_dict())
    holder = divided.components[0]
    assert [h.name for h in holder.holds] == ["sleeve_left", "sleeve_right"]
    assert holder.holds[1].from_stitch == 20
    assert divided.components[1].resumes == "sleeve_left"
    assert compile_cir(divided).ok


def test_provenance_is_omitted_when_absent_and_kept_when_present():
    """Absent, not null: existing products' serialised forms are frozen digests."""
    plain = fixtures.good_sphere()
    assert "provenance" not in plain.to_dict()
    assert plain.provenance is None

    stamped = fixtures.good_sphere()
    stamped.provenance = Provenance(
        concept_key="c1", brief_digest="abc", primitives_used=["grading", "shaping"],
        benchmarks_consulted=("benchmark-side-to-side-cardigan",), at="2026-09-26T00:00:00Z")
    d = stamped.to_dict()
    assert d["provenance"]["primitives_used"] == ("grading", "shaping")
    back = CIR.from_json(stamped.to_json())
    assert back.provenance == stamped.provenance
    assert back.to_dict() == d
    # And stamping a design changes its fingerprint, so a provenance is not free to add later
    # to a design already certified without it.
    assert stamped.fingerprint != plain.fingerprint


def test_the_reader_and_writer_cover_the_same_keys():
    """Structural: a new dataclass field without a `from_dict` line fails here."""
    cir = CIR(
        slug="k", title="K", version="1", construction="flat_rows",
        gauge=Gauge(16, 18, chains_per_10cm=19, chain_gauge_uncertainty=0.02),
        components=[
            Component("a", "flat_rows", foundation=8, grain="across",
                      holds=[Hold("h", at_row=2, count=4, from_stitch=2, note="n")],
                      rows=[Row(1, [Op("sc", 8)], declared_count=8, turning_chain=1),
                            Row(2, [Op("sc", 2, loop="back"), Op("ch", 4, spans=4),
                                    Op("sc", 2, loop="front")],
                                declared_count=8, turning_chain=1),
                            Row(3, [Op("sc", 4)], declared_count=4, skips=4,
                                allow_remainder=True, turning_chain=1)]),
            Component("b", "joined_rounds", foundation=0, foundation_kind="none",
                      resumes="h", make=2,
                      rows=[Row(1, [Repeat([Op("sc")], times=4)], declared_count=4)])],
        assembly=[Seam("sew", "b", "a", edge_a="top", edge_b="opening", at_round=1,
                       spans_rounds=1, stitches_from_centre=1, mirrored=True)],
        authored="brambleloop",
        provenance=Provenance("c", "d", ("grading",), (), "test", "2026-09-26T00:00:00Z"))
    d = cir.to_dict()
    assert CIR.from_dict(d).to_dict() == d
    assert CIR.from_json(json.dumps(d)).to_dict() == d


def _first_difference(a, b, path="") -> str:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b or a[k] != b[k]:
                return _first_difference(a.get(k), b.get(k), f"{path}.{k}")
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_difference(x, y, f"{path}[{i}]")
    return f"{path}: {a!r} != {b!r}"


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
