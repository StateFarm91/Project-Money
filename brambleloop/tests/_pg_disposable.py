"""A throwaway local PostgreSQL cluster for one test run (shared helper).

The same pattern as `test_codex_v0_postgres._disposable_cluster` (W6 certification), with the
URL variable and database name as parameters so another suite can use it (review 6955484423
N1: the A3 photo fence reported SKIP whenever its URL was unset, and the runner counts a SKIP
as a suite with no passes -- every full certification went red).

When `env_var` is already set it is used as is. Otherwise, when a local PostgreSQL toolchain
is installed, a brand-new cluster is created under /tmp (the `postgres` user must traverse it):
TCP on 127.0.0.1 only, a free port, one fresh empty database named `db_name`, `initdb -A trust`
(any local user may connect while the test runs: fine in a single-tenant test container, never
on a shared host), and it is destroyed afterwards. With no toolchain nothing is created and the
caller SKIPs.
"""
from __future__ import annotations

import contextlib
import os


@contextlib.contextmanager
def disposable_cluster(env_var: str, db_name: str, prefix: str = "pg-disposable-"):
    import glob
    import shutil
    import socket
    import subprocess
    import tempfile

    if os.environ.get(env_var):
        yield os.environ[env_var]
        return
    bins = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if not bins:
        yield None
        return
    bindir = os.path.dirname(bins[-1])
    as_pg: list[str] = []
    if os.geteuid() == 0:                       # initdb refuses root: run as `postgres`
        import pwd

        try:
            pwd.getpwnam("postgres")
        except KeyError:
            yield None
            return
        as_pg = ["runuser", "-u", "postgres", "--"]
    base = tempfile.mkdtemp(prefix=prefix, dir="/tmp")
    os.chmod(base, 0o755)
    if as_pg:
        shutil.chown(base, user="postgres")
    data = os.path.join(base, "data")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    started = False
    saved = os.environ.get(env_var)
    try:
        def run(*a):
            return subprocess.run(as_pg + list(a), check=True, capture_output=True,
                                  timeout=120)

        run(f"{bindir}/initdb", "-D", data, "-A", "trust", "-U", "postgres")
        started = True   # before start: a start that times out may still leave a postmaster
        run(f"{bindir}/pg_ctl", "-D", data, "-w", "-l", os.path.join(base, "log"), "-o",
            f"-c listen_addresses=127.0.0.1 -c port={port} -c unix_socket_directories={base}",
            "start")
        run(f"{bindir}/createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres",
            db_name)
        url = f"postgresql://postgres@127.0.0.1:{port}/{db_name}"
        os.environ[env_var] = url
        yield url
    finally:
        if saved is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = saved
        if started:
            subprocess.run(as_pg + [f"{bindir}/pg_ctl", "-D", data, "-m", "immediate", "-w",
                                    "stop"], capture_output=True, timeout=120)
        shutil.rmtree(base, ignore_errors=True)
