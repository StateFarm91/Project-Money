"""W4-B2 (#147): culture findings reach Seasonal Planning and Content, which read their lesson
inboxes where they decide and record acting on them -- not only Market Radar and SEO."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E401,E702

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.growth import content  # noqa: E402
from brambleloop.improve import bus  # noqa: E402
from brambleloop.seasonal import daily  # noqa: E402
from brambleloop.seasonal.calendar import rolling  # noqa: E402

FAILS = 0


def check(name, ok, detail=""):
    global FAILS
    FAILS += not ok
    print(("OK " if ok else "FAIL ") + name + ("" if ok else f" -- {detail}"))


db = Database("sqlite://")
db.create_all()
cal = rolling(date(2026, 9, 1))
assert cal["events"], "calendar has events"

none = daily.culture_lessons(db, cal)
check("with no cultural lesson no occasion carries one (nothing invented)",
      none["applied"] == [] and none["events_read"] == len(cal["events"]), none)

# The two statements culture.radar publishes, for a Halloween territory and its timing.
terr = bus.publish(db, origin_cell="product_creativity", subject="cultural_territory",
                   statement=("cultural territory halloween (halloween crochet) is rising in "
                              "public interest and worth pursuing where it fits the catalogue"),
                   evidence_ref="culture:halloween:rising", confidence="observed")
timing = bus.publish(db, origin_cell="product_creativity", subject="cultural_timing",
                     statement=("halloween interest peaks 21 days relative to the benchmark's "
                                "entry; time halloween launches and content to that lead"),
                     evidence_ref="culture_timing:halloween:21", confidence="measured")

got = daily.culture_lessons(db, cal)
events = {a["event"]: {l["id"] for l in a["lessons"]} for a in got["applied"]}
check("Seasonal Planning attaches both Halloween lessons to the Halloween plan only",
      events.get("Halloween") == {terr, timing} and list(events) == ["Halloween"], got)
acted = {l["id"]: l for l in bus.inbox(db, daily.SEASONAL_CELL, unacted_only=False)}
check("Seasonal Planning's decision is recorded through bus.acted_on",
      not any(l["id"] in (terr, timing) for l in bus.inbox(db, daily.SEASONAL_CELL)), acted)

facts = content.ProductFacts(slug="ghost-garland", title="Ghost Garland", category="seasonal_decor",
                             size_label=None, difficulty="easy", stitches=["sc"],
                             colors=["white"], yardage_line="about 100 m",
                             maker_hours=(3.0, 5.0), season="halloween", price_cad=8.0)
pieces = content.build_ecosystem(facts, launch_on=date(2026, 10, 10))
noted = content.apply_cultural_timing(db, facts, pieces)
check("Content attaches the timing lesson (not the territory one) to its plan",
      [n["lesson"] for n in noted] == [timing], noted)
pre = [p for p in pieces if p.channel in content.PRE_LAUNCH_CHANNELS]
assert pre, "pre-launch pieces exist"
check("every pre-launch piece carries it; post-launch pieces do not",
      all(p.detail.get("cultural_timing") == noted for p in pre)
      and not any("cultural_timing" in p.detail for p in pieces
                  if p.channel not in content.PRE_LAUNCH_CHANNELS))
check("Content's decision is recorded through bus.acted_on",
      timing not in {l["id"] for l in bus.inbox(db, content.CONTENT_CELL)})

other = content.ProductFacts(slug="lace-runner", title="Lace Runner", category="runner",
                             size_label=None, difficulty="easy", stitches=["sc"], colors=["white"],
                             yardage_line="about 100 m", maker_hours=(3.0, 5.0), season=None,
                             price_cad=8.0)
check("a product the lesson does not name gets no cultural timing",
      content.apply_cultural_timing(db, other, content.build_ecosystem(
          other, launch_on=date(2026, 10, 10))) == [])

from brambleloop.build2 import reachability  # noqa: E402

for mod, fn in (("seasonal/daily.py", "culture_lessons"),
                ("growth/content.py", "apply_cultural_timing")):
    r = reachability.function_reached(mod, fn)
    check(f"{mod}:{fn} is reached from a live handler", r["reached"], r)

print("FAILED" if FAILS else "ALL OK", FAILS)
sys.exit(1 if FAILS else 0)
