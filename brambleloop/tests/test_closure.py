"""The Build 2 closure matrix: four final states, computed from evidence, never from the status."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.build2 import closure as C, executor, requirements as R

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

m = C.matrix()
check("every requirement lands in exactly one state and the counts sum to 320", sum(m["counts"].values()) == 320 == m["total"])
check("every executor gate is classified as owner, data or external waiting", all(C.kind_of(g.key) for g in executor.GATES))
try:
    C.kind_of("a_gate_nobody_classified"); check("an unclassified gate is refused", False)
except C.ClosureRefused:
    check("an unclassified gate is refused rather than filed where it flatters", True)
covered = [r for r in m["rows"] if r["status"] == R.COVERED]
check("a covered row is COMPLETE+PROVEN only when a named module exists and is tested", all((r["state"] == C.COMPLETE_PROVEN) == r["proof"]["proven"] for r in covered))
unproven = [r["id"] for r in covered if r["state"] == C.OPEN]
check("covered rows without proof are OPEN, never silently complete", all(r["why"].startswith("covered, but") for r in covered if r["state"] == C.OPEN))
print("     covered-without-proof:", len(unproven), unproven[:80])
check("the external blockers are stated in words with their evidence", all(("403" in v or "0 of 16" in v) for v in m["external_blockers"].values()))
check("a data-gated row is DATA-GATED only when its machinery exists, else OPEN (C-39)",
      all((r["state"] == C.DATA_GATED) == bool(r["proof"]["existing"])
          for r in m["rows"] if r["status"] == R.DATA_GATED))
_fake = R.Requirement(id=999, title="t", body="b", version="v", section="s",
                      status=R.DATA_GATED, note="needs launch data", parked_on="", proof="")
check("a data-gated row that names no module is OPEN, not parked on missing data",
      C.classify(_fake)["state"] == C.OPEN)
# Certification (C-41/C-43/C-59): a covered row whose only module nothing in the runtime
# reaches is not COMPLETE+PROVEN -- the failure that invalidated the 63f2493 closeout. And the
# same module wired into a runtime path is.
_dead = R.Requirement(id=998, title="t", body="b", version="v", section="s",
                      status=R.COVERED, note="", parked_on="",
                      proof="gateway/evals.py tests/test_gateway.py")
check("a covered row naming only an unreached module is OPEN, not COMPLETE+PROVEN",
      C.classify(_dead)["state"] == C.OPEN and "reached" in C.classify(_dead)["why"])
_live = R.Requirement(id=997, title="t", body="b", version="v", section="s",
                      status=R.COVERED, note="", parked_on="",
                      proof="commerce/kill_table.py tests/test_kill_table.py")
check("the same shape of row naming a runtime-reached module is COMPLETE+PROVEN",
      C.classify(_live)["state"] == C.COMPLETE_PROVEN)
_dead_data = R.Requirement(id=996, title="t", body="b", version="v", section="s",
                           status=R.DATA_GATED, note="", parked_on="",
                           proof="gateway/evals.py tests/test_gateway.py")
check("a data-gated row whose machinery nothing runs is OPEN (C-59)",
      C.classify(_dead_data)["state"] == C.OPEN)
# C-65: the three blind spots the 9434c53 audit found in the rule above.
# The fixture is a library only app/main.py imports (#4's preproduction, in no repair wave).
# commerce/offers.py served here until the C-64 repair wired it into portfolio.review -- the
# rule working, not a reason to loosen it. If this precondition fails, pick another static-only
# module; do not weaken the check.
from brambleloop.build2 import reachability as _reach
_pre = _reach.reached("commerce/preproduction.py")
check("fixture precondition: commerce/preproduction.py is still only statically imported",
      not _pre["reached"], str(_pre))
_static = R.Requirement(id=995, title="t", body="b", version="v", section="s",
                        status=R.COVERED, note="", parked_on="",
                        proof="commerce/preproduction.py runtime/release.py app/main.py "
                              "tests/test_preproduction.py")
_sv = C.classify(_static)
check("a covered row whose library only a static state() route touches is OPEN, and naming a "
      "runtime root beside it does not count as reach (C-65)",
      _sv["state"] == C.OPEN and "commerce/preproduction.py" in _sv["proof"]["unreached"],
      str(_sv["proof"]))
_orig_gate_for = C.executor.gate_for
C.executor.gate_for = lambda i: "owned_surfaces" if i in (994, 993) else _orig_gate_for(i)
try:
    _og = R.Requirement(id=994, title="t", body="b", version="v", section="s",
                        status=R.OWNER_GATED, note="", parked_on="",
                        proof="commerce/preproduction.py tests/test_preproduction.py")
    _ogv = C.classify(_og, gate_open={"owned_surfaces": False})
    check("an owner_gated row whose built half names unreached machinery is OPEN (C-65)",
          _ogv["state"] == C.OPEN and "not reached" in _ogv["why"], _ogv["why"])
    _og_live = R.Requirement(id=993, title="t", body="b", version="v", section="s",
                             status=R.OWNER_GATED, note="", parked_on="",
                             proof="commerce/kill_table.py tests/test_kill_table.py")
    _olv = C.classify(_og_live, gate_open={"owned_surfaces": False})
    check("the same owner_gated row naming live machinery stays OWNER-GATED",
          _olv["state"] == C.OWNER_GATED and _olv["gate_checked"] is True, _olv["why"])
    _unchecked = C.classify(_og_live)
    check("with no database the gate is reported UNCHECKED, never as verified closed (C-65)",
          _unchecked["gate_open"] is None and _unchecked["gate_checked"] is False
          and "NOT checked live" in _unchecked["why"], _unchecked["why"])
finally:
    C.executor.gate_for = _orig_gate_for
check("the matrix without a database says its gates were not checked and names the rows resting "
      "on the registry's word", m["gates_checked_live"] is False
      and isinstance(m["gates_unchecked"], dict) and m["gates_unchecked"]["rows"])
check("a partial row with no gate is OPEN (executable work owed)", all(r["state"] == C.OPEN for r in m["rows"] if r["status"] in R.EXECUTABLE and not executor.gate_for(r["id"])))
r75 = next(r for r in m["rows"] if r["id"] == 75)
print("     #75:", r75["state"], r75["gate"], r75["why"][:80])
# an opened gate returns its requirements to OPEN
# (a parked row whose built half is live: one whose machinery is unreached is OPEN already, C-65)
parked = next((r for r in R.load() if r.parked_on and r.parked_on in C.OWNER_GATES
               and C.classify(r, gate_open={r.parked_on: False})["state"] != C.OPEN), None)
check("a parked row with a live built half exists to test the reopening on", parked is not None)
if parked:
    row = C.classify(parked, gate_open={parked.parked_on: True})
    check("an opened gate returns its requirement to OPEN rather than leaving it parked", row["state"] == C.OPEN and "opened" in row["why"])
check("the closeout bar is open == 0 and is reported as a boolean, not a percentage", m["closed_out"] == (m["counts"][C.OPEN] == 0))
print("     matrix:", m["counts"], "closed_out:", m["closed_out"])

# the route reports the same matrix, with gates checked live against the database
import tempfile as _tf
_TMP = _tf.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/app.sqlite"
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
from fastapi.testclient import TestClient  # noqa: E402
from brambleloop.app import main as _main  # noqa: E402
with TestClient(_main.app) as _c:
    _r = _c.get("/api/closure")
    _j = _r.json() if _r.status_code == 200 else {}
check("/api/closure serves the matrix with gates checked live", _r.status_code == 200 and _j.get("gates_checked_live") is True and _j.get("gates_unchecked") is None and sum(_j.get("counts", {}).values()) == 320, str(_r.status_code))
check("/api/closure agrees with the module on every state count except gate-opened rows", set(_j.get("counts", {})) == set(m["counts"]))
print(f"\n  {PASSED} passing, {FAILED} failing"); sys.exit(1 if FAILED else 0)
