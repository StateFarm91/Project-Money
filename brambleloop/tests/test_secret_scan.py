"""Secret scan gate (F-159): no credential in the repository, its evidence or its generated artefacts.

WHY A SCAN AND NOT ONLY CAREFUL CODE. The protections that existed were targeted: the continuity
export redacts connection strings, OAuth tokens live in a sealed store, and the Anthropic key
that was once pasted into a session is held only as a Railway variable. Each of those covers the
path somebody thought of. A credential that reaches a log fixture, an evidence JSON written by a
worker, or a rendered report reaches it by a path nobody thought of -- which is exactly the path
a targeted protection does not cover. So this reads every byte that could be released and fails
on anything shaped like a credential.

WHAT IS SCANNED
  * every file git tracks in the whole repository (not only brambleloop/), and every untracked
    file git has not been told to ignore -- i.e. everything the next `git add -A` would commit;
  * the generated directories that are deliberately ignored but still leave the machine in
    evidence bundles or backups: brambleloop/artifacts/, brambleloop/backups/,
    brambleloop/reports/shadow_release/_store/, and every research/**/evidence directory.
Binary files (a NUL byte in the first 8 KiB) are skipped, as are files over 20 MB; both limits
are stated because a scan that silently skips is the failure this file exists to prevent.
A compressed PDF stream is not decoded -- a named limit, not a pass.

WHAT A HIT LOOKS LIKE. A finding names the file, the line, the pattern and a 12-hex fingerprint
(sha256 of the matched text). It NEVER contains the matched text: a secret scanner whose failure
message prints the secret has moved the leak from the repository into the CI log.

THE ALLOW-LIST is keyed by (path, pattern, fingerprint), so an allowance covers exactly one
known, reviewed string in one file -- not a file, not a pattern. A new string in an allowed file
still fails. Every entry must say why it is not a credential.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # brambleloop/
REPO = ROOT.parent

# Built from fragments so this file does not match its own patterns when it is scanned.
_SK = "sk" + "-"
PATTERNS: dict[str, re.Pattern] = {
    "anthropic_key": re.compile(_SK + r"ant-[a-z]+\d*-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(_SK + r"(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"
                             r"T3Blbk" + r"FJ[A-Za-z0-9_\-]{10,}|"
                             + _SK + r"(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{40,}"),
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws_secret_access_key": re.compile(
        r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?"
                              r"PRIVATE KEY(?: BLOCK)?-----"),
    # A literal bearer token. `f"Bearer {token}"` does not match: the braces are not token
    # characters, so only a credential written out in full is caught.
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{24,}=*"),
    # Etsy: an OAuth access token is "<numeric user id>.<long urlsafe token>"; a v3 keystring is
    # 24 lowercase alphanumerics and is only distinguishable by context, so it is matched only
    # when assigned to something that names it.
    "etsy_oauth_token": re.compile(r"\b\d{5,12}\.[A-Za-z0-9_\-]{50,}"),
    "etsy_keystring": re.compile(r"(?i)(?:etsy[_\-]?(?:api[_\-]?)?key(?:string)?|keystring|"
                                 r"x-api-key)[\"']?\s*[:=]\s*[\"']?[a-z0-9]{24}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|"
                               r"\bgithub_pat_[A-Za-z0-9_]{50,}"),
    "stripe_live_key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{20,}"),
    # A connection string with an inline password. Placeholders (`***`, `<...>`, `$VAR`,
    # `{...}`) are not credentials and are excluded by the character class.
    "db_url_password": re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|amqp)(?:\+\w+)?://"
                                  r"[^\s:/@\"'<>{}$*]+:[^\s@/\"'<>{}$*]{6,}@[\w.\-]+"),
}

# (repo-relative path, pattern, fingerprint) -> why it is not a credential.
# Reviewed 2026-09-28: every entry is a deliberately fake value in a test that proves a real
# credential is refused or redacted. Each is lowercase words and hyphens / the word "hunter2".
ALLOW: dict[tuple[str, str, str], str] = {
    ("brambleloop/tests/test_continuity.py", "db_url_password", "8eb43038eda2"):
        "the 'hunter2' fixture the redaction test proves is masked in the export",
    ("brambleloop/tests/test_etsy_exercise.py", "bearer_token", "abef6d67251a"):
        "a wrong operator token ('not-the-operator-token...') the endpoint must refuse",
    ("brambleloop/tests/test_etsy_exercise.py", "bearer_token", "e1e776d6d36e"):
        "a wrong operator token ('wrong-but-long-enough...') the endpoint must refuse",
    ("brambleloop/tests/test_etsy_oauth_callback.py", "bearer_token", "2fd7f17c8290"):
        "a wrong operator token ('not-the-operator-token...') the callback must refuse",
    ("brambleloop/tests/test_policy_intake.py", "bearer_token", "ca7a0c5d29eb"):
        "a wrong operator token ('wrong-token-of-...') the intake must refuse",
}

GENERATED_DIRS = ("brambleloop/artifacts", "brambleloop/backups",
                  "brambleloop/reports/shadow_release/_store")
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", "benchmark_library"}
MAX_BYTES = 20 * 1024 * 1024


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """[(line number, pattern name, fingerprint)] -- never the matched text itself."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pat in PATTERNS.items():
            for m in pat.finditer(line):
                out.append((n, name, fingerprint(m.group(0))))
    return out


def _git_files() -> list[Path]:
    res = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], capture_output=True, check=True)
    return [REPO / p for p in res.stdout.decode().split("\0") if p]


def _generated_files() -> list[Path]:
    roots = [REPO / d for d in GENERATED_DIRS]
    roots += [p for p in (ROOT / "research").rglob("evidence") if p.is_dir()]
    out = []
    for r in roots:
        if r.is_dir():
            out += [p for p in r.rglob("*") if p.is_file()]
    return out


def candidate_files() -> list[Path]:
    seen, out = set(), []
    for p in _git_files() + _generated_files():
        rel = p.relative_to(REPO)
        if rel in seen or SKIP_PARTS & set(rel.parts) or not p.is_file() or p.is_symlink():
            continue
        seen.add(rel)
        out.append(p)
    return out


def _read_text(p: Path) -> str | None:
    if p.stat().st_size > MAX_BYTES:
        return None
    raw = p.read_bytes()
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_repository() -> tuple[list[str], int, list[str]]:
    """(findings, files scanned, files skipped) -- findings are path:line pattern fingerprint."""
    findings, skipped, scanned = [], [], 0
    for p in candidate_files():
        text = _read_text(p)
        if text is None:
            skipped.append(str(p.relative_to(REPO)))
            continue
        scanned += 1
        rel = str(p.relative_to(REPO))
        for line, name, fp in scan_text(text):
            if (rel, name, fp) not in ALLOW:
                findings.append(f"{rel}:{line} {name} fp={fp}")
    return findings, scanned, skipped


# --- the gate ------------------------------------------------------------------------------------
def test_no_credential_shaped_string_in_tracked_files_evidence_or_generated_artefacts():
    findings, scanned, _ = scan_repository()
    assert scanned > 500, f"only {scanned} files scanned; the scan is not seeing the repository"
    assert not findings, ("credential-shaped strings found (values withheld):\n  "
                          + "\n  ".join(findings))


def test_every_allow_list_entry_still_matches_something_so_the_list_cannot_rot():
    # An allowance for a string that is gone is an allowance waiting for a different string
    # with the same fingerprint -- vanishingly unlikely, but a dead entry is also a lie about
    # what the tree contains. Keep the list exactly as long as the reviewed strings.
    live = set()
    for p in candidate_files():
        rel = str(p.relative_to(REPO))
        if not any(k[0] == rel for k in ALLOW):
            continue
        text = _read_text(p) or ""
        live |= {(rel, name, fp) for _, name, fp in scan_text(text)}
    dead = [k for k in ALLOW if k not in live]
    assert not dead, f"allow-list entries that no longer match anything: {dead}"
    assert all(why.strip() for why in ALLOW.values())


# --- the detector detects (built at runtime so this file never contains a literal) ----------------
def _fake(prefix: str, body: str) -> str:
    return prefix + body


def test_each_credential_family_is_detected_by_its_pattern():
    a = "A1b2C3d4E5f6G7h8I9j0" * 3
    samples = {
        "anthropic_key": _fake(_SK + "ant-" + "api03-", a),
        "openai_key": _fake(_SK + "proj-", a),
        "aws_access_key_id": _fake("AK" + "IA", "ABCDEFGHIJKLMNOP"),
        "aws_secret_access_key": "aws_secret_access_key = " + ("abcdEFGH1234/+ab" * 3)[:40],
        "private_key": "-----BEGIN " + "RSA PRIVATE KEY-----",
        "bearer_token": "Authorization: Bear" + "er " + a,
        "etsy_oauth_token": "123456789." + a + a,
        "etsy_keystring": "ETSY_API_KEY=" + "abcdefghijklmnopqrstuvwx",
        "github_token": _fake("gh" + "p_", "a" * 36),
        "stripe_live_key": _fake("sk" + "_live_", a),
        "slack_token": _fake("xo" + "xb-", a),
        "db_url_password": "postgresql://brambleloop:" + "Zq8rT2vW" + "@db.internal/app",
    }
    assert set(samples) == set(PATTERNS), "a pattern has no positive sample"
    for name, sample in samples.items():
        hits = {n for _, n, _ in scan_text(sample)}
        assert name in hits, f"{name} not detected"


def test_placeholders_and_templated_headers_are_not_findings():
    benign = "\n".join([
        'headers = {"Authorization": f"Bearer {token}"}',
        "postgresql://***@host/db",
        "postgresql://user:${PGPASSWORD}@host/db",
        "DATABASE_URL=postgresql://<user>:<password>@<host>/<db>",
        "ANTHROPIC_API_KEY is read from the environment",
        "x-api-key: {keystring}",
    ])
    assert scan_text(benign) == [], scan_text(benign)


def test_a_finding_never_contains_the_matched_value():
    secret = _fake(_SK + "ant-" + "api03-", "Q" * 40)
    hits = scan_text("key = " + secret)
    assert hits and all(secret not in str(h) for h in hits)
    assert hits[0][2] == fingerprint(secret)


def test_the_scan_includes_untracked_and_generated_files_not_only_what_git_tracks():
    # A file a worker wrote but has not committed yet is exactly the one about to be released.
    probe = ROOT / "research" / "_secret_scan_probe" / "evidence" / "probe.json"
    probe.parent.mkdir(parents=True, exist_ok=True)
    try:
        probe.write_text('{"k": "' + _fake(_SK + "ant-" + "api03-", "Z" * 40) + '"}')
        findings, _, _ = scan_repository()
        mine = [f for f in findings if "_secret_scan_probe" in f]
        assert mine and "anthropic_key" in mine[0], findings
    finally:
        probe.unlink(missing_ok=True)
        for d in (probe.parent, probe.parent.parent):
            try:
                d.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
