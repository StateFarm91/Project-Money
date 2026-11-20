"""Titles/tags/prices captured from the real five-listing chain (j_product_listings.py), re-checked by seo.truth + lint."""
from brambleloop.seo import facts as F, truth as TR
from brambleloop.store_foundation.lint import lint
D = {
 "market-basket-small": ("Hexagonal Bread Basket | Crochet Pattern PDF | Nursery | Written Instructions and Chart | US and UK Terms", 6.5,
   ['basket crochet','nursery crochet','nursery basket','written and chart','pdf crochet pattern','diy basket','digital download','home decor diy','instant download pdf','yarn craft project','us and uk terms','printable pdf chart','fiber art project']),
 "market-basket-medium": ("Hexagonal Storage Basket | Crochet Pattern PDF | Nursery | Written Instructions and Chart | US and UK Terms", 6.5,
   ['beginner crochet','diy gift crochet','basket crochet','nursery crochet','nursery basket','written and chart','pdf crochet pattern','diy basket','digital download','home decor diy','instant download pdf','yarn craft project','us and uk terms']),
 "market-basket-large": ("Hexagonal Market Basket | Crochet Pattern PDF | Nursery | Written Instructions and Chart | US and UK Terms", 6.5,
   ['crochet home decor','basket crochet','nursery crochet','nursery basket','written and chart','pdf crochet pattern','diy basket','digital download','home decor diy','instant download pdf','yarn craft project','us and uk terms','printable pdf chart']),
 "hexagon-coaster-set": ("Hexagon Coaster Set | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms", 4.0,
   ['coaster crochet','hexagon crochet','hexagon coaster','written and chart','pdf crochet pattern','diy coaster','digital download','home decor diy','instant download pdf','yarn craft project','us and uk terms','printable pdf chart','fiber art project']),
 "cloudline-baby-blanket": ("Cloudline Textured Baby Blanket | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms", 7.5,
   ['baby crochet pattern','cloudline crochet','cloudline baby','crochet baby chart','textured crochet','diy baby','written and chart','pdf crochet pattern','digital download','instant download pdf','yarn craft project','us and uk terms','printable pdf chart']),
}
facts = {f.slug: f for f in F.launch0_facts()}
comp = TR.competitor_names()
for slug, (title, price, tags) in D.items():
    kind = {"basket":"basket","coaster":"coaster","blanket":"blanket"}[[k for k in ("basket","coaster","blanket") if k in slug][0]]
    other = [k for k in ("basket","coaster","blanket","mosaic") if k != kind and (k in title.lower() or any(k in t for t in tags))]
    v = TR.validate_listing(title, tags, facts[slug], competitors=comp)
    print(f"{slug:24} price={price} own-noun-in-title={kind in title.lower()} foreign-product-words={other} len(title)={len(title)} tags={len(tags)} max_tag={max(map(len,tags))}")
    print("    seo.truth ok:", v["ok"], v["blocking"][:3], "| lint:", [x["code"] for x in lint(title+' '+' '.join(tags), voice=False)])
