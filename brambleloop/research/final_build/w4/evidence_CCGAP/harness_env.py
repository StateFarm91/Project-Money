"""Shared env for the CCVERIFY lane: throwaway local Postgres, shadow phase, no outbound network,
TEST-only owner credentials (generated locally, never real). Imported first by seed.py and serve.py."""
import os
import socket
import sys

ROOT = "/home/user/Project-Money/.claude/worktrees/W4-CCGAP/brambleloop"
sys.path.insert(0, ROOT + "/src")
SCR = os.path.dirname(os.path.abspath(__file__))

os.environ["BRAMBLELOOP_DATABASE_URL"] = "sqlite:///" + os.path.join(SCR, "tmp", "cc.db")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["TMPDIR"] = os.path.join(SCR, "tmp")
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(SCR, "art")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for k in list(os.environ):
    if k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI", "RAILWAY")):
        os.environ.pop(k)

_orig = socket.socket.connect


def _guarded(self, addr, *a, **k):
    if isinstance(addr, str) or (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "localhost", "::1")):
        return _orig(self, addr, *a, **k)
    raise OSError("network refused by CCVERIFY harness (loopback only)")


socket.socket.connect = _guarded
_orig_cc = socket.create_connection


def _cc(addr, *a, **k):
    if addr[0] in ("127.0.0.1", "localhost", "::1"):
        return _orig_cc(addr, *a, **k)
    raise OSError("network refused by CCVERIFY harness (loopback only)")


socket.create_connection = _cc

# TEST credentials: read from a local file in the scratchpad (never committed, never printed).
_cred = os.path.join(SCR, "test_creds.env")
for line in open(_cred):
    k, v = line.rstrip("\n").split("=", 1)
    os.environ[k] = v
