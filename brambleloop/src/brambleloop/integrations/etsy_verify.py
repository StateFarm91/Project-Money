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


# ---------------------------------------------------------------------------
# F-559: the customer's files, read back from Etsy
# ---------------------------------------------------------------------------

#: Etsy exposes no content hash for a listing file. The verdict for the hash is therefore
#: never MATCH on Etsy's side: it is this, and the byte identity is established *before* the
#: upload (the bytes sent were compared to the certified release hash) rather than after it.
HASH_NOT_EXPOSED = "HASH_NOT_EXPOSED_BY_ETSY"


@dataclass
class FileReadBack:
    """The files Etsy holds for one listing, judged against the certified release's files."""

    listing_id: str
    files: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        """True only when every certified file is on Etsy under its name and at its size,
        every file we sent is the certified one, and Etsy holds nothing else.

        An empty expectation is not verified: a listing with no certified file to compare
        against is a listing whose delivery nobody checked.
        """
        return (not self.problems and bool(self.files)
                and all(f["name"] == MATCH and f["size"] == MATCH and f["certified"]
                        for f in self.files))

    def summary(self) -> dict[str, Any]:
        return {"listing_id": self.listing_id, "verified": self.verified,
                "files": list(self.files), "problems": list(self.problems),
                "hash_on_etsy": HASH_NOT_EXPOSED,
                "hash_note": ("Etsy's ShopListingFile has filename and size_bytes and no "
                              "hash. Byte identity is proven on our side: the sha256 of the "
                              "bytes uploaded equals the certified release hash. On Etsy's "
                              "side the proof is name + exact size, and it says so.")}


def _remote_size(row: dict[str, Any]) -> int | None:
    """`size_bytes` when Etsy returns it. `filesize` is a human string ("1.2 MB") and is
    never parsed into a byte count: rounding a display string is how a stale file of a
    similar size would pass."""
    value = row.get("size_bytes")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def verify_files(expected: list[dict[str, Any]], remote: list[dict[str, Any]] | None, *,
                 listing_id: str = "") -> FileReadBack:
    """Compare the files attached to a listing with the certified release (F-559).

    `expected` is one entry per file we uploaded: `name`, `size` (bytes), `sha256` (of the
    bytes sent) and `certified_sha256` (the release hash `assets.build` recorded). `remote`
    is `EtsyClient.get_listing_files`'s results, or None when the read failed -- which is
    unverified, never clean.
    """
    out = FileReadBack(listing_id=str(listing_id))
    if remote is None:
        out.problems.append("the listing's files could not be read back from Etsy, so what "
                            "the buyer would download is unverified")
        return out
    if not expected:
        out.problems.append("no certified file was named for this listing, so there is "
                            "nothing to verify delivery against")
        return out
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in remote:
        by_name.setdefault(str(row.get("filename") or ""), []).append(row)
    seen: set[str] = set()
    for want in expected:
        name = str(want.get("name") or "")
        rows = by_name.get(name) or []
        certified = bool(want.get("sha256")) and want.get("sha256") == want.get(
            "certified_sha256")
        entry: dict[str, Any] = {"file": name, "sent_sha256": want.get("sha256"),
                                 "certified_sha256": want.get("certified_sha256"),
                                 "certified": certified, "size_sent": want.get("size")}
        if not certified:
            out.problems.append(
                f"{name}: the bytes sent hash to {str(want.get('sha256'))[:12]} and the "
                f"certified release file is {str(want.get('certified_sha256'))[:12]}")
        if not rows:
            entry.update(name=NOT_RETURNED, size=NOT_RETURNED, size_on_etsy=None)
            out.problems.append(f"{name} is not attached to listing {listing_id} on Etsy")
        else:
            seen.add(name)
            if len(rows) > 1:
                out.problems.append(f"{name} is attached {len(rows)} times")
            size = _remote_size(rows[0])
            entry["name"] = MATCH
            entry["size_on_etsy"] = size
            if size is None:
                entry["size"] = NOT_RETURNED
                out.problems.append(f"{name}: Etsy returned no size_bytes, so a stale file "
                                    f"of the same name cannot be told from the certified one")
            elif size != int(want.get("size") or -1):
                entry["size"] = MISMATCH
                out.problems.append(f"{name} is {size} bytes on Etsy and {want.get('size')} "
                                    f"bytes certified: a different file under the same name")
            else:
                entry["size"] = MATCH
        out.files.append(entry)
    stale = sorted(n for n in by_name if n not in seen)
    for name in stale:
        out.problems.append(f"Etsy holds {name!r} on listing {listing_id}, which is not a "
                            f"file of the certified release: a stale or foreign download")
    return out


# ---------------------------------------------------------------------------
# W3-I: the listing's images, rank by rank -- count, order, alt text and pixel size
# ---------------------------------------------------------------------------

# Etsy, uploadListingImage: "When uploading a new image, data such as colors and size may
# return as null values due to asynchronous processing of the image. Use getListingImage
# endpoint to fetch these values." So a null size straight after upload is PENDING, which is
# neither a match nor a mismatch, and is never counted as verified.
PENDING = "PENDING_ETSY_PROCESSING"


@dataclass
class ImageReadBack:
    """The images Etsy holds for one listing, judged against what was uploaded."""

    listing_id: str
    images: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        """True only when every image sent is on Etsy at its rank, with its alt text and its
        pixel size, and Etsy holds no other image. Pending sizes are not verified."""
        return (not self.problems and bool(self.images)
                and all(i["alt_text"] == MATCH and i["size"] == MATCH for i in self.images))

    @property
    def pending(self) -> bool:
        return any(i.get("size") == PENDING for i in self.images)

    def summary(self) -> dict[str, Any]:
        return {"listing_id": self.listing_id, "verified": self.verified,
                "pending": self.pending, "images": list(self.images),
                "problems": list(self.problems),
                "hash_note": ("Etsy's ListingImage carries no hash of the uploaded bytes and "
                              "re-encodes images (sRGB, compression). Byte identity is proven "
                              "on our side; on Etsy's side the proof is rank, alt text and "
                              "full_width x full_height, and it says so.")}


def _dim(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def verify_images(expected: list[dict[str, Any]], remote: list[dict[str, Any]] | None, *,
                  listing_id: str = "") -> ImageReadBack:
    """Compare a listing's images on Etsy with the images uploaded, in rank order.

    `expected`: one entry per image sent, in upload order, with `alt_text`, `width`,
    `height` (read from the bytes sent, e.g. `etsy_constraints.image_info`). `remote`:
    `EtsyClient.get_listing_images` results, or None when the read failed (unverified).

    Etsy serves `url_fullxfull` at up to 3000 px per side, so an image sent larger than that
    may legitimately come back scaled; a scaled size with the same aspect ratio is reported
    as MATCH with a note, and anything else as MISMATCH.
    """
    out = ImageReadBack(listing_id=str(listing_id))
    if remote is None:
        out.problems.append("the listing's images could not be read back from Etsy, so what "
                            "a shopper sees is unverified")
        return out
    if not expected:
        out.problems.append("no uploaded image was named for this listing, so there is "
                            "nothing to verify against (and Etsy will not activate it)")
        return out
    held = sorted(remote, key=lambda r: int(_dim(r.get("rank")) or 0))
    if len(held) != len(expected):
        out.problems.append(f"images: sent {len(expected)}, Etsy holds {len(held)}")
    for rank, want in enumerate(expected, start=1):
        entry: dict[str, Any] = {"rank": rank, "sent_alt_text": want.get("alt_text", ""),
                                 "sent_px": [want.get("width"), want.get("height")]}
        got = held[rank - 1] if rank <= len(held) else None
        if got is None:
            entry.update(alt_text=NOT_RETURNED, size=NOT_RETURNED, etsy_px=None)
            out.problems.append(f"image rank {rank} is not on listing {listing_id}")
            out.images.append(entry)
            continue
        entry["listing_image_id"] = got.get("listing_image_id")
        sent_alt, got_alt = str(want.get("alt_text") or ""), str(got.get("alt_text") or "")
        entry["alt_text"] = MATCH if sent_alt == got_alt else MISMATCH
        if entry["alt_text"] == MISMATCH:
            out.problems.append(f"image rank {rank} alt_text: sent {sent_alt!r}, Etsy holds "
                                f"{got_alt!r}")
        w, h = _dim(got.get("full_width")), _dim(got.get("full_height"))
        entry["etsy_px"] = [w, h]
        sw, sh = _dim(want.get("width")), _dim(want.get("height"))
        if w is None or h is None:
            entry["size"] = PENDING
            out.problems.append(f"image rank {rank}: Etsy has not reported its size yet "
                                f"(asynchronous processing); re-read before activation")
        elif sw is None or sh is None:
            entry["size"] = NOT_RETURNED
            out.problems.append(f"image rank {rank}: the size sent was not recorded, so "
                                f"Etsy's {w}x{h} cannot be compared")
        elif (w, h) == (sw, sh):
            entry["size"] = MATCH
        elif max(sw, sh) > 3000 and max(w, h) <= 3000 and abs(w * sh - h * sw) <= max(sw, sh):
            entry["size"] = MATCH
            entry["note"] = f"sent {sw}x{sh}, served scaled to {w}x{h} (Etsy's 3000 px cap)"
        else:
            entry["size"] = MISMATCH
            out.problems.append(f"image rank {rank} is {w}x{h} on Etsy and {sw}x{sh} as sent: "
                                f"a different or cropped image")
        out.images.append(entry)
    for extra in held[len(expected):]:
        out.problems.append(f"Etsy holds an extra image (listing_image_id "
                            f"{extra.get('listing_image_id')}) that was not sent")
    return out


# ---------------------------------------------------------------------------
# F-543: the remote draft against the certified listing, before activation
# ---------------------------------------------------------------------------


def activation_readiness(*, sent: dict[str, Any], remote: dict[str, Any],
                         remote_files: list[dict[str, Any]] | None,
                         expected_files: list[dict[str, Any]],
                         expected_images: int, listing_id: str = "",
                         disclosure: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything Etsy holds for a draft, compared with what was certified, in one verdict.

    Field-by-field read-back (title, description, tags, materials, price, quantity,
    taxonomy, who/when made, type) through `verify`; the draft state; the image count
    against the certified frame count; the files through `verify_files`; and the
    disclosure check run on the copy **as Etsy holds it**, because a disclosure that is in
    our database and not on the listing is not a disclosure. `ready` is True only when every
    one of them passed; anything unread is a reason, never a pass.
    """
    fields = verify(sent, remote, listing_id=listing_id, expect_state="draft",
                    expect_images=expected_images)
    files = verify_files(expected_files, remote_files, listing_id=listing_id)
    reasons: list[str] = []
    reasons.extend(fields.problems)
    reasons.extend(f"{v.field} on Etsy is {v.remote!r}, certified {v.sent!r}"
                   for v in fields.mismatches)
    reasons.extend(f"{v.field} was not returned by Etsy, so it is unverified"
                   for v in fields.unverifiable)
    if expected_images < 1:
        reasons.append("the certified listing set has no frame, so there is no first image "
                       "to activate with")
    reasons.extend(files.problems)
    if disclosure is None or not disclosure.get("checked"):
        reasons.append("the disclosure check was not run on the copy Etsy holds")
    elif disclosure.get("finding"):
        reasons.append(f"the copy on Etsy is missing owed disclosures: "
                       f"{disclosure.get('missing')} {disclosure.get('misplaced') or ''}")
    return {"ready": not reasons, "reasons": reasons, "fields": fields.summary(),
            "files": files.summary(), "disclosure": disclosure,
            "expected_images": expected_images}
