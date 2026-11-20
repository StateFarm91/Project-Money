"""A push to production is verified, not assumed, to have deployed (RELENG, 2026-10-11).

On 2026-10-11 the push of 0417f35 created no Railway deployment; `ops/deploy.sh` ended at
`git push` and so reported nothing. These tests drive `ops/verify_deploy.py` with an injected
clock and /health reader, then run the real `ops/deploy.sh` end to end against a throwaway
repository, a local bare "origin" and a loopback /health server. The guard is stubbed to ALLOW
in the scratch copy only (its own decisions are covered by test_deploy_path). Nothing here
pushes to a real remote or calls the real host.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT.parent / "ops"
sys.path.insert(0, str(OPS))

import verify_deploy as V  # noqa: E402

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

NEW, OLD = "1" * 40, "2" * 40


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _health(commit, known=True):
    return {"status": "ok", "build": {"commit": commit, "known": known}}


def test_deployed_when_health_reaches_the_pushed_sha():
    c = _Clock()
    answers = iter([_health(OLD), _health(OLD), _health(NEW)])
    out = V.wait_for(NEW, fetch=lambda u: next(answers), timeout=100, interval=10,
                     clock=c, sleep=c.sleep)
    assert out["verdict"] == "DEPLOYED" and out["polls"] == 3 and out["seconds"] == 20


def test_no_deploy_when_production_keeps_the_old_commit():
    c = _Clock()
    out = V.wait_for(NEW, fetch=lambda u: _health(OLD), timeout=60, interval=15,
                     clock=c, sleep=c.sleep)
    assert out["verdict"] == "NO_DEPLOY", out
    assert out["production_commit"] == OLD and out["seconds"] >= 60
    assert "never started a deployment" in out["why"]


def test_unreachable_or_unknown_health_is_unverified_not_deployed():
    c = _Clock()

    def boom(u):
        raise OSError("502")

    out = V.wait_for(NEW, fetch=boom, timeout=30, interval=10, clock=c, sleep=c.sleep)
    assert out["verdict"] == "UNVERIFIED"
    c2 = _Clock()
    out = V.wait_for(NEW, fetch=lambda u: _health(NEW, known=False), timeout=30, interval=10,
                     clock=c2, sleep=c2.sleep)
    assert out["verdict"] == "UNVERIFIED", "an unknown build must not count as the pushed sha"


def test_mid_deploy_errors_are_tolerated_until_the_new_commit_answers():
    c = _Clock()
    seq = [_health(OLD), OSError("502"), _health(NEW)]

    def fetch(u):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    out = V.wait_for(NEW, fetch=fetch, timeout=100, interval=5, clock=c, sleep=c.sleep)
    assert out["verdict"] == "DEPLOYED"


def test_short_sha_is_a_usage_error():
    assert V.main(["0417f35"]) == 2


# -- end to end: the real deploy.sh, a scratch repo, a loopback /health ----------------------

def _serve(commit_box: dict) -> HTTPServer:
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps(_health(commit_box["commit"])).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True)


def _scratch():
    base = Path(tempfile.mkdtemp(prefix="deployverify-"))
    origin, repo = base / "origin.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ops").mkdir()
    for name in ("deploy.sh", "verify_deploy.py"):
        (repo / "ops" / name).write_bytes((OPS / name).read_bytes())
    # Stub guard and production reader: ALLOW, so the push happens (scratch copy only).
    (repo / "ops" / "deploy_guard.py").write_text("import sys; sys.exit(0)\n")
    (repo / "ops" / "deployed_sha.py").write_text("print('0' * 40)\n")
    (repo / "README").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    return repo, origin, _git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_deploy(repo, url, **extra):
    env = dict(os.environ, BRAMBLELOOP_PRODUCTION_URL=url, DEPLOY_VERIFY_TIMEOUT="2",
               DEPLOY_VERIFY_INTERVAL="0.2", **extra)
    return subprocess.run(["sh", "ops/deploy.sh"], cwd=repo, env=env, capture_output=True,
                          text=True, timeout=60)


def test_deploy_sh_reports_no_deploy_when_production_never_moves():
    repo, origin, head = _scratch()
    box = {"commit": OLD}
    srv = _serve(box)
    try:
        r = _run_deploy(repo, f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "NO DEPLOY" in r.stderr and head in r.stderr and OLD in r.stderr
    pushed = subprocess.run(["git", "--git-dir", str(origin), "rev-parse",
                             "refs/heads/claude/repository-setup-nc9x6o"],
                            capture_output=True, text=True).stdout.strip()
    assert pushed == head, "the push itself must have happened; only the deploy is missing"


def test_deploy_sh_succeeds_only_when_production_reports_the_pushed_sha():
    repo, origin, head = _scratch()
    box = {"commit": OLD}
    srv = _serve(box)
    threading.Timer(0.5, lambda: box.update(commit=head)).start()
    try:
        r = _run_deploy(repo, f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert f"DEPLOYED {head}" in r.stdout


def test_deploy_sh_can_skip_verification_but_says_so():
    repo, origin, head = _scratch()
    r = _run_deploy(repo, "http://127.0.0.1:9", VERIFY_DEPLOY="0")
    assert r.returncode == 0 and "NOT checked" in r.stderr, (r.stdout, r.stderr)


def test_verification_follows_the_only_push_in_deploy_sh():
    text = (OPS / "deploy.sh").read_text()
    push = text.index('git -C "$top" push')
    verify = text.index('ops/verify_deploy.py" "$sha"')
    assert push < verify and 'exit "$rc"' in text[verify:]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
