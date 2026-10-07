"""The first physical proof: which pattern, the printable kit, materials, protocol, intake (#64).

Gate `physical_proof` opens on the first PhysicalTest row with a completion date. This module
is everything that row needs before a person can produce it -- prepared now so the only
remaining step is a tester's hands.

**Which pattern.** `market-basket-small` (Crochet Hexagonal Bread Basket) at its current
release. Chosen by rule, not taste, from the Launch-0 products whose risk class requires
physical evidence before live sale (`gates.risk_matrix`):

* hexagon-coaster-set is Class A -- clears on deterministic evidence; a make proves nothing
  it needs;
* cloudline-baby-blanket is Class B on high yardage: ~15 h make, ~600 m, ceiling ~CA$441;
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
    "version": "1.2.0",
    "title": "Crochet Hexagonal Bread Basket",
    "risk_class": "B (dimensional_form)",
    "required": "partial_physical (a full make satisfies it and gives the #64 photograph)",
    "scope": "full_make",
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

PROTOCOL_STEPS: tuple[str, ...] = (
    "Before starting: weigh each full ball and record the ball band (grams and metres)",
    "Work a 10 x 10 cm sc swatch first; record stitches and rounds per 10 cm and the hook",
    "Make the basket exactly as written in the test PDF; note every place you had to guess, "
    "re-read or rip back, with the round number",
    "Weigh what is left of each ball; grams used = start minus end, per colour",
    "Measure the finished base across the points and across the flats, and the wall height, "
    "in cm, without stretching",
    "Record total hours and whether you followed the instructions exactly",
    "Photograph the finished basket on a plain surface (top and side) in daylight",
    "Return the record sheet and photos; the operator enters them (POST /api/physical-test "
    "and /api/physical-photo)",
)

# Record-sheet fields -> the /api/physical-test payload keys (runtime.release physical.record).
RECORD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("tester_ref", "your tester reference", "tester_ref"),
    ("grams_cream", "grams used, colour A (cream)", "grams_by_color.cream"),
    ("grams_wine", "grams used, colour B (wine)", "grams_by_color.wine"),
    ("ball_band_grams", "ball band: grams per ball", "ball_band_grams"),
    ("ball_band_metres", "ball band: metres per ball", "ball_band_metres"),
    ("hook_mm", "hook used (mm)", "hook_mm"),
    ("swatch", "swatch: sts and rounds per 10 cm", "notes"),
    ("width_cm", "base across the points (cm)", "measured_width_cm"),
    ("flats_cm", "base across the flats (cm)", "notes"),
    ("height_cm", "wall height (cm)", "measured_height_cm"),
    ("hours", "total hours", "hours"),
    ("followed", "followed exactly? yes/no", "instructions_followed"),
    ("problems", "anything unclear or wrong (round numbers)", "notes"),
)


def intake_payload(sheet: dict, *, content_hash: str) -> dict:
    """A filled record sheet -> the exact /api/physical-test payload (the one intake)."""
    payload = {
        "slug": KIT["slug"], "version": KIT["version"], "scope": KIT["scope"],
        "content_hash": content_hash,
        "tester_ref": str(sheet["tester_ref"]),
        "grams_by_color": {"cream": float(sheet["grams_cream"]),
                           "wine": float(sheet["grams_wine"])},
        "ball_band_grams": float(sheet["ball_band_grams"]),
        "ball_band_metres": float(sheet["ball_band_metres"]),
        "hook_mm": float(sheet["hook_mm"]) if sheet.get("hook_mm") else None,
        "measured_width_cm": (float(sheet["width_cm"]) if sheet.get("width_cm") else None),
        "measured_height_cm": (float(sheet["height_cm"]) if sheet.get("height_cm") else None),
        "hours": float(sheet["hours"]) if sheet.get("hours") else None,
        "instructions_followed": str(sheet.get("followed", "yes")).lower().startswith("y"),
        "notes": "; ".join(f"{k}: {sheet[k]}" for k in ("swatch", "flats_cm", "problems")
                           if sheet.get(k)),
    }
    return payload


def content_hash() -> tuple[str, str]:
    """(version, content hash) of the release the kit prints -- what gate.certify binds."""
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..gates.certificate import _release_hash
    from ..products import launch0

    cir = launch0.cir_for(BUILD_KEY)
    result = compile_cir(cir)
    return cir.version, _release_hash(cir, write_pattern(cir, result, "US"))


def _record_sheet_pdf(version: str, chash: str) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER, invariant=1)
    w, h = LETTER
    y = h - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, f"Brambleloop tester record -- {KIT['title']}")
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, f"{KIT['slug']}@{version}   content {chash[:16]}   scope: "
                             f"{KIT['scope']}")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    for _key, label, _api in RECORD_FIELDS:
        c.drawString(20 * mm, y, label)
        c.line(95 * mm, y - 1, 190 * mm, y - 1)
        y -= 9 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Protocol")
    c.setFont("Helvetica", 8.5)
    for i, step in enumerate(PROTOCOL_STEPS, start=1):
        y -= 5.5 * mm
        c.drawString(20 * mm, y, f"{i}. {step}"[:118])
    y -= 9 * mm
    c.drawString(20 * mm, y, "No review, rating or favourite is requested. Your fee does not "
                             "depend on your opinion.")
    c.showPage()
    c.save()
    return buf.getvalue()


def build(out_dir: Path) -> dict:
    """Write the printable kit: pattern PDF, record sheet PDF, manifest. Returns the manifest."""
    from datetime import date

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..products import launch0
    from ..publish.pdf import build_pattern_pdf

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cir = launch0.cir_for(BUILD_KEY)
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    version, chash = content_hash()
    doc = build_pattern_pdf(cir, terminology="US", twin=twin, released_on=date(2026, 10, 7))
    pattern = out_dir / f"{KIT['slug']}-{version}-TEST.pdf"
    pattern.write_bytes(doc.pdf_bytes)
    sheet = out_dir / f"{KIT['slug']}-{version}-RECORD-SHEET.pdf"
    sheet.write_bytes(_record_sheet_pdf(version, chash))
    manifest = {
        **KIT, "version": version, "content_hash": chash,
        "finished_size_cm": {"across_points": twin.width_cm,
                             "across_flats": twin.across_flats_cm,
                             "wall_height": twin.height_cm},
        "yarn_metres_by_colour": dict(twin.yarn_metres_by_color),
        "yardage_tolerance": twin.yardage_tolerance,
        "materials": list(MATERIALS), "materials_total_cad_estimated": MATERIALS_TOTAL_CAD,
        "person_needed": PERSON_NEEDED, "protocol": list(PROTOCOL_STEPS),
        "record_fields": [{"field": k, "label": l, "api": a} for k, l, a in RECORD_FIELDS],
        "intake": {"test": "POST /api/physical-test (queued job physical.record)",
                   "photo": "POST /api/physical-photo {slug, sha256, source, rights}",
                   "gate_opens_when": "the physical.record job writes a PhysicalTest row "
                                      "with completed_at"},
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (pattern, sheet)},
        "pattern_pages": doc.pages,
    }
    (out_dir / "KIT_MANIFEST.json").write_text(json.dumps(manifest, indent=1, default=str)
                                               + "\n")
    return manifest


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(json.dumps(build(Path(sys.argv[1] if len(sys.argv) > 1 else ".")), indent=1,
                     default=str)[:2000])
