"""Run a test file as __main__ with every job handler timed; print the slowest job types."""
import atexit, collections, runpy, sys, time
from brambleloop.runtime import worker
T = collections.defaultdict(lambda: [0, 0.0, 0.0])
real_get = worker.HandlerRegistry.get
def timed_get(self, job_type):
    fn = real_get(self, job_type)
    if fn is None:
        return None
    def wrapped(ctx, _fn=fn, _jt=job_type):
        t0 = time.monotonic()
        try:
            return _fn(ctx)
        finally:
            d = time.monotonic() - t0; r = T[_jt]; r[0] += 1; r[1] += d; r[2] = max(r[2], d)
    return wrapped
worker.HandlerRegistry.get = timed_get
@atexit.register
def report():
    rows = sorted(T.items(), key=lambda kv: -kv[1][1])[:80]
    print("== HANDLER TIMES (type, n, total s, max s)")
    for k, (n, tot, mx) in rows:
        print(f"   {k:45s} {n:4d} {tot:8.1f} {mx:7.1f}")
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
