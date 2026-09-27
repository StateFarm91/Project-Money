"""What self-improvement may never do, enforced before a hypothesis is written down.

Requirement 102 draws the line: the system may improve code, prompts, scoring, workflows and
agent configuration within tested, reversible, spend-authorised bounds — and may never weaken
policy gates, fabricate evidence, bypass owner authority or disable safety checks.

That sentence describes the central hazard of a system that optimises its own metrics. Every
number this company reports is produced by a check, so the cheapest way to improve any of them
is to loosen the check that produces it. A release-certification rate rises beautifully when
the certifier stops refusing things. The improvement is real, the measurement is real, the
company is worse, and nothing in the loop would notice — because from inside, weakening a gate
and fixing a defect look identical: a change, followed by a better number.

So the boundary is a refusal at the point a hypothesis is *proposed*, before any work is done
on it. Not a review afterwards, because by then somebody has built the thing and the argument
becomes about the work rather than about the rule.

The protected surfaces are named rather than inferred. A blocklist of file paths would be
evaded by a refactor; these are the *capabilities* that may not be traded away, whatever file
they end up living in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

# The gates whose strictness is not an optimisation variable. Each exists because something
# went wrong once, or would have.
PROTECTED_GATES: tuple[str, ...] = (
    "deterministic_validation",     # the compiler decides what a pattern says
    "reverse_compilation",          # the document and the design must agree
    "asset_truth",                  # an image must be what it claims
    "policy_gate",                  # platform policy and legal compliance
    "claim_gates",                  # no size or technique claim the twin cannot support
    "shadow_mode",                  # publication refusal while unpromoted
    "spend_ceilings",               # budget enforced in code
    "owner_authority",              # RED actions belong to the owner
    "evidence_grading",             # a substitute may never close a mandate
    "confidence_ladder",            # the CA$5K model counts rows
    "creative_jury",                # one rejection ends a concept
    "benchmark_quarantine",         # competitor files stay unreachable
    "product_truth",                # the fabric works the certified chart, never a guess
)

_FABRICATION = (
    "synthetic review", "fake review", "seed customers", "simulate orders",
    "backfill revenue", "sample data as evidence", "placeholder metric",
    "assume conversion", "estimate the sample", "fill in the missing",
)


class GovernanceRefused(PermissionError):
    """A hypothesis that improves a number by damaging the thing it measures."""


@dataclass(frozen=True)
class Boundary:
    ok: bool
    reason: str = ""
    rule: str = ""

    def raise_if_refused(self) -> None:
        if not self.ok:
            raise GovernanceRefused(f"{self.reason} [{self.rule}]")


def _mentions(text: str, needles: tuple[str, ...]) -> str | None:
    low = (text or "").lower()
    for needle in needles:
        if needle in low:
            return needle
    return None


# ---- identities and surfaces, normalised once --------------------------------------------
#
# Found by certification (C-19, C-22): `approve(approved_by="Listing")` passed on listing's
# own proposal, `touches=("Product_Truth",)` graded as an unknown code surface, and the
# Director saw 'Weights ' and 'weights' as two surfaces. Every comparison of a name now goes
# through one of these two functions, so a spelling can never be the difference between the
# same thing and another thing.


def normalise_actor(name: str | None) -> str:
    """An agent or person's identity as compared: case-folded, whitespace collapsed."""
    return " ".join((name or "").split()).casefold()


def normalise_surface(name: str | None) -> str:
    """A declared surface as compared: case-folded, spaces and hyphens become underscores."""
    return re.sub(r"[\s\-]+", "_", (name or "").strip().casefold()).strip("_")


def normalise_touches(touches) -> tuple[str, ...]:
    out: list[str] = []
    for t in touches or ():
        key = normalise_surface(t)
        if key and key not in out:
            out.append(key)
    return tuple(out)


# ---- which department operates which protected gate ----------------------------------------
#
# A cell may propose a change to a protected gate only if it operates that gate, and even then
# the change is graded `gate` and needs the owner (`improve.tiers`). A gate no cell operates
# is changed by the owner directly, never by the loop. This is what separates Creative Assets
# proposing a Product Truth change for the owner to judge from Pattern Engineering reaching
# into a gate it does not run (#102, C-20).
GATE_OPERATORS: dict[str, tuple[str, ...]] = {
    "deterministic_validation": ("pattern_engineering", "quality"),
    "reverse_compilation": ("pattern_engineering", "quality"),
    "asset_truth": ("creative_assets",),
    "product_truth": ("creative_assets",),
    "policy_gate": ("quality",),
    "claim_gates": ("quality",),
    "shadow_mode": (),
    "spend_ceilings": ("finance",),
    "owner_authority": (),
    "evidence_grading": ("quality",),
    "confidence_ladder": ("finance",),
    "creative_jury": ("product_creativity",),
    "benchmark_quarantine": ("market_radar",),
}


# ---- protected constants, discovered rather than listed ------------------------------------
#
# C-20(b): "set REGRESSION_TOLERANCE from 0.05 to 0.25" names no gate and no weakening verb,
# and is a change to the self-improvement boundary itself. Every UPPERCASE constant defined in
# a protected package is found by reading the source (ast, so nothing is imported or run), and
# naming one is touching the protected surface that module implements.
_PROTECTED_PACKAGES: tuple[str, ...] = ("gates", "cir", "publish", "quality", "visual",
                                        "improve")

_MODULE_SURFACE: dict[str, str] = {
    "gates.asset_truth": "asset_truth",
    "gates.confidence": "confidence_ladder",
    "gates.certificate": "deterministic_validation",
    "gates.regression": "deterministic_validation",
    "cir.reverse": "reverse_compilation",
    "visual.inspect": "asset_truth",
    "publish.listing_asset": "claim_gates",
    "publish.listing_assets": "claim_gates",
    "publish.eligibility": "shadow_mode",
}
_PACKAGE_SURFACE: dict[str, str] = {
    "gates": "policy_gate",
    "cir": "deterministic_validation",
    "publish": "claim_gates",
    "quality": "deterministic_validation",
    "visual": "product_truth",
    "improve": "owner_authority",
}


@lru_cache(maxsize=1)
def protected_constants() -> dict[str, str]:
    """UPPERCASE module constants of the protected packages -> the surface they belong to.

    A name counts when it carries an underscore (REGRESSION_TOLERANCE) or holds a number
    (a bare threshold): single words like `CIR` or `DC` are ordinary vocabulary in a
    hypothesis, not a reference to a constant.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    found: dict[str, str] = {}
    for pkg in _PROTECTED_PACKAGES:
        for path in sorted((root / pkg).glob("*.py")):
            module = f"{pkg}.{path.stem}"
            surface = _MODULE_SURFACE.get(module, _PACKAGE_SURFACE[pkg])
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.AnnAssign):
                    targets, value = [node.target], node.value
                else:
                    continue
                numeric = (isinstance(value, ast.Constant)
                           and isinstance(value.value, (int, float))
                           and not isinstance(value.value, bool))
                for target in targets:
                    if not isinstance(target, ast.Name) or not target.id.isupper():
                        continue
                    if "_" in target.id.strip("_") or numeric:
                        found.setdefault(target.id, surface)
    return found


def _named_constants(text: str) -> dict[str, str]:
    table = protected_constants()
    return {tok: table[tok] for tok in re.findall(r"\b[A-Z][A-Z0-9_]*[A-Z0-9]\b", text or "")
            if tok in table}


# ---- Product Truth described in plain words -------------------------------------------------
#
# C-20(d): "read stitches from the beauty photo instead of the certified chart" never says
# `product_truth`. The rule it breaks is that the certified chart (the CIR, the compiled
# instructions) is the only source of what the fabric is; an image, a photo or a generator
# standing in for it is the violation, however it is worded.
_TRUTH_SOURCES = re.compile(
    r"\b(certified (chart|pattern|instructions?)|chart|cir|compiled (pattern|instructions?)"
    r"|instructions?|pattern text|written pattern|stitch counts?)\b")
_TRUTH_SUBSTITUTES = re.compile(
    r"\b(image|images|imagery|photo|photos|photograph\w*|picture\w*|beauty shot\w*|"
    r"render(ed)? (image|photo)\w*|vision model|ai model|language model|llm|diffusion|"
    r"generat\w+|guess\w*|infer\w*|estimat\w+)\b")
_REPLACEMENT = re.compile(
    r"\b(instead of|rather than|in place of|replac\w+|swap\w*|substitut\w+|derived from|"
    r"\w+ derived|read\w* (\w+ ){0,3}from|infer\w* (\w+ ){0,3}from|generat\w+ (\w+ ){0,3}"
    r"from|take\w* (\w+ ){0,3}from|no longer (use|need|require)\w*)\b")


def _describes_product_truth(text: str) -> bool:
    for sentence in _SENTENCE_SPLIT.split((text or "").lower()):
        if (_TRUTH_SOURCES.search(sentence) and _TRUTH_SUBSTITUTES.search(sentence)
                and _REPLACEMENT.search(sentence)):
            return True
    return False


def implied_surfaces(hypothesis: str) -> dict[str, str]:
    """Protected surfaces a hypothesis touches by what it says, whatever it declared.

    Returns surface -> how it was found. Three sources: a protected gate named in prose, an
    UPPERCASE constant of a protected module, and Product Truth described in plain words.
    """
    out: dict[str, str] = {}
    named = _names_protected_gate(hypothesis)
    for name in named:
        out.setdefault(name, f"names {name.replace('_', ' ')!r}")
    for const, surface in _named_constants(hypothesis).items():
        out.setdefault(surface, f"names the protected constant {const}")
    if _describes_product_truth(hypothesis):
        out.setdefault("product_truth",
                       "describes the certified chart being replaced by an image, photo, "
                       "model or generator")
    return out


# ---- the lexical net: weakening verbs governing gate objects --------------------------------
#
# Verbs that weaken, and the objects they weaken, checked as a *pair within a clause*. Found
# by writing "lower the thumbnail threshold": a literal-phrase list caught "lower the threshold
# on the thumbnail check" and missed the same sentence reordered. Certification (C-20) then
# found the next layer: inflections ("lowering"), synonyms ("decrease", "loosen"), and an
# object more than four words after its verb. So verbs are matched on their inflected forms,
# and the object may sit anywhere after the verb up to the end of its clause -- but not
# before it, and not past a clause break, because "tightening the thumbnail check should
# reduce defects" has the verb acting on the defects.
_WEAKEN_BASES: tuple[str, ...] = (
    "lower", "reduce", "decrease", "relax", "loosen", "soften", "weaken", "drop", "ease",
    "widen", "broaden", "shrink", "skip", "bypass", "disable", "remove", "waive", "suppress",
    "cut", "trim", "lessen", "slacken", "downgrade", "dilute", "exempt", "omit", "circumvent",
    "override", "deactivate", "retire", "halve",
)
# Verbs that weaken only when their object is an allowance: raising a threshold is often a
# tightening, raising a tolerance never is.
_WIDEN_BASES: tuple[str, ...] = ("raise", "increase", "extend", "expand", "grow", "double",
                                 "enlarge", "allow", "permit", "accept")
_ALLOWANCE_OBJECTS: tuple[str, ...] = (
    "tolerance", "tolerances", "deviation", "deviations", "allowance", "allowances", "margin",
    "margins", "leeway", "slack", "variance", "error", "errors", "mismatch", "mismatches",
)


def _forms(base: str) -> set[str]:
    stem = base[:-1] if base.endswith("e") else base
    forms = {base, base + "s", base + "es", base + "d", base + "ed", stem + "ing",
             stem + "ed", base + "ing"}
    if len(base) > 2 and base[-1] not in "aeiouwy" and base[-2] in "aeiou" \
            and base[-3] not in "aeiou":
        forms |= {base + base[-1] + "ing", base + base[-1] + "ed"}
    if base.endswith("y"):
        forms |= {base[:-1] + "ies", base[:-1] + "ied"}
    return forms


_WEAKEN_VERBS: frozenset[str] = frozenset(f for b in _WEAKEN_BASES for f in _forms(b))
_WIDEN_VERBS: frozenset[str] = frozenset(f for b in _WIDEN_BASES for f in _forms(b))

_GATE_OBJECTS: tuple[str, ...] = (
    "threshold", "thresholds", "check", "checks", "gate", "gates", "validation", "validator",
    "tolerance", "tolerances", "strictness", "standard", "standards", "bar", "requirement",
    "requirements", "refusal", "refusals", "guard", "guards", "minimum", "minimums", "floor",
    "cutoff", "cutoffs", "lock", "locks", "inspection", "certification", "verification",
    "safeguard", "safeguards", "rule", "rules", "criteria", "criterion",
)

# Objects that are gates by their nature, whatever surface a hypothesis declares. "Lower the
# threshold" on an unprotected scoring surface is ordinary tuning; "lower the gate threshold"
# is not, and declaring `touches=("weights",)` beside it does not make it tuning.
_INTRINSIC_GATE_OBJECTS: tuple[str, ...] = (
    "gate", "gates", "guard", "guards", "refusal", "refusals", "validation", "validator",
    "check", "checks", "lock", "locks", "inspection", "certification", "verification",
    "safeguard", "safeguards",
)

# Words that end the clause a verb governs.
_CLAUSE_BREAKS: frozenset[str] = frozenset((
    "should", "would", "will", "could", "might", "may", "must", "so", "because", "since",
    "which", "while", "but", "then", "thereby", "whereas", "to", "until", "unless",
))

# The stated effect of a loosening: more things pass the check, fewer are refused. A change
# whose purpose is fewer refusals is a gate change, whatever surface it names.
_REFUSAL_EFFECT = re.compile(
    r"\b(more|most) (\w+ ){0,3}(pass\w*|certif\w*|clear\w*|surviv\w*|get through|"
    r"go through|through|approv\w*)"
    r"|\bfewer (\w+ ){0,4}(are |get |being )?(refus\w*|block\w*|reject\w*|fail\w*|flag\w*|"
    r"revert\w*|caught)"
    r"|\bstop\w* (refus\w*|block\w*|reject\w*|fail\w*)")

_SENTENCE_SPLIT = re.compile(r"[.;!?\n]+")

# Phrases that describe loosening rather than improving, kept from the first version so the
# documented refusals keep their wording.
_LOOSENING = (
    "lower the threshold", "raise the threshold to pass", "relax", "loosen", "soften",
    "disable", "skip the", "bypass", "turn off", "remove the check", "remove the gate",
    "stop refusing", "allow through", "widen the tolerance", "reduce strictness",
    "make the gate optional", "waive", "suppress the warning", "ignore the finding",
)


def _clauses(text: str):
    for sentence in _SENTENCE_SPLIT.split((text or "").lower()):
        for part in re.split(r"[,:()]", sentence):
            yield re.findall(r"[a-z]+", part)


def _weakening(text: str) -> tuple[str, list[str]] | None:
    """A weakening verb governing a gate object, and the clause tokens it governs."""
    for tokens in _clauses(text):
        for index, token in enumerate(tokens):
            if token not in _WEAKEN_VERBS and token not in _WIDEN_VERBS:
                continue
            clause = []
            for word in tokens[index + 1:]:
                if word in _CLAUSE_BREAKS:
                    break
                clause.append(word)
            objects = (_GATE_OBJECTS if token in _WEAKEN_VERBS else _ALLOWANCE_OBJECTS)
            obj = next((w for w in clause if w in objects), None)
            if obj:
                return f"{token} the {obj}", clause
    return None


def _weakens(text: str) -> str | None:
    hit = _weakening(text)
    return hit[0] if hit else None


def _intrinsic_object(text: str) -> str | None:
    hit = _weakening(text)
    if not hit:
        return None
    return next((w for w in hit[1] if w in _INTRINSIC_GATE_OBJECTS), None)


def check(hypothesis: str, *, touches: tuple[str, ...] = (),
          reversible: bool = True, spend_cad: float = 0.0,
          spend_authorised_cad: float = 0.0, cell: str | None = None) -> Boundary:
    """Decide whether this change is one the system is allowed to make to itself.

    Structural first, lexical second (C-20). The structural half reads what the change
    touches: the declared surfaces (normalised, so 'Product_Truth' is product_truth), plus
    the protected surfaces the text itself touches -- a gate named in prose, a protected
    module's constant, Product Truth described in plain words. A protected surface the text
    touches but the declaration omits is refused; a declared protected surface is allowed
    only to the department that operates it (when `cell` is given), and `improve.tiers`
    grades it `gate`, which needs the owner. The lexical half is the net behind it: a
    weakening verb governing a gate object anywhere in its clause.

    Ordered so the most serious refusal is the one reported: fabricating evidence, then
    weakening a gate, then an undeclared or unowned protected surface, then reversibility
    and budget.
    """
    fabricating = _mentions(hypothesis, _FABRICATION)
    if fabricating:
        return Boundary(False,
                        f"the hypothesis proposes {fabricating!r}, which manufactures the "
                        f"evidence rather than the result. Every number this company reports "
                        f"is only worth what produced it",
                        "#102: may never fabricate evidence")

    declared = normalise_touches(touches)
    declared_protected = [name for name in declared
                          if name in PROTECTED_GATES or _gate_tier_surface(name)]
    implied = implied_surfaces(hypothesis)
    protected = list(dict.fromkeys(declared_protected + list(implied)))

    loosening = _mentions(hypothesis, _LOOSENING) or _weakens(hypothesis)
    if loosening and not declared and not implied:
        # Loosening something unprotected is ordinary tuning, and allowed — but the surfaces
        # it touches have to have been declared, or every check below is trivially avoided
        # by saying nothing.
        return Boundary(False,
                        f"the hypothesis proposes to {loosening!r} without declaring what "
                        f"it touches. An undeclared surface cannot be checked against the "
                        f"protected list, which makes the list advisory",
                        "#102: the surfaces a change touches must be declared")
    if loosening and not protected:
        # A hypothesis that weakens something that is a gate by nature, or whose stated
        # purpose is that fewer things are refused, is judged by what it says rather than by
        # what it declared (#102, #178).
        intrinsic = _intrinsic_object(hypothesis)
        if not intrinsic and loosening.rsplit(" ", 1)[-1] in _INTRINSIC_GATE_OBJECTS:
            intrinsic = loosening.rsplit(" ", 1)[-1]
        if not intrinsic and _REFUSAL_EFFECT.search((hypothesis or "").lower()):
            intrinsic = loosening.rsplit(" ", 1)[-1]
        if intrinsic:
            protected = [intrinsic]
    if protected and loosening:
        return Boundary(False,
                        f"this proposes to {loosening!r} on {protected}, which improves the "
                        f"metric by damaging the thing that produces it. From inside the "
                        f"loop, weakening a gate and fixing a defect look identical: a "
                        f"change, then a better number",
                        "#102: may never weaken a policy gate")

    undeclared = {name: how for name, how in implied.items() if name not in declared}
    if undeclared:
        detail = "; ".join(f"{name} ({how})" for name, how in undeclared.items())
        return Boundary(False,
                        f"the hypothesis touches the protected surface(s) {detail} without "
                        f"declaring them in `touches`. A change is classified by what it "
                        f"touches, and a protected surface reached through wording is still "
                        f"reached; declare it, and it is graded as the gate it is",
                        "#102: the protected surfaces a change touches must be declared")

    if cell is not None:
        foreign = [name for name in declared if name in GATE_OPERATORS
                   and cell not in GATE_OPERATORS[name]]
        if foreign:
            return Boundary(False,
                            f"{cell!r} does not operate {foreign}. A department may propose a "
                            f"change to a protected gate only if it runs that gate, and then "
                            f"only for the owner's decision; a gate no department runs is "
                            f"changed by the owner, not by the loop",
                            "#102: a protected gate is changed only by the department that "
                            "runs it, and only for the owner")

    if not reversible:
        return Boundary(False,
                        "an improvement with no way back is not an experiment, it is a "
                        "decision — and #93 requires every promotion to store its rollback "
                        "path before it is applied",
                        "#93: automatic rollback")

    if spend_cad > spend_authorised_cad:
        return Boundary(False,
                        f"CA${spend_cad:.2f} exceeds the CA${spend_authorised_cad:.2f} "
                        f"authorised for improvement work. Continuous learning is not "
                        f"permission to burn tokens (#99)",
                        "#99: improvement budget")

    return Boundary(True)


def _gate_tier_surface(name: str) -> bool:
    """A declared surface `improve.tiers` grades as a gate is protected here too."""
    from .tiers import SURFACE_TIER

    return SURFACE_TIER.get(normalise_surface(name)) == "gate"


def _names_protected_gate(text: str) -> list[str]:
    """Protected gates named in prose: `product truth`, `asset-truth`, `Deterministic_Validation`."""
    low = " " + re.sub(r"[\s_\-]+", " ", (text or "").lower()) + " "
    return [name for name in PROTECTED_GATES if f" {name.replace('_', ' ')} " in low
            or f" {name.replace('_', ' ')}s " in low]


def check_owner_authority(action: str) -> Boundary:
    """Refuse a self-improvement that quietly grants the system an owner-only power."""
    owner_only = ("publish", "kyc", "identity verification", "banking", "payout",
                  "legal acceptance", "advertising budget", "phase to production",
                  "graduate the phase", "connect etsy")
    hit = _mentions(action, owner_only)
    if hit:
        return Boundary(False,
                        f"{hit!r} is the owner's to decide. A system that can widen its own "
                        f"authority has none",
                        "#102: may never bypass owner authority")
    return Boundary(True)


def protected_surface(name: str) -> bool:
    return normalise_surface(name) in PROTECTED_GATES


def describe() -> dict:
    """The boundary, stated where the owner can read it rather than inferred from code."""
    return {
        "may": ["code", "prompts", "scoring weights", "workflows", "agent configuration",
                "cadences", "routing", "thresholds on unprotected surfaces"],
        "may_never": [
            "weaken a protected gate",
            "fabricate evidence, reviews, customers or revenue",
            "bypass owner authority",
            "disable a safety check",
            "spend beyond the authorised improvement budget",
            "promote a change with no rollback path",
        ],
        "protected_gates": list(PROTECTED_GATES),
        "why": ("Every number this company reports is produced by a check, so the cheapest "
                "way to improve any of them is to loosen the check. The improvement would be "
                "real, the measurement would be real, and the company would be worse."),
    }


_WORD_BOUNDARY = re.compile(r"\b")  # kept for future stricter matching
