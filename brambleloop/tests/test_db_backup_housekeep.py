"""db-backup housekeeping: manifest, rotation, space precheck, offsite copy off by default.

RELENG 2026-10-11 (RELENG_FIX.md section 5). This drives `ops/db_backup/housekeep.sh` with a
stand-in backup script that speaks the same `BK RESULT OK <path>` protocol as the proven
Railway job, in a temporary directory. The offsite round trip goes to a loopback S3-shaped
server with a throwaway gpg key. Nothing here touches Railway, a real bucket, or the network.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT.parent / "ops" / "db_backup" / "housekeep.sh"

_COUNTER = [0]


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().endswith("_PROXY") and not k.startswith(("OFFSITE_", "BACKUP_",
                                                                       "BK_"))}
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    env.update(extra)
    return env


def _fake_backup(dir_: Path, ok: bool = True) -> Path:
    """A stand-in for the proven job: writes a dump, then reports like it does."""
    _COUNTER[0] += 1
    name = f"brambleloop_prod_20261011T{_COUNTER[0]:06d}Z.dump"
    script = dir_.parent / f"b{_COUNTER[0]}.sh"
    payload = os.urandom(2048).hex()
    body = f'printf %s "{payload}" > "{dir_}/{name}"\necho "BK file {dir_}/{name}"\n'
    body += (f'echo "BK RESULT OK {dir_}/{name}"\n' if ok
             else 'echo "BK RESULT FAIL pg_restore"\nexit 1\n')
    script.write_text(body)
    return script


def _run(*args, env=None):
    return subprocess.run(["bash", str(SCRIPT), *map(str, args)], capture_output=True,
                          text=True, env=env or _env(), timeout=120)


def _dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="bkhk-")) / "backup"
    d.mkdir()
    return d


def _dumps(d: Path):
    return sorted(p.name for p in d.glob("brambleloop_prod_*.dump"))


def test_a_verified_run_is_recorded_with_a_checksum_manifest():
    d = _dir()
    r = _run("run", _fake_backup(d), d)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "BK offsite disabled" in r.stdout
    [name] = _dumps(d)
    manifest = (d / "MANIFEST.jsonl").read_text()
    sha = hashlib.sha256((d / name).read_bytes()).hexdigest()
    assert f'"event":"verified","file":"{name}"' in manifest and sha in manifest
    assert (d / "SHA256SUMS").read_text() == f"{sha}  {name}\n"
    c = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=d, capture_output=True, text=True)
    assert c.returncode == 0, c.stdout


def test_rotation_keeps_the_newest_n_verified_dumps():
    d = _dir()
    for _ in range(4):
        assert _run("run", _fake_backup(d), d, env=_env(BACKUP_KEEP="2")).returncode == 0
    names = _dumps(d)
    assert len(names) == 2 and names == sorted(names)
    assert names[-1].endswith(f"{_COUNTER[0]:06d}Z.dump"), "the newest must survive"
    manifest = (d / "MANIFEST.jsonl").read_text()
    assert manifest.count('"event":"deleted"') == 2
    assert len((d / "SHA256SUMS").read_text().splitlines()) == 2


def test_a_failed_run_records_nothing_and_never_deletes_the_last_good_dump():
    d = _dir()
    assert _run("run", _fake_backup(d), d, env=_env(BACKUP_KEEP="1")).returncode == 0
    good = _dumps(d)
    r = _run("run", _fake_backup(d, ok=False), d, env=_env(BACKUP_KEEP="1"))
    assert r.returncode == 1 and "nothing recorded" in r.stdout
    assert set(good) <= set(_dumps(d)), "a failed run removed the last verified dump"
    partial = sorted(set(_dumps(d)) - set(good))
    assert partial and partial[0] not in (d / "MANIFEST.jsonl").read_text()
    # The next good run clears the older, unverified partial.
    assert _run("run", _fake_backup(d), d, env=_env(BACKUP_KEEP="1")).returncode == 0
    assert partial[0] not in _dumps(d) and len(_dumps(d)) == 1


def test_check_detects_a_changed_or_missing_dump():
    d = _dir()
    _run("run", _fake_backup(d), d)
    _run("run", _fake_backup(d), d)
    assert _run("check", d).returncode == 0
    a, b = _dumps(d)
    (d / a).write_text("tampered")
    (d / b).unlink()
    r = _run("check", d)
    assert r.returncode == 4 and f"CHANGED {a}" in r.stdout and f"MISSING {b}" in r.stdout


def test_precheck_frees_the_oldest_but_never_the_newest():
    d = _dir()
    for _ in range(3):
        _run("run", _fake_backup(d), d, env=_env(BACKUP_KEEP="3"))
    size = (d / _dumps(d)[-1]).stat().st_size
    r = _run("precheck", d, env=_env(BK_FREE_BYTES=str(size // 2)))
    assert r.returncode == 0, r.stdout
    assert len(_dumps(d)) == 2 and "making room" in r.stdout
    r = _run("precheck", d, env=_env(BK_FREE_BYTES="0", BACKUP_KEEP="3"))
    assert r.returncode == 1 and "only the newest" in r.stdout
    assert len(_dumps(d)) == 1, "the newest verified dump must never be deleted for space"


def test_offsite_is_off_by_default_and_calls_nothing():
    d = _dir()
    fakebin = d.parent / "bin"
    fakebin.mkdir()
    marker = d.parent / "curl_called"
    (fakebin / "curl").write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    os.chmod(fakebin / "curl", 0o755)
    env = _env(PATH=f"{fakebin}:{os.environ['PATH']}", OFFSITE_ENDPOINT="http://x",
               OFFSITE_BUCKET="b")
    r = _run("run", _fake_backup(d), d, env=env)
    assert r.returncode == 0 and "offsite disabled" in r.stdout and not marker.exists()


def test_offsite_enabled_but_unconfigured_fails_loudly_and_keeps_the_local_dump():
    d = _dir()
    r = _run("run", _fake_backup(d), d, env=_env(OFFSITE_UPLOAD="1"))
    assert r.returncode == 3 and "OFFSITE FAIL OFFSITE_ENDPOINT is not set" in r.stdout
    assert len(_dumps(d)) == 1 and '"event":"verified"' in (d / "MANIFEST.jsonl").read_text()


# -- offsite round trip against a loopback S3-shaped store ---------------------------------

class _Store(BaseHTTPRequestHandler):
    objects: dict = {}
    auth: list = []

    def do_PUT(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self.objects[self.path] = self.rfile.read(n)
        self.auth.append(self.headers.get("Authorization", ""))
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        body = self.objects.get(self.path)
        self.auth.append(self.headers.get("Authorization", ""))
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *a):
        pass


def _gpg_key(home: Path) -> tuple[str, str]:
    home.mkdir(mode=0o700)
    env = dict(os.environ, GNUPGHOME=str(home))
    base = ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
    subprocess.run(base + ["--quick-gen-key", "Owner Test <owner@example.invalid>", "default",
                           "default", "never"], env=env, check=True, capture_output=True)
    pub = subprocess.run(["gpg", "--batch", "--armor", "--export"], env=env, check=True,
                         capture_output=True).stdout
    priv = subprocess.run(base + ["--armor", "--export-secret-keys"], env=env, check=True,
                          capture_output=True).stdout
    return base64.b64encode(pub).decode(), base64.b64encode(priv).decode()


def test_offsite_round_trip_encrypts_to_the_owner_key_and_reads_back():
    if not shutil.which("gpg") or not shutil.which("curl"):
        print("SKIP gpg/curl not installed")
        return
    d = _dir()
    # INTEG3: gpg-agent's socket lives in GNUPGHOME, and a Unix socket path is capped at ~107
    # bytes. Under run_tests.sh the per-suite TMPDIR alone is ~100 bytes, so --quick-gen-key
    # failed (exit 2) in every full run while passing alone. The owner's keyring gets a short
    # home of its own, removed below.
    owner = Path(tempfile.mkdtemp(prefix="gpg-", dir="/tmp")) / "h"
    pub_b64, priv_b64 = _gpg_key(owner)
    srv = HTTPServer(("127.0.0.1", 0), _Store)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    secret = "s3cr3t-never-on-a-command-line"
    env = _env(OFFSITE_UPLOAD="1", OFFSITE_ENDPOINT=f"http://127.0.0.1:{srv.server_port}",
               OFFSITE_BUCKET="bramble-bk", OFFSITE_REGION="us-west-004",
               OFFSITE_KEY_ID="KEYID123", OFFSITE_SECRET=secret,
               OFFSITE_GPG_PUBKEY_B64=pub_b64)
    try:
        r = _run("run", _fake_backup(d), d, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        [name] = _dumps(d)
        path = f"/bramble-bk/pgdump/daily/{name}.gpg"
        blob = _Store.objects[path]
        assert blob and (d / name).read_bytes() not in blob, "uploaded in the clear"
        assert "OFFSITE OK" in r.stdout and '"event":"offsite"' in (
            d / "MANIFEST.jsonl").read_text()
        assert all(a.startswith("AWS4-HMAC-SHA256") and "KEYID123" in a and secret not in a
                   for a in _Store.auth)
        # Only the owner's private key opens it (decrypted here as the owner would).
        out = subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase",
                              "", "--decrypt"], input=blob, capture_output=True,
                             env=dict(os.environ, GNUPGHOME=str(owner)))
        assert out.returncode == 0 and out.stdout == (d / name).read_bytes()
        # A private key pasted where the public key belongs is refused, not used.
        r = _run("ship", d, d / name, env=dict(env, OFFSITE_GPG_PUBKEY_B64=priv_b64))
        assert r.returncode == 3 and "PRIVATE key" in r.stdout
    finally:
        srv.shutdown()
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], capture_output=True,
                       env=dict(os.environ, GNUPGHOME=str(owner)))
        shutil.rmtree(owner.parent, ignore_errors=True)


def test_the_script_never_deletes_offsite_and_ships_disabled():
    text = SCRIPT.read_text()
    assert "-X DELETE" not in text and "DELETE" not in text.replace("deleted", "")
    assert 'OFFSITE_UPLOAD:-0' in text


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
