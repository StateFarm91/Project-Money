"""The proof stack: what this company can honestly claim about a pattern, and why.

Requirement 8. A flagship accumulates progressively stronger proof -- deterministic
validation, then independent reverse compilation, then a physical tester's example, then a
real customer's finished project, then somebody buying a second one -- and *marketing must
distinguish those levels honestly*.

That last sentence is the requirement. The first four words of it are the easy part; the
work is making the distinction impossible to blur, because the pressure runs one way. A
pattern that compiles and has never been made by a human being is genuinely well founded and
genuinely unproven, and "tested" is the word everybody reaches for anyway.

So three properties.

**A rung is a query, not a field.** Each level counts something -- a clean compile, a
reverse-compilation agreement, a recorded sample assessment, a customer project, a second
order from the same buyer. There is no parameter that sets a rung and no way to raise one
without changing what the database contains.

**The claim level is the highest *contiguous* rung.** A customer photograph arriving before
any tester has made the thing does not license "tested by makers" -- it licenses nothing the
rung below it did not, and the gap is reported rather than averaged away. Proof accumulates;
it does not leapfrog.

**Language is checked against the level, not against intention.** `check_claim` reads
customer-facing text for the phrases each rung licenses and refuses the ones above it. A
listing that says "maker-tested" at level two is refused with the level it would need, which
is a different thing from a person deciding to be careful.

The permission half of the requirement lives in `consent_required`: a photograph from a
tester or a customer is somebody else's picture of their own work, and it may not be
published without a recorded consent reference. Absent consent is not implied consent.
"""
from __future__ import annotations

from dataclasses import dataclass

ERROR, WARN = "ERROR", "WARN"


@dataclass(frozen=True)
class Rung:
    """One level of proof: what it shows, what it does not, and what it lets us say."""

    level: int
    key: str
    proves: str
    does_not_prove: str
    checked_by: str
    licenses: tuple[str, ...]


LADDER: tuple[Rung, ...] = (
    Rung(1, "deterministic_validation",
         "the pattern's own arithmetic is internally consistent",
         "that anybody can follow it, or that the result is worth making",
         "the CIR compiles with no errors",
         ("validated", "checked by software", "the counts add up")),
    Rung(2, "independent_reverse_compilation",
         "a second implementation reads the written pattern back to the same structure",
         "that a human reading it understands it -- two programs agreeing is not a reader",
         "the reverse compiler reproduces the CIR from the written text",
         ("independently verified", "machine-checked twice")),
    Rung(3, "physical_tester_example",
         "at least one person made the thing and it came out",
         "that it comes out for everybody, or at a different gauge",
         "a recorded sample assessment exists for this pattern version",
         ("maker tested", "tested", "test crocheted", "made by a tester")),
    Rung(4, "customer_project",
         "somebody who paid for it finished it",
         "that most buyers finish it -- one project is one project",
         "a customer project or review is recorded against this pattern",
         ("customers have made this", "finished projects", "reviewed by buyers")),
    Rung(5, "repeat_purchase",
         "a buyer came back for a second pattern",
         "that the catalogue retains buyers generally",
         "a second order exists from a buyer who already bought one",
         ("customers come back", "repeat buyers", "best seller")),
)

RUNG_BY_KEY: dict[str, Rung] = {r.key: r for r in LADDER}

# Every phrase any rung licenses, mapped to the level that earns it. Matched on the text a
# customer actually reads, because that is where the claim is made.
_PHRASE_LEVEL: dict[str, int] = {
    phrase: rung.level for rung in LADDER for phrase in rung.licenses}

# Sources whose imagery is somebody else's picture of their own work.
NEEDS_CONSENT: tuple[str, ...] = ("tester", "customer")


class ProofRefused(ValueError):
    """A claim above the level the evidence reaches, or an unconsented photograph."""


def reached(states: dict[str, bool]) -> dict:
    """The claim level, which is the highest *contiguous* rung, plus what leapfrogged.

    Contiguous on purpose. A customer photograph arriving before any tester made the thing is
    real and does not license "tested by makers" -- proof accumulates rather than leapfrogs,
    and reporting the highest rung reached in isolation is how a listing ends up claiming a
    test nobody ran.
    """
    unknown = sorted(set(states) - set(RUNG_BY_KEY))
    if unknown:
        raise ProofRefused(f"{unknown} are not rungs of this ladder: {sorted(RUNG_BY_KEY)}")

    level = 0
    for rung in LADDER:
        if not states.get(rung.key):
            break
        level = rung.level
    ahead = [r.key for r in LADDER if r.level > level and states.get(r.key)]
    return {
        "level": level,
        "rung": LADDER[level - 1].key if level else "",
        "reached": [r.key for r in LADDER if states.get(r.key)],
        "claim_level": level,
        "ahead_of_the_ladder": ahead,
        "licenses": sorted({p for r in LADDER if r.level <= level for p in r.licenses}),
        "proves": LADDER[level - 1].proves if level else "nothing yet",
        "does_not_prove": (LADDER[level - 1].does_not_prove if level else
                           "anything at all -- this pattern has not been compiled"),
        "why": (
            "nothing on this ladder has been established yet" if not level else
            f"level {level}: {LADDER[level - 1].proves}"
            + (f". {ahead} is established and does not raise the claim level, because proof "
               f"accumulates rather than leapfrogs: the rung under it is missing" if ahead
               else "")),
    }


def check_claim(text: str, states: dict[str, bool]) -> list[dict]:
    """Refuse customer-facing language that claims more proof than exists.

    Read against the level rather than against intention. "Maker tested" on a pattern nobody
    has made is the same sentence whether somebody meant it or reached for it, and this is
    the only place that difference stops mattering.
    """
    level = reached(states)["claim_level"]
    lowered = (text or "").lower()
    out: list[dict] = []
    for phrase, needs in sorted(_PHRASE_LEVEL.items()):
        if phrase in lowered and needs > level:
            rung = LADDER[needs - 1]
            out.append({
                "phrase": phrase, "needs_level": needs, "have_level": level,
                "rung": rung.key,
                "why": (f"{phrase!r} claims {rung.proves}, which is level {needs}. This "
                        f"pattern is at level {level}. The check is {rung.checked_by}"),
            })
    return out


def consent_required(source: str, consent_ref: str | None) -> dict:
    """A tester's or a customer's photograph needs a recorded permission, not an assumption.

    The requirement says "with appropriate permission". Appropriate means recorded: a
    reference to where the permission is, so that somebody can go and look. Absent consent is
    not implied consent, and a photograph is the one asset class where getting this wrong is
    a wrong done to a specific person rather than a number being off.
    """
    needs = (source or "").strip().lower() in NEEDS_CONSENT
    have = bool((consent_ref or "").strip())
    return {
        "source": source,
        "needs_consent": needs,
        "has_consent": have,
        "publishable": (not needs) or have,
        "why": ("this source does not require a permission record" if not needs else
                "a recorded permission reference is present" if have else
                f"a photograph from a {source} is their picture of their own work. Absent "
                f"consent is not implied consent, and a reference to where the permission "
                f"lives is what makes it checkable rather than remembered"),
    }


def states_from_db(db, slug: str, version: str = "") -> dict[str, bool]:
    """Read each rung from rows, so no code change can raise one.

    The certificate is the evidence for the first two rungs and it is the right evidence: it
    is granted only when no stage produced an error, and it records which stages ran. A
    granted certificate whose `stages_run` contains "reverse" is precisely the claim rung two
    makes -- a second implementation read the written pattern back and agreed.

    Rungs four and five read False for as long as this company has no orders. False here
    means "not established", which is the same thing a listing has to say, and the key is
    present rather than absent because a missing key and an unreached rung look identical to
    a caller and mean completely different things.
    """
    from sqlalchemy import select

    from ..core.models import PatternVersion, PhysicalTest, Product

    states = {r.key: False for r in LADDER}
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        certificates = []
        if product is not None:
            for row in s.scalars(select(PatternVersion).where(
                    PatternVersion.product_id == product.id)):
                if version and row.version != version:
                    continue
                if row.certificate:
                    certificates.append(row.certificate)
        tests = [t for t in s.scalars(select(PhysicalTest).where(
            PhysicalTest.product_slug == slug))
            if (not version or t.version == version) and t.completed_at is not None]

    granted = [c for c in certificates if c.get("granted")]
    states["deterministic_validation"] = any(
        "compile" in (c.get("stages_run") or []) for c in granted)
    states["independent_reverse_compilation"] = any(
        "reverse" in (c.get("stages_run") or []) for c in granted)
    # A completed test that *failed* is evidence and is not this rung: rung three says the
    # thing came out, and a sample that disagreed with the pattern is the most valuable
    # possible result and the opposite of a proof point.
    states["physical_tester_example"] = any(t.passed for t in tests)
    return states


def report(db, slug: str, version: str = "") -> dict:
    """The full proof position for one pattern, in the shape a listing has to respect."""
    states = states_from_db(db, slug, version)
    out = reached(states)
    return {
        "slug": slug,
        "version": version,
        "states": states,
        "ladder": [{"level": r.level, "rung": r.key, "proves": r.proves,
                    "does_not_prove": r.does_not_prove, "checked_by": r.checked_by,
                    "licenses": list(r.licenses), "established": states.get(r.key, False)}
                   for r in LADDER],
        **out,
        "not_reachable_yet": {
            "customer_project": "waits on orders, which is the customers gate",
            "repeat_purchase": "waits on a buyer returning, which is the same gate twice",
        },
    }
