"""Read-back verification: does the listing on Etsy match what we sent?

A write we never read back is an assumption. This module turns "we sent a title" into "Etsy
holds this title", and it is the only thing in the commerce path that can tell the difference
between a request Etsy accepted and a request Etsy acted on.

Three failure modes it exists to catch, each of which returns HTTP 200 on the way out:

1. **A field Etsy ignored.** `updateListing` has no `price` property. Send one and the
   request succeeds, nothing changes, and the only evidence is a read-back.
2. **A field Etsy transformed.** Etsy returns `price` as a Money object
   (`{amount, divisor, currency_code}`), not the decimal we sent, and it renames `type` to
   `listing_type` on the way back. A naive comparison reports both as mismatches, which is
   how a verifier gets switched off.
3. **A field Etsy did not return at all.** Not the same as a mismatch, and not the same as a
   match. It is reported as its own verdict, because "we cannot tell" is the honest answer
   and treating it as a pass is how a verifier becomes decoration.

Nothing here is Etsy's behaviour on our data -- it is Etsy's documented response shape,
applied to what came back. The comparison itself is real as soon as a real response arrives.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NOT_RETURNED = "NOT_RETURNED"

# Etsy's response field for a value we send under a different name. From the ShopListing
# schema: the writable property is `type` (enum physical/download/both); the property Etsy
# returns is `listing_type` with the same enum. A verifier that does not know this reports
# every listing's type as missing.
RESPONSE_ALIASES = {"type": ("listing_type", "type")}

# Fields this system may send that are not compared field-by-field. The upload parameters
# (`image`, `file`, `name`, `rank`, `alt_text`, `overwrite`, `is_watermarked`) are not listing
# properties and Etsy's ShopListing response does not carry them. `state` is excluded for the
# opposite reason: Etsy does return it, and it is checked on its own against `expect_state`
# because it is the one field whose value decides whether a customer can reach the listing.
NOT_IN_RESPONSE = frozenset({"state", "image", "file", "name", "rank", "alt_text",
                             "overwrite", "is_watermarked"})


@dataclass(frozen=True)
class FieldVerdict:
    field: str
    verdict: str
    sent: Any = None
    remote: Any = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == MATCH


@dataclass
class ReadBack:
    """What Etsy holds, judged against what we sent."""

    listing_id: str
    verdicts: list[FieldVerdict] = field(default_factory=list)
    state: str = ""
    image_count: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def mismatches(self) -> list[FieldVerdict]:
        return [v for v in self.verdicts if v.verdict == MISMATCH]

    @property
    def unverifiable(self) -> list[FieldVerdict]:
        return [v for v in self.verdicts if v.verdict == NOT_RETURNED]

    @property
    def verified(self) -> bool:
        """True only when every field we sent was returned and matched.

        A field Etsy did not return counts against this deliberately. The alternative is a
        verifier that passes because it could not see, which is the same as not verifying.
        """
        return (not self.problems and bool(self.verdicts)
                and all(v.ok for v in self.verdicts))

    def summary(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "verified": self.verified,
            "state_on_etsy": self.state,
            "images_on_etsy": self.image_count,
            "fields_checked": len(self.verdicts),
            "matched": sum(1 for v in self.verdicts if v.ok),
            "mismatched": [{"field": v.field, "sent": v.sent, "remote": v.remote}
                           for v in self.mismatches],
            "not_returned": [v.field for v in self.unverifiable],
            "problems": list(self.problems),
        }


def money_to_decimal(value: Any) -> float | None:
    """Etsy's Money object as the number we sent, or None if this is not a Money.

    Etsy: Money is `{amount, divisor, currency_code}` and the price on a listing response is
    one. A price of CA$7.50 comes back as amount 750, divisor 100. Comparing 750 to 7.5 and
    calling it a mismatch is how the first read-back gets dismissed as broken.
    """
    if isinstance(value, dict) and "amount" in value and "divisor" in value:
        try:
            divisor = float(value["divisor"]) or 1.0
            return round(float(value["amount"]) / divisor, 4)
        except (TypeError, ValueError):
            return None
    return None


def _normalise(key: str, value: Any) -> Any:
    """Put a sent value and a returned value into the same shape before comparing.

    Every rule here is a documented difference between the request and the response, not a
    tolerance invented to make a comparison pass. There is no fuzzy matching: two strings that
    differ after normalisation are a mismatch.
    """
    money = money_to_decimal(value)
    if money is not None:
        return money
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value]
    if isinstance(value, str):
        text = value.strip()
        if key in ("tags", "materials", "image_ids"):
            # We may have sent these comma-joined; Etsy returns a list.
            return [part.strip() for part in text.split(",") if part.strip()]
        if key == "description":
            # Etsy's response carries the description as it will render it, which for a
            # description containing & or < is HTML-escaped. Unescaping is not a tolerance:
            # it is undoing a transformation Etsy applied, and if the text still differs the
            # verdict is still MISMATCH.
            return re.sub(r"\r\n", "\n", html.unescape(text))
        lowered = text.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        try:
            return round(float(text), 4)
        except ValueError:
            return text
    return value


def verify(sent: dict[str, Any], remote: dict[str, Any], *,
           listing_id: str = "", expect_state: str = "draft",
           expect_images: int | None = None) -> ReadBack:
    """Compare a write against the listing Etsy returned afterwards.

    `sent` is what went into the request body. `remote` is the body of a subsequent
    `getListing` -- a separate request, made after the write, which is the whole point: the
    write's own 200 response is Etsy repeating our own data back at us, and a mismatch cannot
    appear in it.
    """
    out = ReadBack(listing_id=str(listing_id or remote.get("listing_id") or ""))

    if not remote:
        out.problems.append(
            "Etsy returned no listing on read-back. Either the id is wrong or the listing "
            "does not exist, and in both cases the write is unverified rather than fine.")
        return out

    out.state = str(remote.get("state") or "")
    images = remote.get("images")
    out.image_count = len(images) if isinstance(images, list) else 0

    if expect_state and out.state.lower() != expect_state.lower():
        out.problems.append(
            f"state on Etsy is {out.state!r}, expected {expect_state!r}. For a draft this is "
            f"the single most important field on the listing: a listing that is not a draft "
            f"is a listing a customer can reach.")
    if expect_images is not None and out.image_count != expect_images:
        out.problems.append(
            f"Etsy holds {out.image_count} image(s) for this listing, expected "
            f"{expect_images}. Etsy will not activate a listing with none, so this is the "
            f"field that decides whether the listing could ever go live.")

    for key, value in sent.items():
        if key in NOT_IN_RESPONSE:
            continue
        names = RESPONSE_ALIASES.get(key, (key,))
        present = [n for n in names if n in remote]
        if not present:
            out.verdicts.append(FieldVerdict(
                key, NOT_RETURNED, sent=value,
                note=f"Etsy's response carries none of {list(names)}, so this write cannot "
                     f"be confirmed either way."))
            continue
        name = present[0]
        ours = _normalise(key, value)
        theirs = _normalise(key, remote[name])
        verdict = MATCH if ours == theirs else MISMATCH
        out.verdicts.append(FieldVerdict(key, verdict, sent=ours, remote=theirs,
                                         note="" if name == key else f"returned as {name}"))
    return out
