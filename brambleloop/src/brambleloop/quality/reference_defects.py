"""Reference defect feedback loop (F-758) -- W4-C07.

"If a generator faithfully reproduces a defect in Brambleloop's deterministic reference,
classify the defect as upstream reference error, fix the reference, add a regression test and
regenerate. Do not blame or tune the image model around bad Product Truth geometry."

`classify(defect, reference_checks)` decides whose defect it is:

* `defect = {kind, slug, image_ref}` -- what a judge saw in a generated image;
* `reference_checks = {kind: "PASS" | "FAIL" | None}` -- the deterministic reference's own
  structural checks for the same property (silhouette, stitch count, colour placement, ...).

When the reference itself FAILs that property, the generator reproduced it faithfully and the
defect is UPSTREAM_REFERENCE_ERROR. When the reference PASSes it, it is GENERATOR_ERROR. When
the reference was never checked for it, it is UNKNOWN -- and UNKNOWN routes upstream first,
because tuning a model against geometry nobody verified is the failure this row forbids.

`record(db, ...)` opens one P2 incident per (slug, kind) for an upstream error. While it is open
`tuning_allowed` is False: no prompt, conditioning or model change may cite this defect.
`resolve` closes it only with all three of the row's steps: the reference fix, the regression
test that now fails on the old reference, and the regenerated image ref.
"""
from __future__ import annotations

UPSTREAM = "UPSTREAM_REFERENCE_ERROR"
GENERATOR = "GENERATOR_ERROR"
UNKNOWN = "UNKNOWN"
PREFIX = "reference-defect:"


class LoopRefused(ValueError):
    pass


def classify(defect: dict, reference_checks: dict) -> dict:
    verdict = (reference_checks or {}).get(defect["kind"])
    if verdict == "FAIL":
        cls, why = UPSTREAM, "the deterministic reference fails this property itself"
    elif verdict == "PASS":
        cls, why = GENERATOR, "the reference passes this property; the generator departed"
    else:
        cls, why = UNKNOWN, ("the reference was never checked for this property; verify the "
                             "reference before any change to the model")
    return {"kind": defect["kind"], "slug": defect.get("slug"), "class": cls, "why": why,
            "tune_model": cls == GENERATOR,
            "next": ({"fix": "reference", "then": ["regression test", "regenerate"]}
                     if cls != GENERATOR else {"fix": "generator conditioning or prompt"})}


def _sig(slug, kind):
    return f"{PREFIX}{slug}:{kind}"[:120]


def record(db, classified: dict, *, image_ref: str = "") -> str | None:
    from sqlalchemy import select

    from ..core.models import Incident

    if classified["class"] == GENERATOR:
        return None
    sig = _sig(classified["slug"], classified["kind"])
    with db.session() as s:
        if s.scalar(select(Incident).where(Incident.signature == sig,
                                           Incident.resolved.is_(False))) is None:
            s.add(Incident(severity="P2", signature=sig, halts_publication=False,
                           summary=(f"{classified['slug']}: generated images reproduce a "
                                    f"{classified['kind']} defect traced to the deterministic "
                                    f"reference ({classified['class']}); fix the reference, "
                                    f"add a regression test, regenerate"),
                           detail={"owner": "product_truth", "class": classified["class"],
                                   "image_ref": image_ref, "tune_model": False}))
    return sig


def tuning_allowed(db, slug: str, kind: str) -> bool:
    from sqlalchemy import select

    from ..core.models import Incident

    with db.session() as s:
        return s.scalar(select(Incident).where(Incident.signature == _sig(slug, kind),
                                               Incident.resolved.is_(False))) is None


def resolve(db, slug: str, kind: str, *, reference_fix: str, regression_test: str,
            regenerated_ref: str) -> dict:
    from sqlalchemy import select

    from ..core.models import Incident

    missing = [n for n, v in (("reference_fix", reference_fix),
                              ("regression_test", regression_test),
                              ("regenerated_ref", regenerated_ref)) if not str(v or "").strip()]
    if missing:
        raise LoopRefused(f"the loop closes only with all three steps; missing {missing}")
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == _sig(slug, kind),
                                              Incident.resolved.is_(False)))
        if inc is None:
            raise LoopRefused("no open reference-defect incident for this property")
        inc.detail = {**(inc.detail or {}), "reference_fix": reference_fix,
                      "regression_test": regression_test, "regenerated_ref": regenerated_ref}
        inc.resolved = True
        return {"signature": inc.signature, "resolved": True}
