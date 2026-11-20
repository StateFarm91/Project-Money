"""ENG-LOWSEW-CHENILLE: chenille / jumbo yarn (CYC 6-7) as a first-class yarn class.

A chunky chenille toy is the format the owner's priority shop wins with, and the commonest
complaint about that format is "the stitches were too tight with the stated hook": a pattern
that names one hook and no gauge leaves a chenille maker guessing, because chenille has
almost no give and its pile hides the stitch. A yarn class states what the pattern needs to
say instead of a single hook:

  - gauge per hook (single crochet, worked in the round at toy tension);
  - the hook range the class is worked on, printed in the PDF;
  - tension guidance and a shedding / care note, in Brambleloop's own words;
  - a yardage model for the twin: a factor on the stitch-width yarn model and a wider,
    stated tolerance, because no sample of these yarns has been measured here;
  - a metres-per-100 g band, so the twin's metres become balls and grams.

Every gauge here is a DESIGN gauge chosen inside the Craft Yarn Council band for the weight
(`publish.substitution.WEIGHTS`): it is a stated assumption, not a measurement, and
`gauge_findings` / the PDF say so. A physical swatch replaces it when one exists.

`classify(cir)` reads the class from the materials: a yarn material whose name says chenille
and whose weight is super_bulky or jumbo. `findings(cir)` refuses a chenille design whose
gauge is not this table's gauge for its hook, or whose hook is outside the class's range.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Gauge

ROW_RATIO = 1.1          # sc rows per sc stitch in toy tension (as `creative.prototype`)


@dataclass(frozen=True)
class HookGauge:
    hook_mm: float
    sc_per_10cm: float
    use: str


@dataclass(frozen=True)
class YarnClass:
    key: str
    name: str
    cyc: int
    weight_key: str
    hooks: tuple[HookGauge, ...]
    tension: str
    shedding_care: str
    yardage_factor: float          # multiplies the twin's stitch-width yarn model
    yardage_tolerance: float       # replaces the default +/- band (uncalibrated)
    metres_per_100g: tuple[float, float]
    basis: str

    @property
    def hook_range_mm(self) -> tuple[float, float]:
        return (min(h.hook_mm for h in self.hooks), max(h.hook_mm for h in self.hooks))

    def at(self, hook_mm: float) -> HookGauge | None:
        return next((h for h in self.hooks if abs(h.hook_mm - hook_mm) < 1e-9), None)

    def gauge(self, hook_mm: float | None = None) -> Gauge:
        """The design gauge at `hook_mm` (default: the toy-tension hook, the smallest)."""
        hg = self.at(hook_mm) if hook_mm is not None else self.hooks[0]
        if hg is None:
            raise ValueError(f"{hook_mm} mm is not a hook the {self.name} class is worked on "
                             f"({self.hook_range_words})")
        return Gauge(stitches_per_10cm=hg.sc_per_10cm,
                     rows_per_10cm=round(hg.sc_per_10cm * ROW_RATIO, 1),
                     stitch_type="sc", hook_mm=hg.hook_mm, yarn_weight=self.weight_key)

    @property
    def hook_range_words(self) -> str:
        lo, hi = self.hook_range_mm
        return f"{lo:g}-{hi:g} mm"

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "cyc": self.cyc,
                "weight": self.weight_key, "hook_range_mm": list(self.hook_range_mm),
                "gauge_by_hook": [{"hook_mm": h.hook_mm, "sc_per_10cm": h.sc_per_10cm,
                                   "use": h.use} for h in self.hooks],
                "yardage_factor": self.yardage_factor,
                "yardage_tolerance": self.yardage_tolerance,
                "metres_per_100g": list(self.metres_per_100g), "basis": self.basis}


_TENSION = ("Chenille barely stretches and its soft pile hides each stitch, so it is easy to "
            "work too loosely and hard to see why. For a toy, use the smallest hook in the "
            "range and keep the fabric firm enough that stuffing never shows between "
            "stitches. If your swatch has more stitches than the gauge, move up one hook "
            "size; if stuffing shows or it has fewer, move down. Find the top of each stitch "
            "by feel rather than by sight, and keep a marker in the first stitch of every "
            "round.")
_CARE = ("Chenille can shed loose fibres as you work and can 'worm': a loop of the pile "
         "works out of the fabric when a stitch is pulled hard. Snip a worm flush with "
         "the fabric; never pull it. Weave each end through at least 8 cm, because the "
         "smooth core grips less than wool. Spot clean or hand wash cold, do not tumble "
         "dry, and reshape while damp. Your ball band decides the rest.")

CHENILLE_6 = YarnClass(
    key="chenille_6", name="super bulky chenille", cyc=6, weight_key="super_bulky",
    hooks=(HookGauge(6.0, 9.0, "toy tension: firm, stuffing does not show"),
           HookGauge(6.5, 8.5, "toy tension, a looser hand"),
           HookGauge(7.0, 8.0, "soft toy fabric"),
           HookGauge(8.0, 7.0, "blankets and cushions, not toys")),
    tension=_TENSION, shedding_care=_CARE,
    yardage_factor=1.0, yardage_tolerance=0.30, metres_per_100g=(60.0, 100.0),
    basis=("design gauges inside the CYC 6 band (5-9 sc / 10 cm); uncalibrated: no swatch of "
           "a chenille yarn has been measured here, so yardage carries +/- 30 %"))
CHENILLE_7 = YarnClass(
    key="chenille_7", name="jumbo chenille", cyc=7, weight_key="jumbo",
    hooks=(HookGauge(8.0, 6.0, "toy tension: firm, stuffing does not show"),
           HookGauge(9.0, 5.5, "toy tension, a looser hand"),
           HookGauge(10.0, 5.0, "soft toy fabric"),
           HookGauge(12.0, 4.0, "blankets and cushions, not toys")),
    tension=_TENSION, shedding_care=_CARE,
    yardage_factor=1.0, yardage_tolerance=0.30, metres_per_100g=(20.0, 60.0),
    basis=("design gauges inside the CYC 7 band (1-6 sc / 10 cm); uncalibrated: no swatch of "
           "a chenille yarn has been measured here, so yardage carries +/- 30 %"))

CLASSES: dict[str, YarnClass] = {c.key: c for c in (CHENILLE_6, CHENILLE_7)}
_BY_WEIGHT = {c.weight_key: c for c in CLASSES.values()}


def for_weight(weight_key: str) -> YarnClass:
    try:
        return _BY_WEIGHT[weight_key]
    except KeyError:
        raise ValueError(f"no chenille class for {weight_key!r}: chenille is classed at CYC 6 "
                         f"(super_bulky) and CYC 7 (jumbo)") from None


def classify(cir) -> YarnClass | None:
    """The chenille class of the design's yarn, or None when it is not chenille."""
    for m in getattr(cir, "materials", None) or []:
        name = (getattr(m, "name", "") or "").lower()
        if "chenille" in name and getattr(m, "yarn_weight", None) in _BY_WEIGHT:
            return _BY_WEIGHT[m.yarn_weight]
    return None


def findings(cir) -> list:
    """A chenille design's gauge must be this class's gauge for its hook."""
    from .compiler import ERROR, Finding

    cls = classify(cir)
    out: list = []
    names = [(getattr(m, "name", "") or "").lower() for m in cir.materials]
    if cls is None:
        if any("chenille" in n for n in names):
            out.append(Finding(ERROR, "CHENILLE_WEIGHT_UNCLASSED",
                               "a chenille yarn is named at a weight with no chenille class "
                               "(CYC 6 super_bulky or CYC 7 jumbo)"))
        return out
    g = cir.gauge
    if g is None or g.hook_mm is None:
        out.append(Finding(ERROR, "CHENILLE_GAUGE_UNSTATED",
                           f"a {cls.name} design must state its hook and gauge"))
        return out
    hg = cls.at(g.hook_mm)
    if hg is None:
        out.append(Finding(ERROR, "CHENILLE_HOOK_OUT_OF_RANGE",
                           f"{g.hook_mm:g} mm is not a hook of the {cls.name} class "
                           f"({cls.hook_range_words})"))
    elif abs(hg.sc_per_10cm - g.stitches_per_10cm) > 1e-9 or g.yarn_weight != cls.weight_key:
        out.append(Finding(ERROR, "CHENILLE_GAUGE_MISMATCH",
                           f"the gauge {g.stitches_per_10cm:g} sc / 10 cm at {g.hook_mm:g} mm "
                           f"is not the {cls.name} gauge {hg.sc_per_10cm:g} at that hook"))
    return out


def grams(metres: float, cls: YarnClass) -> tuple[int, int]:
    """Grams for `metres` of this class: (lightest, heaviest) across its metres-per-100 g band."""
    lo, hi = cls.metres_per_100g
    return int(metres / hi * 100.0 + 0.999), int(metres / lo * 100.0 + 0.999)
