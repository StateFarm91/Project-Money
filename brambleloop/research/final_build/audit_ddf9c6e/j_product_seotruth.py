from brambleloop.seo import facts as F, truth as T
fl = F.launch0_facts()
f = fl[0]
print("facts for", f.slug, f.kind, f.category)
tests = ["hexagon basket crochet", "ravelry pattern", "Ravelry", "R A V E L R Y", "ｒａｖｅｌｒｙ", "ＲＡＶＥＬＲＹ",
 "ＢＥＳＴ", "ｂｅｓｔ ｓｅｌｌｅｒ", "最佳", "★★★★★", "😀", "100% hand knitted", "ｗｏｏｂｌｅｓ", "woobles", "Wo0bles",
 "w00bles", "disney", "ｄｉｓｎｅｙ", "ＤＩＳＮＥＹ", "ｍｉｃｋｅｙ ｍｏｕｓｅ", "crochet pattern pdf", "CROCHET BASKET", "crochet  basket",
 "basket-crochet", "basket​crochet", "bestseller basket", "free pattern", "knit basket", "waterproof basket", "food safe basket",
 "baby safe basket", "beginner basket", "easy basket", "organic cotton basket", "hand made basket", "etsy choice basket"]
for t in tests:
    v = T.check_term(t, f, competitors=T.competitor_names())
    print("OK  " if v.ok else "refuse", repr(t), [x.split(":")[0] for x in v.findings][:3])
print("== validate_listing (the whole-set validator) with evasive tags")
good_title = "Hexagonal Storage Basket | Crochet Pattern PDF"
for tags in (["ｒａｖｅｌｒｙ"], ["ＢＥＳＴ"], ["ｄｉｓｎｅｙ"], ["最佳"], ["★★★★★"], ["basket​crochet"], ["Basket Crochet"], ["x"*21], [f"basket{i}" for i in range(14)],
             ["crochet basket", "Crochet Basket"], ["ｒａｖｅｌｒｙ ｂａｓｋｅｔ"]):
    r = T.validate_listing(good_title, tags, f, competitors=T.competitor_names())
    print("ok" if r["ok"] else "blocked", [t[:12] for t in tags][:3], [b[:60] for b in r["blocking"]][:3])
for title in ("ＢＥＳＴ Hexagonal Storage Basket", "Hexagonal Storage Basket | ｒａｖｅｌｒｙ", "x"*141):
    r = T.validate_listing(title, ["crochet basket"], f, competitors=T.competitor_names())
    print("title", "ok" if r["ok"] else "blocked", title[:40], [b[:70] for b in r["blocking"]][:3])
print("== realistic set + one evasive item")
base = ["crochet basket", "storage basket", "nursery decor", "hexagon pattern", "pdf pattern", "crochet pdf",
        "beginner basket", "basket pdf", "hexagonal", "written chart", "us uk terms"]
r0 = T.validate_listing("Hexagonal Storage Basket | Crochet Pattern PDF", base, f, competitors=T.competitor_names())
print("baseline ok:", r0["ok"], r0["blocking"][:3]); B0=set(r0["blocking"])
for ev in ("ｒａｖｅｌｒｙ", "ＢＥＳＴ ＳＥＬＬＥＲ", "ｄｉｓｎｅｙ", "最佳"):
    r = T.validate_listing("Hexagonal Storage Basket | Crochet Pattern PDF", base + [ev], f, competitors=T.competitor_names())
    print("tag", repr(ev), "ok" if r["ok"] else "blocked", sorted(set(r["blocking"])-B0)[:2])
for t in ("ＢＥＳＴ Hexagonal Storage Basket | Crochet Pattern PDF", "Hexagonal Storage Basket | ｄｉｓｎｅｙ | Crochet Pattern PDF"):
    r = T.validate_listing(t, base, f, competitors=T.competitor_names())
    print("title", repr(t), "ok" if r["ok"] else "blocked", sorted(set(r["blocking"])-B0)[:2])
