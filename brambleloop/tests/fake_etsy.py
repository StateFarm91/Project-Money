"""A local HTTP server that behaves like Etsy's documented contract, and nothing more.

**Read this before trusting anything a test using it proves.** This is a model of Etsy built
from Etsy's own published API description, read on 2026-09-25. It is not Etsy. A test that
passes against it has established that:

- our bytes are parseable by an independent parser -- form bodies by `urllib.parse.parse_qsl`
  and multipart bodies by Python's `email` package, neither of which is our encoder;
- our client sends the media type each endpoint documents, because this server returns 415
  when it does not;
- our client puts the image binary in a part named `image` and the digital file in one named
  `file`, because this server looks for those names and 400s otherwise;
- our read-back verification detects a field the server ignored, transformed or renamed;
- our OAuth refresh spends a refresh token, receives a rotated one and retries the call.

It has not established that Etsy does any of these things. Where the fidelity is real it is
because Etsy's own strings are used: the two API-key error messages below are the exact
responses `openapi.etsy.com` returned to this environment on 2026-09-25, observed rather than
imagined.

It lives in `tests/` on purpose. Nothing in `src/` may import it, so no production code path
can ever be pointed at a server that agrees with us.
"""
from __future__ import annotations

import email
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Observed from the real API on 2026-09-25, unauthenticated GET to
# https://openapi.etsy.com/v3/application/openapi-ping:
MALFORMED_KEY = "Invalid API key: should be in the format 'keystring:shared_secret'."
UNKNOWN_KEY = "API key not found or not active, or incorrect shared secret for API key."

# From Etsy's createDraftListing request schema.
CREATE_REQUIRED = ("quantity", "title", "description", "price", "who_made", "when_made",
                   "taxonomy_id")
ENUMS = {
    "who_made": ("i_did", "someone_else", "collective"),
    "type": ("physical", "download", "both"),
    "when_made": ("made_to_order", "2020_2026", "2010_2019", "2007_2009", "before_2007",
                  "2000_2006", "1990s", "1980s", "1970s", "1960s", "1950s", "1940s", "1930s",
                  "1920s", "1910s", "1900s", "1800s", "1700s", "before_1700"),
}
# From updateListing's schema. `price` is deliberately absent: Etsy has no price property on
# this operation, and this server therefore ignores one exactly as an unknown field, which is
# the behaviour read-back verification exists to catch.
UPDATE_WRITABLE = ("image_ids", "title", "description", "materials", "should_auto_renew",
                   "shop_section_id", "is_taxable", "taxonomy_id", "tags", "who_made",
                   "when_made", "featured_rank", "state", "is_supply", "type")
DELETABLE_STATES = ("draft", "inactive", "expired", "sold_out", "active")


class FakeEtsy:
    """Runs the server on a loopback port for the life of a `with` block."""

    def __init__(self, *, keystring: str = "fakekeystring",
                 shared_secret: str = "fakesharedsecret",
                 shop_id: str = "12345",
                 scopes: tuple[str, ...] = ("listings_r", "listings_w", "listings_d",
                                            "shops_r", "shops_w"),
                 access_token_seconds: float = 3600.0,
                 tags_are_repeated_keys: bool = False,
                 taxonomy_nodes: tuple[dict[str, Any], ...] | None = None,
                 required_property: dict[str, Any] | None = None,
                 remap_taxonomy_to: int | None = None,
                 image_failure: tuple[int, str] | None = None,
                 delete_failure: tuple[int, str] | None = None,
                 delete_is_soft: bool = False,
                 echo_token_in_error: bool = False) -> None:
        self.keystring = keystring
        self.shared_secret = shared_secret
        self.shop_id = str(shop_id)
        self.scopes = scopes
        self.access_token_seconds = access_token_seconds
        # -- the knobs that make the failure taxonomy executable ------------
        # Each one produces the signature of one entry in `etsy_probe.TAXONOMY`, so the
        # classification is run rather than described. None of them makes this server more
        # like Etsy: they make it like the *other* readings of Etsy's document, which is the
        # only honest thing a model can be when the document is ambiguous.
        #
        # Etsy reads `tags=a&tags=b` and treats a comma-joined value as one tag. This is the
        # other half of the ambiguity in ETSY_TRANSPORT.md 3.3, and note that it produces no
        # error at all: the listing is created, 201, with one wrong tag.
        self.tags_are_repeated_keys = tags_are_repeated_keys
        self.taxonomy_nodes = taxonomy_nodes if taxonomy_nodes is not None else (
            {"id": 1, "name": "Craft Supplies & Tools", "level": 1, "children": [
                {"id": 66, "name": "Patterns", "level": 2, "children": []},
                {"id": 67, "name": "Patterns & Blueprints", "level": 2, "children": []},
            ]},
        )
        self.required_property = required_property
        self.remap_taxonomy_to = remap_taxonomy_to
        self.image_failure = image_failure
        self.delete_failure = delete_failure
        self.delete_is_soft = delete_is_soft
        # When true, an error body carries a token-shaped string, which is how a real API
        # leaks one: inside prose nobody predicted. The redaction test uses it.
        self.echo_token_in_error = echo_token_in_error
        self.listings: dict[str, dict[str, Any]] = {}
        self.images: dict[str, list[dict[str, Any]]] = {}
        self.requests: list[dict[str, Any]] = []
        self.token_requests: list[dict[str, Any]] = []
        self.next_id = 700000001
        # token -> (expires_at, scopes). Start with one live token and one already dead, so a
        # test can choose which failure it is provoking.
        self.tokens: dict[str, tuple[float, tuple[str, ...]]] = {
            "111.live-token": (time.time() + access_token_seconds, scopes),
            "111.dead-token": (time.time() - 1.0, scopes),
        }
        self.refresh_tokens: dict[str, tuple[str, ...]] = {"111.refresh-one": scopes}
        self.refreshes = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "FakeEtsy":
        outer = self

        class Handler(_Handler):
            fake = outer

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    @property
    def root(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def base(self) -> str:
        return f"{self.root}/v3/application"

    @property
    def token_url(self) -> str:
        return f"{self.root}/v3/public/oauth/token"

    def api_key_header(self) -> str:
        return f"{self.keystring}:{self.shared_secret}"

    def expire_all_access_tokens(self) -> None:
        """Make every issued access token dead, as an hour of wall-clock time would."""
        self.tokens = {t: (time.time() - 1.0, s) for t, (_, s) in self.tokens.items()}

    # -- the listing store -------------------------------------------------

    def array(self, key: str, value: str, repeated: Any = ()) -> list[str]:
        """Read a form array the way this server's configured reading of Etsy reads it.

        With `tags_are_repeated_keys` false -- the default, and the reading this system
        currently sends -- a comma splits, so `tags=a,b` and `tags=a&tags=b` are the same two
        tags. With it true, only repeated keys are separate values and a comma-joined string
        is **one tag containing a comma**: accepted, stored, 201 returned, and nothing on the
        wire says anything is wrong. That silent outcome is the reason the run reads tags back
        instead of trusting the status.
        """
        if not self.tags_are_repeated_keys or key in (repeated or ()):
            return _split(value)
        return [value] if value else []

    def _new_listing(self, fields: dict[str, str],
                     repeated: Any = ()) -> dict[str, Any]:
        listing_id = str(self.next_id)
        self.next_id += 1
        price = float(fields.get("price", "0") or 0)
        taxonomy = int(float(fields.get("taxonomy_id", "0") or 0))
        if self.remap_taxonomy_to is not None:
            # Etsy silently remaps a deprecated node. No error, no warning, and the listing
            # is in a category nobody chose.
            taxonomy = self.remap_taxonomy_to
        record = {
            "listing_id": int(listing_id),
            "shop_id": int(self.shop_id),
            "state": "draft",
            "title": fields.get("title", ""),
            "description": fields.get("description", ""),
            "quantity": int(float(fields.get("quantity", "0") or 0)),
            # Etsy returns a Money object, not the decimal that was sent.
            "price": {"amount": int(round(price * 100)), "divisor": 100,
                      "currency_code": "CAD"},
            "tags": self.array("tags", fields.get("tags", ""), repeated),
            "materials": self.array("materials", fields.get("materials", ""), repeated),
            "taxonomy_id": taxonomy,
            # Etsy renames `type` to `listing_type` on the way back.
            "listing_type": fields.get("type", "physical"),
            "who_made": fields.get("who_made", ""),
            "when_made": fields.get("when_made", ""),
            "is_supply": fields.get("is_supply", "false") == "true",
            "file_data": "",
            "url": f"https://www.etsy.com/listing/{listing_id}/",
        }
        self.listings[listing_id] = record
        self.images[listing_id] = []
        return record


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class _Handler(BaseHTTPRequestHandler):
    fake: FakeEtsy
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:   # keep the test output readable
        return

    # -- plumbing ----------------------------------------------------------

    def _send(self, status: int, body: dict | None = None) -> None:
        raw = json.dumps(body or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _check_key(self) -> dict | None:
        """Etsy's api_key check, with Etsy's own two messages and Etsy's own status."""
        key = self.headers.get("x-api-key", "")
        if ":" not in key:
            return {"status": 403, "error": MALFORMED_KEY}
        if key != self.fake.api_key_header():
            return {"status": 403, "error": UNKNOWN_KEY}
        return None

    def _check_token(self, needs: tuple[str, ...]) -> dict | None:
        if not needs:
            return None
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return {"status": 401, "error": "missing bearer token"}
        token = auth[len("Bearer "):]
        known = self.fake.tokens.get(token)
        if known is None:
            return {"status": 401, "error": "invalid_token"}
        expires_at, scopes = known
        if time.time() >= expires_at:
            # What an hour-old access token looks like. The whole reason refresh exists.
            return {"status": 401, "error": "invalid_token: access token expired"}
        missing = [s for s in needs if s not in scopes]
        if missing:
            return {"status": 403, "error": f"insufficient scope; missing {missing}"}
        return None

    def _guard(self, needs: tuple[str, ...]) -> bool:
        problem = self._check_key() or self._check_token(needs)
        if problem is None:
            return True
        self._send(problem["status"], {"error": problem["error"]})
        return False

    def _form(self) -> dict[str, str] | None:
        """Parse a form-encoded body, or answer 415 the way a typed endpoint must.

        The Content-Type check is the point of this method. Etsy lists
        `application/x-www-form-urlencoded` as the only media type for its two listing write
        operations; a client that sends JSON gets a body this server will not read.

        Repeated keys are joined with a comma rather than dropped, so that
        `tags=a&tags=b` and `tags=a,b` arrive as the same string. Which of those Etsy means
        is the open question; how this server *stores* them is where the two readings differ,
        and that is decided in `_new_listing` from `tags_are_repeated_keys`. Parsing them
        identically here is deliberate: a parser that silently kept only the last value would
        hide the repeated-key encoding rather than model it.
        """
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        raw = self._read_body()
        if content_type != "application/x-www-form-urlencoded":
            self._send(415, {"error": f"Unsupported Media Type: {content_type!r}. This "
                                      f"endpoint accepts application/x-www-form-urlencoded."})
            return None
        out: dict[str, str] = {}
        self.repeated: set[str] = set()
        for key, value in urllib.parse.parse_qsl(raw.decode(), keep_blank_values=True):
            if key in out:
                self.repeated.add(key)
                out[key] = f"{out[key]},{value}"
            else:
                out[key] = value
        return out

    def _multipart(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]] | None:
        """Parse a multipart body with Python's `email` parser -- not with our encoder."""
        content_type = self.headers.get("Content-Type") or ""
        if not content_type.startswith("multipart/form-data"):
            self._send(415, {"error": f"Unsupported Media Type: {content_type!r}. This "
                                      f"endpoint accepts multipart/form-data."})
            return None
        raw = self._read_body()
        message = email.message_from_bytes(
            b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        text: dict[str, str] = {}
        files: dict[str, tuple[str, bytes]] = {}
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            name = part.get_param("name", header="content-disposition")
            filename = part.get_param("filename", header="content-disposition")
            payload = part.get_payload(decode=True) or b""
            if filename:
                files[str(name)] = (str(filename), payload)
            else:
                text[str(name)] = payload.decode(errors="replace")
        return text, files

    def _record(self, operation: str) -> None:
        self.fake.requests.append({
            "operation": operation, "method": self.command, "path": self.path,
            "content_type": (self.headers.get("Content-Type") or "").split(";")[0],
        })

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:   # noqa: N802
        path, _, query = self.path.partition("?")
        parts = [p for p in path.strip("/").split("/") if p]
        params = dict(urllib.parse.parse_qsl(query))
        fake = self.fake

        if path == "/v3/application/openapi-ping":
            self._record("ping")
            if not self._guard(()):
                return
            return self._send(200, {"application_id": 1})

        # GET /v3/application/shops/{shop_id}/listings?state=draft -- the sweep's read.
        if len(parts) == 5 and parts[2] == "shops" and parts[4] == "listings":
            self._record("getListingsByShop")
            if not self._guard(("listings_r",)):
                return
            state = params.get("state", "")
            results = [dict(r) for r in fake.listings.values()
                       if not state or r.get("state") == state]
            return self._send(200, {"count": len(results), "results": results})

        # GET /v3/application/seller-taxonomy/nodes -- the whole tree, as Etsy returns it.
        if path == "/v3/application/seller-taxonomy/nodes":
            self._record("getSellerTaxonomyNodes")
            if not self._guard(()):
                return
            return self._send(200, {"count": len(fake.taxonomy_nodes),
                                    "results": [dict(n) for n in fake.taxonomy_nodes]})

        # GET /v3/application/seller-taxonomy/nodes/{id}/properties
        if len(parts) == 6 and parts[2] == "seller-taxonomy" and parts[5] == "properties":
            self._record("getPropertiesByTaxonomyId")
            if not self._guard(()):
                return
            required = ([{**fake.required_property, "is_required": True}]
                        if fake.required_property is not None else [])
            return self._send(200, {"count": len(required), "results": required})

        if len(parts) == 4 and parts[2] == "shops":
            self._record("getShop")
            if not self._guard(()):
                return
            if parts[3] != fake.shop_id:
                return self._send(404, {"error": "Shop not found."})
            return self._send(200, {"shop_id": int(fake.shop_id),
                                    "shop_name": "FakeShopForTests",
                                    "is_vacation": False, "currency_code": "CAD"})

        if path == "/v3/application/users/me":
            self._record("getMe")
            if not self._guard(("shops_r",)):
                return
            return self._send(200, {"user_id": 111, "shop_id": int(fake.shop_id)})

        if len(parts) == 4 and parts[2] == "listings":
            self._record("getListing")
            if not self._guard(()):
                return
            record = fake.listings.get(parts[3])
            if record is None:
                return self._send(404, {"error": "Listing not found."})
            body = dict(record)
            if "Images" in params.get("includes", ""):
                body["images"] = list(fake.images.get(parts[3], []))
            return self._send(200, body)

        if len(parts) == 5 and parts[2] == "listings" and parts[4] == "images":
            self._record("getListingImages")
            if not self._guard(()):
                return
            return self._send(200, {"count": len(fake.images.get(parts[3], [])),
                                    "results": list(fake.images.get(parts[3], []))})

        self._send(404, {"error": f"no such endpoint: {path}"})

    def do_POST(self) -> None:   # noqa: N802
        path = self.path.partition("?")[0]
        parts = [p for p in path.strip("/").split("/") if p]
        fake = self.fake

        if path == "/v3/public/oauth/token":
            return self._oauth_token()

        # POST /v3/application/shops/{shop_id}/listings
        if len(parts) == 5 and parts[2] == "shops" and parts[4] == "listings":
            self._record("createDraftListing")
            if not self._guard(("listings_w",)):
                return
            fields = self._form()
            if fields is None:
                return
            missing = [f for f in CREATE_REQUIRED if not fields.get(f)]
            if missing:
                return self._send(400, {"error": f"Required parameters missing: {missing}"})
            if "state" in fields:
                # createDraftListing has no state property. A real Etsy would ignore it; this
                # server refuses, because a client that sends it is relying on a field that is
                # not in the contract.
                return self._send(400, {"error": "createDraftListing has no state parameter."})
            for key, allowed in ENUMS.items():
                if key in fields and fields[key] not in allowed:
                    return self._send(400, {"error": f"{key} must be one of {list(allowed)}"})
            if fake.required_property is not None:
                # What a taxonomy node with a required listing property does to every single
                # create against it. The message names the property id, which is the only
                # thing that makes the failure actionable.
                return self._send(400, {
                    "error": f"Required listing property missing for this taxonomy: "
                             f"property_id {fake.required_property.get('property_id')} "
                             f"({fake.required_property.get('name')})."})
            return self._send(201, fake._new_listing(fields, getattr(self, "repeated", ())))

        # POST /v3/application/shops/{shop_id}/listings/{listing_id}/images
        if len(parts) == 7 and parts[6] == "images":
            self._record("uploadListingImage")
            if not self._guard(("listings_w",)):
                return
            parsed = self._multipart()
            if parsed is None:
                return
            text, files = parsed
            listing_id = parts[5]
            if listing_id not in fake.listings:
                return self._send(404, {"error": "Listing not found."})
            if "image" not in files:
                # The exact failure the old transport would have produced: a well-formed
                # multipart request with the binary in a part named `file`.
                return self._send(
                    400, {"error": f"No image supplied. This endpoint reads the binary from a "
                                   f"part named 'image'; parts received: {sorted(files)}."})
            filename, data = files["image"]
            if not data:
                return self._send(400, {"error": "Empty image."})
            if not data.startswith(b"\x89PNG") and not data.startswith(b"\xff\xd8"):
                return self._send(400, {"error": "Unsupported image format."})
            if fake.image_failure is not None:
                # Etsy's image rules are on help.etsy.com, which refuses automated readers, so
                # this server cannot model them -- it can only be told to refuse. A test uses
                # it to exercise the `image_too_small` path, whose whole point is that a
                # refusal there is a finding about the fixture and not about the transport.
                status, message = fake.image_failure
                return self._send(status, {"error": message})
            image = {"listing_image_id": 900000 + len(fake.images[listing_id]) + 1,
                     "listing_id": int(listing_id),
                     "rank": int(float(text.get("rank", "1") or 1)),
                     "alt_text": text.get("alt_text", ""),
                     "full_height": 1, "full_width": 1}
            fake.images[listing_id].append(image)
            return self._send(201, image)

        # POST /v3/application/shops/{shop_id}/listings/{listing_id}/files
        if len(parts) == 7 and parts[6] == "files":
            self._record("uploadListingFile")
            if not self._guard(("listings_w",)):
                return
            parsed = self._multipart()
            if parsed is None:
                return
            text, files = parsed
            listing_id = parts[5]
            if listing_id not in fake.listings:
                return self._send(404, {"error": "Listing not found."})
            if "file" not in files:
                return self._send(400, {"error": f"No file supplied; parts received: "
                                                 f"{sorted(files)}."})
            filename, data = files["file"]
            fake.listings[listing_id]["file_data"] = filename
            return self._send(201, {"listing_file_id": 800001, "listing_id": int(listing_id),
                                    "filename": filename, "filesize": str(len(data))})

        self._send(404, {"error": f"no such endpoint: {path}"})

    def do_PATCH(self) -> None:   # noqa: N802
        path = self.path.partition("?")[0]
        parts = [p for p in path.strip("/").split("/") if p]
        fake = self.fake

        # PATCH /v3/application/shops/{shop_id}/listings/{listing_id}
        if len(parts) == 6 and parts[2] == "shops" and parts[4] == "listings":
            self._record("updateListing")
            if not self._guard(("listings_w",)):
                return
            fields = self._form()
            if fields is None:
                return
            listing_id = parts[5]
            record = fake.listings.get(listing_id)
            if record is None:
                return self._send(404, {"error": "Listing not found."})
            ignored = [k for k in fields if k not in UPDATE_WRITABLE]
            for key, value in fields.items():
                if key in ignored:
                    # Silently ignored, exactly as an unknown form field is. This is the
                    # behaviour that makes read-back verification necessary rather than nice.
                    continue
                if key == "state":
                    if value == "active" and not fake.images.get(listing_id):
                        return self._send(
                            400, {"error": "Listings must have at least one image to be "
                                           "activated."})
                    if value not in ("active", "inactive"):
                        return self._send(400, {"error": "state must be active or inactive"})
                    record["state"] = value
                elif key in ("tags", "materials"):
                    record[key] = fake.array(key, value, getattr(self, "repeated", ()))
                elif key == "type":
                    record["listing_type"] = value
                elif key in ("taxonomy_id", "featured_rank", "shop_section_id"):
                    record[key] = int(float(value))
                elif key in ("is_supply", "is_taxable", "should_auto_renew"):
                    record[key] = value == "true"
                else:
                    record[key] = value
            body = dict(record)
            if ignored:
                body["_fake_ignored_fields"] = sorted(ignored)
            return self._send(200, body)

        self._send(404, {"error": f"no such endpoint: {path}"})

    def do_DELETE(self) -> None:   # noqa: N802
        path = self.path.partition("?")[0]
        parts = [p for p in path.strip("/").split("/") if p]
        fake = self.fake

        if len(parts) == 4 and parts[2] == "listings":
            self._record("deleteListing")
            if not self._guard(("listings_d",)):
                return
            record = fake.listings.get(parts[3])
            if record is None:
                return self._send(404, {"error": "Listing not found."})
            if record["state"] not in DELETABLE_STATES:
                return self._send(409, {"error": f"cannot delete a listing in state "
                                                 f"{record['state']}"})
            if fake.delete_failure is not None:
                status, message = fake.delete_failure
                if fake.echo_token_in_error:
                    # How a token really leaks: inside prose, in a field nobody predicted,
                    # from a server that had no business repeating it. Redaction that only
                    # looked at known key names would pass this straight into the report.
                    message = (f"{message} (request was authorised as "
                               f"{self.headers.get('Authorization', '')})")
                return self._send(status, {"error": message})
            if fake.delete_is_soft:
                # Etsy accepts the deletion and keeps the record in a terminal state. The 204
                # is honest about the request and says nothing about the listing.
                record["state"] = "removed"
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            fake.listings.pop(parts[3])
            fake.images.pop(parts[3], None)
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self._send(404, {"error": f"no such endpoint: {path}"})

    # -- OAuth -------------------------------------------------------------

    def _oauth_token(self) -> None:
        """Etsy's token endpoint: form-encoded in, JSON out, refresh token rotated.

        The rotation matters. Etsy returns a new refresh token on every refresh and the old
        one is spent, so a client that refreshes and does not persist the new one works until
        it restarts. This server enforces that by forgetting the spent token, which turns a
        silent future failure into a test that fails now.
        """
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        raw = self._read_body()
        if content_type != "application/x-www-form-urlencoded":
            return self._send(415, {"error": "the token endpoint takes "
                                             "application/x-www-form-urlencoded"})
        form = dict(urllib.parse.parse_qsl(raw.decode()))
        self.fake.token_requests.append({k: ("***" if "token" in k else v)
                                         for k, v in form.items()})
        if form.get("client_id") != self.fake.keystring:
            return self._send(400, {"error": "invalid_client",
                                    "error_description": "unknown client_id"})
        grant = form.get("grant_type")
        if grant != "refresh_token":
            return self._send(400, {"error": "unsupported_grant_type",
                                    "error_description": f"this fake implements the refresh "
                                                         f"grant only; got {grant!r}"})
        presented = form.get("refresh_token", "")
        scopes = self.fake.refresh_tokens.pop(presented, None)
        if scopes is None:
            return self._send(400, {"error": "invalid_grant",
                                    "error_description": "refresh token unknown, spent or "
                                                         "expired"})
        self.fake.refreshes += 1
        access = f"111.access-{self.fake.refreshes}"
        rotated = f"111.refresh-{self.fake.refreshes + 1}"
        self.fake.tokens[access] = (time.time() + self.fake.access_token_seconds, scopes)
        self.fake.refresh_tokens[rotated] = scopes
        return self._send(200, {"access_token": access, "token_type": "Bearer",
                                "expires_in": int(self.fake.access_token_seconds),
                                "refresh_token": rotated, "scope": " ".join(scopes)})
