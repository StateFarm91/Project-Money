"""Static checks for the Owner Command Center PWA (v1.1 lane D: F-882, F-883, F-898).

Pure Python, no browser. Each check reads the shipped files under
src/brambleloop/app/command_center/static and proves a property the browser cannot be trusted
to report on its own:

* the web app manifest is valid and installable (name, scope, start_url inside scope,
  192/512 PNG icons that exist at their declared sizes, a maskable icon);
* no inline script, no event-handler attribute, no inline style (the edge CSP is
  script-src 'self'; style-src 'self');
* no HTML-string sink anywhere (innerHTML/outerHTML/insertAdjacentHTML/document.write) and no
  eval/new Function/string timers -- dynamic text goes through textContent only;
* no external URL: no CDN, no web font, no third-party fetch;
* the service worker never caches /api/ responses (money/customer/security data), only the
  listed shell, and the shell list is complete and exact;
* every mutating call in the API client carries CSRF + nonce + timestamp headers, and no
  response is written to persistent storage;
* test fixtures (the mock API) are not shipped in the static directory.
"""
from __future__ import annotations

import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"

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


def files(*suffixes: str) -> list[Path]:
    return sorted(p for p in STATIC.rglob("*") if p.is_file() and p.suffix in suffixes)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return struct.unpack(">II", data[16:24])


def strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(^|[^:\\])//[^\n]*", r"\1", src)


# ---- manifest ------------------------------------------------------------------------------

def test_manifest() -> None:
    path = STATIC / "manifest.webmanifest"
    check(path.is_file(), "manifest: file exists")
    m = json.loads(path.read_text())
    for key in ("name", "short_name", "start_url", "scope", "display", "icons", "theme_color", "background_color"):
        check(bool(m.get(key)), f"manifest: has {key}")
    check(m["display"] in ("standalone", "fullscreen", "minimal-ui"), "manifest: app-like display mode", m["display"])
    scope = m["scope"]
    check(scope == "./" and m["start_url"].startswith("./"), "manifest: start_url inside relative scope (/cc/)",
          f"scope={scope} start={m['start_url']}")
    check(re.fullmatch(r"#[0-9A-Fa-f]{6}", m["theme_color"]) is not None, "manifest: theme_color is hex")
    icons = m["icons"]
    check(len(icons) >= 2, "manifest: icons listed", str(len(icons)))
    sizes = set()
    for icon in icons:
        f = STATIC / icon["src"]
        check(f.is_file(), f"manifest: icon {icon['src']} exists")
        if icon.get("type") == "image/png":
            w, h = png_size(f)
            check(f"{w}x{h}" == icon["sizes"], f"manifest: {icon['src']} is really {icon['sizes']}", f"{w}x{h}")
            sizes.add(icon["sizes"])
    check({"192x192", "512x512"} <= sizes, "manifest: 192 and 512 PNG icons", str(sizes))
    check(any("maskable" in i.get("purpose", "") for i in icons), "manifest: maskable icon present")
    shortcuts = m.get("shortcuts", [])
    check(len(shortcuts) > 0 and all(s["url"].startswith("./#/") for s in shortcuts),
          "manifest: shortcuts are in-scope deep links")
    html = (STATIC / "index.html").read_text()
    check('rel="manifest" href="manifest.webmanifest"' in html, "manifest: linked from index.html")


# ---- HTML: no inline script / handlers / styles ---------------------------------------------

class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.problems: list[str] = []
        self.scripts = 0
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k, v in attrs:
            if k.startswith("on"):
                self.problems.append(f"event handler attribute {k} on <{tag}>")
            if k == "style":
                self.problems.append(f"inline style on <{tag}>")
            if k in ("href", "src", "action") and v and v.strip().lower().startswith("javascript:"):
                self.problems.append(f"javascript: URL on <{tag}>")
        if tag == "script":
            self.scripts += 1
            self._in_script = True
            if not a.get("src"):
                self.problems.append("inline <script> without src")
        if tag == "style":
            self.problems.append("inline <style> block")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script and data.strip():
            self.problems.append("script body text")


def test_html_csp_clean() -> None:
    pages = files(".html")
    check(len(pages) > 0, "html: pages found", str(pages))
    for page in pages:
        scan = _Scan()
        scan.feed(page.read_text())
        check(scan.scripts > 0, f"html: {page.name} loads its script from a file")
        check(not scan.problems, f"html: {page.name} has no inline script/handler/style", "; ".join(scan.problems))


# ---- JS: no HTML sinks, no eval ------------------------------------------------------------

SINKS = [
    (r"\.innerHTML\b", "innerHTML"),
    (r"\.outerHTML\b", "outerHTML"),
    (r"insertAdjacentHTML", "insertAdjacentHTML"),
    (r"document\.write", "document.write"),
    (r"\beval\s*\(", "eval"),
    (r"\bnew\s+Function\b", "new Function"),
    (r"set(?:Timeout|Interval)\s*\(\s*['\"`]", "string timer"),
    (r"createContextualFragment", "createContextualFragment"),
    (r"DOMParser", "DOMParser"),
    (r"\.setAttribute\(\s*['\"]style['\"]", "style attribute"),
    (r"\.setAttribute\(\s*['\"]on", "event attribute"),
]


def test_js_no_html_sinks() -> None:
    scripts = files(".js")
    check(len(scripts) >= 10, "js: modules found", str(len(scripts)))
    hits = []
    for js in scripts:
        src = strip_js_comments(js.read_text())
        for pattern, label in SINKS:
            if re.search(pattern, src):
                hits.append(f"{js.relative_to(STATIC)}: {label}")
    check(not hits, "js: no innerHTML/outerHTML/document.write/eval/string-timer sinks", "; ".join(hits))
    dom = (STATIC / "js" / "dom.js").read_text()
    check("textContent" in dom and "createTextNode" in dom, "js: dom helper inserts text as text nodes")
    check('k === "href" || k === "src"' in dom and "safeUrl(v)" in dom, "js: href/src pass through safeUrl")


# ---- no external URLs ---------------------------------------------------------------------

ALLOWED_ABSOLUTE = {"http://www.w3.org/2000/svg"}  # an XML namespace identifier, never fetched


def test_no_external_urls() -> None:
    shipped = files(".html", ".js", ".css", ".webmanifest", ".svg", ".json")
    check(len(shipped) > 0, "external: files scanned")
    found = []
    for f in shipped:
        text = f.read_text()
        urls = re.findall(r"https?://[^\s\"'`)<>]+", text)
        urls += [u for u in re.findall(r"[\"'(=]\s*(//[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s\"'`)]*)", text)]
        for url in urls:
            if url not in ALLOWED_ABSOLUTE:
                found.append(f"{f.relative_to(STATIC)}: {url}")
        if f.suffix == ".css" and re.search(r"@import|@font-face", text):
            found.append(f"{f.relative_to(STATIC)}: @import/@font-face")
    check(not found, "external: no CDN, font or third-party URL shipped", "; ".join(found[:10]))
    api = (STATIC / "js" / "api.js").read_text()
    check('API_BASE = "/api/cc"' in api, "external: API is same-origin relative")
    check(api.count('credentials: "same-origin"') >= 3, "external: fetches use same-origin credentials")


# ---- service worker -----------------------------------------------------------------------

def test_service_worker_never_caches_api() -> None:
    sw = (STATIC / "sw.js").read_text()
    code = strip_js_comments(sw)
    check('url.pathname.startsWith("/api/")' in code, "sw: recognises /api/ requests")
    i_api = code.find("if (isApi(url)) return;")
    i_respond = code.find("event.respondWith")
    check(0 <= i_api < i_respond, "sw: /api/ requests return before respondWith (never intercepted)",
          f"isApi@{i_api} respondWith@{i_respond}")
    check('if (req.method !== "GET") return;' in code, "sw: non-GET requests never intercepted")
    check("url.origin !== self.location.origin" in code, "sw: cross-origin requests never intercepted")
    check(code.count("c.put(") == 1 and "SHELL_PATHS.has(shellKey)" in code,
          "sw: cache.put only for listed shell paths")
    m = re.search(r"const SHELL = \[(.*?)\];", code, flags=re.S)
    check(m is not None, "sw: SHELL list present")
    shell = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    check(len(shell) > 0, "sw: SHELL list non-empty", str(len(shell)))
    check(not any("/api/" in s or s.startswith("api/") for s in shell), "sw: SHELL contains no API path", str(shell))
    missing = [s for s in shell if s != "./" and not (STATIC / s).is_file()]
    check(not missing, "sw: every SHELL entry exists", str(missing))
    shipped = {str(p.relative_to(STATIC)) for p in files(".js", ".css", ".html", ".webmanifest", ".png", ".svg")}
    shipped.discard("sw.js")
    unlisted = sorted(shipped - set(shell))
    check(not unlisted, "sw: every shipped asset is in the offline shell", str(unlisted))
    check("caches." not in strip_js_comments("".join(p.read_text() for p in files(".js") if p.name != "sw.js")),
          "sw: no page script writes the Cache API")


# ---- API client: CSRF/replay headers and no persistent storage ---------------------------

def test_api_client_security() -> None:
    api = strip_js_comments((STATIC / "js" / "api.js").read_text())
    check('H_CSRF = "X-CSRF-Token"' in api and 'H_NONCE = "X-CC-Nonce"' in api and 'H_TS = "X-CC-Timestamp"' in api,
          "api: contract header names")
    raw = api[api.find("async function rawPost"):api.find("export async function post")]
    check("headers[H_CSRF]" in raw and "headers[H_NONCE] = nonce()" in raw and "headers[H_TS]" in raw,
          "api: every POST carries CSRF + fresh nonce + timestamp")
    posts = re.findall(r'method:\s*"(POST|PUT|PATCH|DELETE)"', api)
    check(posts == ["POST"], "api: exactly one mutating fetch site (rawPost)", str(posts))
    check('body.code === "STEP_UP_REQUIRED"' in api, "api: step-up retry path present")
    check(api.count("await rawPost(path, payload)") == 2, "api: step-up retry re-sends via rawPost (fresh nonce)")
    stores = []
    for js in files(".js"):
        src = strip_js_comments(js.read_text())
        for m in re.finditer(r"(localStorage|sessionStorage|indexedDB)\.?\w*", src):
            stores.append(f"{js.name}:{m.group(0)}")
    check(stores and all(s.startswith("app.js:localStorage") for s in stores),
          "api: only app.js touches storage (theme preference)", str(stores))
    app = (STATIC / "js" / "app.js").read_text()
    check(len(re.findall(r"localStorage\.setItem\(", app)) == 1 and 'THEME_KEY = "cc-theme"' in app,
          "api: the single persisted key is the theme")


# ---- structure: routes, views, fixture separation -----------------------------------------

def test_structure() -> None:
    routes = (STATIC / "js" / "routes.js").read_text()
    ids = re.findall(r'id: "([a-z]+)"', routes)
    check(len(ids) >= 10, "structure: tabs declared", str(ids))
    required = {"home", "approvals", "store", "money", "operations", "learn", "insights", "notifications", "account", "ask"}
    check(required <= set(ids), "structure: all required tabs present", str(required - set(ids)))
    for view in ids + ["more", "drill", "emergency"]:
        f = STATIC / "js" / "views" / f"{view}.js"
        check(f.is_file() and "export async function render" in f.read_text(), f"structure: view {view} exports render")
    imports = []
    for js in files(".js"):
        for spec in re.findall(r'from\s+"(\.[^"]+)"', js.read_text()):
            imports.append((js, spec))
    check(len(imports) > 10, "structure: relative imports found")
    broken = [f"{js.name}->{spec}" for js, spec in imports if not (js.parent / spec).resolve().is_file()]
    check(not broken, "structure: every relative import resolves", str(broken))
    leaked = [str(p.relative_to(STATIC)) for p in STATIC.rglob("*") if re.search(r"mock|fixture", p.name, re.I)]
    check(not leaked, "structure: no mock/fixture file shipped", str(leaked))
    text = "".join(p.read_text() for p in files(".js", ".html"))
    check("cc_mock" not in text and "__mock" not in text, "structure: shipped code never references the mock")
    total = sum(p.stat().st_size for p in STATIC.rglob("*") if p.is_file())
    check(total < 400_000, "structure: static bundle under 400 KB", str(total))


def test_money_rules_in_code() -> None:
    fmt = (STATIC / "js" / "format.js").read_text()
    check('UNKNOWN_TEXT = "Unknown"' in fmt, "money: Unknown wording constant")
    check("if (!m.known) return UNKNOWN_TEXT;" in fmt, "money: formatMoney returns Unknown for unknown values")
    check('"value_cad" in v' in fmt and "known ? amount : null" in fmt, "money: contract value_cad null never coerced")
    coercions = []
    for js in files(".js"):
        src = strip_js_comments(js.read_text())
        coercions += [f"{js.name}: {m.group(0)}" for m in re.finditer(
            r"(amount|value_cad|value|cents|amount_minor)\s*(\?\?|\|\|)\s*0\b", src)]
    check(not coercions, "money: no `value ?? 0` / `amount || 0` coercion anywhere", str(coercions))


if __name__ == "__main__":
    for fn in (test_manifest, test_html_csp_clean, test_js_no_html_sinks, test_no_external_urls,
               test_service_worker_never_caches_api, test_api_client_security, test_structure, test_money_rules_in_code):
        try:
            fn()
        except Exception as exc:  # a crash is a failure, never a silent pass
            failures += 1
            print(f"FAIL {fn.__name__}: crashed: {exc!r}")
    print(f"{passes} passed, {failures} failed")
    sys.exit(1 if failures else 0)
