"""Static guard: every `h(tag, {attrs})` call in the Command Center PWA uses only attribute keys
that `static/js/dom.js` `h()` accepts (CC_VERIFY_7421ef6 RB-1).

THE DEFECT. `h()` throws `h(): attribute <k> is not allowed` for any key outside its allowlist.
The throw happens at render time, so a view that passes e.g. `maxlength` (instead of the property
name `maxLength`) crashes the whole tab -- and only when the data that renders that element is
present. The Store tab shipped like this in 7421ef6: the mock data never rendered the live-shop
observation form, so no browser check reached it.

THE RULE. Pure Python, no browser: scan every shipped .js file under command_center/static/js
for `h(` calls whose second argument is an object literal, extract that literal's top-level keys
and require each one to be accepted by dom.js -- the special keys handled by name, `on*`
handlers, setAttribute keys, or `ALLOWED_PROPS` (parsed from dom.js itself, so the allowlist has
one source of truth). A spread (`...x`) cannot be checked statically and is reported by name in
`SPREAD_OK` (must stay empty unless reviewed).

Named limit: attribute objects built elsewhere and passed by variable are not seen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js"
DOM = JS / "dom.js"

SPECIAL = {"class", "text", "aria", "data", "href", "src", "role", "for", "lang", "rel", "target",
           "datetime", "enterkeyhint", "autocapitalize"}
SPREAD_OK: set[str] = set()

passes = 0
failures = 0


def check(cond: bool, name: str, why: str = "") -> None:
    global passes, failures
    if cond:
        passes += 1
        print(f"OK {name}")
    else:
        failures += 1
        print(f"FAIL {name}: {why}")


def allowed_props() -> set[str]:
    m = re.search(r"ALLOWED_PROPS\s*=\s*new Set\(\[(.*?)\]\)", DOM.read_text(), re.S)
    assert m, "dom.js ALLOWED_PROPS not found"
    return set(re.findall(r'"([A-Za-z]+)"', m.group(1)))


def allowed(key: str, props: set[str]) -> bool:
    return key in SPECIAL or key in props or (key.startswith("on") and len(key) > 2)


_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {""}


def _skip_string(src: str, i: int) -> int:
    q = src[i]
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if q == "`" and src.startswith("${", i):
            i = _skip_balanced(src, i + 1, "{", "}")
            continue
        if c == q:
            return i + 1
        i += 1
    return i


def _skip_regex(src: str, i: int) -> int:
    i += 1
    in_class = False
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            i += 1
            while i < len(src) and src[i].isalpha():
                i += 1
            return i
        i += 1
    return i


def _prev_sig(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j].isspace():
        j -= 1
    if j < 0:
        return ""
    if src[j].isalnum() or src[j] in "_$":
        k = j
        while k >= 0 and (src[k].isalnum() or src[k] in "_$"):
            k -= 1
        word = src[k + 1:j + 1]
        return "" if word in ("return", "typeof", "case", "in", "of") else "x"
    return src[j]


def _skip_trivia(src: str, i: int) -> int | None:
    """If src[i] starts a string, comment or regex, return the index after it; else None."""
    c = src[i]
    if c in "'\"`":
        return _skip_string(src, i)
    if src.startswith("//", i):
        j = src.find("\n", i)
        return len(src) if j < 0 else j
    if src.startswith("/*", i):
        j = src.find("*/", i + 2)
        return len(src) if j < 0 else j + 2
    if c == "/" and _prev_sig(src, i) in _REGEX_PREV:
        return _skip_regex(src, i)
    return None


def _skip_balanced(src: str, i: int, open_: str, close: str) -> int:
    """src[i] == open_; return index just past the matching close."""
    depth = 0
    while i < len(src):
        nxt = _skip_trivia(src, i)
        if nxt is not None:
            i = nxt
            continue
        c = src[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _object_keys(src: str, i: int) -> list[str]:
    """src[i] == '{' of an object literal: its top-level keys ('...name' for spreads)."""
    keys = []
    end = _skip_balanced(src, i, "{", "}")
    j = i + 1
    expect_key = True
    while j < end - 1:
        if src[j].isspace():
            j += 1
            continue
        if expect_key:
            if src.startswith("...", j):
                m = re.match(r"\.\.\.\s*([\w$.]+)", src[j:])
                keys.append("..." + (m.group(1) if m else "?"))
            else:
                m = re.match(r"""(["'])([^"']+)\1|([A-Za-z_$][\w$]*)""", src[j:])
                if m:
                    keys.append(m.group(2) or m.group(3))
            expect_key = False
        nxt = _skip_trivia(src, j)
        if nxt is not None:
            j = nxt
            continue
        c = src[j]
        if c in "([{":
            j = _skip_balanced(src, j, c, {"(": ")", "[": "]", "{": "}"}[c])
            continue
        if c == ",":
            expect_key = True
        j += 1
    return keys


def h_calls(src: str):
    """Yield (line, keys) for each `h(tag, { ... })` call."""
    i = 0
    while i < len(src):
        nxt = _skip_trivia(src, i)
        if nxt is not None:
            i = nxt
            continue
        if (src[i] == "h" and src.startswith("(", i + 1)
                and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] in "_$."))):
            # first argument: up to the top-level comma
            j = i + 2
            depth = 0
            while j < len(src):
                nxt = _skip_trivia(src, j)
                if nxt is not None:
                    j = nxt
                    continue
                c = src[j]
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif c == "," and depth == 0:
                    break
                j += 1
            if j < len(src) and src[j] == ",":
                k = j + 1
                while k < len(src) and src[k].isspace():
                    k += 1
                if src.startswith("{", k):
                    yield src.count("\n", 0, i) + 1, _object_keys(src, k)
            i += 2
            continue
        i += 1


def bad_keys(src: str, props: set[str]) -> list[tuple[int, str]]:
    out = []
    for line, keys in h_calls(src):
        for k in keys:
            if k.startswith("..."):
                if k not in SPREAD_OK:
                    out.append((line, k))
            elif not allowed(k, props):
                out.append((line, k))
    return out


def test_detector_catches_the_rb1_shape() -> None:
    props = allowed_props()
    sample = ('const a = h("textarea", { id: "x", rows: 3, maxlength: 6000 });\n'
              'const b = h("input", { type: "text", maxLength: 5, onclick: () => go(/a{1}/), class: ["c", d ? "e" : null] });\n'
              'const s = "h(\\"p\\", { bogus: 1 })"; // h("p", { alsoBogus: 2 })\n'
              'const c = h("p", { title: `t ${x}`, aria: { label: "y" }, data: { k: 1 } }, "z");\n')
    calls = list(h_calls(sample))
    check(len(calls) == 3, "self-test: three h() calls with attribute objects found (strings/comments skipped)", str(calls))
    check(bad_keys(sample, props) == [(1, "maxlength")], "self-test: the RB-1 key 'maxlength' is reported, nothing else",
          str(bad_keys(sample, props)))
    check("maxLength" in props and "maxlength" not in props, "self-test: allowlist parsed from dom.js", str(sorted(props)))


def test_every_h_call_uses_allowed_keys() -> None:
    props = allowed_props()
    files = sorted(JS.rglob("*.js"))
    views = [f for f in files if f.parent.name == "views"]
    check(len(views) >= 15, "views scanned", str(len(views)))
    total_calls = 0
    total_keys = 0
    problems = []
    for f in files:
        src = f.read_text()
        calls = list(h_calls(src))
        total_calls += len(calls)
        total_keys += sum(len(k) for _, k in calls)
        problems += [f"{f.relative_to(JS)}:{line} {k}" for line, k in bad_keys(src, props)]
    check(total_calls >= 200 and total_keys >= 300, "h() attribute objects scanned across the PWA",
          f"{total_calls} calls, {total_keys} keys")
    check(not problems, "every h() attribute key is accepted by dom.js (no render-time throw)",
          "; ".join(problems))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"\n{passes} passed, {failures} failed")
    sys.exit(1 if failures or not passes else 0)
