"""A urllib transport for Etsy. Standard library only.

Deliberately small and deliberately separate from the client. The client's refusals decide
whether a request may happen at all; this only knows how to make one.

**Encoding is per endpoint, and that is Etsy's decision, not a house style.** Read from
Etsy's own published API description on 2026-09-25 (`ETSY_OPENAPI_URL` in
`publish/listing_schema.py`, document version 3.0.0):

| Operation | The only media type Etsy lists |
|---|---|
| `createDraftListing`, `updateListing` | `application/x-www-form-urlencoded` |
| `uploadListingImage`, `uploadListingFile` | `multipart/form-data` |
| `updateListingInventory` | `application/json` |
| the OAuth token endpoint | form-encoded, per RFC 6749 section 4.1.3 |

So a transport with one body format is wrong for Etsy whichever format it picks. This one
carries three body channels and sets the Content-Type from the channel the caller used,
which means the header can no longer disagree with the bytes. The previous version of this
file serialised everything with `json.dumps` and announced `application/json`; the two write
endpoints this company depends on do not accept that media type.

What is exercised and what is not, as of 2026-09-25:

- Reaching Etsy: **exercised.** `probe_live()` makes a real request to Etsy's `openapi-ping`
  and Etsy answers. TLS through this environment's proxy, the error body and the status all
  come back as this module expects.
- The *encodings*: exercised against a local server that parses them with an independent
  parser (`tests/fake_etsy.py`), and **never against Etsy**, because Etsy refuses on the API
  key before it looks at a body, so no unauthenticated request can teach us anything about
  body handling. A parseable body is not a proof that Etsy accepts it.
"""
from __future__ import annotations

import json as jsonlib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from .etsy import FilePart, Response

TIMEOUT_SECONDS = 30

# Etsy's ping endpoint. Root-level security in Etsy's document is `[{'api_key': []}]`, so
# this needs a keystring and nothing else -- no OAuth token, no shop, no scope. It is the
# only Etsy endpoint this system can touch with no credentials at all, and what it proves is
# reachability, not authorisation.
PING_URL = "https://openapi.etsy.com/v3/application/openapi-ping"


def form_body(fields: dict[str, Any]) -> bytes:
    """Encode `application/x-www-form-urlencoded`, the way Etsy's two write endpoints want it.

    Booleans become `true`/`false` rather than Python's `True`/`False`, which Etsy's parser
    would read as a string and not as a boolean. Lists arrive already flattened by the
    caller: how Etsy wants an array in a form body is an open question recorded in
    `etsy.ARRAY_ENCODING`, and it is not a question a byte-level encoder should answer.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in fields.items():
        if isinstance(value, bool):
            pairs.append((key, "true" if value else "false"))
        elif value is None:
            continue
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs).encode("utf-8")


def multipart_body(part: FilePart,
                   fields: dict[str, Any] | None = None) -> tuple[bytes, str]:
    """Encode `multipart/form-data` and return the body with the Content-Type to send.

    The file's field name is a parameter rather than a constant because Etsy's two upload
    endpoints disagree about it: `uploadListingImage` reads the binary from a part named
    `image` ("To upload a new image, set the image file as the value for the `image`
    parameter") and `uploadListingFile` from one named `file`. A single hard-coded `file`
    part -- which is what this module used to send -- uploads a listing image that Etsy will
    not see.
    """
    boundary = f"----brambleloop{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in (fields or {}).items():
        rendered = "true" if value is True else "false" if value is False else str(value)
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{_escape(key)}"\r\n\r\n'
            f"{rendered}\r\n".encode("utf-8"))
    chunks.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{_escape(part.field)}"; '
        f'filename="{_escape(part.filename)}"\r\n'
        f"Content-Type: {part.content_type}\r\n\r\n".encode("utf-8"))
    chunks.append(part.data)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _escape(value: str) -> str:
    """Quote-escape a multipart field or file name.

    A filename containing a double quote would otherwise end the header's quoted string and
    the rest of the name would be read as more header parameters. Our filenames come from
    pattern slugs, so this has never happened; it is one line and the failure it prevents is
    a corrupt upload rather than an error.
    """
    return (value.replace("\\", "\\\\").replace('"', '\\"')
                 .replace("\r", "").replace("\n", ""))


class UrllibTransport:
    """One request, one response, no retries: retrying is the caller's policy decision.

    Exactly one body channel may be used per request. Sending two would mean the
    Content-Type describes one of them, which is the defect this class exists to remove.
    """

    def request(self, method: str, url: str, *, headers: dict[str, str],
                json: dict | None = None,
                form: dict | None = None,
                multipart: FilePart | None = None,
                timeout: float = TIMEOUT_SECONDS) -> Response:
        if multipart is None:
            channels = [name for name, value in (("json", json), ("form", form))
                        if value is not None]
            if len(channels) > 1:
                raise ValueError(
                    f"a request has one body; got {channels}. The Content-Type can only "
                    f"describe one of them.")
        elif json is not None:
            raise ValueError("multipart and json are two bodies; multipart carries its text "
                             "parts in `form`.")

        send = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        body: bytes | None = None

        if multipart is not None:
            body, content_type = multipart_body(multipart, form)
            send["Content-Type"] = content_type
        elif form is not None:
            body = form_body(form)
            send["Content-Type"] = "application/x-www-form-urlencoded"
        elif json is not None:
            body = jsonlib.dumps(json).encode("utf-8")
            send["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=body, headers=send, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return Response(status=response.status, body=_parse(raw),
                                headers=dict(response.headers))
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            return Response(status=e.code, body=_parse(raw), headers=dict(e.headers or {}))
        except urllib.error.URLError as e:
            # A transport failure is not a response. Reported as a 503 so the client's own
            # classification decides whether it is worth retrying, rather than this module
            # inventing a policy.
            return Response(status=503, body={"error": f"transport failure: {e.reason}"})


def _parse(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        parsed = jsonlib.loads(raw.decode())
    except (ValueError, UnicodeDecodeError):
        return {"error": raw[:400].decode(errors="replace")}
    return parsed if isinstance(parsed, dict) else {"body": parsed}


def probe_live(api_key_header: str = "", transport: Any | None = None) -> dict:
    """Ask Etsy's ping endpoint whether we can reach it, and report what came back.

    This is the one call this system can make to Etsy with no credentials, so it is the one
    piece of live evidence available before the owner authorises an app. It creates nothing,
    changes nothing and costs CA$0.

    What it measures: that Etsy is reachable from this environment through its proxy, that
    the response parses, and what Etsy says about the `x-api-key` header -- which is how the
    keystring:shared_secret format claim in `Credentials.api_key_header` gets checked by
    Etsy rather than by us reading Etsy's document about itself.
    """
    transport = transport or UrllibTransport()
    headers = {"x-api-key": api_key_header} if api_key_header else {}
    response = transport.request("GET", PING_URL, headers=headers)
    return {"url": PING_URL,
            "sent_api_key_header": bool(api_key_header),
            "status": response.status,
            "body": response.body,
            "reachable": response.status != 503,
            "authenticated": response.status == 200}
