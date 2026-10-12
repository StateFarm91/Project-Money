"""The customer-claim register: every promise the shop makes, its evidence, and its fence.

W4-COPY, owner directive 2026-10-11. Every claim a buyer can read in the storefront, FAQ,
policies, the pattern PDF or a listing description is listed here with:
- a verdict (SUPPORTED / QUALIFIED / REMOVED);
- the evidence that decides it;
- the wording now used;
- whether it is open for owner or legal review.

FORBIDDEN is the fence. These are wordings that would make a false claim:
- an invented human designer;
- physical testing or samples that never happened;
- photographs that do not exist;
- a hidden or human Laura;
- legal clearance nobody gave;
- a promise to message every buyer, which no API can deliver;
- the rejected machinery talk.

`scan()` refuses them in every customer surface (`surfaces()`), and the tests keep them out.

Rule: a legal question (licence enforceability, consumer-law refund rights, CASL, the Etsy
image rule for renderings) is recorded as OPEN for owner/legal review. It is never resolved
here by assertion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED = "SUPPORTED"
QUALIFIED = "QUALIFIED"     # true only with the qualification now written into the copy
REMOVED = "REMOVED"         # false or unsupportable; the wording is gone

OWNER = "owner"
LEGAL = "legal"


@dataclass(frozen=True)
class Claim:
    key: str
    topic: str
    was: str
    verdict: str
    evidence: str
    now: str
    review: str = ""        # "" | OWNER | LEGAL -- an open question, never resolved here
    review_question: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "topic": self.topic, "was": self.was, "verdict": self.verdict,
                "evidence": self.evidence, "now": self.now, "review": self.review,
                "review_question": self.review_question}


CLAIMS: tuple[Claim, ...] = (
    Claim("C-01", "AI involvement / designer",
          "Parts of this design were developed with AI assistance, directed and edited by the "
          "designer.",
          REMOVED,
          "'the designer' reads as a human designer; Brambleloop has none (Laura is an AI, "
          "D-FB-13). Etsy: 'Sellers must disclose within their listing description if an item "
          "is created with the use of AI' and 'Designed by a seller: original designs by a "
          "seller or seller-prompted AI art offered as a digital download' "
          "(gates.policy_knowledge creativity_standards, read 2026-09-26).",
          "This design was created with AI assistance, and every row's stitch count is checked "
          "before release. (gates.platform_policy.DISCLOSURES['ai_assisted_design'], carried "
          "verbatim in every listing description, the FAQ and the shop disclosure.)"),
    Claim("C-02", "originality",
          "Brambleloop Studio designs crochet patterns (original designs).",
          QUALIFIED,
          "Each CIR carries an originality record (products/originality, policy_knowledge "
          "creativity_standards 'originality'); competitor research is demand intelligence "
          "only (CLAUDE.md). 'Original' as a legal non-infringement assurance has not been "
          "reviewed.",
          "'Brambleloop Studio designs crochet patterns' -- the word 'original' is not used "
          "as a guarantee in customer copy.",
          LEGAL, "Is an originality/non-infringement statement wanted, and on what clearance?"),
    Claim("C-03", "testing / physical samples",
          "(no claim of test-making or physical samples anywhere)",
          SUPPORTED,
          "No PhysicalTest is complete (executor gate physical_proof closed in production "
          "2026-10-11); copy says 'We have not yet worked physical samples' and the FAQ says "
          "'we have not yet worked a physical sample'.",
          "'We have not yet worked physical samples, so make a gauge swatch first.' FORBIDDEN "
          "refuses tested-by / test-made / sample-made claims."),
    Claim("C-04", "stitch-count / chart accuracy",
          "every row's stitch count is checked; a chart that matches the words",
          SUPPORTED,
          "cir/compiler.py verifies every row's count and repeat division; cir/reverse.py "
          "reads the finished document back against the design; gates/certificate.py refuses "
          "release on a mismatch. Charts render from the same pattern (publish/charts.py, "
          "cir/twin.py). Listings exist only for certified releases.",
          "'every row's stitch count adds up, every repeat divides evenly, and the written "
          "pattern is read back against the chart'; listing: 'A chart drawn from the same "
          "pattern as the written instructions, so the two always agree'."),
    Claim("C-05", "US/UK terminology",
          "two complete PDFs, one in US terms and one in UK terms",
          SUPPORTED,
          "publish/pdf.py TERMINOLOGIES; assets.build renders both and store.publish attaches "
          "both (commerce/seo.py build_description note).",
          "unchanged"),
    Claim("C-06", "digital delivery",
          "instant download; no processing time; nothing is posted",
          SUPPORTED,
          "Etsy help 115013328108 'How to Download a Digital Item' (read 2026-10-11 through "
          "the Help Center API): files are on the Purchases page once payment clears.",
          "unchanged"),
    Claim("C-07", "commercial use of finished items",
          "finished items may be sold by individual makers and small businesses, not "
          "manufactured at scale",
          QUALIFIED,
          "commerce.terms FINISHED_ITEM_SALE (decided by the build); terms.enforceable is "
          "False and every surface says 'not yet been through legal review'.",
          "unchanged sentence, rendered from commerce.terms with its review caveat",
          LEGAL, "Are these licence terms enforceable as written (Canada, US, EU buyers)?"),
    Claim("C-08", "corrections / version updates",
          "corrections and revisions are free forever, and buyers are told when the version "
          "they own changes; 'we send the corrected file to everyone who bought it'",
          QUALIFIED,
          "No Etsy Messages API exists ('conversation' 1 occurrence in Etsy's OpenAPI, "
          "intel.etsy_surfaces), so a notice to every past buyer would be a person typing "
          "each message. Etsy help 115015628347 says nothing about past buyers receiving "
          "replaced files. 'Forever' was a perpetual promise nobody reviewed.",
          "'corrections are free: a corrected pattern replaces the old file, and anyone who "
          "bought an earlier version can ask for the corrected one at any time'; 'we correct "
          "the pattern itself and send you the corrected file'.",
          OWNER, "Do you want to commit to proactively messaging past buyers on a correction "
                 "(manual Etsy Messages)? Until you do, the copy promises only on request."),
    Claim("C-09", "redistribution limits",
          "the pattern file, its charts and its photographs may not be shared...",
          QUALIFIED,
          "The shop has no photographs (every image is a rendering; "
          "store_foundation.readiness LICENCE_MENTIONS_PHOTOGRAPHS).",
          "'the pattern file, its charts and its images may not be shared, resold, uploaded "
          "or included in another publication'",
          LEGAL, "Enforceability of the redistribution term (same review as C-07)."),
    Claim("C-10", "refunds / cancellations",
          "Etsy does not allow a seller to accept a return on a digital listing",
          QUALIFIED,
          "Etsy help 115013328108: 'digital listings are not able to be returned or canceled. "
          "If there's a problem with your digital order, like it's not as described in the "
          "listing or the seller never delivers the file, you may be covered under Etsy's "
          "Purchase Protection.' A seller can still refund an order.",
          "'Digital patterns cannot be returned or cancelled: Etsy does not allow returns on "
          "digital listings ... A digital item that is not as described, or never arrives, "
          "may also be covered by Etsy's Purchase Protection.' No refund is refused in "
          "words; 'we will put it right'.",
          LEGAL, "Consumer-law rights for digital content (EU withdrawal waiver, Quebec/"
                 "provincial law) -- does the returns text need a statutory-rights sentence?"),
    Claim("C-11", "AI imagery / listing images",
          "the pictures are digital renderings of each finished design, not photographs",
          QUALIFIED,
          "True and disclosed (platform_policy.DISCLOSURES disclosed_render). But Etsy's "
          "listing image rule as held: 'Your own photographs or video content--not stock "
          "photos, artistic renderings, or photos used by other sellers or sites are required "
          "for listings' (policy_knowledge listing_image_rules).",
          "disclosure unchanged; no copy calls a rendering a photo (FORBIDDEN)",
          OWNER, "Policy review: does a rendered finished-object image satisfy Etsy's image "
                 "rule for a digital pattern listing, or must the first image be the pattern "
                 "document / chart itself until a real sample is photographed?"),
    Claim("C-12", "support commitments",
          "questions answered through Etsy Messages against the exact version bought",
          QUALIFIED,
          "Etsy Messages has no API, so every reply is sent by the human account holder; no "
          "response time is promised anywhere (FORBIDDEN refuses 'within N hours').",
          "unchanged channel; no response-time promise",
          OWNER, "Confirm you will answer Etsy Messages (the only support channel)."),
    Claim("C-13", "Laura",
          "Laura is Brambleloop's AI founder and the face of the shop",
          SUPPORTED,
          "D-FB-11..13 (spec/07): AI, never human, never the legal owner or seller; lint "
          "TRUTH_LAURA_HUMAN_CLAIM.",
          "'She is an AI, not a person, and we will always say so.'"),
    Claim("C-14", "seller identity",
          "sold on Etsy by the human holder of this shop account",
          SUPPORTED,
          "Etsy's account holder is the legal seller (etsy_constraints, Owner role).",
          "unchanged"),
    Claim("C-15", "machinery talk",
          "'automated pattern compiler', 'the way software gets made', 'machine-readable'",
          REMOVED,
          "Owner rejected v1 store copy 2026-10-06; owner directive 2026-10-11 'no "
          "unnecessary AI-infrastructure talk'. brand.storefront.ABOUT still held the v1 "
          "text and the Info & appearance owner action pointed at it.",
          "plain checks language; brand.storefront.ABOUT now is store copy v3"),
    Claim("C-16", "legal clearance",
          "(none claimed)",
          SUPPORTED,
          "No trademark, licence or safety clearance exists (owner decision brand_clearance "
          "open); FORBIDDEN refuses 'trademark registered', 'legally reviewed', 'certified'.",
          "the terms say 'have not yet been through legal review'"),
)

# Wordings that would make a false claim. (pattern, why) -- case-insensitive.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    (r"\b(edited|directed|designed|created|written) by (the|our|a|my) designer\b",
     "invents a human designer (C-01)"),
    (r"\bour designer\b|\bthe designer'?s\b", "invents a human designer (C-01)"),
    (r"\b(i|we) (designed|crocheted|made|tested) (this|these|it|each|every)\b",
     "first-person making or testing that did not happen (C-03)"),
    (r"\btest(ed)?[- ](made|crocheted|knit|worked)\b|\bpattern testers?\b|\btested by\b"
     r"|\btester[- ]approved\b|\btested and (proven|approved)\b",
     "physical testing that has not happened (C-03)"),
    (r"\bsample (was|has been) (made|worked|crocheted)\b|\bphotographed sample\b"
     r"|\bour (finished )?samples?\b", "a physical sample that does not exist (C-03)"),
    (r"\bphoto(graph)?s? of (the|our|my) (finished|actual|real)\b|\breal photos?\b",
     "calls a rendering a photograph (C-11)"),
    (r"\bto everyone who bought\b|\bevery(one| buyer) who (has )?bought\b.{0,40}\b(send|sent|"
     r"email|message|notif)", "a proactive notice no channel can deliver (C-08)"),
    (r"\bfree forever\b|\bforever free\b", "an unreviewed perpetual promise (C-08)"),
    (r"\bbuyers are told when\b", "a proactive notice no channel can deliver (C-08)"),
    (r"\bwithin \d+ (minutes?|hours?|days?)\b|\b24/7\b|\bsame[- ]day (reply|response)\b",
     "a response-time promise nobody committed to (C-12)"),
    (r"\b(legally (reviewed|cleared|approved)|trademark(ed)? registered|registered trademark"
     r"|lawyer[- ]approved)\b", "legal clearance nobody gave (C-16)"),
    (r"\blaura (is|was) (a )?(real|human|person|woman)\b|\blaura (crochet|knit|made|tested)",
     "presents Laura as human or as a maker (C-13)"),
    (r"\bcompiler\b|\bthe way software gets made\b|\bmachine[- ]readable\b",
     "rejected machinery talk (C-15)"),
    (r"\bits photographs\b", "the shop has no photographs (C-09)"),
)

_FORBIDDEN = tuple((re.compile(p, re.I), why) for p, why in FORBIDDEN)


def scan(text: str) -> list[dict]:
    """Every forbidden wording in `text`, with why it is forbidden."""
    out = []
    for rx, why in _FORBIDDEN:
        for m in rx.finditer(text or ""):
            out.append({"match": m.group(0), "why": why})
    return out


def sample_description() -> str:
    """A listing description built by the real template from representative facts."""
    from ..commerce import seo

    return seo.build_description(
        "Market Basket", size_label="20 x 20 x 12 cm", yardage_lines=["Yarn A: 180 m"],
        tolerance_pct=15, difficulty="Easy", colors=["Oat"], terminology="US",
        gauge_line="14 sts x 16 rows = 10 cm on a 5 mm hook", stitches=["sc", "ch"],
        why_it_matters="Why it is worth making: a quick, practical make.")


def surfaces() -> dict[str, str]:
    """Every customer-facing text this repository produces, keyed by where it appears."""
    from ..brand import storefront
    from ..commerce import shop_package
    from ..commerce import terms as T
    from ..gates import platform_policy
    from ..publish import pdf
    from . import copy_v2

    out = {f"copy:{k}": v for k, v in copy_v2.customer_copy().items()}
    out["storefront:about"] = storefront.ABOUT
    for k, v in shop_package.policies().items():
        out[f"policy:{k}"] = v
    for surface in T.SURFACES:
        out[f"terms:{surface}"] = T.render(T.BRAMBLELOOP_TERMS, surface)
    for k, v in platform_policy.DISCLOSURES.items():
        out[f"disclosure:{k}"] = v
    out["pdf:ai_disclosure"] = pdf.AI_DISCLOSURE
    out["listing:description_template"] = sample_description()
    return out


def audit() -> dict:
    """Every surface scanned; `clean` only when no forbidden wording appears anywhere."""
    hits = {k: f for k, v in surfaces().items() if (f := scan(v))}
    return {"clean": not hits, "hits": hits, "claims": [c.to_dict() for c in CLAIMS],
            "open_reviews": [c.key for c in CLAIMS if c.review]}
