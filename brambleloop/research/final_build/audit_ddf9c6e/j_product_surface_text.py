from brambleloop.store_foundation import content as C, readiness as R, lint
def S(key, value, group="shop"):
    return C.Surface(key=key, label=key, group=group, value=value, source="probe", etsy_location="x", entry="x")
probes = {
 "grid title":   S("opening_grid", [{"title": "Best-selling Crochet Basket, Trusted by 5,000 Makers, Since 2014", "plan_title":"x", "candidate":"c","qualifiers":[],"price_cad":6.5,"variant_count":1,"representative":{"build":"b"}}]),
 "dict nested":  S("about", {"story": ["Since 2014, thousands of makers trust us"]}),
 "dict str":     S("about", {"story": "Since 2014, thousands of makers trust us"}),
 "list of str":  S("trust_signals", ["Since 2014, thousands of makers trust us"]),
 "faq 'body'":   S("faq", [{"question":"q","body":"Trusted by thousands of makers since 2014"}]),
 "faq 'answer'": S("faq", [{"question":"q","answer":"Trusted by thousands of makers since 2014"}]),
}
for k, s in probes.items():
    t = s.text()
    print(f"{k:14} text()={t[:50]!r:55} lint findings={[f['code'] for f in lint.lint(t, voice=False)]}")
