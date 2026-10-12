"""Deterministic parser: Final Master v1.0 text -> machine-readable requirement registry.

Input:  research/final_build/master_v1.0.txt (pypdf extraction of
        spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf, sha256 526ed69c...)
Output: research/final_build/master_registry.json

The parser never invents a requirement: every record carries the source line numbers
it was read from, and the ID-space accounting (gaps, collisions) is computed, not typed.
Run: python3 research/final_build/parse_master.py
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "master_v1.0.txt"
OUT = HERE / "master_registry.json"

# Addendum start lines, read from the document's own version headers/notes.
VERSIONS = [
    (1, "v0.1"), (296, "v0.2"), (470, "v0.3"), (616, "v0.4"), (857, "v0.5"),
    (1020, "v0.6"), (1116, "v0.7"), (1220, "v0.8"), (1552, "v0.9"), (1732, "v0.10"),
    (1866, "v0.11"), (1984, "v0.12"), (2152, "v0.13"), (2448, "v0.14"), (2705, "v0.15"),
    (2879, "v0.16"), (3108, "v0.17"), (3385, "v0.18"), (3590, "v0.19"), (3724, "v0.20"),
    (3826, "v0.21"), (3898, "v0.22"), (4060, "v0.23"), (4116, "v0.24"), (4237, "v1.0"),
]


def expand(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


# Source-stated priority (verbatim sources cited per entry).
MASTER_PRIORITY = {}
for n in expand("1-15,20-31,39-43,48-49,52,58-60"):
    MASTER_PRIORITY[n] = ("P0-before-launch", "master line 274 (v0.1 s5)")
for n in expand("32-38,44-45,50-51,53-57"):
    MASTER_PRIORITY[n] = ("P1-after-real-traffic", "master line 275 (v0.1 s5)")
ADDENDUM_PRIORITY = {
    "v0.8": ("addendum-P0-launch-critical", "master line 1222"),
    "v0.9": ("addendum-P0-launch-critical", "master line 1554"),
    "v0.10": ("addendum-P0-launch-critical", "master line 1734"),
}

# Explicit supersession language in the document.
SUPERSESSIONS = [
    {"superseding": "F-789..F-798", "superseded": "F-781..F-788",
     "scope": "where conflicting", "source": "master lines 4061-4070 (v0.23 s78-79)",
     "effect": "Private full reverse-engineering of purchased patterns is allowed; the "
               "publishable-output boundary (no protected text/images/light derivative) remains."},
    {"superseding": "F-831..F-840", "superseded": "any weaker interpretation of completion",
     "scope": "whole Master", "source": "master line 4364 (v1.0 s91)",
     "effect": "Runtime-proof chain is the definition of done everywhere."},
    {"superseding": "F-851..F-860", "superseded": "generative product-redraw default (Visual V1 direction)",
     "scope": "Visual implementation direction", "source": "master lines 4368-4369 (v1.0 s91)",
     "effect": "B+C default; Product Truth, dual verdict and canonical-model requirements stay mandatory."},
    {"superseding": "v0.6 identity protocol", "superseded": "provider scores from the broken identity protocol",
     "scope": "identity-related scores", "source": "master line 1079",
     "effect": "Old identity scores cannot be reused as evidence."},
]

DEF_RE = re.compile(r"^\W{0,3}F-(\d{3})(?![\d–-]*\s*[–-]\s*F-\d)\b(.*)$")
RANGE_HDR = re.compile(r"^\W{0,3}F-\d{3}\s*[–-]\s*F-\d{3}")
STOP_RE = [
    re.compile(r"^\d{1,2}\. [A-Z0-9]"),
    re.compile(r"^BRAMBLELOOP FINAL MASTER"),
    re.compile(r"^\W*v\d+\.\d+ (Addendum|appends)"),
    re.compile(r"^Version note"),
    re.compile(r"^\W*Registry additions\s*$"),
    re.compile(r"^Final-upgrade registry now runs"),
    re.compile(r"^New executable requirements"),
]
HEADER_NOISE = {"ID", "Requirement", "Executable definition"}


def version_of(line_no):
    v = VERSIONS[0][1]
    for start, name in VERSIONS:
        if line_no >= start:
            v = name
    return v


def is_titleish(s):
    words = re.findall(r"[A-Za-z][A-Za-z'/&-]*", s)
    if not words or len(s) > 48 or s.endswith("."):
        return False
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "is", "not", "of",
             "on", "or", "the", "to", "vs", "via", "with", "per", "into", "before", "after"}
    return all(w[0].isupper() or w.lower() in small or not w[0].isalpha() for w in words)


def parse():
    lines = SRC.read_text().split("\n")
    sections, cur_section = {}, None
    for i, l in enumerate(lines, 1):
        if re.match(r"^\d{1,2}\. [A-Z]", l):
            cur_section = l.strip()
        sections[i] = cur_section

    starts = []
    for i, l in enumerate(lines, 1):
        if RANGE_HDR.match(l):
            continue
        m = DEF_RE.match(l)
        if m:
            starts.append((i, int(m.group(1)), m.group(2)))

    records = []
    for k, (i, n, rest) in enumerate(starts):
        nxt = starts[k + 1][0] if k + 1 < len(starts) else len(lines) + 1
        body, end = [], i
        first = rest.strip()
        for j in range(i + 1, nxt):
            l = lines[j - 1]
            if any(r.match(l) for r in STOP_RE) or RANGE_HDR.match(l):
                break
            if re.match(r"^\x7f\s", l) and not re.match(r"^\x7f\s*F-\d", l):
                break  # an acceptance-test bullet, not part of this requirement
            if l.strip() and l.strip() not in HEADER_NOISE:
                body.append(l.strip())
            end = j
        fmt = "table"
        title, desc = None, None
        m = re.match(r"^[·\s]*(.+?)\s+[—-]\s+(.*)$", first)
        if first and m:
            fmt = "inline"
            title, desc = m.group(1).strip(" ·-"), " ".join([m.group(2)] + body)
        elif first:
            fmt = "inline"
            title, desc = first.strip(" ·-"), " ".join(body)
        else:
            tparts = []
            while body and is_titleish(body[0]) and len(tparts) < 3:
                tparts.append(body.pop(0))
            title = " ".join(tparts) if tparts else None
            desc = " ".join(body)
        version = version_of(i)
        text = re.sub(r"\s+", " ", ((title or "") + " - " + (desc or "")).strip(" -"))
        rec = {
            "id": f"F-{n:03d}", "num": n, "title": title, "text": desc, "full_text": text,
            "version": version, "section": sections.get(i), "source_lines": [i, end],
            "format": fmt,
        }
        if n in MASTER_PRIORITY:
            rec["master_priority"], rec["master_priority_source"] = MASTER_PRIORITY[n]
        elif version in ADDENDUM_PRIORITY:
            rec["master_priority"], rec["master_priority_source"] = ADDENDUM_PRIORITY[version]
        records.append(rec)

    # ID-space accounting.
    by_num = {}
    for r in records:
        by_num.setdefault(r["num"], []).append(r)
    collisions = {}
    for n, rs in by_num.items():
        if len(rs) > 1:
            collisions[f"F-{n:03d}"] = [r["version"] for r in rs]
            for r in rs:
                r["uid"] = f"F-{n:03d}@{r['version']}"
                r["collision"] = True
    for r in records:
        r.setdefault("uid", r["id"])
    absent = [n for n in range(1, 880) if n not in by_num]
    for r in records:
        if 781 <= r["num"] <= 788:
            r["superseded_where_conflicting_by"] = "F-789..F-798 (v0.23 s79)"
    return {
        "source": {"pdf": "spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf",
                   "pdf_sha256": "526ed69c8cf9b50e8b5ed736301607b0d314f7e80126ebd5a2178e9689471a99",
                   "text": "research/final_build/master_v1.0.txt", "lines": len(lines)},
        "id_space": {"declared": "F-001..F-879", "records": len(records),
                     "distinct_ids": len(by_num), "absent_ids": [f"F-{n:03d}" for n in absent],
                     "collisions": collisions},
        "supersessions": SUPERSESSIONS,
        "requirements": records,
    }


if __name__ == "__main__":
    reg = parse()
    OUT.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n")
    s = reg["id_space"]
    print(f"records={s['records']} distinct={s['distinct_ids']} absent={len(s['absent_ids'])} "
          f"collisions={list(s['collisions'])}")
