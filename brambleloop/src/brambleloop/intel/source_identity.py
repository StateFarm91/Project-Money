"""Canonical marketplace identifiers used in evidence attribution."""
import re


def marketplace_shop_id(value) -> str:
    """Positive ASCII decimal ID, with equivalent zero-padded forms collapsed."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    text = str(value).strip()
    if len(text) > 32 or re.fullmatch(r"[0-9]+", text) is None:
        return ""
    return text.lstrip("0")
