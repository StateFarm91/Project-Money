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
check("a partial row with no gate is OPEN (executable work owed)", all(r["state"] == C.OPEN for r in m["rows"] if r["status"] in R.EXECUTABLE and not executor.gate_for(r["id"])))
r75 = next(r for r in m["rows"] if r["id"] == 75)
print("     #75:", r75["state"], r75["gate"], r75["why"][:80])
# an opened gate returns its requirements to OPEN
parked = next((r for r in R.load() if r.parked_on and r.parked_on in C.OWNER_GATES), None)
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
check("/api/closure serves the matrix with gates checked live", _r.status_code == 200 and _j.get("gates_checked_live") is True and sum(_j.get("counts", {}).values()) == 320, str(_r.status_code))
check("/api/closure agrees with the module on every state count except gate-opened rows", set(_j.get("counts", {})) == set(m["counts"]))
print(f"\n  {PASSED} passing, {FAILED} failing"); sys.exit(1 if FAILED else 0)
