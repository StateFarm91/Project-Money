"""Reproduce the lane D real-backend check: serve a lane C checkout (with this branch's static
dir copied in) on 127.0.0.1 via a stdlib HTTP -> ASGI bridge. Test tooling only, never shipped.
Usage: CC_PASSPHRASE=... PORT=8899 python3 real_backend_bridge.py <brambleloop dir of the checkout>
"""
import os, sys, tempfile, socket
root = sys.argv[1]
sys.path.insert(0, os.path.join(root, "src"))
tmp = tempfile.mkdtemp(prefix="v11_D_int_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tmp}/cc.db"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(tmp, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for k in list(os.environ):
    if k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(k)
_orig = socket.socket.connect
def guarded(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "localhost", "::1"):
        return _orig(self, addr, *a, **k)
    raise OSError("network refused by lane D integration harness")
socket.socket.connect = guarded
from brambleloop.app.command_center import auth
from brambleloop.core import opsauth
os.environ[opsauth.TOKEN_VAR] = "i" * 40
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(os.environ["CC_PASSPHRASE"], iterations=100_000)
from brambleloop.app import main
main.db.create_all()
# No uvicorn in this interpreter: bridge a stdlib HTTP server to the ASGI app through
# Starlette's TestClient (cookies passed through explicitly, never kept in the client jar).
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from fastapi.testclient import TestClient
import threading
client = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
lock = threading.Lock()
class H(BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
        # Bridge artifact only: the app sees https://testserver, so present the browser's
        # same-origin Origin as that origin.
        for k in list(hdrs):
            if k.lower() == "origin":
                hdrs[k] = "https://testserver"
        with lock:
            client.cookies.clear()
            r = client.request(self.command, self.path, content=body, headers=hdrs, follow_redirects=False)
        self.send_response(r.status_code)
        for k, v in r.headers.multi_items():
            if k.lower() in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                continue
            self.send_header(k, v)
        data = r.content
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_GET = do_POST = do_PUT = do_DELETE = _go
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8899"))), H).serve_forever()
