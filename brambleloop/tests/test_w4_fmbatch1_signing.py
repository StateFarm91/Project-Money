"""F-153 / F-156 / F-157: commit-signing truth, recovery doc, and release-record evidence.

Runs against throwaway git repos with their own config; never signs with a real key.
"""
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
import signing_audit  # noqa: E402
import deploy_guard  # noqa: E402

KEY_BLOCK = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{40,}")


def _repo(cfg=()):
    d = Path(tempfile.mkdtemp())
    run = lambda *a: subprocess.run(["git", "-C", str(d), *a], check=True,
                                    capture_output=True, text=True)
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    run("config", "commit.gpgsign", "false")
    run("config", "user.signingkey", "")
    for k, v in cfg:
        run("config", k, v)
    (d / "a").write_text("1")
    run("add", "a")
    run("-c", "commit.gpgsign=false", "commit", "-q", "-m", "c1")
    return d, run


def _head(d):
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def test_no_key_is_unavailable_not_claimed():
    d, _ = _repo()
    a = signing_audit.audit(d, None, "HEAD")
    assert a["status"] == "unavailable" and a["claimed"] is False
    assert a["unsigned"] and a["unsigned"][0]["status"] == "N"
    assert a["independently_verifiable"] is False


def test_empty_key_file_is_no_key():
    tmp = Path(tempfile.mkdtemp()) / "k.pub"
    tmp.write_text("")
    d, run = _repo()
    run("config", "user.signingkey", str(tmp))
    run("config", "commit.gpgsign", "true")
    a = signing_audit.audit(d, None, "HEAD")
    assert a["signing_key_setting_present"] and not a["signing_key_configured"]
    assert a["status"] == "unavailable"


def test_configured_key_with_unsigned_commit_is_a_false_claim():
    tmp = Path(tempfile.mkdtemp()) / "k.pub"
    tmp.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIexample t@example.invalid\n")
    d, run = _repo()
    run("config", "user.signingkey", str(tmp))
    run("config", "commit.gpgsign", "true")
    a = signing_audit.audit(d, None, "HEAD")
    assert a["status"] == "claimed_but_unsigned" and a["claimed"]
    ev = deploy_guard.signing_evidence(d, _head(d), env={})
    assert "refused" in ev


def test_release_evidence_lists_unsigned_and_required_refuses():
    d, _ = _repo()
    sha = _head(d)
    ev = deploy_guard.signing_evidence(d, sha, env={})
    assert "refused" not in ev and ev["intentional_unsigned"] is True
    assert ev["unsigned"][0]["sha"] == sha
    req = deploy_guard.signing_evidence(d, sha, env={"BRAMBLELOOP_SIGNING_REQUIRED": "1"})
    assert "refused" in req and req["intentional_unsigned"] is False


def test_record_problems_flags_required_unsigned():
    read = lambda rel: None
    base = {"sha": "0" * 40, "release_eligible": True}
    ok = deploy_guard._record_problems(
        {**base, "signing": {"status": "unavailable", "required": False,
                             "unsigned": [{"sha": "0" * 40, "status": "N"}]}}, read)
    bad = deploy_guard._record_problems(
        {**base, "signing": {"status": "unavailable", "required": True,
                             "unsigned": [{"sha": "0" * 40, "status": "N"}]}}, read)
    assert not any("signing" in r for r in ok)
    assert any("signing" in r for r in bad)


def test_cli_exit_codes():
    d, _ = _repo()
    env = {k: v for k, v in os.environ.items() if k != "BRAMBLELOOP_SIGNING_REQUIRED"}
    r = subprocess.run([sys.executable, str(ROOT / "ops/signing_audit.py"), "--head", "HEAD",
                        "--repo", str(d)], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "unavailable"
    env["BRAMBLELOOP_SIGNING_REQUIRED"] = "1"
    r = subprocess.run([sys.executable, str(ROOT / "ops/signing_audit.py"), "--head", "HEAD",
                        "--repo", str(d)], capture_output=True, text=True, env=env)
    assert r.returncode == 1


def test_recovery_doc_and_no_private_keys_tracked():
    doc = (ROOT / "ops/SIGNING_RECOVERY.md").read_text()
    for must in ("allowedSignersFile", "%G?", "BRAMBLELOOP_SIGNING_REQUIRED", "No private key is ever committed"):
        assert must in doc, must
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True,
                           text=True).stdout.splitlines()
    for f in files:
        if f.startswith("brambleloop/research/_secret_scan_probe/"):
            continue
        p = ROOT / f
        if not p.is_file() or p.stat().st_size > 200_000:
            continue
        # an actual key block (header, then base64 body), not a detector's pattern string
        assert not KEY_BLOCK.search(p.read_bytes()), f


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
