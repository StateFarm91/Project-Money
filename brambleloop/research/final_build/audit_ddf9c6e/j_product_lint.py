from brambleloop.store_foundation.lint import lint, is_truthful
cases = [
 "Since 2014 we have made patterns", "Est 2015", "Serving makers since the early days",
 "Over a decade of experience", "10 years in the craft", "A trusted name in crochet",
 "Join 2,000 makers", "Our 1000+ happy customers", "Rated 4.9 stars", "Five stars from buyers",
 "Best-selling pattern", "The b e s t pattern", "Bestselling", "Ƅest crochet patterns", "the ᴬest",
 "Proudly tested by real crocheters", "Pattern tested by crocheters", "We have tested every row",
 "Handmade with love", "hand made in Canada", "Hand-crocheted sample shown", "photo of the finished blanket",
 "Only a few left", "Last chance", "Sale today", "Save 20 percent", "Half price this week", "20% off",
 "Our shop has been around for years", "My nan taught me", "Our grandmother's recipe", "Passed down through generations",
 "Over 500 patterns sold", "Customers love it", "Shop reviews are glowing", "Thousands of makers",
 "Premium quality", "Top quality", "Most-loved pattern", "Etsy's choice", "Etsy Pick", "Award winning",
 "Not a photograph, but we crocheted this", "no sample has been photographed and we crocheted it",
 "Safe for babies", "Non-toxic and baby safe", "Oeko-Tex certified", "Hypoallergenic",
 "Trusted by makers", "Trusted by 50 makers", "Established in the 2010s", "Est. two thousand fifteen",
 "BEST", "b​est pattern", "be​st", "Тhe best",  # cyrillic T
 "Over twenty years of crochet", "Two decades", "Fifteen years in business",
 "A beloved pattern", "Everyone's favourite", "Our bestselling",
]
for c in cases:
    f = lint(c, voice=False)
    print("CAUGHT " if f else "MISSED ", repr(c), [x["code"] for x in f])
print("== negation-window evasion (negatable rules: PHYSICAL_MAKING, SAFETY_CERT)")
for c in ["Not a toy, we crocheted this basket ourselves", "No fuss, no waiting: we crocheted and photographed every sample", 
          "Never boring, always lab-tested", "No sample was ever photographed", "we crocheted this", "Not a photograph", "We never skip it and these are baby safe"]:
    print("CAUGHT " if lint(c, voice=False) else "MISSED ", repr(c))
