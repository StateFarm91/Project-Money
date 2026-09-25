"""What Etsy actually requires of a digital-download listing, read from Etsy's own document.

The Etsy client in `integrations.etsy` maps a listing we already trust onto Etsy's shape and
enforces the limits the policy gate already enforces: 140-character title, 13 tags of 20
characters, 13 materials. Those limits are real and they are not the whole contract, and the
part that is missing is the part that only fails on the day it matters -- because every one
of these rules is enforced by Etsy's API rather than by anything here, so the first time a
violation is discovered is the first time a request is sent.

This module is that contract, written down, with each clause labelled by where it came from.

**SOURCED means a sentence exists.** Every SOURCED clause here was read out of Etsy's own
published OpenAPI document at `ETSY_OPENAPI_URL` on `READ_ON`, and carries the sentence it
came from. That is a stronger claim than "we believe Etsy requires this", and it is a
checkable one: the document is public, the quote is here, and a future reader can diff them.

**INFERRED means we reasoned.** An inferred clause is this company's reading, usually of what
the absence of a rule means. It is labelled so that it can be argued with. The honest
distinction matters more than the count: Etsy changes its requirements, and a stale assumption
wearing a sourced label is worse than no label at all.

Three things in here are the reason it exists, and all three are invisible to the limits the
client already checks:

1. **A draft listing is not a published one, and publishing needs an image.** Etsy: "Setting
   a `draft` listing to `active` will also publish the listing on etsy.com and requires that
   the listing have an image set." Nothing in this system uploads a listing image to Etsy.
   The client uploads the *pattern file*, which is a different endpoint and a different thing.
   A catalogue of drafts that cannot be activated is a shop that opens empty.

2. **Etsy's character sets are narrower than "a string".** Titles may use `%`, `:`, `&` and
   `+` once each and no other symbols; tags allow letters, digits, whitespace, hyphen and
   apostrophe; materials allow letters, digits and whitespace *only*. A material called
   "100% cotton" is refused by Etsy and by nothing here. This is the failure mode that scales
   with the catalogue: it is fine until one product's yarn is written with a percent sign.

3. **The request is form-encoded.** Etsy's document lists exactly one request media type for
   creating a listing, and it is `application/x-www-form-urlencoded`. The transport sends
   JSON. That is recorded here rather than silently fixed, because the fix cannot be verified
   without a live call and a client that was changed on the strength of a reading is not
   better than one that was not -- it is the same untested code with more confidence.

What this module does not do is decide whether a listing is *good*. `commerce.seo`,
`publish.eligibility` and the policy gate already do that, and this restates none of it.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Where every SOURCED clause below was read from, and when. A snapshot, not a constant: the
# document is versioned and Etsy changes it, so a clause that cannot name its reading date
# cannot be trusted to still be true.
ETSY_OPENAPI_URL = "https://www.etsy.com/openapi/generated/oas/3.0.0.json"
ETSY_OPENAPI_VERSION = "3.0.0"
READ_ON = "2026-09-24"

# How old a reading may be before the clauses it supports are historical rather than current.
# Matches `gates.platform_policy.MAX_AGE_DAYS`'s reasoning and is stated separately because it
# governs a different document.
MAX_AGE_DAYS = 30

SOURCED = "sourced"
INFERRED = "inferred"


class SchemaRefused(ValueError):
    """A payload Etsy's own document says it will not accept."""


@dataclass(frozen=True)
class Clause:
    """One requirement, and the evidence for it.

    `quote` is empty for an INFERRED clause on purpose. A clause with no quote and a SOURCED
    label is the failure this dataclass exists to make impossible to write by accident.
    """

    key: str
    rule: str
    basis: str
    quote: str = ""

    def __post_init__(self) -> None:
        if self.basis not in (SOURCED, INFERRED):
            raise SchemaRefused(f"{self.key}: basis is {self.basis!r}, not sourced/inferred")
        if self.basis == SOURCED and not self.quote.strip():
            raise SchemaRefused(
                f"{self.key} claims to be sourced and quotes nothing. A sourced label with "
                f"no sentence behind it is an assumption that has stopped being arguable")

    def to_dict(self) -> dict:
        return {"key": self.key, "rule": self.rule, "basis": self.basis,
                "quote": self.quote, "read_from": ETSY_OPENAPI_URL, "read_on": READ_ON}


# ---------------------------------------------------------------------------
# The fields, and which of them a digital download actually needs

# createDraftListing's own `required` array, verbatim from the document's request schema.
REQUIRED_TO_CREATE: tuple[str, ...] = ("quantity", "title", "description", "price",
                                       "who_made", "when_made", "taxonomy_id")

# What a listing needs *in addition* before it can be made active. This is the gap that a
# draft-only integration cannot see.
REQUIRED_TO_ACTIVATE: tuple[str, ...] = ("image_ids",)

# Fields that a physical listing needs and a digital one does not. Listed rather than omitted
# because "we did not send it" and "it is not required" are different states, and only the
# second one is safe.
NOT_REQUIRED_FOR_DIGITAL: tuple[str, ...] = ("shipping_profile_id", "return_policy_id",
                                             "readiness_state_id")

# Accepted values, from the document's enums. Closed here because a value outside them is a
# rejected request rather than a question of taste.
TYPE_VALUES: tuple[str, ...] = ("physical", "download", "both")
WHO_MADE_VALUES: tuple[str, ...] = ("i_did", "someone_else", "collective")
UPDATE_STATE_VALUES: tuple[str, ...] = ("active", "inactive")

DIGITAL_TYPE = "download"

# The media type Etsy's document lists for createDraftListing and updateListing. One entry,
# not two: there is no JSON variant in the document.
REQUEST_ENCODING = "application/x-www-form-urlencoded"
UPLOAD_ENCODING = "multipart/form-data"

# The OAuth scope the write endpoints carry in the document's `security` block.
WRITE_SCOPE = "listings_w"

MAX_IMAGES = 20

CLAUSES: tuple[Clause, ...] = (
    Clause("required_to_create",
           "quantity, title, description, price, who_made, when_made and taxonomy_id are "
           "required to create a draft listing",
           SOURCED,
           "required: ['quantity', 'title', 'description', 'price', 'who_made', "
           "'when_made', 'taxonomy_id']"),
    Clause("image_required_to_publish",
           "a draft cannot be activated without at least one listing image",
           SOURCED,
           "Setting a `draft` listing to `active` will also publish the listing on etsy.com "
           "and requires that the listing have an image set."),
    Clause("images_are_a_separate_endpoint",
           "listing images are uploaded to the listing's own images endpoint; they cannot "
           "be attached by creating the listing",
           SOURCED,
           "Uploads or assigns an image to a listing identified by a shop ID with a listing "
           "ID. To upload a new image, set the image file as the value for the `image` "
           "parameter."),
    Clause("files_are_a_separate_endpoint",
           "the digital file is uploaded to the listing's files endpoint after the draft "
           "exists",
           SOURCED,
           "Uploads a new file for a digital listing, or associates an existing file with a "
           "specific listing."),
    Clause("shipping_profile_physical_only",
           "shipping_profile_id is required only for physical listings",
           SOURCED,
           "Required when listing type is `physical`."),
    Clause("return_policy_physical_only",
           "return_policy_id is required only for active physical listings, so a digital "
           "listing needs none",
           SOURCED,
           "Required for active physical listings. This requirement does not apply to "
           "listings of EU-based shops."),
    Clause("readiness_state_physical_only",
           "readiness_state_id (the processing profile) applies to active physical listings",
           SOURCED,
           "Returned only when the listing is `active` and of type `physical`"),
    Clause("title_character_set",
           "a title may contain letters, digits, punctuation, mathematical symbols, "
           "whitespace and the trademark, copyright and registered marks, and may use each "
           "of % : & + only once",
           SOURCED,
           "valid title strings contain only letters, numbers, punctuation marks, "
           "mathematical symbols, whitespace characters, ™, ©, and ®. "
           "You can only use the %, :, & and + characters once each."),
    Clause("tag_character_set",
           "a tag may contain letters, digits, whitespace, hyphen, apostrophe and the "
           "trademark, copyright and registered marks",
           SOURCED,
           "valid tag strings contain only letters, numbers, whitespace characters, -, ', "
           "™, ©, and ®."),
    Clause("material_character_set",
           "a material may contain letters, digits and whitespace, and nothing else",
           SOURCED,
           "Valid materials strings contain only letters, numbers, and whitespace "
           "characters."),
    Clause("form_encoded_request",
           "the create and update requests are form-encoded, not JSON",
           SOURCED,
           "requestBody content: application/x-www-form-urlencoded"),
    Clause("write_scope",
           "the write endpoints require the listings_w OAuth scope on the access token",
           SOURCED,
           "security: [{'api_key': [], 'oauth2': ['listings_w']}]"),
    Clause("image_count",
           f"a listing carries at most {MAX_IMAGES} images",
           SOURCED,
           "An array of numeric image IDs of the images in a listing, which can include up "
           "to 20 images."),
    Clause("taxonomy_required_properties",
           "some taxonomy nodes require listing properties (attributes), and which ones is "
           "only knowable by asking Etsy for that taxonomy id",
           SOURCED,
           "is_required: When true, listings assigned eligible taxonomy IDs require this "
           "property."),
    Clause("digital_quantity",
           "quantity is required and positive; for a file that is copied rather than "
           "consumed any number is arbitrary, so the system sends Etsy's maximum",
           INFERRED),
    Clause("draft_is_the_default",
           "createDraftListing takes no `state` field -- a created listing is a draft, and "
           "activation is the separate updateListing call",
           INFERRED),
    Clause("taxonomy_id_unverified",
           "the taxonomy id this system sends for patterns has not been read back from "
           "Etsy's seller taxonomy, which needs an authenticated call this phase forbids",
           INFERRED),
)

CLAUSES_BY_KEY: dict[str, Clause] = {c.key: c for c in CLAUSES}


# ---------------------------------------------------------------------------
# The character sets, as code

# Unicode general categories, because Python's `re` has no \p{...}. Spelled out so the
# mapping from Etsy's sentence to this code can be checked by eye.
_LETTER = ("Lu", "Ll", "Lt", "Lm", "Lo")
_DIGIT = ("Nd",)
_SPACE = ("Zs",)
_PUNCTUATION = ("Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po")
_MATH = ("Sm",)

_MARKS = "™©®"          # TM, (c), (R) -- allowed in titles and tags

TITLE_CATEGORIES = _LETTER + _DIGIT + _PUNCTUATION + _MATH + _SPACE
TITLE_EXTRA = _MARKS
# Allowed, but at most once each. A second one is a rejected request, and the title that
# produces it is the kind a template writes without anybody noticing: "Pattern & Chart &
# Written Instructions".
TITLE_ONCE_ONLY = "%:&+"

TAG_CATEGORIES = _LETTER + _DIGIT + _SPACE
TAG_EXTRA = "-'" + _MARKS

MATERIAL_CATEGORIES = _LETTER + _DIGIT + _SPACE
MATERIAL_EXTRA = ""


def offending_characters(text: str, categories: tuple[str, ...], extra: str) -> list[str]:
    """The characters Etsy would refuse, in the order they appear, deduplicated.

    Returned rather than counted so the refusal can name them. "invalid characters" sends
    somebody reading a 140-character title one glyph at a time; "the character '%'" does not.
    """
    bad: list[str] = []
    for char in text:
        if char in extra or unicodedata.category(char) in categories:
            continue
        if char not in bad:
            bad.append(char)
    return bad


def title_problems(title: str) -> list[str]:
    """Etsy's two rules about a title's characters, checked separately because they differ.

    One is a character set and the other is a budget, and a title can satisfy the first and
    fail the second -- which is exactly the case a set-only check waves through.
    """
    problems: list[str] = []
    bad = offending_characters(title, TITLE_CATEGORIES, TITLE_EXTRA + TITLE_ONCE_ONLY)
    if bad:
        problems.append(
            f"TITLE_CHARACTERS: Etsy refuses {bad} in a listing title; it allows letters, "
            f"numbers, punctuation, mathematical symbols and whitespace")
    for char in TITLE_ONCE_ONLY:
        count = title.count(char)
        if count > 1:
            problems.append(
                f"TITLE_REPEATED_SYMBOL: {char!r} appears {count} times and Etsy allows it "
                f"once in a title")
    return problems


def tag_problems(tags: list[str]) -> list[str]:
    problems: list[str] = []
    for tag in tags:
        bad = offending_characters(tag, TAG_CATEGORIES, TAG_EXTRA)
        if bad:
            problems.append(
                f"TAG_CHARACTERS: {tag!r} contains {bad}; Etsy allows letters, numbers, "
                f"whitespace, hyphen and apostrophe in a tag")
    return problems


def material_problems(materials: list[str]) -> list[str]:
    """Materials are the narrowest set of the three, and the one most likely to be violated.

    Letters, digits and whitespace only: no percent sign, no slash, no hyphen. Yarn is
    routinely described as "100% cotton" or "8/4 cotton", and both are refused by Etsy while
    reading as perfectly ordinary to everyone here.
    """
    problems: list[str] = []
    for material in materials:
        bad = offending_characters(material, MATERIAL_CATEGORIES, MATERIAL_EXTRA)
        if bad:
            problems.append(
                f"MATERIAL_CHARACTERS: {material!r} contains {bad}; Etsy allows letters, "
                f"numbers and whitespace only in a material")
    duplicates = sorted({m for m in materials if materials.count(m) > 1})
    if duplicates:
        problems.append(
            f"MATERIAL_DUPLICATES: {duplicates} appear more than once. A pattern worked in "
            f"six colours of one yarn has one material, not six, and Etsy's thirteen slots "
            f"are spent either way")
    return problems


def check_payload(payload: dict, *, images: int = 0, intended_state: str = "draft") -> list[str]:
    """Everything Etsy's document says about this payload that the client does not check.

    Deliberately additive. The limits the client already enforces -- title length, tag count,
    tag length, material count -- are not restated here, because a limit written in two places
    is a limit that will be changed in one of them.

    `images` is the number of listing images that will exist on the listing when it is
    activated. It defaults to zero, which is the true value for this system today.
    """
    problems: list[str] = []

    missing = [f for f in REQUIRED_TO_CREATE if payload.get(f) in (None, "", [])]
    if missing:
        problems.append(
            f"LISTING_MISSING_REQUIRED: {missing} are required by createDraftListing")

    kind = payload.get("type")
    if kind is not None and kind not in TYPE_VALUES:
        problems.append(f"LISTING_TYPE_INVALID: {kind!r} is not one of {list(TYPE_VALUES)}")
    if kind != DIGITAL_TYPE:
        problems.append(
            f"LISTING_NOT_DIGITAL: type is {kind!r}; a pattern is an instant download and a "
            f"physical listing would also require a shipping profile")

    who = payload.get("who_made")
    if who is not None and who not in WHO_MADE_VALUES:
        problems.append(f"LISTING_WHO_MADE_INVALID: {who!r} is not one of "
                        f"{list(WHO_MADE_VALUES)}")

    quantity = payload.get("quantity")
    if isinstance(quantity, int) and quantity <= 0:
        problems.append("LISTING_QUANTITY_NOT_POSITIVE: Etsy requires a positive non-zero "
                        "quantity even for a file")

    problems.extend(title_problems(str(payload.get("title", ""))))
    problems.extend(tag_problems(list(payload.get("tags") or [])))
    problems.extend(material_problems(list(payload.get("materials") or [])))

    if "state" in payload and payload["state"] not in ("draft",):
        problems.append(
            f"LISTING_STATE_ON_CREATE: {payload['state']!r} was set on creation. "
            f"createDraftListing takes no state field and activation is a separate "
            f"updateListing call, whose only accepted values are "
            f"{list(UPDATE_STATE_VALUES)}")

    if images > MAX_IMAGES:
        problems.append(f"LISTING_TOO_MANY_IMAGES: {images} exceeds Etsy's {MAX_IMAGES}")

    if intended_state == "active" and images < 1:
        problems.append(
            "LISTING_CANNOT_BE_ACTIVATED: Etsy refuses to activate a listing with no image "
            "set, and no listing image is uploaded anywhere in this system. The pattern "
            "file is not a listing image; it goes to a different endpoint")

    return problems


def form_encoded(payload: dict) -> dict[str, str]:
    """The same payload in the shape Etsy's document says the request body takes.

    Provided as a mapping rather than wired into the transport. The wire format cannot be
    verified without a live call, and a transport changed on the strength of a reading is the
    same untested code carrying more confidence than it did before. What this *can* do is
    make the shape explicit and testable now, so the change, when it is made, is a change to
    one line rather than an invention.

    Arrays become comma-separated strings because that is how the document describes them:
    "A comma-separated list of tag strings for the listing."
    """
    out: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


def gaps() -> list[dict]:
    """The distance between Etsy's contract and what this system produces today.

    Each entry names the clause it rests on, so a gap that stops being true when Etsy changes
    its document stops being true visibly. `blocks_launch` is the only field that matters on
    the day the phase moves, and it is set from what would actually fail, not from severity.
    """
    return [
        # 2026-09-25: the image-upload and JSON-body gaps were closed in code. They are not
        # deleted, because a gap between the contract and what this system *produces* was
        # replaced by a gap between what this system produces and what Etsy has confirmed --
        # and on launch day the second one fails just as loudly. What changed is the reason,
        # and the reason is now an owner action rather than a build task.
        {"gap": "the listing-image upload has never been confirmed by Etsy",
         "clause": "image_required_to_publish",
         "detail": ("integrations.etsy.EtsyClient.upload_image sends the binary in a part "
                    "named `image` to the listing's images endpoint, and read-back "
                    "verification checks that Etsy holds it. Exercised end to end against a "
                    "local server built from Etsy's document (tests/fake_etsy.py) and "
                    "against Etsy: never, because there are no credentials in this "
                    "environment. Until one real upload succeeds, 'this listing can be "
                    "activated' remains a reading of a document"),
         "blocks_launch": True},
        {"gap": "the form-encoded write path has never been confirmed by Etsy",
         "clause": "form_encoded_request",
         "detail": ("integrations.http.UrllibTransport now sets the Content-Type from the "
                    "body channel the caller used, and createDraftListing and updateListing "
                    "use the form channel. It sent application/json to both until "
                    "2026-09-25. Etsy refuses a request on its API key before it reads a "
                    "body, so no unauthenticated call can confirm the encoding and only the "
                    "owner's OAuth grant makes that possible"),
         "blocks_launch": True},
        {"gap": "nothing has ever authenticated against Etsy",
         "clause": "write_scope",
         "detail": ("integrations.etsy_oauth implements the authorization-code grant with "
                    "PKCE and the refresh grant, and integrations.etsy_probe is the "
                    "shadow-safe sequence that would exercise the write path -- read the "
                    "shop, create a draft, upload an image, update it, read it back, delete "
                    "it -- without activating anything or incurring a fee. It needs one "
                    "browser authorisation from the owner, which no code path can supply: "
                    "Etsy has no key-only route to a write scope"),
         "blocks_launch": True},
        # This entry said "character sets are not checked before sending" after the check was
        # written, which made the gap list wrong in the direction that matters least and is
        # noticed least. `build_payload` calls `check_payload`, so the check exists; what does
        # not exist is any confirmation that our reading of the character sets matches Etsy's
        # enforcement of them.
        {"gap": "the character-set rules are enforced from a reading, not from Etsy",
         "clause": "title_character_set",
         "detail": ("integrations.etsy.build_payload refuses a material written "
                    "'100% cotton' and a title with two ampersands, from the regexes in "
                    "Etsy's property descriptions. No listing has ever been refused by Etsy "
                    "for a character, so whether these rules are stricter or looser than "
                    "Etsy's is unknown; stricter costs a refusal we could have avoided, "
                    "looser costs a rejected listing at publish time"),
         "blocks_launch": False},
        {"gap": "the taxonomy id has never been read back from Etsy",
         "clause": "taxonomy_id_unverified",
         "detail": ("integrations.etsy.TAXONOMY_PATTERNS is 66 with the comment "
                    "'craft_supplies_and_tools.patterns'. Confirming it needs one "
                    "authenticated GET to getSellerTaxonomyNodes, which needs a keystring "
                    "this environment does not have and this phase would not use"),
         "blocks_launch": False},
        {"gap": "required listing properties for the chosen taxonomy are unknown",
         "clause": "taxonomy_required_properties",
         "detail": ("getPropertiesByTaxonomyId reports which attributes a taxonomy node "
                    "marks is_required. Nothing here calls it, and nothing here can set a "
                    "listing property. If the patterns node requires one, every listing is "
                    "refused and the message will name a property id"),
         "blocks_launch": False},
        {"gap": "duplicate materials are collapsed here and not upstream",
         "clause": "material_character_set",
         "detail": ("a CIR carries one material entry per colour, so an eight-colour blanket "
                    "arrives with the same yarn eight times and above thirteen colours would "
                    "be refused outright. integrations.etsy.build_payload collapses them, "
                    "preserving order, which fixes the listing and leaves the CIR-to-listing "
                    "mapping still producing the duplicates"),
         "blocks_launch": False},
    ]


def describe() -> dict:
    """The whole contract as data, for the readiness report and the API."""
    return {
        "source": ETSY_OPENAPI_URL,
        "source_version": ETSY_OPENAPI_VERSION,
        "read_on": READ_ON,
        "max_age_days": MAX_AGE_DAYS,
        "required_to_create": list(REQUIRED_TO_CREATE),
        "required_to_activate": list(REQUIRED_TO_ACTIVATE),
        "not_required_for_digital": list(NOT_REQUIRED_FOR_DIGITAL),
        "request_encoding": REQUEST_ENCODING,
        "upload_encoding": UPLOAD_ENCODING,
        "write_scope": WRITE_SCOPE,
        "clauses": [c.to_dict() for c in CLAUSES],
        "gaps": gaps(),
        "note": ("Read from Etsy's own published OpenAPI document. Every sourced clause "
                 "carries the sentence it came from; an inferred clause carries none and "
                 "says so. Etsy changes this document, so the reading date is part of the "
                 "claim."),
    }
