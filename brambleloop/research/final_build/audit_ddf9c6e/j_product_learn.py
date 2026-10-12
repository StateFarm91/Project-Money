import json, tempfile, os
from brambleloop.improve import invariants as I, policy_loops as P
from brambleloop.core.db import Database
print("== invariants.check attempts (loop seo_lesson_match tunable min_shared 1..4)")
lp = P.BY_KEY["seo_lesson_match"]; t = lp.tunable()
for name, val in [("min_shared",3),("Min-Shared",3),("min shared",3),("min_shared ",3),("minshared",3),
    ("min_shared",0),("min_shared",9),("min_shared",True),("min_shared",float("nan")),("min_shared","2"),
    ("min_shared",[1]),("min_shared",{"a":1}),("MIN_SHARED",1),("min_shared​",2),("ｍｉｎ_shared",2),
    ("evidence_floor",1),("MIN_MATCHED",1),("min_matched",1),("MIN_DECISIONS",1),("regression_margin",0.5),
    ("publish_gate",1),("catalogue_depth",1),("catalogue_depth_min",1),("depth",1),("min_catalog",1),
    ("size_count_as_product",1),("price_floor",1),("max_tags",99),("nested",{"min_shared":1})]:
    try:
        v = I.check(name, val, tunable=t); print(("ALLOW " if v.ok else "refuse"), repr(name), repr(val), v.invariant)
    except Exception as e: print("EXC", repr(name), type(e).__name__, e)
print("== check_payload with alias twin keys")
print([v.to_dict() for v in I.check_payload({"min_shared":2,"Min-Shared":3}, tunable=t)])
print("== active() reading a registry payload spelled with an alias")
d = tempfile.mkdtemp(); db = Database(f"sqlite:///{d}/x.sqlite"); db.create_all()
from brambleloop.improve import league
league.register(db, kind="scoring", key=lp.registry_key, payload=json.dumps({"Min-Shared": 3}),
    why_changed="alias payload planted directly to probe the read guard", tests_declared=("t",),
    affected_departments=("seo_search",), incumbent=True)
try: print(P.active(db, "seo_lesson_match"))
except Exception as e: print("EXC in active():", type(e).__name__, e)
print("== submit() with alias key")
d2 = tempfile.mkdtemp(); db2 = Database(f"sqlite:///{d2}/y.sqlite"); db2.create_all()
for params in ({"Min-Shared": 3}, {"min_shared": 3}):
    try: print(params, "->", P.submit(db2, "seo_lesson_match", params, proposed_by="experiment_designer"))
    except Exception as e: print(params, "EXC", type(e).__name__, e)
