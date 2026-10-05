"""Import evidence cache must follow exact source bytes, not file metadata."""
import sys,os,tempfile,ast
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from brambleloop.build2 import maturity as m


def test_same_size_same_mtime_mutation_cannot_reuse_obsolete_import():
    with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
        p=Path(folder)/'test_a.py';p.write_text('import brambleloop.alpha\n');stamp=p.stat()
        assert m._tested_modules()==frozenset({'alpha'})
        p.write_text('import brambleloop.bravo\n');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert p.stat().st_size==stamp.st_size and p.stat().st_mtime_ns==stamp.st_mtime_ns
        assert m._tested_modules()==frozenset({'bravo'})
        assert not m._tested('alpha.py')


def test_add_remove_malformed_and_root_switch():
    with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
        p=Path(a)/'test_a.py';p.write_text('from brambleloop.finance import books\n')
        with patch.object(m,'_TESTS',Path(a)):
            assert m._tested_modules()==frozenset({'finance','finance.books'})
            q=Path(a)/'test_b.py';q.write_text('import brambleloop.beta\n')
            assert 'beta' in m._tested_modules()
            q.unlink();assert 'beta' not in m._tested_modules()
            p.write_text('from ! syntax error');assert m._tested_modules()==frozenset()
        Path(b,'test_a.py').write_text('import brambleloop.other\n')
        with patch.object(m,'_TESTS',Path(b)):assert m._tested_modules()==frozenset({'other'})


def test_read_failure_does_not_return_warm_pass():
    with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
        Path(folder,'test_a.py').write_text('import brambleloop.alpha\n')
        assert m._tested_modules()==frozenset({'alpha'})
        with patch.object(Path,'read_bytes',side_effect=PermissionError('unreadable')):
            try:m._tested_modules()
            except PermissionError:pass
            else:raise AssertionError('unreadable evidence reused cached success')


def test_unchanged_corpus_matches_original_ast_algorithm():
    found=set()
    for path in sorted(m._TESTS.glob('test_*.py')):
        try:tree=ast.parse(path.read_text(encoding='utf-8',errors='replace'))
        except SyntaxError:continue
        for n in ast.walk(tree):
            if isinstance(n,ast.ImportFrom) and n.module:
                found.add(n.module);found.update(n.module+'.'+a.name for a in n.names)
            elif isinstance(n,ast.Import):found.update(a.name for a in n.names)
    expected=frozenset(n[len('brambleloop.'):] for n in found if n.startswith('brambleloop.'))
    m._tested_modules.cache_clear();assert m._tested_modules()==expected
    before=m._tested_modules.cache_info();assert m._tested_modules()==expected
    assert m._tested_modules.cache_info().hits==before.hits+1


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test();print('OK  ',test.__name__)
    print(len(tests),'passed')
