"""F-470 Resource-Aware Concurrency: what the container actually has, read from the kernel.

Concurrency was bounded by a fixed pool, lane limits, provider breakers and DB lock handling;
CPU, memory and database capacity were never measured, so the pool could scale up into a
container that was already swapping. This reads, without any dependency:

* process RSS (``/proc/self/status`` VmRSS) against the memory limit (cgroup v2
  ``memory.max``, else v1 ``memory.limit_in_bytes``, else ``MemTotal``);
* CPU pressure for this container (cgroup v2 PSI ``cpu.pressure``, "some avg60"). The load
  average is reported too, per usable CPU, but only as information: ``/proc/loadavg`` is
  host-wide inside a container, so it would scale this pool down for a neighbour's load;
* process CPU seconds (``/proc/self/stat``);
* database connections in use against ``max_connections`` (Postgres only; SQLite has none to
  count, which is reported as not applicable rather than zero).

`saturated` is true when any reading crosses its threshold. `swarm.capacity.worker_target`
reads it and returns to one worker while saturated; `ops.health` reports it as the
``resources`` signal. Every value a platform does not expose is None with the reason.
"""
from __future__ import annotations

import os
from pathlib import Path

MEMORY_SATURATED = 0.85      # RSS share of the memory limit
CPU_PRESSURE_SATURATED = 80.0  # % of the last minute some task waited for CPU (PSI avg60)
DB_SATURATED = 0.80          # connections in use / max_connections
# W4-FMBATCH1 (F-470): storage capacity and I/O pressure, the half CLOSE5 found unmeasured.
STORAGE_FREE_SHARE_MIN = 0.02  # free share of a working filesystem below this saturates
STORAGE_FREE_GB_MIN = 2.0      # ... or free GB below this, whichever bites first
IO_PRESSURE_SATURATED = 50.0   # % of the last minute some task waited on I/O (PSI avg60)

_PROC = Path("/proc")
_CGROUP = Path("/sys/fs/cgroup")


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except Exception:  # noqa: BLE001 - absent on this platform
        return None


def rss_bytes(proc: Path = _PROC) -> int | None:
    text = _read(proc / "self" / "status")
    for line in (text or "").splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return None


def memory_limit_bytes(cgroup: Path = _CGROUP, proc: Path = _PROC) -> tuple[int | None, str]:
    v2 = _read(cgroup / "memory.max")
    if v2 and v2.isdigit():
        return int(v2), "cgroup v2 memory.max"
    v1 = _read(cgroup / "memory" / "memory.limit_in_bytes")
    if v1 and v1.isdigit() and int(v1) < 1 << 60:
        return int(v1), "cgroup v1 memory.limit_in_bytes"
    for line in (_read(proc / "meminfo") or "").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024, "MemTotal (no cgroup limit)"
    return None, "no memory limit readable"


def usable_cpus(cgroup: Path = _CGROUP) -> tuple[float | None, str]:
    q = _read(cgroup / "cpu.max")
    if q:
        parts = q.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and int(parts[1]):
            return round(int(parts[0]) / int(parts[1]), 3), "cgroup v2 cpu.max quota"
    n = os.cpu_count()
    return (float(n), "os.cpu_count") if n else (None, "cpu count unreadable")


def cpu_pressure_avg60(cgroup: Path = _CGROUP) -> float | None:
    for line in (_read(cgroup / "cpu.pressure") or "").splitlines():
        if line.startswith("some "):
            for part in line.split()[1:]:
                if part.startswith("avg60="):
                    try:
                        return float(part.split("=", 1)[1])
                    except ValueError:
                        return None
    return None


def cpu_seconds(proc: Path = _PROC) -> float | None:
    text = _read(proc / "self" / "stat")
    if not text:
        return None
    try:
        fields = text.rsplit(")", 1)[1].split()
        ticks = os.sysconf("SC_CLK_TCK")
        return round((int(fields[11]) + int(fields[12])) / ticks, 2)
    except Exception:  # noqa: BLE001
        return None


def io_pressure_avg60(cgroup: Path = _CGROUP) -> float | None:
    text = _read(cgroup / "io.pressure")
    for line in (text or "").splitlines():
        if line.startswith("some "):
            for part in line.split():
                if part.startswith("avg60="):
                    try:
                        return float(part.split("=", 1)[1])
                    except ValueError:
                        return None
    return None


def storage(paths: dict[str, str] | None = None) -> dict:
    """Free space where this container writes (temp and artifacts), per filesystem."""
    import shutil
    import tempfile

    paths = paths if paths is not None else {
        "tmp": tempfile.gettempdir(),
        "artifacts": os.environ.get("BRAMBLELOOP_ARTIFACT_DIR", "artifacts")}
    out = {}
    for name, path in paths.items():
        target = path if os.path.isdir(path) else None
        if target is None:
            out[name] = {"free_share": None, "why": f"{path} does not exist here"}
            continue
        try:
            u = shutil.disk_usage(target)
        except OSError as exc:
            out[name] = {"free_share": None, "why": f"unreadable: {exc}"[:120]}
            continue
        out[name] = {"free_gb": round(u.free / 1e9, 3), "total_gb": round(u.total / 1e9, 3),
                     "free_share": round(u.free / u.total, 4) if u.total else None}
    return out


def db_connections(db) -> dict:
    eng = getattr(db, "engine", None)
    if eng is None or eng.dialect.name != "postgresql":
        return {"in_use": None, "max": None, "share": None,
                "why": "not applicable: only a Postgres server has a connection limit"}
    from sqlalchemy import text

    try:
        with eng.connect() as c:
            in_use = int(c.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )).scalar() or 0)
            mx = int(c.execute(text("SHOW max_connections")).scalar() or 0)
    except Exception as exc:  # noqa: BLE001
        return {"in_use": None, "max": None, "share": None,
                "why": f"unreadable: {type(exc).__name__}"}
    return {"in_use": in_use, "max": mx, "share": round(in_use / mx, 4) if mx else None,
            "why": "pg_stat_activity / max_connections"}


def read(db=None, *, proc: Path = _PROC, cgroup: Path = _CGROUP, load=None,
         storage_paths: dict[str, str] | None = None) -> dict:
    rss = rss_bytes(proc)
    limit, limit_src = memory_limit_bytes(cgroup, proc)
    cpus, cpu_src = usable_cpus(cgroup)
    try:
        load1 = (load or os.getloadavg)()[0]
    except Exception:  # noqa: BLE001
        load1 = None
    dbc = db_connections(db) if db is not None else {"share": None, "why": "no database given"}
    mem_share = round(rss / limit, 4) if rss and limit else None
    load_per_cpu = round(load1 / cpus, 3) if load1 is not None and cpus else None
    psi = cpu_pressure_avg60(cgroup)
    hot = []
    if mem_share is not None and mem_share >= MEMORY_SATURATED:
        hot.append(f"memory {mem_share:.0%} of the {limit_src} limit")
    if psi is not None and psi >= CPU_PRESSURE_SATURATED:
        hot.append(f"CPU pressure {psi}% (PSI some avg60)")
    if dbc.get("share") is not None and dbc["share"] >= DB_SATURATED:
        hot.append(f"database connections at {dbc['share']:.0%} of max_connections")
    io = io_pressure_avg60(cgroup)
    if io is not None and io >= IO_PRESSURE_SATURATED:
        hot.append(f"I/O pressure {io}% (PSI some avg60)")
    disks = storage(storage_paths)
    for name, d in disks.items():
        share, free = d.get("free_share"), d.get("free_gb")
        if share is not None and (share < STORAGE_FREE_SHARE_MIN
                                  or (free is not None and free < STORAGE_FREE_GB_MIN)):
            hot.append(f"storage {name}: {free} GB free ({share:.0%})")
    measured = mem_share is not None or psi is not None
    return {
        "rss_bytes": rss, "memory_limit_bytes": limit, "memory_limit_source": limit_src,
        "memory_share": mem_share, "usable_cpus": cpus, "cpu_source": cpu_src,
        "load1": load1, "load_per_cpu": load_per_cpu,
        "load_note": "host-wide inside a container: informational, never saturation",
        "cpu_pressure_avg60": psi, "cpu_seconds": cpu_seconds(proc),
        "db_connections": dbc,
        "io_pressure_avg60": io, "storage": disks,
        # The memory and CPU limits read above are the hosting platform's container limits
        # (Railway sets them as the cgroup), so "platform capacity" is those readings.
        "platform_capacity_source": f"{limit_src}; {cpu_src}",
        "saturated": bool(hot) if measured else None,
        "why": ("; ".join(hot) if hot else
                "within thresholds" if measured else
                "UNKNOWN: neither memory nor CPU pressure is readable on this platform"),
        "thresholds": {"memory_share": MEMORY_SATURATED,
                       "cpu_pressure_avg60": CPU_PRESSURE_SATURATED,
                       "db_share": DB_SATURATED,
                       "io_pressure_avg60": IO_PRESSURE_SATURATED,
                       "storage_free_share_min": STORAGE_FREE_SHARE_MIN,
                       "storage_free_gb_min": STORAGE_FREE_GB_MIN},
    }
