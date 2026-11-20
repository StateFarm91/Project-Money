"""W4-FMBATCH1: F-621's KPI trend in the Command Center PWA -- static checks.

The Company view draws `kpi_trend_7d` (useful completions and defect dead letters per day) with
the shared dependency-free `barChart`, and an unmeasured trend reads Unknown with its reason,
never zeros. The rendered behaviour is checked in the browser harness
(tests/fixtures/cc_mock/check.mjs, run by test_v11_pwa_browser.py); this file pins the source.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src/brambleloop/app/command_center/static/js/views/company.js"
MOCK = ROOT / "tests/fixtures/cc_mock/data.mjs"


def test_company_view_draws_the_kpi_trend_with_the_shared_chart():
    src = JS.read_text(encoding="utf-8")
    assert "kpiTrend(it.kpi_trend_7d)" in src
    body = src[src.index("function kpiTrend("):]
    body = body[:body.index("\n}\n") + 2]
    assert body.count("barChart(") == 2, body
    assert "t.useful_completions" in body and "t.defect_dead_letters" in body
    assert 't.basis !== "measured"' in body and "UNKNOWN_TEXT" in body
    # No HTML sink and no default zero series.
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", body)
    assert "[0, 0" not in body and "fill(0)" not in body


def test_the_mock_carries_a_measured_and_an_unknown_trend():
    data = MOCK.read_text(encoding="utf-8")
    assert data.count("kpi_trend_7d") == 2
    assert 'kpi_trend_7d: { basis: "unknown"' in data


def test_company_js_parses():
    node = shutil.which("node")
    if not node:
        print("SKIP node not found")
        return
    r = subprocess.run([node, "--check", str(JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
