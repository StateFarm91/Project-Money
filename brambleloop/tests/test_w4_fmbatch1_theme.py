"""F-670: the Studio shell has light and dark tokens (prefers-color-scheme), no hard-coded
surface colours outside the token block, and a chart component with drill-down links."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1th_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/t.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()


def test_tokens_cover_light_and_dark_and_rules_use_them():
    css = main._CSS
    assert "prefers-color-scheme:dark" in css and "color-scheme:light dark" in css
    rules = css.split("--grey-bg:#262d35;--alarm:#ff7b72}}", 1)[1]
    assert not re.findall(r"#[0-9a-fA-F]{3,6}\b", rules), re.findall(r"#[0-9a-fA-F]{3,6}\b", rules)


def test_sparkline_component():
    svg = main._sparkline([0, 2, 1, 4], label="spend")
    assert svg.startswith("<svg") and 'aria-label="spend"' in svg
    pts = re.search(r'points="([^"]+)"', svg).group(1).split()
    assert len(pts) == 4 and pts[3].endswith(",2.0")      # the peak touches the top
    assert "<script" not in svg


def test_dashboard_renders_trends_with_drill_down():
    with main.db.session() as s:
        s.add(CostEntry(agent="a", kind="model", amount_cad=1.5, purpose="p"))
    html = TestClient(main.app).get("/").text
    assert "<h2>Trends</h2>" in html and html.count('class="spark"') >= 2
    assert 'href="/api/spend-report">drill down' in html
    assert "CA$1.50 over 14 days" in html


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
