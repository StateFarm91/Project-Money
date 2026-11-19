"""Etsy's AI and authorship rules as a deterministic listing check (ENG-ETSY-AI-POLICY, w6).

Etsy Help Center, read through the public article API on 2026-11-19:

* 44297885802647 (edited 2026-11-11): "Sellers must still disclose when an item is created
  using AI and cannot misrepresent AI-generated work as handmade or entirely their own
  creation."
* 115015663347 (edited 2026-11-06): "If you use AI to edit any of your listing photos, note
  whether images were edited in your listing description."

Brambleloop's listing description carries the AI sentences (`platform_policy.DISCLOSURES`),
but nothing refused a description that CLAIMS human authorship or physical evidence the
company does not have ("I designed", "hand-drawn", "tested by crocheters"). The fixed
sentences were a convention, not a guard. `authorship_claim_problems` is that guard. It only
adds a refusal; it never satisfies or relaxes another gate, and it states no answer to
whether Etsy's `who_made` value is true -- that is an owner attestation
(research/final_build/w6/etsy_ai_policy_audit.md, owner exceptions).
"""
from __future__ import annotations

import re

CODE = "AUTHORSHIP_CLAIM"

SOURCES = (
    {"article": "44297885802647", "edited_at": "2026-11-11T14:26:29Z", "read_on": "2026-11-19",
     "quote": ("Sellers must still disclose when an item is created using AI and cannot "
               "misrepresent AI-generated work as handmade or entirely their own creation.")},
    {"article": "115015663347", "edited_at": "2026-11-06T18:10:09Z", "read_on": "2026-11-19",
     "quote": ("If you use AI to edit any of your listing photos, note whether images were "
               "edited in your listing description.")},
)

_CLAIMS = (
    r"hand[- ]?(?:drawn|designed|written|tested)",
    r"(?:designed|written|created|made|tested) (?:entirely |completely )?by "
    r"(?:hand|me|myself|a human|an? (?:independent |experienced |professional )?"
    r"(?:designer|crocheter|maker))",
    r"\bmy (?:own )?(?:original )?(?:design|pattern|sample|swatch)s?\b",
    r"\bi (?:designed|wrote|made|crocheted|tested|stitched|drew)\b",
    r"tested by (?:real |experienced |human )?(?:crocheters|makers|stitchers|testers)",
    r"\bhuman[- ](?:designed|made|written|tested|crafted)",
    r"\b(?:sample|swatch)(?:es)? (?:we|i) (?:crocheted|made|stitched)",
)
_RX = re.compile("|".join(f"(?:{c})" for c in _CLAIMS), re.I)


def authorship_claim_problems(text: str) -> list[str]:
    """Phrases in listing copy that claim human authorship or a made sample."""
    found = sorted({m.group(0).strip().lower() for m in _RX.finditer(text or "")})
    return [f"{CODE}: the listing copy claims {phrase!r}; this pattern is compiled from a "
            f"validated specification with AI assistance and no sample is asserted by the "
            f"copy (Etsy Help 44297885802647: sellers 'cannot misrepresent AI-generated work "
            f"as handmade or entirely their own creation')" for phrase in found]
