"""Blind original graduation for product-only Visual V2 (F-857) -- W4-C07.

"Product-only Visual V2 graduates on a Brambleloop-original design with no finished-product
visual reference."

V1's graduation (research/VISUAL_V1_GRADUATION.md) set the discipline: the subject is a
Brambleloop-original design that has never been made, so no photograph of the finished object
exists anywhere for a generator to copy or a judge to anchor on. This makes it a gate:

* `subject(cir, provenance)` -- the design must be Brambleloop's: the CIR is not authored as a
  benchmark, its provenance names no purchased pattern or benchmark source, and no finished
  object of it has been photographed (`finished_photos` is empty). Otherwise INELIGIBLE.
* `conditioning(references)` -- every reference the generation was conditioned on must be a
  deterministic derivative of Product Truth (`DETERMINISTIC_KINDS`: the CIR render, its mask,
  normal map, region map, chart). A finished-product photograph, a benchmark image or an
  unknown kind makes the run ineligible -- an unknown kind is not assumed safe.
* `graduate(cir, provenance, references, certified_images)` -- GRADUATED only when the subject
  and the conditioning are eligible and at least `MIN_CERTIFIED` generated images passed the
  product-truth gates; otherwise NOT_GRADUATED with every reason. It never certifies an image:
  `certified_images` are the existing gates' verdicts.
"""
from __future__ import annotations

DETERMINISTIC_KINDS = frozenset({"cir_render", "mask", "normal_map", "region_map", "chart"})
MIN_CERTIFIED = 1


def subject(cir, provenance: dict) -> list[str]:
    out = []
    if str(getattr(cir, "authored", "") or "").lower() == "benchmark":
        out.append("the CIR is authored as a benchmark, not a Brambleloop original")
    srcs = [str(s).lower() for s in (provenance or {}).get("sources") or []]
    if any(("purchased" in s) or ("benchmark" in s) for s in srcs):
        out.append("its provenance names a purchased or benchmark source")
    if (provenance or {}).get("finished_photos"):
        out.append("a finished object has been photographed; the run is not blind")
    if not (provenance or {}).get("original", False):
        out.append("provenance does not state the design is a Brambleloop original")
    return out


def conditioning(references) -> list[str]:
    out = []
    for r in references or ():
        kind = r.get("kind")
        if kind not in DETERMINISTIC_KINDS:
            out.append(f"reference {r.get('ref')!r} is {kind!r}, not a deterministic "
                       f"derivative of Product Truth")
    return out


def graduate(cir, provenance: dict, references, certified_images) -> dict:
    reasons = subject(cir, provenance) + conditioning(references)
    certified = [i for i in certified_images or () if i.get("status") == "PASS"]
    if len(certified) < MIN_CERTIFIED:
        reasons.append(f"{len(certified)} certified image(s); graduation needs "
                       f"{MIN_CERTIFIED}")
    return {"slug": getattr(cir, "slug", None),
            "state": "NOT_GRADUATED" if reasons else "GRADUATED", "reasons": reasons,
            "certified": [i.get("ref") for i in certified],
            "rule": "a blind original subject, deterministic conditioning only, gates passed"}
