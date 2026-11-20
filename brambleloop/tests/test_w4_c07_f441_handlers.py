"""W4-C07: F-441 provider selection on trial records, and F-464's two render handlers.

F-464 finding, asserted rather than assumed: since F-852 the generative render paths behind
`assets.model_photography` and `assets.owned_photography` return the redraw refusal before any
provider is asked, so neither handler can hold a worker slot waiting on a render. The deferred
primitives (`images.submit_render` / `poll_render`, test_w4_c07_f464.py) are what a live render
path uses when one exists again. Fixtures only; CA$0."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402


def test_f441_trial_records_carry_all_six_selection_criteria():
    from brambleloop.visual import provider_trial as PT

    rows = [{"provider": "flux-2-pro", "slug": "a", "made": True, "spent_cad": 0.08,
             "texture_failed": [], "structural_failed": [], "photoreal_failed": [],
             "product_truth": "match", "photographic_realism": "clear",
             "usable_as_listing_asset": True},
            {"provider": "flux-2-pro", "slug": "a", "made": False,
             "why": "TransientError: poll 503", "spent_cad": 0.0},
            {"provider": "flux-2-pro", "slug": "b", "made": True, "spent_cad": 0.08,
             "texture_failed": ["texture_not_repeating"], "structural_failed": [],
             "photoreal_failed": [], "product_truth": "match",
             "photographic_realism": "clear", "usable_as_listing_asset": False}]
    sel = PT.selection("flux-2-pro", rows)
    c = sel["criteria"]
    assert set(c) == set(PT.SELECTION_CRITERIA) and sel["account"] == "bfl"
    assert c["fit"]["status"] == "MEASURED" and c["fit"]["usable_rate"] == 0.5
    assert c["reliability"] == {**c["reliability"], "status": "MEASURED",
                                "completion_rate": 0.667, "attempts": 3}
    assert c["cost"]["cad_per_usable"] == 0.16
    assert c["reversibility"]["status"] == "RECORDED"
    # Licence and maintenance are not read by this build: open, and said so.
    assert c["licence"]["status"] == "UNVERIFIED" and c["maintenance"]["status"] == "UNVERIFIED"
    assert sel["decision_ready"] is False
    assert set(sel["open_criteria"]) == {"licence", "maintenance"}
    thin = PT.selection("flux-2-pro", rows[:1])
    assert thin["criteria"]["reliability"]["status"] == "UNMEASURED"
    assert "selection" in inspect.getsource(PT.run)


def test_f464_the_render_handlers_cannot_wait_on_a_provider():
    from brambleloop.publish import model_photography, owned_photography

    for mod in (model_photography, owned_photography):
        body = ast.parse(inspect.getsource(mod.make)).body[0].body
        stmts = [s for s in body if not (isinstance(s, ast.Expr)
                                         and isinstance(getattr(s, "value", None), ast.Constant))]
        assert isinstance(stmts[1], ast.Return), mod.__name__     # import, then return
        assert "redraw_refusal" in ast.unparse(stmts[1])

    called = []

    def generator(*a, **k):
        called.append(a)
        raise AssertionError("a provider was asked")

    db = Database("sqlite://")
    db.create_all()
    cir = build(CATALOGUE["cloudline-baby-blanket"])
    twin = build_twin(cir, compile_cir(cir))
    for mod in (model_photography, owned_photography):
        out = mod.make(db, cir, twin, generator=generator, work_dir="/nonexistent")
        assert out["made"] is False and "F-852" in out["why"]
    assert called == []


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
