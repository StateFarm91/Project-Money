"""ENG-AUTOCODER: where the autocoder's workspace comes from and where its branch goes.

Two hosts, one contract:

* `materialize(base, dest)` puts the repository at `base` (a commit SHA or branch name) into
  the empty directory `dest` -- a depth-1 snapshot, the equivalent of a shallow clone -- and
  returns the resolved 40-hex SHA.
* `ci_status(sha, context)` reads the CI sandbox's verdict on a pushed commit (B19 A1): the
  autocoder never runs the code it pushes; `.github/workflows/autocoder-ci.yml` does.
* `push(ref, base_sha, files, message)` creates one commit on top of `base_sha` whose only
  changes are `files` ({repo-relative path: new text}) and points `ref` at it. Returns the
  commit SHA. **`ref` must pass `autocoder_safety.assert_ref_allowed`** (`refs/heads/auto/*`):
  each host checks it again itself, so neither the job nor a caller can reach the production
  branch, `main` or a release branch through it.

`GitHubHost` is production. The worker image has no git credentials and need not run git for
the workspace: it reads a tarball of the base commit (`GET /repos/{repo}/tarball/{sha}`) and
writes the branch through the Git Data API (blobs -> tree on the base tree -> commit -> ref),
authenticated by the owner-issued fine-grained token `BRAMBLELOOP_GITHUB_TOKEN`
(contents:write on this one repository). The token is read from the process environment at
call time, sent only to api.github.com (and GitHub's own tarball redirect), and never logged,
returned or written.

`LocalGitHost` drives the `git` binary against a local repository. It is what the tests use
(a toy repository in a temp directory) and needs no network.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from .autocoder_safety import assert_ref_allowed, normalize, path_refusal

TOKEN_VAR = "BRAMBLELOOP_GITHUB_TOKEN"
REPO_VAR = "BRAMBLELOOP_AUTOCODER_REPO"
DEFAULT_REPO = "statefarm91/project-money"
API = "https://api.github.com"
_SHA = re.compile(r"^[0-9a-f]{40}$")
# Extraction limits: the repository is ~400 MB unpacked; generous but finite.
MAX_EXTRACT_BYTES = 2 * 1024 ** 3
MAX_MEMBER_BYTES = 50 * 1024 ** 2
HTTP_TIMEOUT_S = 120


class HostError(RuntimeError):
    """The host could not do what was asked (network, auth, missing ref). Retryable."""


class HostBlocked(RuntimeError):
    """A named, owner-fixable blocker (no token, no git binary). Never a silent no-op."""


def token_present() -> bool:
    return bool((os.environ.get(TOKEN_VAR) or "").strip())


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> dict:
    """Extract regular files and directories only, under `dest`, stripping the top folder."""
    total = files = skipped = 0
    dest = dest.resolve()
    for m in tar.getmembers():
        parts = m.name.split("/", 1)
        if len(parts) < 2 or not parts[1]:
            continue
        rel = parts[1]
        if rel.startswith("/") or ".." in rel.split("/") or "\x00" in rel:
            raise HostError(f"unsafe path in tarball: {m.name!r}")
        target = (dest / rel).resolve()
        if dest not in target.parents and target != dest:
            raise HostError(f"tarball member escapes the workspace: {m.name!r}")
        if m.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not m.isfile() or m.size > MAX_MEMBER_BYTES:
            skipped += 1        # symlinks, devices, oversized binaries: never needed to test
            continue
        total += m.size
        if total > MAX_EXTRACT_BYTES:
            raise HostError("tarball exceeds the workspace extraction limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        src = tar.extractfile(m)
        if src is None:
            skipped += 1
            continue
        with open(target, "wb") as fh:
            shutil.copyfileobj(src, fh)
        os.chmod(target, 0o755 if m.mode & 0o111 else 0o644)
        files += 1
    return {"files": files, "skipped": skipped, "bytes": total}


class GitHubHost:
    """The production host: GitHub's REST API with the owner-issued token."""

    name = "github"

    def __init__(self, repo: str | None = None, *, opener=None):
        self.repo = (repo or os.environ.get(REPO_VAR) or DEFAULT_REPO).strip()
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", self.repo):
            raise HostBlocked(f"{REPO_VAR} is not owner/name")
        self._opener = opener or urllib.request.urlopen

    def _token(self) -> str:
        tok = (os.environ.get(TOKEN_VAR) or "").strip()
        if not tok:
            raise HostBlocked(f"{TOKEN_VAR} is not set: the autocoder cannot read the "
                              f"repository or push an auto/* branch (OWNER_ACTIONS_AUTOCODER.md)")
        return tok

    def _call(self, method: str, path: str, body: dict | None = None, *,
              raw: bool = False, to_file: Path | None = None):
        url = f"{API}/repos/{self.repo}{path}"
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token()}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "brambleloop-autocoder")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener(req, timeout=HTTP_TIMEOUT_S) as resp:
                if to_file is not None:
                    # Streamed to disk: the tarball is large and the worker's memory is not.
                    total = 0
                    with open(to_file, "wb") as fh:
                        while True:
                            chunk = resp.read(1 << 20)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_EXTRACT_BYTES:
                                raise HostError("tarball exceeds the download limit")
                            fh.write(chunk)
                    return to_file
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            # The body may echo the request; only the status and GitHub's message leave.
            try:
                msg = json.loads(exc.read() or b"{}").get("message", "")
            except Exception:  # noqa: BLE001
                msg = ""
            raise HostError(f"GitHub {method} {path.split('?')[0]} -> HTTP {exc.code} "
                            f"{str(msg)[:120]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HostError(f"GitHub {method} {path.split('?')[0]} unreachable: "
                            f"{type(exc).__name__}") from None
        return payload if raw else json.loads(payload or b"{}")

    def resolve(self, base: str) -> str:
        sha = str(self._call("GET", f"/commits/{base}").get("sha") or "")
        if not _SHA.match(sha):
            raise HostError(f"base {base!r} did not resolve to a commit")
        return sha

    def materialize(self, base: str, dest: Path) -> str:
        sha = self.resolve(base)
        dest = Path(dest)
        archive = dest.parent / f".{dest.name}.tar.gz"
        try:
            self._call("GET", f"/tarball/{sha}", to_file=archive)
            with tarfile.open(archive, mode="r:*") as tar:
                _safe_extract(tar, dest)
        finally:
            try:
                archive.unlink()
            except OSError:
                pass
        return sha

    def ci_status(self, sha: str, context: str) -> dict:
        """B19 A1: the newest commit status in `context` on `sha` (the autocoder-ci workflow's
        verdict), with who posted it. Needs the token's "Commit statuses: read" permission.
        Returns {"state": "none"} when there is none yet."""
        if not _SHA.match(sha or ""):
            raise HostError("ci_status needs a 40-hex commit")
        rows = self._call("GET", f"/commits/{sha}/statuses?per_page=100")
        for row in rows if isinstance(rows, list) else []:
            if row.get("context") == context:
                return {"state": str(row.get("state") or "none"), "sha": sha,
                        "creator": str((row.get("creator") or {}).get("login") or ""),
                        "target_url": str(row.get("target_url") or "")[:300]}
        return {"state": "none", "sha": sha}

    def push(self, ref: str, base_sha: str, files: dict[str, str], message: str) -> str:
        full = assert_ref_allowed(ref)
        if not _SHA.match(base_sha or ""):
            raise HostError("push needs the 40-hex base commit")
        for p in files:
            why = path_refusal(p)
            if why:
                raise PermissionError(f"push refused: {why}")
        base_tree = self._call("GET", f"/git/commits/{base_sha}")["tree"]["sha"]
        entries = []
        for path, text in sorted(files.items()):
            blob = self._call("POST", "/git/blobs", {"content": text, "encoding": "utf-8"})
            entries.append({"path": normalize(path), "mode": "100644", "type": "blob",
                            "sha": blob["sha"]})
        tree = self._call("POST", "/git/trees", {"base_tree": base_tree, "tree": entries})
        commit = self._call("POST", "/git/commits", {"message": message, "tree": tree["sha"],
                                                     "parents": [base_sha]})
        sha = commit["sha"]
        short = full[len("refs/"):]          # "heads/auto/..."
        try:
            self._call("POST", "/git/refs", {"ref": full, "sha": sha})
        except HostError as exc:
            if "422" not in str(exc):
                raise
            # The auto/ branch exists from an earlier attempt of this request. It is ours
            # (auto/* is the autocoder's namespace), so it is moved to the new commit.
            self._call("PATCH", f"/git/refs/{short}", {"sha": sha, "force": True})
        return sha


class LocalGitHost:
    """A local repository driven by the git binary (tests; no network, no token)."""

    name = "local"

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path)
        if shutil.which("git") is None:
            raise HostBlocked("git binary not found")
        # Stand-in for GitHub's commit statuses: tests post the CI sandbox's verdict here.
        self.statuses: dict[str, dict] = {}

    def ci_status(self, sha: str, context: str) -> dict:
        got = self.statuses.get(sha) or {}
        if got.get("context", context) != context:
            return {"state": "none", "sha": sha}
        return {"state": "none", "sha": sha, **got}

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        out = subprocess.run(["git", *args], cwd=str(cwd or self.repo_path),
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise HostError(f"git {args[0]} failed: {out.stderr.strip()[:200]}")
        return out.stdout.strip()

    def resolve(self, base: str) -> str:
        return self._git("rev-parse", f"{base}^{{commit}}")

    def materialize(self, base: str, dest: Path) -> str:
        sha = self.resolve(base)
        dest = Path(dest)
        self._git("archive", "--format=tar", "-o", str(dest / ".snapshot.tar"), sha)
        with tarfile.open(dest / ".snapshot.tar") as tar:
            for m in tar.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    raise HostError(f"unsafe path {m.name!r}")
                if m.isdir():
                    (dest / m.name).mkdir(parents=True, exist_ok=True)
                elif m.isfile():
                    (dest / m.name).parent.mkdir(parents=True, exist_ok=True)
                    with open(dest / m.name, "wb") as fh:
                        shutil.copyfileobj(tar.extractfile(m), fh)
        (dest / ".snapshot.tar").unlink()
        return sha

    def push(self, ref: str, base_sha: str, files: dict[str, str], message: str) -> str:
        full = assert_ref_allowed(ref)
        for p in files:
            why = path_refusal(p)
            if why:
                raise PermissionError(f"push refused: {why}")
        env = {**os.environ, "GIT_INDEX_FILE": str(self.repo_path / ".git" / "autocoder.index"),
               "GIT_AUTHOR_NAME": "brambleloop-autocoder", "GIT_AUTHOR_EMAIL": "autocoder@invalid",
               "GIT_COMMITTER_NAME": "brambleloop-autocoder",
               "GIT_COMMITTER_EMAIL": "autocoder@invalid"}

        def g(*args, inp=None):
            out = subprocess.run(["git", *args], cwd=str(self.repo_path), capture_output=True,
                                 text=True, timeout=120, env=env, input=inp)
            if out.returncode != 0:
                raise HostError(f"git {args[0]} failed: {out.stderr.strip()[:200]}")
            return out.stdout.strip()

        g("read-tree", base_sha)
        for path, text in sorted(files.items()):
            blob = g("hash-object", "-w", "--stdin", inp=text)
            g("update-index", "--add", "--cacheinfo", f"100644,{blob},{normalize(path)}")
        tree = g("write-tree")
        sha = g("commit-tree", tree, "-p", base_sha, "-m", message)
        g("update-ref", full, sha)
        try:
            os.unlink(env["GIT_INDEX_FILE"])
        except OSError:
            pass
        return sha
