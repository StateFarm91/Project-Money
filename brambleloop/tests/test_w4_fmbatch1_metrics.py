"""F-618: one canonical definition per KPI; the callers that report them agree with it, and
UNKNOWN is None, never 0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.analytics import metrics as M  # noqa: E402
from brambleloop.growth import loops  # noqa: E402
from brambleloop.scale import runrate  # noqa: E402


def test_definitions_and_unknown_rule():
    assert M.conversion(3, 120) == 0.025 and M.ctr(120, 4000) == 0.03
    assert M.cac(60.0, 4) == 15.0 and M.roas(90.0, 30.0) == 3.0
    for fn, args in ((M.conversion, (3, 0)), (M.conversion, (None, 10)), (M.ctr, (5, None)),
                     (M.refund_rate, (1, 0)), (M.cac, (10.0, 0)), (M.roas, (10.0, 0))):
        assert fn(*args) is None, (fn.__name__, args)
    assert M.contribution_margin(100.0, 10.0, None) is None
    assert set(M.REGISTRY) >= {"conversion", "ctr", "aov", "refund_rate", "cac", "roas",
                               "contribution_margin"}


def test_runrate_reports_the_canonical_rates():
    o = runrate.Observed(visits=200, impressions=5000, orders=6, revenue_cad=54.0,
                         contribution_cad=30.0)
    assert o.conversion == M.conversion(6, 200)
    assert o.ctr == M.ctr(200, 5000)
    assert o.aov_cad == M.aov(54.0, 6)
    assert o.revenue_per_visitor == M.revenue_per_visitor(54.0, 200)
    assert o.contribution_per_visitor == M.contribution_per_visitor(30.0, 200)
    assert runrate.Observed().conversion is None


def test_growth_loops_conversion_is_the_canonical_one_rounded():
    loop = loops.Loop(key="x", name="x", visits=300, orders=7)
    assert loop.conversion == round(M.conversion(7, 300), 4)
    assert loops.Loop(key="y", name="y").conversion is None


def test_books_contribution_margin_is_the_canonical_one():
    from brambleloop.finance import books

    pl = books.ProfitAndLoss(period_start="2026-10-01", period_end="2026-10-31",
                             gross_sales_cad=120.0, refunds_cad=10.0, platform_fees_cad=12.5,
                             cost_by_kind={"ads": 7.5})
    assert pl.contribution_margin_cad == round(M.contribution_margin(
        pl.net_sales_cad, 12.5, 7.5), 2) == 90.0


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
