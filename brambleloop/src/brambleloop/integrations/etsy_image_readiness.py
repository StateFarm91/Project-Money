"""Etsy image-upload readiness, verified offline against Etsy's documented constraints (B4).

"Etsy has never confirmed an image upload" is true, and only a real upload under an owner
publication grant can change it. What CAN be settled without calling Etsy is that the exact
requests `EtsyClient.publish` would send for a product's certified image set are the requests
Etsy documents. This module builds those requests with the client's own `_upload_image` (its
validation and its field construction), with `_call` replaced by a recorder so nothing leaves the
process, encodes them with the production `http.multipart_body`, re-parses the bytes with
Python's `email` package (an independent parser), and checks them against:

* **uploadListingImage** (Etsy Open API v3, `POST /v3/application/shops/{shop_id}/listings/
  {listing_id}/images`, multipart/form-data): the binary in a part named `image`; `rank` a
  positive position, rank 1 left-most; `alt_text` "Max length 500 characters"; `overwrite` and
  `is_watermarked` booleans (https://www.etsy.com/openapi/generated/oas/3.0.0.json, read
  2026-10-20; the same document `etsy_constraints.OPENAPI_URL` cites);
* the listing-image rules in `integrations.etsy_constraints` (Help Center 115015663347 and
  115015628707, quoted there): up to 20 photos; .jpg/.gif/.png/.svg/.heic; no animation or
  transparency; first photo >= 635 px and landscape or square; 2000 px recommended; > 1 MB may
  not finish uploading in a browser (API behaviour UNKNOWN).

Severity follows `etsy_constraints._finding`: `fail` breaks a documented rule; `warn` is a
documented recommendation; neither is a substitute for Etsy accepting the bytes.

What only a real upload confirms (owner-gated publication): that Etsy accepts these bytes on
this shop (the API states no size limit), returns a listing_image_id, processes the image
(full_width/height are null until then), stores the alt text verbatim, honours the rank order,
crops the thumbnails acceptably, and lets the draft activate.
"""
from __future__ import annotations

import email
import email.policy
import hashlib

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

OPERATION = "uploadListingImage"
DOC = "https://www.etsy.com/openapi/generated/oas/3.0.0.json#uploadListingImage"
ONLY_A_REAL_UPLOAD_CONFIRMS = (
    "Etsy accepting these bytes on this shop (no API size limit is published)",
    "a listing_image_id returned for each rank",
    "Etsy's asynchronous processing (full_width/full_height are null until it finishes)",
    "alt text stored verbatim and rank order honoured on the listing",
    "the square/portrait/landscape thumbnail crops of the first image",
    "draft activation with the image set attached",
)


class _Recorder:
    """Stands in for `EtsyClient._call`: keeps the request, answers like Etsy's 201 shape."""

    def __init__(self):
        self.requests: list[dict] = []

    def __call__(self, method, path, *, operation, form=None, multipart=None, **_kw):
        from types import SimpleNamespace

        self.requests.append({"method": method, "path": path, "operation": operation,
                              "form": dict(form or {}), "part": multipart})
        return SimpleNamespace(status=201, body={"listing_image_id": len(self.requests)})


def build_requests(images: list) -> tuple[list[dict], list[str]]:
    """The exact uploadListingImage requests `EtsyClient.publish` makes for `images`, in
    rank order, built by the client's own `_upload_image`. Returns (requests, refusals)."""
    from types import SimpleNamespace

    from .etsy import EtsyClient, EtsyRejected

    client = object.__new__(EtsyClient)
    rec = _Recorder()
    client._require = lambda *_a, **_k: SimpleNamespace(shop_id="SHOP")   # type: ignore
    client._call = rec                                                    # type: ignore
    refusals = []
    aligned: list[dict | None] = []
    for rank, entry in enumerate(images or [], start=1):
        name, data = entry[0], entry[1]
        alt = entry[2] if len(entry) > 2 else str(getattr(entry, "alt_text", "") or "")
        before = len(rec.requests)
        try:
            client._upload_image("LISTING", filename=name, data=data, rank=rank, alt_text=alt)
        except EtsyRejected as exc:
            refusals.append(f"rank {rank} ({name}): the client refuses: {exc}"[:300])
        aligned.append(rec.requests[-1] if len(rec.requests) > before else None)
    return aligned, refusals


def parse_request(req: dict) -> dict:
    """Encode with the production encoder and read it back with an independent parser."""
    from .http import multipart_body

    body, ctype = multipart_body(req["part"], req["form"])
    msg = email.message_from_bytes(
        f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body,
        policy=email.policy.HTTP)
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if part.get_filename() is not None:
            files[name] = {"filename": part.get_filename(),
                           "content_type": part.get_content_type(),
                           "data": part.get_payload(decode=True)}
        else:
            fields[name] = part.get_payload(decode=True).decode("utf-8")
    return {"content_type": msg.get_content_type(), "fields": fields, "files": files,
            "bytes": len(body)}


def check_set(images: list) -> dict:
    """PASS only when every request is built, parses back to exactly what was certified and
    breaks no documented `fail` rule. Recommendations are reported as warnings."""
    from . import etsy_constraints as K

    if not images:
        return {"state": FAIL, "why": "no certified image bytes: a draft with no image can "
                "never be activated", "images": [], "warnings": [], "failures": ["no images"]}
    reqs, refusals = build_requests(images)
    failures = list(refusals)
    warnings: list[str] = []
    rows = []
    limit = K.value("listing_images_max")
    if len(images) > limit:
        failures.append(f"{len(images)} images; Etsy allows {limit} photos per listing")
    alt_max = K.value("alt_text_max_chars")
    advice = K.value("alt_text_advice_chars")
    for rank, (entry, req) in enumerate(zip(images, reqs), start=1):
        name, data = entry[0], entry[1]
        alt = entry[2] if len(entry) > 2 else str(getattr(entry, "alt_text", "") or "")
        row = {"rank": rank, "filename": name, "bytes": len(data),
               "sha256": hashlib.sha256(data).hexdigest(), "alt_text_chars": len(alt)}
        probs = []
        if req is None:
            info = K.image_info(data)
            row.update({k: info[k] for k in ("format", "width", "height")})
            row.update(state=FAIL, problems=["the client refused to build this request"])
            rows.append(row)
            continue
        got = parse_request(req)
        part = got["files"].get("image")
        row.update({"method": req["method"], "operation": req["operation"],
                    "path": req["path"].replace("SHOP", "{shop_id}").replace(
                        "LISTING", "{listing_id}")})
        if req["method"] != "POST" or req["operation"] != OPERATION or \
                not req["path"].endswith("/images"):
            probs.append(f"not a POST {OPERATION}: {req['method']} {req['path']}")
        if got["content_type"] != "multipart/form-data":
            probs.append(f"body is {got['content_type']}, not multipart/form-data")
        if part is None:
            probs.append("no part named `image` (Etsy reads the binary from `image`)")
        else:
            if part["data"] != data:
                probs.append("the `image` part's bytes differ from the certified bytes")
            row["content_type"] = part["content_type"]
        if got["fields"].get("rank") != str(rank):
            probs.append(f"rank field {got['fields'].get('rank')!r} != {rank}")
        if (got["fields"].get("alt_text") or "") != alt:
            probs.append("alt_text field differs from the certified alt text")
        if len(alt) > alt_max:
            probs.append(f"alt text {len(alt)} chars > Etsy's {alt_max}")
        if not alt:
            warnings.append(f"rank {rank}: no alt text")
        elif len(alt) > advice:
            warnings.append(f"rank {rank}: alt text {len(alt)} chars > Etsy's advice {advice}")
        info = K.image_info(data)
        row.update({k: info[k] for k in ("format", "width", "height", "transparent",
                                         "animated")})
        for f in K.image_bytes_problems("listing_image", data, position=rank):
            (probs if f["severity"] == "fail" else warnings).append(
                (f"rank {rank}: " if f["severity"] != "fail" else "")
                + f"{f['code']}: {f['detail']}")
        row["state"] = FAIL if probs else PASS
        row["problems"] = probs
        failures.extend(f"rank {rank}: {p}" for p in probs)
        rows.append(row)
    return {"state": FAIL if failures else PASS, "images": rows, "failures": failures,
            "warnings": warnings, "doc": DOC,
            "only_a_real_upload_confirms": list(ONLY_A_REAL_UPLOAD_CONFIRMS),
            "etsy_called": False}


def for_release(db, slug: str, version: str, *, release: str = "", store_root=None) -> dict:
    """`check_set` on exactly the bytes `store.publish` would upload for this release."""
    from ..runtime import etsy_ops

    got = etsy_ops.certified_images(db, slug, version, release=release, store_root=store_root)
    if got["problems"]:
        return {"state": FAIL, "why": "the certified image set is not uploadable",
                "failures": list(got["problems"])[:8], "images": [], "warnings": [],
                "etsy_called": False}
    out = check_set(got["images"])
    out["record_id"] = got.get("record_id")
    return out
