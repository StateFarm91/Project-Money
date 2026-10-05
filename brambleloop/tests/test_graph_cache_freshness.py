"""Graph evidence follows exact source and policy snapshots, never old PASSes."""
import sys,os,threading
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests import test_reachability as fixture
R=fixture.R


def remove_call():
    p=R.PKG/'runtime/release.py';stamp=p.stat();s=p.read_text(encoding='utf-8')
    old='result = live.compute(ctx.db)';new='result = None'.ljust(len(old))
    p.write_text(s.replace(old,new),encoding='utf-8');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert p.stat().st_size==stamp.st_size and p.stat().st_mtime_ns==stamp.st_mtime_ns


def test_same_size_mtime_call_removal_refutes_warm_reachability():
    def probe():
        assert R.reached('lib/live.py')['reached']
        remove_call()
        assert not R.reached('lib/live.py')['reached']
        assert not R.function_reached('lib/live.py','compute')['reached']
    fixture._with_package(probe)


def test_import_removal_and_source_add_delete_invalidate():
    def probe():
        assert 'brambleloop.lib.live' in R.reachable()
        p=R.PKG/'runtime/release.py';s=p.read_text(encoding='utf-8')
        p.write_text(s.replace('live, auditonly','auditonly').replace('result = live.compute(ctx.db)','result = None'),encoding='utf-8')
        assert 'brambleloop.lib.live' not in R.reachable()
        p.write_text(s+'\nfrom ..lib import added\n',encoding='utf-8')
        added=R.PKG/'lib/added.py';added.write_text('VALUE=1\n')
        assert 'brambleloop.lib.added' in R.reachable()
        added.unlink();assert 'brambleloop.lib.added' not in R.reachable()
    fixture._with_package(probe)


def test_root_policy_change_invalidates_cached_graph():
    def probe():
        assert R.reached('lib/live.py')['reached']
        with patch.object(R,'ROOTS',()):
            assert not R.reachable()
            assert not R.reached('lib/live.py')['reached']
        assert R.reached('lib/live.py')['reached']
    fixture._with_package(probe)


def test_unreadable_entry_or_changed_boundary_never_returns_success():
    def probe():
        assert R.reached('lib/live.py')['reached']
        with patch.object(Path,'read_bytes',side_effect=PermissionError('fixture denied')):
            try:R.reached('lib/live.py')
            except PermissionError:pass
            else:raise AssertionError('unreadable source reused old PASS')
        @R._graph_boundary
        def changing():
            assert R.reached('lib/live.py')['reached'];remove_call();return True
        try:changing()
        except RuntimeError:pass
        else:raise AssertionError('changed graph returned result')
        assert R._GRAPH_SCOPE.get() is None
        original=R._capture_graph_sources;count=[]
        def failing_final():
            count.append(1)
            if len(count)>1:raise PermissionError('final read denied')
            return original()
        with patch.object(R,'_capture_graph_sources',side_effect=failing_final):
            try:R.reached('lib/live.py')
            except RuntimeError:pass
            else:raise AssertionError('unreadable final capture returned')
    fixture._with_package(probe)


def test_unchanged_graph_reuses_parse_and_preserves_fixture_verdicts():
    def probe():
        first=R.reached('lib/live.py')
        with patch.object(R.ast,'parse',wraps=R.ast.parse) as parse:
            assert R.reached('lib/live.py')==first
            assert parse.call_count==0
        assert first['reached']
        for rel in ('lib/auditonly.py','lib/static.py','lib/manualonly.py','lib/unimported.py'):
            assert not R.reached(rel)['reached']
    fixture._with_package(probe)


def test_concurrent_scopes_keep_immutable_sources_and_abort_old_result():
    def probe():
        captured=threading.Event();changed=threading.Event()
        @R._graph_boundary
        def old_report():
            assert R.reached('lib/live.py')['reached'];captured.set();assert changed.wait(5)
            assert R.reached('lib/live.py')['reached'];return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(old_report);assert captured.wait(5)
            remove_call();assert not pool.submit(R.reached,'lib/live.py').result(5)['reached']
            changed.set()
            try:old.result(5)
            except RuntimeError:pass
            else:raise AssertionError('old report escaped mutation')
        assert R._GRAPH_SCOPE.get() is None
    fixture._with_package(probe)


def test_traversal_error_and_nested_exception_fail_closed():
    def probe():
        assert R.reached('lib/live.py')['reached']
        def unreadable_walk(root,onerror):
            onerror(PermissionError('unreadable directory'))
            return iter(())
        with patch.object(R.os,'walk',side_effect=unreadable_walk):
            try:R.reached('lib/live.py')
            except PermissionError:pass
            else:raise AssertionError('unreadable directory became partial graph')
        @R._graph_boundary
        def inner():raise ValueError('fixture')
        @R._graph_boundary
        def outer():
            parent=R._GRAPH_SCOPE.get()
            try:inner()
            except ValueError:pass
            assert R._GRAPH_SCOPE.get() is parent
            return R.reached('lib/live.py')['reached']
        assert outer() and R._GRAPH_SCOPE.get() is None
    fixture._with_package(probe)


def test_closure_matrix_aggregation_captures_twice_and_mutation_aborts():
    from types import SimpleNamespace
    from brambleloop.build2 import closure,maturity
    for mutate in (False,True):
        def probe():
            tests=R.PKG/'tests';tests.mkdir();(tests/'test_live.py').write_text('import brambleloop.lib.live\n')
            rows=[SimpleNamespace(id='fixture-'+str(i)) for i in range(3)];seen=[]
            def classify(row,**kwargs):
                assert R.reached('lib/live.py')['reached']
                seen.append(row.id)
                if mutate and len(seen)==1:remove_call()
                return {'id':row.id,'section':'fixture','state':closure.OPEN,'gate':None}
            with patch.object(closure.reg,'load',return_value=rows),patch.object(closure.executor,'gate_for',return_value=None),patch.object(closure,'classify',side_effect=classify),patch.object(maturity,'_TESTS',tests),patch.object(R,'_capture_graph_sources',wraps=R._capture_graph_sources) as capture:
                if mutate:
                    try:closure.matrix(None)
                    except RuntimeError:pass
                    else:raise AssertionError('matrix returned changed graph evidence')
                else:
                    result=closure.matrix(None);assert result['total']==3 and result['counts'][closure.OPEN]==3
                assert capture.call_count==2 and len(seen)==3
            assert R._GRAPH_SCOPE.get() is None
        fixture._with_package(probe)


def test_top_level_package_import_resolves_inside_snapshot():
    def probe():
        p=R.PKG/'runtime/worker.py'
        p.write_text('import brambleloop\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
        assert R._path_of('brambleloop').resolve()==(R.PKG/'__init__.py').resolve()
        assert 'brambleloop' in R.reachable()
        assert R.reached('lib/live.py')['reached']
        @R._graph_boundary
        def scoped():
            assert R._path_of('brambleloop').resolve()==(R.PKG/'__init__.py').resolve()
            assert R._parse('brambleloop') is not None
        scoped()
    fixture._with_package(probe)


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test();print('PASS',test.__name__)
    print(len(tests),'passed')
