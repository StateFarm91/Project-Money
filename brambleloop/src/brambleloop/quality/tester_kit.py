"""The first physical proof: which pattern, the printable kit, materials, protocol, intake (#64).

Gate `physical_proof` opens on the first PhysicalTest row with a completion date. This module
is everything that row needs before a person can produce it -- prepared now so the only
remaining step is a tester's hands.

**Which pattern.** `market-basket-small` (Crochet Hexagonal Bread Basket) at its current
release. Chosen by rule, not taste, from the Launch-0 products whose risk class requires
physical evidence before live sale (`gates.risk_matrix`):

* hexagon-coaster-set is Class A -- clears on deterministic evidence; a make proves nothing
  it needs;
* the Launch-0 blanket is Class B on high yardage: ~15 h make, ~600 m, ceiling ~CA$441;
* the three market baskets are Class B on `dimensional_form`, share one gauge, stitch and
  yarn weight (sc, 12.5 sts/10 cm, 5.0 mm, worsted cotton), and the small one is the
  cheapest make (~2.2 h, ~52 m; ceiling CA$59.65 at the risk matrix's own rates).

A full make of the small basket satisfies its partial-physical requirement (a full make
contains one, `risk_matrix.satisfies`), calibrates the sc/worsted-cotton yardage factor all
three baskets use, falsifies or confirms a closed 3-D form's stated size (the risk the class
exists for), and yields the finished-object photograph #64's upgrade path is waiting for.

**What is never done here:** no physical evidence is created, inferred or assumed; the kit is
the customer PDF of exactly the release the tester makes, and the content hash printed on the
record sheet binds the result to that text (F-078).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

BUILD_KEY = "basket_small"

# Filled from the CIR at build time; the static copy is what the owner card quotes.
KIT: dict = {
    "slug": "market-basket-small",
    "version": "1.2.1",
    "title": "Crochet Hexagonal Bread Basket",
    "risk_class": "B (dimensional_form)",
    "positioning": "kitchen and home (bread basket); small size only",
    "required": "partial_physical (a full make satisfies it and gives the #64 photograph)",
    "scope": "full_make",
    "size": "small",
    "make_hours_estimate": 2.15,
    "max_cost_cad": 59.65,
    "cost_basis": ("gates.risk_matrix.owner_action_spec: 2.8 tester hours (estimate x1.3) at "
                   "CA$20/h + 63 m yarn at CA$0.06/m. ESTIMATED ceiling; no tester has been "
                   "paid yet"),
}

# Materials with ESTIMATED Canadian retail prices (no purchase made; a tester usually owns the
# tools). The yarn quantity is the twin's figure with its stated +/-20% tolerance.
MATERIALS: tuple[dict, ...] = (
    {"item": "worsted-weight 100% cotton yarn, colour A (cream)", "quantity": "1 ball "
     "(twin: 40.2 m needed; any ball of >= 50 m)", "est_cad": 5.00},
    {"item": "worsted-weight 100% cotton yarn, colour B (wine)", "quantity": "1 ball "
     "(twin: 11.9 m needed)", "est_cad": 5.00},
    {"item": "5.0 mm crochet hook", "quantity": "1", "est_cad": 6.00},
    {"item": "tapestry needle, 4 stitch markers, scissors", "quantity": "1 set",
     "est_cad": 4.00},
    {"item": "kitchen scale reading to 1 g", "quantity": "tester's own", "est_cad": 0.00},
    {"item": "tape measure / ruler (cm)", "quantity": "tester's own", "est_cad": 0.00},
)
MATERIALS_TOTAL_CAD = round(sum(m["est_cad"] for m in MATERIALS), 2)

PERSON_NEEDED = {
    "who": ("one independent adult crocheter (not the owner, F-071) who agreed through the "
            "tester programme (quality.tester_programme)"),
    "skill": ("confident with single crochet worked in joined rounds, increasing at six "
              "points to make a flat hexagon, and turning a base into straight walls; can "
              "read a written pattern in US terms; owns or can borrow a 1 g kitchen scale"),
    "time": "about 2-3 hours of making plus 15 minutes of measuring and recording",
}

# The swatch step (PHYSFIX G2): the balls are weighed again after the swatch, so the yarn the
# swatch used is never counted as yarn the object used.
REWEIGH = ("then RE-WEIGH each ball and use that as its start weight, so the swatch's yarn is "
           "not counted as project yarn")

PROTOCOL_STEPS: tuple[str, ...] = (
    "Before starting: weigh each full ball and record the ball band (grams and metres)",
    "Work a 10 x 10 cm sc swatch first; record stitches and rounds per 10 cm and the hook; "
    + REWEIGH,
    "Make the basket exactly as written in the test PDF; note every place you had to guess, "
    "re-read or rip back, with the round number",
    "Weigh what is left of each ball; grams used = re-weighed start minus end, per colour",
    "Measure the finished base across the points and across the flats, and the wall height, "
    "in cm, without stretching",
    "Set the empty basket on a flat table. Does the base sit flat without rocking? Does it hold "
    "its shape (walls upright, no collapse, lean or flare)? Answer yes or no to each, and write "
    "any problem in the problems box",
    "Record total hours (not the swatch) and whether you followed the instructions exactly",
    "Photograph in daylight on a real surface (wood, linen or a countertop). Keep every camera "
    "file UNEDITED: no filter, crop, resize or retouch; landscape or square, at least 2000 px "
    "each side, the whole basket in frame with space around it",
    "Shots: (1) three-quarter view from about 30 degrees above, empty or with two or three rolls "
    "below the rim -- the listing's first photo; (2) straight down from above; (3) side view at "
    "table level; (4) a tape measure across the points, then a tape at wall height; (5) close-up "
    "of the rim and colour change; (6) in use on a set table with bread",
    "Return the record sheet and the original photo files; the operator enters them (POST "
    "/api/physical-test and /api/physical-photo)",
)

# Record-sheet fields -> the /api/physical-test payload keys (runtime.release physical.record),
# with the type each is entered as. "made.<piece>" is the count of that piece made.
RECORD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("tester_ref", "your tester reference", "tester_ref"),
    ("made_basket", "baskets made (of 1)", "made.basket"),
    ("grams_cream", "grams used, colour A (cream)", "grams_by_color.cream"),
    ("grams_wine", "grams used, colour B (wine)", "grams_by_color.wine"),
    ("ball_band_grams", "ball band: grams per ball", "ball_band_grams"),
    ("ball_band_metres", "ball band: metres per ball", "ball_band_metres"),
    ("hook_mm", "hook used (mm)", "hook_mm"),
    ("swatch_sts", "swatch: stitches per 10 cm", "swatch_stitches_per_10cm"),
    ("swatch_rows", "swatch: rounds per 10 cm", "swatch_rows_per_10cm"),
    ("width_cm", "base across the points (cm)", "measured_width_cm"),
    ("flats_cm", "base across the flats (cm)", "measured_flats_cm"),
    ("height_cm", "wall height (cm)", "measured_height_cm"),
    ("lies_flat", "base sits flat, no rocking? yes/no", "lies_flat"),
    ("holds_shape", "holds its shape? yes/no", "holds_shape"),
    ("hours", "total hours", "hours"),
    ("followed", "followed exactly? yes/no", "instructions_followed"),
    ("problems", "anything unclear or wrong (round numbers)", "problem_notes"),
)

# ---- the hexagon coaster set (W4-SAMPLE, rebuilt here by PHYSFIX so both kits come from one
# builder; formerly a script that swapped this module's constants) ---------------------------

COASTER_KIT: dict = {
    "slug": "hexagon-coaster-set",
    "version": "1.2.1",
    "title": "Hexagon Coaster Set (4)",
    "risk_class": "A (no section-8 feature; automated threshold)",
    "required": ("partial_physical (first-customer floor, gates.risk_matrix."
                 "first_customer_requirement); the kit is a full make of all four, which "
                 "satisfies it and is the coaster's one physical claim: it lies flat"),
    "scope": "full_make",
    "size": "set_of_four",
    "make_hours_estimate": 3.46,
    "max_cost_cad": 92.03,
    "cost_basis": ("gates.risk_matrix.owner_action_spec: 4.5 tester hours (estimate x1.3) at "
                   "CA$20/h + 35 m yarn at CA$0.06/m. ESTIMATED ceiling; no tester has been "
                   "paid yet"),
}

COASTER_MATERIALS: tuple[dict, ...] = (
    {"item": "DK-weight 100% cotton yarn, colour A (cream)", "quantity": "1 ball "
     "(twin: 22.6 m needed for all four; any ball of >= 30 m)", "est_cad": 5.00},
    {"item": "DK-weight 100% cotton yarn, colour B (wine)", "quantity": "1 ball "
     "(twin: 6.2 m needed for all four)", "est_cad": 5.00},
    {"item": "5.0 mm crochet hook", "quantity": "1", "est_cad": 6.00},
    {"item": "tapestry needle, 1 stitch marker, scissors", "quantity": "1 set",
     "est_cad": 4.00},
    {"item": "kitchen scale reading to 1 g", "quantity": "tester's own", "est_cad": 0.00},
    {"item": "tape measure / ruler (cm)", "quantity": "tester's own", "est_cad": 0.00},
)

COASTER_PERSON = {
    "who": ("one independent adult crocheter (not the owner, F-071) who agreed through the "
            "tester programme (quality.tester_programme)"),
    "skill": ("confident with single crochet in joined rounds from a magic ring, and with "
              "increasing at six stacked corners to make a flat hexagon; can read a written "
              "pattern in US terms; owns or can borrow a 1 g kitchen scale"),
    "time": "about 3.5-4.5 hours of making (all four coasters) plus 20 minutes of measuring",
}

COASTER_STEPS: tuple[str, ...] = (
    "Weigh each full ball; record the ball band (grams and metres)",
    "Work a 10 x 10 cm sc swatch; record stitches and rounds per 10 cm and the hook; " + REWEIGH,
    "Make all FOUR coasters exactly as written; note every guess, re-read or rip-back by round",
    "Weigh what is left; grams used = re-weighed start minus end, per colour, for all four",
    "Measure EACH coaster across the points and across the flats, flat on a table, unstretched, "
    "and write all four in their own boxes (cm)",
    "Lay each coaster on a flat table: does it lie flat? If one cups (edges lift) or ruffles "
    "(wavy edge), answer no and say which in the problems box",
    "Record total hours (all four, not the swatch) and whether you followed it exactly",
    "Photograph in daylight on a real surface; keep every camera file UNEDITED (no filter, crop, "
    "resize or retouch), landscape or square, at least 2000 px each side, with space around",
    "Shots: (1) all four laid flat in a 2 x 2 group, three-quarter angle -- the listing's first "
    "photo; (2) one coaster side-on at table level, not pressed down; (3) a ruler across the "
    "points; (4) close-up of a corner and the contrast round; (5) a mug on one coaster",
    "Return sheet and photos; the operator enters them (POST /api/physical-test, "
    "/api/physical-photo)",
)

COASTER_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("tester_ref", "your tester reference", "tester_ref"),
    ("made_coaster", "coasters made (of 4)", "made.coaster"),
    ("grams_cream", "grams used, colour A (cream)", "grams_by_color.cream"),
    ("grams_wine", "grams used, colour B (wine)", "grams_by_color.wine"),
    ("ball_band_grams", "ball band: grams per ball", "ball_band_grams"),
    ("ball_band_metres", "ball band: metres per ball", "ball_band_metres"),
    ("hook_mm", "hook used (mm)", "hook_mm"),
    ("swatch_sts", "swatch: stitches per 10 cm", "swatch_stitches_per_10cm"),
    ("swatch_rows", "swatch: rounds per 10 cm", "swatch_rows_per_10cm"),
    # SECREVIEW F6: every coaster in its own checked fields, each compared with the twin.
    ("c1_points", "coaster 1 across the points (cm)", "piece.coaster.1.width_cm"),
    ("c1_flats", "coaster 1 across the flats (cm)", "piece.coaster.1.height_cm"),
    ("c2_points", "coaster 2 across the points (cm)", "piece.coaster.2.width_cm"),
    ("c2_flats", "coaster 2 across the flats (cm)", "piece.coaster.2.height_cm"),
    ("c3_points", "coaster 3 across the points (cm)", "piece.coaster.3.width_cm"),
    ("c3_flats", "coaster 3 across the flats (cm)", "piece.coaster.3.height_cm"),
    ("c4_points", "coaster 4 across the points (cm)", "piece.coaster.4.width_cm"),
    ("c4_flats", "coaster 4 across the flats (cm)", "piece.coaster.4.height_cm"),
    ("lies_flat", "all four lie flat? yes/no", "lies_flat"),
    ("hours", "total hours (all four)", "hours"),
    ("followed", "followed exactly? yes/no", "instructions_followed"),
    ("problems", "anything unclear or wrong (round numbers)", "problem_notes"),
)

# One builder, one table: each kit's product key, constants and manifest file name.
KITS: dict[str, dict] = {
    "basket_small": {"kit": KIT, "materials": MATERIALS, "person": PERSON_NEEDED,
                     "protocol": PROTOCOL_STEPS, "fields": RECORD_FIELDS,
                     "manifest": "KIT_MANIFEST.json"},
    "hexagon_coasters": {"kit": COASTER_KIT, "materials": COASTER_MATERIALS,
                         "person": COASTER_PERSON, "protocol": COASTER_STEPS,
                         "fields": COASTER_FIELDS,
                         "manifest": "KIT_MANIFEST_hexagon-coaster-set.json"},
}

_NUMBER_KEYS = {"ball_band_grams", "ball_band_metres", "hook_mm", "swatch_stitches_per_10cm",
                "swatch_rows_per_10cm", "measured_width_cm", "measured_height_cm",
                "measured_flats_cm", "hours"}
_YES_NO_KEYS = {"lies_flat", "holds_shape"}


def _yes_no(value) -> bool | None:
    """Exactly yes or no (SECREVIEW F2): "yes"/"y" and "no"/"n", any case. Blank is None
    (unanswered); anything else is refused rather than guessed from its first letter."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in ("yes", "y"):
        return True
    if text in ("no", "n"):
        return False
    raise ValueError(f"expected yes or no, got {value!r}")


def intake_payload(sheet: dict, *, content_hash: str, key: str = BUILD_KEY) -> dict:
    """A filled record sheet -> the exact /api/physical-test payload (the one intake).

    Every field on the sheet maps to one payload key. A field left blank is left out, so the
    intake -- not this function -- decides what an incomplete sheet means (it refuses a full
    make with no shape answer, PHYSFIX G3)."""
    spec = KITS[key]
    kit = spec["kit"]
    payload: dict = {"slug": kit["slug"], "version": kit["version"], "scope": kit["scope"],
                     "size": kit["size"], "content_hash": content_hash,
                     "grams_by_color": {}, "made": {}}
    notes: list[str] = []
    pieces: dict[tuple[str, int], dict] = {}
    for field_key, label, api in spec["fields"]:
        raw = sheet.get(field_key)
        if raw is None or str(raw).strip() == "":
            continue
        if api.startswith("piece."):
            _p, comp, n, key = api.split(".")
            pieces.setdefault((comp, int(n)), {"component": comp})[key] = float(raw)
        elif api.startswith("grams_by_color."):
            payload["grams_by_color"][api.split(".", 1)[1]] = float(raw)
        elif api.startswith("made."):
            count = float(raw)
            if count != int(count):
                raise ValueError(f"{label}: a whole number of pieces, not {raw!r}")
            payload["made"][api.split(".", 1)[1]] = int(count)
        elif api == "notes":
            notes.append(f"{label}: {raw}")
        elif api in _YES_NO_KEYS or api == "instructions_followed":
            payload[api] = _yes_no(raw)
        elif api in _NUMBER_KEYS:
            payload[api] = float(raw)
        else:
            payload[api] = str(raw)
    # SECREVIEW F4: no default for "followed exactly?" -- a blank answer stays out, and the
    # intake refuses a record without it.
    if pieces:
        payload["piece_measurements"] = [pieces[k] for k in sorted(pieces)]
    payload["notes"] = "; ".join(notes)
    if not payload["made"]:
        del payload["made"]      # the intake refuses a multi-piece full make without it
    return payload


def content_hash(key: str = BUILD_KEY) -> tuple[str, str]:
    """(version, content hash) of the release the kit prints -- what gate.certify binds."""
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..gates.certificate import _release_hash
    from ..products import launch0

    cir = launch0.cir_for(key)
    result = compile_cir(cir)
    return cir.version, _release_hash(cir, write_pattern(cir, result, "US"))


# The record sheet's text column: at 8.5 pt Helvetica, 170 mm holds about 118 characters. A
# longer protocol step wraps onto the next line; it is never cut (PHYSFIX G2).
SHEET_WRAP_CHARS = 110


def _wrapped(text: str, width: int = SHEET_WRAP_CHARS) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width, break_long_words=False,
                         break_on_hyphens=False) or [""]


def _record_sheet_pdf(version: str, chash: str, key: str = BUILD_KEY) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    spec = KITS[key]
    kit = spec["kit"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER, invariant=1)
    w, h = LETTER
    y = h - 20 * mm

    def room(need: float) -> None:
        nonlocal y
        if y - need < 15 * mm:
            c.showPage()
            y = h - 20 * mm
            c.setFont("Helvetica", 8.5)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, f"Brambleloop tester record -- {kit['title']}")
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, f"{kit['slug']}@{version}   content {chash[:16]}   scope: "
                             f"{kit['scope']}   size: {kit['size']}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"This sheet covers exactly one size ({kit['size']}). Another "
                             f"size needs its own sample and its own sheet.")
    y -= 9 * mm
    c.setFont("Helvetica", 10)
    for _key, label, _api in spec["fields"]:
        c.drawString(20 * mm, y, label)
        c.line(95 * mm, y - 1, 190 * mm, y - 1)
        y -= 8.5 * mm
    y -= 3 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Protocol")
    c.setFont("Helvetica", 8.5)
    for i, step in enumerate(spec["protocol"], start=1):
        lines = _wrapped(f"{i}. {step}")
        room(5.5 * mm + 4.2 * mm * (len(lines) - 1))
        y -= 5.5 * mm
        c.drawString(20 * mm, y, lines[0])
        for more in lines[1:]:
            y -= 4.2 * mm
            c.drawString(24 * mm, y, more)
    room(9 * mm)
    y -= 9 * mm
    c.drawString(20 * mm, y, "No review, rating or favourite is requested. Your fee does not "
                             "depend on your opinion.")
    c.showPage()
    c.save()
    return buf.getvalue()


def _finished_size(twin) -> dict:
    """The twin's finished figures named for what they are: a disc has no wall height."""
    out = {"across_points": twin.width_cm, "across_flats": twin.across_flats_cm}
    if twin.shape != "disc":
        out["wall_height"] = twin.height_cm
    return out


def build(out_dir: Path, key: str = BUILD_KEY) -> dict:
    """Write the printable kit: pattern PDF, record sheet PDF, manifest. Returns the manifest.

    Deterministic: the same code and release give byte-identical files (fixed release date,
    reportlab `invariant`), so a rebuild is checkable against the committed digests."""
    from datetime import date

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..gates import risk_matrix
    from ..products import launch0
    from ..publish.pdf import build_pattern_pdf

    spec = KITS[key]
    kit = spec["kit"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cir = launch0.cir_for(key)
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    version, chash = content_hash(key)
    # The quoted ceiling is recomputed, never trusted: the static copy must equal what the
    # risk matrix's own rates give for this make.
    ceiling = risk_matrix.owner_action_spec(
        slug=cir.slug, version=version, content_hash=chash,
        required=risk_matrix.FULL_PHYSICAL_MAKE, effective_class="B",
        make_hours=kit["make_hours_estimate"],
        yarn_metres=sum(twin.yarn_metres_by_color.values()))["max_cost_cad"]
    if abs(ceiling - kit["max_cost_cad"]) > 0.005:
        raise ValueError(f"{cir.slug}: the kit quotes CA${kit['max_cost_cad']:.2f} but the "
                         f"risk matrix gives CA${ceiling:.2f}")
    doc = build_pattern_pdf(cir, terminology="US", twin=twin, released_on=date(2026, 10, 7))
    pattern = out_dir / f"{kit['slug']}-{version}-TEST.pdf"
    pattern.write_bytes(doc.pdf_bytes)
    sheet = out_dir / f"{kit['slug']}-{version}-RECORD-SHEET.pdf"
    sheet.write_bytes(_record_sheet_pdf(version, chash, key))
    materials = spec["materials"]
    manifest = {
        **kit, "version": version, "content_hash": chash,
        "finished_size_cm": _finished_size(twin),
        "pieces": {c.name: int(c.make or 1) for c in cir.components},
        "yarn_metres_by_colour": dict(twin.yarn_metres_by_color),
        "yarn_metres_scope": "every piece the pattern makes (cir.twin._yardage x make)",
        "yardage_tolerance": twin.yardage_tolerance,
        "materials": list(materials),
        "materials_total_cad_estimated": round(sum(m["est_cad"] for m in materials), 2),
        "person_needed": spec["person"], "protocol": list(spec["protocol"]),
        "record_fields": [{"field": k, "label": l, "api": a} for k, l, a in spec["fields"]],
        "covers_size": {"slug": cir.slug, "version": version, "size": kit["size"],
                        "rule": "a sample covers exactly this one size"},
        "intake": {"test": "POST /api/physical-test (queued job physical.record)",
                   "photo": "POST /api/physical-photo {slug, sha256, source, rights}",
                   "gate_opens_when": "the physical.record job writes a PhysicalTest row "
                                      "with completed_at",
                   "outcomes": ("PASS binds; PARTIAL (not flat, shape not held, a problem "
                                "recorded) goes to the owner and binds nothing; FAIL binds "
                                "nothing; a size outside 12% halts this release")},
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (pattern, sheet)},
        "pattern_pages": doc.pages,
        "built_by": f"quality.tester_kit.build(key={key!r})",
    }
    (out_dir / spec["manifest"]).write_text(json.dumps(manifest, indent=1, default=str)
                                            + "\n")
    return manifest


if __name__ == "__main__":  # pragma: no cover
    import sys

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    for kit_key in (sys.argv[2:] or list(KITS)):
        print(json.dumps(build(out, kit_key)["files"], indent=1))
