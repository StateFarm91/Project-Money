"""ENG-COMPOSER: compose, certify and render the six proof items; print a JSON evidence record.

    cd brambleloop && python3 scripts/compose_examples.py [--pdf-dir DIR] > evidence.json

Uses the same concepts as `tests/test_eng_composer.py::ITEMS`. The children's assignment for
the toys and the lovey, and the not-for-a-child decision for the round cushion, are TEST
arguments for rendering only (as in tests/test_eng_plush.py); no owner decision is recorded.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _tmp; _tmp.install()  # noqa: E402,E702

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.creative import composer as C  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.publish import pdf  # noqa: E402


def main(argv: list[str]) -> int:
    from test_eng_composer import BEANIE, ITEMS
    from test_eng_plush import _decided_not_for_a_child

    out_dir = Path(argv[argv.index("--pdf-dir") + 1]) if "--pdf-dir" in argv else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for key, concept in ITEMS.items():
        plan = C.plan_for(concept)
        cir = C.compose(plan)
        result = compile_cir(cir)
        rec = {"item": key, "slug": cir.slug, "title": cir.title,
               "plan_digest": C.plan_digest(plan), "cir_fingerprint": cir.fingerprint,
               "parts": [{"name": p["name"], "shape": p["shape"],
                          "closure": p.get("closure", "open"), "make": p.get("make", 1)}
                         for p in plan["parts"]],
               "joins": [j["kind"] for j in plan.get("joins", [])],
               "rows": sum(len(c.rows) for c in cir.components),
               "stitches": sum(r.stitch_count for r in result.rows),
               "risk_class": cir.risk_class, "size": cir.finished_size_note,
               "certificate": {}, "pdf": {}}
        for terms in ("US", "UK"):
            cert = certify(cir, terminology=terms)
            rec["certificate"][terms] = {
                "granted": cert.granted, "stages": cert.stages_run,
                "errors": sorted({f.code for f in cert.findings if f.severity == "ERROR"})}
        childrens = None
        undo = None
        if CS.applies(cir):
            childrens = ("lovey", "under_3") if key == "lovey" else ("amigurumi_toy", "under_3")
        elif key == "cushion":
            undo = _decided_not_for_a_child(cir)
        try:
            for terms in ("US", "UK"):
                doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=childrens)
                rec["pdf"][terms] = {"bytes": len(doc.pdf_bytes),
                                     "sha256": hashlib.sha256(doc.pdf_bytes).hexdigest()}
                if out_dir:
                    (out_dir / f"{cir.slug}-{terms}.pdf").write_bytes(doc.pdf_bytes)
        finally:
            if undo:
                undo()
        records.append(rec)
    try:
        C.compose(C.plan_for(BEANIE))
        beanie = {"refused": False}
    except C.ComposeRefused as exc:
        beanie = {"refused": True, "primitive": exc.primitive, "why": exc.why}
    print(json.dumps({"items": records, "beanie": beanie}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
