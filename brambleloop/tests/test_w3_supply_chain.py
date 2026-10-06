"""Supply chain: lock verification, SBOM, change record, release evidence (F-158, F-416).

Wave 3, lane TOOLS (cluster K14). Offline: reads files and throwaway git repositories only.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = _load("w3_supply_chain", ROOT / "scripts" / "supply_chain.py")
DG = _load("w3_deploy_guard", REPO / "ops" / "deploy_guard.py")

H1, H2 = "a" * 64, "b" * 64
GOOD_LOCK = (f"# header\nalpha==1.0 \\\n    --hash=sha256:{H1}\n"
             f"beta-pkg==2.1 \\\n    --hash=sha256:{H1} \\\n    --hash=sha256:{H2}\n")
GOOD_REQS = "alpha>=1\nBeta_Pkg>=2  # comment\n"
GOOD_DOCKER = ("FROM python:3.11-slim@sha256:" + "c" * 64 + "\nCOPY requirements.lock ./\n"
               "RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock\n")


def test_the_committed_lock_and_dockerfile_verify_and_the_open_pins_are_named():
    v = SC.verify(lock_text=(ROOT / "requirements.lock").read_text(),
                  reqs_text=(ROOT / "requirements.txt").read_text(),
                  docker_text=(ROOT / "Dockerfile").read_text())
    assert v["ok"] is True, v["problems"]
    assert v["distributions"] > 20 and v["hashes"] >= v["distributions"]
    entries = v["_entries"]
    assert entries and all(e["hashes"] and e["version"] for e in entries.values())
    # Honest about what is still unpinned in the build (the deploy-path change is owner/
    # integrator-applied, not made by this lane).
    ids = {f["id"] for f in v["findings"]}
    assert "base_image_not_digest_pinned" in ids, v["findings"]
    assert all(f["remedy"] for f in v["findings"])


def test_a_lock_that_is_not_exact_pinned_and_hashed_is_refused():
    assert SC.verify(lock_text=GOOD_LOCK, reqs_text=GOOD_REQS, docker_text=GOOD_DOCKER)[
        "ok"] is True
    cases = {
        "no sha256 hash": "alpha==1.0\n",
        "not exact-pinned": f"alpha>=1.0 \\\n    --hash=sha256:{H1}\n",
        "listed twice": GOOD_LOCK + f"alpha==1.0 \\\n    --hash=sha256:{H1}\n",
        "not in the lock": f"alpha==1.0 \\\n    --hash=sha256:{H1}\n",
        "option line": "--index-url https://example.invalid/simple\n" + GOOD_LOCK,
        "lists no distributions": "# empty\n",
    }
    assert len(cases) == 6
    for want, lock in cases.items():
        v = SC.verify(lock_text=lock, reqs_text=GOOD_REQS, docker_text=GOOD_DOCKER)
        assert v["ok"] is False and any(want in p for p in v["problems"]), (want, v["problems"])


def test_an_install_path_that_bypasses_the_hash_checked_lock_is_refused():
    cases = {
        "without --require-hashes": GOOD_DOCKER.replace("--require-hashes ", ""),
        "without --no-deps": GOOD_DOCKER.replace("--no-deps ", ""),
        "outside the lock": GOOD_DOCKER + "RUN pip install requests\n",
        "pipes a download": GOOD_DOCKER + "RUN curl -sSL https://example.invalid/x | sh\n",
        "does not install requirements.lock": "FROM python:3.11-slim\nCOPY requirements.lock ./\n",
    }
    assert len(cases) == 5
    for want, docker in cases.items():
        v = SC.verify(lock_text=GOOD_LOCK, reqs_text=GOOD_REQS, docker_text=docker)
        assert v["ok"] is False and any(want in p for p in v["problems"]), (want, v["problems"])
    # A digest-pinned base and versioned apt packages leave no finding.
    pinned = GOOD_DOCKER + "RUN apt-get install -y --no-install-recommends fonts-x=1.2-3\n"
    assert SC.verify(lock_text=GOOD_LOCK, reqs_text=GOOD_REQS, docker_text=pinned)[
        "findings"] == []


def test_sbom_and_change_record_are_derived_from_the_lock():
    entries, problems = SC.parse_lock(GOOD_LOCK)
    assert problems == [] and set(entries) == {"alpha", "beta-pkg"}
    bom = SC.sbom(entries, lock_sha256="x")
    assert bom["bomFormat"] == "CycloneDX" and len(bom["components"]) == 2
    assert {c["purl"] for c in bom["components"]} == {"pkg:pypi/alpha@1.0",
                                                     "pkg:pypi/beta-pkg@2.1"}
    new_lock = (f"alpha==1.1 \\\n    --hash=sha256:{H2}\n"
                f"beta-pkg==2.1 \\\n    --hash=sha256:{H1}\n"
                f"gamma==0.1 \\\n    --hash=sha256:{H1}\n")
    ch = SC.change_record(entries, SC.parse_lock(new_lock)[0])
    assert ch["added"] == ["gamma==0.1"] and ch["removed"] == []
    assert ch["version_changed"] == ["alpha: 1.0 -> 1.1"]
    assert ch["hash_changed_same_version"] == ["beta-pkg"] and ch["material"] is True
    assert SC.change_record(entries, entries)["material"] is False


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_release_evidence_is_computed_at_the_sha_and_a_bad_lock_refuses_the_record():
    repo = Path(tempfile.mkdtemp(prefix="w3sc-"))
    try:
        bl = repo / "brambleloop"
        (bl / "scripts").mkdir(parents=True)
        (bl / "release").mkdir()
        _git(repo, "init", "-q", "-b", "main")
        (bl / "requirements.txt").write_text(GOOD_REQS)
        (bl / "Dockerfile").write_text(GOOD_DOCKER)
        (bl / "requirements.lock").write_text(f"alpha==0.9 \\\n    --hash=sha256:{H1}\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "deployed: before the verifier existed")
        deployed = _git(repo, "rev-parse", "HEAD")
        ev, problems = DG.supply_chain_evidence(repo, deployed)
        assert ev["status"] == "unavailable" and problems == []
        shutil.copy(ROOT / "scripts" / "supply_chain.py", bl / "scripts" / "supply_chain.py")
        (bl / "requirements.lock").write_text(GOOD_LOCK)
        (bl / "release" / "DEPLOYED_HISTORY.json").write_text(json.dumps(
            {"deployed": [{"sha": deployed}]}))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "candidate")
        good = _git(repo, "rev-parse", "HEAD")
        ev, problems = DG.supply_chain_evidence(repo, good)
        assert problems == [] and ev["status"] == "verified", ev
        ch = ev["change_since_deployed"]
        assert ch["base"] == deployed and ch["base_had_lock"] is True
        assert ch["version_changed"] == ["alpha: 0.9 -> 1.0"] and ch["added"] == ["beta-pkg==2.1"]
        assert len(ev["sbom_sha256"]) == 64 and ev["sbom_components"] == 2
        # A working-tree edit does not change the verdict for the committed SHA.
        (bl / "requirements.lock").write_text("alpha==1.0\n")
        assert DG.supply_chain_evidence(repo, good)[0]["status"] == "verified"
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "an unhashed lock")
        bad = _git(repo, "rev-parse", "HEAD")
        ev, problems = DG.supply_chain_evidence(repo, bad)
        assert ev["status"] == "refused" and any("no sha256 hash" in p for p in problems)
        # A release record carrying a refused verdict does not prove its SHA.
        reasons = DG._record_problems({"sha": bad, "release_eligible": True,
                                       "supply_chain": ev}, lambda rel: None)
        assert any("refused supply-chain verdict" in r for r in reasons), reasons
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_the_cli_verify_exits_zero_on_the_repo_and_strict_fails_on_open_pins():
    py = sys.executable
    ok = subprocess.run([py, str(ROOT / "scripts" / "supply_chain.py"), "verify"],
                        capture_output=True, text=True, timeout=60)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["ok"] is True
    strict = subprocess.run([py, str(ROOT / "scripts" / "supply_chain.py"), "verify",
                             "--strict"], capture_output=True, text=True, timeout=60)
    assert strict.returncode == 1          # the base image is not digest-pinned yet


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
