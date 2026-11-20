"""Request-scoped import evidence never returns a stale result."""
import sys,os,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from brambleloop.build2 import maturity as m,closure,requirements as reg,reachability


def fixture(folder):
    p=Path(folder)/'test_a.py';p.write_text('import brambleloop.alpha\n');return p


def test_multiple_reads_capture_exactly_twice_and_separate_calls_refresh():
    with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
        p=fixture(folder)
        @m._with_test_import_snapshot
        def probe():return [m._tested_modules() for _ in range(28)]
        with patch.object(m,'_capture_test_sources',wraps=m._capture_test_sources) as capture:
            result=probe();assert capture.call_count==2
        assert all(x==frozenset({'alpha'}) for x in result)
        p.write_text('import brambleloop.bravo\n');assert probe()[0]==frozenset({'bravo'})


def test_mutation_add_remove_and_unreadable_abort_no_result():
    for mode in ('same_metadata','add','remove','unreadable'):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
            p=fixture(folder);stamp=p.stat()
            @m._with_test_import_snapshot
            def probe():
                assert m._tested_modules()==frozenset({'alpha'})
                if mode=='same_metadata':
                    p.write_text('import brambleloop.bravo\n');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                elif mode=='add':Path(folder,'test_b.py').write_text('import brambleloop.beta\n')
                elif mode=='remove':p.unlink()
                return 'must never escape'
            original=m._capture_test_sources;reads=[]
            def capture():
                reads.append(1)
                if mode=='unreadable' and len(reads)>1:raise PermissionError('denied')
                return original()
            with patch.object(m,'_capture_test_sources',side_effect=capture):
                try:probe()
                except RuntimeError:pass
                else:raise AssertionError(mode+' returned stale result')
            assert m._test_import_snapshot.get() is None


def test_nested_and_exception_contexts_restore_parent():
    with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
        fixture(folder)
        @m._with_test_import_snapshot
        def inner():raise ValueError('fixture')
        @m._with_test_import_snapshot
        def outer():
            parent=m._test_import_snapshot.get()
            try:inner()
            except ValueError:pass
            assert m._test_import_snapshot.get() is parent
            return m._tested_modules()
        assert outer()==frozenset({'alpha'})
        assert m._test_import_snapshot.get() is None


def test_parallel_requests_do_not_share_snapshot():
    with tempfile.TemporaryDirectory() as folder,patch.object(m,'_TESTS',Path(folder)):
        p=fixture(folder);captured=threading.Event();changed=threading.Event()
        @m._with_test_import_snapshot
        def first():
            captured.set();assert changed.wait(5)
            assert m._tested_modules()==frozenset({'alpha'})
            return 'stale'
        @m._with_test_import_snapshot
        def second():return m._tested_modules()
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(first);assert captured.wait(5)
            p.write_text('import brambleloop.bravo\n')
            new=pool.submit(second);assert new.result(5)==frozenset({'bravo'})
            changed.set()
            try:old.result(5)
            except RuntimeError:pass
            else:raise AssertionError('first request returned changed evidence')
        assert m._test_import_snapshot.get() is None


def test_real_consumers_preserve_unchanged_fixture_results():
    rows=reg.by_status(reg.COVERED)[:2]
    # Isolate unrelated runtime graph; real row resolution and import checks still run.
    with patch.object(reg,'by_status',return_value=rows),patch.object(m,'jobs_reaching',return_value=[]):
        assert m.report(None)==m.report.__wrapped__(None)
    with patch.object(reg,'load',return_value=rows),patch.object(reachability,'reached',return_value={'reached':False,'why':'fixture graph unavailable'}):
        a=closure.matrix(None);b=closure.matrix.__wrapped__(None)
        a.pop('as_of');b.pop('as_of');assert a==b


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test();print('OK  ',test.__name__)
    print(len(tests),'passed')
