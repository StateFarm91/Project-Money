"""W4-FMBATCH1: dashboard order and compact drilldown (F-200, F-201).

- F-200 "On mobile, order the page by owner decision value: health/phase -> true active owner
  actions -> launch blockers -> product/creative truth -> spend -> operations detail/audit
  trail."
- F-201 "Large tables (audit trail, incidents, agents, learning changes) default to concise
  summaries with expandable/drilldown detail so mobile status remains readable without losing
  evidence."
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="fmb1_dash_")
DB_FILE = os.path.join(_TMP, "dash.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the test")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402

_HTML: dict = {}


def _page() -> str:
    if not _HTML:
        main.db.create_all()
        Registry(main.db).seed_defaults()
        with main.db.session() as s:
            s.add(Incident(signature="health:disk", severity="P1", summary="disk filling",
                           halts_publication=True, detail={}))
            s.add(Incident(signature="health:x", severity="P2", summary="minor", detail={}))
            for k in range(12):
                s.add(AuditLog(actor="orchestrator", action=f"test.action{k}", detail={}))
        _HTML["html"] = TestClient(main.app).get("/").text
    return _HTML["html"]


def _at(html, marker):
    i = html.find(marker)
    assert i >= 0, f"{marker!r} missing from the dashboard"
    return i


def test_f200_the_page_reads_in_owner_decision_order():
    html = _page()
    order = ["<h2>Health</h2>", "<h2>Waiting on the owner</h2>",
             "<h2>Launch readiness</h2>", "<h2>Open incidents</h2>", "<h2>Products</h2>",
             "<h2>Volume and operations</h2>", "<h2>Recent jobs</h2>", "<h2>Agents</h2>",
             "<h2>Audit trail</h2>"]
    pos = [_at(html, m) for m in order]
    assert pos == sorted(pos), list(zip(order, pos))
    # Spend sits after product truth and before the operations detail.
    spend = _at(html, "<h2>Spend governance</h2>")
    assert _at(html, "<h2>Products</h2>") < spend < _at(html, "<h2>Volume and operations</h2>")


def test_f201_large_tables_fold_to_a_summary_without_losing_rows():
    html = _page()
    folds = re.findall(r'<details class="fold"( open)?><summary>([^<]*)</summary>', html)
    summaries = [s for _o, s in folds]
    assert any(s.startswith("12 most recent audit rows") or "most recent audit rows" in s
               for s in summaries), summaries
    assert any(re.match(r"\d+ agents, \d+ enabled", s) for s in summaries), summaries
    assert any(s.startswith("2 open, 1 halting publication") for s in summaries), summaries
    # A halting incident is never hidden behind a fold: that fold opens by default.
    incident_fold = next(o for o, s in folds if s.startswith("2 open"))
    assert incident_fold == " open"
    # Nothing is dropped: every audited action is still in the page, inside its fold.
    audit = html[_at(html, "<h2>Audit trail</h2>"):]
    for k in range(12):
        assert f"test.action{k}" in audit, k


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
