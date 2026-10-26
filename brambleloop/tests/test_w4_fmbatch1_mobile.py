"""F-653: phone and tablet access -- responsive breakpoints, tables that scroll in their own
box, and the compact owner view at /m."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1m_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/m.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
C = TestClient(main.app)


def test_breakpoints_exist_for_phone_and_tablet():
    assert "@media (max-width:600px)" in main._CSS
    assert "@media (min-width:601px) and (max-width:1024px)" in main._CSS
    assert ".tw{overflow-x:auto" in main._CSS


def test_every_dashboard_table_scrolls_inside_its_own_box():
    html = C.get("/").text
    tables = html.count("<table>")
    assert tables > 3
    assert html.count('<div class="tw"><table>') == tables, (
        tables, html.count('<div class="tw"><table>'))


def test_mobile_owner_view():
    r = C.get("/m")
    assert r.status_code == 200
    html = r.text
    assert 'name="viewport" content="width=device-width' in html
    for h in ("<h2>Health</h2>", "<h2>Waiting on you</h2>", "<h2>Today</h2>"):
        assert h in html, h
    assert "unavailable:" not in html, re.findall(r"unavailable:[^<]*", html)
    assert "<table" not in html                       # cards only: nothing wider than a phone
    assert 'href="/"' in html


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
