"""What the buyer may do with what they bought, decided once and said the same way everywhere.

Requirement 40. Every crochet pattern on earth carries terms, most of them copied from another
pattern, and the two failures are equally ordinary.

The first is that the terms were never decided. "Do not redistribute" appears because it
appears on everything, and then a customer asks whether they may sell finished items at a
craft fair — which is the question they actually have — and the answer is invented in a
support reply. That reply is now the terms.

The second is drift. The PDF says one thing, the listing says another and the FAQ says a
third, because they were written at different times by different parts of the system. A buyer
who finds the discrepancy is entitled to rely on the most favourable one, and a seller who
finds it has a support problem with no correct answer.

So: five axes, each with a closed set of options chosen deliberately; one place they are
decided; and a consistency check that refuses a set where the three surfaces disagree.

The module is explicit about what it is not. These are commercial terms this company chooses
to offer, rendered consistently. Whether any of them is enforceable is a legal question, and
`reviewed` stays False until somebody qualified has said so — a term nobody reviewed is a
promise rather than a protection, which is fine as long as nobody relies on it as the second.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# The five axes #40 names, each with the options a pattern seller actually chooses between.
# Closed, because free text is how "do not redistribute" arrives without anybody deciding.
PDF_USE = "pdf_use"
FINISHED_ITEM_SALE = "finished_item_sale"
REDISTRIBUTION = "redistribution"
SUPPORT_POLICY = "support_policy"
VERSION_POLICY = "version_policy"

AXES: tuple[str, ...] = (PDF_USE, FINISHED_ITEM_SALE, REDISTRIBUTION, SUPPORT_POLICY,
                         VERSION_POLICY)

OPTIONS: dict[str, dict[str, str]] = {
    PDF_USE: {
        "personal_single_user": ("for the buyer's own use, on their own devices, printed as "
                                 "often as they like"),
        "personal_and_teaching": ("for the buyer's own use, and to teach from in a class "
                                  "where each participant has their own copy"),
    },
    FINISHED_ITEM_SALE: {
        # The question customers actually ask, and the one most patterns answer by accident.
        "permitted_with_credit": ("finished items may be sold, in any quantity, with a "
                                  "credit to Brambleloop as the pattern designer"),
        "permitted_small_scale": ("finished items may be sold by individual makers and small "
                                  "businesses, not manufactured at scale"),
        "not_permitted": "finished items may not be sold",
    },
    REDISTRIBUTION: {
        "prohibited": ("the pattern file, its charts and its photographs may not be shared, "
                       "resold, uploaded or included in another publication"),
    },
    SUPPORT_POLICY: {
        "version_aware_email": ("questions are answered by email, from the exact version of "
                                "the pattern that was bought"),
        # Added 2026-09-25, and the chosen option, because the one above named a channel this
        # company does not have. There is no support mailbox; the shop's message thread is the
        # route, and it is the route the pattern PDF has always told buyers to use. Printing
        # the two side by side on one page is what made the difference visible: the licence
        # block said "answered by email" directly above a paragraph saying "tell us through
        # the shop you bought it from". A term that names an unreachable channel is worse than
        # a narrower one, because the buyer who tries it concludes nobody is there.
        "version_aware_shop_message": ("questions are answered through the shop the pattern "
                                       "was bought from, against the exact version that was "
                                       "bought"),
    },
    VERSION_POLICY: {
        "free_updates_forever": ("corrections and revisions are free forever, and buyers are "
                                 "told when the version they own changes"),
        "free_updates_one_year": "corrections and revisions are free for one year",
    },
}

# Where the terms have to say the same thing. #40's own list, and the three that drift.
SURFACES: tuple[str, ...] = ("pdf", "listing", "faq")


class TermsRefused(Exception):
    """A term nobody chose, or three surfaces saying three things."""


@dataclass(frozen=True)
class Terms:
    """One deliberate set of customer-use terms."""

    choices: dict
    decided_on: str = ""
    decided_by: str = ""
    legal_review: dict | None = None

    def __post_init__(self) -> None:
        missing = [a for a in AXES if a not in self.choices]
        if missing:
            raise TermsRefused(
                f"{missing} were never decided. An undecided term is answered for the first "
                f"time in a support reply, by whoever is answering, and that reply becomes "
                f"the terms (#40)")
        for axis, option in self.choices.items():
            if axis not in AXES:
                raise TermsRefused(f"{axis!r} is not a terms axis: {list(AXES)}")
            if option not in OPTIONS[axis]:
                raise TermsRefused(
                    f"{axis}: {option!r} is not an option. Options are closed so the choice "
                    f"is made once rather than phrased differently each time: "
                    f"{sorted(OPTIONS[axis])}")

    @property
    def enforceable(self) -> bool:
        """Deliberately not the same as 'decided'.

        These are terms this company offers. Whether any of them binds anybody is a legal
        question, and until somebody qualified has answered it the honest word is 'stated'.
        """
        return bool(self.legal_review and self.legal_review.get("reviewed_by"))

    def sentence(self, axis: str) -> str:
        return OPTIONS[axis][self.choices[axis]]

    def to_dict(self) -> dict:
        return {
            "choices": dict(self.choices),
            "sentences": {a: self.sentence(a) for a in AXES},
            "decided_on": self.decided_on or date.today().isoformat(),
            "decided_by": self.decided_by,
            "enforceable": self.enforceable,
            "legal_review": self.legal_review,
            "note": ("Stated terms, rendered identically on every surface. Enforceability is "
                     "a legal question and stays False until somebody qualified has "
                     "answered it -- a term nobody reviewed is a promise, not a protection."),
        }


# The terms this company has actually chosen. Recorded here rather than assembled per product,
# because per-product terms are how three products end up with three answers to the craft-fair
# question.
#
# **This is the canonical Launch-0 licence, and it is the only one.** Owner ruling
# 2026-09-25: one conservative source, every surface renders from it, no divergent copies.
# Conservative means what the four sentences below say -- the buyer's own use, finished items
# sold by individual makers and small businesses, no manufacture at scale, and no passing on
# the file, the charts or the photographs.
#
# Four surfaces now render from here: the pattern PDF (`publish.pdf.licence_paragraphs`), the
# listing description (`commerce.seo`), the shop's policies and FAQ (`commerce.shop_package`,
# which `brand.storefront` reads) and the content FAQ (`growth.content`). None of them holds
# licence prose of its own, and `consistency()` is run against text extracted from the real
# PDF rather than against this module's own rendering of it.
#
# **No legal reason found that professional review must precede the first sale.** These are
# terms this company offers about its own copyright work in its own jurisdiction; nothing
# here is a regulated disclosure, a consumer-law notice or a statement whose absence voids a
# sale. `enforceable` stays False and says so on the page, which is the honest word for an
# unreviewed term. Review is scheduled before material scale -- owner decision 4 in
# BUILD_STATE, 30 minutes, max CA$500 -- and is not a launch blocker.
BRAMBLELOOP_TERMS = Terms(
    choices={
        PDF_USE: "personal_and_teaching",
        FINISHED_ITEM_SALE: "permitted_small_scale",
        REDISTRIBUTION: "prohibited",
        SUPPORT_POLICY: "version_aware_shop_message",
        VERSION_POLICY: "free_updates_forever",
    },
    # The five axes were decided on 2026-09-19; the support channel was amended on 2026-09-25
    # when the PDF began rendering from here and named a mailbox that does not exist.
    decided_on="2026-09-25",
    decided_by="build",
    legal_review=None,
)


def render(terms: Terms, surface: str) -> str:
    """The terms as they appear on one surface — same substance, same order, every time.

    Rendered from one source rather than written per surface. Writing them three times is
    what produces three sets of terms, and the difference is never noticed by the person who
    wrote the third one.
    """
    if surface not in SURFACES:
        raise TermsRefused(f"{surface!r} is not a surface: {list(SURFACES)}")
    lines = [terms.sentence(axis) for axis in AXES]
    if surface == "pdf":
        head = "What you may do with this pattern"
    elif surface == "listing":
        head = "Pattern use and support"
    else:
        head = "Can I sell what I make?"
    body = "\n".join(f"- {line}" for line in lines)
    tail = ("" if terms.enforceable else
            "\n\nThese are the terms Brambleloop offers; they have not yet been through "
            "legal review.")
    return f"{head}\n\n{body}{tail}"


def consistency(pdf_text: str, listing_text: str, faq_text: str,
                terms: Terms | None = None) -> dict:
    """#40's real requirement: the three surfaces must not disagree.

    Checked on substance rather than on wording, because the surfaces are allowed different
    headings and are not allowed different answers. A buyer who finds a discrepancy is
    entitled to rely on the most favourable version, and a seller who finds one has a support
    question with no correct answer.
    """
    terms = terms or BRAMBLELOOP_TERMS
    surfaces = {"pdf": pdf_text, "listing": listing_text, "faq": faq_text}
    missing: list[dict] = []
    for axis in AXES:
        sentence = terms.sentence(axis)
        for name, text in surfaces.items():
            if sentence not in (text or ""):
                missing.append({"axis": axis, "surface": name,
                                "expected": sentence})
    return {
        "consistent": not missing,
        "divergences": missing,
        "surfaces": list(SURFACES),
        "note": ("All three surfaces render from one decision. A divergence here means one "
                 "of them was written by hand, which is the only way this drifts (#40)."),
    }


def record_legal_review(terms: Terms, *, reviewed_by: str, reviewed_on: str,
                        scope: str) -> Terms:
    """Record that somebody qualified has looked. Only the owner can arrange this."""
    if not reviewed_by.strip() or not scope.strip():
        raise TermsRefused(
            "a legal review records who reviewed it and what they covered, or it is the "
            "same unreviewed terms with a more confident label")
    return Terms(choices=dict(terms.choices), decided_on=terms.decided_on,
                 decided_by=terms.decided_by,
                 legal_review={"reviewed_by": reviewed_by.strip(),
                               "reviewed_on": reviewed_on,
                               "scope": scope.strip()})
