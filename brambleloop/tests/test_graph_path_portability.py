"""Runtime root matching uses canonical paths on Windows and POSIX."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests import test_reachability as fixture
R=fixture.R

def test_scheduled_handler_and_negative_controls():
    def probe():
        assert R._rel_of('brambleloop.runtime.worker')=='runtime/worker.py'
        assert R.reached('lib/live.py')['reached']
        for rel in ('lib/auditonly.py','lib/static.py','lib/manualonly.py','lib/unimported.py'):
            assert not R.reached(rel)['reached'],(rel,R.reached(rel))
    fixture._with_package(probe)

if __name__=='__main__':
    test_scheduled_handler_and_negative_controls();print('PASS scheduled handler and4 negative controls')
