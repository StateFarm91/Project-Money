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
