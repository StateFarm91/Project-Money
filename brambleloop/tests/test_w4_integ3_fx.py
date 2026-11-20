"""W4-INTEG3: the one assumed USD/CAD rate moves to the Bank of Canada reference (2026-10-16).

The old 1/0.715 = 1.3986 reserved every USD-priced call about 1.2% low against its CAD ceiling
(VISREF.md row 18). The reference is now 1 USD = CA$1.4154. No ceiling, cap or limit changes:
they are all stated in CAD and none of them reads the rate.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_integ3_fx.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def test_the_reference_is_the_bank_of_canada_rate_for_2026_10_16():
    from brambleloop.core import fx

    assert fx.ASSUMED_CAD_PER_USD == 1.4154
    assert fx.ASSUMED_RATE_AS_OF == "2026-10-16"
    assert "Bank of Canada" in fx.ASSUMED_RATE_SOURCE
    assert abs(fx.ASSUMED_CAD_PER_USD * fx.ASSUMED_USD_PER_CAD - 1.0) < 1e-12
    # Conservative versus the rate it replaces: a USD bill never reserves less CAD than before.
    assert fx.ASSUMED_CAD_PER_USD > 1.0 / 0.715


def test_every_consumer_reads_the_new_rate():
    from brambleloop.core import fx
    from brambleloop.finance import currency
    from brambleloop.gateway import anthropic, image_bench, images, routing
    from brambleloop.scale import target
    from brambleloop.visual import d_judge

    for v in (routing.USD_PER_CAD, currency.ASSUMED_USD_PER_CAD, target.USD_PER_CAD):
        assert v == fx.ASSUMED_USD_PER_CAD
    for v in (anthropic.USD_TO_CAD, images.USD_TO_CAD, image_bench.USD_TO_CAD,
              d_judge.USD_TO_CAD):
        assert v == 1.4154
    # The labels say the rate they convert at, not a stale literal.
    assert f"{fx.ASSUMED_USD_PER_CAD:.4f}" in routing.FX_NOTE and "1.4154" in routing.FX_NOTE
    assert "0.715 " not in routing.FX_NOTE
    src = (ROOT / "src/brambleloop/finance/listing_costs.py").read_text()
    assert "assumed 0.715" not in src


def test_a_usd_cost_reserves_at_the_new_rate():
    from brambleloop.finance import currency

    out = currency.to_reporting(currency.Money(10.0, "USD"), currency.assumed_rate())
    assert out["converted"] is True
    assert out["reporting"]["amount"] == 14.154, out
    assert out["rate"]["measured"] is False  # still an assumption, labelled so


def test_no_limit_reads_the_rate_and_no_ceiling_moved():
    """Every ceiling is stated in CAD; none is derived from the exchange rate."""
    from brambleloop.finance import spend_policy

    for path in ("src/brambleloop/finance/spend_policy.py", "src/brambleloop/agents/registry.py"):
        tree = ast.parse((ROOT / path).read_text())
        names = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.endswith("fx") or "routing" in m for m in names), (path, names)
    # The values at production 1b21e81, unchanged.
    assert spend_policy.CEILING_CAD == 100.0
    assert spend_policy.ceiling_cad() == 100.0
    assert spend_policy.INFRA_CEILING_CAD == 20.0
    assert spend_policy.INFRA_MONTHLY_CAD == 7.0
    assert spend_policy.BENCHMARK_BUDGET_CAD == 50.0


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
