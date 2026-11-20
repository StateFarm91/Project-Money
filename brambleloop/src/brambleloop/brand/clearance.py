"""The shop name's knock-out search: recorded evidence, validated in code (W4-LAUNCHFIX D2).

Master Plan v1.2 section 29: "Before commercial launch, perform marketplace/domain/social-handle
screening and appropriate trademark clearance; escalate formal legal clearance to the
owner/professional if needed." OWNER_ACTIONS and `launch.readiness.TRADEMARK_SCREEN` place the
free knock-out search with the company and only the filing decision with the owner.

A knock-out search is a reading of public registers on a date, like the Etsy observations in
`publish.listing_schema.ETSY_VERIFIED_FACTS`, so it is recorded the same way: as a reviewed
entry in this file, with the sources, the queries and every hit, never as a flag. Until an
entry is added `KNOCKOUT_SEARCHES` is empty and `brand_clearance` stays unready. An entry is
only counted when `problems()` finds nothing wrong with it, and only while it is younger than
`MAX_AGE_DAYS`.

Nothing here decides whether a hit is a conflict on anyone's behalf: each hit carries the
searcher's stated relevance and reason, and the owner's sealed decision
(`ops.launch_decisions`) is bound to the digest of exactly the entry they were shown.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

SHOP_NAME = "Brambleloop Studio"

#: A register reading older than this is not a current clearance (marks are filed every day).
MAX_AGE_DAYS = 365

#: The screens section 29 names. Each must be present in an entry, with its source and queries.
REQUIRED_SCREENS: dict[str, str] = {
    "trademark_register_ca": ("the Canadian Trademarks Database (CIPO), the register for this "
                              "company's jurisdiction"),
    "marketplace": "Etsy shop-name and listing search for the name",
    "domain": "the name's domains and any existing site trading under it",
    "social_handles": "the name's handles on the social platforms the company would use",
}

RELEVANCE = ("conflict", "not_a_conflict")

#: Recorded knock-out searches, oldest first. EMPTY: no search has been recorded yet. An entry is
#: {"name", "searched_on" (YYYY-MM-DD), "searched_by", "screens": {screen: {"source" (https URL),
#: "queries": [..], "hits": [{"hit", "relevance" (RELEVANCE), "why"}]}}, "conflicts": [hit, ..],
#: "conclusion"}. `conflicts` must list exactly the hits marked "conflict".
KNOCKOUT_SEARCHES: tuple[dict, ...] = ()


def digest(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def problems(entry: dict, *, today: date | None = None) -> list[str]:
    """Everything that stops `entry` counting as a knock-out search. Empty means it counts."""
    today = today or date.today()
    out: list[str] = []
    if not isinstance(entry, dict):
        return ["the entry is not a mapping"]
    if entry.get("name") != SHOP_NAME:
        out.append(f"name is {entry.get('name')!r}, not the shop name {SHOP_NAME!r}")
    try:
        on = date.fromisoformat(str(entry.get("searched_on")))
        age = (today - on).days
        if age < 0:
            out.append("searched_on is in the future")
        elif age > MAX_AGE_DAYS:
            out.append(f"searched {age} days ago; a clearance older than {MAX_AGE_DAYS} days "
                       f"is not current")
    except ValueError:
        out.append(f"searched_on {entry.get('searched_on')!r} is not an ISO date")
    if not str(entry.get("searched_by") or "").strip():
        out.append("searched_by is empty")
    screens = entry.get("screens") if isinstance(entry.get("screens"), dict) else {}
    marked_conflicts: list = []
    for key in REQUIRED_SCREENS:
        sc = screens.get(key)
        if not isinstance(sc, dict):
            out.append(f"screen {key!r} is missing ({REQUIRED_SCREENS[key]})")
            continue
        if not str(sc.get("source") or "").startswith("https://"):
            out.append(f"screen {key!r} names no https source")
        queries = sc.get("queries") if isinstance(sc.get("queries"), list) else []
        if not any("brambleloop" in str(q).lower() for q in queries):
            out.append(f"screen {key!r} records no query for the name")
        hits = sc.get("hits")
        if not isinstance(hits, list):
            out.append(f"screen {key!r} has no hits list (an empty list is a recorded "
                       f"'no hits'; a missing one is an unrecorded result)")
            continue
        for h in hits:
            if (not isinstance(h, dict) or h.get("relevance") not in RELEVANCE
                    or not str(h.get("why") or "").strip() or not str(h.get("hit") or "")):
                out.append(f"screen {key!r} has a hit without hit/relevance/why")
            elif h["relevance"] == "conflict":
                marked_conflicts.append(h)
    conflicts = entry.get("conflicts")
    if not isinstance(conflicts, list):
        out.append("conflicts is not a list")
    elif digest({"c": conflicts}) != digest({"c": marked_conflicts}):
        out.append("conflicts does not list exactly the hits marked 'conflict'")
    if not str(entry.get("conclusion") or "").strip():
        out.append("conclusion is empty")
    return out


def latest(*, searches: tuple[dict, ...] | None = None, today: date | None = None) -> dict:
    """The newest recorded search and whether it counts. Never falls back to an older one."""
    rows = KNOCKOUT_SEARCHES if searches is None else tuple(searches)
    if not rows:
        return {"state": "NONE", "entry": None, "digest": None,
                "problems": ["no knock-out search is recorded (brand.clearance."
                             "KNOCKOUT_SEARCHES is empty); it is company work"]}
    entry = rows[-1]
    found = problems(entry, today=today)
    return {"state": "INVALID" if found else "VALID", "entry": entry,
            "digest": digest(entry), "problems": found}
