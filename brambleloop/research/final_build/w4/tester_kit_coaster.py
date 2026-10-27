"""W4-SAMPLE: build the hexagon-coaster-set tester kit through the basket kit's own code path.

`quality.tester_kit` is written for one product (BUILD_KEY "basket_small"). This script does not
copy its renderer: it swaps the module's product constants for the coaster's, calls the same
`tester_kit.build` (compile_cir -> build_twin -> _release_hash -> publish.pdf.build_pattern_pdf ->
the reportlab record sheet), then restores the constants. The cost ceiling is computed by
`gates.risk_matrix.owner_action_spec`, the make time by `products.launch0.make_hours`, never typed.

Also re-builds the basket kit into a scratch directory and checks its file hashes against the
committed KIT_MANIFEST.json (determinism check), and prints both kits' digests.

Usage (from brambleloop/):  nice -n 19 python3 research/final_build/w4/tester_kit_coaster.py
                            [--refresh-basket]  (rebuild the basket kit in place if stale)
Writes into research/final_build/w4/tester_kit/ beside the basket kit:
  hexagon-coaster-set-1.2.0-TEST.pdf, hexagon-coaster-set-1.2.0-RECORD-SHEET.pdf,
  KIT_MANIFEST_hexagon-coaster-set.json
Nothing is sent, published, purchased or recorded; no database is touched.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                  # brambleloop/
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.gates import risk_matrix  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.quality import tester_kit  # noqa: E402

KIT_DIR = HERE / "tester_kit"
COASTER_KEY = "hexagon_coasters"

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

# Each step is kept under the record sheet's 118-character print limit.
COASTER_STEPS: tuple[str, ...] = (
    "Weigh each full ball; record the ball band (grams and metres)",
    "Work a 10 x 10 cm sc swatch; record sts and rounds per 10 cm and hook; then RE-WEIGH each ball",
    "Make all FOUR coasters exactly as written; note every guess, re-read or rip-back by round",
    "Weigh what is left; grams used = re-weighed start minus end, per colour, for all four",
    "Measure each coaster across the points and the flats, flat on a table, unstretched (cm)",
    "Lay each coaster on a flat table: lies flat, cups (edges lift) or ruffles (wavy edge)?",
    "Record total hours (all four, not the swatch) and whether you followed it exactly",
    "Photograph in daylight on a plain surface: all four top-down, and one side-on at table level",
    "Return sheet and photos; the operator enters them (POST /api/physical-test, /api/physical-photo)",
)

COASTER_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("tester_ref", "your tester reference", "tester_ref"),
    ("grams_cream", "grams used, colour A (cream)", "grams_by_color.cream"),
    ("grams_wine", "grams used, colour B (wine)", "grams_by_color.wine"),
    ("ball_band_grams", "ball band: grams per ball", "ball_band_grams"),
    ("ball_band_metres", "ball band: metres per ball", "ball_band_metres"),
    ("hook_mm", "hook used (mm)", "hook_mm"),
    ("swatch", "swatch: sts and rounds per 10 cm", "notes"),
    ("width_cm", "across points, furthest coaster (cm)", "measured_width_cm"),
    ("height_cm", "across flats, same coaster (cm)", "measured_height_cm"),
    ("all_sizes", "all four: points x flats (cm)", "notes"),
    ("flat", "lies flat? per coaster (flat/cups/ruffles)", "notes"),
    ("hours", "total hours (all four)", "hours"),
    ("followed", "followed exactly? yes/no", "instructions_followed"),
    ("problems", "anything unclear or wrong (round numbers)", "notes"),
)


def _coaster_kit() -> dict:
    cir = launch0.cir_for(COASTER_KEY)
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    version, chash = (cir.version, None)
    matrix = risk_matrix.matrix_for(cir, result)
    hours = launch0.make_hours(cir.slug)
    metres = sum(twin.yarn_metres_by_color.values())
    # Priced as a full make: only a whole-set sample passes physical.record today (the
    # yardage factor is measured against the whole-set twin; see PHYSICAL_SAMPLE_PACKAGES.md).
    spec = risk_matrix.owner_action_spec(
        slug=cir.slug, version=version, content_hash=chash,
        required=risk_matrix.FULL_PHYSICAL_MAKE, effective_class=matrix["effective"],
        make_hours=hours, yarn_metres=metres)
    cand = launch0.candidate_for_cir(cir.slug)
    return {
        "slug": cir.slug, "version": version, "title": cand.title,
        "risk_class": f"{matrix['effective']} (no section-8 feature; automated threshold)",
        "required": ("partial_physical (first-customer floor, gates.risk_matrix."
                     "first_customer_requirement); the whole set of four is the smallest "
                     "sample physical.record accepts, so the scope is full_make"),
        "scope": "full_make",
        "make_hours_estimate": hours,
        "max_cost_cad": spec["max_cost_cad"],
        "cost_basis": (f"gates.risk_matrix.owner_action_spec: {spec['cost_basis']}. "
                       f"ESTIMATED ceiling; no tester has been paid yet"),
    }


def _swap(**values):
    old = {k: getattr(tester_kit, k) for k in values}
    for k, v in values.items():
        setattr(tester_kit, k, v)
    return old


def _digests(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.glob("*.pdf"))}


def main() -> dict:
    out: dict = {}
    # 1. Basket: rebuild into scratch and compare with the committed manifest.
    committed = json.loads((KIT_DIR / "KIT_MANIFEST.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        m = tester_kit.build(Path(tmp))
        out["basket"] = {
            "slug": m["slug"], "version": m["version"], "content_hash": m["content_hash"],
            "content_hash_matches_committed": m["content_hash"] == committed["content_hash"],
            "files": m["files"],
            "files_match_committed": m["files"] == committed["files"],
            "pattern_pages": m["pattern_pages"]}
    if "--refresh-basket" in sys.argv and not out["basket"]["files_match_committed"]:
        # The content hash binds the evidence; the PDF bytes also carry the renderer's
        # boilerplate (licence, support scope, "how this was made"), which W4-COPY changed
        # after the kit was cut. The tester must work the text a customer would receive.
        out["basket"]["committed_files_before_refresh"] = committed["files"]
        tester_kit.build(KIT_DIR)
        out["basket"]["refreshed_in_place"] = True
    # 2. Coaster: the same build with the coaster's constants.
    kit = _coaster_kit()
    old = _swap(BUILD_KEY=COASTER_KEY, KIT=kit, MATERIALS=COASTER_MATERIALS,
                MATERIALS_TOTAL_CAD=round(sum(x["est_cad"] for x in COASTER_MATERIALS), 2),
                PERSON_NEEDED=COASTER_PERSON, PROTOCOL_STEPS=COASTER_STEPS,
                RECORD_FIELDS=COASTER_FIELDS)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            m = tester_kit.build(Path(tmp))
            # build() names the twin's height "wall_height" (a basket); a coaster's twin height
            # is its across-the-flats span, so the manifest says what the number is.
            twin = build_twin(launch0.cir_for(COASTER_KEY),
                              compile_cir(launch0.cir_for(COASTER_KEY)))
            m["finished_size_cm"] = {"across_points": twin.width_cm,
                                     "across_flats": twin.across_flats_cm,
                                     "per": "one coaster (Component.make = 4)"}
            m["yarn_metres_scope"] = "all four coasters (cir.twin._yardage multiplies by make)"
            m["built_by"] = "research/final_build/w4/tester_kit_coaster.py via quality.tester_kit.build"
            for name in m["files"]:
                shutil.copyfile(Path(tmp) / name, KIT_DIR / name)
            (KIT_DIR / "KIT_MANIFEST_hexagon-coaster-set.json").write_text(
                json.dumps(m, indent=1, default=str) + "\n")
            out["coaster"] = {"slug": m["slug"], "version": m["version"],
                              "content_hash": m["content_hash"], "files": m["files"],
                              "pattern_pages": m["pattern_pages"],
                              "max_cost_cad": m["max_cost_cad"],
                              "cost_basis": m["cost_basis"]}
    finally:
        _swap(**old)
    out["coaster_files_on_disk"] = {k: v for k, v in _digests(KIT_DIR).items()
                                    if k.startswith("hexagon-coaster-set")}
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
