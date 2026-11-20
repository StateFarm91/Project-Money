"""Resolver outputs remain canonical and ambiguity remains refused on every host."""
import sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from brambleloop.build2 import maturity as m


def test_nested_resolution_is_canonical_and_reaches_import_evidence():
    with tempfile.TemporaryDirectory() as folder:
        pkg=Path(folder)/'package';tests=Path(folder)/'tests'
        (pkg/'nested').mkdir(parents=True);tests.mkdir()
        (pkg/'nested'/'sample.py').write_text('VALUE=1\n')
        (tests/'test_sample.py').write_text('import brambleloop.nested.sample\n')
        with patch.object(m,'_PACKAGE',pkg),patch.object(m,'_TESTS',tests):
            for token in ('nested/sample.py','nested.sample','sample.py','sample'):
                result=m._module_of(token)
                assert result=='nested/sample.py',(token,result)
                assert m._tested(result)
            assert m.modules_named('sample.VALUE and nested/sample.py')==['nested/sample.py']
            # Preserve direct-path resolution; only slash spelling changes.
            assert m._module_of(str(pkg/'nested'/'sample.py'))==(pkg/'nested'/'sample.py').as_posix()


def test_ambiguous_bare_name_remains_refused():
    with tempfile.TemporaryDirectory() as folder:
        pkg=Path(folder)
        for name in ('first','second'):
            (pkg/name).mkdir();(pkg/name/'same.py').write_text('VALUE=1\n')
        with patch.object(m,'_PACKAGE',pkg):
            assert m._module_of('same.py') is None
            assert m._module_of('same') is None
            assert m._module_of('first.same')=='first/same.py'
            assert m._module_of('missing') is None


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test();print('OK  ',test.__name__)
    print(len(tests),'passed')
