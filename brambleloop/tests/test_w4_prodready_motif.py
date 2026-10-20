"""W4-PRODREADY (owner directive 2026-10-19): a motif word in a title or in the copy must be
backed by the CIR's motif declaration (Product Truth, `products.launch0.motif_promise`).

* nordic-star-ornaments was "Nordic Snowflake Ornament Set (6)", but the CIR draws six striped
  pieces with scattered 3 x 3 raised crosses and no snowflake outline. It is now "Textured
  Stripe Ornament Set (6)" (1.5.0).
* mosaic-placemat-pair was "Diamond Lattice Placemat Pair", but the lattice exists only as
  raised stitches, one colour per row. It is now "Raised Diamond Lattice Placemat Pair"
  (1.4.0).

The declaration is the CIR's own provenance (`primitives_used`, e.g. products.motifs:snowfall),
read through a closed table. A relief motif must be called a relief in title-like text. A motif
the table does not know backs nothing.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_prodready_motif.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.seo import strategy as S  # noqa: E402


def _retitled(build: str, title: str):
    return dataclasses.replace(L.cir_for(build), title=title)


def test_the_old_titles_are_refused():
    old = (("snowflake_ornaments", "Nordic Snowflake Ornament Set (6)"),
           ("snowflake_ornaments", "Nordic Star Ornament Set (6)"),     # production 1.0.0
           ("placemat_pair", "Diamond Lattice Placemat Pair"))
    for build, title in old:
        r = L.motif_promise(_retitled(build, title))
        assert r["backed"] is False and r["problems"], (title, r)
    # and the reason is the one the owner named
    r = L.motif_promise(_retitled("snowflake_ornaments", "Nordic Snowflake Ornament Set (6)"))
    assert any("'snowflake'" in p for p in r["problems"]), r
    r = L.motif_promise(_retitled("placemat_pair", "Diamond Lattice Placemat Pair"))
    assert any("raised stitches" in p for p in r["problems"]), r


def test_the_old_copy_is_refused():
    cir = L.cir_for("snowflake_ornaments")
    r = L.motif_promise(cir, tags={"tags": ["snowflake ornament", "nordic snowflake"]})
    assert not r["backed"] and len(r["problems"]) == 2, r
    r = L.motif_promise(cir, {"seo": "Snowflake Ornament Crochet Pattern, Set of 6"})
    assert not r["backed"], r


def test_the_new_titles_and_copy_are_backed_and_versions_moved():
    orn, mat = L.cir_for("snowflake_ornaments"), L.cir_for("placemat_pair")
    assert orn.title == "Textured Stripe Ornament Set (6)" and orn.version == "1.5.0"
    assert mat.title == "Raised Diamond Lattice Placemat Pair" and mat.version == "1.4.0"
    for slug in ("nordic-star-ornaments", "mosaic-placemat-pair"):
        cand = L.candidate(slug)
        texts, tags = L._copy_texts(slug)
        assert texts and tags, slug
        cir = L.cir_for(cand.variants[0].build)
        r = L.motif_promise(cir, {"candidate.title": cand.title,
                                  "candidate.what_it_is": cand.what_it_is, **texts},
                            tags=tags)
        assert r["backed"], (slug, r["problems"])
        assert not any("snowflake" in p.lower() for ps in tags.values() for p in ps), tags
        assert "snowflake" not in S.TITLES[slug].lower()


def test_every_launch0_product_passes_product_truth_with_the_motif_gate():
    assert L.LAUNCH0_SLUGS
    for slug in L.LAUNCH0_SLUGS:
        t = L.product_truth(L.candidate(slug))
        assert "motif_promise_backed" in t["gates"], t["gates"]
        assert t["passes_gates"], (slug, t["gates"],
                                   [v["motif_promise"]["problems"] for v in t["variants"]])


def test_declarations_come_from_the_cir_and_unknown_backs_nothing():
    assert L.declared_motifs(L.cir_for("snowflake_ornaments")) == ["products.motifs:snowfall"]
    assert L.declared_motifs(L.cir_for("placemat_pair")) == [
        "products.motifs:diamond-lattice"]
    # the relief throw keeps its truthful name
    assert L.motif_promise(L.cir_for("snowfall_throw"))["backed"]
    # a CIR that declares no motif backs no motif word
    plain = dataclasses.replace(L.cir_for("hexagon_coasters"), title="Star Coaster Set")
    r = L.motif_promise(plain)
    assert not r["backed"] and r["declared"] == [], r


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:800])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
