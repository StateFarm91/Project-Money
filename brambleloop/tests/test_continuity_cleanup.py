"""Scratch restore databases release OS file handles on every exit path."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sqlalchemy import text
from brambleloop.core.db import Database
from brambleloop.core import continuity


def exercise(failure):
    # A real file DB matters: memory SQLite cannot reproduce Windows unlink refusal.
    with tempfile.TemporaryDirectory() as source_dir:
        source=Database('sqlite:///'+str(Path(source_dir)/'source.sqlite'),scratch=True)
        source.create_all()
        scratch_engines=[]
        original_database=continuity.Database
        original_restore=continuity.restore
        original_export=continuity.export
        def database(*args,**kwargs):
            db=original_database(*args,**kwargs)
            scratch_engines.append(db.engine)
            return db
        def restore(*args,**kwargs):
            result=original_restore(*args,**kwargs)
            if failure=='restore':raise RuntimeError('injected after restore opened file')
            return result
        def export(db,*args,**kwargs):
            if failure=='roundtrip' and db is not source:
                # Exercise the failure after the restored scratch pool owns an OS handle.
                raise RuntimeError('injected roundtrip export failure')
            return original_export(db,*args,**kwargs)
        try:
            with tempfile.TemporaryDirectory() as work:
                with patch.object(continuity,'Database',side_effect=database),patch.object(continuity,'restore',side_effect=restore),patch.object(continuity,'export',side_effect=export):
                    try:
                        proof=continuity.prove_restore(source,work)
                    except RuntimeError as exc:
                        assert failure=='roundtrip' and 'injected roundtrip' in str(exc)
                    else:
                        assert failure!='roundtrip'
                        assert proof.ok is (failure is None)
                        if failure=='restore':assert 'injected after restore' in proof.problems[0]
                assert len(scratch_engines)==1
                # Cross-platform assertion: disposed pool has no checked-in connections;
                # Windows additionally enforces real file deletion immediately below.
                assert scratch_engines[0].pool.checkedin()==0
                Path(work,'continuity-restore-check.sqlite').unlink()
            with source.engine.connect() as connection:
                assert connection.execute(text('select 1')).scalar()==1
        finally:
            for engine in scratch_engines:engine.dispose()
            source.engine.dispose()


def test_successful_restore_releases_scratch_before_workspace_cleanup():exercise(None)
def test_restore_failure_returns_original_finding_and_releases_scratch():exercise('restore')
def test_roundtrip_export_failure_releases_scratch_without_masking_error():exercise('roundtrip')

if __name__=='__main__':
    failures=0
    for name,test in list(globals().items()):
        if name.startswith('test_'):
            try:test();print('OK  ',name)
            except Exception as exc:failures+=1;print('FAIL',name,type(exc).__name__,str(exc))
    print(f'{3-failures}/3 passing');sys.exit(bool(failures))
