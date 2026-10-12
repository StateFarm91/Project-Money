"""Shared harness for lane J security probes (fresh SQLite DB, real app, TestClient)."""
import os, sys, tempfile, socket, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="jsec_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP,'j.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
for k in list(os.environ):
    if k.startswith(("ANTHROPIC_API","ETSY","OPENAI","REPLICATE","FAL_","GEMINI")): os.environ.pop(k)
def _nonet(*a, **k): raise OSError("no network")
socket.socket.connect = _nonet; socket.create_connection = _nonet
from fastapi.testclient import TestClient
from brambleloop.app import main, security
from brambleloop.app.command_center import auth
from brambleloop.core import opsauth
OPS = "k"*40
PASS = "owner passphrase for the harness only"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
from brambleloop.agents.registry import Registry
try: Registry(main.db).seed_defaults()
except Exception as e: print("seed_defaults:", e)
db = main.db
def client(): return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
def login(c, **extra):
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS, **extra}); assert r.status_code==200, r.text
    return r.json()["csrf_token"]
def fresh(csrf, **over):
    h = {"X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time()))}
    if csrf is not None: h["X-CSRF-Token"] = csrf
    h.update(over); return h
def cc_routes():
    out=[]
    for path, methods, _ in security.iter_api_routes(main.app):
        if path.startswith("/api/cc/"):
            for m in sorted(methods-{"HEAD","OPTIONS"}): out.append((m,path))
    return out
def clear_events():
    from brambleloop.app.command_center.models import SecurityEvent
    with db.session() as s: s.query(SecurityEvent).delete()
