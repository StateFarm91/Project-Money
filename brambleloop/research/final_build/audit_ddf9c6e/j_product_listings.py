"""Draft all five Launch-0 listings through the real chain and dump title/tags/price/category/sizes."""
import sys, os
sys.path.insert(0, "tests")
import test_launch0_listing_truth as T
from brambleloop.products import launch0 as L
from brambleloop.core.models import ListingSearchProfile, Listing
from sqlalchemy import select
db = T._chain()
for build in T.BUILDS:
    cir = L.cir_for(build)
    row = T._listing(db, cir.slug)
    ident = L.listing_identity(cir.slug)
    with db.session() as s:
        p = s.scalar(select(ListingSearchProfile).where(ListingSearchProfile.product_slug == cir.slug))
        tax = p.taxonomy_id
    print("---", build, cir.slug, "kind", ident.kind)
    print(" title:", row.title); print(" tags:", row.tags); print(" price:", row.price_cad, "tax", tax)
    print(" desc:", (row.description or "")[:1500].replace("\n"," / "))
from brambleloop.store_foundation.lint import lint
from brambleloop.seo import facts as F, truth as TR
import re
facts = {f.slug: f for f in F.launch0_facts()}
print("\n===== lint + seo.truth over each drafted listing =====")
for build in T.BUILDS:
    cir = L.cir_for(build); row = T._listing(db, cir.slug)
    fl = lint(row.title + "\n" + (row.description or ""), surface=cir.slug)
    print(cir.slug, "lint:", [(x["code"], x["match"]) for x in fl])
    f = facts.get(cir.slug)
    if f is not None:
        v = TR.validate_listing(row.title, list(row.tags), f, competitors=TR.competitor_names(db))
        print("   seo.truth.validate_listing ok:", v["ok"], v["blocking"][:4])
    else:
        print("   no ProductFacts for", cir.slug, "(launch0_facts slugs:", sorted(facts), ")")
    m = re.search(r"Finished size:[^\n]*", row.description or "")
    print("   ", m.group(0) if m else "no size line", "| set/qty words:", re.findall(r"\b(?:set of \d+|\d+ coasters?|four|six)\b", (row.description or "").lower())[:3])
