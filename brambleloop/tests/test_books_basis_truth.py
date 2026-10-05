"""Books never present a modelled/unknown operating cost as observed (Codex FB verification item 8)."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests.test_operating_cost_basis import dbnew
from brambleloop.core.models import CostEntry
from brambleloop.finance.books import Books, cfo_challenge


def _burn(db):
    return [c for c in cfo_challenge(Books(db).profit_and_loss()) if c.subject == "burn"]


def test_unit_economics_reports_the_cost_basis():
    cases = (({}, 'unknown'), ({'price_basis': 'assumed'}, 'modelled'), ({'price_basis': 'measured'}, 'measured'))
    seen = 0
    for declared, expected in cases:
        db = dbnew()
        with db.session() as s:
            s.add(CostEntry(agent='a', kind='llm', amount_cad=2, detail=declared))
        ue = Books(db).unit_economics(products_validated=1, listings_drafted=1)
        assert ue['operating_cost_cad'] == 2
        assert ue['operating_cost_basis'] == expected, (declared, ue)
        assert ue['operating_cost_by_basis'] == {expected: 2}
        seen += 1
    assert seen == 3


def test_cfo_never_says_the_cost_is_known_when_it_is_modelled():
    for declared, measured in (({'price_basis': 'assumed'}, False), ({'price_basis': 'measured'}, True)):
        db = dbnew()
        with db.session() as s:
            s.add(CostEntry(agent='a', kind='llm', amount_cad=2, detail=declared))
        burn = _burn(db)
        text = ' '.join(c.finding for c in burn)
        assert len(burn) == 1, burn  # fresh DB: revenue UNMEASURED, cost > 0
        assert 'The cost is known' not in text
        assert ('The cost is measured' in text) == measured, text


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    for t in tests: t(); print('PASS', t.__name__)
    print(len(tests), 'passed')
