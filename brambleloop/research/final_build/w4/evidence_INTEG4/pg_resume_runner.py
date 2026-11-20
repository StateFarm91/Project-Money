"""Run tests/test_w4_integ4_resume.py and test_w4_credhealth's restart tests on PostgreSQL:
the experiments harness is imported from a copy whose only changes are ROOT and the DB URL."""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("test_w4_controlled_experiments", sys.argv[1])
mod = importlib.util.module_from_spec(spec); sys.modules["test_w4_controlled_experiments"] = mod
spec.loader.exec_module(mod)
import test_w4_credhealth as CH, test_w4_integ4_resume as R
assert "postgresql" in str(CH.DB.engine.url)
names = [n for n in dir(R) if n.startswith("test_")] + \
        [n for n in dir(CH) if n.startswith("test_restart")]
fails = 0
for n in names:
    fn = getattr(R, n, None) or getattr(CH, n)
    try:
        fn(); print("OK  ", n)
    except Exception as e:
        fails += 1; print("FAIL", n, type(e).__name__, str(e)[:300])
print(f"{len(names)-fails}/{len(names)} passed on {CH.DB.engine.url.get_backend_name()}")
sys.exit(1 if fails else 0)
