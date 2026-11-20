"""W4-B2: Build 2's dashboard figures and ledger come from the closure, and #280's
fashion-and-home half reads the connected culture feed instead of claiming none exists."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E401,E702

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from brambleloop.build2 import closure as C, requirements as R  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import colour  # noqa: E402

FAILS = 0


def check(name, ok, detail=""):
    global FAILS
    FAILS += not ok
    print(("OK " if ok else "FAIL ") + name + ("" if ok else f" -- {detail}"))


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _fake_get_for(sweep_no):
    def get(url):
        # Teal climbs between sweeps, mauve falls; every other topic is flat. Synthetic, never
        # fetched.
        last = 100
        if "/Teal/" in url:
            last = 100 if sweep_no == 0 else 180
        if "/Mauve/" in url:
            last = 200 if sweep_no == 0 else 120
        return {"items": [{"timestamp": f"202609{d:02d}00", "views": 200}
                          for d in range(1, 28)]
                + [{"timestamp": "2026092800", "views": last}]}
    return get


# --- #280: colour attention from the connected feed, labelled a proxy -----------------------
db = _db()
empty = colour.forecast(db)["fashion_and_home_signals"]
check("with no colour reading the fashion/home half is unmeasurable with a reason, not zero",
      empty["measurable"] is False and "reason" in empty and "proxy" in empty["basis"])
first = colour.sweep_colour_signals(db, today=date(2026, 9, 30), get=_fake_get_for(0))
check("a colour sweep records every colour and home topic through the culture feed",
      first["recorded"] == len(colour.colour_signal_keys()) and not first["failures"], first)
one = colour.forecast(db)["fashion_and_home_signals"]
check("one reading per colour is a level, not a direction: still unmeasurable",
      one["measurable"] is False and len(one["colours"]) == len(colour.COLOUR_TOPICS))
colour.sweep_colour_signals(db, today=date(2026, 10, 1), get=_fake_get_for(1))
two = colour.forecast(db)["fashion_and_home_signals"]
check("two dated readings give each colour a direction, rising and falling named",
      two["measurable"] is True and "teal" in two["rising"] and "mauve" in two["falling"], two)
check("the reading carries its basis: reference reading, not fashion sales or a forecast",
      "not fashion sales" in two["basis"])
check("the home topic is context, never counted as a colour",
      any(c["signal_key"] == "home:interior_design" for c in two["context"])
      and all(c["signal_key"].startswith("colour:") for c in two["colours"]))
check("brambleloop performance stays parked on customers", "customers gate" in
      colour.forecast(db)["brambleloop_performance"]["reason"])

from brambleloop.build2 import reachability  # noqa: E402

live = reachability.function_reached("seasonal/colour.py", "sweep_colour_signals")
check("the colour sweep is reached from the culture.sweep handler", live["reached"], live)

# --- dashboard and ledger from the closure ---------------------------------------------------
m = C.matrix()
d = C.dashboard(m=m)
cov = R.coverage()
check("dashboard figures partition the 320 rows",
      d["complete"] + d["owner_gated"] + d["data_gated"] + d["external_gated"]
      + d["open_defects"] == d["total"] == 320, d)
check("dashboard executable remaining is OPEN work only, never parked rows",
      d["executable_remaining"] == m["counts"][C.OPEN])
check("registry 'executable_remaining' counts parked partial rows; the dashboard does not "
      "inherit that", cov["executable_remaining"] - cov["executable_unparked"]
      == cov["executable_parked_on_a_gate"] and d["executable_remaining"] <= cov["executable_unparked"]
      + sum(1 for r in m["rows"] if r["state"] == C.OPEN and r["status"] != R.PARTIAL), (d, cov))
check("proven + not-applicable == complete (directives are not counted as built machinery)",
      d["proven"] + d["not_applicable"] == d["complete"] and d["not_applicable"] >= 1, d)

led = C.ledger()
rows = led["rows"]
check("ledger has one row per requirement", len(rows) == 320 and len({r["id"] for r in rows}) == 320)
assert rows, "ledger rows must not be empty"
check("every ledger row is in the ledger vocabulary",
      all(r["state"] in C.LEDGER_STATES for r in rows))
mapped = {"PROVEN": C.COMPLETE_PROVEN, "NOT-APPLICABLE": C.COMPLETE_PROVEN,
          "OWNER-GATED": C.OWNER_GATED, "DATA-GATED": C.DATA_GATED,
          "EXTERNAL-GATED": C.EXTERNAL_BLOCKED, "OPEN-DEFECT": C.OPEN}
check("ledger states agree with the closure matrix row for row",
      all(mapped[r["state"]] == r["closure_state"] for r in rows))
gated = [r for r in rows if r["state"] in ("OWNER-GATED", "DATA-GATED", "EXTERNAL-GATED")]
assert gated, "there are gated rows to check"
check("every gated row names its exact gate, its kind and what opens it",
      all(r["gate"]["key"] and r["gate"]["kind"] == {"OWNER-GATED": C.OWNER_GATED,
          "DATA-GATED": C.DATA_GATED, "EXTERNAL-GATED": C.EXTERNAL_BLOCKED}[r["state"]]
          and (r["gate"]["opens_when"] or r["gate"]["external_evidence"]) for r in gated
          if "gate" in r) and all("gate" in r or r["registry_status"] == R.DATA_GATED
                                  for r in gated))
proven = [r for r in rows if r["state"] == "PROVEN"]
assert proven
check("every PROVEN row carries a test, an artefact and a runtime consumer",
      all(r["evidence"]["artefacts"] and (r["evidence"]["tests"] or r["evidence"]["tested_modules"])
          and r["evidence"]["runtime_consumers"] for r in proven),
      [r["id"] for r in proven if not r["evidence"]["runtime_consumers"]][:10])
check("a gate given as open returns its rows to OPEN-DEFECT rather than leaving them parked",
      all(r["state"] == "OPEN-DEFECT" for r in C.ledger(gate_open={"ad_authority": True},
          gate_source="test")["rows"] if r["id"] in (294, 295)))

print("FAILED" if FAILS else "ALL OK", FAILS)
sys.exit(1 if FAILS else 0)
