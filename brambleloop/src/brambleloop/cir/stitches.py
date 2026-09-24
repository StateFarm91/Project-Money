"""Canonical crochet stitch taxonomy.

The CIR is terminology-neutral: canonical codes are US terms. UK rendering happens in the
writer (Master Plan section 31: localization is downstream of CIR, never a fork of it).

Every stitch declares how it interacts with the fabric, which is what makes the compiler
deterministic rather than an LLM opinion (Master Plan section 3):

  consumes -- how many stitches of the row being worked into this operation uses up
  produces -- how many stitches this operation contributes to the new row's count
  height   -- turning-chain units (sc=1, hdc=2, dc=3, tr=4): the convention that decides
              how many chains you turn with. NOT a physical measurement.
  row_height -- how tall a row of this stitch actually is, in sc units. A dc turns with three
              chains but is about twice the height of a sc, not three times. Conflating the
              two overstates a blanket's finished length by half, which is a size claim on a
              listing and therefore a refund.

A stitch that consumes 2 and produces 1 is a decrease; consumes 1 produces 2 is an increase.
That single pair of numbers is what catches the overwhelming majority of real pattern bugs.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stitch:
    code: str
    name_us: str
    name_uk: str
    consumes: int
    produces: int
    height: float
    row_height: float = 0.0
    counts_in_total: bool = True

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.code


# Canonical registry. `height` is in "sc units" and drives row-height geometry.
# The abbreviation each code is PRINTED as, per terminology. This lives here, in the lowest
# layer, because it is a fact about the stitch rather than about any document, and because it
# was previously two tables that disagreed. `cir/writer._term` carried its own copy covering
# only the basic stitches and their shaping variants; `publish/abbreviations.TOKENS` carried
# the complete one. The writer's copy silently returned the US code for anything it did not
# know, so a UK document printed `fpdc` -- which a UK maker correctly reads as front post
# DOUBLE crochet, the stitch a US pattern calls single crochet, HALF the height of the one
# the pattern compiled. On the cable throw that is a garment coming out at roughly half its
# stated length, from a document that was internally consistent and wrong.
#
# One table, in the layer both consumers can import. `publish.abbreviations.TOKENS` now
# derives from this rather than restating it.
UK_TERMS: dict[str, str] = {
    "ch": "ch", "slst": "ss", "sc": "dc", "hdc": "htr", "dc": "tr", "tr": "dtr",
    "inc": "dc inc", "dec": "dc dec", "dc_inc": "tr inc", "dc_dec": "tr dec",
    "sk": "miss", "fpdc": "fptr", "bpdc": "bptr",
    # Same token in both terminologies. Named explicitly rather than left to a default,
    # because "absent from the table" and "identical in both" are different facts and only
    # one of them is safe to print.
    "bob": "bob", "cable2x2": "cable2x2", "cable1x1": "cable1x1",
}


def term(code: str, terminology: str = "US") -> str:
    """The abbreviation this code is printed as. Unknown codes are refused, not passed through.

    Passing an unknown code through unchanged is what produced a UK document instructing the
    wrong stitch, so a code with no stated rendering raises instead of guessing.
    """
    if terminology.upper() != "UK":
        return code
    try:
        return UK_TERMS[code]
    except KeyError:
        raise KeyError(
            f"{code!r} has no stated UK rendering; add it to cir.stitches.UK_TERMS rather "
            f"than letting a UK document print a US abbreviation") from None


_STITCHES: dict[str, Stitch] = {}


def _register(s: Stitch) -> Stitch:
    _STITCHES[s.code] = s
    return s


CH = _register(Stitch("ch", "chain", "chain", consumes=0, produces=1, height=0.25, row_height=0.25))
SLST = _register(Stitch("slst", "slip stitch", "slip stitch", consumes=1, produces=1, height=0.25, row_height=0.3))
SC = _register(Stitch("sc", "single crochet", "double crochet", consumes=1, produces=1, height=1.0, row_height=1.0))
HDC = _register(Stitch("hdc", "half double crochet", "half treble crochet", consumes=1, produces=1, height=2.0, row_height=1.5))
DC = _register(Stitch("dc", "double crochet", "treble crochet", consumes=1, produces=1, height=3.0, row_height=2.0))
TR = _register(Stitch("tr", "treble crochet", "double treble crochet", consumes=1, produces=1, height=4.0, row_height=2.8))

# Shaping. `inc`/`dec` are sc-based by convention; taller variants are explicit.
INC = _register(Stitch("inc", "single crochet increase", "double crochet increase", consumes=1, produces=2, height=1.0, row_height=1.0))
DEC = _register(Stitch("dec", "single crochet decrease", "double crochet decrease", consumes=2, produces=1, height=1.0, row_height=1.0))
DC_INC = _register(Stitch("dc_inc", "double crochet increase", "treble crochet increase", consumes=1, produces=2, height=3.0, row_height=2.0))
DC_DEC = _register(Stitch("dc_dec", "double crochet decrease", "treble crochet decrease", consumes=2, produces=1, height=3.0, row_height=2.0))

# Skipping a stitch consumes fabric but contributes nothing to the new count; it is how
# ch-spaces, mesh and shell stitches open the fabric up.
SK = _register(Stitch("sk", "skip", "miss", consumes=1, produces=0, height=0.0, row_height=0.0))

# ---- texture ---------------------------------------------------------------
#
# Added because three products in the catalogue were named for techniques their patterns
# could not contain: a "Heirloom Cable Throw", a "Bobble Floor Pillow" and a "Chunky Ribbed
# Scarf", all worked in plain sc and dc colourwork. That is the same defect as the flat panel
# called a basket, in a different dimension -- a name claiming something the fabric does not
# do -- and the fix is the same: make the claim true, or stop making it.
#
# Post stitches are worked around the post of the stitch below rather than into its top. The
# count arithmetic is identical to a dc, which is why they cost the compiler nothing; what
# they buy is ribbing and cables, which cannot be faked with colour.
FPDC = _register(Stitch("fpdc", "front post double crochet", "front post treble crochet",
                        consumes=1, produces=1, height=3.0, row_height=1.9))
BPDC = _register(Stitch("bpdc", "back post double crochet", "back post treble crochet",
                        consumes=1, produces=1, height=3.0, row_height=1.9))

# A bobble is several incomplete double crochets worked into one stitch and closed together.
# It consumes one stitch and produces one, so the arithmetic is unremarkable; what is *not*
# unremarkable is the yarn, which is why `twin._YARN_FACTOR` carries an entry for it rather
# than falling back to a default that would understate a bobble blanket by a third.
BOBBLE = _register(Stitch("bob", "bobble", "bobble", consumes=1, produces=1,
                          height=3.0, row_height=2.0))

# A cable crossing works stitches out of order: two are skipped, two are worked, and the
# skipped two are then worked in front of or behind them. That re-ordering is deliberately
# *not* modelled as a sequence of ops, because the CIR consumes stitches strictly in order
# and a model that pretended otherwise would be lying about the one thing it guarantees.
# Instead a crossing is one composite stitch: it consumes four and produces four, the
# arithmetic the compiler checks stays exact, and which two cross in front is a property of
# the stitch rather than prose nobody validated.
CABLE_2X2 = _register(Stitch("cable2x2", "2-over-2 cable crossing", "2-over-2 cable crossing",
                             consumes=4, produces=4, height=3.0, row_height=2.0))
CABLE_1X1 = _register(Stitch("cable1x1", "1-over-1 cable crossing", "1-over-1 cable crossing",
                             consumes=2, produces=2, height=3.0, row_height=2.0))


def get(code: str) -> Stitch:
    try:
        return _STITCHES[code]
    except KeyError:
        raise UnknownStitch(code) from None


def known_codes() -> list[str]:
    return sorted(_STITCHES)


class UnknownStitch(KeyError):
    """Raised when CIR references a stitch outside the canonical registry.

    Deliberately fatal: an unrecognised stitch means the compiler cannot reason about the
    fabric, and a pattern the compiler cannot reason about must never reach a customer.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return f"unknown stitch {self.code!r}; known: {', '.join(known_codes())}"
