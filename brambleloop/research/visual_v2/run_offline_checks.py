"""Run selected existing evidence/gate tests in isolated, network-disabled processes.

Optional first argument: directory containing scipy (for bundled Python runtimes).
No main from a provider runner is called. Historical path dependencies can fail;
preserve those failures rather than treating them as a product result.
"""
import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out/tests"
SUITES = ["research/e1/test_specs.py", "research/e3/test_e3.py", "research/e4/test_e4.py",
          "research/e5/test_e5.py", "research/bench1/test_bench1.py", "research/bench2/test_bench2.py",
          "research/v1grad/test_v1grad.py", "tests/test_fabric_relief.py"]


def run(suite, deps):
    code = """
import sys, socket, runpy
sys.dont_write_bytecode = True
sys.path[:0] = [sys.argv[1], sys.argv[2]]
def no_network(*args, **kwargs):
    raise RuntimeError('Visual V2 offline test: network is forbidden')
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network
runpy.run_path(sys.argv[3], run_name='__main__')
"""
    start = time.perf_counter()
    r = subprocess.run([sys.executable, "-c", code, deps, str(ROOT / "src"), str(ROOT / suite)], cwd=ROOT, capture_output=True, text=True, errors="replace")
    log = r.stdout + r.stderr
    filename = suite.replace("/", "_") + ".full.log"
    (OUT / filename).write_text(log, encoding="utf-8", newline="\n")
    summary = {"suite": suite, "exit_code": r.returncode, "seconds": round(time.perf_counter()-start, 2),
               "tail": log.splitlines()[-12:], "failures": [l for l in log.splitlines() if l.startswith(("FAIL", "FAILED", "ERROR"))]}
    print(json.dumps(summary), flush=True)
    return summary


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    deps = str(Path(sys.argv[1]).resolve()) if len(sys.argv)>1 else ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda s: run(s, deps), SUITES))
    (OUT / "offline_checks.json").write_text(json.dumps({"network_disabled": True, "suites": records}, indent=2), encoding="utf-8", newline="\n")
    sys.exit(any(r["exit_code"] for r in records))
