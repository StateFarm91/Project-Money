"""ENG-GARMENT: a garment release -- one design, every size, certified together.

A garment is sold as one document in a run of sizes, so it is released as one unit: every
sourced size is built, each goes through the full release chain (`gates.certificate.certify`,
the same compile -> twin -> assembly -> reverse -> originality -> physical -> child-safety
chain every product takes), and the run as a whole goes through the garment gates
(`gates.garment_fit`). The release is granted only when every size is granted and the garment
gates find nothing. A size that is refused refuses the release: a buyer who chooses size 4X
must get a size 4X that the system has checked.

Concept routing (`spec_for`) is a table, never a model's guess:

  construction  top_down_yoke -> raglan cardigan; flat_rows -> one-piece body with built-in
                sleeves; bottom_up / modular_panels -> drop-shoulder panels; side_to_side ->
                side-to-side vest. Anything else is a named engine gap.
  garment word  the title must name what the construction builds (`GARMENT_WORDS`): a raglan
                builds a cardigan, the one-piece and drop-shoulder build a sweater/pullover/
                jumper, side-to-side builds a vest. A title naming another garment, or a hood,
                is held, never drafted as something it does not say.
  body table    new_parent -> CYC baby (3-24 months); child -> CYC child/youth 2-12; teen ->
                CYC child/youth 14-16; everyone else -> CYC woman XS-5X.
  fit           the premise's fit word (`creative.garment_design.EASE_WORDS`) or the
                feeling's; each fit has a stated ease set per audience (`EASES`).
  buttons       an adult raglan cardigan has buttons; a baby's or child's garment has none
                (child-safety rule: no buttons and no ties for babies and under-3s).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import garment_families as GF

# ---- the five Brambleloop garments ------------------------------------------------------

EASES: dict[str, dict[str, tuple[tuple[str, float], ...]]] = {
    "adult": {
        "relaxed": (("bust", 18), ("back_length", 12), ("armhole_depth", 4), ("upper_arm", 8)),
        "oversized": (("bust", 28), ("back_length", 12), ("armhole_depth", 6),
                      ("upper_arm", 12)),
    },
    "child": {
        "relaxed": (("bust", 14), ("back_length", 6), ("armhole_depth", 2), ("upper_arm", 5)),
        "oversized": (("bust", 22), ("back_length", 6), ("armhole_depth", 3),
                      ("upper_arm", 7)),
    },
    "baby": {
        "relaxed": (("bust", 10), ("back_length", 4), ("armhole_depth", 2), ("upper_arm", 4)),
        "oversized": (("bust", 14), ("back_length", 4), ("armhole_depth", 2),
                      ("upper_arm", 5)),
    },
}
VEST_EASE = {"adult": (("bust", 16), ("back_length", 8), ("armhole_depth", 5))}

CHILD_SIZES = ("2", "4", "6", "8", "10", "12")
TEEN_SIZES = ("14", "16")

DESIGNS: dict[str, GF.GarmentSpec] = {s.key: s for s in (
    GF.GarmentSpec("fernhollow-raglan-cardigan", "Fernhollow Raglan Cardigan", "cardigan",
                   "adult", "raglan", "worsted", "wool", "relaxed", EASES["adult"]["relaxed"],
                   buttons=True),
    GF.GarmentSpec("brookside-kids-sweater", "Brookside Kids Sweater", "sweater", "child",
                   "one_piece", "dk", "cotton", "relaxed", EASES["child"]["relaxed"],
                   sizes=CHILD_SIZES),
    GF.GarmentSpec("little-wren-baby-cardigan", "Little Wren Baby Cardigan", "cardigan",
                   "baby", "raglan", "dk", "cotton", "relaxed", EASES["baby"]["relaxed"],
                   buttons=False),
    GF.GarmentSpec("driftline-side-to-side-vest", "Driftline Side-to-Side Vest", "vest",
                   "adult", "side_to_side", "worsted", "wool", "relaxed", VEST_EASE["adult"]),
    GF.GarmentSpec("kestrel-drop-shoulder-pullover", "Kestrel Drop-Shoulder Pullover",
                   "pullover", "adult", "drop_shoulder", "worsted", "wool", "relaxed",
                   (("bust", 16), ("back_length", 12), ("armhole_depth", 4),
                    ("upper_arm", 8))),
)}


# ---- concept -> spec ---------------------------------------------------------------------

CONSTRUCTION_FOR: dict[str, str] = {
    "top_down_yoke": "raglan", "flat_rows": "one_piece", "bottom_up": "drop_shoulder",
    "modular_panels": "drop_shoulder", "side_to_side": "side_to_side",
}
# What each construction honestly builds, as title words.
GARMENT_WORDS: dict[str, tuple[str, ...]] = {
    "raglan": ("cardigan", "cardi"),
    "one_piece": ("sweater", "jumper", "pullover"),
    "drop_shoulder": ("sweater", "jumper", "pullover"),
    "side_to_side": ("vest", "tank", "slipover"),
}
_ANY_GARMENT = re.compile(r"\b(cardigans?|cardi|sweaters?|jumpers?|pullovers?|vests?|tanks?|"
                          r"slipovers?|hoodies?|hooded|hoods?|tops?|tees?|t-shirts?|ponchos?|"
                          r"shrugs?|dress(?:es)?|rompers?|onesies?|jackets?|coats?)\b")
_HOOD = re.compile(r"\bhood(?:ie|ies|ed|s)?\b")
FIT_FOR_FEELING_OVERSIZED = frozenset({"cosy", "bold", "rugged"})


class GarmentRefused(ValueError):
    """A garment concept no verified garment engine builds, with the named reason."""

    def __init__(self, family: str, why: str):
        super().__init__(f"construction_unsupported:{family} -- {why}")
        self.family, self.why = family, why


def audience_for(recipient: str) -> str:
    return {"new_parent": "baby", "child": "child", "teen": "child"}.get(recipient, "adult")


def spec_for(concept) -> GF.GarmentSpec:
    """The garment spec a concept describes, or GarmentRefused naming what is missing."""
    from ..creative.garment_design import EASE_WORDS, FITTED_WORDS, _words

    if concept.form != "fitted_garment":
        raise GarmentRefused("garment", f"{concept.form!r} is not a garment form")
    cons = CONSTRUCTION_FOR.get(concept.construction)
    if cons is None:
        raise GarmentRefused(f"garment_{concept.construction}",
                             f"no garment engine works the {concept.construction!r} "
                             f"construction")
    title = (concept.title or "").lower()
    if _HOOD.search(title) or _HOOD.search((concept.premise or "").lower()):
        raise GarmentRefused("garment_hood", "a hood is a shaped piece no garment engine "
                                             "builds yet; the concept would sell a hood the "
                                             "pattern does not make")
    named = {m.group(1) for m in _ANY_GARMENT.finditer(title)}
    honest = {w for w in named if any(w.startswith(h) for h in GARMENT_WORDS[cons])}
    if not named or named != honest:
        raise GarmentRefused(f"garment_{cons}",
                             f"the title names {sorted(named) or 'no garment'}; the {cons} "
                             f"engine builds a {'/'.join(GARMENT_WORDS[cons])}")
    audience = audience_for(concept.recipient)
    if cons == "side_to_side" and audience != "adult":
        raise GarmentRefused("garment_side_to_side",
                             "the side-to-side vest is graded on the adult table only")
    premise = f"{concept.premise} {concept.notes}".lower()
    if any(w in premise for w in FITTED_WORDS):
        raise GarmentRefused(f"garment_{cons}", "a fitted garment is risk class C and needs a "
                                                "physical fit test before it can ship")
    fit = _words(premise, EASE_WORDS) or (
        "oversized" if concept.feeling in FIT_FOR_FEELING_OVERSIZED else "relaxed")
    if fit not in ("relaxed", "oversized"):
        fit = "relaxed"
    if cons == "side_to_side":
        ease, fit = VEST_EASE["adult"], "relaxed"
    else:
        ease = EASES[audience][fit]
    sizes = (CHILD_SIZES if concept.recipient == "child" else
             TEEN_SIZES if concept.recipient == "teen" else None)
    weight, fibre = ("dk", "cotton") if audience != "adult" else ("worsted", "wool")
    category = next(iter(named))
    return GF.GarmentSpec(concept.key, concept.title, category, audience, cons, weight, fibre,
                          fit, ease, buttons=(cons == "raglan" and audience == "adult"),
                          sizes=sizes)


# ---- the release -------------------------------------------------------------------------


@dataclass
class GarmentRelease:
    spec: GF.GarmentSpec
    design: object
    cirs: dict = field(default_factory=dict)
    certificates: dict = field(default_factory=dict)
    verdict: object = None
    claims: list = field(default_factory=list)

    @property
    def sizes(self) -> tuple[str, ...]:
        return tuple(self.cirs)

    @property
    def granted(self) -> bool:
        return (bool(self.certificates) and all(c.granted for c in self.certificates.values())
                and self.verdict is not None and self.verdict.ok)

    def reasons(self) -> list[str]:
        out = []
        for size, c in self.certificates.items():
            out += [f"size {size}: {f.code}: {f.message}" for f in c.findings
                    if f.severity == "ERROR"]
        if self.verdict is not None:
            out += [str(f) for f in self.verdict.findings]
        return out


def build(spec: GF.GarmentSpec) -> GarmentRelease:
    design = GF.design(spec)
    cirs = {s: design.build(s) for s in design.sourced_sizes()}
    return GarmentRelease(spec=spec, design=design, cirs=cirs)


def certify(release: GarmentRelease, *, physical_evidence: list[dict] | None = None,
            claims: list[dict] | None = None) -> GarmentRelease:
    """Every size through the release chain, then the garment gates over the run."""
    from ..gates import certificate, garment_fit

    for size, cir in release.cirs.items():
        release.certificates[size] = certificate.certify(
            cir, physical_evidence=physical_evidence)
    release.claims = claims if claims is not None else garment_fit.size_claims(
        release.design, release.cirs)
    release.verdict = garment_fit.evaluate(release.design, release.cirs, claims=release.claims)
    return release


def from_concept(concept) -> GarmentRelease:
    return certify(build(spec_for(concept)))
