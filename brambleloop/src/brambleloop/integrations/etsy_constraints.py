"""Etsy's store and listing constraints, read from Etsy's own documents on 2026-10-06.

This is the one place the rest of the system reads Etsy's image sizes, field limits, file
limits and the taxonomy/attribute call order from. Lane B (store preview), lane G (SEO) and
the publish path consume it; none of them should restate a number this module carries.

**Where the numbers came from.** Two of Etsy's own documents, each fetched on `RETRIEVED_ON`:

- Etsy's Help Center articles, read as JSON through the Help Center's public article API
  (`https://help.etsy.com/api/v2/help_center/en-us/articles/<id>.json`). The human HTML
  pages answer automated readers with HTTP 403 -- which is why earlier modules record the help
  centre as unreadable -- but the article API returns the same article body, with Etsy's own
  `edited_at` date. Every Help Center figure here carries the article id, its `edited_at`,
  and the sentence it came from.
- Etsy's published Open API v3 document (`publish.listing_schema.ETSY_OPENAPI_URL`).

**Three bases, never collapsed.**

- `VERIFIED_HELP` / `VERIFIED_OPENAPI`: a sentence in an Etsy document says it, quoted here.
  That is evidence of what Etsy *publishes*; it is not an observation of Etsy enforcing it on
  this shop (no authenticated call has ever been made -- see `listing_schema`).
- `UNVERIFIED`: nothing Etsy publishes was found that states it. The value, if any, is this
  repository's assumption or a third-party blog's, and is labelled as such. Third-party "Etsy
  size guides" were consulted and are **not** used as evidence: several disagree with Etsy's
  own article (e.g. "3360 x 840" big banners, which no Etsy document states).
- `UNKNOWN`: no value at all. Never rendered as a number.

Etsy changes these articles; `MAX_AGE_DAYS` makes a reading go stale visibly.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date
from typing import Any

RETRIEVED_ON = "2026-10-06"
MAX_AGE_DAYS = 30

VERIFIED_HELP = "VERIFIED_HELP_CENTER"
VERIFIED_OPENAPI = "VERIFIED_OPENAPI"
UNVERIFIED = "UNVERIFIED"
UNKNOWN = "UNKNOWN"
BASES = (VERIFIED_HELP, VERIFIED_OPENAPI, UNVERIFIED, UNKNOWN)
VERIFIED_BASES = (VERIFIED_HELP, VERIFIED_OPENAPI)

HELP_API = "https://help.etsy.com/api/v2/help_center/en-us/articles/{id}.json"
OPENAPI_URL = "https://www.etsy.com/openapi/generated/oas/3.0.0.json"

MB = 1024 * 1024


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    edited_at: str          # Etsy's own last-edited timestamp for the article (UTC)
    api_url: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "url": self.url,
                "api_url": self.api_url, "edited_at": self.edited_at,
                "retrieved_on": RETRIEVED_ON}


def _help(aid: str, slug: str, title: str, edited: str) -> Source:
    return Source(aid, title, f"https://help.etsy.com/hc/en-us/articles/{aid}-{slug}",
                  edited, HELP_API.format(id=aid))


SOURCES: dict[str, Source] = {s.id: s for s in (
    _help("115015663347", "Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop",
          "Requirements and Best Practices for Images in Your Etsy Shop",
          "2026-05-04T19:20:43Z"),
    _help("115015663247", "How-to-Customize-Your-Shop-s-Appearance",
          "How to Customize Your Shop's Appearance", "2026-05-05T14:06:33Z"),
    _help("115015628487", "How-to-Edit-Your-Shop-s-About-Section",
          "How to Edit Your Shop's About Section", "2026-05-04T16:00:09Z"),
    _help("115015651948", "Your-Bio-and-Profile-Picture", "Your Bio and Profile Picture",
          "2025-07-15T20:01:41Z"),
    _help("360000343708", "How-to-Add-a-Shop-Announcement-and-Shop-Title",
          "How to Add a Shop Announcement and Shop Title", "2025-06-12T14:37:51Z"),
    _help("360000345048", "How-to-Create-and-Manage-Shop-Sections",
          "How to Create and Manage Shop Sections", "2024-02-15T16:56:10Z"),
    _help("115015710568", "How-to-Change-Your-Shop-Name", "How to Change Your Shop Name",
          "2026-05-04T19:15:05Z"),
    _help("115015628707", "How-to-Create-a-Listing", "How to Create a Listing",
          "2026-06-29T20:48:25Z"),
    _help("360000336307", "How-to-Use-Tags-to-Get-Found-in-Search",
          "How to Use Tags to Get Found in Search", "2026-04-21T15:22:37Z"),
    _help("115014502508", "How-to-Use-Attributes-When-Listing-an-Item",
          "How to Use Attributes When Listing an Item", "2026-09-16T20:47:43Z"),
    _help("4406604492823", "How-to-Add-a-Text-Alternative-to-Your-Listing-Images",
          "How to Add a Text Alternative to Your Listing Images", "2024-12-10T16:55:55Z"),
    _help("360016260113", "How-to-Edit-Your-Listing-Photos", "How to Edit Your Listing Photos",
          "2026-06-29T20:40:47Z"),
    _help("115015628347", "How-to-Manage-Your-Digital-Listings",
          "How to Manage Your Digital Listings", "2025-03-21T20:00:21Z"),
    _help("25869947521175", "How-to-Use-the-Etsy-Search-Visibility-Page",
          "How to Use the Etsy Search Visibility Page", "2026-05-04T19:26:01Z"),
    _help("360024112614", "What-Can-I-Sell-on-Etsy", "What Can I Sell on Etsy?",
          "2025-09-17T18:36:53Z"),
    _help("360000336867", "How-to-Display-Team-Members-in-your-Shop-About-Section",
          "How to Display Team Members in your Shop About Section", "2026-07-30T14:44:17Z"),
    _help("360000337107", "How-to-Add-or-Edit-Your-Post-Purchase-Message-to-Buyers",
          "How to Add or Edit Your Post-Purchase Message to Buyers", "2025-12-15T20:09:13Z"),
    _help("115014372467", "How-to-Set-Up-Your-Shop-Policies", "How to Set Up Your Shop Policies",
          "2025-04-21T19:35:24Z"),
    _help("43476182453399", "How-Printed-Items-From-Digital-Purchases-Work-for-Sellers",
          "How Printed Items From Digital Purchases Work for Sellers", "2026-09-24T13:57:50Z"),
    _help("115015672808", "How-to-Open-an-Etsy-Shop", "How to Open an Etsy Shop",
          "2026-05-04T16:17:02Z"),
    Source("openapi", "Etsy Open API v3 (OpenAPI 3.0.0 document)", OPENAPI_URL,
           "unversioned; read 2026-10-06"),
)}


@dataclass(frozen=True)
class Constraint:
    """One Etsy requirement or recommendation, with its evidence.

    `value` is None exactly when the basis is UNKNOWN. A VERIFIED constraint must quote.
    `enforced` says what Etsy does with a breach, from the quoted sentence: "required" (Etsy
    refuses), "recommended" (Etsy advises; publishing still works), "display" (how Etsy shows
    it). It decides whether a breach is a failure or a warning here.
    """

    key: str
    surface: str
    what: str
    value: Any
    basis: str
    source: str = ""
    quote: str = ""
    enforced: str = "required"
    note: str = ""

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise ValueError(f"{self.key}: basis {self.basis!r} not in {BASES}")
        if self.basis == UNKNOWN and self.value is not None:
            raise ValueError(f"{self.key}: an UNKNOWN constraint may not carry a value")
        if self.basis in VERIFIED_BASES:
            if not self.quote.strip():
                raise ValueError(f"{self.key}: verified with no quoted sentence")
            if self.source not in SOURCES:
                raise ValueError(f"{self.key}: source {self.source!r} is not recorded")
        if self.enforced not in ("required", "recommended", "display"):
            raise ValueError(f"{self.key}: enforced={self.enforced!r}")

    @property
    def verified(self) -> bool:
        return self.basis in VERIFIED_BASES

    def to_dict(self) -> dict:
        src = SOURCES.get(self.source)
        return {"key": self.key, "surface": self.surface, "what": self.what,
                "value": list(self.value) if isinstance(self.value, tuple) else self.value,
                "basis": self.basis, "enforced": self.enforced, "quote": self.quote,
                "note": self.note,
                "source": src.to_dict() if src else None}


H, O = VERIFIED_HELP, VERIFIED_OPENAPI
A_IMG, A_ABOUT, A_PROFILE, A_APPEAR = ("115015663347", "115015628487", "115015651948",
                                       "115015663247")

_C = (
    # ---------------------------------------------------------------- shop identity images
    Constraint("logo_min_px", "shop_logo", "shop logo (icon) minimum size, px (w, h)",
               (500, 500), H, A_ABOUT,
               "Your logo must be a .jpg, .png, or .gif file, smaller than 10MB, and at least "
               "500px by 500px."),
    Constraint("logo_recommended_px", "shop_logo", "shop logo recommended size, px",
               (500, 500), H, A_IMG, "The recommended size for logos is 500 x 500px.",
               "recommended"),
    Constraint("logo_max_bytes", "shop_logo", "shop logo file size, bytes (exclusive)",
               10 * MB, H, A_ABOUT, "smaller than 10MB"),
    Constraint("logo_formats", "shop_logo", "shop logo file types",
               ("jpg", "png", "gif"), H, A_ABOUT, "Your logo must be a .jpg, .png, or .gif file"),
    Constraint("logo_crop", "shop_logo", "the logo is cropped square in the editor",
               "square crop tool", H, A_APPEAR,
               "Select the square (crop) icon to crop your image.", "display",
               note=("Whether Etsy then masks the logo as a circle on any surface is NOT "
                     "stated by Etsy (third-party guides claim it). Design the mark to "
                     "survive a circular mask anyway; that is a design margin, not a fact.")),
    Constraint("logo_affects_search", "shop_logo", "a missing logo may lower search visibility",
               True, H, "25869947521175",
               "Your shop should have a logo, which helps the buyer understand who you are. If "
               "your shop is not complete, your listings' search visibility may be impacted.",
               "recommended"),
    Constraint("profile_min_px", "profile_photo",
               "account public-profile picture minimum size, px", (400, 400), H, A_PROFILE,
               "The image you use must be at least 400 x 400 pixels in size and smaller than "
               "10MB."),
    Constraint("profile_recommended_px", "profile_photo", "profile photo recommended size, px",
               (400, 400), H, A_IMG, "The recommended size for profile photos is 400 x 400px.",
               "recommended"),
    Constraint("profile_max_bytes", "profile_photo", "profile photo size, bytes (exclusive)",
               10 * MB, H, A_PROFILE, "smaller than 10MB"),
    Constraint("profile_square", "profile_photo", "profile photo must be square",
               1.0, H, A_PROFILE, "Make sure your original image is a square, or your profile "
                             "picture will be distorted on the site."),
    Constraint("profile_formats", "profile_photo", "profile photo file types",
               ("jpg", "png", "gif"), H, A_PROFILE,
               "Profile pictures should be a .jpg, .png, or .gif file only."),
    Constraint("profile_is_account_level", "profile_photo",
               "the profile picture belongs to the signed-in Etsy *account* (Your account > "
               "Account settings > Public profile), not to the shop",
               "account", H, A_PROFILE,
               "On Etsy.com, go to Your account. Go to Account settings. Go to Public profile.",
               "display",
               note=("Truth consequence: this is the account holder's own picture. Putting an "
                     "AI persona there presents the persona as the account holder. See "
                     "ETSY_SETTINGS_CHECKLIST.md item B3.")),
    Constraint("big_banner_min_px", "big_banner", "big shop banner minimum size, px",
               (1200, 300), H, A_IMG,
               "The minimum required size for big shop banners is 1200 x 300px."),
    Constraint("big_banner_recommended_px", "big_banner", "big shop banner recommended size, px",
               (1600, 400), H, A_IMG, "The recommended size is 1600 x 400px.", "recommended"),
    Constraint("mini_banner_min_px", "mini_banner", "mini shop banner minimum size, px",
               (1200, 160), H, A_IMG,
               "The minimum required size for mini shop banners is 1200 x 160px."),
    Constraint("mini_banner_recommended_px", "mini_banner",
               "mini shop banner recommended size, px", (1600, 213), H, A_IMG,
               "The recommended size is 1600 x 213px.", "recommended"),
    Constraint("banner_mobile_crop", "big_banner",
               "how much of the banner a phone shows", None, UNKNOWN,
               note=("Etsy says only that the banner 'appears when shoppers view your shop on "
                     "the standard view of the website as well as on mobile devices' and that "
                     "'Image sizes are optimized for mobile displays'. No crop geometry or "
                     "safe zone is published. Third-party 'safe zones' (e.g. 1200x300 central) "
                     "are not evidence. Keep text/marks centred with generous margins and "
                     "check the real crop in the Etsy app after upload (checklist B2).")),
    Constraint("receipt_banner_min_px", "receipt_banner", "order receipt banner minimum, px",
               (760, 100), H, A_IMG,
               "The minimum required size for order receipt banner photos is 760 x 100px."),
    Constraint("carousel_collage_etsy_plus", "big_banner",
               "carousel and collage banners need Etsy Plus (paid)", True, H, A_IMG,
               "The carousel and collage banners are only available to sellers subscribed to "
               "Etsy Plus.", "display"),
    Constraint("about_photos_max", "about", "About featured photos, count", 5, H, A_ABOUT,
               "Upload up to 5 photos with captions from this section."),
    Constraint("about_photo_max_bytes", "about", "About featured photo size, bytes", 2 * MB, H,
               A_ABOUT, "Images can be .jpg, .png, or .gif files up to 2MB."),
    Constraint("about_photo_display_px", "about", "About photos are cropped to display at, px",
               (760, 468), H, A_ABOUT,
               "your photos will be cropped to display at 760 x 468 pixels.", "display"),
    Constraint("about_video_max_bytes", "about", "shop featured video, bytes", 300 * MB, H,
               A_ABOUT, "Your video must be an MP4, MOV, AVI, MPEG, or M4V file up to 300 MB."),
    # --------------------------------------------------------------------- shop text
    Constraint("shop_title_max_chars", "shop_title", "shop title (tagline) characters", 55, H,
               "360000343708", "Shop titles can be up to 55 characters long."),
    Constraint("shop_name_chars", "shop_name", "shop name length (min, max) characters",
               (4, 20), H, "115015672808", "4-20 characters in length",
               note="Also: 'they can't have spaces or punctuation' (article 115015710568)."),
    Constraint("shop_name_changes", "shop_name", "self-service shop-name changes once open",
               5, H, "115015710568",
               "Once your shop is open, you can change your shop name up to 5 times"),
    Constraint("about_max_chars", "about", "About your shop characters", 5000, H, A_ABOUT,
               "Share the story behind your business in 5,000 characters or less."),
    Constraint("announcement_max_chars", "announcement", "shop announcement characters", None,
               UNKNOWN, note=("Etsy says only 'Keep your announcement short and sweet' "
                              "(360000343708). No number is published; the repo's 160 is an "
                              "internal style cap, not Etsy's limit.")),
    Constraint("announcement_needs_open_shop", "announcement",
               "announcement and shop title cannot be set before the shop is open", True, H,
               "360000343708", "If your shop isn't open to the public yet, you won't be able "
                               "to add an announcement until you open your shop.", "display"),
    Constraint("sections_max", "sections", "custom shop sections, count", 20, H, "360000345048",
               "You can have up to 20 custom sections, as well as the default All items "
               "section that is in every shop."),
    Constraint("section_name_max_chars", "sections", "shop section name characters", 24, H,
               "360000345048", "A section name can be up to 24 characters."),
    Constraint("empty_sections_hidden", "sections", "empty sections are not shown", True, H,
               "360000345048", "Sections that don't have any item listings won't appear on "
                               "your public shop page.", "display"),
    Constraint("featured_listings", "shop_home", "featured listings shown on shop home", 4, H,
               A_APPEAR, "Featuring items is a way to showcase 4 listings", "display"),
    Constraint("policy_additional_eu_only", "policies",
               "updateShop.policy_additional may only be set by EU-located shops", True, O,
               "openapi", "the policy_additional field should only be set for shops located in "
                          "the EU. Passing a value for this field for shops outside of the EU, "
                          "will result in an error.",
               note="Brambleloop is Canadian: policy_additional must not be sent."),
    Constraint("digital_sale_message_max_chars", "policies",
               "Message to Buyers for Digital Items characters", None, UNKNOWN,
               note="Field exists (updateShop.digital_sale_message; help 360000337107); no "
                    "length published."),
    Constraint("faq_limits", "policies", "FAQ entries / characters", None, UNKNOWN,
               note="Etsy's policies article suggests putting licensing info in FAQs but "
                    "publishes no FAQ limits."),
    # ---------------------------------------------------------------------- listing text
    Constraint("title_max_chars", "listing", "listing title characters", 140, H, "115015628707",
               "A listing's title can be up to 140 characters long."),
    Constraint("title_words_advice", "listing", "title word-count guidance", 15, H,
               "115015628707", "Consider using less than 15 words", "recommended"),
    Constraint("tags_max", "listing", "tags per listing", 13, H, "360000336307",
               "You can use up to 13 tags per listing."),
    Constraint("tag_max_chars", "listing", "characters per tag", 20, H, "360000336307",
               "Each tag can contain up to 20 characters."),
    Constraint("tag_no_leading_punct", "listing", "a tag may not start with ' or -", "'-", H,
               "360000336307", "You're able to use ' and - within words and phrases, but "
                               "cannot start your tag with these characters."),
    Constraint("materials_max", "listing", "materials per listing", None, UNKNOWN,
               note=("13 is asserted in integrations.etsy.MATERIALS_MAX. Neither the Open API "
                     "document nor any help article read on 2026-10-06 states a materials "
                     "count; materials are now also an attribute (115014502508).")),
    Constraint("description_max_chars", "listing", "listing description characters", None,
               UNKNOWN, note=("integrations.etsy.DESCRIPTION_MAX = 102400 has no Etsy source "
                              "on file; the Open API description field states no maximum.")),
    Constraint("styles_max", "listing", "styles per listing", 2, O, "openapi",
               "the listing may have up to two styles."),
    Constraint("alt_text_max_chars", "listing_image", "image alt text characters (API)", 500, O,
               "openapi", "Alt text for the listing image. Max length 500 characters."),
    Constraint("alt_text_advice_chars", "listing_image", "alt text guidance, characters", 250,
               H, "4406604492823", "Keep the description concise: up to 250 characters.",
               "recommended"),
    # -------------------------------------------------------------------- listing images
    Constraint("listing_images_max", "listing_image", "photos per listing", 20, H,
               "115015628707", "You can add up to 20 photos and 2 videos that are 5-15 seconds "
                               "in length to each listing."),
    Constraint("listing_videos_max", "listing_image", "videos per listing (5-15 s each)", 2, H,
               "115015628707", "You can add up to 20 photos and 2 videos that are 5-15 seconds "
                               "in length to each listing."),
    Constraint("listing_image_recommended_px", "listing_image",
               "listing photo recommended min width AND height, px", 2000, H, A_IMG,
               "We recommend your listing photos have a width and height of at least 2000 "
               "pixels or more.", "recommended",
               note="Etsy's form warns below 2000 px wide but still publishes (115015628707)."),
    Constraint("first_image_min_px", "listing_image",
               "first listing photo min width and height to avoid lower search placement, px",
               635, H, A_IMG, "Your first listing photo should have a width and height of at "
                            "least 635 pixels to avoid showing up lower in searches.",
               "recommended"),
    Constraint("first_image_orientation", "listing_image",
               "first photo should be landscape or square", ("landscape", "square"), H, A_IMG,
               "The first photo in a listing should be horizontal (landscape) or square.",
               "recommended",
               note=("The same article also says 'Avoid square crops. Upload horizontal or "
                     "landscape images.' Etsy is internally inconsistent; landscape satisfies "
                     "both sentences.")),
    Constraint("thumbnail_crops", "listing_image",
               "thumbnails are cut from the first photo in three shapes",
               ("square", "portrait", "landscape"), H, A_IMG,
               "Make sure your thumbnail images have enough of a border that they can be "
               "cropped to square, portrait, and landscape thumbnails without losing some of "
               "the product.", "display",
               note="The exact aspect ratios of the three crops are NOT published (UNKNOWN)."),
    Constraint("primary_photo_single_product", "listing_image",
               "primary photo: a single finished product, no collage", True, H,
               "25869947521175",
               "The listing's primary photo is a singular image of a finished product (no "
               "collaged or stitched together images)", "recommended"),
    Constraint("image_formats", "listing_image", "image file types Etsy supports",
               ("jpg", "gif", "png", "svg", "heic"), H, A_IMG,
               "All images in your shop should be one of these file types: .jpg, .gif, .png, "
               ".svg, or .heic. These are the only image file types Etsy supports."),
    Constraint("no_animation_no_transparency", "listing_image",
               "animated GIF and transparent PNG unsupported; transparency renders black",
               True, H, A_IMG,
               "Animated .gif files & transparent .png files are not supported. If a file "
               "contains transparency, the transparent parts of the image will appear black on "
               "Etsy."),
    Constraint("image_upload_bytes_advice", "listing_image",
               "images over 1MB may not finish uploading", 1 * MB, H, A_IMG,
               "Images larger than 1MB in file size may not finish uploading, especially on a "
               "slower internet connection.", "recommended",
               note="Applies to the browser upload; whether the API enforces any size is "
                    "UNKNOWN."),
    Constraint("color_profile", "listing_image", "Etsy converts images to sRGB", "sRGB", H, A_IMG,
               "We convert images to use the sRGB color profile", "display"),
    Constraint("full_image_max_px", "listing_image",
               "url_fullxfull is served at up to this many px per dimension", 3000, O,
               "openapi", "The url string for the full-size image, up to 3000 pixels in each "
                          "dimension", "display"),
    Constraint("image_size_async", "listing_image",
               "size/colour fields may be null straight after upload", True, O, "openapi",
               "When uploading a new image, data such as colors and size may return as null "
               "values due to asynchronous processing of the image. Use getListingImage "
               "endpoint to fetch these values.", "display"),
    # -------------------------------------------------------------------- digital files
    Constraint("digital_files_max", "digital_file", "files per digital listing", 5, H,
               "115015628347", "You can upload up to five digital files."),
    Constraint("digital_file_max_bytes", "digital_file", "size per digital file, bytes",
               20 * MB, H, "115015628347", "The maximum size for each file is 20MB."),
    Constraint("digital_filename_max_chars", "digital_file", "digital file name characters",
               70, H, "115015628347", "File names are limited to 70 alphanumeric characters, "
                                      "periods, underscores, or hyphens."),
    Constraint("digital_filename_immutable", "digital_file",
               "a digital file's name cannot be edited after upload", True, H, "115015628347",
               "We don't have a way of editing the name after uploading, so be sure to name "
               "your files appropriately first.", "display"),
    Constraint("digital_file_types", "digital_file", "digital file types",
               ("bmp", "doc", "gif", "jpeg", "jpg", "mobi", "mov", "mp3", "mpeg", "pdf", "png",
                "psp", "rtf", "stl", "txt", "zip", "epub", "ibook"), H, "115015628347",
               "Supported file types .bmp .doc .gif .jpeg .jpg .mobi .mov .mp3 .mpeg .pdf .png "
               ".psp .rtf .stl .txt .zip .ePUB .iBook"),
    Constraint("instant_digital_needs_file", "digital_file",
               "an instant digital listing cannot be published or saved without a file", True,
               H, "115015628347", "You will be unable to publish or save an instant digital "
                                  "listing if there is no file attached to it."),
    Constraint("digital_no_variations", "digital_file", "digital listings take no variations",
               True, H, "115015628347", "No, you can't offer variations for digital items."),
    # ------------------------------------------------------------- disclosure / identity
    Constraint("ai_disclosure", "disclosure", "seller-prompted AI creations must disclose AI",
               True, H, "360024112614", "Seller-prompted AI creations must disclose the use of "
                                        "AI."),
    Constraint("owner_role_truth", "about",
               "a shop-team 'Owner' must be a real responsible owner who makes/designs",
               True, H, "360000336867",
               "Owner: You and anyone else you consider to be an owner of your Etsy shop. The "
               "owner must also be making, designing, hand picking, or sourcing qualifying "
               "items in line with Etsy's Creativity Standards. Under Etsy's Terms of Use, the "
               "owner is responsible for any activity on the account."),
)

CONSTRAINTS: dict[str, Constraint] = {c.key: c for c in _C}
if len(CONSTRAINTS) != len(_C):      # pragma: no cover - a duplicate key is a typo
    raise ValueError("duplicate constraint key")


def value(key: str) -> Any:
    """The constraint's value; raises for UNKNOWN so nobody renders a missing number."""
    c = CONSTRAINTS[key]
    if c.basis == UNKNOWN:
        raise LookupError(f"{key}: Etsy publishes no value ({c.note})")
    return c.value


def is_stale(today: date | None = None) -> bool:
    today = today or date.today()
    return (today - date.fromisoformat(RETRIEVED_ON)).days > MAX_AGE_DAYS


# ---------------------------------------------------------------------------
# The taxonomy / attribute API flow, in call order. Every step is an Open API operation;
# `auth` is what the call needs (api_key alone or an OAuth scope).

TAXONOMY_FLOW: tuple[dict, ...] = (
    {"step": 1, "operation": "getSellerTaxonomyNodes", "auth": "api_key",
     "purpose": "read the full seller taxonomy tree; choose the node for a crochet pattern",
     "repo": "integrations.etsy_taxonomy.refresh (gated on a recorded etsy.probe)"},
    {"step": 2, "operation": "getPropertiesByTaxonomyId", "auth": "api_key",
     "purpose": "read that node's properties: is_required, supports_attributes, "
                "possible_values, scales, max_values_allowed",
     "repo": "integrations.etsy_taxonomy.refresh; EtsyClient.get_taxonomy_properties"},
    {"step": 3, "operation": "createDraftListing", "auth": "listings_w",
     "purpose": "create the draft with taxonomy_id and type=download",
     "repo": "EtsyClient.create_draft"},
    {"step": 4, "operation": "updateListingProperty", "auth": "listings_w",
     "purpose": "set each attribute: value_ids + values (+ scale_id where the property has "
                "scales). Required properties must be set before activation",
     "repo": "EtsyClient.set_listing_property"},
    {"step": 5, "operation": "uploadListingFile", "auth": "listings_w",
     "purpose": "attach the PDF (<=5 files, <=20MB each, name <=70 chars [A-Za-z0-9._-])",
     "repo": "EtsyClient.attach_file"},
    {"step": 6, "operation": "uploadListingImage", "auth": "listings_w",
     "purpose": "upload images (multipart part `image`, rank, alt_text <=500)",
     "repo": "EtsyClient.upload_image"},
    {"step": 7, "operation": "getListing / getListingProperties / getAllListingFiles / "
                             "getListingImages", "auth": "listings_r",
     "purpose": "read back everything sent; image width/height may be null until Etsy's "
                "asynchronous processing finishes",
     "repo": "runtime.etsy_ops.read_back; integrations.etsy_verify"},
    {"step": 8, "operation": "updateListing state=active", "auth": "listings_w",
     "purpose": "activation (GATED: owner authority; requires an image and a file)",
     "repo": "EtsyClient.activate"},
)

TAXONOMY_ID_STATUS = {
    "value_in_code": "integrations.etsy.TAXONOMY_PATTERNS = 66",
    "basis": UNVERIFIED,
    "why": ("getSellerTaxonomyNodes needs an Etsy keystring this environment does not hold; "
            "the id has never been read back. Gated on the owner's Etsy re-authorisation."),
}


# ---------------------------------------------------------------------------
# Checks. Each finding is {"code", "severity", "detail", "constraint"}; severity is "fail"
# (Etsy refuses / a verified requirement is broken), "warn" (a verified recommendation is
# missed) or "unverified" (nothing verified to check against).


def _finding(code: str, key: str, detail: str, *, severity: str | None = None) -> dict:
    c = CONSTRAINTS[key]
    sev = severity or ("fail" if c.enforced == "required" and c.verified else
                       "warn" if c.verified else "unverified")
    return {"code": code, "severity": sev, "detail": detail, "constraint": key,
            "basis": c.basis, "source": (SOURCES[c.source].url if c.source in SOURCES
                                         else None)}


def image_info(data: bytes) -> dict:
    """Format, size and transparency facts read from the bytes themselves (PNG/JPEG/GIF).

    Header parsing only, no decoder, so it runs anywhere. `has_alpha` is True when the PNG
    carries an alpha channel or a tRNS chunk; `transparent` is True only when a pixel is
    actually transparent, computed with Pillow when it is installed (else None = unknown).
    """
    info: dict[str, Any] = {"format": None, "width": None, "height": None,
                            "has_alpha": None, "transparent": None, "animated": None,
                            "bytes": len(data)}
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 33:
        w, h, _depth, ctype = struct.unpack(">IIBB", data[16:26])
        info.update(format="png", width=w, height=h, animated=b"acTL" in data[:4096])
        info["has_alpha"] = ctype in (4, 6) or b"tRNS" in data
    elif data[:2] == b"\xff\xd8":
        info.update(format="jpg", has_alpha=False, transparent=False, animated=False)
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD,
                          0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                info.update(width=w, height=h)
                break
            i += 2 + seg
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10])
        info.update(format="gif", width=w, height=h, animated=data.count(b"\x21\xf9") > 1)
    if info["format"] == "png" and info["has_alpha"] is False:
        info["transparent"] = False
    elif info["format"] in ("png", "gif") and info["transparent"] is None:
        try:
            import io

            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:
                if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                    alpha = im.convert("RGBA").getchannel("A")
                    info["transparent"] = alpha.getextrema()[0] < 255
                else:
                    info["transparent"] = False
                if info["format"] == "gif":
                    info["animated"] = getattr(im, "n_frames", 1) > 1
        except Exception:  # noqa: BLE001 - no Pillow or unreadable: stays unknown
            pass
    return info


# The surfaces `image_problems` knows, mapped to (min key, recommended key, bytes key,
# formats key). None = Etsy publishes nothing for that dimension.
IMAGE_SURFACES: dict[str, tuple] = {
    "shop_logo": ("logo_min_px", "logo_recommended_px", "logo_max_bytes", "logo_formats"),
    "profile_photo": ("profile_min_px", "profile_recommended_px", "profile_max_bytes",
                      "profile_formats"),
    "big_banner": ("big_banner_min_px", "big_banner_recommended_px", None, "image_formats"),
    "mini_banner": ("mini_banner_min_px", "mini_banner_recommended_px", None, "image_formats"),
    "receipt_banner": ("receipt_banner_min_px", None, None, "image_formats"),
    "about_photo": (None, None, "about_photo_max_bytes", "logo_formats"),
    "listing_image": (None, None, None, "image_formats"),
}


def image_problems(surface: str, *, width: int, height: int, nbytes: int | None = None,
                   fmt: str | None = None, transparent: bool | None = None,
                   animated: bool | None = None, position: int = 1) -> list[dict]:
    """Every published Etsy rule this image breaks, for one surface. Empty = none broken."""
    if surface not in IMAGE_SURFACES:
        raise KeyError(f"unknown image surface {surface!r}: {sorted(IMAGE_SURFACES)}")
    mn, rec, byt, fmts = IMAGE_SURFACES[surface]
    out: list[dict] = []
    if mn:
        mw, mh = CONSTRAINTS[mn].value
        if width < mw or height < mh:
            out.append(_finding("IMAGE_BELOW_MINIMUM", mn,
                                f"{surface} is {width}x{height}; Etsy requires at least "
                                f"{mw}x{mh}"))
    if rec:
        rw, rh = CONSTRAINTS[rec].value
        if width < rw or height < rh:
            out.append(_finding("IMAGE_BELOW_RECOMMENDED", rec,
                                f"{surface} is {width}x{height}; Etsy recommends {rw}x{rh}"))
        elif surface in ("big_banner", "mini_banner") and abs(width / height - rw / rh) > 0.02:
            out.append(_finding("BANNER_ASPECT_DIFFERS", rec,
                                f"{surface} aspect {width / height:.3f} differs from Etsy's "
                                f"recommended {rw}x{rh} ({rw / rh:.3f}); Etsy will crop",
                                severity="warn"))
    if surface == "profile_photo" and width != height:
        out.append(_finding("PROFILE_NOT_SQUARE", "profile_square",
                            f"profile photo is {width}x{height}; Etsy distorts non-square"))
    if surface == "shop_logo" and width != height:
        out.append(_finding("LOGO_NOT_SQUARE", "logo_crop",
                            f"logo is {width}x{height}; Etsy's editor crops it square",
                            severity="warn"))
    if byt and nbytes is not None and nbytes >= CONSTRAINTS[byt].value:
        out.append(_finding("IMAGE_TOO_LARGE", byt,
                            f"{surface} is {nbytes} bytes; Etsy's limit is "
                            f"{CONSTRAINTS[byt].value // MB}MB"))
    if fmt is not None and fmt.lower().lstrip(".").replace("jpeg", "jpg") not in \
            tuple(f.replace("jpeg", "jpg") for f in CONSTRAINTS[fmts].value):
        out.append(_finding("IMAGE_FORMAT_UNSUPPORTED", fmts,
                            f"{surface} is .{fmt}; Etsy accepts "
                            f"{list(CONSTRAINTS[fmts].value)}", severity="fail"))
    if transparent:
        out.append(_finding("IMAGE_TRANSPARENT", "no_animation_no_transparency",
                            f"{surface} has transparent pixels; Etsy renders them black"))
    if animated:
        out.append(_finding("IMAGE_ANIMATED", "no_animation_no_transparency",
                            f"{surface} is animated; Etsy does not support animated images"))
    if surface == "listing_image":
        rec_px = CONSTRAINTS["listing_image_recommended_px"].value
        if min(width, height) < rec_px:
            out.append(_finding("LISTING_IMAGE_BELOW_2000", "listing_image_recommended_px",
                                f"listing image {width}x{height}; Etsy recommends both sides "
                                f">= {rec_px}"))
        if position == 1:
            first = CONSTRAINTS["first_image_min_px"].value
            if min(width, height) < first:
                out.append(_finding("FIRST_IMAGE_BELOW_635", "first_image_min_px",
                                    f"first listing image {width}x{height} is under {first} px; "
                                    f"Etsy says it may show lower in search"))
            if height > width:
                out.append(_finding("FIRST_IMAGE_PORTRAIT", "first_image_orientation",
                                    f"first listing image is portrait ({width}x{height}); "
                                    f"Etsy asks for landscape or square"))
        if nbytes is not None and nbytes > CONSTRAINTS["image_upload_bytes_advice"].value:
            out.append(_finding("IMAGE_OVER_1MB", "image_upload_bytes_advice",
                                f"listing image is {nbytes} bytes; Etsy warns browser uploads "
                                f"over 1MB may not finish (API behaviour UNKNOWN)"))
    return out


def image_bytes_problems(surface: str, data: bytes, *, position: int = 1) -> list[dict]:
    """`image_problems` on real bytes. Unreadable bytes are a failure, not a pass."""
    info = image_info(data)
    if not info["width"]:
        return [_finding("IMAGE_UNREADABLE", "image_formats",
                         f"{surface}: bytes are not a PNG/JPEG/GIF this check can read",
                         severity="fail")]
    return image_problems(surface, width=info["width"], height=info["height"],
                          nbytes=len(data), fmt=info["format"],
                          transparent=info["transparent"], animated=info["animated"],
                          position=position)


_FILENAME_OK = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def digital_file_problems(files: list[tuple[str, int]]) -> list[dict]:
    """Etsy's published digital-file rules for one listing's files: (name, size_bytes)."""
    out: list[dict] = []
    if not files:
        out.append(_finding("DIGITAL_NO_FILE", "instant_digital_needs_file",
                            "an instant digital listing has no file; Etsy will not publish"))
    if len(files) > CONSTRAINTS["digital_files_max"].value:
        out.append(_finding("DIGITAL_TOO_MANY_FILES", "digital_files_max",
                            f"{len(files)} files; Etsy allows "
                            f"{CONSTRAINTS['digital_files_max'].value}"))
    types = CONSTRAINTS["digital_file_types"].value
    for name, size in files:
        if len(name) > CONSTRAINTS["digital_filename_max_chars"].value:
            out.append(_finding("DIGITAL_FILENAME_TOO_LONG", "digital_filename_max_chars",
                                f"{name!r} is {len(name)} characters; Etsy allows 70"))
        bad = sorted({c for c in name if c not in _FILENAME_OK})
        if bad:
            out.append(_finding("DIGITAL_FILENAME_CHARACTERS", "digital_filename_max_chars",
                                f"{name!r} contains {bad}; Etsy allows letters, digits, "
                                f"periods, underscores and hyphens"))
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in types:
            out.append(_finding("DIGITAL_FILE_TYPE", "digital_file_types",
                                f"{name!r}: .{ext} is not an Etsy digital file type"))
        if size > CONSTRAINTS["digital_file_max_bytes"].value:
            out.append(_finding("DIGITAL_FILE_TOO_LARGE", "digital_file_max_bytes",
                                f"{name!r} is {size} bytes; Etsy allows 20MB per file"))
    return out


# Text fields `text_problems` knows: field -> constraint key of its character limit.
TEXT_LIMITS = {"shop_title": "shop_title_max_chars", "about": "about_max_chars",
               "announcement": "announcement_max_chars",
               "section_name": "section_name_max_chars", "listing_title": "title_max_chars",
               "tag": "tag_max_chars", "alt_text": "alt_text_max_chars",
               "digital_sale_message": "digital_sale_message_max_chars"}


def text_problems(fieldname: str, text: str) -> list[dict]:
    """A text against its Etsy character limit. An UNKNOWN limit is never a pass."""
    key = TEXT_LIMITS[fieldname]
    c = CONSTRAINTS[key]
    n = len(text or "")
    if c.basis == UNKNOWN:
        return [_finding("LIMIT_UNKNOWN", key, f"{fieldname}: {n} characters; Etsy publishes "
                                               f"no limit. Check Etsy's counter at entry.")]
    out = []
    if n > c.value:
        out.append(_finding("TEXT_TOO_LONG", key,
                            f"{fieldname} is {n} characters; Etsy allows {c.value}"))
    if fieldname == "tag" and text[:1] in ("'", "-"):
        out.append(_finding("TAG_LEADING_PUNCTUATION", "tag_no_leading_punct",
                            f"tag {text!r} starts with {text[:1]!r}; Etsy refuses that"))
    if fieldname == "alt_text" and n > CONSTRAINTS["alt_text_advice_chars"].value:
        out.append(_finding("ALT_TEXT_OVER_ADVICE", "alt_text_advice_chars",
                            f"alt text is {n} characters; Etsy advises up to 250"))
    return out


def shop_name_problems(name: str) -> list[dict]:
    lo, hi = CONSTRAINTS["shop_name_chars"].value
    out = []
    if not lo <= len(name) <= hi:
        out.append(_finding("SHOP_NAME_LENGTH", "shop_name_chars",
                            f"shop name {name!r} is {len(name)} characters; Etsy needs {lo}-{hi}"))
    if any(not ch.isalnum() for ch in name):
        out.append(_finding("SHOP_NAME_CHARACTERS", "shop_name_chars",
                            f"shop name {name!r} has spaces or punctuation; Etsy refuses both"))
    return out


# ---------------------------------------------------------------------------
# Reconciliation: what this repository's code asserts against what Etsy publishes.

AGREES, DISAGREES, ETSY_UNKNOWN, NOT_PRESENT = (
    "AGREES", "DISAGREES", "ETSY_PUBLISHES_NONE", "NOT_PRESENT")
# The repo carries no number (or an unsourced one) where Etsy now publishes one: not wrong,
# but the repo's basis label should be upgraded to the verified value.
REPO_UNKNOWN_ETSY_PUBLISHES = "REPO_UNKNOWN_ETSY_PUBLISHES"
AGREES_REPO_UNSOURCED = "AGREES_BUT_REPO_LABELS_UNSOURCED"
STATUSES = (AGREES, DISAGREES, ETSY_UNKNOWN, NOT_PRESENT, REPO_UNKNOWN_ETSY_PUBLISHES,
            AGREES_REPO_UNSOURCED)


def _row(where: str, repo: Any, key: str, status: str, note: str = "") -> dict:
    c = CONSTRAINTS[key]
    return {"where": where, "repo_value": repo, "etsy_value": c.value if c.basis != UNKNOWN
            else None, "constraint": key, "basis": c.basis, "status": status, "note": note}


def _cmp(where: str, repo: Any, key: str, note: str = "") -> dict:
    c = CONSTRAINTS[key]
    if c.basis == UNKNOWN:
        return _row(where, repo, key, ETSY_UNKNOWN, note or c.note)
    want = list(c.value) if isinstance(c.value, tuple) else c.value
    got = list(repo) if isinstance(repo, tuple) else repo
    return _row(where, repo, key, AGREES if got == want else DISAGREES, note)


def reconcile() -> list[dict]:
    """Every Etsy number the codebase asserts, compared with the evidence above.

    Imports lazily and never raises: a module that is absent is NOT_PRESENT, so this runs in
    any worktree and reports on whatever exists there.
    """
    rows: list[dict] = []

    def guard(where: str, key: str, fn) -> None:
        try:
            rows.extend(fn())
        except Exception as e:  # noqa: BLE001 - reconciliation reports, never crashes
            rows.append(_row(where, None, key, NOT_PRESENT, f"{type(e).__name__}: {e}"[:200]))

    def etsy_client():
        from . import etsy
        return [_cmp("integrations.etsy.TITLE_MAX", etsy.TITLE_MAX, "title_max_chars"),
                _cmp("integrations.etsy.TAGS_MAX", etsy.TAGS_MAX, "tags_max"),
                _cmp("integrations.etsy.TAG_CHARS_MAX", etsy.TAG_CHARS_MAX, "tag_max_chars"),
                _cmp("integrations.etsy.MATERIALS_MAX", etsy.MATERIALS_MAX, "materials_max"),
                _cmp("integrations.etsy.DESCRIPTION_MAX", etsy.DESCRIPTION_MAX,
                     "description_max_chars"),
                _cmp("integrations.etsy.ALT_TEXT_MAX", etsy.ALT_TEXT_MAX, "alt_text_max_chars"),
                _row("integrations.etsy.IMAGE_CONTENT_TYPES",
                     sorted(s.lstrip(".") for s in etsy.IMAGE_CONTENT_TYPES), "image_formats",
                     AGREES if {s.lstrip(".").replace("jpeg", "jpg")
                                for s in etsy.IMAGE_CONTENT_TYPES}
                     <= set(CONSTRAINTS["image_formats"].value) else DISAGREES,
                     "the client may send a subset of Etsy's formats, never a superset")]

    def schema():
        from ..publish import listing_schema as ls
        return [_cmp("publish.listing_schema.MAX_IMAGES", ls.MAX_IMAGES, "listing_images_max")]

    def brand():
        from ..brand import storefront as sf
        return [_cmp("brand.storefront.BANNER_SIZE", sf.BANNER_SIZE,
                     "big_banner_recommended_px"),
                _cmp("brand.storefront.ICON_SIZE", sf.ICON_SIZE, "logo_recommended_px"),
                _cmp("brand.storefront.ABOUT_MAX", sf.ABOUT_MAX, "about_max_chars"),
                _cmp("brand.storefront.ANNOUNCEMENT_MAX", sf.ANNOUNCEMENT_MAX,
                     "announcement_max_chars",
                     "Etsy publishes no announcement limit; 160 is an internal style cap"),
                _row("brand.storefront.SECTIONS (count)", len(sf.SECTIONS), "sections_max",
                     AGREES if len(sf.SECTIONS) <= 20 else DISAGREES),
                _row("brand.storefront.SECTIONS (longest name)",
                     max(len(s.name) for s in sf.SECTIONS), "section_name_max_chars",
                     AGREES if max(len(s.name) for s in sf.SECTIONS) <= 24 else DISAGREES)]

    def preview_assumption():
        from ..brand import storefront_preview as sp
        return [_row("brand.storefront_preview.SECTION_LABEL_MAX", sp.SECTION_LABEL_MAX,
                     "section_name_max_chars",
                     AGREES if sp.SECTION_LABEL_MAX <= 24 else DISAGREES,
                     "repo labels 30 ASSUMED; Etsy's verified section-name limit is 24")]

    def listing_canvas():
        from ..publish import listing_assets as la
        return [_row("publish.listing_assets.CANVAS", la.CANVAS,
                     "listing_image_recommended_px",
                     AGREES if la.CANVAS >= 2000 else DISAGREES)]

    def seo_consts():
        from ..commerce import search, seo
        return [_cmp("commerce.seo.TITLE_MAX", seo.TITLE_MAX, "title_max_chars"),
                _cmp("commerce.seo.TAG_MAX_CHARS", seo.TAG_MAX_CHARS, "tag_max_chars"),
                _cmp("commerce.seo.TAG_MAX_COUNT", seo.TAG_MAX_COUNT, "tags_max"),
                _cmp("commerce.search.TITLE_MAX", search.TITLE_MAX, "title_max_chars"),
                _cmp("commerce.search.TAG_MAX_CHARS", search.TAG_MAX_CHARS, "tag_max_chars")]

    def store_limits():
        from ..store_foundation import limits as L
        out = []
        for lk, ck in (("about", "about_max_chars"), ("announcement", "announcement_max_chars"),
                       ("sections_count", "sections_max"), ("shop_title", "shop_title_max_chars"),
                       ("section_name", "section_name_max_chars"),
                       ("shop_name", "shop_name_chars")):
            lim = L.LIMITS.get(lk)
            if lim is None:
                continue
            c = CONSTRAINTS[ck]
            repo = lim.max_chars
            if c.basis == UNKNOWN:
                status = ETSY_UNKNOWN
            elif repo is None:
                status = REPO_UNKNOWN_ETSY_PUBLISHES
            else:
                want = c.value[1] if ck == "shop_name_chars" else c.value
                status = (DISAGREES if repo != want else
                          AGREES if lim.basis == "VERIFIED" else AGREES_REPO_UNSOURCED)
            out.append(_row(f"store_foundation.limits.LIMITS[{lk!r}] ({lim.basis})", repo, ck,
                            status))
        for lk, ck in (("banner_px", "big_banner_recommended_px"),
                       ("icon_px", "logo_recommended_px")):
            lim = L.LIMITS.get(lk)
            if lim is not None:
                out.append(_row(f"store_foundation.limits.LIMITS[{lk!r}] ({lim.basis})",
                                lim.max_chars, ck,
                                REPO_UNKNOWN_ETSY_PUBLISHES if lim.basis != "VERIFIED"
                                else AGREES,
                                "repo records this as UNKNOWN; Etsy publishes it"))
        return out

    def shop_copy():
        from ..commerce import shop_package
        t = shop_package.shop_text()
        out = [_row("commerce.shop_package.shop_text()['title'] length", len(t["title"]),
                    "shop_title_max_chars",
                    AGREES if len(t["title"]) <= 55 else DISAGREES, repr(t["title"]))]
        out.append(_row("commerce.shop_package.shop_text()['policy_additional']",
                        bool(t.get("policy_additional")), "policy_additional_eu_only",
                        DISAGREES if t.get("policy_additional") else AGREES,
                        "a Canadian shop sending policy_additional gets an error from Etsy"))
        return out

    def copy_v2():
        import importlib
        mod = importlib.import_module("brambleloop.store_foundation.copy_v2")
        out = []
        tagline = getattr(mod, "TAGLINE", None) or getattr(mod, "SHOP_TITLE", None)
        if isinstance(tagline, str):
            out.append(_row("store_foundation.copy_v2 tagline length", len(tagline),
                            "shop_title_max_chars",
                            AGREES if len(tagline) <= 55 else DISAGREES, repr(tagline)))
        return out

    for where, key, fn in (("integrations.etsy", "title_max_chars", etsy_client),
                           ("publish.listing_schema", "listing_images_max", schema),
                           ("brand.storefront", "big_banner_recommended_px", brand),
                           ("brand.storefront_preview", "section_name_max_chars",
                            preview_assumption),
                           ("publish.listing_assets", "listing_image_recommended_px",
                            listing_canvas),
                           ("commerce.seo/search", "title_max_chars", seo_consts),
                           ("store_foundation.limits", "shop_title_max_chars", store_limits),
                           ("commerce.shop_package", "shop_title_max_chars", shop_copy),
                           ("store_foundation.copy_v2", "shop_title_max_chars", copy_v2)):
        guard(where, key, fn)
    return rows


def summary() -> dict:
    """Everything above as JSON-serialisable data, for lanes B/G, the API and the docs."""
    by_basis: dict[str, int] = {b: 0 for b in BASES}
    for c in CONSTRAINTS.values():
        by_basis[c.basis] += 1
    return {"retrieved_on": RETRIEVED_ON, "max_age_days": MAX_AGE_DAYS, "stale": is_stale(),
            "counts_by_basis": by_basis,
            "constraints": [c.to_dict() for c in CONSTRAINTS.values()],
            "sources": [s.to_dict() for s in SOURCES.values()],
            "taxonomy_flow": [dict(s) for s in TAXONOMY_FLOW],
            "taxonomy_id": dict(TAXONOMY_ID_STATUS),
            "note": ("Etsy-published requirements, read 2026-10-06. VERIFIED means an Etsy "
                     "document says it (quoted); it does not mean Etsy has been observed "
                     "enforcing it on this shop.")}


__all__ = ["CONSTRAINTS", "SOURCES", "TAXONOMY_FLOW", "TAXONOMY_ID_STATUS", "IMAGE_SURFACES",
           "TEXT_LIMITS", "value", "image_info", "image_problems", "image_bytes_problems",
           "digital_file_problems", "text_problems", "shop_name_problems", "reconcile",
           "summary", "is_stale", "VERIFIED_HELP", "VERIFIED_OPENAPI", "UNVERIFIED", "UNKNOWN"]

