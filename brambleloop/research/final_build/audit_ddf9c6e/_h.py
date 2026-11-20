import os, sys, tempfile, socket
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="J_fin_")
import atexit, shutil; atexit.register(shutil.rmtree, _TMP, True)  # W3-HYG: removed at exit
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
def _nn(*a, **k): raise OSError("network refused")
socket.socket.connect = _nn; socket.create_connection = _nn
from datetime import datetime, timedelta, timezone
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
NOW = datetime.now(timezone.utc)
_n=[0]
def mkdb(seed=False):
    _n[0]+=1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite"); db.create_all(); Registry(db).seed_defaults()
    if seed:
        from brambleloop.finance.accounting import shadow_dataset
        shadow_dataset.seed(db, now=NOW)
    return db
