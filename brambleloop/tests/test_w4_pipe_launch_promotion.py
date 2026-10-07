"""W4-PIPE: the two strongest truthful products joined Launch-0 because their imagery verifies.

Owner directive 2026-10-07: move the strongest products to the final publication gate. A
product outside Launch-0 has no authoritative CIR, so its disclosed renders are structural
UNKNOWN (D-FB-7) and it can never reach the gate. Promotion is measured, not declared: each
promoted product certifies, is name-true, is resolved by `authoritative_cir`, and its
disclosed render set verifies against that CIR from the pixels and is usable. The cap
(test_launch0: at most five candidates) and the catalogue-depth floor of eight are untouched.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROMOTED = ("nordic-star-ornaments", "winter-village-graphghan")
FAILED = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main():
    work = Path(tempfile.mkdtemp(prefix="w4pipe-promo-"))
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(work / "art")
    from brambleloop.core.db import Database
    from brambleloop.gates.certificate import certify
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import disclosed_listing, eligibility, listing_asset
    from brambleloop.visual.render_verification import authoritative_cir

    check("cap_unchanged", 1 <= len(l0.LAUNCH0_SLUGS) <= 5, l0.LAUNCH0_SLUGS)
    check("reserve_still_not_launched", "harvest-table-runner" not in l0.launch_scope_slugs())
    db = Database(f"sqlite:///{work}/promo.sqlite")
    db.create_all()
    assert PROMOTED, "nothing promoted"
    for slug in PROMOTED:
        check(f"in_scope:{slug}", slug in l0.launch_scope_slugs()
              and listing_asset._in_launch_scope(slug))
        cand = l0.candidate(slug)
        assert cand.variants, slug
        cir = l0.cir_for(cand.variants[0].build)
        check(f"title_is_the_cir_title:{slug}", cand.title == cir.title, (cand.title, cir.title))
        check(f"certifies:{slug}", certify(cir).granted)
        from brambleloop.gates import first_customer as fc
        check(f"kind_is_a_cir_product_type:{slug}",
              cand.listing.kind in fc.product_type_words_in_cir(cir),
              (cand.listing.kind, sorted(fc.product_type_words_in_cir(cir))))
        check(f"name_true:{slug}", eligibility.name_truth(cir) == [],
              eligibility.name_truth(cir))
        auth = authoritative_cir(slug, cir.version)
        check(f"authoritative:{slug}", auth is not None and auth.fingerprint == cir.fingerprint)
        rec = disclosed_listing.build(cir, db=db)
        frames = rec.get("frames") or []
        assert frames, (slug, rec.get("why"))
        check(f"frames_verify:{slug}",
              all(f["structural_truth"]["status"] == "PASS" for f in frames),
              [f["structural_truth"]["status"] for f in frames])
        check(f"render_set_usable:{slug}", rec.get("usable_as_listing_asset") is True,
              rec.get("launch_blocked"))
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
