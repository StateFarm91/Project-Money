"""The dashboard's spend block states the controls that exist, not the one table that is empty.

It printed "No spend limits configured." while every model call was refused against a monthly
ceiling and 24 agent permissions -- true of the paid-media SpendLimit table and false of the
company (cost-governance audit, 2026-09-26)."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/app.sqlite"
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.finance import spend_policy  # noqa: E402

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))


with TestClient(main.app) as c:
    html = main._spend_governance_html()
    data = main._spend_governance_data()
    page = c.get("/").text
check("the block names the monthly ceiling as a figure", f"{spend_policy.CEILING_CAD:.2f}" in html
      or f"{int(spend_policy.CEILING_CAD)}" in html, html[:300])
check("scoped paid-media caps are reported as none configured with the reason",
      "Scoped caps (paid media): none configured" in html and "advertising authority" in html)
check("the bare sentence that said the company had no limits is gone",
      "No spend limits configured." not in html and "No spend limits configured." not in page)
check("the dashboard page renders the governance block", "Scoped caps" in page)
check("the data behind the block is structured, not only prose", isinstance(data, dict) and data)
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
