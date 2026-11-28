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
BACKUP = ROOT.parent / "ops" / "db_backup" / "backup.sh"
ENCODE = ROOT.parent / "ops" / "db_backup" / "encode.sh"

_COUNTER = [0]


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().endswith("_PROXY") and not k.startswith(("OFFSITE_", "BACKUP_",
                                                                       "BK_", "FAKE_"))
           and k not in ("SRC_URL", "DATABASE_URL")}
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
    # ops/autopromote.py reads any line matching `BK RESULT OK` as a verified backup.
    assert "BK RESULT OK" not in r.stdout and "BK RESULT FAIL housekeep" in r.stdout
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
    r = _run("precheck", d, env=_env(BK_FREE_BYTES=str(size // 2), BACKUP_KEEP="3"))
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


# -- ENG-DB-BACKUP 2026-11-28: backup.sh (SCRIPT_B64) excludes continuity_archives data ------
#
# The dump tools are stubbed on PATH so the REAL backup.sh and the REAL housekeep.sh run
# together exactly as the Railway start command runs them (`housekeep.sh run <dir>`, script
# defaulting to backup.sh beside it). The stubs log their argv, so the test reads the pg_dump
# command line that was actually executed, not the script's text. A further test runs both
# against a real local Postgres when one is installed.

_STUB_PG_DUMP = r"""#!/bin/bash
if [ "${1:-}" = "--version" ]; then echo "pg_dump (PostgreSQL) 18.0"; exit 0; fi
printf '%s\n' "$*" >> "$FAKE_LOG"
for a in "$@"; do case "$a" in --file=*) f=${a#--file=} ;; esac; done
head -c "${FAKE_DUMP_BYTES:-4096}" /dev/urandom > "$f" || exit 1
"""

_STUB_PG_RESTORE = r"""#!/bin/bash
f=${@: -1}
case " $* " in
  *" --list "*)
    printf ';\n; Archive created at fake\n'
    printf '101; 1259 1 TABLE public continuity_archives postgres\n'
    printf '102; 1259 2 TABLE public jobs postgres\n'
    printf '201; 0 2 TABLE DATA public jobs postgres\n'
    [ "${FAKE_ARCHIVE_DATA_IN_TOC:-0}" = 1 ] && \
      printf '202; 0 1 TABLE DATA public continuity_archives postgres\n'
    exit 0 ;;
  *" --file=/dev/null "*)
    [ "$(head -c 5 "$f")" = TRUNC ] && { echo "pg_restore: error: unexpected EOF" >&2; exit 1; }
    exit 0 ;;
esac
printf 'restore %s\n' "$*" >> "$FAKE_LOG"
exit 0
"""

# psql <conninfo> -Atc <query>. "restored" in the conninfo means the scratch restore target.
_STUB_PSQL = r"""#!/bin/bash
conn=$1; q=${@: -1}
case "$q" in
  "show server_version") echo "18.0"; exit 0 ;;
  *"from pg_tables"*) printf 'continuity_archives\njobs\n'; exit 0 ;;
  *to_regclass*) echo t; exit 0 ;;
esac
case "$conn:$q" in
  *restored*continuity_archives*) echo "${FAKE_RESTORED_ARCHIVES:-0}" ;;
  *continuity_archives*) echo 3 ;;
  *jobs*) echo 7 ;;
  *) echo 0 ;;
esac
"""

# A stand-in `date` so three runs inside one second still get distinct, ordered dump names.
_STUB_DATE = r"""#!/bin/bash
if [ "${2:-}" = "+%Y%m%dT%H%M%SZ" ]; then
  n=$(( $(cat "$FAKE_CLOCK" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_CLOCK"
  printf '20261128T09%04dZ\n' "$n"; exit 0
fi
exec /bin/date "$@"
"""


def _stub_env(d: Path, **extra):
    fakebin = d.parent / "fakebin"
    if not fakebin.exists():
        fakebin.mkdir()
        for name, body in (("pg_dump", _STUB_PG_DUMP), ("pg_restore", _STUB_PG_RESTORE),
                           ("psql", _STUB_PSQL), ("date", _STUB_DATE)):
            (fakebin / name).write_text(body)
            os.chmod(fakebin / name, 0o755)
    return _env(PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_LOG=str(d.parent / "calls.log"),
                FAKE_CLOCK=str(d.parent / "clock"), SRC_URL="postgresql://fake/source",
                BK_RESTORE_URL="postgresql://fake/restored", BACKUP_DIR=str(d), **extra)


def _calls(d: Path) -> list[str]:
    p = d.parent / "calls.log"
    return p.read_text().splitlines() if p.exists() else []


def test_the_dump_command_excludes_continuity_archives_data():
    text = BACKUP.read_text()
    dump_cmd = text[text.index("\npg_dump --format=custom"):].split("\nrc=$?")[0]
    assert "--exclude-table-data=continuity_archives" in dump_cmd, dump_cmd
    assert 'EXCLUDED_DATA_TABLES="continuity_archives"' in text
    # What actually ran: the real script, through the real wrapper, logged by the stub.
    d = _dir()
    r = _run("run", d, env=_stub_env(d))
    assert r.returncode == 0, r.stdout + r.stderr
    dumps = [c for c in _calls(d) if "--format=custom" in c]
    assert len(dumps) == 1, _calls(d)
    assert "--exclude-table-data=continuity_archives" in dumps[0].split()
    assert "--compress=6" in dumps[0].split()
    assert "BK excluded_table_data continuity_archives" in r.stdout


def test_housekeep_runs_backup_sh_by_default_and_records_its_verified_dump():
    d = _dir()
    r = _run("run", d, env=_stub_env(d, BACKUP_KEEP="2"))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    order = ["BK precheck", "BK start", "BK restore_ok", "BK RESULT OK", "BK manifest recorded",
             "BK rotate kept", "BK check ok", "BK offsite disabled"]
    pos = [out.index(m) for m in order]
    assert pos == sorted(pos), out
    # The comparison expects 0 restored rows for the excluded table, and reports no drift.
    assert "BK excluded continuity_archives restored=0 source_now=3" in out
    assert "BK drift continuity_archives" not in out and "BK drift jobs" not in out
    assert "BK tables 2 restored_rows 7 tables_changed_since_snapshot 0" in out
    [name] = _dumps(d)
    assert f"BK RESULT OK {d}/{name}" in out
    assert f'"event":"verified","file":"{name}"' in (d / "MANIFEST.jsonl").read_text()


def test_restored_archive_rows_or_archive_data_in_the_dump_fail_and_record_nothing():
    d = _dir()
    r = _run("run", d, env=_stub_env(d, FAKE_RESTORED_ARCHIVES="2"))
    assert r.returncode == 1, r.stdout
    assert "BK RESULT FAIL excluded-table check continuity_archives:restored=2" in r.stdout
    assert "nothing recorded" in r.stdout and '"verified"' not in (d / "MANIFEST.jsonl").read_text()
    d = _dir()
    r = _run("run", d, env=_stub_env(d, FAKE_ARCHIVE_DATA_IN_TOC="1"))
    assert r.returncode == 1
    assert "BK RESULT FAIL dump contains TABLE DATA for continuity_archives" in r.stdout
    assert not any(c.startswith("restore ") for c in _calls(d)), "restored a bad dump"


def test_daily_runs_through_housekeep_keep_the_newest_two_verified_dumps():
    d = _dir()
    made = []
    for _ in range(4):
        r = _run("run", d, env=_stub_env(d, BACKUP_KEEP="2"))
        assert r.returncode == 0, r.stdout + r.stderr
        made.append(r.stdout.split("BK RESULT OK ")[1].split()[0].rsplit("/", 1)[1])
    assert len(set(made)) == 4
    assert _dumps(d) == made[-2:], (made, _dumps(d))
    manifest = (d / "MANIFEST.jsonl").read_text()
    assert manifest.count('"event":"verified"') == 4 and manifest.count('"event":"deleted"') == 2
    sums = (d / "SHA256SUMS").read_text().splitlines()
    assert [ln.split()[1] for ln in sums] == made[-2:]
    assert subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=d,
                          capture_output=True).returncode == 0


def test_first_run_adopts_legacy_dumps_and_cleans_up_to_the_newest_two():
    """The volume as it is today: legacy dumps from the old job, one of them truncated, and no
    manifest. The first run keeps the newest legacy dump that reads back in full plus the new
    one; the second run leaves only new, archive-free dumps."""
    d = _dir()
    legacy = [f"brambleloop_prod_202611{day:02d}T121900Z.dump" for day in (17, 18, 19, 20)]
    for name in legacy[:3]:
        (d / name).write_bytes(os.urandom(4096))
    (d / legacy[3]).write_bytes(b"TRUNC" + os.urandom(100))  # a partial, failed run
    r = _run("run", d, env=_stub_env(d, BACKUP_KEEP="2"))
    assert r.returncode == 0, r.stdout + r.stderr
    # Newest first: the truncated one is refused, the next two read back, the oldest is not
    # even read (it is beyond the newest 2 and is deleted either way).
    assert r.stdout.count("BK adopt verified legacy") == 2
    assert f"BK adopt refused {legacy[3]}" in r.stdout
    assert f"BK adopt skipped {legacy[0]}" in r.stdout
    new1 = r.stdout.split("BK RESULT OK ")[1].split()[0].rsplit("/", 1)[1]
    assert _dumps(d) == sorted([legacy[2], new1]), _dumps(d)
    assert f"BK rotate removed unverified {legacy[3]}" in r.stdout
    r = _run("run", d, env=_stub_env(d, BACKUP_KEEP="2"))
    assert r.returncode == 0 and "BK adopt" not in r.stdout, r.stdout
    new2 = r.stdout.split("BK RESULT OK ")[1].split()[0].rsplit("/", 1)[1]
    assert _dumps(d) == [new1, new2]
    assert _run("check", d).returncode == 0


def test_encode_builds_payloads_that_decode_to_the_exact_scripts():
    out = Path(tempfile.mkdtemp(prefix="enc-"))
    r = subprocess.run(["bash", str(ENCODE), str(out)], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    pairs = (("SCRIPT_B64", BACKUP), ("HOUSEKEEP_B64", SCRIPT))
    for var, src in pairs:
        b64 = (out / var).read_text()
        assert "\n" not in b64 and base64.b64decode(b64) == src.read_bytes()
        assert hashlib.sha256(src.read_bytes()).hexdigest() in r.stdout
    assert len(pairs) == 2 and r.stdout.count("sha256 ") == 2
    p = subprocess.run(["bash", str(ENCODE), "--print", "SCRIPT_B64"], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0 and base64.b64decode(p.stdout) == BACKUP.read_bytes()
    g = subprocess.run(["bash", str(ENCODE), "--print-gz", "HOUSEKEEP_B64"], capture_output=True,
                       text=True, timeout=60)
    import gzip
    assert g.returncode == 0 and gzip.decompress(base64.b64decode(g.stdout)) == SCRIPT.read_bytes()
    assert subprocess.run(["bash", str(ENCODE), "--print", "NOPE"],
                          capture_output=True).returncode == 2


# -- 2026-11-28 production incident: the first run on a full volume ------------------------
#
# Reproduced on a real, size-limited tmpfs so ENOSPC is the kernel's, not a simulation: six
# legacy dumps, the partial from an earlier failed run, a manifest whose appends were cut
# short, and a second partial that filled the volume to the last byte.

LEGACY = ["20261112T013853Z", "20261117T032249Z", "20261119T132003Z", "20261119T155212Z",
          "20261119T165654Z", "20261120T121953Z"]
PARTIALS = ["20261128T051026Z", "20261128T060409Z"]


def _mount_full_volume(size_kib: int):
    d = _dir()
    r = subprocess.run(["mount", "-t", "tmpfs", "-o", f"size={size_kib}k", "tmpfs", str(d)],
                       capture_output=True, text=True)
    return (d if r.returncode == 0 else None), r.stderr.strip()


def _umount(d: Path):
    subprocess.run(["umount", str(d)], capture_output=True)


def _fill(path: Path):
    """Write a partial dump until the volume refuses, as pg_dump did."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, b"TRUNC")
        while True:
            os.write(fd, os.urandom(4096))
    except OSError:
        pass
    finally:
        os.close(fd)


def _free(d: Path) -> int:
    st = os.statvfs(d)
    return st.f_bavail * st.f_frsize


def test_full_volume_with_failed_manifest_writes_recovers_and_keeps_two():
    d, why = _mount_full_volume(1024)
    if d is None:
        print(f"SKIP cannot mount a size-limited tmpfs here ({why})")
        return
    try:
        names = [f"brambleloop_prod_{ts}.dump" for ts in LEGACY]
        for n in names:
            (d / n).write_bytes(os.urandom(120 * 1024))
        (d / f"brambleloop_prod_{PARTIALS[0]}.dump").write_bytes(b"TRUNC" + os.urandom(40000))
        # The incident's manifest: the adopt appends were cut short by ENOSPC.
        (d / "MANIFEST.jsonl").write_bytes(b'{"event":"verified","file":"brambleloop_prod_2026')
        _fill(d / f"brambleloop_prod_{PARTIALS[1]}.dump")
        assert _free(d) < 4096, "the volume must start full"
        with open(d / "MANIFEST.jsonl", "ab") as fh:  # the incident's failing write, for real
            try:
                fh.write(b"x" * 8192); fh.flush(); os.fsync(fh.fileno())
                raise AssertionError("a manifest append succeeded on a full volume")
            except OSError:
                pass
        env = _stub_env(d, BACKUP_KEEP="2", FAKE_DUMP_BYTES=str(100 * 1024))
        r = _run("run", d, env=env)
        out = r.stdout
        assert r.returncode == 0, out + r.stderr
        for p in PARTIALS:
            assert f"BK adopt refused brambleloop_prod_{p}.dump" in out
            assert f"BK rotate removed unverified brambleloop_prod_{p}.dump" in out
        assert out.count("BK adopt verified legacy") == 2
        assert "precheck no previous dump" not in out and "manifest write FAILED" not in out
        # Deletes come before the first manifest write and before the dump.
        assert out.index("BK rotate removed unverified") < out.index("BK adopt recorded 2")
        assert out.index("BK adopt recorded 2") < out.index("BK precheck ok") < out.index("BK start")
        new = out.split("BK RESULT OK ")[1].split()[0].rsplit("/", 1)[1]
        assert (d / new).stat().st_size == 100 * 1024, "the new dump was not written in full"
        assert _dumps(d) == [names[-1], new], _dumps(d)
        assert "BK rotate kept 2 verified (keep 2)" in out
        assert subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=d,
                              capture_output=True).returncode == 0
        manifest = (d / "MANIFEST.jsonl").read_text()
        assert '"event":"adopt-done"' in manifest and '"adopted":true' in manifest
        # The next day: only new dumps, no adoption, still 2.
        r = _run("run", d, env=env)
        assert r.returncode == 0 and "BK adopt" not in r.stdout, r.stdout
        new2 = r.stdout.split("BK RESULT OK ")[1].split()[0].rsplit("/", 1)[1]
        assert _dumps(d) == [new, new2]
        assert _run("check", d).returncode == 0
    finally:
        _umount(d)


def test_a_manifest_that_cannot_be_written_is_fatal_and_no_dump_is_attempted():
    d, why = _mount_full_volume(512)
    if d is None:
        print(f"SKIP cannot mount a size-limited tmpfs here ({why})")
        return
    try:
        only = d / f"brambleloop_prod_{LEGACY[-1]}.dump"
        only.write_bytes(os.urandom(100 * 1024))
        _fill(d / "not-a-dump.bin")  # space nothing here may delete
        r = _run("run", d, env=_stub_env(d, BACKUP_KEEP="2"))
        assert r.returncode == 1, r.stdout
        assert "manifest write FAILED" in r.stdout and "no dump attempted" in r.stdout
        assert "precheck no previous dump" not in r.stdout
        assert not any("--format=custom" in c for c in _calls(d)), "pg_dump ran anyway"
        assert only.exists() and _dumps(d) == [only.name], "the only verified dump was touched"
    finally:
        _umount(d)


def test_partials_are_kept_when_no_verified_dump_would_remain():
    d = _dir()
    p = [f"brambleloop_prod_{ts}.dump" for ts in PARTIALS]
    for n in p:
        (d / n).write_bytes(b"TRUNC" + os.urandom(64))
    r = _run("precheck", d, env=_stub_env(d))
    assert r.returncode == 0, r.stdout
    assert "no verified dump on the volume; 2 unverified left untouched" in r.stdout
    assert _dumps(d) == p


def _pg_bin() -> Path | None:
    for cand in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        if (cand / "initdb").exists() and (cand / "pg_ctl").exists():
            return cand
    return None


def test_real_postgres_dump_restores_with_archive_schema_and_no_archive_rows():
    pgbin = _pg_bin()
    if pgbin is None or os.geteuid() != 0 or subprocess.run(
            ["id", "postgres"], capture_output=True).returncode != 0:
        print("SKIP no local Postgres cluster binaries, or not root with a postgres user")
        return
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); src_port = s.getsockname()[1]; s.close()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); rst_port = s.getsockname()[1]; s.close()
    # Cluster homes live in short /tmp paths the postgres user can enter (socket paths are
    # capped near 107 bytes and the per-suite TMPDIR is root-only); removed in finally.
    home = Path(tempfile.mkdtemp(prefix="bkpg-", dir="/tmp"))
    os.chmod(home, 0o755)
    shutil.chown(home, "postgres")
    data = home / "src"
    asp = ["runuser", "-u", "postgres", "--"]
    path = f"{pgbin}:{os.environ['PATH']}"
    src = f"host={home} port={src_port} user=postgres dbname=bramble"
    try:
        subprocess.run(asp + [str(pgbin / "initdb"), "-D", str(data), "-U", "postgres", "-A",
                              "trust", "--no-sync"], check=True, capture_output=True)
        subprocess.run(asp + [str(pgbin / "pg_ctl"), "-D", str(data), "-l", str(home / "log"),
                              "-w", "-o", f"-p {src_port} -k {home} -c listen_addresses=",
                              "start"], check=True, capture_output=True)
        sql = ("create table jobs(id serial primary key, k text);"
               "insert into jobs(k) select 'j'||g from generate_series(1,5) g;"
               "create table continuity_archives(id serial primary key, blob bytea);"
               "insert into continuity_archives(blob) select decode(repeat('ab', 50000),'hex')"
               " from generate_series(1,3);")
        subprocess.run(["psql", f"host={home} port={src_port} user=postgres dbname=postgres",
                        "-qc", "create database bramble"], check=True, capture_output=True)
        subprocess.run(["psql", src, "-qc", sql], check=True, capture_output=True)
        before = set(Path("/tmp").glob("bkr-*"))
        d = _dir()
        env = _env(PATH=path, SRC_URL=src, BACKUP_DIR=str(d), BK_RESTORE_PORT=str(rst_port),
                   BACKUP_KEEP="2")
        names = []
        for i in range(3):
            if i:
                import time; time.sleep(1.1)  # dump names have one-second resolution
            r = _run("run", d, env=env)
            assert r.returncode == 0, r.stdout + r.stderr
            names.append(r.stdout.split("BK RESULT OK ")[1].split()[0])
        out = r.stdout
        assert "BK restore_ok" in out
        assert "BK excluded continuity_archives restored=0 source_now=3" in out
        assert "BK tables 2 restored_rows 5 tables_changed_since_snapshot 0" in out
        toc = subprocess.run(["pg_restore", "--list", names[-1]], capture_output=True,
                             text=True, check=True).stdout
        assert " TABLE public continuity_archives " in toc
        assert "TABLE DATA public jobs " in toc
        assert "TABLE DATA public continuity_archives" not in toc
        assert [str(d / n) for n in _dumps(d)] == names[-2:]
        assert set(Path("/tmp").glob("bkr-*")) <= before, \
            "backup.sh left its scratch restore cluster behind"
    finally:
        subprocess.run(asp + [str(pgbin / "pg_ctl"), "-D", str(data), "-m", "immediate",
                              "stop"], capture_output=True)
        shutil.rmtree(home, ignore_errors=True)


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
