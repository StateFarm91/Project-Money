"""W4-PIPE: publication holds every product -- not only Launch-0 -- to its name."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.publish import eligibility  # noqa: E402
from brambleloop.runtime.pipeline import _engineered_cir  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main():
    from brambleloop.products import launch0 as l0
    scope = [s for s in sorted(l0.launch_scope_slugs()) if _engineered_cir(s) is not None]
    assert len(scope) >= 5, scope
    for slug in scope:
        cir = _engineered_cir(slug)
        check(f"launch0_variant_name_true:{slug}", eligibility.name_truth(cir) == [],
              eligibility.name_truth(cir))
    # A re-certified catalogue product whose title claims six pieces and whose CIR makes one.
    cir = _engineered_cir("harvest-table-runner")
    check("truthful_reserve_passes", eligibility.name_truth(cir) == [], eligibility.name_truth(cir))
    from brambleloop.cir.model import CIR
    lie = CIR.from_dict({**cir.to_dict(), "title": "Harvest Table Runner Set (6)"})
    problems = eligibility.name_truth(lie)
    check("count_lie_refused", any(p.startswith("count:") for p in problems), problems)
    lie2 = CIR.from_dict({**cir.to_dict(), "title": "Harvest Mosaic Table Runner"})
    problems2 = eligibility.name_truth(lie2)
    check("fabric_lie_refused", any(p.startswith("fabric:") for p in problems2), problems2)
    copy = {"title": "Harvest Mosaic Table Runner | Crochet Pattern PDF", "tags": ["table runner"]}
    lp = eligibility.name_truth(cir, copy)
    check("listing_copy_colourwork_refused", any(p.startswith("listing:") for p in lp), lp)
    check("listing_copy_truthful_passes",
          eligibility.name_truth(cir, {"title": "Harvest Table Runner", "tags": ["runner"]}) == [])
    # Through the publication verdict, on a scratch database with a recertified release.
    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.gates.certificate import GAUGE_STANDARD
    import tempfile
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/t.sqlite"); db.create_all()
    with db.session() as s:
        for c in (cir, lie):
            slug = "runner-truth" if c is cir else "runner-lie"
            p = Product(slug=slug, title=c.title, status="certified"); s.add(p); s.flush()
            s.add(PatternVersion(product_id=p.id, version=c.version, certified=True,
                                 cir_json={**c.to_dict(), "slug": slug},
                                 certificate={"granted": True, "gauge_standard": GAUGE_STANDARD},
                                 release_hash="x" * 64))
        s.commit()
    good = eligibility.product_publication(db, "runner-truth", cir.version)
    bad = eligibility.product_publication(db, "runner-lie", lie.version)
    codes_good = [r["code"] for r in good["reasons"]]
    codes_bad = [r["code"] for r in bad["reasons"]]
    check("verdict_truthful_has_no_name_reason", eligibility.NAME_OUTRUNS_PATTERN not in codes_good, codes_good)
    check("verdict_lie_refused", eligibility.NAME_OUTRUNS_PATTERN in codes_bad and not bad["publishable"], codes_bad)
    if FAILED:
        raise SystemExit(f"{len(FAILED)} failed: {FAILED}")


if __name__ == "__main__":
    main()
