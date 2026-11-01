"""Build each product CIR twice; report any mutable object (dict/list/dataclass) shared
between the two builds (aliasing => an in-place edit of one build leaks into the next)."""
import sys, dataclasses, inspect
sys.path[:0] = ["src"]
from brambleloop.cir.model import CIR
from brambleloop.products import launch0, moment_candidates, garments, pipeline_board, vessels, texture, nordic_forest, builder

def walk(o, path, seen, out):
    if isinstance(o, (str, int, float, bool, type(None), tuple, frozenset)) and not isinstance(o, tuple):
        return
    if isinstance(o, tuple):
        for i, x in enumerate(o): walk(x, f"{path}[{i}]", seen, out)
        return
    if id(o) in seen: return
    seen.add(id(o)); out[id(o)] = path
    if isinstance(o, dict):
        for k, v in o.items(): walk(v, f"{path}.{k}", seen, out)
    elif isinstance(o, list):
        for i, v in enumerate(o): walk(v, f"{path}[{i}]", seen, out)
    elif dataclasses.is_dataclass(o):
        for f in dataclasses.fields(o): walk(getattr(o, f.name), f"{path}.{f.name}", seen, out)
    elif hasattr(o, "__dict__"):
        for k, v in vars(o).items(): walk(v, f"{path}.{k}", seen, out)

fns = {}
for modname, mod in [("launch0.BUILDERS", getattr(launch0, "BUILDERS", {})),
                     ("launch0.PROPOSED", getattr(launch0, "PROPOSED_BUILDERS", {})),
                     ("moment.ENGINEERED", moment_candidates.ENGINEERED),
                     ("garments.DESIGNS", garments.DESIGNS),
                     ("pipeline_board.CREATIVE", pipeline_board.CREATIVE_ENGINEERED)]:
    for k, f in mod.items(): fns[f"{modname}:{k}"] = f
for m in (vessels, texture, nordic_forest, builder):
    for n, f in inspect.getmembers(m, inspect.isfunction):
        if n.startswith("build") and f.__module__ == m.__name__:
            fns[f"{m.__name__.split('.')[-1]}.{n}"] = f
bad = 0; n_cir = 0; skipped = []
for name, f in sorted(fns.items()):
    try:
        a, b = f(), f()
    except TypeError:
        try:
            skipped.append(name + "(needs args)")
            continue
        except Exception: continue
    except Exception as e:
        print("ERR", name, type(e).__name__, str(e)[:80]); continue
    if not isinstance(a, CIR):
        skipped.append(name)
        continue
    n_cir += 1
    oa, ob = {}, {}
    walk(a, "cir", set(), oa); walk(b, "cir", set(), ob)
    shared = sorted(oa[i] for i in set(oa) & set(ob))
    if shared:
        bad += 1; print("SHARED", name, shared[:6], f"(+{len(shared)-6})" if len(shared) > 6 else "")
print("CIRs compared", n_cir, "skipped", skipped); print("checked", len(fns), "builders;", bad, "share mutable state")
extra = {}
for slug, d in builder.CATALOGUE.items():
    extra[f"builder.build:{slug}"] = (lambda d=d: builder.build(d))
for k, f in garments.DESIGNS.items():
    g = f()
    extra[f"garments:{k}"] = (lambda f=f: [c for c in (f().build_all() if hasattr(f(), "build_all") else [])])
bad2 = 0
for name, f in sorted(extra.items()):
    try:
        a, b = f(), f()
    except Exception as e:
        print("ERR", name, type(e).__name__, str(e)[:100]); continue
    oa, ob = {}, {}
    walk(a, "x", set(), oa); walk(b, "x", set(), ob)
    shared = sorted(oa[i] for i in set(oa) & set(ob))
    if shared:
        bad2 += 1; print("SHARED", name, shared[:6], len(shared))
print("extra checked", len(extra), "shared", bad2)
