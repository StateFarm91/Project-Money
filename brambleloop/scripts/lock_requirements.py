#!/usr/bin/env python3
"""Generate `requirements.lock` from the interpreter the suite actually ran on (F-158, F-416).

WHY NOT pip-compile. `requirements.txt` carries only lower bounds (`>=`), so a rebuild of the
production image could pull a major version nobody had ever tested -- the suite passing on a
developer venv said nothing about what the container would install that night. The usual fix
is `pip-compile --generate-hashes`, which *resolves afresh* against today's index. That closes
the drift going forward but pins whatever is newest today, which is again a set the suite has
never run on. The requirement is the opposite: the image must install exactly what the suite
proved. So the versions here are read from the installed distributions of the interpreter this
script runs under (the project venv), and only the hashes come from the index.

WHAT IT DOES
  1. Parses `requirements.txt` (the human-edited intent: names, extras, lower bounds).
  2. Walks the installed dependency closure through `importlib.metadata`, evaluating each
     `Requires-Dist` marker for this interpreter (CPython 3.11 on Linux, which is also the
     `python:3.11-slim` image) and carrying extras (`uvicorn[standard]`) through.
  3. Refuses if any installed version does not satisfy the specifier in `requirements.txt`, or
     if a required distribution is not installed at all -- a lock of a venv that does not meet
     its own requirements file would be a lie with hashes on it.
  4. For each pinned `name==version`, asks PyPI's JSON API for the sha256 of every published
     file of that exact version (wheels for every platform and the sdist, as pip-compile does)
     so `pip install --require-hashes` works on whichever wheel the image's platform selects.
  5. Writes the lock, and prints a supply-chain change record (added / removed / version
     changed against the previous lock) so a material change is visible in the commit that
     makes it rather than discovered in production.

`--check` runs steps 1-3 offline and compares against the committed lock: exit 1 if the venv
and the lock disagree. It never touches the network.

This script is the only network client in the dependency path, it talks only to pypi.org, and
it is run by hand. Nothing in the service or the suite imports it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # `packaging` is not in the lock; pip always vendors it.
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
REQS = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock"

_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+?)(\s*\\)?$")


def read_requirements(path: Path = REQS) -> list[Requirement]:
    out = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(Requirement(line))
    return out


def _marker_ok(req: Requirement, extras: set[str]) -> bool:
    if req.marker is None:
        return True
    env = default_environment()
    # A marker without `extra` must hold for the base install; one with `extra` must hold for
    # some requested extra. Evaluating against "" covers the base case.
    for extra in (extras or {""}) | {""}:
        env["extra"] = extra
        if req.marker.evaluate(env):
            return True
    return False


def closure(reqs: list[Requirement]) -> dict[str, tuple[str, str]]:
    """{canonical name: (display name, installed version)} for the whole installed closure.

    Raises SystemExit naming the first requirement the venv does not satisfy.
    """
    found: dict[str, tuple[str, str]] = {}
    extras_seen: dict[str, set[str]] = {}
    stack: list[Requirement] = list(reqs)
    top = {canonicalize_name(r.name): r for r in reqs}
    while stack:
        req = stack.pop()
        key = canonicalize_name(req.name)
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            raise SystemExit(f"{req.name} is required but not installed in {sys.prefix}")
        version = dist.version
        if key in top and top[key].specifier and version not in top[key].specifier:
            raise SystemExit(f"installed {req.name}=={version} does not satisfy "
                             f"requirements.txt `{top[key]}`")
        new_extras = set(req.extras) - extras_seen.get(key, set())
        if key in found and not new_extras:
            continue
        found[key] = (dist.metadata["Name"], version)
        extras_seen.setdefault(key, set()).update(req.extras)
        for dep in dist.requires or []:
            d = Requirement(dep)
            if _marker_ok(d, extras_seen[key]):
                # Only follow deps whose marker needs an extra if that extra was requested.
                if d.marker is not None and "extra" in str(d.marker):
                    env = default_environment()
                    if not any(d.marker.evaluate({**env, "extra": e})
                               for e in extras_seen[key]):
                        continue
                stack.append(d)
    return found


def read_lock(path: Path = LOCK) -> dict[str, tuple[str, str, list[str]]]:
    """{canonical name: (display name, version, [sha256 hashes])} from a lock file."""
    out: dict[str, tuple[str, str, list[str]]] = {}
    current = None
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            current = canonicalize_name(m.group(1))
            out[current] = (m.group(1), m.group(2), [])
            continue
        h = re.match(r"^--hash=sha256:([0-9a-f]{64})(\s*\\)?$", line)
        if h and current:
            out[current][2].append(h.group(1))
            continue
        raise SystemExit(f"unrecognised line in {path.name}: {raw!r}")
    return out


def pypi_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=60) as r:            # noqa: S310 (fixed host)
        data = json.load(r)
    hashes = sorted({f["digests"]["sha256"] for f in data.get("urls", [])})
    if not hashes:
        raise SystemExit(f"PyPI lists no files for {name}=={version}")
    return hashes


def render(pins: dict[str, tuple[str, str, list[str]]]) -> str:
    head = [
        "# GENERATED by scripts/lock_requirements.py -- do not edit by hand.",
        "# Versions are those installed in the project venv the acceptance suite ran on;",
        "# hashes are every sha256 PyPI publishes for that exact version. Install with:",
        "#   pip install --require-hashes -r requirements.lock",
        "# requirements.txt stays the human-edited intent; this file is what is installed.",
        "",
    ]
    body = []
    for key in sorted(pins):
        name, version, hashes = pins[key]
        body.append(f"{name}=={version} \\")
        for i, h in enumerate(hashes):
            tail = " \\" if i < len(hashes) - 1 else ""
            body.append(f"    --hash=sha256:{h}{tail}")
    return "\n".join(head + body) + "\n"


def change_record(old: dict, new: dict) -> list[str]:
    lines = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            lines.append(f"ADDED    {new[k][0]}=={new[k][1]}")
        elif k not in new:
            lines.append(f"REMOVED  {old[k][0]}=={old[k][1]}")
        elif old[k][1] != new[k][1]:
            lines.append(f"CHANGED  {new[k][0]} {old[k][1]} -> {new[k][1]}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="offline: exit 1 if the lock disagrees with this interpreter")
    args = ap.parse_args(argv)
    found = closure(read_requirements())
    old = read_lock()
    if args.check:
        drift = change_record({k: (v[0], v[1]) for k, v in old.items()},
                              {k: v for k, v in found.items()})
        for d in drift:
            print(d)
        return 1 if drift else 0
    pins = {k: (n, v, pypi_hashes(n, v)) for k, (n, v) in found.items()}
    LOCK.write_text(render(pins))
    changes = change_record(old, pins)
    print(f"wrote {LOCK.name}: {len(pins)} distributions")
    print("supply-chain changes vs previous lock:" if changes else "no version changes")
    for c in changes:
        print("  " + c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
