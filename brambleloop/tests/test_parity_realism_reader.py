"""Parity's LIFESTYLE_QUALITY reads the realism judgement product-first frames actually record.

owned_photography writes realism as named checks under `inspection.realism`; parity read only a
top-level `photographic_realism`, so every flat product read as unjudged (2026-09-27)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.visual import parity as P

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

def owned(realism, judged=True):
    return {"role": "hero", "inspection": {"realism_judged": judged, "realism": realism}}

def lifestyle(frames):
    return P.assess(frames)["dimensions"][P.LIFESTYLE_QUALITY]

def state(v):
    return {"pass": True, "fail": False, "unjudged": None}[v["verdict"]]

clear = lifestyle([owned({"lighting": True, "texture": True})])
blocked = lifestyle([owned({"lighting": True, "texture": False})])
partial = lifestyle([owned({"lighting": True, "texture": None})])
unjudged = lifestyle([owned({"lighting": True}, judged=False)])
check("an owned frame whose every realism check passed is judged clear", state(clear) is True, str(clear))
check("any failed realism check blocks, whatever else passed", state(blocked) is False, str(blocked))
check("an unanswered check is not a pass", state(partial) is None, str(partial))
check("a frame the realism judge never ran on stays unjudged", state(unjudged) is None, str(unjudged))
top = lifestyle([{"role": "hero", "photographic_realism": {"verdict": "blocked"}}])
check("the model path's top-level verdict still wins where it exists", state(top) is False, str(top))
print(f"\n  {PASSED} passing, {FAILED} failing"); sys.exit(1 if FAILED else 0)
