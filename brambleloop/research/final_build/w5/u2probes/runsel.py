import sys, traceback
sys.path[:0] = ["src", "tests"]
mod = __import__(sys.argv[1]); fns = sys.argv[2].split(",")
failed = 0
for fn in fns:
    try:
        getattr(mod, fn)(); print("OK", fn)
    except BaseException as e:
        failed += 1; print("FAIL", fn, repr(e)[:200])
sys.exit(1 if failed else 0)
