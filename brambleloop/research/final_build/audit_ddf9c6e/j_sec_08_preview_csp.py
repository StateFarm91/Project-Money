from j_sec_common import *
import re
from brambleloop.core.models import Product, Listing, PatternVersion
XSS='<script>alert(1)</script><img src=x onerror=alert(2)>"\'><svg/onload=alert(3)>'
with db.session() as s:
    p=Product(slug="xssp", title=XSS, status="certified"); s.add(p); s.flush()
    s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"a":1}, release_hash="r"*20, certified=True, certificate={}))
    s.add(Listing(product_slug="xssp", version="1.0.0", title=XSS, description=XSS, tags=[XSS], price_cad=9.0, state="draft", release_hash="r"*20))
c=client(); csrf=login(c)
for vp in ("mobile","desktop","<script>"):
    r=c.get("/cc/store-preview", params={"viewport":vp}); h=r.text
    print(vp, r.status_code, "len",len(h), "| raw <script in body (excluding none):", len(re.findall(r"<script",h,re.I)), "| onerror= unescaped:", bool(re.search(r'<img[^>]*onerror',h)), "| payload escaped present:", "&lt;script&gt;" in h)
    print("  CSP:", r.headers.get("content-security-policy")); print("  other:", {k:r.headers.get(k) for k in ("x-frame-options","x-content-type-options","cache-control","referrer-policy","x-robots-tag")})
r=c.get("/cc/store-preview"); csp=r.headers["content-security-policy"]
print("preview CSP allows unsafe-inline style:", "style-src 'self' 'unsafe-inline'" in csp, "| script-src:", re.search(r"script-src [^;]*",csp).group(0), "| frame-ancestors:", re.search(r"frame-ancestors [^;]*",csp).group(0))
print("preview has inline <style>:", "<style>" in r.text, "| inline event handler attrs:", bool(re.search(r"\son\w+=",r.text)))
# static shell
for p in ["/cc/","/cc/index.html","/cc/sw.js","/cc/js/app.js","/cc/manifest.webmanifest"]:
    r=client().get(p); print(p, r.status_code, {k:r.headers.get(k) for k in ("content-security-policy","x-frame-options","cache-control","service-worker-allowed")})
r=client().get("/cc/sw.js"); print("sw caches /api?:", "/api/" in r.text and "isApi" in r.text, "| cache.put guarded to SHELL:", "SHELL_PATHS.has(shellKey)" in r.text)
# any HTML sinks in JS
import pathlib
js=pathlib.Path(ROOT/"src/brambleloop/app/command_center/static")
sinks=[]
for f in js.rglob("*.js"):
    for i,l in enumerate(f.read_text().splitlines(),1):
        if re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function|setTimeout\(\s*[\"']|srcdoc|\.setAttribute\(\s*[\"']on|DOMParser|createContextualFragment|localStorage|sessionStorage|indexedDB|caches\.",l): sinks.append((str(f.relative_to(js)),i,l.strip()[:120]))
print("JS sinks/storage:", sinks or "none")
h=c.get("/cc/store-preview").text
print("preview mentions payload tokens:", [(m.start(), h[max(0,m.start()-30):m.start()+40]) for m in re.finditer("alert|xssp",h)][:4])
