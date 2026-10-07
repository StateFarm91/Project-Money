"""Wave-3 lane claims about Final Master rows, parsed from research/final_build/w3/handoff_*.md.

A claim is what a lane SAID; it is never certification (F-867). fm_ledger.py and fold.py use
claims only to decide which rows to re-map and which tests to run; the canonical verdict still
comes from aggregate.cap()/completion() over the re-mapped row.

Each claim: {uid, lane, status (COMPLETE|PARTIAL|GATED|OPEN|FAIL), text, tests[], modules[]}.
"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
SRC = ROOT / "src" / "brambleloop"
TESTS = ROOT / "tests"

_UID = re.compile(r"F-(\d{3})")
_RANGE = re.compile(r"F-(\d{3})\s*(?:\.\.|–|-)\s*F?-?(\d{3})")
_STATUS = [("FAIL", "FAIL"), ("NOT CERTIFIED", "PARTIAL"), ("PARTIAL", "PARTIAL"),
           ("machinery", "PARTIAL"), ("pending wiring", "PARTIAL"), ("OPEN", "OPEN"),
           ("COMPLETE", "COMPLETE"), ("PASS", "COMPLETE"), ("HOLDS", "COMPLETE"),
           ("GATED", "GATED"), ("BUILT", "PARTIAL")]

# SPEND wrote its row verdicts as prose bullets under status headings, not a table.
SPEND = {
    "COMPLETE": ["F-303", "F-320", "F-183", "F-184", "F-110", "F-105", "F-305", "F-308",
                 "F-315", "F-326", "F-306", "F-307", "F-339", "F-109", "F-474"],
    "GATED": ["F-106"],
    "OPEN": ["F-070", "F-103", "F-304", "F-319", "F-322", "F-325", "F-629", "F-098", "F-309",
             "F-310", "F-311", "F-312", "F-313", "F-314", "F-316", "F-317", "F-318", "F-328",
             "F-472", "F-659"],
}


def _uids(cell: str) -> list[str]:
    out = []
    for a, b in _RANGE.findall(cell):
        if int(b) > int(a) and int(b) - int(a) < 60 and "/" not in cell:
            out += [f"F-{n:03d}" for n in range(int(a), int(b) + 1)]
    out += [f"F-{n}" for n in _UID.findall(cell)]
    # "F-233/234/235" shorthand
    for m in re.finditer(r"F-(\d{3})((?:/\d{3})+)", cell):
        out += [f"F-{n}" for n in m.group(2).strip("/").split("/")]
    seen, res = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def _status(cell: str) -> str | None:
    for word, st in _STATUS:
        if word in cell:
            return st
    return None


_TEST_INDEX: dict[str, list[str]] = {}


def test_index() -> dict[str, list[str]]:
    """{test function name: [tests/file.py, ...]}."""
    if not _TEST_INDEX:
        for p in sorted(TESTS.glob("*.py")):
            for m in re.finditer(r"^def (test_\w+)", p.read_text(errors="replace"), re.M):
                _TEST_INDEX.setdefault(m.group(1), []).append(f"tests/{p.name}")
    return _TEST_INDEX


def resolve_tests(text: str, default_file: str | None = None) -> list[str]:
    """`tests/x.py::test_y` refs for every test the text names (prefix forms `test_x_*`,
    `test_x…`, `test_x...` expand to every function with that prefix; a bare test file name
    expands to the file)."""
    idx = test_index()
    refs: list[str] = []
    files = set(re.findall(r"\b(test_[\w]+)\.py", text))
    for m in re.finditer(r"(test_\w+?)(\*|…|\.\.\.)?(?=[`\s,;)(:.]|$)", text):
        name, pre = m.group(1), m.group(2)
        if name in files or (name + ".py") in text and not pre and name not in idx:
            continue
        if pre or name not in idx:
            hits = [n for n in idx if n.startswith(name)] if (pre or len(name) > 12) else []
        else:
            hits = [name]
        for n in hits:
            fs = idx[n]
            if default_file and f"tests/{default_file}" in fs:
                fs = [f"tests/{default_file}"]
            refs += [f"{f}::{n}" for f in fs]
    for f in files:
        if (TESTS / f"{f}.py").exists() and not any(r.startswith(f"tests/{f}.py") for r in refs):
            refs.append(f"tests/{f}.py")
    return sorted(set(refs))


_STEMS: dict[str, list[str]] = {}


def _stems() -> dict[str, list[str]]:
    if not _STEMS:
        for f in SRC.rglob("*.py"):
            if "__pycache__" in f.parts or f.name == "__init__.py":
                continue
            _STEMS.setdefault(f.stem, []).append(f.relative_to(SRC).as_posix())
    return _STEMS


def test_imports(test_refs: list[str]) -> set[str]:
    """Modules (relative to src/brambleloop) the cited test files import."""
    out: set[str] = set()
    for f in {r.split("::")[0] for r in test_refs}:
        text = (ROOT / f).read_text(errors="replace") if (ROOT / f).exists() else ""
        for m in re.finditer(r"from brambleloop((?:\.\w+)*) import ([\w, ()\n]+)", text):
            pkg = m.group(1).strip(".").replace(".", "/")
            if pkg and (SRC / f"{pkg}.py").is_file():
                out.add(f"{pkg}.py")
            for name in re.findall(r"\w+", m.group(2)):
                cand = f"{pkg}/{name}.py" if pkg else f"{name}.py"
                if (SRC / cand).is_file():
                    out.add(cand)
        for m in re.finditer(r"import brambleloop((?:\.\w+)+)", text):
            cand = m.group(1).strip(".").replace(".", "/") + ".py"
            if (SRC / cand).is_file():
                out.add(cand)
    return out


def resolve_modules(text: str, prefer: set[str] | None = None) -> list[str]:
    """Modules (relative to src/brambleloop) the text names, as paths, dotted names, or a
    short `module.func` whose module stem is unique (or is among `prefer`, the modules the
    cited tests import)."""
    prefer = prefer or set()
    mods: list[str] = []
    for p in re.findall(r"(?<![\w.])((?:[a-z_]+/)+[a-z_0-9]+)(?:\.py)?", text):
        p = p.removeprefix("src/brambleloop/")
        if (SRC / f"{p}.py").is_file():
            mods.append(f"{p}.py")
    for d in re.findall(r"(?<![\w/])([a-z_][a-z_0-9]*(?:\.[a-z_][a-z_0-9]*)+)", text):
        parts = d.split(".")
        hit = None
        for k in range(len(parts), 0, -1):
            cand = "/".join(parts[:k]) + ".py"
            if (SRC / cand).is_file():
                hit = cand
                break
        if hit is None:
            for k in range(len(parts) - 1, -1, -1):
                st = _stems().get(parts[k], [])
                pref = [m for m in st if m in prefer]
                if len(pref) == 1 or len(st) == 1:
                    hit = (pref or st)[0]
                    break
        if hit:
            mods.append(hit)
    seen, out = set(), []
    for m in mods:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _default_test_file(text: str) -> str | None:
    m = re.search(r"tests/(test_\w+\.py)", text) or re.search(r"\b(test_\w+\.py)", text)
    return m.group(1) if m else None


def parse() -> dict[str, list[dict]]:
    claims: dict[str, list[dict]] = {}

    def add(uid, lane, status, text, dflt):
        tests = resolve_tests(text, dflt)
        claims.setdefault(uid, []).append({
            "uid": uid, "lane": lane, "status": status, "text": text.strip()[:1200],
            "tests": tests, "modules": resolve_modules(text, test_imports(tests)),
            "test_imports": sorted(test_imports(tests))})

    for path in sorted((FB / "w3").glob("handoff_*.md")):
        lane = path.stem.removeprefix("handoff_")
        text = path.read_text(errors="replace")
        dflt = _default_test_file(text)
        if lane == "SPEND":
            for st, ids in SPEND.items():
                for u in ids:
                    para = "\n".join(l for l in text.splitlines() if u in l)
                    add(u, lane, st, para or f"SPEND handoff lists {u} as {st}", dflt)
            continue
        if lane in ("K",):
            continue  # the audit lane itself makes no implementation claim
        for line in text.splitlines():
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            ids = _uids(cells[0])
            if not ids:
                continue
            st = _status(cells[1]) or _status(" ".join(cells[1:]))
            if st is None:
                continue
            for u in ids:
                add(u, lane, st, line, dflt)
    return claims


if __name__ == "__main__":
    import collections
    import json
    c = parse()
    print(len(c), collections.Counter(x["status"] for v in c.values() for x in v))
    print(json.dumps({k: c[k] for k in list(c)[:2]}, indent=1)[:2500])
