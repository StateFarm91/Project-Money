import datetime as _dt, sys, importlib
FIXED = _dt.datetime.fromisoformat(sys.argv[1])
class FakeDT(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED if tz else FIXED.replace(tzinfo=None)
_dt.datetime = FakeDT          # before any import that does `from datetime import datetime`
sys.path[:0] = ["src", "tests"]
import test_w4_ccfm1 as T
from brambleloop.app.command_center import company
company.datetime = FakeDT
assert T.NOW == FIXED, T.NOW
for n in ("test_completed_trend_is_measured_per_department_and_day",
          "test_departments_carry_objective_spend_and_trend"):
    getattr(T, n)(); print("OK", n, "at", FIXED.isoformat())
