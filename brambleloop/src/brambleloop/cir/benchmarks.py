"""Reference garments the CIR is measured against, encoded from real commercial patterns.

A benchmark here is a known-good object: a pattern somebody wrote, sold and crocheted, whose
finished measurements are published and whose finished garment has been photographed. That
combination is what makes it possible to ask whether Brambleloop's representation reproduces
a real thing rather than merely compiles.

These are OUR encodings of publicly-describable technique: construction method, stitch
sequence, counts, gauge and grading. Stitch counts and construction methods are facts about
how a garment is made, not authorship. The seller's written text and photographs are theirs
and are not reproduced here, and nothing in this module is a Brambleloop product -- a product
informed by a benchmark gets its own design decisions, its own instructions and its own
validation, not a paraphrase.
"""
from __future__ import annotations

from .model import CIR, Component, Gauge, Material, Op, Repeat, Row, Seam

# --- the side-to-side textured cardigan ------------------------------------
#
# Worked flat in one piece for the body: first front, an armhole, the back, a second armhole,
# the second front. The foundation chain runs the LENGTH of the garment, so rows stack around
# the body and the grain is "across". Sleeves, neckline ribbing and pockets are separate and
# sewn on. The hem ribbing is not a separate band: it is nine back-loop stitches worked at one
# edge of every body row, so it is created by the same rows as the fabric it borders.

SIZES = ("XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL")

# Per size, in size order.
BODY_STS    = (90, 94, 94, 94, 94, 98, 98, 98, 98)   # after the foundation chain
FRONT_ROWS  = (18, 20, 22, 24, 26, 28, 30, 32, 34)   # each front panel
BACK_ROWS   = (44, 50, 54, 58, 62, 68, 72, 78, 82)
ARMHOLE_CH  = (27, 29, 31, 33, 35, 37, 39, 41, 43)   # chains spanning the opening
SLEEVE_STS  = (62, 62, 64, 64, 66, 66, 68, 68, 70)
SLEEVE_ROWS = (26, 30, 32, 34, 36, 40, 42, 44, 46)
YARN_G      = (520, 585, 635, 675, 725, 810, 860, 915, 970)

# What the pattern states its finished garment measures, in centimetres. Held separately from
# the counts on purpose: these are the designer's claims, and the point of the benchmark is to
# recompute them from the counts and see whether they agree.
STATED_LENGTH  = (62, 65, 65, 65, 65, 67, 67, 67, 67)
STATED_BACK_W  = (47, 53, 58, 62, 66, 73, 77, 83, 87)
STATED_ARMHOLE = (14, 15, 16.5, 18, 19, 21, 22, 23, 24)
STATED_SLEEVE  = (39, 39, 41, 41, 42, 42, 43, 43, 45)
STATED_BUST    = (71, 81, 91, 101, 112, 122, 132, 142, 152)

GAUGE_STS, GAUGE_ROWS = 14.5, 9.5     # per 10cm, in the textured stitch pattern
HOOK_MM = 6.0
EDGE_RIB = 9                          # back-loop stitches forming the integral hem rib
POCKET_STS, POCKET_ROWS = 24, 13
NECK_RIB_STS = 7


def _body_row(index: int, *, a_row: bool, total: int, rib: int = EDGE_RIB) -> Row:
    """One body row of the textured pattern, with the integral rib band at one edge.

    Row A:  rib band, then (FLO, BLO) to the end, then one plain stitch.
    Row B:  (BLO, FLO) to the end, then the rib band, then one plain stitch.

    The band sits at the same fabric edge in both, because flat rows turn: the end of a row
    worked one way is the start of the row worked back. The loop targets alternate along the
    row and flip between rows, which is what breaks the surface up instead of striping it.
    """
    field = total - rib - 1
    if field % 2:
        raise ValueError(f"field of {field} cannot hold whole loop-alternating pairs")
    first, second = ("front", "back") if a_row else ("back", "front")
    pair = Repeat([Op("hdc", loop=first), Op("hdc", loop=second)], times=field // 2)
    ops = ([Op("hdc", rib, loop="back"), pair, Op("hdc", 1)] if a_row
           else [pair, Op("hdc", rib, loop="back"), Op("hdc", 1)])
    return Row(index=index, ops=ops, declared_count=total, turning_chain=1)


def _armhole_row(index: int, *, total: int, chains: int) -> Row:
    """The row that opens an armhole: stop short, chain across the gap, turn.

    The chains replace stitches the row did not work. One of them is consumed turning into
    the next row, so `chains` chains span `chains - 1` stitches -- which is why the worked
    count is `total - (chains - 1)` and not `total - chains`.
    """
    worked = total - (chains - 1)
    # Declared as worked stitches PLUS the bridge chains, which is how the pattern itself
    # writes it ("<64 + 27 chs>"). The CIR has no way to say "these chains are a bridge
    # rather than stitches of this row", so the count is the sum and the distinction lives
    # in this note. Named as a gap rather than smoothed over: a representation that cannot
    # separate a span from a stitch will get every chain-spanned opening subtly wrong.
    return Row(index=index, ops=[Op("hdc", worked), Op("ch", chains)],
               declared_count=worked + chains, turning_chain=1, skips=chains - 1,
               note=f"armhole: {worked} sts worked, {chains} chains span the opening")


def cardigan(size: str = "XS") -> CIR:
    """The full garment at one size: body, sleeves, pockets, neckline ribbing, assembly."""
    i = SIZES.index(size)
    total, rib = BODY_STS[i], EDGE_RIB
    front, back, arm = FRONT_ROWS[i], BACK_ROWS[i], ARMHOLE_CH[i]

    rows: list[Row] = [Row(index=1, ops=[Op("hdc", total)], declared_count=total,
                           turning_chain=1, note="worked into the back bumps of the chain")]
    n = 1

    def field(count: int, after_armhole: bool = False) -> None:
        nonlocal n
        for k in range(count):
            n += 1
            row = _body_row(n, a_row=(n % 2 == 1), total=total)
            if after_armhole and k == 0:
                # The row that works back across the bridge skips the first chain -- "HDC in
                # the 2nd ch from hook" -- so exactly one of the chains is never worked into.
                # Declared, because an unworked stitch nobody declared is the defect this
                # check exists to catch.
                row.allow_remainder = True
                row.note = ("works back across the armhole bridge; the first chain is the "
                            "turning chain and is deliberately not worked into")
            rows.append(row)

    field(front - 1)                                   # first front panel
    n += 1; rows.append(_armhole_row(n, total=total, chains=arm))
    field(back - 1, after_armhole=True)                # back panel
    n += 1; rows.append(_armhole_row(n, total=total, chains=arm))
    field(front - 1, after_armhole=True)               # second front panel
    n += 1
    rows.append(Row(index=n, ops=[Op("hdc", rib, loop="back"), Op("hdc", total - rib)],
                    declared_count=total, turning_chain=1,
                    note="final body row: worked plain across"))

    body = Component("body", "flat_rows", rows, foundation=total, grain="across",
                     note="one piece: front, armhole, back, armhole, front")

    # Sleeve. Row B's edge band is slip stitch rather than half double -- a shorter stitch,
    # so the cuff draws in and the straight tube above it reads as a balloon.
    s_sts, s_rows = SLEEVE_STS[i], SLEEVE_ROWS[i]
    srows: list[Row] = [Row(index=1, ops=[Op("hdc", s_sts)], declared_count=s_sts,
                            turning_chain=1)]
    for r in range(2, s_rows + 1):
        if r % 2 == 0:
            f = s_sts - rib - 1
            srows.append(Row(index=r, declared_count=s_sts, turning_chain=1,
                             ops=[Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")],
                                         times=f // 2),
                                  Op("slst", rib, loop="back"), Op("slst", 1)],
                             note="cuff edge in slip stitch: draws the sleeve end in"))
        else:
            srows.append(_body_row(r, a_row=True, total=s_sts))
    sleeve = Component("sleeve", "flat_rows", srows, foundation=s_sts, make=2, grain="across",
                       note="folded lengthways and seamed into a tube")

    prows: list[Row] = [Row(index=1, ops=[Op("hdc", POCKET_STS)],
                            declared_count=POCKET_STS, turning_chain=1)]
    for r in range(2, POCKET_ROWS):
        prows.append(_body_row(r, a_row=True, total=POCKET_STS, rib=1))
    prows.append(Row(index=POCKET_ROWS, ops=[Op("hdc", POCKET_STS)],
                     declared_count=POCKET_STS, turning_chain=1))
    pocket = Component("pocket", "flat_rows", prows, foundation=POCKET_STS, make=2)

    # Neckline ribbing: back-loop half doubles worked until it spans the neckline. Its row
    # count is "however long the neckline is", which the pattern never states as a number --
    # so it is derived here rather than invented, from the opening the body actually makes.
    neck_rows = _neckline_rows(i)
    nrows: list[Row] = [Row(index=1, ops=[Op("hdc", NECK_RIB_STS)],
                            declared_count=NECK_RIB_STS, turning_chain=1)]
    for r in range(2, neck_rows + 1):
        nrows.append(Row(index=r, declared_count=NECK_RIB_STS, turning_chain=1,
                         ops=[Op("hdc", NECK_RIB_STS - 1, loop="back"), Op("hdc", 1)]))
    ribbing = Component("neck_ribbing", "flat_rows", nrows, foundation=NECK_RIB_STS,
                        note=f"worked to span the neckline: {neck_rows} rows at this size")

    return CIR(
        slug=f"benchmark-side-to-side-cardigan-{size.lower()}",
        title=f"Benchmark side-to-side textured cardigan ({size})",
        version="1.0.0", construction="flat_rows",
        components=[body, sleeve, pocket, ribbing],
        gauge=Gauge(GAUGE_STS, GAUGE_ROWS, stitch_type="hdc", hook_mm=HOOK_MM),
        materials=[Material(name="worsted acrylic", yarn_weight="worsted",
                            metres_estimate=round(YARN_G[i] * 2.25, 1))],
        assembly=[
            Seam("whipstitch", "sleeve", "sleeve", note="fold lengthways, seam the long edge"),
            Seam("whipstitch", "body", "body", note="shoulder seams, fronts onto back"),
            Seam("whipstitch", "sleeve", "body", note="sleeve head into the armhole"),
            Seam("whipstitch", "neck_ribbing", "body", note="ribbing along the neckline"),
            Seam("whipstitch", "pocket", "body", note="pockets onto the fronts"),
        ],
        designer_notes=("Pieces are joined with the right side inward, so the surface worn "
                        "outward is the reverse of the textured face."),
        finished_size_note=(f"to fit bust {STATED_BUST[i]}cm; length {STATED_LENGTH[i]}cm; "
                            f"back width {STATED_BACK_W[i]}cm"))


def _neckline_rows(i: int) -> int:
    """How many ribbing rows span the neckline, derived rather than stated.

    The neckline of this construction is the two front edges plus the back neck, and the
    ribbing is worked sideways along it, so its row count is that length at row gauge. The
    pattern says only "until the ribbing measures the length of the entire neckline", which
    is honest for a human and useless to a compiler: a number nobody wrote down cannot be
    checked. Derived here, and flagged as derived, so that the one measurement this pattern
    leaves to the maker is visible as such instead of quietly missing.
    """
    front_edge_cm = STATED_LENGTH[i]
    back_neck_cm = STATED_BACK_W[i] / 3.0
    return round((2 * front_edge_cm + back_neck_cm) / 10.0 * GAUGE_ROWS)


def reconcile(size: str = "XS") -> dict:
    """Recompute the pattern's stated measurements from its own counts and gauge."""
    i = SIZES.index(size)
    length = BODY_STS[i] / GAUGE_STS * 10
    back_w = BACK_ROWS[i] / GAUGE_ROWS * 10
    sleeve_circ = SLEEVE_ROWS[i] / GAUGE_ROWS * 10
    rows_sum = FRONT_ROWS[i] * 2 + BACK_ROWS[i] + 1
    # Chains are narrower than worked stitches, so the armhole -- which is spanned by chains
    # rather than stitches -- cannot be measured at the fabric's stitch gauge. What the
    # pattern's own numbers imply is recorded instead of assumed.
    implied_chain_gauge = (2 * ARMHOLE_CH[i]) / sleeve_circ * 10
    return {
        "size": size,
        "length_cm": round(length, 1), "length_stated": STATED_LENGTH[i],
        "back_width_cm": round(back_w, 1), "back_width_stated": STATED_BACK_W[i],
        "total_rows": rows_sum,
        "sleeve_circumference_cm": round(sleeve_circ, 1),
        "armhole_perimeter_stated_cm": 2 * STATED_ARMHOLE[i],
        "implied_chain_gauge_per_10cm": round(implied_chain_gauge, 1),
        "seam_compatible": abs(sleeve_circ - 2 * STATED_ARMHOLE[i]) / sleeve_circ < 0.06,
    }
