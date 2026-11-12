"""An implicit adult decision cannot override a changed child-audience title."""
import dataclasses

import test_a1r_child_safety_core as harness
from brambleloop.products import inventory, launch0


def test_child_title_on_implicitly_exempt_slug_is_held_by_real_worker():
    adult = inventory._engineered("market-basket-small")
    assert launch0.childrens_decision_for(adult)[0] == launch0.NOT_FOR_CHILDREN
    for title in ("Baby Basket", "Βaby Basket", "Ｂaby Basket", "Ba\u200bby Basket"):
        changed = dataclasses.replace(adult, title=title)
        assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED, title
        assert harness._refused(changed), title
    result = harness._assets_build_full(dataclasses.replace(adult, title="Baby Basket"))
    assert harness._held(result), result
    assert result["outputs"]["reason"] == "undecided", result
    assert harness._rendered(harness._assets_build_full(adult))


if __name__ == "__main__":
    # Review U6 H2: run under the suite harness (one `OK name` line per test), without pytest.
    import _minipytest

    _minipytest.run_module(globals())
