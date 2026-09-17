"""A urllib transport for the Etsy client. Standard library only.

Deliberately small and deliberately separate from the client. The client's refusals decide
whether a request may happen at all; this only knows how to make one. Nothing in this
environment can get past those refusals, so this code has never run against Etsy -- which is
exactly why it contains no cleverness to be wrong about.
"""
from __future__ import annotations

import json as jsonlib
import urllib.error
import urllib.request
import uuid

from .etsy import Response

TIMEOUT_SECONDS = 30


class UrllibTransport:
    """One request, one response, no retries: retrying is the caller's policy decision."""

    def request(self, method: str, url: str, *, headers: dict[str, str],
                json: dict | None = None,
                file: tuple[str, bytes] | None = None) -> Response:
        body: bytes | None = None
        send = dict(headers)

        if file is not None:
            boundary = f"----brambleloop{uuid.uuid4().hex}"
            filename, data = file
            parts: list[bytes] = []
            for key, value in (json or {}).items():
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n"
                    f"\r\n{value}\r\n".encode())
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"{filename}\"\r\n"
                f"Content-Type: application/pdf\r\n\r\n".encode())
            parts.append(data)
            parts.append(f"\r\n--{boundary}--\r\n".encode())
            body = b"".join(parts)
            send["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif json is not None:
            body = jsonlib.dumps(json).encode()
            send.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(url, data=body, headers=send, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
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
