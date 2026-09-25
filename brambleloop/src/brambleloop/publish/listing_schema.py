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

# ---------------------------------------------------------------------------
# The three states, which are not two
#
# Every claim this department makes about the Etsy write path is in exactly one of these, and
# collapsing any two of them is the specific dishonesty this module exists to prevent.
#
# The temptation is real and it is always the same: a green test suite makes LOCALLY_TESTED
# feel like VERIFIED_AGAINST_ETSY. It is not. `tests/fake_etsy.py` is a server built from
# Etsy's own document by the same people who read that document to write the client, so a
# passing test says our client agrees with our reading. If the reading is wrong, the client
# and the fake are wrong together and every test still passes. One successful fake-shop run
# is not evidence of Etsy's behaviour, and no number of them adds up to one.

IMPLEMENTED = "IMPLEMENTED"
"""The code exists and is reachable. Says nothing about whether it works."""

LOCALLY_TESTED = "LOCALLY_TESTED"
"""Exercised end to end against `tests/fake_etsy.py`, including its failure paths.

Establishes that our bytes are parseable by parsers that are not ours, that the media types
match the bytes, and that our own refusals refuse. Establishes nothing about Etsy.
"""

VERIFIED_AGAINST_ETSY = "VERIFIED_AGAINST_ETSY"
"""Observed in a real response from `openapi.etsy.com`, with the observation recorded.

Reachable only through `ETSY_VERIFIED_FACTS` below, and a claim may not be promoted into it
by anything except a live observation being written down.
"""

VERIFICATION_STATES: tuple[str, ...] = (IMPLEMENTED, LOCALLY_TESTED, VERIFIED_AGAINST_ETSY)

# Everything `openapi.etsy.com` has ever told this system, and nothing else. Four facts, all
# from the three unauthenticated pings of 2026-09-25 recorded in research/ETSY_TRANSPORT.md
# section 3.1. They need no OAuth token, they create nothing and they cost CA$0.
#
# A fact enters this tuple when a real Etsy response is observed and the observation is
# written here. Nothing else promotes a claim to VERIFIED_AGAINST_ETSY, and
# `verification_matrix()` refuses to emit that state for a key this tuple does not carry.
ETSY_VERIFIED_FACTS: tuple[dict, ...] = (
    {"key": "etsy_reachable_through_our_transport",
     "fact": ("openapi.etsy.com is reachable from this environment through "
              "integrations.http.UrllibTransport: TLS through the agent proxy, the body "
              "parsed by http._parse, the status classified by core.resilience"),
     "observed": "GET /v3/application/openapi-ping returned a parsed JSON body",
     "on": "2026-09-25"},
    {"key": "api_key_header_format",
     "fact": "x-api-key takes keystring:shared_secret, which is what Credentials builds",
     "observed": ("unauthenticated ping: HTTP 403 \"Invalid API key: should be in the format "
                  "'keystring:shared_secret'.\"; supplying that format changed the error to "
                  "\"API key not found or not active, or incorrect shared secret for API "
                  "key.\", so the format itself was accepted"),
     "on": "2026-09-25"},
    {"key": "bad_key_is_403_not_401",
     "fact": ("Etsy answers a bad API key with 403, not 401. Both classify as permanent, so "
              "retry behaviour is right, but a runbook expecting 401 is wrong"),
     "observed": "HTTP 403 on all three unauthenticated requests",
     "on": "2026-09-25"},
    {"key": "api_key_refused_before_body",
     "fact": ("Etsy refuses on the API key before reading a body, so no unauthenticated "
              "request can ever establish anything about encoding"),
     "observed": ("a JSON body POSTed to a form-only endpoint with an invalid key returned "
                  "the API-key 403 rather than a 415"),
     "on": "2026-09-25"},
)

_VERIFIED_KEYS = frozenset(fact["key"] for fact in ETSY_VERIFIED_FACTS)


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


# Every claim about the Etsy write path, in exactly one of the three states, with the probe
# step that would move it. `claim` keys match `integrations.etsy_probe.TAXONOMY`, so the run's
# report and this table name the same things and cannot describe different worlds.
_MATRIX: tuple[dict, ...] = (
    {"claim": "etsy_reachable_through_our_transport",
     "state": VERIFIED_AGAINST_ETSY, "blocks_launch": False,
     "what": "a request from this system reaches openapi.etsy.com and the reply parses",
     "graduates_by": "already verified; the three unauthenticated pings of 2026-09-25"},
    {"claim": "api_key_header_format",
     "state": VERIFIED_AGAINST_ETSY, "blocks_launch": False,
     "what": "x-api-key is keystring:shared_secret",
     "graduates_by": "already verified; Etsy named the format in its own error"},
    {"claim": "bad_key_is_403_not_401",
     "state": VERIFIED_AGAINST_ETSY, "blocks_launch": False,
     "what": "a refused key is a 403",
     "graduates_by": "already verified"},
    {"claim": "api_key_refused_before_body",
     "state": VERIFIED_AGAINST_ETSY, "blocks_launch": False,
     "what": "Etsy checks the key before the body, so encoding is unverifiable unauthenticated",
     "graduates_by": "already verified; it is why every row below needs credentials"},
    {"claim": "form_encoded_create",
     "state": LOCALLY_TESTED, "blocks_launch": True,
     "what": "Etsy accepts createDraftListing as application/x-www-form-urlencoded",
     "graduates_by": "probe step 2 (create_draft) returning 201 with a listing_id"},
    {"claim": "multipart_image_upload",
     "state": LOCALLY_TESTED, "blocks_launch": True,
     "what": "Etsy reads the image binary from a multipart part named `image`",
     "graduates_by": ("probe step 3 (upload_image) returning 201 with a listing_image_id "
                      "AND step 6 reading one image back from Etsy")},
    {"claim": "image_minimum_acceptable",
     "state": IMPLEMENTED, "blocks_launch": False,
     "what": ("a 1x1 PNG is an acceptable listing image. Etsy's image rules are on "
              "help.etsy.com, which refuses automated readers, so this is not even a reading"),
     "graduates_by": ("probe step 3 accepting the generated pixel; a refusal is a finding "
                      "about the fixture, not about the transport")},
    {"claim": "array_encoding_tags",
     "state": LOCALLY_TESTED, "blocks_launch": True,
     "what": ("tags are comma-joined (`tags=a,b`) rather than repeated keys. Genuinely "
              "ambiguous: Etsy's description says 'a comma-separated list' and the OpenAPI "
              "default for an un-encoded form array is repeated keys, and both are Etsy's "
              "own document"),
     "graduates_by": ("probe step 6 comparing the tags Etsy holds against the tags sent. A "
                      "201 settles nothing: the wrong reading is stored as one tag "
                      "containing a comma, with no error anywhere")},
    {"claim": "oauth_token_endpoint",
     "state": IMPLEMENTED, "blocks_launch": True,
     "what": ("which host serves the token endpoint, and that either grant works. Etsy's "
              "authentication page says api.etsy.com and Etsy's OpenAPI document says "
              "openapi.etsy.com"),
     "graduates_by": ("the owner's browser authorisation, then the first refresh: probe "
                      "step 1 cannot run without one")},
    {"claim": "taxonomy_patterns_id",
     "state": IMPLEMENTED, "blocks_launch": False,
     "what": "integrations.etsy.TAXONOMY_PATTERNS = 66 is the patterns node",
     "graduates_by": ("probe step 6 reading the node out of getSellerTaxonomyNodes and "
                      "comparing the listing's taxonomy_id on Etsy. A wrong id is a listing "
                      "in the wrong category, not an error, so a 201 proves nothing")},
    {"claim": "taxonomy_required_properties",
     "state": IMPLEMENTED, "blocks_launch": False,
     "what": "whether the patterns node requires a listing property",
     "graduates_by": ("probe step 6 reading getPropertiesByTaxonomyId. If one is required, "
                      "every create is refused with a property id in the message and this "
                      "becomes a launch blocker with a build task attached")},
    {"claim": "delete_removes_draft",
     "state": LOCALLY_TESTED, "blocks_launch": False,
     "what": "deleteListing really removes a draft rather than accepting and keeping it",
     "graduates_by": ("probe step 8 (verify_cleanup) reading the listing back and getting "
                      "404. The 204 in step 7 is Etsy accepting the request, which is a "
                      "different claim")},
)


def verification_matrix() -> list[dict]:
    """Every Etsy claim and which of the three states it is in. The honest status, as data.

    Refuses to emit VERIFIED_AGAINST_ETSY for a claim that `ETSY_VERIFIED_FACTS` does not
    carry an observation for. That is the enforcement, not a convention: promoting a claim
    means writing down what Etsy actually said, and a row that cannot name an observation
    cannot be green.
    """
    out: list[dict] = []
    facts = {fact["key"]: fact for fact in ETSY_VERIFIED_FACTS}
    for row in _MATRIX:
        if row["state"] not in VERIFICATION_STATES:
            raise SchemaRefused(f"{row['claim']}: {row['state']!r} is not one of "
                                f"{list(VERIFICATION_STATES)}")
        if row["state"] == VERIFIED_AGAINST_ETSY and row["claim"] not in _VERIFIED_KEYS:
            raise SchemaRefused(
                f"{row['claim']} claims to be verified against Etsy and no observation of "
                f"Etsy saying so is recorded in ETSY_VERIFIED_FACTS. A claim cannot be "
                f"promoted by being believed.")
        entry = dict(row)
        fact = facts.get(row["claim"])
        entry["evidence"] = fact["observed"] if fact else (
            "tests/fake_etsy.py, which is our reading of Etsy's document, not Etsy"
            if row["state"] == LOCALLY_TESTED else "none; the code exists and has not run")
        entry["observed_on"] = fact["on"] if fact else None
        out.append(entry)
    return out


def verification_summary() -> dict:
    """How many claims are in each state. The number that must not be allowed to drift."""
    rows = verification_matrix()
    return {state: sum(1 for r in rows if r["state"] == state)
            for state in VERIFICATION_STATES}


def gaps() -> list[dict]:
    """The distance between Etsy's contract and what this system produces today.

    Each entry names the clause it rests on, so a gap that stops being true when Etsy changes
    its document stops being true visibly. `blocks_launch` is the only field that matters on
    the day the phase moves, and it is set from what would actually fail, not from severity.

    Every entry also carries `verification`: one of IMPLEMENTED, LOCALLY_TESTED or
    VERIFIED_AGAINST_ETSY, stamped from `verification_matrix()` rather than written here, so
    the gap list and the matrix cannot say different things about the same claim. A gap row
    whose `claim` is unknown to the matrix is refused: a gap nobody can state the evidential
    status of is a gap that gets closed on a feeling.
    """
    return _stamp([
        # 2026-09-25: the image-upload and JSON-body gaps were closed in code. They are not
        # deleted, because a gap between the contract and what this system *produces* was
        # replaced by a gap between what this system produces and what Etsy has confirmed --
        # and on launch day the second one fails just as loudly. What changed is the reason,
        # and the reason is now an owner action rather than a build task.
        {"gap": "the listing-image upload has never been confirmed by Etsy",
         "claim": "multipart_image_upload",
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
         "claim": "form_encoded_create",
         "clause": "form_encoded_request",
         "detail": ("integrations.http.UrllibTransport now sets the Content-Type from the "
                    "body channel the caller used, and createDraftListing and updateListing "
                    "use the form channel. It sent application/json to both until "
                    "2026-09-25. Etsy refuses a request on its API key before it reads a "
                    "body, so no unauthenticated call can confirm the encoding and only the "
                    "owner's OAuth grant makes that possible"),
         "blocks_launch": True},
        {"gap": "nothing has ever authenticated against Etsy",
         "claim": "oauth_token_endpoint",
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
         "claim": "taxonomy_patterns_id",
         "clause": "taxonomy_id_unverified",
         "detail": ("integrations.etsy.TAXONOMY_PATTERNS is 66 with the comment "
                    "'craft_supplies_and_tools.patterns'. Confirming it needs one "
                    "authenticated GET to getSellerTaxonomyNodes, which needs a keystring "
                    "this environment does not have and this phase would not use"),
         "blocks_launch": False},
        {"gap": "required listing properties for the chosen taxonomy are unknown",
         "claim": "taxonomy_required_properties",
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
        # Two gaps the predecessor's list did not carry, because both look closed from inside
        # this repository and neither is. They are the two claims most likely to pass every
        # local check and fail on the real shop, and the first of them fails silently.
        {"gap": "how an array is form-encoded has never been settled by Etsy",
         "clause": "form_encoded_request",
         "claim": "array_encoding_tags",
         "detail": ("integrations.etsy.ARRAY_ENCODING is 'comma', so tags go out as "
                    "`tags=a,b`. Etsy's tags description says 'a comma-separated list' and "
                    "the OpenAPI default for an un-encoded form array is repeated keys "
                    "(`tags=a&tags=b`); both readings are Etsy's own document, and this "
                    "system had to pick one. The dangerous outcome is not a 400: if the "
                    "reading is wrong Etsy returns 201 and stores a single tag containing a "
                    "comma, which only the read-back comparison can see. Both settings are "
                    "exercised locally; one real create settles it and one constant moves"),
         "blocks_launch": True},
        {"gap": "nothing has confirmed that deleting a draft removes it",
         "clause": "write_scope",
         "claim": "delete_removes_draft",
         "detail": ("integrations.etsy.EtsyClient.delete_listing reads the listing's state "
                    "back and refuses unless it is the draft the caller expected, then sends "
                    "DELETE. Etsy's document lists DRAFT as a deletable state and says "
                    "nothing about what the listing becomes, so a 204 is Etsy accepting the "
                    "request and not Etsy confirming the listing is gone. The run therefore "
                    "reads the listing back afterwards and expects a 404. Until it has, "
                    "every shadow write is a write this system cannot prove it can undo"),
         "blocks_launch": False},
    ])


def _stamp(rows: list[dict]) -> list[dict]:
    """Attach each gap's verification state from the matrix, refusing an unknown claim."""
    states = {row["claim"]: row["state"] for row in verification_matrix()}
    for row in rows:
        claim = row.get("claim")
        if claim is None:
            # A gap about this system's own internals rather than about Etsy's behaviour --
            # the duplicate-materials one. IMPLEMENTED is the honest state: the code exists
            # and Etsy has said nothing about it, which is true of everything here.
            row["verification"] = IMPLEMENTED
            continue
        if claim not in states:
            raise SchemaRefused(
                f"gap {row['gap']!r} names claim {claim!r}, which the verification matrix "
                f"does not carry. A gap with no stated evidential status is one somebody "
                f"closes because it feels closed.")
        row["verification"] = states[claim]
    return rows


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
        "verification_states": list(VERIFICATION_STATES),
        "verification_matrix": verification_matrix(),
        "verification_summary": verification_summary(),
        "verified_against_etsy": [dict(f) for f in ETSY_VERIFIED_FACTS],
        "note": ("Read from Etsy's own published OpenAPI document. Every sourced clause "
                 "carries the sentence it came from; an inferred clause carries none and "
                 "says so. Etsy changes this document, so the reading date is part of the "
                 "claim."),
    }
