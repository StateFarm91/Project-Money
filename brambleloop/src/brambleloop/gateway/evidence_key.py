"""One fingerprint for every evidence-reuse path (F-311 Cache Certified Evidence).

Paid evidence -- a model's analysis, an image-benchmark trial, a realism verdict about a file,
an observed listing, a paid call's write-ahead intent -- is reused only when the thing it was
about is unchanged. Each path used to hash its own way; three formulas that happened to agree
are one refactor away from two that do not, and a path whose key silently changes either pays
again for evidence it holds or, worse, serves evidence about something else. They all key
through here now. The outputs are byte-identical to the formulas they replace (pinned by
`tests/test_w4_spenda_k5a.py`), so nothing already on file stops matching.

Three shapes, because the evidence comes in three shapes:

* `content(payload)` -- canonical JSON of upstream content (sorted keys, UTF-8, `str` for
  anything else), full SHA-256. Changed content -> different key -> a miss, never a stale hit.
* `material(parts, length)` -- the recipe a measurement was taken under (method version,
  rubric, sample count ...), joined with `|`, truncated SHA-256. A changed method is a miss.
* `file_bytes(path)` -- the exact bytes a verdict was made about; "" when unreadable, which
  every caller treats as "nothing to reuse", never as a match.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

# Every evidence-reuse path and the function that keys it. A test resolves each one and
# checks it goes through this module, so a new path cannot quietly invent its own hash.
REUSE_PATHS: dict[str, str] = {
    "model analysis cache (routing.cached_analysis)": "brambleloop.gateway.routing:fingerprint",
    "paid-call write-ahead intent": "brambleloop.gateway.paid_calls:fingerprint",
    "image benchmark rubric": "brambleloop.gateway.image_bench:rubric_fingerprint",
    "image benchmark trial": "brambleloop.gateway.image_bench:trial_fingerprint",
    "carried portrait realism verdict": "brambleloop.visual.photoreal:_portrait_fingerprint",
    "benchmark observation change detection": "brambleloop.intel.pods:fingerprint",
}


def content(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def material(parts: Iterable[str], length: int = 16) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:length]


def file_bytes(path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""
