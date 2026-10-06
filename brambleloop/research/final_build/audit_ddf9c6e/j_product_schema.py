from brambleloop.publish import listing_schema as LS
from brambleloop.gates import policy
from brambleloop.commerce import search, seo
for tags in (["ｄｉｓｎｅｙ"], ["ＤＩＳＮＥＹ ｂａｓｋｅｔ"], ["disney basket"], ["最佳"], ["Basket"]*2):
    print(tags, "tag_problems:", LS.tag_problems(tags))
for title in ("ＤＩＳＮＥＹ Basket Crochet Pattern PDF", "Disney Basket Crochet Pattern PDF"):
    print(repr(title), "title_problems:", LS.title_problems(title))
print("IP terms sample:", list(policy._IP_TERMS)[:6])
print("policy claim fn names:", [n for n in dir(policy) if "claim" in n.lower() or "ip" in n.lower()][:10])
