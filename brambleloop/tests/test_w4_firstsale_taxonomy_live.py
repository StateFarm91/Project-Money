"""W4-FIRSTSALE B2: verify the category matcher against PRODUCTION's real taxonomy audit row.

A live, read-only verification (one public GET of `/api/audit?action=etsy.taxonomy_refreshed`).
It is not in the offline regression set because its answer depends on what production has
read. Exit codes: 0 = verified, 1 = the real row contradicts the matcher, 3 = UNKNOWN (the row
does not yet carry the evidence, or production is unreachable). UNKNOWN is never PASS.

What it checks, on the newest refresh row:

* `category_choices` (written by a release carrying this branch): every CHOSEN category has
  `path_ids[-1] == taxonomy_id`, as many names as ids, a pattern-named node on its path, and a
  crochet basis that is either the path or an Etsy property id + value id. Exact by id and path
  from the real data; nothing here invents an id.
* `name_evidence` (written by production b931d17 and later): the real pattern-named paths. The
  matcher's root rule (`commerce.category.pattern_roots`) is run on those NAMES to predict
  whether a unique pattern root exists. A prediction is diagnostic only -- it is never a match,
  because names carry no ids.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale_taxonomy_live.py
     (BRAMBLELOOP_PROD_URL overrides the production origin.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import category as C  # noqa: E402

PROD = os.environ.get("BRAMBLELOOP_PROD_URL",
                      "https://brambleloop-os-production.up.railway.app").rstrip("/")
VERIFIED, CONTRADICTED, UNKNOWN = 0, 1, 3


def newest_row(rows: list[dict]) -> dict | None:
    rows = [r for r in rows if r.get("action") == "etsy.taxonomy_refreshed"]
    return max(rows, key=lambda r: r.get("at") or "") if rows else None


def check_choices(choices: dict) -> list[str]:
    """Contradictions in the recorded choices (empty = consistent)."""
    bad = []
    for cat, ch in sorted((choices or {}).items()):
        if ch.get("status") != C.CHOSEN:
            if ch.get("taxonomy_id") is not None:
                bad.append(f"{cat}: {ch.get('status')} but carries id {ch.get('taxonomy_id')}")
            continue
        ids, names = ch.get("path_ids") or [], ch.get("path_names") or []
        if not ids or ids[-1] != ch.get("taxonomy_id"):
            bad.append(f"{cat}: path_ids {ids} do not end at {ch.get('taxonomy_id')}")
        if len(ids) != len(names):
            bad.append(f"{cat}: {len(ids)} ids but {len(names)} names")
        if not any("pattern" in str(n).lower() for n in names):
            bad.append(f"{cat}: no pattern-named node on {names}")
        basis = ch.get("crochet_basis") or {}
        if basis.get("via") == "path":
            if not any("crochet" in str(n).lower() for n in names):
                bad.append(f"{cat}: crochet basis 'path' but no crochet node on {names}")
        elif basis.get("via") == "property":
            if not (isinstance(basis.get("property_id"), int)
                    and isinstance(basis.get("value_id"), int)
                    and str(basis.get("value", "")).lower() == "crochet"):
                bad.append(f"{cat}: property basis without Etsy's ids: {basis}")
        else:
            bad.append(f"{cat}: CHOSEN with no crochet basis")
    return bad


def predict_root(evidence: dict) -> dict:
    """Run the root rule on the real pattern-named PATHS (names only; ids are placeholders
    used for structure and never reported as Etsy's)."""
    paths = [p.split(" > ") for p in evidence.get("pattern_named") or []]
    ids: dict[tuple, int] = {}
    nodes = []
    for path in paths:
        for depth in range(1, len(path) + 1):
            key = tuple(path[:depth])
            if key not in ids:
                ids[key] = len(ids) + 1
                nodes.append({"id": ids[key], "name": key[-1],
                              "path_ids": [ids[key[:d]] for d in range(1, depth + 1)],
                              "path_names": list(key)})
    root, why = C.pattern_root({"nodes": nodes})
    return {"unique_root": " > ".join(root["path_names"]) if root else None, "why": why,
            "pattern_paths": len(paths), "crochet_named": evidence.get("crochet_named") or []}


def verify(rows: list[dict]) -> tuple[int, dict]:
    row = newest_row(rows)
    if row is None:
        return UNKNOWN, {"why": "no etsy.taxonomy_refreshed row"}
    d = row.get("detail") or {}
    out = {"at": row.get("at"), "nodes": d.get("nodes"), "pattern_subtree": d.get("pattern_subtree")}
    if d.get("category_choices") is not None:
        bad = check_choices(d["category_choices"])
        out["choices"] = {c: (v.get("status"), v.get("taxonomy_id"), v.get("path_names"))
                          for c, v in d["category_choices"].items()}
        if bad:
            out["contradictions"] = bad
            return CONTRADICTED, out
        chosen = [c for c, v in d["category_choices"].items() if v.get("status") == C.CHOSEN]
        out["chosen"] = chosen
        return (VERIFIED if chosen else UNKNOWN), out
    if d.get("name_evidence") is not None:
        out["prediction"] = predict_root(d["name_evidence"])
        out["why"] = ("the real names are recorded but this production does not yet record "
                      "category_choices; the match stays UNKNOWN until a release carrying "
                      "W4-FIRSTSALE reads the schemas")
        return UNKNOWN, out
    if (d.get("pattern_subtree") or 0) > 0:
        out["why"] = "a crochet-pattern subtree exists but no choices are recorded"
        return UNKNOWN, out
    out["why"] = "the newest row predates name_evidence (production before b931d17)"
    return UNKNOWN, out


def fetch() -> list[dict]:
    req = urllib.request.Request(f"{PROD}/api/audit?action=etsy.taxonomy_refreshed",
                                 method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:          # noqa: S310 - fixed origin
        return (json.loads(r.read()) or {}).get("audit") or []


def _self_test() -> None:
    """The verifier's own rules, offline (a verifier that passes anything verifies nothing)."""
    good = {"blanket": {"status": "CHOSEN", "taxonomy_id": 5, "path_ids": [1, 5],
                        "path_names": ["Patterns & How To", "Blankets"],
                        "crochet_basis": {"via": "property", "property_id": 9, "value_id": 4,
                                          "value": "Crochet"}}}
    assert check_choices(good) == []
    wrong_end = json.loads(json.dumps(good))
    wrong_end["blanket"]["path_ids"] = [1, 6]
    assert check_choices(wrong_end)
    no_basis = json.loads(json.dumps(good))
    no_basis["blanket"]["crochet_basis"] = None
    assert check_choices(no_basis)
    code, _ = verify([{"action": "etsy.taxonomy_refreshed", "at": "x",
                       "detail": {"nodes": 3065, "pattern_subtree": 0}}])
    assert code == UNKNOWN
    code, out = verify([{"action": "etsy.taxonomy_refreshed", "at": "x", "detail": {
        "name_evidence": {"pattern_named": ["Craft Supplies & Tools > Patterns & How To"],
                          "crochet_named": []}}}])
    assert code == UNKNOWN and out["prediction"]["unique_root"] == \
        "Craft Supplies & Tools > Patterns & How To"
    code, _ = verify([{"action": "etsy.taxonomy_refreshed", "at": "x",
                       "detail": {"category_choices": wrong_end}}])
    assert code == CONTRADICTED


if __name__ == "__main__":
    _self_test()
    print("OK   self-test of the verifier")
    try:
        rows = fetch()
    except Exception as exc:  # noqa: BLE001
        print(f"UNKNOWN production unreachable: {type(exc).__name__}: {exc}"[:400])
        sys.exit(UNKNOWN)
    code, out = verify(rows)
    print({VERIFIED: "VERIFIED", CONTRADICTED: "CONTRADICTED", UNKNOWN: "UNKNOWN"}[code],
          json.dumps(out, default=str)[:3000])
    sys.exit(code)
