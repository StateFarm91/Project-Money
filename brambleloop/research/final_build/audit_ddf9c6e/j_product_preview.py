from brambleloop.store_foundation import preview as P
from brambleloop.app.security import esc
hostile = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "' onmouseover='alert(1)", "javascript:alert(1)", "</style><script>x</script>", "{{7*7}}", " <svg onload=alert(1)>"]
for h in hostile:
    e = P._esc(h)
    print("ESC", repr(h)[:40], "->", e[:60], "| raw '<' or quote survives:", ("<" in e) or ('"' in e) or ("'" in e and "&#" not in e))
    print("   _paras:", P._paras(h + "\n\n- " + h)[:90])
tile = P._tile({"title": hostile[1], "price_cad": 6.5, "variant_count": 3}, {"status": "VERIFIED", "png": b"\x89PNG", "alt_text": hostile[1]})
print("TILE", tile[:400])
print("alt attr breaks out:", 'onerror=alert' in tile and '&quot;' not in tile)
