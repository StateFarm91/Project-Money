"""Physical evidence specificity (F-876) -- W4-C07.

"Request physical/tester evidence only for the exact unresolved property it can prove."

A request names one property, the exact measurement that proves it, and why it is still
unresolved. `request(prop, known=...)` refuses:

* a property the deterministic chain already settles -- stitch counts (compiler), the written
  text's agreement with the CIR (reverse compiler), construction and repeat arithmetic. A
  tester asked to "check the counts" is asked to redo what the compiler proved, and their
  answer cannot outrank it;
* a property already resolved by physical evidence on file (`known[prop] == "RESOLVED"`);
* a vague request ("make it and send photos"), i.e. any property not in `PHYSICAL`.

`requests_for(unresolved)` turns the unresolved set (e.g. from `quality.physical` findings and
an uncalibrated twin) into exactly one request per property, and nothing else.
"""
from __future__ import annotations

DETERMINISTIC = {
    "stitch_counts": "cir.compiler proves every row total",
    "written_matches_cir": "cir.reverse.compare proves the text against the CIR",
    "repeat_arithmetic": "cir.compiler resolves every repeat",
    "construction_order": "the CIR states the construction and the compiler resolves it",
}
PHYSICAL: dict[str, dict] = {
    "yardage": {"measure": "grams used per colour on a kitchen scale, with the ball band "
                           "(weight and metres per ball)",
                "proves": "the twin's yardage calibration for this yarn weight and stitch"},
    "finished_size": {"measure": "width and height (or circumference) in cm, flat, after "
                                 "blocking, with the swatch gauge",
                      "proves": "whether the twin's geometry matches the object"},
    "gauge_in_yarn": {"measure": "stitches and rows over 10 cm on a blocked swatch in the "
                                 "named yarn and hook",
                      "proves": "that the stated yarn can hold the stated gauge"},
    "drape": {"measure": "one photograph of the piece hanging from one edge, beside a ruler",
              "proves": "the macro drape the 3D model assumes"},
    "make_time": {"measure": "hours worked, logged per session",
                  "proves": "the make-time distribution for this class and skill (F-083)"},
    "colour_appearance": {"measure": "one daylight photograph with a grey card",
                          "proves": "that the colourway reads as the listing says"},
    "wash_behaviour": {"measure": "measurements before and after one wash on the label's "
                                  "setting",
                       "proves": "the care instructions"},
}


class RequestRefused(ValueError):
    pass


def request(prop: str, *, known: dict | None = None, product_slug: str = "",
            version: str = "") -> dict:
    known = known or {}
    if prop in DETERMINISTIC:
        raise RequestRefused(f"{prop!r} is settled deterministically ({DETERMINISTIC[prop]}); "
                             f"a tester is not asked to prove it")
    if prop not in PHYSICAL:
        raise RequestRefused(f"{prop!r} names no property a physical measurement proves; a "
                             f"request names one of {sorted(PHYSICAL)}")
    if known.get(prop) == "RESOLVED":
        raise RequestRefused(f"{prop!r} is already resolved by physical evidence on file")
    spec = PHYSICAL[prop]
    return {"product_slug": product_slug, "version": version, "property": prop,
            "measure": spec["measure"], "proves": spec["proves"],
            "only": True, "why": known.get(prop) or "UNRESOLVED"}


def requests_for(unresolved, *, known: dict | None = None, product_slug: str = "",
                 version: str = "") -> dict:
    made, refused = [], []
    for prop in sorted(set(unresolved or ())):
        try:
            made.append(request(prop, known=known, product_slug=product_slug, version=version))
        except RequestRefused as exc:
            refused.append({"property": prop, "why": str(exc)})
    return {"requests": made, "refused": refused,
            "rule": "one request per unresolved physical property, and nothing else"}
